"""What people wrote about themselves and their data reaches the designers
(services/ai_context.py): the profile's description stands in for an empty
box where a model is on, the rest travels as labelled background, and with no
model an empty box stays empty."""
from app.services import ai_context as ctx


def test_their_own_words_come_first_and_each_description_is_labelled():
    got = ctx.compose("I follow late deliveries", llm_on=True, about="I plan the routes",
                      connection="The operations database", connection_name="Ops",
                      dataset="One row per delivery", dataset_name="Deliveries",
                      dashboard="For the Monday review", dashboard_name="Weekly")
    assert got.startswith("I follow late deliveries\n\nBackground")
    for part in ("About the person (from their profile): I plan the routes",
                 "The connection 'Ops' is described as: The operations database",
                 "The dataset 'Deliveries' is described as: One row per delivery",
                 "The dashboard 'Weekly' is for: For the Monday review"):
        assert part in got


def test_with_nothing_typed_the_profile_stands_in_only_where_a_model_reads_it():
    assert ctx.compose("", llm_on=True, about="I plan the routes", dataset="One row per delivery") \
        .startswith("I plan the routes\n\nBackground")
    # No profile description: an empty box stays empty, whatever else is described.
    assert ctx.compose("  ", llm_on=True, about=None, dataset="One row per delivery") == ""
    # No model: nothing is added to what was typed, and nothing stands in.
    assert ctx.compose("", llm_on=False, about="I plan the routes") == ""
    assert ctx.compose("late deliveries", llm_on=False, about="I plan the routes") == "late deliveries"


def test_nothing_described_adds_nothing_and_a_long_description_is_cut():
    assert ctx.compose("late deliveries", llm_on=True) == "late deliveries"
    assert ctx.background() == []
    line = ctx.background(dataset="x" * 5000)[0]
    assert len(line) < ctx.EACH + 60


async def test_a_person_saves_and_clears_what_they_say_about_themselves(client, two_orgs, auth_headers):
    me = await client.get("/api/v1/auth/me", headers=auth_headers["a"])
    assert me.status_code == 200 and me.json().get("about") is None
    r = await client.patch("/api/v1/auth/me", json={"about": "  I plan the routes  "}, headers=auth_headers["a"])
    assert r.status_code == 200 and r.json()["about"] == "I plan the routes"
    assert (await client.get("/api/v1/auth/me", headers=auth_headers["a"])).json()["about"] == "I plan the routes"
    # It is theirs alone: the other organisation's person sees nothing of it.
    assert (await client.get("/api/v1/auth/me", headers=auth_headers["b"])).json().get("about") is None
    r = await client.patch("/api/v1/auth/me", json={"about": ""}, headers=auth_headers["a"])
    assert r.json()["about"] is None
    assert (await client.patch("/api/v1/auth/me", json={"about": "x" * 1001}, headers=auth_headers["a"])).status_code == 422


def test_the_copilot_is_told_the_background_as_background():
    from app.services.agent.nodes.copilot import render_page_context
    text = render_page_context({"report_name": "Weekly", "page_name": "Page 1", "widgets": [],
                                "background": ctx.background(about="I plan the routes", dashboard="For the Monday review")})
    assert "Background: About the person (from their profile): I plan the routes" in text
    assert "Background: The dashboard is for: For the Monday review" in text


def test_guided_setup_passes_the_background_to_its_model_calls_and_never_stores_or_searches_it():
    from types import SimpleNamespace as NS
    from app.routers.guided_setup import _with_background
    from app.services.guided_setup import datasets, demand
    saved = {"work": "I plan the routes", "focus": "late deliveries"}
    brief = _with_background(saved, NS(about="I decide where to add capacity"), NS(description="The operations database"))
    assert saved == {"work": "I plan the routes", "focus": "late deliveries"}            # the saved brief is untouched
    text = datasets._brief_text(brief)
    assert "About them, from their profile: I decide where to add capacity" in text
    assert "The connection is described as: The operations database" in text
    prompt = "\\n".join(m["content"] for m in demand.build_prompt(brief, [], [], "en"))
    assert "I decide where to add capacity" in prompt and "The operations database" in prompt
    # The plain fallback narrows the data by what was TYPED, not by the background.
    said = demand._said(brief, [], [])
    assert "late deliveries" in said and "capacity" not in said and "operations database" not in said
    # Nothing described: the brief is passed as it is.
    assert _with_background(saved, NS(about=None), NS(description="  ")) == saved
