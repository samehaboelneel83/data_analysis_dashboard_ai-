"""Proposing a dashboard for an existing dataset, for a named kind of person.

The model chooses the charts. That is the point of the feature -- a generic rule
("one KPI, one trend, one breakdown") produces the same dashboard for a hospital
and a bookshop, and neither person wanted it. What the model must NOT be allowed
to do is propose something that renders blank, and it will: an LLM handed 64
widget types binds a bubble chart to one measure and a map to a dataset with no
coordinates.

So every proposed widget passes three gates before a human sees it:

  1. the menu it chose from was already filtered by what this data supports
  2. the config is checked against the widget's required roles and the real
     column list
  3. it is EXECUTED, and dropped if the shaper says it has nothing to draw

Gate 3 is the one that matters most, and is the direct lesson of an exhaustive
test where 92 widgets "passed" a check that never ran the renderer.
"""
import pandas as pd
import pytest

from app.services.dataset_profile import build_profile
from app.services.suggest_dataset_dashboard import (
    build_messages, polish_widget, usable_widgets, validate_widget,
    suggest_for_dataset,
)


def hospital_df():
    return pd.DataFrame({
        "encounter_id": range(1, 61),
        "department": ["Cardiology", "ENT", "Oncology"] * 20,
        "wait_minutes": [30, 60, 90] * 20,
        "total_cost": [1200, 900, 4300] * 20,
        "arrived_at": pd.date_range("2024-01-01", periods=60, freq="W"),
        "patient_email": ["a@b.com"] * 60,
    })


def geo_df():
    df = hospital_df()
    df["site_lat"] = 30.05
    df["site_lon"] = 31.24
    return df


@pytest.fixture
def profile():
    return build_profile(hospital_df())


class TestTheMenuFitsTheData:
    def test_maps_are_not_offered_without_coordinates(self, profile):
        assert not [w for w in usable_widgets(profile) if w.startswith("map_")]

    def test_maps_are_offered_when_coordinates_exist(self):
        got = usable_widgets(build_profile(geo_df()))
        assert "map_points" in got

    def test_time_widgets_are_not_offered_without_a_date(self):
        flat = build_profile(pd.DataFrame({"a": ["x", "y"], "n": [1, 2]}))
        assert "dual_axis_time_series" not in usable_widgets(flat)

    def test_the_plain_shapes_are_always_offered(self, profile):
        for wt in ("bar", "line", "kpi", "table", "pie"):
            assert wt in usable_widgets(profile)

    def test_an_org_chart_needs_a_reference_hierarchy(self, profile):
        assert "org" not in usable_widgets(profile)


class TestValidation:
    def test_a_good_widget_passes(self, profile):
        ok, why = validate_widget(
            {"widget_type": "bar", "title": "Wait by department",
             "config": {"dimension": "department", "measure": "wait_minutes",
                        "aggregation": "avg"}}, profile)
        assert ok, why

    def test_an_invented_column_is_refused(self, profile):
        ok, why = validate_widget(
            {"widget_type": "bar", "title": "x",
             "config": {"dimension": "ward", "measure": "wait_minutes",
                        "aggregation": "avg"}}, profile)
        assert not ok and "ward" in why

    def test_a_missing_required_role_is_refused(self, profile):
        """The blank-tile bug, caught before anybody sees the tile."""
        ok, why = validate_widget(
            {"widget_type": "bubble", "title": "x",
             "config": {"dimension": "department", "measure": "wait_minutes"}},
            profile)
        assert not ok and "measure2" in why and "size" in why

    def test_summing_an_identifier_is_refused(self, profile):
        ok, why = validate_widget(
            {"widget_type": "bar", "title": "x",
             "config": {"dimension": "department", "measure": "encounter_id",
                        "aggregation": "sum"}}, profile)
        assert not ok and "encounter_id" in why

    def test_counting_an_identifier_is_fine(self, profile):
        """Counting encounters is the most useful thing this dataset does."""
        ok, why = validate_widget(
            {"widget_type": "bar", "title": "x",
             "config": {"dimension": "department", "measure": "encounter_id",
                        "aggregation": "count"}}, profile)
        assert ok, why

    def test_personal_data_is_refused_as_a_dimension(self, profile):
        ok, why = validate_widget(
            {"widget_type": "pie", "title": "x",
             "config": {"dimension": "patient_email", "measure": "wait_minutes",
                        "aggregation": "avg"}}, profile)
        assert not ok and "patient_email" in why

    def test_a_widget_type_the_data_cannot_support_is_refused(self, profile):
        ok, why = validate_widget(
            {"widget_type": "map_points", "title": "x",
             "config": {"lat": "wait_minutes", "lon": "wait_minutes"}}, profile)
        assert not ok

    def test_an_unknown_aggregation_is_refused(self, profile):
        ok, why = validate_widget(
            {"widget_type": "bar", "title": "x",
             "config": {"dimension": "department", "measure": "wait_minutes",
                        "aggregation": "median_of_medians"}}, profile)
        assert not ok


