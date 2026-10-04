"""The brief-first designer's facts and result checks (services/source_brief.py).

Every case is a mistake the old designer shipped on the Egyptian food
database, asked for by the Minister of Supply (live, 2026-10-03).
"""
from app.services.source_brief import (assess, facts_text, mixed_unit_tables,
                                       normalise_widget, table_warnings)

PRICES = {
    "name": "wfp_food_prices", "rows": 3658, "description": "WFP retail prices",
    "columns": [
        {"name": "date", "dtype": "date", "min": "2010-08-15", "max": "2026-08-15", "distinct": 193},
        {"name": "governorate", "dtype": "text", "null_ratio": 0.705,
         "top_k": [{"value": "Cairo", "count": 1078}], "distinct": 1},
        {"name": "market", "dtype": "text", "distinct": 2,
         "top_k": [{"value": "National Average", "count": 2580},
                   {"value": "Cairo (national average)", "count": 1078}]},
        {"name": "commodity", "dtype": "text", "distinct": 40,
         "top_k": [{"value": "Rice", "count": 211}, {"value": "Lentils", "count": 212}]},
        {"name": "unit", "dtype": "text", "distinct": 6,
         "top_k": [{"value": "KG", "count": 3000}, {"value": "800 G", "count": 380},
                   {"value": "1 piece", "count": 67}]},
        {"name": "priceflag", "dtype": "text", "distinct": 1,
         "top_k": [{"value": "actual", "count": 3658}]},
        {"name": "price_egp", "dtype": "numeric", "min": "0.3", "max": "302.5"},
    ],
}
POVERTY = {
    "name": "poverty_rate", "rows": 51,
    "columns": [
        {"name": "year", "dtype": "integer", "distinct": 2,
         "top_k": [{"value": "2014", "count": 26}, {"value": "2008", "count": 25}]},
        {"name": "admin1_name", "dtype": "text", "distinct": 27, "null_ratio": 0.08},
        {"name": "headcount_ratio", "dtype": "numeric"},
    ],
}


def test_mixed_units_are_named_with_the_fix():
    warn = " ".join(table_warnings(PRICES))
    assert "6 different units" in warn and "price_egp" in warn
    assert "never SUM or AVG" in warn
    assert mixed_unit_tables([PRICES])["wfp_food_prices"]["unit"] == "unit"


def test_a_mostly_empty_column_says_what_little_it_holds():
    warn = " ".join(table_warnings(PRICES))
    assert "governorate is 70% empty" in warn and "'Cairo'" in warn


def test_years_present_are_listed_so_nobody_joins_on_2026():
    warn = " ".join(table_warnings(POVERTY))
    assert "2008, 2014" in warn


def test_facts_show_the_real_filter_values():
    text = facts_text([PRICES, POVERTY])
    # `priceflag = 'A'` blanked every price tile; the real value is 'actual'.
    assert "actual" in text
    assert "TABLE poverty_rate" in text


def _p(*widgets):
    return {"title": "t", "widgets": [normalise_widget(w) for w in widgets]}


COLS = ["month", "commodity", "unit", "price", "yoy_change_pct", "is_latest", "governorate"]
ROWS = [
    ["2026-07-15", "Rice", "KG", 29.0, 10.0, 0, "Cairo"],
    ["2026-08-15", "Rice", "KG", 29.8, 12.0, 1, "Cairo"],
    ["2026-07-15", "Oil (cotton)", "800 G", 60.0, 20.0, 0, "Cairo"],
    ["2026-08-15", "Oil (cotton)", "800 G", 64.9, 25.0, 1, "Cairo"],
    ["2026-08-15", "Eggs (medium size)", "1 piece", 4.1, 30.0, 1, "Cairo"],
]


def test_a_text_column_is_not_a_kpi_number():
    got = assess(_p({"widget_type": "kpi", "title": "Highest risk", "measure": "governorate",
                     "aggregation": "max"}), COLS, ROWS)
    assert any("text, not a number" in g for g in got)


def test_a_single_value_breakdown_is_refused():
    got = assess(_p({"widget_type": "bar", "title": "By gov", "dimension": "governorate",
                     "measure": "yoy_change_pct", "aggregation": "avg"}), COLS, ROWS)
    assert any("single value" in g for g in got)


def test_prices_averaged_across_units_are_refused_but_per_item_is_fine():
    across = assess(_p({"widget_type": "kpi", "title": "Avg price", "measure": "price",
                        "aggregation": "avg"}), COLS, ROWS)
    assert any("mixes 3 units" in g for g in across)
    per_item = assess(_p({"widget_type": "bar", "title": "Price per item", "dimension": "commodity",
                          "measure": "price", "aggregation": "avg"}), COLS, ROWS)
    assert per_item == []
    # A % change has no unit: averaging it across items is a fair headline.
    pct = assess(_p({"widget_type": "kpi", "title": "Avg change", "measure": "yoy_change_pct",
                     "aggregation": "avg", "filter_column": "is_latest", "filter_value": "1"}), COLS, ROWS)
    assert pct == []


def test_a_filter_value_that_matches_nothing_is_refused():
    got = assess(_p({"widget_type": "kpi", "title": "x", "measure": "price", "aggregation": "max",
                     "filter_column": "commodity", "filter_value": "Bread"}), COLS, ROWS)
    assert any("no row has" in g for g in got)


def test_an_empty_measure_is_refused():
    rows = [r[:3] + [None] + r[4:] for r in ROWS]
    got = assess(_p({"widget_type": "bar", "title": "p", "dimension": "commodity",
                     "measure": "price", "aggregation": "avg"}), COLS, rows)
    assert any("empty in 100%" in g for g in got)


def test_no_rows_is_one_clear_message():
    assert "returned no rows" in assess(_p({"widget_type": "kpi", "title": "x", "measure": "price",
                                            "aggregation": "sum"}), COLS, [])[0]


def test_unknown_output_column_is_named():
    got = assess(_p({"widget_type": "line", "title": "l", "dimension": "month", "dimension2": "item",
                     "measure": "price", "aggregation": "avg"}), COLS, ROWS)
    assert any("item is not an output column" in g for g in got)


