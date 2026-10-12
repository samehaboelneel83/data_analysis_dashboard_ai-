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

#: White cards on a pale page, one family of blues: a page a person can put
#: in front of others as it is.
EXECUTIVE = {"mode": "light", "page_background": "#f3f5f9", "card_background": "#ffffff", "border_style": "none",
             "radius": 6, "shadow": "soft", "font_family": "sans", "title_size": 15, "title_weight": 600,
             "accent": "#1d4ed8", "palette": "ocean", "gap": 12}

BUILTIN: dict[str, dict] = {
    "executive": {
        "name": "Executive summary", "category": "overview",
        "tags": ["numbers", "trend", "forecast", "influencers", "map"],
        "description": "One page to open a meeting with: the headline numbers against the period before, where the "
                       "main number is heading, what goes with a higher one, and where it comes from -- with a page "
                       "each for the trend, the groups and the detail behind it.",
        "style": EXECUTIVE,
        "slots": [_slot("value", "The number to follow", "measure", True, number=["amount", "count"]),
                  _slot("date", "When each row happened", "date", True),
                  _slot("value2", "A second number", "measure"),
                  _slot("value3", "Third number", "measure"),
                  _slot("group", "The main way to split it", "category", max_distinct=25),
                  _slot("group2", "A second way to split it", "category", max_distinct=12),
                  _slot("place", "The place of each row", "geography")],
        "filters": [{"slot": "date", "mode": "range"}, {"slot": "group", "mode": "dropdown"},
                    {"slot": "group2", "mode": "buttons"}],
        "pages": [
            {"name": "Summary", "widgets": [
                _w("kpi", "Total {value}", 0, 0, 2, 4, **_total(sparkline_date="$date")),
                _w("kpi", "Total {value2}", 2, 0, 2, 4, **_total("$value2", sparkline_date="$date")),
                _w("kpi", "Total {value3}", 4, 0, 2, 4, **_total("$value3", sparkline_date="$date")),
                _w("area", "{value} over time", 6, 0, 6, 4, dimension="$date", dimension_granularity="month",
                   **_total()),
                _w("forecast", "{value} by month, and where it is heading", 0, 4, 8, 6, dimension="$date",
                   dimension_granularity="month", **_total()),
                _w("model_influencers", "What goes with a higher {value}", 8, 4, 4, 6, response="$value",
                   # As a meeting reads it: what goes with a higher value, the few that matter, no model lines.
                   influencer_style="bubbles", influencer_direction="higher", influencer_limit=6,
                   influencer_details=False),
                _w("map_choropleth", "{value} by {place}", 0, 10, 4, 6, dimension="$place", **_total()),
                _w("bar", "{value} by {group}", 4, 10, 4, 6, dimension="$group", sort="desc", sort_by="value",
                   limit=8, orientation="horizontal", **_total()),
                _w("bar", "{value} by quarter", 8, 10, 4, 6, dimension="$date", dimension_granularity="quarter",
                   **_total()),
            ]},
            {"name": "Trends", "widgets": [
                _w("line", "{value} by month", 0, 0, 12, 6, dimension="$date", dimension_granularity="month",
                   **_total()),
                _w("line", "{value} by {group2} over time", 0, 6, 7, 6, dimension="$date",
                   dimension_granularity="quarter", dimension2="$group2", **_total()),
                _w("bar", "{value} by day of the week", 7, 6, 5, 6, dimension="$date",
                   dimension_granularity="weekday", **_total()),
            ]},
            {"name": "Groups", "widgets": [
                _w("bar", "{value} by {group}, largest first", 0, 0, 7, 7, dimension="$group", sort="desc",
                   sort_by="value", limit=15, **_total()),
                _w("donut", "Share of {value} by {group2}", 7, 0, 5, 7, dimension="$group2", **_total()),
                _w("heatmap", "{value} by {group} and {group2}", 0, 7, 12, 6, dimension="$group",
                   dimension2="$group2", **_total()),
            ]},
            {"name": "Detail", "widgets": [
                _w("table", "{group} in detail", 0, 0, 12, 10, dimension="$group",
                   columns=["$group", "$value", "$value2", "$value3"]),
            ]},
        ],
    },
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
    "association": {
        "name": "What goes together", "category": "comparison", "tags": ["rules", "network", "roles"],
        "description": "Which values of these columns appear together more often than chance, read five ways by "
                       "the role each value plays: what a rule starts from, what it concludes, or both.",
        "style": LIGHT,
        "slots": [_slot("a", "A column of labels", "category", True, max_distinct=30),
                  _slot("b", "A second column of labels", "category", True, max_distinct=30),
                  _slot("c", "A third column of labels", "category", max_distinct=30),
                  _slot("d", "A fourth column of labels", "category", max_distinct=30)],
        "filters": [{"slot": "a", "mode": "dropdown"}, {"slot": "b", "mode": "dropdown"}],
        "pages": [{"name": "What goes together", "widgets": [
            _w("model_rules", "Values and what links them", 0, 0, 4, 8, predictors=["$a", "$b", "$?c", "$?d"],
               rules_view="network"),
            _w("model_rules", "The role of each value towards each other", 4, 0, 4, 8,
               predictors=["$a", "$b", "$?c", "$?d"], rules_view="matrix"),
            _w("model_rules", "How each value is linked", 8, 0, 4, 8, predictors=["$a", "$b", "$?c", "$?d"],
               rules_view="summary"),
            _w("model_rules", "The rules, with each value's role", 0, 8, 7, 8, predictors=["$a", "$b", "$?c", "$?d"],
               rules_view="table"),
            _w("model_rules", "Which values are linked, and how strongly", 7, 8, 5, 8,
               predictors=["$a", "$b", "$?c", "$?d"], rules_view="chord"),
        ]}],
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



# ── One page per analysis technique ──────────────────────────────────────────
# Each is named for the QUESTION the technique answers and built from what the
# platform already computes on any table: a distribution, a correlation grid,
# fitted models with each of their views as its own tile (`model_tab`), a
# forecast, a line read for unusual periods. A technique the platform does
# not have (survival curves, a solver's optimum) has no page here.
_NUMBER = "The number to follow"

BUILTIN.update({
    "describe": {
        "name": "What is in the data", "category": "analysis", "tags": ["descriptive", "distribution", "breakdown"],
        "description": "The first look at a table: how many rows, how one number is spread, and how the rows "
                       "divide among the values of a column.",
        "style": LIGHT,
        "slots": [_slot("value", "The number to look into", "measure", True),
                  _slot("group", "The main way to split it", "category", True, max_distinct=25),
                  _slot("group2", "A second way to split it", "category", max_distinct=12)],
        "filters": [{"slot": "group", "mode": "dropdown"}, {"slot": "group2", "mode": "buttons"}],
        "pages": [{"name": "What is in the data", "widgets": [
            _w("kpi", "Rows", 0, 0, 3, 3, measure="$value", aggregation="count"),
            _w("kpi", "Average {value}", 3, 0, 3, 3, measure="$value", aggregation="avg"),
            _w("kpi", "Lowest {value}", 6, 0, 3, 3, measure="$value", aggregation="min"),
            _w("kpi", "Highest {value}", 9, 0, 3, 3, measure="$value", aggregation="max"),
            _w("histogram", "How {value} is spread", 0, 3, 7, 6, measure="$value", bins=20),
            _w("donut", "Rows by {group}", 7, 3, 5, 6, dimension="$group", measure="$value", aggregation="count"),
            _w("box_plot", "{value} within each {group}", 0, 9, 7, 6, dimension="$group", measure="$value"),
            _w("bar", "Rows by {group2}", 7, 9, 5, 6, dimension="$group2", measure="$value", aggregation="count",
               sort="desc", sort_by="value", orientation="horizontal"),
        ]}],
    },
    "correlation": {
        "name": "Which numbers move together", "category": "analysis", "tags": ["correlation", "relationship"],
        "description": "Every pair of numbers at once, and the first number set against each of the others.",
        "style": LIGHT,
        "slots": [_slot("value", "First number", "measure", True), _slot("other", "Second number", "measure", True),
                  _slot("c", "Third number", "measure"), _slot("d", "Fourth number", "measure"),
                  _slot("e", "Fifth number", "measure"), _slot("group", "A way to split them", "category", max_distinct=12)],
        "filters": [{"slot": "group", "mode": "dropdown"}],
        "pages": [{"name": "Which numbers move together", "widgets": [
            _w("correlation_matrix", "Every pair of numbers", 0, 0, 6, 8, measures=["$value", "$other", "$?c", "$?d", "$?e"]),
            _w("numeric_series", "{value} against {other}", 6, 0, 6, 4, measure="$value", measure2="$other", points=True, limit=1500),
            _w("numeric_series", "{value} against {c}", 6, 4, 6, 4, measure="$value", measure2="$c", points=True, limit=1500),
            _w("parallel_coordinates", "Each row across the numbers", 0, 8, 12, 6,
               measures=["$value", "$other", "$?c", "$?d", "$?e"]),
        ]}],
    },
    "segments": {
        "name": "Natural groups", "category": "analysis", "tags": ["clustering", "segments"],
        "description": "The rows sorted into groups that resemble each other on the numbers you choose: the groups "
                       "as a picture, what each is like, and how well they hold apart.",
        "style": LIGHT,
        "slots": [_slot("value", "First number", "measure", True), _slot("other", "Second number", "measure", True),
                  _slot("c", "Third number", "measure"), _slot("d", "Fourth number", "measure")],
        "filters": [],
        "pages": [{"name": "Natural groups", "widgets": [
            _w("model_cluster", "The groups as a picture", 0, 0, 7, 8, measures=["$value", "$other", "$?c", "$?d"],
               model_tab="map"),
            _w("model_cluster", "What each group is like", 7, 0, 5, 8, measures=["$value", "$other", "$?c", "$?d"],
               model_tab="seg"),
            _w("numeric_series", "{value} against {other}", 0, 8, 7, 6, measure="$value", measure2="$other", points=True, limit=1500),
            _w("model_cluster", "How well the groups hold apart", 7, 8, 5, 6,
               measures=["$value", "$other", "$?c", "$?d"], model_tab="fit"),
        ]}],
    },
    "classify": {
        "name": "Which outcome a row will have", "category": "analysis", "tags": ["classification", "prediction"],
        "description": "A yes-or-no outcome predicted from the columns you choose: how often the prediction is right, "
                       "where it is wrong, and what matters most.",
        "style": LIGHT,
        "slots": [_slot("outcome", "The yes-or-no outcome", "flag", True),
                  _slot("value", "First number", "measure", True), _slot("other", "Second number", "measure"),
                  _slot("group", "A way to split it", "category", max_distinct=12)],
        "filters": [],
        "pages": [{"name": "Which outcome", "widgets": [
            _w("model_logistic", "How well it predicts", 0, 0, 4, 6, response="$outcome",
               predictors=["$value", "$?other", "$?group"], model_tab="fit"),
            _w("model_logistic", "Right and wrong", 4, 0, 4, 6, response="$outcome",
               predictors=["$value", "$?other", "$?group"], model_tab="cm"),
            _w("model_logistic", "Against a coin toss", 8, 0, 4, 6, response="$outcome",
               predictors=["$value", "$?other", "$?group"], model_tab="roc"),
            _w("model_tree", "What matters most", 0, 6, 6, 7, response="$outcome",
               predictors=["$value", "$?other", "$?group"], model_tab="imp"),
            _w("model_logistic", "What each factor does to the odds", 6, 6, 6, 7, response="$outcome",
               predictors=["$value", "$?other", "$?group"], model_tab="coef"),
        ]}],
    },
    "explain_number": {
        "name": "What a number depends on", "category": "analysis", "tags": ["regression", "relationship"],
        "description": "One number explained by others: how close the explanation comes, where it misses, and how "
                       "much each factor adds.",
        "style": LIGHT,
        "slots": [_slot("value", "The number to explain", "measure", True),
                  _slot("other", "A number it may depend on", "measure", True),
                  _slot("c", "Third number", "measure"), _slot("group", "A way to split it", "category", max_distinct=12)],
        "filters": [],
        "pages": [{"name": "What it depends on", "widgets": [
            _w("model_linear", "How well it is explained", 0, 0, 4, 6, measure="$value",
               predictors=["$other", "$?c", "$?group"], model_tab="fit"),
            _w("model_linear", "Actual against predicted", 4, 0, 4, 6, measure="$value",
               predictors=["$other", "$?c", "$?group"], model_tab="ap"),
            _w("model_linear", "Where it misses", 8, 0, 4, 6, measure="$value",
               predictors=["$other", "$?c", "$?group"], model_tab="resid"),
            _w("model_linear", "What each factor adds", 0, 6, 7, 7, measure="$value",
               predictors=["$other", "$?c", "$?group"], model_tab="coef"),
            _w("numeric_series", "{value} against {other}", 7, 6, 5, 7, measure="$value", measure2="$other", points=True, limit=1500),
        ]}],
    },
    "through_time": {
        "name": "A number through time", "category": "analysis", "tags": ["time series", "forecast", "seasonality"],
        "description": "One number month by month with where it is heading, the season in it, and the days of the "
                       "week that carry it.",
        "style": LIGHT,
        "slots": [_slot("value", _NUMBER, "measure", True, number=["amount", "count"]),
                  _slot("date", "When each row happened", "date", True)],
        "filters": [{"slot": "date", "mode": "range"}],
        "pages": [{"name": "Through time", "widgets": [
            _w("kpi", "Total {value}", 0, 0, 4, 4, **_total(sparkline_date="$date")),
            _w("kpi", "Average {value}", 4, 0, 4, 4, measure="$value", aggregation="avg", sparkline_date="$date"),
            _w("kpi", "Highest {value}", 8, 0, 4, 4, measure="$value", aggregation="max"),
            _w("forecast", "{value} by month, and where it is heading", 0, 4, 12, 6, dimension="$date",
               dimension_granularity="month", **_total()),
            _w("bar", "{value} by month of the year", 0, 10, 6, 6, dimension="$date",
               dimension_granularity="month_of_year", **_total()),
            _w("bar", "{value} by day of the week", 6, 10, 6, 6, dimension="$date",
               dimension_granularity="weekday", **_total()),
        ]}],
    },
    "unusual": {
        "name": "What is out of the ordinary", "category": "analysis", "tags": ["anomaly", "outliers"],
        "description": "The periods outside what their own history made likely, the values far from the rest, and "
                       "the groups they sit in.",
        "style": LIGHT,
        "slots": [_slot("value", "The number to look into", "measure", True),
                  _slot("date", "When each row happened", "date", True),
                  _slot("group", "A way to split it", "category", max_distinct=20)],
        "filters": [{"slot": "date", "mode": "range"}, {"slot": "group", "mode": "dropdown"}],
        "pages": [{"name": "Out of the ordinary", "widgets": [
            _w("kpi", "Average {value}", 0, 0, 4, 3, measure="$value", aggregation="avg"),
            _w("kpi", "Lowest {value}", 4, 0, 4, 3, measure="$value", aggregation="min"),
            _w("kpi", "Highest {value}", 8, 0, 4, 3, measure="$value", aggregation="max"),
            _w("line", "{value} by month, and the months outside the usual", 0, 3, 12, 6, dimension="$date",
               dimension_granularity="month", anomaly_band=True, change_point=True, **_total()),
            _w("box_plot", "{value} within each {group}", 0, 9, 7, 6, dimension="$group", measure="$value"),
            _w("histogram", "How {value} is spread", 7, 9, 5, 6, measure="$value", bins=30),
        ]}],
    },
    "words": {
        "name": "What a column of text says", "category": "analysis", "tags": ["text", "frequency"],
        "description": "The values of a text column by how often they occur: as a cloud, as a ranked list, and "
                       "across the groups.",
        "style": LIGHT,
        "slots": [_slot("text", "The column of text", "category", True, max_distinct=2000),
                  _slot("group", "A way to split it", "category", max_distinct=12)],
        "filters": [{"slot": "group", "mode": "dropdown"}],
        "pages": [{"name": "What the text says", "widgets": [
            _w("word_cloud", "{text}, sized by how often", 0, 0, 7, 8, dimension="$text", measure="$text",
               aggregation="count", limit=60),
            _w("list", "The most frequent {text}", 7, 0, 5, 8, dimension="$text", measure="$text", aggregation="count",
               sort="desc", sort_by="value", limit=15),
            _w("heatmap", "{text} by {group}", 0, 8, 12, 6, dimension="$text", dimension2="$group", measure="$text",
               aggregation="count", limit=15),
        ]}],
    },
    "links": {
        "name": "What is connected to what", "category": "analysis", "tags": ["network", "flow"],
        "description": "Two columns that name the two ends of a link: the network they make, the flow between them, "
                       "and the ends with the most links.",
        "style": LIGHT,
        "slots": [_slot("source", "Where a link starts", "category", True, max_distinct=40),
                  _slot("target", "Where a link ends", "category", True, max_distinct=40)],
        "filters": [{"slot": "source", "mode": "dropdown"}],
        "pages": [{"name": "What is connected", "widgets": [
            _w("network", "{source} and {target} as a network", 0, 0, 7, 8, dimension="$source",
               dimension2="$target", measure="$source", aggregation="count"),
            _w("list", "{source} with the most links", 7, 0, 5, 8, dimension="$source", measure="$target",
               aggregation="count", sort="desc", sort_by="value", limit=12),
            _w("sankey", "From {source} to {target}", 0, 8, 7, 7, dimension="$source", dimension2="$target",
               measure="$source", aggregation="count"),
            _w("heatmap", "{source} against {target}", 7, 8, 5, 7, dimension="$source", dimension2="$target",
               measure="$source", aggregation="count"),
        ]}],
    },
    "why_changed": {
        "name": "Where a number comes from", "category": "analysis", "tags": ["diagnostic", "contribution"],
        "description": "A total taken apart: what each group adds to it, the few that carry most of it, and how "
                       "the groups moved over time.",
        "style": LIGHT,
        "slots": [_slot("value", _NUMBER, "measure", True, number=["amount", "count"]),
                  _slot("group", "The groups to compare", "category", True, max_distinct=25),
                  _slot("date", "When each row happened", "date"),
                  _slot("group2", "A second way to split it", "category", max_distinct=12)],
        "filters": [{"slot": "date", "mode": "range"}, {"slot": "group2", "mode": "buttons"}],
        "pages": [{"name": "Where it comes from", "widgets": [
            _w("kpi", "Total {value}", 0, 0, 4, 4, **_total(sparkline_date="$?date")),
            _w("waterfall", "How {group} adds up to total {value}", 4, 0, 8, 7, dimension="$group", sort="desc",
               sort_by="value", limit=10, **_total()),
            _w("donut", "Share of {value} by {group2}", 0, 4, 4, 6, dimension="$group2", **_total()),
            _w("dual_axis_bar_line", "{value} by {group}, largest first", 0, 10, 7, 6, dimension="$group",
               measure="$value", measure2="$value", aggregation="sum", pareto=True, sort="desc"),
            _w("line", "{value} by {group} over time", 7, 7, 5, 9, dimension="$date", dimension_granularity="quarter",
               dimension2="$group", **_total()),
        ]}],
    },
})
BUILTIN["association"]["category"] = "analysis"

for _key, _spec in BUILTIN.items():
    _spec.update(schema=SCHEMA, key=_key)
    check(_spec)


def listing() -> list[dict]:
    return list(BUILTIN.values())
