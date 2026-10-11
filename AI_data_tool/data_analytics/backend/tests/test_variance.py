"""One number against another: where the difference sits, the bridge, and the
grid of the difference (docs/discovery/PLAN.md §N-3)."""
import numpy as np
import pandas as pd
import pytest

from app.services import widget_data as wd
from app.services.analysis.change_drivers import ChangeError, explain_variance
from app.services.discovery import engine, profile as store


def rows(seed=2, groups=("a", "b", "c", "d")):
    """`reached` runs 30% short of `expected` in group b, and matches elsewhere."""
    rng = np.random.default_rng(seed)
    out = []
    for d in pd.date_range("2024-01-01", "2024-12-31", freq="D"):
        for g in groups:
            expected = 100.0
            reached = expected * (0.7 if g == "b" else 1.0) + rng.normal(0, 0.5)
            out.append((d, g, "x" if d.day % 2 else "y", reached, expected, rng.normal(5, 1)))
    return pd.DataFrame(out, columns=["when", "kind", "place", "reached", "expected", "weight"])


def test_the_difference_is_found_in_the_group_that_carries_it():
    got = explain_variance(rows(), "reached", "expected").to_dict()
    m = got["meta"]
    assert m["mode"] == "measures" and m["change"] < 0 and -9 < m["change_pct"] < -6
    first = m["factors"][0]
    assert first["column"] == "kind" and first["top"] == "b" and first["concentration"] > 0.9
    assert -31 < first["values"][0]["delta_pct"] < -29 and first["values"][0]["share_of_change_pct"] > 95
    assert "not what caused it" in got["warnings"][0]


def test_rows_with_only_one_of_the_two_numbers_are_in_neither_total():
    df = rows()
    df.loc[df.index[:100], "expected"] = None
    got = explain_variance(df, "reached", "expected").to_dict()
    assert got["meta"]["rows_left_out"] == 100 and any("only one of the two" in w for w in got["warnings"])
    with pytest.raises(ChangeError, match="same column"):
        explain_variance(df, "reached", "reached")


def test_the_bridge_starts_at_one_total_and_arrives_at_the_other():
    df = rows()
    out = wd.get_widget_data_from_df(df, {"dimension": "kind", "measure": "reached", "aggregation": "sum",
                                          "bridge_from": "expected"}, "waterfall")
    bars = out["bars"]
    assert bars[0]["name"] == "expected" and bars[0]["total"] and bars[-1]["name"] == "reached" and bars[-1]["total"]
    assert bars[1]["name"] == "b" and bars[1]["delta"] < 0                    # the largest difference first
    assert abs(bars[-2]["end"] - bars[-1]["end"]) < 1e-6                       # it arrives
    assert abs(out["bridge"]["delta"] - (df["reached"].sum() - df["expected"].sum())) < 1e-6
    v = {r["name"]: r for r in out["variance"]}
    assert -31 < v["b"]["delta_pct"] < -29 and abs(v["a"]["delta_pct"]) < 1


def test_a_long_bridge_gathers_the_rest_and_still_arrives():
    df = rows(groups=tuple("abcdefghijkl"))
    out = wd.get_widget_data_from_df(df, {"dimension": "kind", "measure": "reached", "aggregation": "sum",
                                          "bridge_from": "expected"}, "waterfall")
    names = [b["name"] for b in out["bars"]]
    assert wd.BRIDGE_OTHER in names and len(names) == wd.BRIDGE_STEPS + 3
    assert abs(out["bars"][-2]["end"] - out["bars"][-1]["end"]) < 1e-6 and out["truncation"]["applied"]
    assert len(out["variance"]) == 12                                           # the table keeps every group


def test_a_bridge_of_averages_is_refused_in_plain_words():
    out = wd.get_widget_data_from_df(rows(), {"dimension": "kind", "measure": "reached", "aggregation": "avg",
                                              "bridge_from": "expected"}, "waterfall")
    assert out["type"] == "error" and "do not add up" in out["message"]


def test_a_waterfall_without_the_setting_is_as_before():
    out = wd.get_widget_data_from_df(rows(), {"dimension": "kind", "measure": "reached", "aggregation": "sum"}, "waterfall")
    assert "bridge" not in out and all("total" not in b for b in out["bars"])


def test_the_grid_of_the_difference_is_signed_and_marked_diverging():
    out = wd.get_widget_data_from_df(rows(), {
        "dimension": "kind", "dimension2": "when", "dimension2_granularity": "month",
        "measure": "reached", "aggregation": "sum", "difference_of": "expected"}, "heatmap")
    assert out["type"] == "heatmap" and out["diverging"] is True and len(out["cols_axis"]) == 12
    b = out["cells"][out["rows_axis"].index("b")]
    a = out["cells"][out["rows_axis"].index("a")]
    assert all(v < -800 for v in b) and all(abs(v) < 20 for v in a)


META = {"reached": {"number": "amount", "unit": "kg"}, "expected": {"number": "amount", "unit": "kg"},
        "weight": {"number": "amount", "unit": "kg"}}


def test_two_numbers_of_one_unit_and_one_size_are_offered_against_each_other():
    prof = store.compute(rows())
    kinds = engine.column_kinds(prof, META)
    assert engine.comparable_pairs(prof, kinds, META) == [("reached", "expected")]      # weight: same unit, another size
    cards = [c for c in engine.tier0(prof, META)["cards"] if "expected" in c["fields"] and "reached" in c["fields"]]
    kinds_offered = {c["action"].get("analysis") or c["action"].get("widget_type") for c in cards}
    assert kinds_offered == {"explain_variance", "waterfall", "heatmap"}
    assert all(any("yardstick" in l for l in c["limits"]) for c in cards)
    for c in cards:
        if c["action"]["kind"] == "add_widget":
            out = wd.get_widget_data_from_df(rows(), c["action"]["config"], c["action"]["widget_type"])
            assert out.get("type") in ("waterfall", "heatmap"), out.get("message")


def test_numbers_without_a_recorded_unit_are_not_paired():
    prof = store.compute(rows())
    assert engine.comparable_pairs(prof, engine.column_kinds(prof, {}), {}) == []


def test_rows_with_no_category_are_still_in_the_bridge():
    df = rows()
    df.loc[df.index[::9], "kind"] = None
    out = wd.get_widget_data_from_df(df, {"dimension": "kind", "measure": "reached", "aggregation": "sum",
                                          "bridge_from": "expected"}, "waterfall")
    assert "(empty)" in [b["name"] for b in out["bars"]]
    assert abs(out["bridge"]["actual"] - df["reached"].sum()) < 1e-6


def test_a_number_three_times_the_other_is_not_its_yardstick():
    df = rows()
    df["expected"] = df["expected"] * 3
    prof = store.compute(df)
    assert engine.comparable_pairs(prof, engine.column_kinds(prof, META), META) == []
