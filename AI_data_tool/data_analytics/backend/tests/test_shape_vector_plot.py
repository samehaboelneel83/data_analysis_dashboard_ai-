import pandas as pd
from app.services.widget_data import shape_vector_plot, SHAPERS


def sample_df():
    return pd.DataFrame({
        "px": [0, 1, 2],
        "py": [0, 1, 2],
        "magnitude": [5, 10, 15],
        "angle": [0, 90, 180],
    })


def test_builds_one_row_per_point():
    config = {"roles": {"measure": "px", "measure2": "py", "size": "magnitude", "direction": "angle"}}
    result = shape_vector_plot(sample_df(), config)
    assert result["type"] == "vector_plot"
    assert len(result["rows"]) == 3
    r = result["rows"][1]
    assert r["x"] == 1 and r["y"] == 1 and r["size"] == 10 and r["direction"] == 90


def test_column_collision_does_not_crash():
    """House rule: size and direction resolving to the same column must not crash."""
    config = {"roles": {"measure": "px", "measure2": "py", "size": "magnitude", "direction": "magnitude"}}
    result = shape_vector_plot(sample_df(), config)
    assert result["type"] == "vector_plot"
    assert len(result["rows"]) == 3
    assert result["rows"][0]["size"] == result["rows"][0]["direction"]


def test_missing_required_role_returns_empty():
    config = {"roles": {"measure": "px", "measure2": "py", "size": "magnitude"}}   # no direction
    result = shape_vector_plot(sample_df(), config)
    assert result == {"type": "empty", "rows": [], "total": 0}


def test_respects_limit():
    df = pd.DataFrame({"a": list(range(500)), "b": list(range(500)), "s": list(range(500)), "d": list(range(500))})
    config = {"roles": {"measure": "a", "measure2": "b", "size": "s", "direction": "d"}, "limit": 10}
    result = shape_vector_plot(df, config)
    assert len(result["rows"]) == 10


def test_registered_in_shapers():
    assert SHAPERS["vector_plot"] is shape_vector_plot
