"""Propose whole dashboards for a dataset that already exists, for a named person.

`suggest_dashboard.py` answers a different question: someone has connected a
database and does not know which tables to join. This one starts after that --
the dataset exists, its columns are known, its data can be queried -- and asks
what a particular person should see.

WHY THE MODEL CHOOSES, AND NOT A RULE
-------------------------------------
A rule ("one KPI, one trend, one breakdown by the biggest category") produces
the same dashboard for a hospital, a bookshop and a bus network, and nobody
asked for that dashboard. Which of 64 chart types suits *this* data for *this*
person is a judgement, and it is the judgement the model is for. The free-text
goal -- "I am an instructor", "I run the emergency department" -- is passed
through verbatim, because the words someone chooses about their own job carry
more than any dropdown of roles would.

WHY THE MODEL IS FENCED IN ANYWAY
---------------------------------
A model given 64 widget types will bind a bubble chart to one measure, put a map
on a dataset with no coordinates, and sum a column of identifiers. Each of those
renders as a tile that says "No data" or shows a meaningless number, and a
proposal that renders blank is worse than no proposal: it costs the user the
time to accept it and the confusion of debugging it.

So three gates, narrowest first:

  1. `usable_widgets` -- the menu is filtered by what the DATA supports before
     the model sees it. No coordinates, no map types offered.
  2. `validate_widget` -- required roles present (`widget_roles.REQUIRED_ROLES`),
     every column real, no arithmetic on identifiers, no personal column as a
     dimension.
  3. the probe -- every surviving widget is EXECUTED and dropped if the shaper
     reports nothing to draw.

Gate 3 exists because an exhaustive test in this repository once declared 92 of
92 widgets working on the strength of a check that never ran the renderer. Six
of them were blank on screen.
"""
from __future__ import annotations

import asyncio
import re

from .dataset_profile import HIGH_CARDINALITY, describe_for_prompt
from .widget_roles import REQUIRED_ROLES, missing_roles

#: How many widgets are probed at once. The work is GIL-bound pandas, so
#: more than a handful buys nothing and costs event-loop responsiveness.
PROBE_CONCURRENCY = 4

#: Aggregations offered. A subset of the engine's 16: the ones whose meaning does
#: not depend on the grain. `std` and the percentiles are more often wrong than
#: right on a first draft, and nobody checks a first draft that closely.
ALLOWED_AGGREGATIONS = ("sum", "avg", "count", "countd", "min", "max", "median")

#: What a model calls an aggregation, mapped to what this engine calls it. Six
#: usable widgets were discarded in one live run because the model wrote
#: `average` and the engine spells it `avg`. A synonym is a vocabulary
#: difference, not a mistake, and throwing away a good chart over one is the kind
#: of strictness that makes a feature feel broken.
AGGREGATION_SYNONYMS = {
    "average": "avg", "mean": "avg", "avg.": "avg",
    "total": "sum", "sum_of": "sum",
    "count_distinct": "countd", "distinct_count": "countd", "unique": "countd",
    "minimum": "min", "maximum": "max", "med": "median",
}


def normalise_aggregations(config: dict) -> dict:
    """A copy of `config` with aggregation names the engine recognises."""
    out = dict(config)
    for key in ("aggregation", "aggregation2"):
        value = str(out.get(key) or "").lower().strip()
        if value in AGGREGATION_SYNONYMS:
            out[key] = AGGREGATION_SYNONYMS[value]
        elif value:
            out[key] = value
    return out


#: Aggregations that do arithmetic on the values. Meaningless on an identifier:
#: the sum of a column of encounter numbers is a number with no referent, which
#: is exactly what one dashboard in this repository displayed as "284,686".
ARITHMETIC_AGGREGATIONS = ("sum", "avg", "median", "min", "max")

