"""A4: analysis tool catalogue -- single source of truth for what analyses
this app can run.

Consumed by two callers that must never drift apart:
  - `GET /analysis/registry` (routers/analysis.py) -- capability discovery
    for any client (frontend, external integrator).
  - the agent's SQL-generation prompt (services/agent/nodes/generate.py) --
    a compact "Analyses available" block so the model knows deeper analyses
    exist beyond what it can express in SQL.
Both render from `all_analyses()` below, so a registration added here shows
up in BOTH places automatically -- see test_registry.py's single-source test.

Registration pattern: explicit `register()` calls, all centralized in THIS
module (below), rather than each analysis module self-registering via a
decorator at its own import time. Two of the analysis modules
(`analysis/segment.py`, `analysis/anomaly.py`) exist specifically to keep
heavy ML imports (sklearn, pyod) off the app-import path -- see their own
docstrings -- and `services/widget_data.py` does the same for statsforecast.
A self-registering decorator would need `registry.register` to run at THEIR
import time, which is harmless by itself, but it would also mean importing
`analysis.registry` -- from the router AND from the agent's hot
prompt-building path, both far more frequently exercised than any single
analysis run -- transitively imports every analysis module. That is one more
place a future analysis module could accidentally add a module-level heavy
import without anyone noticing it broke THIS file's "importable from
anywhere at zero cost" contract. Centralizing the calls here instead keeps
this module pure, dependency-light metadata: it imports nothing from
segment.py/anomaly.py/widget_data.py at all, so it is safe to import from
main.py's router wiring and from every prompt build alike.
"""
from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from typing import Any
from ..widget_data import (DEFAULT_FORECAST_PERIODS, FORECAST_MIN_PERIODS,
                           MAX_FORECAST_PERIODS)
# Depth bounds only -- this module imports no sklearn, and decision_tree.py's
# own sklearn import lives inside its function precisely so this stays true.
from .decision_tree import DEFAULT_MAX_DEPTH as DEFAULT_TREE_DEPTH
from .forecast_scenario import DEFAULT_HORIZON as DEFAULT_SCENARIO_HORIZON
from .forecast_scenario import MAX_HORIZON as MAX_SCENARIO_HORIZON
from .text_topics import DEFAULT_TOPICS as DEFAULT_TEXT_TOPICS
from .text_topics import MAX_TOPICS as MAX_TEXT_TOPICS
from .decision_tree import HARD_MAX_DEPTH as HARD_TREE_DEPTH


@dataclass(frozen=True)
class AnalysisSpec:
    name: str
    description: str
    params_schema: dict[str, Any]
    result_kind: str
    #: "module.path:function", resolved on first call -- NOT a function object.
    #: This module is imported by router wiring and by the agent's hot
    #: prompt-building path, and `analysis/segment.py` and `analysis/anomaly.py`
    #: exist specifically to keep sklearn and pyod off the app-import path. A
    #: function reference here would import them at registration time and undo
    #: that silently; a string defers it to the first actual run.
    #:
    #: The handler's signature is `(df, **params) -> result`, which every
    #: analysis in this codebase already satisfies.
    handler: str | None = None

    #: Whether this analysis reads COLUMN ROLES, and therefore receives
    #: `column_meta` when dispatched. **No default, deliberately.**
    #:
    #: Before this field, `run_analysis` passed no roles at all and all 18
    #: runnable handlers would have raised TypeError if it had. The visible
    #: cost was Key influencers ranking `student_id` as a top driver: an
    #: identifier cut into quantile ranges, which describes row order rather
    #: than anything anyone can act on.
    #:
    #: The fix is not "hand it to everything". A paired t-test has no use for
    #: roles, and a parameter every handler accepts while most ignore it
    #: cannot be told apart from one that is consulted -- the same
    #: prose-instead-of-code failure the RLS choke-point pin exists to stop.
    #: So each analysis DECLARES, and `test_step_and_analysis_contracts`
    #: requires the declaration: a new analysis cannot be registered without
    #: someone deciding whether column kinds matter to it.
    #:
    #: `None` is "nobody decided", not a third behaviour: it cannot be a
    #: required field because `handler` above it already has a default, so the
    #: pin enforces what the dataclass cannot. A `None` here forwards nothing
    #: and fails the contract test by name.
    consumes_column_meta: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "params_schema": self.params_schema,
            "result_kind": self.result_kind,
            # Whether a generic caller can invoke it, without publishing the
            # import path -- that is internal wiring and names our layout.
            "runnable": self.handler is not None,
        }


