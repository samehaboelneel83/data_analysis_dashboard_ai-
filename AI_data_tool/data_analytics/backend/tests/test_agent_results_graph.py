"""The graph keeps a result snapshot on SINK steps and records which tables
the context ranked first -- the two facts the chat needs to draw a result and
explain a table choice. Shares test_agent_graph's world and scripted model."""
import asyncio

from sqlalchemy import select

from app.models.models import AgentStep, QueryExample
from app.services.agent.charts import MAX_MARKS, MAX_OPTIONS, pick_axes, validated_axes
from app.services.agent.graph import run_agent
from tests.test_agent_graph import (NOT_AMBIGUOUS, ONE_STEP, TWO_STEP_CHAIN,  # noqa: F401
                                    ScriptedClient, world)


class FollowupClient(ScriptedClient):
    """ScriptedClient plus the follow-up resolver's schema (keyed on `kind`)
    and a record of every classify prompt, so a test can see whether the
    conversation reached it."""

    def __init__(self, *a, followup=None, **kw):
        super().__init__(*a, **kw)
        self.script["followup"] = list(followup or [])
        self.followup_calls = []
        self.classify_calls = []

    async def complete_json(self, messages, schema, **kw):
        props = set(schema.get("properties", {}))
        joined = "".join(m["content"] for m in messages)
        if "kind" in props:
            self.followup_calls.append(joined)
            return self.script["followup"].pop(0) if self.script["followup"] else None
        if "intent" in props:
            self.classify_calls.append(joined)
        return await super().complete_json(messages, schema, **kw)


PREV_SQL = "SELECT region, total FROM orders ORDER BY id"
PREV_SNAP = {"step": "s1", "columns": ["region", "total"],
             "rows": [["west", 10.0], ["east", 20.0]], "total": 2, "truncated": False}
HISTORY = [
    {"role": "user", "content": "orders by region", "sql": [], "results": []},
    {"role": "assistant", "content": "West 10, east 20.", "sql": [PREV_SQL],
     "results": [PREV_SNAP]},
]


class TestSnapshots:
    async def test_a_single_step_run_keeps_its_rows(self, db_session, world):
        client = ScriptedClient(
            classify=[NOT_AMBIGUOUS], plan=[ONE_STEP],
            generate=[{"sql": "SELECT region, total FROM orders ORDER BY id"}])
        run = await run_agent(db_session, question="orders by region",
                              source=world["ds"], user=world["user"], client=client)
        await db_session.commit()
        step = (await db_session.execute(select(AgentStep))).scalar_one()
        assert step.result_rows == {
            "columns": ["region", "total"],
            "rows": [["west", 10.0], ["east", 20.0]],
            "total": 2, "truncated": False}
        assert step.rows_returned == 2
        assert run.presentation is None

    async def test_only_the_sink_step_is_snapshotted(self, db_session, world):
        # s1 feeds s2; its rows were consumed by parent_facts and must not
        # be re-shown as if they were an answer.
        client = ScriptedClient(
            classify=[NOT_AMBIGUOUS], plan=[TWO_STEP_CHAIN],
            generate=[{"sql": "SELECT id FROM orders"},
                      {"sql": "SELECT sum(total) AS t FROM orders"}])
        run = await run_agent(db_session, question="q", source=world["ds"],
                              user=world["user"], client=client)
        await db_session.commit()
        assert run.status == "ok"
        steps = {s.node: s for s in
                 (await db_session.execute(select(AgentStep))).scalars().all()}
        assert steps["s1"].result_rows is None
        assert steps["s2"].result_rows["columns"] == ["t"]
        assert steps["s2"].result_rows["rows"] == [[30.0]]

    async def test_a_failed_step_has_no_snapshot(self, db_session, world):
        bad = {"sql": "SELECT ghost FROM orders"}
        client = ScriptedClient(classify=[NOT_AMBIGUOUS], plan=[ONE_STEP],
                                generate=[bad, bad, bad])
        run = await run_agent(db_session, question="q", source=world["ds"],
                              user=world["user"], client=client)
        await db_session.commit()
        assert run.status == "failed"
        step = (await db_session.execute(select(AgentStep))).scalar_one()
        assert step.result_rows is None


