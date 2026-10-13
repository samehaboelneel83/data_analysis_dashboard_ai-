"""Synthetic traps from the persona test (docs/persona-test/REPORT_AND_PLAN.md).

One small frame per trap, made up here: no rule may depend on any real
database, business or language. Each test names the plan item it guards.
"""
import datetime as dt

import pandas as pd

from app.services.guided_setup import demand


def daily_object_dates(start="2022-01-01", days=900):
    """A table whose date column arrives as Python `date` objects, as a
    database DATE column does (dtype object, not datetime64)."""
    first = dt.date.fromisoformat(start)
    return pd.DataFrame({
        "day": [first + dt.timedelta(days=i) for i in range(days)],
        "item": [f"I{i % 300}" for i in range(days)],          # many values: shown only as examples
        "value": [float(i % 17) for i in range(days)],
    })


class TestPlan01DatesOfEveryKind:
    def test_python_date_objects_are_dates(self):
        assert demand._is_date(daily_object_dates()["day"])

    def test_iso_text_is_a_date_and_free_text_is_not(self):
        assert demand._is_date(pd.Series(["2024-01-05", "2024-02-11 10:00:00", None]))
        assert not demand._is_date(pd.Series(["north", "south", "2024-01-05"]))

    def test_the_profile_shows_a_range_not_example_values(self):
        line = [ln for ln in demand.profile_text(daily_object_dates()).splitlines() if "`day`" in ln][0]
        assert "date, 2022-01-01 to 2024-06-18" in line

    def test_a_date_column_is_never_offered_as_a_value_to_pick(self):
        cols = {c["column"] for c in demand.candidates(daily_object_dates())}
        assert "day" not in cols


class TestPlan02NoFilterFromExampleValues:
    def test_a_year_copied_as_six_example_dates_becomes_the_whole_year(self):
        df = daily_object_dates()
        examples = [str(d) for d in df["day"].iloc[[400, 401, 402, 500, 520, 600]]]
        got = demand.resolve_scope(df, {"said": "the year 2023", "column": "day", "op": "in",
                                        "values": examples})
        assert got["op"] == "between" and got["values"] == ["2023-01-01", "2023-12-31"]
        assert got["matched_rows"] == 365 and got["status"] == "in_dashboard"

    def test_between_two_dates_includes_both_ends(self):
        got = demand.resolve_scope(daily_object_dates(), {"said": "first quarter", "column": "day",
                                                          "op": "between", "values": ["2022-01-01", "2022-03-31"]})
        assert got["matched_rows"] == 90

    def test_a_number_range_said_in_words(self):
        df = pd.DataFrame({"model_year": [2014, 2015, 2016, 2018, 2019, 2020]})
        got = demand.resolve_scope(df, {"said": "2015 to 2018", "column": "model_year", "op": "between",
                                        "values": ["2015", "2018"]})
        assert got["matched_rows"] == 3 and got["values"] == [2015.0, 2018.0]

    def test_a_range_the_dataset_already_holds_needs_no_filter(self):
        df = pd.DataFrame({"model_year": [2015, 2016, 2017, 2018]})
        got = demand.resolve_scope(df, {"said": "2015 to 2018", "column": "model_year", "op": "between",
                                        "values": ["2015", "2018"]})
        assert got["status"] == "in_data"

    def test_example_values_of_a_many_valued_column_are_not_a_filter(self):
        df = daily_object_dates()
        got = demand.resolve_scope(df, {"said": "the busy items", "column": "item", "op": "in",
                                        "values": ["I1", "I2", "I3"]}, named_only=True)
        assert got["status"] == "unmatched"

    def test_a_many_valued_value_the_person_typed_still_counts(self):
        got = demand.resolve_scope(daily_object_dates(), {"said": "item i7", "column": "item", "op": "in",
                                                          "values": ["I7"]}, named_only=True)
        assert got["values"] == ["I7"] and got["status"] == "in_dashboard"

    def test_between_becomes_two_widget_filters_and_reads_as_a_range(self):
        scope = [{"dataset_id": 1, "status": "in_dashboard", "column": "model_year", "op": "between",
                  "values": [2015.0, 2018.0], "said": "2015 to 2018"}]
        assert demand.filters_for({"scope": scope}, 1) == [
            {"column": "model_year", "op": "gte", "value": 2015.0},
            {"column": "model_year", "op": "lte", "value": 2018.0}]
        assert demand.scope_words({"scope": scope}, 1) == ["model year: 2015 – 2018"]


class TestPlan03WhatTheDatasetAlreadyHolds:
    def test_a_year_in_their_words_matches_a_date_in_the_query(self):
        sql = "SELECT * FROM prices WHERE commodity IN ('A', 'B') AND date >= '2021-01-01'"
        assert demand.made_for(sql, {"said": "since 2021", "values": []}) == ["2021-01-01"]

    def test_numbers_in_their_words_match_the_query(self):
        sql = "SELECT * FROM t WHERE year IN (2022, 2025)"
        assert demand.made_for(sql, {"said": "now compared with 2022", "values": []}) == ["2022"]

    def test_a_yes_no_condition_named_by_their_words(self):
        sql = "SELECT * FROM lines AS l JOIN heads AS h ON l.k = h.k WHERE h.is_cancellation = FALSE"
        got = demand.made_for(sql, {"said": "real sales, not cancelled orders", "values": []})
        assert got and "is_cancellation" in got[0]

    def test_unrelated_words_match_nothing(self):
        sql = "SELECT * FROM lines WHERE is_cancellation = FALSE AND qty > 0"
        assert demand.made_for(sql, {"said": "best products", "values": []}) == []


class TestPlan04NoFalseBannerNoFocusAsName:
    def test_pages_do_not_repeat_what_the_data_lacks(self):
        from app.services.guided_setup import answer
        dem = {"scope": [{"said": "2015 to 2018", "status": "unmatched", "dataset_id": 1}]}
        assert answer.scope_note([], [], 10, 10, "en", dem, 1) is None

    def test_a_restriction_already_saying_only_is_not_doubled(self):
        scope = [{"dataset_id": 1, "status": "in_data", "column": None, "op": "in", "values": [],
                  "said": "used cars only"}]
        assert demand.scope_words({"scope": scope}, 1) == ["used cars"]

    def test_the_focus_never_names_the_analysis_and_names_cut_at_a_word(self):
        from types import SimpleNamespace

        from app.routers.guided_setup import FLOW_NAME_CHARS, _flow_name
        focus_only = SimpleNamespace(name=None, demand=None, brief={"focus": "real sales, not cancelled orders"})
        assert _flow_name(focus_only) is None
        long_q = "Which hours of the day and which pickup areas earn me the most per trip and why"
        got = _flow_name(SimpleNamespace(name=None, demand=None, brief={"questions": long_q}))
        assert got.endswith("…") and len(got) <= FLOW_NAME_CHARS + 1 and long_q.startswith(got[:-1])


class TestPlan07ALookupCodeIsNotUnknown:
    @staticmethod
    def coded(label_for_zero="Flexible plan", with_label=True):
        codes = [0 if i % 20 == 0 else 1 + i % 3 for i in range(400)]
        names = {0: label_for_zero, 1: "Plan A", 2: "Plan B", 3: "Plan C"}
        df = pd.DataFrame({"plan_id": codes, "amount": [10.0 + i % 7 for i in range(400)]})
        if with_label:
            df["plan_name"] = [names[c] for c in codes]
        return df

    def placeholder(self, df):
        from app.services import data_quality
        return data_quality._column(df, "plan_id")["placeholder"]

    def test_a_named_code_is_kept(self):
        assert self.placeholder(self.coded()) is None

    def test_a_code_named_unknown_is_still_a_placeholder(self):
        assert self.placeholder(self.coded("Unknown"))["value"] == 0

    def test_without_a_name_the_zero_is_still_suspect(self):
        assert self.placeholder(self.coded(with_label=False))["value"] == 0


class TestPlan06DurationsAreNumbers:
    def test_a_date_minus_a_date_becomes_days(self):
        from app.services.ingest import detect_types
        df = pd.DataFrame({"days_late": pd.to_timedelta(["1 days 12:00:00", "-2 days", None]),
                           "wait": [dt.timedelta(hours=36), dt.timedelta(hours=12), None]})
        types = detect_types(df)
        assert types == {"days_late": "numeric", "wait": "numeric"}
        assert df["days_late"].tolist()[:2] == [1.5, -2.0] and df["wait"].tolist()[:2] == [1.5, 0.5]

    def test_the_name_chooses_the_unit(self):
        from app.services.ingest import detect_types
        df = pd.DataFrame({"hours_open": pd.to_timedelta(["90 min", "3 hours"])})
        detect_types(df)
        assert df["hours_open"].tolist() == [1.5, 3.0]


class TestPlan09CountingQuestions:
    def test_summing_a_count_column_counts(self):
        from app.services.agent.validate import measure_fit
        sql = "SELECT month, SUM(order_count) AS n FROM monthly GROUP BY month"
        assert measure_fit("which month is busiest", sql, "duckdb") is None

    def test_summing_an_unnamed_amount_is_still_questioned(self):
        from app.services.agent.validate import measure_fit
        sql = "SELECT month, SUM(volume) AS v FROM calls GROUP BY month"
        assert measure_fit("which month is busiest", sql, "duckdb").rung == "V7"


class TestPlan08AIRulesDoNotRemoveAGroup:
    @staticmethod
    def trips():
        kinds = ["Paid"] * 380 + ["Waived"] * 20
        return pd.DataFrame({"pay_kind": kinds, "fare": [5.0 + i % 9 for i in range(400)],
                             "charged": [5.0 + i % 9 if k == "Paid" else 0.0 for i, k in enumerate(kinds)]})

    def test_a_rule_broken_by_one_groups_own_rows_describes_that_group(self):
        from app.services.guided_setup import health
        got = health.rule_describes_group(self.trips(), "`charged` == `fare`")
        assert got == {"column": "pay_kind", "value": "Waived"}

    def test_scattered_breaks_are_not_a_group(self):
        from app.services.guided_setup import health
        df = self.trips()
        df.loc[[3, 50, 120, 200, 300], "charged"] = -1.0
        df["charged"] = df["fare"].where(df["charged"] != -1.0, -1.0)
        assert health.rule_describes_group(df, "`charged` == `fare`") is None

    def test_cleaning_never_applies_a_group_rule_by_itself(self):
        from app.services.guided_setup import cleaning
        item = {"kind": "rule", "column": "fare, charged", "rows": 2, "what": "x", "describes": {"column": "pay_kind"},
                "action": {"kind": "exclude", "expression": "`charged` == `fare`", "rule": "`charged` == `fare`"}}
        assert cleaning.plan([item], "en", rows=10_000) == []
        assert cleaning.plan([{**item, "describes": None}], "en", rows=10_000)


class TestPlan05TitlesMatchTheirQuery:
    @staticmethod
    def orders():
        return pd.DataFrame({
            "review_score": [1, 5, 4, 3, 5, 2] * 10,
            "days_late": [3.0, -1.0, -2.0, 0.5, -4.0, 6.0] * 10,
            "is_returned": [False, True, False, False, True, False] * 10,
            "region": ["North", "South", "East", "West", "North", "South"] * 10,
        })

    def test_a_qualifier_the_query_does_not_apply_is_refused(self):
        from app.services.guided_setup.answer import title_promises
        w = {"title": "Review score: late orders", "widget_type": "kpi",
             "config": {"measure": "review_score", "aggregation": "avg"}}
        assert "days_late" in title_promises(w, self.orders())

    def test_the_same_title_with_the_filter_passes(self):
        from app.services.guided_setup.answer import title_promises
        w = {"title": "Review score: late orders", "widget_type": "kpi",
             "config": {"measure": "review_score", "aggregation": "avg",
                        "filters": [{"column": "days_late", "op": "gt", "value": 0}]}}
        assert title_promises(w, self.orders()) is None

    def test_a_category_value_in_the_title_needs_that_column(self):
        from app.services.guided_setup.answer import title_promises
        w = {"title": "Average score in the North", "widget_type": "kpi",
             "config": {"measure": "review_score", "aggregation": "avg"}}
        assert "North" in title_promises(w, self.orders())
        w["config"]["dimension"] = "region"
        assert title_promises(w, self.orders()) is None

    def test_a_flag_named_in_the_title(self):
        from app.services.guided_setup.answer import title_promises
        w = {"title": "Returned share by region", "widget_type": "bar",
             "config": {"dimension": "region", "measure": "review_score", "aggregation": "avg"}}
        assert "is_returned" in title_promises(w, self.orders())

    def test_a_plain_title_passes(self):
        from app.services.guided_setup.answer import title_promises
        w = {"title": "Average review score by region", "widget_type": "bar",
             "config": {"dimension": "region", "measure": "review_score", "aggregation": "avg"}}
        assert title_promises(w, self.orders()) is None


