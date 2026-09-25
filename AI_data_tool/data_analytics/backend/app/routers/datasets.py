import asyncio
import logging
import shutil
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from ..core.database import get_db
from ..core.config import settings
from ..core.org_scope import check_org
from ..core.capability import (readable_dataset_ids, require_dataset_capability,
                               require_dataset_read, require_dataset_write)
from ..core.rls import resolve_denied_columns, resolve_rls_expr
from ..dependencies import get_current_user, require_org_admin
from ..services.audit import record as audit
from pydantic import BaseModel, Field
from ..models.models import (AnalysisResult, Dataset, DatasetColumn, DataSource,
                             SourceColumn, SourceObject, User)
from sqlalchemy.orm.attributes import flag_modified
from ..schemas.schemas import DataViewDefault, SuggestDashboardsRequest, DatasetOut, BatchUploadItem, BatchUploadOut, MaterializeRequest, CalcColumnDef, CalcColumnPreviewRequest, ColumnFormatRequest, DataPreviewRequest, FilterExprUpdate, FilterPreviewRequest, MeasureDef, MeasurePreviewRequest, ColumnMetaUpdate, RefreshScheduleUpdate, DatasetRefreshRequest, DatasetShareOut, CustomFunctionDef, CustomFunctionPreviewRequest, AggregateCreateRequest, AggregateUpdateRequest
from ..services.analytics import load_file, detect_types
from ..services.frame_cache import remove_parquet_sidecar, write_parquet_sidecar
from ..services.widget_data import preview_expression, apply_filter_expr
from ..services.direct_query import DirectQueryUnsupported, run_direct_query
from ..services import quotas, upload_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/datasets", tags=["datasets"])


class _SizeBudget:
    """A running byte ceiling for one batch request.

    Charged as each file lands rather than summed up front, because
    `UploadFile` does not reliably know its size before it is read. Checking
    incrementally means file N+1 is refused the moment the batch is over
    budget, instead of after every file is already on disk.
    """

    def __init__(self, limit_mb: int):
        self.limit = limit_mb * 1024 * 1024
        self.used = 0

    def charge(self, n: int) -> None:
        self.used += n
        if self.used > self.limit:
            raise HTTPException(
                413, f"Upload exceeds the {self.limit // (1024 * 1024)} MB limit "
                     f"for a single batch")


async def _without_denied_columns(db: AsyncSession, current_user: User, ds: Dataset,
                                  *, with_knowledge: bool = False) -> DatasetOut:
    """Serialize a Dataset with any column this role is denied on it removed
    from the schema listing too -- not just from query results.

    `resolve_denied_columns` already keeps `widget-data`/prep/export from
    returning a denied column's *values*; this endpoint's `columns` list is
    schema metadata, a separate response built straight off the ORM
    relationship, so it needs the same filter applied to it directly or a
    restricted role can still read a denied column's name (and dtype/stats)
    here even though its values are masked everywhere else."""
    item = DatasetOut.model_validate(ds)
    denied = set(await resolve_denied_columns(db, current_user, ds.id))
    if denied:
        item.columns = [c for c in item.columns if c.name not in denied]
    # Columns the prep pipeline creates (a partition, a split) are real to
    # every widget but absent from the uploaded file's column list; list them
    # so the pickers can offer them. Negative ids: they have no stored row.
    try:
        from ..services.prep import prep_added_columns, prep_steps_of
        from ..schemas.schemas import DatasetColumnOut
        steps = [s for s in prep_steps_of(ds) if not (isinstance(s, dict) and s.get("kind") == "join")]
        added = prep_added_columns(steps, {c.name: c.dtype for c in ds.columns})
        item.columns = item.columns + [
            DatasetColumnOut(id=-(i + 1), name=n, dtype=t) for i, (n, t) in enumerate(added) if n not in denied]
    except Exception:                                        # noqa: BLE001
        logger.warning("could not list prep-created columns for dataset %s", ds.id, exc_info=True)

    # Opt-in, and off for the LIST: resolving knowledge is a handful of queries
    # per dataset, which is nothing on one dataset and a hundred round trips on
    # a shelf of them. The single-dataset read is what the builder and the
    # dataset page load, and they are the surfaces that show this.
    if with_knowledge:
        from ..services import knowledge as knowledge_service
        try:
            know = await knowledge_service.for_dataset(db, ds, denied=denied)
        except Exception:                                    # noqa: BLE001
            # Cosmetic enrichment must never be able to fail a dataset read.
            logger.warning("could not resolve knowledge for dataset %s", ds.id,
                           exc_info=True)
            return item
        item.column_descriptions = {
            n: c.description for n, c in know.columns.items() if c.description}
        item.value_labels = {
            n: c.enum_labels for n, c in know.columns.items() if c.enum_labels}
        item.grain = know.object.grain
        item.business_name = know.object.business_name
        item.column_targets = {n: c.target_priority for n, c in know.columns.items()
                               if c.target_priority is not None}
        item.ineligible_columns = [n for n, c in know.columns.items()
                                   if not c.eligible_for_suggestion]
    return item


