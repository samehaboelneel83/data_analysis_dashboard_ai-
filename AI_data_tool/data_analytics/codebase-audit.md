# Datalytics — Codebase Audit (factual inventory)

**Date:** 2026-09-22
**What was audited:** the **working tree** of `AI_data_tool/data_analytics/` (the git repo root). It differs substantially from `HEAD` (`dccd81c9`): `git status --porcelain` lists **355 entries**, made up of 185 modified, 48 deleted and 123 untracked. The modified files include `backend/app/main.py`, `models/models.py`, `schemas/schemas.py`, most routers and several `services/agent/*` files. This audit describes the files as they are on disk, not as they are at `HEAD`.

**Present in the repo but not audited as product code:**
- `docs/`: design specs and plans (`docs/superpowers/`, `docs/ux-redesign/`) plus five operational docs.
- `MCAIT Design System/`: a design-system bundle with components, tokens, ui_kits and `_ds_bundle.js`.
- `backend/sample_data/`: two SQLite databases, `cairo_hospital.db` (119 MB) and `moodle_egypt_university.db` (69 MB), used as demo data sources.
- `backend/uploads/`: 31 entries of uploaded-file state.
- `.worktrees/custom-calc-functions;C/`: an empty folder.
- `node_modules/` at the repo root.
- Documents at the repo root: `ARCHITECTURE.md`, `PROJECT_AUDIT.md`, `DATALYTICS_ALL_DOCS.md`, and others.

Scripts in the parent folders (`prompt.py`, `generate_hospital_data.py`, `render_readme.py` and `AI_data_tool/drivers.py`) are outside the git repo and were not audited.

**Out of scope:** the sibling folders one level up.
- `WrenAI/`, `superset_ref/` and `maps_project/` are separate projects kept for reference.
- `data_analytics.rar` is a 331 MB archive.
- `data_analytics;C/` is empty.
- None of these is imported by the product. The only mention of Wren in product code is a comment, `backend/app/services/llm.py:5-8`: "*…the Wren AI dependency: ARCHITECTURE.md lists WrenAI under "Avoided entirely" because it is AGPL…*".

**Method:**
- Code was read directly. Six parallel read-only passes covered the data model, the query path, the frontend, the AI layer, the endpoints and the gaps.
- The quotes this audit depends on most were re-read against the source before inclusion: `ReportWidget`, `WidgetDataRequest`/`WidgetDataResponse`, the widget-data route, the DirectQuery column-denial check, `resolve_rls_expr`, the pandas RLS pipeline, the demo report spec, `suggest_dashboard` validation, `main.py` lifespan and middleware, and the LLM config.
- Nothing was executed except counting commands and one `import app.main` to enumerate routes.
- The in-repo documents `ARCHITECTURE.md`, `PROJECT_AUDIT.md` and `qa/*.md` are treated as **claims**. Where this audit cites them, it says so.

---

## 1. STACK

### Languages
- Python 3.12. The backend image is `python:3.12-slim`, and the local venv runs 3.12.7.
- TypeScript 5.4 with React 18, on Node 20 (`node:20-alpine`).
- SQL, in the Postgres, DuckDB and customer database dialects.

### Backend (`backend/requirements.txt`, all pinned with `==`)

| Area | Packages |
|---|---|
| Web | fastapi 0.111.0, uvicorn[standard] 0.29.0, python-multipart 0.0.9, pydantic-settings 2.2.1 |
| ORM / DB | sqlalchemy[asyncio] 2.0.30, asyncpg 0.29.0, aiosqlite 0.20.0 (tests), alembic 1.13.2, psycopg2-binary 2.9.9 |
| Customer DB drivers | pymssql 2.3.0, pymysql 1.1.1, oracledb 2.3.0, pyodbc 5.2.0, duckdb-engine 0.13.2 |
| Dataframes / query | pandas 2.2.2, numpy 1.26.4, pyarrow 16.1.0, sqlglot 30.17.0 |
| Stats / ML | scipy 1.13.0, statsmodels 0.14.6, scikit-learn 1.5.1, statsforecast 2.1.1 (numba 0.67.0, llvmlite 0.49.0), pyod 3.6.5 |
| Files / export | openpyxl 3.1.2, reportlab 4.2.2, matplotlib 3.9.2, arabic-reshaper 3.0.1, python-bidi 0.6.11, lxml 6.1.2 |
| Auth / crypto | passlib[bcrypt] 1.7.4, bcrypt 4.3.0, python-jose[cryptography] 3.3.0, signxml 5.1.0 |
| HTTP / cache | httpx 0.27.0, redis 5.0.4, fakeredis 2.23.2 |
| Telemetry | opentelemetry-api/sdk 1.27.0, instrumentation-fastapi/sqlalchemy 0.48b0, exporter-otlp-proto-http 1.27.0, setuptools 75.6.0 |
| Test | pytest 8.2.2, pytest-asyncio 0.23.7, pytest-timeout 2.3.1, freezegun 1.5.1 |

- No LLM SDK is installed: no `openai` and no `anthropic`. The LLM is called with raw `httpx` (see §7).
- No LangGraph or LangChain.

### Frontend (`frontend/package.json`, caret ranges)
- **Runtime:** react ^18.3.1, react-dom ^18.3.1, react-router-dom ^6.23.1, axios ^1.7.2
- **Rendering:** recharts ^2.12.7, d3-geo ^3.1.1, topojson-client ^3.1.0, world-atlas ^2.0.2, d3-cloud ^1.2.9, reactflow ^11.11.4
- **Other:** pptxgenjs ^4.0.1, lucide-react ^0.383.0, react-hot-toast ^2.4.1
- **Dev:** vite ^5.2.12, @vitejs/plugin-react ^4.3.0, typescript ^5.4.5, vitest ^2.0.5, jsdom ^24.1.1, @testing-library/react ^16, playwright ^1.61.1
- **State management library:** not present. The app uses React Context plus local state.

### Databases and query engines actually used
- **PostgreSQL 16** (`postgres:16-alpine`) holds the app metadata, via `postgresql+asyncpg`. A sync psycopg2 engine exists only for query logging (`services/query_log.py:48-49`). **The test suite runs on in-memory SQLite** (`backend/tests/conftest.py`), not Postgres.
- **pandas** is the default engine for imported (uploaded) data. Files are loaded into DataFrames and shaped in Python.
- **DuckDB** is used in four places:
  - Import-mode pushdown over parquet sidecars or CSV files (`services/duck_agg.py`, on by default: `widget_duckdb_pushdown: bool = True`, `core/config.py:231`).
  - The Ask AI dataset-mode executor, which is in-memory (`services/agent/executor.py`).
  - A metadata sample cache (`services/metadata/cache.py`).
  - A connector type (`duckdb:///…`).
- **Parquet via pyarrow:** each uploaded file gets a sidecar written by `services/frame_cache.py`.
- **Customer databases (DirectQuery / import):** SQLAlchemy engines for the Postgres, MySQL, SQL Server, Oracle, SQLite and ClickHouse families (`services/connectors.py:34`). See §5 for the connector list.
- **Valkey 8** (`valkey/valkey:8-alpine`) is an optional shared result cache (`services/cache_backend.py`). `config.py:298` defaults to `valkey_url = None`, but `docker-compose.yml` sets `VALKEY_URL=redis://valkey:6379/0` by default. If Valkey is unreachable, the cache falls back to in-process.
- **Embeddings service:** a separate FastAPI + ONNX Runtime container (`embedding_server/`) running `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384-dim). `config.py:267-269` defaults it to `None`; compose sets `EMBEDDING_BASE_URL=http://embeddings:8000/v1`.
- **LLM:** an external, self-hosted vLLM endpoint serving Qwen (see §7). It is not part of compose.

### Build and deploy
- **`docker-compose.yml`** (205 lines) defines these services:
  - `postgres`, host port 5433
  - `backend`, port 8000; uvicorn with `--reload`, or `--workers N` when `UVICORN_WORKERS>1`; source bind-mounted
  - `valkey`, no host port
  - `embeddings`, no host port, `mem_limit: 1g`
  - `frontend`, the Vite dev server, host port 3001 → container 3000
  - `web`, behind the `prod` profile: nginx 1.27 serving the built bundle and proxying `/api/` to `backend:8000`, host port `${WEB_PORT:-8090}`
- **`docker-compose2.yml`** (68 lines, older) is a three-service variant: postgres on 5432, backend and frontend. Its frontend service has **no build `target`**, so it builds the Dockerfile's last stage (nginx on port 80) while publishing container port 3000.
- **Frontend Dockerfile** is multi-stage: `dev` (node:20-alpine), `build` (`npm run build` = `tsc && vite build`), and `prod` (nginx:1.27-alpine). It uses `npm install`, not `npm ci`. There is no `.nvmrc` or `engines` field.
- **Backend Dockerfile:** `python:3.12-slim` plus apt `freetds-dev mdbtools`.
- **Migrations run inside the app at startup.** See §2 and §9.
- **CI:** not present. There is no `.github/`, GitLab, Azure or Jenkins config. `backend/evals/README.md` says: "This repository has no CI (no remote either)."
- **Scripts:** `scripts/` holds `demo_up.ps1`, `demo_down.ps1`, `backup.ps1`, `restore.ps1`, `build_offline_bundle.ps1` (an air-gap bundle), `seed_dev_accounts.py`, `seed_demo_gaps.py` and `export_users_workbook.py`. `qa/seed.ps1` wraps `demo_up` and `seed_dev_accounts`.

---

## 2. ARCHITECTURE

### Layering as it exists

```
Browser (React SPA, Vite)                                   external host application
  pages/*  ──►  components/*  ──►  services/api.ts (single axios instance, /api/v1, Bearer JWT from localStorage)
                                               │                                   │ (signed embed JWT)
                                               ▼                                   ▼
                     ┌──────── FastAPI app (backend/app/main.py) ─────────────────────────────┐
                     │ middleware: CORS · OTel (opt-in) · rate-limit · unhandled→500          │
                     │ 25 router modules, 27 include_router calls, all prefix /api/v1         │
                     │ auth dep: dependencies.get_current_user (JWT or dk_ API key → User)    │
                     └───────┬───────────────────┬───────────────────┬────────────────────────┘
                             │                   │                   │
             routers/reports.py        routers/widget_data.py   routers/agent.py, report_copilot.py
             (CRUD, persists at       (_resolve_widget_data)     (services/agent/graph.py → LLM)
              once, revision++)              │                              │
                    │                ┌───────┴──────────┐        LLM (vLLM/Qwen, httpx, JSON schema)
                    ▼                ▼                  ▼                    │
          Postgres (ORM, 79     import mode          DirectQuery             ▼
           tables): reports,   services/widget_data  services/direct_query  sqlglot validation ladder
           pages, widgets,     ├ duck_agg (DuckDB     ├ f-string SQL +       → executor: customer DB
           datasets, RLS…      │  over parquet/csv)   │  sql_expr RLS           or DuckDB over
                               └ pandas (load_file,   └ SQLAlchemy text()       RLS'd pandas frames
                                 RLS, prep, SHAPERS)     on customer DB
                                        │                      │
                                        └──── shaped dict (untyped) ──► frontend
                                                                        WidgetRenderer → WidgetBody
                                                                        → CHART_RENDERERS[type]
                                                                        (Recharts / d3-geo / SVG / HTML)

Background (same process, started in lifespan): refresh_scheduler.run_scheduler — dataset refresh,
dataflow refresh, report schedules (PDF/xlsx → SMTP/webhook), data alerts, automation_runner.tick.
```

### Where a user request enters
- **Browser:** every call goes through `frontend/src/services/api.ts`, verbatim:
  ```ts
  const CONFIGURED_ORIGIN = (import.meta.env.VITE_API_URL ?? '').trim()
  const API_ORIGIN = CONFIGURED_ORIGIN || (import.meta.env.PROD ? '' : 'http://localhost:8000')
  const BASE = API_ORIGIN + '/api/v1'
  export const api = axios.create({ baseURL: BASE })
  ```
  The token lives in `localStorage['datalytics_token']` and is attached as `Authorization: Bearer …` by a request interceptor (`api.ts:30-65`).
- **Backend:** `backend/app/main.py:455-544` defines `app = FastAPI(title="Datalytics API", version="2.0.0", lifespan=lifespan)`. It registers `CORSMiddleware`, `setup_telemetry` (opt-in), the `_rate_limit_gate` middleware and the `unhandled_errors_keep_cors_headers` middleware, then 27 `app.include_router(..., prefix="/api/v1")` calls.
- **Machine clients:**
  - `backend/mcp_server/` is a separate stdio MCP server with 9 tools that proxy HTTP to `/api/v1`, authenticated with `dk_` API keys.
  - Embeds use `/api/v1/embed/*`.
  - Share links use `/api/v1/shared/{token}`.

### Middleware order
The docstring at `main.py:482-492` says the error middleware sits **inside** CORS ("Registered after CORSMiddleware, so it sits INSIDE it"). In Starlette, however, each `add_middleware` call (and `@app.middleware`) inserts at the front of the stack. So the last-registered middleware, `unhandled_errors_keep_cors_headers`, is the **outermost**, outside CORS. This is an ordering fact about the framework; the audit did not observe it at runtime.

### Startup (`main.py:349-452`, lifespan)
```python
async with engine.connect() as lockconn:
    is_pg = lockconn.dialect.name == "postgresql"
    if is_pg:
        await lockconn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": _STARTUP_LOCK_KEY})
    try:
        await _run_alembic()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await _migrate(conn)
```
The lifespan then runs, in order:
1. `_backfill_default_org`, `_run_secrets_migration`, `reap_stuck_sync_runs`, `reap_orphaned_failures`, `reap_stuck_automation_steps`
2. `asyncio.create_task(run_scheduler(AsyncSessionLocal))`
3. `eval_schedule.maybe_create_task(...)`, which is off by default
4. a one-shot `_probe_llm_contract()`