class TestPlan13And14PeriodsAndStrayDates:
    def test_a_thin_last_month_of_a_month_keyed_summary_is_partial(self):
        from app.services.relative_dates import partial_period
        months = pd.date_range("2020-01-01", periods=12, freq="MS")
        rows = [m for m in months[:-1] for _ in range(20)] + [months[-1]] * 6
        df = pd.DataFrame({"month": rows})
        result = {"rows": [{"name": m.strftime("%Y-%m"), "value": 1} for m in months]}
        got = partial_period(df, "month", "month", result)
        assert got and got["label"] == "2020-12" and got.get("thin")

    def test_a_full_last_month_of_a_summary_is_not_partial(self):
        from app.services.relative_dates import partial_period
        months = pd.date_range("2020-01-01", periods=12, freq="MS")
        df = pd.DataFrame({"month": [m for m in months for _ in range(20)]})
        result = {"rows": [{"name": m.strftime("%Y-%m"), "value": 1} for m in months]}
        assert partial_period(df, "month", "month", result) is None

    def test_a_few_rows_years_away_are_strays(self):
        from app.services.relative_dates import stray_dates
        main = pd.Series(pd.date_range("2024-01-01", "2024-01-31 23:00", freq="h"))
        dates = pd.concat([main, pd.Series(pd.to_datetime(["2002-12-31", "2009-01-01"]))], ignore_index=True)
        got = stray_dates(dates)
        assert got["rows"] == 2 and str(got["lo"].date()) == "2024-01-01"

    def test_an_even_spread_has_no_strays(self):
        from app.services.relative_dates import stray_dates
        assert stray_dates(pd.Series(pd.date_range("2020-01-01", periods=1000, freq="D"))) is None

    def test_the_trend_finding_ignores_stray_months(self):
        from app.services.insights import generate_insights
        main = pd.date_range("2023-01-01", "2024-01-31", freq="6h")
        df = pd.DataFrame({"when": list(main) + list(pd.to_datetime(["2002-12-31", "2009-01-01"])),
                           "amount": [10.0] * len(main) + [1.0, 1.0]})
        found = generate_insights(df, {"when": "datetime", "amount": "numeric"}, None)
        assert not any("%" in str(f.get("title")) and "000" in str(f.get("title")) for f in found.get("findings") or [])

    def test_the_check_offers_to_leave_strays_out_and_never_does_it_by_itself(self):
        from app.services.guided_setup import cleaning, health
        main = pd.date_range("2024-01-01", "2024-01-31 23:00", freq="h")
        df = pd.DataFrame({"when": list(main) + list(pd.to_datetime(["2002-12-31", "2009-01-01"]))})
        items = [i for i in health.generic_rules(df, "en") if i["kind"] == "stray"]
        assert len(items) == 1 and items[0]["rows"] == 2 and items[0]["action"]["kind"] == "exclude"
        assert cleaning.plan(items, "en", rows=len(df)) == []

    def test_a_kpi_trend_drops_every_thin_month_at_the_tail(self):
        from app.services.widget_data import kpi_trend
        days = pd.date_range("2020-01-01", "2020-08-31", freq="D")
        when = [d for d in days for _ in range(10)] + list(pd.to_datetime(["2020-09-03"] * 16 + ["2020-10-02"] * 4))
        df = pd.DataFrame({"when": when, "n": 1})
        got = kpi_trend(df, {"measure": "n", "aggregation": "count", "sparkline_date": "when",
                             "sparkline_granularity": "month"})
        assert got["period"] == "2020-08" and got["partial_dropped"]


class TestPlan16SmallGroupsDoNotRank:
    @staticmethod
    def frame():
        rows = [("Big", 10.0 + i % 3) for i in range(200)] + [("Mid", 12.0)] * 40 + [("Tiny", 350.0)] * 2
        return pd.DataFrame(rows, columns=["zone", "fare"])

    def test_an_average_ranking_hides_groups_below_the_floor(self):
        from app.services.widget_data import shape_series
        got = shape_series(self.frame(), {"dimension": "zone", "measure": "fare", "aggregation": "avg",
                                          "min_group_rows": 30})
        assert [r["name"] for r in got["rows"]] == ["Mid", "Big"]
        assert got["small_groups"] == {"hidden": 1, "min_rows": 30}

    def test_a_total_keeps_every_group(self):
        from app.services.widget_data import shape_series
        got = shape_series(self.frame(), {"dimension": "zone", "measure": "fare", "aggregation": "sum",
                                          "min_group_rows": 30})
        assert {r["name"] for r in got["rows"]} == {"Big", "Mid", "Tiny"} and "small_groups" not in got

    def test_the_builders_set_the_floor_on_averages_by_a_category_not_on_time(self):
        from app.services.suggest_dataset_dashboard import polish_widget
        profile = {"columns": [{"name": "zone", "role": "categorical", "distinct": 3},
                               {"name": "fare", "role": "numeric"},
                               {"name": "day", "role": "datetime"}]}
        by_zone = polish_widget({"widget_type": "bar", "config": {"dimension": "zone", "measure": "fare",
                                                                  "aggregation": "avg"}}, profile)
        by_day = polish_widget({"widget_type": "line", "config": {"dimension": "day", "measure": "fare",
                                                                  "aggregation": "avg",
                                                                  "dimension_granularity": "month"}}, profile)
        total = polish_widget({"widget_type": "bar", "config": {"dimension": "zone", "measure": "fare",
                                                                "aggregation": "sum"}}, profile)
        assert by_zone["config"]["min_group_rows"] == 30
        assert "min_group_rows" not in by_day["config"] and "min_group_rows" not in total["config"]

    def test_duckdb_applies_the_floor_in_sql(self, tmp_path):
        from app.services import duck_agg
        path = tmp_path / "f.parquet"
        self.frame().to_parquet(path, index=False)
        frame = duck_agg.aggregate(str(path), {"dimension": "zone", "measure": "fare", "aggregation": "avg",
                                               "min_group_rows": 30}, ["zone", "fare"])
        assert set(frame["zone"]) == {"Big", "Mid"}


class TestPlan110ExclusionsAreRules:
    catalog = [{"name": "people", "columns": [{"name": "pid"}, {"name": "person_no"}, {"name": "unit"},
                                               {"name": "health_note"}]},
               {"name": "scores", "columns": [{"name": "pid"}, {"name": "score"}]}]

    def test_named_columns_leave_every_select(self):
        from app.services.guided_setup.datasets import banned_columns, without_columns
        banned = banned_columns([{"table": "people", "column": "person_no"},
                                 {"table": "people", "column": "health_note"},
                                 {"table": "nowhere", "column": "x"}], self.catalog)
        assert banned == {("people", "person_no"), ("people", "health_note")}
        sql = ("SELECT p.person_no, p.unit, s.score, p.health_note AS note FROM scores AS s "
               "JOIN people AS p ON s.pid = p.pid WHERE p.person_no IS NOT NULL")
        got, removed = without_columns(sql, "postgresql", banned)
        assert removed == ["person_no", "note"]
        assert "p.unit" in got and "s.score" in got and "health_note" not in got
        assert "WHERE p.person_no IS NOT NULL" in got          # used to filter, not shown

    def test_nothing_banned_changes_nothing(self):
        from app.services.guided_setup.datasets import without_columns
        sql = "SELECT unit FROM people"
        assert without_columns(sql, "postgresql", {("people", "person_no")}) == (sql, [])


class TestPlan113CopiesNeedAKey:
    def test_a_named_row_makes_identical_rows_copies(self):
        from app.services.guided_setup import health
        df = pd.DataFrame({"id": [f"S{i}" for i in range(100)] + ["S1", "S2"], "fee": [5.0] * 102})
        assert health.has_row_key(df)

    def test_without_a_key_copies_are_only_possible(self):
        from app.services.guided_setup import cleaning, health
        df = pd.DataFrame({"product": ["A", "B"] * 50 + ["A"], "qty": [1, 2] * 50 + [1], "price": [2.5, 3.5] * 50 + [2.5]})
        assert not health.has_row_key(df)
        items = health.column_items({"rows": len(df), "duplicate_rows": 99, "column_report": []}, df, "en")
        dups = next(i for i in items if i["kind"] == "dups")
        assert dups["keyed"] is False and "may be real repeats" in dups["what"]
        assert cleaning.plan([dups], "en", rows=len(df)) == []

    def test_with_a_key_copies_are_removed_by_themselves(self):
        from app.services.guided_setup import cleaning, health
        df = pd.DataFrame({"id": list(range(100)) + [1], "fee": [5.0] * 101})
        items = health.column_items({"rows": len(df), "duplicate_rows": 1, "column_report": []}, df, "en")
        assert [a["kind"] for a in cleaning.plan(items, "en", rows=len(df))] == ["dups"]


class TestPlan111TimeParts:
    profile = {"columns": [{"name": "pickup", "role": "datetime"}, {"name": "fare", "role": "numeric"}],
               "structure": {"date_range": {"granularity": "day"}}}

    def test_a_title_naming_the_hour_groups_by_hour(self):
        from app.services.suggest_dataset_dashboard import polish_widget
        got = polish_widget({"widget_type": "bar", "title": "Average fare by hour of day",
                             "config": {"dimension": "pickup", "measure": "fare", "aggregation": "avg",
                                        "dimension_granularity": "day"}}, self.profile)
        assert got["config"]["dimension_granularity"] == "hour_of_day"

    def test_weekday_in_arabic(self):
        from app.services.suggest_dataset_dashboard import time_part_named
        assert time_part_named("متوسط الأجرة حسب يوم الأسبوع") == "weekday"

    def test_a_plain_trend_keeps_its_grain(self):
        from app.services.suggest_dataset_dashboard import polish_widget
        got = polish_widget({"widget_type": "line", "title": "Fares over time",
                             "config": {"dimension": "pickup", "measure": "fare", "aggregation": "avg",
                                        "dimension_granularity": "month"}}, self.profile)
        assert got["config"]["dimension_granularity"] == "month"


class TestPlan16SmallData:
    def test_data_too_small_for_the_floor_keeps_every_group(self):
        from app.services.widget_data import shape_series
        small = pd.DataFrame({"dept": ["A"] * 5 + ["B"] * 4, "wait": [1.0] * 5 + [2.0] * 4})
        got = shape_series(small, {"dimension": "dept", "measure": "wait", "aggregation": "avg",
                                   "min_group_rows": 30})
        assert {r["name"] for r in got["rows"]} == {"A", "B"}


