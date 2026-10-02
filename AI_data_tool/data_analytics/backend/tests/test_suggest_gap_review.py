"""Corrections from the five-dataset gap review (2026-10-02).

An analyst's reference dashboard was designed for each of five datasets
(enrolments, daily ops, call records, workforce, Olist) and the platform's
three engines were run on the same data. Each test below pins one gap the
comparison found: the wrong numbers it offered, and the interactive structure
it lacked.
"""
import numpy as np
import pandas as pd

from app.services.analyst_panel import (
    _drop_dependent_predictors, _no_sum_of_rates, _whole_needs_a_total, date_as_number,
    dependent_split, detail_table, mixes_units, one_unit, refusal_code, repair_and_check,
    slicers_for, with_slicers)
from app.services.analytics import detect_types
from app.services.dataset_profile import build_profile
from app.services.fact_sheet import build_facts, one_to_one
from app.services.insights import order_event_dates
from app.services.semantic_guard import default_summary, is_intensive
from app.services.suggest_dataset_dashboard import validate_widget


def _enrolments(n=240, seed=1):
    rng = np.random.default_rng(seed)
    faculty = rng.choice(["Engineering", "Law", "Medicine", "Arts"], n)
    fee = pd.Series(faculty).map({"Engineering": 12000, "Law": 9500, "Medicine": 15800, "Arts": 8800})
    return pd.DataFrame({
        "student_id": np.arange(100000, 100000 + n), "faculty": faculty, "tuition_fee": fee,
        "final_score": rng.normal(70, 8, n).round(1),
        "enrolled_on": pd.Timestamp("2025-09-01") + pd.to_timedelta(rng.integers(0, 120, n), "D"),
        "hire_year": rng.integers(1985, 2000, n),
    })


def _profile(df):
    tm = detect_types(df)
    return build_profile(df, tm, {})


# ── wrong numbers ─────────────────────────────────────────────────────────────

def test_a_summed_year_is_refused_before_it_is_offered():
    """'Total hire year' passed the probe and would have shown the render
    path's semantic veto as an error on the dashboard."""
    df = _enrolments()
    ok, why = validate_widget({"widget_type": "kpi", "title": "Total hire year",
                               "config": {"measure": "hire_year", "aggregation": "sum"}}, _profile(df))
    assert not ok and "adds up years" in why
    assert refusal_code(why) == "meaning"


def test_daily_distinct_counts_are_averaged_not_totalled():
    for c in ("active_sellers", "unique_customers", "unique_products_sold", "distinct_users", "dau"):
        assert is_intensive(c) and default_summary(c) == "avg", c
    for c in ("total_orders", "total_revenue", "active_minutes", "uniqueness_score_raw"):
        assert default_summary(c) == "sum" or c == "uniqueness_score_raw", c
    w = _no_sum_of_rates({"widget_type": "line", "title": "Active sellers",
                          "config": {"dimension": "day_date", "measure": "active_sellers", "aggregation": "sum"}})
    assert w["config"]["aggregation"] == "avg"


def test_a_summed_card_drops_what_cannot_be_totalled():
    w = _no_sum_of_rates({"widget_type": "card", "title": "Summary",
                          "config": {"measures": ["total_orders", "total_revenue", "unique_customers",
                                                  "active_sellers"]}})
    assert w["config"]["measures"] == ["total_orders", "total_revenue"]
    assert "aggregation" not in w["config"]


def test_a_pie_of_averages_becomes_a_bar():
    w = _whole_needs_a_total({"widget_type": "pie", "title": "Top 20 Products Price Share",
                              "config": {"dimension": "product_id", "measure": "price",
                                         "aggregation": "avg", "limit": 20}})
    assert w["widget_type"] == "bar" and w["title"] == "Top 20 Products Price"
    same = {"widget_type": "pie", "title": "Orders by status",
            "config": {"dimension": "status", "measure": "order_id", "aggregation": "countd"}}
    assert _whole_needs_a_total(same) is same


def test_an_averaged_date_is_not_a_duration():
    dates = {"order_delivered_carrier_date", "order_purchase_timestamp"}
    bad = {"widget_type": "line", "title": "Time to Carrier Trend",
           "config": {"dimension": "order_purchase_timestamp", "dimension_granularity": "month",
                      "measure": "order_delivered_carrier_date", "aggregation": "avg"}}
    why = date_as_number(bad, dates)
    assert why and refusal_code(why) == "meaning"
    counted = {"widget_type": "line", "title": "Orders per month",
               "config": {"dimension": "order_purchase_timestamp", "measure": "order_purchase_timestamp",
                          "aggregation": "count"}}
    tenure = {"widget_type": "bubble", "title": "Tenure vs pay",
              "config": {"dimension": "dept", "measure": "salary", "measure2": "hire_date", "aggregation": "avg"}}
    assert date_as_number(counted, dates) is None and date_as_number(tenure, {"hire_date"}) is None


def test_two_columns_that_are_one_fact_are_not_split_by_together():
    df = _enrolments()
    pairs = one_to_one(df, ["faculty", "tuition_fee", "hire_year"])
    assert pairs == {"faculty": ["tuition_fee"], "tuition_fee": ["faculty"]}
    tm = detect_types(df)
    from app.services.insights import effective_roles
    facts = build_facts(df, effective_roles(tm, {}))
    assert facts["one_to_one"]["faculty"] == ["tuition_fee"]
    assert any(f["kind"] == "same" for f in facts["facts"])
    tree = {"widget_type": "sunburst", "title": "Faculty > Fee",
            "config": {"levels": ["faculty", "tuition_fee"], "measure": "student_id", "aggregation": "countd"}}
    why = dependent_split(tree, pairs)
    assert why and refusal_code(why) == "repeat"
    model = _drop_dependent_predictors({"widget_type": "model_linear", "title": "Score drivers",
                                        "config": {"measure": "final_score",
                                                   "predictors": ["faculty", "tuition_fee", "hire_year"]}}, pairs)
    assert model["config"]["predictors"] == ["faculty", "hire_year"]


def test_a_city_inside_a_country_is_still_a_nesting():
    df = pd.DataFrame({"country": ["EG"] * 30 + ["SA"] * 30,
                       "city": ["Cairo", "Giza", "Alex"] * 10 + ["Riyadh", "Jeddah", "Dammam"] * 10})
    assert one_to_one(df, ["country", "city"]) == {}


