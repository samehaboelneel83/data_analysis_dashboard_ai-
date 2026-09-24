import os
import time
import pandas as pd
import app.services.widget_data as wd
from app.services.widget_data import get_widget_data, clear_widget_data_cache


def _write_csv(tmp_path, rows, name="d.csv"):
    path = tmp_path / name
    pd.DataFrame(rows).to_csv(path, index=False)
    return str(path)


def setup_function():
    clear_widget_data_cache()


def test_repeated_identical_query_hits_cache(tmp_path, monkeypatch):
    # Counts load_file calls, which only the pandas path makes.
    from app.core.config import settings as _s
    monkeypatch.setattr(_s, "widget_duckdb_pushdown", False)
    path = _write_csv(tmp_path, [{"region": "North", "sales": 100}, {"region": "South", "sales": 200}])
    calls = {"n": 0}
    real_load = wd.load_file
    def counting_load(p):
        calls["n"] += 1
        return real_load(p)
    monkeypatch.setattr(wd, "load_file", counting_load)

    config = {"dimension": "region", "measure": "sales", "aggregation": "sum"}
    r1 = get_widget_data(path, config, widget_type="bar")
    r2 = get_widget_data(path, config, widget_type="bar")

    assert r1 == r2
    assert calls["n"] == 1  # second call served from cache, file never re-read


def test_different_rls_filter_expr_never_shares_a_cache_entry(tmp_path):
    path = _write_csv(tmp_path, [{"region": "North", "sales": 100}, {"region": "South", "sales": 200}])
    config = {"dimension": "region", "measure": "sales", "aggregation": "sum"}

    unrestricted = get_widget_data(path, config, widget_type="bar", rls_filter_expr=None)
    restricted = get_widget_data(path, config, widget_type="bar", rls_filter_expr="region == 'North'")

    assert {r["name"] for r in unrestricted["rows"]} == {"North", "South"}
    assert {r["name"] for r in restricted["rows"]} == {"North"}


def test_file_mtime_change_invalidates_cache(tmp_path):
    path = _write_csv(tmp_path, [{"region": "North", "sales": 100}])
    config = {"dimension": "region", "measure": "sales", "aggregation": "sum"}
    r1 = get_widget_data(path, config, widget_type="bar")
    assert r1["rows"][0]["value"] == 100

    pd.DataFrame([{"region": "North", "sales": 999}]).to_csv(path, index=False)
    os.utime(path, (time.time() + 5, time.time() + 5))  # force a distinct mtime past fs resolution
    r2 = get_widget_data(path, config, widget_type="bar")
    assert r2["rows"][0]["value"] == 999


def test_cache_is_bounded_by_maxsize(tmp_path, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "widget_data_cache_maxsize", 2)
    path = _write_csv(tmp_path, [{"region": "North", "sales": 100}])

    for i in range(5):
        get_widget_data(path, {"dimension": "region", "measure": "sales", "limit": i}, widget_type="bar")

    assert len(wd._WIDGET_DATA_CACHE) <= 2


def test_negative_maxsize_rejected_at_settings_construction():
    from app.core.config import Settings
    import pytest
    with pytest.raises(Exception):
        Settings(widget_data_cache_maxsize=-1)


def test_cache_hit_returns_a_copy_not_the_same_object(tmp_path):
    path = _write_csv(tmp_path, [{"region": "North", "sales": 100}])
    config = {"dimension": "region", "measure": "sales", "aggregation": "sum"}
    r1 = get_widget_data(path, config, widget_type="bar")
    r1["rows"].append({"name": "INJECTED", "value": 999})  # mutate the caller's copy

    r2 = get_widget_data(path, config, widget_type="bar")
    assert r2 is not r1
    assert len(r2["rows"]) == 1  # the mutation must not have reached the cached entry


def test_oversized_result_is_not_cached(tmp_path, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "widget_data_cache_max_entry_bytes", 10)  # tiny, forces every result to be "too big"
    path = _write_csv(tmp_path, [{"region": "North", "sales": 100}, {"region": "South", "sales": 200}])
    config = {"dimension": "region", "measure": "sales", "aggregation": "sum"}

    get_widget_data(path, config, widget_type="bar")

    assert len(wd._WIDGET_DATA_CACHE) == 0  # never wrote to the cache