`/health/ready` returns 503 until `_STARTUP_COMPLETE` is set.

### Where data comes from
- **Import datasets:** uploaded files in the `uploaded_files` volume (`/app/uploads`), read by pandas or DuckDB.
- **DirectQuery datasets:** live SQL against a customer database through `services/engines.get_engine`.
- **App state:** Postgres.

### Where SQL is generated
In several places; there is no single compiler. See §4.
- **Widgets:** `services/direct_query.py` (DirectQuery) and `services/duck_agg.py` (DuckDB).
- **Security and filter predicates:** `services/sql_expr.py`.
- **Visual query builder:** `services/query_builder.py`.
- **Aggregate datasets:** `services/aggregates.py`.
- **LLM output:** raw SQL, written by the model and then validated with sqlglot (`services/agent/*`, `services/suggest_dashboard.py`).

### Where results are rendered
In the browser only:
- `components/report/WidgetRenderer.tsx` → `WidgetBody.tsx` → `components/report/chartRenderers/index.tsx` `CHART_RENDERERS`.
- The server also renders PDFs (`services/pdf_export.py`, reportlab plus matplotlib).

---

## 3. DATA MODEL

### Where it lives
- **Models:** all in `backend/app/models/models.py` (2,136 lines). **79 SQLAlchemy model classes, which is 79 tables** (`grep -c "^class .*(Base)"` = 79).
- **Base and engine:** `core/database.py` uses async SQLAlchemy 2.x with a plain `DeclarativeBase`.
- **Schema definitions:** three mechanisms, all run at startup:
  - Alembic: 35 revisions, from `0001_baseline.py` to head **`0035_page_layout_mode`**.
  - `Base.metadata.create_all`.
  - `main.py` `_migrate()`: 77 raw `ALTER TABLE … ADD COLUMN IF NOT EXISTS` / `CREATE …` statements.
  - `main.py:238-241` states: "*create_all + _migrate still run right after this, unconditionally, and remain what actually guarantees the schema is correct this cycle -- Alembic is additive here, not yet load-bearing.*"
- **`postgres/init.sql`** (99 lines) is mounted as the Postgres init script. It creates only 8 legacy tables without later columns, including a `charts` table that has **no ORM model**.

### All 79 tables, by area
Field-level detail for the core entities is quoted below. The remainder are listed by name and purpose.

| Area | Tables |
|---|---|
| Datasets and semantic metadata | `datasets`, `dataset_shares`, `dataset_columns`, `analysis_results`, `hierarchy_nodes`, `relationships`, `data_views`, `watermarks`, `materializations`, `column_stats`, `prediction_models` |
| Sources and catalog | `data_sources`, `custom_connectors`, `source_objects`, `source_columns`, `source_relationships`, `schema_versions`, `sync_runs`, `entities`, `glossary_terms`, `boundary_sets` |
| Reports | `reports`, `report_pages`, `report_widgets`, `report_versions`, `bookmarks`, `report_parameters`, `common_filters`, `report_classifications`, `report_translations`, `report_comments`, `report_schedules`, `report_capability`, `report_user_grants`, `page_role_visibility`, `page_templates`, `widget_templates`, `org_themes`, `recent_views`, `pinned_tiles`, `share_links`, `share_link_access`, `embed_configs`, `workspace_nodes`, `workspace_folder_roles`, `workspace_folder_grants` |
| Identity and security | `organizations`, `roles`, `users`, `org_units`, `user_org_units`, `row_security_rules`, `column_security_rules`, `object_row_policies`, `api_keys`, `org_idps`, `saml_authn_requests`, `org_mcp_access`, `org_parents`, `quotas`, `audit_log`, `admin_audit` |
| Delivery | `deliveries`, `data_alerts`, `notifications` |
| Agent and telemetry | `conversations`, `agent_messages`, `agent_runs`, `agent_steps`, `agent_feedback`, `eval_runs`, `query_examples`, `query_runs`, `retrieval_embeddings` |
| Scheduling and automation | `schedule_failures`, `dataflows`, `dataflow_capabilities`, `automation_runs`, `automation_steps` |

### Fields of every table

Compact field lists from a full read of `models.py`. Line numbers are `models.py:<n>`.

Legend: **NN** = `nullable=False`, **N** = nullable, **JSON** = JSON column, **FK→** = foreign key (ondelete rule). Every `created_at`/`updated_at` is `DateTime(timezone=True)`. The `id` Integer primary key is omitted unless noted.

#### Datasets and semantic metadata

**Dataset → `datasets`** (`models.py:7`)
| column | type | null | notes |
|---|---|---|---|
| name | String(255) | NN | |
| description | Text | N | |
| filename | String(500) | N | |
| row_count / col_count | Integer | N | default 0 |
| file_size | BigInteger | N | |
| calculated_columns | **JSON** | N | default list |
| custom_functions | **JSON** | N | default list |
| column_formats | **JSON** | N | default dict |
| measures | **JSON** | N | default list, post-aggregation measures |
| column_meta | **JSON** | N | default dict, per-column author overrides |
| default_filter_expr | Text | N | |
| data_source_id | Integer | N | FK→data_sources (SET NULL) |
| source_table | String(500) | N | |
| source_query | Text | N | |
| query_model | **JSON** | N | visual query-builder graph |
| mode | String(20) | NN | default "import" |
| refresh_interval_minutes | Integer | N | |
| last_refreshed_at | DateTime | N | |
| aggregate_of_dataset_id | Integer | N | FK→datasets (CASCADE), indexed |
| aggregate_spec | **JSON** | N | |
| is_deprecated | Boolean | NN | |
| description_source | String(20) | N | |
| last_profiled_at | DateTime | N | |
| org_id | Integer | N | FK→organizations (CASCADE) |
| created_by | Integer | N | FK→users (SET NULL) |

**DatasetShare → `dataset_shares`** (`:82`): dataset_id FK→datasets (CASCADE) NN; user_id FK→users (CASCADE) NN; created_at. Unique on (dataset_id, user_id).

**DatasetColumn → `dataset_columns`** (`:101`): dataset_id FK NN; name String(255) NN; dtype String(50) NN; missing_pct Float; stats **JSON**; semantic_type String(40) N; description Text N; description_source String(20) N; source_column_id FK→source_columns (SET NULL) N.

**AnalysisResult → `analysis_results`** (`:133`): dataset_id FK NN; analysis_type String(100) NN; result **JSON** NN; run_id FK→automation_runs (SET NULL) N; params **JSON** N; created_by FK→users N.

**HierarchyNode → `hierarchy_nodes`** (`:264`): dataset_id FK NN; parent_id FK→hierarchy_nodes (CASCADE) N; name String(255) NN; node_type String(20) NN default "folder"; column_name String(255); aggregation String(50); format String(100); position Integer NN.

**Relationship → `relationships`** (`:533`): org_id FK NN; from_dataset_id FK NN; from_column String(255) NN; to_dataset_id FK NN; to_column String(255) NN; confidence Float NN; source String(20) NN default "declared"; evidence **JSON** N; cardinality String(20) N.

**DataView → `data_views`** (`:865`): org_id FK NN; name String(255) NN; payload **JSON** NN; creator_user_id FK N; is_default Boolean NN.

**Watermark → `watermarks`** (`:1256`): dataset_id FK unique NN; strategy String(20) NN; cursor_column String(255) N; cursor_value Text N; updated_at.

**Materialization → `materializations`** (`:1274`): dataset_id FK unique NN; path String(1000) NN; kind String(20) NN; row_count Integer NN; columns **JSON** NN; watermark_value Text N.

**ColumnStats → `column_stats`** (`:1171`): dataset_column_id FK→dataset_columns unique N; source_column_id FK→source_columns unique N; null_ratio Float; distinct_count BigInteger; top_k **JSON**; min_value / max_value Text; avg_width Integer; exact Boolean NN; computed_at.

**PredictionModel → `prediction_models`** (`:371`): org_id FK NN; dataset_id FK NN; name String(200) NN; target String(255) NN; features **JSON** NN; feature_columns **JSON** NN; categories **JSON** NN; task String(32) NN; model_family String(64) NN; score Float N; score_name String(32) N; artifact LargeBinary NN (joblib pickle); trained_rls Text N; created_by FK N. Unique on (org_id, dataset_id, name).

#### Data sources and the source catalog

**DataSource → `data_sources`** (`:280`): name String(255) NN; type String(50) NN; config **JSON** (secrets encrypted); cache_ttl_seconds Integer NN default 60; allow_llm_sampling Boolean NN; description Text N; description_source String(20) N; last_synced_at DateTime N; sync_status String(20) NN default "pending"; org_id FK N; created_by FK N; created_at / updated_at; cache_epoch Integer NN; custom_connector_id FK→custom_connectors (RESTRICT) N.

**CustomConnector → `custom_connectors`** (`:323`): org_id FK NN; key String(100) NN; label String(255) NN; base_type String(50) NN; base_config **JSON**; locked_fields **JSON**; created_by FK N. Unique on (org_id, key).

**SourceObject → `source_objects`** (`:1323`): data_source_id FK NN; org_id FK NN; schema_name String(255) N; name String(500) NN; kind String(20) NN; row_count_estimate BigInteger N; comment Text N; description Text N; description_source N; is_canonical Boolean NN; is_deprecated Boolean NN; last_profiled_at N; sample_timed_out_at N. Unique on (data_source_id, schema_name, name).

**SourceColumn → `source_columns`** (`:1369`): source_object_id FK NN; name String(500) NN; position Integer NN; native_type String(255) N; dtype String(50) N; nullable Boolean NN; is_primary_key Boolean NN; comment Text N; semantic_type String(40) N; description Text N; description_source N; enum_labels **JSON** N; enum_labels_source N; target_candidate_priority Integer N. Unique on (source_object_id, name).

**SourceRelationship → `source_relationships`** (`:1413`): data_source_id, org_id, from_object_id, to_object_id (all FK NN); from_column / to_column String(500) NN; confidence Float NN; source String(20) NN; evidence **JSON** N; cardinality N.

**SchemaVersion → `schema_versions`** (`:1207`): data_source_id FK NN; org_id FK NN; fingerprint String(64) NN; diff **JSON** N; detected_at.

**SyncRun → `sync_runs`** (`:1232`): data_source_id FK NN; org_id FK NN; trigger String(20) NN; status String(20) NN; stages **JSON** NN; error Text N; started_at; finished_at N.

**Entity → `entities`** (`:1691`): org_id FK NN; data_source_id FK NN; name String(255) NN; business_name N; grain Text N; description Text N; primary_object String(500) N; source String(20) NN default "inferred". Unique on (data_source_id, name).

**GlossaryTerm → `glossary_terms`** (`:1565`): org_id FK NN; data_source_id FK N; term String(200) NN; definition Text N; synonyms **JSON** NN; maps_to_object String(255) N; maps_to_column String(255) N.

**BoundarySet → `boundary_sets`** (`:343`): org_id FK NN; name String(200) NN; geometry **JSON** NN (GeoJSON); key_properties **JSON**; feature_count Integer NN; created_by FK N. Unique on (org_id, name).

#### Reports, dashboards and widgets

**Report → `reports`** (`:150`): name String(255) NN; description Text; dataset_id FK→datasets (SET NULL) N; additional_dataset_ids **JSON** default list; theme String(20) NN default "default"; display_rules **JSON** default list; revision Integer NN default 0; created_by FK→users (SET NULL) N; published Boolean NN; origin String(20) NN default "user"; org_id FK N; created_at / updated_at. Relationships: `pages` (cascade, ordered by position) and `bookmarks`.

**ReportPage → `report_pages`** (`:198`): report_id FK (CASCADE) NN; name String(255) NN; title String(255); page_type String(20) NN default "normal"; prompt_column / prompt_label String(255); position Integer NN; page_size String(20) NN default "16:9"; custom_width / custom_height Integer N; mobile_layout **JSON** N; background_url String(1000) N; layout_mode String(20) N; layout_template String(40) N.

**ReportWidget → `report_widgets`** (`:252`): page_id FK (CASCADE) NN; widget_type String(50) NN; title String(255); config **JSON** default dict; layout **JSON** default `{"x":0,"y":0,"w":6,"h":4}`.

**ReportVersion → `report_versions`** (`:225`): report_id FK NN; revision Integer NN; snapshot **JSON** NN; created_by FK N.

**Bookmark → `bookmarks`** (`:560`): report_id FK NN; name String(255) NN; position Integer NN; state **JSON** NN.

**ReportParameter → `report_parameters`** (`:606`): report_id FK NN; name String(60) NN; param_type String(20) NN; label String(120); default_value String(500); options **JSON**; position NN.

**CommonFilter → `common_filters`** (`:983`): report_id FK NN; column String(255) NN; op String(10) NN default "eq"; value **JSON**; position NN.

**ReportClassification → `report_classifications`** (`:891`): report_id FK unique NN; org_id FK NN; label String(40) NN; updated_at.

**ReportTranslation → `report_translations`** (`:1148`): report_id FK NN; locale String(10) NN; payload **JSON** NN (keys "w<id>" / "c<id>").

**ReportComment → `report_comments`** (`:1034`): org_id NN, report_id NN, page_id (SET NULL) N, user_id NN (all FK); text Text NN.

**ReportSchedule → `report_schedules`** (`:627`): org_id, report_id, creator_user_id (FK NN); interval_minutes Integer NN; recipients **JSON** NN; subject String(200); last_run_at N; last_status String(200); timezone String(64) N.

