"""Import a table or query from a database connection into a dataset.

Moved out of `routers/data_sources.py` so the two ways in run the same code:
`POST /data-sources/{id}/import` still imports inside the request, and
`POST /data-sources/{id}/import-jobs` queues a durable job (services/jobs.py)
whose handler, below, calls the same function.

`checkpoint` and `before_commit` are how a job drives it. `checkpoint(stage,
**detail)` is awaited between the stages (after the source query, after the
file is written aside) and may raise to stop with nothing committed;
`before_commit(db, dataset)` is awaited inside the final transaction, so the
job's `succeeded` and the dataset commit together or not at all. The request
path passes neither.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.models import DataSource, Dataset, DatasetColumn, User
from ..schemas.schemas import ImportRequest
from . import connectors, jobs, knowledge, quotas
from .analytics import detect_types
from .connections import import_to_dataframe, preview_table
from .frame_cache import write_parquet_sidecar
from .ingest import duplicate_columns, missing_pct

IMPORT_JOB_KIND = "dataset.import"


class ImportRefused(Exception):
    """An import the source, the request or the target refused, worded for
    the person importing. The router turns it into an HTTP error; the job
    handler into a failed job. (Services never pick HTTP status codes
    themselves -- see test_layer_conformance.)"""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


async def _checkpoint(hook, stage: str, **detail) -> None:
    if hook is not None:
        await hook(stage, **detail)


async def _before_commit(hook, db, dataset) -> None:
    if hook is not None:
        await hook(db, dataset)


def compile_model_for_source(cfg: dict, ds_type: str, model: dict, *, unlimited: bool) -> str:
    """Compile a Query-builder model against the live schema -- the SAME
    compile the builder shows, run server-side at save time so the stored SQL
    never depends on what the browser happened to send.

    `unlimited` is True for DirectQuery: a live dataset stores its SQL with no
    LIMIT (see query_builder.build_sql)."""
    from .query_builder import (build_sql, introspect_tables, list_functions,
                                referenced_functions, referenced_tables)
    known = introspect_tables(cfg, referenced_tables(model))
    funcs = {f["name"] for f in list_functions(cfg)} if referenced_functions(model) else set()
    return build_sql(model, connectors.sql_family_of(cfg) or ds_type, known,
                     cfg.get('schema') or None, funcs, unlimited=unlimited)


_TRAILING_LIMIT = None


def strip_compiled_limit(sql: str) -> str | None:
    """The LIMIT the builder appended to a compiled statement, removed -- or
    None when `sql` does not end the way build_sql ends a capped query.

    Used once, to repair live datasets saved before build_sql learned
    `unlimited`: their stored SQL ends `... LIMIT 100000` (or the Oracle /
    SQL Server spelling) and every widget saw only those rows."""
    import re
    global _TRAILING_LIMIT
    if _TRAILING_LIMIT is None:
        _TRAILING_LIMIT = (
            re.compile(r"\s+LIMIT\s+\d+\s*$", re.I),
            re.compile(r"\s+FETCH\s+FIRST\s+\d+\s+ROWS\s+ONLY\s*$", re.I),
            re.compile(r"^(\s*(?:WITH\s.*?\)\s*)?SELECT\s+)TOP\s+\d+\s+", re.I | re.S),
        )
    lim, fetch, top = _TRAILING_LIMIT
    for pat in (lim, fetch):
        if pat.search(sql):
            return pat.sub("", sql)
    if top.search(sql):
        return top.sub(r"\1", sql, count=1)
    return None


async def repair_capped_live_datasets(db: AsyncSession) -> int:
    """Strip the row LIMIT that older Query-builder saves baked into live
    (DirectQuery) datasets. Only datasets with a `query_model` are touched:
    their SQL was compiled by build_sql, so the trailing LIMIT is known to be
    the builder's and not something a person wrote on purpose. Idempotent."""
    rows = (await db.execute(
        select(Dataset).where(Dataset.mode == "directquery",
                              Dataset.query_model.is_not(None),
                              Dataset.source_query.is_not(None)))).scalars().all()
    fixed = 0
    for d in rows:
        new_sql = strip_compiled_limit(d.source_query or "")
        if new_sql and new_sql != d.source_query:
            d.source_query = new_sql
            fixed += 1
    if fixed:
        await db.commit()
        import logging
        logging.getLogger(__name__).info(
            "removed a builder row LIMIT from %d live dataset(s)", fixed)
    return fixed


