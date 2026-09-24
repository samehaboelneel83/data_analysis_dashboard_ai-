# PROJECT_AUDIT.md

Read-only audit. No file in the repository was modified, refactored or deleted to produce it.

- **Repo root** — `AI_data_tool/data_analytics/`. The enclosing `d:\Omda 2025\projects\data_analysis_dashboard_ai\` folder is **not** a git repository; this file sits at the real root, two levels down.
- **Audited at** — commit `8406c7fd`, branch `restyle/step-1-tokens`.
- **Scope** — 993 tracked source files, 199,502 LOC. `node_modules/`, `.git/`, `.venv/`, `__pycache__/`, `frontend/dist/`, `.worktrees/` excluded throughout.
- **Baselines taken before the audit** — `pytest` exit 0; `vitest` 169 files / 2,265 tests pass, exit 0. Both suites were green, so any failure after a deletion is caused by the deletion.

---

## 1. PURPOSE

Inferred from `backend/app/main.py` (27 `include_router` calls), `backend/app/models/models.py` (77 `__tablename__`s), `backend/app/core/config.py` and the Dockerfiles — not from the README or ARCHITECTURE.md.

A multi-tenant, **self-hosted business-intelligence platform with a governed AI analyst**. An organisation installs it on its own hardware and points it at its own data: uploaded files (`routers/datasets.py:226` `UploadFile`) or live database connections (`services/connectors.py`, five SQL dialects behind ~45 connector entries). Users profile and model that data, then build multi-page dashboards from 67 widget types, cross-filter them, schedule them to email or webhook, and share them by link or iframe embed.

What distinguishes it from a generic BI tool is visible in the code's centre of gravity. First, **security is enforced inside the query path, not above it**: `core/rls.py` resolves a per-role row predicate and `resolve_denied_columns` a per-role column denylist, and every engine — pandas, pushed-down SQL, and the LLM agent's sandboxed DuckDB — applies both before returning a row (`services/widget_data.py:3065` `apply_rls_filter`; `routers/widget_data.py:277-286` refuses a denied column with 403 rather than silently dropping it). Second, it is built to run **air-gapped**: `backend/Dockerfile` states "the running container makes no network calls", fonts are vendored under `frontend/src/assets/fonts/`, and `frontend/src/offlineAssets.test.ts` fails the build if any CDN string reappears. The LLM endpoint is optional — `llm_enabled=False` in `core/config.py` removes the AI entirely.

Users are analysts and dashboard authors (upload, model, build), restricted viewers (read a dashboard filtered to their own rows), organisation admins (`Role.is_org_admin` — users, roles, row/column rules, export policy, SSO, audit), and a platform super-admin identified by an email allowlist (`core/dependencies.py:103-108`) who creates organisations and sets per-org quotas. There is no signup, no billing and no payment route anywhere in `routers/`.

The problem it solves: organisations that cannot send data to a cloud BI vendor still need self-service dashboards and conversational analysis, with a hard guarantee that no viewer — human or model — receives a row or column they are not entitled to.

---

## 2. STACK

### Runtimes and images

| Component | Version | Evidence |
|---|---|---|
| Python | 3.12 | `backend/Dockerfile:1` `FROM python:3.12-slim` |
| Node | 20 (alpine) | `frontend/Dockerfile` `FROM node:20-alpine` |
| PostgreSQL | 16 (alpine) | `docker-compose.yml:5` `image: postgres:16-alpine` |
| Valkey (Redis-compatible cache) | 8 (alpine) | `docker-compose.yml:107` `image: valkey/valkey:8-alpine` |
| nginx (prod profile only) | 1.27 (alpine) | `frontend/Dockerfile` `FROM nginx:1.27-alpine AS prod` |
| mdbtools, freetds-dev | Debian bookworm | `backend/Dockerfile:7` — build-time only, for MS Access + SQL Server |

### Backend — `backend/requirements.txt` (50 pinned packages)

Web/data core: `fastapi==0.111.0`, `uvicorn[standard]==0.29.0`, `sqlalchemy[asyncio]==2.0.30`, `asyncpg==0.29.0`, `alembic==1.13.2`, `pydantic-settings==2.2.1`, `pandas==2.2.2`, `numpy==1.26.4`, `pyarrow==16.1.0`.

Analysis/ML: `scipy==1.13.0`, `scikit-learn==1.5.1`, `statsmodels==0.14.6`, `statsforecast==2.1.1`, `pyod==3.6.5`, `numba==0.67.0`, `llvmlite==0.49.0`, `matplotlib==3.9.2`.

Connectors: `psycopg2-binary==2.9.9`, `pymssql==2.3.0`, `pymysql==1.1.1`, `oracledb==2.3.0`, `pyodbc==5.2.0`, `duckdb-engine==0.13.2`, `aiosqlite==0.20.0`, `sqlglot==30.17.0`, `httpx==0.27.0`.

Auth/security: `passlib[bcrypt]==1.7.4`, `bcrypt==4.3.0`, `python-jose[cryptography]==3.3.0`, `signxml==5.1.0`, `lxml==6.1.2` (SAML).

Output/i18n: `reportlab==4.2.2`, `openpyxl==3.1.2`, `arabic-reshaper==3.0.1`, `python-bidi==0.6.11`, `tzdata==2024.1`.

Cache/telemetry: `redis==5.0.4`, `fakeredis==2.23.2`, five `opentelemetry-*` at `1.27.0` / `0.48b0`.

Test: `pytest==8.2.2`, `pytest-asyncio==0.23.7`, `pytest-timeout==2.3.1`, `freezegun==1.5.1`.

### Frontend — `frontend/package.json` (v2.0.0)

Runtime: `react@^18.3.1`, `react-dom@^18.3.1`, `react-router-dom@^6.23.1`, `axios@^1.7.2`, `recharts@^2.12.7`, `reactflow@^11.11.4`, `lucide-react@^0.383.0`, `react-hot-toast@^2.4.1`, `d3-geo@^3.1.1`, `d3-cloud@^1.2.9`, `topojson-client@^3.1.0`, `world-atlas@^2.0.2`, `pptxgenjs@^4.0.1`.

Dev: `vite@^5.2.12`, `typescript@^5.4.5`, `vitest@^2.0.5`, `jsdom@^24.1.1`, `@vitejs/plugin-react@^4.3.0`, `@testing-library/react@^16.0.0`, `@testing-library/dom@^10.4.1`, `@testing-library/jest-dom@^6.4.8`, `playwright@^1.61.1`, `@types/*`.

### Embeddings sidecar — `embedding_server/requirements.txt`

`fastapi==0.115.0`, `uvicorn[standard]==0.30.6`, `onnxruntime==1.19.2`, `tokenizers==0.20.1`, `numpy==1.26.4`, `huggingface-hub==0.25.1`. Its own header states torch and sentence-transformers are deliberately excluded (~2 GB) and that `huggingface-hub` is build-time only.

### Self-hosted fonts (no runtime fetch)

`frontend/src/assets/fonts/` — `inter-variable-latin.woff2`, `ibm-plex-sans-arabic-{400,500,600}-arabic.woff2` (live), plus `syne-`, `manrope-`, `jetbrains-mono-variable-latin.woff2` (see §6).

---

## 3. HOW TO RUN

### Entry points

| Layer | Entry point |
|---|---|
| Backend ASGI app | `backend/app/main.py:446` — `app = FastAPI(title="Datalytics API", version="2.0.0", lifespan=lifespan)` |
| Frontend | `frontend/index.html` → `frontend/src/main.tsx` → `src/App.tsx` |
| Embeddings sidecar | `embedding_server/server.py` |
| DB schema | Alembic, `backend/alembic/versions/` — 29 revisions, applied by the backend's `lifespan` on startup |

### Dev (the real command)

```
docker compose up
```

`docker-compose.yml:36-40` runs the backend as:

```
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload      # UVICORN_WORKERS <= 1
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers $N  # UVICORN_WORKERS > 1
```

Frontend dev container: `npm run dev -- --host 0.0.0.0 --port 3000`, published on host **3001** (`docker-compose.yml:162`). Postgres is published on host **5433** to avoid clashing with a local 5432 (`docker-compose.yml:16`).

Outside Docker: `cd backend && uvicorn app.main:app --reload` and `cd frontend && npm run dev`.

### Prod

```
docker compose --profile prod up
```

Adds the `web` service (`docker-compose.yml:178-194`), which builds `frontend/Dockerfile` **stage `prod`** — `npm run build` into nginx 1.27 — on `${WEB_PORT:-8090}`. `target:` is mandatory on both frontend services; the Dockerfile header warns that omitting it silently builds the last stage and turns the dev service into nginx with no HMR.

### Required services

- **PostgreSQL 16** — required. `DATABASE_URL` is `postgresql+asyncpg://…`.
- **Valkey 8** — optional result cache. `docker-compose.yml` notes a failure "degrades rather than breaks": the cache opens a circuit and falls back in-process.
- **Embeddings sidecar** — optional; `retrieval.py` falls back to TF-IDF. No `depends_on`, by design.
- **External OpenAI-compatible LLM endpoint (vLLM)** — optional; `llm_enabled=False` disables all AI.
- **SMTP** — optional; without it deliveries are recorded as undeliverable.
- No message broker. No GPU. The scheduler runs **in-process** inside the backend (`app/main.py` lifespan), not as a separate service.

### Tests

```
cd backend  && ./.venv/Scripts/python.exe -m pytest -q     # exit 0 at 8406c7fd
cd frontend && npm test                                    # 169 files / 2265 tests, exit 0
```

---

## 4. FILE MAP

Every tracked source file (`.py .ts .tsx .js .jsx .mjs .css .sql .sh .ps1`).
`node_modules/`, `.git/`, `.venv/`, `__pycache__/`, `frontend/dist/`, `.worktrees/` excluded.

**993 files, 199,502 LOC.** Purpose is the file's own header comment, verbatim; `_(no header comment)_` marks the 374 files that have none.

Reference column: `yes: <file>` = a real import resolves to it. `TEXT-ONLY: <file>` = its name appears only as text (a string-pinned test, a doc, a config) — see §7 before deleting. `**NO**` = no import and no textual mention anywhere. `runner (...)` = collected by a test-runner glob, never imported.

#### `./` — 7 files, 1,440 LOC

- `CrossFilterContext.tsx` — 98 — CrossFilterContext — yes: ReportBuilder.tsx +31
- `ReportBuilder.tsx` — 300 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-13-rls-phase3-frontend.md +3
- `WidgetConfigPanel.tsx` — 198 — _(no header comment)_ — yes: ReportBuilder.tsx +10
- `WidgetRenderer.tsx` — 373 — _(no header comment)_ — yes: ReportBuilder.tsx +10
- `analytics.py` — 141 — Analytics Service — type detection, descriptive stats, outlier detection, — yes: backend/app/services/agent/graph.py +6
- `init.sql` — 99 — _(no header comment)_ — TEXT-ONLY: .claude/settings.local.json +10
- `widget_data.py` — 231 — Widget Data Service — yes: backend/app/main.py +25

> **Caveat for this group:** these seven files are stale copies of files that live under `frontend/src/` and `backend/app/`. Their `yes:` status is a **basename collision** — `from './WidgetRenderer'` resolves to the real file, not this one. Verified unreachable in §6.1.

#### `MCAIT Design System/` — 2 files, 1,644 LOC

- `_ds_bundle.js` — 1634 — @ds-bundle: {"format":3,"namespace":"MCAITDesignSystem_6bac07","components":[{"name":"Alert","sourcePath":"components... — TEXT-ONLY: MCAIT Design System/components/core/appbar.card.html +4
- `styles.css` — 10 — MCAIT Design System — global entry point — TEXT-ONLY: COURSE_1_narrations.txt +48

#### `MCAIT Design System/components/core/` — 20 files, 977 LOC

- `Alert.d.ts` — 10 — Inline status message. Use for success confirmations, warnings, errors, and contextual info — never for toasts or loa... — **NO**
- `Alert.jsx` — 33 — _(no header comment)_ — TEXT-ONLY: COURSE_2_narrations.txt +9
- `AppBar.d.ts` — 65 — _(no header comment)_ — **NO**
- `AppBar.jsx` — 210 — ── MCAIT product suite (the shared family) ─────────────────────── */ — TEXT-ONLY: MCAIT Design System/_ds_bundle.js +7
- `Avatar.d.ts` — 10 — User identity avatar. Use wherever a person, team, or AI agent needs a visual identity mark. Falls back to initials w... — **NO**
- `Avatar.jsx` — 42 — _(no header comment)_ — TEXT-ONLY: MCAIT Design System/_adherence.oxlintrc.json +5
- `Badge.d.ts` — 11 — Small status chip. Use to label states, categories, counts, or file types. Never use for interactive actions — use Bu... — **NO**
- `Badge.jsx` — 38 — _(no header comment)_ — TEXT-ONLY: MCAIT Design System/_adherence.oxlintrc.json +8
- `Button.d.ts` — 23 — Primary interactive control. Use for all user-initiated actions. — **NO**
- `Button.jsx` — 92 — _(no header comment)_ — TEXT-ONLY: MCAIT Design System/_adherence.oxlintrc.json +21
- `Card.d.ts` — 18 — Surface container for grouped content. Use for settings panels, file previews, summaries, and dashboards. */ — **NO**
- `Card.jsx` — 48 — _(no header comment)_ — TEXT-ONLY: MCAIT Design System/_adherence.oxlintrc.json +18
- `Input.d.ts` — 19 — Text input field with optional label, prefix/suffix, error and hint states. */ — **NO**
- `Input.jsx` — 50 — _(no header comment)_ — TEXT-ONLY: MCAIT Design System/_adherence.oxlintrc.json +7
- `Sidebar.d.ts` — 54 — _(no header comment)_ — **NO**
- `Sidebar.jsx` — 179 — ── Lucide-style icons (currentColor, 1.5 stroke) ───────────────── */ — TEXT-ONLY: MCAIT Design System/_ds_bundle.js +8
- `Switch.d.ts` — 8 — Boolean toggle control. Use for settings and preferences that take effect immediately. */ — **NO**
- `Switch.jsx` — 30 — _(no header comment)_ — TEXT-ONLY: MCAIT Design System/_adherence.oxlintrc.json +9
- `Tabs.d.ts` — 9 — Horizontal tab row. Use for switching between views within a page section — not for top-level app navigation. */ — **NO**
- `Tabs.jsx` — 28 — _(no header comment)_ — TEXT-ONLY: MCAIT Design System/_adherence.oxlintrc.json +6

#### `MCAIT Design System/tokens/` — 5 files, 204 LOC

- `colors.css` — 62 — MCAIT — Color tokens — yes: MCAIT Design System/styles.css +1
- `fonts.css` — 11 — MCAIT — Webfonts — yes: MCAIT Design System/styles.css +1
- `products.css` — 65 — MCAIT — Per-product accent themes — yes: MCAIT Design System/styles.css +1
- `spacing.css` — 33 — MCAIT — Spacing, radii, shadows, motion — yes: MCAIT Design System/styles.css +1
- `typography.css` — 33 — MCAIT — Typography tokens — yes: MCAIT Design System/styles.css +1

#### `backend/` — 2 files, 100 LOC

- `conftest.py` — 60 — Rootdir conftest: a floor on how many tests must be collected. — yes: backend/tests/test_measures_api.py
- `run_eval_gate.ps1` — 40 — _(no header comment)_ — TEXT-ONLY: ARCHITECTURE.html +6

#### `backend/alembic/` — 1 files, 95 LOC

- `env.py` — 95 — Alembic environment for Datalytics. — TEXT-ONLY: .gitignore +30

#### `backend/alembic/versions/` — 29 files, 2,542 LOC

- `0001_baseline.py` — 1026 — baseline — alembic (revision chain)
- `0002_deliveries_tz.py` — 67 — T3 deliveries and schedule timezone — alembic (revision chain)
- `0003_feedback_evals.py` — 64 — T4 agent feedback and eval runs — alembic (revision chain)
- `0004_retrieval_embeddings.py` — 46 — Tier 2 retrieval: retrieval_embeddings cache table — alembic (revision chain)
- `0005_entities.py` — 55 — Tier 2 retrieval: entities table — alembic (revision chain)
- `0006_embed_configs.py` — 59 — Task E1: embed_configs table — alembic (revision chain)
- `0007_quotas.py` — 43 — Task E2: quotas table — alembic (revision chain)
- `0008_materializations.py` — 45 — Task O3: materializations table — alembic (revision chain)
- `0009_workspace_nodes.py` — 86 — Workspaces: workspace_nodes table — alembic (revision chain)
- `0010_dataflows.py` — 95 — Dataflows: dataflows + dataflow_capabilities tables — alembic (revision chain)
- `0011_pinned_tiles.py` — 56 — Pinned tiles: any chart, pinned to a personal live dashboard. — alembic (revision chain)
- `0012_pin_layout_and_insights.py` — 69 — Pin layout + Dynamic Insight Pins: position, size, and finding references. — alembic (revision chain)
- `0013_report_created_by.py` — 52 — Report authorship: `reports.created_by`. — alembic (revision chain)
- `0014_publish_and_user_grants.py` — 66 — Publish/grant model: `reports.published`, `workspace_nodes.published`, — alembic (revision chain)
- `0015_recent_views.py` — 54 — Per-user recents: the `recent_views` table. — alembic (revision chain)
- `0016_org_units.py` — 75 — Hierarchical RLS: `org_units` and `user_org_units`. — alembic (revision chain)
- `0017_agent_results.py` — 45 — Ask AI results travel with the answer. — alembic (revision chain)
- `0018_report_versions.py` — 42 — Report version history (R2): a restorable content snapshot per revision. — alembic (revision chain)
- `0019_workspace_folder_grants.py` — 57 — Workspace sharing: live folder grants to people, roles, and teams. — alembic (revision chain)
- `0020_dataset_ownership.py` — 68 — Dataset and connection ownership: `created_by`, backfilled to an org admin. — alembic (revision chain)
- `0021_schedule_failures.py` — 47 — Scheduler backoff: remember failures instead of retrying blindly. — alembic (revision chain)
- `0022_dataset_custom_functions.py` — 29 — Custom calculated-column functions: `datasets.custom_functions`. — alembic (revision chain)
- `0023_custom_connectors.py` — 59 — Custom connector presets: `custom_connectors` table and — alembic (revision chain)
- `0024_boundary_sets.py` — 58 — Customer-supplied map boundaries: the `boundary_sets` table. — alembic (revision chain)
- `0025_data_view_default.py` — 33 — A data view an admin can mark as the default for new datasets. — alembic (revision chain)
- `0026_page_background.py` — 25 — A background image on a report page. — alembic (revision chain)
- `0027_prediction_models.py` — 58 — A store for fitted models, so a champion can score new rows. — alembic (revision chain)
- `0028_query_run_shape.py` — 26 — query_runs: the shape of the query, so index advice has something to read. — alembic (revision chain)
- `0029_aggregate_datasets.py` — 37 — Aggregate datasets: a scheduled GROUP BY over a DirectQuery source. — alembic (revision chain)

#### `backend/app/` — 3 files, 790 LOC

- `__init__.py` — 1 — _(no header comment)_ — yes: backend/alembic.ini +375
- `dependencies.py` — 114 — _(no header comment)_ — yes: backend/app/routers/admin.py +32
- `main.py` — 675 — _(no header comment)_ — yes: backend/tests/conftest.py +12

#### `backend/app/core/` — 11 files, 1,807 LOC

- `__init__.py` — 1 — _(no header comment)_ — yes: backend/alembic.ini +198
- `api_keys.py` — 40 — Generation and hashing of machine API keys. — yes: backend/app/routers/auth.py +1
- `capability.py` — 503 — Per-report viewer capability levels — SAS's three additive tiers. — yes: backend/tests/test_workspace_grants.py
- `config.py` — 291 — _(no header comment)_ — yes: backend/alembic.ini +64
- `database.py` — 41 — _(no header comment)_ — yes: backend/alembic/env.py +17
- `org_scope.py` — 12 — _(no header comment)_ — yes: backend/tests/test_org_scope.py +1
- `rate_limit.py` — 223 — In-process token-bucket rate limiting middleware (S5). — yes: backend/tests/test_embed.py +1
- `rls.py` — 287 — _(no header comment)_ — yes: backend/tests/test_aggregate_endpoints.py +3
- `security.py` — 66 — _(no header comment)_ — yes: backend/app/core/rate_limit.py +80
- `telemetry.py` — 300 — E3: OpenTelemetry, opt-in (settings.otel_enabled, default False). — yes: backend/app/main.py +7
- `widget_errors.py` — 43 — The HTTPException that carries a widget error code, and the one way to raise it. — yes: backend/tests/test_widget_error_codes.py

#### `backend/app/models/` — 2 files, 1,969 LOC

- `__init__.py` — 1 — _(no header comment)_ — yes: backend/alembic/env.py +248
- `models.py` — 1968 — _(no header comment)_ — yes: backend/alembic/env.py +248

#### `backend/app/routers/` — 26 files, 12,587 LOC

