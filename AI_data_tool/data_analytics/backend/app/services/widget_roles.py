"""What each widget type must be given before it can draw anything.

`ROLE_SPECS` in `frontend/src/types/report.ts` has always carried this: which
field roles a widget type needs, and which are optional. The config panel
enforces it, so a person building a widget by hand cannot get it wrong.

The server had no such notion. `get_widget_data` accepts any config; a widget
missing a role it needs falls through to a shaper that returns
`{"type": "empty"}`, and the reader sees a tile saying "No data" — the same
thing they would see if a filter excluded every row. Nothing distinguishes
"you didn't finish configuring this" from "there is nothing to show".

That mattered little while every widget came from the panel. It matters a great
deal now that a model proposes them: an LLM given 64 widget types will bind a
bubble chart to one measure, and a proposal that renders blank is worse than no
proposal at all.

`REQUIRED_ROLES` is the same information, server-side, checked before a proposed
widget is ever shown to anyone. `tests/test_widget_roles.py` re-derives the table
from the TypeScript source and fails if the two drift.
"""
from __future__ import annotations

#: widget type -> the roles it cannot draw without. Mirrors `required: true` in
#: ROLE_SPECS. An empty tuple means the type either needs nothing (a text box) or
#: is configured by keys that are options rather than field roles (`levels` for a
#: hierarchy, `id_col`/`parent_col` for an org chart) — those are checked
#: separately, because a role slot cannot express an ordered list of columns.
REQUIRED_ROLES: dict[str, tuple[str, ...]] = {
    # Models as widgets (services/model_widgets.py). Response + predictors,
    # SAS's statistics-object roles; a comparison has no roles of its own --
    # it names the model widgets it compares.
    "model_linear": ("measure", "predictors"),
    "model_logistic": ("response", "predictors"),
    "model_tree": ("response",),
    "model_cluster": ("measures",),
    "model_compare": (),
    "model_score": (),
    # Association rules: the columns are optional (blank = every usable text
    # column), and so is the column the conclusions must be about.
    "model_rules": (),
    "area": ("category",),
    "bar": ("category",),
    "box_plot": ("category", "measure"),
    "bubble": ("category", "measure", "measure2", "size"),
    "bubble_change": ("category", "measure", "measure2", "size", "animation"),
    "butterfly": ("category", "measure", "measure2"),
    "button": (),
    "card": ("measures",),
    "comparative_time_series": ("start", "measure", "measure2"),
    "container": (),
    "correlation_matrix": ("measures",),
    "crosstab": ("category",),
    # The category only. Layers carry their own measures, and a required
    # "measure" role would ask for a seventh field the builder does not use.
    "custom_graph": ("category",),
    # No required role: like every hierarchy layout, the columns that form
    # the nesting are `levels` (an ORDERED option), and the measure is
    # optional -- a pack of counts is a legitimate chart.
    "circle_pack": (),
    "custom_visual": (),
    "decomposition": (),
    "dendrogram": (),
    "donut": ("category",),
    "dot_plot": ("category",),
    "dual_axis_bar": ("category", "measure", "measure2"),
    "dual_axis_bar_line": ("category", "measure", "measure2"),
    "dual_axis_line": ("category", "measure", "measure2"),
    "dual_axis_time_series": ("start", "measure", "measure2"),
    "forecast": ("category", "measure"),
    "funnel": ("category",),
    "gauge": ("measure",),
    "heatmap": ("category", "category2", "measure"),
    "histogram": ("measure",),
    "icicle": (),
    "image": (),
    # A measure, never a dimension: a KPI renders rows[0].value, so a
    # dimension would headline ONE group's number as the overall figure.
    # Mirrors ROLE_SPECS since 6483a74 made the frontend say the same.
    "kpi": ("measure",),
    "line": ("category",),
    "list": ("category",),
    "map_bubbles": (),
    "map_choropleth": ("category", "measure"),
    "map_clusters": ("lat", "lon"),
    "map_density": ("lat", "lon"),
    "map_contour": ("lat", "lon"),
    "map_layers": (),
    "map_lines": ("lat", "lon", "lat2", "lon2"),
    "map_network": ("category", "category2", "lat", "lon", "lat2", "lon2"),
    "map_pie": ("category", "category2"),
    "map_points": (),
    "matrix": ("category",),
    "needle": ("category",),
    "network": ("category", "category2"),
    "numeric_series": ("measure", "measure2"),
    "org": (),
    "parallel_coordinates": ("measures",),
    "pie": ("category",),
    "ribbon": ("category", "category2", "measure"),
    "sankey": ("category", "category2"),
    "scatter": ("category",),
    "schedule": ("category", "start", "end"),
    # A script picks its own columns out of the frame; a required role here
    # would be a second answer to a question the code already answers.
    "script": (),
    "shape": (),
    "slicer": ("category",),
    "small_multiples": ("category",),
    "step": ("category",),
    "sunburst": (),
    "table": ("category",),
    "text": (),
    "tree": (),
    "treemap": ("category",),
    "vector_plot": ("measure", "measure2", "size", "direction"),
    "waterfall": ("category", "measure"),
    "web_content": (),
    "word_cloud": ("category",),
}

