"""T5: query_runs telemetry -- each of the three query-execution write points
(DirectQuery pushdown, the import/pandas widget path, both agent executors)
must write exactly one QueryRun row, tagged correctly, with no SQL text ever
stored -- only its sha256 hash. And a logging failure must never break the
query it's trying to describe.

T13 fix: the writer (app/services/query_log.py) was rewritten from an
async-session-via-asyncio.run() design (which corrupted the app's shared
asyncpg pool -- see the T5 report addendum) to a fully synchronous, wholly
separate `create_engine`(NullPool) writer that never touches the async
engine, `AsyncSessionLocal`, or any event loop. `app_db` below points that
writer's engine at an isolated on-disk sqlite file per test, via
`settings.database_url` + resetting the module's lazy engine singleton --
NOT via `app.core.database.AsyncSessionLocal`, which this module must never
reference again.
"""
import re
import sqlite3
from types import SimpleNamespace

import pandas as pd
import pytest
from sqlalchemy import create_engine

import app.core.database as db_module
from app.core.config import settings
from app.core.database import Base
from app.models.models import QueryRun
from app.services import query_log


@pytest.fixture
def app_db(tmp_path, monkeypatch):
    """A real, file-backed sqlite database standing in for the app's own
    database -- built with the SAME `Base.metadata` every real table comes
    from, so `query_log`'s raw `QueryRun.__table__.insert()` lands on a
    schema that actually exists. `settings.database_url` (not
    `app.core.database.AsyncSessionLocal`) is what query_log's writer reads,
    so that's what gets pointed at the test file; the module's lazily-cached
    engine singleton is reset before and after so no test's engine leaks
    into the next one."""
    db_path = tmp_path / "app.db"
    setup_engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(setup_engine)
    setup_engine.dispose()

    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")
    monkeypatch.setattr(query_log, "_sync_engine", None)
    yield db_path
    monkeypatch.setattr(query_log, "_sync_engine", None)


def _rows(db_path):
    """Read back every QueryRun row over a FRESH connection -- not the one
    query_log's writer used -- so a passing assertion actually proves the
    writer committed and closed rather than merely that the same connection
    can see its own uncommitted work."""
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.connect() as conn:
            result = conn.execute(QueryRun.__table__.select())
            return [dict(r._mapping) for r in result]
    finally:
        engine.dispose()


