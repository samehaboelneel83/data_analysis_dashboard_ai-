"""The chat surface's API. The pane lives inside the report builder (user's
choice, session of 2026-08-24); v1 answers INLINE — the request waits for
the run — because streaming adds a transport decision that changes nothing
about correctness. The run record makes any later streaming retrofit purely
additive.
"""
from __future__ import annotations

import asyncio
import io

import sqlglot
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlglot import exp

from ..core.capability import require_dataset_read
from ..core.database import get_db
from ..core.org_scope import check_org
from .data_sources import _visible_source_ids
from ..dependencies import get_current_user, require_org_admin
from ..models.models import (AgentFeedback, AgentMessage, AgentRun, AgentStep,
                             Conversation, Dataset, DataSource,
                             ObjectRowPolicy, Role, SourceObject, User)
from ..services import llm as llm_service
from ..services import quotas
from ..services.agent.export import build_result_pdf, build_result_xlsx
from ..services.agent.graph import run_agent
from ..services.agent.validate import _dialect

router = APIRouter(prefix="/agent", tags=["agent"])


def _reject_directquery(ds: Dataset) -> None:
    """Dataset mode answers out of a file frame, so a dataset whose rows live
    in a connection has nothing to load -- `run_agent`'s dataset_frames used
    to hand its NULL filename straight to abspath() and raise.

    The same picker already offers the connection, and source mode is the
    DirectQuery path, so the refusal points at it rather than just saying no.
    Called on BOTH the create and the ask path: conversations stored before
    this guard existed are still bound to these datasets."""
    if ds.mode == "directquery" or not ds.filename:
        raise HTTPException(
            400,
            f"'{ds.name}' is a DirectQuery dataset, which Ask AI cannot read "
            "as a table. Pick its connection instead to ask about live data.")


class ConversationIn(BaseModel):
    data_source_id: int | None = None
    dataset_ids: list[int] | None = None
    title: str | None = None


class AskIn(BaseModel):
    question: str


class RowPolicyIn(BaseModel):
    source_object_id: int
    role_id: int
    predicate: str


class FeedbackIn(BaseModel):
    run_id: int | None = None
    rating: str
    comment: str | None = None


class TitleIn(BaseModel):
    title: str


#: Earlier turns handed to the agent with a new question -- enough for "the
#: same for Cairo" or "as a table" to resolve against, small enough that a
#: long chat does not grow every prompt without bound.
HISTORY_TURNS = 6

#: A conversation created without a title takes its first question as one;
#: longer than this and a sidebar entry stops reading as a title.
TITLE_MAX = 80
DEFAULT_TITLE = "New conversation"


async def _owned_conversation(db: AsyncSession, cid: int, user: User) -> Conversation:
    """Owner-only, 404 otherwise -- the rule every conversation route shares.
    Same-org is not enough: AgentStep.sql carries the asker's RLS-filtered
    SQL, so an org-mate must not even learn the thread exists."""
    conv = await db.get(Conversation, cid)
    check_org(conv, user, "Conversation not found")
    if conv.user_id != user.id:
        raise HTTPException(404, "Conversation not found")
    return conv


def _run_payload(run: AgentRun, steps: list[AgentStep]) -> dict:
    """What the chat needs from a run beside its answer: the sink steps'
    result snapshots, their SQL, and the run-level metadata. A run with no
    snapshot (failed, or older than migration 0017) still lists whatever
    SQL it ran, so "Show SQL" keeps working on it."""
    sinks = [s for s in steps if s.result_rows is not None]
    sql_steps = sinks or [s for s in steps if s.sql]
    # `source` says where a result's rows came FROM. Everything a query
    # returned is "query"; the catalog listing behind a "describe this data"
    # answer is "catalog" -- real metadata, but not query output, and rows
    # with no SQL behind them are exactly the shape a fabricated answer has.
    # The chat captions it so nobody has to wonder which they are reading.
    return {"results": [{"step": s.node,
                         "source": "catalog" if s.node == "catalog" else "query",
                         **s.result_rows} for s in sinks],
            "sql": [s.sql for s in sql_steps if s.sql],
            "presentation": run.presentation,
            "context_objects": run.context_objects}


