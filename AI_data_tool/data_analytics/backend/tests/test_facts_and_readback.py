"""Step 1 of the analyst-panel pipeline (2026-10-02): suggestions are designed
from measured facts and say what they actually drew."""
import asyncio

import numpy as np
import pandas as pd

from app.services.analytics import detect_types
from app.services.fact_sheet import build_facts
from app.services.insights import effective_roles, generate_insights, suggest_widgets_from_findings
from app.services.readback import takeaway
from app.services.widget_data import get_widget_data_from_df as draw


def _hr(n=3000, seed=0):
    rng = np.random.default_rng(seed)
    dept = rng.choice(["Sales", "Development", "Finance", "Marketing"], n)
    title = np.where(np.isin(dept, ["Sales", "Finance"]), rng.choice(["Staff", "Senior Staff"], n, p=[.3, .7]),
                     rng.choice(["Engineer", "Senior Engineer"], n))
    years = rng.uniform(0, 15, n)
    return pd.DataFrame({
        "emp_no": np.arange(10001, 10001 + n), "dept_name": dept, "title": title,
        "gender": rng.choice(["M", "F"], n, p=[.6, .4]),
        "salary": 50000 + np.where(dept == "Sales", 20000, 0) + years * 1000 + rng.normal(0, 4000, n),
        "hire_date": pd.Timestamp("2000-01-01") - pd.to_timedelta(years * 365.25, "D"),
    })


def _roles(df):
    return effective_roles(detect_types(df), {})


# ── fact sheet ───────────────────────────────────────────────────────────────

def test_facts_state_the_real_differences_and_the_flat_ones():
    df = _hr()
    f = build_facts(df, _roles(df))
    kinds = {x["kind"] for x in f["facts"]}
    assert {"overview", "measure", "groups", "flat", "trend", "link", "independent"} <= kinds
    text = f["text"]
    assert "highest Sales" in text                       # salary by department
    assert "same for every gender" in text               # gender does not move pay
    assert "gender and" in text and "independent" in text


def test_facts_never_mention_a_blocked_column():
    df = _hr()
    f = build_facts(df, _roles(df), ineligible={"gender"})
    assert "gender" not in f["text"]


def test_the_designer_prompt_carries_the_facts_and_the_flat_rule():
    from app.services.dataset_profile import build_profile
    from app.services.suggest_dataset_dashboard import build_messages
    df = _hr()
    profile = build_profile(df, detect_types(df), {})
    facts = build_facts(df, _roles(df))["text"]
    msg = build_messages(profile, "I run HR", 2, None, facts)[1]["content"]
    assert "MEASURED FACTS" in msg and "highest Sales" in msg
    assert "never promise a gap the facts rule out" in msg
    assert "MEASURED FACTS" not in build_messages(profile, "I run HR", 2)[1]["content"]


# ── read-back ────────────────────────────────────────────────────────────────

def _say(df, wt, cfg):
    return takeaway(wt, cfg, draw(df, cfg, wt))


def test_a_flat_gap_is_called_flat():
    df = _hr()
    s = _say(df, "bar", {"dimension": "dept_name", "dimension2": "gender", "measure": "salary",
                         "aggregation": "avg", "bar_mode": "clustered"})
    assert s.startswith("No real difference between F and M") or "differ by under 2%" in s


def test_a_mix_is_judged_by_the_series_that_moves_most():
    df = _hr()
    s = _say(df, "bar", {"dimension": "dept_name", "dimension2": "title", "measure": "emp_no",
                         "aggregation": "countd", "bar_mode": "stacked100"})
    assert "mix differs by dept name" in s and "0% of" in s
    s = _say(df, "bar", {"dimension": "dept_name", "dimension2": "gender", "measure": "emp_no",
                         "aggregation": "countd", "bar_mode": "stacked100"})
    assert "mix is about the same in every dept name" in s


