"""Ingestion — reading a file into a frame, and typing its columns.

Layer 2. Split out of `analytics.py`, which had grown two unrelated
responsibilities: reading/typing a dataset (here) and computing statistics over
one (still there). Nearly every caller of the old module wanted only this half —
routers, `widget_data`, `prep`, `dataset_refresh`, `demo_content`, the agent —
and importing it dragged scipy and the whole descriptive-stats surface along.

The split also unwinds a real cycle. `frame_cache.py` needed `SUPPORTED` and had
to import it *inside a function body*, with the comment "local import; analytics
imports us", because `analytics.load_file` calls `frame_cache.get_frame`. With
the two halves separated, `frame_cache` (layer 3) imports `ingest` (layer 2)
normally and only `load_file` reaches upward — see `KNOWN_VIOLATIONS` in
tests/test_layer_conformance.py.

Nothing here computes a statistic. Nothing here imports scipy.
"""
from pathlib import Path  # noqa: F401  (kept: SUPPORTED consumers type-check paths)

import numpy as np  # noqa: F401  (re-exported for callers that did `from analytics import np`)
import pandas as pd


SUPPORTED = {".csv": pd.read_csv, ".xlsx": pd.read_excel,
             ".xls": pd.read_excel, ".json": pd.read_json}
try:
    SUPPORTED[".parquet"] = pd.read_parquet
except Exception:
    pass
try:
    # F1: lxml is in requirements.txt (already pulled in for other XML work);
    # pd.read_xml uses it as its parser automatically when present. If a
    # deployment image lacks it, .xml simply doesn't appear as a supported
    # extension rather than registering a reader that fails on first use.
    import lxml.etree  # noqa: F401
    SUPPORTED[".xml"] = pd.read_xml
except Exception:
    pass


def load_file(path: str) -> pd.DataFrame:
    # Routed through the process-local frame memo: same bytes, parsed once per
    # process instead of once per widget. Every caller gets a private deep
    # copy, so in-place mutation (detect_types below does it) stays safe.
    from .frame_cache import get_frame
    return get_frame(path)


#: The window an integer must land in to be read as a Unix epoch: 2000-01-01 to
#: 2040-01-01. Deliberately tighter than "any plausible date". The window's job is
#: to separate a timestamp from the other long digit runs a database holds --
#: national IDs, order numbers, amounts in cents -- and those cluster outside it.
#: A false positive here invents a date and shows it as fact; a false negative
#: leaves the column numeric, which is exactly the behaviour that existed before.
#: So the window errs narrow, and a pre-2000 archive stays a number.
_EPOCH_S_MIN = 946684800     # 2000-01-01
_EPOCH_S_MAX = 2208988800    # 2040-01-01

#: Column names that read as an instant in time. Required by `detect_types` on top
#: of the range check, because the range alone cannot tell 1_500_000_000 cents
#: from 1_500_000_000 seconds.
#:
#: Matched as SUBSTRINGS, because the convention this exists for glues the words
#: together -- Moodle writes `startdate`, `timecreated`, `lastaccess`, and no
#: token split recovers those. Substring matching is why the list must be chosen
#: carefully: an earlier version included "start", "end", "due" and "finish", and
#: "end" made `sentiment` a date. The full suite caught it; none of the unit tests
#: did, because every name I thought to test was one I had written the rule for.
#:
#: Nothing was lost by dropping those four. `startdate` and `enddate` match on
#: "date"; `timestart` and `timefinish` match on "time". A column named bare
#: `start` holding an epoch stays numeric, which is the behaviour that existed
#: before this function -- the safe direction to fail in.
_TIME_NAME_HINTS = (
    "time", "date", "_at", "stamp", "created", "modified", "updated",
    "expire", "access", "login", "logout", "seen",
)


def epoch_unit(s: pd.Series) -> str | None:
    """`"s"`, `"ms"`, or None — the unit this integer column is a Unix epoch in.

    One function so the three places that care (type detection, PII
    classification, the prep `retype` step) cannot drift into disagreeing about
    what an epoch looks like. Values must be whole numbers and *every* one of
    them must land inside the window: a single stray value outside it means the
    column is something else that happens to overlap.
    """
    if not pd.api.types.is_numeric_dtype(s) or pd.api.types.is_bool_dtype(s):
        return None
    v = s.dropna()
    if v.empty:
        return None
    try:
        if not bool((v % 1 == 0).all()):
            return None
        lo, hi = float(v.min()), float(v.max())
    except (TypeError, ValueError):
        return None
    if _EPOCH_S_MIN <= lo and hi <= _EPOCH_S_MAX:
        return "s"
    if _EPOCH_S_MIN * 1000 <= lo and hi <= _EPOCH_S_MAX * 1000:
        return "ms"
    return None


