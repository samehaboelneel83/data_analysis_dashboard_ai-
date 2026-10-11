"""The platform's own templates.

Each is named for WHAT IT SHOWS (an overview, a trend, stages, a target met or
missed), never for a line of business: the same "Stages and conversion" reads a
pipeline of any kind, and what its boxes are called comes from the columns a
person maps, not from here. Slot labels are plain ("The number to follow").
Names, descriptions and slot labels are catalogue keys in the browser
(`tpl.b.<key>.*`); the English here is the fallback and the stored title text.

A 12-column grid, as the builder's.
"""
from __future__ import annotations

from .spec import SCHEMA, check


def _w(kind: str, title: str, x: int, y: int, w: int, h: int, **config) -> dict:
    return {"widget_type": kind, "title": title, "config": config, "layout": {"x": x, "y": y, "w": w, "h": h}}


def _slot(sid: str, label: str, kind: str, required: bool = False, **more) -> dict:
    return {"id": sid, "label": label, "kind": kind, "required": required, **more}


def _total(slot: str = "$value", **more) -> dict:
    return {"measure": slot, "aggregation": "sum", **more}


DARK = {"mode": "dark", "page_background": "#0f172a", "card_background": "#1e293b", "text_color": "#e2e8f0",
        "title_color": "#f8fafc", "border_style": "solid", "border_width": 1, "border_color": "#334155",
        "radius": 12, "shadow": "none", "font_family": "sans", "title_size": 14, "accent": "#38bdf8"}
LIGHT = {"mode": "light", "page_background": "#f4f6fb", "card_background": "#ffffff", "border_style": "solid",
         "border_width": 1, "border_color": "#e5e7eb", "radius": 14, "shadow": "soft", "font_family": "sans",
         "title_size": 14, "accent": "#2563eb"}
CRISP = {"mode": "light", "page_background": "#ffffff", "card_background": "#ffffff", "border_style": "solid",
         "border_width": 1, "border_color": "#d1d5db", "radius": 4, "shadow": "none", "font_family": "condensed",
         "title_size": 13, "title_weight": 700, "accent": "#0f766e"}
SOFT = {"mode": "light", "page_background": "#eef2ff", "card_background": "#ffffff", "border_style": "none",
        "radius": 20, "shadow": "raised", "font_family": "rounded", "title_size": 15, "accent": "#7c3aed"}
MIDNIGHT = {"mode": "dark", "page_background": "#0b1020", "card_background": "#111a33", "text_color": "#dbe4ff",
            "title_color": "#ffffff", "border_style": "solid", "border_width": 1, "border_color": "#1f2b4d",
            "radius": 10, "shadow": "strong", "font_family": "sans", "title_size": 13, "title_weight": 700,
            "accent": "#f59e0b", "palette": "sunset"}

