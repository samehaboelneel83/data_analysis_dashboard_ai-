import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from .core.widget_errors import CodedHTTPException
from .core.config import settings
from .services.quotas import QuotaExceeded

logger = logging.getLogger(__name__)
from .core.database import engine, Base, AsyncSessionLocal
from .models.models import Dataset, Report, DataSource, Organization, Role
from .routers import datasets, analysis, reports, hierarchy, widget_data, data_sources, custom_connectors, auth, admin, relationships, demo, notifications, shared, widget_templates, platform, sso, metadata, embed, report_copilot
from .routers import boundary_sets, map_settings, prediction_models, authz, review, semantic
from .routers import workspace
from .routers import dataflows
from .routers import pins
from .routers import agent as agent_router


async def _migrate(conn):
    """Add new columns to existing tables without dropping data."""
    stmts = [
        "ALTER TABLE report_pages ADD COLUMN IF NOT EXISTS title VARCHAR(255)",
        "ALTER TABLE report_pages ADD COLUMN IF NOT EXISTS page_type VARCHAR(20) NOT NULL DEFAULT 'normal'",
        "ALTER TABLE report_pages ADD COLUMN IF NOT EXISTS prompt_column VARCHAR(255)",
        "ALTER TABLE report_pages ADD COLUMN IF NOT EXISTS prompt_label VARCHAR(255)",
        "ALTER TABLE datasets ADD COLUMN IF NOT EXISTS calculated_columns JSON DEFAULT '[]'",
        "ALTER TABLE datasets ADD COLUMN IF NOT EXISTS column_formats JSON DEFAULT '{}'",
        "ALTER TABLE datasets ADD COLUMN IF NOT EXISTS measures JSON DEFAULT '[]'",
        "ALTER TABLE datasets ADD COLUMN IF NOT EXISTS custom_functions JSON DEFAULT '[]'",
        "ALTER TABLE datasets ADD COLUMN IF NOT EXISTS column_meta JSON DEFAULT '{}'",
        "ALTER TABLE datasets ADD COLUMN IF NOT EXISTS refresh_interval_minutes INTEGER",
        "ALTER TABLE datasets ADD COLUMN IF NOT EXISTS last_refreshed_at TIMESTAMPTZ",
        "ALTER TABLE reports ADD COLUMN IF NOT EXISTS additional_dataset_ids JSON DEFAULT '[]'",
        "ALTER TABLE reports ADD COLUMN IF NOT EXISTS revision INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE datasets ADD COLUMN IF NOT EXISTS default_filter_expr TEXT",
        "ALTER TABLE datasets ADD COLUMN IF NOT EXISTS data_source_id INTEGER REFERENCES data_sources(id) ON DELETE SET NULL",
        "ALTER TABLE datasets ADD COLUMN IF NOT EXISTS source_table VARCHAR(500)",
        "ALTER TABLE datasets ADD COLUMN IF NOT EXISTS source_query TEXT",
        "ALTER TABLE datasets ADD COLUMN IF NOT EXISTS mode VARCHAR(20) NOT NULL DEFAULT 'import'",
        "ALTER TABLE data_sources ADD COLUMN IF NOT EXISTS cache_ttl_seconds INTEGER NOT NULL DEFAULT 60",
        "ALTER TABLE datasets ADD COLUMN IF NOT EXISTS org_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE",
        "ALTER TABLE reports ADD COLUMN IF NOT EXISTS org_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE",
        "ALTER TABLE data_sources ADD COLUMN IF NOT EXISTS org_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE",
        "ALTER TABLE report_pages ADD COLUMN IF NOT EXISTS page_size VARCHAR(20) NOT NULL DEFAULT '16:9'",
        "ALTER TABLE report_pages ADD COLUMN IF NOT EXISTS custom_width INTEGER",
        "ALTER TABLE report_pages ADD COLUMN IF NOT EXISTS custom_height INTEGER",
        "ALTER TABLE report_pages ADD COLUMN IF NOT EXISTS mobile_layout JSON",
        "ALTER TABLE report_pages ADD COLUMN IF NOT EXISTS layout_mode VARCHAR(20)",
        "ALTER TABLE report_pages ADD COLUMN IF NOT EXISTS layout_template VARCHAR(40)",
        # 0038: session revocation cut-off (see User.tokens_valid_after).
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS tokens_valid_after TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE reports ADD COLUMN IF NOT EXISTS theme VARCHAR(20) NOT NULL DEFAULT 'default'",
        "ALTER TABLE reports ADD COLUMN IF NOT EXISTS display_rules JSON DEFAULT '[]'",
        # ── Layer 1 — Connectors & Ingestion ────────────────────────────────
        # The four new metadata tables come free from create_all; these are the
        # columns Layer 1 adds to tables that already exist in live databases.
        # Existing relationships default to declared/1.0 on purpose: a human
        # typed them in, so they outrank anything inference later proposes.
        "ALTER TABLE relationships ADD COLUMN IF NOT EXISTS confidence DOUBLE PRECISION NOT NULL DEFAULT 1.0",
        "ALTER TABLE relationships ADD COLUMN IF NOT EXISTS source VARCHAR(20) NOT NULL DEFAULT 'declared'",
        "ALTER TABLE relationships ADD COLUMN IF NOT EXISTS evidence JSON",
        "ALTER TABLE relationships ADD COLUMN IF NOT EXISTS cardinality VARCHAR(20)",
        "ALTER TABLE dataset_columns ADD COLUMN IF NOT EXISTS semantic_type VARCHAR(40)",
        "ALTER TABLE dataset_columns ADD COLUMN IF NOT EXISTS description TEXT",
        "ALTER TABLE dataset_columns ADD COLUMN IF NOT EXISTS description_source VARCHAR(20)",
        "ALTER TABLE datasets ADD COLUMN IF NOT EXISTS is_deprecated BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE datasets ADD COLUMN IF NOT EXISTS description_source VARCHAR(20)",
        "ALTER TABLE datasets ADD COLUMN IF NOT EXISTS last_profiled_at TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE data_sources ADD COLUMN IF NOT EXISTS allow_llm_sampling BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE data_sources ADD COLUMN IF NOT EXISTS last_synced_at TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE data_sources ADD COLUMN IF NOT EXISTS sync_status VARCHAR(20) NOT NULL DEFAULT 'pending'",
        "ALTER TABLE data_sources ADD COLUMN IF NOT EXISTS description TEXT",
        "ALTER TABLE data_sources ADD COLUMN IF NOT EXISTS description_source VARCHAR(20)",
        # Nullable with no default, so Postgres does this as a metadata-only
        # change rather than rewriting an 82-row-per-source table.
        "ALTER TABLE source_objects ADD COLUMN IF NOT EXISTS sample_timed_out_at TIMESTAMP WITH TIME ZONE",
        # T1: an admin's assertion that this object is the source of truth for
        # what it describes -- see SourceObject.is_canonical.
        "ALTER TABLE source_objects ADD COLUMN IF NOT EXISTS is_canonical BOOLEAN NOT NULL DEFAULT FALSE",
        # T2: what a coded column's values MEAN, and who said so.
        "ALTER TABLE source_columns ADD COLUMN IF NOT EXISTS enum_labels JSON",
        "ALTER TABLE source_columns ADD COLUMN IF NOT EXISTS enum_labels_source VARCHAR(20)",
        # The source catalog: statistics can now belong to a catalog column
        # rather than a dataset column, so the existing NOT NULL has to go.
        "ALTER TABLE column_stats ADD COLUMN IF NOT EXISTS source_column_id INTEGER REFERENCES source_columns(id) ON DELETE CASCADE",
        "ALTER TABLE column_stats ALTER COLUMN dataset_column_id DROP NOT NULL",
        # Layer 4, multi-mode amendment: a conversation may target a fixed set
        # of datasets instead of a DataSource (Task 17).
        "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS dataset_ids JSON",
        # T6: per-source cache epoch, bumped by a drift-changed sync so every
        # DirectQuery cache key for the source becomes unaddressable.
        "ALTER TABLE data_sources ADD COLUMN IF NOT EXISTS cache_epoch INTEGER NOT NULL DEFAULT 0",
        # T12: share-link revision pinning -- see ShareLink.snapshot/.pinned.
        "ALTER TABLE share_links ADD COLUMN IF NOT EXISTS snapshot JSON",
        "ALTER TABLE share_links ADD COLUMN IF NOT EXISTS pinned BOOLEAN NOT NULL DEFAULT FALSE",
        # ── Dashboard v2: pin layout + Dynamic Insight Pins (0012) ──────────
        # create_all never ALTERs the pinned_tiles table 0011 already created
        # on running installs, so the 0012 columns are patched here too.
        "ALTER TABLE pinned_tiles ADD COLUMN IF NOT EXISTS position INTEGER",
        "ALTER TABLE pinned_tiles ADD COLUMN IF NOT EXISTS size VARCHAR(1) NOT NULL DEFAULT 'm'",
        "ALTER TABLE pinned_tiles ADD COLUMN IF NOT EXISTS dataset_id INTEGER REFERENCES datasets(id) ON DELETE CASCADE",
        "ALTER TABLE pinned_tiles ADD COLUMN IF NOT EXISTS finding_key TEXT",
        "ALTER TABLE pinned_tiles ALTER COLUMN widget_id DROP NOT NULL",
        # A unique INDEX rather than ADD CONSTRAINT: this loop tolerates no
        # per-statement failure, and only CREATE INDEX has IF NOT EXISTS. On a
        # fresh install create_all's constraint already owns this name, so the
        # IF NOT EXISTS quietly stands down.
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_pin_user_finding ON pinned_tiles (user_id, dataset_id, finding_key)",
        # 0013: report authorship for the My-workspaces/Granted grouping. NULL
        # (every pre-existing report) means unowned -- never "mine" for anyone.
        "ALTER TABLE reports ADD COLUMN IF NOT EXISTS created_by INTEGER REFERENCES users(id) ON DELETE SET NULL",
        "CREATE INDEX IF NOT EXISTS ix_reports_created_by ON reports (created_by)",
        # 0014: publish/grant model. Defaults keep every existing row a draft,
        # which changes nothing because pre-0013 rows are unowned and
        # grandfathered. report_user_grants is a NEW table -- create_all makes
        # it on startup; no ALTER needed.
        "ALTER TABLE reports ADD COLUMN IF NOT EXISTS published BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE workspace_nodes ADD COLUMN IF NOT EXISTS published BOOLEAN NOT NULL DEFAULT FALSE",
        # Dataset-mode memory scoping: sorted dataset ids joined with commas
        # (e.g. "3,17"), NULL for source-mode rows -- see QueryExample.dataset_key.
        "ALTER TABLE query_examples ADD COLUMN IF NOT EXISTS dataset_key VARCHAR(120)",
        # D1: the query-builder graph behind a builder-created dataset's SQL, so
        # "Edit query" can reopen the design instead of only the compiled text.
        "ALTER TABLE datasets ADD COLUMN IF NOT EXISTS query_model JSON",
        # S0c: marks a row-security rule (or its current filter_expr) as machine-
        # proposed rather than admin-typed -- see RowSecurityRule.auto_generated.
        "ALTER TABLE row_security_rules ADD COLUMN IF NOT EXISTS auto_generated BOOLEAN NOT NULL DEFAULT FALSE",
        # SH1: dataset_shares is a brand-new table so create_all already provisions
        # it on every environment -- nothing to ALTER here, this line just documents
        # that the table's existence was verified.
        # T3: the scheduler interprets a schedule's calendar hour/minute in this
        # IANA zone (zoneinfo), defaulting to UTC when NULL -- see ReportSchedule.timezone.
        "ALTER TABLE report_schedules ADD COLUMN IF NOT EXISTS timezone VARCHAR(64)",
        # T3: `deliveries` is a brand-new table so create_all already provisions it
        # on every environment -- nothing to ALTER here, this line just documents
        # that the table's existence was verified.
        # T4: `agent_feedback` and `eval_runs` are brand-new tables so create_all
        # already provisions them on every environment -- nothing to ALTER here,
        # this line just documents that their existence was verified.
        # Tier 2 R1: `retrieval_embeddings` is a brand-new table so create_all
        # already provisions it -- nothing to ALTER here.
        # Tier 2 R3: `entities` is a brand-new table so create_all already
        # provisions it on every environment -- nothing to ALTER here, this
        # line just documents that its existence was verified.
        # Tier 3 E1: `embed_configs` is a brand-new table so create_all
        # already provisions it -- nothing to ALTER here.
        # Tier 3 E2: `quotas` is a brand-new table so create_all already
        # provisions it on every environment -- nothing to ALTER here.
        # Tier 4 O3: `materializations` is a brand-new table so create_all
        # already provisions it on every environment -- nothing to ALTER here.
        "ALTER TABLE agent_steps ADD COLUMN IF NOT EXISTS result_rows JSON",
        "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS context_objects JSON",
        "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS presentation JSON",
        # 0020: dataset/connection ownership. The BACKFILL matters as much as
        # the columns -- a NULL owner reads as "unowned" and stays readable by
        # the whole org, so without it the new dataset rules would apply to
        # nothing on an existing install. Assigning each row to its org's
        # first admin grants nobody anything (admins already read everything)
        # and drops members to owner / shared / reachable-by-dashboard.
        "ALTER TABLE datasets ADD COLUMN IF NOT EXISTS created_by INTEGER REFERENCES users(id) ON DELETE SET NULL",
        "ALTER TABLE data_sources ADD COLUMN IF NOT EXISTS created_by INTEGER REFERENCES users(id) ON DELETE SET NULL",
        "ALTER TABLE data_sources ADD COLUMN IF NOT EXISTS custom_connector_id INTEGER REFERENCES custom_connectors(id) ON DELETE RESTRICT",
        """UPDATE datasets SET created_by = (
               SELECT u.id FROM users u JOIN roles r ON r.id = u.role_id
               WHERE u.org_id = datasets.org_id AND r.is_org_admin = true
               ORDER BY u.id LIMIT 1)
           WHERE created_by IS NULL AND org_id IS NOT NULL""",
        """UPDATE data_sources SET created_by = (
               SELECT u.id FROM users u JOIN roles r ON r.id = u.role_id
               WHERE u.org_id = data_sources.org_id AND r.is_org_admin = true
               ORDER BY u.id LIMIT 1)
           WHERE created_by IS NULL AND org_id IS NOT NULL""",
    ]
    for s in stmts:
        await conn.execute(text(s))


