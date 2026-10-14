"""Suggestions in the shape the data asks for (HR re-test 2026-10-02): the panel
offered 4 widget types of 75. Each new kind must appear only when its shape is
really in the data, must draw, and no kind may crowd the list."""
import numpy as np
import pandas as pd

from app.services.analytics import detect_types
from app.services.insights import effective_roles, generate_insights, suggest_widgets_from_findings
from app.services.suggest_variety import diversify, draws, variety_suggestions
from app.services.widget_data import shape_bubble


def _hr(n=4000, seed=0, link_title=True, tenure_by_title=True):
    rng = np.random.default_rng(seed)
    dept = rng.choice(["Sales", "Development", "Finance", "Marketing", "Research"], n)
    if link_title:
        title = np.where(np.isin(dept, ["Sales", "Finance", "Marketing"]),
                         rng.choice(["Staff", "Senior Staff"], n, p=[.3, .7]),
                         rng.choice(["Engineer", "Senior Engineer", "Staff"], n))
    else:
        title = rng.choice(["Staff", "Senior Staff", "Engineer", "Senior Engineer"], n)
    base = pd.Series(title).map({"Senior Staff": 80000, "Staff": 62000,
                                 "Senior Engineer": 60000, "Engineer": 55000}).to_numpy()
    years = (np.where(pd.Series(title).str.startswith("Senior"), rng.uniform(0, 8, n), rng.uniform(6, 15, n))
             if tenure_by_title else rng.uniform(0, 15, n))
    return pd.DataFrame({
        "emp_no": np.arange(10001, 10001 + n), "dept_name": dept, "title": title,
        "gender": rng.choice(["M", "F"], n), "salary": base + rng.normal(0, 8000, n),
        "hire_date": pd.Timestamp("1985-01-01") + pd.to_timedelta(years * 365.25, "D"),
    })


def _roles(df):
    return effective_roles(detect_types(df), {})


def _by_kind(items):
    return {s["kind"]: s for s in items}


def test_each_shape_is_offered_and_draws():
    df = _hr()
    got = _by_kind(variety_suggestions(df, _roles(df)))
    assert {"kpi", "mix", "spread", "bubble", "share", "rules"} <= set(got)
    for s in got.values():
        assert draws(s["widget_type"], s["config"], df), s["title"]
    mix = got["mix"]
    assert mix["widget_type"] == "bar" and mix["config"]["bar_mode"] == "stacked100"
    assert {mix["config"]["dimension"], mix["config"]["dimension2"]} == {"dept_name", "title"}
    assert got["spread"]["config"] == {"dimension": "title", "measure": "salary", "limit": 15}


def test_independent_categories_are_never_a_mix():
    """Gender is independent of department and title: a mix of it would draw
    the same split in every bar."""
    df = _hr()
    for s in variety_suggestions(df, _roles(df)):
        if s["kind"] == "mix":
            assert "gender" not in (s["config"]["dimension"], s["config"]["dimension2"])


def test_no_mix_when_nothing_travels_together():
    df = _hr(link_title=False)
    assert "mix" not in _by_kind(variety_suggestions(df, _roles(df)))


def test_no_bubble_when_an_axis_does_not_vary_by_group():
    df = _hr(link_title=False, tenure_by_title=False)
    df["salary"] = 60000 + np.random.default_rng(1).normal(0, 8000, len(df))
    got = _by_kind(variety_suggestions(df, _roles(df)))
    assert "bubble" not in got and "spread" not in got


def test_bubble_sizes_by_headcount_and_reads_the_date_as_years():
    df = _hr()
    s = _by_kind(variety_suggestions(df, _roles(df)))["bubble"]
    assert s["config"]["size_aggregation"] == "countd" and s["config"]["measure2"] == "hire_date"
    r = shape_bubble(df, s["config"])
    by = {row["name"]: row for row in r["rows"]}
    assert by["Staff"]["size"] == int((df.title == "Staff").sum())
    years = (df.hire_date.max() - df.hire_date).dt.days / 365.25
    assert abs(by["Staff"]["y"] - years[df.title == "Staff"].mean()) < 1e-6
    assert r["derived"] == {"hire_date": "years_before_latest"}


def test_bubble_date_from_a_live_source_object_column():
    df = _hr()
    df["hire_date"] = df["hire_date"].dt.date              # what a SQL driver returns
    r = shape_bubble(df, {"dimension": "title", "measure": "salary", "measure2": "hire_date",
                          "size": "emp_no", "size_aggregation": "countd", "aggregation": "avg"})
    assert r["type"] == "bubble_series" and all(row["y"] is not None for row in r["rows"])


def test_split_trend_only_when_the_mix_changes():
    df = _hr()
    df["hire_date"] = pd.Timestamp("1985-01-01") + pd.to_timedelta(
        np.where(df.dept_name == "Sales", 0, 3000) + np.random.default_rng(2).integers(0, 2000, len(df)), "D")
    assert "trend_split" in _by_kind(variety_suggestions(df, _roles(df)))
    flat = _hr(tenure_by_title=False)
    assert "trend_split" not in _by_kind(variety_suggestions(flat, _roles(flat)))


def test_at_most_two_of_a_kind_and_stacked_bars_count_apart():
    items = [{"widget_type": "bar", "config": {}}] * 3 + \
            [{"widget_type": "bar", "config": {"dimension2": "x"}}] * 3
    out = diversify(items, 10)
    assert len(out) == 4


def test_the_panel_list_mixes_kinds_and_every_item_draws():
    df = _hr()
    roles = _roles(df)
    res = generate_insights(df, detect_types(df), {})
    out = suggest_widgets_from_findings(res["findings"], roles, "HR", frame=df)
    from app.services.suggest_variety import _type_key
    types = [_type_key(s) for s in out]
    assert len(set(types)) >= 6, types
    assert max(types.count(t) for t in set(types)) <= 2
    for s in out:
        assert s["kind"] == "rules" or draws(s["widget_type"], s["config"], df), s["title"]


def test_a_blocked_column_is_never_volunteered():
    df = _hr()
    out = variety_suggestions(df, _roles(df), ineligible={"title"})
    assert all("title" not in str(s["config"]) for s in out)


def test_every_suggestion_passes_the_save_check():
    """Add runs validate_widget_payload; a refused suggestion added silently
    nothing (an axis title on a box plot, HR re-test 2026-10-02)."""
    from app.services.widget_roles import validate_widget_payload
    df = _hr()
    res = generate_insights(df, detect_types(df), {})
    for s in suggest_widgets_from_findings(res["findings"], _roles(df), "HR", frame=df):
        validate_widget_payload(s["widget_type"], s["config"])
    assert not draws("box_plot", {"dimension": "title", "measure": "salary",
                                  "x_axis_label": "Title"}, df)