async def _runs_and_steps(db: AsyncSession, run_ids: list[int]):
    """The runs behind a batch of messages and their steps, two queries."""
    if not run_ids:
        return {}, {}
    runs = {r.id: r for r in (await db.execute(
        select(AgentRun).where(AgentRun.id.in_(run_ids)))).scalars().all()}
    steps: dict[int, list[AgentStep]] = {}
    for s in (await db.execute(
            select(AgentStep).where(AgentStep.agent_run_id.in_(run_ids))
            .order_by(AgentStep.id))).scalars().all():
        steps.setdefault(s.agent_run_id, []).append(s)
    return runs, steps


async def _history(db: AsyncSession, conv: Conversation) -> list[dict]:
    """The last HISTORY_TURNS messages, oldest first, each assistant turn
    carrying its run's SQL and result snapshots.

    Loaded BEFORE the new user message is added: the session autoflushes on
    query, so loading afterwards would hand the model its own question back
    as history. Ordered by id, not created_at -- a request's user and
    assistant turns share a timestamp."""
    msgs = list(reversed((await db.execute(
        select(AgentMessage).where(AgentMessage.conversation_id == conv.id)
        .order_by(AgentMessage.id.desc()).limit(HISTORY_TURNS))).scalars().all()))
    runs, steps = await _runs_and_steps(
        db, [m.agent_run_id for m in msgs if m.agent_run_id is not None])
    out = []
    for m in msgs:
        entry = {"role": m.role, "content": m.content, "sql": [], "results": []}
        run = runs.get(m.agent_run_id) if m.agent_run_id is not None else None
        if run is not None:
            payload = _run_payload(run, steps.get(run.id, []))
            entry["sql"], entry["results"] = payload["sql"], payload["results"]
        out.append(entry)
    return out


@router.post("/conversations")
async def create_conversation(body: ConversationIn,
                              db: AsyncSession = Depends(get_db),
                              user: User = Depends(get_current_user)):
    if (body.data_source_id is None) == (not body.dataset_ids):
        raise HTTPException(
            422, "exactly one of data_source_id or dataset_ids is required")

    if body.data_source_id is not None:
        source = await db.get(DataSource, body.data_source_id)
        check_org(source, user, "Data source not found")
        # Asking the agent about a connection is reading its data in prose.
        # Without this a member could scope a conversation to a warehouse the
        # Connections page no longer lists for them, and have the model read
        # it out -- the dataset list's rules with an extra step in front.
        visible = await _visible_source_ids(db, user)
        if visible is not None and source.id not in visible:
            raise HTTPException(404, "Data source not found")
        conv = Conversation(org_id=user.org_id, user_id=user.id,
                            data_source_id=source.id, dataset_ids=None,
                            title=body.title or "New conversation")
    else:
        for did in body.dataset_ids:
            ds = await db.get(Dataset, did)
            check_org(ds, user, "Dataset not found")
            # Same gate the Datasets page, the raw preview and widget-data
            # use. The agent reads whole tables to answer, so a scope it may
            # not read is a leak with a friendlier interface.
            await require_dataset_read(db, user, did)
            _reject_directquery(ds)
        conv = Conversation(org_id=user.org_id, user_id=user.id,
                            data_source_id=None,
                            dataset_ids=list(body.dataset_ids),
                            title=body.title or "New conversation")
    db.add(conv)
    await db.commit()
    return {"id": conv.id, "title": conv.title}


@router.get("/conversations")
async def list_conversations(db: AsyncSession = Depends(get_db),
                             user: User = Depends(get_current_user)):
    # Scoped to the CALLING USER, not just the org: AgentStep.sql holds
    # post-policy-injection SQL and RLS predicates carry the asker's email
    # as a literal, so an org-mate listing/reading another user's
    # conversation would leak that user's policy internals and RLS-filtered
    # answers.
    rows = (await db.execute(
        select(Conversation).where(Conversation.org_id == user.org_id,
                                   Conversation.user_id == user.id)
        .order_by(Conversation.id.desc()))).scalars().all()
    return [{"id": c.id, "title": c.title,
             "data_source_id": c.data_source_id,
             "dataset_ids": c.dataset_ids,
             "created_at": c.created_at.isoformat() if c.created_at else None}
            for c in rows]


