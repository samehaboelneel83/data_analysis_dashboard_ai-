"""Pie maps, multi-layer maps, and the density map's shared cluster shaper."""
import pandas as pd
import pytest

from app.services.widget_data import SHAPERS, shape_geo_layers, shape_geo_pies


def df():
    return pd.DataFrame({
        "country": ["Japan"] * 3 + ["Brazil"] * 2,
        "cat": ["A", "B", "A", "A", "B"],
        "rev": [5.0, 3.0, 2.0, 4.0, 1.0],
        "la": [35.6, 35.7, 35.5, -23.5, -23.6],
        "lo": [139.7, 139.8, 139.6, -46.6, -46.7],
    })


def test_pies_group_by_location_then_slice():
    r = shape_geo_pies(df(), {"dimension": "country", "dimension2": "cat", "measure": "rev"})
    japan = next(x for x in r["rows"] if x["name"] == "Japan")
    assert japan["total"] == 10.0
    assert {s["label"]: s["value"] for s in japan["slices"]} == {"A": 7.0, "B": 3.0}
    # ordered by total: Japan first
    assert [x["name"] for x in r["rows"]] == ["Japan", "Brazil"]


def test_pies_fold_small_slices_into_other():
    big = pd.DataFrame({"country": ["X"] * 9, "cat": list("abcdefghi"), "rev": [9.0 - i for i in range(9)]})
    r = shape_geo_pies(big, {"dimension": "country", "dimension2": "cat", "measure": "rev"})
    slices = r["rows"][0]["slices"]
    assert len(slices) == 7                      # top 6 + Other
    assert slices[-1]["label"] == "Other"
    assert sum(s["value"] for s in slices) == pytest.approx(sum(range(1, 10)))


def test_layers_carry_both_regions_and_points():
    r = shape_geo_layers(df(), {"roles": {"category": "country", "measure": "rev",
                                          "lat": "la", "lon": "lo"}})
    assert {x["name"]: x["value"] for x in r["regions"]} == {"Japan": 10.0, "Brazil": 5.0}
    assert len(r["points"]) == 5


def test_layers_degrade_to_one_layer_when_roles_are_partial():
    only_regions = shape_geo_layers(df(), {"roles": {"category": "country", "measure": "rev"}})
    assert only_regions["regions"] and not only_regions["points"]
    only_points = shape_geo_layers(df(), {"roles": {"lat": "la", "lon": "lo"}})
    assert only_points["points"] and not only_points["regions"]


def test_density_map_reuses_the_cluster_shaper():
    # Same aggregation, different renderer: one grid, two presentations.
    assert SHAPERS["map_density"] is SHAPERS["map_clusters"]
