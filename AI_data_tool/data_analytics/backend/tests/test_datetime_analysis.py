"""Date/datetime profiling: self-coercing, granularity-aware, weekday/monthly
shaped -- correct on the string-typed frames CSV loading actually produces."""
import pandas as pd
import pytest

from app.services.analytics import analyze_datetime, run_full_analysis


def test_string_dates_analyze_without_detect_types_running_first():
    # the regression this file exists for: str - str used to TypeError here
    df = pd.DataFrame({"d": ["2026-01-05", "2026-02-10", "2026-03-15", None]})
    r = analyze_datetime(df, ["d"])["columns"]["d"]
    assert r["range_days"] == 69
    assert r["n_values"] == 3
    assert r["missing_pct"] == pytest.approx(25.0)
    assert r["granularity"] == "date"


def test_granularity_flips_to_datetime_when_any_time_of_day_exists():
    df = pd.DataFrame({"t": ["2026-01-05 09:30:00", "2026-01-06 00:00:00"]})
    r = analyze_datetime(df, ["t"])["columns"]["t"]
    assert r["granularity"] == "datetime"
    assert sum(h["count"] for h in r["hour_counts"]) == 2
    assert next(h for h in r["hour_counts"] if h["hour"] == 9)["count"] == 1


def test_weekday_counts_cover_all_seven_days_in_order():
    # 2026-01-05 is a Monday
    df = pd.DataFrame({"d": ["2026-01-05", "2026-01-12", "2026-01-06"]})
    r = analyze_datetime(df, ["d"])["columns"]["d"]
    days = {w["day"]: w["count"] for w in r["weekday_counts"]}
    assert [w["day"] for w in r["weekday_counts"]] == ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    assert days["Mon"] == 2 and days["Tue"] == 1 and days["Sun"] == 0


def test_monthly_counts_and_busiest_period():
    df = pd.DataFrame({"d": ["2026-01-01", "2026-01-15", "2026-01-20", "2026-02-01"]})
    r = analyze_datetime(df, ["d"])["columns"]["d"]
    assert r["busiest_period"] == {"period": "2026-01", "count": 3}
    assert [m["count"] for m in r["monthly_counts"]] == [3, 1]


def test_unparseable_column_degrades_to_a_note_not_a_crash():
    df = pd.DataFrame({"d": ["not", "a", "date"]})
    r = analyze_datetime(df, ["d"])["columns"]["d"]
    assert "note" in r and "min" not in r


def test_full_analysis_carries_the_datetime_section():
    df = pd.DataFrame({
        "d": pd.date_range("2026-01-01", periods=60).strftime("%Y-%m-%d"),
        "v": range(60),
    })
    r = run_full_analysis(df)
    assert r["type_map"]["d"] == "datetime"
    d = r["datetime"]["columns"]["d"]
    assert d["range_days"] == 59 and d["granularity"] == "date"
    assert "weekday_counts" in d and "monthly_counts" in d
