"""Relative date filters (Phase 6.4): explicit anchor, labelled window,
incomplete periods flagged, and a partial last bucket on a time axis."""
from datetime import date

import pandas as pd
import pytest

from app.services.relative_dates import (RelativeDateError, add_periods, partial_period,
                                         resolve_filters, validate_spec, window)
from app.services.widget_data import _apply_filters, get_widget_data_from_df


def _w(mode, unit, anchor, n=1, **kw):
    return window(validate_spec({"mode": mode, "unit": unit, "n": n, **kw}), anchor)


A = date(2026, 9, 14)  # a Monday


def test_last_n_days_includes_the_anchor_day():
    s, e, label, inc = _w("last", "day", A, n=30)
    assert (s, e) == (date(2026, 8, 16), date(2026, 9, 15))
    assert label == "Last 30 days" and not inc


def test_last_n_months_are_complete_months_by_default():
    s, e, label, inc = _w("last", "month", A, n=3)
    assert (s, e) == (date(2026, 6, 1), date(2026, 9, 1))
    assert "complete" in label and not inc


def test_last_n_months_including_current_is_flagged_incomplete():
    s, e, label, inc = _w("last", "month", A, n=3, include_current=True)
    assert (s, e) == (date(2026, 7, 1), date(2026, 10, 1))
    assert inc


@pytest.mark.parametrize("unit,start", [("week", date(2026, 9, 14)), ("month", date(2026, 9, 1)),
                                        ("quarter", date(2026, 7, 1)), ("year", date(2026, 1, 1))])
def test_to_date_runs_from_period_start_through_the_anchor(unit, start):
    s, e, _label, inc = _w("to_date", unit, A)
    assert (s, e) == (start, date(2026, 9, 15)) and not inc


def test_this_month_is_incomplete_mid_month_and_complete_on_the_last_day():
    assert _w("this", "month", A)[3] is True
    assert _w("this", "month", date(2026, 9, 30))[3] is False


def test_previous_and_rolling():
    assert _w("previous", "quarter", A)[:2] == (date(2026, 4, 1), date(2026, 7, 1))
    s, e, label, _ = _w("rolling", "month", A, n=12)
    assert (s, e) == (date(2025, 9, 15), date(2026, 9, 15)) and label == "Rolling 12 months"


def test_month_arithmetic_clamps_the_day():
    assert add_periods(date(2026, 3, 31), "month", -1) == date(2026, 2, 28)
    assert add_periods(date(2024, 3, 31), "month", -1) == date(2024, 2, 29)


@pytest.mark.parametrize("spec", [None, {"mode": "soon"}, {"unit": "decade"},
                                  {"anchor": "yesterday"}, {"n": 0}, {"n": "x"}])
def test_bad_specs_are_refused_with_a_sentence(spec):
    with pytest.raises(RelativeDateError):
        validate_spec(spec)


def _frame():
    days = pd.date_range("2026-01-01", "2026-09-14", freq="D")
    return pd.DataFrame({"d": days.strftime("%Y-%m-%d"), "v": 1.0})


def test_data_max_anchor_reads_the_latest_date_even_from_text_dates():
    df = _frame()
    f = [{"column": "d", "op": "relative",
          "value": {"mode": "last", "unit": "day", "n": 7, "anchor": "data_max"}}]
    out, notes = resolve_filters(df, f, today=date(2027, 1, 1))
    assert out == [{"column": "d", "op": "date_range", "value": ["2026-09-08", "2026-09-15"]}]
    assert notes[0]["anchor_date"] == "2026-09-14"
    assert "latest data (14 Sep 2026)" in notes[0]["text"]
    assert len(_apply_filters(df, f)) == 7


def test_today_anchor_is_named_and_can_return_nothing():
    df = _frame()
    f = [{"column": "d", "op": "relative", "value": {"mode": "last", "unit": "day", "n": 7}}]
    out, notes = resolve_filters(df, f, today=date(2027, 1, 1))
    assert notes[0]["anchor_label"] == "today (1 Jan 2027)"
    assert _apply_filters(df, out).empty


def test_an_unresolvable_filter_matches_nothing_and_says_why():
    df = pd.DataFrame({"d": ["x", "y"], "v": [1, 2]})
    f = [{"column": "d", "op": "relative", "value": {"mode": "last", "unit": "day", "n": 7, "anchor": "data_max"}}]
    out, notes = resolve_filters(df, f)
    assert "no dates" in notes[0]["error"]
    assert _apply_filters(df, out).empty