class TestCredentialRedaction:
    async def test_credential_values_never_reach_snapshot_or_explain(
            self, db_session, world):
        # The world's table has no credential column, so the SQL aliases one
        # into existence -- which is exactly how a real SELECT would surface
        # it. Both the stored snapshot and explain's figures must carry the
        # mask, never the value.
        client = ScriptedClient(
            classify=[NOT_AMBIGUOUS], plan=[ONE_STEP],
            generate=[{"sql": "SELECT region AS password_hash, total FROM orders"}])
        run = await run_agent(db_session, question="sample the users",
                              source=world["ds"], user=world["user"], client=client)
        await db_session.commit()
        assert run.status == "ok"
        step = (await db_session.execute(select(AgentStep))).scalar_one()
        assert step.result_rows["columns"] == ["password_hash", "total"]
        assert set(r[0] for r in step.result_rows["rows"]) == {"•••"}
        assert "west" not in client.explain_calls[0]
        assert "•••" in client.explain_calls[0]


class TestTablesConsidered:
    async def test_the_run_records_the_ranked_objects(self, db_session, world):
        client = ScriptedClient(
            classify=[NOT_AMBIGUOUS], plan=[ONE_STEP],
            generate=[{"sql": "SELECT sum(total) AS total FROM orders"}])
        run = await run_agent(db_session, question="total of orders",
                              source=world["ds"], user=world["user"], client=client)
        await db_session.commit()
        assert run.context_objects == ["orders"]


class TestFollowUps:
    async def test_a_presentation_follow_up_reshows_the_last_result_without_sql(
            self, db_session, world):
        client = FollowupClient(
            followup=[{"kind": "presentation", "question": "as a table",
                       "format": "table", "limit": None}])
        run = await run_agent(db_session, question="can you present a table",
                              source=world["ds"], user=world["user"],
                              client=client, history=HISTORY)
        await db_session.commit()
        assert run.status == "ok"
        assert run.intent == "present"
        assert run.presentation == {"format": "table", "limit": None,
                                    "x": None, "y": None}
        assert run.answer
        # Nothing was classified, planned or generated: the rows already existed.
        assert client.classify_calls == []
        assert client.generate_calls == []
        step = (await db_session.execute(select(AgentStep))).scalar_one()
        assert step.result_rows == {k: PREV_SNAP[k] for k in ("columns", "rows", "total", "truncated")}
        assert step.sql == PREV_SQL      # "Show SQL" still explains the rows
        # ...but "as a table" is not a verified question for that SQL.
        assert (await db_session.execute(select(QueryExample))).scalars().all() == []

    async def test_a_limit_slices_the_reshown_rows(self, db_session, world):
        client = FollowupClient(
            followup=[{"kind": "presentation", "question": "first row only",
                       "format": "table", "limit": 1}])
        run = await run_agent(db_session, question="just show the first one",
                              source=world["ds"], user=world["user"],
                              client=client, history=HISTORY)
        await db_session.commit()
        step = (await db_session.execute(select(AgentStep))).scalar_one()
        assert step.result_rows["rows"] == [["west", 10.0]]
        assert step.result_rows["total"] == 2
        assert step.result_rows["truncated"] is True
        assert run.presentation == {"format": "table", "limit": 1,
                                    "x": None, "y": None}

    async def test_a_data_follow_up_runs_the_standalone_rewrite(self, db_session, world):
        client = FollowupClient(
            followup=[{"kind": "data",
                       "question": "total of orders in the west region",
                       "format": None, "limit": None}],
            classify=[NOT_AMBIGUOUS], plan=[ONE_STEP],
            generate=[{"sql": "SELECT sum(total) AS t FROM orders WHERE region = 'west'"}])
        run = await run_agent(db_session, question="the same for west",
                              source=world["ds"], user=world["user"],
                              client=client, history=HISTORY)
        await db_session.commit()
        assert run.status == "ok"
        assert run.presentation is None
        assert run.question == "the same for west"   # what was typed
        # The rewrite, not the fragment, is what classify and generate saw --
        # and both also saw the conversation itself.
        # "Conversation so far:" with the colon is the rendered block; the
        # system prompt mentions the phrase itself when explaining the rule.
        assert "total of orders in the west region" in client.classify_calls[0]
        assert "Conversation so far:" in client.classify_calls[0]
        assert "orders by region" in client.classify_calls[0]
        assert "Conversation so far (" in client.generate_calls[0]
        assert PREV_SQL in client.generate_calls[0]
        # The verified example is the standalone question, which is reusable.
        ex = (await db_session.execute(select(QueryExample))).scalar_one()
        assert ex.question == "total of orders in the west region"

    async def test_no_history_means_no_resolver_call(self, db_session, world):
        client = FollowupClient(
            classify=[NOT_AMBIGUOUS], plan=[ONE_STEP],
            generate=[{"sql": "SELECT sum(total) AS total FROM orders"}])
        run = await run_agent(db_session, question="total sales",
                              source=world["ds"], user=world["user"], client=client)
        assert run.status == "ok"
        assert client.followup_calls == []
        assert "Conversation so far:" not in client.classify_calls[0]
        assert "orders by region" not in client.classify_calls[0]

    async def test_a_presentation_request_with_no_earlier_rows_queries_instead(
            self, db_session, world):
        bare = [{"role": "user", "content": "hi", "sql": [], "results": []},
                {"role": "assistant", "content": "Which table?", "sql": [], "results": []}]
        client = FollowupClient(
            followup=[{"kind": "presentation", "question": "orders as a table",
                       "format": "table", "limit": None}],
            classify=[NOT_AMBIGUOUS], plan=[ONE_STEP],
            generate=[{"sql": "SELECT region, total FROM orders"}])
        run = await run_agent(db_session, question="as a table",
                              source=world["ds"], user=world["user"],
                              client=client, history=bare)
        assert run.status == "ok"
        assert run.presentation is None
        assert client.generate_calls, "no rows to re-show, so the database was asked"

    async def test_resolver_failure_degrades_to_the_question_as_typed(
            self, db_session, world):
        client = FollowupClient(
            followup=[],   # the model never satisfies the contract
            classify=[NOT_AMBIGUOUS], plan=[ONE_STEP],
            generate=[{"sql": "SELECT sum(total) AS total FROM orders"}])
        run = await run_agent(db_session, question="total sales",
                              source=world["ds"], user=world["user"],
                              client=client, history=HISTORY)
        assert run.status == "ok"
        assert "total sales" in client.classify_calls[0]


