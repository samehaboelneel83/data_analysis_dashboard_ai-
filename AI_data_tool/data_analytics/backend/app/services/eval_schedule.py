"""T4: an OPT-IN, in-process nightly stand-in for a real CI accuracy gate.

This is NOT continuous integration. There is no CI job wired to it, nothing
blocks a merge on its result, and it runs against whatever `agent_runs` the
live agent produces overnight, not a hermetic build. It exists only so a
deployment that wants a recurring accuracy signal can opt into one without
standing up a separate CI pipeline -- flip `settings.eval_gate_enabled` on
and point `settings.eval_gate_source_id` at a data source with a golden set
worth trusting. Off by default (`eval_gate_enabled=False`): a real run is
~20 minutes of live LLM calls (`evals.run_gate`'s ask loop, one golden
question at a time -- see that module), and that cost must be an explicit
per-deployment choice, never a surprise on boot.

Registration mirrors `services/refresh_scheduler.py`'s in-process pattern
(`maybe_create_task`, called from `main.py`'s lifespan) but runs as its own
loop rather than folding into that one -- a stuck 20-minute gate run must
never delay dataset refreshes or delivery ticks that share the other loop's
`TICK_SECONDS`.

The actual gate call (`run_gate`) is synchronous end-to-end (it wraps
`evals.run_gate`'s own `asyncio.run()` calls, the same thing the CLI does)
and is always invoked through `asyncio.to_thread` -- never awaited directly
-- so ~20 minutes of blocking work can never stall the event loop that is
also serving requests. `run_gate` is a module-level function specifically so
tests can monkeypatch `eval_schedule.run_gate` to a canned result and never
touch the LLM.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select

from ..core.config import settings

log = logging.getLogger(__name__)

# How often the loop wakes to check whether a nightly run is due. Independent
# of the nightly cadence itself (EVAL_GATE_INTERVAL_MINUTES) -- this only
# bounds how late a due run can start.
TICK_SECONDS = 3600

# "Nightly" as an elapsed-time floor since the last run STARTED, checked
# against `eval_runs.started_at` -- simpler than a calendar/cron spec, and a
# 20-minute run is dominated by the interval either way.
EVAL_GATE_INTERVAL_MINUTES = 24 * 60

# Where the nightly gate's golden set lives. Not a setting: `--golden` is a
# CLI convenience for ad hoc runs (evals/run_gate.py), but the scheduled job
# always exercises the same fixed set, so drift between deployments (someone
# quietly pointing production at an easier golden file) can't hide a real
# regression.
GOLDEN_PATH = "evals/golden/maps.jsonl"


def run_gate(source_id: int, min_accuracy: float) -> dict:
    """The real gate, called synchronously -- this IS `evals.run_gate`'s
    ask-loop-then-score pipeline, invoked in-process instead of via the CLI's
    subprocess. Talks to the live agent over HTTP and to the source directly,
    exactly like `python -m evals.run_gate` does.

    Returns {"accuracy": float, "passed": bool, "detail": {...}}. Never
    raises for a scoring failure (evaluate()/run_ask_loop already swallow
    per-question errors into "wrong"); a raised exception here means
    something is structurally broken (bad source id, unreadable golden file)
    and is left for the caller to catch.
    """
    from evals.run_gate import (_source_cfg, load_golden, make_executor,
                                operational_summary, run_ask_loop, score)

    golden = load_golden(GOLDEN_PATH)
    ask_results = asyncio.run(run_ask_loop(golden, source_id))
    cfg = asyncio.run(_source_cfg(source_id))
    execute = make_executor(cfg)
    scored = score(ask_results, execute)
    op = operational_summary(ask_results)
    accuracy = scored.get("accuracy", 0.0) or 0.0
    return {"accuracy": accuracy, "passed": accuracy >= min_accuracy,
            "detail": {"summary": scored, "operational": op}}


async def run_eval_gate_once(session_factory) -> None:
    """One full nightly run: call the gate off-thread, write one `eval_runs`
    row, log loudly on regression. Never raises -- a broken gate run must not
    take down the scheduler loop, only be visible in the row it (fails to)
    write and the ERROR it logs."""
    from ..models.models import EvalRun

    started_at = datetime.utcnow()
    try:
        result = await asyncio.to_thread(
            run_gate, settings.eval_gate_source_id, settings.eval_gate_min_accuracy)
    except Exception as e:  # noqa: BLE001 - see docstring
        log.exception("Scheduled eval gate crashed")
        result = {"accuracy": None, "passed": False, "detail": {"error": str(e)}}
    finished_at = datetime.utcnow()

    async with session_factory() as session:
        session.add(EvalRun(started_at=started_at, finished_at=finished_at,
                            accuracy=result.get("accuracy"),
                            passed=result.get("passed"),
                            detail=result.get("detail")))
        await session.commit()

    if not result.get("passed"):
        log.error(
            "Scheduled eval gate REGRESSION: accuracy=%s below min_accuracy=%s "
            "(source_id=%s). This is a nightly stand-in, not CI -- nothing was "
            "blocked; someone should look at this.",
            result.get("accuracy"), settings.eval_gate_min_accuracy,
            settings.eval_gate_source_id)


async def _last_started_at(session_factory) -> datetime | None:
    from ..models.models import EvalRun

    async with session_factory() as session:
        return (await session.execute(
            select(EvalRun.started_at).order_by(EvalRun.id.desc()).limit(1)
        )).scalar_one_or_none()


async def run_eval_schedule(session_factory) -> None:
    """Wake every TICK_SECONDS; run the gate once when a nightly interval has
    elapsed since the last run STARTED (never-run counts as due). Never-die,
    same contract as refresh_scheduler.run_scheduler: one bad tick is logged
    and swallowed, the loop keeps ticking."""
    while True:
        try:
            await asyncio.sleep(TICK_SECONDS)
            now = datetime.utcnow()
            last = await _last_started_at(session_factory)
            if last is None or (now - last) >= timedelta(minutes=EVAL_GATE_INTERVAL_MINUTES):
                await run_eval_gate_once(session_factory)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 - a bad tick must not kill the loop
            log.warning("Eval gate scheduler tick failed: %s", e)


def maybe_create_task(session_factory) -> "asyncio.Task | None":
    """Registration entry point for main.py's lifespan -- returns a running
    task only when `settings.eval_gate_enabled` is on, so the flag being off
    (the default) means literally no task, not a task that immediately no-ops.
    Kept as a plain function, separate from the app's lifespan, so the
    on/off decision is unit-testable without booting the whole app."""
    if not settings.eval_gate_enabled:
        return None
    return asyncio.create_task(run_eval_schedule(session_factory))