def _is_duplicate_schema_drift_error(exc: Exception) -> bool:
    """True when `exc` looks like a DuplicateTable/DuplicateColumn class
    error: `upgrade head` tried to (re-)create an object that already
    exists. This is the signature of schema drift -- the live DB is already
    at (or ahead of) head, but `alembic_version` is pinned behind -- as
    opposed to a genuinely broken revision (bad SQL, unreachable DB, ...),
    which must NOT be self-healed.

    PRECONDITION -- UNSAFE ONCE DATA MIGRATIONS EXIST: this heuristic is
    only sound while every revision is SCHEMA-ONLY (create_all/_migrate
    can then rebuild head-equivalence, so stamping is safe). A revision
    that also moves DATA (CREATE TABLE x; INSERT INTO x ...) would raise
    DuplicateTable when x pre-exists, pass the all-tables-present check,
    and get stamped -- silently orphaning the INSERT. Before authoring the
    first data-bearing revision, gate or remove this self-heal.

    Checked two ways: the driver's own exception class name (asyncpg raises
    `DuplicateTableError`/`DuplicateColumnError` for Postgres), and a message
    fallback (SQLite's `sqlite3.OperationalError` just says "table X already
    exists" / "duplicate column name: X", wrapped by SQLAlchemy) -- since the
    test suite runs on SQLite and production runs on Postgres, both need to
    match the same drift.
    """
    seen = set()
    node = exc
    while node is not None and id(node) not in seen:
        seen.add(id(node))
        cls_name = type(node).__name__
        if "Duplicate" in cls_name and ("Table" in cls_name or "Column" in cls_name):
            return True
        msg = str(node).lower()
        if "already exists" in msg and ("table" in msg or "column" in msg or "index" in msg):
            return True
        if "duplicate column name" in msg:
            return True
        node = getattr(node, "orig", None)
    return False


