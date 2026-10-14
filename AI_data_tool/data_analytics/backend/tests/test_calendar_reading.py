"""Calendar readings: weekday and month-of-year date parts, one date on both
sides of a chart, and the cards that offer them (docs/discovery/PLAN.md §N-1)."""
import numpy as np
import pandas as pd

from app.services import widget_data as wd
from app.services.discovery import engine, profile as store


def events(start="2023-01-01", end="2025-06-30 23:00", freq="h", seed=4):
    rng = np.random.default_rng(seed)
    when = pd.date_range(start, end, freq=freq)
    # More on Thursday mornings: the planted habit.
    busy = (when.dayofweek == 3) & (when.hour == 9)
    amount = np.where(busy, 50.0, 1.0) + rng.random(len(when))
    return pd.DataFrame({"when": when, "amount": amount, "kind": rng.choice(["a", "b"], len(when))})


def test_weekday_and_month_labels_sort_in_calendar_order_and_skip_missing():
    s = pd.Series(pd.to_datetime(["2025-01-06", "2025-03-09", None, "2025-12-25"]))
    assert wd._dimension_granularity_label(s, "weekday").tolist()[:2] == ["1 Mon", "7 Sun"]
    assert wd._dimension_granularity_label(s, "month_of_year").tolist()[3] == "12 Dec"
    assert wd._dimension_granularity_label(s, "weekday").isna().tolist() == [False, False, True, False]
    assert sorted(wd._WEEKDAYS) == list(wd._WEEKDAYS) and sorted(wd._MONTHS) == list(wd._MONTHS)
    assert wd._bucket_grain("4 Thu") == "weekday" and wd._bucket_grain("03 Mar") == "month_of_year"
    assert wd._bucket_grain("09") == "hour_of_day"


def test_one_date_on_both_sides_of_a_grid_weekday_by_hour():
    df = events()
    out = wd.get_widget_data_from_df(df, {
        "dimension": "when", "dimension_granularity": "weekday",
        "dimension2": "when", "dimension2_granularity": "hour_of_day",
        "measure": "amount", "aggregation": "sum"}, "heatmap")
    assert out["type"] == "heatmap"
    assert out["rows_axis"] == list(wd._WEEKDAYS) and out["cols_axis"] == [f"{h:02d}" for h in range(24)]
    cells = np.array(out["cells"], dtype=float)
    r, c = np.unravel_index(np.nanargmax(cells), cells.shape)
    assert (out["rows_axis"][r], out["cols_axis"][c]) == ("4 Thu", "09")


def test_hours_with_no_rows_stay_on_the_grid():
    df = events()
    df = df[df["when"].dt.hour.between(8, 17)]
    out = wd.get_widget_data_from_df(df, {
        "dimension": "when", "dimension_granularity": "weekday",
        "dimension2": "when", "dimension2_granularity": "hour_of_day",
        "measure": "amount", "aggregation": "sum"}, "heatmap")
    assert len(out["cols_axis"]) == 24 and out["cells"][0][0] is None


def test_each_year_over_the_months_is_one_line_per_year():
    out = wd.get_widget_data_from_df(events(freq="D"), {
        "dimension": "when", "dimension_granularity": "month_of_year",
        "dimension2": "when", "dimension2_granularity": "year",
        "measure": "amount", "aggregation": "sum"}, "line")
    assert out["type"] == "crosstab" and out["columns"][:4] == ["when", "2023", "2024", "2025"]
    assert [r[0] for r in out["rows"]] == list(wd._MONTHS)
    # 2025 stops in June: the later months are empty for it, not zero.
    assert out["rows"][5][3] is not None and out["rows"][6][3] is None and out["rows"][11][3] is None
    assert out["rows"][11][1] is not None


def test_a_second_grain_on_a_column_without_dates_changes_nothing():
    df = events()
    same, cfg = wd.second_grain(df, {"dimension2": "kind", "dimension2_granularity": "year"})
    assert cfg["dimension2"] == "kind" and list(same.columns) == list(df.columns)


META = {}


def cards_for(df):
    prof = store.compute(df)
    return {c["title"]: c for c in engine.tier0(prof, META)["cards"]
            if c["action"].get("config", {}).get("dimension2_granularity")}


def test_timed_dates_over_years_get_all_three_calendar_cards():
    got = cards_for(events())
    assert len(got) == 4
    grid = next(c for c in got.values() if c["action"]["config"]["dimension2_granularity"] == "hour_of_day")
    assert grid["action"]["widget_type"] == "heatmap" and grid["action"]["config"]["dimension_granularity"] == "weekday"
    assert grid["family"] == "trend" and grid["evidence"] is None      # offered, not claimed
    assert any("time zone" in l for l in grid["limits"])


def test_dates_without_a_time_of_day_get_no_hour_grid():
    got = cards_for(events(freq="D"))
    assert {c["action"]["config"]["dimension2_granularity"] for c in got.values()} == {"year", "month_of_year"}


def test_one_year_of_dates_is_not_compared_year_against_year():
    got = cards_for(events(start="2025-01-01", end="2025-06-30 23:00"))
    assert [c["action"]["config"]["dimension2_granularity"] for c in got.values()] == ["hour_of_day"]


def test_three_weeks_are_not_a_weekly_habit():
    assert cards_for(events(start="2025-06-01", end="2025-06-20 23:00")) == {}


def test_every_calendar_card_draws():
    df = events()
    for card in cards_for(df).values():
        out = wd.get_widget_data_from_df(df, card["action"]["config"], card["action"]["widget_type"])
        assert out.get("type") in ("heatmap", "series", "crosstab", "grid"), (card["title"], out.get("type"), out.get("message"))


def test_many_years_get_the_grid_but_not_a_line_per_year():
    got = cards_for(events(start="2010-01-01", end="2025-06-30", freq="D"))
    assert [c["action"]["widget_type"] for c in got.values()] == ["bar", "heatmap"]


def test_the_last_two_years_month_against_month():
    df = events(start="2021-01-01", end="2025-06-30", freq="D")
    card = next(c for c in cards_for(df).values() if c["action"]["widget_type"] == "bar")
    cfg = card["action"]["config"]
    assert cfg["filters"][0]["value"] == {"mode": "last", "unit": "year", "n": 2, "include_current": True, "anchor": "data_max"}
    out = wd.get_widget_data_from_df(df, cfg, "bar")
    assert out["type"] == "crosstab" and out["columns"][1:3] == ["2024", "2025"], out.get("message")
    assert [r[0] for r in out["rows"]] == list(wd._MONTHS)
    assert out["rows"][11][1] is not None and out["rows"][11][2] is None      # December 2025 has not happened


def test_the_month_the_data_stops_inside_is_not_set_beside_a_whole_one():
    df = events(start="2023-01-01", end="2025-06-12", freq="D")
    out = wd.get_widget_data_from_df(df, {
        "dimension": "when", "dimension_granularity": "month_of_year",
        "dimension2": "when", "dimension2_granularity": "year", "measure": "amount", "aggregation": "sum"}, "bar")
    june = out["rows"][5]
    assert june[1] is not None and june[2] is not None and june[3] is None     # 2025's twelve days of June: left out
    assert out["rows"][4][3] is not None                                        # May 2025 is whole
    assert out["partial_period"]["dropped"] is True and out["partial_period"]["label"] == "2025-06"
