"""Step 2 of the analyst-panel pipeline (2026-10-02): several lenses propose,
everything is drawn, and the data decides what is kept."""
import asyncio

import numpy as np
import pandas as pd

from app.services.analyst_panel import choose_lenses, evidence, run_panel, select
from app.services.analytics import detect_types
from app.services.dataset_profile import build_profile
from app.services.fact_sheet import build_facts
from app.services.insights import effective_roles, generate_insights
from app.services.widget_data import get_widget_data_from_df


def _hr(n=4000, seed=0):
    rng = np.random.default_rng(seed)
    dept = rng.choice(["Sales", "Development", "Finance", "Marketing", "Research"], n)
    title = np.where(np.isin(dept, ["Sales", "Finance", "Marketing"]),
                     rng.choice(["Staff", "Senior Staff"], n, p=[.3, .7]),
                     rng.choice(["Engineer", "Senior Engineer"], n))
    years = rng.uniform(0, 15, n)
    return pd.DataFrame({
        "emp_no": np.arange(10001, 10001 + n), "dept_name": dept, "title": title,
        "gender": rng.choice(["M", "F"], n, p=[.6, .4]),
        "salary": 50000 + np.where(dept == "Sales", 20000, 0) + years * 1200 + rng.normal(0, 4000, n),
        "hire_date": pd.Timestamp("2000-01-01") - pd.to_timedelta(years * 365.25, "D"),
    })


LENS_ANSWERS = {
    "Composition": [
        {"question": "Where do people work?", "widget_type": "treemap", "title": "Headcount by department",
         "config": {"dimension": "dept_name", "measure": "emp_no", "aggregation": "countd"}, "value": 5},
        {"question": "How senior is each department?", "widget_type": "stacked_bar", "title": "Title mix",
         "config": {"dimension": "dept_name", "dimension2": "title", "measure": "emp_no",
                    "aggregation": "countd", "bar_mode": "stacked100"}, "value": 5},
        {"question": "Is gender balanced in every department?", "widget_type": "bar", "title": "Gender by dept",
         "config": {"dimension": "dept_name", "dimension2": "gender", "measure": "emp_no",
                    "aggregation": "countd", "bar_mode": "stacked100"}, "value": 4,
         "why": "Flat: about 40% everywhere."},
        {"question": "Nonsense", "widget_type": "bar", "title": "Bad column",
         "config": {"dimension": "region", "measure": "emp_no", "aggregation": "countd"}, "value": 5},
    ],
    "Levels & drivers": [
        {"question": "Which department pays most?", "widget_type": "bar", "title": "Pay by department",
         "config": {"dimension": "dept_name", "measure": "salary", "aggregation": "avg"}, "value": 5},
        {"question": "Which department pays most? (again)", "widget_type": "bar", "title": "Avg pay by dept",
         "config": {"dimension": "dept_name", "measure": "salary", "aggregation": "avg"}, "value": 3},
        {"question": "Is there a gender gap?", "widget_type": "bar", "title": "Pay by gender",
         "config": {"dimension": "gender", "measure": "salary", "aggregation": "avg"}, "value": 4},
        {"question": "What is typical pay?", "widget_type": "kpi", "title": "Median salary",
         "config": {"measure": "salary", "aggregation": "median"}, "value": 5},
    ],
    "Over time": [
        {"question": "When did we hire?", "widget_type": "line", "title": "Hires per year",
         "config": {"dimension": "year", "measure": "emp_no", "aggregation": "countd"}, "value": 5},
    ],
    "Fairness & like-for-like": [
        {"question": "Are men and women paid alike in each department?", "widget_type": "bar",
         "title": "Average salary by department and gender",
         "config": {"dimension": "dept_name", "dimension2": "gender", "measure": "salary",
                    "aggregation": "avg", "bar_mode": "clustered"}, "value": 5,
         "why": "Flat: the same within every department."},
        {"question": "Sales pay", "widget_type": "histogram", "title": "Salary distribution in Sales",
         "config": {"measure": "salary", "dept_filter": "Sales"}, "value": 4},
    ],
    "Patterns & models": [
        {"question": "What drives pay?", "widget_type": "model_linear", "title": "Pay drivers",
         "config": {"measure": "salary", "predictors": ["title", "dept_name", "hire_date"]}, "value": 5},
    ],
}


