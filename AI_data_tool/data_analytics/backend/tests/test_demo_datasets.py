import pandas as pd
from app.services.demo_content import build_demo_frames


def test_every_frame_is_present_and_non_empty():
    frames = build_demo_frames()
    assert set(frames) == {"sales", "metrics", "projects", "feedback", "routes"}
    for name, df in frames.items():
        assert len(df) > 0, name


def test_generation_is_deterministic_so_the_demo_is_reproducible():
    a, b = build_demo_frames()["sales"], build_demo_frames()["sales"]
    pd.testing.assert_frame_equal(a, b)


def test_sales_spans_two_years_of_months_for_the_time_series_widgets():
    s = build_demo_frames()["sales"]
    months = pd.to_datetime(s["date"]).dt.to_period("M").nunique()
    assert months == 24


def test_sales_carries_negative_values_so_bands_and_diverging_charts_have_something_to_show():
    s = build_demo_frames()["sales"]
    assert (s["margin_pct"] < 0).any()
    assert (s["revenue"] < 0).any()


def test_metrics_correlate_where_the_correlation_matrix_needs_them_to():
    m = build_demo_frames()["metrics"]
    strong = m["height"].corr(m["weight"])
    weak = m["score_a"].corr(m["score_b"])
    # Asserting BOTH is the point: a frame of pure noise passes the first check alone
    # if the threshold is low, and a frame of one repeated pattern passes the second.
    assert strong > 0.7
    assert abs(weak) < 0.3


def test_projects_have_ordered_date_ranges_a_gantt_can_draw():
    p = build_demo_frames()["projects"]
    assert (pd.to_datetime(p["end_date"]) > pd.to_datetime(p["start_date"])).all()