#: The catalogue as the model sees it: what each type is FOR, in one line.
#: Written as advice rather than description -- "use when" is the decision the
#: model is actually making. Requirements come from REQUIRED_ROLES, so this table
#: cannot drift out of agreement with what the shapers need.
WIDGET_GUIDE: dict[str, str] = {
    "kpi": "one headline number over the WHOLE dataset. Give it a `measure` and an "
           "`aggregation` and NO dimension -- a dimension would make it show one "
           "group's number under a headline label.",
    "card": "several headline numbers together. Use when 2-4 figures share a frame.",
    "gauge": "one number against its range. Use when there is a natural target or ceiling.",
    "bar": "compare a measure across categories. The default for a breakdown.",
    "line": "a measure over time. Needs a date dimension.",
    "area": "a measure over time where the volume matters as much as the shape.",
    "step": "a measure over time that changes in steps rather than continuously.",
    "pie": "share of a whole. Only for 2-6 categories; beyond that a bar is clearer.",
    "donut": "share of a whole, with room for a total in the middle.",
    "treemap": "share of a whole across many categories, sized by value.",
    "scatter": "the relationship between two measures.",
    "histogram": "the distribution of one measure. Use to show spread, not total.",
    "box_plot": "the spread of a measure per category, including outliers.",
    "dot_plot": "compare a measure across a handful of categories, precisely.",
    "needle": "compare a measure across categories against a common scale.",
    "butterfly": "two measures per category, mirrored. Use for a comparison of two sides.",
    "waterfall": "how a total is built up or eroded, step by step.",
    "funnel": "attrition through ordered stages.",
    "table": "the rows themselves. Use when the detail is the point.",
    "crosstab": "a measure across two categories, as a grid of numbers.",
    "matrix": "a measure across two categories, as a grid of numbers.",
    "heatmap": "a measure across two categories, as colour. Use to spot hot spots.",
    "word_cloud": "the frequency of text values.",
    "list": "a simple ranked list of values.",
    "small_multiples": "the same chart repeated per category. Needs `facet_by`.",
    "forecast": "a measure over time, projected forward.",
    "dual_axis_bar_line": "two measures of different KINDS over one dimension, e.g. a "
                          "COUNT as bars and an AVERAGE as a line. Set `aggregation` for "
                          "the first and `aggregation2` for the second.",
    "dual_axis_bar": "two comparable measures per category, as paired bars.",
    "dual_axis_line": "two measures per category, as two lines on separate scales.",
    "dual_axis_time_series": "two measures over time on separate scales.",
    "comparative_time_series": "two measures over time, compared.",
    "ribbon": "how a composition changes over time, with rank changes visible. "
              "`dimension` is the period, `dimension2` the series.",
    "sankey": "flow from one category to another. `dimension` is the source, "
              "`dimension2` the target.",
    "network": "which categories occur together.",
    "correlation_matrix": "which measures move together. Takes `measures` (a list).",
    "parallel_coordinates": "several measures per row, compared. Takes `measures`.",
    "decomposition": "what drives a total, drilled down. Set `auto_split: true`.",
    "tree": "a nesting, as an indented tree. Takes `levels` (an ordered column list).",
    "sunburst": "a nesting, as rings. Takes `levels`. Only additive aggregations.",
    "icicle": "a nesting, as stacked bars. Takes `levels`.",
    "custom_graph": "several plot layers on one pair of axes, each with its own mark and aggregation. Takes `dimension` and `layers`. Use when one picture needs bars and a line together.",
    "circle_pack": "a nesting, as circles inside circles. Takes `levels`. Only additive aggregations -- area is the encoding.",
    "dendrogram": "a nesting, as a branching diagram. Takes `levels`.",
    "org": "a reporting line. Takes `id_col`, `parent_col` and `label_col`.",
    "schedule": "intervals over time. Takes `start` and `end` date columns.",
    "bubble": "three measures at once: x, y and size, per category.",
    "numeric_series": "two numeric columns plotted against each other, row by row.",
    "map_points": "locations on a map. Needs latitude and longitude.",
    "map_bubbles": "locations sized by a measure.",
    "map_clusters": "locations grouped into clusters where they crowd.",
    "map_density": "where locations concentrate, as a heat grid.",
    "map_choropleth": "COUNTRIES shaded by a measure. The dimension must hold country "
                      "names -- not provinces, states or cities.",
    "map_lines": "routes between two places. Needs both ends as coordinates.",
    "map_network": "a network anchored to geography.",
    "map_pie": "composition per COUNTRY, as pies on a map.",
    "map_layers": "regions and points on one map.",
}

#: Widget types that need something the profile can tell us about in advance.
#: The value is the profile key that must be non-empty.
_NEEDS_STRUCTURE = {
    "map_points": "coordinate_pairs", "map_bubbles": "coordinate_pairs",
    "map_clusters": "coordinate_pairs", "map_density": "coordinate_pairs",
    "map_lines": "coordinate_pairs", "map_network": "coordinate_pairs",
    "map_layers": "coordinate_pairs",
    "org": "parent_child",
    "tree": "hierarchies", "sunburst": "hierarchies",
    "icicle": "hierarchies", "dendrogram": "hierarchies",
}

