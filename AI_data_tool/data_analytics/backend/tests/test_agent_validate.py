"""The ladder, cheapest first (D4.1) — each rung caught AT that rung.

Cheapest-first only matters if it holds: a syntax error must be V1, not a
confusing V2 miss. And V3 is the single most important test in the layer
(spec F1): a join whose only support is an INFERRED relationship must be
rejected — 105 of the live source's 133 edges are proposals, and executing
on one returns a plausible wrong number.
"""
from app.services.agent.context import JoinInfo, ObjectInfo, SchemaContext
from app.services.agent.validate import validate_sql


def ctx():
    c = SchemaContext(source_id=1, family="postgresql")
    c.objects["customers"] = ObjectInfo("customers", "table", None,
                                        {"id": "integer", "city": "text"})
    c.objects["orders"] = ObjectInfo("orders", "table", None,
                                     {"id": "integer", "customer_id": "integer",
                                      "total": "numeric"})
    c.joins.append(JoinInfo("orders", "customer_id", "customers", "id", "declared"))
    return c


def ctx_with_b_table():
    c = ctx()
    c.objects["t"] = ObjectInfo("t", "table", None, {"b": "text"})
    return c


class TestV1ReadsATable:
    """An answer about the data has to come FROM the data.

    Traced live: asked which attributes were worth visualising, the model
    answered with `SELECT 'id' AS attribute, 'Numeric ID' AS description ...
    UNION ALL ...` -- rows it wrote itself, shown as a grid with Show SQL,
    CSV and Excel beside them. Every other rung checks that the names a query
    uses are real; none of them fires when the query uses no names at all, so
    this was the one fabrication the ladder let through."""

    def test_a_query_that_reads_no_table_is_refused(self):
        failure = validate_sql(
            "SELECT 'id' AS attribute, 'Numeric ID' AS description "
            "UNION ALL SELECT 'total', 'How much'", ctx())
        assert failure.rung == "V1"
        assert "reads no table" in failure.detail

    def test_a_bare_constant_is_refused_too(self):
        assert validate_sql("SELECT 1", ctx()).rung == "V1"

    def test_a_real_query_is_untouched(self):
        assert validate_sql("SELECT id, city FROM customers", ctx()) is None
        assert validate_sql("SELECT count(*) FROM orders", ctx()) is None

    def test_a_cte_counts_as_reading_its_tables(self):
        """The table is inside the WITH body; the walk finds it there."""
        assert validate_sql(
            "WITH recent AS (SELECT id FROM orders) SELECT id FROM recent",
            ctx()) is None


class TestV1Parse:
    def test_garbage_fails_at_v1(self):
        failure = validate_sql("SELEC totl FRM", ctx())
        assert failure.rung == "V1"

    def test_only_select_is_allowed(self):
        """The agent reads; it never writes. A model that emits DELETE has
        been prompt-injected or has hallucinated — either way, refuse."""
        for sql in ("DELETE FROM orders", "UPDATE orders SET total = 0",
                    "DROP TABLE orders", "INSERT INTO orders VALUES (1)"):
            failure = validate_sql(sql, ctx())
            assert failure is not None and failure.rung == "V1", sql


class TestV2Schema:
    def test_a_hallucinated_table_fails_at_v2(self):
        failure = validate_sql("SELECT * FROM shipments", ctx())
        assert failure.rung == "V2"
        assert "shipments" in failure.detail

    def test_a_hallucinated_column_fails_at_v2(self):
        failure = validate_sql("SELECT discount FROM orders", ctx())
        assert failure.rung == "V2"
        assert "discount" in failure.detail

    def test_aliases_resolve_before_checking(self):
        assert validate_sql(
            "SELECT o.total FROM orders AS o", ctx()) is None

    def test_select_output_alias_used_in_order_by_is_not_a_v2_failure(self):
        """Task-15 completion killer: `count(*) AS c ... ORDER BY c` was
        wrongly rejected as 'no such column: c' — c is the query's own
        output name, not a catalog column."""
        assert validate_sql(
            "SELECT b, count(*) AS c FROM t GROUP BY b ORDER BY c DESC",
            ctx_with_b_table()) is None

    def test_select_output_alias_used_in_having_is_not_a_v2_failure(self):
        assert validate_sql(
            "SELECT customer_id, sum(total) AS s FROM orders "
            "GROUP BY customer_id HAVING s > 100", ctx()) is None

    def test_a_genuinely_unknown_column_still_fails_v2(self):
        failure = validate_sql(
            "SELECT customer_id, sum(total) AS s FROM orders "
            "GROUP BY customer_id ORDER BY bogus_alias", ctx())
        assert failure.rung == "V2"
        assert "bogus_alias" in failure.detail

    def test_a_cte_and_its_output_column_pass(self):
        assert validate_sql(
            "WITH t2 AS (SELECT city FROM customers) SELECT city FROM t2",
            ctx()) is None

    def test_a_hallucinated_table_inside_a_cte_body_still_fails_v2(self):
        failure = validate_sql(
            "WITH t2 AS (SELECT x FROM shipments) SELECT x FROM t2", ctx())
        assert failure.rung == "V2"
        assert "shipments" in failure.detail

    def test_cte_pass_through_does_not_leak_to_a_select_not_using_the_cte(self):
        """The parked blind spot: CTE presence anywhere in the statement must
        not blanket-permit unqualified columns in a SELECT whose FROM never
        references that CTE."""
        failure = validate_sql(
            "WITH t2 AS (SELECT city FROM customers) "
            "SELECT bogus_col FROM orders, t2", ctx())
        assert failure is not None
        assert failure.rung == "V2"
        assert "bogus_col" in failure.detail

    def test_a_column_that_resolves_against_a_real_table_in_the_same_select_is_checked_normally(self):
        """c.ghost is qualified, but even unqualified 'ghost' with customers c
        present (not a CTE) must fail — real resolution is preferred over the
        CTE pass-through."""
        failure = validate_sql(
            "WITH t2 AS (SELECT city FROM customers) "
            "SELECT c.ghost FROM customers c", ctx())
        assert failure is not None
        assert failure.rung == "V2"


