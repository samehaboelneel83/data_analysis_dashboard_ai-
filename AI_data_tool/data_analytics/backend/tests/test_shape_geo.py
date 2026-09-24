"""The map widgets' data shapes.

Region-mode maps consume ordinary shape_series output on purpose -- every existing
filter/RLS/measure path applies with no geo-specific backend -- so what needs testing
here is the lat/lon mode and the fallback between the two.
"""
import pandas as pd

from app.services.widget_data import get_widget_data_from_df


def test_choropleth_is_series_shaped():
    df = pd.DataFrame({"country": ["US", "US", "CA"], "revenue": [10.0, 20.0, 5.0]})
    r = get_widget_data_from_df(df, {"dimension": "country", "measure": "revenue",
                                     "aggregation": "sum"}, "map_choropleth")
    assert {row["name"]: row["value"] for row in r["rows"]} == {"US": 30.0, "CA": 5.0}


def test_latlon_mode_passes_coordinates_through():
    df = pd.DataFrame({"site": ["A", "B"], "lat": [48.85, 40.71], "lon": [2.35, -74.0],
                       "sales": [100.0, 200.0]})
    r = get_widget_data_from_df(df, {"lat": "lat", "lon": "lon", "dimension": "site",
                                     "measure": "sales"}, "map_points")
    assert r["type"] == "geo_points"
    assert r["rows"][0] == {"lat": 48.85, "lon": 2.35, "name": "A", "value": 100.0}
    assert len(r["rows"]) == 2


def test_out_of_range_coordinates_are_dropped_and_counted():
    """A marker at (999, 999) is a lie and NaN is a crash; both must go, visibly."""
    df = pd.DataFrame({"lat": [48.85, 999.0, None], "lon": [2.35, 0.0, 10.0]})
    r = get_widget_data_from_df(df, {"lat": "lat", "lon": "lon"}, "map_points")
    assert len(r["rows"]) == 1
    assert r["dropped"] == 2


def test_without_latlon_roles_it_falls_back_to_the_series_shape():
    """The mode that works on data with no coordinate columns: country + measure only.
    The renderer plots these at country centroids."""
    df = pd.DataFrame({"country": ["US", "CA"], "revenue": [10.0, 5.0]})
    r = get_widget_data_from_df(df, {"dimension": "country", "measure": "revenue",
                                     "aggregation": "sum"}, "map_bubbles")
    assert r["type"] != "geo_points"
    assert {row["name"] for row in r["rows"]} == {"US", "CA"}


def test_latlon_mode_respects_filters():
    """The point path must go through _apply_filters like everything else -- a map that
    ignores the page's cross-filters would show different data from every other widget."""
    df = pd.DataFrame({"region": ["EU", "US"], "lat": [48.0, 40.0], "lon": [2.0, -74.0]})
    r = get_widget_data_from_df(
        df, {"lat": "lat", "lon": "lon",
             "filters": [{"column": "region", "op": "eq", "value": "EU"}]}, "map_points")
    assert len(r["rows"]) == 1
    assert r["rows"][0]["lat"] == 48.0
