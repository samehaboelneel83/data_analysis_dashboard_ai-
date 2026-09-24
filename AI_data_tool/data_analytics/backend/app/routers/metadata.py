"""Layer 1 API — metadata sync, review, and column statistics.

Three groups of routes:

  sync    trigger the six-stage pipeline and watch it run
  review  see what inference proposed, and confirm or reject it
  stats   read column_stats, including top_k

The stats route earns its place independently of any AI work: `top_k` is a real
list of a column's actual values, so a filter UI can offer a dropdown of what is
really there instead of a free-text box a user has to guess into.

Org scoping uses the project's existing `check_org`, which raises 404 rather
than 403 — "doesn't exist" and "exists but isn't yours" have to stay
indistinguishable, or the error code itself leaks the catalog.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import AsyncSessionLocal, get_db
from ..core.org_scope import check_org
from ..dependencies import get_current_user, require_org_admin
from ..models.models import (ColumnStats, Dataset, DataSource, DatasetColumn,
                             Entity, GlossaryTerm, Relationship, SchemaVersion,
                             SourceColumn, SourceObject, SourceRelationship,
                             SyncRun, User)
from ..services import llm as llm_service
from ..services.metadata import cache as cache_module
from ..services.metadata import store, sync

router = APIRouter(prefix="/data-sources", tags=["metadata"])

#: A column with more distinct values than this is not an enumeration a human
#: should be hand-labelling through this form -- see T2's describe-stage
#: eligibility cap (ColumnStats.top_k <= 12), kept generous here since a human
#: edit is a deliberate act, not an LLM guess.
MAX_ENUM_LABELS = 24


class ConfirmRequest(BaseModel):
    """What the review UI sends back.

    Both lists are optional so the UI can confirm relationships and edit column
    descriptions independently, in whichever order the user works.
    """
    relationship_ids: list[int] = Field(default_factory=list)
    rejected_relationship_ids: list[int] = Field(default_factory=list)
    column_updates: list[dict] = Field(default_factory=list)
    object_updates: list[dict] = Field(default_factory=list)


async def _get_source(db: AsyncSession, source_id: int, user: User) -> DataSource:
    source = await db.get(DataSource, source_id)
    check_org(source, user, "Data source not found")
    return source


# ── sync ────────────────────────────────────────────────────────────────────

@router.post("/{source_id}/sync")
async def trigger_sync(
    source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_org_admin),
):
    """Run the metadata pipeline against one source.

    Admin-gated: a sync reads schema and samples across every table of a
    connection, which is more than a report author should be able to trigger.

    Refuses rather than queues when another sync holds the lock. Queueing would
    let a user hammering the button stack up identical runs, and the honest
    answer — "one is already going" — is more useful than a queue position.
    """
    source = await _get_source(db, source_id, current_user)

    # The live-sampling path needs the connection config. Assembled here, the
    # same way every other router that opens a connection does it, so credential
    # handling stays out of the pipeline.
    cfg = dict(source.config or {})
    cfg["type"] = source.type

    # A run already in flight? Answer immediately rather than queueing — the
    # honest "one is already going" is more useful than a queue position, and a
    # user hammering the button cannot stack up identical runs.
    active = await sync.find_active_run(db, source.id)
    if active is not None:
        raise HTTPException(409, "A sync is already running for this data source")

    # Create the row and commit it BEFORE starting the work, so the response can
    # hand back an id the client polls while the stages are still running.
    run = SyncRun(
        data_source_id=source.id, org_id=current_user.org_id,
        trigger="manual", status="running", stages=[],
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    # Detached from this request: the sync outlives the response, and the client
    # watches it through GET /sync/{run_id}.
    asyncio.create_task(sync.run_sync_background(
        AsyncSessionLocal, run.id, source.id, current_user.org_id,
        cache=cache_module.get_cache(),
        llm_client=llm_service.get_client(),
        allow_llm=bool(source.allow_llm_sampling),
        source_config=cfg,
    ))

    return {"sync_run_id": run.id, "status": "running", "stages": []}


@router.get("/{source_id}/sync/latest")
async def latest_sync(
    source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_source(db, source_id, current_user)
    run = (await db.execute(
        select(SyncRun).where(SyncRun.data_source_id == source_id)
        .order_by(SyncRun.id.desc()).limit(1)
    )).scalar_one_or_none()
    if run is None:
        return {"status": "never_run", "stages": []}
    return _run_payload(run)


@router.get("/{source_id}/sync/{run_id}")
async def sync_status(
    source_id: int, run_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_source(db, source_id, current_user)
    run = await db.get(SyncRun, run_id)
    if run is None or run.data_source_id != source_id:
        raise HTTPException(404, "Sync run not found")
    check_org(run, current_user, "Sync run not found")
    return _run_payload(run)


def _run_payload(run: SyncRun) -> dict:
    return {
        "id": run.id,
        "status": run.status,
        "trigger": run.trigger,
        "stages": run.stages or [],
        "error": run.error,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
    }


# ── review ──────────────────────────────────────────────────────────────────

@router.get("/{source_id}/review")
async def review_queue(
    source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """What the sync learned about this database.

    Reads the SOURCE CATALOG — every table and column the connection can see —
    not the datasets someone happened to import. Those are different sets, and
    the tables nobody imported are exactly the ones a newcomer needs told about.

    Confirmed and declared relationships are returned alongside the proposed
    ones, marked as such: a proposal is only judgeable in context, and the join
    graph is unreadable without the settled edges drawn in.
    """
    source = await _get_source(db, source_id, current_user)

    objects = (await db.execute(
        select(SourceObject).where(
            SourceObject.data_source_id == source_id,
            SourceObject.org_id == current_user.org_id,
        ).order_by(SourceObject.name)
    )).scalars().all()

    payload_source = {
        "id": source.id, "name": source.name, "type": source.type,
        "description": source.description,
        "description_source": source.description_source,
        "allow_llm_sampling": bool(source.allow_llm_sampling),
        "sync_status": source.sync_status,
        "last_synced_at": source.last_synced_at,
    }

    by_id = {o.id: o for o in objects}
    if not by_id:
        return {"source": payload_source, "datasets": [],
                "relationships": [], "columns": []}

    columns = (await db.execute(
        select(SourceColumn).where(SourceColumn.source_object_id.in_(list(by_id)))
        .order_by(SourceColumn.position)
    )).scalars().all()

    rels = (await db.execute(
        select(SourceRelationship).where(
            SourceRelationship.data_source_id == source_id,
            SourceRelationship.org_id == current_user.org_id,
        )
    )).scalars().all()

    return {
        "source": payload_source,
        # Kept under `datasets` so the client contract is unchanged; these are
        # catalog objects, which is what the client always wanted to render.
        "datasets": [
            {"id": o.id, "name": o.name, "kind": o.kind,
             "is_deprecated": o.is_deprecated,
             "row_count": o.row_count_estimate,
             # A COMMENT written in the schema is documentation, so it is shown
             # in preference to anything the model wrote.
             "description": o.comment or o.description,
             # Non-null means the last sync gave up on sampling this object and
             # the next one will skip it. Surfaced so the skip is something a
             # person can SEE and undo, rather than a table that quietly stops
             # being described with no explanation on the page.
             "sample_timed_out_at": (o.sample_timed_out_at.isoformat()
                                     if o.sample_timed_out_at else None),
             "description_source": "schema" if o.comment else o.description_source,
             "is_canonical": bool(o.is_canonical)}
            for o in objects
        ],
        "relationships": [
            {
                "id": r.id,
                "from_dataset_id": r.from_object_id,
                "from_dataset": by_id[r.from_object_id].name,
                "from_column": r.from_column,
                "to_dataset_id": r.to_object_id,
                "to_dataset": by_id[r.to_object_id].name if r.to_object_id in by_id else None,
                "to_column": r.to_column,
                "confidence": r.confidence,
                "source": r.source,
                "cardinality": r.cardinality,
                "evidence": r.evidence,
                # Only inference is ever asked about. A declared key is what the
                # database enforces; confirming it would be asking a person to
                # ratify a constraint they cannot change from here.
                "needs_review": r.source == store.INFERRED,
            }
            for r in rels
        ],
        "columns": [
            {
                "id": c.id,
                "dataset_id": c.source_object_id,
                "dataset": by_id[c.source_object_id].name,
                "name": c.name,
                "dtype": c.dtype or c.native_type,
                "semantic_type": c.semantic_type,
                "description": c.comment or c.description,
                "description_source": "schema" if c.comment else c.description_source,
                "needs_review": (not c.comment) and c.description_source == store.INFERRED,
                "enum_labels": c.enum_labels,
                "enum_labels_source": c.enum_labels_source,
            }
            for c in columns
        ],
    }


@router.post("/{source_id}/review/confirm")
async def confirm_review(
    source_id: int, body: ConfirmRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_org_admin),
):
    """Promote inferred catalog items to `confirmed` — the terminal state.

    Rejection DELETES rather than marking, because a rejected proposal would
    otherwise be re-proposed by the next sync and the user would spend every
    morning rejecting it again. Safe precisely because inference is
    reproducible: nothing a human wrote is lost.
    """
    await _get_source(db, source_id, current_user)

    confirmed = 0
    for relationship_id in body.relationship_ids:
        row = await db.get(SourceRelationship, relationship_id)
        if row is None or row.org_id != current_user.org_id or row.data_source_id != source_id:
            raise HTTPException(404, "Relationship not found")
        row.source = store.CONFIRMED
        row.confidence = 1.0
        confirmed += 1

    rejected = 0
    for relationship_id in body.rejected_relationship_ids:
        row = await db.get(SourceRelationship, relationship_id)
        if row is None or row.org_id != current_user.org_id or row.data_source_id != source_id:
            raise HTTPException(404, "Relationship not found")
        # A declared key is enforced by the database; deleting the row here
        # would not remove the constraint, only our knowledge of it.
        if row.source == store.INFERRED:
            await db.delete(row)
            rejected += 1

    updated = 0
    for update in body.column_updates:
        column = await db.get(SourceColumn, update.get("id"))
        if column is None:
            continue
        obj = await db.get(SourceObject, column.source_object_id)
        if obj is None or obj.org_id != current_user.org_id or obj.data_source_id != source_id:
            raise HTTPException(404, "Column not found")
        if "description" in update:
            column.description = update["description"]
            # A human touched it, so it stops being a proposal.
            column.description_source = store.CONFIRMED
        if "semantic_type" in update:
            column.semantic_type = update["semantic_type"]
        if "enum_labels" in update:
            labels = update["enum_labels"]
            if not isinstance(labels, dict) or len(labels) > MAX_ENUM_LABELS or \
               not all(isinstance(v, str) for v in labels.values()):
                raise HTTPException(
                    422, "enum_labels must be an object of at most "
                    f"{MAX_ENUM_LABELS} string values")
            column.enum_labels = labels
            # A human touched it, so it stops being a proposal -- mirrors
            # description_source: never overwritten by a later sync.
            column.enum_labels_source = store.CONFIRMED
        updated += 1

    for update in body.object_updates:
        obj = await db.get(SourceObject, update.get("id"))
        if obj is None or obj.org_id != current_user.org_id or obj.data_source_id != source_id:
            raise HTTPException(404, "Table not found")
        if "description" in update:
            obj.description = update["description"]
            obj.description_source = store.CONFIRMED
            updated += 1
        if "is_canonical" in update:
            obj.is_canonical = bool(update["is_canonical"])
            updated += 1
        if update.get("retry_sample"):
            # Clearing the flag is the whole of Retry: the next sync then treats
            # this object as it would any other. Deliberately NOT a sync trigger
            # -- one object is not worth a run, and the person clearing this is
            # usually clearing several before starting one.
            #
            # This is what keeps the skip from being a one-way door. An object
            # given up on stays visible and stays recoverable by the person who
            # can actually judge whether the view has been fixed.
            obj.sample_timed_out_at = None
            updated += 1

    await db.commit()
    return {"confirmed": confirmed, "rejected": rejected, "columns_updated": updated}


class SourceSettings(BaseModel):
    """What a human can change about a source's metadata."""
    allow_llm_sampling: bool | None = None
    description: str | None = None


