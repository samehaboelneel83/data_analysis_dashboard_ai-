import sqlite3
from types import SimpleNamespace

import pandas as pd
import pytest

from app.services.direct_query import DirectQueryUnsupported, run_direct_query
from app.services.widget_data import clear_widget_data_cache, get_widget_data_from_df


@pytest.fixture(autouse=True)
def _clear_cache():
    # These tests predate DirectQuery result caching, so their _dataset() fixtures
    # don't set data_source_id -- without clearing between tests, an earlier
    # test's cache entry could collide with a later one's key (same source_table,
    # similar config) and leak stale data across unrelated tests.
    clear_widget_data_cache()
    yield
    clear_widget_data_cache()


ROWS = [
    ("east", 100), ("east", 50), ("east", 25),
    ("west", 200), ("west", 10),
    ("north", 5),
]


@pytest.fixture
def sqlite_source(tmp_path):
    """A real on-disk SQLite DB (not the async app DB) seeded with a sales
    table, plus the DataSource-style connection config that points at it."""
    db_path = tmp_path / "direct_query_test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE sales (region TEXT, revenue REAL)")
    conn.executemany("INSERT INTO sales (region, revenue) VALUES (?, ?)", ROWS)
    conn.commit()
    conn.close()
    return {"type": "sqlite", "filepath": str(db_path)}


def _dataset(source_table="sales", columns=("region", "revenue")):
    return SimpleNamespace(
        source_table=source_table, source_query=None,
        columns=[SimpleNamespace(name=c) for c in columns],
    )


@pytest.mark.parametrize("agg", ["sum", "avg", "min", "max"])
def test_run_direct_query_matches_import_mode_grain_invariant(sqlite_source, agg):
    """The core correctness property: for a grain-safe aggregation, pushing the
    GROUP BY down to SQL and re-aggregating in the shaper must produce exactly
    the same widget output as loading all rows into pandas and aggregating
    once. If this test fails, the grain invariant the whole DirectQuery design
    relies on is broken.

    Limited to sum/avg/min/max here because SQLite has no PERCENTILE_CONT/MEDIAN
    -- see test_run_direct_query_rejects_percentile_on_sqlite below for that
    dialect gap (median/p25/p75/p90/p95 are still grain-safe in principle; they
    just aren't pushable to this particular dialect yet)."""
    config = {"dimension": "region", "measure": "revenue", "aggregation": agg}

    direct_result = run_direct_query(sqlite_source, _dataset(), config, widget_type="bar")

    df = pd.DataFrame(ROWS, columns=["region", "revenue"])
    import_result = get_widget_data_from_df(df, config, widget_type="bar")

    assert direct_result == import_result


def test_run_direct_query_rejects_percentile_on_sqlite(sqlite_source):
    config = {"dimension": "region", "measure": "revenue", "aggregation": "median"}

    with pytest.raises(DirectQueryUnsupported):
        run_direct_query(sqlite_source, _dataset(), config, widget_type="bar")


def test_run_direct_query_applies_rls_filter(sqlite_source):
    """The whole point of RLS pushdown: a user restricted to 'east' must never see
    west/north rows in the aggregated result, matching import mode's apply_rls_filter
    behavior but enforced in SQL before aggregation."""
    config = {"dimension": "region", "measure": "revenue", "aggregation": "sum"}

    result = run_direct_query(
        sqlite_source, _dataset(), config, widget_type="bar", rls_filter_expr="region == 'east'",
    )

    names = {row["name"] for row in result["rows"]}
    assert names == {"east"}
    assert result["total"] == 3  # the 3 'east' rows, not all 6


def test_run_direct_query_rls_is_fail_closed_on_untranslatable_expression(sqlite_source, monkeypatch):
    """An RLS rule that can't be translated must never result in the query running
    without the predicate -- assert the engine is never even reached, not just that
    an exception is raised, since a bug that raised AFTER running the query would
    still leak rows to the caller in a partially-handled error path."""
    import app.services.direct_query as direct_query_module

    called = False

    def _spy_get_engine(cfg):
        nonlocal called
        called = True
        raise AssertionError("engine should never be created for an untranslatable RLS expression")

    monkeypatch.setattr(direct_query_module, "get_engine", _spy_get_engine)

    config = {"dimension": "region", "measure": "revenue", "aggregation": "sum"}

    with pytest.raises(DirectQueryUnsupported):
        run_direct_query(
            sqlite_source, _dataset(), config, widget_type="bar",
            rls_filter_expr="SUM(revenue) > 100",  # function calls aren't translatable
        )

    assert called is False


def test_run_direct_query_counts_rows_per_dimension_when_no_measure_is_set(sqlite_source):
    """The single most common widget shape: a bar chart with only a dimension
    set, no measure -- 'count of rows per category'. shape_series's own
    no-measure branch always falls back to .size() regardless of the
    'aggregation' field's value (see widget_data.py's grouped-series branch),
    so DirectQuery must reproduce that exactly, not require a measure that
    doesn't exist for this very common chart shape."""
    config = {"dimension": "region", "aggregation": "sum"}  # aggregation set but irrelevant -- no measure

    direct_result = run_direct_query(sqlite_source, _dataset(), config, widget_type="bar")

    df = pd.DataFrame(ROWS, columns=["region", "revenue"])
    import_result = get_widget_data_from_df(df, config, widget_type="bar")

    assert direct_result == import_result


