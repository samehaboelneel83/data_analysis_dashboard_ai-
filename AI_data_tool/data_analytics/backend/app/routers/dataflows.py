"""Dataflows: a transformation as a first-class object.

A prep pipeline belongs to one dataset and a materialized result records its
recipe in that dataset's `column_meta`. Both are owned by a dataset, and that
ownership is the limit this router lifts. A Dataflow owns the recipe, can produce
SEVERAL outputs, carries its own schedule, and -- the reason it exists -- has its
own authoring permissions instead of inheriting whatever the reports that happen
to use its output allow.

WHAT IS GATED, AND WHAT IS NOT
------------------------------
Authoring is gated: edit the recipe, change the schedule, run it, delete it,
grant capabilities. Reading is NOT. An output is an ordinary dataset, readable by
any member of the org with row-level security narrowing rows as the reader's own
identity -- exactly as `DatasetShare` records the platform already works. Gating
reads here would contradict every other read path rather than extend one, so a
user restricted to 'view' on a dataflow still sees its output data in full.

The refusals that guard materialization are REUSED, not reimplemented: governed
sources are refused (a snapshot would freeze one person's row-security slice as
everyone's data) and export-blocked sources are refused (materializing writes a
downloadable copy, so treating it as anything but an export makes the control
bypassable). A dataflow must not become the way around either.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.capability import (effective_dataflow_capability,
                               require_dataflow_capability)
from ..core.database import get_db
from ..core.org_scope import check_org
from ..dependencies import get_current_user
from ..models.models import (Dataflow, DataflowCapability, Dataset,
                             DatasetColumn, User)
from ..services.audit import record as audit
from ..services.ingest import missing_pct
# A run writes a file per output; the same ceiling materialize already enforces.
from ..services.prep import MATERIALIZE_MAX_ROWS

router = APIRouter(prefix="/dataflows", tags=["dataflows"])


class DataflowIn(BaseModel):
    name: str
    description: str | None = None
    source_dataset_id: int
    steps: list[dict] = []
    refresh_interval_minutes: int | None = None


class DataflowPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    steps: list[dict] | None = None
    refresh_interval_minutes: int | None = None


class RunRequest(BaseModel):
    """A run either creates a new output or refreshes the existing ones.

    `output_name` creates; omitting it refreshes every output already produced,
    which is what a schedule does. Keeping both on one endpoint means the
    scheduled path and the manual path exercise identical code.
    """
    output_name: str | None = None


class CapabilityGrant(BaseModel):
    role_id: int
    level: str


class CapabilitiesIn(BaseModel):
    grants: list[CapabilityGrant]


async def _get_flow(db: AsyncSession, flow_id: int, user: User) -> Dataflow:
    flow = await db.get(Dataflow, flow_id)
    check_org(flow, user, "Dataflow not found")
    return flow


def _iso_z(dt: datetime | None) -> str | None:
    """`created_at`/`last_run_at` are DateTime(timezone=True) columns: a row
    freshly written in this request holds the naive `datetime.utcnow()` it was
    assigned, but one read back from Postgres comes back tz-aware, and its
    `.isoformat()` already ends in "+00:00" -- blindly appending "Z" then
    produces "...+00:00Z", which `new Date()` cannot parse (surfaced live as
    "NaNd ago" in Dataflows.tsx)."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return dt.isoformat() + "Z"


def _out(flow: Dataflow, outputs: list[dict] | None = None,
         capability: str | None = None) -> dict:
    return {
        "id": flow.id, "name": flow.name, "description": flow.description,
        "source_dataset_id": flow.source_dataset_id,
        "join_dataset_ids": flow.join_dataset_ids or [],
        "steps": flow.steps or [],
        "refresh_interval_minutes": flow.refresh_interval_minutes,
        "created_by": flow.created_by,
        "created_at": _iso_z(flow.created_at),
        "last_run_at": _iso_z(flow.last_run_at),
        "last_run_status": flow.last_run_status,
        "last_run_rows": flow.last_run_rows,
        "last_run_error": flow.last_run_error,
        "outputs": outputs if outputs is not None else [],
        "your_capability": capability,
    }


async def _outputs_of(db: AsyncSession, flow_id: int, org_id: int) -> list[Dataset]:
    """Datasets this dataflow produced.

    Outputs are not a join table: a produced dataset records `dataflow_id` in the
    `__derived_from__` JSON it already carries, so linking one needed no schema
    change and every derived dataset that predates dataflows keeps working with
    no dataflow_id at all.
    """
    from ..services.prep import derived_from_of

    rows = (await db.execute(
        select(Dataset).where(Dataset.org_id == org_id))).scalars().all()
    return [d for d in rows
            if (derived_from_of(d) or {}).get("dataflow_id") == flow_id]


