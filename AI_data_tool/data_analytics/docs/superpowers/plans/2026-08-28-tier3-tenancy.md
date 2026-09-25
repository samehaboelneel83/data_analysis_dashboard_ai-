# Tier 3 Tenancy & Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** Close the three Tier-3 gaps: embeds with host-signed JWTs (D7.1 — "never trust the browser with scope"), per-tenant quotas, OpenTelemetry.

**Spec:** ARCHITECTURE.md D7.1/D8.4 + the gap doc's Layer 7 #1 and Layer 8 #2/#5 rows are the requirements; this plan is self-contained where they are terse.

## Global Constraints

- models.py / main.py / config.py are BOM utf-8-sig — preserve.
- New schema: alembic revision chained on current head (**id ≤ 32 chars** — pin test), plus `_migrate`/create_all belt-and-braces. Chain serially across tasks: E1's revision first, E2 chains on it.
- Defaults preserve behavior: quotas null = unlimited; OTel disabled by default; embeds are net-new surface.
- Secrets encrypted with the existing enc:v2 machinery (grep `encrypt_value`/`_secrets` in core) — never plaintext at rest, never returned by the API after creation.
- Docker pytest from PowerShell ONLY: `docker run --rm -v "d:\Omda 2025\projects\data_analysis_dashboard_ai\AI_data_tool\data_analytics:/repo" -w /repo/backend datalytics-backend:test python -m pytest <paths> -q --no-header -p no:warnings` (rebuild image if requirements change: `docker build -t datalytics-backend:test backend` — tell the controller if you can't).
- TDD; commits end `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.
- JWTs via the existing `python-jose` (requirements already pin it) — no PyJWT.
- 404-never-403 for cross-org objects; guest/embed endpoints rate-limited via the existing `rate_limit.py` bucket patterns.

### Task E1: Embedded reports with host-signed JWTs

**Files:** models.py (+`EmbedConfig`: id, org_id, report_id FK, name, secret_encrypted Text, allowed_origins JSON list, enabled bool default true, created_at, last_used_at nullable; unique (report_id, name)); alembic revision; router `backend/app/routers/embed.py` (mount in main.py); admin endpoints on the reports router or embed router: create (returns the secret ONCE, stores encrypted), list (no secret), revoke/enable, delete — gated like report-sharing management; frontend: `frontend/src/pages/EmbeddedReport.tsx` (minimal chrome like SharedReport) + an "Embed" section in the report share dialog (create config, show iframe snippet + sample server-side token-generation code in Python and Node); tests backend `test_embed.py` + frontend vitest.

**Token contract (server-side host app generates):** HS256 JWT signed with the config's secret. Claims: `cfg` (embed config id), `exp` (required, max 24h ahead — reject longer), optional `filters` (list of {column, op, value} injected server-side into every widget query for the report — reuse the object-filter shape the widget pipeline already accepts; grep how config filters flow), optional `viewer_email` / `viewer_org` (fed to `apply_user_context` so USEREMAIL()/ORGID() expand to the HOST's declared viewer — document that trust lives in the host's signature).
**Endpoint flow:** `GET /api/v1/embed/report?token=<jwt>`: decode UNVERIFIED header→cfg id→load config (enabled, else 404)→verify signature with decrypted secret (jose, require exp)→origin check: if `Origin`/`Referer` present it must match allowed_origins (empty list = no origin restriction, document the tradeoff); response carries the report structure + a short-lived (15 min) internal embed session token used by the widget-data calls; widget-data on the embed path applies RLS (creator base + JWT viewer identity) and ALWAYS merges the JWT's `filters` server-side — query params from the browser are never read for scope. Set `Content-Security-Policy: frame-ancestors <allowed_origins>` on the embed HTML response path if there is one (the SPA route serves it; at minimum document where the header belongs and set it on the API responses).
**Tests:** valid token renders (structure + widget data); tampered signature 401; expired 401; exp >24h rejected at decode; revoked/disabled 404; wrong-org config 404; filters injected (value-pinned: two different `filters` claims → different rows on same widget); viewer_email expands USEREMAIL(); origin mismatch 403; browser-supplied filter params ignored (value-pinned); secret never in list responses; rate-limit bucket applied.

### Task E2: Per-tenant quotas

**Files:** models.py (+`Quota`: org_id unique FK, max_queries_per_day, max_agent_asks_per_day, max_storage_mb, max_concurrent_asks — all Integer nullable=unlimited); alembic revision chained on E1's; `backend/app/services/quotas.py` (check functions, cheap: count `query_runs` by org_id+created_at≥midnight UTC for queries; agent asks counted from agent_runs same way; storage = sum of Dataset.file_size for the org (grep the field) checked at upload/import; concurrent asks via an in-process per-org counter with context-manager acquire/release); enforcement at: widget-data/query execution entry (429 + Retry-After midnight), agent ask endpoint (429), upload/import (413 with a clear message); admin: platform-admin-only CRUD endpoints + a column on the existing admin org page (grep the admin orgs UI) showing usage vs quota.
**Tests:** null quota = unlimited (no behavior change — regression assert on existing tests passing untouched); over-limit 429/413 value-pinned at the boundary (n-1 ok, n blocked); per-org isolation (org A exhausted, org B unaffected); concurrent counter releases on exception; storage counts current datasets not deleted ones.

### Task E3: OpenTelemetry (opt-in)

**Files:** requirements (+`opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-instrumentation-fastapi`, `opentelemetry-instrumentation-sqlalchemy`, `opentelemetry-exporter-otlp-proto-http` — pinned compatible versions); config.py (+`otel_enabled` bool default False, `otel_endpoint` str None, `otel_service_name` default "datalytics-backend"); `backend/app/core/telemetry.py`: `setup_telemetry(app)` called from main.py startup — no-op when disabled; when enabled instruments FastAPI + SQLAlchemy and exports OTLP/HTTP to `otel_endpoint` (console exporter when endpoint None); manual spans: agent graph nodes (one span per node in `agent/graph.py` — wrap the node dispatch loop, attach run_id/node/status attributes, NO question text or SQL in attributes — hash only, same discipline as query_runs), DirectQuery execution, dataset refresh. Failure isolation: any otel import/setup error logs and continues (never brick startup — wrap like `_run_secrets_migration`).
**Tests:** disabled = zero instrumentation (no otel imports executed at startup — assert lazily-imported); enabled with console exporter emits spans for a request and an agent node (capture via in-memory span exporter from the SDK); attributes carry hashes not SQL/question text; setup failure doesn't brick startup (monkeypatch to raise).

**Batching:** B1: E1 · B2: E2 · B3: E3 · final review + merge. Rebuild `datalytics-backend:test` after E3's requirements change.
