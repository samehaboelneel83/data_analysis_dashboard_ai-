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
    assert r["rows"][0] == {"lat": 48.85, "lon": 2.35, "name": "A", "value": 100.0, "count": 1}
    assert len(r["rows"]) == 2


def test_one_marker_per_location_with_its_rows_counted():
    """Live QA 2026-09-28: 2,464 located call records drew their first 1,000
    rows -- 41 of 88 sites -- and said nothing. A marker is a place."""
    df = pd.DataFrame({"lat": [30.04, 30.04, 30.04, 31.09, 29.96],
                       "lon": [31.40, 31.40, 31.40, 29.72, 31.25],
                       "svc": ["voice", "data", "voice", "voice", "data"],
                       "amt": [1.0, 2.0, 3.0, 10.0, 5.0]})
    r = get_widget_data_from_df(df, {"lat": "lat", "lon": "lon", "dimension": "svc"}, "map_points")
    assert [(x["lat"], x["count"], x["value"], x["name"]) for x in r["rows"]] == [
        (30.04, 3, 3, "voice"), (31.09, 1, 1, "voice"), (29.96, 1, 1, "data")]
    assert r["locations"] == 3 and r["rows_mapped"] == 5 and "truncation" not in r
    r = get_widget_data_from_df(df, {"lat": "lat", "lon": "lon", "measure": "amt", "aggregation": "avg"}, "map_points")
    assert [x["value"] for x in r["rows"]] == [2.0, 10.0, 5.0]


def test_a_location_cap_keeps_the_largest_and_says_so():
    df = pd.DataFrame({"lat": [1.0, 2.0, 2.0, 3.0, 3.0, 3.0], "lon": [1.0, 2.0, 2.0, 3.0, 3.0, 3.0]})
    r = get_widget_data_from_df(df, {"lat": "lat", "lon": "lon", "limit": 2}, "map_points")
    assert sorted(x["count"] for x in r["rows"]) == [2, 3]
    assert r["truncation"] == {"applied": True, "shown": 2, "of": 3, "limit": 2, "reason": "limit", "unit": "locations"}


def test_clusters_size_their_cells_from_the_data():
    """A fixed 5-degree grid put every site between Cairo and Alexandria in one cluster."""
    df = pd.DataFrame({"lat": [30.04, 30.05, 31.09, 31.08, 29.96], "lon": [31.40, 31.41, 29.72, 29.73, 31.25]})
    r = get_widget_data_from_df(df, {"lat": "lat", "lon": "lon"}, "map_clusters")
    assert r["cell_degrees"] < 0.5 and len(r["rows"]) == 3
    r = get_widget_data_from_df(df, {"lat": "lat", "lon": "lon", "cluster_cell_degrees": 5}, "map_clusters")
    assert r["cell_degrees"] == 5 and len(r["rows"]) == 1


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


class TestAnimatedMaps:
    """Requested 2026-09-28: a map with a slider through a date or time series."""

    df = pd.DataFrame({"d": pd.to_datetime(["2026-03-01", "2026-03-02", "2026-04-01", "2026-05-09"]),
                       "lat": [30.0, 30.1, 31.0, 29.9], "lon": [31.3, 31.4, 29.7, 31.2],
                       "amt": [1.0, 2.0, 5.0, 3.0]})

    def test_one_frame_per_period_on_one_extent_and_one_scale(self):
        r = get_widget_data_from_df(self.df, {"lat": "lat", "lon": "lon", "measure": "amt", "aggregation": "sum",
                                              "animate_by": "d", "animate_granularity": "month"}, "map_bubbles")
        assert r["type"] == "animated" and r["inner"] == "map_bubbles"
        assert [f["label"] for f in r["frames"]] == ["2026-03", "2026-04", "2026-05"]
        assert [len(f["result"]["rows"]) for f in r["frames"]] == [2, 1, 1]
        assert r["fit_extent"] == [[29.7, 29.9], [31.4, 31.0]]
        assert r["domain"] == [0.0, 5.0]                     # the marker values, not a longitude

    def test_a_choropleth_frames_on_every_period_s_regions(self):
        df = pd.DataFrame({"d": pd.to_datetime(["2026-03-01", "2026-04-01"]), "c": ["Egypt", "France"], "v": [1, 2]})
        r = get_widget_data_from_df(df, {"dimension": "c", "measure": "v", "aggregation": "sum",
                                         "animate_by": "d", "animate_granularity": "month"}, "map_choropleth")
        assert r["fit_names"] == ["Egypt", "France"] and r["domain"] == [0.0, 2.0]