**ReportCapability → `report_capability`** (`:829`): report_id FK NN; role_id FK NN; level String(10) NN default "data".

**ReportUserGrant → `report_user_grants`** (`:804`): report_id FK NN; user_id FK NN; level String(5) NN default "edit". Unique on (report_id, user_id).

**PageRoleVisibility → `page_role_visibility`** (`:788`): page_id FK NN; role_id FK NN.

**PageTemplate → `page_templates`** (`:700`): org_id FK NN; name String(120) NN; kind String(20) NN; payload **JSON** NN.

**WidgetTemplate → `widget_templates`** (`:999`): org_id FK NN; name String(255) NN; widget_type String(50) NN; config **JSON** NN; creator_user_id FK N.

**OrgTheme → `org_themes`** (`:590`): org_id FK NN; name String(100) NN; colors **JSON** NN.

**RecentView → `recent_views`** (`:717`): user_id FK NN; report_id FK NN; viewed_at NN. Unique on (user_id, report_id).

**PinnedTile → `pinned_tiles`** (`:748`): org_id FK NN; user_id FK NN; widget_id FK→report_widgets N; dataset_id FK N; finding_key Text N; position Integer N; size String(1) NN. Two unique constraints.

**ShareLink → `share_links`** (`:1049`): org_id, report_id, creator_user_id (FK NN); token_hash String(64) unique NN; expires_at NN; revoked_at N; snapshot **JSON** N; pinned Boolean NN.

**ShareLinkAccess → `share_link_access`** (`:1075`): share_link_id FK NN; viewer_user_id FK N; ts; ip_hash String(64) N; user_agent String(200) N.

**EmbedConfig → `embed_configs`** (`:1092`): org_id, report_id, created_by (FK NN); name String(255) NN; secret_encrypted Text NN; allowed_origins **JSON**; enabled Boolean NN; last_used_at N. Unique on (report_id, name).

**WorkspaceNode → `workspace_nodes`** (`:1734`): org_id FK NN; parent_id FK self N; node_type String(20) NN; name String(255) N; report_id FK unique N; created_by FK N; position NN; published Boolean NN.

**WorkspaceFolderRole → `workspace_folder_roles`** (`:1793`): node_id FK NN; role_id FK NN. Unique on the pair.

**WorkspaceFolderGrant → `workspace_folder_grants`** (`:1870`): org_id FK NN; node_id FK NN; user_id / role_id / org_unit_id FK N (exactly one is set, enforced by the router); level String(10) NN; created_by FK N.

#### Users, organisations, roles and security

**Organization → `organizations`** (`:420`): name String(255) NN.

**Role → `roles`** (`:430`): org_id FK NN; name String(255) NN; is_org_admin Boolean NN.

**User → `users`** (`:443`): org_id FK NN; role_id FK→roles (RESTRICT) NN; email String(255) unique NN; password_hash String(255) NN; is_active Boolean NN.

**OrgUnit → `org_units`** (`:457`): org_id FK NN; parent_id FK self N; name String(255) NN; level_name String(60); match_value String(255) NN; position NN. Unique on (org_id, parent_id, name).

**UserOrgUnit → `user_org_units`** (`:493`): user_id FK NN; org_unit_id FK NN. Unique on the pair.

**RowSecurityRule → `row_security_rules`** (`:515`): role_id FK NN; dataset_id FK NN; filter_expr Text NN; auto_generated Boolean NN. Unique on (role_id, dataset_id).

**ColumnSecurityRule → `column_security_rules`** (`:850`): role_id FK NN; dataset_id FK NN; denied_columns **JSON** NN.

**ObjectRowPolicy → `object_row_policies`** (`:1619`): org_id, source_object_id, role_id (FK NN); predicate Text NN. Unique on (source_object_id, role_id).

**ApiKey → `api_keys`** (`:905`): org_id FK NN; user_id FK NN; name String(120) NN; prefix String(16) unique NN; key_hash String(64) NN; last_used_at N.

**OrgIdp → `org_idps`** (`:924`): org_id FK unique NN; protocol String(10) NN; enabled NN; email_domain String(255) NN; issuer String(500); client_id String(255); client_secret String(1000) (encrypted); config **JSON**.

**SamlAuthnRequest → `saml_authn_requests`** (`:945`): id String(64) PK; org_id FK NN; acs_url String(1000) NN.

**OrgMcpAccess → `org_mcp_access`** (`:958`): org_id FK unique NN; enabled NN.

**OrgParent → `org_parents`** (`:970`): org_id FK unique NN; parent_org_id FK NN.

**Quota → `quotas`** (`:1125`): org_id FK unique NN; max_queries_per_day, max_agent_asks_per_day, max_storage_mb and max_concurrent_asks (all Integer N).

**AuditLogEntry → `audit_log`** (`:571`): org_id FK NN; user_id FK N; user_email String(255); action String(50) NN; entity String(50); entity_id Integer; detail String(500).

**AdminAudit → `admin_audit`** (`:1638`): org_id FK NN; actor_id FK N; actor_email; action String(50) NN; target String(255); detail String(500).

#### Delivery, alerts and notifications

- **Delivery → `deliveries`** (`:653`): org_id FK NN; schedule_id FK N; report_id FK N; kind String(20) NN; status String(10) NN; error Text N; artifact_kind String(10) NN; duration_ms N.
- **DataAlert → `data_alerts`** (`:677`): org_id, dataset_id, creator_user_id (FK NN); name String(200) NN; expression Text NN; interval_minutes NN; recipients **JSON** NN; last_checked_at N; last_state String(10) NN; last_status.
- **Notification → `notifications`** (`:1017`): org_id FK NN; user_id FK NN; kind String(40) NN; text String(500) NN; link String(500) N; read_at N.

#### Agent, retrieval and telemetry

- **Conversation → `conversations`** (`:1439`): org_id FK NN; user_id FK N; data_source_id FK N; dataset_ids **JSON** N; title String(200) N.
- **AgentMessage → `agent_messages`** (`:1457`): conversation_id FK NN; role String(20) NN; content Text NN; agent_run_id FK N.
- **AgentRun → `agent_runs`** (`:1469`): org_id FK NN; conversation_id FK N; question Text NN; status String(30) NN; intent String(30) N; plan **JSON** N; answer Text N; error Text N; ms N; context_objects **JSON** N; presentation **JSON** N.
- **AgentStep → `agent_steps`** (`:1494`): agent_run_id FK NN; node String(80) NN; status String(30) NN; sql Text N; rows_returned N; result_rows **JSON** N; validation_failures **JSON** N; repair_attempts NN; ms N.
- **AgentFeedback → `agent_feedback`** (`:1514`): org_id, user_id, conversation_id (FK NN); run_id FK N; rating String(10) NN; comment Text N.
- **EvalRun → `eval_runs`** (`:1533`): started_at NN; finished_at N; accuracy Float N; passed Boolean N; detail **JSON** N.
- **QueryExample → `query_examples`** (`:1548`): org_id FK NN; data_source_id FK N; dataset_key String(120) N; question Text NN; sql Text NN; confirmed_by FK N.
- **QueryRun → `query_runs`** (`:1588`): org_id FK N; source_kind String(20) NN; data_source_id FK N; dataset_id FK N; sql_hash String(64) N; rows_returned N; duration_ms NN; executor String(20) NN; cache_hit NN; source_table N; filter_columns **JSON** N; group_column N.
- **RetrievalEmbedding → `retrieval_embeddings`** (`:1662`): kind String(30) NN; ref String(500) NN; text_hash String(64) NN; vector **JSON** NN; model String(200) NN. Unique on (text_hash, model).

#### Scheduling, dataflows and automation

- **ScheduleFailure → `schedule_failures`** (`:1832`): kind String(20) NN; item_id Integer NN; attempts NN; next_attempt_at N; last_error Text N; first_failed_at; updated_at. Unique on (kind, item_id).
- **Dataflow → `dataflows`** (`:1927`): org_id FK NN; name String(255) NN; description Text N; steps **JSON** NN; source_dataset_id FK N; join_dataset_ids **JSON** NN; refresh_interval_minutes N; created_by FK N; last_run_at, last_run_status, last_run_rows, last_run_error (all N).
- **DataflowCapability → `dataflow_capabilities`** (`:1969`): dataflow_id FK NN; role_id FK NN; level String(10) NN. Unique on the pair.
- **AutomationRun → `automation_runs`** (`:2013`): org_id FK NN; created_by FK N; trigger String(30) NN; subject_type String(30) N; subject_id Integer N; status String(20) NN; result_report_id FK N; result_report_name N; proposal_path String(20) N; widgets_accepted / widgets_rejected N; rejection_reasons **JSON** N; raw_proposals **JSON** N; error Text N; finished_at N.
- **AutomationStep → `automation_steps`** (`:2088`): run_id FK NN; name String(40) NN; order Integer NN; status String(20) NN; output_ref Text N; error Text N; attempts NN; next_attempt_at N; started_at N; finished_at N. Unique on (run_id, name).

### Core entities (verbatim; `...` marks removed comment blocks only)

**Data source / connection** (`models.py:280-320`):
```python
class DataSource(Base):
    __tablename__ = "data_sources"
    id         = Column(Integer, primary_key=True)
    name       = Column(String(255), nullable=False)
    type       = Column(String(50), nullable=False)
    config     = Column(JSON, default=dict)
    cache_ttl_seconds = Column(Integer, nullable=False, default=60, server_default="60")
    allow_llm_sampling = Column(Boolean, nullable=False, default=False, server_default="0")
    ...
    description        = Column(Text, nullable=True)
    description_source = Column(String(20), nullable=True)   # inferred | confirmed
    last_synced_at     = Column(DateTime(timezone=True), nullable=True)
    sync_status        = Column(String(20), nullable=False, default="pending", server_default="pending")
    org_id     = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    ...
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                        nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    ...
    cache_epoch = Column(Integer, nullable=False, default=0, server_default="0")
    ...
    custom_connector_id = Column(Integer, ForeignKey("custom_connectors.id", ondelete="RESTRICT"),
                                  nullable=True, index=True)
```

**Dataset** (`models.py:7-79`):
```python
class Dataset(Base):
    __tablename__ = "datasets"
    id          = Column(Integer, primary_key=True)
    name        = Column(String(255), nullable=False)
    description = Column(Text)
    filename    = Column(String(500))
    row_count   = Column(Integer, default=0)
    col_count   = Column(Integer, default=0)
    file_size   = Column(BigInteger, default=0)
    created_at  = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at  = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    calculated_columns  = Column(JSON, default=list)
    ...
    custom_functions    = Column(JSON, default=list)
    column_formats      = Column(JSON, default=dict)
    # Post-aggregation measures — evaluated at the requesting widget's grouping grain,
    # unlike calculated_columns which are row-level and applied before aggregation.
    measures            = Column(JSON, default=list)
    # Per-column author overrides, keyed by column name: role (classification
    # override), aggregation (default when assigned to a measure role), hidden,
    # label. Detection stays the source of truth for dtype; this only overrides it.
    column_meta         = Column(JSON, default=dict)
    default_filter_expr = Column(Text, nullable=True)
    data_source_id      = Column(Integer, ForeignKey("data_sources.id", ondelete="SET NULL"), nullable=True)
    source_table        = Column(String(500), nullable=True)
    source_query        = Column(Text, nullable=True)
    ...
    query_model         = Column(JSON, nullable=True)
    mode                = Column(String(20), nullable=False, default="import", server_default="import")
    ...
    refresh_interval_minutes = Column(Integer, nullable=True)
    last_refreshed_at        = Column(DateTime(timezone=True), nullable=True)
    ...
    aggregate_of_dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"),
                                     nullable=True, index=True)
    aggregate_spec          = Column(JSON, nullable=True)
    ...
    is_deprecated      = Column(Boolean, nullable=False, default=False, server_default="0")
    description_source = Column(String(20), nullable=True)   # inferred | confirmed
    last_profiled_at   = Column(DateTime(timezone=True), nullable=True)
    org_id          = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    ...
    created_by      = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"),
                             nullable=True, index=True)

    columns          = relationship("DatasetColumn", back_populates="dataset", cascade="all, delete-orphan")
    analysis_results = relationship("AnalysisResult", back_populates="dataset", cascade="all, delete-orphan")
    hierarchy_nodes  = relationship("HierarchyNode", back_populates="dataset", cascade="all, delete-orphan")
```

**Column metadata** (`models.py:101-130`):
```python
class DatasetColumn(Base):
    __tablename__ = "dataset_columns"
    id          = Column(Integer, primary_key=True)
    dataset_id  = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    name        = Column(String(255), nullable=False)
    dtype       = Column(String(50), nullable=False)
    missing_pct = Column(Float, default=0)
    stats       = Column(JSON, default=dict)
    created_at  = Column(DateTime(timezone=True), default=datetime.utcnow)
    semantic_type      = Column(String(40), nullable=True)
    description        = Column(Text, nullable=True)
    description_source = Column(String(20), nullable=True)
    source_column_id   = Column(Integer, ForeignKey("source_columns.id", ondelete="SET NULL"),
                                nullable=True, index=True)
    dataset     = relationship("Dataset", back_populates="columns")
```
The connected-database catalog has its own column table, `SourceColumn` (`models.py:1369-1410`). It carries `native_type`, `dtype`, `comment`, `semantic_type`, `description`, `enum_labels` (JSON) and `target_candidate_priority`.