async def import_from_source(db: AsyncSession, current_user: User, ds: DataSource,
                             req: ImportRequest, *, checkpoint=None, before_commit=None) -> dict:
    """Import (or DirectQuery-connect) `req` from `ds` for `current_user`.

    The caller has already checked that `ds` is in the user's org and that the
    user may import. Refusals raise ImportRefused; a full storage quota
    raises quotas.QuotaExceeded, as it always has."""
    cfg = dict(ds.config)
    cfg['type'] = ds.type

    # D1: when dataset_id is set, this is a re-import of a builder-created
    # dataset -- update the row and its data in place (full reload semantics)
    # instead of creating a sibling. selectinload so `.columns` is safe to
    # touch on this async session without a lazy-load round trip.
    existing = None
    if req.dataset_id is not None:
        result = await db.execute(
            select(Dataset).options(selectinload(Dataset.columns)).where(Dataset.id == req.dataset_id)
        )
        existing = result.scalar_one_or_none()
        if existing is None or existing.org_id != current_user.org_id:
            raise ImportRefused("Dataset not found", 404)

    async def _replace_columns(dataset: Dataset, cols: list[DatasetColumn]) -> None:
        # semantic_type (email/phone/url/...) comes from metadata sync or a
        # manual edit, never from this re-import's fresh type detection --
        # carry it forward by column name or every re-import quietly wipes it
        # until the next metadata sync, degrading the codeless RLS builder
        # and auto-generate in the meantime.
        semantic_types = {c.name: c.semantic_type for c in dataset.columns if c.semantic_type}
        # Provenance survives a re-import for the same reason semantic_type
        # does: it was established once, possibly from a more informative
        # query than this one, and `link_columns` below can only ADD links.
        # Losing it would silently strip every description the dataset had
        # been resolving through it until the next sync.
        source_links = {c.name: c.source_column_id for c in dataset.columns if c.source_column_id}
        for col in list(dataset.columns):
            await db.delete(col)
        await db.flush()
        for col in cols:
            if col.semantic_type is None:
                col.semantic_type = semantic_types.get(col.name)
            if col.source_column_id is None:
                col.source_column_id = source_links.get(col.name)
            db.add(col)

    # A builder save carries its model: compile it HERE, for the target mode,
    # instead of storing whatever SQL the browser sent. Live datasets get no
    # row LIMIT; imports keep the person's limit (refused above the import
    # cap, never silently lowered). Hand-written SQL (no model) is kept as is.
    if req.query_model and req.query:
        try:
            req.query = await asyncio.to_thread(
                compile_model_for_source, cfg, ds.type, req.query_model,
                unlimited=(req.mode == "directquery"))
        except ValueError as e:
            raise ImportRefused(str(e))

    if req.mode == "directquery":
        # Refuse up front for a source that cannot serve DirectQuery at all.
        # The probe below is only a preview, and preview works for import-only
        # types (Access reads its file, the API connector fetches its rows), so
        # without this check the request SUCCEEDS and creates a dataset that
        # cannot render -- the failure surfaces later, at the first widget, far
        # from the choice that caused it.
        try:
            spec = connectors.resolve(ds.type)
        except connectors.UnknownConnector:
            spec = None
        if spec is not None and not spec.supports_directquery:
            raise ImportRefused(
                f"{spec.label} cannot be queried live — import the table "
                     f"instead (mode='import')")

        # No data materializes -- just a lightweight schema probe (same preview_table
        # used by the schema browser) to populate DatasetColumn rows, since the
        # DirectQuery query path (direct_query.py) validates every column it touches
        # against that allowlist before it ever reaches SQL.
        def _probe():
            return preview_table(cfg, req.table, req.query, limit=50)

        try:
            preview = await asyncio.to_thread(_probe)
        except Exception as e:
            raise ImportRefused(str(e))

        probe_df = pd.DataFrame(preview['rows'], columns=preview['columns'])
        type_map = detect_types(probe_df) if len(probe_df) else {}
        new_cols = [DatasetColumn(name=c, dtype=type_map.get(c, 'unknown'), stats={}) for c in preview['columns']]

        if existing is not None:
            existing.name = req.dataset_name
            existing.description = f"DirectQuery from {ds.name} ({ds.type})"
            existing.data_source_id = ds.id
            existing.source_table = req.table
            existing.source_query = req.query
            existing.query_model = req.query_model
            existing.mode = "directquery"
            existing.filename = None
            existing.row_count = 0
            existing.col_count = len(preview['columns'])
            existing.file_size = 0
            for c in new_cols:
                c.dataset_id = existing.id
            await _replace_columns(existing, new_cols)
            # Record where each column came from, so `services/knowledge.py` can
            # resolve its description, semantic type and enum labels out of the
            # source catalog at read time. Best-effort by design: a source that was
            # never synced has no catalog to link against, and an import must not
            # fail because metadata is missing.
            await knowledge.link_columns(db, existing)
            await _audit_import(db, current_user, existing, ds, req, replaced=True)
            await _before_commit(before_commit, db, existing)
            await db.commit()
            await db.refresh(existing)
            return {'id': existing.id, 'name': existing.name, 'row_count': 0, 'col_count': existing.col_count, 'mode': 'directquery'}

        dataset = Dataset(
            name=req.dataset_name,
            description=f"DirectQuery from {ds.name} ({ds.type})",
            filename=None, row_count=0, col_count=len(preview['columns']), file_size=0,
            data_source_id=ds.id, source_table=req.table, source_query=req.query,
            query_model=req.query_model, mode="directquery", org_id=current_user.org_id,
            # Owned by the importer, like an upload (NULL means readable by
            # the whole org, which is for pre-ownership rows only).
            created_by=current_user.id,
        )
        db.add(dataset)
        await db.flush()
        for c in new_cols:
            c.dataset_id = dataset.id
            db.add(c)
        # Record where each column came from, so `services/knowledge.py` can
        # resolve its description, semantic type and enum labels out of the
        # source catalog at read time. Best-effort by design: a source that was
        # never synced has no catalog to link against, and an import must not
        # fail because metadata is missing.
        await knowledge.link_columns(db, dataset)
        from .sensitivity import apply_confidential_export_default
        await apply_confidential_export_default(db, dataset)
        await _audit_import(db, current_user, dataset, ds, req, replaced=False)
        await _before_commit(before_commit, db, dataset)
        await db.commit()
        await db.refresh(dataset)
        return {'id': dataset.id, 'name': dataset.name, 'row_count': 0, 'col_count': dataset.col_count, 'mode': 'directquery'}

    def _fetch():
        df = import_to_dataframe(cfg, req.table, req.query)
        # Two columns with the same name make `df[name]` a DataFrame rather than a
        # Series, and every later truth test on it raises a pandas message that
        # names nothing the person wrote. Refuse here, naming the column instead.
        dupes = duplicate_columns(df.columns)
        if dupes:
            raise ValueError(
                "The query returns more than one column named %s. Give each one a "
                "different name with AS, for example `l.unit AS lab_unit`."
                % ", ".join("'%s'" % d for d in dupes))
        return df

    def _write_aside(df, file_path_hint: str | None):
        if file_path_hint:
            file_path = Path(file_path_hint)
            file_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            # E07: a fresh, per-org path -- the same allocator uploads use. It
            # was  upload_dir/<dataset name>.csv : shared by EVERY org, so two
            # imports named alike overwrote each other's data across tenants,
            # and a name carrying  ..\  escaped the upload folder on Windows.
            from .upload_store import allocate_path
            file_path = allocate_path(current_user.org_id, "import.csv")
        # Type detection BEFORE the write, not after. `detect_types` converts in
        # place -- an epoch-integer column becomes real datetimes, a text date
        # column becomes datetimes -- and running it afterwards left that
        # conversion in a frame that had already been serialised. The dataset was
        # then labelled `datetime` while every widget re-read integers off the
        # CSV, which is a disagreement no unit test on the type can see.
        # E07: offset-carrying instants to the reference zone, before typing
        # (a two-offset column is otherwise typed datetime and unusable).
        from .timezones import normalize_instants
        normalize_instants(df)
        type_map = detect_types(df)
        # Written aside, then swapped in: a re-import writes over the LIVE file,
        # and a crash or a full disk mid-write left a truncated CSV that the
        # dataset still pointed at. os.replace is atomic on one filesystem.
        tmp = file_path.with_name(file_path.name + ".tmp")
        df.to_csv(tmp, index=False)
        return file_path, tmp, type_map

    def _swap_in(file_path: Path, tmp: Path) -> None:
        os.replace(tmp, file_path)
        write_parquet_sidecar(str(file_path))  # already on a worker thread

    # Three stages with a checkpoint between each, so a queued import can be
    # cancelled with nothing written. The last checkpoint is before the swap:
    # once a re-import has replaced the live file there is no going back.
    try:
        df = await asyncio.to_thread(_fetch)
    except Exception as e:
        raise ImportRefused(str(e))
    await _checkpoint(checkpoint, "writing", rows=len(df))
    try:
        target, tmp, type_map = await asyncio.to_thread(
            _write_aside, df, existing.filename if existing is not None else None)
    except Exception as e:
        raise ImportRefused(str(e))
    try:
        await _checkpoint(checkpoint, "saving", rows=len(df))
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    try:
        await asyncio.to_thread(_swap_in, target, tmp)
    except Exception as e:
        Path(tmp).unlink(missing_ok=True)
        raise ImportRefused(str(e))
    file_path = str(target)

    new_cols = [DatasetColumn(name=col_name, dtype=dtype,
                               missing_pct=missing_pct(df[col_name]), stats={})
                for col_name, dtype in type_map.items()]

    if existing is not None:
        existing.name = req.dataset_name
        existing.description = f"Imported from {ds.name} ({ds.type})"
        existing.filename = file_path
        existing.row_count = len(df)
        existing.col_count = len(df.columns)
        existing.file_size = Path(file_path).stat().st_size
        existing.data_source_id = ds.id
        existing.source_table = req.table
        existing.source_query = req.query
        existing.query_model = req.query_model
        existing.mode = "import"
        for c in new_cols:
            c.dataset_id = existing.id
        await _replace_columns(existing, new_cols)
        # Record where each column came from, so `services/knowledge.py` can
        # resolve its description, semantic type and enum labels out of the
        # source catalog at read time. Best-effort by design: a source that was
        # never synced has no catalog to link against, and an import must not
        # fail because metadata is missing.
        await knowledge.link_columns(db, existing)
        await _audit_import(db, current_user, existing, ds, req, replaced=True)
        await _before_commit(before_commit, db, existing)
        await db.commit()
        await db.refresh(existing)
        return {'id': existing.id, 'name': existing.name, 'row_count': existing.row_count, 'col_count': existing.col_count, 'mode': 'import'}

    # Task E2: storage quota, new-dataset imports only -- a re-import above
    # overwrites its own existing file in place rather than growing total
    # usage, so it's exempt (checking it would need a "size delta" this
    # in-place overwrite doesn't cleanly expose).
    new_file_size = Path(file_path).stat().st_size
    try:
        await quotas.enforce_storage_quota(db, current_user.org_id, new_file_size)
    except quotas.QuotaExceeded:
        # A refused import must not leave its file on disk (E07) -- nor its
        # parquet sidecar.
        from .frame_cache import remove_parquet_sidecar
        Path(file_path).unlink(missing_ok=True)
        remove_parquet_sidecar(str(file_path))
        raise

    dataset = Dataset(last_refreshed_at=datetime.utcnow(),  # E06: when the data was loaded
        name=req.dataset_name,
        description=f"Imported from {ds.name} ({ds.type})",
        filename=file_path,
        row_count=len(df),
        col_count=len(df.columns),
        file_size=Path(file_path).stat().st_size,
        data_source_id=ds.id,
        source_table=req.table,
        source_query=req.query,
        query_model=req.query_model,
        org_id=current_user.org_id,
        # Owned by the importer, like an upload (see the DirectQuery branch).
        created_by=current_user.id,
    )
    db.add(dataset)
    await db.flush()
    for c in new_cols:
        c.dataset_id = dataset.id
        db.add(c)

    # Record where each column came from, so `services/knowledge.py` can
    # resolve its description, semantic type and enum labels out of the
    # source catalog at read time. Best-effort by design: a source that was
    # never synced has no catalog to link against, and an import must not
    # fail because metadata is missing.
    await knowledge.link_columns(db, dataset)
    from .sensitivity import apply_confidential_export_default
    await apply_confidential_export_default(db, dataset)
    await _audit_import(db, current_user, dataset, ds, req, replaced=False)
    await _before_commit(before_commit, db, dataset)
    await db.commit()
    await db.refresh(dataset)
    return {'id': dataset.id, 'name': dataset.name, 'row_count': dataset.row_count, 'col_count': dataset.col_count, 'mode': 'import'}


