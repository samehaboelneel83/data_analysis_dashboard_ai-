"""A chart with time on its x-axis should start in time order.

Found by photographing a hospital dashboard. "Arrivals by month" — a step chart
over `arrived_at` bucketed to months — drew its axis as:

    2024-12, 2025-01, 2026-01, 2025-12, 2025-02, 2025-11, 2025-04, 2024-11

Every value was correct. The chart was meaningless. The shaper defaults to
`sort_by=value, sort=desc`, which is exactly right for a ranking — the top ten
departments by cost — and exactly wrong for a series whose whole meaning is the
order of its axis. Nobody plots a trend and wants December before January.

The author can still ask for anything: an explicit `sort_by` is obeyed
unchanged, including `value` on a date, because "which month was busiest" is a
real question. This only changes what happens when nothing was said.
"""
import pandas as pd
import pytest

from app.services.widget_data import get_widget_data_from_df

MONTHS = ["2025-03", "2025-01", "2025-02", "2024-12", "2025-04"]


def frame():
    """Deliberately shuffled, with counts that disagree with the date order — so
    a value sort and a date sort cannot accidentally look the same."""
    rows = []
    for month, n in zip(MONTHS, [9, 3, 14, 5, 1]):
        for _ in range(n):
            rows.append({"arrived_at": pd.Timestamp(month + "-15"), "id": 1,
                         "department": "Cardiology"})
    return pd.DataFrame(rows)


def names(result):
    return [str(r["name"]) for r in result["rows"]]


class TestATimeDimension:
    def test_it_defaults_to_chronological_order(self):
        got = get_widget_data_from_df(frame(), {
            "dimension": "arrived_at", "measure": "id", "aggregation": "count",
            "dimension_granularity": "month"})
        assert names(got) == sorted(names(got)), names(got)

    def test_the_earliest_period_comes_first(self):
        got = get_widget_data_from_df(frame(), {
            "dimension": "arrived_at", "measure": "id", "aggregation": "count",
            "dimension_granularity": "month"})
        assert names(got)[0] == "2024-12", names(got)

    def test_a_raw_date_column_orders_too(self):
        """Not only when a granularity is applied — a date dimension with no
        bucketing is still an axis of time."""
        got = get_widget_data_from_df(frame(), {
            "dimension": "arrived_at", "measure": "id", "aggregation": "count"})
        assert names(got) == sorted(names(got)), names(got)


class TestTheAuthorStillDecides:
    def test_an_explicit_value_sort_is_obeyed(self):
        """"Which month was busiest" is a real question and must still work."""
        got = get_widget_data_from_df(frame(), {
            "dimension": "arrived_at", "measure": "id", "aggregation": "count",
            "dimension_granularity": "month", "sort_by": "value", "sort": "desc"})
        assert names(got)[0] == "2025-02", names(got)      # the 14-row month

    def test_an_explicit_descending_date_sort_is_obeyed(self):
        got = get_widget_data_from_df(frame(), {
            "dimension": "arrived_at", "measure": "id", "aggregation": "count",
            "dimension_granularity": "month", "sort_by": "name", "sort": "desc"})
        assert names(got) == sorted(names(got), reverse=True), names(got)


class TestEverythingElseIsUnchanged:
    def test_a_categorical_dimension_still_ranks_by_value(self):
        """The default that makes a top-ten chart useful must not move."""
        df = pd.DataFrame({"department": ["A", "B", "C"] * 3 + ["B", "B"],
                           "id": 1})
        got = get_widget_data_from_df(df, {
            "dimension": "department", "measure": "id", "aggregation": "count"})
        assert names(got)[0] == "B", names(got)

    def test_a_numeric_dimension_still_ranks_by_value(self):
        df = pd.DataFrame({"age_years": [30, 40, 40, 40, 50, 50], "id": 1})
        got = get_widget_data_from_df(df, {
            "dimension": "age_years", "measure": "id", "aggregation": "count"})
        assert got["rows"][0]["name"] == 40, names(got)


