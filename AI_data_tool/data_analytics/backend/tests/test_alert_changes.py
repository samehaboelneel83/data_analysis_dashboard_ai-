"""HR evaluation 2026-10-01, item 3.1: change alerts and Test now."""
from types import SimpleNamespace

import pandas as pd

from app.services.alerts import _split_comparison, evaluate


DF = pd.DataFrame({"emp_no": range(100), "salary": [50000 + i for i in range(100)]})


def test_condition_reports_its_current_value():
    out = evaluate(DF, SimpleNamespace(expression="COUNT(emp_no) < 99", change_pct=None))
    assert out["firing"] is False and out["value"] == 100
    assert "100" in out["message"] and "would not fire" in out["message"]


def test_split_comparison_ignores_operators_inside_calls():
    assert _split_comparison("SUM(a) >= 10") == ("SUM(a)", ">=", "10")
    assert _split_comparison("COUNT(a)") is None


def test_change_alert_sets_a_baseline_then_fires_on_the_move():
    a = SimpleNamespace(expression="COUNT(emp_no)", change_pct=20, change_direction="down", last_value=None)
    first = evaluate(DF, a)
    assert first["firing"] is False and first["value"] == 100 and "baseline" in first["message"]
    a.last_value = 140.0
    assert evaluate(DF, a)["firing"] is True        # 100 vs 140 = -28.6%
    a.change_direction = "up"
    assert evaluate(DF, a)["firing"] is False
