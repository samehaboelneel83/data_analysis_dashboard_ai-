"""Stored times are UTC whatever the server's clock says.

The app writes naive UTC (`datetime.utcnow()`) into TIMESTAMPTZ columns.
asyncpg sends a naive datetime as the PROCESS's local time, and PostgreSQL
reads a naive text timestamp in the SESSION's time zone -- so on a machine
not set to UTC every stored time moved (found live on one set to Cairo: a
run a moment ago read "3 hours ago"). Checked against PostgreSQL 16 with the
session in Africa/Cairo and the process in EEST: without the fix a stored
utcnow() was 3.0 h in the past, with it 0.0 h.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.database import (naive_params_as_utc, pin_utc_on_connect, utc_bound_datetimes,
                               utc_connect_args)

NAIVE = datetime(2026, 9, 26, 12, 0)
AWARE = datetime(2026, 9, 26, 15, 0, tzinfo=timezone(timedelta(hours=3)))


class TestBoundParameters:
    def test_a_naive_datetime_is_marked_utc(self):
        out = naive_params_as_utc({"at": NAIVE, "n": 1, "s": "x"})
        assert out["at"] == datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
        assert out["n"] == 1 and out["s"] == "x"

    def test_an_aware_datetime_is_left_as_it_is(self):
        assert naive_params_as_utc({"at": AWARE})["at"] is AWARE

    def test_positional_and_executemany_shapes(self):
        assert naive_params_as_utc((NAIVE, 2))[0].tzinfo is timezone.utc
        many = naive_params_as_utc([{"at": NAIVE}, {"at": None}])
        assert many[0]["at"].tzinfo is timezone.utc and many[1]["at"] is None
        assert naive_params_as_utc([(NAIVE,), (AWARE,)])[1][0] is AWARE

    def test_nothing_bound(self):
        assert naive_params_as_utc(None) is None and naive_params_as_utc({}) == {}


class TestEngines:
    def test_the_async_driver_asks_for_a_utc_session(self):
        assert utc_connect_args("postgresql+asyncpg://u@h/db") == {"server_settings": {"timezone": "UTC"}}
        assert utc_connect_args("sqlite+aiosqlite:///x.db") == {}

    def test_the_parameter_hook_is_on_an_asyncpg_engine_only(self):
        pg = create_async_engine("postgresql+asyncpg://u:p@localhost/db")
        hook = utc_bound_datetimes(pg)
        assert hook is not None and event.contains(pg.sync_engine, "before_cursor_execute", hook)
        stmt, params = hook(None, None, "INSERT ...", {"at": NAIVE}, None, False)
        assert params["at"].tzinfo is timezone.utc
        assert utc_bound_datetimes(create_async_engine("sqlite+aiosqlite://")) is None

    def test_the_app_engine_carries_it(self):
        from app.core import database
        if database.engine.dialect.name == "postgresql":
            assert event.contains(database.engine.sync_engine, "before_cursor_execute",
                                  database._ENGINE_UTC_HOOK)

    def test_a_sync_engine_sets_utc_on_postgres_only(self):
        pg = create_engine("postgresql+psycopg2://u:p@localhost/db")
        hook = pin_utc_on_connect(pg)
        assert hook is not None and event.contains(pg, "connect", hook)
        assert pin_utc_on_connect(create_engine("sqlite://")) is None
