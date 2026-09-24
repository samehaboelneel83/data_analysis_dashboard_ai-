"""Solve for the factor value a target requires.

This lived inside `routers/datasets.py::goal_seek`, its arithmetic interleaved
with `HTTPException`, `Depends` and the secured-frame loader. Nothing but HTTP
could call it: not the analysis registry, not the statistics panel, not the
agent. The maths moves here unchanged; the router keeps the security path and
translates these errors into status codes.

`GoalSeekError` subclasses `ValueError` so a caller that does not know this
module still catches its refusals -- and so no service layer raises HTTP.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


class GoalSeekError(ValueError):
    """A refusal the caller can act on: bad columns, or a fit that cannot solve."""


def goal_seek(df: pd.DataFrame, x_column: str, y_column: str, target_y: float,
              x_min: float | None = None, x_max: float | None = None) -> dict:
    """Solve for the x a target y requires, on a linear fit of y ~ x.

    The answer carries the fit's r² and whether the required x sits inside the
    observed range -- a goal outside the data is an extrapolation, and the
    caller deserves to know rather than receive a confident number.

    Optional per-factor bounds (SAS's goal-seek constraint): when x_min/x_max
    are given and the required x falls outside them, the solve reports
    infeasibility honestly -- plus the BEST ACHIEVABLE y at the binding bound,
    which is the number a bounded solver actually optimises to.
    """
    for col in (x_column, y_column):
        if col not in df.columns:
            raise GoalSeekError(f"Column '{col}' not found")

    pair = pd.DataFrame({
        "x": pd.to_numeric(df[x_column], errors="coerce"),
        "y": pd.to_numeric(df[y_column], errors="coerce"),
    }).dropna()
    if len(pair) < 3 or pair["x"].nunique() < 2:
        raise GoalSeekError("Not enough varying numeric data to fit y ~ x")

    slope, intercept = np.polyfit(pair["x"], pair["y"], 1)
    if abs(slope) < 1e-12:
        raise GoalSeekError(
            f"'{y_column}' does not move with '{x_column}' (flat fit)")

    pred = slope * pair["x"] + intercept
    ss_res = float(((pair["y"] - pred) ** 2).sum())
    ss_tot = float(((pair["y"] - pair["y"].mean()) ** 2).sum())
    required = (target_y - intercept) / slope
    out = {
        "required_x": round(float(required), 6),
        "slope": round(float(slope), 6),
        "intercept": round(float(intercept), 6),
        "r2": round(1 - ss_res / ss_tot, 4) if ss_tot else None,
        "x_observed_min": float(pair["x"].min()),
        "x_observed_max": float(pair["x"].max()),
        "within_observed_range": bool(
            pair["x"].min() <= required <= pair["x"].max()),
    }

    if x_min is not None or x_max is not None:
        lo = x_min if x_min is not None else float("-inf")
        hi = x_max if x_max is not None else float("inf")
        if lo > hi:
            raise GoalSeekError("x_min must not exceed x_max")
        within = lo <= required <= hi
        out["within_bounds"] = bool(within)
        if not within:
            # The binding bound and the best y the fit predicts there: what a
            # constrained solver would actually return.
            bound = lo if required < lo else hi
            out["bound_x"] = float(bound)
            out["achievable_y"] = round(float(slope * bound + intercept), 6)
    return out
