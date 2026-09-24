"""Intent + the D4.3 rule: clarify when ambiguous, never guess.

A wrong confident answer destroys trust faster than a question costs
patience (spec / ARCHITECTURE.md D4.3). The tests fake the client — what is
under test is the CONTRACT: the schema sent, enforce=True, and honest None
propagation.
"""
from app.services.agent.context import ObjectInfo, SchemaContext
from app.services.agent.nodes.classify import CLASSIFY_SCHEMA, classify
from app.services.agent.nodes.clarify import clarify


def ctx():
    c = SchemaContext(source_id=1, family="postgresql")
    c.objects["orders"] = ObjectInfo("orders", "table", None,
                                     {"id": "integer", "total": "numeric"})
    return c


class FakeClient:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    async def complete_json(self, messages, schema, **kw):
        self.calls.append({"messages": messages, "schema": schema, **kw})
        return self.reply

    async def complete(self, messages, **kw):
        self.calls.append({"messages": messages, **kw})
        return self.reply if isinstance(self.reply, str) else None


class TestClassify:
    async def test_returns_the_models_verdict(self):
        client = FakeClient({"intent": "aggregate", "ambiguous": False,
                             "ambiguity_reason": None})
        got = await classify("total sales by city", ctx(), client)
        assert got["intent"] == "aggregate"
        assert got["ambiguous"] is False

    async def test_uses_the_enforced_contract(self):
        """F2: grammar enforcement is the only mechanism that held up under
        adversarial probing. Prompt-begging alone is not a contract."""
        client = FakeClient({"intent": "lookup", "ambiguous": False,
                             "ambiguity_reason": None})
        await classify("q", ctx(), client)
        call = client.calls[0]
        assert call["enforce"] is True
        assert call["schema"] is CLASSIFY_SCHEMA
        # Spelled out rather than compared against INTENTS: a test that reads the
        # same constant it is checking pins nothing. Adding an intent should make
        # this line fail once, deliberately, and be updated by whoever added it.
        assert call["schema"]["properties"]["intent"]["enum"] == [
            "lookup", "aggregate", "trend", "compare", "explain",
            "suggest_dashboard", "chat", "describe_data"]

    async def test_the_schema_context_reaches_the_prompt(self):
        client = FakeClient({"intent": "lookup", "ambiguous": False,
                             "ambiguity_reason": None})
        await classify("q", ctx(), client)
        text = "".join(m["content"] for m in client.calls[0]["messages"])
        assert "orders" in text

    async def test_llm_failure_is_none_not_a_guess(self):
        assert await classify("q", ctx(), FakeClient(None)) is None

    async def test_the_prompt_no_longer_biases_toward_ambiguous(self):
        """H5: 72% of real (answerable) questions were stopped for
        clarification — the 'when in doubt, prefer ambiguous=true' wording
        was the culprit. It must be gone, replaced by an explicit
        tie-breaking instruction."""
        client = FakeClient({"intent": "lookup", "ambiguous": False,
                             "ambiguity_reason": None})
        await classify("q", ctx(), client)
        system_text = client.calls[0]["messages"][0]["content"]
        assert "prefer ambiguous=true" not in system_text
        assert "cannot break the tie" in system_text
        assert "most specific matching table wins" in system_text

    async def test_a_request_to_see_the_data_is_never_ambiguous_by_contract(self):
        """Live thread, 2026-09-03: "i need to see sample of data" ran, but
        "what is this data have" and "show the data" came back as "needs
        more detail" -- the prompt had no example of a plain look at the
        rows, so the model asked which metric. Pin the rule and the
        examples; model judgment itself is the eval gate's to police."""
        client = FakeClient({"intent": "lookup", "ambiguous": False,
                             "ambiguity_reason": None})
        await classify("show me a sample", ctx(), client)
        system_text = client.calls[0]["messages"][0]["content"]
        assert "never ambiguous" in system_text
        assert ('Q: show me a sample of the data -> {"intent": "lookup", '
                '"ambiguous": false') in system_text
        assert ('Q: i need to see the first 20 rows -> {"intent": "lookup", '
                '"ambiguous": false') in system_text
        # "What IS this data" left `lookup` for its own intent (describe_data)
        # once the catalog could answer it; wanting ROWS is what stays here,
        # and the two must not be blurred back together.
        assert ('Q: what does this data contain -> {"intent": "describe_data", '
                '"ambiguous": false') in system_text

    async def test_the_conversation_reaches_the_prompt_only_when_there_is_one(self):
        client = FakeClient({"intent": "lookup", "ambiguous": False,
                             "ambiguity_reason": None})
        history = [{"role": "user", "content": "orders per city", "sql": [], "results": []},
                   {"role": "assistant", "content": "Cairo 3.",
                    "sql": ["SELECT city, count(*) FROM orders GROUP BY city"],
                    "results": []}]
        await classify("the same for Cairo", ctx(), client, history=history)
        user_text = client.calls[0]["messages"][1]["content"]
        assert "Conversation so far:" in user_text
        assert "orders per city" in user_text
        assert user_text.endswith("Question: the same for Cairo")
        # And the rule that a follow-up is not ambiguous for leaning on it.
        assert "never call it ambiguous" in client.calls[0]["messages"][0]["content"]

    async def test_the_render_uses_an_8000_char_budget_not_the_full_default(self):
        """Latency fix: classify carried the FULL ~24000-char default render
        just to judge intent/ambiguity — ~6k tokens of prefill it never
        needed. It must now call context.render(max_chars=8000, ...): every
        object NAME still survives (the two-pass render's breadth
        guarantee, pass 1, is budget-independent), but enrichment
        (descriptions/dtypes, depth pass 2) is starved sooner than at the
        full default — that's generate.py's need, not classify's."""
        big_ctx = ctx()
        n = 80
        for i in range(n):
            name = f"table_{i:03d}"
            # Padding pushes the description past MAX_SKELETON_DESC_CHARS
            # (90), so pass 1's hard-truncated skeleton description cuts it
            # off BEFORE the marker; only pass 2's full, untruncated
            # description carries the marker through.
            desc = ("padding " * 15) + f"unique_enrich_marker_{i:03d}"
            big_ctx.objects[name] = ObjectInfo(
                name, "table", desc,
                {f"col{j}": "text" for j in range(3)})
        full_render = big_ctx.render()
        assert len(full_render) > 8000, "test needs a catalog bigger than the new budget"

        client = FakeClient({"intent": "lookup", "ambiguous": False,
                             "ambiguity_reason": None})
        await classify("q", big_ctx, client)
        user_text = client.calls[0]["messages"][1]["content"]

        # Pin the exact call: classify's render is capped at 8000, not the
        # ~24000-char default.
        assert user_text == f"Database:\n{big_ctx.render(max_chars=8000, question='q')}\n\nQuestion: q"

        # Breadth guarantee: every object name still reaches the prompt at
        # the smaller budget.
        for i in range(n):
            assert f"table_{i:03d}" in user_text

        # Depth: at least one object's enrichment marker, present in the
        # full ~24000-char render, is dropped at the 8000-char cap —
        # proving classify is no longer sent the full render.
        dropped = [i for i in range(n)
                  if f"unique_enrich_marker_{i:03d}" in full_render
                  and f"unique_enrich_marker_{i:03d}" not in user_text]
        assert dropped, "expected classify's smaller budget to drop some enrichment"


