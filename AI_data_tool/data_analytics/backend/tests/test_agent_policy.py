"""V4: predicates into the AST — never concatenated, never post-filtered.

ARCHITECTURE.md calls this the security-critical flow of the whole platform,
and forbids the two easy ways out: string concatenation (injectable) and
post-filtering (leaks row counts, aggregates and existence — an aggregate
computed before the filter is already the wrong number). The import path's
apply_rls_filter post-filters; the agent path must never call it (spec F4).
"""
import pytest
import sqlglot

from app.services.agent.policy import PolicyError, apply_policies


class TestInjection:
    def test_the_predicate_lands_inside_where(self):
        out = apply_policies("SELECT total FROM orders",
                             {"orders": "region = 'west'"}, "postgresql")
        tree = sqlglot.parse_one(out, dialect="postgres")
        assert "region = 'west'" in tree.args["where"].sql(dialect="postgres")

    def test_an_existing_where_is_preserved_with_and(self):
        out = apply_policies("SELECT total FROM orders WHERE total > 10",
                             {"orders": "region = 'west'"}, "postgresql")
        where = sqlglot.parse_one(out, dialect="postgres").args["where"].sql()
        assert "total > 10" in where and "region = 'west'" in where
        assert "AND" in where.upper()

    def test_aggregates_are_filtered_before_aggregation(self):
        """The whole point of AST injection over post-filtering: the WHERE
        applies before GROUP BY, so the aggregate itself is computed over
        only the permitted rows."""
        out = apply_policies(
            "SELECT city, sum(total) FROM orders GROUP BY city",
            {"orders": "region = 'west'"}, "postgresql")
        rendered = out.upper()
        assert rendered.index("WHERE") < rendered.index("GROUP BY")

    def test_the_predicate_is_qualified_by_the_tables_alias(self):
        out = apply_policies(
            "SELECT o.total FROM orders AS o JOIN customers AS c "
            "ON o.customer_id = c.id",
            {"orders": "region = 'west'"}, "postgresql")
        assert "o.region = 'west'" in out

    def test_each_policied_table_gets_its_own_predicate(self):
        out = apply_policies(
            "SELECT o.total FROM orders o JOIN customers c "
            "ON o.customer_id = c.id",
            {"orders": "region = 'west'", "customers": "tier = 'gold'"},
            "postgresql")
        assert "o.region = 'west'" in out and "c.tier = 'gold'" in out

    def test_unpolicied_tables_are_untouched(self):
        sql = "SELECT city FROM customers"
        assert apply_policies(sql, {"orders": "region = 'west'"},
                              "postgresql").upper().count("WHERE") == 0


class TestRefusalOverLeakage:
    def test_a_malformed_predicate_refuses_rather_than_concatenates(self):
        """A predicate that does not parse must fail the QUERY, not be pasted
        in as text — failing open here is the vulnerability."""
        with pytest.raises(PolicyError):
            apply_policies("SELECT total FROM orders",
                           {"orders": "region = 'west"}, "postgresql")

    def test_a_policied_table_inside_a_subquery_still_gets_filtered(self):
        out = apply_policies(
            "SELECT * FROM (SELECT total FROM orders) t",
            {"orders": "region = 'west'"}, "postgresql")
        assert "region = 'west'" in out

    def test_a_cte_name_colliding_with_a_policied_table_cannot_underfilter(self):
        """policy.py matches policied tables by NAME, with no notion of
        CTEs — a `WITH orders AS (...)` binds the name `orders` to a
        synthetic relation for the rest of the query, and any `FROM orders`
        after it resolves to the CTE, never the real table.

        Pinning the actual (imperfect) behaviour: the predicate gets
        injected against the CTE reference anyway, since apply_policies has
        no CTE-awareness. That's a false injection (the resulting SQL
        references a column, e.g. region, the CTE's own SELECT never
        projects, so it fails downstream rather than executing) — but it is
        SAFE, because the query's only `FROM orders` reference is to the
        CTE, so the real `orders` table is never touched and no unfiltered
        row from it can leak. If a future query referenced the real table
        by the same name inside the CTE body, that inner reference is a
        separate `exp.Table` node under a different owning SELECT and would
        be filtered (or raise PolicyError) independently — this test only
        pins the collision-at-the-outer-level case.
        """
        out = apply_policies(
            "WITH orders AS (SELECT 1 AS x) SELECT x FROM orders",
            {"orders": "region = 'west'"}, "postgresql")
        # Documented actual behaviour: injected onto the CTE reference, not
        # silently dropped and not applied to a real `orders` table (there
        # is none referenced) — so it can never UNDER-filter real data.
        assert "region = 'west'" in out
