"""Two what-ifs side by side (docs/discovery/PLAN.md §N, scenarios)."""
import numpy as np
import pandas as pd
import pytest

from app.services.analysis.compare_scenarios import CompareScenariosError, compare_scenarios
from app.services.analysis.forecast_scenario import forecast_scenario


def frame():
    """Revenue is 3x spend plus a trend, so the arithmetic can be checked."""
    rng = np.random.default_rng(0)
    months = pd.date_range("2024-01-01", periods=30, freq="MS")
    spend = rng.uniform(80, 120, 30)
    return pd.DataFrame({"month": months, "spend": spend, "headcount": rng.uniform(9, 11, 30),
                         "revenue": 3.0 * spend + 20 * np.arange(30) + rng.normal(0, 3, 30)})


UP = {"name": "more", "adjustments": {"spend": 0.1}}
DOWN = {"name": "less", "adjustments": {"spend": -0.1}}


def test_each_scenario_is_exactly_the_single_what_if_set_beside_the_others():
    got = compare_scenarios(frame(), "month", "revenue", ["spend"], [UP, DOWN])
    one = forecast_scenario(frame(), "month", "revenue", ["spend"], {"spend": 0.1})
    rows = {r["scenario"]: r for r in got["table"]}
    assert rows["more"]["total"] == one["scenario_total"] and rows["Nothing moved"]["total"] == one["baseline_total"]
    assert rows["more"]["vs_baseline"] > 0 > rows["less"]["vs_baseline"]
    assert abs(rows["more"]["vs_baseline"] + rows["less"]["vs_baseline"]) < 1e-3          # a line: +10% and -10% mirror
    assert got["highest"] == "more" and got["lowest"] == "less"
    assert abs(got["gap"] - (rows["more"]["total"] - rows["less"]["total"])) < 1e-3
    assert got["series"] == ["Nothing moved", "more", "less"] and len(got["chart"]) == got["horizon"]
    assert got["chart"][0]["more"] > got["chart"][0]["Nothing moved"] > got["chart"][0]["less"]


def test_the_warnings_are_said_once_and_a_stretched_scenario_carries_its_name():
    got = compare_scenarios(frame(), "month", "revenue", ["spend"],
                            [{"name": "more", "adjustments": {"spend": 0.01}}, {"name": "doubled", "adjustments": {"spend": 1.0}}])
    assert sum("association, not intervention" in c for c in got["caveats"]) == 1
    assert any(c.startswith("doubled:") and "outside anything observed" in c for c in got["caveats"])
    rows = {r["scenario"]: r for r in got["table"]}
    assert rows["doubled"]["extrapolating"] is True and rows["more"]["extrapolating"] is False


def test_what_cannot_be_compared_is_refused_in_plain_words():
    with pytest.raises(CompareScenariosError, match="2 to 4"):
        compare_scenarios(frame(), "month", "revenue", ["spend"], [UP])
    with pytest.raises(CompareScenariosError, match="both called"):
        compare_scenarios(frame(), "month", "revenue", ["spend"], [UP, {**DOWN, "name": "MORE"}])
    with pytest.raises(CompareScenariosError, match="moves nothing"):
        compare_scenarios(frame(), "month", "revenue", ["spend"], [UP, {"name": "same", "adjustments": {"spend": 0}}])
    with pytest.raises(CompareScenariosError):
        compare_scenarios(frame().head(5), "month", "revenue", ["spend"], [UP, DOWN])


def test_it_runs_from_the_catalogue_and_is_offered_for_a_date_and_two_numbers():
    from app.services.analysis import registry
    from app.services.discovery import engine, profile as store
    meta = {"revenue": {"number": "amount"}, "spend": {"number": "amount"}}
    card = next(c for c in engine.tier0(store.compute(frame()), meta)["cards"] if c["capability"] == "compare_scenarios")
    assert card["claim"] == "hypothesis" and len(card["action"]["params"]["scenarios"]) == 2
    out = registry.run_analysis("compare_scenarios", frame(), card["action"]["params"], column_meta=meta)
    assert len(out["table"]) == 3


def test_a_model_that_explains_little_says_so_before_anything_else():
    df = frame()
    df["revenue"] = np.random.default_rng(5).normal(1000, 50, len(df))          # nothing to do with spend
    got = compare_scenarios(df, "month", "revenue", ["spend"], [UP, DOWN])
    assert got["weak_fit"] is True and "explains only" in got["caveats"][0]
    assert compare_scenarios(frame(), "month", "revenue", ["spend"], [UP, DOWN])["weak_fit"] is False