def test_series_kpi_and_time_sentences_carry_the_drawn_numbers():
    df = _hr()
    s = _say(df, "bar", {"dimension": "dept_name", "measure": "emp_no", "aggregation": "countd"})
    top = df.dept_name.value_counts()
    assert f"{top.index[0]} leads with {top.iloc[0]:,}" in s
    assert _say(df, "kpi", {"measure": "emp_no", "aggregation": "countd"}) == f"Headcount: {len(df):,}."
    s = _say(df, "line", {"dimension": "hire_date", "dimension_granularity": "year",
                          "measure": "salary", "aggregation": "avg"})
    assert s.startswith("Average salary falls from")
    assert _say(df, "donut", {"dimension": "gender", "measure": "emp_no", "aggregation": "countd"}).startswith("M 6")


def test_models_say_when_they_are_a_coin_toss():
    df = _hr()
    s = _say(df, "model_logistic", {"response": "gender", "event_value": "F",
                                    "predictors": ["salary", "title"]})
    assert "coin toss" in s


def test_an_unknown_or_empty_result_gives_no_sentence():
    assert takeaway("bar", {}, {"type": "empty", "rows": []}) is None
    assert takeaway("bar", {}, None) is None
    assert takeaway("whatever", {}, {"type": "novel", "rows": [{"x": 1}]}) is None


def test_panel_suggestions_carry_takeaways():
    df = _hr()
    res = generate_insights(df, detect_types(df), {})
    out = suggest_widgets_from_findings(res["findings"], _roles(df), "HR", frame=df)
    said = [x for x in out if x.get("takeaway")]
    assert len(said) >= len(out) - 1                     # all but the rules widget


def test_dashboard_proposals_carry_takeaways_from_what_drew(monkeypatch):
    """The router keys each probe's result by (type, config) and reads it back."""
    from app.routers.datasets import _drawn_key
    df = _hr()
    cfg = {"dimension": "dept_name", "measure": "salary", "aggregation": "avg"}
    drawn = {_drawn_key("bar", cfg): draw(df, cfg, "bar")}
    s = takeaway("bar", cfg, drawn[_drawn_key("bar", dict(reversed(list(cfg.items()))))])
    assert s and "Sales is highest" in s
    asyncio.get_event_loop_policy()                      # (no event loop needed)


def test_an_invented_year_field_becomes_the_date_column_by_year():
    from app.services.dataset_profile import build_profile
    from app.services.suggest_dataset_dashboard import resolve_time_words, validate_widget
    df = _hr()
    profile = build_profile(df, detect_types(df), {})
    for name in ("year", "hire_year", "Year of hire"):
        w = resolve_time_words({"widget_type": "bar", "title": "Hires",
                                "config": {"dimension": name, "measure": "emp_no", "aggregation": "countd"}}, profile)
        assert w["config"]["dimension"] == "hire_date" and w["config"]["dimension_granularity"] == "year", name
        assert validate_widget(w, profile)[0]
    real = {"widget_type": "bar", "config": {"dimension": "dept_name"}}
    assert resolve_time_words(real, profile) is real


def test_an_average_of_a_date_is_years_since_it():
    df = _hr()
    r = draw(df, {"measure": "hire_date", "aggregation": "avg"}, "kpi")
    years = (df.hire_date.max() - df.hire_date).dt.days.mean() / 365.25
    assert abs(r["rows"][0]["value"] - years) < 1e-6 and r["derived"] == {"hire_date": "years_before_latest"}
    assert takeaway("kpi", {"measure": "hire_date", "aggregation": "avg"}, r).startswith("Average years since hire date:")


def test_aliases_and_time_words_in_any_slot():
    from app.services.dataset_profile import build_profile
    from app.services.suggest_dataset_dashboard import resolve_time_words, validate_widget
    df = _hr()
    profile = build_profile(df, detect_types(df), {})
    w = resolve_time_words({"widget_type": "stacked_bar", "title": "Mix",
                            "config": {"category": "year", "dimension2": "dept_name",
                                       "measure": "emp_no", "aggregation": "countd"}}, profile)
    assert w["widget_type"] == "bar" and w["config"]["bar_mode"] == "stacked"
    assert w["config"]["category"] == "hire_date" and w["config"]["dimension_granularity"] == "year"