#: role -> the config key that carries it. Two roles are spelled differently in a
#: config than in a spec, for historical reasons; every other role uses its own
#: name. This is the server-side twin of the frontend's `configKeyFor`.
_ROLE_CONFIG_KEY = {"category": "dimension", "category2": "dimension2"}


def config_key_for_role(role: str) -> str:
    """The config key a role is written under."""
    return _ROLE_CONFIG_KEY.get(role, role)


def _blank(v) -> bool:
    return v is None or v == "" or (isinstance(v, list) and not v)


def migrate_widget_config(config: dict | None) -> dict:
    """A saved config in the current shape (E03). A copy; idempotent.

    Two legacy shapes, both still read by the engine but not by the widget
    panel, which opened them empty and then saved them away:

    * a `roles` dict (the demo's map and flow widgets) is flattened into the
      keys the panel edits (`config_key_for_role`). Only when no flat role
      key disagrees with it: `resolve_roles` uses `roles` alone when it is
      present, while `shape_series` reads the flat keys, so a config where
      they differ renders differently per chart and is left as it is;
    * `agg` becomes `aggregation` (dropped if `aggregation` is set: it is
      read first, so `agg` beside it was dead);
    * `interaction.mode`, which nothing reads, is dropped.

    Mirrors `migrateWidgetConfig` in the frontend's
    widgetConfigPanel/configShape.ts; both are pinned to the cases in
    widgetConfigPanel/widgetConfigMigrations.json."""
    from .widget_data import _LEGACY_ROLE_KEYS
    cfg = dict(config or {})
    if "agg" in cfg:
        if not _blank(cfg.get("aggregation")):
            cfg.pop("agg")
        elif isinstance(cfg["agg"], str) and cfg["agg"]:
            cfg["aggregation"] = cfg.pop("agg")
    inter = cfg.get("interaction")
    if isinstance(inter, dict) and "mode" in inter:
        # The demo wrote `{"mode": "two_way"}`: read by nothing (page-level
        # modes live elsewhere), and not an interaction setting.
        cfg["interaction"] = {k: v for k, v in inter.items() if k != "mode"}
    roles = cfg.get("roles")
    if isinstance(roles, dict):
        flat = {config_key_for_role(r): v for r, v in roles.items() if not _blank(v)}
        keys = set(_LEGACY_ROLE_KEYS) | set(flat)
        conflict = any(not _blank(cfg.get(k)) and (k not in flat or cfg[k] != flat[k]) for k in keys)
        if not conflict:
            cfg.pop("roles")
            cfg.update(flat)
    return cfg