**Report / dashboard** (`models.py:150-195`):
```python
class Report(Base):
    __tablename__ = "reports"
    id                     = Column(Integer, primary_key=True)
    name                   = Column(String(255), nullable=False)
    description            = Column(Text)
    dataset_id             = Column(Integer, ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True)
    additional_dataset_ids = Column(JSON, default=list)
    theme                  = Column(String(20), nullable=False, default="default", server_default="default")
    display_rules          = Column(JSON, default=list)
    revision               = Column(Integer, nullable=False, default=0, server_default="0")
    ...
    created_by             = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    ...
    published              = Column(Boolean, nullable=False, default=False, server_default="0")
    ...
    origin                 = Column(String(20), nullable=False, default="user",
                                    server_default="user", index=True)
    org_id                 = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    created_at             = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at             = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    pages                  = relationship("ReportPage", back_populates="report", cascade="all, delete-orphan",
                                          order_by="ReportPage.position")
    bookmarks              = relationship("Bookmark", back_populates="report", cascade="all, delete-orphan",
                                          order_by="Bookmark.position")
```

**Page** (`models.py:198-222`):
```python
class ReportPage(Base):
    __tablename__ = "report_pages"
    id             = Column(Integer, primary_key=True)
    report_id      = Column(Integer, ForeignKey("reports.id", ondelete="CASCADE"), nullable=False)
    name           = Column(String(255), nullable=False, default="Page 1")
    title          = Column(String(255))
    page_type      = Column(String(20), nullable=False, default="normal")
    prompt_column  = Column(String(255))
    prompt_label   = Column(String(255))
    position       = Column(Integer, nullable=False, default=0)
    page_size      = Column(String(20), nullable=False, default="16:9", server_default="16:9")
    custom_width   = Column(Integer, nullable=True)
    custom_height  = Column(Integer, nullable=True)
    mobile_layout  = Column(JSON, nullable=True)
    ...
    background_url = Column(String(1000), nullable=True)
    layout_mode    = Column(String(20), nullable=True)
    layout_template = Column(String(40), nullable=True)
    created_at     = Column(DateTime(timezone=True), default=datetime.utcnow)
    report         = relationship("Report", back_populates="pages")
    widgets        = relationship("ReportWidget", back_populates="page", cascade="all, delete-orphan")
```

**Widget / chart** (`models.py:252-261`; re-read against source):
```python
class ReportWidget(Base):
    __tablename__ = "report_widgets"
    id          = Column(Integer, primary_key=True)
    page_id     = Column(Integer, ForeignKey("report_pages.id", ondelete="CASCADE"), nullable=False)
    widget_type = Column(String(50), nullable=False)
    title       = Column(String(255))
    config      = Column(JSON, default=dict)
    layout      = Column(JSON, default=lambda: {"x": 0, "y": 0, "w": 6, "h": 4})
    created_at  = Column(DateTime(timezone=True), default=datetime.utcnow)
    page        = relationship("ReportPage", back_populates="widgets")
```

**User / org / role** (`models.py:420-454`):
```python
class Organization(Base):
    __tablename__ = "organizations"
    id         = Column(Integer, primary_key=True)
    name       = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

class Role(Base):
    __tablename__ = "roles"
    id           = Column(Integer, primary_key=True)
    org_id       = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name         = Column(String(255), nullable=False)
    is_org_admin = Column(Boolean, nullable=False, default=False)
    created_at   = Column(DateTime(timezone=True), default=datetime.utcnow)

class User(Base):
    __tablename__ = "users"
    id            = Column(Integer, primary_key=True)
    org_id        = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    role_id       = Column(Integer, ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False)
    email         = Column(String(255), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    is_active     = Column(Boolean, nullable=False, default=True)
    created_at    = Column(DateTime(timezone=True), default=datetime.utcnow)
```
Each user has exactly one role. Org-chart placement for row scoping lives in `org_units` and `user_org_units`.

**Security rules**, all keyed by **role**, not by user:
```python
class RowSecurityRule(Base):                       # models.py:515
    __tablename__ = "row_security_rules"
    id          = Column(Integer, primary_key=True)
    role_id     = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    dataset_id  = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    filter_expr = Column(Text, nullable=False)
    ...
    auto_generated = Column(Boolean, nullable=False, default=False, server_default="0")
    created_at  = Column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("role_id", "dataset_id", name="uq_role_dataset_rule"),)

class ColumnSecurityRule(Base):                    # models.py:850
    __tablename__ = "column_security_rules"
    id             = Column(Integer, primary_key=True)
    role_id        = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    dataset_id     = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    denied_columns = Column(JSON, nullable=False, default=list)

class ObjectRowPolicy(Base):                       # models.py:1619 — used only by the Ask AI source path
    __tablename__ = "object_row_policies"
    id               = Column(Integer, primary_key=True)
    org_id           = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    source_object_id = Column(Integer, ForeignKey("source_objects.id", ondelete="CASCADE"), nullable=False)
    role_id          = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    predicate        = Column(Text, nullable=False)
```
Row security is therefore stored in **two separate policy models**:
- `row_security_rules` apply per dataset, to widgets, analysis and Ask AI dataset mode.
- `object_row_policies` apply per source table, to Ask AI source mode only.

### Is there a semantic layer?
**Partly. All of it is keyed by physical column name; there are no semantic IDs.**

**What exists:**
- **`Dataset.column_meta`** is a JSON dict **keyed by column name** holding author overrides. Its shape is `ColumnMeta`, `schemas.py:93-127`: `role` (`measure|category|temporal|geography|freetext|identifier`), `aggregation`, `hidden`, `label`, `boundary_set_id`, `eligible_for_suggestion` and `target_candidate_priority`.
  - The same dict also carries non-column dunder keys: `__prep_steps__` (the prep pipeline), `__derived_from__` and `__demo__`.
- **`Dataset.measures`** and **`Dataset.calculated_columns`** are JSON lists identified **by name**. Measure lookup is by name, and a real column with the same name wins (`services/widget_data.py:374-378`):
  ```python
  measure_def = None
  if meas and meas not in df.columns:
      measure_def = _measure_eval.resolve_measure(meas, config.get("measure_defs"))
  ```
- **A catalog/knowledge plane**: the `source_objects`/`source_columns`/`entities`/`glossary_terms` tables plus `dataset_columns.source_column_id` provenance. `services/knowledge.py` resolves it at read time into `DatasetKnowledge.columns: dict[str, ColumnKnowledge]`, also **keyed by column name** (`knowledge.py:152-164`). Descriptions reach the client as transient `DatasetOut` fields.
- **`DataView`** is a reusable bundle of column meta, formats, calculated columns, measures, filter and prep. It is applied "by COLUMN NAME on apply" (`models.py:865-875`).
- **`HierarchyNode`** is a drill-path/folder tree whose leaves hold `column_name`.

**Not present:**
- A semantic-model, dimension or measure table with stable IDs that widgets bind to.
- Any separation between a field's identity and its physical column name.

**Widgets reference raw column names.** The config panel's options are built from `DatasetColumn.name` (`frontend/src/components/report/WidgetConfigPanel.tsx:739-742`):
```ts
const colOptions = effectiveCols.map(c => ({ value: c.name, label: c.dtype === 'calculated' ? `ƒx ${c.name}` : `${c.name} (${c.dtype})` }))
```
The field list shows `column_meta[...].label` but drags the raw name: `e.dataTransfer.setData('application/x-field', c.name)` (`pages/ReportBuilder.tsx:1665`). The backend then resolves those strings directly against DataFrame columns or SQL identifiers.

### Pydantic schemas (`backend/app/schemas/schemas.py`, 903 lines)
Widget `config` is an untyped `dict` in every schema. No Pydantic model validates widget config contents.
```python
class WidgetCreate(BaseModel):
    widget_type: str
    title: Optional[str] = None
    config: dict = {}
    layout: dict = {"x": 0, "y": 0, "w": 6, "h": 4}

class WidgetUpdate(BaseModel):
    widget_type: Optional[str] = None
    title: Optional[str] = None
    config: Optional[dict] = None
    layout: Optional[dict] = None

class ReportUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    dataset_id: Optional[int] = None
    additional_dataset_ids: Optional[list[int]] = None
    theme: Optional[str] = None
    display_rules: Optional[list[dict]] = None
```
`widget_type` is a free `str` in the schema. The frontend's closed union and the backend `REQUIRED_ROLES` table are the only type registries (see §6).

---

## 4. QUERY PATH (one chart render, end to end)

### Step 1: the frontend builds the request
`components/report/WidgetRenderer.tsx` merges four kinds of filters into the widget config:
- the widget's own `config`
- report-wide filters
- cross-filters
- page-prompt filters

It sets them as `cfg.filters = [...existing, ...reportWide, ...crossFilters, ...pagePrompt]`, then adds drill and display-rule keys and calls (`:320`):
```ts
const result = await widgetDataApi.query(widgetDatasetId, mergedConfig, effectiveCalcCols, wt, { reportId, parameters, fresh })
```
`services/api.ts:1551-1573`:
```ts
query: (dsId: number, config: Record<string, unknown>, calculatedColumns: CalcColumn[] = [], widgetType = 'bar',
        opts?: { reportId?: number; parameters?: Record<string, unknown>; fresh?: boolean }) => {
  const body = {
    config, calculated_columns: calculatedColumns, widget_type: widgetType,
    report_id: opts?.reportId, parameters: opts?.parameters ?? {},
  }
  const key = `${dsId}|${JSON.stringify(body)}`
  ...
      const r = await api.post(`/datasets/${dsId}/widget-data`, body)
```
The client adds three things of its own:
- a 30-second cache with at most 100 entries, keyed on the request body
- in-flight deduplication
- a limit of 6 concurrent requests

Fetches are lazy: an IntersectionObserver starts them 300px before the widget scrolls into view.

### Step 2: the backend entry point, with a thin request object around an untyped query
`routers/widget_data.py:359` (re-read):
```python
@router.post("/{dataset_id}/widget-data")
async def query_widget(
    dataset_id: int, req: WidgetDataRequest,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
):
    return await _resolve_widget_data(dataset_id, req, db, current_user)
```
`schemas.py:512` (re-read):
```python
class WidgetDataRequest(BaseModel):
    config: dict
    calculated_columns: list[Any] = []
    widget_type: str = "bar"
    report_id: int | None = None
    parameters: dict[str, Any] = {}
```
There is a request model, but the query itself is `config: dict`. Every layer reads it with `config.get(...)`. `duck_agg.py` says there are "34 distinct `config.get(...)` keys across app/".

The internal dataclasses `QueryPlan`/`RowFetchPlan` (direct_query) and `DuckPlan` (duck_agg) are derived from that dict per engine. They are not a shared query-request type.

`_resolve_widget_data` (`widget_data.py:195`) is shared by four callers:
- the live endpoint
- the export endpoint
- share links (`routers/shared.py:289`)
- embeds (`routers/embed.py:385`)

### Step 3: identity checks and dispatch
`_resolve_widget_data` runs these checks in order:
1. `check_org`, the tenant check.
2. `require_dataset_read(db, current_user, dataset_id, report_id=…)`, which returns 404 when access is refused.
3. `quotas.enforce_query_quota`.
4. `_apply_report_parameters`.

It then branches on `ds.mode`.

**DirectQuery branch** (`widget_data.py:257-300`, re-read). It first refuses three features:
```python
if ds.mode == "directquery":
    if calc_cols:
        raise widget_error(400, "unsupported", "Calculated columns are not yet supported for DirectQuery datasets")
    if _config_uses_measure(req.config, measure_defs):
        raise widget_error(400, "unsupported", "Measures are not yet supported for DirectQuery datasets")
    if ds.default_filter_expr:
        raise widget_error(400, "unsupported", "Report-level filter expressions are not yet supported for DirectQuery datasets")
```
It then resolves row security and checks column security:
```python
    rls_filter_expr = await resolve_rls_expr(db, current_user, dataset_id)
    denied = await resolve_denied_columns(db, current_user, dataset_id)
    if denied:
        referenced = {v for v in req.config.values() if isinstance(v, str)}
        for f in (req.config.get("filters") or []):
            referenced.add(str(f.get("column")))
        if referenced & set(denied):
            raise widget_error(403, "forbidden_column", "This widget references a column your role cannot access")
    ...
    return await asyncio.to_thread(
        run_direct_query,
        source_cfg, ds, req.config, widget_type=req.widget_type, rls_filter_expr=rls_filter_expr,
        cache_ttl_seconds=source.cache_ttl_seconds, cache_epoch=source.cache_epoch,
        org_id=current_user.org_id,
    )
```
- The denied-column check looks only at top-level **string** config values and filter columns. List-valued keys such as `measures` and `columns`, and the `roles` dict, are not inspected.
- `services/direct_query.py` has **zero** references to `denied` or `drop_columns`, and its row-fetch plans issue `SELECT *`.
- The runtime effect of this combination was not tested.

**Import branch.** It resolves RLS, denied columns, prep steps, join frames and author expressions, then calls `services/widget_data.get_widget_data` (`:3196`) through `asyncio.to_thread`. That function:
1. Checks the result cache.
2. Tries DuckDB pushdown (`duck_agg.try_aggregate`). It is eligible only when there are no prep steps, calculated columns or measures, and it translates RLS through `sql_expr`.
3. Otherwise runs the pandas pipeline (`widget_data.py:3344-3365`, re-read):
   ```python
   df = load_file(file_path)
   _enforce_import_row_cap(df, file_path)
   df = apply_rls_filter(df, rls_filter_expr)
   if drop_columns:
       present = [c for c in drop_columns if c in df.columns]
       if present:
           df = df.drop(columns=present)
   if prep_steps:
       from .prep import apply_prep_steps
       df = apply_prep_steps(df, prep_steps, prep_aux_frames)
   if filter_expr:
       df = apply_filter_expr(df, filter_expr, silent=True)
   if calculated_columns:
       df = apply_calculated_columns(df, calculated_columns, custom_functions)
   result = get_widget_data_from_df(df, config, widget_type, measures=measures)
   ```
