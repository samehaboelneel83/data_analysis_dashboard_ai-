"""What occurs together in the same group, and the rules as a network
(docs/discovery/PLAN.md, phase 2 #10)."""
import numpy as np
import pandas as pd
import pytest

from app.services.analysis.patterns import PatternError, basket_rules, rules_network
from app.services.model_widgets import shape_model_rules


def lines(n=600, seed=2):
    """One row per (group, thing). Things `a` and `b` are put together on
    purpose; `x`, `y`, `z` fall where chance puts them."""
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(n):
        if rng.random() < 0.35:
            rows += [(g, "a"), (g, "b")]
        for thing in ("x", "y", "z"):
            if rng.random() < 0.3:
                rows.append((g, thing))
        if rng.random() < 0.1:
            rows.append((g, "a"))
    return pd.DataFrame(rows, columns=["grp", "thing"])


def test_it_finds_the_pair_that_was_put_together_and_not_the_chance_ones():
    got = basket_rules(lines(), "grp", "thing").to_dict()
    top = got["rows"][0]
    assert {top["if_items"][0][1], top["then_items"][0][1]} == {"a", "b"} and top["lift"] > 1.8
    assert 0.7 < top["confidence"] <= 1.0 and top["support_rows"] > 150
    others = [r for r in got["rows"][1:] if r["lift"] >= 1.5]
    assert others == []                                             # x, y, z are independent
    assert got["meta"]["mode"] == "baskets" and got["meta"]["groups"] == lines()["grp"].nunique()


def test_a_table_with_one_thing_per_group_is_refused_in_plain_words():
    df = pd.DataFrame({"grp": range(200), "thing": ["a", "b"] * 100})
    with pytest.raises(PatternError, match="nothing occurs together"):
        basket_rules(df, "grp", "thing")


def test_the_rules_become_a_network_of_values():
    rows = basket_rules(lines(), "grp", "thing").to_dict()["rows"]
    net = rules_network(rows)
    ids = {n["id"] for n in net["nodes"]}
    assert {"thing=a", "thing=b"} <= ids
    edge = net["edges"][0]
    assert {edge["source"], edge["target"]} == {"thing=a", "thing=b"} and edge["lift"] == rows[0]["lift"]
    assert all(e["source"] in ids and e["target"] in ids for e in net["edges"])


def test_the_widget_draws_baskets_when_told_which_column_is_the_group():
    got = shape_model_rules(lines(), {"basket": "grp", "item": "thing"})
    assert got["status"] == "ok" and got["mode"] == "baskets" and got["network"]["edges"]
    assert got["rows"][0]["name"] in ("a + b", "b + a")


def test_the_row_wise_rules_carry_a_network_too():
    rng = np.random.default_rng(1)
    n = 800
    c1 = rng.choice(["p", "q"], n)
    c2 = np.where((c1 == "p") & (rng.random(n) < 0.8), "m", rng.choice(["m", "n"], n))
    got = shape_model_rules(pd.DataFrame({"c1": c1, "c2": c2}), {"predictors": ["c1", "c2"]})
    assert got["status"] == "ok" and "network" in got
    assert all(set(e) >= {"source", "target", "lift", "confidence"} for e in got["network"]["edges"])