class TestAHeadlineNumberNeedsSomethingToCount:
    """Observed live: after the dimension was dropped from a KPI, the model had
    given it no measure either, leaving `{"aggregation": "median"}` -- a median
    of nothing. The shaper answered with a 50-row table and the renderer showed
    the first row. A headline figure with no measure is not a headline figure."""

    def test_a_kpi_without_a_measure_is_refused(self, profile):
        ok, why = validate_widget(
            {"widget_type": "kpi", "title": "Median wait",
             "config": {"dimension": "department", "aggregation": "median"}}, profile)
        assert not ok and "measure" in why

    def test_a_gauge_without_a_measure_is_refused(self, profile):
        ok, why = validate_widget(
            {"widget_type": "gauge", "title": "x", "config": {"aggregation": "avg"}},
            profile)
        assert not ok and "measure" in why

    def test_a_kpi_with_one_is_accepted(self, profile):
        ok, why = validate_widget(
            {"widget_type": "kpi", "title": "Median wait",
             "config": {"dimension": "department", "measure": "wait_minutes",
                        "aggregation": "median"}}, profile)
        assert ok, why

    def test_a_bar_chart_may_still_count_rows(self, profile):
        """Only the headline types need one -- `count` with no measure is a
        legitimate bar chart of row counts per category."""
        ok, why = validate_widget(
            {"widget_type": "bar", "title": "Encounters by department",
             "config": {"dimension": "department", "aggregation": "count"}}, profile)
        assert ok, why


class TestTheKpiContradiction:
    """The prompt told the model a KPI must have NO dimension. The validator,
    reading ROLE_SPECS, demanded one. Every KPI the model proposed was therefore
    discarded -- three dashboards came back with no headline number at all.

    ROLE_SPECS describes the config PANEL's field list. The shaper needs no
    dimension for a KPI and the product's own demo content omits it."""

    def test_a_kpi_with_no_dimension_is_accepted(self, profile):
        ok, why = validate_widget(
            {"widget_type": "kpi", "title": "Median wait",
             "config": {"measure": "wait_minutes", "aggregation": "median"}}, profile)
        assert ok, why

    def test_a_gauge_with_no_dimension_is_accepted(self, profile):
        ok, why = validate_widget(
            {"widget_type": "gauge", "title": "Occupancy",
             "config": {"measure": "wait_minutes", "aggregation": "avg"}}, profile)
        assert ok, why

    def test_a_bar_chart_still_needs_its_dimension(self, profile):
        ok, why = validate_widget(
            {"widget_type": "bar", "title": "x",
             "config": {"measure": "wait_minutes", "aggregation": "avg"}}, profile)
        assert not ok and "dimension" in why


