"""A live source that runs short of memory is retried once, then reported as
busy -- never as "could not reach the data source" (HR re-test, 2026-10-01:
Postgres "could not resize shared memory segment" under two parallel reads)."""
import pytest
from sqlalchemy.exc import OperationalError

from app.services import direct_query as dq


class _PgErr(Exception):
    def __init__(self, msg, code):
        super().__init__(msg)
        self.pgcode = code


def _op(msg, code=None):
    return OperationalError("SELECT 1", {}, _PgErr(msg, code))


def test_resource_exhaustion_detected_by_sqlstate_and_text():
    assert dq.is_resource_exhaustion(_op("whatever", "53100"))
    assert dq.is_resource_exhaustion(_op('could not resize shared memory segment "/PostgreSQL.1"'))
    assert not dq.is_resource_exhaustion(_op("connection refused", "08001"))


def test_busy_is_still_a_source_unavailable():
    assert issubclass(dq.SourceBusy, dq.SourceUnavailable)


def test_run_direct_query_retries_once_then_succeeds(monkeypatch):
    calls = []

    def inner(*a, **k):
        calls.append(1)
        if len(calls) == 1:
            raise _op("No space left on device", "53100")
        return {"rows": []}

    monkeypatch.setattr(dq, "_run_direct_query_inner", inner)
    monkeypatch.setattr(dq.time, "sleep", lambda s: None)
    assert dq.run_direct_query({}, None, {}) == {"rows": []}
    assert len(calls) == 2


def test_run_direct_query_reports_busy_after_second_failure(monkeypatch):
    def inner(*a, **k):
        raise _op("No space left on device", "53100")

    monkeypatch.setattr(dq, "_run_direct_query_inner", inner)
    monkeypatch.setattr(dq.time, "sleep", lambda s: None)
    with pytest.raises(dq.SourceBusy):
        dq.run_direct_query({}, None, {})


def test_connection_failure_is_not_retried(monkeypatch):
    calls = []

    def inner(*a, **k):
        calls.append(1)
        raise _op("connection refused", "08001")

    monkeypatch.setattr(dq, "_run_direct_query_inner", inner)
    with pytest.raises(dq.SourceUnavailable) as ei:
        dq.run_direct_query({}, None, {})
    assert not isinstance(ei.value, dq.SourceBusy)
    assert len(calls) == 1


def test_the_retry_runs_with_parallel_workers_off(monkeypatch):
    """HR re-test 2026-10-01: retrying the same parallel plan ran out of
    shared memory again. The retry now switches parallel workers off."""
    from app.services import engines
    seen = []

    def inner(*a, **k):
        seen.append(engines._NO_PARALLEL.get())
        if len(seen) == 1:
            raise _op("could not resize shared memory segment", "53100")
        return {"rows": []}

    monkeypatch.setattr(dq, "_run_direct_query_inner", inner)
    monkeypatch.setattr(dq.time, "sleep", lambda s: None)
    dq.run_direct_query({}, None, {})
    assert seen == [False, True]
    assert engines._NO_PARALLEL.get() is False      # restored afterwards


def test_the_switch_sets_local_on_each_transaction():
    from sqlalchemy import create_engine
    from app.services import engines
    eng = create_engine("sqlite://")
    sent = []
    from sqlalchemy import event

    @event.listens_for(eng, "before_cursor_execute")
    def _rec(conn, cursor, statement, *a):  # noqa: ANN001
        sent.append(statement)
    # sqlite has no such setting; record it instead of running it
    orig = eng.dialect.do_execute
    eng.dialect.do_execute = lambda cursor, statement, params, context=None: (
        None if statement.startswith("SET LOCAL") else orig(cursor, statement, params, context))
    engines._install_parallel_switch(eng)
    with eng.connect() as c:
        c.exec_driver_sql("SELECT 1")
    assert not any(s.startswith("SET LOCAL") for s in sent)
    with engines.parallel_workers_off():
        with eng.connect() as c:
            c.exec_driver_sql("SELECT 1")
    assert any(s.startswith("SET LOCAL max_parallel_workers_per_gather = 0") for s in sent)
