"""The metadata pipeline, run against a CONNECTION rather than against datasets.

    1 discover    introspect the live database — every table, view, column,
                  primary key, declared foreign key and schema comment
    2 sample      ~1000 masked rows per object into the local cache
    3 profile     statistics and top_k per column
    4 infer_keys  foreign keys nobody declared, from value overlap
    5 describe    semantic types, roles, and the LLM's account of the database
    5.5 entities  named business objects and their grain (Tier 2 / spec S5)
    6 drift       fingerprint the catalog and record what changed

WHY THIS EXISTS SEPARATELY FROM sync.py
----------------------------------------
`sync.py` describes the Datasets a person has created. This describes the
DATABASE. They are not the same thing and neither subsumes the other:

  * a Dataset is a slice somebody chose to import or query — often one table out
    of eighty, sometimes a hand-written join that matches no table at all;
  * the catalog is everything the connection can see, whether or not anyone has
    looked at it yet.

A description assembled from datasets describes the part of the database
somebody already knew to import. That is precisely backwards for the person who
has just connected a source and wants to know what is in it — the tables they
have NOT imported are the ones they most need told about.

So this pipeline needs nothing but a connection, and it describes everything.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

from sqlalchemy import select

from ...models.models import (ColumnStats, DataSource, Entity, SchemaVersion,
                              SourceColumn, SourceObject, SourceRelationship,
                              SyncRun)
from .. import pii
from . import drift, infer_keys, infer_semantic, introspect, sample, store
from .sync import StageResult, _run_stage, _skip

logger = logging.getLogger(__name__)



class CatalogContext:
    """State threaded through the stages of one catalog sync."""

    def __init__(self, db, source: DataSource, *, cache, llm_client=None,
                 allow_llm: bool = False, source_config: dict | None = None):
        self.db = db
        self.source = source
        self.data_source_id = source.id
        self.org_id = source.org_id
        self.cache = cache
        self.llm_client = llm_client
        self.allow_llm = allow_llm
        self.source_config = source_config

        self.objects: list[SourceObject] = []
        self.columns_by_object: dict[int, list[SourceColumn]] = {}
        self.schema_columns: list[dict] = []
        # Semantic types detected during sampling, BEFORE masking. Stage 5 reuses
        # them rather than re-classifying masked values, which would classify the
        # mask instead of the data.
        self.sample_types: dict[int, dict] = {}
        self.stages: list[StageResult] = []
        self.run: SyncRun | None = None


def _engine_for(cfg: dict):
    """The interactive pool — used by discover, which issues a handful of cheap
    catalogue reads and is not worth a second pool."""
    from ..engines import get_engine
    return get_engine(cfg)


def _sampling_engine_for(cfg: dict):
    """The metadata pool — used by sampling, which runs many objects at once and
    must not compete with live widget traffic for connections."""
    from ..engines import get_metadata_engine
    return get_metadata_engine(cfg)


# ── stage 1 ─────────────────────────────────────────────────────────────────

async def stage_discover(context: CatalogContext) -> dict:
    """Read the whole database catalog and write it down.

    Everything here comes from the connection alone. Objects that have vanished
    from the source are removed, so a table dropped upstream stops being
    described — but their inferred relationships go with them by cascade, and
    Stage 6 separately flags any CONFIRMED annotation that just lost its column.
    """
    cfg = context.source_config
    if not cfg:
        raise RuntimeError("no connection config; cannot introspect the source")

    schema = cfg.get("schema") or None
    engine = _engine_for(cfg)
    described = await asyncio.to_thread(
        introspect.introspect_source, engine, schema, with_counts=True
    )

    existing = {
        (o.schema_name, o.name): o
        for o in (await context.db.execute(
            select(SourceObject).where(
                SourceObject.data_source_id == context.data_source_id)
        )).scalars().all()
    }
    seen: set[tuple] = set()

    for entry in described:
        key = (entry.get("schema"), entry["name"])
        seen.add(key)
        obj = existing.get(key)
        if obj is None:
            obj = SourceObject(
                data_source_id=context.data_source_id, org_id=context.org_id,
                schema_name=entry.get("schema"), name=entry["name"],
            )
            context.db.add(obj)
            await context.db.flush()

        obj.kind = entry.get("kind", "table")
        obj.row_count_estimate = entry.get("row_count_estimate")
        # A COMMENT written in the schema is documentation, not a guess. Kept in
        # its own field so it never competes with an inferred description.
        obj.comment = entry.get("comment")

        await _sync_columns(context, obj, entry["columns"])
        context.objects.append(obj)

    # Objects that no longer exist upstream.
    for key, obj in existing.items():
        if key not in seen:
            await context.db.delete(obj)

    await context.db.flush()

    for obj in context.objects:
        for column in context.columns_by_object.get(obj.id, []):
            context.schema_columns.append({
                "table": obj.name, "name": column.name,
                "dtype": column.dtype, "nullable": column.nullable,
            })

    declared = await _seed_declared_keys(context, described)

    return {
        "objects": len(context.objects),
        "columns": len(context.schema_columns),
        "declared_foreign_keys": declared,
        "views": sum(1 for o in context.objects if o.kind == "view"),
    }


async def _sync_columns(context: CatalogContext, obj: SourceObject, columns: list[dict]) -> None:
    """Upsert one object's columns, preserving anything a human confirmed."""
    existing = {
        c.name: c
        for c in (await context.db.execute(
            select(SourceColumn).where(SourceColumn.source_object_id == obj.id)
        )).scalars().all()
    }
    seen = set()

    for entry in columns:
        seen.add(entry["name"])
        column = existing.get(entry["name"])
        if column is None:
            column = SourceColumn(source_object_id=obj.id, name=entry["name"])
            context.db.add(column)

        column.position = entry["position"]
        column.native_type = entry["native_type"]
        column.dtype = entry["dtype"]
        column.nullable = entry["nullable"]
        column.is_primary_key = entry["is_primary_key"]
        column.comment = entry.get("comment")

    for name, column in existing.items():
        if name not in seen:
            await context.db.delete(column)

    await context.db.flush()
    context.columns_by_object[obj.id] = (await context.db.execute(
        select(SourceColumn).where(SourceColumn.source_object_id == obj.id)
        .order_by(SourceColumn.position)
    )).scalars().all()


