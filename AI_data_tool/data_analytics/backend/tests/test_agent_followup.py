"""The follow-up resolver (nodes/followup.py): a new message read against
the conversation so far.

Two jobs, one contract: decide whether the message only wants the LAST
RESULT SHOWN DIFFERENTLY (a table, a chart, a CSV, fewer rows) or wants DATA,
and in the data case rewrite it as one standalone question. The screenshots
that motivated this had "execute query and i need to see result" and "can
you present a table" both answered with "needs more detail", because each
was classified cold."""
from app.services.agent.nodes.followup import (FOLLOWUP_SCHEMA, last_result,
                                               render_history, resolve)

SNAP = {"step": "s1", "columns": ["city", "n"], "rows": [["Cairo", 3]],
        "total": 1, "truncated": False}
HISTORY = [
    {"role": "user", "content": "orders per city", "sql": [], "results": []},
    {"role": "assistant", "content": "Cairo has 3 orders.",
     "sql": ["SELECT city, count(*) AS n FROM orders GROUP BY city"],
     "results": [SNAP]},
]


class FakeClient:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    async def complete_json(self, messages, schema, **kw):
        self.calls.append({"messages": messages, "schema": schema, **kw})
        return self.reply


class TestHistoryBlock:
    def test_turns_carry_their_sql_and_row_counts(self):
        block = render_history(HISTORY)
        assert "User: orders per city" in block
        assert "Assistant: Cairo has 3 orders." in block
        assert "SQL: SELECT city, count(*) AS n FROM orders GROUP BY city" in block
        # The count is what lets "show 5 rows" vs "show 500 rows" be judged.
        assert "returned 1 rows" in block

    def test_the_block_is_bounded(self):
        long = [{"role": "user", "content": "x" * 5000, "sql": [], "results": []}] * 20
        assert len(render_history(long)) <= 2000

    def test_empty_history_renders_empty(self):
        assert render_history([]) == ""


class TestLastResult:
    def test_the_most_recent_assistant_turn_with_rows_wins(self):
        older = {"role": "assistant", "content": "a", "sql": ["SELECT 1"],
                 "results": [{**SNAP, "rows": [["Giza", 1]]}]}
        newer_without = {"role": "assistant", "content": "b", "sql": [], "results": []}
        assert last_result([older, newer_without])["results"][0]["rows"] == [["Giza", 1]]
        assert last_result([newer_without]) is None
        assert last_result([]) is None

    def test_an_empty_result_is_skipped_in_favour_of_real_rows(self):
        # Traced live: a query against an empty table named `charts`
        # produced a 0-row "result", and "chart for samples" then re-showed
        # nothing instead of the sample the user meant. You cannot chart
        # nothing; the earlier turn with rows is the referent.
        sample = {"role": "assistant", "content": "sample", "sql": ["SELECT *"],
                  "results": [SNAP]}
        empty = {"role": "assistant", "content": "None found.",
                 "sql": ["SELECT * FROM charts"],
                 "results": [{"step": "s1", "columns": ["id"], "rows": [],
                              "total": 0, "truncated": False}]}
        assert last_result([sample, empty]) is sample
        assert last_result([empty]) is None


