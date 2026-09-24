"""Quarterly and weekly time intelligence: QTD/WTD running sums, prior-period
lookups, and QoQ growth."""
import numpy as np
import pandas as pd
import pytest

from app.services.widget_data import apply_calculated_columns


def _calc(df, expr):
    out = apply_calculated_columns(df, [{"name": "out", "expression": expr}])
    assert "out" in out.columns, "expression failed to evaluate"
    return out["out"]


def test_qtd_resets_at_quarter_boundaries():
    df = pd.DataFrame({"d": ["2026-01-10", "2026-02-10", "2026-03-10", "2026-04-10"],
                       "v": [1.0, 2.0, 3.0, 4.0]})
    out = _calc(df, "QTD(`v`, `d`)")
    assert list(out) == [1.0, 3.0, 6.0, 4.0]      # April starts Q2 afresh


def test_wtd_resets_at_iso_week_boundaries():
    # Mon 2026-01-05 .. Wed, then next Monday
    df = pd.DataFrame({"d": ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-12"],
                       "v": [1.0, 1.0, 1.0, 5.0]})
    out = _calc(df, "WTD(`v`, `d`)")
    assert list(out) == [1.0, 2.0, 3.0, 5.0]


def test_sameperiodlastquarter_looks_back_three_months():
    df = pd.DataFrame({"d": ["2026-01-15", "2026-01-20", "2026-04-15"],
                       "v": [10.0, 5.0, 99.0]})
    out = _calc(df, "SAMEPERIODLASTQUARTER(`v`, `d`)")
    assert out.iloc[2] == 15.0                     # April sees January's total
    assert np.isnan(out.iloc[0])                   # nothing three months before January


def test_sameperiodlastweek_matches_weekday():
    df = pd.DataFrame({"d": ["2026-01-05", "2026-01-12", "2026-01-13"],
                       "v": [7.0, 1.0, 2.0]})
    out = _calc(df, "SAMEPERIODLASTWEEK(`v`, `d`)")
    assert out.iloc[1] == 7.0                      # Monday sees last Monday
    assert np.isnan(out.iloc[2])                   # no prior Tuesday data


def test_qoq_growth_masks_missing_and_zero_priors():
    df = pd.DataFrame({"d": ["2026-01-15", "2026-04-15", "2026-07-15"],
                       "v": [10.0, 15.0, 30.0]})
    out = _calc(df, "QOQ_GROWTH(`v`, `d`)")
    assert np.isnan(out.iloc[0])
    assert out.iloc[1] == pytest.approx(50.0)
    assert out.iloc[2] == pytest.approx(100.0)