async def _seed_declared_keys(context: CatalogContext, described: list[dict]) -> int:
    """Record the foreign keys the database itself declares.

    These are facts, not proposals: the schema enforces them. Seeding them means
    value-overlap inference is only asked to find the keys nobody declared,
    rather than re-deriving by statistics what the catalog states outright.
    """
    by_name = {o.name: o for o in context.objects}
    written = 0

    for entry in described:
        parent_lookup = by_name.get(entry["name"])
        if parent_lookup is None:
            continue
        for fk in entry.get("foreign_keys", []):
            target = by_name.get(fk["to_table"])
            if target is None:
                continue
            await _upsert_source_relationship(
                context, from_object_id=parent_lookup.id, from_column=fk["from_column"],
                to_object_id=target.id, to_column=fk["to_column"],
                source="declared", confidence=1.0, evidence=None,
                cardinality="many_to_one",
            )
            written += 1

    return written


async def _upsert_source_relationship(
    context: CatalogContext, *, from_object_id: int, from_column: str,
    to_object_id: int, to_column: str, source: str, confidence: float,
    evidence: dict | None, cardinality: str | None,
) -> None:
    """Provenance-aware write, mirroring metadata/store.py's ladder.

    confirmed > declared > inferred, and a confirmation is never overwritten.
    """
    rank = {"inferred": 0, "declared": 1, "confirmed": 2}

    existing = (await context.db.execute(
        select(SourceRelationship).where(
            SourceRelationship.data_source_id == context.data_source_id,
            SourceRelationship.from_object_id == from_object_id,
            SourceRelationship.from_column == from_column,
            SourceRelationship.to_object_id == to_object_id,
            SourceRelationship.to_column == to_column,
        )
    )).scalar_one_or_none()

    if existing is not None:
        if rank.get(source, 0) < rank.get(existing.source, 0):
            return
        existing.source = source
        existing.confidence = confidence
        existing.evidence = evidence
        existing.cardinality = cardinality
        return

    context.db.add(SourceRelationship(
        data_source_id=context.data_source_id, org_id=context.org_id,
        from_object_id=from_object_id, from_column=from_column,
        to_object_id=to_object_id, to_column=to_column,
        source=source, confidence=confidence,
        evidence=evidence, cardinality=cardinality,
    ))


# ── stage 2 ─────────────────────────────────────────────────────────────────

def _looks_like_timeout(exc: BaseException) -> bool:
    """Whether a driver error is a statement timeout.

    Matched on message text because each driver raises its own exception type
    for the same condition, and importing all of them to catch them precisely
    would couple this module to every connector the platform supports.
    """
    text_form = f"{type(exc).__name__} {exc}".lower()
    return any(token in text_form for token in (
        "statement timeout", "canceling statement", "query execution was interrupted",
        "timeout expired", "querytimeout", "max_execution_time",
    ))


