"""Quick one-click calculations and confidentiality suppression on shape_series."""
import pandas as pd
import pytest

from app.services.widget_data import shape_series


def df():
    return pd.DataFrame({
        "dept": ["Eng", "Eng", "Eng", "Ops", "HR", "HR"],
        "salary": [100.0, 110.0, 120.0, 200.0, 90.0, 95.0],
    })


def base(**extra):
    return {"dimension": "dept", "measure": "salary", "aggregation": "sum", **extra}


# ── suppression ──────────────────────────────────────────────────────────────

def test_groups_below_the_row_threshold_are_suppressed():
    # Ops has ONE source row: its "sum" is one person's salary. Hidden.
    r = shape_series(df(), base(suppress_below=2))
    names = {x["name"] for x in r["rows"]}
    assert "Ops" not in names and names == {"Eng", "HR"}


def test_complement_hides_the_smallest_survivor_only_when_something_was_suppressed():
    r = shape_series(df(), base(suppress_below=2, suppress_complement=True))
    # HR (185) is the smallest survivor: hidden so Ops cannot be back-computed
    # from a visible total.
    assert {x["name"] for x in r["rows"]} == {"Eng"}
    # nothing suppressed -> complement leaves everything alone
    r = shape_series(df(), base(suppress_below=1, suppress_complement=True))
    assert {x["name"] for x in r["rows"]} == {"Eng", "Ops", "HR"}


def test_suppression_happens_before_totals():
    r = shape_series(df(), base(suppress_below=2, show_totals=True))
    assert r["totals"][1] == pytest.approx(330.0 + 185.0)  # Eng + HR only


def test_malformed_threshold_is_ignored():
    r = shape_series(df(), base(suppress_below="lots"))
    assert len(r["rows"]) == 3


# ── quick calculations ───────────────────────────────────────────────────────

def test_percent_of_total_sums_to_one_hundred():
    r = shape_series(df(), base(quick_calc="percent_of_total"))
    vals = [x["value"] for x in r["rows"]]
    assert sum(vals) == pytest.approx(100.0, abs=0.1)
    by = {x["name"]: x["value"] for x in r["rows"]}
    assert by["Eng"] == pytest.approx(330.0 / 715.0 * 100, abs=0.01)


def test_difference_and_percent_change_follow_the_sort_order():
    r = shape_series(df(), base(quick_calc="difference", sort="desc"))
    rows = r["rows"]
    # first row has no previous -> None; second is its value minus the first's
    assert rows[0]["value"] is None
    assert rows[1]["value"] == pytest.approx(-130.0)  # Eng 330 -> Ops 200

    r = shape_series(df(), base(quick_calc="percent_change", sort="desc"))
    assert r["rows"][1]["value"] == pytest.approx(-39.39, abs=0.01)


def test_rank_is_dense_from_the_largest():
    r = shape_series(df(), base(quick_calc="rank"))
    assert {x["name"]: x["value"] for x in r["rows"]} == {"Eng": 1, "Ops": 2, "HR": 3}


def test_percent_of_total_uses_all_categories_not_just_the_visible_page():
    # limit truncates AFTER the transform: the visible bars keep their share of
    # the whole, they do not re-base to the page.
    r = shape_series(df(), base(quick_calc="percent_of_total", limit=1))
    assert r["rows"][0]["value"] == pytest.approx(330.0 / 715.0 * 100, abs=0.01)
