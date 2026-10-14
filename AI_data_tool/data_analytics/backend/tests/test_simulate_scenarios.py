"""How sure a what-if is (docs/discovery/PLAN.md §D-15, phase 5)."""
import numpy as np
import pytest

from app.services.analysis.compare_scenarios import compare_scenarios
from app.services.analysis.simulate_scenarios import SimulateScenariosError, simulate_scenarios
from tests.test_compare_scenarios import DOWN, UP, frame


def test_the_middle_of_the_runs_is_the_single_what_if_and_the_range_holds_it():
    got = simulate_scenarios(frame(), "month", "revenue", ["spend"], [UP, DOWN])
    line = {r["scenario"]: r for r in compare_scenarios(frame(), "month", "revenue", ["spend"], [UP, DOWN])["table"]}
    for row in got["table"]:
        assert row["expected"] == line[row["scenario"]]["total"]
        assert row["p05"] < row["p25"] < row["median"] < row["p75"] < row["p95"]
        assert abs(row["median"] - row["expected"]) / abs(row["expected"]) < 0.01
    assert got["baseline"]["expected"] == line["Nothing moved"]["total"]
    assert got["series"] == ["Nothing moved", "more", "less"] and got["highest"] == "more"


def test_a_factor_that_really_moves_the_number_leaves_little_chance_of_ending_below_doing_nothing():
    rows = {r["scenario"]: r for r in simulate_scenarios(frame(), "month", "revenue", ["spend"], [UP, DOWN])["table"]}
    assert rows["more"]["chance_below_baseline"] < 0.01 and rows["less"]["chance_below_baseline"] > 0.99
    assert rows["more"]["gain_p05"] > 0 > rows["less"]["gain_p95"]


def test_a_factor_that_does_nothing_is_a_coin_toss_and_says_so():
    df = frame()
    rows = simulate_scenarios(df, "month", "revenue", ["headcount"], [{"name": "more", "adjustments": {"headcount": 0.1}}])["table"]
    assert 0.05 < rows[0]["chance_below_baseline"] < 0.95


def test_the_same_data_gives_the_same_answer_and_a_floor_is_reported():
    a = simulate_scenarios(frame(), "month", "revenue", ["spend"], [UP])
    b = simulate_scenarios(frame(), "month", "revenue", ["spend"], [UP])
    assert a == b
    low = a["table"][0]["p05"]
    got = simulate_scenarios(frame(), "month", "revenue", ["spend"], [UP], floor=low)
    assert 0.03 <= got["table"][0]["chance_below_floor"] <= 0.07 and got["floor"] == low
    assert "chance_below_floor" not in a["table"][0]


def test_the_histogram_is_shared_and_each_scenario_adds_up():
    got = simulate_scenarios(frame(), "month", "revenue", ["spend"], [UP, DOWN])
    for name in got["series"]:
        assert abs(sum(b[name] for b in got["histogram"]) - 100) < 0.5
    assert all(a["to"] == b["from"] for a, b in zip(got["histogram"], got["histogram"][1:]))


def test_one_number_is_enough_to_ask():
    got = simulate_scenarios(frame(), "month", "revenue", ["spend"], change_pct=5)
    assert [r["scenario"] for r in got["table"]] == ["+5%", "-5%"]
    assert got["table"][0]["adjustments"] == {"spend": 0.05}


def test_what_cannot_be_simulated_is_refused_in_plain_words():
    with pytest.raises(SimulateScenariosError, match="moves nothing"):
        simulate_scenarios(frame(), "month", "revenue", ["spend"], [{"name": "same", "adjustments": {}}])
    with pytest.raises(SimulateScenariosError, match="both called"):
        simulate_scenarios(frame(), "month", "revenue", ["spend"], [UP, {**DOWN, "name": "MORE"}])
    with pytest.raises(SimulateScenariosError, match="periods of history"):
        simulate_scenarios(frame().head(6), "month", "revenue", ["spend"], [UP])
    with pytest.raises(SimulateScenariosError, match="other than 0"):
        simulate_scenarios(frame(), "month", "revenue", ["spend"], change_pct=0)