@router.get("")
async def list_dataflows(db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
    """Every dataflow in the org. Listing is not gated -- see the module note on
    authoring-vs-reading -- but each row carries the caller's own capability so
    the UI can hide controls it would only be refused for."""
    flows = (await db.execute(
        select(Dataflow).where(Dataflow.org_id == current_user.org_id)
        .order_by(Dataflow.id.desc()))).scalars().all()
    out = []
    for f in flows:
        cap = await effective_dataflow_capability(db, current_user, f.id)
        out.append(_out(f, outputs=[{"id": d.id, "name": d.name,
                                     "row_count": d.row_count}
                                    for d in await _outputs_of(db, f.id, current_user.org_id)],
                        capability=cap))
    return out


@router.post("", status_code=201)
async def create_dataflow(req: DataflowIn, db: AsyncSession = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    """Create a dataflow from a source dataset and a recipe.

    Requires 'data' on the SOURCE, because a dataflow reads that dataset on every
    run: someone who may not author the source's data model must not be able to
    stand up a scheduled job that reads it.
    """
    from ..core.capability import require_dataset_capability
    from ..routers.datasets import _validated_join_columns
    from ..services.prep import (MAX_STEPS, collect_join_dataset_ids,
                                 validate_prep_steps)

    name = (req.name or "").strip()[:255]
    if not name:
        raise HTTPException(400, "name is required")

    src = await db.get(Dataset, req.source_dataset_id)
    check_org(src, current_user, "Dataset not found")
    await require_dataset_capability(db, current_user, req.source_dataset_id, "data")
    if src.mode == "directquery" or not src.filename:
        raise HTTPException(400, "Only import-mode datasets can feed a dataflow")

    steps = req.steps or []
    if not isinstance(steps, list) or len(steps) > MAX_STEPS:
        raise HTTPException(400, f"steps must be a list of at most {MAX_STEPS}")

    # Validated at CREATE, not only at run: a recipe that cannot run should fail
    # while its author is looking at it, not silently at 3am on a schedule.
    known = {r[0] for r in (await db.execute(
        select(DatasetColumn.name)
        .where(DatasetColumn.dataset_id == req.source_dataset_id))).all()}
    join_columns = await _validated_join_columns(db, current_user.org_id, steps)
    try:
        validate_prep_steps(steps, known, join_columns)
    except ValueError as e:
        raise HTTPException(400, str(e))

    flow = Dataflow(
        org_id=current_user.org_id, name=name, description=req.description or None,
        source_dataset_id=req.source_dataset_id, steps=steps,
        join_dataset_ids=sorted(set(collect_join_dataset_ids(steps))),
        refresh_interval_minutes=req.refresh_interval_minutes,
        created_by=current_user.id)
    db.add(flow)
    await db.flush()
    await audit(db, current_user, "dataflow.create", "dataflow", flow.id, name)
    await db.commit()
    await db.refresh(flow)
    return _out(flow, outputs=[], capability="data")


@router.get("/{flow_id}")
async def get_dataflow(flow_id: int, db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    flow = await _get_flow(db, flow_id, current_user)
    outputs = await _outputs_of(db, flow_id, current_user.org_id)
    return _out(flow,
                outputs=[{"id": d.id, "name": d.name, "row_count": d.row_count,
                          "last_refreshed_at": _iso_z(d.last_refreshed_at)}
                         for d in outputs],
                capability=await effective_dataflow_capability(db, current_user, flow_id))


@router.put("/{flow_id}")
async def update_dataflow(flow_id: int, req: DataflowPatch,
                          db: AsyncSession = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    """Edit the recipe, name or schedule. Needs 'edit'."""
    from ..routers.datasets import _validated_join_columns
    from ..services.prep import (MAX_STEPS, collect_join_dataset_ids,
                                 validate_prep_steps)
    from ..services.refresh_scheduler import MIN_INTERVAL_MINUTES

    flow = await _get_flow(db, flow_id, current_user)
    await require_dataflow_capability(db, current_user, flow_id, "edit")

    if req.name is not None:
        name = req.name.strip()[:255]
        if not name:
            raise HTTPException(400, "name cannot be empty")
        flow.name = name
    if req.description is not None:
        flow.description = req.description or None

    if req.steps is not None:
        if not isinstance(req.steps, list) or len(req.steps) > MAX_STEPS:
            raise HTTPException(400, f"steps must be a list of at most {MAX_STEPS}")
        known = {r[0] for r in (await db.execute(
            select(DatasetColumn.name)
            .where(DatasetColumn.dataset_id == flow.source_dataset_id))).all()}
        join_columns = await _validated_join_columns(db, current_user.org_id, req.steps)
        try:
            validate_prep_steps(req.steps, known, join_columns)
        except ValueError as e:
            raise HTTPException(400, str(e))
        flow.steps = req.steps
        flow.join_dataset_ids = sorted(set(collect_join_dataset_ids(req.steps)))

    if req.refresh_interval_minutes is not None:
        if req.refresh_interval_minutes and req.refresh_interval_minutes < MIN_INTERVAL_MINUTES:
            raise HTTPException(400, f"Minimum refresh interval is {MIN_INTERVAL_MINUTES} minutes")
        flow.refresh_interval_minutes = req.refresh_interval_minutes or None

    await audit(db, current_user, "dataflow.update", "dataflow", flow.id, flow.name)
    await db.commit()
    await db.refresh(flow)
    return _out(flow, capability=await effective_dataflow_capability(db, current_user, flow_id))


@router.delete("/{flow_id}", status_code=204)
async def delete_dataflow(flow_id: int, db: AsyncSession = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    """Delete the dataflow. Needs 'data'.

    Outputs are deliberately LEFT IN PLACE. They are ordinary datasets that
    reports may already point at, and deleting a recipe is not a statement about
    the data it produced -- silently removing those would turn a tidy-up into
    data loss. They simply stop being refreshed.
    """
    flow = await _get_flow(db, flow_id, current_user)
    await require_dataflow_capability(db, current_user, flow_id, "data")
    name = flow.name
    await db.delete(flow)
    await audit(db, current_user, "dataflow.delete", "dataflow", flow_id, name)
    await db.commit()


@router.post("/{flow_id}/run")
async def run_dataflow(flow_id: int, req: RunRequest,
                       db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    """Run the recipe. Needs 'edit'.

    With `output_name`, creates a new output dataset. Without it, refreshes every
    existing output in place -- which is what the scheduler calls, so both paths
    run identical code rather than drifting apart.
    """
    from ..routers.datasets import (_build_frame, _refuse_if_ungovernable,
                                    _write_frame_as_dataset_file)
    from ..services.prep import DERIVED_FROM_KEY

    flow = await _get_flow(db, flow_id, current_user)
    await require_dataflow_capability(db, current_user, flow_id, "edit")

    src = await db.get(Dataset, flow.source_dataset_id) if flow.source_dataset_id else None
    if src is None or src.org_id != current_user.org_id or not src.filename:
        raise HTTPException(409, "This dataflow's source dataset no longer exists")

    steps = flow.steps or []
    # Re-run EVERY refusal on each run, not only at create: rules may have been
    # added since, and a run that ignored them would launder newly-governed data.
    inherited = await _refuse_if_ungovernable(
        db, [flow.source_dataset_id] + list(flow.join_dataset_ids or []))

    try:
        out = await _build_frame(db, current_user, src, steps)
    except FileNotFoundError:
        raise HTTPException(404, "Source dataset file not found on server")

    if len(out) > MATERIALIZE_MAX_ROWS:
        raise HTTPException(400, f"Result has {len(out):,} rows, above the "
                                 f"{MATERIALIZE_MAX_ROWS:,} limit for a saved dataset")

    now = datetime.utcnow()
    made: list[Dataset] = []

    def _provenance() -> dict:
        return {
            "dataflow_id": flow.id,
            "source_dataset_id": flow.source_dataset_id,
            "join_dataset_ids": sorted(set(flow.join_dataset_ids or [])),
            "steps": steps,
            # The dataflow's creator, not the caller: a scheduled run has nobody
            # at the keyboard, and this is the identity it resolves RLS as.
            "built_by_user_id": flow.created_by or current_user.id,
            "built_at": now.isoformat() + "Z",
            "built_rows": int(len(out)),
            "recipe_version": 1,
        }

    if req.output_name:
        path, size, type_map = await _write_frame_as_dataset_file(
            db, current_user.org_id, out)
        new = Dataset(
            name=req.output_name.strip()[:255], filename=str(path),
            row_count=len(out), col_count=len(out.columns), file_size=size,
            org_id=current_user.org_id, mode="import", last_refreshed_at=now,
            column_meta={**inherited, DERIVED_FROM_KEY: _provenance()})
        db.add(new)
        await db.flush()
        for col_name, dtype in type_map.items():
            db.add(DatasetColumn(
                dataset_id=new.id, name=col_name, dtype=dtype,
                missing_pct=missing_pct(out[col_name]), stats={}))
        made.append(new)
    else:
        import asyncio

        from sqlalchemy.orm.attributes import flag_modified

        from ..services.frame_cache import write_parquet_sidecar
        from ..services.ingest import detect_types

        outputs = await _outputs_of(db, flow_id, current_user.org_id)
        if not outputs:
            raise HTTPException(400, "This dataflow has no outputs yet — name one to create it")
        type_map = await asyncio.to_thread(detect_types, out)
        for ds in outputs:
            # Written in place so every report pointing at the output picks the
            # new rows up with no rewiring.
            await asyncio.to_thread(lambda p=ds.filename: out.to_csv(p, index=False))
            await asyncio.to_thread(write_parquet_sidecar, str(ds.filename))
            ds.row_count, ds.col_count = len(out), len(out.columns)
            ds.last_refreshed_at = now
            meta = dict(ds.column_meta or {})
            meta[DERIVED_FROM_KEY] = _provenance()
            ds.column_meta = meta
            flag_modified(ds, "column_meta")
            for c in (await db.execute(select(DatasetColumn).where(
                    DatasetColumn.dataset_id == ds.id))).scalars().all():
                await db.delete(c)
            await db.flush()
            for col_name, dtype in type_map.items():
                db.add(DatasetColumn(
                    dataset_id=ds.id, name=col_name, dtype=dtype,
                    missing_pct=missing_pct(out[col_name]), stats={}))
            made.append(ds)

    flow.last_run_at = now
    flow.last_run_status = "ok"
    flow.last_run_rows = int(len(out))
    flow.last_run_error = None
    await audit(db, current_user, "dataflow.run", "dataflow", flow.id,
                f"{len(out)} rows into {len(made)} output(s)")
    await db.commit()
    return {"rows": int(len(out)),
            "outputs": [{"id": d.id, "name": d.name} for d in made]}


@router.get("/{flow_id}/capabilities")
async def get_capabilities(flow_id: int, db: AsyncSession = Depends(get_db),
                           current_user: User = Depends(get_current_user)):
    """Current grants. Readable by anyone in the org who can see the dataflow --
    knowing who may edit something is not itself sensitive, and hiding it makes
    "why was I refused?" unanswerable without an admin."""
    await _get_flow(db, flow_id, current_user)
    rows = (await db.execute(
        select(DataflowCapability).where(
            DataflowCapability.dataflow_id == flow_id))).scalars().all()
    return {"grants": [{"role_id": r.role_id, "level": r.level} for r in rows],
            "your_capability": await effective_dataflow_capability(
                db, current_user, flow_id)}


@router.put("/{flow_id}/capabilities")
async def set_capabilities(flow_id: int, req: CapabilitiesIn,
                           db: AsyncSession = Depends(get_db),
                           current_user: User = Depends(get_current_user)):
    """Replace the grants. Needs 'data'.

    Sending an empty list clears every grant, which returns the dataflow to
    ungoverned -- full access for every role. That is the documented default, not
    a lockout, and it is the only way back once grants exist.
    """
    from ..core.capability import LEVELS

    await _get_flow(db, flow_id, current_user)
    await require_dataflow_capability(db, current_user, flow_id, "data")

    for g in req.grants:
        if g.level not in LEVELS:
            raise HTTPException(400, f"level must be one of {', '.join(LEVELS)}")

    for row in (await db.execute(select(DataflowCapability).where(
            DataflowCapability.dataflow_id == flow_id))).scalars().all():
        await db.delete(row)
    await db.flush()
    seen: set[int] = set()
    for g in req.grants:
        if g.role_id in seen:
            continue
        seen.add(g.role_id)
        db.add(DataflowCapability(dataflow_id=flow_id, role_id=g.role_id,
                                  level=g.level))
    await audit(db, current_user, "dataflow.capabilities", "dataflow", flow_id,
                f"{len(seen)} grant(s)")
    await db.commit()
    return {"grants": [{"role_id": g.role_id, "level": g.level}
                       for g in req.grants if g.role_id in seen]}
