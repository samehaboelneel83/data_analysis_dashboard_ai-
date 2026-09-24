import asyncio
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from ..core.database import get_db
from ..core.org_scope import check_org
from ..dependencies import get_current_user
from ..models.models import Dataset, DatasetColumn, HierarchyNode, User
from ..schemas.schemas import HierarchyNodeCreate, HierarchyNodeUpdate, HierarchyNodeOut
from ..services.analytics import load_file, detect_types

router = APIRouter(prefix="/datasets", tags=["hierarchy"])

DATE_DRILL_LEVELS = [("Year", "year"), ("Quarter", "quarter"), ("Month", "month"), ("Day", "day")]


async def _get_dataset(dataset_id: int, db: AsyncSession, current_user: User) -> Dataset:
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    return ds


@router.get("/{dataset_id}/hierarchy", response_model=list[HierarchyNodeOut])
async def get_hierarchy(dataset_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    await _get_dataset(dataset_id, db, current_user)
    r = await db.execute(
        select(HierarchyNode).where(HierarchyNode.dataset_id == dataset_id).order_by(HierarchyNode.position)
    )
    return r.scalars().all()


@router.post("/{dataset_id}/hierarchy", response_model=HierarchyNodeOut, status_code=201)
async def create_node(dataset_id: int, body: HierarchyNodeCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    await _get_dataset(dataset_id, db, current_user)
    node = HierarchyNode(dataset_id=dataset_id, **body.model_dump())
    db.add(node)
    await db.commit()
    await db.refresh(node)
    return node


@router.patch("/{dataset_id}/hierarchy/{node_id}", response_model=HierarchyNodeOut)
async def update_node(dataset_id: int, node_id: int, body: HierarchyNodeUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    await _get_dataset(dataset_id, db, current_user)
    r = await db.execute(select(HierarchyNode).where(HierarchyNode.id == node_id, HierarchyNode.dataset_id == dataset_id))
    node = r.scalar_one_or_none()
    if not node:
        raise HTTPException(404, "Node not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(node, k, v)
    await db.commit()
    await db.refresh(node)
    return node


@router.delete("/{dataset_id}/hierarchy/{node_id}", status_code=204)
async def delete_node(dataset_id: int, node_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    await _get_dataset(dataset_id, db, current_user)
    r = await db.execute(select(HierarchyNode).where(HierarchyNode.id == node_id, HierarchyNode.dataset_id == dataset_id))
    node = r.scalar_one_or_none()
    if not node:
        raise HTTPException(404, "Node not found")
    # Removing a node HEALS the chain: its children re-parent to its parent, so
    # deleting Quarter from Year->Quarter->Month->Day leaves Year->Month->Day.
    # Without this, the parent_id CASCADE silently destroyed every level beneath
    # the deleted one -- removing one level of a date hierarchy took the rest
    # of the hierarchy with it.
    children = (await db.execute(
        select(HierarchyNode).where(HierarchyNode.parent_id == node.id)
    )).scalars().all()
    for child in children:
        child.parent_id = node.parent_id
    await db.flush()
    await db.delete(node)
    await db.commit()


@router.post("/{dataset_id}/hierarchy/auto-generate", response_model=list[HierarchyNodeOut])
async def auto_generate(dataset_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    ds = await _get_dataset(dataset_id, db, current_user)

    if ds.mode == "directquery":
        # No file to load -- DatasetColumn already carries the dtype detected
        # from the schema probe at dataset-creation time (see data_sources.py's
        # /import endpoint's directquery branch).
        cols_result = await db.execute(select(DatasetColumn).where(DatasetColumn.dataset_id == dataset_id))
        type_map = {c.name: c.dtype for c in cols_result.scalars().all()}
    else:
        if not ds.filename:
            raise HTTPException(404, "Dataset not found or no file")
        try:
            df       = await asyncio.to_thread(load_file, ds.filename)
            type_map = await asyncio.to_thread(detect_types, df)
        except FileNotFoundError:
            raise HTTPException(404, "Dataset file not found on server — please re-upload the file")

    await db.execute(delete(HierarchyNode).where(HierarchyNode.dataset_id == dataset_id))

    folder_info = [
        ("Dimensions", "categorical", "dimension"),
        ("Measures",   "numeric",     "measure"),
        ("Dates",      "datetime",    "date"),
        ("Text",       "text",        "text"),
    ]
    folder_ids: dict[str, int] = {}
    for pos, (fname, fkey, _) in enumerate(folder_info):
        folder = HierarchyNode(dataset_id=dataset_id, name=fname, node_type="folder", position=pos)
        db.add(folder)
        await db.flush()
        folder_ids[fkey] = folder.id

    counters: dict[str, int] = {k: 0 for k in folder_ids}
    for col_name, col_type in type_map.items():
        if col_type not in folder_ids:
            continue
        _, _, ntype = next(x for x in folder_info if x[1] == col_type)
        node = HierarchyNode(
            dataset_id=dataset_id,
            parent_id=folder_ids[col_type],
            name=col_name,
            node_type=ntype,
            column_name=col_name,
            aggregation="sum" if col_type == "numeric" else None,
            position=counters[col_type],
        )
        db.add(node)
        counters[col_type] += 1

        if col_type == "datetime":
            # Linear Year -> Quarter -> Month -> Day drill chain under this date
            # column's node. Every level shares the same underlying column_name
            # (none has its own physical column) -- `format` is what
            # distinguishes granularity. No aggregation: these are drill/grouping
            # levels, not measures.
            await db.flush()  # assign node.id so it can be used as parent_id below
            parent_id = node.id
            for pos, (label, granularity) in enumerate(DATE_DRILL_LEVELS):
                level_node = HierarchyNode(
                    dataset_id=dataset_id, parent_id=parent_id, name=label,
                    node_type="date", column_name=col_name, aggregation=None,
                    format=granularity, position=pos,
                )
                db.add(level_node)
                await db.flush()
                parent_id = level_node.id

    await db.commit()
    r = await db.execute(
        select(HierarchyNode).where(HierarchyNode.dataset_id == dataset_id).order_by(HierarchyNode.position)
    )
    return r.scalars().all()