#: How much of a driver error message to keep in the run record.
ERROR_DETAIL_CHARS = 160


def _error_summary(exc: BaseException) -> str:
    """The exception class, plus enough of its message to act on.

    The class alone was a dead end. A run reporting
    `v_maps_state_student_solution: InternalError` on every sync gave nobody
    anything to do about it; the actual cause -- a PL/Python function on the
    server whose `import requests` fails -- only came out of a hand-written
    probe against the live database. That is a defect in the customer's view,
    permanently broken for every caller, and the person who can fix it is the
    one reading this record.

    FIRST LINE ONLY, and bounded. Driver messages append the failing SQL and a
    documentation link, and the SQL can carry literal values from the query --
    which is how a run record quietly becomes somewhere personal data lives.
    The diagnosis is always the first line; the rest is bulk and risk.
    """
    first = str(exc).strip().splitlines()
    detail = first[0].strip() if first else ""
    if not detail:
        return type(exc).__name__
    if len(detail) > ERROR_DETAIL_CHARS:
        detail = detail[:ERROR_DETAIL_CHARS] + "…"
    return f"{type(exc).__name__}: {detail}"


def _sample_object(spec: dict, cfg: dict, n: int, cache) -> dict:
    """Sample, classify, mask and cache one object — entirely off the event loop.

    `spec` is plain data — {"id", "name", "kind", "row_count_estimate"} — never a
    SourceObject. The rule is already written down at `_profile_object` below:
    an AsyncSession's instances must not be touched from another thread, and a
    lazy attribute load from here would be a race rather than an error. The
    previous version passed the instance in and was safe only because the
    session runs with `expire_on_commit=False`.

    Classification, masking and `put_sample` happen HERE rather than back on the
    loop. They are synchronous CPU work over ~1000 rows plus a DuckDB write; on
    the loop they froze every other request, and doing them between awaits would
    also have serialised the fan-out on whichever object finished first.

    Returns a verdict — never rows, never an ORM object. Every outcome is a
    value, including the failures, so the caller can aggregate on the loop
    without needing to interpret exceptions.

    Every query runs under a statement timeout. Some views are expensive by
    construction — the cost is in the view definition, and no sampling strategy
    can avoid it — so each object gets a fixed budget and the run moves on.
    """
    from sqlalchemy import text

    from ...core.config import settings
    from .. import connectors

    verdict = {"id": spec["id"], "name": spec["name"], "outcome": "error",
               "column_types": None, "masked": 0, "error": None}

    family = connectors.sql_family_of(cfg) or "postgresql"
    strategy = sample.choose_strategy(
        family=family, kind=spec.get("kind") or "table",
        row_count=spec.get("row_count_estimate"),
    )
    engine = _sampling_engine_for(cfg)

    conn = engine.connect()
    try:
        deadline = sample.statement_timeout_sql(
            family, settings.metadata_statement_timeout_s)
        if deadline:
            conn.execute(text(deadline))
        sql = sample.build_sample_sql(
            spec["name"], family=family, strategy=strategy, n=n,
            row_count=spec.get("row_count_estimate"),
        )
        rows = [dict(r._mapping) for r in conn.execute(text(sql))]

        # TABLESAMPLE works in PAGES, so an empty result is not evidence the
        # table is empty. Confirm with a bounded read before believing it —
        # `head`, not `random`: the point of the retry is a cheap second look,
        # and sorting the table would cost more than the first attempt saved.
        if not rows and strategy == "tablesample":
            fallback = sample.build_sample_sql(
                spec["name"], family=family, strategy="head", n=n,
                row_count=spec.get("row_count_estimate"),
            )
            rows = [dict(r._mapping) for r in conn.execute(text(fallback))]
    except Exception as exc:
        # A cancelled statement leaves the connection inside an aborted
        # transaction. It is still ALIVE -- pool_pre_ping happily hands it back
        # -- but every statement on it then fails with "current transaction is
        # aborted", so one timed-out view was poisoning the next few objects.
        # Measured: 9 real timeouts produced 4 further InternalErrors that had
        # nothing wrong with them. Discard it instead of returning it.
        conn.invalidate()
        # Classified HERE, where the exception is, rather than by the caller.
        verdict["outcome"] = "timeout" if _looks_like_timeout(exc) else "error"
        verdict["error"] = _error_summary(exc)
        return verdict
    finally:
        conn.close()

    if not rows:
        # Genuinely empty, and confirmed as such by the fallback above. Worth
        # recording: emptiness is one of the deprecation signals Stage 5 uses.
        cache.put_sample(spec["id"], [])
        verdict["outcome"] = "empty"
        return verdict

    # Classify from the REAL values, then mask, then cache. Nothing after this
    # line ever sees an unmasked personal value.
    column_types = {
        name: pii.detect_semantic_type([r.get(name) for r in rows])
        for name in rows[0].keys()
    }
    cache.put_sample(spec["id"], pii.mask_rows(rows, column_types))

    verdict["outcome"] = "sampled"
    verdict["column_types"] = column_types
    verdict["masked"] = sum(1 for k in column_types.values() if pii.is_pii(k))
    return verdict