def looks_like_time_column(name: object) -> bool:
    """Does this column's NAME read as an instant in time?

    The hint must sit at the START or the END of the name, or be a whole
    underscore-delimited word inside it. A bare substring match is not enough:
    `sentiment` contains "time" (sen-TIME-nt), and that one collision was enough
    to turn a demo measure into a date column and break three tests.

    Anchoring keeps every name this exists for -- `timecreated` and `timestamp`
    start with the hint, `startdate` and `lastaccess` end with one, `created_at`
    ends with "_at" -- while `sentiment`, `trend` and `attendance` match nothing.
    """
    n = str(name).lower()
    return any(n.startswith(h) or n.endswith(h) or f"_{h}_" in n
               for h in _TIME_NAME_HINTS)


def detect_types(df: pd.DataFrame) -> dict[str, str]:
    type_map = {}
    for col in df.columns:
        s = df[col]
        if pd.api.types.is_numeric_dtype(s):
            # An integer column named for a time, whose values all sit in the
            # epoch window, is a date stored as a number -- the Moodle/WordPress/
            # log-table convention. Converting it here is what puts it under Dates
            # in the report builder instead of Measures; leaving it numeric is how
            # a "courses per month" chart ends up plotting 1771106400 on its axis.
            unit = epoch_unit(s) if looks_like_time_column(col) else None
            if unit:
                df[col] = pd.to_datetime(s, unit=unit, errors="coerce")
                type_map[col] = "datetime"
                continue
            type_map[col] = "numeric"
        elif pd.api.types.is_datetime64_any_dtype(s):
            type_map[col] = "datetime"
        else:
            try:
                parsed = pd.to_datetime(s, infer_datetime_format=True)
                if parsed.notna().sum() / max(len(s), 1) > 0.8:
                    df[col] = parsed
                    type_map[col] = "datetime"
                    continue
            except Exception:
                pass
            try:
                nunique = s.nunique()
            except TypeError:
                # Unhashable cell values (dict/list) -- e.g. a jsonb or array column
                # coming back from a live database connection. There's no
                # categorical/distinct-count notion for structured values, so
                # fall back to "text" rather than letting nunique() crash the
                # whole type-detection pass over one column.
                type_map[col] = "text"
                continue
            ratio = nunique / max(len(s.dropna()), 1)
            type_map[col] = "categorical" if (ratio < 0.5 or nunique <= 30) else "text"
    return type_map


def missing_pct(series: pd.Series) -> float:
    """How much of a column is empty, as a percentage — never NaN.

    `series.isnull().mean()` is NaN on an empty frame, and NaN is not valid JSON.
    Six call sites computed this inline, so one dataset built from a query that
    returned no rows made `GET /api/v1/datasets` raise

        ValueError: Out of range float values are not JSON compliant: nan

    and 500 for the whole organisation — the Datasets page and the Ask AI scope
    picker both blank, with nothing to say which row was at fault. An empty query
    is an ordinary thing to write; it must produce an empty dataset, not a broken
    tenant. No rows means nothing is missing, so the honest answer is 0.
    """
    if len(series) == 0:
        return 0.0
    value = float(series.isnull().mean() * 100)
    return 0.0 if value != value else round(value, 2)      # NaN != NaN


def duplicate_columns(names) -> list[str]:
    """Column names that appear more than once, in the order they first appeared.

    SQL is happy to return two columns called `unit` — a lab result's unit of
    measure and a department's unit are different things that share a word.
    pandas is not: `df["unit"]` stops being a Series and becomes a DataFrame, and
    the first truth test on it raises "The truth value of a Series is ambiguous",
    which is what reached the user as a 400 when this was found.

    Compared case-insensitively, because SQLite resolves `Unit` and `unit` to the
    same key and the collision is the same one wearing a hat.
    """
    seen, dupes = set(), []
    for name in names:
        key = str(name).strip().lower()
        if key in seen:
            if key not in dupes:
                dupes.append(key)
        else:
            seen.add(key)
    return dupes
