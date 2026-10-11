"""The guided setup's designer has the same three ways to get its charts as
"Suggest dashboards", on its own switch (settings.setup_ai_selection,
docs/discovery/PLAN.md §AV): in "cards" mode the model chooses among charts
the platform built, by id, and cannot add one."""
import asyncio

from app.services.guided_setup import answer

CARDS = [
    {"widget_type": "kpi", "title": "Rows", "why": "how many there are", "config": {"aggregation": "count"}},
    {"widget_type": "bar", "title": "Amount by group", "why": "which group is largest",
     "config": {"dimension": "group", "measure": "amount", "aggregation": "sum"}},
    {"widget_type": "line", "title": "Amount by month", "why": "how it moved",
     "config": {"dimension": "day", "measure": "amount", "aggregation": "sum", "dimension_granularity": "month"}},
]
DEMAND = {"sentence": "where the amount is largest", "questions": [{"id": "q1", "text": "Which group is largest?"}]}


class Chooser:
    def __init__(self, answer_):
        self.answer, self.calls = answer_, []

    async def complete_json(self, messages, schema, **kw):
        self.calls.append((messages, schema))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def pick(got):
    client = Chooser(got)
    return asyncio.run(answer.pick_pages(client, CARDS, DEMAND, [], 100, 2, "en")), client


def test_a_page_holds_only_charts_from_the_list():
    pages, client = pick({"pages": [{"title": "Where it is largest", "rationale": "the groups, ranked", "picks": [
        {"id": 1, "question": "q1", "title": "Largest groups", "why": "ranks the groups"},
        {"id": 7, "question": "q1", "why": "not in the list"},
        {"id": "2", "question": "q1", "why": "not a number"},
        {"id": True, "question": "q1", "why": "not a number either"},
        {"id": 1, "question": "q1", "why": "the same chart twice"}]}]})
    assert len(pages) == 1 and len(pages[0]["widgets"]) == 1
    w = pages[0]["widgets"][0]
    # The chart is the platform's: its kind and its fields cannot be changed by the answer.
    assert (w["widget_type"], w["config"]) == (CARDS[1]["widget_type"], CARDS[1]["config"])
    assert w["config"] is not CARDS[1]["config"]
    # Its words are the person's: a title and a reason may be given.
    assert w["title"] == "Largest groups" and w["question"] == "q1" and w["why"] == "ranks the groups"
    assert client.calls[0][1] is answer.PICKS_SCHEMA


def test_the_list_and_the_request_are_fenced_as_data():
    _pages, client = pick({"pages": []})
    system, user = (m["content"] for m in client.calls[0][0])
    assert "ONLY from the list" in system
    assert "1 | bar | Amount by group | which group is largest" in user
    assert "Which group is largest?" in user


def test_a_page_of_nothing_is_not_a_page_and_a_failure_is_harmless():
    assert pick({"pages": [{"title": "t", "rationale": "r", "picks": []}]})[0] == []
    assert pick({"pages": [{"title": "t", "rationale": "r", "picks": [{"id": 9, "question": "q1", "why": "x"}]}]})[0] == []
    assert pick(RuntimeError("the model is away"))[0] == []
    assert pick(None)[0] == []
    assert asyncio.run(answer.pick_pages(None, CARDS, DEMAND, [], 100, 2, "en")) == []


def test_no_more_pages_than_asked_for():
    pages, _ = pick({"pages": [{"title": f"p{i}", "rationale": "r", "picks": [{"id": i, "question": "q1", "why": "w"}]}
                               for i in range(3)]})
    assert [p["title"] for p in pages] == ["p0", "p1"]


PROFILE = {"columns": [
    {"name": "id", "role": "numeric", "is_identifier": True, "distinct": 900},
    {"name": "region", "role": "categorical", "distinct": 5},
    {"name": "channel", "role": "categorical", "distinct": 3},
    {"name": "code", "role": "categorical", "distinct": 900, "is_identifier": True},
    {"name": "amount", "role": "numeric", "distinct": 400},
    {"name": "score", "role": "numeric", "distinct": 9},
    {"name": "created", "role": "datetime", "distinct": 300},
    {"name": "secret", "role": "categorical", "distinct": 4, "is_personal": True},
]}
SHARES = [{"name": "is_open_pct", "of": "is_open", "is": "yes"}, {"name": "is_open_not_pct", "of": "is_open", "is": "no"},
          {"name": "is_open_label", "of": "is_open", "is": "label"}]


def test_the_plain_charts_come_from_the_shape_of_the_data():
    cards = answer.standard_cards(PROFILE, SHARES, None)
    by = {(c["widget_type"], c["config"].get("dimension"), c["config"].get("measure"), c["config"]["aggregation"])
          for c in cards}
    # how many, per group and over time; the share of a yes/no; a number totalled, a score averaged
    assert ("kpi", None, "id", "count") in by and ("kpi", None, "is_open_pct", "avg") in by
    assert ("bar", "region", "id", "count") in by and ("bar", "region", "is_open_pct", "avg") in by
    assert ("bar", "channel", "amount", "sum") in by and ("bar", "region", "score", "avg") in by
    assert ("line", "created", "id", "count") in by
    assert any(c["widget_type"] == "heatmap" and {c["config"]["dimension"], c["config"]["dimension2"]} == {"region", "channel"}
               for c in cards)
    used = {v for c in cards for v in (c["config"].get("dimension"), c["config"].get("dimension2"), c["config"].get("measure"))}
    # never grouped by an identifier, a personal column, or a column made for drawing
    assert not used & {"code", "secret", "is_open_label", "is_open_not_pct"}
    assert all(c["source"] == "standard" and c["title"] and c["why"] for c in cards)
    assert len(cards) <= answer.MAX_STANDARD


def test_a_column_that_may_not_be_shown_is_left_out():
    cards = answer.standard_cards(PROFILE, SHARES, None, ineligible={"region", "amount"})
    used = {v for c in cards for v in (c["config"].get("dimension"), c["config"].get("dimension2"), c["config"].get("measure"))}
    assert not used & {"region", "amount"}


def test_the_switch_is_its_own_and_free_unless_set(monkeypatch):
    from app.core.config import settings
    assert answer.setup_selection_mode() == "free"
    monkeypatch.setattr(settings, "setup_ai_selection", "cards")
    assert answer.setup_selection_mode() == "cards"
    assert answer.setup_selection_mode("both") == "both"
    monkeypatch.setattr(settings, "setup_ai_selection", "nonsense")
    assert answer.setup_selection_mode() == "free"