async def stage_sample(context: CatalogContext) -> dict:
    """Sample every object, several at a time, masking before anything is cached.

    Bounded by `metadata_sample_concurrency`, which is also the size of the
    dedicated metadata connection pool — so the sync's footprint on the source
    is exactly that number and cannot exceed it.

    A plain local Semaphore, not the module-level weak-map gate used in
    routers/widget_data.py: that indirection exists because THAT gate outlives
    any one event loop. This one is created on the loop that awaits it and dies
    with the call.
    """
    from ...core.config import settings

    n = settings.metadata_sample_rows
    gate = asyncio.Semaphore(settings.metadata_sample_concurrency)

    # Objects already known to be too expensive never reach a thread and never
    # open a connection. Their previously cached sample stays, so every later
    # stage still covers them.
    pending = [o for o in context.objects if o.sample_timed_out_at is None]
    skipped_slow = [o.name for o in context.objects if o.sample_timed_out_at is not None]

    specs = [{"id": o.id, "name": o.name, "kind": o.kind,
              "row_count_estimate": o.row_count_estimate} for o in pending]

    async def one(spec: dict) -> dict:
        async with gate:
            return await asyncio.to_thread(
                _sample_object, spec, context.source_config, n, context.cache)

    # return_exceptions so one object's failure never sinks its siblings — the
    # same choice, for the same reason, as the describe stage below.
    results = await asyncio.gather(*(one(s) for s in specs), return_exceptions=True)

    # Everything from here runs on the loop, after the fan-out has fully
    # drained. No ORM instance was touched by a worker, and none is touched
    # concurrently now.
    by_id = {o.id: o for o in pending}
    sampled = empty = masked_columns = 0
    failures: list[str] = []
    timed_out: list[str] = []

    for spec, result in zip(specs, results):
        if isinstance(result, BaseException):
            failures.append(f"{spec['name']}: {type(result).__name__}")
            continue

        outcome = result["outcome"]
        if outcome == "sampled":
            sampled += 1
            masked_columns += result["masked"]
            context.sample_types[spec["id"]] = result["column_types"]
        elif outcome == "empty":
            empty += 1
        elif outcome == "timeout":
            timed_out.append(spec["name"])
            obj = by_id.get(spec["id"])
            if obj is not None:
                # Remembered, so the next sync does not pay this deadline again.
                obj.sample_timed_out_at = datetime.utcnow()
        else:
            failures.append(f"{spec['name']}: {result.get('error') or 'error'}")

    evicted = await asyncio.to_thread(context.cache.evict_if_over_budget)

    return {
        "objects_sampled": sampled, "objects_empty": empty,
        "objects_timed_out": len(timed_out),
        "timed_out": timed_out[:10] or None,
        # Distinct from `timed_out`: that is "failed this run", this is "not
        # attempted, because it failed before".
        "objects_skipped_slow": len(skipped_slow),
        "skipped_slow": skipped_slow[:10] or None,
        "concurrency": settings.metadata_sample_concurrency,
        "pii_columns_masked": masked_columns, "evicted": len(evicted),
        "failures": failures or None,
    }


def _profile_object(cache, object_id: int, columns: list[tuple[int, str]]) -> list[tuple[int, dict]]:
    """Compute statistics for one object's columns, off the event loop.

    Takes plain tuples rather than ORM rows: an AsyncSession's objects must not
    be touched from another thread, and a lazy attribute load from here would be
    a race rather than an error.
    """
    rows = cache.get_sample(object_id)
    if not rows:
        return []

    out: list[tuple[int, dict]] = []
    for column_id, name in columns:
        values = [r.get(name) for r in rows]
        present = [v for v in values if v is not None]
        distinct = len(set(present))

        top_k = None
        if present and distinct < 100:
            counts: dict[str, int] = {}
            for value in present:
                counts[str(value)] = counts.get(str(value), 0) + 1
            top_k = [
                {"value": v, "count": c, "ratio": round(c / len(present), 6)}
                for v, c in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
            ][:100]

        out.append((column_id, {
            "null_ratio": round((len(values) - len(present)) / len(values), 6) if values else None,
            "distinct_count": distinct,
            "top_k": top_k,
            "min_value": str(min(present)) if present else None,
            "max_value": str(max(present)) if present else None,
            # Computed over a SAMPLE, not the table.
            "exact": False,
        }))
    return out