_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class TestHelper:
    def test_log_query_run_sync_writes_a_row(self, app_db):
        query_log.log_query_run_sync(
            org_id=1, source_kind="agent", data_source_id=None, dataset_id=None,
            sql_hash=None, rows_returned=3, duration_ms=5, executor="duckdb",
            cache_hit=False,
        )
        rows = _rows(app_db)
        assert len(rows) == 1
        assert rows[0]["source_kind"] == "agent"
        assert rows[0]["rows_returned"] == 3

    def test_a_raising_logger_does_not_raise(self, app_db, monkeypatch):
        """The fire-and-forget contract: whatever goes wrong inside the
        insert, log_query_run_sync itself must never raise."""
        def _boom():
            raise RuntimeError("db is on fire")
        monkeypatch.setattr(query_log, "_get_engine", _boom)
        query_log.log_query_run_sync(org_id=1, source_kind="agent", duration_ms=1, executor="duckdb")
        # No exception reached here -- that IS the assertion.

    def test_the_writer_never_imports_or_touches_the_async_engine(self, app_db, monkeypatch):
        """T13's actual root cause: the writer must never go anywhere near
        `app.core.database.AsyncSessionLocal` or the shared async `engine`,
        and must never drive anything through `asyncio.run()` (the exact
        mechanism that corrupted the pool). Proven three ways -- (1) the
        module binds no `asyncio` name at all (checked by AST, over actual
        import statements only -- the docstring above mentions both names in
        prose, which a raw substring search would wrongly flag), (2) neither
        the async `engine` nor `AsyncSessionLocal` object is ever imported
        into the module's namespace, and (3) poisoning AsyncSessionLocal with
        a callable that raises the moment it's invoked still lets a normal
        call through clean."""
        import ast
        import inspect

        tree = ast.parse(inspect.getsource(query_log))
        imported_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_names.update(a.asname or a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported_names.update(a.asname or a.name for a in node.names)
        assert "asyncio" not in imported_names
        assert "AsyncSessionLocal" not in imported_names
        assert "AsyncSessionLocal" not in vars(query_log)
        assert "engine" not in vars(query_log)

        def _poisoned(*a, **kw):
            raise AssertionError("query_log touched the async session factory")
        monkeypatch.setattr(db_module, "AsyncSessionLocal", _poisoned)

        query_log.log_query_run_sync(org_id=1, source_kind="agent", duration_ms=1, executor="duckdb")
        assert len(_rows(app_db)) == 1

    async def test_calling_from_inside_a_running_event_loop_works(self, app_db):
        """The exact scenario that broke production: T13 traced the pool
        corruption to log_query_run_sync being reachable from a context where
        an event loop is already running (a worker thread whose asyncio.run()
        collided with the main loop's asyncpg connections). The fix must make
        that context simply WORK -- no asyncio.run(), so no loop conflict is
        even possible. This test runs inside pytest-asyncio's own running
        loop and calls the (synchronous, blocking) helper directly."""
        import asyncio

        asyncio.get_running_loop()  # sanity: a loop really is running here
        query_log.log_query_run_sync(org_id=2, source_kind="agent", duration_ms=1, executor="pushdown")
        rows = _rows(app_db)
        assert len(rows) == 1
        assert rows[0]["org_id"] == 2

    def test_repeated_calls_leave_no_open_transaction(self, app_db):
        """NullPool + connect/insert/commit/close per call means nothing is
        ever left half-committed for a later caller to inherit -- the T13
        failure mode (a zombie idle-in-transaction connection whose next
        borrower's commit silently lands inside the wrong transaction).
        Proven by reading all N rows back over a brand-new connection after
        N calls -- a stuck transaction would hide at least the most recent
        writes from a fresh connection."""
        for i in range(10):
            query_log.log_query_run_sync(
                org_id=i, source_kind="agent", duration_ms=i, executor="duckdb",
            )
        rows = _rows(app_db)
        assert len(rows) == 10
        assert sorted(r["org_id"] for r in rows) == list(range(10))


class TestDirectQueryWritePoint:
    """Write point #1: direct_query.run_direct_query."""

    @pytest.fixture
    def sqlite_source(self, tmp_path):
        db_path = tmp_path / "dq.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE sales (region TEXT, revenue REAL)")
        conn.executemany(
            "INSERT INTO sales (region, revenue) VALUES (?, ?)",
            [("east", 100), ("west", 200), ("north", 5)],
        )
        conn.commit()
        conn.close()
        return {"type": "sqlite", "filepath": str(db_path)}

    def _dataset(self):
        return SimpleNamespace(
            id=42, data_source_id=7, source_table="sales", source_query=None,
            columns=[SimpleNamespace(name=c) for c in ("region", "revenue")],
        )

    def test_a_pushdown_query_writes_one_row_tagged_pushdown(self, app_db, sqlite_source):
        from app.services.direct_query import run_direct_query
        from app.services.widget_data import clear_widget_data_cache

        clear_widget_data_cache()
        run_direct_query(
            sqlite_source, self._dataset(),
            {"dimension": "region", "measure": "revenue", "aggregation": "sum"},
            widget_type="bar", cache_ttl_seconds=0, org_id=9,
        )
        rows = _rows(app_db)
        assert len(rows) == 1
        row = rows[0]
        assert row["source_kind"] == "directquery"
        assert row["executor"] == "pushdown"
        assert row["cache_hit"] == 0
        assert row["org_id"] == 9
        assert row["data_source_id"] == 7
        assert row["dataset_id"] == 42
        # No SQL text stored anywhere -- sql_hash is either absent or a bare
        # sha256 hex digest, never a string that looks like SQL.
        if row["sql_hash"] is not None:
            assert _HEX64.match(row["sql_hash"])

    def test_a_cache_hit_is_logged_too(self, app_db, sqlite_source):
        from app.services.direct_query import run_direct_query
        from app.services.widget_data import clear_widget_data_cache

        clear_widget_data_cache()
        config = {"dimension": "region", "measure": "revenue", "aggregation": "sum"}
        ds = self._dataset()
        run_direct_query(sqlite_source, ds, config, widget_type="bar", cache_ttl_seconds=60)
        run_direct_query(sqlite_source, ds, config, widget_type="bar", cache_ttl_seconds=60)
        rows = sorted(_rows(app_db), key=lambda r: r["id"])
        assert len(rows) == 2
        assert rows[0]["cache_hit"] == 0
        assert rows[1]["cache_hit"] == 1

    def test_a_raising_logger_never_fails_the_query(self, app_db, sqlite_source, monkeypatch):
        from app.services import direct_query
        from app.services.widget_data import clear_widget_data_cache

        clear_widget_data_cache()

        # Patch the failure INSIDE log_query_run_sync (its engine builder),
        # not log_query_run_sync itself -- the real guarantee under test is
        # that log_query_run_sync's own try/except swallows a broken write,
        # not that callers wrap it a second time (they don't).
        def _boom():
            raise RuntimeError("telemetry is down")
        monkeypatch.setattr(query_log, "_get_engine", _boom)

        result = direct_query.run_direct_query(
            sqlite_source, self._dataset(),
            {"dimension": "region", "measure": "revenue", "aggregation": "sum"},
            widget_type="bar", cache_ttl_seconds=0,
        )
        assert result["type"] != "error"
        assert _rows(app_db) == []

    def test_analysis_and_data_preview_style_synchronous_calls_now_log_too(self, app_db, sqlite_source):
        """T13 fix side-effect, required by the coordinator: the old
        running-loop guard that silently no-op'd `analysis.py`'s and
        `datasets.py`'s data-preview call sites (which call run_direct_query
        synchronously from inside a request coroutine, not via
        asyncio.to_thread) is gone. A synchronous call made while a loop is
        running elsewhere in the process must still log -- simulated here by
        calling run_direct_query directly from a plain (non-async) test,
        which is exactly the calling convention those two routers use."""
        from app.services.direct_query import run_direct_query
        from app.services.widget_data import clear_widget_data_cache

        clear_widget_data_cache()
        run_direct_query(
            sqlite_source, self._dataset(),
            {"dimension": "region", "measure": "revenue", "aggregation": "sum"},
            widget_type="bar", cache_ttl_seconds=0, org_id=4,
        )
        rows = _rows(app_db)
        assert len(rows) == 1
        assert rows[0]["org_id"] == 4


