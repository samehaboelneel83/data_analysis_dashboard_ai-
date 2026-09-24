"""The six-stage metadata pipeline.

    1 discover    tables and columns
    2 profile     statistics, top_k
    3 sample      masked rows into the DuckDB cache
    4 infer_keys  declared foreign keys read from the source, plus candidates
                  proposed by value-overlap inference for the rest
    5 infer_sem   semantic types, roles, deprecation, descriptions
    6 drift       fingerprint, diff, notify

STAGES FAIL INDEPENDENTLY
--------------------------
A source that blocks TABLESAMPLE, a warehouse that times out on one wide table,
a GPU host that is down — none of these should cost you the other five stages'
output. Each stage is guarded, records its own status in `sync_runs.stages`, and
the run continues wherever the next stage does not depend on it.

The one real dependency is stage 4 on stage 3: foreign-key inference reads the
sample cache, so if sampling produced nothing there is nothing to infer from and
the stage is skipped rather than run against an empty cache (which would score
every overlap 0.0 and look like "no relationships found" — a wrong answer
dressed as a real one).

A run is `failed` only when stage 1 fails. Without tables there is nothing for
any other stage to describe.

WHY THE ADVISORY LOCK
----------------------
This runs under N uvicorn workers and a background scheduler. Two concurrent
syncs of one source would interleave their writes to the same rows and produce a
catalog that reflects neither. The project already solved this shape in
refresh_scheduler.py; the same convention is used here rather than a second one.
"""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select, text

from ...models.models import (Dataset, DataSource, DatasetColumn, Relationship,
                              SchemaVersion, SyncRun)
from .. import pii
from . import drift, infer_keys, infer_semantic, sample, store

logger = logging.getLogger(__name__)

#: Distinct from the startup and scheduler keys so the three cannot collide.
_SYNC_LOCK_BASE = 0x5DA7A5C0


@dataclass
class StageResult:
    name: str
    status: str                 # ok | failed | skipped
    ms: int = 0
    detail: dict = field(default_factory=dict)
    error: str | None = None

    def as_dict(self) -> dict:
        out = {"name": self.name, "status": self.status, "ms": self.ms}
        if self.detail:
            out["detail"] = self.detail
        if self.error:
            out["error"] = self.error
        return out


class SyncContext:
    """Carries state between stages of one run."""

    def __init__(self, db, data_source_id: int, org_id: int, *, cache, llm_client=None,
                 allow_llm: bool = False, source_config: dict | None = None):
        self.db = db
        self.data_source_id = data_source_id
        self.org_id = org_id
        self.cache = cache
        self.llm_client = llm_client
        self.allow_llm = allow_llm
        # Connection config for the live-sampling path. None for an import-only
        # source, and None in tests that seed the cache directly.
        self.source_config = source_config
        # Semantic types detected during sampling, before masking. Stage 5 reuses
        # them rather than re-classifying the masked values, which would now
        # classify the MASK rather than the data.
        self.sample_types: dict[int, dict] = {}

        # The row to publish per-stage progress into, if the caller wants it.
        self.run: SyncRun | None = None

        self.datasets: list[Dataset] = []
        self.columns_by_dataset: dict[int, list[DatasetColumn]] = {}
        self.schema_columns: list[dict] = []
        self.stages: list[StageResult] = []


