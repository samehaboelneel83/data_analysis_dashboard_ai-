"""The map layer stack (MASTER_PLAN Phase 4 item 3): several layers, in order,
each with its own roles -- and a layer that cannot be drawn is NAMED."""
import pandas as pd

from app.services.widget_data import get_widget_data_from_df

DF = pd.DataFrame({
    "country": ["Egypt", "Egypt", "France", "Chile"],
    "sales": [10, 20, 5, 7],
    "lat": [30.0, 31.2, 48.8, 999.0], "lon": [31.2, 29.9, 2.3, -70.6],
    "lat2": [48.8, 48.8, 30.0, 30.0], "lon2": [2.3, 2.3, 31.2, 31.2],
})


def layers(*stack, **cfg):
    return get_widget_data_from_df(DF, {"layers": list(stack), **cfg}, "map_layers")


def test_layers_come_back_in_order_with_their_own_data():
    out = layers({"id": "a", "kind": "regions", "category": "country", "measure": "sales"},
                 {"id": "b", "kind": "points", "lat": "lat", "lon": "lon", "measure": "sales"},
                 {"id": "c", "kind": "lines", "lat": "lat", "lon": "lon", "lat2": "lat2", "lon2": "lon2"})
    assert [l["id"] for l in out["layers"]] == ["a", "b", "c"]
    regions = {r["name"]: r["value"] for r in out["layers"][0]["regions"]}
    assert regions == {"Egypt": 30, "France": 5, "Chile": 7}
    assert len(out["layers"][1]["points"]) == 3 and out["layers"][1]["dropped"] == 1
    assert len(out["layers"][2]["lines"]) == 3


def test_a_layer_that_cannot_be_drawn_is_named_not_dropped():
    out = layers({"id": "ok", "kind": "bubbles", "category": "country"},
                 {"id": "no-coords", "kind": "points", "title": "Stores", "lat": "lat"},
                 {"id": "gone", "kind": "regions", "category": "governorate"},
                 {"id": "odd", "kind": "hexbins"})
    errs = {l["id"]: l.get("error") for l in out["layers"]}
    assert errs["ok"] is None
    assert errs["no-coords"] == "needs Longitude"
    assert "'governorate'" in errs["gone"]
    assert "unknown layer type" in errs["odd"]


def test_the_stack_is_capped_and_says_so():
    out = layers(*[{"id": str(i), "kind": "bubbles", "category": "country"} for i in range(8)])
    assert len(out["layers"]) == 7
    assert "at most 6" in out["layers"][-1]["error"]


def test_a_capped_point_layer_discloses_its_truncation():
    out = layers({"id": "p", "kind": "points", "lat": "lat", "lon": "lon", "limit": 2})
    t = out["layers"][0]["truncation"]
    assert t["applied"] and t["shown"] == 2 and t["of"] == 3


def test_filters_narrow_every_layer():
    out = layers({"id": "a", "kind": "regions", "category": "country"},
                 filters=[{"column": "country", "op": "eq", "value": "Egypt"}])
    assert out["layers"][0]["regions"] == [{"name": "Egypt", "value": 2}]


def test_without_a_stack_the_two_layer_widget_is_unchanged():
    out = get_widget_data_from_df(DF, {"dimension": "country", "lat": "lat", "lon": "lon"}, "map_layers")
    assert "layers" not in out and out["regions"] and out["points"]