def test_a_grain_under_its_own_name_becomes_the_granularity():
    from app.services.dataset_profile import build_profile
    from app.services.suggest_dataset_dashboard import resolve_time_words
    df = _hr()
    profile = build_profile(df, detect_types(df), {})
    w = resolve_time_words({"widget_type": "line", "config": {"dimension": "hire_date", "granularity": "year",
                                                              "measure": "salary"}}, profile)
    assert "granularity" not in w["config"] and w["config"]["dimension_granularity"] == "year"


def test_a_field_written_as_an_object_is_split_into_column_and_setting():
    from app.services.dataset_profile import build_profile
    from app.services.suggest_dataset_dashboard import resolve_time_words, validate_widget
    df = _hr()
    profile = build_profile(df, detect_types(df), {})
    w = resolve_time_words({"widget_type": "bar", "title": "Hires by dept over time",
                            "config": {"dimension": {"column": "hire_date", "dimension_granularity": "year"},
                                       "dimension2": "dept_name",
                                       "measure": {"column": "emp_no", "aggregation": "countd"}}}, profile)
    assert w["config"]["dimension"] == "hire_date" and w["config"]["dimension_granularity"] == "year"
    assert w["config"]["measure"] == "emp_no" and w["config"]["aggregation"] == "countd"
    assert validate_widget(w, profile)[0]
    w = resolve_time_words({"widget_type": "card", "config": {
        "measures": [{"column": "salary", "aggregation": "avg"}, {"column": "emp_no"}]}}, profile)
    assert w["config"]["measures"] == ["salary", "emp_no"]


def test_a_count_grid_is_read_for_the_link_not_the_biggest_cell():
    from app.services.analyst_panel import evidence
    df = _hr()
    flat = {"dimension": "dept_name", "dimension2": "gender", "measure": "emp_no", "aggregation": "countd"}
    r = draw(df, flat, "heatmap")
    assert takeaway("heatmap", flat, r).startswith("Gender does not depend on dept name")
    assert evidence("heatmap", flat, r) < 0.1
    linked = {**flat, "dimension2": "title"}
    r = draw(df, linked, "heatmap")
    assert "as common as the two would be by chance" in takeaway("heatmap", linked, r)
    assert evidence("heatmap", linked, r) > 0.5


def test_a_filter_under_a_singular_name_is_kept_as_a_filter():
    from app.services.dataset_profile import build_profile
    from app.services.suggest_dataset_dashboard import resolve_time_words, validate_widget
    df = _hr()
    profile = build_profile(df, detect_types(df), {})
    w = resolve_time_words({"widget_type": "bar", "title": "Sales: salary by gender", "config": {
        "dimension": "gender", "measure": "salary", "aggregation": "avg",
        "filter": {"field": "dept_name", "operator": "eq", "value": "Sales"}, "bin_count": 3}}, profile)
    assert w["config"]["filters"] == [{"column": "dept_name", "op": "eq", "value": "Sales"}]
    assert "filter" not in w["config"] and w["config"]["bins"] == 3
    assert validate_widget(w, profile)[0]


def test_stacking_written_as_flags_becomes_the_bar_mode():
    from app.services.dataset_profile import build_profile
    from app.services.suggest_dataset_dashboard import resolve_time_words
    df = _hr()
    profile = build_profile(df, detect_types(df), {})
    base = {"dimension": "dept_name", "dimension2": "gender", "measure": "emp_no", "aggregation": "countd"}
    w = resolve_time_words({"widget_type": "bar", "config": {**base, "stacked": True, "percent": True}}, profile)
    assert w["config"]["bar_mode"] == "stacked100" and "stacked" not in w["config"]
    w = resolve_time_words({"widget_type": "bar", "config": {**base, "stacked": True}}, profile)
    assert w["config"]["bar_mode"] == "stacked"


