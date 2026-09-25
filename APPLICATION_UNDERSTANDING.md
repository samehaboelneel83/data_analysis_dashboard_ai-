# Application Understanding

Source-based assessment, 24 September 2026. This document describes the working tree inspected, not a running production installation.

**Reading convention:** paths prefixed by `backend/`, `frontend/`, `embedding_server/`, `clients/`, `postgres/`, or `scripts/` are relative to **`AI_data_tool/data_analytics/`** unless stated otherwise. Linked inventory entries use repository-root-relative paths. Code and registrations take precedence over README descriptions and historical design plans. **Needs Verification** means the available source does not establish the stated deployment fact or end-to-end behavior.

This was a static, read-only analysis until creation of this document. No application code, database, dependencies, configuration, or running services were changed. Tests were inspected, not executed; historical test outputs are not evidence of current passing status. Actual credentials and environment values are deliberately omitted.

The scope covers the active Datalytics application and the purpose/boundaries of the other root projects. Third-party checkouts, generated assets, archived worktrees, screenshots, and copied implementations are not treated as active Datalytics modules. Their internals are not exhaustively audited.

## 1. Executive Summary

Datalytics is a self-hosted business intelligence and data analysis application. Users bring in files or connect data sources, inspect and prepare datasets, build interactive dashboards, ask natural-language questions, run statistical analyses, and share or export results. It aims to put data preparation, report authoring, analytical assistance, and access control in one application.

Expected users are inferred from implemented roles and screens: dataset/report authors, dashboard viewers, analysts using statistical tools or notebooks, organization administrators, and platform administrators. These are usage personas, not a fixed set of database role names: roles are organization-scoped records and users belong to one role.

Technically, it is a React/TypeScript single-page application backed by a Python FastAPI modular monolith. PostgreSQL holds application metadata and governance records. Imported data is kept in server-side files with Parquet sidecars; pandas and DuckDB perform analysis. DirectQuery translates supported widget requests into SQL against external databases. AI uses a configurable OpenAI-compatible model endpoint, a native SQL validation/orchestration pipeline, and optional local embeddings. Datalytics does not invoke the adjacent WrenAI or Superset checkout in its active query path.

The source is a substantial, actively evolved implementation, not merely a mockup: it has persistent multi-user models, migrations, source connectors, report history, API routes, a large test suite, and deployment scripts. It also has large central modules, legacy schema compatibility code, incomplete UI exposure for some backend capabilities, and security-sensitive execution features. A production-readiness certification cannot be inferred from repository size, comments, or past QA reports.

Verified inventory: **81 ORM models/tables, 303 application-router HTTP operations, 37 Alembic revisions, 382 backend test modules, and 211 frontend test files**. There are also three application health endpoints and separate prototype/embedding endpoints. These are static file/registration counts, not executed test counts.

Evidence: `backend/app/main.py`, `models/models.py`, `routers/`, `frontend/src/App.tsx`, package manifests and Compose.

## 2. Repository Structure

~~~text
repository root/
  APPLICATION_UNDERSTANDING.md
  README.md, MASTER_PLAN.md, WORKFLOW.md, *_TEST.md, comparisons/audits
  prompt.py, chat.html, index.html, requirements.txt
  maps_project/                  Wren semantic-model project for a source database
  WrenAI/                        independent upstream semantic-engine checkout
  superset_ref/superset/          upstream reference checkout
  SAS/, sas_new_data/             SAS reverse-engineering/specification material
  info1/, screenshots/            diagrams and captured UI evidence
  AI_data_tool/
    drivers.py                   standalone driver abstraction/prototype
    ARCHITECTURE*.md, README.md   design/context
    data_analytics/
      backend/
        app/
          main.py                FastAPI composition and lifecycle
          core/                  settings, DB, auth, capabilities, RLS, telemetry
          models/models.py       ORM definition of application metadata
          schemas/schemas.py     shared Pydantic HTTP contracts
          routers/               HTTP orchestration and some business rules
          services/              querying, prep, analysis, AI, delivery
        alembic/versions/        schema migrations
        tests/, evals/           automated tests and AI evaluation harness
        mcp_server/              optional stdio MCP facade over REST
        uploads/                 local development/runtime data artifacts
        boundary_packs/          shipped geographic boundary packs
      frontend/
        src/pages/               routed screens and screen-specific helpers
        src/components/          report studio, charts, forms, dialogs, chat
        src/contexts/, hooks/    shared state and hooks
        src/services/api.ts      REST types and API wrappers
        src/lib/                 formatting, layout and expression utilities
        src/types/report.ts      report/widget/client type vocabulary
        src/i18n/, styles/, assets/
        public/                  installability manifest and service worker
      embedding_server/          separate ONNX embedding HTTP process
      clients/python/            notebook client for semantic API
      postgres/init.sql          historical bootstrap schema
      scripts/                   seed, demo, backup, restore, offline bundle
      docs/, qa/                 plans, walkthroughs, manual QA records
      docker-compose.yml         active development + production-web profile
      docker-compose2.yml        alternative historical configuration
      .env.example               partial environment example
      *.py, *.tsx, init.sql      duplicate/older top-level implementation copies
~~~

The backend entry point is `backend/app/main.py`, and frontend imports begin at `frontend/src/main.tsx`. Top-level copies such as `data_analytics/widget_data.py` and `ReportBuilder.tsx`, `.claude/worktrees/`, `.worktrees/`, and `_to_delete/` are not selected by these entry points. Do not use them as the current implementation.

The root `prompt.py` is a separate FastAPI prototype. It serves `/` and `/prompt-ui`, exposes `POST /api/chat` and `POST /api/completions`, calls an LLM, and shells out to `wren query` in `maps_project`. Its regex-based read-only check and lack of Datalytics authentication are separate from the main application's controls. Root `requirements.txt` belongs to this small prototype, not the main backend.

`maps_project/generate_mdl.py` introspects PostgreSQL and writes Wren model definitions; `models/`, `relationships.yml`, `views/`, `knowledge/`, and `target/` hold semantic project inputs and outputs. A GIS-related source catalog is not evidence that Datalytics runs a GIS solver.

`WrenAI/.claude/CLAUDE.md` describes Rust/DataFusion semantic planning, shared MDL types, Python bindings/CLI, and WASM. It is an independently configured upstream project. `superset_ref/`, `SAS/`, and `sas_new_data/` provide comparison/reference material, not deployed services in the active Compose stack. The untracked `sas_new_data/` directory already existed when inspection began.

## 3. Technology Stack

| Area | Actual implementation |
|---|---|
| Frontend | React `^18.3.1`, TypeScript `^5.4.5`, Vite `^5.2.12`; package version `2.0.0` is a manifest label, not a maturity guarantee |
| Routing/state | `react-router-dom ^7.18.4`; React state/effects/refs and Context, not a registered Redux/Zustand store |
| UI/forms | Custom components and CSS tokens; `lucide-react`, `react-hot-toast`; controlled inputs and handwritten validation. No dedicated form/validation library in the frontend manifest |
| Charts/maps/graphs | `recharts ^2.12.7`, `d3-cloud`, `d3-geo`, `topojson-client`, `world-atlas`, `reactflow ^11.11.4`, custom SVG/HTML renderers |
| API/export | `axios ^1.7.2`; `pptxgenjs ^4.0.1`; browser print plus server PDF/export paths |
| Backend | Python 3.12 Docker base; `fastapi==0.111.0`, `uvicorn[standard]==0.29.0` |
| ORM/validation | `sqlalchemy[asyncio]==2.0.30`, `asyncpg==0.29.0`, Pydantic v2-style models, `pydantic-settings==2.2.1`, `alembic==1.13.2` |
| Frames/statistics | `pandas==2.2.2`, `numpy==1.26.4`, `scipy==1.13.0`, `scikit-learn==1.5.1`, `statsmodels==0.14.6`, `statsforecast==2.1.1`, `pyod==3.6.5` |
| Files/querying | `pyarrow==16.1.0`, `openpyxl==3.1.2`, `duckdb-engine==0.13.2`, `sqlglot==30.17.0`, `lxml==6.1.2`; mdbtools in backend image |
| Authentication | `python-jose[cryptography]==3.3.0`, `passlib[bcrypt]==1.7.4`, `bcrypt==4.3.0`; OIDC and SAML implementation, `signxml==5.1.0` |
| Network/DB drivers | `httpx==0.27.0`, psycopg2-binary, pymssql, pymysql, oracledb, pyodbc; connector-dependent optional dialects |
| Output | `reportlab==4.2.2`, `matplotlib==3.9.2`, arabic-reshaper and python-bidi |
| Operational | Python logging; optional OpenTelemetry API/SDK/exporter `1.27.0` and instrumentation `0.48b0`; `redis==5.0.4` client for Valkey |
| Tests | pytest `8.2.2`, pytest-asyncio, pytest-timeout, freezegun, aiosqlite, fakeredis; Vitest `^2.0.5`, Testing Library, jsdom, axe-core; Playwright declared |
| Infrastructure | PostgreSQL `16-alpine`, Valkey `8-alpine`, Node `20-alpine`, production Nginx `1.27-alpine`; Docker Compose bridge network and named volumes |

Frontend versions above are declared ranges, not claims about every installed package. Python values are manifest pins. The embeddings process uses ONNX Runtime, tokenizers, numpy and FastAPI, with model files baked into its image. It does not run a full local chat model.

## 4. System Architecture

~~~mermaid
flowchart LR
  U[User] --> SPA[React SPA]
  SPA --> WEB[Vite dev or Nginx production]
  WEB --> API[FastAPI REST API]
  NB[Notebook client or MCP client] --> API
  API --> AUTH[Identity, organization, capability and data rules]
  AUTH --> ORM[Async SQLAlchemy metadata]
  ORM --> PG[(PostgreSQL)]
  AUTH --> Q[Widget and analytical services]
  Q --> FILES[(Imported files and Parquet)]
  Q --> PD[Pandas and DuckDB]
  Q --> DQ[DirectQuery SQL compiler]
  DQ --> SOURCES[(External databases and APIs)]
  Q <--> CACHE[Valkey or process cache]
  API --> AI[Native agent and copilot]
  AI --> Q
  AI --> LLM[Configured chat model HTTP endpoint]
  AI --> RET[Lexical or embedding retrieval]
  RET --> EMB[ONNX embeddings service]
  API --> SYNC[Metadata discovery and review]
  SYNC --> SOURCES
  SYNC --> PG
  SYNC --> LLM
  SCHED[In-process scheduler] --> Q
  SCHED --> AUTO[Persisted automation steps]
  SCHED --> SEND[PDF, email, webhook delivery and alerts]
  SEND --> SMTP[SMTP / external webhook]
~~~

The browser calls a single `/api/v1` REST namespace. Development uses an absolute API origin; production normally calls same-origin URLs through Nginx. ORM operations use async sessions; CPU-heavy frame operations and blocking source calls are frequently moved to `asyncio.to_thread`. This is not a microservice-per-domain design.

There are separate planes:

* **Metadata/governance:** datasets, connections, source catalog, reports, users, policies and execution records in PostgreSQL.
* **Data execution:** imported frames, Parquet/DuckDB optimization, or generated source SQL.
* **Analytical assistance:** statistical handlers, deterministic insights, LLM classification/planning/narration, suggestions and copilot.
* **Presentation:** persisted widget configuration interpreted by browser renderers.
* **Background operations:** refreshes, schedules, alerts, evaluations and automation.

Startup acquires a PostgreSQL advisory lock, attempts Alembic adoption/upgrades, runs ORM `create_all` and compatibility ALTERs, backfills organization/ownership information, migrates secrets, reaps stale jobs, then starts background tasks. The readiness flag is set after this sequence. Shutdown cancels scheduler tasks. Alembic failures can be logged and swallowed; therefore readiness is not proof that every intended migration succeeded.

## 5. Application Domains

| Domain | Entities and business meaning | Services / routes | Screens |
|---|---|---|---|
| Identity and tenancy | Organization, Role, User; org units and user placements; platform parent tree | dependencies, core security/org_scope/capability/rls; auth/admin/platform/authz | Login, admin users/roles/org units, platform organizations |
| Connections and knowledge | DataSource config; CustomConnector preset; SourceObject/Column/Relationship, Entity, GlossaryTerm, ColumnStats, SchemaVersion, SyncRun | connectors/connections/engines; metadata pipeline, knowledge/retrieval; data-sources, metadata | Connections, SourceReview, query-builder and review dialogs |
| Datasets and preparation | Dataset files or live query definitions; DatasetColumn, Watermark, Materialization, DataView, Relationship, HierarchyNode | ingest, prep, refresh, aggregates, custom functions, SQL expressions | Upload, dataset list/detail, studio data/model/prep panes |
| Reports and navigation | Report ? pages ? widgets; workspace folders; templates, bookmarks, parameters, translations, display rules | reports/workspace/widget_data; widget shaping/roles, review, composition | Reports, ReportBuilder, ReportPrint, workspace tree |
| Analytics and prediction | AnalysisResult, PredictionModel and analytical registry | analytics/analysis/insights/model_widgets; prediction-models | DatasetDetail, StatisticsPanel, InsightsHub, model widgets |
| AI conversations | Conversation, AgentMessage, AgentRun, AgentStep, QueryExample, AgentFeedback, RetrievalEmbedding | agent graph/nodes/validation/policy/executor; copilot and suggestions | AskAI, embedded ChatPane, CopilotChat, suggestion dialogs |
| Sharing and governance | ReportCapability/UserGrant, DatasetShare, folder grants, page visibility, RLS/CLS, classifications, ShareLink, EmbedConfig | capability, sensitivity, shared/embed/export guards | Access/share dialogs, SharedReport, EmbeddedReport, admin policies |
| Operations | ReportSchedule, DataAlert, Delivery, ScheduleFailure, QueryRun, Quota, audits, Notification, AutomationRun/Step | refresh_scheduler, delivery, alerts, quotas, telemetry, automation_runner | Monitoring, notification controls; automation management UI not found |
| Geography | BoundarySet, OrgMapSettings, geography hints in dataset/widget JSON | boundary validation and map settings | Map settings, boundary import/matching, geographic widget renderers |

Domain relationships are often JSON references rather than foreign keys. For example, per-widget dataset overrides live in widget config; dataflow outputs carry a recipe reference in dataset metadata. Not every relationship visible in the UI is a SQL foreign key.

## 6. Database Model

The active application metadata database is PostgreSQL. SQLAlchemy has 81 declarative tables in `backend/app/models/models.py`. It uses ordinary integer primary keys except the string-keyed SAML authentication request. Raw customer rows normally live in files or the external source, not in one PostgreSQL application table per uploaded dataset.

JSON columns store report layouts/configuration, derived formulas, measures, column metadata, prep recipes, aggregate specifications, relationship evidence, analytics results, schedules' recipients/options, run plans/results, embeddings, and snapshots. These nested structures have fewer database constraints than normalized columns. ORM JSON types and legacy bootstrap JSONB columns are not identical schema definitions.

~~~mermaid
erDiagram
  organizations ||--o{ users : contains
  organizations ||--o{ roles : defines
  roles ||--o{ users : assigned
  organizations ||--o{ datasets : owns
  data_sources o|--o{ datasets : supplies
  datasets ||--o{ dataset_columns : describes
  data_sources ||--o{ source_objects : catalogs
  source_objects ||--o{ source_columns : contains
  source_columns o|--o{ dataset_columns : provenance
  datasets o|--o{ reports : primary_dataset
  reports ||--o{ report_pages : contains
  report_pages ||--o{ report_widgets : contains
  reports ||--o{ report_versions : snapshots
  reports ||--o{ report_user_grants : grants
  users ||--o{ report_user_grants : receives
  roles ||--o{ row_security_rules : restricts
  datasets ||--o{ row_security_rules : scoped
  reports ||--o{ share_links : exposes
  reports ||--o{ embed_configs : embeds
  reports ||--o{ report_schedules : schedules
  datasets ||--o{ prediction_models : trains
  conversations ||--o{ agent_messages : records
  conversations o|--o{ agent_runs : groups
  agent_runs ||--o{ agent_steps : executes
  automation_runs ||--o{ automation_steps : progresses
~~~

The ER diagram is a readable subset. The complete column/foreign-key/constraint inventory below is authoritative for static ORM declarations.

Hierarchies are distinct: dataset field hierarchy nodes, workspace folder/report nodes, organization units used for user scope, and platform organization parent relationships. The latter does not automatically grant cross-organization data access.

Many-to-many links include user/org-unit placements, dataset/user shares, report/user grants, report/role capabilities, page/role visibility, folder/role restrictions, and dataflow/role capabilities. Folder grants target exactly one user, role or org unit by API convention; that XOR is not a database CHECK.

Important constraints include global unique user email; role/dataset row-rule uniqueness; object/role policy uniqueness; source object and source-column identity; unique report/user grant and dataset/user share; unique model name per organization/dataset; one map/review/SSO/quota row per organization; one materialization/watermark per dataset; and unique automation step name per run. See declarations below for the exact set. Nullable multi-column unique constraints have PostgreSQL NULL semantics, so they are not automatically equivalent to API-level uniqueness.

Deletion behavior matters: report pages/widgets and many governance records cascade; several owner pointers use SET NULL so authored artifacts can outlive the user; source references may become NULL; an aggregate dataset points to its source with CASCADE. The API sometimes reparents hierarchy/workspace children before deletion, rather than relying on cascade semantics.

Audit timestamps are mostly Python `datetime.utcnow` defaults; they are not evidence of update triggers. Legacy bootstrap SQL uses some server `NOW()` defaults. No active application CREATE POLICY/ENABLE ROW LEVEL SECURITY, trigger, stored procedure, custom database function, or application view definition was found in the inspected ORM/migration/bootstrap paths. Application RLS is implemented in Python/SQL generation. Source-database views and functions exposed by connectors are a different concern. No PostgreSQL vector extension is required by the current embeddings table; vectors are JSON.

Schema evolution has overlapping authorities: `postgres/init.sql`, Alembic, current ORM metadata and `main._migrate`. Bootstrap SQL also creates a legacy `charts` table absent from current ORM models, plus indexes not declared identically in the ORM. Actual installed tables/indexes and migration state **Need Verification** against a live database. The migration list follows the table inventory.

### Complete ORM inventory

All fields below are source declarations, not inspected live DDL. Default is an ORM-side default unless server_default is explicit. Column indexes/uniqueness and compound constraints are shown. JSON-linked IDs have no FK unless explicitly declared.

#### `datasets` ? Dataset

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L7).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| name | String(255) | ? | nullable=False |
| description | Text | ? | ORM defaults |
| filename | String(500) | ? | ORM defaults |
| row_count | Integer | ? | default=0 |
| col_count | Integer | ? | default=0 |
| file_size | BigInteger | ? | default=0 |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |
| updated_at | DateTime(timezone=True) | ? | default=datetime.utcnow; onupdate=datetime.utcnow |
| calculated_columns | JSON | ? | default=list |
| custom_functions | JSON | ? | default=list |
| column_formats | JSON | ? | default=dict |
| measures | JSON | ? | default=list |
| column_meta | JSON | ? | default=dict |
| default_filter_expr | Text | ? | nullable=True |
| data_source_id | Integer | ForeignKey('data_sources.id', ondelete='SET NULL') | nullable=True |
| source_table | String(500) | ? | nullable=True |
| source_query | Text | ? | nullable=True |
| query_model | JSON | ? | nullable=True |
| mode | String(20) | ? | nullable=False; default='import'; server_default='import' |
| refresh_interval_minutes | Integer | ? | nullable=True |
| last_refreshed_at | DateTime(timezone=True) | ? | nullable=True |
| aggregate_of_dataset_id | Integer | ForeignKey('datasets.id', ondelete='CASCADE') | nullable=True; index=True |
| aggregate_spec | JSON | ? | nullable=True |
| is_deprecated | Boolean | ? | nullable=False; default=False; server_default='0' |
| description_source | String(20) | ? | nullable=True |
| last_profiled_at | DateTime(timezone=True) | ? | nullable=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=True |
| created_by | Integer | ForeignKey('users.id', ondelete='SET NULL') | nullable=True; index=True |


ORM navigation: `columns: relationship('DatasetColumn', back_populates='dataset', cascade='all, delete-orphan')`; `analysis_results: relationship('AnalysisResult', back_populates='dataset', cascade='all, delete-orphan')`; `hierarchy_nodes: relationship('HierarchyNode', back_populates='dataset', cascade='all, delete-orphan')`.

#### `dataset_shares` ? DatasetShare

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L82).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| dataset_id | Integer | ForeignKey('datasets.id', ondelete='CASCADE') | nullable=False |
| user_id | Integer | ForeignKey('users.id', ondelete='CASCADE') | nullable=False |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


Compound declarations: `(UniqueConstraint('dataset_id', 'user_id', name='uq_dataset_share'),)`.

ORM navigation: `dataset: relationship('Dataset')`; `user: relationship('User')`.

#### `dataset_columns` ? DatasetColumn

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L101).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| dataset_id | Integer | ForeignKey('datasets.id', ondelete='CASCADE') | nullable=False |
| name | String(255) | ? | nullable=False |
| dtype | String(50) | ? | nullable=False |
| missing_pct | Float | ? | default=0 |
| stats | JSON | ? | default=dict |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |
| semantic_type | String(40) | ? | nullable=True |
| description | Text | ? | nullable=True |
| description_source | String(20) | ? | nullable=True |
| source_column_id | Integer | ForeignKey('source_columns.id', ondelete='SET NULL') | nullable=True; index=True |


ORM navigation: `dataset: relationship('Dataset', back_populates='columns')`.

#### `analysis_results` ? AnalysisResult

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L133).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| dataset_id | Integer | ForeignKey('datasets.id', ondelete='CASCADE') | nullable=False |
| analysis_type | String(100) | ? | nullable=False |
| result | JSON | ? | nullable=False |
| run_id | Integer | ForeignKey('automation_runs.id', ondelete='SET NULL') | nullable=True; index=True |
| params | JSON | ? | nullable=True |
| created_by | Integer | ForeignKey('users.id', ondelete='SET NULL') | nullable=True |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


ORM navigation: `dataset: relationship('Dataset', back_populates='analysis_results')`.

#### `reports` ? Report

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L150).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| name | String(255) | ? | nullable=False |
| description | Text | ? | ORM defaults |
| dataset_id | Integer | ForeignKey('datasets.id', ondelete='SET NULL') | nullable=True |
| additional_dataset_ids | JSON | ? | default=list |
| theme | String(20) | ? | nullable=False; default='default'; server_default='default' |
| display_rules | JSON | ? | default=list |
| revision | Integer | ? | nullable=False; default=0; server_default='0' |
| created_by | Integer | ForeignKey('users.id', ondelete='SET NULL') | nullable=True; index=True |
| published | Boolean | ? | nullable=False; default=False; server_default='0' |
| origin | String(20) | ? | nullable=False; default='user'; server_default='user'; index=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=True |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |
| updated_at | DateTime(timezone=True) | ? | default=datetime.utcnow; onupdate=datetime.utcnow |


ORM navigation: `pages: relationship('ReportPage', back_populates='report', cascade='all, delete-orphan', order_by='ReportPage.position')`; `bookmarks: relationship('Bookmark', back_populates='report', cascade='all, delete-orphan', order_by='Bookmark.position')`.

#### `report_pages` ? ReportPage

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L198).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| report_id | Integer | ForeignKey('reports.id', ondelete='CASCADE') | nullable=False |
| name | String(255) | ? | nullable=False; default='Page 1' |
| title | String(255) | ? | ORM defaults |
| page_type | String(20) | ? | nullable=False; default='normal' |
| prompt_column | String(255) | ? | ORM defaults |
| prompt_label | String(255) | ? | ORM defaults |
| position | Integer | ? | nullable=False; default=0 |
| page_size | String(20) | ? | nullable=False; default='16:9'; server_default='16:9' |
| custom_width | Integer | ? | nullable=True |
| custom_height | Integer | ? | nullable=True |
| mobile_layout | JSON | ? | nullable=True |
| background_url | String(1000) | ? | nullable=True |
| layout_mode | String(20) | ? | nullable=True |
| layout_template | String(40) | ? | nullable=True |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


ORM navigation: `report: relationship('Report', back_populates='pages')`; `widgets: relationship('ReportWidget', back_populates='page', cascade='all, delete-orphan')`.

#### `report_versions` ? ReportVersion

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L225).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| report_id | Integer | ForeignKey('reports.id', ondelete='CASCADE') | nullable=False; index=True |
| revision | Integer | ? | nullable=False; default=0 |
| snapshot | JSON | ? | nullable=False |
| created_by | Integer | ForeignKey('users.id', ondelete='SET NULL') | nullable=True |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


#### `report_widgets` ? ReportWidget

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L252).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| page_id | Integer | ForeignKey('report_pages.id', ondelete='CASCADE') | nullable=False |
| widget_type | String(50) | ? | nullable=False |
| title | String(255) | ? | ORM defaults |
| config | JSON | ? | default=dict |
| layout | JSON | ? | default=lambda: {'x': 0, 'y': 0, 'w': 6, 'h': 4} |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


ORM navigation: `page: relationship('ReportPage', back_populates='widgets')`.

#### `hierarchy_nodes` ? HierarchyNode

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L264).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| dataset_id | Integer | ForeignKey('datasets.id', ondelete='CASCADE') | nullable=False |
| parent_id | Integer | ForeignKey('hierarchy_nodes.id', ondelete='CASCADE') | nullable=True |
| name | String(255) | ? | nullable=False |
| node_type | String(20) | ? | nullable=False; default='folder' |
| column_name | String(255) | ? | ORM defaults |
| aggregation | String(50) | ? | ORM defaults |
| format | String(100) | ? | ORM defaults |
| position | Integer | ? | nullable=False; default=0 |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


ORM navigation: `dataset: relationship('Dataset', back_populates='hierarchy_nodes')`; `children: relationship('HierarchyNode', cascade='all, delete-orphan')`.

#### `data_sources` ? DataSource

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L280).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| name | String(255) | ? | nullable=False |
| type | String(50) | ? | nullable=False |
| config | JSON | ? | default=dict |
| cache_ttl_seconds | Integer | ? | nullable=False; default=60; server_default='60' |
| allow_llm_sampling | Boolean | ? | nullable=False; default=False; server_default='0' |
| description | Text | ? | nullable=True |
| description_source | String(20) | ? | nullable=True |
| last_synced_at | DateTime(timezone=True) | ? | nullable=True |
| sync_status | String(20) | ? | nullable=False; default='pending'; server_default='pending' |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=True |
| created_by | Integer | ForeignKey('users.id', ondelete='SET NULL') | nullable=True; index=True |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |
| updated_at | DateTime(timezone=True) | ? | default=datetime.utcnow; onupdate=datetime.utcnow |
| cache_epoch | Integer | ? | nullable=False; default=0; server_default='0' |
| custom_connector_id | Integer | ForeignKey('custom_connectors.id', ondelete='RESTRICT') | nullable=True; index=True |


#### `custom_connectors` ? CustomConnector

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L323).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False; index=True |
| key | String(100) | ? | nullable=False |
| label | String(255) | ? | nullable=False |
| base_type | String(50) | ? | nullable=False |
| base_config | JSON | ? | default=dict |
| locked_fields | JSON | ? | default=list |
| created_by | Integer | ForeignKey('users.id', ondelete='SET NULL') | nullable=True; index=True |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |
| updated_at | DateTime(timezone=True) | ? | default=datetime.utcnow; onupdate=datetime.utcnow |


Compound declarations: `(UniqueConstraint('org_id', 'key', name='uq_custom_connectors_org_key'),)`.

#### `boundary_sets` ? BoundarySet

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L343).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False; index=True |
| name | String(200) | ? | nullable=False |
| geometry | JSON | ? | nullable=False |
| key_properties | JSON | ? | default=list |
| feature_count | Integer | ? | nullable=False; default=0 |
| created_by | Integer | ForeignKey('users.id', ondelete='SET NULL') | nullable=True; index=True |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


Compound declarations: `(UniqueConstraint('org_id', 'name', name='uq_boundary_sets_org_name'),)`.

#### `prediction_models` ? PredictionModel

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L371).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False; index=True |
| dataset_id | Integer | ForeignKey('datasets.id', ondelete='CASCADE') | nullable=False; index=True |
| name | String(200) | ? | nullable=False |
| target | String(255) | ? | nullable=False |
| features | JSON | ? | nullable=False; default=list |
| feature_columns | JSON | ? | nullable=False; default=list |
| categories | JSON | ? | nullable=False; default=dict |
| task | String(32) | ? | nullable=False |
| model_family | String(64) | ? | nullable=False |
| score | Float | ? | nullable=True |
| score_name | String(32) | ? | nullable=True |
| artifact | LargeBinary | ? | nullable=False |
| trained_rls | Text | ? | nullable=True |
| created_by | Integer | ForeignKey('users.id', ondelete='SET NULL') | nullable=True; index=True |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


Compound declarations: `(UniqueConstraint('org_id', 'dataset_id', 'name', name='uq_prediction_models_org_dataset_name'),)`.

#### `org_review_settings` ? OrgReviewSettings

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L420).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False; unique=True; index=True |
| publish_gate | Boolean | ? | nullable=False; default=False; server_default=text('false') |
| updated_by | Integer | ForeignKey('users.id', ondelete='SET NULL') | nullable=True |
| updated_at | DateTime(timezone=True) | ? | default=datetime.utcnow; onupdate=datetime.utcnow |


#### `org_map_settings` ? OrgMapSettings

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L432).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False; unique=True; index=True |
| tile_url | String(500) | ? | nullable=True |
| attribution | String(300) | ? | nullable=True |
| contrast_tile_url | String(500) | ? | nullable=True |
| updated_by | Integer | ForeignKey('users.id', ondelete='SET NULL') | nullable=True |
| updated_at | DateTime(timezone=True) | ? | default=datetime.utcnow; onupdate=datetime.utcnow |


#### `organizations` ? Organization

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L450).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| name | String(255) | ? | nullable=False |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


ORM navigation: `roles: relationship('Role', back_populates='organization', cascade='all, delete-orphan')`; `users: relationship('User', back_populates='organization', cascade='all, delete-orphan')`.

#### `roles` ? Role

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L460).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False |
| name | String(255) | ? | nullable=False |
| is_org_admin | Boolean | ? | nullable=False; default=False |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


ORM navigation: `organization: relationship('Organization', back_populates='roles')`; `users: relationship('User', back_populates='role')`; `rules: relationship('RowSecurityRule', back_populates='role', cascade='all, delete-orphan')`.

#### `users` ? User

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L473).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False |
| role_id | Integer | ForeignKey('roles.id', ondelete='RESTRICT') | nullable=False |
| email | String(255) | ? | nullable=False; unique=True |
| password_hash | String(255) | ? | nullable=False |
| is_active | Boolean | ? | nullable=False; default=True |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


ORM navigation: `organization: relationship('Organization', back_populates='users')`; `role: relationship('Role', back_populates='users')`.

#### `org_units` ? OrgUnit

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L487).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False; index=True |
| parent_id | Integer | ForeignKey('org_units.id', ondelete='CASCADE') | nullable=True; index=True |
| name | String(255) | ? | nullable=False |
| level_name | String(60) | ? | ORM defaults |
| match_value | String(255) | ? | nullable=False |
| position | Integer | ? | nullable=False; default=0 |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


Compound declarations: `(UniqueConstraint('org_id', 'parent_id', 'name', name='uq_org_unit_sibling_name'),)`.

#### `user_org_units` ? UserOrgUnit

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L523).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| user_id | Integer | ForeignKey('users.id', ondelete='CASCADE') | nullable=False; index=True |
| org_unit_id | Integer | ForeignKey('org_units.id', ondelete='CASCADE') | nullable=False; index=True |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


Compound declarations: `(UniqueConstraint('user_id', 'org_unit_id', name='uq_user_org_unit'),)`.

#### `row_security_rules` ? RowSecurityRule

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L545).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| role_id | Integer | ForeignKey('roles.id', ondelete='CASCADE') | nullable=False |
| dataset_id | Integer | ForeignKey('datasets.id', ondelete='CASCADE') | nullable=False |
| filter_expr | Text | ? | nullable=False |
| auto_generated | Boolean | ? | nullable=False; default=False; server_default='0' |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


Compound declarations: `(UniqueConstraint('role_id', 'dataset_id', name='uq_role_dataset_rule'),)`.

ORM navigation: `role: relationship('Role', back_populates='rules')`; `dataset: relationship('Dataset')`.

#### `relationships` ? Relationship

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L563).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False |
| from_dataset_id | Integer | ForeignKey('datasets.id', ondelete='CASCADE') | nullable=False |
| from_column | String(255) | ? | nullable=False |
| to_dataset_id | Integer | ForeignKey('datasets.id', ondelete='CASCADE') | nullable=False |
| to_column | String(255) | ? | nullable=False |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |
| confidence | Float | ? | nullable=False; default=1.0; server_default='1.0' |
| source | String(20) | ? | nullable=False; default='declared'; server_default='declared' |
| evidence | JSON | ? | nullable=True |
| cardinality | String(20) | ? | nullable=True |


ORM navigation: `from_dataset: relationship('Dataset', foreign_keys=[from_dataset_id])`; `to_dataset: relationship('Dataset', foreign_keys=[to_dataset_id])`.

#### `bookmarks` ? Bookmark

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L590).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| report_id | Integer | ForeignKey('reports.id', ondelete='CASCADE') | nullable=False |
| name | String(255) | ? | nullable=False |
| position | Integer | ? | nullable=False; default=0 |
| state | JSON | ? | nullable=False |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


ORM navigation: `report: relationship('Report', back_populates='bookmarks')`.

#### `audit_log` ? AuditLogEntry

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L601).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False; index=True |
| user_id | Integer | ForeignKey('users.id', ondelete='SET NULL') | nullable=True |
| user_email | String(255) | ? | ORM defaults |
| action | String(50) | ? | nullable=False |
| entity | String(50) | ? | ORM defaults |
| entity_id | Integer | ? | ORM defaults |
| detail | String(500) | ? | ORM defaults |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow; index=True |


#### `org_themes` ? OrgTheme

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L620).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False; index=True |
| name | String(100) | ? | nullable=False |
| colors | JSON | ? | nullable=False; default=list |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


#### `report_parameters` ? ReportParameter

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L636).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| report_id | Integer | ForeignKey('reports.id', ondelete='CASCADE') | nullable=False; index=True |
| name | String(60) | ? | nullable=False |
| param_type | String(20) | ? | nullable=False; default='number' |
| label | String(120) | ? | ORM defaults |
| default_value | String(500) | ? | ORM defaults |
| options | JSON | ? | default=list |
| position | Integer | ? | nullable=False; default=0 |


#### `report_schedules` ? ReportSchedule

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L657).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False; index=True |
| report_id | Integer | ForeignKey('reports.id', ondelete='CASCADE') | nullable=False |
| creator_user_id | Integer | ForeignKey('users.id', ondelete='CASCADE') | nullable=False |
| interval_minutes | Integer | ? | nullable=False |
| recipients | JSON | ? | nullable=False; default=list |
| subject | String(200) | ? | ORM defaults |
| last_run_at | DateTime(timezone=True) | ? | nullable=True |
| last_status | String(200) | ? | ORM defaults |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |
| timezone | String(64) | ? | nullable=True |


#### `deliveries` ? Delivery

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L683).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False; index=True |
| schedule_id | Integer | ForeignKey('report_schedules.id', ondelete='CASCADE') | nullable=True; index=True |
| report_id | Integer | ForeignKey('reports.id', ondelete='CASCADE') | nullable=True; index=True |
| kind | String(20) | ? | nullable=False |
| status | String(10) | ? | nullable=False |
| error | Text | ? | nullable=True |
| artifact_kind | String(10) | ? | nullable=False; default='none' |
| duration_ms | Integer | ? | nullable=True |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow; index=True |


#### `data_alerts` ? DataAlert

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L707).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False; index=True |
| dataset_id | Integer | ForeignKey('datasets.id', ondelete='CASCADE') | nullable=False |
| creator_user_id | Integer | ForeignKey('users.id', ondelete='CASCADE') | nullable=False |
| name | String(200) | ? | nullable=False |
| expression | Text | ? | nullable=False |
| interval_minutes | Integer | ? | nullable=False; default=60 |
| recipients | JSON | ? | nullable=False; default=list |
| last_checked_at | DateTime(timezone=True) | ? | nullable=True |
| last_state | String(10) | ? | nullable=False; default='clear' |
| last_status | String(200) | ? | ORM defaults |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


#### `page_templates` ? PageTemplate

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L730).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False; index=True |
| name | String(120) | ? | nullable=False |
| kind | String(20) | ? | nullable=False; default='page' |
| payload | JSON | ? | nullable=False; default=dict |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


#### `recent_views` ? RecentView

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L747).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| user_id | Integer | ForeignKey('users.id', ondelete='CASCADE') | nullable=False; index=True |
| report_id | Integer | ForeignKey('reports.id', ondelete='CASCADE') | nullable=False; index=True |
| viewed_at | DateTime(timezone=True) | ? | default=datetime.utcnow; onupdate=datetime.utcnow; nullable=False |


Compound declarations: `(UniqueConstraint('user_id', 'report_id', name='uq_recent_user_report'),)`.

#### `pinned_tiles` ? PinnedTile

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L778).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False |
| user_id | Integer | ForeignKey('users.id', ondelete='CASCADE') | nullable=False |
| widget_id | Integer | ForeignKey('report_widgets.id', ondelete='CASCADE') | nullable=True |
| dataset_id | Integer | ForeignKey('datasets.id', ondelete='CASCADE') | nullable=True |
| finding_key | Text | ? | nullable=True |
| position | Integer | ? | nullable=True |
| size | String(1) | ? | nullable=False; default='m'; server_default='m' |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


Compound declarations: `(UniqueConstraint('user_id', 'widget_id', name='uq_pin_user_widget'), UniqueConstraint('user_id', 'dataset_id', 'finding_key', name='uq_pin_user_finding'))`.

#### `page_role_visibility` ? PageRoleVisibility

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L818).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| page_id | Integer | ForeignKey('report_pages.id', ondelete='CASCADE') | nullable=False; index=True |
| role_id | Integer | ForeignKey('roles.id', ondelete='CASCADE') | nullable=False |


#### `report_user_grants` ? ReportUserGrant

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L834).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| report_id | Integer | ForeignKey('reports.id', ondelete='CASCADE') | nullable=False; index=True |
| user_id | Integer | ForeignKey('users.id', ondelete='CASCADE') | nullable=False; index=True |
| level | String(5) | ? | nullable=False; default='edit' |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


Compound declarations: `(UniqueConstraint('report_id', 'user_id', name='uq_report_user_grant'),)`.

#### `report_capability` ? ReportCapability

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L859).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| report_id | Integer | ForeignKey('reports.id', ondelete='CASCADE') | nullable=False; index=True |
| role_id | Integer | ForeignKey('roles.id', ondelete='CASCADE') | nullable=False |
| level | String(10) | ? | nullable=False; default='data' |


#### `column_security_rules` ? ColumnSecurityRule

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L880).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| role_id | Integer | ForeignKey('roles.id', ondelete='CASCADE') | nullable=False |
| dataset_id | Integer | ForeignKey('datasets.id', ondelete='CASCADE') | nullable=False; index=True |
| denied_columns | JSON | ? | nullable=False; default=list |


#### `data_views` ? DataView

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L895).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False; index=True |
| name | String(255) | ? | nullable=False |
| payload | JSON | ? | nullable=False; default=dict |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |
| creator_user_id | Integer | ForeignKey('users.id', ondelete='SET NULL') | nullable=True |
| is_default | Boolean | ? | nullable=False; default=False; server_default=text('false') |


