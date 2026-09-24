from types import SimpleNamespace

from app.services.direct_query import DirectQueryUnsupported, build_count_sql, build_sql, plan_query


def _dataset(source_table=None, source_query=None):
    return SimpleNamespace(source_table=source_table, source_query=source_query)


def test_build_sql_basic_group_by():
    plan = plan_query({"dimension": "region", "measure": "revenue", "aggregation": "sum"}, "bar")
    sql, params = build_sql(_dataset(source_table="sales"), plan, "postgresql")

    assert 'SELECT "region" AS "region", SUM("revenue") AS "revenue"' in sql
    assert 'FROM (SELECT * FROM "sales") AS src' in sql
    assert 'GROUP BY "region"' in sql
    assert params == {}


def test_build_sql_orders_by_measure_value_descending_by_default():
    plan = plan_query({"dimension": "region", "measure": "revenue"}, "bar")
    sql, _ = build_sql(_dataset(source_table="sales"), plan, "postgresql")

    assert "ORDER BY 2 DESC" in sql


def test_build_sql_orders_ascending_when_sort_asc():
    plan = plan_query({"dimension": "region", "measure": "revenue", "sort": "asc"}, "bar")
    sql, _ = build_sql(_dataset(source_table="sales"), plan, "postgresql")

    assert "ORDER BY 2 ASC" in sql


def test_build_sql_orders_by_dimension_when_sort_by_name():
    plan = plan_query({"dimension": "region", "measure": "revenue", "sort_by": "name"}, "bar")
    sql, _ = build_sql(_dataset(source_table="sales"), plan, "postgresql")

    assert "ORDER BY 1" in sql


def test_build_sql_includes_where_for_comparison_filter():
    config = {
        "dimension": "region", "measure": "revenue",
        "filters": [{"column": "revenue", "op": "gte", "value": 100}],
    }
    plan = plan_query(config, "bar")
    sql, params = build_sql(_dataset(source_table="sales"), plan, "postgresql")

    assert 'WHERE "revenue" >= :f0' in sql
    assert params == {"f0": 100}


def test_build_sql_in_operator_expands_to_multiple_params():
    config = {
        "dimension": "region", "measure": "revenue",
        "filters": [{"column": "region", "op": "in", "value": ["east", "west"]}],
    }
    plan = plan_query(config, "bar")
    sql, params = build_sql(_dataset(source_table="sales"), plan, "postgresql")

    assert 'WHERE "region" IN (:f0_0, :f0_1)' in sql
    assert params == {"f0_0": "east", "f0_1": "west"}


def test_build_sql_source_query_wraps_as_subquery_not_concatenated():
    plan = plan_query({"dimension": "region", "measure": "revenue"}, "bar")
    sql, _ = build_sql(_dataset(source_query="SELECT * FROM raw_sales WHERE active = 1"), plan, "postgresql")

    assert "FROM (SELECT * FROM raw_sales WHERE active = 1) AS src" in sql


def test_build_sql_strips_trailing_semicolon_from_source_query():
    plan = plan_query({"dimension": "region", "measure": "revenue"}, "bar")
    sql, _ = build_sql(_dataset(source_query="SELECT * FROM raw_sales;"), plan, "postgresql")

    assert "FROM (SELECT * FROM raw_sales) AS src" in sql


def test_build_sql_oracle_uses_fetch_first_not_limit():
    plan = plan_query({"dimension": "region", "measure": "revenue", "limit": 10}, "bar")
    sql, _ = build_sql(_dataset(source_table="sales"), plan, "oracle")

    assert "FETCH FIRST 10 ROWS ONLY" in sql
    assert "LIMIT" not in sql


def test_build_sql_percentile_uses_percentile_cont():
    plan = plan_query({"dimension": "region", "measure": "revenue", "aggregation": "p90"}, "bar")
    sql, _ = build_sql(_dataset(source_table="sales"), plan, "postgresql")

    assert 'PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY "revenue")' in sql


def test_build_sql_median_percentile_rejected_for_mysql():
    plan = plan_query({"dimension": "region", "measure": "revenue", "aggregation": "median"}, "bar")
    try:
        build_sql(_dataset(source_table="sales"), plan, "mysql")
        assert False, "expected DirectQueryUnsupported"
    except DirectQueryUnsupported:
        pass


def test_build_count_sql_counts_underlying_rows_not_groups():
    """shape_series reports `total` as the row count of the frame it was handed
    -- for import mode that's every raw row; for DirectQuery the aggregate query
    only returns one row per group. build_count_sql builds the companion query
    that recovers the true underlying row count, applying the same filters."""
    plan = plan_query({"dimension": "region", "measure": "revenue"}, "bar")
    sql, params = build_count_sql(_dataset(source_table="sales"), plan, "postgresql")

    assert sql == 'SELECT COUNT(*) FROM (SELECT * FROM "sales") AS src'
    assert params == {}


def test_build_count_sql_includes_same_where_as_build_sql():
    config = {
        "dimension": "region", "measure": "revenue",
        "filters": [{"column": "revenue", "op": "gte", "value": 100}],
    }
    plan = plan_query(config, "bar")
    sql, params = build_count_sql(_dataset(source_table="sales"), plan, "postgresql")

    assert sql == 'SELECT COUNT(*) FROM (SELECT * FROM "sales") AS src WHERE "revenue" >= :f0'
    assert params == {"f0": 100}


def test_build_sql_wraps_rls_predicate_around_base_before_widget_filters():
    """The RLS predicate must sit in its own inner subquery boundary -- so a
    widget-level filter's own WHERE (applied outside that subquery) can never
    resurrect a row the RLS subquery already excluded, even via an OR."""
    plan = plan_query({"dimension": "region", "measure": "revenue"}, "bar")
    sql, params = build_sql(
        _dataset(source_table="sales"), plan, "postgresql",
        rls_where='"region" = :r0', rls_params={"r0": "east"},
    )

    assert 'FROM (SELECT * FROM (SELECT * FROM "sales") AS rls_src WHERE "region" = :r0) AS src' in sql
    assert params == {"r0": "east"}


def test_build_sql_merges_rls_and_filter_params_without_collision():
    config = {
        "dimension": "region", "measure": "revenue",
        "filters": [{"column": "revenue", "op": "gte", "value": 100}],
    }
    plan = plan_query(config, "bar")
    sql, params = build_sql(
        _dataset(source_table="sales"), plan, "postgresql",
        rls_where='"region" = :r0', rls_params={"r0": "east"},
    )

    assert params == {"r0": "east", "f0": 100}


def test_build_sql_without_rls_where_is_unchanged():
    plan = plan_query({"dimension": "region", "measure": "revenue"}, "bar")
    sql, _ = build_sql(_dataset(source_table="sales"), plan, "postgresql")

    assert "rls_src" not in sql
    assert 'FROM (SELECT * FROM "sales") AS src' in sql


def test_build_count_sql_also_wraps_rls_predicate():
    plan = plan_query({"dimension": "region", "measure": "revenue"}, "bar")
    sql, params = build_count_sql(
        _dataset(source_table="sales"), plan, "postgresql",
        rls_where='"region" = :r0', rls_params={"r0": "east"},
    )

    assert sql == 'SELECT COUNT(*) FROM (SELECT * FROM (SELECT * FROM "sales") AS rls_src WHERE "region" = :r0) AS src'
    assert params == {"r0": "east"}
