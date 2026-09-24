import pytest

from app.services.direct_query import DirectQueryUnsupported, plan_query


def test_plan_query_returns_plan_for_supported_config():
    plan = plan_query({"dimension": "region", "measure": "revenue", "aggregation": "sum"}, "bar")

    assert plan.dim == "region"
    assert plan.meas == "revenue"
    assert plan.agg == "sum"


def test_plan_query_rejects_unknown_widget_type():
    with pytest.raises(DirectQueryUnsupported):
        plan_query({"dimension": "region", "measure": "revenue"}, "gantt_chart")


def test_plan_query_rejects_missing_dimension():
    with pytest.raises(DirectQueryUnsupported):
        plan_query({"measure": "revenue"}, "bar")


def test_plan_query_allows_missing_measure_as_a_count_of_rows_plan():
    """No measure means 'count of rows per dimension value' (see _run_count_series
    in direct_query.py) -- a valid, common widget shape, not an error."""
    plan = plan_query({"dimension": "region"}, "bar")
    assert plan.dim == "region"
    assert plan.meas is None


def test_plan_query_rejects_pct_aggregation_without_a_measure():
    with pytest.raises(DirectQueryUnsupported):
        plan_query({"dimension": "region", "aggregation": "pct"}, "bar")


def test_plan_query_rejects_crosstab_dimension2():
    with pytest.raises(DirectQueryUnsupported):
        plan_query({"dimension": "region", "dimension2": "product", "measure": "revenue"}, "crosstab")


def test_plan_query_rejects_running_totals():
    with pytest.raises(DirectQueryUnsupported):
        plan_query({"dimension": "region", "measure": "revenue", "running": "sum"}, "bar")


def test_plan_query_rejects_cross_column_sort():
    with pytest.raises(DirectQueryUnsupported):
        plan_query({"dimension": "region", "measure": "revenue", "sort_col": "profit"}, "bar")


def test_plan_query_allows_sort_col_matching_dimension():
    plan = plan_query({"dimension": "region", "measure": "revenue", "sort_col": "region"}, "bar")
    assert plan.dim == "region"


@pytest.mark.parametrize("agg", ["sum", "avg", "mean", "min", "max", "median", "p25", "p75", "p90", "p95"])
def test_plan_query_accepts_grain_safe_aggregations(agg):
    plan = plan_query({"dimension": "region", "measure": "revenue", "aggregation": agg}, "bar")
    assert plan.agg == agg


@pytest.mark.parametrize("agg", ["count", "frequency", "countd", "distinct", "std", "variance", "range", "pct"])
def test_plan_query_rejects_non_grain_safe_aggregations(agg):
    """These aggregations are NOT safe to push down under the grain invariant: applying
    the same aggregation a second time to an already-aggregated singleton does not
    reproduce the original value (e.g. count of one row is 1, not the real count)."""
    with pytest.raises(DirectQueryUnsupported):
        plan_query({"dimension": "region", "measure": "revenue", "aggregation": agg}, "bar")


def test_plan_query_rejects_unsupported_filter_operator():
    config = {
        "dimension": "region", "measure": "revenue",
        "filters": [{"column": "region", "op": "like", "value": "east"}],
    }
    with pytest.raises(DirectQueryUnsupported):
        plan_query(config, "bar")


def test_plan_query_accepts_supported_filter_operators():
    config = {
        "dimension": "region", "measure": "revenue",
        "filters": [{"column": "revenue", "op": "gte", "value": 100}],
    }
    plan = plan_query(config, "bar")
    assert plan.filters == config["filters"]