@router.get("/conversations/{cid}/messages")
async def list_messages(cid: int, db: AsyncSession = Depends(get_db),
                        user: User = Depends(get_current_user)):
    """The thread, oldest first, each assistant turn with the run behind it
    -- answer status, SQL, result snapshots -- so a reopened conversation
    redraws exactly what was shown, grids included. Before this the pane
    resumed the server thread by id but could never read it back."""
    conv = await _owned_conversation(db, cid, user)
    msgs = (await db.execute(
        select(AgentMessage).where(AgentMessage.conversation_id == conv.id)
        .order_by(AgentMessage.id))).scalars().all()
    runs, steps = await _runs_and_steps(
        db, [m.agent_run_id for m in msgs if m.agent_run_id is not None])

    def run_view(m: AgentMessage) -> dict | None:
        run = runs.get(m.agent_run_id) if m.agent_run_id is not None else None
        if run is None:
            return None
        return {"id": run.id, "status": run.status, "intent": run.intent,
                "error": run.error, **_run_payload(run, steps.get(run.id, []))}

    return [{"id": m.id, "role": m.role, "content": m.content,
             "created_at": m.created_at.isoformat() if m.created_at else None,
             "run": run_view(m)} for m in msgs]


@router.patch("/conversations/{cid}")
async def rename_conversation(cid: int, body: TitleIn,
                              db: AsyncSession = Depends(get_db),
                              user: User = Depends(get_current_user)):
    conv = await _owned_conversation(db, cid, user)
    title = body.title.strip()
    if not title:
        raise HTTPException(422, "title must not be blank")
    conv.title = title[:200]
    await db.commit()
    return {"id": conv.id, "title": conv.title}


@router.delete("/conversations/{cid}", status_code=204)
async def delete_conversation(cid: int, db: AsyncSession = Depends(get_db),
                              user: User = Depends(get_current_user)):
    """Messages cascade with the thread; the runs keep their evidence for
    the eval gate and merely lose their conversation_id (FK SET NULL)."""
    conv = await _owned_conversation(db, cid, user)
    await db.delete(conv)
    await db.commit()


@router.post("/conversations/{cid}/ask")
async def ask(cid: int, body: AskIn, db: AsyncSession = Depends(get_db),
              user: User = Depends(get_current_user)):
    conv = await _owned_conversation(db, cid, user)

    # Task E2: daily cap first (cheap, no in-process state), then the
    # concurrent-asks slot wraps the actual run so it's held for the run's
    # whole lifetime and released even if run_agent raises.
    await quotas.enforce_agent_quota(db, user.org_id)

    # Before the new message is added -- see _history for why.
    history = await _history(db, conv)

    # The first question names an untitled thread. Only the default title is
    # replaced: one the user typed, or renamed to, is theirs.
    if not (conv.title or "").strip() or conv.title == DEFAULT_TITLE:
        conv.title = body.question.strip()[:TITLE_MAX] or conv.title

    db.add(AgentMessage(conversation_id=conv.id, role="user",
                        content=body.question))

    async with quotas.concurrent_ask_slot(db, user.org_id):
        if conv.dataset_ids:
            datasets = []
            for did in conv.dataset_ids:
                ds = await db.get(Dataset, did)
                check_org(ds, user, "Conversation not found")
                _reject_directquery(ds)
                datasets.append(ds)
            run = await run_agent(db, question=body.question, datasets=datasets,
                                  user=user, client=llm_service.get_client(),
                                  conversation_id=conv.id, history=history)
        else:
            source = await db.get(DataSource, conv.data_source_id)
            check_org(source, user, "Conversation not found")
            run = await run_agent(db, question=body.question, source=source,
                                  user=user, client=llm_service.get_client(),
                                  conversation_id=conv.id, history=history)

    db.add(AgentMessage(conversation_id=conv.id, role="assistant",
                        content=run.answer or run.error or "",
                        agent_run_id=run.id))
    await db.commit()
    steps = (await db.execute(select(AgentStep).where(
        AgentStep.agent_run_id == run.id).order_by(AgentStep.id))).scalars().all()
    return {"run_id": run.id, "status": run.status, "answer": run.answer,
            "intent": run.intent, "error": run.error,
            **_run_payload(run, steps)}


