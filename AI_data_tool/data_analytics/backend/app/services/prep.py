"""Step-based data preparation: an ordered, persisted pipeline of cleansing and
shaping steps applied every time an import dataset's frame is loaded.

This is the Power Query counterpart: dedupe, null handling, trim/case, value
replacement, rename, retype, split, row filters, column removal, aggregation and
single-cell corrections, stored as one JSON list and applied in order.

`edit_cells` is where this differs from SAS on purpose. SAS edits the source
table in place; here a typed correction becomes a STEP, addressed by the value
of a key column rather than a row number. The source file is never rewritten, the
correction is visible in the pipeline beside every other change, it survives a
re-upload of the same data, and removing it restores the original -- none of
which is true of a row write. The cost is that a row with no usable key cannot be
corrected this way, which is the honest half of the trade. Non-destructive by design -- the
uploaded file is never rewritten, so removing a step restores what it changed,
which is the property that makes the editor safe to experiment in.

Where it sits in the load order (see get_widget_data):

    load -> column security -> RLS -> PREP -> dataset filter -> calc columns

After RLS on purpose: an aggregate step must summarise only the rows this user
may see, and a fill-from-mean must impute from the visible slice -- running prep
first would leak hidden rows' influence into both. After column security for
the same fail-closed reason.

Storage: `Dataset.column_meta[PREP_STEPS_KEY]` -- a reserved key in an existing
JSON map, because create_all never ALTERs deployed tables (same pattern as
`__exports_disabled__`, and as `DERIVED_FROM_KEY` below).

A pipeline can also be MATERIALIZED: `POST /datasets/{id}/materialize` runs it
once and writes the result as a new import dataset, which is how several
datasets joined together become one listable dataset rather than a view that
re-joins on every read. The new dataset records its recipe under
`DERIVED_FROM_KEY` and can be re-run with `POST /datasets/{id}/rebuild`.

Failure model: steps are validated hard at save time (the router 400s), and
skipped soft at apply time (a column deleted by a re-upload must degrade the one
step that referenced it, not blank every widget on the dataset).
"""
from __future__ import annotations

import pandas as pd

PREP_STEPS_KEY = "__prep_steps__"
MAX_STEPS = 50

#: Provenance for a dataset MATERIALIZED from another one's pipeline -- the
#: recipe that produced its rows, so it can be rebuilt and so lineage can draw
#: the edge. Stored in `column_meta` for the same reason PREP_STEPS_KEY is:
#: `create_all` never ALTERs a deployed table, so a real column would exist on
#: fresh databases and be silently missing on every already-deployed one.
#:
#:     {"source_dataset_id": 12, "join_dataset_ids": [15, 19],
#:      "steps": [...],                  # verbatim SNAPSHOT, see below
#:      "built_by_user_id": 7, "built_at": "...Z", "built_rows": 48213,
#:      "recipe_version": 1}
#:
#: `steps` is a snapshot, not a pointer: a rebuild replays exactly what was used
#: at save time, never "whatever the source's pipeline says now". That is the
#: whole content of the promise that a saved dataset does not change under a
#: report when somebody edits the pipeline it came from.
DERIVED_FROM_KEY = "__derived_from__"

#: A many-to-many join multiplies rows: 10k x 10k on a shared key is 100M rows,
#: which exhausts memory long before the storage quota would notice. Checked on
#: the in-memory frame before anything is written.
MATERIALIZE_MAX_ROWS = 2_000_000

_AGGS = {"sum": "sum", "avg": "mean", "mean": "mean", "min": "min", "max": "max",
         "count": "count", "median": "median", "nunique": "nunique"}
_CASES = {"upper", "lower", "title"}
_FILL_METHODS = {"value", "zero", "mean", "median", "mode", "ffill", "bfill", "interpolate"}
_DEDUPE_KEEP = {"first", "last", "none"}
# ── Data preparation for analysis and modelling (2026-09-25) ────────────────
_OUTLIER_METHODS = {"iqr", "zscore"}
_OUTLIER_ACTIONS = {"flag", "remove", "cap"}
_NORMALIZE_METHODS = {"minmax", "zscore", "log"}
_ENCODE_METHODS = {"onehot", "label"}
_DATE_PARTS = {"year", "quarter", "month", "day", "weekday", "hour", "dayofyear", "week"}
_BALANCE_METHODS = {"undersample", "oversample"}
#: One-hot makes one column per category; past this it is a different problem
#: (an id, a free-text field) and a label code is the honest encoding.
MAX_ONEHOT_CATEGORIES = 50
MAX_PCA_COMPONENTS = 10
PARTITION_TEST = "Test"


def encoded_column(column: str, category) -> str:
    """The one-hot column for `category`: region_North."""
    return f"{column}_{category}"
_RETYPES = {"numeric", "text", "datetime"}
_JOIN_HOW = {"left", "right", "inner", "full"}
_SORT_DIRS = {"asc", "desc"}
#: Cell edits per step. A step is a correction, not a data load: past this the
#: honest answer is a join or a fixed source, and thousands of edits carried in
#: a JSON column would be replayed on every single load of the dataset.
MAX_CELL_EDITS = 500


def prep_steps_of(dataset) -> list[dict]:
    """The saved pipeline, or []. Accepts the ORM row or a raw column_meta dict."""
    meta = dataset if isinstance(dataset, dict) else (getattr(dataset, "column_meta", None) or {})
    steps = meta.get(PREP_STEPS_KEY)
    return steps if isinstance(steps, list) else []


def derived_from_of(dataset) -> dict | None:
    """The materialization recipe, or None for a dataset that was uploaded or
    imported rather than built from others. Accepts the ORM row or a raw dict."""
    meta = dataset if isinstance(dataset, dict) else (getattr(dataset, "column_meta", None) or {})
    prov = meta.get(DERIVED_FROM_KEY)
    return prov if isinstance(prov, dict) else None


def derived_source_ids(prov: dict | None) -> list[int]:
    """Every dataset a materialized one was built from, base first.

    Ints only: the recipe is JSON a previous version may have written
    differently, and a malformed entry must not crash a lineage read.
    """
    if not prov:
        return []
    base = prov.get("source_dataset_id")
    out = [base] if isinstance(base, int) else []
    out += [i for i in (prov.get("join_dataset_ids") or []) if isinstance(i, int)]
    return out


# ── Validation (save time, hard) ─────────────────────────────────────────────

def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise ValueError(msg)


def _str(v) -> bool:
    return isinstance(v, str) and v != ""


