"""C-11: a percentage on a dual-axis chart's second axis is averaged, not summed,
when the author never chose its aggregation (a right axis read 12,000%)."""
import pandas as pd

from app.services.widget_data import get_widget_data_from_df

DF = pd.DataFrame({"month": ["Jan", "Jan", "Feb", "Feb"],
                   "revenue": [100.0, 200.0, 50.0, 50.0],
                   "margin_pct": [10.0, 30.0, 20.0, 40.0]})


def _by_month(r, key):
    return {row["name"]: row[key] for row in r["rows"]}


def test_blank_aggregation2_averages_a_percentage():
    r = get_widget_data_from_df(DF, {"dimension": "month", "measure": "revenue", "measure2": "margin_pct"},
                                "dual_axis_line")
    assert _by_month(r, "value") == {"Jan": 300.0, "Feb": 100.0}
    assert _by_month(r, "value2") == {"Jan": 20.0, "Feb": 30.0}


def test_an_explicit_aggregation2_is_kept():
    r = get_widget_data_from_df(DF, {"dimension": "month", "measure": "revenue", "measure2": "margin_pct",
                                     "aggregation2": "sum"}, "dual_axis_line")
    assert _by_month(r, "value2") == {"Jan": 40.0, "Feb": 60.0}


def test_an_additive_second_measure_still_inherits_sum():
    df = DF.assign(units=[1, 2, 3, 4])
    r = get_widget_data_from_df(df, {"dimension": "month", "measure": "revenue", "measure2": "units"},
                                "dual_axis_line")
    assert _by_month(r, "value2") == {"Jan": 3, "Feb": 7}


# C-11 round 2: the DuckDB pre-aggregation and the DirectQuery GROUP BY never
# take a second measure, so no path sums it "as sent": both hand the rows to
# shape_dual_series, whose default above applies. Pinned here so a widened
# pushdown cannot silently bring the 12,000% axis back.
import pytest  # noqa: E402


def test_duckdb_pushdown_declines_a_second_measure():
    from app.services import duck_agg
    with pytest.raises(duck_agg.Ineligible):
        duck_agg.plan({"dimension": "month", "measure": "revenue", "aggregation": "sum", "measure2": "margin_pct"},
                      ["month", "revenue", "margin_pct"], "src")


@pytest.mark.parametrize("wt", ["dual_axis_line", "dual_axis_bar", "dual_axis_bar_line",
                                "dual_axis_time_series", "comparative_time_series", "butterfly"])
def test_directquery_group_by_declines_dual_axis_charts(wt):
    from app.services.direct_query import plan_query, DirectQueryUnsupported
    with pytest.raises(DirectQueryUnsupported):
        plan_query({"dimension": "month", "measure": "revenue", "measure2": "margin_pct"}, wt)