class TestAggregationSynonyms:
    """The model writes `average`; the engine spells it `avg`. Six good widgets
    were thrown away over that in one live run. A synonym is not a mistake worth
    discarding a chart for."""

    def test_average_becomes_avg(self, profile):
        got = polish_widget(
            {"widget_type": "bar", "title": "x",
             "config": {"dimension": "department", "measure": "wait_minutes",
                        "aggregation": "average"}}, profile)
        assert got["config"]["aggregation"] == "avg"

    def test_mean_becomes_avg(self, profile):
        got = polish_widget(
            {"widget_type": "bar", "title": "x",
             "config": {"dimension": "department", "measure": "wait_minutes",
                        "aggregation": "mean"}}, profile)
        assert got["config"]["aggregation"] == "avg"

    def test_total_becomes_sum(self, profile):
        got = polish_widget(
            {"widget_type": "bar", "title": "x",
             "config": {"dimension": "department", "measure": "total_cost",
                        "aggregation": "total"}}, profile)
        assert got["config"]["aggregation"] == "sum"

    def test_a_second_aggregation_is_normalised_too(self, profile):
        got = polish_widget(
            {"widget_type": "dual_axis_bar_line", "title": "x",
             "config": {"dimension": "department", "measure": "encounter_id",
                        "aggregation": "count", "measure2": "wait_minutes",
                        "aggregation2": "average"}}, profile)
        assert got["config"]["aggregation2"] == "avg"

    def test_a_synonym_passes_validation(self, profile):
        """Normalisation has to happen before the check, or the widget is
        discarded before anything gets the chance to fix it."""
        ok, why = validate_widget(
            {"widget_type": "bar", "title": "x",
             "config": {"dimension": "department", "measure": "wait_minutes",
                        "aggregation": "average"}}, profile)
        assert ok, why

    def test_a_real_nonsense_aggregation_is_still_refused(self, profile):
        ok, why = validate_widget(
            {"widget_type": "bar", "title": "x",
             "config": {"dimension": "department", "measure": "wait_minutes",
                        "aggregation": "median_of_medians"}}, profile)
        assert not ok


class TestPolish:
    def test_a_date_dimension_gets_a_granularity(self, profile):
        got = polish_widget(
            {"widget_type": "line", "title": "x",
             "config": {"dimension": "arrived_at", "measure": "encounter_id",
                        "aggregation": "count"}}, profile)
        assert got["config"]["dimension_granularity"] == \
            profile["structure"]["date_range"]["granularity"]

    def test_a_granularity_the_model_chose_is_kept(self, profile):
        got = polish_widget(
            {"widget_type": "line", "title": "x",
             "config": {"dimension": "arrived_at", "measure": "encounter_id",
                        "aggregation": "count", "dimension_granularity": "year"}},
            profile)
        assert got["config"]["dimension_granularity"] == "year"

    def test_a_non_date_dimension_gets_none(self, profile):
        got = polish_widget(
            {"widget_type": "bar", "title": "x",
             "config": {"dimension": "department", "measure": "wait_minutes",
                        "aggregation": "avg"}}, profile)
        assert "dimension_granularity" not in got["config"]

    def test_a_high_cardinality_dimension_gets_a_limit(self):
        df = pd.DataFrame({"patient": [f"p{i}" for i in range(500)],
                           "cost": range(500)})
        prof = build_profile(df)
        got = polish_widget(
            {"widget_type": "bar", "title": "x",
             "config": {"dimension": "patient", "measure": "cost",
                        "aggregation": "sum"}}, prof)
        assert got["config"]["limit"] <= 20


