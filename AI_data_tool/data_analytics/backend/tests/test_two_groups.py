"""Two groups, one outcome: the reading of an experiment (docs/discovery/PLAN.md §N-4)."""
import numpy as np
import pandas as pd
import pytest

from app.services.analysis.two_groups import TwoGroupsError, compare_two_groups
from app.services.discovery import engine, profile as store


def trial(n=4000, base=0.105, other=0.142, seed=7):
    rng = np.random.default_rng(seed)
    arm = np.where(np.arange(n) % 2 == 0, "first", "second")
    done = rng.random(n) < np.where(arm == "second", other, base)
    return pd.DataFrame({"arm": arm, "done": np.where(done, "yes", "no"),
                         "spent": rng.normal(50, 10, n) + np.where(arm == "second", 3.0, 0.0),
                         "row_id": np.arange(n)})


def test_a_real_difference_in_rates_is_read_with_its_range_lift_and_verdict():
    m = compare_two_groups(trial(n=12000), "arm", "done", outcome_value="yes", baseline="first").to_dict()["meta"]
    assert m["measure"] == "rate" and m["baseline"] == "first" and m["other"] == "second"
    assert 0.01 < m["difference"] < 0.06 and m["low"] > 0 and m["high"] > m["difference"]
    assert 10 < m["lift_pct"] < 60 and m["chance_higher"] > 0.99 and m["p_value"] < 0.01
    assert m["verdict"] == "higher" and "second is higher than first" in m["sentence"]
    assert len(m["curves"]["first"]) > 20 and all(0 <= x <= 1 for x, _ in m["curves"]["second"])


def test_no_real_difference_is_not_called_one():
    m = compare_two_groups(trial(other=0.105, seed=11), "arm", "done", outcome_value="yes").to_dict()["meta"]
    assert m["verdict"] == "not_clear" and m["low"] < 0 < m["high"] and "Not clear yet" in m["sentence"]


def test_a_number_is_compared_as_an_average():
    m = compare_two_groups(trial(), "arm", "spent", baseline="first").to_dict()["meta"]
    assert m["measure"] == "mean" and 2 < m["difference"] < 4 and m["verdict"] == "higher"


def test_the_rarer_value_is_the_one_counted_by_default_and_the_answer_is_the_same_twice():
    a = compare_two_groups(trial(), "arm", "done").to_dict()
    assert a["meta"]["outcome_value"] == "yes"
    assert a == compare_two_groups(trial(), "arm", "done").to_dict()


def test_it_always_says_what_it_cannot_know():
    w = compare_two_groups(trial(), "arm", "done").to_dict()["warnings"]
    assert "at random" in w[0]


def test_three_groups_and_a_tiny_group_are_refused_in_plain_words():
    df = trial()
    df.loc[df.index[:500], "arm"] = "third"
    with pytest.raises(TwoGroupsError, match="exactly two groups"):
        compare_two_groups(df, "arm", "done")
    small = trial(n=200)
    small["arm"] = np.where(np.arange(200) < 10, "first", "second")
    with pytest.raises(TwoGroupsError, match="at least 30"):
        compare_two_groups(small, "arm", "done")


def test_it_is_offered_for_a_column_of_two_big_groups_and_runs_from_the_catalogue():
    df = trial()
    meta = {"done": {"outcome": True}}
    prof = store.compute(df)
    cards = [c for c in engine.tier0(prof, meta)["cards"] if c["capability"] == "compare_two_groups"]
    assert cards and cards[0]["action"]["params"]["group_col"] == "arm" and cards[0]["claim"] == "association"
    assert "row_id" not in {c["action"]["params"]["group_col"] for c in cards}
    from app.services.analysis import registry
    out = registry.run_analysis("compare_two_groups", df, cards[0]["action"]["params"], column_meta=meta)
    assert (out.to_dict() if hasattr(out, "to_dict") else out)["meta"]["verdict"] in ("higher", "lower", "not_clear")
