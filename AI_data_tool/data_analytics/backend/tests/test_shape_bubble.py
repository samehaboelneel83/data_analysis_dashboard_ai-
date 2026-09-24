import pandas as pd
from app.services.widget_data import shape_bubble, SHAPERS


def sample_df():
    return pd.DataFrame({
        "region": ["East", "East", "West", "West", "North"],
        "product_line": ["Toy", "Novelty", "Toy", "Toy", "Novelty"],
        "revenue": [100, 50, 200, 100, 300],
        "cost":    [60, 20, 90, 40, 120],
        "units":   [10, 5, 20, 10, 30],
    })


def id_like_df():
    """A dataset with an id-like numeric column, the "colors that act as id"
    bug report: state_id is numeric but means identity, not quantity."""
    return pd.DataFrame({
        "region":   ["East", "East", "West", "West", "North"],
        "state_id": [1, 1, 2, 2, 3],
        "revenue":  [100, 50, 200, 100, 300],
        "cost":     [60, 20, 90, 40, 120],
        "units":    [10, 5, 20, 10, 30],
    })


def test_aggregates_one_bubble_per_category():
    config = {"roles": {"category": "region", "measure": "revenue", "measure2": "cost", "size": "units"}}
    result = shape_bubble(sample_df(), config)
    assert result["type"] == "bubble_series"
    by_name = {r["name"]: r for r in result["rows"]}
    assert by_name["East"]["x"] == 150
    assert by_name["East"]["y"] == 80
    assert by_name["East"]["size"] == 15
    assert by_name["West"]["x"] == 300


def test_color_role_aggregated_like_other_measures():
    config = {"roles": {"category": "region", "measure": "revenue", "measure2": "cost", "size": "units", "color": "revenue"}}
    result = shape_bubble(sample_df(), config)
    by_name = {r["name"]: r for r in result["rows"]}
    assert by_name["East"]["color"] == 150
    # A genuine numeric measure keeps the continuous-ramp contract.
    assert result["color_kind"] == "measure"


def test_id_like_color_taken_via_first_not_summed():
    """The bug report: "the colors that act as id — it is not measure, it is
    category." state_id is numeric, but SUM-ing it (100) is meaningless -- East's
    two rows both carry state_id=1, so the right answer is 1, not 2."""
    config = {"roles": {"category": "region", "measure": "revenue", "measure2": "cost",
                         "size": "units", "color": "state_id"}}
    result = shape_bubble(id_like_df(), config)
    by_name = {r["name"]: r for r in result["rows"]}
    assert by_name["East"]["color"] == 1
    assert by_name["West"]["color"] == 2
    assert result["color_kind"] == "category"


def test_non_numeric_color_included_as_category():
    """Old behavior: a text color role concatenated under "sum" (or raised under any
    aggregation pandas can't apply to strings, e.g. "avg"). Either way it wasn't a
    deliberate category contract. Now it's taken via first() and marked as such,
    which also makes it work under every aggregation, not just "sum"."""
    config = {"roles": {"category": "region", "measure": "revenue", "measure2": "cost",
                         "size": "units", "color": "product_line"},
              "aggregation": "avg"}
    result = shape_bubble(sample_df(), config)
    by_name = {r["name"]: r for r in result["rows"]}
    assert by_name["East"]["color"] == "Toy"  # first row for East
    assert result["color_kind"] == "category"


def test_group_role_taken_via_first_not_aggregated():
    config = {"roles": {"category": "region", "measure": "revenue", "measure2": "cost", "size": "units", "group": "product_line"}}
    result = shape_bubble(sample_df(), config)
    by_name = {r["name"]: r for r in result["rows"]}
    assert by_name["East"]["group"] == "Toy"  # first row for East is Toy
    assert by_name["West"]["group"] == "Toy"
    assert by_name["North"]["group"] == "Novelty"


def test_missing_required_role_returns_empty():
    config = {"roles": {"category": "region", "measure": "revenue", "measure2": "cost"}}  # no size
    result = shape_bubble(sample_df(), config)
    assert result == {"type": "empty", "rows": [], "total": 0}


def test_duplicate_measure_roles_do_not_crash():
    """Regression guard: same house rule as Phase 1's Task 6/15 fixes — a repeated column
    across x/y/size/color must not produce a pandas duplicate-column crash."""
    config = {"roles": {"category": "region", "measure": "revenue", "measure2": "revenue", "size": "revenue"}}
    result = shape_bubble(sample_df(), config)
    by_name = {r["name"]: r for r in result["rows"]}
    assert by_name["East"]["x"] == 150
    assert by_name["East"]["y"] == 150
    assert by_name["East"]["size"] == 150


def test_color_same_as_category_returns_empty():
    """Regression guard: color colliding with the category (dimension) role used as the
    groupby key makes reset_index() try to insert a column that already exists
    (ValueError: cannot insert region, already exists)."""
    config = {"roles": {"category": "region", "measure": "revenue", "measure2": "cost", "size": "units", "color": "region"}}
    result = shape_bubble(sample_df(), config)
    assert result == {"type": "empty", "rows": [], "total": 0}


def test_group_same_as_category_returns_empty():
    """Regression guard: group colliding with the category (dimension) role used as the
    merge key makes the group merge try to insert a column that already exists
    (ValueError: cannot insert region, already exists)."""
    config = {"roles": {"category": "region", "measure": "revenue", "measure2": "cost", "size": "units", "group": "region"}}
    result = shape_bubble(sample_df(), config)
    assert result == {"type": "empty", "rows": [], "total": 0}


def test_registered_in_shapers():
    assert SHAPERS["bubble"] is shape_bubble


def test_fit_line_included_when_requested():
    config = {"roles": {"category": "region", "measure": "revenue", "measure2": "cost", "size": "units"}, "fit_line": "linear"}
    result = shape_bubble(sample_df(), config)
    assert "fit_line" in result
    assert len(result["fit_line"]) == 20


def test_fit_line_omitted_when_not_requested():
    config = {"roles": {"category": "region", "measure": "revenue", "measure2": "cost", "size": "units"}}
    result = shape_bubble(sample_df(), config)
    assert "fit_line" not in result