class TestTheFollowUpsThatNeverQuery:
    """The second turn has its own door out of SQL, and it needs one.

    classify's `chat` intent catches "hi" as a FIRST message, but a later one
    never reaches classify: the resolver runs first and, with only `data` and
    `presentation` to choose from, rewrote "thanks" into a standalone data
    question that was then queried. `describe` is the same gap on the other
    side -- "explain this chart" is about rows that already exist, and sent on
    to classify it hit the `explain` INTENT, which means the key-influencers
    analysis, and answered about a column nobody had named."""

    async def test_a_chat_follow_up_is_answered_without_classifying_it(
            self, db_session, world):
        client = FollowupClient(
            followup=[{"kind": "chat", "question": "thanks",
                       "format": None, "limit": None}],
            prose="You're welcome.")
        run = await run_agent(db_session, question="thanks", source=world["ds"],
                              user=world["user"], client=client, history=HISTORY)
        await db_session.commit()
        assert run.status == "ok"
        assert run.intent == "chat"
        assert run.answer == "You're welcome."
        assert client.classify_calls == []
        assert client.generate_calls == []
        # Nothing is re-shown either: "thanks" did not ask for the rows again.
        assert (await db_session.execute(select(AgentStep))).scalars().all() == []

    async def test_describe_explains_the_rows_that_already_exist(
            self, db_session, world):
        client = FollowupClient(
            followup=[{"kind": "describe",
                       "question": "Explain the orders by region result",
                       "format": None, "limit": None}],
            prose="West took 10 and east 20, so east is twice west.")
        run = await run_agent(db_session, question="explain this chart",
                              source=world["ds"], user=world["user"],
                              client=client, history=HISTORY)
        await db_session.commit()
        assert run.status == "ok"
        assert run.intent == "describe"
        assert run.answer == "West took 10 and east 20, so east is twice west."
        assert client.classify_calls == []
        assert client.generate_calls == []
        # The rows it explains are the rows it shows, and the SQL behind them
        # rides along so "Show SQL" still accounts for both.
        step = (await db_session.execute(select(AgentStep))).scalar_one()
        assert step.result_rows == {k: PREV_SNAP[k]
                                    for k in ("columns", "rows", "total", "truncated")}
        assert step.sql == PREV_SQL
        # The narration is written FROM figures, never remembered from the
        # conversation text -- and from describe's prompt, not explain's: run
        # through explain's, "explain this chart" came back refusing to draw a
        # chart that was already drawn.
        assert client.explain_calls, "the answer was written from figures"
        assert "ALREADY LOOKING AT" in client.explain_calls[0]
        assert "west" in client.explain_calls[0]

    async def test_a_truncated_snapshot_is_explained_as_a_sample(
            self, db_session, world):
        """The snapshot is capped at RESULT_ROW_CAP and explain() counts the
        rows it is handed, so without the note it would call a 2-row sample of
        4,000 "2 rows" -- the same contradiction _facts already learned once."""
        big = [{"role": "assistant", "content": "lots", "sql": [PREV_SQL],
                "results": [{**PREV_SNAP, "total": 4000, "truncated": True}]}]
        client = FollowupClient(
            followup=[{"kind": "describe", "question": "explain it",
                       "format": None, "limit": None}],
            prose="A sample of 2 of 4000 rows.")
        run = await run_agent(db_session, question="what does this mean",
                              source=world["ds"], user=world["user"],
                              client=client, history=big)
        assert run.status == "ok"
        assert "shows 2 of 4000 rows" in client.explain_calls[0]

    async def test_describe_falls_back_to_the_figures_when_prose_fails(
            self, db_session, world):
        """A correct result must not be discarded because prose generation
        failed -- the rule render_fallback already exists for."""
        client = FollowupClient(
            followup=[{"kind": "describe", "question": "explain it",
                       "format": None, "limit": None}],
            prose=None)
        run = await run_agent(db_session, question="explain this chart",
                              source=world["ds"], user=world["user"],
                              client=client, history=HISTORY)
        assert run.status == "ok"
        assert "west" in run.answer