class TestResolve:
    async def test_the_prompt_carries_the_conversation_and_the_new_message(self):
        client = FakeClient({"kind": "presentation", "question": "as a table",
                             "format": "table", "limit": None})
        got = await resolve("as a table", HISTORY, client)
        joined = "".join(m["content"] for m in client.calls[0]["messages"])
        assert "orders per city" in joined
        assert "New message: as a table" in joined
        assert client.calls[0]["schema"] is FOLLOWUP_SCHEMA
        assert got == {"kind": "presentation", "question": "as a table",
                       "format": "table", "limit": None, "x": None, "y": None}

    async def test_a_presentation_request_with_nothing_to_show_becomes_data(self):
        # "as a table" right after a clarifying question has no rows to
        # re-show; asking the database is the only honest move.
        client = FakeClient({"kind": "presentation", "question": "orders per city as a table",
                             "format": "table", "limit": None})
        no_rows = [{"role": "user", "content": "q", "sql": [], "results": []},
                   {"role": "assistant", "content": "Which metric?", "sql": [], "results": []}]
        got = await resolve("as a table", no_rows, client)
        assert got["kind"] == "data"
        assert got["question"] == "orders per city as a table"

    async def test_a_data_rewrite_comes_back_standalone(self):
        client = FakeClient({"kind": "data",
                             "question": "How many orders per city, for Cairo only?",
                             "format": None, "limit": None})
        got = await resolve("the same for Cairo only", HISTORY, client)
        assert got["kind"] == "data"
        assert got["question"] == "How many orders per city, for Cairo only?"

    async def test_an_empty_rewrite_falls_back_to_the_message_as_typed(self):
        client = FakeClient({"kind": "data", "question": "   ", "format": None, "limit": None})
        got = await resolve("orders per region", HISTORY, client)
        assert got["question"] == "orders per region"

    async def test_model_failure_yields_none(self):
        assert await resolve("as a table", HISTORY, FakeClient(None)) is None

    async def test_chart_requests_are_taught_as_presentation(self):
        # "give me some suggested charts" ran SQL against an empty table
        # that happened to be NAMED charts (live trace, conversation 11).
        # The rule and both examples are pinned in the prompt.
        client = FakeClient({"kind": "presentation", "question": "q",
                             "format": "bar", "limit": None})
        await resolve("chart for samples", HISTORY, client)
        system = client.calls[0]["messages"][0]["content"]
        assert "'suggest charts'" in system
        assert "New message: chart for samples" in system
        assert "New message: give me some suggested charts" in system
        assert "never a query against a table" in system.replace("\n-- ", " ")

    async def test_a_nonpositive_limit_is_dropped(self):
        client = FakeClient({"kind": "presentation", "question": "q",
                             "format": "table", "limit": 0})
        got = await resolve("just the table", HISTORY, client)
        assert got["limit"] is None


class TestTheKindsThatNeverQuery:
    """`describe` and `chat`: the two kinds added after the screenshots.

    "explain this chart" used to reach classify, whose `explain` intent means
    the key-influencers ANALYSIS, and came back as "the response needs at
    least two distinct numeric values" -- about a column nobody had named. And
    a second-turn "thanks" was rewritten into a standalone data question and
    queried, because `data` was the only kind left once it was not a re-show.
    Neither is a word list: the model still decides, it just has somewhere
    honest to land."""

    def test_both_kinds_are_offered_to_the_model(self):
        assert FOLLOWUP_SCHEMA["properties"]["kind"]["enum"] == [
            "data", "presentation", "describe", "chat"]

    async def test_describe_answers_from_the_rows_that_exist(self):
        client = FakeClient({"kind": "describe",
                             "question": "Explain the orders per city result",
                             "format": None, "limit": None})
        got = await resolve("explain this chart", HISTORY, client)
        assert got["kind"] == "describe"
        assert got["question"] == "Explain the orders per city result"
        # It re-shows nothing, so it carries no format and no limit.
        assert got["format"] is None and got["limit"] is None

    async def test_describe_with_no_earlier_rows_becomes_a_query(self):
        """Same guard as presentation, for the same reason: both kinds answer
        FROM rows, so with no rows the database is the only honest source."""
        no_rows = [{"role": "user", "content": "q", "sql": [], "results": []},
                   {"role": "assistant", "content": "Which metric?",
                    "sql": [], "results": []}]
        client = FakeClient({"kind": "describe", "question": "explain the orders result",
                             "format": None, "limit": None})
        got = await resolve("explain that", no_rows, client)
        assert got["kind"] == "data"

    async def test_chat_keeps_the_message_exactly_as_typed(self):
        """There is no question inside it to make standalone, and a rewrite is
        what turned "thanks" into a query in the first place."""
        client = FakeClient({"kind": "chat",
                             "question": "How many orders are there per city?",
                             "format": None, "limit": None})
        got = await resolve("thanks", HISTORY, client)
        assert got["kind"] == "chat"
        assert got["question"] == "thanks"
        assert got["format"] is None and got["limit"] is None

    async def test_chat_survives_having_no_earlier_rows(self):
        """Unlike describe and presentation it needs no rows at all, so the
        no-rows fallback must not drag it back to `data`."""
        client = FakeClient({"kind": "chat", "question": "hello",
                             "format": None, "limit": None})
        got = await resolve("hello", [{"role": "user", "content": "hi",
                                       "sql": [], "results": []}], client)
        assert got["kind"] == "chat"

    async def test_the_prompt_teaches_both_kinds_by_example(self):
        client = FakeClient({"kind": "chat", "question": "thanks",
                             "format": None, "limit": None})
        await resolve("thanks", HISTORY, client)
        system = client.calls[0]["messages"][0]["content"]
        assert "New message: explain this chart" in system
        assert "New message: thanks" in system
        assert '"kind": "describe"' in system
        assert '"kind": "chat"' in system