@router.get("/runs/{run_id}")
async def run_detail(run_id: int, db: AsyncSession = Depends(get_db),
                     user: User = Depends(get_current_user)):
    run = await db.get(AgentRun, run_id)
    check_org(run, user, "Run not found")
    # A run only belongs to the caller if its conversation does. A run with
    # no conversation_id has no route to the caller via this router, so it
    # is guarded shut (404) rather than treated as accessible.
    conv = await db.get(Conversation, run.conversation_id) \
        if run.conversation_id is not None else None
    if conv is None or conv.user_id != user.id:
        raise HTTPException(404, "Run not found")
    steps = (await db.execute(select(AgentStep).where(
        AgentStep.agent_run_id == run.id).order_by(AgentStep.id))).scalars().all()
    return {"id": run.id, "status": run.status, "question": run.question,
            "intent": run.intent, "answer": run.answer, "error": run.error,
            "plan": run.plan, "ms": run.ms,
            "context_objects": run.context_objects,
            "presentation": run.presentation,
            "steps": [{"node": s.node, "status": s.status, "sql": s.sql,
                       "rows_returned": s.rows_returned,
                       "result_rows": s.result_rows,
                       "validation_failures": s.validation_failures,
                       "repair_attempts": s.repair_attempts, "ms": s.ms}
                      for s in steps]}


_EXPORT_MEDIA = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}


