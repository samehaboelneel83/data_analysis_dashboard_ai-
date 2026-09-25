import asyncio
import csv
import io
from pathlib import Path
import pandas as pd
from sqlalchemy import select
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified
from ..core.database import get_db
from ..core.config import settings
from ..core.capability import readable_dataset_ids
from ..core.org_scope import check_org
from ..services import connectors, secrets
from ..services.custom_connectors import apply_preset_locks
from ..services.frame_cache import write_parquet_sidecar
from ..dependencies import get_current_user, require_org_admin
from ..models.models import CustomConnector, DataSource, Dataset, DatasetColumn, User
from ..schemas.schemas import DataSourceCreate, DataSourceUpdate, DataSourceOut, TablePreviewRequest, ImportRequest
from ..services.connections import test_connection, list_tables, preview_table, import_to_dataframe
from ..services.analytics import detect_types
from ..services.ingest import duplicate_columns, missing_pct
from pydantic import BaseModel, Field
from ..services import knowledge, quotas

import logging

router = APIRouter(prefix="/data-sources", tags=["data-sources"])

logger = logging.getLogger(__name__)


def _redacted(ds: DataSource, custom_connector_label: str | None = None) -> DataSourceOut:
    """A DataSourceOut whose secret config fields are the redaction sentinel, so
    ciphertext never leaves the server. Built as a fresh response model rather than by
    mutating the ORM row, so the stored (encrypted) config is never touched."""
    out = DataSourceOut.model_validate(ds)
    out.config = secrets.redact_config(ds.config or {}, connectors.secret_field_names(ds.type))
    out.custom_connector_label = custom_connector_label
    return out


async def _label_for(db: AsyncSession, ds: DataSource) -> str | None:
    if ds.custom_connector_id is None:
        return None
    return (await db.execute(
        select(CustomConnector.label).where(CustomConnector.id == ds.custom_connector_id,
                                             CustomConnector.org_id == ds.org_id)
    )).scalar_one_or_none()


async def _administrable_or_404(ds: DataSource, db: AsyncSession, user: User) -> None:
    """Two different refusals, in the order that leaks least.

    A connection you cannot even SEE gets 404 -- a 403 would confirm the id is
    real, which is the discipline org scoping and draft privacy already keep.
    One you can see but do not own gets 403, which is the honest answer: it
    exists, it is not yours to change.
    """
    visible = await _visible_source_ids(db, user)
    if visible is not None and ds.id not in visible:
        raise HTTPException(404, "Data source not found")
    if not _may_administer(ds, user):
        raise HTTPException(403, "Only an admin or the person who added this "
                                 "connection can change it")


def _may_administer(ds: DataSource, user: User) -> bool:
    """An org admin, or whoever added the connection.

    `created_by` is nullable: rows from before 0020 and anything a seeder made
    have no owner, and those stay admin-only rather than everyone-editable --
    "nobody owns it" must not read as "anybody may delete it". Migration 0020
    backfills live rows to an org admin, so this is the seeded/test case.
    """
    if user.role and user.role.is_org_admin:
        return True
    return ds.created_by is not None and ds.created_by == user.id


async def _visible_source_ids(db: AsyncSession, user: User) -> set[int] | None:
    """Connections this user may SEE. None means all of them (admins).

    Yours, plus any that backs a dataset you can read -- a member who was
    given a dataset still needs to see the connection behind it for the
    dataset picker and the Ask-AI scope selector to make sense. Seeing a
    connection is not using it: the config comes back redacted, importing
    stays admin-only, and changing it needs `_may_administer` below.
    """
    if user.role and user.role.is_org_admin:
        return None
    ids = set((await db.execute(
        select(DataSource.id).where(
            DataSource.org_id == user.org_id,
            or_(DataSource.created_by == user.id, DataSource.created_by.is_(None)))
    )).scalars().all())
    readable = await readable_dataset_ids(db, user)
    q = select(Dataset.data_source_id).where(
        Dataset.org_id == user.org_id, Dataset.data_source_id.isnot(None))
    if readable is not None:
        q = q.where(Dataset.id.in_(readable or {-1}))
    ids |= set(x for x in (await db.execute(q)).scalars().all() if x is not None)
    return ids