def test_a_bubble_is_offered_with_one_number_and_a_date():
    from app.services.dataset_profile import build_profile
    from app.services.suggest_dataset_dashboard import usable_widgets
    df = _hr()
    profile = build_profile(df, detect_types(df), {})
    assert "bubble" in usable_widgets(profile)
    assert "bubble" not in usable_widgets(build_profile(df.drop(columns=["hire_date"]),
                                                        detect_types(df.drop(columns=["hire_date"])), {}))


# ── the same sentence in the reader's language ───────────────────────────────

def _catalogue():
    import os
    import re
    path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "src", "i18n", "en.ts")
    if not os.path.exists(path):
        import pytest
        pytest.skip("frontend catalogue not present in this checkout")
    text = open(path, encoding="utf-8").read()
    return {k: v.replace("\\'", "'") for k, v in re.findall(r"^\s*'(rb\.[^']+)': '((?:[^'\\]|\\.)*)',$", text, re.M)}


def _render(cat, said):
    import re
    tpl = cat["rb." + said["key"]]
    vals = {k: (_render(cat, v) if isinstance(v, dict) else v) for k, v in said.get("vars", {}).items()}
    return re.sub(r"\{(\w+)\}", lambda m: vals[m.group(1)], tpl)


def test_every_takeaway_has_a_catalogue_sentence_that_reads_the_same():
    """The browser renders `rb.<key>` with the pieces; in English that must be
    the server's own sentence, or the two languages say different things."""
    from app.services.analyst_panel import evidence  # noqa: F401  (imports the models)
    from app.services.readback import as_i18n
    cat = _catalogue()
    df = _hr()
    cases = [
        ("kpi", {"measure": "emp_no", "aggregation": "countd"}),
        ("kpi", {"measure": "salary", "aggregation": "avg"}),
        ("kpi", {"measure": "hire_date", "aggregation": "avg"}),
        ("bar", {"dimension": "dept_name", "measure": "emp_no", "aggregation": "countd"}),
        ("bar", {"dimension": "dept_name", "measure": "salary", "aggregation": "avg"}),
        ("bar", {"dimension": "gender", "measure": "salary", "aggregation": "avg"}),
        ("donut", {"dimension": "gender", "measure": "emp_no", "aggregation": "countd"}),
        ("line", {"dimension": "hire_date", "dimension_granularity": "year", "measure": "salary", "aggregation": "avg"}),
        ("histogram", {"measure": "salary"}),
        ("box_plot", {"dimension": "dept_name", "measure": "salary"}),
        ("bar", {"dimension": "dept_name", "dimension2": "title", "measure": "emp_no", "aggregation": "countd",
                 "bar_mode": "stacked100"}),
        ("bar", {"dimension": "dept_name", "dimension2": "gender", "measure": "emp_no", "aggregation": "countd",
                 "bar_mode": "stacked100"}),
        ("bar", {"dimension": "dept_name", "dimension2": "gender", "measure": "salary", "aggregation": "avg",
                 "bar_mode": "clustered"}),
        ("heatmap", {"dimension": "dept_name", "dimension2": "gender", "measure": "emp_no", "aggregation": "countd"}),
        ("heatmap", {"dimension": "dept_name", "dimension2": "title", "measure": "emp_no", "aggregation": "countd"}),
        ("heatmap", {"dimension": "dept_name", "dimension2": "title", "measure": "salary", "aggregation": "avg"}),
        ("bubble", {"dimension": "dept_name", "measure": "hire_date", "measure2": "salary", "aggregation": "avg",
                    "size": "emp_no", "size_aggregation": "countd"}),
        ("model_linear", {"measure": "salary", "predictors": ["title", "dept_name", "hire_date"]}),
        ("model_logistic", {"response": "gender", "event_value": "F", "predictors": ["salary", "title"]}),
        ("model_rules", {}),
        ("model_tree", {"response": "title", "predictors": ["dept_name", "salary"]}),
        ("card", {"measures": ["salary", "emp_no"], "aggregation": "countd"}),
        ("numeric_series", {"measure": "salary", "measure2": "emp_no"}),
    ]
    seen = set()
    for wt, cfg in cases:
        said = takeaway(wt, cfg, draw(df, cfg, wt))
        assert said, (wt, cfg)
        i18n = as_i18n(said)
        seen.add(i18n["key"])
        rendered = _render(cat, i18n)
        assert rendered[:1].upper() + rendered[1:] == str(said), (wt, rendered, str(said))
    assert len(seen) >= 12


