"""The agent's answer-synthesis node: figures in, prose out.

H6 review found a correct-SQL-wrong-answer case: rows were present and
correct, but the synthesized natural-language answer claimed "impossible to
determine". The tests here pin the prompt-level fix — they cannot test model
judgment, only that the CONTRACT the prompt states is the strengthened one.
"""
from app.services.agent.nodes.explain import _facts, explain, render_fallback
from app.services.agent.state import StepResult, StepSpec, sink_step_ids


class FakeClient:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    async def complete(self, messages, **kw):
        self.calls.append({"messages": messages, **kw})
        return self.reply


def results():
    return {"s1": StepResult(
        step_id="s1", status="ok", sql="SELECT maps_state_id FROM x",
        rows=[{"maps_state_id": 3}, {"maps_state_id": 9}], error=None,
        validation_failures=[], repair_attempts=0, ms=12)}


def two_step_results():
    """s1 is an intermediate step (s2 depends on it) whose raw rows must
    never reach explain/fallback; s2 is the DAG's sink — the actual final
    answer."""
    return {
        "s1": StepResult(
            step_id="s1", status="ok", sql="SELECT id FROM intermediate",
            rows=[{"leak_marker": "should never surface"}], error=None,
            validation_failures=[], repair_attempts=0, ms=5),
        "s2": StepResult(
            step_id="s2", status="ok", sql="SELECT id FROM final",
            rows=[{"final_marker": 3}, {"final_marker": 9}], error=None,
            validation_failures=[], repair_attempts=0, ms=7),
    }


class TestExplain:
    async def test_returns_the_models_prose(self):
        client = FakeClient("3 and 9 have no ideal solution recorded.")
        got = await explain("which states have no ideal solution",
                            results(), [], client)
        assert got == "3 and 9 have no ideal solution recorded."

    async def test_llm_failure_is_none(self):
        assert await explain("q", results(), [], FakeClient(None)) is None

    async def test_the_prompt_forbids_contradicting_its_own_figures(self):
        """H6 fix 2: 'which map states have no ideal solution' had correct
        SQL and rows, but the answer said 'impossible to determine' — the
        prompt must now forbid that when any step returned rows."""
        client = FakeClient("ok")
        await explain("q", results(), [], client)
        system_text = client.calls[0]["messages"][0]["content"]
        assert "FORBIDDEN" in system_text
        assert "impossible to determine" in system_text
        assert "none found" in system_text

    async def test_the_facts_reach_the_prompt(self):
        client = FakeClient("ok")
        await explain("q", results(), [], client)
        text = "".join(m["content"] for m in client.calls[0]["messages"])
        assert "maps_state_id" in text

    async def test_the_facts_state_the_total_row_count(self):
        """Round-5 false-refusal: prose contradicted its own figures because
        the sample carried no total count. Now each sink step's fact states
        its TOTAL row count next to the sample."""
        client = FakeClient("ok")
        await explain("q", results(), [], client)
        text = "".join(m["content"] for m in client.calls[0]["messages"])
        assert "(2 rows" in text

    async def test_the_forbidden_rule_covers_the_claim_not_just_phrasing(self):
        """Round-5 false-refusal used new wording ('impossible to
        determine' was not the phrase used) — the rule must forbid the
        CLAIM, listing example phrasings as non-exhaustive."""
        client = FakeClient("ok")
        await explain("q", results(), [], client)
        system_text = client.calls[0]["messages"][0]["content"]
        assert "not an exhaustive list" in system_text

    async def test_single_step_behaviour_is_unchanged_with_no_sink_ids(self):
        """The one step IS the sink — no sink_ids argument needed, same as
        before this fix, so every pre-existing single-step call site keeps
        working without modification."""
        client = FakeClient("ok")
        await explain("q", results(), [], client)
        text = "".join(m["content"] for m in client.calls[0]["messages"])
        assert "maps_state_id" in text

    async def test_a_two_step_chain_shows_only_the_sink_steps_rows(self):
        """H6 follow-up: on a multi-step run, an intermediate step's raw
        rows must never reach the model — only the DAG's sink (the actual
        final answer) does. Without sink_ids, s1's leaked marker would also
        appear; with it, only s2's does."""
        client = FakeClient("ok")
        await explain("q", two_step_results(), [], client, sink_ids={"s2"})
        text = "".join(m["content"] for m in client.calls[0]["messages"])
        assert "final_marker" in text
        assert "leak_marker" not in text

    async def test_without_sink_ids_every_step_still_leaks(self):
        """Documents the failure this fix closes: omitting sink_ids on a
        multi-step results dict is the old, unsafe default — intermediate
        rows DO reach the prompt. Callers on the multi-step path (graph.py)
        must always pass sink_ids; single-step callers are unaffected
        because there is nothing to leak."""
        client = FakeClient("ok")
        await explain("q", two_step_results(), [], client)
        text = "".join(m["content"] for m in client.calls[0]["messages"])
        assert "leak_marker" in text


