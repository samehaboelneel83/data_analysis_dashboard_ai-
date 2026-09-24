import pandas as pd
import numpy as np
from app.services.widget_data import _eval_expr


def test_date_part_extraction():
    df = pd.DataFrame({"d": pd.to_datetime(["2024-01-15", "2024-07-04", "2023-12-31"])})
    assert _eval_expr("YEAR(d)", df).tolist() == [2024, 2024, 2023]
    assert _eval_expr("QUARTER(d)", df).tolist() == [1, 3, 4]
    assert _eval_expr("MONTH(d)", df).tolist() == [1, 7, 12]
    assert _eval_expr("DAY(d)", df).tolist() == [15, 4, 31]


def test_datetrunc_month_and_string_dates_are_coerced():
    # date column stored as plain strings, like a freshly-read CSV column
    df = pd.DataFrame({"d": ["2024-03-17", "2024-03-02"]})
    result = _eval_expr("DATETRUNC(d, 'month')", df)
    assert list(result) == [pd.Timestamp("2024-03-01")] * 2


def test_ytd_resets_at_year_boundary():
    df = pd.DataFrame({
        "d": pd.to_datetime(["2023-12-01", "2024-01-01", "2024-02-01"]),
        "sales": [1000, 10, 20],
    })
    assert _eval_expr("YTD(sales, d)", df).tolist() == [1000, 10, 30]


def test_sameperiodlastyear_missing_prior_year_is_nan_and_yoy_growth_computes():
    df = pd.DataFrame({
        "d": pd.to_datetime(["2023-01-15", "2024-01-10", "2024-01-20"]),
        "sales": [100, 60, 90],
    })
    spy = _eval_expr("SAMEPERIODLASTYEAR(sales, d)", df)
    assert pd.isna(spy.iloc[0])       # 2023-01 has no 2022-01 to compare against
    assert spy.iloc[1] == spy.iloc[2] == 100.0

    growth = _eval_expr("YOY_GROWTH(sales, d)", df)
    assert pd.isna(growth.iloc[0])
    assert round(growth.iloc[1], 2) == 50.0   # (150 - 100) / 100 * 100


def test_yoy_growth_zero_prior_baseline_is_nan_not_inf():
    df = pd.DataFrame({
        "d": pd.to_datetime(["2023-01-15", "2024-01-10"]),
        "sales": [0, 60],
    })
    growth = _eval_expr("YOY_GROWTH(sales, d)", df)
    assert pd.isna(growth.iloc[1])  # prior-year (2023-01) baseline was exactly 0 -> NaN, not inf
    assert not np.isinf(growth.iloc[1])