`get_widget_data_from_df` (`:2602`) dispatches with `shaper = SHAPERS.get(widget_type, shape_series)`. `SHAPERS` (`:2495`) maps about 55 widget types to about 25 shaper functions. Most chart types use `shape_series`. Display rules are then evaluated on the shaped result.

### Step 4: where SQL is built. There is no single compiler.

| File | What it builds |
|---|---|
| `services/direct_query.py` | DirectQuery widget SQL as f-strings with `:name` binds: `build_sql`, `build_count_sql`, `build_group_total_sql`, `build_row_totals_sql`, `build_histogram_bucket_sql`, `build_correlation_matrix_sql`, `build_row_fetch_sql`, `_build_count_series_sql`. sqlglot transpile is used for ClickHouse only (`_finalize_for_dialect`). |
| `services/duck_agg.py` | DuckDB `GROUP BY` over `read_parquet('…')` or `read_csv_auto('…')`. The file path is interpolated into the SQL; values are bound with `?`. |
| `services/sql_expr.py` | Converts a Python-AST expression into a parameterized `WHERE` fragment. Used for RLS and filter expressions on the DuckDB and DirectQuery paths. |
| `services/query_builder.py` | Visual query builder model → SQL, including recursive CTEs. Serves `/data-sources/{id}/build-query` only. |
| `services/aggregates.py:90` | `compile_aggregate_sql` for aggregate-dataset materialization. Reuses `direct_query._base_query_sql`. |
| `services/connections.py`, `dataset_refresh.py`, `index_advice.py`, `metadata/*` | Table previews, incremental refresh `SELECT * … WHERE col > :cursor_val`, catalog queries, profiling and sampling |
| `services/agent/*` | Model-written SQL, which is parsed and rewritten with sqlglot (row limits, policy injection) |
| `services/suggest_dashboard.py` | Model-written SQL, regex-checked (see §7) |

The central DirectQuery builder (`direct_query.py:295`):
```python
def build_sql(dataset, plan: QueryPlan, dialect: str,
              rls_where: str = "", rls_params: dict | None = None) -> tuple[str, dict]:
    base = _base_query_sql(dataset, rls_where)
    ...
    sql = (
        f"SELECT {dim_sql} AS {dim_sql}, {agg_sql} AS {meas_sql} "
        f"FROM ({base}) AS src{where_clause} "
        f"GROUP BY {dim_sql} "
        f"ORDER BY {order_col} {order_dir}{tiebreak} "
        f"{_limit_clause(dialect, plan.limit)}"
    )
    return _finalize_for_dialect(sql, dialect), {**(rls_params or {}), **params}
```
RLS is applied by wrapping the source as a subquery: `return f"SELECT * FROM ({inner}) AS rls_src WHERE {rls_where}"`.

**Pandas still aggregates in most paths:**
- DuckDB and DirectQuery results are passed back through the same pandas shaper. Only "grain-safe" aggregations are pushed down (`GRAIN_SAFE_AGGREGATIONS`, `direct_query.py:64`).
- For widgets `plan_query` refuses (count, countd, crosstab, running totals and others), DirectQuery fetches raw rows with `SELECT *` up to a cap (`DEFAULT_ROW_CAP = 10_000`, or `analysis_row_cap = 250_000`) and aggregates them in pandas.

### Step 5: identity in the query path
User identity is part of the query path. It enters through `dependencies.get_current_user`, which decodes a JWT or `dk_` API key into a `User`.

**Row filters come from `core/rls.py:167`** (re-read):
```python
async def resolve_rls_expr(db: AsyncSession, current_user: User, dataset_id: int) -> str | None:
    if current_user.role.is_org_admin:
        return None
    dataset_id, _spec = await _aggregate_source(db, dataset_id)
    result = await db.execute(
        select(RowSecurityRule).where(
            RowSecurityRule.role_id == current_user.role_id, RowSecurityRule.dataset_id == dataset_id,
        )
    )
    rule = result.scalar_one_or_none()
    if rule is None:
        return None
    ...
    expr = apply_user_context(
        rule.filter_expr, email=current_user.email, user_id=current_user.id,
        org_id=current_user.org_id, org_name=org_name,
    )
```
The resulting expression is applied three ways:
- **pandas:** `apply_rls_filter`, which fails closed to zero rows.
- **DuckDB:** `sql_expr.translate_filter_expr_null_safe`. If translation fails, the query falls back to pandas.
- **DirectQuery:** `sql_expr.translate_filter_expr`. If translation fails, the query raises `DirectQueryUnsupported`.

**Column denials** come from `core/rls.py:250` `resolve_denied_columns`:
- Import mode drops the denied columns after RLS.
- DuckDB validates its plan against the visible columns.
- DirectQuery only has the router check shown above.

**Share links and embeds substitute a different identity:**
- Share links resolve as the in-org viewer, otherwise as the link's creator.
- Embeds resolve as the embed config's creator.

**Other callers of `get_widget_data` that do not go through `_resolve_widget_data`:**
- `routers/reports.py:961-1006` `_resolve_report_sections` (PDF and scheduled PDF)
- `services/delivery.py:76-118` `build_digest` (xlsx digest)

Both pass `rls_filter_expr` but **no `drop_columns`**. In the lines read, no column-security step appeared on either path.

**Caching:** no cache is keyed by user ID. The keys are:

| Cache | Key |
|---|---|
| Import server cache | file stat + config + `__denied__` + `__prep__` + the verbatim, already-expanded RLS expression |
| DirectQuery server cache | RLS expression + TTL bucket + `cache_epoch` (no denied columns) |
| `frame_cache` | file identity only; it sits below every security layer by design |
| Frontend cache | request body, per tab |

### Step 6: result shape and rendering
**The response is not enforced by any schema.** `WidgetDataResponse` exists (`schemas.py:523`) but nothing references it, and no widget-data route declares a `response_model`:
```python
class WidgetDataResponse(BaseModel):
    type: str
    rows: list[Any] = []
    total: int = 0
    columns: Optional[list[str]] = None
    dimension: Optional[str] = None
    measure: Optional[str] = None
    aggregation: Optional[str] = None
```
The actual payload is whatever dict the shaper builds. For example (`widget_data.py:705`):
```python
result = {"type": "series", "dimension": dim, "measure": meas or "count",
          "aggregation": agg, "rows": rows, "total": len(df)}
```
- Rows are `{"name", "value"}`.
- Other shapes include `table`, `crosstab`, `matrix`, `cells`, `bars`, `links`, `forecast`, `value`, `text_values` and `error`.
- `rule_styles` and `rule_errors` are attached to every result.

On the frontend, `WidgetBody.tsx:431` reads `data.rows`, and `:462` looks up `CHART_RENDERERS[wt]`. Renderers receive the untyped props `ChartRendererProps { rows: any[]; data: any; cfg: any; … }`.

### Ask AI SQL is a separate path
The agent (§7) does **not** use `direct_query`, `duck_agg`, `sql_expr` or `SHAPERS`. The LLM writes the SQL, sqlglot validates it, and it runs either on the customer database via `engines.get_engine` or on DuckDB over RLS-filtered pandas frames. The only shared pieces are `engines`, `resolve_rls_expr`, `resolve_denied_columns`, `load_file` and `apply_rls_filter`.

---

## 5. FEATURE INVENTORY

"UI caller" means a function in `frontend/src/services/api.ts` that is called from non-test production code. Of the 287 routes, 241 have a UI caller and 8 are reached in other ways (SSO browser navigation, IdP callbacks, health probes). **38 have no UI caller.**

### Working (backend implementation plus UI caller)

**Accounts and access**
- Email/password login with JWT (HS256, 7-day expiry, bcrypt). OIDC login (PKCE) and SAML 2.0 SP-initiated login, match-existing users only. Per-org SSO configuration.
- Admin: users (including bulk create), roles, org units and user placement, row security rules (auto-generate and preflight), column security rules, export policy, API keys (`dk_…`), audit logs, SSO settings.
- Monitoring pages: jobs, deliveries, activity.
- Super-admin: create organizations, set quotas and org parent, toggle MCP access.

**Data**
- File upload, single and batch: CSV, XLSX, JSON, Parquet, XML (when lxml imports), and Access `.mdb`/`.accdb`, which are expanded to one dataset per table via mdbtools.
- Connections: create, test, browse schema, preview, import as a dataset, visual query builder (compile and preview), index advice, similar-dataset lookup.
- Custom connector presets (admin).
- Source metadata: sync, review queue, confirm, drift history, glossary, entities.
- Dataset detail:
  - data preview
  - calculated columns, measures, custom functions (each with preview)
  - prep steps and preview
  - materialize, aggregate datasets, rebuild, refresh and refresh schedule
  - data alerts, sharing, column formats and descriptions, column meta (set), data views (save, apply, set default)
  - dataset filter expression
  - hierarchies (auto-generate, update, delete)
  - duplicate column
- Lineage graph page.
- Statistics and analysis panel (`/analysis/registry`, `/analysis/run`), segmentation, association rules, key influencers, prediction models (train, list, score, delete).

**Dashboards ("reports")**
- Pages and widgets, persisted immediately on every edit, with a revision counter.
- Themes, display rules, common filters, parameters, bookmarks.
- Version history (50 kept) with restore.
- Comments, translations, page templates, widget templates.
- Page visibility per role, report capabilities per role, per-user grants.
- Publish, classification (set).
- Cross-filtering, drill-down and drill-through, containers, popup and tooltip pages.
- Per-widget CSV/XLSX export and PNG export. Server PDF export, and a print view with PPTX export.
- Schedules, subscriptions, run-now and delivery history.
- Share links, including a guest view at `/shared/:token`.
- Embed configs, including the host-embedded view at `/embed`.
- Workspace folder tree with roles and grants.
- AI suggest-widgets and auto-compose.
- Page copilot: chat that edits widgets.

**AI and insights**
- Ask AI: conversations, ask, run detail and export, feedback, connection row policies.
- Insights hub: dataset insights, narration, explain, goal-seek, outlier details.
- Suggest dashboards for a dataset, and for a role over a connection.

**Other**
- Notifications (list, mark read).
- Arabic/English UI with RTL.
- PWA manifest and service worker (production builds only).

### Partially built
- **Dataflows:** 8 backend routes (`routers/dataflows.py`) and `dataflowsApi` in `api.ts`. The scheduler refreshes them (`refresh_scheduler.py:818-835`). There is **no route, page or nav entry** in the frontend.
- **DirectQuery** is limited. Refused with "not yet supported":
  - calculated columns
  - measures
  - dataset-level filter expressions
  - crosstab / `dimension2`
  - running totals
  - sorting on a non-dimension column
  - some aggregations and filter operators
  - histogram and correlation pushdown on non-Postgres databases (`_STAT_DIALECTS = {"postgresql"}`, `direct_query.py:1029`)

  Two gaps that are not refused:
  - `plan_query` and `_build_where` ignore `dimension_granularity` / filter `granularity`. Pandas and DuckDB honour them. The runtime behaviour of date-bucketed DirectQuery widgets was not determined.
  - Column security on DirectQuery is the router string check only (§4).
- **Connectors whose drivers are not installed:** Snowflake, BigQuery, Databricks, Trino and ClickHouse name a `driver_module` that is absent from `requirements.txt`. The first four are import-only by design. ODBC also needs unixODBC plus a vendor driver, which the image does not install.
- **`.xls` upload** is registered as `pd.read_excel`, but `xlrd` is not in requirements. This was inferred from dependencies, not tested.
- **Email delivery:** `smtp_host = ""` by default. Schedules and alerts then record "SMTP is not configured" and send nothing; webhooks still work.
- **LLM features** depend on `llm_base_url = "http://10.125.18.189:8000/v1"` being reachable (§7).
- **Analysis catalogue:** 24 registered analyses, of which 6 have no handler: `full_profile`, `forecast_ets`, `forecast_simple`, `anomaly_iqr`, `anomaly_iforest`, `anomaly_ecod` (`services/analysis/registry.py`). `/analysis/run` answers them with "is listed but cannot be run through this endpoint yet" (`routers/analysis.py:607-611`). Their logic is reached through other endpoints.
- **Endpoints with an `api.ts` wrapper that no component calls (26):**
  - dataflows ×8
  - pins list/update/delete
  - demo seed/unseed
  - org theme create/delete
  - org-unit update
  - `auth/my-scope`
  - boundary-set delete
  - hierarchy node create
  - column-meta GET
  - column-formats GET
  - data-view delete
  - report classification GET
  - relationship delete
  - workspace node roles GET
  - column stats GET
- **Endpoints with no frontend code at all (12):**
  - the 8 `/datasets/{id}/statistics/*` routes (the same analyses run via `/analysis/run`)
  - `GET /datasets/{id}/export`
  - `GET /data-sources/{id}`
  - `GET /platform/organizations/tree`
  - `POST /data-sources/{id}/review/reset-inferred`