# ── stage 3 ─────────────────────────────────────────────────────────────────

async def stage_profile(context: CatalogContext) -> dict:
    """Statistics and top_k for every catalog column, from the cached sample."""
    from .store import upsert_column_stats

    written = 0
    for obj in context.objects:
        columns = context.columns_by_object.get(obj.id, [])
        if not columns:
            continue

        # Reading the cache and computing the statistics are both synchronous
        # DuckDB / Python work. Done on the event loop they freeze every other
        # request for the duration; in a thread they cost only this stage.
        computed = await asyncio.to_thread(
            _profile_object, context.cache, obj.id,
            [(c.id, c.name) for c in columns],
        )
        if not computed:
            continue

        for column_id, stats in computed:
            await upsert_column_stats(
                context.db, source_column_id=column_id, **stats)
            written += 1
        obj.last_profiled_at = datetime.utcnow()

    return {"columns_profiled": written}


# ── stage 4 ─────────────────────────────────────────────────────────────────

async def stage_infer_keys(context: CatalogContext) -> dict:
    """Find the foreign keys nobody declared."""
    from ...core.config import settings

    tables = [
        {
            "dataset_id": obj.id, "name": obj.name,
            "columns": [
                {"name": c.name, "dtype": c.dtype}
                for c in context.columns_by_object.get(obj.id, [])
            ],
        }
        for obj in context.objects
    ]

    # The expensive stage: quadratic candidate generation plus a DuckDB join per
    # surviving pair. Measured at ~4 minutes on an 82-table source — four
    # minutes during which, on the event loop, the API answered nothing at all.
    candidates = await asyncio.to_thread(
        infer_keys.infer_foreign_keys,
        tables, context.cache,
        overlap_high=settings.fk_overlap_high,
        overlap_review=settings.fk_overlap_review,
    )

    for candidate in candidates:
        await _upsert_source_relationship(
            context,
            from_object_id=candidate.from_dataset_id, from_column=candidate.from_column,
            to_object_id=candidate.to_dataset_id, to_column=candidate.to_column,
            source="inferred", confidence=candidate.confidence,
            evidence=candidate.evidence, cardinality=candidate.cardinality,
        )

    high = sum(1 for c in candidates if c.evidence.get("high_confidence"))
    return {"proposed": len(candidates), "high_confidence": high,
            "needs_review": len(candidates) - high}


# ── stage 5 ─────────────────────────────────────────────────────────────────