class TestChoosingWhatToChart:
    """"i need chart" says HOW to draw, not WHAT to draw.

    The two pictures that started this: a result whose columns were all
    numeric drew its id column against itself, and one whose numbers never
    changed drew thirty-three identical bars. Both came from the frontend
    guessing two columns. The rows decide now, and when they do not, the
    person is ASKED -- with the real column names as the options.
    """

    FIRST_TEN = {"step": "s1", "columns": ["id", "symbol_code", "institute_code"],
                 "rows": [[718, 5000, 2], [719, 38, 2], [720, 331, 2]],
                 "total": 3, "truncated": False}

    def history(self, snap):
        return [{"role": "user", "content": "show me the rows", "sql": [], "results": []},
                {"role": "assistant", "content": "Here they are.",
                 "sql": [PREV_SQL], "results": [snap]}]

    async def test_two_columns_that_determine_a_pair_are_just_drawn(
            self, db_session, world):
        """The ordinary result -- one label, one measure -- is not a choice,
        and asking about it would be an interrogation, not a clarification."""
        client = FollowupClient(
            followup=[{"kind": "presentation", "question": "as a bar chart",
                       "format": "bar", "limit": None, "x": None, "y": None}])
        run = await run_agent(db_session, question="i need chart",
                              source=world["ds"], user=world["user"],
                              client=client, history=HISTORY)
        await db_session.commit()
        assert run.status == "ok"
        assert run.presentation == {"format": "bar", "limit": None,
                                    "x": "region", "y": "total"}

    async def test_an_all_numeric_result_is_asked_about_not_guessed(
            self, db_session, world):
        """id, symbol_code and a constant: two columns could label and two
        could size, so four pairs would 'work' and the old code drew id
        against itself."""
        client = FollowupClient(
            followup=[{"kind": "presentation", "question": "as a bar chart",
                       "format": "bar", "limit": None, "x": None, "y": None}])
        run = await run_agent(db_session, question="i need chart",
                              source=world["ds"], user=world["user"],
                              client=client, history=self.history(self.FIRST_TEN))
        await db_session.commit()
        assert run.status == "needs_clarification"
        assert run.presentation["kind"] == "choices"
        options = run.presentation["options"]
        assert "Chart symbol_code by id" in options
        assert "Chart id by symbol_code" in options
        # The constant column is on neither axis of any option: every bar
        # would be named the same, or be the same height.
        assert not any("institute_code" in o for o in options)
        # A question is not a result: nothing was re-shown.
        assert (await db_session.execute(select(AgentStep))).scalars().all() == []

    async def test_a_result_with_nothing_varying_says_so(self, db_session, world):
        """Screenshot 4, exactly: institute_code and state_type_code are the
        same in every row, record_count is 1 in every row, and only
        symbol_code varies -- so there is no second column to size the bars
        with. It drew 33 identical bars; now it says why it cannot."""
        flat = {"step": "s1",
                "columns": ["institute_code", "state_type_code", "symbol_code",
                            "record_count"],
                "rows": [[2, 4, 338, 1], [2, 4, 16, 1], [2, 4, 118, 1]],
                "total": 3, "truncated": False}
        client = FollowupClient(
            followup=[{"kind": "presentation", "question": "chart it",
                       "format": "bar", "limit": None, "x": None, "y": None}])
        run = await run_agent(db_session, question="i need suggestion charts",
                              source=world["ds"], user=world["user"],
                              client=client, history=self.history(flat))
        await db_session.commit()
        assert run.status == "needs_clarification"
        assert "symbol_code" in run.answer
        assert "record_count" in run.answer
        # It leads somewhere: the rows can still be read.
        assert run.presentation["options"] == ["Show the rows as a table"]

    async def test_the_columns_a_message_names_are_the_ones_drawn(
            self, db_session, world):
        """The round trip: the option offered above, clicked, comes back
        through the resolver as x and y and is drawn with them."""
        client = FollowupClient(
            followup=[{"kind": "presentation", "question": "Draw symbol_code by id",
                       "format": "bar", "limit": None, "x": "id", "y": "symbol_code"}])
        run = await run_agent(db_session, question="Chart symbol_code by id",
                              source=world["ds"], user=world["user"],
                              client=client, history=self.history(self.FIRST_TEN))
        await db_session.commit()
        assert run.status == "ok"
        assert run.presentation == {"format": "bar", "limit": None,
                                    "x": "id", "y": "symbol_code"}
        step = (await db_session.execute(select(AgentStep))).scalar_one()
        assert step.result_rows["rows"] == self.FIRST_TEN["rows"]

    async def test_a_column_that_is_not_in_the_result_is_not_trusted(
            self, db_session, world):
        """A named column that does not exist falls through to the picker --
        never invented, and never a reason to fail."""
        client = FollowupClient(
            followup=[{"kind": "presentation", "question": "chart revenue by month",
                       "format": "bar", "limit": None, "x": "month", "y": "revenue"}])
        run = await run_agent(db_session, question="chart revenue by month",
                              source=world["ds"], user=world["user"],
                              client=client, history=HISTORY)
        await db_session.commit()
        assert run.status == "ok"
        assert run.presentation["x"] == "region"   # the picker's answer
        assert run.presentation["y"] == "total"

    async def test_a_table_is_never_asked_about(self, db_session, world):
        """Only a chart needs two columns chosen. "as a table" still just
        shows the rows, whatever they contain."""
        client = FollowupClient(
            followup=[{"kind": "presentation", "question": "as a table",
                       "format": "table", "limit": None, "x": None, "y": None}])
        run = await run_agent(db_session, question="show it as a table",
                              source=world["ds"], user=world["user"],
                              client=client, history=self.history(self.FIRST_TEN))
        assert run.status == "ok"
        assert run.presentation["format"] == "table"

