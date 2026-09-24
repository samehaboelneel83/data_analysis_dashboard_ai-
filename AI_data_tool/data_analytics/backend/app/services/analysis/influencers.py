"""Key influencers: which factors move a chosen outcome, and by how much.

The question this answers is "what drives churn?" -- asked constantly, and
normally answered by a data scientist with a notebook. Power BI's Key
Influencers visual is the closest analogue and the most-cited capability this
platform lacked.

**Why an auditable ratio and not a black box.** The output has to be read
by somebody who did not fit it, so every number here is one a person can check
against the data by hand: the group is a plain column-value rule, the lift is a
ratio of two rates, and the support is a row count. A gradient-boosted ensemble
would rank factors more accurately and explain nothing. Accuracy that cannot be
audited is the wrong trade for a self-serve BI feature -- a confidently wrong
"your top driver is X" is worse than no answer, because nobody can tell.

**What it will not claim.** Influence is not causation, and this module never
says it is. The wording in the result is deliberately "higher when" rather than
"causes": the analysis observes that a group's outcome rate differs from the
baseline, which is a fact about the data, not about the world.

**No ML dependency at all.** This started out reaching for a decision tree and
ended up not needing one: a group-vs-baseline lift is what the reader actually
wants explained, and pandas computes it exactly. So unlike `segment.py` and
`anomaly.py` there is nothing heavy to import lazily here -- the module costs
nothing to import and adds no package to the air-gapped image.
"""
from __future__ import annotations

import pandas as pd

from ..analysis_contract import AnalysisContract

RANDOM_STATE = 42

#: Fitting over an unbounded import frame would turn one request into a long
#: CPU burn on a shared worker. A seeded sample keeps it bounded and
#: reproducible, and `meta.sampled` says when it happened rather than quietly
#: analysing a subset.
FRAME_SAMPLE_THRESHOLD = 50_000

#: Below this there is not enough signal for a split to mean anything; saying
#: so beats returning noise with a confident-looking lift.
MIN_ROWS = 30

#: A factor supported by a handful of rows is an anecdote. Groups thinner than
#: this share of the data are dropped before ranking, so a 3-row group with a
#: 12x lift cannot top the list.
MIN_GROUP_FRACTION = 0.02
MIN_GROUP_ROWS = 10

#: How many influencers to return. More than this is a data-mining expedition,
#: not an explanation.
TOP_N = 6

#: A high-cardinality text column (an id, an email) has one row per value and
#: would produce a perfect, meaningless split. Columns above this many distinct
#: values are skipped, with a warning naming them.
MAX_CATEGORICAL_LEVELS = 50

#: Continuous factors are cut into quantile bins so a "group" stays a rule a
#: person can read ("tenure in the lowest quarter") rather than a threshold to
#: four decimal places.
NUMERIC_BINS = 4


class InfluencerError(ValueError):
    """Input that cannot support the analysis (too few rows, no usable
    factors, a target that never varies). The router maps this to HTTP 400."""


def _usable_factors(df: pd.DataFrame, target: str, factors: list[str] | None,
                    column_meta: dict | None = None) -> tuple[list[str], list[str]]:
    """The columns worth splitting on, and the reasons others were dropped.

    IDENTIFIERS ARE EXCLUDED BEFORE THE NUMERIC/CATEGORICAL SPLIT
    -------------------------------------------------------------
    The categorical branch below has always dropped high-cardinality columns
    as "too many to group". The numeric branch never did -- so `student_id`,
    numeric and near-unique, went straight through and `_grouped` cut it into
    quantile bins. The result ranked an identifier as a top driver and
    described it in "ranges", which is row order wearing the clothes of a
    finding. On a real dataset that was four of six rows.

    The check has to run BEFORE the dtype split, because the bug is that the
    numeric path never reached a check at all.

    `classify_role` is the canonical heuristic (name pattern OR near-unique),
    not a fifth local copy -- the other three are widget_data's name-only
    check, columnRole.ts's frontend mirror, and the cardinality rule below.
    An AUTHORED role in `column_meta` outranks it, because a human who called
    a column a measure has already answered the question.
    """
    from ...services.metadata.infer_semantic import classify_role

    meta = column_meta or {}
    candidates = [c for c in (factors or df.columns) if c != target and c in df.columns]
    keep: list[str] = []
    warnings: list[str] = []
    row_count = int(len(df))
    for c in candidates:
        col = df[c]
        if col.isna().all():
            warnings.append(f"'{c}' skipped: no values")
            continue

        authored = (meta.get(c) or {}) if isinstance(meta.get(c), dict) else {}
        role = authored.get("role") or classify_role(
            c, str(col.dtype),
            {"distinct_count": int(col.nunique(dropna=True)), "row_count": row_count})
        if role == "identifier":
            warnings.append(
                f"'{c}' skipped: it identifies rows rather than describing them")
            continue

        if pd.api.types.is_numeric_dtype(col):
            if col.nunique(dropna=True) < 2:
                warnings.append(f"'{c}' skipped: only one value")
                continue
            keep.append(c)
            continue
        levels = col.nunique(dropna=True)
        if levels < 2:
            warnings.append(f"'{c}' skipped: only one value")
        elif levels > MAX_CATEGORICAL_LEVELS:
            # Almost always an identifier. A split on it would be perfect and
            # tell the reader nothing they can act on.
            warnings.append(
                f"'{c}' skipped: {levels} distinct values, too many to group")
        else:
            keep.append(c)
    return keep, warnings