class TestAHeadlineNumberIsTheWholeDatasets:
    """A KPI with a dimension shows ONE GROUP'S value under a headline label.

    Observed live: the model proposed "Current Median Wait Time" as a KPI over
    `department`, and the renderer -- which reads `rows[0].value` -- displayed
    62.0, the median wait in Laboratory Medicine. The real median across 120,000
    encounters is 60.0. Nothing on the tile said which of the two it was.

    The product's own demo content builds KPIs with no dimension at all, which
    makes the shaper return a scalar over every row. That is the shape a headline
    number has to have.
    """

    def test_a_kpi_loses_its_dimension(self, profile):
        got = polish_widget(
            {"widget_type": "kpi", "title": "Median wait",
             "config": {"dimension": "department", "measure": "wait_minutes",
                        "aggregation": "median"}}, profile)
        assert "dimension" not in got["config"]

    def test_a_gauge_loses_its_dimension_too(self, profile):
        got = polish_widget(
            {"widget_type": "gauge", "title": "Occupancy",
             "config": {"dimension": "department", "measure": "wait_minutes",
                        "aggregation": "avg"}}, profile)
        assert "dimension" not in got["config"]

    def test_the_measure_and_aggregation_survive(self, profile):
        got = polish_widget(
            {"widget_type": "kpi", "title": "Median wait",
             "config": {"dimension": "department", "measure": "wait_minutes",
                        "aggregation": "median"}}, profile)
        assert got["config"]["measure"] == "wait_minutes"
        assert got["config"]["aggregation"] == "median"

    def test_a_bar_chart_keeps_its_dimension(self, profile):
        got = polish_widget(
            {"widget_type": "bar", "title": "Wait by department",
             "config": {"dimension": "department", "measure": "wait_minutes",
                        "aggregation": "avg"}}, profile)
        assert got["config"]["dimension"] == "department"


class TestACategoryAxisStaysReadable:
    """26 departments in a half-width tile is not a chart.

    Photographed from a generated dashboard: "Queue Depth by Department" drew 26
    bars with their names rotated into an unreadable band, and one bar so much
    taller than the rest that the other 25 were a flat line. The high-cardinality
    rule did not fire, because 26 is not high cardinality -- it is simply more
    categories than a bar chart can label.

    Top-12-by-value is the ordinary BI default, and the author can raise it.
    """

    def cfg(self, n):
        import pandas as pd
        df = pd.DataFrame({"dept": [f"d{i}" for i in range(n)] * 3,
                           "cost": range(n * 3)})
        from app.services.dataset_profile import build_profile
        return build_profile(df)

    def test_a_bar_chart_over_many_categories_is_capped(self):
        got = polish_widget(
            {"widget_type": "bar", "title": "x",
             "config": {"dimension": "dept", "measure": "cost", "aggregation": "sum"}},
            self.cfg(26))
        assert got["config"]["limit"] == 12

    def test_a_handful_of_categories_is_left_alone(self):
        got = polish_widget(
            {"widget_type": "bar", "title": "x",
             "config": {"dimension": "dept", "measure": "cost", "aggregation": "sum"}},
            self.cfg(6))
        assert "limit" not in got["config"]

    def test_a_limit_the_model_chose_is_kept(self):
        got = polish_widget(
            {"widget_type": "bar", "title": "x",
             "config": {"dimension": "dept", "measure": "cost",
                        "aggregation": "sum", "limit": 30}}, self.cfg(26))
        assert got["config"]["limit"] == 30

    def test_a_table_is_not_capped(self):
        """A table is a list on purpose; truncating it to twelve hides rows the
        reader came for."""
        got = polish_widget(
            {"widget_type": "table", "title": "x",
             "config": {"dimension": "dept", "measure": "cost", "aggregation": "sum"}},
            self.cfg(26))
        assert got["config"].get("limit") != 12

    def test_a_time_axis_is_not_capped(self, profile):
        """Twelve months out of a two-year trend is not a trend."""
        got = polish_widget(
            {"widget_type": "line", "title": "x",
             "config": {"dimension": "arrived_at", "measure": "encounter_id",
                        "aggregation": "count"}}, profile)
        assert got["config"].get("limit") != 12


