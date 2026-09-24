"""A4: analysis tool catalogue -- registry contents, the endpoint, and the
single-source-of-truth guarantee that a registration shows up both in the
endpoint's response and the agent's prompt block.
"""
import pytest

from app.services.analysis import registry


class TestRegistryContents:
    def test_contains_every_registered_analysis(self):
        """An exact set, not a subset: this catalogue is what the UI renders
        AND what the agent's prompt advertises, so an analysis that lands in
        the code without landing here is invisible to both."""
        names = {s.name for s in registry.all_analyses()}
        assert names == {
            "full_profile", "segment", "key_influencers",
            # Pattern mining: the one question no other analysis reaches --
            # correlation needs two numeric columns, key influencers needs a
            # chosen outcome, and neither can say two VALUES co-occur.
            "association_rules",
            "forecast_ets", "forecast_simple",
            "anomaly_iqr", "anomaly_iforest", "anomaly_ecod",
            # Two that shipped reachable from one dialog each and were never
            # catalogued -- so the endpoint, the generic panel and the agent
            # all believed the platform could not do them.
            "explain_response", "goal_seek",
            # "When will this reach X?" -- goal-seek along a forecast rather
            # than across two columns.
            "forecast_goal",
            # The rules that separate one outcome from another --
            # sklearn, lazily imported like its two siblings.
            "decision_tree",
            # Several candidates on one split, with a "just guess"
            # baseline that decides whether the winner earned it.
            "automated_prediction",
            # Topics from free text: NMF over TF-IDF, no new dependency.
            "text_topics",
            # Tone from free text: an English + Arabic lexicon with negation,
            # coverage stated, agreement with a label column when there is one.
            "text_sentiment",
            # The other half of forecast what-if: factors you can move.
            "forecast_scenario",
            # Inferential statistics. Adding these caught the prompt block
            # silently dropping its last entries: 12 analyses no longer fit the
            # old 1,200-character budget, and the tail marker did not fit
            # either, so three were invisible to the agent with nothing to say
            # so. The budget was raised rather than the descriptions gutted --
            # the descriptions are what tell the model when to reach for each.
            "compare_groups", "test_independence",
            "correlation_test", "regression",
            # Advanced models. Adding these hit the budget again at 16 -- but
            # this time the block SAID it had truncated instead of dropping
            # entries silently, which is the difference between a visible
            # limit and a vanished capability.
            "glm_logistic", "mixed_model", "survival", "pairwise_comparisons",
        }

    def test_every_spec_has_required_fields(self):
        for spec in registry.all_analyses():
            assert spec.name
            assert spec.description
            assert spec.result_kind
            assert spec.params_schema["type"] == "object"
            assert "properties" in spec.params_schema

    def test_segment_params_schema_matches_segment_request(self):
        spec = registry.get("segment")
        assert spec.result_kind == "segment"
        assert "columns" in spec.params_schema["properties"]

    def test_forecast_variants_pin_method_and_result_kind(self):
        ets, simple = registry.get("forecast_ets"), registry.get("forecast_simple")
        assert ets.params_schema["properties"]["method"]["const"] == "ets"
        assert simple.params_schema["properties"]["method"]["const"] == "simple"
        assert ets.result_kind == simple.result_kind == "forecast"

    def test_anomaly_detectors_match_the_real_detector_constant(self):
        from app.services.analysis.anomaly import DETECTORS
        registered = {
            spec.params_schema["properties"]["detector"]["const"]
            for name, spec in
            ((n, registry.get(n)) for n in ("anomaly_iqr", "anomaly_iforest", "anomaly_ecod"))
        }
        assert registered == set(DETECTORS)

    def test_get_unknown_returns_none(self):
        assert registry.get("does-not-exist") is None

    def test_duplicate_registration_raises(self):
        spec = registry.get("segment")
        with pytest.raises(registry.DuplicateAnalysisError):
            registry.register(spec)


