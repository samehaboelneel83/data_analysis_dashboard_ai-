"""Why did it change: which groups carry the difference between two periods
(docs/discovery/PLAN.md, phase 3 #14)."""
import numpy as np
import pandas as pd
import pytest

from app.services.analysis.change_drivers import ChangeError, explain_change


def rows(seed=3, last_day="2024-06-30"):
    """Six months. In June, group `b` of `kind` doubles; nothing else moves."""
    rng = np.random.default_rng(seed)
    out = []
    for d in pd.date_range("2024-01-01", last_day, freq="D"):
        for kind in ("a", "b", "c"):
            for place in ("x", "y"):
                amount = 100.0 + rng.normal(0, 1)
                if d.month == 6 and kind == "b":
                    amount *= 2
                out.append((d, kind, place, amount, len(out)))
    return pd.DataFrame(out, columns=["when", "kind", "place", "amount", "row_id"])


def test_it_finds_the_group_that_carries_the_change():
    got = explain_change(rows(), "when", "amount").to_dict()
    m = got["meta"]
    assert m["period"] == "2024-06" and m["baseline"] == "2024-05" and m["change"] > 0
    first = m["factors"][0]
    assert first["column"] == "kind" and first["top"] == "b" and first["concentration"] > 0.9
    top = first["values"][0]
    # Over 100%: June is a day shorter than May, so the other groups fell a little.
    assert top["value"] == "b" and 100 < top["share_of_change_pct"] < 115
    place = next(f for f in m["factors"] if f["column"] == "place")
    assert place["concentration"] < 0.6                                          # spread evenly: not where it sits


def test_the_period_the_data_stops_inside_is_not_the_one_explained():
    got = explain_change(rows(last_day="2024-07-04"), "when", "amount").to_dict()["meta"]
    assert got["period"] == "2024-06" and got["baseline"] == "2024-05"


def test_an_identifier_and_a_hidden_column_are_not_breakdowns():
    df = rows()
    got = explain_change(df, "when", "amount", column_meta={"place": {"hidden": True}}).to_dict()["meta"]
    assert [f["column"] for f in got["factors"]] == ["kind"]


def test_an_average_gets_each_values_own_change_and_no_share():
    got = explain_change(rows(), "when", "amount", aggregation="avg").to_dict()
    top = got["meta"]["factors"][0]["values"][0]
    assert got["meta"]["additive"] is False and "share_of_change_pct" not in top and "rows_share_pct" in top
    assert any("average does not split into parts" in w for w in got["warnings"])


def test_values_that_cancel_get_no_share_and_empty_is_named():
    """A column whose values swap rows between periods (a state that moves on)
    shows huge opposite parts of a small change: said as offsetting, no shares."""
    df = rows()
    df["state"] = np.where(df["when"].dt.month == 6, "open", "closed")
    df.loc[df.index[::7], "state"] = None
    got = explain_change(df, "when", "amount").to_dict()["meta"]
    state = next(f for f in got["factors"] if f["column"] == "state")
    assert state["offsetting"] and all("share_of_change_pct" not in v for v in state["values"])
    assert "(empty)" in {v["value"] for v in state["values"]} and "nan" not in {v["value"] for v in state["values"]}
    assert got["factors"][0]["column"] == "kind" and got["factors"][-1]["column"] == "state"


def test_named_periods_are_compared_as_named():
    got = explain_change(rows(), "when", "amount", period="2024-06", baseline="2024-01").to_dict()["meta"]
    assert got["baseline"] == "2024-01"
    with pytest.raises(ChangeError, match="no rows fall in"):
        explain_change(rows(), "when", "amount", period="2031-01", baseline="2024-01")


def test_it_always_says_it_is_not_a_cause():
    assert "not what caused it" in explain_change(rows(), "when", "amount").to_dict()["warnings"][0]


def test_it_runs_from_the_catalogue():
    from app.services.analysis import registry
    out = registry.run_analysis("explain_change", rows(), {"date_column": "when", "measure": "amount"}, column_meta={})
    body = out.to_dict() if hasattr(out, "to_dict") else out
    assert body["meta"]["factors"][0]["column"] == "kind"