async def _run_stage(context: SyncContext, name: str, fn) -> StageResult:
    """Execute one stage, recording its outcome either way.

    The broad except is the point of the function: a stage raising must become a
    recorded failure, not an aborted run. Anything narrower would let an
    unanticipated driver error take down the other five stages.
    """
    started = time.monotonic()
    try:
        detail = await fn(context) or {}
        result = StageResult(name, "ok", int((time.monotonic() - started) * 1000), detail)
    except Exception as exc:
        logger.exception("metadata sync stage %s failed", name)
        # A stage that raised mid-write can leave partial changes pending on
        # the session (e.g. some but not all of a batch flushed). Without
        # rolling those back, the progress-publish commit just below would
        # persist them anyway -- a "failed" stage silently keeping its
        # half-done writes. Rolling back only discards uncommitted state;
        # `context.run` was already flushed/committed by an earlier stage or
        # the caller, so it survives (SQLAlchemy just re-fetches it on next
        # access) and the `context.run.stages = ...` assignment right after
        # this still lands cleanly.
        try:
            await context.db.rollback()
        except Exception:
            logger.warning(
                "could not roll back after stage %s failed", name, exc_info=True)
        result = StageResult(
            name, "failed", int((time.monotonic() - started) * 1000),
            error=f"{type(exc).__name__}: {exc}",
        )
    context.stages.append(result)

    # Publish progress after every stage. Without this the row only changes at
    # the very end and the UI's polling has nothing to show.
    if context.run is not None:
        context.run.stages = [st.as_dict() for st in context.stages]
        try:
            await context.db.commit()
        except Exception:
            # Progress reporting must never be able to fail the run it reports on.
            logger.warning("could not publish sync progress", exc_info=True)

    return result


def _skip(context: SyncContext, name: str, why: str) -> StageResult:
    result = StageResult(name, "skipped", detail={"reason": why})
    context.stages.append(result)
    return result


# ── stages ──────────────────────────────────────────────────────────────────

async def stage_discover(context: SyncContext) -> dict:
    """Load the datasets belonging to this source, and their columns."""
    rows = (await context.db.execute(
        select(Dataset).where(
            Dataset.data_source_id == context.data_source_id,
            Dataset.org_id == context.org_id,
        )
    )).scalars().all()
    context.datasets = list(rows)

    for dataset in context.datasets:
        columns = (await context.db.execute(
            select(DatasetColumn).where(DatasetColumn.dataset_id == dataset.id)
        )).scalars().all()
        context.columns_by_dataset[dataset.id] = list(columns)
        for column in columns:
            context.schema_columns.append({
                "table": dataset.name,
                "name": column.name,
                "dtype": column.dtype,
                "nullable": True,
            })

    return {"datasets": len(context.datasets), "columns": len(context.schema_columns)}


def _sample_import_dataset(dataset, n: int) -> list[dict] | None:
    """Sample an uploaded dataset from its parsed frame.

    Goes through the existing frame_cache rather than re-reading the file: a
    sync of twenty datasets would otherwise re-parse twenty CSVs that the app
    already has in memory.

    S1 note: deliberately NOT row-level-security filtered. This sample feeds the
    org-wide metadata/agent catalog (schema shape, column semantic types) for an
    admin-triggered sync with no per-viewer identity to resolve RLS against --
    it is a system-plane operation, not a request one. The values themselves are
    PII-masked before caching (stage_sample, below) and the catalog is schema
    metadata, not row data; any actual query a user later runs against this
    dataset still goes through the request-time RLS choke points (get_widget_data
    / the dataset routers / agent graph.py's dataset-mode base-frame filtering).
    """
    import pathlib

    from ...core.config import settings
    from ..ingest import load_file
    from ..frame_cache import get_frame

    # None means "could not read", which is different from an empty table --
    # see stage_sample. A dataset with no file is not an empty dataset.
    if not dataset.filename:
        return None
    path = pathlib.Path(settings.upload_dir) / dataset.filename
    if not path.exists():
        return None
    try:
        frame = get_frame(str(path))
    except Exception:
        frame = load_file(str(path))
    return sample.reservoir_sample_frame(frame, n)


