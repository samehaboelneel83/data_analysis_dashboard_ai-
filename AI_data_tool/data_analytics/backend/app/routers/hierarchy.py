import asyncio
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from ..core.database import get_db
from ..core.capability import require_dataset_capability, require_dataset_read
from ..core.org_scope import check_org
from ..dependencies import get_current_user
from ..models.models import Dataset, DatasetColumn, HierarchyNode, User
from ..schemas.schemas import HierarchyNodeCreate, HierarchyNodeUpdate, HierarchyNodeOut
from ..services.analytics import load_file, detect_types
from ..services.ingest import is_time_only

router = APIRouter(prefix="/datasets", tags=["hierarchy"])

#: The default drill chain under every date column, as SAS's: year > quarter >
#: month > week > the date itself. `format` is the grain each level groups by.
DATE_DRILL_LEVELS = [("Year", "year"), ("Quarter", "quarter"), ("Month", "month"),
                     ("Week", "week"), ("Date", "day")]
#: A time-of-day column's one level.
TIME_DRILL_LEVELS = [("Hour of day", "hour_of_day")]

#: The default geography chain, outermost first: each level is the first
#: column whose name matches one of its spellings. Built when two or more
#: levels are present (Continent > Country > City; a "region" column stands in
#: for a continent in data that groups countries that way).
GEO_DRILL_LEVELS = [
    ("Continent", ("continent", "continentname", "region", "regionname")),
    ("Country", ("country", "countryname", "nation", "countrycode")),
    ("State", ("state", "statename", "province", "governorate", "county")),
    ("City", ("city", "cityname", "town")),
]


def _norm(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


def geography_chain(columns: list[str]) -> list[tuple[str, str]]:
    """(level label, column) for each default geography level these columns have."""
    by_norm = {}
    for c in columns:
        by_norm.setdefault(_norm(c), c)
    chain = []
    used: set[str] = set()
    for label, spellings in GEO_DRILL_LEVELS:
        col = next((by_norm[s] for s in spellings if s in by_norm and by_norm[s] not in used), None)
        if col:
            chain.append((label, col))
            used.add(col)
    return chain if len(chain) >= 2 else []


async def _get_dataset(dataset_id: int, db: AsyncSession, current_user: User,
                       *, write: bool = False) -> Dataset:
    """Reading the tree needs read access to the dataset; changing it is
    authoring, which needs the same capability as the rest of the model."""
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, current_user, "Dataset not found")
    if write:
        await require_dataset_capability(db, current_user, dataset_id, "data")
    else:
        await require_dataset_read(db, current_user, dataset_id)
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
    await _get_dataset(dataset_id, db, current_user, write=True)
    node = HierarchyNode(dataset_id=dataset_id, **body.model_dump())
    db.add(node)
    await db.commit()
    await db.refresh(node)
    return node