class TestPromptBlock:
    def test_renders_all_analyses_by_default(self):
        text = registry.render_prompt_block()
        for spec in registry.all_analyses():
            assert spec.name in text

    def test_stays_under_its_cap(self):
        text = registry.render_prompt_block(max_chars=300)
        assert len(text) <= 300

    def test_cap_truncation_notes_omitted_count(self):
        # A cap too small for even one full entry still returns *something*
        # under budget, never raises.
        text = registry.render_prompt_block(max_chars=40)
        assert len(text) <= 40


class TestRegistryEndpointAuth:
    async def test_requires_auth(self, client):
        resp = await client.get("/api/v1/analysis/registry")
        assert resp.status_code in (401, 403)

    async def test_authenticated_lists_registered_analyses(self, client, auth_headers):
        resp = await client.get("/api/v1/analysis/registry", headers=auth_headers["a"])
        assert resp.status_code == 200
        body = resp.json()
        names = {a["name"] for a in body["analyses"]}
        assert "segment" in names and "anomaly_iforest" in names

    async def test_any_authenticated_org_can_read_it(self, client, auth_headers):
        # No admin gate, no org-scoped data -- org "b" reads the exact same
        # global catalogue as org "a".
        resp_a = await client.get("/api/v1/analysis/registry", headers=auth_headers["a"])
        resp_b = await client.get("/api/v1/analysis/registry", headers=auth_headers["b"])
        assert resp_a.status_code == resp_b.status_code == 200
        assert resp_a.json() == resp_b.json()


class TestSingleSourceOfTruth:
    """Registering a fake analysis makes it appear BOTH in the endpoint's
    response and in the agent's rendered prompt block, because both render
    from the same `all_analyses()` call."""

    @pytest.fixture(autouse=True)
    def fake_analysis(self):
        spec = registry.AnalysisSpec(
            name="__test_fake_analysis__",
            description="A fake analysis registered only for this test.",
            params_schema={"type": "object", "properties": {}},
            result_kind="fake",
        )
        registry.register(spec)
        yield spec
        registry.unregister(spec.name)

    async def test_appears_in_endpoint(self, client, auth_headers):
        resp = await client.get("/api/v1/analysis/registry", headers=auth_headers["a"])
        names = {a["name"] for a in resp.json()["analyses"]}
        assert "__test_fake_analysis__" in names

    def test_appears_in_prompt_block(self):
        text = registry.render_prompt_block(max_chars=100_000)
        assert "__test_fake_analysis__" in text

    async def test_appears_in_generate_sql_prompt(self):
        from app.services.agent.context import SchemaContext
        from app.services.agent.nodes.generate import generate_sql

        class FakeClient:
            def __init__(self):
                self.calls = []

            async def complete_json(self, messages, schema, **kw):
                self.calls.append(messages)
                return {"sql": "SELECT 1"}

        ctx = SchemaContext(source_id=1, family="postgresql")
        client = FakeClient()
        await generate_sql("q", ctx, [], client)
        text = "".join(m["content"] for m in client.calls[0])
        assert "__test_fake_analysis__" in text


def test_forecast_periods_bounds_match_shape_forecast():
    """The registry's forecast params schema is pinned to widget_data's real
    clamp constants -- a clamp change without a registry change fails here."""
    from app.services.widget_data import (DEFAULT_FORECAST_PERIODS,
                                          FORECAST_MIN_PERIODS,
                                          MAX_FORECAST_PERIODS)
    from app.services.analysis.registry import all_analyses

    for spec in all_analyses():
        props = spec.params_schema.get("properties", {})
        fp = props.get("forecast_periods")
        if fp is not None:
            assert fp["minimum"] == FORECAST_MIN_PERIODS
            assert fp["maximum"] == MAX_FORECAST_PERIODS
            assert fp["default"] == DEFAULT_FORECAST_PERIODS


