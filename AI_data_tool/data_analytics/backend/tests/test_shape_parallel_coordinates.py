import pandas as pd
from app.services.widget_data import shape_parallel_coordinates, SHAPERS


def sample_df():
    return pd.DataFrame({
        "revenue": [0, 50, 100],
        "cost":    [0, 25, 50],
        "units":   [0, 5, 10],
    })


def test_normalizes_each_axis_to_0_1():
    result = shape_parallel_coordinates(sample_df(), {"measures": ["revenue", "cost", "units"]})
    assert result["type"] == "parallel_coordinates"
    assert [a["name"] for a in result["axes"]] == ["revenue", "cost", "units"]
    assert result["axes"][0]["min"] == 0 and result["axes"][0]["max"] == 100
    # first row is all-zero -> normalized to 0.0 on every axis
    assert result["lines"][0] == [0.0, 0.0, 0.0]
    # last row is all-max -> normalized to 1.0 on every axis
    assert result["lines"][2] == [1.0, 1.0, 1.0]
    # middle row is exactly halfway on every axis
    assert result["lines"][1] == [0.5, 0.5, 0.5]


def test_respects_measure_order_not_alphabetical():
    result = shape_parallel_coordinates(sample_df(), {"measures": ["units", "revenue"]})
    assert [a["name"] for a in result["axes"]] == ["units", "revenue"]


def test_fewer_than_two_measures_returns_empty():
    result = shape_parallel_coordinates(sample_df(), {"measures": ["revenue"]})
    assert result == {"type": "empty", "rows": [], "total": 0}


def test_respects_limit():
    df = pd.DataFrame({"a": list(range(500)), "b": list(range(500))})
    result = shape_parallel_coordinates(df, {"measures": ["a", "b"], "limit": 10})
    assert len(result["lines"]) == 10


def test_duplicate_measures_deduped():
    result = shape_parallel_coordinates(sample_df(), {"measures": ["revenue", "revenue", "cost"]})
    assert [a["name"] for a in result["axes"]] == ["revenue", "cost"]


def test_registered_in_shapers():
    assert SHAPERS["parallel_coordinates"] is shape_parallel_coordinates