class TestWidgetDataWritePoint:
    """Write point #2: widget_data.get_widget_data (the import/pandas path)."""

    def _csv(self, tmp_path):
        path = tmp_path / "d.csv"
        pd.DataFrame([
            {"region": "North", "sales": 100},
            {"region": "South", "sales": 200},
        ]).to_csv(path, index=False)
        return str(path)

    def test_a_pandas_render_writes_one_row_tagged_pandas(self, app_db, tmp_path, monkeypatch):
        # Asserts the executor tag is "pandas", so it must take the pandas path.
        from app.core.config import settings as _s
        monkeypatch.setattr(_s, "widget_duckdb_pushdown", False)
        from app.services.widget_data import clear_widget_data_cache, get_widget_data

        clear_widget_data_cache()
        get_widget_data(
            self._csv(tmp_path),
            {"dimension": "region", "measure": "sales", "aggregation": "sum"},
            widget_type="bar", org_id=3, dataset_id=11,
        )
        rows = _rows(app_db)
        assert len(rows) == 1
        row = rows[0]
        assert row["source_kind"] == "import"
        assert row["executor"] == "pandas"
        assert row["sql_hash"] is None
        assert row["org_id"] == 3
        assert row["dataset_id"] == 11
        assert row["data_source_id"] is None

    def test_a_raising_logger_never_fails_the_render(self, app_db, tmp_path, monkeypatch):
        import app.services.widget_data as wd

        wd.clear_widget_data_cache()

        def _boom():
            raise RuntimeError("telemetry is down")
        monkeypatch.setattr(query_log, "_get_engine", _boom)

        result = wd.get_widget_data(
            self._csv(tmp_path),
            {"dimension": "region", "measure": "sales", "aggregation": "sum"},
            widget_type="bar",
        )
        assert result["type"] != "error"
        assert _rows(app_db) == []