class DuplicateAnalysisError(ValueError):
    """Two specs registered under the same name -- a programming error caught
    at import time, never a runtime/user-facing condition."""


class UnknownAnalysisError(KeyError):
    """No analysis is registered under that name."""


class NotRunnableError(ValueError):
    """The analysis exists in the catalogue but declares no handler.

    Deliberately distinct from `UnknownAnalysisError`: one means the caller
    made a typo, the other means the analysis is real but has no generic entry
    point yet. Collapsing them would send someone hunting for a spelling
    mistake that is not there.
    """


_REGISTRY: dict[str, AnalysisSpec] = {}


def register(spec: AnalysisSpec) -> AnalysisSpec:
    if spec.name in _REGISTRY:
        raise DuplicateAnalysisError(f"analysis '{spec.name}' already registered")
    _REGISTRY[spec.name] = spec
    return spec


def unregister(name: str) -> None:
    """Test-only symmetry for `register` -- lets a test add a fake analysis
    and clean up afterwards without reaching into `_REGISTRY` directly.
    Silently no-ops on an unknown name (idempotent teardown)."""
    _REGISTRY.pop(name, None)


_HANDLERS: dict[str, Any] = {}


def resolve_handler(spec: AnalysisSpec):
    """Import and cache the callable a spec names.

    Raises `NotRunnableError` for a catalogue-only entry, and lets an
    ImportError/AttributeError from a wrong path propagate -- a broken handler
    string is a programming error and should be loud, not silently unrunnable.
    """
    if not spec.handler:
        raise NotRunnableError(
            f"analysis '{spec.name}' is listed but has no handler to run")
    fn = _HANDLERS.get(spec.handler)
    if fn is None:
        from importlib import import_module
        module_path, _, attr = spec.handler.partition(":")
        fn = getattr(import_module(module_path), attr)
        _HANDLERS[spec.handler] = fn
    return fn


def run_analysis(name: str, df, params: dict[str, Any] | None = None,
                 column_meta: dict | None = None):
    """Run a registered analysis over an ALREADY SECURED frame.

    This performs no security of its own, by design: `df` must arrive from
    `routers/analysis.py::_secured_frame`, which applies row-level security,
    prep steps and column denial. A dispatcher that loaded data itself would be
    a second path to the data, and the one that gets forgotten is the one with
    the security on it.

    Always returns a plain dict. The handlers do not agree on that themselves:
    the inferential analyses return a `TestResult` dataclass and the three
    older ones return an `AnalysisContract`, while `explain_response` and
    `goal_seek` return dicts already. Every typed endpoint calls `.to_dict()`
    before answering -- which for `TestResult` rounds the statistic, rounds the
    p-value to six places and adds `alpha` -- so a dispatcher that handed the
    dataclass straight to the serializer would return DIFFERENT NUMBERS for the
    same analysis, and a missing key the reader needs to judge `significant`.
    It would also skip `safe_clean`'s NaN handling downstream, which walks
    dicts and lists and quietly does nothing to a dataclass.

    Narrowed to dataclasses deliberately: `to_dict` is a common method name --
    a pandas DataFrame has one, and calling it would silently reshape a result.
    """
    spec = get(name)
    if spec is None:
        raise UnknownAnalysisError(f"no analysis named '{name}'")
    call_params = dict(params or {})
    # Forwarded ONLY to a spec that declared it wants roles. Handing it to
    # every handler would mean 18 signature changes for a parameter most of
    # them would ignore, and an ignored parameter is indistinguishable from a
    # consulted one -- so the declaration is what makes this checkable.
    if spec.consumes_column_meta and column_meta is not None:
        call_params["column_meta"] = column_meta
    result = resolve_handler(spec)(df, **call_params)
    if dataclasses.is_dataclass(result) and hasattr(result, "to_dict"):
        return result.to_dict()
    return result


def all_analyses() -> list[AnalysisSpec]:
    """Registration order (dict insertion order) -- lets the static
    registrations below control display order (the default full-profile
    analysis first, then segment/forecast/anomaly), not an incidental sort."""
    return list(_REGISTRY.values())


def get(name: str) -> AnalysisSpec | None:
    return _REGISTRY.get(name)