### Stubbed or dead
- **Pins:** `pinsApi.create` is called from `DatasetDetail.tsx` and `InsightsPane.tsx`, and the toast says "Pinned to your dashboard". Nothing lists or renders pins. A comment in `WidgetRenderer.tsx:855-858` says the section that showed them "is gone".
- **Automation runner** (`services/automation_runner.py`, about 80 KB): seven real steps, ticked every scheduler cycle. `create_run`, `approve_review` and `reject_review` are called **only from tests**; no router or UI creates a run. The queue is polled but never filled.
- **Demo seeder UI:** `demoApi` is imported nowhere. The backend routes remain live and are used by `scripts/demo_up.ps1`.
- **`ApiKey.last_used_at`** (`models.py:921`) is never written; the only `last_used_at =` writes are on `EmbedConfig` (`embed.py:313, 391`). `ApiKeys.tsx` shows "never used" for every key.
- **`WidgetDataResponse`** (`schemas.py:523`) is defined and never referenced.
- **`metadata_describe_concurrency`** (`config.py:143`): "# DEPRECATED: no longer read by stage_describe".
- **Stray files at the repo root**, none imported anywhere, all dated 2026-06-28:
  - `WidgetRenderer.tsx`, `ReportBuilder.tsx`, `WidgetConfigPanel.tsx`, `CrossFilterContext.tsx`, `analytics.py` and `widget_data.py` are old, smaller versions of files under `frontend/src` and `backend/app`.
  - `init.sql` is byte-identical to `postgres/init.sql`.
  - `TEST_PLAN.md` and `REPORT_TEMPLATE.md` are byte-identical copies of the `qa/` files, kept deliberately according to `CLAUDE.md`.
- **Feature flags off by default** (`core/config.py`, not overridden by compose): `eval_gate_enabled = False` (the nightly eval gate) and `otel_enabled = False`.
- **Off in the code defaults but switched on by `docker-compose.yml`**, so they are live in the standard deployment and are not dead:
  - `valkey_url = None` in code; compose sets it
  - `embedding_base_url/model/dim = None` in code; compose sets them
  - `super_admin_emails = ""` in code; compose sets `admin@datalytics.local,admin,admin@admin.com`
- **`frontend/scripts/bench_pageload.mjs:8`** hardcodes `createRequire('file:///D:/data_analytics/frontend/')`, a path that does not exist on this checkout.
- Zero `TODO`/`FIXME`/`XXX`/`HACK` markers. The `NotImplementedError` hits are an abstract base class (`cache_backend.py:51-57`) and one caught exception.

---

## 6. VISUALIZATIONS

### Widget types: 67
The canonical registry is `frontend/src/types/report.ts:3-15`:
```ts
export type WidgetType =
  | 'bar' | 'line' | 'pie' | 'donut' | 'scatter' | 'treemap' | 'step' | 'dot_plot' | 'needle'
  | 'histogram' | 'butterfly' | 'dual_axis_bar' | 'dual_axis_line' | 'dual_axis_bar_line' | 'dual_axis_time_series' | 'comparative_time_series' | 'numeric_series'
  | 'bubble' | 'bubble_change' | 'correlation_matrix' | 'heatmap' | 'parallel_coordinates' | 'box_plot' | 'waterfall' | 'gauge' | 'schedule' | 'vector_plot' | 'word_cloud'
  | 'kpi' | 'table' | 'crosstab' | 'list' | 'text' | 'button' | 'slicer'
  | 'area' | 'funnel' | 'ribbon' | 'card' | 'matrix' | 'image' | 'shape' | 'web_content' | 'custom_visual'
  | 'map_choropleth' | 'map_points' | 'map_bubbles' | 'map_lines' | 'map_clusters'
  | 'map_pie' | 'map_layers' | 'map_density' | 'map_network'
  | 'network'
  | 'container' | 'forecast' | 'sankey' | 'decomposition' | 'small_multiples'
  | 'script'
  | 'tree' | 'sunburst' | 'icicle' | 'dendrogram' | 'org' | 'circle_pack'
| 'custom_graph'
```
The same 67 types appear in four other places:
- `WIDGET_CATALOG`: label, category, icon and default size.
- `ROLE_SPECS: Record<WidgetType, RoleField[]>`, whose type makes it exhaustive.
- `roleAccepts()`: filters the column dropdowns by numeric, date or any type.
- The backend `REQUIRED_ROLES` (`services/widget_roles.py:29`), kept in parity with `ROLE_SPECS` by `tests/test_widget_roles.py`, which parses the TypeScript file.

**Every declared type has a renderer, and every renderer has a declared type.** The only fallback is the runtime `Unknown widget: ${wt}`.

### Dispatch
- `WidgetRenderer.tsx` handles `container` itself, rendering its child widgets as a group or as tabs.
- `WidgetBody.tsx` has inline branches for text, button, image, web_content, script, custom_visual, shape, slicer, kpi, card, table/crosstab/matrix and list.
- Everything else goes to the registry (`WidgetBody.tsx:462-480`):
  ```tsx
  const ChartRenderer = CHART_RENDERERS[wt]
  if (ChartRenderer) {
    return (
      <Suspense fallback={<EmptyState msg="Loading map…" />}>
        <MeasuredChart>
          {(plotW, plotH) => (
            <ChartRenderer rows={rows} data={data} cfg={cfg} rtl={rtl} broadcasts={broadcasts}
              localSelected={localSelected} onClickPoint={onClickPoint}
              measureFmt={measureFmt} measure2Fmt={measure2Fmt} allFormats={allFormats}
              ruleStyles={ruleStyles} geography={geography} plotW={plotW} plotH={plotH} />
          )}
        </MeasuredChart>
      </Suspense>
    )
  }
  return <EmptyState msg={`Unknown widget: ${wt}`} />
  ```
  `CHART_RENDERERS` (`components/report/chartRenderers/index.tsx:67`) has 52 entries. The maps, network, decomposition and small_multiples are loaded with `React.lazy`.

### Rendering library by type

| Library | Types |
|---|---|
| **Recharts** (27) | bar, line, area, pie, donut, scatter, treemap, step, dot_plot, needle, histogram, butterfly, dual_axis_bar, dual_axis_line, dual_axis_bar_line, dual_axis_time_series, comparative_time_series, numeric_series, bubble, bubble_change, waterfall, schedule (Gantt), funnel, sankey, forecast, custom_graph; gauge (the `arc` shape uses RadialBarChart, other shapes are hand-drawn SVG) |
| **d3-geo + topojson-client + world-atlas `countries-50m.json`**, SVG (9) | map_choropleth, map_points, map_bubbles, map_lines, map_clusters, map_pie, map_layers, map_density, map_network (`components/report/geo/worldGeometry.ts`, `MapFrame.tsx`) |
| **d3-cloud** (1) | word_cloud |
| **Hand-written SVG** (11) | box_plot, parallel_coordinates, vector_plot, ribbon, network, tree, sunburst, icicle, dendrogram, org, circle_pack |
| **HTML tables** (7) | correlation_matrix, heatmap, table, crosstab, matrix (virtualized `WindowedTable` with inline SVG sparklines), list, script |
| **HTML/CSS elements** (10) | decomposition, small_multiples, kpi, card, slicer, text, button, shape, container, image |
| **iframe** (2) | web_content; custom_visual (sandboxed iframe fed through `postMessage`) |

`reactflow` is not used by any widget; it renders only `components/review/JoinGraph.tsx`.

### How a chart's configuration is stored
- **Frontend type** (`types/report.ts:17-25`):
  ```ts
  export interface Widget {
    id: number
    page_id: number
    widget_type: WidgetType
    title: string
    config: Record<string, unknown>
    layout: { x: number; y: number; w: number; h: number }
    created_at: string
  }
  ```
  **There is no typed `WidgetConfig` interface.** Components read it as `const cfg = widget.config as any` (`WidgetBody.tsx:90`).
- **Backend storage:** the `report_widgets.config` JSON column (§3). `layout` is stored separately on a 12-column grid.
- **Config keys that hold column names**, stored as raw name strings (§3):
  - roles: `dimension`, `dimension2`, `measure`, `measure2`, `measures[]`, `size`, `color`, `group`, `target`, `start`, `end`, `animation`, `direction`, `lat`, `lon`, `lat2`, `lon2`
  - also: `filters[].column`, `sort_col`, `columns[]`, `levels[]`, `id_col`, `parent_col`, `label_col`, `facet_by`, `split_by`, `dimension_levels`, and `display_rules[].column`
- **Two config dialects coexist:**
  - Legacy top-level keys, read directly by `shape_series`.
  - A newer `roles` dict, which is authoritative when present (`resolve_roles`, `widget_data.py:2583-2599`). `ROLE_TO_CONFIG_KEY` maps `category → dimension`, `category2 → dimension2` and `measure → measure`.

### Chart features present
- **Cross-filtering:** `components/report/CrossFilterContext.tsx`. Per-widget `broadcasts`/`receives`, filter or highlight mode, per-pair actions, and page interaction modes `manual|linked|oneway|twoway`. The provider is mounted separately on each surface (builder, print, shared, embed, popups, tooltip pages).
- **Drill-down** (hierarchy path), expand-all levels, decomposition-tree drill, and drill-through to `drillthrough` pages.
- **Conditional formatting ("display rules"):** kinds `expression|value_map|interval|data_bar`, applied to mark, background or visibility. Evaluated on the server (`services/display_rules.py`). Report rules precede widget rules.
- **Themes:** six built-in palettes (`default, ocean, sunset, forest, mono, contrast`) plus org custom themes. App-level light/dark mode.
- **RTL:** English and Arabic (151 keys each). `DirectionContext` sets `dir`/`lang`, and each widget has an `rtl` flag. Many builder and widget strings are hardcoded English outside the `useT()` catalogue.
- **Export:** PNG per widget (`lib/widgetImage.ts`), CSV/XLSX per widget, server PDF (`GET /reports/{id}/pdf`), `window.print()`, and PPTX via pptxgenjs from the print view.

---

## 7. AI / AGENT LAYER

### Client (`backend/app/services/llm.py`, `core/config.py:81-95`)
- It speaks the OpenAI-compatible `/v1/chat/completions` API to a **self-hosted vLLM** serving **Qwen**, using raw `httpx` with no auth header. Settings (re-read):
  ```python
  llm_base_url: str = "http://10.125.18.189:8000/v1"
  llm_model: str = "qwen3.5"
  llm_timeout_s: float = Field(default=180.0, gt=0)
  llm_enabled: bool = True
  llm_max_concurrency: int = Field(default=12, ge=1)
  llm_reserved_interactive: int = Field(default=2, ge=0)
  ```
- Every request payload includes `"chat_template_kwargs": {"enable_thinking": False}`, which is Qwen-specific (`llm.py:134-136`).
- `complete_json(..., enforce=True)` sends `response_format={"type": "json_schema", ...}`. It then runs a shallow parse and check: required keys and top-level types.
  - A reply that fails the check is retried up to 2 times, with the error fed back to the model.
  - Every failure path returns `None`; none raises.
- Two semaphores keep 2 slots reserved for interactive calls.
- A startup probe makes one enforced call and only logs `ERROR` if it fails.

### Every LLM call site

| Call site | Purpose | Emits | Validator |
|---|---|---|---|
| `main.py:401` `_probe_llm_contract` | startup check | JSON `{n, note?}` | key-set check; logs only |
| `agent/nodes/followup.py:181` | classify a follow-up message, rewrite it as a standalone question | JSON `{kind, question, format, limit, x, y}` | schema plus code coercion; axes re-checked by `charts.validated_axes` |
| `agent/nodes/classify.py:203` | intent and ambiguity | JSON `{intent, ambiguous, ambiguity_reason}` | schema/enum only (the docstring says the eval gate polices quality) |
| `agent/nodes/clarify.py:8` | one clarifying question | prose | none; has a fallback string |
| `agent/nodes/converse.py:54` | small talk | prose | none; the prompt forbids figures |
| `agent/nodes/analyze.py:120` | pick columns for compare_groups / explain_response | JSON enum picks | enum in schema, re-checked in code |
| `agent/plan.py:40` | split the question into a DAG of 1–6 steps | JSON `{steps:[{id, question, depends_on}]}` | `topological_layers` (cycles or unknown dependencies fall back to one step) |
| `agent/nodes/generate.py:105` | **write SQL** per step | JSON `{sql}` | validation ladder V1/V6/V2/V3 → V4 policy → V5 EXPLAIN/execute; up to 3 attempts |
| `agent/nodes/explain.py:137` / `:109` | final answer / "explain this chart" | prose | **none on content** (no numeric guard found); deterministic fallback when None |
| `agent/nodes/copilot.py:223` | page copilot | JSON `{reply, data_question, actions[]}` (widget create/update/delete/add_calculated_column) | schema, then per-action checks in `routers/report_copilot.py` |
| `services/suggest_dashboard.py:301`, `:443` | dashboard(s) for a role over a connection | JSON `{title, **sql**, widgets[]}` | **regex** (`_SELECT_ONLY`, `_FORBIDDEN`, `_TABLE_REF`) + sqlglot qualified-column check (unparseable SQL passes) + execute probe |
| `suggest_dashboard.py:398` | extract a stated persona | JSON `{persona}` | schema |
| `services/suggest_dataset_dashboard.py:640` | dashboards for a dataset and a goal | JSON `{proposals:[{title, rationale, widgets:[{widget_type, title, why, config}]}]}` (**widget configs**, open object) | `validate_widget` (required roles, real columns, no arithmetic on IDs, no personal column as a dimension) → `polish_widget` → render probe on the RLS-filtered frame |
| `suggest_dataset_dashboard.py:772` | one clarifying question | prose | truncated to 200 characters |
| `services/widget_review.py:174` | tune limit/sort/granularity on proposed widgets | JSON attributes | bounds and enum checks; on failure, widgets are returned unchanged |
| `services/insights.py:509`, `:549` | narrate findings | prose | **digit guard**: the digit runs in the output must be a subset of those in the facts; 8 s timeout; 120 s breaker |
| `services/metadata/infer_semantic.py:378, 581, 633, 763` | column/table descriptions, enum labels, source overview, entities | JSON (**not** schema-enforced) | keep only the keys that were asked for; gated by `DataSource.allow_llm_sampling` (default False) |

The model never emits component code. Its outputs are SQL, JSON widget configs and edit actions, and prose.

