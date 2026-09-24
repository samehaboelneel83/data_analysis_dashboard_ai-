"""T4: the opt-in scheduled eval gate (services/eval_schedule.py).

`run_gate` -- the ~20-minutes-of-LLM-calls piece -- is always monkeypatched
here to a canned result; nothing in this file talks to an LLM or a live
source. What's under test: the flag genuinely gates registration (off means
no task, not a no-op task), a stubbed run writes one `eval_runs` row with the
right fields, and a regression logs at ERROR.
"""
import asyncio
import logging
from datetime import datetime, timedelta

import pytest

from app.core.config import settings
from app.models.models import EvalRun
from app.services import eval_schedule
from sqlalchemy import select


class _FactoryCtx:
    """Wraps one already-open test session as a `session_factory()` --
    matches the pattern test_refresh_schedule.py uses for the same reason:
    the module under test expects `session_factory()` to be an async
    context manager, and the `db_session` fixture is just a session."""
    def __init__(self, session):
        self._s = session

    async def __aenter__(self):
        return self._s

    async def __aexit__(self, *exc):
        return False


def _factory(session):
    return lambda: _FactoryCtx(session)


class TestRegistration:
    def test_disabled_by_default(self):
        assert settings.eval_gate_enabled is False

    async def test_flag_off_registers_no_task(self, monkeypatch):
        monkeypatch.setattr(settings, "eval_gate_enabled", False)
        task = eval_schedule.maybe_create_task(lambda: None)
        assert task is None

    async def test_flag_on_registers_a_task(self, monkeypatch):
        monkeypatch.setattr(settings, "eval_gate_enabled", True)
        # A real loop would sleep for TICK_SECONDS before doing anything, so
        # creating (and then cancelling) it is safe here -- it never reaches
        # the gate call within this test.
        task = eval_schedule.maybe_create_task(lambda: None)
        try:
            assert task is not None
        finally:
            task.cancel()
            try:
                await task
            except (Exception, asyncio.CancelledError):
                pass


class TestRunOnce:
    async def test_stubbed_gate_writes_an_eval_runs_row(self, db_session, monkeypatch):
        canned = {"accuracy": 0.9, "passed": True, "detail": {"summary": {"accuracy": 0.9}}}

        called = {}

        def stub(source_id, min_accuracy):
            called["source_id"] = source_id
            called["min_accuracy"] = min_accuracy
            return canned

        monkeypatch.setattr(eval_schedule, "run_gate", stub)
        monkeypatch.setattr(settings, "eval_gate_source_id", 7)
        monkeypatch.setattr(settings, "eval_gate_min_accuracy", 0.5)

        await eval_schedule.run_eval_gate_once(_factory(db_session))

        assert called == {"source_id": 7, "min_accuracy": 0.5}
        rows = (await db_session.execute(select(EvalRun))).scalars().all()
        assert len(rows) == 1
        row = rows[0]
        assert row.accuracy == 0.9
        assert row.passed is True
        assert row.detail == canned["detail"]
        assert row.started_at is not None
        assert row.finished_at is not None

    async def test_regression_logs_at_error(self, db_session, monkeypatch, caplog):
        monkeypatch.setattr(eval_schedule, "run_gate",
                            lambda source_id, min_accuracy: {
                                "accuracy": 0.2, "passed": False,
                                "detail": {"summary": {"accuracy": 0.2}}})
        monkeypatch.setattr(settings, "eval_gate_source_id", 1)
        monkeypatch.setattr(settings, "eval_gate_min_accuracy", 0.5)

        with caplog.at_level(logging.ERROR, logger="app.services.eval_schedule"):
            await eval_schedule.run_eval_gate_once(_factory(db_session))

        assert any("REGRESSION" in r.message for r in caplog.records)
        rows = (await db_session.execute(select(EvalRun))).scalars().all()
        assert rows[0].passed is False

    async def test_a_crashing_gate_still_writes_a_row_and_never_raises(
            self, db_session, monkeypatch, caplog):
        def boom(source_id, min_accuracy):
            raise RuntimeError("source unreachable")

        monkeypatch.setattr(eval_schedule, "run_gate", boom)
        monkeypatch.setattr(settings, "eval_gate_source_id", 1)
        monkeypatch.setattr(settings, "eval_gate_min_accuracy", 0.5)

        with caplog.at_level(logging.ERROR, logger="app.services.eval_schedule"):
            await eval_schedule.run_eval_gate_once(_factory(db_session))  # must not raise

        rows = (await db_session.execute(select(EvalRun))).scalars().all()
        assert len(rows) == 1
        assert rows[0].passed is False
        assert rows[0].accuracy is None


class TestDueCalculation:
    async def test_never_run_is_due_immediately(self, db_session):
        last = await eval_schedule._last_started_at(_factory(db_session))
        assert last is None

    async def test_a_recent_run_is_not_due(self, db_session):
        db_session.add(EvalRun(started_at=datetime.utcnow() - timedelta(hours=1),
                               finished_at=datetime.utcnow(), accuracy=0.9,
                               passed=True, detail={}))
        await db_session.commit()

        last = await eval_schedule._last_started_at(_factory(db_session))
        now = datetime.utcnow()
        assert last is not None
        assert (now - last) < timedelta(minutes=eval_schedule.EVAL_GATE_INTERVAL_MINUTES)

    async def test_an_old_run_is_due_again(self, db_session):
        db_session.add(EvalRun(
            started_at=datetime.utcnow() - timedelta(minutes=eval_schedule.EVAL_GATE_INTERVAL_MINUTES + 5),
            finished_at=datetime.utcnow(), accuracy=0.9, passed=True, detail={}))
        await db_session.commit()

        last = await eval_schedule._last_started_at(_factory(db_session))
        now = datetime.utcnow()
        assert (now - last) >= timedelta(minutes=eval_schedule.EVAL_GATE_INTERVAL_MINUTES)
