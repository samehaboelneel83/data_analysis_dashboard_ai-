import pandas as pd
import pytest
from app.services.widget_data import get_widget_data_from_df, SHAPERS, shape_series


@pytest.fixture
def sample_df():
    return pd.DataFrame({
        "region": ["East", "East", "West", "West", "North"],
        "product": ["A", "B", "A", "B", "A"],
        "revenue": [100, 150, 200, 50, 300],
    })


@pytest.mark.parametrize("widget_type", ["bar", "line", "pie", "donut", "treemap", "scatter"])
def test_shapers_registry_dispatches_grouped_series(sample_df, widget_type):
    config = {"dimension": "region", "measure": "revenue", "aggregation": "sum"}
    direct = shape_series(sample_df, config)
    via_registry = SHAPERS[widget_type](sample_df, config)
    assert via_registry == direct
    assert via_registry["type"] == "series"
    assert {r["name"] for r in via_registry["rows"]} == {"East", "West", "North"}


def test_unknown_widget_type_falls_back_to_shape_series(sample_df):
    config = {"dimension": "region", "measure": "revenue"}
    result = get_widget_data_from_df(sample_df, config, widget_type="some_future_chart_type")
    expected = shape_series(sample_df, config)
    # The dispatcher adds the one population field every result carries.
    assert {k: v for k, v in result.items() if k != "rows_scanned"} == expected
    assert result["rows_scanned"] == expected["total"]


def test_every_result_says_what_population_it_describes_and_what_it_dropped(sample_df):
    """MASTER_PLAN Part IV criterion 3: rows_scanned / truncation everywhere."""
    n = len(sample_df)
    for wt, cfg in [
        ("bar", {"dimension": "region", "measure": "revenue"}),
        ("crosstab", {"dimension": "region", "dimension2": "product", "measure": "revenue"}),
        ("dual_axis_bar", {"dimension": "region", "measure": "revenue", "measure2": "revenue"}),
        ("waterfall", {"dimension": "region", "measure": "revenue"}),
        ("box_plot", {"dimension": "region", "measure": "revenue"}),
        ("numeric_series", {"measure": "revenue", "measure2": "revenue"}),
        ("gauge", {"measure": "revenue"}),
        ("histogram", {"measure": "revenue"}),
    ]:
        r = get_widget_data_from_df(sample_df, cfg, widget_type=wt)
        assert r.get("rows_scanned") == n, (wt, r.get("rows_scanned"))
        assert "truncation" in r and "applied" in r["truncation"], wt


def test_a_capped_dual_axis_chart_says_it_was_cut(sample_df):
    cfg = {"dimension": "region", "measure": "revenue", "measure2": "revenue", "limit": 1}
    r = get_widget_data_from_df(sample_df, cfg, widget_type="dual_axis_bar")
    assert r["truncation"]["applied"] is True
    assert r["truncation"]["shown"] == 1 and r["truncation"]["of"] > 1


def test_crosstab_shape_unaffected_by_widget_type(sample_df):
    config = {"dimension": "region", "dimension2": "product", "measure": "revenue"}
    result = get_widget_data_from_df(sample_df, config, widget_type="bar")
    assert result["type"] == "crosstab"


def test_a_frame_level_sum_fx_column_listed_row_by_row_when_aggregation_is_none():
    """Live: all_employee_count = SUM(employee_count) writes the same total onto
    every row. A KPI/table with the default Sum then adds those copies together
    (9 × 265,932 = 2,393,388). aggregation=none must list the column's values
    instead of collapsing them."""
    from app.services.widget_data import apply_calculated_columns

    df = pd.DataFrame({"employee_count": [10, 20, 30]})
    df = apply_calculated_columns(
        df, [{"name": "all_employee_count", "expression": "SUM(employee_count)"}])
    summed = shape_series(df, {"measure": "all_employee_count", "aggregation": "sum"})
    assert summed["type"] == "scalar"
    assert summed["rows"][0]["value"] == 180
    assert summed["total"] == 3

    raw = shape_series(df, {"measure": "all_employee_count", "aggregation": "none"})
    assert raw["type"] == "table"
    assert raw["columns"] == ["all_employee_count"]
    assert raw["rows"] == [[60], [60], [60]]
    assert raw["total"] == 3


def test_the_copilot_agg_key_is_read_as_aggregation(sample_df):
    via_alias = shape_series(sample_df, {"dimension": "region", "measure": "revenue",
                                         "agg": "avg"})
    via_name = shape_series(sample_df, {"dimension": "region", "measure": "revenue",
                                        "aggregation": "avg"})
    assert via_alias == via_name