def test_a_cte_and_unaliased_columns_pass_the_static_check():
    from app.services.source_brief import _static_problems
    p = {"sql": "WITH m AS (SELECT commodity, price_egp FROM wfp_food_prices) "
                "SELECT p.admin1_name, m.commodity FROM m JOIN poverty_rate p ON 1=1",
         "widgets": [normalise_widget({"widget_type": "bar", "title": "x", "dimension": "admin1_name",
                                       "measure": "commodity", "aggregation": "count"})]}
    assert _static_problems(p, {"wfp_food_prices", "poverty_rate"}, [], lambda s, c: (True, "")) is None
    p["sql"] = "DELETE FROM wfp_food_prices"
    assert _static_problems(p, {"wfp_food_prices"}, [], lambda s, c: (True, ""))
    p["sql"] = "SELECT * FROM secrets"
    assert "secrets" in _static_problems(p, {"wfp_food_prices"}, [], lambda s, c: (True, ""))


def test_a_zero_filled_join_is_caught():
    p = _p({"widget_type": "bar", "title": "Poor people", "dimension": "commodity",
            "measure": "price", "aggregation": "sum"})
    p["sql"] = "SELECT COALESCE(pop.population, 0) AS price FROM x"
    rows = [r[:3] + [0.0] + r[4:] for r in ROWS[:3]] + ROWS[3:]
    got = assess(p, COLS, rows)
    assert any("COALESCE" in g for g in got)


def test_questions_left_out_of_every_group_get_their_own_dashboard():
    from app.services.source_brief import question_groups
    brief = {"questions": [{"question": f"q{i}"} for i in range(5)],
             "dashboards": [{"title": "A", "questions": [1, 2]}, {"title": "B", "questions": []}]}
    groups = question_groups(brief, 3)
    assert [t for t, _ in groups] == ["A", "q2"]
    assert [q["question"] for q in groups[1][1]] == ["q2", "q3", "q4"]


def test_extract_from_a_date_column_is_not_a_table():
    from app.services.source_brief import _tables_named
    sql = ("WITH y AS (SELECT EXTRACT(year FROM date) AS yr, price_egp FROM wfp_food_prices) "
           "SELECT yr FROM y JOIN conflict_events c ON c.year = y.yr")
    assert _tables_named(sql) == {"wfp_food_prices", "conflict_events"}


def test_several_filter_values_become_one_in_filter():
    w = normalise_widget({"widget_type": "line", "title": "x", "dimension": "month",
                          "dimension2": "commodity", "measure": "yoy_change_pct", "aggregation": "avg",
                          "filter_column": "commodity", "filter_value": "Rice|Bread"})
    assert w["filters"] == [{"column": "commodity", "op": "in", "value": ["Rice", "Bread"]}]
    got = assess({"widgets": [w]}, COLS, ROWS)
    assert any("'Bread'" in g for g in got) and not any("'Rice'" in g for g in got)


def test_category_share_of_summed_prices_is_refused():
    from app.services.source_brief import sql_problems
    sql = """WITH m AS (SELECT date_trunc('month', date) AS period, commodity, category,
                    AVG(price_egp) AS avg_price FROM wfp_food_prices GROUP BY 1, 2, 3),
             s AS (SELECT period, category, AVG(avg_price) AS cat_avg,
                    SUM(AVG(avg_price)) OVER (PARTITION BY period) AS total
                   FROM m GROUP BY period, category)
             SELECT period, category, cat_avg / total * 100 AS share FROM s"""
    got = sql_problems(sql, mixed_unit_tables([PRICES]))
    assert got and "DIFFERENT items" in got[0]


def test_per_item_change_is_fine():
    from app.services.source_brief import sql_problems
    sql = """WITH m AS (SELECT date_trunc('month', date) AS period, commodity,
                    AVG(price_egp) AS p FROM wfp_food_prices GROUP BY 1, 2)
             SELECT c.period, c.commodity, (c.p - b.p) / b.p * 100 AS yoy_pct,
                    AVG((c.p - b.p) / b.p) OVER (PARTITION BY c.period) AS avg_yoy
             FROM m c JOIN m b ON b.commodity = c.commodity AND c.period = b.period + interval '1 year'"""
    assert sql_problems(sql, mixed_unit_tables([PRICES])) == []


def test_a_latest_rank_that_is_never_filtered_is_refused():
    from app.services.source_brief import sql_problems
    sql = """WITH r AS (SELECT commodity, price_egp,
                    ROW_NUMBER() OVER (PARTITION BY commodity ORDER BY date DESC) AS rn
                    FROM wfp_food_prices)
             SELECT commodity, price_egp FROM r"""
    assert any("rn ranks the rows" in g for g in sql_problems(sql, {}))
    assert sql_problems(sql.replace("FROM r", "FROM r WHERE rn = 1"), {}) == []


def test_a_latest_title_over_all_periods_is_refused():
    w = normalise_widget({"widget_type": "kpi", "title": "أعلى معدل تضخم (أحدث شهر)",
                          "measure": "yoy_change_pct", "aggregation": "max"})
    got = assess({"widgets": [w]}, COLS, ROWS)
    assert any("latest" in g for g in got)
    w = normalise_widget({"widget_type": "kpi", "title": "أعلى معدل تضخم (أحدث شهر)",
                          "measure": "yoy_change_pct", "aggregation": "max",
                          "filter_column": "is_latest", "filter_value": "1"})
    assert assess({"widgets": [w]}, COLS, ROWS) == []


def test_unrelated_tables_cross_joined_are_refused():
    from app.services.source_brief import sql_problems
    sql = """WITH p AS (SELECT admin1_name, headcount_ratio FROM poverty_rate WHERE year = 2014),
             r AS (SELECT age_range, SUM(population) AS refugees FROM refugees_in_egypt GROUP BY age_range)
             SELECT p.admin1_name, p.headcount_ratio, r.refugees FROM p LEFT JOIN r ON TRUE"""
    assert any("no key" in g for g in sql_problems(sql, {}))
    one_row = """WITH t AS (SELECT SUM(population) AS total FROM population_by_governorate),
                 p AS (SELECT admin1_name, population FROM population_by_governorate)
                 SELECT p.admin1_name, p.population / t.total AS share FROM p CROSS JOIN t"""
    assert sql_problems(one_row, {}) == []


REFUGEES = {"name": "refugees_in_egypt", "rows": 46540, "columns": [
    {"name": "year", "dtype": "integer"},
    {"name": "gender", "dtype": "text", "distinct": 3,
     "top_k": [{"value": "f", "count": 1}, {"value": "m", "count": 1}, {"value": "all", "count": 1}]},
    {"name": "age_range", "dtype": "text", "distinct": 6,
     "top_k": [{"value": "0-4"}, {"value": "5-11"}, {"value": "12-17"}, {"value": "all"}]},
    {"name": "population", "dtype": "integer"}]}


