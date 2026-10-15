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