class TestAFieldMustNameAColumn:
    """A role slot holds a COLUMN NAME. Observed live: a gauge arrived with
    `target: 20`, meaning "the goal is 20". The engine reads `target` as a role,
    looked for a column called 20, found none, and dropped it -- so the tile drew
    with no target at all and nothing said so. Refusing it sends the model back
    with a specific complaint instead."""

    def test_a_number_where_a_column_belongs_is_refused(self, profile):
        ok, why = validate_widget(
            {"widget_type": "gauge", "title": "Abnormal rate",
             "config": {"measure": "wait_minutes", "aggregation": "avg",
                        "target": 20}}, profile)
        assert not ok and "target" in why

    def test_a_column_name_is_accepted(self, profile):
        ok, why = validate_widget(
            {"widget_type": "gauge", "title": "x",
             "config": {"measure": "wait_minutes", "aggregation": "avg",
                        "target": "total_cost"}}, profile)
        assert ok, why

    def test_settings_may_still_be_numbers(self, profile):
        """`limit` is a number and always was."""
        ok, why = validate_widget(
            {"widget_type": "bar", "title": "x",
             "config": {"dimension": "department", "measure": "wait_minutes",
                        "aggregation": "avg", "limit": 10}}, profile)
        assert ok, why


@pytest.mark.asyncio
class TestAScalarIsOneNumberNotNothing:
    async def test_a_scalar_widget_reports_one_row(self, profile):
        """A gauge answers with `value`, no rows. Reporting "0 rows" next to it
        in the panel reads as an empty tile when it is a working one."""
        async def probe(widget_type, config):
            return {"type": "gauge", "measure": "wait_minutes", "value": 466948}
        got, _ = await suggest_for_dataset(
            profile, None, 1, probe=probe,
            client=_client_returning({"widget_type": "gauge", "title": "Rate",
                                      "why": "x",
                                      "config": {"measure": "wait_minutes",
                                                 "aggregation": "avg"}}))
        assert got[0]["widgets"][0]["row_count"] == 1


def _client_returning(widget):
    class C:
        async def complete_json(self, messages, schema, **kw):
            return {"proposals": [{"title": "t", "rationale": "r",
                                   "widgets": [widget]}]}
    return C()


class TestCountingAFlagIsNeverTheRate:
    """Live, twice in one answer: "Abnormal Rate by Branch" configured as `count`
    of `abnormal_flag`. `count` counts rows, so that tile would have shown
    466,948 -- every lab result there has ever been -- under the word "Rate"."""

    def flagged(self):
        import pandas as pd
        from app.services.dataset_profile import build_profile
        return build_profile(pd.DataFrame({
            "dept": ["A", "B"] * 30, "died": [0, 1] * 30,
            "cost": range(60)}))

    def test_counting_a_flag_is_refused(self):
        ok, why = validate_widget(
            {"widget_type": "bar", "title": "Mortality rate",
             "config": {"dimension": "dept", "measure": "died",
                        "aggregation": "count"}}, self.flagged())
        assert not ok and "avg" in why

    def test_averaging_a_flag_is_the_rate_and_is_accepted(self):
        ok, why = validate_widget(
            {"widget_type": "bar", "title": "Mortality rate",
             "config": {"dimension": "dept", "measure": "died",
                        "aggregation": "avg"}}, self.flagged())
        assert ok, why

    def test_summing_a_flag_is_accepted(self):
        """The number of deaths is a legitimate question; only `count` is wrong,
        because it ignores the flag entirely."""
        ok, why = validate_widget(
            {"widget_type": "bar", "title": "Deaths",
             "config": {"dimension": "dept", "measure": "died",
                        "aggregation": "sum"}}, self.flagged())
        assert ok, why

    def test_counting_a_real_measure_is_untouched(self):
        ok, why = validate_widget(
            {"widget_type": "bar", "title": "x",
             "config": {"dimension": "dept", "measure": "cost",
                        "aggregation": "count"}}, self.flagged())
        assert ok, why