def test_total_rows_are_named_and_summing_them_with_parts_is_refused():
    from app.services.source_brief import sql_problems, total_rows
    assert "TOTALS" in " ".join(table_warnings(REFUGEES))
    totals = total_rows([REFUGEES])
    assert totals == {"refugees_in_egypt": {"gender": "all", "age_range": "all"}}
    bad = "SELECT population_group, SUM(population) AS n FROM refugees_in_egypt WHERE year = 2025 GROUP BY 1"
    assert len(sql_problems(bad, {}, totals)) == 2
    good = ("SELECT age_range, SUM(population) AS n FROM refugees_in_egypt "
            "WHERE year = 2025 AND gender = 'all' AND age_range <> 'all' GROUP BY 1")
    assert sql_problems(good, {}, totals) == []


def test_short_text_columns_are_enumerated_live_when_the_sync_left_none():
    import asyncio
    from app.services.source_brief import enrich_facts, total_rows
    table = {"name": "refugees_in_egypt", "rows": 100, "columns": [
        {"name": "gender", "dtype": "text", "distinct": 3},
        {"name": "population", "dtype": "integer"}]}
    asked = []

    async def run_query(sql, limit):
        if "COUNT(*) AS n FROM" in sql and "GROUP BY" not in sql:
            return {"columns": ["n"], "rows": [[30]]}
        asked.append(sql)
        return {"columns": ["value", "n"], "rows": [["f", 10], ["m", 10], ["all", 10]]}
    asyncio.run(enrich_facts([table], run_query))
    assert len(asked) == 1 and '"gender"' in asked[0] and table["rows"] == 30
    assert total_rows([table]) == {"refugees_in_egypt": {"gender": "all"}}


def test_the_failing_charts_are_known_by_position_even_with_quotes_in_titles():
    p = _p({"widget_type": "bar", "title": "Prices 'National' vs 'Cairo'", "dimension": "governorate",
            "measure": "yoy_change_pct", "aggregation": "avg"},
           {"widget_type": "bar", "title": "fine", "dimension": "commodity",
            "measure": "yoy_change_pct", "aggregation": "avg"},
           {"widget_type": "kpi", "title": "bad kpi", "measure": "governorate", "aggregation": "max"})
    bad = set()
    assess(p, COLS, ROWS, None, bad)
    assert bad == {0, 2}


def test_a_zero_row_estimate_is_checked_before_calling_a_table_empty():
    import asyncio
    from app.services.source_brief import enrich_facts
    depts = {"name": "departments", "rows": 0, "columns": [{"name": "dept_name", "dtype": "text"}]}
    gone = {"name": "returnees", "rows": 0, "columns": [{"name": "gender", "dtype": "text"}]}
    assert "EMPTY" not in " ".join(table_warnings(depts))       # an estimate alone says nothing

    async def run_query(sql, limit):
        if "departments" in sql:
            return {"columns": ["x"], "rows": [[1]]} if "present" in sql else \
                {"columns": ["value", "n"], "rows": [["Sales", 1], ["HR", 1]]}
        return {"columns": ["x"], "rows": []}
    asyncio.run(enrich_facts([depts, gone], run_query))
    assert depts["rows"] is None and "EMPTY" not in facts_text([depts])
    assert gone.get("checked_empty") and "EMPTY" in " ".join(table_warnings(gone))


def test_a_huge_catalog_is_cut_to_the_budget():
    tables = [{"name": f"t{i}", "rows": i, "columns": [{"name": f"c{j}", "dtype": "text",
                                                         "description": "x" * 100} for j in range(10)]}
              for i in range(80)]
    text = facts_text(tables, budget=8000)
    assert len(text) < 10_500 and "TABLE t79" in text and "TABLE t0" in text


def test_a_per_department_number_repeated_on_each_title_row_is_not_summed():
    cols = ["dept", "title", "dept_headcount"]
    rows = [["Sales", t, 100] for t in ("A", "B", "C")] + [["HR", t, 40] for t in ("A", "B")] \
        + [["Dev", t, 300] for t in ("A", "B", "C", "D")]
    got = assess(_p({"widget_type": "bar", "title": "Headcount", "dimension": "dept",
                     "measure": "dept_headcount", "aggregation": "sum"}), cols, rows)
    assert any("SUM multiplies" in g for g in got)
    ok = assess(_p({"widget_type": "bar", "title": "Headcount", "dimension": "dept",
                    "measure": "dept_headcount", "aggregation": "max"}), cols, rows)
    assert ok == []


def test_today_in_old_data_and_open_ended_dates():
    from app.services.source_brief import data_end, sql_problems
    emp = {"name": "dept_emp", "rows": 10, "columns": [
        {"name": "from_date", "dtype": "date", "min": "1985-01-01", "max": "2002-08-01"},
        {"name": "to_date", "dtype": "date", "min": "1985-02-01", "max": "9999-01-01"}]}
    assert "STILL OPEN" in " ".join(table_warnings(emp))
    assert data_end([emp]) == "2002-08-01"
    sql = "SELECT CURRENT_DATE - from_date AS tenure FROM dept_emp"
    assert any("data ends on 2002-08-01" in g for g in sql_problems(sql, {}, None, "2002-08-01"))
    assert sql_problems(sql, {}, None, None) == []


def test_a_cross_joined_grouped_subquery_is_refused():
    from app.services.source_brief import sql_problems
    sql = ("WITH s AS (SELECT seller_id, COUNT(*) AS n FROM order_items GROUP BY seller_id) "
           "SELECT * FROM s CROSS JOIN (SELECT category, AVG(price) AS p FROM items GROUP BY category) c")
    assert any("no key" in g for g in sql_problems(sql, {}))
    one = "SELECT * FROM order_items CROSS JOIN (SELECT MAX(date) AS d FROM orders) m"
    assert not any("(SELECT" in g for g in sql_problems(one, {}))


def test_an_average_of_rates_over_groups_of_different_size_is_refused():
    cols = ["state", "seller_state", "total_orders", "cancel_rate_pct"]
    rows = [["SP", "SP", 40000, 0.5], ["SP", "RJ", 3, 33.3], ["RJ", "SP", 9000, 0.7], ["RJ", "RJ", 5, 20.0]]
    got = assess(_p({"widget_type": "bar", "title": "Cancel rate", "dimension": "state",
                     "measure": "cancel_rate_pct", "aggregation": "avg"}), cols, rows)
    assert any("average of rates" in g for g in got)


