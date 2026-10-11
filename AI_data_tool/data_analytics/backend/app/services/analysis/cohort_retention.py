"""Who comes back: rows grouped by when their entity was first seen, and how
many of each group are seen again in each later period
(docs/discovery/PLAN.md §D-19, phase 5).

For a table where the same entity appears on many rows over time -- an
identifier that repeats, and a date. Everything is read from those two
columns:

  * an entity's COHORT is the period of its first row;
  * it is ACTIVE in a later period when it has at least one row in it;
  * RETENTION is the share of a cohort active k periods after its first.

The newest periods are incomplete for the youngest cohorts by construction:
a cohort that began two periods ago has no fourth period yet. Those cells
are left empty, never shown as zero.
"""
from __future__ import annotations

import pandas as pd

from ..analysis_contract import AnalysisContract
from ..readback import _s, as_i18n

#: Entities below this, and "who comes back" is a handful of names.
MIN_ENTITIES = 30
#: A cohort smaller than this is shown but flagged: one entity is several points.
SMALL_COHORT = 20
MAX_COHORTS = 24
MAX_PERIODS = 12
_FREQ = {"day": "D", "week": "W", "month": "M", "quarter": "Q", "year": "Y"}


class CohortRetentionError(ValueError):
    """Unusable input. The router maps this to HTTP 400."""


def cohort_retention(df: pd.DataFrame, entity: str, date_column: str, granularity: str = "month",
                     periods: int = MAX_PERIODS, column_meta: dict | None = None) -> AnalysisContract:
    for col in (entity, date_column):
        if col not in df.columns:
            raise CohortRetentionError(f"column '{col}' is not in this dataset")
    if granularity not in _FREQ:
        raise CohortRetentionError(f"granularity must be one of {', '.join(_FREQ)}")
    periods = max(1, min(int(periods or MAX_PERIODS), MAX_PERIODS))
    when = pd.to_datetime(df[date_column], errors="coerce")
    frame = pd.DataFrame({"e": df[entity], "p": when.dt.to_period(_FREQ[granularity])}).dropna()
    left_out = int(len(df) - len(frame))
    if frame.empty:
        raise CohortRetentionError(f"{date_column} holds no dates")
    entities = int(frame["e"].nunique())
    if entities < MIN_ENTITIES:
        raise CohortRetentionError(f"'{entity}' has {entities} different values; at least {MIN_ENTITIES} are needed "
                                   "to say who comes back")
    if len(frame) == entities:
        raise CohortRetentionError(f"every '{entity}' appears on one row only: nothing comes back")

    pairs = frame.drop_duplicates()
    first = pairs.groupby("e")["p"].min().rename("cohort")
    pairs = pairs.join(first, on="e")
    pairs["k"] = (pairs["p"].astype("int64") - pairs["cohort"].astype("int64")).astype(int)   # periods since the first
    last = pairs["p"].max()
    sizes = first.value_counts().sort_index()
    cohorts = list(sizes.index)[-MAX_COHORTS:]
    dropped_cohorts = len(sizes) - len(cohorts)
    counts = pairs[pairs["k"] <= periods].groupby(["cohort", "k"])["e"].nunique()

    rows, small = [], 0
    for c in cohorts:
        size = int(sizes[c])
        reachable = int(last.ordinal - c.ordinal)          # periods this cohort has lived through
        row = {"cohort": str(c), "size": size}
        for k in range(1, periods + 1):
            row[f"p{k}"] = (round(100.0 * int(counts.get((c, k), 0)) / size, 1) if k <= reachable else None)
        small += size < SMALL_COHORT
        rows.append(row)

    # The typical curve: each period's retention over the cohorts that reached it, weighted by size.
    curve = []
    for k in range(1, periods + 1):
        reached = [c for c in cohorts if last.ordinal - c.ordinal >= k]
        base = sum(int(sizes[c]) for c in reached)
        kept = sum(int(counts.get((c, k), 0)) for c in reached)
        curve.append({"period": k, "retention": round(100.0 * kept / base, 1) if base else None,
                      "cohorts": len(reached), "entities": base})
    known = [p for p in curve if p["retention"] is not None]
    if not known:
        raise CohortRetentionError("the data covers one period only: there is no later period to come back in")
    first_back = known[0]["retention"]
    settled = known[-1]
    once = int((pairs.groupby("e")["p"].nunique() == 1).sum())

    caveats = [_s("co.active", "\"Came back\" means at least one row in that {g}; how much they did is not counted.",
                  g=granularity),
               _s("co.unfinished", "The newest cohorts have not lived through the later periods yet: those cells "
                                   "are empty, not zero.")]
    if small:
        caveats.append(_s("co.small", "{n} cohorts have fewer than {m} members: one of them is several points.",
                          n=small, m=SMALL_COHORT))
    if dropped_cohorts:
        caveats.append(_s("co.older", "Only the newest {n} cohorts are shown; {d} older ones are left out.",
                          n=len(cohorts), d=dropped_cohorts))
    if left_out:
        caveats.append(_s("co.nodate", "{n} rows have no {d} or no {e} and are not counted.",
                          n=f"{left_out:,}", d=date_column, e=entity))
    headline = _s("co.headline", "{first}% are seen again in the {g} after their first; {last}% are still seen "
                                 "{k} {g}s on. {once} of {n} appear in one {g} only.",
                  first=first_back, last=settled["retention"], k=settled["period"], g=granularity,
                  once=f"{once:,}", n=f"{entities:,}")
    meta = {"entity": entity, "date_column": date_column, "granularity": granularity, "periods": periods,
            "entities": entities, "once_only": once, "cohorts": len(cohorts), "curve": curve,
            "first_back": first_back, "settled": settled["retention"], "settled_period": settled["period"],
            "from": str(cohorts[0]), "to": str(last), "headline": str(headline), "headline_i18n": as_i18n(headline),
            "warnings_i18n": [as_i18n(c) for c in caveats]}
    columns = [{"name": "cohort", "type": "string"}, {"name": "size", "type": "number"},
               *[{"name": f"p{k}", "type": "number"} for k in range(1, periods + 1)]]
    return AnalysisContract(kind="cohort_retention", columns=columns, rows=rows, meta=meta,
                            warnings=[str(c) for c in caveats])