@router.patch("/{dataset_id}/hierarchy/{node_id}", response_model=HierarchyNodeOut)
async def update_node(dataset_id: int, node_id: int, body: HierarchyNodeUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    await _get_dataset(dataset_id, db, current_user, write=True)
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
    await _get_dataset(dataset_id, db, current_user, write=True)
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
    ds = await _get_dataset(dataset_id, db, current_user, write=True)

    if ds.mode == "directquery":
        # No file to load -- DatasetColumn already carries the dtype detected
        # from the schema probe at dataset-creation time (see data_sources.py's
        # /import endpoint's directquery branch).
        cols_result = await db.execute(select(DatasetColumn).where(DatasetColumn.dataset_id == dataset_id))
        _cols = cols_result.scalars().all()
        type_map = {c.name: c.dtype for c in _cols}
        time_only = {c.name for c in _cols if c.semantic_type == "time_of_day"}
    else:
        if not ds.filename:
            raise HTTPException(404, "Dataset not found or no file")
        try:
            df       = await asyncio.to_thread(load_file, ds.filename)
            type_map = await asyncio.to_thread(detect_types, df)
            time_only = {c for c, t in type_map.items() if t == "datetime" and is_time_only(df[c])}
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
            # A clock time with no date drills by hour of day; a year or a
            # quarter of it would be the day the file was read.
            levels = TIME_DRILL_LEVELS if col_name in time_only else DATE_DRILL_LEVELS
            for pos, (label, granularity) in enumerate(levels):
                level_node = HierarchyNode(
                    dataset_id=dataset_id, parent_id=parent_id, name=label,
                    node_type="date", column_name=col_name, aggregation=None,
                    format=granularity, position=pos,
                )
                db.add(level_node)
                await db.flush()
                parent_id = level_node.id

    # Geography: one chain of the place columns this data has.
    chain = geography_chain(list(type_map))
    if chain:
        folder = HierarchyNode(dataset_id=dataset_id, name="Geography", node_type="folder",
                               position=len(folder_info))
        db.add(folder)
        await db.flush()
        parent_id = folder.id
        for pos, (label, col) in enumerate(chain):
            level = HierarchyNode(dataset_id=dataset_id, parent_id=parent_id, name=label,
                                  node_type="dimension", column_name=col, position=pos)
            db.add(level)
            await db.flush()
            parent_id = level.id

    await db.commit()
    r = await db.execute(
        select(HierarchyNode).where(HierarchyNode.dataset_id == dataset_id).order_by(HierarchyNode.position)
    )
    return r.scalars().all()


@router.put("/{dataset_id}/hierarchy/order", response_model=list[HierarchyNodeOut])
async def reorder_chain(dataset_id: int, body: dict, db: AsyncSession = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    """Put a drill chain's levels in a new order: `{"ids": [...]}`, outermost
    first -- the order the author dragged them into. The ids must be exactly
    one chain as it stands (each level the parent of the next), so nothing
    outside it moves; the chain keeps its place under its parent, and
    anything hanging below its old last level hangs below its new one."""
    await _get_dataset(dataset_id, db, current_user, write=True)
    ids = body.get("ids") if isinstance(body, dict) else None
    if not isinstance(ids, list) or len(ids) < 2 or not all(isinstance(i, int) for i in ids) or len(set(ids)) != len(ids):
        raise HTTPException(400, "ids must list two or more distinct levels")
    rows = (await db.execute(select(HierarchyNode).where(HierarchyNode.dataset_id == dataset_id))).scalars().all()
    by_id = {n.id: n for n in rows}
    if any(i not in by_id for i in ids):
        raise HTTPException(404, "Level not found")
    wanted = set(ids)
    # The chain as it stands: one level whose parent is outside, then each
    # level's single child inside the set.
    tops = [by_id[i] for i in ids if by_id[i].parent_id not in wanted]
    if len(tops) != 1:
        raise HTTPException(400, "These levels are not one drill chain")
    current = [tops[0]]
    while True:
        kids = [n for n in rows if n.parent_id == current[-1].id and n.id in wanted]
        if not kids:
            break
        if len(kids) > 1:
            raise HTTPException(400, "These levels are not one drill chain")
        current.append(kids[0])
    if len(current) != len(ids):
        raise HTTPException(400, "These levels are not one drill chain")
    outside_parent = tops[0].parent_id
    below = [n for n in rows if n.parent_id == current[-1].id and n.id not in wanted]
    # Detach first, so no level is ever its own ancestor mid-way.
    for n in current:
        n.parent_id = None
    await db.flush()
    prev = outside_parent
    for pos, i in enumerate(ids):
        by_id[i].parent_id = prev
        by_id[i].position = pos if prev == outside_parent else 0
        prev = i
    for n in below:
        n.parent_id = ids[-1]
    await db.commit()
    r = await db.execute(
        select(HierarchyNode).where(HierarchyNode.dataset_id == dataset_id).order_by(HierarchyNode.position)
    )
    return r.scalars().all()
