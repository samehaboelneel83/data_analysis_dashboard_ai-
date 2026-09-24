"""Rank selection: top/bottom N by aggregated value, independent of display sort."""
import pandas as pd

from app.services.widget_data import shape_series


def df():
    return pd.DataFrame({"d": list("abcdef"), "v": [10.0, 50.0, 30.0, 30.0, 5.0, 40.0]})


def base(**extra):
    return {"dimension": "d", "measure": "v", "aggregation": "sum", **extra}


def test_top_n_keeps_boundary_ties():
    # top 3 by value: b(50), f(40), then c and d tie at 30 -- both stay.
    r = shape_series(df(), base(rank={"mode": "top", "n": 3}))
    assert {x["name"] for x in r["rows"]} == {"b", "f", "c", "d"}


def test_bottom_n_is_independent_of_the_display_sort():
    # bottom 2 by VALUE (e=5, a=10), displayed alphabetically -- two different
    # orderings, which is exactly why rank cannot be the sort+limit pair.
    r = shape_series(df(), base(rank={"mode": "bottom", "n": 2}, sort_by="name", sort="asc"))
    assert [x["name"] for x in r["rows"]] == ["a", "e"]


def test_rank_composes_with_quick_calc_percent_of_total():
    # rank first selects the categories; percent-of-total then re-bases over the
    # SELECTED set (the visual's context).
    r = shape_series(df(), base(rank={"mode": "top", "n": 2}, quick_calc="percent_of_total"))
    vals = [x["value"] for x in r["rows"]]
    assert abs(sum(vals) - 100.0) < 0.1


def test_malformed_rank_is_ignored():
    assert len(shape_series(df(), base(rank={"mode": "top", "n": "many"}))["rows"]) == 6
    assert len(shape_series(df(), base(rank="top3"))["rows"]) == 6