# ── Static registrations ─────────────────────────────────────────────────────
# Descriptive metadata only, mirroring the REAL params each service accepts
# (SegmentRequest, shape_forecast's `method`/`forecast_periods` config keys,
# anomaly.detect's `detector`) without importing those services' code -- see
# the module docstring for why. A change to a service's actual default
# (anomaly.CONTAMINATION, segment.MAX_K, etc.) does not auto-propagate here;
# test_registry.py pins the numbers in this file against the real constants
# so drift is a failing test, not a silent lie.

register(AnalysisSpec(
    name="full_profile",
    description="Descriptive profile of a dataset: per-column type/stat "
                 "breakdown (numeric/categorical/datetime) plus an overview.",
    params_schema={
        "type": "object",
        "properties": {"analysis_type": {"type": "string", "default": "full"}},
    },
    consumes_column_meta=False,
    result_kind="full_profile",
))

register(AnalysisSpec(
    name="segment",
    description="KMeans clustering over selected numeric columns "
                 "(standardized), with k chosen automatically (2..8) by "
                 "silhouette score.",
    params_schema={
        "type": "object",
        "properties": {
            "columns": {"format": "column", 
                "type": ["array", "null"], "items": {"type": "string"},
                "description": "Numeric columns to cluster on; omitted/null "
                                "means every usable numeric column.",
            },
        },
    },
    consumes_column_meta=False,
    result_kind="segment",
    handler="app.services.analysis.segment:segment_dataframe",
))

register(AnalysisSpec(
    name="association_rules",
    description="Which values travel together: 'customers on the premium tier "
                 "also choose express shipping'. Reports lift (how many times "
                 "more often than chance), confidence, the base rate it must "
                 "be read against, and the supporting row count. "
                 "Co-occurrence, not causation.",
    params_schema={
        "type": "object",
        "properties": {
            "columns": {"format": "column", 
                "type": ["array", "null"], "items": {"type": "string"},
                "description": "Categorical columns to mine; omitted/null "
                                "means every usable categorical column.",
            },
        },
    },
    consumes_column_meta=False,
    result_kind="association_rules",
    handler="app.services.analysis.patterns:association_rules",
))

register(AnalysisSpec(
    name="key_influencers",
    description="Which factors move a chosen outcome, ranked by how far each "
                 "group's rate (or mean) sits from the dataset baseline. "
                 "Reports lift, supporting row count and a not-causation "
                 "caveat; correlational, not causal.",
    params_schema={
        "type": "object",
        "required": ["target"],
        "properties": {
            "target": {"format": "column", "type": "string",
                        "description": "The outcome column to explain."},
            "target_value": {
                "type": ["string", "null"],
                "description": "For a categorical target, the outcome of "
                                "interest. Defaults to the RAREST value -- "
                                "'what drives churn' is asked far more often "
                                "than 'what drives staying'.",
            },
            "factors": {
                "format": "column",
                "type": ["array", "null"], "items": {"type": "string"},
                "description": "Columns to consider; omitted/null means every "
                                "usable column except the target.",
            },
        },
    },
    consumes_column_meta=True,
    result_kind="key_influencers",
    handler="app.services.analysis.influencers:key_influencers",
))

register(AnalysisSpec(
    name="forecast_ets",
    description="Per-series time forecast via StatsForecast AutoETS, with a "
                 "95% prediction interval. Default forecasting method.",
    params_schema={
        "type": "object",
        "properties": {
            "method": {"type": "string", "const": "ets"},
            "forecast_periods": {"type": "integer",
                                  "minimum": FORECAST_MIN_PERIODS,
                                  "maximum": MAX_FORECAST_PERIODS,
                                  "default": DEFAULT_FORECAST_PERIODS},
        },
    },
    consumes_column_meta=False,
    result_kind="forecast",
))

register(AnalysisSpec(
    name="forecast_simple",
    description="Hand-rolled Holt-Winters ETS forecast (statsmodels), "
                 "falling back to naive linear-trend extrapolation for "
                 "short/unfittable series.",
    params_schema={
        "type": "object",
        "properties": {
            "method": {"type": "string", "const": "simple"},
            "forecast_periods": {"type": "integer",
                                  "minimum": FORECAST_MIN_PERIODS,
                                  "maximum": MAX_FORECAST_PERIODS,
                                  "default": DEFAULT_FORECAST_PERIODS},
        },
    },
    consumes_column_meta=False,
    result_kind="forecast",
))