async def stage_describe(context: CatalogContext) -> dict:
    """Semantic types, roles, deprecation, and the account of the database.

    Three levels of description, because they answer different questions:
    the SOURCE overview tells a person what this database is; the OBJECT
    descriptions tell them what each table holds; the COLUMN descriptions give
    an agent what it needs to compose a query.
    """
    from ...core.config import settings

    # Every sample this stage needs, read ONCE, in a single hop off the loop.
    #
    # The loop below reads each object's sample, and `describe_one` further down
    # then read the SAME sample again -- 164 lock-serialised DuckDB reads on the
    # measured source where 82 would do. Reading them all inside one thread also
    # takes the cache lock 82 times instead of 164 and costs one thread handoff
    # instead of 164.
    def _read_all() -> dict:
        return {o.id: context.cache.get_sample(o.id) for o in context.objects}

    samples = await asyncio.to_thread(_read_all)

    typed = 0
    for obj in context.objects:
        rows = samples.get(obj.id)
        detected = context.sample_types.get(obj.id, {})
        columns = context.columns_by_object.get(obj.id, [])

        payload = [{
            "name": c.name, "dtype": c.dtype,
            "sample_values": [r.get(c.name) for r in rows][:50] if rows else [],
            "stats": {"row_count": len(rows) if rows else None},
        } for c in columns]

        proposals = infer_semantic.apply_column_inference(payload, {})
        by_name = {c.name: c for c in columns}
        for name, proposed in proposals.items():
            column = by_name.get(name)
            if column is None:
                continue
            semantic_type = detected.get(name) or proposed.get("semantic_type")
            if semantic_type and not column.semantic_type:
                column.semantic_type = semantic_type
                typed += 1

        flagged, _ = infer_semantic.detect_deprecation(
            obj.name, obj.row_count_estimate)
        if flagged and not obj.is_deprecated:
            obj.is_deprecated = True

    if not (context.allow_llm and context.llm_client and context.objects):
        return {"semantic_types": typed, "llm_used": False,
                "objects_described": 0, "columns_described": 0,
                "source_overview": False}

    # ── the database-level pass ────────────────────────────────────────────
    by_id = {o.id: o for o in context.objects}
    rels = (await context.db.execute(
        select(SourceRelationship).where(
            SourceRelationship.data_source_id == context.data_source_id)
    )).scalars().all()

    payload_tables = [{
        "name": o.name,
        "kind": o.kind,
        "row_count": o.row_count_estimate,
        "columns": [
            {"name": c.name, "semantic_type": c.semantic_type,
             "role": "identifier" if c.is_primary_key else None}
            for c in context.columns_by_object.get(o.id, [])
        ],
    } for o in context.objects]

    payload_rels = [{
        "from_table": by_id[r.from_object_id].name, "from_column": r.from_column,
        "to_table": by_id[r.to_object_id].name, "to_column": r.to_column,
    } for r in rels if r.from_object_id in by_id and r.to_object_id in by_id]

    result = await infer_semantic.describe_source_with_llm(
        context.source.name, payload_tables, context.llm_client,
        allow=True, relationships=payload_rels,
    ) or {}

    overview = result.get("overview")
    wrote_overview = False
    if overview and context.source.description_source != "confirmed":
        context.source.description = overview
        context.source.description_source = "inferred"
        wrote_overview = True

    objects_described = 0

    # ── per-table column descriptions, concurrently ────────────────────────
    # One call per table, and an 82-table source at ~7s each is ten minutes of
    # wall time during which the sync looks hung. The calls are independent, so
    # they overlap — bounded, so one sync cannot saturate a model endpoint that
    # other work is also using.
    # Bounded by the LLM client's own gate now (services/llm.py), not a local
    # semaphore -- the sync's describe stage and agent runs share one Qwen
    # box, and a bound that only covers this stage's calls would let a sync
    # double the endpoint's load during an agent run. infer_semantic passes
    # background=True on these calls, which also keeps this stage out of the
    # slots reserved for interactive work (llm_reserved_interactive).

    async def describe_one(obj):
        columns = context.columns_by_object.get(obj.id, [])
        if not columns:
            return obj, {}
        rows = samples.get(obj.id)
        payload = [{
            "name": c.name, "dtype": c.dtype,
            "sample_values": [r.get(c.name) for r in rows][:5] if rows else [],
        } for c in columns]
        return obj, await infer_semantic.describe_with_llm(
            obj.name, payload, context.llm_client, allow=True,
            kind=obj.kind or "table")

    # return_exceptions keeps one failed table from cancelling the rest.
    results = await asyncio.gather(
        *(describe_one(o) for o in context.objects), return_exceptions=True)

    columns_described = 0
    for result in results:
        if isinstance(result, BaseException):
            logger.info("a column-description call failed", exc_info=result)
            continue
        obj, descriptions = result
        descriptions = dict(descriptions or {})

        # The table's own sentence comes back on the same call as its columns',
        # so a big database costs no extra requests for it.
        table_text = descriptions.pop(infer_semantic.TABLE_DESCRIPTION_KEY, None)
        if table_text and obj.description_source != "confirmed":
            obj.description = table_text
            obj.description_source = "inferred"
            objects_described += 1

        by_name = {c.name: c for c in context.columns_by_object.get(obj.id, [])}
        for name, text_value in descriptions.items():
            column = by_name.get(name)
            if column is not None and column.description_source != "confirmed":
                column.description = text_value
                column.description_source = "inferred"
                columns_described += 1

    # ── enum value labels: what a coded column's values MEAN ───────────────
    # T2 / L3 gap #2: top_k already knows st_cd holds 1, 2, 3 -- the meaning
    # (3 = cancelled) is what this adds. One batched call per object, asking
    # only about columns whose top_k is short enough to be an enumeration
    # rather than free-form data, and skipping anything a human already
    # labelled -- same never-overwrite-a-confirmation rule as descriptions.
    all_column_ids = [
        c.id for cols in context.columns_by_object.values() for c in cols]
    top_k_by_column_id: dict[int, list] = {}
    if all_column_ids:
        stats_rows = (await context.db.execute(
            select(ColumnStats).where(
                ColumnStats.source_column_id.in_(all_column_ids))
        )).scalars().all()
        top_k_by_column_id = {
            s.source_column_id: s.top_k for s in stats_rows if s.top_k}

    async def draft_labels_one(obj):
        columns = context.columns_by_object.get(obj.id, [])
        eligible = [
            c for c in columns
            if c.enum_labels_source != "confirmed"
            and top_k_by_column_id.get(c.id)
            and len(top_k_by_column_id[c.id]) <= infer_semantic.ENUM_LABEL_MAX_VALUES
        ]
        if not eligible:
            return obj, {}
        payload = [{
            "name": c.name, "dtype": c.dtype, "description": c.description,
            "top_k": top_k_by_column_id[c.id],
        } for c in eligible]
        return obj, await infer_semantic.draft_enum_labels(
            obj.name, payload, context.llm_client, allow=True)

    label_results = await asyncio.gather(
        *(draft_labels_one(o) for o in context.objects), return_exceptions=True)

    labels_drafted = 0
    for result in label_results:
        if isinstance(result, BaseException):
            logger.info("an enum-label call failed", exc_info=result)
            continue
        obj, labels = result
        by_name = {c.name: c for c in context.columns_by_object.get(obj.id, [])}
        for name, mapping in labels.items():
            column = by_name.get(name)
            if column is not None and column.enum_labels_source != "confirmed":
                column.enum_labels = mapping
                column.enum_labels_source = "inferred"
                labels_drafted += 1

    return {
        "semantic_types": typed, "llm_used": True,
        "source_overview": wrote_overview,
        "objects_described": objects_described,
        "columns_described": columns_described,
        "labels_drafted": labels_drafted,
    }