def test_a_model_clusters_one_unit_at_a_time():
    mixed = {"ROUNDED_VOLUME": {"by": "SERVICE", "high": "GPRS", "low": "Voice", "common": "Voice",
                                "high_median": 1e6, "low_median": 60}}
    cluster = {"widget_type": "model_cluster", "title": "Call Behavior Clusters",
               "config": {"measures": ["ROUNDED_VOLUME", "RATED_AMOUNT"]}}
    assert mixes_units(cluster, mixed)
    fixed = one_unit(cluster, mixed)
    assert fixed["config"]["filters"] == [{"column": "SERVICE", "op": "eq", "value": "Voice"}]
    assert mixes_units(fixed, mixed) is None
    # a mixed predictor with its unit column beside it is the model's to separate
    lin = {"widget_type": "model_linear", "title": "Amount drivers",
           "config": {"measure": "RATED_AMOUNT", "predictors": ["SERVICE", "ROUNDED_VOLUME"]}}
    assert mixes_units(lin, mixed) is None


def test_the_trend_detector_reads_the_date_a_record_happened_on():
    cols = ["order_estimated_delivery_date", "order_delivered_customer_date", "order_purchase_timestamp"]
    assert order_event_dates(cols)[0] == "order_purchase_timestamp"


def test_repair_and_check_applies_the_new_rules_together():
    df = _enrolments()
    profile = _profile(df)
    pairs = one_to_one(df, list(df.columns))
    w, ok, why = repair_and_check({"widget_type": "treemap", "title": "Faculty & fee",
                                   "config": {"dimension": "faculty", "dimension2": "tuition_fee",
                                              "measure": "student_id", "aggregation": "countd"}},
                                  profile, {}, {}, pairs)
    assert not ok and refusal_code(why) == "repeat"


# ── interactive structure ─────────────────────────────────────────────────────

def test_each_page_gets_slicers_for_what_its_charts_split_by():
    df = _enrolments()
    df["notes"] = np.random.default_rng(2).choice(["ok", "late", "transfer"], len(df))
    profile = _profile(df)
    page = [{"widget_type": "bar", "config": {"dimension": "faculty", "measure": "final_score"}},
            {"widget_type": "box_plot", "config": {"dimension": "faculty", "measure": "final_score"}},
            {"widget_type": "bar", "config": {"dimension": "notes", "measure": "student_id"}}]
    s = slicers_for(page, profile)
    assert [x["config"]["dimension"] for x in s] == ["faculty", "notes"]
    assert all(x["widget_type"] == "slicer" for x in s)
    # an identifier or a personal column is never a slicer
    assert slicers_for([{"widget_type": "bar", "config": {"dimension": "student_id"}}], profile) == []
    # a headline page borrows the dataset's
    assert slicers_for([{"widget_type": "kpi", "config": {"measure": "final_score"}}], profile,
                       fallback=["faculty"])[0]["config"] == {"dimension": "faculty"}


def test_slicers_sit_above_the_page():
    placed = [({"widget_type": "kpi"}, {"x": 0, "y": 0, "w": 3, "h": 2}),
              ({"widget_type": "bar"}, {"x": 0, "y": 2, "w": 12, "h": 4})]
    out = with_slicers(placed, [{"widget_type": "slicer"}, {"widget_type": "slicer"}])
    assert [s["w"] for _, s in out[:2]] == [6, 6] and out[2][1]["y"] == 3 and out[3][1]["y"] == 5


def test_the_detail_table_lists_rows_and_is_valid():
    df = _enrolments()
    profile = _profile(df)
    for c in profile["columns"]:
        if c["name"] == "faculty":
            c["is_personal"] = True          # a personal column never appears
    t = detail_table(profile, set(), ["enrolled_on"])
    assert t["config"]["columns"][0] == "student_id" and "faculty" not in t["config"]["columns"]
    assert "enrolled_on" in t["config"]["columns"] and t["config"]["sort"] == "desc"
    ok, why = validate_widget(t, profile)
    assert ok, why
    from app.services.widget_data import get_widget_data_from_df
    got = get_widget_data_from_df(df, t["config"], "table")
    assert got["type"] == "table" and len(got["rows"]) == 200 and got["total"] == len(df)


def test_a_panel_ends_on_a_detail_page_and_pages_carry_slicers():
    from tests.test_analyst_panel import _run
    out, _ = _run(size=12)
    sections = [p["section"] for p in out["proposals"]]
    # the record page, then the hidden page a bar drills into
    assert sections[-2:] == ["detail", "drill"]
    drill = out["proposals"][-1]
    assert drill["page_type"] == "drillthrough" and drill["prompt_column"]
    marked = [w for p in out["proposals"] for w in p["widgets"] if w.get("drill_to") == "drill"]
    assert marked and all(w["config"]["dimension"] == drill["prompt_column"] for w in marked)
    pages = [p for p in out["proposals"] if p["section"] != "drill"]
    with_controls = [p for p in pages if any(w["widget_type"] == "slicer" for w in p["widgets"])]
    assert len(with_controls) == len(pages)
    for p in with_controls:
        first = [w for w in p["widgets"] if w["layout"]["y"] == 0]
        assert all(w["widget_type"] == "slicer" for w in first)


def test_an_inferred_measure_does_not_unlock_a_summed_year():
    """The metadata automation marked hire_year a measure (role_source
    "inferred"), and the veto took that as the author's word."""
    from app.services.semantic_guard import config_refusal
    cfg = {"measure": "hire_year", "aggregation": "sum"}
    assert config_refusal(cfg, {"hire_year": {"role": "measure", "role_source": "inferred"}},
                          sums_by_default=True)
    assert config_refusal(cfg, {"hire_year": {"role": "measure"}}, sums_by_default=True) is None
    assert default_summary("hire_year", {"hire_year": {"role": "measure", "role_source": "inferred"}}) == "max"


def test_a_histogram_bins_one_unit_at_a_time():
    mixed = {"ROUNDED_VOLUME": {"by": "SERVICE", "high": "GPRS", "low": "Voice", "common": "Voice",
                                "high_median": 1e6, "low_median": 60}}
    h = {"widget_type": "histogram", "title": "Call Duration Distribution",
         "config": {"measure": "ROUNDED_VOLUME", "aggregation": "count"}}
    assert mixes_units(h, mixed)
    assert one_unit(h, mixed)["config"]["filters"] == [{"column": "SERVICE", "op": "eq", "value": "Voice"}]
    bar = {"widget_type": "bar", "title": "Records by service",
           "config": {"dimension": "SERVICE", "measure": "ROUNDED_VOLUME", "aggregation": "count"}}
    assert mixes_units(bar, mixed) is None