async def _audit_import(db: AsyncSession, user: User, dataset, source, req, *, replaced: bool) -> None:
    """E07: who brought which data in, from where, and how much. Uploads,
    exports and deletes were audited; an import from a database was not."""
    from .audit import record
    what = req.table or ("query: " + " ".join((req.query or "").split())[:200])
    live = dataset.mode == "directquery"
    rows = "live" if live else f"{dataset.row_count:,} rows"
    # 5.7: a live dataset copies nothing, so "import" in the activity log
    # misdescribed it -- an auditor looking for data leaving the source would
    # chase a copy that does not exist.
    if live:
        action = "dataset.update_live" if replaced else "dataset.create_live"
    else:
        action = "dataset.reimport" if replaced else "dataset.import"
    await record(db, user, action, "dataset", dataset.id, f"{source.name} ({source.type}) {what} -> {rows}")


# ── The queued path ──────────────────────────────────────────────────────────

def job_inputs(ds_id: int, req: ImportRequest) -> dict:
    """What an import job runs with, frozen at enqueue."""
    return {"data_source_id": ds_id, **req.model_dump()}


@jobs.register(IMPORT_JOB_KIND)
async def run_import_job(ctx: "jobs.JobContext") -> None:
    """Run a queued import as the person who queued it, as they are NOW.

    Permissions are checked at execution, not frozen at enqueue: an admin
    demoted, deactivated or moved while the job waited does not get the import,
    and a connection deleted meanwhile fails the job with a plain reason."""
    inputs = dict(ctx.inputs)
    ds_id = inputs.pop("data_source_id", None)
    req = ImportRequest(**inputs)
    if req.mode != "import":
        raise jobs.JobError("Only imports run as jobs; DirectQuery connects at once")
    await ctx.checkpoint("querying")
    created_file: list[str] = []
    async with ctx.session_factory() as db:
        user = await ctx.load_user(db)
        if user is None or not (user.role and user.role.is_org_admin):
            raise jobs.JobError("The person who queued this import may no longer import data",
                                code="not_allowed")
        ds = await db.get(DataSource, ds_id) if ds_id is not None else None
        if ds is None or ds.org_id != ctx.org_id:
            raise jobs.JobError("The connection this import reads from no longer exists")

        async def _complete(db_, dataset) -> None:
            if req.dataset_id is None and dataset.filename:
                created_file.append(dataset.filename)
            await ctx.complete(db_, {"dataset_id": dataset.id, "dataset_name": dataset.name,
                                     "row_count": dataset.row_count,
                                     "col_count": dataset.col_count,
                                     "replaced": req.dataset_id is not None})

        try:
            await import_from_source(db, user, ds, req, checkpoint=ctx.checkpoint,
                                     before_commit=_complete)
        except ImportRefused as e:
            raise jobs.JobError(str(e))
        except quotas.QuotaExceeded as e:
            raise jobs.JobError(str(e))
        except jobs.LeaseLost:
            # Another worker owns this job now and will write its own file; a
            # NEW import's file from this attempt would be an orphan.
            await db.rollback()
            from .frame_cache import remove_parquet_sidecar
            for f in created_file:
                Path(f).unlink(missing_ok=True)
                remove_parquet_sidecar(f)
            raise