async def _run_alembic() -> None:
    """T1: adopt Alembic without breaking a database that already has data.

    Three cases, told apart by inspecting the live DB (never by assuming):
      - No app tables at all (brand-new DB) -> `upgrade head`. Alembic
        provisions the schema from 0001_baseline (+ any later revisions).
      - `alembic_version` table already present (a DB Alembic has already
        adopted, on a previous boot or in CI) -> `upgrade head` picks up
        whatever revisions haven't run yet. A no-op when already current.
      - App tables exist but no `alembic_version` (every database that
        existed before this task shipped) -> stamp HEAD. This writes only
        the version marker; it runs no DDL, so a live DB is adopted without
        being touched -- create_all + `_migrate`, which run right after,
        bring the schema to head-equivalence in the same boot. From the
        next boot on it falls into the branch above.

    Like `_run_secrets_migration`, this is wrapped end-to-end: any failure
    (bad revision, unreachable DB, a bug in a future migration) is logged
    rather than bricking startup, so /health/live and the logs stay
    reachable. It is NOT swallowed any more: the failure is recorded in
    `_MIGRATION_ERROR` and /health/ready answers 503 while it is set, so a
    replica whose schema never reached head stays out of rotation instead of
    serving as if it had (on 2026-09-19 the dev stack did exactly that for
    every boot, over an oversized revision id). A run that "succeeds" but
    leaves the DB off the script head is recorded the same way.
    """
    global _MIGRATION_ERROR
    _MIGRATION_ERROR = None
    try:
        import asyncio
        import os
        from alembic import command
        from alembic.config import Config
        from sqlalchemy import inspect as sa_inspect

        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cfg = Config(os.path.join(backend_dir, "alembic.ini"))
        cfg.set_main_option("script_location", os.path.join(backend_dir, "alembic"))

        def _inspect_sync(sync_conn):
            existing = set(sa_inspect(sync_conn).get_table_names())
            has_alembic_version = "alembic_version" in existing
            has_app_tables = bool(existing & set(Base.metadata.tables.keys()))
            return has_alembic_version, has_app_tables

        async with engine.connect() as conn:
            has_alembic_version, has_app_tables = await conn.run_sync(_inspect_sync)

        if has_app_tables and not has_alembic_version:
            # Stamp HEAD, not the baseline: create_all + _migrate run right
            # after this and bring the schema to head-equivalence in the same
            # boot. Stamping the baseline instead would make the next boot's
            # `upgrade head` re-create 0002+'s tables (DuplicateTable), pinning
            # the version forever and orphaning every future revision.
            logger.info("alembic: existing database with no alembic_version -- stamping head")
            await asyncio.to_thread(command.stamp, cfg, "head")
        else:
            logger.info("alembic: running upgrade head")
            try:
                await asyncio.to_thread(command.upgrade, cfg, "head")
            except Exception as upgrade_exc:
                if not _is_duplicate_schema_drift_error(upgrade_exc):
                    raise

                def _missing_tables_sync(sync_conn):
                    existing = set(sa_inspect(sync_conn).get_table_names())
                    return set(Base.metadata.tables.keys()) - existing

                async with engine.connect() as conn:
                    missing = await conn.run_sync(_missing_tables_sync)

                if missing:
                    # Not actually head-equivalent -- some other duplicate-
                    # object condition. Don't paper over a real gap; fall
                    # through to the outer log-and-continue.
                    raise

                logger.warning(
                    "alembic: upgrade head hit a duplicate-object error (schema "
                    "drift -- alembic_version is behind a DB that already has "
                    "every table): %s -- self-healing by stamping head",
                    upgrade_exc,
                )
                await asyncio.to_thread(command.stamp, cfg, "head")

        # Verify, don't infer: the version the DB now records must be the
        # script head, whichever branch ran above.
        from alembic.script import ScriptDirectory
        from sqlalchemy import text as sa_text
        head = ScriptDirectory.from_config(cfg).get_current_head()
        async with engine.connect() as conn:
            current = (await conn.execute(sa_text("SELECT version_num FROM alembic_version"))).scalar()
        if current != head:
            logger.error("alembic: database is at %r, script head is %r -- not ready", current, head)
            _MIGRATION_ERROR = "revision_mismatch"
    except Exception as exc:
        # Type name only: /health/ready is unauthenticated and a connection
        # error's message can carry the DSN.
        _MIGRATION_ERROR = type(exc).__name__
        logger.exception("alembic startup migration failed; this replica will report "
                         "not ready (create_all/_migrate still run)")


