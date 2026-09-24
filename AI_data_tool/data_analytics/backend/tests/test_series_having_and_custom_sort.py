"""Post-aggregate filters (HAVING) and explicit category ordering on shape_series.

Both operate on the GROUPED frame: a HAVING condition compares each category's
aggregated value (which no row-level filter can express), and a custom order is
an author's explicit list that beats any computed sort.
"""
import pandas as pd

from app.services.widget_data import shape_series


def df():
    return pd.DataFrame({
        "region": ["US", "US", "CA", "MX", "DE"],
        "amount": [10.0, 20.0, 5.0, 50.0, 7.0],
    })


def base(**extra):
    return {"dimension": "region", "measure": "amount", "aggregation": "sum", **extra}


def test_having_filters_on_the_aggregate_not_the_rows():
    # US rows are 10 and 20 -- each below 25, but their SUM is 30. A row-level
    # filter at 25 would drop US entirely; HAVING must keep it.
    result = shape_series(df(), base(having=[{"op": "gt", "value": 25}]))
    assert {r["name"]: r["value"] for r in result["rows"]} == {"US": 30.0, "MX": 50.0}


def test_having_operators():
    assert {r["name"] for r in shape_series(df(), base(having=[{"op": "lt", "value": 10}]))["rows"]} == {"CA", "DE"}
    assert {r["name"] for r in shape_series(df(), base(having=[{"op": "gte", "value": 30}]))["rows"]} == {"US", "MX"}
    assert {r["name"] for r in shape_series(df(), base(having=[{"op": "eq", "value": 50}]))["rows"]} == {"MX"}


def test_malformed_having_entry_is_ignored_not_fatal():
    result = shape_series(df(), base(having=[{"op": "gt", "value": "not-a-number"}, {"op": None}]))
    assert len(result["rows"]) == 4


def test_grand_total_reflects_surviving_groups_only():
    # `total` documents what the chart shows; a HAVING-filtered chart totalling
    # invisible categories would disagree with its own bars.
    result = shape_series(df(), base(having=[{"op": "gt", "value": 25}]))
    assert sum(r["value"] for r in result["rows"]) == 80.0


def test_custom_order_wins_over_computed_sort():
    result = shape_series(df(), base(sort_custom=["MX", "CA", "US", "DE"]))
    assert [r["name"] for r in result["rows"]] == ["MX", "CA", "US", "DE"]


def test_categories_missing_from_the_list_follow_rather_than_vanish():
    # A typo in the author's list must never silently hide data.
    result = shape_series(df(), base(sort_custom=["DE"]))
    names = [r["name"] for r in result["rows"]]
    assert names[0] == "DE"
    assert set(names) == {"DE", "US", "CA", "MX"}


def test_having_and_custom_order_compose():
    result = shape_series(df(), base(having=[{"op": "gt", "value": 25}], sort_custom=["MX", "US"]))
    assert [r["name"] for r in result["rows"]] == ["MX", "US"]
