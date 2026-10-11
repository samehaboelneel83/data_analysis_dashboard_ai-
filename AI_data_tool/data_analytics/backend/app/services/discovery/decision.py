"""A decision that could be set up on this data -- recognised by its shape,
written down as a specification, never solved here
(docs/discovery/PLAN.md §D2, phase 5).

There is no solver on this platform, and none is added. This module does two
things only:

1. `recognise` reads the stored profile for the STRUCTURE of a decision --
   never offered because numbers exist:

   * **choose among options** (allocation): one row per option (a key that
     never repeats) with at least two amounts that add up -- one can be what
     is gained, another what is spent -- and no date: a dated row is an
     event, not an option;
   * **match two sets** (assignment): two columns whose pairs fill most of a
     grid (every one of A against every one of B) with a number per pair.

2. `specify` takes what the PERSON says -- which amount to make large or
   small, which one is limited and by how much -- checks it on the rows, and
   returns the problem as a neutral, versioned document a solver elsewhere
   can read. Nothing is inferred silently: a column's role in the decision is
   whatever the person chose for it.
"""
from __future__ import annotations

import pandas as pd

SCHEMA = "datalytics.decision-problem/1"
#: Fewer options than this is a choice a person makes by looking; more than
#: the upper bound is a table of events, not of options.
MIN_OPTIONS, MAX_OPTIONS = 5, 5000
#: Share of the A x B grid that must be present for "every A against every B".
GRID_FILL = 0.5
GRID_MIN_SIDE = 2
GRID_MAX_SIDE = 400
MAX_OFFERED = 3
#: Rows a dated table needs before "which levels make this number largest" is offered.
RESPONSE_MIN_ROWS = 60
#: Factors a response problem may set at once (the what-if model's own limit).
RESPONSE_MAX_FACTORS = 4


class DecisionProblemError(ValueError):
    """Unusable input. The router maps this to HTTP 400."""


def recognise(profile: dict, kinds: dict[str, set[str]]) -> list[dict]:
    """Candidates, strongest first: {"problem", "key"?, "amounts"?, "from"?, "to"?, "numbers"?}.
    Read from the stored profile; no row is read."""
    table, cols = profile.get("table") or {}, profile.get("columns") or {}
    rows = int(table.get("rows") or 0)
    if not rows:
        return []
    # A row that carries a date is something that HAPPENED; a decision is made
    # among things. Every table of events has a key and amounts too -- without
    # this, any small table of records would be offered a choice to set up.
    # What a dated table CAN have is the third shape: a number that moved over
    # time beside other numbers that moved with it -- levels to set.
    dates = [c for c, ks in kinds.items() if "date" in ks]
    if dates:
        got = lambda c: int((cols.get(c) or {}).get("count") or 0)               # noqa: E731
        outcomes = [c for c, ks in kinds.items() if "additive" in ks and got(c) >= 0.9 * rows]
        levers = [c for c, ks in kinds.items() if ks & {"additive", "level", "number"} and "key" not in ks
                  and "date" not in ks and got(c) >= 0.9 * rows]
        if rows >= RESPONSE_MIN_ROWS and outcomes and len(levers) >= 2:
            return [{"problem": "response", "date": dates[0], "dates": dates[:4], "measures": outcomes[:6],
                     "factors": levers[:8], "rows": rows}]
        return []
    distinct = lambda c: int((cols.get(c) or {}).get("distinct") or 0)           # noqa: E731
    filled = lambda c: int((cols.get(c) or {}).get("count") or 0)                # noqa: E731
    amounts = [c for c, ks in kinds.items() if "additive" in ks and filled(c) >= 0.9 * rows]
    numbers = [c for c, ks in kinds.items() if ks & {"additive", "level", "number"} and "key" not in ks
               and filled(c) >= 0.9 * rows]
    out: list[dict] = []
    # One row per option: a column that never repeats and is filled on every row.
    keys = [c for c, ks in kinds.items() if "date" not in ks and c not in numbers
            and distinct(c) == rows and filled(c) == rows]
    if keys and len(amounts) >= 2 and MIN_OPTIONS <= rows <= MAX_OPTIONS:
        out.append({"problem": "allocation", "key": keys[0], "amounts": amounts[:6], "options": rows})
    # Every A against every B: the pairs fill most of the grid, once each.
    sides = [c for c, ks in kinds.items() if ks & {"category", "key"} and "date" not in ks and c not in numbers
             and GRID_MIN_SIDE <= distinct(c) <= GRID_MAX_SIDE and filled(c) == rows]
    best = None
    for i, a in enumerate(sides):
        for b in sides[i + 1:]:
            grid = distinct(a) * distinct(b)
            if grid >= rows >= GRID_FILL * grid and min(distinct(a), distinct(b)) >= GRID_MIN_SIDE and rows > max(
                    distinct(a), distinct(b)):
                fill = rows / grid
                if best is None or fill > best[0]:
                    best = (fill, a, b)
    if best and numbers:
        out.append({"problem": "assignment", "from": best[1], "to": best[2], "numbers": numbers[:6],
                    "pairs": rows, "fill": round(best[0], 3)})
    return out[:MAX_OFFERED]