#: Config keys that are SETTINGS rather than field roles: their values are
#: numbers, booleans or enumerations, and are never column names.
_SETTING_KEYS = ("aggregation", "aggregation2", "limit", "sort", "sort_by",
                 "dimension_granularity", "auto_split", "running", "rtl",
                 "inner_widget_type", "why", "bins", "baseline", "bar_mode",
                 "show_totals", "show_subtotals", "x_axis_angle", "filters")

#: What `_apply_filters` actually implements. An operator outside this list is
#: swallowed there without complaint, which would leave a chart showing
#: EVERYTHING under a title promising a subset -- worse than showing nothing.
FILTER_OPS = ("eq", "neq", "gt", "lt", "gte", "lte", "in", "like")


#: Widget types drawn along a labelled category axis. More categories than this
#: and the labels rotate into an unreadable band -- 26 departments in a
#: half-width tile, photographed from a generated dashboard. Top-N by value is
#: the ordinary default, and the author can raise it.
_CATEGORY_AXIS = ("bar", "pie", "donut", "treemap", "dot_plot", "needle",
                  "butterfly", "waterfall", "funnel", "step", "word_cloud",
                  "box_plot", "dual_axis_bar", "dual_axis_line", "dual_axis_bar_line")
READABLE_CATEGORIES = 12


#: The two map types that place rows by COUNTRY NAME rather than by coordinates.
#: Detected by column name, which is how such a column is actually named, and
#: gated because a choropleth of Egyptian governorates matched nothing and drew a
#: blank world map on a real dashboard in this repository.
_NEEDS_COUNTRY = ("map_choropleth", "map_pie")
_COUNTRY_WORDS = ("country", "nation", "country_name", "country_code", "iso_country")


def _has_country_column(profile: dict) -> bool:
    from .dataset_profile import _looks_like
    return any(_looks_like(c["name"], _COUNTRY_WORDS)
               for c in profile.get("columns", [])
               if c["role"] == "categorical")


#: Types that need a date column to mean anything.
_NEEDS_DATE = ("line", "area", "step", "forecast", "ribbon", "schedule",
               "dual_axis_time_series", "comparative_time_series", "bubble_change")

#: Types that need at least two numeric columns.
_NEEDS_TWO_MEASURES = ("scatter", "bubble", "numeric_series", "correlation_matrix",
                       "parallel_coordinates", "dual_axis_bar", "dual_axis_line",
                       "dual_axis_bar_line", "butterfly", "vector_plot")

#: Types deliberately withheld from the model. They carry no data (a text box, a
#: shape) or need a target the model cannot know (a button's action), so
#: proposing them is noise on a first draft.
#: `script` is withheld for a stronger reason than the rest: its content is
#: Python the server executes, only an admin may author one, and a proposed
#: tile with no code is a tile that shows an error.
_NOT_PROPOSABLE = ("text", "image", "shape", "button", "web_content", "container",
                   "custom_visual", "slicer", "script")

PROPOSALS_SCHEMA = {
    "type": "object",
    "properties": {
        "proposals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "rationale": {"type": "string"},
                    "widgets": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "widget_type": {"type": "string"},
                                "title": {"type": "string"},
                                "why": {"type": "string"},
                                "config": {"type": "object"},
                            },
                            "required": ["widget_type", "title", "why", "config"],
                        },
                    },
                },
                "required": ["title", "rationale", "widgets"],
            },
        },
    },
    "required": ["proposals"],
}


def _by_name(profile: dict) -> dict:
    out = {c["name"]: c for c in profile.get("columns", [])}
    for c in profile.get("other_columns", []):
        out.setdefault(c["name"], {"name": c["name"], "role": c.get("role"),
                                   "is_identifier": False, "is_personal": False,
                                   "distinct": 0})
    return out


def usable_widgets(profile: dict) -> list[str]:
    """The widget types this dataset can actually support.

    Filtering the menu is cheaper and far more reliable than rejecting the
    answer: a model that is never shown `map_points` cannot propose a map of a
    dataset with no coordinates.
    """
    st = profile.get("structure") or {}
    cols = profile.get("columns") or []
    numeric = [c for c in cols if c["role"] == "numeric" and not c["is_identifier"]]
    categorical = [c for c in cols if c["role"] == "categorical" and not c["is_personal"]]
    has_date = bool(st.get("date_range"))

    out: list[str] = []
    for wt in WIDGET_GUIDE:
        if wt in _NOT_PROPOSABLE:
            continue
        need = _NEEDS_STRUCTURE.get(wt)
        if need and not st.get(need):
            continue
        if wt in _NEEDS_COUNTRY and not _has_country_column(profile):
            continue
        if wt in _NEEDS_DATE and not has_date:
            continue
        if wt in _NEEDS_TWO_MEASURES and len(numeric) < 2:
            continue
        if wt in ("heatmap", "crosstab", "matrix", "sankey", "network", "map_pie") \
                and len(categorical) < 2:
            continue
        if not categorical and wt not in ("kpi", "card", "gauge", "histogram",
                                          "numeric_series", "correlation_matrix",
                                          "parallel_coordinates", "scatter", "table"):
            continue
        out.append(wt)
    return out


