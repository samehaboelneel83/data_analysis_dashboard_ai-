"""Guided setup: connect -> understand -> choose data -> check & discover -> dashboard.

docs/guided-setup/PLAN.md. A journey is per person and connection, so two
people setting up the same database each keep their own place and their own
"About you" answers. Every route reads the connection with the caller's own
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
from ..models.models import DataSource, Dataset, Report, SetupJourney, SourceObject, User
from ..services.guided_setup import access

logger = __import__("logging").getLogger(__name__)

router = APIRouter(prefix="/setup", tags=["guided-setup"])

#: The four steps the progress bar shows, in order; "done" follows the last.
STEPS = ("understand", "data", "check", "dashboard")
Step = Literal["understand", "data", "check", "dashboard", "done"]

#: Longest answer kept per "About you" field: hints for a prompt, not documents.
BRIEF_FIELD_MAX = 1000


class Brief(BaseModel):
    """About you -- every field optional; hints for the model, never rules."""
    work: str | None = Field(None, max_length=BRIEF_FIELD_MAX)
    focus: str | None = Field(None, max_length=BRIEF_FIELD_MAX)
    questions: str | None = Field(None, max_length=BRIEF_FIELD_MAX)
    exclude: str | None = Field(None, max_length=BRIEF_FIELD_MAX)


class JourneyUpdate(BaseModel):
    step: Step | None = None
    brief: Brief | None = None
    dataset_ids: list[int] | None = None
    report_id: int | None = None


async def source_or_404(db: AsyncSession, source_id: int, user: User) -> DataSource:
    """The connection if this user may SEE it (the Connections list's rule)."""
    source = await access.visible_source(db, source_id, user)
    if source is None:
        raise HTTPException(404, "Data source not found")
    return source


def _out(j: SetupJourney, source: DataSource) -> dict:
    position = STEPS.index(j.step) + 1 if j.step in STEPS else len(STEPS)
    return {
        "id": j.id,
        "source": {"id": source.id, "name": source.name, "type": source.type},
        "step": j.step,
        "position": position,
        "total": len(STEPS),
        "brief": j.brief or {},
        "dataset_ids": list(j.dataset_ids or []),
        "report_id": j.report_id,
        "updated_at": j.updated_at.isoformat() if j.updated_at else None,
    }


async def _journey(db: AsyncSession, user: User, source: DataSource) -> SetupJourney | None:
    return (await db.execute(select(SetupJourney).where(
        SetupJourney.user_id == user.id,
        SetupJourney.data_source_id == source.id))).scalar_one_or_none()


@router.get("/journeys")
async def my_journeys(db: AsyncSession = Depends(get_db),
                      user: User = Depends(get_current_user)):
    """My unfinished setups, newest first: what Home offers to continue.

    A journey on a connection I can no longer see is left out, not shown."""
    rows = (await db.execute(
        select(SetupJourney, DataSource)
        .join(DataSource, DataSource.id == SetupJourney.data_source_id)
        .where(SetupJourney.user_id == user.id, SetupJourney.org_id == user.org_id,
               SetupJourney.step != "done")
        .order_by(SetupJourney.updated_at.desc(), SetupJourney.id.desc()))).all()
    visible = await access.visible_source_ids(db, user)
    return [_out(j, s) for j, s in rows if visible is None or s.id in visible]


async def _journey_or_start(db: AsyncSession, user: User, source: DataSource) -> SetupJourney:
    j = await _journey(db, user, source)
    if j is None:
        j = SetupJourney(org_id=user.org_id, user_id=user.id, data_source_id=source.id,
                         step="understand", created_at=datetime.utcnow(), updated_at=datetime.utcnow())
        db.add(j)
        await db.commit()
        await db.refresh(j)
    return j


@router.get("/{source_id}")
async def get_journey(source_id: int, db: AsyncSession = Depends(get_db),
                      user: User = Depends(get_current_user)):
    """My setup of this connection, started on first visit."""
    source = await source_or_404(db, source_id, user)
    return _out(await _journey_or_start(db, user, source), source)


@router.patch("/{source_id}")
async def update_journey(source_id: int, body: JourneyUpdate, db: AsyncSession = Depends(get_db),
                         user: User = Depends(get_current_user)):
    source = await source_or_404(db, source_id, user)
    j = await _journey(db, user, source)
    if j is None:
        raise HTTPException(404, "Setup not started")
    if body.step is not None:
        j.step = body.step
    if body.brief is not None:
        # Blank answers are dropped, so "not answered" and "answered empty" read the same.
        j.brief = {k: v.strip() for k, v in body.brief.model_dump().items() if v and v.strip()}
    if body.dataset_ids is not None:
        ids = list(dict.fromkeys(body.dataset_ids))
        if ids:
            readable = await readable_dataset_ids(db, user)
            found = set((await db.execute(select(Dataset.id).where(
                Dataset.id.in_(ids), Dataset.org_id == user.org_id))).scalars().all())
            if set(ids) - found or (readable is not None and set(ids) - readable):
                raise HTTPException(404, "Dataset not found")
        j.dataset_ids = ids
    if "report_id" in body.model_fields_set:
        if body.report_id is not None:
            check_org(await db.get(Report, body.report_id), user, "Dashboard not found")
        j.report_id = body.report_id
    j.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(j)
    return _out(j, source)


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
    return kept.get("values") if kept.get("sync") == stamp else None


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


def _failer(journey_id: int, column: str, attempt: str, *, key: str | None = None, item: str | None = None,
            flag: str | None = None):
    """An on_error hook: mark one attempt failed in `column` (proposals,
    designs, findings[key], summary[key]) -- or one item's `flag` -- unless a
    newer attempt replaced it meanwhile."""
    async def mark(session: AsyncSession) -> None:
        j = await session.get(SetupJourney, journey_id)
        if j is None:
            return
        state = dict(getattr(j, column) or {})
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
        setattr(j, column, state)
        await session.commit()
    return mark


async def _owner(db: AsyncSession, j: SetupJourney) -> tuple[DataSource | None, User | None]:
    from sqlalchemy.orm import selectinload
    source = await db.get(DataSource, j.data_source_id)
    user = (await db.execute(select(User).options(selectinload(User.role))
                             .where(User.id == j.user_id))).scalar_one_or_none()
    return source, user


def _words_of(j: SetupJourney, lang: str) -> dict | None:
    entries = _entries(j)
    return (entries.get(lang) or entries.get("en") or next(iter(entries.values()), {}) or {}).get("words")


# ── Step 2: Choose data ─────────────────────────────────────────────────────

async def write_proposals(db: AsyncSession, journey_id: int, lang: str, attempt: str) -> None:
    from ..services.guided_setup import datasets
    from ..services.llm import get_client

    j = await db.get(SetupJourney, journey_id)
    if j is None:
        return
    source, user = await _owner(db, j)
    if source is None or user is None:
        return
    try:
        items, reason = await datasets.propose(db, user, source, j.brief, _words_of(j, lang), lang, get_client())
    except Exception:                                       # noqa: BLE001
        # Never leave the step "pending": a crash recorded as pending was
        # restarted by every visit, asking the model again each time. Offer
        # the plain proposals from the facts instead.
        import logging
        logging.getLogger(__name__).exception("guided setup: proposing datasets failed")
        items, reason = await _plain_proposals(db, user, source, lang, _words_of(j, lang)), "failed"
    await db.refresh(j)
    state = dict(j.proposals or {})
    if state.get("attempt") != attempt:
        return
    j.proposals = {"lang": lang, "attempt": attempt, "items": items,
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


def _proposals_out(j: SetupJourney) -> dict:
    state = dict(j.proposals or {})
    stale = state.get("pending") and _pending_is_stale(state)
    return {"pending": bool(state.get("pending")) and not stale,
            "failed": state.get("failed"),
            "items": state.get("items") or [],
            "language": state.get("lang"),
            "asked": bool(state)}


async def _start_proposals(db: AsyncSession, user: User, j: SetupJourney, lang: str) -> None:
    import uuid
    attempt = uuid.uuid4().hex
    old = dict(j.proposals or {})
    j.proposals = {"lang": lang, "attempt": attempt, "pending": True,
                   "items": old.get("items") or [], "at": datetime.utcnow().isoformat()}
    await db.commit()

    async def job(session):
        await write_proposals(session, j.id, lang, attempt)
    await _background(db, user, f"proposals:{j.id}", job, _failer(j.id, "proposals", attempt))


@router.get("/{source_id}/datasets")
async def get_datasets_step(source_id: int, lang: str = "en", db: AsyncSession = Depends(get_db),
                            user: User = Depends(get_current_user)):
    """The Choose data step: kept proposals, datasets already made, and whether
    this person may create datasets (importing is admin-only in this app).

    Nothing is asked of the model here: the page first offers "About you"
    (or Skip), then calls /suggest -- so the first proposals already use the
    answers. Kept proposals are served as they are."""
    source = await source_or_404(db, source_id, user)
    j = await _journey_or_start(db, user, source)
    lang = _language(lang)
    state = dict(j.proposals or {})
    if state.get("pending") and _pending_is_stale(state):
        await _start_proposals(db, user, j, state.get("lang") or lang)
    elif state.get("pending") and f"proposals:{j.id}" not in _running:
        # A restart dropped the job: carry on with the same attempt.
        async def job(session):
            await write_proposals(session, j.id, state.get("lang") or lang, state["attempt"])
        await _background(db, user, f"proposals:{j.id}", job, _failer(j.id, "proposals", state["attempt"]))
    return {"proposals": _proposals_out(j), "brief": j.brief or {},
            "existing": await _existing_datasets(db, user, source),
            "chosen": list(j.dataset_ids or []),
            "can_create": _may_create(user),
            "allow_ai": bool(source.allow_llm_sampling)}


@router.post("/{source_id}/datasets/suggest")
async def suggest_datasets(source_id: int, lang: str = "en", db: AsyncSession = Depends(get_db),
                           user: User = Depends(get_current_user)):
    """Ask the model again ("Suggest again", or after changing About you)."""
    source = await source_or_404(db, source_id, user)
    j = await _journey_or_start(db, user, source)
    await _start_proposals(db, user, j, _language(lang))
    return {"proposals": _proposals_out(j)}


class RefineIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)


async def write_refinement(db: AsyncSession, journey_id: int, pid: str, message: str,
                           lang: str, attempt: str) -> None:
    from ..services.guided_setup import datasets
    from ..services.llm import get_client

    j = await db.get(SetupJourney, journey_id)
    if j is None:
        return
    source, user = await _owner(db, j)
    items = list((j.proposals or {}).get("items") or [])
    current = next((p for p in items if p["id"] == pid), None)
    if source is None or user is None or current is None:
        return
    try:
        revised, reply = await datasets.refine(db, user, source, j.brief, _words_of(j, lang),
                                               current, message, lang, get_client())
    except Exception:                                       # noqa: BLE001
        import logging
        logging.getLogger(__name__).exception("guided setup: refining a dataset failed")
        revised, reply = None, "failed"
    await db.refresh(j)
    state = dict(j.proposals or {})
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
    j.proposals = state
    await db.commit()


@router.post("/{source_id}/datasets/{pid}/refine")
async def refine_dataset(source_id: int, pid: str, body: RefineIn, lang: str = "en",
                         db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Change one proposal by asking in plain words ("leave out the Arabic columns")."""
    import uuid
    source = await source_or_404(db, source_id, user)
    j = await _journey_or_start(db, user, source)
    state = dict(j.proposals or {})
    items = list(state.get("items") or [])
    if not any(p["id"] == pid for p in items):
        raise HTTPException(404, "Proposal not found")
    attempt = uuid.uuid4().hex
    state["items"] = [{**{k: v for k, v in p.items() if k != "refine_failed"}, "refining": attempt}
                      if p["id"] == pid else p for p in items]
    j.proposals = state
    await db.commit()
    lang = _language(lang)

    async def job(session):
        await write_refinement(session, j.id, pid, body.message.strip(), lang, attempt)
    await _background(db, user, f"refine:{j.id}:{pid}", job,
                      _failer(j.id, "proposals", attempt, item=pid, flag="refining"))
    return {"proposals": _proposals_out(j)}


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
async def create_datasets(source_id: int, body: CreateIn, db: AsyncSession = Depends(get_db),
                          user: User = Depends(get_current_user)):
    """Make the chosen proposals into datasets, through the app's own import.

    A copy ("import") is queued as a durable job -- the page polls
    GET /jobs/{id}, whose `result.dataset_id` is the dataset; an idempotency
    key per journey and proposal makes a double click one import. A live
    dataset ("directquery") copies nothing and is made at once."""
    from ..schemas.schemas import ImportRequest
    from ..services import jobs as job_service
    from ..services.source_import import IMPORT_JOB_KIND, ImportRefused, import_from_source, job_inputs

    source = await source_or_404(db, source_id, user)
    if not _may_create(user):
        raise HTTPException(403, "Only an admin can create datasets from a connection")
    j = await _journey_or_start(db, user, source)
    items = {p["id"]: p for p in (j.proposals or {}).get("items") or []}
    out = []
    for item in body.items:
        p = items.get(item.id)
        name = item.name.strip()
        if p is None:
            out.append({"proposal_id": item.id, "name": name, "job_id": None, "dataset_id": None,
                        "error": "This suggestion is no longer available"})
            continue
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
            idempotency_key=f"setup:{j.id}:{item.id}:{_fingerprint(p['sql'], name)}")
        out.append({"proposal_id": item.id, "name": name, "job_id": job.id, "dataset_id": None, "error": None})
    return {"items": out}


# ── Step 3: Check & discover ────────────────────────────────────────────────

async def _check_one(db: AsyncSession, user: User, ds: Dataset, brief: dict | None, lang: str) -> dict:
    """Health lines and plain insights for one dataset, read as `user`."""
    import asyncio
    from ..core.capability import require_dataset_read
    from ..services import alerts
    from ..services.data_quality import quality_report
    from ..services.guided_setup import health
    from ..services.llm import get_client
    from .datasets import dataset_insights

    await require_dataset_read(db, user, ds.id)
    df = await alerts.alert_frame(db, ds, user)
    await access.release(db)
    report = await asyncio.to_thread(quality_report, df)
    client = get_client()
    items = health.column_items(report, df, lang)
    items += health.generic_rules(df, lang, skip={i["column"] for i in items if i["kind"] == "placeholder"})
    try:
        items += await health.model_rules(df, brief, lang, client)
    except Exception:                                       # noqa: BLE001
        logger.exception("guided setup: model rules failed for dataset %s", ds.id)
    if not items:
        items = [health.good_item(df, lang)]
    insights: list[dict] = []
    try:
        scan = await dataset_insights(ds.id, db, user, None)
        await access.release(db)
        insights = await health.plain_insights(scan.get("findings") or [], brief, lang, client)
    except Exception:                                       # noqa: BLE001
        logger.exception("guided setup: insights failed for dataset %s", ds.id)
    return {"health": items, "insights": insights, "rows": int(len(df)), "columns": int(len(df.columns))}


async def write_findings(db: AsyncSession, journey_id: int, dataset_id: int, lang: str, attempt: str) -> None:
    j = await db.get(SetupJourney, journey_id)
    ds = await db.get(Dataset, dataset_id)
    if j is None or ds is None:
        return
    _source, user = await _owner(db, j)
    if user is None:
        return
    try:
        result, failed = await _check_one(db, user, ds, j.brief, lang), None
    except HTTPException as e:
        result, failed = {}, str(e.detail)
    except Exception:                                       # noqa: BLE001
        logger.exception("guided setup: checking dataset %s failed", dataset_id)
        result, failed = {}, "failed"
    await db.refresh(j)
    state = dict(j.findings or {})
    entry = dict(state.get(str(dataset_id)) or {})
    if entry.get("attempt") != attempt:
        return
    state[str(dataset_id)] = {"attempt": attempt, "lang": lang, **result, "failed": failed,
                              "fixed": [], "at": datetime.utcnow().isoformat()}
    j.findings = state
    await db.commit()



async def _start_check(db: AsyncSession, user: User, j: SetupJourney, dataset_id: int, lang: str) -> None:
    import uuid
    attempt = uuid.uuid4().hex
    state = dict(j.findings or {})
    old = dict(state.get(str(dataset_id)) or {})
    state[str(dataset_id)] = {**{k: v for k, v in old.items() if k in ("health", "insights", "rows", "columns")},
                              "attempt": attempt, "pending": True, "lang": lang,
                              "fixed": old.get("fixed") or [], "at": datetime.utcnow().isoformat()}
    j.findings = state
    await db.commit()

    async def job(session):
        await write_findings(session, j.id, dataset_id, lang, attempt)
    await _background(db, user, f"check:{j.id}:{dataset_id}", job,
                      _failer(j.id, "findings", attempt, key=str(dataset_id)))


def _finding_out(entry: dict) -> dict:
    stale = entry.get("pending") and _pending_is_stale(entry)
    return {"pending": bool(entry.get("pending")) and not stale, "failed": entry.get("failed"),
            "health": entry.get("health") or [], "insights": entry.get("insights") or [],
            "rows": entry.get("rows"), "columns": entry.get("columns"),
            "fixed": entry.get("fixed") or [], "language": entry.get("lang"), "checked": bool(entry)}


async def _journey_datasets(db: AsyncSession, user: User, j: SetupJourney) -> list[Dataset]:
    readable = await readable_dataset_ids(db, user)
    out = []
    for dsid in j.dataset_ids or []:
        ds = await db.get(Dataset, dsid)
        if ds is not None and ds.org_id == user.org_id and (readable is None or ds.id in readable):
            out.append(ds)
    return out


@router.get("/{source_id}/check")
async def get_check_step(source_id: int, lang: str = "en", db: AsyncSession = Depends(get_db),
                         user: User = Depends(get_current_user)):
    """Check & discover: per chosen dataset, the plain health lines and
    insights. The first visit checks each dataset once; results are kept
    until "Check again"."""
    source = await source_or_404(db, source_id, user)
    j = await _journey_or_start(db, user, source)
    lang = _language(lang)
    out = []
    for ds in await _journey_datasets(db, user, j):
        entry = dict((j.findings or {}).get(str(ds.id)) or {})
        if not entry or (entry.get("pending") and _pending_is_stale(entry)):
            await _start_check(db, user, j, ds.id, lang)
            entry = dict((j.findings or {}).get(str(ds.id)) or {})
        elif entry.get("pending") and f"check:{j.id}:{ds.id}" not in _running:
            async def job(session, dsid=ds.id, attempt=entry["attempt"], lg=entry.get("lang") or lang):
                await write_findings(session, j.id, dsid, lg, attempt)
            await _background(db, user, f"check:{j.id}:{ds.id}", job,
                              _failer(j.id, "findings", entry["attempt"], key=str(ds.id)))
        out.append({"id": ds.id, "name": ds.name, "mode": ds.mode, "row_count": ds.row_count,
                    "findings": _finding_out(entry)})
    return {"datasets": out}


@router.post("/{source_id}/check/{dataset_id}/run")
async def run_check(source_id: int, dataset_id: int, lang: str = "en", db: AsyncSession = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """Check one dataset again ("Check again", or after a fix)."""
    source = await source_or_404(db, source_id, user)
    j = await _journey_or_start(db, user, source)
    if dataset_id not in [d.id for d in await _journey_datasets(db, user, j)]:
        raise HTTPException(404, "Dataset not found")
    await _start_check(db, user, j, dataset_id, _language(lang))
    return {"findings": _finding_out(dict(j.findings[str(dataset_id)]))}


class FixIn(BaseModel):
    item_id: str
    #: "fix" applies the line's action; "check" saves its rule as a warning check.
    how: Literal["fix", "check"] = "fix"


@router.post("/{source_id}/check/{dataset_id}/fix")
async def fix_item(source_id: int, dataset_id: int, body: FixIn, lang: str = "en",
                   db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Apply one "Fix it": a prep step on the dataset (through the dataset's
    own prep route, so its permission and validation apply), or a saved check."""
    from ..services.guided_setup import health
    from ..services.prep import prep_steps_of
    source = await source_or_404(db, source_id, user)
    j = await _journey_or_start(db, user, source)
    ds = next((d for d in await _journey_datasets(db, user, j) if d.id == dataset_id), None)
    entry = dict((j.findings or {}).get(str(dataset_id)) or {})
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
    await db.refresh(j)
    state = dict(j.findings or {})
    entry = dict(state.get(str(dataset_id)) or {})
    entry["fixed"] = list(dict.fromkeys((entry.get("fixed") or []) + [f"{body.item_id}|{body.how}"]))
    state[str(dataset_id)] = entry
    j.findings = state
    await db.commit()
    return {"findings": _finding_out(entry)}


@router.get("/findings/{dataset_id}")
async def findings_for_dataset(dataset_id: int, db: AsyncSession = Depends(get_db),
                               user: User = Depends(get_current_user)):
    """The latest setup findings for a dataset, for the plain summaries on the
    dataset, quality and Insights pages (plan phase 5). Only the caller's own
    journeys, and only a dataset they can read."""
    from ..core.capability import require_dataset_read
    ds = await db.get(Dataset, dataset_id)
    check_org(ds, user, "Dataset not found")
    await require_dataset_read(db, user, dataset_id)
    rows = (await db.execute(select(SetupJourney).where(
        SetupJourney.user_id == user.id, SetupJourney.org_id == user.org_id)
        .order_by(SetupJourney.updated_at.desc()))).scalars().all()
    for j in rows:
        entry = (j.findings or {}).get(str(dataset_id))
        if entry and not entry.get("pending") and (entry.get("health") or entry.get("insights")):
            return {"findings": _finding_out(dict(entry)), "source_id": j.data_source_id}
    return {"findings": None, "source_id": None}


# ── Step 4: Dashboard ───────────────────────────────────────────────────────

#: The designer's goal box holds this much (SuggestDashboardsRequest.goal).
GOAL_MAX = 2000


def design_goal(brief: dict | None, entry: dict | None, ask: str | None = None) -> str | None:
    """What the designer is told: who the person is, what they want to know,
    and what the Check & discover step found -- so charts avoid the data's
    problems and start from what already stands out. None when there is
    nothing to say (the designer then uses its statistics engine)."""
    b = brief or {}
    parts = []
    for label, key in (("Who they are", "work"), ("Focus on", "focus"),
                       ("They want to know", "questions"), ("Leave out", "exclude")):
        if b.get(key):
            parts.append(f"{label}: {b[key]}")
    health = [i for i in (entry or {}).get("health") or [] if i.get("tone") in ("problem", "warning", "info")]
    if health:
        parts.append("Data notes -- avoid charts these would mislead, prefer medians over averages where "
                     "values are extreme, and do not chart mostly-empty columns:\n"
                     + "\n".join(f"- {i['what']}" for i in health[:6]))
    insights = (entry or {}).get("insights") or []
    if insights:
        parts.append("Already found in this data (worth a chart):\n"
                     + "\n".join(f"- {i['what']}" for i in insights[:4]))
    if parts:
        # The model otherwise calls market listings "my inventory" (live run 2026-10-07).
        parts.append("Describe the data as what it is; never call it the person's own stock, "
                     "clients or records unless they said so.")
    if ask:
        parts.append(ask)
    text = "\n".join(parts).strip()
    return text[:GOAL_MAX] if text else None


async def _design_for(db: AsyncSession, user: User, ds: Dataset, goal: str | None, count: int) -> dict:
    from ..schemas.schemas import SuggestDashboardsRequest
    from .datasets import suggest_dashboards
    return await suggest_dashboards(ds.id, SuggestDashboardsRequest(goal=goal, count=count, mode="quick"),
                                    db, user, None)


async def write_designs(db: AsyncSession, journey_id: int, lang: str, attempt: str) -> None:
    import uuid
    j = await db.get(SetupJourney, journey_id)
    if j is None:
        return
    _source, user = await _owner(db, j)
    if user is None:
        return
    datasets_ = await _journey_datasets(db, user, j)
    count = 3 if len(datasets_) <= 1 else 2
    items, failed = [], None
    for ds in datasets_[:3]:
        goal = design_goal(j.brief, (j.findings or {}).get(str(ds.id)),
                           "Write titles in Arabic." if lang == "ar" else None)
        try:
            await access.release(db)
            got = await _design_for(db, user, ds, goal, count)
        except HTTPException as e:
            failed = str(e.detail)
            continue
        except Exception:                                   # noqa: BLE001
            logger.exception("guided setup: designing for dataset %s failed", ds.id)
            failed = "failed"
            continue
        for p in got.get("proposals") or []:
            if p.get("widgets"):
                items.append({"id": uuid.uuid4().hex[:10], "dataset_id": ds.id, "dataset_name": ds.name,
                              "proposal": p, "derived": got.get("derived") or {}, "goal": goal,
                              "history": []})
    await db.refresh(j)
    state = dict(j.designs or {})
    if state.get("attempt") != attempt:
        return
    j.designs = {"lang": lang, "attempt": attempt, "items": items,
                 "failed": None if items else (failed or "none"), "at": datetime.utcnow().isoformat()}
    await db.commit()


def _designs_out(j: SetupJourney) -> dict:
    state = dict(j.designs or {})
    stale = state.get("pending") and _pending_is_stale(state)
    return {"pending": bool(state.get("pending")) and not stale, "failed": state.get("failed"),
            "items": state.get("items") or [], "asked": bool(state), "report_id": j.report_id,
            "language": state.get("lang")}


async def _start_designs(db: AsyncSession, user: User, j: SetupJourney, lang: str) -> None:
    import uuid
    attempt = uuid.uuid4().hex
    old = dict(j.designs or {})
    j.designs = {"lang": lang, "attempt": attempt, "pending": True, "items": old.get("items") or [],
                 "at": datetime.utcnow().isoformat()}
    await db.commit()

    async def job(session):
        await write_designs(session, j.id, lang, attempt)
    await _background(db, user, f"designs:{j.id}", job, _failer(j.id, "designs", attempt))


@router.get("/{source_id}/dashboard")
async def get_dashboard_step(source_id: int, lang: str = "en", db: AsyncSession = Depends(get_db),
                             user: User = Depends(get_current_user)):
    """The Dashboard step: proposed dashboards, designed once and kept until
    "Suggest again". The first visit starts the design."""
    source = await source_or_404(db, source_id, user)
    j = await _journey_or_start(db, user, source)
    lang = _language(lang)
    state = dict(j.designs or {})
    has_data = bool(await _journey_datasets(db, user, j))
    if has_data and (not state or (state.get("pending") and _pending_is_stale(state))):
        await _start_designs(db, user, j, lang)
    elif state.get("pending") and f"designs:{j.id}" not in _running:
        async def job(session):
            await write_designs(session, j.id, state.get("lang") or lang, state["attempt"])
        await _background(db, user, f"designs:{j.id}", job, _failer(j.id, "designs", state["attempt"]))
    return {"designs": _designs_out(j), "has_data": has_data,
            "datasets": [{"id": d.id, "name": d.name} for d in await _journey_datasets(db, user, j)]}


@router.post("/{source_id}/dashboard/suggest")
async def suggest_designs(source_id: int, lang: str = "en", db: AsyncSession = Depends(get_db),
                          user: User = Depends(get_current_user)):
    source = await source_or_404(db, source_id, user)
    j = await _journey_or_start(db, user, source)
    await _start_designs(db, user, j, _language(lang))
    return {"designs": _designs_out(j)}


async def write_design_change(db: AsyncSession, journey_id: int, did: str, message: str,
                              lang: str, attempt: str) -> None:
    j = await db.get(SetupJourney, journey_id)
    if j is None:
        return
    _source, user = await _owner(db, j)
    items = list((j.designs or {}).get("items") or [])
    current = next((d for d in items if d["id"] == did), None)
    ds = await db.get(Dataset, current["dataset_id"]) if current else None
    if user is None or current is None or ds is None:
        return
    titles = ", ".join(w.get("title") or w.get("widget_type") for w in current["proposal"].get("widgets") or [])
    ask = (f"Change this proposed dashboard, titled \"{current['proposal'].get('title')}\" (charts: {titles}), "
           f"as the person asks, keeping the rest: {message}")
    reply, new = "failed", None
    try:
        got = await _design_for(db, user, ds, design_goal(j.brief, (j.findings or {}).get(str(ds.id)), ask), 1)
        props = [p for p in got.get("proposals") or [] if p.get("widgets")]
        if props:
            new, reply = props[0], "ok"
            derived = got.get("derived") or {}
    except Exception:                                       # noqa: BLE001
        logger.exception("guided setup: changing a dashboard failed")
    await db.refresh(j)
    state = dict(j.designs or {})
    items = list(state.get("items") or [])
    for i, d in enumerate(items):
        if d["id"] == did and d.get("changing") == attempt:
            history = list(d.get("history") or []) + [{"role": "user", "text": message}]
            if new is not None:
                items[i] = {**{k: v for k, v in d.items() if k not in ("changing", "change_failed")},
                            "proposal": new, "derived": derived, "history": history}
            else:
                items[i] = {**{k: v for k, v in d.items() if k != "changing"},
                            "change_failed": reply, "history": history}
    state["items"] = items
    j.designs = state
    await db.commit()


@router.post("/{source_id}/dashboard/{did}/refine")
async def refine_design(source_id: int, did: str, body: RefineIn, lang: str = "en",
                        db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Change one proposed dashboard by asking in plain words."""
    import uuid
    source = await source_or_404(db, source_id, user)
    j = await _journey_or_start(db, user, source)
    state = dict(j.designs or {})
    items = list(state.get("items") or [])
    if not any(d["id"] == did for d in items):
        raise HTTPException(404, "Proposal not found")
    attempt = uuid.uuid4().hex
    state["items"] = [{**{k: v for k, v in d.items() if k != "change_failed"}, "changing": attempt}
                      if d["id"] == did else d for d in items]
    j.designs = state
    await db.commit()
    lang = _language(lang)

    async def job(session):
        await write_design_change(session, j.id, did, body.message.strip(), lang, attempt)
    await _background(db, user, f"design:{j.id}:{did}", job,
                      _failer(j.id, "designs", attempt, item=did, flag="changing"))
    return {"designs": _designs_out(j)}


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