register(AnalysisSpec(
    name="anomaly_iqr",
    description="Outlier flagging via 1.5x-IQR fences. Default detector, "
                 "unchanged from before PyOD detectors were added.",
    params_schema={
        "type": "object",
        "properties": {"detector": {"type": "string", "const": "iqr"}},
    },
    consumes_column_meta=False,
    result_kind="anomaly",
))

register(AnalysisSpec(
    name="anomaly_iforest",
    description="Outlier flagging via PyOD IsolationForest.",
    params_schema={
        "type": "object",
        "properties": {"detector": {"type": "string", "const": "iforest"}},
    },
    consumes_column_meta=False,
    result_kind="anomaly",
))

register(AnalysisSpec(
    name="anomaly_ecod",
    description="Outlier flagging via PyOD ECOD (empirical-CDF, "
                 "distribution-free outlier scoring).",
    params_schema={
        "type": "object",
        "properties": {"detector": {"type": "string", "const": "ecod"}},
    },
    consumes_column_meta=False,
    result_kind="anomaly",
))


#: Small and static (a handful of entries, never per-organization/per-schema)
#: -- generous enough that today's whole catalogue fits comfortably, while
#: still bounding a future catalogue from growing the prompt unboundedly.
#: The registry grew from 8 analyses to 12 when the inferential tests landed,
#: and 1,200 characters no longer fit them: the block dropped the last three
#: SILENTLY -- the tail marker itself did not fit either -- so the agent could
#: not know those analyses existed. An analysis the model cannot see is an
#: analysis that will never be suggested, which is the same unreachable-feature
#: trap as an endpoint with no caller.
#:
#: Raised rather than trimming descriptions further: the descriptions are what
#: tell the model WHEN to reach for each analysis, and a budget that forces them
#: to be uninformative defeats the block's purpose. Still bounded -- this is
#: prompt context, not documentation.
#: Raised again at 16 analyses. The renderer now ANNOUNCES truncation rather
#: than dropping entries silently, so this is a quality choice rather than a
#: correctness one -- but an analysis the model cannot see is one it will never
#: suggest, which is the same unreachable-capability trap in a different guise.
DEFAULT_PROMPT_MAX_CHARS = 4000


#: A sentence ends at . ? or ! followed by a space -- NOT at the dot inside
#: "0.62", which is why this is not a plain `split(".")`.
_SENTENCE_END = re.compile(r"(.+?[.?!])(?:\s|$)", re.S)


def _opening_sentence(description: str) -> str:
    """The first sentence, or the whole thing when there is only one.

    The block is capability DISCOVERY prefixed onto every SQL-generation call.
    These descriptions open with the question the analysis answers ("When will
    this reach a target?") and then explain themselves at length; the opening is
    what a model choosing between analyses needs, and the rest is for the panel,
    where a reader has already asked.

    Breadth before depth, the same rule `SchemaContext.render` follows: at 22
    analyses the full descriptions came to 4,055 characters on every request,
    which had already pushed the budget past its third raise. Trimming halves
    the block and drops no NAME, which is the part that must never be lost.
    """
    text = (description or "").strip()
    match = _SENTENCE_END.match(text)
    return match.group(1) if match else text


def render_prompt_block(max_chars: int = DEFAULT_PROMPT_MAX_CHARS) -> str:
    """Compact "Analyses available" block for the agent's SQL-generation
    prompt (services/agent/nodes/generate.py).

    Capability discovery, not an invocation contract: today's agent only
    writes SQL, so this is informational context -- it lets the model
    mention that a deeper analysis (forecast, segment, anomaly detection)
    exists via the dedicated endpoints, rather than trying to fake one in a
    SELECT. Because the registry is small and static, a simple
    length-capped join is enough here; it does not need the two-pass
    reserve-then-degrade machinery `SchemaContext.render` uses to bound a
    potentially large, per-request, per-source object catalog -- that
    machinery exists to guarantee breadth (every object's NAME survives)
    under a budget that varies request to request, a problem this fixed,
    handful-of-entries list does not have.
    """
    lines = [f"- {s.name}: {_opening_sentence(s.description)}"
             for s in all_analyses()]
    header = "Analyses available (beyond SQL):\n"

    kept: list[str] = []
    used = len(header)
    for line in lines:
        addition = len(line) + (1 if kept else 0)
        if used + addition > max_chars:
            omitted = len(lines) - len(kept)
            if omitted > 0:
                # The marker is NOT optional. It used to be appended only if it
                # happened to fit, so a budget just tight enough dropped entries
                # with nothing to say so -- the agent could not know an analysis
                # existed and no part of the output hinted at the omission.
                # Now the marker displaces kept lines until it fits: "there is
                # more" is the most important thing this block can say when it
                # cannot say everything.
                tail = f"(+{omitted} more)"
                while kept and used + len(tail) + 1 > max_chars:
                    dropped = kept.pop()
                    used -= len(dropped) + (1 if kept else 0)
                    omitted += 1
                    tail = f"(+{omitted} more)"
                if used + len(tail) + (1 if kept else 0) <= max_chars:
                    kept.append(tail)
            break
        kept.append(line)
        used += addition

    return header + "\n".join(kept)

