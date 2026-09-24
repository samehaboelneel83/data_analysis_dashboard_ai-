"""Unit tests for the post-aggregation measure evaluator.

Measures differ from row-level calculated columns: aggregation functions inside a
measure expression aggregate *within the visual's grouping grain*, and TOTAL()
escapes that grain to the whole filter context.
"""
import pandas as pd
import pytest

from app.services.measure_eval import evaluate_measure


def test_pct_of_total_by_region_varies_by_group():
    df = pd.DataFrame({
        "region": ["East", "East", "West", "West"],
        "sales": [100, 50, 200, 100],
    })

    result = evaluate_measure("SUM(sales) / TOTAL(SUM(sales)) * 100", df, group_cols=["region"])

    assert isinstance(result, pd.Series)
    assert len(result) == 2
    assert round(result["East"], 2) == 33.33   # 150 / 450
    assert round(result["West"], 2) == 66.67   # 300 / 450


def test_group_sums_align_for_a_ratio_of_two_measures():
    df = pd.DataFrame({
        "region": ["East", "East", "West"],
        "profit": [10, 20, 50],
        "revenue": [100, 100, 200],
    })

    result = evaluate_measure("SUM(profit) / SUM(revenue) * 100", df, group_cols=["region"])

    assert round(result["East"], 2) == 15.0    # 30 / 200
    assert round(result["West"], 2) == 25.0    # 50 / 200


def test_scalar_profit_margin_with_no_grouping():
    df = pd.DataFrame({"profit": [10, 20], "revenue": [100, 200]})

    result = evaluate_measure("SUM(profit) / SUM(revenue) * 100", df, group_cols=[])

    assert not isinstance(result, pd.Series)
    assert result == 10.0                       # 30 / 300


def test_total_without_grouping_equals_the_plain_aggregate():
    df = pd.DataFrame({"sales": [1, 2, 3]})

    assert evaluate_measure("TOTAL(SUM(sales))", df, group_cols=[]) == 6


def test_two_grouping_columns_produce_one_value_per_intersection():
    df = pd.DataFrame({
        "region": ["East", "East", "West", "West"],
        "product": ["A", "B", "A", "B"],
        "sales": [10, 20, 30, 40],
    })

    result = evaluate_measure("SUM(sales)", df, group_cols=["region", "product"])

    assert len(result) == 4
    assert result[("East", "B")] == 20
    assert result[("West", "A")] == 30


def test_count_and_countd_are_group_aware():
    df = pd.DataFrame({
        "region": ["East", "East", "East", "West"],
        "rep": ["a", "a", "b", "c"],
    })

    counts = evaluate_measure("COUNT(rep)", df, group_cols=["region"])
    distinct = evaluate_measure("COUNTD(rep)", df, group_cols=["region"])

    assert counts["East"] == 3 and counts["West"] == 1
    assert distinct["East"] == 2 and distinct["West"] == 1


def test_nested_total_is_rejected():
    df = pd.DataFrame({"sales": [1, 2]})

    with pytest.raises(ValueError, match="TOTAL"):
        evaluate_measure("TOTAL(TOTAL(SUM(sales)))", df, group_cols=[])


def test_attribute_access_is_rejected_by_the_shared_safety_check():
    df = pd.DataFrame({"sales": [1, 2]})

    with pytest.raises(ValueError):
        evaluate_measure("SUM(sales.values)", df, group_cols=[])


def test_row_level_window_functions_are_not_available_in_measures():
    df = pd.DataFrame({"region": ["East", "West"], "sales": [1, 2]})

    with pytest.raises(ValueError):
        evaluate_measure("CUMSUM(sales)", df, group_cols=["region"])


def test_empty_filter_context_returns_an_empty_series_not_a_crash():
    df = pd.DataFrame({"region": pd.Series([], dtype="object"), "sales": pd.Series([], dtype="float")})

    result = evaluate_measure("SUM(sales)", df, group_cols=["region"])

    assert isinstance(result, pd.Series)
    assert len(result) == 0


def test_unknown_column_raises_rather_than_silently_returning_zero():
    df = pd.DataFrame({"sales": [1, 2]})

    with pytest.raises(ValueError):
        evaluate_measure("SUM(nope)", df, group_cols=[])
