"""Suggest a whole dashboard for a named kind of person.

The platform could already suggest widgets, but only for a dataset that already
exists and only from the insights engine's statistical findings. Two things were
missing for the case that prompted this:

  * it starts from a DATASET. A user who has just connected a database has no
    dataset yet, and does not know which of 17 `mdl_*` tables to join to get one.
  * it does not know WHO is asking. An instructor, a student-affairs officer and
    a dean want three different dashboards out of the same database, and nothing
    in the existing path takes the person as an input.

So this proposes, from the synced catalog plus a role name, one SQL query that
builds the right dataset and the widgets to put over it. It only ever *proposes*:
nothing is created until the caller accepts, because a wrong dashboard that
appears by itself is worse than no dashboard.
"""
import pytest

from app.services.suggest_dashboard import (SUGGESTION_SCHEMA, build_prompt,
                                            validate_suggestion)

CATALOG = [
    {"name": "mdl_course", "description": "Academic courses.",
     "columns": [{"name": "id", "dtype": "integer"},
                 {"name": "fullname", "dtype": "text"},
                 {"name": "startdate", "dtype": "datetime"}]},
    {"name": "mdl_grade_grades", "description": "One grade per student per item.",
     "columns": [{"name": "userid", "dtype": "integer"},
                 {"name": "finalgrade", "dtype": "numeric"}]},
]


class TestPrompt:
    def test_the_prompt_names_the_person_it_is_for(self):
        prompt = build_prompt(CATALOG, for_role="Instructor",
                              goal="see which of my students are failing")
        text = " ".join(m["content"] for m in prompt)
        assert "Instructor" in text
        assert "failing" in text

    def test_the_prompt_carries_the_tables_and_their_descriptions(self):
        text = " ".join(m["content"] for m in build_prompt(CATALOG, for_role="Dean"))
        assert "mdl_grade_grades" in text
        assert "One grade per student per item." in text
        assert "finalgrade" in text

    def test_the_prompt_survives_a_source_with_no_descriptions(self):
        """A source can be connected but never synced. Suggesting from bare table
        names is worse than suggesting from descriptions, but it is not a crash."""
        bare = [{"name": "t1", "description": None,
                 "columns": [{"name": "a", "dtype": "text"}]}]
        assert build_prompt(bare, for_role="Instructor")


class TestValidation:
    """The model proposes; this decides what is safe to act on."""

    def _ok(self):
        return {
            "title": "Instructor — Course Health",
            "sql": "SELECT c.fullname AS course, g.finalgrade AS grade "
                   "FROM mdl_course c JOIN mdl_grade_grades g ON 1=1",
            "widgets": [
                {"widget_type": "kpi", "title": "Average grade",
                 "dimension": "", "measure": "grade", "aggregation": "avg"},
                {"widget_type": "bar", "title": "Grade by course",
                 "dimension": "course", "measure": "grade", "aggregation": "avg"},
            ],
        }

    def test_a_well_formed_suggestion_is_accepted(self):
        ok, why = validate_suggestion(self._ok(), {"mdl_course", "mdl_grade_grades"})
        assert ok, why

    def test_a_suggestion_naming_an_unknown_table_is_refused(self):
        bad = self._ok()
        bad["sql"] = "SELECT * FROM mdl_secret_payroll"
        ok, why = validate_suggestion(bad, {"mdl_course", "mdl_grade_grades"})
        assert not ok and "mdl_secret_payroll" in why

    @pytest.mark.parametrize("statement", [
        "DROP TABLE mdl_course",
        "DELETE FROM mdl_course",
        "UPDATE mdl_course SET fullname = 'x'",
        "INSERT INTO mdl_course VALUES (1)",
        "SELECT 1; DROP TABLE mdl_course",
    ])
    def test_anything_that_is_not_a_single_select_is_refused(self, statement):
        """The suggestion is executed to build a dataset, so it is a query, never
        a change. Refusing here rather than trusting the prompt is the point."""
        bad = self._ok()
        bad["sql"] = statement
        ok, why = validate_suggestion(bad, {"mdl_course"})
        assert not ok, f"{statement!r} was accepted"

    def test_a_widget_whose_columns_are_not_in_the_query_is_refused(self):
        """A widget on a column the SQL does not return renders as an error. The
        model is good at SQL and careless about aliases; this is where that shows."""
        bad = self._ok()
        bad["widgets"][1]["dimension"] = "department"      # never selected
        ok, why = validate_suggestion(bad, {"mdl_course", "mdl_grade_grades"})
        assert not ok and "department" in why

    def test_a_suggestion_with_no_widgets_is_refused(self):
        bad = self._ok()
        bad["widgets"] = []
        ok, why = validate_suggestion(bad, {"mdl_course"})
        assert not ok

    def test_an_unknown_widget_type_is_refused(self):
        bad = self._ok()
        bad["widgets"][0]["widget_type"] = "hologram"
        ok, why = validate_suggestion(bad, {"mdl_course", "mdl_grade_grades"})
        assert not ok and "hologram" in why