@router.patch("/{source_id}/metadata-settings")
async def update_metadata_settings(
    source_id: int, body: SourceSettings,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_org_admin),
):
    """Change LLM consent, or edit the database description by hand.

    Consent is admin-only and per source, because turning it on means masked
    samples and structure start leaving for the model endpoint. That is a
    decision about data handling, not a display preference.

    An edited description becomes `confirmed`, which means no later sync will
    overwrite it — the same provenance rule that protects every other human
    judgement in this layer.
    """
    source = await _get_source(db, source_id, current_user)

    if body.allow_llm_sampling is not None:
        source.allow_llm_sampling = body.allow_llm_sampling
    if body.description is not None:
        source.description = body.description
        source.description_source = store.CONFIRMED

    await db.commit()
    return {
        "allow_llm_sampling": bool(source.allow_llm_sampling),
        "description": source.description,
        "description_source": source.description_source,
    }


# ── drift ───────────────────────────────────────────────────────────────────

@router.get("/{source_id}/drift")
async def drift_history(
    source_id: int, limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_source(db, source_id, current_user)
    versions = (await db.execute(
        select(SchemaVersion).where(SchemaVersion.data_source_id == source_id)
        .order_by(SchemaVersion.id.desc()).limit(min(limit, 100))
    )).scalars().all()

    return [
        {
            "id": v.id,
            "fingerprint": v.fingerprint,
            "detected_at": v.detected_at,
            "is_baseline": (v.diff or {}).get("is_baseline", False),
            "added": (v.diff or {}).get("added", []),
            "removed": (v.diff or {}).get("removed", []),
            "changed": (v.diff or {}).get("changed", []),
            "orphaned_annotations": (v.diff or {}).get("orphaned_annotations", []),
        }
        for v in versions
    ]


# ── glossary ────────────────────────────────────────────────────────────────
#
# T3 — business terms and synonyms (spec L3 gap #3: "'إجمالي المبيعات' and
# 'GMV' cannot resolve to the same metric"). Admin-gated for writes because a
# glossary term drives the query the agent generates for everyone who asks
# using that word — the same trust level as an is_canonical flag or a row
# policy. Reads are open to any org member, same as `review`.

class GlossaryIn(BaseModel):
    term: str
    definition: str | None = None
    synonyms: list[str] = Field(default_factory=list)
    maps_to_object: str | None = None
    maps_to_column: str | None = None


def _glossary_payload(t: GlossaryTerm) -> dict:
    return {"id": t.id, "term": t.term, "definition": t.definition,
            "synonyms": t.synonyms or [], "maps_to_object": t.maps_to_object,
            "maps_to_column": t.maps_to_column,
            "data_source_id": t.data_source_id}


@router.get("/{source_id}/glossary")
async def list_glossary(
    source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """This source's own terms, plus every ORG-WIDE term (data_source_id
    NULL) — a term like "GMV" usually means the same thing everywhere in the
    org, matching what `agent/context.py`'s `load_context` loads for the
    agent itself."""
    await _get_source(db, source_id, current_user)
    rows = (await db.execute(
        select(GlossaryTerm).where(
            GlossaryTerm.org_id == current_user.org_id,
            or_(GlossaryTerm.data_source_id == source_id,
                GlossaryTerm.data_source_id.is_(None)),
        ).order_by(GlossaryTerm.term)
    )).scalars().all()
    return [_glossary_payload(t) for t in rows]


@router.post("/{source_id}/glossary")
async def create_glossary_term(
    source_id: int, body: GlossaryIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_org_admin),
):
    source = await _get_source(db, source_id, current_user)

    term = body.term.strip()
    if not term:
        raise HTTPException(422, "term must not be empty")

    synonyms = body.synonyms or []
    if not isinstance(synonyms, list) or not all(
        isinstance(s, str) and s.strip() for s in synonyms
    ):
        raise HTTPException(422, "synonyms must be a list of non-empty strings")

    row = GlossaryTerm(
        org_id=current_user.org_id, data_source_id=source.id, term=term,
        definition=body.definition, synonyms=[s.strip() for s in synonyms],
        maps_to_object=body.maps_to_object, maps_to_column=body.maps_to_column,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _glossary_payload(row)


@router.delete("/{source_id}/glossary/{term_id}", status_code=204)
async def delete_glossary_term(
    source_id: int, term_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_org_admin),
):
    await _get_source(db, source_id, current_user)
    term = await db.get(GlossaryTerm, term_id)
    check_org(term, current_user, "Glossary term not found")
    # A source-scoped delete must not reach into another source's term —
    # only this source's own rows, or an org-wide (NULL) row, are fair game
    # from this endpoint.
    if term.data_source_id not in (None, source_id):
        raise HTTPException(404, "Glossary term not found")
    await db.delete(term)
    await db.commit()


# ── entities ────────────────────────────────────────────────────────────────
#
# Tier 2 / spec section 5 (E2, Task R3): named business objects a source
# models ("customer", "order"), drafted by the sync's LLM pass
# (catalog_sync.stage_entities, same complete_json pattern as enum labels)
# and confirmed/edited here. Same ladder discipline as every other write in
# this router: a human touch sets `source = 'confirmed'`, and a confirmed row
# is never overwritten by a later sync's draft.

class EntityUpdate(BaseModel):
    id: int
    business_name: str | None = None
    grain: str | None = None
    description: str | None = None
    # Lets the UI confirm a row unedited (agreeing with the draft as-is)
    # without having to resend every field just to flip its provenance.
    confirm: bool = False


class EntityConfirmRequest(BaseModel):
    updates: list[EntityUpdate] = Field(default_factory=list)


def _entity_payload(e: Entity) -> dict:
    return {"id": e.id, "name": e.name, "business_name": e.business_name,
            "grain": e.grain, "description": e.description,
            "primary_object": e.primary_object, "source": e.source}


@router.get("/{source_id}/entities")
async def list_entities(
    source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_source(db, source_id, current_user)
    rows = (await db.execute(
        select(Entity).where(
            Entity.data_source_id == source_id,
            Entity.org_id == current_user.org_id,
        ).order_by(Entity.name)
    )).scalars().all()
    return [_entity_payload(e) for e in rows]


@router.post("/{source_id}/entities/confirm")
async def confirm_entities(
    source_id: int, body: EntityConfirmRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_org_admin),
):
    """Edit and/or confirm entity rows. Editing a field and confirming are
    both "a human touched this" -- either one promotes the row to
    `confirmed`, the same rule `review/confirm` applies to column
    descriptions and enum labels above."""
    await _get_source(db, source_id, current_user)

    updated = 0
    for update in body.updates:
        entity = await db.get(Entity, update.id)
        if entity is None or entity.org_id != current_user.org_id \
           or entity.data_source_id != source_id:
            raise HTTPException(404, "Entity not found")

        touched = update.confirm
        if update.business_name is not None:
            entity.business_name = update.business_name
            touched = True
        if update.grain is not None:
            entity.grain = update.grain
            touched = True
        if update.description is not None:
            entity.description = update.description
            touched = True
        if touched:
            entity.source = store.CONFIRMED
        updated += 1

    await db.commit()
    return {"updated": updated}


# ── column statistics ───────────────────────────────────────────────────────

stats_router = APIRouter(prefix="/datasets", tags=["metadata"])


@stats_router.get("/{dataset_id}/columns/{column_name}/stats")
async def column_statistics(
    dataset_id: int, column_name: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Statistics for one column, including `top_k`.

    Useful well before any agent exists: `top_k` is the column's real values, so
    a filter control can offer a dropdown of what is actually there rather than
    a text box the user has to guess into.

    `exact` tells the caller whether these are measured or estimated. A UI
    showing a distinct count as fact should check it.
    """
    dataset = await db.get(Dataset, dataset_id)
    check_org(dataset, current_user, "Dataset not found")

    column = (await db.execute(
        select(DatasetColumn).where(
            DatasetColumn.dataset_id == dataset_id,
            DatasetColumn.name == column_name,
        )
    )).scalar_one_or_none()
    if column is None:
        raise HTTPException(404, "Column not found")

    stats = (await db.execute(
        select(ColumnStats).where(ColumnStats.dataset_column_id == column.id)
    )).scalar_one_or_none()

    if stats is None:
        # Not an error: statistics arrive with the first sync, and a column
        # asked about before then simply has none yet.
        return {
            "column": column_name, "dtype": column.dtype,
            "semantic_type": column.semantic_type,
            "profiled": False,
        }

    return {
        "column": column_name,
        "dtype": column.dtype,
        "semantic_type": column.semantic_type,
        "description": column.description,
        "description_source": column.description_source,
        "profiled": True,
        "null_ratio": stats.null_ratio,
        "distinct_count": stats.distinct_count,
        "top_k": stats.top_k,
        "min_value": stats.min_value,
        "max_value": stats.max_value,
        "exact": stats.exact,
        "computed_at": stats.computed_at,
    }


class SuggestDashboardIn(BaseModel):
    """Who the dashboard is for, and optionally what they said they want."""
    for_role: str = Field(min_length=1, max_length=100)
    goal: str | None = Field(default=None, max_length=500)


@router.post("/{source_id}/suggest-dashboard")
async def suggest_dashboard_for_role(source_id: int, body: SuggestDashboardIn,
                                     db: AsyncSession = Depends(get_db),
                                     current_user: User = Depends(get_current_user)):
    """Propose a dashboard for a kind of person, from this connection's catalog.

    The existing `/reports/{id}/suggest-widgets` needs a dataset to already exist
    and ranks by statistical interest. This is the step before that: someone has
    connected a database, has no dataset, and does not know which of its tables to
    join. It answers with one SQL query and the widgets to put over it.

    Nothing is created. The response is a proposal the caller accepts or discards,
    because a dashboard that appears by itself and is subtly wrong is worse than
    no dashboard.
    """
    src = await db.get(DataSource, source_id)
    check_org(src, current_user, "Data source not found")

    from ..services.suggest_dashboard import load_catalog, load_joins
    catalog = await load_catalog(db, source_id)
    joins = await load_joins(db, source_id)
    if not catalog:
        raise HTTPException(400, "Sync this connection first — there is no catalog to read")

    # The database gets the last word on whether the proposed query runs. One
    # bounded row: enough to compile and execute it, cheap enough to do inside a
    # retry loop.
    cfg = dict(src.config)
    cfg["type"] = src.type

    async def probe(sql: str) -> str | None:
        from ..services.connections import preview_table
        try:
            await asyncio.to_thread(preview_table, cfg, None, sql, 1)
            return None
        except Exception as exc:                          # noqa: BLE001
            return str(exc)[:300]

    from ..services.suggest_dashboard import suggest_dashboard
    suggestion, why = await suggest_dashboard(catalog, body.for_role, body.goal,
                                              probe=probe)
    if suggestion is None:
        # 200 with a reason, not an error: "the model is off" and "the model
        # proposed something unsafe" are both normal answers to a request for a
        # suggestion, and the UI shows the reason rather than an error toast.
        return {"ok": False, "reason": why, "suggestion": None}
    return {"ok": True, "reason": "", "suggestion": suggestion}


@router.post("/{source_id}/review/reset-inferred")
async def reset_inferred_metadata(source_id: int, db: AsyncSession = Depends(get_db),
                                  current_user: User = Depends(require_org_admin)):
    """Clear the descriptions and semantic types that INFERENCE wrote.

    The sync only ever proposes; nothing in it retracts a value once written. That
    is correct while the inference is correct and a trap when it is not — after
    the PII classifier stopped calling every Unix timestamp a `national_id`, a
    fresh sync inferred nothing wrong and the catalog still showed all 41 bad
    labels from the first run. There was no way to clear them from anywhere in the
    product, so an organisation that synced before a metadata fix kept the bad
    metadata forever and the fix looked like it had not worked.

    Only `description_source == 'inferred'` rows are touched. What a person typed
    is theirs — the same rule `infer_semantic.py` follows when writing, and it
    would be a strange repair that discarded the corrections somebody made by hand
    *because* the inference was wrong.

    Admin-only: metadata is org-wide, so one member's reset rewrites what everyone
    reads. Run a sync afterwards to re-describe with the current logic.
    """
    src = await db.get(DataSource, source_id)
    check_org(src, current_user, "Data source not found")

    object_ids = (await db.execute(
        select(SourceObject.id).where(SourceObject.data_source_id == source_id)
    )).scalars().all()
    if not object_ids:
        return {"objects_cleared": 0, "columns_cleared": 0}

    cols = (await db.execute(
        select(SourceColumn).where(SourceColumn.source_object_id.in_(object_ids),
                                   SourceColumn.description_source == "inferred")
    )).scalars().all()
    for c in cols:
        c.description = None
        c.description_source = None
        c.semantic_type = None

    objs = (await db.execute(
        select(SourceObject).where(SourceObject.id.in_(object_ids),
                                   SourceObject.description_source == "inferred")
    )).scalars().all()
    for o in objs:
        o.description = None
        o.description_source = None

    await db.commit()
    return {"objects_cleared": len(objs), "columns_cleared": len(cols)}
