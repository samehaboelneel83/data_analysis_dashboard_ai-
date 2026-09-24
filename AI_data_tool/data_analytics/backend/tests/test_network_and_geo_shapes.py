"""Network/link analysis with centralities, origin-destination lines, and grid
cluster maps."""
import numpy as np
import pandas as pd
import pytest

from app.services.widget_data import shape_geo_clusters, shape_geo_lines, shape_network


def net():
    # a -- b, a -- c, b -- c, c -- d, c -- e: c is the cut vertex to d and e.
    return pd.DataFrame({"s": ["a", "a", "b", "c", "c"],
                         "t": ["b", "c", "c", "d", "e"],
                         "w": [1.0, 2.0, 1.0, 3.0, 1.0]})


def test_network_nodes_links_and_centralities():
    r = shape_network(net(), {"dimension": "s", "dimension2": "t", "measure": "w"})
    by = {n["id"]: n for n in r["nodes"]}
    # c touches every other node: degree 4/4; the only path to d and e runs
    # through it, so its betweenness dominates.
    assert by["c"]["degree"] == 1.0
    assert by["c"]["betweenness"] > by["a"]["betweenness"]
    assert by["c"]["reach"] == 1.0
    assert {(l["source"], l["target"]): l["value"] for l in r["links"]}[("a", "c")] == 2.0


def test_network_layout_is_deterministic():
    a = shape_network(net(), {"dimension": "s", "dimension2": "t"})
    b = shape_network(net(), {"dimension": "s", "dimension2": "t"})
    assert [(n["x"], n["y"]) for n in a["nodes"]] == [(n["x"], n["y"]) for n in b["nodes"]]


def test_network_self_loops_dropped_and_node_cap_by_degree():
    df = pd.DataFrame({"s": ["a", "a", "b"], "t": ["a", "b", "c"]})
    r = shape_network(df, {"dimension": "s", "dimension2": "t"})
    assert all(l["source"] != l["target"] for l in r["links"])
    big = pd.DataFrame({"s": [f"n{i}" for i in range(50)], "t": ["hub"] * 50})
    r = shape_network(big, {"dimension": "s", "dimension2": "t", "limit": 10})
    assert len(r["nodes"]) <= 11  # hub + top spokes


def test_geo_lines_drop_invalid_endpoints():
    df = pd.DataFrame({"olat": [40.7, 999.0], "olon": [-74.0, 0.0],
                       "dlat": [35.6, 10.0], "dlon": [139.7, 10.0]})
    r = shape_geo_lines(df, {"roles": {"lat": "olat", "lon": "olon", "lat2": "dlat", "lon2": "dlon"}})
    assert len(r["rows"]) == 1 and r["dropped"] == 1
    assert r["rows"][0]["lat2"] == 35.6


def test_clusters_merge_nearby_points_and_keep_far_ones_apart():
    pts = pd.DataFrame({"la": np.repeat([40.0, 41.0, -33.0], 50),
                        "lo": np.repeat([-74.0, -73.0, 151.0], 50)})
    r = shape_geo_clusters(pts, {"roles": {"lat": "la", "lon": "lo"}, "cluster_cell_degrees": 5})
    counts = sorted(x["count"] for x in r["rows"])
    assert counts == [50, 100]   # the two NYC-ish cells merged; Sydney alone
    assert r["cell_degrees"] == 5


def test_cluster_measure_sums_within_cells():
    pts = pd.DataFrame({"la": [40.0, 40.1], "lo": [-74.0, -74.1], "v": [3.0, 4.0]})
    r = shape_geo_clusters(pts, {"roles": {"lat": "la", "lon": "lo", "measure": "v"}})
    assert r["rows"][0]["value"] == pytest.approx(7.0)
