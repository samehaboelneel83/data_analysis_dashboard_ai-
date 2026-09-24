from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..core.database import get_db
from ..core.org_scope import check_org
from ..dependencies import get_current_user
from ..models.models import Dataset, DatasetColumn, Relationship, User
from ..schemas.schemas import RelationshipCreate, RelationshipOut

router = APIRouter(prefix="/relationships", tags=["relationships"])


async def _check_column_exists(db: AsyncSession, dataset_id: int, column: str) -> None:
    result = await db.execute(
        select(DatasetColumn).where(DatasetColumn.dataset_id == dataset_id, DatasetColumn.name == column)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(400, f"Column '{column}' does not exist on dataset {dataset_id}")


@router.get("", response_model=list[RelationshipOut])
async def list_relationships(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(Relationship).where(Relationship.org_id == current_user.org_id))
    return result.scalars().all()


@router.post("", response_model=RelationshipOut)
async def create_relationship(body: RelationshipCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    from_ds = await db.get(Dataset, body.from_dataset_id)
    check_org(from_ds, current_user, "Dataset not found")
    to_ds = await db.get(Dataset, body.to_dataset_id)
    check_org(to_ds, current_user, "Dataset not found")

    await _check_column_exists(db, body.from_dataset_id, body.from_column)
    await _check_column_exists(db, body.to_dataset_id, body.to_column)

    rel = Relationship(
        org_id=current_user.org_id, from_dataset_id=body.from_dataset_id, from_column=body.from_column,
        to_dataset_id=body.to_dataset_id, to_column=body.to_column,
    )
    db.add(rel)
    await db.commit()
    await db.refresh(rel)
    return rel


@router.post("/check")
async def check_relationship(body: dict, db: AsyncSession = Depends(get_db),
                             current_user: User = Depends(get_current_user)):
    """How a candidate mapping will carry a filter, before it is saved: the share
    of the source column's values that exist in the target column, the ones that
    do not, and near-misses (case/spacing). Both sides are read AS THE CALLER --
    RLS, column security and each dataset's own prep -- so the check can never
    reveal values the caller could not see by opening either dataset."""
    import asyncio

    from ..services.prep import mapping_match_report, resolve_join_frames
    try:
        fid, tid = int(body.get("from_dataset_id")), int(body.get("to_dataset_id"))
    except (TypeError, ValueError):
        raise HTTPException(400, "from_dataset_id and to_dataset_id are required")
    fcol, tcol = str(body.get("from_column") or ""), str(body.get("to_column") or "")
    if not fcol or not tcol:
        raise HTTPException(400, "Both columns are required")
    for did in (fid, tid):
        check_org(await db.get(Dataset, did), current_user, "Dataset not found")
    frames = await resolve_join_frames(db, current_user, [{"kind": "join", "dataset_id": fid},
                                                          {"kind": "join", "dataset_id": tid}])
    left, right = frames.get(fid), frames.get(tid)
    if left is None or right is None:
        raise HTTPException(400, "Match checks read import-mode datasets you can open; one side is not available")
    for frame, col in ((left, fcol), (right, tcol)):
        if col not in frame.columns:
            raise HTTPException(400, f"Column '{col}' is not available to you on that dataset")
    return await asyncio.to_thread(mapping_match_report, left[fcol], right[tcol])


@router.delete("/{relationship_id}", status_code=204)
async def delete_relationship(relationship_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    rel = await db.get(Relationship, relationship_id)
    check_org(rel, current_user, "Relationship not found")
    await db.delete(rel)
    await db.commit()