class TestPlan12SubtotalRows:
    @staticmethod
    def people():
        rows = []
        for i, region in enumerate(["North", "South", "East", "West", "Centre"]):
            men, women = 100 + i * 7, 90 + i * 5
            rows += [(region, "men", men), (region, "women", women), (region, "both", men + women)]
        return pd.DataFrame(rows, columns=["region", "group", "people"])

    def test_a_value_that_totals_its_siblings_is_found_by_arithmetic(self):
        from app.services.guided_setup import health
        got = health.subtotal_members(self.people())
        assert got == [{"column": "group", "value": "both", "rows": 5, "measure": "people"}]

    def test_ordinary_categories_are_not_subtotals(self):
        from app.services.guided_setup import health
        df = self.people()
        df = df[df["group"] != "both"]
        assert health.subtotal_members(df) == []

    def test_the_check_leaves_total_rows_out_by_itself_and_says_so(self):
        from app.services.guided_setup import cleaning, health
        items = [i for i in health.generic_rules(self.people(), "en") if i["kind"] == "subtotal"]
        assert len(items) == 1 and "hold the totals" in items[0]["what"]
        planned = cleaning.plan(items, "en", rows=15)
        assert [a["kind"] for a in planned] == ["subtotal"] and "totals of the other rows" in planned[0]["said"]

    def test_nested_totals_with_a_small_unrecorded_part_are_found(self):
        from app.services.guided_setup import health
        rows = []
        for year in (2021, 2022, 2023, 2024):
            for sex in ("f", "m"):
                bands = [40 + year % 7, 70, 300 - (year % 5)]
                rows += [(year, sex, b, n) for b, n in zip(("young", "adult", "old"), bands)]
                rows.append((year, sex, "all", sum(bands) + 2))          # a few people with no age
            rows.append((year, "all", "all", 2 * (410 + year % 7) + 9))
        df = pd.DataFrame(rows, columns=["year", "sex", "band", "people"])
        assert {(m["column"], m["value"]) for m in health.subtotal_members(df)} >= {("band", "all")}

    def test_a_number_a_category_fixes_is_not_the_amount(self):
        from app.services.guided_setup import health
        df = pd.DataFrame({"band": ["0-4", "5-9", "all"] * 4, "low_age": [0, 5, 0] * 4,
                           "sex": ["f"] * 6 + ["m"] * 6, "people": [1, 1, 1, 2, 0, 1, 1, 1, 1, 0, 2, 1]})
        assert health.subtotal_members(df) == []


class TestPlan17OddMembers:
    @staticmethod
    def lines():
        codes = [f"{10000 + i}" for i in range(150)] + [f"{20000 + i}B" for i in range(50)] + ["POST", "FEE"]
        return pd.DataFrame({"code": codes * 2, "amount": [3.0] * (len(codes) * 2)})

    def test_codes_written_unlike_the_rest_are_found(self):
        from app.services.guided_setup import health
        got = health.odd_members(self.lines())
        assert got == [{"column": "code", "values": ["POST", "FEE"], "rows": 4}]

    def test_free_text_is_not_searched(self):
        from app.services.guided_setup import health
        words = ["red apple", "Green Pear", "plum", "big orange box", "kiwi 2", "x"] * 10
        df = pd.DataFrame({"name": [f"{w} {i}" if i % 3 else w for i, w in enumerate(words)]})
        assert health.odd_members(df) == []

    def test_the_offered_fix_runs_and_is_never_applied_by_itself(self):
        from app.services.guided_setup import cleaning, health
        from app.services.widget_data import apply_filter_expr
        df = self.lines()
        items = [i for i in health.generic_rules(df, "en") if i["kind"] == "odd"]
        assert len(items) == 1 and "“POST”" in items[0]["what"]
        kept = apply_filter_expr(df, items[0]["action"]["expression"], silent=False)
        assert len(kept) == len(df) - 4
        assert cleaning.plan(items, "en", rows=len(df)) == []


class TestPlan15SeasonIsNotAnAnomaly:
    @staticmethod
    def sales(spike_month=None):
        days = pd.date_range("2022-01-01", "2023-12-31", freq="D")
        amount = []
        for d in days:
            base = 100.0 + (d.dayofyear % 7)
            if d.month == 11:
                base *= 2.0                      # the yearly peak
            if spike_month and d.strftime("%Y-%m") == spike_month:
                base *= 3.0                      # a one-off
            amount.append(base)
        return pd.DataFrame({"when": days, "amount": amount})

    def test_a_month_that_peaks_every_year_is_a_season(self):
        from app.services.insights import generate_insights
        found = generate_insights(self.sales(), {"when": "datetime", "amount": "numeric"}, None)["findings"]
        kinds = {(f["kind"], (f.get("figures") or {}).get("period")) for f in found}
        assert ("season", "2023-11") in kinds
        assert not any(k == "anomaly" and p == "2023-11" for k, p in kinds)

    def test_a_one_off_month_is_still_an_anomaly(self):
        from app.services.insights import generate_insights
        found = generate_insights(self.sales("2023-06"), {"when": "datetime", "amount": "numeric"}, None)["findings"]
        assert any(f["kind"] == "anomaly" and f["figures"]["period"] == "2023-06" for f in found)

    def test_a_seasonal_last_month_is_compared_with_a_year_before(self):
        from app.services.insights import generate_insights
        df = self.sales()
        df = df[df["when"] < "2023-12-01"]                  # the data ends with the peak month
        found = generate_insights(df, {"when": "datetime", "amount": "numeric"}, None)["findings"]
        trend = [f for f in found if f["kind"] == "trend"]
        assert trend and "year_before" in trend[0]["figures"] and abs(trend[0]["figures"]["delta_pct"]) < 10


class TestPlan19JoinSafety:
    catalog = [{"name": "people", "columns": [{"name": "pid"}, {"name": "name"}], "pk": ["pid"]},
               {"name": "pay", "columns": [{"name": "pid"}, {"name": "amount"}, {"name": "until"}], "pk": []}]

    def run(self, sql):
        import sqlite3
        from app.services.guided_setup.datasets import join_check_sql
        con = sqlite3.connect(":memory:")
        con.executescript("CREATE TABLE people(pid INT PRIMARY KEY, name TEXT);"
                          "CREATE TABLE pay(pid INT, amount REAL, until TEXT);"
                          "INSERT INTO people VALUES (1,'a'),(2,'b'),(3,'c'),(4,'d');"
                          "INSERT INTO pay VALUES (1,10,'old'),(1,12,'now'),(2,20,'now'),(3,30,'old');")
        built = join_check_sql(sql, "sqlite", self.catalog)
        cur = con.execute(built[0])
        return built, dict(zip([d[0] for d in cur.description], cur.fetchone()))

    def test_a_join_that_repeats_the_main_rows_is_measured(self):
        built, row = self.run("SELECT p.name, y.amount FROM people AS p JOIN pay AS y ON p.pid = y.pid")
        assert built[1] == "people" and (row["n"], row["k"]) == (4, 3)

    def test_a_left_join_without_matches_is_measured(self):
        built, row = self.run("SELECT p.name, y.amount FROM people AS p "
                              "LEFT JOIN pay AS y ON p.pid = y.pid AND y.until = 'now'")
        assert built[2] == ["pay"] and (row["n"], row["u0"]) == (4, 2)

    def test_a_single_table_is_not_checked(self):
        from app.services.guided_setup.datasets import join_check_sql
        assert join_check_sql("SELECT name FROM people", "sqlite", self.catalog) is None


class TestPlan11MeaningOfNumbers:
    def test_ids_sequences_coordinates_and_years_are_never_calculated(self):
        from types import SimpleNamespace as S
        from app.services.guided_setup.meaning import never_calculated
        assert never_calculated("line_item_id") and never_calculated("payment_sequential")
        assert never_calculated("pickup_lat") and never_calculated("pickup_lng")
        assert never_calculated("yr", S(min_value=1999, max_value=2024)) == "a year"
        assert never_calculated("price", S(min_value=0.5, max_value=900)) is None
        assert never_calculated("installments", S(min_value=1, max_value=24)) is None

    def test_a_table_of_open_ended_periods_holds_levels(self):
        from types import SimpleNamespace as S
        from app.services.guided_setup.meaning import holds_periods
        cols = [S(id=1, dtype="integer"), S(id=2, dtype="date")]
        assert holds_periods({"_columns": cols, "_stats": {2: S(max_value="9999-01-01")}})
        assert not holds_periods({"_columns": cols, "_stats": {2: S(max_value="2024-06-30")}})


class TestPlan26InsightsMustBeNews:
    def test_two_readings_of_one_quantity_are_not_a_finding(self):
        from app.services.insights import generate_insights
        import numpy as np
        rng = np.random.default_rng(3)
        level = 100 + np.cumsum(rng.normal(0, 1, 400))
        df = pd.DataFrame({"opening": level, "closing": level + rng.normal(0, 0.2, 400),
                           "volume": rng.integers(100, 1000, 400).astype(float)})
        found = generate_insights(df, {"opening": "numeric", "closing": "numeric", "volume": "numeric"}, None)
        assert not [f for f in found["findings"] if f["kind"] == "correlation"
                    and set(f["columns"]) == {"opening", "closing"}]

    def test_a_reason_given_only_when_it_happened_is_not_a_rate(self):
        from app.services.insights import _filled_only_for
        hit = pd.Series([True] * 20 + [False] * 180)
        reason = pd.Series(["late", "broken"] * 10 + ["Unknown"] * 180)
        region = pd.Series(["north", "south"] * 100)
        assert _filled_only_for(reason, hit)
        assert not _filled_only_for(region, hit)


class TestPlan23And25PlainVerdicts:
    def test_groups_a_few_percent_apart_are_about_the_same(self):
        from app.services.guided_setup.answer import finding
        w = {"widget_type": "bar", "config": {"dimension": "channel", "measure": "sales", "aggregation": "sum"}}
        res = {"rows": [{"name": "Online", "value": 2790}, {"name": "Shop", "value": 2740},
                        {"name": "Partner", "value": 2690}, {"name": "Retail", "value": 2670}]}
        assert "about the same" in finding(w, res, set(), "en")

    def test_a_real_gap_is_a_ranking(self):
        from app.services.guided_setup.answer import finding
        w = {"widget_type": "bar", "config": {"dimension": "channel", "measure": "sales", "aggregation": "sum"}}
        res = {"rows": [{"name": "Online", "value": 5000}, {"name": "Retail", "value": 2000}]}
        got = finding(w, res, set(), "en")
        assert got.startswith("Highest: Online") and "about the same" not in got


class TestPlan22LikeForLike:
    W = {"widget_type": "line", "config": {"dimension": "month", "measure": "sales", "aggregation": "sum"}}

    def test_the_latest_month_is_compared_with_a_year_before_and_the_peak_is_named(self):
        from app.services.guided_setup.answer import finding
        rows = [{"name": f"2020-{m:02d}", "value": 100 + (60 if m == 11 else 0)} for m in range(1, 13)]
        rows += [{"name": f"2021-{m:02d}", "value": 96 + (58 if m == 11 else 0)} for m in range(1, 12)]
        got = finding(self.W, {"rows": rows}, {"month"}, "en")
        assert got.startswith("2021-11: 154 (-4% on 2020-11)") and "highest: 2020-11 (160)" in got

    def test_without_a_year_of_history_the_period_before_is_the_reference(self):
        from app.services.guided_setup.answer import finding
        rows = [{"name": f"2021-0{m}", "value": v} for m, v in ((1, 100), (2, 120), (3, 90))]
        got = finding(self.W, {"rows": rows}, {"month"}, "en")
        assert got.startswith("2021-03: 90 (-25% on 2021-02)")