# ── Inferential statistics ───────────────────────────────────────────────────
# The eight analyses above describe, forecast, cluster or flag. None answers
# "is this difference real?", which is the question a reader asks the moment a
# descriptive finding surprises them. scipy and statsmodels were already in the
# image, so these expose capability that was already paid for.
#
# Every one returns an EFFECT SIZE beside its p-value. With a two-million-row
# cap a p-value alone is nearly content-free -- at large n almost anything is
# "significant" -- so a result that reported only p would be a machine for
# manufacturing confident trivia.

register(AnalysisSpec(
    name="compare_groups",
    description="Is a measure genuinely different across groups? Welch's "
                "t-test or ANOVA, with p and an effect size.",
    params_schema={
        "type": "object",
        "required": ["value_col", "group_col"],
        "properties": {
            "value_col": {"format": "column", "type": "string",
                          "description": "The numeric measure to compare."},
            "group_col": {"format": "column", "type": "string",
                          "description": "The categorical column defining the groups."},
        },
    },
    consumes_column_meta=False,
    result_kind="statistical_test",
    handler="app.services.analysis.inferential:compare_groups",
))

register(AnalysisSpec(
    name="test_independence",
    description="Are two categorical columns related or independent? "
                "Chi-square with Cramer's V.",
    params_schema={
        "type": "object",
        "required": ["col_a", "col_b"],
        "properties": {
            "col_a": {"format": "column", "type": "string", "description": "First categorical column."},
            "col_b": {"format": "column", "type": "string", "description": "Second categorical column."},
        },
    },
    consumes_column_meta=False,
    result_kind="statistical_test",
    handler="app.services.analysis.inferential:test_independence",
))

register(AnalysisSpec(
    name="correlation_test",
    description="Do two measures move together, and is it distinguishable "
                "from noise? Pearson or Spearman with a p-value.",
    params_schema={
        "type": "object",
        "required": ["col_a", "col_b"],
        "properties": {
            "col_a": {"format": "column", "type": "string", "description": "First numeric column."},
            "col_b": {"format": "column", "type": "string", "description": "Second numeric column."},
            "method": {"type": "string", "enum": ["pearson", "spearman"],
                       "description": "pearson (linear) or spearman (rank/monotonic). "
                                      "Defaults to pearson."},
        },
    },
    consumes_column_meta=False,
    result_kind="statistical_test",
    handler="app.services.analysis.inferential:correlation_test",
))

register(AnalysisSpec(
    name="regression",
    description="Ordinary least squares: how much does each predictor move "
                "the target? Coefficient table with p, CIs and R squared.",
    params_schema={
        "type": "object",
        "required": ["target", "predictors"],
        "properties": {
            "target": {"format": "column", "type": "string",
                       "description": "The numeric column to explain."},
            "predictors": {"format": "column", "type": "array", "items": {"type": "string"},
                           "description": "Numeric columns used to explain it."},
        },
    },
    consumes_column_meta=False,
    result_kind="statistical_test",
    handler="app.services.analysis.inferential:regression",
))


register(AnalysisSpec(
    name="glm_logistic",
    description="Which factors move the odds of a yes/no outcome? Logistic "
                "regression with odds ratios and CIs.",
    params_schema={
        "type": "object",
        "required": ["target", "predictors"],
        "properties": {
            "target": {"format": "column", "type": "string",
                       "description": "The binary outcome column."},
            "predictors": {"format": "column", "type": "array", "items": {"type": "string"},
                           "description": "Numeric columns that may explain it."},
            "target_value": {
                "type": ["string", "null"],
                "description": "Which value counts as the event. Defaults to "
                               "the rarer one.",
            },
        },
    },
    consumes_column_meta=False,
    result_kind="statistical_test",
    handler="app.services.analysis.inferential:glm_logistic",
))