def missing_roles(widget_type: str, config: dict) -> list[str]:
    """The config keys `widget_type` still needs, in the spec's own order.

    Named as config KEYS rather than role names because that is what a caller
    has to act on: they are writing a config, and "add `dimension2`" is
    actionable where "add the category2 role" is a translation exercise.

    An unknown widget type requires nothing. The shaper registry already falls
    back gracefully for types it does not know, and refusing here would reject a
    widget the rest of the system is happy to render.
    """
    required = REQUIRED_ROLES.get(widget_type)
    if not required:
        return []
    from .widget_data import resolve_roles
    cfg = config or {}
    have = resolve_roles(cfg)

    def present(role: str) -> bool:
        # Legacy keys resolve through resolve_roles; every other role lives
        # under its own config key (`predictors`, `response`, `partition`...)
        # -- the same test the builder's placeholder makes. Checking only the
        # resolved legacy roles reported every model widget as unfinished.
        if have.get(role):
            return True
        v = cfg.get(config_key_for_role(role))
        return not (v is None or v == "" or (isinstance(v, (list, tuple)) and not v))
    return [config_key_for_role(r) for r in required if not present(r)]


class InvalidWidget(ValueError):
    """A widget payload no engine can execute as written. Raised at SAVE time."""


# ── Formatting capabilities (E03 slice 2) ─────────────────────────────────────
# Mirror of CAPABILITIES in frontend/src/components/report/widgetCapabilities.ts:
# which formatting options each widget type's renderer actually HONOURS (that
# file documents, renderer by renderer, why each type gets what it gets).
# tests/test_widget_roles.py re-derives the map from the TypeScript and fails
# on drift, the same tripwire REQUIRED_ROLES has.
_FULL_WITH_LEGEND = ("axes", "yScale", "yDomain", "grid", "legend", "dataLabels")
_FULL_NO_LEGEND = ("axes", "yScale", "yDomain", "grid", "dataLabels")
_DUAL_SCALE = ("axes", "grid", "legend", "dataLabels")
_VALUE_ON_X_AXIS = ("axes", "grid", "dataLabels")

FORMATTING_CAPABILITIES: dict[str, frozenset[str]] = {k: frozenset(v) for k, v in {
    "bar": _FULL_WITH_LEGEND + ("overview", "patterns", "xCategoryAxis"),
    "bubble": _FULL_WITH_LEGEND,
    "ribbon": _FULL_WITH_LEGEND,
    "line": _FULL_NO_LEGEND + ("overview", "xCategoryAxis"),
    "area": _FULL_NO_LEGEND + ("overview", "xCategoryAxis"),
    "step": _FULL_NO_LEGEND + ("overview", "xCategoryAxis"),
    "histogram": _FULL_NO_LEGEND + ("xCategoryAxis",),
    "waterfall": _FULL_NO_LEGEND + ("xCategoryAxis",),
    "scatter": _FULL_NO_LEGEND,
    "bubble_change": _FULL_NO_LEGEND,
    "needle": _FULL_NO_LEGEND + ("xCategoryAxis",),
    "numeric_series": _FULL_NO_LEGEND,
    "pie": ("patterns", "dataLabels"),
    "donut": ("patterns", "legend", "dataLabels"),
    "funnel": ("patterns", "dataLabels"),
    "treemap": ("dataLabels",),
    "forecast": ("axes", "yScale", "yDomain", "grid", "xCategoryAxis"),
    "dual_axis_bar": _DUAL_SCALE + ("xCategoryAxis",),
    "dual_axis_line": _DUAL_SCALE + ("patterns", "xCategoryAxis"),
    "dual_axis_bar_line": _DUAL_SCALE + ("patterns", "xCategoryAxis"),
    "dual_axis_time_series": _DUAL_SCALE + ("patterns", "xCategoryAxis"),
    "comparative_time_series": _DUAL_SCALE + ("patterns", "xCategoryAxis"),
    "dot_plot": _VALUE_ON_X_AXIS,
    "butterfly": _VALUE_ON_X_AXIS,
    "schedule": ("axes", "grid"),
    "table": ("tableOptions",),
    "crosstab": ("tableOptions",),
    "matrix": ("tableOptions",),
}.items()}

