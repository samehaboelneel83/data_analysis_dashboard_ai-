"""Two groups, one outcome: how each did, how far apart they are, and how sure
that is (docs/discovery/PLAN.md §N-4).

The reading of an experiment -- or of any table that marks its rows as
belonging to one of two groups: the rate (or the average) in each, the
difference with its likely range, the lift of one over the other, the chance
the second really is higher, and one plain verdict.

What it cannot know is whether the rows were PUT in their groups at random.
If they were, the difference is the effect of the group. If they were not, it
is a difference between two kinds of rows, and says so every time.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from ..analysis_contract import AnalysisContract
from ..readback import _s, as_i18n

#: Rows a group needs before its rate is worth setting beside another's.
MIN_GROUP_ROWS = 30
#: The range reported for the difference.
LEVEL = 0.95
#: Above this chance of being higher (or below one minus it) the verdict names
#: a side; between, it is "not clear yet".
SURE = 0.95
#: Draws for the chance one group is higher; seeded, so the same data gives
#: the same answer.
DRAWS = 20_000
SEED = 20261011
#: Points of each group's curve (what its true rate or average probably is).
CURVE_POINTS = 61


class TwoGroupsError(ValueError):
    """Unusable input. The router maps this to HTTP 400."""


def _curve(center: float, spread: float, lo: float | None = None, hi: float | None = None) -> list[list[float]]:
    if not spread or not math.isfinite(spread):
        return []
    xs = np.linspace(center - 4 * spread, center + 4 * spread, CURVE_POINTS)
    if lo is not None:
        xs = xs[xs >= lo]
    if hi is not None:
        xs = xs[xs <= hi]
    ys = np.exp(-0.5 * ((xs - center) / spread) ** 2)
    return [[round(float(x), 6), round(float(y), 4)] for x, y in zip(xs, ys)]


def compare_two_groups(df: pd.DataFrame, group_col: str, outcome: str, outcome_value=None,
                       baseline=None, column_meta: dict | None = None) -> AnalysisContract:
    """`group_col` marks the two groups; `outcome` is what is compared.

    An outcome with two values (or with `outcome_value` named) is compared as
    a RATE -- the share of each group's rows that hold that value (default:
    the rarer one). A number with more values is compared as an AVERAGE.
    `baseline` names the group the other is set against (default: the larger)."""
    from scipy import stats

    for col in (group_col, outcome):
        if col not in df.columns:
            raise TwoGroupsError(_s("no.change_drivers.1", "column '{a}' is not in this dataset", cap=False, a=col))
    if group_col == outcome:
        raise TwoGroupsError(_s("no.two_groups.1", "the groups and the outcome are the same column", cap=False))
    frame = df[df[group_col].notna() & df[outcome].notna()]
    sizes = frame[group_col].astype(str).value_counts()
    if len(sizes) != 2:
        raise TwoGroupsError(
            _s("no.two_groups.2", "'{a}' has {b} values; this reading sets exactly two groups side by side. Filter to two of them, or compare all the groups instead.", cap=False, a=group_col, b=len(sizes)))
    names = list(sizes.index)
    base = str(baseline) if baseline is not None else names[0]
    if base not in names:
        raise TwoGroupsError(_s("no.influencers.3", "'{a}' is not a value of '{b}'", cap=False, a=baseline, b=group_col))
    other = next(n for n in names if n != base)
    small = [n for n in names if sizes[n] < MIN_GROUP_ROWS]
    if small:
        raise TwoGroupsError(_s("no.two_groups.3", "group '{a}' has {b} rows; each needs at least {c}", cap=False, a=small[0], b=int(sizes[small[0]]), c=MIN_GROUP_ROWS))

    key = frame[group_col].astype(str)
    levels = frame[outcome].nunique()
    numeric = pd.api.types.is_numeric_dtype(frame[outcome]) and not pd.api.types.is_bool_dtype(frame[outcome])
    as_rate = outcome_value is not None or levels == 2 or not numeric
    rng = np.random.default_rng(SEED)
    z = float(stats.norm.ppf(0.5 + LEVEL / 2))
    caveats: list[str] = []

    if as_rate:
        counts = frame[outcome].astype(str).value_counts()
        chosen = str(outcome_value) if outcome_value is not None else str(counts.index[-1])
        if chosen not in set(counts.index):
            raise TwoGroupsError(_s("no.influencers.3", "'{a}' is not a value of '{b}'", cap=False, a=outcome_value, b=outcome))
        if levels > 2 and outcome_value is None:
            caveats.append(_s("an.rarest", "'{col}' has {n} values; the rarest ('{v}') is the one counted.",
                              col=outcome, n=levels, v=chosen))
        hit = (frame[outcome].astype(str) == chosen)
        n = {g: int((key == g).sum()) for g in names}
        k = {g: int(hit[key == g].sum()) for g in names}
        est = {g: k[g] / n[g] for g in names}
        diff = est[other] - est[base]
        se = math.sqrt(est[base] * (1 - est[base]) / n[base] + est[other] * (1 - est[other]) / n[other])
        # Two-sided test of equal rates (pooled), the textbook one.
        pooled = (k[base] + k[other]) / (n[base] + n[other])
        se0 = math.sqrt(pooled * (1 - pooled) * (1 / n[base] + 1 / n[other]))
        p_value = float(2 * stats.norm.sf(abs(diff) / se0)) if se0 else 1.0
        # What each group's true rate probably is, having seen these rows and
        # nothing else (a flat starting belief): the chance the other's is higher.
        draws = {g: rng.beta(k[g] + 1, n[g] - k[g] + 1, DRAWS) for g in names}
        curves = {g: _curve(est[g], math.sqrt(est[g] * (1 - est[g]) / n[g]), 0.0, 1.0) for g in names}
        measure, detail = "rate", {g: {"rows": n[g], "with_outcome": k[g]} for g in names}
        if min(k[base], k[other], n[base] - k[base], n[other] - k[other]) < 5:
            caveats.append(_s("an.few5", "One of the groups has fewer than 5 rows on one side of the outcome: the range is rough."))
    else:
        vals = {g: pd.to_numeric(frame.loc[key == g, outcome], errors="coerce").dropna().to_numpy(dtype=float) for g in names}
        n = {g: int(len(vals[g])) for g in names}
        est = {g: float(vals[g].mean()) for g in names}
        var = {g: float(vals[g].var(ddof=1)) for g in names}
        diff = est[other] - est[base]
        se = math.sqrt(var[base] / n[base] + var[other] / n[other])
        p_value = float(stats.ttest_ind(vals[other], vals[base], equal_var=False).pvalue) if se else 1.0
        draws = {g: rng.normal(est[g], math.sqrt(var[g] / n[g]), DRAWS) for g in names}
        curves = {g: _curve(est[g], math.sqrt(var[g] / n[g])) for g in names}
        measure, chosen = "mean", None
        detail = {g: {"rows": n[g], "spread": round(math.sqrt(var[g]), 6)} for g in names}

    chance_higher = float((draws[other] > draws[base]).mean())
    lo, hi = diff - z * se, diff + z * se
    lift = (diff / abs(est[base]) * 100) if est[base] else None
    verdict = ("higher" if chance_higher >= SURE else "lower" if chance_higher <= 1 - SURE else "not_clear")
    sentence = _s(f"an.tg.{verdict}", {
        "higher": "{other} is higher than {base}, and the rows seen leave little room for the opposite.",
        "lower": "{other} is lower than {base}, and the rows seen leave little room for the opposite.",
        "not_clear": "Not clear yet: on these rows {other} could be higher or lower than {base}.",
    }[verdict], cap=False, other=other, base=base)      # a group's name is shown as it is stored
    caveats.insert(0, _s("an.random", "If rows were not put in their groups at random, this is a difference between two "
                                      "kinds of rows, not the effect of the group."))
    return AnalysisContract(
        kind="two_groups",
        columns=[{"name": "group", "type": "text"}, {"name": measure, "type": "number"}, {"name": "rows", "type": "number"}],
        rows=[{"group": g, measure: round(est[g], 6), "rows": n[g], "baseline": g == base, **detail[g]} for g in (base, other)],
        meta={"group_col": group_col, "outcome": outcome, "outcome_value": chosen, "measure": measure,
              "baseline": base, "other": other,
              "difference": round(diff, 6), "low": round(lo, 6), "high": round(hi, 6), "level": LEVEL,
              "lift_pct": None if lift is None else round(lift, 2),
              "chance_higher": round(chance_higher, 4), "p_value": round(p_value, 6),
              "verdict": verdict, "sentence": str(sentence), "sentence_i18n": as_i18n(sentence),
              "warnings_i18n": [as_i18n(c) for c in caveats],
              "curves": {g: curves[g] for g in (base, other)},
              "rows_used": int(len(frame)), "rows_left_out": int(len(df) - len(frame))},
        warnings=[str(c) for c in caveats])