def test_the_detail_table_sorts_by_a_one_unit_number_and_skips_coordinates():
    profile = {"columns": [
        {"name": "SERVICE", "role": "categorical", "distinct": 6},
        {"name": "ROUNDED_VOLUME", "role": "numeric", "distinct": 900},
        {"name": "RATED_AMOUNT", "role": "numeric", "distinct": 300},
        {"name": "LATITUDE", "role": "numeric", "distinct": 40}]}
    t = detail_table(profile, set(), ["FULL_DATE"], {"ROUNDED_VOLUME": {"by": "SERVICE"}})
    assert "LATITUDE" not in t["config"]["columns"] and t["config"]["sort_col"] == "RATED_AMOUNT"
    assert order_event_dates(["CALL_TIME", "FULL_DATE"])[0] == "FULL_DATE"


def test_a_table_by_an_identifier_becomes_a_list_of_records():
    from app.services.analyst_panel import _rows_not_groups
    df = _enrolments()
    df["notes"] = np.random.default_rng(3).choice(["no issues raised", "attendance follow-up"], len(df))
    profile = _profile(df)
    w = {"widget_type": "table", "title": "Students Requiring Follow-up",
         "config": {"dimension": "student_id", "measure": "final_score", "aggregation": "avg",
                    "filters": [{"column": "notes", "op": "eq", "value": "attendance follow-up"}]}}
    got, ok, why = repair_and_check(w, profile, {})
    assert ok, why
    assert got["config"]["columns"] == ["student_id", "final_score", "notes"]
    assert got["config"]["sort_col"] == "final_score" and got["config"]["filters"]
    top = {"widget_type": "table", "title": "Top 10 students",
           "config": {"dimension": "student_id", "measure": "final_score", "limit": 10}}
    assert _rows_not_groups(top, profile) is top


def test_a_count_word_measure_counts_rows():
    from app.services.analyst_panel import _count_word_measure
    profile = {"columns": [{"name": "order_status", "role": "categorical", "distinct": 7},
                           {"name": "order_purchase_timestamp", "role": "datetime"}]}
    w = _count_word_measure({"widget_type": "ribbon", "title": "Status over time",
                             "config": {"dimension": "order_purchase_timestamp", "dimension2": "order_status",
                                        "measure": "count", "aggregation": "sum"}}, profile)
    assert w["config"]["measure"] == "order_purchase_timestamp" and w["config"]["aggregation"] == "count"


def test_two_columns_with_the_same_numbers_are_shown_once():
    from app.services.analyst_panel import _drop_twins, same_number_twice
    from app.services.fact_sheet import identical_columns
    rng = np.random.default_rng(4)
    orders = rng.integers(50, 300, 100)
    df = pd.DataFrame({"total_orders": orders, "unique_customers": orders,
                       "total_revenue": orders * rng.uniform(90, 140, 100)})
    twins = identical_columns(df, list(df.columns))
    assert twins == {"total_orders": ["unique_customers"], "unique_customers": ["total_orders"]}
    why = same_number_twice({"widget_type": "dual_axis_time_series", "title": "Orders vs customers",
                             "config": {"measure": "total_orders", "measure2": "unique_customers"}}, twins)
    assert why and refusal_code(why) == "repeat"
    m = _drop_twins({"widget_type": "correlation_matrix", "title": "What moves together",
                     "config": {"measures": ["total_orders", "unique_customers", "total_revenue"]}}, twins)
    assert m["config"]["measures"] == ["total_orders", "total_revenue"]


def test_a_spread_of_dates_is_refused_not_crashed():
    why = date_as_number({"widget_type": "box_plot", "title": "Delivery Duration by Month",
                          "config": {"dimension": "order_purchase_timestamp",
                                     "measure": "order_delivered_customer_date"}},
                         {"order_delivered_customer_date", "order_purchase_timestamp"})
    assert why and refusal_code(why) == "meaning"


def test_a_spelled_out_aggregation_meets_the_same_rules():
    rng = np.random.default_rng(5)
    bought = pd.Timestamp("2017-01-01") + pd.to_timedelta(rng.integers(0, 600, 300), "D")
    df = pd.DataFrame({"order_purchase_timestamp": bought,
                       "order_delivered_customer_date": bought + pd.to_timedelta(rng.integers(2, 30, 300), "D"),
                       "order_status": rng.choice(["delivered", "shipped"], 300),
                       "price": rng.uniform(10, 200, 300)})
    profile = _profile(df)
    w, ok, why = repair_and_check({"widget_type": "line", "title": "Average Lead Time by Year",
                                   "config": {"dimension": "order_purchase_timestamp",
                                              "measure": "order_delivered_customer_date",
                                              "aggregation": "average", "dimension_granularity": "year"}},
                                  profile, {})
    assert not ok and refusal_code(why) == "meaning"


def test_a_chart_without_a_measure_takes_the_number_its_title_names():
    from app.services.analyst_panel import _grain_from_title, _measure_from_title
    prof = {"columns": [{"name": "total_orders", "role": "numeric"}, {"name": "canceled_orders", "role": "numeric"},
                        {"name": "total_revenue", "role": "numeric"}, {"name": "day_date", "role": "datetime"}]}
    w = _measure_from_title({"widget_type": "line", "title": "Canceled Orders Volume",
                             "config": {"dimension": "day_date"}}, prof)
    assert w["config"]["measure"] == "canceled_orders" and w["config"]["aggregation"] == "sum"
    t = _measure_from_title({"widget_type": "table", "title": "Top 20 High-Volume Days",
                             "config": {"dimension": "day_date", "sort": "total_orders", "limit": 20}}, prof)
    assert t["config"]["measure"] == "total_orders" and t["config"]["sort"] == "desc"
    # nothing named: the rows are counted, as asked
    hc = {"widget_type": "bar", "title": "Headcount by department", "config": {"dimension": "dept"}}
    assert _measure_from_title(hc, prof) is hc
    # the title's grain wins; "daily" describing a measure does not
    days = _grain_from_title({"widget_type": "table", "title": "Top 10 Days by Cancellation Rate",
                              "config": {"dimension": "day_date", "dimension_granularity": "month"}}, {"day_date"})
    assert days["config"]["dimension_granularity"] == "day"
    daily = {"widget_type": "line", "title": "Daily Order Volume Trend",
             "config": {"dimension": "day_date", "dimension_granularity": "month"}}
    assert _grain_from_title(daily, {"day_date"}) is daily