def _sample_sql_dataset(dataset, cfg: dict, n: int) -> list[dict] | None:
    """Sample a live SQL table.

    The strategy is chosen from the source's capabilities (TABLESAMPLE where the
    engine supports it on a physical table, an ordered-random fallback
    otherwise), and every generated query is row-bounded — an unbounded sample
    against a customer's production table is the exact failure the metadata
    plane exists to prevent.
    """
    from sqlalchemy import text

    from .. import connectors
    from ..engines import get_engine

    table = dataset.source_table
    if not table:
        return None

    family = connectors.sql_family_of(cfg) or "postgresql"
    row_count = dataset.row_count or None
    strategy = sample.choose_strategy(family=family, kind="table", row_count=row_count)

    engine = get_engine(cfg)
    with engine.connect() as conn:
        sql = sample.build_sample_sql(
            table, family=family, strategy=strategy, n=n, row_count=row_count,
        )
        rows = [dict(r._mapping) for r in conn.execute(text(sql))]

        # An empty result from TABLESAMPLE is not evidence the table is empty:
        # it samples PAGES, so a small or unluckily-laid-out table can return
        # nothing at all. Confirm with a bounded ordered-random read before
        # believing it. A genuinely empty table costs one cheap extra query;
        # a table TABLESAMPLE merely missed gets its metadata instead of
        # silently contributing nothing to the whole pipeline.
        if not rows and strategy == "tablesample":
            fallback = sample.build_sample_sql(
                table, family=family, strategy="head", n=n, row_count=row_count,
            )
            rows = [dict(r._mapping) for r in conn.execute(text(fallback))]

    return rows


async def stage_sample(context: SyncContext) -> dict:
    """Pull ~1000 rows per dataset into the local cache, masked.

    This is the stage that makes the two-plane split real: every later question
    about structure is answered from here rather than from the customer's
    database.

    A dataset that cannot be sampled is skipped, not fatal. One unreadable table
    -- dropped, renamed, permission revoked -- must not cost the other nineteen
    their metadata.
    """
    from ...core.config import settings

    n = settings.metadata_sample_rows
    sampled = 0
    skipped = 0
    empty = 0
    masked_columns = 0
    failures: list[str] = []

    cfg = None
    if context.source_config:
        cfg = dict(context.source_config)

    for dataset in context.datasets:
        try:
            if dataset.mode == "directquery" and cfg:
                rows = await asyncio.to_thread(_sample_sql_dataset, dataset, cfg, n)
            else:
                rows = await asyncio.to_thread(_sample_import_dataset, dataset, n)
        except Exception as exc:
            # Could not read it. Leave any previous sample alone -- stale
            # metadata beats none, and the next run will refresh it.
            failures.append(f"{dataset.name}: {type(exc).__name__}")
            continue

        if rows is None:
            skipped += 1
            continue

        if not rows:
            # Genuinely empty, and confirmed as such by the sampler's fallback.
            # Worth recording — emptiness is one of the deprecation signals
            # Stage 5 looks for — but also worth REPORTING, because a sync whose
            # tables all came back empty produced no metadata and should not
            # look identical to one that worked.
            context.cache.put_sample(dataset.id, [])
            empty += 1
            continue

        # Classify from the real values, then mask, then cache. The order is the
        # point: detection needs the true values, and nothing after this line
        # ever sees them.
        column_types: dict[str, str | None] = {}
        for name in rows[0].keys():
            values = [row.get(name) for row in rows]
            column_types[name] = pii.detect_semantic_type(values)

        masked = pii.mask_rows(rows, column_types)
        masked_columns += sum(1 for k in column_types.values() if pii.is_pii(k))

        context.cache.put_sample(dataset.id, masked)
        context.sample_types[dataset.id] = column_types
        sampled += 1

    evicted = context.cache.evict_if_over_budget()

    return {
        "datasets_sampled": sampled,
        "datasets_skipped": skipped,
        "datasets_empty": empty,
        "pii_columns_masked": masked_columns,
        "evicted": len(evicted),
        "failures": failures or None,
    }