def _menu_text(profile: dict) -> str:
    lines = []
    for wt in usable_widgets(profile):
        req = REQUIRED_ROLES.get(wt, ())
        from .widget_roles import config_key_for_role
        keys = ", ".join(config_key_for_role(r) for r in req) or "no required fields"
        lines.append("- {}: {}\n    requires: {}".format(wt, WIDGET_GUIDE[wt], keys))
    return "\n".join(lines)


SYSTEM = """You design dashboards. You are given a real dataset and one person's \
description of their own job, and you propose the dashboards that would be most \
useful to THAT person.

Judge like an analyst who has to defend the page:

- Lead with the number that person opens the page to check. One KPI at the top \
beats three.
- Every widget must answer a question they would actually ask. If you cannot say \
what decision a chart informs, do not include it.
- Prefer few, well-chosen charts. Six that matter beat twelve that fill space.
- Vary the shapes: a page of nine bar charts wastes the catalogue and the reader.
- Use the person's own vocabulary in the titles.

Hard rules, because breaking them produces a chart that renders blank or lies:

- Use ONLY the column names given. Never invent one, never guess a plural.
- Use ONLY the widget types offered, and give every field each one requires.
- Never sum or average a column marked [identifier]; count it instead.
- Never use a column marked [personal data] as a dimension.
- For a chart over time, use the date column and let the granularity be chosen \
for you unless a different one is clearly better.
- `aggregation` applies to `measure`. On dual-axis charts, `aggregation2` applies \
to `measure2` -- use it when the two numbers are different kinds, such as a count \
against an average.
- A RATE or a SHARE is the `avg` of a 0/1 flag column, never a `count` of it. \
Counting a flag counts every row, which is the total, not the rate.
- Every field value is a COLUMN NAME. Never put a number, a target, or an \
expression in a field -- there is no SQL here. If you have no column for \
something, leave the field out.
- To narrow a chart to part of the data, add `filters`: a list of \
{"column": "...", "op": "...", "value": ...}. `op` is one of eq, neq, gt, lt, \
gte, lte, in (whose value is a list), like. This is how you build a rate or a \
subset out of a TEXT column -- count the rows whose status is one of the values \
you care about, rather than writing a condition into a field."""