async def _run_secrets_migration(session: AsyncSession) -> None:
    """Run the enc:v1->v2 secrets migration in isolation, so a transient DB
    error here can never brick startup -- the migration is idempotent, so
    whatever wasn't migrated this boot stays enc:v1 and is retried next time."""
    try:
        from .services.secrets import migrate_v1_to_v2
        migrated = await migrate_v1_to_v2(session)
        logger.info("enc:v1->v2 startup migration: %d data source(s) upgraded", migrated)
    except Exception:
        logger.exception("enc:v1->v2 startup migration failed; continuing startup unmigrated")


async def _backfill_default_org(session: AsyncSession) -> None:
    """Ensure a default organization + admin role exist, and backfill any org_id-less
    rows in Dataset/Report/DataSource into it. Idempotent — guarded by checking
    whether any Organization row exists yet, so this is a no-op on every startup
    after the first."""
    result = await session.execute(select(Organization).limit(1))
    org = result.scalar_one_or_none()
    if org is None:
        org = Organization(name="Default Organization")
        session.add(org)
        await session.flush()
        session.add(Role(org_id=org.id, name="Admin", is_org_admin=True))
        await session.flush()
    await session.execute(update(Dataset).where(Dataset.org_id.is_(None)).values(org_id=org.id))
    await session.execute(update(Report).where(Report.org_id.is_(None)).values(org_id=org.id))
    await session.execute(update(DataSource).where(DataSource.org_id.is_(None)).values(org_id=org.id))
    await session.commit()