def test_the_warnings_of_the_what_if_come_with_it_and_carry_keys():
    got = simulate_scenarios(frame(), "month", "revenue", ["spend"],
                             [{"name": "more", "adjustments": {"spend": 0.01}},
                              {"name": "doubled", "adjustments": {"spend": 1.0}}])
    assert len(got["caveats"]) == len(got["caveats_i18n"])
    assert sum("association, not intervention" in c for c in got["caveats"]) == 1
    assert any(c.startswith("doubled:") and "outside anything observed" in c for c in got["caveats"])
    keys = [k["key"] for k in got["caveats_i18n"] if k]
    assert {"sim.what", "sim.same", "fs.assoc", "an.outside.named"} <= set(keys)
    assert {r["scenario"]: r["extrapolating"] for r in got["table"]} == {"more": False, "doubled": True}


# ── A model of the wrong form (the open item of §AY) ─────────────────────────

import pandas as pd


def _history(curve: bool, n: int = 48, seed: int = 4):
    """One row per month: the number follows the factor in a straight line, or
    (curve) with a bend that grows as the factor grows -- and the factor rises
    over time, so the newest periods are where the line is most wrong."""
    rng = np.random.default_rng(seed)
    months = pd.date_range("2021-01-01", periods=n, freq="MS")
    spend = np.linspace(10.0, 60.0, n) + rng.normal(0, 1.0, n)
    outcome = 50 + 3.0 * spend + (0.25 * (spend - 10) ** 2 if curve else 0.0) + rng.normal(0, 4.0, n)
    return pd.DataFrame({"month": months, "spend": spend, "outcome": outcome})


def test_a_straight_line_through_a_curve_is_widened_and_said_to_bend():
    got = simulate_scenarios(_history(curve=True), "month", "outcome", ["spend"], [UP])
    assert got["widened"] and got["bends"]
    assert got["noise"]["unseen"] > got["noise"]["own"] * 1.25
    keys = [c["key"] for c in got["caveats_i18n"] if c]
    assert "sim.widened" in keys and "sim.bends" in keys


def test_the_widened_range_is_really_wider_than_the_models_own():
    from app.services.analysis import simulate_scenarios as sim
    df = _history(curve=True)
    wide = simulate_scenarios(df, "month", "outcome", ["spend"], [UP])["table"][0]
    old = sim.WIDEN_FROM
    sim.WIDEN_FROM = 1e9                                   # never widen: the model's own idea of its noise
    try:
        narrow = simulate_scenarios(df, "month", "outcome", ["spend"], [UP])["table"][0]
    finally:
        sim.WIDEN_FROM = old
    assert (wide["p95"] - wide["p05"]) > 1.2 * (narrow["p95"] - narrow["p05"])
    # The middle does not move: only how sure it is.
    assert abs(wide["median"] - narrow["median"]) / abs(narrow["median"]) < 0.02


def test_a_model_of_the_right_form_is_left_as_it_was():
    got = simulate_scenarios(_history(curve=False), "month", "outcome", ["spend"], [UP])
    assert not got["widened"] and not got["bends"]
    assert not {"sim.widened", "sim.bends"} & {c["key"] for c in got["caveats_i18n"] if c}


def test_too_short_a_history_to_hold_any_back_measures_nothing():
    from app.services.analysis.simulate_scenarios import _unseen_miss
    x = np.column_stack([np.ones(7), np.arange(7.0), np.arange(7.0) ** 0.5])
    assert _unseen_miss(np.arange(7.0), x) is None
    longer = np.column_stack([np.ones(30), np.arange(30.0), np.sin(np.arange(30.0))])
    assert _unseen_miss(np.arange(30.0) * 2 + 1, longer) < 1e-6        # a perfect line misses nothing