class TestPickAxes:
    """`charts.pick_axes` in isolation: the rules, without a run around them."""

    def test_one_label_and_one_measure_is_the_answer_not_a_question(self):
        got = pick_axes(["city", "n"], [["Cairo", 3], ["Giza", 1]])
        assert got == {"outcome": "ok", "x": "city", "y": "n"}

    def test_a_constant_column_is_on_neither_axis(self):
        """It would name every bar the same, or give every bar the same
        height. Dropping it is what leaves one real pair here."""
        got = pick_axes(["city", "n", "year"],
                        [["Cairo", 3, 2026], ["Giza", 1, 2026]])
        assert got == {"outcome": "ok", "x": "city", "y": "n"}

    def test_several_workable_pairs_are_asked_about(self):
        got = pick_axes(["id", "symbol_code"], [[718, 5000], [719, 38]])
        assert got["outcome"] == "ambiguous"
        assert set(got["options"]) == {"Chart symbol_code by id",
                                       "Chart id by symbol_code"}

    def test_only_one_column_varies_so_nothing_can_be_drawn(self):
        got = pick_axes(["institute_code", "symbol_code", "record_count"],
                        [[2, 338, 1], [2, 16, 1], [2, 118, 1]])
        assert got["outcome"] == "flat"
        assert "symbol_code" in got["question"]
        assert got["options"] == ["Show the rows as a table"]

    def test_a_result_where_nothing_varies_at_all(self):
        got = pick_axes(["a", "b"], [[1, 2], [1, 2]])
        assert got["outcome"] == "flat"
        assert "same value in every row" in got["question"]

    def test_a_truncated_snapshot_claims_only_the_rows_it_saw(self):
        """The snapshot is a capped sample, so a column constant across it may
        vary in row 201. The chart still draws these rows -- but the sentence
        must not say "never" about rows nobody looked at."""
        cols = ["institute_code", "symbol_code", "record_count"]
        rows = [[2, 338, 1], [2, 16, 1]]
        assert "in every row shown" in pick_axes(cols, rows, True)["question"]
        assert "in every row." in pick_axes(cols, rows, False)["question"]

    def test_no_rows_is_flat_not_a_crash(self):
        assert pick_axes(["a"], [])["outcome"] == "flat"
        assert pick_axes([], [[1]])["outcome"] == "flat"

    def test_options_are_capped(self):
        cols = [f"c{i}" for i in range(6)]
        rows = [[i * 10 + j for j in range(6)] for i in range(4)]
        got = pick_axes(cols, rows)
        assert got["outcome"] == "ambiguous"
        assert len(got["options"]) == MAX_OPTIONS

    def test_thousands_of_distinct_labels_are_not_a_chart(self):
        """Live: a continuous score grouped into 5,000 distinct values, then
        drawn as 5,000 bars. Correct data, unreadable picture."""
        rows = [[i / 10, 1] for i in range(MAX_MARKS + 50)]
        got = pick_axes(["finalgrade", "user_count"], rows)
        assert got["outcome"] == "flat"
        assert "distinct values" in got["question"]
        assert "ranges" in got["question"]
        assert got["options"] == ["Show the rows as a table"]

    def test_a_crowded_label_yields_to_a_readable_one(self):
        """When another label would draw, the crowded one is simply not
        offered -- no refusal, no question."""
        rows = [[i / 10, "a" if i % 2 else "b", 1] for i in range(MAX_MARKS + 50)]
        got = pick_axes(["score", "band", "n"], rows)
        assert got["outcome"] == "ok"
        assert got["x"] == "band"

    def test_booleans_are_not_measures(self):
        """True is not a number to size a bar with; it is a category."""
        got = pick_axes(["flag", "n"], [[True, 3], [False, 5]])
        assert got == {"outcome": "ok", "x": "flag", "y": "n"}