# Serializes multi-worker startup. Concurrent create_all from N uvicorn
# workers races Postgres catalog inserts (duplicate-key on pg_type), and two
# workers racing _backfill_default_org on a first boot would BOTH see "no org
# yet" and create two defaults. A session-level advisory lock on a dedicated
# connection makes worker startup strictly sequential; single-process
# dialects (SQLite in tests) skip it, matching the scheduler's convention.
_STARTUP_LOCK_KEY = 0x5DA7A171C5  # arbitrary, stable; distinct from scheduler keys

#: Flipped once lifespan has finished migrations and backfills. /health/ready
#: reports "not_ready" until then, so a replica still running Alembic is not
#: sent traffic. Module-level rather than app.state so the readiness handler
#: can read it without a request-scoped app reference.
_STARTUP_COMPLETE = False

#: Set by `_run_alembic` when the schema did not reach the script head: the
#: failing exception's type name, or "revision_mismatch". /health/ready is 503
#: while it is set. None means the last run verified the DB at head.
_MIGRATION_ERROR: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.connect() as lockconn:
        is_pg = lockconn.dialect.name == "postgresql"
        if is_pg:
            await lockconn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": _STARTUP_LOCK_KEY})
        try:
            await _run_alembic()
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                await _migrate(conn)
            async with AsyncSessionLocal() as session:
                await _backfill_default_org(session)
            async with AsyncSessionLocal() as session:
                await _run_secrets_migration(session)
            # A metadata sync is a detached task; if the previous process died
            # mid-run its SyncRun row still says "running", and nothing ever
            # corrected it. Inside the startup lock, where no such task can
            # possibly be alive.
            async with AsyncSessionLocal() as session:
                from .services.refresh_scheduler import reap_orphaned_failures, reap_stuck_sync_runs
                await reap_stuck_sync_runs(session)
                await reap_orphaned_failures(session)
                # Same class of orphan, one table over: `automation_runner.tick`
                # marks a step `running` before threading it, so a process that
                # died mid-step leaves a row that says `running` forever. It has
                # no output_ref, so the run sits at the head of the queue looking
                # like progress nobody is making.
                from .services.automation_runner import reap_stuck_automation_steps
                await reap_stuck_automation_steps(session)
        finally:
            if is_pg:
                await lockconn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _STARTUP_LOCK_KEY})

    # Background refresh loop. One runs per uvicorn worker, which is why
    # refresh_one takes a per-dataset Postgres advisory lock before doing any work.
    import asyncio
    from .services.refresh_scheduler import run_scheduler
    scheduler = asyncio.create_task(run_scheduler(AsyncSessionLocal))

    # T4: opt-in nightly eval gate (settings.eval_gate_enabled, default
    # False) -- a stand-in for CI, not CI itself. See services/eval_schedule.py.
    from .services import eval_schedule
    eval_scheduler = eval_schedule.maybe_create_task(AsyncSessionLocal)

    async def _probe_llm_contract():
        """F2's silent failure must never recur silently. One tiny enforced
        call; a schema violation is logged at ERROR and nothing else happens —
        the app must start regardless."""
        try:
            from .services import llm as llm_service
            client = llm_service.get_client()
            got = await client.complete_json(
                [{"role": "user", "content": "Reply with the number one."}],
                {"type": "object",
                 "properties": {
                     "n": {"type": "integer"},
                     # Union type, deliberately -- this is the schema shape
                     # (spec F2 regression) that once made complete_json
                     # raise instead of returning None: a JSON-Schema union
                     # like the agent's `ambiguity_reason` has an unhashable
                     # `type` list. Optional, so a model that omits it still
                     # passes; present so a contract regression of this kind
                     # is caught here, at startup, rather than live on
                     # /agent/conversations/{id}/ask.
                     "note": {"type": ["string", "null"]},
                 },
                 "required": ["n"], "additionalProperties": False},
                enforce=True, background=True, max_tokens=30, retries=0)
            # "note" is optional (Optional[str], deliberately unioned with
            # null) — a model that includes it is still a passing probe.
            # Requiring set(got) == {"n"} exactly made every response that
            # honoured the optional field a false PROBE FAILED.
            if (not isinstance(got, dict) or "n" not in got
                    or not set(got) <= {"n", "note"}):
                logging.getLogger(__name__).error(
                    "LLM json_schema enforcement PROBE FAILED — agent SQL "
                    "contracts are not being grammar-enforced (last_error=%s)",
                    client.last_error)
        except Exception:
            logging.getLogger(__name__).exception("LLM contract probe crashed")

    asyncio.get_running_loop().create_task(_probe_llm_contract())

    # Migrations, backfills and scheduler wiring are all done by this point:
    # /health/ready may now report the replica as servable.
    global _STARTUP_COMPLETE
    _STARTUP_COMPLETE = True

    try:
        yield
    finally:
        _STARTUP_COMPLETE = False
        scheduler.cancel()
        try:
            await scheduler
        except asyncio.CancelledError:
            pass
        if eval_scheduler is not None:
            eval_scheduler.cancel()
            try:
                await eval_scheduler
            except asyncio.CancelledError:
                pass