def _strlist(v) -> bool:
    return isinstance(v, list) and all(_str(x) for x in v)


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate_prep_steps(steps: list, known_columns: set[str],
                        join_columns: dict[int, set[str]] | None = None) -> set[str]:
    """Raise ValueError on the first malformed step.

    Column references are checked against a name set that EVOLVES through the
    pipeline (rename/split/aggregate change what downstream steps can see), so
    "renamed then used" validates and "used then renamed away" is refused --
    checking everything against the original columns would get both wrong.
    """
    _require(isinstance(steps, list), "steps must be a list")
    _require(len(steps) <= MAX_STEPS, f"at most {MAX_STEPS} steps")
    cols = set(known_columns)

    def has(c, i):
        _require(c in cols, f"step {i + 1}: column '{c}' does not exist at this point in the pipeline")

    for i, s in enumerate(steps):
        _require(isinstance(s, dict), f"step {i + 1}: not an object")
        kind = s.get("kind")
        if kind == "drop_duplicates":
            for c in s.get("subset") or []:
                has(c, i)
        elif kind == "drop_nulls":
            for c in s.get("columns") or []:
                has(c, i)
        elif kind == "fill_nulls":
            _require(_str(s.get("column")), f"step {i + 1}: fill_nulls needs a column")
            has(s["column"], i)
            m = s.get("method")
            _require(m in _FILL_METHODS, f"step {i + 1}: method must be one of {sorted(_FILL_METHODS)}")
            if m == "value":
                _require("value" in s, f"step {i + 1}: method 'value' needs a value")
        elif kind == "trim":
            for c in s.get("columns") or []:
                has(c, i)
        elif kind == "case":
            _require(_str(s.get("column")), f"step {i + 1}: case needs a column")
            has(s["column"], i)
            _require(s.get("to") in _CASES, f"step {i + 1}: to must be one of {sorted(_CASES)}")
        elif kind == "replace":
            _require(_str(s.get("column")), f"step {i + 1}: replace needs a column")
            has(s["column"], i)
            _require("find" in s, f"step {i + 1}: replace needs a find value")
            _require("replace" in s, f"step {i + 1}: replace needs a replacement value")
            _require(s.get("match", "exact") in {"exact", "contains"},
                     f"step {i + 1}: match must be 'exact' or 'contains'")
        elif kind == "rename":
            _require(_str(s.get("column")) and _str(s.get("to")), f"step {i + 1}: rename needs column and to")
            has(s["column"], i)
            _require(s["to"] not in cols, f"step {i + 1}: '{s['to']}' already exists")
            cols.discard(s["column"]); cols.add(s["to"])
        elif kind == "retype":
            _require(_str(s.get("column")), f"step {i + 1}: retype needs a column")
            has(s["column"], i)
            _require(s.get("to") in _RETYPES, f"step {i + 1}: to must be one of {sorted(_RETYPES)}")
        elif kind == "split":
            _require(_str(s.get("column")), f"step {i + 1}: split needs a column")
            has(s["column"], i)
            _require(_str(s.get("delimiter")), f"step {i + 1}: split needs a delimiter")
            into = s.get("into")
            _require(_strlist(into) and 0 < len(into) <= 6, f"step {i + 1}: 'into' needs 1-6 new column names")
            for n in into:
                _require(n not in cols, f"step {i + 1}: '{n}' already exists")
            cols |= set(into)
        elif kind == "filter_rows":
            _require(_str(s.get("expression")), f"step {i + 1}: filter_rows needs an expression")
        elif kind == "remove_columns":
            named = s.get("columns")
            _require(_strlist(named) and named, f"step {i + 1}: remove_columns needs column names")
            for c in named:
                has(c, i)
            _require(set(named) != cols, f"step {i + 1}: cannot remove every column")
            cols -= set(named)
        elif kind == "aggregate":
            gb = s.get("group_by")
            _require(_strlist(gb) and gb, f"step {i + 1}: aggregate needs group_by columns")
            aggs = s.get("aggregations")
            _require(isinstance(aggs, list) and aggs, f"step {i + 1}: aggregate needs aggregations")
            for c in gb:
                has(c, i)
            new_cols = set(gb)
            for a in aggs:
                _require(isinstance(a, dict) and _str(a.get("column")), f"step {i + 1}: each aggregation needs a column")
                has(a["column"], i)
                _require(a.get("agg") in _AGGS, f"step {i + 1}: agg must be one of {sorted(_AGGS)}")
                new_cols.add(a.get("as") or a["column"])
            cols = new_cols
        elif kind == "sort":
            by = s.get("columns")
            _require(isinstance(by, list) and by, f"step {i + 1}: sort needs at least one column")
            for entry in by:
                _require(isinstance(entry, dict) and _str(entry.get("column")),
                         f"step {i + 1}: each sort entry needs a column")
                has(entry["column"], i)
                _require(entry.get("dir", "asc") in _SORT_DIRS,
                         f"step {i + 1}: sort dir must be one of {sorted(_SORT_DIRS)}")
        elif kind == "dedupe":
            for c in s.get("subset") or []:
                has(c, i)
            _require(s.get("keep", "first") in _DEDUPE_KEEP,
                     f"step {i + 1}: keep must be one of {sorted(_DEDUPE_KEEP)}")
        elif kind == "partition":
            _require(_str(s.get("name")), f"step {i + 1}: partition needs a column name")
            _require(s["name"] not in cols, f"step {i + 1}: '{s['name']}' already exists")
            pct = s.get("train_pct")
            _require(isinstance(pct, (int, float)) and not isinstance(pct, bool) and 1 <= pct <= 99,
                     f"step {i + 1}: train_pct must be between 1 and 99")
            test = s.get("test_pct", 0) or 0
            _require(_num(test) and 0 <= test <= 98 and pct + test <= 100,
                     f"step {i + 1}: test_pct must be 0-98 and leave train_pct + test_pct at most 100")
            seed = s.get("seed", 42)
            _require(isinstance(seed, int) and not isinstance(seed, bool), f"step {i + 1}: seed must be a whole number")
            if s.get("key"):
                has(s["key"], i)
            if s.get("stratify"):
                has(s["stratify"], i)
            cols |= {s["name"]}
        elif kind == "outliers":
            cs = s.get("columns")
            _require(_strlist(cs) and bool(cs), f"step {i + 1}: outliers needs at least one column")
            for c in cs:
                has(c, i)
            _require(s.get("method", "iqr") in _OUTLIER_METHODS,
                     f"step {i + 1}: method must be one of {sorted(_OUTLIER_METHODS)}")
            _require(s.get("k") is None or (_num(s["k"]) and s["k"] > 0), f"step {i + 1}: k must be a positive number")
            act = s.get("action", "flag")
            _require(act in _OUTLIER_ACTIONS, f"step {i + 1}: action must be one of {sorted(_OUTLIER_ACTIONS)}")
            if act == "flag":
                flag = s.get("name") or "_Outlier_"
                _require(_str(flag) and flag not in cols, f"step {i + 1}: '{flag}' already exists")
                cols |= {flag}
        elif kind == "normalize":
            cs = s.get("columns")
            _require(_strlist(cs) and bool(cs), f"step {i + 1}: normalize needs at least one column")
            for c in cs:
                has(c, i)
            _require(s.get("method") in _NORMALIZE_METHODS,
                     f"step {i + 1}: method must be one of {sorted(_NORMALIZE_METHODS)}")
            suffix = s.get("suffix", "")
            _require(isinstance(suffix, str), f"step {i + 1}: suffix must be text")
            if suffix:
                for c in cs:
                    _require(c + suffix not in cols, f"step {i + 1}: '{c + suffix}' already exists")
                    cols.add(c + suffix)
        elif kind == "encode":
            _require(_str(s.get("column")), f"step {i + 1}: encode needs a column")
            has(s["column"], i)
            m = s.get("method")
            _require(m in _ENCODE_METHODS, f"step {i + 1}: method must be one of {sorted(_ENCODE_METHODS)}")
            cats = s.get("categories")
            _require(cats is None or (isinstance(cats, list) and all(isinstance(x, (str, int, float))
                                                                     and not isinstance(x, bool) for x in cats)),
                     f"step {i + 1}: categories must be a list of values")
            if m == "onehot":
                # The new columns must be known BEFORE the data is read, so later
                # steps (and every field picker) can name them -- hence an explicit
                # list, which also keeps a model's inputs fixed across refreshes.
                _require(bool(cats) and len(cats) <= MAX_ONEHOT_CATEGORIES,
                         f"step {i + 1}: one-hot needs 1-{MAX_ONEHOT_CATEGORIES} categories")
                new = [encoded_column(s["column"], x) for x in cats]
            else:
                new = [f"{s['column']}_code"]
            for n in new:
                _require(n not in cols, f"step {i + 1}: '{n}' already exists")
            cols |= set(new)
            if s.get("drop_original"):
                cols.discard(s["column"])
        elif kind == "date_parts":
            _require(_str(s.get("column")), f"step {i + 1}: date_parts needs a column")
            has(s["column"], i)
            parts = s.get("parts")
            _require(_strlist(parts) and bool(parts) and set(parts) <= _DATE_PARTS,
                     f"step {i + 1}: parts must be some of {sorted(_DATE_PARTS)}")
            for p in parts:
                n = f"{s['column']}_{p}"
                _require(n not in cols, f"step {i + 1}: '{n}' already exists")
                cols.add(n)
        elif kind == "feature_select":
            for key, lo, hi in (("max_missing_pct", 0, 100), ("min_variance", 0, None), ("max_correlation", 0, 1)):
                v = s.get(key)
                _require(v is None or (_num(v) and v >= lo and (hi is None or v <= hi)),
                         f"step {i + 1}: {key} is out of range")
            _require(any(s.get(k) is not None for k in ("max_missing_pct", "min_variance", "max_correlation")),
                     f"step {i + 1}: feature_select needs at least one rule")
            for c in s.get("keep") or []:
                has(c, i)
            # Which columns go is only known once the data is read, so `cols` is
            # left as is: a later step naming a dropped column degrades softly.
        elif kind == "pca":
            cs = s.get("columns")
            _require(_strlist(cs) and len(cs) >= 2, f"step {i + 1}: pca needs at least two columns")
            for c in cs:
                has(c, i)
            n = s.get("n", 2)
            _require(isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= min(len(cs), MAX_PCA_COMPONENTS),
                     f"step {i + 1}: n must be 1-{min(len(cs), MAX_PCA_COMPONENTS)}")
            prefix = s.get("prefix") or "PC"
            _require(_str(prefix), f"step {i + 1}: prefix must be text")
            for j in range(1, n + 1):
                _require(f"{prefix}{j}" not in cols, f"step {i + 1}: '{prefix}{j}' already exists")
                cols.add(f"{prefix}{j}")
        elif kind == "balance":
            _require(_str(s.get("column")), f"step {i + 1}: balance needs a class column")
            has(s["column"], i)
            _require(s.get("method") in _BALANCE_METHODS,
                     f"step {i + 1}: method must be one of {sorted(_BALANCE_METHODS)}")
            seed = s.get("seed", 42)
            _require(isinstance(seed, int) and not isinstance(seed, bool), f"step {i + 1}: seed must be a whole number")
            if s.get("only_column"):
                has(s["only_column"], i)
        elif kind == "append":
            _require(isinstance(s.get("dataset_id"), int), f"step {i + 1}: append needs a dataset_id")
            other_cols = (join_columns or {}).get(s["dataset_id"])
            if other_cols is not None:
                cols |= set(other_cols)
            src = s.get("source_column")
            if src:
                _require(_str(src) and src not in cols, f"step {i + 1}: '{src}' already exists")
                cols.add(src)
        elif kind == "edit_cells":
            _require(_str(s.get("key_column")), f"step {i + 1}: edit_cells needs a key_column")
            _require(_str(s.get("column")), f"step {i + 1}: edit_cells needs a column")
            has(s["key_column"], i)
            has(s["column"], i)
            # The key is how an edit finds its row. Editing it in the same step
            # would make the step's own result depend on evaluation order.
            _require(s["column"] != s["key_column"],
                     f"step {i + 1}: cannot edit the key column the edits are matched on")
            edits = s.get("edits")
            _require(isinstance(edits, list) and edits,
                     f"step {i + 1}: edit_cells needs at least one edit")
            _require(len(edits) <= MAX_CELL_EDITS,
                     f"step {i + 1}: at most {MAX_CELL_EDITS} cell edits per step")
            for e in edits:
                _require(isinstance(e, dict) and e.get("key") is not None,
                         f"step {i + 1}: each edit needs the key of the row it applies to")
                _require("value" in e, f"step {i + 1}: each edit needs a value")
        elif kind == "join":
            _require(isinstance(s.get("dataset_id"), int), f"step {i + 1}: join needs a dataset_id")
            _require(s.get("how") in _JOIN_HOW, f"step {i + 1}: how must be one of {sorted(_JOIN_HOW)}")
            pairs = join_key_pairs(s)
            _require(bool(pairs), f"step {i + 1}: join needs a key column on each side")
            if isinstance(s.get("left_ons"), list) or isinstance(s.get("right_ons"), list):
                # Composite keys match position for position, so a missing entry
                # on one side would silently pair the wrong columns.
                _require(len(s.get("left_ons") or []) == len(s.get("right_ons") or []),
                         f"step {i + 1}: join needs the same number of key columns on each side")
            for left, _r in pairs:
                has(left, i)
            right_cols = (join_columns or {}).get(s["dataset_id"])
            if right_cols is not None:
                for _l, right in pairs:
                    _require(right in right_cols,
                             f"step {i + 1}: column '{right}' does not exist on the joined dataset")
                # After the merge, overlapping right columns arrive suffixed '_2'
                # (pandas suffixes=('', '_2')) -- mirror that so downstream steps
                # validate against what will actually exist.
                for c in right_cols:
                    cols.add(f"{c}_2" if c in cols else c)
        else:
            raise ValueError(f"step {i + 1}: unknown kind '{kind}'")
    # The columns the pipeline ENDS with -- what a widget can actually use.
    return cols