def build_messages(profile: dict, goal: str | None, count: int,
                   knowledge=None) -> list[dict]:
    """The full exchange sent to the model.

    `knowledge` (a `services.knowledge.DatasetKnowledge`) is what turns this from
    a description of column SHAPES into a description of what the data means.
    Optional, and omitting it reproduces the previous prompt exactly -- an
    upload with no catalog behind it still gets the shape-only version, which is
    all anything knows about it.
    """
    who = (goal or "").strip()
    person = ('The person asking describes themselves like this, in their own words:\n'
              '"""\n{}\n"""\n'.format(who) if who else
              "The person asking has not described their role. Propose dashboards "
              "that would suit whoever owns this data, and say who you think that is "
              "in each rationale.\n")
    user = """{person}
THE DATA
{data}

WIDGETS YOU MAY USE
{menu}

Propose {count} different dashboards. Make them genuinely different from each \
other -- different questions, not the same page reordered. Each needs a title, a \
one-sentence rationale naming who it is for and what it answers, and 4 to 8 \
widgets. Give every widget a `why`: the question it answers, in one short \
sentence.""".format(person=person, data=describe_for_prompt(profile, knowledge),
                    menu=_menu_text(profile), count=count)
    return [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": user}]


def validate_widget(widget: dict, profile: dict) -> tuple[bool, str]:
    """`(ok, why not)` for one proposed widget."""
    wt = widget.get("widget_type")
    config = normalise_aggregations(widget.get("config") or {})
    title = widget.get("title") or wt

    if wt not in usable_widgets(profile):
        return False, "{}: {} is not usable on this dataset".format(title, wt)

    gaps = missing_roles(wt, config)
    # ROLE_SPECS marks `category` required on a KPI and a gauge because the config
    # panel lists the field. The tile does not need it -- and must not have it, or
    # it shows one group's number under a headline label. The prompt says so; the
    # validator agreeing with the prompt is the other half.
    if wt in ("kpi", "gauge"):
        gaps = [g for g in gaps if g != "dimension"]
    if gaps:
        return False, "{}: a {} also needs {}".format(title, wt, ", ".join(gaps))

    # ROLE_SPECS marks a KPI's `category` required and its measure optional --
    # true of the panel's field list, false of the tile. A KPI renders one
    # number, and with no measure the shaper answers with a table whose first row
    # the renderer then displays. Seen live as `{"aggregation": "median"}`: a
    # median of nothing, shown as a headline.
    if wt in ("kpi", "gauge") and not config.get("measure"):
        return False, "{}: a {} needs a measure to show".format(title, wt)

    known = _by_name(profile)
    # Every value that names a column must name a real one. Values that are
    # settings (a granularity, a limit, a boolean) are left alone.
    for key, value in config.items():
        if key in _SETTING_KEYS:
            continue
        # An explicit null or empty string means "not set". The model writes them
        # when told a field must be absent, and treating one as a column name
        # rejected three good widgets in a single live answer.
        if value is None or value == "":
            continue
        for name in (value if isinstance(value, list) else [value]):
            if name is None or name == "":
                continue
            # A role slot holds a COLUMN NAME. A gauge arrived live with
            # `target: 20` -- meaning "the goal is 20" -- which the engine read
            # as a column called 20, failed to find, and silently dropped. The
            # tile then drew with no target and said nothing about it.
            if not isinstance(name, str):
                return False, ("{}: {} has to name a column, not a value like "
                               "{!r}".format(title, key, name))
            if name not in known:
                return False, "{}: there is no column called {}".format(title, name)

    # Filters are how a chart is narrowed to part of the data, and are checked
    # here because `_apply_filters` drops a bad one silently: the tile would then
    # draw EVERYTHING under a title promising a subset. A model with no filter
    # vocabulary reaches for SQL instead -- observed live as a field containing
    # `abnormal_flag IN ('H', 'L')`, which cost six usable widgets in one answer.
    for f in (config.get("filters") or []):
        if not isinstance(f, dict):
            return False, ("{}: each filter is an object with column, op and value"
                           .format(title))
        col, op = f.get("column"), str(f.get("op") or "").lower()
        if col not in known:
            return False, "{}: there is no column called {}".format(title, col)
        if op not in FILTER_OPS:
            return False, ("{}: {!r} is not a filter operator here -- use one of {}"
                           .format(title, f.get("op"), ", ".join(FILTER_OPS)))

    agg = str(config.get("aggregation") or "").lower()
    agg2 = str(config.get("aggregation2") or "").lower()
    for a in (agg, agg2):
        if a and a not in ALLOWED_AGGREGATIONS:
            return False, "{}: {} is not an aggregation this engine has".format(title, a)

    for measure_key, which in (("measure", agg), ("measure2", agg2 or agg)):
        col = config.get(measure_key)
        if isinstance(col, str) and known.get(col, {}).get("is_identifier") \
                and which in ARITHMETIC_AGGREGATIONS:
            return False, ("{}: {} is an identifier -- {} of it means nothing, "
                           "use count".format(title, col, which))

    # `count` ignores the values in the column it counts, so counting a 0/1 flag
    # returns the row count -- seen live as "Abnormal Rate by Branch" configured
    # to count `abnormal_flag`, which would have drawn 466,948 under the word
    # "Rate". `avg` is the share, `sum` is the number flagged; both are useful.
    for measure_key in ("measure", "measure2"):
        col = config.get(measure_key)
        which = agg if measure_key == "measure" else (agg2 or agg)
        if isinstance(col, str) and known.get(col, {}).get("is_flag")                 and which in ("count", "countd"):
            return False, ("{}: {} is a 0/1 flag -- counting it counts every row. "
                           "Use avg for the rate, or sum for the number flagged."
                           .format(title, col))

    # An axis has to be readable. An identifier with thousands of distinct
    # values is a list of hashes wearing a chart, and the tell is the same one
    # `_hierarchies` already uses to keep such columns out of tree widgets.
    # Low-cardinality identifiers are left alone on purpose: `store_id` over
    # five stores is a legitimate dimension and refusing it would trade one
    # wrong answer for another.
    for dim_key in ("dimension", "dimension2", "group"):
        col = config.get(dim_key)
        if not isinstance(col, str):
            continue
        info = known.get(col, {})
        if info.get("is_identifier") and (info.get("distinct") or 0) > HIGH_CARDINALITY:
            alternatives = sorted(
                name for name, c in known.items()
                if c.get("role") == "categorical" and not c.get("is_identifier")
                and not c.get("is_personal")
                and 1 < (c.get("distinct") or 0) <= HIGH_CARDINALITY)
            instead = (" Group by {} instead.".format(", ".join(alternatives[:3]))
                       if alternatives else
                       " This data has no column with few enough values to group by.")
            return False, (
                "{}: {} is an identifier with {:,} distinct values -- charting it "
                "draws a row of hashes nobody can read.{}"
                .format(title, col, info.get("distinct") or 0, instead))

    for dim_key in ("dimension", "dimension2", "group"):
        col = config.get(dim_key)
        if isinstance(col, str) and known.get(col, {}).get("is_personal"):
            return False, "{}: {} is personal data and cannot be a dimension".format(
                title, col)

    # ── sense, not only shape ────────────────────────────────────────────────
    # Everything above asks whether the chart CAN be drawn. This asks whether
    # the number it draws means anything.
    #
    # On the first real run of the automation chain the model proposed 17
    # widgets, this function rejected none of them, and the lead tile on the
    # composed report was a SUM OF EXAM SCORES across 240 students. It rendered
    # perfectly. A total of 240 scores has no referent: it grows with the class
    # size rather than with attainment, and nothing can be compared against it.
    for measure_key in ("measure", "measure2"):
        col = config.get(measure_key)
        which = agg if measure_key == "measure" else (agg2 or agg)
        if not isinstance(col, str) or which not in ("sum",):
            continue
        if _is_bounded_measure(col, known.get(col) or {}):
            return False, (
                "{}: adding up {} does not give a meaningful total -- it "
                "describes each row rather than counting something, so the sum "
                "grows with the number of rows instead of telling you anything. "
                "Use an average, or a distribution to show how it varies."
                .format(title, col))

    return True, ""


#: Names that describe a bounded per-row quantity rather than something
#: countable. Summing any of them produces a number with no referent.
#:
#: Name-driven for the same reason `classify_role` is: it is the signal that
#: survives a column whose values happen to look ordinary. The range check below
#: is the corroborating half, for a column nobody named helpfully.
_BOUNDED_MEASURE_NAME = re.compile(
    r"(^|_)(score|scores|pct|percent|percentage|rate|ratio|rating|grade|"
    r"index|share|proportion|probability|accuracy|utilisation|utilization)($|_)",
    re.IGNORECASE)


def _is_bounded_measure(name: str, column: dict) -> bool:
    """True when summing this column is almost certainly not what was meant.

    Two signals, either sufficient:

    - **The name.** `final_score`, `pass_rate`, `satisfaction_rating`. This is
      the strong one: a column called a score is a score whatever its values
      happen to span.
    - **A 0..1 range.** A proportion is a proportion even when nobody named it
      one, and proportions do not add up to anything. A 0/1 FLAG is the one
      exception: its sum is the number of rows where it holds, which is a
      real question ("deaths"), so a flagged column is left to the flag
      rule above, which only refuses `count`.

    Deliberately NOT triggered by "small range" or "few distinct values".
    `tuition_fee` spans 8,800 to 15,800 across four values and summing it is
    exactly the question a registrar asks -- a rule that caught it would remove
    the case sums exist for.
    """
    if _BOUNDED_MEASURE_NAME.search(name or ""):
        return True
    if column.get("is_flag"):
        return False
    lo, hi = column.get("min"), column.get("max")
    try:
        return lo is not None and hi is not None and 0.0 <= float(lo) and float(hi) <= 1.0
    except (TypeError, ValueError):
        return False


def polish_widget(widget: dict, profile: dict) -> dict:
    """Fill in the settings an author would set and a model routinely forgets.

    Not corrections -- additions. A date axis with no granularity plots one point
    per raw timestamp, and a bar chart of a 500-value column draws 500 bars. Both
    are configurations the model chose correctly and simply left incomplete.
    """
    config = normalise_aggregations(widget.get("config") or {})
    known = _by_name(profile)
    span = (profile.get("structure") or {}).get("date_range") or {}

    # A KPI renders `rows[0].value`. Given a dimension it therefore shows ONE
    # GROUP'S number under a headline label -- observed live as "Current Median
    # Wait Time: 62", which was Laboratory Medicine's median, not the hospital's
    # 60. Dropping the dimension makes the shaper return a scalar over every row,
    # which is how the product's own demo content builds its KPIs.
    if widget.get("widget_type") in ("kpi", "gauge"):
        config.pop("dimension", None)
        config.pop("dimension2", None)

    dim = config.get("dimension")
    if isinstance(dim, str) and known.get(dim, {}).get("role") == "datetime" \
            and not config.get("dimension_granularity") and span.get("granularity"):
        config["dimension_granularity"] = span["granularity"]

    if isinstance(dim, str) and not config.get("limit"):
        distinct = known.get(dim, {}).get("distinct") or 0
        is_time = known.get(dim, {}).get("role") == "datetime"
        if distinct > HIGH_CARDINALITY:
            config["limit"] = 20
        elif (widget.get("widget_type") in _CATEGORY_AXIS
              and not is_time and distinct > READABLE_CATEGORIES):
            # Not about cardinality -- about how many labels fit under an axis.
            config["limit"] = READABLE_CATEGORIES

    # A formatting option this type's renderer ignores (the model sets
    # `x_axis_angle` on box and dot plots). Dropped here rather than proposed:
    # the dialog saves proposals through add-widget, which refuses such an
    # option (widget_roles.validate_widget_payload), so leaving it in would
    # fail "Create" halfway through a dashboard.
    from .widget_roles import unsupported_options
    for key in unsupported_options(widget.get("widget_type") or "", config):
        config.pop(key, None)

    return {**widget, "config": config}


#: Distinguishes "caller said nothing" from "caller said there is no model".
_UNSET = object()


async def suggest_for_dataset(profile: dict, goal: str | None, count: int = 3,
                              client=_UNSET, probe=None,
                              knowledge=None) -> tuple[list[dict], str]:
    """`(proposals, reason)` -- dashboards to choose from, or why there are none.

    `probe(widget_type, config)` runs the widget the way the browser will. A
    proposal is only returned once its widgets have actually drawn something.
    """
    if client is _UNSET:
        try:
            from .llm import get_client
            client = get_client()
        except Exception:                                    # noqa: BLE001
            client = None
    if client is None:
        return [], "the model endpoint is not configured"

    messages = build_messages(profile, goal, count, knowledge)
    rejected: list[str] = []

    # One generation, then at most one repair. The repair is worth its cost
    # because the failures are the kind a model fixes when told exactly what was
    # wrong -- an invented column, a missing field -- and without it the person
    # asked for help and got an empty panel.
    for attempt in range(2):
        got = await client.complete_json(messages, PROPOSALS_SCHEMA,
                                         max_tokens=12000, enforce=True)
        if not got or not got.get("proposals"):
            return [], "the model did not answer"

        kept: list[dict] = []
        rejected = []
        for proposal in got["proposals"][:count]:
            # Validate first -- it is free -- then probe what survives, several
            # at a time. Probing eighteen widgets one after another took 99
            # seconds in the browser: each one re-reads and re-prepares the
            # frame, so end to end they are the whole wait. Bounded, because the
            # pandas work is GIL-bound and firing them all at once would starve
            # the event loop without finishing sooner.
            candidates = []
            for widget in proposal.get("widgets") or []:
                ok, why = validate_widget(widget, profile)
                if not ok:
                    rejected.append(why)
                    continue
                candidates.append(polish_widget(widget, profile))

            gate = asyncio.Semaphore(PROBE_CONCURRENCY)

            async def _guarded(w):
                async with gate:
                    return await _probe(w, probe)

            results = await asyncio.gather(*(_guarded(w) for w in candidates))                 if candidates else []

            # Zipped back onto `candidates`, so the order the model chose
            # survives being probed out of sequence -- the tiles are laid out in
            # exactly this order.
            widgets = []
            for widget, (drew, rows, why) in zip(candidates, results):
                if not drew:
                    rejected.append("{}: {}".format(
                        widget.get("title"), why or "returned nothing to draw"))
                    continue
                widgets.append({**widget, "row_count": rows})
            if widgets:
                kept.append({**proposal, "widgets": widgets})

        if kept:
            # The rejections travel with the answer. A page that quietly contains
            # four widgets when the model proposed seven tells the person nothing;
            # naming what was dropped, and why, lets them judge the rest.
            return kept, ("; ".join(rejected[:6]) if rejected else "")
        if attempt == 0:
            messages = messages + [
                {"role": "assistant", "content": "(previous attempt)"},
                {"role": "user", "content":
                    "None of those could be used:\n- " + "\n- ".join(rejected[:12])
                    + "\n\nPropose again, fixing exactly these problems. Use only "
                      "the columns and widget types listed above."}]

    return [], ("nothing proposed could be drawn: " + "; ".join(rejected[:4])
                if rejected else "nothing could be proposed")


#: Keys a widget result carries ABOUT its data rather than data itself.
_RESULT_METADATA = frozenset({"truncation", "relative_dates", "partial_period", "population",
                              "evidence", "notes", "warnings", "disclosure"})


async def _probe(widget: dict, probe) -> tuple[bool, int, str]:
    """Did this widget actually draw, how much, and if not -- why not?

    The shaper's own verdict is the authority. Counting rows under a key of my
    choosing is what produced a false all-clear once already: a sunburst answers
    with `root`, a decomposition with `children`, a heatmap with `cells`, and a
    check that only knew about `rows` called all three empty.

    The third element is the reason. "returned nothing to draw" is true when a
    shaper produced an empty result and false when the ENGINE refused the
    aggregation -- and a person watching two of three proposed dashboards vanish
    deserves the difference, because one of them is about their data and the
    other is about this dataset's mode.
    """
    if probe is None:
        return True, 0, ""
    try:
        result = await probe(widget["widget_type"], widget["config"])
    except Exception as exc:                                 # noqa: BLE001
        return False, 0, "could not be drawn ({})".format(type(exc).__name__)
    # A probe may hand back its own refusal rather than an empty shape.
    if isinstance(result, dict) and result.get("unsupported"):
        return False, 0, str(result["unsupported"])
    if not isinstance(result, dict) or result.get("type") == "empty":
        return False, 0, "returned nothing to draw"
    # `rows` when the shaper has them; otherwise the largest DATA container.
    # Disclosure metadata (truncation, date windows...) is a dict too, and
    # counting its keys reported a 3-bar chart as "5 rows".
    if isinstance(result.get("rows"), list):
        size = len(result["rows"])
    else:
        size = 0
        for key, value in result.items():
            if key in _RESULT_METADATA:
                continue
            if isinstance(value, (list, dict)):
                size = max(size, len(value))
    if size == 0 and result.get("value") is None:
        return False, 0, "returned nothing to draw"
    # A gauge or a scalar KPI answers with `value` and no rows. Reporting "0
    # rows" beside it in the panel reads as an empty tile when it is a working
    # one: it is one number, so it counts as one.
    return True, size or 1, ""


#: The clarifying question is capped hard. A paragraph is not a question, and a
#: person who has already been kept waiting for a design will not read one.
MAX_QUESTION_CHARS = 200


async def clarifying_question(goal: str | None, reason: str, profile: dict,
                              client=_UNSET) -> str | None:
    """One short question to ask when no dashboard could be designed.

    The designer already answers "why not" -- but a reason is a dead end, and
    the person is left rereading their own sentence wondering which part was
    wrong. `agent/nodes/clarify.py` solved the same problem for the agent (D4.3,
    "ask, do not guess"), and this is that node's shape applied here: turn the
    refusal into a question that offers the concrete interpretations.

    Returns None when there is no model, when the reason is that there is no
    model, or when the model declines -- and None means the caller shows the
    reason exactly as it did before. An invented question would be worse than
    the plain refusal it replaced.
    """
    if client is _UNSET:
        try:
            from .llm import get_client
            client = get_client()
        except Exception:                                    # noqa: BLE001
            client = None
    if client is None:
        return None
    # "The model endpoint is not configured" cannot be clarified by asking the
    # model. Guard explicitly rather than letting the call fail and be swallowed.
    if "not configured" in (reason or "").casefold():
        return None

    columns = ", ".join(c["name"] for c in (profile.get("columns") or [])[:40])
    try:
        got = await client.complete(
            [{"role": "system", "content": (
                "A person asked for a dashboard and none could be designed. "
                "Write ONE short question that would let you try again, offering "
                "the concrete choices this data actually supports. No preamble, "
                "no apology, no more than one sentence.")},
             {"role": "user", "content":
                "What they asked for: {}\nWhy it could not be designed: {}\n"
                "Columns available: {}".format(goal or "(they said nothing)",
                                               reason or "(no reason given)",
                                               columns)}],
            max_tokens=120, temperature=0.2)
    except Exception:                                        # noqa: BLE001
        # Asking is an improvement on a refusal, never a requirement. A model
        # that cannot answer this must not turn a clean "no" into a 500.
        return None
    text = (got or "").strip()
    return text[:MAX_QUESTION_CHARS] or None