class TestPlan24NamesNotCodes:
    @staticmethod
    def facts():
        from types import SimpleNamespace as C
        return [
            {"name": "staff", "rows": 1000, "links": [{"column": "dept", "table": "depts", "to_column": "code"}],
             "_columns": [C(name="id", dtype="integer", is_primary_key=True), C(name="dept", dtype="text", is_primary_key=False),
                          C(name="pay", dtype="numeric", is_primary_key=False)]},
            {"name": "depts", "rows": 5, "links": [],
             "_columns": [C(name="code", dtype="text", is_primary_key=True), C(name="title", dtype="text", is_primary_key=False)]},
        ]

    def test_a_code_gets_its_name_beside_it(self):
        import sqlite3
        from app.services.guided_setup.datasets import with_names
        sql, added = with_names("SELECT s.dept, s.pay FROM staff AS s", "sqlite", self.facts())
        assert added == ["title"]
        con = sqlite3.connect(":memory:")
        con.executescript("CREATE TABLE staff(id INT, dept TEXT, pay REAL); CREATE TABLE depts(code TEXT, title TEXT);"
                          "INSERT INTO staff VALUES (1,'d1',10),(2,'d2',20),(3,'d9',5);"
                          "INSERT INTO depts VALUES ('d1','Sales'),('d2','Research');")
        rows = con.execute(sql).fetchall()
        assert len(rows) == 3 and ("d1", 10.0, "Sales") in rows and ("d9", 5.0, None) in rows

    def test_a_lookup_already_joined_or_a_summary_is_left_alone(self):
        from app.services.guided_setup.datasets import with_names
        joined = "SELECT s.dept, d.title FROM staff AS s JOIN depts AS d ON s.dept = d.code"
        assert with_names(joined, "sqlite", self.facts()) == (joined, [])
        grouped = "SELECT s.dept, AVG(s.pay) AS pay FROM staff AS s GROUP BY s.dept"
        assert with_names(grouped, "sqlite", self.facts())[1] == []


class TestPlan27UncheckedFiguresStepAside:
    def test_sentences_with_made_up_numbers_are_set_aside(self):
        from app.services.agent.evidence import set_aside_untraced, trace_claims
        results = [{"columns": ["month", "sales"], "rows": [["2011-11", 1509496.33], ["2010-11", 1470272.48]],
                    "total": 2}]
        answer = ("The highest sales were in 2011-11 at 1,509,496.33, then 2010-11 at 1,470,272.48. "
                  "Total sales for 2010 were 9,352,485.08 and for 2011 were 10,635,747.57.")
        ev = trace_claims(answer, "best months", results, ["SELECT 1"])
        assert ev["untraced"] >= 2
        checked, aside = set_aside_untraced(answer, ev)
        assert "1,509,496.33" in checked and "9,352,485.08" not in checked
        assert aside == ["Total sales for 2010 were 9,352,485.08 and for 2011 were 10,635,747.57."]

    def test_an_answer_with_nothing_checked_is_left_whole(self):
        from app.services.agent.evidence import set_aside_untraced
        ev = {"claims": [{"start": 6, "end": 9, "status": "untraced"}]}
        assert set_aside_untraced("Total 123.", ev) == ("Total 123.", [])


class TestPlan21EveryQuestionAnswered:
    @staticmethod
    def page():
        return [{"title": "P", "rationale": "", "widgets": [{"widget_type": "kpi", "question": "q1", "title": "T",
                                                             "config": {}, "finding": "1"}]}]

    def test_an_unanswered_question_says_why_its_chart_was_left_out(self):
        from app.services.guided_setup.answer import _finish
        dem = {"questions": [{"id": "q1", "text": "How many?", "asked": True},
                             {"id": "q2", "text": "Is there a pay gap?", "asked": True},
                             {"id": "q3", "text": "Which hour is best?", "asked": True}]}
        out = _finish(self.page(), dem, None, "en", None,
                      {"q2": "'Pay gap': the chart is flat -- answer the question another way or leave it out"})
        said = out[0]["unanswered"]
        assert said[0].startswith("This data could not answer: Is there a pay gap? -- the chart for it was left out: the chart is flat")
        assert said[1] == "This data could not answer: Which hour is best? -- no chart of these columns answers it"


class TestPlan34LeftoversFoldAway:
    """A dataset nobody uses, made by someone else, is listed last -- judged by
    use, never by its name ("delete me" is just a name)."""

    async def test_used_and_own_first_unused_others_last(self, db_session, two_orgs):
        from app.models.models import DataSource, Dataset, Report
        from app.routers.guided_setup import _existing_datasets
        user = two_orgs["a"]["user"]
        src = DataSource(name="Any", type="postgresql", config={}, org_id=user.org_id)
        db_session.add(src)
        await db_session.flush()
        made = {}
        for name, owner in [("trial", None), ("mine", user.id), ("in use", None), ("extra use", None)]:
            d = Dataset(name=name, org_id=user.org_id, data_source_id=src.id, created_by=owner)
            db_session.add(d)
            await db_session.flush()
            made[name] = d.id
        db_session.add(Report(name="R", org_id=user.org_id, dataset_id=made["in use"],
                              additional_dataset_ids=[made["extra use"]]))
        await db_session.flush()
        out = await _existing_datasets(db_session, user, src)
        names = [d["name"] for d in out]
        assert names[-1] == "trial"
        assert set(names[:2]) == {"in use", "extra use"} and names[2] == "mine"
        by = {d["name"]: d for d in out}
        assert by["in use"]["used"] == 1 and by["trial"]["used"] == 0
        assert by["mine"]["mine"] and not by["trial"]["mine"]


class TestPlan35ParetoOnlyWhenAsked:
    """A concentrated ranking stays a plain bar unless the chart asked for the
    running share; the planner is told it may ask."""

    def _dress(self, cfg):
        import asyncio
        from types import SimpleNamespace
        from app.services.guided_setup import dress
        vals = [500, 300, 40, 30, 20, 10, 5, 5]
        res = {"rows": [{"name": f"g{i}", "value": v} for i, v in enumerate(vals)]}

        class G:
            richness, percent, dates, flag_of = "balanced", set(), set(), {}

            async def _draw(self, w):
                return res, ""
        pages = [{"title": "P", "scope_filters": [], "widgets": [
            {"widget_type": "bar", "title": "Top groups", "config": {"dimension": "g", "measure": "m",
                                                                      "aggregation": "sum", **cfg}}]}]
        inputs = SimpleNamespace(column_meta={}, ineligible=lambda: set(), df=SimpleNamespace(columns=["g", "m"]),
                                 profile={"columns": [{"name": "g", "role": "categorical", "distinct": 8},
                                                      {"name": "m", "role": "numeric"}]})
        asyncio.run(dress.apply(pages, G(), inputs, "en"))
        return [w["widget_type"] for w in pages[0]["widgets"]]

    def test_a_plain_ranking_gets_no_running_share(self):
        assert "dual_axis_bar_line" not in self._dress({})

    def test_asked_for_it_gets_it(self):
        assert "dual_axis_bar_line" in self._dress({"pareto": True})

    def test_the_planner_may_ask(self):
        from app.services.guided_setup import answer
        plain = {"is_identifier": False, "is_personal": False}
        _types, text = answer.menu({"columns": [{"name": "g", "role": "categorical", "distinct": 8, **plain},
                                                {"name": "m", "role": "numeric", **plain}]}, "balanced")
        assert '"pareto": true' in text


class TestPlan35WholeNumberGroups:
    """A grouping column held as decimals only because it has blanks reads as
    whole numbers ("2000", never "2000.0"); real decimals stay decimals."""

    def test_years_with_blanks(self):
        import numpy as np
        import pandas as pd
        from app.services.widget_data import get_widget_data_from_df
        df = pd.DataFrame({"yr": [2000.0, 2000.0, 2001.0, np.nan, 1999.0], "v": [1, 2, 3, 4, 5]})
        rows = get_widget_data_from_df(df, {"dimension": "yr", "measure": "v", "aggregation": "sum"}, "bar")["rows"]
        assert sorted(str(r["name"]) for r in rows) == ["1999", "2000", "2001"]

    def test_real_decimals_stay(self):
        import pandas as pd
        from app.services.widget_data import get_widget_data_from_df
        df = pd.DataFrame({"rate": [1.5, 1.5, 2.25], "v": [1, 2, 3]})
        rows = get_widget_data_from_df(df, {"dimension": "rate", "measure": "v", "aggregation": "sum"}, "bar")["rows"]
        assert sorted(str(r["name"]) for r in rows) == ["1.5", "2.25"]


class TestPlan36HowLongItTakes:
    """A finished AI step keeps how long it took; the next person is told the
    usual wait (the median over recent analyses) and how long theirs has run."""

    def test_took_and_since(self):
        from datetime import datetime, timedelta
        from app.routers.guided_setup import _since, _took
        started = (datetime.utcnow() - timedelta(seconds=42)).isoformat()
        assert 41 <= _took(started) <= 44
        assert _took(None) is None
        assert _since({"pending": True, "at": started}) == started
        assert _since({"at": started}) is None

    async def test_usual_is_the_median_per_step(self, db_session, two_orgs):
        from app.models.models import DataSource, SetupFlow, SetupJourney
        from app.routers.guided_setup import _usual_waits
        user = two_orgs["a"]["user"]
        src = DataSource(name="Any", type="postgresql", config={}, org_id=user.org_id)
        db_session.add(src)
        await db_session.flush()
        j = SetupJourney(org_id=user.org_id, user_id=user.id, data_source_id=src.id)
        db_session.add(j)
        await db_session.flush()
        for took in (10, 30, 200):
            db_session.add(SetupFlow(org_id=user.org_id, user_id=user.id, journey_id=j.id, data_source_id=src.id,
                                     proposals={"took": took}, findings={"1": {"took": took / 2}}, designs={}))
        await db_session.flush()
        usual = await _usual_waits(db_session, user.org_id)
        assert usual == {"proposals": 30, "check": 15}
        assert await _usual_waits(db_session, two_orgs["b"]["user"].org_id) == {}


class TestPlan37ChartsThatListPeople:
    """A chart grouped by a personal column or an identifier lists single
    records; a chart grouped by a category does not. Decided from the column,
    never from what the data is about."""

    SEM = {1: {"member_no": None, "branch": None, "email": "email", "full_name": None, "score": None}}

    def _w(self, wt, **cfg):
        return {"id": 9, "title": "T", "page": "P", "widget_type": wt, "config": cfg}

    def test_identifier_and_personal_axes_are_found(self):
        from app.services.listed_records import listed
        got = listed([self._w("bar", dimension="member_no", measure="score"),
                      self._w("bar", dimension="branch", measure="score"),
                      self._w("table", columns=["branch", "full_name"])], self.SEM, {}, 1)
        assert [(g["column"], g["kind"]) for g in got] == [("member_no", "identifier"), ("full_name", "person_name")]

    def test_a_detected_type_counts_without_a_telling_name(self):
        from app.services.listed_records import listed
        got = listed([self._w("bar", dimension="email", measure="score")], self.SEM, {}, 1)
        assert got[0]["kind"] == "email"

    def test_columns_carry_the_mark(self):
        from app.schemas.schemas import DatasetColumnOut
        c = DatasetColumnOut(id=1, name="contact", dtype="object", semantic_type="phone")
        assert c.model_dump()["personal"] == "phone"
        assert DatasetColumnOut(id=2, name="branch", dtype="object").model_dump()["personal"] is None


class TestPlan17MembersOnAnotherScale:
    """Members whose typical value sits orders of magnitude from the rest (an
    index beside companies) are flagged; a smooth long tail is not."""

    def test_a_separate_cluster_is_flagged(self):
        import numpy as np
        import pandas as pd
        from app.services.guided_setup.health import odd_items, scale_members
        rng = np.random.default_rng(1)
        rows = [{"member": f"M{i:02d}", "amount": v} for i in range(20) for v in rng.uniform(1e3, 5e4, 10)]
        rows += [{"member": f"T{i}", "amount": v} for i in range(2) for v in rng.uniform(1e8, 5e9, 10)]
        df = pd.DataFrame(rows)
        (got,) = scale_members(df)
        assert (got["column"], got["measure"], sorted(got["values"]), got["rows"]) == ("member", "amount", ["T0", "T1"], 20)
        assert any(i["kind"] == "odd" and "another scale" in i["what"] for i in odd_items(df, "en"))

    def test_a_long_tail_signed_numbers_and_text_dates_are_not(self):
        import numpy as np
        import pandas as pd
        from app.services.guided_setup.health import scale_members
        rng = np.random.default_rng(2)
        tail = pd.DataFrame([{"member": f"M{i}", "amount": v} for i in range(60)
                             for v in rng.lognormal(3 + i * 0.08, 1, 10)])
        assert scale_members(tail) == []
        signed = tail.assign(amount=tail["amount"] - 30)
        assert scale_members(signed) == []
        days = pd.DataFrame([{"day": f"2024-01-{d:02d}", "amount": (1e7 if d == 1 else 10.0)} for d in range(1, 29)
                             for _ in range(3)])
        assert scale_members(days) == []