def _number(df: pd.DataFrame, col: str, what: str) -> pd.Series:
    if not col or col not in df.columns:
        raise DecisionProblemError(f"choose the column for {what}")
    s = pd.to_numeric(df[col], errors="coerce")
    if s.notna().sum() == 0:
        raise DecisionProblemError(f"'{col}' holds no numbers")
    return s


def _direction(value) -> str:
    v = str(value or "").strip().lower()
    if v in ("max", "maximize", "maximise", "largest", "highest"):
        return "maximize"
    if v in ("min", "minimize", "minimise", "smallest", "lowest"):
        return "minimize"
    raise DecisionProblemError("say whether the objective is to be made as large or as small as possible")


def specify(df: pd.DataFrame, problem: str, *, dataset: dict | None = None, **choices) -> dict:
    """The problem as a document: {"schema", "problem", "objective", "decisions",
    "constraints", "data", "checks"}. Raises when what was chosen cannot be a
    decision on these rows."""
    if problem == "allocation":
        spec = _allocation(df, **choices)
    elif problem == "assignment":
        spec = _assignment(df, **choices)
    elif problem == "response":
        spec = _response(df, **choices)
    else:
        raise DecisionProblemError("problem must be 'allocation', 'assignment' or 'response'")
    return {"schema": SCHEMA, "problem": problem, **spec,
            "dataset": dataset or {}, "solved": False,
            "note": "A specification only: nothing here has been optimised."}


def _only_volume(df: pd.DataFrame, factor: str, objective: str) -> bool:
    """The engine's own rule for withholding a what-if (evidence._scenarios):
    with enough rows to judge, the factor and the number barely move together
    row by row, so a fit on period totals is reading volume."""
    import numpy as np

    from .evidence import SCENARIO_TOGETHER
    x, y = pd.to_numeric(df[factor], errors="coerce"), pd.to_numeric(df[objective], errors="coerce")
    both = x.notna() & y.notna()
    if both.sum() < 30 or not x[both].std() or not y[both].std():
        return False
    together = float(np.corrcoef(x[both], y[both])[0, 1])
    return not np.isfinite(together) or abs(together) < SCENARIO_TOGETHER


