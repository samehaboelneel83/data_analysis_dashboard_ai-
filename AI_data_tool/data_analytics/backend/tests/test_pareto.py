"""A few groups carry most of a total (docs/discovery/PLAN.md, phase 2 #12)."""
import numpy as np
import pandas as pd

from app.services.insights import generate_insights, suggest_widgets_from_findings
from app.services.widget_data import get_widget_data_from_df


def skewed(seed=3):
    """Twelve groups; three of them hold most of the amount."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(12):
        size = 900.0 if i < 3 else 25.0
        rows += [(f"g{i:02d}", size + rng.normal(0, 2)) for _ in range(40)]
    return pd.DataFrame(rows, columns=["grp", "amount"])


TYPES = {"grp": "categorical", "amount": "numeric"}
META = {"amount": {"number": "amount"}}


def test_the_chart_runs_from_the_largest_down_with_the_running_share():
    got = get_widget_data_from_df(skewed(), {"dimension": "grp", "measure": "amount", "aggregation": "sum", "pareto": True},
                                  "dual_axis_bar_line")
    values = [r["value"] for r in got["rows"]]
    shares = [r["value2"] for r in got["rows"]]
    assert values == sorted(values, reverse=True) and shares == sorted(shares) and shares[-1] == 100.0
    assert got["pareto"]["groups"] == 3 and got["pareto"]["of"] == 12 and got["pareto"]["carried_pct"] >= 80


def test_a_cut_chart_still_ends_where_its_groups_really_end():
    got = get_widget_data_from_df(skewed(), {"dimension": "grp", "measure": "amount", "aggregation": "sum",
                                             "pareto": True, "limit": 4}, "dual_axis_bar_line")
    assert len(got["rows"]) == 4 and got["rows"][-1]["value2"] < 100


def test_without_the_setting_the_chart_is_as_before():
    got = get_widget_data_from_df(skewed(), {"dimension": "grp", "measure": "amount", "aggregation": "sum"},
                                  "dual_axis_bar_line")
    assert "pareto" not in got and [r["name"] for r in got["rows"]] == sorted(r["name"] for r in got["rows"])


def test_the_detector_says_how_few_carry_how_much_and_becomes_a_chart():
    found = generate_insights(skewed(), TYPES, META)["findings"]
    p = next(f for f in found if f["kind"] == "pareto")
    assert p["title"].startswith("3 of 12 grp values carry") and p["figures"]["groups"] == 3
    sug = suggest_widgets_from_findings([p], TYPES, None, column_meta=META, frame=skewed())
    chart = next(s for s in sug if s["title"] == p["title"])
    assert chart["widget_type"] == "dual_axis_bar_line" and chart["config"]["pareto"] is True


def test_even_groups_and_averaged_numbers_get_no_pareto():
    rng = np.random.default_rng(1)
    even = pd.DataFrame({"grp": np.repeat([f"g{i}" for i in range(12)], 40), "amount": rng.uniform(90, 110, 480)})
    assert not [f for f in generate_insights(even, TYPES, META)["findings"] if f["kind"] == "pareto"]
    level = generate_insights(skewed(), TYPES, {"amount": {"number": "level"}})["findings"]
    assert not [f for f in level if f["kind"] == "pareto"]             # a total of a level means nothing


def test_one_group_carrying_everything_is_the_standout_not_a_pareto():
    rng = np.random.default_rng(5)
    rows = [("big", 5000.0 + rng.normal(0, 5)) for _ in range(60)]
    rows += [(f"g{i}", 10.0 + rng.normal(0, 1)) for i in range(7) for _ in range(40)]
    df = pd.DataFrame(rows, columns=["grp", "amount"])
    found = generate_insights(df, TYPES, META)["findings"]
    assert not [f for f in found if f["kind"] == "pareto"]
    assert [f for f in found if f["kind"] == "standout"]