class TestTheColumnsAChartMessageNames:
    """`x` and `y` ride back when the message says which columns to use.

    They exist so that clicking "Chart symbol_code by id" -- an option the
    agent itself offered -- is understood as the answer to the question it
    asked, instead of being read as a vague new chart request and guessed at
    all over again."""

    def test_the_contract_carries_them(self):
        props = FOLLOWUP_SCHEMA["properties"]
        assert props["x"]["type"] == ["string", "null"]
        assert props["y"]["type"] == ["string", "null"]
        # Required, like every other field: this schema is enforced, and an
        # optional key in an enforced schema is a key the model may drop.
        assert set(FOLLOWUP_SCHEMA["required"]) == {
            "kind", "question", "format", "limit", "x", "y"}

    async def test_named_columns_come_back_as_written(self):
        client = FakeClient({"kind": "presentation", "question": "Draw n by city",
                             "format": "bar", "limit": None,
                             "x": "city", "y": "n"})
        got = await resolve("Chart n by city", HISTORY, client)
        assert (got["x"], got["y"]) == ("city", "n")

    async def test_a_chart_message_that_names_nothing_carries_no_axes(self):
        client = FakeClient({"kind": "presentation", "question": "chart it",
                             "format": "bar", "limit": None, "x": None, "y": None})
        got = await resolve("i need chart", HISTORY, client)
        assert got["x"] is None and got["y"] is None

    async def test_every_kind_returns_the_same_shape(self):
        """One shape out, whatever comes back -- the caller reads `x` and `y`
        without asking which kind it is holding."""
        for reply, typed in [
            ({"kind": "data", "question": "q", "format": None, "limit": None,
              "x": "city", "y": "n"}, "the same for Cairo"),
            ({"kind": "describe", "question": "explain", "format": None,
              "limit": None, "x": None, "y": None}, "what does this mean"),
            ({"kind": "chat", "question": "hi", "format": None, "limit": None,
              "x": None, "y": None}, "thanks"),
        ]:
            got = await resolve(typed, HISTORY, FakeClient(reply))
            assert set(got) == {"kind", "question", "format", "limit", "x", "y"}
            # Only a presentation can carry axes; nothing else draws anything.
            if got["kind"] != "presentation":
                assert got["x"] is None and got["y"] is None

    async def test_the_prompt_teaches_the_phrasing_it_offers(self):
        """The options the agent offers are phrased "Chart Y by X"; if the
        resolver were not taught that phrasing, clicking one would be read as
        a fresh vague request -- the loop would not close."""
        client = FakeClient({"kind": "presentation", "question": "q",
                             "format": "bar", "limit": None, "x": "city", "y": "n"})
        await resolve("Chart n by city", HISTORY, client)
        system = client.calls[0]["messages"][0]["content"]
        assert "New message: Chart n by city" in system
        assert '"x": "city"' in system

