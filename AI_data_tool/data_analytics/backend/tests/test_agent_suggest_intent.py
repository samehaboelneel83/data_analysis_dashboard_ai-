"""Asking the chat for a dashboard.

"Suggest a dashboard for me" is not a question about the data — there is no row
to return and no SQL to run for it. Sent through the ordinary pipeline it became
a `lookup` and came back as a confused answer or a clarification request.

So it is its own intent, and it short-circuits: classify recognises it, the graph
hands it to `services/suggest_dashboard`, and the proposals ride back on the run's
existing `presentation` field — the same channel a "show it as a bar chart"
follow-up already uses, so the chat surface needs no new transport.
"""
from app.services.agent.context import ObjectInfo, SchemaContext
from app.services.agent.nodes.classify import CLASSIFY_SCHEMA, INTENTS, classify


def ctx():
    c = SchemaContext(source_id=1, family="sqlite")
    c.objects["mdl_course"] = ObjectInfo("mdl_course", "table", "Courses.",
                                         {"id": "integer", "fullname": "text"})
    return c


class FakeClient:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    async def complete_json(self, messages, schema, **kw):
        self.calls.append({"messages": messages, "schema": schema, **kw})
        return self.reply


def test_the_new_intent_is_offered_to_the_model():
    assert "suggest_dashboard" in INTENTS
    assert "suggest_dashboard" in CLASSIFY_SCHEMA["properties"]["intent"]["enum"]


def test_the_existing_intents_are_untouched():
    """Adding an intent must not remove one; every existing question type keeps
    the classification it had, and the eval gate keeps measuring the same set."""
    for kept in ("lookup", "aggregate", "trend", "compare", "explain"):
        assert kept in INTENTS


async def test_the_prompt_teaches_the_new_intent_by_example():
    """The classifier is shape-enforced but quality-prompted (see the module
    docstring in classify.py), so a new intent without an example is a new intent
    the model never picks."""
    client = FakeClient({"intent": "suggest_dashboard", "ambiguous": False,
                         "ambiguity_reason": None})
    await classify("suggest a dashboard for me", ctx(), client)
    prompt = " ".join(m["content"] for m in client.calls[0]["messages"])
    assert "suggest_dashboard" in prompt
    assert "dashboard" in prompt.lower()


async def test_a_dashboard_request_is_classified_as_such():
    client = FakeClient({"intent": "suggest_dashboard", "ambiguous": False,
                         "ambiguity_reason": None})
    got = await classify("build me a dashboard for my courses", ctx(), client)
    assert got["intent"] == "suggest_dashboard"


async def test_asking_for_a_dashboard_is_never_treated_as_ambiguous():
    """"Suggest a dashboard" has no missing detail to ask back about -- the whole
    point is that the model chooses. A clarification here is a dead end."""
    from app.services.agent.nodes.classify import is_dashboard_request
    assert is_dashboard_request("suggest a dashboard for me")
    assert is_dashboard_request("Build me a DASHBOARD please")
    assert is_dashboard_request("create a dashboard with a KPI")
    assert not is_dashboard_request("what were total sales last month")


class TestWhoTheDashboardIsFor:
    """"i am a department manager and i need ... a dashboard" came back
    "for a Platform Admin": the account's role, while the words "department
    manager" went unread. What they SAID wins; the role is the fallback."""

    class Persona:
        def __init__(self, persona):
            self.persona, self.calls = persona, []

        async def complete_json(self, messages, schema, **kw):
            self.calls.append(messages)
            return {"persona": self.persona}

    async def test_the_stated_persona_is_read_from_the_request(self):
        from app.services.suggest_dashboard import stated_persona
        client = self.Persona("department manager")
        assert await stated_persona("i am a department manager, build me a dashboard",
                                    client) == "department manager"
        assert "i am a department manager" in client.calls[0][1]["content"]

    async def test_no_persona_means_none_not_a_guess(self):
        from app.services.suggest_dashboard import stated_persona
        assert await stated_persona("suggest a dashboard", self.Persona(None)) is None
        assert await stated_persona("suggest a dashboard", self.Persona("  ")) is None
        assert await stated_persona("", self.Persona("x")) is None

    async def test_the_prompt_forbids_inventing_one(self):
        from app.services.suggest_dashboard import stated_persona
        client = self.Persona(None)
        await stated_persona("sales by region", client)
        assert "Never guess one from the subject matter" in client.calls[0][0]["content"]