def test_selection_reaches_a_column_no_chart_has_shown():
    from app.services.analyst_panel import select
    def w(title, col, value=4, ev=0.6, sec="time"):
        return {"widget_type": "line", "title": title, "section": sec, "value": value, "evidence": ev,
                "config": {"dimension": "day_date", "measure": col, "aggregation": "sum"}, "source": "model"}
    pool = [w("Orders", "total_orders", value=5, ev=0.9), w("Revenue", "total_revenue", value=5, ev=0.9),
            w("Orders again", "total_orders", value=5, ev=0.8), w("Canceled orders", "canceled_orders", value=3, ev=0.4)]
    pool[2]["config"]["dimension_granularity"] = "week"
    chosen, _ = select(pool, 3, ["summary", "time"])
    assert "Canceled orders" in [c["title"] for c in chosen]


def test_a_date_difference_runs_on_a_live_source_with_pandas_meaning():
    """DATEDIFF floors whole days in pandas; the SQL must give the same number
    (sqlite run for real, other families checked for their form)."""
    import sqlite3
    from app.services.sql_expr import ExpressionTranslationError, calc_column_to_sql
    known = {"bought", "arrived"}
    sql, used = calc_column_to_sql("DATEDIFF(bought, arrived, 'day')", known, "sqlite")
    assert set(used) == known
    rows = [("2018-01-01 10:00:00", "2018-01-02 22:00:00"), ("2018-01-03 10:00:00", "2018-01-03 08:00:00"),
            ("2018-01-01 00:00:00", "2018-01-11 00:00:00"), ("2018-01-01 00:00:00", None)]
    con = sqlite3.connect(":memory:")
    con.execute('CREATE TABLE t ("bought" TEXT, "arrived" TEXT)')
    con.executemany("INSERT INTO t VALUES (?, ?)", rows)
    got = [r[0] for r in con.execute(f"SELECT {sql} FROM t")]
    df = pd.DataFrame(rows, columns=["bought", "arrived"])
    from app.services.widget_data import apply_calculated_columns
    want = apply_calculated_columns(df, [{"name": "d", "expression": "DATEDIFF(bought, arrived, 'day')"}])["d"]
    assert got[:3] == [int(x) for x in want[:3]] == [1, -1, 10] and got[3] is None
    for dialect in ("postgresql", "mysql", "sqlserver", "oracle"):
        assert "FLOOR" in calc_column_to_sql("DATEDIFF(bought, arrived, 'day')", known, dialect)[0]
    for bad in (None, "clickhouse"):
        try:
            calc_column_to_sql("DATEDIFF(bought, arrived, 'day')", known, bad)
            raise AssertionError("should refuse")
        except ExpressionTranslationError:
            pass


# ── derived fields and whole periods (gap review, round 2) ───────────────────

def _orders(n=400, seed=6):
    rng = np.random.default_rng(seed)
    bought = pd.Timestamp("2017-01-01") + pd.to_timedelta(rng.integers(0, 540, n), "D")
    eta = bought + pd.to_timedelta(rng.integers(15, 30, n), "D")
    got = bought + pd.to_timedelta(rng.integers(3, 35, n), "D")
    return pd.DataFrame({"order_id": [f"o{i}" for i in range(n)], "status": rng.choice(["a", "b", "c"], n),
                         "order_purchase_timestamp": bought, "order_estimated_delivery_date": eta,
                         "order_delivered_customer_date": got, "price": rng.uniform(5, 50, n)})


def test_a_rate_of_totals_is_proposed_for_a_part_and_its_total():
    from app.services.derived_fields import propose
    rng = np.random.default_rng(7)
    orders = rng.integers(100, 300, 200)
    df = pd.DataFrame({"total_orders": orders, "canceled_orders": rng.binomial(orders, 0.01),
                       "delivered_orders": orders - rng.integers(0, 5, 200), "total_revenue": orders * 120.0})
    roles = {c: "numeric" for c in df.columns}
    got = propose(df, roles)
    names = [m["name"] for m in got["measures"]]
    assert "canceled_orders_pct_of_total_orders" in names
    # one whole per part, and the total is that whole
    assert not any(n.startswith("canceled_orders_pct_of_delivered") for n in names)
    m = next(m for m in got["measures"] if m["name"] == "canceled_orders_pct_of_total_orders")
    from app.services.measure_eval import evaluate_measure
    assert abs(evaluate_measure(m["expression"], df, []) - df.canceled_orders.sum() / df.total_orders.sum() * 100) < 1e-9


def test_durations_and_lateness_are_proposed_from_dates():
    from app.services.derived_fields import propose
    df = _orders()
    roles = {"order_id": "text", "status": "categorical", "price": "numeric",
             "order_purchase_timestamp": "datetime", "order_estimated_delivery_date": "datetime",
             "order_delivered_customer_date": "datetime"}
    got = propose(df, roles)
    calc = {c["name"]: c for c in got["calculated_columns"]}
    assert "days_purchase_to_delivered_customer" in calc
    assert calc["days_late_vs_estimated_delivery"]["expression"] == \
        "DATEDIFF(order_estimated_delivery_date, order_delivered_customer_date, 'day')"
    assert [m["name"] for m in got["measures"]] == ["late_pct_vs_estimated_delivery"]
    from app.services.widget_data import apply_calculated_columns
    out = apply_calculated_columns(df, list(calc.values()))
    assert (out["days_purchase_to_delivered_customer"] >= 3).all()


def test_the_panel_draws_derived_fields_and_reports_what_to_create():
    import asyncio
    from app.services.suggest_inputs import SuggestInputs, panel
    df = _orders(800)
    tm = detect_types(df)
    inp = SuggestInputs(df=df, type_map=tm, profile=build_profile(df, tm, {}), knowledge=None, measures=[],
                        column_meta={}, description=None, measured={})
    out = asyncio.run(panel(inp, None, 24, client=None))
    used = {f["name"] for k in ("measures", "calculated_columns") for f in out["derived"][k]}
    assert "late_pct_vs_estimated_delivery" in used
    titles = [w["title"] for p in out["proposals"] for w in p["widgets"]]
    assert any("late pct vs estimated delivery" in t.lower() for t in titles)
    assert all(set(d) <= {"name", "expression", "dtype", "format", "default_aggregation"}
               for k in ("measures", "calculated_columns") for d in out["derived"][k])


