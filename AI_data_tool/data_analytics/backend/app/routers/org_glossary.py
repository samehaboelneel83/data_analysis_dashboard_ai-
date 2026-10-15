"""Org-wide glossary terms (B-21 step 1).

A term with no connection and no dataset means the same thing everywhere in
the org ("GMV"): the AI already read such terms for every connection
(agent/context.load_context) and every dataset (knowledge.glossary_terms_for),
but nothing could create one -- the only writes were a connection's
(routers/metadata.py) and one dataset's (routers/dataset_glossary.py).

Same fields, validation and permission rule as a connection's terms: writes
are org-admin only (a term steers the queries the AI writes for everyone who
asks with that word), reads are open to every member of the org. These routes
touch org-wide terms only; a connection's or a dataset's term is 404 here,
and is edited where it lives.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.org_scope import check_org
from ..dependencies import get_current_user, require_org_admin
from ..models.models import GlossaryTerm, User
from .metadata import (GlossaryIn, GlossaryPatch, _glossary_payload,
                       apply_glossary_patch, new_glossary_term)

router = APIRouter(prefix="/glossary", tags=["glossary"])


def _org_wide():
    return (GlossaryTerm.data_source_id.is_(None), GlossaryTerm.dataset_id.is_(None))


async def _org_wide_term(db: AsyncSession, user: User, term_id: int) -> GlossaryTerm:
    term = await db.get(GlossaryTerm, term_id)
    check_org(term, user, "Glossary term not found")
    if term.data_source_id is not None or term.dataset_id is not None:
        raise HTTPException(404, "Glossary term not found")
    return term


async def _forget_answers(db: AsyncSession, org_id: int) -> None:
    # An org-wide rule changes what earlier answers on EVERY connection should
    # have been -- the connection routes forget one source's, this the org's.
    from ..services.agent import memory
    await memory.forget(db, org_id)


@router.get("")
async def list_org_glossary(db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(get_current_user)):
    rows = (await db.execute(
        select(GlossaryTerm).where(GlossaryTerm.org_id == current_user.org_id, *_org_wide())
        .order_by(GlossaryTerm.term))).scalars().all()
    return [_glossary_payload(t) for t in rows]


@router.post("")
async def create_org_term(body: GlossaryIn, db: AsyncSession = Depends(get_db),
                          current_user: User = Depends(require_org_admin)):
    row = new_glossary_term(body, org_id=current_user.org_id, data_source_id=None)
    db.add(row)
    if row.rule:
        await _forget_answers(db, current_user.org_id)
    await db.commit()
    await db.refresh(row)
    return _glossary_payload(row)


@router.patch("/{term_id}")
async def update_org_term(term_id: int, body: GlossaryPatch, db: AsyncSession = Depends(get_db),
                          current_user: User = Depends(require_org_admin)):
    term = await _org_wide_term(db, current_user, term_id)
    if apply_glossary_patch(term, body):
        await _forget_answers(db, current_user.org_id)
    await db.commit()
    await db.refresh(term)
    return _glossary_payload(term)


@router.delete("/{term_id}", status_code=204)
async def delete_org_term(term_id: int, db: AsyncSession = Depends(get_db),
                          current_user: User = Depends(require_org_admin)):
    term = await _org_wide_term(db, current_user, term_id)
    await db.delete(term)
    await db.commit()