class TestPhase4MixedUnits:
    """A measure recorded in different units per category (bytes beside
    seconds) is never added across them."""

    def test_found_and_refused(self):
        import numpy as np
        import pandas as pd
        from app.services.analyst_panel import mixes_units
        from app.services.fact_sheet import mixed_units
        rng = np.random.default_rng(3)
        df = pd.DataFrame([{"kind": k, "volume": v} for k, scale in (("a", 60), ("b", 5e6))
                           for v in rng.uniform(scale / 2, scale * 2, 40)])
        mixed = mixed_units(df, ["volume"], ["kind"], {"kind": 2})
        assert mixed["volume"]["by"] == "kind"
        w = {"widget_type": "kpi", "config": {"measure": "volume", "aggregation": "sum"}}
        assert mixes_units(w, mixed)


class TestPhase4StockOverTime:
    """A column recorded as a level (a balance, a headcount at a date) is
    averaged when rolled up, never summed across periods."""

    def test_a_level_is_averaged(self):
        from app.services.semantic_guard import default_summary
        assert default_summary("on_hand", {"on_hand": {"number": "level"}}) == "avg"
        assert default_summary("on_hand", {"on_hand": {"number": "amount"}}) == "sum"


class TestPhase4WideScoreColumns:
    """Repeated score columns (s2_1 … s3_10) are read as one group with one
    average (see TestPlan24ScoreGroups for the shape rules)."""

    def test_wide_columns_become_one_group(self):
        import numpy as np
        import pandas as pd
        from app.services.guided_setup.groups import score_groups
        rng = np.random.default_rng(5)
        base = rng.normal(4.2, 0.6, 80)
        df = pd.DataFrame({f"s{2 + i // 10}_{i % 10 + 1}": np.clip(np.rint(base + rng.normal(0, 0.5, 80)), 3, 7)
                           for i in range(20)})
        (g,) = score_groups(df)
        assert len(g["columns"]) == 20


#: Phase 4.3: every trap the persona test found has a synthetic fixture here.
TRAP_FIXTURES = {
    "interval column": "TestPlan06DurationsAreNumbers",
    "DATE column": "TestPlan01DatesOfEveryKind",
    "lookup code 0": "TestPlan07ALookupCodeIsNotUnknown",
    "subtotal rows": "TestPlan12SubtotalRows",
    "partial last period": "TestPlan13And14PeriodsAndStrayDates",
    "out-of-range dates": "TestPlan13And14PeriodsAndStrayDates",
    "seasonal peak": "TestPlan15SeasonIsNotAnAnomaly",
    "tiny groups": "TestPlan16SmallGroupsDoNotRank",
    "mixed-scale members": "TestPlan17MembersOnAnotherScale",
    "mixed units": "TestPhase4MixedUnits",
    "fan-out join": "TestPlan19JoinSafety",
    "LEFT JOIN current": "TestPlan19JoinSafety",
    "wide score columns": "TestPhase4WideScoreColumns",
    "stock over time": "TestPhase4StockOverTime",
    "excluded identifier": "TestPlan110ExclusionsAreRules",
}


def test_every_trap_has_a_fixture():
    missing = [t for t, cls in TRAP_FIXTURES.items() if cls not in globals()]
    assert not missing and len(TRAP_FIXTURES) == 15


class TestOlistTitlesKeepTheirPromise:
    """Fresh benchmark run 2026-10-13 (lowest scenario): a share title over an
    average of days, a chart refused for naming a column that is one fact with
    the one it uses, and a title naming a column only a sibling dataset holds."""

    def _df(self):
        import pandas as pd
        return pd.DataFrame({"state": list("ABCD") * 5, "performance": ["Late", "On Time"] * 10,
                             "is_late": [1, 0] * 10, "days_late": [3.0, 0.0] * 10, "score": [2, 4, 3, 5] * 5})

    def test_a_declared_share_needs_a_share_in_any_language(self):
        from app.services.guided_setup.answer import shows_mismatch
        df = self._df()
        for title in ("Share of late deliveries", "نسبة التأخير", "Retards"):
            days = {"title": title, "shows": "share", "config": {"measure": "days_late", "aggregation": "avg"}}
            assert "a share of the whole" in shows_mismatch(days, df)
        flag = {"shows": "share", "config": {"measure": "is_late", "aggregation": "avg"}}
        assert shows_mismatch(flag, df) is None
        part = {"shows": "share", "config": {"dimension": "state", "measure": "days_late", "aggregation": "sum",
                                             "quick_calc": "percent_of_total"}}
        assert shows_mismatch(part, df) is None
        classified = {"shows": "share", "config": {"measure": "days_late", "aggregation": "avg"}}
        assert shows_mismatch(classified, df, column_meta={"days_late": {"number": "share"}}) is None

    def test_the_title_words_alone_decide_nothing(self):
        from app.services.guided_setup.answer import shows_mismatch, title_promises
        df = self._df()
        w = {"title": "Late rate", "shows": "average", "config": {"measure": "days_late", "aggregation": "avg"}}
        assert title_promises(w, df) is None and shows_mismatch(w, df) is None
        w["config"]["aggregation"] = "sum"
        assert "an average" in shows_mismatch(w, df)
        assert shows_mismatch({"config": {"measure": "days_late", "aggregation": "sum"}}, df) is None

    def test_one_fact_written_twice_counts_as_used(self):
        from app.services.guided_setup.answer import title_promises
        rate = {"title": "Late delivery rate by state",
                "config": {"dimension": "state", "measure": "is_late", "aggregation": "avg"}}
        assert title_promises(rate, self._df()) is None
        perf = {"title": "Score by performance", "config": {"dimension": "state", "measure": "score",
                                                            "aggregation": "avg"}}
        assert "performance" in title_promises(perf, self._df())

    def test_a_column_only_a_sibling_holds(self):
        from app.services.guided_setup.answer import title_promises
        df = self._df().drop(columns=["score"])
        card = {"title": "Review scores: late vs on time", "config": {"measures": ["days_late"], "aggregation": "avg"}}
        assert "another dataset" in title_promises(card, df, elsewhere={"review_score", "state"})
        assert title_promises(card, df, elsewhere={"state"}) is None


class TestLevelGroupsSaidPlainly:
    """Groups equal at the shown precision: "1 for every state", never
    "about the same … from 1 to 1"."""

    def _level(self, values, overall):
        import asyncio
        from app.services.guided_setup.answer import Gate, _key
        g = object.__new__(Gate)
        g.dates, g.percent, g.lang, g.level = set(), set(), "en", {}

        async def draw(_w):
            return {"rows": [{"name": "all", "value": overall}]}, ""
        g._draw = draw
        w = {"widget_type": "bar", "question": "q1", "title": "Typical delay by state",
             "config": {"dimension": "state", "measure": "days", "aggregation": "median"}}
        res = {"rows": [{"name": n, "value": v} for n, v in zip("ABC", values)]}
        number, _drawn = asyncio.run(g._same_everywhere(w, res))
        return g.level[_key(number)]

    def test_equal_groups(self):
        assert self._level([1, 1, 1], 1) == "1 for every state"

    def test_close_groups_keep_their_range(self):
        assert "(913 to 934)" in self._level([913, 920, 934], 925)


class TestTitleRulesDoNotOverreach:
    """Redesign 2026-10-13: the sibling rule refused every Taxi title with
    "trip" (trip_count), and "share of deliveries late" was refused for naming
    delivery_days -- the dataset's rows are deliveries."""

    def test_one_generic_word_is_not_a_sibling_column(self):
        import pandas as pd
        from app.services.guided_setup.answer import title_promises
        df = pd.DataFrame({"hour": [1, 2, 3, 4] * 5, "fare": [10.0, 12.0, 9.0, 15.0] * 5})
        w = {"title": "Earnings per trip by hour", "config": {"dimension": "hour", "measure": "fare", "aggregation": "avg"}}
        assert title_promises(w, df, elsewhere={"trip_count", "total_amount"}) is None

    def test_words_of_the_dataset_name_promise_nothing(self):
        import pandas as pd
        from app.services.guided_setup.answer import title_promises
        df = pd.DataFrame({"service": list("ABCD") * 5, "is_late": [1, 0, 0, 1] * 5,
                           "delivery_days": [3.0, 1.0, 2.0, 5.0, 4.0] * 4})
        w = {"title": "Share of deliveries that are late by service",
             "config": {"dimension": "service", "measure": "is_late", "aggregation": "avg"}}
        assert "delivery_days" in (title_promises(w, df) or "")
        assert title_promises(w, df, context="All deliveries with lateness and return status") is None


class TestOlderTitleCheckKnowsTwins:
    def test_a_value_of_a_twin_column_in_the_title(self):
        from app.services.analyst_panel import broken_promise
        profile = {"columns": [{"name": "state", "role": "categorical", "distinct": 4},
                               {"name": "performance", "role": "categorical", "distinct": 2,
                                "top_values": [{"value": "Late"}, {"value": "On Time"}]},
                               {"name": "is_late", "role": "numeric"}]}
        w = {"source": "model", "widget_type": "bar", "title": "Late rate by state",
             "config": {"dimension": "state", "measure": "is_late", "aggregation": "avg"}}
        assert "Late" in (broken_promise(w, profile) or "")
        assert broken_promise(w, profile, {"performance": ["is_late"], "is_late": ["performance"]}) is None


class TestAShareIsWhatTheChartDeclares:
    """The count-to-share repair follows the declared `shows`, not the title's
    words (owner 2026-10-13: no word lists tuned to the test connections)."""

    def _gate(self):
        from types import SimpleNamespace
        import pandas as pd
        from app.services.guided_setup.answer import Gate
        g = object.__new__(Gate)
        g.percent, g.twins, g.made = set(), {}, []
        g.inputs = SimpleNamespace(df=pd.DataFrame({"status": ["Back", "Kept", "Kept", "Back"], "region": list("NNSS")}))
        return g

    def _w(self, title, shows=None):
        w = {"title": title, "widget_type": "bar",
             "config": {"dimension": "region", "measure": "status", "aggregation": "count",
                        "filters": [{"column": "status", "op": "eq", "value": "Back"}]}}
        return {**w, "shows": shows} if shows else w

    def test_a_declared_share_is_drawn_as_one_in_any_language(self):
        for title in ("Returned by region", "المرتجع حسب المنطقة"):
            got = self._gate()._as_share(self._w(title, "share"))
            assert got["config"]["aggregation"] == "avg" and got["config"]["measure"].startswith("status_back")

    def test_a_declared_count_stays_a_count_whatever_the_title(self):
        got = self._gate()._as_share(self._w("Share returned by region", "count"))
        assert got["config"]["aggregation"] == "count"