def test_a_live_source_only_gets_columns_its_sql_can_compute():
    import asyncio
    from app.services.suggest_inputs import SuggestInputs, panel
    df = _orders(800)
    tm = detect_types(df)
    base = dict(df=df, type_map=tm, profile=build_profile(df, tm, {}), knowledge=None, measures=[],
                column_meta={}, description=None, measured={}, live=True)
    out = asyncio.run(panel(SuggestInputs(**base, sql_family="clickhouse"), None, 24, client=None))
    assert out["derived"]["calculated_columns"] == []
    out = asyncio.run(panel(SuggestInputs(**base, sql_family="postgresql"), None, 24, client=None))
    assert {"measures", "calculated_columns"} <= set(out["derived"])


def test_edges_leave_out_stub_and_partial_periods_but_not_a_falling_trend():
    from app.services.fact_sheet import edge_periods
    days = list(pd.date_range("2016-09-10", periods=3)) + [pd.Timestamp("2016-12-20")] + \
        list(pd.date_range("2017-01-01", "2018-08-31", freq="6h")) + [pd.Timestamp("2018-09-03")]
    span = edge_periods(pd.DataFrame({"d": days}), ["d"])["d"]["month"]
    assert span == {"from": "2017-01-01", "before": "2018-09-01"}
    years = []
    for y, n in zip(range(1985, 2001), [2800, 2700, 2500, 2300, 2000, 1800, 1500, 1200, 1000, 800, 600, 400,
                                         300, 200, 120, 2]):
        years += [pd.Timestamp(f"{y}-01-01") + pd.Timedelta(days=int(i * 360 / n)) for i in range(n)]
    span = edge_periods(pd.DataFrame({"d": years}), ["d"])["d"]["year"]
    assert span == {"from": "1985-01-01", "before": "2000-01-01"}


def test_a_trend_is_filtered_to_whole_periods_and_says_so():
    from app.services.analyst_panel import trim_edges
    edges = {"d": {"month": {"from": "2017-01-01", "before": "2018-09-01"}}}
    w = trim_edges({"widget_type": "line", "title": "Orders by month", "why": "Volume over time.",
                    "config": {"dimension": "d", "dimension_granularity": "month", "measure": "x"}}, edges)
    assert w["config"]["filters"] == [{"column": "d", "op": "gte", "value": "2017-01-01"},
                                      {"column": "d", "op": "lt", "value": "2018-09-01"}]
    assert "Whole months only" in w["why"]
    daily = {"widget_type": "line", "title": "Orders by day", "config": {"dimension": "d", "dimension_granularity": "day"}}
    assert trim_edges(daily, edges) is daily


def test_the_lenses_still_run_when_derived_fields_are_offered():
    """A derived measure listed in the profile lacked keys the prompt reads,
    and every lens of the live daily-ops and Olist panels failed (KeyError)."""
    import asyncio
    from app.services.suggest_inputs import SuggestInputs, panel

    class Client:
        seen: list = []

        async def complete_json(self, messages, schema, **kw):
            self.seen.append(messages[1]["content"])
            return {"widgets": []}
    df = _orders(800)
    tm = detect_types(df)
    inp = SuggestInputs(df=df, type_map=tm, profile=build_profile(df, tm, {}), knowledge=None, measures=[],
                        column_meta={}, description=None, measured={})
    c = Client()
    out = asyncio.run(panel(inp, None, 24, client=c))
    assert out["panel"]["lens_notes"] and not any("failed" in v for v in out["panel"]["lens_notes"].values())
    assert any("late_pct_vs_estimated_delivery" in m for m in c.seen)


def test_an_aggregation_written_beside_its_slot_is_read():
    from app.services.suggest_dataset_dashboard import resolve_time_words
    df = _enrolments()
    profile = _profile(df)
    w, ok, why = repair_and_check({"widget_type": "bar", "title": "Average score by faculty",
                                   "config": {"dimension": "faculty", "measure": "final_score",
                                              "measure_aggregation": "avg"}}, profile, {})
    assert ok, why
    assert w["config"]["aggregation"] == "avg" and "measure_aggregation" not in w["config"]


def test_a_title_naming_the_year_of_a_date_drawn_by_year_keeps_its_promise():
    from app.services.analyst_panel import broken_promise
    profile = {"columns": [{"name": "hire_date", "role": "datetime"}, {"name": "hire_year", "role": "numeric"},
                           {"name": "title", "role": "categorical", "distinct": 7}]}
    w = {"widget_type": "ribbon", "title": "Title mix by hire year", "source": "model",
         "config": {"dimension": "hire_date", "dimension2": "title", "dimension_granularity": "year"}}
    assert broken_promise(w, profile) is None
    w["config"]["dimension_granularity"] = "month"
    assert broken_promise(w, profile)


def test_a_share_of_a_whole_keeps_its_total_when_polished():
    from app.services.suggest_dataset_dashboard import polish_widget
    profile = {"columns": [{"name": "seller_id", "role": "categorical", "distinct": 20},
                           {"name": "price", "role": "numeric", "distinct": 500}]}
    w = polish_widget({"widget_type": "treemap", "title": "Revenue by top sellers",
                       "config": {"dimension": "seller_id", "measure": "price", "aggregation": "sum", "limit": 10}},
                      profile)
    assert w["config"]["aggregation"] == "sum"
    b = polish_widget({"widget_type": "bar", "title": "Price by seller",
                       "config": {"dimension": "seller_id", "measure": "price", "aggregation": "sum"}}, profile)
    assert b["config"]["aggregation"] == "avg"


# ── round 3: period data, drill-through, every engine ────────────────────────

def _daily(n=400, seed=8):
    rng = np.random.default_rng(seed)
    orders = rng.integers(80, 300, n)
    return pd.DataFrame({"day_date": pd.date_range("2017-01-01", periods=n, freq="D"),
                         "total_orders": orders, "canceled_orders": rng.binomial(orders, 0.01),
                         "total_revenue": orders * rng.uniform(90, 140, n),
                         "avg_order_value": rng.uniform(90, 140, n)})