def test_run_direct_query_count_series_applies_display_rules(sqlite_source):
    """_run_count_series -- the no-measure "count of rows per dimension value" path,
    the single most common widget shape -- returns directly from
    _dispatch_direct_query instead of reaching get_widget_data_from_df, so display
    rules used to never evaluate here even though the docstring and spec claimed
    DirectQuery worked identically to import mode. run_direct_query now applies the
    rule pass centrally, once, after dispatch returns, so this must pick up rules
    exactly like the plain aggregate path does."""
    config = {
        "dimension": "region", "aggregation": "sum",
        "display_rules": [{"id": "r1", "kind": "expression", "target": "mark",
                            "expression": "value > 2", "style": {"fill": "#f87171"}}],
    }

    result = run_direct_query(sqlite_source, _dataset(), config, widget_type="bar")

    assert result["rule_errors"] == []
    # east has 3 rows (> 2), west 2, north 1 -- only east's row should be painted.
    east_idx = next(i for i, r in enumerate(result["rows"]) if r["name"] == "east")
    north_idx = next(i for i, r in enumerate(result["rows"]) if r["name"] == "north")
    assert result["rule_styles"]["rows"][east_idx] == {"fill": "#f87171"}
    assert result["rule_styles"]["rows"][north_idx] is None


def test_run_direct_query_count_series_rule_error_fails_open(sqlite_source):
    """A broken rule must be recorded in rule_errors without blanking the widget --
    same fail-open contract as every other display-rules path (display_rules.py's
    module docstring)."""
    config = {
        "dimension": "region", "aggregation": "sum",
        "display_rules": [{"id": "bad", "kind": "expression", "target": "mark",
                            "expression": "not a valid expr !!", "style": {"fill": "#f87171"}}],
    }

    result = run_direct_query(sqlite_source, _dataset(), config, widget_type="bar")

    assert len(result["rule_errors"]) == 1
    assert result["rule_errors"][0]["id"] == "bad"
    assert len(result["rows"]) == 3  # every row still returned despite the broken rule


def test_run_direct_query_no_rls_rule_means_unrestricted(sqlite_source):
    config = {"dimension": "region", "measure": "revenue", "aggregation": "sum"}

    result = run_direct_query(sqlite_source, _dataset(), config, widget_type="bar", rls_filter_expr=None)

    names = {row["name"] for row in result["rows"]}
    assert names == {"east", "west", "north"}


def test_run_direct_query_applies_comparison_filter(sqlite_source):
    config = {
        "dimension": "region", "measure": "revenue", "aggregation": "sum",
        "filters": [{"column": "revenue", "op": "gte", "value": 50}],
    }

    result = run_direct_query(sqlite_source, _dataset(), config, widget_type="bar")

    names = {row["name"] for row in result["rows"]}
    assert names == {"east", "west"}  # north's only row (revenue=5) is filtered out


def test_run_direct_query_rejects_unsupported_dialect(sqlite_source):
    # snowflake, not sqlserver: sqlserver became a supported dialect once
    # OFFSET/FETCH replaced the TOP-n syntax that had blocked it.
    cfg = {**sqlite_source, "type": "snowflake"}

    with pytest.raises(DirectQueryUnsupported):
        run_direct_query(cfg, _dataset(), {"dimension": "region", "measure": "revenue"}, widget_type="bar")


def test_run_direct_query_rejects_unknown_column(sqlite_source):
    config = {"dimension": "region", "measure": "does_not_exist"}

    with pytest.raises(DirectQueryUnsupported):
        run_direct_query(sqlite_source, _dataset(), config, widget_type="bar")


def test_run_direct_query_uses_source_query_when_no_source_table(sqlite_source):
    config = {"dimension": "region", "measure": "revenue", "aggregation": "sum"}
    dataset = _dataset(source_table=None)
    dataset.source_query = "SELECT * FROM sales WHERE region != 'north'"

    result = run_direct_query(sqlite_source, dataset, config, widget_type="bar")

    names = {row["name"] for row in result["rows"]}
    assert "north" not in names


@pytest.mark.parametrize("config", [
    {"dimension": "region", "measure": "revenue", "aggregation": "sum", "limit": 2},
    {"dimension": "region", "aggregation": "sum", "limit": 2},   # the count-only path
])
def test_a_cut_page_is_disclosed_exactly_as_import_mode_does(sqlite_source, config):
    """The SQL LIMIT means the shaper only ever sees the top N groups, so its own
    truncation would always read "nothing cut". DirectQuery measures the group
    count in SQL and must say what import mode says: 2 shown of 3."""
    direct = run_direct_query(sqlite_source, _dataset(), config, widget_type="bar")
    df = pd.DataFrame(ROWS, columns=["region", "revenue"])
    imported = get_widget_data_from_df(df, config, widget_type="bar")
    assert direct["truncation"] == imported["truncation"]
    assert direct["truncation"]["applied"] is True
    assert (direct["truncation"]["shown"], direct["truncation"]["of"]) == (2, 3)


def test_a_short_page_is_not_cut(sqlite_source):
    config = {"dimension": "region", "measure": "revenue", "aggregation": "sum", "limit": 10}
    direct = run_direct_query(sqlite_source, _dataset(), config, widget_type="bar")
    assert direct["truncation"]["applied"] is False
    assert direct["truncation"]["of"] == 3