async def stage_profile(context: SyncContext) -> dict:
    """Persist statistics for every column that has a cached sample.

    Reads from the sample cache rather than the source: the samples are already
    here, and re-querying a customer's database for numbers we can compute
    locally is exactly the cost the two-plane split exists to remove.
    """
    written = 0
    for dataset in context.datasets:
        rows = context.cache.get_sample(dataset.id)
        if not rows:
            continue
        for column in context.columns_by_dataset.get(dataset.id, []):
            values = [row.get(column.name) for row in rows]
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

            await store.upsert_column_stats(
                context.db, dataset_column_id=column.id,
                null_ratio=round((len(values) - len(present)) / len(values), 6) if values else None,
                distinct_count=distinct,
                top_k=top_k,
                min_value=str(min(present)) if present else None,
                max_value=str(max(present)) if present else None,
                # Computed over a SAMPLE, not the table. The distinction the
                # `exact` flag exists to carry.
                exact=False,
            )
            written += 1
        dataset.last_profiled_at = datetime.utcnow()
    return {"columns_profiled": written}


def _read_declared_fks(cfg: dict, table_names: list[str]) -> dict[str, list[dict]]:
    """Real foreign keys read from a live SQL source's own catalog, per table.

    A declared key is a fact the schema enforces, not a guess — see
    `metadata/store.py`'s precedence ladder. Single-column only, matching this
    project's relationship rows (from one column to one column); a composite
    FK is recorded as skipped rather than truncated to its first column, which
    would produce a join that looks declared but is wrong. Mirrors
    `introspect.py`'s identical rule for the catalog_sync (whole-database)
    pipeline -- this is the same rule applied per-Dataset instead of per
    SourceObject.
    """
    from sqlalchemy import inspect

    from ..engines import get_engine

    engine = get_engine(cfg)
    inspector = inspect(engine)
    out: dict[str, list[dict]] = {}
    for name in table_names:
        try:
            fks = inspector.get_foreign_keys(name) or []
        except Exception:
            logger.debug("could not read foreign keys for %s", name, exc_info=True)
            continue
        entries = []
        for fk in fks:
            local = fk.get("constrained_columns") or []
            remote = fk.get("referred_columns") or []
            target = fk.get("referred_table")
            if target and len(local) == 1 and len(remote) == 1:
                entries.append({"from_column": local[0], "to_table": target,
                                "to_column": remote[0]})
            elif target:
                logger.debug("skipping composite foreign key on %s -> %s", name, target)
        if entries:
            out[name] = entries
    return out


async def _seed_declared_keys(context: SyncContext) -> int:
    """Seed declared relationships for DirectQuery datasets from the live
    source's own catalog, before inference runs.

    Only DirectQuery-mode datasets map onto a real table this can introspect;
    an imported file has no live connection to read a FOREIGN KEY from. A
    dataset whose FK target was never itself imported as a Dataset has no
    Relationship row to point the edge at, so it is skipped -- there is
    nothing here for it to join to.

    Writes through `store.upsert_declared_relationship`, which enforces the
    confirmed > declared > inferred ladder: an existing inferred proposal for
    the same edge is upgraded, an existing confirmation is left alone, and a
    resync of the same declared key is a no-op rather than a duplicate row.
    """
    if not context.source_config:
        return 0

    by_table_name = {
        dataset.source_table: dataset
        for dataset in context.datasets
        if dataset.mode == "directquery" and dataset.source_table
    }
    if not by_table_name:
        return 0

    fk_map = await asyncio.to_thread(
        _read_declared_fks, context.source_config, list(by_table_name))

    written = 0
    for table_name, entries in fk_map.items():
        from_dataset = by_table_name.get(table_name)
        if from_dataset is None:
            continue
        for fk in entries:
            to_dataset = by_table_name.get(fk["to_table"])
            if to_dataset is None:
                continue
            await store.upsert_declared_relationship(
                context.db, org_id=context.org_id,
                from_dataset_id=from_dataset.id, from_column=fk["from_column"],
                to_dataset_id=to_dataset.id, to_column=fk["to_column"],
                cardinality="many_to_one",
            )
            written += 1

    return written


