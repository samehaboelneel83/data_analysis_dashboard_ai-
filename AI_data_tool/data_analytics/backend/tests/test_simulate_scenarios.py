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