#: The config keys WidgetConfigPanel writes ONLY under each capability (its
#: save effect, "only write keys the capability map actually grants"). A key
#: listed here on a type without the capability is an option its renderer
#: ignores -- stored, shown as set, and doing nothing.
CAPABILITY_KEYS: dict[str, tuple[str, ...]] = {
    "axes": ("x_axis_label", "y_axis_label", "axis_tick_size", "axis_tick_color",
             "y_axis_angle", "axis_line", "tick_line"),
    "xCategoryAxis": ("x_axis_angle",),
    "yScale": ("y_scale",),
    "yDomain": ("y_min", "y_max"),
    "grid": ("grid", "grid_style", "grid_color", "wall_color", "show_as_table"),
    "legend": ("legend", "legend_position"),
    "overview": ("overview_axis",),
    "dataLabels": ("data_labels",),
    "patterns": ("series_patterns",),
    "tableOptions": ("show_totals", "show_subtotals", "totals_position", "totals_scope",
                     "table_row_numbers"),
}


def unsupported_options(widget_type: str, config: dict) -> list[str]:
    """Formatting keys set on `config` that `widget_type`'s renderer ignores."""
    granted = FORMATTING_CAPABILITIES.get(widget_type, frozenset())
    out = []
    for cap, keys in CAPABILITY_KEYS.items():
        if cap in granted:
            continue
        out += [k for k in keys if config.get(k) not in (None, "", [])]
    return out


# ── E03: the settings nested in a config, and fixed vocabularies ────────────
# Each is what the engine or the renderer actually reads (see the comments on
# each); a value outside it was ignored (a filter op that matched everything),
# misread (`bar_mode: "stack"` drew stacked in the browser while the server
# computed a clustered axis) or crashed the request (a `sort` that is not a
# string). Checked on create for the whole config, and on update only for the
# keys the update changes -- a stored value nobody is editing is not
# re-litigated, so a legacy widget stays editable.

#: widget_data._apply_filters (pandas); DirectQuery and DuckDB take a subset.
FILTER_OPS = frozenset({"eq", "neq", "gt", "gte", "lt", "lte", "in", "like", "relative"})
#: widget_data series/grid HAVING (neq is not implemented).
HAVING_OPS = frozenset({"gt", "gte", "lt", "lte", "eq"})
#: The scalar options with a fixed vocabulary, lowercased where the reader
#: lowercases (sort, sort_by, dimension_granularity).
VOCABULARIES: dict[str, frozenset] = {
    "sort": frozenset({"asc", "desc"}),
    "sort_by": frozenset({"value", "name"}),
    "quick_calc": frozenset({"percent_of_total", "difference", "percent_change", "rank"}),
    "totals_position": frozenset({"before", "after"}),
    "totals_scope": frozenset({"all", "shown"}),
    "bar_mode": frozenset({"clustered", "stacked", "stacked100"}),
    "slicer_mode": frozenset({"auto", "buttons", "list", "dropdown", "search", "text"}),
    "legend_position": frozenset({"top", "bottom", "left", "right"}),
    "y_scale": frozenset({"linear", "log"}),
    "gauge_shape": frozenset({"arc", "speedometer", "bullet", "thermometer", "progress"}),
    "container_mode": frozenset({"group", "tabs", "scroll", "prompt", "precision"}),
    "dimension_granularity": frozenset({"year", "quarter", "month", "week", "day",
                                        "hour", "hour_of_day",
                                        "hijri_month", "hijri_year",
                                        "fiscal_year", "fiscal_quarter"}),
}
_CASE_FOLDED = frozenset({"sort", "sort_by", "dimension_granularity"})
INTERACTION_KEYS = frozenset({"broadcasts", "receives", "syncAllPages", "receiveMode", "actions"})
INTERACTION_MODES = frozenset({"filter", "highlight"})
ANALYTICS_KEYS = {"showAverageLine": bool, "referenceValue": (int, float),
                  "referenceLabel": str, "referenceColor": str}
RULE_KINDS = frozenset({"expression", "value_map", "interval", "data_bar"})
RULE_TARGETS = frozenset({"mark", "background", "visibility"})
MAX_DISPLAY_RULES = 100


def _is_number(v) -> bool:
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return True
    if isinstance(v, str):
        try:
            float(v)
            return True
        except ValueError:
            return False
    return False