class TestTimeStoredAsText:
    """A CSV-loaded `month` column is text ("2024-07"), not a pandas datetime.
    Found building "count by month" as a line in the browser: the axis read
    2024-07, 2024-08, 2024-11, 2025-02 ... -- ranked by count."""

    def text_frame(self):
        rows = []
        for month, n in zip(MONTHS, [9, 3, 14, 5, 1]):
            rows += [{"month": month, "id": 1}] * n
        return pd.DataFrame(rows)

    def test_iso_month_text_orders_chronologically(self):
        got = get_widget_data_from_df(self.text_frame(), {
            "dimension": "month", "measure": "id", "aggregation": "count"})
        assert names(got) == sorted(MONTHS), names(got)

    def test_the_panels_stamped_desc_does_not_reverse_time(self):
        """The settings panel writes sort=desc on every save; with no sort_by
        stated that is its default, not the author's choice."""
        got = get_widget_data_from_df(self.text_frame(), {
            "dimension": "month", "measure": "id", "aggregation": "count", "sort": "desc"})
        assert names(got)[0] == "2024-12", names(got)

    def test_an_explicit_value_sort_on_text_months_is_obeyed(self):
        got = get_widget_data_from_df(self.text_frame(), {
            "dimension": "month", "measure": "id", "aggregation": "count",
            "sort_by": "value", "sort": "desc"})
        assert names(got)[0] == "2025-02", names(got)

    def test_unpadded_labels_do_not_qualify(self):
        """'2024-7' sorts after '2024-10' as text; a wrong time order is worse
        than a value order, so these keep ranking by value."""
        df = pd.DataFrame({"m": ["2024-7"] * 5 + ["2024-10"] * 2 + ["2024-9"] * 9, "id": 1})
        got = get_widget_data_from_df(df, {"dimension": "m", "measure": "id", "aggregation": "count"})
        assert names(got)[0] == "2024-9", names(got)

    def test_quarter_and_week_labels_qualify(self):
        df = pd.DataFrame({"q": ["2025-Q2"] * 5 + ["2025-Q1"] * 1 + ["2024-Q4"] * 3, "id": 1})
        got = get_widget_data_from_df(df, {"dimension": "q", "measure": "id", "aggregation": "count"})
        assert names(got) == ["2024-Q4", "2025-Q1", "2025-Q2"], names(got)

    def test_ordinary_text_is_untouched(self):
        df = pd.DataFrame({"region": ["Europe"] * 2 + ["Asia"] * 5, "id": 1})
        got = get_widget_data_from_df(df, {"dimension": "region", "measure": "id", "aggregation": "count"})
        assert names(got)[0] == "Asia", names(got)


class TestDirectQueryTimeAxis:
    """Same rule on the SQL path, where order is decided by ORDER BY."""

    def ds(self, dtype):
        from types import SimpleNamespace as NS
        return NS(columns=[NS(name="month", dtype=dtype), NS(name="region", dtype="categorical")])

    def test_a_datetime_dimension_orders_by_time_ascending(self):
        from app.services.direct_query import plan_query, _time_axis_default
        cfg = {"dimension": "month", "measure": "revenue", "aggregation": "sum", "sort": "desc"}
        plan = _time_axis_default(plan_query(cfg, "line"), cfg, self.ds("datetime"))
        assert plan.sort_by_dim and not plan.sort_desc

    def test_an_explicit_sort_by_is_obeyed(self):
        from app.services.direct_query import plan_query, _time_axis_default
        cfg = {"dimension": "month", "measure": "revenue", "aggregation": "sum", "sort_by": "value"}
        plan = _time_axis_default(plan_query(cfg, "line"), cfg, self.ds("datetime"))
        assert not plan.sort_by_dim

    def test_a_category_still_ranks(self):
        from app.services.direct_query import plan_query, _time_axis_default
        cfg = {"dimension": "region", "measure": "revenue", "aggregation": "sum"}
        plan = _time_axis_default(plan_query(cfg, "bar"), cfg, self.ds("datetime"))
        assert not plan.sort_by_dim and plan.sort_desc
