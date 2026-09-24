"""Phase 7.2: "Is this difference real?" on two bars of a chart."""
import numpy as np
import pandas as pd
import pytest

from app.services.analysis.inferential import StatisticalError, difference_check


def _frame():
    rng = np.random.default_rng(7)
    a = pd.DataFrame({"region": "A", "revenue": rng.normal(100, 10, 200)})
    b = pd.DataFrame({"region": "B", "revenue": rng.normal(130, 10, 200)})
    c = pd.DataFrame({"region": "C", "revenue": rng.normal(100, 10, 400)})
    return pd.concat([a, b, c], ignore_index=True)


def test_average_uses_welch_and_names_the_population():
    r = difference_check(_frame(), "region", ["A", "B"], "revenue", "avg")
    t = r["tests"][0]
    assert t["test"] == "Welch's t-test" and t["significant"] and t["effect_label"] == "large"
    assert r["population"]["rows_a"] == 200 and "400 rows behind these two bars" in r["caveats"][0]


def test_count_uses_a_binomial_split():
    r = difference_check(_frame(), "region", ["A", "C"], None, "count")
    t = r["tests"][0]
    assert t["test"].startswith("Exact binomial") and t["significant"]
    assert t["values"] == {"A": 200, "C": 400}
    same = difference_check(_frame(), "region", ["A", "B"], None, "count")["tests"][0]
    assert not same["significant"]


def test_a_sum_is_split_into_its_two_drivers():
    r = difference_check(_frame(), "region", ["A", "C"], "revenue", "sum")
    assert [t["question"] for t in r["tests"]] == ["typical row", "row counts"]
    assert "driven by the number of rows" in r["summary"]
    assert "typical row's value" not in r["summary"]


def test_median_is_rank_based():
    assert difference_check(_frame(), "region", ["A", "B"], "revenue", "median")["tests"][0]["test"] == "Mann-Whitney U"


@pytest.mark.parametrize("groups,agg,msg", [
    (["A", "A"], "avg", "two different"),
    (["A", "Z"], "avg", "No rows for Z"),
    (["A", "B"], "max", "one extreme row"),
])
def test_refusals_are_sentences(groups, agg, msg):
    with pytest.raises(StatisticalError) as e:
        difference_check(_frame(), "region", groups, "revenue", agg)
    assert msg in str(e.value)


def test_granularity_buckets_dates():
    df = pd.DataFrame({"d": ["2026-01-05"] * 30 + ["2026-02-05"] * 30,
                       "v": list(range(30)) + list(range(100, 130))})
    r = difference_check(df, "d", ["2026-01", "2026-02"], "v", "avg", "month")
    assert r["tests"][0]["significant"]


def test_a_significant_but_negligible_part_is_worded_as_such():
    rng = np.random.default_rng(3)
    df = pd.concat([pd.DataFrame({"g": "A", "v": rng.normal(100, 10, 5800)}),
                    pd.DataFrame({"g": "B", "v": rng.normal(100, 10, 5200)})], ignore_index=True)
    r = difference_check(df, "g", ["A", "B"], "v", "sum")
    counts = r["tests"][1]
    assert counts["significant"] and counts["effect_label"] == "negligible"
    assert "Only the number of rows differs significantly, and by a negligible amount" in r["summary"]