def _check_filters(filters) -> None:
    if not isinstance(filters, list):
        raise InvalidWidget("filters must be a list")
    for i, f in enumerate(filters):
        if not isinstance(f, dict):
            raise InvalidWidget(f"filters[{i}] must be an object")
        if f.get("column") is not None and not isinstance(f["column"], str):
            raise InvalidWidget(f"filters[{i}].column must be a column name")
        if f.get("column") is None:
            continue    # names no column: every engine skips it, whatever else it says
        op = f.get("op", "eq")
        if op not in FILTER_OPS:
            raise InvalidWidget(f"filters[{i}].op {op!r} is not a filter operator "
                                f"({', '.join(sorted(FILTER_OPS))}); an unknown one matched every row")
        value = f.get("value")
        if op == "relative":
            from .relative_dates import RelativeDateError, validate_spec
            try:
                validate_spec(value)
            except RelativeDateError as e:
                raise InvalidWidget(f"filters[{i}]: {e}")
        elif op == "in":
            if isinstance(value, dict):
                raise InvalidWidget(f"filters[{i}].value must be a list of values for 'in'")
        elif isinstance(value, (dict, list)):
            raise InvalidWidget(f"filters[{i}].value must be a single value for {op!r}")


def _check_having(having) -> None:
    if not isinstance(having, list):
        raise InvalidWidget("having must be a list")
    for i, h in enumerate(having):
        if not isinstance(h, dict):
            raise InvalidWidget(f"having[{i}] must be an object")
        if h.get("op") not in HAVING_OPS:
            raise InvalidWidget(f"having[{i}].op must be one of {', '.join(sorted(HAVING_OPS))}")
        if not _is_number(h.get("value")):
            raise InvalidWidget(f"having[{i}].value must be a number")


def _check_rank(rank) -> None:
    if not isinstance(rank, dict):
        raise InvalidWidget("rank must be an object")
    if rank.get("mode") not in (None, "", "top", "bottom"):
        raise InvalidWidget("rank.mode must be 'top' or 'bottom'")
    n = rank.get("n")
    if isinstance(n, str) and n.startswith("@") and len(n) > 1:
        pass                                     # a report parameter, typed at render
    elif not _is_number(n) or float(n) <= 0:
        raise InvalidWidget("rank.n must be a positive number or a @parameter")
    for flag in ("percent", "other"):
        if flag in rank and not isinstance(rank[flag], bool):
            raise InvalidWidget(f"rank.{flag} must be true or false")


def _check_sort_keys(keys) -> None:
    if not isinstance(keys, list):
        raise InvalidWidget("sort_keys must be a list")
    for i, k in enumerate(keys):
        if not isinstance(k, dict) or not isinstance(k.get("col"), str):
            raise InvalidWidget(f"sort_keys[{i}] must be an object with a column name in 'col'")
        d = k.get("dir")
        if d is not None and (not isinstance(d, str) or d.lower() not in ("asc", "desc")):
            raise InvalidWidget(f"sort_keys[{i}].dir must be 'asc' or 'desc'")


def _check_display_rules(rules) -> None:
    if not isinstance(rules, list):
        raise InvalidWidget("display_rules must be a list")
    if len(rules) > MAX_DISPLAY_RULES:
        raise InvalidWidget(f"a widget takes at most {MAX_DISPLAY_RULES} display rules")
    for i, r in enumerate(rules):
        if not isinstance(r, dict):
            raise InvalidWidget(f"display_rules[{i}] must be an object")
        if r.get("kind") not in (None, *RULE_KINDS):
            raise InvalidWidget(f"display_rules[{i}].kind must be one of {', '.join(sorted(RULE_KINDS))}")
        if r.get("target") not in (None, *RULE_TARGETS):
            raise InvalidWidget(f"display_rules[{i}].target must be one of {', '.join(sorted(RULE_TARGETS))}")
        if r.get("expression") is not None and not isinstance(r["expression"], str):
            raise InvalidWidget(f"display_rules[{i}].expression must be text")
        for key in ("bands", "mappings"):
            if r.get(key) is not None and (not isinstance(r[key], list)
                                           or not all(isinstance(x, dict) for x in r[key])):
                raise InvalidWidget(f"display_rules[{i}].{key} must be a list of objects")


