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
    "kpi": ("category",),
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
