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
    from .pipeline_alerts import on_run_finished
    await on_run_finished(session, kind, item_id, status, error)
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