register(AnalysisSpec(
    name="mixed_model",
    description="Repeated measurements within groups (stores, patients, "
                "regions). Random-intercept model; reports the share of "
                "variation that is between groups.",
    params_schema={
        "type": "object",
        "required": ["target", "predictors", "group_col"],
        "properties": {
            "target": {"format": "column", "type": "string", "description": "The numeric outcome."},
            "predictors": {"format": "column", "type": "array", "items": {"type": "string"},
                           "description": "Numeric columns that may explain it."},
            "group_col": {"format": "column", "type": "string",
                          "description": "The column identifying each group."},
        },
    },
    consumes_column_meta=False,
    result_kind="statistical_test",
    handler="app.services.analysis.inferential:mixed_model",
))

register(AnalysisSpec(
    name="survival",
    description="What changes how LONG something takes? Cox proportional "
                "hazards; uses rows where the event has not happened yet "
                "instead of discarding them.",
    params_schema={
        "type": "object",
        "required": ["duration_col", "event_col", "predictors"],
        "properties": {
            "duration_col": {"format": "column", "type": "string",
                             "description": "How long each row was observed."},
            "event_col": {"format": "column", "type": "string",
                          "description": "1 where the event happened, 0 where "
                                         "it has not yet (censored)."},
            "predictors": {"format": "column", "type": "array", "items": {"type": "string"},
                           "description": "Numeric columns that may change the timing."},
        },
    },
    consumes_column_meta=False,
    result_kind="statistical_test",
    handler="app.services.analysis.inferential:survival",
))

register(AnalysisSpec(
    name="pairwise_comparisons",
    description="After an ANOVA, which PAIRS of groups actually differ? "
                "Pairwise Welch tests with the p-values adjusted for the "
                "number of comparisons.",
    params_schema={
        "type": "object",
        "required": ["value_col", "group_col"],
        "properties": {
            "value_col": {"format": "column", "type": "string", "description": "The numeric measure."},
            "group_col": {"format": "column", "type": "string",
                          "description": "The categorical column defining groups."},
            "method": {"type": "string", "enum": ["holm", "bonferroni", "fdr_bh"],
                       "description": "Correction method. Defaults to holm."},
        },
    },
    consumes_column_meta=False,
    result_kind="statistical_test",
    handler="app.services.analysis.inferential:pairwise_comparisons",
))

# ── The two that shipped outside the catalogue ───────────────────────────────
# Both of these were built, tested and reachable from exactly one dialog each,
# and neither was listed here -- so `GET /analysis/registry` did not mention
# them, the generic statistics panel could not drive them, and the agent's
# prompt block (rendered from this catalogue) did not know the platform could
# do either. `goal_seek`'s arithmetic lived inside a router function and has
# been extracted to a service so a name can point at it.

register(AnalysisSpec(
    name="explain_response",
    description="Which columns move a chosen response, ranked on one 0-1 "
                "scale (|Pearson r| for numeric factors, the correlation "
                "ratio for categorical ones). The top factor scores 1 and the "
                "rest are proportional to it, and the strongest relationship "
                "comes back as plottable data. Association, not causation.",
    params_schema={
        "type": "object",
        "required": ["response"],
        "properties": {
            "response": {"format": "column", "type": "string",
                         "description": "The numeric column to explain."},
        },
    },
    consumes_column_meta=False,
    result_kind="explanation",
    handler="app.services.explain:explain_response",
))

register(AnalysisSpec(
    name="goal_seek",
    description="Work backwards from a target: on a linear fit of y ~ x, "
                "solve for the x value that reaches a wanted y. Reports the "
                "fit's r-squared and whether the answer lies inside the "
                "observed data or is an extrapolation. Optional bounds on x "
                "report infeasibility plus the best y reachable at the "
                "binding bound.",
    params_schema={
        "type": "object",
        "required": ["x_column", "y_column", "target_y"],
        "properties": {
            "x_column": {"format": "column", "type": "string",
                         "description": "The numeric factor to solve for."},
            "y_column": {"format": "column", "type": "string",
                         "description": "The numeric outcome being targeted."},
            "target_y": {"type": "number",
                         "description": "The value of y you want to reach."},
            "x_min": {"type": ["number", "null"],
                      "description": "Lowest x considered achievable."},
            "x_max": {"type": ["number", "null"],
                      "description": "Highest x considered achievable."},
        },
    },
    consumes_column_meta=False,
    result_kind="goal_seek",
    handler="app.services.analysis.goal_seek:goal_seek",
))