def prep_added_columns(steps: list | None, columns: dict[str, str],
                       join_columns: dict[int, set[str]] | None = None) -> list[tuple[str, str]]:
    """(name, dtype) of every column the pipeline CREATES, for the schema listing.

    The stored column list is the uploaded file's; a partition, a split or a
    rename made by prep never reached it, so no field picker could offer the
    column the author had just made. Only additions are reported (a removed or
    renamed-away column stays listed -- the conservative direction: a stale
    field renders empty, a missing one cannot be chosen at all). A pipeline
    that no longer validates reports nothing rather than guessing."""
    if not steps:
        return []
    try:
        final = validate_prep_steps(steps, set(columns), join_columns)
    except ValueError:
        return []
    dtype: dict[str, str] = dict(columns)
    for s in steps:
        if not isinstance(s, dict):
            continue
        k = s.get("kind")
        if k == "rename" and s.get("column") in dtype:
            dtype[s["to"]] = dtype[s["column"]]
        elif k == "retype":
            dtype[s.get("column")] = {"numeric": "numeric", "datetime": "datetime"}.get(s.get("to"), "categorical")
        elif k == "aggregate":
            for a in s.get("aggregations") or []:
                if isinstance(a, dict):
                    dtype.setdefault(a.get("as") or a.get("column"), "numeric")
        elif k == "normalize" and s.get("suffix"):
            for c in s.get("columns") or []:
                dtype.setdefault(c + s["suffix"], "numeric")
        elif k == "encode":
            if s.get("method") == "onehot":
                for cat in s.get("categories") or []:
                    dtype.setdefault(encoded_column(s.get("column"), cat), "numeric")
            else:
                dtype.setdefault(f"{s.get('column')}_code", "numeric")
        elif k == "date_parts":
            for p in s.get("parts") or []:
                dtype.setdefault(f"{s.get('column')}_{p}", "numeric")
        elif k == "pca":
            for j in range(1, int(s.get("n", 2)) + 1):
                dtype.setdefault(f"{s.get('prefix') or 'PC'}{j}", "numeric")
    return [(n, dtype.get(n, "categorical")) for n in sorted(final - set(columns))]


