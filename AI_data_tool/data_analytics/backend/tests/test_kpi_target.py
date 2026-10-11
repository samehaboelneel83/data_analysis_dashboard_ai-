"""A number against the target its author stored (docs/discovery/PLAN.md §N-7)."""
import numpy as np
import pandas as pd

from app.services import semantic_guard as guard
from app.services.discovery import engine, profile as store
from app.services.widget_data import get_widget_data_from_df


def daily(last="2024-08-31", seed=1):
    rng = np.random.default_rng(seed)
    days = pd.date_range("2024-01-01", last, freq="D")
    return pd.DataFrame({"when": np.repeat(days, 10), "amount": 100.0 + rng.normal(0, 1, len(days) * 10),
                         "kind": np.tile(["a", "b"], len(days) * 5)})


def test_a_target_on_everything_shown_says_how_far_along_and_whether_met():
    df = daily()
    out = get_widget_data_from_df(df, {"measure": "amount", "aggregation": "sum", "target_value": 300000}, "kpi")
    t = out["target"]
    assert t["applies"] and 80 < t["pct"] < 82 and t["met"] is False and t["remaining"] > 0 and t["period"] is None
    met = get_widget_data_from_df(df, {"measure": "amount", "aggregation": "sum", "target_value": 200000}, "kpi")["target"]
    assert met["met"] is True and met["pct"] > 100


def test_a_monthly_target_is_set_against_the_last_complete_month_not_the_total():
    df = daily(last="2024-09-05")
    out = get_widget_data_from_df(df, {"measure": "amount", "aggregation": "sum", "target_value": 40000,
                                       "target_period": "month", "sparkline_date": "when",
                                       "sparkline_granularity": "month"}, "kpi")
    t = out["target"]
    assert t["applies"] and t["label"] == "2024-08" and 76 < t["pct"] < 79          # August: 31 days x 10 x 100


def test_a_period_target_with_no_history_is_not_applied_and_says_why():
    out = get_widget_data_from_df(daily(), {"measure": "amount", "aggregation": "sum", "target_value": 40000,
                                            "target_period": "month"}, "kpi")
    assert out["target"]["applies"] is False and "no history by month" in out["target"]["reason"]


def test_where_lower_is_better_being_under_the_target_is_meeting_it():
    out = get_widget_data_from_df(daily(), {"measure": "amount", "aggregation": "avg", "target_value": 110,
                                            "trend_good": "down"}, "kpi")
    assert out["target"]["met"] is True and out["target"]["lower_is_better"] is True


def test_a_kpi_without_a_target_has_none():
    assert "target" not in get_widget_data_from_df(daily(), {"measure": "amount", "aggregation": "sum"}, "kpi")


def test_only_a_stored_target_is_read_and_never_a_guess():
    assert guard.target_of("amount", {"amount": {"target": 5000, "target_period": "month"}}) == (5000.0, "month")
    assert guard.target_of("amount", {"amount": {"target": 5000, "target_period": "fortnight"}}) == (5000.0, None)
    assert guard.target_of("amount", {"amount": {"number": "amount"}}) is None
    assert guard.target_of("amount", {"amount": {"target": "soon"}}) is None


def test_the_headline_card_is_offered_against_a_stored_target_only():
    prof = store.compute(daily())
    kinds = engine.column_kinds(prof, {})

    def kpi_card(meta):
        cards = [{"action": {"kind": "add_widget", "widget_type": "kpi", "config": {"measure": "amount", "aggregation": "sum"}},
                  "limits": []}]
        engine._with_history(cards, kinds, prof, meta)
        engine._with_targets(cards, kinds, prof, meta)
        return cards[0]

    plain = kpi_card({})
    assert "target_value" not in plain["action"]["config"]
    monthly = kpi_card({"amount": {"target": 40000, "target_period": "month", "direction": "higher_better"}})
    cfg = monthly["action"]["config"]
    assert cfg["target_value"] == 40000 and cfg["target_period"] == "month" and cfg["sparkline_granularity"] == "month"
    assert cfg["trend_good"] == "up" and any("stored for this column" in l for l in monthly["limits"])
    out = get_widget_data_from_df(daily(), cfg, "kpi")
    assert out["target"]["applies"] and out["target"]["label"] == "2024-08"
