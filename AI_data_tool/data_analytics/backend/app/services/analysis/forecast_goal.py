"""`forecast_goal` as a catalogued analysis: forecast a frame, then answer.

The crossing logic itself is `services/forecast_goal.py`, in the query layer --
`shape_forecast` attaches the answer to its own payload so the caption agrees
with the chart, and layer 4 cannot import layer 5. This module is the part that
is genuinely analytics: it takes a DataFrame, builds the projection, and hands
the result to the catalogue.
"""
from __future__ import annotations

from typing import Any

from ..forecast_goal import ForecastGoalError, forecast_goal

__all__ = ["ForecastGoalError", "forecast_goal", "forecast_goal_over"]


def forecast_goal_over(df, date_column: str, measure: str, target: Any,
                       aggregation: str = "sum", granularity: str = "month",
                       forecast_periods: int | None = None) -> dict:
    """Forecast a series from a frame, then answer "when will it reach X?".

    The dispatcher hands every analysis a DataFrame, and this one reasons about
    a projection — so the projection is built here, with `shape_forecast`, the
    SAME shaper the forecast widget uses. Deliberately the same: a second fit
    would be a second opinion presented as one fact, and a caption that
    disagreed with the chart above it is worse than no caption.

    The forecast itself comes back with the answer. A reader deciding whether
    to believe "expected 2026-03" needs to see the trajectory it came from.
    """
    from ..widget_data import shape_forecast

    for column in (date_column, measure):
        if column not in getattr(df, "columns", []):
            raise ForecastGoalError(f"Column '{column}' not found")

    config: dict[str, Any] = {
        "dimension": date_column, "measure": measure,
        "aggregation": aggregation, "dimension_granularity": granularity,
    }
    if forecast_periods:
        config["forecast_periods"] = forecast_periods

    shaped = shape_forecast(df, config)
    if shaped.get("type") == "empty":
        raise ForecastGoalError(
            shaped.get("error") or "There is not enough history to forecast")

    answer = forecast_goal(shaped.get("rows") or [],
                           shaped.get("forecast") or [], target)
    return {**answer,
            "measure": measure,
            "history": shaped.get("rows") or [],
            "forecast": shaped.get("forecast") or []}