def _check_interaction(inter) -> None:
    if not isinstance(inter, dict):
        raise InvalidWidget("interaction must be an object")
    unknown = sorted(set(inter) - INTERACTION_KEYS)
    if unknown:
        raise InvalidWidget(f"interaction has no setting {', '.join(map(repr, unknown))}")
    for flag in ("broadcasts", "receives", "syncAllPages"):
        if flag in inter and not isinstance(inter[flag], bool):
            raise InvalidWidget(f"interaction.{flag} must be true or false")
    if inter.get("receiveMode") not in (None, *INTERACTION_MODES):
        raise InvalidWidget("interaction.receiveMode must be 'filter' or 'highlight'")
    actions = inter.get("actions")
    if actions is not None:
        if not isinstance(actions, list):
            raise InvalidWidget("interaction.actions must be a list")
        for i, a in enumerate(actions):
            if not isinstance(a, dict) or isinstance(a.get("targetId"), bool) \
                    or not isinstance(a.get("targetId"), int):
                raise InvalidWidget(f"interaction.actions[{i}] must name a target widget id")
            if a.get("mode") not in (None, *INTERACTION_MODES):
                raise InvalidWidget(f"interaction.actions[{i}].mode must be 'filter' or 'highlight'")


def _check_analytics(analytics) -> None:
    if not isinstance(analytics, dict):
        raise InvalidWidget("analytics must be an object")
    for k, v in analytics.items():
        kind = ANALYTICS_KEYS.get(k)
        if kind is None:
            raise InvalidWidget(f"analytics has no setting {k!r}")
        if v is not None and (isinstance(v, bool) and kind is not bool or not isinstance(v, kind)):
            raise InvalidWidget(f"analytics.{k} has the wrong type")


def _check_count(key: str, value) -> None:
    """limit / suppress_below: a whole number >= 0 (0 or blank = the default)."""
    if value is None or value == "":
        return
    if not _is_number(value) or float(value) < 0 or float(value) != int(float(value)):
        raise InvalidWidget(f"{key} must be a whole number, 0 or more")


_NESTED_CHECKS = {
    "filters": _check_filters, "having": _check_having, "rank": _check_rank,
    "sort_keys": _check_sort_keys, "display_rules": _check_display_rules,
    "interaction": _check_interaction, "analytics": _check_analytics,
}


def _check_settings(config: dict, keys) -> None:
    for key in keys:
        if key not in config:
            continue
        value = config[key]
        if key in _NESTED_CHECKS:
            if value is not None:
                _NESTED_CHECKS[key](value)
        elif key in VOCABULARIES:
            if value is None or value == "":
                continue
            probe = value.lower() if isinstance(value, str) and key in _CASE_FOLDED else value
            if probe not in VOCABULARIES[key]:
                raise InvalidWidget(f"{key} must be one of {', '.join(sorted(VOCABULARIES[key]))}")
        elif key in ("limit", "suppress_below"):
            _check_count(key, value)


