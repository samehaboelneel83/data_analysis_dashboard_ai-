"""Task O2: widget_data.py's cache functions actually route through
cache_backend.py's ValkeyCache when settings.valkey_url is set, using
fakeredis so no real server/network is needed. Complements
test_cache_backend.py (interface-level) and test_widget_data_cache.py
(pre-O2 in-process regression, left untouched)."""
import numpy as np
import pandas as pd
import fakeredis

import app.services.widget_data as wd
# The cache singleton lives in widget_shaping now (widget_data re-exports
# the accessors); assigning it must target the module that owns it.
import app.services.widget_shaping as ws
from app.services.cache_backend import ValkeyCache
from app.services.widget_data import (
    get_widget_data, get_widget_data_from_df,
    _widget_data_cache_get, _widget_data_cache_set,
)


def _write_csv(tmp_path, rows, name="d.csv"):
    path = tmp_path / name
    pd.DataFrame(rows).to_csv(path, index=False)
    return str(path)


def setup_function():
    wd.clear_widget_data_cache()
    wd.reset_cache_backend()


def teardown_function():
    wd.clear_widget_data_cache()
    wd.reset_cache_backend()


def _install_fake_valkey(monkeypatch, server=None):
    server = server or fakeredis.FakeServer()
    client = fakeredis.FakeRedis(server=server)
    monkeypatch.setattr(wd.settings, "valkey_url", "redis://fake-for-tests")
    ws._valkey_backend = ValkeyCache(client=client, key_prefix="wdc:")
    return client, server


def test_widget_data_result_lands_in_valkey_when_configured(tmp_path, monkeypatch):
    client, _ = _install_fake_valkey(monkeypatch)
    path = _write_csv(tmp_path, [{"region": "North", "sales": 100}])
    config = {"dimension": "region", "measure": "sales", "aggregation": "sum"}

    get_widget_data(path, config, widget_type="bar")

    stored = client.keys("wdc:*")
    assert len(stored) == 1  # went to Valkey, not just the in-process dict
    assert len(wd._WIDGET_DATA_CACHE) == 0  # in-process store untouched on this path


def test_cache_hit_via_valkey_skips_reloading_the_file(tmp_path, monkeypatch):
    # Counts load_file calls, which only the pandas path makes.
    from app.core.config import settings as _s
    monkeypatch.setattr(_s, "widget_duckdb_pushdown", False)
    _install_fake_valkey(monkeypatch)
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
    assert calls["n"] == 1


def test_raw_rls_expression_text_never_reaches_the_fake_server(tmp_path, monkeypatch):
    """sha256-hashed keys: the sensitive RLS expression string that IS part
    of the plaintext cache key (load-bearing for RLS isolation) must never
    appear anywhere in what's actually stored in Valkey."""
    client, _ = _install_fake_valkey(monkeypatch)
    path = _write_csv(tmp_path, [{"region": "North", "sales": 100}, {"region": "South", "sales": 200}])
    config = {"dimension": "region", "measure": "sales", "aggregation": "sum"}
    secret_expr = "region == 'a-secret-looking-region-name'"

    get_widget_data(path, config, widget_type="bar", rls_filter_expr=secret_expr)

    for key in client.keys("*"):
        assert secret_expr.encode() not in key
    for value in (client.get(k) for k in client.keys("*")):
        assert secret_expr.encode() not in value


def test_two_widget_data_workers_share_a_cached_result_via_valkey(tmp_path, monkeypatch):
    """Two InProcess->shared-Valkey 'workers' (simulated as two ValkeyCache
    instances over one fakeredis server, the way two backend replicas would
    share one real Valkey) see each other's cache entries."""
    server = fakeredis.FakeServer()
    path = _write_csv(tmp_path, [{"region": "North", "sales": 100}])
    config = {"dimension": "region", "measure": "sales", "aggregation": "sum"}

    # "Worker A" writes the entry.
    client_a, _ = _install_fake_valkey(monkeypatch, server=server)
    r1 = get_widget_data(path, config, widget_type="bar")

    # "Worker B": a fresh cache-backend instance, same shared fakeredis server,
    # and never calls load_file -- proving it's served from the shared cache.
    wd.reset_cache_backend()
    client_b = fakeredis.FakeRedis(server=server)
    ws._valkey_backend = ValkeyCache(client=client_b, key_prefix="wdc:")

    calls = {"n": 0}
    real_load = wd.load_file
    def failing_load(p):
        calls["n"] += 1
        raise AssertionError("worker B should never re-parse the file on a shared-cache hit")
    monkeypatch.setattr(wd, "load_file", failing_load)

    r2 = get_widget_data(path, config, widget_type="bar")
    assert r2 == r1
    assert calls["n"] == 0


def test_valkey_url_none_never_touches_a_client(monkeypatch):
    """Regression: with no valkey_url, the cache-backend selector must return
    the in-process backend and never attempt to build or use a Valkey client.

    The unset state is now SET here rather than assumed. It used to be the
    shipped default, so the test could assert it as a precondition -- but
    docker-compose.yml now points VALKEY_URL at the valkey service it already
    runs, and a deployment that wants the old behaviour sets `VALKEY_URL=`
    explicitly. That is exactly the configuration under test, so it has to be
    established rather than inherited from whatever the environment happens to
    be."""
    monkeypatch.setattr(wd.settings, "valkey_url", None)
    wd.reset_cache_backend()
    backend = wd._get_cache_backend()
    assert backend is wd._inprocess_backend


