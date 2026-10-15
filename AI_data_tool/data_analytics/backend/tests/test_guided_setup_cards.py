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


# ── A ready chart on one part of the rows ────────────────────────────────────

import pandas as pd

PART_PROFILE = {"columns": [
    {"name": "group", "role": "categorical"}, {"name": "kind", "role": "categorical"},
    {"name": "code", "role": "categorical", "is_identifier": True}, {"name": "amount", "role": "numeric"}]}
PART_ROWS = pd.DataFrame({"group": ["a"] * 60 + ["b"] * 35 + ["c"] * 5, "kind": ["x"] * 50 + ["y"] * 50,
                     "code": [str(i) for i in range(100)], "amount": range(100)})
PARTS = answer.parts_of(PART_PROFILE, PART_ROWS)


def test_the_parts_offered_exist_and_are_large_enough():
    assert {(p["column"], p["value"]) for p in PARTS} == {("group", "a"), ("group", "b"), ("kind", "x"), ("kind", "y")}
    assert next(p for p in PARTS if p["value"] == "a")["rows"] == 60
    # A column the page is already narrowed by offers none; neither does an identifier.
    assert {p["column"] for p in answer.parts_of(PART_PROFILE, PART_ROWS, skip={"group"})} == {"kind"}


def pick_part(picks):
    client = Chooser({"pages": [{"title": "One part", "rationale": "r", "picks": picks}]})
    return asyncio.run(answer.pick_pages(client, CARDS, DEMAND, [], 100, 2, "en", PARTS)), client


def test_a_chart_is_drawn_on_one_listed_part_and_says_which():
    k = next(i for i, p in enumerate(PARTS) if (p["column"], p["value"]) == ("kind", "x"))
    pages, client = pick_part([{"id": 1, "question": "q1", "title": "Largest groups", "why": "w", "part": k}])
    w = pages[0]["widgets"][0]
    assert w["config"]["filters"] == [{"column": "kind", "op": "eq", "value": "x"}]
    assert w["config"]["dimension"] == "group" and "(x)" in w["title"]
    assert CARDS[1]["config"].get("filters") is None            # the listed chart itself is untouched
    assert "THE PARTS" in client.calls[0][0][1]["content"]


def test_a_part_that_is_not_listed_or_is_the_charts_own_split_is_ignored():
    own = next(i for i, p in enumerate(PARTS) if p["column"] == "group")
    pages, _ = pick_part([{"id": 1, "question": "q1", "why": "w", "part": own},
                          {"id": 0, "question": "q1", "why": "w", "part": 99}])
    assert [w["config"].get("filters") for w in pages[0]["widgets"]] == [None, None]


def test_the_same_chart_may_be_used_for_two_parts_but_not_twice_for_one():
    x = next(i for i, p in enumerate(PARTS) if (p["column"], p["value"]) == ("kind", "x"))
    y = next(i for i, p in enumerate(PARTS) if (p["column"], p["value"]) == ("kind", "y"))
    pages, _ = pick_part([{"id": 1, "question": "q1", "why": "w", "part": x},
                          {"id": 1, "question": "q1", "why": "w", "part": y},
                          {"id": 1, "question": "q1", "why": "w", "part": x}])
    assert len(pages[0]["widgets"]) == 2


def test_without_parts_nothing_about_them_is_said():
    _pages, client = pick({"pages": []})
    assert "THE PARTS" not in client.calls[0][0][1]["content"] and "part" not in client.calls[0][0][0]["content"]


# ── "by <entity>" through a linked key (B-35) ────────────────────────────────

LINKED_PROFILE = {"columns": [
    {"name": "shipment_id", "role": "categorical", "is_identifier": True, "distinct": 900},
    {"name": "origin_branch_id", "role": "numeric", "is_identifier": True, "distinct": 12},
    {"name": "service_type", "role": "categorical", "distinct": 3},
    {"name": "delivery_fee_egp", "role": "numeric", "distinct": 400},
]}
FEES_BY_BRANCH = {"sentence": "late deliveries and delivery fees by branch",
                  "questions": [{"id": "q1", "text": "Which branch collects the most delivery fees?"}]}


