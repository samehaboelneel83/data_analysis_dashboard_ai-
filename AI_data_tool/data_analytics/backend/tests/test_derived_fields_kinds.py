"""B-36: a rate of totals only between two numbers of the same kind."""
import numpy as np
import pandas as pd

from app.services.derived_fields import rate_measures


def _frame(n=200):
    rng = np.random.default_rng(0)
    attempts = rng.integers(1, 4, n)
    return pd.DataFrame({
        "delivery_attempts": attempts,
        "delivery_fee_egp": rng.uniform(20, 80, n).round(2),
        "late_orders": rng.integers(0, 3, n),
        "total_orders": rng.integers(5, 10, n),
    })


def test_a_count_is_not_a_share_of_money_by_name():
    df = _frame()
    names = {m["name"] for m in rate_measures(df, list(df.columns), set())}
    assert "delivery_attempts_pct_of_delivery_fee_egp" not in names
    assert "late_orders_pct_of_total_orders" in names


def test_a_count_is_not_a_share_of_money_by_classification():
    df = _frame().rename(columns={"delivery_fee_egp": "delivery_charge"})
    meta = {"delivery_attempts": {"number": "count"}, "delivery_charge": {"number": "amount"}}
    names = {m["name"] for m in rate_measures(df, list(df.columns), set(), meta)}
    assert "delivery_attempts_pct_of_delivery_charge" not in names


def _shipments(n=300):
    rng = np.random.default_rng(1)
    return pd.DataFrame({
        "shipment_id": [f"S{i}" for i in range(n)],
        "service_type": rng.choice(["express", "standard", "economy"], n),
        "weight_kg": rng.uniform(0.5, 30, n).round(2),
        "declared_value_egp": rng.uniform(100, 5000, n).round(2),
        "delivery_fee_egp": rng.uniform(20, 80, n).round(2),
        "cod_amount_egp": rng.uniform(0, 3000, n).round(2),
        "delivery_attempts": rng.integers(1, 4, n),
    })


def test_a_card_of_several_numbers_holds_one_unit_and_says_which():
    """B-36 item 2: "Total of 5 numbers" listed weight, value, fees, COD and
    attempts as one card of totals."""
    from app.services.analytics import detect_types
    from app.services.insights import effective_roles
    from app.services.suggest_variety import _Profile, catalogue_suggestions
    df = _shipments()
    p = _Profile(df, effective_roles(detect_types(df), {}), {}, None)
    cards = [s for s in catalogue_suggestions(p) if s["widget_type"] == "card"]
    for c in cards:
        ms = c["config"]["measures"]
        assert "weight_kg" not in ms or len(ms) == 1, ms
        assert "delivery_attempts" not in ms, ms
        assert "numbers" not in c["title"], c["title"]
    money = [c for c in cards if set(c["config"]["measures"]) == {"declared_value_egp", "delivery_fee_egp", "cod_amount_egp"}]
    assert money, [c["config"] for c in cards]