# ── Application (load time, soft) ────────────────────────────────────────────

def join_key_pairs(s: dict) -> list[tuple[str, str]]:
    """The (left, right) column pairs a join step matches on.

    Two shapes are accepted, and both are load-bearing:

        {"left_on": "cust", "right_on": "id"}                 # one pair
        {"left_ons": ["region", "date"],
         "right_ons": ["region", "as_of"]}                    # composite

    The singular form came first and is what every pipeline saved before
    composite keys existed still carries, so it is read verbatim rather than
    migrated -- a rewrite over `column_meta` JSON in every deployment would be a
    lot of risk for a shape that costs three lines to keep supporting.

    Returns [] when the step names no usable key, which the callers treat as
    "not joinable" rather than guessing.
    """
    lefts = s.get("left_ons")
    rights = s.get("right_ons")
    if isinstance(lefts, list) and isinstance(rights, list):
        pairs = [(l, r) for l, r in zip(lefts, rights)
                 if isinstance(l, str) and l.strip() and isinstance(r, str) and r.strip()]
        # Ragged lists mean the editor is mid-edit or the JSON was hand-written;
        # zip already truncates to the shorter one, which is the safe reading.
        if pairs:
            return pairs
    left, right = s.get("left_on"), s.get("right_on")
    if isinstance(left, str) and left.strip() and isinstance(right, str) and right.strip():
        return [(left, right)]
    return []


PARTITION_TRAIN = "Training"
PARTITION_VALIDATION = "Validation"


def partition_column(df: pd.DataFrame, s: dict) -> pd.DataFrame:
    """A persistent train/validation split (MASTER_PLAN Phase 3 item 4).

    Assigned by a SEEDED HASH of each row's key, never by drawing random
    numbers over the rows at hand. That is what makes it a property of the
    row: the frame this runs on has already been narrowed by the viewer's
    row-level security, so a random draw would put the same row in Training
    for one user and in Validation for another, and two model widgets could
    never agree on what "held out" meant. A hash does not care which other
    rows are present.

    The key defaults to the row's position in the source file. Naming a key
    column (customer id) keeps every row of one customer on the same side --
    the split a churn model needs, or it is graded on customers it has seen."""
    import numpy as np

    name = s["name"]
    if name in df.columns:
        return df
    key = s.get("key")
    base = df[key] if key and key in df.columns else pd.Series(df.index, index=df.index)
    hash_key = f"{int(s.get('seed', 42)):016d}"[-16:]
    h = pd.util.hash_pandas_object(base.astype(str), index=False, hash_key=hash_key)
    u = pd.Series(h.to_numpy(dtype="uint64") / float(2 ** 64), index=df.index)
    strat = s.get("stratify")
    if strat and strat in df.columns:
        # Stratified: within each class, rows are placed by the RANK of their
        # hash, so every class splits in the stated proportions (a rare class
        # can no longer land wholly in Training) -- still a property of the
        # rows, not of a random draw.
        groups = df[strat].astype(str).where(df[strat].notna(), "\0")
        u = (u.groupby(groups).rank(method="first") - 0.5) / groups.map(groups.value_counts())
    train = float(s["train_pct"]) / 100.0
    test = float(s.get("test_pct") or 0) / 100.0
    # Training keeps the same rows whether or not a Test share is added: Test is
    # carved from the TOP of the range, Validation is what lies between.
    labels = np.where(u < train, PARTITION_TRAIN,
                      np.where(u >= 1.0 - test, PARTITION_TEST, PARTITION_VALIDATION)) if test \
        else np.where(u < train, PARTITION_TRAIN, PARTITION_VALIDATION)
    return df.assign(**{name: labels})


