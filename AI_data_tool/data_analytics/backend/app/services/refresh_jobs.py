"""A manual dataset refresh, run now or as a durable job (E12).

`POST /datasets/{id}/refresh` answered only when the reload finished: a large
table held the request (and the button) for minutes, a closed tab or a proxy
timeout lost the outcome, a server restart lost the work, and two clicks, or
two people, ran two refreshes over the same file at once. An incremental one
appends, so two overlapping appends could write the same rows twice.

This module is the one refresh, used both ways:

* `refresh_now` is the whole operation (checks, fetch, schema guard, file,
  columns, watermark, manifest, audit, query log) and is what the synchronous
  endpoint runs, unchanged in behaviour;
* the `dataset.refresh` job runs the same function in the worker
  (services/jobs.py), as the person who queued it, as they are NOW. It fetches
  without touching the file, fences its success on the job row, and only then
  writes the file and commits: an attempt that lost its lease writes nothing,
  so overlapping attempts cannot both append. A schema break fails the job
  with the missing columns and their likely new names as its result, so the
  page can offer the same mapping the synchronous refresh does.

One refresh per dataset at a time: a second request while one is queued or
running gets that one back (its owner) or a refusal (anyone else), and the
synchronous endpoint refuses while a job holds the dataset.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.models import (DataSource, Dataset, DatasetColumn, Job, User,
                             Watermark)
from . import jobs

REFRESH_JOB_KIND = "dataset.refresh"


class RefreshRefused(Exception):
    """The refresh cannot run; `status_code` is what the endpoint answers."""

    def __init__(self, message: str, status_code: int = 400, code: str = "refused"):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


class ChecksRefused(Exception):
    """Phase 3: a blocking data check failed on the new data; nothing was
    written. `payload` is the 409 body: the message and every check result."""

    def __init__(self, payload: dict):
        super().__init__(payload["detail"])
        self.payload = payload


class SchemaBreakRefused(Exception):
    """E05: the source dropped columns this dataset uses; nothing was written.
    `payload` is the 409 body: the message, the missing columns, suggested
    new names, every incoming column, and what depends on each."""

    def __init__(self, payload: dict):
        super().__init__(payload["detail"])
        self.payload = payload


async def load_refreshable(db: AsyncSession, user: User, dataset_id: int) -> tuple[Dataset, DataSource]:
    """The dataset and its connection, or RefreshRefused saying why not.

    Checked when a refresh is asked for AND again when a queued one runs:
    the person may have lost access, or the connection been deleted, while
    it waited."""
    from ..core.capability import require_dataset_capability
    from ..core.org_scope import check_org

    dataset = (await db.execute(
        select(Dataset).options(selectinload(Dataset.columns)).where(Dataset.id == dataset_id)
    )).scalar_one_or_none()
    check_org(dataset, user, "Dataset not found")
    await require_dataset_capability(db, user, dataset_id, "data")
    if dataset.mode == "directquery":
        raise RefreshRefused("DirectQuery datasets always query the live source — there's nothing to refresh")
    if not dataset.data_source_id:
        raise RefreshRefused("This dataset was not imported from a database connection")
    if not dataset.source_table and not dataset.source_query:
        raise RefreshRefused("Source query not recorded — re-import from the Connections page")
    src = await db.get(DataSource, dataset.data_source_id)
    check_org(src, user, "Original data source no longer exists")
    return dataset, src


async def active_refresh_job(db: AsyncSession, org_id: int, dataset_id: int) -> Job | None:
    """The queued or running refresh job for this dataset, if any.

    Filtered in Python: `inputs` is JSON, and an org has only a handful of
    active refresh jobs at any moment."""
    rows = (await db.execute(select(Job).where(
        Job.org_id == org_id, Job.kind == REFRESH_JOB_KIND,
        Job.state.in_([jobs.QUEUED, jobs.RUNNING])).order_by(Job.id))).scalars().all()
    return next((j for j in rows if (j.inputs or {}).get("dataset_id") == dataset_id), None)


async def refresh_now(db: AsyncSession, user: User, dataset_id: int, **kwargs
                      ) -> tuple[Dataset, str | None]:
    """A manual refresh (see `_refresh_now`), recorded as a `RefreshRun`.

    Pipeline plan, phase 1: the manual path left one `QueryRun` row on
    success and nothing on failure. The run starts only once the dataset is
    known to be refreshable, so a refusal ("a DirectQuery dataset has
    nothing to refresh") is an answer, not a failed run."""
    from .refresh_runs import finish_run, start_run
    run: dict = {"id": None, "mutating": False}

    async def _started() -> None:
        run["id"] = await start_run(db, "dataset", dataset_id, user.org_id, "manual")

    try:
        dataset, warning = await _refresh_now(db, user, dataset_id, _on_loaded=_started,
                                              _state=run, **kwargs)
    except BaseException as e:
        if run["id"] is not None:
            # Only a failure AFTER the dataset rows were changed has anything
            # to discard -- and must discard it, or recording the run would
            # commit a half-applied refresh. Earlier failures leave the
            # session clean, and the caller's instances usable.
            if run["mutating"]:
                try:
                    await db.rollback()
                except Exception:  # noqa: BLE001
                    pass
            if isinstance(e, (jobs.LeaseLost, jobs.JobCancelled)):
                await finish_run(db, run["id"], "skipped",
                                 error="Cancelled" if isinstance(e, jobs.JobCancelled)
                                 else "Another worker took this refresh over",
                                 error_code="cancelled")
            elif isinstance(e, ChecksRefused):
                await finish_run(db, run["id"], "blocked", error=e.payload["detail"],
                                 error_code="checks_blocked", checks=e.payload.get("checks"))
            else:
                detail = e.payload.get("detail") if isinstance(e, SchemaBreakRefused) else str(e)
                code = ("schema_break" if isinstance(e, SchemaBreakRefused)
                        else getattr(e, "code", None) or "refresh_failed")
                await finish_run(db, run["id"], "failed", error=detail or type(e).__name__,
                                 error_code=str(code)[:40])
        raise
    await finish_run(db, run["id"], "ok", rows=dataset.row_count, checks=run.get("checks"))
    return dataset, warning


async def _refresh_now(
    db: AsyncSession, user: User, dataset_id: int, *,
    _on_loaded: Callable[[], Awaitable[None]] | None = None,
    _state: dict | None = None,
    publish_anyway: bool = False,
    mode: str = "full", cursor_column: str | None = None,
    column_map: dict[str, str] | None = None, force: bool = False,
    checkpoint: Callable[..., Awaitable[None]] | None = None,
    before_commit: Callable[[AsyncSession, Dataset, dict], Awaitable[None]] | None = None,
    defer_write: bool = False,
) -> tuple[Dataset, str | None]:
    """Re-fetch the dataset from its connection; return it and any warning.

    F3: `mode` picks full reload or watermark-driven incremental append. The
    Watermark row IS the persisted config -- a `cursor_column` given here
    drives this run and carries over to the next one and to the scheduler.
    E05: a full load missing a column something uses raises
    SchemaBreakRefused before anything is written, unless `column_map`
    re-attaches it or `force` accepts the break.

    `defer_write` (the queued path) leaves the file untouched until
    `before_commit` has run -- which is where a job fences its success -- so
    a refresh whose outcome does not stand writes nothing."""
    from ..services.audit import record as audit
    from ..services.dataset_refresh import (SchemaBreak, refresh_dataset,
                                            write_dataset_files,
                                            write_materialization)
    from ..services.dependencies import find_dependents_of
    from ..services.ingest import missing_pct
    from ..services.query_log import log_query_run_sync

    dataset, src = await load_refreshable(db, user, dataset_id)
    if _on_loaded is not None:
        await _on_loaded()
    cfg = dict(src.config)
    cfg['type'] = src.type

    watermark = (await db.execute(
        select(Watermark).where(Watermark.dataset_id == dataset_id)
    )).scalar_one_or_none()

    requested_mode = "incremental" if mode == "incremental" else "full"
    cursor_column = cursor_column or (watermark.cursor_column if watermark else None)
    # A cursor value only applies to the SAME column it was measured on --
    # switching the watermark column mid-flight must not filter by a value
    # from a different one.
    cursor_value = (watermark.cursor_value
                    if watermark and watermark.cursor_column == cursor_column else None)

    # Allowlist for the cursor-column identifier the incremental query
    # interpolates: this dataset's own known columns, captured before the
    # delete+recreate below touches them.
    known_columns = {c.name for c in dataset.columns}
    # semantic_type is set by metadata sync / the RLS builder / auto-generate,
    # never re-derived from the refreshed data, so it is carried forward by
    # name across the delete+recreate below.
    semantic_types = {c.name: c.semantic_type for c in dataset.columns if c.semantic_type}

    # E05: the columns something on this dataset names.
    dependents = {} if force else await find_dependents_of(db, dataset, sorted(known_columns))
    required = {n for n, deps in dependents.items() if deps}

    if checkpoint is not None:
        await checkpoint("querying")
    # Phase 3: the dataset's saved checks run on the new frame before it is
    # written. `publish_anyway` -- an editor's decision after seeing them
    # fail -- records the results and publishes regardless.
    from ..services.data_checks import (ChecksBlocked, blocking_failures, describe,
                                        known_types, load_checks, make_validator)
    holder = _state if _state is not None else {}
    validate = make_validator(await load_checks(db, dataset_id), dataset.row_count,
                              await known_types(db, dataset_id), holder, force=publish_anyway)
    start = time.monotonic()
    try:
        outcome = await asyncio.to_thread(
            refresh_dataset, cfg, dataset.filename, dataset.source_table, dataset.source_query,
            requested_mode, cursor_column, cursor_value, known_columns,
            required, column_map, not defer_write, validate,
        )
    except ChecksBlocked as e:
        failed = blocking_failures(e.results)
        raise ChecksRefused({
            "detail": "Not published: " + "; ".join(describe(r) for r in failed)
                      + ". The previous data is still live.",
            "code": "checks_blocked",
            "checks": e.results,
        })
    except SchemaBreak as e:
        raise SchemaBreakRefused({
            "detail": (f"Not refreshed: the source no longer has {', '.join(repr(m) for m in e.missing)}, "
                       "which this dataset's widgets or calculations use. Map each to its new name, "
                       "or refresh anyway with force."),
            "code": "schema_break",
            "missing": e.missing,
            "suggestions": e.suggestions,
            "available": e.available,
            "dependents": {m: dependents.get(m, []) for m in e.missing},
        })
    except Exception as e:
        raise RefreshRefused(f"Refresh failed: {e}", code="source_error")
    duration_ms = int((time.monotonic() - start) * 1000)
    if checkpoint is not None:
        # The last point a cancel can stop it: nothing has been written yet.
        await checkpoint("saving", rows=len(outcome["df"]))

    df, type_map = outcome["df"], outcome["type_map"]
    if _state is not None:
        _state["mutating"] = True
    dataset.row_count = len(df)
    dataset.col_count = len(df.columns)
    dataset.last_refreshed_at = datetime.utcnow()

    for col in list(dataset.columns):
        await db.delete(col)
    await db.flush()
    for col_name, dtype in type_map.items():
        db.add(DatasetColumn(
            dataset_id=dataset.id, name=col_name, dtype=dtype,
            missing_pct=missing_pct(df[col_name]), stats={},
            semantic_type=semantic_types.get(col_name),
        ))

    if cursor_column:
        if watermark is None:
            watermark = Watermark(dataset_id=dataset_id)
            db.add(watermark)
        watermark.strategy = outcome["mode"]
        watermark.cursor_column = cursor_column
        watermark.cursor_value = outcome["cursor_value"]

    if dataset.filename:
        await write_materialization(
            db, dataset.id, dataset.filename, outcome["mode"],
            len(df), list(df.columns), outcome.get("cursor_value"),
        )

    # E07: a manual reload replaces what every dashboard on it shows.
    await audit(db, user, "dataset.refresh", "dataset", dataset.id,
                f"{outcome['mode']} from {src.name} -> {len(df):,} rows"
                + (" (forced past a schema break)" if force else ""))
    if before_commit is not None:
        await before_commit(db, dataset, outcome)
    if defer_write and dataset.filename:
        # After the fence: this attempt's outcome stands, so its file does.
        await asyncio.to_thread(write_dataset_files, df, dataset.filename)
    dataset.file_size = Path(dataset.filename).stat().st_size if dataset.filename else 0
    await db.commit()

    log_query_run_sync(
        org_id=user.org_id, source_kind="refresh", data_source_id=dataset.data_source_id,
        dataset_id=dataset.id, sql_hash=None, rows_returned=len(df),
        duration_ms=duration_ms, executor="pandas", cache_hit=False,
    )
    return dataset, outcome.get("warning")


def job_inputs(dataset_id: int, mode: str, cursor_column: str | None,
               column_map: dict[str, str] | None, force: bool,
               publish_anyway: bool = False) -> dict:
    """What a refresh job runs with, frozen at enqueue."""
    return {"dataset_id": dataset_id, "publish_anyway": bool(publish_anyway),
            "mode": "incremental" if mode == "incremental" else "full",
            "cursor_column": cursor_column or None,
            "column_map": dict(column_map) if column_map else None,
            "force": bool(force)}


@jobs.register(REFRESH_JOB_KIND)
async def run_refresh_job(ctx: "jobs.JobContext") -> None:
    """Run a queued refresh as the person who queued it, as they are NOW."""
    inputs = dict(ctx.inputs)
    dataset_id = inputs.get("dataset_id")
    async with ctx.session_factory() as db:
        user = await ctx.load_user(db)
        if user is None:
            raise jobs.JobError("The person who queued this refresh can no longer refresh it",
                                code="not_allowed")

        async def _complete(db_, dataset: Dataset, outcome: dict) -> None:
            await ctx.complete(db_, {
                "dataset_id": dataset.id, "dataset_name": dataset.name,
                "row_count": dataset.row_count, "col_count": dataset.col_count,
                "mode": outcome["mode"], "rows_added": outcome.get("rows_added"),
                "warning": outcome.get("warning")})

        try:
            await refresh_now(db, user, dataset_id,
                              mode=inputs.get("mode") or "full",
                              cursor_column=inputs.get("cursor_column"),
                              column_map=inputs.get("column_map"),
                              force=bool(inputs.get("force")),
                              publish_anyway=bool(inputs.get("publish_anyway")),
                              checkpoint=ctx.checkpoint, before_commit=_complete,
                              defer_write=True)
        except ChecksRefused as e:
            raise jobs.JobError(e.payload["detail"], code="checks_blocked",
                                detail={"checks": e.payload["checks"]})
        except SchemaBreakRefused as e:
            raise jobs.JobError(e.payload["detail"], code="schema_break", detail={
                k: e.payload[k] for k in ("missing", "suggestions", "available", "dependents")})
        except RefreshRefused as e:
            raise jobs.JobError(str(e), code=e.code)
        except (jobs.LeaseLost, jobs.JobCancelled):
            # Lost the lease: another worker owns the job, and this attempt
            # wrote nothing. Cancelled: stopped before anything was written.
            await db.rollback()
            raise
        except Exception as e:
            # check_org / the capability rung refuse with 404 or 403 (an HTTP
            # exception; services do not import the web framework, so it is
            # recognised by its status): the dataset is gone, or no longer
            # this person's to refresh.
            if getattr(e, "status_code", None) in (403, 404):
                raise jobs.JobError("This dataset no longer exists, or you may no longer "
                                    "refresh it", code="not_allowed")
            raise