def validate_widget_payload(widget_type: str | None, config: dict | None, *,
                            changed_keys=None) -> None:
    """Refuse, when a widget is SAVED, what would otherwise fail silently later.

    The server stored any `widget_type` string and any config dict. A typo'd
    type rendered as an empty tile; a misspelt aggregation fell back to SUM in
    both pandas paths -- a different number, with nothing to say so; a filter
    given as a string was skipped. Each failed far from its cause, so this is
    the one place such a mistake can be told to whoever made it.

    Deliberately narrow (E03 slice 1): the TYPE, and the SHAPE of the fields
    every engine reads. Unknown extra keys stay allowed -- a config carries
    dozens of renderer options, and declaring those is the next slice.
    `widget_type=None` checks the config alone (a PATCH that keeps the type).
    `changed_keys`, on an update: the config keys the update changes; the
    nested and vocabulary checks (slice 3) look only at those, so a legacy
    value nobody is editing never blocks an edit. None means all of them.
    Raises InvalidWidget naming the field.
    """
    if widget_type is not None and widget_type not in REQUIRED_ROLES:
        raise InvalidWidget(f"Unknown widget type {widget_type!r}")
    if config is None:
        return
    if not isinstance(config, dict):
        raise InvalidWidget("config must be an object")

    from .widget_data import AGGREGATION_NAMES, PERCENT_WIDGETS, SHARE_AGGREGATIONS
    for key in ("aggregation", "aggregation2"):
        agg = config.get(key)
        if agg is None or agg == "":
            continue
        name = agg.lower() if isinstance(agg, str) else None
        if name in SHARE_AGGREGATIONS:
            # Offered by the panel, computed by the grouped shapers only: the
            # save refused it everywhere, and would otherwise let a KPI or a
            # heatmap show a sum labelled as a percentage.
            if widget_type is not None and widget_type not in PERCENT_WIDGETS:
                raise InvalidWidget(
                    f"{key} 'pct' (Percentage %) is each group's share of the total; "
                    f"a {widget_type} does not group rows that way -- use it on a bar, "
                    f"line, pie or table")
            continue
        if name not in AGGREGATION_NAMES:
            raise InvalidWidget(
                f"{key} {agg!r} is not a supported aggregation "
                f"(an unknown name would silently be summed)")

    # E03 slice 3: nested settings and fixed vocabularies -- all of them on a
    # create, only the changed ones on an update (`changed_keys`).
    _check_settings(config, config.keys() if changed_keys is None else changed_keys)

    measures = config.get("measures")
    if measures is not None and not isinstance(measures, list):
        raise InvalidWidget("measures must be a list")

    # Several measures on one value axis (services/multi_measure.py).
    extra = config.get("extra_measures")
    if extra is not None:
        from .multi_measure import MULTI_MEASURE_WIDGETS
        from .pivot import PIVOT_WIDGETS
        if not isinstance(extra, list) or not all(isinstance(m, str) for m in extra):
            raise InvalidWidget("extra_measures must be a list of field names")
        if extra and widget_type is not None and widget_type not in MULTI_MEASURE_WIDGETS | PIVOT_WIDGETS:
            raise InvalidWidget(
                f"a {widget_type} widget takes one measure; more than one is for "
                f"{', '.join(sorted(MULTI_MEASURE_WIDGETS))} charts")
        if extra and config.get("dimension2") and widget_type not in PIVOT_WIDGETS:
            raise InvalidWidget(
                "several measures and a series split cannot be drawn together: "
                "remove the Series field or the extra measures")
    # More row / column levels on a crosstab (services/pivot.py).
    for key in ("rows_extra", "columns_extra"):
        v = config.get(key)
        if v is None:
            continue
        from .pivot import PIVOT_WIDGETS
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            raise InvalidWidget(f"{key} must be a list of field names")
        if v and widget_type is not None and widget_type not in PIVOT_WIDGETS:
            raise InvalidWidget(f"{key} is for a crosstab or matrix, not a {widget_type} widget")

    # Live QA 2026-10-03: both of these, in the wrong shape, saved fine and
    # then failed every render with a bare 500. The panel writes a string
    # for each; the API, the copilot or an import can write anything.
    def _changing(key):
        return changed_keys is None or key in changed_keys
    running = config.get("running")
    if _changing("running") and running not in (None, "") and (not isinstance(running, str)
                                      or running.lower() not in ("sum", "avg")):
        raise InvalidWidget("running must be 'sum' or 'avg'")
    split_by = config.get("split_by")
    if _changing("split_by") and split_by not in (None, "") and not isinstance(split_by, str):
        raise InvalidWidget("split_by names one field: the decomposition tree "
                            "splits one level at a time")

    roles = config.get("roles")
    if roles is not None and not isinstance(roles, dict):
        raise InvalidWidget("roles must be an object")

    # Slice 2: an option this type's renderer would ignore. The builder never
    # sends one (it rebuilds the config from the capability map on every save);
    # the API, the copilot and an import could, and it would sit in the config
    # looking set while doing nothing. Needs the type, so a config-only check
    # (widget_type=None) skips it -- callers pass the EFFECTIVE type instead.
    if widget_type is not None:
        ignored = unsupported_options(widget_type, config)
        if ignored:
            raise InvalidWidget(
                f"{', '.join(ignored)} {'has' if len(ignored) == 1 else 'have'} "
                f"no effect on a {widget_type} widget")