def test_one_row_per_period_data_gets_an_exceptions_lens():
    from app.services.analyst_panel import choose_lenses
    assert "exceptions" in choose_lenses(_profile(_daily()), [])
    assert "exceptions" not in choose_lenses(_profile(_enrolments()), [])


def test_a_ranked_table_of_periods_lists_the_rows():
    df = _daily()
    w, ok, why = repair_and_check({"widget_type": "table", "title": "Top 10 cancellation days",
                                   "config": {"dimension": "day_date", "measures": ["total_orders", "canceled_orders"],
                                              "sort_by": "canceled_orders", "limit": 10}}, _profile(df), {})
    assert ok, why
    assert w["config"] == {"columns": ["day_date", "total_orders", "canceled_orders"], "limit": 10,
                           "sort_col": "canceled_orders", "sort": "desc"}
    from app.services.widget_data import get_widget_data_from_df
    rows = get_widget_data_from_df(df, w["config"], "table")["rows"]
    assert rows[0][2] == df.canceled_orders.max()


def test_the_drill_page_repeats_headlines_and_records_for_one_value():
    from app.services.analyst_panel import drill_page
    props = [
        {"section": "summary", "widgets": [{"widget_type": "kpi", "title": "Median wait", "config": {"measure": "w"},
                                            "layout": {}}]},
        {"section": "measures", "widgets": [{"widget_type": "bar", "title": "Wait by dept",
                                             "config": {"dimension": "dept", "measure": "w"}, "layout": {}},
                                            {"widget_type": "slicer", "title": "f", "config": {"dimension": "dept"},
                                             "layout": {}}]},
        {"section": "detail", "widgets": [{"widget_type": "table", "title": "Detail rows",
                                           "config": {"columns": ["id", "dept", "w"]}, "layout": {}}]},
    ]
    page = drill_page(props, ["dept"])
    assert page["page_type"] == "drillthrough" and page["prompt_column"] == "dept"
    assert [w["widget_type"] for w in page["widgets"]] == ["kpi", "table"]
    assert props[1]["widgets"][0]["drill_to"] == "drill" and "drill_to" not in props[1]["widgets"][1]
    assert drill_page(props, []) is None


def test_the_designer_and_statistics_engines_get_the_same_help(client_factory=None):
    """Quick mode is offered the derived fields; the statistics engine trims
    edge periods and applies the veto (checked on the router's helper)."""
    import asyncio
    from app.routers.datasets import _suggest_from_insights

    class DS:
        name, description, column_meta = "daily", None, {}
    df = _daily(700)
    df.loc[len(df)] = [pd.Timestamp("2019-01-01"), 5, 0, 500.0, 100.0]       # a stub period after a gap
    tm = detect_types(df)
    from app.services.widget_data import get_widget_data_from_df

    async def probe(wt, cfg):
        return get_widget_data_from_df(df, cfg, wt)
    props, _ = asyncio.run(_suggest_from_insights(df, tm, DS(), probe, _profile(df)))
    trends = [w for p in props for w in p["widgets"] if (w["config"].get("dimension_granularity") == "month")]
    assert trends and all(any(f.get("op") == "lt" for f in w["config"].get("filters") or []) for w in trends)


def test_the_datas_own_faults_are_stated():
    from app.services.fact_sheet import quality_issues
    df = pd.DataFrame({"dest": ["Mobile to Mobile", "Mobile To Mobile", " Catch All Zone", "Local"] * 10,
                       "amount": list(range(39)) + [None]})
    df = pd.concat([df, df.iloc[:3]], ignore_index=True)
    got = quality_issues(df, ["dest"])
    assert got[0].startswith("3 rows are exact duplicates")
    assert any("stray spaces" in t and "' Catch All Zone'" in t for t in got)
    assert any("'Mobile to Mobile' / 'Mobile To Mobile'" in t for t in got)
    assert quality_issues(pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]}), ["b"]) == []


# ── round 4 ──────────────────────────────────────────────────────────────────

def test_data_with_nothing_to_group_by_gets_period_slicers():
    from app.services.analyst_panel import slicers_for
    from app.services.widget_data import get_widget_data_from_df, infer_date_filter_grains
    df = _daily(700)
    got = slicers_for([], _profile(df))
    assert [s["config"] for s in got] == [{"dimension": "day_date", "dimension_granularity": "year"},
                                         {"dimension": "day_date", "dimension_granularity": "month"}]
    years = [r["name"] for r in get_widget_data_from_df(df, got[0]["config"], "slicer")["rows"]]
    # a picked year is a bucket every engine filters by
    f = infer_date_filter_grains([{"column": "day_date", "op": "eq", "value": years[0]}], {"day_date"})
    kpi = get_widget_data_from_df(df, {"measure": "total_orders", "aggregation": "sum", "filters": f}, "kpi")
    assert kpi["rows"][0]["value"] == df[df.day_date.dt.year == int(years[0])].total_orders.sum()


def test_overlap_recall_counts_a_near_miss_but_not_a_stranger():
    from app.services.panel_benchmark import coverage
    ref = [{"widget_type": "table", "title": "Top cancellation days",
            "config": {"dimension": "day", "measures": ["orders", "canceled", "rate"]}}]
    cols = {"day", "orders", "canceled", "rate", "revenue"}
    near = [{"widget_type": "table", "config": {"dimension": "day", "measures": ["orders", "canceled"]}}]
    far = [{"widget_type": "table", "config": {"dimension": "day", "measures": ["revenue"]}}]
    assert coverage(near, ref, cols)["question_recall"] == 0
    assert coverage(near, ref, cols)["overlap_recall"] == 1
    assert coverage(far, ref, cols)["overlap_recall"] == 0


def test_quick_mode_replaces_what_the_gate_refused():
    import asyncio
    from app.services.suggest_dataset_dashboard import suggest_for_dataset
    df = _enrolments()
    profile = _profile(df)
    first = {"proposals": [{"title": "Scores", "rationale": "r", "widgets": [
        {"widget_type": "bar", "title": "Average score by faculty",
         "config": {"dimension": "faculty", "measure": "final_score", "aggregation": "avg"}},
        {"widget_type": "bar", "title": "Bad", "config": {"dimension": "region", "measure": "final_score"}}]}]}
    second = {"proposals": [{"title": "Scores", "rationale": "r", "widgets": [
        {"widget_type": "histogram", "title": "Score distribution", "config": {"measure": "final_score"}}]}]}

    class Client:
        calls = 0

        async def complete_json(self, messages, schema, **kw):
            Client.calls += 1
            return first if Client.calls == 1 else second
    from app.services.widget_data import get_widget_data_from_df

    async def probe(wt, cfg):
        return get_widget_data_from_df(df, cfg, wt)
    props, reason = asyncio.run(suggest_for_dataset(profile, "I run admissions", 1, client=Client(), probe=probe))
    assert [w["title"] for w in props[0]["widgets"]] == ["Average score by faculty", "Score distribution"]
    assert reason.startswith("1 of 1 refused ideas replaced")