# ── Round-trip type equality: Valkey hit vs. in-process hit vs. fresh compute ─
#
# cache_backend.ValkeyCache serializes with `json.dumps(value, default=str)`;
# InProcessCache stores the Python object as-is. If ANY field of a cached
# result were not already JSON-native by the time it reaches either backend,
# the two would silently diverge in TYPE for the identical cache key: the
# in-process hit keeps the original object, the Valkey hit gets whatever
# `default=str` produced. `widget_data._safe` is the single choke point every
# result field is supposed to funnel through before caching -- these tests
# pin that it actually closes the gap for the value shapes most likely to
# leak through un-sanitized: numpy floats, NaN, a real pandas Timestamp/NaT
# (the gap this test suite caught -- DirectQuery's `pd.read_sql` produces
# datetime64 columns for a raw "table" widget, and `_safe` used to let a
# non-null Timestamp fall through unconverted), and non-ASCII (Arabic) text.

def _realistic_df():
    return pd.DataFrame({
        "label": ["مرحبا", "قيمة عربية", None],
        "amount": [np.float64(12.5), np.float64("nan"), np.float64(7.0)],
        "when": pd.to_datetime(["2024-01-15", pd.NaT, "2023-12-31"]),
    })


def test_safe_converts_timestamps_to_the_same_iso_string_every_time():
    """Unit-level pin on the actual fix: a non-null Timestamp/date must
    become a plain `str` (ISO format), and NaT must become `None`, so there
    is nothing left for a JSON encoder to transform differently than the
    in-process store already holds."""
    ts = pd.Timestamp("2024-01-15")
    safe_ts = wd._safe(ts)
    assert safe_ts == "2024-01-15T00:00:00"
    assert type(safe_ts) is str

    assert wd._safe(pd.NaT) is None

    import datetime
    assert wd._safe(datetime.date(2023, 12, 31)) == "2023-12-31"


def test_realistic_result_round_trips_identically_through_both_backends(monkeypatch):
    df = _realistic_df()
    result = get_widget_data_from_df(df, {}, widget_type="table")
    # Sanity: the shaped result already contains the value shapes under test,
    # and _safe already normalized the Timestamp column to plain strings --
    # nothing pandas/numpy-typed should remain for either backend to diverge on.
    for row in result["rows"]:
        for cell in row:
            assert not isinstance(cell, (pd.Timestamp, np.generic))

    key = "o2-realistic-values-round-trip"

    # In-process backend. Set explicitly rather than assumed: VALKEY_URL now
    # defaults to the compose service, so "unset" is a configuration this test
    # must establish, not one it can inherit.
    wd.clear_widget_data_cache()
    monkeypatch.setattr(wd.settings, "valkey_url", None)
    wd.reset_cache_backend()
    _widget_data_cache_set(key, result)
    in_process_hit = _widget_data_cache_get(key)

    # Valkey backend (fakeredis stands in for a real server).
    client = fakeredis.FakeRedis()
    monkeypatch.setattr(wd.settings, "valkey_url", "redis://fake-for-tests")
    wd.reset_cache_backend()
    ws._valkey_backend = ValkeyCache(client=client, key_prefix="wdc:")
    _widget_data_cache_set(key, result)
    valkey_hit = _widget_data_cache_get(key)

    # Value equality...
    assert in_process_hit == result
    assert valkey_hit == result
    assert in_process_hit == valkey_hit
    # ...AND type equality, cell by cell -- the actual thing under test. Value
    # equality alone would hide e.g. a Timestamp-vs-str drift whenever the
    # string repr happens to compare equal-ish, or a bool/int/float mismatch
    # that Python's `==` quietly forgives (`1 == 1.0 == True`).
    for row_a, row_b in zip(in_process_hit["rows"], valkey_hit["rows"]):
        for cell_a, cell_b in zip(row_a, row_b):
            assert type(cell_a) is type(cell_b), f"{cell_a!r} ({type(cell_a)}) vs {cell_b!r} ({type(cell_b)})"


def test_directquery_style_datetime64_column_survives_the_cache_as_a_string(monkeypatch):
    """Reproduces the concrete scenario that made the Timestamp gap real:
    DirectQuery's `pd.read_sql` (services/direct_query.py) yields a
    datetime64 column for a SQL DATE/DATETIME field, which a raw "table"
    widget (no dimension/measure -- see shape_series's itertuples branch)
    passes straight through per-cell `_safe`. Before the fix this cell
    stayed a live `pd.Timestamp` on an in-process hit while becoming a
    `str(Timestamp)` on a Valkey hit for the SAME cache key -- silent,
    backend-dependent type drift. After the fix both are the identical str
    from the moment `_safe` runs, so there is nothing left to drift."""
    df = pd.DataFrame({"order_date": pd.to_datetime(["2024-06-01", "2024-06-02"])})
    result = get_widget_data_from_df(df, {}, widget_type="table")
    cell = result["rows"][0][0]
    assert isinstance(cell, str)
    assert cell == "2024-06-01T00:00:00"

    key = "o2-directquery-datetime-column"
    wd.clear_widget_data_cache()
    wd.reset_cache_backend()
    _widget_data_cache_set(key, result)
    in_process_hit = _widget_data_cache_get(key)

    client = fakeredis.FakeRedis()
    monkeypatch.setattr(wd.settings, "valkey_url", "redis://fake-for-tests")
    wd.reset_cache_backend()
    ws._valkey_backend = ValkeyCache(client=client, key_prefix="wdc:")
    _widget_data_cache_set(key, result)
    valkey_hit = _widget_data_cache_get(key)

    assert in_process_hit["rows"][0][0] == valkey_hit["rows"][0][0] == "2024-06-01T00:00:00"
    assert type(in_process_hit["rows"][0][0]) is type(valkey_hit["rows"][0][0]) is str
