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


def validate_widget_payload(widget_type: str | None, config: dict | None) -> None:
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
    Raises InvalidWidget naming the field.
    """
    if widget_type is not None and widget_type not in REQUIRED_ROLES:
        raise InvalidWidget(f"Unknown widget type {widget_type!r}")
    if config is None:
        return
    if not isinstance(config, dict):
        raise InvalidWidget("config must be an object")

    from .widget_data import AGGREGATION_NAMES
    for key in ("aggregation", "aggregation2"):
        agg = config.get(key)
        if agg is None or agg == "":
            continue
        if not isinstance(agg, str) or agg.lower() not in AGGREGATION_NAMES:
            raise InvalidWidget(
                f"{key} {agg!r} is not a supported aggregation "
                f"(an unknown name would silently be summed)")

    filters = config.get("filters")
    if filters is not None:
        if not isinstance(filters, list):
            raise InvalidWidget("filters must be a list")
        for i, f in enumerate(filters):
            if not isinstance(f, dict):
                raise InvalidWidget(f"filters[{i}] must be an object")
            if f.get("column") is not None and not isinstance(f["column"], str):
                raise InvalidWidget(f"filters[{i}].column must be a column name")

    measures = config.get("measures")
    if measures is not None and not isinstance(measures, list):
        raise InvalidWidget("measures must be a list")
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