def test_every_lens_asks_greedily_with_one_seed():
    import asyncio
    from app.services.analyst_panel import LENS_SEED
    from app.services.suggest_inputs import SuggestInputs, panel
    seen = []

    class Client:
        async def complete_json(self, messages, schema, **kw):
            seen.append((kw.get("temperature"), kw.get("seed")))
            return {"widgets": []}
    df = _enrolments()
    tm = detect_types(df)
    inp = SuggestInputs(df=df, type_map=tm, profile=build_profile(df, tm, {}), knowledge=None, measures=[],
                        column_meta={}, description=None, measured={})
    asyncio.run(panel(inp, None, 12, client=Client()))
    assert seen and set(seen) == {(0.0, LENS_SEED)}


def test_the_model_client_sends_the_seed():
    from app.services.llm import LLMClient
    assert "seed" in LLMClient.complete.__code__.co_varnames
    assert "seed" in LLMClient.complete_json.__code__.co_varnames


# ── round 5 ──────────────────────────────────────────────────────────────────

def _daily_rated(n=400):
    df = _daily(n)
    df["cancellation_rate_pct"] = (df.canceled_orders / df.total_orders * 100).round(2)
    return df


def test_one_row_per_period_data_gets_the_standard_series_visuals():
    """Daily ops: the lenses drew orders against revenue six ways and never
    plain "revenue by month" or the top cancellation days."""
    from app.services.analyst_panel import series_backbone
    df = _daily_rated()
    got = series_backbone(_profile(df), set(), {}, ["day_date"])
    by = {(w["widget_type"], w["title"]) for w in got}
    assert ("kpi", "Total canceled orders") in by and ("line", "Revenue by month") in by
    assert ("line", "Average order value by month") in by          # a rate is averaged, never summed
    assert not any(w["config"].get("measure") == "avg_order_value" and w["config"].get("aggregation") == "sum"
                   for w in got)
    tops = {w["config"]["sort_col"]: w["config"]["columns"] for w in got if w["widget_type"] == "table"}
    # canceled orders is ranked because the data also keeps it as a rate
    assert "cancellation_rate_pct" in tops["canceled_orders"]
    corr = next(w for w in got if w["widget_type"] == "correlation_matrix")
    assert {"total_orders", "canceled_orders", "total_revenue"} <= set(corr["config"]["measures"])
    assert series_backbone(_profile(df), set(), {}, []) == []


def test_period_bars_and_regressions_are_offered_without_a_category():
    from app.services.suggest_dataset_dashboard import usable_widgets, validate_widget
    from app.services.widget_data import get_widget_data_from_df
    df = _daily_rated()
    profile = _profile(df)
    assert {"bar", "dual_axis_bar_line", "box_plot", "model_linear"} <= set(usable_widgets(profile))
    bar = {"dimension": "day_date", "dimension_granularity": "quarter", "measure": "total_revenue",
           "aggregation": "sum"}
    assert validate_widget({"widget_type": "bar", "title": "Revenue by quarter", "config": bar}, profile)[0]
    assert len(get_widget_data_from_df(df, bar, "bar")["rows"]) == 5


def test_a_short_sorted_list_is_a_ranking_question():
    from app.services.analyst_panel import _identity
    from app.services.panel_benchmark import question
    cols = {"day", "orders", "canceled"}
    top = {"columns": ["day", "orders", "canceled"], "sort_col": "canceled", "limit": 10}
    assert question("table", top, cols) == ("compare", frozenset(cols))
    assert question("table", {**top, "limit": 200}, cols) == ("detail", frozenset())
    a = {"widget_type": "table", "config": top}
    b = {"widget_type": "table", "config": {**top, "sort_col": "orders"}}
    assert _identity(a) != _identity(b)


def test_a_lens_answer_is_reused_for_the_same_question_on_the_same_data():
    import asyncio
    from app.services import analyst_panel as AP
    from app.services.suggest_inputs import SuggestInputs, panel
    AP.clear_lens_cache()
    calls = []

    class Client:
        model = "m1"

        async def complete_json(self, messages, schema, **kw):
            calls.append(1)
            return {"widgets": [{"widget_type": "histogram", "title": "Score spread",
                                 "config": {"measure": "final_score"}, "question": "q", "value": 4}]}
    df = _enrolments()
    tm = detect_types(df)

    def run(client):
        inp = SuggestInputs(df=df, type_map=tm, profile=build_profile(df, tm, {}), knowledge=None, measures=[],
                            column_meta={}, description=None, measured={})
        return asyncio.run(panel(inp, None, 12, client=client))
    first = run(Client())
    n = len(calls)
    second = run(Client())
    assert n > 0 and len(calls) == n                          # nothing asked twice
    assert [w["title"] for p in first["proposals"] for w in p["widgets"]] == \
           [w["title"] for p in second["proposals"] for w in p["widgets"]]
    assert all("(reused)" in v for v in second["panel"]["lens_notes"].values())

    class Other(Client):
        model = "m2"
    run(Other())
    assert len(calls) == 2 * n                                # another model is asked afresh
    AP.clear_lens_cache()


def test_a_failed_or_empty_lens_answer_is_not_kept():
    from app.services import analyst_panel as AP
    AP.clear_lens_cache()
    key = AP.lens_cache_key(object(), [{"role": "user", "content": "x"}])
    assert AP._cache_get(key) is None
    AP._cache_set(key, {"widgets": [1]})
    assert AP._cache_get(key) == {"widgets": [1]}
    assert key != AP.lens_cache_key(object(), [{"role": "user", "content": "y"}])
    AP.clear_lens_cache()