# ── Preparation for analysis and modelling ──────────────────────────────────
# Each works on the frame it is given, which is already the VIEWER's
# RLS-filtered rows: a bound, a mean or a sample is computed over what this
# reader may see, never over rows they may not.

def _outlier_bounds(col: pd.Series, method: str, k) -> tuple[float, float] | None:
    x = pd.to_numeric(col, errors="coerce").dropna()
    if x.empty:
        return None
    if method == "zscore":
        k = 3.0 if k is None else float(k)
        sd = float(x.std(ddof=0))
        if not sd:
            return None
        m = float(x.mean())
        return m - k * sd, m + k * sd
    k = 1.5 if k is None else float(k)
    q1, q3 = float(x.quantile(0.25)), float(x.quantile(0.75))
    return q1 - k * (q3 - q1), q3 + k * (q3 - q1)


def _outliers(df: pd.DataFrame, s: dict) -> pd.DataFrame:
    method, k, act = s.get("method", "iqr"), s.get("k"), s.get("action", "flag")
    out = df
    mask = pd.Series(False, index=df.index)
    for c in s.get("columns") or []:
        if c not in out.columns or not pd.api.types.is_numeric_dtype(out[c]) or out[c].dtype == bool:
            continue
        b = _outlier_bounds(out[c], method, k)
        if b is None:
            continue
        if act == "cap":
            out = out.assign(**{c: out[c].clip(lower=b[0], upper=b[1])})
        else:
            mask |= (out[c] < b[0]) | (out[c] > b[1])
    if act == "remove":
        return out[~mask]
    if act == "flag":
        return out.assign(**{s.get("name") or "_Outlier_": mask})
    return out


def _normalize(df: pd.DataFrame, s: dict) -> pd.DataFrame:
    import numpy as np
    out, suffix, m = df, s.get("suffix", ""), s["method"]
    for c in s.get("columns") or []:
        if c not in out.columns or not pd.api.types.is_numeric_dtype(out[c]) or out[c].dtype == bool:
            continue
        x = out[c].astype(float)
        if m == "minmax":
            lo, hi = x.min(), x.max()
            v = (x - lo) / (hi - lo) if pd.notna(lo) and hi != lo else x * 0.0
        elif m == "zscore":
            sd = x.std(ddof=0)
            v = (x - x.mean()) / sd if sd else x * 0.0
        else:  # log: log(1 + x); x <= -1 has no log and becomes blank, not an error
            v = np.log1p(x.where(x > -1))
        out = out.assign(**{c + suffix: v})
    return out


def _encode(df: pd.DataFrame, s: dict) -> pd.DataFrame:
    c = s["column"]
    if c not in df.columns:
        return df
    text = df[c].map(lambda v: None if pd.isna(v) else str(v))
    if s["method"] == "onehot":
        out = df.assign(**{encoded_column(c, cat): (text == str(cat)).astype(int) for cat in s["categories"]})
    else:
        order = [str(x) for x in (s.get("categories") or sorted(text.dropna().unique()))]
        code = {v: i for i, v in enumerate(order)}
        out = df.assign(**{f"{c}_code": text.map(code).astype("Int64")})
    return out.drop(columns=[c]) if s.get("drop_original") else out


def _date_parts(df: pd.DataFrame, s: dict) -> pd.DataFrame:
    c = s["column"]
    if c not in df.columns:
        return df
    dt = pd.to_datetime(df[c], errors="coerce")
    get = {"year": lambda d: d.dt.year, "quarter": lambda d: d.dt.quarter, "month": lambda d: d.dt.month,
           "day": lambda d: d.dt.day, "weekday": lambda d: d.dt.weekday, "hour": lambda d: d.dt.hour,
           "dayofyear": lambda d: d.dt.dayofyear, "week": lambda d: d.dt.isocalendar().week}
    # Int64, not float: a blank date must not turn every year into 2024.0.
    return df.assign(**{f"{c}_{p}": get[p](dt).astype("Int64") for p in s["parts"]})


def _feature_select(df: pd.DataFrame, s: dict) -> pd.DataFrame:
    keep = set(s.get("keep") or [])
    drop: list[str] = []
    candidates = [c for c in df.columns if c not in keep]
    if s.get("max_missing_pct") is not None:
        drop += [c for c in candidates if df[c].isna().mean() * 100 > s["max_missing_pct"]]
    numeric = [c for c in candidates if c not in drop and pd.api.types.is_numeric_dtype(df[c]) and df[c].dtype != bool]
    if s.get("min_variance") is not None:
        drop += [c for c in candidates if c not in drop and df[c].nunique(dropna=True) <= 1]
        drop += [c for c in numeric if c not in drop and float(df[c].var(ddof=0) or 0) <= s["min_variance"]]
    if s.get("max_correlation") is not None:
        rest = [c for c in numeric if c not in drop]
        if len(rest) > 1:
            corr = df[rest].corr().abs()
            for j, c in enumerate(rest):          # keep the first of each correlated pair
                if c not in drop and any(corr.loc[p, c] > s["max_correlation"]
                                         for p in rest[:j] if p not in drop):
                    drop.append(c)
    return df.drop(columns=list(dict.fromkeys(drop)))


def _pca(df: pd.DataFrame, s: dict) -> pd.DataFrame:
    import numpy as np
    cols = [c for c in s["columns"] if c in df.columns and pd.api.types.is_numeric_dtype(df[c])]
    prefix, n = s.get("prefix") or "PC", int(s.get("n", 2))
    if len(cols) < 2:
        return df
    x = df[cols].astype(float)
    ok = x.notna().all(axis=1)
    sd = x[ok].std(ddof=0).replace(0, 1.0)
    z = ((x[ok] - x[ok].mean()) / sd).to_numpy()
    n = min(n, len(cols), int(ok.sum()))
    if n < 1:
        return df
    _u, _s, vt = np.linalg.svd(z, full_matrices=False)
    # A component's sign is arbitrary in SVD; fix it (largest loading positive)
    # so the same data always gives the same scores.
    vt = vt * np.sign(vt[np.arange(vt.shape[0]), np.abs(vt).argmax(axis=1)])[:, None]
    scores = z @ vt[:n].T
    out = df.copy()
    for j in range(n):
        col = pd.Series(np.nan, index=df.index)
        col[ok] = scores[:, j]
        out[f"{prefix}{j + 1}"] = col
    return out