class TestValidatedAxes:
    def test_columns_of_this_result_pass_whatever_their_case(self):
        assert validated_axes("symbol_code", "ID", ["ID", "SYMBOL_CODE"]) ==             ("SYMBOL_CODE", "ID")

    def test_anything_else_is_dropped_rather_than_invented(self):
        assert validated_axes("month", "revenue", ["city", "n"]) == (None, None)
        assert validated_axes(None, None, ["city", "n"]) == (None, None)
        # The same column on both axes is the bug this whole path exists for.
        assert validated_axes("city", "city", ["city", "n"]) == (None, None)

DESCRIBE = {"intent": "describe_data", "ambiguous": False, "ambiguity_reason": None}


class TestDescribingWhatTheDataIs:
    """"describe this dataset", answered from the CATALOG and by the query.

    Live, over a seventeen-table connection, this question was answered with
    four COUNT(*)s over four tables the model chose -- correct numbers, and a
    narrowing the reader was never told about. The catalog knows all
    seventeen, so the description comes from there and the query keeps its
    job: the two arrive together, the listing first.
    """

    async def test_the_catalog_listing_leads_and_the_query_still_runs(
            self, db_session, world):
        client = ScriptedClient(
            classify=[DESCRIBE], plan=[ONE_STEP],
            generate=[{"sql": "SELECT count(*) AS n FROM orders"}])
        run = await run_agent(db_session, question="describe this data",
                              source=world["ds"], user=world["user"], client=client)
        await db_session.commit()
        assert run.status == "ok"
        assert run.intent == "describe_data"
        steps = (await db_session.execute(
            select(AgentStep).order_by(AgentStep.id))).scalars().all()
        assert [s.node for s in steps] == ["catalog", "s1"]
        # The description: this source has one table, so describing it is
        # listing its columns.
        assert steps[0].result_rows["columns"] == ["column", "type"]
        assert ["id", "integer"] in steps[0].result_rows["rows"]
        # ...and it carries no SQL, because no SQL produced it.
        assert steps[0].sql is None
        # The query ran anyway: the numbers are still there.
        assert steps[1].sql == "SELECT count(*) AS n FROM orders"
        assert steps[1].rows_returned == 1

    async def test_both_results_are_narrated(self, db_session, world):
        """explain() sees the listing as well as the rows, so the answer can
        say what the data is AND what the query found."""
        client = ScriptedClient(
            classify=[DESCRIBE], plan=[ONE_STEP],
            generate=[{"sql": "SELECT count(*) AS n FROM orders"}])
        await run_agent(db_session, question="describe this data",
                        source=world["ds"], user=world["user"], client=client)
        figures = client.explain_calls[0]
        assert "the data catalog" in figures   # the listing reached the prose
        assert "rows from orders" in figures   # so did the count, by its table

    async def test_a_query_that_cannot_be_written_does_not_delete_the_description(
            self, db_session, world):
        """Measured live, run 162: "what this data" reached the catalog
        listing -- 17 tables, computed -- and then the model could not write
        SQL for the fragment. The failed step took the listing down with it
        and the person saw "no SQL produced". The query is the EXTRA here; its
        failure is a note on the answer, never the answer."""
        client = ScriptedClient(
            classify=[DESCRIBE], plan=[ONE_STEP], generate=[])  # no SQL ever
        run = await run_agent(db_session, question="what this data",
                              source=world["ds"], user=world["user"], client=client)
        await db_session.commit()
        assert run.status == "ok"
        assert run.answer
        # The listing survived and is what the answer is written from...
        assert "catalog" in client.explain_calls[0]
        # ...and the reader is told the query was tried and failed.
        assert "no query could be written" in client.explain_calls[0]

    async def test_the_query_is_on_a_clock_and_the_description_is_not(
            self, db_session, world, monkeypatch):
        """Measured live: 31 seconds inside ONE generate call that returned no
        SQL, while the listing had been ready in under a second. The
        description does not wait for a number that may never come."""
        from app.services.agent import graph as graph_mod
        monkeypatch.setattr(graph_mod, "DESCRIBE_QUERY_BUDGET_S", 0.05)

        class SlowClient(ScriptedClient):
            async def complete_json(self, messages, schema, **kw):
                if "sql" in set(schema.get("properties", {})):
                    await asyncio.sleep(0.5)      # longer than the budget
                return await super().complete_json(messages, schema, **kw)

        client = SlowClient(classify=[DESCRIBE], plan=[ONE_STEP],
                            generate=[{"sql": "SELECT count(*) AS n FROM orders"}])
        run = await run_agent(db_session, question="describe this data",
                              source=world["ds"], user=world["user"], client=client)
        await db_session.commit()
        assert run.status == "ok"
        assert "timed out" in client.explain_calls[0]
        # The listing is still the answer, and still stored.
        steps = (await db_session.execute(select(AgentStep))).scalars().all()
        assert [s.node for s in steps] == ["catalog"]

    async def test_an_ordinary_question_is_never_cut_short(
            self, db_session, world, monkeypatch):
        """The clock exists because a description can stand alone. A real
        question has nothing to fall back on, so it waits."""
        from app.services.agent import graph as graph_mod
        monkeypatch.setattr(graph_mod, "DESCRIBE_QUERY_BUDGET_S", 0.05)

        class SlowClient(ScriptedClient):
            async def complete_json(self, messages, schema, **kw):
                if "sql" in set(schema.get("properties", {})):
                    await asyncio.sleep(0.2)
                return await super().complete_json(messages, schema, **kw)

        client = SlowClient(classify=[NOT_AMBIGUOUS], plan=[ONE_STEP],
                            generate=[{"sql": "SELECT count(*) AS n FROM orders"}])
        run = await run_agent(db_session, question="how many orders",
                              source=world["ds"], user=world["user"], client=client)
        assert run.status == "ok"
        assert client.generate_calls

    async def test_a_failed_step_still_fails_an_ordinary_question(
            self, db_session, world):
        """The rescue is for a description that stands alone -- not a licence
        to answer a real question with a partial one."""
        client = ScriptedClient(
            classify=[NOT_AMBIGUOUS], plan=[ONE_STEP], generate=[])
        run = await run_agent(db_session, question="how many orders",
                              source=world["ds"], user=world["user"], client=client)
        assert run.status == "failed"
        assert "no SQL produced" in (run.error or "")

    async def test_an_ordinary_question_gains_no_listing(self, db_session, world):
        """Additive or it is a regression: only a question that ASKS what the
        data is gets the catalog beside its answer."""
        client = ScriptedClient(
            classify=[NOT_AMBIGUOUS], plan=[ONE_STEP],
            generate=[{"sql": "SELECT count(*) AS n FROM orders"}])
        await run_agent(db_session, question="how many orders",
                        source=world["ds"], user=world["user"], client=client)
        await db_session.commit()
        steps = (await db_session.execute(select(AgentStep))).scalars().all()
        assert [s.node for s in steps] == ["s1"]

    async def test_the_same_question_routes_the_same_way_on_a_later_turn(
            self, db_session, world):
        """The bug that started this: asked as turn 1 it reached classify and
        returned rows; asked as turn 3 the follow-up resolver called it small
        talk and answered from the column names. One question, one route."""
        client = FollowupClient(
            followup=[{"kind": "data", "question": "describe this dataset",
                       "format": None, "limit": None, "x": None, "y": None}],
            classify=[DESCRIBE], plan=[ONE_STEP],
            generate=[{"sql": "SELECT count(*) AS n FROM orders"}])
        run = await run_agent(db_session, question="describe this dataset",
                              source=world["ds"], user=world["user"],
                              client=client, history=HISTORY)
        await db_session.commit()
        assert run.intent == "describe_data"
        assert client.classify_calls, "it reached the classifier, not the chat exit"