async def stage_infer_keys(context: SyncContext) -> dict:
    """Seed declared foreign keys, then propose the rest through inference.

    Declared wins over inference by construction here: it runs first and
    writes through the provenance store, so an inferred candidate for the same
    edge computed a moment later cannot downgrade it -- see
    `store._may_overwrite`.
    """
    from ...core.config import settings

    # Seeding needs a live source connection; inference does not. A seeding
    # failure (engine build, catalog read) must not take value-overlap
    # inference down with it -- the stage still produces inferred edges.
    try:
        declared = await _seed_declared_keys(context)
    except Exception:
        logger.warning("declared-FK seeding failed; continuing with inference",
                       exc_info=True)
        declared = 0

    tables = [
        {
            "dataset_id": dataset.id,
            "name": dataset.name,
            "columns": [
                {"name": c.name, "dtype": c.dtype}
                for c in context.columns_by_dataset.get(dataset.id, [])
            ],
        }
        for dataset in context.datasets
    ]

    candidates = infer_keys.infer_foreign_keys(
        tables, context.cache,
        overlap_high=settings.fk_overlap_high,
        overlap_review=settings.fk_overlap_review,
    )

    written = 0
    for candidate in candidates:
        # Returns the STORED row, which may be a human's confirmation rather
        # than this proposal. That is the contract; nothing here overrides it.
        await store.upsert_inferred_relationship(
            context.db, org_id=context.org_id,
            from_dataset_id=candidate.from_dataset_id, from_column=candidate.from_column,
            to_dataset_id=candidate.to_dataset_id, to_column=candidate.to_column,
            confidence=candidate.confidence,
            evidence=candidate.evidence,
            cardinality=candidate.cardinality,
        )
        written += 1

    high = sum(1 for c in candidates if c.evidence.get("high_confidence"))
    return {"proposed": written, "high_confidence": high,
            "needs_review": written - high, "declared": declared}


