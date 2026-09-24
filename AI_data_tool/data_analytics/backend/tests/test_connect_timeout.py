"""Every networked engine-creation path must apply the connect timeout, so an
unreachable database fails fast (like Test Connection does) instead of hanging on the
OS/driver default. Regression guard for the psycopg2 "timeout expired" hang: only
test_connection used to set connect_timeout; list_tables, preview, import, the query
builder and DirectQuery did not.
"""
import pytest

# get_engine and its create_engine call moved to services/engines.py
# (layer 1); direct_query only re-exports the name.
from app.services import connections, engines, query_builder

PG = {"type": "postgresql", "host": "db.invalid", "port": 5432,
      "database": "d", "username": "u", "password": "p"}
SQLITE = {"type": "sqlite", "filepath": "/tmp/x.sqlite"}


class _Stop(Exception):
    """Raised by the fake create_engine so we capture connect_args without a real connect."""


def _capture(monkeypatch, module):
    cap = {}

    def fake_create_engine(url, **kw):
        cap["connect_args"] = kw.get("connect_args") or {}
        raise _Stop()

    monkeypatch.setattr(module, "create_engine", fake_create_engine)
    # Stub URL building so we never touch net_guard / DNS for the fake host.
    monkeypatch.setattr(connections, "_build_url", lambda cfg: "postgresql://stub", raising=False)
    monkeypatch.setattr(engines, "_build_url", lambda cfg: "postgresql://stub", raising=False)
    return cap


def test_list_tables_applies_connect_timeout(monkeypatch):
    cap = _capture(monkeypatch, connections)
    with pytest.raises(_Stop):
        connections.list_tables(PG)
    assert cap["connect_args"].get("connect_timeout") == 8


def test_preview_table_applies_connect_timeout(monkeypatch):
    cap = _capture(monkeypatch, connections)
    with pytest.raises(_Stop):
        connections.preview_table(PG, "t", None)
    assert cap["connect_args"].get("connect_timeout") == 8


def test_import_to_dataframe_applies_connect_timeout(monkeypatch):
    cap = _capture(monkeypatch, connections)
    with pytest.raises(_Stop):
        connections.import_to_dataframe(PG, "t", None)
    assert cap["connect_args"].get("connect_timeout") == 8


def test_directquery_get_engine_applies_connect_timeout(monkeypatch):
    cap = _capture(monkeypatch, engines)
    with pytest.raises(_Stop):
        engines.get_engine(PG)
    assert cap["connect_args"].get("connect_timeout") == 8


def test_query_builder_table_columns_applies_connect_timeout(monkeypatch):
    cap = _capture(monkeypatch, query_builder)
    with pytest.raises(_Stop):
        query_builder.table_columns(PG, "t")
    assert cap["connect_args"].get("connect_timeout") == 8


def test_sqlite_gets_no_connect_timeout(monkeypatch):
    # In-process drivers reject connect_timeout — it must stay absent for them.
    cap = _capture(monkeypatch, connections)
    with pytest.raises(_Stop):
        connections.list_tables(SQLITE)
    assert "connect_timeout" not in cap["connect_args"]
