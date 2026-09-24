"""SQL Server DirectQuery support.

SQL Server was originally excluded from DirectQuery because `TOP n` sits after
SELECT rather than at the end of the query, which does not fit the
`... GROUP BY ... ORDER BY ... <limit>` shape build_sql produces. SQL Server 2012+
supports `OFFSET ... ROWS FETCH NEXT ... ROWS ONLY` as a *trailing* clause after
ORDER BY, which does fit — build_sql always emits an ORDER BY, which that syntax
requires.
"""
from types import SimpleNamespace

import pytest

from app.services.direct_query import (
    SUPPORTED_DIALECTS, DirectQueryUnsupported, build_sql, build_count_sql,
    build_row_fetch_sql, plan_query, plan_row_fetch,
)


def _dataset(source_table=None, source_query=None):
    return SimpleNamespace(source_table=source_table, source_query=source_query)


def test_sqlserver_is_a_supported_dialect():
    assert "sqlserver" in SUPPORTED_DIALECTS


def test_sqlserver_limit_uses_offset_fetch_not_top():
    plan = plan_query({"dimension": "region", "measure": "revenue", "limit": 25}, "bar")
    sql, _ = build_sql(_dataset(source_table="sales"), plan, "sqlserver")

    assert "OFFSET 0 ROWS FETCH NEXT 25 ROWS ONLY" in sql
    assert "TOP" not in sql
    assert "LIMIT" not in sql


def test_sqlserver_limit_clause_follows_order_by_which_it_requires():
    plan = plan_query({"dimension": "region", "measure": "revenue"}, "bar")
    sql, _ = build_sql(_dataset(source_table="sales"), plan, "sqlserver")

    assert sql.index("ORDER BY") < sql.index("OFFSET 0 ROWS")


def test_sqlserver_group_by_shape_matches_the_other_dialects():
    plan = plan_query({"dimension": "region", "measure": "revenue", "aggregation": "sum"}, "bar")
    sql, params = build_sql(_dataset(source_table="sales"), plan, "sqlserver")

    assert 'SELECT "region" AS "region", SUM("revenue") AS "revenue"' in sql
    assert 'FROM (SELECT * FROM "sales") AS src' in sql
    assert 'GROUP BY "region"' in sql
    assert params == {}


def test_sqlserver_count_query_is_dialect_independent():
    plan = plan_query({"dimension": "region", "measure": "revenue"}, "bar")
    sql, _ = build_count_sql(_dataset(source_table="sales"), plan, "sqlserver")

    assert sql == 'SELECT COUNT(*) FROM (SELECT * FROM "sales") AS src'


def test_sqlserver_carries_filters_as_bound_parameters():
    plan = plan_query({
        "dimension": "region", "measure": "revenue",
        "filters": [{"column": "year", "op": "eq", "value": 2024}],
    }, "bar")
    sql, params = build_sql(_dataset(source_table="sales"), plan, "sqlserver")

    assert '"year" = :f0' in sql
    assert params == {"f0": 2024}


def test_sqlserver_rejects_percentile_aggregations():
    """T-SQL's PERCENTILE_CONT is a window function, not an aggregate, so it cannot
    sit in a GROUP BY select list. Rejecting beats emitting SQL that will not run."""
    plan = plan_query({"dimension": "region", "measure": "revenue", "aggregation": "p90"}, "bar")

    with pytest.raises(DirectQueryUnsupported, match="p90"):
        build_sql(_dataset(source_table="sales"), plan, "sqlserver")


def test_sqlserver_row_fetch_still_has_an_order_by_when_not_sampling():
    """OFFSET/FETCH is only legal after ORDER BY. The row-fetch path omits ORDER BY
    when it is not sampling, so without a placeholder the emitted T-SQL is invalid."""
    plan = plan_row_fetch({}, "table")
    sql, _ = build_row_fetch_sql(_dataset(source_table="sales"), plan, "sqlserver", cap=5000, sampled=False)

    assert "ORDER BY" in sql
    assert sql.index("ORDER BY") < sql.index("OFFSET 0 ROWS")


def test_sqlserver_row_fetch_orders_randomly_when_sampling():
    plan = plan_row_fetch({}, "table")
    sql, _ = build_row_fetch_sql(_dataset(source_table="sales"), plan, "sqlserver", cap=5000, sampled=True)

    assert "ORDER BY NEWID()" in sql
    assert "OFFSET 0 ROWS FETCH NEXT 5000 ROWS ONLY" in sql


def test_other_dialects_row_fetch_is_unchanged_when_not_sampling():
    """The ORDER BY placeholder is a T-SQL requirement, so it must not leak into
    dialects that are happy with a bare LIMIT."""
    plan = plan_row_fetch({}, "table")

    for dialect in ("postgresql", "mysql", "sqlite"):
        sql, _ = build_row_fetch_sql(_dataset(source_table="s"), plan, dialect, cap=100, sampled=False)
        assert "ORDER BY" not in sql
        assert sql.endswith("LIMIT 100")


def test_other_dialects_keep_their_own_limit_syntax():
    plan = plan_query({"dimension": "region", "measure": "revenue", "limit": 10}, "bar")

    assert "LIMIT 10" in build_sql(_dataset(source_table="s"), plan, "postgresql")[0]
    assert "LIMIT 10" in build_sql(_dataset(source_table="s"), plan, "mysql")[0]
    assert "LIMIT 10" in build_sql(_dataset(source_table="s"), plan, "sqlite")[0]
    assert "FETCH FIRST 10 ROWS ONLY" in build_sql(_dataset(source_table="s"), plan, "oracle")[0]