def test_sampled_statistics_are_not_read_as_facts_about_the_table():
    from app.services.source_brief import is_sampled
    geo = {"name": "geolocation", "rows": 1_000_163, "columns": [
        {"name": "geolocation_state", "dtype": "text", "distinct": 1, "top_k": [{"value": "SP", "count": 1000}]},
        {"name": "geolocation_zip_code_prefix", "dtype": "text", "distinct": 437}]}
    assert is_sampled(geo)
    geo["sampled"] = True
    for c in geo["columns"]:
        c["sample_only"] = True
    assert "holds only" not in " ".join(table_warnings(geo))
    assert "sample" in facts_text([geo])


def test_percentages_are_never_summed_across_groups():
    cols = ["state", "seller", "failure_rate_pct"]
    rows = [["SP", "a", 1.0], ["SP", "b", 2.0], ["RJ", "c", 3.0]]
    got = assess(_p({"widget_type": "kpi", "title": "Overall failure rate", "measure": "failure_rate_pct",
                     "aggregation": "sum"}), cols, rows)
    assert any("adds percentages" in g for g in got)
    one_row_each = [["SP", "a", 1.0], ["RJ", "c", 3.0]]
    assert assess(_p({"widget_type": "bar", "title": "x", "dimension": "state", "measure": "failure_rate_pct",
                      "aggregation": "sum"}), cols, one_row_each) == []


def test_a_comparison_written_into_the_filter_value_is_understood():
    w = normalise_widget({"widget_type": "bar", "title": "Cancel rate of sellers", "dimension": "commodity",
                          "measure": "yoy_change_pct", "aggregation": "avg",
                          "filter_column": "price", "filter_value": "price >= 20"})
    assert w["filters"] == [{"column": "price", "op": "gte", "value": 20}]
    assert assess({"widgets": [w]}, COLS, ROWS) == []
    w2 = normalise_widget({"widget_type": "kpi", "title": "x", "measure": "price", "aggregation": "max",
                           "filter_column": "price", "filter_value": "> 1000"})
    assert any("no row has price gt 1000" in g for g in assess({"widgets": [w2]}, COLS, ROWS))


def test_each_chart_states_its_answer_and_says_flat_when_it_is():
    from app.services.source_brief import findings
    p = _p({"widget_type": "bar", "title": "YoY by item", "dimension": "commodity",
            "measure": "yoy_change_pct", "aggregation": "avg", "filter_column": "is_latest", "filter_value": "1"},
           {"widget_type": "kpi", "title": "Highest", "measure": "yoy_change_pct", "aggregation": "max",
            "filter_column": "is_latest", "filter_value": "1"})
    findings(p, COLS, ROWS)
    assert p["widgets"][0]["finding"] == "Highest Eggs (medium size): 30; lowest Rice: 12"
    assert p["widgets"][1]["finding"] == "30 (Eggs (medium size))"
    flat = _p({"widget_type": "bar", "title": "Revenue by channel", "dimension": "ch",
               "measure": "amt", "aggregation": "sum"})
    findings(flat, ["ch", "amt"], [["Online", 2_789_665], ["Retail", 2_666_663], ["Partner", 2_691_165]])
    assert flat["widgets"][0]["finding"].startswith("Flat:")


def test_duration_is_not_a_ratio():
    from app.services.source_brief import _RATE_WORDS
    assert not _RATE_WORDS.search("total_duration_ms")
    assert _RATE_WORDS.search("cancel_rate_pct") and _RATE_WORDS.search("orders_per_day")
    assert _RATE_WORDS.search("share") and not _RATE_WORDS.search("shareholders")


def test_fan_trap_and_unknown_joins_are_refused():
    from app.services.source_brief import sql_problems
    trap = ("SELECT r.id, COUNT(rv.id) AS views, COUNT(qr.id) AS runs FROM reports r "
            "LEFT JOIN recent_views rv ON r.id = rv.report_id LEFT JOIN query_runs qr ON r.id = qr.report_id "
            "GROUP BY r.id")
    assert any("fan trap" in g for g in sql_problems(trap, {}))
    joins = [{"from_table": "recent_views", "from_column": "report_id", "to_table": "reports", "to_column": "id"}]
    catalog = [{"name": n, "columns": []} for n in ("reports", "recent_views", "query_runs")]
    bad = "SELECT r.id FROM reports r JOIN query_runs qr ON r.id = qr.dataset_id"
    assert any("not a relationship" in g for g in sql_problems(bad, {}, joins=joins, catalog=catalog))
    good = "SELECT r.id FROM reports r JOIN recent_views rv ON r.id = rv.report_id"
    assert sql_problems(good, {}, joins=joins, catalog=catalog) == []
    same_name = "SELECT 1 FROM poverty_rate p JOIN population_by_governorate g ON p.admin1_code = g.admin1_code"
    cat2 = [{"name": "poverty_rate", "columns": []}, {"name": "population_by_governorate", "columns": []}]
    assert sql_problems(same_name, {}, joins=[], catalog=cat2) == []


def test_stale_statistics_are_measured_again():
    from app.services.source_brief import is_sampled
    runs = {"name": "agent_runs", "rows": 350, "columns": [
        {"name": "status", "dtype": "text", "distinct": 1, "top_k": [{"value": "failed", "count": 3}]}]}
    assert is_sampled(runs)
    fresh = {"name": "agent_runs", "rows": 350, "columns": [
        {"name": "status", "dtype": "text", "distinct": 2,
         "top_k": [{"value": "ok", "count": 300}, {"value": "failed", "count": 50}]}]}
    assert not is_sampled(fresh)


def test_a_dashboard_that_keeps_mixing_subjects_is_narrowed_to_one():
    import asyncio
    from app.services import source_brief as sb
    catalog = [{"name": n, "rows": 10, "columns": [{"name": "x", "dtype": "integer"}]} for n in ("a", "b")]
    brief = {"language": "en", "role": "r", "understanding": "u", "cannot_answer": [],
             "questions": [{"question": "qa", "tables": ["a"]}, {"question": "qb", "tables": ["b"]}],
             "dashboards": [{"title": "T", "questions": [1, 2]}]}
    bad = {"proposals": [{"title": "T", "sql": "SELECT a.x FROM a CROSS JOIN (SELECT x FROM b GROUP BY x) s",
                          "widgets": [{"widget_type": "kpi", "title": "k", "measure": "x", "aggregation": "sum",
                                       "question": "", "dimension": "", "dimension2": ""}]}]}
    good = {"proposals": [{"title": "T", "sql": "SELECT x FROM a",
                           "widgets": [{"widget_type": "kpi", "title": "k", "measure": "x", "aggregation": "sum",
                                        "question": "", "dimension": "", "dimension2": ""}]}]}
    seen = []

    class Client:
        async def complete_json(self, messages, schema, **kw):
            if schema is sb.BRIEF_SCHEMA:
                return brief
            seen.append(messages[-1]["content"])
            return good if "One subject only" in messages[-1]["content"] else bad

    async def run_query(sql, limit):
        return {"columns": ["x"], "rows": [[1], [2]]}
    props, _, _ = asyncio.run(sb.design(client=Client(), catalog=catalog, persona="p", request="r",
                                        joins=[], run_query=run_query, count=1))
    assert props and props[0]["questions"] == ["qa"]


