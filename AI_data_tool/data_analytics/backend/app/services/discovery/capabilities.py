"""One record per thing the platform can draw or compute: what it NEEDS of the
data, what it costs, what kind of claim its result is.

Before this there were five tables that each knew a part (the browser's role
list, the server's required roles, the shaper map, the model's menu text, and
four `_NEEDS_*` tuples in the designer), and every analysis kept its own
minimum in its own file. None recorded cost, the kind of claim, or whether a
model is needed -- so nothing could ask "what does THIS dataset support?"
without drawing everything.

What lives here is what nothing else records. Roles stay in
`widget_roles.REQUIRED_ROLES` (the save-time whitelist) and the menu prose in
`suggest_dataset_dashboard.WIDGET_GUIDE`; this registry reads them, so there
is still one place for each fact. The structure requirements (a date, two
measures, coordinates, a hierarchy, countries) MOVED here: the designer now
reads them from this module.

Everything is stated in terms of the DATA'S SHAPE -- a number that adds up, a
date, a category, an outcome, free text, a place -- never of a subject
(docs/discovery/PLAN.md: the platform is domain-neutral).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .. import widget_roles

# ── column kinds a capability can ask for ────────────────────────────────────
#   number     any quantity                additive   a number that adds up
#   level      a number that is averaged   date       a point in time
#   category   a column of few labels      outcome    what became of a row
#   text       free text                   place      a country / region / city
#   coords     a latitude + longitude      key        an identifier
#   item       a column naming things (more values than a category, fewer than a key)
KINDS = ("number", "additive", "level", "date", "category", "outcome", "text", "place", "coords", "key", "item")

FAMILIES = ("basics", "compare", "trend", "distribution", "relationship", "composition", "place", "flow",
            "table", "statistic", "model", "forecast", "anomaly", "pattern", "scenario", "text")
#: What a result IS, and therefore how it may be worded. A model may never
#: upgrade it: an association is not reported as a cause.
CLAIMS = ("observation", "association", "prediction", "hypothesis")
#: The question a capability answers.
ANSWERS = ("how_many", "compare", "trend", "relate", "explain", "predict", "unusual", "what_if", "where",
           "what_is_in_it", "what_goes_together")


@dataclass(frozen=True)
class Capability:
    name: str
    kind: str                       # "widget" | "analysis"
    family: str
    claim: str = "observation"
    answers: tuple[str, ...] = ()
    #: How many columns of each kind it needs, e.g. {"additive": 1, "date": 1}.
    needs: dict = field(default_factory=dict)
    #: Smallest data it is worth running on: rows, groups, periods, texts.
    minimum: dict = field(default_factory=dict)
    #: A structure the table must have: hierarchies | parent_child | transactions.
    structure: str | None = None
    #: 0 = answered from the stored profile; 1 = one aggregate; 2 = fits a model
    #: or scans many pairs (run as a job on large data).
    cost: int = 1
    #: Where its evidence can be computed.
    backends: tuple[str, ...] = ("frame",)
    #: none | optional | required
    llm: str = "none"
    #: A library that gives a richer variant when installed; the built-in one
    #: is always there (the platform runs fully offline).
    optional_backend: str | None = None
    #: Widget types that can show its result, best first.
    draws: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {"name": self.name, "kind": self.kind, "family": self.family, "claim": self.claim,
                "answers": list(self.answers), "needs": dict(self.needs), "minimum": dict(self.minimum),
                "structure": self.structure, "cost": self.cost, "backends": list(self.backends),
                "llm": self.llm, "optional_backend": self.optional_backend, "draws": list(self.draws)}


# ── structure requirements of widgets (moved from suggest_dataset_dashboard) ─
#: The value is the profile's `structure` key that must be non-empty.
NEEDS_STRUCTURE = {
    "map_points": "coordinate_pairs", "map_bubbles": "coordinate_pairs",
    "map_clusters": "coordinate_pairs", "map_density": "coordinate_pairs",
    "map_lines": "coordinate_pairs", "map_network": "coordinate_pairs",
    "map_layers": "coordinate_pairs",
    "org": "parent_child",
    "tree": "hierarchies", "sunburst": "hierarchies",
    "icicle": "hierarchies", "dendrogram": "hierarchies",
}
NEEDS_COUNTRY = ("map_choropleth", "map_pie")
NEEDS_DATE = ("line", "area", "step", "forecast", "ribbon", "schedule",
              "dual_axis_time_series", "comparative_time_series", "bubble_change")
NEEDS_TWO_MEASURES = ("scatter", "bubble", "numeric_series", "correlation_matrix",
                      "parallel_coordinates", "dual_axis_bar", "dual_axis_line",
                      "dual_axis_bar_line", "butterfly", "vector_plot")
NEEDS_TWO_CATEGORIES = ("heatmap", "crosstab", "matrix", "sankey", "network", "map_pie")
#: Carry no data, or need a target only a person knows: never proposed.
NOT_PROPOSABLE = ("text", "image", "shape", "button", "web_content", "container",
                  "custom_visual", "slicer", "script",
                  # carries an analysis' own parameters: offered through that analysis' card (`tile`)
                  "analysis_result")

# ── what each widget is: family, the question it answers, its cost ───────────
_WIDGETS: dict[str, tuple[str, tuple[str, ...], int]] = {
    "kpi": ("basics", ("how_many",), 1), "card": ("basics", ("how_many",), 1), "gauge": ("basics", ("how_many",), 1),
    "needle": ("basics", ("how_many",), 1),
    "bar": ("compare", ("compare", "how_many"), 1), "dot_plot": ("compare", ("compare",), 1),
    "butterfly": ("compare", ("compare",), 1), "dual_axis_bar": ("compare", ("compare",), 1),
    "dual_axis_line": ("compare", ("compare",), 1), "dual_axis_bar_line": ("compare", ("compare",), 1),
    "small_multiples": ("compare", ("compare",), 1), "word_cloud": ("compare", ("how_many",), 1),
    "custom_graph": ("compare", ("compare",), 1),
    "line": ("trend", ("trend",), 1), "area": ("trend", ("trend",), 1), "step": ("trend", ("trend",), 1),
    "ribbon": ("trend", ("trend", "compare"), 1), "dual_axis_time_series": ("trend", ("trend",), 1),
    "comparative_time_series": ("trend", ("trend", "compare"), 1), "bubble_change": ("trend", ("trend", "relate"), 1),
    "schedule": ("trend", ("trend",), 1), "decomposition": ("compare", ("explain",), 2),
    "forecast": ("forecast", ("predict", "trend"), 2),
    "histogram": ("distribution", ("unusual", "what_is_in_it"), 1), "box_plot": ("distribution", ("compare", "unusual"), 1),
    "scatter": ("relationship", ("relate",), 1), "numeric_series": ("relationship", ("relate",), 1),
    "bubble": ("relationship", ("relate", "compare"), 1), "vector_plot": ("relationship", ("relate",), 1),
    "correlation_matrix": ("relationship", ("relate",), 2), "parallel_coordinates": ("relationship", ("relate",), 1),
    "heatmap": ("relationship", ("compare", "relate"), 1),
    "pie": ("composition", ("how_many",), 1), "donut": ("composition", ("how_many",), 1),
    "treemap": ("composition", ("how_many", "compare"), 1), "funnel": ("composition", ("how_many",), 1),
    "waterfall": ("composition", ("explain",), 1),
    "tree": ("composition", ("how_many",), 1), "sunburst": ("composition", ("how_many",), 1),
    "icicle": ("composition", ("how_many",), 1), "dendrogram": ("composition", ("how_many",), 1),
    "circle_pack": ("composition", ("how_many",), 1), "org": ("composition", ("what_is_in_it",), 1),
    "map_choropleth": ("place", ("where",), 1), "map_points": ("place", ("where",), 1),
    "map_bubbles": ("place", ("where",), 1), "map_lines": ("place", ("where",), 1),
    "map_clusters": ("place", ("where",), 1), "map_density": ("place", ("where",), 1),
    "map_contour": ("place", ("where",), 2), "map_pie": ("place", ("where", "compare"), 1),
    "map_network": ("place", ("where",), 1), "map_layers": ("place", ("where",), 1),
    "sankey": ("flow", ("what_goes_together",), 1), "network": ("flow", ("what_goes_together",), 2),
    "table": ("table", ("what_is_in_it",), 1), "list": ("table", ("what_is_in_it",), 1),
    "crosstab": ("table", ("compare",), 1), "matrix": ("table", ("compare",), 1),
    "model_linear": ("model", ("explain", "predict"), 2), "model_logistic": ("model", ("explain", "predict"), 2),
    "model_tree": ("model", ("explain", "predict"), 2), "model_cluster": ("model", ("what_goes_together",), 2),
    "model_compare": ("model", ("predict",), 2), "model_score": ("model", ("predict",), 2),
    "model_rules": ("pattern", ("what_goes_together",), 2),
    "model_influencers": ("model", ("explain",), 2),
}
_CLAIM_OF_FAMILY = {"relationship": "association", "model": "association", "pattern": "association",
                    "forecast": "prediction", "scenario": "hypothesis"}
#: How many columns of which kind a widget role stands for.
_ROLE_KIND = {"category": "category", "category2": "category", "measure": "number", "measure2": "number",
              "size": "number", "measures": "number", "response": "number", "predictors": "number",
              "animation": "date", "source": "category", "target": "category"}

# ── analyses: what each needs, smallest data, cost ───────────────────────────
#: Keyed by the name in services/analysis/registry.py. The minimums repeat the
#: constants of each analysis module; tests/test_discovery_capabilities.py
#: holds the two in agreement.
_ANALYSES: dict[str, dict] = {
    "full_profile": dict(family="basics", answers=("what_is_in_it",), needs={}, cost=0),
    "compare_groups": dict(family="statistic", answers=("compare",), needs={"number": 1, "category": 1},
                           minimum={"rows_per_group": 10}, cost=1, claim="association"),
    "pairwise_comparisons": dict(family="statistic", answers=("compare",), needs={"number": 1, "category": 1},
                                 minimum={"rows_per_group": 10}, cost=1, claim="association"),
    "test_independence": dict(family="statistic", answers=("relate",), needs={"category": 2}, cost=1, claim="association"),
    "correlation_test": dict(family="statistic", answers=("relate",), needs={"number": 2}, cost=1, claim="association"),
    "regression": dict(family="model", answers=("explain", "predict"), needs={"number": 2}, cost=2, claim="association"),
    "glm_logistic": dict(family="model", answers=("explain", "predict"), needs={"outcome": 1, "number": 1},
                         minimum={"events_per_predictor": 10}, cost=2, claim="association"),
    "mixed_model": dict(family="model", answers=("explain",), needs={"number": 2, "category": 1}, cost=2, claim="association"),
    "survival": dict(family="model", answers=("explain",), needs={"number": 1, "outcome": 1}, cost=2, claim="association"),
    "explain_response": dict(family="statistic", answers=("explain",), needs={"number": 1}, minimum={"columns": 3},
                             cost=1, claim="association"),
    "compare_two_groups": dict(family="statistic", answers=("compare",), needs={"category": 1},
                               minimum={"rows": 60}, cost=1, claim="association"),
    "explain_variance": dict(family="statistic", answers=("explain", "compare"), needs={"number": 2, "category": 1},
                             cost=1),
    "explain_change": dict(family="statistic", answers=("explain",), needs={"number": 1, "date": 1, "category": 1},
                           minimum={"periods": 2}, cost=1),
    "key_influencers": dict(family="statistic", answers=("explain",), needs={"outcome": 1}, minimum={"rows": 30},
                            cost=2, claim="association", draws=("model_influencers",)),
    "segment": dict(family="model", answers=("what_goes_together",), needs={"number": 2}, minimum={"rows": 80},
                    cost=2, claim="association", draws=("model_cluster",)),
    "association_rules": dict(family="pattern", answers=("what_goes_together",), needs={"category": 2},
                              minimum={"rows": 200}, cost=2, claim="association", draws=("model_rules",)),
    "decision_tree": dict(family="model", answers=("explain", "predict"), needs={"outcome": 1}, minimum={"rows": 40},
                          cost=2, claim="association", draws=("model_tree",)),
    "automated_prediction": dict(family="model", answers=("predict",), needs={"outcome": 1}, minimum={"rows": 60},
                                 cost=2, claim="prediction"),
    "forecast_ets": dict(family="forecast", answers=("predict",), needs={"additive": 1, "date": 1},
                         minimum={"periods": 12}, cost=2, claim="prediction", draws=("forecast",)),
    "forecast_simple": dict(family="forecast", answers=("predict",), needs={"number": 1, "date": 1},
                            minimum={"periods": 6}, cost=1, claim="prediction", draws=("forecast",)),
    "forecast_goal": dict(family="forecast", answers=("predict", "what_if"), needs={"number": 1, "date": 1},
                          minimum={"periods": 8}, cost=2, claim="prediction"),
    "forecast_scenario": dict(family="scenario", answers=("what_if",), needs={"number": 2, "date": 1},
                              minimum={"periods": 8}, cost=2, claim="hypothesis"),
    "stage_board": dict(family="statistic", answers=("what_is_in_it", "compare"), needs={"category": 1, "date": 1},
                        cost=1),
    "compare_scenarios": dict(family="scenario", answers=("what_if",), needs={"number": 2, "date": 1},
                              minimum={"periods": 11}, cost=1, claim="hypothesis"),
    "goal_seek": dict(family="scenario", answers=("what_if",), needs={"number": 2}, cost=1, claim="hypothesis"),
    "anomaly_iqr": dict(family="anomaly", answers=("unusual",), needs={"number": 1}, cost=1),
    "anomaly_iforest": dict(family="anomaly", answers=("unusual",), needs={"number": 1}, minimum={"rows": 100}, cost=2),
    "anomaly_ecod": dict(family="anomaly", answers=("unusual",), needs={"number": 1}, minimum={"rows": 100}, cost=2),
    "text_topics": dict(family="text", answers=("what_is_in_it",), needs={"text": 1}, minimum={"texts": 20}, cost=2),
    "text_sentiment": dict(family="text", answers=("what_is_in_it",), needs={"text": 1}, minimum={"texts": 10}, cost=1),
}


# ── what the stored profile answers by itself (no analysis is run) ───────────
_PROFILE: dict[str, dict] = {
    # Every column's validity card: valid / unique / mistyped / missing, the
    # most and least common value, text lengths, the shape values share.
    "column_profile": dict(family="basics", answers=("what_is_in_it",), needs={}, cost=0),
    # How old the newest record is, by the date a record began.
    "data_delay": dict(family="basics", answers=("what_is_in_it",), needs={"date": 1}, cost=0),
    # Rows that are exact copies of another.
    "duplicate_rows": dict(family="basics", answers=("what_is_in_it",), needs={}, cost=0),
    # Values that are not what their column mostly holds.
    "mistyped_values": dict(family="basics", answers=("what_is_in_it", "unusual"), needs={}, cost=0),
}


# ── variants of a catalogued analysis that need another shape of table ───────
_VARIANTS: dict[str, dict] = {
    # One row per (group, thing): what occurs together in the same group.
    "basket_rules": dict(family="pattern", answers=("what_goes_together",), needs={"key": 1, "item": 1},
                         minimum={"rows": 200}, structure="transactions", cost=2, claim="association",
                         draws=("model_rules",)),
}


def _widget(name: str) -> Capability:
    family, answers, cost = _WIDGETS[name]
    needs: dict[str, int] = {}
    for role in widget_roles.REQUIRED_ROLES.get(name, ()):
        kind = _ROLE_KIND.get(role)
        if kind:
            needs[kind] = needs.get(kind, 0) + 1
    if name in NEEDS_DATE:
        # The "category" role of a time chart IS its date axis.
        needs["date"] = max(needs.get("date", 0), 1)
        if needs.get("category"):
            needs["category"] -= 1
            if not needs["category"]:
                del needs["category"]
    if name in NEEDS_TWO_MEASURES:
        needs["number"] = max(needs.get("number", 0), 2)
    if name in NEEDS_TWO_CATEGORIES:
        needs["category"] = max(needs.get("category", 0), 2)
    if name in NEEDS_COUNTRY:
        needs["place"] = 1
    structure = NEEDS_STRUCTURE.get(name)
    if structure == "coordinate_pairs":
        needs["coords"], structure = 1, None
    return Capability(name=name, kind="widget", family=family, answers=answers, needs=needs, structure=structure,
                      cost=cost, claim=_CLAIM_OF_FAMILY.get(family, "observation"),
                      minimum={"periods": 6} if name == "forecast" else {}, draws=(name,))


def _build() -> dict[str, Capability]:
    out: dict[str, Capability] = {}
    for name in widget_roles.REQUIRED_ROLES:
        if name in NOT_PROPOSABLE or name not in _WIDGETS:
            continue
        out[f"widget:{name}"] = _widget(name)
    for name, spec in _ANALYSES.items():
        out[f"analysis:{name}"] = Capability(name=name, kind="analysis",
                                             claim=spec.get("claim", "observation"),
                                             **{k: v for k, v in spec.items() if k != "claim"})
    for name, spec in _PROFILE.items():
        out[f"profile:{name}"] = Capability(name=name, kind="profile", **spec)
    for name, spec in _VARIANTS.items():
        out[f"analysis:{name}"] = Capability(name=name, kind="analysis", claim=spec.get("claim", "observation"),
                                             **{k: v for k, v in spec.items() if k != "claim"})
    return out


_ALL: dict[str, Capability] | None = None


def all_capabilities() -> dict[str, Capability]:
    global _ALL
    if _ALL is None:
        _ALL = _build()
    return _ALL


def widget(name: str) -> Capability | None:
    return all_capabilities().get(f"widget:{name}")


def analysis(name: str) -> Capability | None:
    return all_capabilities().get(f"analysis:{name}")


def profile_capability(name: str) -> Capability | None:
    return all_capabilities().get(f"profile:{name}")


def undescribed_widgets() -> list[str]:
    """Proposable widget types the server accepts that this registry does not
    describe -- must be empty (the test holds it)."""
    return sorted(n for n in widget_roles.REQUIRED_ROLES if n not in NOT_PROPOSABLE and n not in _WIDGETS)
