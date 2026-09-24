"""The agent stops writing SQL for questions that are not SQL questions.

`render_prompt_block`'s own docstring says the catalogue is "capability
discovery, not an invocation contract: today's agent only writes SQL." So "is
revenue really different across regions?" became a GROUP BY returning four
averages -- which is the arithmetic, not the answer. Whether those four numbers
differ by more than chance is a t-test, and the platform has had one for months.

Two intents route to two analyses. Not more, deliberately: `compare` and
`explain` are the two whose SQL answer is most obviously the wrong shape, and
proving the seam on two is what makes the third cheap.

The column choice is the hard part, and it is made SAFE rather than clever: the
model chooses from an enum built out of the frame's own columns. It cannot name
a column that does not exist, and -- because dataset mode drops denied columns
from the frame before anything sees it -- it cannot name one this user is not
allowed to see. Anything the model gets wrong anyway falls through to SQL, which
is the behaviour of the day before this existed.
"""
import pandas as pd
import pytest

from app.services.agent.nodes.analyze import (ANALYSIS_FOR_INTENT,
                                              choose_analysis)


@pytest.fixture
def frame():
    return pd.DataFrame({
        "region": ["north", "south"] * 20,
        "product": ["a", "b", "c", "d"] * 10,
        "revenue": list(range(40)),
        "units": [i * 2 for i in range(40)],
    })


class FakeClient:
    """Records what it was asked and answers with whatever it was given."""

    def __init__(self, reply=None):
        self.reply = reply
        self.calls: list[tuple[list[dict], dict]] = []

    async def complete_json(self, messages, schema, **kw):
        self.calls.append((messages, schema))
        return self.reply


class TestItPicksTheRightAnalysis:
    async def test_compare_becomes_a_group_comparison(self, frame):
        client = FakeClient({"value_col": "revenue", "group_col": "region"})
        got = await choose_analysis("is revenue different across regions?",
                                    "compare", frame, client)
        assert got["analysis"] == "compare_groups"
        assert got["params"] == {"value_col": "revenue", "group_col": "region"}

    async def test_explain_becomes_an_explanation(self, frame):
        client = FakeClient({"response": "revenue"})
        got = await choose_analysis("what drives revenue?", "explain",
                                    frame, client)
        assert got["analysis"] == "explain_response"
        assert got["params"] == {"response": "revenue"}

    def test_only_two_intents_are_routed(self):
        """`aggregate`, `trend` and `lookup` are genuinely SQL questions --
        routing them would replace a correct answer with a worse one."""
        assert set(ANALYSIS_FOR_INTENT) == {"compare", "explain"}


class TestTheModelCannotNameAColumnThatIsNotThere:
    """The whole safety argument. The enum is built from the frame, and the
    frame has already had row-level security applied and denied columns
    dropped, so an invented or forbidden column is not on the menu."""

    async def test_the_choices_offered_are_the_frames_own_columns(self, frame):
        client = FakeClient({"value_col": "revenue", "group_col": "region"})
        await choose_analysis("q", "compare", frame, client)
        _, schema = client.calls[0]
        assert set(schema["properties"]["value_col"]["enum"]) == {"revenue", "units"}
        assert set(schema["properties"]["group_col"]["enum"]) == {"region", "product"}

    async def test_a_column_missing_from_the_frame_is_refused(self, frame):
        """Belt and braces: `enforce=True` should make this impossible, but a
        model reply is still untrusted input, and running an analysis on a
        column nobody offered is exactly the failure the enum exists to
        prevent."""
        client = FakeClient({"value_col": "salary", "group_col": "region"})
        assert await choose_analysis("q", "compare", frame, client) is None

    async def test_a_denied_column_is_absent_because_the_frame_is(self):
        """Column security is structural here rather than a check: dataset mode
        drops the denied columns from the frame before the agent sees it, so
        they never reach the enum. This pins that the enum is derived from the
        frame and nothing else -- a future version reading the dataset's full
        column list instead would reopen the hole silently."""
        secured = pd.DataFrame({"region": ["n", "s"] * 10,
                                "revenue": list(range(20))})
        client = FakeClient({"value_col": "revenue", "group_col": "region"})
        await choose_analysis("q", "compare", secured, client)
        _, schema = client.calls[0]
        assert "salary" not in schema["properties"]["value_col"]["enum"]


class TestItFallsThroughRatherThanFailing:
    """Every refusal returns None, and None means "answer it with SQL, as
    before". A question the analysis path cannot serve must still get an
    answer."""

    async def test_the_model_returning_nothing_falls_through(self, frame):
        assert await choose_analysis("q", "compare", frame,
                                     FakeClient(None)) is None

    async def test_a_reply_missing_a_required_field_falls_through(self, frame):
        client = FakeClient({"value_col": "revenue"})
        assert await choose_analysis("q", "compare", frame, client) is None

    async def test_an_intent_with_no_analysis_falls_through(self, frame):
        client = FakeClient({"value_col": "revenue", "group_col": "region"})
        assert await choose_analysis("q", "aggregate", frame, client) is None
        assert not client.calls, "the model should not be asked at all"

    async def test_no_numeric_column_falls_through_without_asking(self):
        """'why did returns spike' against a frame of names and dates has no
        response to explain. Deciding that here costs nothing; asking the model
        costs a round trip to reach the same answer."""
        text_only = pd.DataFrame({"name": ["a", "b"], "note": ["x", "y"]})
        client = FakeClient({"response": "name"})
        assert await choose_analysis("why did returns spike", "explain",
                                     text_only, client) is None
        assert not client.calls

    async def test_no_categorical_column_falls_through_for_compare(self):
        numeric_only = pd.DataFrame({"a": range(20), "b": range(20)})
        client = FakeClient({"value_col": "a", "group_col": "b"})
        assert await choose_analysis("q", "compare", numeric_only, client) is None
        assert not client.calls

    async def test_a_frame_too_small_to_test_falls_through(self):
        """`compare_groups` refuses under ten rows per group. Reaching it only
        to be refused turns a working SQL answer into an error message."""
        tiny = pd.DataFrame({"region": ["n", "s"], "revenue": [1.0, 2.0]})
        client = FakeClient({"value_col": "revenue", "group_col": "region"})
        assert await choose_analysis("q", "compare", tiny, client) is None
        assert not client.calls


class TestTheQuestionReachesTheModel:
    async def test_the_question_is_in_the_prompt(self, frame):
        client = FakeClient({"value_col": "revenue", "group_col": "region"})
        await choose_analysis("is revenue different across regions?",
                              "compare", frame, client)
        messages, _ = client.calls[0]
        assert any("is revenue different across regions?" in m["content"]
                   for m in messages)

    async def test_it_is_asked_under_a_constrained_grammar(self, frame):
        """Without `enforce`, a chatty reply is a parse failure that falls
        through to SQL -- the feature would work only sometimes, which is
        worse than not working."""
        seen = {}

        class Recorder(FakeClient):
            async def complete_json(self, messages, schema, **kw):
                seen.update(kw)
                return await super().complete_json(messages, schema, **kw)

        await choose_analysis("q", "compare", frame,
                              Recorder({"value_col": "revenue",
                                        "group_col": "region"}))
        assert seen.get("enforce") is True
        assert seen.get("temperature") == 0.0
