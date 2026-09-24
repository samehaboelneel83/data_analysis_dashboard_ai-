"""Index recommendations from what the platform has watched itself run.

DirectQuery latency on a big table is the customer's index situation, not
this codebase's -- measured 2026-09-12 at 10M rows: an index on the FILTERED
column cut a governed query by a quarter; an index on the GROUPED column
changed nothing, because a full aggregation scans either way. So the advice
has to come from the filter and RLS columns the platform has actually seen,
and must never be "index what you group by".

Three parts, each pinned:

  * the SHAPE of a query is recorded with its run -- column names in the
    filters and the RLS rule, the grouped column, the table. Names only:
    never a value, never SQL.
  * the recommender ranks (table, filter column) pairs by runs x mean duration,
    skips anything already leading an index, needs a minimum number of runs
    before it will say anything, and IGNORES grouped columns.
  * the endpoint belongs to the source's org and returns recommendations
    only. Nothing here ever creates an index on a customer database.
"""
import json
from datetime import datetime, timedelta

import pytest

from app.models.models import DataSource, QueryRun
from app.services import direct_query, index_advice
from app.services.sql_expr import expression_columns


# ── shape ───────────────────────────────────────────────────────────────────

class TestExpressionColumns:
    def test_lists_every_column_an_expression_reads(self):
        cols = expression_columns("region == 'North' and `unit cost` > 3 or tier in ['a']",
                                  {"region", "unit cost", "tier", "other"})
        assert cols == {"region", "unit cost", "tier"}

    def test_an_empty_expression_reads_nothing(self):
        assert expression_columns("", {"region"}) == set()

    def test_an_unknown_column_is_refused_not_guessed(self):
        from app.services.sql_expr import ExpressionTranslationError
        with pytest.raises(ExpressionTranslationError):
            expression_columns("nope == 1", {"region"})


class _DS:
    id = 7
    data_source_id = 3
    source_table = "orders"
    source_query = None
    columns = [type("C", (), {"name": n, "dtype": "categorical"})()
               for n in ("region", "tenant", "customer", "amount")]