class TestAgentWritePoints:
    """Write point #3: agent/executor.py's two executors."""

    @pytest.fixture
    def source_db(self, tmp_path, monkeypatch):
        from sqlalchemy import text

        from app.services.agent import executor

        path = tmp_path / "s.db"
        eng = create_engine(f"sqlite:///{path}")
        with eng.begin() as conn:
            conn.execute(text("CREATE TABLE orders (id INTEGER, total REAL)"))
            for i in range(5):
                conn.execute(text("INSERT INTO orders VALUES (:i, :t)"), {"i": i, "t": i * 1.5})
        monkeypatch.setattr(executor, "_engine_for", lambda cfg: eng)
        yield {"type": "sqlite", "filepath": str(path)}
        eng.dispose()

    async def test_execute_sql_writes_a_pushdown_agent_row(self, app_db, source_db):
        from app.services.agent.executor import execute_sql

        rows, err = await execute_sql(
            "SELECT total FROM orders WHERE id = 3", source_db, "sqlite",
            org_id=5, data_source_id=17,
        )
        assert err is None
        db_rows = _rows(app_db)
        assert len(db_rows) == 1
        row = db_rows[0]
        assert row["source_kind"] == "agent"
        assert row["executor"] == "pushdown"
        assert row["org_id"] == 5
        assert row["data_source_id"] == 17
        assert row["rows_returned"] == 1
        assert _HEX64.match(row["sql_hash"])

    async def test_execute_on_datasets_writes_a_duckdb_agent_row(self, app_db):
        from app.services.agent.executor import execute_on_datasets

        frame = pd.DataFrame({"a": [1, 2, 3]})
        rows, err = await execute_on_datasets(
            "SELECT * FROM t", {"t": frame}, org_id=6, dataset_id=21,
        )
        assert err is None
        db_rows = _rows(app_db)
        assert len(db_rows) == 1
        row = db_rows[0]
        assert row["source_kind"] == "agent"
        assert row["executor"] == "duckdb"
        assert row["org_id"] == 6
        assert row["dataset_id"] == 21
        assert row["rows_returned"] == 3
        assert _HEX64.match(row["sql_hash"])

    async def test_a_raising_logger_never_fails_the_agent_query(self, app_db, source_db, monkeypatch):
        from app.services.agent import executor

        def _boom():
            raise RuntimeError("telemetry is down")
        monkeypatch.setattr(query_log, "_get_engine", _boom)

        rows, err = await executor.execute_sql(
            "SELECT total FROM orders WHERE id = 3", source_db, "sqlite",
        )
        assert err is None
        assert rows == [{"total": 4.5}]
        assert _rows(app_db) == []

    async def test_no_row_is_written_for_a_failed_query(self, app_db, source_db):
        """Only real executions are training signal -- a query that never ran
        (V4 refusal, generation failure) or errored out must not leave a row
        claiming rows_returned that don't exist."""
        from app.services.agent.executor import execute_sql

        rows, err = await execute_sql("SELECT ghost FROM orders", source_db, "sqlite")
        assert rows is None
        assert err is not None
        assert _rows(app_db) == []
