"""Rank selection's SAS-parity modes: percent-of-categories and the
All Other bucket — the bucket aggregated from RAW excluded rows, never as an
aggregate of aggregates."""
import pandas as pd

from app.services.widget_data import shape_series


def df():
    return pd.DataFrame({
        "region": ["A"] * 3 + ["B"] * 2 + ["C"] * 2 + ["D"] * 1 + ["E"] * 2,
        "sales": [100.0, 100.0, 100.0,   80.0, 80.0,  30.0, 30.0,  20.0,  5.0, 5.0],
    })
    # sums: A=300, B=160, C=60, D=20, E=10  (counts: 3,2,2,1,2)


def base(**extra):
    return {"dimension": "region", "measure": "sales", "aggregation": "sum", **extra}


def test_top_n_still_keeps_boundary_ties():
    r = shape_series(df(), base(rank={"mode": "top", "n": 2}))
    assert [x["name"] for x in r["rows"]] == ["A", "B"]


def test_percent_mode_reads_n_as_share_of_categories():
    # 5 categories, top 40% -> ceil(2) = 2 kept
    r = shape_series(df(), base(rank={"mode": "top", "n": 40, "percent": True}))
    assert {x["name"] for x in r["rows"]} == {"A", "B"}


def test_all_other_bucket_sums_the_excluded_categories():
    r = shape_series(df(), base(rank={"mode": "top", "n": 2, "other": True}))
    rows = {x["name"]: x["value"] for x in r["rows"]}
    assert rows["A"] == 300 and rows["B"] == 160
    assert rows["All Other"] == 60 + 20 + 10  # C + D + E


def test_all_other_uses_raw_rows_for_non_additive_aggregations():
    """avg over 'All Other' must be the mean of the excluded categories' RAW
    salaries, not the mean of their per-category means."""
    r = shape_series(df(), base(aggregation="mean", rank={"mode": "top", "n": 2, "other": True}))
    rows = {x["name"]: x["value"] for x in r["rows"]}
    # excluded raw rows: C(30,30), D(20), E(5,5) -> mean = 90/5 = 18
    # (mean of means would be (30+20+5)/3 = 18.33...)
    assert rows["All Other"] == 18


def test_bottom_n_with_other_bucket():
    r = shape_series(df(), base(rank={"mode": "bottom", "n": 2, "other": True}))
    rows = {x["name"]: x["value"] for x in r["rows"]}
    assert set(rows) == {"D", "E", "All Other"}
    assert rows["All Other"] == 300 + 160 + 60


def test_count_aggregation_other_bucket_counts_raw_rows():
    r = shape_series(df(), {"dimension": "region", "aggregation": "count",
                            "rank": {"mode": "top", "n": 2, "other": True}})
    rows = {x["name"]: x["value"] for x in r["rows"]}
    # counts: A=3, (B,C,E)=2 -- top-2 boundary is 2, ties kept: A,B,C,E all survive
    assert rows["All Other"] == 1  # only D excluded