class TestFilters:
    """The engine narrows a chart with `filters`; the prompt never said so.

    Live consequence: a lab dataset whose `abnormal_flag` holds H / L / N, and a
    model that wanted "the abnormal rate". With no filter vocabulary it reached
    for SQL and wrote `abnormal_flag IN ('H', 'L')` into a field where a column
    name belongs. Six widgets were discarded over it in one answer -- all six
    were sensible charts the engine can draw.
    """

    def test_a_filter_on_a_real_column_is_accepted(self, profile):
        ok, why = validate_widget(
            {"widget_type": "bar", "title": "Long waits by department",
             "config": {"dimension": "department", "measure": "encounter_id",
                        "aggregation": "count",
                        "filters": [{"column": "wait_minutes", "op": "gt",
                                     "value": 60}]}}, profile)
        assert ok, why

    def test_a_filter_on_an_invented_column_is_refused(self, profile):
        ok, why = validate_widget(
            {"widget_type": "bar", "title": "x",
             "config": {"dimension": "department", "measure": "encounter_id",
                        "aggregation": "count",
                        "filters": [{"column": "ward", "op": "eq",
                                     "value": "A"}]}}, profile)
        assert not ok and "ward" in why

    def test_an_unknown_operator_is_refused(self, profile):
        ok, why = validate_widget(
            {"widget_type": "bar", "title": "x",
             "config": {"dimension": "department", "measure": "encounter_id",
                        "aggregation": "count",
                        "filters": [{"column": "department", "op": "regex",
                                     "value": "x"}]}}, profile)
        assert not ok and "regex" in why

    def test_an_in_filter_takes_a_list(self, profile):
        ok, why = validate_widget(
            {"widget_type": "bar", "title": "x",
             "config": {"dimension": "department", "measure": "encounter_id",
                        "aggregation": "count",
                        "filters": [{"column": "department", "op": "in",
                                     "value": ["Cardiology", "ENT"]}]}}, profile)
        assert ok, why

    def test_the_prompt_explains_them(self, profile):
        blob = " ".join(m["content"] for m in build_messages(profile, None, 3))
        assert "filters" in blob and '"op"' in blob


class TestAnEmptyFieldMeansUnset:
    """`"dimension": null` means the field is not set, not that it names a column
    called None.

    Told that a KPI must have no dimension, the model obeyed literally and sent
    the key with a null value. The strict "a field must name a column" rule then
    rejected three good widgets in one answer for the crime of being explicit.
    """

    def test_a_null_field_is_ignored(self, profile):
        ok, why = validate_widget(
            {"widget_type": "kpi", "title": "Median wait",
             "config": {"dimension": None, "measure": "wait_minutes",
                        "aggregation": "median"}}, profile)
        assert ok, why

    def test_an_empty_string_field_is_ignored(self, profile):
        ok, why = validate_widget(
            {"widget_type": "kpi", "title": "x",
             "config": {"dimension": "", "measure": "wait_minutes",
                        "aggregation": "avg"}}, profile)
        assert ok, why

    def test_a_null_does_not_satisfy_a_required_role(self, profile):
        """Ignoring it must not mean accepting it where one is needed."""
        ok, why = validate_widget(
            {"widget_type": "bar", "title": "x",
             "config": {"dimension": None, "measure": "wait_minutes",
                        "aggregation": "avg"}}, profile)
        assert not ok and "dimension" in why

    def test_a_real_number_in_a_field_is_still_refused(self, profile):
        ok, why = validate_widget(
            {"widget_type": "gauge", "title": "x",
             "config": {"measure": "wait_minutes", "aggregation": "avg",
                        "target": 20}}, profile)
        assert not ok and "target" in why


