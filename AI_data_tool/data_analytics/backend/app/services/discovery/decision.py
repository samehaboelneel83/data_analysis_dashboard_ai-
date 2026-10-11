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
    if any("date" in ks for ks in kinds.values()):
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
    else:
        raise DecisionProblemError("problem must be 'allocation' or 'assignment'")
    return {"schema": SCHEMA, "problem": problem, **spec,
            "dataset": dataset or {}, "solved": False,
            "note": "A specification only: nothing here has been optimised."}


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
