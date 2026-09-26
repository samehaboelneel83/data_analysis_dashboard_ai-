"""Every number in an Ask AI answer is traced to the rows it came from (E11).

The plan's criterion: "every numerical claim links to computed evidence". The
answer's prose is a model's; these tests pin the deterministic check that
reads it back against the result rows (services/agent/evidence.py) and the
API that carries the trace to the chat.
"""
import pytest

from app.models.models import AgentRun, AgentStep, DataSource
from app.services.agent.evidence import trace_claims

REGIONS = {"columns": ["region", "revenue", "share"],
           "rows": [["North", 12431.2, 0.382], ["South", 8200, 0.25],
                    ["East", 4000, 0.123]],
           "total": 3, "truncated": False}


def claims(answer, results=(REGIONS,), question="", sqls=()):
    got = trace_claims(answer, question, list(results), list(sqls))
    return [(c["text"], c["status"], (c.get("source") or {}).get("kind"),
             (c.get("source") or {}).get("row"), (c.get("source") or {}).get("column"))
            for c in got["claims"]]


class TestNumbersFoundInTheRows:
    def test_a_stated_cell_is_linked_to_its_row_and_column(self):
        assert claims("North had 12,431.2 in revenue.") == [
            ("12,431.2", "traced", "cell", 0, "revenue")]

    def test_the_span_is_the_number_as_written(self):
        got = trace_claims("South: 8,200.", "", [REGIONS], [])["claims"][0]
        assert "South: 8,200."[got["start"]:got["end"]] == "8,200" == got["text"]

    @pytest.mark.parametrize("written", ["12431.2", "12,431", "12.4K", "12.43 thousand"])
    def test_a_rounded_or_scaled_figure_matches_at_its_own_precision(self, written):
        assert claims(f"North: {written}.")[0][1:3] == ("traced", "cell")

    def test_a_percentage_matches_a_share_stored_as_a_fraction(self):
        assert claims("North is 38.2% of the total.")[0][1:5] == ("traced", "cell", 0, "share")
        assert claims("North is 38% of the total.")[0][1] == "traced"

    def test_trailing_zeros_in_a_large_integer_read_as_rounding(self):
        big = {"columns": ["k", "v"], "rows": [["a", 12431]], "total": 1, "truncated": False}
        assert claims("About 12,400.", [big])[0][1] == "traced"
        assert claims("About 12,000.", [big])[0][1] == "traced"
        assert claims("About 13,000.", [big])[0][1] == "untraced"
        small = {"columns": ["k", "v"], "rows": [["a", 2400]], "total": 1, "truncated": False}
        # At least two significant digits are kept: "2,000" is 1,950-2,049.
        assert claims("About 2,000.", [small])[0][1] == "untraced"

    def test_a_decrease_stated_without_its_sign(self):
        change = {"columns": ["region", "delta"], "rows": [["East", -5]], "total": 1, "truncated": False}
        assert claims("East fell by 5.", [change])[0][1] == "traced"

    def test_arabic_indic_digits_and_separators(self):
        assert [c[1] for c in claims("الشمال ١٢٬٤٣١٫٢ أي ٣٨٫٢٪")] == ["traced", "traced"]

    def test_the_row_the_sentence_names_wins_when_two_rows_hold_the_value(self):
        tie = {"columns": ["region", "orders"], "rows": [["North", 7], ["South", 7]],
               "total": 2, "truncated": False}
        assert claims("South had 7 orders.", [tie])[0][3] == 1
        assert claims("North had 7 orders.", [tie])[0][3] == 0

    def test_a_count_of_the_rows(self):
        assert claims("There are 3 regions.")[0][1:3] == ("traced", "count")

    def test_the_second_result_is_named_by_its_index(self):
        other = {"columns": ["n"], "rows": [[91]], "total": 1, "truncated": False}
        got = trace_claims("There were 91.", "", [REGIONS, other], [])["claims"][0]
        assert got["source"]["result"] == 1


class TestArithmeticOverTheRows:
    def test_a_total_and_an_average_of_a_column(self):
        assert claims("The total is 24,631.2, an average of 8,210.4.") == [
            ("24,631.2", "traced", "sum", None, "revenue"),
            ("8,210.4", "traced", "average", None, "revenue")]

    def test_a_share_difference_and_change_between_named_rows(self):
        got = claims("North is 50.5% of revenue and beats South by 4,231.2 (51.6% more).")
        assert [c[2] for c in got] == ["share", "difference", "change"]

    def test_a_difference_the_sentence_does_not_tie_to_rows_is_not_taken(self):
        # 4,231.2 IS North minus South, but nothing says so: among many rows
        # some pair differs by almost any number, so a bare figure is not
        # traced through a difference.
        assert claims("The gap is 4,231.2.")[0][1] == "untraced"

    def test_no_arithmetic_over_a_partial_result(self):
        head = {**REGIONS, "total": 5000, "truncated": True}
        assert claims("The total is 24,631.2.", [head])[0][1] == "untraced"