class TestTruncationIsNeverSilent:
    """Adding the inferential analyses pushed the block past its budget and it
    dropped the last three with NO marker -- the tail only appeared if it
    happened to fit. The agent could not know those analyses existed, and
    nothing in the output hinted at the omission. A truncation that announces
    itself is recoverable; a silent one is a capability that has vanished."""

    def test_a_tight_budget_still_says_there_is_more(self):
        # The exact budget that used to fail: enough for most entries, not
        # enough for the marker after them.
        block = registry.render_prompt_block(1200)
        assert "more)" in block

    def test_every_budget_that_truncates_says_so(self):
        full = registry.render_prompt_block()
        for budget in (60, 200, 600, 900, 1200, 1400):
            block = registry.render_prompt_block(budget)
            if len(block) < len(full):
                assert "more)" in block, f"silent truncation at {budget} chars"

    def test_the_block_never_exceeds_its_budget(self):
        for budget in (60, 200, 600, 900, 1200, 1400, 2000):
            assert len(registry.render_prompt_block(budget)) <= budget

    def test_an_untruncated_block_has_no_marker(self):
        """The marker must mean something: it appears only when entries were
        actually dropped."""
        assert "more)" not in registry.render_prompt_block(10_000)


class TestThePromptBlockStaysAffordable:
    """The block is capability DISCOVERY, and it is prefixed onto every
    SQL-generation call.

    Its budget has now been raised three times -- 2600, 3400, 4000 -- each time
    because another analysis was registered, and at 22 analyses the full
    descriptions came to 4,055 characters of prompt on every request. Raising
    the number a fourth time treats the symptom.

    The descriptions here open with the question the analysis answers ("When
    will this reach a target?", "Which model predicts this outcome best?") and
    then explain themselves at length. The opening sentence is what capability
    discovery needs; the rest is for the panel, where a reader has asked. So the
    block carries FIRST SENTENCES -- the same breadth-before-depth rule
    `SchemaContext.render` already follows, where pass one never drops a name.
    """

    def test_every_analysis_still_appears(self):
        from app.services.analysis.registry import all_analyses, render_prompt_block
        text = render_prompt_block()
        for spec in all_analyses():
            assert spec.name in text

    def test_it_is_far_under_the_cap_now(self):
        from app.services.analysis.registry import (DEFAULT_PROMPT_MAX_CHARS,
                                                    render_prompt_block)
        text = render_prompt_block()
        assert len(text) < DEFAULT_PROMPT_MAX_CHARS * 0.75, (
            "the block has crept back up -- shorten the opening sentences "
            "rather than raising the cap again")

    def test_a_long_description_is_cut_at_its_first_sentence(self):
        from app.services.analysis import registry
        spec = registry.AnalysisSpec(
            name="_verbose", result_kind="x", params_schema={"type": "object"},
            description="The short answer. Then several more sentences that a "
                        "reader wants when they have asked for this analysis, "
                        "and that a model choosing between analyses does not.")
        registry.register(spec)
        try:
            text = registry.render_prompt_block()
            assert "- _verbose: The short answer." in text
            assert "Then several more" not in text
        finally:
            registry.unregister("_verbose")

    def test_a_description_with_no_full_stop_survives_whole(self):
        from app.services.analysis import registry
        registry.register(registry.AnalysisSpec(
            name="_terse", result_kind="x", params_schema={"type": "object"},
            description="No trailing punctuation here"))
        try:
            assert "- _terse: No trailing punctuation here" in registry.render_prompt_block()
        finally:
            registry.unregister("_terse")

    def test_a_question_mark_ends_a_sentence_too(self):
        # Most of these descriptions open with a question, so this is the
        # common case rather than an edge one.
        from app.services.analysis import registry
        registry.register(registry.AnalysisSpec(
            name="_asks", result_kind="x", params_schema={"type": "object"},
            description="When will this reach a target? A longer explanation."))
        try:
            text = registry.render_prompt_block()
            assert "- _asks: When will this reach a target?" in text
            assert "A longer explanation" not in text
        finally:
            registry.unregister("_asks")

    def test_a_decimal_point_does_not_end_a_sentence(self):
        # "beats 0.5 of the time." must not truncate at "0."
        from app.services.analysis import registry
        registry.register(registry.AnalysisSpec(
            name="_decimal", result_kind="x", params_schema={"type": "object"},
            description="Wins 0.62 of the time. And more besides."))
        try:
            assert "- _decimal: Wins 0.62 of the time." in registry.render_prompt_block()
        finally:
            registry.unregister("_decimal")
