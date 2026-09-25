"""Scheduled refresh of import-mode datasets.

The design constraint that shapes this module: the scheduler runs *in-process*, so
there is one of it per uvicorn worker. Without a guard, four workers means four
simultaneous refreshes of the same dataset, each overwriting the same CSV while the
others read it. Rather than add a scheduler dependency with its own job store, this
takes a Postgres advisory lock per dataset — the database is already the one thing
every worker shares.

Advisory locks are Postgres-only. On any other dialect (SQLite in tests, or a
single-process dev run) the lock is skipped, which is safe precisely because those
deployments have one worker. That is stated rather than silently assumed.

The due-calculation and the lock key are pure functions so they can be tested
directly; the loop that calls them is kept thin on purpose.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text

from sqlalchemy.orm.attributes import flag_modified
from ..models.models import Dataflow, DataSource, Dataset, DatasetColumn

log = logging.getLogger(__name__)

# How often the loop wakes to look for work. Independent of any dataset's interval —
# a dataset scheduled every 15 minutes is refreshed on the first tick at or after
# its due time, so this bounds the lateness rather than the frequency.
TICK_SECONDS = 60

# Floor on a dataset's interval. A 1-minute schedule against a production database
# is a self-inflicted denial of service.
MIN_INTERVAL_MINUTES = 5

# A tick processes at most this many due items per category (schedules,
# alerts). After downtime everything is due at once; the cap turns that
# stampede into a drain over a few ticks, oldest-served-first.
MAX_ITEMS_PER_TICK = 25

# How many schedule/alert items run concurrently within a tick. Each gets its
# own session (an AsyncSession is not concurrency-safe) and takes its
# advisory lock on that session's connection, which is what makes the lock
# actually held for the duration of the work.
ITEM_CONCURRENCY = 3

# Backoff after consecutive failures, in minutes, indexed by attempt count.
# Past the end, the last value repeats -- an item that has failed six times
# is tried daily, not abandoned, because the fix is usually on the other side
# (a database comes back, a credential is rotated) and nobody wants to hunt
# for a "re-enable" button afterwards.
#
# Before this, failure had no memory at all: the item's timestamp advanced
# whether or not the work succeeded, so a source that had been unreachable
# for a week was retried exactly as eagerly as one that failed once.
BACKOFF_MINUTES = (5, 15, 60, 240, 720, 1440)


def backoff_minutes(attempts: int) -> int:
    """Minutes to wait after `attempts` consecutive failures (1-based)."""
    if attempts < 1:
        attempts = 1
    return BACKOFF_MINUTES[min(attempts, len(BACKOFF_MINUTES)) - 1]


async def _failure_row(session, kind: str, item_id: int):
    from ..models.models import ScheduleFailure
    return (await session.execute(
        select(ScheduleFailure).where(ScheduleFailure.kind == kind,
                                      ScheduleFailure.item_id == item_id)
    )).scalars().first()


async def in_backoff(session, kind: str, item_id: int, now: datetime) -> bool:
    """True when this item failed recently and its next attempt is not due.

    Checked in addition to the item's own schedule, never instead of it: a
    healthy item has no row here and is unaffected.
    """
    row = await _failure_row(session, kind, item_id)
    if row is None or row.next_attempt_at is None:
        return False
    return _as_utc_naive(now) < _as_utc_naive(row.next_attempt_at)


async def record_failure(session, kind: str, item_id: int, error: str,
                         now: datetime | None = None) -> int:
    """Count one failure and schedule the retry. Returns the attempt count."""
    from ..models.models import ScheduleFailure

    now = now or datetime.utcnow()
    row = await _failure_row(session, kind, item_id)
    if row is None:
        row = ScheduleFailure(kind=kind, item_id=item_id, attempts=0,
                              first_failed_at=now)
        session.add(row)
    row.attempts = (row.attempts or 0) + 1
    row.last_error = (error or "")[:2000] or None
    row.next_attempt_at = now + timedelta(minutes=backoff_minutes(row.attempts))
    row.updated_at = now
    await session.commit()
    log.warning("Scheduler %s %s failed (attempt %s), next try in %s min: %s",
                kind, item_id, row.attempts, backoff_minutes(row.attempts), error)
    return row.attempts


async def clear_failure(session, kind: str, item_id: int) -> None:
    """Forget a resolved failure. A healthy install carries no rows at all."""
    row = await _failure_row(session, kind, item_id)
    if row is not None:
        await session.delete(row)
        await session.commit()


async def reap_stuck_sync_runs(session) -> int:
    """Mark metadata sync runs that a restart orphaned.

    `run_sync_background` is a detached task owned by no request. If the
    process dies mid-run its `SyncRun` row keeps saying `running` FOREVER --
    the UI shows a sync in progress that nothing is progressing, and the next
    sync of that source looks like a duplicate. Nothing cleaned these up.

    Called once at startup, where "still running" is impossible by
    definition: no task from the previous process survived it.
    """
    from ..models.models import SyncRun

    rows = (await session.execute(
        select(SyncRun).where(SyncRun.status == "running")
    )).scalars().all()
    for row in rows:
        row.status = "failed"
        if hasattr(row, "error"):
            row.error = "Interrupted by a server restart"
        if hasattr(row, "finished_at") and row.finished_at is None:
            row.finished_at = datetime.utcnow()
    if rows:
        await session.commit()
        log.warning("Reaped %s metadata sync run(s) left running by a restart",
                    len(rows))
    return len(rows)


async def reap_orphaned_failures(session) -> int:
    """Delete `kind="dataset"` failure rows whose dataset no longer exists.

    ScheduleFailure is keyed (kind, item_id) with no foreign key, so a dataset
    deleted before dataset_cleanup existed left its row behind, and so does
    any delete that bypasses the routers. Nothing reads an orphan (the tick
    scans datasets), but nothing removed them either. Called once at startup.
    """
    from sqlalchemy import delete
    from ..models.models import Dataset, ScheduleFailure
    live = select(Dataset.id)
    result = await session.execute(
        delete(ScheduleFailure).where(ScheduleFailure.kind == "dataset",
                                      ScheduleFailure.item_id.not_in(live)))
    if result.rowcount:
        # Some drivers report rowcount as -1 when it cannot be determined;
        # treat anything below 1 as "unknown", not a negative count.
        await session.commit()
        count = result.rowcount if result.rowcount > 0 else 0
        if count:
            log.warning("Reaped %s scheduler failure row(s) for deleted datasets", count)
        return count
    return 0


CALENDAR_INTERVAL_BOUNDS = {"daily": 24 * 60, "weekly": 7 * 24 * 60, "monthly": 28 * 24 * 60}


def calendar_spec(recipients) -> dict | None:
    """The reserved calendar entry riding in the recipients JSON list.

    recipients gained calendar duty the same way column_meta carries reserved
    __keys: the table cannot gain a column (create_all never ALTERs deployed
    tables), and valid_recipients() already ignores every non-string entry,
    so a dict entry is invisible to delivery and free to carry settings."""
    for r in recipients or []:
        if isinstance(r, dict) and isinstance(r.get("__calendar__"), dict):
            return r["__calendar__"]
    return None


def _to_zone(dt: datetime, tz_name: str | None) -> datetime:
    """`dt` is UTC-naive; return the equivalent naive wall-clock time in
    `tz_name`, or `dt` unchanged when `tz_name` is falsy (UTC, the historical
    default)."""
    if not tz_name:
        return dt
    from zoneinfo import ZoneInfo
    return dt.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz_name)).replace(tzinfo=None)


def _from_zone(dt_local: datetime, tz_name: str | None) -> datetime:
    """Inverse of `_to_zone`: a naive wall-clock time in `tz_name` back to
    naive UTC, unchanged when `tz_name` is falsy."""
    if not tz_name:
        return dt_local
    from zoneinfo import ZoneInfo
    return dt_local.replace(tzinfo=ZoneInfo(tz_name)).astimezone(timezone.utc).replace(tzinfo=None)


def _last_occurrence(spec: dict, now: datetime, tz_name: str | None = None) -> datetime | None:
    """The most recent scheduled occurrence at or before `now` (UTC in, UTC out).

    Clock times are interpreted in `tz_name` (an IANA zone) when given, UTC
    otherwise -- the historical, still-default behaviour for every schedule
    that predates T3 (NULL timezone). The wall-clock arithmetic below is done
    entirely in the target zone's local time, then converted back to UTC at
    the end, so a schedule set for "09:00 Asia/Riyadh" fires at the same
    local wall-clock moment year-round regardless of DST elsewhere.
    """
    try:
        hour, minute = int(spec.get("hour", 9)), int(spec.get("minute", 0))
        kind = spec.get("kind")
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None
        local_now = _to_zone(now, tz_name)
        if kind == "daily":
            occ = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            occ = occ if occ <= local_now else occ - timedelta(days=1)
        elif kind == "weekly":
            weekday = int(spec.get("weekday", 0))  # Monday = 0
            occ = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            occ -= timedelta(days=(local_now.weekday() - weekday) % 7)
            occ = occ if occ <= local_now else occ - timedelta(days=7)
        elif kind == "monthly":
            monthday = min(max(int(spec.get("monthday", 1)), 1), 28)  # 29-31 skip months
            occ = local_now.replace(day=monthday, hour=hour, minute=minute, second=0, microsecond=0)
            if occ > local_now:
                first = local_now.replace(day=1) - timedelta(days=1)  # last day of previous month
                occ = first.replace(day=monthday, hour=hour, minute=minute, second=0, microsecond=0)
        else:
            return None
        return _from_zone(occ, tz_name)
    except (TypeError, ValueError, LookupError):
        # LookupError covers zoneinfo.ZoneInfoNotFoundError (a KeyError subclass) --
        # an unknown zone name is validated at write time (422), so this is a
        # last-resort guard, not the normal path.
        return None


def is_calendar_due(spec: dict, last_run_at: datetime | None, now: datetime, tz_name: str | None = None) -> bool:
    """Due when a scheduled occurrence has passed that the last run predates."""
    occ = _last_occurrence(spec, _as_utc_naive(now), tz_name)
    if occ is None:
        return False
    return last_run_at is None or _as_utc_naive(last_run_at) < occ


def schedule_is_due(sched, now: datetime) -> bool:
    """Calendar semantics when the schedule carries them; interval otherwise.

    `sched.timezone` only affects the calendar path -- interval schedules
    (`is_due`) are elapsed-time-based and have no wall-clock to localize."""
    spec = calendar_spec(sched.recipients)
    if spec is not None:
        return is_calendar_due(spec, sched.last_run_at, now, getattr(sched, "timezone", None))
    return is_due(sched.interval_minutes, sched.last_run_at, now)


def _oldest_first(items, stamp_attr: str):
    """Fairness order for a capped tick: never-run items first, then the item
    that has waited longest since its last run."""
    return sorted(items, key=lambda x: (getattr(x, stamp_attr) is not None,
                                        _as_utc_naive(getattr(x, stamp_attr)) or datetime.min))


def _as_utc_naive(dt: datetime | None) -> datetime | None:
    """Postgres timestamptz columns come back tz-AWARE while the loop's clock is
    naive utcnow() -- the same live-only TypeError that once broke share-link
    expiry (SQLite tests cannot catch it). Every comparison in this module goes
    through this normalizer."""
    if dt is None:
        return None
    return dt if dt.tzinfo is None else dt.astimezone(timezone.utc).replace(tzinfo=None)


def is_due(interval_minutes: int | None, last_refreshed_at: datetime | None, now: datetime) -> bool:
    """True when a dataset's next scheduled refresh has come around.

    A dataset that has never been refreshed is due immediately — otherwise it would
    sit idle for a full interval after being scheduled, which reads as broken to
    whoever just set it up.
    """
    if not interval_minutes or interval_minutes <= 0:
        return False
    if last_refreshed_at is None:
        return True
    return _as_utc_naive(now) - _as_utc_naive(last_refreshed_at) >= timedelta(minutes=interval_minutes)


def due_datasets(datasets, now: datetime) -> list:
    """Filter to datasets that are both eligible for scheduling and currently due.

    DirectQuery datasets are excluded because they read the live source on every
    query — there is no cached file to refresh.

    TWO kinds are eligible, and they are refreshed by different means:

      * a SOURCE-backed dataset re-reads its connection. It needs a
        data_source_id and a recorded table/query, or the refresh would fail
        every tick.
      * a DERIVED dataset (built by `POST /datasets/{id}/materialize`) re-runs
        the recipe stored in `__derived_from__` instead. It has no connection at
        all, which is why the source checks below are skipped for it -- this is
        what makes a transformation keep itself current rather than waiting for
        somebody to press Rebuild.
    """
    from .prep import derived_from_of

    out = []
    for ds in datasets:
        if ds.mode == "directquery":
            continue
        derived = derived_from_of(ds) is not None
        if not derived:
            if not ds.data_source_id:
                continue
            if not (ds.source_table or ds.source_query):
                continue
        if is_due(ds.refresh_interval_minutes, ds.last_refreshed_at, now):
            out.append(ds)
    return out


def advisory_lock_key(dataset_id: int) -> int:
    """A stable per-dataset key for pg_try_advisory_lock, which takes a bigint.

    Derived by hashing rather than using the id directly so these keys cannot
    collide with an unrelated advisory lock elsewhere that happens to use small
    integers. Folded into signed 64-bit range, which is what the function accepts.
    """
    digest = hashlib.sha256(f"datalytics.dataset.refresh.{dataset_id}".encode()).digest()
    unsigned = int.from_bytes(digest[:8], "big")
    return unsigned - 2**63


async def _try_lock(session, key: int) -> bool:
    """Take the advisory lock, or report that another worker holds it.

    Returns True on dialects without advisory locks: those are single-process
    deployments, where the lock has nothing to protect against.
    """
    if session.bind.dialect.name != "postgresql":
        return True
    result = await session.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": key})
    return bool(result.scalar())


async def _unlock(session, key: int) -> None:
    if session.bind.dialect.name != "postgresql":
        return
    await session.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})


async def _rebuild_derived(session, ds) -> bool:
    """Re-run a materialized dataset's recipe on its schedule.

    Runs AS ITS BUILDER, not as nobody: `__derived_from__.built_by_user_id`
    records who created it, and the frames are loaded through that identity so
    row-level security is resolved exactly as it was at build time. A scheduled
    run with no identity would be an unfiltered read, which is the same trap
    ReportSchedule avoids by resolving RLS as its creator.

    In practice the refusal in the materialize endpoint means no source can
    carry security rules at all, so this cannot widen anybody's access -- but
    the identity is threaded through anyway, because that refusal is a policy
    that could be relaxed later and this code would silently become wrong.

    Failures are logged and swallowed, like every other scheduled refresh: one
    broken recipe must not stop the loop, and there is no request to answer.
    """
    import asyncio as _asyncio

    from ..models.models import User
    from .ingest import detect_types, load_file
    from .frame_cache import write_parquet_sidecar
    from .prep import apply_prep_steps, derived_from_of, resolve_join_frames
    from .widget_data import apply_rls_filter

    prov = derived_from_of(ds) or {}
    steps = prov.get("steps") or []
    base_id = prov.get("source_dataset_id")
    base = await session.get(Dataset, base_id) if isinstance(base_id, int) else None
    if base is None or base.org_id != ds.org_id or not base.filename:
        log.warning("Scheduled rebuild skipped for dataset %s: source %s is gone",
                    ds.id, base_id)
        # Advanced anyway so a permanently broken recipe retries on its schedule
        # rather than on every tick.
        ds.last_refreshed_at = datetime.utcnow()
        await session.commit()
        return True

    builder = await session.get(User, prov.get("built_by_user_id")) \
        if isinstance(prov.get("built_by_user_id"), int) else None
    if builder is None:
        log.warning("Scheduled rebuild skipped for dataset %s: builder is gone", ds.id)
        ds.last_refreshed_at = datetime.utcnow()
        await session.commit()
        return True

    try:
        from ..core.rls import resolve_denied_columns, resolve_rls_expr
        rls = await resolve_rls_expr(session, builder, base.id)
        denied = await resolve_denied_columns(session, builder, base.id)
        aux = await resolve_join_frames(session, builder, steps)

        def _run():
            frame = load_file(base.filename)
            frame = apply_rls_filter(frame, rls)
            present = [c for c in (denied or []) if c in frame.columns]
            if present:
                frame = frame.drop(columns=present)
            return apply_prep_steps(frame, steps, aux)

        out = await _asyncio.to_thread(_run)

        # Written in place: the dataset keeps its path, so every report and
        # widget pointing at it picks the new rows up with no rewiring.
        await _asyncio.to_thread(lambda: out.to_csv(ds.filename, index=False))
        await _asyncio.to_thread(write_parquet_sidecar, str(ds.filename))
        type_map = await _asyncio.to_thread(detect_types, out)

        ds.row_count = len(out)
        ds.col_count = len(out.columns)
        from pathlib import Path as _Path
        ds.file_size = _Path(ds.filename).stat().st_size

        for c in (await session.execute(
            select(DatasetColumn).where(DatasetColumn.dataset_id == ds.id)
        )).scalars().all():
            await session.delete(c)
        await session.flush()
        for name, dtype in type_map.items():
            session.add(DatasetColumn(
                dataset_id=ds.id, name=name, dtype=dtype,
                missing_pct=round(out[name].isnull().mean() * 100, 2), stats={}))

        meta = dict(ds.column_meta or {})
        from .prep import DERIVED_FROM_KEY
        meta[DERIVED_FROM_KEY] = {**prov, "built_at": datetime.utcnow().isoformat() + "Z",
                                  "built_rows": int(len(out))}
        ds.column_meta = meta
        flag_modified(ds, "column_meta")
    except Exception as e:  # noqa: BLE001 -- never-die, as elsewhere in this loop
        log.warning("Scheduled rebuild failed for dataset %s: %s", ds.id, e)

    ds.last_refreshed_at = datetime.utcnow()
    await session.commit()
    return True


def due_dataflows(flows, now: datetime) -> list:
    """Dataflows whose own interval has come round.

    A dataflow's schedule lives on the DATAFLOW, not on the datasets it
    produces -- that is what "independently scheduled" means, and it is why the
    dataset query above cannot find these: an output's own
    `refresh_interval_minutes` is normally None. One interval drives every
    output, so the set refreshes together rather than each output drifting to
    its own cadence.
    """
    return [f for f in flows
            if is_due(f.refresh_interval_minutes, f.last_run_at, now)]


async def refresh_dataflow(session, flow) -> bool:
    """Re-run one dataflow's recipe into every output it already produced.

    Runs AS THE DATAFLOW'S CREATOR. A scheduled run has nobody at the keyboard,
    and reading the source with no identity would be an unfiltered read -- the
    same stance ReportSchedule takes with its creator and `_rebuild_derived`
    takes with a dataset's recorded builder.

    Never raises: one broken recipe must not stop the loop, and there is no
    request to answer. The failure is recorded on the dataflow itself so it is
    visible in the UI rather than only in a log.
    """
    import asyncio as _asyncio

    from ..models.models import User
    from .prep import DERIVED_FROM_KEY, apply_prep_steps, derived_from_of, resolve_join_frames
    from .frame_cache import write_parquet_sidecar
    from .ingest import detect_types, load_file
    from .widget_data import apply_rls_filter

    now = datetime.utcnow()
    outputs = [d for d in (await session.execute(
        select(Dataset).where(Dataset.org_id == flow.org_id))).scalars().all()
        if (derived_from_of(d) or {}).get("dataflow_id") == flow.id]

    def _finish(status, error=None, rows=None):
        flow.last_run_at, flow.last_run_status = now, status
        flow.last_run_error, flow.last_run_rows = error, rows

    if not outputs:
        # Nothing to write into yet. Advance the clock so a dataflow nobody has
        # run stays quiet instead of retrying on every single tick.
        _finish("skipped", "no outputs yet")
        await session.commit()
        return True

    src = await session.get(Dataset, flow.source_dataset_id) if flow.source_dataset_id else None
    builder = await session.get(User, flow.created_by) if flow.created_by else None
    if src is None or not src.filename or builder is None:
        _finish("failed", "source dataset or creator is gone")
        await session.commit()
        return True

    try:
        from ..core.rls import resolve_denied_columns, resolve_rls_expr
        rls = await resolve_rls_expr(session, builder, src.id)
        denied = await resolve_denied_columns(session, builder, src.id)
        aux = await resolve_join_frames(session, builder, flow.steps or [])

        def _run():
            frame = load_file(src.filename)
            frame = apply_rls_filter(frame, rls)
            present = [c for c in (denied or []) if c in frame.columns]
            if present:
                frame = frame.drop(columns=present)
            return apply_prep_steps(frame, flow.steps or [], aux)

        out = await _asyncio.to_thread(_run)
        type_map = await _asyncio.to_thread(detect_types, out)

        for ds in outputs:
            await _asyncio.to_thread(lambda p=ds.filename: out.to_csv(p, index=False))
            await _asyncio.to_thread(write_parquet_sidecar, str(ds.filename))
            ds.row_count, ds.col_count = len(out), len(out.columns)
            ds.last_refreshed_at = now
            meta = dict(ds.column_meta or {})
            meta[DERIVED_FROM_KEY] = {**(meta.get(DERIVED_FROM_KEY) or {}),
                                      "built_at": now.isoformat() + "Z",
                                      "built_rows": int(len(out))}
            ds.column_meta = meta
            flag_modified(ds, "column_meta")
            for c in (await session.execute(select(DatasetColumn).where(
                    DatasetColumn.dataset_id == ds.id))).scalars().all():
                await session.delete(c)
            await session.flush()
            for name, dtype in type_map.items():
                session.add(DatasetColumn(
                    dataset_id=ds.id, name=name, dtype=dtype,
                    missing_pct=round(out[name].isnull().mean() * 100, 2), stats={}))
        _finish("ok", None, int(len(out)))
    except Exception as e:  # noqa: BLE001 -- never-die, as elsewhere in this loop
        log.warning("Scheduled dataflow %s failed: %s", flow.id, e)
        _finish("failed", str(e)[:500])

    await session.commit()
    return True


async def rescan_insights(session, ds) -> bool:
    """Refresh the shared insight-scan baseline after a dataset refresh.

    "After a refresh" is THE moment for this: the data just changed, so the
    stored scan is stale precisely now, and rescanning here is what lets the
    next reader's NEW/CHANGED badges describe the refresh rather than whichever
    click happened to come first.

    The scheduler has no caller identity, and the shared insights_scan row may
    only ever hold an UNRESTRICTED scan (the AnalysisResult poisoning rule in
    routers/analysis.py). Two consequences, both deliberate:

    * the scan runs with no RLS and no column mask -- that IS the unrestricted
      baseline, the same thing an org admin's click computes;
    * a pipeline with JOIN steps is SKIPPED. Joined frames are secured per
      identity (resolve_join_frames), and every identity available here -- the
      builder, a creator -- can carry rules; a baseline quietly shaped by one
      person's row visibility would poison every reader's badges. The next
      unrestricted click refreshes those datasets' baselines instead.

    Fail-soft like everything in this loop: a scan failure is logged and
    swallowed, never allowed to mark the REFRESH failed."""
    from ..models.models import AnalysisResult
    from .analytics import detect_types, load_file
    from .insights import generate_insights
    from .prep import apply_prep_steps, collect_join_dataset_ids, prep_steps_of
    from .widget_data import apply_calculated_columns

    if not ds.filename or ds.mode == "directquery":
        return False
    steps = prep_steps_of(ds)
    if collect_join_dataset_ids(steps):
        log.debug("Insight rescan skipped for dataset %s: join steps need an identity", ds.id)
        return False

    def _scan():
        df = load_file(ds.filename)
        df = apply_prep_steps(df, steps, {})
        if ds.calculated_columns:
            df = apply_calculated_columns(df, ds.calculated_columns, ds.custom_functions)
        return generate_insights(df, detect_types(df), ds.column_meta or {})

    try:
        result = await asyncio.to_thread(_scan)
        raw = {"findings": result["findings"]}
        from sqlalchemy import select
        row = (await session.execute(select(AnalysisResult).where(
            AnalysisResult.dataset_id == ds.id,
            AnalysisResult.analysis_type == "insights_scan",
        ))).scalar_one_or_none()
        if row:
            row.result = raw
            row.created_at = datetime.utcnow()
        else:
            session.add(AnalysisResult(dataset_id=ds.id,
                                       analysis_type="insights_scan", result=raw))
        await session.commit()
        return True
    except Exception as e:  # noqa: BLE001 -- never-die, and never fail the refresh
        log.warning("Insight rescan failed for dataset %s: %s", ds.id, e)
        return False


async def refresh_one(session, ds: Dataset) -> bool:
    """Refresh a single dataset's cached file. Returns whether it actually ran.

    Failures are logged and swallowed: one unreachable source must not stop the loop
    from refreshing every other dataset, and there is no user request to return an
    error to. `last_refreshed_at` is advanced either way, so a permanently broken
    source is retried on its schedule rather than on every tick.
    """
    from .dataset_refresh import rewrite_dataset_file, write_materialization

    key = advisory_lock_key(ds.id)
    if not await _try_lock(session, key):
        return False
    try:
        from .prep import derived_from_of
        if derived_from_of(ds) is not None:
            return await _rebuild_derived(session, ds)

        is_aggregate = ds.aggregate_of_dataset_id is not None
        if is_aggregate:
            # An aggregate is governed by its SOURCE's rules at read time,
            # which is only sound while the grain carries every column those
            # rules read. A rule added since creation can break that. Reads
            # for that role already fail closed; this refuses to keep
            # rewriting the file and says why, the way every scheduler
            # failure is said, so the Aggregates tab can show it.
            from ..models.models import Role, RowSecurityRule
            from ..services.aggregates import (aggregate_staleness, rls_columns_outside_grain,
                                               uncovered_message)
            rows = (await session.execute(
                select(RowSecurityRule, Role.name).join(Role, Role.id == RowSecurityRule.role_id)
                .where(RowSecurityRule.dataset_id == ds.aggregate_of_dataset_id))).all()
            known = {c.name for c in (await session.execute(
                select(DatasetColumn).where(DatasetColumn.dataset_id == ds.aggregate_of_dataset_id)
            )).scalars().all()}
            bad = rls_columns_outside_grain([r for r, _ in rows], (ds.aggregate_spec or {}).get("grain") or [], known)
            if bad:
                names = {r.role_id: n for r, n in rows}
                msg = uncovered_message(bad, names, when="refresh")
                await record_failure(session, "dataset", ds.id, msg)
                ds.last_refreshed_at = datetime.utcnow()
                await session.commit()
                return True

            # The source may since have grown a report-level filter expression
            # (an aggregate would ignore it) or been re-pointed at a different
            # query (routers/data_sources.py allows narrowing source_table /
            # source_query) -- either would otherwise keep this aggregate
            # summarising the WRONG rows forever with no error, the
            # silent-wrong-number this design exists to avoid. Both checks
            # live in one helper shared with `list_aggregates`, so an
            # unscheduled aggregate (never selected by the tick's own query)
            # shows the identical wording in the Aggregates tab.
            source = await session.get(Dataset, ds.aggregate_of_dataset_id)
            stale = aggregate_staleness(source, ds)
            if stale:
                await record_failure(session, "dataset", ds.id, stale)
                ds.last_refreshed_at = datetime.utcnow()
                await session.commit()
                return True
            # clear_failure is deliberately NOT called here -- it waits until
            # AFTER a successful rewrite below, so a previously recorded
            # failure cannot vanish before the rewrite that follows has
            # actually succeeded.

        src = await session.get(DataSource, ds.data_source_id)
        if src is None:
            return False
        cfg = dict(src.config or {})
        cfg["type"] = src.type
        # E05: the columns something on this dataset names. A rewrite that
        # would drop one is refused before the file is touched, and SAID --
        # recorded like any scheduler failure -- rather than silently breaking
        # every widget that uses it on the next tick.
        from .dataset_refresh import SchemaBreak
        from .dependencies import find_dependents_of
        known = [c.name for c in (await session.execute(
            select(DatasetColumn).where(DatasetColumn.dataset_id == ds.id))).scalars().all()]
        required = {n for n, deps in (await find_dependents_of(session, ds, known)).items() if deps}
        # Passed only when something is required, so a dataset nothing uses
        # makes exactly the call it always made.
        guard = {"required_columns": required} if required else {}
        try:
            df, _type_map = await asyncio.to_thread(
                rewrite_dataset_file, cfg, ds.filename, ds.source_table, ds.source_query, **guard)
            # O3: rewrite_dataset_file is always a full rewrite (no watermark
            # here -- see module docstring), so the manifest kind is "full"
            # and there is no cursor value to carry.
            if ds.filename:
                await write_materialization(
                    session, ds.id, ds.filename, "full", len(df), list(df.columns), None)
        except SchemaBreak as e:
            log.warning("Scheduled refresh refused for dataset %s: %s", ds.id, e)
            await record_failure(session, "dataset", ds.id,
                                 f"Not refreshed: {e}, still used on this dataset. "
                                 "Refresh it by hand to map the new column names.")
            ds.last_refreshed_at = datetime.utcnow()
            await session.commit()
            return True
        except Exception as e:  # noqa: BLE001 - see docstring
            log.warning("Scheduled refresh failed for dataset %s: %s", ds.id, e)
            if is_aggregate:
                # Said, not only logged. run_scheduler clears this item's
                # failure after refresh_one returns unless the item is in
                # backoff; a swallowed error that recorded nothing would
                # leave a prior failure due for retry, and the tick would
                # erase it. Recording puts the item in backoff, keeps the
                # row, and shows the real error in the Aggregates tab.
                await record_failure(session, "dataset", ds.id, f"Refresh failed: {e}")
        else:
            if is_aggregate:
                await clear_failure(session, "dataset", ds.id)
        ds.last_refreshed_at = datetime.utcnow()
        await session.commit()
        # The data just changed; the stored insight baseline describes the OLD
        # data. Still under this dataset's advisory lock, so a user-triggered
        # scan cannot interleave.
        await rescan_insights(session, ds)
        return True
    finally:
        await _unlock(session, key)


async def run_items(session_factory, due_ids: list[int], model,
                    key_offset: int, runner, kind: str = "item") -> None:
    """Run one category's due items concurrently, each in ITS OWN session.

    A shared session must not be used here: an AsyncSession is not
    concurrency-safe under gather, and an advisory lock is held by the
    CONNECTION that takes it -- lock, work and unlock have to share a session
    or the lock protects nothing. The row is re-fetched in that session for
    the same reason: runners mutate and commit it, and a cross-session
    instance would silently not flush. Each item carries its own try/except
    -- one failure never sinks its siblings."""
    sem = asyncio.Semaphore(ITEM_CONCURRENCY)

    async def _one(item_id: int) -> None:
        async with sem:
            try:
                async with session_factory() as s:
                    row = await s.get(model, item_id)
                    if row is None:
                        return
                    key = advisory_lock_key(key_offset + item_id)
                    if await _try_lock(s, key):
                        try:
                            await runner(s, row)
                            await clear_failure(s, kind, item_id)
                        finally:
                            await _unlock(s, key)
            except Exception as e:  # noqa: BLE001 - never-die, per item
                # Counted and backed off, not just logged: a delivery whose
                # SMTP host is wrong should stop being attempted every
                # interval until somebody fixes it.
                try:
                    async with session_factory() as s2:
                        await record_failure(s2, kind, item_id, str(e))
                except Exception:  # noqa: BLE001 - bookkeeping must not raise
                    log.warning("Scheduler item %s/%s failed: %s",
                                model.__name__, item_id, e)

    await asyncio.gather(*[_one(i) for i in due_ids])


async def run_scheduler(session_factory) -> None:
    """Wake every TICK_SECONDS; refresh datasets, run deliveries, check alerts.

    One loop for all three rather than three loops: they share the tick, the
    advisory-lock discipline and the never-die contract, and a second scheduler
    would be a second place for those to drift."""
    from ..models.models import DataAlert, ReportSchedule
    from .alerts import check_alert
    from .delivery import run_schedule

    while True:
        try:
            await asyncio.sleep(TICK_SECONDS)
            now = datetime.utcnow()
            async with session_factory() as session:
                result = await session.execute(
                    select(Dataset).where(Dataset.refresh_interval_minutes.isnot(None))
                )
                # Dataset refreshes stay serial: rewrite_dataset_file is
                # already thread-offloaded and I/O-bound against customer
                # databases; parallel refreshes would multiply that load.
                # Per-item isolation. These two loops ran bare inside the
                # tick's try, so ONE raising dataset skipped every dataset
                # after it -- while schedules and alerts (run_items) were
                # already isolated. Same contract for all four now.
                #
                # Iterating IDS, not instances, for the reason run_items
                # already gives: recovering from a failure means rolling the
                # session back, which EXPIRES every other instance loaded in
                # it. The next `ds.id` would then be lazy IO from a sync
                # attribute access -- MissingGreenlet, thrown out of the loop,
                # which is precisely the tick-killing behaviour being fixed.
                due_ds_ids = [d.id for d in
                              due_datasets(list(result.scalars().all()), now)]
                for ds_id in due_ds_ids:
                    if await in_backoff(session, "dataset", ds_id, now):
                        continue
                    try:
                        ds_row = await session.get(Dataset, ds_id)
                        if ds_row is None:
                            continue
                        await refresh_one(session, ds_row)
                        # Not an unconditional clear: an aggregate whose grain
                        # no longer covers its source's rules records that
                        # failure INSIDE refresh_one and returns True (it did
                        # run -- it chose not to rewrite), so clearing here on
                        # every tick would erase the row this same call just
                        # wrote and the Aggregates tab would never see it.
                        # in_backoff is already true for a row just written,
                        # since record_failure schedules the next attempt in
                        # the future.
                        if not await in_backoff(session, "dataset", ds_id, now):
                            await clear_failure(session, "dataset", ds_id)
                    except Exception as e:  # noqa: BLE001 - never-die, per item
                        await session.rollback()
                        await record_failure(session, "dataset", ds_id, str(e), now)

                # Dataflows carry their own interval, so the dataset query above
                # cannot see them: an output's own refresh_interval_minutes is
                # normally None.
                flows = (await session.execute(
                    select(Dataflow).where(Dataflow.refresh_interval_minutes.isnot(None))
                )).scalars().all()
                due_flow_ids = [f.id for f in due_dataflows(flows, now)]
                for flow_id in due_flow_ids:
                    if await in_backoff(session, "dataflow", flow_id, now):
                        continue
                    try:
                        flow_row = await session.get(Dataflow, flow_id)
                        if flow_row is None:
                            continue
                        await refresh_dataflow(session, flow_row)
                        await clear_failure(session, "dataflow", flow_id)
                    except Exception as e:  # noqa: BLE001 - never-die, per item
                        await session.rollback()
                        await record_failure(session, "dataflow", flow_id, str(e), now)

                scheds = (await session.execute(
                    select(ReportSchedule).where(ReportSchedule.interval_minutes.isnot(None))
                )).scalars().all()
                due_scheds = _oldest_first(
                    [s for s in scheds if schedule_is_due(s, now)],
                    "last_run_at")[:MAX_ITEMS_PER_TICK]

                alerts = (await session.execute(
                    select(DataAlert).where(DataAlert.interval_minutes.isnot(None))
                )).scalars().all()
                due_alerts = _oldest_first(
                    [a for a in alerts if is_due(a.interval_minutes, a.last_checked_at, now)],
                    "last_checked_at")[:MAX_ITEMS_PER_TICK]

                # ids extracted while the session is open; the rows themselves
                # never leave it. Anything inside its backoff window is held
                # back here rather than inside run_items, so the concurrency
                # budget goes to work that can actually succeed.
                due_sched_ids = [x.id for x in due_scheds
                                 if not await in_backoff(session, "schedule", x.id, now)]
                due_alert_ids = [a.id for a in due_alerts
                                 if not await in_backoff(session, "alert", a.id, now)]

            # Item execution happens OUTSIDE the tick session's scope, on
            # per-item sessions -- see run_items.
            await run_items(session_factory, due_sched_ids, ReportSchedule,
                            1_000_000_000, run_schedule, "schedule")
            await run_items(session_factory, due_alert_ids, DataAlert,
                            2_000_000_000, check_alert, "alert")

            # Power Pi automation: ONE step of ONE run per tick. It shares this
            # loop for the reason stated above -- a second scheduler would be a
            # second place for the tick, the advisory-lock discipline and the
            # never-die contract to drift. Its own try/except because the two
            # are independent: an orchestrator bug must not stop tonight's
            # dataset refreshes, and a broken refresh must not stall the
            # automation queue.
            #
            # Deliberately one step per tick rather than "drain what's ready":
            # a real step is a profile or a report composition, and the
            # refreshes above are waiting behind it.
            try:
                from .automation_runner import tick as automation_tick
                async with session_factory() as automation_session:
                    await automation_tick(automation_session, now)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 - never-die, same contract
                log.warning("Automation runner tick failed: %s", e)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 - a bad tick must not kill the loop
            log.warning("Refresh scheduler tick failed: %s", e)
