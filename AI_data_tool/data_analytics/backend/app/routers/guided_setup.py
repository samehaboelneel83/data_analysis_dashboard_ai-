"""Guided setup: connect -> understand -> choose data -> check & discover -> dashboard.

docs/guided-setup/PLAN.md and PLAN_V2.md. A journey is per person and
connection, so two people setting up the same database each keep their own
place. Understand is done once per journey; steps 2-4 are a FLOW, and a
person may run several on one connection -- each with its own request, its
own datasets and its own dashboard (`flow=` on every step's route; without
it, the flow last worked on). Every route reads the connection with the caller's own
visibility (decision D1): a connection hidden from them is a 404.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.capability import readable_dataset_ids
from ..core.database import get_db
from ..core.org_scope import check_org
from ..dependencies import get_current_user
from ..models.models import DataSource, Dataset, MeaningFact, Report, SetupFlow, SetupJourney, SourceObject, User
from ..services.guided_setup import access

logger = __import__("logging").getLogger(__name__)

router = APIRouter(prefix="/setup", tags=["guided-setup"])

#: The four steps the progress bar shows, in order; "done" follows the last.
STEPS = ("understand", "data", "check", "dashboard")
Step = Literal["understand", "data", "check", "dashboard", "done"]
#: The steps a flow goes through; Understand belongs to the journey, once.
FLOW_STEPS = ("data", "check", "dashboard", "done")

#: Longest answer kept per "About you" field: hints for a prompt, not documents.
BRIEF_FIELD_MAX = 1000
#: Most flows offered on one connection; older ones can be archived.
MAX_FLOWS = 60          # the default of settings.setup_max_analyses


class Brief(BaseModel):
    """About you -- every field optional; what the person typed."""
    work: str | None = Field(None, max_length=BRIEF_FIELD_MAX)
    focus: str | None = Field(None, max_length=BRIEF_FIELD_MAX)
    questions: str | None = Field(None, max_length=BRIEF_FIELD_MAX)
    exclude: str | None = Field(None, max_length=BRIEF_FIELD_MAX)


class JourneyUpdate(BaseModel):
    step: Step | None = None
    brief: Brief | None = None
    dataset_ids: list[int] | None = None
    #: Which of `dataset_ids` this flow made itself (the others were adopted).
    created_ids: list[int] | None = None
    report_id: int | None = None



def _with_background(brief: dict | None, user, source) -> dict:
    """The person's brief with what they wrote on their profile and what the
    connection is described as, for the model calls that read it. Nothing is
    stored: the saved brief stays what the person typed in the setup."""
    from ..services.ai_context import _clean
    out = dict(brief or {})
    about, described = _clean(getattr(user, "about", None)), _clean(getattr(source, "description", None))
    if about:
        out["about"] = about
    if described:
        out["connection"] = described
    return out

async def source_or_404(db: AsyncSession, source_id: int, user: User) -> DataSource:
    """The connection if this user may SEE it (the Connections list's rule)."""
    source = await access.visible_source(db, source_id, user)
    if source is None:
        raise HTTPException(404, "Data source not found")
    return source


async def _journey(db: AsyncSession, user: User, source: DataSource) -> SetupJourney | None:
    return (await db.execute(select(SetupJourney).where(
        SetupJourney.user_id == user.id,
        SetupJourney.data_source_id == source.id))).scalar_one_or_none()


async def _journey_or_start(db: AsyncSession, user: User, source: DataSource) -> SetupJourney:
    j = await _journey(db, user, source)
    if j is None:
        j = SetupJourney(org_id=user.org_id, user_id=user.id, data_source_id=source.id,
                         step="understand", created_at=datetime.utcnow(), updated_at=datetime.utcnow())
        db.add(j)
        await db.commit()
        await db.refresh(j)
    return j


# ── flows: steps 2-4, as many times as the person has things to ask ─────────

def _new_flow(j: SetupJourney, **fields) -> SetupFlow:
    now = datetime.utcnow()
    return SetupFlow(org_id=j.org_id, user_id=j.user_id, journey_id=j.id, data_source_id=j.data_source_id,
                     created_at=now, updated_at=now, **{"step": "data", **fields})


async def _flows(db: AsyncSession, j: SetupJourney) -> list[SetupFlow]:
    """The journey's flows, oldest first. A journey from before flows existed
    kept steps 2-4 on itself: its first read copies them into its first flow,
    so nothing in progress is lost (alembic 0061)."""
    rows = (await db.execute(select(SetupFlow).where(SetupFlow.journey_id == j.id)
                             .order_by(SetupFlow.created_at, SetupFlow.id))).scalars().all()
    if not rows and (j.proposals or j.dataset_ids or j.findings or j.designs or j.report_id or j.brief):
        f = _new_flow(j, step=j.step if j.step in FLOW_STEPS else "data", brief=j.brief,
                      dataset_ids=j.dataset_ids, report_id=j.report_id, proposals=j.proposals,
                      findings=j.findings, designs=j.designs)
        db.add(f)
        await db.commit()
        await db.refresh(f)
        rows = [f]
    return [f for f in rows if not f.archived]


def _latest(flows: list[SetupFlow]) -> SetupFlow | None:
    return max(flows, key=lambda f: (f.updated_at or f.created_at or datetime.min, f.id)) if flows else None


async def _start_flow(db: AsyncSession, j: SetupJourney, flows: list[SetupFlow]) -> SetupFlow:
    """A new flow, starting at Choose data. Who the person is was asked once:
    it is carried over; what they want this time is not."""
    last = _latest(flows)
    work = ((last.brief or {}).get("work") if last is not None else None)
    f = _new_flow(j, brief={"work": work} if work else None)
    db.add(f)
    await db.commit()
    await db.refresh(f)
    return f


async def _flow(db: AsyncSession, user: User, source: DataSource,
                flow_id: int | None = None) -> tuple[SetupJourney, SetupFlow]:
    """(the journey, the flow asked for) -- or the one last worked on, started
    when there is none yet."""
    j = await _journey_or_start(db, user, source)
    flows = await _flows(db, j)
    if flow_id is not None:
        f = next((x for x in flows if x.id == flow_id), None)
        if f is None:
            raise HTTPException(404, "Analysis not found")
        return j, f
    return j, _latest(flows) or await _start_flow(db, j, flows)


def _touch(f: SetupFlow) -> None:
    f.updated_at = datetime.utcnow()


def _flow_name(f: SetupFlow) -> str | None:
    """What the person would call this analysis: the name they gave it, else
    what they asked for."""
    if f.name:
        return f.name
    b = f.brief or {}
    said = (f.demand or {}).get("subject") or (f.demand or {}).get("sentence") or b.get("focus") or b.get("questions")
    return (str(said).strip()[:70] or None) if said else None


def _flow_out(f: SetupFlow) -> dict:
    return {"id": f.id, "name": _flow_name(f), "step": f.step,
            "position": STEPS.index(f.step) + 1 if f.step in STEPS else len(STEPS),
            "dataset_ids": list(f.dataset_ids or []), "report_id": f.report_id,
            "updated_at": f.updated_at.isoformat() if f.updated_at else None}


def _out(j: SetupJourney, source: DataSource, flows: list[SetupFlow], f: SetupFlow | None) -> dict:
    """The journey as the page reads it: the step of the flow on screen (or
    Understand, until that is done), plus every flow of this connection."""
    step = "understand" if j.step == "understand" or f is None else f.step
    position = STEPS.index(step) + 1 if step in STEPS else len(STEPS)
    return {
        "id": j.id,
        "source": {"id": source.id, "name": source.name, "type": source.type},
        "step": step,
        "position": position,
        "total": len(STEPS),
        "brief": (f.brief if f is not None else None) or {},
        "dataset_ids": list((f.dataset_ids if f is not None else None) or []),
        "report_id": f.report_id if f is not None else None,
        "flow_id": f.id if f is not None else None,
        "flow_name": _flow_name(f) if f is not None else None,
        "flows": [_flow_out(x) for x in flows],
        "updated_at": ((f.updated_at if f is not None else None) or j.updated_at or datetime.utcnow()).isoformat(),
    }


@router.get("/journeys")
async def my_journeys(db: AsyncSession = Depends(get_db),
                      user: User = Depends(get_current_user)):
    """What Home offers to continue, newest first: every unfinished analysis
    (one line per flow), and connections still at Understand.

    A journey on a connection I can no longer see is left out, not shown."""
    rows = (await db.execute(
        select(SetupJourney, DataSource)
        .join(DataSource, DataSource.id == SetupJourney.data_source_id)
        .where(SetupJourney.user_id == user.id, SetupJourney.org_id == user.org_id))).all()
    visible = await access.visible_source_ids(db, user)
    out = []
    for j, s in rows:
        if visible is not None and s.id not in visible:
            continue
        flows = await _flows(db, j)
        if j.step == "understand":
            out.append(_out(j, s, flows, None))
            continue
        out += [_out(j, s, flows, f) for f in flows if f.step != "done"]
    return sorted(out, key=lambda o: o["updated_at"], reverse=True)


@router.get("/{source_id}")
async def get_journey(source_id: int, flow: int | None = None, db: AsyncSession = Depends(get_db),
                      user: User = Depends(get_current_user)):
    """My setup of this connection, started on first visit; `flow` picks one of
    its analyses (default: the one last worked on)."""
    source = await source_or_404(db, source_id, user)
    j, f = await _flow(db, user, source, flow)
    return _out(j, source, await _flows(db, j), f)


@router.patch("/{source_id}")
async def update_journey(source_id: int, body: JourneyUpdate, flow: int | None = None,
                         db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    source = await source_or_404(db, source_id, user)
    if await _journey(db, user, source) is None:
        raise HTTPException(404, "Setup not started")
    j, f = await _flow(db, user, source, flow)
    if body.step is not None:
        if body.step != "understand":
            if j.step == "understand":
                j.step = "data"          # Understand is done once, for every flow
            f.step = body.step
    if body.brief is not None:
        # Blank answers are dropped, so "not answered" and "answered empty" read the same.
        f.brief = {k: v.strip() for k, v in body.brief.model_dump().items() if v and v.strip()}
    if body.dataset_ids is not None:
        ids = list(dict.fromkeys(body.dataset_ids))
        if ids:
            readable = await readable_dataset_ids(db, user)
            found = set((await db.execute(select(Dataset.id).where(
                Dataset.id.in_(ids), Dataset.org_id == user.org_id))).scalars().all())
            if set(ids) - found or (readable is not None and set(ids) - readable):
                raise HTTPException(404, "Dataset not found")
        if ids != list(f.dataset_ids or []):
            # Other data, another request: what was written down and designed
            # for the old datasets no longer stands.
            f.demand, f.designs = None, None
        f.dataset_ids = ids
        made = set(f.created_ids or []) | set(body.created_ids or [])
        f.created_ids = [i for i in ids if i in made]
    if "report_id" in body.model_fields_set:
        if body.report_id is not None:
            check_org(await db.get(Report, body.report_id), user, "Dashboard not found")
        f.report_id = body.report_id
    _touch(f)
    j.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(f)
    return _out(j, source, await _flows(db, j), f)


class FlowUpdate(BaseModel):
    name: str | None = Field(None, max_length=255)
    archived: bool | None = None


@router.post("/{source_id}/flows")
async def start_flow(source_id: int, db: AsyncSession = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """Start another analysis of this connection, from Choose data. The ones
    already made are untouched."""
    source = await source_or_404(db, source_id, user)
    j = await _journey_or_start(db, user, source)
    flows = await _flows(db, j)
    from ..core.config import settings as _settings
    if len(flows) >= int(getattr(_settings, "setup_max_analyses", MAX_FLOWS) or MAX_FLOWS):
        raise HTTPException(400, "Too many analyses on this connection; remove one first")
    # An empty flow already waiting is the new one: pressing twice makes one.
    f = next((x for x in flows if not x.proposals and not x.dataset_ids and x.step == "data"
              and not set(x.brief or {}) - {"work"}), None)
    if f is None:
        f = await _start_flow(db, j, flows)
    else:
        _touch(f)
    if j.step == "understand":
        j.step = "data"
    await db.commit()
    return _out(j, source, await _flows(db, j), f)


@router.patch("/{source_id}/flows/{flow_id}")
async def update_flow(source_id: int, flow_id: int, body: FlowUpdate, db: AsyncSession = Depends(get_db),
                      user: User = Depends(get_current_user)):
    """Rename an analysis, or remove it from the list (its datasets and its
    dashboard stay where they are)."""
    source = await source_or_404(db, source_id, user)
    j, f = await _flow(db, user, source, flow_id)
    if body.name is not None:
        f.name = body.name.strip() or None
    if body.archived is not None:
        f.archived = body.archived
    await db.commit()
    flows = await _flows(db, j)
    return _out(j, source, flows, _latest(flows))


# ── Step 1: Understand ──────────────────────────────────────────────────────

#: Tables whose sample rows go to the model with the summary request.
PROMPT_SAMPLES = 6
#: A "still writing" mark older than this is treated as abandoned (a restart
#: mid-call), so the next visit starts again instead of waiting forever.
PENDING_STALE_SECONDS = 600

#: (journey, language) pairs whose words are being written in this process now.
_writing: set[tuple[int, str]] = set()


def _language(lang: str | None) -> str:
    return "ar" if (lang or "").lower().startswith("ar") else "en"


def _entries(j: SetupJourney) -> dict:
    """The kept words, one entry per language:
    {"en": {"attempt", "words"?, "pending"?, "failed"?, "at"}, "ar": {...}}.

    Asked once per language and kept until someone presses "Ask AI again"
    (owner, 2026-10-07): leaving the page, switching language, re-syncing or
    correcting a description never asks again by itself -- a correction wins
    over the model's text when the page is drawn, so it needs no new words.
    Rows written before this shape ({"key": "en|<sync>", ...}) are read as
    that language's entry."""
    raw = dict(j.summary or {})
    if "key" in raw:
        lang = str(raw.pop("key")).split("|", 1)[0] or "en"
        return {lang: {"attempt": "legacy", **raw}}
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def _keep_entries(j: SetupJourney, entries: dict) -> None:
    """Write the language entries back, keeping the private keys (_ranges)."""
    private = {k: v for k, v in dict(j.summary or {}).items() if k.startswith("_")}
    j.summary = {**private, **entries}


async def _ranges_for(db: AsyncSession, user: User, source: DataSource, j: SetupJourney,
                      facts: list[dict]) -> dict | None:
    """Measured date ranges, kept on the journey per sync; None while not measured."""
    kept = (j.summary or {}).get("_ranges") or {}
    stamp = source.last_synced_at.isoformat() if source.last_synced_at else None
    values = kept.get("values")
    # Ranges kept before each recorded its column are measured again.
    if kept.get("sync") != stamp or any("column" not in v for v in (values or {}).values()):
        return None
    return values


async def write_ranges(db: AsyncSession, journey_id: int) -> None:
    from ..services.guided_setup import understand
    j = await db.get(SetupJourney, journey_id)
    if j is None:
        return
    source, user = await _owner(db, j)
    if source is None or user is None:
        return
    facts = await understand.load_facts(db, source)
    values = await understand.exact_ranges(db, user, source, facts)
    await db.refresh(j)
    stamp = source.last_synced_at.isoformat() if source.last_synced_at else None
    j.summary = {**dict(j.summary or {}), "_ranges": {"sync": stamp, "values": values}}
    await db.commit()


async def write_words(db: AsyncSession, journey_id: int, lang: str, attempt: str) -> None:
    """Ask the model for the Understand step's words and keep them on the journey.

    Runs detached from the request: a model can take minutes (or be down, and
    fail over endpoint by endpoint), and the facts must not wait on it. Reads
    sample rows as the journey's owner (decision D1). Every outcome is kept --
    the words, or why there are none -- so a model that is down is not asked
    again on every visit. A failed re-ask keeps the earlier words."""
    from sqlalchemy.orm import selectinload
    from ..services.guided_setup import understand
    from ..services.llm import get_client

    j = await db.get(SetupJourney, journey_id)
    if j is None:
        return
    source = await db.get(DataSource, j.data_source_id)
    from ..services import ai_policy
    await ai_policy.enter(db, source=source)
    user = (await db.execute(select(User).options(selectinload(User.role))
                             .where(User.id == j.user_id))).scalar_one_or_none()
    if source is None or user is None:
        return
    facts = await understand.load_facts(db, source)
    ranges = await _ranges_for(db, user, source, j, facts)
    if ranges is None:
        ranges = await understand.exact_ranges(db, user, source, facts)
    understand.apply_ranges(facts, ranges)
    samples: dict[str, list[dict]] = {}
    for t in [t for t in facts if t["group"] != "technical"][:PROMPT_SAMPLES]:
        got = await access.sample_rows(db, user, source, await db.get(SourceObject, t["id"]), limit=2)
        if got["rows"]:
            samples[t["name"]] = got["rows"]
    await access.release(db)
    try:
        words, reason = await understand.describe(source, facts, lang, samples, get_client())
    except Exception:                                       # noqa: BLE001
        import logging
        logging.getLogger(__name__).exception("guided setup: describing the database failed")
        words, reason = None, "failed"
    await db.refresh(j)
    entries = _entries(j)
    entry = entries.get(lang) or {}
    if entry.get("attempt") != attempt:
        return   # a newer "Ask AI again" replaced this attempt meanwhile
    now = datetime.utcnow().isoformat()
    if words is not None:
        entries[lang] = {"attempt": attempt, "words": words, "at": now}
    else:
        kept = {"words": entry["words"]} if entry.get("words") is not None else {}
        entries[lang] = {"attempt": attempt, **kept, "failed": reason or "failed", "at": now}
    _keep_entries(j, entries)
    await db.commit()


async def _start_writing(db: AsyncSession, user: User, journey_id: int, lang: str, attempt: str) -> None:
    """Start `write_words` in the background, metered against the user's org."""
    import asyncio
    from ..core.database import AsyncSessionLocal
    from ..services import quotas

    if (journey_id, lang) in _writing:
        return
    _writing.add((journey_id, lang))
    meter = await quotas.open_ai_meter(db, user.org_id, user.id, "setup")

    async def run():
        try:
            async with AsyncSessionLocal() as session:
                await write_words(session, journey_id, lang, attempt)
        except Exception:                                   # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception("guided setup: writing the summary failed")
            try:   # never leave the words "pending": every visit would restart them
                async with AsyncSessionLocal() as session:
                    j = await session.get(SetupJourney, journey_id)
                    if j is not None:
                        entries = _entries(j)
                        entry = dict(entries.get(lang) or {})
                        if entry.get("attempt") == attempt:
                            entries[lang] = {**{k: v for k, v in entry.items() if k != "pending"}, "failed": "failed"}
                            _keep_entries(j, entries)
                            await session.commit()
            except Exception:                               # noqa: BLE001
                logging.getLogger(__name__).exception("guided setup: recording the summary failure failed")
        finally:
            _writing.discard((journey_id, lang))

    asyncio.create_task(quotas.run_metered(AsyncSessionLocal, meter, run()))


def _pending_is_stale(cached: dict) -> bool:
    try:
        started = datetime.fromisoformat(cached.get("at") or "")
    except ValueError:
        return True
    return (datetime.utcnow() - started).total_seconds() > PENDING_STALE_SECONDS


async def _summary(db: AsyncSession, user: User, source: DataSource, lang: str,
                   *, fresh: bool = False) -> dict:
    from ..services.guided_setup import understand
    from .data_sources import _may_administer

    facts = await understand.load_facts(db, source)
    base = {
        "source": {"id": source.id, "name": source.name, "type": source.type,
                   "allow_ai": bool(source.allow_llm_sampling)},
        "sync": {"status": source.sync_status,
                 "last_synced_at": source.last_synced_at.isoformat() if source.last_synced_at else None},
        "can_edit": _may_administer(source, user),
        "language": lang,
    }
    if not facts:
        # Nothing catalogued: still syncing, the sync failed, or the database is empty.
        status = ("syncing" if source.sync_status in ("pending", "running") else
                  "failed" if source.sync_status == "failed" else "empty")
        return {**base, "status": status}

    # The facts answer now; the model's words arrive when they are written.
    words, ai = None, {"used": False, "pending": False, "reason": None}
    j = await _journey_or_start(db, user, source)
    ranges = await _ranges_for(db, user, source, j, facts)
    if ranges is None:
        async def measure(session):
            await write_ranges(session, j.id)
        await _background(db, user, f"ranges:{j.id}", measure)
    understand.apply_ranges(facts, ranges)
    base["ranges_pending"] = ranges is None
    if not source.allow_llm_sampling:
        ai["reason"] = "off"
    else:
        import uuid
        entries = _entries(j)
        entry = entries.get(lang) or {}
        start = fresh or not entry or (entry.get("pending") and _pending_is_stale(entry))
        if start:
            attempt = uuid.uuid4().hex
            kept = {"words": entry["words"]} if entry.get("words") is not None else {}
            entries[lang] = {"attempt": attempt, **kept, "pending": True, "at": datetime.utcnow().isoformat()}
            _keep_entries(j, entries)
            await db.commit()
            await _start_writing(db, user, j.id, lang, attempt)
            entry = entries[lang]
        elif entry.get("pending") and (j.id, lang) not in _writing:
            # A restart dropped the task: carry on with the same attempt.
            await _start_writing(db, user, j.id, lang, entry["attempt"])
        if entry.get("words") is not None:
            words, ai["used"] = entry["words"], True
        ai["pending"] = bool(entry.get("pending"))
        if entry.get("failed") and not ai["pending"]:
            ai["reason"] = entry["failed"]

    merged = understand.merge_words(facts, words)
    if source.description and source.description_source == "confirmed":
        overview, overview_source = source.description, "you"
    elif merged["overview"]:
        overview, overview_source = merged["overview"], "ai"
    elif source.description:
        overview, overview_source = source.description, "ai"
    else:
        overview, overview_source = None, None
    return {**base, "status": "ready", "ai": ai,
            "overview": overview, "overview_source": overview_source,
            "totals": understand.totals(facts),
            "tables": merged["tables"],
            "relationships": understand.relationships_of(facts),
            "questions": merged["questions"]}


@router.get("/{source_id}/summary")
async def get_summary(source_id: int, lang: str = "en", db: AsyncSession = Depends(get_db),
                      user: User = Depends(get_current_user)):
    """What the database holds, in plain words, most useful tables first.

    Answers at once with the facts; while the model is still writing, `ai.pending`
    is true and the page asks again in a few seconds."""
    source = await source_or_404(db, source_id, user)
    return await _summary(db, user, source, _language(lang))


@router.post("/{source_id}/summary/refresh")
async def refresh_summary(source_id: int, lang: str = "en", db: AsyncSession = Depends(get_db),
                          user: User = Depends(get_current_user)):
    """Ask the model again -- the only thing that does ("Ask AI again")."""
    source = await source_or_404(db, source_id, user)
    return await _summary(db, user, source, _language(lang), fresh=True)


async def _object_or_404(db: AsyncSession, source: DataSource, object_id: int) -> SourceObject:
    obj = await db.get(SourceObject, object_id)
    if obj is None or obj.data_source_id != source.id:
        raise HTTPException(404, "Table not found")
    return obj


@router.get("/{source_id}/tables/{object_id}/sample")
async def table_sample(source_id: int, object_id: int, limit: int = 5,
                       db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """A few rows, as this user may see them (row rules applied, personal values masked)."""
    source = await source_or_404(db, source_id, user)
    obj = await _object_or_404(db, source, object_id)
    return await access.sample_rows(db, user, source, obj, limit=limit)


class DescriptionIn(BaseModel):
    text: str = Field("", max_length=4000)


async def _editable(db: AsyncSession, source_id: int, user: User) -> DataSource:
    from .data_sources import _may_administer
    source = await source_or_404(db, source_id, user)
    if not _may_administer(source, user):
        raise HTTPException(403, "Only an admin or the person who added this connection can change its description")
    return source


@router.patch("/{source_id}/overview")
async def edit_overview(source_id: int, body: DescriptionIn, db: AsyncSession = Depends(get_db),
                        user: User = Depends(get_current_user)):
    """Correct the database's description. Empty text hands it back to the model."""
    source = await _editable(db, source_id, user)
    text = body.text.strip()
    source.description = text or None
    source.description_source = "confirmed" if text else None
    await db.commit()
    return {"overview": source.description, "overview_source": "you" if text else None}


@router.patch("/{source_id}/tables/{object_id}")
async def edit_table(source_id: int, object_id: int, body: DescriptionIn,
                     db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Correct what a table holds. Empty text hands it back to the model."""
    source = await _editable(db, source_id, user)
    obj = await _object_or_404(db, source, object_id)
    text = body.text.strip()
    obj.description = text or None
    obj.description_source = "confirmed" if text else None
    await db.commit()
    return {"id": obj.id, "what": obj.description, "what_source": "you" if text else None}


# ── the Meaning map: how to read this database (docs/meaning-map/PLAN.md) ───

async def write_meaning(db: AsyncSession, journey_id: int, attempt: str) -> None:
    """Measure and name the connection's meaning facts, once; kept until
    "Ask AI again". Read as the journey's owner (decision D1)."""
    from ..services.guided_setup import meaning
    from ..services.llm import get_client
    j = await db.get(SetupJourney, journey_id)
    if j is None:
        return
    source, user = await _owner(db, j)
    if source is None or user is None:
        return
    failed = None
    try:
        built = await meaning.build(db, user, source, get_client())
        await meaning.save(db, source, built)
    except Exception:                                       # noqa: BLE001
        logger.exception("meaning map: building it for source %s failed", j.data_source_id)
        failed = "failed"
    await db.refresh(j)
    state = dict((j.summary or {}).get("_meaning") or {})
    if state.get("attempt") != attempt:
        return
    stamp = source.last_synced_at.isoformat() if source.last_synced_at else None
    j.summary = {**dict(j.summary or {}), "_meaning": {"attempt": attempt, "failed": failed, "sync": stamp,
                                                       "at": datetime.utcnow().isoformat()}}
    await db.commit()


async def _start_meaning(db: AsyncSession, user: User, j: SetupJourney) -> None:
    import uuid
    attempt = uuid.uuid4().hex
    j.summary = {**dict(j.summary or {}), "_meaning": {"attempt": attempt, "pending": True,
                                                       "at": datetime.utcnow().isoformat()}}
    await db.commit()

    async def job(session):
        await write_meaning(session, j.id, attempt)

    async def failed(session):
        row = await session.get(SetupJourney, j.id)
        state = dict((row.summary or {}).get("_meaning") or {}) if row is not None else {}
        if row is not None and state.get("attempt") == attempt:
            row.summary = {**dict(row.summary or {}), "_meaning": {"attempt": attempt, "failed": "failed",
                                                                   "at": datetime.utcnow().isoformat()}}
            await session.commit()
    await _background(db, user, f"meaning:{j.data_source_id}", job, failed)


async def _meaning_out(db: AsyncSession, j: SetupJourney, source: DataSource, lang: str) -> dict:
    from ..services.guided_setup import meaning
    state = dict((j.summary or {}).get("_meaning") or {})
    pending = bool(state.get("pending")) and not _pending_is_stale(state)
    rows = (await db.execute(select(MeaningFact).where(MeaningFact.data_source_id == source.id)
                             .order_by(MeaningFact.kind, MeaningFact.subject))).scalars().all()
    words = _words_of(j, lang) or {}
    titles = {t.get("name"): t.get("title") for t in words.get("tables") or [] if isinstance(t, dict) and t.get("title")}
    active = await meaning.load(db, source.id)
    rejected = [{"kind": r.kind, "subject": r.subject} for r in rows if r.status != "active"]
    return {"pending": pending, "failed": state.get("failed"), "built": bool(state) and not pending,
            "lines": meaning.sentences(active, lang, titles),
            "rejected": rejected,
            "numbers": [{"subject": r.subject, "table": r.body.get("table"), "column": r.body.get("column"),
                         "kind": r.body.get("kind"), "unit": r.body.get("unit") or "",
                         "direction": r.body.get("direction") or "neither", "source": r.source}
                        for r in rows if r.kind == "number" and r.status == "active"],
            "kinds": list(meaning.NUMBER_KINDS), "min_base": meaning.MIN_BASE}


@router.get("/{source_id}/meaning")
async def get_meaning(source_id: int, lang: str = "en", db: AsyncSession = Depends(get_db),
                      user: User = Depends(get_current_user)):
    """How to read this database: what is counted against what, what became of
    a row, which numbers add up. Built once on the first visit."""
    source = await source_or_404(db, source_id, user)
    j = await _journey_or_start(db, user, source)
    state = dict((j.summary or {}).get("_meaning") or {})
    stamp = source.last_synced_at.isoformat() if source.last_synced_at else None
    synced = source.sync_status not in ("pending", "running") and stamp is not None
    if synced and (not state or (state.get("pending") and _pending_is_stale(state))):
        await _start_meaning(db, user, j)
    elif state.get("pending") and f"meaning:{source.id}" not in _running:
        async def job(session):
            await write_meaning(session, j.id, state["attempt"])
        await _background(db, user, f"meaning:{source.id}", job)
    return await _meaning_out(db, j, source, _language(lang))


@router.get("/{source_id}/meaning/link-checks")
async def meaning_link_checks(source_id: int, db: AsyncSession = Depends(get_db),
                              user: User = Depends(get_current_user)):
    """Are the links between this connection's tables consistent? For each
    measured link: how many rows point at something that is not there
    (orphans -- they silently drop out of every joined figure), how many
    carry no value at all, and how many parents have children. Counted on the
    database, as this person. Problems first."""
    from ..services.guided_setup import meaning, understand
    source = await source_or_404(db, source_id, user)
    facts = await understand.load_facts(db, source)
    checks = await meaning.link_checks(db, user, source, facts)
    return {"source_id": source_id, "links": checks,
            "problems": sum(1 for c in checks if c["verdict"] in ("many_orphans", "few_orphans", "empty"))}


@router.post("/{source_id}/meaning/refresh")
async def refresh_meaning(source_id: int, lang: str = "en", db: AsyncSession = Depends(get_db),
                          user: User = Depends(get_current_user)):
    """Measure and ask again. A person's own corrections stay."""
    source = await source_or_404(db, source_id, user)
    j = await _journey_or_start(db, user, source)
    await _start_meaning(db, user, j)
    return await _meaning_out(db, j, source, _language(lang))


class MeaningEdit(BaseModel):
    kind: Literal["grain", "base", "outcome", "number"]
    subject: str = Field(..., max_length=600)
    #: "rejected" = not right, never use it; "active" = use it again.
    status: Literal["active", "rejected"] | None = None
    number_kind: str | None = None
    direction: str | None = None


@router.patch("/{source_id}/meaning")
async def edit_meaning(source_id: int, body: MeaningEdit, lang: str = "en", db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user)):
    """A person corrects the map: their word wins over the model's and over
    the next measurement."""
    from ..services.guided_setup import meaning
    source = await _editable(db, source_id, user)
    j = await _journey_or_start(db, user, source)
    row = (await db.execute(select(MeaningFact).where(
        MeaningFact.data_source_id == source.id, MeaningFact.kind == body.kind,
        MeaningFact.subject == body.subject))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Fact not found")
    if body.status is not None:
        row.status = body.status
    change = dict(row.body or {})
    if body.number_kind is not None:
        if body.number_kind not in meaning.NUMBER_KINDS:
            raise HTTPException(422, "Unknown kind of number")
        change["kind"] = body.number_kind
    if body.direction is not None:
        if body.direction not in meaning.DIRECTIONS:
            raise HTTPException(422, "Unknown direction")
        change["direction"] = body.direction
    row.body = change
    row.source = "confirmed"
    await db.commit()
    return await _meaning_out(db, j, source, _language(lang))


# ── shared: model work in the background ────────────────────────────────────

#: Background jobs running in this process, by tag, so one is never started twice.
_running: set[str] = set()


async def _background(db: AsyncSession, user: User, tag: str, job, on_error=None) -> None:
    """Run `job(session)` detached, metered against the user's org.

    The pattern of the Understand step: a model may take minutes or be down,
    so the request answers at once and the page asks again while `pending`."""
    import asyncio
    import logging
    from ..core.database import AsyncSessionLocal
    from ..services import quotas

    if tag in _running:
        return
    _running.add(tag)
    meter = await quotas.open_ai_meter(db, user.org_id, user.id, "setup")

    async def run():
        try:
            async with AsyncSessionLocal() as session:
                await job(session)
        except Exception:                                   # noqa: BLE001
            logging.getLogger(__name__).exception("guided setup: background job %s failed", tag)
            # Record the failure on a fresh session: a job that died (even while
            # saving) must not stay "pending", or every visit restarts it.
            if on_error is not None:
                try:
                    async with AsyncSessionLocal() as session:
                        await on_error(session)
                except Exception:                           # noqa: BLE001
                    logging.getLogger(__name__).exception("guided setup: recording failure of %s failed", tag)
        finally:
            _running.discard(tag)

    asyncio.create_task(quotas.run_metered(AsyncSessionLocal, meter, run()))


def _failer(flow_id: int, column: str, attempt: str, *, key: str | None = None, item: str | None = None,
            flag: str | None = None):
    """An on_error hook: mark one attempt failed in a flow's `column`
    (proposals, designs, demand, findings[key]) -- or one item's `flag` --
    unless a newer attempt replaced it meanwhile."""
    async def mark(session: AsyncSession) -> None:
        f = await session.get(SetupFlow, flow_id)
        if f is None:
            return
        state = dict(getattr(f, column) or {})
        if item is not None:
            items = list(state.get("items") or [])
            failed_key = {"refining": "refine_failed", "changing": "change_failed"}[flag]
            state["items"] = [{**{k: v for k, v in it.items() if k != flag}, failed_key: "failed"}
                              if it.get("id") == item and it.get(flag) == attempt else it for it in items]
        elif key is not None:
            entry = dict(state.get(key) or {})
            if entry.get("attempt") != attempt:
                return
            state[key] = {**{k: v for k, v in entry.items() if k != "pending"}, "failed": "failed"}
        else:
            if state.get("attempt") != attempt:
                return
            state = {**{k: v for k, v in state.items() if k != "pending"}, "failed": "failed"}
        setattr(f, column, state)
        await session.commit()
    return mark


async def _owner(db: AsyncSession, j) -> tuple[DataSource | None, User | None]:
    """The connection and the person a journey or a flow belongs to."""
    from sqlalchemy.orm import selectinload
    source = await db.get(DataSource, j.data_source_id)
    user = (await db.execute(select(User).options(selectinload(User.role))
                             .where(User.id == j.user_id))).scalar_one_or_none()
    # "Allow AI" for this connection, applied to every model call the setup
    # makes for it from here on (services/ai_policy.py).
    from ..services import ai_policy
    await ai_policy.enter(db, source=source)
    return source, user


def _words_of(j: SetupJourney | None, lang: str) -> dict | None:
    if j is None:
        return None
    entries = _entries(j)
    return (entries.get(lang) or entries.get("en") or next(iter(entries.values()), {}) or {}).get("words")


async def _flow_words(db: AsyncSession, f: SetupFlow, lang: str) -> dict | None:
    return _words_of(await db.get(SetupJourney, f.journey_id), lang)


# ── Step 2: Choose data ─────────────────────────────────────────────────────

async def write_proposals(db: AsyncSession, flow_id: int, lang: str, attempt: str) -> None:
    from ..services.guided_setup import datasets
    from ..services.llm import get_client

    f = await db.get(SetupFlow, flow_id)
    if f is None:
        return
    source, user = await _owner(db, f)
    if source is None or user is None:
        return
    words = await _flow_words(db, f, lang)
    try:
        items, reason = await datasets.propose(db, user, source, _with_background(f.brief, user, source),
                                               words, lang, get_client())
    except Exception:                                       # noqa: BLE001
        # Never leave the step "pending": a crash recorded as pending was
        # restarted by every visit, asking the model again each time. Offer
        # the plain proposals from the facts instead.
        logger.exception("guided setup: proposing datasets failed")
        items, reason = await _plain_proposals(db, user, source, lang, words), "failed"
    await db.refresh(f)
    state = dict(f.proposals or {})
    if state.get("attempt") != attempt:
        return
    f.proposals = {"lang": lang, "attempt": attempt, "items": items,
                   "failed": reason, "at": datetime.utcnow().isoformat()}
    await db.commit()


async def _plain_proposals(db: AsyncSession, user: User, source: DataSource, lang: str,
                           words: dict | None) -> list[dict]:
    from ..services.guided_setup import datasets, understand
    from ..services.guided_setup.access import _family
    try:
        facts = await understand.load_facts(db, source)
        family = _family(source)
        out = []
        for item in datasets.fallback_items(facts, family, lang, "failed", words):
            ok = await datasets._accept(db, user, source, item, datasets.catalog_of(facts), family, None)
            if ok:
                out.append(ok)
        return out
    except Exception:                                       # noqa: BLE001
        return []


async def _existing_datasets(db: AsyncSession, user: User, source: DataSource) -> list[dict]:
    """Datasets already made from this connection that the user can read: the
    setup can adopt them instead of making new ones."""
    readable = await readable_dataset_ids(db, user)
    q = select(Dataset).where(Dataset.org_id == user.org_id, Dataset.data_source_id == source.id)
    if readable is not None:
        q = q.where(Dataset.id.in_(readable or {-1}))
    rows = (await db.execute(q.order_by(Dataset.created_at.desc()))).scalars().all()
    return [{"id": d.id, "name": d.name, "rows": getattr(d, "row_count", None),
             "mode": getattr(d, "mode", None)} for d in rows[:20]]


def _proposals_out(f: SetupFlow) -> dict:
    state = dict(f.proposals or {})
    stale = state.get("pending") and _pending_is_stale(state)
    return {"pending": bool(state.get("pending")) and not stale,
            "failed": state.get("failed"),
            "items": state.get("items") or [],
            "language": state.get("lang"),
            "asked": bool(state)}


async def _start_proposals(db: AsyncSession, user: User, f: SetupFlow, lang: str) -> None:
    import uuid
    attempt = uuid.uuid4().hex
    old = dict(f.proposals or {})
    f.proposals = {"lang": lang, "attempt": attempt, "pending": True,
                   "items": old.get("items") or [], "at": datetime.utcnow().isoformat()}
    _touch(f)
    await db.commit()

    async def job(session):
        await write_proposals(session, f.id, lang, attempt)
    await _background(db, user, f"proposals:{f.id}", job, _failer(f.id, "proposals", attempt))


@router.get("/{source_id}/datasets")
async def get_datasets_step(source_id: int, lang: str = "en", flow: int | None = None,
                            db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """The Choose data step: kept proposals, datasets already made, and whether
    this person may create datasets (importing is admin-only in this app).

    Nothing is asked of the model here: the page first offers "About you"
    (or Skip), then calls /suggest -- so the first proposals already use the
    answers. Kept proposals are served as they are."""
    source = await source_or_404(db, source_id, user)
    _j, f = await _flow(db, user, source, flow)
    lang = _language(lang)
    state = dict(f.proposals or {})
    if state.get("pending") and _pending_is_stale(state):
        await _start_proposals(db, user, f, state.get("lang") or lang)
    elif state.get("pending") and f"proposals:{f.id}" not in _running:
        # A restart dropped the job: carry on with the same attempt.
        async def job(session):
            await write_proposals(session, f.id, state.get("lang") or lang, state["attempt"])
        await _background(db, user, f"proposals:{f.id}", job, _failer(f.id, "proposals", state["attempt"]))
    return {"proposals": _proposals_out(f), "brief": f.brief or {},
            "existing": await _existing_datasets(db, user, source),
            "chosen": list(f.dataset_ids or []),
            "can_create": _may_create(user),
            "allow_ai": bool(source.allow_llm_sampling)}


@router.post("/{source_id}/datasets/suggest")
async def suggest_datasets(source_id: int, lang: str = "en", flow: int | None = None,
                           db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Ask the model again ("Suggest again", or after changing About you)."""
    source = await source_or_404(db, source_id, user)
    _j, f = await _flow(db, user, source, flow)
    await _start_proposals(db, user, f, _language(lang))
    return {"proposals": _proposals_out(f)}


class RefineIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)


async def write_refinement(db: AsyncSession, flow_id: int, pid: str, message: str,
                           lang: str, attempt: str) -> None:
    from ..services.guided_setup import datasets
    from ..services.llm import get_client

    f = await db.get(SetupFlow, flow_id)
    if f is None:
        return
    source, user = await _owner(db, f)
    items = list((f.proposals or {}).get("items") or [])
    current = next((p for p in items if p["id"] == pid), None)
    if source is None or user is None or current is None:
        return
    try:
        revised, reply = await datasets.refine(db, user, source, f.brief, await _flow_words(db, f, lang),
                                               current, message, lang, get_client())
    except Exception:                                       # noqa: BLE001
        logger.exception("guided setup: refining a dataset failed")
        revised, reply = None, "failed"
    await db.refresh(f)
    state = dict(f.proposals or {})
    items = list(state.get("items") or [])
    for i, p in enumerate(items):
        if p["id"] == pid and p.get("refining") == attempt:
            if revised is not None:
                items[i] = revised
            else:
                items[i] = {**{k: v for k, v in p.items() if k != "refining"},
                            "refine_failed": reply,
                            "history": list(p.get("history") or []) + [{"role": "user", "text": message}]}
    state["items"] = items
    f.proposals = state
    await db.commit()


@router.post("/{source_id}/datasets/{pid}/refine")
async def refine_dataset(source_id: int, pid: str, body: RefineIn, lang: str = "en", flow: int | None = None,
                         db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Change one proposal by asking in plain words ("leave out the Arabic columns")."""
    import uuid
    source = await source_or_404(db, source_id, user)
    _j, f = await _flow(db, user, source, flow)
    state = dict(f.proposals or {})
    items = list(state.get("items") or [])
    if not any(p["id"] == pid for p in items):
        raise HTTPException(404, "Proposal not found")
    attempt = uuid.uuid4().hex
    state["items"] = [{**{k: v for k, v in p.items() if k != "refine_failed"}, "refining": attempt}
                      if p["id"] == pid else p for p in items]
    f.proposals = state
    _touch(f)
    await db.commit()
    lang = _language(lang)

    async def job(session):
        await write_refinement(session, f.id, pid, body.message.strip(), lang, attempt)
    await _background(db, user, f"refine:{f.id}:{pid}", job,
                      _failer(f.id, "proposals", attempt, item=pid, flag="refining"))
    return {"proposals": _proposals_out(f)}


def _fingerprint(*parts: str) -> str:
    import hashlib
    return hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]


def _may_create(user: User) -> bool:
    """Importing from a connection is admin-only (POST /data-sources/{id}/import
    and the import job both check it); the setup does not widen that."""
    return bool(user.role and user.role.is_org_admin)


class CreateItem(BaseModel):
    id: str
    name: str = Field(..., min_length=1, max_length=255)


class CreateIn(BaseModel):
    items: list[CreateItem] = Field(..., min_length=1, max_length=5)
    mode: Literal["import", "directquery"] = "import"


@router.post("/{source_id}/datasets/create")
async def create_datasets(source_id: int, body: CreateIn, flow: int | None = None,
                          db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Make the chosen proposals into datasets, through the app's own import.

    A copy ("import") is queued as a durable job -- the page polls
    GET /jobs/{id}, whose `result.dataset_id` is the dataset; an idempotency
    key per flow and proposal makes a double click one import. A live
    dataset ("directquery") copies nothing and is made at once."""
    from ..schemas.schemas import ImportRequest
    from ..services import jobs as job_service
    from ..services.source_import import IMPORT_JOB_KIND, ImportRefused, import_from_source, job_inputs

    source = await source_or_404(db, source_id, user)
    if not _may_create(user):
        raise HTTPException(403, "Only an admin can create datasets from a connection")
    _j, f = await _flow(db, user, source, flow)
    state = dict(f.proposals or {})
    items = {p["id"]: p for p in state.get("items") or []}
    out, made_as = [], {}
    for item in body.items:
        p = items.get(item.id)
        name = item.name.strip()
        if p is None:
            out.append({"proposal_id": item.id, "name": name, "job_id": None, "dataset_id": None,
                        "error": "This suggestion is no longer available"})
            continue
        made_as[item.id] = name
        req = ImportRequest(dataset_name=name, query=p["sql"], mode=body.mode)
        if body.mode == "directquery":
            try:
                made = await import_from_source(db, user, source, req)
                out.append({"proposal_id": item.id, "name": name, "job_id": None,
                            "dataset_id": made["id"], "error": None})
            except ImportRefused as e:
                out.append({"proposal_id": item.id, "name": name, "job_id": None, "dataset_id": None,
                            "error": str(e)})
            continue
        job, _ = await job_service.enqueue(
            db, user=user, kind=IMPORT_JOB_KIND, inputs=job_inputs(source.id, req),
            subject=f"{source.name} · {name}",
            # The query's fingerprint is in the key: a proposal changed in the
            # chat and created again is a new import, not a conflict.
            idempotency_key=f"setup:f{f.id}:{item.id}:{_fingerprint(p['sql'], name)}")
        out.append({"proposal_id": item.id, "name": name, "job_id": job.id, "dataset_id": None, "error": None})
    if made_as:
        # Which suggestion a dataset was made from: what it was proposed FOR,
        # and what the person typed while choosing it, is part of what they want.
        await db.refresh(f)
        state = dict(f.proposals or {})
        state["items"] = [{**p, "made_as": made_as[p["id"]]} if p["id"] in made_as else p
                          for p in state.get("items") or []]
        f.proposals = state
        _touch(f)
        await db.commit()
    return {"items": out}


# ── the Demand: what the person wants, written once and checked ─────────────

async def _journey_datasets(db: AsyncSession, user: User, f: SetupFlow) -> list[Dataset]:
    readable = await readable_dataset_ids(db, user)
    out = []
    for dsid in f.dataset_ids or []:
        ds = await db.get(Dataset, dsid)
        if ds is not None and ds.org_id == user.org_id and (readable is None or ds.id in readable):
            out.append(ds)
    return out


async def build_demand(db: AsyncSession, f: SetupFlow, user: User, lang: str, edits: list[str],
                       earlier: dict | None = None) -> dict:
    """The Demand for a flow's datasets, read as its owner (decision D1)."""
    from ..services import alerts
    from ..services.guided_setup import demand
    from ..services.llm import get_client

    source = await db.get(DataSource, f.data_source_id)
    made = {p.get("made_as"): p for p in (f.proposals or {}).get("items") or [] if p.get("made_as")}
    frames = []
    for ds in (await _journey_datasets(db, user, f))[:3]:
        try:
            frame = await alerts.alert_frame(db, ds, user)
        except Exception:                                   # noqa: BLE001
            logger.exception("guided setup: reading dataset %s for the demand failed", ds.id)
            continue
        frames.append({"id": ds.id, "name": ds.name, "frame": frame, "proposal": made.get(ds.name)})
    await access.release(db)
    client = get_client() if source is not None and source.allow_llm_sampling else None
    got = await demand.write(_with_background(f.brief, user, source), frames, edits, lang, client, earlier)
    # A dataset that holds events but not what they are counted against can
    # show counts and never rates (docs/meaning-map/PLAN.md): said to the
    # person before a dashboard is designed on it.
    from ..services.guided_setup import meaning
    m = await meaning.load(db, f.data_source_id)
    # "Only the returned ones", on a dataset that keeps every row with the
    # column saying what became of it: that is an OUTCOME to measure over all
    # the rows -- its count, its share, the share per group -- not a part of
    # the data to narrow the dashboard to (which would leave no base).
    outcome_columns = {o["column"] for o in m.outcomes}
    got["outcomes"] = [s for s in got.get("scope") or []
                       if s.get("status") == "in_dashboard" and s.get("column") in outcome_columns]
    got["scope"] = [s for s in got.get("scope") or [] if s not in got["outcomes"]]
    got["base_missing"] = [{"dataset_id": d["id"], "events": b["events"], "base": b["base"]}
                           for d in frames for b in m.events_without_base((d.get("proposal") or {}).get("tables") or [])]
    return got


async def write_demand(db: AsyncSession, flow_id: int, lang: str, attempt: str) -> None:
    f = await db.get(SetupFlow, flow_id)
    if f is None:
        return
    _source, user = await _owner(db, f)
    if user is None:
        return
    old = dict(f.demand or {})
    edits = list(old.get("edits") or [])
    got = await build_demand(db, f, user, lang, edits, old if old.get("sentence") and edits else None)
    await db.refresh(f)
    state = dict(f.demand or {})
    if state.get("attempt") != attempt:
        return
    f.demand = {**got, "lang": lang, "attempt": attempt, "edits": list(state.get("edits") or edits),
                "at": datetime.utcnow().isoformat()}
    await db.commit()


async def _start_demand(db: AsyncSession, user: User, f: SetupFlow, lang: str, edit: str | None = None) -> None:
    import uuid
    attempt = uuid.uuid4().hex
    old = dict(f.demand or {})
    edits = list(old.get("edits") or []) + ([edit] if edit else [])
    f.demand = {**{k: v for k, v in old.items() if k != "failed"}, "lang": lang, "attempt": attempt,
                "pending": True, "edits": edits, "at": datetime.utcnow().isoformat()}
    _touch(f)
    await db.commit()

    async def job(session):
        await write_demand(session, f.id, lang, attempt)
    await _background(db, user, f"demand:{f.id}", job, _failer(f.id, "demand", attempt))


async def _ensure_demand(db: AsyncSession, user: User, f: SetupFlow, lang: str) -> None:
    """Start writing the Demand the first time a step needs it; carry on an
    attempt a restart dropped. Written once, kept until the person changes it."""
    state = dict(f.demand or {})
    if not f.dataset_ids:
        return
    if not state or (state.get("pending") and _pending_is_stale(state)):
        await _start_demand(db, user, f, lang)
    elif state.get("pending") and f"demand:{f.id}" not in _running:
        async def job(session):
            await write_demand(session, f.id, state.get("lang") or lang, state["attempt"])
        await _background(db, user, f"demand:{f.id}", job, _failer(f.id, "demand", state["attempt"]))


def _demand_out(f: SetupFlow) -> dict:
    state = dict(f.demand or {})
    stale = state.get("pending") and _pending_is_stale(state)
    return {"pending": bool(state.get("pending")) and not stale, "failed": state.get("failed"),
            "written": bool(state.get("sentence")), "sentence": state.get("sentence") or "",
            "who": state.get("who") or "", "subject": state.get("subject") or "",
            "questions": state.get("questions") or [], "exclude": state.get("exclude") or [],
            "scope": state.get("scope") or [], "source": state.get("source"),
            "edits": state.get("edits") or [], "language": state.get("lang"),
            "base_missing": state.get("base_missing") or []}


@router.get("/{source_id}/demand")
async def get_demand(source_id: int, lang: str = "en", flow: int | None = None,
                     db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """What this analysis is for, as the setup understood it."""
    source = await source_or_404(db, source_id, user)
    _j, f = await _flow(db, user, source, flow)
    await _ensure_demand(db, user, f, _language(lang))
    return {"demand": _demand_out(f)}


@router.post("/{source_id}/demand/change")
async def change_demand(source_id: int, body: RefineIn, lang: str = "en", flow: int | None = None,
                        db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """The person corrects what was understood ("I meant 4x4, and only since
    2020"). The correction wins over everything said before; dashboards
    designed for the old request are dropped, so the next visit designs for
    the new one."""
    source = await source_or_404(db, source_id, user)
    _j, f = await _flow(db, user, source, flow)
    if not f.dataset_ids:
        raise HTTPException(400, "Choose data first")
    f.designs = None
    await _start_demand(db, user, f, _language(lang), body.message.strip())
    return {"demand": _demand_out(f)}


# ── Step 3: Check & discover ────────────────────────────────────────────────

def _said_columns(f: SetupFlow, df) -> set[str]:
    """Columns the person named in their own words: never left out for them."""
    text = " ".join(str(v) for v in (f.brief or {}).values() if v).casefold()
    for p in (f.proposals or {}).get("items") or []:
        text += " " + " ".join(m.get("text", "") for m in p.get("history") or []).casefold()
    return {str(c) for c in df.columns
            if len(str(c)) >= 3 and str(c).replace("_", " ").casefold() in text}


async def _check_one(db: AsyncSession, user: User, ds: Dataset, f: SetupFlow, lang: str) -> tuple[dict, dict]:
    """(findings, cleaning) for one dataset, read as `user`.

    The check, then the automatic fixes for what it found (only on a dataset
    this flow made; cleaning.py), then the insights -- on the cleaned rows, so
    what the person reads and what the dashboard draws are the same data."""
    import asyncio
    from ..core.capability import require_dataset_read
    from ..services import alerts
    from ..services.data_quality import quality_report
    from ..services.guided_setup import cleaning, health
    from ..services.llm import get_client
    from ..services.prep import prep_steps_of
    from .datasets import dataset_insights, set_prep_steps

    await require_dataset_read(db, user, ds.id)
    from ..services import ai_policy
    await ai_policy.enter(db, datasets=[ds])
    brief = f.brief
    df = await alerts.alert_frame(db, ds, user)
    await access.release(db)
    report = await asyncio.to_thread(quality_report, df)
    client = get_client()
    # Each column classified once and kept (services/column_classes.py): the
    # check reads what a column IS from there, like every other engine.
    from ..services import column_classes
    classes = await column_classes.ensure(db, ds, df)
    await access.release(db)
    items = health.column_items(report, df, lang, classes)
    items += health.generic_rules(df, lang, skip={i["column"] for i in items if i["kind"] == "placeholder"},
                                  column_meta=classes)
    try:
        # A rule that only re-finds what a plain check already found (the same
        # rows, one of the same columns) is said once.
        known = {(i.get("column"), i.get("rows")) for i in items if i.get("kind") in ("negative", "placeholder")}
        items += [r for r in await health.model_rules(df, brief, lang, client, classes)
                  if not any((c.strip(), r.get("rows")) in known for c in str(r.get("column") or "").split(","))]
    except Exception:                                       # noqa: BLE001
        logger.exception("guided setup: model rules failed for dataset %s", ds.id)

    state = dict((f.cleaning or {}).get(str(ds.id)) or {})
    actions = list(state.get("actions") or [])
    undone = set(state.get("undone") or [])
    rows_before = state.get("rows_before") if state.get("rows_before") is not None else int(len(df))
    if ds.id in (f.created_ids or []) and ds.mode != "directquery":
        new = cleaning.plan(items, lang, undone=undone, protect=_said_columns(f, df), rows=int(len(df)))
        applied = []
        if new:
            try:
                await set_prep_steps(ds.id, cleaning.steps_with(list(prep_steps_of(ds)), new), db, user)
                applied = new
            except HTTPException:
                # One step the dataset refuses must not cost the others.
                for a in new:
                    try:
                        await db.refresh(ds)
                        await set_prep_steps(ds.id, cleaning.steps_with(list(prep_steps_of(ds)), [a]), db, user)
                        applied.append(a)
                    except HTTPException:
                        logger.info("guided setup: automatic fix %s refused on dataset %s", a["key"], ds.id)
        if applied:
            done = {a["key"] for a in applied}
            items = [i for i in items if cleaning.key_of(i) not in done]
            actions += applied
            await db.refresh(ds)
            df = await alerts.alert_frame(db, ds, user)
            await access.release(db)
    cleaned = {"actions": actions, "undone": sorted(undone), "rows_before": rows_before,
               "rows_after": int(len(df))}
    if not items:
        items = [health.good_item(df, lang)]
    insights: list[dict] = []
    try:
        scan = await dataset_insights(ds.id, db, user, None)
        await access.release(db)
        from ..services.semantic_guard import recorded_number
        kinds = {str(c): recorded_number(str(c), classes) for c in df.columns}
        found = [x for x in scan.get("findings") or []
                 if health.beyond_size(x, df) and health.totals_mean_something(x, df, kinds)]
        insights = await health.plain_insights(found, brief, lang, client)
    except Exception:                                       # noqa: BLE001
        logger.exception("guided setup: insights failed for dataset %s", ds.id)
    return ({"health": items, "insights": insights, "rows": int(len(df)), "columns": int(len(df.columns))},
            cleaned)


async def write_findings(db: AsyncSession, flow_id: int, dataset_id: int, lang: str, attempt: str) -> None:
    f = await db.get(SetupFlow, flow_id)
    ds = await db.get(Dataset, dataset_id)
    if f is None or ds is None:
        return
    _source, user = await _owner(db, f)
    if user is None:
        return
    cleaned = None
    try:
        (result, cleaned), failed = await _check_one(db, user, ds, f, lang), None
    except HTTPException as e:
        result, failed = {}, str(e.detail)
    except Exception:                                       # noqa: BLE001
        logger.exception("guided setup: checking dataset %s failed", dataset_id)
        result, failed = {}, "failed"
    await db.refresh(f)
    state = dict(f.findings or {})
    entry = dict(state.get(str(dataset_id)) or {})
    if cleaned is not None:
        # Kept even when a newer check replaced this one: the prep steps exist.
        f.cleaning = {**dict(f.cleaning or {}), str(dataset_id): cleaned}
    if entry.get("attempt") == attempt:
        state[str(dataset_id)] = {"attempt": attempt, "lang": lang, **result, "failed": failed,
                                  "fixed": [], "at": datetime.utcnow().isoformat()}
        f.findings = state
    await db.commit()


async def _start_check(db: AsyncSession, user: User, f: SetupFlow, dataset_id: int, lang: str) -> None:
    import uuid
    attempt = uuid.uuid4().hex
    state = dict(f.findings or {})
    old = dict(state.get(str(dataset_id)) or {})
    state[str(dataset_id)] = {**{k: v for k, v in old.items() if k in ("health", "insights", "rows", "columns")},
                              "attempt": attempt, "pending": True, "lang": lang,
                              "fixed": old.get("fixed") or [], "at": datetime.utcnow().isoformat()}
    f.findings = state
    _touch(f)
    await db.commit()

    async def job(session):
        await write_findings(session, f.id, dataset_id, lang, attempt)
    await _background(db, user, f"check:{f.id}:{dataset_id}", job,
                      _failer(f.id, "findings", attempt, key=str(dataset_id)))


def _finding_out(entry: dict, cleaned: dict | None = None) -> dict:
    from ..services.guided_setup import cleaning
    stale = entry.get("pending") and _pending_is_stale(entry)
    health_items = entry.get("health") or []
    return {"pending": bool(entry.get("pending")) and not stale, "failed": entry.get("failed"),
            "health": health_items, "insights": entry.get("insights") or [],
            "rows": entry.get("rows"), "columns": entry.get("columns"),
            "fixed": entry.get("fixed") or [], "language": entry.get("lang"), "checked": bool(entry),
            "cleaning": {**cleaning.summary(cleaned, health_items),
                         "actions": [{k: a.get(k) for k in ("id", "said", "ai", "state", "kind", "column", "rows")}
                                     for a in (cleaned or {}).get("actions") or []]}}


def _finding_of(f: SetupFlow, dataset_id: int) -> dict:
    return _finding_out(dict((f.findings or {}).get(str(dataset_id)) or {}),
                        (f.cleaning or {}).get(str(dataset_id)))


@router.get("/{source_id}/check")
async def get_check_step(source_id: int, lang: str = "en", flow: int | None = None,
                         db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Check & discover: per chosen dataset, what was fixed for the person,
    the plain health lines and insights -- and what the setup understood they
    want. The first visit checks each dataset once; results are kept until
    "Check again"."""
    source = await source_or_404(db, source_id, user)
    _j, f = await _flow(db, user, source, flow)
    lang = _language(lang)
    await _ensure_demand(db, user, f, lang)
    out = []
    for ds in await _journey_datasets(db, user, f):
        entry = dict((f.findings or {}).get(str(ds.id)) or {})
        if not entry or (entry.get("pending") and _pending_is_stale(entry)):
            await _start_check(db, user, f, ds.id, lang)
        elif entry.get("pending") and f"check:{f.id}:{ds.id}" not in _running:
            async def job(session, dsid=ds.id, attempt=entry["attempt"], lg=entry.get("lang") or lang):
                await write_findings(session, f.id, dsid, lg, attempt)
            await _background(db, user, f"check:{f.id}:{ds.id}", job,
                              _failer(f.id, "findings", entry["attempt"], key=str(ds.id)))
        out.append({"id": ds.id, "name": ds.name, "mode": ds.mode, "row_count": ds.row_count,
                    "auto_clean": ds.id in (f.created_ids or []) and ds.mode != "directquery",
                    "findings": _finding_of(f, ds.id)})
    # The pages are designed while the person reads this step: by the time they
    # press Next the dashboard is usually ready (PLAN_V2 4f). Once, like any
    # other design: only when nothing was designed yet.
    done = bool(out) and all(d["findings"]["checked"] and not d["findings"]["pending"] for d in out)
    if done and (f.demand or {}).get("sentence") and not (f.demand or {}).get("pending") and not f.designs:
        await _start_designs(db, user, f, lang)
    return {"datasets": out, "demand": _demand_out(f)}


@router.post("/{source_id}/check/{dataset_id}/run")
async def run_check(source_id: int, dataset_id: int, lang: str = "en", flow: int | None = None,
                    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Check one dataset again ("Check again", or after a fix)."""
    source = await source_or_404(db, source_id, user)
    _j, f = await _flow(db, user, source, flow)
    if dataset_id not in [d.id for d in await _journey_datasets(db, user, f)]:
        raise HTTPException(404, "Dataset not found")
    await _start_check(db, user, f, dataset_id, _language(lang))
    return {"findings": _finding_of(f, dataset_id)}


class FixIn(BaseModel):
    item_id: str
    #: "fix" applies the line's action; "check" saves its rule as a warning check.
    how: Literal["fix", "check"] = "fix"


@router.post("/{source_id}/check/{dataset_id}/fix")
async def fix_item(source_id: int, dataset_id: int, body: FixIn, lang: str = "en", flow: int | None = None,
                   db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Apply one "Fix it": a prep step on the dataset (through the dataset's
    own prep route, so its permission and validation apply), or a saved check."""
    from ..services.guided_setup import health
    from ..services.prep import prep_steps_of
    source = await source_or_404(db, source_id, user)
    _j, f = await _flow(db, user, source, flow)
    ds = next((d for d in await _journey_datasets(db, user, f) if d.id == dataset_id), None)
    entry = dict((f.findings or {}).get(str(dataset_id)) or {})
    item = next((i for i in entry.get("health") or [] if i["id"] == body.item_id), None)
    if ds is None or item is None or not item.get("action"):
        raise HTTPException(404, "Nothing to fix here")
    action = item["action"]
    if body.how == "check":
        from ..schemas.schemas import DataCheckIn
        from .datasets import create_data_check
        rule = action.get("rule")
        if not rule:
            raise HTTPException(400, "This line has no rule to check")
        await create_data_check(ds.id, DataCheckIn(kind="rule", params={"expression": rule}, severity="warn"),
                                db, user)
    else:
        from .datasets import set_prep_steps
        step = health.prep_step_for(action, _language(lang))
        if step is None:
            raise HTTPException(400, "This line cannot be fixed automatically")
        await set_prep_steps(ds.id, list(prep_steps_of(ds)) + [step], db, user)
    await db.refresh(f)
    state = dict(f.findings or {})
    entry = dict(state.get(str(dataset_id)) or {})
    entry["fixed"] = list(dict.fromkeys((entry.get("fixed") or []) + [f"{body.item_id}|{body.how}"]))
    state[str(dataset_id)] = entry
    f.findings = state
    await db.commit()
    return {"findings": _finding_of(f, dataset_id)}


class UndoIn(BaseModel):
    #: One automatic fix; None means all of them.
    action_id: str | None = None
    #: True puts a fix that was taken back in place again.
    redo: bool = False


@router.post("/{source_id}/check/{dataset_id}/undo")
async def undo_fix(source_id: int, dataset_id: int, body: UndoIn, flow: int | None = None,
                   db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Take back an automatic fix (or all of them), or put one back.

    Removes exactly the prep steps the setup added -- through the dataset's own
    prep route, so its permission and validation apply -- and remembers the
    choice: "Check again" never re-applies what the person undid. The finding
    returns to the list with its "Fix it" button."""
    from ..services.guided_setup import cleaning
    from ..services.prep import prep_steps_of
    from .datasets import set_prep_steps
    source = await source_or_404(db, source_id, user)
    _j, f = await _flow(db, user, source, flow)
    ds = next((d for d in await _journey_datasets(db, user, f) if d.id == dataset_id), None)
    state = dict((f.cleaning or {}).get(str(dataset_id)) or {})
    actions = [dict(a) for a in state.get("actions") or []]
    want = "undone" if body.redo else "applied"
    chosen = [a for a in actions if a.get("state") == want and body.action_id in (None, a["id"])]
    if ds is None or not chosen:
        raise HTTPException(404, "Nothing to undo here")
    steps = list(prep_steps_of(ds))
    ids = {a["id"] for a in chosen}
    steps = cleaning.steps_with(steps, chosen) if body.redo else cleaning.steps_without(steps, ids)
    await set_prep_steps(ds.id, steps, db, user)
    await db.refresh(f)
    undone = set(state.get("undone") or [])
    for a in actions:
        if a["id"] in ids:
            a["state"] = "applied" if body.redo else "undone"
            (undone.discard if body.redo else undone.add)(a["key"])
    findings = dict(f.findings or {})
    entry = dict(findings.get(str(dataset_id)) or {})
    back = {cleaning.key_of(a["item"]): a["item"] for a in chosen if a.get("item")}
    health_items = [i for i in entry.get("health") or [] if i.get("kind") != "good"]
    if body.redo:
        health_items = [i for i in health_items if cleaning.key_of(i) not in back]
    else:
        have = {cleaning.key_of(i) for i in health_items}
        health_items = [it for k, it in back.items() if k not in have] + health_items
    entry["health"] = health_items or entry.get("health") or []
    findings[str(dataset_id)] = entry
    f.findings = findings
    try:
        from ..services import alerts
        rows_after = int(len(await alerts.alert_frame(db, ds, user)))
    except Exception:                                       # noqa: BLE001
        rows_after = state.get("rows_after")
    f.cleaning = {**dict(f.cleaning or {}), str(dataset_id): {**state, "actions": actions,
                                                              "undone": sorted(undone), "rows_after": rows_after}}
    # The dashboards were designed on other rows: design again on the next visit.
    if not f.report_id:
        f.designs = None
    _touch(f)
    await db.commit()
    return {"findings": _finding_of(f, dataset_id)}


@router.get("/findings/{dataset_id}")
async def findings_for_dataset(dataset_id: int, db: AsyncSession = Depends(get_db),
                               user: User = Depends(get_current_user)):
    """The latest setup findings for a dataset, for the plain summaries on the
    dataset, quality and Insights pages (plan phase 5). Only the caller's own
    analyses, and only a dataset they can read."""
    from ..core.capability import require_dataset_read
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, user, "Dataset not found")
    await require_dataset_read(db, user, dataset_id)
    rows = (await db.execute(select(SetupFlow).where(
        SetupFlow.user_id == user.id, SetupFlow.org_id == user.org_id)
        .order_by(SetupFlow.updated_at.desc()))).scalars().all()
    for f in rows:
        entry = (f.findings or {}).get(str(dataset_id))
        if entry and not entry.get("pending") and (entry.get("health") or entry.get("insights")):
            return {"findings": _finding_of(f, dataset_id), "source_id": f.data_source_id, "flow_id": f.id}
    return {"findings": None, "source_id": None, "flow_id": None}


# ── Step 4: Dashboard ───────────────────────────────────────────────────────

async def _plain_design(db: AsyncSession, user: User, ds: Dataset, f: SetupFlow, count: int) -> list[dict]:
    """Without a model: the app's statistics designer, narrowed to what the
    person asked for. No goal is passed, so it never waits on a model."""
    from ..schemas.schemas import SuggestDashboardsRequest
    from ..services.guided_setup import answer, demand
    from .datasets import suggest_dashboards
    got = await suggest_dashboards(ds.id, SuggestDashboardsRequest(goal=None, count=count, mode="quick", use_profile=False),
                                   db, user, None)
    filters = demand.filters_for(f.demand, ds.id)
    out = []
    for p in (got.get("proposals") or [])[:count]:
        widgets = list(p.get("widgets") or [])
        if widgets:
            out.append({**p, "widgets": widgets, "answer": "", "unanswered": [], "answers": [],
                        "scope_filters": filters})
    return out


async def write_designs(db: AsyncSession, flow_id: int, lang: str, attempt: str) -> None:
    import uuid
    from ..services.guided_setup import answer
    from ..services.llm import get_client
    f = await db.get(SetupFlow, flow_id)
    if f is None:
        return
    source, user = await _owner(db, f)
    if user is None:
        return
    # The dashboard is designed FOR the Demand: written first when a visitor
    # reached this step before it was.
    if not (f.demand or {}).get("sentence"):
        got = await build_demand(db, f, user, lang, list((f.demand or {}).get("edits") or []))
        await db.refresh(f)
        if not (f.demand or {}).get("sentence"):
            f.demand = {**got, "lang": lang, "attempt": (f.demand or {}).get("attempt") or uuid.uuid4().hex,
                        "edits": list((f.demand or {}).get("edits") or []), "at": datetime.utcnow().isoformat()}
            await db.commit()
    dem = dict(f.demand or {})
    datasets_ = await _journey_datasets(db, user, f)
    count = 3 if len(datasets_) <= 1 else 2
    client = get_client() if source is not None and source.allow_llm_sampling else None
    from ..services.guided_setup import meaning
    m = await meaning.load(db, f.data_source_id)
    tables_of = {p.get("made_as"): p.get("tables") for p in (f.proposals or {}).get("items") or [] if p.get("made_as")}
    items, failed = [], None
    for ds in datasets_[:3]:
        entry = (f.findings or {}).get(str(ds.id))
        proposals: list[dict] = []
        derived: dict = {}
        try:
            await access.release(db)
            got = await answer.design(db, user, ds, dem, entry, lang, count, client,
                                      meaning_map=m, tables=tables_of.get(ds.name))
            proposals, derived = got["proposals"], got.get("derived") or {}
        except HTTPException as e:
            failed = str(e.detail)
        except Exception:                                   # noqa: BLE001
            logger.exception("guided setup: designing for dataset %s failed", ds.id)
            failed = "failed"
        if not proposals:
            try:
                await access.release(db)
                proposals = await _plain_design(db, user, ds, f, count)
            except Exception:                               # noqa: BLE001
                logger.exception("guided setup: the plain design for dataset %s failed", ds.id)
        for p in proposals:
            items.append({"id": uuid.uuid4().hex[:10], "dataset_id": ds.id, "dataset_name": ds.name,
                          "proposal": p, "derived": derived, "history": []})
    await db.refresh(f)
    state = dict(f.designs or {})
    if state.get("attempt") != attempt:
        return
    f.designs = {"lang": lang, "attempt": attempt, "items": items, "used": [],
                 "failed": None if items else (failed or "none"), "at": datetime.utcnow().isoformat()}
    await db.commit()


def _designs_out(f: SetupFlow) -> dict:
    state = dict(f.designs or {})
    stale = state.get("pending") and _pending_is_stale(state)
    return {"pending": bool(state.get("pending")) and not stale, "failed": state.get("failed"),
            "items": state.get("items") or [], "asked": bool(state), "report_id": f.report_id,
            "used": state.get("used") or [], "language": state.get("lang")}


async def _start_designs(db: AsyncSession, user: User, f: SetupFlow, lang: str) -> None:
    import uuid
    attempt = uuid.uuid4().hex
    old = dict(f.designs or {})
    f.designs = {"lang": lang, "attempt": attempt, "pending": True, "items": old.get("items") or [],
                 "used": old.get("used") or [], "at": datetime.utcnow().isoformat()}
    _touch(f)
    await db.commit()

    async def job(session):
        await write_designs(session, f.id, lang, attempt)
    await _background(db, user, f"designs:{f.id}", job, _failer(f.id, "designs", attempt))


@router.get("/{source_id}/dashboard")
async def get_dashboard_step(source_id: int, lang: str = "en", flow: int | None = None,
                             db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """The Dashboard step: pages proposed for what the person wants, designed
    once and kept until "Suggest again". The first visit starts the design."""
    source = await source_or_404(db, source_id, user)
    _j, f = await _flow(db, user, source, flow)
    lang = _language(lang)
    state = dict(f.designs or {})
    datasets_ = await _journey_datasets(db, user, f)
    demand_pending = bool((f.demand or {}).get("pending")) and not _pending_is_stale(f.demand or {})
    if datasets_ and not demand_pending and (not state or (state.get("pending") and _pending_is_stale(state))):
        await _start_designs(db, user, f, lang)
    elif state.get("pending") and f"designs:{f.id}" not in _running:
        async def job(session):
            await write_designs(session, f.id, state.get("lang") or lang, state["attempt"])
        await _background(db, user, f"designs:{f.id}", job, _failer(f.id, "designs", state["attempt"]))
    out = _designs_out(f)
    if demand_pending and not state:
        out["pending"] = True             # the request is being rewritten; the design follows it
    return {"designs": out, "has_data": bool(datasets_), "demand": _demand_out(f),
            "datasets": [{"id": d.id, "name": d.name} for d in datasets_]}


@router.post("/{source_id}/dashboard/suggest")
async def suggest_designs(source_id: int, lang: str = "en", flow: int | None = None,
                          db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    source = await source_or_404(db, source_id, user)
    _j, f = await _flow(db, user, source, flow)
    await _start_designs(db, user, f, _language(lang))
    return {"designs": _designs_out(f)}


class UsedIn(BaseModel):
    report_id: int
    design_ids: list[str] = Field(default_factory=list, max_length=20)


@router.post("/{source_id}/dashboard/used")
async def designs_used(source_id: int, body: UsedIn, flow: int | None = None,
                       db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """The person made (or added pages to) this flow's dashboard from these
    designs: one dashboard per flow, each chosen design a page of it."""
    source = await source_or_404(db, source_id, user)
    j, f = await _flow(db, user, source, flow)
    check_org(await db.get(Report, body.report_id), user, "Dashboard not found")
    f.report_id = body.report_id
    f.step = "done"
    if j.step == "understand":
        j.step = "data"
    state = dict(f.designs or {})
    state["used"] = list(dict.fromkeys((state.get("used") or []) + body.design_ids))
    f.designs = state
    _touch(f)
    await db.commit()
    return _out(j, source, await _flows(db, j), f)


async def write_design_change(db: AsyncSession, flow_id: int, did: str, message: str,
                              lang: str, attempt: str) -> None:
    from ..services.guided_setup import answer
    from ..services.llm import get_client
    f = await db.get(SetupFlow, flow_id)
    if f is None:
        return
    source, user = await _owner(db, f)
    items = list((f.designs or {}).get("items") or [])
    current = next((d for d in items if d["id"] == did), None)
    ds = await db.get(Dataset, current["dataset_id"]) if current else None
    if user is None or current is None or ds is None:
        return
    new = None
    try:
        client = get_client() if source is not None and source.allow_llm_sampling else None
        await access.release(db)
        from ..services.guided_setup import meaning
        tables_of = {p.get("made_as"): p.get("tables") for p in (f.proposals or {}).get("items") or []
                     if p.get("made_as")}
        new = await answer.change(db, user, ds, dict(f.demand or {}), (f.findings or {}).get(str(ds.id)),
                                  current["proposal"], message, lang, client,
                                  meaning_map=await meaning.load(db, f.data_source_id),
                                  tables=tables_of.get(ds.name))
    except Exception:                                       # noqa: BLE001
        logger.exception("guided setup: changing a dashboard failed")
    await db.refresh(f)
    state = dict(f.designs or {})
    items = list(state.get("items") or [])
    for i, d in enumerate(items):
        if d["id"] == did and d.get("changing") == attempt:
            history = list(d.get("history") or []) + [{"role": "user", "text": message}]
            if new is not None:
                more = new.pop("_derived", None) or {}
                have = {c.get("name") for c in (d.get("derived") or {}).get("calculated_columns") or []}
                cols = list((d.get("derived") or {}).get("calculated_columns") or []) + [
                    c for c in more.get("calculated_columns") or [] if c.get("name") not in have]
                items[i] = {**{k: v for k, v in d.items() if k not in ("changing", "change_failed")},
                            "proposal": new, "history": history,
                            "derived": {"measures": [], "calculated_columns": cols}}
            else:
                items[i] = {**{k: v for k, v in d.items() if k != "changing"},
                            "change_failed": "failed", "history": history}
    state["items"] = items
    f.designs = state
    await db.commit()


@router.post("/{source_id}/dashboard/{did}/refine")
async def refine_design(source_id: int, did: str, body: RefineIn, lang: str = "en", flow: int | None = None,
                        db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Change one proposed page by asking in plain words; charts the person
    did not mention stay as they are."""
    import uuid
    source = await source_or_404(db, source_id, user)
    _j, f = await _flow(db, user, source, flow)
    state = dict(f.designs or {})
    items = list(state.get("items") or [])
    if not any(d["id"] == did for d in items):
        raise HTTPException(404, "Proposal not found")
    attempt = uuid.uuid4().hex
    state["items"] = [{**{k: v for k, v in d.items() if k != "change_failed"}, "changing": attempt}
                      if d["id"] == did else d for d in items]
    f.designs = state
    _touch(f)
    await db.commit()
    lang = _language(lang)

    async def job(session):
        await write_design_change(session, f.id, did, body.message.strip(), lang, attempt)
    await _background(db, user, f"design:{f.id}:{did}", job,
                      _failer(f.id, "designs", attempt, item=did, flag="changing"))
    return {"designs": _designs_out(f)}


# ── Phase 5: plain health for ANY dataset (uploads too), fast, no model ─────

@router.get("/datasets/{dataset_id}/health")
async def dataset_health(dataset_id: int, lang: str = "en", db: AsyncSession = Depends(get_db),
                         user: User = Depends(get_current_user)):
    """What to know about a dataset, in plain words, for its own pages.

    The quality report and the generic rules only -- seconds, no model -- so
    it works for an uploaded file as well as a connection's dataset. The
    guided setup's richer findings (model rules, insights) are served by
    /setup/findings/{id} when the person ran the setup."""
    import asyncio
    from ..core.capability import require_dataset_read
    from ..services import alerts
    from ..services.data_quality import quality_report
    from ..services.guided_setup import health
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, user, "Dataset not found")
    await require_dataset_read(db, user, dataset_id)
    lang = _language(lang)
    try:
        df = await alerts.alert_frame(db, ds, user)
    except Exception:                                       # noqa: BLE001
        raise HTTPException(400, "This dataset could not be read")
    report = await asyncio.to_thread(quality_report, df)
    items = health.column_items(report, df, lang)
    items += health.generic_rules(df, lang, skip={i["column"] for i in items if i["kind"] == "placeholder"})
    if not items:
        items = [health.good_item(df, lang)]
    return {"health": items, "insights": [], "rows": int(len(df)), "columns": int(len(df.columns)),
            "pending": False, "failed": None, "fixed": [], "language": lang, "checked": True}


class ActionIn(BaseModel):
    action: dict


@router.post("/datasets/{dataset_id}/fix")
async def dataset_fix(dataset_id: int, body: ActionIn, lang: str = "en", db: AsyncSession = Depends(get_db),
                      user: User = Depends(get_current_user)):
    """Apply a health line's action on a dataset page. Goes through the
    dataset's own prep-steps route, so its permission check and validation
    decide -- exactly as if the person had added the step by hand."""
    from ..services.guided_setup import health
    from ..services.prep import prep_steps_of
    from .datasets import set_prep_steps
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, user, "Dataset not found")
    step = health.prep_step_for(body.action, _language(lang))
    if step is None:
        raise HTTPException(400, "This line cannot be fixed automatically")
    return {"steps": await set_prep_steps(ds.id, list(prep_steps_of(ds)) + [step], db, user)}


# ── Change the data behind a dataset (2026-10-08) ───────────────────────────

async def _changeable(db: AsyncSession, user: User, dataset_id: int) -> tuple[Dataset, DataSource | None, str | None]:
    """(dataset, its connection, why it cannot be changed here -- or None)."""
    from sqlalchemy.orm import selectinload
    from ..core.capability import require_dataset_read
    ds = (await db.execute(select(Dataset).options(selectinload(Dataset.columns))
                           .where(Dataset.id == dataset_id))).scalar_one_or_none()
    check_org(ds, user, "Dataset not found")
    await require_dataset_read(db, user, dataset_id)
    if not ds.data_source_id or not (ds.source_query or ds.source_table):
        return ds, None, "not_from_connection"
    source = await access.visible_source(db, ds.data_source_id, user)
    if source is None:
        return ds, None, "not_from_connection"
    if ds.mode != "import":
        return ds, source, "live"
    if not _may_create(user):
        return ds, source, "admin_only"
    try:
        from ..core.capability import require_dataset_capability
        await require_dataset_capability(db, user, dataset_id, "data")
    except HTTPException:
        return ds, source, "no_edit"
    return ds, source, None


@router.get("/datasets/{dataset_id}/change")
async def change_options(dataset_id: int, db: AsyncSession = Depends(get_db),
                         user: User = Depends(get_current_user)):
    """What can be added to this dataset: its source table's other columns,
    and whether the AI may help."""
    from ..services.guided_setup import change
    ds, source, why = await _changeable(db, user, dataset_id)
    return {"can_change": why is None, "reason": why,
            "columns": [c.name for c in ds.columns],
            "addable": await change.addable(db, source, ds) if source is not None else [],
            "allow_ai": bool(source and source.allow_llm_sampling),
            "source": {"id": source.id, "name": source.name} if source else None}


class ChangePreviewIn(BaseModel):
    add: list[str] | None = Field(None, max_length=50)
    message: str | None = Field(None, max_length=1000)


@router.post("/datasets/{dataset_id}/change/preview")
async def change_preview(dataset_id: int, body: ChangePreviewIn, lang: str = "en",
                         db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """The changed query, what it adds and removes, and a preview run as the person."""
    from ..services.guided_setup import change
    from ..services.llm import get_client
    ds, source, why = await _changeable(db, user, dataset_id)
    if why is not None:
        raise HTTPException(403 if why in ("admin_only", "no_edit") else 400, why)
    from ..services import ai_policy
    await ai_policy.enter(db, datasets=[ds], source=source)
    return await change.preview(db, user, source, ds, add=body.add, message=(body.message or "").strip() or None,
                                lang=_language(lang), client=get_client())


class ChangeApplyIn(BaseModel):
    sql: str = Field(..., min_length=1, max_length=20000)


@router.post("/datasets/{dataset_id}/change/apply")
async def change_apply(dataset_id: int, body: ChangeApplyIn, db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user)):
    """Re-import the dataset IN PLACE with the changed query (same id, so its
    dashboards keep working). Checked again here: one read over this
    connection's catalog, run as the person, and nothing in use removed."""
    from ..schemas.schemas import ImportRequest
    from ..services import jobs as job_service
    from ..services.guided_setup import change, datasets, understand
    from ..services.source_import import IMPORT_JOB_KIND, job_inputs
    ds, source, why = await _changeable(db, user, dataset_id)
    if why is not None:
        raise HTTPException(403 if why in ("admin_only", "no_edit") else 400, why)
    facts = await understand.load_facts(db, source)
    clean, problem = datasets.check_sql(body.sql, access._family(source), datasets.catalog_of(facts))
    if clean is None:
        raise HTTPException(400, problem)
    run = await datasets.test_run(db, user, source, clean)
    if run["error"]:
        raise HTTPException(400, run["error"])
    removes = [c.name for c in ds.columns if c.name not in run["columns"]]
    blocked = await change.blocked_removals(db, ds, removes)
    if blocked:
        raise HTTPException(409, {"message": "This change removes columns your dashboards use",
                                  "blocked": blocked})
    req = ImportRequest(dataset_name=ds.name, query=clean, mode="import", dataset_id=ds.id)
    job, _ = await job_service.enqueue(
        db, user=user, kind=IMPORT_JOB_KIND, inputs=job_inputs(source.id, req),
        subject=f"{source.name} · {ds.name} (changed)",
        idempotency_key=f"change:{ds.id}:{_fingerprint(clean)}")
    return {"job_id": job.id}
