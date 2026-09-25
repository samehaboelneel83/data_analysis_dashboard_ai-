"""When will this reach X? — goal-seek along a forecast.

Goal-seek existed, solving for the x a target y needs on a linear fit of one
column against another. A forecast existed, projecting a series forward with a
95% prediction interval. Neither knew about the other, so the question a
forecast most obviously invites — *when* do we get there — had no answer.

This is the trajectory question only. Scenario analysis over underlying factors
("if marketing spend rose 10%...") needs a model that accepts exogenous
regressors, and the forecast path is AutoETS, which does not. Saying so is
better than implying otherwise.

Three things make the answer honest rather than a number:

  * **History is consulted first.** A target the series already passed is
    answered from history. On the demo data revenue peaked over a year ago and
    the projection has since settled below it — "not within the horizon" is true
    there and useless, where "already reached, in 2025-05, and not expected to
    recross" is something a reader can act on.

  * **The band gives earliest and latest.** The central estimate says when it is
    expected; the optimistic edge says the soonest it could happen and the
    pessimistic edge the latest. `shape_forecast`'s own docstring says a
    forecast whose uncertainty does not grow is lying about one of the two — an
    answer that ignores the band inherits that lie.

  * **Direction is read from the data.** A target above the last actual is a
    rise; below it, a fall. Which edge of the band counts as optimistic swaps
    between them, and getting that backwards would report the pessimistic date
    as the hopeful one.

Raises `ForecastGoalError` and imports no HTTP framework: layer 6 owns status
codes, and a service that raised `HTTPException` would be unusable from the
scheduler or a script.

**Why this lives in the query layer rather than beside the other analyses.**
`shape_forecast` attaches the answer to the widget payload, so that the caption
on screen is computed from the same numbers as the chart above it. That made
layer 4 import layer 5, which the conformance ratchet refused -- correctly. The
crossing logic is pure and has no dependencies, and "where does this projection
cross" is forecasting, which layer 4 already owns. The CATALOGUED analysis --
which forecasts a frame first, and is therefore genuinely analytics -- lives in
`analysis/forecast_goal.py` and imports downward into this.
"""
from __future__ import annotations

from typing import Any


class ForecastGoalError(ValueError):
    """Not enough to answer with — no forecast, no history, or no target."""


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None      # NaN is not a number here either


def _first_crossing(points: list[dict], key: str, target: float, rising: bool) -> str | None:
    """The first period whose `key` reaches the target, or None.

    FIRST, not last: "when do we get there" is answered by the earliest time it
    is true. Taking the last crossing would move the answer every time a period
    was appended, and would be wrong for a series that crosses and falls back.
    """
    for p in points:
        value = _num(p.get(key))
        if value is None:
            continue
        if (value >= target) if rising else (value <= target):
            name = p.get("name")
            return str(name) if name is not None else None
    return None


def forecast_goal(history: list[dict], forecast: list[dict], target: Any) -> dict:
    """When a forecast series is expected to reach `target`.

    `history` is `shape_forecast`'s `rows` ({name, value}); `forecast` is its
    `forecast` ({name, yhat, lo, hi}). Both are taken as given rather than
    recomputed, so this answers a question about the SAME numbers the reader is
    looking at — a second fit could disagree with the chart on screen.
    """
    goal = _num(target)
    if goal is None:
        raise ForecastGoalError("A numeric target is required")
    if not forecast:
        raise ForecastGoalError("There is no forecast to search")

    actuals = [p for p in history or [] if _num(p.get("value")) is not None]
    if not actuals:
        raise ForecastGoalError(
            "There is no history to compare the target against")

    last_actual = _num(actuals[-1]["value"])
    # Equal counts as a rise: `>=` then answers "we are already there" rather
    # than searching for a fall that has nothing to fall to.
    rising = goal >= last_actual

    # Already achieved? Answered from the earliest period that did it.
    reached = None
    for p in actuals:
        value = _num(p.get("value"))
        if value is None:
            continue
        if (value >= goal) if rising else (value <= goal):
            reached = {"period": str(p.get("name")), "value": value}
            break

    expected = _first_crossing(forecast, "yhat", goal, rising)
    # The optimistic edge is the one that moves TOWARDS the target: the high
    # edge for a rise, the low edge for a fall. Swapping these would report the
    # pessimistic date as the hopeful one.
    optimistic_key, pessimistic_key = ("hi", "lo") if rising else ("lo", "hi")
    earliest = _first_crossing(forecast, optimistic_key, goal, rising)
    latest = _first_crossing(forecast, pessimistic_key, goal, rising)

    end = forecast[-1]
    return {
        "target": goal,
        "direction": "rise" if rising else "fall",
        "last_actual": last_actual,
        "reached_in_history": reached,
        "expected_period": expected,
        # Both None when the forecast carries no band -- a `simple` forecast can
        # come back without lo/hi, and that should cost the range, not the answer.
        "earliest_period": earliest,
        "latest_period": latest,
        "within_horizon": expected is not None,
        "horizon": len(forecast),
        # How far short, so "not within the horizon" does not leave the reader
        # guessing whether they missed by a little or by a factor of two.
        "end_period": str(end.get("name")),
        "end_value": _num(end.get("yhat")),
        "end_lo": _num(end.get("lo")),
        "end_hi": _num(end.get("hi")),
    }