class TestThePrompt:
    def test_it_carries_the_persons_own_words(self, profile):
        msgs = build_messages(profile, "I am the emergency department manager", 3)
        blob = " ".join(m["content"] for m in msgs)
        assert "emergency department manager" in blob

    def test_it_describes_the_columns(self, profile):
        blob = " ".join(m["content"] for m in build_messages(profile, None, 3))
        assert "wait_minutes" in blob and "department" in blob

    def test_it_states_the_required_roles_of_what_it_offers(self, profile):
        blob = " ".join(m["content"] for m in build_messages(profile, None, 3))
        assert "dimension" in blob and "measure" in blob

    def test_it_does_not_offer_a_map_when_none_is_possible(self, profile):
        blob = " ".join(m["content"] for m in build_messages(profile, None, 3))
        assert "map_points" not in blob

    def test_it_asks_for_the_number_requested(self, profile):
        blob = " ".join(m["content"] for m in build_messages(profile, None, 4))
        assert "4" in blob


class FakeClient:
    """Stands in for the model at the boundary, so everything else is real."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.seen = []

    async def complete_json(self, messages, schema, **kw):
        self.seen.append(messages)
        return self.replies.pop(0) if self.replies else None


def one_proposal(widgets):
    return {"proposals": [{"title": "Emergency overview",
                           "rationale": "what the ED manager watches",
                           "widgets": widgets}]}


async def probe_all_good(widget_type, config):
    return {"type": "series", "rows": [{"name": "Cardiology", "value": 3}]}


async def probe_all_empty(widget_type, config):
    return {"type": "empty", "rows": []}


GOOD = {"widget_type": "bar", "title": "Wait by department",
        "config": {"dimension": "department", "measure": "wait_minutes",
                   "aggregation": "avg"}}


@pytest.mark.asyncio
class TestProbingIsConcurrent:
    """Eighteen widgets probed one after another took 99 seconds in the browser,
    against 25 for the same request when the cache happened to be warm. Each
    probe re-reads and re-prepares the frame; run end to end they dominate the
    wait, and the person is watching a counter the whole time.

    Bounded rather than unbounded: the pandas work is GIL-bound, so firing all
    eighteen at once would starve the event loop without going faster.
    """

    async def test_widgets_are_probed_in_parallel(self, profile):
        import asyncio
        active = {"now": 0, "peak": 0}

        async def probe(widget_type, config):
            active["now"] += 1
            active["peak"] = max(active["peak"], active["now"])
            await asyncio.sleep(0.05)
            active["now"] -= 1
            return {"type": "series", "rows": [{"name": "a", "value": 1}]}

        widgets = [{"widget_type": "bar", "title": "w%d" % i, "why": "x",
                    "config": {"dimension": "department", "measure": "wait_minutes",
                               "aggregation": "avg"}} for i in range(8)]
        client = FakeClient({"proposals": [{"title": "t", "rationale": "r",
                                            "widgets": widgets}]})
        got, _ = await suggest_for_dataset(profile, None, 1, client=client, probe=probe)
        assert len(got[0]["widgets"]) == 8
        assert active["peak"] > 1, "probes ran one at a time"

    async def test_it_does_not_probe_without_limit(self, profile):
        import asyncio
        active = {"now": 0, "peak": 0}

        async def probe(widget_type, config):
            active["now"] += 1
            active["peak"] = max(active["peak"], active["now"])
            await asyncio.sleep(0.05)
            active["now"] -= 1
            return {"type": "series", "rows": [{"name": "a", "value": 1}]}

        widgets = [{"widget_type": "bar", "title": "w%d" % i, "why": "x",
                    "config": {"dimension": "department", "measure": "wait_minutes",
                               "aggregation": "avg"}} for i in range(20)]
        client = FakeClient({"proposals": [{"title": "t", "rationale": "r",
                                            "widgets": widgets}]})
        await suggest_for_dataset(profile, None, 1, client=client, probe=probe)
        assert active["peak"] <= 6, active["peak"]

    async def test_the_order_of_the_widgets_is_kept(self, profile):
        """Tiles are laid out in the order they arrive, so the order the model
        chose must survive being probed out of sequence."""
        import asyncio

        async def probe(widget_type, config):
            # The later ones finish first, to break any accidental ordering.
            await asyncio.sleep(0.05 if "1" in str(config.get("limit")) else 0.01)
            return {"type": "series", "rows": [{"name": "a", "value": 1}]}

        widgets = [{"widget_type": "bar", "title": "w%d" % i, "why": "x",
                    "config": {"dimension": "department", "measure": "wait_minutes",
                               "aggregation": "avg", "limit": i + 1}}
                   for i in range(5)]
        client = FakeClient({"proposals": [{"title": "t", "rationale": "r",
                                            "widgets": widgets}]})
        got, _ = await suggest_for_dataset(profile, None, 1, client=client, probe=probe)
        assert [w["title"] for w in got[0]["widgets"]] == ["w0", "w1", "w2", "w3", "w4"]


@pytest.mark.asyncio
class TestEndToEnd:
    async def test_it_returns_what_the_model_proposed(self, profile):
        got, why = await suggest_for_dataset(
            profile, "I am an ED manager", 1,
            client=FakeClient(one_proposal([GOOD])), probe=probe_all_good)
        assert len(got) == 1
        assert got[0]["widgets"][0]["title"] == "Wait by department"

    async def test_a_widget_that_draws_nothing_is_dropped(self, profile):
        """The whole lesson of the exhaustive test: ask the renderer, not the
        endpoint. A proposal is only offered if its widgets actually draw."""
        got, why = await suggest_for_dataset(
            profile, None, 1,
            client=FakeClient(one_proposal([GOOD]), one_proposal([GOOD])),
            probe=probe_all_empty)
        assert got == []

    async def test_an_invalid_widget_is_dropped_but_its_proposal_survives(self, profile):
        bad = {"widget_type": "bar", "title": "Invented",
               "config": {"dimension": "nope", "measure": "wait_minutes",
                          "aggregation": "avg"}}
        got, why = await suggest_for_dataset(
            profile, None, 1,
            client=FakeClient(one_proposal([GOOD, bad])), probe=probe_all_good)
        assert len(got) == 1
        assert [w["title"] for w in got[0]["widgets"]] == ["Wait by department"]

    async def test_every_widget_carries_the_rows_it_returned(self, profile):
        """Shown on the card, so the person choosing can see it is not empty."""
        got, _ = await suggest_for_dataset(
            profile, None, 1, client=FakeClient(one_proposal([GOOD])),
            probe=probe_all_good)
        assert got[0]["widgets"][0]["row_count"] == 1

    async def test_it_retries_once_when_everything_was_rejected(self, profile):
        bad = {"widget_type": "bar", "title": "Invented",
               "config": {"dimension": "nope", "measure": "wait_minutes",
                          "aggregation": "avg"}}
        client = FakeClient(one_proposal([bad]), one_proposal([GOOD]))
        got, _ = await suggest_for_dataset(profile, None, 1, client=client,
                                           probe=probe_all_good)
        assert len(got) == 1
        assert len(client.seen) == 2

    async def test_the_retry_says_what_was_wrong(self, profile):
        bad = {"widget_type": "bar", "title": "Invented",
               "config": {"dimension": "nope", "measure": "wait_minutes",
                          "aggregation": "avg"}}
        client = FakeClient(one_proposal([bad]), one_proposal([GOOD]))
        await suggest_for_dataset(profile, None, 1, client=client, probe=probe_all_good)
        assert "nope" in " ".join(m["content"] for m in client.seen[1])

    async def test_no_model_is_an_explanation_not_a_crash(self, profile):
        got, why = await suggest_for_dataset(profile, None, 1, client=None,
                                             probe=probe_all_good)
        assert got == [] and why

    async def test_a_model_that_answers_nothing_is_an_explanation(self, profile):
        got, why = await suggest_for_dataset(profile, None, 1,
                                             client=FakeClient(None), probe=probe_all_good)
        assert got == [] and why
