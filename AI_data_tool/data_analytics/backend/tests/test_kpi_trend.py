"""A KPI with its recent history: sparkline and change against the previous
period (docs/discovery/PLAN.md, phase 2 #3)."""
import numpy as np
import pandas as pd

from app.services.widget_data import get_widget_data_from_df, kpi_trend


def daily(months=8, last_day="2024-08-31", per_day=10, seed=1):
    rng = np.random.default_rng(seed)
    days = pd.date_range("2024-01-01", last_day, freq="D")
    rows = [(d, 100.0 + rng.normal(0, 2), "a" if i % 2 else "b") for d in days for i in range(per_day)]
    return pd.DataFrame(rows, columns=["when", "amount", "g"])


def test_the_kpi_carries_its_history_and_the_change():
    df = daily()
    df.loc[df["when"].dt.month == 8, "amount"] *= 1.5                 # the last full month is half as large again
    got = get_widget_data_from_df(df, {"measure": "amount", "aggregation": "sum", "sparkline_date": "when"}, "kpi")
    assert got["type"] == "scalar" and got["rows"][0]["value"] == df["amount"].sum()     # the headline is untouched
    t = got["trend"]
    assert t["granularity"] == "month" and [p["period"] for p in t["series"]][-2:] == ["2024-07", "2024-08"]
    assert t["period"] == "2024-08" and t["previous_period"] == "2024-07"
    assert 40 < t["change_pct"] < 60 and t["current"] == t["series"][-1]["value"]


def test_the_period_the_data_stops_inside_is_left_out():
    """Data through 5 September: September is five days, not a collapse."""
    t = kpi_trend(daily(last_day="2024-09-05"), {"measure": "amount", "aggregation": "sum", "sparkline_date": "when"})
    assert t["period"] == "2024-08" and t["partial_dropped"] is True
    assert abs(t["change_pct"]) < 10


def test_the_trend_uses_the_kpis_own_aggregation_and_filters():
    df = daily()
    cfg = {"measure": "amount", "aggregation": "avg", "sparkline_date": "when",
           "filters": [{"column": "g", "op": "eq", "value": "a"}]}
    t = kpi_trend(df, cfg)
    only_a = df[df["g"] == "a"]
    assert abs(t["current"] - only_a[only_a["when"].dt.month == 8]["amount"].mean()) < 1e-6
    count = kpi_trend(df, {"measure": "amount", "aggregation": "count", "sparkline_date": "when"})
    assert count["current"] == 31 * 10


def test_the_grain_follows_how_much_history_there_is():
    month_of_days = daily(last_day="2024-01-30")
    assert kpi_trend(month_of_days, {"measure": "amount", "aggregation": "sum", "sparkline_date": "when"})["granularity"] == "day"
    years = pd.DataFrame({"when": pd.date_range("2015-01-01", "2024-12-31", freq="7D")})
    years["amount"] = 1.0
    assert kpi_trend(years, {"measure": "amount", "aggregation": "sum", "sparkline_date": "when"})["granularity"] == "year"


def test_too_little_history_is_no_trend_and_never_an_error():
    two = pd.DataFrame({"when": pd.to_datetime(["2024-01-15", "2024-02-15"]), "amount": [1.0, 2.0]})
    got = get_widget_data_from_df(two, {"measure": "amount", "aggregation": "sum", "sparkline_date": "when"}, "kpi")
    assert "trend" not in got and got["rows"][0]["value"] == 3.0
    missing = get_widget_data_from_df(two, {"measure": "amount", "aggregation": "sum", "sparkline_date": "nope"}, "kpi")
    assert "trend" not in missing and missing["type"] == "scalar"


def test_a_kpi_without_the_setting_is_exactly_as_before():
    got = get_widget_data_from_df(daily(), {"measure": "amount", "aggregation": "sum"}, "kpi")
    assert "trend" not in got


def two_years(seed=3):
    """Monthly totals that are higher every December, and 20% up on the year."""
    rng = np.random.default_rng(seed)
    rows = []
    for d in pd.date_range("2023-01-01", "2024-12-31", freq="D"):
        level = (100.0 if d.year == 2023 else 120.0) * (3.0 if d.month == 12 else 1.0)
        rows.append((d, level + rng.normal(0, 0.5)))
    return pd.DataFrame(rows, columns=["when", "amount"])


def test_the_same_period_a_year_before_sits_beside_the_previous_period():
    t = kpi_trend(two_years(), {"measure": "amount", "aggregation": "sum", "sparkline_date": "when"})
    assert t["period"] == "2024-12" and t["previous_period"] == "2024-11"
    assert t["change_pct"] > 150                                    # the seasonal jump on November
    assert t["year_ago"]["period"] == "2023-12" and 18 < t["year_ago"]["change_pct"] < 22   # the year's real growth


def test_no_year_before_when_the_history_does_not_reach():
    t = kpi_trend(daily(), {"measure": "amount", "aggregation": "sum", "sparkline_date": "when"})
    assert t["year_ago"] is None


def test_the_year_before_of_each_grain():
    from app.services.widget_data import _year_before
    assert _year_before("2024-03", "month") == "2023-03" and _year_before("2024-Q2", "quarter") == "2023-Q2"
    assert _year_before("2024-W07", "week") == "2023-W07" and _year_before("2024-03-05", "day") == "2023-03-05"
    assert _year_before("2024-02-29", "day") is None and _year_before("2024", "year") is None