def _balance(df: pd.DataFrame, s: dict) -> pd.DataFrame:
    import numpy as np
    c = s["column"]
    if c not in df.columns:
        return df
    only = s.get("only_column")
    if only:
        # Balance the TRAINING rows only (only_column = only_value): resampling
        # the evaluation rows too would grade the model on copies of itself.
        if only not in df.columns:
            return df
        inside = df[only].astype(str) == str(s.get("only_value", ""))
        balanced = _balance(df[inside], {**s, "only_column": None})
        return pd.concat([balanced, df[~inside]], ignore_index=True)
    known = df[df[c].notna()]
    counts = known[c].value_counts()
    if len(counts) < 2:
        return df
    rng = np.random.default_rng(int(s.get("seed", 42)))
    target = int(counts.min() if s["method"] == "undersample" else counts.max())
    parts = []
    for cls in sorted(counts.index, key=str):     # a fixed order: same seed, same rows
        rows = known[known[c] == cls]
        if s["method"] == "undersample":
            pick = np.sort(rng.choice(len(rows), size=target, replace=False))
            parts.append(rows.iloc[pick])
        else:
            extra = rng.choice(len(rows), size=target - len(rows), replace=True)
            parts.append(pd.concat([rows, rows.iloc[extra]]))
    # Rows with no class are left as they were: balancing cannot place them.
    return pd.concat(parts + [df[df[c].isna()]], ignore_index=True)


#: Step kinds that read ANOTHER dataset: both are loaded and secured as the
#: caller by resolve_join_frames, and both must pass the read check.
OTHER_DATASET_KINDS = ("join", "append")


def collect_join_dataset_ids(steps: list[dict] | None) -> list[int]:
    return [s["dataset_id"] for s in (steps or [])
            if isinstance(s, dict) and s.get("kind") in OTHER_DATASET_KINDS
            and isinstance(s.get("dataset_id"), int)]