@router.get("", response_model=list[DataSourceOut])
async def list_data_sources(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(
        select(DataSource).where(DataSource.org_id == current_user.org_id).order_by(DataSource.created_at.desc())
    )
    sources = list(result.scalars().all())
    visible = await _visible_source_ids(db, current_user)
    if visible is not None:
        sources = [ds for ds in sources if ds.id in visible]
    cc_ids = {ds.custom_connector_id for ds in sources if ds.custom_connector_id is not None}
    labels: dict[int, str] = {}
    if cc_ids:
        rows = (await db.execute(
            select(CustomConnector.id, CustomConnector.label).where(
                CustomConnector.id.in_(cc_ids), CustomConnector.org_id == current_user.org_id)
        )).all()
        labels = {i: lbl for i, lbl in rows}
    return [_redacted(ds, labels.get(ds.custom_connector_id)) for ds in sources]


@router.post("", response_model=DataSourceOut)
async def create_data_source(body: DataSourceCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    preset = None
    if body.custom_connector_id is not None:
        preset = (await db.execute(
            select(CustomConnector).where(CustomConnector.id == body.custom_connector_id,
                                           CustomConnector.org_id == current_user.org_id)
        )).scalar_one_or_none()
        if preset is None:
            raise HTTPException(404, "Custom connector not found")
        ds_type = preset.base_type
    else:
        ds_type = body.type
    _require_known_connector(ds_type)
    config = apply_preset_locks(body.config or {}, preset) if preset is not None else (body.config or {})
    config = secrets.encrypt_config(config, connectors.secret_field_names(ds_type))
    ds = DataSource(name=body.name, type=ds_type, config=config,
                    custom_connector_id=(preset.id if preset else None),
                    org_id=current_user.org_id, created_by=current_user.id)
    db.add(ds)
    await db.commit()
    await db.refresh(ds)

    out = _redacted(ds, preset.label if preset else None)
    out.sync_run_id = await _start_initial_sync(db, ds, current_user)
    return out


class ConnectionProbe(BaseModel):
    """Settings to try BEFORE they are saved (the New/Edit connection form)."""
    type: str
    config: dict = {}
    custom_connector_id: int | None = None
    # When editing: a secret sent back as the redaction sentinel means "the one
    # already stored on this connection", exactly as on update.
    source_id: int | None = None


@router.post("/test")
async def test_unsaved_connection(body: ConnectionProbe, db: AsyncSession = Depends(get_db),
                                  current_user: User = Depends(require_org_admin)):
    """Try a connection's settings without saving anything.

    The form could only test a connection that already existed, so the only
    way to find a typo in a password was to create a broken connection first.
    Nothing is written: no row, no sync, no audit entry. Org admins only --
    it is a live probe of an arbitrary host, like the one on a saved source.
    """
    preset = None
    ds_type = body.type
    if body.custom_connector_id is not None:
        preset = (await db.execute(
            select(CustomConnector).where(CustomConnector.id == body.custom_connector_id,
                                           CustomConnector.org_id == current_user.org_id)
        )).scalar_one_or_none()
        if preset is None:
            raise HTTPException(404, "Custom connector not found")
        ds_type = preset.base_type
    _require_known_connector(ds_type)
    cfg = dict(body.config or {})
    secret_names = connectors.secret_field_names(ds_type)
    if body.source_id is not None:
        ds = await db.get(DataSource, body.source_id)
        check_org(ds, current_user, "Data source not found")
        await _administrable_or_404(ds, db, current_user)
        stored = ds.config or {}
        for name in secret_names:
            if cfg.get(name) == secrets.REDACTED:
                cfg[name] = stored.get(name)
    if preset is not None:
        cfg = apply_preset_locks(cfg, preset)
    cfg = secrets.decrypt_config(cfg, secret_names)
    cfg['type'] = ds_type
    return await asyncio.to_thread(test_connection, cfg)


async def _start_initial_sync(db: AsyncSession, ds: DataSource,
                              user: User) -> int | None:
    """Read the new connection's catalog, without being asked.

    Creating a connection used to do nothing else: the row was saved, a toast
    said "Connection created", and the person who had just plugged in a database
    they did not know was left looking at a list of table names. Everything that
    explains a database -- the plain-language overview, the per-table and
    per-column descriptions, inferred joins, entities -- lives behind a sync that
    nothing prompted them to run, reachable only from a row menu.

    So the connection describes itself on arrival. The run is detached, exactly
    like `POST /{id}/sync`: the response returns immediately with the run id, and
    the review page watches it finish.

    Returns the run id, or None when there is nothing to sync -- which is not an
    error and must never fail the create. A connection that cannot be
    introspected is still a perfectly good connection.
    """
    from ..models.models import SyncRun
    from ..core.database import AsyncSessionLocal
    from ..services import llm as llm_service
    from ..services.metadata import cache as cache_module, sync

    cfg = dict(ds.config or {})
    cfg["type"] = ds.type
    try:
        run = SyncRun(data_source_id=ds.id, org_id=ds.org_id,
                      trigger="on_create", status="running", stages=[])
        db.add(run)
        await db.commit()
        await db.refresh(run)

        asyncio.create_task(sync.run_sync_background(
            AsyncSessionLocal, run.id, ds.id, ds.org_id,
            cache=cache_module.get_cache(),
            llm_client=llm_service.get_client(),
            allow_llm=bool(ds.allow_llm_sampling),
            source_config=cfg,
        ))
        return run.id
    except Exception:                                        # noqa: BLE001
        # The connection is created either way. A failure to START describing it
        # is a missing convenience, not a failed request -- and the user can run
        # the sync by hand from the review page, which is what they had to do
        # before this existed.
        logger.exception("could not start the initial sync for data source %s", ds.id)
        return None


@router.get("/connectors")
async def list_connectors(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """The connector catalog for the connection UI — labels, icons, categories and
    per-connector config-field specs, plus this org's custom connector presets.
    The single source of truth the frontend renders from. No secrets, no dialects."""
    presets = (await db.execute(
        select(CustomConnector).where(CustomConnector.org_id == current_user.org_id)
        .order_by(CustomConnector.created_at.desc())
    )).scalars().all()
    return connectors.catalog_payload(presets)


def _require_known_connector(type_key: str | None) -> None:
    if type_key is not None and not connectors.is_known(type_key):
        raise HTTPException(400, f"Unknown connector type '{type_key}'")


@router.get("/{ds_id}/index-advice")
async def index_advice_for_source(
    ds_id: int, days: int = 30,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Which filter columns this source has been queried on, and which of them
    have no index -- from the platform's own query log, never from the SQL.

    Recommendations only: nothing creates an index on a customer database.
    Grouped columns are deliberately absent (services/index_advice.py).
    """
    from datetime import datetime, timedelta

    from ..models.models import QueryRun
    from ..services import index_advice

    ds = await db.get(DataSource, ds_id)
    check_org(ds, current_user, "Data source not found")
    since = datetime.utcnow() - timedelta(days=max(1, min(days, 365)))
    rows = (await db.execute(
        select(QueryRun.source_table, QueryRun.filter_columns, QueryRun.group_column,
               QueryRun.duration_ms)
        .where(QueryRun.data_source_id == ds.id, QueryRun.source_kind == "directquery",
               QueryRun.cache_hit.is_(False), QueryRun.created_at >= since,
               QueryRun.source_table.isnot(None))
    )).all()
    runs = [{"source_table": t, "filter_columns": f, "group_column": g, "duration_ms": d}
            for t, f, g, d in rows]
    tables = {r["source_table"] for r in runs}
    cfg = dict(ds.config or {})
    cfg["type"] = ds.type
    try:
        # The customer's database, in a thread: a slow or dead source must not
        # stall the loop, and its absence must not blank the advice.
        indexed = await asyncio.to_thread(index_advice.leading_index_columns, cfg, tables)
        # None: not a Postgres source, so the catalog could not be asked and no
        # statement is offered -- said as such, never as a false "checked".
        index_check = "checked" if indexed is not None else "unsupported"
    except Exception:  # noqa: BLE001 -- advice without the indexed flag beats no advice
        indexed, index_check = set(), "unavailable"
    out = index_advice.advise(runs, indexed)
    out.update({"observed_days": days, "runs_considered": len(runs), "index_check": index_check})
    return out


@router.get("/{ds_id}", response_model=DataSourceOut)
async def get_data_source(ds_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(DataSource, ds_id)
    check_org(ds, current_user, "Data source not found")
    visible = await _visible_source_ids(db, current_user)
    if visible is not None and ds.id not in visible:
        raise HTTPException(404, "Data source not found")
    return _redacted(ds, await _label_for(db, ds))


@router.put("/{ds_id}", response_model=DataSourceOut)
async def update_data_source(ds_id: int, body: DataSourceUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(DataSource, ds_id)
    check_org(ds, current_user, "Data source not found")
    await _administrable_or_404(ds, db, current_user)
    if body.name is not None:
        ds.name = body.name

    preset = None
    if body.custom_connector_id is not None:
        preset = (await db.execute(
            select(CustomConnector).where(CustomConnector.id == body.custom_connector_id,
                                           CustomConnector.org_id == current_user.org_id)
        )).scalar_one_or_none()
        if preset is None:
            raise HTTPException(404, "Custom connector not found")
        ds.type = preset.base_type
        ds.custom_connector_id = preset.id
    elif ds.custom_connector_id is not None:
        # A preset is already attached. body.type must never be able to detach
        # it implicitly or desynchronize ds.type from the preset's base_type --
        # that gap let a same-org PUT {"type": ...} rewrite ds.type away from
        # the preset while a locked secret was still being decrypted/merged
        # under the OLD (preset's) secret-field set, writing it to disk and
        # the response in plaintext. body.type is silently ignored here,
        # exactly as it already is on create when custom_connector_id is set.
        preset = (await db.execute(
            select(CustomConnector).where(CustomConnector.id == ds.custom_connector_id,
                                           CustomConnector.org_id == ds.org_id)
        )).scalar_one_or_none()
        if preset is not None:
            ds.type = preset.base_type
    elif body.type is not None:
        _require_known_connector(body.type)
        ds.type = body.type

    config_needs_merge = body.config is not None or body.custom_connector_id is not None
    if config_needs_merge:
        secret_names = connectors.secret_field_names(ds.type)
        stored = ds.config or {}
        if body.config is not None:
            # A secret field sent back as the redaction sentinel means "unchanged" — keep the
            # stored (encrypted) value; anything else is a new secret to encrypt.
            merged = dict(body.config)
            for name in secret_names:
                if merged.get(name) == secrets.REDACTED:
                    merged[name] = stored.get(name)
        else:
            merged = secrets.decrypt_config(stored, secret_names)
        if preset is not None:
            merged = apply_preset_locks(merged, preset)
        ds.config = secrets.encrypt_config(merged, secret_names)
        flag_modified(ds, 'config')

    if body.cache_ttl_seconds is not None:
        ds.cache_ttl_seconds = body.cache_ttl_seconds
    await db.commit()
    await db.refresh(ds)
    return _redacted(ds, await _label_for(db, ds))


@router.delete("/{ds_id}", status_code=204)
async def delete_data_source(ds_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(DataSource, ds_id)
    check_org(ds, current_user, "Data source not found")
    await _administrable_or_404(ds, db, current_user)
    await db.delete(ds)
    await db.commit()


@router.post("/{ds_id}/test")
async def test_data_source(ds_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(DataSource, ds_id)
    check_org(ds, current_user, "Data source not found")
    # A live credential probe, so it belongs with the other administration.
    await _administrable_or_404(ds, db, current_user)
    cfg = dict(ds.config)
    cfg['type'] = ds.type
    result = await asyncio.to_thread(test_connection, cfg)
    return result


@router.get("/{ds_id}/schema")
async def get_schema(ds_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await db.get(DataSource, ds_id)
    check_org(ds, current_user, "Data source not found")
    cfg = dict(ds.config)
    cfg['type'] = ds.type
    try:
        tables = await asyncio.to_thread(list_tables, cfg)
        return {'tables': tables}
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/{ds_id}/preview")
async def preview_data(ds_id: int, req: TablePreviewRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_org_admin)):
    ds = await db.get(DataSource, ds_id)
    check_org(ds, current_user, "Data source not found")
    cfg = dict(ds.config)
    cfg['type'] = ds.type
    try:
        result = await asyncio.to_thread(preview_table, cfg, req.table, req.query, req.limit)
        return result
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/{ds_id}/import")
async def import_dataset(ds_id: int, req: ImportRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_org_admin)):
    ds = await db.get(DataSource, ds_id)
    check_org(ds, current_user, "Data source not found")
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
        check_org(existing, current_user, "Dataset not found")

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
            raise HTTPException(
                400, f"{spec.label} cannot be queried live — import the table "
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
            raise HTTPException(400, str(e))

        probe_df = pd.DataFrame(preview['rows'], columns=preview['columns'])
        type_map = detect_types(probe_df) if len(probe_df) else {}
        new_cols = [DatasetColumn(name=c, dtype=type_map.get(c, 'unknown'), stats={}) for c in preview['columns']]

        if existing is not None:
            existing.name = req.dataset_name
            existing.description = f"DirectQuery from {ds.name} ({ds.type})"
            existing.data_source_id = ds_id
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
            await db.commit()
            await db.refresh(existing)
            return {'id': existing.id, 'name': existing.name, 'row_count': 0, 'col_count': existing.col_count, 'mode': 'directquery'}

        dataset = Dataset(
            name=req.dataset_name,
            description=f"DirectQuery from {ds.name} ({ds.type})",
            filename=None, row_count=0, col_count=len(preview['columns']), file_size=0,
            data_source_id=ds_id, source_table=req.table, source_query=req.query,
            query_model=req.query_model, mode="directquery", org_id=current_user.org_id,
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
        await db.commit()
        await db.refresh(dataset)
        return {'id': dataset.id, 'name': dataset.name, 'row_count': 0, 'col_count': dataset.col_count, 'mode': 'directquery'}

    def _run(file_path_hint: str | None):
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
        if file_path_hint:
            file_path = Path(file_path_hint)
            file_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            upload_dir = Path(settings.upload_dir)
            upload_dir.mkdir(parents=True, exist_ok=True)
            safe_name = req.dataset_name.replace(' ', '_').replace('/', '_')
            file_path = upload_dir / f"{safe_name}.csv"
        # Type detection BEFORE the write, not after. `detect_types` converts in
        # place -- an epoch-integer column becomes real datetimes, a text date
        # column becomes datetimes -- and running it afterwards left that
        # conversion in a frame that had already been serialised. The dataset was
        # then labelled `datetime` while every widget re-read integers off the
        # CSV, which is a disagreement no unit test on the type can see.
        type_map = detect_types(df)
        df.to_csv(file_path, index=False)
        write_parquet_sidecar(str(file_path))  # already on a worker thread
        return df, str(file_path), type_map

    try:
        df, file_path, type_map = await asyncio.to_thread(_run, existing.filename if existing is not None else None)
    except Exception as e:
        raise HTTPException(400, str(e))

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
        existing.data_source_id = ds_id
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
    except HTTPException:
        Path(file_path).unlink(missing_ok=True)
        raise

    dataset = Dataset(
        name=req.dataset_name,
        description=f"Imported from {ds.name} ({ds.type})",
        filename=file_path,
        row_count=len(df),
        col_count=len(df.columns),
        file_size=Path(file_path).stat().st_size,
        data_source_id=ds_id,
        source_table=req.table,
        source_query=req.query,
        query_model=req.query_model,
        org_id=current_user.org_id,
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
    await db.commit()
    await db.refresh(dataset)
    return {'id': dataset.id, 'name': dataset.name, 'row_count': dataset.row_count, 'col_count': dataset.col_count, 'mode': 'import'}


class SimilarDatasetsRequest(BaseModel):
    """What a dataset WOULD be built from, before anything is created."""
    columns: list[str] = Field(default_factory=list, max_length=500)
    table: str | None = Field(default=None, max_length=500)
    query: str | None = None


@router.post("/{ds_id}/similar-datasets")
async def find_similar_datasets(ds_id: int, body: SimilarDatasetsRequest,
                                db: AsyncSession = Depends(get_db),
                                current_user: User = Depends(get_current_user)):
    """Datasets already built from this connection that cover these columns.

    The step that was missing from the AI path. Asked to build a dashboard, the
    platform would import a fresh dataset every time -- a shelf of near-identical
    datasets nobody chose, each refreshing on its own schedule, each drifting
    apart from the others.

    Advisory only. Nothing here blocks a create, and no caller should treat it as
    a refusal: the person asked for something, and the honest response is "you
    may already have this" followed by doing what they say. An empty list is the
    common and correct answer.
    """
    ds = await db.get(DataSource, ds_id)
    check_org(ds, current_user, "Data source not found")
    visible = await _visible_source_ids(db, current_user)
    if visible is not None and ds.id not in visible:
        raise HTTPException(404, "Data source not found")

    matches = await knowledge.similar_datasets(
        db, source_id=ds_id, org_id=current_user.org_id,
        column_names=[c for c in body.columns if c],
        table=body.table, query=body.query)

    # Scoped to what this person may actually open. Naming a dataset they cannot
    # read would leak its existence and its columns, and suggesting they reuse
    # something they cannot see is not a suggestion at all.
    readable = await readable_dataset_ids(db, current_user)
    if readable is not None:
        matches = [m for m in matches if m.dataset_id in readable]

    return {"matches": [{
        "dataset_id": m.dataset_id, "name": m.name, "mode": m.mode,
        "row_count": m.row_count, "overlap": m.overlap, "coverage": m.coverage,
        "matched_columns": m.matched_columns, "by_name": m.by_name,
    } for m in matches]}


# ── Visual query builder ──────────────────────────────────────────────────────

@router.get("/{ds_id}/tables/{table}/columns")
async def get_table_columns(ds_id: int, table: str, db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(get_current_user)):
    """One table's columns from the live connection, for the builder's pickers."""
    from ..services.query_builder import introspect_tables, table_columns
    ds = await db.get(DataSource, ds_id)
    check_org(ds, current_user, "Data source not found")
    cfg = dict(ds.config)
    cfg['type'] = ds.type

    def _run():
        # membership check first: an unknown table 400s before any column query
        introspect_tables(cfg, [table])
        return table_columns(cfg, table)

    try:
        return await asyncio.to_thread(_run)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(400, f"Could not read the table's columns: {e}")


@router.get("/{ds_id}/functions")
async def get_functions(ds_id: int, db: AsyncSession = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    """The connection's scalar functions, for the builder's diagram and the
    function picker. Empty where the dialect has no queryable catalogue."""
    from ..services.query_builder import list_functions
    ds = await db.get(DataSource, ds_id)
    check_org(ds, current_user, "Data source not found")
    cfg = dict(ds.config)
    cfg['type'] = ds.type
    return await asyncio.to_thread(list_functions, cfg)


@router.post("/{ds_id}/build-query")
async def compile_query(ds_id: int, model: dict, db: AsyncSession = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    """Compile the visual model to SQL WITHOUT running it -- the builder shows
    the statement as it evolves. Every identifier is membership-checked against
    the live schema; the compile itself is the validation."""
    from ..services.query_builder import build_sql, introspect_tables, referenced_tables
    ds = await db.get(DataSource, ds_id)
    check_org(ds, current_user, "Data source not found")
    cfg = dict(ds.config)
    cfg['type'] = ds.type

    def _run():
        from ..services.query_builder import list_functions, referenced_functions
        known = introspect_tables(cfg, referenced_tables(model))
        funcs = {f["name"] for f in list_functions(cfg)} if referenced_functions(model) else set()
        return build_sql(model, connectors.sql_family_of(cfg) or ds.type, known, cfg.get('schema') or None, funcs)

    try:
        return {"sql": await asyncio.to_thread(_run)}
    except (ValueError, KeyError) as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(400, f"Could not compile the query: {e}")


@router.post("/{ds_id}/build-query/preview")
async def preview_built_query(ds_id: int, model: dict, db: AsyncSession = Depends(get_db),
                              current_user: User = Depends(get_current_user)):
    """Compile then run with a hard preview cap, returning rows + the SQL --
    what the builder's data pane shows."""
    from ..services.connections import preview_table
    from ..services.query_builder import build_sql, introspect_tables, referenced_tables
    ds = await db.get(DataSource, ds_id)
    check_org(ds, current_user, "Data source not found")
    cfg = dict(ds.config)
    cfg['type'] = ds.type

    def _run():
        from ..services.query_builder import list_functions, referenced_functions
        known = introspect_tables(cfg, referenced_tables(model))
        funcs = {f["name"] for f in list_functions(cfg)} if referenced_functions(model) else set()
        capped = {**model, "limit": min(int(model.get("limit") or 100), 200)}
        sql = build_sql(capped, connectors.sql_family_of(cfg) or ds.type, known, cfg.get('schema') or None, funcs)
        result = preview_table(cfg, None, sql, limit=200)
        result["sql"] = sql
        return result

    try:
        return await asyncio.to_thread(_run)
    except (ValueError, KeyError) as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(400, f"Query failed: {e}")