async def stage_infer_semantic(context: SyncContext) -> dict:
    """Semantic types, roles, deprecation, and optionally descriptions."""
    typed = 0
    described = 0

    for dataset in context.datasets:
        rows = context.cache.get_sample(dataset.id)
        columns = context.columns_by_dataset.get(dataset.id, [])

        # Types detected during sampling, BEFORE masking. Re-classifying the
        # cached rows here would classify the mask, not the data — a masked
        # email no longer looks like an email, so every PII column would come
        # back unclassified.
        detected = context.sample_types.get(dataset.id, {})

        payload = []
        for column in columns:
            sample_values = [r.get(column.name) for r in rows][:50] if rows else []
            payload.append({
                "name": column.name,
                "dtype": column.dtype,
                "sample_values": sample_values,
                "detected_semantic_type": detected.get(column.name),
                "stats": {"row_count": len(rows) if rows else None},
            })

        proposals = infer_semantic.apply_column_inference(
            payload, (dataset.column_meta or {})
        )
        by_name = {c.name: c for c in columns}
        for name, proposed in proposals.items():
            column = by_name.get(name)
            if column is None:
                continue
            # Pre-mask detection wins where it found something; it saw the real
            # values and the classifier here did not.
            semantic_type = detected.get(name) or proposed.get("semantic_type")
            if semantic_type and not column.semantic_type:
                column.semantic_type = semantic_type
                typed += 1

        flagged, reason = infer_semantic.detect_deprecation(
            dataset.name, len(rows) if rows is not None else None
        )
        if flagged and not dataset.is_deprecated:
            dataset.is_deprecated = True
            logger.info("dataset %s flagged deprecated: %s", dataset.name, reason)

        descriptions = await infer_semantic.describe_with_llm(
            dataset.name,
            [{"name": c.name, "dtype": c.dtype} for c in columns],
            context.llm_client,
            allow=context.allow_llm,
        )
        for name, text_value in descriptions.items():
            column = by_name.get(name)
            # An author's description outranks a generated one, permanently.
            if column is not None and column.description_source != "confirmed":
                column.description = text_value
                column.description_source = "inferred"
                described += 1

    # The database-level pass. Runs once for the whole source rather than per
    # table, because the useful thing to say about a database is how its parts
    # fit together -- which is not visible from inside any one table.
    overview_written = False
    tables_described = 0
    if context.allow_llm and context.llm_client and context.datasets:
        source = await context.db.get(DataSource, context.data_source_id)
        by_id = {d.id: d for d in context.datasets}

        payload_tables = [
            {
                "name": d.name,
                "row_count": len(context.cache.get_sample(d.id)) or None,
                "columns": [
                    {"name": c.name, "semantic_type": c.semantic_type,
                     "role": (d.column_meta or {}).get(c.name, {}).get("role")}
                    for c in context.columns_by_dataset.get(d.id, [])
                ],
            }
            for d in context.datasets
        ]

        rel_rows = (await context.db.execute(
            select(Relationship).where(
                Relationship.org_id == context.org_id,
                Relationship.from_dataset_id.in_(list(by_id)),
            )
        )).scalars().all()
        payload_rels = [
            {
                "from_table": by_id[r.from_dataset_id].name, "from_column": r.from_column,
                "to_table": by_id[r.to_dataset_id].name, "to_column": r.to_column,
            }
            for r in rel_rows
            if r.from_dataset_id in by_id and r.to_dataset_id in by_id
        ]

        result = await infer_semantic.describe_source_with_llm(
            source.name if source else "database", payload_tables,
            context.llm_client, allow=True, relationships=payload_rels,
        )

        overview = (result or {}).get("overview")
        # A human's description outranks a generated one, permanently.
        if overview and source is not None and source.description_source != "confirmed":
            source.description = overview
            source.description_source = "inferred"
            overview_written = True

        for name, text_value in (result or {}).get("tables", {}).items():
            for dataset in context.datasets:
                if dataset.name == name and dataset.description_source != "confirmed":
                    dataset.description = text_value
                    dataset.description_source = "inferred"
                    tables_described += 1

    return {"semantic_types": typed, "descriptions": described,
            "tables_described": tables_described,
            "source_overview": overview_written,
            "llm_used": bool(context.allow_llm and context.llm_client)}


async def stage_drift(context: SyncContext) -> dict:
    """Fingerprint the schema and record any change."""
    latest = (await context.db.execute(
        select(SchemaVersion)
        .where(SchemaVersion.data_source_id == context.data_source_id)
        .order_by(SchemaVersion.id.desc())
        .limit(1)
    )).scalar_one_or_none()

    previous_columns = (latest.diff or {}).get("_schema") if latest else None

    annotations = [
        {"table": d.name, "name": c.name, "kind": "column",
         "source": c.description_source, "detail": c.description}
        for d in context.datasets
        for c in context.columns_by_dataset.get(d.id, [])
        if c.description
    ]

    event = drift.detect(
        latest.fingerprint if latest else None,
        previous_columns,
        context.schema_columns,
        annotations,
    )
    if event is None:
        return {"changed": False}

    # The full schema is carried inside the diff so the NEXT run can produce a
    # real column-level comparison rather than only "the hash moved".
    payload = dict(event)
    payload["_schema"] = context.schema_columns

    context.db.add(SchemaVersion(
        data_source_id=context.data_source_id,
        org_id=context.org_id,
        fingerprint=event["fingerprint"],
        diff=payload,
    ))
    # T6: bump the source's cache epoch in the same transaction as the
    # SchemaVersion row above -- see catalog_sync.stage_drift's identical
    # comment. Unlike catalog_sync, this context doesn't already hold the
    # loaded DataSource, so it's fetched fresh; a dataset-mode sync with no
    # DataSource behind it (context.data_source_id pointing at nothing, which
    # shouldn't happen but isn't asserted against) leaves the epoch alone
    # rather than raising.
    source = await context.db.get(DataSource, context.data_source_id)
    if source is not None:
        source.cache_epoch = (source.cache_epoch or 0) + 1

    return {
        "changed": True,
        "baseline": event["is_baseline"],
        "summary": drift.summarize(event),
        "orphaned_annotations": len(event["orphaned_annotations"]),
    }