class TestNumbersNotFound:
    def test_an_invented_figure_is_untraced(self):
        got = trace_claims("North had 13,900 in revenue.", "", [REGIONS], [])
        assert got["untraced"] == 1
        assert got["claims"][0]["status"] == "untraced"
        assert "source" not in got["claims"][0]

    def test_a_misread_figure_is_untraced(self):
        assert claims("North had 12,341.2.")[0][1] == "untraced"


class TestNotClaims:
    def test_numbers_from_the_question_are_context(self):
        assert claims("The top 5 regions: North first.", question="top 5 regions")[0][1] == "context"

    def test_sql_literals_are_context(self):
        got = claims("Of the 10 largest, North leads.", sqls=["SELECT * FROM t LIMIT 10"])
        assert got[0][1] == "context"

    def test_dates_times_quoted_names_and_identifiers_are_skipped(self):
        assert claims('On 2024-03-01 at 14:30 "Sales 2024" had Q3 and step_1.') == []

    def test_nothing_to_trace_against(self):
        assert trace_claims("It is 5.", "", [], []) is None
        assert trace_claims(None, "", [REGIONS], []) is None


# ── Through the API ─────────────────────────────────────────────────────────

SNAPSHOT = {"columns": ["city", "n"], "rows": [["Cairo", 3], ["Giza", 1]],
            "total": 2, "truncated": False}


@pytest.fixture
def scripted(monkeypatch):
    answers = {}

    async def fake_run(db, *, question, user, client, source=None, datasets=None,
                       conversation_id=None, history=None, **kw):
        run = AgentRun(org_id=user.org_id, conversation_id=conversation_id,
                       question=question, status="ok", intent="lookup",
                       answer=answers.get(question, "Cairo has 3, Giza 9."))
        db.add(run)
        await db.flush()
        db.add(AgentStep(agent_run_id=run.id, node="s1", status="ok",
                         sql="SELECT city, n FROM t", rows_returned=2,
                         result_rows=SNAPSHOT))
        await db.flush()
        return run
    monkeypatch.setattr("app.routers.agent.run_agent", fake_run)
    return answers


@pytest.fixture
async def source(db_session, two_orgs):
    src = DataSource(name="wh-a", type="postgresql", org_id=two_orgs["a"]["org"].id)
    db_session.add(src)
    await db_session.commit()
    return src


class TestTheChatReceivesTheTrace:
    async def test_ask_and_the_stored_conversation_carry_the_same_trace(
            self, client, auth_headers, source, scripted):
        h = auth_headers["a"]
        cid = (await client.post("/api/v1/agent/conversations",
                                 json={"data_source_id": source.id}, headers=h)).json()["id"]
        got = (await client.post(f"/api/v1/agent/conversations/{cid}/ask",
                                 json={"question": "orders per city"}, headers=h)).json()
        ev = got["evidence"]
        assert ev["untraced"] == 1
        assert [(c["text"], c["status"]) for c in ev["claims"]] == [
            ("3", "traced"), ("9", "untraced")]
        assert ev["claims"][0]["source"] == {"result": 0, "row": 0, "column": "n",
                                             "value": 3, "kind": "cell"}
        msgs = (await client.get(f"/api/v1/agent/conversations/{cid}/messages",
                                 headers=h)).json()
        assert msgs[1]["run"]["evidence"] == ev

    async def test_a_reply_with_no_query_has_no_trace(self, client, auth_headers,
                                                      source, monkeypatch):
        async def chat_run(db, *, question, user, client, conversation_id=None, **kw):
            run = AgentRun(org_id=user.org_id, conversation_id=conversation_id,
                           question=question, status="ok", intent="chat",
                           answer="Hello! I can count 3 things.")
            db.add(run)
            await db.flush()
            return run
        monkeypatch.setattr("app.routers.agent.run_agent", chat_run)
        h = auth_headers["a"]
        cid = (await client.post("/api/v1/agent/conversations",
                                 json={"data_source_id": source.id}, headers=h)).json()["id"]
        got = (await client.post(f"/api/v1/agent/conversations/{cid}/ask",
                                 json={"question": "hi"}, headers=h)).json()
        assert got["evidence"] is None