def test_the_arabic_catalogue_has_every_sentence():
    import os
    import re
    cat = _catalogue()
    ar = open(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "src", "i18n", "ar.ts"),
              encoding="utf-8").read()
    have = set(re.findall(r"^\s*'(rb\.[^']+)':", ar, re.M))
    assert set(cat) <= have
    from app.services import readback
    src = open(readback.__file__, encoding="utf-8").read()
    keys = (set(re.findall(r'_s\("([\w.]+)"', src)) | {f"time.{t}{p}" for t in ("rises", "falls") for p in ("", "Peak")}
            | {f"card{n}" for n in range(1, 5)})
    assert {"rb." + k for k in keys} <= set(cat), {"rb." + k for k in keys} - set(cat)


def test_a_copied_measure_is_not_a_finding():
    from app.services.insights import drop_duplicate_measures
    df = _hr()
    df["salary (copy)"] = df["salary"]
    df["salary_cents"] = df["salary"] * 100
    assert drop_duplicate_measures(df, ["salary", "salary (copy)", "salary_cents", "emp_no"]) == ["salary", "emp_no"]
    res = generate_insights(df, detect_types(df), {})
    assert not any("copy" in f["title"] or "cents" in f["title"] for f in res["findings"])
    facts = build_facts(df, _roles(df))["text"]
    assert "copy" not in facts


def test_axes_must_be_categories_and_grains_need_dates():
    from app.services.dataset_profile import build_profile
    from app.services.suggest_dataset_dashboard import polish_widget, resolve_time_words, validate_widget
    df = _hr()
    profile = build_profile(df, detect_types(df), {})
    ok, why = validate_widget({"widget_type": "heatmap", "title": "Pay by status", "config": {
        "dimension": "dept_name", "dimension2": "salary", "measure": "emp_no", "aggregation": "countd"}}, profile)
    assert not ok and "continuous number" in why
    assert validate_widget({"widget_type": "histogram", "title": "Pay", "config": {"measure": "salary"}}, profile)[0]
    p = polish_widget({"widget_type": "line", "config": {"dimension": "salary", "dimension_granularity": "quarter",
                                                         "measure": "emp_no", "aggregation": "countd"}}, profile)
    assert "dimension_granularity" not in p["config"]
    w = resolve_time_words({"widget_type": "bar", "config": {"dimension": "dept_name", "measure": "salary",
                                                             "limit_dimension": 10}}, profile)
    assert w["config"]["limit"] == 10 and "limit_dimension" not in w["config"]
    t = resolve_time_words({"widget_type": "model_tree", "config": {"response": "title", "max_depth": 3}}, profile)
    assert t["config"].get("max_depth") == 3 and "limit" not in t["config"]


def test_a_top_list_of_an_identifier_is_allowed():
    from app.services.dataset_profile import build_profile
    from app.services.suggest_dataset_dashboard import validate_widget
    df = _hr()
    df["seller_id"] = [f"s{i % 900:04d}x{i % 7}" for i in range(len(df))]
    profile = build_profile(df, detect_types(df), {})
    base = {"widget_type": "bar", "title": "Top sellers", "config": {
        "dimension": "seller_id", "measure": "salary", "aggregation": "sum"}}
    ok_top = validate_widget({**base, "config": {**base["config"], "limit": 10}}, profile)
    assert ok_top[0], ok_top[1]
    assert not validate_widget(base, profile)[0]