class TestPlan24ScoreGroups:
    """Columns holding one kind of score, one per item, found from their
    values whatever their names; their row average is one number."""

    def _df(self):
        import numpy as np
        import pandas as pd
        rng = np.random.default_rng(4)
        quality = rng.normal(5, 1, 60)                # one thing the items all rate
        df = pd.DataFrame({f"item_{chr(97 + i)}": np.clip(np.rint(quality + rng.normal(0, 0.7, 60)), 3, 7)
                           for i in range(6)})
        for k in range(3):                           # codes on a similar range: they do not move together
            df[f"code{k}"] = rng.integers(1, 9, 60)
        df["flag"] = rng.integers(0, 2, 60)          # yes/no: never a score
        df["year"] = rng.integers(2020, 2025, 60)    # whole numbers beyond a scale
        df["amount"] = rng.uniform(10, 900, 60)      # not whole numbers
        return df

    def test_a_group_is_found_from_the_values(self):
        from app.services.guided_setup.groups import score_groups
        (g,) = score_groups(self._df())
        assert g["columns"] == [f"item_{chr(97 + i)}" for i in range(6)]
        assert g["name"] == "average_of_6_item_a_to_item_f" and g["expression"].endswith("/ 6")

    def test_names_do_not_matter(self):
        from app.services.guided_setup.groups import score_groups
        df = self._df().rename(columns={f"item_{chr(97 + i)}": n for i, n in
                                        enumerate(["جودة", "سرعة", "دقة", "أمانة", "تعاون", "مبادرة"])})
        (g,) = score_groups(df)
        assert len(g["columns"]) == 6

    def test_the_average_is_drawable(self):
        from app.services.guided_setup.groups import score_groups
        from app.services.widget_data import apply_calculated_columns
        df = self._df()
        (g,) = score_groups(df)
        made = apply_calculated_columns(df, [{k: v for k, v in g.items() if k not in ("columns", "low", "high")}])
        want = df[g["columns"]].mean(axis=1)
        assert abs(float(made[g["name"]].mean()) - float(want.mean())) < 1e-9


class TestOneBarPerMeasure:
    """A bar of several measures and no category draws one bar per measure --
    the items of a score group compared, the weakest named."""

    def test_engine_roles_and_finding(self):
        import pandas as pd
        from app.services.guided_setup.answer import finding
        from app.services.widget_data import get_widget_data_from_df
        from app.services.widget_roles import missing_roles
        df = pd.DataFrame({"q1": [4, 5, 4], "q2": [3, 3, 4], "q3": [5, 5, 5], "region": list("NSN")})
        cfg = {"measures": ["q1", "q2", "q3"], "aggregation": "avg", "filters": [{"column": "region", "op": "eq", "value": "N"}]}
        got = get_widget_data_from_df(df, cfg, "bar")
        assert [r["name"] for r in got["rows"]] == ["q1", "q2", "q3"]
        assert [r["value"] for r in got["rows"]] == [4.0, 3.5, 5.0]           # the filter applies to each bar
        assert missing_roles("bar", cfg) == [] and missing_roles("bar", {"measures": ["q1"]})
        text = finding({"widget_type": "bar", "config": cfg}, got, set(), "en")
        assert "q3" in text and "q2" in text

    def test_sorted_when_asked(self):
        import pandas as pd
        from app.services.widget_data import get_widget_data_from_df
        df = pd.DataFrame({"q1": [4, 5], "q2": [3, 3], "q3": [5, 5]})
        got = get_widget_data_from_df(df, {"measures": ["q1", "q2", "q3"], "aggregation": "avg", "sort": "asc"}, "bar")
        assert [r["name"] for r in got["rows"]] == ["q2", "q1", "q3"]


class TestPlan21EveryAskedQuestionIsStated:
    """Under a page's summary, each question the person asked that the page
    answers is stated from its chart's measured finding."""

    DEM = {"questions": [{"id": "q1", "text": "What is the average score?", "asked": True},
                         {"id": "q2", "text": "Which item is weakest?", "asked": True},
                         {"id": "q3", "text": "Extra idea", "asked": False}]}

    def _page(self):
        return {"widgets": [{"widget_type": "kpi", "question": "q1", "finding": "4.25"},
                            {"widget_type": "bar", "question": "q2", "finding": "Highest: a (5.21); lowest: g (4.15)"},
                            {"widget_type": "bar", "question": "q3", "finding": "Highest: x (9)"}]}

    def test_a_question_the_summary_left_out_gets_its_line(self):
        from app.services.guided_setup.answer import answer_lines
        lines = answer_lines(self._page(), self.DEM, "The average score is 4.25.")
        assert lines == ["• Which item is weakest: Highest: a (5.21); lowest: g (4.15)"]

    def test_nothing_is_said_twice_and_unasked_ideas_stay_out(self):
        from app.services.guided_setup.answer import answer_lines
        said = "The average score is 4.25; item g is weakest at 4.15 and a strongest at 5.21."
        assert answer_lines(self._page(), self.DEM, said) == []


class TestMembersSetApartByTheCheck:
    """What the check measured as unlike the rest of its column is left out of
    the design's charts by visible "is not" filters -- never deleted."""

    def _df(self):
        import pandas as pd
        return pd.DataFrame({"member": ["M01", "M02", "IDX A", "IDX B"], "amount": [1.0, 2.0, 9e9, 8e9]})

    def test_values_from_the_finding_become_filters(self):
        from app.services.guided_setup.answer import set_apart
        entry = {"health": [{"kind": "odd", "column": "member", "values": ["IDX A", "IDX B"]}]}
        (got,) = set_apart(entry, self._df(), [])
        assert got["filters"] == [{"column": "member", "op": "neq", "value": "IDX A"},
                                  {"column": "member", "op": "neq", "value": "IDX B"}]

    def test_an_older_finding_is_read_from_its_rule(self):
        from app.services.guided_setup.answer import set_apart
        entry = {"health": [{"kind": "odd", "column": "member",
                             "action": {"rule": "`member` not in ['IDX A', 'IDX B']"}}]}
        assert set_apart(entry, self._df(), [])[0]["values"] == ["IDX A", "IDX B"]

    def test_the_person_s_own_scope_on_that_column_wins(self):
        from app.services.guided_setup.answer import set_apart
        entry = {"health": [{"kind": "odd", "column": "member", "values": ["IDX A"]}]}
        assert set_apart(entry, self._df(), [{"column": "member", "op": "eq", "value": "IDX A"}]) == []

    def test_the_engine_leaves_them_out(self):
        from app.services.guided_setup.answer import set_apart
        from app.services.widget_data import get_widget_data_from_df
        entry = {"health": [{"kind": "odd", "column": "member", "values": ["IDX A", "IDX B"]}]}
        (got,) = set_apart(entry, self._df(), [])
        res = get_widget_data_from_df(self._df(), {"measure": "amount", "aggregation": "sum",
                                                  "filters": got["filters"]}, "kpi")
        assert res["rows"][0]["value"] == 3.0


def test_the_page_note_says_what_was_set_apart():
    from app.services.guided_setup.answer import scope_note
    note = scope_note([], [], 10, 10, "en", apart=[{"column": "member", "values": ["IDX A"]}])
    assert "Left out: “IDX A” in “member”" in note
    assert "مستبعد" in scope_note([], [], 10, 10, "ar", apart=[{"column": "member", "values": ["IDX A"]}])


class TestChangeOverThePeriod:
    """'How much did it go up' is the level on the last date against the first
    -- not the average of a daily-change column (index +66.8% read 0.264)."""

    def _df(self):
        import pandas as pd
        return pd.DataFrame({"day": pd.to_datetime(["2023-01-02", "2023-01-02", "2023-06-01", "2023-12-28", "2023-12-28"]),
                             "member": ["A", "B", "A", "A", "B"], "close": [40.0, 7.0, 55.0, 72.0, 9.0],
                             "daily_change": [0.1, 0.2, 0.3, 0.2, 0.4]})

    def test_the_change_of_one_member(self):
        from app.services.guided_setup.answer import finding
        from app.services.widget_data import get_widget_data_from_df
        cfg = {"measure": "close", "aggregation": "avg", "change_over": "day",
               "filters": [{"column": "member", "op": "eq", "value": "A"}]}
        got = get_widget_data_from_df(self._df(), cfg, "kpi")
        assert got["rows"][0]["value"] == 80.0 and got["change"]["from"] == 40.0 and got["change"]["to"] == 72.0
        text = finding({"widget_type": "kpi", "config": cfg}, got, set(), "en")
        assert text.startswith("+80.0% (from 40 on 2023-01-02 to 72 on 2023-12-28")

    def test_one_date_only_has_no_change(self):
        import pandas as pd
        from app.services.widget_data import get_widget_data_from_df
        df = pd.DataFrame({"day": pd.to_datetime(["2023-01-02"]), "close": [40.0]})
        got = get_widget_data_from_df(df, {"measure": "close", "change_over": "day"}, "kpi")
        assert got["rows"] == []


class TestAQuestionAboutAnotherDatasetsRows:
    """"How much did <one member> go up?" is not answered by a chart on rows
    that never hold that member (another dataset's query keeps to it)."""

    def test_the_query_s_kept_values(self):
        from app.services.guided_setup.datasets import narrowed_to
        assert narrowed_to("SELECT d, close FROM prices WHERE member = 'M7' AND d >= '2023-01-01'") == {"m7"}
        assert narrowed_to("SELECT * FROM t WHERE region IN ('North', 'South')") == {"north", "south"}
        assert narrowed_to("not sql at all ((") == set()

    def test_a_value_these_rows_hold_is_not_foreign(self):
        import pandas as pd
        from app.services.guided_setup.answer import _not_held, names_foreign
        df = pd.DataFrame({"member": ["M7", "M8"], "close": [1.0, 2.0]})
        assert _not_held({"m7", "m9"}, df) == {"m9"}
        assert names_foreign("How much did M9 go up in 2023?", {"m9"}) == "m9"
        assert names_foreign("How did the market do?", {"m9"}) is None

    def test_the_line_is_not_written_under_another_question(self):
        import asyncio
        import pandas as pd
        from types import SimpleNamespace
        from app.services.guided_setup.answer import Gate
        g = object.__new__(Gate)
        g.foreign, g.asked_text = {"m9"}, {"q2": "How much did M9 go up?"}
        seen = {}

        def check(widget):
            seen["question"] = widget.get("question")
            return None, "stop here"
        g._check = check
        g.inputs = SimpleNamespace(df=pd.DataFrame({"close": [1.0]}))
        asyncio.run(g.one({"widget_type": "kpi", "title": "Index growth", "question": "q2",
                           "config": {"measure": "close"}}))
        assert seen["question"] == ""


class TestSharesInAnyScript:
    """Held-out H3 (2026-10-13): a status column of two Arabic values had no
    share at all, and every Arabic-named column was skipped."""

    def test_two_text_values_give_a_share_each_in_any_language(self):
        import pandas as pd
        from app.services.guided_setup.answer import share_columns
        from app.services.widget_data import apply_calculated_columns, get_widget_data_from_df
        df = pd.DataFrame({"الفرع": ["أ", "أ", "ب", "ب"], "الحالة": ["مرتجع", "تم التسليم", "مرتجع", "مرتجع"]})
        shares = share_columns(df)
        twin = next(c for c in shares if c.get("value") == "مرتجع")
        made = apply_calculated_columns(df, [{k: v for k, v in twin.items() if k not in ("of", "is", "value")}])
        got = get_widget_data_from_df(made, {"dimension": "الفرع", "measure": twin["name"], "aggregation": "avg"}, "bar")
        assert {r["name"]: r["value"] for r in got["rows"]} == {"أ": 50.0, "ب": 100.0}

    def test_a_flag_with_a_non_ascii_name(self):
        import pandas as pd
        from app.services.guided_setup.answer import share_columns
        df = pd.DataFrame({"متأخر": [True, False, True]})
        assert any(c["is"] == "yes" for c in share_columns(df))