def _grouped(series: pd.Series) -> tuple[pd.Series, str]:
    """A factor as readable groups, plus how it was grouped.

    Numeric columns become quantile bins so the result reads as a rule rather
    than a decimal threshold. `duplicates="drop"` handles a skewed column whose
    quartile edges collide -- fewer bins is correct there, not an error.
    """
    if pd.api.types.is_numeric_dtype(series):
        try:
            binned = pd.qcut(series, NUMERIC_BINS, duplicates="drop")
        except (ValueError, IndexError):
            return series.astype("object"), "value"
        return binned.astype("object"), "quantile"
    return series.astype("object"), "value"


def key_influencers(
    df: pd.DataFrame, target: str, target_value=None,
    factors: list[str] | None = None, column_meta: dict | None = None,
) -> AnalysisContract:
    """Rank the factors whose groups shift `target` furthest from its baseline.

    For a categorical target, `target_value` picks the outcome of interest
    (defaulting to the rarest level -- the interesting one is nearly always
    churn/fraud/failure rather than the majority class). For a numeric target
    the analysis compares group means instead of rates.
    """
    if target not in df.columns:
        raise InfluencerError(f"column '{target}' is not in this dataset")

    total_rows = len(df)
    sampled = total_rows > FRAME_SAMPLE_THRESHOLD
    if sampled:
        df = df.sample(n=FRAME_SAMPLE_THRESHOLD, random_state=RANDOM_STATE)

    df = df[df[target].notna()]
    if len(df) < MIN_ROWS:
        raise InfluencerError(
            f"need at least {MIN_ROWS} rows with a value for '{target}' "
            f"to find influencers; this has {len(df)}")

    numeric_target = pd.api.types.is_numeric_dtype(df[target]) and df[target].nunique() > 2
    if numeric_target:
        outcome = pd.to_numeric(df[target], errors="coerce")
        baseline = float(outcome.mean())
        measure, chosen = "mean", None
    else:
        levels = df[target].value_counts()
        if len(levels) < 2:
            raise InfluencerError(
                f"'{target}' has only one value, so nothing distinguishes its rows")
        # The rarest level by default: "what drives churn" is asked far more
        # often than "what drives staying", and the minority class is the one
        # a lift is informative about.
        chosen = target_value if target_value is not None else levels.index[-1]
        if chosen not in set(levels.index):
            raise InfluencerError(f"'{chosen}' is not a value of '{target}'")
        outcome = (df[target] == chosen).astype(float)
        baseline = float(outcome.mean())
        measure = "rate"

    usable, warnings = _usable_factors(df, target, factors, column_meta)
    if not usable:
        raise InfluencerError(
            "no usable factors: every other column is constant, empty, or has "
            "too many distinct values to group")

    min_rows = max(MIN_GROUP_ROWS, int(len(df) * MIN_GROUP_FRACTION))
    found: list[dict] = []
    for col in usable:
        groups, how = _grouped(df[col])
        stats = outcome.groupby(groups, dropna=True).agg(["mean", "count"])
        stats = stats[stats["count"] >= min_rows]
        if stats.empty:
            continue
        for value, row in stats.iterrows():
            rate = float(row["mean"])
            # Lift against the baseline, which is what makes two factors on
            # different scales comparable at all.
            if baseline == 0:
                continue
            found.append({
                "factor": col,
                "group": str(value),
                "grouped_by": how,
                measure: round(rate, 6),
                "baseline": round(baseline, 6),
                "lift": round(rate / baseline, 4),
                "rows": int(row["count"]),
                "share_of_rows": round(float(row["count"]) / len(df), 4),
            })

    if not found:
        raise InfluencerError(
            f"no group large enough to be meaningful (each needs at least "
            f"{min_rows} rows)")

    # Rank by distance from the baseline in either direction: a factor that
    # HALVES the outcome is exactly as informative as one that doubles it, and
    # ranking on the raw rate would bury it.
    found.sort(key=lambda r: abs(r["lift"] - 1.0), reverse=True)
    top = found[:TOP_N]

    return AnalysisContract(
        kind="key_influencers",
        columns=[{"name": c, "dtype": str(df[c].dtype)} for c in usable],
        rows=top,
        meta={
            "method": "group lift against baseline",
            "target": target,
            "target_value": None if chosen is None else str(chosen),
            "measure": measure,
            "baseline": round(baseline, 6),
            "params": {
                "factors": usable,
                "min_group_rows": min_rows,
                "top_n": TOP_N,
                "numeric_bins": NUMERIC_BINS,
                "random_state": RANDOM_STATE,
            },
            "n_rows_used": int(len(df)),
            "n_rows_total": int(total_rows),
            "sampled": sampled,
            "groups_considered": len(found),
            # Said plainly, in the payload, because a UI that renders "top
            # driver" without it invites exactly the wrong reading.
            "caveat": "These factors move with the outcome; that is not proof "
                       "they cause it.",
        },
        warnings=warnings + (
            [f"analysed a {FRAME_SAMPLE_THRESHOLD:,}-row sample of "
             f"{total_rows:,} rows"] if sampled else []),
    )
