import pandas as pd
from app.services.widget_data import shape_dual_series, SHAPERS


def sample_df():
    return pd.DataFrame({
        "month": ["Jan", "Jan", "Feb", "Feb", "Mar"],
        "revenue": [100, 50, 200, 100, 300],
        "cost": [60, 20, 90, 40, 120],
    })


def test_both_measures_grouped_by_category():
    config = {"roles": {"category": "month", "measure": "revenue", "measure2": "cost"}}
    result = shape_dual_series(sample_df(), config)
    assert result["type"] == "dual_series"
    assert result["category"] == "month"
    by_name = {r["name"]: r for r in result["rows"]}
    assert by_name["Jan"]["value"] == 150
    assert by_name["Jan"]["value2"] == 80
    assert by_name["Feb"]["value"] == 300
    assert result["total"] == 5


def test_start_role_used_as_grouping_column_like_category():
    config = {"roles": {"start": "month", "measure": "revenue"}}
    result = shape_dual_series(sample_df(), config)
    assert result["category"] == "month"
    assert all("value" in r and "value2" not in r for r in result["rows"])


def test_only_measure2_no_measure():
    config = {"roles": {"category": "month", "measure2": "cost"}}
    result = shape_dual_series(sample_df(), config)
    assert all("value2" in r and "value" not in r for r in result["rows"])


def test_missing_category_returns_empty():
    config = {"roles": {"measure": "revenue"}}
    result = shape_dual_series(sample_df(), config)
    assert result == {"type": "empty", "rows": [], "total": 0}


def test_missing_both_measures_returns_empty():
    config = {"roles": {"category": "month"}}
    result = shape_dual_series(sample_df(), config)
    assert result == {"type": "empty", "rows": [], "total": 0}


def test_respects_aggregation_config():
    config = {"roles": {"category": "month", "measure": "revenue"}, "aggregation": "avg"}
    result = shape_dual_series(sample_df(), config)
    by_name = {r["name"]: r for r in result["rows"]}
    assert by_name["Jan"]["value"] == 75.0


def test_measure_equal_to_measure2_produces_valid_scalars_not_a_crash():
    config = {"roles": {"category": "month", "measure": "revenue", "measure2": "revenue"}}
    result = shape_dual_series(sample_df(), config)
    by_name = {r["name"]: r for r in result["rows"]}
    assert by_name["Jan"]["value"] == 150
    assert by_name["Jan"]["value2"] == 150
    assert isinstance(by_name["Jan"]["value"], (int, float))
    assert isinstance(by_name["Jan"]["value2"], (int, float))


def test_all_five_widget_types_registered_to_same_shaper():
    for wt in ["dual_axis_bar", "dual_axis_line", "dual_axis_bar_line", "dual_axis_time_series", "comparative_time_series"]:
        assert SHAPERS[wt] is shape_dual_series


def test_works_with_legacy_config_keys_not_just_roles_dict():
    """Regression test: the real frontend sends legacy keys (dimension/measure/measure2/start),
    never a 'roles' object — this must work identically to the roles-dict form."""
    config = {"dimension": "month", "measure": "revenue", "measure2": "cost"}
    result = shape_dual_series(sample_df(), config)
    by_name = {r["name"]: r for r in result["rows"]}
    assert by_name["Jan"]["value"] == 150
    assert by_name["Jan"]["value2"] == 80


def test_works_with_legacy_start_key_not_just_roles_dict():
    config = {"start": "month", "measure": "revenue"}
    result = shape_dual_series(sample_df(), config)
    assert result["category"] == "month"
    assert all("value" in r for r in result["rows"])


def test_dual_series_honours_dimension_granularity():
    """The config panel offers dimension_granularity for the dual-axis and comparative
    time-series types, and shape_series honours it -- this shaper ignored it, so an
    author asking to group by month silently got one point per raw row. Over a real
    dataset that is thousands of points on an axis meant to show twelve.

    Asserts the GROUPED result, not merely that rows came back: the unfixed shaper also
    returns rows, just the wrong ones, so a length or truthiness check passes either
    way."""
    import pandas as pd
    from app.services.widget_data import get_widget_data_from_df

    df = pd.DataFrame({
        "date": pd.to_datetime(["2024-01-05", "2024-01-20", "2024-02-11", "2024-02-26"]),
        "revenue": [10.0, 20.0, 30.0, 40.0],
        "units": [1, 2, 3, 4],
    })
    config = {"dimension": "date", "dimension_granularity": "month",
              "measure": "revenue", "measure2": "units", "aggregation": "sum"}

    for wt in ("dual_axis_line", "dual_axis_bar", "comparative_time_series"):
        result = get_widget_data_from_df(df.copy(), dict(config), wt)
        names = [r["name"] for r in result["rows"]]
        assert names == ["2024-01", "2024-02"], f"{wt}: {names}"
        # The two January rows must have been summed, not merely relabelled.
        assert result["rows"][0]["value"] == 30.0, wt


def test_dual_series_without_granularity_is_unchanged():
    """The fix must not group when nothing asked it to -- an omitted granularity still
    means one point per distinct dimension value."""
    import pandas as pd
    from app.services.widget_data import get_widget_data_from_df

    df = pd.DataFrame({
        "date": pd.to_datetime(["2024-01-05", "2024-01-20"]),
        "revenue": [10.0, 20.0], "units": [1, 2],
    })
    result = get_widget_data_from_df(
        df, {"dimension": "date", "measure": "revenue", "measure2": "units"}, "dual_axis_line")

    assert len(result["rows"]) == 2