BUILTIN: dict[str, dict] = {
    "overview": {
        "name": "Performance overview", "category": "overview", "tags": ["numbers", "trend", "breakdown"],
        "description": "The headline numbers with their history, how the main number moved over time, and "
                       "where it comes from.",
        "style": LIGHT,
        "slots": [_slot("value", "The number to follow", "measure", True, number=["amount", "count"]),
                  _slot("date", "When each row happened", "date"),
                  _slot("group", "The main way to split it", "category", max_distinct=25),
                  _slot("group2", "A second way to split it", "category", max_distinct=12),
                  _slot("value2", "A second number", "measure")],
        "filters": [{"slot": "date", "mode": "range"}, {"slot": "group", "mode": "dropdown"}],
        "pages": [{"name": "Overview", "widgets": [
            _w("kpi", "Total {value}", 0, 0, 3, 3, **_total(sparkline_date="$?date")),
            _w("kpi", "Rows", 3, 0, 3, 3, measure="$value", aggregation="count", sparkline_date="$?date"),
            _w("kpi", "Average {value}", 6, 0, 3, 3, measure="$value", aggregation="avg"),
            _w("kpi", "Total {value2}", 9, 0, 3, 3, **_total("$value2", sparkline_date="$?date")),
            _w("area", "{value} over time", 0, 3, 8, 6, dimension="$date", dimension_granularity="month", **_total()),
            _w("donut", "{value} by {group2}", 8, 3, 4, 6, dimension="$group2", **_total()),
            _w("bar", "{value} by {group}", 0, 9, 6, 6, dimension="$group", sort="desc", limit=10, **_total()),
            _w("table", "{group} in detail", 6, 9, 6, 6, dimension="$group", columns=["$group", "$value", "$value2"]),
        ], "relations": [{"from": 6, "to": 4, "mode": "filter"}, {"from": 6, "to": 5, "mode": "filter"},
                         {"from": 5, "to": 4, "mode": "filter"}, {"from": 5, "to": 6, "mode": "filter"}]}],
    },
    "scorecard": {
        "name": "Scorecard", "category": "overview", "tags": ["numbers", "at a glance"],
        "description": "Up to six numbers side by side, each with its change from the period before.",
        "style": MIDNIGHT,
        "slots": [_slot("date", "When each row happened", "date"),
                  _slot("a", "First number", "measure", True), _slot("b", "Second number", "measure"),
                  _slot("c", "Third number", "measure"), _slot("d", "Fourth number", "measure"),
                  _slot("e", "Fifth number", "measure"), _slot("f", "Sixth number", "measure"),
                  _slot("group", "A way to split them", "category", max_distinct=20)],
        "filters": [{"slot": "date", "mode": "range"}, {"slot": "group", "mode": "dropdown"}],
        "pages": [{"name": "Scorecard", "widgets": [
            *[_w("kpi", "{%s}" % s, (i % 3) * 4, (i // 3) * 3, 4, 3, **_total("$" + s, sparkline_date="$?date"))
              for i, s in enumerate("abcdef")],
            _w("line", "{a} over time", 0, 6, 7, 6, dimension="$date", dimension_granularity="month", **_total("$a")),
            _w("bar", "{a} by {group}", 7, 6, 5, 6, dimension="$group", sort="desc", limit=8, **_total("$a")),
        ], "relations": [{"from": 7, "to": 6, "mode": "filter"}]}],
    },
    "trend": {
        "name": "Trends and seasons", "category": "trend", "tags": ["time", "seasonality", "heatmap"],
        "description": "One number through time: month by month, year against year, and which days carry it.",
        "style": DARK,
        "slots": [_slot("value", "The number to follow", "measure", True, number=["amount", "count"]),
                  _slot("date", "When each row happened", "date", True),
                  _slot("group", "A way to split it", "category", max_distinct=8)],
        "filters": [{"slot": "date", "mode": "range"}, {"slot": "group", "mode": "buttons"}],
        "pages": [{"name": "Trends", "widgets": [
            _w("kpi", "Total {value}", 0, 0, 4, 3, **_total(sparkline_date="$?date")),
            _w("kpi", "Average {value}", 4, 0, 4, 3, measure="$value", aggregation="avg", sparkline_date="$?date"),
            _w("kpi", "Highest {value}", 8, 0, 4, 3, measure="$value", aggregation="max"),
            _w("line", "{value} by month", 0, 3, 7, 6, dimension="$date", dimension_granularity="month", **_total()),
            _w("bar", "{value} by day of the week", 7, 3, 5, 6, dimension="$date",
               dimension_granularity="weekday", **_total()),
            _w("heatmap", "{value} by year and month", 0, 9, 7, 6, dimension="$date", dimension_granularity="year",
               dimension2="$date", dimension2_granularity="month_of_year", **_total()),
            _w("line", "{value} by {group} over time", 7, 9, 5, 6, dimension="$date", dimension_granularity="quarter",
               dimension2="$group", **_total()),
        ]}],
    },
    "stages": {
        "name": "Stages and conversion", "category": "stages", "tags": ["funnel", "pipeline", "steps"],
        "description": "How many reach each stage, what each stage is worth, and how the flow moved over time.",
        "style": DARK,
        "slots": [_slot("stage", "The stage each row is at", "stage", True),
                  _slot("value", "What each row is worth", "measure", number=["amount", "count"]),
                  _slot("date", "When each row happened", "date"),
                  _slot("group", "A way to split it", "category", max_distinct=20)],
        "filters": [{"slot": "date", "mode": "range"}, {"slot": "group", "mode": "dropdown"}],
        "pages": [{"name": "Stages", "widgets": [
            _w("kpi", "Rows", 0, 0, 4, 3, measure="$stage", aggregation="count", sparkline_date="$?date"),
            _w("kpi", "Total {value}", 4, 0, 4, 3, **_total(sparkline_date="$?date")),
            _w("kpi", "Average {value}", 8, 0, 4, 3, measure="$value", aggregation="avg"),
            _w("funnel", "Rows at each {stage}", 0, 3, 5, 7, dimension="$stage", aggregation="count"),
            _w("line", "Rows over time", 5, 3, 7, 7, dimension="$date", dimension_granularity="month",
               measure="$stage", aggregation="count"),
            _w("bar", "{value} by {stage}", 0, 10, 5, 6, dimension="$stage", **_total()),
            _w("bar", "{stage} within each {group}", 5, 10, 7, 6, dimension="$group", dimension2="$stage",
               aggregation="count", bar_mode="stacked100", limit=12),
        ], "relations": [{"from": 3, "to": 4, "mode": "filter"}, {"from": 3, "to": 6, "mode": "filter"}]}],
    },
    "target": {
        "name": "Target against actual", "category": "target", "tags": ["goal", "budget", "attainment"],
        "description": "What was reached against what was expected: overall, for each group, and through time.",
        "style": CRISP,
        "slots": [_slot("actual", "What was reached", "measure", True, number=["amount", "count"]),
                  _slot("target", "What was expected", "measure", True, number=["amount", "count"],
                        same_unit="actual"),
                  _slot("date", "When each row happened", "date"),
                  _slot("group", "The groups to compare", "category", max_distinct=25)],
        "metrics": [{"id": "reached", "label": "{actual} as % of {target}",
                     "expression": "SUM({actual}) / SUM({target}) * 100",
                     "format": {"type": "number", "decimals": 1, "suffix": "%"}},
                    {"id": "gap", "label": "{actual} minus {target}", "expression": "SUM({actual}) - SUM({target})"}],
        "filters": [{"slot": "date", "mode": "range"}, {"slot": "group", "mode": "dropdown"}],
        "pages": [{"name": "Target", "widgets": [
            _w("kpi", "{actual}", 0, 0, 3, 3, **_total("$actual", sparkline_date="$?date")),
            _w("kpi", "{target}", 3, 0, 3, 3, **_total("$target")),
            _w("kpi", "Gap", 6, 0, 3, 3, measure="$m:gap"),
            _w("gauge", "Reached (%)", 9, 0, 3, 6, measure="$m:reached", target_value=100, gauge_shape="arc"),
            _w("dual_axis_line", "{actual} and {target} over time", 0, 3, 9, 6, dimension="$date",
               dimension_granularity="month", measure="$actual", measure2="$target", aggregation="sum"),
            _w("bar", "Reached (%) by {group}", 0, 9, 6, 6, dimension="$group", measure="$m:reached", sort="desc",
               limit=15, analytics={"referenceValue": 100}),
            _w("bar", "Gap by {group}", 6, 9, 6, 6, dimension="$group", measure="$m:gap", sort="asc", limit=15),
        ]}],
    },
    "monitoring": {
        "name": "Activity monitor", "category": "monitoring", "tags": ["volume", "hours", "heatmap"],
        "description": "How much is happening, when in the week it happens, and what kinds make it up.",
        "style": MIDNIGHT,
        "slots": [_slot("date", "When each row happened", "date", True),
                  _slot("kind", "The kind of each row", "category", True, max_distinct=15),
                  _slot("value", "A number to follow", "measure"),
                  _slot("where", "Where it happened", "category", max_distinct=30)],
        "filters": [{"slot": "date", "mode": "range"}, {"slot": "kind", "mode": "buttons"}],
        "pages": [{"name": "Activity", "widgets": [
            _w("kpi", "Rows", 0, 0, 4, 3, measure="$kind", aggregation="count", sparkline_date="$?date",
               sparkline_granularity="day"),
            _w("kpi", "Total {value}", 4, 0, 4, 3, **_total(sparkline_date="$?date")),
            _w("kpi", "Average {value}", 8, 0, 4, 3, measure="$value", aggregation="avg"),
            _w("area", "Rows over time", 0, 3, 8, 6, dimension="$date", dimension_granularity="day",
               measure="$kind", aggregation="count"),
            _w("bar", "Rows by {kind}", 8, 3, 4, 6, dimension="$kind", aggregation="count", sort="desc"),
            _w("heatmap", "Rows by day and hour", 0, 9, 8, 6, dimension="$date", dimension_granularity="weekday",
               dimension2="$date", dimension2_granularity="hour_of_day", measure="$kind", aggregation="count"),
            _w("bar", "Rows by {where}", 8, 9, 4, 6, dimension="$where", aggregation="count", sort="desc", limit=10),
        ], "relations": [{"from": 4, "to": 3, "mode": "filter"}, {"from": 4, "to": 5, "mode": "filter"}]}],
    },
    "comparison": {
        "name": "Groups compared", "category": "comparison", "tags": ["ranking", "share", "pareto"],
        "description": "Which groups carry the number: ranked, as shares, and one split against another.",
        "style": SOFT,
        "slots": [_slot("value", "The number to compare", "measure", True, number=["amount", "count"]),
                  _slot("group", "The groups to compare", "category", True, max_distinct=40),
                  _slot("group2", "A second way to split it", "category", max_distinct=12)],
        "filters": [{"slot": "group2", "mode": "buttons"}],
        "pages": [{"name": "Comparison", "widgets": [
            _w("kpi", "Total {value}", 0, 0, 4, 3, **_total()),
            _w("kpi", "Average {value}", 4, 0, 4, 3, measure="$value", aggregation="avg"),
            _w("kpi", "Number of {group}", 8, 0, 4, 3, measure="$group", aggregation="countd"),
            _w("dual_axis_bar_line", "{value} by {group}, largest first", 0, 3, 8, 6, dimension="$group",
               measure="$value", measure2="$value", aggregation="sum", pareto=True, sort="desc"),
            _w("donut", "Share of {value} by {group2}", 8, 3, 4, 6, dimension="$group2", **_total()),
            _w("treemap", "{value} by {group}", 0, 9, 6, 6, dimension="$group", **_total()),
            _w("heatmap", "{value} by {group} and {group2}", 6, 9, 6, 6, dimension="$group", dimension2="$group2",
               **_total()),
        ], "relations": [{"from": 4, "to": 3, "mode": "filter"}, {"from": 4, "to": 5, "mode": "filter"}]}],
    },
    "geography": {
        "name": "Places", "category": "geography", "tags": ["map", "regions"],
        "description": "A number on the map, the places ranked, and how each place moved over time.",
        "style": LIGHT,
        "slots": [_slot("place", "The place of each row", "geography", True),
                  _slot("value", "The number to follow", "measure", True, number=["amount", "count"]),
                  _slot("date", "When each row happened", "date"),
                  _slot("group", "A way to split it", "category", max_distinct=12)],
        "filters": [{"slot": "date", "mode": "range"}, {"slot": "group", "mode": "dropdown"}],
        "pages": [{"name": "Places", "widgets": [
            _w("kpi", "Total {value}", 0, 0, 4, 3, **_total(sparkline_date="$?date")),
            _w("kpi", "Number of {place}", 4, 0, 4, 3, measure="$place", aggregation="countd"),
            _w("kpi", "Average {value}", 8, 0, 4, 3, measure="$value", aggregation="avg"),
            _w("map_choropleth", "{value} by {place}", 0, 3, 7, 8, dimension="$place", **_total()),
            _w("bar", "{place} ranked by {value}", 7, 3, 5, 8, dimension="$place", sort="desc", limit=12, **_total()),
            _w("line", "{value} over time", 0, 11, 7, 5, dimension="$date", dimension_granularity="month", **_total()),
            _w("donut", "{value} by {group}", 7, 11, 5, 5, dimension="$group", **_total()),
        ], "relations": [{"from": 4, "to": 5, "mode": "filter"}, {"from": 4, "to": 6, "mode": "filter"}]}],
    },
    "distribution": {
        "name": "Spread and outliers", "category": "distribution", "tags": ["histogram", "range", "typical"],
        "description": "How a number is spread: its typical value, its range in each group, and the rows far "
                       "from the rest.",
        "style": CRISP,
        "slots": [_slot("value", "The number to look into", "measure", True),
                  _slot("group", "The groups to compare", "category", max_distinct=15),
                  _slot("other", "A second number", "measure")],
        "filters": [{"slot": "group", "mode": "dropdown"}],
        "pages": [{"name": "Spread", "widgets": [
            _w("kpi", "Typical {value}", 0, 0, 3, 3, measure="$value", aggregation="median"),
            _w("kpi", "Average {value}", 3, 0, 3, 3, measure="$value", aggregation="avg"),
            _w("kpi", "Lowest {value}", 6, 0, 3, 3, measure="$value", aggregation="min"),
            _w("kpi", "Highest {value}", 9, 0, 3, 3, measure="$value", aggregation="max"),
            _w("histogram", "How {value} is spread", 0, 3, 6, 6, measure="$value", bins=20),
            _w("box_plot", "{value} within each {group}", 6, 3, 6, 6, dimension="$group", measure="$value"),
            _w("scatter", "{value} against {other}", 0, 9, 6, 6, dimension="$other", measure="$value"),
            _w("bar", "Typical {value} by {group}", 6, 9, 6, 6, dimension="$group", measure="$value",
               aggregation="median", sort="desc"),
        ]}],
    },
    "detail": {
        "name": "Rows explorer", "category": "detail", "tags": ["table", "filters", "search"],
        "description": "The rows themselves, with filters above them and the counts that say what is in view.",
        "style": LIGHT,
        "slots": [_slot("columns", "The columns to show", "detail", True, many=True, max=8),
                  _slot("group", "A filter", "category", max_distinct=40),
                  _slot("group2", "A second filter", "category", max_distinct=40),
                  _slot("date", "When each row happened", "date"),
                  _slot("value", "A number to total", "measure")],
        "filters": [{"slot": "date", "mode": "range"}, {"slot": "group", "mode": "dropdown"},
                    {"slot": "group2", "mode": "dropdown"}],
        "pages": [{"name": "Rows", "widgets": [
            _w("kpi", "Total {value}", 0, 0, 3, 3, **_total()),
            _w("bar", "Rows by {group}", 3, 0, 9, 3, dimension="$group", aggregation="count", sort="desc", limit=12),
            _w("table", "Rows", 0, 3, 12, 10, dimension="$columns", columns=["$columns"]),
        ], "relations": [{"from": 1, "to": 2, "mode": "filter"}, {"from": 1, "to": 0, "mode": "filter"}]}],
    },
}

for _key, _spec in BUILTIN.items():
    _spec.update(schema=SCHEMA, key=_key)
    check(_spec)


def listing() -> list[dict]:
    return list(BUILTIN.values())