#### `report_classifications` ? ReportClassification

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L921).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| report_id | Integer | ForeignKey('reports.id', ondelete='CASCADE') | nullable=False; unique=True; index=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False; index=True |
| label | String(40) | ? | nullable=False |
| updated_at | DateTime(timezone=True) | ? | default=datetime.utcnow; onupdate=datetime.utcnow |


#### `api_keys` ? ApiKey

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L935).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False; index=True |
| user_id | Integer | ForeignKey('users.id', ondelete='CASCADE') | nullable=False; index=True |
| name | String(120) | ? | nullable=False |
| prefix | String(16) | ? | nullable=False; unique=True; index=True |
| key_hash | String(64) | ? | nullable=False |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |
| last_used_at | DateTime(timezone=True) | ? | nullable=True |


#### `org_idps` ? OrgIdp

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L954).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False; unique=True; index=True |
| protocol | String(10) | ? | nullable=False; default='oidc' |
| enabled | Boolean | ? | nullable=False; default=True |
| email_domain | String(255) | ? | nullable=False; index=True |
| issuer | String(500) | ? | ORM defaults |
| client_id | String(255) | ? | ORM defaults |
| client_secret | String(1000) | ? | ORM defaults |
| config | JSON | ? | default=dict |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


#### `saml_authn_requests` ? SamlAuthnRequest

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L975).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | String(64) | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False |
| acs_url | String(1000) | ? | nullable=False |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


#### `org_mcp_access` ? OrgMcpAccess

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L988).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False; unique=True; index=True |
| enabled | Boolean | ? | nullable=False; default=True |


#### `org_parents` ? OrgParent

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L1000).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False; unique=True; index=True |
| parent_org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False; index=True |


#### `common_filters` ? CommonFilter

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L1013).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| report_id | Integer | ForeignKey('reports.id', ondelete='CASCADE') | nullable=False; index=True |
| column | String(255) | ? | nullable=False |
| op | String(10) | ? | nullable=False; default='eq' |
| value | JSON | ? | ORM defaults |
| position | Integer | ? | nullable=False; default=0 |


#### `widget_templates` ? WidgetTemplate

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L1029).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False; index=True |
| name | String(255) | ? | nullable=False |
| widget_type | String(50) | ? | nullable=False |
| config | JSON | ? | nullable=False; default=dict |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |
| creator_user_id | Integer | ForeignKey('users.id', ondelete='SET NULL') | nullable=True |


#### `notifications` ? Notification

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L1047).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False; index=True |
| user_id | Integer | ForeignKey('users.id', ondelete='CASCADE') | nullable=False; index=True |
| kind | String(40) | ? | nullable=False |
| text | String(500) | ? | nullable=False |
| link | String(500) | ? | nullable=True |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |
| read_at | DateTime(timezone=True) | ? | nullable=True |


#### `report_comments` ? ReportComment

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L1064).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False; index=True |
| report_id | Integer | ForeignKey('reports.id', ondelete='CASCADE') | nullable=False; index=True |
| page_id | Integer | ForeignKey('report_pages.id', ondelete='SET NULL') | nullable=True |
| user_id | Integer | ForeignKey('users.id', ondelete='CASCADE') | nullable=False |
| text | Text | ? | nullable=False |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


#### `share_links` ? ShareLink

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L1079).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False; index=True |
| report_id | Integer | ForeignKey('reports.id', ondelete='CASCADE') | nullable=False; index=True |
| creator_user_id | Integer | ForeignKey('users.id', ondelete='CASCADE') | nullable=False |
| token_hash | String(64) | ? | nullable=False; unique=True; index=True |
| expires_at | DateTime(timezone=True) | ? | nullable=False |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |
| revoked_at | DateTime(timezone=True) | ? | nullable=True |
| snapshot | JSON | ? | nullable=True |
| pinned | Boolean | ? | nullable=False; default=False |


#### `share_link_access` ? ShareLinkAccess

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L1105).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| share_link_id | Integer | ForeignKey('share_links.id', ondelete='CASCADE') | nullable=False; index=True |
| viewer_user_id | Integer | ForeignKey('users.id', ondelete='SET NULL') | nullable=True |
| ts | DateTime(timezone=True) | ? | default=datetime.utcnow; index=True |
| ip_hash | String(64) | ? | nullable=True |
| user_agent | String(200) | ? | nullable=True |


#### `embed_configs` ? EmbedConfig

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L1122).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False; index=True |
| report_id | Integer | ForeignKey('reports.id', ondelete='CASCADE') | nullable=False; index=True |
| created_by | Integer | ForeignKey('users.id', ondelete='CASCADE') | nullable=False |
| name | String(255) | ? | nullable=False |
| secret_encrypted | Text | ? | nullable=False |
| allowed_origins | JSON | ? | default=list |
| enabled | Boolean | ? | nullable=False; default=True |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |
| last_used_at | DateTime(timezone=True) | ? | nullable=True |


Compound declarations: `(UniqueConstraint('report_id', 'name', name='uq_embed_config_name'),)`.

#### `quotas` ? Quota

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L1155).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False; unique=True |
| max_queries_per_day | Integer | ? | nullable=True |
| max_agent_asks_per_day | Integer | ? | nullable=True |
| max_storage_mb | Integer | ? | nullable=True |
| max_concurrent_asks | Integer | ? | nullable=True |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |
| updated_at | DateTime(timezone=True) | ? | default=datetime.utcnow; onupdate=datetime.utcnow |


#### `report_translations` ? ReportTranslation

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L1178).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| report_id | Integer | ForeignKey('reports.id', ondelete='CASCADE') | nullable=False; index=True |
| locale | String(10) | ? | nullable=False |
| payload | JSON | ? | nullable=False; default=dict |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


#### `column_stats` ? ColumnStats

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L1201).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| dataset_column_id | Integer | ForeignKey('dataset_columns.id', ondelete='CASCADE') | nullable=True; unique=True; index=True |
| source_column_id | Integer | ForeignKey('source_columns.id', ondelete='CASCADE') | nullable=True; unique=True; index=True |
| null_ratio | Float | ? | nullable=True |
| distinct_count | BigInteger | ? | nullable=True |
| top_k | JSON | ? | nullable=True |
| min_value | Text | ? | nullable=True |
| max_value | Text | ? | nullable=True |
| avg_width | Integer | ? | nullable=True |
| exact | Boolean | ? | nullable=False; default=False; server_default='0' |
| computed_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


#### `schema_versions` ? SchemaVersion

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L1237).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| data_source_id | Integer | ForeignKey('data_sources.id', ondelete='CASCADE') | nullable=False; index=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False; index=True |
| fingerprint | String(64) | ? | nullable=False |
| diff | JSON | ? | nullable=True |
| detected_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


#### `sync_runs` ? SyncRun

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L1262).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| data_source_id | Integer | ForeignKey('data_sources.id', ondelete='CASCADE') | nullable=False; index=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False; index=True |
| trigger | String(20) | ? | nullable=False |
| status | String(20) | ? | nullable=False |
| stages | JSON | ? | nullable=False; default=list |
| error | Text | ? | nullable=True |
| started_at | DateTime(timezone=True) | ? | default=datetime.utcnow |
| finished_at | DateTime(timezone=True) | ? | nullable=True |


#### `watermarks` ? Watermark

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L1286).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| dataset_id | Integer | ForeignKey('datasets.id', ondelete='CASCADE') | nullable=False; unique=True; index=True |
| strategy | String(20) | ? | nullable=False; default='full' |
| cursor_column | String(255) | ? | nullable=True |
| cursor_value | Text | ? | nullable=True |
| updated_at | DateTime(timezone=True) | ? | default=datetime.utcnow; onupdate=datetime.utcnow |


#### `materializations` ? Materialization

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L1304).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| dataset_id | Integer | ForeignKey('datasets.id', ondelete='CASCADE') | nullable=False; unique=True; index=True |
| path | String(1000) | ? | nullable=False |
| kind | String(20) | ? | nullable=False |
| row_count | Integer | ? | nullable=False; default=0 |
| columns | JSON | ? | nullable=False; default=list |
| watermark_value | Text | ? | nullable=True |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


#### `source_objects` ? SourceObject

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L1353).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| data_source_id | Integer | ForeignKey('data_sources.id', ondelete='CASCADE') | nullable=False; index=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False; index=True |
| schema_name | String(255) | ? | nullable=True |
| name | String(500) | ? | nullable=False |
| kind | String(20) | ? | nullable=False; default='table' |
| row_count_estimate | BigInteger | ? | nullable=True |
| comment | Text | ? | nullable=True |
| description | Text | ? | nullable=True |
| description_source | String(20) | ? | nullable=True |
| is_canonical | Boolean | ? | nullable=False; default=False; server_default='0' |
| is_deprecated | Boolean | ? | nullable=False; default=False; server_default='0' |
| last_profiled_at | DateTime(timezone=True) | ? | nullable=True |
| sample_timed_out_at | DateTime(timezone=True) | ? | nullable=True |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


Compound declarations: `(UniqueConstraint('data_source_id', 'schema_name', 'name', name='uq_source_object'),)`.

ORM navigation: `columns: relationship('SourceColumn', back_populates='object', cascade='all, delete-orphan')`.

#### `source_columns` ? SourceColumn

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L1399).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| source_object_id | Integer | ForeignKey('source_objects.id', ondelete='CASCADE') | nullable=False; index=True |
| name | String(500) | ? | nullable=False |
| position | Integer | ? | nullable=False; default=0 |
| native_type | String(255) | ? | nullable=True |
| dtype | String(50) | ? | nullable=True |
| nullable | Boolean | ? | nullable=False; default=True |
| is_primary_key | Boolean | ? | nullable=False; default=False; server_default='0' |
| comment | Text | ? | nullable=True |
| semantic_type | String(40) | ? | nullable=True |
| description | Text | ? | nullable=True |
| description_source | String(20) | ? | nullable=True |
| enum_labels | JSON | ? | nullable=True |
| enum_labels_source | String(20) | ? | nullable=True |
| target_candidate_priority | Integer | ? | nullable=True |


Compound declarations: `(UniqueConstraint('source_object_id', 'name', name='uq_source_column'),)`.

ORM navigation: `object: relationship('SourceObject', back_populates='columns')`.

#### `source_relationships` ? SourceRelationship

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L1443).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| data_source_id | Integer | ForeignKey('data_sources.id', ondelete='CASCADE') | nullable=False; index=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False; index=True |
| from_object_id | Integer | ForeignKey('source_objects.id', ondelete='CASCADE') | nullable=False; index=True |
| from_column | String(500) | ? | nullable=False |
| to_object_id | Integer | ForeignKey('source_objects.id', ondelete='CASCADE') | nullable=False; index=True |
| to_column | String(500) | ? | nullable=False |
| confidence | Float | ? | nullable=False; default=1.0; server_default='1.0' |
| source | String(20) | ? | nullable=False; default='declared'; server_default='declared' |
| evidence | JSON | ? | nullable=True |
| cardinality | String(20) | ? | nullable=True |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


#### `conversations` ? Conversation

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L1469).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False |
| user_id | Integer | ForeignKey('users.id', ondelete='SET NULL') | nullable=True |
| data_source_id | Integer | ForeignKey('data_sources.id', ondelete='SET NULL') | nullable=True |
| dataset_ids | JSON | ? | nullable=True |
| title | String(200) | ? | nullable=True |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


ORM navigation: `messages: relationship('AgentMessage', cascade='all, delete-orphan')`.

#### `agent_messages` ? AgentMessage

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L1487).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| conversation_id | Integer | ForeignKey('conversations.id', ondelete='CASCADE') | nullable=False |
| role | String(20) | ? | nullable=False |
| content | Text | ? | nullable=False |
| agent_run_id | Integer | ForeignKey('agent_runs.id', ondelete='SET NULL') | nullable=True |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


#### `agent_runs` ? AgentRun

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L1499).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False |
| conversation_id | Integer | ForeignKey('conversations.id', ondelete='SET NULL') | nullable=True |
| question | Text | ? | nullable=False |
| status | String(30) | ? | nullable=False; default='running' |
| intent | String(30) | ? | nullable=True |
| plan | JSON | ? | nullable=True |
| answer | Text | ? | nullable=True |
| error | Text | ? | nullable=True |
| ms | Integer | ? | nullable=True |
| context_objects | JSON | ? | nullable=True |
| presentation | JSON | ? | nullable=True |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


#### `agent_steps` ? AgentStep

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L1524).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| agent_run_id | Integer | ForeignKey('agent_runs.id', ondelete='CASCADE') | nullable=False |
| node | String(80) | ? | nullable=False |
| status | String(30) | ? | nullable=False |
| sql | Text | ? | nullable=True |
| rows_returned | Integer | ? | nullable=True |
| result_rows | JSON | ? | nullable=True |
| validation_failures | JSON | ? | nullable=True |
| repair_attempts | Integer | ? | nullable=False; default=0 |
| ms | Integer | ? | nullable=True |


#### `agent_feedback` ? AgentFeedback

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L1544).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False; index=True |
| user_id | Integer | ForeignKey('users.id', ondelete='CASCADE') | nullable=False |
| conversation_id | Integer | ForeignKey('conversations.id', ondelete='CASCADE') | nullable=False |
| run_id | Integer | ForeignKey('agent_runs.id', ondelete='CASCADE') | nullable=True |
| rating | String(10) | ? | nullable=False |
| comment | Text | ? | nullable=True |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


#### `eval_runs` ? EvalRun

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L1563).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| started_at | DateTime(timezone=True) | ? | nullable=False |
| finished_at | DateTime(timezone=True) | ? | nullable=True |
| accuracy | Float | ? | nullable=True |
| passed | Boolean | ? | nullable=True |
| detail | JSON | ? | nullable=True |


#### `query_examples` ? QueryExample

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L1578).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False |
| data_source_id | Integer | ForeignKey('data_sources.id', ondelete='CASCADE') | nullable=True |
| dataset_key | String(120) | ? | nullable=True |
| question | Text | ? | nullable=False |
| sql | Text | ? | nullable=False |
| confirmed_by | Integer | ForeignKey('users.id', ondelete='SET NULL') | nullable=True |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


#### `glossary_terms` ? GlossaryTerm

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L1595).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False; index=True |
| data_source_id | Integer | ForeignKey('data_sources.id', ondelete='CASCADE') | nullable=True; index=True |
| term | String(200) | ? | nullable=False |
| definition | Text | ? | nullable=True |
| synonyms | JSON | ? | nullable=False; default=list |
| maps_to_object | String(255) | ? | nullable=True |
| maps_to_column | String(255) | ? | nullable=True |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


#### `query_runs` ? QueryRun

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L1618).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='SET NULL') | nullable=True; index=True |
| source_kind | String(20) | ? | nullable=False |
| data_source_id | Integer | ForeignKey('data_sources.id', ondelete='SET NULL') | nullable=True; index=True |
| dataset_id | Integer | ForeignKey('datasets.id', ondelete='SET NULL') | nullable=True; index=True |
| sql_hash | String(64) | ? | nullable=True |
| rows_returned | Integer | ? | nullable=True |
| duration_ms | Integer | ? | nullable=False |
| executor | String(20) | ? | nullable=False |
| cache_hit | Boolean | ? | nullable=False; default=False; server_default='0' |
| source_table | String(255) | ? | nullable=True |
| filter_columns | JSON | ? | nullable=True |
| group_column | String(255) | ? | nullable=True |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


#### `object_row_policies` ? ObjectRowPolicy

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L1649).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False |
| source_object_id | Integer | ForeignKey('source_objects.id', ondelete='CASCADE') | nullable=False |
| role_id | Integer | ForeignKey('roles.id', ondelete='CASCADE') | nullable=False |
| predicate | Text | ? | nullable=False |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


Compound declarations: `(UniqueConstraint('source_object_id', 'role_id', name='uq_object_role_policy'),)`.

#### `admin_audit` ? AdminAudit

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L1668).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False; index=True |
| actor_id | Integer | ForeignKey('users.id', ondelete='SET NULL') | nullable=True |
| actor_email | String(255) | ? | ORM defaults |
| action | String(50) | ? | nullable=False |
| target | String(255) | ? | ORM defaults |
| detail | String(500) | ? | ORM defaults |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow; index=True |


#### `retrieval_embeddings` ? RetrievalEmbedding

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L1692).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| kind | String(30) | ? | nullable=False |
| ref | String(500) | ? | nullable=False |
| text_hash | String(64) | ? | nullable=False; index=True |
| vector | JSON | ? | nullable=False |
| model | String(200) | ? | nullable=False |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


Compound declarations: `(UniqueConstraint('text_hash', 'model', name='uq_retrieval_embedding_text_model'),)`.

#### `entities` ? Entity

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L1721).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False; index=True |
| data_source_id | Integer | ForeignKey('data_sources.id', ondelete='CASCADE') | nullable=False; index=True |
| name | String(255) | ? | nullable=False |
| business_name | String(255) | ? | nullable=True |
| grain | Text | ? | nullable=True |
| description | Text | ? | nullable=True |
| primary_object | String(500) | ? | nullable=True |
| source | String(20) | ? | nullable=False; default='inferred'; server_default='inferred' |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |
| updated_at | DateTime(timezone=True) | ? | default=datetime.utcnow; onupdate=datetime.utcnow |


Compound declarations: `(UniqueConstraint('data_source_id', 'name', name='uq_entity_name'),)`.

#### `workspace_nodes` ? WorkspaceNode

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L1764).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False; index=True |
| parent_id | Integer | ForeignKey('workspace_nodes.id', ondelete='CASCADE') | nullable=True; index=True |
| node_type | String(20) | ? | nullable=False; default='folder' |
| name | String(255) | ? | ORM defaults |
| report_id | Integer | ForeignKey('reports.id', ondelete='CASCADE') | nullable=True; unique=True; index=True |
| created_by | Integer | ForeignKey('users.id', ondelete='SET NULL') | nullable=True; index=True |
| position | Integer | ? | nullable=False; default=0 |
| published | Boolean | ? | nullable=False; default=False; server_default='0' |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


#### `workspace_folder_roles` ? WorkspaceFolderRole

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L1823).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| node_id | Integer | ForeignKey('workspace_nodes.id', ondelete='CASCADE') | nullable=False; index=True |
| role_id | Integer | ForeignKey('roles.id', ondelete='CASCADE') | nullable=False |


Compound declarations: `(UniqueConstraint('node_id', 'role_id', name='uq_workspace_folder_role'),)`.

#### `schedule_failures` ? ScheduleFailure

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L1862).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| kind | String(20) | ? | nullable=False |
| item_id | Integer | ? | nullable=False |
| attempts | Integer | ? | nullable=False; default=1 |
| next_attempt_at | DateTime(timezone=True) | ? | nullable=True; index=True |
| last_error | Text | ? | nullable=True |
| first_failed_at | DateTime(timezone=True) | ? | default=datetime.utcnow |
| updated_at | DateTime(timezone=True) | ? | default=datetime.utcnow; onupdate=datetime.utcnow |


Compound declarations: `(UniqueConstraint('kind', 'item_id', name='uq_schedule_failure_item'),)`.

#### `workspace_folder_grants` ? WorkspaceFolderGrant

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L1900).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False; index=True |
| node_id | Integer | ForeignKey('workspace_nodes.id', ondelete='CASCADE') | nullable=False; index=True |
| user_id | Integer | ForeignKey('users.id', ondelete='CASCADE') | nullable=True; index=True |
| role_id | Integer | ForeignKey('roles.id', ondelete='CASCADE') | nullable=True |
| org_unit_id | Integer | ForeignKey('org_units.id', ondelete='CASCADE') | nullable=True |
| level | String(10) | ? | nullable=False; default='view' |
| created_by | Integer | ForeignKey('users.id', ondelete='SET NULL') | nullable=True |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |


#### `dataflows` ? Dataflow

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L1957).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False; index=True |
| name | String(255) | ? | nullable=False |
| description | Text | ? | nullable=True |
| steps | JSON | ? | nullable=False; default=list |
| source_dataset_id | Integer | ForeignKey('datasets.id', ondelete='SET NULL') | nullable=True |
| join_dataset_ids | JSON | ? | nullable=False; default=list |
| refresh_interval_minutes | Integer | ? | nullable=True |
| created_by | Integer | ForeignKey('users.id', ondelete='SET NULL') | nullable=True |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow |
| last_run_at | DateTime(timezone=True) | ? | nullable=True |
| last_run_status | String(20) | ? | nullable=True |
| last_run_rows | Integer | ? | nullable=True |
| last_run_error | Text | ? | nullable=True |


#### `dataflow_capabilities` ? DataflowCapability

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L1999).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| dataflow_id | Integer | ForeignKey('dataflows.id', ondelete='CASCADE') | nullable=False; index=True |
| role_id | Integer | ForeignKey('roles.id', ondelete='CASCADE') | nullable=False |
| level | String(10) | ? | nullable=False; default='data' |


Compound declarations: `(UniqueConstraint('dataflow_id', 'role_id', name='uq_dataflow_capability'),)`.

#### `automation_runs` ? AutomationRun

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L2043).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| org_id | Integer | ForeignKey('organizations.id', ondelete='CASCADE') | nullable=False; index=True |
| created_by | Integer | ForeignKey('users.id', ondelete='SET NULL') | nullable=True; index=True |
| trigger | String(30) | ? | nullable=False; default='manual' |
| subject_type | String(30) | ? | nullable=True |
| subject_id | Integer | ? | nullable=True |
| status | String(20) | ? | nullable=False; default='pending'; index=True |
| result_report_id | Integer | ForeignKey('reports.id', ondelete='SET NULL') | nullable=True; index=True |
| result_report_name | String(255) | ? | nullable=True |
| proposal_path | String(20) | ? | nullable=True; index=True |
| widgets_accepted | Integer | ? | nullable=True |
| widgets_rejected | Integer | ? | nullable=True |
| rejection_reasons | JSON | ? | nullable=True |
| raw_proposals | JSON | ? | nullable=True |
| error | Text | ? | nullable=True |
| created_at | DateTime(timezone=True) | ? | default=datetime.utcnow; index=True |
| finished_at | DateTime(timezone=True) | ? | nullable=True |


ORM navigation: `steps: relationship('AutomationStep', back_populates='run', cascade='all, delete-orphan', order_by='AutomationStep.order')`.

#### `automation_steps` ? AutomationStep

