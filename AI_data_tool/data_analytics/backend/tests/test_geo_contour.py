"""Geo contour (MASTER_PLAN Phase 4 item 5): a density surface from points."""
import numpy as np
import pandas as pd

from app.services.widget_data import CONTOUR_NX, CONTOUR_NY, get_widget_data_from_df


def frame(n=500, seed=1):
    rng = np.random.default_rng(seed)
    # Two clusters: Cairo (dense) and Alexandria (sparse).
    cairo = rng.normal([30.04, 31.24], 0.1, size=(int(n * 0.8), 2))
    alex = rng.normal([31.2, 29.92], 0.1, size=(n - len(cairo), 2))
    pts = np.vstack([cairo, alex])
    return pd.DataFrame({"lat": pts[:, 0], "lon": pts[:, 1], "sales": rng.uniform(1, 10, n)})


def contour(df, **cfg):
    return get_widget_data_from_df(df, {"lat": "lat", "lon": "lon", **cfg}, "map_contour")


def test_the_surface_peaks_where_the_points_are():
    out = contour(frame())
    g = out["grid"]
    assert len(g["values"]) == CONTOUR_NX * CONTOUR_NY and max(g["values"]) == 1.0
    z = np.array(g["values"]).reshape(g["ny"], g["nx"])
    iy, ix = np.unravel_index(z.argmax(), z.shape)
    lat = g["south"] + iy * (g["north"] - g["south"]) / (g["ny"] - 1)
    lon = g["west"] + ix * (g["east"] - g["west"]) / (g["nx"] - 1)
    assert abs(lat - 30.04) < 0.3 and abs(lon - 31.24) < 0.3  # Cairo, not Alexandria
    assert out["levels"] and out["points_used"] == 500


def test_bad_coordinates_are_counted_not_hidden():
    df = frame(100)
    df.loc[:9, "lat"] = 999
    out = contour(df)
    assert out["points_used"] == 90 and out["dropped"] == 10


def test_too_few_points_is_a_reason_not_a_blank():
    out = contour(frame(100).head(2))
    assert out["grid"] is None and "at least 3" in out["reason"]


def test_a_weight_measure_is_used_and_named():
    out = contour(frame(), measure="sales")
    assert out["weighted_by"] == "sales" and out["grid"] is not None


def test_filters_narrow_the_surface():
    df = frame()
    df["city"] = np.where(df["lon"] < 30.5, "Alex", "Cairo")
    out = contour(df, filters=[{"column": "city", "op": "eq", "value": "Alex"}])
    assert out["points_used"] == 100