class TestV3Joins:
    def test_a_declared_join_passes(self):
        assert validate_sql(
            "SELECT c.city, sum(o.total) FROM orders o "
            "JOIN customers c ON o.customer_id = c.id GROUP BY c.city",
            ctx()) is None

    def test_the_join_passes_written_either_way_round(self):
        assert validate_sql(
            "SELECT 1 FROM customers c JOIN orders o ON c.id = o.customer_id",
            ctx()) is None

    def test_an_unconfirmed_join_fails_at_v3(self):
        """THE spec-F1 test. orders.total = customers.id is nonsense the
        schema cannot catch — both exist — only provenance can."""
        failure = validate_sql(
            "SELECT 1 FROM orders o JOIN customers c ON o.total = c.id", ctx())
        assert failure.rung == "V3"

    def test_an_inferred_only_join_fails_at_v3(self):
        c = ctx()
        # An inferred edge exists in the DB but never entered ctx.joins —
        # load_context filtered it. Simulate the SQL a model might still write.
        failure = validate_sql(
            "SELECT 1 FROM orders o JOIN customers c ON o.id = c.id", c)
        assert failure.rung == "V3"


class TestOrder:
    def test_a_query_with_both_problems_reports_the_cheaper_rung(self):
        # unknown table AND bad join: V2 fires first — cheapest-first.
        failure = validate_sql(
            "SELECT 1 FROM shipments s JOIN customers c ON s.x = c.city", ctx())
        assert failure.rung == "V2"


import pytest as _pt  # noqa: E402


@_pt.mark.parametrize("question,sql,refused", [
    # Live QA 2026-09-28: "activity" answered by adding up seconds and bytes.
    ("Which services generated the highest activity?",
     "SELECT SERVICE, SUM(ROUNDED_VOLUME) AS v FROM t GROUP BY SERVICE", True),
    ("Find unusual activity.",
     "WITH d AS (SELECT DATE(x) AS day, SUM(ROUNDED_VOLUME) AS v FROM t GROUP BY 1) SELECT * FROM d", True),
    # A count beside a named measure, a named sum, or no counting word at all: fine.
    ("What was the daily activity trend?",
     "SELECT d, COUNT(*) AS n, SUM(RATED_AMOUNT) AS a FROM t GROUP BY d", False),
    ("Which services have high activity but relatively low rated amount?",
     "SELECT SERVICE, COUNT(*) AS n, SUM(RATED_AMOUNT) AS a FROM t GROUP BY SERVICE", False),
    ("How many calls used the most data volume?",
     "SELECT SERVICE, SUM(volume) FROM t GROUP BY SERVICE", False),
    ("Show rated amount by service.", "SELECT SERVICE, SUM(RATED_AMOUNT) FROM t GROUP BY SERVICE", False),
])
def test_a_counting_question_is_answered_with_a_count(question, sql, refused):
    from app.services.agent.validate import measure_fit
    got = measure_fit(question, sql, "duckdb")
    assert (got is not None) is refused
    if refused:
        assert got.rung == "V7" and "COUNT(*)" in got.detail


class TestDerivedTables:
    """HR evaluation 2026-10-01 (item 1.10): `FROM (SELECT ...) AS latest`
    was refused with "unknown alias: latest", so a leaver definition given in
    plain words could never be answered."""

    def test_a_derived_table_alias_is_a_valid_qualifier(self):
        sql = ("SELECT latest.customer_id, COUNT(*) FROM "
               "(SELECT customer_id, MAX(total) AS top FROM orders GROUP BY customer_id) AS latest "
               "GROUP BY latest.customer_id")
        assert validate_sql(sql, ctx()) is None

    def test_a_derived_table_joined_to_a_real_table(self):
        sql = ("SELECT c.city, COUNT(*) FROM customers c JOIN "
               "(SELECT customer_id FROM orders) AS o ON o.customer_id = c.id GROUP BY c.city")
        assert validate_sql(sql, ctx()) is None

    def test_its_inner_tables_are_still_checked(self):
        sql = "SELECT x.a FROM (SELECT a FROM nope) AS x"
        got = validate_sql(sql, ctx())
        assert got is not None and got.rung == "V2"

    def test_an_unknown_qualifier_still_fails(self):
        sql = "SELECT z.id FROM (SELECT id FROM orders) AS x"
        got = validate_sql(sql, ctx())
        assert got is not None and "unknown alias" in got.detail


def test_partial_last_period_is_flagged():
    from app.services.agent.nodes.explain import partial_period_note
    from app.services.agent.state import StepResult
    rows = [{"leave_year": y, "n": v} for y, v in [(1999, 6964), (2000, 7610), (2001, 7241), (2002, 4011)]]
    r = StepResult("s1", "ok", None, rows, None, [], 0, 0)
    assert "2002" in (partial_period_note(r) or "")
    steady = [{"y": y, "n": 100} for y in (2000, 2001, 2002, 2003)]
    assert partial_period_note(StepResult("s1", "ok", None, steady, None, [], 0, 0)) is None