def test_the_same_measure_under_two_filters_becomes_a_split():
    from app.services.dataset_profile import build_profile
    from app.services.suggest_dataset_dashboard import resolve_time_words, validate_widget
    df = _hr()
    profile = build_profile(df, detect_types(df), {})
    w = resolve_time_words({"widget_type": "comparative_time_series", "title": "M vs F hires", "config": {
        "start": "hire_date", "dimension_granularity": "year", "measure": "emp_no", "measure2": "emp_no",
        "aggregation": "countd", "aggregation2": "countd",
        "filters": [{"column": "gender", "op": "eq", "value": "M"}, {"column": "gender", "op": "eq", "value": "F"}]}},
        profile)
    assert w["widget_type"] == "line" and w["config"]["dimension"] == "hire_date"
    assert w["config"]["dimension2"] == "gender" and "filters" not in w["config"]
    assert validate_widget(w, profile)[0]
    b = resolve_time_words({"widget_type": "butterfly", "title": "OUT vs IN", "config": {
        "dimension": "dept_name", "measure": "countd", "measure2": "countd",
        "filters": [{"column": "gender", "op": "eq", "value": "M"}, {"column": "gender", "op": "eq", "value": "F"}]}},
        profile)
    assert b["widget_type"] == "bar" and b["config"]["aggregation"] == "countd" and b["config"]["dimension2"] == "gender"
    assert "measure" not in b["config"]


def test_a_list_of_aggregations_becomes_the_chart_aggregation():
    from app.services.dataset_profile import build_profile
    from app.services.suggest_dataset_dashboard import resolve_time_words, validate_widget
    df = _hr()
    profile = build_profile(df, detect_types(df), {})
    w = resolve_time_words({"widget_type": "table", "title": "Pay", "config": {
        "dimension": "dept_name", "measures": ["salary", "emp_no"], "aggregations": ["avg", "countd"]}}, profile)
    assert w["config"]["aggregation"] == "avg" and "aggregations" not in w["config"]
    assert validate_widget(w, profile)[0]


def test_start_is_the_dimension_for_charts_that_do_not_read_start():
    from app.services.dataset_profile import build_profile
    from app.services.suggest_dataset_dashboard import resolve_time_words
    df = _hr()
    profile = build_profile(df, detect_types(df), {})
    f = resolve_time_words({"widget_type": "forecast", "config": {"start": "hire_date", "measure": "salary"}}, profile)
    assert f["config"].get("dimension") == "hire_date" and "start" not in f["config"]
    d = resolve_time_words({"widget_type": "dual_axis_time_series",
                            "config": {"start": "hire_date", "measure": "salary", "measure2": "emp_no"}}, profile)
    assert d["config"].get("start") == "hire_date"


def test_the_quick_designer_gets_the_panels_checks_too():
    from app.services.dataset_profile import build_profile
    from app.services.suggest_dataset_dashboard import suggest_for_dataset
    df = _hr()
    profile = build_profile(df, detect_types(df), {})

    class Designer:
        async def complete_json(self, messages, schema, **kw):
            return {"proposals": [{"title": "Pay", "rationale": "r", "widgets": [
                {"widget_type": "bar", "title": "Average salary by gender",
                 "config": {"dimension": "gender", "measure": "salary"}},
                {"widget_type": "histogram", "title": "Salary distribution in Sales",
                 "config": {"measure": "salary"}},
            ]}]}

    async def probe(wt, cfg):
        return draw(df, cfg, wt)

    proposals, reason = asyncio.run(suggest_for_dataset(profile, "I run HR", 1, client=Designer(), probe=probe))
    widgets = proposals[0]["widgets"]
    assert [w["title"] for w in widgets] == ["Average salary by gender"]
    assert widgets[0]["config"]["aggregation"] == "avg" and "source" not in widgets[0]
    assert "names Sales" in reason