# The interactive docs list every route and schema. Handy in development;
# in production they are a free map of the API for anyone without a login,
# so they are switched off there (the same is_production() rule as SSO).
_docs_on = not settings.is_production()
app = FastAPI(title="Datalytics API", version="2.0.0", lifespan=lifespan,
              docs_url="/docs" if _docs_on else None,
              redoc_url="/redoc" if _docs_on else None,
              openapi_url="/openapi.json" if _docs_on else None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# E3: OpenTelemetry, opt-in (settings.otel_enabled, default False).
# setup_telemetry is itself a hard no-op when disabled -- no otel import
# executed -- and swallows any setup failure internally (see
# core/telemetry.py), the same never-brick-startup discipline as
# _run_secrets_migration above.
from .core import telemetry as _telemetry
_telemetry.setup_telemetry(app)


@app.middleware("http")
async def _rate_limit_gate(request, call_next):
    from .core.rate_limit import rate_limit_middleware
    return await rate_limit_middleware(request, call_next)


@app.middleware("http")
async def unhandled_errors_keep_cors_headers(request, call_next):
    """Turn an unhandled exception into a normal 500 response.

    Starlette handles an escaped exception in ServerErrorMiddleware, which sits
    OUTSIDE the CORS middleware -- so its 500 carries no Access-Control-Allow-Origin
    header. The browser then reports a CORS policy violation, and whoever is
    debugging goes looking at origins and headers instead of at the traceback
    that actually caused it.

    Registered after CORSMiddleware, so it sits INSIDE it: the JSONResponse below
    travels back out through CORS and picks up the headers. The real error is
    logged with its traceback, and the client gets a 500 it can actually read.
    """
    try:
        return await call_next(request)
    except Exception:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error. See server logs for details.",
                     "code": "internal"},
        )