register(AnalysisSpec(
    name="forecast_goal",
    description="When will this reach a target? Projects a series forward and "
                "reports the period its forecast crosses the value you name -- "
                "with the soonest and latest the prediction band allows, and, "
                "when the series has been there before, the period it first "
                "was. Answers 'not within the horizon' with how far short the "
                "projection ends, rather than just no.",
    params_schema={
        "type": "object",
        "required": ["date_column", "measure", "target"],
        "properties": {
            "date_column": {"format": "column", "type": "string",
                            "description": "The date column to project along."},
            "measure": {"format": "column", "type": "string",
                        "description": "The numeric column being projected."},
            "target": {"type": "number",
                       "description": "The value you want the series to reach."},
            "aggregation": {"type": "string",
                            "description": "How to total each period. Defaults to sum."},
            "granularity": {"type": "string",
                            "enum": ["day", "week", "month", "quarter", "year"],
                            "description": "Period size. Defaults to month."},
            "forecast_periods": {
                "type": ["integer", "null"],
                # Pinned to shape_forecast's real clamps by
                # test_forecast_periods_bounds_match_shape_forecast: a schema
                # that advertised a horizon the shaper silently clamps would
                # promise a projection nobody gets.
                "minimum": FORECAST_MIN_PERIODS,
                "maximum": MAX_FORECAST_PERIODS,
                "default": DEFAULT_FORECAST_PERIODS,
                "description": "How far ahead to project."},
        },
    },
    consumes_column_meta=False,
    result_kind="forecast_goal",
    handler="app.services.analysis.forecast_goal:forecast_goal_over",
))


register(AnalysisSpec(
    name="decision_tree",
    description="The rules that separate one outcome from another: a shallow, "
                "readable tree, scored on rows it never saw. Says which "
                "splits matter, how many rows take each branch, and what it "
                "predicts at the end -- 'margin below 12% and Wholesale: three "
                "quarters churn'. Association, not causation.",
    params_schema={
        "type": "object",
        "required": ["target"],
        "properties": {
            "target": {"format": "column", "type": "string",
                       "description": "The outcome to explain. Categorical "
                                      "gives a classification tree, numeric a "
                                      "regression tree."},
            "predictors": {"format": "column",
                           "type": ["array", "null"], "items": {"type": "string"},
                           "description": "Columns to split on; omitted means "
                                          "every usable column."},
            "max_depth": {"type": ["integer", "null"], "minimum": 1,
                          "maximum": HARD_TREE_DEPTH,
                          "default": DEFAULT_TREE_DEPTH,
                          "description": "How many levels deep. Deeper trees "
                                         "fit better and explain less."},
        },
    },
    # False for now: it has its own level-count rule and does not read
    # roles yet. Flipping this to True without adding the parameter is
    # caught by test_step_and_analysis_contracts.
    consumes_column_meta=False,
    result_kind="decision_tree",
    handler="app.services.analysis.decision_tree:decision_tree",
))


register(AnalysisSpec(
    name="automated_prediction",
    description="Which model predicts this outcome best? Fits several "
                "candidates -- a tree, a forest, a linear or logistic model -- "
                "on ONE shared split and names the winner. Always runs a "
                "'just guess' baseline too, and says plainly when the winner "
                "does not beat it. Nothing is saved: this answers what can be "
                "predicted and how well, not 'score these new rows'.",
    params_schema={
        "type": "object",
        "required": ["target"],
        "properties": {
            "target": {"format": "column", "type": "string",
                       "description": "The outcome to predict."},
            "predictors": {"format": "column",
                           "type": ["array", "null"], "items": {"type": "string"},
                           "description": "Columns to predict from; omitted "
                                          "means every usable column."},
            "partition": {"format": "column", "type": ["string", "null"],
                          "description": "A Training/Validation column (the prep "
                                         "Partition step) to split by, instead of a "
                                         "random 25%."},
        },
    },
    # False for now: it has its own level-count rule and does not read
    # roles yet. Flipping this to True without adding the parameter is
    # caught by test_step_and_analysis_contracts.
    consumes_column_meta=False,
    result_kind="automated_prediction",
    handler="app.services.analysis.automated_prediction:automated_prediction",
))


