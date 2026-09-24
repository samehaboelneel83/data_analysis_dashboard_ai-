import pandas as pd
from app.services.widget_data import shape_heatmap, SHAPERS


def sample_df():
    return pd.DataFrame({
        "region":  ["East", "East", "West", "West"],
        "product": ["Toy", "Novelty", "Toy", "Toy"],
        "revenue": [100, 50, 200, 100],
    })


def test_builds_a_grid_of_aggregated_values():
    config = {"roles": {"category": "region", "category2": "product", "measure": "revenue"}}
    result = shape_heatmap(sample_df(), config)
    assert result["type"] == "heatmap"
    assert set(result["rows_axis"]) == {"East", "West"}
    assert set(result["cols_axis"]) == {"Toy", "Novelty"}
    ri = result["rows_axis"].index("West")
    ci = result["cols_axis"].index("Toy")
    assert result["cells"][ri][ci] == 300  # West/Toy: 200 + 100


def test_missing_combination_is_none():
    config = {"roles": {"category": "region", "category2": "product", "measure": "revenue"}}
    result = shape_heatmap(sample_df(), config)
    ri = result["rows_axis"].index("West")
    ci = result["cols_axis"].index("Novelty")
    assert result["cells"][ri][ci] is None  # West/Novelty never occurs


def test_min_max_reflect_actual_cell_range():
    config = {"roles": {"category": "region", "category2": "product", "measure": "revenue"}}
    result = shape_heatmap(sample_df(), config)
    assert result["min"] == 50
    assert result["max"] == 300


def test_missing_required_role_returns_empty():
    config = {"roles": {"category": "region", "measure": "revenue"}}  # no category2
    result = shape_heatmap(sample_df(), config)
    assert result == {"type": "empty", "rows": [], "total": 0}


def test_same_category_and_category2_returns_empty():
    config = {"roles": {"category": "region", "category2": "region", "measure": "revenue"}}
    result = shape_heatmap(sample_df(), config)
    assert result == {"type": "empty", "rows": [], "total": 0}


def test_registered_in_shapers():
    assert SHAPERS["heatmap"] is shape_heatmap