class TestChartingATurnThatAlsoDescribesTheData:
    """A describe run carries TWO results: the catalog listing, and the rows
    the query returned. The listing comes first.

    Traced live, twice. "i need suggest charts to add to dashoard" and then
    "i need bar chart to explain this data" were both refused with "only
    column, type varies" -- the listing's own columns -- while a 35-row
    result sat behind it on the very same turn. Anything that reaches for
    "the rows" by taking the FIRST result with rows gets the description."""

    DESCRIBE_TURN = {
        "role": "assistant", "content": "13 columns, and Europe leads.",
        "sql": [None, "SELECT region, count(*) AS n FROM demo_sales GROUP BY region"],
        "results": [
            {"step": "catalog", "source": "catalog", "columns": ["column", "type"],
             "rows": [["region", "categorical"], ["revenue", "numeric"]],
             "total": 13, "truncated": False},
            {"step": "s1", "source": "query", "columns": ["region", "n"],
             "rows": [["Europe", 514], ["Asia Pacific", 517]],
             "total": 4, "truncated": False},
        ],
    }

    async def test_the_chart_draws_the_data_not_the_description(
            self, db_session, world):
        client = FollowupClient(
            followup=[{"kind": "presentation", "question": "bar chart",
                       "format": "bar", "limit": None, "x": None, "y": None}])
        run = await run_agent(db_session, question="i need bar chart to explain this data",
                              source=world["ds"], user=world["user"],
                              client=client, history=[self.DESCRIBE_TURN])
        await db_session.commit()
        assert run.status == "ok", run.answer
        assert run.presentation == {"format": "bar", "limit": None,
                                    "x": "region", "y": "n"}
        # ONE picture: the listing is not copied beside it.
        steps = (await db_session.execute(select(AgentStep))).scalars().all()
        assert [s.node for s in steps] == ["s1"]
        assert steps[0].result_rows["columns"] == ["region", "n"]

    async def test_a_table_still_shows_everything_including_the_listing(
            self, db_session, world):
        """Only CHARTING has to choose. "Show the rows as a table" after a
        describe means everything that turn produced."""
        client = FollowupClient(
            followup=[{"kind": "presentation", "question": "as a table",
                       "format": "table", "limit": None, "x": None, "y": None}])
        run = await run_agent(db_session, question="show the rows as a table",
                              source=world["ds"], user=world["user"],
                              client=client, history=[self.DESCRIBE_TURN])
        await db_session.commit()
        assert run.status == "ok"
        steps = (await db_session.execute(
            select(AgentStep).order_by(AgentStep.id))).scalars().all()
        assert [s.node for s in steps] == ["catalog", "s1"]

    async def test_a_turn_with_only_a_description_is_not_charted_at_all(
            self, db_session, world):
        """The four-turn loop: describe, then chart, and the only rows in the
        conversation are the listing. It must not be drawn, and it must not
        dead-end -- the request goes and reads the dataset instead."""
        listing_only = {**self.DESCRIBE_TURN,
                        "results": [self.DESCRIBE_TURN["results"][0]]}
        client = FollowupClient(
            followup=[{"kind": "presentation", "question": "bar chart",
                       "format": "bar", "limit": None, "x": None, "y": None}])
        run = await run_agent(db_session, question="i need bar chart",
                              source=world["ds"], user=world["user"],
                              client=client, history=[listing_only])
        await db_session.commit()
        # Source mode has no frame to read, so it asks -- but it asks about
        # the DATA, never offering "only column, type varies" again.
        assert run.status == "needs_clarification"
        assert "column, type" not in (run.answer or "")
        assert (await db_session.execute(select(AgentStep))).scalars().all() == []