register(AnalysisSpec(
    name="text_topics",
    description="What is this free text about? Clusters a column of comments "
                "into topics, each with the words that define it and the "
                "comments behind it, and each topic's average tone. A topic "
                "is a cluster of words, not a label -- naming it is your "
                "judgement. Arabic, English, French, Spanish and German "
                "common words are removed after detecting the language.",
    params_schema={
        "type": "object",
        "required": ["column"],
        "properties": {
            "column": {"format": "column", "type": "string",
                       "description": "The free-text column: comments, "
                                      "descriptions, notes."},
            "topics": {"type": ["integer", "null"], "minimum": 2,
                       "maximum": MAX_TEXT_TOPICS, "default": DEFAULT_TEXT_TOPICS,
                       "description": "How many clusters to look for."},
            "max_terms": {"type": ["integer", "null"], "minimum": 3, "maximum": 25,
                          "description": "Words shown per topic."},
            "stop_words": {"type": ["array", "null"], "items": {"type": "string"},
                           "description": "Extra words to ignore -- the escape "
                                          "hatch for another language, or a "
                                          "domain word that swamps every topic."},
            "language": {"type": "string",
                         "enum": ["auto", "ar", "en", "fr", "es", "de"],
                         "default": "auto",
                         "description": "Whose common words to remove: auto "
                                        "detects from the text (a bilingual "
                                        "column gets both lists)."},
        },
    },
    consumes_column_meta=False,
    result_kind="text_topics",
    handler="app.services.analysis.text_topics:text_topics",
))


register(AnalysisSpec(
    name="text_sentiment",
    description="How do people feel in this free text? Scores each comment "
                "positive, neutral or negative from an English + Arabic "
                "lexicon with negation and intensifiers, shows the words that "
                "drove it, splits by a group, and -- given a column that "
                "already holds a rating or label -- reports how often it "
                "agrees. Comments with no scored word stay unscored.",
    params_schema={
        "type": "object",
        "required": ["column"],
        "properties": {
            "column": {"format": "column", "type": "string",
                       "description": "The free-text column: comments, reviews."},
            "group_by": {"format": "column", "type": ["string", "null"],
                         "description": "Compare tone across this column's "
                                        "values (branch, product, month)."},
            "validate_against": {"format": "column", "type": ["string", "null"],
                                 "description": "A column that already holds "
                                                "sentiment labels or 1-5 ratings, "
                                                "to measure agreement."},
        },
    },
    consumes_column_meta=False,
    result_kind="text_sentiment",
    handler="app.services.analysis.text_sentiment:text_sentiment",
))


register(AnalysisSpec(
    name="forecast_scenario",
    description="What if a factor changed? Projects a measure forward from a "
                "fit on time plus the factors you name, then again with the "
                "factors moved by a percentage -- and reports the difference. "
                "Each factor carries its own p-value, and a scenario that "
                "leaves the observed range is named as an extrapolation. "
                "Association, not intervention.",
    params_schema={
        "type": "object",
        "required": ["date_column", "measure", "factors"],
        "properties": {
            "date_column": {"format": "column", "type": "string",
                            "description": "The date column to project along."},
            "measure": {"format": "column", "type": "string",
                        "description": "The numeric column being projected."},
            "factors": {"format": "column",
                        "type": "array", "items": {"type": "string"},
                        "description": "Numeric columns that may move it."},
            "adjustments": {"type": ["object", "null"],
                            "description": "Per-factor change as a fraction: "
                                           "{\"spend\": 0.1} is +10%."},
            "periods": {"type": ["integer", "null"], "minimum": 1,
                        "maximum": MAX_SCENARIO_HORIZON,
                        "default": DEFAULT_SCENARIO_HORIZON,
                        "description": "How far ahead to project."},
            "granularity": {"type": "string",
                            "enum": ["day", "week", "month", "quarter", "year"],
                            "description": "Period size. Defaults to month."},
        },
    },
    consumes_column_meta=False,
    result_kind="forecast_scenario",
    handler="app.services.analysis.forecast_scenario:forecast_scenario",
))