class FakeClient:
    def __init__(self):
        self.calls = []

    async def complete_json(self, messages, schema, **kw):
        system = messages[0]["content"]
        lens = next(k for k in LENS_ANSWERS if f"Your lens is {k}" in system)
        self.calls.append(lens)
        assert "MEASURED FACTS" in messages[1]["content"]
        return {"widgets": LENS_ANSWERS[lens]}


def _run(size=12, client="fake"):
    df = _hr()
    tm = detect_types(df)
    roles = effective_roles(tm, {})
    profile = build_profile(df, tm, {})
    facts = build_facts(df, roles)
    findings = generate_insights(df, tm, {})["findings"]
    c = FakeClient() if client == "fake" else None

    async def probe(wt, cfg):
        return get_widget_data_from_df(df, cfg, wt)

    out = asyncio.run(run_panel(df=df, profile=profile, roles=roles, column_meta={}, ineligible=set(),
                                findings=findings, facts=facts, goal="I run HR", size=size,
                                probe=probe, client=c))
    return out, c


def test_lenses_follow_the_shape_of_the_data():
    df = _hr()
    profile = build_profile(df, detect_types(df), {})
    assert choose_lenses(profile, []) == ["composition", "measures", "equity", "time", "relationships"]
    no_dates = df.drop(columns=["hire_date"])
    assert "time" not in choose_lenses(build_profile(no_dates, detect_types(no_dates), {}), [])


def test_a_panel_run_proposes_draws_merges_and_selects():
    out, client = _run(size=12)
    assert sorted(client.calls) == sorted(LENS_ANSWERS)        # one call per lens
    p = out["panel"]
    assert p["from_model"] == 12 and p["from_statistics"] > 0
    assert p["rejected"] >= 1 and "region" in out["reason"]    # invented column dropped, named
    assert p["duplicates_merged"] >= 1                         # the second pay-by-dept
    assert p["selected"] <= 12
    widgets = [w for prop in out["proposals"] for w in prop["widgets"]]
    # Controls and the rows themselves have nothing to read back.
    assert all(w["takeaway"] for w in widgets if not w["widget_type"].startswith("model_rules")
               and w["widget_type"] != "slicer" and w["title"] != "Detail rows")
    titles = [w["title"] for w in widgets]
    assert "Bad column" not in titles
    # the invented "year" was mapped to the date column, so the hiring line survived
    assert any(w["config"].get("dimension") == "hire_date" for w in widgets)
    # the first section is the headline numbers
    assert out["proposals"][0]["section"] == "summary"


def test_a_flat_comparison_never_beats_a_real_one():
    out, _ = _run(size=12)
    widgets = [w for prop in out["proposals"] for w in prop["widgets"]]
    # flat results outside the fairness section, where they are the finding
    flat = [w for p in out["proposals"] if p["section"] != "equity" for w in p["widgets"]
            if w["evidence"] is not None and w["evidence"] < 0.1]
    assert len(flat) <= 1
    by_title = {w["title"]: w for w in widgets}
    assert "Pay by department" in by_title or "Avg pay by dept" in by_title


def test_without_a_model_the_statistics_ideas_still_make_a_selection():
    out, _ = _run(size=12, client=None)
    assert out["panel"]["from_model"] == 0 and out["panel"]["selected"] >= 6