def test_a_key_linked_to_a_named_entity_is_a_dimension():
    links = [{"column": "origin_branch_id", "table": "public.branches"}]
    linked = answer.linked_dimensions(LINKED_PROFILE, FEES_BY_BRANCH, links)
    assert linked == [{"column": "origin_branch_id", "entity": "branch", "table": "branches"}]
    cards = answer.standard_cards(LINKED_PROFILE, [], None, linked=linked)
    by = [c for c in cards if c["config"].get("dimension") == "origin_branch_id"]
    assert by and all(c["widget_type"] == "bar" for c in by)
    # Captioned for what it is: the branch's key, not its name.
    assert any(c["title"] == "Total delivery fee egp by branch (id)" for c in by), [c["title"] for c in by]
    # The model designing its own pages is told the same.
    note = answer.linked_notes(linked)[0]
    assert "`origin_branch_id`" in note and "branch" in note


def test_a_key_is_not_a_dimension_without_a_link_or_a_question_naming_it():
    assert answer.linked_dimensions(LINKED_PROFILE, FEES_BY_BRANCH, []) == []
    other = {"questions": [{"id": "q1", "text": "Which service type is late most often?"}]}
    assert answer.linked_dimensions(LINKED_PROFILE, other, [{"column": "origin_branch_id", "table": "branches"}]) == []
    # A key with a value per row is no grouping, whatever is asked.
    wide = {"columns": [{**c, "distinct": 900} if c["name"] == "origin_branch_id" else c
                        for c in LINKED_PROFILE["columns"]]}
    assert answer.linked_dimensions(wide, FEES_BY_BRANCH, [{"column": "origin_branch_id", "table": "branches"}]) == []
    cards = answer.standard_cards(LINKED_PROFILE, [], None)
    assert not any(c["config"].get("dimension") == "origin_branch_id" for c in cards)


async def test_only_defined_links_of_this_dataset_are_read(db_session, two_orgs):
    from app.models.models import (DataSource, Dataset, Relationship, SourceObject, SourceRelationship)
    org = two_orgs["a"]["org"].id
    src = DataSource(name="Nile", type="postgresql", config={}, org_id=org)
    db_session.add(src)
    await db_session.flush()
    ship = Dataset(name="Shipments", org_id=org, data_source_id=src.id, source_table="public.shipments")
    branches = Dataset(name="Branches", org_id=org)
    db_session.add_all([ship, branches])
    objs = {n: SourceObject(data_source_id=src.id, org_id=org, schema_name="public", name=n)
            for n in ("shipments", "branches", "couriers", "zones")}
    db_session.add_all(objs.values())
    await db_session.flush()
    db_session.add_all([
        Relationship(org_id=org, from_dataset_id=ship.id, from_column="dest_branch_id",
                     to_dataset_id=branches.id, to_column="id", source="confirmed"),
        SourceRelationship(data_source_id=src.id, org_id=org, from_object_id=objs["shipments"].id,
                           from_column="origin_branch_id", to_object_id=objs["branches"].id, to_column="id",
                           source="declared"),
        # A guess nobody confirmed is not a link to group by.
        SourceRelationship(data_source_id=src.id, org_id=org, from_object_id=objs["shipments"].id,
                           from_column="courier_id", to_object_id=objs["couriers"].id, to_column="id",
                           source="inferred"),
        # Another table's link is not this dataset's.
        SourceRelationship(data_source_id=src.id, org_id=org, from_object_id=objs["couriers"].id,
                           from_column="zone_id", to_object_id=objs["zones"].id, to_column="id",
                           source="declared"),
    ])
    await db_session.commit()
    links = await answer.links_of(db_session, ship)
    assert sorted((d["column"], d["table"]) for d in links) == [
        ("dest_branch_id", "Branches"), ("origin_branch_id", "branches")]