@router.get("/runs/{run_id}/export")
async def export_run(run_id: int, format: str = "xlsx",
                     db: AsyncSession = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """One answer's result as a file. Same ownership rule as /runs/{id}; the
    rows come from the stored snapshot, so what downloads is exactly what the
    chat showed -- same RLS, same cap -- in a different format. CSV stays
    client-side (the browser already holds the rows); this endpoint carries
    the two formats a browser cannot write itself."""
    fmt = (format or "").lower()
    if fmt not in _EXPORT_MEDIA:
        raise HTTPException(400, "format must be 'xlsx' or 'pdf'")

    run = await db.get(AgentRun, run_id)
    check_org(run, user, "Run not found")
    conv = await db.get(Conversation, run.conversation_id) \
        if run.conversation_id is not None else None
    if conv is None or conv.user_id != user.id:
        raise HTTPException(404, "Run not found")

    steps = (await db.execute(select(AgentStep).where(
        AgentStep.agent_run_id == run.id).order_by(AgentStep.id))).scalars().all()
    snaps = [(s.node, s.result_rows) for s in steps if s.result_rows]
    if not snaps:
        raise HTTPException(400, "This answer has no tabular result to export")

    # Serialization is CPU-bound (xlsx especially) -- a worker thread, not
    # the event loop, same as the widget export.
    if fmt == "xlsx":
        payload = await asyncio.to_thread(build_result_xlsx, snaps)
    else:
        sqls = [s.sql for s in steps if s.sql]
        payload = await asyncio.to_thread(
            build_result_pdf, run.question, run.answer, sqls, snaps)

    return StreamingResponse(
        io.BytesIO(payload), media_type=_EXPORT_MEDIA[fmt],
        headers={"Content-Disposition":
                 f'attachment; filename="ask-ai-result-{run.id}.{fmt}"'})


@router.post("/conversations/{cid}/feedback")
async def submit_feedback(cid: int, body: FeedbackIn,
                          db: AsyncSession = Depends(get_db),
                          user: User = Depends(get_current_user)):
    """👍/👎 on an agent answer. Owner-only -- same-org, different-user is a
    404 just like /ask and /runs/{id}, because AgentStep.sql (reachable via
    run_id) carries the asker's RLS-filtered results, not just the rating."""
    conv = await db.get(Conversation, cid)
    check_org(conv, user, "Conversation not found")
    if conv.user_id != user.id:
        raise HTTPException(404, "Conversation not found")

    if body.rating not in ("up", "down"):
        raise HTTPException(422, "rating must be 'up' or 'down'")

    if body.run_id is not None:
        run = await db.get(AgentRun, body.run_id)
        check_org(run, user, "Run not found")
        if run.conversation_id != conv.id:
            raise HTTPException(404, "Run not found")

    existing = (await db.execute(
        select(AgentFeedback).where(
            AgentFeedback.conversation_id == conv.id,
            AgentFeedback.run_id == body.run_id,
            AgentFeedback.user_id == user.id))).scalar_one_or_none()
    if existing is not None:
        existing.rating = body.rating
        existing.comment = body.comment
        fb = existing
    else:
        fb = AgentFeedback(org_id=user.org_id, user_id=user.id,
                           conversation_id=conv.id, run_id=body.run_id,
                           rating=body.rating, comment=body.comment)
        db.add(fb)
    await db.commit()
    await db.refresh(fb)
    return {"id": fb.id, "run_id": fb.run_id, "rating": fb.rating,
            "comment": fb.comment}


@router.get("/row-policies")
async def list_row_policies(source_id: int, db: AsyncSession = Depends(get_db),
                            user: User = Depends(require_org_admin)):
    source = await db.get(DataSource, source_id)
    check_org(source, user, "Data source not found")

    rows = (await db.execute(
        select(ObjectRowPolicy, SourceObject.name, Role.name)
        .join(SourceObject, SourceObject.id == ObjectRowPolicy.source_object_id)
        .join(Role, Role.id == ObjectRowPolicy.role_id)
        .where(ObjectRowPolicy.org_id == user.org_id,
               SourceObject.data_source_id == source_id))).all()
    return [{"id": pol.id, "source_object_id": pol.source_object_id,
             "object_name": obj_name, "role_id": pol.role_id,
             "role_name": role_name, "predicate": pol.predicate}
            for pol, obj_name, role_name in rows]


@router.post("/row-policies")
async def create_row_policy(body: RowPolicyIn,
                            db: AsyncSession = Depends(get_db),
                            user: User = Depends(require_org_admin)):
    obj = await db.get(SourceObject, body.source_object_id)
    check_org(obj, user, "Source object not found")

    role = await db.get(Role, body.role_id)
    check_org(role, user, "Role not found")

    # Validate in the SAME dialect apply-time (agent/policy.py) will parse in
    # — the source's real type, not a hardcoded one. A predicate valid only
    # in the source's dialect must not be wrongly 422'd here, and a
    # dialect-specific predicate that only "looks" valid under a different
    # dialect must not slip through and fail closed later at query time.
    source = await db.get(DataSource, obj.data_source_id)
    check_org(source, user, "Data source not found")

    try:
        sqlglot.parse_one(body.predicate, dialect=_dialect(source.type),
                          into=exp.Condition)
    except Exception as exc:
        raise HTTPException(
            422, str(exc).splitlines()[0] if str(exc) else "invalid predicate")

    existing = (await db.execute(
        select(ObjectRowPolicy).where(
            ObjectRowPolicy.source_object_id == body.source_object_id,
            ObjectRowPolicy.role_id == body.role_id))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            409, "A row policy already exists for this object and role")

    policy = ObjectRowPolicy(org_id=user.org_id,
                             source_object_id=body.source_object_id,
                             role_id=body.role_id, predicate=body.predicate)
    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    return {"id": policy.id, "source_object_id": policy.source_object_id,
            "object_name": obj.name, "role_id": policy.role_id,
            "role_name": role.name, "predicate": policy.predicate}


@router.delete("/row-policies/{policy_id}", status_code=204)
async def delete_row_policy(policy_id: int, db: AsyncSession = Depends(get_db),
                            user: User = Depends(require_org_admin)):
    policy = await db.get(ObjectRowPolicy, policy_id)
    check_org(policy, user, "Row policy not found")
    await db.delete(policy)
    await db.commit()