- `__init__.py` — 1 — _(no header comment)_ — yes: backend/app/main.py +24
- `admin.py` — 821 — _(no header comment)_ — yes: backend/app/main.py +2
- `agent.py` — 474 — The chat surface's API. The pane lives inside the report builder (user's — yes: backend/app/main.py +4
- `analysis.py` — 659 — _(no header comment)_ — yes: backend/app/main.py +7
- `auth.py` — 119 — _(no header comment)_ — yes: backend/app/main.py +5
- `boundary_sets.py` — 159 — Customer-supplied map boundaries: governorates, states, districts. — yes: backend/app/main.py
- `custom_connectors.py` — 126 — _(no header comment)_ — yes: backend/app/main.py +1
- `data_sources.py` — 613 — _(no header comment)_ — yes: backend/app/main.py +5
- `dataflows.py` — 447 — Dataflows: a transformation as a first-class object. — yes: backend/app/main.py +1
- `datasets.py` — 3011 — _(no header comment)_ — yes: backend/app/main.py +11
- `demo.py` — 90 — Load (and unload) the demo content for the calling user's organization. — yes: backend/app/main.py +1
- `embed.py` — 393 — Task E1: embedded reports, secured with HOST-SIGNED JWTs -- "never trust the — yes: backend/app/main.py +1
- `hierarchy.py` — 151 — _(no header comment)_ — yes: backend/app/main.py +4
- `metadata.py` — 768 — Layer 1 API — metadata sync, review, and column statistics. — yes: backend/app/main.py +4
- `notifications.py` — 41 — The bell: a user's own notifications, newest first, with mark-read. — yes: backend/app/main.py +3
- `pins.py` — 214 — Pin any chart to a personal, live home dashboard. — yes: backend/app/main.py
- `platform.py` — 215 — Platform super-admin: manage organizations across the whole platform. — yes: backend/app/main.py +1
- `prediction_models.py` — 270 — Fitted models that can score rows they have never seen. — yes: backend/app/main.py
- `relationships.py` — 52 — _(no header comment)_ — yes: backend/app/main.py +2
- `report_copilot.py` — 281 — The dashboard page copilot: chat that edits the OPEN page, or answers — yes: backend/app/main.py +1
- `reports.py` — 1942 — _(no header comment)_ — yes: backend/app/main.py +5
- `shared.py` — 290 — Guest access: the public face of a share link. NO auth dependency here -- — yes: backend/app/main.py +4
- `sso.py` — 265 — SSO endpoints: the public OIDC login/callback flow, and per-org IdP configuration. — yes: backend/app/main.py +1
- `widget_data.py` — 418 — _(no header comment)_ — yes: backend/app/main.py +22
- `widget_templates.py` — 71 — Object templates: a configured widget saved by name for reuse across reports. — yes: backend/app/main.py +1
- `workspace.py` — 696 — The org's report-navigation tree: folders, filed reports, and their pages. — yes: backend/app/main.py +1

#### `backend/app/schemas/` — 2 files, 838 LOC

- `__init__.py` — 1 — _(no header comment)_ — yes: backend/app/routers/admin.py +19
- `schemas.py` — 837 — _(no header comment)_ — yes: backend/app/routers/admin.py +19

#### `backend/app/services/` — 65 files, 21,617 LOC

- `__init__.py` — 1 — _(no header comment)_ — yes: backend/app/core/capability.py +301
- `admin_audit.py` — 32 — Writing admin-plane security audit entries (S5). — yes: backend/app/routers/admin.py +3
- `aggregates.py` — 185 — Compiling an aggregate dataset from a DirectQuery source. — yes: backend/tests/test_aggregate_endpoints.py +3
- `alerts.py` — 122 — Evaluating data alerts on their schedule. — yes: backend/app/services/refresh_scheduler.py +2
- `analysis_contract.py` — 97 — A1: uniform internal contract for analysis services. — yes: backend/app/services/agent/graph.py +4
- `analytics.py` — 168 — Analytics Service - descriptive stats, outlier detection, categorical — yes: backend/app/services/agent/graph.py +16
- `audit.py` — 28 — Writing audit entries. — yes: backend/app/routers/dataflows.py +6
- `auth_provisioning.py` — 29 — _(no header comment)_ — yes: backend/scripts/create_org_admin.py +7
- `boundary_sets.py` — 123 — Validate a customer-supplied set of map boundaries. — yes: backend/app/main.py +1
- `cache_backend.py` — 196 — Task O2: shared result-cache backend abstraction. — yes: backend/app/services/widget_data.py +3
- `connections.py` — 202 — _(no header comment)_ — yes: backend/app/services/agent/graph.py +7
- `connectors.py` — 538 — The connector registry — the single source of truth for data-source types. — yes: backend/app/routers/custom_connectors.py +19
- `custom_connectors.py` — 52 — Custom connector presets: save-time validation and config merging. — yes: backend/app/main.py +2
- `custom_functions.py` — 162 — Custom calculated-column functions: named, parameterized expression — yes: backend/app/services/widget_data.py +2
- `data_views.py` — 176 — Reusable data views: snapshot a dataset's semantic layer, apply it elsewhere. — TEXT-ONLY: ARCHITECTURE.html +6
- `dataset_cleanup.py` — 35 — What a dataset leaves behind, removed in one place. — TEXT-ONLY: backend/app/routers/datasets.py +2
- `dataset_profile.py` — 294 — A description of a dataset thorough enough to choose charts from. — yes: backend/app/services/suggest_dataset_dashboard.py +3
- `dataset_refresh.py` — 263 — Shared dataset-refresh work. — yes: backend/app/services/refresh_scheduler.py +4
- `delivery.py` — 252 — Building and sending a scheduled report delivery. — yes: backend/app/services/alerts.py +4
- `demo_content.py` — 2363 — Demo dataset frames for the "Load demo content" feature. — yes: backend/app/services/demo_use_cases.py +10
- `demo_use_cases.py` — 811 — Insight-led demo reports: what the platform does FOR someone. — yes: backend/app/services/demo_content.py +2
- `direct_query.py` — 1075 — DirectQuery Service — yes: backend/app/services/aggregates.py +23
- `display_rules.py` — 326 — Display rules: expression-driven restyling of an already-shaped widget result. — yes: backend/app/services/delivery.py +8
- `duck_agg.py` — 328 — DuckDB pre-aggregation for the import/pandas widget path. — yes: backend/app/services/widget_data.py +5
- `engines.py` — 141 — Pooled SQLAlchemy engines, keyed by connection identity. — yes: backend/app/services/agent/executor.py +10
- `error_codes.py` — 41 — The codes a widget-data error can carry, and the one way to raise one. — yes: backend/tests/test_widget_error_codes.py
- `eval_schedule.py` — 151 — T4: an OPT-IN, in-process nightly stand-in for a real CI accuracy gate. — yes: backend/app/main.py +1
- `explain.py` — 86 — Automated explanation of a response variable: which columns move it, ranked. — yes: backend/app/services/agent/graph.py +2
- `forecast_goal.py` — 140 — When will this reach X? — goal-seek along a forecast. — yes: backend/app/services/analysis/forecast_goal.py +1
- `frame_cache.py` — 294 — Process-local DataFrame memo: the same file parses once, not once per widget. — yes: backend/app/services/dataset_cleanup.py +17
- `index_advice.py` — 118 — Index recommendations from what the platform has watched itself run. — yes: backend/app/routers/data_sources.py +1
- `ingest.py` — 206 — Ingestion — reading a file into a frame, and typing its columns. — yes: backend/app/services/agent/graph.py +16
- `insights.py` — 659 — The insights engine: scan a dataset's secured frame unprompted and return — yes: backend/app/services/dataset_profile.py +9
- `llm.py` — 362 — Client for the self-hosted model endpoint. — yes: backend/app/main.py +12
- `mdb.py` — 161 — Reading Microsoft Access databases (.mdb / .accdb) through mdbtools. — yes: backend/app/routers/datasets.py +3
- `measure_eval.py` — 426 — Post-aggregation measure evaluation. — yes: backend/app/services/widget_data.py +6
- `net_guard.py` — 69 — SSRF guard for outbound data-source connections. — yes: backend/app/services/connections.py +2
- `notifications.py` — 28 — In-app notifications: one row per event per user, capped per user. — yes: backend/app/main.py +4
- `org_access.py` — 32 — Per-organization MCP / machine-access switch (see models.OrgMcpAccess). — yes: backend/app/routers/platform.py
- `page_templates.py` — 141 — Serialising pages to templates and rehydrating them. — TEXT-ONLY: backend/alembic/versions/0001_baseline.py +4
- `parameters.py` — 62 — Typed substitution of report parameters into expressions. — yes: backend/tests/test_expression_parameters.py +1
- `pdf_export.py` — 294 — Server-rendered report PDF. — yes: backend/app/services/delivery.py +4
- `pii.py` — 256 — Detect personal data in a sample, and mask it before the sample leaves. — yes: backend/app/services/dataset_profile.py +6
- `prep.py` — 554 — Step-based data preparation: an ordered, persisted pipeline of cleansing and — yes: backend/app/services/alerts.py +16
- `query_builder.py` — 591 — Visual query builder: a validated query model compiled to dialect-correct SQL. — yes: backend/tests/test_connect_timeout.py +2
- `query_log.py` — 114 — T5: fire-and-forget QueryRun telemetry. — yes: backend/app/services/agent/executor.py +9
- `quotas.py` — 178 — Task E2: per-tenant quota enforcement. — yes: backend/app/routers/agent.py +12
- `refresh_scheduler.py` — 877 — Scheduled refresh of import-mode datasets. — yes: backend/tests/test_aggregate_endpoints.py +10
- `report_composer.py` — 198 — Compose a whole report page from the insights engine's ranked findings. — yes: backend/tests/test_report_composer.py
- `retrieval.py` — 726 — Tier 2 retrieval scorer (spec §1, Task R1). — yes: backend/app/services/agent/context.py +4
- `rtl_text.py` — 159 — Right-to-left text for server-side PDF export. — yes: backend/app/services/agent/export.py +2
- `saml.py` — 177 — SAML 2.0 Web Browser SSO (SP-initiated), per organization — Phase 2 of SSO. — yes: backend/app/routers/sso.py
- `script_runner.py` — 106 — The child process that executes a script tile's code. Never imported. — TEXT-ONLY: backend/app/services/script_tile.py +1
- `script_tile.py` — 147 — A tile that runs server-side Python and shows what it returns. — yes: backend/app/services/widget_data.py +1
- `secrets.py` — 219 — At-rest encryption for connection secrets stored in DataSource.config. — yes: backend/app/routers/custom_connectors.py +15
- `sql_expr.py` — 228 — Filter-expression -> SQL translation — yes: backend/app/services/aggregates.py +6
- `sso.py` — 251 — OpenID Connect (Authorization Code + PKCE) single sign-on, per organization. — yes: backend/app/main.py +3
- `suggest_dashboard.py` — 490 — Propose a whole dashboard for a named kind of person. — yes: backend/app/routers/metadata.py +3
- `suggest_dataset_dashboard.py` — 626 — Propose whole dashboards for a dataset that already exists, for a named person. — yes: backend/app/services/suggest_from_insights.py +1
- `suggest_from_insights.py` — 178 — A dashboard proposed from the statistics alone, with no model involved. — yes: backend/tests/test_suggest_from_insights.py
- `upload_store.py` — 107 — Where an uploaded file goes on disk, and what it may be called. — yes: backend/app/routers/datasets.py +1
- `widget_data.py` — 3644 — Widget Data Service — yes: backend/app/main.py +130
- `widget_review.py` — 181 — A second pass over proposed widgets: make each chart say something. — yes: backend/app/services/agent/graph.py +1
- `widget_roles.py` — 133 — What each widget type must be given before it can draw anything. — yes: backend/app/services/suggest_dataset_dashboard.py +1
- `widget_shaping.py` — 208 — Shared shaping and result-cache surface for the two widget query engines. — yes: backend/app/services/direct_query.py +2

#### `backend/app/services/agent/` — 12 files, 2,454 LOC