def test_the_schema_is_flat_enough_for_strict_json_mode():
    """`complete_json(enforce=True)` sends this to the endpoint as a json_schema.
    Strict mode rejects an open object, so every level needs its properties
    declared and `additionalProperties` off."""
    def check(node):
        if node.get("type") == "object":
            assert node.get("properties"), "an object with no declared properties"
            assert node.get("additionalProperties") is False
            for child in node["properties"].values():
                check(child)
        if node.get("type") == "array":
            check(node["items"])
    check(SUGGESTION_SCHEMA)


# ---------------------------------------------------------------------------
# The repair loop. On the very first real run against the Moodle catalog the
# model proposed a KPI with measure "count" -- the name of the aggregation, not
# a column the query selects. The validator caught it, which is right, but a
# feature that refuses on its first use is not a feature. The agent already
# solves this shape (graph.py: bounded retries, each fed the rung that rejected
# the last attempt), so the same pattern is used here rather than a second one.
# ---------------------------------------------------------------------------
from app.services import suggest_dashboard as sd


class FakeClient:
    """Returns each canned reply in turn, and records what it was told."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    async def complete_json(self, messages, schema, **kw):
        self.calls.append(messages)
        return self.replies.pop(0) if self.replies else None


def _good():
    return {"title": "T", "sql": "SELECT c.fullname AS course, g.finalgrade AS grade "
                                 "FROM mdl_course c JOIN mdl_grade_grades g ON 1=1",
            "widgets": [{"widget_type": "bar", "title": "W", "dimension": "course",
                         "measure": "grade", "aggregation": "avg"}]}


def _bad_measure():
    bad = _good()
    bad["widgets"][0]["measure"] = "count"      # the real first-run mistake
    return bad


async def test_a_rejected_suggestion_is_retried_with_the_reason(monkeypatch):
    client = FakeClient([_bad_measure(), _good()])
    monkeypatch.setattr(sd, "get_client", lambda: client, raising=False)
    monkeypatch.setattr("app.services.llm.get_client", lambda: client)

    got, why = await sd.suggest_dashboard(CATALOG, for_role="Instructor")

    assert got is not None, why
    assert len(client.calls) == 2, "the second attempt was never made"
    retry_text = " ".join(m["content"] for m in client.calls[1])
    assert "count" in retry_text, "the retry did not carry what was wrong"


async def test_the_retries_are_bounded(monkeypatch):
    """A model that keeps making the same mistake must stop, not loop."""
    client = FakeClient([_bad_measure()] * 10)
    monkeypatch.setattr("app.services.llm.get_client", lambda: client)

    got, why = await sd.suggest_dashboard(CATALOG, for_role="Instructor")

    assert got is None
    assert "count" in why
    assert len(client.calls) <= sd.MAX_ATTEMPTS


async def test_a_first_attempt_that_is_valid_is_not_retried(monkeypatch):
    client = FakeClient([_good()])
    monkeypatch.setattr("app.services.llm.get_client", lambda: client)

    got, _ = await sd.suggest_dashboard(CATALOG, for_role="Instructor")

    assert got is not None
    assert len(client.calls) == 1


# ---------------------------------------------------------------------------
# The execution rung. The first suggestion that passed every static check still
# failed on contact with the database: SQLite rejected "DISTINCT is not supported
# for window functions". Safe SQL and consistent aliases are not the same as SQL
# that RUNS, and the only thing that knows the difference is the database. So the
# loop asks it, and hands the database's own error back to the model.
# ---------------------------------------------------------------------------


async def test_sql_that_does_not_execute_is_retried_with_the_database_error(monkeypatch):
    client = FakeClient([_good(), _good()])
    monkeypatch.setattr("app.services.llm.get_client", lambda: client)
    tried = []

    async def probe(sql):
        tried.append(sql)
        return "DISTINCT is not supported for window functions" if len(tried) == 1 else None

    got, why = await sd.suggest_dashboard(CATALOG, for_role="Instructor", probe=probe)

    assert got is not None, why
    assert len(tried) == 2, "the query was not re-checked after the repair"
    retry_text = " ".join(m["content"] for m in client.calls[1])
    assert "window functions" in retry_text, "the database's error was not fed back"


async def test_a_query_that_never_runs_is_refused_with_the_database_error(monkeypatch):
    client = FakeClient([_good()] * 10)
    monkeypatch.setattr("app.services.llm.get_client", lambda: client)

    async def probe(sql):
        return "no such column: nope"

    got, why = await sd.suggest_dashboard(CATALOG, for_role="Instructor", probe=probe)

    assert got is None
    assert "no such column" in why


async def test_without_a_probe_the_loop_behaves_as_before(monkeypatch):
    """The probe is optional: `build_prompt`/`validate_suggestion` stay usable, and
    a caller with no connection to test against still gets a static check."""
    client = FakeClient([_good()])
    monkeypatch.setattr("app.services.llm.get_client", lambda: client)

    got, _ = await sd.suggest_dashboard(CATALOG, for_role="Instructor")

    assert got is not None
    assert len(client.calls) == 1


# ---------------------------------------------------------------------------
# SEVERAL proposals, not one. A person asking "suggest a dashboard for me" has
# not decided what they want yet -- one answer is a decision made for them, three
# is a choice. Asked for in one call, not three: the catalog prompt is the
# expensive part and sending it three times triples the wait for no gain.
#
# Each proposal is validated and probed INDEPENDENTLY. Two good proposals and one
# that will not run is a useful answer; throwing all three away because of the
# third is not.
# ---------------------------------------------------------------------------


def _batch(*proposals):
    return {"proposals": list(proposals)}


def _titled(title, measure="grade"):
    p = _good()
    p["title"] = title
    p["widgets"][0]["measure"] = measure
    return p


async def test_several_proposals_come_back_from_one_call(monkeypatch):
    client = FakeClient([_batch(_titled("A"), _titled("B"), _titled("C"))])
    monkeypatch.setattr("app.services.llm.get_client", lambda: client)

    got, why = await sd.suggest_dashboards(CATALOG, for_role="Instructor", count=3)

    assert [p["title"] for p in got] == ["A", "B", "C"], why
    assert len(client.calls) == 1, "asked the model more than once"


async def test_the_prompt_asks_for_distinct_proposals(monkeypatch):
    client = FakeClient([_batch(_titled("A"))])
    monkeypatch.setattr("app.services.llm.get_client", lambda: client)

    await sd.suggest_dashboards(CATALOG, for_role="Instructor", count=3)

    text = " ".join(m["content"] for m in client.calls[0])
    assert "3" in text
    assert "different" in text.lower(), "nothing stops it restating one dashboard 3 times"


async def test_one_bad_proposal_does_not_lose_the_good_ones(monkeypatch):
    client = FakeClient([_batch(_titled("A"), _bad_measure(), _titled("C"))])
    monkeypatch.setattr("app.services.llm.get_client", lambda: client)

    got, why = await sd.suggest_dashboards(CATALOG, for_role="Instructor", count=3)

    assert [p["title"] for p in got] == ["A", "C"], why


async def test_every_proposal_is_checked_against_the_database(monkeypatch):
    client = FakeClient([_batch(_titled("A"), _titled("B"))])
    monkeypatch.setattr("app.services.llm.get_client", lambda: client)
    seen = []

    async def probe(sql):
        seen.append(sql)
        return "no such table" if len(seen) == 2 else None

    got, _ = await sd.suggest_dashboards(CATALOG, for_role="Instructor",
                                         count=2, probe=probe)

    assert len(seen) == 2, "a proposal was returned without being run"
    assert [p["title"] for p in got] == ["A"]


async def test_when_nothing_survives_the_reason_says_why(monkeypatch):
    client = FakeClient([_batch(_bad_measure(), _bad_measure())])
    monkeypatch.setattr("app.services.llm.get_client", lambda: client)

    got, why = await sd.suggest_dashboards(CATALOG, for_role="Instructor", count=2)

    assert got == []
    assert "count" in why, why


async def test_an_unreachable_model_is_reported_not_raised(monkeypatch):
    client = FakeClient([])           # returns None
    monkeypatch.setattr("app.services.llm.get_client", lambda: client)

    got, why = await sd.suggest_dashboards(CATALOG, for_role="Instructor")

    assert got == []
    assert why


# ---------------------------------------------------------------------------
# The batch needs the repair round too. On the first real run through the chat
# all three proposals were rejected -- two invented `mdl_user_enrolments.courseid`
# (that table joins through `mdl_enrol`, so the column does not exist) and one
# wrote `strftime('%H:%M', ...)`, whose colon SQLAlchemy reads as a bind
# parameter. Every one of those is fixable by telling the model what the database
# said. Without a repair round the person asks for a dashboard and gets nothing.
# ---------------------------------------------------------------------------


async def test_rejected_proposals_are_repaired_and_kept(monkeypatch):
    client = FakeClient([_batch(_bad_measure(), _bad_measure()),
                         _batch(_titled("Fixed A"), _titled("Fixed B"))])
    monkeypatch.setattr("app.services.llm.get_client", lambda: client)

    got, why = await sd.suggest_dashboards(CATALOG, for_role="Instructor", count=2)

    assert [p["title"] for p in got] == ["Fixed A", "Fixed B"], why
    assert len(client.calls) == 2


async def test_the_repair_carries_what_the_database_said(monkeypatch):
    client = FakeClient([_batch(_titled("A")), _batch(_titled("A"))])
    monkeypatch.setattr("app.services.llm.get_client", lambda: client)
    calls = []

    async def probe(sql):
        calls.append(sql)
        return "no such column: ue.courseid" if len(calls) == 1 else None

    got, _ = await sd.suggest_dashboards(CATALOG, for_role="Instructor",
                                         count=1, probe=probe)

    assert got, "the repaired proposal was thrown away"
    retry = " ".join(m["content"] for m in client.calls[1])
    assert "ue.courseid" in retry, "the model was not told what was wrong"


async def test_good_proposals_are_not_re_asked_for(monkeypatch):
    """Only the failures go back. Re-generating the whole batch would risk losing
    a proposal that was already fine."""
    client = FakeClient([_batch(_titled("Keep"), _bad_measure()),
                         _batch(_titled("Repaired"))])
    monkeypatch.setattr("app.services.llm.get_client", lambda: client)

    got, _ = await sd.suggest_dashboards(CATALOG, for_role="Instructor", count=2)

    assert [p["title"] for p in got] == ["Keep", "Repaired"]


async def test_the_repair_round_happens_at_most_once(monkeypatch):
    """Bounded like every other loop here: a model that cannot fix it twice will
    not fix it on the fifth try, and the person is waiting."""
    client = FakeClient([_batch(_bad_measure())] * 6)
    monkeypatch.setattr("app.services.llm.get_client", lambda: client)

    got, why = await sd.suggest_dashboards(CATALOG, for_role="Instructor", count=1)

    assert got == []
    assert len(client.calls) == 2, f"asked the model {len(client.calls)} times"


# ---------------------------------------------------------------------------
# The join paths. Twice through the real chat the model invented
# `mdl_user_enrolments.courseid` -- that table reaches a course through
# `mdl_enrol`, and the column does not exist. It kept inventing it through the
# repair round too, which is the tell that this is not carelessness: the prompt
# listed every table and every column and never said how they connect, so the
# model had to guess, and it guessed the same reasonable-but-wrong thing twice.
#
# The sync already knows. It found 19 declared foreign keys on this database and
# wrote them down. Handing them over is cheaper than any amount of repair.
# ---------------------------------------------------------------------------

CATALOG_WITH_JOINS = CATALOG + [{
    "name": "mdl_user_enrolments",
    "description": "Links a user to an enrolment.",
    "columns": [{"name": "userid", "dtype": "integer"},
                {"name": "enrolid", "dtype": "integer"}],
}]

JOINS = [
    {"from_table": "mdl_user_enrolments", "from_column": "enrolid",
     "to_table": "mdl_enrol", "to_column": "id"},
    {"from_table": "mdl_grade_grades", "from_column": "userid",
     "to_table": "mdl_user", "to_column": "id"},
]


def test_the_prompt_states_how_the_tables_join():
    text = " ".join(m["content"] for m in
                    build_prompt(CATALOG_WITH_JOINS, "Instructor", joins=JOINS))
    assert "mdl_user_enrolments.enrolid" in text
    assert "mdl_enrol.id" in text


def test_the_prompt_forbids_inventing_a_join():
    text = " ".join(m["content"] for m in
                    build_prompt(CATALOG_WITH_JOINS, "Instructor", joins=JOINS))
    assert "join" in text.lower()
    assert "do not invent" in text.lower() or "only the joins" in text.lower()


def test_a_source_with_no_known_joins_still_produces_a_prompt():
    """Inference finds nothing on some databases. Fewer hints, not a crash."""
    assert build_prompt(CATALOG, "Instructor", joins=[])
    assert build_prompt(CATALOG, "Instructor", joins=None)


async def test_the_joins_reach_the_batch_prompt(monkeypatch):
    client = FakeClient([_batch(_titled("A"))])
    monkeypatch.setattr("app.services.llm.get_client", lambda: client)

    await sd.suggest_dashboards(CATALOG_WITH_JOINS, for_role="Instructor",
                                count=1, joins=JOINS)

    text = " ".join(m["content"] for m in client.calls[0])
    assert "mdl_user_enrolments.enrolid" in text


# ---------------------------------------------------------------------------
# The empty-dashboard rung. The first dashboard built from the chat came out
# blank: every tile drew "—". The SQL was valid, ran without error, and returned
# zero rows, because the model proposed "Today's Pulse" and filtered to the last
# 7 days — while the newest event in that database is three months old.
#
# "It executes" is not the same as "it has data in it", and a dashboard of empty
# tiles is exactly the confident-looking wrong answer this module keeps trying to
# avoid. So the probe reports the row count, and a proposal that returns nothing
# is sent back with the reason.
# ---------------------------------------------------------------------------


async def test_a_proposal_that_returns_no_rows_is_rejected(monkeypatch):
    client = FakeClient([_batch(_titled("Empty")), _batch(_titled("Empty"))])
    monkeypatch.setattr("app.services.llm.get_client", lambda: client)

    async def probe(sql):
        return "returned no rows"

    got, why = await sd.suggest_dashboards(CATALOG, for_role="Instructor",
                                           count=1, probe=probe)

    assert got == []
    assert "no rows" in why


async def test_the_repair_is_told_the_dashboard_was_empty(monkeypatch):
    client = FakeClient([_batch(_titled("Empty")), _batch(_titled("Filled"))])
    monkeypatch.setattr("app.services.llm.get_client", lambda: client)
    seen = []

    async def probe(sql):
        seen.append(sql)
        return "returned no rows" if len(seen) == 1 else None

    got, _ = await sd.suggest_dashboards(CATALOG, for_role="Instructor",
                                         count=1, probe=probe)

    assert [p["title"] for p in got] == ["Filled"]
    retry = " ".join(m["content"] for m in client.calls[1])
    assert "no rows" in retry


def test_the_prompt_states_how_current_the_data_is():
    """The model has no clock and the database is not live. Told that the newest
    row is from June, it stops proposing a dashboard about today."""
    text = " ".join(m["content"] for m in build_prompt(
        CATALOG, "Instructor", data_range="2023-09-14 to 2026-06-14"))
    assert "2026-06-14" in text
    assert "today" in text.lower() or "recent" in text.lower()