def _response(df: pd.DataFrame, date_col: str = "", objective: str = "", direction: str = "",
              factors: list[str] | None = None, ranges: dict | None = None, granularity: str = "month",
              periods: int | None = None, **_ignored) -> dict:
    """Which LEVELS of some factors make a number largest (or smallest) over
    the next periods, under the model the what-if fits: a level, a trend and
    one straight-line effect per factor. Each factor may be set anywhere in a
    range -- the person's, or what was observed. The model and its doubts go
    into the document; the best levels are not worked out here."""
    import numpy as np

    from ..analysis import simulate_scenarios as sim
    from ..analysis.forecast_scenario import ForecastScenarioError, forecast_scenario
    way = _direction(direction)
    chosen = [f for f in dict.fromkeys(factors or []) if f]
    if not date_col or date_col not in df.columns:
        raise DecisionProblemError("choose the date column")
    _number(df, objective, "what is to be made large or small")
    if not chosen:
        raise DecisionProblemError("choose at least one factor whose level could be set")
    if len(chosen) > RESPONSE_MAX_FACTORS:
        raise DecisionProblemError(f"at most {RESPONSE_MAX_FACTORS} factors can be set at once")
    if objective in chosen:
        raise DecisionProblemError("the objective cannot also be a factor to set")
    for f in chosen:
        _number(df, f, f"the factor '{f}'")
    horizon = int(periods or sim.DEFAULT_HORIZON)
    try:
        # The what-if's own checks of columns and history, in its own words.
        single = forecast_scenario(df, date_col, objective, chosen, {chosen[0]: 0.1}, horizon, granularity)
    except ForecastScenarioError as e:
        raise DecisionProblemError(str(e)) from e
    grouped, fitted, recent, y, X = sim._fit(df, date_col, objective, chosen, granularity)
    params = [float(v) for v in fitted.params]
    pvalues = [float(v) for v in fitted.pvalues]
    checks: list[dict] = []
    decisions, constraints = [], []
    for i, f in enumerate(chosen):
        seen_lo, seen_hi = float(grouped[f].min()), float(grouped[f].max())
        asked = (ranges or {}).get(f) if isinstance(ranges, dict) else None
        lo, hi = seen_lo, seen_hi
        if isinstance(asked, (list, tuple)) and len(asked) == 2 and all(v is not None for v in asked):
            lo, hi = float(asked[0]), float(asked[1])
        if not hi > lo:
            raise DecisionProblemError(f"the range for '{f}' needs a highest level above its lowest")
        decisions.append({"name": f, "type": "level", "per": granularity, "recent": round(recent[f], 4),
                          "lower": round(lo, 4), "upper": round(hi, 4),
                          "observed": [round(seen_lo, 4), round(seen_hi, 4)]})
        constraints.append({"kind": "range", "column": f, "lower": round(lo, 4), "upper": round(hi, 4)})
        if lo < seen_lo or hi > seen_hi:
            # Outside anything seen: the model has no evidence there.
            checks.append({"code": "beyond_observed", "column": f, "observed": [round(seen_lo, 4), round(seen_hi, 4)]})
        if pvalues[2 + i] >= 0.05:
            # The data cannot tell which way this factor moves the number.
            checks.append({"code": "effect_unclear", "column": f, "p": round(pvalues[2 + i], 4)})
        elif _only_volume(df, f, objective):
            # Summed by period the two climb in step, yet row by row they do
            # not move together: busier periods simply hold more of both.
            checks.append({"code": "only_volume", "column": f})
    r2 = float(single.get("r2", fitted.rsquared))
    if r2 < sim.WEAK_FIT:
        checks.append({"code": "weak_model", "r2": round(r2, 4)})
    own = float(np.sqrt(max(float(fitted.scale), 0.0)))
    unseen = sim._unseen_miss(y, X)
    if unseen is not None and own > 0 and unseen > own * sim.WIDEN_FROM:
        checks.append({"code": "misses_unseen", "times": round(unseen / own, 2)})
    if sim._bends(y, X, fitted):
        checks.append({"code": "bends"})
    # A straight-line model is largest at an end of every range: what a solver
    # returns is only as good as the ranges it was given.
    checks.append({"code": "linear_optimum_at_bounds"})
    checks.append({"code": "association_not_intervention"})
    return {
        "objective": {"direction": way, "column": objective, "aggregate": "total_over_horizon",
                      "horizon": horizon, "per": granularity},
        "model": {"form": "linear", "intercept": round(params[0], 6), "per_period": round(params[1], 6),
                  "coefficients": {f: round(params[2 + i], 6) for i, f in enumerate(chosen)},
                  "r2": round(r2, 4), "periods_fitted": int(len(grouped)),
                  "next_period_index": int(len(grouped)),
                  "noise": {"own": round(own, 4), "unseen": round(unseen, 4) if unseen is not None else None}},
        "decisions": decisions,
        "constraints": constraints,
        "data": {"rows": int(len(df)), "columns": [date_col, objective, *chosen]},
        "checks": checks,
    }