# ── runner ──────────────────────────────────────────────────────────────────

async def run_sync(
    db, data_source_id: int, org_id: int, *,
    cache, llm_client=None, allow_llm: bool = False, trigger: str = "manual",
    source_config: dict | None = None, run: SyncRun | None = None,
) -> SyncRun:
    """Run all six stages and record the outcome.

    Always returns a persisted SyncRun, including when stages failed — a run
    that vanishes because it went badly is the opposite of observability.

    `run` lets a caller pass a row it already created and committed, which is
    what the background runner does: the request needs an id to hand back for
    polling before any stage has started.
    """
    if run is None:
        run = SyncRun(
            data_source_id=data_source_id, org_id=org_id,
            trigger=trigger, status="running", stages=[],
        )
        db.add(run)
        # Commit, not just flush: _run_stage rolls back on stage failure, and a
        # merely-flushed row would be expunged with it -- violating "always
        # returns a persisted SyncRun" exactly when a run goes badly (the case
        # observability exists for). The background runner already passes a
        # committed row; this makes the direct-call path match.
        await db.commit()

    context = SyncContext(
        db, data_source_id, org_id,
        cache=cache, llm_client=llm_client, allow_llm=allow_llm,
        source_config=source_config,
    )
    context.run = run

    discover = await _run_stage(context, "discover", stage_discover)
    if discover.status != "ok":
        # Nothing else has anything to describe.
        run.status = "failed"
        run.error = discover.error
        run.stages = [s.as_dict() for s in context.stages]
        run.finished_at = datetime.utcnow()
        await db.flush()
        return run

    # Sampling precedes profiling: statistics are computed FROM the cached rows,
    # so a profile run before the sample lands would describe an empty cache.
    await _run_stage(context, "sample", stage_sample)
    await _run_stage(context, "profile", stage_profile)

    # If nothing reached the cache, inference has nothing to work from — and
    # running it anyway would score every overlap 0.0 and report "no
    # relationships found", which is a wrong answer wearing the clothes of a
    # real one.
    if any(context.cache.has_sample(d.id) for d in context.datasets):
        await _run_stage(context, "infer_keys", stage_infer_keys)
        await _run_stage(context, "infer_semantic", stage_infer_semantic)
    else:
        _skip(context, "infer_keys", "no cached samples")
        _skip(context, "infer_semantic", "no cached samples")

    await _run_stage(context, "drift", stage_drift)

    failed = [s for s in context.stages if s.status == "failed"]
    run.status = "ok" if not failed else "partial"
    run.stages = [s.as_dict() for s in context.stages]
    run.finished_at = datetime.utcnow()
    await db.flush()
    return run


#: A run still "running" after this long is treated as abandoned — the process
#: died mid-sync. Without it, one crash wedges a source at 409 forever, which is
#: the same shape of bug as a leaked advisory lock.
STALE_RUN_MINUTES = 60


async def find_active_run(db, data_source_id: int) -> SyncRun | None:
    """The run currently in progress for this source, if any.

    Ignores runs older than STALE_RUN_MINUTES: those belong to a process that is
    no longer alive, and refusing new syncs on their behalf helps nobody.
    """
    from datetime import timedelta

    cutoff = datetime.utcnow() - timedelta(minutes=STALE_RUN_MINUTES)
    return (await db.execute(
        select(SyncRun).where(
            SyncRun.data_source_id == data_source_id,
            SyncRun.status == "running",
            SyncRun.started_at >= cutoff,
        ).order_by(SyncRun.id.desc()).limit(1)
    )).scalar_one_or_none()