app.include_router(datasets.router,     prefix="/api/v1")
app.include_router(analysis.router,     prefix="/api/v1")
app.include_router(analysis.registry_router, prefix="/api/v1")
app.include_router(reports.router,      prefix="/api/v1")
app.include_router(report_copilot.router, prefix="/api/v1")
app.include_router(hierarchy.router,    prefix="/api/v1")
app.include_router(widget_data.router,  prefix="/api/v1")
app.include_router(data_sources.router, prefix="/api/v1")
app.include_router(custom_connectors.router, prefix="/api/v1")
app.include_router(boundary_sets.router, prefix="/api/v1")
app.include_router(map_settings.router, prefix="/api/v1")
app.include_router(authz.router, prefix="/api/v1")
app.include_router(review.router, prefix="/api/v1")
app.include_router(semantic.router, prefix="/api/v1")
app.include_router(prediction_models.router, prefix="/api/v1")
app.include_router(auth.router,         prefix="/api/v1")
app.include_router(admin.router,        prefix="/api/v1")
app.include_router(relationships.router, prefix="/api/v1")
app.include_router(demo.router,          prefix="/api/v1")
app.include_router(notifications.router, prefix="/api/v1")
app.include_router(shared.router,        prefix="/api/v1")
app.include_router(embed.router,         prefix="/api/v1")
app.include_router(widget_templates.router, prefix="/api/v1")
app.include_router(workspace.router,     prefix="/api/v1")
app.include_router(dataflows.router,     prefix="/api/v1")
app.include_router(platform.router,      prefix="/api/v1")
app.include_router(sso.router,           prefix="/api/v1")
app.include_router(pins.router,          prefix="/api/v1")
# Layer 1 — metadata plane. Two routers because the routes hang off two
# different resources: sync/review/drift under a data source, column
# statistics under a dataset.
app.include_router(metadata.router,      prefix="/api/v1")
app.include_router(metadata.stats_router, prefix="/api/v1")
# Layer 4 — agent chat surface. Mounted under /api/v1 like every other router.
#
# It was previously mounted bare, on the reasoning that the router "owns its own
# /agent namespace". That reasoning was wrong in a way nothing caught: the
# frontend has a single axios instance whose baseURL already ends in /api/v1
# (services/api.ts), so every agentApi call requested /api/v1/agent/... and got
# a 404. The whole natural-language query feature was unreachable from the UI
# while its own tests passed, because those tests asked for the bare path.
#
# test_router_reachability.py now pins every router to the prefix the client
# actually uses, so a future unprefixed mount fails instead of going dark.
app.include_router(agent_router.router,  prefix="/api/v1")


@app.exception_handler(CodedHTTPException)
async def _coded_http_exception_handler(request, exc: CodedHTTPException):
    """`{"detail": ..., "code": ...}` -- see services/error_codes.py.

    Registered on the subclass, so FastAPI's own HTTPException handler keeps
    serving every other router unchanged. Same placement reason as the
    handlers around it: inside CORSMiddleware, or the browser reports a
    CORS violation instead of the error the reader needs to see."""
    return JSONResponse(status_code=exc.status_code,
                        content={"detail": exc.detail, "code": exc.code},
                        headers=getattr(exc, "headers", None))