def test_a_finding_read_off_cut_rows_says_so():
    from app.services.source_brief import findings
    p = _p({"widget_type": "bar", "title": "x", "dimension": "commodity", "measure": "price", "aggregation": "max"})
    findings(p, COLS, ROWS, cut=True)
    assert p["widgets"][0]["finding"].endswith("(on the first 5 rows)")


OLIST_JOINS = [
    {"from_table": "order_payments", "from_column": "order_id", "to_table": "orders", "to_column": "order_id",
     "cardinality": "many_to_one"},
    {"from_table": "orders", "from_column": "customer_id", "to_table": "customers", "to_column": "customer_id",
     "cardinality": "many_to_one"},
]


def test_rows_repeated_by_a_join_inside_a_cte_are_not_counted():
    from app.services.source_brief import sql_problems
    sql = """WITH m AS (SELECT o.order_id, c.customer_state, o.order_status, p.payment_type
                        FROM orders o JOIN customers c ON o.customer_id = c.customer_id
                        LEFT JOIN order_payments p ON o.order_id = p.order_id)
             SELECT customer_state, COUNT(*) AS total_orders,
                    SUM(CASE WHEN order_status = 'canceled' THEN 1 ELSE 0 END) AS canceled
             FROM m GROUP BY customer_state"""
    got = sql_problems(sql, {}, joins=OLIST_JOINS)
    assert any("order_payments" in g and "COUNT(DISTINCT" in g for g in got)
    distinct = sql.replace("COUNT(*) AS total_orders", "COUNT(DISTINCT order_id) AS total_orders") \
        .replace("SUM(CASE WHEN order_status = 'canceled' THEN 1 ELSE 0 END)",
                 "COUNT(DISTINCT CASE WHEN order_status = 'canceled' THEN order_id END)")
    assert sql_problems(distinct, {}, joins=OLIST_JOINS) == []


def test_summing_the_many_side_itself_is_fine_and_the_direct_case_is_caught():
    from app.services.source_brief import sql_problems
    ok = ("SELECT o.order_status, SUM(p.payment_value) AS paid FROM orders o "
          "JOIN order_payments p ON o.order_id = p.order_id GROUP BY o.order_status")
    assert sql_problems(ok, {}, joins=OLIST_JOINS) == []
    bad = ("SELECT c.customer_state, COUNT(*) AS orders FROM orders o "
           "JOIN customers c ON o.customer_id = c.customer_id "
           "JOIN order_payments p ON o.order_id = p.order_id GROUP BY c.customer_state")
    assert any("COUNT(*)" in g for g in sql_problems(bad, {}, joins=OLIST_JOINS))
    # Without cardinality nothing is guessed.
    assert sql_problems(bad, {}, joins=[{**j, "cardinality": None} for j in OLIST_JOINS]) == []


def test_a_max_kpi_names_what_it_points_at():
    from app.services.source_brief import findings
    p = _p({"widget_type": "kpi", "title": "Highest yearly rise", "measure": "yoy_change_pct",
            "aggregation": "max", "filter_column": "is_latest", "filter_value": "1"})
    findings(p, COLS, ROWS)
    assert p["widgets"][0]["finding"] == "30 (Eggs (medium size))"


def test_the_request_answers_with_what_is_ready_at_the_deadline():
    import asyncio
    from app.services import source_brief as sb
    catalog = [{"name": n, "rows": 10, "columns": [{"name": "x", "dtype": "integer"}]} for n in ("a", "b")]
    brief = {"language": "en", "role": "r", "understanding": "u", "cannot_answer": [],
             "questions": [{"question": "qa", "tables": ["a"]}, {"question": "qb", "tables": ["b"]}],
             "dashboards": [{"title": "A", "questions": [1]}, {"title": "B", "questions": [2]}]}
    good = lambda t: {"proposals": [{"title": t, "sql": f"SELECT x FROM {t.lower()}", "widgets": [
        {"widget_type": "kpi", "title": "k", "measure": "x", "aggregation": "sum",
         "question": "", "dimension": "", "dimension2": ""}]}]}

    class Client:
        async def complete_json(self, messages, schema, **kw):
            if schema is sb.BRIEF_SCHEMA:
                return brief
            if "THIS DASHBOARD: B" in messages[-1]["content"]:
                await asyncio.sleep(5)
            return good("A" if "THIS DASHBOARD: A" in messages[-1]["content"] else "B")

    async def run_query(sql, limit):
        return {"columns": ["x"], "rows": [[1], [2]]}
    sb._brief_get = lambda key: None
    props, _, why = asyncio.run(sb.design(client=Client(), catalog=catalog, persona="p", request="r",
                                          joins=[], run_query=run_query, count=2, deadline_s=0.5))
    assert [p["title"] for p in props] == ["A"] and "B: not finished in time" in why


def test_the_brief_is_reused_for_the_same_question():
    import asyncio
    from app.services import source_brief as sb
    store = {}
    sb._brief_get, sb._brief_set = store.get, store.__setitem__
    catalog = [{"name": "a", "rows": 10, "columns": [{"name": "x", "dtype": "integer"}]}]
    calls = []

    class Client:
        async def complete_json(self, messages, schema, **kw):
            calls.append(schema is sb.BRIEF_SCHEMA)
            if schema is sb.BRIEF_SCHEMA:
                return {"language": "en", "role": "r", "understanding": "u", "cannot_answer": [],
                        "questions": [{"question": "q", "tables": ["a"]}]}
            return {"proposals": [{"title": "T", "sql": "SELECT x FROM a", "widgets": [
                {"widget_type": "kpi", "title": "k", "measure": "x", "aggregation": "sum",
                 "question": "", "dimension": "", "dimension2": ""}]}]}

    async def run_query(sql, limit):
        return {"columns": ["x"], "rows": [[1]]}
    for _ in range(2):
        asyncio.run(sb.design(client=Client(), catalog=catalog, persona="p", request="same",
                              joins=[], run_query=run_query, count=1))
    assert calls.count(True) == 1


