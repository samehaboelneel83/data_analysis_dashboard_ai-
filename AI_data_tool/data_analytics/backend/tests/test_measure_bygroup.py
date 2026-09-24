"""BYGROUP: per-aggregation ByGroup context declared inside one measure."""
import pandas as pd
import pytest

from app.services.measure_eval import evaluate_measure


def _df():
    return pd.DataFrame({
        "region": ["N", "N", "S", "S"],
        "city":   ["A", "B", "C", "D"],
        "chan":   ["web", "store", "web", "store"],
        "sales":  [10.0, 30.0, 20.0, 20.0],
    })


def test_share_of_own_region_rebasess_per_region():
    r = evaluate_measure("SUM(sales) / BYGROUP(SUM(sales), 'region') * 100", _df(), ["city"])
    got = {k: round(v, 1) for k, v in r.items()}
    assert got == {"A": 25.0, "B": 75.0, "C": 50.0, "D": 50.0}


def test_bygroup_ignores_the_outer_grain():
    # Grouped by chan, BYGROUP still buckets by region: each (chan) cell divides
    # its own sales by its rows' region totals. web = A(N)+C(S) = 10+20; the
    # region denominators are N=40, S=40 -> 10/40 + ... but the measure is one
    # value per chan, so this asserts the region context is what BYGROUP used.
    r = evaluate_measure("BYGROUP(SUM(sales), 'region')", _df(), ["chan"])
    # web rows are A(region N) and C(region S); .first() picks N -> 40
    # store rows are B(N) and D(S); .first() picks N -> 40
    assert round(r["web"], 1) == 40.0
    assert round(r["store"], 1) == 40.0


def test_multi_column_bygroup():
    df = _df()
    r = evaluate_measure("BYGROUP(SUM(sales), 'region', 'chan')", df, ["city"])
    # each city maps to its (region, chan): A=(N,web)=10, B=(N,store)=30,
    # C=(S,web)=20, D=(S,store)=20
    assert {k: round(v, 1) for k, v in r.items()} == {"A": 10.0, "B": 30.0, "C": 20.0, "D": 20.0}


def test_bygroup_combines_with_total():
    # region share of grand total, evaluated per city
    r = evaluate_measure(
        "BYGROUP(SUM(sales), 'region') / TOTAL(SUM(sales)) * 100", _df(), ["city"])
    # region N total 40, S total 40, grand 80 -> every city 50%
    assert all(round(v, 1) == 50.0 for v in r)


def test_scalar_grain_is_refused():
    with pytest.raises(ValueError, match="grouped by a dimension"):
        evaluate_measure("BYGROUP(SUM(sales), 'region')", _df(), [])


def test_nesting_is_rejected():
    with pytest.raises(ValueError, match="cannot contain"):
        evaluate_measure("BYGROUP(BYGROUP(SUM(sales), 'chan'), 'region')", _df(), ["city"])
    with pytest.raises(ValueError, match="cannot contain"):
        evaluate_measure("BYGROUP(TOTAL(SUM(sales)), 'region')", _df(), ["city"])


def test_unquoted_column_is_rejected():
    with pytest.raises(ValueError, match="quoted column names"):
        evaluate_measure("BYGROUP(SUM(sales), region)", _df(), ["city"])


def test_missing_column_is_reported():
    with pytest.raises(ValueError, match="not found"):
        evaluate_measure("BYGROUP(SUM(sales), 'nope')", _df(), ["city"])