def _apply_one(df: pd.DataFrame, s: dict, aux_frames: dict[int, pd.DataFrame] | None = None) -> pd.DataFrame:
    kind = s.get("kind")
    if kind == "join":
        other = (aux_frames or {}).get(s.get("dataset_id"))
        # A missing frame (dataset deleted, cross-org, RLS resolved to nothing the
        # caller could load) degrades to a no-op: fail-soft for availability, and
        # fail-CLOSED for data -- skipping a join never leaks rows, it omits them.
        if other is None:
            return df
        pairs = join_key_pairs(s)
        # ALL key columns must be present, not just some: dropping one from a
        # composite key silently widens the match and multiplies rows, which is
        # far worse than not joining at all.
        if not pairs or any(l not in df.columns or r not in other.columns for l, r in pairs):
            return df
        how = {"full": "outer"}.get(s["how"], s["how"])
        return df.merge(other, how=how, left_on=[l for l, _ in pairs],
                        right_on=[r for _, r in pairs], suffixes=("", "_2"))
    if kind == "append":
        # Rows of another dataset stacked under these, matched by column NAME
        # (a column only one side has is blank on the other) -- how the same
        # table from two databases, or two months' files, become one dataset.
        other = (aux_frames or {}).get(s.get("dataset_id"))
        if other is None:
            return df
        out = pd.concat([df, other], ignore_index=True, sort=False)
        src = s.get("source_column")
        if src:
            out[src] = [s.get("base_label") or "this dataset"] * len(df) + \
                       [s.get("label") or f"dataset {s['dataset_id']}"] * len(other)
        return out
    if kind == "outliers":
        return _outliers(df, s)
    if kind == "normalize":
        return _normalize(df, s)
    if kind == "encode":
        return _encode(df, s)
    if kind == "date_parts":
        return _date_parts(df, s)
    if kind == "feature_select":
        return _feature_select(df, s)
    if kind == "pca":
        return _pca(df, s)
    if kind == "balance":
        return _balance(df, s)
    if kind == "sort":
        by = [(e.get("column"), e.get("dir", "asc")) for e in (s.get("columns") or [])
              if isinstance(e, dict) and e.get("column") in df.columns]
        if not by:
            return df
        cols = [c for c, _ in by]
        ascending = [d != "desc" for _, d in by]
        return df.sort_values(by=cols, ascending=ascending, kind="mergesort", na_position="last")
    if kind == "dedupe":
        subset = [c for c in (s.get("subset") or []) if c in df.columns] or None
        keep = s.get("keep", "first")
        # "none": drop EVERY copy of a duplicated row -- the rows no one can
        # say which of is right.
        return df.drop_duplicates(subset=subset, keep=False if keep == "none" else keep)
    if kind == "partition":
        return partition_column(df, s)
    if kind == "drop_duplicates":
        subset = [c for c in (s.get("subset") or []) if c in df.columns] or None
        return df.drop_duplicates(subset=subset)
    if kind == "drop_nulls":
        subset = [c for c in (s.get("columns") or []) if c in df.columns] or None
        return df.dropna(subset=subset)
    if kind == "fill_nulls":
        c, m = s["column"], s["method"]
        if c not in df.columns:
            return df
        col = df[c]
        if m == "value":
            fill = s.get("value")
            # A numeric column filled with a numeric-looking string stays numeric.
            if pd.api.types.is_numeric_dtype(col):
                try:
                    fill = float(fill)
                except (TypeError, ValueError):
                    return df
        elif m == "zero":
            fill = 0
        elif m == "mean":
            fill = col.mean()
        elif m == "median":
            fill = col.median()
        elif m == "mode":
            modes = col.mode()
            if modes.empty:
                return df
            fill = modes.iloc[0]
        elif m == "bfill":
            return df.assign(**{c: col.bfill()})
        elif m == "interpolate":
            # Straight line between the known neighbours; numbers only.
            if not pd.api.types.is_numeric_dtype(col):
                return df
            return df.assign(**{c: col.interpolate(limit_direction="both")})
        else:  # ffill
            return df.assign(**{c: col.ffill()})
        return df.assign(**{c: col.fillna(fill)})
    if kind == "trim":
        named = s.get("columns") or []
        targets = [c for c in named if c in df.columns] if named else \
                  [c for c in df.columns if df[c].dtype == object]
        out = df
        for c in targets:
            if out[c].dtype == object:
                out = out.assign(**{c: out[c].str.strip()})
        return out
    if kind == "case":
        c = s["column"]
        if c not in df.columns or df[c].dtype != object:
            return df
        fn = {"upper": str.upper, "lower": str.lower, "title": str.title}[s["to"]]
        return df.assign(**{c: df[c].map(lambda v: fn(v) if isinstance(v, str) else v)})
    if kind == "replace":
        c = s["column"]
        if c not in df.columns:
            return df
        find, repl = s.get("find"), s.get("replace")
        if s.get("match", "exact") == "contains":
            if df[c].dtype != object:
                return df
            # Literal substring, never a regex: a user typing "1.5" means the text
            # "1.5", and treating it as a pattern would be a quiet wrong answer.
            return df.assign(**{c: df[c].str.replace(str(find), str(repl), regex=False)})
        if pd.api.types.is_numeric_dtype(df[c]):
            try:
                find, repl = float(find), float(repl)
            except (TypeError, ValueError):
                return df
        return df.assign(**{c: df[c].replace(find, repl)})
    if kind == "rename":
        c, to = s["column"], s["to"]
        if c not in df.columns or to in df.columns:
            return df
        return df.rename(columns={c: to})
    if kind == "retype":
        c, to = s["column"], s["to"]
        if c not in df.columns:
            return df
        if to == "numeric":
            return df.assign(**{c: pd.to_numeric(df[c], errors="coerce")})
        if to == "datetime":
            # An integer column of Unix epochs must be told its unit. Without one,
            # pandas reads the integer as NANOSECONDS and lands every row on
            # 1970-01-01 -- a wrong date that looks like a date, which is worse
            # than an error. `epoch_unit` is shared with type detection so the two
            # cannot disagree about what an epoch is.
            from .ingest import epoch_unit
            unit = epoch_unit(df[c])
            if unit:
                return df.assign(**{c: pd.to_datetime(df[c], unit=unit, errors="coerce")})
            return df.assign(**{c: pd.to_datetime(df[c], errors="coerce")})
        return df.assign(**{c: df[c].astype(str)})
    if kind == "split":
        c, delim, into = s["column"], s["delimiter"], s["into"]
        if c not in df.columns or df[c].dtype != object:
            return df
        parts = df[c].str.split(delim, n=len(into), expand=True)
        out = df
        for i, name in enumerate(into):
            if name in out.columns:
                continue
            out = out.assign(**{name: parts[i].str.strip() if i in parts.columns else None})
        return out
    if kind == "edit_cells":
        key, col = s.get("key_column"), s.get("column")
        if key not in df.columns or col not in df.columns:
            return df
        mapping = {str(e.get("key")): e.get("value") for e in s.get("edits") or []
                   if isinstance(e, dict)}
        if not mapping:
            return df
        # Matched on the key as TEXT: the value came through JSON, where 42 and
        # "42" are different things and the column may be either.
        keys = df[key].astype(str)
        hit = keys.isin(mapping)
        if not hit.any():
            return df
        out = df.copy()
        replacement = keys[hit].map(mapping)
        target = out[col]
        if pd.api.types.is_numeric_dtype(target):
            numeric = pd.to_numeric(replacement, errors="coerce")
            # Someone typing "n/a" into a numeric column is a real correction.
            # Widen the column to text rather than turning that cell into NaN,
            # which would read as missing data instead of what they wrote.
            if numeric.notna().all() or replacement.isna().all():
                replacement = numeric
            else:
                out[col] = target.astype(object)
        elif pd.api.types.is_datetime64_any_dtype(target):
            parsed = pd.to_datetime(replacement, errors="coerce")
            if parsed.notna().all() or replacement.isna().all():
                replacement = parsed
            else:
                out[col] = target.astype(object)
        out.loc[hit, col] = replacement
        return out
    if kind == "filter_rows":
        from .widget_data import apply_filter_expr  # lazy: widget_data imports this module
        return apply_filter_expr(df, s["expression"], silent=True)
    if kind == "remove_columns":
        present = [c for c in s.get("columns", []) if c in df.columns]
        if len(present) == len(df.columns):
            return df
        return df.drop(columns=present)
    if kind == "aggregate":
        gb = [c for c in s.get("group_by", []) if c in df.columns]
        if not gb:
            return df
        named = {}
        for a in s.get("aggregations", []):
            col, agg = a.get("column"), _AGGS.get(a.get("agg"))
            if col in df.columns and agg:
                named[a.get("as") or col] = (col, agg)
        if not named:
            return df
        return df.groupby(gb, dropna=False).agg(**named).reset_index()
    return df


def apply_prep_steps(df: pd.DataFrame, steps: list[dict] | None,
                     aux_frames: dict[int, pd.DataFrame] | None = None) -> pd.DataFrame:
    """Apply the pipeline in order. Each step is individually fail-soft: a step
    whose column vanished (re-upload) degrades to a no-op instead of sinking
    every widget on the dataset. Save-time validation is the hard gate.

    `aux_frames` carries the already-secured frames join steps merge against,
    keyed by dataset id -- resolved by the caller via `resolve_join_frames`,
    because securing them takes the db and the requesting identity, which this
    pure function deliberately does not have."""
    for s in steps or []:
        if isinstance(s, dict) and s.get("disabled"):
            # A disabled step is a first-class, persisted "paused" state (the
            # editor's enable/disable toggle) -- it stays in the saved list and
            # round-trips through GET, it just contributes nothing to the frame.
            continue
        try:
            df = _apply_one(df, s, aux_frames)
        except Exception:  # noqa: BLE001 -- see docstring
            continue
    return df


async def resolve_join_frames(db, user, steps: list[dict] | None) -> dict[int, "pd.DataFrame"]:
    """Load and SECURE every dataset the pipeline's join steps reference, as the
    given identity (the viewer, or a schedule/alert's creator).

    Each frame gets the full treatment its own dataset would get on a direct
    read: org check, that dataset's RLS (fail closed), its column-security mask,
    and its own prep steps MINUS joins -- stripping nested joins is what makes
    A-joins-B-joins-A terminate instead of recursing. A dataset that fails any
    check is simply absent, which the join step degrades on (no rows leaked).
    """
    import asyncio

    from ..core.rls import resolve_denied_columns, resolve_rls_expr
    from ..models.models import Dataset
    from .ingest import load_file
    from .widget_data import apply_rls_filter

    out: dict[int, pd.DataFrame] = {}
    for sid in collect_join_dataset_ids(steps):
        if sid in out:
            continue
        ds = await db.get(Dataset, sid)
        if ds is None or ds.org_id != user.org_id or ds.mode != "import" or not ds.filename:
            continue
        try:
            frame = await asyncio.to_thread(load_file, ds.filename)
        except Exception:  # noqa: BLE001 -- absent frame degrades the join, see above
            continue
        rls = await resolve_rls_expr(db, user, sid)
        frame = apply_rls_filter(frame, rls)
        denied = await resolve_denied_columns(db, user, sid)
        present = [c for c in (denied or []) if c in frame.columns]
        if present:
            frame = frame.drop(columns=present)
        own = [x for x in prep_steps_of(ds) if x.get("kind") not in OTHER_DATASET_KINDS]
        frame = await asyncio.to_thread(apply_prep_steps, frame, own)
        out[sid] = frame
    return out