class TestFallback:
    def test_the_fallback_carries_the_raw_rows_when_prose_fails(self):
        text = render_fallback(results(), [])
        assert "maps_state_id" in text

    def test_concerns_are_appended_as_notes(self):
        text = render_fallback(results(), ["the query returned no rows"])
        assert "no rows" in text

    def test_the_fallback_also_shows_only_sink_steps_rows(self):
        text = render_fallback(two_step_results(), [], sink_ids={"s2"})
        assert "final_marker" in text
        assert "leak_marker" not in text


class TestSinkStepIds:
    def test_a_single_step_is_its_own_sink(self):
        assert sink_step_ids([StepSpec(id="s1", question="q")]) == {"s1"}

    def test_a_step_depended_on_by_another_is_not_a_sink(self):
        steps = [StepSpec(id="s1", question="q1"),
                 StepSpec(id="s2", question="q2", depends_on=["s1"])]
        assert sink_step_ids(steps) == {"s2"}

    def test_two_independent_sinks_both_count(self):
        """A fan-out plan (two unrelated final steps) has two sinks — this
        isn't only about linear chains."""
        steps = [StepSpec(id="a", question="q1"),
                 StepSpec(id="b", question="q2")]
        assert sink_step_ids(steps) == {"a", "b"}

class TestFiguresAreLabelledByTable:
    """Live, twice in one thread: "the best table is step_1, which contains
    10 rows of grade data" and "a dataset from step_1 containing 939 rows".
    The figures block labelled each result `step step_1`, and the model read
    the label as a name. Results are labelled by the tables their SQL read,
    and the step id never reaches the prose."""

    def _result(self, step_id, sql, rows=None):
        return StepResult(step_id=step_id, status="ok", sql=sql,
                          rows=rows if rows is not None else [{"n": 1}],
                          error=None, validation_failures=[],
                          repair_attempts=0, ms=0)

    def test_a_result_is_named_after_the_tables_it_read(self):
        facts = _facts({"step_1": self._result(
            "step_1", "SELECT id, grade FROM mdl_grade_grades LIMIT 10")})
        assert "rows from mdl_grade_grades" in facts
        assert "step_1" not in facts

    def test_a_join_names_every_table(self):
        facts = _facts({"s1": self._result(
            "s1", "SELECT c.name FROM mdl_course c JOIN mdl_assign a ON a.course = c.id")})
        assert "rows from mdl_assign, mdl_course" in facts

    def test_the_catalog_listing_says_what_it_is(self):
        facts = _facts({"catalog": self._result("catalog", None,
                                                 rows=[{"table": "mdl_course"}])})
        assert "the data catalog" in facts
        assert "catalog (" not in facts.replace("the data catalog (", "")

    def test_unparseable_sql_still_gets_a_neutral_label(self):
        facts = _facts({"s1": self._result("s1", "SELEC nonsense")})
        assert "query result" in facts
        assert "s1" not in facts


class TestTheCatalogStepIsCountedInItsOwnUnit:
    """"what is this data?" on a 13-column dataset came back as "13 rows".

    The count was true and the noun was wrong: in single-object scope the
    catalog step has one row per COLUMN, and the figures handed to the model
    called them rows. A reader who knows the dataset has 2,000 rows reads that
    as a plain error, so the unit is now stated with the count.
    """

    def _catalog(self, rows):
        return {"catalog": StepResult(
            step_id="catalog", status="ok", sql=None, rows=rows,
            error=None, validation_failures=[], repair_attempts=0, ms=0)}

    def test_one_object_in_scope_counts_columns(self):
        rows = [{"column": f"c{i}", "type": "text"} for i in range(13)]
        facts = _facts(self._catalog(rows))
        assert "13 columns" in facts
        assert "13 rows" not in facts

    def test_several_objects_in_scope_count_tables(self):
        rows = [{"table": "orders", "kind": "table", "columns": 7},
                {"table": "customers", "kind": "table", "columns": 4}]
        facts = _facts(self._catalog(rows))
        assert "2 tables" in facts
        assert "2 rows" not in facts

    def test_an_ordinary_query_still_counts_rows(self):
        assert "2 rows" in _facts(results())


