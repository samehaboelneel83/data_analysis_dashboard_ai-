"""A page's key takeaways, said without a model (docs/discovery/PLAN.md, phase 2 #16)."""
import numpy as np
import pandas as pd

from app.services.discovery.takeaways import MAX_LINES, summarise
from app.services.widget_data import get_widget_data_from_df


def data(seed=2):
    rng = np.random.default_rng(seed)
    days = pd.date_range("2024-01-01", "2024-08-31", freq="D")
    rows = [(d, g, 100.0 * (3 if g == "a" else 1) + rng.normal(0, 3)) for d in days for g in ("a", "b", "c")]
    return pd.DataFrame(rows, columns=["when", "g", "amount"])


def item(df, wid, title, wt, cfg):
    return {"widget_id": wid, "title": title, "widget_type": wt, "config": cfg,
            "result": get_widget_data_from_df(df, cfg, wt)}


def test_each_sentence_is_its_charts_own_numbers_in_reading_order():
    df = data()
    got = summarise([
        item(df, 1, "By group", "bar", {"dimension": "g", "measure": "amount", "aggregation": "sum"}),
        item(df, 2, "Over time", "line", {"dimension": "when", "dimension_granularity": "month", "measure": "amount",
                                          "aggregation": "sum"}),
        item(df, 3, "Total", "kpi", {"measure": "amount", "aggregation": "sum", "sparkline_date": "when"}),
    ])
    assert [t["widget_id"] for t in got["takeaways"]] == [3, 2, 1]             # headline, then time, then groups
    assert [t["section"] for t in got["takeaways"]] == ["headline", "over_time", "comparison"]
    by_group = got["takeaways"][2]["sentence"]
    assert "A leads with" in by_group and f"{df[df.g == 'a'].amount.sum():,.0f}" in by_group
    assert got["source"] == "deterministic" and got["nothing_to_say"] == 0


def test_a_headline_with_history_says_how_the_last_period_compares():
    df = data()
    df.loc[df["when"].dt.month == 8, "amount"] *= 2
    got = summarise([item(df, 3, "Total", "kpi", {"measure": "amount", "aggregation": "sum", "sparkline_date": "when"})])
    line = got["takeaways"][0]["sentence"]
    assert "2024-08 was" in line and "above 2024-07" in line


def test_a_widget_with_nothing_to_show_says_nothing_and_is_counted():
    df = data()
    empty = {"widget_id": 9, "title": "x", "widget_type": "bar", "config": {}, "result": {"type": "empty", "rows": []}}
    refused = {"widget_id": 8, "title": "y", "widget_type": "bar", "config": {}, "result": None}
    got = summarise([empty, refused, item(df, 1, "By group", "bar", {"dimension": "g", "measure": "amount", "aggregation": "sum"})])
    assert len(got["takeaways"]) == 1 and got["nothing_to_say"] == 2 and got["widgets_read"] == 3


def test_a_long_page_is_still_a_summary():
    df = data()
    many = [item(df, i, f"c{i}", "bar", {"dimension": "g", "measure": "amount", "aggregation": "sum", "limit": i + 2})
            for i in range(20)]
    got = summarise(many)
    assert len(got["takeaways"]) == MAX_LINES and got["left_out"] == 20 - MAX_LINES