# ── stage 5.5 ────────────────────────────────────────────────────────────────

async def stage_entities(context: CatalogContext) -> dict:
    """E2 / Tier 2 retrieval (spec section 5): what named business objects
    does this database model, and what is one row of each?

    One complete_json call for the whole source -- unlike the per-table enum
    label pass, an entity's existence is a property of the CATALOG's shape
    (which tables exist and how they relate), not of any single table, so
    asking per-object would mean asking the same question eighty times with
    eighty different slivers of context.

    Same ladder discipline as everything else this pipeline drafts: a row
    already `confirmed` (a human edited or approved it on the review surface)
    is never touched by a later draft -- see `SourceColumn.enum_labels_source`
    for the same rule applied to enum labels. Isolated like every other
    enrichment stage: `_run_stage` records a failure here as a failed STAGE,
    never an aborted run.
    """
    if not (context.allow_llm and context.llm_client and context.objects):
        return {"llm_used": False, "drafted": 0}

    payload_tables = [{
        "name": o.name, "kind": o.kind, "row_count": o.row_count_estimate,
        "columns": [c.name for c in context.columns_by_object.get(o.id, [])],
    } for o in context.objects]

    proposals = await infer_semantic.draft_entities(
        context.source.name, payload_tables, context.llm_client, allow=True)
    if not proposals:
        return {"llm_used": True, "drafted": 0}

    existing = (await context.db.execute(
        select(Entity).where(Entity.data_source_id == context.data_source_id)
    )).scalars().all()
    by_name = {e.name: e for e in existing}

    drafted = 0
    for proposal in proposals:
        name = proposal["name"]
        row = by_name.get(name)
        if row is None:
            row = Entity(org_id=context.org_id, data_source_id=context.data_source_id,
                        name=name, source=store.INFERRED)
            context.db.add(row)
            by_name[name] = row
        elif row.source == store.CONFIRMED:
            # Never overwritten by a later draft -- the same rule that
            # protects a human-confirmed enum label or description.
            continue

        row.business_name = proposal["business_name"] or row.business_name
        row.grain = proposal["grain"] or row.grain
        row.description = proposal["description"] or row.description
        row.primary_object = proposal["primary_object"] or row.primary_object
        row.source = store.INFERRED
        drafted += 1

    return {"llm_used": True, "drafted": drafted}


# ── stage 6 ─────────────────────────────────────────────────────────────────