`mcp_server/` makes no LLM calls. It is an outbound MCP stdio server with 9 HTTP-proxy tools.

### Agent graph (`services/agent/graph.py`, hand-rolled)
- There is no LangGraph. `dag.py:3-5` says: "*Deliberately ~80 lines and owned, not LangGraph…*".
- The flow, per `graph.py:1-2`: "classify -> (clarify) -> context -> plan -> DAG of [generate -> ladder -> policy -> execute -> sanity] -> explain".
- Two modes, **source** (customer DB) and **datasets** (uploaded files). Besides SQL, runs can branch to:
  - follow-up handling (chat, describe, presentation, chart from scratch)
  - a word-match dashboard refusal in dataset mode
  - suggest-dashboards in source mode
  - catalog overview
  - statistical analysis intents
- The per-step repair loop (`graph.py:437-506`), abridged:
  ```python
  for attempt in range(MAX_ATTEMPTS):
      sql = await generate_sql(step_question_text, context, examples, client, feedback=feedback, history=history)
      if sql is None: failures.append({"rung": "generate", ...}); break
      failure = validate_sql(sql, context)
      if failure is not None:
          ...; feedback = f"{failure.rung}: {failure.detail}"; continue
      if dataset_mode:
          rows, error = await execute_on_datasets(final_sql, frames, ...)
      else:
          try: final_sql = apply_policies(sql, policies, context.family)
          except PolicyError as exc:
              failures.append({"rung": "V4", "detail": str(exc)}); break
          rows, error = await execute_sql(final_sql, cfg, context.family, ...)
  ```

### SQL validation ladder (`services/agent/validate.py`, `policy.py`, `executor.py`; sqlglot AST)
- **V1:** the statement must parse, must be `SELECT` or `UNION`, and must read at least one table.
- **V6** (column security, runs before V2):
  ```python
  if context.denied_columns:
      denied_all = {str(name).casefold() for cols in context.denied_columns.values() for name in cols}
      for col in tree.find_all(exp.Column):
          if col.name and col.name.casefold() in denied_all:
              return ValidationFailure("V6", f"column '{col.name}' is blocked by a column-security rule for this user. ...")
  ```
- **V2:** every table and column must exist in the catalog; CTE scope is respected.
- **V3:** every JOIN needs an ON clause, and join pairs must be confirmed or declared relationships.
- **V4** (source mode only): `ObjectRowPolicy` predicates are ANDed into the WHERE of each SELECT that owns the table. If a predicate cannot be attached, the query is refused. Org admins bypass this.
- **V5:**
  - Source mode applies a statement timeout (30 s), caps rows at 5,000, runs `EXPLAIN` and then executes on the customer DB.
  - Dataset mode registers the RLS-filtered, column-dropped pandas frames in an in-memory DuckDB (`enable_external_access=false`), with a watchdog interrupt.

**Security coverage of LLM SQL:**
- **Dataset mode:** `RowSecurityRule` RLS and column drops are applied to the frames *before* DuckDB sees them.
- **Source mode:** only `ObjectRowPolicy` (V4) applies. Dataset-level `RowSecurityRule`s are **not** applied. Denied columns are removed from the prompt and enforced by V6.
- **`suggest_dashboard` (both entry points) does not use this ladder.** Its model SQL is regex-checked (re-read, `suggest_dashboard.py:44-52`):
  ```python
  _SELECT_ONLY = re.compile(r"^\s*select\b", re.IGNORECASE)
  _FORBIDDEN = re.compile(
      r"\b(insert|update|delete|drop|alter|create|truncate|replace|attach|pragma|grant)\b",
      re.IGNORECASE)
  ```
  It is then executed through `connections.preview_table`: `df = pd.read_sql(sql, engine); df = df.head(limit)` (`connections.py:118-119`). That is the full query, with the rows cut afterwards.
  - There is no statement timeout or injected LIMIT.
  - `suggest_dashboard.py` has zero references to `denied`, `rls` or `polic`.

### Report copilot
- **Schema** (`COPILOT_SCHEMA`, `copilot.py:21-82`):
  - `op ∈ {create, update, delete, add_calculated_column}`
  - `config` as an array of at most 16 `{key, value}` pairs, because strict schemas reject open objects
  - `layout {x, y, w, h}`
  - at most 8 actions
- **Router checks** (`report_copilot.py:146-356`):
  - `edit` capability and agent quota
  - create/convert only to `CREATABLE_TYPES` (25 types)
  - widget IDs must belong to the page
  - `_clean_config` drops `dataset_id` and checks `dimension/dimension2/measure/measure2` against real and calculated columns; an unknown column skips the action
  - layout clamped to the 12-column grid
  - `add_calculated_column` is refused on DirectQuery, below `data` capability, on a name clash, or when `_validate_expr_safety` fails
  - `data_question` is delegated to `run_agent`
  - if the model returns None, the route returns HTTP 502

### Embeddings and retrieval
- `embedding_server/` is an ONNX Runtime MiniLM service with an OpenAI-shaped `POST /v1/embeddings`. Weights are baked into the image.
- `services/retrieval.py` ranks catalog objects for the prompt:
  - Backend A: lexical TF-IDF, always on.
  - Backend B: the embeddings service, with a 3 s timeout and a 300 s circuit breaker that falls back to A.
  - Vectors are persisted in `retrieval_embeddings`.

### Evals
- `backend/evals/` contains:
  - golden sets `fixture.jsonl` (10 questions) and `maps.jsonl` (25), each with `{question, sql, intent}`
  - `run_gate.py`, which asks the live agent each question and compares **result rows** (order-, alias- and type-tolerant) between the golden and generated SQL
- It is run manually with `backend/run_eval_gate.ps1`, taking about 20 minutes. An in-process nightly option exists but is off (`eval_gate_enabled=False`).

### When the LLM is unreachable
- **Hard failure:**
  - `classify` failing fails the run: "the model endpoint could not classify the question".
  - The copilot returns 502.
  - `generate_sql` failing fails the step.
- **Deterministic fallback:** explain, clarify and converse, narration (template text kept), the widget review (widgets unchanged), and metadata description (sync completes without descriptions).
- **Dataset suggestions:** automation falls back to `suggest_from_insights`, which uses no model.

---

## 8. PERSISTENCE FORMAT

### How a dashboard is saved
- **Normalized rows plus JSON columns:**
  - one `reports` row
  - N `report_pages` rows, ordered by `position`
  - M `report_widgets` rows per page
- **Widgets are separate rows, not embedded JSON.**
- **There is no explicit save.** Each edit is a REST mutation that commits immediately (`models.py:161-164`: "*Every edit here persists immediately with no explicit save*"). Every mutation goes through `_bump_revision` (`routers/reports.py:92-111`), which checks `edit` capability, snapshots the prior state and increments `revision`.
- **JSON columns:**
  - `reports.additional_dataset_ids`, `reports.display_rules`
  - `report_pages.mobile_layout`
  - `report_widgets.config` (bindings, aggregation, sort, limit, widget filters, formatting, interactions, `container_id`, per-widget `dataset_id` override)
  - `report_widgets.layout` (`{x, y, w, h}` on a 12-column grid)
- **Filters live in several places:**
  - widget-level: `config.filters`
  - report-level: `common_filters` rows
  - `report_parameters` rows
  - dataset-level: `datasets.default_filter_expr`
  - security: `row_security_rules`, `column_security_rules`
  - bookmarks: `bookmarks.state` JSON
- **Containers:** a child widget stores `config.container_id` pointing at the container widget's ID.

**Versions** (`report_versions.snapshot`, 50 kept; `routers/reports.py:153-170`):
```python
by_page: dict[int, list[dict]] = {}
for w in widget_rows:
    by_page.setdefault(w["page_id"], []).append(
        {"widget_type": w["widget_type"], "title": w["title"],
         "config": w["config"], "layout": w["layout"]})
snapshot = {
    "report": {"theme": rep.theme, "display_rules": rep.display_rules},
    "pages": [{
        "name": p["name"], "title": p["title"], "page_type": p["page_type"],
        "prompt_column": p["prompt_column"], "prompt_label": p["prompt_label"],
        "position": p["position"], "page_size": p["page_size"],
        "custom_width": p["custom_width"], "custom_height": p["custom_height"],
        "mobile_layout": p["mobile_layout"],
        "layout_mode": p.get("layout_mode"),
        "layout_template": p.get("layout_template"),
        "widgets": by_page.get(p["id"], []),
    } for p in page_rows],
}
```
- `background_url` is not in the snapshot.
- Restore recreates pages and widgets with **new IDs**. Anything keyed by widget ID therefore goes stale: `report_translations.payload` (`"w<id>"`) and `pinned_tiles.widget_id`.
- `share_links.snapshot` optionally freezes the whole report layout when the link is pinned.

### A real stored example
No fixture or test holds a full serialized multi-widget report document; `qa/` contains only Markdown, CSVs and `seed.ps1`. The closest real source is the demo seeder, which writes rows directly.

The seeder spec (`backend/app/services/demo_content.py:866-887`, re-read verbatim):
```python
def _projects_feedback_specs(datasets: dict[str, Dataset]) -> list[tuple[str, str, int, int, dict]]:
    """The one demo report drawing on two datasets: projects for the Gantt, feedback
    for the word cloud, which carries a per-widget `dataset_id` override."""
    return [
        ("schedule", "Project schedule by phase", 7, 6,
         {"dimension": "task", "start": "start_date", "end": "end_date",
          "group": "phase", "limit": 40}),
        ("word_cloud", "What customers talk about", 5, 6,
         {"dataset_id": datasets["feedback"].id, "dimension": "topic",
          "aggregation": "count", "limit": 50, "sort": "desc", "sort_by": "value"}),
    ]
```
(The two comment blocks inside the list are omitted here.)

Each spec is written as rows by `demo_content.py:1010-1043`:
```python
report = Report(name=DEMO_REPORT_NAMES[report_key], description=..., dataset_id=dataset.id,
                additional_dataset_ids=[datasets[k].id for k in extra_keys], org_id=org_id)
page = ReportPage(report_id=report.id, name="Page 1", title=DEMO_REPORT_NAMES[report_key], position=0)
packer = _GridPacker()
for widget_type, title, w, h, config in build_specs(datasets):
    db.add(ReportWidget(page_id=page.id, widget_type=widget_type, title=title,
                        config={**config, DEMO_META_KEY: DEMO_MARKER},
                        layout=packer.place(w, h)))
```
The quote above is condensed from the source's line breaks; the calls and arguments are unchanged.

**The resulting stored rows.** These are derived from that code, not read from a live database.

| Table | Stored values |
|---|---|
| `reports` | `name="Demo — Projects & Feedback"`, `dataset_id=<projects id>`, `additional_dataset_ids=[<feedback id>]`, `theme="default"`, `display_rules=[]`, `revision=0` |
| `report_pages` | `name="Page 1"`, `title="Demo — Projects & Feedback"`, `position=0`, `page_type="normal"`, `page_size="16:9"` |
| `report_widgets` row 1 | `widget_type="schedule"`, `title="Project schedule by phase"`, `config={"dimension":"task","start":"start_date","end":"end_date","group":"phase","limit":40,"__demo__":"__demo__"}`, `layout={"x":0,"y":0,"w":7,"h":6}` |
| `report_widgets` row 2 | `widget_type="word_cloud"`, `title="What customers talk about"`, `config={"dataset_id":<feedback id>,"dimension":"topic","aggregation":"count","limit":50,"sort":"desc","sort_by":"value","__demo__":"__demo__"}`, `layout={"x":7,"y":0,"w":5,"h":6}` |

More config shapes from the `sales_overview` demo (`demo_content.py:564-626`), showing both config dialects:
```python
("kpi", "Total revenue", 3, 3, {"measure": "revenue", "aggregation": "sum"}),
("card", "Revenue, cost and units", 3, 5,
 {"measures": ["revenue", "cost", "units"],
  "roles": {"measures": ["revenue", "cost", "units"]},
  "aggregation": "sum"}),
("line", "Monthly revenue", 6, 5,
 {"dimension": "date", "dimension_granularity": "month", "measure": "revenue",
  "aggregation": "sum", "limit": 24, "sort": "asc", "sort_by": "name"}),
("table", "Largest transactions", 6, 6,
 {"columns": ["date", "region", "product", "channel", "revenue", "units", "margin_pct"],
  "limit": 100, "sort_col": "revenue", "sort": "desc"}),
```

The API/GET shape as used in a test fixture (`backend/tests/test_report_copilot.py:29-35`):
```python
PAGE_CTX = {
    "report_name": "Sales", "page_name": "Overview",
    "widgets": [{"id": 41, "widget_type": "bar", "title": "Revenue by region",
                 "config": {"dimension": "region", "measure": "revenue", "agg": "sum"},
                 "layout": {"x": 0, "y": 0, "w": 6, "h": 5}}],
    "columns": {"demo_sales": {"region": "text", "revenue": "numeric"}},
}
```

---

## 9. GAPS AND ROUGH EDGES