class TestTheChatIntent:
    """The message that is not a question about the data.

    A screenshot started this: someone typed "hi" and got ten rows of a table
    back. The classifier's enum was six DATA intents wide, sent with
    enforce=True, so the model had no legal way to say "this asks nothing
    about the data" -- `lookup` was the closest lie available, and the
    pipeline dutifully planned, queried and narrated it. The fix is a seventh
    value, not a word list: WHICH messages are chat stays the model's
    judgement, as every other intent does."""

    def test_the_intent_is_offered_to_the_model(self):
        from app.services.agent.nodes.classify import INTENTS
        assert "chat" in INTENTS
        assert "chat" in CLASSIFY_SCHEMA["properties"]["intent"]["enum"]

    def test_the_existing_intents_are_untouched(self):
        from app.services.agent.nodes.classify import INTENTS
        for kept in ("lookup", "aggregate", "trend", "compare", "explain",
                     "suggest_dashboard"):
            assert kept in INTENTS

    async def test_the_prompt_teaches_it_by_example(self):
        """Shape is enforced, quality is prompted (see classify.py's module
        docstring): an intent with no example is an intent never chosen."""
        client = FakeClient({"intent": "chat", "ambiguous": False,
                             "ambiguity_reason": None})
        await classify("hi", ctx(), client)
        prompt = " ".join(m["content"] for m in client.calls[0]["messages"])
        assert '"intent": "chat"' in prompt
        # ...and the example that stops it over-triggering: a greeting wrapped
        # around a real question is still the question.
        assert "hi, how many orders are there" in prompt

    async def test_a_greeting_comes_back_as_chat(self):
        client = FakeClient({"intent": "chat", "ambiguous": False,
                             "ambiguity_reason": None})
        got = await classify("hi", ctx(), client)
        assert got["intent"] == "chat"