async def stage_drift(context: CatalogContext) -> dict:
    """Fingerprint the catalog and record any change."""
    latest = (await context.db.execute(
        select(SchemaVersion)
        .where(SchemaVersion.data_source_id == context.data_source_id)
        .order_by(SchemaVersion.id.desc()).limit(1)
    )).scalar_one_or_none()

    annotations = [
        {"table": o.name, "name": c.name, "kind": "column",
         "source": c.description_source, "detail": c.description}
        for o in context.objects
        for c in context.columns_by_object.get(o.id, [])
        if c.description
    ]

    event = drift.detect(
        latest.fingerprint if latest else None,
        (latest.diff or {}).get("_schema") if latest else None,
        context.schema_columns, annotations,
    )
    if event is None:
        return {"changed": False}

    payload = dict(event)
    payload["_schema"] = context.schema_columns
    context.db.add(SchemaVersion(
        data_source_id=context.data_source_id, org_id=context.org_id,
        fingerprint=event["fingerprint"], diff=payload,
    ))
    # T6: bump the source's cache epoch in the same transaction as the
    # SchemaVersion row above -- every DirectQuery cache key for this source
    # folds this in, so a drift-changed sync makes every existing cache entry
    # unaddressable without needing a sweeper.
    context.source.cache_epoch = (context.source.cache_epoch or 0) + 1

    return {"changed": True, "baseline": event["is_baseline"],
            "summary": drift.summarize(event),
            "orphaned_annotations": len(event["orphaned_annotations"])}


# ── stage 7 ─────────────────────────────────────────────────────────────────

async def stage_link_datasets(context: CatalogContext) -> dict:
    """Give the datasets already built from this source their provenance.

    `link_columns` runs at import time, but the ordinary first run of this
    product does not import after a sync -- it connects, browses, imports, and
    syncs afterwards if at all. Every dataset made in that window would carry
    NULL provenance for the rest of its life, because linking is idempotent and
    nothing else ever revisits it. The catalog would describe the columns
    perfectly and no dashboard would ever see a word of it.

    So the sync closes the loop from its own side: the moment a catalog exists,
    every dataset pointing at this source is linked against it. Cheap (a name
    match per column, no customer database involved) and idempotent -- a column
    that already has a link keeps it.

    Guarded like every other stage: failing here must not fail a sync whose real
    work -- describing the database -- has already succeeded.
    """
    from ...models.models import Dataset
    from .. import knowledge

    datasets = list((await context.db.execute(
        select(Dataset).where(Dataset.data_source_id == context.data_source_id)
    )).scalars().all())

    linked = 0
    touched = 0
    for ds in datasets:
        got = await knowledge.link_columns(context.db, ds)
        if got:
            linked += got
            touched += 1
    if linked:
        await context.db.flush()
    return {"datasets": len(datasets), "datasets_linked": touched,
            "columns_linked": linked}


# ── runner ──────────────────────────────────────────────────────────────────

async def run_catalog_sync(
    db, source: DataSource, *, cache, llm_client=None, allow_llm: bool = False,
    source_config: dict | None = None, trigger: str = "manual",
    run: SyncRun | None = None,
) -> SyncRun:
    """Describe a whole database from its connection.

    Stage 1 is the only one whose failure aborts: without a catalog there is
    nothing for any later stage to describe. Everything after it is guarded
    independently, so one blocked table or an unreachable model costs only its
    own contribution.
    """
    if run is None:
        run = SyncRun(data_source_id=source.id, org_id=source.org_id,
                      trigger=trigger, status="running", stages=[])
        db.add(run)
        await db.flush()

    context = CatalogContext(
        db, source, cache=cache, llm_client=llm_client,
        allow_llm=allow_llm, source_config=source_config,
    )
    context.run = run

    discover = await _run_stage(context, "discover", stage_discover)
    if discover.status != "ok":
        run.status = "failed"
        run.error = discover.error
        run.stages = [s.as_dict() for s in context.stages]
        run.finished_at = datetime.utcnow()
        await db.flush()
        return run

    await _run_stage(context, "sample", stage_sample)
    await _run_stage(context, "profile", stage_profile)

    has_any_sample = await asyncio.to_thread(
        lambda: any(context.cache.has_sample(o.id) for o in context.objects))
    if has_any_sample:
        await _run_stage(context, "infer_keys", stage_infer_keys)
    else:
        _skip(context, "infer_keys", "no cached samples")

    await _run_stage(context, "describe", stage_describe)
    await _run_stage(context, "entities", stage_entities)
    await _run_stage(context, "drift", stage_drift)
    await _run_stage(context, "link_datasets", stage_link_datasets)

    failed = [s for s in context.stages if s.status == "failed"]
    run.status = "ok" if not failed else "partial"
    run.stages = [s.as_dict() for s in context.stages]
    run.finished_at = datetime.utcnow()
    await db.flush()
    return run