class TestSummariesKeepTheirGroupSize:
    """Held-out H1 (2026-10-13): a unit of 4 reviews ranked best in a summary
    with one row per unit. A summary query keeps how many rows each of its
    rows stands for, and the ranking rule weighs groups by it."""

    def test_a_grouping_query_gets_its_count(self):
        from app.services.guided_setup.datasets import with_group_size
        sql, size = with_group_size("SELECT unit, AVG(score) AS avg_score FROM reviews GROUP BY unit", "postgresql")
        assert size == "row_count" and "COUNT(*) AS row_count" in sql
        same, own = with_group_size("SELECT unit, COUNT(*) AS n, AVG(score) FROM reviews GROUP BY unit", "postgresql")
        assert own == "n" and "row_count" not in same
        assert with_group_size("SELECT unit, score FROM reviews", "postgresql") == \
            ("SELECT unit, score FROM reviews", None)

    def _summary(self):
        import pandas as pd
        return pd.DataFrame({"unit": ["Big", "Mid", "Tiny"], "avg_score": [3.5, 3.2, 4.5], "row_count": [180, 140, 4]})

    def test_the_tiny_group_leaves_the_ranking(self):
        from app.services.widget_data import get_widget_data_from_df
        cfg = {"dimension": "unit", "measure": "avg_score", "aggregation": "avg", "min_group_rows": 30,
               "size_column": "row_count"}
        got = get_widget_data_from_df(self._summary(), cfg, "bar")
        assert {r["name"] for r in got["rows"]} == {"Big", "Mid"} and got["small_groups"]["hidden"] == 1

    def test_the_same_through_duckdb(self, tmp_path, monkeypatch):
        from app.core.config import settings
        from app.services import duck_agg
        path = tmp_path / "s.parquet"
        self._summary().to_parquet(path)
        monkeypatch.setattr(settings, "widget_duckdb_pushdown", True)
        cfg = {"dimension": "unit", "measure": "avg_score", "aggregation": "avg", "min_group_rows": 30,
               "size_column": "row_count"}
        frame, reason = duck_agg.try_aggregate(str(path), cfg, ["unit", "avg_score", "row_count"])
        if frame is None:
            import pytest
            pytest.skip(f"DuckDB did not take this plan: {reason}")
        assert set(frame.iloc[:, 0]) == {"Big", "Mid"}


class TestAColumnComparedWithAColumn:
    """Held-out H3: "how many were late" filters delivery days > promised days;
    no engine compares two columns in a filter, so the setup derives it."""

    def test_a_derived_flag_replaces_the_filter(self):
        import pandas as pd
        from types import SimpleNamespace
        from app.services.guided_setup.answer import Gate
        from app.services.widget_data import get_widget_data_from_df
        g = object.__new__(Gate)
        g.made = []
        g.inputs = SimpleNamespace(df=pd.DataFrame({"days": [1, 4, 6, 2], "promised": [2, 3, 5, 2]}))
        w = {"widget_type": "kpi", "config": {"measure": "days", "aggregation": "count",
                                               "filters": [{"column": "days", "op": "gt", "value": "promised"}]}}
        fixed = g._compare_columns(w)
        assert fixed["config"]["filters"] == [{"column": "days_gt_promised", "op": "eq", "value": 1}]
        assert g.made and get_widget_data_from_df(g.inputs.df, fixed["config"], "kpi")["rows"][0]["value"] == 2

    def test_platform_made_columns_are_not_named_by_a_title(self):
        import pandas as pd
        from types import SimpleNamespace
        from app.services.guided_setup.answer import Gate
        g = object.__new__(Gate)
        g.made = []
        g.inputs = SimpleNamespace(df=pd.DataFrame({"r1": [1], "average_of_2_r1_to_r2": [1.0]}),
                                   shares=[], groups=[{"name": "average_of_2_r1_to_r2"}])
        assert list(g._data_only().columns) == ["r1"]


class TestAFilterOnTheWrongColumn:
    """Held-out H3: "branch = مرتجع" -- the value belongs to the status column.
    Moved by the values, never by names."""

    def _gate(self):
        import pandas as pd
        from types import SimpleNamespace
        from app.services.guided_setup.answer import Gate
        g = object.__new__(Gate)
        g.made = []
        g.inputs = SimpleNamespace(df=pd.DataFrame({"الفرع": ["أ", "ب", "أ"], "الحالة": ["مرتجع", "تم", "تم"],
                                                    "note": ["x", "y", "z"]}))
        return g

    def test_moved_to_the_one_column_that_holds_it(self):
        w = {"config": {"filters": [{"column": "الفرع", "op": "eq", "value": "مرتجع"}]}}
        got = self._gate()._retarget_filters(w)
        assert got["config"]["filters"] == [{"column": "الحالة", "op": "eq", "value": "مرتجع"}]

    def test_left_alone_when_no_column_or_the_right_one_holds_it(self):
        g = self._gate()
        nowhere = {"config": {"filters": [{"column": "الفرع", "op": "eq", "value": "غير موجود"}]}}
        assert g._retarget_filters(nowhere) == nowhere
        right = {"config": {"filters": [{"column": "الحالة", "op": "eq", "value": "مرتجع"}]}}
        assert g._retarget_filters(right) == right

    def test_comparisons_wait_until_after_the_checks(self):
        import pandas as pd
        g = self._gate()
        g.inputs.df = pd.DataFrame({"days": [1, 4], "promised": [2, 3]})
        w = {"config": {"filters": [{"column": "days", "op": "gt", "value": "promised"}]}}
        clean, aside = g._set_aside_comparisons(w)
        assert clean["config"]["filters"] == [] and aside == w["config"]["filters"]


class TestAChartAnswersOnlyItsKindOfQuestion:
    """A question that wants a share is not answered by a chart of averages
    (held-out H3: average days stood under "which branch has the highest
    return share"). Declared by the model on both sides, in any language."""

    def test_kinds(self):
        from app.services.guided_setup.answer import answers_kind
        assert answers_kind("share", "share") and answers_kind("count", "total")
        assert not answers_kind("average", "share") and not answers_kind("total", "average")
        assert answers_kind(None, "share") and answers_kind("average", None) and answers_kind("list", "share")

    def test_the_link_is_dropped_not_the_chart(self):
        import asyncio
        import pandas as pd
        from types import SimpleNamespace
        from app.services.guided_setup.answer import Gate
        g = object.__new__(Gate)
        g.foreign, g.asked_text, g.wants = set(), {"q1": "أي فرع لديه أعلى نسبة مرتجعات؟"}, {"q1": "share"}
        seen = {}

        def check(widget):
            seen["question"] = widget.get("question")
            return None, "stop"
        g._check = check
        g.inputs = SimpleNamespace(df=pd.DataFrame({"x": [1]}))
        asyncio.run(g.one({"widget_type": "bar", "title": "متوسط الأيام", "question": "q1", "shows": "average",
                           "config": {"dimension": "x", "measure": "x"}}))
        assert seen["question"] == ""

    def test_demand_keeps_a_known_kind_only(self):
        from app.services.guided_setup.demand import WANTS
        from app.services.guided_setup.answer import SHOWS
        assert set(WANTS) <= set(SHOWS)


def test_derived_columns_with_non_ascii_names_are_created():
    """Held-out H3 dashboard (2026-10-13): "'الحالة_مرتجع_pct' is not a column":
    the used-columns search ran over JSON with Arabic escaped, so a derived
    column with a non-ASCII name was never created on the dataset."""
    from types import SimpleNamespace
    from app.services.guided_setup.answer import derived_for
    twin = {"name": "الحالة_مرتجع_pct", "expression": 'IF(`الحالة` == "مرتجع", 100, 0)', "dtype": "numeric",
            "of": "الحالة", "is": "value", "value": "مرتجع"}
    pages = [{"widgets": [{"config": {"dimension": "الفرع", "measure": "الحالة_مرتجع_pct", "aggregation": "avg"}}]}]
    made = derived_for(pages, SimpleNamespace(shares=[twin], groups=[]))
    assert [c["name"] for c in made["calculated_columns"]] == ["الحالة_مرتجع_pct"]
    assert "value" not in made["calculated_columns"][0] and "of" not in made["calculated_columns"][0]


class TestDisplayNamesInThePersonsLanguage:
    """Persona S9 (Arabic UI): "تصفية حسب corp name", "تفاصيل corp name واحد" --
    raw column names inside Arabic text. The design names each column it uses
    in the person's language; generated text uses that name."""

    def test_names_kept_only_for_real_columns_and_short_text(self):
        from app.services.guided_setup.answer import clean_names, display_name as _label
        names = clean_names({"names": {"corp_name": "السلاح", "nope": "x", "rank_name": "y" * 80}},
                            ["corp_name", "rank_name"])
        assert names == {"corp_name": "السلاح"}
        assert _label("corp_name", names) == "السلاح" and _label("rank_name", names) == "rank name"

    def test_filters_and_detail_pages_use_them(self):
        from app.services.guided_setup import dress
        widgets = [{"widget_type": "bar", "config": {"dimension": "corp_name", "measure": "score", "aggregation": "avg"}}]
        profile = {"columns": [{"name": "corp_name", "role": "categorical", "distinct": 7, "is_identifier": False,
                                "is_personal": False}, {"name": "score", "role": "numeric"}]}
        got = dress.slicers(widgets, profile, set(), set(), "ar", {"corp_name": "السلاح"})
        assert got and "corp name" not in got[0]["title"] and "السلاح" in got[0]["title"]


class TestStoredKindsBeforeNames:
    """§7 audit (2026-10-13): where a column's stored kind exists, its name
    decides nothing."""

    def test_a_classified_count_keeps_its_trend_finding(self):
        from app.services.guided_setup.health import sensible
        trend = {"kind": "trend", "columns": ["open_tickets"], "figures": {}}
        assert not sensible(trend)                                   # unclassified: judged by its words
        assert sensible(trend, {"open_tickets": "count"})            # classified: its kind decides

    def test_the_panel_reads_a_rate_from_its_stored_kind(self):
        from app.services.analyst_panel import series_backbone
        profile = {"columns": [{"name": "day", "role": "datetime"},
                               {"name": "نسبة_الإلغاء", "role": "numeric", "number": "share"},
                               {"name": "orders", "role": "numeric", "number": "count"},
                               {"name": "revenue", "role": "numeric", "number": "amount"}],
                   "structure": {"date_range": ["2024-01-01", "2024-12-31"]}}
        got = series_backbone(profile, dates=["day"])
        titles = [w["title"] for w in got]
        assert any("نسبة الإلغاء" in t and t.startswith("Average") for t in titles), titles

    def test_a_rate_is_a_percentage_before_it_is_money(self):
        from app.services.metadata.infer_semantic import classify_semantic_type
        assert classify_semantic_type("fee_rate", []) == "percentage"
        assert classify_semantic_type("fee", []) == "currency"


def test_a_declared_chart_is_not_rewritten_by_its_title_words():
    from app.services.analyst_panel import _mix_from_filter
    w = {"widget_type": "bar", "title": "Gender mix by department",
         "config": {"dimension": "department", "measure": "id", "aggregation": "count",
                    "filters": [{"column": "gender", "op": "eq", "value": "F"}]}}
    assert _mix_from_filter(w)["config"].get("bar_mode") == "stacked100"     # undeclared: words still help
    assert _mix_from_filter({**w, "shows": "count"}) == {**w, "shows": "count"}


