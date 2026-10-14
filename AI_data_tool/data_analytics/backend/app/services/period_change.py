"""How much a level changed over the period shown: a headline number.

"How much did the price go up in 2023?" is the level on the LAST date against
the level on the FIRST date -- not the average of a daily-change column, which
read "0.264" for a year the index rose 66.8% (persona benchmark, 2026-10-13).

A kpi with `change_over: <date column>` is resolved as four ordinary headline
numbers through whatever path the caller uses (so row rules, engines and
caching are the single-measure ones): the first and last date, then the
measure on each of those dates. The result is the percent change, with both
ends kept so the sentence can say "from 42.75 to 76.89".
"""
from __future__ import annotations

from typing import Awaitable, Callable


def change_over(widget_type: str, config: dict | None) -> str | None:
    cfg = config or {}
    col = cfg.get("change_over")
    if widget_type in ("kpi", "card") and isinstance(col, str) and col and isinstance(cfg.get("measure"), str):
        return col
    return None


def _first(result: dict | None):
    rows = (result or {}).get("rows") or []
    return rows[0].get("value") if rows and isinstance(rows[0], dict) else None


def _plan(config: dict, date: str) -> tuple[dict, dict, dict]:
    base = {k: v for k, v in config.items() if k not in ("change_over", "sparkline_date", "dimension")}
    when = lambda agg: {**base, "measure": date, "aggregation": agg}          # noqa: E731
    return base, when("min"), when("max")


def _on(base: dict, date: str, day) -> dict:
    return {**base, "aggregation": base.get("aggregation") or "avg",
            "filters": list(base.get("filters") or []) + [{"column": date, "op": "gte", "value": day},
                                                          {"column": date, "op": "lte", "value": day}]}


def _result(config: dict, first_day, last_day, start, end) -> dict:
    measure = config.get("measure")
    if start in (None, 0) or end is None or first_day is None or first_day == last_day:
        return {"type": "empty", "rows": [], "total": 0, "unavailable": "period_change"}
    pct = (float(end) - float(start)) / abs(float(start)) * 100.0
    return {"type": "scalar", "measure": measure, "aggregation": "period_change",
            "rows": [{"name": measure, "value": round(pct, 2)}], "total": 1,
            "change": {"from": start, "to": end, "first": first_day, "last": last_day, "pct": round(pct, 2)},
            "format": {"type": "percent", "decimals": 1}}


def resolve(config: dict, one: Callable[[dict], dict]) -> dict:
    """Synchronously, with `one(config) -> kpi result` (the in-memory engine)."""
    date = config["change_over"]
    base, lo, hi = _plan(config, date)
    first_day, last_day = _first(one(lo)), _first(one(hi))
    if first_day is None or last_day is None:
        return _result(config, None, None, None, None)
    return _result(config, first_day, last_day, _first(one(_on(base, date, first_day))),
                   _first(one(_on(base, date, last_day))))


async def resolve_async(config: dict, one: Callable[[dict], Awaitable[dict]]) -> dict:
    """The same, through an async single-number path (the widget-data router)."""
    date = config["change_over"]
    base, lo, hi = _plan(config, date)
    first_day, last_day = _first(await one(lo)), _first(await one(hi))
    if first_day is None or last_day is None:
        return _result(config, None, None, None, None)
    return _result(config, first_day, last_day, _first(await one(_on(base, date, first_day))),
                   _first(await one(_on(base, date, last_day))))
