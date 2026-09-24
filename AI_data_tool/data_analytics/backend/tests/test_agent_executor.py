"""V5 and execution: bounded, timed, off the event loop, honest about limits.

The metadata work's hard-won lessons apply verbatim: blocking DB work goes
through to_thread (a stuck query must not freeze the app), a cancelled
statement poisons its connection (invalidate, do not return it), and every
result is capped — an agent that selects a million rows must cost a LIMIT,
not an OOM.
"""
import pytest
from sqlalchemy import create_engine, text

from app.services.agent import executor
from app.services.agent.executor import execute_sql, sanity_check


@pytest.fixture
def source_db(tmp_path, monkeypatch):
    path = tmp_path / "s.db"
    eng = create_engine(f"sqlite:///{path}")
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE orders (id INTEGER, total REAL)"))
        for i in range(20):
            conn.execute(text("INSERT INTO orders VALUES (:i, :t)"),
                         {"i": i, "t": i * 1.5})
    monkeypatch.setattr(executor, "_engine_for", lambda cfg: eng)
    yield {"type": "sqlite", "filepath": str(path)}
    eng.dispose()


class TestExecution:
    async def test_a_query_returns_rows(self, source_db):
        rows, err = await execute_sql("SELECT total FROM orders WHERE id = 3",
                                      source_db, "sqlite")
        assert err is None
        assert rows == [{"total": 4.5}]

    async def test_the_row_cap_is_injected_when_no_limit_present(
            self, source_db, monkeypatch):
        from app.core.config import settings
        monkeypatch.setattr(settings, "agent_row_cap", 5)
        rows, err = await execute_sql("SELECT id FROM orders", source_db, "sqlite")
        assert err is None
        assert len(rows) == 5

    async def test_an_existing_smaller_limit_is_respected(self, source_db):
        rows, _ = await execute_sql("SELECT id FROM orders LIMIT 2",
                                    source_db, "sqlite")
        assert len(rows) == 2

    async def test_an_existing_limit_larger_than_the_cap_is_floored(
            self, source_db, monkeypatch):
        """The cap is a hard ceiling, not merely a default for LIMIT-less
        queries — a model-written LIMIT 99999999 must still be reduced to
        the cap, not passed through."""
        from app.core.config import settings
        monkeypatch.setattr(settings, "agent_row_cap", 5)
        rows, err = await execute_sql("SELECT id FROM orders LIMIT 99999999",
                                      source_db, "sqlite")
        assert err is None
        assert len(rows) == 5

    async def test_a_broken_query_returns_the_error_as_a_value(self, source_db):
        rows, err = await execute_sql("SELECT ghost FROM orders",
                                      source_db, "sqlite")
        assert rows is None
        assert "ghost" in err

    async def test_the_error_keeps_the_first_line_only(self, source_db):
        """Same rule as catalog_sync._error_summary: driver messages append
        the failing SQL, and SQL can carry values."""
        rows, err = await execute_sql("SELECT ghost FROM orders",
                                      source_db, "sqlite")
        assert "\n" not in err


class TestGuardedInterrupt:
    """H2 review finding: timer.cancel() cannot stop a callback already
    running, so a bare `threading.Timer(timeout, conn.interrupt)` can fire
    conn.interrupt() in the window right after a query genuinely finished
    but before cancel() runs — misreporting a success as an interrupt error,
    and racing conn.interrupt() against conn.close(). _guarded_interrupt
    closes that window with a `done` Event, checked directly here without
    any real timing or DuckDB involved."""

    def test_the_callback_interrupts_when_done_was_never_set(self):
        import threading

        from app.services.agent.executor import _guarded_interrupt

        class FakeConn:
            def __init__(self):
                self.interrupt_calls = 0

            def interrupt(self):
                self.interrupt_calls += 1

        conn = FakeConn()
        done = threading.Event()
        callback = _guarded_interrupt(conn, done)
        callback()
        assert conn.interrupt_calls == 1

    def test_the_callback_is_a_no_op_once_done_is_set(self):
        """The success path calls done.set() before conn.close() — if the
        timer thread's callback still fires after that (the race the fix
        closes), it must not touch conn at all."""
        import threading

        from app.services.agent.executor import _guarded_interrupt

        class FakeConn:
            def __init__(self):
                self.interrupt_calls = 0

            def interrupt(self):
                self.interrupt_calls += 1

        conn = FakeConn()
        done = threading.Event()
        callback = _guarded_interrupt(conn, done)
        done.set()
        callback()
        assert conn.interrupt_calls == 0


class TestDatasetWatchdog:
    async def test_a_pathological_query_is_interrupted_not_hung(self, monkeypatch):
        """H2: DuckDB has no statement-timeout pragma, so the executor must
        arm its own watchdog (threading.Timer -> conn.interrupt) before a
        dataset-mode query runs. A cross join of two ~2000-row frames with an
        expensive per-row filter, with the timeout monkeypatched down to 1s,
        must come back as the normal (None, error) tuple well inside the
        test's own bound — never hang until pytest's outer timeout."""
        import time

        import pandas as pd

        from app.core.config import settings
        from app.services.agent.executor import execute_on_datasets

        monkeypatch.setattr(settings, "agent_statement_timeout_s", 1)

        n = 6000
        left = pd.DataFrame({"a": range(n), "x": [i % 97 for i in range(n)]})
        right = pd.DataFrame({"b": range(n), "y": [i % 89 for i in range(n)]})
        frames = {"left_t": left, "right_t": right}

        # A 36M-row cross join with an md5+regex filter per row — cheap
        # arithmetic filters get vectorized fast enough (sub-second) that
        # DuckDB can finish before the 1s watchdog ever fires; hashing +
        # regex forces real per-row CPU work so the interrupt reliably wins.
        sql = (
            "SELECT count(*) FROM left_t, right_t "
            "WHERE regexp_matches(md5(left_t.a::VARCHAR || right_t.b::VARCHAR "
            "|| left_t.x::VARCHAR || right_t.y::VARCHAR), '^0')"
        )

        start = time.monotonic()
        rows, err = await execute_on_datasets(sql, frames)
        elapsed = time.monotonic() - start

        assert rows is None
        assert err is not None
        assert elapsed < 15
        assert "interrupt" in err.lower() or "cancel" in err.lower()


class TestSanity:
    def test_empty_is_flagged(self):
        assert "no rows" in sanity_check([], "total sales")

    def test_a_normal_result_passes(self):
        assert sanity_check([{"n": 42}], "total sales") is None

    def test_all_null_is_flagged(self):
        concern = sanity_check([{"n": None}, {"n": None}], "total sales")
        assert concern is not None

    def test_at_the_row_cap_is_flagged_as_probably_truncated(self, monkeypatch):
        from app.core.config import settings
        monkeypatch.setattr(settings, "agent_row_cap", 3)
        concern = sanity_check([{"n": 1}, {"n": 2}, {"n": 3}], "list orders")
        assert "cap" in concern
