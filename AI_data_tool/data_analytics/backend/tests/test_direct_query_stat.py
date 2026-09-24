from types import SimpleNamespace

import pytest

from app.services.direct_query import (
    DirectQueryUnsupported,
    _histogram_bin_edges,
    build_correlation_matrix_sql,
    build_histogram_bucket_sql,
    build_histogram_stats_sql,
    plan_correlation_matrix,
    plan_histogram,
)


def _dataset(source_table="sales", columns=("region", "revenue", "profit")):
    return SimpleNamespace(
        source_table=source_table, source_query=None,
        columns=[SimpleNamespace(name=c) for c in columns],
    )


# ── bin edges (must match numpy exactly -- see np.histogram/np.linspace parity check) ──

def test_histogram_bin_edges_matches_numpy_uniform_case():
    edges = _histogram_bin_edges(1.0, 10.0, 5)
    assert edges == [1.0, 2.8, 4.6, 6.4, 8.2, 10.0]


def test_histogram_bin_edges_degenerate_range_widens_by_half():
    """numpy's fallback when min == max: widen the range by 0.5 on each side
    (np.histogram([5,5,5], bins=4) -- see verification done during implementation)."""
    edges = _histogram_bin_edges(5.0, 5.0, 4)
    assert edges == [4.5, 4.75, 5.0, 5.25, 5.5]


# ── plan_histogram / plan_correlation_matrix (validation) ──────────────────

def test_plan_histogram_requires_measure():
    with pytest.raises(DirectQueryUnsupported):
        plan_histogram({}, "histogram")


def test_plan_histogram_rejects_unknown_widget_type():
    with pytest.raises(DirectQueryUnsupported):
        plan_histogram({"measure": "revenue"}, "bar")


def test_plan_correlation_matrix_requires_at_least_two_measures():
    with pytest.raises(DirectQueryUnsupported):
        plan_correlation_matrix({"measures": ["revenue"]}, "correlation_matrix")


def test_plan_correlation_matrix_accepts_two_or_more_measures():
    plan = plan_correlation_matrix({"measures": ["revenue", "profit"]}, "correlation_matrix")
    assert plan.measures == ["revenue", "profit"]


# ── SQL builders (pure) ─────────────────────────────────────────────────────

def test_build_histogram_stats_sql():
    plan = plan_histogram({"measure": "revenue"}, "histogram")
    sql, params = build_histogram_stats_sql(_dataset(), plan)

    assert sql == (
        'SELECT MIN("revenue") AS lo, MAX("revenue") AS hi, COUNT("revenue") AS n '
        'FROM (SELECT * FROM "sales") AS src WHERE "revenue" IS NOT NULL'
    )
    assert params == {}


def test_build_histogram_bucket_sql_clamps_boundary_bucket():
    """WIDTH_BUCKET(x, low, high, n) puts x == high in bucket n+1 (out of range) --
    numpy's last bin is closed on both ends, so the boundary value belongs in
    bucket n. GREATEST/LEAST clamp both ends defensively."""
    plan = plan_histogram({"measure": "revenue"}, "histogram")
    sql, params = build_histogram_bucket_sql(_dataset(), plan, edges=[0.0, 5.0, 10.0])

    assert 'GREATEST(LEAST(WIDTH_BUCKET("revenue", :lo, :hi, :bins), :bins), 1)' in sql
    assert 'WHERE "revenue" IS NOT NULL' in sql
    assert 'GROUP BY bucket' in sql
    assert params == {"lo": 0.0, "hi": 10.0, "bins": 2}


def test_build_correlation_matrix_sql_one_row_all_pairs():
    plan = plan_correlation_matrix({"measures": ["revenue", "profit"]}, "correlation_matrix")
    sql, params = build_correlation_matrix_sql(_dataset(), plan)

    assert sql == (
        'SELECT CORR("revenue", "revenue") AS c0_0, CORR("revenue", "profit") AS c0_1, '
        'CORR("profit", "profit") AS c1_1 '
        'FROM (SELECT * FROM "sales") AS src'
    )
    assert params == {}
