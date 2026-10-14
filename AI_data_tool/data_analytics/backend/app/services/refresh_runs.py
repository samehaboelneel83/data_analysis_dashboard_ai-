"""Refresh run history: one `RefreshRun` row per dataset refresh or dataflow run.

Pipeline plan, phase 1 (2026-10-03). Before this a scheduled refresh that
failed was logged and forgotten, and nothing kept durations or row counts.

Bookkeeping must never break the work it records: every function here swallows
its own errors and logs them. The run is addressed by ID, not by instance,
because a refresh that fails rolls its session back, which expires every
instance loaded in it.
"""
from __future__ import annotations

import logging
from datetime import datetime

log = logging.getLogger(__name__)

#: A run is "slower than usual" when it takes this many times the median of
#: the item's recent successful runs AND at least SLOW_MIN_MS: a 2-second
#: refresh taking 7 is noise, a 10-minute one taking 35 is news.
SLOW_FACTOR = 3.0
SLOW_MIN_MS = 30_000
#: Successful runs the median is taken over, and the fewest it needs.
SLOW_WINDOW = 10
SLOW_MIN_HISTORY = 3

#: How many runs are kept per item. Older ones are trimmed on each finish, so
#: a dataset refreshed every 5 minutes does not grow the table without bound.
KEEP_PER_ITEM = 200


async def start_run(session, kind: str, item_id: int, org_id: int | None,
                    trigger: str = "schedule") -> int | None:
    """Record that a run began. Returns its id, or None if recording failed."""
    from ..models.models import RefreshRun
    try:
        run = RefreshRun(kind=kind, item_id=item_id, org_id=org_id, trigger=trigger,
                         status="running", started_at=datetime.utcnow())
        session.add(run)
        await session.commit()
        return run.id
    except Exception as e:  # noqa: BLE001 -- bookkeeping must not break the run
        log.warning("Could not record the start of %s %s: %s", kind, item_id, e)
        try:
            await session.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None


async def finish_run(session, run_id: int | None, status: str, *, rows: int | None = None,
                     error: str | None = None, error_code: str | None = None,
                     checks: list | None = None) -> None:
    """Close a run as ok | failed | skipped | blocked, with its row count or
    error, and the data checks' results when any ran (phase 3)."""
    if run_id is None:
        return
    from sqlalchemy import delete, select
    from ..models.models import RefreshRun
    try:
        run = await session.get(RefreshRun, run_id)
        if run is None:
            return
        now = datetime.utcnow()
        run.status = status
        run.finished_at = now
        run.rows = rows
        run.error = (error or "")[:2000] or None
        run.error_code = error_code
        if checks is not None:
            run.checks = _json_safe(checks)
        started = run.started_at
        if started is not None:
            if started.tzinfo is not None:
                from datetime import timezone
                started = started.astimezone(timezone.utc).replace(tzinfo=None)
            run.duration_ms = max(0, int((now - started).total_seconds() * 1000))
        slow_news = False
        if status == "ok":
            run.metrics, slow_news = await _metrics(session, run)
        # Trim this item's history to the newest KEEP_PER_ITEM runs.
        keep = select(RefreshRun.id).where(
            RefreshRun.kind == run.kind, RefreshRun.item_id == run.item_id
        ).order_by(RefreshRun.id.desc()).limit(KEEP_PER_ITEM)
        keep_ids = [r for (r,) in (await session.execute(keep)).all()]
        if len(keep_ids) >= KEEP_PER_ITEM:
            await session.execute(delete(RefreshRun).where(
                RefreshRun.kind == run.kind, RefreshRun.item_id == run.item_id,
                RefreshRun.id < min(keep_ids)))
        kind, item_id = run.kind, run.item_id
        await session.commit()
    except Exception as e:  # noqa: BLE001 -- bookkeeping must not break the run
        log.warning("Could not record the end of refresh run %s: %s", run_id, e)
        try:
            await session.rollback()
        except Exception:  # noqa: BLE001
            pass
        return
    # Phase 2: a run that changes the item's state -- first failure, or the
    # success that ends a failure -- is announced. Never raises.
    from .pipeline_alerts import on_run_finished, on_slow_run
    await on_run_finished(session, kind, item_id, status, error)
    if slow_news:
        await on_slow_run(session, kind, item_id, run_id)
    if status == "ok":
        # Phase 4: whatever is set to run after this data now has new input.
        from .pipeline_deps import flow_outputs, mark_dependents
        if kind == "dataset":
            await mark_dependents(session, item_id)
        elif kind == "dataflow":
            from ..models.models import Dataflow
            flow = await session.get(Dataflow, item_id)
            for out in (await flow_outputs(session, item_id, flow.org_id) if flow else []):
                await mark_dependents(session, out)


async def _metrics(session, run) -> tuple[dict | None, bool]:
    """How fast this successful run went, and whether it was far slower than
    this item's usual (2026-10-10, docs/pipeline/PLAN.md). Returns
    (metrics, announce): announce only the FIRST slow run of a streak."""
    from statistics import median
    from sqlalchemy import select
    from ..models.models import Dataset, RefreshRun
    out: dict = {}
    ms = run.duration_ms or 0
    if run.rows is not None and ms > 0:
        out["rows_per_sec"] = round(run.rows / (ms / 1000))
    if run.kind == "dataset":
        ds = await session.get(Dataset, run.item_id)
        if ds is not None and ds.file_size:
            out["file_mb"] = round(ds.file_size / 1_000_000, 2)
    prev = (await session.execute(
        select(RefreshRun).where(RefreshRun.kind == run.kind, RefreshRun.item_id == run.item_id,
                                 RefreshRun.status == "ok", RefreshRun.id < run.id,
                                 RefreshRun.duration_ms.is_not(None))
        .order_by(RefreshRun.id.desc()).limit(SLOW_WINDOW))).scalars().all()
    announce = False
    if len(prev) >= SLOW_MIN_HISTORY:
        usual = median(r.duration_ms for r in prev)
        if usual > 0 and ms >= SLOW_MIN_MS and ms > SLOW_FACTOR * usual:
            out["slow"] = {"median_ms": int(usual), "times": round(ms / usual, 1)}
            announce = not ((prev[0].metrics or {}).get("slow"))
    return (out or None), announce


def _json_safe(value):
    """Check results carry pandas/numpy scalars in their samples; a JSON
    column wants plain ones."""
    import json
    return json.loads(json.dumps(value, default=str))


async def reap_running(session) -> int:
    """At startup, close runs a restart left `running`: none survived it."""
    from sqlalchemy import select
    from ..models.models import RefreshRun
    rows = (await session.execute(
        select(RefreshRun).where(RefreshRun.status == "running"))).scalars().all()
    for r in rows:
        r.status = "failed"
        r.error = "Interrupted by a server restart"
        r.error_code = "interrupted"
        r.finished_at = r.finished_at or datetime.utcnow()
    if rows:
        await session.commit()
    return len(rows)


async def latest_runs(session, kind: str, ids) -> dict:
    """The newest RefreshRun per item, by item id, in one query."""
    from sqlalchemy import func, select
    from ..models.models import RefreshRun
    ids = list(ids or [])
    if not ids:
        return {}
    newest = (select(RefreshRun.item_id, func.max(RefreshRun.id).label("rid"))
              .where(RefreshRun.kind == kind, RefreshRun.item_id.in_(ids))
              .group_by(RefreshRun.item_id).subquery())
    rows = (await session.execute(
        select(RefreshRun).join(newest, RefreshRun.id == newest.c.rid))).scalars().all()
    return {r.item_id: r for r in rows}