@router.get("", response_model=list[DatasetOut])
async def list_datasets(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(
        select(Dataset).options(selectinload(Dataset.columns))
        .where(Dataset.org_id == current_user.org_id)
        .order_by(Dataset.created_at.desc())
    )
    datasets = result.scalars().all()
    # The list is now SCOPED, not just badged: a member sees what they own,
    # what was shared with them, and what a dashboard they can open draws on.
    # `None` means an admin, who sees the org's whole shelf.
    readable = await readable_dataset_ids(db, current_user)
    if readable is not None:
        datasets = [ds for ds in datasets if ds.id in readable]
    # SH1: the badge still says which ones were handed to you explicitly --
    # sharing now GRANTS as well as flags, so the two meanings agree.
    from ..models.models import DatasetShare
    shared_ids = set((await db.execute(
        select(DatasetShare.dataset_id).where(DatasetShare.user_id == current_user.id)
    )).scalars().all())
    for ds in datasets:
        ds.shared = ds.id in shared_ids
    return [await _without_denied_columns(db, current_user, ds) for ds in datasets]


@router.get("/{dataset_id}", response_model=DatasetOut)
async def get_dataset(dataset_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(
        select(Dataset).options(selectinload(Dataset.columns)).where(Dataset.id == dataset_id)
    )
    ds = result.scalar_one_or_none()
    check_org(ds, current_user, "Dataset not found")
    await require_dataset_read(db, current_user, dataset_id)
    from ..models.models import DatasetShare
    ds.shared = (await db.execute(
        select(DatasetShare.id).where(DatasetShare.dataset_id == dataset_id, DatasetShare.user_id == current_user.id)
    )).scalar_one_or_none() is not None
    return await _without_denied_columns(db, current_user, ds, with_knowledge=True)


async def _ingest_upload_file(
    db: AsyncSession, org_id: int, *, source_filename: str | None, stream,
    name: str, description: str, budget: "_SizeBudget | None" = None,
    owner_id: int | None = None,
) -> Dataset:
    """Store one uploaded file and describe it as a Dataset.

    Flushes but does NOT commit -- the caller owns the transaction, because a
    batch has to commit per file (see `upload_datasets`) while a single upload
    commits once at the end.

    `source_filename` is the CLIENT's name and is never trusted as a path; only
    its extension survives `upload_store.allocate_path`. See that module for the
    traversal it closes.
    """
    # Before any bytes touch the disk, unlike the original which wrote first and
    # discovered the file was unreadable several steps later.
    try:
        upload_store.allowed_suffix(source_filename)
    except ValueError as e:
        raise HTTPException(400, str(e))

    file_path = upload_store.allocate_path(org_id, source_filename)

    with open(file_path, "wb") as f:
        shutil.copyfileobj(stream, f)

    file_size = file_path.stat().st_size
    if file_size > settings.max_upload_mb * 1024 * 1024:
        file_path.unlink(missing_ok=True)
        raise HTTPException(400, f"File exceeds {settings.max_upload_mb} MB limit")

    # A batch also has a ceiling on the REQUEST, not just each file: twenty
    # files each under the per-file cap can still be far more than one process
    # should ingest inline.
    if budget is not None:
        try:
            budget.charge(file_size)
        except HTTPException:
            file_path.unlink(missing_ok=True)
            raise

    # Task E2: 413 when this upload would push the org's total dataset
    # storage past its quota. Checked before the (comparatively expensive)
    # parse below, but after the file is on disk -- unlink on rejection so a
    # blocked upload doesn't leave orphaned bytes behind.
    try:
        await quotas.enforce_storage_quota(db, org_id, file_size)
    except (HTTPException, quotas.QuotaExceeded):
        # QuotaExceeded is deliberately NOT an HTTPException (it is raised from
        # schedulers too), so catching only the latter would let a blocked
        # upload leave its bytes on disk.
        file_path.unlink(missing_ok=True)
        raise

    try:
        df = await asyncio.to_thread(load_file, str(file_path))
    except Exception as e:
        # F1: an unsupported extension (ValueError from frame_cache) or a
        # malformed file the reader can't parse (e.g. XML syntax errors from
        # lxml) must read as a clean rejection of THIS upload, not a 500 --
        # the file is already on disk, so clean it up either way.
        file_path.unlink(missing_ok=True)
        raise HTTPException(400, f"Could not read file: {e}")
    type_map = await asyncio.to_thread(detect_types, df)
    # Best-effort accelerant: a verified parquet sidecar makes every later
    # load of this CSV a fraction of the parse cost. Failure never fails
    # the upload (the helper swallows and logs).
    await asyncio.to_thread(write_parquet_sidecar, str(file_path))

    ds = Dataset(
        name=name, description=description or None, filename=str(file_path),
        row_count=len(df), col_count=len(df.columns), file_size=file_size,
        org_id=org_id, created_by=owner_id,
    )
    db.add(ds)
    await db.flush()

    for col_name, dtype in type_map.items():
        db.add(DatasetColumn(
            dataset_id=ds.id, name=col_name, dtype=dtype,
            missing_pct=round(df[col_name].isnull().mean() * 100, 2), stats={},
        ))
    await _apply_default_data_view(db, ds, org_id)
    return ds


async def _apply_default_data_view(db: AsyncSession, ds: Dataset, org_id: int) -> None:
    """Apply the org's default data view to a freshly ingested dataset.

    SAS's admin default: an organisation that has already decided `amount` is a
    currency measure should not have to say so on every import.

    NEVER fails the upload. `apply_view` is match-by-name and skip-with-report,
    so a view built on other columns lands what fits and leaves the rest; and
    any error at all is swallowed, because a file that uploaded successfully
    must not be lost to a semantic layer that did not fit it.
    """
    from ..models.models import DataView
    from ..services.data_views import apply_view
    try:
        view = (await db.execute(
            select(DataView).where(DataView.org_id == org_id,
                                   DataView.is_default.is_(True)))).scalars().first()
        if view is None:
            return
        # The columns have been added to the session but not flushed, and
        # apply_view reads them back by name.
        await db.flush()
        await apply_view(db, ds, view.payload or {})
    except Exception:
        logger.exception("default data view could not be applied to dataset %s", ds.id)


@router.post("", response_model=DatasetOut)
async def upload_dataset(
    file: UploadFile = File(...),
    name: str = Form(...),
    description: str = Form(""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # An Access file holds many tables and so yields many datasets, which cannot
    # be returned as one DatasetOut. Rejecting here (rather than widening this
    # endpoint's response_model) keeps the single-file contract every existing
    # caller depends on.
    if Path(file.filename or "").suffix.lower() in upload_store.CONTAINER_SUFFIXES:
        raise HTTPException(
            400, "A Microsoft Access file contains multiple tables and produces "
                 "one dataset per table. Upload it via /api/v1/datasets/batch.")

    ds = await _ingest_upload_file(
        db, current_user.org_id, source_filename=file.filename, stream=file.file,
        name=name, description=description, owner_id=current_user.id)
    await db.commit()
    result = await db.execute(
        select(Dataset).options(selectinload(Dataset.columns)).where(Dataset.id == ds.id)
    )
    return result.scalar_one()


async def _ingest_access_file(
    db: AsyncSession, org_id: int, *, source_filename: str | None, stream,
    name: str, description: str, budget: "_SizeBudget | None" = None,
    owner_id: int | None = None,
) -> list[BatchUploadItem]:
    """Turn one uploaded .mdb/.accdb into one dataset per user table.

    Deliberately NOT routed through `ingest.SUPPORTED`: that dict maps a suffix
    to a reader returning ONE frame, and `frame_cache` memoises per path, so an
    Access file would half-work there and then poison the memo.

    Each table is exported to its own CSV, which then flows through exactly the
    same sidecar/typing machinery as any other upload -- so nothing downstream
    needs to know Access exists.
    """
    from ..services import mdb

    try:
        upload_store.allowed_suffix(source_filename)
    except ValueError as e:
        raise HTTPException(400, str(e))

    mdb_path = upload_store.allocate_path(org_id, source_filename)
    with open(mdb_path, "wb") as fh:
        shutil.copyfileobj(stream, fh)

    try:
        size = mdb_path.stat().st_size
        if size > settings.max_upload_mb * 1024 * 1024:
            raise HTTPException(400, f"File exceeds {settings.max_upload_mb} MB limit")
        if budget is not None:
            budget.charge(size)

        try:
            tables = await asyncio.to_thread(mdb.list_tables, str(mdb_path))
        except (mdb.MdbUnavailable, mdb.MdbReadError) as e:
            raise HTTPException(400, str(e))
        if not tables:
            raise HTTPException(400, "This Access file contains no user tables")

        items: list[BatchUploadItem] = []
        for table in tables:
            label = f"{source_filename or 'database'} → {table}"
            csv_path = None
            try:
                df = await asyncio.to_thread(mdb.read_table, str(mdb_path), table)
                if df.empty and not len(df.columns):
                    raise HTTPException(400, "table is empty")

                csv_path = upload_store.allocate_path(org_id, "table.csv")
                await asyncio.to_thread(lambda: df.to_csv(csv_path, index=False))
                csv_size = csv_path.stat().st_size
                try:
                    await quotas.enforce_storage_quota(db, org_id, csv_size)
                except quotas.QuotaExceeded as e:
                    raise HTTPException(e.status_code, str(e.detail))

                type_map = await asyncio.to_thread(detect_types, df)
                await asyncio.to_thread(write_parquet_sidecar, str(csv_path))

                ds = Dataset(name=f"{name} — {table}",
                             description=description or None,
                             filename=str(csv_path), row_count=len(df),
                             col_count=len(df.columns), file_size=csv_size,
                             org_id=org_id, created_by=owner_id)
                db.add(ds)
                await db.flush()
                for col_name, dtype in type_map.items():
                    db.add(DatasetColumn(
                        dataset_id=ds.id, name=col_name, dtype=dtype,
                        missing_pct=round(df[col_name].isnull().mean() * 100, 2),
                        stats={}))
                await db.commit()
                items.append(BatchUploadItem(
                    source_filename=label, status="created",
                    dataset=DatasetOut.model_validate(
                        await _load_dataset_out(db, ds.id))))
            except (HTTPException, mdb.MdbReadError) as e:
                # One unreadable table must not cost the other thirty-nine.
                await db.rollback()
                if csv_path is not None:
                    csv_path.unlink(missing_ok=True)
                detail = e.detail if isinstance(e, HTTPException) else str(e)
                items.append(BatchUploadItem(source_filename=label,
                                             status="error", error=str(detail)))
        return items
    finally:
        # The .mdb is a transport format: every table has been materialised as
        # its own CSV, nothing reads the original again, and keeping it would
        # count twice against the org's storage quota.
        mdb_path.unlink(missing_ok=True)


def _item_name(base: str, filename: str | None, only_one: bool) -> str:
    """The dataset name for one file of a batch.

    A single file keeps the name the user typed. Several files each get their
    own stem appended, because twenty datasets all called "Q3" would be
    indistinguishable in the list.
    """
    if only_one:
        return base
    stem = Path(filename or "file").stem or "file"
    # A stem the base already IS adds nothing but noise: the uploader seeds the
    # base from what the files share, so a batch of `qa_sample.csv` and
    # `qa_sample2.csv` would otherwise name the first one "qa_sample —
    # qa_sample". The other files still get their own stem, so the set stays
    # distinguishable.
    if stem.strip().casefold() == base.strip().casefold():
        return base
    return f"{base} — {stem}"


async def _load_dataset_out(db: AsyncSession, dataset_id: int) -> Dataset:
    return (await db.execute(
        select(Dataset).options(selectinload(Dataset.columns))
        .where(Dataset.id == dataset_id)
    )).scalar_one()


@router.post("/batch", response_model=BatchUploadOut)
async def upload_datasets(
    files: list[UploadFile] = File(...),
    name: str = Form(...),
    description: str = Form(""),
    mode: str = Form("separate"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload several files at once.

    `mode="separate"` makes one dataset per file. `mode="append"` concatenates
    them into a single dataset -- the union of their columns, NULL-filled where
    a file lacked one.

    Declared ABOVE `/{dataset_id}`: FastAPI matches in declaration order, and
    while that route is a GET (so there is no real conflict today), relying on
    the method to disambiguate a literal-vs-parameter collision is the kind of
    thing that breaks the day someone adds `POST /{dataset_id}`.

    Ingestion runs inline, as it does for a single upload, so a twenty-file
    batch is a long request rather than a job. That is a deliberate limit of
    this change, not an oversight -- `max_upload_files` and
    `max_batch_upload_mb` are what keep it bounded.
    """
    if mode not in ("separate", "append"):
        raise HTTPException(400, "mode must be 'separate' or 'append'")
    if not files:
        raise HTTPException(400, "No files uploaded")
    if len(files) > settings.max_upload_files:
        raise HTTPException(
            400, f"At most {settings.max_upload_files} files can be uploaded at once "
                 f"({len(files)} given)")

    budget = _SizeBudget(settings.max_batch_upload_mb)
    if mode == "append":
        return await _append_into_one(db, current_user.org_id, files=files,
                                      name=name, description=description,
                                      budget=budget, owner_id=current_user.id)

    items: list[BatchUploadItem] = []
    quota_hit = False
    only_one = len(files) == 1
    for f in files:
        suffix = Path(f.filename or "").suffix.lower()
        # Checked out here, not inside the try: an unsupported extension is
        # settled before any database work, so it must not reach the rollback
        # below. Rolling back for it would discard the caller's transaction
        # over a file we never touched the database for.
        try:
            upload_store.allowed_suffix(f.filename)
        except ValueError as e:
            items.append(BatchUploadItem(
                source_filename=f.filename or "", status="error", error=str(e)))
            continue

        try:
            if suffix in upload_store.CONTAINER_SUFFIXES:
                # One Access file fans out into one dataset per table, so it
                # contributes several items rather than one.
                items.extend(await _ingest_access_file(
                    db, current_user.org_id, source_filename=f.filename,
                    stream=f.file, name=_item_name(name, f.filename, only_one),
                    description=description, budget=budget,
                    owner_id=current_user.id))
                continue

            ds = await _ingest_upload_file(
                db, current_user.org_id, source_filename=f.filename, stream=f.file,
                name=_item_name(name, f.filename, only_one), description=description,
                budget=budget, owner_id=current_user.id)
            # Committed per file, and this is load-bearing: enforce_storage_quota
            # sums COMMITTED rows, so without it every file in the batch would
            # see the same pre-batch total and the org could overshoot its cap
            # by (N-1) files.
            await db.commit()
            items.append(BatchUploadItem(
                source_filename=f.filename or "", status="created",
                dataset=DatasetOut.model_validate(
                    await _load_dataset_out(db, ds.id))))
        except (HTTPException, quotas.QuotaExceeded) as e:
            await db.rollback()
            if e.status_code == 413:
                quota_hit = True
                # The batch ceiling is a property of the REQUEST, not of this
                # file: nothing after it can fit either, so stop rather than
                # reporting the same error N more times.
                items.append(BatchUploadItem(
                    source_filename=f.filename or "", status="error",
                    error=str(e.detail)))
                break
            items.append(BatchUploadItem(
                source_filename=f.filename or "", status="error",
                error=str(e.detail)))

    return _batch_result(items, "separate", quota_hit=quota_hit)


def _batch_result(items: list[BatchUploadItem], mode: str, *,
                  quota_hit: bool = False) -> BatchUploadOut:
    """Assemble the response, and choose a status code for the whole request.

    200 whenever anything was created -- partial success is success, and the
    per-item errors carry the rest. Total failure is a 400 (or 413 when a quota
    is what stopped it, so an org can tell "your files were bad" from "you are
    out of space") with the same body, so a client parses one shape either way.
    """
    created = sum(1 for i in items if i.status == "created")
    failed = len(items) - created
    body = BatchUploadOut(items=items, created=created, failed=failed, mode=mode)
    if created == 0:
        raise HTTPException(413 if quota_hit else 400,
                            body.model_dump(mode="json"))
    return body


async def _append_into_one(
    db: AsyncSession, org_id: int, *, files: list[UploadFile], name: str,
    description: str, budget: "_SizeBudget", owner_id: int | None = None,
) -> BatchUploadOut:
    """Concatenate several uploads into a single dataset.

    Each file is parsed from a temp path and then discarded -- only the combined
    CSV is kept, so the stored bytes match the dataset exactly and nothing is
    counted twice against the storage quota.

    `detect_types` runs on the COMBINED frame, never per file: it mutates its
    input (coercing date-like text) and classifies categoricals by a
    distinct-ratio, both of which need to see every row. Typing the parts
    separately would produce a type map that disagreed with the bytes written.
    """
    frames: list = []
    items: list[BatchUploadItem] = []
    quota_hit = False
    total_bytes = 0

    for f in files:
        # Settled before any I/O, so these never reach the handler below.
        if Path(f.filename or "").suffix.lower() in upload_store.CONTAINER_SUFFIXES:
            items.append(BatchUploadItem(
                source_filename=f.filename or "", status="error",
                error="A Microsoft Access file cannot be appended; upload it "
                      "with mode='separate' to get one dataset per table"))
            continue
        try:
            upload_store.allowed_suffix(f.filename)
        except ValueError as e:
            items.append(BatchUploadItem(source_filename=f.filename or "",
                                         status="error", error=str(e)))
            continue

        tmp = None
        try:
            tmp = upload_store.allocate_path(org_id, f.filename)
            with open(tmp, "wb") as fh:
                shutil.copyfileobj(f.file, fh)

            size = tmp.stat().st_size
            if size > settings.max_upload_mb * 1024 * 1024:
                raise HTTPException(400, f"File exceeds {settings.max_upload_mb} MB limit")
            budget.charge(size)
            total_bytes += size

            frames.append(await asyncio.to_thread(load_file, str(tmp)))
            items.append(BatchUploadItem(source_filename=f.filename or "",
                                         status="created"))
        except (HTTPException, quotas.QuotaExceeded) as e:
            items.append(BatchUploadItem(source_filename=f.filename or "",
                                         status="error", error=str(e.detail)))
            if e.status_code == 413:
                quota_hit = True
                break
        finally:
            if tmp is not None:
                tmp.unlink(missing_ok=True)

    if not frames:
        return _batch_result(items, "append", quota_hit=quota_hit)

    combined = await asyncio.to_thread(upload_store.concat_frames, frames)
    frames.clear()          # the merged copy is what matters now; free the parts

    try:
        await quotas.enforce_storage_quota(db, org_id, total_bytes)
    except quotas.QuotaExceeded as e:
        raise HTTPException(e.status_code, str(e.detail))

    final_path = upload_store.allocate_path(org_id, "combined.csv")
    await asyncio.to_thread(lambda: combined.to_csv(final_path, index=False))
    real_size = final_path.stat().st_size
    try:
        # The written CSV is rarely the same size as the sum of its inputs, so
        # re-check against what actually landed rather than the estimate.
        await quotas.enforce_storage_quota(db, org_id, real_size)
    except (HTTPException, quotas.QuotaExceeded) as e:
        final_path.unlink(missing_ok=True)
        raise HTTPException(getattr(e, "status_code", 413), str(e.detail))

    type_map = await asyncio.to_thread(detect_types, combined)
    await asyncio.to_thread(write_parquet_sidecar, str(final_path))

    ds = Dataset(name=name, description=description or None, filename=str(final_path),
                 row_count=len(combined), col_count=len(combined.columns),
                 file_size=real_size, org_id=org_id, created_by=owner_id)
    db.add(ds)
    await db.flush()
    for col_name, dtype in type_map.items():
        db.add(DatasetColumn(
            dataset_id=ds.id, name=col_name, dtype=dtype,
            missing_pct=round(combined[col_name].isnull().mean() * 100, 2), stats={}))
    await db.commit()

    out = DatasetOut.model_validate(await _load_dataset_out(db, ds.id))
    for item in items:
        if item.status == "created":
            item.dataset = out
    return _batch_result(items, "append", quota_hit=quota_hit)


@router.delete("/{dataset_id}", status_code=204)
async def delete_dataset(dataset_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    # Deleting is an authoring action. Where the dataset is a dataflow's output
    # the dataflow's grants decide, so deleting what a pipeline produced cannot
    # route around the pipeline's own permissions.
    await require_dataset_write(db, current_user, ds, "data")
    from ..services.dataset_cleanup import discard_dataset_artifacts
    # Aggregate datasets are the first dataset -> dataset cascade
    # (aggregate_of_dataset_id, ondelete=CASCADE): the DB removes their ROWS
    # with no application code running, so their files and failure rows are
    # only cleaned up because this sweeps them first.
    aggregates = (await db.execute(
        select(Dataset).where(Dataset.aggregate_of_dataset_id == ds.id))).scalars().all()
    await discard_dataset_artifacts(db, [ds, *aggregates])
    await audit(db, current_user, "dataset.delete", "dataset", ds.id, ds.name)
    await db.delete(ds)
    await db.commit()


# ── Calculated Columns ────────────────────────────────────────────────────────

@router.post("/{dataset_id}/columns/{column_name}/duplicate")
async def duplicate_column(
    dataset_id: int, column_name: str,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Duplicate a column as a calculated column referencing the original.

    SAS's standard way to get two aggregations or two date formats from one column:
    the copy is a real data item with its own default aggregation, format and
    granularity, while reading the original's values -- the backtick-quoted column is the identity
    expression, evaluated by the same engine as any calculated column.
    """
    ds = (await db.execute(
        select(Dataset).options(selectinload(Dataset.columns)).where(Dataset.id == dataset_id)
    )).scalar_one_or_none()
    check_org(ds, current_user, "Dataset not found")
    # Authoring gate. Open by default (`max_dataset_capability` returns "data"
    # unless every report using this dataset holds the role below it), so this
    # changes nothing for an ordinary install -- but until it was here the
    # control could not be applied AT ALL, and a member the admin had held to
    # "view" could still rewrite this dataset's model for everybody.
    await require_dataset_capability(db, current_user, dataset_id, "data")

    known = {c.name for c in ds.columns} | {c.get("name") for c in (ds.calculated_columns or [])}
    if column_name not in known:
        raise HTTPException(404, f"No column named {column_name!r}")

    # First free "name (copy)", "name (copy 2)", ... -- duplicating twice must not
    # produce two identically-named items, which nothing downstream could tell apart.
    base = f"{column_name} (copy)"
    new_name, n = base, 2
    while new_name in known:
        new_name, n = f"{column_name} (copy {n})", n + 1

    cols = list(ds.calculated_columns or [])
    cols.append({"name": new_name, "expression": f"`{column_name}`"})
    ds.calculated_columns = cols
    flag_modified(ds, "calculated_columns")
    await audit(db, current_user, "dataset.duplicate_column", "dataset", ds.id,
                f"{column_name} -> {new_name}")
    await db.commit()
    return {"name": new_name, "expression": f"`{column_name}`"}


EXPORT_DISABLED_KEY = "__exports_disabled__"
# Lives in Dataset.column_meta under a reserved key rather than as a real column:
# create_all never alters deployed tables, and column_meta is already a free-form
# JSON dict the org admin controls. The key is stripped from column listings.


_EXPORT_POLICY_FORMATS = {"csv", "tsv", "xlsx"}


@router.post("/{dataset_id}/export-policy")
async def set_export_policy(
    dataset_id: int, disabled: bool | None = None, body: dict | None = None,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Set one dataset's export policy. Org-admin only: export disablement is a
    governance control, and a control any user can flip is not one.

    Two grains (SAS's per-destination model):
      ?disabled=true|false      -- everything off / everything on (the original contract)
      JSON body {"formats": ["csv", ...], "auto_private": bool}
                                -- disable specific destinations, and/or disable
                                   automatically WHILE the dataset carries row- or
                                   column-security rules (checked live at export
                                   time, so adding a rule later closes exports
                                   without revisiting this policy)."""
    if not current_user.role.is_org_admin:
        raise HTTPException(403, "Only an organization admin can change export policy")
    ds = (await db.execute(select(Dataset).where(Dataset.id == dataset_id))).scalar_one_or_none()
    check_org(ds, current_user, "Dataset not found")
    if ds.aggregate_of_dataset_id is not None:
        raise HTTPException(400, "Export policy is inherited from the source dataset; set it there.")
    meta = dict(ds.column_meta or {})

    if body is not None and (body.get("formats") is not None or body.get("auto_private") is not None):
        formats = [f for f in (body.get("formats") or []) if f in _EXPORT_POLICY_FORMATS]
        if len(formats) != len(body.get("formats") or []):
            raise HTTPException(400, f"formats must be among {sorted(_EXPORT_POLICY_FORMATS)}")
        policy: dict = {}
        if formats:
            policy["formats"] = sorted(formats)
        if body.get("auto_private"):
            policy["auto_private"] = True
        if policy:
            meta[EXPORT_DISABLED_KEY] = policy
        else:
            meta.pop(EXPORT_DISABLED_KEY, None)
        summary = "exports policy: " + (", ".join(
            (["formats off: " + "/".join(policy["formats"])] if policy.get("formats") else [])
            + (["auto-disable when private"] if policy.get("auto_private") else [])) or "cleared")
    elif disabled is not None:
        if disabled:
            meta[EXPORT_DISABLED_KEY] = True
        else:
            meta.pop(EXPORT_DISABLED_KEY, None)
        summary = "exports disabled" if disabled else "exports enabled"
    else:
        raise HTTPException(400, "Provide ?disabled= or a policy body")

    ds.column_meta = meta
    flag_modified(ds, "column_meta")
    await audit(db, current_user, "dataset.export_policy", "dataset", ds.id, summary)
    from ..services import admin_audit
    await admin_audit.record(db, current_user, "export_policy.set", f"dataset:{ds.id}", summary)
    await db.commit()
    return {"export_policy": meta.get(EXPORT_DISABLED_KEY, False)}


@router.get("/{dataset_id}/export-policy")
async def get_export_policy(
    dataset_id: int,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    if not current_user.role.is_org_admin:
        raise HTTPException(403, "Only an organization admin can read export policy")
    ds = (await db.execute(select(Dataset).where(Dataset.id == dataset_id))).scalar_one_or_none()
    check_org(ds, current_user, "Dataset not found")
    policy_ds = await _policy_dataset(db, ds)
    return {"export_policy": (policy_ds.column_meta or {}).get(EXPORT_DISABLED_KEY, False),
            "has_security_rules": await _dataset_has_security(db, dataset_id),
            "inherited_from": policy_ds.id if policy_ds.id != ds.id else None}


async def _policy_dataset(db: AsyncSession, ds: Dataset) -> Dataset:
    """The dataset whose export policy governs `ds`: its SOURCE for an
    aggregate, itself otherwise. Resolved, never copied -- the same rule the
    security resolvers follow, so a policy change on the source applies to
    every aggregate at once."""
    from ..core.rls import _aggregate_source
    source_id, _spec = await _aggregate_source(db, ds.id)
    if source_id == ds.id:
        return ds
    source = await db.get(Dataset, source_id)
    if source is None:
        # The FK cascade (aggregate_of_dataset_id, ondelete=CASCADE) makes
        # this unreachable in practice -- deleting the source deletes every
        # aggregate of it in the same transaction. But a security resolver
        # defaults CLOSED, never open: falling back to `ds` here would
        # resolve the policy from the aggregate's own column_meta, which is
        # always {} (unrestricted), silently treating "the source is gone"
        # as "the source allows everything".
        raise HTTPException(404, "Dataset not found")
    return source


async def _dataset_has_security(db: AsyncSession, dataset_id: int) -> bool:
    """True when any row- or column-security rule targets this dataset -- the
    'private data present' signal auto_private keys off, evaluated LIVE.

    An aggregate dataset carries no rules of its own (core.rls._aggregate_source):
    it is governed exactly when its SOURCE is, so the check follows that link
    first -- otherwise a governed aggregate would read as unprotected here,
    letting materialize snapshot it rule-free and auto_private never trigger."""
    from ..core.rls import _aggregate_source
    from ..models.models import ColumnSecurityRule, RowSecurityRule
    dataset_id, _spec = await _aggregate_source(db, dataset_id)
    row = (await db.execute(select(RowSecurityRule.id).where(
        RowSecurityRule.dataset_id == dataset_id).limit(1))).scalar_one_or_none()
    if row is not None:
        return True
    col = (await db.execute(select(ColumnSecurityRule.id).where(
        ColumnSecurityRule.dataset_id == dataset_id).limit(1))).scalar_one_or_none()
    return col is not None


def _exports_disabled(ds: Dataset, fmt: str | None = None, has_security: bool = False) -> bool:
    """Is exporting `fmt` from this dataset forbidden right now?

    True (bool) forbids everything -- the original all-or-nothing contract.
    A dict policy forbids its listed formats, and, with auto_private, forbids
    everything WHILE security rules exist on the dataset (callers pass
    has_security from _dataset_has_security)."""
    pol = (ds.column_meta or {}).get(EXPORT_DISABLED_KEY)
    if pol is True:
        return True
    if isinstance(pol, dict):
        if pol.get("auto_private") and has_security:
            return True
        blocked = pol.get("formats") or []
        return (fmt in blocked) if fmt is not None else bool(blocked)
    return bool(pol)


@router.get("/{dataset_id}/export")
async def export_dataset(
    dataset_id: int, format: str = "csv",
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Download the whole dataset as CSV or TSV.

    Row-level security is applied exactly as it is for display: the file a restricted
    user downloads is the slice they can see, not the table on disk. Calculated
    columns are not materialised here -- this exports the dataset, and calculated
    columns belong to widgets that request them.
    """
    import io as _io
    import re as _re
    from fastapi.responses import StreamingResponse

    fmt = (format or "csv").lower()
    if fmt not in ("csv", "tsv"):
        raise HTTPException(400, f"Unsupported export format: {format}")

    ds = (await db.execute(select(Dataset).where(Dataset.id == dataset_id))).scalar_one_or_none()
    check_org(ds, current_user, "Dataset not found")
    await require_dataset_read(db, current_user, dataset_id)
    policy_ds = await _policy_dataset(db, ds)
    if _exports_disabled(policy_ds, fmt, await _dataset_has_security(db, dataset_id)):
        raise HTTPException(403, "Exports are disabled for this dataset")
    if ds.mode == "directquery" or not ds.filename:
        raise HTTPException(400, "Whole-table export is available for import-mode datasets only")

    df = await asyncio.to_thread(load_file, ds.filename)
    rls_expr = await resolve_rls_expr(db, current_user, dataset_id)
    if rls_expr:
        df = apply_filter_expr(df, rls_expr, silent=True)
    denied = await resolve_denied_columns(db, current_user, dataset_id)
    if denied:
        df = df.drop(columns=[c for c in denied if c in df.columns])
    from ..services.prep import apply_prep_steps, prep_steps_of, resolve_join_frames
    _ex_steps = prep_steps_of(ds)
    _ex_aux = await resolve_join_frames(db, current_user, _ex_steps) if _ex_steps else {}
    df = await asyncio.to_thread(apply_prep_steps, df, _ex_steps, _ex_aux)
    if ds.default_filter_expr:
        df = apply_filter_expr(df, ds.default_filter_expr, silent=True)

    # Exports are the audit-worthy READ: they move data out of the org boundary.
    await audit(db, current_user, "dataset.export", "dataset", ds.id, f"{fmt}, {len(df)} rows")
    await db.commit()

    sep = "	" if fmt == "tsv" else ","
    payload = df.to_csv(index=False, sep=sep).encode("utf-8-sig")
    name = _re.sub(r"[^A-Za-z0-9 _.-]", "", ds.name or "dataset").strip()[:60] or "dataset"
    media = "text/tab-separated-values" if fmt == "tsv" else "text/csv"
    return StreamingResponse(
        _io.BytesIO(payload), media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{name}.{fmt}"'},
    )


@router.get("/{dataset_id}/calculated-columns")
async def list_calculated_columns(dataset_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    return ds.calculated_columns or []


@router.put("/{dataset_id}/calculated-columns")
async def save_calculated_column(dataset_id: int, col: CalcColumnDef, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    await require_dataset_capability(db, current_user, dataset_id, "data")
    cols = [c for c in (ds.calculated_columns or []) if c.get('name') != col.name]
    cols.append(col.model_dump())
    ds.calculated_columns = cols
    flag_modified(ds, 'calculated_columns')
    await db.commit()
    return cols


async def _refuse_if_referenced(db: AsyncSession, ds: Dataset, name: str, force: bool):
    """A measure or calculated column that something still names is not
    deleted unless the caller said `force`. Deleting it anyway used to leave
    every widget that named it silently showing a ROW COUNT (shape_series'
    no-measure branch) -- E05: a change shows its consequences first."""
    from fastapi.responses import JSONResponse
    from ..services.dependencies import describe, find_dependents
    dependents = await find_dependents(db, ds, name)
    if dependents and not force:
        return JSONResponse(status_code=409, content={
            "detail": f"'{name}' is {describe(dependents)}. Delete anyway with ?force=true.",
            "dependents": dependents})
    return None


@router.get("/{dataset_id}/dependents")
async def dataset_dependents(dataset_id: int, name: str, db: AsyncSession = Depends(get_db),
                             current_user: User = Depends(get_current_user)):
    """Everything that references `name` (a column, calculated column or
    measure) on this dataset: widgets, other expressions, alerts, hierarchies,
    filters and aggregates. What a change to it would touch."""
    from ..services.dependencies import find_dependents
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    await require_dataset_read(db, current_user, dataset_id)
    return {"name": name, "dependents": await find_dependents(db, ds, name)}


@router.delete("/{dataset_id}/calculated-columns/{col_name}")
async def delete_calculated_column(dataset_id: int, col_name: str, force: bool = False, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    await require_dataset_capability(db, current_user, dataset_id, "data")
    refused = await _refuse_if_referenced(db, ds, col_name, force)
    if refused is not None:
        return refused
    cols = [c for c in (ds.calculated_columns or []) if c.get('name') != col_name]
    ds.calculated_columns = cols
    flag_modified(ds, 'calculated_columns')
    await db.commit()
    return cols


@router.post("/{dataset_id}/calculated-columns/preview")
async def preview_calculated_column(dataset_id: int, req: CalcColumnPreviewRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    if not ds.filename:
        raise HTTPException(404, "Dataset not found")
    rls_expr = await resolve_rls_expr(db, current_user, dataset_id)
    from ..services.prep import prep_steps_of, resolve_join_frames
    _cp_steps = prep_steps_of(ds)
    _cp_aux = await resolve_join_frames(db, current_user, _cp_steps) if _cp_steps else {}
    return await asyncio.to_thread(preview_expression, ds.filename, req.expression, 8, rls_expr,
                                   _cp_steps, _cp_aux, custom_functions=ds.custom_functions)


# ── Measures (post-aggregation) ───────────────────────────────────────────────

async def _validate_measure(measure: MeasureDef, ds: Dataset, db: AsyncSession) -> None:
    """Reject a measure that could never resolve, at save time rather than at render.

    Three failure modes are caught here: an unsafe expression, a name that collides
    with a real column (shape_series resolves columns first, so the measure would be
    unreachable), and a reference to another measure (needs dependency ordering and
    cycle detection, which is not built yet)."""
    from ..services.widget_data import _validate_expr_safety
    import ast

    try:
        _validate_expr_safety(measure.expression)
    except ValueError as e:
        raise HTTPException(400, str(e))

    result = await db.execute(select(DatasetColumn.name).where(DatasetColumn.dataset_id == ds.id))
    column_names = {r[0] for r in result.all()}
    calc_names = {c.get("name") for c in (ds.calculated_columns or [])}
    custom_function_names = {f.get("name") for f in (ds.custom_functions or [])}

    if measure.name in column_names or measure.name in calc_names:
        raise HTTPException(400, f"'{measure.name}' is already a column on this dataset — pick another name")
    if measure.name in custom_function_names:
        raise HTTPException(400, f"'{measure.name}' is already a custom function on this dataset — pick another name")

    other_measures = {m.get("name") for m in (ds.measures or []) if m.get("name") != measure.name}
    referenced = {n.id for n in ast.walk(ast.parse(measure.expression, mode="eval")) if isinstance(n, ast.Name)}
    if referenced & other_measures:
        clash = sorted(referenced & other_measures)[0]
        raise HTTPException(400, f"A measure cannot reference another measure ('{clash}') yet")


@router.get("/{dataset_id}/measures")
async def list_measures(dataset_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    return ds.measures or []


@router.post("/{dataset_id}/measures")
async def save_measure(dataset_id: int, measure: MeasureDef, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    await require_dataset_capability(db, current_user, dataset_id, "data")
    await _validate_measure(measure, ds, db)
    items = [m for m in (ds.measures or []) if m.get("name") != measure.name]
    items.append(measure.model_dump(exclude_none=True))
    ds.measures = items
    flag_modified(ds, "measures")
    await db.commit()
    return items


@router.delete("/{dataset_id}/measures/{measure_name}")
async def delete_measure(dataset_id: int, measure_name: str, force: bool = False, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    await require_dataset_capability(db, current_user, dataset_id, "data")
    refused = await _refuse_if_referenced(db, ds, measure_name, force)
    if refused is not None:
        return refused
    items = [m for m in (ds.measures or []) if m.get("name") != measure_name]
    ds.measures = items
    flag_modified(ds, "measures")
    await db.commit()
    return items


@router.post("/{dataset_id}/measures/preview")
async def preview_measure_expr(dataset_id: int, req: MeasurePreviewRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    if not ds.filename:
        raise HTTPException(404, "Dataset not found")
    rls_expr = await resolve_rls_expr(db, current_user, dataset_id)
    # Column security too, not just row security. Without this, previewing
    # SUM(<denied column>) computed the exact aggregate the rule hides --
    # verified live before the fix. Dropping the column makes the evaluator
    # report it as unknown, which is the honest answer for this caller.
    denied = await resolve_denied_columns(db, current_user, dataset_id)

    from ..services.prep import apply_prep_steps, prep_steps_of, resolve_join_frames
    _mp_steps = prep_steps_of(ds)
    _mp_aux = await resolve_join_frames(db, current_user, _mp_steps) if _mp_steps else {}

    def _run():
        from ..services.measure_eval import preview_measure
        from ..services.widget_data import apply_rls_filter, apply_calculated_columns
        df = load_file(ds.filename)
        df = apply_rls_filter(df, rls_expr)
        df = apply_prep_steps(df, _mp_steps, _mp_aux)
        present = [c for c in denied if c in df.columns]
        if present:
            df = df.drop(columns=present)
        if ds.default_filter_expr:
            df = apply_filter_expr(df, ds.default_filter_expr, silent=True)
        if ds.calculated_columns:
            df = apply_calculated_columns(df, ds.calculated_columns, ds.custom_functions)
        return preview_measure(req.expression, df, req.group_by)

    return await asyncio.to_thread(_run)


# ── Custom functions ──────────────────────────────────────────────────────────

@router.get("/{dataset_id}/custom-functions")
async def list_custom_functions(dataset_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    return ds.custom_functions or []


@router.put("/{dataset_id}/custom-functions")
async def save_custom_function(dataset_id: int, fn: CustomFunctionDef, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    from ..services.custom_functions import CustomFunctionError, validate_custom_function_def
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    await require_dataset_capability(db, current_user, dataset_id, "data")

    result = await db.execute(select(DatasetColumn.name).where(DatasetColumn.dataset_id == ds.id))
    column_names = {r[0] for r in result.all()}
    calc_names = {c.get("name") for c in (ds.calculated_columns or [])}
    measure_names = {m.get("name") for m in (ds.measures or [])}
    existing = {f["name"]: f for f in (ds.custom_functions or []) if f.get("name") != fn.name}

    try:
        validate_custom_function_def(fn.name, fn.params, fn.expression,
                                      column_names, calc_names, measure_names, existing)
    except CustomFunctionError as e:
        raise HTTPException(400, str(e))

    items = [f for f in (ds.custom_functions or []) if f.get("name") != fn.name]
    items.append(fn.model_dump())
    ds.custom_functions = items
    flag_modified(ds, "custom_functions")
    await db.commit()
    return items


@router.delete("/{dataset_id}/custom-functions/{name}")
async def delete_custom_function(dataset_id: int, name: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    await require_dataset_capability(db, current_user, dataset_id, "data")
    items = [f for f in (ds.custom_functions or []) if f.get("name") != name]
    ds.custom_functions = items
    flag_modified(ds, "custom_functions")
    await db.commit()
    return items


@router.post("/{dataset_id}/custom-functions/preview")
async def preview_custom_function(dataset_id: int, req: CustomFunctionPreviewRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    from ..services.custom_functions import CustomFunctionError, validate_custom_function_def
    from ..services.widget_data import _eval_expr, _safe
    import pandas as pd

    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")

    try:
        validate_custom_function_def("__preview__", req.params, req.expression, set(), set(), set(), {})
    except CustomFunctionError as e:
        return {"ok": False, "error": str(e)}

    try:
        row = {p: [req.sample_values.get(p)] for p in req.params}
        df = pd.DataFrame(row) if row else pd.DataFrame({"_": [0]})
        result = _eval_expr(req.expression, df)
        value = result.iloc[0] if hasattr(result, "iloc") else result
        return {"ok": True, "result": _safe(value)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.patch("/{dataset_id}/refresh-schedule", response_model=DatasetOut)
async def set_refresh_schedule(dataset_id: int, req: RefreshScheduleUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Set or clear a dataset's automatic refresh interval. None clears it."""
    from ..services.prep import derived_from_of
    from ..services.refresh_scheduler import MIN_INTERVAL_MINUTES

    result = await db.execute(
        select(Dataset).options(selectinload(Dataset.columns)).where(Dataset.id == dataset_id)
    )
    ds = result.scalar_one_or_none()
    check_org(ds, current_user, "Dataset not found")
    await require_dataset_write(db, current_user, ds, "edit")

    if req.interval_minutes is not None:
        if ds.mode == "directquery":
            raise HTTPException(400, "DirectQuery datasets read the live source on every query — there is nothing to schedule")
        # A DERIVED dataset has no connection by design -- it refreshes by
        # replaying the recipe in `__derived_from__`, which is exactly what
        # `due_datasets` admits it for. Requiring a data_source_id here would
        # make scheduled materialization unreachable from the UI.
        if not ds.data_source_id and derived_from_of(ds) is None:
            raise HTTPException(400, "This dataset was not imported from a database connection and has no recipe to replay")
        if req.interval_minutes < MIN_INTERVAL_MINUTES:
            raise HTTPException(400, f"Minimum refresh interval is {MIN_INTERVAL_MINUTES} minutes")

    ds.refresh_interval_minutes = req.interval_minutes
    await db.commit()
    # Re-select rather than db.refresh(): refresh expires the eagerly-loaded
    # `columns` relationship, and serializing DatasetOut would then try to lazy-load
    # it outside async context and raise MissingGreenlet.
    result = await db.execute(
        select(Dataset).options(selectinload(Dataset.columns)).where(Dataset.id == dataset_id)
    )
    return result.scalar_one()


# ── Column metadata (data item properties) ────────────────────────────────────

#: `geography` is a CATEGORY that also says what it is a category OF, so a map
#: built on it inherits its boundary set instead of asking the author again on
#: every widget. Everything that groups, filters, sorts or counts treats it as
#: an ordinary category -- `isNumericField` and the shapers only ever ask
#: whether the role is "measure".
#: What a column IS, for every engine that reads it. The canonical spellings --
#: what gets STORED -- plus the aliases accepted on write below.
#:
#: This set used to be {measure, category, geography} while
#: `insights._ROLE_TO_ANALYSIS_KIND` already read `timestamp` and `identifier`.
#: The engine understood two classifications that no endpoint could set: an
#: author could see `student_id` charted as a measure and had no way to say it
#: was an identifier. A vocabulary the reader knows and the writer refuses is a
#: feature that exists only in the code.
_VALID_ROLES = {"measure", "category", "temporal", "geography", "freetext",
                "identifier"}

#: Accepted on write, stored as the canonical spelling. One key per concept in
#: storage is what keeps the readers simple -- every consumer looks up exactly
#: one string, and a dataset labelled `dimension` behaves identically to one
#: labelled `category` because they are the same row after this map.
_ROLE_ALIASES = {
    "categorical": "category",
    "dimension": "category",
    "numeric": "measure",
    "datetime": "temporal",
    "timestamp": "temporal",
    "geo": "geography",
    "text": "freetext",
}


def _canonical_role(role: str | None) -> str | None:
    """The stored spelling for a role a caller sent, or the value unchanged.

    Validation happens after this, so an unknown value still fails loudly --
    canonicalising never turns a typo into a silent acceptance.
    """
    if role is None:
        return None
    return _ROLE_ALIASES.get(role.strip().lower(), role.strip().lower())

# Mirrors the names widget_data's _agg_series / _pandas_agg_fn actually accept, plus
# 'pct' which shape_series handles in its own branch. Anything outside this set would
# be silently ignored at query time and fall back to sum.
_VALID_AGGREGATIONS = {
    "sum", "avg", "mean", "average", "min", "minimum", "max", "maximum", "median",
    "count", "frequency", "countd", "distinct", "nunique", "std", "stdev",
    "variance", "var", "range", "p25", "p75", "p90", "p95", "pct",
    "none", "raw", "first",
    # The statistical half of SAS's aggregation menu. Each returns nothing when
    # the group cannot support it -- skewness of two points and a t statistic of
    # one are artefacts of the formula, not numbers.
    "stderr", "sem", "standard_error", "skewness", "skew", "kurtosis", "kurt",
    "cv", "coefficient_of_variation", "uss", "uncorrected_sum_of_squares",
    "css", "corrected_sum_of_squares", "tstat", "t_statistic", "pvalue", "p_value",
}


class ColumnDescriptionIn(BaseModel):
    """What this column means, in a person's words."""
    description: str = Field(max_length=2000)


@router.patch("/{dataset_id}/columns/{column}/description")
async def set_column_description(dataset_id: int, column: str,
                                 body: ColumnDescriptionIn,
                                 db: AsyncSession = Depends(get_db),
                                 current_user: User = Depends(get_current_user)):
    """Describe a column, and write it where the description BELONGS.

    A column that came from a connected table is described once, on the source
    catalog, and every dataset ever built from that table reads the same
    sentence -- which is the whole reason `services/knowledge.py` resolves
    through provenance instead of copying text onto each dataset. Writing the
    edit back to the dataset row instead would create exactly the divergence
    that arrangement exists to prevent: two datasets from one table, each
    describing `status` differently, with no way to tell which is current.

    So: a LINKED column writes to its source column at `confirmed`, the terminal
    rung of the precedence ladder, where no later sync may overwrite it. An
    unlinked column -- an upload, a query whose output matched nothing -- writes
    to the dataset row, because there is nowhere else for it to go.

    The response names where it landed, so the UI can tell the person their
    sentence now describes this column for everybody rather than letting them
    discover that later.
    """
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    await require_dataset_read(db, current_user, dataset_id)
    # The same authoring gate `column-meta` uses: describing a column edits the
    # dataset's model, and a member held to "view" must not rewrite it.
    await require_dataset_capability(db, current_user, dataset_id, "data")

    denied = set(await resolve_denied_columns(db, current_user, dataset_id))
    if column in denied:
        # Never confirm the existence of a column this role may not see.
        raise HTTPException(404, "Column not found on this dataset")

    col = (await db.execute(select(DatasetColumn).where(
        DatasetColumn.dataset_id == dataset_id,
        DatasetColumn.name == column))).scalar_one_or_none()
    if col is None:
        raise HTTPException(404, "Column not found on this dataset")

    text = body.description.strip()

    if col.source_column_id is not None:
        src = await db.get(SourceColumn, col.source_column_id)
        if src is not None:
            obj = await db.get(SourceObject, src.source_object_id)
            # Org scope is not implied by the link: check it rather than trust
            # it, the way every other cross-object write here does.
            if obj is not None and obj.org_id == current_user.org_id:
                src.description = text or None
                src.description_source = "confirmed" if text else None
                await db.commit()
                return {"written_to": "source", "shared": True,
                        "object": obj.name, "column": src.name}

    col.description = text or None
    col.description_source = "confirmed" if text else None
    await db.commit()
    return {"written_to": "dataset", "shared": False,
            "object": ds.name, "column": col.name}


@router.get("/{dataset_id}/column-meta")
async def get_column_meta(dataset_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    return ds.column_meta or {}


@router.put("/{dataset_id}/column-meta")
async def set_column_meta(dataset_id: int, req: ColumnMetaUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Replaces the whole map. That is deliberate: it makes a bulk edit across many
    columns one request, and lets a property be cleared by omitting it rather than
    needing a separate delete."""
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    # Authoring gate. Open by default (`max_dataset_capability` returns "data"
    # unless every report using this dataset holds the role below it), so this
    # changes nothing for an ordinary install -- but until it was here the
    # control could not be applied AT ALL, and a member the admin had held to
    # "view" could still rewrite this dataset's model for everybody.
    await require_dataset_capability(db, current_user, dataset_id, "data")

    result = await db.execute(select(DatasetColumn.name).where(DatasetColumn.dataset_id == dataset_id))
    known = {r[0] for r in result.all()}
    known |= {c.get("name") for c in (ds.calculated_columns or [])}
    known |= {m.get("name") for m in (ds.measures or [])}

    for col, meta in req.meta.items():
        if col.startswith("__"):
            # Reserved keys (__exports_disabled__, __prep_steps__) have their own
            # routes and their own permission story -- this one must not become a
            # side door to them.
            raise HTTPException(400, f"'{col}' is a reserved key")
        if col not in known:
            raise HTTPException(400, f"'{col}' is not a column on this dataset")
        if meta.role is not None:
            meta.role = _canonical_role(meta.role)
            if meta.role not in _VALID_ROLES:
                raise HTTPException(
                    400, f"role must be one of {sorted(_VALID_ROLES)}, got '{meta.role}'")
        if meta.target_candidate_priority is not None and meta.target_candidate_priority < 0:
            raise HTTPException(400, "target_candidate_priority must be zero or more")
        if meta.boundary_set_id is not None and meta.boundary_set_id < 1:
            raise HTTPException(400, "boundary_set_id must be a positive id")
        if meta.aggregation is not None and meta.aggregation not in _VALID_AGGREGATIONS:
            # A bad aggregation would be silently ignored at query time and render a
            # plausible-looking wrong number, so refuse it at write time.
            raise HTTPException(400, f"unknown aggregation '{meta.aggregation}'")

    # Replace only the per-column entries; reserved __keys (export policy, prep
    # steps) survive a bulk column edit -- wholesale replacement would silently
    # re-enable exports or drop the prep pipeline.
    preserved = {k: v for k, v in (ds.column_meta or {}).items() if k.startswith("__")}
    ds.column_meta = {**preserved,
                      **{c: m.model_dump(exclude_none=True) for c, m in req.meta.items()}}
    flag_modified(ds, "column_meta")
    await db.commit()
    return ds.column_meta


# ── Insights engine ──────────────────────────────────────────────────────────

@router.post("/{dataset_id}/suggest-dashboards")
async def suggest_dashboards(dataset_id: int, req: SuggestDashboardsRequest,
                             db: AsyncSession = Depends(get_db),
                             current_user: User = Depends(get_current_user)):
    """Whole dashboards proposed for this dataset and this person.

    Two engines behind one endpoint, chosen by whether the person described
    themselves. With a goal, the model tailors to their own words. WITHOUT one
    there is nothing to tailor to, and a model would spend 25 seconds and a
    network round trip producing the generic answer the statistics engine
    produces instantly, deterministically, and with each finding's own numbers
    in the caption. So an empty box changes the ENGINE, not just the prompt.

    `require_dataset_read` and not merely `check_org`: this endpoint does not
    just read a dataset, it sends a profile carrying SAMPLE VALUES to a model,
    and belonging to the same org is not permission to read.

    Every widget in every proposal has been EXECUTED before it is offered --
    `row_count` is that evidence. A proposal that renders blank costs the
    person the time to accept it and the confusion of debugging it.
    """
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    await require_dataset_read(db, current_user, dataset_id)
    if not ds.filename and ds.mode != "directquery":
        raise HTTPException(400, "This dataset has no rows to suggest from yet")

    denied = await resolve_denied_columns(db, current_user, dataset_id)
    rls_expr = await resolve_rls_expr(db, current_user, dataset_id)
    from ..services.prep import apply_prep_steps, prep_steps_of, resolve_join_frames
    _steps = prep_steps_of(ds)
    _aux = await resolve_join_frames(db, current_user, _steps) if _steps else {}

    from ..services import analysis_frame as frames

    live: "frames.AnalysisFrame | None" = None
    if ds.mode == "directquery":
        try:
            live = await frames.load_directquery_frame(
                db, ds, rls_filter_expr=rls_expr, denied=set(denied))
        except frames.FrameUnavailable as exc:
            raise HTTPException(400, str(exc))

    def _load():
        from ..services.widget_data import apply_calculated_columns, apply_rls_filter
        if live is not None:
            df = live.frame
            if ds.calculated_columns:
                df = apply_calculated_columns(df, ds.calculated_columns,
                                              ds.custom_functions)
            return df
        df = load_file(ds.filename)
        df = apply_rls_filter(df, rls_expr)
        df = apply_prep_steps(df, _steps, _aux)
        # Dropped BEFORE profiling, not filtered out of the answer: the
        # profile is what goes to the model, and a column this role may not
        # see must never be in it.
        if denied:
            df = df.drop(columns=[c for c in denied if c in df.columns])
        if ds.calculated_columns:
            df = apply_calculated_columns(df, ds.calculated_columns, ds.custom_functions)
        return df

    try:
        df = await asyncio.to_thread(_load)
    except FileNotFoundError:
        raise HTTPException(404, "Dataset file not found on server")

    from ..services.analytics import detect_types
    from ..services.dataset_profile import build_profile
    from ..services.suggest_dataset_dashboard import suggest_for_dataset
    from ..services.widget_data import get_widget_data_from_df

    type_map = await asyncio.to_thread(detect_types, df)
    profile = await asyncio.to_thread(
        build_profile, df, type_map, ds.column_meta or {})

    async def probe(widget_type: str, config: dict) -> dict:
        """Run one proposed widget exactly as the browser will.

        On the already-secured frame, so a probe can never see more than the
        person asking would. Off the event loop: the shaping is pandas work.

        For a DirectQuery dataset the browser does NOT go through this frame --
        it goes through `direct_query`, which pushes the aggregate into SQL and
        refuses anything that is not grain-safe. So the engine's own planner is
        asked first. Without this the probe proves a widget draws in pandas and
        the dashboard then renders "aggregation 'count' is not yet supported",
        which is the promise "every widget has been executed" quietly becoming
        false for half the datasets in the product.
        """
        if ds.mode == "directquery":
            from ..services.direct_query import DirectQueryUnsupported, plan_query
            try:
                plan_query(config, widget_type)
            except DirectQueryUnsupported as exc:
                # Reported rather than returned empty: "nothing to draw" would
                # blame the data for what is a property of this dataset's MODE,
                # and the person would go looking in the wrong place.
                return {"unsupported": str(exc)}
            except Exception:                            # noqa: BLE001
                # A planner that raised for any other reason has not proved the
                # widget unusable; fall through and let the frame decide.
                pass
        return await asyncio.to_thread(
            get_widget_data_from_df, df, config, widget_type,
            ds.measures or [])

    # What the platform KNOWS about these columns, resolved out of the source
    # catalog through each column's provenance. Without it the designer sees
    # `status (categorical, 3 distinct)` and picks a chart that is valid and
    # meaningless; with it, it sees what the column is for and what 2 means.
    # `denied` is passed so a column this role may not see cannot arrive in the
    # prompt wearing a description -- the same rule that dropped it from the
    # frame above.
    from ..services import knowledge as knowledge_service
    know = await knowledge_service.for_dataset(db, ds, denied=denied)

    goal = (req.goal or "").strip()
    if goal:
        proposals, reason = await suggest_for_dataset(
            profile, goal, req.count, probe=probe, knowledge=know)
        source = "model"
    else:
        proposals, reason = await _suggest_from_insights(
            df, type_map, ds, probe)
        source = "insights"

    # Nothing to offer? Ask, rather than leaving the person rereading their own
    # sentence wondering which part of it was wrong. Same shape as the agent's
    # D4.3 clarify node: a refusal is a dead end, a question is a next step.
    question = None
    if not proposals and goal:
        from ..services.suggest_dataset_dashboard import clarifying_question
        question = await clarifying_question(goal, reason, profile)

    measured = (live or frames.imported_frame(df))
    return {"proposals": [{**p, "source": source} for p in proposals],
            "reason": reason, "question": question,
            "profile": profile, "source": source,
            # Which rows the proposals were designed from. A dashboard proposed
            # off a sample is still a good dashboard; presenting it as though it
            # had seen everything is what would not be.
            "measured": {"origin": measured.origin,
                         "rows_analysed": measured.rows_analysed,
                         "total_rows": measured.total_rows,
                         "sampled": measured.sampled,
                         "description": measured.describe()}}


async def _suggest_from_insights(df, type_map: dict, ds: Dataset, probe) -> tuple[list[dict], str]:
    """One proposal, chosen by the statistics engine rather than a model.

    The findings are already ranked by how interesting they are and each
    carries its own sentence, so the captions state the numbers behind them --
    which is the half a generic model answer cannot do.

    Probed like any other proposal: this engine is more careful than a model
    but not infallible, and the promise that every offered widget has drawn is
    the same promise either way.
    """
    from ..services.insights import (effective_roles, generate_insights,
                                     suggest_widgets_from_findings)
    from ..services.suggest_dataset_dashboard import _probe

    result = await asyncio.to_thread(
        generate_insights, df, type_map, ds.column_meta or {})
    roles = effective_roles(type_map, ds.column_meta or {})
    ineligible = {name for name, entry in (ds.column_meta or {}).items()
                  if isinstance(entry, dict)
                  and entry.get("eligible_for_suggestion") is False}
    suggested = suggest_widgets_from_findings(
        result.get("findings") or [], roles, ds.description,
        ineligible=ineligible)

    widgets: list[dict] = []
    dropped: list[str] = []
    for suggestion in suggested:
        widget = {"widget_type": suggestion.get("widget_type"),
                  "title": suggestion.get("title") or "",
                  "why": suggestion.get("reason") or "",
                  "config": suggestion.get("config") or {}}
        drew, rows, _why = await _probe(widget, probe)
        if not drew:
            dropped.append("{}: returned nothing to draw".format(widget["title"]))
            continue
        widgets.append({**widget, "row_count": rows})

    if not widgets:
        return [], ("nothing the statistics engine found could be drawn: "
                    + "; ".join(dropped[:4]) if dropped
                    else "the statistics engine found nothing worth charting")
    proposal = {
        "title": "What stands out in {}".format(ds.name),
        "rationale": result.get("narrative")
                     or "Ranked by what the statistics engine found most interesting.",
        "widgets": widgets,
    }
    return [proposal], ("; ".join(dropped[:6]) if dropped else "")


@router.post("/{dataset_id}/insights")
async def dataset_insights(dataset_id: int, db: AsyncSession = Depends(get_db),
                           current_user: User = Depends(get_current_user)):
    """Unprompted ranked findings over the secured frame -- trends, standouts,
    laggards, correlations, outlier impact and data-quality flags, each carrying
    the numbers its sentence states, plus a one-paragraph narrative."""
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    # A DirectQuery dataset is read live, bounded by `analysis_row_cap`; an
    # import dataset is read from its file. Both end as a frame, which is all
    # any detector has ever wanted. What is still refused is a dataset with
    # neither -- no file and no connection is genuinely nothing to analyse.
    if not ds.filename and ds.mode != "directquery":
        raise HTTPException(400, "This dataset has no rows to analyse yet")
    denied = await resolve_denied_columns(db, current_user, dataset_id)
    rls_expr = await resolve_rls_expr(db, current_user, dataset_id)
    from ..services.prep import apply_prep_steps, prep_steps_of, resolve_join_frames
    _steps = prep_steps_of(ds)
    _aux = await resolve_join_frames(db, current_user, _steps) if _steps else {}

    # What the business calls these columns and what their coded values mean, so
    # a finding reads "paid orders carry 62% of revenue" rather than "2 carries
    # 62% of amount". The numbers are unchanged -- only the words around them.
    # Resolved out here because it is database work, and never fatal: a finding
    # in the schema's words is still a finding.
    from ..services import knowledge as knowledge_service
    try:
        _know = await knowledge_service.for_dataset(db, ds, denied=set(denied))
        _labels = {n: c.description for n, c in _know.columns.items()
                   if c.description and len(c.description) <= 60}
        _value_labels = {n: c.enum_labels for n, c in _know.columns.items()
                         if c.enum_labels}
    except Exception:                                    # noqa: BLE001
        logger.warning("could not resolve labels for dataset %s insights",
                       dataset_id, exc_info=True)
        _labels, _value_labels = {}, {}

    from ..services import analysis_frame as frames

    # Read live, before the thread: row-level security travels WITH the query
    # here rather than being applied to a frame afterwards, which is why this
    # adds no `apply_rls_filter` call site.
    live: "frames.AnalysisFrame | None" = None
    if ds.mode == "directquery":
        try:
            live = await frames.load_directquery_frame(
                db, ds, rls_filter_expr=rls_expr, denied=set(denied))
        except frames.FrameUnavailable as exc:
            raise HTTPException(400, str(exc))

    def _run():
        from ..services.analytics import detect_types
        from ..services.insights import generate_insights
        from ..services.widget_data import apply_calculated_columns, apply_rls_filter
        if live is not None:
            df = live.frame
            provenance = live
        else:
            df = load_file(ds.filename)
            df = apply_rls_filter(df, rls_expr)
            df = apply_prep_steps(df, _steps, _aux)
            if denied:
                df = df.drop(columns=[c for c in denied if c in df.columns])
            provenance = frames.imported_frame(df)
        if ds.calculated_columns:
            df = apply_calculated_columns(df, ds.calculated_columns, ds.custom_functions)
        result = generate_insights(df, detect_types(df), ds.column_meta or {},
                                   labels=_labels, value_labels=_value_labels)
        # Said, not implied. A reader comparing two datasets deserves to know
        # one was measured over every row and the other over a sample -- and
        # `insights.py` promises every number is computed rather than guessed,
        # which only stays true if a sampled number says so.
        result["measured"] = {
            "origin": provenance.origin,
            "rows_analysed": provenance.rows_analysed,
            "total_rows": provenance.total_rows,
            "sampled": provenance.sampled,
            "description": provenance.describe(),
        }
        return result

    try:
        result = await asyncio.to_thread(_run)
    except FileNotFoundError:
        raise HTTPException(404, "Dataset file not found on server — please re-upload the file")

    # ── Novelty: what changed since the last scan ─────────────────────────────
    # Restricted callers are excluded from BOTH sides, mirroring the
    # AnalysisResult rule in routers/analysis.py: their scan must not be
    # written to the shared org-wide row, and comparing their restricted scan
    # against an unrestricted baseline would flag "changes" that are really
    # just the rows their rules hide -- an inference channel about hidden data
    # dressed as a NEW badge.
    if not rls_expr and not denied:
        from ..services.insights import apply_novelty

        prev_row = (await db.execute(
            select(AnalysisResult).where(
                AnalysisResult.dataset_id == dataset_id,
                AnalysisResult.analysis_type == "insights_scan",
            ))).scalar_one_or_none()
        previous = (prev_row.result or {}).get("findings") if prev_row else None

        # The RAW scan is persisted (pre-boost scores), and persisted BEFORE
        # the annotations are applied to the response: storing boosted scores
        # would compound the boost on every run, and storing novelty labels
        # would compare next run's findings against this run's opinions
        # instead of its facts.
        raw = {"findings": result["findings"]}
        if prev_row:
            prev_row.result = raw
            prev_row.created_at = datetime.utcnow()
        else:
            db.add(AnalysisResult(dataset_id=dataset_id,
                                  analysis_type="insights_scan", result=raw))
        await db.commit()

        result = {**result, "findings": apply_novelty(result["findings"], previous)}

    # ── LLM narrative: phrasing only, never evidence ──────────────────────────
    # The model receives the findings’ already-computed sentences and rephrases
    # them; on any failure (disabled, down, empty, or a reply stating a number
    # the evidence does not contain) the deterministic template narrative above
    # stands. `narrative_source` says which one the reader is getting -- the
    # template used to describe itself as "honest about being template prose",
    # and that honesty must survive the upgrade.
    from ..services.insights import narrate_findings
    prose = await narrate_findings(result["findings"], row_count=result.get("row_count"))
    if prose:
        result = {**result, "narrative": prose, "narrative_source": "llm"}
    else:
        result = {**result, "narrative_source": "template"}

    return result


# ── Goal seeking ─────────────────────────────────────────────────────────────

@router.post("/{dataset_id}/goal-seek")
async def goal_seek(dataset_id: int, x_column: str, y_column: str, target_y: float,
                    x_min: float | None = None, x_max: float | None = None,
                    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Solve for the factor value a target requires, on a linear fit of y ~ x
    over the same secured frame widgets read. The answer carries the fit's r²
    and whether the required x sits inside the observed range -- a goal outside
    the data is an extrapolation, and the caller deserves to know.

    Optional per-factor bounds (SAS's goal-seek constraint): when x_min/x_max
    are given and the required x falls outside them, the solve reports
    infeasibility honestly -- plus the BEST ACHIEVABLE y at the binding bound,
    which is the number a bounded solver actually optimises to."""
    from ..services.analysis.goal_seek import GoalSeekError, goal_seek as _solve

    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    if not ds.filename or ds.mode == "directquery":
        raise HTTPException(400, "Goal seek is available for import-mode datasets only")
    denied = await resolve_denied_columns(db, current_user, dataset_id)
    if x_column in (denied or []) or y_column in (denied or []):
        raise HTTPException(404, "Column not found")
    rls_expr = await resolve_rls_expr(db, current_user, dataset_id)
    from ..services.prep import apply_prep_steps, prep_steps_of, resolve_join_frames
    _steps = prep_steps_of(ds)
    _aux = await resolve_join_frames(db, current_user, _steps) if _steps else {}

    def _run():
        from ..services.widget_data import apply_calculated_columns, apply_rls_filter
        df = load_file(ds.filename)
        df = apply_rls_filter(df, rls_expr)
        df = apply_prep_steps(df, _steps, _aux)
        if ds.calculated_columns:
            df = apply_calculated_columns(df, ds.calculated_columns, ds.custom_functions)
        # The arithmetic lives in the service so the analysis registry, the
        # statistics panel and the agent can all reach it -- none of them can
        # call a function interleaved with Depends and HTTPException.
        return _solve(df, x_column, y_column, target_y, x_min, x_max)

    try:
        return await asyncio.to_thread(_run)
    except GoalSeekError as e:
        # The service raises ValueError subclasses; no service layer in this
        # codebase raises HTTP, so the translation happens here.
        raise HTTPException(400, str(e))
    except FileNotFoundError:
        raise HTTPException(404, "Dataset file not found on server — please re-upload the file")


# ── Automated explanation ────────────────────────────────────────────────────

@router.post("/{dataset_id}/explain")
async def explain_column(dataset_id: int, column: str, body: dict | None = None,
                         db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Which columns move `column`, ranked SAS-style (top factor = 1, rest
    proportional), plus the top factor's relationship data. Same secured frame
    as every widget; a denied response column fails closed."""
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    if not ds.filename or ds.mode == "directquery":
        raise HTTPException(400, "Explanation is available for import-mode datasets only")
    denied = await resolve_denied_columns(db, current_user, dataset_id)
    if column in (denied or []):
        raise HTTPException(404, f"Column '{column}' not found")
    rls_expr = await resolve_rls_expr(db, current_user, dataset_id)
    from ..services.prep import apply_prep_steps, prep_steps_of, resolve_join_frames
    _steps = prep_steps_of(ds)
    _aux = await resolve_join_frames(db, current_user, _steps) if _steps else {}

    def _run():
        from ..services.explain import explain_response
        from ..services.widget_data import apply_calculated_columns, apply_rls_filter
        df = load_file(ds.filename)
        df = apply_rls_filter(df, rls_expr)
        df = apply_prep_steps(df, _steps, _aux)
        if denied:
            df = df.drop(columns=[c for c in denied if c in df.columns])
        if ds.calculated_columns:
            df = apply_calculated_columns(df, ds.calculated_columns, ds.custom_functions)
        if column not in df.columns:
            raise HTTPException(404, f"Column '{column}' not found")
        # A reader's "Explain this" is about the rows the WIDGET shows: its own
        # filters and the page's selections, passed as `{"filters": [...]}`.
        filters = (body or {}).get("filters") if isinstance(body, dict) else None
        rows_before = int(len(df))
        if isinstance(filters, list) and filters:
            from ..services.widget_data import _apply_filters
            df = _apply_filters(df, [f for f in filters if isinstance(f, dict)])
        out = explain_response(df, column)
        out["rows"] = int(len(df))
        out["rows_before_filters"] = rows_before
        return out

    try:
        result = await asyncio.to_thread(_run)
    except FileNotFoundError:
        raise HTTPException(404, "Dataset file not found on server — please re-upload the file")

    # A sentence to go with the numbers, which is what SAS's automated
    # explanation produces and this returned without. It goes through the
    # SAME guarded path the Dynamic Pin card uses: `narrate_one` carries the
    # digit guard (a reply stating a number the evidence does not contain is
    # discarded) and the shared breaker (a model that just failed is not asked
    # again for two minutes).
    #
    # Narration is an ADDITION to the answer, never a precondition for it. An
    # air-gapped install has no model at all, and the factors are the
    # explanation -- so every failure here is swallowed and the sentence is
    # simply absent. Absent as null, not "": a blank string renders as a line
    # that failed to load rather than one that was never offered.
    result["narrative"] = None
    result["narrative_source"] = None
    factors = result.get("factors") or []
    if factors:
        top = factors[0]
        finding = {
            "title": f"What moves {column}",
            "detail": (f"{top.get('column')} has the strongest measured "
                       f"relationship with {column}."),
            # Only what the evidence already states: the digit guard compares
            # the reply against exactly these figures.
            "figures": {"strength": top.get("score"),
                        "relative": top.get("relative")},
        }
        try:
            from ..services.insights import narrate_one
            sentence = await narrate_one(finding)
        except Exception:                       # noqa: BLE001
            # "We could not phrase this" must not become "we could not
            # explain this" -- the answer is already computed.
            sentence = None
        if sentence:
            result["narrative"] = sentence
            result["narrative_source"] = "model"
    return result


# ── Outlier details ──────────────────────────────────────────────────────────

@router.post("/{dataset_id}/outlier-details")
async def outlier_details(dataset_id: int, column: str, detector: str = "iqr",
                          db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """The detail behind the Fields pane's ⚠ badge: box-plot stats, the outlier
    rows themselves, and an impact assessment (how much of the total the
    outliers carry; the mean with and without them). Computed on the same
    RLS-filtered, prepped frame every widget sees.

    A3: `detector` selects which rows count as outliers -- `"iqr"` (default,
    UNCHANGED from before this task) vs PyOD's `"iforest"`/`"ecod"`. The box-plot
    stats (fences included) are always the IQR ones regardless of detector; only
    the flagged-row set and its downstream impact numbers change."""
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    if not ds.filename or ds.mode == "directquery":
        raise HTTPException(400, "Outlier details are available for import-mode datasets only")
    denied = await resolve_denied_columns(db, current_user, dataset_id)
    if column in (denied or []):
        # Fail closed exactly like the widget path: the column does not exist
        # for this role, so neither do its outliers.
        raise HTTPException(404, f"Column '{column}' not found")
    rls_expr = await resolve_rls_expr(db, current_user, dataset_id)
    from ..services.prep import apply_prep_steps, prep_steps_of, resolve_join_frames
    _steps = prep_steps_of(ds)
    _aux = await resolve_join_frames(db, current_user, _steps) if _steps else {}

    def _run():
        import pandas as pd
        from ..services.analysis.anomaly import AnomalyError, detect as detect_anomalies
        from ..services.widget_data import _safe, apply_calculated_columns, apply_rls_filter
        df = load_file(ds.filename)
        df = apply_rls_filter(df, rls_expr)
        df = apply_prep_steps(df, _steps, _aux)
        if denied:
            df = df.drop(columns=[c for c in denied if c in df.columns])
        if ds.calculated_columns:
            df = apply_calculated_columns(df, ds.calculated_columns, ds.custom_functions)
        if column not in df.columns:
            raise HTTPException(404, f"Column '{column}' not found")
        s = pd.to_numeric(df[column], errors="coerce")
        clean = s.dropna()
        if clean.empty:
            raise HTTPException(400, f"Column '{column}' has no numeric values")
        q1, q3 = float(clean.quantile(0.25)), float(clean.quantile(0.75))
        try:
            clean_mask, lo, hi = detect_anomalies(clean, detector)
        except AnomalyError as e:
            raise HTTPException(400, str(e))
        mask = clean_mask.reindex(s.index, fill_value=False)
        out_vals = s[mask.fillna(False)]
        total = float(clean.sum())
        rows = df[mask.fillna(False)].head(50)
        return {
            "column": column,
            "detector": detector,
            "stats": {"min": _safe(clean.min()), "q1": _safe(q1), "median": _safe(clean.median()),
                      "q3": _safe(q3), "max": _safe(clean.max()),
                      "fence_low": _safe(lo), "fence_high": _safe(hi)},
            "outliers": {
                "count": int(mask.sum()), "total_rows": int(len(clean)),
                "columns": list(rows.columns),
                "rows": [[_safe(v) for v in r] for r in rows.values.tolist()],
            },
            "impact": {
                # Share of the column total the outlier rows carry, and what the
                # mean looks like with them in versus out -- SAS's assessment.
                "share_of_sum": _safe(float(out_vals.sum()) / total) if total else None,
                "mean_with": _safe(clean.mean()),
                "mean_without": _safe(clean[~clean.index.isin(out_vals.index)].mean())
                                if int(mask.sum()) < len(clean) else None,
            },
        }

    try:
        return await asyncio.to_thread(_run)
    except FileNotFoundError:
        raise HTTPException(404, "Dataset file not found on server — please re-upload the file")


# ── Lineage ──────────────────────────────────────────────────────────────────

def _extraction_kind(d: "Dataset") -> str:
    """What fed this dataset: DirectQuery (live), a query-built import (SQL/model
    against a connection), or the extension of an uploaded/imported file."""
    if d.mode == "directquery":
        return "directquery"
    if d.data_source_id and (d.query_model or d.source_query or d.source_table):
        return "query"
    if d.filename:
        return Path(d.filename).suffix.lstrip(".").lower() or "file"
    return "unknown"


def _staleness_bucket(last_refreshed_at) -> str:
    from datetime import datetime as _dt, timezone as _tz
    if last_refreshed_at is None:
        return "never"
    now = _dt.now(_tz.utc)
    ts = last_refreshed_at if last_refreshed_at.tzinfo else last_refreshed_at.replace(tzinfo=_tz.utc)
    age_hours = (now - ts).total_seconds() / 3600
    return "fresh" if age_hours < 24 else "stale"


@router.get("/lineage/graph")
async def lineage_graph(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """The org's data estate as a graph: sources feed datasets, join steps link
    datasets, reports read datasets. Answers both lineage questions -- "where
    did this number come from" and "what breaks if I delete this dataset".
    Org-scoped, read-only; two path segments so /{dataset_id} can't swallow it.

    F4: each dataset node also carries its ETL story -- how it was extracted
    (file type / DirectQuery / query-built), a summary of its active transform
    pipeline (disabled steps excluded, same rule apply_prep_steps uses), and its
    load/refresh state (last_refreshed_at, watermark strategy + cursor column)
    so the graph answers "how fresh/how transformed" without a second trip to
    DatasetDetail."""
    from sqlalchemy.orm import selectinload as _sl

    from ..models.models import DataSource, Materialization, Report, ReportPage, Watermark
    from ..services.prep import (collect_join_dataset_ids, derived_from_of,
                                 derived_source_ids, prep_steps_of)

    org = current_user.org_id
    sources = (await db.execute(select(DataSource).where(DataSource.org_id == org))).scalars().all()
    datasets = (await db.execute(select(Dataset).where(Dataset.org_id == org))).scalars().all()
    # The lineage map draws every dataset, connection and dashboard it is
    # given, so an unscoped list here would redraw on a diagram exactly the
    # names the dataset list stopped showing. Nodes are trimmed to what this
    # viewer may read; the edges below are built from what survives, so a
    # dropped dataset takes its arrows with it.
    readable = await readable_dataset_ids(db, current_user)
    if readable is not None:
        datasets = [d for d in datasets if d.id in readable]
        visible_sources = {d.data_source_id for d in datasets if d.data_source_id}
        sources = [s for s in sources
                   if s.id in visible_sources
                   or s.created_by is None or s.created_by == current_user.id]
    reports = (await db.execute(
        select(Report).options(_sl(Report.pages).selectinload(ReportPage.widgets))
        .where(Report.org_id == org)
    )).scalars().all()
    watermarks = (await db.execute(
        select(Watermark).where(Watermark.dataset_id.in_([d.id for d in datasets] or [-1]))
    )).scalars().all()
    watermark_by_ds = {w.dataset_id: w for w in watermarks}
    # O3: one Materialization row per dataset (see write_materialization) --
    # its presence is what "materialized" means here, org-scoped for free
    # since dataset_id is filtered to this org's datasets above.
    materializations = (await db.execute(
        select(Materialization).where(Materialization.dataset_id.in_([d.id for d in datasets] or [-1]))
    )).scalars().all()
    materialization_by_ds = {m.dataset_id: m for m in materializations}

    ds_ids = {d.id for d in datasets}
    report_nodes = []
    for r in reports:
        used = set()
        if r.dataset_id in ds_ids:
            used.add(r.dataset_id)
        for extra in (r.additional_dataset_ids or []):
            if extra in ds_ids:
                used.add(extra)
        # Widgets can point anywhere via config.dataset_id -- the graph must see
        # what the widgets actually read, not just what the report declares.
        for page in r.pages:
            for w in page.widgets:
                wid_ds = (w.config or {}).get("dataset_id")
                if wid_ds in ds_ids:
                    used.add(wid_ds)
        report_nodes.append({"id": r.id, "name": r.name, "dataset_ids": sorted(used)})

    def _dataset_node(d: Dataset) -> dict:
        active_steps = [s for s in prep_steps_of(d) if not (isinstance(s, dict) and s.get("disabled"))]
        wm = watermark_by_ds.get(d.id)
        mat = materialization_by_ds.get(d.id)
        return {
            "id": d.id, "name": d.name, "mode": d.mode,
            "source_id": d.data_source_id,
            "joins": sorted(set(collect_join_dataset_ids(prep_steps_of(d))) & ds_ids),
            # A MATERIALIZED dataset has no steps of its own -- the joins were
            # consumed into its file -- so `joins` above is empty for it and its
            # derivation would otherwise be invisible in the graph. Distinct
            # from `joins` on purpose: that edge is live and re-evaluated on
            # every read, this one is a snapshot taken at `built_at`.
            "derived_from": sorted(set(derived_source_ids(derived_from_of(d))) & ds_ids),
            "built_at": (derived_from_of(d) or {}).get("built_at"),
            "extraction_kind": _extraction_kind(d),
            "transform": {
                "count": len(active_steps),
                "kinds": [s.get("kind") for s in active_steps if isinstance(s, dict) and s.get("kind")],
            },
            "load": {
                "last_refreshed_at": d.last_refreshed_at,
                "strategy": wm.strategy if wm else None,
                "cursor_column": wm.cursor_column if wm else None,
                "staleness": _staleness_bucket(d.last_refreshed_at),
            },
            # O3: whether a refresh has written a Materialization manifest row
            # for this dataset (never true for a dataset that has only ever
            # been uploaded, not refreshed from a connection).
            "materialized": mat is not None,
            "materialized_row_count": mat.row_count if mat else None,
        }

    return {
        "sources": [{"id": s.id, "name": s.name, "type": s.type} for s in sources],
        "datasets": [_dataset_node(d) for d in datasets],
        "reports": report_nodes,
    }


# ── Data views (reusable semantic bundles) ───────────────────────────────────

@router.get("/data-views/list")
async def list_data_views(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Two path segments on purpose: a single-segment literal after /{dataset_id}
    # would be swallowed by the int route and 422.
    from ..models.models import DataView
    rows = (await db.execute(
        select(DataView).where(DataView.org_id == current_user.org_id).order_by(DataView.name)
    )).scalars().all()
    return [{"id": v.id, "name": v.name, "created_at": v.created_at,
             "is_default": bool(v.is_default),
             "pieces": sorted(k for k, val in (v.payload or {}).items() if val)} for v in rows]


@router.post("/{dataset_id}/save-data-view", status_code=201)
async def save_data_view(dataset_id: int, name: str,
                         db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Snapshot this dataset's semantic layer under a name, org-wide."""
    from ..models.models import DataView
    from ..services.data_views import snapshot_dataset
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    name = (name or "").strip()[:255]
    if not name:
        raise HTTPException(400, "A data view needs a name")
    payload = await snapshot_dataset(db, ds)
    view = DataView(org_id=current_user.org_id, name=name, payload=payload,
                    creator_user_id=current_user.id)
    db.add(view)
    await audit(db, current_user, "dataset.save_data_view", "dataset", ds.id, name)
    await db.commit()
    return {"id": view.id, "name": view.name}


@router.post("/{dataset_id}/apply-data-view")
async def apply_data_view(dataset_id: int, view_id: int,
                          db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Apply a saved bundle to this dataset, matching by column name. The
    response reports exactly what applied and what was skipped."""
    from ..models.models import DataView
    from ..services.data_views import apply_view
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    if ds.mode == "directquery":
        raise HTTPException(400, "Data views apply to import datasets")
    view = await db.get(DataView, view_id)
    check_org(view, current_user, "Data view not found")
    report = await apply_view(db, ds, view.payload or {})
    await audit(db, current_user, "dataset.apply_data_view", "dataset", ds.id, view.name)
    await db.commit()
    return report


@router.patch("/data-views/{view_id}/default")
async def set_default_data_view(view_id: int, req: DataViewDefault,
                                db: AsyncSession = Depends(get_db),
                                current_user: User = Depends(get_current_user)):
    """Mark (or unmark) a view as the one applied to every new dataset.

    SAS's admin default. Admin-only because it decides what every future
    upload looks like for everybody in the org, and AT MOST ONE per org --
    setting a second clears the first, since two defaults would be a coin toss
    dressed up as a setting.
    """
    from ..models.models import DataView
    if not (current_user.role and current_user.role.is_org_admin):
        raise HTTPException(
            403, "Only an organisation admin can choose the data view applied "
                 "to new datasets.")
    view = await db.get(DataView, view_id)
    check_org(view, current_user, "Data view not found")
    if req.default:
        for other in (await db.execute(
                select(DataView).where(DataView.org_id == current_user.org_id,
                                       DataView.is_default.is_(True)))).scalars().all():
            other.is_default = False
    view.is_default = bool(req.default)
    await audit(db, current_user, "dataset.default_data_view", "data_view",
                view.id, f"{view.name}: {view.is_default}")
    await db.commit()
    return {"id": view.id, "name": view.name, "is_default": view.is_default}


@router.delete("/data-views/{view_id}", status_code=204)
async def delete_data_view(view_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    from ..models.models import DataView
    view = await db.get(DataView, view_id)
    check_org(view, current_user, "Data view not found")
    await db.delete(view)
    await audit(db, current_user, "dataset.delete_data_view", "dataset", view_id, view.name)
    await db.commit()


# ── Prep steps (step-based transformation pipeline) ──────────────────────────

@router.get("/{dataset_id}/prep-steps")
async def get_prep_steps(dataset_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    from ..services.prep import prep_steps_of
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    return prep_steps_of(ds)


@router.put("/{dataset_id}/prep-steps")
async def set_prep_steps(dataset_id: int, steps: list[dict], db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Replace the dataset's prep pipeline wholesale (same replace-don't-merge
    contract as column-meta). Validation is the hard gate: a malformed step is
    refused here so the apply path can afford to be fail-soft."""
    from ..services.prep import PREP_STEPS_KEY, validate_prep_steps
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    await require_dataset_capability(db, current_user, dataset_id, "data")
    if ds.mode == "directquery":
        raise HTTPException(400, "Prep steps apply to import datasets; DirectQuery data is shaped in SQL")

    result = await db.execute(select(DatasetColumn.name).where(DatasetColumn.dataset_id == dataset_id))
    known = {r[0] for r in result.all()}

    # Join targets are validated HARD here (org, mode, existence, key column):
    # apply time degrades soft, so save time is where a bad reference is caught.
    join_columns: dict[int, set[str]] = {}
    for st in steps:
        if isinstance(st, dict) and st.get("kind") == "join" and isinstance(st.get("dataset_id"), int):
            other = await db.get(Dataset, st["dataset_id"])
            if other is None or other.org_id != current_user.org_id:
                raise HTTPException(400, f"joined dataset {st['dataset_id']} does not exist")
            if other.mode == "directquery":
                raise HTTPException(400, "Cannot join a DirectQuery dataset; joins run over import data")
            res = await db.execute(select(DatasetColumn.name).where(DatasetColumn.dataset_id == other.id))
            join_columns[other.id] = {r[0] for r in res.all()}
    try:
        validate_prep_steps(steps, known, join_columns)
    except ValueError as e:
        raise HTTPException(400, str(e))

    meta = dict(ds.column_meta or {})
    if steps:
        meta[PREP_STEPS_KEY] = steps
    else:
        meta.pop(PREP_STEPS_KEY, None)
    ds.column_meta = meta
    flag_modified(ds, "column_meta")
    await audit(db, current_user, "dataset.prep_steps", "dataset", ds.id, f"{len(steps)} steps")
    await db.commit()
    return steps


@router.post("/{dataset_id}/prep-preview")
async def preview_prep_steps(dataset_id: int, steps: list[dict], db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Apply CANDIDATE steps (not the saved ones) to this user's RLS-filtered
    frame and return shape-before, shape-after and a sample -- the editor calls
    this on every change so the author sees the effect before saving."""
    from ..services.prep import MAX_STEPS, apply_prep_steps
    from ..services.widget_data import _safe, apply_rls_filter
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    if not ds.filename or ds.mode == "directquery":
        raise HTTPException(400, "Prep preview is available for import-mode datasets only")
    if not isinstance(steps, list) or len(steps) > MAX_STEPS:
        raise HTTPException(400, f"steps must be a list of at most {MAX_STEPS}")
    rls_expr = await resolve_rls_expr(db, current_user, dataset_id)
    denied = await resolve_denied_columns(db, current_user, dataset_id)
    from ..services.prep import resolve_join_frames
    aux = await resolve_join_frames(db, current_user, steps)

    def _run():
        df = load_file(ds.filename)
        df = apply_rls_filter(df, rls_expr)
        # Denied columns leave BEFORE the before-shape is captured: the editor
        # must not list a column the caller cannot see, and a candidate step on
        # it then degrades to a no-op the same way a vanished column does.
        present = [c for c in denied if c in df.columns]
        if present:
            df = df.drop(columns=present)
        before = {"rows": int(len(df)), "columns": list(df.columns)}
        # Per-step breakdown: apply steps one at a time so the editor can show
        # "data at this point" for whichever card is selected -- each entry is
        # fail-soft the same way apply_prep_steps is (a step on a vanished
        # column degrades to a no-op instead of aborting the whole preview).
        running = df
        per_step = []
        for st in steps:
            rows_in = int(len(running))
            # apply_prep_steps itself skips a disabled step (paused, not deleted)
            # -- rows_in == rows_out here is that no-op, surfaced so the editor
            # can render the card as "skipped" rather than merely quiet.
            running = apply_prep_steps(running, [st], aux)
            per_step.append({"rows_in": rows_in, "rows_out": int(len(running)),
                             "columns": list(running.columns),
                             "skipped": bool(isinstance(st, dict) and st.get("disabled"))})
        out = running
        sample = out.head(20)
        return {
            "before": before,
            "after": {"rows": int(len(out)), "columns": list(out.columns)},
            "steps": per_step,
            "sample": {"columns": list(sample.columns),
                       "rows": [[_safe(v) for v in r] for r in sample.values.tolist()]},
        }

    try:
        return await asyncio.to_thread(_run)
    except FileNotFoundError:
        raise HTTPException(404, "Dataset file not found on server — please re-upload the file")


@router.get("/{dataset_id}/sensitivity")
async def get_dataset_sensitivity(dataset_id: int, db: AsyncSession = Depends(get_db),
                                  current_user: User = Depends(get_current_user)):
    """The dataset's own label, its EFFECTIVE label (highest over its lineage
    and joins) with the reason, and what that label enforces (Phase 7.3)."""
    from ..services.sensitivity import LEVELS, dataset_effective, own_label, redacted_columns
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    await require_dataset_read(db, current_user, dataset_id)
    effective, reasons = await dataset_effective(db, dataset_id)
    return {"label": own_label(ds), "effective": effective, "reasons": reasons, "options": LEVELS,
            "redacted_on_share": await redacted_columns(db, dataset_id)}


@router.put("/{dataset_id}/sensitivity")
async def set_dataset_sensitivity(dataset_id: int, body: dict, db: AsyncSession = Depends(get_db),
                                  current_user: User = Depends(get_current_user)):
    """Label a dataset Public / Internal / Confidential / Restricted (or clear
    it). Needs data-level access; audited. Everything built from or joining it
    inherits the label."""
    from sqlalchemy.orm.attributes import flag_modified as _flag

    from ..services.sensitivity import LEVELS, META_KEY
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    await require_dataset_write(db, current_user, ds, "data")
    label = (body.get("label") or "").strip()
    if label and label not in LEVELS:
        raise HTTPException(400, f"label must be one of {LEVELS} or empty")
    meta = dict(ds.column_meta or {})
    if label:
        meta[META_KEY] = label
    else:
        meta.pop(META_KEY, None)
    ds.column_meta = meta
    _flag(ds, "column_meta")
    await audit(db, current_user, "dataset.classify", "dataset", dataset_id, label or "(cleared)")
    await db.commit()
    return await get_dataset_sensitivity(dataset_id, db, current_user)


@router.post("/{dataset_id}/join-check")
async def check_join(dataset_id: int, body: dict, db: AsyncSession = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    """How a candidate join step will land, before it is saved.

    `{"steps": [...], "index": i}`: step `i` is the join; the left side is the
    caller's secured frame after steps `0..i-1`, the right side the joined
    dataset secured as the caller -- exactly what the pipeline will join."""
    from ..services.prep import MAX_STEPS, apply_prep_steps, join_key_pairs, join_match_report, resolve_join_frames
    from ..services.widget_data import apply_rls_filter
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    if not ds.filename or ds.mode == "directquery":
        raise HTTPException(400, "Join checks are available for import-mode datasets only")
    steps, index = body.get("steps"), body.get("index")
    if not isinstance(steps, list) or len(steps) > MAX_STEPS or not isinstance(index, int) \
            or not 0 <= index < len(steps) or not isinstance(steps[index], dict) or steps[index].get("kind") != "join":
        raise HTTPException(400, "steps[index] must be a join step")
    step = steps[index]
    pairs = join_key_pairs(step)
    if not pairs:
        raise HTTPException(400, "The join needs a key column on each side")
    rls_expr = await resolve_rls_expr(db, current_user, dataset_id)
    denied = await resolve_denied_columns(db, current_user, dataset_id)
    aux = await resolve_join_frames(db, current_user, steps[: index + 1])
    right = aux.get(step.get("dataset_id"))
    if right is None:
        raise HTTPException(404, "The dataset to join is not available to you")

    def _run():
        df = load_file(ds.filename)
        df = apply_rls_filter(df, rls_expr)
        df = df.drop(columns=[c for c in denied if c in df.columns])
        df = apply_prep_steps(df, steps[:index], aux)
        return join_match_report(df, right, pairs, how=str(step.get("how") or "left"))

    try:
        return await asyncio.to_thread(_run)
    except FileNotFoundError:
        raise HTTPException(404, "Dataset file not found on server — please re-upload the file")


# ── Materialize: a pipeline's result as a dataset of its own ──────────────────

async def _validated_join_columns(
    db: AsyncSession, org_id: int, steps: list[dict],
) -> dict[int, set[str]]:
    """Resolve and HARD-check every join target, returning their column sets.

    The same gate `PUT /prep-steps` applies, extracted so materialize and
    rebuild cannot drift from it. Apply time is fail-soft, so a bad reference
    has to be caught wherever a pipeline is committed to.
    """
    join_columns: dict[int, set[str]] = {}
    for st in steps:
        if not (isinstance(st, dict) and st.get("kind") == "join"
                and isinstance(st.get("dataset_id"), int)):
            continue
        other = await db.get(Dataset, st["dataset_id"])
        if other is None or other.org_id != org_id:
            raise HTTPException(400, f"joined dataset {st['dataset_id']} does not exist")
        if other.mode == "directquery":
            raise HTTPException(400, "Cannot join a DirectQuery dataset; joins run over import data")
        res = await db.execute(select(DatasetColumn.name).where(DatasetColumn.dataset_id == other.id))
        join_columns[other.id] = {r[0] for r in res.all()}
    return join_columns


async def _refuse_if_ungovernable(db: AsyncSession, source_ids: list[int]) -> dict:
    """Refuse to snapshot governed data, and honour every source's export policy.

    **The security decision this feature turns on.** Every read applies the
    CALLER's row-level security, so a user restricted to EMEA who materializes
    writes a file of EMEA rows -- and the new dataset carries no rules of its
    own. An unrestricted colleague would then read a silently truncated table
    (wrong totals, no error anywhere), and a differently-restricted one would
    read rows they must not see.

    Refusing outright is fail-closed and needs no new ACL machinery. Copying the
    source's rules onto the copy was considered and rejected: a join renames
    colliding columns (`region` -> `region_2`) and an `aggregate` step can
    remove the rule's column altogether, so the copied rule would reference a
    column that no longer exists -- a control that looks enabled and is not.

    Materializing is also an EXPORT: it writes source rows to a file the org can
    download, share or deliver. Skipping the export policy here would make it
    trivially bypassable -- materialize, then export the copy, which carries no
    policy of its own. Hence both checks, and hence the policy is propagated to
    the new dataset by the caller.

    Returns the strictest policy found, for the caller to copy onto the result.
    """
    strictest: dict | bool | None = None
    for sid in source_ids:
        if await _dataset_has_security(db, sid):
            raise HTTPException(
                403, "Cannot save a snapshot of a dataset that has row- or "
                     "column-security rules: the result would freeze one "
                     "person's filtered view as everyone's data.")
        src = await db.get(Dataset, sid)
        if src is None:
            continue
        policy_ds = await _policy_dataset(db, src)
        if _exports_disabled(policy_ds, "csv", False):
            raise HTTPException(
                403, f"Exports are disabled for '{src.name}', so its rows "
                     f"cannot be written to a new dataset.")
        policy = (policy_ds.column_meta or {}).get(EXPORT_DISABLED_KEY)
        if policy is True:
            strictest = True
        elif isinstance(policy, dict) and strictest is not True:
            merged = dict(strictest or {}) if isinstance(strictest, dict) else {}
            merged["formats"] = sorted(set(merged.get("formats") or [])
                                       | set(policy.get("formats") or []))
            if policy.get("auto_private"):
                merged["auto_private"] = True
            if not merged.get("formats"):
                merged.pop("formats", None)
            strictest = merged or None
    return {EXPORT_DISABLED_KEY: strictest} if strictest else {}


async def _build_frame(db: AsyncSession, user: User, ds: Dataset, steps: list[dict]):
    """Run one pipeline to completion for this user, as every read path does."""
    from ..services.prep import apply_prep_steps, resolve_join_frames
    from ..services.widget_data import apply_rls_filter

    rls_expr = await resolve_rls_expr(db, user, ds.id)
    denied = await resolve_denied_columns(db, user, ds.id)
    aux = await resolve_join_frames(db, user, steps)

    def _run():
        df = load_file(ds.filename)
        df = apply_rls_filter(df, rls_expr)
        present = [c for c in (denied or []) if c in df.columns]
        if present:
            df = df.drop(columns=present)
        return apply_prep_steps(df, steps, aux)

    return await asyncio.to_thread(_run)


async def _write_frame_as_dataset_file(db: AsyncSession, org_id: int, out):
    """Persist a computed frame the way an upload is persisted, and charge it.

    Returns (path, size, type_map). Raises after cleaning up its own bytes.
    """
    from ..services.prep import MATERIALIZE_MAX_ROWS

    if len(out) > MATERIALIZE_MAX_ROWS:
        raise HTTPException(
            400, f"The result has {len(out):,} rows, over the "
                 f"{MATERIALIZE_MAX_ROWS:,} limit for a saved dataset. Add a "
                 f"filter or aggregate step, or use a narrower join.")

    path = upload_store.allocate_path(org_id, "joined.csv")
    await asyncio.to_thread(lambda: out.to_csv(path, index=False))
    size = path.stat().st_size
    try:
        await quotas.enforce_storage_quota(db, org_id, size)
    except (HTTPException, quotas.QuotaExceeded) as e:
        # QuotaExceeded is a plain Exception, not an HTTPException -- catching
        # only the latter would leave these bytes orphaned on disk.
        path.unlink(missing_ok=True)
        raise HTTPException(getattr(e, "status_code", 413), str(e.detail))
    type_map = await asyncio.to_thread(detect_types, out)
    await asyncio.to_thread(write_parquet_sidecar, str(path))
    return path, size, type_map


@router.post("/{dataset_id}/materialize", response_model=DatasetOut)
async def materialize_dataset(
    dataset_id: int, req: MaterializeRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Run this dataset's pipeline once and save the result as a NEW dataset.

    This is how several datasets joined together become one listable dataset: a
    prep `join` step is a view that re-joins on every read, whereas the result
    of this endpoint is an ordinary import dataset with its own file, columns
    and reports. It is a SNAPSHOT -- it does not follow its sources, and
    `POST /{id}/rebuild` re-runs it deliberately.

    Candidate `steps` may be supplied (as `prep-preview` accepts them) so the
    editor saves exactly the result the author is looking at, saved or not.
    Whatever runs is recorded verbatim as the recipe.
    """
    from ..services.prep import (DERIVED_FROM_KEY, MAX_STEPS,
                                 collect_join_dataset_ids, prep_steps_of,
                                 validate_prep_steps)

    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    await require_dataset_capability(db, current_user, dataset_id, "data")
    if ds.mode == "directquery" or not ds.filename:
        raise HTTPException(400, "Only import-mode datasets can be saved as a new dataset")

    name = (req.name or "").strip()[:255]
    if not name:
        raise HTTPException(400, "name is required")

    steps = req.steps if req.steps is not None else prep_steps_of(ds)
    if not isinstance(steps, list) or len(steps) > MAX_STEPS:
        raise HTTPException(400, f"steps must be a list of at most {MAX_STEPS}")

    known = {r[0] for r in (await db.execute(
        select(DatasetColumn.name).where(DatasetColumn.dataset_id == dataset_id))).all()}
    join_columns = await _validated_join_columns(db, current_user.org_id, steps)
    try:
        validate_prep_steps(steps, known, join_columns)
    except ValueError as e:
        raise HTTPException(400, str(e))

    join_ids = collect_join_dataset_ids(steps)
    inherited = await _refuse_if_ungovernable(db, [dataset_id] + join_ids)

    try:
        out = await _build_frame(db, current_user, ds, steps)
    except FileNotFoundError:
        raise HTTPException(404, "Dataset file not found on server — please re-upload the file")

    path, size, type_map = await _write_frame_as_dataset_file(db, current_user.org_id, out)

    new = Dataset(
        name=name, description=(req.description or None), filename=str(path),
        row_count=len(out), col_count=len(out.columns), file_size=size,
        org_id=current_user.org_id, mode="import",
        last_refreshed_at=datetime.utcnow(),
        column_meta={
            **inherited,
            DERIVED_FROM_KEY: {
                "source_dataset_id": dataset_id,
                "join_dataset_ids": sorted(set(join_ids)),
                "steps": steps,
                "built_by_user_id": current_user.id,
                "built_at": datetime.utcnow().isoformat() + "Z",
                "built_rows": int(len(out)),
                "recipe_version": 1,
            },
        },
    )
    db.add(new)
    await db.flush()
    for col_name, dtype in type_map.items():
        db.add(DatasetColumn(
            dataset_id=new.id, name=col_name, dtype=dtype,
            missing_pct=round(out[col_name].isnull().mean() * 100, 2), stats={}))
    await audit(db, current_user, "dataset.materialize", "dataset", new.id,
                f"from {dataset_id}, {len(out)} rows")
    await db.commit()
    return (await db.execute(
        select(Dataset).options(selectinload(Dataset.columns))
        .where(Dataset.id == new.id))).scalar_one()


async def _source_rules(db: AsyncSession, dataset_id: int):
    """Every row-level rule on a dataset, with the role's name for messages."""
    from ..models.models import Role, RowSecurityRule
    rows = (await db.execute(
        select(RowSecurityRule, Role.name)
        .join(Role, Role.id == RowSecurityRule.role_id)
        .where(RowSecurityRule.dataset_id == dataset_id))).all()
    return [(rule, role_name) for rule, role_name in rows]


def _uncovered_message(bad: list[tuple[int, str]], rules) -> str:
    """Thin wrapper: the sentence itself lives in services/aggregates.py so
    the scheduler's refresh-time refusal (refresh_scheduler.py) can share it
    without importing this router."""
    from ..services.aggregates import uncovered_message
    names = {rule.role_id: role_name for rule, role_name in rules}
    return uncovered_message(bad, names)


@router.get("/{dataset_id}/aggregate-preflight")
async def aggregate_preflight(
    dataset_id: int,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """What the Aggregates tab needs before an author chooses anything: the
    columns every RLS rule reads (the grain must include them), and which
    columns can be grain or measure."""
    from ..services.aggregates import rls_columns_outside_grain
    ds = (await db.execute(select(Dataset).options(selectinload(Dataset.columns))
                           .where(Dataset.id == dataset_id))).scalar_one_or_none()
    check_org(ds, current_user, "Dataset not found")
    # Both gates, deliberately: capability is about AUTHORING this dataset's
    # data model and defaults open for a dataset no report uses yet (see
    # max_dataset_capability); read is about SEEING it at all and defaults
    # open only when nobody owns it (readable_dataset_ids). A source with an
    # owner and no report -- exactly an unshared connection somebody just
    # wired up -- must fail read even though capability alone would allow it.
    await require_dataset_read(db, current_user, dataset_id)
    await require_dataset_capability(db, current_user, dataset_id, "data")
    known = {c.name for c in ds.columns}
    rules = await _source_rules(db, dataset_id)
    # Every rule column, found by asking which are outside an EMPTY grain.
    rls_cols = sorted({c for _, c in rls_columns_outside_grain([r for r, _ in rules], [], known)
                       if c != "<untranslatable>"})
    numeric = [c.name for c in ds.columns if c.dtype in ("numeric", "number", "float", "integer")]
    return {"rls_columns": rls_cols,
            "grain_candidates": sorted(known),
            "measure_candidates": sorted(numeric)}


async def _build_aggregate_file(db: AsyncSession, current_user: User, ds: Dataset,
                                grain: list[str], measures: list[dict]):
    """Validate a spec against the source AS IT IS NOW, compile, run the
    query, write the file, enforce the row cap and the storage quota.
    Returns (spec, sql, path, df, type_map, size). Raises HTTPException with
    the file already removed on every refusal after the write."""
    from ..services.aggregates import (AggregateSpecError, compile_aggregate_sql,
                                       normalise_spec, rls_columns_outside_grain)
    from ..services.dataset_refresh import rewrite_dataset_file
    from ..services.prep import MATERIALIZE_MAX_ROWS

    if ds.default_filter_expr:
        raise HTTPException(400, "The source has a report-level filter expression; an aggregate "
                                 "would ignore it. Remove the filter or aggregate a source without one.")
    known = {c.name for c in ds.columns}
    try:
        spec = normalise_spec({"grain": grain, "measures": measures}, known)
    except AggregateSpecError as e:
        raise HTTPException(400, str(e))
    rules = await _source_rules(db, ds.id)
    bad = rls_columns_outside_grain([r for r, _ in rules], spec["grain"], known)
    if bad:
        raise HTTPException(400, _uncovered_message(bad, rules))

    source = await db.get(DataSource, ds.data_source_id)
    check_org(source, current_user, "Data source not found")
    cfg = dict(source.config or {})
    cfg["type"] = source.type
    sql = compile_aggregate_sql(ds, spec)
    path = upload_store.allocate_path(current_user.org_id, "aggregate.csv")
    try:
        df, type_map = await asyncio.to_thread(rewrite_dataset_file, cfg, str(path), None, sql)
    except Exception as e:  # noqa: BLE001 -- type only: the driver's text can embed a DSN
        # rewrite_dataset_file writes the CSV (and its sidecar) as a side
        # effect before returning, so a failure AFTER that point can leave
        # bytes behind with no Dataset row to ever clean them up.
        path.unlink(missing_ok=True)
        remove_parquet_sidecar(str(path))
        raise HTTPException(400, f"The source rejected the aggregate query: {type(e).__name__}")
    if len(df) > MATERIALIZE_MAX_ROWS:
        path.unlink(missing_ok=True)
        remove_parquet_sidecar(str(path))
        raise HTTPException(
            400, f"The grain is too fine: this aggregate has {len(df):,} rows, over the "
                 f"{MATERIALIZE_MAX_ROWS:,} limit for a saved dataset. Add a coarser grain "
                 "column or fewer measures.")
    size = path.stat().st_size
    try:
        await quotas.enforce_storage_quota(db, current_user.org_id, size)
    except (HTTPException, quotas.QuotaExceeded) as e:
        # QuotaExceeded is a plain Exception, not an HTTPException -- catching
        # only the latter would leave these bytes orphaned on disk.
        path.unlink(missing_ok=True)
        remove_parquet_sidecar(str(path))
        raise HTTPException(getattr(e, "status_code", 413), str(e.detail))
    return spec, sql, path, df, type_map, size


@router.post("/{dataset_id}/aggregates", response_model=DatasetOut, status_code=201)
async def create_aggregate(
    dataset_id: int, req: AggregateCreateRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """A scheduled GROUP BY over a DirectQuery dataset, saved as a new dataset.

    Governed, not copied: the new dataset carries no rules; the resolvers in
    core/rls.py apply the SOURCE's rules to it at read time, which is only
    sound if the grain contains every column those rules read -- hence the
    refusal in _build_aggregate_file, and the same check on every refresh
    (refresh_scheduler). The first refresh runs here, synchronously, so the
    response carries a real row count -- or, if the source rejects the SQL,
    the exception's TYPE only: the driver's own text can embed a DSN or
    credentials, so it is never handed back to the caller.
    """
    from ..services.dataset_refresh import write_materialization
    from ..services.refresh_scheduler import MIN_INTERVAL_MINUTES

    ds = (await db.execute(select(Dataset).options(selectinload(Dataset.columns))
                           .where(Dataset.id == dataset_id))).scalar_one_or_none()
    check_org(ds, current_user, "Dataset not found")
    # Both gates, deliberately -- see the identical pairing (and its reason)
    # in aggregate_preflight above.
    await require_dataset_read(db, current_user, dataset_id)
    await require_dataset_capability(db, current_user, dataset_id, "data")
    if ds.mode != "directquery" or not ds.data_source_id:
        raise HTTPException(400, "Only a DirectQuery dataset can be aggregated; an import "
                                 "dataset is already a file")
    name = (req.name or "").strip()[:255]
    if not name:
        raise HTTPException(400, "name is required")
    if req.refresh_interval_minutes is not None and req.refresh_interval_minutes < MIN_INTERVAL_MINUTES:
        raise HTTPException(400, f"Minimum refresh interval is {MIN_INTERVAL_MINUTES} minutes")

    spec, sql, path, df, type_map, size = await _build_aggregate_file(
        db, current_user, ds, req.grain, [m.model_dump() for m in req.measures])

    new = Dataset(
        name=name, filename=str(path), org_id=current_user.org_id, mode="import",
        data_source_id=ds.data_source_id, source_query=sql,
        aggregate_of_dataset_id=ds.id, aggregate_spec=spec,
        refresh_interval_minutes=req.refresh_interval_minutes,
        row_count=len(df), col_count=len(df.columns), file_size=size,
        last_refreshed_at=datetime.utcnow(), column_meta={},
        # Owned by its creator, like an upload -- NOT left NULL. A NULL
        # created_by is org-wide readable (readable_dataset_ids), and this
        # file by design holds every tenant's unfiltered rows: RLS is applied
        # only when core/rls.py resolves a READ through a report, never here.
        created_by=current_user.id,
    )
    db.add(new)
    await db.flush()
    for col_name, dtype in type_map.items():
        db.add(DatasetColumn(dataset_id=new.id, name=col_name, dtype=dtype,
                             missing_pct=round(df[col_name].isnull().mean() * 100, 2), stats={}))
    await write_materialization(db, new.id, str(path), "full", len(df), list(df.columns), None)
    await audit(db, current_user, "dataset.aggregate", "dataset", new.id,
                f"from {dataset_id}, grain {spec['grain']}, {len(df)} rows")
    await db.commit()
    return (await db.execute(select(Dataset).options(selectinload(Dataset.columns))
                             .where(Dataset.id == new.id))).scalar_one()


@router.put("/{dataset_id}/aggregates/{agg_id}", response_model=DatasetOut)
async def update_aggregate(
    dataset_id: int, agg_id: int, req: AggregateUpdateRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Edit an aggregate's grain, measures or schedule, or -- with an empty
    body -- rebuild it against the source as it is now. Every creation check
    runs again: rules and the source's query can have changed since. The old
    file is replaced only after the new one is fully written and accepted.

    Ownership needs BOTH: read + data capability on the SOURCE (the checks
    `create_aggregate` makes, since the request names the source), and write
    on the AGGREGATE itself (`require_dataset_write`, the same gate
    `delete_dataset` uses) -- a role held below `data` on a report built over
    the aggregate must not be able to rewrite that report's grain and
    measures out from under it just because it can still author the source.
    """
    from ..services.dataset_refresh import write_materialization
    from ..services.refresh_scheduler import MIN_INTERVAL_MINUTES, clear_failure

    ds = (await db.execute(select(Dataset).options(selectinload(Dataset.columns))
                           .where(Dataset.id == dataset_id))).scalar_one_or_none()
    check_org(ds, current_user, "Dataset not found")
    await require_dataset_read(db, current_user, dataset_id)
    await require_dataset_capability(db, current_user, dataset_id, "data")
    agg = await db.get(Dataset, agg_id)
    if agg is None or agg.aggregate_of_dataset_id != ds.id or agg.org_id != current_user.org_id:
        raise HTTPException(404, "Aggregate not found")
    await require_dataset_write(db, current_user, agg, "data")
    stored = agg.aggregate_spec or {}
    grain = req.grain if req.grain is not None else list(stored.get("grain") or [])
    measures = ([m.model_dump() for m in req.measures] if req.measures is not None
                else list(stored.get("measures") or []))
    interval = agg.refresh_interval_minutes
    if "refresh_interval_minutes" in req.model_fields_set:
        interval = req.refresh_interval_minutes
        if interval is not None and interval < MIN_INTERVAL_MINUTES:
            raise HTTPException(400, f"Minimum refresh interval is {MIN_INTERVAL_MINUTES} minutes")

    spec, sql, path, df, type_map, size = await _build_aggregate_file(db, current_user, ds, grain, measures)

    old_file = agg.filename
    agg.filename = str(path)
    agg.data_source_id = ds.data_source_id
    agg.source_query = sql
    agg.aggregate_spec = spec
    agg.refresh_interval_minutes = interval
    agg.row_count, agg.col_count, agg.file_size = len(df), len(df.columns), size
    agg.last_refreshed_at = datetime.utcnow()
    # An aggregate's own column_meta is meant to always be {} -- export policy
    # is resolved through the SOURCE (_policy_dataset), never stored here --
    # but an older build or a direct row edit could still leave this key
    # behind. Strip it on every edit so it cannot outlive whatever put it there.
    agg.column_meta = {k: v for k, v in (agg.column_meta or {}).items() if k != EXPORT_DISABLED_KEY}
    flag_modified(agg, "column_meta")
    for col in (await db.execute(select(DatasetColumn).where(DatasetColumn.dataset_id == agg.id))).scalars().all():
        await db.delete(col)
    # Flush the deletes before the inserts: SQLAlchemy orders INSERT before
    # DELETE within one flush, so a column that keeps its name (tenant,
    # region, row_count) would otherwise briefly exist twice. dataset_columns
    # has no unique constraint on (dataset_id, name) today; the flush keeps
    # this correct if one is ever added.
    await db.flush()
    for col_name, dtype in type_map.items():
        db.add(DatasetColumn(dataset_id=agg.id, name=col_name, dtype=dtype,
                             missing_pct=round(df[col_name].isnull().mean() * 100, 2), stats={}))
    await write_materialization(db, agg.id, str(path), "full", len(df), list(df.columns), None)
    await audit(db, current_user, "dataset.aggregate.update", "dataset", agg.id,
                f"grain {spec['grain']}, {len(df)} rows")
    # AFTER audit(), not before: clear_failure commits internally when a
    # failure row exists, which would otherwise split the transaction and
    # leave the audit row outside the commit this endpoint makes below.
    await clear_failure(db, "dataset", agg.id)
    await db.commit()
    if old_file and old_file != str(path):
        Path(old_file).unlink(missing_ok=True)
        remove_parquet_sidecar(old_file)
    # No cache clear here, deliberately: both the widget-data cache and the
    # DuckDB frame cache key on path + mtime + size, and the rebuild above
    # always allocates a NEW path (`_build_aggregate_file`), so a stale hit
    # is impossible -- while `clear_widget_data_cache()` empties the shared
    # Valkey `wdc:` namespace for EVERY org, not just this one.
    return (await db.execute(select(Dataset).options(selectinload(Dataset.columns))
                             .where(Dataset.id == agg.id))).scalar_one()


@router.get("/{dataset_id}/aggregates")
async def list_aggregates(
    dataset_id: int,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """The aggregates of a source, each with the scheduler's last failure for
    it (a ScheduleFailure row), so a grain a later rule outgrew is visible.

    The scheduler's tick only ever selects `refresh_interval_minutes IS NOT
    NULL`, so an UNSCHEDULED aggregate's guards never run on their own -- a
    default filter added to the source, or the source being re-pointed at a
    different query, would otherwise go unreported forever. For any aggregate
    with no recorded ScheduleFailure, this computes the same two cheap checks
    the scheduler makes (`aggregate_staleness`, shared so the wording cannot
    drift) against the source as it is RIGHT NOW."""
    from ..models.models import ScheduleFailure
    from ..services.aggregates import aggregate_staleness
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    await require_dataset_read(db, current_user, dataset_id)
    aggs = (await db.execute(select(Dataset).options(selectinload(Dataset.columns))
                             .where(Dataset.aggregate_of_dataset_id == dataset_id)
                             .order_by(Dataset.id))).scalars().all()
    out = []
    for a in aggs:
        failure = (await db.execute(select(ScheduleFailure).where(
            ScheduleFailure.kind == "dataset", ScheduleFailure.item_id == a.id))).scalar_one_or_none()
        if failure is not None:
            last_error, attempts = failure.last_error, failure.attempts
        else:
            last_error, attempts = aggregate_staleness(ds, a), 0
        out.append({"dataset": DatasetOut.model_validate(a, from_attributes=True),
                    "last_error": last_error,
                    "attempts": attempts})
    return out


@router.post("/{dataset_id}/rebuild", response_model=DatasetOut)
async def rebuild_dataset(
    dataset_id: int,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Re-run the recipe that built this dataset, replacing its rows.

    Replays the SNAPSHOT taken at save time, not the source's current pipeline:
    editing the source's steps must not silently change a dataset somebody has
    already built reports on. Every refusal is re-evaluated, because rules can
    be added after the fact and a rebuild must not launder newly-governed data.

    Fails HARD (409) where a read would degrade soft. A missing join frame makes
    `_apply_one` a no-op, which on a read costs one widget and on a rebuild
    would silently drop every joined column from a persisted dataset.
    """
    from ..services.prep import (DERIVED_FROM_KEY, derived_from_of,
                                 derived_source_ids, validate_prep_steps)

    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    await require_dataset_capability(db, current_user, dataset_id, "data")

    prov = derived_from_of(ds)
    if not prov:
        raise HTTPException(400, "This dataset was not built from other datasets, so "
                                 "there is no recipe to re-run.")

    steps = prov.get("steps") or []
    base_id = prov.get("source_dataset_id")
    base = await db.get(Dataset, base_id) if isinstance(base_id, int) else None
    if base is None or base.org_id != current_user.org_id:
        raise HTTPException(409, f"The dataset this was built from (#{base_id}) no longer "
                                 f"exists, so it cannot be rebuilt. Its current data is "
                                 f"unchanged.")
    if base.mode == "directquery" or not base.filename:
        raise HTTPException(409, f"'{base.name}' is no longer an import dataset, so this "
                                 f"cannot be rebuilt.")

    known = {r[0] for r in (await db.execute(
        select(DatasetColumn.name).where(DatasetColumn.dataset_id == base.id))).all()}
    join_columns = await _validated_join_columns(db, current_user.org_id, steps)
    try:
        validate_prep_steps(steps, known, join_columns)
    except ValueError as e:
        # A source was re-uploaded without a column the recipe needs. Say which,
        # rather than rebuilding something quietly different.
        raise HTTPException(409, f"The recipe no longer fits its sources: {e}")

    await _refuse_if_ungovernable(db, derived_source_ids(prov) or [base.id])

    try:
        out = await _build_frame(db, current_user, base, steps)
    except FileNotFoundError:
        raise HTTPException(409, "The source dataset's file is missing on the server.")

    path, size, type_map = await _write_frame_as_dataset_file(db, current_user.org_id, out)

    # Swap only once the new file is safely written and charged: any failure
    # above leaves the dataset exactly as it was.
    old = ds.filename
    ds.filename = str(path)
    ds.row_count, ds.col_count, ds.file_size = len(out), len(out.columns), size
    ds.last_refreshed_at = datetime.utcnow()

    for c in (await db.execute(
        select(DatasetColumn).where(DatasetColumn.dataset_id == ds.id))).scalars().all():
        await db.delete(c)
    await db.flush()
    for col_name, dtype in type_map.items():
        db.add(DatasetColumn(
            dataset_id=ds.id, name=col_name, dtype=dtype,
            missing_pct=round(out[col_name].isnull().mean() * 100, 2), stats={}))

    meta = dict(ds.column_meta or {})
    meta[DERIVED_FROM_KEY] = {**prov, "built_by_user_id": current_user.id,
                              "built_at": datetime.utcnow().isoformat() + "Z",
                              "built_rows": int(len(out))}
    ds.column_meta = meta
    flag_modified(ds, "column_meta")

    await audit(db, current_user, "dataset.rebuild", "dataset", ds.id, f"{len(out)} rows")
    await db.commit()

    if old and old != str(path):
        Path(old).unlink(missing_ok=True)
        remove_parquet_sidecar(old)

    return (await db.execute(
        select(Dataset).options(selectinload(Dataset.columns))
        .where(Dataset.id == ds.id))).scalar_one()


# ── Column Formats ────────────────────────────────────────────────────────────

@router.get("/{dataset_id}/column-formats")
async def get_column_formats(dataset_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    return ds.column_formats or {}


@router.put("/{dataset_id}/column-formats")
async def set_column_format(dataset_id: int, req: ColumnFormatRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    # Authoring gate. Open by default (`max_dataset_capability` returns "data"
    # unless every report using this dataset holds the role below it), so this
    # changes nothing for an ordinary install -- but until it was here the
    # control could not be applied AT ALL, and a member the admin had held to
    # "view" could still rewrite this dataset's model for everybody.
    await require_dataset_capability(db, current_user, dataset_id, "data")
    fmts = dict(ds.column_formats or {})
    if req.format is None:
        fmts.pop(req.column, None)
    else:
        fmts[req.column] = req.format.model_dump(exclude_none=True)
    ds.column_formats = fmts
    flag_modified(ds, 'column_formats')
    await db.commit()
    return fmts


@router.post("/{dataset_id}/data-preview")
async def data_preview(dataset_id: int, req: DataPreviewRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    # selectinload(Dataset.columns): run_direct_query's RLS translation needs
    # dataset.columns to validate/resolve column names, and it's called
    # synchronously (not awaited) -- a lazy-loaded relationship accessed there
    # would need an async fetch outside any async context and raise
    # MissingGreenlet, so it must already be loaded before this point.
    result = await db.execute(select(Dataset).options(selectinload(Dataset.columns)).where(Dataset.id == dataset_id))
    ds = result.scalar_one_or_none()
    check_org(ds, current_user, "Dataset not found")
    # Raw rows: the strictest surface there is, and no report to ride in on.
    await require_dataset_read(db, current_user, dataset_id)
    rls_expr = await resolve_rls_expr(db, current_user, dataset_id)
    # Column security, not just row security. The Data tab returned the DENIED
    # column's raw row values -- the most direct form of the leak the rule
    # exists to prevent, and worse than the profile-statistics leak fixed in
    # routers/analysis.py. Verified live before the fix.
    denied = await resolve_denied_columns(db, current_user, dataset_id)

    if ds.mode == "directquery":
        # Same restrictions as the widget-data DirectQuery path: no translation
        # for calculated columns or a dataset-level filter expression yet.
        if req.calculated_columns:
            raise HTTPException(400, "Calculated columns are not yet supported for DirectQuery datasets")
        if ds.default_filter_expr:
            raise HTTPException(400, "Report-level filter expressions are not yet supported for DirectQuery datasets")
        source = await db.get(DataSource, ds.data_source_id)
        check_org(source, current_user, "Data source not found")
        source_cfg = dict(source.config or {})
        source_cfg["type"] = source.type
        try:
            result = run_direct_query(
                source_cfg, ds, {}, widget_type="table", rls_filter_expr=rls_expr,
                cache_ttl_seconds=source.cache_ttl_seconds, cache_epoch=source.cache_epoch,
                org_id=current_user.org_id,
            )
        except DirectQueryUnsupported as e:
            raise HTTPException(400, str(e))
        cols = result.get("columns", [])
        rows = result.get("rows", [])
        if denied:
            keep = [i for i, c in enumerate(cols) if c not in denied]
            cols = [cols[i] for i in keep]
            rows = [[r[i] for i in keep] for r in rows]
        return {"columns": cols, "rows": rows, "total": result.get("total", 0)}

    if not ds.filename:
        raise HTTPException(404, "Dataset not found")

    from ..services.prep import prep_steps_of, resolve_join_frames
    _steps = prep_steps_of(ds)
    _aux = await resolve_join_frames(db, current_user, _steps) if _steps else {}

    def _run():
        import pandas as pd
        from ..services.analytics import load_file
        from ..services.widget_data import apply_calculated_columns, apply_filter_expr as _afe, apply_rls_filter, _safe

        df = load_file(ds.filename)

        # RLS floor — applied before anything else, exactly like the widget-data path.
        # apply_rls_filter fails CLOSED (zero rows) on a malformed rule, unlike the
        # fail-open silent=True behavior used for the non-RLS filters below.
        df = apply_rls_filter(df, rls_expr)

        # Prep pipeline next, so the Data view shows exactly the cleansed frame
        # every widget queries -- same position as the widget-data path.
        from ..services.prep import apply_prep_steps
        df = apply_prep_steps(df, _steps, _aux)

        present = [c for c in denied if c in df.columns]
        if present:
            df = df.drop(columns=present)

        # Apply dataset-level global filter first
        if ds.default_filter_expr:
            df = _afe(df, ds.default_filter_expr, silent=True)

        # Apply calculated columns. An empty request list is the dashboard
        # Data tab (it never sends the saved formulas); fall back to the
        # dataset's own list so a column visible on the dataset page is not
        # missing here. A non-empty request is the dataset page's live editor
        # and wins outright.
        calc_source = req.calculated_columns or ds.calculated_columns or []
        calc_defs = [c for c in calc_source if c.get('name') and c.get('expression')]
        if calc_defs:
            df = apply_calculated_columns(df, calc_defs, ds.custom_functions)

        # Apply filters
        for f in req.filters:
            col = f.get('column')
            op  = f.get('op', 'eq')
            val = f.get('value', '')
            if not col or col not in df.columns:
                continue
            try:
                series = df[col]
                is_num = pd.api.types.is_numeric_dtype(series)
                nv = float(val) if is_num else None
                if op == 'eq':          df = df[series == (nv if is_num else val)]
                elif op == 'ne':        df = df[series != (nv if is_num else val)]
                elif op == 'gt':        df = df[series >  float(val)]
                elif op == 'lt':        df = df[series <  float(val)]
                elif op == 'gte':       df = df[series >= float(val)]
                elif op == 'lte':       df = df[series <= float(val)]
                elif op == 'contains':  df = df[series.astype(str).str.contains(str(val), case=False, na=False)]
                elif op == 'startswith':df = df[series.astype(str).str.startswith(str(val), na=False)]
            except Exception:
                pass

        # Global search across all columns
        if req.search:
            mask = df.astype(str).apply(lambda col: col.str.contains(req.search, case=False, na=False)).any(axis=1)
            df = df[mask]

        total = len(df)

        # Sort
        if req.sort_by and req.sort_by in df.columns:
            df = df.sort_values(req.sort_by, ascending=(req.sort_dir == 'asc'), na_position='last')

        paged  = df.iloc[req.offset: req.offset + req.limit]
        return {'columns': list(paged.columns), 'rows': [[_safe(v) for v in r] for r in paged.values.tolist()], 'total': total}

    try:
        return await asyncio.to_thread(_run)
    except FileNotFoundError:
        raise HTTPException(404, "Dataset file not found on server — please re-upload the file")


@router.patch("/{dataset_id}/filter", response_model=DatasetOut)
async def update_filter_expr(dataset_id: int, body: FilterExprUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    ds.default_filter_expr = body.expression or None
    await db.commit()
    result = await db.execute(select(Dataset).options(selectinload(Dataset.columns)).where(Dataset.id == dataset_id))
    return result.scalar_one()


@router.post("/{dataset_id}/filter-preview")
async def preview_filter_expr(dataset_id: int, req: FilterPreviewRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    if not ds.filename:
        raise HTTPException(404, "Dataset not found")
    rls_expr = await resolve_rls_expr(db, current_user, dataset_id)
    # Column security: a filter preview over a denied column answered
    # "how many rows have revenue > 5000" for the very column the rule hides --
    # a predicate oracle. Verified live before the fix.
    denied = await resolve_denied_columns(db, current_user, dataset_id)

    from ..services.prep import apply_prep_steps, prep_steps_of, resolve_join_frames
    _fp_steps = prep_steps_of(ds)
    _fp_aux = await resolve_join_frames(db, current_user, _fp_steps) if _fp_steps else {}

    def _run():
        from ..services.analytics import load_file
        from ..services.widget_data import apply_calculated_columns, apply_filter_expr as _afe, apply_rls_filter

        df = load_file(ds.filename)
        df = apply_rls_filter(df, rls_expr)
        df = apply_prep_steps(df, _fp_steps, _fp_aux)
        present = [c for c in denied if c in df.columns]
        if present:
            df = df.drop(columns=present)
        total = len(df)

        if req.calculated_columns:
            calc_defs = [c for c in req.calculated_columns if c.get('name') and c.get('expression')]
            if calc_defs:
                df = apply_calculated_columns(df, calc_defs, ds.custom_functions)

        try:
            filtered = _afe(df, req.expression)
            return {'ok': True, 'passing': len(filtered), 'total': total}
        except Exception as e:
            return {'ok': False, 'error': str(e), 'total': total}

    try:
        return await asyncio.to_thread(_run)
    except FileNotFoundError:
        raise HTTPException(404, "Dataset file not found on server — please re-upload the file")


@router.post("/{dataset_id}/refresh", response_model=DatasetOut)
async def refresh_dataset(
    dataset_id: int, body: DatasetRefreshRequest = DatasetRefreshRequest(),
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Re-fetch data from the original database connection.

    F3: `body.mode` picks full reload (re-run the stored query/table wholesale)
    or watermark-driven incremental (append only rows past the last cursor and
    advance it). The Watermark row IS the persisted config — a manual
    `cursor_column` here both drives this run and, once set, carries over to
    the next one and to the background scheduler.
    """
    import time
    from datetime import datetime as _dt
    from ..models.models import Watermark
    from ..services.dataset_refresh import refresh_dataset as run_refresh, write_materialization
    from ..services.query_log import log_query_run_sync

    result = await db.execute(
        select(Dataset).options(selectinload(Dataset.columns)).where(Dataset.id == dataset_id)
    )
    dataset = result.scalar_one_or_none()
    check_org(dataset, current_user, "Dataset not found")
    await require_dataset_capability(db, current_user, dataset_id, "data")

    if dataset.mode == "directquery":
        raise HTTPException(400, "DirectQuery datasets always query the live source — there's nothing to refresh")
    if not dataset.data_source_id:
        raise HTTPException(400, "This dataset was not imported from a database connection")
    if not dataset.source_table and not dataset.source_query:
        raise HTTPException(400, "Source query not recorded — re-import from the Connections page")

    src = await db.get(DataSource, dataset.data_source_id)
    check_org(src, current_user, "Original data source no longer exists")

    cfg = dict(src.config)
    cfg['type'] = src.type

    watermark = (await db.execute(
        select(Watermark).where(Watermark.dataset_id == dataset_id)
    )).scalar_one_or_none()

    requested_mode = "incremental" if body.mode == "incremental" else "full"
    cursor_column = body.cursor_column or (watermark.cursor_column if watermark else None)
    # A cursor value only applies to the SAME column it was measured on -- switching
    # the watermark column mid-flight must not filter by a value from a different one.
    cursor_value = (watermark.cursor_value
                    if watermark and watermark.cursor_column == cursor_column else None)

    # Allowlist for the cursor-column identifier the incremental query below
    # interpolates: this dataset's own known columns, captured before the
    # delete+recreate further down touches them.
    known_columns = {c.name for c in dataset.columns}
    # semantic_type is set by metadata sync / the RLS builder / auto-generate,
    # never re-derived from the refreshed data, so it has to be carried
    # forward by name across the delete+recreate below or every one of those
    # features silently degrades until the next metadata sync.
    semantic_types = {c.name: c.semantic_type for c in dataset.columns if c.semantic_type}

    start = time.monotonic()
    try:
        outcome = await asyncio.to_thread(
            run_refresh, cfg, dataset.filename, dataset.source_table, dataset.source_query,
            requested_mode, cursor_column, cursor_value, known_columns,
        )
    except Exception as e:
        raise HTTPException(400, f"Refresh failed: {e}")
    duration_ms = int((time.monotonic() - start) * 1000)

    df, type_map = outcome["df"], outcome["type_map"]
    dataset.row_count = len(df)
    dataset.col_count = len(df.columns)
    dataset.file_size = Path(dataset.filename).stat().st_size if dataset.filename else 0
    dataset.last_refreshed_at = _dt.utcnow()

    for col in list(dataset.columns):
        await db.delete(col)
    await db.flush()
    for col_name, dtype in type_map.items():
        db.add(DatasetColumn(
            dataset_id=dataset.id, name=col_name, dtype=dtype,
            missing_pct=round(df[col_name].isnull().mean() * 100, 2), stats={},
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

    await db.commit()

    log_query_run_sync(
        org_id=current_user.org_id, source_kind="refresh", data_source_id=dataset.data_source_id,
        dataset_id=dataset.id, sql_hash=None, rows_returned=len(df),
        duration_ms=duration_ms, executor="pandas", cache_hit=False,
    )

    result2 = await db.execute(
        select(Dataset).options(selectinload(Dataset.columns)).where(Dataset.id == dataset_id)
    )
    ds_out = result2.scalar_one()
    ds_out.refresh_warning = outcome.get("warning")
    return ds_out


# ── Data alerts ───────────────────────────────────────────────────────────────
from ..models.models import DataAlert  # noqa: E402
from ..services.delivery import valid_recipients as _valid_recipients  # noqa: E402
from ..services.widget_data import _validate_expr_safety  # noqa: E402


@router.get("/{dataset_id}/alerts")
async def list_alerts(dataset_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    # Belonging to the org is not permission to read the dataset. An alert
    # names a condition over its rows and carries recipient addresses; the
    # 404 matches what /datasets/{id} and widget-data already answer.
    await require_dataset_read(db, current_user, dataset_id)
    rows = (await db.execute(
        select(DataAlert).where(DataAlert.dataset_id == dataset_id)
    )).scalars().all()
    return [{"id": a.id, "name": a.name, "expression": a.expression,
             "interval_minutes": a.interval_minutes, "recipients": a.recipients,
             "last_state": a.last_state, "last_status": a.last_status,
             "last_checked_at": a.last_checked_at} for a in rows]


@router.post("/{dataset_id}/alerts", status_code=201)
async def create_alert(dataset_id: int, body: dict, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Watch a condition on this dataset. The expression is validated by the same
    sandbox gate widgets use, at creation time -- an alert that fails validation on
    every tick would only ever report evaluation errors."""
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    await require_dataset_read(db, current_user, dataset_id)

    name = str(body.get("name") or "").strip()[:200]
    expression = str(body.get("expression") or "").strip()
    if not name or not expression:
        raise HTTPException(400, "name and expression are required")
    try:
        _validate_expr_safety(expression)
    except Exception as e:
        raise HTTPException(400, f"expression rejected: {e}")
    interval = max(15, int(body.get("interval_minutes") or 60))
    recipients = _valid_recipients(body.get("recipients"))
    if not recipients:
        raise HTTPException(400, "At least one valid recipient email is required")

    alert = DataAlert(org_id=current_user.org_id, dataset_id=dataset_id,
                      creator_user_id=current_user.id, name=name, expression=expression,
                      interval_minutes=interval, recipients=recipients)
    db.add(alert)
    await db.commit()
    return {"id": alert.id, "name": alert.name}


@router.delete("/{dataset_id}/alerts/{alert_id}", status_code=204)
async def delete_alert(dataset_id: int, alert_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    await require_dataset_read(db, current_user, dataset_id)
    alert = await db.get(DataAlert, alert_id)
    check_org(alert, current_user, "Alert not found")
    # The alert must belong to the dataset in the PATH. Without this, the
    # dataset segment is decoration: any alert id in the org could be deleted
    # through a dataset the caller happens to be allowed to read.
    if alert.dataset_id != dataset_id:
        raise HTTPException(404, "Alert not found")
    await db.delete(alert)
    await db.commit()


# ── Sharing (SH1) ──────────────────────────────────────────────────────────────
# A dataset has no owner concept in this codebase (unlike reports, which have
# per-role capabilities), so who may manage a dataset's shares mirrors the admin
# gating used elsewhere (row-security rules, users) rather than an ownership
# check: org admin only. Read access to any dataset is already open to every org
# member (list_datasets/get_dataset above), so the share row itself only carries
# visibility metadata (the `shared: true` flag) -- RLS is what actually narrows a
# shared viewer's rows, resolved as THEIR identity at the base-frame choke point.
from ..models.models import DatasetShare  # noqa: E402
from ..schemas.schemas import DatasetShareCreate  # noqa: E402


@router.get("/{dataset_id}/shares", response_model=list[DatasetShareOut])
async def list_dataset_shares(dataset_id: int, db: AsyncSession = Depends(get_db),
                              current_user: User = Depends(require_org_admin)):
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    rows = (await db.execute(
        select(DatasetShare, User.email).join(User, User.id == DatasetShare.user_id)
        .where(DatasetShare.dataset_id == dataset_id)
        .order_by(DatasetShare.created_at.desc())
    )).all()
    return [{"id": s.id, "user_id": s.user_id, "email": email, "created_at": s.created_at} for s, email in rows]


@router.post("/{dataset_id}/shares", response_model=DatasetShareOut, status_code=201)
async def create_dataset_share(dataset_id: int, body: DatasetShareCreate, db: AsyncSession = Depends(get_db),
                               current_user: User = Depends(require_org_admin)):
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    target = await db.get(User, body.user_id)
    # 404-never-403: a cross-org user id reads identically to a nonexistent one.
    check_org(target, current_user, "User not found")

    existing = (await db.execute(
        select(DatasetShare).where(DatasetShare.dataset_id == dataset_id, DatasetShare.user_id == body.user_id)
    )).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(400, "Dataset already shared with this user")

    share = DatasetShare(dataset_id=dataset_id, user_id=body.user_id)
    db.add(share)
    await audit(db, current_user, "dataset.share_created", "dataset", dataset_id, target.email)
    from ..services import admin_audit
    await admin_audit.record(db, current_user, "dataset_share.create", f"dataset:{dataset_id}", target.email)
    await db.commit()
    await db.refresh(share)
    return {"id": share.id, "user_id": share.user_id, "email": target.email, "created_at": share.created_at}


@router.delete("/{dataset_id}/shares/{share_id}", status_code=204)
async def delete_dataset_share(dataset_id: int, share_id: int, db: AsyncSession = Depends(get_db),
                               current_user: User = Depends(require_org_admin)):
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    share = await db.get(DatasetShare, share_id)
    if share is None or share.dataset_id != dataset_id:
        raise HTTPException(404, "Share not found")
    await audit(db, current_user, "dataset.share_revoked", "dataset", dataset_id, str(share.user_id))
    from ..services import admin_audit
    await admin_audit.record(db, current_user, "dataset_share.revoke", f"dataset:{dataset_id}", str(share.user_id))
    await db.delete(share)
    await db.commit()
