import pandas as pd
from app.services.widget_data import get_widget_data_from_df


def test_area_widget_type_uses_the_same_shaper_as_bar():
    df = pd.DataFrame({"region": ["North", "South", "North"], "sales": [10, 20, 5]})
    config = {"roles": {"category": "region", "measure": "sales"}, "aggregation": "sum"}
    bar_result = get_widget_data_from_df(df, config, "bar")
    area_result = get_widget_data_from_df(df, config, "area")
    assert area_result == bar_result


def test_funnel_widget_type_uses_the_same_shaper_as_bar():
    df = pd.DataFrame({"stage": ["Visit", "Signup", "Purchase"], "count": [100, 40, 10]})
    config = {"roles": {"category": "stage", "measure": "count"}, "aggregation": "sum"}
    bar_result = get_widget_data_from_df(df, config, "bar")
    funnel_result = get_widget_data_from_df(df, config, "funnel")
    assert funnel_result == bar_result


def test_ribbon_widget_type_uses_the_same_shaper_as_heatmap():
    df = pd.DataFrame({"month": ["Jan", "Jan", "Feb"], "product": ["A", "B", "A"], "sales": [10, 20, 15]})
    config = {"roles": {"category": "month", "category2": "product", "measure": "sales"}, "aggregation": "sum"}
    heatmap_result = get_widget_data_from_df(df, config, "heatmap")
    ribbon_result = get_widget_data_from_df(df, config, "ribbon")
    assert ribbon_result == heatmap_result