def test_widget_result_carries_the_note_and_the_partial_month():
    df = _frame()
    cfg = {"dimension": "d", "dimension_granularity": "month", "measure": "v", "aggregation": "sum",
           "filters": [{"column": "d", "op": "relative",
                        "value": {"mode": "last", "unit": "month", "n": 2, "include_current": True,
                                  "anchor": "data_max"}}]}
    res = get_widget_data_from_df(df, cfg, "bar")
    assert [r["name"] for r in res["rows"]] == ["2026-08", "2026-09"]
    assert res["relative_dates"][0]["incomplete"] is True
    assert res["partial_period"]["label"] == "2026-09"
    assert res["partial_period"]["through"] == "2026-09-14"


def test_no_partial_flag_when_the_last_bucket_is_complete_or_not_shown():
    df = _frame()
    df = df[df["d"] <= "2026-08-31"]
    res = get_widget_data_from_df(df, {"dimension": "d", "dimension_granularity": "month",
                                       "measure": "v", "aggregation": "sum"}, "bar")
    assert "partial_period" not in res
    assert partial_period(_frame(), "d", "month", {"rows": [{"name": "2026-08"}]}) is None


def test_relative_is_an_accepted_report_filter_op():
    from app.routers.reports import _FILTER_OPS
    assert "relative" in _FILTER_OPS


def test_weekly_or_month_start_data_is_not_called_partial():
    weekly = pd.DataFrame({"d": pd.date_range("2025-01-05", "2025-12-28", freq="7D"), "v": 1.0})
    res = get_widget_data_from_df(weekly, {"dimension": "d", "dimension_granularity": "month",
                                           "measure": "v", "aggregation": "sum"}, "bar")
    assert "partial_period" not in res
    monthly = pd.DataFrame({"d": pd.date_range("2024-01-01", "2025-12-01", freq="MS"), "v": 1.0})
    res = get_widget_data_from_df(monthly, {"dimension": "d", "dimension_granularity": "month",
                                            "measure": "v", "aggregation": "sum"}, "bar")
    assert "partial_period" not in res
    # ...but weekly data three weeks short of a quarter's end still is
    res = get_widget_data_from_df(weekly[weekly["d"] <= "2025-12-07"],
                                  {"dimension": "d", "dimension_granularity": "quarter",
                                   "measure": "v", "aggregation": "sum"}, "bar")
    assert res["partial_period"]["label"] == "2025-Q4"


def test_this_month_on_weekly_data_ending_near_month_end_is_not_incomplete():
    weekly = pd.DataFrame({"d": pd.date_range("2025-01-05", "2025-12-28", freq="7D"), "v": 1.0})
    f = [{"column": "d", "op": "relative", "value": {"mode": "this", "unit": "month", "anchor": "data_max"}}]
    _, notes = resolve_filters(weekly, f)
    assert notes[0]["incomplete"] is False


def test_directquery_gets_a_plain_range_from_today_and_refuses_data_max():
    from fastapi import HTTPException
    from app.routers.widget_data import _direct_query_relative_dates
    from app.schemas.schemas import WidgetDataRequest
    req = WidgetDataRequest(widget_type="bar", config={"filters": [
        {"column": "d", "op": "relative", "value": {"mode": "last", "unit": "day", "n": 7, "anchor": "today"}},
        {"column": "r", "op": "eq", "value": "x"}]})
    out = _direct_query_relative_dates(req).config["filters"]
    assert [f["op"] for f in out] == ["gte", "lt", "eq"]
    bad = WidgetDataRequest(widget_type="bar", config={"filters": [
        {"column": "d", "op": "relative", "value": {"mode": "last", "unit": "day", "n": 7, "anchor": "data_max"}}]})
    with pytest.raises(HTTPException) as e:
        _direct_query_relative_dates(bad)
    assert "latest date" in str(e.value.detail)


def test_hijri_buckets_are_tabular_and_sort_as_text():
    from app.services.hijri import to_hijri
    d = pd.Series(pd.to_datetime(["2023-03-23", "2000-01-01", None]))
    y, m, day = to_hijri(d)
    assert (y[0], m[0], day[0]) == (1444, 9, 1)        # 1 Ramadan 1444
    assert (y[1], m[1], day[1]) == (1420, 9, 24)       # 24 Ramadan 1420
    assert y[2] == -1
    df = pd.DataFrame({"d": ["2023-03-23", "2023-03-24", "2023-04-25"], "v": [1.0, 2.0, 4.0]})
    res = get_widget_data_from_df(df, {"dimension": "d", "dimension_granularity": "hijri_month",
                                       "measure": "v", "aggregation": "sum"}, "bar")
    assert [(r["name"], r["value"]) for r in res["rows"]] == [("1444-09", 3.0), ("1444-10", 4.0)]
    yr = get_widget_data_from_df(df, {"dimension": "d", "dimension_granularity": "hijri_year",
                                      "measure": "v", "aggregation": "sum"}, "bar")
    assert yr["rows"] == [{"name": "1444", "value": 7.0}]