def test_two_summaries_joined_on_a_shared_attribute_are_refused():
    from app.services.source_brief import sql_problems
    sql = """WITH s AS (SELECT seller_id, seller_state, COUNT(*) AS n FROM sellers GROUP BY seller_id, seller_state),
                  c AS (SELECT customer_city, customer_state, COUNT(*) AS m FROM customers
                        GROUP BY customer_city, customer_state)
             SELECT * FROM s JOIN c ON s.seller_state = c.customer_state"""
    assert any("unique in neither" in g for g in sql_problems(sql, {}))
    on_key = """WITH a AS (SELECT state, COUNT(*) AS n FROM sellers GROUP BY state),
                     b AS (SELECT state, COUNT(*) AS m FROM customers GROUP BY state)
                SELECT * FROM a JOIN b ON a.state = b.state"""
    assert sql_problems(on_key, {}) == []


def test_a_rate_ranking_led_by_tiny_groups_is_refused():
    cols = ["seller", "total_orders", "low_score_rate"]
    rows = [["a", 1, 1.0], ["b", 2, 0.5], ["c", 300, 0.2], ["d", 500, 0.1]]
    got = assess(_p({"widget_type": "bar", "title": "Worst sellers", "dimension": "seller",
                     "measure": "low_score_rate", "aggregation": "max", "sort": "desc"}), cols, rows)
    assert any("noise" in g for g in got)
    big = [["a", 40, 1.0], ["b", 52, 0.5], ["c", 300, 0.2], ["d", 500, 0.1]]
    assert assess(_p({"widget_type": "bar", "title": "Worst sellers", "dimension": "seller",
                      "measure": "low_score_rate", "aggregation": "max", "sort": "desc"}), cols, big) == []


def test_a_continuous_number_is_not_a_line_axis():
    cols = ["days", "score"]
    rows = [[i / 3, 5 - i / 100] for i in range(60)]
    got = assess(_p({"widget_type": "line", "title": "Score vs days", "dimension": "days",
                     "measure": "score", "aggregation": "avg"}), cols, rows)
    assert any("continuous number" in g for g in got)


def test_only_a_zero_filled_measure_is_suspected_of_hiding_a_join():
    from app.services.source_brief import coalesced_to_zero
    sql = ("WITH s AS (SELECT state, COALESCE(SUM(fail), 0) AS failures, COUNT(*) AS n FROM o GROUP BY state) "
           "SELECT state, failures, failures * 100.0 / n AS failure_rate_pct, COALESCE(name, 'x') AS label FROM s")
    got = coalesced_to_zero(sql)
    assert "failures" in got and "failure_rate_pct" in got and "label" not in got and "n" not in got
    real_zeros = _p({"widget_type": "bar", "title": "Failure rate", "dimension": "commodity",
                     "measure": "price", "aggregation": "max"})
    real_zeros["sql"] = "SELECT commodity, price, COALESCE(unit, 'n/a') AS unit FROM t"
    rows = [r[:3] + [0.0] + r[4:] for r in ROWS[:3]] + ROWS[3:]
    assert not any("COALESCE" in g for g in assess(real_zeros, COLS, rows))


def test_totals_after_a_dataset_wide_volume_cut_are_refused():
    cols = ["seller_state", "total_orders", "late_orders", "late_rate_pct"]
    rows = [["SP", 40, 5, 12.5], ["SP", 30, 3, 10.0], ["RJ", 25, 2, 8.0]]
    p = _p({"widget_type": "bar", "title": "Late orders by state", "dimension": "seller_state",
            "measure": "late_orders", "aggregation": "sum"})
    p["sql"] = "WITH s AS (SELECT 1) SELECT seller_state, total_orders, late_orders FROM s WHERE total_orders >= 10"
    assert any("leaves them out" in g for g in assess(p, cols, rows))
    p["sql"] = "SELECT seller_state, total_orders, late_orders FROM s"
    assert assess(p, cols, rows) == []


def test_comments_and_trailing_semicolons_are_not_a_second_statement():
    from app.services.source_brief import clean_sql
    sql = "SELECT a, -- the share; per order\n b FROM t /* note; */ WHERE c = 'x;y';"
    out = clean_sql(sql)
    assert out.count(";") == 1 and "'x;y'" in out and "--" not in out and "/*" not in out


def test_a_semicolon_inside_a_string_is_not_a_second_statement():
    from app.services.source_brief import _static_problems
    p = {"sql": "SELECT x FROM a WHERE c = 'x;y'",
         "widgets": [normalise_widget({"widget_type": "kpi", "title": "k", "measure": "x", "aggregation": "sum"})]}
    assert _static_problems(p, {"a"}, [], lambda s, c: (True, "")) is None
    p["sql"] = "SELECT x FROM a; DROP TABLE a"
    assert _static_problems(p, {"a"}, [], lambda s, c: (True, ""))


def test_child_rows_counted_as_parents_are_refused():
    from app.services.source_brief import sql_problems
    sql = ("SELECT payment_type, COUNT(*) AS total_orders FROM order_payments GROUP BY payment_type")
    got = sql_problems(sql, {}, joins=OLIST_JOINS)
    assert any("counts order_payments rows, not orders" in g for g in got)
    ok = "SELECT payment_type, COUNT(DISTINCT order_id) AS total_orders FROM order_payments GROUP BY payment_type"
    assert sql_problems(ok, {}, joins=OLIST_JOINS) == []
    payments = "SELECT payment_type, COUNT(*) AS payments FROM order_payments GROUP BY payment_type"
    assert sql_problems(payments, {}, joins=OLIST_JOINS) == []
    cte = ("WITH s AS (SELECT p.payment_type, COUNT(*) AS order_count FROM order_payments p "
           "JOIN orders o ON o.order_id = p.order_id GROUP BY p.payment_type) SELECT * FROM s")
    assert any("order_count" in g for g in sql_problems(cte, {}, joins=OLIST_JOINS))