class TestTooFewToRank:
    """Persona S6 (2026-10-13): 29 listings by governorate, the floor of 30
    could not apply, and the page said "lowest: Aswan" from one listing."""

    def _df(self):
        import pandas as pd
        return pd.DataFrame({"area": ["A"] * 12 + ["B"] * 10 + ["C"] * 6 + ["D"],
                             "price": [10.0] * 12 + [9.0] * 10 + [11.0] * 6 + [3.0]})

    def test_drawn_but_not_ranked(self):
        from app.services.guided_setup.answer import finding
        from app.services.widget_data import get_widget_data_from_df
        cfg = {"dimension": "area", "measure": "price", "aggregation": "median", "min_group_rows": 30}
        got = get_widget_data_from_df(self._df(), cfg, "bar")
        assert len(got["rows"]) == 4 and got["small_groups"]["too_few"] == 4
        text = finding({"widget_type": "bar", "config": cfg}, got, set(), "en")
        assert "too few" in text and "D" not in text.split(":")[0]

    def test_enough_rows_still_rank(self):
        import pandas as pd
        from app.services.guided_setup.answer import finding
        from app.services.widget_data import get_widget_data_from_df
        df = pd.DataFrame({"area": ["A"] * 40 + ["B"] * 35 + ["D"], "price": [10.0] * 40 + [9.0] * 35 + [3.0]})
        cfg = {"dimension": "area", "measure": "price", "aggregation": "median", "min_group_rows": 30}
        got = get_widget_data_from_df(df, cfg, "bar")
        assert "too_few" not in got["small_groups"] and "Highest" in finding({"widget_type": "bar", "config": cfg},
                                                                            got, set(), "en")


class TestALeaderMadeByOneRow:
    """Persona S1: one order of 80,995 units made a product "the best seller"."""

    def test_said_when_one_row_carries_the_leader(self):
        import pandas as pd
        from app.services.guided_setup.answer import one_row_leader
        df = pd.DataFrame({"item": ["A", "A", "B", "B", "B"], "qty": [9000, 10, 300, 320, 310]})
        w = {"widget_type": "bar", "config": {"dimension": "item", "measure": "qty", "aggregation": "sum"}}
        res = {"rows": [{"name": "A", "value": 9010}, {"name": "B", "value": 930}]}
        assert round(one_row_leader(w, res, df, set())) == 100

    def test_not_for_a_leader_built_from_many_rows_or_an_average(self):
        import pandas as pd
        from app.services.guided_setup.answer import one_row_leader
        df = pd.DataFrame({"item": ["A"] * 5 + ["B"] * 5, "qty": [100] * 5 + [90] * 5})
        w = {"widget_type": "bar", "config": {"dimension": "item", "measure": "qty", "aggregation": "sum"}}
        res = {"rows": [{"name": "A", "value": 500}, {"name": "B", "value": 450}]}
        assert one_row_leader(w, res, df, set()) is None
        w["config"]["aggregation"] = "avg"
        assert one_row_leader(w, res, df, set()) is None


def test_a_dataset_name_word_counts_with_its_ending():
    """Taxi (2026-10-13): "earnings per trip" was refused for naming
    trip_distance_miles on a dataset named "...trips..."."""
    import pandas as pd
    from app.services.guided_setup.answer import title_promises
    df = pd.DataFrame({"hour": [1, 2, 3, 4] * 5, "total": [10.0, 12.0, 9.0, 15.0] * 5,
                       "trip_distance_miles": [1.0, 2.5, 3.0, 0.5, 4.0] * 4})
    w = {"title": "Earnings per trip by hour", "config": {"dimension": "hour", "measure": "total", "aggregation": "avg"}}
    assert "trip_distance_miles" in (title_promises(w, df) or "")
    assert title_promises(w, df, context="All taxi trips with zone details") is None


class TestAChartUsesItsQuestionsColumns:
    """Olist benchmark: "do late deliveries get lower review SCORES" was
    answered by days late over time -- both averages. The demand names the
    columns each question rests on; a chart using none of them loses it."""

    def _gate(self):
        import pandas as pd
        from types import SimpleNamespace
        from app.services.guided_setup.answer import Gate
        g = object.__new__(Gate)
        g.about, g.percent, g.made = {"q1": ["review_score", "is_late"]}, {"is_late_pct"}, []
        g.inputs = SimpleNamespace(df=pd.DataFrame({"review_score": [5], "is_late": [1], "days_late": [2.0],
                                                    "is_late_pct": [100.0]}),
                                   shares=[{"name": "is_late_pct", "of": "is_late"}], groups=[])
        return g

    def test_kept_or_dropped_by_its_columns(self):
        g = self._gate()
        assert g._about_question({"question": "q1", "config": {"measure": "review_score", "dimension": "is_late"}})
        assert g._about_question({"question": "q1", "config": {"measure": "is_late_pct"}})            # its share
        assert not g._about_question({"question": "q1", "config": {"measure": "days_late"}})

    def test_not_judged_without_this_dataset_s_columns(self):
        g = self._gate()
        g.about = {"q1": ["somewhere_else"]}
        assert g._about_question({"question": "q1", "config": {"measure": "days_late"}})

    def test_a_zero_one_number_becomes_a_percentage(self):
        import pandas as pd
        from app.services.guided_setup.answer import share_columns
        (twin,) = share_columns(pd.DataFrame({"is_late": [1, 0, 0, 1]}))
        assert twin["name"] == "is_late_pct" and twin["expression"] == "IF(`is_late` == 1, 100, 0)"


def test_a_filter_that_keeps_every_row_does_not_keep_a_title_s_promise():
    """Olist: a one-number card "Late vs. On Time" filtered is_late in [0, 1]
    showed every order's average (4.14; late orders were 2.55)."""
    import pandas as pd
    from app.services.guided_setup.answer import title_promises
    df = pd.DataFrame({"performance": ["Late", "On Time"] * 10, "is_late": [1, 0] * 10,
                       "review": [2, 4, 3, 5] * 5})
    card = {"title": "Review scores: Late vs. On Time", "widget_type": "card",
            "config": {"measures": ["review"], "aggregation": "avg",
                       "filters": [{"column": "is_late", "op": "in", "value": [0, 1]}]}}
    assert title_promises(card, df) is not None
    split = {"title": "Review scores: Late vs. On Time", "widget_type": "bar",
             "config": {"dimension": "is_late", "measure": "review", "aggregation": "avg"}}
    assert title_promises(split, df) is None


def _synthetic_gate(df):
    """A real Gate over a synthetic frame: profile, share twins, no model."""
    from types import SimpleNamespace
    from app.services.analytics import detect_types
    from app.services.dataset_profile import build_profile
    from app.services.guided_setup.answer import Gate, menu, share_columns
    from app.services.widget_data import apply_calculated_columns
    shares = share_columns(df)
    df = apply_calculated_columns(df, [{k: v for k, v in c.items() if k not in ("of", "is", "value")}
                                       for c in shares if c.get("is") != "label"])
    profile = build_profile(df, detect_types(df), {})
    inputs = SimpleNamespace(df=df, profile=profile, column_meta={}, shares=shares, groups=[], knowledge=None,
                             ineligible=lambda: set(), live=False, probe=None, drawn={})
    allowed, _ = menu(profile, "balanced")
    return Gate(inputs, {}, allowed, {"q1"}, [], "en", set(), "balanced")


def test_a_share_filtered_to_its_own_outcome_is_not_100_percent():
    """Olist: avg(is_late) over the late rows read "100.0%"."""
    import pandas as pd
    g = _synthetic_gate(pd.DataFrame({"state": list("ABCD") * 10, "is_late": [1, 0, 0, 0, 1] * 8,
                                      "score": [3.0, 4.0, 5.0, 4.0, 2.0] * 8}))
    checked, why = g._check({"widget_type": "kpi", "title": "Late share", "question": "q1", "shows": "share",
                             "config": {"measure": "is_late", "aggregation": "avg",
                                        "filters": [{"column": "is_late", "op": "eq", "value": 1}]}})
    assert checked is not None, why
    assert checked["config"]["measure"] == "is_late_pct"
    assert not any(f.get("column") == "is_late" for f in checked["config"].get("filters") or [])


def test_an_unlinked_chart_is_kept_not_refused():
    """A chart whose kind does not match its question loses the question but
    stays on the page (it was refused as "does not say which question")."""
    import asyncio
    import pandas as pd
    g = _synthetic_gate(pd.DataFrame({"state": list("ABCD") * 10, "is_late": [1, 0, 0, 0, 1] * 8,
                                      "score": [3.0, 4.0, 5.0, 4.0, 2.0] * 8}))
    g.wants = {"q1": "share"}
    kept, why = asyncio.run(g.one({"widget_type": "bar", "title": "Score by state", "question": "q1",
                                   "shows": "average", "config": {"dimension": "state", "measure": "score",
                                                                  "aggregation": "avg"}}))
    assert kept is not None, why
    assert kept.get("question") == "" and "_unlinked" not in kept


class TestAScopeThatIsTheDatasetItself:
    """Employees benchmark: "current staff" became "from_date >= 2002-08-01"
    on a dataset of current employees, keeping 673 of 240,124 rows."""

    def test_the_dataset_s_own_subject_is_not_a_cut(self):
        from app.services.guided_setup.demand import describes_dataset
        item = {"said": "current staff", "column": "from_date", "op": "gte", "values": ["2002-08-01"]}
        assert describes_dataset(item, "Current employees with salary and department")
        assert describes_dataset({**item, "said": "الموظفون الحاليون"}, "الموظفون الحاليون مع الرواتب")

    def test_a_stated_figure_or_a_list_stays_a_scope(self):
        from app.services.guided_setup.demand import describes_dataset
        assert not describes_dataset({"said": "since 2020", "op": "gte", "values": ["2020-01-01"]}, "Sales since 2015")
        assert not describes_dataset({"said": "current staff", "op": "in", "values": ["x"]}, "Current employees")
        assert not describes_dataset({"said": "last month", "op": "gte", "values": ["2024-11-01"]}, "Orders")


def test_a_count_of_people_counts_people_not_rows():
    """Employees: one person per assignment row; "how many people" counted rows."""
    import pandas as pd
    g = _synthetic_gate(pd.DataFrame({"emp_no": [1, 1, 2, 3, 3, 3], "dept": list("ABABAB"),
                                      "salary": [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]}))
    g.wants, g.about = {"q1": "count"}, {"q1": ["emp_no"]}
    w = {"widget_type": "kpi", "question": "q1", "config": {"measure": "salary", "aggregation": "count"}}
    assert g._count_whom(w)["config"] == {"measure": "emp_no", "aggregation": "countd"}
    g.wants = {"q1": "total"}
    assert g._count_whom(w) == w


def test_a_count_of_a_category_is_not_turned_into_its_kinds():
    import pandas as pd
    g = _synthetic_gate(pd.DataFrame({"status": ["Returned", "Delivered"] * 30, "weight": [1.0, 2.0] * 30}))
    g.wants, g.about = {"q1": "count"}, {"q1": ["status"]}
    w = {"widget_type": "kpi", "question": "q1", "config": {"measure": "weight", "aggregation": "count",
                                                            "filters": [{"column": "status", "op": "eq",
                                                                         "value": "Returned"}]}}
    assert g._count_whom(w) == w


def test_a_title_naming_another_dataset_s_value_is_refused():
    """EGX: "COMI total gain in 2023" drawn on the index dataset read the index's change."""
    import asyncio
    import pandas as pd
    g = _synthetic_gate(pd.DataFrame({"day": pd.date_range("2023-01-01", periods=40), "close": range(40)}))
    g.foreign = {"m7"}
    kept, why = asyncio.run(g.one({"widget_type": "kpi", "title": "M7 total gain in 2023", "question": "q1",
                                   "config": {"measure": "close", "aggregation": "avg"}}))
    assert kept is None and "another dataset" in why


def test_a_chart_that_computes_a_change_keeps_a_change_title():
    """EGX: "COMI price change in 2023" over close (change_over) was refused
    for naming the daily column change_pct."""
    import pandas as pd
    from app.services.guided_setup.answer import title_promises
    df = pd.DataFrame({"day": pd.date_range("2023-01-01", periods=30), "close": range(30),
                       "change_pct": [0.1, -0.2, 0.3] * 10})
    w = {"title": "Price change in 2023", "widget_type": "kpi",
         "config": {"measure": "close", "aggregation": "avg", "change_over": "day"}}
    assert title_promises(w, df) is None
    plain = {"title": "Price change in 2023", "widget_type": "kpi", "config": {"measure": "close", "aggregation": "avg"}}
    assert "change_pct" in (title_promises(plain, df) or "")