def _allocation(df: pd.DataFrame, key: str = "", objective: str = "", direction: str = "", limited: str = "",
                limit: float | None = None, at_most: int | None = None, **_ignored) -> dict:
    if not key or key not in df.columns:
        raise DecisionProblemError("choose the column that names each option")
    if df[key].isna().any() or df[key].duplicated().any():
        raise DecisionProblemError(f"'{key}' repeats or is empty on some rows: each row must be one option")
    way = _direction(direction)
    gain = _number(df, objective, "what is to be made large or small")
    checks: list[dict] = []
    constraints: list[dict] = []
    if limited:
        if limited == objective:
            raise DecisionProblemError("the limited amount and the objective are the same column")
        cost = _number(df, limited, "what is limited")
        if limit is None or float(limit) <= 0:
            raise DecisionProblemError(f"give the most of '{limited}' that may be used, above zero")
        constraints.append({"kind": "total_at_most", "column": limited, "value": float(limit)})
        if (cost < 0).any():
            checks.append({"code": "negative_cost", "column": limited, "rows": int((cost < 0).sum())})
        if cost.isna().any():
            checks.append({"code": "missing", "column": limited, "rows": int(cost.isna().sum())})
        fits = int((cost <= float(limit)).sum())
        checks.append({"code": "fit_alone", "options": fits, "of": int(len(df))})
        if fits == 0:
            raise DecisionProblemError(f"no option fits within {float(limit):g} of '{limited}' by itself")
        if float(cost.clip(lower=0).sum()) <= float(limit):
            checks.append({"code": "limit_not_binding", "column": limited, "total": round(float(cost.sum()), 4)})
    if at_most not in (None, ""):
        if int(at_most) < 1:
            raise DecisionProblemError("the number of options that may be chosen must be at least 1")
        constraints.append({"kind": "count_at_most", "value": int(at_most)})
    if not constraints:
        raise DecisionProblemError("a choice needs a limit: an amount that may not be exceeded, or how many "
                                   "options may be chosen")
    if gain.isna().any():
        checks.append({"code": "missing", "column": objective, "rows": int(gain.isna().sum())})
    return {
        "objective": {"direction": way, "column": objective, "aggregate": "sum_over_chosen"},
        "decisions": {"unit": "row", "key": key, "type": "choose", "domain": [0, 1], "count": int(len(df))},
        "constraints": constraints,
        "data": {"rows": int(len(df)), "columns": [c for c in (key, objective, limited) if c]},
        "checks": checks,
    }


def _assignment(df: pd.DataFrame, from_col: str = "", to_col: str = "", objective: str = "", direction: str = "",
                each_from: str = "exactly_one", each_to_at_most: int | None = 1, **_ignored) -> dict:
    for col, what in ((from_col, "the first set"), (to_col, "the second set")):
        if not col or col not in df.columns:
            raise DecisionProblemError(f"choose the column for {what}")
    if from_col == to_col:
        raise DecisionProblemError("the two sets must be two different columns")
    way = _direction(direction)
    value = _number(df, objective, "the number carried by each pair")
    pairs = df[[from_col, to_col]]
    if pairs.isna().any().any():
        raise DecisionProblemError("some rows have no value in one of the two sets")
    if pairs.duplicated().any():
        raise DecisionProblemError(f"some pairs of '{from_col}' and '{to_col}' appear more than once: "
                                   "each pair must be one row")
    n_from, n_to = int(df[from_col].nunique()), int(df[to_col].nunique())
    if each_from not in ("exactly_one", "at_most_one"):
        raise DecisionProblemError("each of the first set is matched exactly once, or at most once")
    cap = int(each_to_at_most) if each_to_at_most not in (None, "") else None
    if cap is not None and cap < 1:
        raise DecisionProblemError("each of the second set must be able to take at least 1")
    checks: list[dict] = []
    missing = n_from * n_to - len(df)
    if missing:
        checks.append({"code": "pairs_missing", "pairs": int(missing), "of": int(n_from * n_to)})
    if value.isna().any():
        checks.append({"code": "missing", "column": objective, "rows": int(value.isna().sum())})
    if each_from == "exactly_one" and cap is not None and n_from > n_to * cap:
        raise DecisionProblemError(f"{n_from} of '{from_col}' cannot each be matched when {n_to} of '{to_col}' "
                                   f"take at most {cap} each")
    constraints = [{"kind": "each_from", "column": from_col, "rule": each_from}]
    if cap is not None:
        constraints.append({"kind": "each_to_at_most", "column": to_col, "value": cap})
    return {
        "objective": {"direction": way, "column": objective, "aggregate": "sum_over_chosen"},
        "decisions": {"unit": "row", "from": from_col, "to": to_col, "type": "choose", "domain": [0, 1],
                      "count": int(len(df)), "from_count": n_from, "to_count": n_to},
        "constraints": constraints,
        "data": {"rows": int(len(df)), "columns": [from_col, to_col, objective]},
        "checks": checks,
    }