def test_the_designer_reports_where_its_time_went():
    import asyncio
    from app.services import source_brief as sb
    sb._brief_get, sb._brief_set = (lambda k: None), (lambda k, v: None)
    catalog = [{"name": "a", "rows": 10, "columns": [{"name": "x", "dtype": "integer"}]}]

    class Client:
        async def complete_json(self, messages, schema, **kw):
            if schema is sb.BRIEF_SCHEMA:
                return {"language": "en", "role": "r", "understanding": "u", "cannot_answer": [],
                        "questions": [{"question": "q", "tables": ["a"]}]}
            return {"proposals": [{"title": "T", "sql": "SELECT x FROM a", "widgets": [
                {"widget_type": "kpi", "title": "k", "measure": "x", "aggregation": "sum",
                 "question": "", "dimension": "", "dimension2": ""}]}]}

    async def run_query(sql, limit):
        return {"columns": ["x"], "rows": [[1]]}
    _, brief, _ = asyncio.run(sb.design(client=Client(), catalog=catalog, persona="p", request="r",
                                        joins=[], run_query=run_query, count=1))
    t = brief["_timings"]
    assert {"brief_s", "brief_cached", "dashboards_s", "total_s"} <= set(t) and t["brief_cached"] is False


def test_a_join_whose_on_links_no_columns_is_refused():
    """"ON opa.payment_type = 'boleto'" put one boleto row beside every year,
    so boleto revenue was summed three times (Olist, live 2026-10-04)."""
    from app.services.source_brief import sql_problems
    sql = ("WITH a AS (SELECT payment_type, SUM(payment_value) AS v FROM order_payments GROUP BY payment_type), "
           "b AS (SELECT EXTRACT(YEAR FROM order_purchase_timestamp) AS y, COUNT(*) AS n FROM orders GROUP BY 1) "
           "SELECT a.payment_type, a.v, b.y, b.n FROM a LEFT JOIN b ON a.payment_type = 'boleto'")
    assert any("no key" in g for g in sql_problems(sql, {}))
    keyed = ("WITH a AS (SELECT order_id, SUM(payment_value) AS v FROM order_payments GROUP BY order_id) "
             "SELECT o.order_status, SUM(a.v) FROM orders o JOIN a ON a.order_id = o.order_id "
             "AND o.order_status = 'delivered' GROUP BY 1")
    assert not any("no key" in g for g in sql_problems(keyed, {}))


def test_a_rate_title_over_a_count_is_refused():
    """"Cancellation rate by payment method: credit_card 444" drew cancelled
    orders, not a rate (Olist, live 2026-10-04)."""
    cols = ["payment_type", "canceled_orders", "cancellation_rate"]
    rows = [["credit_card", 444, 0.0058], ["boleto", 120, 0.0060], ["debit_card", 7, 0.0047]]
    count = assess(_p({"widget_type": "bar", "title": "Cancellation Rate by Payment Method",
                       "dimension": "payment_type", "measure": "canceled_orders"}), cols, rows)
    assert any("promises a rate" in g for g in count)
    rate = assess(_p({"widget_type": "bar", "title": "Cancellation Rate by Payment Method",
                      "dimension": "payment_type", "measure": "cancellation_rate", "aggregation": "max"}), cols, rows)
    assert not any("promises a rate" in g for g in rate)


def test_a_year_axis_is_written_as_a_year():
    from app.services.source_brief import findings
    p = {"widgets": [{"widget_type": "line", "title": "Boleto orders", "dimension": "y", "measure": "n"}]}
    findings(p, ["y", "n"], [[2016.0, 63], [2017.0, 9000], [2018.0, 10213]])
    assert p["widgets"][0]["finding"] == "63 at 2016 → 10,213 at 2018; peak 10,213 at 2018"


def test_a_key_counted_over_a_finer_grain_is_probed():
    """"Total delivered orders: 97,325" summed per-instalment-plan order
    counts; there are 96,478 orders (Olist, live 2026-10-04). Whether the
    grain is finer is a fact about the data, so it is asked of the data."""
    from app.services.source_brief import grain_messages, grain_probes
    sql = ("WITH t AS (SELECT op.order_id, op.payment_installments, SUM(op.payment_value) AS v "
           "FROM order_payments op GROUP BY op.order_id, op.payment_installments) "
           "SELECT payment_installments, COUNT(order_id) AS order_count FROM t GROUP BY payment_installments")
    got = grain_probes(sql)
    assert len(got) == 1 and got[0]["groups"] == ["payment_installments"] and not got[0]["others"]
    assert "COUNT(DISTINCT order_id)" in got[0]["probe"] and "FROM t" in got[0]["probe"]
    widgets = [{"widget_type": "kpi", "title": "Total delivered orders", "measure": "order_count"},
               {"widget_type": "bar", "title": "Orders by plan", "measure": "order_count",
                "dimension": "payment_installments"}]
    whole, per = grain_messages(got[0], 97325, 96478, widgets)
    assert whole is None and list(per) == [0] and "97,325" in per[0]
    inflated = sql.replace("SELECT payment_installments, COUNT", "SELECT COUNT").replace(
        " GROUP BY payment_installments", "")
    found = grain_probes(inflated)
    whole, per = grain_messages(found[0], 97325, 96478, widgets)
    assert whole and "counted twice" in whole
    assert grain_probes(sql.replace("COUNT(order_id)", "COUNT(DISTINCT order_id)")) == []


def test_the_designer_drops_a_total_the_probe_proves_double_counted():
    import asyncio

    from app.services import source_brief as sb
    sb._brief_get, sb._brief_set = (lambda k: None), (lambda k, v: None)
    catalog = [{"name": "order_payments", "rows": 100, "columns": [
        {"name": "order_id", "dtype": "text"}, {"name": "payment_installments", "dtype": "integer"}]}]
    sql = ("WITH t AS (SELECT order_id, payment_installments FROM order_payments "
           "GROUP BY order_id, payment_installments) "
           "SELECT payment_installments, COUNT(order_id) AS order_count FROM t GROUP BY payment_installments")
    w = {"question": "", "dimension2": "", "aggregation": "sum", "measure": "order_count"}

    class Client:
        async def complete_json(self, messages, schema, **kw):
            if schema is sb.BRIEF_SCHEMA:
                return {"language": "en", "role": "r", "understanding": "u", "cannot_answer": [],
                        "questions": [{"question": "q", "tables": ["order_payments"]}]}
            return {"proposals": [{"title": "Plans", "sql": sql, "widgets": [
                {**w, "widget_type": "kpi", "title": "Total orders", "dimension": ""},
                {**w, "widget_type": "bar", "title": "Orders by plan", "dimension": "payment_installments"},
                {**w, "widget_type": "pie", "title": "Plan mix", "dimension": "payment_installments"}]}]}

    async def run_query(q, limit):
        if q.lstrip().upper().startswith("WITH") and "COUNT(DISTINCT" in q:
            return {"columns": ["n", "k"], "rows": [[97325, 96478]]}
        return {"columns": ["payment_installments", "order_count"], "rows": [[1, 50], [2, 30], [3, 20]]}
    kept, _, _ = asyncio.run(sb.design(client=Client(), catalog=catalog, persona="p", request="r",
                                       joins=[], run_query=run_query, count=1))
    assert kept and [x["title"] for x in kept[0]["widgets"]] == ["Orders by plan", "Plan mix"]
    assert any("97,325" in d for d in kept[0]["dropped"])