class TestAChartRequestWithNothingOnScreen:
    """"i need chart" typed after a greeting.

    It has no rows to re-show, names no columns, and asks no question -- so
    the resolver had nowhere to put it and called it `chat`, which produced
    the worst sentence in the product: "I can't generate charts directly."
    It stays `presentation`; WHAT to draw is settled afterwards, from the
    data (services/agent/charts.py), and asked about when the data does not
    settle it."""

    GREETED = [{"role": "user", "content": "hi", "sql": [], "results": []},
               {"role": "assistant", "content": "Hello! Ask me anything.",
                "sql": [], "results": []}]

    async def test_it_stays_a_presentation_with_no_rows_to_re_show(self):
        client = FakeClient({"kind": "presentation", "question": "Draw a chart",
                             "format": "bar", "limit": None, "x": None, "y": None})
        got = await resolve("i need chart", self.GREETED, client)
        assert got["kind"] == "presentation"
        assert got["format"] == "bar"

    async def test_a_table_with_no_rows_still_becomes_a_query(self):
        """Only a chart is exempt: "as a table" with nothing to show has to
        go and get something to show."""
        client = FakeClient({"kind": "presentation", "question": "as a table",
                             "format": "table", "limit": None, "x": None, "y": None})
        got = await resolve("as a table", self.GREETED, client)
        assert got["kind"] == "data"

    async def test_the_prompt_says_a_chart_is_never_small_talk(self):
        client = FakeClient({"kind": "presentation", "question": "Draw a chart",
                             "format": "bar", "limit": None, "x": None, "y": None})
        await resolve("i need chart", self.GREETED, client)
        system = client.calls[0]["messages"][0]["content"]
        assert "never chat either" in system
        assert "New message: i need chart" in system

class TestACatalogListingIsNotTheData:
    """The listing behind "what is this data" describes the data; it is not
    the data, and a chart of it is a chart of column NAMES.

    Traced live over four turns. After a describe, "i need suggest charts to
    add to dashboard" tried to chart the listing and refused -- "only column,
    type varies" -- offering "Show the rows as a table", which showed the
    listing again. "btwen region and count" refused identically. So did
    "dount". The person broke the loop by pasting their own numbers into the
    chat box. A chart request has to reach PAST the description."""

    CATALOG_TURN = {
        "role": "assistant", "content": "This data has 13 columns.", "sql": [],
        "results": [{"step": "catalog", "source": "catalog",
                     "columns": ["column", "type"],
                     "rows": [["region", "categorical"], ["revenue", "numeric"]],
                     "total": 13, "truncated": False}],
    }
    DATA_TURN = {
        "role": "assistant", "content": "Europe leads.", "sql": [PREV_SQL := "SELECT 1"],
        "results": [{"step": "s1", "source": "query", "columns": ["region", "n"],
                     "rows": [["Europe", 514]], "total": 4, "truncated": False}],
    }

    def test_a_chart_reaches_past_the_listing_to_the_real_result(self):
        history = [self.DATA_TURN, self.CATALOG_TURN]
        assert last_result(history) is self.CATALOG_TURN          # re-show: fine
        assert last_result(history, chartable=True) is self.DATA_TURN

    def test_a_chart_with_only_a_listing_behind_it_finds_nothing(self):
        """None is the right answer, not the listing: it sends the request to
        `_chart_from_scratch`, which reads the dataset itself."""
        assert last_result([self.CATALOG_TURN], chartable=True) is None

    def test_showing_the_listing_as_a_table_is_still_allowed(self):
        """Only CHARTING it is wrong. "Show the rows as a table" right after a
        describe means the listing, and always did."""
        assert last_result([self.CATALOG_TURN]) is self.CATALOG_TURN

    def test_a_mixed_turn_keeps_its_query_rows(self):
        """A describe run carries BOTH: the listing and the query beside it.
        The query's rows are real data and stay chartable."""
        mixed = {"role": "assistant", "content": "13 columns, 2000 rows.",
                 "sql": ["SELECT count(*) FROM demo_sales"],
                 "results": [
                     {"step": "catalog", "source": "catalog", "columns": ["column"],
                      "rows": [["region"]], "total": 13, "truncated": False},
                     {"step": "s1", "source": "query", "columns": ["n"],
                      "rows": [[2000]], "total": 1, "truncated": False}]}
        assert last_result([mixed], chartable=True) is mixed