# ── Join match check (the geography panel's pattern, applied to joins) ───────

def join_match_report(left: pd.DataFrame, right: pd.DataFrame, pairs: list[tuple[str, str]],
                      how: str = "left", top: int = 50) -> dict:
    """How a join will land BEFORE it is saved: the share of rows that find a
    partner, the key values that do not (with their row counts), and keys
    that appear more than once on the other side -- the silent row
    multiplier that turns 2,000 orders into 2,340 after a "lookup" join.

    Keys compare as trimmed text, the way a person reads them; the join
    itself compares raw values, so a "1" vs 1 mismatch shows up here as a
    match the join will miss -- reported as `type_mismatch`."""
    lcols = [l for l, _ in pairs]
    rcols = [r for _, r in pairs]
    missing = [c for c in lcols if c not in left.columns] + [c for c in rcols if c not in right.columns]
    if missing:
        return {"error": "column " + ", ".join(f"'{c}'" for c in missing) + " is not there"}

    def keys(frame: pd.DataFrame, cols: list[str]) -> pd.Series:
        parts = [frame[c].astype(str).str.strip().where(frame[c].notna()) for c in cols]
        k = parts[0]
        for p in parts[1:]:
            k = k + " · " + p
        return k

    lk, rk = keys(left, lcols), keys(right, rcols)
    blank = int(lk.isna().sum())
    rcounts = rk.dropna().value_counts()
    matched = lk.notna() & lk.isin(rcounts.index)
    total = int(len(left))
    matched_rows = int(matched.sum())
    unmatched = lk[lk.notna() & ~matched].value_counts()
    dup = rcounts[rcounts > 1]
    fan = lk[matched].map(rcounts).fillna(1)
    pairs_n = int(fan.sum())
    # E06: the other side too. Rows of the joined dataset whose key finds no
    # partner here are dropped by a left/inner join (silently) and kept by a
    # right/full one -- either way the author should see how many.
    lvalues = set(lk.dropna())
    r_matched = rk.notna() & rk.isin(lvalues)
    right_total = int(len(right))
    right_orphans = right_total - int(r_matched.sum())
    after = {"inner": pairs_n,
             "left": pairs_n + (total - matched_rows),
             "right": pairs_n + right_orphans,
             "full": pairs_n + (total - matched_rows) + right_orphans}.get(how)
    # Raw-value compatibility: text keys that match only after str() are a
    # silent miss in the real merge.
    type_mismatch = [f"{l} ({left[l].dtype}) vs {r} ({right[r].dtype})" for l, r in pairs
                     if (pd.api.types.is_numeric_dtype(left[l]) != pd.api.types.is_numeric_dtype(right[r]))]
    return {
        "rows": total, "matched_rows": matched_rows,
        "pct_rows": int((matched_rows * 100) // total) if total else 0,
        "blank_keys": blank,
        "unmatched": [{"key": str(k), "rows": int(n)} for k, n in unmatched.head(top).items()],
        "unmatched_values": int(len(unmatched)),
        "duplicate_right_keys": int(len(dup)),
        "duplicate_examples": [{"key": str(k), "count": int(n)} for k, n in dup.head(5).items()],
        "rows_after": after,
        # rows_after / rows: 1.17 means the join turns 1,000 rows into 1,170.
        "multiplier": round(after / total, 2) if after is not None and total else None,
        "right_rows": right_total,
        "right_unmatched_rows": right_orphans,
        "type_mismatch": type_mismatch,
    }


# ── Cross-source mapping check (Phase 6.1) ─────────────────────────────────────

def mapping_match_report(source: pd.Series, target: pd.Series, top: int = 20) -> dict:
    """Will a click on a value of `source` find rows in `target`?

    A cross-dataset mapping carries a filter VALUE from one dataset to another,
    so what matters is distinct values, not rows: the share of the source's
    values that exist on the target side, the ones that do not (most frequent
    first), and the ones that WOULD match ignoring case and spaces -- a mapping
    that looks right and silently filters to nothing on "Egypt" vs "EGYPT ".
    Compared as trimmed text; a numeric/text pairing is named because the
    filter compares raw values there.
    """
    def text(s: pd.Series) -> pd.Series:
        return s.dropna().astype(str).str.strip()

    src, tgt = text(source), text(target)
    src_counts = src.value_counts()
    tgt_values = set(tgt.unique())
    matched = [v for v in src_counts.index if v in tgt_values]
    unmatched = src_counts[[v not in tgt_values for v in src_counts.index]]
    folded = {v.casefold().replace(" ", ""): v for v in tgt_values}
    near = [{"source": str(v), "target": folded[v.casefold().replace(" ", "")]}
            for v in unmatched.index if v.casefold().replace(" ", "") in folded][:top]
    n = int(len(src_counts))
    pct = int((len(matched) * 100) // n) if n else 0
    back = sum(1 for v in tgt_values if v in set(src_counts.index))
    type_mismatch = pd.api.types.is_numeric_dtype(source) != pd.api.types.is_numeric_dtype(target)
    return {
        "source_values": n, "matched_values": int(len(matched)), "pct_values": pct,
        "target_values": int(len(tgt_values)),
        "pct_target_covered": int((back * 100) // len(tgt_values)) if tgt_values else 0,
        "unmatched": [{"value": str(v), "rows": int(c)} for v, c in unmatched.head(top).items()],
        "unmatched_count": int(len(unmatched)),
        "near_matches": near,
        "type_mismatch": (f"{source.name} is {'numeric' if pd.api.types.is_numeric_dtype(source) else 'text'}, "
                          f"{target.name} is {'numeric' if pd.api.types.is_numeric_dtype(target) else 'text'}")
                         if type_mismatch else None,
    }
