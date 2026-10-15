"""Glossary terms of ONE dataset (B-21).

The glossary worked per connection only (routers/metadata.py): an uploaded
dataset had nowhere to put "Revenue means `amount`", and the dataset's
Columns tab could not show or add the term a column stands for. A term made
here has `dataset_id` set: it is listed and given to the AI only with this
dataset, and only to a reader who may open the dataset; a term naming a
column the reader's role is denied is left out (services/knowledge).

Writes are org-admin only, like every glossary write: a term steers the
queries the AI writes for everyone who asks with that word.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.capability import require_dataset_read
from ..core.database import get_db
from ..core.org_scope import check_org
from ..core.rls import resolve_denied_columns
from ..dependencies import get_current_user, require_org_admin
from ..models.models import Dataset, DatasetColumn, GlossaryTerm, User
from ..services import knowledge
from .metadata import GlossaryIn, GlossaryPatch, _glossary_payload

router = APIRouter(prefix="/datasets", tags=["glossary"])


async def _readable(db: AsyncSession, user: User, dataset_id: int) -> Dataset:
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, user, "Dataset not found")
    await require_dataset_read(db, user, dataset_id)
    return ds


async def _columns(db: AsyncSession, ds: Dataset) -> set[str]:
    stored = (await db.execute(select(DatasetColumn.name).where(DatasetColumn.dataset_id == ds.id))).scalars().all()
    calc = [c.get("name") for c in (ds.calculated_columns or []) if isinstance(c, dict) and c.get("name")]
    return {str(c) for c in list(stored) + calc}


async def _own_term(db: AsyncSession, user: User, ds: Dataset, term_id: int) -> GlossaryTerm:
    term = await db.get(GlossaryTerm, term_id)
    check_org(term, user, "Glossary term not found")
    # Only this dataset's own terms: an org-wide or a connection's term is
    # edited where it lives, another dataset's not at all from here.
    if term.dataset_id != ds.id:
        raise HTTPException(404, "Glossary term not found")
    return term


@router.get("/{dataset_id}/glossary")
async def list_dataset_glossary(dataset_id: int, db: AsyncSession = Depends(get_db),
                                current_user: User = Depends(get_current_user)):
    """The terms that apply to this dataset for this reader: org-wide, its
    connection's and its own -- without those naming a column denied to them."""
    ds = await _readable(db, current_user, dataset_id)
    denied = set(await resolve_denied_columns(db, current_user, ds.id))
    return [_glossary_payload(t) for t in await knowledge.glossary_terms_for(db, ds, denied=denied)]


@router.post("/{dataset_id}/glossary")
async def create_dataset_term(dataset_id: int, body: GlossaryIn, db: AsyncSession = Depends(get_db),
                              current_user: User = Depends(require_org_admin)):
    ds = await _readable(db, current_user, dataset_id)
    term = body.term.strip()
    if not term:
        raise HTTPException(422, "term must not be empty")
    if not all(isinstance(s, str) and s.strip() for s in body.synonyms or []):
        raise HTTPException(422, "synonyms must be a list of non-empty strings")
    column = (body.maps_to_column or "").strip() or None
    if column and column not in await _columns(db, ds):
        raise HTTPException(422, f"'{column}' is not a column of this dataset")
    row = GlossaryTerm(org_id=current_user.org_id, data_source_id=None, dataset_id=ds.id, term=term,
                       definition=(body.definition or "").strip() or None,
                       synonyms=[s.strip() for s in body.synonyms or []],
                       maps_to_object=None, maps_to_column=column,
                       rule=(body.rule or "").strip() or None, always=bool(body.always))
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _glossary_payload(row)


@router.patch("/{dataset_id}/glossary/{term_id}")
async def update_dataset_term(dataset_id: int, term_id: int, body: GlossaryPatch,
                              db: AsyncSession = Depends(get_db),
                              current_user: User = Depends(require_org_admin)):
    ds = await _readable(db, current_user, dataset_id)
    term = await _own_term(db, current_user, ds, term_id)
    data = body.model_dump(exclude_unset=True)
    if "definition" in data:
        term.definition = (data["definition"] or "").strip() or None
    if data.get("synonyms") is not None:
        term.synonyms = [s.strip() for s in data["synonyms"] if s and s.strip()]
    if "rule" in data:
        term.rule = (data["rule"] or "").strip() or None
    if data.get("always") is not None:
        term.always = bool(data["always"])
    await db.commit()
    await db.refresh(term)
    return _glossary_payload(term)


@router.delete("/{dataset_id}/glossary/{term_id}", status_code=204)
async def delete_dataset_term(dataset_id: int, term_id: int, db: AsyncSession = Depends(get_db),
                              current_user: User = Depends(require_org_admin)):
    ds = await _readable(db, current_user, dataset_id)
    term = await _own_term(db, current_user, ds, term_id)
    await db.delete(term)
    await db.commit()