- `__init__.py` — 0 — _(no header comment)_ — yes: backend/app/main.py +30
- `context.py` — 774 — What the agent may know about a source. — yes: backend/app/services/agent/graph.py +16
- `dag.py` — 72 — Run a step DAG in topological layers under one bounded gate. — yes: backend/app/services/agent/graph.py +3
- `executor.py` — 229 — V5 (dry run) + execution + sanity — the only module that touches the — yes: backend/app/services/agent/graph.py +6
- `export.py` — 137 — Chat results as files: the stored snapshot serialized to Excel or PDF. — yes: backend/tests/test_agent_export.py
- `graph.py` — 664 — One question's journey: classify -> (clarify) -> context -> plan -> DAG of — yes: backend/tests/test_agent_analysis_seam.py +7
- `memory.py` — 72 — query_examples: verified question->SQL pairs, recalled as few-shot. — yes: backend/app/services/agent/graph.py +3
- `plan.py` — 68 — Question -> typed step DAG. — yes: backend/app/services/agent/graph.py +2
- `policy.py` — 93 — V4 — row policies injected into the parsed AST. — yes: backend/app/services/agent/graph.py +2
- `results.py` — 102 — Result snapshots: the rows a sink step returned, made small and JSON-safe. — yes: backend/app/services/agent/graph.py +1
- `state.py` — 45 — Typed state passed between the agent's nodes. — yes: backend/app/services/agent/dag.py +6
- `validate.py` — 198 — The validation ladder, rungs V1-V3 and V6 (V4 is policy.py, V5 lives in — yes: backend/app/services/agent/executor.py +5

#### `backend/app/services/agent/nodes/` — 8 files, 868 LOC

- `__init__.py` — 0 — _(no header comment)_ — yes: backend/app/services/agent/graph.py +9
- `analyze.py` — 134 — Choose an analysis for a question that SQL answers in the wrong shape. — yes: backend/tests/test_agent_choose_analysis.py
- `clarify.py` — 15 — D4.3: ask, do not guess. This node turns the classifier's ambiguity — yes: backend/app/services/agent/graph.py +2
- `classify.py` — 147 — Intent + ambiguity, under the enforced JSON contract. — yes: backend/app/services/agent/graph.py +3
- `copilot.py` — 252 — The page copilot's brain: one chat message about an OPEN dashboard page. — yes: backend/tests/test_report_copilot.py
- `explain.py` — 66 — The answer, with provenance — and a deterministic fallback, because a — yes: backend/app/services/agent/graph.py +2
- `followup.py` — 155 — A new message, read against the conversation so far. — yes: backend/app/services/agent/nodes/classify.py +2
- `generate.py` — 99 — SQL generation — one attempt, under the enforced contract. — yes: backend/tests/test_agent_generate.py +2

#### `backend/app/services/analysis/` — 15 files, 3,794 LOC

- `__init__.py` — 0 — _(no header comment)_ — yes: backend/app/main.py +25
- `anomaly.py` — 67 — A3: PyOD anomaly detectors (iforest, ecod) alongside the pre-existing IQR fence — yes: backend/tests/test_anomaly.py +1
- `automated_prediction.py` — 207 — Fit several models, name the one that wins — and say whether it earned it. — yes: backend/app/services/analysis/model_store.py +1
- `decision_tree.py` — 295 — A decision tree: the rules that separate one outcome from another. — yes: backend/app/services/analysis/automated_prediction.py +3
- `forecast_goal.py` — 55 — `forecast_goal` as a catalogued analysis: forecast a frame, then answer. — yes: backend/app/services/widget_data.py +1
- `forecast_scenario.py` — 196 — What if spend rose 10%? — a projection with factors you can move. — yes: backend/app/services/analysis/registry.py +1
- `goal_seek.py` — 79 — Solve for the factor value a target requires. — yes: backend/app/routers/datasets.py +1
- `inferential.py` — 930 — Inferential statistics: is the difference real, or is it noise? — yes: backend/tests/test_inferential_statistics.py
- `influencers.py` — 233 — Key influencers: which factors move a chosen outcome, and by how much. — yes: backend/tests/test_key_influencers.py
- `model_store.py` — 251 — Keep the champion, and score rows it has never seen. — yes: backend/tests/test_model_store.py
- `patterns.py` — 332 — Association rules: which values travel together. — yes: backend/tests/test_association_rules.py
- `registry.py` — 814 — A4: analysis tool catalogue -- single source of truth for what analyses — yes: backend/app/routers/analysis.py +12
- `restricted.py` — 31 — What to tell a viewer whose own access is why an analysis cannot run. — yes: backend/tests/test_restricted_analysis_message.py
- `segment.py` — 143 — A2: KMeans segmentation with automatic k selection. — yes: backend/tests/test_segment.py
- `text_topics.py` — 161 — What is this free text about? — topics from a column of comments. — yes: backend/app/services/analysis/registry.py +1

#### `backend/app/services/metadata/` — 11 files, 4,665 LOC

- `__init__.py` — 11 — Layer 1 — the metadata plane. — yes: backend/app/main.py +23
- `cache.py` — 423 — Stage 3 storage — the DuckDB sample cache. — yes: backend/app/routers/metadata.py +5
- `catalog_sync.py` — 962 — The metadata pipeline, run against a CONNECTION rather than against datasets. — yes: backend/app/services/metadata/sync.py +3
- `drift.py` — 162 — Stage 6 — schema fingerprinting and drift detection. — yes: backend/app/services/metadata/catalog_sync.py +2
- `infer_keys.py` — 356 — Stage 4 — inferring foreign keys. — yes: backend/app/services/metadata/catalog_sync.py +5
- `infer_semantic.py` — 753 — Stage 5 — turning structure into meaning. — yes: backend/app/services/metadata/catalog_sync.py +3
- `introspect.py` — 263 — Stage 1 — read a database's own catalog. — yes: backend/app/services/metadata/catalog_sync.py +1
- `profile.py` — 327 — Stage 2 — column statistics. — yes: backend/app/services/metadata/sample.py +2
- `sample.py` — 231 — Stage 3 — deciding how to take a sample, and building the query that does it. — yes: backend/app/services/agent/executor.py +5
- `store.py` — 262 — Provenance-aware writes for the metadata plane. — yes: backend/app/routers/metadata.py +9
- `sync.py` — 915 — The six-stage metadata pipeline. — yes: backend/app/routers/metadata.py +8

#### `backend/evals/` — 4 files, 439 LOC

- `__init__.py` — 0 — _(no header comment)_ — yes: backend/app/services/eval_schedule.py +5
- `report.py` — 82 — Render an `evaluate()` results dict as a table, and gate on a minimum accuracy. — yes: backend/evals/run_gate.py +1
- `run_eval.py` — 42 — Execution-accuracy evaluation (spec: 'results, not strings'). — yes: backend/evals/run_gate.py +2
- `run_gate.py` — 315 — The real accuracy gate: runs the golden set through the LIVE agent and scores it. — yes: backend/app/services/eval_schedule.py +1

#### `backend/mcp_server/` — 3 files, 275 LOC

- `__init__.py` — 8 — datalytics MCP server — exposes datalytics's data and analytics to AI agents. — yes: backend/tests/test_mcp_client.py +1
- `client.py` — 131 — Authenticated client of the datalytics HTTP API, used by the MCP tools. — yes: backend/mcp_server/server.py +1
- `server.py` — 136 — datalytics MCP server (stdio transport). — yes: backend/tests/test_mcp_client_reuse.py

#### `backend/scripts/` — 11 files, 1,692 LOC

- `bench_common.py` — 123 — Shared pieces of the performance benchmark harness. — yes: backend/scripts/bench_dashboard.py +3
- `bench_dashboard.py` — 159 — A whole dashboard, cold then warm, alone then with ten people on it. — TEXT-ONLY: docs/superpowers/plans/2026-09-12-aggregate-datasets.md +1
- `bench_directquery.py` — 280 — DirectQuery at scale: does row count reach the application at all? — TEXT-ONLY: docs/superpowers/plans/2026-09-12-aggregate-datasets.md +2
- `bench_equivalence.py` — 117 — The semantic gate: run the config battery through get_widget_data twice — — TEXT-ONLY: backend/app/services/frame_cache.py
- `bench_http.py` — 114 — Full-HTTP-path concurrency benchmark against the live stack. — TEXT-ONLY: docs/superpowers/specs/2026-09-12-scale-plan-design.md
- `bench_widget_data.py` — 105 — In-process widget-data benchmark: times load_file cold and the config — TEXT-ONLY: backend/scripts/bench_dashboard.py +1
- `compat_check.py` — 103 — The same journey in Chromium, Firefox and WebKit. — TEXT-ONLY: ARCHITECTURE.md
- `create_org_admin.py` — 34 — Bootstrap script: create the first Organization and its admin User. — TEXT-ONLY: backend/scripts/validate_pipeline.py +2
- `smoke_embeddings.py` — 253 — Live smokes for Task M2 (docs/superpowers/plans/2026-08-30-embeddings-service.md, — TEXT-ONLY: docs/superpowers/plans/2026-08-30-embeddings-service.md
- `ui_walkthrough.py` — 164 — Drive Datalytics in a real browser and photograph every layer. — TEXT-ONLY: ARCHITECTURE.md +1
- `validate_pipeline.py` — 240 — End-to-end validation of preprocessing, modeling and the query builder. — **NO**

#### `backend/tests/` — 356 files, 63,733 LOC

- `__init__.py` — 0 — _(no header comment)_ — runner (pytest glob)
- `conftest.py` — 137 — _(no header comment)_ — runner (pytest glob)
- `test_admin_audit.py` — 135 — S5 admin_audit trail: security-relevant admin mutations write rows with — runner (pytest glob)
- `test_admin_endpoints_require_admin.py` — 43 — _(no header comment)_ — runner (pytest glob)
- `test_admin_rls_auto_generate.py` — 198 — _(no header comment)_ — runner (pytest glob)
- `test_admin_roles.py` — 76 — _(no header comment)_ — runner (pytest glob)
- `test_admin_row_security_rules.py` — 221 — _(no header comment)_ — runner (pytest glob)
- `test_admin_users.py` — 82 — _(no header comment)_ — runner (pytest glob)
- `test_agent_analysis_seam.py` — 275 — The agent actually runs the analysis -- checked through the graph, not the node. — runner (pytest glob)
- `test_agent_api.py` — 325 — The chat API. Org-scoping is the security property under test: every — runner (pytest glob)
- `test_agent_choose_analysis.py` — 171 — The agent stops writing SQL for questions that are not SQL questions. — runner (pytest glob)
- `test_agent_classify.py` — 165 — Intent + the D4.3 rule: clarify when ambiguous, never guess. — runner (pytest glob)
- `test_agent_column_security.py` — 176 — Column security in the AI agent path (R1 of the competitive assessment). — runner (pytest glob)
- `test_agent_context.py` — 991 — What the agent knows about a source — and what it must NOT know. — runner (pytest glob)
- `test_agent_conversations.py` — 235 — Conversation history, titles, results and the follow-up context on the — runner (pytest glob)
- `test_agent_dag.py` — 118 — The executor: topological layers, one bounded gate, failures contained. — runner (pytest glob)
- `test_agent_dataset_context.py` — 101 — Dataset-mode schema context (Task 16). Same F1 provenance rule as — runner (pytest glob)
- `test_agent_dataset_mode.py` — 400 — The multi-mode amendment (Tasks 16-17): the agent answers over uploaded — runner (pytest glob)
- `test_agent_deps.py` — 22 — sqlglot is the agent's one new dependency — and its only parser. — runner (pytest glob)
- `test_agent_eval.py` — 56 — The accuracy gate. Structural enforcement was MEASURED passing — runner (pytest glob)
- `test_agent_executor.py` — 183 — V5 and execution: bounded, timed, off the event loop, honest about limits. — runner (pytest glob)
- `test_agent_explain.py` — 150 — The agent's answer-synthesis node: figures in, prose out. — runner (pytest glob)
- `test_agent_export.py` — 157 — Downloading a chat result as a file: Excel and PDF. — runner (pytest glob)
- `test_agent_feedback.py` — 155 — T4: 👍/👎 feedback on an agent answer. Owner-only (same-org, different-user — runner (pytest glob)
- `test_agent_followup.py` — 129 — The follow-up resolver (nodes/followup.py): a new message read against — runner (pytest glob)
- `test_agent_generate.py` — 229 — One generation attempt, and the memory it draws on. — runner (pytest glob)
- `test_agent_graph.py` — 485 — One question, end to end, with a scripted model and a real SQLite source. — runner (pytest glob)
- `test_agent_memory.py` — 94 — memory.py: query_examples recall/remember (spec Task R2, section 6). — runner (pytest glob)
- `test_agent_models.py` — 129 — The agent's data model. — runner (pytest glob)
- `test_agent_plan.py` — 78 — Question -> step DAG: the prompt-level rules pinned here, plus the — runner (pytest glob)
- `test_agent_policy.py` — 99 — V4: predicates into the AST — never concatenated, never post-filtered. — runner (pytest glob)
- `test_agent_results.py` — 93 — Result snapshots (services/agent/results.py): small, JSON-safe, honest — runner (pytest glob)
- `test_agent_results_graph.py` — 222 — The graph keeps a result snapshot on SINK steps and records which tables — runner (pytest glob)
- `test_agent_suggest_intent.py` — 69 — Asking the chat for a dashboard. — runner (pytest glob)
- `test_agent_validate.py` — 145 — The ladder, cheapest first (D4.1) — each rung caught AT that rung. — runner (pytest glob)
- `test_aggregate_endpoints.py` — 776 — Creating an aggregate: refuse what cannot be governed, run the first — runner (pytest glob)
- `test_aggregate_model.py` — 59 — An aggregate dataset remembers its source, and dies with it. — runner (pytest glob)
- `test_aggregate_refresh.py` — 290 — A refresh re-checks the grain against the source's rules. — runner (pytest glob)
- `test_aggregate_security.py` — 346 — An aggregate is governed by its source's rules, applied at read time. — runner (pytest glob)
- `test_aggregates_compile.py` — 208 — Compiling an aggregate: the SQL is pinned, and everything it refuses is named. — runner (pytest glob)
- `test_alembic_migrations.py` — 339 — T1: Alembic adopted alongside the existing create_all/_migrate path. — runner (pytest glob)
- `test_alert_endpoints_security.py` — 183 — Alerts are reachable, and reachable only by people who may read the dataset. — runner (pytest glob)
- `test_analysis_contract.py` — 112 — A1: uniform AnalysisContract envelope. — runner (pytest glob)
- `test_analysis_directquery_router.py` — 60 — _(no header comment)_ — runner (pytest glob)
- `test_analysis_dispatch.py` — 246 — The analysis registry becomes a dispatcher. — runner (pytest glob)
- `test_analysis_orphans.py` — 123 — The two SAS-shaped analyses that were not in the catalogue. — runner (pytest glob)
- `test_analysis_rls.py` — 77 — _(no header comment)_ — runner (pytest glob)
- `test_analysis_run_endpoint.py` — 260 — One endpoint that runs any catalogued analysis by name. — runner (pytest glob)
- `test_anomaly.py` — 73 — A3: service-level tests for services/analysis/anomaly.py -- the iqr/iforest/ecod — runner (pytest glob)
- `test_api_keys.py` — 72 — Machine API keys: durable bearer credentials that authenticate as their user. — runner (pytest glob)
- `test_app_engine_recovery.py` — 62 — Does this application survive its own database restarting? — runner (pytest glob)
- `test_architecture_doc.py` — 210 — ARCHITECTURE.md and .html must agree with the code they describe. — runner (pytest glob)
- `test_association_rules.py` — 232 — Association rules: which values travel together. — runner (pytest glob)
- `test_audit_log.py` — 71 — The audit log: append-only, org-scoped, admin-readable. — runner (pytest glob)
- `test_auth_models.py` — 60 — _(no header comment)_ — runner (pytest glob)
- `test_auth_provisioning.py` — 41 — _(no header comment)_ — runner (pytest glob)
- `test_auth_router.py` — 124 — _(no header comment)_ — runner (pytest glob)
- `test_automated_prediction.py` — 188 — Automated prediction: fit several models, name the one that wins. — runner (pytest glob)
- `test_batch_quota.py` — 160 — Storage limits across a multi-file upload. — runner (pytest glob)
- `test_batch_upload.py` — 203 — Multi-file upload: one dataset per file, or all of them appended into one. — runner (pytest glob)
- `test_bookmark_model.py` — 15 — _(no header comment)_ — runner (pytest glob)
- `test_bookmarks_org_scoping.py` — 48 — _(no header comment)_ — runner (pytest glob)
- `test_boolean_columns.py` — 88 — Boolean columns must not crash analysis. — runner (pytest glob)
- `test_boundary_sets.py` — 203 — Bring-your-own map boundaries. — runner (pytest glob)
- `test_boundary_sets_endpoints.py` — 198 — The HTTP surface for customer-supplied map boundaries. — runner (pytest glob)
- `test_bulk_users.py` — 85 — Bulk user provisioning: CSV-style import with partial success (enterprise admin). — runner (pytest glob)
- `test_cache_backend.py` — 208 — Task O2: cache_backend.py -- InProcessCache and ValkeyCache against one — runner (pytest glob)
- `test_calc_date_stats_functions.py` — 218 — Date, date-construction and advanced-statistics functions in the expression language. — runner (pytest glob)
- `test_calculated_column_preview_rls.py` — 89 — _(no header comment)_ — runner (pytest glob)
- `test_catalog_sync.py` — 905 — Describing a database from its CONNECTION, with no datasets involved. — runner (pytest glob)
- `test_column_meta_api.py` — 143 — Per-column metadata — SAS's "data item properties". — runner (pytest glob)
- `test_column_security.py` — 359 — Column-level security: denied columns cease to exist for the restricted role. — runner (pytest glob)
- `test_common_filters.py` — 68 — Report-level common filters (gap row 358). — runner (pytest glob)
- `test_compose_defaults.py` — 74 — Shipped deployment defaults, pinned where they are a real claim. — runner (pytest glob)
- `test_compute_fit_line.py` — 37 — _(no header comment)_ — runner (pytest glob)
- `test_conftest_smoke.py` — 12 — _(no header comment)_ — runner (pytest glob)
- `test_connect_timeout.py` — 76 — Every networked engine-creation path must apply the connect timeout, so an — runner (pytest glob)
- `test_connector_family_directquery.py` — 99 — A wire-compatible alias lights up DirectQuery through family resolution. — runner (pytest glob)
- `test_connectors_endpoint.py` — 60 — The connector catalog endpoint and type validation on data-source writes. — runner (pytest glob)
- `test_connectors_registry.py` — 156 — The connector registry: family resolution, URL building, capabilities. — runner (pytest glob)
- `test_create_directquery_dataset.py` — 94 — _(no header comment)_ — runner (pytest glob)
- `test_custom_category_expressions.py` — 92 — Contract test between the frontend custom-category generator and this engine. — runner (pytest glob)
- `test_custom_connectors.py` — 256 — _(no header comment)_ — runner (pytest glob)
- `test_custom_functions.py` — 345 — Custom calculated-column functions: validation and expansion. — runner (pytest glob)
- `test_custom_graph.py` — 130 — Composing a chart from plot layers — SAS calls this Graph Builder. — runner (pytest glob)
- `test_data_preview_directquery_router.py` — 81 — _(no header comment)_ — runner (pytest glob)
- `test_data_preview_rls.py` — 65 — _(no header comment)_ — runner (pytest glob)
- `test_data_source_cache_ttl.py` — 19 — _(no header comment)_ — runner (pytest glob)
- `test_data_source_secrets.py` — 68 — Data-source secrets are encrypted at rest and redacted on the wire. — runner (pytest glob)
- `test_data_sources_custom_connector.py` — 167 — _(no header comment)_ — runner (pytest glob)
- `test_data_sources_org_scoping.py` — 182 — _(no header comment)_ — runner (pytest glob)
- `test_data_view_default.py` — 216 — A data view an admin marks as the default for newly imported datasets. — runner (pytest glob)
- `test_data_views.py` — 134 — Reusable data views: snapshot a dataset's semantic layer, apply it to another — runner (pytest glob)
- `test_dataflow_permissions.py` — 320 — A dataflow's permissions are ITS OWN -- the point of the whole object. — runner (pytest glob)
- `test_dataflows_api.py` — 283 — Dataflows: the object itself -- CRUD, multiple outputs, and the refusals it — runner (pytest glob)
- `test_dataset_materialize.py` — 315 — Saving a prep pipeline's result as a dataset of its own. — runner (pytest glob)
- `test_dataset_mode.py` — 19 — _(no header comment)_ — runner (pytest glob)
- `test_dataset_model_authorisation.py` — 144 — Who may change a dataset's shared model. — runner (pytest glob)
- `test_dataset_profile.py` — 170 — What the model is told about a dataset before it proposes anything. — runner (pytest glob)
- `test_dataset_rebuild.py` — 214 — Re-running the recipe behind a materialized dataset. — runner (pytest glob)
- `test_dataset_refresh_modes.py` — 428 — F3: watermark-driven full/incremental refresh. — runner (pytest glob)
- `test_dataset_shares.py` — 158 — _(no header comment)_ — runner (pytest glob)
- `test_dataset_visibility.py` — 356 — Who may READ a dataset, and who may see or change a connection. — runner (pytest glob)
- `test_datasets_org_scoping.py` — 93 — _(no header comment)_ — runner (pytest glob)
- `test_datetime_analysis.py` — 58 — Date/datetime profiling: self-coercing, granularity-aware, weekday/monthly — runner (pytest glob)
- `test_decision_tree.py` — 261 — A decision tree: the rules that separate one outcome from another. — runner (pytest glob)
- `test_declared_fk_seeding.py` — 299 — T2 -- declared-FK seeding for DirectQuery datasets: sync.py's Relationship — runner (pytest glob)
- `test_decomposition.py` — 249 — The decomposition tree: a number broken down one level at a time. — runner (pytest glob)
- `test_delivery_log.py` — 376 — T3: the Delivery log (one row per delivery ATTEMPT, success and failure — runner (pytest glob)
- `test_demo_action_coverage.py` — 175 — The demo must keep demonstrating the product as the product grows. — runner (pytest glob)
- `test_demo_datasets.py` — 41 — _(no header comment)_ — runner (pytest glob)
- `test_demo_directquery.py` — 616 — Tests for the DirectQuery demo: a SQLite source, a fifth dataset in — runner (pytest glob)
- `test_demo_endpoint.py` — 154 — The "Load demo content" endpoint. — runner (pytest glob)
- `test_demo_features.py` — 931 — Tests for the demo's feature layer — the app's own features laid over the demo content. — runner (pytest glob)
- `test_demo_reports.py` — 1032 — Tests for the demo reports. — runner (pytest glob)
- `test_demo_seed_datasets.py` — 204 — Tests for persisting the demo frames as real Dataset rows. — runner (pytest glob)
- `test_demo_use_cases.py` — 559 — The insight-led use-case demo layer: seeds, and unseeds completely. — runner (pytest glob)
- `test_demo_ux_showcase.py` — 355 — Tests for the UX Showcase demo report — the second seeded report that tours every — runner (pytest glob)
- `test_dependencies.py` — 52 — _(no header comment)_ — runner (pytest glob)
- `test_detect_types.py` — 37 — _(no header comment)_ — runner (pytest glob)
- `test_dimension_granularity.py` — 61 — _(no header comment)_ — runner (pytest glob)
- `test_direct_query_cache.py` — 64 — _(no header comment)_ — runner (pytest glob)
- `test_direct_query_cache_execution.py` — 92 — _(no header comment)_ — runner (pytest glob)
- `test_direct_query_engine.py` — 23 — _(no header comment)_ — runner (pytest glob)
- `test_direct_query_execution.py` — 223 — _(no header comment)_ — runner (pytest glob)
- `test_direct_query_plan.py` — 87 — _(no header comment)_ — runner (pytest glob)
- `test_direct_query_row_capped.py` — 121 — _(no header comment)_ — runner (pytest glob)
- `test_direct_query_row_capped_execution.py` — 108 — _(no header comment)_ — runner (pytest glob)
- `test_direct_query_sql.py` — 171 — _(no header comment)_ — runner (pytest glob)
- `test_direct_query_sqlserver.py` — 116 — SQL Server DirectQuery support. — runner (pytest glob)
- `test_direct_query_stat.py` — 94 — _(no header comment)_ — runner (pytest glob)
- `test_direct_query_stat_postgres.py` — 120 — Equivalence tests for the sql_stat strategy (histogram, correlation_matrix) — runner (pytest glob)
- `test_direct_query_table_preview.py` — 44 — _(no header comment)_ — runner (pytest glob)
- `test_direct_query_totals.py` — 412 — `show_totals` on a DirectQuery dataset. — runner (pytest glob)
- `test_directquery_unsupported_endpoints.py` — 37 — DirectQuery datasets have no local file, so refresh (which re-fetches into that — runner (pytest glob)
- `test_display_rules.py` — 419 — _(no header comment)_ — runner (pytest glob)
- `test_display_rules_contract.py` — 180 — Contract test between the frontend display-rule compiler and this engine. — runner (pytest glob)
- `test_display_rules_vectorized.py` — 557 — Characterization tests for the value_map and interval rule paths. — runner (pytest glob)
- `test_drift.py` — 160 — Stage 6 — schema drift. — runner (pytest glob)
- `test_drift_cache_epoch.py` — 221 — T6: drift -> cache invalidation, via a per-source cache epoch. — runner (pytest glob)
- `test_dual_axis_second_aggregation.py` — 82 — Each axis of a dual-axis chart gets its own aggregation. — runner (pytest glob)
- `test_duck_agg.py` — 349 — DuckDB pre-aggregation: identical results to pandas, or no DuckDB at all. — runner (pytest glob)
- `test_duck_agg_governed.py` — 226 — Governed and filtered widgets on the DuckDB path. — runner (pytest glob)
- `test_duck_agg_granularity.py` — 156 — Date bucketing (`dimension_granularity`) on the DuckDB path. — runner (pytest glob)
- `test_duplicate_column_import.py` — 102 — A query that returns two columns with the same name must say so. — runner (pytest glob)
- `test_embed.py` — 505 — Task E1: embedded reports with host-signed JWTs -- "never trust the browser — runner (pytest glob)
- `test_empty_dataset_listing.py` — 90 — A dataset with no rows must not break the dataset list. — runner (pytest glob)
- `test_enc_migration.py` — 99 — S5: startup enc:v1 -> enc:v2 migration for DataSource.config secrets — runner (pytest glob)
- `test_engine_pool.py` — 69 — DirectQuery engine pool: dedup by connection identity + bounded LRU eviction. — runner (pytest glob)
- `test_envelope.py` — 124 — Envelope encryption for connection secrets (ARCHITECTURE.md stage 0.3). — runner (pytest glob)
- `test_epoch_timestamps.py` — 214 — Integer columns holding Unix epoch timestamps are dates, not numbers. — runner (pytest glob)
- `test_eval_gate.py` — 254 — Unit tests for evals/run_gate.py's PURE parts -- golden loading, the — runner (pytest glob)
- `test_eval_report.py` — 78 — T9: evals/report.py turns evaluate()'s results dict into a table and a pass/fail — runner (pytest glob)
- `test_eval_schedule.py` — 149 — T4: the opt-in scheduled eval gate (services/eval_schedule.py). — runner (pytest glob)
- `test_explain_narrative.py` — 159 — A sentence to go with the automated explanation. — runner (pytest glob)
- `test_export_policy_granular.py` — 124 — Per-destination export policy and the auto-disable-when-private trigger. — runner (pytest glob)
- `test_expression_parameters.py` — 94 — Expression-based parameters (gap row 370). — runner (pytest glob)
- `test_expression_sandbox_escape.py` — 68 — _(no header comment)_ — runner (pytest glob)
- `test_filter_preview_rls.py` — 47 — _(no header comment)_ — runner (pytest glob)
- `test_forecast_goal.py` — 275 — When will this reach X? — goal-seek along a forecast. — runner (pytest glob)
- `test_forecast_scenario.py` — 205 — What if spend rose 10%? — a projection with factors you can move. — runner (pytest glob)
- `test_frame_cache.py` — 150 — The process-local DataFrame memo: correctness properties that make it safe — runner (pytest glob)
- `test_frame_size_estimate.py` — 102 — Sizing a frame for the memo without walking every string in it. — runner (pytest glob)
- `test_frontend_constant_mirrors.py` — 371 — Frontend copies of backend limits must not drift. — runner (pytest glob)
- `test_geo_network_and_explain.py` — 81 — Geographic network shaper and the automated-explanation service. — runner (pytest glob)
- `test_geo_pies_layers.py` — 52 — Pie maps, multi-layer maps, and the density map's shared cluster shaper. — runner (pytest glob)
- `test_geography_classification.py` — 109 — Classifying a data item as Geography, the way SAS's data pane does. — runner (pytest glob)
- `test_get_widget_data_rls.py` — 44 — _(no header comment)_ — runner (pytest glob)
- `test_goal_seek.py` — 91 — Goal seeking on a linear fit over the secured frame. — runner (pytest glob)
- `test_graph_analytics.py` — 156 — Graph intelligence: communities and predicted links. — runner (pytest glob)
- `test_health_probes.py` — 162 — Liveness and readiness probes. — runner (pytest glob)
- `test_heatmap_granularity.py` — 66 — `dimension_granularity` must reach the matrix shapers too. — runner (pytest glob)
- `test_hierarchical_rls.py` — 276 — Hierarchical RLS (0016): access flows DOWN an organization's own chart. — runner (pytest glob)
- `test_hierarchy_auto_generate_dates.py` — 58 — _(no header comment)_ — runner (pytest glob)
- `test_hierarchy_auto_generate_directquery.py` — 48 — _(no header comment)_ — runner (pytest glob)
- `test_hierarchy_editing.py` — 93 — Editing auto-generated hierarchies: level removal heals the chain, levels — runner (pytest glob)
- `test_hierarchy_expand.py` — 40 — Hierarchy expand: multi-level grouping with path labels, composing with the — runner (pytest glob)
- `test_hierarchy_widget_analysis_org_scoping.py` — 88 — _(no header comment)_ — runner (pytest glob)
- `test_hierarchy_widgets.py` — 268 — Hierarchy widgets: five layouts over one shaper. — runner (pytest glob)
- `test_id_columns_sort_numeric.py` — 41 — Id-like columns are categories for aggregation, but NUMERIC for sorting. — runner (pytest glob)
- `test_import_row_cap.py` — 203 — Hardening task 2.3: the import/pandas path is bounded. — runner (pytest glob)
- `test_index_advice.py` — 229 — Index recommendations from what the platform has watched itself run. — runner (pytest glob)
- `test_infer_keys.py` — 304 — Stage 4 unit behaviour — each filter in isolation. — runner (pytest glob)
- `test_infer_keys_accuracy.py` — 243 — M1.4 - measured precision and recall of foreign-key inference. — runner (pytest glob)
- `test_infer_semantic.py` — 698 — Stage 5 — semantic types, roles, deprecation, and the LLM description pass. — runner (pytest glob)
- `test_inferential_statistics.py` — 657 — Inferential statistics: is the difference real, or is it noise? — runner (pytest glob)
- `test_insight_narrative.py` — 160 — The LLM narrative: phrasing, never evidence. — runner (pytest glob)
- `test_insight_novelty.py` — 323 — Novelty: what changed since the last scan. — runner (pytest glob)
- `test_insight_suggestions_identifiers.py` — 72 — The one-click chart suggestions must not sum an identifier. — runner (pytest glob)
- `test_insights.py` — 110 — The insights engine: each detector fires on data built to trigger it, stays — runner (pytest glob)
- `test_introspect.py` — 201 — Stage 1 — reading a database's own catalog. — runner (pytest glob)
- `test_key_influencers.py` — 270 — Key influencers: which factors move an outcome. — runner (pytest glob)
- `test_layer_conformance.py` — 391 — The seven-layer architecture, enforced. — runner (pytest glob)
- `test_lineage_notifications_comments.py` — 284 — Lineage graph, in-app notifications, and report comments. — runner (pytest glob)
- `test_llm_client.py` — 197 — The offline model client. — runner (pytest glob)
- `test_llm_gate.py` — 143 — One Qwen box serves the sync AND the agent (spec F5). — runner (pytest glob)
- `test_matrix_widget_type.py` — 10 — _(no header comment)_ — runner (pytest glob)
- `test_mcp_client.py` — 105 — The datalytics MCP server's API client (mcp_server/client.py). — runner (pytest glob)
- `test_mcp_client_reuse.py` — 66 — T8: the MCP server's `_client()` used to build a fresh DatalyticsClient (and HTTP — runner (pytest glob)
- `test_mdb.py` — 338 — Reading Microsoft Access files. — runner (pytest glob)
- `test_measure_bygroup.py` — 70 — BYGROUP: per-aggregation ByGroup context declared inside one measure. — runner (pytest glob)
- `test_measure_calc.py` — 133 — CALC: filter-context manipulation in the measure engine. — runner (pytest glob)
- `test_measure_eval.py` — 116 — Unit tests for the post-aggregation measure evaluator. — runner (pytest glob)
- `test_measures_api.py` — 173 — Measures CRUD + preview API, and the DirectQuery rejection. — runner (pytest glob)
- `test_metadata_api.py` — 665 — Layer 1 routes: org scoping, admin gating, and the review round trip. — runner (pytest glob)
- `test_metadata_cache.py` — 428 — The DuckDB sample cache — the thing that makes the two-plane split real. — runner (pytest glob)
- `test_metadata_store.py` — 266 — The provenance rule, which is the whole point of the metadata store. — runner (pytest glob)
- `test_metrics.py` — 182 — Metrics: emitted when otel is on, free when it is off. — runner (pytest glob)
- `test_migrate_backfill.py` — 72 — _(no header comment)_ — runner (pytest glob)
- `test_migrations.py` — 77 — T1/T2's ALTER-IF-NOT-EXISTS lines in app.main._migrate. — runner (pytest glob)
- `test_model_store.py` — 189 — Saving the champion, and scoring rows it has never seen. — runner (pytest glob)
- `test_monitoring_endpoints.py` — 120 — The Monitoring read API: /admin/monitoring/jobs and /deliveries. — runner (pytest glob)
- `test_narrate_one.py` — 150 — One guarded sentence for one finding -- the Dynamic Pin card's prose. — runner (pytest glob)
- `test_net_guard.py` — 73 — SSRF guard: metadata endpoints always blocked; private ranges by policy. — runner (pytest glob)
- `test_network_and_geo_shapes.py` — 63 — Network/link analysis with centralities, origin-destination lines, and grid — runner (pytest glob)
- `test_org_scope.py` — 36 — _(no header comment)_ — runner (pytest glob)
- `test_outlier_details.py` — 109 — Outlier details behind the ⚠ badge: fences, the rows, and the impact. — runner (pytest glob)
- `test_page_background.py` — 84 — A page background image, with widgets that can let it show through. — runner (pytest glob)
- `test_page_templates.py` — 165 — Page templates: serialise, rehydrate, and the import that is both at once. — runner (pytest glob)
- `test_page_visibility.py` — 104 — Per-role page visibility, enforced server-side. — runner (pytest glob)
- `test_parquet_sidecar.py` — 155 — The parquet sidecar: a verified derived cache next to each CSV. The CSV — runner (pytest glob)
- `test_pdf_export.py` — 82 — Server-rendered report PDF: the document builder and the download endpoint. — runner (pytest glob)
- `test_pdf_pagination.py` — 108 — The report PDF as a paginated document, not a screenshot. — runner (pytest glob)
- `test_phase3_registrations.py` — 14 — _(no header comment)_ — runner (pytest glob)
- `test_pii.py` — 172 — PII detection and masking for the sample cache. — runner (pytest glob)
- `test_pinned_tiles.py` — 377 — Pinned tiles: any chart on a personal, live home dashboard. — runner (pytest glob)
- `test_platform.py` — 115 — Platform super-admin: cross-org organization management + hierarchy. — runner (pytest glob)
- `test_prediction_models_api.py` — 308 — The model store over HTTP: train, list, score, delete — and who may. — runner (pytest glob)
- `test_prep_join.py` — 250 — Report-layer joins as a prep step: merge semantics, and the security spine -- — runner (pytest glob)
- `test_prep_steps.py` — 354 — Step-based prep pipeline: cleansing steps, ordering, validation, fail-soft. — runner (pytest glob)
- `test_prep_steps_api.py` — 347 — Prep pipeline end to end: the API contract, the load-order guarantees, and the — runner (pytest glob)
- `test_profile_generic.py` — 160 — Profiling where pg_stats is not available: other SQL families, and the — runner (pytest glob)
- `test_profile_pg_stats.py` — 159 — Reading PostgreSQL's own statistics instead of scanning the table. — runner (pytest glob)
- `test_publish_and_grants.py` — 339 — The publish/grant regime (0014): draft -> publish (view-only) -> share-to. — runner (pytest glob)
- `test_query_builder.py` — 309 — The query-model → SQL compiler: dialect quoting, derived GROUP BY, joins, — runner (pytest glob)
- `test_query_builder_api.py` — 241 — Query-builder routes end to end against a real SQLite connection: column — runner (pytest glob)
- `test_query_builder_hierarchy.py` — 207 — Self-referencing hierarchies in the query builder. — runner (pytest glob)
- `test_query_runs.py` — 392 — T5: query_runs telemetry -- each of the three query-execution write points — runner (pytest glob)
- `test_quick_calc_and_suppression.py` — 78 — Quick one-click calculations and confidentiality suppression on shape_series. — runner (pytest glob)
- `test_quotas.py` — 266 — Task E2: per-tenant quotas. — runner (pytest glob)
- `test_rank_capability.py` — 118 — Ranking as a cross-widget capability: the newly covered shapers. — runner (pytest glob)
- `test_rank_modes.py` — 61 — Rank selection's SAS-parity modes: percent-of-categories and the — runner (pytest glob)
- `test_rank_selection.py` — 38 — Rank selection: top/bottom N by aggregated value, independent of display sort. — runner (pytest glob)
- `test_rate_limit.py` — 175 — S5 rate limiting middleware (core/rate_limit.py): in-process token bucket, — runner (pytest glob)
- `test_recent_views.py` — 166 — Per-user Recents (0015): opening a dashboard is what makes it recent. — runner (pytest glob)
- `test_refresh_schedule.py` — 362 — Scheduled dataset refresh. — runner (pytest glob)
- `test_registry.py` — 302 — A4: analysis tool catalogue -- registry contents, the endpoint, and the — runner (pytest glob)
- `test_relationship_model.py` — 23 — _(no header comment)_ — runner (pytest glob)
- `test_relationships_org_scoping.py` — 120 — _(no header comment)_ — runner (pytest glob)
- `test_report_capabilities.py` — 164 — Per-report viewer capability levels: view / edit / data, enforced server-side. — runner (pytest glob)
- `test_report_classification.py` — 71 — Sensitivity labels on reports (gap row 470). — runner (pytest glob)
- `test_report_composer.py` — 175 — Auto-composed reports: placement, ordering, and the grid contract. — runner (pytest glob)
- `test_report_copilot.py` — 417 — The dashboard page copilot: chat that edits the OPEN page. — runner (pytest glob)
- `test_report_display_rules_api.py` — 46 — _(no header comment)_ — runner (pytest glob)
- `test_report_ownership.py` — 169 — Report authorship (`reports.created_by`, 0013) and the honest report list. — runner (pytest glob)
- `test_report_page_mobile_layout.py` — 26 — _(no header comment)_ — runner (pytest glob)
- `test_report_page_size.py` — 27 — _(no header comment)_ — runner (pytest glob)
- `test_report_parameters.py` — 210 — Report parameters: typed values referenced as @name in filters and expressions. — runner (pytest glob)
- `test_report_revision.py` — 203 — Report revision counter, the basis of concurrent-edit detection. — runner (pytest glob)
- `test_report_theme.py` — 17 — _(no header comment)_ — runner (pytest glob)
- `test_report_translations.py` — 45 — Per-locale report text overrides. — runner (pytest glob)
- `test_report_versions.py` — 137 — Report version history with restore (R2 of the competitive assessment). — runner (pytest glob)
- `test_reports_org_scoping.py` — 181 — _(no header comment)_ — runner (pytest glob)
- `test_require_org_admin.py` — 37 — _(no header comment)_ — runner (pytest glob)
- `test_reset_inferred_metadata.py` — 138 — Clearing what inference got wrong. — runner (pytest glob)
- `test_resolve_roles.py` — 120 — _(no header comment)_ — runner (pytest glob)
- `test_restricted_analysis_message.py` — 73 — What a restricted viewer is told when an analysis cannot run. — runner (pytest glob)
- `test_retrieval.py` — 504 — Tier 2 retrieval scorer (spec §1, Task R1). — runner (pytest glob)
- `test_rls_base_frame_choke_point.py` — 144 — S1 structural pin: every apply_rls_filter call site in the source tree sits at the — runner (pytest glob)
- `test_rls_fail_closed.py` — 34 — _(no header comment)_ — runner (pytest glob)
- `test_rls_user_context.py` — 124 — Dynamic user context in RLS: USEREMAIL()/USER()/USERID() (enterprise profiling). — runner (pytest glob)
- `test_router_reachability.py` — 154 — Every route the frontend calls must be a route the server serves. — runner (pytest glob)
- `test_row_security_rule_model.py` — 53 — _(no header comment)_ — runner (pytest glob)
- `test_rtl_pdf.py` — 219 — Right-to-left text in the server-side PDF. — runner (pytest glob)
- `test_saml.py` — 245 — SAML 2.0 SP-initiated Web SSO, driven against a mocked IdP. — runner (pytest glob)
- `test_sample_strategies.py` — 273 — Stage 3 — choosing HOW to take a sample. — runner (pytest glob)
- `test_scheduled_delivery.py` — 341 — Scheduled deliveries and data alerts. — runner (pytest glob)
- `test_scheduled_materialization.py` — 406 — A materialized dataset that keeps itself current. — runner (pytest glob)
- `test_scheduler_backoff.py` — 220 — The scheduler remembers failure, and one bad item no longer sinks its tick. — runner (pytest glob)
- `test_schema_isolation_concurrent.py` — 50 — Two sources on one database, different schemas, under concurrency. — runner (pytest glob)
- `test_script_tile.py` — 350 — A tile that runs server-side Python and shows what it returns. — runner (pytest glob)
- `test_secrets.py` — 50 — At-rest encryption of connection secrets (services/secrets.py). — runner (pytest glob)
- `test_security.py` — 55 — _(no header comment)_ — runner (pytest glob)
- `test_segment.py` — 199 — A2: KMeans segmentation with automatic k -- service-level fixture/degenerate — runner (pytest glob)
- `test_series_having_and_custom_sort.py` — 63 — Post-aggregate filters (HAVING) and explicit category ordering on shape_series. — runner (pytest glob)
- `test_shape_box_plot.py` — 53 — _(no header comment)_ — runner (pytest glob)
- `test_shape_bubble.py` — 132 — _(no header comment)_ — runner (pytest glob)
- `test_shape_bubble_animated.py` — 117 — _(no header comment)_ — runner (pytest glob)
- `test_shape_card.py` — 54 — _(no header comment)_ — runner (pytest glob)
- `test_shape_correlation_matrix.py` — 75 — _(no header comment)_ — runner (pytest glob)
- `test_shape_dual_series.py` — 130 — _(no header comment)_ — runner (pytest glob)
- `test_shape_forecast.py` — 234 — Unit tests for shape_forecast's methods: — runner (pytest glob)
- `test_shape_gantt.py` — 57 — _(no header comment)_ — runner (pytest glob)
- `test_shape_gauge.py` — 70 — _(no header comment)_ — runner (pytest glob)
- `test_shape_geo.py` — 55 — The map widgets' data shapes. — runner (pytest glob)
- `test_shape_heatmap.py` — 52 — _(no header comment)_ — runner (pytest glob)
- `test_shape_histogram.py` — 32 — _(no header comment)_ — runner (pytest glob)
- `test_shape_parallel_coordinates.py` — 48 — _(no header comment)_ — runner (pytest glob)
- `test_shape_series_target.py` — 35 — A bound target column in the series shape (the targeted-bar row). — runner (pytest glob)
- `test_shape_vector_plot.py` — 46 — _(no header comment)_ — runner (pytest glob)
- `test_shape_waterfall.py` — 43 — _(no header comment)_ — runner (pytest glob)
- `test_shape_xy_numeric.py` — 52 — _(no header comment)_ — runner (pytest glob)
- `test_share_link_access_log.py` — 103 — S4: share-link access log. `log_share_access_sync` follows the exact — runner (pytest glob)
- `test_share_link_viewer_identity.py` — 170 — S3: in-org sharing identity. An AUTHENTICATED IN-ORG viewer who follows a — runner (pytest glob)
- `test_share_links.py` — 357 — Guest share links: mint/list/revoke, and the anonymous surface's security -- — runner (pytest glob)
- `test_slicer_text_control.py` — 61 — A text control for a column whose value list is useless. — runner (pytest glob)
- `test_small_multiples.py` — 176 — Small multiples: the same chart, once per value of a facet field. — runner (pytest glob)
- `test_smoke.py` — 2 — _(no header comment)_ — runner (pytest glob)
- `test_source_description.py` — 272 — The database-level description — the artefact a person actually reads. — runner (pytest glob)
- `test_source_schema.py` — 112 — The Schema field on a connection, which until now did nothing. — runner (pytest glob)
- `test_source_unreachable.py` — 218 — What a reader sees when the customer's database is down. — runner (pytest glob)
- `test_sql_expr.py` — 113 — _(no header comment)_ — runner (pytest glob)
- `test_sso.py` — 246 — OIDC SSO flow, driven against a mocked identity provider. — runner (pytest glob)
- `test_stage_sample.py` — 280 — Stage 3 — the stage that actually reads rows from a source. — runner (pytest glob)
- `test_startup_migration_resilience.py` — 31 — S5 review fix: a transient DB error during the enc:v1->v2 startup migration — runner (pytest glob)
- `test_statistical_aggregations.py` — 107 — The aggregations SAS offers on a data item that this product did not. — runner (pytest glob)
- `test_subscriptions.py` — 233 — Self-serve subscriptions: a viewer signs themselves up for a report. — runner (pytest glob)
- `test_suggest_dashboard.py` — 514 — Suggest a whole dashboard for a named kind of person. — runner (pytest glob)
- `test_suggest_dashboards_endpoint.py` — 274 — The HTTP surface for "suggest dashboards for this dataset". — runner (pytest glob)
- `test_suggest_dataset_dashboard.py` — 752 — Proposing a dashboard for an existing dataset, for a named kind of person. — runner (pytest glob)
- `test_suggest_from_insights.py` — 183 — Proposing a dashboard with no model at all. — runner (pytest glob)
- `test_suggest_widgets.py` — 101 — Insight-driven widget suggestions, steered by the report description. — runner (pytest glob)
- `test_sweep_two.py` — 148 — Export disablement, column duplication, org themes. — runner (pytest glob)
- `test_sync_background.py` — 189 — Starting a sync must return immediately, and must never wedge the source. — runner (pytest glob)
- `test_sync_does_not_block.py` — 206 — A sync must not freeze the rest of the application. — runner (pytest glob)
- `test_sync_pipeline.py` — 286 — The six-stage pipeline. — runner (pytest glob)
- `test_table_multi_sort.py` — 61 — Multi-column sort for the raw table / list widget (gap row 362). — runner (pytest glob)
- `test_table_totals.py` — 160 — _(no header comment)_ — runner (pytest glob)
- `test_telemetry.py` — 210 — E3: OpenTelemetry, opt-in. — runner (pytest glob)
- `test_text_functions.py` — 136 — Text functions for the calculated-column engine. — runner (pytest glob)
- `test_text_topics.py` — 170 — What is this free text about? — topics from a column of comments. — runner (pytest glob)
- `test_time_axis_default_sort.py` — 89 — A chart with time on its x-axis should start in time order. — runner (pytest glob)
- `test_time_intelligence_functions.py` — 50 — _(no header comment)_ — runner (pytest glob)
- `test_time_intelligence_periods.py` — 53 — Quarterly and weekly time intelligence: QTD/WTD running sums, prior-period — runner (pytest glob)
- `test_timestamp_semantic_type.py` — 81 — A date column should be labelled a date, not merely not-mislabelled. — runner (pytest glob)
- `test_upload_path_safety.py` — 155 — Where uploaded bytes are allowed to land. — runner (pytest glob)
- `test_week_granularity.py` — 66 — `week` is an offered granularity that produced an empty chart. — runner (pytest glob)
- `test_widget_attribute_review.py` — 213 — Making each proposed chart actually useful before it is built. — runner (pytest glob)
- `test_widget_data_area_funnel.py` — 26 — _(no header comment)_ — runner (pytest glob)
- `test_widget_data_author_tokens.py` — 120 — S0: USEREMAIL()/USERID()/ORGID()/ORGNAME() must expand in ORDINARY author — runner (pytest glob)
- `test_widget_data_cache.py` — 98 — _(no header comment)_ — runner (pytest glob)
- `test_widget_data_cache_valkey_wiring.py` — 253 — Task O2: widget_data.py's cache functions actually route through — runner (pytest glob)
- `test_widget_data_directquery_router.py` — 246 — _(no header comment)_ — runner (pytest glob)
- `test_widget_data_display_rules.py` — 52 — _(no header comment)_ — runner (pytest glob)
- `test_widget_data_measures.py` — 249 — Integration tests: measures resolved through the full get_widget_data pipeline. — runner (pytest glob)
- `test_widget_data_rls_enforcement.py` — 111 — _(no header comment)_ — runner (pytest glob)
- `test_widget_data_thread_offload.py` — 78 — The widget-data hot path runs via asyncio.to_thread: same payloads, same — runner (pytest glob)
- `test_widget_error_codes.py` — 184 — Every widget-data error carries a code the frontend can act on. — runner (pytest glob)
- `test_widget_export.py` — 213 — Exporting a widget's data as CSV or Excel. — runner (pytest glob)
- `test_widget_roles.py` — 113 — What each widget type must be given before it can draw. — runner (pytest glob)
- `test_widget_shapers.py` — 34 — _(no header comment)_ — runner (pytest glob)
- `test_widget_templates.py` — 55 — Object templates: save a configured widget by name and reuse it org-wide. — runner (pytest glob)
- `test_workspace.py` — 696 — The workspace tree: folders, filed reports, and the rules that protect them. — runner (pytest glob)
- `test_workspace_grants.py` — 541 — Workspace sharing: folder grants that OPEN live access to a subtree. — runner (pytest glob)
- `test_xml_extraction.py` — 75 — F1: .xml joins csv/xlsx/xls/json/parquet as a supported upload extension. — runner (pytest glob)
- `test_yoy_growth_json_safe.py` — 26 — _(no header comment)_ — runner (pytest glob)

#### `embedding_server/` — 4 files, 370 LOC

- `download_model.py` — 24 — Build-time-only weight download. Runs exclusively inside the Dockerfile — TEXT-ONLY: embedding_server/Dockerfile
- `rank_stability.py` — 116 — fp32-vs-int8 rank-stability check (Task M1's gate for choosing the int8 — TEXT-ONLY: embedding_server/Dockerfile +1
- `server.py` — 181 — Self-hosted embeddings server -- Task M1 of — TEXT-ONLY: ARCHITECTURE.html +195
- `smoke.py` — 49 — Container-level smoke test -- Task M1's acceptance smoke: — TEXT-ONLY: ARCHITECTURE.html +19

#### `frontend/` — 2 files, 38 LOC

- `vite.config.ts` — 27 — _(no header comment)_ — TEXT-ONLY: docker-compose.yml +2
- `vitest.config.ts` — 11 — _(no header comment)_ — TEXT-ONLY: docs/superpowers/plans/2026-08-10-chart-phase0-foundation.md

#### `frontend/public/` — 1 files, 73 LOC

- `sw.js` — 73 — Minimal service worker. Its job is installability plus a usable offline shell — — TEXT-ONLY: frontend/nginx.conf +5

#### `frontend/scripts/` — 1 files, 74 LOC

- `bench_pageload.mjs` — 74 — Frontend fetch-waterfall benchmark: counts /widget-data requests and times — **NO**

#### `frontend/src/` — 5 files, 481 LOC

- `App.tsx` — 128 — _(no header comment)_ — yes: frontend/src/main.tsx
- `index.css` — 179 — MCAIT Design System — token bridge — TEXT-ONLY: COURSE_1_narrations.txt +241
- `main.tsx` — 34 — _(no header comment)_ — TEXT-ONLY: ARCHITECTURE.html +122
- `offlineAssets.test.ts` — 61 — Offline-readiness regression pin (Tier-4 Task O1). — runner (vitest glob)
- `pwa.test.ts` — 79 — Installability guards for the PWA. — runner (vitest glob)

#### `frontend/src/components/` — 31 files, 6,301 LOC

- `ActionMenu.test.tsx` — 153 — _(no header comment)_ — runner (vitest glob)
- `ActionMenu.tsx` — 189 — _(no header comment)_ — yes: frontend/src/components/ActionMenu.test.tsx +5
- `CommandPalette.test.tsx` — 75 — _(no header comment)_ — runner (vitest glob)
- `CommandPalette.tsx` — 189 — _(no header comment)_ — yes: frontend/src/components/CommandPalette.test.tsx +1
- `DatasetShareDialog.test.tsx` — 74 — _(no header comment)_ — runner (vitest glob)
- `DatasetShareDialog.tsx` — 131 — In-org dataset sharing, managed by org admins. — yes: frontend/src/components/DatasetShareDialog.test.tsx +1
- `DynamicPinCard.test.tsx` — 113 — The Dynamic Pin card: Insight Engine → Evidence Boundary → LLM Narrator. — runner (vitest glob)
- `DynamicPinCard.tsx` — 152 — A Dynamic Pin: one insight finding, pinned to the home dashboard. — yes: frontend/src/components/DynamicPinCard.test.tsx +1
- `FolderShareDialog.test.tsx` — 150 — The share dialog for a workspace folder. What carries risk: — runner (vitest glob)
- `FolderShareDialog.tsx` — 263 — Share a workspace folder — live, never a snapshot. — yes: frontend/src/components/FolderShareDialog.test.tsx +1
- `LanguageSwitcher.test.tsx` — 94 — Picking a language must move BOTH document attributes: `dir` (what mirrors — runner (vitest glob)
- `LanguageSwitcher.tsx` — 85 — _(no header comment)_ — yes: frontend/src/components/LanguageSwitcher.test.tsx +2
- `Layout.test.tsx` — 169 — Mutable so individual tests can drop the admin flag -- the rail's Monitoring — runner (vitest glob)
- `Layout.tsx` — 207 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-13-rls-phase3-frontend.md +3
- `NotificationsBell.test.tsx` — 41 — _(no header comment)_ — runner (vitest glob)
- `NotificationsBell.tsx` — 97 — _(no header comment)_ — yes: frontend/src/components/NotificationsBell.test.tsx +1
- `ProtectedRoute.tsx` — 9 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-13-rls-phase3-frontend.md +1
- `QueryBuilderDialog.test.tsx` — 328 — _(no header comment)_ — runner (vitest glob)
- `QueryBuilderDialog.tsx` — 637 — _(no header comment)_ — yes: frontend/src/components/QueryBuilderDialog.test.tsx +2
- `QueryCanvas.test.tsx` — 109 — _(no header comment)_ — runner (vitest glob)
- `QueryCanvas.tsx` — 234 — _(no header comment)_ — yes: frontend/src/components/QueryBuilderDialog.tsx +1
- `RequireAdmin.tsx` — 11 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-13-rls-phase3-frontend.md +1
- `RequireSuperAdmin.tsx` — 10 — _(no header comment)_ — yes: frontend/src/App.tsx
- `StatisticsPanel.test.tsx` — 772 — One screen for every runnable analysis, driven by the registry. — runner (vitest glob)
- `StatisticsPanel.tsx` — 273 — _(no header comment)_ — yes: frontend/src/components/StatisticsPanel.test.tsx +1
- `TopBar.test.tsx` — 93 — The top bar's three jobs: name the current page, open the ONE search — runner (vitest glob)
- `TopBar.tsx` — 162 — _(no header comment)_ — yes: frontend/src/components/Layout.tsx +1
- `WorkspaceTree.test.tsx` — 633 — The navigation menu. Three behaviours carry real risk: — runner (vitest glob)
- `WorkspaceTree.tsx` — 593 — _(no header comment)_ — yes: frontend/src/components/Layout.tsx +1
- `navigation.ts` — 155 — _(no header comment)_ — yes: frontend/src/components/Layout.tsx +1
- `navigationGuards.test.ts` — 100 — The rail's permission for a destination must match the ROUTE GUARD that — runner (vitest glob)

#### `frontend/src/components/analysis/` — 1 files, 807 LOC

- `analysisResults.tsx` — 807 — The result views two screens share. — yes: frontend/src/components/StatisticsPanel.tsx +2

#### `frontend/src/components/chat/` — 9 files, 1,693 LOC

- `AnalysisResult.test.tsx` — 109 — The agent answers some questions with an analysis instead of SQL. — runner (vitest glob)
- `AnalysisResult.tsx` — 50 — An analysis the agent ran instead of writing SQL. — yes: frontend/src/components/chat/AnalysisResult.test.tsx +1
- `ChatPane.test.tsx` — 437 — _(no header comment)_ — runner (vitest glob)
- `ChatPane.tsx` — 437 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-25-layer-4-agent-orchestration.md +3
- `ChatPaneProgress.test.tsx` — 81 — What the chat shows while it is working. — runner (vitest glob)
- `DashboardProposals.test.tsx` — 182 — The chat's answer to "suggest a dashboard for me". — runner (vitest glob)
- `DashboardProposals.tsx` — 171 — One dashboard the agent proposed: the query that builds its data, and the — yes: frontend/src/components/chat/ChatPane.tsx +1
- `Pending.tsx` — 72 — What the chat shows between pressing Send and the answer arriving. — yes: frontend/src/components/chat/ChatPane.tsx +1
- `ResultView.tsx` — 154 — A sink step's rows, drawn in the chat. — yes: frontend/src/components/chat/ChatPane.test.tsx +2

#### `frontend/src/components/dataset/` — 8 files, 1,935 LOC

- `AggregatesPanel.test.tsx` — 172 — The Aggregates tab. The governance rule -- the grain must include every — runner (vitest glob)
- `AggregatesPanel.tsx` — 243 — _(no header comment)_ — yes: docs/superpowers/plans/2026-09-12-aggregate-datasets.md +2
- `AlertsPanel.test.tsx` — 215 — Alerts shipped complete and unreachable. — runner (vitest glob)
- `AlertsPanel.tsx` — 266 — Watch a condition on this dataset and email someone when it becomes true. — yes: frontend/src/components/dataset/AlertsPanel.test.tsx +1
- `PredictionModelsPanel.test.tsx` — 160 — Saved models, and scoring rows with one. — runner (vitest glob)
- `PredictionModelsPanel.tsx` — 209 — Models kept so they can score rows they have never seen. — yes: frontend/src/components/dataset/PredictionModelsPanel.test.tsx +1
- `SuggestDashboardsDialog.test.tsx` — 340 — "Suggest dashboards", from the dataset list. — runner (vitest glob)
- `SuggestDashboardsDialog.tsx` — 330 — _(no header comment)_ — yes: frontend/src/components/dataset/SuggestDashboardsDialog.test.tsx +1

#### `frontend/src/components/expr/` — 2 files, 531 LOC

- `ExpressionBuilder.test.tsx` — 111 — _(no header comment)_ — runner (vitest glob)
- `ExpressionBuilder.tsx` — 420 — _(no header comment)_ — yes: frontend/src/components/dataset/AlertsPanel.tsx +5

#### `frontend/src/components/insights/` — 4 files, 198 LOC

- `FindingChart.test.tsx` — 81 — _(no header comment)_ — runner (vitest glob)
- `FindingChart.tsx` — 52 — _(no header comment)_ — yes: frontend/src/components/insights/FindingChart.test.tsx +2
- `MiniBarChart.test.tsx` — 30 — _(no header comment)_ — runner (vitest glob)
- `MiniBarChart.tsx` — 35 — A finding's chart, not a dashboard widget: no axes, no tooltip, no library -- — yes: frontend/src/components/insights/FindingChart.tsx +1

#### `frontend/src/components/report/` — 113 files, 23,564 LOC

- `AccessDialog.tsx` — 81 — _(no header comment)_ — yes: frontend/src/pages/ReportBuilder.tsx
- `BookmarksPane.test.tsx` — 34 — _(no header comment)_ — runner (vitest glob)
- `BookmarksPane.tsx` — 53 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-16-side-panes.md +2
- `BoundarySetPicker.test.tsx` — 199 — Choosing the shapes a region map draws — and getting a new set in. — runner (vitest glob)
- `BoundarySetPicker.tsx` — 154 — Which shapes a region map draws — and how a new set gets here. — yes: frontend/src/components/report/BoundarySetPicker.test.tsx +1
- `CalcColumnsPanel.palette.test.ts` — 41 — Structural guard on the expression palette. — runner (vitest glob)
- `CalcColumnsPanel.test.tsx` — 62 — _(no header comment)_ — runner (vitest glob)
- `CalcColumnsPanel.tsx` — 547 — _(no header comment)_ — yes: docs/superpowers/plans/2026-09-08-custom-calc-functions.md +3
- `CollapsibleSide.test.tsx` — 175 — _(no header comment)_ — runner (vitest glob)
- `CollapsibleSide.tsx` — 209 — _(no header comment)_ — yes: frontend/src/components/report/CollapsibleSide.test.tsx +1
- `ColumnFormatsPanel.test.tsx` — 47 — _(no header comment)_ — runner (vitest glob)
- `ColumnFormatsPanel.tsx` — 231 — _(no header comment)_ — yes: frontend/src/components/report/ColumnFormatsPanel.test.tsx +1
- `CommentsPane.test.tsx` — 63 — _(no header comment)_ — runner (vitest glob)
- `CommentsPane.tsx` — 88 — Discussion on the report: flat thread, newest last, optionally pinned to the — yes: frontend/src/components/report/CommentsPane.test.tsx +1
- `CopilotChat.test.tsx` — 159 — The page copilot panel: opens without touching the canvas, sends the — runner (vitest glob)
- `CopilotChat.tsx` — 212 — The page copilot: edit the OPEN dashboard page in plain language. — yes: frontend/src/components/report/CopilotChat.test.tsx +1
- `CrossFilterContext.test.tsx` — 58 — _(no header comment)_ — runner (vitest glob)
- `CrossFilterContext.tsx` — 228 — CrossFilterContext — yes: ReportBuilder.tsx +31
- `CustomCategoryPanel.test.tsx` — 242 — _(no header comment)_ — runner (vitest glob)
- `CustomCategoryPanel.tsx` — 211 — Custom categories — SAS's "custom category", Power BI's New group / New bin. — yes: frontend/src/components/report/CustomCategoryPanel.test.tsx +1
- `CustomFunctionsPanel.test.tsx` — 99 — _(no header comment)_ — runner (vitest glob)
- `CustomFunctionsPanel.tsx` — 151 — Management surface for a dataset's custom calculated-column functions -- — yes: docs/superpowers/plans/2026-09-08-custom-calc-functions.md +2
- `DataBarEditor.test.tsx` — 63 — _(no header comment)_ — runner (vitest glob)
- `DataBarEditor.tsx` — 54 — _(no header comment)_ — yes: frontend/src/components/report/DataBarEditor.test.tsx +1
- `DataView.test.tsx` — 138 — _(no header comment)_ — runner (vitest glob)
- `DataView.tsx` — 112 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-15-application-shell.md +2
- `DataViewsBar.test.tsx` — 98 — _(no header comment)_ — runner (vitest glob)
- `DataViewsBar.tsx` — 109 — Save/apply reusable data views: a named snapshot of a dataset's semantic — yes: frontend/src/components/report/DataView.tsx +1
- `DisplayRulesPanel.test.tsx` — 297 — _(no header comment)_ — runner (vitest glob)
- `DisplayRulesPanel.tsx` — 407 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-18-display-rules-engine.md +3
- `ExpandableGroup.test.tsx` — 86 — _(no header comment)_ — runner (vitest glob)
- `ExpandableGroup.tsx` — 94 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-20-chart-formatting-axis-options.md +3
- `ExplainDialog.test.tsx` — 67 — The generated sentence beside the factors. — runner (vitest glob)
- `ExplainDialog.tsx` — 138 — _(no header comment)_ — yes: frontend/src/components/report/ExplainDialog.test.tsx +2
- `FilterBar.test.tsx` — 87 — The page's filter strip. — runner (vitest glob)
- `FilterBar.tsx` — 47 — What is filtering this page, and a way to undo it. — yes: ReportBuilder.tsx +4
- `FloatingFilterWindow.test.tsx` — 120 — The filters, reachable from anywhere on a long page. — runner (vitest glob)
- `FloatingFilterWindow.tsx` — 109 — What is filtering this page, reachable from anywhere on it. — yes: frontend/src/components/report/FloatingFilterWindow.test.tsx +3
- `GraphLayersEditor.test.tsx` — 136 — Building a graph from layers, and getting it into the widget's config. — runner (vitest glob)
- `GraphLayersEditor.tsx` — 124 — Building a graph out of plot layers — the authoring half of Graph Builder. — yes: frontend/src/components/report/GraphLayersEditor.test.tsx +1
- `HierarchyTree.test.tsx` — 100 — _(no header comment)_ — runner (vitest glob)
- `HierarchyTree.tsx` — 147 — _(no header comment)_ — yes: ReportBuilder.tsx +3
- `InsightsPane.test.tsx` — 162 — _(no header comment)_ — runner (vitest glob)
- `InsightsPane.tsx` — 160 — _(no header comment)_ — yes: frontend/src/components/report/InsightsPane.test.tsx +1
- `InteractionSettings.tsx` — 116 — _(no header comment)_ — yes: WidgetConfigPanel.tsx +2
- `IntervalEditor.test.tsx` — 148 — _(no header comment)_ — runner (vitest glob)
- `IntervalEditor.tsx` — 110 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-21-table-chrome-and-rule-editors.md +2
- `MapPinsEditor.test.tsx` — 183 — Authoring map pins. — runner (vitest glob)
- `MapPinsEditor.tsx` — 151 — Author-placed pins on a coordinate map: "our new depot", "the flood line". — yes: frontend/src/components/report/MapPinsEditor.test.tsx +1
- `MeasuresPanel.test.tsx` — 145 — _(no header comment)_ — runner (vitest glob)
- `MeasuresPanel.tsx` — 265 — Authoring surface for post-aggregation measures. — yes: frontend/src/components/report/MeasuresPanel.test.tsx +1
- `MobileLayoutEditor.test.tsx` — 52 — _(no header comment)_ — runner (vitest glob)
- `MobileLayoutEditor.tsx` — 74 — _(no header comment)_ — yes: frontend/src/components/report/MobileLayoutEditor.test.tsx +1
- `ModelView.test.tsx` — 30 — _(no header comment)_ — runner (vitest glob)
- `ModelView.tsx` — 112 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-15-application-shell.md +2
- `OutlierDetailsDialog.test.tsx` — 58 — _(no header comment)_ — runner (vitest glob)
- `OutlierDetailsDialog.tsx` — 125 — _(no header comment)_ — yes: frontend/src/components/report/OutlierDetailsDialog.test.tsx +3
- `OutlinePane.test.tsx` — 44 — _(no header comment)_ — runner (vitest glob)
- `OutlinePane.tsx` — 99 — The report's structure as a tree: pages, their widgets, and container — yes: frontend/src/components/report/OutlinePane.test.tsx +1
- `PagePropertiesPanel.test.tsx` — 175 — _(no header comment)_ — runner (vitest glob)
- `PagePropertiesPanel.tsx` — 317 — _(no header comment)_ — yes: frontend/src/components/report/PagePropertiesPanel.test.tsx +1
- `PopupOverlay.tsx` — 83 — _(no header comment)_ — yes: frontend/src/pages/ReportBuilder.tsx
- `PrepPipelinePanel.test.tsx` — 477 — _(no header comment)_ — runner (vitest glob)
- `PrepPipelinePanel.tsx` — 808 — F2: the transform pipeline editor. Each step is a small card in order; the — yes: frontend/src/components/report/PrepPipelinePanel.test.tsx +1
- `PrepStepsPanel.test.tsx` — 125 — _(no header comment)_ — runner (vitest glob)
- `PrepStepsPanel.tsx` — 299 — Step-based data preparation editor: the ordered cleansing pipeline applied to — yes: frontend/src/components/report/DataView.tsx +1
- `ReviewPane.test.tsx` — 194 — _(no header comment)_ — runner (vitest glob)
- `ReviewPane.tsx` — 219 — _(no header comment)_ — yes: frontend/src/components/report/ReviewPane.test.tsx +1
- `SelectionPane.test.tsx` — 23 — _(no header comment)_ — runner (vitest glob)
- `SelectionPane.tsx` — 31 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-16-side-panes.md +2
- `ShareLinksDialog.test.tsx` — 104 — _(no header comment)_ — runner (vitest glob)
- `ShareLinksDialog.tsx` — 282 — _(no header comment)_ — yes: frontend/src/components/report/ShareLinksDialog.test.tsx +1
- `StatusBar.test.tsx` — 48 — _(no header comment)_ — runner (vitest glob)
- `StatusBar.tsx` — 39 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-15-application-shell.md +2
- `SubscribeButton.test.tsx` — 149 — _(no header comment)_ — runner (vitest glob)
- `SubscribeButton.tsx` — 194 — _(no header comment)_ — yes: frontend/src/components/report/SubscribeButton.test.tsx +1
- `SuggestionsPane.test.tsx` — 167 — _(no header comment)_ — runner (vitest glob)
- `SuggestionsPane.tsx` — 196 — _(no header comment)_ — yes: frontend/src/components/report/InsightsPane.tsx +2
- `SyncSlicersPane.test.tsx` — 25 — _(no header comment)_ — runner (vitest glob)
- `SyncSlicersPane.tsx` — 39 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-16-side-panes.md +2
- `TabOrderPane.test.tsx` — 25 — _(no header comment)_ — runner (vitest glob)
- `TabOrderPane.tsx` — 38 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-17-quick-win-visuals-formatting.md +2
- `TooltipPageOverlay.tsx` — 69 — _(no header comment)_ — yes: frontend/src/pages/ReportBuilder.tsx
- `TranslationsPane.tsx` — 93 — Localisation authoring: pick a locale, translate widget titles (and text — yes: frontend/src/pages/ReportBuilder.tsx
- `ValueMapEditor.test.tsx` — 78 — _(no header comment)_ — runner (vitest glob)
- `ValueMapEditor.tsx` — 47 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-21-table-chrome-and-rule-editors.md +2
- `VersionHistoryPane.test.tsx` — 62 — _(no header comment)_ — runner (vitest glob)
- `VersionHistoryPane.tsx` — 142 — Version history for the open report (R2 of the competitive assessment). — yes: frontend/src/components/report/VersionHistoryPane.test.tsx +1
- `WidgetConfigPanel.test.tsx` — 1645 — _(no header comment)_ — runner (vitest glob)
- `WidgetConfigPanel.tsx` — 2455 — _(no header comment)_ — yes: ReportBuilder.tsx +10
- `WidgetRenderer.test.tsx` — 2392 — _(no header comment)_ — runner (vitest glob)
- `WidgetRenderer.tsx` — 1776 — Reports the tile's measured size to the chart inside it. — yes: ReportBuilder.tsx +10
- `automaticSort.test.tsx` — 90 — A chart built in the UI must be able to NOT state a sort. — runner (vitest glob)
- `chartUtils.test.ts` — 201 — _(no header comment)_ — runner (vitest glob)
- `chartUtils.tsx` — 361 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-10-chart-phase0-foundation.md +51
- `containerRenderer.test.tsx` — 178 — _(no header comment)_ — runner (vitest glob)
- `customVisualTwoWay.test.tsx` — 146 — A custom visual that can select, not just display. — runner (vitest glob)
- `hierarchyConfig.test.tsx` — 189 — _(no header comment)_ — runner (vitest glob)
- `interactionPersistence.test.tsx` — 126 — Interactions have to survive a reload. — runner (vitest glob)
- `rankingGate.test.tsx` — 68 — _(no header comment)_ — runner (vitest glob)
- `roleColumnTypes.test.tsx` — 129 — _(no header comment)_ — runner (vitest glob)
- `rtlAxisSeam.test.tsx` — 105 — _(no header comment)_ — runner (vitest glob)
- `ruleCapabilities.test.ts` — 44 — Each expectation below is a claim about display_rules.py, not about layout: a — runner (vitest glob)
- `ruleCapabilities.ts` — 53 — Which controls a display-rule row should render, given the rule shape being — yes: frontend/src/components/report/DisplayRulesPanel.tsx +1
- `secondAggregation.test.tsx` — 96 — The second axis must be aggregable from the UI, not only from the API. — runner (vitest glob)
- `seriesPatterns.test.ts` — 66 — _(no header comment)_ — runner (vitest glob)
- `settingsTabs.test.tsx` — 240 — The settings rail: one object's settings, grouped the way SAS groups them. — runner (vitest glob)
- `themes.ts` — 34 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-17-quick-win-visuals-formatting.md +4
- `useMeasuredWidth.test.tsx` — 169 — The canvas must be laid out at the width it actually has. — runner (vitest glob)
- `useMeasuredWidth.ts` — 51 — The live width of an element, from the moment it exists. — yes: frontend/src/components/report/useMeasuredWidth.test.tsx +1
- `useWindowedRows.ts` — 59 — Below this row count, render everything exactly as before. This is the — yes: frontend/src/components/report/WidgetRenderer.tsx
- `widgetCapabilities.test.ts` — 203 — _(no header comment)_ — runner (vitest glob)
- `widgetCapabilities.ts` — 229 — Which formatting options each widget type can actually honour. — yes: docs/superpowers/plans/2026-08-20-chart-formatting-axis-options.md +3

#### `frontend/src/components/report/chartRenderers/` — 71 files, 8,813 LOC

- `AreaChartRenderer.tsx` — 27 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-17-quick-win-visuals-formatting.md +2
- `BarChartRenderer.tsx` — 146 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-10-chart-phase0-foundation.md +9
- `BoxPlotRenderer.tsx` — 66 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-11-chart-phase3-custom-rendered.md +1
- `BubbleChangePlotRenderer.tsx` — 102 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-10-chart-phase2-relationship-plots.md +4
- `BubbleChartRenderer.tsx` — 93 — v1 simplification: when a numeric `color` role is set (no `group`), interpolate a single — yes: docs/superpowers/plans/2026-08-10-chart-phase2-relationship-plots.md +2
- `ButterflyChartRenderer.tsx` — 57 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-11-chart-phase3-custom-rendered.md +2
- `ComparativeTimeSeriesRenderer.tsx` — 39 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-10-chart-phase1-native-recharts.md +3
- `CorrelationMatrixRenderer.tsx` — 56 — Diverging color scale: strong negative -> red, 0 -> neutral surface, strong positive -> accent blue. — yes: docs/superpowers/plans/2026-08-10-chart-phase2-relationship-plots.md +1
- `CustomGraphRenderer.test.tsx` — 85 — A chart the author composed from layers. — runner (vitest glob)
- `CustomGraphRenderer.tsx` — 104 — _(no header comment)_ — yes: frontend/src/components/report/chartRenderers/CustomGraphRenderer.test.tsx +1
- `DecompositionRenderer.test.tsx` — 119 — The decomposition tree's job is to stay honest while the reader explores. — runner (vitest glob)
- `DecompositionRenderer.tsx` — 124 — A decomposition tree: one number, broken down a level at a time. — yes: frontend/src/components/report/chartRenderers/DecompositionRenderer.test.tsx +1
- `DonutChartRenderer.tsx` — 78 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-10-chart-phase0-foundation.md +3
- `DotPlotRenderer.tsx` — 30 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-10-chart-phase1-native-recharts.md +3
- `DualAxisBarChartRenderer.tsx` — 39 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-10-chart-phase1-native-recharts.md +2
- `DualAxisBarLineChartRenderer.tsx` — 39 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-10-chart-phase1-native-recharts.md +4
- `DualAxisLineChartRenderer.tsx` — 39 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-10-chart-phase1-native-recharts.md +2
- `DualAxisTimeSeriesRenderer.tsx` — 41 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-10-chart-phase1-native-recharts.md +2
- `ForecastChartRenderer.tsx` — 140 — History as a solid line, forecast as a dashed one, the 95% interval as a band. — yes: frontend/src/components/report/chartRenderers/forecastGoal.test.tsx +1
- `FunnelChartRenderer.tsx` — 35 — _(no header comment)_ — yes: frontend/src/components/report/chartRenderers/PieDonutFunnelTreemapFormatting.test.tsx +1
- `GaugeRenderer.tsx` — 131 — Gauge shapes, SAS-style: one value+target result, five presentations. — yes: docs/superpowers/plans/2026-08-11-chart-phase3-custom-rendered.md +3
- `GeoChoroplethRenderer.tsx` — 143 — _(no header comment)_ — yes: frontend/src/components/report/chartRenderers/geoRenderers.test.tsx +1
- `GeoLineClusterRenderer.tsx` — 141 — _(no header comment)_ — yes: frontend/src/components/report/chartRenderers/geoRenderers.test.tsx +1
- `GeoNetworkRenderer.tsx` — 89 — _(no header comment)_ — yes: frontend/src/components/report/chartRenderers/geoRenderers.test.tsx +1
- `GeoPieLayerRenderer.tsx` — 222 — _(no header comment)_ — yes: frontend/src/components/report/chartRenderers/geoRenderers.test.tsx +2
- `GeoPointMapRenderer.tsx` — 262 — _(no header comment)_ — yes: frontend/src/components/report/chartRenderers/geoRenderers.test.tsx +1
- `HeatMapRenderer.tsx` — 56 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-10-chart-phase2-relationship-plots.md +1
- `HierarchyRenderer.test.tsx` — 122 — Circle packing: the geometry has to mean what it claims. — runner (vitest glob)
- `HierarchyRenderer.tsx` — 404 — Six hierarchy layouts over ONE shaped contract. — yes: frontend/src/components/report/chartRenderers/HierarchyRenderer.test.tsx +1
- `HistogramRenderer.tsx` — 32 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-10-chart-phase1-native-recharts.md +4
- `LineChartRenderer.tsx` — 36 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-10-chart-phase0-foundation.md +4
- `NeedlePlotRenderer.tsx` — 32 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-10-chart-phase1-native-recharts.md +1
- `NetworkGraphRenderer.tsx` — 123 — _(no header comment)_ — yes: frontend/src/components/report/chartRenderers/index.tsx +1
- `NumericSeriesPlotRenderer.tsx` — 42 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-10-chart-phase1-native-recharts.md +3
- `ParallelCoordinatesRenderer.tsx` — 46 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-10-chart-phase2-relationship-plots.md +1
- `PieChartRenderer.tsx` — 39 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-10-chart-phase0-foundation.md +3
- `PieDonutFunnelTreemapFormatting.test.tsx` — 146 — Slice 1 of the widget-enhancement roadmap: pie/donut/funnel/treemap silently — runner (vitest glob)
- `RibbonChartRenderer.tsx` — 125 — A real ribbon chart, Power BI-style: within each period the series stack in — yes: frontend/src/components/report/chartRenderers/axisOptions.integration.test.tsx +2
- `SankeyChartRenderer.tsx` — 27 — Flow diagram over the backend's {nodes, links}. Recharts ships a Sankey layout; — yes: frontend/src/components/report/chartRenderers/index.tsx
- `ScatterChartRenderer.tsx` — 33 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-10-chart-phase0-foundation.md +3
- `ScheduleChartRenderer.tsx` — 84 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-11-chart-phase3-custom-rendered.md +3
- `SmallMultiplesRenderer.test.tsx` — 93 — The one thing this visual must get right is the SHARED SCALE. Comparing the — runner (vitest glob)
- `SmallMultiplesRenderer.tsx` — 91 — Small multiples: the same chart repeated once per facet value. — yes: frontend/src/components/report/chartRenderers/SmallMultiplesRenderer.test.tsx +1
- `StepPlotRenderer.tsx` — 28 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-10-chart-phase1-native-recharts.md +2
- `TreemapChartRenderer.tsx` — 42 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-10-chart-phase0-foundation.md +2
- `VectorPlotRenderer.tsx` — 49 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-11-chart-phase3-custom-rendered.md +1
- `WaterfallChartRenderer.tsx` — 58 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-11-chart-phase3-custom-rendered.md +2
- `WordCloudRenderer.tsx` — 74 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-11-chart-phase3-custom-rendered.md +1
- `analyticsLines.test.ts` — 43 — _(no header comment)_ — runner (vitest glob)
- `analyticsLines.ts` — 38 — _(no header comment)_ — yes: frontend/src/components/report/chartRenderers/BarChartRenderer.tsx +2
- `axisOptions.integration.test.tsx` — 855 — _(no header comment)_ — runner (vitest glob)
- `axisOptions.test.ts` — 336 — _(no header comment)_ — runner (vitest glob)
- `axisOptions.ts` — 815 — Pure prop-builders for the Recharts Cartesian primitives. — yes: docs/superpowers/plans/2026-08-20-chart-formatting-axis-options.md +30
- `barSeries.test.ts` — 39 — _(no header comment)_ — runner (vitest glob)
- `barSeries.ts` — 25 — Reshapes shape_series's crosstab output ({ type: 'crosstab', columns: [dim, ...series, '__total__'], — yes: frontend/src/components/report/chartRenderers/BarChartRenderer.tsx +1
- `barTarget.test.tsx` — 60 — _(no header comment)_ — runner (vitest glob)
- `dualAxisSecondSeries.test.tsx` — 73 — _(no header comment)_ — runner (vitest glob)
- `forecastGoal.test.tsx` — 178 — "When will this reach X?" on the forecast itself. — runner (vitest glob)
- `gaugeShapes.test.tsx` — 108 — Locale-agnostic: this machine's locale renders Arabic-Indic digits, so the — runner (vitest glob)
- `geoRenderers.test.tsx` — 720 — Spread the real module: a partial mock of `services/api` has previously — runner (vitest glob)
- `geoUnmatchedAndDensity.test.tsx` — 72 — Two more ways a map could show nothing without saying so. — runner (vitest glob)
- `index.test.tsx` — 34 — _(no header comment)_ — runner (vitest glob)
- `index.tsx` — 122 — The map renderers pull in the bundled world geometry (~740 kB raw), which would — yes: MCAIT Design System/_adherence.oxlintrc.json +4
- `networkAnalytics.test.tsx` — 104 — Communities and predicted links, made visible. — runner (vitest glob)
- `rtlAxis.test.tsx` — 215 — _(no header comment)_ — runner (vitest glob)
- `ruleFillWiring.test.tsx` — 270 — _(no header comment)_ — runner (vitest glob)
- `svgDirection.test.ts` — 33 — Structural pin: every Recharts SVG is drawn in physical (ltr) coordinates. — runner (vitest glob)
- `types.ts` — 30 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-10-chart-phase0-foundation.md +54
- `xAxisLayout.test.tsx` — 96 — _(no header comment)_ — runner (vitest glob)
- `xAxisPlan.test.ts` — 171 — _(no header comment)_ — runner (vitest glob)
- `yAxisPlan.test.tsx` — 147 — _(no header comment)_ — runner (vitest glob)

#### `frontend/src/components/report/geo/` — 4 files, 897 LOC

- `regionSetCache.ts` — 78 — Fetch a boundary set once per page, not once per widget. — yes: frontend/src/components/report/chartRenderers/GeoChoroplethRenderer.tsx +1
- `worldGeometry.fit.test.ts` — 127 — A map should frame the data it is drawing. — runner (vitest glob)
- `worldGeometry.test.ts` — 331 — _(no header comment)_ — runner (vitest glob)
- `worldGeometry.ts` — 361 — World geometry for the map widgets: features, name matching, centroids. — yes: frontend/src/components/report/chartRenderers/GeoChoroplethRenderer.tsx +7

#### `frontend/src/components/review/` — 4 files, 641 LOC

- `EvidencePopover.tsx` — 40 — Why inference proposed a relationship. — yes: frontend/src/pages/SourceReview.tsx
- `JoinGraph.tsx` — 263 — _(no header comment)_ — yes: frontend/src/pages/SourceReview.tsx
- `SourceOverview.tsx` — 251 — What this database is, in plain language. — yes: frontend/src/pages/SourceReview.tsx
- `SyncProgress.tsx` — 87 — Per-stage outcome of a metadata sync. — yes: frontend/src/pages/SourceReview.tsx

#### `frontend/src/components/ui/` — 14 files, 1,058 LOC

- `ConfirmDialog.test.tsx` — 119 — Harness: a button that asks, and a readout of what the promise resolved to. */ — runner (vitest glob)
- `ConfirmDialog.tsx` — 155 — _(no header comment)_ — yes: docs/superpowers/plans/2026-09-08-custom-calc-functions.md +39
- `EmptyState.test.tsx` — 39 — _(no header comment)_ — runner (vitest glob)
- `EmptyState.tsx` — 37 — "There is nothing here yet" — distinct from LoadError's "we could not ask". — yes: docs/superpowers/plans/2026-09-09-custom-connector-framework.md +14
- `IconLabel.tsx` — 30 — An icon beside a label, for buttons and menu items. — yes: frontend/src/components/report/InsightsPane.tsx +6
- `ListFilter.test.tsx` — 110 — Dashboard, Reports, Connections and Dataflows each rendered their whole — runner (vitest glob)
- `ListFilter.tsx` — 81 — A search box for a list that renders every row it is given. — yes: frontend/src/components/ui/ListFilter.test.tsx +8
- `LoadError.tsx` — 44 — "We could not ask" — distinct from "there is nothing". — yes: docs/superpowers/plans/2026-09-09-custom-connector-framework.md +27
- `LoadingState.test.tsx` — 15 — _(no header comment)_ — runner (vitest glob)
- `LoadingState.tsx` — 11 — The one-line "Loading…" every page already wrote by hand — Dashboard, — yes: docs/superpowers/plans/2026-09-09-custom-connector-framework.md +22
- `modalAccessibility.test.tsx` — 110 — The modals, checked for the three things nine of them shipped without. — runner (vitest glob)
- `overlayCoverage.test.ts` — 106 — Every full-screen overlay must be a real dialog. — runner (vitest glob)
- `useModalDialog.test.tsx` — 106 — Nine dialogs shipped with no Escape, no focus trap and no `aria-modal`: a — runner (vitest glob)
- `useModalDialog.ts` — 95 — The keyboard mechanics every modal needs: Escape closes, Tab cycles inside, — yes: docs/superpowers/plans/2026-09-09-custom-connector-framework.md +23

#### `frontend/src/contexts/` — 3 files, 343 LOC

- `AuthContext.tsx` — 82 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-13-rls-phase3-frontend.md +18
- `DirectionContext.test.tsx` — 109 — _(no header comment)_ — runner (vitest glob)
- `DirectionContext.tsx` — 152 — _(no header comment)_ — yes: frontend/src/App.tsx +13

#### `frontend/src/hooks/` — 2 files, 64 LOC

- `useMediaQuery.test.ts` — 44 — _(no header comment)_ — runner (vitest glob)
- `useMediaQuery.ts` — 20 — Shared breakpoint queries — use these instead of inlining pixel values so every — yes: frontend/src/hooks/useMediaQuery.test.ts +1

#### `frontend/src/i18n/` — 4 files, 485 LOC

- `ar.ts` — 170 — Arabic UI strings. Keys must match `en.ts` exactly. */ — yes: frontend/src/i18n/index.test.ts +2
- `en.ts` — 170 — English UI strings. Arabic lives in `ar.ts`; keep the two key sets identical. */ — yes: frontend/src/i18n/ar.ts +2
- `index.test.ts` — 23 — _(no header comment)_ — runner (vitest glob)
- `index.ts` — 122 — _(no header comment)_ — yes: MCAIT Design System/_adherence.oxlintrc.json +20

#### `frontend/src/lib/` — 28 files, 2,202 LOC

- `aggregateDisclosure.test.ts` — 59 — _(no header comment)_ — runner (vitest glob)
- `aggregateDisclosure.ts` — 63 — Shown wherever an aggregate dataset is named in the builder. */ — yes: docs/superpowers/plans/2026-09-13-aggregate-followups.md +3
- `alignment.test.ts` — 29 — _(no header comment)_ — runner (vitest glob)
- `alignment.ts` — 42 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-17-quick-win-visuals-formatting.md +2
- `autoChart.test.ts` — 193 — Dropping fields on the canvas and getting the right chart. — runner (vitest glob)
- `autoChart.ts` — 162 — Which chart a set of dropped fields should become. — yes: frontend/src/lib/autoChart.test.ts +1
- `cellEdits.test.ts` — 110 — In-place cell editing, recorded as a prep step. — runner (vitest glob)
- `cellEdits.ts` — 85 — In-place cell editing, recorded as a prep step. — yes: frontend/src/lib/cellEdits.test.ts +1
- `columnRole.test.ts` — 31 — _(no header comment)_ — runner (vitest glob)
- `columnRole.ts` — 43 — Identifier-column detection — the frontend mirror of the metadata plane's — yes: frontend/src/components/report/WidgetConfigPanel.tsx +1
- `customCategories.test.ts` — 129 — Custom categories compile to expressions for the existing calculated-column — runner (vitest glob)
- `customCategories.ts` — 99 — Custom categories — SAS's "custom category", Power BI's New group / New bin. — yes: frontend/src/components/report/CustomCategoryPanel.tsx +1
- `displayRules.test.ts` — 47 — _(no header comment)_ — runner (vitest glob)
- `displayRules.ts` — 92 — Compiles a structured display-rule condition into an expression string for the — yes: docs/superpowers/plans/2026-08-18-display-rules-engine.md +14
- `fieldHints.test.ts` — 172 — The statistics behind these hints were already computed by `analyze_numeric` — — runner (vitest glob)
- `fieldHints.ts` — 99 — Inline field hints — SAS's "related measures" icon and outlier marker. — yes: frontend/src/lib/fieldHints.test.ts +1
- `hierarchyUtils.test.ts` — 42 — _(no header comment)_ — runner (vitest glob)
- `hierarchyUtils.ts` — 27 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-17-hierarchy-drill-down.md +3
- `pptExport.test.ts` — 55 — _(no header comment)_ — runner (vitest glob)
- `pptExport.ts` — 62 — Export the print view to PowerPoint: one widescreen slide per report page, — yes: frontend/src/lib/pptExport.test.ts +1
- `quickCalcs.test.ts` — 105 — One-click calculations from the field list. — runner (vitest glob)
- `quickCalcs.ts` — 86 — One-click calculations offered from the field list. — yes: frontend/src/lib/quickCalcs.test.ts +1
- `simpleExpr.test.ts` — 83 — _(no header comment)_ — runner (vitest glob)
- `simpleExpr.ts` — 105 — Compiles the "Simple" structured mode of ExpressionBuilder (C2) into the same — yes: frontend/src/components/expr/ExpressionBuilder.tsx +2
- `sqlWhere.test.ts` — 57 — _(no header comment)_ — runner (vitest glob)
- `sqlWhere.ts` — 76 — D3: a small SQL-specific compiler for the query-builder's WHERE rows. — yes: frontend/src/components/QueryBuilderDialog.tsx +1
- `widgetImage.ts` — 43 — Rasterise a live chart SVG to a PNG data URL. — yes: frontend/src/components/report/WidgetRenderer.tsx +1
- `zIndex.ts` — 6 — Shared z-index scale — keeps every overlay's stacking order intentional — yes: docs/superpowers/plans/2026-09-09-custom-connector-framework.md +13

#### `frontend/src/pages/` — 36 files, 15,141 LOC

- `AskAI.test.tsx` — 175 — The page's whole job is scope resolution: turn a URL or a picker choice — runner (vitest glob)
- `AskAI.tsx` — 256 — _(no header comment)_ — yes: frontend/src/App.tsx +1
- `Connections.test.tsx` — 120 — _(no header comment)_ — runner (vitest glob)
- `Connections.tsx` — 574 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-13-rls-phase3-frontend.md +3
- `ConnectionsPermissions.test.tsx` — 96 — The Connections page must not offer what the server will refuse. — runner (vitest glob)
- `Dashboard.test.tsx` — 353 — _(no header comment)_ — runner (vitest glob)
- `Dashboard.tsx` — 410 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-13-rls-phase3-frontend.md +3
- `Dataflows.test.tsx` — 173 — _(no header comment)_ — runner (vitest glob)
- `Dataflows.tsx` — 370 — _(no header comment)_ — yes: frontend/src/App.tsx +1
- `DatasetDetail.test.tsx` — 989 — _(no header comment)_ — runner (vitest glob)
- `DatasetDetail.tsx` — 1527 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-13-rls-phase3-frontend.md +2
- `EmbeddedReport.test.tsx` — 166 — _(no header comment)_ — runner (vitest glob)
- `EmbeddedReport.tsx` — 141 — _(no header comment)_ — yes: frontend/src/App.tsx +1
- `Home.test.tsx` — 195 — Home is a landing page built from data the app already serves. The claims — runner (vitest glob)
- `Home.tsx` — 300 — _(no header comment)_ — yes: frontend/src/App.tsx +1
- `InsightsHub.test.tsx` — 210 — The hub navigates, it never analyses -- so its contract is exactly its — runner (vitest glob)
- `InsightsHub.tsx` — 246 — _(no header comment)_ — yes: frontend/src/App.tsx +1
- `Lineage.test.tsx` — 259 — _(no header comment)_ — runner (vitest glob)
- `Lineage.tsx` — 256 — _(no header comment)_ — yes: frontend/src/App.tsx +2
- `Login.tsx` — 118 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-13-rls-phase3-frontend.md +1
- `ReportBuilder.test.tsx` — 1845 — _(no header comment)_ — runner (vitest glob)
- `ReportBuilder.tsx` — 3075 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-13-rls-phase3-frontend.md +3
- `ReportPrint.test.tsx` — 51 — _(no header comment)_ — runner (vitest glob)
- `ReportPrint.tsx` — 116 — _(no header comment)_ — yes: frontend/src/App.tsx +1
- `Reports.test.tsx` — 173 — _(no header comment)_ — runner (vitest glob)
- `Reports.tsx` — 345 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-13-rls-phase3-frontend.md +3
- `SharedReport.test.tsx` — 174 — _(no header comment)_ — runner (vitest glob)
- `SharedReport.tsx` — 160 — _(no header comment)_ — yes: frontend/src/App.tsx +1
- `SourceReview.live.test.tsx` — 228 — The review page against a REAL catalog. — runner (vitest glob)
- `SourceReview.test.tsx` — 672 — Stage 7 — human confirmation. — runner (vitest glob)
- `SourceReview.tsx` — 756 — _(no header comment)_ — yes: frontend/src/App.tsx +2
- `SsoCallback.tsx` — 25 — Landing page for the OIDC redirect. The backend hands us a datalytics token in the — yes: frontend/src/App.tsx
- `Upload.test.tsx` — 206 — The upload page after it learned to take several files. — runner (vitest glob)
- `Upload.tsx` — 187 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-13-rls-phase3-frontend.md +2
- `listFilterWiring.test.tsx` — 57 — Every page that renders a search box must actually filter with it. — runner (vitest glob)
- `loadFailures.test.tsx` — 137 — _(no header comment)_ — runner (vitest glob)

#### `frontend/src/pages/admin/` — 24 files, 3,660 LOC

- `AdminAudit.test.tsx` — 102 — _(no header comment)_ — runner (vitest glob)
- `AdminAudit.tsx` — 105 — S5: read-only trail of security-relevant admin mutations -- row/column — yes: frontend/src/App.tsx +1
- `AdminColumnSecurityRules.test.tsx` — 119 — _(no header comment)_ — runner (vitest glob)
- `AdminColumnSecurityRules.tsx` — 237 — _(no header comment)_ — yes: frontend/src/App.tsx +1
- `AdminCustomConnectors.test.tsx` — 68 — _(no header comment)_ — runner (vitest glob)
- `AdminCustomConnectors.tsx` — 175 — _(no header comment)_ — yes: docs/superpowers/plans/2026-09-09-custom-connector-framework.md +2
- `AdminExportPolicy.test.tsx` — 54 — _(no header comment)_ — runner (vitest glob)
- `AdminExportPolicy.tsx` — 138 — _(no header comment)_ — yes: frontend/src/App.tsx +1
- `AdminOrgUnits.test.tsx` — 120 — The page authors the org chart and places people in it. What matters is that — runner (vitest glob)
- `AdminOrgUnits.tsx` — 219 — _(no header comment)_ — yes: frontend/src/App.tsx +1
- `AdminRoles.test.tsx` — 44 — _(no header comment)_ — runner (vitest glob)
- `AdminRoles.tsx` — 149 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-13-rls-phase3-frontend.md +2
- `AdminRowSecurityRules.test.tsx` — 221 — _(no header comment)_ — runner (vitest glob)
- `AdminRowSecurityRules.tsx` — 499 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-13-rls-phase3-frontend.md +2
- `AdminSso.test.tsx` — 53 — _(no header comment)_ — runner (vitest glob)
- `AdminSso.tsx` — 191 — _(no header comment)_ — yes: frontend/src/App.tsx +1
- `AdminUsers.test.tsx` — 66 — _(no header comment)_ — runner (vitest glob)
- `AdminUsers.tsx` — 278 — _(no header comment)_ — yes: docs/superpowers/plans/2026-08-13-rls-phase3-frontend.md +2
- `ApiKeys.test.tsx` — 103 — _(no header comment)_ — runner (vitest glob)
- `ApiKeys.tsx` — 121 — _(no header comment)_ — yes: frontend/src/App.tsx +2
- `ConnectionRowPolicies.test.tsx` — 115 — Row rules for a CONNECTION — the ones Ask AI obeys. — runner (vitest glob)
- `ConnectionRowPolicies.tsx` — 184 — _(no header comment)_ — yes: frontend/src/App.tsx +1
- `PlatformOrgs.test.tsx` — 101 — _(no header comment)_ — runner (vitest glob)
- `PlatformOrgs.tsx` — 198 — _(no header comment)_ — yes: frontend/src/App.tsx +1

#### `frontend/src/pages/monitoring/` — 4 files, 481 LOC

- `Monitoring.test.tsx` — 157 — The three Monitoring pages are read-only aggregations; what can go wrong in — runner (vitest glob)
- `MonitoringActivity.tsx` — 85 — _(no header comment)_ — yes: frontend/src/App.tsx +1
- `MonitoringDeliveries.tsx` — 96 — _(no header comment)_ — yes: frontend/src/App.tsx +1
- `MonitoringJobs.tsx` — 143 — _(no header comment)_ — yes: frontend/src/App.tsx +1

#### `frontend/src/services/` — 2 files, 2,273 LOC

- `api.ts` — 2171 — _(no header comment)_ — yes: ReportBuilder.tsx +189
- `widgetDataFetch.test.ts` — 102 — The widget-data fetch discipline in api.ts: in-flight dedup, the 30s TTL — runner (vitest glob)

#### `frontend/src/styles/` — 2 files, 295 LOC

- `datalytics-fonts.css` — 66 — Datalytics — Webfonts (self-hosted, offline-safe) — yes: frontend/src/index.css
- `datalytics.css` — 229 — Datalytics — product theme — yes: frontend/src/index.css

#### `frontend/src/styles/mcait/` — 5 files, 310 LOC

- `colors.css` — 62 — MCAIT — Color tokens — yes: MCAIT Design System/styles.css +1
- `fonts.css` — 117 — MCAIT — Webfonts (self-hosted, offline-safe) — yes: MCAIT Design System/styles.css +1
- `products.css` — 65 — MCAIT — Per-product accent themes — yes: MCAIT Design System/styles.css +1
- `spacing.css` — 33 — MCAIT — Spacing, radii, shadows, motion — yes: MCAIT Design System/styles.css +1
- `typography.css` — 33 — MCAIT — Typography tokens — yes: MCAIT Design System/styles.css +1

#### `frontend/src/test/` — 4 files, 146 LOC

- `authInterceptor.test.ts` — 87 — _(no header comment)_ — runner (vitest glob)
- `renderWithProviders.tsx` — 26 — `render` with the app-level providers a component may reach for. — yes: docs/superpowers/plans/2026-09-08-custom-calc-functions.md +17
- `setup.ts` — 26 — jsdom doesn't implement matchMedia -- Layout.tsx's theme detection (and anything — TEXT-ONLY: ARCHITECTURE.html +27
- `smoke.test.ts` — 7 — _(no header comment)_ — runner (vitest glob)

#### `frontend/src/types/` — 1 files, 605 LOC

- `report.ts` — 605 — _(no header comment)_ — yes: ReportBuilder.tsx +62

#### `postgres/` — 1 files, 99 LOC

- `init.sql` — 99 — _(no header comment)_ — TEXT-ONLY: .claude/settings.local.json +10

#### `scripts/` — 8 files, 1,394 LOC

- `backup.ps1` — 168 — _(no header comment)_ — TEXT-ONLY: ARCHITECTURE.html +5
- `build_offline_bundle.ps1` — 262 — _(no header comment)_ — TEXT-ONLY: ARCHITECTURE.html +4
- `demo_down.ps1` — 100 — _(no header comment)_ — TEXT-ONLY: docs/DEMO_WALKTHROUGH.md +1
- `demo_up.ps1` — 239 — _(no header comment)_ — TEXT-ONLY: docs/DEMO_WALKTHROUGH.md +2
- `export_users_workbook.py` — 223 — Write the live identity map to an Excel workbook (demo passwords included). — **NO**
- `restore.ps1` — 185 — _(no header comment)_ — TEXT-ONLY: ARCHITECTURE.html +28
- `seed_demo_gaps.py` — 129 — Demo content for the two frontend pages the existing seeder leaves empty. — **NO**
- `seed_dev_accounts.py` — 88 — Seed the dev accounts the local stack was missing: a super admin, and two — TEXT-ONLY: scripts/export_users_workbook.py

---

## 5. RUNTIME FLOW

One full cycle: **a chart on a dashboard fetches its data.** This is the hottest path in the product — six UI surfaces share it. Functions are named in call order.

**1. Render.** `frontend/src/components/report/WidgetRenderer.tsx:45` imports `widgetDataApi` from `../../services/api`. The component resolves which dataset the widget reads (`WidgetRenderer.tsx:216`, `cfgDatasetId ?? datasetId` — a widget may override the report's dataset) and calls the query.

**2. Client transport.** `frontend/src/services/api.ts:1509` `widgetDataApi` wraps `api.post(\`/datasets/${dsId}/widget-data\`, body)` at `api.ts:1531`. Three mechanisms guard it, applied *only* here (`api.ts:1477`): in-flight de-duplication, a 30-second TTL cache capped at 100 entries, and a concurrency gate of 6. This is the single Axios instance for the whole app — no other frontend file performs HTTP. A 401 anywhere triggers the interceptor and ends the session; 403 has no global handler.

**3. Route.** `backend/app/routers/widget_data.py:359` `@router.post("/{dataset_id}/widget-data")` → `query_widget` (`:360`), mounted at `/api/v1` by `app/main.py:501`. It delegates to `_resolve_widget_data` (`widget_data.py:195`), which is where every gate lives, in this order:

| Order | Call | File:line | Purpose |
|---|---|---|---|
| a | `db.execute(...)` load `Dataset` | `widget_data.py:214` | org-scoped fetch; a cross-tenant id answers 404 |
| b | `require_dataset_read(...)` | `widget_data.py:236` | capability check |
| c | `quotas.enforce_query_quota(db, org_id)` | `widget_data.py:250` | per-org daily cap; raises `QuotaExceeded` → 429 |
| d | `_apply_report_parameters(req, db, user)` | `widget_data.py:252` / def at `:77` | substitutes typed `@name` parameters as literals |
| e | `resolve_rls_expr(db, user, dataset_id)` | `core/rls.py:167` | the row predicate for this user's role |
| f | `resolve_denied_columns(db, user, dataset_id)` | `core/rls.py:250` | the column denylist |
| g | denied-column refusal | `widget_data.py:279-291` | a **DirectQuery** widget naming a denied column → 403; import mode drops it instead |

**4a. DirectQuery branch** (`widget_data.py:295-305`): `asyncio.to_thread(...)` into `services/direct_query.py`, which compiles the widget config to dialect-correct SQL with the row predicate translated into the `WHERE` clause, and executes it on the customer's database through the pooled engine registry (`services/engines.py`, re-exported at `direct_query.py:551`). Anything it cannot express raises `DirectQueryUnsupported` rather than falling back.

**4b. Import branch** (`widget_data.py:318-350`): `resolve_join_frames` (prep-step joins) and `expand_author_expressions` (`core/rls.py:207`, calculated columns and measures) run first, then `asyncio.to_thread` into `services/widget_data.py:3183` `get_widget_data(...)`, passing `rls_filter_expr`, `drop_columns=denied`, `prep_steps`. Inside: the Parquet sidecar or source file is loaded into a pandas frame (memoised on path + mtime + size), `apply_rls_filter(df, expr)` (`services/widget_data.py:3065`) removes rows the role may not see, denied columns are dropped, `_apply_filters` (`:314`) applies the widget's own filters, and the shaper for the widget type is dispatched from the `SHAPERS` table at `services/widget_data.py:2482` (e.g. `shape_series` `:339`, `shape_histogram` `:737`, `shape_sankey` `:2204`). Eligible configs are pushed into DuckDB instead of pandas (`services/duck_agg.py`).

**5. Response.** `{rows, columns, total, ...}`, or the error contract `{type: 'error', code, message}`. `_record_widget_metrics` (`services/widget_data.py:85`) emits the OpenTelemetry counters; a `QueryRun` row records the hashed SQL and column *names* (never values).

**6. Back in the UI.** `WidgetRenderer` draws the chart, or renders an `EmptyState` for `type === 'error'`. Only `source_unavailable` and `quota` get a "Try again" button — every other code is deterministic and a retry would return the same answer.

**Order matters and is deliberate:** the row rule is applied over *every* column, and only then are denied columns dropped. Reversing it would let a rule that filters on a hidden column return nothing.

---

## 6. DEAD WEIGHT CANDIDATES

Confidence rules used here: **HIGH** = the name was searched across all 1,183 tracked files including string literals, config, docs and HTML, and the only hit is its own definition (or a proven-unreachable copy). **MEDIUM** = no caller found, but a plausible non-static consumer exists. **LOW** = guess, stated as such.

### 6.1 Duplicate / superseded files at the repo root — HIGH

Nine files sit at the repo root that belong to `frontend/` or `backend/`. All nine were added in one commit on **2026-06-30** and, except one, never touched again, while their real counterparts grew 5–15×.

| Path | LOC | Real counterpart | LOC | Evidence | Conf. |
|---|---|---|---|---|---|
| `init.sql` | 99 | `postgres/init.sql` | 99 | `diff -q` reports **IDENTICAL**. Both `docker-compose.yml:14` and `docker-compose2.yml:14` mount `./postgres/init.sql`; nothing mounts the root copy. | **HIGH** |
| `ReportBuilder.tsx` | 300 | `frontend/src/pages/ReportBuilder.tsx` | 3,075 | unreachable — see note | **HIGH** |
| `WidgetRenderer.tsx` | 373 | `frontend/src/components/report/WidgetRenderer.tsx` | 1,776 | unreachable | **HIGH** |
| `WidgetConfigPanel.tsx` | 198 | `frontend/src/components/report/WidgetConfigPanel.tsx` | 2,455 | unreachable | **HIGH** |
| `CrossFilterContext.tsx` | 98 | `frontend/src/components/report/CrossFilterContext.tsx` | 228 | unreachable | **HIGH** |
| `widget_data.py` | 231 | `backend/app/routers/widget_data.py` (418) + `backend/app/services/widget_data.py` (3,644) | — | no `import widget_data` / `from widget_data` outside the `app.` package | **HIGH** |
| `analytics.py` | 141 | `backend/app/services/analytics.py` | 168 | no `import analytics` / `from analytics` at top level | **HIGH** |
| `README2.md` | 197 | — | — | byte-for-byte stale twin of `README.md` (both say "12 widget types" at line 46; the real count is 67) | **HIGH** |
| `docker-compose2.yml` | 68 | `docker-compose.yml` (261) | — | no reference outside prose; **but last touched 2026-09-08**, so someone may still run it by hand | **MEDIUM** |

**Why the four `.tsx` copies are unreachable, not merely unimported:** the Vite root is `frontend/`, and no file under `frontend/src/` contains an import climbing above `src/` (`grep -rn "from '\.\./\.\./\.\./\.\./" frontend/src/` → zero hits). The FILE MAP shows these rows as `yes: …` — **that is a basename collision**, not a real reference: `from './CrossFilterContext'` resolves to the file in `components/report/`. Only 17 of 933 distinct basenames in the repo collide; these four are among them.

### 6.2 `postgres/init.sql` is a stale bootstrap — HIGH

It creates 8 tables; the live schema is SQLAlchemy `create_all` plus 29 Alembic revisions producing **77** tables. `charts` exists in `init.sql` and **has no model, no query and no migration** — `grep -rn "charts"` finds no `__tablename__ = "charts"` anywhere in `backend/app/models/`. Seven of its eight tables (`datasets`, `dataset_columns`, `reports`, `report_pages`, `report_widgets`, `analysis_results`, `hierarchy_nodes`) still exist as models, so the file is not wholly dead — but it is not the schema of record and will drift silently. Conf. **HIGH** for `charts`, **MEDIUM** for retiring the file.

### 6.3 Source files with zero references of any kind — HIGH

Fourteen files, excluding anything collected by a test-runner glob or the Alembic revision chain.

| Path | LOC | Evidence | Conf. |
|---|---|---|---|
| `MCAIT Design System/components/core/{Alert,AppBar,Avatar,Badge,Button,Card,Input,Sidebar,Switch,Tabs}.d.ts` | 8–65 (227 total) | Ten TypeScript declaration files. Their type names (`AlertProps`, `MCAITUser`, `SidebarVolume`, …) appear in **no** file but their own. The app consumes only the design system's **CSS** (`frontend/src/styles/mcait/*.css`); it imports no MCAIT component. | **HIGH** |
| `frontend/scripts/bench_pageload.mjs` | 74 | Zero callers anywhere. Also **broken on this checkout**: line 10 hardcodes `createRequire('file:///D:/data_analytics/frontend/')`, a path that does not exist — the repo is at `D:/Omda 2025/projects/data_analysis_dashboard_ai/AI_data_tool/data_analytics`. It is the only consumer of the npm `playwright` devDependency. | **HIGH** |
| `backend/scripts/validate_pipeline.py` | 240 | No caller in any script, compose file, Dockerfile, `.ps1`, or `package.json`. (It *imports* `create_org_admin`, so it is a leaf.) | **MEDIUM** — a human may run it by hand |
| `scripts/export_users_workbook.py` | 223 | No caller. Produces `datalytics-users-and-privileges.xlsx`, which is itself referenced only from `.gitignore` and prose. | **MEDIUM** — human-run tool |
| `scripts/seed_demo_gaps.py` | 129 | No caller. `scripts/demo_up.ps1` does not invoke it. | **MEDIUM** — human-run tool |

### 6.4 Scripts with no caller — MEDIUM

Beyond §6.3, these are referenced **only from Markdown prose**, never from code, compose, CI or another script: `backend/scripts/bench_http.py`, `bench_dashboard.py`, `bench_widget_data.py`, `bench_directquery.py`, `bench_equivalence.py`, `compat_check.py`, `smoke_embeddings.py`, `ui_walkthrough.py`. `bench_common.py` is imported by four of them, so the bench family is internally consistent — it is the *family* that has no automated caller. Conf. **MEDIUM**; these are developer tools, and a doc reference is a legitimate invocation record.

### 6.5 Exported symbols with zero consumers — HIGH where marked

Across the whole repo, 2,287 top-level symbols have no consumer outside their own file. Most are false alarms (see §7). After excluding routers, tests and migrations, **130** remain; of those, exactly **8** have their name appear only once in the entire repository — i.e. at the definition itself. Five of the eight are framework hooks (§7). The three that are genuinely dead:

| Symbol | Path:line | Evidence | Conf. |
|---|---|---|---|
| `WidgetDataResponse` | `backend/app/schemas/schemas.py:463` | Pydantic model, 7 fields. `grep -rl --fixed-strings WidgetDataResponse` over every tracked file → **1 file** (its own). No `response_model=` uses it; the widget-data endpoints return plain dicts. | **HIGH** |
| `SKIN_OPTIONS` | `frontend/src/components/report/WidgetRenderer.tsx:74` | `export const SKIN_OPTIONS = ['none','flat','raised','recessed','sheen','gloss','matte']`. Whole-repo search → 1 file. The adjacent `SKIN_SHADOWS` map *is* used by `skinShadow()` at `:76`; the exported option list is not — so no UI offers these skins. | **HIGH** |
| `NARROW_DESKTOP_QUERY` | `frontend/src/hooks/useMediaQuery.ts:6` | `export const NARROW_DESKTOP_QUERY = '(max-width: 1200px)'`. Whole-repo search → 1 file. Its sibling `MOBILE_QUERY` is consumed; this one never was. | **HIGH** |

**17 exported TypeScript types in `frontend/src/services/api.ts` have no importer:** `AnalysisRunResponse`, `AssociationRule`, `BatchUploadResult`, `BoundarySetDetail`, `DataAlertInput`, `DataflowOutput`, `DemoSeedResult`, `IndexAdviceColumn`, `KeyInfluencer`, `OrgUsage`, `ProfiledColumn`, `ReviewColumn`, `SubscribeBody`, `SyncStage`, `SyncStarted`, `UserOrgUnitRow`, `WidgetRelation`. Each is used inside `api.ts` as a return annotation, so removing the `export` keyword is safe; removing the type is not. Conf. **HIGH** for "no external consumer", **LOW** for "deletable".

### 6.6 API functions with zero callers — HIGH

Fifteen functions in `frontend/src/services/api.ts` are exported and never called anywhere in `frontend/src/` outside `api.ts` itself. Re-verified this audit with `grep -rl --fixed-strings` per name:

`boundarySetsApi.remove`, `columnFormatsApi.get`, `dataViewsApi.delete`, `dataflowsApi.get`, `dataflowsApi.update`, `demoApi.unseed`, `hierarchyApi.create`, `metadataApi.columnStats`, `orgUnitsApi.myScope`, `orgUnitsApi.update`, `relationshipsApi.delete`, `reportsApi.getClassification`, `themesApi.create`, `themesApi.delete`, `workspaceApi.roles` — **0 callers each**.

Three are the "read current value" companions to setters that *are* wired (`reportsApi.getClassification`, `workspaceApi.roles`, `columnFormatsApi.get`), meaning those editors open from a blank rather than the server's value — a bug, not dead code. `demoApi.unseed` means seeded demo content cannot be removed from the UI. Conf. **HIGH** that they are uncalled; deleting them would remove capability the backend still offers.

### 6.7 Backend endpoints no client in this repo calls — MEDIUM/HIGH

279 routes were enumerated from `@router.<method>(...)` decorators and matched against `frontend/src/services/api.ts`, which is the **only** file in the repo that performs HTTP.

| Endpoint | File:line | Frontend caller | Backend test | Conf. |
|---|---|---|---|---|
| `POST /{dataset_id}/statistics/independence` | `routers/analysis.py:430` | none | none | **HIGH** |
| `POST /{dataset_id}/statistics/glm-logistic` | `routers/analysis.py:481` | none | none | **HIGH** |
| `POST /{dataset_id}/statistics/mixed-model` | `routers/analysis.py:499` | none | none | **HIGH** |
| `POST /{dataset_id}/statistics/survival` | `routers/analysis.py:520` | none | none | **HIGH** |
| `POST /{dataset_id}/statistics/pairwise` | `routers/analysis.py:539` | none | none | **HIGH** |
| `GET/POST/DELETE /{source_id}/glossary[/{term_id}]` | `routers/metadata.py` (3 routes) | none | none | **HIGH** |
| `POST /{source_id}/review/reset-inferred` | `routers/metadata.py:720` | none | `backend/tests/test_reset_inferred_metadata.py` (6 calls) | **MEDIUM** |

The frontend runs statistics through the **generic** registry instead — `analysisCatalogueApi.run` posts to `/datasets/{id}/analysis/run` (`api.ts:480`) after reading `/analysis/registry` (`api.ts:477`). The five direct endpoints above are a parallel, unexercised entry to the same service functions. `compare-groups` and `correlation` share slugs with registry analyses, so they are not listed.

The `glossary` trio is a complete CRUD surface with a model (`models.py:1534` `__tablename__ = "glossary_terms"`) and a migration (`0001_baseline.py:165`) and **no reader at all** — no UI, no test, no MCP tool.

### 6.8 Dependencies declared but never imported — HIGH / MEDIUM

| Package | Manifest | Evidence | Conf. |
|---|---|---|---|
| `aiofiles==23.2.1` | `backend/requirements.txt:12` | `grep -rn "aiofiles" backend/ --include=*.py` matches **only** inside `.venv/`. No repo source imports it. | **HIGH** |
| `playwright@^1.61.1` (npm) | `frontend/package.json` devDeps | Sole consumer is `frontend/scripts/bench_pageload.mjs`, which is uncalled and hardcodes a non-existent path (§6.3). Note the **Python** `playwright` used by `backend/scripts/ui_walkthrough.py` is a different package and is not in `requirements.txt`. | **MEDIUM** |
| `@testing-library/dom@^10.4.1` | `frontend/package.json` devDeps | Never imported directly; it is a peer of `@testing-library/react`, which is imported widely. Listing it explicitly is defensible. | **LOW** — likely intentional |

Everything else that reported zero imports is runtime-only and belongs in §7: `uvicorn`, `asyncpg`, `psycopg2-binary`, `pymssql`, `pymysql`, `oracledb`, `pyodbc`, `aiosqlite`, `duckdb-engine`, `numba`, `llvmlite`, `setuptools`, `tzdata`, `fakeredis`, `freezegun`, `python-multipart`, `bcrypt`, `vite`, `typescript`, `jsdom`, `@vitejs/plugin-react`, `@types/*`. (`python-jose` and `@testing-library/jest-dom` were initially flagged by the scan and are **false positives** — `from jose import jwt` at `core/security.py:3`, and a side-effect import at `frontend/src/test/setup.ts:1`.)

### 6.9 Unused imports inside files — HIGH

**Backend — `pyflakes` reports 49 `imported but unused`.** A representative sample, all verified by the tool:

- `backend/app/routers/admin.py:12` — `..dependencies.get_current_user`
- `backend/app/routers/auth.py:5` — `sqlalchemy.orm.selectinload`
- `backend/app/routers/data_sources.py:2,3` — `csv`, `io`
- `backend/app/routers/metadata.py:29` — `..models.models.Relationship`
- `backend/app/routers/platform.py:13` — `datetime.timedelta`
- `backend/app/routers/reports.py:13` — `..models.models.DataAlert`
- `backend/app/routers/widget_data.py:18` — `..services.parameters.encode_literal`
- `backend/app/services/analytics.py:11,13,20` — `scipy.stats`, `pathlib.Path`, `.ingest.SUPPORTED`, `.ingest.load_file`
- `backend/app/services/connectors.py:27` — `dataclasses.field`
- `backend/app/services/dataset_cleanup.py:14` — `sqlalchemy.select`
- `backend/app/services/direct_query.py:41,43,45,49,50,54` — `hashlib`, `threading`, `collections.OrderedDict`, `sqlalchemy.create_engine`, `sqlalchemy.engine.Engine`, `.connections._build_url`

**Exception:** the six names pyflakes flags at `backend/app/services/direct_query.py:551` (`_ENGINE_REGISTRY`, `_ENGINE_REGISTRY_LOCK`, `_engine_key`, `dispose_engine`, `get_metadata_engine`, and `get_engine`) are **deliberate re-exports** — see §7.

**Frontend — `tsc --noUnusedLocals --noUnusedParameters` reports 16.** The non-test ones:

- `frontend/src/pages/ReportBuilder.tsx:9` — type `PageType` declared but never used (TS6196)
- `frontend/src/pages/ReportBuilder.tsx:46` — `AccessShield` imported but never used
- `frontend/src/pages/ReportBuilder.tsx:381` — local `savedFailed`
- `frontend/src/pages/DatasetDetail.tsx:138` — local `prepSteps`
- `frontend/src/components/report/MeasuresPanel.tsx:89` — local `loadFailed`
- `frontend/src/components/report/WidgetRenderer.tsx:204` — parameter `interactions`
- `frontend/src/components/QueryCanvas.tsx:29` — parameter `onCycleJoin`
- `frontend/src/components/report/chartRenderers/DecompositionRenderer.tsx:23` — parameter `cfg`
- `frontend/src/components/review/SourceOverview.tsx:203` — local `empty`

`loadFailed` and `savedFailed` are declared error-state variables that are never rendered — a silent-failure smell, not just lint noise.

### 6.10 Config and environment — MEDIUM

**Read but undocumented.** Eleven keys are read with `os.getenv` / `os.environ` and appear in **neither** `.env.example` nor `core/config.py`:

`ALEMBIC_DATABASE_URL`, `BENCH_EMAIL`, `BENCH_PASSWORD`, `DATALYTICS_FAKE_SECRET`, `DATALYTICS_TEST_DUCKDB_PUSHDOWN`, `DATALYTICS_TOKEN`, `DATALYTICS_URL`, `EMBEDDING_MODEL_NAME`, `MODEL_DIR`, `ONNX_FILENAME`, `ORT_INTRA_OP_THREADS`.

Most belong to bench scripts, tests or the embeddings image, so they are not dead — they are **undocumented**. Conf. **MEDIUM** that `.env.example` should grow, **HIGH** that they are absent from it.

**Defined but never read:** none. Every field in `core/config.py` is consumed. The one that appeared dead, `connector_allow_private_hosts` (`config.py:62`), is read via `getattr(settings, "connector_allow_private_hosts", True)` at `services/net_guard.py:61` — a false positive of attribute-access scanning.

### 6.11 Assets never referenced — HIGH

| Path | Size | Evidence | Conf. |
|---|---|---|---|
| `frontend/icon.jpg` | 562 KB | `grep -rl --fixed-strings "icon.jpg"` over every tracked file → **0 hits**. Not in `index.html`, `manifest.webmanifest`, `sw.js`, `nginx.conf` or any source file, and `git grep -l "icon.jpg" HEAD -- frontend/dist` is also empty, so no past build bundled it. | **HIGH** |
| `frontend/datalyticsicon.jfif` | 477 KB | 0 code references (one hit, inside a `.superpowers/` review diff). | **HIGH** |
| `12.jfif` (root) | 681 KB | 0 code references; mentioned only in `first-stop.md` prose. | **HIGH** |
| `x2.png` (root) | 104 KB | 0 code references. Its 13 apparent "hits" are token collisions with the variable `x2`. | **HIGH** |
| `1.png` (root) | 58 KB | 0 code references; `first-stop.md` prose only. | **HIGH** |
| `MCAIT Design System/scraps/{collapse_zoom,corner_zoom}.png`, `MCAIT Design System/uploads/*.png` (3) | — | 0 references; `scraps/` and `uploads/` are vendored working directories of the design system. | **HIGH** |
| `frontend/src/assets/fonts/{syne,manrope,jetbrains-mono}-variable-latin.woff2` + their 3 `OFL-*.txt` | 89 KB | Declared in `frontend/src/styles/mcait/fonts.css`, but **no longer in any `font-family` stack**: `--sans` and `--display` now resolve to `--dl-font` (Inter / IBM Plex Sans Arabic) and `var(--font-mono)` has exactly one consumer, `--mono` at `index.css:60`, which itself has **0** consumers in `src/`. These three faces are downloaded by the browser and never rendered. *(This became true at commit `8406c7fd`, yesterday.)* | **MEDIUM** — confirm after the restyle finishes |
| `backend/uploads/**` — 38 tracked files, 1.9 MB | — | 18 `.csv` + 18 `.parquet` + `demo_2_directquery.db` + `moodle_egypt_university.db`. Only 3 are named in code (`Regions.csv`, `demo_1_sales.csv[.parquet]`, by tests). The rest are **runtime upload state committed to git**, including `org_1/<uuid>.csv` files. | **MEDIUM** as dead weight; see §8 |

### 6.12 DB tables, models and migrations — HIGH where marked

- **`charts`** — created by `postgres/init.sql`, no SQLAlchemy model, no query, no migration. **HIGH**.
- **Every one of the 77 model class names appears in at least one file outside `models/`.** That is the weaker proxy I actually measured — a bare `ClassName` match across `backend/app/**` excluding `models/`, plus the script and test corpus. It counts a type annotation or a `relationship("X")` string as a hit, so it proves *mentioned*, **not** *queried*. Proving "never queried" needs a per-model search for `select(X)` / `db.query(X)` / `db.get(X, ...)`, which I did not run — see §8.2. The weakest table is `glossary_terms`: model (`models.py:1534`) and migration exist, and its three endpoints have no caller at all (§6.7).
- **All 29 Alembic revisions are reachable.** Walked the `down_revision` chain: exactly one head (`0029_aggregate_datasets`), a single unbranched chain of 29 back to `down_revision = None`, **zero orphans, zero branch points**. (`backend/alembic/versions/` holds 29 files; `env.py`, `script.py.mako` and `README.md` sit one level up and are not revisions.)

### 6.13 Commented-out code and unreachable blocks — none found

Scanned every `.py/.ts/.tsx/.js/.jsx` for runs of ≥5 consecutive comment lines whose content parses as code (`# if `, `# def `, `// const `, `// return `, …). **Zero blocks.** The codebase's comments are prose, not disabled code.

### 6.14 Stale documentation — HIGH

`README.md:46` and `README2.md:46` both claim "**12 widget types** on a 12-column grid canvas". The real count is **67**, verified twice in `frontend/src/types/report.ts`: 67 `type:` entries in `WIDGET_CATALOG` and 67 entries in `ROLE_SPECS`. Both READMEs are 5–6× out of date on the product's headline number. `first-stop.md:24-30` already records them as stale.

---

## 7. KEEP-BUT-LOOKS-DEAD

Everything below scores as unreferenced by static analysis and **must not be deleted**.

**Framework registration by decorator.** 214 of the 2,287 zero-consumer symbols live in `backend/app/routers/` — they are FastAPI path operations, called by the framework through `@router.get/post/...`, never by name. Same for `backend/app/main.py:health_live`, `health_ready` and `unhandled_errors_keep_cors_headers` (`@app.get` / `@app.exception_handler`), and `embedding_server/server.py:create_embeddings`.

**Test-runner globs.** 280 of the 326 zero-reference files are tests: 356 backend modules collected by `backend/pytest.ini` (`testpaths = tests`, `python_files = test_*.py`) and 169 frontend files collected by vitest. `backend/conftest.py:pytest_collection_modifyitems` is a pytest hook, invoked by name-matching. `backend/conftest.py` also enforces a **floor on how many tests must be collected** — deleting test files will fail it.

**Alembic revision chain.** All 30 files in `backend/alembic/versions/` are discovered by directory scan and linked by `down_revision` strings, never imported. `0001_baseline.py` (1,026 LOC) looks like the biggest dead file in the repo and is the foundation of the schema.

**Source files pinned as *text* by tests.** This repo reads its own source as strings. Deleting or renaming any of these breaks a suite even though nothing imports them:
- `frontend/src/index.css` — `svgDirection.test.ts` reads the file and regexes `.recharts-surface { … direction: ltr }`.
- every file under `frontend/src/` and `frontend/index.html` — `offlineAssets.test.ts` walks the tree and fails on any CDN string.
- `frontend/src/App.tsx` + `navigation.ts` — `navigationGuards.test.ts` parses `App.tsx` as text to pin each rail entry's permission to its route guard.
- `frontend/src/types/report.ts` — a backend test regex-parses `ROLE_SPECS` and requires exactly 67 entries.
- `ARCHITECTURE.md` / `.html` — a backend test re-derives file and test counts from the tree and fails if the prose drifts.
The FILE MAP marks these `TEXT-ONLY:`.

**String-dispatch tables.** `shape_sankey` (`services/widget_data.py:2204`) has no direct call; it is an entry in the `SHAPERS` dict at `:2482`, selected by `widget_type` at runtime. Every shaper in that table looks uncalled.

**SQLAlchemy `relationship("Model")` strings.** Model classes are wired by *name in a string*; a symbol grep that ignores string literals will mark them orphaned.

**Deliberate compatibility re-exports.** `backend/app/services/direct_query.py:551-558` re-imports six names from `.engines` with an explicit comment: *"Re-exported here because `agent/executor.py`, `metadata/*` and `demo_content.py` import these names from this module."* pyflakes flags all six; removing them breaks three modules.

**Side-effect imports.** `frontend/src/test/setup.ts:1` — `import '@testing-library/jest-dom'` has no binding, so an import-name scan misses it. Same class: `frontend/src/main.tsx` importing `./index.css`.

**CSS attribute-selector coupling.** `frontend/index.html` carries `data-product="datalytics"`, matched only by CSS attribute selectors in `frontend/src/styles/datalytics.css`. No JavaScript symbol search will connect them; removing the attribute silently disables the entire product theme.

**Runtime-only packages.** `uvicorn` (invoked from `backend/Dockerfile:11` and `docker-compose.yml:36-40`), `alembic`, `asyncpg`/`psycopg2-binary`/`pymssql`/`pymysql`/`oracledb`/`pyodbc`/`aiosqlite`/`duckdb-engine` (DBAPI drivers resolved from a connection URL string), `python-multipart` (FastAPI needs it for the `UploadFile`/`File(...)` parameters at `routers/datasets.py:226,366`), `bcrypt` (a passlib *backend*, named as the string `"bcrypt"` at `core/security.py:6`), `numba`/`llvmlite` (statsforecast's compiler), `tzdata` (zoneinfo data on slim images), `setuptools`, `fakeredis`/`freezegun` (test doubles), and the frontend's `vite`/`typescript`/`jsdom`/`@vitejs/plugin-react`/`@types/*`.

**Compose-level environment keys.** `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` and `VITE_API_URL` appear in `.env.example` with no matching field in `core/config.py` — correctly so: the first three are consumed by the Postgres image and interpolated into `DATABASE_URL` at `docker-compose.yml:44`, and `VITE_API_URL` is a Vite build-time variable read by `frontend/src/services/api.ts`.

**Externally-called endpoints.** `POST /auth/sso/saml/acs` (`routers/sso.py:160`) has no in-repo caller by design — the identity provider POSTs to it. Likewise, `backend/mcp_server/` exposes routes to machine callers outside this repository, and API-key clients may call any endpoint the issuing user can.

**Operational files referenced only from config.** `frontend/nginx.conf` (named only by `frontend/Dockerfile`), `frontend/public/sw.js` and `manifest.webmanifest` (named only by `frontend/index.html` and `pwa.test.ts`), `frontend/public/icon-{192,512,maskable-512}.png` (named only by `manifest.webmanifest`), and the `.ps1` operations scripts (`scripts/backup.ps1`, `restore.ps1`, `build_offline_bundle.ps1`, `demo_up.ps1`, `demo_down.ps1`, `backend/run_eval_gate.ps1`) which are invoked by an operator, not by code.

---

## 8. RISK NOTES

### 8.1 Not dead weight, but the most important thing found

**`.env` is tracked in git and contains live secrets.** `git ls-files --error-unmatch .env` succeeds. It holds non-empty `SECRET_KEY` and `POSTGRES_PASSWORD` values. `.gitignore:12-14` lists `.env` and `*.env` — but git ignores rules for files already tracked, and this one was added on **2026-06-30** (`8d8d86df`), before the rule. `backend/app/services/secrets.py:70` derives the Fernet key for stored connection secrets from it — `hashlib.sha256(("datasource-config-v1:" + settings.secret_key).encode())` — whenever `connector_secret_key` is unset (`:64`). This key therefore protects every stored database credential in the `data_sources` table.

Confirm and see the exposure window:
```
git log --all --format="%h %ad %an" --date=short -- .env
git log --all -p -- .env | head -40          # what has been committed over time
```
Untracking it (`git rm --cached .env`) removes it from future commits but **not from history** — rotating `SECRET_KEY` and `POSTGRES_PASSWORD` is the real remedy, and rotating `secret_key` makes existing encrypted connection secrets undecryptable.

### 8.2 What I could not verify statically

| Claim | Why it is unverifiable from source | Command to confirm |
|---|---|---|
| The §6.1 root duplicates are safe to delete | Nothing imports them, but a human workflow or an external tool might read them | `git rm -n init.sql README2.md CrossFilterContext.tsx ReportBuilder.tsx WidgetConfigPanel.tsx WidgetRenderer.tsx analytics.py widget_data.py` then both suites |
| `docker-compose2.yml` is unused | Touched 2026-09-08; a person may run `docker compose -f docker-compose2.yml up` by hand | ask the team; `git log -p -- docker-compose2.yml` |
| The 5 statistics + 3 glossary endpoints have no caller **anywhere** | Only this repo's client was searched. An MCP client, an API-key script, or a customer integration outside the repo could call them | `grep -rn "glossary\|statistics/" backend/mcp_server/`; then check access logs / `query_runs` in a live DB |
| `aiofiles` is removable | Import scanning cannot see a transitive requirement of another package | `pip uninstall aiofiles && pytest -q` in a scratch venv |
| The three MCAIT fonts are unrendered | CSS cascade is not statically decidable; step 2 of the restyle may reintroduce them | open the app, DevTools → Network, filter `woff2`, confirm only `inter-*` and `ibm-plex-*` load |
| `SKIN_OPTIONS` / `NARROW_DESKTOP_QUERY` / `WidgetDataResponse` are dead | HIGH by whole-repo search, but a future feature may be mid-flight | `git log -S SKIN_OPTIONS --oneline` to see if it was recently added |
| A model/table is never **queried** (as opposed to never mentioned) | §6.12 measured name mentions, not query sites | `for M in $(grep -oP '^class \K\w+' backend/app/models/models.py); do printf "%s %s
" "$M" "$(grep -rc "select($M)\|query($M)\|get($M," backend/app | awk -F: '{s+=$2} END{print s}')"; done` |
| Any deletion is behaviour-preserving | Static analysis cannot prove runtime behaviour | `cd backend && ./.venv/Scripts/python.exe -m pytest -q` and `cd frontend && npm test` — both were **exit 0** at `8406c7fd` |

### 8.3 Method caveats that limit confidence

- **Basename collisions.** 17 of 933 distinct `.py/.ts/.tsx` basenames are ambiguous. The FILE MAP's reference column resolves imports by name, so those 17 rows can over-report. The seven root duplicates in §6.1 are among them and were re-verified by hand; the remaining ten were not individually checked. Find them with:
  `git ls-files | grep -E '\.(py|ts|tsx)$' | grep -v '^frontend/dist/' | xargs -n1 basename | sort | uniq -d`
- **The backend suite's output was swallowed.** The run finished **exit 0**, but the RTK wrapper buffered the summary line, so the pass/fail counts are not in this document. Re-run without it for the numbers:
  `cd backend && ./.venv/Scripts/python.exe -m pytest -q --tb=no 2>&1 | tail -3`
- **374 of 993 files have no header comment**, so their FILE MAP purpose reads `_(no header comment)_`. That is a documentation gap, not a scan failure.
- **`.worktrees/custom-calc-functions;C` and the sibling `../data_analytics;C/` were not audited.** Both are untracked and 0 bytes — almost certainly the debris of a malformed shell redirection (`> ...;C`), not real work. Confirm with `ls -la ".worktrees/custom-calc-functions;C"` before removing.
- **`frontend/dist/` was excluded** as build output, but it is **tracked in git** and currently shows as deleted in the working tree. Decide whether it belongs in the repository at all: `git ls-files frontend/dist | wc -l`.
- **Pyflakes and tsc were run at `8406c7fd`.** Re-run both after any edit:
  `./backend/.venv/Scripts/python.exe -m pyflakes backend/app backend/scripts scripts embedding_server`
  `cd frontend && npx tsc --noEmit --noUnusedLocals --noUnusedParameters`
- **Everything under `MCAIT Design System/` is a vendored third-party design system.** The app consumes only its CSS tokens. Its 27 files and 2,825 LOC are flagged as unreferenced throughout this audit; treat that as "unused by this app", not "safe to delete from the upstream package".
