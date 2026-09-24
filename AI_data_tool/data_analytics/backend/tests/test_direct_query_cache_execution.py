import sqlite3
from types import SimpleNamespace

import pytest

from app.services.direct_query import run_direct_query
from app.services.widget_data import clear_widget_data_cache


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_widget_data_cache()
    yield
    clear_widget_data_cache()


@pytest.fixture
def sqlite_source(tmp_path):
    db_path = tmp_path / "cache_test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE sales (region TEXT, revenue REAL)")
    conn.executemany("INSERT INTO sales (region, revenue) VALUES (?, ?)", [("east", 100), ("west", 50)])
    conn.commit()
    conn.close()
    return str(db_path)


def _dataset(db_path, data_source_id=1):
    return SimpleNamespace(
        data_source_id=data_source_id, source_table="sales", source_query=None,
        columns=[SimpleNamespace(name="region"), SimpleNamespace(name="revenue")],
    )


def _mutate(db_path, new_value):
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE sales SET revenue = ? WHERE region = 'east'", (new_value,))
    conn.commit()
    conn.close()


def test_within_ttl_window_returns_cached_stale_result(sqlite_source):
    cfg = {"type": "sqlite", "filepath": sqlite_source}
    config = {"dimension": "region", "measure": "revenue", "aggregation": "sum"}

    first = run_direct_query(cfg, _dataset(sqlite_source), config, widget_type="bar", cache_ttl_seconds=600)
    _mutate(sqlite_source, 999999)
    second = run_direct_query(cfg, _dataset(sqlite_source), config, widget_type="bar", cache_ttl_seconds=600)

    assert second == first  # still the pre-mutation value -- proves the second call hit cache


def test_ttl_zero_bypasses_cache_entirely(sqlite_source):
    cfg = {"type": "sqlite", "filepath": sqlite_source}
    config = {"dimension": "region", "measure": "revenue", "aggregation": "sum"}

    run_direct_query(cfg, _dataset(sqlite_source), config, widget_type="bar", cache_ttl_seconds=0)
    _mutate(sqlite_source, 999999)
    second = run_direct_query(cfg, _dataset(sqlite_source), config, widget_type="bar", cache_ttl_seconds=0)

    east_value = next(r["value"] for r in second["rows"] if r["name"] == "east")
    assert east_value == 999999  # fresh data every time -- cache_ttl_seconds=0 means true real-time


def test_different_rls_filter_expr_never_shares_a_cache_entry(sqlite_source):
    """Mirrors the isolation guarantee already tested for widget_data's own cache:
    a role with a restrictive RLS rule can never be served a cache entry computed
    for a different (looser or absent) rule."""
    cfg = {"type": "sqlite", "filepath": sqlite_source}
    config = {"dimension": "region", "measure": "revenue", "aggregation": "sum"}

    unrestricted = run_direct_query(cfg, _dataset(sqlite_source), config, widget_type="bar",
                                     rls_filter_expr=None, cache_ttl_seconds=600)
    restricted = run_direct_query(cfg, _dataset(sqlite_source), config, widget_type="bar",
                                   rls_filter_expr="region == 'east'", cache_ttl_seconds=600)

    assert {r["name"] for r in unrestricted["rows"]} == {"east", "west"}
    assert {r["name"] for r in restricted["rows"]} == {"east"}


def test_different_data_source_id_never_shares_a_cache_entry(sqlite_source):
    cfg = {"type": "sqlite", "filepath": sqlite_source}
    config = {"dimension": "region", "measure": "revenue", "aggregation": "sum"}

    run_direct_query(cfg, _dataset(sqlite_source, data_source_id=1), config, widget_type="bar", cache_ttl_seconds=600)
    _mutate(sqlite_source, 999999)
    # A DIFFERENT data_source_id pointed at the same underlying data must not
    # reuse data_source_id=1's cache entry.
    second = run_direct_query(cfg, _dataset(sqlite_source, data_source_id=2), config, widget_type="bar", cache_ttl_seconds=600)

    east_value = next(r["value"] for r in second["rows"] if r["name"] == "east")
    assert east_value == 999999
