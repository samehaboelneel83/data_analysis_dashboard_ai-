"""A bound target column in the series shape (the targeted-bar row)."""
import pandas as pd

from app.services.widget_data import get_widget_data_from_df

DF = pd.DataFrame({
    "region": ["US", "US", "CA"],
    "revenue": [10.0, 20.0, 5.0],
    "target": [12.0, 12.0, 8.0],
})


def test_target_rides_along_per_group_with_the_same_aggregation():
    r = get_widget_data_from_df(DF.copy(), {
        "dimension": "region", "measure": "revenue", "target": "target",
        "aggregation": "sum"}, "bar")
    by = {row["name"]: row for row in r["rows"]}
    # Summed like the measure: two US rows -> 24, not 12. An averaged target under a
    # summed measure would compare incomparable numbers.
    assert by["US"] == {"name": "US", "value": 30.0, "target": 24.0}
    assert by["CA"] == {"name": "CA", "value": 5.0, "target": 8.0}


def test_without_a_target_the_rows_are_unchanged():
    r = get_widget_data_from_df(DF.copy(), {
        "dimension": "region", "measure": "revenue", "aggregation": "sum"}, "bar")
    assert all("target" not in row for row in r["rows"])


def test_a_non_numeric_target_column_is_ignored_not_crashed():
    df = DF.assign(target=["a", "b", "c"])
    r = get_widget_data_from_df(df, {
        "dimension": "region", "measure": "revenue", "target": "target",
        "aggregation": "sum"}, "bar")
    assert all("target" not in row for row in r["rows"])
