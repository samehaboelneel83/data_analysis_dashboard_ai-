"""Each axis of a dual-axis chart gets its own aggregation.

The reason a chart has two axes is that its two numbers are not the same KIND of
number. "Volume and average wait by department" is the canonical example, and it
was impossible to build: one `aggregation` was applied to both measures, so the
author could have a count of encounters and a count of wait minutes, or an
average of each, but never the pairing the chart exists for.

Found while building an emergency-department dashboard, where the widget titled
"Volume and wait by department" could carry only the wait.

`aggregation2` defaults to `aggregation`, so every chart already saved keeps the
numbers it has.
"""
import pandas as pd

from app.services.widget_data import get_widget_data_from_df

DUAL = "dual_axis_bar_line"


def frame():
    """Three encounters in Cardiology, one in ENT — so a count and an average
    disagree, and cannot be confused for one another."""
    return pd.DataFrame({
        "department": ["Cardiology", "Cardiology", "Cardiology", "ENT"],
        "encounter_id": [1, 2, 3, 4],
        "wait_minutes": [30, 60, 90, 10],
    })


def by_name(result):
    return {r["name"]: r for r in result["rows"]}


class TestTwoAggregations:
    CFG = {"dimension": "department", "measure": "encounter_id",
           "aggregation": "count", "measure2": "wait_minutes",
           "aggregation2": "avg"}

    def test_the_first_measure_uses_the_first_aggregation(self):
        got = by_name(get_widget_data_from_df(frame(), self.CFG, DUAL))
        assert got["Cardiology"]["value"] == 3          # a count of encounters

    def test_the_second_measure_uses_the_second(self):
        got = by_name(get_widget_data_from_df(frame(), self.CFG, DUAL))
        assert got["Cardiology"]["value2"] == 60        # mean of 30, 60, 90

    def test_both_are_reported_for_every_category(self):
        got = by_name(get_widget_data_from_df(frame(), self.CFG, DUAL))
        assert got["ENT"]["value"] == 1 and got["ENT"]["value2"] == 10

    def test_one_column_can_carry_two_aggregations(self):
        """"Total and average cost" is one column read two ways -- the dedupe
        that protects measure == measure2 must not collapse it to one number."""
        got = by_name(get_widget_data_from_df(frame(), {
            "dimension": "department", "measure": "wait_minutes", "aggregation": "sum",
            "measure2": "wait_minutes", "aggregation2": "avg"}, DUAL))
        assert got["Cardiology"]["value"] == 180
        assert got["Cardiology"]["value2"] == 60


class TestTheOldBehaviourIsIntact:
    def test_omitting_the_second_aggregation_reuses_the_first(self):
        """Every dual-axis chart saved before this existed must not move."""
        got = by_name(get_widget_data_from_df(frame(), {
            "dimension": "department", "measure": "encounter_id",
            "measure2": "wait_minutes", "aggregation": "sum"}, DUAL))
        assert got["Cardiology"]["value"] == 6          # 1 + 2 + 3
        assert got["Cardiology"]["value2"] == 180       # 30 + 60 + 90

    def test_a_single_measure_still_works(self):
        got = by_name(get_widget_data_from_df(frame(), {
            "dimension": "department", "measure": "wait_minutes",
            "aggregation": "avg"}, DUAL))
        assert got["Cardiology"]["value"] == 60
        assert "value2" not in got["Cardiology"]

    def test_the_measure_names_are_still_reported(self):
        got = get_widget_data_from_df(frame(), TestTwoAggregations.CFG, DUAL)
        assert got["measure"] == "encounter_id"
        assert got["measure2"] == "wait_minutes"