class TestAnswersReadLikeTheirData:
    """BUG-032: the numbers were right but the prose was not -- it named the
    internal query table (`qa_chrome_sales`), repeated float64 sums as
    `2580.0`, listed groups in the engine's arbitrary order, and offered
    analyses on columns the data does not have."""

    def _r(self, sql, rows):
        return {"s1": StepResult(step_id="s1", status="ok", sql=sql, rows=rows, error=None,
                                 validation_failures=[], repair_attempts=0, ms=0)}

    def test_a_dataset_is_named_as_its_author_named_it(self):
        facts = _facts(self._r("SELECT region, SUM(sales) AS s FROM qa_chrome_sales GROUP BY region",
                               [{"region": "N", "s": 1.0}]),
                       names={"qa_chrome_sales": "QA_CHROME_sales"})
        assert 'rows from "QA_CHROME_sales"' in facts
        assert "qa_chrome_sales" not in facts

    def test_a_real_table_keeps_its_name(self):
        facts = _facts(self._r("SELECT id FROM mdl_course", [{"id": 1}]), names=None)
        assert "rows from mdl_course" in facts

    def test_whole_numbers_lose_the_point_zero_and_others_are_rounded(self):
        facts = _facts(self._r("SELECT region, SUM(sales) AS s FROM t GROUP BY region ORDER BY region",
                               [{"region": "N", "s": 2580.0}, {"region": "S", "s": 1/3},
                                {"region": "W", "s": True}]))
        assert "'s': 2580}" in facts and "2580.0" not in facts
        assert "0.3333" in facts and "0.33333" not in facts
        assert "True" in facts           # a flag is not a number

    def test_unordered_groups_are_listed_largest_first(self):
        facts = _facts(self._r("SELECT region, SUM(sales) AS s FROM t GROUP BY region",
                               [{"region": "N", "s": 10.0}, {"region": "S", "s": 30.0},
                                {"region": "E", "s": None}, {"region": "W", "s": 20.0}]))
        assert facts.index("'S'") < facts.index("'W'") < facts.index("'N'") < facts.index("'E'")

    def test_an_explicit_order_by_is_kept(self):
        facts = _facts(self._r("SELECT month, SUM(sales) AS s FROM t GROUP BY month ORDER BY month",
                               [{"month": 1, "s": 5.0}, {"month": 2, "s": 50.0}]))
        assert facts.index("'month': 1") < facts.index("'month': 2")

    def test_the_stored_rows_are_not_reordered(self):
        res = self._r("SELECT region, SUM(sales) AS s FROM t GROUP BY region",
                      [{"region": "N", "s": 10.0}, {"region": "S", "s": 30.0}])
        _facts(res)
        assert [r["region"] for r in res["s1"].rows] == ["N", "S"]

    async def test_the_prompt_names_the_dataset_and_forbids_invented_suggestions(self):
        client = FakeClient("ok")
        await explain("total by region?", self._r("SELECT region FROM qa_chrome_sales", [{"region": "N"}]),
                      [], client, names={"qa_chrome_sales": "QA_CHROME_sales"})
        system = client.calls[0]["messages"][0]["content"]
        user = client.calls[0]["messages"][1]["content"]
        assert "Do not suggest further analyses" in system
        assert "never mention a column that is not in the figures" in system
        assert '"QA_CHROME_sales"' in user

    def test_the_fallback_uses_the_same_names_and_numbers(self):
        text = render_fallback(self._r("SELECT SUM(x) AS s FROM qa_chrome_sales", [{"s": 2580.0}]),
                               [], names={"qa_chrome_sales": "QA_CHROME_sales"})
        assert '"QA_CHROME_sales"' in text and "2580.0" not in text
