import pandas as pd
from app.services.widget_data import shape_gauge, SHAPERS


def sample_df():
    return pd.DataFrame({"revenue": [10, 20, 30], "quota": [15, 15, 15]})


def test_aggregates_measure_to_a_single_value():
    result = shape_gauge(sample_df(), {"roles": {"measure": "revenue"}, "aggregation": "sum"})
    assert result["type"] == "gauge"
    assert result["value"] == 60
    assert result["target"] is None


def test_target_role_aggregated_same_way():
    result = shape_gauge(sample_df(), {"roles": {"measure": "revenue", "target": "quota"}, "aggregation": "sum"})
    assert result["value"] == 60
    assert result["target"] == 45   # sum of quota column


def test_literal_target_value_used_when_no_target_role():
    result = shape_gauge(sample_df(), {"roles": {"measure": "revenue"}, "aggregation": "sum", "target_value": 75})
    assert result["target"] == 75


def test_target_role_takes_priority_over_literal_target_value():
    result = shape_gauge(sample_df(), {"roles": {"measure": "revenue", "target": "quota"}, "aggregation": "sum", "target_value": 999})
    assert result["target"] == 45


def test_missing_measure_returns_empty():
    result = shape_gauge(sample_df(), {"roles": {}})
    assert result == {"type": "empty", "rows": [], "total": 0}


def test_literal_target_value_zero_is_honored():
    result = shape_gauge(sample_df(), {"roles": {"measure": "revenue"}, "aggregation": "sum", "target_value": 0})
    assert result["target"] == 0


def test_literal_target_value_nan_string_becomes_none():
    result = shape_gauge(sample_df(), {"roles": {"measure": "revenue"}, "aggregation": "sum", "target_value": "nan"})
    assert result["target"] is None


def test_registered_in_shapers():
    assert SHAPERS["gauge"] is shape_gauge


def test_datetime_target_column_degrades_to_none_instead_of_crashing():
    df = pd.DataFrame({
        "revenue": [10, 20, 30],
        "signup_date": pd.to_datetime(["2024-01-01", "2024-02-01", "2024-03-01"]),
    })
    result = shape_gauge(df, {"roles": {"measure": "revenue", "target": "signup_date"}, "aggregation": "sum"})
    assert result["type"] == "gauge"
    assert result["value"] == 60
    assert result["target"] is None


def test_string_target_column_with_avg_degrades_to_none_instead_of_crashing():
    df = pd.DataFrame({
        "revenue": [10, 20, 30],
        "region": ["east", "west", "north"],
    })
    result = shape_gauge(df, {"roles": {"measure": "revenue", "target": "region"}, "aggregation": "avg"})
    assert result["type"] == "gauge"
    assert result["value"] == 20
    assert result["target"] is None
