"""Geographic network shaper and the automated-explanation service."""
import pandas as pd
import pytest

from app.services.explain import explain_response
from app.services.widget_data import shape_geo_network


def routes():
    return pd.DataFrame({
        "f": ["NY", "NY", "LN"], "t": ["LN", "TK", "TK"],
        "sla": [40.7, 40.8, 51.5], "slo": [-74.0, -74.1, -0.1],
        "tla": [51.5, 35.6, 35.6], "tlo": [-0.1, 139.7, 139.7],
        "v": [3.0, 1.0, 2.0],
    })


def _cfg():
    return {"roles": {"category": "f", "category2": "t", "lat": "sla", "lon": "slo",
                      "lat2": "tla", "lon2": "tlo", "measure": "v"}}


def test_geo_network_anchors_nodes_at_mean_observed_coords():
    r = shape_geo_network(routes(), _cfg())
    ny = next(n for n in r["nodes"] if n["id"] == "NY")
    assert ny["lat"] == pytest.approx(40.75)      # mean of the two jittered origins
    assert ny["degree"] == 2
    assert {(l["source"], l["target"]): l["value"] for l in r["links"]}[("NY", "LN")] == 3.0


def test_geo_network_drops_bad_coords_and_self_loops():
    df = routes()
    df.loc[1, "sla"] = 999.0
    df.loc[2, "t"] = "LN"          # LN -> LN self loop
    r = shape_geo_network(df, _cfg())
    assert r["dropped"] == 1
    assert all(l["source"] != l["target"] for l in r["links"])


def test_explain_ranks_numeric_and_categorical_on_one_scale():
    df = pd.DataFrame({
        "y": [1.0, 2.0, 3.0, 4.0, 10.0, 11.0, 12.0, 13.0],
        "x_strong": [1.0, 2.0, 3.0, 4.0, 10.0, 11.0, 12.0, 13.0],   # r = 1
        "x_weak": [5.0, 1.0, 4.0, 2.0, 3.0, 5.0, 1.0, 4.0],
        "seg": ["a", "a", "a", "a", "b", "b", "b", "b"],             # splits low/high
    })
    r = explain_response(df, "y")
    assert r["factors"][0]["column"] == "x_strong"
    assert r["factors"][0]["relative"] == 1.0                        # SAS scale: top = 1
    cols = [f["column"] for f in r["factors"]]
    assert "seg" in cols                                             # categorical ranked too
    seg = next(f for f in r["factors"] if f["column"] == "seg")
    weak = next(f for f in r["factors"] if f["column"] == "x_weak")
    assert seg["score"] > weak["score"]
    # top factor numeric -> scatter relationship
    assert r["relationship"]["kind"] == "scatter"
    assert len(r["relationship"]["points"]) == 8


def test_explain_categorical_top_factor_gives_group_means():
    df = pd.DataFrame({"y": [1.0, 1.1, 9.0, 9.1] * 5,
                       "dept": ["low", "low", "high", "high"] * 5})
    r = explain_response(df, "y")
    assert r["factors"][0]["column"] == "dept"
    rel = r["relationship"]
    assert rel["kind"] == "group_means"
    means = {g["name"]: g["mean"] for g in rel["groups"]}
    assert means["high"] > means["low"]


def test_explain_refuses_a_constant_response():
    df = pd.DataFrame({"y": [1.0] * 5, "x": [1, 2, 3, 4, 5]})
    r = explain_response(df, "y")
    assert r["factors"] == [] and "distinct" in r["note"]


def test_explain_skips_id_like_categories():
    df = pd.DataFrame({"y": [float(i) for i in range(40)],
                       "row_id": [f"id{i}" for i in range(40)]})
    r = explain_response(df, "y")
    assert all(f["column"] != "row_id" for f in r["factors"])
