"""Question -> step DAG: the prompt-level rules pinned here, plus the
single-step fallback the planner degrades to on any failure.

Live Q24: "Which 5 students placed the most symbols — and how many did
each place?" kept being split into a compute step (GROUP BY + ORDER BY +
LIMIT — the complete golden answer) and a fragile lookup/format step. The
question is structurally ONE query; the system prompt must say so with a
concrete shape, not just "most questions are one step".
"""
from app.services.agent.context import SchemaContext
from app.services.agent.plan import PLAN_SCHEMA, plan_steps


def ctx():
    return SchemaContext(source_id=1, family="postgresql")


class FakeClient:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    async def complete_json(self, messages, schema, **kw):
        self.calls.append({"messages": messages, "schema": schema, **kw})
        return self.reply


class TestPlanPrompt:
    async def test_the_prompt_names_the_ranking_plus_measure_shape(self):
        client = FakeClient({"steps": [
            {"id": "s1", "question": "q", "depends_on": []}]})
        await plan_steps("which 5 students placed the most symbols and "
                         "how many did each place", "aggregate", ctx(), client)
        system_text = client.calls[0]["messages"][0]["content"]
        assert "which X ... and how many/much ...\") is ONE SQL query" in system_text
        assert "GROUP BY the entity, aggregate the measure, ORDER BY it, LIMIT N" in system_text
        assert "never a compute step followed by a lookup/format step" in system_text

    async def test_the_prompt_still_names_the_legitimate_decompose_cases(self):
        client = FakeClient({"steps": [
            {"id": "s1", "question": "q", "depends_on": []}]})
        await plan_steps("q", "aggregate", ctx(), client)
        system_text = client.calls[0]["messages"][0]["content"]
        assert ("a DIFFERENT table's data that cannot be reached via the "
               "allowed joins") in system_text
        assert "genuinely separate computation" in system_text

    async def test_the_schema_is_unchanged_at_one_to_six_steps(self):
        assert PLAN_SCHEMA["properties"]["steps"]["minItems"] == 1
        assert PLAN_SCHEMA["properties"]["steps"]["maxItems"] == 6


class TestPlanFallback:
    async def test_a_null_reply_falls_back_to_a_single_step(self):
        steps = await plan_steps("total sales", "aggregate", ctx(),
                                 FakeClient(None))
        assert len(steps) == 1
        assert steps[0].id == "s1"
        assert steps[0].question == "total sales"
        assert steps[0].depends_on == []

    async def test_a_cyclic_plan_falls_back_to_a_single_step(self):
        client = FakeClient({"steps": [
            {"id": "s1", "question": "a", "depends_on": ["s2"]},
            {"id": "s2", "question": "b", "depends_on": ["s1"]},
        ]})
        steps = await plan_steps("q", "aggregate", ctx(), client)
        assert len(steps) == 1
        assert steps[0].id == "s1"
        assert steps[0].question == "q"

    async def test_a_valid_multi_step_plan_passes_through(self):
        client = FakeClient({"steps": [
            {"id": "s1", "question": "a", "depends_on": []},
            {"id": "s2", "question": "b", "depends_on": ["s1"]},
        ]})
        steps = await plan_steps("q", "aggregate", ctx(), client)
        assert [s.id for s in steps] == ["s1", "s2"]
        assert steps[1].depends_on == ["s1"]