def test_a_total_of_per_group_distinct_counts_is_checked_against_the_real_total():
    """"Orders using multiple payments: 5,207" summed per-method distinct
    counts; an order paid by card and voucher sits in both (Olist, live
    2026-10-04)."""
    import asyncio

    from app.services.source_brief import _distinct_totals, distinct_total_probes
    sql = ("WITH s AS (SELECT op.order_id, op.payment_type, c.n FROM order_payments op JOIN c ON c.order_id = op.order_id), "
           "t AS (SELECT payment_type, COUNT(DISTINCT CASE WHEN n > 1 THEN order_id END) AS multi_orders "
           "FROM s GROUP BY payment_type) SELECT payment_type, multi_orders FROM t")
    found = distinct_total_probes(sql)
    assert found[0]["alias"] == "multi_orders" and found[0]["groups"] == ["payment_type"]
    assert found[0]["probe"].upper().endswith("AS K FROM S") and found[0]["probe"].upper().startswith("WITH")
    p = {"sql": sql, "widgets": [
        {"widget_type": "kpi", "title": "Multi-payment orders", "measure": "multi_orders", "aggregation": "sum"},
        {"widget_type": "bar", "title": "By method", "measure": "multi_orders", "dimension": "payment_type"}]}
    out = {"columns": ["payment_type", "multi_orders"], "rows": [["voucher", 2672], ["credit_card", 2535]]}

    async def run(q, limit):
        return {"columns": ["k"], "rows": [[2961]]}
    bad, msgs = asyncio.run(_distinct_totals(p, out, run))
    assert bad == {0} and "5,207 summed vs 2,961" in msgs[0]

    async def disjoint(q, limit):
        return {"columns": ["k"], "rows": [[5207]]}
    assert asyncio.run(_distinct_totals(p, out, disjoint)) == (set(), [])


def test_payment_rows_counted_through_a_cte_are_refused():
    from app.services.source_brief import sql_problems
    sql = ("WITH base AS (SELECT op.payment_type, o.order_status FROM order_payments op "
           "JOIN orders o ON op.order_id = o.order_id) "
           "SELECT payment_type, COUNT(*) AS total_orders FROM base GROUP BY payment_type")
    assert any("not orders" in g or "rows per order" in g for g in sql_problems(sql, {}, joins=OLIST_JOINS))
    grouped = ("WITH base AS (SELECT order_id, MAX(payment_type) AS payment_type FROM order_payments GROUP BY order_id) "
               "SELECT payment_type, COUNT(*) AS total_orders FROM base GROUP BY payment_type")
    assert not any("rows per order" in g for g in sql_problems(grouped, {}, joins=OLIST_JOINS))


def test_a_kpi_adding_a_value_repeated_per_group_is_refused():
    """"Total delivered revenue: 337.05M" -- each method's revenue once per
    month row (Olist, live 2026-10-04)."""
    cols = ["payment_type", "delivered_revenue", "order_month", "payment_count"]
    rows = [[t, rev, mth, 10] for t, rev in (("credit_card", 12.1e6), ("boleto", 2.8e6))
            for mth in ("2018-01", "2018-02", "2018-03")]
    got = assess(_p({"widget_type": "kpi", "title": "Total delivered revenue", "measure": "delivered_revenue"}),
                 cols, rows)
    assert any("repeats the same value" in g for g in got)
    once = [[t, rev, None, 10] for t, rev in (("credit_card", 12.1e6), ("boleto", 2.8e6))]
    assert not any("repeats" in g for g in assess(_p({"widget_type": "kpi", "title": "Total",
                                                      "measure": "delivered_revenue"}), cols, once))


def test_findings_on_cut_or_repeated_rows_do_not_mislead():
    """Olist, live 2026-10-04: "orders using multiple payments: 147" summed
    the first 5,000 of 99,440 rows; "65.7 (00010242fe…)" named an order for a
    value repeated on every row; a count of order ids read 0."""
    from app.services.source_brief import findings
    rows = [[f"o{i}", 1 + (i % 3 == 0), 65.7] for i in range(30)]
    p = {"widgets": [
        {"widget_type": "kpi", "title": "Multi", "measure": "n", "aggregation": "sum"},
        {"widget_type": "kpi", "title": "Avg voucher", "measure": "v", "aggregation": "max"},
        {"widget_type": "bar", "title": "Orders per count", "measure": "order_id", "aggregation": "count",
         "dimension": "n"}]}
    findings(p, ["order_id", "n", "v"], rows, cut=True)
    multi, voucher, per = p["widgets"]
    assert "finding" not in multi
    assert voucher["finding"] == "65.7 (on the first 30 rows)"
    assert per["finding"].startswith("Highest 1: 20; lowest 2: 10")


def test_two_child_tables_joined_on_the_parent_key_are_refused():
    """"Total revenue: 20.31M" joined order_payments to order_items on
    order_id; it is 16.01M (Olist, live 2026-10-04)."""
    from app.services.source_brief import sql_problems
    joins = OLIST_JOINS + [{"from_table": "order_items", "from_column": "order_id", "to_table": "orders",
                            "to_column": "order_id", "cardinality": "many_to_one"}]
    sql = ("SELECT op.payment_type, SUM(op.payment_value) AS total_revenue, AVG(oi.price) AS p "
           "FROM order_payments op JOIN order_items oi ON op.order_id = oi.order_id GROUP BY op.payment_type")
    assert any("both have several rows per order" in g for g in sql_problems(sql, {}, joins=joins))
    fine = ("WITH i AS (SELECT order_id, SUM(price) AS items FROM order_items GROUP BY order_id) "
            "SELECT o.order_status, SUM(i.items) FROM orders o JOIN i ON i.order_id = o.order_id GROUP BY 1")
    assert not any("both have several rows" in g for g in sql_problems(fine, {}, joins=joins))
