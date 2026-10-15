"""C-24: a dual-axis time series over a DAILY date shows the whole range by
default (it showed the first 50 of 633 days), bucketed to a coarser grain."""
import pandas as pd

from app.services.widget_data import get_widget_data_from_df

DAYS = pd.date_range("2024-01-01", periods=633, freq="D")
DF = pd.DataFrame({"date": DAYS, "revenue": range(633), "units": [1] * 633})


def test_daily_dates_are_bucketed_to_cover_the_whole_range():
    r = get_widget_data_from_df(DF, {"dimension": "date", "measure": "revenue", "measure2": "units"},
                                "dual_axis_time_series")
    rows = r["rows"]
    assert len(rows) <= 120
    assert r.get("auto_granularity") in ("week", "month")
    assert str(rows[0]["name"]).startswith("2024")
    assert str(rows[-1]["name"]).startswith("2025-09") or str(rows[-1]["name"]).startswith("2025-W")
    assert sum(x["value2"] for x in rows) == 633          # every day counted once
    assert not (r.get("truncation") or {}).get("applied")


def test_an_authors_granularity_or_limit_still_wins():
    r = get_widget_data_from_df(DF, {"dimension": "date", "measure": "revenue", "measure2": "units",
                                     "dimension_granularity": "day", "limit": 700}, "dual_axis_time_series")
    assert len(r["rows"]) == 633 and "auto_granularity" not in r


def test_a_short_daily_series_is_left_daily():
    df = DF.head(40)
    r = get_widget_data_from_df(df, {"dimension": "date", "measure": "revenue", "measure2": "units"},
                                "dual_axis_time_series")
    assert len(r["rows"]) == 40 and "auto_granularity" not in r