async def run_sync_background(
    session_factory, run_id: int, data_source_id: int, org_id: int, *,
    cache, llm_client=None, allow_llm: bool = False,
    source_config: dict | None = None,
) -> None:
    """Execute a sync on its own session, updating a run row created elsewhere.

    Runs detached from any request, so it owns its session and its errors. The
    outer try/except is not optional: an exception escaping here would leave the
    row saying "running" forever, and the source unsyncable.
    """
    async with session_factory() as db:
        try:
            async with source_sync_lock(db, data_source_id) as acquired:
                if not acquired:
                    run = await db.get(SyncRun, run_id)
                    if run is not None:
                        run.status = "failed"
                        run.error = "Another sync acquired the lock first"
                        run.finished_at = datetime.utcnow()
                        await db.commit()
                    return

                run = await db.get(SyncRun, run_id)
                source = await db.get(DataSource, data_source_id)

                # Describe the DATABASE from its connection, not just the
                # datasets someone happened to import from it. The dataset-level
                # pipeline (`run_sync`) remains for sources that have no live
                # connection to introspect — an uploaded file has a dataset and
                # nothing else to read.
                from .catalog_sync import run_catalog_sync

                if source is not None and source_config:
                    from .cache import get_object_cache
                    await run_catalog_sync(
                        db, source, cache=get_object_cache(),
                        llm_client=llm_client, allow_llm=allow_llm,
                        source_config=source_config, run=run,
                    )
                else:
                    await run_sync(
                        db, data_source_id, org_id,
                        cache=cache, llm_client=llm_client, allow_llm=allow_llm,
                        source_config=source_config, run=run,
                    )

                source = await db.get(DataSource, data_source_id)
                if source is not None and run is not None:
                    source.sync_status = run.status
                    source.last_synced_at = run.finished_at
                await db.commit()
        except Exception as exc:
            logger.exception("background sync failed for source %s", data_source_id)
            try:
                run = await db.get(SyncRun, run_id)
                if run is not None and run.status == "running":
                    run.status = "failed"
                    run.error = f"{type(exc).__name__}: {exc}"
                    run.finished_at = datetime.utcnow()
                    await db.commit()
            except Exception:
                logger.exception("could not record the failure of run %s", run_id)


@asynccontextmanager
async def source_sync_lock(db, data_source_id: int):
    """Hold a per-source advisory lock for the duration of a sync.

    Yields True if the lock was taken, False if another sync already holds it.

    THE LOCK LIVES ON ITS OWN CONNECTION, and that is the whole point.
    `pg_try_advisory_lock` is SESSION-scoped -- it belongs to the Postgres
    connection that took it. Taking it on the request's session and then calling
    `db.commit()` mid-run lets SQLAlchemy return that connection to the pool and
    check out another, so the later `pg_advisory_unlock` runs on a connection
    that never held the lock: it returns false, and the original connection
    keeps the lock until it happens to close. The source is then permanently
    409, which is precisely the failure this replaced.

    A dedicated connection, held open across the run and closed in a finally,
    has none of that ambiguity. It matches what the startup path in main.py
    already does.

    On SQLite (tests, single-process dialects) there is nothing to lock and the
    manager yields True, matching the convention used elsewhere in the project.
    """
    bind = db.bind
    if bind is None or bind.dialect.name != "postgresql":
        yield True
        return

    key = _SYNC_LOCK_BASE + int(data_source_id)
    conn = await bind.connect()
    try:
        got = await conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": key})
        acquired = bool(got.scalar())
        if not acquired:
            yield False
            return
        try:
            yield True
        finally:
            try:
                await conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})
            except Exception:
                # Closing the connection below releases it anyway, but a failure
                # here is worth seeing: a lock that outlives its run makes the
                # source unsyncable until something restarts.
                logger.exception("failed to release sync lock for source %s", data_source_id)
    finally:
        await conn.close()
