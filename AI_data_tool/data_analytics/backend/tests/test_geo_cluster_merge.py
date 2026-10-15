"""C-29 (round 2): a city whose jittered points straddle a grid-cell boundary
comes back as ONE cluster, not two concentric ones (QA MAP-02)."""
import pandas as pd

from app.services.widget_data import shape_geo_clusters


def _rows(*groups):
    lat, lon, v = [], [], []
    for (la, lo, n) in groups:
        lat += [la] * n
        lon += [lo] * n
        v += [1.0] * n
    return pd.DataFrame({"lat": lat, "lon": lon, "sales": v})


CFG = {"lat": "lat", "lon": "lon", "measure": "sales", "cluster_cell_degrees": 10}


def test_a_city_split_by_a_cell_edge_is_one_cluster():
    # Tokyo's points on both sides of the 35 deg edge of a 10 deg grid.
    df = _rows((34.8, 139.7, 3), (35.2, 139.7, 27), (51.5, -0.1, 12))
    r = shape_geo_clusters(df, CFG)
    counts = sorted(row["count"] for row in r["rows"])
    assert counts == [12, 30]
    tokyo = max(r["rows"], key=lambda row: row["count"])
    assert abs(tokyo["lat"] - (34.8 * 3 + 35.2 * 27) / 30) < 1e-6
    assert tokyo["value"] == 30.0


def test_neighbouring_cells_with_far_apart_points_stay_apart():
    # Two real places in adjacent cells, each well inside its own: not merged.
    df = _rows((31.0, 139.7, 5), (39.0, 139.7, 5))
    r = shape_geo_clusters(df, CFG)
    assert sorted(row["count"] for row in r["rows"]) == [5, 5]
