import pandas as pd
from app.services.widget_data import shape_box_plot, SHAPERS


def sample_df():
    return pd.DataFrame({
        "region": ["East"] * 6 + ["West"] * 6,
        "revenue": [10, 12, 13, 14, 15, 100,   # East: one clear outlier (100)
                    50, 51, 52, 53, 54, 55],    # West: tight cluster, no outliers
    })


def test_computes_quartiles_per_category():
    result = shape_box_plot(sample_df(), {"roles": {"category": "region", "measure": "revenue"}})
    assert result["type"] == "box_plot"
    names = [r["name"] for r in result["rows"]]
    assert names == ["East", "West"]
    west = next(r for r in result["rows"] if r["name"] == "West")
    assert west["min"] == 50 and west["max"] == 55
    assert west["q1"] < west["median"] < west["q3"]
    assert west["outliers"] == []


def test_separates_outliers_from_min_max():
    result = shape_box_plot(sample_df(), {"roles": {"category": "region", "measure": "revenue"}})
    east = next(r for r in result["rows"] if r["name"] == "East")
    assert 100 in east["outliers"]
    assert east["max"] < 100          # the outlier is excluded from max, not included in it
    assert east["min"] == 10


def test_single_point_category_does_not_crash():
    df = pd.DataFrame({"cat": ["A"], "val": [42]})
    result = shape_box_plot(df, {"roles": {"category": "cat", "measure": "val"}})
    row = result["rows"][0]
    assert row["min"] == row["q1"] == row["median"] == row["q3"] == row["max"] == 42
    assert row["outliers"] == []


def test_missing_required_role_returns_empty():
    result = shape_box_plot(sample_df(), {"roles": {"category": "region"}})
    assert result == {"type": "empty", "rows": [], "total": 0}


def test_respects_limit():
    df = pd.DataFrame({"cat": [f"c{i}" for i in range(30) for _ in range(3)],
                        "val": list(range(90))})
    result = shape_box_plot(df, {"roles": {"category": "cat", "measure": "val"}, "limit": 5})
    assert len(result["rows"]) == 5


def test_registered_in_shapers():
    assert SHAPERS["box_plot"] is shape_box_plot