class TestTheShapeIsLogged:
    @pytest.fixture
    def captured(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(direct_query, "_dispatch_direct_query",
                            lambda *a, **kw: {"rows": [], "total": 0})
        monkeypatch.setattr(direct_query, "log_query_run_sync",
                            lambda **fields: seen.update(fields))
        return seen

    def test_filter_and_rls_columns_and_the_grouped_column(self, captured):
        direct_query.run_direct_query(
            {"type": "postgresql"}, _DS(),
            {"dimension": "customer", "measure": "amount", "aggregation": "sum",
             "filters": [{"column": "region", "op": "eq", "value": "North"}]},
            widget_type="bar", rls_filter_expr="tenant == 'acme'", cache_ttl_seconds=0)
        assert captured["source_table"] == "orders"
        assert captured["group_column"] == "customer"
        assert captured["filter_columns"] == ["region", "tenant"]

    def test_never_a_value_never_sql(self, captured):
        direct_query.run_direct_query(
            {"type": "postgresql"}, _DS(),
            {"dimension": "customer", "measure": "amount", "aggregation": "sum",
             "filters": [{"column": "region", "op": "eq", "value": "SECRET-VALUE"}]},
            widget_type="bar", rls_filter_expr="tenant == 'acme-private'", cache_ttl_seconds=0)
        blob = json.dumps(captured, default=str)
        assert "SECRET-VALUE" not in blob
        assert "acme-private" not in blob
        assert "SELECT" not in blob.upper()

    def test_no_filters_logs_an_empty_list_not_nothing(self, captured):
        direct_query.run_direct_query(
            {"type": "postgresql"}, _DS(),
            {"dimension": "customer", "measure": "amount", "aggregation": "sum"},
            widget_type="bar", cache_ttl_seconds=0)
        assert captured["filter_columns"] == []


# ── recommender ─────────────────────────────────────────────────────────────

def run(table, filters, group, ms):
    return {"source_table": table, "filter_columns": filters, "group_column": group,
            "duration_ms": ms}


class TestTheRecommender:
    def test_ranks_by_runs_times_mean_duration(self):
        runs = ([run("orders", ["region"], "customer", 900)] * 5
                + [run("orders", ["tenant"], "customer", 100)] * 5)
        out = index_advice.advise(runs, indexed=set(), min_runs=3)
        cols = [c["column"] for c in out["tables"][0]["columns"]]
        assert cols == ["region", "tenant"]
        assert out["tables"][0]["columns"][0]["recommended"] is True

    def test_a_column_already_leading_an_index_is_not_recommended(self):
        runs = [run("orders", ["region"], "customer", 900)] * 5
        out = index_advice.advise(runs, indexed={("orders", "region")}, min_runs=3)
        col = out["tables"][0]["columns"][0]
        assert col["indexed"] is True and col["recommended"] is False

    def test_needs_a_minimum_number_of_runs(self):
        runs = [run("orders", ["region"], "customer", 900)] * 2
        out = index_advice.advise(runs, indexed=set(), min_runs=3)
        assert out["tables"] == []

    def test_the_grouped_column_is_never_recommended(self):
        """The measured finding. `customer` is grouped in every run and filtered
        in none; an index on it did nothing at 10M rows. Counting it would make
        the recommender confidently wrong."""
        runs = [run("orders", ["region"], "customer", 900)] * 10
        out = index_advice.advise(runs, indexed=set(), min_runs=3)
        assert [c["column"] for c in out["tables"][0]["columns"]] == ["region"]

    def test_the_statement_is_ready_to_paste(self):
        stmt = index_advice.create_index_statement("orders", "region")
        assert stmt == 'CREATE INDEX ON "orders" ("region");'

    def test_a_dotted_table_keeps_its_schema(self):
        assert index_advice.create_index_statement("sales.orders", "region") == \
            'CREATE INDEX ON "sales"."orders" ("region");'


class TestReadingTheCustomersIndexes:
    def test_pairs_come_from_the_catalog_not_from_text(self):
        """The first version parsed pg_indexes.indexdef with a regex and read
        `(region DESC)` as a column called "region DESC" -- so an index that
        existed was reported missing. The catalog gives the leading column
        by attribute number; nothing is parsed."""
        rows = [("public", "orders", "region"),
                ("public", "orders", "id"),
                ("sales", "orders", "customer")]
        pairs = index_advice._pairs_from_catalog(rows, {"orders", "sales.orders"})
        assert ("orders", "region") in pairs and ("orders", "id") in pairs
        # A schema-qualified table only matches its own schema's indexes.
        assert ("sales.orders", "customer") in pairs
        assert ("sales.orders", "region") not in pairs

    def test_an_expression_index_has_no_leading_column(self):
        rows = [("public", "orders", None)]      # indkey[0] = 0 -> no attribute
        assert index_advice._pairs_from_catalog(rows, {"orders"}) == set()

    def test_a_non_postgres_source_is_reported_as_unsupported_not_checked(self):
        assert index_advice.leading_index_columns({"type": "mysql"}, {"orders"}) is None


class TestAdviceWithoutAnIndexCheck:
    def test_no_statement_when_the_dialect_is_not_postgres(self):
        """MySQL needs an index name; the statement would be wrong syntax. Say
        the column is hot, offer nothing to paste."""
        runs = [run("orders", ["region"], "customer", 900)] * 5
        out = index_advice.advise(runs, indexed=None, min_runs=3)
        col = out["tables"][0]["columns"][0]
        assert col["recommended"] is True and col["statement"] is None
        assert col["indexed"] is None

# ── endpoint ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_endpoint_returns_advice_for_the_sources_own_org(
        client, auth_headers, db_session, two_orgs, monkeypatch):
    org = two_orgs["a"]["org"]
    src = DataSource(name="Warehouse", type="postgresql", org_id=org.id,
                     config={"host": "h", "port": 5432, "database": "d",
                             "username": "u", "password": "p"})
    db_session.add(src)
    await db_session.flush()
    now = datetime.utcnow()
    for _ in range(4):
        db_session.add(QueryRun(org_id=org.id, source_kind="directquery",
                                data_source_id=src.id, duration_ms=800, executor="pushdown",
                                source_table="orders", filter_columns=["region"],
                                group_column="customer", created_at=now - timedelta(hours=1)))
    await db_session.commit()
    # The customer's indexes come from their database; not reachable here.
    monkeypatch.setattr(index_advice, "leading_index_columns",
                        lambda cfg, tables: {("orders", "id")})

    r = await client.get(f"/api/v1/data-sources/{src.id}/index-advice",
                         headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tables"][0]["table"] == "orders"
    col = body["tables"][0]["columns"][0]
    assert col["column"] == "region" and col["recommended"] is True
    assert col["statement"] == 'CREATE INDEX ON "orders" ("region");'

    other = await client.get(f"/api/v1/data-sources/{src.id}/index-advice",
                             headers=auth_headers["b"])
    assert other.status_code == 404

@pytest.mark.asyncio
async def test_a_mysql_source_says_unsupported_and_offers_no_statement(
        client, auth_headers, db_session, two_orgs):
    org = two_orgs["a"]["org"]
    src = DataSource(name="Shop", type="mysql", org_id=org.id,
                     config={"host": "h", "port": 3306, "database": "d",
                             "username": "u", "password": "p"})
    db_session.add(src)
    await db_session.flush()
    now = datetime.utcnow()
    for _ in range(4):
        db_session.add(QueryRun(org_id=org.id, source_kind="directquery",
                                data_source_id=src.id, duration_ms=500, executor="pushdown",
                                source_table="orders", filter_columns=["region"],
                                group_column="customer", created_at=now))
    await db_session.commit()
    r = await client.get(f"/api/v1/data-sources/{src.id}/index-advice", headers=auth_headers["a"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["index_check"] == "unsupported"
    col = body["tables"][0]["columns"][0]
    assert col["statement"] is None and col["indexed"] is None
