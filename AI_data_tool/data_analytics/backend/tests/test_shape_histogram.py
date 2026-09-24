import pandas as pd
from app.services.widget_data import shape_histogram, SHAPERS


def test_bins_numeric_data_into_default_10_bins():
    df = pd.DataFrame({"revenue": list(range(100))})
    result = shape_histogram(df, {"measure": "revenue"})
    assert result["type"] == "series"
    assert len(result["rows"]) == 10
    assert sum(r["value"] for r in result["rows"]) == 100


def test_custom_bin_count():
    df = pd.DataFrame({"revenue": list(range(100))})
    result = shape_histogram(df, {"measure": "revenue", "bins": 4})
    assert len(result["rows"]) == 4


def test_missing_measure_returns_empty():
    df = pd.DataFrame({"revenue": [1, 2, 3]})
    result = shape_histogram(df, {"measure": "nonexistent"})
    assert result == {"type": "empty", "rows": [], "total": 0}


def test_drops_nan_before_binning():
    df = pd.DataFrame({"revenue": [1.0, 2.0, None, 4.0, 5.0]})
    result = shape_histogram(df, {"measure": "revenue", "bins": 2})
    assert sum(r["value"] for r in result["rows"]) == 4


def test_registered_in_shapers():
    assert SHAPERS["histogram"] is shape_histogram