Source: [AI_data_tool/data_analytics/backend/app/models/models.py](AI_data_tool/data_analytics/backend/app/models/models.py#L2118).


| Column | Type | Reference | Constraints / default / index |
| --- | --- | --- | --- |
| id | Integer | ? | primary_key=True |
| run_id | Integer | ForeignKey('automation_runs.id', ondelete='CASCADE') | nullable=False; index=True |
| name | String(40) | ? | nullable=False |
| order | Integer | ? | nullable=False |
| status | String(20) | ? | nullable=False; default='pending'; index=True |
| output_ref | Text | ? | nullable=True |
| error | Text | ? | nullable=True |
| attempts | Integer | ? | nullable=False; default=0 |
| next_attempt_at | DateTime(timezone=True) | ? | nullable=True; index=True |
| started_at | DateTime(timezone=True) | ? | nullable=True |
| finished_at | DateTime(timezone=True) | ? | nullable=True |


Compound declarations: `(UniqueConstraint('run_id', 'name', name='uq_automation_step_run_name'),)`.

ORM navigation: `run: relationship('AutomationRun', back_populates='steps')`.


### Migration chain

| Revision / purpose from filename | Parent | Source |
| --- | --- | --- |
| 0001_baseline | None | [AI_data_tool/data_analytics/backend/alembic/versions/0001_baseline.py](AI_data_tool/data_analytics/backend/alembic/versions/0001_baseline.py) |
| 0002_deliveries_tz | '0001_baseline' | [AI_data_tool/data_analytics/backend/alembic/versions/0002_deliveries_tz.py](AI_data_tool/data_analytics/backend/alembic/versions/0002_deliveries_tz.py) |
| 0003_feedback_evals | '0002_deliveries_tz' | [AI_data_tool/data_analytics/backend/alembic/versions/0003_feedback_evals.py](AI_data_tool/data_analytics/backend/alembic/versions/0003_feedback_evals.py) |
| 0004_retrieval_embeddings | '0003_feedback_evals' | [AI_data_tool/data_analytics/backend/alembic/versions/0004_retrieval_embeddings.py](AI_data_tool/data_analytics/backend/alembic/versions/0004_retrieval_embeddings.py) |
| 0005_entities | '0004_retrieval_embeddings' | [AI_data_tool/data_analytics/backend/alembic/versions/0005_entities.py](AI_data_tool/data_analytics/backend/alembic/versions/0005_entities.py) |
| 0006_embed_configs | '0005_entities' | [AI_data_tool/data_analytics/backend/alembic/versions/0006_embed_configs.py](AI_data_tool/data_analytics/backend/alembic/versions/0006_embed_configs.py) |
| 0007_quotas | '0006_embed_configs' | [AI_data_tool/data_analytics/backend/alembic/versions/0007_quotas.py](AI_data_tool/data_analytics/backend/alembic/versions/0007_quotas.py) |
| 0008_materializations | '0007_quotas' | [AI_data_tool/data_analytics/backend/alembic/versions/0008_materializations.py](AI_data_tool/data_analytics/backend/alembic/versions/0008_materializations.py) |
| 0009_workspace_nodes | '0008_materializations' | [AI_data_tool/data_analytics/backend/alembic/versions/0009_workspace_nodes.py](AI_data_tool/data_analytics/backend/alembic/versions/0009_workspace_nodes.py) |
| 0010_dataflows | '0009_workspace_nodes' | [AI_data_tool/data_analytics/backend/alembic/versions/0010_dataflows.py](AI_data_tool/data_analytics/backend/alembic/versions/0010_dataflows.py) |
| 0011_pinned_tiles | '0010_dataflows' | [AI_data_tool/data_analytics/backend/alembic/versions/0011_pinned_tiles.py](AI_data_tool/data_analytics/backend/alembic/versions/0011_pinned_tiles.py) |
| 0012_pin_layout_and_insights | '0011_pinned_tiles' | [AI_data_tool/data_analytics/backend/alembic/versions/0012_pin_layout_and_insights.py](AI_data_tool/data_analytics/backend/alembic/versions/0012_pin_layout_and_insights.py) |
| 0013_report_created_by | '0012_pin_layout_and_insights' | [AI_data_tool/data_analytics/backend/alembic/versions/0013_report_created_by.py](AI_data_tool/data_analytics/backend/alembic/versions/0013_report_created_by.py) |
| 0014_publish_and_user_grants | '0013_report_created_by' | [AI_data_tool/data_analytics/backend/alembic/versions/0014_publish_and_user_grants.py](AI_data_tool/data_analytics/backend/alembic/versions/0014_publish_and_user_grants.py) |
| 0015_recent_views | '0014_publish_and_user_grants' | [AI_data_tool/data_analytics/backend/alembic/versions/0015_recent_views.py](AI_data_tool/data_analytics/backend/alembic/versions/0015_recent_views.py) |
| 0016_org_units | '0015_recent_views' | [AI_data_tool/data_analytics/backend/alembic/versions/0016_org_units.py](AI_data_tool/data_analytics/backend/alembic/versions/0016_org_units.py) |
| 0017_agent_results | '0016_org_units' | [AI_data_tool/data_analytics/backend/alembic/versions/0017_agent_results.py](AI_data_tool/data_analytics/backend/alembic/versions/0017_agent_results.py) |
| 0018_report_versions | '0017_agent_results' | [AI_data_tool/data_analytics/backend/alembic/versions/0018_report_versions.py](AI_data_tool/data_analytics/backend/alembic/versions/0018_report_versions.py) |
| 0019_workspace_folder_grants | '0018_report_versions' | [AI_data_tool/data_analytics/backend/alembic/versions/0019_workspace_folder_grants.py](AI_data_tool/data_analytics/backend/alembic/versions/0019_workspace_folder_grants.py) |
| 0020_dataset_ownership | '0019_workspace_folder_grants' | [AI_data_tool/data_analytics/backend/alembic/versions/0020_dataset_ownership.py](AI_data_tool/data_analytics/backend/alembic/versions/0020_dataset_ownership.py) |
| 0021_schedule_failures | '0020_dataset_ownership' | [AI_data_tool/data_analytics/backend/alembic/versions/0021_schedule_failures.py](AI_data_tool/data_analytics/backend/alembic/versions/0021_schedule_failures.py) |
| 0022_dataset_custom_functions | '0021_schedule_failures' | [AI_data_tool/data_analytics/backend/alembic/versions/0022_dataset_custom_functions.py](AI_data_tool/data_analytics/backend/alembic/versions/0022_dataset_custom_functions.py) |
| 0023_custom_connectors | '0022_dataset_custom_functions' | [AI_data_tool/data_analytics/backend/alembic/versions/0023_custom_connectors.py](AI_data_tool/data_analytics/backend/alembic/versions/0023_custom_connectors.py) |
| 0024_boundary_sets | '0023_custom_connectors' | [AI_data_tool/data_analytics/backend/alembic/versions/0024_boundary_sets.py](AI_data_tool/data_analytics/backend/alembic/versions/0024_boundary_sets.py) |
| 0025_data_view_default | '0024_boundary_sets' | [AI_data_tool/data_analytics/backend/alembic/versions/0025_data_view_default.py](AI_data_tool/data_analytics/backend/alembic/versions/0025_data_view_default.py) |
| 0026_page_background | '0025_data_view_default' | [AI_data_tool/data_analytics/backend/alembic/versions/0026_page_background.py](AI_data_tool/data_analytics/backend/alembic/versions/0026_page_background.py) |
| 0027_prediction_models | '0026_page_background' | [AI_data_tool/data_analytics/backend/alembic/versions/0027_prediction_models.py](AI_data_tool/data_analytics/backend/alembic/versions/0027_prediction_models.py) |
| 0028_query_run_shape | '0027_prediction_models' | [AI_data_tool/data_analytics/backend/alembic/versions/0028_query_run_shape.py](AI_data_tool/data_analytics/backend/alembic/versions/0028_query_run_shape.py) |
| 0029_aggregate_datasets | '0028_query_run_shape' | [AI_data_tool/data_analytics/backend/alembic/versions/0029_aggregate_datasets.py](AI_data_tool/data_analytics/backend/alembic/versions/0029_aggregate_datasets.py) |
| 0030_automation_runs | '0029_aggregate_datasets' | [AI_data_tool/data_analytics/backend/alembic/versions/0030_automation_runs.py](AI_data_tool/data_analytics/backend/alembic/versions/0030_automation_runs.py) |
| 0031_report_origin | '0030_automation_runs' | [AI_data_tool/data_analytics/backend/alembic/versions/0031_report_origin.py](AI_data_tool/data_analytics/backend/alembic/versions/0031_report_origin.py) |
| 0032_automation_run_record | '0031_report_origin' | [AI_data_tool/data_analytics/backend/alembic/versions/0032_automation_run_record.py](AI_data_tool/data_analytics/backend/alembic/versions/0032_automation_run_record.py) |
| 0033_dataset_column_provenance | '0032_automation_run_record' | [AI_data_tool/data_analytics/backend/alembic/versions/0033_dataset_column_provenance.py](AI_data_tool/data_analytics/backend/alembic/versions/0033_dataset_column_provenance.py) |
| 0034_source_column_target | '0033_dataset_column_provenance' | [AI_data_tool/data_analytics/backend/alembic/versions/0034_source_column_target.py](AI_data_tool/data_analytics/backend/alembic/versions/0034_source_column_target.py) |
| 0035_page_layout_mode | '0034_source_column_target' | [AI_data_tool/data_analytics/backend/alembic/versions/0035_page_layout_mode.py](AI_data_tool/data_analytics/backend/alembic/versions/0035_page_layout_mode.py) |
| 0036_org_map_settings | '0035_page_layout_mode' | [AI_data_tool/data_analytics/backend/alembic/versions/0036_org_map_settings.py](AI_data_tool/data_analytics/backend/alembic/versions/0036_org_map_settings.py) |
| 0037_org_review_settings | '0036_org_map_settings' | [AI_data_tool/data_analytics/backend/alembic/versions/0037_org_review_settings.py](AI_data_tool/data_analytics/backend/alembic/versions/0037_org_review_settings.py) |



## 7. Backend Architecture and API Routes

`main.py` mounts 31 router objects from 29 router modules under `/api/v1`; analysis and metadata each have a secondary router. The endpoint inventory below is extracted from those decorated functions, including request arguments, declared response models or return forms, and directly visible authorization calls. A function with `body: dict` relies on manual validation; the inventory does not invent a stricter schema.

Key contracts and behavior:

| Endpoint (relative to /api/v1) | Request ? response | Main implementation and access |
|---|---|---|
| POST /auth/login | JSON email/password ? bearer token | auth.login; public credential check |
| GET /auth/me | bearer token ? UserOut with role/org information | active DB user resolved from JWT/API key |
| POST /datasets | multipart file, name, description ? DatasetOut | ingest, managed upload storage, columns/metadata; authenticated |
| POST /datasets/batch | files, name, description, separate/append mode ? per-item batch output | request/file caps, ingestion and validation |
| POST /data-sources/{id}/import | table/query and mode ? dataset | import or DirectQuery definition; org-admin dependency |
| POST /data-sources/{id}/sync | source id ? run information | background metadata synchronization; route-specific controls |
| POST /datasets/{id}/widget-data | widget_type, config, optional calculated_columns/report_id/parameters ? chart-shaped JSON | org/read access, quotas, semantics, RLS/CLS, import or DirectQuery |
| POST /datasets/{id}/analysis/run | analysis identifier and params ? handler-specific result | registry and secured frame; authenticated dataset reader |
| POST /datasets/{id}/suggest-dashboards | description/configuration ? validated proposals | profiling, model or deterministic insights, widget execution checks |
| POST /reports; POST /reports/{id}/pages | ReportCreate / PageCreate ? ReportOut / PageOut | report authoring and capability checks |
| POST/PATCH report widget routes | widget type/config/layout ? WidgetOut | report revision snapshot + edit capability; script authoring guard |
| POST /reports/{id}/publish | published boolean ? publication state | author/admin; optional high-severity review gate |
| POST /reports/{id}/versions/{version_id}/restore | identifiers ? restored/saved version IDs and note | recreates pages/widgets and saves current state |
| POST /agent/conversations; POST .../{cid}/ask | source or dataset scope; message ? run/result payload | ownership/scope, quota and native agent graph |
| POST /reports/{id}/pages/{page_id}/copilot | message/history context ? answer/actions | copilot action validation and report mutation path |
| POST /datasets/{id}/prediction-models | name,target,predictors,optional partition ? model metadata | data-authoring access; import only; artifact stays server-side |
| POST .../prediction-models/{model_id}/score | supplied rows or secured dataset rows ? predictions | dataset/org/feature/RLS checks |
| GET /shared/{token}; POST .../widget-data/{id} | secret URL token and saved widget id ? report/render data | token expiry/revocation, sensitivity and effective identity |
| GET /embed/report; POST /embed/widget-data/{id} | host token then embed session credential ? saved report/render data | embed origin/signature/audience checks |
| POST /semantic/query; GET /semantic/datasets/{id}/rows | aggregate specification or paging ? JSON/CSV | import-only governed frame, export policy, sensitivity and auditing |

The service layer is extensive, but not uniformly isolated from HTTP. Routes still assemble secure frames, calculate results, mutate ORM records and control transactions. Several services import router helpers; see section 23.

### Complete registered API inventory

Requests show declared parameters except database/request/auth dependencies. Body model fields are expanded below. Return forms are static expressions when no response model is declared; branches may differ. Direct checks are calls visible in the route, not a guarantee every branch invokes every helper. Shared helpers may add checks. See sections 8 and 12 for effective authorization.

#### admin.py

| Method | Full URL | Purpose | Request contract | Response | Authorization boundary | Implementation |
| --- | --- | --- | --- | --- | --- | --- |
| GET | /api/v1/admin/roles | list roles | path/auth only | list[RoleOut] | Depends(require_org_admin) | list_roles ? [AI_data_tool/data_analytics/backend/app/routers/admin.py](AI_data_tool/data_analytics/backend/app/routers/admin.py#L31) |
| POST | /api/v1/admin/roles | create role | body: RoleCreate | RoleOut | Depends(require_org_admin) | create_role ? [AI_data_tool/data_analytics/backend/app/routers/admin.py](AI_data_tool/data_analytics/backend/app/routers/admin.py#L37) |
| PATCH | /api/v1/admin/roles/{role_id} | update role | role_id: int; body: RoleUpdate | RoleOut | Depends(require_org_admin); Direct checks: check_org | update_role ? [AI_data_tool/data_analytics/backend/app/routers/admin.py](AI_data_tool/data_analytics/backend/app/routers/admin.py#L46) |
| DELETE | /api/v1/admin/roles/{role_id} | delete role | role_id: int | empty response; HTTP 204 | Depends(require_org_admin); Direct checks: check_org | delete_role ? [AI_data_tool/data_analytics/backend/app/routers/admin.py](AI_data_tool/data_analytics/backend/app/routers/admin.py#L59) |
| GET | /api/v1/admin/users | list users | path/auth only | list[UserOut] | Depends(require_org_admin) | list_users ? [AI_data_tool/data_analytics/backend/app/routers/admin.py](AI_data_tool/data_analytics/backend/app/routers/admin.py#L79) |
| POST | /api/v1/admin/users | create user | body: UserCreate | UserOut | Depends(require_org_admin); Direct checks: check_org | create_user ? [AI_data_tool/data_analytics/backend/app/routers/admin.py](AI_data_tool/data_analytics/backend/app/routers/admin.py#L88) |
| POST | /api/v1/admin/users/bulk | bulk create users ? Provision many users at once (CSV import from the admin UI). Partial success: every valid row is created and every invalid one is reported with its reason, so one bad line never sinks the whole upload. Roles are matched by name within the a? | body: BulkUserCreate | object {created_count, created, errors} | Depends(require_org_admin) | bulk_create_users ? [AI_data_tool/data_analytics/backend/app/routers/admin.py](AI_data_tool/data_analytics/backend/app/routers/admin.py#L104) |
| PATCH | /api/v1/admin/users/{user_id} | update user | user_id: int; body: UserUpdate | UserOut | Depends(require_org_admin); Direct checks: check_org | update_user ? [AI_data_tool/data_analytics/backend/app/routers/admin.py](AI_data_tool/data_analytics/backend/app/routers/admin.py#L152) |
| DELETE | /api/v1/admin/users/{user_id} | delete user | user_id: int | empty response; HTTP 204 | Depends(require_org_admin); Direct checks: check_org | delete_user ? [AI_data_tool/data_analytics/backend/app/routers/admin.py](AI_data_tool/data_analytics/backend/app/routers/admin.py#L173) |
| GET | /api/v1/admin/row-security-rules | list rules | path/auth only | list[RowSecurityRuleOut] | Depends(require_org_admin) | list_rules ? [AI_data_tool/data_analytics/backend/app/routers/admin.py](AI_data_tool/data_analytics/backend/app/routers/admin.py#L231) |
| POST | /api/v1/admin/row-security-rules | create rule | body: RowSecurityRuleCreate | RowSecurityRuleOut | Depends(require_org_admin); Direct checks: check_org | create_rule ? [AI_data_tool/data_analytics/backend/app/routers/admin.py](AI_data_tool/data_analytics/backend/app/routers/admin.py#L240) |
| POST | /api/v1/admin/rls-rules/auto-generate | auto generate rls rules ? Propose (and optionally create) row-security rules from column semantics/ naming (S0c). Proposing needs only a dataset; applying needs a role too, since a RowSecurityRule is always (role, dataset). Checked proposals for the SAME role+datase? | body: RlsAutoGenerateRequest | object {proposals} / object {proposals, created, skipped, reason} / object {proposals, created, skipped} | Depends(require_org_admin); Direct checks: check_org | auto_generate_rls_rules ? [AI_data_tool/data_analytics/backend/app/routers/admin.py](AI_data_tool/data_analytics/backend/app/routers/admin.py#L302) |
| GET | /api/v1/admin/row-security-rules/preflight | rule preflight ? What a rule reads, and which of those columns the role cannot see. | role_id: int; dataset_id: int; filter_expr: str | object {columns, denied} | Depends(require_org_admin); Direct checks: check_org | rule_preflight ? [AI_data_tool/data_analytics/backend/app/routers/admin.py](AI_data_tool/data_analytics/backend/app/routers/admin.py#L379) |
| PATCH | /api/v1/admin/row-security-rules/{rule_id} | update rule | rule_id: int; body: RowSecurityRuleUpdate | RowSecurityRuleOut | Depends(require_org_admin) | update_rule ? [AI_data_tool/data_analytics/backend/app/routers/admin.py](AI_data_tool/data_analytics/backend/app/routers/admin.py#L422) |
| DELETE | /api/v1/admin/row-security-rules/{rule_id} | delete rule | rule_id: int | empty response; HTTP 204 | Depends(require_org_admin) | delete_rule ? [AI_data_tool/data_analytics/backend/app/routers/admin.py](AI_data_tool/data_analytics/backend/app/routers/admin.py#L441) |
| GET | /api/v1/admin/audit-log | list audit log ? The org's audit trail, newest first. Admin-only and org-scoped: the log records an org's own actions and is readable by that org's admins alone. | limit: int = 200 | list comprehension | Depends(require_org_admin) | list_audit_log ? [AI_data_tool/data_analytics/backend/app/routers/admin.py](AI_data_tool/data_analytics/backend/app/routers/admin.py#L450) |
| GET | /api/v1/admin/column-security-rules | list column rules | path/auth only | list comprehension | Depends(require_org_admin) | list_column_rules ? [AI_data_tool/data_analytics/backend/app/routers/admin.py](AI_data_tool/data_analytics/backend/app/routers/admin.py#L473) |
| POST | /api/v1/admin/column-security-rules | create column rule | body: dict | object {id}; HTTP 201 | Depends(require_org_admin); Direct checks: check_org | create_column_rule ? [AI_data_tool/data_analytics/backend/app/routers/admin.py](AI_data_tool/data_analytics/backend/app/routers/admin.py#L484) |
| DELETE | /api/v1/admin/column-security-rules/{rule_id} | delete column rule | rule_id: int | empty response; HTTP 204 | Depends(require_org_admin); Direct checks: check_org | delete_column_rule ? [AI_data_tool/data_analytics/backend/app/routers/admin.py](AI_data_tool/data_analytics/backend/app/routers/admin.py#L502) |
| GET | /api/v1/admin/admin-audit | list admin audit ? Read-only trail of security-relevant admin mutations, newest first. Org-scoped and admin-only, same as `/audit-log`; `action` filters by exact action name, `q` by a case-insensitive substring of the target. | limit: int = 200; action: str &#124; None = None; q: str &#124; None = None | list comprehension | Depends(require_org_admin) | list_admin_audit ? [AI_data_tool/data_analytics/backend/app/routers/admin.py](AI_data_tool/data_analytics/backend/app/routers/admin.py#L516) |
| GET | /api/v1/admin/monitoring/jobs | list monitoring jobs ? Every scheduled thing in the org, one uniform row shape per kind. | path/auth only | jobs | Depends(require_org_admin) | list_monitoring_jobs ? [AI_data_tool/data_analytics/backend/app/routers/admin.py](AI_data_tool/data_analytics/backend/app/routers/admin.py#L551) |
| GET | /api/v1/admin/monitoring/deliveries | list monitoring deliveries ? The org's delivery log across every report and alert, newest first -- the per-report `GET /reports/{id}/deliveries` view unscoped from one report. Report names come back joined because a bare report_id would force the page into N follow-up ? | limit: int = 200 | list comprehension | Depends(require_org_admin) | list_monitoring_deliveries ? [AI_data_tool/data_analytics/backend/app/routers/admin.py](AI_data_tool/data_analytics/backend/app/routers/admin.py#L621) |
| GET | /api/v1/admin/org-units | list org units ? The whole tree, flat. The client nests it -- one query beats N. | path/auth only | list comprehension | Depends(require_org_admin) | list_org_units ? [AI_data_tool/data_analytics/backend/app/routers/admin.py](AI_data_tool/data_analytics/backend/app/routers/admin.py#L661) |
| POST | /api/v1/admin/org-units | create org unit | body: dict | _unit_out(...); HTTP 201 | Depends(require_org_admin) | create_org_unit ? [AI_data_tool/data_analytics/backend/app/routers/admin.py](AI_data_tool/data_analytics/backend/app/routers/admin.py#L677) |
| PATCH | /api/v1/admin/org-units/{unit_id} | update org unit | unit_id: int; body: dict | _unit_out(...) | Depends(require_org_admin) | update_org_unit ? [AI_data_tool/data_analytics/backend/app/routers/admin.py](AI_data_tool/data_analytics/backend/app/routers/admin.py#L707) |
| DELETE | /api/v1/admin/org-units/{unit_id} | delete org unit ? Deleting a unit deletes its subtree (FK cascade) and every placement in it. Said plainly in the UI confirmation, because it is not recoverable. | unit_id: int | empty response; HTTP 204 | Depends(require_org_admin) | delete_org_unit ? [AI_data_tool/data_analytics/backend/app/routers/admin.py](AI_data_tool/data_analytics/backend/app/routers/admin.py#L760) |
| GET | /api/v1/admin/users/{user_id}/org-units | list user org units | user_id: int | list comprehension | Depends(require_org_admin); Direct checks: check_org | list_user_org_units ? [AI_data_tool/data_analytics/backend/app/routers/admin.py](AI_data_tool/data_analytics/backend/app/routers/admin.py#L774) |
| PUT | /api/v1/admin/users/{user_id}/org-units | set user org units ? Replace this user's placements wholesale. An empty list clears them, which means MYSCOPE() no longer resolves for that user and any rule using it fails closed -- they see nothing rather than everything. | user_id: int; body: dict | object {org_unit_ids} | Depends(require_org_admin); Direct checks: check_org | set_user_org_units ? [AI_data_tool/data_analytics/backend/app/routers/admin.py](AI_data_tool/data_analytics/backend/app/routers/admin.py#L790) |


#### agent.py

| Method | Full URL | Purpose | Request contract | Response | Authorization boundary | Implementation |
| --- | --- | --- | --- | --- | --- | --- |
| POST | /api/v1/agent/conversations | create conversation | body: ConversationIn | object {id, title} | Depends(get_current_user); Direct checks: check_org, require_dataset_read | create_conversation ? [AI_data_tool/data_analytics/backend/app/routers/agent.py](AI_data_tool/data_analytics/backend/app/routers/agent.py#L160) |
| GET | /api/v1/agent/conversations | list conversations | path/auth only | list comprehension | Depends(get_current_user) | list_conversations ? [AI_data_tool/data_analytics/backend/app/routers/agent.py](AI_data_tool/data_analytics/backend/app/routers/agent.py#L199) |
| GET | /api/v1/agent/conversations/{cid}/messages | list messages ? The thread, oldest first, each assistant turn with the run behind it -- answer status, SQL, result snapshots -- so a reopened conversation redraws exactly what was shown, grids included. Before this the pane resumed the server thread by id ? | cid: int | list comprehension | Depends(get_current_user) | list_messages ? [AI_data_tool/data_analytics/backend/app/routers/agent.py](AI_data_tool/data_analytics/backend/app/routers/agent.py#L218) |
| PATCH | /api/v1/agent/conversations/{cid} | rename conversation | cid: int; body: TitleIn | object {id, title} | Depends(get_current_user) | rename_conversation ? [AI_data_tool/data_analytics/backend/app/routers/agent.py](AI_data_tool/data_analytics/backend/app/routers/agent.py#L244) |
| DELETE | /api/v1/agent/conversations/{cid} | delete conversation ? Messages cascade with the thread; the runs keep their evidence for the eval gate and merely lose their conversation_id (FK SET NULL). | cid: int | empty response; HTTP 204 | Depends(get_current_user) | delete_conversation ? [AI_data_tool/data_analytics/backend/app/routers/agent.py](AI_data_tool/data_analytics/backend/app/routers/agent.py#L257) |
| POST | /api/v1/agent/conversations/{cid}/ask | ask | cid: int; body: AskIn | object {run_id, status, answer, intent, error, **spread} | Depends(get_current_user); Direct checks: check_org | ask ? [AI_data_tool/data_analytics/backend/app/routers/agent.py](AI_data_tool/data_analytics/backend/app/routers/agent.py#L267) |
| GET | /api/v1/agent/runs/{run_id} | run detail | run_id: int | object {id, status, question, intent, answer, error, plan, ms, context_objects, presentation, steps} | Depends(get_current_user); Direct checks: check_org | run_detail ? [AI_data_tool/data_analytics/backend/app/routers/agent.py](AI_data_tool/data_analytics/backend/app/routers/agent.py#L317) |
| GET | /api/v1/agent/runs/{run_id}/export | export run ? One answer's result as a file. Same ownership rule as /runs/{id}; the rows come from the stored snapshot, so what downloads is exactly what the chat showed -- same RLS, same cap -- in a different format. CSV stays client-side (the browser a? | run_id: int; format: str = 'xlsx' | StreamingResponse(...) | Depends(get_current_user); Direct checks: check_org | export_run ? [AI_data_tool/data_analytics/backend/app/routers/agent.py](AI_data_tool/data_analytics/backend/app/routers/agent.py#L350) |
| POST | /api/v1/agent/conversations/{cid}/feedback | submit feedback ? 👍/👎 on an agent answer. Owner-only -- same-org, different-user is a 404 just like /ask and /runs/{id}, because AgentStep.sql (reachable via run_id) carries the asker's RLS-filtered results, not just the rating. | cid: int; body: FeedbackIn | object {id, run_id, rating, comment} | Depends(get_current_user); Direct checks: check_org | submit_feedback ? [AI_data_tool/data_analytics/backend/app/routers/agent.py](AI_data_tool/data_analytics/backend/app/routers/agent.py#L391) |
| GET | /api/v1/agent/row-policies | list row policies | source_id: int | list comprehension | Depends(require_org_admin); Direct checks: check_org | list_row_policies ? [AI_data_tool/data_analytics/backend/app/routers/agent.py](AI_data_tool/data_analytics/backend/app/routers/agent.py#L432) |
| POST | /api/v1/agent/row-policies | create row policy | body: RowPolicyIn | object {id, source_object_id, object_name, role_id, role_name, predicate} | Depends(require_org_admin); Direct checks: check_org | create_row_policy ? [AI_data_tool/data_analytics/backend/app/routers/agent.py](AI_data_tool/data_analytics/backend/app/routers/agent.py#L450) |
| DELETE | /api/v1/agent/row-policies/{policy_id} | delete row policy | policy_id: int | empty response; HTTP 204 | Depends(require_org_admin); Direct checks: check_org | delete_row_policy ? [AI_data_tool/data_analytics/backend/app/routers/agent.py](AI_data_tool/data_analytics/backend/app/routers/agent.py#L494) |


#### analysis.py

| Method | Full URL | Purpose | Request contract | Response | Authorization boundary | Implementation |
| --- | --- | --- | --- | --- | --- | --- |
| POST | /api/v1/analysis/narrate | narrate finding ? Guarded LLM polish for one finding's sentence -- display-only. | body: NarrateRequest | object {sentence} | Depends(get_current_user) | narrate_finding ? [AI_data_tool/data_analytics/backend/app/routers/analysis.py](AI_data_tool/data_analytics/backend/app/routers/analysis.py#L43) |
| GET | /api/v1/analysis/registry | get analysis registry ? A4: the machine-readable analysis tool catalogue -- name, description, params schema, result kind for every registered analysis. Org-authenticated only (any logged-in user may discover what analyses exist; there is no per-dataset or admin-o? | path/auth only | object {analyses} | Depends(get_current_user) | get_analysis_registry ? [AI_data_tool/data_analytics/backend/app/routers/analysis.py](AI_data_tool/data_analytics/backend/app/routers/analysis.py#L59) |
| POST | /api/v1/datasets/{dataset_id}/analysis | run analysis | dataset_id: int; req: AnalysisRequest | as_response(...) | Depends(get_current_user); Direct checks: check_org | run_analysis ? [AI_data_tool/data_analytics/backend/app/routers/analysis.py](AI_data_tool/data_analytics/backend/app/routers/analysis.py#L96) |
| GET | /api/v1/datasets/{dataset_id}/analysis | get analysis | dataset_id: int | as_response(...) | Depends(get_current_user); Direct checks: check_org | get_analysis ? [AI_data_tool/data_analytics/backend/app/routers/analysis.py](AI_data_tool/data_analytics/backend/app/routers/analysis.py#L181) |
| POST | /api/v1/datasets/{dataset_id}/segment | run segment ? A2: KMeans segmentation over the SECURED base frame. Always computed live (never cached) -- unlike /analysis there is no shared AnalysisResult row to poison across roles, so this sidesteps that cache-vs-RLS problem entirely rather than need? | dataset_id: int; req: SegmentRequest | contract.to_dict(...) | Depends(get_current_user) | run_segment ? [AI_data_tool/data_analytics/backend/app/routers/analysis.py](AI_data_tool/data_analytics/backend/app/routers/analysis.py#L216) |
| POST | /api/v1/datasets/{dataset_id}/association-rules | run association rules ? Which values travel together, over the SECURED base frame. | dataset_id: int; req: AssociationRulesRequest | contract.to_dict(...) | Depends(get_current_user) | run_association_rules ? [AI_data_tool/data_analytics/backend/app/routers/analysis.py](AI_data_tool/data_analytics/backend/app/routers/analysis.py#L249) |
| POST | /api/v1/datasets/{dataset_id}/key-influencers | run key influencers ? Which factors move an outcome, over the RLS-filtered base frame. | dataset_id: int; req: KeyInfluencersRequest | contract.to_dict(...) | Depends(get_current_user); Direct checks: check_org | run_key_influencers ? [AI_data_tool/data_analytics/backend/app/routers/analysis.py](AI_data_tool/data_analytics/backend/app/routers/analysis.py#L288) |
| POST | /api/v1/datasets/{dataset_id}/statistics/compare-groups | run compare groups ? Welch's t-test or one-way ANOVA over the RLS-filtered base frame. | dataset_id: int; req: CompareGroupsRequest | res.to_dict(...) | Depends(get_current_user) | run_compare_groups ? [AI_data_tool/data_analytics/backend/app/routers/analysis.py](AI_data_tool/data_analytics/backend/app/routers/analysis.py#L407) |
| POST | /api/v1/datasets/{dataset_id}/statistics/independence | run independence ? Chi-square test of independence over the RLS-filtered base frame. | dataset_id: int; req: IndependenceRequest | res.to_dict(...) | Depends(get_current_user) | run_independence ? [AI_data_tool/data_analytics/backend/app/routers/analysis.py](AI_data_tool/data_analytics/backend/app/routers/analysis.py#L424) |
| POST | /api/v1/datasets/{dataset_id}/statistics/correlation | run correlation test ? Pearson or Spearman correlation with a p-value, over the secured frame. | dataset_id: int; req: CorrelationTestRequest | res.to_dict(...) | Depends(get_current_user) | run_correlation_test ? [AI_data_tool/data_analytics/backend/app/routers/analysis.py](AI_data_tool/data_analytics/backend/app/routers/analysis.py#L441) |
| POST | /api/v1/datasets/{dataset_id}/statistics/regression | run regression ? Ordinary least squares over the RLS-filtered base frame. | dataset_id: int; req: RegressionRequest | res.to_dict(...) | Depends(get_current_user) | run_regression ? [AI_data_tool/data_analytics/backend/app/routers/analysis.py](AI_data_tool/data_analytics/backend/app/routers/analysis.py#L459) |
| POST | /api/v1/datasets/{dataset_id}/statistics/glm-logistic | run glm logistic ? Logistic regression over the RLS-filtered base frame. | dataset_id: int; req: GlmLogisticRequest | res.to_dict(...) | Depends(get_current_user) | run_glm_logistic ? [AI_data_tool/data_analytics/backend/app/routers/analysis.py](AI_data_tool/data_analytics/backend/app/routers/analysis.py#L475) |
| POST | /api/v1/datasets/{dataset_id}/statistics/mixed-model | run mixed model ? Random-intercept mixed model over the RLS-filtered base frame. | dataset_id: int; req: MixedModelRequest | res.to_dict(...) | Depends(get_current_user) | run_mixed_model ? [AI_data_tool/data_analytics/backend/app/routers/analysis.py](AI_data_tool/data_analytics/backend/app/routers/analysis.py#L493) |
| POST | /api/v1/datasets/{dataset_id}/statistics/survival | run survival ? Cox proportional hazards over the RLS-filtered base frame. | dataset_id: int; req: SurvivalRequest | res.to_dict(...) | Depends(get_current_user) | run_survival ? [AI_data_tool/data_analytics/backend/app/routers/analysis.py](AI_data_tool/data_analytics/backend/app/routers/analysis.py#L514) |
| POST | /api/v1/datasets/{dataset_id}/statistics/pairwise | run pairwise ? Pairwise group comparisons with multiple-comparison correction. | dataset_id: int; req: PairwiseRequest | res.to_dict(...) | Depends(get_current_user) | run_pairwise ? [AI_data_tool/data_analytics/backend/app/routers/analysis.py](AI_data_tool/data_analytics/backend/app/routers/analysis.py#L533) |
| POST | /api/v1/datasets/{dataset_id}/difference-check | difference check endpoint ? "Is this difference real?" for two bars of a chart (Phase 7.2). | dataset_id: int; body: dict | await asyncio.to_thread(_run) | Depends(get_current_user); Direct checks: require_dataset_read | difference_check_endpoint ? [AI_data_tool/data_analytics/backend/app/routers/analysis.py](AI_data_tool/data_analytics/backend/app/routers/analysis.py#L594) |
| POST | /api/v1/datasets/{dataset_id}/analysis/run | run catalogued analysis ? Run any runnable analysis in the catalogue over this dataset's secured frame. | dataset_id: int; req: RunAnalysisRequest | object {analysis, result_kind, params, result} | Depends(get_current_user); Direct checks: require_dataset_read | run_catalogued_analysis ? [AI_data_tool/data_analytics/backend/app/routers/analysis.py](AI_data_tool/data_analytics/backend/app/routers/analysis.py#L628) |


#### auth.py

| Method | Full URL | Purpose | Request contract | Response | Authorization boundary | Implementation |
| --- | --- | --- | --- | --- | --- | --- |
| POST | /api/v1/auth/login | login | body: LoginRequest | TokenOut | No auth dependency declared; protocol/token logic may be inside handler | login ? [AI_data_tool/data_analytics/backend/app/routers/auth.py](AI_data_tool/data_analytics/backend/app/routers/auth.py#L24) |
| GET | /api/v1/auth/me | me | path/auth only | UserOut | Depends(get_current_user) | me ? [AI_data_tool/data_analytics/backend/app/routers/auth.py](AI_data_tool/data_analytics/backend/app/routers/auth.py#L42) |
| GET | /api/v1/auth/api-keys | list api keys | path/auth only | list comprehension | Depends(get_current_user) | list_api_keys ? [AI_data_tool/data_analytics/backend/app/routers/auth.py](AI_data_tool/data_analytics/backend/app/routers/auth.py#L63) |
| POST | /api/v1/auth/api-keys | create api key ? Issue a key. The `key` in the response is shown ONCE and cannot be recovered — store it now. It authenticates as this user until revoked. | body: ApiKeyCreate | object {**spread, key}; HTTP 201 | Depends(get_current_user) | create_api_key ? [AI_data_tool/data_analytics/backend/app/routers/auth.py](AI_data_tool/data_analytics/backend/app/routers/auth.py#L71) |
| DELETE | /api/v1/auth/api-keys/{key_id} | revoke api key | key_id: int | empty response; HTTP 204 | Depends(get_current_user) | revoke_api_key ? [AI_data_tool/data_analytics/backend/app/routers/auth.py](AI_data_tool/data_analytics/backend/app/routers/auth.py#L87) |
| GET | /api/v1/auth/my-scope | my scope ? What MYSCOPE() resolves to for the CALLER: their org-unit placements expanded to every descendant. | path/auth only | object {placed, values, is_org_admin} | Depends(get_current_user) | my_scope ? [AI_data_tool/data_analytics/backend/app/routers/auth.py](AI_data_tool/data_analytics/backend/app/routers/auth.py#L99) |


#### authz.py

| Method | Full URL | Purpose | Request contract | Response | Authorization boundary | Implementation |
| --- | --- | --- | --- | --- | --- | --- |
| POST | /api/v1/authz/decisions | decisions ? `{"checks": [{"resource": "report"&#124;"dataset", "id": 5, "action": "edit", "column"?: "x"}]}` -> `{"decisions": [{...check, allowed, reason, level?, sensitivity?}]}` in the same order. | body: dict | object {decisions} | Depends(get_current_user) | decisions ? [AI_data_tool/data_analytics/backend/app/routers/authz.py](AI_data_tool/data_analytics/backend/app/routers/authz.py#L79) |


#### boundary_sets.py

| Method | Full URL | Purpose | Request contract | Response | Authorization boundary | Implementation |
| --- | --- | --- | --- | --- | --- | --- |
| GET | /api/v1/boundary-sets | list boundary sets | path/auth only | list comprehension | Depends(get_current_user) | list_boundary_sets ? [AI_data_tool/data_analytics/backend/app/routers/boundary_sets.py](AI_data_tool/data_analytics/backend/app/routers/boundary_sets.py#L65) |
| GET | /api/v1/boundary-sets/packs | list boundary packs ? Starter packs this deployment ships (Egypt governorates, US states...). Metadata only; the geometry is read when a pack is installed. | path/auth only | list_packs(...) | Depends(get_current_user) | list_boundary_packs ? [AI_data_tool/data_analytics/backend/app/routers/boundary_sets.py](AI_data_tool/data_analytics/backend/app/routers/boundary_sets.py#L75) |
| POST | /api/v1/boundary-sets/packs/{pack_id}/install | install boundary pack ? Install a pack as an ordinary boundary set of the caller's org. | pack_id: str; body: dict &#124; None = None | object {**spread, sample_names}; HTTP 201 | Depends(get_current_user) | install_boundary_pack ? [AI_data_tool/data_analytics/backend/app/routers/boundary_sets.py](AI_data_tool/data_analytics/backend/app/routers/boundary_sets.py#L82) |
| GET | /api/v1/boundary-sets/{set_id} | get boundary set ? The geometry, verbatim. This is what the browser draws. | set_id: int | object {**spread, geometry} | Depends(get_current_user) | get_boundary_set ? [AI_data_tool/data_analytics/backend/app/routers/boundary_sets.py](AI_data_tool/data_analytics/backend/app/routers/boundary_sets.py#L123) |
| POST | /api/v1/boundary-sets | create boundary set | body: dict | object {**spread, sample_names}; HTTP 201 | Depends(get_current_user) | create_boundary_set ? [AI_data_tool/data_analytics/backend/app/routers/boundary_sets.py](AI_data_tool/data_analytics/backend/app/routers/boundary_sets.py#L131) |
| DELETE | /api/v1/boundary-sets/{set_id} | delete boundary set | set_id: int | empty response; HTTP 204 | Depends(get_current_user) | delete_boundary_set ? [AI_data_tool/data_analytics/backend/app/routers/boundary_sets.py](AI_data_tool/data_analytics/backend/app/routers/boundary_sets.py#L197) |
| PUT | /api/v1/boundary-sets/{set_id}/pins | set boundary pins ? Pin data values to regions: `{"pins": {"England": 12, ...}}`, value -> feature index. Replaces the set's pins wholesale. | set_id: int; body: dict | object {id, pins} | Depends(get_current_user) | set_boundary_pins ? [AI_data_tool/data_analytics/backend/app/routers/boundary_sets.py](AI_data_tool/data_analytics/backend/app/routers/boundary_sets.py#L217) |


#### custom_connectors.py

| Method | Full URL | Purpose | Request contract | Response | Authorization boundary | Implementation |
| --- | --- | --- | --- | --- | --- | --- |
| GET | /api/v1/custom-connectors | list custom connectors | path/auth only | list[CustomConnectorOut] | Depends(require_org_admin) | list_custom_connectors ? [AI_data_tool/data_analytics/backend/app/routers/custom_connectors.py](AI_data_tool/data_analytics/backend/app/routers/custom_connectors.py#L32) |
| POST | /api/v1/custom-connectors | create custom connector | body: CustomConnectorCreate | CustomConnectorOut | Depends(require_org_admin) | create_custom_connector ? [AI_data_tool/data_analytics/backend/app/routers/custom_connectors.py](AI_data_tool/data_analytics/backend/app/routers/custom_connectors.py#L40) |
| PUT | /api/v1/custom-connectors/{cc_id} | update custom connector | cc_id: int; body: CustomConnectorUpdate | CustomConnectorOut | Depends(require_org_admin) | update_custom_connector ? [AI_data_tool/data_analytics/backend/app/routers/custom_connectors.py](AI_data_tool/data_analytics/backend/app/routers/custom_connectors.py#L63) |
| DELETE | /api/v1/custom-connectors/{cc_id} | delete custom connector | cc_id: int | empty response; HTTP 204 | Depends(require_org_admin) | delete_custom_connector ? [AI_data_tool/data_analytics/backend/app/routers/custom_connectors.py](AI_data_tool/data_analytics/backend/app/routers/custom_connectors.py#L115) |


#### data_sources.py

| Method | Full URL | Purpose | Request contract | Response | Authorization boundary | Implementation |
| --- | --- | --- | --- | --- | --- | --- |
| GET | /api/v1/data-sources | list data sources | path/auth only | list[DataSourceOut] | Depends(get_current_user) | list_data_sources ? [AI_data_tool/data_analytics/backend/app/routers/data_sources.py](AI_data_tool/data_analytics/backend/app/routers/data_sources.py#L109) |
| POST | /api/v1/data-sources | create data source | body: DataSourceCreate | DataSourceOut | Depends(get_current_user); Direct checks: _require_known_connector | create_data_source ? [AI_data_tool/data_analytics/backend/app/routers/data_sources.py](AI_data_tool/data_analytics/backend/app/routers/data_sources.py#L129) |
| GET | /api/v1/data-sources/connectors | list connectors ? The connector catalog for the connection UI — labels, icons, categories and per-connector config-field specs, plus this org's custom connector presets. The single source of truth the frontend renders from. No secrets, no dialects. | path/auth only | connectors.catalog_payload(...) | Depends(get_current_user) | list_connectors ? [AI_data_tool/data_analytics/backend/app/routers/data_sources.py](AI_data_tool/data_analytics/backend/app/routers/data_sources.py#L207) |
| GET | /api/v1/data-sources/{ds_id}/index-advice | index advice for source ? Which filter columns this source has been queried on, and which of them have no index -- from the platform's own query log, never from the SQL. | ds_id: int; days: int = 30 | out | Depends(get_current_user); Direct checks: check_org | index_advice_for_source ? [AI_data_tool/data_analytics/backend/app/routers/data_sources.py](AI_data_tool/data_analytics/backend/app/routers/data_sources.py#L224) |
| GET | /api/v1/data-sources/{ds_id} | get data source | ds_id: int | DataSourceOut | Depends(get_current_user); Direct checks: check_org | get_data_source ? [AI_data_tool/data_analytics/backend/app/routers/data_sources.py](AI_data_tool/data_analytics/backend/app/routers/data_sources.py#L269) |
| PUT | /api/v1/data-sources/{ds_id} | update data source | ds_id: int; body: DataSourceUpdate | DataSourceOut | Depends(get_current_user); Direct checks: _require_known_connector, check_org | update_data_source ? [AI_data_tool/data_analytics/backend/app/routers/data_sources.py](AI_data_tool/data_analytics/backend/app/routers/data_sources.py#L279) |
| DELETE | /api/v1/data-sources/{ds_id} | delete data source | ds_id: int | empty response; HTTP 204 | Depends(get_current_user); Direct checks: check_org | delete_data_source ? [AI_data_tool/data_analytics/backend/app/routers/data_sources.py](AI_data_tool/data_analytics/backend/app/routers/data_sources.py#L340) |
| POST | /api/v1/data-sources/{ds_id}/test | test data source | ds_id: int | result | Depends(get_current_user); Direct checks: check_org | test_data_source ? [AI_data_tool/data_analytics/backend/app/routers/data_sources.py](AI_data_tool/data_analytics/backend/app/routers/data_sources.py#L349) |
| GET | /api/v1/data-sources/{ds_id}/schema | get schema | ds_id: int | object {tables} | Depends(get_current_user); Direct checks: check_org | get_schema ? [AI_data_tool/data_analytics/backend/app/routers/data_sources.py](AI_data_tool/data_analytics/backend/app/routers/data_sources.py#L361) |
| POST | /api/v1/data-sources/{ds_id}/preview | preview data | ds_id: int; req: TablePreviewRequest | result | Depends(require_org_admin); Direct checks: check_org | preview_data ? [AI_data_tool/data_analytics/backend/app/routers/data_sources.py](AI_data_tool/data_analytics/backend/app/routers/data_sources.py#L374) |
| POST | /api/v1/data-sources/{ds_id}/import | import dataset | ds_id: int; req: ImportRequest | object {id, name, row_count, col_count, mode} | Depends(require_org_admin); Direct checks: check_org | import_dataset ? [AI_data_tool/data_analytics/backend/app/routers/data_sources.py](AI_data_tool/data_analytics/backend/app/routers/data_sources.py#L387) |
| POST | /api/v1/data-sources/{ds_id}/similar-datasets | find similar datasets ? Datasets already built from this connection that cover these columns. | ds_id: int; body: SimilarDatasetsRequest | object {matches} | Depends(get_current_user); Direct checks: check_org | find_similar_datasets ? [AI_data_tool/data_analytics/backend/app/routers/data_sources.py](AI_data_tool/data_analytics/backend/app/routers/data_sources.py#L620) |
| GET | /api/v1/data-sources/{ds_id}/tables/{table}/columns | get table columns ? One table's columns from the live connection, for the builder's pickers. | ds_id: int; table: str | await asyncio.to_thread(_run) | Depends(get_current_user); Direct checks: check_org | get_table_columns ? [AI_data_tool/data_analytics/backend/app/routers/data_sources.py](AI_data_tool/data_analytics/backend/app/routers/data_sources.py#L663) |
| GET | /api/v1/data-sources/{ds_id}/functions | get functions ? The connection's scalar functions, for the builder's diagram and the function picker. Empty where the dialect has no queryable catalogue. | ds_id: int | await asyncio.to_thread(list_functions, cfg) | Depends(get_current_user); Direct checks: check_org | get_functions ? [AI_data_tool/data_analytics/backend/app/routers/data_sources.py](AI_data_tool/data_analytics/backend/app/routers/data_sources.py#L686) |
| POST | /api/v1/data-sources/{ds_id}/build-query | compile query ? Compile the visual model to SQL WITHOUT running it -- the builder shows the statement as it evolves. Every identifier is membership-checked against the live schema; the compile itself is the validation. | ds_id: int; model: dict | object {sql} | Depends(get_current_user); Direct checks: check_org | compile_query ? [AI_data_tool/data_analytics/backend/app/routers/data_sources.py](AI_data_tool/data_analytics/backend/app/routers/data_sources.py#L699) |
| POST | /api/v1/data-sources/{ds_id}/build-query/preview | preview built query ? Compile then run with a hard preview cap, returning rows + the SQL -- what the builder's data pane shows. | ds_id: int; model: dict | await asyncio.to_thread(_run) | Depends(get_current_user); Direct checks: check_org | preview_built_query ? [AI_data_tool/data_analytics/backend/app/routers/data_sources.py](AI_data_tool/data_analytics/backend/app/routers/data_sources.py#L725) |


#### dataflows.py

| Method | Full URL | Purpose | Request contract | Response | Authorization boundary | Implementation |
| --- | --- | --- | --- | --- | --- | --- |
| GET | /api/v1/dataflows | list dataflows ? Every dataflow in the org. Listing is not gated -- see the module note on authoring-vs-reading -- but each row carries the caller's own capability so the UI can hide controls it would only be refused for. | path/auth only | out | Depends(get_current_user); Direct checks: effective_dataflow_capability | list_dataflows ? [AI_data_tool/data_analytics/backend/app/routers/dataflows.py](AI_data_tool/data_analytics/backend/app/routers/dataflows.py#L139) |
| POST | /api/v1/dataflows | create dataflow ? Create a dataflow from a source dataset and a recipe. | req: DataflowIn | _out(...); HTTP 201 | Depends(get_current_user); Direct checks: check_org, require_dataset_capability | create_dataflow ? [AI_data_tool/data_analytics/backend/app/routers/dataflows.py](AI_data_tool/data_analytics/backend/app/routers/dataflows.py#L158) |
| GET | /api/v1/dataflows/{flow_id} | get dataflow | flow_id: int | _out(...) | Depends(get_current_user); Direct checks: effective_dataflow_capability | get_dataflow ? [AI_data_tool/data_analytics/backend/app/routers/dataflows.py](AI_data_tool/data_analytics/backend/app/routers/dataflows.py#L211) |
| PUT | /api/v1/dataflows/{flow_id} | update dataflow ? Edit the recipe, name or schedule. Needs 'edit'. | flow_id: int; req: DataflowPatch | _out(...) | Depends(get_current_user); Direct checks: effective_dataflow_capability, require_dataflow_capability | update_dataflow ? [AI_data_tool/data_analytics/backend/app/routers/dataflows.py](AI_data_tool/data_analytics/backend/app/routers/dataflows.py#L223) |
| DELETE | /api/v1/dataflows/{flow_id} | delete dataflow ? Delete the dataflow. Needs 'data'. | flow_id: int | empty response; HTTP 204 | Depends(get_current_user); Direct checks: require_dataflow_capability | delete_dataflow ? [AI_data_tool/data_analytics/backend/app/routers/dataflows.py](AI_data_tool/data_analytics/backend/app/routers/dataflows.py#L269) |
| POST | /api/v1/dataflows/{flow_id}/run | run dataflow ? Run the recipe. Needs 'edit'. | flow_id: int; req: RunRequest | object {rows, outputs} | Depends(get_current_user); Direct checks: require_dataflow_capability | run_dataflow ? [AI_data_tool/data_analytics/backend/app/routers/dataflows.py](AI_data_tool/data_analytics/backend/app/routers/dataflows.py#L287) |
| GET | /api/v1/dataflows/{flow_id}/capabilities | get capabilities ? Current grants. Readable by anyone in the org who can see the dataflow -- knowing who may edit something is not itself sensitive, and hiding it makes "why was I refused?" unanswerable without an admin. | flow_id: int | object {grants, your_capability} | Depends(get_current_user); Direct checks: effective_dataflow_capability | get_capabilities ? [AI_data_tool/data_analytics/backend/app/routers/dataflows.py](AI_data_tool/data_analytics/backend/app/routers/dataflows.py#L399) |
| PUT | /api/v1/dataflows/{flow_id}/capabilities | set capabilities ? Replace the grants. Needs 'data'. | flow_id: int; req: CapabilitiesIn | object {grants} | Depends(get_current_user); Direct checks: require_dataflow_capability | set_capabilities ? [AI_data_tool/data_analytics/backend/app/routers/dataflows.py](AI_data_tool/data_analytics/backend/app/routers/dataflows.py#L414) |


#### datasets.py

| Method | Full URL | Purpose | Request contract | Response | Authorization boundary | Implementation |
| --- | --- | --- | --- | --- | --- | --- |
| GET | /api/v1/datasets | list datasets | path/auth only | list[DatasetOut] | Depends(get_current_user) | list_datasets ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L110) |
| GET | /api/v1/datasets/{dataset_id} | get dataset | dataset_id: int | DatasetOut | Depends(get_current_user); Direct checks: check_org, require_dataset_read | get_dataset ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L135) |
| POST | /api/v1/datasets | upload dataset | file: UploadFile = File(...); name: str = Form(...); description: str = Form('') | DatasetOut | Depends(get_current_user) | upload_dataset ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L264) |
| POST | /api/v1/datasets/batch | upload datasets ? Upload several files at once. | files: list[UploadFile] = File(...); name: str = Form(...); description: str = Form(''); mode: str = Form('separate') | BatchUploadOut | Depends(get_current_user) | upload_datasets ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L411) |
| DELETE | /api/v1/datasets/{dataset_id} | delete dataset | dataset_id: int | empty response; HTTP 204 | Depends(get_current_user); Direct checks: check_org, require_dataset_write | delete_dataset ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L630) |
| POST | /api/v1/datasets/{dataset_id}/columns/{column_name}/duplicate | duplicate column ? Duplicate a column as a calculated column referencing the original. | dataset_id: int; column_name: str | object {name, expression} | Depends(get_current_user); Direct checks: check_org, require_dataset_capability | duplicate_column ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L653) |
| POST | /api/v1/datasets/{dataset_id}/export-policy | set export policy ? Set one dataset's export policy. Org-admin only: export disablement is a governance control, and a control any user can flip is not one. | dataset_id: int; disabled: bool &#124; None = None; body: dict &#124; None = None | object {export_policy} | Depends(get_current_user); Direct checks: check_org | set_export_policy ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L706) |
| GET | /api/v1/datasets/{dataset_id}/export-policy | get export policy | dataset_id: int | object {export_policy, has_security_rules, inherited_from} | Depends(get_current_user); Direct checks: check_org | get_export_policy ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L764) |
| GET | /api/v1/datasets/{dataset_id}/export | export dataset ? Download the whole dataset as CSV or TSV. | dataset_id: int; format: str = 'csv' | StreamingResponse(...) | Depends(get_current_user); Direct checks: check_org, require_dataset_read | export_dataset ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L839) |
| GET | /api/v1/datasets/{dataset_id}/calculated-columns | list calculated columns | dataset_id: int | ds.calculated_columns or [] | Depends(get_current_user); Direct checks: check_org | list_calculated_columns ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L896) |
| PUT | /api/v1/datasets/{dataset_id}/calculated-columns | save calculated column | dataset_id: int; col: CalcColumnDef | cols | Depends(get_current_user); Direct checks: check_org, require_dataset_capability | save_calculated_column ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L903) |
| DELETE | /api/v1/datasets/{dataset_id}/calculated-columns/{col_name} | delete calculated column | dataset_id: int; col_name: str | cols | Depends(get_current_user); Direct checks: check_org, require_dataset_capability | delete_calculated_column ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L916) |
| POST | /api/v1/datasets/{dataset_id}/calculated-columns/preview | preview calculated column | dataset_id: int; req: CalcColumnPreviewRequest | await asyncio.to_thread(preview_expression, ds.filename, req.expression, 8, rls_expr, _cp_steps, _cp_aux, custom_functions=ds.custom_functions) | Depends(get_current_user); Direct checks: check_org | preview_calculated_column ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L928) |
| GET | /api/v1/datasets/{dataset_id}/measures | list measures | dataset_id: int | ds.measures or [] | Depends(get_current_user); Direct checks: check_org | list_measures ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L976) |
| POST | /api/v1/datasets/{dataset_id}/measures | save measure | dataset_id: int; measure: MeasureDef | items | Depends(get_current_user); Direct checks: check_org, require_dataset_capability | save_measure ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L983) |
| DELETE | /api/v1/datasets/{dataset_id}/measures/{measure_name} | delete measure | dataset_id: int; measure_name: str | items | Depends(get_current_user); Direct checks: check_org, require_dataset_capability | delete_measure ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L997) |
| POST | /api/v1/datasets/{dataset_id}/measures/preview | preview measure expr | dataset_id: int; req: MeasurePreviewRequest | await asyncio.to_thread(_run) | Depends(get_current_user); Direct checks: check_org | preview_measure_expr ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L1009) |
| GET | /api/v1/datasets/{dataset_id}/custom-functions | list custom functions | dataset_id: int | ds.custom_functions or [] | Depends(get_current_user); Direct checks: check_org | list_custom_functions ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L1046) |
| PUT | /api/v1/datasets/{dataset_id}/custom-functions | save custom function | dataset_id: int; fn: CustomFunctionDef | items | Depends(get_current_user); Direct checks: check_org, require_dataset_capability | save_custom_function ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L1053) |
| DELETE | /api/v1/datasets/{dataset_id}/custom-functions/{name} | delete custom function | dataset_id: int; name: str | items | Depends(get_current_user); Direct checks: check_org, require_dataset_capability | delete_custom_function ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L1080) |
| POST | /api/v1/datasets/{dataset_id}/custom-functions/preview | preview custom function | dataset_id: int; req: CustomFunctionPreviewRequest | object {ok, error} / object {ok, result} | Depends(get_current_user); Direct checks: check_org | preview_custom_function ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L1092) |
| PATCH | /api/v1/datasets/{dataset_id}/refresh-schedule | set refresh schedule ? Set or clear a dataset's automatic refresh interval. None clears it. | dataset_id: int; req: RefreshScheduleUpdate | DatasetOut | Depends(get_current_user); Direct checks: check_org, require_dataset_write | set_refresh_schedule ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L1116) |
| PATCH | /api/v1/datasets/{dataset_id}/columns/{column}/description | set column description ? Describe a column, and write it where the description BELONGS. | dataset_id: int; column: str; body: ColumnDescriptionIn | object {written_to, shared, object, column} | Depends(get_current_user); Direct checks: check_org, require_dataset_capability, require_dataset_read | set_column_description ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L1218) |
| GET | /api/v1/datasets/{dataset_id}/column-meta | get column meta | dataset_id: int | ds.column_meta or {} | Depends(get_current_user); Direct checks: check_org | get_column_meta ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L1282) |
| PUT | /api/v1/datasets/{dataset_id}/column-meta | set column meta ? Replaces the whole map. That is deliberate: it makes a bulk edit across many columns one request, and lets a property be cleared by omitting it rather than needing a separate delete. | dataset_id: int; req: ColumnMetaUpdate | ds.column_meta | Depends(get_current_user); Direct checks: check_org, require_dataset_capability | set_column_meta ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L1289) |
| POST | /api/v1/datasets/{dataset_id}/suggest-dashboards | suggest dashboards ? Whole dashboards proposed for this dataset and this person. | dataset_id: int; req: SuggestDashboardsRequest | object {proposals, reason, question, profile, source, measured} | Depends(get_current_user); Direct checks: check_org, require_dataset_read | suggest_dashboards ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L1343) |
| POST | /api/v1/datasets/{dataset_id}/insights | dataset insights ? Unprompted ranked findings over the secured frame -- trends, standouts, laggards, correlations, outlier impact and data-quality flags, each carrying the numbers its sentence states, plus a one-paragraph narrative. | dataset_id: int | result | Depends(get_current_user); Direct checks: check_org | dataset_insights ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L1544) |
| POST | /api/v1/datasets/{dataset_id}/goal-seek | goal seek ? Solve for the factor value a target requires, on a linear fit of y ~ x over the same secured frame widgets read. The answer carries the fit's r² and whether the required x sits inside the observed range -- a goal outside the data is an extr? | dataset_id: int; x_column: str; y_column: str; target_y: float; x_min: float &#124; None = None; x_max: float &#124; None = None | await asyncio.to_thread(_run) | Depends(get_current_user); Direct checks: check_org | goal_seek ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L1682) |
| POST | /api/v1/datasets/{dataset_id}/explain | explain column ? Which columns move `column`, ranked SAS-style (top factor = 1, rest proportional), plus the top factor's relationship data. Same secured frame as every widget; a denied response column fails closed. | dataset_id: int; column: str; body: dict &#124; None = None | result | Depends(get_current_user); Direct checks: check_org | explain_column ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L1733) |
| POST | /api/v1/datasets/{dataset_id}/outlier-details | outlier details ? The detail behind the Fields pane's ⚠ badge: box-plot stats, the outlier rows themselves, and an impact assessment (how much of the total the outliers carry; the mean with and without them). Computed on the same RLS-filtered, prepped frame ? | dataset_id: int; column: str; detector: str = 'iqr' | await asyncio.to_thread(_run) | Depends(get_current_user); Direct checks: check_org | outlier_details ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L1821) |
| GET | /api/v1/datasets/lineage/graph | lineage graph ? The org's data estate as a graph: sources feed datasets, join steps link datasets, reports read datasets. Answers both lineage questions -- "where did this number come from" and "what breaks if I delete this dataset". Org-scoped, read-only;? | path/auth only | object {sources, datasets, reports} | Depends(get_current_user) | lineage_graph ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L1924) |
| GET | /api/v1/datasets/data-views/list | list data views | path/auth only | list comprehension | Depends(get_current_user) | list_data_views ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L2034) |
| POST | /api/v1/datasets/{dataset_id}/save-data-view | save data view ? Snapshot this dataset's semantic layer under a name, org-wide. | dataset_id: int; name: str | object {id, name}; HTTP 201 | Depends(get_current_user); Direct checks: check_org | save_data_view ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L2047) |
| POST | /api/v1/datasets/{dataset_id}/apply-data-view | apply data view ? Apply a saved bundle to this dataset, matching by column name. The response reports exactly what applied and what was skipped. | dataset_id: int; view_id: int | report | Depends(get_current_user); Direct checks: check_org | apply_data_view ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L2067) |
| PATCH | /api/v1/datasets/data-views/{view_id}/default | set default data view ? Mark (or unmark) a view as the one applied to every new dataset. | view_id: int; req: DataViewDefault | object {id, name, is_default} | Depends(get_current_user); Direct checks: check_org | set_default_data_view ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L2086) |
| DELETE | /api/v1/datasets/data-views/{view_id} | delete data view | view_id: int | empty response; HTTP 204 | Depends(get_current_user); Direct checks: check_org | delete_data_view ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L2116) |
| GET | /api/v1/datasets/{dataset_id}/prep-steps | get prep steps | dataset_id: int | prep_steps_of(...) | Depends(get_current_user); Direct checks: check_org | get_prep_steps ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L2128) |
| PUT | /api/v1/datasets/{dataset_id}/prep-steps | set prep steps ? Replace the dataset's prep pipeline wholesale (same replace-don't-merge contract as column-meta). Validation is the hard gate: a malformed step is refused here so the apply path can afford to be fail-soft. | dataset_id: int; steps: list[dict] | steps | Depends(get_current_user); Direct checks: check_org, require_dataset_capability | set_prep_steps ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L2136) |
| POST | /api/v1/datasets/{dataset_id}/prep-preview | preview prep steps ? Apply CANDIDATE steps (not the saved ones) to this user's RLS-filtered frame and return shape-before, shape-after and a sample -- the editor calls this on every change so the author sees the effect before saving. | dataset_id: int; steps: list[dict] | await asyncio.to_thread(_run) | Depends(get_current_user); Direct checks: check_org | preview_prep_steps ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L2180) |
| GET | /api/v1/datasets/{dataset_id}/sensitivity | get dataset sensitivity ? The dataset's own label, its EFFECTIVE label (highest over its lineage and joins) with the reason, and what that label enforces (Phase 7.3). | dataset_id: int | object {label, effective, reasons, options, redacted_on_share} | Depends(get_current_user); Direct checks: check_org, require_dataset_read | get_dataset_sensitivity ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L2239) |
| PUT | /api/v1/datasets/{dataset_id}/sensitivity | set dataset sensitivity ? Label a dataset Public / Internal / Confidential / Restricted (or clear it). Needs data-level access; audited. Everything built from or joining it inherits the label. | dataset_id: int; body: dict | await get_dataset_sensitivity(dataset_id, db, current_user) | Depends(get_current_user); Direct checks: check_org, require_dataset_write | set_dataset_sensitivity ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L2253) |
| POST | /api/v1/datasets/{dataset_id}/join-check | check join ? How a candidate join step will land, before it is saved. | dataset_id: int; body: dict | await asyncio.to_thread(_run) | Depends(get_current_user); Direct checks: check_org | check_join ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L2280) |
| POST | /api/v1/datasets/{dataset_id}/materialize | materialize dataset ? Run this dataset's pipeline once and save the result as a NEW dataset. | dataset_id: int; req: MaterializeRequest | DatasetOut | Depends(get_current_user); Direct checks: check_org, require_dataset_capability | materialize_dataset ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L2450) |
| GET | /api/v1/datasets/{dataset_id}/aggregate-preflight | aggregate preflight ? What the Aggregates tab needs before an author chooses anything: the columns every RLS rule reads (the grain must include them), and which columns can be grain or measure. | dataset_id: int | object {rls_columns, grain_candidates, measure_candidates} | Depends(get_current_user); Direct checks: check_org, require_dataset_capability, require_dataset_read | aggregate_preflight ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L2554) |
| POST | /api/v1/datasets/{dataset_id}/aggregates | create aggregate ? A scheduled GROUP BY over a DirectQuery dataset, saved as a new dataset. | dataset_id: int; req: AggregateCreateRequest | DatasetOut; HTTP 201 | Depends(get_current_user); Direct checks: check_org, require_dataset_capability, require_dataset_read | create_aggregate ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L2643) |
| PUT | /api/v1/datasets/{dataset_id}/aggregates/{agg_id} | update aggregate ? Edit an aggregate's grain, measures or schedule, or -- with an empty body -- rebuild it against the source as it is now. Every creation check runs again: rules and the source's query can have changed since. The old file is replaced only aft? | dataset_id: int; agg_id: int; req: AggregateUpdateRequest | DatasetOut | Depends(get_current_user); Direct checks: check_org, require_dataset_capability, require_dataset_read, require_dataset_write | update_aggregate ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L2707) |
| GET | /api/v1/datasets/{dataset_id}/aggregates | list aggregates ? The aggregates of a source, each with the scheduler's last failure for it (a ScheduleFailure row), so a grain a later rule outgrew is visible. | dataset_id: int | out | Depends(get_current_user); Direct checks: check_org, require_dataset_read | list_aggregates ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L2793) |
| POST | /api/v1/datasets/{dataset_id}/rebuild | rebuild dataset ? Re-run the recipe that built this dataset, replacing its rows. | dataset_id: int | DatasetOut | Depends(get_current_user); Direct checks: check_org, require_dataset_capability | rebuild_dataset ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L2830) |
| GET | /api/v1/datasets/{dataset_id}/column-formats | get column formats | dataset_id: int | ds.column_formats or {} | Depends(get_current_user); Direct checks: check_org | get_column_formats ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L2925) |
| PUT | /api/v1/datasets/{dataset_id}/column-formats | set column format | dataset_id: int; req: ColumnFormatRequest | fmts | Depends(get_current_user); Direct checks: check_org, require_dataset_capability | set_column_format ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L2932) |
| POST | /api/v1/datasets/{dataset_id}/data-preview | data preview | dataset_id: int; req: DataPreviewRequest | object {columns, rows, total} / await asyncio.to_thread(_run) | Depends(get_current_user); Direct checks: check_org, require_dataset_read | data_preview ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L2953) |
| PATCH | /api/v1/datasets/{dataset_id}/filter | update filter expr | dataset_id: int; body: FilterExprUpdate | DatasetOut | Depends(get_current_user); Direct checks: check_org | update_filter_expr ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L3083) |
| POST | /api/v1/datasets/{dataset_id}/filter-preview | preview filter expr | dataset_id: int; req: FilterPreviewRequest | await asyncio.to_thread(_run) | Depends(get_current_user); Direct checks: check_org | preview_filter_expr ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L3095) |
| POST | /api/v1/datasets/{dataset_id}/refresh | refresh dataset ? Re-fetch data from the original database connection. | dataset_id: int; body: DatasetRefreshRequest = DatasetRefreshRequest() | DatasetOut | Depends(get_current_user); Direct checks: check_org, require_dataset_capability | refresh_dataset ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L3140) |
| GET | /api/v1/datasets/{dataset_id}/alerts | list alerts | dataset_id: int | list comprehension | Depends(get_current_user); Direct checks: check_org, require_dataset_read | list_alerts ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L3262) |
| POST | /api/v1/datasets/{dataset_id}/alerts | create alert ? Watch a condition on this dataset. The expression is validated by the same sandbox gate widgets use, at creation time -- an alert that fails validation on every tick would only ever report evaluation errors. | dataset_id: int; body: dict | object {id, name}; HTTP 201 | Depends(get_current_user); Direct checks: check_org, require_dataset_read | create_alert ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L3279) |
| DELETE | /api/v1/datasets/{dataset_id}/alerts/{alert_id} | delete alert | dataset_id: int; alert_id: int | empty response; HTTP 204 | Depends(get_current_user); Direct checks: check_org, require_dataset_read | delete_alert ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L3309) |
| GET | /api/v1/datasets/{dataset_id}/shares | list dataset shares | dataset_id: int | list[DatasetShareOut] | Depends(require_org_admin); Direct checks: check_org | list_dataset_shares ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L3335) |
| POST | /api/v1/datasets/{dataset_id}/shares | create dataset share | dataset_id: int; body: DatasetShareCreate | DatasetShareOut; HTTP 201 | Depends(require_org_admin); Direct checks: check_org | create_dataset_share ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L3348) |
| DELETE | /api/v1/datasets/{dataset_id}/shares/{share_id} | delete dataset share | dataset_id: int; share_id: int | empty response; HTTP 204 | Depends(require_org_admin); Direct checks: check_org | delete_dataset_share ? [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L3373) |


#### demo.py

| Method | Full URL | Purpose | Request contract | Response | Authorization boundary | Implementation |
| --- | --- | --- | --- | --- | --- | --- |
| POST | /api/v1/demo/seed | seed demo ? Fill the caller's org with the demo datasets and reports. | path/auth only | object {datasets, reports, widgets} | Depends(get_current_user) | seed_demo ? [AI_data_tool/data_analytics/backend/app/routers/demo.py](AI_data_tool/data_analytics/backend/app/routers/demo.py#L31) |
| DELETE | /api/v1/demo/seed | unseed demo ? Remove the demo content from the caller's org, leaving their own data alone. | path/auth only | removed | Depends(get_current_user) | unseed_demo ? [AI_data_tool/data_analytics/backend/app/routers/demo.py](AI_data_tool/data_analytics/backend/app/routers/demo.py#L83) |


#### embed.py

| Method | Full URL | Purpose | Request contract | Response | Authorization boundary | Implementation |
| --- | --- | --- | --- | --- | --- | --- |
| POST | /api/v1/reports/{report_id}/embed-configs | create embed config ? Mint an embed config, recorded as created by THIS user -- the embed's entire data-access ceiling from here on. The plaintext secret is returned exactly ONCE; only its enc:v2 ciphertext is stored -- see `core/api_keys.py`'s secret-shown-once? | report_id: int; body: dict | object {id, name, secret, allowed_origins, enabled, created_at, note}; HTTP 201 | Depends(get_current_user); Direct checks: check_org, require_capability | create_embed_config ? [AI_data_tool/data_analytics/backend/app/routers/embed.py](AI_data_tool/data_analytics/backend/app/routers/embed.py#L164) |
| GET | /api/v1/reports/{report_id}/embed-configs | list embed configs | report_id: int | list comprehension | Depends(get_current_user); Direct checks: check_org | list_embed_configs ? [AI_data_tool/data_analytics/backend/app/routers/embed.py](AI_data_tool/data_analytics/backend/app/routers/embed.py#L200) |
| PATCH | /api/v1/reports/{report_id}/embed-configs/{config_id} | update embed config ? Enable/disable (revoke) an embed config. Revocation, not deletion -- mirrors ShareLink: the row (and its audit trail) stays. | report_id: int; config_id: int; body: dict | object {id, name, allowed_origins, enabled} | Depends(get_current_user); Direct checks: check_org, require_capability | update_embed_config ? [AI_data_tool/data_analytics/backend/app/routers/embed.py](AI_data_tool/data_analytics/backend/app/routers/embed.py#L212) |
| DELETE | /api/v1/reports/{report_id}/embed-configs/{config_id} | delete embed config | report_id: int; config_id: int | empty response; HTTP 204 | Depends(get_current_user); Direct checks: check_org, require_capability | delete_embed_config ? [AI_data_tool/data_analytics/backend/app/routers/embed.py](AI_data_tool/data_analytics/backend/app/routers/embed.py#L235) |
| GET | /api/v1/embed/report | embed report ? Decode UNVERIFIED header -> cfg id -> load config (else 404) -> verify signature with the config's decrypted secret -> origin check -> return the report structure plus a short-lived internal session token for widget-data calls. Every step h? | token: str | object {name, theme, classification, common_filters, dataset_id, column_formats, geography, calculated_columns, pages, embed_session_token, **spread} | No auth dependency declared; protocol/token logic may be inside handler | embed_report ? [AI_data_tool/data_analytics/backend/app/routers/embed.py](AI_data_tool/data_analytics/backend/app/routers/embed.py#L251) |
| POST | /api/v1/embed/widget-data/{widget_id} | embed widget data ? One widget's data for an embedded report. The embed SESSION token (from `GET /embed/report`, 15 min TTL) is the only credential accepted here -- it carries the cfg id plus the ORIGINAL host JWT's filters/viewer_email/ viewer_org, baked in a? | widget_id: int | result | No auth dependency declared; protocol/token logic may be inside handler | embed_widget_data ? [AI_data_tool/data_analytics/backend/app/routers/embed.py](AI_data_tool/data_analytics/backend/app/routers/embed.py#L354) |


#### hierarchy.py

| Method | Full URL | Purpose | Request contract | Response | Authorization boundary | Implementation |
| --- | --- | --- | --- | --- | --- | --- |
| GET | /api/v1/datasets/{dataset_id}/hierarchy | get hierarchy | dataset_id: int | list[HierarchyNodeOut] | Depends(get_current_user) | get_hierarchy ? [AI_data_tool/data_analytics/backend/app/routers/hierarchy.py](AI_data_tool/data_analytics/backend/app/routers/hierarchy.py#L24) |
| POST | /api/v1/datasets/{dataset_id}/hierarchy | create node | dataset_id: int; body: HierarchyNodeCreate | HierarchyNodeOut; HTTP 201 | Depends(get_current_user) | create_node ? [AI_data_tool/data_analytics/backend/app/routers/hierarchy.py](AI_data_tool/data_analytics/backend/app/routers/hierarchy.py#L33) |
| PATCH | /api/v1/datasets/{dataset_id}/hierarchy/{node_id} | update node | dataset_id: int; node_id: int; body: HierarchyNodeUpdate | HierarchyNodeOut | Depends(get_current_user) | update_node ? [AI_data_tool/data_analytics/backend/app/routers/hierarchy.py](AI_data_tool/data_analytics/backend/app/routers/hierarchy.py#L43) |
| DELETE | /api/v1/datasets/{dataset_id}/hierarchy/{node_id} | delete node | dataset_id: int; node_id: int | empty response; HTTP 204 | Depends(get_current_user) | delete_node ? [AI_data_tool/data_analytics/backend/app/routers/hierarchy.py](AI_data_tool/data_analytics/backend/app/routers/hierarchy.py#L57) |
| POST | /api/v1/datasets/{dataset_id}/hierarchy/auto-generate | auto generate | dataset_id: int | list[HierarchyNodeOut] | Depends(get_current_user) | auto_generate ? [AI_data_tool/data_analytics/backend/app/routers/hierarchy.py](AI_data_tool/data_analytics/backend/app/routers/hierarchy.py#L79) |


#### map_settings.py

| Method | Full URL | Purpose | Request contract | Response | Authorization boundary | Implementation |
| --- | --- | --- | --- | --- | --- | --- |
| GET | /api/v1/map-settings | get map settings | path/auth only | _out(...) | Depends(get_current_user) | get_map_settings ? [AI_data_tool/data_analytics/backend/app/routers/map_settings.py](AI_data_tool/data_analytics/backend/app/routers/map_settings.py#L49) |
| PUT | /api/v1/map-settings | set map settings | body: dict | _out(...) | Depends(require_org_admin) | set_map_settings ? [AI_data_tool/data_analytics/backend/app/routers/map_settings.py](AI_data_tool/data_analytics/backend/app/routers/map_settings.py#L57) |


#### metadata.py

| Method | Full URL | Purpose | Request contract | Response | Authorization boundary | Implementation |
| --- | --- | --- | --- | --- | --- | --- |
| POST | /api/v1/data-sources/{source_id}/sync | trigger sync ? Run the metadata pipeline against one source. | source_id: int | object {sync_run_id, status, stages} | Depends(require_org_admin) | trigger_sync ? [AI_data_tool/data_analytics/backend/app/routers/metadata.py](AI_data_tool/data_analytics/backend/app/routers/metadata.py#L67) |
| GET | /api/v1/data-sources/{source_id}/sync/latest | latest sync | source_id: int | object {status, stages} / _run_payload(...) | Depends(get_current_user) | latest_sync ? [AI_data_tool/data_analytics/backend/app/routers/metadata.py](AI_data_tool/data_analytics/backend/app/routers/metadata.py#L120) |
| GET | /api/v1/data-sources/{source_id}/sync/{run_id} | sync status | source_id: int; run_id: int | _run_payload(...) | Depends(get_current_user); Direct checks: check_org | sync_status ? [AI_data_tool/data_analytics/backend/app/routers/metadata.py](AI_data_tool/data_analytics/backend/app/routers/metadata.py#L136) |
| GET | /api/v1/data-sources/{source_id}/review | review queue ? What the sync learned about this database. | source_id: int | object {source, datasets, relationships, columns} | Depends(get_current_user) | review_queue ? [AI_data_tool/data_analytics/backend/app/routers/metadata.py](AI_data_tool/data_analytics/backend/app/routers/metadata.py#L164) |
| POST | /api/v1/data-sources/{source_id}/review/confirm | confirm review ? Promote inferred catalog items to `confirmed` — the terminal state. | source_id: int; body: ConfirmRequest | object {confirmed, rejected, columns_updated} | Depends(require_org_admin) | confirm_review ? [AI_data_tool/data_analytics/backend/app/routers/metadata.py](AI_data_tool/data_analytics/backend/app/routers/metadata.py#L275) |
| PATCH | /api/v1/data-sources/{source_id}/metadata-settings | update metadata settings ? Change LLM consent, or edit the database description by hand. | source_id: int; body: SourceSettings | object {allow_llm_sampling, description, description_source} | Depends(require_org_admin) | update_metadata_settings ? [AI_data_tool/data_analytics/backend/app/routers/metadata.py](AI_data_tool/data_analytics/backend/app/routers/metadata.py#L370) |
| GET | /api/v1/data-sources/{source_id}/drift | drift history | source_id: int; limit: int = 20 | list comprehension | Depends(get_current_user) | drift_history ? [AI_data_tool/data_analytics/backend/app/routers/metadata.py](AI_data_tool/data_analytics/backend/app/routers/metadata.py#L404) |
| GET | /api/v1/data-sources/{source_id}/glossary | list glossary ? This source's own terms, plus every ORG-WIDE term (data_source_id NULL) — a term like "GMV" usually means the same thing everywhere in the org, matching what `agent/context.py`'s `load_context` loads for the agent itself. | source_id: int | list comprehension | Depends(get_current_user) | list_glossary ? [AI_data_tool/data_analytics/backend/app/routers/metadata.py](AI_data_tool/data_analytics/backend/app/routers/metadata.py#L454) |
| POST | /api/v1/data-sources/{source_id}/glossary | create glossary term | source_id: int; body: GlossaryIn | _glossary_payload(...) | Depends(require_org_admin) | create_glossary_term ? [AI_data_tool/data_analytics/backend/app/routers/metadata.py](AI_data_tool/data_analytics/backend/app/routers/metadata.py#L475) |
| DELETE | /api/v1/data-sources/{source_id}/glossary/{term_id} | delete glossary term | source_id: int; term_id: int | empty response; HTTP 204 | Depends(require_org_admin); Direct checks: check_org | delete_glossary_term ? [AI_data_tool/data_analytics/backend/app/routers/metadata.py](AI_data_tool/data_analytics/backend/app/routers/metadata.py#L504) |
| GET | /api/v1/data-sources/{source_id}/entities | list entities | source_id: int | list comprehension | Depends(get_current_user) | list_entities ? [AI_data_tool/data_analytics/backend/app/routers/metadata.py](AI_data_tool/data_analytics/backend/app/routers/metadata.py#L551) |
| POST | /api/v1/data-sources/{source_id}/entities/confirm | confirm entities ? Edit and/or confirm entity rows. Editing a field and confirming are both "a human touched this" -- either one promotes the row to `confirmed`, the same rule `review/confirm` applies to column descriptions and enum labels above. | source_id: int; body: EntityConfirmRequest | object {updated} | Depends(require_org_admin) | confirm_entities ? [AI_data_tool/data_analytics/backend/app/routers/metadata.py](AI_data_tool/data_analytics/backend/app/routers/metadata.py#L567) |
| GET | /api/v1/datasets/{dataset_id}/columns/{column_name}/stats | column statistics ? Statistics for one column, including `top_k`. | dataset_id: int; column_name: str | object {column, dtype, semantic_type, profiled} / object {column, dtype, semantic_type, description, description_source, profiled, null_ratio, distinct_count, top_k, min_value, max_value, exact, computed_at} | Depends(get_current_user); Direct checks: check_org | column_statistics ? [AI_data_tool/data_analytics/backend/app/routers/metadata.py](AI_data_tool/data_analytics/backend/app/routers/metadata.py#L609) |
| POST | /api/v1/data-sources/{source_id}/suggest-dashboard | suggest dashboard for role ? Propose a dashboard for a kind of person, from this connection's catalog. | source_id: int; body: SuggestDashboardIn | object {ok, reason, suggestion} | Depends(get_current_user); Direct checks: check_org | suggest_dashboard_for_role ? [AI_data_tool/data_analytics/backend/app/routers/metadata.py](AI_data_tool/data_analytics/backend/app/routers/metadata.py#L672) |
| POST | /api/v1/data-sources/{source_id}/review/reset-inferred | reset inferred metadata ? Clear the descriptions and semantic types that INFERENCE wrote. | source_id: int | object {objects_cleared, columns_cleared} | Depends(require_org_admin); Direct checks: check_org | reset_inferred_metadata ? [AI_data_tool/data_analytics/backend/app/routers/metadata.py](AI_data_tool/data_analytics/backend/app/routers/metadata.py#L721) |


#### notifications.py

| Method | Full URL | Purpose | Request contract | Response | Authorization boundary | Implementation |
| --- | --- | --- | --- | --- | --- | --- |
| GET | /api/v1/notifications | list notifications | limit: int = 30 | object {unread, notifications} | Depends(get_current_user) | list_notifications ? [AI_data_tool/data_analytics/backend/app/routers/notifications.py](AI_data_tool/data_analytics/backend/app/routers/notifications.py#L16) |
| POST | /api/v1/notifications/mark-read | mark read ? Marks ALL of the caller's notifications read. Only ever the caller's own rows -- there is no cross-user surface here at all. | path/auth only | object {marked} | Depends(get_current_user) | mark_read ? [AI_data_tool/data_analytics/backend/app/routers/notifications.py](AI_data_tool/data_analytics/backend/app/routers/notifications.py#L31) |


#### pins.py

| Method | Full URL | Purpose | Request contract | Response | Authorization boundary | Implementation |
| --- | --- | --- | --- | --- | --- | --- |
| POST | /api/v1/pins | create pin | body: PinCreate | object {id, already_pinned} / object {id, widget_id, already_pinned}; HTTP 201 | Depends(get_current_user); Direct checks: check_org | create_pin ? [AI_data_tool/data_analytics/backend/app/routers/pins.py](AI_data_tool/data_analytics/backend/app/routers/pins.py#L86) |
| PATCH | /api/v1/pins/{pin_id} | update pin ? Layout only -- position and size. What a pin POINTS AT is immutable; repointing would silently swap a card's meaning under its position. | pin_id: int; body: PinUpdate | object {id, position, size} | Depends(get_current_user) | update_pin ? [AI_data_tool/data_analytics/backend/app/routers/pins.py](AI_data_tool/data_analytics/backend/app/routers/pins.py#L136) |
| GET | /api/v1/pins | list pins | path/auth only | object {pins} | Depends(get_current_user) | list_pins ? [AI_data_tool/data_analytics/backend/app/routers/pins.py](AI_data_tool/data_analytics/backend/app/routers/pins.py#L155) |
| DELETE | /api/v1/pins/{pin_id} | delete pin | pin_id: int | empty response; HTTP 204 | Depends(get_current_user) | delete_pin ? [AI_data_tool/data_analytics/backend/app/routers/pins.py](AI_data_tool/data_analytics/backend/app/routers/pins.py#L206) |


#### platform.py

| Method | Full URL | Purpose | Request contract | Response | Authorization boundary | Implementation |
| --- | --- | --- | --- | --- | --- | --- |
| POST | /api/v1/platform/organizations | create org ? Provision a whole organization plus its first admin user in one call. | body: OrgCreate | object {org_id, name, admin_user_id, admin_email}; HTTP 201 | Depends(require_super_admin) | create_org ? [AI_data_tool/data_analytics/backend/app/routers/platform.py](AI_data_tool/data_analytics/backend/app/routers/platform.py#L32) |
| GET | /api/v1/platform/organizations | list orgs ? Every organization on the platform, with member counts, its parent, and (Task E2) its quota config alongside today's usage against it -- three grouped aggregates, not N per-org queries, so this stays one round trip regardless of how many or? | path/auth only | list comprehension | Depends(require_super_admin) | list_orgs ? [AI_data_tool/data_analytics/backend/app/routers/platform.py](AI_data_tool/data_analytics/backend/app/routers/platform.py#L56) |
| PUT | /api/v1/platform/organizations/{org_id}/quota | set org quota ? Create or update the one Quota row for an org. Every field is nullable and null means unlimited, so a caller wanting to CLEAR a limit just omits it (Pydantic default None) or sends it explicitly as null -- both look the same on this model, ? | org_id: int; body: OrgQuotaSet | object {org_id, max_queries_per_day, max_agent_asks_per_day, max_storage_mb, max_concurrent_asks} | Depends(require_super_admin) | set_org_quota ? [AI_data_tool/data_analytics/backend/app/routers/platform.py](AI_data_tool/data_analytics/backend/app/routers/platform.py#L109) |
| GET | /api/v1/platform/organizations/tree | org tree ? The organization hierarchy as nested nodes, rooted at the top-level orgs. | path/auth only | list comprehension | Depends(require_super_admin) | org_tree ? [AI_data_tool/data_analytics/backend/app/routers/platform.py](AI_data_tool/data_analytics/backend/app/routers/platform.py#L138) |
| PUT | /api/v1/platform/organizations/{org_id}/mcp | set org mcp ? Activate or deactivate MCP / machine (API-key) access for one org. Deactivating makes every one of that org's API keys stop authenticating immediately. | org_id: int; body: OrgMcpSet | object {org_id, mcp_enabled} | Depends(require_super_admin) | set_org_mcp ? [AI_data_tool/data_analytics/backend/app/routers/platform.py](AI_data_tool/data_analytics/backend/app/routers/platform.py#L160) |
| PUT | /api/v1/platform/organizations/{org_id}/parent | set org parent ? Set (or clear, with null) an org's parent. Guards against a self-parent and any cycle — a parent may not be the org itself or one of its own descendants. | org_id: int; body: OrgParentSet | object {org_id, parent_org_id} | Depends(require_super_admin) | set_org_parent ? [AI_data_tool/data_analytics/backend/app/routers/platform.py](AI_data_tool/data_analytics/backend/app/routers/platform.py#L178) |


#### prediction_models.py

| Method | Full URL | Purpose | Request contract | Response | Authorization boundary | Implementation |
| --- | --- | --- | --- | --- | --- | --- |
| POST | /api/v1/datasets/{dataset_id}/prediction-models | train model ? Compare candidates, keep the champion. | dataset_id: int; req: TrainRequest | _out(...); HTTP 201 | Depends(get_current_user); Direct checks: _dataset_for_read, require_dataset_capability | train_model ? [AI_data_tool/data_analytics/backend/app/routers/prediction_models.py](AI_data_tool/data_analytics/backend/app/routers/prediction_models.py#L101) |
| GET | /api/v1/datasets/{dataset_id}/prediction-models | list models ? Models on this dataset that the caller may actually use. | dataset_id: int | list comprehension | Depends(get_current_user); Direct checks: _dataset_for_read | list_models ? [AI_data_tool/data_analytics/backend/app/routers/prediction_models.py](AI_data_tool/data_analytics/backend/app/routers/prediction_models.py#L178) |
| POST | /api/v1/datasets/{dataset_id}/prediction-models/{model_id}/score | score model ? Predictions for rows whose outcome is not known yet. | dataset_id: int; model_id: int; req: ScoreRequest | await asyncio.to_thread(score_frame, pkg, frame) | Depends(get_current_user); Direct checks: _dataset_for_read | score_model ? [AI_data_tool/data_analytics/backend/app/routers/prediction_models.py](AI_data_tool/data_analytics/backend/app/routers/prediction_models.py#L232) |
| DELETE | /api/v1/datasets/{dataset_id}/prediction-models/{model_id} | delete model | dataset_id: int; model_id: int | empty response; HTTP 204 | Depends(get_current_user); Direct checks: _dataset_for_read, check_org, require_dataset_capability | delete_model ? [AI_data_tool/data_analytics/backend/app/routers/prediction_models.py](AI_data_tool/data_analytics/backend/app/routers/prediction_models.py#L283) |


#### relationships.py

| Method | Full URL | Purpose | Request contract | Response | Authorization boundary | Implementation |
| --- | --- | --- | --- | --- | --- | --- |
| GET | /api/v1/relationships | list relationships | path/auth only | list[RelationshipOut] | Depends(get_current_user) | list_relationships ? [AI_data_tool/data_analytics/backend/app/routers/relationships.py](AI_data_tool/data_analytics/backend/app/routers/relationships.py#L22) |
| POST | /api/v1/relationships | create relationship | body: RelationshipCreate | RelationshipOut | Depends(get_current_user); Direct checks: check_org | create_relationship ? [AI_data_tool/data_analytics/backend/app/routers/relationships.py](AI_data_tool/data_analytics/backend/app/routers/relationships.py#L28) |
| POST | /api/v1/relationships/check | check relationship ? How a candidate mapping will carry a filter, before it is saved: the share of the source column's values that exist in the target column, the ones that do not, and near-misses (case/spacing). Both sides are read AS THE CALLER -- RLS, column? | body: dict | await asyncio.to_thread(mapping_match_report, left[fcol], right[tcol]) | Depends(get_current_user); Direct checks: check_org | check_relationship ? [AI_data_tool/data_analytics/backend/app/routers/relationships.py](AI_data_tool/data_analytics/backend/app/routers/relationships.py#L48) |
| DELETE | /api/v1/relationships/{relationship_id} | delete relationship | relationship_id: int | empty response; HTTP 204 | Depends(get_current_user); Direct checks: check_org | delete_relationship ? [AI_data_tool/data_analytics/backend/app/routers/relationships.py](AI_data_tool/data_analytics/backend/app/routers/relationships.py#L79) |


#### report_copilot.py

| Method | Full URL | Purpose | Request contract | Response | Authorization boundary | Implementation |
| --- | --- | --- | --- | --- | --- | --- |
| POST | /api/v1/reports/{report_id}/pages/{page_id}/copilot | page copilot | report_id: int; page_id: int; body: CopilotIn | object {reply, applied, notes, results} / object {reply, applied, notes, results, before_version_id, summary} | Depends(get_current_user); Direct checks: check_org, max_dataset_capability, require_capability | page_copilot ? [AI_data_tool/data_analytics/backend/app/routers/report_copilot.py](AI_data_tool/data_analytics/backend/app/routers/report_copilot.py#L147) |


#### reports.py

| Method | Full URL | Purpose | Request contract | Response | Authorization boundary | Implementation |
| --- | --- | --- | --- | --- | --- | --- |
| GET | /api/v1/reports | list reports | path/auth only | list[ReportOut] | Depends(get_current_user); router: [Depends(_report_access_gate)] | list_reports ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L198) |
| POST | /api/v1/reports | create report | body: ReportCreate | ReportOut; HTTP 201 | Depends(get_current_user); router: [Depends(_report_access_gate)] | create_report ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L220) |
| GET | /api/v1/reports/recent | list recent ? This user's recently opened dashboards, newest first. | limit: int = 8 | out | Depends(get_current_user); router: [Depends(_report_access_gate)] | list_recent ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L238) |
| GET | /api/v1/reports/{report_id} | get report | report_id: int | ReportOut | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: effective_capability | get_report ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L300) |
| GET | /api/v1/reports/{report_id}/revision | get report revision ? Just the revision counter — deliberately cheap, with none of the page and widget eager-loading GET /{report_id} does, because a client polls this to notice concurrent edits and should not pull the whole report to do it. | report_id: int | object {revision} | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org | get_report_revision ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L347) |
| GET | /api/v1/reports/{report_id}/classification | get report classification | report_id: int | object {label, options, floor, floor_reasons, effective, effective_reasons} | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org | get_report_classification ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L357) |
| PUT | /api/v1/reports/{report_id}/classification | set report classification ? Set (or clear, with an empty label) a report's sensitivity label. Editing the classification is a report edit, so it goes through the same capability gate and revision bump as any other mutation. | report_id: int; body: dict | ReportOut | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: effective_capability | set_report_classification ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L371) |
| POST | /api/v1/reports/{report_id}/common-filters | add common filter ? Add a report-level filter applied to every widget. Editing report filters is a report edit — same capability gate and revision bump as any mutation. | report_id: int; body: dict | object {id, column, op, value}; HTTP 201 | Depends(get_current_user); router: [Depends(_report_access_gate)] | add_common_filter ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L408) |
| DELETE | /api/v1/reports/{report_id}/common-filters/{filter_id} | delete common filter | report_id: int; filter_id: int | empty response; HTTP 204 | Depends(get_current_user); router: [Depends(_report_access_gate)] | delete_common_filter ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L438) |
| PATCH | /api/v1/reports/{report_id} | update report | report_id: int; body: ReportUpdate | ReportOut | Depends(get_current_user); router: [Depends(_report_access_gate)] | update_report ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L452) |
| DELETE | /api/v1/reports/{report_id} | delete report | report_id: int | empty response; HTTP 204 | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org, require_capability | delete_report ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L472) |
| POST | /api/v1/reports/{report_id}/publish | set published | report_id: int; body: dict | object {published} | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org | set_published ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L497) |
| GET | /api/v1/reports/{report_id}/grants | list grants | report_id: int | list comprehension | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org | list_grants ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L531) |
| POST | /api/v1/reports/{report_id}/grants | create grant ? Share to a user BY EMAIL. An email input rather than a user picker on purpose: members cannot list the org directory, and sharing should not be the endpoint that leaks it -- you share with someone you already know. | report_id: int; body: dict | object {id, user_id, email, level}; HTTP 201 | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org | create_grant ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L548) |
| DELETE | /api/v1/reports/{report_id}/grants/{grant_id} | delete grant | report_id: int; grant_id: int | empty response; HTTP 204 | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org | delete_grant ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L589) |
| POST | /api/v1/reports/{report_id}/pages | add page | report_id: int; body: PageCreate | PageOut; HTTP 201 | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org | add_page ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L608) |
| PATCH | /api/v1/reports/{report_id}/pages/{page_id} | update page | report_id: int; page_id: int; body: PageUpdate | PageOut | Depends(get_current_user); router: [Depends(_report_access_gate)] | update_page ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L619) |
| DELETE | /api/v1/reports/{report_id}/pages/{page_id} | delete page | report_id: int; page_id: int | empty response; HTTP 204 | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org | delete_page ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L641) |
| POST | /api/v1/reports/{report_id}/pages/{page_id}/widgets | add widget | report_id: int; page_id: int; body: WidgetCreate | WidgetOut; HTTP 201 | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org | add_widget ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L690) |
| PATCH | /api/v1/reports/{report_id}/pages/{page_id}/widgets/{widget_id} | update widget | report_id: int; page_id: int; widget_id: int; body: WidgetUpdate | WidgetOut | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org | update_widget ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L715) |
| DELETE | /api/v1/reports/{report_id}/pages/{page_id}/widgets/{widget_id} | delete widget | report_id: int; page_id: int; widget_id: int | empty response; HTTP 204 | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org | delete_widget ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L781) |
| GET | /api/v1/reports/{report_id}/versions | list versions ? Newest first. Every entry is a restorable content state; `revision` is the counter value it describes. Small on purpose — the snapshot itself only travels on restore, never in the list. | report_id: int | list comprehension | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org | list_versions ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L800) |
| POST | /api/v1/reports/{report_id}/versions/{version_id}/restore | restore version ? Put the report's CONTENT back as it was at that version. | report_id: int; version_id: int | object {restored_version_id, restored_revision, saved_current_as_version_id, note} | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org | restore_version ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L825) |
| GET | /api/v1/reports/{report_id}/bookmarks | list bookmarks | report_id: int | list[BookmarkOut] | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org | list_bookmarks ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L896) |
| POST | /api/v1/reports/{report_id}/bookmarks | create bookmark | report_id: int; body: BookmarkCreate | BookmarkOut | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org | create_bookmark ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L904) |
| DELETE | /api/v1/reports/{report_id}/bookmarks/{bookmark_id} | delete bookmark | report_id: int; bookmark_id: int | empty response; HTTP 204 | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org | delete_bookmark ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L916) |
| GET | /api/v1/reports/themes/custom | list org themes | path/auth only | list comprehension | Depends(get_current_user); router: [Depends(_report_access_gate)] | list_org_themes ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L933) |
| POST | /api/v1/reports/themes/custom | create org theme ? Save a custom palette for the org. | body: dict | object {id, name, colors}; HTTP 201 | Depends(get_current_user); router: [Depends(_report_access_gate)] | create_org_theme ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L941) |
| DELETE | /api/v1/reports/themes/custom/{theme_id} | delete org theme | theme_id: int | empty response; HTTP 204 | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org | delete_org_theme ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L962) |
| GET | /api/v1/reports/{report_id}/parameters | list parameters | report_id: int | list comprehension | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org | list_parameters ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L978) |
| PUT | /api/v1/reports/{report_id}/parameters | save parameters ? Replace the report's parameter definitions wholesale. | report_id: int; body: list[dict] | await list_parameters(report_id, db, current_user) | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org, require_capability | save_parameters ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L990) |
| GET | /api/v1/reports/{report_id}/pdf | export report pdf ? Download the report as a server-rendered PDF -- cover, table of contents, and every page's visuals drawn. Any viewer may export what they can see; row-level security is applied as the CALLER, so the PDF never contains rows the downloader co? | report_id: int; paper: str = 'A4'; orientation: str = 'landscape'; contents: bool = True; pages: str &#124; None = None | StreamingResponse(...) | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: download_gate | export_report_pdf ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L1105) |
| GET | /api/v1/reports/{report_id}/package | export report package ? The report as ONE offline HTML file: visible pages, every widget's result frozen as the caller sees it, and an inline renderer. | report_id: int | Response(...) | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: download_gate | export_report_package ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L1156) |
| POST | /api/v1/reports/{report_id}/suggest-widgets | suggest widgets ? Widget suggestions for THIS report: the insights engine's ranked findings over the report's dataset, each mapped to a one-click widget config, with findings about columns the report's name/description mentions boosted to the top -- the desc? | report_id: int | await asyncio.to_thread(_run) | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org | suggest_widgets ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L1238) |
| POST | /api/v1/reports/{report_id}/auto-compose | auto compose ? Build a whole page from the insights engine, in one call. | report_id: int | object {page_id, name, widget_count} | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org | auto_compose ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L1306) |
| GET | /api/v1/reports/{report_id}/schedules | list schedules | report_id: int | list comprehension | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org | list_schedules ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L1409) |
| POST | /api/v1/reports/{report_id}/schedules | create schedule ? Create a recurring delivery. Runs AS THE CREATOR: the schedule's emails carry the creator's row-level slice, which is why the identity is recorded here and never substituted later. | report_id: int; body: dict | object {id, interval_minutes, recipients, calendar, format, timezone}; HTTP 201 | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org, require_capability | create_schedule ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L1426) |
| GET | /api/v1/reports/{report_id}/subscription | get my subscription ? Whether the caller is subscribed to this report, and on what cadence. | report_id: int | object {subscribed} / object {subscribed, id, calendar, interval_minutes, format, last_run_at, last_status} | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org, require_capability | get_my_subscription ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L1520) |
| POST | /api/v1/reports/{report_id}/subscribe | subscribe to report ? Subscribe YOURSELF to a recurring copy of this report. | report_id: int; body: dict &#124; None = None | object {subscribed, id, calendar, format, timezone}; HTTP 201 | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org, require_capability | subscribe_to_report ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L1544) |
| DELETE | /api/v1/reports/{report_id}/subscribe | unsubscribe from report ? Cancel your own subscription. | report_id: int | empty response; HTTP 204 | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org, require_capability | unsubscribe_from_report ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L1635) |
| DELETE | /api/v1/reports/{report_id}/schedules/{schedule_id} | delete schedule | report_id: int; schedule_id: int | empty response; HTTP 204 | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org, require_capability | delete_schedule ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L1660) |
| POST | /api/v1/reports/{report_id}/schedules/{schedule_id}/run-now | run schedule now ? Trigger one delivery immediately -- how an author verifies the pipe before trusting the timer with it. | report_id: int; schedule_id: int | object {last_status} | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org | run_schedule_now ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L1669) |
| GET | /api/v1/reports/{report_id}/deliveries | list deliveries ? T3: recent delivery attempts for this report's schedules -- status, time, duration, error. 404-never-403 org scoping via check_org, same as list_schedules (its nearest sibling): a viewer who can see the report can see whether its scheduled ? | report_id: int | list comprehension | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org | list_deliveries ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L1680) |
| GET | /api/v1/reports/templates/builtin | list builtin templates | path/auth only | list comprehension | Depends(get_current_user); router: [Depends(_report_access_gate)] | list_builtin_templates ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L1717) |
| GET | /api/v1/reports/templates/page | list page templates | path/auth only | list comprehension | Depends(get_current_user); router: [Depends(_report_access_gate)] | list_page_templates ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L1723) |
| DELETE | /api/v1/reports/templates/page/{template_id} | delete page template ? Remove a saved page template. | template_id: int | empty response; HTTP 204 | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org | delete_page_template ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L1734) |
| POST | /api/v1/reports/{report_id}/pages/{page_id}/save-as-template | save page as template | report_id: int; page_id: int; body: dict | object {id, name}; HTTP 201 | Depends(get_current_user); router: [Depends(_report_access_gate)] | save_page_as_template ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L1753) |
| POST | /api/v1/reports/{report_id}/pages/from-template | add page from template ? Instantiate a page from a saved template, a built-in, or another report's page. | report_id: int; body: dict | object {page_id, widgets}; HTTP 201 | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org | add_page_from_template ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L1767) |
| GET | /api/v1/reports/roles/lite | list roles lite ? Role ids and names for the caller's org. Not admin-gated: the page-visibility control needs the list to offer, and role NAMES within one's own org are not a secret -- the admin surface (membership, permissions) stays admin-only. | path/auth only | list comprehension | Depends(get_current_user); router: [Depends(_report_access_gate)] | list_roles_lite ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L1808) |
| GET | /api/v1/reports/{report_id}/capabilities | get report capabilities ? The per-role capability map for a report. Admin-only: capability is a governance control, and a control any user can read the shape of (then infer they could set) is a step toward one they can flip. | report_id: int | object {levels} | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org | get_report_capabilities ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L1819) |
| PUT | /api/v1/reports/{report_id}/capabilities | set report capabilities ? Replace a report's per-role capability map. Each value is 'view', 'edit' or 'data'; a role omitted (or set to 'data') is unrestricted. Role ids are validated against the caller's org so a foreign role cannot be smuggled in, and an org-admin? | report_id: int; body: dict | object {levels} | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org | set_report_capabilities ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L1836) |
| GET | /api/v1/reports/{report_id}/pages/{page_id}/visibility | get page visibility | report_id: int; page_id: int | object {role_ids} | Depends(get_current_user); router: [Depends(_report_access_gate)] | get_page_visibility ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L1877) |
| PUT | /api/v1/reports/{report_id}/pages/{page_id}/visibility | set page visibility ? Replace the page's role restriction. An empty list clears it (everyone sees). Role ids are validated against the caller's org so a foreign role id cannot be smuggled into the restriction table. | report_id: int; page_id: int; body: dict | object {role_ids} | Depends(get_current_user); router: [Depends(_report_access_gate)] | set_page_visibility ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L1887) |
| GET | /api/v1/reports/{report_id}/comments | list comments | report_id: int | list comprehension | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org | list_comments ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L1919) |
| POST | /api/v1/reports/{report_id}/comments | add comment | report_id: int; body: dict | object {id}; HTTP 201 | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org | add_comment ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L1934) |
| DELETE | /api/v1/reports/{report_id}/comments/{comment_id} | delete comment ? Own comments only, unless org admin -- deleting someone's words is a moderation act, not an editing convenience. | report_id: int; comment_id: int | empty response; HTTP 204 | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org | delete_comment ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L1965) |
| POST | /api/v1/reports/{report_id}/share-links | create share link ? Mint a guest link. The plaintext token is returned exactly ONCE; only its sha256 is stored. Anyone holding the URL sees the report as THIS user sees it -- stated in the response so the sharer decides with eyes open. | report_id: int; body: dict | object {id, token, expires_at, pinned, note}; HTTP 201 | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org, require_capability | create_share_link ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L2019) |
| GET | /api/v1/reports/{report_id}/share-links | list share links | report_id: int | list comprehension | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org | list_share_links ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L2066) |
| DELETE | /api/v1/reports/{report_id}/share-links/{link_id} | revoke share link ? Revocation, not deletion: the row stays as the audit trail of what was exposed and when. Own links, or org admin. | report_id: int; link_id: int | empty response; HTTP 204 | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org, require_capability | revoke_share_link ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L2097) |
| GET | /api/v1/reports/{report_id}/translations | list translations | report_id: int | {t.locale: t.payload for t in rows} | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org | list_translations ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L2124) |
| PUT | /api/v1/reports/{report_id}/translations/{locale} | save translation ? Replace one locale's overrides wholesale. Keys are 'w<widgetId>' (title) and 'c<widgetId>' (text-widget content); values are plain strings. An empty payload deletes the locale -- no override rows lingering as empty husks. | report_id: int; locale: str; payload: dict | object {} / clean | Depends(get_current_user); router: [Depends(_report_access_gate)]; Direct checks: check_org, require_capability | save_translation ? [AI_data_tool/data_analytics/backend/app/routers/reports.py](AI_data_tool/data_analytics/backend/app/routers/reports.py#L2135) |


#### review.py

| Method | Full URL | Purpose | Request contract | Response | Authorization boundary | Implementation |
| --- | --- | --- | --- | --- | --- | --- |
| GET | /api/v1/reports/{report_id}/review | review report | report_id: int | object {findings, publish_gate} | Depends(get_current_user); Direct checks: check_org, require_capability | review_report ? [AI_data_tool/data_analytics/backend/app/routers/review.py](AI_data_tool/data_analytics/backend/app/routers/review.py#L42) |
| POST | /api/v1/reports/{report_id}/evaluate-performance | evaluate performance ? Evaluate Performance: every data widget run NOW, uncached, as the caller (so the timing is a real reader's), ranked by cost -- plus each dataset's recorded history from the monitoring table (runs, median and p95 over the last 7 days, cache-? | report_id: int | object {widgets, total_ms, slow_ms, slow, history, measured_at} | Depends(get_current_user); Direct checks: check_org, require_capability | evaluate_performance ? [AI_data_tool/data_analytics/backend/app/routers/review.py](AI_data_tool/data_analytics/backend/app/routers/review.py#L52) |
| GET | /api/v1/review-settings | get review settings | path/auth only | object {publish_gate} | Depends(get_current_user) | get_review_settings ? [AI_data_tool/data_analytics/backend/app/routers/review.py](AI_data_tool/data_analytics/backend/app/routers/review.py#L118) |
| PUT | /api/v1/review-settings | put review settings | body: dict | object {publish_gate} | Depends(require_org_admin) | put_review_settings ? [AI_data_tool/data_analytics/backend/app/routers/review.py](AI_data_tool/data_analytics/backend/app/routers/review.py#L124) |


#### semantic.py

| Method | Full URL | Purpose | Request contract | Response | Authorization boundary | Implementation |
| --- | --- | --- | --- | --- | --- | --- |
| GET | /api/v1/semantic/datasets | catalog | path/auth only | object {datasets} | Depends(get_current_user) | catalog ? [AI_data_tool/data_analytics/backend/app/routers/semantic.py](AI_data_tool/data_analytics/backend/app/routers/semantic.py#L99) |
| POST | /api/v1/semantic/query | query ? `{dataset_id, dimensions: [col...], measures: ["Named measure" &#124; {"column", "agg"}], filters: [{column, op, value}], limit, format: "json"&#124;"csv"}`. | body: dict | _respond(...) | Depends(get_current_user) | query ? [AI_data_tool/data_analytics/backend/app/routers/semantic.py](AI_data_tool/data_analytics/backend/app/routers/semantic.py#L121) |
| GET | /api/v1/semantic/datasets/{dataset_id}/rows | rows ? Secured row-level data, paged (at most 50,000 rows per call). | dataset_id: int; offset: int = 0; limit: int = 10000; columns: str &#124; None = None; format: str = 'json' | _respond(...) | Depends(get_current_user) | rows ? [AI_data_tool/data_analytics/backend/app/routers/semantic.py](AI_data_tool/data_analytics/backend/app/routers/semantic.py#L183) |


#### shared.py

| Method | Full URL | Purpose | Request contract | Response | Authorization boundary | Implementation |
| --- | --- | --- | --- | --- | --- | --- |
| GET | /api/v1/shared/{token} | shared report ? The report's structure plus the rendering context (formats, calc column definitions) -- data itself comes per widget from the sibling route. | token: str | object {name, theme, classification, common_filters, dataset_id, column_formats, geography, calculated_columns, pages, pinned, **spread} | Depends(get_current_user_optional); Direct checks: _resolve_link, sensitivity_gate | shared_report ? [AI_data_tool/data_analytics/backend/app/routers/shared.py](AI_data_tool/data_analytics/backend/app/routers/shared.py#L315) |
| POST | /api/v1/shared/{token}/widget-data/{widget_id} | shared widget data ? One widget's data, resolved from its SAVED config as the effective viewer (S3: the requester's own identity when they're an authenticated in-org user, the creator's otherwise -- see `_resolve_identity`). | token: str; widget_id: int | await _resolve_widget_data(dataset_id, req, db, identity, via_report_id=report.id, redact_columns=await redacted_columns(db, int(dataset_id), label)) | Depends(get_current_user_optional); Direct checks: _resolve_link, sensitivity_gate | shared_widget_data ? [AI_data_tool/data_analytics/backend/app/routers/shared.py](AI_data_tool/data_analytics/backend/app/routers/shared.py#L348) |


#### sso.py

| Method | Full URL | Purpose | Request contract | Response | Authorization boundary | Implementation |
| --- | --- | --- | --- | --- | --- | --- |
| POST | /api/v1/auth/sso/discover | discover ? Tell the login UI whether an email's domain has SSO configured, so it can show a 'Sign in with SSO' button. No secrets, no user existence leaked. | body: DiscoverIn | object {sso, protocol} | No auth dependency declared; protocol/token logic may be inside handler | discover ? [AI_data_tool/data_analytics/backend/app/routers/sso.py](AI_data_tool/data_analytics/backend/app/routers/sso.py#L48) |
| GET | /api/v1/auth/sso/oidc/login | oidc login | email: str | RedirectResponse(...) / resp | No auth dependency declared; protocol/token logic may be inside handler | oidc_login ? [AI_data_tool/data_analytics/backend/app/routers/sso.py](AI_data_tool/data_analytics/backend/app/routers/sso.py#L57) |
| GET | /api/v1/auth/sso/oidc/callback | oidc callback | code: str &#124; None = None; state: str &#124; None = None; error: str &#124; None = None | fail(...) / resp | No auth dependency declared; protocol/token logic may be inside handler | oidc_callback ? [AI_data_tool/data_analytics/backend/app/routers/sso.py](AI_data_tool/data_analytics/backend/app/routers/sso.py#L79) |
| GET | /api/v1/auth/sso/saml/metadata | saml metadata | path/auth only | Response(...) | No auth dependency declared; protocol/token logic may be inside handler | saml_metadata ? [AI_data_tool/data_analytics/backend/app/routers/sso.py](AI_data_tool/data_analytics/backend/app/routers/sso.py#L127) |
| GET | /api/v1/auth/sso/saml/login | saml login | email: str | RedirectResponse(...) | No auth dependency declared; protocol/token logic may be inside handler | saml_login ? [AI_data_tool/data_analytics/backend/app/routers/sso.py](AI_data_tool/data_analytics/backend/app/routers/sso.py#L142) |
| POST | /api/v1/auth/sso/saml/acs | saml acs | SAMLResponse: str = Form(...); RelayState: str &#124; None = Form(None) | fail(...) / RedirectResponse(...) | No auth dependency declared; protocol/token logic may be inside handler | saml_acs ? [AI_data_tool/data_analytics/backend/app/routers/sso.py](AI_data_tool/data_analytics/backend/app/routers/sso.py#L161) |
| GET | /api/v1/auth/sso/config | get config | path/auth only | object {configured} / object {configured, **spread} | Depends(require_org_admin) | get_config ? [AI_data_tool/data_analytics/backend/app/routers/sso.py](AI_data_tool/data_analytics/backend/app/routers/sso.py#L213) |
| PUT | /api/v1/auth/sso/config | put config | body: IdpConfigIn | object {configured, **spread} | Depends(require_org_admin) | put_config ? [AI_data_tool/data_analytics/backend/app/routers/sso.py](AI_data_tool/data_analytics/backend/app/routers/sso.py#L222) |
| DELETE | /api/v1/auth/sso/config | delete config | path/auth only | empty response; HTTP 204 | Depends(require_org_admin) | delete_config ? [AI_data_tool/data_analytics/backend/app/routers/sso.py](AI_data_tool/data_analytics/backend/app/routers/sso.py#L260) |


#### widget_data.py

| Method | Full URL | Purpose | Request contract | Response | Authorization boundary | Implementation |
| --- | --- | --- | --- | --- | --- | --- |
| POST | /api/v1/datasets/{dataset_id}/widget-data | query widget | dataset_id: int; req: WidgetDataRequest | await _resolve_widget_data(dataset_id, req, db, current_user) | Depends(get_current_user) | query_widget ? [AI_data_tool/data_analytics/backend/app/routers/widget_data.py](AI_data_tool/data_analytics/backend/app/routers/widget_data.py#L437) |
| POST | /api/v1/datasets/{dataset_id}/widget-data/export | export widget ? Download one widget's data as CSV or Excel. | dataset_id: int; req: WidgetDataRequest; format: str = 'csv' | StreamingResponse(...) | Depends(get_current_user); Direct checks: download_gate | export_widget ? [AI_data_tool/data_analytics/backend/app/routers/widget_data.py](AI_data_tool/data_analytics/backend/app/routers/widget_data.py#L445) |


#### widget_templates.py

| Method | Full URL | Purpose | Request contract | Response | Authorization boundary | Implementation |
| --- | --- | --- | --- | --- | --- | --- |
| GET | /api/v1/widget-templates | list templates | path/auth only | list comprehension | Depends(get_current_user) | list_templates ? [AI_data_tool/data_analytics/backend/app/routers/widget_templates.py](AI_data_tool/data_analytics/backend/app/routers/widget_templates.py#L33) |
| POST | /api/v1/widget-templates | create template | body: TemplateCreate | _out(...); HTTP 201 | Depends(get_current_user) | create_template ? [AI_data_tool/data_analytics/backend/app/routers/widget_templates.py](AI_data_tool/data_analytics/backend/app/routers/widget_templates.py#L43) |
| DELETE | /api/v1/widget-templates/{template_id} | delete template | template_id: int | empty response; HTTP 204 | Depends(get_current_user); Direct checks: check_org | delete_template ? [AI_data_tool/data_analytics/backend/app/routers/widget_templates.py](AI_data_tool/data_analytics/backend/app/routers/widget_templates.py#L64) |


#### workspace.py

| Method | Full URL | Purpose | Request contract | Response | Authorization boundary | Implementation |
| --- | --- | --- | --- | --- | --- | --- |
| GET | /api/v1/workspace/tree | get tree ? The whole org tree, plus any report that has not been filed. | path/auth only | WorkspaceTreeOut | Depends(get_current_user) | get_tree ? [AI_data_tool/data_analytics/backend/app/routers/workspace.py](AI_data_tool/data_analytics/backend/app/routers/workspace.py#L266) |
| POST | /api/v1/workspace/nodes | create node | body: WorkspaceNodeCreate | WorkspaceNodeOut; HTTP 201 | Depends(get_current_user); Direct checks: check_org | create_node ? [AI_data_tool/data_analytics/backend/app/routers/workspace.py](AI_data_tool/data_analytics/backend/app/routers/workspace.py#L363) |
| PATCH | /api/v1/workspace/nodes/{node_id} | update node | node_id: int; body: WorkspaceNodeUpdate | WorkspaceNodeOut | Depends(get_current_user) | update_node ? [AI_data_tool/data_analytics/backend/app/routers/workspace.py](AI_data_tool/data_analytics/backend/app/routers/workspace.py#L409) |
| DELETE | /api/v1/workspace/nodes/{node_id} | delete node ? Remove a node. Reports are never deleted. | node_id: int | empty response; HTTP 204 | Depends(get_current_user) | delete_node ? [AI_data_tool/data_analytics/backend/app/routers/workspace.py](AI_data_tool/data_analytics/backend/app/routers/workspace.py#L452) |
| GET | /api/v1/workspace/nodes/{node_id}/roles | get node roles ? Roles this folder is restricted to. Empty means everyone in the org. | node_id: int | list[int] | Depends(get_current_user) | get_node_roles ? [AI_data_tool/data_analytics/backend/app/routers/workspace.py](AI_data_tool/data_analytics/backend/app/routers/workspace.py#L486) |
| PUT | /api/v1/workspace/nodes/{node_id}/roles | set node roles ? Restrict a folder to these roles. An EMPTY list removes the restriction. | node_id: int; role_ids: list[int] | list[int] | Depends(get_current_user) | set_node_roles ? [AI_data_tool/data_analytics/backend/app/routers/workspace.py](AI_data_tool/data_analytics/backend/app/routers/workspace.py#L499) |
| GET | /api/v1/workspace/share-options | share options ? The names any member may need to ADDRESS a share: this org's roles and org units, id + name only. Role names are already non-secret via /reports/roles/lite; unit names get the same treatment here because a NON-ADMIN folder author may share ? | path/auth only | object {roles, org_units} | Depends(get_current_user) | share_options ? [AI_data_tool/data_analytics/backend/app/routers/workspace.py](AI_data_tool/data_analytics/backend/app/routers/workspace.py#L574) |
| GET | /api/v1/workspace/nodes/{node_id}/grants | get node grants ? Who this folder is shared with. Manager-only, like the roles pair: the share list is the author's ledger, not a grantee's directory. | node_id: int | list[WorkspaceGrantOut] | Depends(get_current_user) | get_node_grants ? [AI_data_tool/data_analytics/backend/app/routers/workspace.py](AI_data_tool/data_analytics/backend/app/routers/workspace.py#L602) |
| PUT | /api/v1/workspace/nodes/{node_id}/grants | set node grants ? Replace this folder's share list. An EMPTY list unshares it. | node_id: int; body: list[WorkspaceGrantIn] | list[WorkspaceGrantOut] | Depends(get_current_user) | set_node_grants ? [AI_data_tool/data_analytics/backend/app/routers/workspace.py](AI_data_tool/data_analytics/backend/app/routers/workspace.py#L613) |


#### Health endpoints

| Method | Path | Response / access |
| --- | --- | --- |
| GET | /health | Public static liveness: status ok |
| GET | /health/live | Public liveness alias |
| GET | /health/ready | Public DB/startup/cache checks; 200 or 503 |



Shared schema inventory: this lists declared fields and validators, including weakly typed dict/Any boundaries, rather than claiming that all nested report configuration is validated.

### Pydantic request/response contracts

Shared schemas and router-local BaseModel fields are listed. Inherited fields remain inherited. Validators contain additional constraints; plain dict payloads are validated inside route bodies.

#### schemas/schemas.py

| Model | Declared fields/defaults | Validators | Source |
| --- | --- | --- | --- |
| DatasetColumnOut | id: int [required]; name: str [required]; dtype: str [required]; missing_pct: float = 0; stats: dict = {}; semantic_type: Optional[str] = None | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L6) |
| CalcColumnFormat | type: str = 'none'; decimals: Optional[int] = None; symbol: Optional[str] = None; prefix: Optional[str] = None; suffix: Optional[str] = None; min: Optional[float] = None; max: Optional[float] = None; color: Optional[str] = None; thresholds: Optional[list[float]] = None | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L19) |
| CalcColumnDef | name: str [required]; expression: str [required]; dtype: Optional[str] = None; format: Optional[CalcColumnFormat] = None | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L31) |
| SuggestDashboardsRequest | goal: Optional[str] = Field(default=None, max_length=2000); count: int = Field(default=3, ge=1, le=5) | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L38) |
| CalcColumnPreviewRequest | expression: str [required] | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L50) |
| MeasureDef | name: str [required]; expression: str [required]; default_aggregation: Optional[str] = 'sum'; format: Optional[CalcColumnFormat] = None | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L54) |
| CustomFunctionDef | name: str [required]; params: list[str] = []; expression: str [required] | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L63) |
| CustomFunctionPreviewRequest | params: list[str] = []; expression: str [required]; sample_values: dict[str, Any] = {} | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L71) |
| RefreshScheduleUpdate | interval_minutes: Optional[int] = None | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L81) |
| DatasetRefreshRequest | mode: str = 'full'; cursor_column: Optional[str] = None | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L85) |
| ColumnMeta | role: Optional[str] = None; boundary_set_id: Optional[int] = None; aggregation: Optional[str] = None; hidden: Optional[bool] = None; label: Optional[str] = None; eligible_for_suggestion: Optional[bool] = None; target_candidate_priority: Optional[int] = None | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L93) |
| DataViewDefault | default: bool [required] | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L130) |
| ColumnMetaUpdate | meta: dict[str, ColumnMeta] = {} | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L135) |
| MeasurePreviewRequest | expression: str [required]; group_by: Optional[str] = None | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L141) |
| DataPreviewRequest | filters: list[dict] = []; calculated_columns: list[Any] = []; sort_by: Optional[str] = None; sort_dir: str = 'asc'; search: Optional[str] = None; limit: int = 100; offset: int = 0 | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L146) |
| ColumnFormatRequest | column: str [required]; format: Optional[CalcColumnFormat] = None | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L156) |
| FilterExprUpdate | expression: Optional[str] = None | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L161) |
| FilterPreviewRequest | expression: str [required]; calculated_columns: list[Any] = [] | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L165) |
| DatasetOut | id: int [required]; name: str [required]; description: Optional[str] = None; filename: Optional[str] = None; row_count: int = 0; col_count: int = 0; file_size: int = 0; created_at: datetime [required]; updated_at: datetime [required]; columns: list[DatasetColumnOut] = []; calculated_columns: list[Any] = []; column_formats: dict = {}; column_meta: dict = {}; default_filter_expr: Optional[str] = None; data_source_id: Optional[int] = None; source_table: Optional[str] = None; source_query: Optional[str] = None; query_model: Optional[dict] = None; mode: str = 'import'; refresh_interval_minutes: Optional[int] = None; last_refreshed_at: Optional[datetime] = None; aggregate_of_dataset_id: int &#124; None = None; aggregate_spec: dict &#124; None = None; refresh_warning: Optional[str] = None; shared: bool = False; column_descriptions: dict[str, str] = {}; value_labels: dict[str, dict[str, str]] = {}; grain: Optional[str] = None; business_name: Optional[str] = None; column_targets: dict[str, int] = {}; ineligible_columns: list[str] = [] | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L170) |
| MaterializeRequest | name: str [required]; description: Optional[str] = None; steps: Optional[list[dict]] = None | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L234) |
| AggregateMeasure | column: str [required]; agg: str [required]; name: str &#124; None = None | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L246) |
| AggregateCreateRequest | name: str [required]; grain: list[str] [required]; measures: list[AggregateMeasure] [required]; refresh_interval_minutes: int &#124; None = None | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L252) |
| AggregateUpdateRequest | grain: list[str] &#124; None = None; measures: list[AggregateMeasure] &#124; None = None; refresh_interval_minutes: int &#124; None = None | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L262) |
| BatchUploadItem | source_filename: str [required]; status: str [required]; dataset: Optional[DatasetOut] = None; error: Optional[str] = None | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L271) |
| BatchUploadOut | items: list[BatchUploadItem] = []; created: int = 0; failed: int = 0; mode: str = 'separate' | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L286) |
| AnalysisRequest | analysis_type: str = 'full' | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L293) |
| AssociationRulesRequest | columns: Optional[list[str]] = None | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L297) |
| SegmentRequest | columns: Optional[list[str]] = None; include_rows: bool = False | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L303) |
| KeyInfluencersRequest | target: str [required]; target_value: Optional[str] = None; factors: Optional[list[str]] = None | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L313) |
| WidgetCreate | widget_type: str [required]; title: Optional[str] = None; config: dict = {}; layout: dict = {'x': 0, 'y': 0, 'w': 6, 'h': 4} | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L324) |
| WidgetUpdate | widget_type: Optional[str] = None; title: Optional[str] = None; config: Optional[dict] = None; layout: Optional[dict] = None | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L331) |
| WidgetOut | id: int [required]; page_id: int [required]; widget_type: str [required]; title: Optional[str] = None; config: dict = {}; layout: dict = {}; created_at: datetime [required] | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L338) |
| PageCreate | name: str = 'Page 1'; position: int = 0; title: Optional[str] = None; page_type: str = 'normal'; prompt_column: Optional[str] = None; prompt_label: Optional[str] = None; page_size: str = '16:9'; custom_width: Optional[int] = None; custom_height: Optional[int] = None; mobile_layout: Optional[dict] = None; layout_mode: Optional[str] = 'packed'; layout_template: Optional[str] = 'executive' | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L349) |
| PageUpdate | name: Optional[str] = None; background_url: Optional[str] = None; position: Optional[int] = None; title: Optional[str] = None; page_type: Optional[str] = None; prompt_column: Optional[str] = None; prompt_label: Optional[str] = None; page_size: Optional[str] = None; custom_width: Optional[int] = None; custom_height: Optional[int] = None; mobile_layout: Optional[dict] = None; layout_mode: Optional[str] = None; layout_template: Optional[str] = None | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L364) |
| PageOut | id: int [required]; report_id: int [required]; name: str [required]; title: Optional[str] = None; page_type: str = 'normal'; prompt_column: Optional[str] = None; prompt_label: Optional[str] = None; position: int [required]; widgets: list[WidgetOut] = []; created_at: datetime [required]; page_size: str = '16:9'; custom_width: Optional[int] = None; custom_height: Optional[int] = None; mobile_layout: Optional[dict] = None; background_url: Optional[str] = None; layout_mode: Optional[str] = None; layout_template: Optional[str] = None | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L382) |
| ReportCreate | name: str [required]; description: Optional[str] = None; dataset_id: Optional[int] = None | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L403) |
| ReportUpdate | name: Optional[str] = None; description: Optional[str] = None; dataset_id: Optional[int] = None; additional_dataset_ids: Optional[list[int]] = None; theme: Optional[str] = None; display_rules: Optional[list[dict]] = None | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L409) |
| ReportOut | id: int [required]; name: str [required]; description: Optional[str] = None; dataset_id: Optional[int] = None; additional_dataset_ids: list[int] = []; theme: str = 'default'; display_rules: list[dict] = []; revision: int = 0; pages: list[PageOut] = []; created_at: datetime [required]; updated_at: datetime [required]; my_capability: str = 'data'; is_mine: bool = False; created_by: Optional[int] = None; published: bool = False; classification: Optional[str] = None; common_filters: list[dict] = [] | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L418) |
| BookmarkCreate | name: str [required]; position: int = 0; state: dict [required] | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L462) |
| BookmarkOut | id: int [required]; report_id: int [required]; name: str [required]; position: int [required]; state: dict [required]; created_at: datetime [required] | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L468) |
| HierarchyNodeCreate | parent_id: Optional[int] = None; name: str [required]; node_type: str = 'folder'; column_name: Optional[str] = None; aggregation: Optional[str] = None; format: Optional[str] = None; position: int = 0 | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L478) |
| HierarchyNodeUpdate | name: Optional[str] = None; node_type: Optional[str] = None; column_name: Optional[str] = None; aggregation: Optional[str] = None; format: Optional[str] = None; position: Optional[int] = None; parent_id: Optional[int] = None | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L488) |
| HierarchyNodeOut | id: int [required]; dataset_id: int [required]; parent_id: Optional[int] = None; name: str [required]; node_type: str [required]; column_name: Optional[str] = None; aggregation: Optional[str] = None; format: Optional[str] = None; position: int [required]; created_at: datetime [required] | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L498) |
| WidgetDataRequest | config: dict [required]; calculated_columns: list[Any] = []; widget_type: str = 'bar'; report_id: int &#124; None = None; parameters: dict[str, Any] = {} | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L512) |
| WidgetDataResponse | type: str [required]; rows: list[Any] = []; total: int = 0; columns: Optional[list[str]] = None; dimension: Optional[str] = None; measure: Optional[str] = None; aggregation: Optional[str] = None | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L523) |
| DataSourceCreate | name: str [required]; type: str [required]; config: dict = {}; custom_connector_id: Optional[int] = None | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L533) |
| DataSourceUpdate | name: Optional[str] = None; type: Optional[str] = None; config: Optional[dict] = None; cache_ttl_seconds: Optional[int] = None; custom_connector_id: Optional[int] = None | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L539) |
| DataSourceOut | id: int [required]; name: str [required]; type: str [required]; config: dict = {}; cache_ttl_seconds: int = 60; created_at: datetime [required]; custom_connector_id: Optional[int] = None; custom_connector_label: Optional[str] = None; sync_run_id: Optional[int] = None | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L546) |
| CustomConnectorCreate | key: str [required]; label: str [required]; base_type: str [required]; base_config: dict = {}; locked_fields: list[str] = [] | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L563) |
| CustomConnectorUpdate | key: Optional[str] = None; label: Optional[str] = None; base_type: Optional[str] = None; base_config: Optional[dict] = None; locked_fields: Optional[list[str]] = None | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L570) |
| CustomConnectorOut | id: int [required]; key: str [required]; label: str [required]; base_type: str [required]; base_config: dict = {}; locked_fields: list[str] = []; created_at: datetime [required] | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L577) |
| TablePreviewRequest | table: Optional[str] = None; query: Optional[str] = None; limit: int = 200 | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L587) |
| ImportRequest | dataset_name: str [required]; table: Optional[str] = None; query: Optional[str] = None; mode: str = 'import'; query_model: Optional[dict] = None; dataset_id: Optional[int] = None | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L592) |
| OrganizationOut | id: int [required]; name: str [required] | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L606) |
| RoleOut | id: int [required]; name: str [required]; is_org_admin: bool [required] | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L612) |
| UserOut | id: int [required]; email: str [required]; is_active: bool [required]; organization: OrganizationOut [required]; role: RoleOut [required]; is_super_admin: bool = False | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L619) |
| LoginRequest | email: str [required]; password: str [required] | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L631) |
| TokenOut | access_token: str [required]; token_type: str = 'bearer' | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L636) |
| RoleCreate | name: str [required]; is_org_admin: bool = False | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L641) |
| RoleUpdate | name: Optional[str] = None; is_org_admin: Optional[bool] = None | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L646) |
| UserCreate | email: str [required]; password: str [required]; role_id: int [required] | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L651) |
| UserUpdate | email: Optional[str] = None; password: Optional[str] = None; role_id: Optional[int] = None; is_active: Optional[bool] = None | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L657) |
| BulkUserRow | email: str [required]; password: str [required]; role: str [required] | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L664) |
| BulkUserCreate | users: list[BulkUserRow] [required] | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L671) |
| RowSecurityRuleCreate | role_id: int [required]; dataset_id: int [required]; filter_expr: str [required] | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L675) |
| RowSecurityRuleUpdate | filter_expr: str [required] | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L681) |
| RowSecurityRuleOut | id: int [required]; role_id: int [required]; dataset_id: int [required]; filter_expr: str [required]; auto_generated: bool = False; created_at: datetime [required] | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L685) |
| RlsAutoGenerateRequest | dataset_id: int [required]; role_id: Optional[int] = None; apply: bool = False; columns: Optional[list[str]] = None | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L695) |
| DatasetShareCreate | user_id: int [required] | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L705) |
| DatasetShareOut | id: int [required]; user_id: int [required]; email: str [required]; created_at: datetime [required] | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L709) |
| RelationshipCreate | from_dataset_id: int [required]; from_column: str [required]; to_dataset_id: int [required]; to_column: str [required] | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L716) |
| RelationshipOut | id: int [required]; org_id: int [required]; from_dataset_id: int [required]; from_column: str [required]; to_dataset_id: int [required]; to_column: str [required]; created_at: datetime [required]; source: str = 'declared'; confidence: float = 1.0; cardinality: Optional[str] = None | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L723) |
| WorkspaceNodeCreate | parent_id: Optional[int] = None; node_type: str = 'folder'; name: Optional[str] = None; report_id: Optional[int] = None; position: int = 0 | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L745) |
| WorkspaceNodeUpdate | name: Optional[str] = None; parent_id: Optional[int] = None; position: Optional[int] = None; published: Optional[bool] = None | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L759) |
| WorkspacePageOut | id: int [required]; name: str [required]; position: int [required] | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L770) |
| WorkspaceNodeOut | id: int [required]; parent_id: Optional[int] = None; node_type: str [required]; name: Optional[str] = None; report_id: Optional[int] = None; position: int [required]; can_manage: bool = False; is_mine: bool = False; my_capability: str = 'data'; published: bool = False; role_ids: list[int] = []; shared_with_me: bool = False; pages: list[WorkspacePageOut] = []; children: list['WorkspaceNodeOut'] = [] | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L780) |
| WorkspaceGrantIn | user_id: Optional[int] = None; user_email: Optional[str] = None; role_id: Optional[int] = None; org_unit_id: Optional[int] = None; level: str = 'view' | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L820) |
| WorkspaceGrantOut | id: int [required]; level: str [required]; user_id: Optional[int] = None; user_email: Optional[str] = None; role_id: Optional[int] = None; role_name: Optional[str] = None; org_unit_id: Optional[int] = None; org_unit_name: Optional[str] = None | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L835) |
| WorkspaceTreeOut | roots: list[WorkspaceNodeOut] = []; unfiled: list[WorkspaceNodeOut] = [] | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L849) |
| CompareGroupsRequest | value_col: str [required]; group_col: str [required] | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L861) |
| IndependenceRequest | col_a: str [required]; col_b: str [required] | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L866) |
| CorrelationTestRequest | col_a: str [required]; col_b: str [required]; method: str = 'pearson' | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L871) |
| RegressionRequest | target: str [required]; predictors: list[str] [required] | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L877) |
| GlmLogisticRequest | target: str [required]; predictors: list[str] [required]; target_value: str &#124; None = None | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L882) |
| MixedModelRequest | target: str [required]; predictors: list[str] [required]; group_col: str [required] | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L888) |
| SurvivalRequest | duration_col: str [required]; event_col: str [required]; predictors: list[str] [required] | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L894) |
| PairwiseRequest | value_col: str [required]; group_col: str [required]; method: str = 'holm' | ? | [AI_data_tool/data_analytics/backend/app/schemas/schemas.py](AI_data_tool/data_analytics/backend/app/schemas/schemas.py#L900) |


#### routers/agent.py

| Model | Declared fields/defaults | Validators | Source |
| --- | --- | --- | --- |
| ConversationIn | data_source_id: int &#124; None = None; dataset_ids: list[int] &#124; None = None; title: str &#124; None = None | ? | [AI_data_tool/data_analytics/backend/app/routers/agent.py](AI_data_tool/data_analytics/backend/app/routers/agent.py#L53) |
| AskIn | question: str [required] | ? | [AI_data_tool/data_analytics/backend/app/routers/agent.py](AI_data_tool/data_analytics/backend/app/routers/agent.py#L59) |
| RowPolicyIn | source_object_id: int [required]; role_id: int [required]; predicate: str [required] | ? | [AI_data_tool/data_analytics/backend/app/routers/agent.py](AI_data_tool/data_analytics/backend/app/routers/agent.py#L63) |
| FeedbackIn | run_id: int &#124; None = None; rating: str [required]; comment: str &#124; None = None | ? | [AI_data_tool/data_analytics/backend/app/routers/agent.py](AI_data_tool/data_analytics/backend/app/routers/agent.py#L69) |
| TitleIn | title: str [required] | ? | [AI_data_tool/data_analytics/backend/app/routers/agent.py](AI_data_tool/data_analytics/backend/app/routers/agent.py#L75) |


#### routers/analysis.py

| Model | Declared fields/defaults | Validators | Source |
| --- | --- | --- | --- |
| NarrateRequest | finding: dict [required] | ? | [AI_data_tool/data_analytics/backend/app/routers/analysis.py](AI_data_tool/data_analytics/backend/app/routers/analysis.py#L38) |
| RunAnalysisRequest | name: str [required]; params: dict = {} | ? | [AI_data_tool/data_analytics/backend/app/routers/analysis.py](AI_data_tool/data_analytics/backend/app/routers/analysis.py#L566) |


#### routers/auth.py

| Model | Declared fields/defaults | Validators | Source |
| --- | --- | --- | --- |
| ApiKeyCreate | name: str = Field(min_length=1, max_length=120) | ? | [AI_data_tool/data_analytics/backend/app/routers/auth.py](AI_data_tool/data_analytics/backend/app/routers/auth.py#L53) |


#### routers/data_sources.py

| Model | Declared fields/defaults | Validators | Source |
| --- | --- | --- | --- |
| SimilarDatasetsRequest | columns: list[str] = Field(default_factory=list, max_length=500); table: str &#124; None = Field(default=None, max_length=500); query: str &#124; None = None | ? | [AI_data_tool/data_analytics/backend/app/routers/data_sources.py](AI_data_tool/data_analytics/backend/app/routers/data_sources.py#L612) |


#### routers/dataflows.py

| Model | Declared fields/defaults | Validators | Source |
| --- | --- | --- | --- |
| DataflowIn | name: str [required]; description: str &#124; None = None; source_dataset_id: int [required]; steps: list[dict] = []; refresh_interval_minutes: int &#124; None = None | ? | [AI_data_tool/data_analytics/backend/app/routers/dataflows.py](AI_data_tool/data_analytics/backend/app/routers/dataflows.py#L49) |
| DataflowPatch | name: str &#124; None = None; description: str &#124; None = None; steps: list[dict] &#124; None = None; refresh_interval_minutes: int &#124; None = None | ? | [AI_data_tool/data_analytics/backend/app/routers/dataflows.py](AI_data_tool/data_analytics/backend/app/routers/dataflows.py#L57) |
| RunRequest | output_name: str &#124; None = None | ? | [AI_data_tool/data_analytics/backend/app/routers/dataflows.py](AI_data_tool/data_analytics/backend/app/routers/dataflows.py#L64) |
| CapabilityGrant | role_id: int [required]; level: str [required] | ? | [AI_data_tool/data_analytics/backend/app/routers/dataflows.py](AI_data_tool/data_analytics/backend/app/routers/dataflows.py#L74) |
| CapabilitiesIn | grants: list[CapabilityGrant] [required] | ? | [AI_data_tool/data_analytics/backend/app/routers/dataflows.py](AI_data_tool/data_analytics/backend/app/routers/dataflows.py#L79) |


#### routers/datasets.py

| Model | Declared fields/defaults | Validators | Source |
| --- | --- | --- | --- |
| ColumnDescriptionIn | description: str = Field(max_length=2000) | ? | [AI_data_tool/data_analytics/backend/app/routers/datasets.py](AI_data_tool/data_analytics/backend/app/routers/datasets.py#L1212) |


#### routers/metadata.py

| Model | Declared fields/defaults | Validators | Source |
| --- | --- | --- | --- |
| ConfirmRequest | relationship_ids: list[int] = Field(default_factory=list); rejected_relationship_ids: list[int] = Field(default_factory=list); column_updates: list[dict] = Field(default_factory=list); object_updates: list[dict] = Field(default_factory=list) | ? | [AI_data_tool/data_analytics/backend/app/routers/metadata.py](AI_data_tool/data_analytics/backend/app/routers/metadata.py#L46) |
| SourceSettings | allow_llm_sampling: bool &#124; None = None; description: str &#124; None = None | ? | [AI_data_tool/data_analytics/backend/app/routers/metadata.py](AI_data_tool/data_analytics/backend/app/routers/metadata.py#L363) |
| GlossaryIn | term: str [required]; definition: str &#124; None = None; synonyms: list[str] = Field(default_factory=list); maps_to_object: str &#124; None = None; maps_to_column: str &#124; None = None | ? | [AI_data_tool/data_analytics/backend/app/routers/metadata.py](AI_data_tool/data_analytics/backend/app/routers/metadata.py#L438) |
| EntityUpdate | id: int [required]; business_name: str &#124; None = None; grain: str &#124; None = None; description: str &#124; None = None; confirm: bool = False | ? | [AI_data_tool/data_analytics/backend/app/routers/metadata.py](AI_data_tool/data_analytics/backend/app/routers/metadata.py#L530) |
| EntityConfirmRequest | updates: list[EntityUpdate] = Field(default_factory=list) | ? | [AI_data_tool/data_analytics/backend/app/routers/metadata.py](AI_data_tool/data_analytics/backend/app/routers/metadata.py#L540) |
| SuggestDashboardIn | for_role: str = Field(min_length=1, max_length=100); goal: str &#124; None = Field(default=None, max_length=500) | ? | [AI_data_tool/data_analytics/backend/app/routers/metadata.py](AI_data_tool/data_analytics/backend/app/routers/metadata.py#L665) |


#### routers/pins.py

| Model | Declared fields/defaults | Validators | Source |
| --- | --- | --- | --- |
| PinCreate | widget_id: int &#124; None = None; dataset_id: int &#124; None = None; finding_key: str &#124; None = None | ? | [AI_data_tool/data_analytics/backend/app/routers/pins.py](AI_data_tool/data_analytics/backend/app/routers/pins.py#L37) |
| PinUpdate | position: int &#124; None = None; size: str &#124; None = None | ? | [AI_data_tool/data_analytics/backend/app/routers/pins.py](AI_data_tool/data_analytics/backend/app/routers/pins.py#L45) |


#### routers/platform.py

| Model | Declared fields/defaults | Validators | Source |
| --- | --- | --- | --- |
| OrgCreate | name: str = Field(min_length=1, max_length=255); admin_email: str = Field(min_length=3, max_length=255); admin_password: str = Field(min_length=1) | ? | [AI_data_tool/data_analytics/backend/app/routers/platform.py](AI_data_tool/data_analytics/backend/app/routers/platform.py#L25) |
| OrgQuotaSet | max_queries_per_day: int &#124; None = None; max_agent_asks_per_day: int &#124; None = None; max_storage_mb: int &#124; None = None; max_concurrent_asks: int &#124; None = None | ? | [AI_data_tool/data_analytics/backend/app/routers/platform.py](AI_data_tool/data_analytics/backend/app/routers/platform.py#L101) |
| OrgMcpSet | enabled: bool [required] | ? | [AI_data_tool/data_analytics/backend/app/routers/platform.py](AI_data_tool/data_analytics/backend/app/routers/platform.py#L155) |
| OrgParentSet | parent_org_id: int &#124; None = None | ? | [AI_data_tool/data_analytics/backend/app/routers/platform.py](AI_data_tool/data_analytics/backend/app/routers/platform.py#L173) |


#### routers/prediction_models.py

| Model | Declared fields/defaults | Validators | Source |
| --- | --- | --- | --- |
| TrainRequest | name: str [required]; target: str [required]; predictors: list[str] &#124; None = None; partition: str &#124; None = None | ? | [AI_data_tool/data_analytics/backend/app/routers/prediction_models.py](AI_data_tool/data_analytics/backend/app/routers/prediction_models.py#L43) |
| ScoreRequest | rows: list[dict] &#124; None = None; from_dataset: bool = False; limit: int = 5000 | ? | [AI_data_tool/data_analytics/backend/app/routers/prediction_models.py](AI_data_tool/data_analytics/backend/app/routers/prediction_models.py#L53) |


#### routers/report_copilot.py

| Model | Declared fields/defaults | Validators | Source |
| --- | --- | --- | --- |
| CopilotIn | message: str [required]; history: list[dict] = Field(default_factory=list); selected_widget_id: int &#124; None = None | ? | [AI_data_tool/data_analytics/backend/app/routers/report_copilot.py](AI_data_tool/data_analytics/backend/app/routers/report_copilot.py#L43) |


#### routers/sso.py

| Model | Declared fields/defaults | Validators | Source |
| --- | --- | --- | --- |
| DiscoverIn | email: str = Field(min_length=1, max_length=320) | ? | [AI_data_tool/data_analytics/backend/app/routers/sso.py](AI_data_tool/data_analytics/backend/app/routers/sso.py#L40) |
| IdpConfigIn | protocol: str = 'oidc'; enabled: bool = True; email_domain: str = Field(min_length=1, max_length=255); issuer: str = Field(default='', max_length=500); client_id: str = Field(default='', max_length=255); client_secret: str &#124; None = None; config: dict = Field(default_factory=dict) | ? | [AI_data_tool/data_analytics/backend/app/routers/sso.py](AI_data_tool/data_analytics/backend/app/routers/sso.py#L202) |


#### routers/widget_templates.py

| Model | Declared fields/defaults | Validators | Source |
| --- | --- | --- | --- |
| TemplateCreate | name: str = Field(min_length=1, max_length=255); widget_type: str = Field(min_length=1, max_length=50); config: dict = {} | ? | [AI_data_tool/data_analytics/backend/app/routers/widget_templates.py](AI_data_tool/data_analytics/backend/app/routers/widget_templates.py#L21) |



### Service and core module map

Descriptions condense module documentation; central behaviors were separately traced above. Symbols form an index, not a claim all helpers are public APIs. Known stale comments and reachability gaps are called out in the narrative.


| Module | Role / module description | Main classes and functions |
| --- | --- | --- |
| [AI_data_tool/data_analytics/backend/app/services/admin_audit.py](AI_data_tool/data_analytics/backend/app/services/admin_audit.py) | Writing admin-plane security audit entries (S5). | record |
| [AI_data_tool/data_analytics/backend/app/services/agent/charts.py](AI_data_tool/data_analytics/backend/app/services/agent/charts.py) | Which two columns a chart of this result should use -- or why it cannot. | pick_axes, validated_axes |
| [AI_data_tool/data_analytics/backend/app/services/agent/context.py](AI_data_tool/data_analytics/backend/app/services/agent/context.py) | What the agent may know about a source. | ObjectInfo, JoinInfo, GlossaryInfo, EntityInfo, SchemaContext, suggest_join_route, load_context, dataset_table_names, load_dataset_context |
| [AI_data_tool/data_analytics/backend/app/services/agent/dag.py](AI_data_tool/data_analytics/backend/app/services/agent/dag.py) | Run a step DAG in topological layers under one bounded gate. | topological_layers, run_dag |
| [AI_data_tool/data_analytics/backend/app/services/agent/executor.py](AI_data_tool/data_analytics/backend/app/services/agent/executor.py) | V5 (dry run) + execution + sanity — the only module that touches the customer's database, and it does so bounded in three ways: a statement timeout, an injected row cap, and to_thread so a slow query never holds the event loop (the lesson the whole app relearned when infer_keys froze it for four minutes). | execute_sql, execute_on_datasets, sanity_check |
| [AI_data_tool/data_analytics/backend/app/services/agent/export.py](AI_data_tool/data_analytics/backend/app/services/agent/export.py) | Chat results as files: the stored snapshot serialized to Excel or PDF. | trunc_note, build_result_xlsx, build_result_pdf |
| [AI_data_tool/data_analytics/backend/app/services/agent/graph.py](AI_data_tool/data_analytics/backend/app/services/agent/graph.py) | One question's journey: classify -> (clarify) -> context -> plan -> DAG of [generate -> ladder -> policy -> execute -> sanity] -> explain. | run_agent, step_question |
| [AI_data_tool/data_analytics/backend/app/services/agent/memory.py](AI_data_tool/data_analytics/backend/app/services/agent/memory.py) | query_examples: verified question->SQL pairs, recalled as few-shot. | recall, remember |
| [AI_data_tool/data_analytics/backend/app/services/agent/nodes/analyze.py](AI_data_tool/data_analytics/backend/app/services/agent/nodes/analyze.py) | Choose an analysis for a question that SQL answers in the wrong shape. | choose_analysis |
| [AI_data_tool/data_analytics/backend/app/services/agent/nodes/clarify.py](AI_data_tool/data_analytics/backend/app/services/agent/nodes/clarify.py) | D4.3: ask, do not guess. This node turns the classifier's ambiguity reason into one short question for the person; the run ends with status `needs_clarification`, and the user's reply arrives as a fresh question. | clarify |
| [AI_data_tool/data_analytics/backend/app/services/agent/nodes/classify.py](AI_data_tool/data_analytics/backend/app/services/agent/nodes/classify.py) | Intent + ambiguity, under the enforced JSON contract. | is_dashboard_request, classify |
| [AI_data_tool/data_analytics/backend/app/services/agent/nodes/converse.py](AI_data_tool/data_analytics/backend/app/services/agent/nodes/converse.py) | The reply to a message that is not a question about the data. | converse |
| [AI_data_tool/data_analytics/backend/app/services/agent/nodes/copilot.py](AI_data_tool/data_analytics/backend/app/services/agent/nodes/copilot.py) | The page copilot's brain: one chat message about an OPEN dashboard page. | render_page_context, render_history, resolve_copilot |
| [AI_data_tool/data_analytics/backend/app/services/agent/nodes/explain.py](AI_data_tool/data_analytics/backend/app/services/agent/nodes/explain.py) | The answer, with provenance — and a deterministic fallback, because a correctly computed result must not be discarded when prose generation fails. | render_fallback, describe, explain |
| [AI_data_tool/data_analytics/backend/app/services/agent/nodes/followup.py](AI_data_tool/data_analytics/backend/app/services/agent/nodes/followup.py) | A new message, read against the conversation so far. | render_history, last_result, resolve |
| [AI_data_tool/data_analytics/backend/app/services/agent/nodes/generate.py](AI_data_tool/data_analytics/backend/app/services/agent/nodes/generate.py) | SQL generation — one attempt, under the enforced contract. | generate_sql |
| [AI_data_tool/data_analytics/backend/app/services/agent/overview.py](AI_data_tool/data_analytics/backend/app/services/agent/overview.py) | What the data in scope IS, read from the catalog rather than guessed. | catalog_overview |
| [AI_data_tool/data_analytics/backend/app/services/agent/plan.py](AI_data_tool/data_analytics/backend/app/services/agent/plan.py) | Question -> typed step DAG. | plan_steps |
| [AI_data_tool/data_analytics/backend/app/services/agent/policy.py](AI_data_tool/data_analytics/backend/app/services/agent/policy.py) | V4 — row policies injected into the parsed AST. | PolicyError, apply_policies, load_policies |
| [AI_data_tool/data_analytics/backend/app/services/agent/results.py](AI_data_tool/data_analytics/backend/app/services/agent/results.py) | Result snapshots: the rows a sink step returned, made small and JSON-safe. | redact_credentials, coerce_scalar, snapshot_rows |
| [AI_data_tool/data_analytics/backend/app/services/agent/state.py](AI_data_tool/data_analytics/backend/app/services/agent/state.py) | Typed state passed between the agent's nodes. | StepSpec, StepResult, sink_step_ids |
| [AI_data_tool/data_analytics/backend/app/services/agent/validate.py](AI_data_tool/data_analytics/backend/app/services/agent/validate.py) | The validation ladder, rungs V1-V3 and V6 (V4 is policy.py, V5 lives in executor.py; V6 — column security — runs here because it is an AST check). | ValidationFailure, validate_sql |
| [AI_data_tool/data_analytics/backend/app/services/aggregates.py](AI_data_tool/data_analytics/backend/app/services/aggregates.py) | Compiling an aggregate dataset from a DirectQuery source. | AggregateSpecError, normalise_spec, compile_aggregate_sql, rls_columns_outside_grain, uncovered_message, aggregate_staleness, derived_measure_names |
| [AI_data_tool/data_analytics/backend/app/services/alerts.py](AI_data_tool/data_analytics/backend/app/services/alerts.py) | Evaluating data alerts on their schedule. | condition_holds, check_alert |
| [AI_data_tool/data_analytics/backend/app/services/analysis/anomaly.py](AI_data_tool/data_analytics/backend/app/services/analysis/anomaly.py) | A3: PyOD anomaly detectors (iforest, ecod) alongside the pre-existing IQR fence path used by the `outlier-details` endpoint (routers/datasets.py). | AnomalyError, detect |
| [AI_data_tool/data_analytics/backend/app/services/analysis/automated_prediction.py](AI_data_tool/data_analytics/backend/app/services/analysis/automated_prediction.py) | Fit several models, name the one that wins — and say whether it earned it. | AutomatedPredictionError, automated_prediction |
| [AI_data_tool/data_analytics/backend/app/services/analysis/decision_tree.py](AI_data_tool/data_analytics/backend/app/services/analysis/decision_tree.py) | A decision tree: the rules that separate one outcome from another. | DecisionTreeError, decision_tree |
| [AI_data_tool/data_analytics/backend/app/services/analysis/forecast_goal.py](AI_data_tool/data_analytics/backend/app/services/analysis/forecast_goal.py) | `forecast_goal` as a catalogued analysis: forecast a frame, then answer. | forecast_goal_over |
| [AI_data_tool/data_analytics/backend/app/services/analysis/forecast_scenario.py](AI_data_tool/data_analytics/backend/app/services/analysis/forecast_scenario.py) | What if spend rose 10%? — a projection with factors you can move. | ForecastScenarioError, forecast_scenario |
| [AI_data_tool/data_analytics/backend/app/services/analysis/goal_seek.py](AI_data_tool/data_analytics/backend/app/services/analysis/goal_seek.py) | Solve for the factor value a target requires. | GoalSeekError, goal_seek |
| [AI_data_tool/data_analytics/backend/app/services/analysis/inferential.py](AI_data_tool/data_analytics/backend/app/services/analysis/inferential.py) | Inferential statistics: is the difference real, or is it noise? | StatisticalError, TestResult, compare_groups, test_independence, correlation_test, regression, glm_logistic, mixed_model, survival, correct_p_values, pairwise_comparisons, difference_check, safe_json |
| [AI_data_tool/data_analytics/backend/app/services/analysis/influencers.py](AI_data_tool/data_analytics/backend/app/services/analysis/influencers.py) | Key influencers: which factors move a chosen outcome, and by how much. | InfluencerError, key_influencers |
| [AI_data_tool/data_analytics/backend/app/services/analysis/model_store.py](AI_data_tool/data_analytics/backend/app/services/analysis/model_store.py) | Keep the champion, and score rows it has never seen. | ModelStoreError, PackagedModel, fit_and_package, align_frame, score_frame |
| [AI_data_tool/data_analytics/backend/app/services/analysis/patterns.py](AI_data_tool/data_analytics/backend/app/services/analysis/patterns.py) | Association rules: which values travel together. | PatternError, association_rules |
| [AI_data_tool/data_analytics/backend/app/services/analysis/registry.py](AI_data_tool/data_analytics/backend/app/services/analysis/registry.py) | A4: analysis tool catalogue -- single source of truth for what analyses this app can run. | AnalysisSpec, DuplicateAnalysisError, UnknownAnalysisError, NotRunnableError, register, unregister, resolve_handler, run_analysis, all_analyses, get, render_prompt_block |
| [AI_data_tool/data_analytics/backend/app/services/analysis/restricted.py](AI_data_tool/data_analytics/backend/app/services/analysis/restricted.py) | What to tell a viewer whose own access is why an analysis cannot run. | explain_shortfall |
| [AI_data_tool/data_analytics/backend/app/services/analysis/segment.py](AI_data_tool/data_analytics/backend/app/services/analysis/segment.py) | A2: KMeans segmentation with automatic k selection. | SegmentError, segment_dataframe |
| [AI_data_tool/data_analytics/backend/app/services/analysis/text_sentiment.py](AI_data_tool/data_analytics/backend/app/services/analysis/text_sentiment.py) | How do people feel in this free text? — lexicon sentiment, Arabic first. | TextSentimentError, text_sentiment |
| [AI_data_tool/data_analytics/backend/app/services/analysis/text_topics.py](AI_data_tool/data_analytics/backend/app/services/analysis/text_topics.py) | What is this free text about? — topics from a column of comments. | TextTopicsError, text_topics |
| [AI_data_tool/data_analytics/backend/app/services/analysis_contract.py](AI_data_tool/data_analytics/backend/app/services/analysis_contract.py) | A1: uniform internal contract for analysis services. | AnalysisContract, safe_clean, full_profile_to_contract, as_response |
| [AI_data_tool/data_analytics/backend/app/services/analysis_frame.py](AI_data_tool/data_analytics/backend/app/services/analysis_frame.py) | One bounded, secured frame for analysis — whichever mode the dataset is in. | FrameUnavailable, AnalysisFrame, analysis_row_cap, load_directquery_frame, imported_frame |
| [AI_data_tool/data_analytics/backend/app/services/analytics.py](AI_data_tool/data_analytics/backend/app/services/analytics.py) | Analytics Service - descriptive stats, outlier detection, categorical analysis, datetime analysis, correlation. | analyze_numeric, analyze_categorical, analyze_datetime, run_full_analysis |
| [AI_data_tool/data_analytics/backend/app/services/audit.py](AI_data_tool/data_analytics/backend/app/services/audit.py) | Writing audit entries. | record |
| [AI_data_tool/data_analytics/backend/app/services/auth_provisioning.py](AI_data_tool/data_analytics/backend/app/services/auth_provisioning.py) | Implementation module; indexed symbols show its responsibilities | create_organization_with_admin |
| [AI_data_tool/data_analytics/backend/app/services/automation_runner.py](AI_data_tool/data_analytics/backend/app/services/automation_runner.py) | Power Pi: the orchestrator that runs the pipeline nobody is watching. | StepRefused, StepContext, StepSpec, discard_run_artifacts, approve_review, reject_review, record_run_result, describe_run, notify_run, masked_profile_for_model, redact_row_values, create_run, advisory_lock_key, tick, reap_stuck_automation_steps |
| [AI_data_tool/data_analytics/backend/app/services/boundary_sets.py](AI_data_tool/data_analytics/backend/app/services/boundary_sets.py) | Validate a customer-supplied set of map boundaries. | BoundarySetError, validate_boundaries, packs_dir, list_packs, load_pack |
| [AI_data_tool/data_analytics/backend/app/services/cache_backend.py](AI_data_tool/data_analytics/backend/app/services/cache_backend.py) | Task O2: shared result-cache backend abstraction. | CacheBackend, InProcessCache, ValkeyCache |
| [AI_data_tool/data_analytics/backend/app/services/connections.py](AI_data_tool/data_analytics/backend/app/services/connections.py) | Implementation module; indexed symbols show its responsibilities | test_connection, list_tables, preview_table, import_to_dataframe |
| [AI_data_tool/data_analytics/backend/app/services/connectors.py](AI_data_tool/data_analytics/backend/app/services/connectors.py) | The connector registry — the single source of truth for data-source types. | UnknownConnector, ConfigField, ConnectorSpec, resolve, secret_field_names, is_known, all_specs, sql_family_of, connect_args, build_url, assert_valid, catalog_payload |
| [AI_data_tool/data_analytics/backend/app/services/custom_connectors.py](AI_data_tool/data_analytics/backend/app/services/custom_connectors.py) | Custom connector presets: save-time validation and config merging. | CustomConnectorError, validate_custom_connector_def, apply_preset_locks |
| [AI_data_tool/data_analytics/backend/app/services/custom_functions.py](AI_data_tool/data_analytics/backend/app/services/custom_functions.py) | Custom calculated-column functions: named, parameterized expression templates built entirely from the existing safe vocabulary in services.widget_data. A custom function never introduces a new execution primitive -- calling one expands its body into the caller's expression (parameter names substituted with the caller's argument  | CustomFunctionError, validate_custom_function_def, expand_custom_functions |
| [AI_data_tool/data_analytics/backend/app/services/data_views.py](AI_data_tool/data_analytics/backend/app/services/data_views.py) | Reusable data views: snapshot a dataset's semantic layer, apply it elsewhere. | snapshot_dataset, apply_view |
| [AI_data_tool/data_analytics/backend/app/services/dataset_cleanup.py](AI_data_tool/data_analytics/backend/app/services/dataset_cleanup.py) | What a dataset leaves behind, removed in one place. | discard_dataset_artifacts |
| [AI_data_tool/data_analytics/backend/app/services/dataset_profile.py](AI_data_tool/data_analytics/backend/app/services/dataset_profile.py) | A description of a dataset thorough enough to choose charts from. | build_profile, describe_for_prompt |
| [AI_data_tool/data_analytics/backend/app/services/dataset_refresh.py](AI_data_tool/data_analytics/backend/app/services/dataset_refresh.py) | Shared dataset-refresh work. | rewrite_dataset_file, build_incremental_query, refresh_dataset, write_materialization |
| [AI_data_tool/data_analytics/backend/app/services/delivery.py](AI_data_tool/data_analytics/backend/app/services/delivery.py) | Building and sending a scheduled report delivery. | valid_recipients, split_recipients, post_webhook, build_digest, send_email, run_schedule |
| [AI_data_tool/data_analytics/backend/app/services/demo_content.py](AI_data_tool/data_analytics/backend/app/services/demo_content.py) | Demo dataset frames for the "Load demo content" feature. | build_demo_frames, is_demo_dataset, seed_demo_datasets, is_demo_report, seed_demo_reports, demo_gauge_bands, demo_gauge_rule, demo_value_map_rule, demo_expression_rule, seed_demo_features, seed_demo_ux_showcase, build_demo_directquery_frame, demo_directquery_sqlite_path, demo_directquery_source_config, is_demo_data_source, seed_demo_directquery, remove_demo_content |
| [AI_data_tool/data_analytics/backend/app/services/demo_use_cases.py](AI_data_tool/data_analytics/backend/app/services/demo_use_cases.py) | Insight-led demo reports: what the platform does FOR someone. | seed_demo_use_cases, seed_demo_workspace |
| [AI_data_tool/data_analytics/backend/app/services/direct_query.py](AI_data_tool/data_analytics/backend/app/services/direct_query.py) | DirectQuery Service ==================== Pushes aggregate-strategy widget queries (the `shape_series` config shape -- dimension/measure/aggregation) down into SQL against a live data source, instead of materializing the whole table into pandas first. See docs/superpowers/specs/2026-08-15-directquery-design.md for the design. | SourceUnavailable, DirectQueryUnsupported, QueryPlan, plan_query, build_sql, build_count_sql, build_group_total_sql, build_row_totals_sql, HistogramPlan, plan_histogram, build_histogram_stats_sql, build_histogram_bucket_sql, CorrelationMatrixPlan, plan_correlation_matrix, build_correlation_matrix_sql, RowFetchPlan, plan_row_fetch, build_row_fetch_sql, FetchedFrame, fetch_analysis_frame, run_direct_query |
| [AI_data_tool/data_analytics/backend/app/services/display_rules.py](AI_data_tool/data_analytics/backend/app/services/display_rules.py) | Display rules: expression-driven restyling of an already-shaped widget result. | result_frame, evaluate_rules |
| [AI_data_tool/data_analytics/backend/app/services/duck_agg.py](AI_data_tool/data_analytics/backend/app/services/duck_agg.py) | DuckDB pre-aggregation for the import/pandas widget path. | Ineligible, DuckPlan, is_enabled, plan, aggregate, try_aggregate |
| [AI_data_tool/data_analytics/backend/app/services/engines.py](AI_data_tool/data_analytics/backend/app/services/engines.py) | Pooled SQLAlchemy engines, keyed by connection identity. | get_metadata_engine, get_engine, dispose_engine |
| [AI_data_tool/data_analytics/backend/app/services/error_codes.py](AI_data_tool/data_analytics/backend/app/services/error_codes.py) | The codes a widget-data error can carry, and the one way to raise one. |  |
| [AI_data_tool/data_analytics/backend/app/services/eval_schedule.py](AI_data_tool/data_analytics/backend/app/services/eval_schedule.py) | T4: an OPT-IN, in-process nightly stand-in for a real CI accuracy gate. | run_gate, run_eval_gate_once, run_eval_schedule, maybe_create_task |
| [AI_data_tool/data_analytics/backend/app/services/explain.py](AI_data_tool/data_analytics/backend/app/services/explain.py) | Automated explanation of a response variable: which columns move it, ranked. | explain_response |
| [AI_data_tool/data_analytics/backend/app/services/forecast_goal.py](AI_data_tool/data_analytics/backend/app/services/forecast_goal.py) | When will this reach X? — goal-seek along a forecast. | ForecastGoalError, forecast_goal |
| [AI_data_tool/data_analytics/backend/app/services/frame_cache.py](AI_data_tool/data_analytics/backend/app/services/frame_cache.py) | Process-local DataFrame memo: the same file parses once, not once per widget. | sidecar_path, write_parquet_sidecar, remove_parquet_sidecar, estimate_frame_bytes, get_frame, clear_frame_cache |
| [AI_data_tool/data_analytics/backend/app/services/hijri.py](AI_data_tool/data_analytics/backend/app/services/hijri.py) | Hijri dates for time axes (Phase 7.5, Arabic formats). | to_hijri, hijri_label |
| [AI_data_tool/data_analytics/backend/app/services/index_advice.py](AI_data_tool/data_analytics/backend/app/services/index_advice.py) | Index recommendations from what the platform has watched itself run. | leading_index_columns, create_index_statement, advise |
| [AI_data_tool/data_analytics/backend/app/services/ingest.py](AI_data_tool/data_analytics/backend/app/services/ingest.py) | Ingestion — reading a file into a frame, and typing its columns. | load_file, epoch_unit, looks_like_time_column, detect_types, missing_pct, duplicate_columns |
| [AI_data_tool/data_analytics/backend/app/services/insights.py](AI_data_tool/data_analytics/backend/app/services/insights.py) | The insights engine: scan a dataset's secured frame unprompted and return ranked, plain-language findings — SAS's Insights / Power BI's Insights, sized to this app. | effective_roles, generate_insights, narrate_findings, narrate_one, apply_novelty, suggest_widgets_from_findings |
| [AI_data_tool/data_analytics/backend/app/services/knowledge.py](AI_data_tool/data_analytics/backend/app/services/knowledge.py) | One read path for everything the platform knows about a dataset's columns. | ColumnKnowledge, ObjectKnowledge, GlossaryEntry, DatasetKnowledge, link_columns, for_dataset, SimilarDataset, similar_datasets |
| [AI_data_tool/data_analytics/backend/app/services/llm.py](AI_data_tool/data_analytics/backend/app/services/llm.py) | Client for the self-hosted model endpoint. | LLMClient, get_client |
| [AI_data_tool/data_analytics/backend/app/services/mdb.py](AI_data_tool/data_analytics/backend/app/services/mdb.py) | Reading Microsoft Access databases (.mdb / .accdb) through mdbtools. | MdbUnavailable, MdbReadError, mdbtools_available, list_tables, read_table |
| [AI_data_tool/data_analytics/backend/app/services/measure_eval.py](AI_data_tool/data_analytics/backend/app/services/measure_eval.py) | Post-aggregation measure evaluation. | resolve_scope, evaluate_measure, resolve_measure, preview_measure |
| [AI_data_tool/data_analytics/backend/app/services/metadata/cache.py](AI_data_tool/data_analytics/backend/app/services/metadata/cache.py) | Stage 3 storage — the DuckDB sample cache. | SampleCache, get_cache, get_object_cache |
| [AI_data_tool/data_analytics/backend/app/services/metadata/catalog_sync.py](AI_data_tool/data_analytics/backend/app/services/metadata/catalog_sync.py) | The metadata pipeline, run against a CONNECTION rather than against datasets. | CatalogContext, stage_discover, stage_sample, stage_profile, stage_infer_keys, stage_describe, stage_entities, stage_drift, stage_link_datasets, run_catalog_sync |
| [AI_data_tool/data_analytics/backend/app/services/metadata/drift.py](AI_data_tool/data_analytics/backend/app/services/metadata/drift.py) | Stage 6 — schema fingerprinting and drift detection. | fingerprint, diff_schemas, find_orphaned_annotations, detect, summarize |
| [AI_data_tool/data_analytics/backend/app/services/metadata/infer_keys.py](AI_data_tool/data_analytics/backend/app/services/metadata/infer_keys.py) | Stage 4 — inferring foreign keys. | Candidate, singularize, name_score, types_compatible, looks_like_key, confidence_from, infer_foreign_keys |
| [AI_data_tool/data_analytics/backend/app/services/metadata/infer_semantic.py](AI_data_tool/data_analytics/backend/app/services/metadata/infer_semantic.py) | Stage 5 — turning structure into meaning. | classify_semantic_type, classify_role, detect_deprecation, apply_column_inference, build_description_prompt, describe_with_llm, build_source_prompt, build_enum_label_prompt, draft_enum_labels, describe_source_with_llm, build_entity_prompt, draft_entities |
| [AI_data_tool/data_analytics/backend/app/services/metadata/introspect.py](AI_data_tool/data_analytics/backend/app/services/metadata/introspect.py) | Stage 1 — read a database's own catalog. | normalize_type, list_objects, describe_object, estimated_row_counts, count_rows, introspect_source |
| [AI_data_tool/data_analytics/backend/app/services/metadata/profile.py](AI_data_tool/data_analytics/backend/app/services/metadata/profile.py) | Stage 2 — column statistics. | normalize_n_distinct, parse_pg_array, build_top_k, should_compute_top_k, from_pg_stats_row, profile_frame, quote_identifier, build_profile_sql, build_top_k_sql |
| [AI_data_tool/data_analytics/backend/app/services/metadata/sample.py](AI_data_tool/data_analytics/backend/app/services/metadata/sample.py) | Stage 3 — deciding how to take a sample, and building the query that does it. | choose_strategy, pick_stratify_column, build_sample_sql, reservoir_sample_frame, statement_timeout_sql |
| [AI_data_tool/data_analytics/backend/app/services/metadata/store.py](AI_data_tool/data_analytics/backend/app/services/metadata/store.py) | Provenance-aware writes for the metadata plane. | ProvenanceError, upsert_inferred_relationship, upsert_declared_relationship, confirm_relationship, upsert_column_stats, apply_inferred_column_semantics |
| [AI_data_tool/data_analytics/backend/app/services/metadata/sync.py](AI_data_tool/data_analytics/backend/app/services/metadata/sync.py) | The six-stage metadata pipeline. | StageResult, SyncContext, stage_discover, stage_sample, stage_profile, stage_infer_keys, stage_infer_semantic, stage_drift, run_sync, find_active_run, run_sync_background, source_sync_lock |
| [AI_data_tool/data_analytics/backend/app/services/model_widgets.py](AI_data_tool/data_analytics/backend/app/services/model_widgets.py) | Models as canvas widgets (MASTER_PLAN Phase 3). | shape_model_linear, shape_model_logistic, shape_model_tree, shape_model_cluster, shape_model_compare, register_scoring_model, shape_model_score |
| [AI_data_tool/data_analytics/backend/app/services/net_guard.py](AI_data_tool/data_analytics/backend/app/services/net_guard.py) | SSRF guard for outbound data-source connections. | BlockedHostError, assert_host_allowed |
| [AI_data_tool/data_analytics/backend/app/services/notifications.py](AI_data_tool/data_analytics/backend/app/services/notifications.py) | In-app notifications: one row per event per user, capped per user. | notify |
| [AI_data_tool/data_analytics/backend/app/services/org_access.py](AI_data_tool/data_analytics/backend/app/services/org_access.py) | Per-organization MCP / machine-access switch (see models.OrgMcpAccess). | mcp_enabled, enabled_map, set_mcp_enabled |
| [AI_data_tool/data_analytics/backend/app/services/page_templates.py](AI_data_tool/data_analytics/backend/app/services/page_templates.py) | Serialising pages to templates and rehydrating them. | serialize_page, rehydrate_page, resolve_index_refs |
| [AI_data_tool/data_analytics/backend/app/services/parameters.py](AI_data_tool/data_analytics/backend/app/services/parameters.py) | Typed substitution of report parameters into expressions. | ParameterError, encode_literal, substitute |
| [AI_data_tool/data_analytics/backend/app/services/pdf_export.py](AI_data_tool/data_analytics/backend/app/services/pdf_export.py) | Server-rendered report PDF. | build_report_pdf |
| [AI_data_tool/data_analytics/backend/app/services/pii.py](AI_data_tool/data_analytics/backend/app/services/pii.py) | Detect personal data in a sample, and mask it before the sample leaves. | classify_value, detect_semantic_type, is_pii, mask_value, mask_rows |
| [AI_data_tool/data_analytics/backend/app/services/prep.py](AI_data_tool/data_analytics/backend/app/services/prep.py) | Step-based data preparation: an ordered, persisted pipeline of cleansing and shaping steps applied every time an import dataset's frame is loaded. | prep_steps_of, derived_from_of, derived_source_ids, validate_prep_steps, prep_added_columns, join_key_pairs, partition_column, collect_join_dataset_ids, apply_prep_steps, resolve_join_frames, join_match_report, mapping_match_report |
| [AI_data_tool/data_analytics/backend/app/services/query_builder.py](AI_data_tool/data_analytics/backend/app/services/query_builder.py) | Visual query builder: a validated query model compiled to dialect-correct SQL. | table_columns, introspect_tables, list_functions, qid_null_check, build_sql, referenced_functions, referenced_tables |
| [AI_data_tool/data_analytics/backend/app/services/query_log.py](AI_data_tool/data_analytics/backend/app/services/query_log.py) | T5: fire-and-forget QueryRun telemetry. | log_query_run_sync, log_share_access_sync, log_delivery_sync |
| [AI_data_tool/data_analytics/backend/app/services/quotas.py](AI_data_tool/data_analytics/backend/app/services/quotas.py) | Task E2: per-tenant quota enforcement. | QuotaExceeded, invalidate_quota_cache, reset_concurrent_counts, get_quota, enforce_query_quota, enforce_agent_quota, enforce_storage_quota, concurrent_ask_slot |
| [AI_data_tool/data_analytics/backend/app/services/refresh_scheduler.py](AI_data_tool/data_analytics/backend/app/services/refresh_scheduler.py) | Scheduled refresh of import-mode datasets. | backoff_minutes, in_backoff, record_failure, clear_failure, reap_stuck_sync_runs, reap_orphaned_failures, calendar_spec, is_calendar_due, schedule_is_due, is_due, due_datasets, advisory_lock_key, due_dataflows, refresh_dataflow, rescan_insights, refresh_one, run_items, run_scheduler |
| [AI_data_tool/data_analytics/backend/app/services/relative_dates.py](AI_data_tool/data_analytics/backend/app/services/relative_dates.py) | Relative date filters: "last 30 days", "month to date", "rolling 12 months". | RelativeDateError, validate_spec, period_start, add_periods, window, as_dates, has_relative, resolve_filters, apply_date_range, cadence_days, partial_period |
| [AI_data_tool/data_analytics/backend/app/services/report_composer.py](AI_data_tool/data_analytics/backend/app/services/report_composer.py) | Compose a whole report page from the insights engine's ranked findings. | compose_page |
| [AI_data_tool/data_analytics/backend/app/services/report_package.py](AI_data_tool/data_analytics/backend/app/services/report_package.py) | Offline report package (MASTER_PLAN Phase 5 item 4). | build_package_html |
| [AI_data_tool/data_analytics/backend/app/services/report_review.py](AI_data_tool/data_analytics/backend/app/services/report_review.py) | Report quality as CI (Phase 7.4): the review's HIGH findings, server-side. | high_findings |
| [AI_data_tool/data_analytics/backend/app/services/retrieval.py](AI_data_tool/data_analytics/backend/app/services/retrieval.py) | Tier 2 retrieval scorer (spec §1, Task R1). | Document, entity_document, rank_objects, rank_documents |
| [AI_data_tool/data_analytics/backend/app/services/rtl_text.py](AI_data_tool/data_analytics/backend/app/services/rtl_text.py) | Right-to-left text for server-side PDF export. | has_rtl, ensure_rtl_font, shape, font_for |
| [AI_data_tool/data_analytics/backend/app/services/saml.py](AI_data_tool/data_analytics/backend/app/services/saml.py) | SAML 2.0 Web Browser SSO (SP-initiated), per organization — Phase 2 of SSO. | SamlError, wrap_pem, decode_response, peek_ids, build_authn_request, validate_response |
| [AI_data_tool/data_analytics/backend/app/services/script_runner.py](AI_data_tool/data_analytics/backend/app/services/script_runner.py) | The child process that executes a script tile's code. Never imported. | main |
| [AI_data_tool/data_analytics/backend/app/services/script_tile.py](AI_data_tool/data_analytics/backend/app/services/script_tile.py) | A tile that runs server-side Python and shows what it returns. | ScriptError, run_script |
| [AI_data_tool/data_analytics/backend/app/services/secrets.py](AI_data_tool/data_analytics/backend/app/services/secrets.py) | At-rest encryption for connection secrets stored in DataSource.config. | is_encrypted, encrypt_value_v1, encrypt_value, decrypt_value, rewrap_value, encrypt_config, decrypt_config, redact_config, migrate_v1_to_v2 |
| [AI_data_tool/data_analytics/backend/app/services/semantic_guard.py](AI_data_tool/data_analytics/backend/app/services/semantic_guard.py) | The semantic veto, backend half (MASTER_PLAN Phase 0, constitution rule 3). | non_additive_kind, is_quantity, aggregation_refusal, config_refusal |
| [AI_data_tool/data_analytics/backend/app/services/sensitivity.py](AI_data_tool/data_analytics/backend/app/services/sensitivity.py) | Sensitivity labels that propagate and ENFORCE (Phase 7.3). | rank, higher, own_label, dataset_effective, report_dataset_ids, report_floor, report_effective, redacted_columns |
| [AI_data_tool/data_analytics/backend/app/services/sql_expr.py](AI_data_tool/data_analytics/backend/app/services/sql_expr.py) | Filter-expression -> SQL translation ===================================== Translates the same row-filter expression grammar used by `widget_data.apply_filter_expr`/`apply_rls_filter` (AND/OR/NOT, comparisons, `in`/`not in`, backtick-quoted column names) into a parameterized SQL WHERE fragment, for DirectQuery pushdown -- most i | ExpressionTranslationError, translate_filter_expr, expression_columns, translate_filter_expr_null_safe |
| [AI_data_tool/data_analytics/backend/app/services/sso.py](AI_data_tool/data_analytics/backend/app/services/sso.py) | OpenID Connect (Authorization Code + PKCE) single sign-on, per organization. | SsoError, domain_of, idp_for_domain, idp_for_org, domain_claimed_by_other, config_out, fetch_discovery, fetch_jwks, exchange_code, make_pkce, build_authorize_url, seal_flow, open_flow, validate_id_token, match_user, apply_secret_update |
| [AI_data_tool/data_analytics/backend/app/services/suggest_dashboard.py](AI_data_tool/data_analytics/backend/app/services/suggest_dashboard.py) | Propose a whole dashboard for a named kind of person. | build_prompt, validate_suggestion, validate_column_references, suggest_dashboard, build_batch_prompt, stated_persona, suggest_dashboards, load_catalog, load_joins, load_data_range |
| [AI_data_tool/data_analytics/backend/app/services/suggest_dataset_dashboard.py](AI_data_tool/data_analytics/backend/app/services/suggest_dataset_dashboard.py) | Propose whole dashboards for a dataset that already exists, for a named person. | normalise_aggregations, usable_widgets, build_messages, validate_widget, polish_widget, suggest_for_dataset, clarifying_question |
| [AI_data_tool/data_analytics/backend/app/services/suggest_from_insights.py](AI_data_tool/data_analytics/backend/app/services/suggest_from_insights.py) | A dashboard proposed from the statistics alone, with no model involved. | build_relations, suggest_from_insights |
| [AI_data_tool/data_analytics/backend/app/services/text_lang.py](AI_data_tool/data_analytics/backend/app/services/text_lang.py) | Text analytics that work offline, Arabic first (Phase 6.6). | normalize_arabic, light_stem_ar, tokens, stop_words_for, detect_languages, score_text, sentiment_series, label_of |
| [AI_data_tool/data_analytics/backend/app/services/upload_store.py](AI_data_tool/data_analytics/backend/app/services/upload_store.py) | Where an uploaded file goes on disk, and what it may be called. | storage_root, allowed_suffixes, allowed_suffix, allocate_path, concat_frames |
| [AI_data_tool/data_analytics/backend/app/services/widget_data.py](AI_data_tool/data_analytics/backend/app/services/widget_data.py) | Widget Data Service =================== Executes aggregation queries on dataset files and returns chart-ready JSON. | ImportRowCapExceeded, load_file_columns, shape_series, shape_histogram, shape_slicer, shape_custom_graph, shape_dual_series, shape_xy_numeric, shape_bubble, shape_bubble_animated, compute_fit_line, shape_correlation_matrix, shape_heatmap, shape_parallel_coordinates, shape_box_plot, shape_waterfall, shape_gauge, shape_script, shape_card, shape_gantt, shape_vector_plot, shape_geo_points, shape_geo_lines, shape_geo_clusters, shape_geo_pies, shape_geo_layers, shape_geo_contour, shape_geo_network, shape_network, shape_forecast, shape_sankey, shape_decomposition, shape_small_multiples, shape_lattice, shape_animation, resolve_roles, get_widget_data_from_df, apply_filter_expr, apply_rls_filter, apply_calculated_columns, preview_expression, get_widget_data, HierarchyError, shape_hierarchy, sums_measure_by_default |
| [AI_data_tool/data_analytics/backend/app/services/widget_review.py](AI_data_tool/data_analytics/backend/app/services/widget_review.py) | A second pass over proposed widgets: make each chart say something. | build_review_prompt, apply_attributes, review_attributes |
| [AI_data_tool/data_analytics/backend/app/services/widget_roles.py](AI_data_tool/data_analytics/backend/app/services/widget_roles.py) | What each widget type must be given before it can draw anything. | config_key_for_role, missing_roles |
| [AI_data_tool/data_analytics/backend/app/services/widget_shaping.py](AI_data_tool/data_analytics/backend/app/services/widget_shaping.py) | Shared shaping and result-cache surface for the two widget query engines. | safe, get_cache_backend, reset_cache_backend, widget_cache_key, widget_cache_get, widget_cache_set, clear_widget_data_cache |



| Module | Role / module description | Main classes and functions |
| --- | --- | --- |
| [AI_data_tool/data_analytics/backend/app/core/api_keys.py](AI_data_tool/data_analytics/backend/app/core/api_keys.py) | Generation and hashing of machine API keys. | looks_like_api_key, prefix_of, hash_key, verify, generate |
| [AI_data_tool/data_analytics/backend/app/core/capability.py](AI_data_tool/data_analytics/backend/app/core/capability.py) | Per-report viewer capability levels — SAS's three additive tiers. | rank, folder_grant_levels, folder_granted_reports, effective_capability, effective_capabilities, require_capability, max_dataset_capability, require_dataset_capability, report_dataset_ids, readable_dataset_ids, can_read_dataset, require_dataset_read, effective_dataflow_capability, require_dataflow_capability, require_dataset_write, explain_capability |
| [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py) | Implementation module; indexed symbols show its responsibilities | Settings |
| [AI_data_tool/data_analytics/backend/app/core/database.py](AI_data_tool/data_analytics/backend/app/core/database.py) | Implementation module; indexed symbols show its responsibilities | Base, get_db |
| [AI_data_tool/data_analytics/backend/app/core/org_scope.py](AI_data_tool/data_analytics/backend/app/core/org_scope.py) | Implementation module; indexed symbols show its responsibilities | check_org |
| [AI_data_tool/data_analytics/backend/app/core/rate_limit.py](AI_data_tool/data_analytics/backend/app/core/rate_limit.py) | In-process token-bucket rate limiting middleware (S5). | TokenBucket, reset_buckets, is_test_mode, rate_limit_middleware |
| [AI_data_tool/data_analytics/backend/app/core/rls.py](AI_data_tool/data_analytics/backend/app/core/rls.py) | Implementation module; indexed symbols show its responsibilities | apply_scope, scope_values_for, apply_user_context, resolve_rls_expr, expand_author_expressions, resolve_denied_columns |
| [AI_data_tool/data_analytics/backend/app/core/security.py](AI_data_tool/data_analytics/backend/app/core/security.py) | Implementation module; indexed symbols show its responsibilities | hash_password, verify_password, create_access_token, decode_access_token, create_embed_session_token, decode_embed_session_token |
| [AI_data_tool/data_analytics/backend/app/core/telemetry.py](AI_data_tool/data_analytics/backend/app/core/telemetry.py) | E3: OpenTelemetry, opt-in (settings.otel_enabled, default False). | setup_telemetry |
| [AI_data_tool/data_analytics/backend/app/core/widget_errors.py](AI_data_tool/data_analytics/backend/app/core/widget_errors.py) | The HTTPException that carries a widget error code, and the one way to raise it. | CodedHTTPException, widget_error |



## 8. Business Logic

**Validation boundaries**

| Layer | What actually lives there |
|---|---|
| UI | field requirements, choices filtered by column roles, widget capabilities, expression editors, semantic veto hints, modal confirmations, import/DirectQuery affordances |
| API | Pydantic shape/type/Field validation where used; manual checks for dict bodies, valid org-owned IDs, requested modes, capability levels, scope, upload limits, page sizes, relationships and sharing |
| Services | restricted expression evaluation/translation, semantic aggregation refusal, prep transformations, SQL planning/validation, confidence precedence, quota calculations, scheduling, analysis feasibility |
| Database | primary/foreign keys, nullability and explicit uniqueness/index declarations; most status vocabularies and JSON structure are not enforced as database enums/CHECKs |

**Imported widget pipeline:** file/sidecar load ? row-cap enforcement ? RLS on the base frame ? denied-column removal ? prep steps (with separately secured join inputs) ? author filter ? calculated columns ? widget filters/grouping/measure calculation ? chart shaping/display rules. The real order comes from `services/widget_data.get_widget_data`, not older comments in other modules. Eligible simple aggregates can execute in DuckDB before pandas; unsupported expressions/configurations fall back.

RLS expression failures return an empty frame. Author filters use a tolerant `silent=True` path in important call sites; an invalid author filter is not equivalent to an invalid security filter. This is a material behavioral distinction.

**Preparation:** `services/prep.py` stores ordered recipes in reserved dataset metadata (not a separate row per step). Operations include deduplication, null handling, trim/case, replace, rename/retype, splitting/filtering/dropping, aggregation, joins, partition labels and key-addressed cell edits. A correction is a replayed step, not a write to the external source. Materialization creates a new dataset and records lineage/recipe information. Refresh rebuilds derived outputs. Security-sensitive aggregations must preserve the columns needed to apply policy, or creation/refresh is refused.

**Calculated columns and measures:** calculated columns are row expressions; measures are evaluated at aggregation grain. `measure_eval.py` handles aggregation, TOTAL/BYGROUP/CALC/scope behavior. `custom_functions.py` validates parameterized expression templates and expands their ASTs; these do not introduce arbitrary Python execution. Report parameters are typed/substituted as data/literals. Expression parameters compute a secured source-wide benchmark and cannot be overwritten by a viewer value; the widget path refuses them for DirectQuery.

**Aggregation:** services implement sum/average/min/max/median/count/distinct count, spread/percentile calculations, percentages, cumulative/running calculations, and time-intelligence calculations. Semantics matter: `semantic_guard.py` can refuse summing columns designated as identifiers or otherwise unsuitable. Widget role and capability registries participate in validation and suggestions.

**DirectQuery:** source SQL is planned by engine family, quotes/checks identifiers, translates supported predicates, applies security before aggregation, and returns a common widget shape. Raw-row strategies are capped. The route explicitly refuses calculated columns, named measures, dataset expression filters, animation, lattice layouts, and relative dates anchored to data maximum. Analysis over DirectQuery is a separate bounded frame path and supports more statistical use cases than these widget restrictions imply.

**Metadata:** source catalog discovery, sampling, profiling, key inference, descriptions/entities, drift detection and provenance linking are separate stages. Confirmed/declared relationships outrank inferred proposals. `metadata/store.py` permits writes of equal or higher provenance rank and refuses lower-rank replacement; ?confirmed? does not mean no human can ever edit a value. Inferred joins need confirmation before the agent uses them. Source-column provenance lets dataset meaning resolve from catalog metadata.

**Scheduling:** one in-process loop wakes at 60-second intervals. Dataset/dataflow refresh, report schedules and alerts use recorded due times, PostgreSQL advisory locks and durable failure streaks. Backoff is 5, 15, 60, 240, 720, then 1440 minutes. Success clears failure rows. Calendar delivery options are interpreted with IANA time zones. This is not a Celery/RabbitMQ worker architecture.

**Alerts/delivery:** alert expressions run on the creator's permitted data; notifications are rising-edge oriented rather than repeated for every true evaluation. Schedules resolve the creator, assemble sections/digests or exports, and record delivery results. Missing SMTP configuration is recorded as an unsuccessful delivery, not proof mail was sent.

**Publication:** publication is visibility/access state; report edits remain possible. Review settings may block a newly published report when high-severity findings remain. Version snapshots are separate from publication and are not full copies of all report-related records.

## 9. Frontend Architecture

`main.tsx` initializes theme, mounts React StrictMode, App and Toaster, and registers the service worker in production. `App.tsx` composes BrowserRouter, direction/auth/confirmation/prompt providers, lazy routes and route guards. `Layout.tsx` owns the application shell/navigation; public shared/embed pages sit outside the protected shell.

State is mostly local to screens plus AuthContext, DirectionContext and report CrossFilterContext. Large report state includes pages/widgets, active dataset, filters, selected objects, layouts, pane visibility, parameter values, pending edits and local undo helpers. REST results are fetched through typed Axios wrappers in `services/api.ts`; there is no separately installed server-state query framework.

The editor uses custom layout/grid helpers (`pages/reportBuilder/grid.ts`, `lib/dashboardLayout.ts`, alignment helpers), rather than a declared react-grid-layout dependency. `WidgetRenderer`/WidgetBody dispatch rendering and data requests; chartRenderers handle many conventional chart types, while maps, trees, networks, models, tables and controls have specialized paths. `WidgetConfigPanel` is the configuration editor, with capability/role utilities limiting relevant options.

Reusable UI includes modal focus/keyboard helpers, ConfirmDialog/PromptDialog, loading/error/empty states, list filters, action menus and expression builders. Important report panes include data/prep/calculations/measures, model relationships, selection/order, interactions/bookmarks, display rules, mobile layout, versions, comments, translations, review and copilot.

Cross-filter state carries source widget and dataset context, translates related columns through dataset relationships, and distinguishes sending/receiving interaction settings. Persisted configuration and current viewer filters are different kinds of state. Shared/embed views reuse renderers but expose a smaller surface and fetch saved widget configurations through token-specific APIs.

English/Arabic dictionaries and direction context support RTL. CSS/design tokens and locally bundled fonts form the visual system. The production service worker does not cache `/api/` responses, so it is an offline shell/installability feature, not offline analytical data access.

### Complete route/screen inventory

API wrappers map to URLs in frontend/src/services/api.ts and section 7. Child panes can make additional calls. Responsibilities are explained in the domain/workflow sections.

| Route | Screen | Route protection | Important components | Direct API wrappers | Source |
| --- | --- | --- | --- | --- | --- |
| /login | Login | Public route; token/protocol checks apply where relevant | LanguageSwitcher | ssoApi.discover, ssoApi.loginUrl | [AI_data_tool/data_analytics/frontend/src/pages/Login.tsx](AI_data_tool/data_analytics/frontend/src/pages/Login.tsx) |
| /sso/callback | SsoCallback | Public route; token/protocol checks apply where relevant |  | Auth/protocol or child component calls | [AI_data_tool/data_analytics/frontend/src/pages/SsoCallback.tsx](AI_data_tool/data_analytics/frontend/src/pages/SsoCallback.tsx) |
| /shared/:token | SharedReport | Public route; token/protocol checks apply where relevant | WidgetRenderer, CrossFilterContext, FilterBar, FloatingFilterWindow | sharedApi.report, sharedApi.widgetData | [AI_data_tool/data_analytics/frontend/src/pages/SharedReport.tsx](AI_data_tool/data_analytics/frontend/src/pages/SharedReport.tsx) |
| /embed | EmbeddedReport | Public route; token/protocol checks apply where relevant | WidgetRenderer, CrossFilterContext, FilterBar, FloatingFilterWindow | embedApi.report, embedApi.widgetData | [AI_data_tool/data_analytics/frontend/src/pages/EmbeddedReport.tsx](AI_data_tool/data_analytics/frontend/src/pages/EmbeddedReport.tsx) |
| / | Home | Signed-in user | LoadError | datasetsApi.list, reportsApi.list, reportsApi.recent | [AI_data_tool/data_analytics/frontend/src/pages/Home.tsx](AI_data_tool/data_analytics/frontend/src/pages/Home.tsx) |
| /datasets | Dashboard | Signed-in user | ConfirmDialog, SuggestDashboardsDialog, ActionMenu, ListFilter, IconLabel, LoadError | datasetsApi.delete, datasetsApi.list | [AI_data_tool/data_analytics/frontend/src/pages/Dashboard.tsx](AI_data_tool/data_analytics/frontend/src/pages/Dashboard.tsx) |
| /upload | Upload | Signed-in user | LoadingState | datasetsApi.upload, datasetsApi.uploadBatch | [AI_data_tool/data_analytics/frontend/src/pages/Upload.tsx](AI_data_tool/data_analytics/frontend/src/pages/Upload.tsx) |
| /ask | AskAI | Signed-in user | ChatPane | agentApi.listConversations, agentApi.remove, agentApi.rename, dataSourcesApi.list, datasetsApi.list | [AI_data_tool/data_analytics/frontend/src/pages/AskAI.tsx](AI_data_tool/data_analytics/frontend/src/pages/AskAI.tsx) |
| /insights | InsightsHub | Signed-in user | ListFilter, EmptyState, LoadError, LoadingState, FindingChart | datasetsApi.list, insightsApi.runShared | [AI_data_tool/data_analytics/frontend/src/pages/InsightsHub.tsx](AI_data_tool/data_analytics/frontend/src/pages/InsightsHub.tsx) |
| /datasets/:id | DatasetDetail | Signed-in user | AggregatesPanel, ColumnMeaningPanel, AlertsPanel, PredictionModelsPanel, StatisticsPanel, DatasetSensitivity, NotebookSnippet, LoadError, LoadingState, EmptyState, OutlierDetailsDialog, IconLabel, FindingChart, CalcColumnsPanel, PrepPipelinePanel, MeasuresPanel, CustomCategoryPanel, ExpressionBuilder, QueryBuilderDialog, DatasetShareDialog | analysisApi.associationRules, analysisApi.get, analysisApi.keyInfluencers, analysisApi.run, analysisApi.segment, dataPreviewApi.query, dataSourcesApi.list, datasetsApi.get, datasetsApi.list, datasetsApi.refresh, datasetsApi.setSchedule, filterExprApi.preview, filterExprApi.update, insightsApi.run, prepApi.get, prepApi.rebuild, prepApi.set, reportsApi.create | [AI_data_tool/data_analytics/frontend/src/pages/DatasetDetail.tsx](AI_data_tool/data_analytics/frontend/src/pages/DatasetDetail.tsx) |
| /reports | Reports | Signed-in user | LoadError, ConfirmDialog, PromptDialog, ListFilter, IconLabel, ActionMenu | datasetsApi.list, reportsApi.create, reportsApi.delete, reportsApi.list, reportsApi.setPublished, reportsApi.update, workspaceApi.create, workspaceApi.delete, workspaceApi.tree, workspaceApi.update | [AI_data_tool/data_analytics/frontend/src/pages/Reports.tsx](AI_data_tool/data_analytics/frontend/src/pages/Reports.tsx) |
| /reports/:id | ReportBuilder | Signed-in user | PdfOptionsDialog, RelativeDateEditor, AccessExplainer, GeoMatchCheck, LoadError, CalcColumnsPanel, ColumnFormatsPanel, WidgetRenderer, WidgetConfigPanel, DisplayRulesPanel, PagePropertiesPanel, HierarchyTree, FilterBar, FloatingFilterWindow, DataView, OutlierDetailsDialog, CommentsPane, TranslationsPane, InsightsPane, ShareLinksDialog, AccessDialog, ExplainDialog, OutlinePane, SuggestionsPane, ModelView, StatusBar, MobileLayoutEditor, SelectionPane, VersionHistoryPane, TabOrderPane, ChatPane, CopilotChat, IconLabel, chartUtils, themes, PackTermsConfirm, ViewerKit, CrossFilterContext, CollapsibleSide, ReviewPane, PopupOverlay, TooltipPageOverlay, WidgetPlaceholder, TruncationNote, DatasetPickerDialog, SubscribeButton, ToolbarMenu, ConfirmDialog, useMeasuredWidth, useModalDialog | analysisApi.get, authzApi.decisions, boundarySetsApi.installPack, boundarySetsApi.list, columnMetaApi.set, dataSourcesApi.list, datasetsApi.get, datasetsApi.list, hierarchyApi.autoGenerate, hierarchyApi.get, measuresApi.delete, measuresApi.save, parametersApi.list, parametersApi.save, relationshipsApi.list, reportsApi.addCommonFilter, reportsApi.addPage, reportsApi.addWidget, reportsApi.deleteCommonFilter, reportsApi.deletePage, reportsApi.deleteWidget, reportsApi.downloadPackage, reportsApi.downloadPdf, reportsApi.get, reportsApi.getClassification, reportsApi.getRevision, reportsApi.listBookmarks, reportsApi.restoreVersion, reportsApi.setClassification, reportsApi.update, reportsApi.updatePage, reportsApi.updateWidget, themesApi.list, translationsApi.list, widgetTemplatesApi.create, widgetTemplatesApi.delete, widgetTemplatesApi.list | [AI_data_tool/data_analytics/frontend/src/pages/ReportBuilder.tsx](AI_data_tool/data_analytics/frontend/src/pages/ReportBuilder.tsx) |
| /dashboards | Navigate | Signed-in user | Redirect alias | /reports or /reports/:id | [AI_data_tool/data_analytics/frontend/src/App.tsx](AI_data_tool/data_analytics/frontend/src/App.tsx) |
| /dashboards/:id | DashboardAlias | Signed-in user | Redirect alias | /reports or /reports/:id | [AI_data_tool/data_analytics/frontend/src/App.tsx](AI_data_tool/data_analytics/frontend/src/App.tsx) |
| /reports/:id/print | ReportPrint | Signed-in user | WidgetRenderer, CrossFilterContext, LoadError, LoadingState | datasetsApi.get, reportsApi.get | [AI_data_tool/data_analytics/frontend/src/pages/ReportPrint.tsx](AI_data_tool/data_analytics/frontend/src/pages/ReportPrint.tsx) |
| /connections | Connections | Signed-in user | LoadError, ConfirmDialog, QueryBuilderDialog, ListFilter, IconLabel, ActionMenu | dataSourcesApi.connectors, dataSourcesApi.delete, dataSourcesApi.list, dataSourcesApi.test | [AI_data_tool/data_analytics/frontend/src/pages/Connections.tsx](AI_data_tool/data_analytics/frontend/src/pages/Connections.tsx) |
| /lineage | Lineage | Signed-in user | LoadError, LoadingState | lineageApi.graph | [AI_data_tool/data_analytics/frontend/src/pages/Lineage.tsx](AI_data_tool/data_analytics/frontend/src/pages/Lineage.tsx) |
| /connections/:id/review | SourceReview | Signed-in user | JoinGraph, SyncProgress, SourceOverview, GlossaryPanel, SuggestFromSourceDialog, LoadError, LoadingState | dataSourcesApi.indexAdvice, metadataApi.confirm, metadataApi.confirmEntities, metadataApi.drift, metadataApi.entities, metadataApi.latestSync, metadataApi.review, metadataApi.settings, metadataApi.sync, metadataApi.syncStatus | [AI_data_tool/data_analytics/frontend/src/pages/SourceReview.tsx](AI_data_tool/data_analytics/frontend/src/pages/SourceReview.tsx) |
| /admin/roles | AdminRoles | Organization admin | ConfirmDialog, useModalDialog, EmptyState, LoadError, LoadingState | adminRolesApi.create, adminRolesApi.delete, adminRolesApi.list, adminRolesApi.update | [AI_data_tool/data_analytics/frontend/src/pages/admin/AdminRoles.tsx](AI_data_tool/data_analytics/frontend/src/pages/admin/AdminRoles.tsx) |
| /admin/custom-connectors | AdminCustomConnectors | Organization admin | ConfirmDialog, useModalDialog, EmptyState, LoadError, LoadingState | customConnectorsApi.create, customConnectorsApi.delete, customConnectorsApi.list, customConnectorsApi.update, dataSourcesApi.connectors | [AI_data_tool/data_analytics/frontend/src/pages/admin/AdminCustomConnectors.tsx](AI_data_tool/data_analytics/frontend/src/pages/admin/AdminCustomConnectors.tsx) |
| /admin/users | AdminUsers | Organization admin | ConfirmDialog, useModalDialog, LoadError, LoadingState | adminRolesApi.list, adminUsersApi.bulkCreate, adminUsersApi.create, adminUsersApi.delete, adminUsersApi.list, adminUsersApi.update | [AI_data_tool/data_analytics/frontend/src/pages/admin/AdminUsers.tsx](AI_data_tool/data_analytics/frontend/src/pages/admin/AdminUsers.tsx) |
| /admin/row-security-rules | AdminRowSecurityRules | Organization admin | ConfirmDialog, ActionMenu, useModalDialog, LoadError, LoadingState | adminRlsRulesApi.autoGenerate, adminRlsRulesApi.create, adminRlsRulesApi.delete, adminRlsRulesApi.list, adminRlsRulesApi.preflight, adminRlsRulesApi.update, adminRolesApi.list, datasetsApi.list | [AI_data_tool/data_analytics/frontend/src/pages/admin/AdminRowSecurityRules.tsx](AI_data_tool/data_analytics/frontend/src/pages/admin/AdminRowSecurityRules.tsx) |
| /admin/connection-rules | ConnectionRowPolicies | Organization admin |  | agentPoliciesApi.create, agentPoliciesApi.list, agentPoliciesApi.remove, dataSourcesApi.list, metadataApi.review, rolesApi.list | [AI_data_tool/data_analytics/frontend/src/pages/admin/ConnectionRowPolicies.tsx](AI_data_tool/data_analytics/frontend/src/pages/admin/ConnectionRowPolicies.tsx) |
| /admin/column-security-rules | AdminColumnSecurityRules | Organization admin | ConfirmDialog, useModalDialog, EmptyState, LoadError, LoadingState | adminRolesApi.list, columnSecurityApi.create, columnSecurityApi.list, columnSecurityApi.remove, datasetsApi.list | [AI_data_tool/data_analytics/frontend/src/pages/admin/AdminColumnSecurityRules.tsx](AI_data_tool/data_analytics/frontend/src/pages/admin/AdminColumnSecurityRules.tsx) |
| /admin/org-units | AdminOrgUnits | Organization admin | ConfirmDialog, PromptDialog, EmptyState, LoadError, LoadingState | adminUsersApi.list, orgUnitsApi.create, orgUnitsApi.forUser, orgUnitsApi.list, orgUnitsApi.remove, orgUnitsApi.setForUser | [AI_data_tool/data_analytics/frontend/src/pages/admin/AdminOrgUnits.tsx](AI_data_tool/data_analytics/frontend/src/pages/admin/AdminOrgUnits.tsx) |
| /monitoring/jobs | MonitoringJobs | Organization admin | ListFilter, EmptyState, LoadError, LoadingState | monitoringApi.jobs | [AI_data_tool/data_analytics/frontend/src/pages/monitoring/MonitoringJobs.tsx](AI_data_tool/data_analytics/frontend/src/pages/monitoring/MonitoringJobs.tsx) |
| /monitoring/deliveries | MonitoringDeliveries | Organization admin | ListFilter, EmptyState, LoadError, LoadingState | monitoringApi.deliveries | [AI_data_tool/data_analytics/frontend/src/pages/monitoring/MonitoringDeliveries.tsx](AI_data_tool/data_analytics/frontend/src/pages/monitoring/MonitoringDeliveries.tsx) |
| /monitoring/activity | MonitoringActivity | Organization admin | ListFilter, EmptyState, LoadError, LoadingState | monitoringApi.activity | [AI_data_tool/data_analytics/frontend/src/pages/monitoring/MonitoringActivity.tsx](AI_data_tool/data_analytics/frontend/src/pages/monitoring/MonitoringActivity.tsx) |
| /admin/export-policy | AdminExportPolicy | Organization admin | EmptyState, LoadError, LoadingState | datasetsApi.list, exportPolicyApi.get, exportPolicyApi.setAll, exportPolicyApi.setGranular | [AI_data_tool/data_analytics/frontend/src/pages/admin/AdminExportPolicy.tsx](AI_data_tool/data_analytics/frontend/src/pages/admin/AdminExportPolicy.tsx) |
| /admin/api-keys | ApiKeys | Organization admin | ConfirmDialog, EmptyState, LoadError, LoadingState | apiKeysApi.create, apiKeysApi.list, apiKeysApi.revoke | [AI_data_tool/data_analytics/frontend/src/pages/admin/ApiKeys.tsx](AI_data_tool/data_analytics/frontend/src/pages/admin/ApiKeys.tsx) |
| /admin/sso | AdminSso | Organization admin | ConfirmDialog, LoadError, LoadingState | ssoApi.deleteConfig, ssoApi.getConfig, ssoApi.putConfig | [AI_data_tool/data_analytics/frontend/src/pages/admin/AdminSso.tsx](AI_data_tool/data_analytics/frontend/src/pages/admin/AdminSso.tsx) |
| /admin/maps | AdminMaps | Organization admin | tiles, LoadError, LoadingState, PackTermsConfirm | boundarySetsApi.installPack, boundarySetsApi.list, boundarySetsApi.packs, mapSettingsApi.get, mapSettingsApi.set | [AI_data_tool/data_analytics/frontend/src/pages/admin/AdminMaps.tsx](AI_data_tool/data_analytics/frontend/src/pages/admin/AdminMaps.tsx) |
| /admin/audit | AdminAudit | Organization admin | LoadError, LoadingState | adminAuditApi.list | [AI_data_tool/data_analytics/frontend/src/pages/admin/AdminAudit.tsx](AI_data_tool/data_analytics/frontend/src/pages/admin/AdminAudit.tsx) |
| /platform/organizations | PlatformOrgs | Platform super-admin | EmptyState, LoadError, LoadingState | platformApi.createOrg, platformApi.listOrgs, platformApi.setMcp, platformApi.setParent, platformApi.setQuota | [AI_data_tool/data_analytics/frontend/src/pages/admin/PlatformOrgs.tsx](AI_data_tool/data_analytics/frontend/src/pages/admin/PlatformOrgs.tsx) |



Notable naming: the `Dashboard.tsx` screen is the dataset list. The UI labels reports ?dashboards,? while canonical URLs and tables still use ?reports.? There is **no current `/dataflows` route** in App.tsx: API types/wrappers and monitoring support exist, but a dedicated dataflow authoring screen was not found. Likewise Home currently calls dataset/report/recent-report APIs, not an automation-runs API.

## 10. User Workflows

### Bring in and inspect data

1. Authenticate; list/upload access is resolved as that user.
2. Upload a file or choose a connection/table/query. Batch upload can separate files or append compatible inputs.
3. Import persists a managed file and dataset/column metadata; DirectQuery persists a live query definition instead.
4. Open DatasetDetail to preview, profile, inspect columns/meaning, create prep/calculated fields, run analyses, or build a report.
5. Save a prep recipe or materialize derived data; source-backed/derived imports can receive refresh schedules.
6. Connectors can be tested and metadata synchronization started; review inferred joins/descriptions before treating them as trusted.

### Build, review and distribute a dashboard

1. Create a report against accessible dataset(s).
2. Add pages/widgets, choose roles and visual types, then configure layout/filtering/calculations/interactions.
3. Fetch each widget through the secured widget-data route.
4. Changes persist through report APIs; relevant mutations snapshot the previous report structure and advance revision.
5. Inspect review findings and performance, optionally publish or grant report/workspace access.
6. Create a share link or embed configuration, export/print, or subscribe/schedule delivery, subject to policy.
7. Restore a saved report structure if required, understanding that pages/widget IDs are recreated.

### Ask AI

1. Select an accessible connection or dataset scope and create/select a conversation.
2. Submit a question; the route stores messages/run context.
3. The graph resolves follow-ups, classifies intent, clarifies ambiguity, retrieves schema/business context, and plans.
4. A suitable statistical question can dispatch to an analysis handler; SQL questions use generation, validation, policy, bounded execution and sanity checks.
5. Store step/result snapshots and render a table/chart plus explanation; bounded retries feed specific failures back to generation.
6. Follow-up presentation requests can reuse stored results; feedback may confirm question/SQL examples for future retrieval.

~~~mermaid
sequenceDiagram
  participant User
  participant UI as AskAI / ChatPane
  participant API as agent router
  participant Graph as Agent graph
  participant Model as LLM endpoint
  participant Exec as Bounded executor
  participant DB as Metadata DB
  User->>UI: Ask a data question
  UI->>API: POST conversation ask
  API->>DB: Resolve owner/scope and record run
  API->>Graph: Question and authorized context
  Graph->>Model: Classify / plan / generate
  Graph->>Graph: Validate SQL and attach policy
  Graph->>Exec: Execute source SQL or secured DuckDB frames
  Exec-->>Graph: Bounded rows and execution details
  Graph->>DB: Persist steps/results
  Graph->>Model: Explain computed result
  Graph-->>API: Answer, status and presentation
  API-->>UI: Result payload
~~~

### Statistical analysis and saved prediction

Choose a dataset and registered analysis, provide required columns/parameters, load a secured frame, validate statistical feasibility, compute and display results/caveats. Saved prediction adds training, candidate comparison, full permitted-frame refit, artifact storage, and later scoring with aligned features. Training can honor a prep partition column and remains import-only.

### Team governance

An admin creates roles/users and org-unit placements, configures dataset row/column rules and separate connection-object row policies, then grants report/folder access. Users can inspect their own scope. Publish/grant visibility never substitutes for data-security predicates.

### Backend-only automation

The implemented runner can persist a run and execute profile ? describe ? scan ? propose ? review ? compose ? notify. Its scheduler hookup and retry/review helpers exist. No registered route or frontend caller for creating/approving/rejecting these runs was found, so a complete user-initiated automation workflow is **Needs Verification**, not documented as available UI.

## 11. Important Data Flows

**Imported chart:** ReportBuilder/WidgetRenderer ? `widgetDataApi` ? `POST /datasets/{id}/widget-data` ? `_resolve_widget_data` (organization/read/quota/parameters/security) ? `get_widget_data` ? cache or DuckDB/pandas pipeline ? chart-shaped JSON ? renderer. PostgreSQL supplies rules/configuration; the upload file supplies values.

**Live chart:** same API boundary ? connection config and source checks ? `run_direct_query` ? SQL plan and security predicate ? pooled source engine ? common shaper/cache ? browser.

**Metadata meaning:** connection sync ? source objects/columns/stats/relationships ? inferred descriptions/entities and drift history ? review confirmation ? `knowledge.for_dataset` follows DatasetColumn.source_column_id ? dataset descriptions/value labels and AI context. This is not a separate Wren MDL compilation step.

**Notebook:** Python client ? bearer API key ? `/semantic` ? governed import frame ? dimensions/measures or paged rows ? JSON/CSV ? pandas client frame. API exports honor export/sensitivity policy; the semantic API refuses DirectQuery row/query execution.

**Scheduled report:** durable ReportSchedule ? scheduler due check/advisory lock ? creator identity ? report section resolution and secured data ? export/digest ? SMTP/webhook ? Delivery/audit record.

**Suggestion:** secured dataset profile ? LLM proposal when description is supplied, or deterministic insights path ? widget role/semantic validation and execution checks ? proposal UI ? accepted report/widgets. A plausible model answer alone is not treated as a validated chart.

## 12. Authentication and Authorization

Local login accepts JSON email/password, verifies bcrypt and active-user status, and returns an HS256 JWT with `sub`, `org_id` and a seven-day expiry. Unknown/inactive/wrong-password paths pay password-check cost and use the same error. On each authenticated request, the backend reloads the active user and role/organization; it does not use client UI state as authority.

The browser keeps `datalytics_token` in localStorage and an in-memory variable. Axios attaches a bearer header; a 401 clears the credential and returns to login. No refresh-token rotation or server-side logout/revocation table was found for ordinary JWTs. User deactivation affects subsequent checks; local logout only clears browser credentials.

API keys use a `dk_` prefix, hash verification and owner identity. The full key is returned once. Organization-level MCP/API-key enablement can deny their use. The UI API-key page is admin-routed even though the ownership-scoped issuing/list/revoking API only requires a current user.

OIDC/SAML are configured per organization and discovered by email domain. Callback/assertion handling lives in `routers/sso.py` and `services/sso.py`, `saml.py`; SAML request IDs are persisted. Provider-side registration, trust configuration and working external sign-in **Need Verification**.

Report capabilities are `none` (resolution only), `view`, `edit`, `data`. Organization scope is checked before report-admin shortcuts. The effective resolver prioritizes admin, author, explicit per-user grant, then folder/publication effects. A per-report user grant can be more restrictive than a folder grant. Published or unowned reports default to view for ordinary users unless a role/grant widens access; an unshared owned draft resolves to none. Folder publication/grants are evaluated through ancestors at read time.

Dataset read access includes administrator, owner, unowned legacy data, explicit share, or datasets used by accessible reports (including additional/per-widget datasets). Dataset **authoring** is separately controlled by `max_dataset_capability`, which uses role restrictions on reports' primary dataset and permissive defaults. It is not the same algorithm as report access; do not substitute one for the other.

Dataset RLS selects the role/dataset rule, with organization administrators bypassing it and no rule meaning unrestricted rows within permitted data. Identity tokens include USEREMAIL/USERID/ORGID/ORGNAME and MYSCOPE. MYSCOPE expands assigned org units and descendants. Column rules remove denied columns. Aggregate datasets inherit source security and must retain sufficient grouping grain.

Source-mode AI uses **ObjectRowPolicy**, distinct from dataset RowSecurityRule. Dataset-mode AI secures frames before registering them in DuckDB. Source policies are parsed/injected into SQL ASTs. No database-native tenant RLS was found.

Share links use hashed URL tokens, expiry/revocation and optional structural snapshots. For data queries a valid same-org viewer is resolved as themselves; otherwise creator identity is used. Page visibility follows the creator's visible ordinary pages. A pinned link freezes report structure, not dataset values.

Embedding checks host credentials/origins and creates a 15-minute, audience-bound embed session token, separate from ordinary login tokens. Host-declared viewer attributes can influence author-expression expansion; they are not an organization-switching grant.

Security-sensitive areas include localStorage bearer tokens, trusted-admin script execution, source credentials/SSRF, SQL validation/policy injection, share/embed identity, security-aware caching, exported artifacts and serialized prediction models. Section 21 distinguishes observed boundaries from unverified exploit hypotheses.

## 13. Configuration and Deployment

Settings are read by Pydantic Settings, including `.env` support. Root Compose substitution and the backend process environment are distinct: adding a variable only to Compose's `.env` does not automatically pass every backend setting into the container. The inspected `.env` and example contain only a small subset of settings. Values were not copied.

| Configuration | Purpose / operational implication |
|---|---|
| DATABASE_URL; POSTGRES_DB/USER/PASSWORD | Metadata DB connection; use `<database-url>` / `<secret>`, not repository demo defaults |
| SECRET_KEY; CONNECTOR_SECRET_KEY | JWT signing and connector secret encryption. Explicit Fernet key recommended by code comments; fallback derives from signing secret, coupling rotation to stored credentials |
| ENV; ALLOWED_ORIGINS; SUPER_ADMIN_EMAILS | Runtime mode, CORS, platform-admin email allowlist |
| UPLOAD_DIR; MAX_UPLOAD_MB/FILES; MAX_BATCH_UPLOAD_MB | Managed local data/artifact location and request limits |
| IMPORT_ROW_CAP; ANALYSIS_ROW_CAP | Imported widget cap vs live statistical sample ceiling |
| FRAME_CACHE_*; WIDGET_DATA_CACHE_*; WIDGET_WORK_MAX_CONCURRENCY | Per-process memory/result budgets and worker-thread concurrency |
| DIRECTQUERY_ENGINE_POOL_MAXSIZE | Bound on distinct pooled source connections |
| VALKEY_URL; VALKEY_CACHE_TTL_S | Optional shared result cache; in-process fallback |
| LLM_BASE_URL/MODEL/ENABLED/TIMEOUT_S/MAX_CONCURRENCY/RESERVED_INTERACTIVE | Configured chat service and foreground/background call budget |
| EMBEDDING_BASE_URL/MODEL/DIM | Optional semantic retrieval; Compose points these at bundled service |
| METADATA_*; DUCKDB_CACHE_PATH; FK_OVERLAP_* | Sampling/profile timeout/concurrency/cache and inference thresholds |
| AGENT_ROW_CAP; AGENT_STATEMENT_TIMEOUT_S | AI execution bounds |
| SMTP_*; PUBLIC_BASE_URL | Email transport and links in output |
| CONNECTOR_ALLOW_PRIVATE_HOSTS | Private/loopback connector host policy; metadata endpoints blocked separately |
| MAP_TILE_HOSTS; BOUNDARY_PACKS_DIR | Basemap allowlist and bundled boundary location |
| RATE_LIMIT_*; OTEL_*; EVAL_GATE_* | Per-process rate limiting, optional telemetry, optional evaluation task |
| AUTOMATION_FRAME_MAX_MB | Persisted secured-frame budget per automation run |
| VITE_API_URL / VITE_API_URL_BUILD; WEB_PORT; UVICORN_WORKERS | API origin/build ingress/worker behavior |

### Complete backend setting inventory

Sensitive/default connection addresses and identity lists are replaced with placeholders. Optional settings do not establish deployment state.

| Environment setting | Type | Declared non-sensitive default or placeholder | Source |
| --- | --- | --- | --- |
| DATABASE_URL | str | <configured value / placeholder; see deployment> | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L6) |
| SECRET_KEY | str | <configured value / placeholder; see deployment> | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L7) |
| ALLOWED_ORIGINS | str | <configured value / placeholder; see deployment> | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L8) |
| ENV | str | 'development' | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L9) |
| UPLOAD_DIR | str | <configured value / placeholder; see deployment> | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L10) |
| BOUNDARY_PACKS_DIR | str | '' | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L13) |
| MAP_TILE_HOSTS | str | '' | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L17) |
| MAX_UPLOAD_MB | int | 100 | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L18) |
| MAX_UPLOAD_FILES | int | 20 | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L24) |
| MAX_BATCH_UPLOAD_MB | int | 200 | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L25) |
| WIDGET_DATA_CACHE_MAXSIZE | int | Field(default=500, ge=0) | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L26) |
| WIDGET_DATA_CACHE_MAX_ENTRY_BYTES | int | Field(default=2000000, ge=0) | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L27) |
| FRAME_CACHE_ENABLED | bool | True | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L33) |
| FRAME_CACHE_MAX_FRAMES | int | Field(default=8, ge=0) | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L34) |
| FRAME_CACHE_MAX_TOTAL_BYTES | int | Field(default=1500000000, ge=0) | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L35) |
| WIDGET_WORK_MAX_CONCURRENCY | int | Field(default=4, ge=1) | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L43) |
| DIRECTQUERY_ENGINE_POOL_MAXSIZE | int | Field(default=32, ge=1) | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L50) |
| SUPER_ADMIN_EMAILS | str | <configured value / placeholder; see deployment> | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L56) |
| CONNECTOR_SECRET_KEY | str | <configured value / placeholder; see deployment> | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L63) |
| CONNECTOR_ALLOW_PRIVATE_HOSTS | bool | True | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L69) |
| SMTP_HOST | str | <configured value / placeholder; see deployment> | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L74) |
| SMTP_PORT | int | 587 | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L75) |
| SMTP_USER | str | <configured value / placeholder; see deployment> | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L76) |
| SMTP_PASSWORD | str | <configured value / placeholder; see deployment> | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L77) |
| SMTP_FROM | str | <configured value / placeholder; see deployment> | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L78) |
| SMTP_STARTTLS | bool | True | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L79) |
| PUBLIC_BASE_URL | str | <configured value / placeholder; see deployment> | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L81) |
| LLM_BASE_URL | str | <configured value / placeholder; see deployment> | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L89) |
| LLM_MODEL | str | 'qwen3.5' | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L90) |
| LLM_TIMEOUT_S | float | Field(default=180.0, gt=0) | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L91) |
| LLM_ENABLED | bool | True | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L92) |
| LLM_MAX_CONCURRENCY | int | Field(default=12, ge=1) | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L98) |
| LLM_RESERVED_INTERACTIVE | int | Field(default=2, ge=0) | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L102) |
| DUCKDB_CACHE_PATH | str | <configured value / placeholder; see deployment> | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L108) |
| METADATA_CACHE_MAX_MB | int | Field(default=512, ge=1) | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L109) |
| METADATA_SAMPLE_ROWS | int | Field(default=1000, ge=10) | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L110) |
| METADATA_STATEMENT_TIMEOUT_S | int | Field(default=20, ge=1) | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L119) |
| METADATA_SAMPLE_CONCURRENCY | int | Field(default=4, ge=1) | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L129) |
| METADATA_DESCRIBE_CONCURRENCY | int | Field(default=12, ge=1) | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L156) |
| FK_OVERLAP_HIGH | float | Field(default=0.95, ge=0.0, le=1.0) | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L163) |
| FK_OVERLAP_REVIEW | float | Field(default=0.7, ge=0.0, le=1.0) | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L164) |
| AGENT_STATEMENT_TIMEOUT_S | int | Field(default=30, ge=1) | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L169) |
| AGENT_ROW_CAP | int | Field(default=5000, ge=1) | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L170) |
| IMPORT_ROW_CAP | int | Field(default=2000000, ge=0) | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L189) |
| ANALYSIS_ROW_CAP | int | Field(default=250000, ge=1) | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L195) |
| AUTOMATION_FRAME_MAX_MB | float | Field(default=256.0, ge=0) | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L210) |
| WIDGET_DUCKDB_PUSHDOWN | bool | True | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L238) |
| WIDGET_DUCKDB_THREADS | int | Field(default=2, ge=1) | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L240) |
| RATE_LIMIT_ENABLED | bool | True | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L249) |
| RATE_LIMIT_WINDOW_SECONDS | int | Field(default=60, ge=1) | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L250) |
| RATE_LIMIT_REQUESTS_PER_WINDOW | int | Field(default=300, ge=1) | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L251) |
| RATE_LIMIT_GUEST_REQUESTS_PER_WINDOW | int | Field(default=60, ge=1) | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L252) |
| RATE_LIMIT_BUCKET_CAP | int | Field(default=10000, ge=1) | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L257) |
| EVAL_GATE_ENABLED | bool | False | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L263) |
| EVAL_GATE_SOURCE_ID | int | 0 | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L264) |
| EVAL_GATE_MIN_ACCURACY | float | Field(default=0.5, ge=0.0, le=1.0) | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L265) |
| EMBEDDING_BASE_URL | str &#124; None | <configured value / placeholder; see deployment> | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L274) |
| EMBEDDING_MODEL | str &#124; None | None | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L275) |
| EMBEDDING_DIM | int &#124; None | None | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L276) |
| OTEL_ENABLED | bool | False | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L281) |
| OTEL_ENDPOINT | str &#124; None | <configured value / placeholder; see deployment> | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L282) |
| OTEL_SERVICE_NAME | str | 'datalytics-backend' | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L283) |
| OTEL_METRICS_ENABLED | bool | True | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L288) |
| OTEL_METRICS_ENDPOINT | str &#124; None | <configured value / placeholder; see deployment> | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L292) |
| OTEL_METRIC_INTERVAL_MS | int | Field(default=60000, ge=1000) | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L296) |
| VALKEY_URL | str &#124; None | <configured value / placeholder; see deployment> | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L305) |
| VALKEY_CACHE_TTL_S | int | Field(default=300, ge=1) | [AI_data_tool/data_analytics/backend/app/core/config.py](AI_data_tool/data_analytics/backend/app/core/config.py#L311) |



Active Compose runs PostgreSQL, backend, frontend development server, Valkey and embeddings; a `prod` profile adds a built Nginx web service. Ports are DB host 5433, backend 8000, development frontend 3001?3000, and production WEB_PORT default 8090?80. Valkey/embeddings are internal. Named volumes preserve PostgreSQL and uploaded files. The backend source is bind-mounted; its Dockerfile installs dependencies but does not COPY the app source, so it is not currently a standalone application image without that mount.

Nginx proxies `/api/` and health, uses SPA fallback, allows 220 MB request bodies, gives fingerprinted assets long caching, and avoids caching index/service-worker files. TLS termination is an external deployment assumption. Production web profile does not independently remove all development-service assumptions from the overall Compose file.

`backup.ps1`, `restore.ps1`, and `build_offline_bundle.ps1` provide operational workflows. Backup must cover metadata **and** uploaded files/sidecars/artifacts. Restore compatibility, encryption-key retention and clean air-gap installation **Need Verification**; scripts were not executed. Disabling the LLM does not itself eliminate all networking: source DBs, map tiles, email, webhooks, embedding services and first image/model builds have independent requirements.

## 14. External Dependencies and Integrations

* **Source databases:** native families include PostgreSQL, MySQL, SQL Server, Oracle, SQLite and DuckDB; registry also describes warehouses/aliases and ODBC escape hatches. A visible catalog tile is not proof an optional dialect/vendor driver is installed. API connectors fetch HTTP/JSON; Access uses mdbtools. Secrets are encrypted/redacted through `services/secrets.py`; custom presets merge locked server-side fields.
* **Chat model:** plain HTTP to configured compatible endpoint through `services/llm.py`; schema-enforced JSON requests, timeout/retry/concurrency controls. Used for descriptions, classification/planning/SQL/narration/copilot/suggestions. Actual model availability and response-contract compliance **Need Verification**.
* **Embeddings:** bundled multilingual MiniLM ONNX service, 384 dimensions, mean pooling/normalization; retrieval has lexical fallback and embedding dimension checks. Cached vectors live in application metadata.
* **Maps:** local boundary packs and uploaded GeoJSON plus browser tile URLs; configurable org defaults and host allowlist. No GeoServer service or GIS optimizer is deployed by Compose. Attribution/licensing metadata belongs to boundary-pack handling.
* **SSO:** OIDC and SAML identity-provider endpoints configured per org; not a built-in deployment of Keycloak.
* **SMTP and webhooks:** scheduled output and alerts. An in-app notification is a database record, separate from successfully sent email.
* **Valkey:** Redis protocol result cache with fallback, not a background-task queue.
* **OpenTelemetry:** opt-in traces/metrics export to configured collector.
* **MCP:** separate FastMCP stdio server authenticates through REST as a user/API key; it is not another access-control authority. Its requirements are separate.
* **Notebook client:** requests+pandas facade over the native semantic API.
* **No active S3/object-store, message-broker or third-party product-analytics service was identified in the main deployment.** Local files and PostgreSQL/Valkey are the configured storage layers.

## 15. Optimization / Modeling Architecture

This is primarily a BI/statistics system. It does not implement the example Domain ? Problem ? immutable mathematical ModelVersion ? Solver ? Solution hierarchy. Neither a general optimization DSL nor a solver-selection/execution subsystem was found. Similar words in upstream references or source datasets are not evidence of such a platform.

Actual modeling concepts:

| Concept | Implemented meaning |
|---|---|
| Domain/entity | Business meaning in Entity, SourceObject, glossary and column semantics, not an optimization problem hierarchy |
| Computational model | Statistical functions or canvas model widgets evaluated over a secured DataFrame |
| Variables/features | Selected source/derived columns; target and predictor lists; numeric/group/date roles |
| Parameters | Analysis request params, report viewer parameters, model/widget config and prep settings |
| Constraints | Type/feasibility/security limits; optional goal-seek x_min/x_max; not a persisted constraint graph |
| Objective | Goal-seek target_y or prediction score comparison, not a general objective-expression model |
| Scenario | Forecast scenario factor adjustments and projection periods; response/config rather than a first-class scenario table |
| Saved model | PredictionModel with binary fitted artifact, feature encoding metadata, score and training RLS string |
| Runs/results | AgentRun/Step, AutomationRun/Step, AnalysisResult, QueryRun; distinct record families |
| Model version | No PredictionModel version chain or publish state. ReportVersion is report-layout history; SchemaVersion is source drift history |

The analytical registry currently has **25 registrations**, of which some describe widget/profile capabilities rather than a generic callable handler. It includes descriptive profiling, segmentation, association rules, key influencers, ETS/simple forecasts, IQR/IsolationForest/ECOD anomalies, inferential tests, explanations, goal seek, forecast goal, decision trees, candidate prediction, topics, sentiment and forecast scenarios. Generic invocation checks for an actual handler; registry presence alone does not imply `/analysis/run` can execute it.

Inferential handlers cover group comparisons, independence, correlation, regression, logistic GLM, mixed model, survival and pairwise comparisons. They return statistical effect/significance/caveat structures, not just chart points. Text sentiment is lexicon-based with Arabic/English handling; it is not a trained LLM sentiment service. Segmentation uses standardized numeric features and silhouette-based k selection.

Goal seek fits `y = slope*x + intercept` with numpy, requires at least three usable pairs and varying x, rejects a near-flat slope, computes `required_x = (target_y - intercept)/slope`, reports R? and extrapolation, and checks optional bounds. When infeasible it reports the binding bound and achievable y. This is a one-variable linear calculation, not a general nonlinear solver.

Forecast scenario fits against time/factors and evaluates fractional changes; its caveats distinguish association from causal intervention. Schedule/network/map widgets visualize schedule/relationship data; they do not schedule resources or solve vehicle-routing problems.

~~~mermaid
flowchart TD
  DS[Accessible dataset] --> SEC[Secured and prepared frame]
  SEC --> REG[Analysis registry / model widgets]
  REG --> RESULT[Statistical result or chart]
  SEC --> CMP[Compare prediction candidates]
  CMP --> FIT[Refit selected estimator]
  FIT --> STORE[PredictionModel artifact and feature schema]
  STORE --> CHECK[Org, feature permission and training-scope checks]
  INPUT[New rows or secured dataset rows] --> CHECK
  CHECK --> ALIGN[One-hot encode and align training columns]
  ALIGN --> SCORE[Predictions and unseen-category diagnostics]
~~~

Prediction candidates include baseline, decision tree, random forest and linear/logistic estimators. Comparison uses a held-out split; the stored estimator is subsequently refitted on the selected permitted training frame. Category encodings and exact feature-column ordering travel with the artifact. Joblib serialization is trusted server-generated pickle; accepting arbitrary uploaded artifacts is not implemented.

## 16. Model and Report Lifecycles

**Saved prediction model:** choose secured import dataset ? optionally select Training partition ? compare candidates ? refit ? persist artifact/metadata/trained_rls ? list/score ? delete. No update/version/publish endpoint exists for saved models. Scoring refuses models whose feature permissions or resolved training-row policy differ from the caller's. Equality of policy text is the implementation's scope test, not a proof of semantic policy equivalence.

**Report:** create owned draft ? add/update pages/widgets and metadata ? optionally review ? publish/unpublish or grant access ? continue editing ? restore prior structure if needed. Publishing never freezes content. `_capture_version` snapshots theme/display rules and page/widget fields before relevant mutation; `VERSIONS_KEPT=50` controls pruning. Not every report-associated record is in the snapshot: names/descriptions, grants, schedules, bookmarks, parameters and translations are not comprehensively versioned by that function. Page background URL is also absent from the inspected capture/restore implementation.

Restore snapshots the current version, deletes/recreates pages/widgets, and restores theme/display rules. IDs change. The response explicitly warns that pins and page-role visibility pointing at replaced objects are removed. Internal page/widget references stored in JSON deserve validation after restore; there is no general FK remap for arbitrary config JSON.

**Pinned share:** capture structural report snapshot ? read live data through the saved structure until expiry/revocation. This is not a frozen result dataset.

**Metadata:** discover/infer ? review/confirm ? resync with provenance precedence ? record schema fingerprint/diff. SchemaVersion is observation history, not a deployable semantic-model release.

## 17. State Machines / Status Fields

These are primarily strings/booleans interpreted by code, not DB enums. Enumerations below describe observed paths, not an exhaustive validation promise for direct database writes.

| Record | States / meaning |
|---|---|
| Report | published false/true; access also depends on owner, folders and grants |
| DataSource | sync_status starts pending; sync code records progress/success/failure |
| SyncRun | running ? terminal outcome; interrupted running rows reaped as failed at startup |
| AgentRun | running ? ok, failed or needs_clarification; follow-up clarification starts another request |
| AgentStep | per-node validation/execution status, SQL, retries and result snapshot |
| Dataflow | last_run_status ok/failed/skipped |
| DataAlert | last_state clear/firing; edge controls repeat delivery |
| Delivery | status/kind/artifact_kind plus error; inspect persisted outcome, not just scheduler due state |
| ScheduleFailure | row exists while failing; attempts + next_attempt_at drive backoff; success deletes row |
| ShareLink | usable until expires_at, revoked_at, invalid creator or policy refusal |
| AutomationRun | pending, running, needs_review, done, failed, cancelled; failed is retryable, review rejection cancels |
| AutomationStep | pending, running, ok, failed, skipped; output_ref is the resume marker |
| Relationship/Entity meaning | inferred, declared where applicable, confirmed provenance; not job status |
| Dataset | import/directquery mode; deprecated boolean; refresh/profile timestamps |

~~~mermaid
stateDiagram-v2
  [*] --> pending
  pending --> running: scheduler executes eligible step
  running --> running: output_ref committed and next step remains
  running --> needs_review: review requires human decision
  running --> failed: execution refusal/error
  failed --> running: retry after backoff
  needs_review --> running: approve helper
  needs_review --> cancelled: reject helper
  cancelled --> [*]
  running --> done: all step outputs exist
  done --> [*]
~~~

The automation helper transitions exist but their user-facing invocation is not currently wired through a discovered route. Rejection behavior and retry eligibility must be understood from runner logic rather than assuming ?failed? is terminal.

## 18. Error Handling

FastAPI translates validation failures and HTTPException responses; most routes manually choose 400/403/404/409/413/422/502 as needed. Org/access helpers often return 404 to avoid revealing inaccessible IDs. Coded widget exceptions return `{detail, code}`; quotas return 429 with retry metadata. Other endpoints still return ordinary `detail` strings or dictionaries, so consumers cannot assume one error shape.

Widget routes distinguish unsupported DirectQuery features, missing files, row caps, source unavailability and semantic refusals. Source errors are sanitized at important boundaries. Security filter failures fail closed with no rows; several optional enrichment/cache/telemetry operations log and degrade gracefully. Migration error suppression is operationally more consequential than optional narration failure.

Frontend uses a global 401 interceptor and local LoadError/toast/inline failure states. Widget rendering has its own coded-error behavior and refresh/retry machinery; this is not a universal API retry policy. The agent bounds SQL generation to three total attempts per step (original plus two repairs). Scheduled work uses durable exponential-like stepwise backoff. LLM/embedding/cache clients have their own retries/fallbacks.

Python logging and persisted audit/run/delivery records serve different purposes. A logged exception is not necessarily a user-visible failure, and an HTTP success can legitimately contain an analytical refusal/result status. **Needs Verification:** production log collection, retention, alerting and the absence of sensitive values in every exceptional driver path.

## 19. Testing

Backend tests use pytest/pytest-asyncio and httpx ASGITransport. The shared fixture creates an in-memory SQLite database with foreign-key enforcement, seeds organizations/users and overrides `get_db`. This exercises route and ORM behavior but does not reproduce all PostgreSQL types, DDL, locking and operational startup behavior.

Critical coverage is present by source inspection:

* Tenant/access/security: org scoping, admin endpoint requirements, report grants, workspace grants, RLS fail-closed behavior, base-frame security boundaries, user tokens, column security, shared-viewer identity, SSO, API keys and secrets.
* Data/querying: upload path safety, prep/join/rebuild, calculations, measures, DirectQuery SQL and source failures, DuckDB parity, caches, aggregates and metadata provenance.
* Analytics/AI: registry, inferential tests, models/scoring, forecasting/anomalies, agent context/SQL/policy/results/repair, suggestions and copilot.
* Report/operations: versions, publication/review, page visibility, templates, exports, schedules/backoff, delivery, automation and migration resilience.
* Frontend: routed pages and many editor/dialog/renderers/utilities; auth interceptor, accessibility helpers/axe, RTL, responsiveness, rendering and form behavior.

The shared backend fixture disables embedding retrieval and DuckDB pushdown by default; dedicated tests opt in. Therefore ?the whole suite? is not automatically a test of the shipping Compose configuration. Some source-contract tests inspect strings/registrations/imports; these are useful structural guards, not runtime behavior proofs.

`backend/conftest.py` imposes a 500-test collection floor unless deliberately narrowed/overridden. `backend/evals/` contains golden datasets and run/report/gate scripts; optional scheduled evaluations are not proof a CI gate is active. Frontend `npm test` runs Vitest; build runs `tsc && vite build`. Playwright is declared, and `qa/` plus root QA documents describe browser/manual checks, but no application-local Playwright config was found in the inspected top-level frontend/backend paths. Upstream WrenAI/Superset tests are not Datalytics coverage.

Current pass/fail totals, line coverage, live connector interoperability, PostgreSQL migration upgrade matrix, external SSO/mail, and production multiworker behavior **Need Verification**. No dependencies were installed and no tests were run during this documentation task.

## 20. Current Architectural Strengths

1. Central identity, organization and capability helpers are reused across many routes; security-specific regression tests exist.
2. The same chart result vocabulary serves imported and live-source paths, with explicit unsupported-feature refusals.
3. Metadata provenance distinguishes guesses from source declarations and human decisions, and catalog meaning links back to dataset columns.
4. Analytical computations live mostly in callable services and a discoverable registry, enabling reuse by UI and assistant.
5. Bounded execution, row/memory budgets, thread offloading and optional-service fallbacks are implemented rather than only planned.
6. Report revision history, stored AI results, query logs and durable delivery/failure records provide useful operational evidence.
7. Shared renderer/component families, typed frontend contracts and RTL/local-font support reduce duplication in presentation.
8. Broad route, security, data-pipeline and frontend tests exist; these are strengths of test design, not claims about current test success.

## 21. Current Architectural Risks / Technical Debt

| Finding | Evidence and practical implication |
|---|---|
| Large coordination modules | widget_data service 4,318 lines; datasets router 3,384; ReportBuilder 3,758; WidgetConfigPanel 2,703; API client 2,464. They concentrate unrelated behavior and make changes hard to reason about |
| Split schema authority | main startup + ORM + 37 revisions + bootstrap SQL. Alembic failures may be swallowed; installed schema correctness needs live verification |
| Dataset authoring/access divergence | core/capability.py max_dataset_capability uses legacy permissive role/primary-report logic, while effective_capability/readable_dataset_ids implement newer ownership/publication/grants |
| JSON-heavy contracts | WidgetCreate/Update/DataRequest accept dict/Any; many API bodies are plain dicts. Python/TS schemas and widget role lists can drift; DB cannot enforce most nested references |
| RLS implemented above database | organization scope and security transforms must be applied at every raw/frame/SQL/export reader; DB itself is not a second tenant isolation barrier |
| DirectQuery denial propagation | router checks selected top-level strings/filter names but does not pass the denied-column set to run_direct_query. Nested config and raw-row paths need an end-to-end security review; exploitability is **Needs Verification** |
| Script execution trust | script_tile runs Python as the server user, not an OS sandbox; environment scrubbing/timeouts do not block file/socket access |
| Script guard boundary | admin-only checks are in report widget create/update, while authenticated widget-data accepts caller config/type and services dispatch script widgets. A non-admin direct query bypass is a concrete path requiring security verification; no exploit was executed |
| Saved artifact trust | prediction artifacts are joblib/pickle. Database/artifact integrity is code-execution-sensitive, even without an upload endpoint |
| Stored model scope comparison | load_usable_model compares resolved RLS text and denied raw features. Equivalent policies may be refused; permission changes involving derived-feature lineage need validation |
| Server/UI exposure gaps | dataflows have APIs but no route/editor found; automation service/scheduler exists without discovered create/review API/UI |
| Partial history | report snapshots omit important associated records and page background; restore replaces IDs and removes dependent records |
| Reverse dependencies | delivery imports reports-router helpers; semantic/shared/coplilot/dataflows cross-call router helpers. Security/frame logic is not entirely in independent services |
| Per-process limits | rate buckets, frame caches and concurrency gates multiply with worker count. Valkey cache does not make all quotas/concurrency controls distributed |
| Local disk dependency | files, sidecars, metadata sample DB and automation artifacts require coordinated storage/backup; separate replicas need the same accessible artifacts |
| Deployment defaults | development secret/database defaults and private connector hosts are allowed by configuration; production settings must be verified. Backend image depends on source mount; no application USER directive in inspected Dockerfile |
| Readiness accuracy | Valkey readiness probes the fallback-capable cache, so an unreachable real Valkey can still appear healthy; startup flag does not prove Alembic success |
| Stale documentation | README feature counts and comments disagree with present registry/routes. Comments claiming old org-wide edit/read behavior must not override current resolver code |
| Test/production mismatch | SQLite fixtures and default-disabled pushdown/embeddings leave live PostgreSQL/driver/multiworker behavior to dedicated integration verification |
| Legacy prototype boundary | root prompt.py lacks Datalytics authentication and uses regex SQL restrictions; it must not be assumed to share the main application's protections |

These are code-grounded review findings, not fixes or a penetration-test report. No vulnerable path was exercised against live data.

## 22. Incomplete or Suspicious Features

The source was searched for TODO, FIXME, placeholder, mock, fake, temporary, hardcoded, stub, NotImplemented and pass patterns. Most hits are comments, input placeholder text, test doubles, defensive exception handling, or demo fixtures rather than unfinished product features.

Significant distinctions:

* `automation_runner._stub` still exists and returns a stub URI, but **the registered seven-step STEPS list uses real implementations**. Calling the whole runner a stub would be incorrect. Its missing discovered UI/API exposure is the actual gap.
* `CacheBackend` raises NotImplementedError as an abstract-style interface; InProcessCache and ValkeyCache implement it.
* `metadata/introspect.py` catches NotImplementedError from dialect functionality; this is a compatibility fallback.
* Registered analytical entries without `handler` are descriptive/widget-specific and cannot all run through the generic analysis route.
* DirectQuery's explicit feature refusals are real product limitations, not TODO comments.
* DatasetColumn.stats remains an ORM field, but creation paths use empty stats and the frontend types it as an empty record; actual statistics are obtained through secured analysis/profile paths. Do not build UI from imagined min/max keys.
* `metadata_describe_concurrency` remains a deprecated setting; the current description path uses the shared LLM gate.
* Duplicate root implementation files, archived worktrees and old plans remain present and can mislead code searches.
* Root README's smaller widget/analysis counts do not match the current WidgetType union/25-entry registry.
* The notebook client's example key prefix differs from the backend's `dk_` implementation; the actual key generator/dependency is authoritative.
* The alternative Compose file and older init SQL should not be treated as equivalent to the active stack without comparison/testing.

## 23. Dependency Map

~~~mermaid
flowchart TD
  App[React App and screens] --> Client[api.ts]
  App --> Render[WidgetRenderer and report components]
  Client --> Routes[FastAPI routers]
  Routes --> Auth[dependencies and core policy]
  Routes --> Schemas[Pydantic schemas]
  Routes --> Models[ORM models]
  Routes --> Query[widget_data / direct_query / analysis_frame]
  Query --> Prep[prep / expressions / measures]
  Query --> Shape[widget shaping / model widgets]
  Query --> Files[ingest / frame cache / Parquet / DuckDB]
  Query --> Drivers[connectors / engines / source DB]
  Routes --> Agent[agent graph]
  Agent --> Context[knowledge / catalog / retrieval]
  Agent --> LLM[LLM client]
  Agent --> Validate[validate / policy / executor]
  Scheduler[refresh scheduler] --> Delivery[delivery and alerts]
  Scheduler --> Automation[automation runner]
  Delivery -. imports helpers from .-> Routes
~~~

Within the frontend, `api.ts` and `types/report.ts` are shared contract hubs; ReportBuilder composes numerous feature panes rather than delegating state to a separate store. Backend model definitions and settings are similarly central.

Observed reverse/cross-router edges: `services/delivery.py ? routers/reports.py`; `services/demo_use_cases.py ? routers/shared.py`; `routers/dataflows.py ? routers/datasets.py`; `routers/report_copilot.py ? routers/agent.py,reports.py`; `routers/semantic.py ? routers/datasets.py,shared.py`; `routers/widget_data.py ? routers/prediction_models.py`. Several are local imports to defer import-time cycles. They establish coupling; no claim of an observed import-crashing circular dependency is made.

Third-party WrenAI/Superset source trees are not arrows in this runtime graph. The root prototype alone reaches Wren CLI and its maps_project semantic definitions.

## 24. Naming Dictionary

| Term | Meaning here |
|---|---|
| Dataset | Registered imported file or DirectQuery table/query, plus semantic/prep metadata |
| Data source / connection | Stored connector type/configuration and source catalog scope |
| Import | Local persisted rows analyzed with pandas/DuckDB |
| DirectQuery | Supported chart/analysis reads pushed to a live source; not full import-feature parity |
| Source object | Cataloged table/view, distinct from a user-selected dataset |
| Entity / grain | Business concept and statement of what one row represents |
| Relationship | Dataset join/cross-filter mapping or source catalog join evidence; these are separate tables |
| Report / dashboard | Same central Report entity; ?dashboard? is the newer UI wording |
| Page | Report canvas; normal/hidden/popup/tooltip/drillthrough behavior depends on viewer surface |
| Widget | Saved visual/control/model/script type, configuration and layout |
| Column role | Analytical meaning/usage such as identifier, category, measure, date or geographic field |
| Calculated column | Row-level formula over a dataset |
| Measure | Aggregated expression evaluated at a grouping grain |
| Custom function | Validated parameterized expression template |
| Parameter | Report viewer value or computed benchmark used in filters/formulas |
| Prep | Ordered transformations applied to a secured frame |
| Dataflow | Separately governed/scheduled reusable recipe with derived output datasets |
| Aggregate dataset | Materialized grouped output of a live source with source-policy/grain checks |
| Data view | Reusable semantic configuration snapshot, not a SQL CREATE VIEW |
| Workspace | Folder/report navigation and sharing tree |
| Org unit / MYSCOPE | Hierarchical user placement and descendant data values |
| RLS / CLS | Application row predicates / denied-column rules |
| Capability | View/edit/data authorization tier; not the same as row visibility |
| Publish | Broaden report/workspace access; does not make report content immutable |
| Report version | Partial structural snapshot used for restoration |
| Schema version | Source catalog fingerprint/drift observation |
| Prediction model | Stored fitted estimator, training feature schema and access scope |
| Agent run | One assistant question's plan, steps and answer |
| Automation run | Background multi-step profile-to-report chain |
| Query run | Operational query timing/cache/source record |
| Insight | Computed finding and suggested presentation, possibly narrated by a model |
| Share link | Expiring/revocable secret-token access to saved report structure |
| Embed | Host-authorized report session with origin and audience controls |
| Model (Wren) | Semantic MDL concept in the separate prototype/upstream tree, not PredictionModel |

## 25. Important Source Files

Read in this order; these paths are under `AI_data_tool/data_analytics/`.

1. `docker-compose.yml`, `backend/app/main.py`: active process boundaries, route mounting, startup/migration behavior.
2. `backend/app/models/models.py`: full persisted vocabulary and deletion/constraint behavior.
3. `backend/app/core/config.py`, `core/database.py`: runtime assumptions and ORM session setup.
4. `backend/app/dependencies.py`, `core/capability.py`, `core/rls.py`: identity, report/dataset authorization and row/column rules.
5. `backend/app/routers/widget_data.py`, `services/widget_data.py`: central secured chart path and imported calculations.
6. `backend/app/services/direct_query.py`, `sql_expr.py`, `engines.py`: live-source SQL and pooling.
7. `backend/app/services/prep.py`, `measure_eval.py`, `aggregates.py`: transformations, grain-aware formulas and materialization.
8. `backend/app/routers/reports.py`, `shared.py`, `embed.py`: mutations/history/publication and external viewing.
9. `backend/app/services/metadata/catalog_sync.py`, `metadata/store.py`, `knowledge.py`: catalog inference, provenance and reused meaning.
10. `backend/app/services/agent/graph.py`, `validate.py`, `policy.py`, `executor.py`: assistant execution and trust boundaries.
11. `backend/app/services/analysis/registry.py`, `model_store.py`, `routers/prediction_models.py`: analyses and fitted-model lifecycle.
12. `backend/app/services/refresh_scheduler.py`, `automation_runner.py`, `delivery.py`: background state and retries.
13. `frontend/src/App.tsx`, `components/Layout.tsx`, `services/api.ts`: screen wiring, navigation and HTTP contracts.
14. `frontend/src/pages/ReportBuilder.tsx`, `components/report/WidgetRenderer.tsx`, `WidgetConfigPanel.tsx`: core user authoring experience.
15. `frontend/src/components/report/CrossFilterContext.tsx`, `types/report.ts`: interaction state and report/widget vocabulary.
16. `backend/tests/conftest.py`, `backend/conftest.py`, `frontend/vitest.config.ts`: what test execution actually exercises.
17. Root `prompt.py` only when working on the separate Wren prototype; it is not the main backend.

The tables in sections 6?9 provide direct links to source files and function/class line anchors.

## 26. Needs Verification

1. Live PostgreSQL schema, migration marker, bootstrap-created legacy objects/indexes and any manual database changes.
2. Which services/configuration are deployed; actual secrets, allowlists, volumes, TLS/proxy topology and worker count.
3. Current test pass/fail and coverage; this assessment did not run suites or reproduce historical QA claims.
4. Real connector driver/dialect availability, database credential permissions, read-only transactions, and timeout semantics for each engine.
5. Script-tile execution authorization through direct widget-data and every alternate template/copilot/restore path.
6. DirectQuery column restrictions for nested role structures and raw-row shapes; derived-column security consistency across readers.
7. Complete entry/review lifecycle for automation runs: implementation exists, but no active route/frontend caller was found.
8. Intended current UI for independently creating/editing dataflows.
9. External SSO callbacks, SMTP/webhook delivery, embeddings/model contract behavior and offline build/restore reproducibility.
10. Operational safety of auto-stamping/recovering Alembic drift as future revisions add data migrations.
11. Report-version restore behavior for config references to replaced page/widget IDs and omitted snapshot properties.
12. Long-running multiworker scheduler exclusion, quota/rate enforcement, cache coherence and storage sharing under real deployment load.
13. Provenance retention/cleanup and data-retention policy for uploads, result snapshots, prediction artifacts, metadata samples and audit records.
14. Business ownership and supported deployment status of the root Wren prototype versus active Datalytics.
15. The actual source database contents and business rules in maps_project; no source queries were executed.
16. Third-party checkout internals beyond their documented module boundaries; this document is not a full upstream WrenAI/Superset architecture review.

## 27. Final Mental Model

The application can be mentally understood as:

1. A governed catalog of connections and datasets, with local imported rows or bounded live-source querying.
2. A shared calculation/preparation/security layer that turns authorized data into chart and analytical results.
3. A report studio that stores pages, widgets and interactions and provides several ways to view, share and export them.
4. An assistance layer that discovers metadata, computes insights and statistics, and uses an LLM to plan/explain validated queries or propose reports.
5. A metadata-backed operational layer for identities, permissions, history, schedules, deliveries and partially exposed automation.
6. A main Datalytics implementation surrounded by prototypes, upstream references and historical copies that must not be mistaken for its active runtime.
