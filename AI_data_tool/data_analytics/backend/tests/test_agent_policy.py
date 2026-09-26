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


# --------------------------------------------------------------------------
# E01: dataset row rules reach a conversation over the connection
# --------------------------------------------------------------------------
# A conversation scoped to a connection writes SQL against the source's own
# tables. A member whose row rule on the "Orders" dataset limits them to one
# region could ask the connection instead and read every region: only object
# row policies applied there. Now each dataset over the connection puts its
# rule on its table, and fails closed wherever it cannot.

def test_an_everywhere_predicate_lands_on_every_table():
    from app.services.agent.policy import ANY_TABLE
    out = apply_policies("SELECT o.total FROM orders o JOIN customers c ON o.cid = c.id",
                         {ANY_TABLE: "1 = 0", "orders": "region = 'west'"}, "postgresql")
    assert "o.region = 'west'" in out and out.count("1 = 0") == 2


class TestDatasetRulesOnTheConnection:
    async def _world(self, db, two_orgs, rule, **dataset):
        from types import SimpleNamespace
        from app.core.security import hash_password
        from app.models.models import (DataSource, Dataset, DatasetColumn, Role,
                                       RowSecurityRule, User)
        org = two_orgs["a"]["org"]
        role = Role(org_id=org.id, name="eu-analyst", is_org_admin=False)
        db.add(role)
        await db.flush()
        user = User(org_id=org.id, role_id=role.id, email="eu@ex.com", password_hash=hash_password("pw"))
        src = DataSource(name="Warehouse", type="postgresql", config={}, org_id=org.id)
        db.add_all([user, src])
        await db.flush()
        ds = Dataset(name="Orders", org_id=org.id, mode="import", data_source_id=src.id,
                     filename="/tmp/none.csv", **dataset)
        db.add(ds)
        await db.flush()
        for c in ("region", "total"):
            db.add(DatasetColumn(dataset_id=ds.id, name=c, dtype="string"))
        if rule:
            db.add(RowSecurityRule(role_id=role.id, dataset_id=ds.id, filter_expr=rule))
        await db.commit()
        await db.refresh(user, ["role"])
        return user, SimpleNamespace(source_id=src.id, family="postgresql")

    async def test_the_readers_rule_is_the_tables_predicate(self, db_session, two_orgs):
        from app.services.agent.policy import load_policies
        user, ctx = await self._world(db_session, two_orgs, "region == 'EU'", source_table="public.orders")
        policies = await load_policies(db_session, ctx, user)
        assert policies == {"orders": "(\"region\" = 'EU')"}
        out = apply_policies("SELECT region, sum(total) FROM orders GROUP BY region", policies, "postgresql")
        assert "WHERE" in out.upper() and "'EU'" in out

    async def test_a_rule_that_cannot_be_translated_lets_no_row_through(self, db_session, two_orgs):
        from app.services.agent.policy import load_policies
        user, ctx = await self._world(db_session, two_orgs, "missing_column == 'EU'", source_table="orders")
        assert await load_policies(db_session, ctx, user) == {"orders": "(1 = 0)"}

    async def test_a_query_datasets_rule_closes_the_tables_it_reads(self, db_session, two_orgs):
        from app.services.agent.policy import load_policies
        user, ctx = await self._world(db_session, two_orgs, "region == 'EU'",
                                      source_query="SELECT o.region, o.total FROM orders o JOIN shops s ON o.sid = s.id")
        assert await load_policies(db_session, ctx, user) == {"orders": "(1 = 0)", "shops": "(1 = 0)"}

    async def test_no_rule_no_predicate_and_admins_are_exempt(self, db_session, two_orgs):
        from app.services.agent.policy import load_policies
        user, ctx = await self._world(db_session, two_orgs, None, source_table="orders")
        assert await load_policies(db_session, ctx, user) == {}
        admin = two_orgs["a"]["user"]
        from app.models.models import User
        from sqlalchemy.orm import selectinload
        from sqlalchemy import select
        admin = (await db_session.execute(select(User).options(selectinload(User.role))
                                          .where(User.id == admin.id))).scalar_one()
        assert await load_policies(db_session, ctx, admin) == {}
