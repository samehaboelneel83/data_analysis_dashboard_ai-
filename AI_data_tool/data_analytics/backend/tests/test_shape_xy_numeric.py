import pandas as pd
from app.services.widget_data import shape_xy_numeric, SHAPERS


def test_returns_sorted_xy_pairs():
    df = pd.DataFrame({"month_offset": [3, 1, 2], "unemployment_rate": [5.5, 4.0, 5.0]})
    result = shape_xy_numeric(df, {"roles": {"measure": "month_offset", "measure2": "unemployment_rate"}})
    assert result["type"] == "xy_series"
    assert result["x"] == "month_offset"
    assert result["y"] == "unemployment_rate"
    assert [r["x"] for r in result["rows"]] == [1, 2, 3]
    assert [r["y"] for r in result["rows"]] == [4.0, 5.0, 5.5]


def test_drops_rows_with_nan_in_either_column():
    df = pd.DataFrame({"x": [1, 2, None, 4], "y": [10, None, 30, 40]})
    result = shape_xy_numeric(df, {"roles": {"measure": "x", "measure2": "y"}})
    assert len(result["rows"]) == 2
    assert result["total"] == 4


def test_missing_measure2_returns_empty():
    df = pd.DataFrame({"x": [1, 2, 3]})
    result = shape_xy_numeric(df, {"roles": {"measure": "x"}})
    assert result == {"type": "empty", "rows": [], "total": 0}


def test_respects_limit():
    df = pd.DataFrame({"x": list(range(10)), "y": list(range(10))})
    result = shape_xy_numeric(df, {"roles": {"measure": "x", "measure2": "y"}, "limit": 3})
    assert len(result["rows"]) == 3


def test_registered_in_shapers():
    assert SHAPERS["numeric_series"] is shape_xy_numeric


def test_measure_equal_to_measure2_produces_valid_rows_not_a_crash():
    df = pd.DataFrame({"col": [3, 1, 2, None]})
    result = shape_xy_numeric(df, {"roles": {"measure": "col", "measure2": "col"}})
    assert result["type"] == "xy_series"
    assert [r["x"] for r in result["rows"]] == [1, 2, 3]
    assert [r["y"] for r in result["rows"]] == [1, 2, 3]
    assert result["total"] == 4


def test_works_with_legacy_config_keys_not_just_roles_dict():
    """Regression test: the real frontend sends legacy keys, never a 'roles' object."""
    df = pd.DataFrame({"month_offset": [3, 1, 2], "unemployment_rate": [5.5, 4.0, 5.0]})
    result = shape_xy_numeric(df, {"measure": "month_offset", "measure2": "unemployment_rate"})
    assert result["type"] == "xy_series"
    assert [r["x"] for r in result["rows"]] == [1, 2, 3]