@app.exception_handler(QuotaExceeded)
async def _quota_exceeded_handler(request, exc: QuotaExceeded):
    """Translate the quota domain exception into its HTTP response.

    Registered after CORSMiddleware for the same reason the generic handler
    below is: a response produced outside the middleware carries no
    Access-Control-Allow-Origin header, and the browser reports a CORS
    violation instead of the 429 the user needs to see.

    Status code and headers come from the exception, so the domain decides
    *which* limit was hit and when it resets (Retry-After) while this only
    decides how to write it down.
    """
    return JSONResponse(
        status_code=exc.status_code,
        # `code` beside `detail`: this is the one widget-path error that is not
        # an HTTPException, so the router's widget_error() never sees it. A
        # 429 with Retry-After is the other retryable answer a widget can get.
        content={"detail": exc.detail, "code": "quota"},
        headers=exc.headers or None,
    )


@app.get("/health")
async def health():
    """Liveness, and the original endpoint name.

    Deliberately static: it answers "is this process running and serving?"
    and nothing more. A liveness probe that touches the database turns a
    30-second Postgres blip into a restart loop across every replica, which
    is strictly worse than the outage it was meant to detect. Use
    /health/ready for dependency state.

    Kept at this path because docker-compose.yml's backend healthcheck and
    any external monitor already point here.
    """
    return {"status": "ok"}


@app.get("/health/live")
async def health_live():
    """Alias of /health, named for readers who expect the k8s convention."""
    return {"status": "ok"}


@app.get("/health/ready")
async def health_ready(response: Response):
    """Readiness: can this replica actually serve a request right now?

    Checks the dependencies a request genuinely needs, and grades them:

      postgres  REQUIRED. Every meaningful request touches it. Unreachable
                means not ready -- 503, take this replica out of rotation.
      valkey    OPTIONAL, and only checked when `settings.valkey_url` is
                set. ValkeyCache already fails soft behind a circuit breaker
                onto an in-process cache, so a degraded Valkey costs
                cross-replica cache coherence, not correctness. Reported as
                "degraded" and never fails the probe -- pulling every
                replica out of rotation over a warm cache would turn a
                performance problem into an outage.
      migrations Reported from startup state. Alembic runs inside lifespan
                under a Postgres advisory lock, so if the app is serving at
                all, migrations completed. This surfaces that fact rather
                than re-deriving it per request.

    Returns 200 with a per-dependency breakdown, or 503 when a REQUIRED
    dependency is down. The body shape is identical either way so a probe
    can log it without branching.
    """
    checks: dict[str, dict] = {}
    ready = True

    # -- postgres (required) --------------------------------------------
    started = time.perf_counter()
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["postgres"] = {
            "status": "ok",
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        }
    except Exception as exc:
        ready = False
        checks["postgres"] = {
            "status": "down",
            "required": True,
            # Type name only: a connection error can carry the DSN, and this
            # endpoint is typically unauthenticated.
            "error": type(exc).__name__,
        }

    # -- valkey (optional, never fails the probe) ------------------------
    if settings.valkey_url:
        started = time.perf_counter()
        try:
            from .services.widget_data import _get_cache_backend

            backend = _get_cache_backend()
            probe_key = "__readiness__"
            backend.set(probe_key, {"v": 1}, ttl_seconds=5)
            backend.get(probe_key)
            checks["valkey"] = {
                "status": "ok",
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            }
        except Exception as exc:
            checks["valkey"] = {
                "status": "degraded",
                "required": False,
                "detail": "serving from in-process fallback cache",
                "error": type(exc).__name__,
            }
    else:
        checks["valkey"] = {"status": "not_configured"}

    # -- migrations (startup-derived) ------------------------------------
    if _MIGRATION_ERROR is not None:
        # A replica that could not bring its schema to head must not take
        # traffic: every request would run against columns and tables that
        # may not exist. /health/live stays up so the logs can be read.
        checks["migrations"] = {"status": "failed", "required": True,
                                "error": _MIGRATION_ERROR}
        ready = False
    else:
        checks["migrations"] = {
            "status": "ok" if _STARTUP_COMPLETE else "pending",
            "detail": "applied during startup under an advisory lock",
        }
    if not _STARTUP_COMPLETE:
        ready = False

    response.status_code = 200 if ready else 503
    return {"status": "ready" if ready else "not_ready", "checks": checks}
