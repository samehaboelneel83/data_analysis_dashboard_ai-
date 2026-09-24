import pandas as pd
from app.services.widget_data import shape_bubble_animated, SHAPERS


def sample_df():
    return pd.DataFrame({
        "region": ["East", "East", "East", "East", "West", "West"],
        "year":   [2023, 2023, 2024, 2024, 2023, 2024],
        "revenue": [100, 50, 120, 60, 200, 220],
        "cost":    [60, 20, 70, 25, 90, 95],
        "units":   [10, 5, 12, 6, 20, 22],
    })


def test_groups_by_category_and_animation_frame():
    config = {"roles": {"category": "region", "measure": "revenue", "measure2": "cost", "size": "units", "animation": "year"}}
    result = shape_bubble_animated(sample_df(), config)
    assert result["type"] == "bubble_animated_series"
    assert result["frames"] == [2023, 2024]
    east_2023 = next(r for r in result["rows"] if r["name"] == "East" and r["frame"] == 2023)
    assert east_2023["x"] == 150  # 100 + 50


def test_missing_animation_role_returns_empty():
    config = {"roles": {"category": "region", "measure": "revenue", "measure2": "cost", "size": "units"}}
    result = shape_bubble_animated(sample_df(), config)
    assert result == {"type": "empty", "rows": [], "total": 0}


def test_animation_same_as_category_returns_empty():
    """Regression guard: animation colliding with category (dimension) makes
    groupby([cat, anim]).reset_index() try to insert a column that already exists
    (ValueError: cannot insert region, already exists)."""
    config = {"roles": {"category": "region", "measure": "revenue", "measure2": "cost", "size": "units", "animation": "region"}}
    result = shape_bubble_animated(sample_df(), config)
    assert result == {"type": "empty", "rows": [], "total": 0}


def test_animation_same_as_measure_returns_empty():
    """Regression guard: animation colliding with measure (x) makes
    groupby([cat, anim])[num_cols].reset_index() try to insert a column that already
    exists (ValueError: cannot insert revenue, already exists)."""
    config = {"roles": {"category": "region", "measure": "revenue", "measure2": "cost", "size": "units", "animation": "revenue"}}
    result = shape_bubble_animated(sample_df(), config)
    assert result == {"type": "empty", "rows": [], "total": 0}


def test_category_same_as_measure_returns_empty():
    """Regression guard: category colliding with measure (x) makes
    groupby([cat, anim])[num_cols].agg(...).reset_index() try to insert a column
    that already exists (ValueError: cannot insert revenue, already exists)."""
    config = {"roles": {"category": "revenue", "measure": "revenue", "measure2": "cost", "size": "units", "animation": "year"}}
    result = shape_bubble_animated(sample_df(), config)
    assert result == {"type": "empty", "rows": [], "total": 0}


def test_category_same_as_measure2_returns_empty():
    """Regression guard: category colliding with measure2 (y) makes
    groupby([cat, anim])[num_cols].agg(...).reset_index() try to insert a column
    that already exists (ValueError: cannot insert cost, already exists)."""
    config = {"roles": {"category": "cost", "measure": "revenue", "measure2": "cost", "size": "units", "animation": "year"}}
    result = shape_bubble_animated(sample_df(), config)
    assert result == {"type": "empty", "rows": [], "total": 0}


def test_category_same_as_size_returns_empty():
    """Regression guard: category colliding with size makes
    groupby([cat, anim])[num_cols].agg(...).reset_index() try to insert a column
    that already exists (ValueError: cannot insert units, already exists)."""
    config = {"roles": {"category": "units", "measure": "revenue", "measure2": "cost", "size": "units", "animation": "year"}}
    result = shape_bubble_animated(sample_df(), config)
    assert result == {"type": "empty", "rows": [], "total": 0}


def test_category_same_as_color_returns_empty():
    """Regression guard: category colliding with color makes
    groupby([cat, anim])[num_cols].agg(...).reset_index() try to insert a column
    that already exists (ValueError: cannot insert cost, already exists)."""
    config = {"roles": {"category": "cost", "measure": "revenue", "measure2": "units", "size": "units", "color": "cost", "animation": "year"}}
    result = shape_bubble_animated(sample_df(), config)
    assert result == {"type": "empty", "rows": [], "total": 0}


def test_registered_in_shapers():
    assert SHAPERS["bubble_change"] is shape_bubble_animated


def test_id_like_color_taken_via_first_and_marked_category():
    df = sample_df().assign(state_id=[1, 1, 1, 1, 2, 2])
    config = {"roles": {"category": "region", "measure": "revenue", "measure2": "cost",
                         "size": "units", "color": "state_id", "animation": "year"}}
    result = shape_bubble_animated(df, config)
    assert result["color_kind"] == "category"
    east_2023 = next(r for r in result["rows"] if r["name"] == "East" and r["frame"] == 2023)
    assert east_2023["color"] == 1


def test_measure_color_stays_a_ramp():
    config = {"roles": {"category": "region", "measure": "revenue", "measure2": "cost",
                         "size": "units", "color": "revenue", "animation": "year"}}
    result = shape_bubble_animated(sample_df(), config)
    assert result["color_kind"] == "measure"
    east_2023 = next(r for r in result["rows"] if r["name"] == "East" and r["frame"] == 2023)
    assert east_2023["color"] == 150  # 100 + 50, same aggregation as x


def test_duplicate_measure_roles_do_not_crash():
    """Regression guard: same house rule as shape_bubble's Task 3 fix and Phase 1's
    Task 6/15 fixes — a repeated column across x/y/size/color must not produce a
    pandas duplicate-column crash."""
    config = {"roles": {"category": "region", "measure": "revenue", "measure2": "revenue",
                         "size": "revenue", "animation": "year"}}
    result = shape_bubble_animated(sample_df(), config)
    east_2023 = next(r for r in result["rows"] if r["name"] == "East" and r["frame"] == 2023)
    assert east_2023["x"] == 150
    assert east_2023["y"] == 150
    assert east_2023["size"] == 150