class TestClarify:
    async def test_produces_a_question_from_the_reason(self):
        client = FakeClient("Did you mean order total or order count?")
        got = await clarify("show me the orders number",
                            "could be count of orders or order totals", client)
        assert got.endswith("?")

    async def test_llm_failure_is_none(self):
        assert await clarify("q", "r", FakeClient(None)) is None

class TestDescribingTheDataItself:
    """"What IS this data?" -- its own intent since a live trace showed the
    same question routed two different ways on two turns: once answered from
    the column names with no query at all, once answered with four COUNT(*)s
    over four tables the model chose out of seventeen. Both were defensible
    and neither was the description that was asked for."""

    def test_the_intent_is_offered_to_the_model(self):
        from app.services.agent.nodes.classify import INTENTS
        assert "describe_data" in INTENTS
        assert "describe_data" in CLASSIFY_SCHEMA["properties"]["intent"]["enum"]

    async def test_the_prompt_separates_describing_from_sampling(self):
        """The distinction that has to survive: "describe this" wants to know
        what the data IS, "show me a sample" wants ROWS."""
        client = FakeClient({"intent": "describe_data", "ambiguous": False,
                             "ambiguity_reason": None})
        await classify("describe this dataset", ctx(), client)
        prompt = " ".join(m["content"] for m in client.calls[0]["messages"])
        assert '"intent": "describe_data"' in prompt
        assert "what tables are in here" in prompt
        assert "that one wants ROWS, and stays `lookup`" in prompt

    async def test_it_is_never_ambiguous(self):
        client = FakeClient({"intent": "describe_data", "ambiguous": False,
                             "ambiguity_reason": None})
        await classify("what does this data contain", ctx(), client)
        prompt = " ".join(m["content"] for m in client.calls[0]["messages"])
        assert "answered from the catalog and is never ambiguous" in prompt

class TestActionsTheChatCannotTake:
    """"create a dataset", three times in one live thread, was answered by
    dumping a whole table and calling it "the dataset". The chat answers
    questions; it does not act -- and a request to act is answered by saying
    where the action lives, never by a query that pretends."""

    async def test_they_are_taught_as_chat(self):
        client = FakeClient({"intent": "chat", "ambiguous": False,
                             "ambiguity_reason": None})
        await classify("create a new dataset", ctx(), client)
        prompt = " ".join(m["content"] for m in client.calls[0]["messages"])
        assert 'Q: create a new dataset -> {"intent": "chat"' in prompt
        assert "CREATE, SAVE, DELETE or CHANGE" in prompt