def test_the_datas_faults_get_a_page_of_their_own():
    import asyncio
    from app.services.analyst_panel import quality_widgets
    from app.services.fact_sheet import quality_findings
    from app.services.suggest_inputs import SuggestInputs, panel
    df = pd.DataFrame({"dest": (["Mobile to Mobile"] * 6 + ["Mobile To Mobile"] * 3 + ["Local"] * 11) * 3,
                       "amount": np.arange(60) * 1.5,
                       "day": pd.date_range("2025-01-01", periods=60, freq="D")})
    df = pd.concat([df, df.iloc[:4]], ignore_index=True)
    found = quality_findings(df, ["dest"])
    assert [f["kind"] for f in found] == ["duplicates", "variants"]
    ws = quality_widgets(found)
    assert ws[0]["widget_type"] == "text" and "exact duplicates" in ws[0]["config"]["content"]
    assert ws[1]["config"]["filters"][0]["value"] == ["Mobile to Mobile", "Mobile To Mobile"]
    assert quality_widgets([]) == []

    tm = detect_types(df)
    inp = SuggestInputs(df=df, type_map=tm, profile=build_profile(df, tm, {}), knowledge=None, measures=[],
                        column_meta={}, description=None, measured={})
    out = asyncio.run(panel(inp, None, 12, client=None))
    page = next(p for p in out["proposals"] if p["section"] == "quality")
    assert [w["widget_type"] for w in page["widgets"]] == ["text", "bar"]   # no slicers on it
    assert page["widgets"][0]["layout"]["w"] == 12
    assert not any(w.get("drill_to") for w in page["widgets"])


# ── round 5, live re-score ───────────────────────────────────────────────────

def test_one_overview_matrix_keeps_the_most_measures():
    """A lens's five-measure matrix beat the seven-measure one on the live
    daily-ops panel, though only one overview is kept."""
    from app.services.analyst_panel import select
    narrow = {"widget_type": "correlation_matrix", "config": {"measures": ["a", "b", "c"]},
              "value": 5, "evidence": 0.5, "section": "relationships", "source": "model"}
    wide = {**narrow, "config": {"measures": ["a", "b", "c", "d", "e"]}, "value": 4, "source": "backbone"}
    chosen, _ = select([narrow, wide], 10, ["summary", "relationships"])
    assert [len(w["config"]["measures"]) for w in chosen] == [5]


def test_a_measure_nothing_shows_gets_its_chart_even_when_flat():
    from app.services.analyst_panel import select
    shown = {"widget_type": "line", "config": {"dimension": "d", "measure": "orders", "aggregation": "sum"},
             "value": 4, "evidence": 0.8, "section": "time"}
    flat = {"widget_type": "line", "config": {"dimension": "d", "measure": "freight_per_item", "aggregation": "avg"},
            "value": 3, "evidence": 0.02, "section": "time"}
    flats = [{**flat, "config": {**flat["config"], "measure": f"other_{i}"}, "value": 2} for i in range(3)]
    chosen, _ = select([shown, flat] + flats, 10, ["summary", "time"])
    got = {w["config"]["measure"] for w in chosen}
    assert "freight_per_item" in got
    assert not any(m.startswith("other_") for m in got)          # low-valued flat ideas still wait


def test_no_drill_through_on_a_period():
    """Daily ops filtered by year and month slicers: every monthly chart
    pointed at a "one day date" page its month labels could never fill."""
    import asyncio
    from app.services.suggest_inputs import SuggestInputs, panel
    df = _daily_rated()
    tm = detect_types(df)
    inp = SuggestInputs(df=df, type_map=tm, profile=build_profile(df, tm, {}), knowledge=None, measures=[],
                        column_meta={}, description=None, measured={})
    out = asyncio.run(panel(inp, None, 24, client=None))
    assert not any(p.get("page_type") == "drillthrough" for p in out["proposals"])
    assert not any(w.get("drill_to") for p in out["proposals"] for w in p["widgets"])


def test_a_measure_only_inside_a_matrix_still_gets_its_own_chart():
    from app.services.analyst_panel import select
    matrix = {"widget_type": "correlation_matrix", "config": {"measures": ["orders", "freight_per_item"]},
              "value": 5, "evidence": 0.6, "section": "relationships"}
    orders = {"widget_type": "line", "config": {"dimension": "d", "measure": "orders", "aggregation": "sum"},
              "value": 4, "evidence": 0.8, "section": "time"}
    flat = {"widget_type": "line", "config": {"dimension": "d", "measure": "freight_per_item", "aggregation": "avg"},
            "value": 3, "evidence": 0.02, "section": "time"}
    chosen, _ = select([matrix, orders, flat], 10, ["summary", "time", "relationships"])
    assert any(w["config"].get("measure") == "freight_per_item" for w in chosen)


def test_every_measure_gets_a_chart_before_second_views_fill_the_room():
    """The live daily-ops panel filled all 50 places with second views of
    orders and revenue before freight per item had a chart of its own."""
    from app.services.analyst_panel import select
    bars = [{"widget_type": "bar", "config": {"dimension": "day", "measure": "orders", "aggregation": agg},
             "value": 5, "evidence": 0.9, "section": "time"} for agg in ("sum", "avg", "max", "min")]
    flat = {"widget_type": "line", "config": {"dimension": "day", "measure": "freight_per_item", "aggregation": "avg"},
            "value": 3, "evidence": 0.02, "section": "time"}
    chosen, _ = select(bars + [flat], 3, ["summary", "time"])
    assert len(chosen) == 3
    assert any(w["config"]["measure"] == "freight_per_item" for w in chosen)


def test_rates_get_a_headline_beside_the_totals():
    from app.services.analyst_panel import series_backbone
    df = _daily_rated()
    got = series_backbone(_profile(df), set(), {}, ["day_date"])
    kpis = {w["title"]: w["config"] for w in got if w["widget_type"] == "kpi"}
    assert kpis["Average order value per day"] == {"measure": "avg_order_value", "aggregation": "avg"}
    assert kpis["Average cancellation rate pct per day"]["aggregation"] == "avg"


def test_two_daily_averages_are_read_against_each_other():
    from app.services.analyst_panel import series_backbone
    df = _daily_rated()
    df["avg_freight_cost"] = df["avg_order_value"] * 0.15
    got = series_backbone(_profile(df), set(), {}, ["day_date"])
    pairs = [w["config"] for w in got if w["widget_type"] == "numeric_series"]
    assert {"measure": "avg_order_value", "measure2": "avg_freight_cost"} in pairs