def test_size_is_respected_and_types_are_spread():
    out, _ = _run(size=24)
    # `size` is the charts chosen; the page controls and the detail page's
    # rows come on top of them.
    widgets = [w for prop in out["proposals"] for w in prop["widgets"]
               if w["widget_type"] != "slicer" and prop["section"] not in ("detail", "drill")]
    assert len(widgets) <= 24
    from collections import Counter
    from app.services.analyst_panel import _family
    fam = Counter(_family(w["widget_type"], w["config"]) for w in widgets)
    assert max(fam.values()) <= max(2, 24 // 8)


def test_evidence_reads_the_result():
    df = _hr()
    strong = get_widget_data_from_df(df, {"dimension": "dept_name", "measure": "salary", "aggregation": "avg"}, "bar")
    flat = get_widget_data_from_df(df, {"dimension": "gender", "measure": "salary", "aggregation": "avg"}, "bar")
    assert evidence("bar", {"dimension": "dept_name"}, strong) > 0.2 > evidence("bar", {"dimension": "gender"}, flat)


def test_select_merges_identical_questions():
    w = {"widget_type": "bar", "config": {"dimension": "a", "measure": "b", "aggregation": "avg"},
         "value": 3, "evidence": 0.5, "section": "measures"}
    chosen, stats = select([w, {**w, "value": 5}], 10, ["summary", "measures"])
    assert len(chosen) == 1 and chosen[0]["value"] == 5 and stats["duplicates_merged"] == 1


def test_two_models_of_the_same_outcome_are_one_question():
    a = {"widget_type": "model_linear", "config": {"measure": "salary", "predictors": ["dept_name", "title"]},
         "value": 5, "evidence": 0.5, "section": "measures"}
    b = {**a, "config": {"measure": "salary", "predictors": ["gender", "dept_name"]}, "value": 4}
    chosen, stats = select([a, b], 10, ["summary", "measures"])
    assert len(chosen) == 1 and stats["duplicates_merged"] == 1


def test_a_year_label_reads_as_a_year():
    from app.services.readback import takeaway
    r = {"type": "series", "rows": [{"name": 1985.0, "value": 10}, {"name": 1990.0, "value": 30},
                                     {"name": 2000.0, "value": 2}]}
    s = takeaway("line", {"dimension": "hire_date", "dimension_granularity": "year",
                          "measure": "emp_no", "aggregation": "countd"}, r)
    assert s and "1985.0" not in s and "1985" in s


def test_the_same_breakdown_drawn_two_ways_is_one_question():
    cfg = {"dimension": "dept_name", "measure": "emp_no", "aggregation": "countd"}
    a = {"widget_type": "treemap", "config": cfg, "value": 4, "evidence": 0.5, "section": "composition"}
    b = {"widget_type": "bar", "config": dict(cfg), "value": 5, "evidence": 0.5, "section": "composition"}
    chosen, stats = select([a, b], 10, ["summary", "composition"])
    assert len(chosen) == 1 and chosen[0]["widget_type"] == "bar"


def test_raw_dates_read_as_a_time_line_and_a_date_axis_gets_a_grain():
    from app.services.readback import takeaway
    r = {"type": "dual_series", "rows": [{"name": "1985-01-20T00:00:00", "value": 100, "value2": 5},
                                          {"name": "1985-02-01T00:00:00", "value": 40, "value2": 6}]}
    s = takeaway("dual_axis_time_series", {"start": "hire_date", "measure": "emp_no"}, r) or ""
    assert "leads" not in s and "T00:00" not in s
    from app.services.dataset_profile import build_profile
    from app.services.suggest_dataset_dashboard import polish_widget
    df = _hr()
    p = build_profile(df, detect_types(df), {})
    w = polish_widget({"widget_type": "dual_axis_time_series",
                       "config": {"start": "hire_date", "measure": "emp_no", "measure2": "salary"}}, p)
    assert w["config"].get("dimension_granularity")


def test_a_section_is_laid_out_as_a_tidy_page():
    from app.services.analyst_panel import layout_section
    ws = [{"widget_type": t, "config": {}} for t in ("line", "kpi", "bar", "model_rules", "box_plot", "kpi")]
    placed = layout_section(ws, "time")
    types = [w["widget_type"] for w, _ in placed]
    assert types[:2] == ["kpi", "kpi"]                         # headline numbers first
    grid = [slot for _, slot in placed]
    assert grid[0] == {"x": 0, "y": 0, "w": 6, "h": 2} and grid[1]["x"] == 6
    line = next(s for w, s in placed if w["widget_type"] == "line")
    assert line["w"] == 12                                     # the lead trend gets the width
    rows: dict = {}
    for _, s in placed:
        rows.setdefault(s["y"], []).append(s)
    for row in rows.values():                                  # every row reaches the edge
        assert sum(s["w"] for s in row) == 12 and len({s["h"] for s in row}) == 1
    cells = set()
    for _, s in placed:                                        # and nothing overlaps
        for x in range(s["x"], s["x"] + s["w"]):
            for y in range(s["y"], s["y"] + s["h"]):
                assert (x, y) not in cells
                cells.add((x, y))


def test_a_title_the_chart_does_not_keep_is_refused():
    from app.services.analyst_panel import broken_promise
    df = _hr()
    profile = build_profile(df, detect_types(df), {})
    m = {"source": "model"}
    assert "dept_filter" in broken_promise({**m, "title": "Salary in Sales", "widget_type": "histogram",
                                            "config": {"measure": "salary", "dept_filter": "Sales"}}, profile)
    assert "names Sales" in broken_promise({**m, "title": "Salary distribution in Sales", "widget_type": "histogram",
                                            "config": {"measure": "salary"}}, profile)
    assert "names gender" in broken_promise({**m, "title": "Salary by title vs gender", "widget_type": "box_plot",
                                             "config": {"dimension": "title", "measure": "salary"}}, profile)
    assert "same measure" in broken_promise({**m, "title": "Pay vs pay", "widget_type": "dual_axis_time_series",
                                             "config": {"start": "hire_date", "measure": "salary", "aggregation": "avg",
                                                        "measure2": "salary", "aggregation2": "avg"}}, profile)
    ok = [{"title": "Salary in Sales", "widget_type": "histogram",
           "config": {"measure": "salary", "filters": [{"column": "dept_name", "op": "eq", "value": "Sales"}]}},
          {"title": "Sales pays most", "widget_type": "bar",
           "config": {"dimension": "dept_name", "measure": "salary", "aggregation": "avg"}},
          {"title": "Average salary by gender", "widget_type": "bar",
           "config": {"dimension": "gender", "measure": "salary", "aggregation": "avg"}}]
    for w in ok:
        assert broken_promise({**m, **w}, profile) is None, w["title"]


def test_the_fairness_section_keeps_its_flat_findings():
    out, _ = _run(size=24)
    sec = next((p for p in out["proposals"] if p["section"] == "equity"), None)
    assert sec and any(w["title"] == "Average salary by department and gender" for w in sec["widgets"])
    titles = [w["title"] for p in out["proposals"] for w in p["widgets"]]
    assert "Salary distribution in Sales" not in titles and "Salary distribution in Sales" in out["reason"]


def test_a_series_under_another_name_becomes_the_split_or_is_dropped():
    from app.services.analyst_panel import broken_promise
    from app.services.suggest_dataset_dashboard import resolve_time_words
    df = _hr()
    profile = build_profile(df, detect_types(df), {})
    w = resolve_time_words({"widget_type": "line", "title": "Hires per year by title", "source": "model",
                            "config": {"dimension": "hire_date", "series": "title", "measure": "emp_no",
                                       "aggregation": "countd"}}, profile)
    assert w["config"].get("dimension2") == "title" and "series" not in w["config"]
    assert broken_promise(w, profile) is None
    h = resolve_time_words({"widget_type": "histogram", "title": "Salary by gender", "source": "model",
                            "config": {"measure": "salary", "color": "gender"}}, profile)
    assert "color" not in h["config"] and "names gender" in broken_promise(h, profile)


def test_a_missing_aggregation_is_read_from_the_title():
    from app.services.analyst_panel import _aggregation_from_title
    w = _aggregation_from_title({"widget_type": "bar", "title": "Average salary by gender",
                                 "config": {"dimension": "gender", "measure": "salary"}})
    assert w["config"]["aggregation"] == "avg"
    # no word in the title: how the column itself rolls up, never a blind sum
    plain = {"widget_type": "bar", "title": "Salary by gender", "config": {"dimension": "gender", "measure": "salary"}}
    assert _aggregation_from_title(plain)["config"]["aggregation"] == "avg"
    rev = {"widget_type": "bar", "title": "Revenue by region", "config": {"dimension": "region", "measure": "revenue"}}
    assert _aggregation_from_title(rev)["config"]["aggregation"] == "sum"
    told_meta = _aggregation_from_title(rev, {"revenue": {"aggregation": "avg"}})
    assert told_meta["config"]["aggregation"] == "avg"
    told = {"widget_type": "bar", "title": "Average salary", "config": {"measure": "salary", "aggregation": "median"}}
    assert _aggregation_from_title(told) is told


def test_a_headline_never_sums_an_identifier_or_mixes_it_into_a_card():
    from app.services.analyst_panel import broken_promise
    df = _hr()
    profile = build_profile(df, detect_types(df), {})
    s = {"source": "statistics", "title": "Workforce snapshot"}
    assert "identifier" in broken_promise({**s, "widget_type": "card",
                                           "config": {"measures": ["emp_no", "salary"]}}, profile)
    assert "two" in broken_promise({**s, "widget_type": "card",
                                    "config": {"measures": ["emp_no", "salary"], "aggregation": "countd"}}, profile)
    assert broken_promise({**s, "widget_type": "kpi", "config": {"measure": "emp_no", "aggregation": "countd"}},
                          profile) is None


def test_a_bubble_without_an_aggregation_averages():
    from app.services.analyst_panel import _aggregation_from_title
    w = _aggregation_from_title({"widget_type": "bubble", "title": "Dept profile: pay, tenure, headcount",
                                 "config": {"dimension": "dept_name", "measure": "salary", "measure2": "hire_date",
                                            "size": "emp_no", "size_aggregation": "countd"}})
    assert w["config"]["aggregation"] == "avg"


def test_a_headline_titled_by_a_split_it_cannot_draw_is_refused():
    from app.services.analyst_panel import broken_promise
    df = _hr()
    profile = build_profile(df, detect_types(df), {})
    w = {"source": "model", "title": "Headcount by gender", "widget_type": "card",
         "config": {"measures": ["emp_no"], "aggregation": "countd", "dimension": "gender"}}
    assert "names gender" in broken_promise(w, profile)
    assert "names gender" in broken_promise({**w, "widget_type": "kpi",
                                             "config": {"measure": "emp_no", "aggregation": "countd",
                                                        "dimension": "gender"}}, profile)


def test_one_headline_per_measure_and_no_impossible_percentiles():
    from app.services.analyst_panel import broken_promise
    k = {"widget_type": "kpi", "config": {"measure": "emp_no", "aggregation": "countd"}, "value": 5,
         "evidence": 0.6, "section": "summary"}
    f = {**k, "config": {**k["config"], "filters": [{"column": "gender", "op": "eq", "value": "F"}]}}
    chosen, _ = select([k, f], 12, ["summary"])
    assert len(chosen) == 1
    df = _hr()
    profile = build_profile(df, detect_types(df), {})
    m = {"source": "model", "title": "Salary percentiles by department"}
    assert "percentile" in broken_promise({**m, "widget_type": "dot_plot",
                                           "config": {"dimension": "dept_name", "measure": "salary"}}, profile)
    assert broken_promise({**m, "widget_type": "box_plot",
                           "config": {"dimension": "dept_name", "measure": "salary"}}, profile) is None


def test_a_mix_drawn_as_one_slice_becomes_the_mix():
    from app.services.analyst_panel import _mix_from_filter
    w = {"widget_type": "bar", "title": "Gender Mix by Department",
         "config": {"dimension": "dept_name", "measure": "emp_no", "aggregation": "countd",
                    "filters": [{"column": "gender", "op": "eq", "value": "F"}]}}
    out = _mix_from_filter(w)["config"]
    assert out["dimension2"] == "gender" and out["bar_mode"] == "stacked100" and "filters" not in out
    plain = {**w, "title": "Women by department"}
    assert _mix_from_filter(plain) is plain                    # a filtered count that says so stays


def test_a_title_does_not_claim_when_a_value_was_measured():
    from app.services.analyst_panel import _honest_title
    df = _hr()
    profile = build_profile(df, detect_types(df), {})
    w = {"title": "Average Starting Salary Trend (1985-2000)", "widget_type": "line", "config": {}}
    assert _honest_title(w, profile)["title"] == "Average Salary Trend (1985-2000)"
    same = {"title": "Average salary by hire year", "widget_type": "line", "config": {}}
    assert _honest_title(same, profile) is same


def test_facet_by_on_a_plain_chart_becomes_its_split():
    from app.services.suggest_dataset_dashboard import resolve_time_words
    df = _hr()
    profile = build_profile(df, detect_types(df), {})
    w = resolve_time_words({"widget_type": "line", "title": "Department mix stability", "config": {
        "dimension": "hire_date", "dimension_granularity": "year", "facet_by": "dept_name"}}, profile)
    assert w["config"]["dimension2"] == "dept_name" and "facet_by" not in w["config"]
    sm = resolve_time_words({"widget_type": "small_multiples", "config": {
        "dimension": "hire_date", "facet_by": "dept_name", "measure": "salary"}}, profile)
    assert sm["config"]["facet_by"] == "dept_name"


def _cdr(n=3000, seed=1):
    rng = np.random.default_rng(seed)
    service = rng.choice(["Voice", "SMS", "GPRS"], n, p=[.5, .2, .3])
    volume = np.where(service == "GPRS", rng.integers(100_000, 2_000_000, n),
                      np.where(service == "SMS", 1, rng.integers(10, 600, n)))
    return pd.DataFrame({"SERVICE": service, "SWITCH": rng.choice(["A", "B", "C"], n),
                         "ROUNDED_VOLUME": volume, "RATED_AMOUNT": rng.uniform(0, 5, n).round(2),
                         "FULL_DATE": pd.Timestamp("2024-01-01") + pd.to_timedelta(rng.integers(0, 365, n), "D")})


def test_a_measure_in_different_units_per_group_is_never_added_across_them():
    from app.services.analyst_panel import mixes_units
    df = _cdr()
    facts = build_facts(df, effective_roles(detect_types(df), {}))
    mixed = facts["mixed_units"]
    assert mixed["ROUNDED_VOLUME"]["by"] == "SERVICE" and "different units" in facts["text"]
    assert "RATED_AMOUNT" not in mixed
    total = {"title": "Total volume", "widget_type": "kpi", "config": {"measure": "ROUNDED_VOLUME", "aggregation": "sum"}}
    assert "different units" in mixes_units(total, mixed)
    by_switch = {"title": "Volume by switch", "widget_type": "bar",
                 "config": {"dimension": "SWITCH", "measure": "ROUNDED_VOLUME", "aggregation": "sum"}}
    assert mixes_units(by_switch, mixed)
    split = {**by_switch, "config": {**by_switch["config"], "dimension2": "SERVICE"}}
    assert mixes_units(split, mixed)                           # bytes beside seconds on one axis
    panels = {"title": "Volume per service", "widget_type": "small_multiples",
              "config": {"facet_by": "SERVICE", "dimension": "SWITCH", "measure": "ROUNDED_VOLUME",
                         "aggregation": "sum"}}
    weight = {"title": "Where volume happens", "widget_type": "map_density",
              "config": {"lat": "LAT", "lon": "LON", "weight": "ROUNDED_VOLUME"}}
    assert mixes_units(panels, mixed) and mixes_units(weight, mixed)   # panels share one scale
    one = {**by_switch, "config": {**by_switch["config"],
                                   "filters": [{"column": "SERVICE", "op": "eq", "value": "Voice"}]}}
    calls = {**by_switch, "config": {**by_switch["config"], "aggregation": "count"}}
    assert mixes_units(one, mixed) is None and mixes_units(calls, mixed) is None


def test_the_suggestions_pane_does_not_total_mixed_units_either():
    from app.services.insights import suggest_widgets_from_findings
    df = _cdr()
    tm = detect_types(df)
    out = suggest_widgets_from_findings(generate_insights(df, tm, {})["findings"], effective_roles(tm, {}),
                                        "network ops", frame=df)
    for x in out:
        c = x["config"]
        if "ROUNDED_VOLUME" in (c.get("measure"), c.get("measure2")) and \
                str(c.get("aggregation") or "sum") not in ("count", "countd"):
            assert "SERVICE" in (c.get("dimension"), c.get("dimension2")) or c.get("filters"), x["title"]


def test_a_mixed_unit_total_is_narrowed_to_one_unit_not_lost():
    from app.services.analyst_panel import mixes_units, one_unit
    df = _cdr()
    mixed = build_facts(df, effective_roles(detect_types(df), {}))["mixed_units"]
    w = {"title": "Monthly volume", "widget_type": "line",
         "config": {"dimension": "FULL_DATE", "dimension_granularity": "month",
                    "measure": "ROUNDED_VOLUME", "aggregation": "sum"}}
    fixed = one_unit(w, mixed)
    assert fixed["title"] == "Monthly volume (Voice)"
    assert {"column": "SERVICE", "op": "eq", "value": "Voice"} in fixed["config"]["filters"]
    assert mixes_units(fixed, mixed) is None
    by_service = {**w, "config": {**w["config"], "dimension": "SERVICE"}}
    assert one_unit(by_service, mixed) is by_service          # the units ARE the axis: refused


def test_one_broken_idea_or_shaper_never_fails_the_run(monkeypatch):
    import app.services.analyst_panel as ap
    df = _hr()
    tm = detect_types(df)
    roles = effective_roles(tm, {})
    profile = build_profile(df, tm, {})
    facts = build_facts(df, roles)

    class Odd:
        async def complete_json(self, messages, schema, **kw):
            return {"widgets": [
                "not a widget", {"widget_type": None},
                {"question": "q", "widget_type": "bar", "title": "Weird value", "value": "high",
                 "config": {"dimension": "dept_name", "measure": "salary", "aggregation": "avg"}},
                {"question": "q", "widget_type": "bar", "title": "Odd filters", "value": 4,
                 "config": {"dimension": "dept_name", "measure": "salary", "filters": {"column": "x"}}},
                {"question": "q", "widget_type": "line", "title": "Boom", "value": 5,
                 "config": {"dimension": "hire_date", "measure": "salary", "aggregation": "avg"}},
            ]}

    async def probe(wt, cfg):
        if wt == "line":
            raise RuntimeError("shaper exploded")
        return get_widget_data_from_df(df, cfg, wt)

    out = asyncio.run(run_panel(df=df, profile=profile, roles=roles, column_meta={}, ineligible=set(),
                                findings=generate_insights(df, tm, {})["findings"], facts=facts,
                                goal=None, size=12, probe=probe, client=Odd()))
    assert out["panel"]["selected"] > 0
    titles = [w["title"] for p in out["proposals"] for w in p["widgets"]]
    assert not any(r["title"] == "Weird value" for r in out["refused"])   # "high" read as 5, not refused
    assert "Boom" not in titles
    assert any("shaper exploded" in (r["why"] or "") for r in out["refused"])


def test_rates_are_averaged_and_named_once():
    from app.services.analyst_panel import _no_sum_of_rates
    from app.services.readback import takeaway
    w = {"widget_type": "line", "title": "Avg freight", "config": {"dimension": "day", "measure": "avg_freight_cost",
                                                                  "aggregation": "sum"}}
    assert _no_sum_of_rates(w)["config"]["aggregation"] == "avg"
    rate = {"widget_type": "bar", "config": {"dimension": "d", "measure": "cancellation_rate_pct", "aggregation": "sum"}}
    assert _no_sum_of_rates(rate)["config"]["aggregation"] == "avg"
    total = {"widget_type": "bar", "config": {"dimension": "d", "measure": "total_orders", "aggregation": "sum"}}
    assert _no_sum_of_rates(total) is total
    s = takeaway("kpi", {"measure": "total_orders", "aggregation": "sum"},
                 {"type": "scalar", "rows": [{"value": 98666}]})
    assert str(s) == "Total orders: 98,666."


def test_daily_table_quirks():
    from app.services.analyst_panel import _honest_title, select
    from app.services.readback import _what
    assert str(_what({"measure": "total_orders", "aggregation": "avg"})) == "average total orders"
    assert str(_what({"measure": "total_orders", "aggregation": "sum"})) == "total orders"
    df = _hr()
    profile = build_profile(df, detect_types(df), {})
    assert _honest_title({"title": "Total total orders"}, profile)["title"] == "Total orders"
    from app.services.suggest_dataset_dashboard import resolve_time_words
    w = resolve_time_words({"widget_type": "numeric_series", "config": {"measure": "hire_date", "measure2": "salary"}},
                           profile)
    assert w["widget_type"] == "line" and w["config"] == {"dimension": "hire_date", "measure": "salary"}
    m = {"widget_type": "correlation_matrix", "value": 4, "evidence": 0.5, "section": "relationships"}
    chosen, stats = select([{**m, "config": {"measures": ["a", "b"]}}, {**m, "config": {"measures": ["a", "b", "c"]}}],
                           12, ["relationships"])
    assert len(chosen) == 1


def test_a_numeric_series_over_a_date_is_a_line():
    from app.services.suggest_dataset_dashboard import resolve_time_words, validate_widget
    df = _hr()
    profile = build_profile(df, detect_types(df), {})
    w = resolve_time_words({"widget_type": "numeric_series", "title": "Pay over time", "config": {
        "dimension": "hire_date", "dimension_granularity": "month", "measure": "salary"}}, profile)
    assert w["widget_type"] == "line" and validate_widget(w, profile)[0]


def test_a_daily_table_of_numbers_gets_its_trends():
    from app.services.suggest_dataset_dashboard import resolve_time_words, usable_widgets, validate_widget
    rng = np.random.default_rng(3)
    days = pd.date_range("2024-01-01", periods=200, freq="D")
    df = pd.DataFrame({"day_date": days, "total_orders": rng.integers(80, 200, 200),
                       "cancellation_rate_pct": rng.uniform(0, 8, 200).round(2)})
    profile = build_profile(df, detect_types(df), {})
    assert "line" in usable_widgets(profile)
    g = resolve_time_words({"widget_type": "gauge", "title": "Cancellations", "config": {
        "measure": "cancellation_rate_pct", "aggregation": "avg", "target": 5}}, profile)
    assert g["config"]["target_value"] == 5 and "target" not in g["config"]
    assert validate_widget(g, profile)[0]
    w = resolve_time_words({"widget_type": "numeric_series", "title": "Rate over time", "config": {
        "measure": "cancellation_rate_pct", "measure2": "day_date"}}, profile)
    assert w["widget_type"] == "line" and w["config"]["dimension"] == "day_date"
    t = resolve_time_words({"widget_type": "table", "title": "Days", "config": {
        "dimension": "day_date", "measures": ["total_orders"], "sort_order": "desc"}}, profile)
    assert t["config"]["sort"] == "desc" and "sort_order" not in t["config"]


def test_what_was_left_out_is_counted_by_kind():
    from app.services.analyst_panel import refusal_code
    assert refusal_code("X: ROUNDED_VOLUME is recorded in different units by SERVICE") == "units"
    assert refusal_code("X: the title names gender, which the chart does not use") == "promise"
    assert refusal_code("X: there is no column called region") == "invalid"
    assert refusal_code("X: returned nothing to draw") == "empty"
    out, _ = _run(size=12)
    p = out["panel"]
    assert p["left_out"].get("invalid", 0) >= 1                 # the invented "region"
    assert sum(p["left_out"].values()) == p["rejected"]
    assert all("code" in r for r in out["refused"])
    assert p["not_picked"] >= 0