### Known-broken or incomplete paths, from code
- **DirectQuery column security** is the router check on top-level string config values only. `direct_query.py` never references denied columns, and its row fetches use `SELECT *` (§4).
- **The PDF export and xlsx digest paths skip column denial.** `reports._resolve_report_sections` and `delivery.build_digest` pass RLS but no `drop_columns`. `build_digest` also passes `default_filter_expr` and calculated columns without `expand_author_expressions`.
- **Embed identity:** `routers/embed.py` resolves RLS as the config's creator. The token's `viewer_email`/`viewer_org` reach only `expand_author_expressions`, not `resolve_rls_expr`.
- **`suggest_dashboard` SQL:** model-written SQL is checked by regex and run with `pd.read_sql` with no LIMIT, no timeout and no RLS/column/policy filtering (§7).
- **Ask AI source mode** does not apply dataset `RowSecurityRule`s, only `ObjectRowPolicy` (§7).
- **Calculated-column failures are silent.** `apply_calculated_columns` (`services/widget_data.py:~3107-3118`) wraps each column in `try: … except Exception: pass`, so a failing expression leaves the column absent with no error.
- **DirectQuery ignores granularity.** `plan_query` and `_build_where` ignore `dimension_granularity` and filter `granularity`; pandas and DuckDB honour them. The runtime result was not determined.
- **The DuckDB plan ignores `f["granularity"]` on `eq` filters.** Whether this errors (and falls back to pandas) or returns different rows was not determined.
- **Middleware order:** the "keep CORS headers on 500" middleware is registered last, which in Starlette makes it outermost, the opposite of what its docstring states (§2).
- **The schema is maintained three ways:** Alembic ("not yet load-bearing", `main.py:238-241`), `create_all`, and 77 raw statements in `_migrate`. `_run_alembic` logs and swallows any failure: "*alembic startup migration failed; continuing startup unmigrated*".
- **`postgres/init.sql`** is still mounted as the Postgres init script, so it **runs on a fresh database volume**. It is a stale bootstrap: 8 legacy tables without their later columns, and a `charts` table that has no ORM model. Alembic, `create_all` and `_migrate` then run on top of it. `_run_alembic` handles the resulting duplicate-object errors by stamping head.
- **`docker-compose2.yml`'s frontend** has no build target, so it builds the nginx stage (port 80) while publishing container port 3000.
- **`backend/alembic.ini`** says the URL is built in `app/alembic/env.py`; the file is actually `backend/alembic/env.py`.

### Recorded test and QA state (repo claims)
- `backend/.pytest_final.txt` (2026-09-08) ends `6 failed, 3179 passed, 4 skipped in 1136.62s`, then `EXIT=0`.
  - It lists only 4 `FAILED` lines, all in `test_architecture_doc.py`, where doc counts drifted from the code.
  - Both result files predate later edits (ARCHITECTURE.md was modified on 2026-09-21), so the current pass/fail state is not known from the repo.
- `backend/.pytest_out.txt` records a different run: `3061 passed, 4 skipped, 44694 warnings`, followed by OpenTelemetry `ValueError: I/O operation on closed file` tracebacks.
- `qa/REPORT.md` (2026-09-21), a browser run:
  - 129 cases: 112 passed and 9 failed on the first pass; 121 passed and 0 failed after fixes; 8 blocked.
  - The mobile viewport cases MOB-01..04 could not be run.
- `qa/FIX_REPORT_2.md:155-200` records that:
  - `tsc --noEmit` shows "four pre-existing errors" (in `CopilotChat.test.tsx`, `geo/MapFrame.tsx` and `geo/worldGeometry.ts` ×2)
  - `WidgetRenderer.test.tsx` has "the same 4 map cross-filter failures" and `SharedReport.test.tsx` "the same 3 failures"
  - "A full vitest run of the whole suite could not be completed here"
  - "There are no width media queries in the stylesheet at all"
- `TEST_PLAN.md:141`: "*known regression: missing on dashboard Data tab vs dataset Data tab*".
- `ARCHITECTURE.md:141-143`: "*Cloud warehouses (Snowflake, BigQuery, Databricks, Trino) are **discoverable but import-only***".
- `PROJECT_AUDIT.md` (2026-09-14) is out of date against the tree. For example, it states 29 Alembic revisions where 35 exist.

### Hardcoded values
- **Secrets:**
  - `core/config.py:6` `database_url = "postgresql+asyncpg://datalytics:datalytics_secret@localhost:5433/datalytics"`
  - `:7` `secret_key = "change_me_in_production"`, the same compose default. A grep of the live `.env` for that literal string matched once; no other `.env` values were read.
  - `connector_secret_key = ""` derives the connector-encryption key from `secret_key`
  - `connector_allow_private_hosts = True`
- **Emails:** compose `SUPER_ADMIN_EMAILS` default is `admin@datalytics.local,admin,admin@admin.com`, which includes a bare `admin`. The seed scripts hardcode `demo-password`.
- **URLs:**
  - `llm_base_url = "http://10.125.18.189:8000/v1"` (a private LAN IP) and `llm_model = "qwen3.5"`
  - `public_base_url = "http://localhost:3000"`
  - `DEMO_EMBED_ORIGINS` hold localhost URLs
  - the MCP server defaults to `http://localhost:8000/api/v1`
  - `frontend/scripts/bench_pageload.mjs:8` uses the absolute path `file:///D:/data_analytics/frontend/`
- **The embedding model name** appears in 4 places: compose, `embedding_server/Dockerfile`, `server.py` and `download_model.py`.
- **Row caps and limits:**
  - configurable: `import_row_cap = 2_000_000`, `analysis_row_cap = 250_000`, `agent_row_cap = 5000`
  - module constants: `direct_query.DEFAULT_ROW_CAP = 10_000`, `prep.MATERIALIZE_MAX_ROWS = 2_000_000`, `query_builder.MAX_LIMIT = 100_000`, `agent/results.RESULT_ROW_CAP = 200`, `script_tile.MAX_INPUT_ROWS = 200_000` / `MAX_OUTPUT_ROWS = 5_000`, `pdf_export.PDF_MAX_TABLE_ROWS = 5_000`, `widget_data.HIER_MAX_NODES = 2_000`
  - frontend: `QueryBuilderDialog.tsx:63,195` default `10000`
- **Stale comments:**
  - `config.py:235-236` says "No Valkey/Redis in this stack", but compose runs Valkey.
  - `backend/conftest.py:21` says "~2450 tests"; the last recorded run collected about 3,189.

### The same logic in more than one file
- **Structured filters (`{column, op, value}`)** are implemented three times, with differing operator and granularity support: pandas `_apply_filters` (`widget_data.py:316`), `direct_query._build_where` (`:235`) and `duck_agg.plan()`.
- **Aggregation-name → function maps** exist five times: `widget_data._agg_series`/`_pandas_agg_fn`, `direct_query._SQL_AGG_FN`, `duck_agg._SQL_AGG`, `query_builder._AGGS` and `aggregates.compile_aggregate_sql`.
- **Date bucketing:**
  - `widget_data._dimension_granularity_label`/`_bucket_dimension` (pandas)
  - `duck_agg._GRANULARITY_SQL`, written to match the pandas labels
  - the `DATETRUNC` calculated-column function (`widget_data.py:2896-2903`)
  - `analysis/forecast_scenario.py:84-88`
  - ad-hoc `to_period("M")` in `analytics.py` and `insights.py`
  - DirectQuery has none
- **RLS application:** three mechanisms (pandas `apply_rls_filter`, `sql_expr` translation, agent sqlglot injection) over two policy models. `apply_rls_filter(` has 25 call sites, each repeating the load → RLS → drop-denied sequence by hand, for example `routers/datasets.py` ×10 and `routers/analysis.py` ×3.
- **Widget resolution** happens in three places: `_resolve_widget_data`, `reports._resolve_report_sections` and `delivery.build_digest`, and they differ from each other.
- **Identifier quoting** is done five ways: `direct_query._quote` (`f'"{identifier}"'`, no escaping; relies on column allowlisting), `duck_agg._quote_ident` (doubles quotes), `query_builder._quote(dialect, …)`, `aggregates._ident` and `metadata/cache.py _quote`.
- **Column-type inference:** `ingest.detect_types`, `dataset_profile._detect_role`, `metadata/introspect.normalize_type`, `metadata/infer_semantic.classify_semantic_type` and `pii.detect_semantic_type`. On the frontend: `lib/autoChart.isDate`, `ReportBuilder.isNumericRole`/`isNumericField` and `chat/ResultView.isNumberish`.
- **K/M/B number formatting:** frontend `chartUtils.tsx`, `insights/MiniBarChart.tsx`, `lib/fieldHints.ts` and `OutlierDetailsDialog.tsx`; backend `insights._fmt` and `pdf_export._fmt`.
- **Widget roles:** backend `REQUIRED_ROLES` duplicates frontend `ROLE_SPECS`. This is deliberate and pinned by a parity test.
- **Result caches:** import and DirectQuery share storage but build their keys separately. The frontend adds a third, per-tab cache.
- **Display-rule evaluation** runs in `get_widget_data_from_df` and again in `_run_direct_query_inner`.
- **Stray root copies** of 7 source files and 2 QA documents (§5).

### Marker counts
Scope: `backend/app`, `mcp_server`, `embedding_server` and `frontend/src`.
- `TODO` 0, `FIXME` 0, `XXX` 0, `HACK` 0
- `NotImplementedError` 4 (abstract base plus one catch)
- `not yet` 45, mostly DirectQuery refusals
- `for now` 3

---

## 10. SIZE

### Line counts
The counts come from `find` + `wc -l` over working-tree files, excluding `__pycache__` and `node_modules`.

**Backend**

| Directory | Files | Lines |
|---|---|---|
| `backend/app` (all `.py`, production) | 161 | 56,926 |
| ├ `routers/` | 26 | 13,125 |
| ├ `services/` (incl. `agent/`, `analysis/`, `metadata/`) | 117 | 38,134 |
| ├ `models/` | 2 | 2,136 |
| ├ `schemas/` | 2 | 904 |
| ├ `core/` | 11 | 1,828 |
| └ `main.py`, `dependencies.py` | 2 | 798 |
| `backend/tests` | 362 (360 `test_*.py`) | 70,693 |
| `backend/alembic` | 36 (35 revisions) | 3,012 |
| `backend/scripts`, `evals`, `mcp_server` | 11 / 4 / 3 | 1,692 / 439 / 275 |
| `embedding_server` | 4 | 370 |

The largest backend files are `services/widget_data.py` (about 172 KB, 3,657 lines), `routers/datasets.py` (3,279 lines), `routers/reports.py` (1,981 lines), `services/demo_content.py` (about 111 KB) and `services/automation_runner.py` (about 80 KB).

**Frontend** (`.ts` and `.tsx`)

| Directory | Production files / lines | Test files / lines |
|---|---|---|
| `frontend/src/components` | 162 / 27,438 | 123 / 22,460 |
| `frontend/src/pages` | 41 / 12,054 | 31 / 8,876 |
| `frontend/src/lib` | 16 / 1,499 | 14 / 1,295 |
| `frontend/src/services` (`api.ts`) | 1 / 2,312 | 1 / 102 |
| `frontend/src/types` (`report.ts`) | 1 / 610 | 0 |
| contexts, hooks, i18n, test, `App.tsx`, `main.tsx` | 10 / 971 | 8 / 465 (includes `src/pwa.test.ts` and `src/offlineAssets.test.ts`) |
| `index.css` + `styles/` | 1,536 + 605 (CSS) | — |

The largest frontend files are `pages/ReportBuilder.tsx` (about 166 KB, 2,940 lines), `components/report/WidgetConfigPanel.tsx` (about 151 KB, 2,416 lines), `pages/DatasetDetail.tsx` (about 79 KB) and `components/report/WidgetRenderer.tsx` (1,034 lines).

### Counts

| Item | Count | How it was counted |
|---|---|---|
| HTTP endpoints | **287** (GET 102, POST 105, DELETE 41, PUT 22, PATCH 17) | Grep for route decorators, cross-checked against FastAPI `app.routes` (APIRoute); excludes the 4 docs/openapi routes |
| Endpoints per router | reports 60, datasets 57, admin 28, analysis 16, data_sources 16, metadata 15, agent 12, sso 9, workspace 9, dataflows 8, auth 6, embed 6, platform 6, hierarchy 5, boundary_sets 4, custom_connectors 4, pins 4, prediction_models 4, main 3, relationships 3, widget_templates 3, demo 2, notifications 2, shared 2, widget_data 2, report_copilot 1 | |
| Endpoints with no UI caller | 38 (26 with a wrapper only, 12 with no frontend code) | |
| ORM models / tables | 79 | |
| Alembic revisions | 35 | |
| React component files (`.tsx`, non-test) | **187** | plus 44 non-test `.ts` modules |
| Page components | 41 production files under `pages/` (16 top-level routes, 12 admin, 3 monitoring) | |
| Widget types | 67 | 52 in `CHART_RENDERERS`, 15 inline |
| `api.ts` exported `*Api` objects | 67 | 268 `api.<method>(` calls |
| Connector types | 45 | `services/connectors.py` `_ALL_SPECS` |
| Backend test functions | **4,568** line-anchored `def test_` / `async def test_` definitions in 360 files | See the note below the table |
| Frontend test cases | **2,382** line-anchored `it(`/`test(` calls in 177 files (138 `.test.tsx`, 39 `.test.ts`) | |
| Agent eval golden questions | 35 (10 + 25) | |

**Unexplained gap in the backend test count.** The source has 4,568 definitions, but the last recorded run (`backend/.pytest_final.txt`, 2026-09-08) collected 6 + 3,179 + 4 = 3,189 tests. Expanding parametrized tests would make the collected number larger, not smaller, so parametrization does not explain it. The repo does not show which of these causes apply:
- The recorded run was narrowed.
- Tests were added after 2026-09-08.
- Some `test_*` functions are helpers or are nested in a way pytest does not collect.

### Test coverage
**Not measurable from the repo:**
- `pytest-cov`/`coverage` is not in `requirements.txt` or the venv.
- No `@vitest/coverage-*` package is installed.
- There is no `.coveragerc` and no coverage block in `vitest.config.ts`.
- No stored `coverage.xml`, `htmlcov`, `lcov.info` or `.coverage` exists.

The backend suite runs on in-memory SQLite, and Postgres-specific tests skip without a live database.
