# Tier 4 — Offline Readiness & Scale-Out Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** Make the platform deployable in an ISOLATED NETWORK (no internet) — the user's stated deployment target — and close the two Tier-4 scale gaps: a shared cache tier (Valkey, self-hosted) and a materialization store.

**Deployment constraint (binding for every task):** production has NO internet. All dependencies resolve at IMAGE BUILD time (which happens outside the isolated network); at runtime nothing may fetch from the public internet — no CDN assets, no font CDNs, no package installs, no telemetry to public endpoints. Anything optional that points at a URL must default to internal/none.

## Global Constraints

- models.py / main.py / config.py BOM utf-8-sig — preserve.
- New schema: alembic revision chained on 0007_quotas (id ≤ 32 chars) + `_migrate`/create_all parity.
- New services/deps must be optional with in-process fallback: `valkey_url=None` (default) keeps today's behavior byte-for-byte — the platform must run without Valkey.
- Docker pytest from PowerShell ONLY: `docker run --rm -v "d:\Omda 2025\projects\data_analysis_dashboard_ai\AI_data_tool\data_analytics:/repo" -w /repo/backend datalytics-backend:test python -m pytest <paths> -q --no-header -p no:warnings`. Rebuild the test image when requirements change.
- TDD; commits end `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.

### Task O1: Offline readiness — self-hosted fonts + deployment bundle

**Files:** `frontend/src/styles/mcait/fonts.css` (replace the Google Fonts `@import` — the ONLY runtime internet dependency found by audit), `frontend/src/assets/fonts/` (vendored woff2 files), `scripts/build_offline_bundle.ps1` (new), `docs/OFFLINE_DEPLOYMENT.md` (new).

- Download the woff2 files for the exact faces/weights in the current @import (Syne 500-800, Manrope 400-800, JetBrains Mono 400-600 — latin + whatever subsets the app's Arabic UI needs: CHECK — these three faces have no Arabic glyphs; find what the app actually renders Arabic with today (system fallback). Vendor woff2s into `frontend/src/assets/fonts/`, write local `@font-face` rules with `font-display: swap` and the same family names so nothing else changes. Keep the fallback stacks. Verify the built bundle (`npx vite build`) contains the fonts and NO `fonts.googleapis` string anywhere in `dist/`.
- `scripts/build_offline_bundle.ps1`: builds backend + frontend images, pulls postgres:16-alpine and valkey (once O2 lands — write it to read the compose file's image list dynamically), `docker save`s them into `offline_bundle/*.tar` with a manifest (image names, digests, git commit), and prints the transfer/load instructions. `docs/OFFLINE_DEPLOYMENT.md`: the full story — build outside, transfer, `docker load`, compose up, first-boot expectations (alembic adoption), what stays disabled offline (Backend-B embeddings unless an internal endpoint exists; OTel to an internal collector only), LLM endpoint is internal by design.
- **Tests:** a repo test (backend or frontend) asserting no `fonts.googleapis`/`cdn.`/`unpkg`/`jsdelivr` strings in frontend/src or index.html (regression pin); frontend suite green after the font swap; built dist spot-check documented in the report (script output pasted, not asserted in CI).

### Task O2: Valkey shared result cache (optional backend)

**Files:** `docker-compose.yml` (+`valkey` service, `valkey/valkey:8-alpine`, no ports exposed beyond the compose network, healthcheck), `backend/requirements.txt` (+`redis` client pinned, +`fakeredis` pinned for tests), config.py (+`valkey_url` default None), new `backend/app/services/cache_backend.py`, wire into the widget-result caches in `services/direct_query.py` and `services/widget_data.py` (grep the OrderedDict LRU caches).

- `cache_backend.py`: a small interface — `get(key) -> bytes|None`, `set(key, value: bytes, ttl_s)`, `delete_prefix(prefix)` — with two impls: `InProcessCache` wrapping the existing OrderedDict semantics (used when `valkey_url` is None — behavior byte-identical, existing tests untouched) and `ValkeyCache` (redis client, JSON/bytes values, per-key TTL, connection failure → log once + fall back to in-process for the life of a cooldown, same circuit pattern as retrieval Backend B). The existing cache KEYS (already include org, config hash, RLS expr, cache_epoch) become the Valkey keys with a `wdc:` prefix — verify nothing sensitive beyond what's already in the key strings (RLS expr text is in keys today — hash the final key with sha256 before sending to Valkey so raw expressions never leave the process; do the same for the in-process impl only if free, else document the asymmetry).
- Frame memo (`frame_cache.py`) stays process-local — DataFrames don't serialize cheaply; document in the module docstring.
- Drift invalidation: `cache_epoch` is already inside the key → stale entries orphan naturally; TTLs bound Valkey memory (maxmemory + allkeys-lru in the compose service command).
- **Tests:** backend of both impls against the interface (fakeredis for ValkeyCache); fallback-on-connection-error with cooldown; keys sha256-hashed (no raw RLS text reaches the client — assert on fakeredis contents); `valkey_url=None` regression: existing direct_query/widget cache tests pass untouched; multi-"worker" simulation: two InProcess→shared fakeredis instances see each other's entries.

### Task O3: Materialization store

**Files:** models.py (+`Materialization`: id, dataset_id FK, path, kind full|incremental, row_count, columns JSON, watermark_value nullable, created_at; alembic revision chained on O2-era head if any else 0007) — check first whether `write_parquet_sidecar`/`_read_sidecar` (frame_cache.py) and `dataset_refresh.py` already give most of this; **build on them, don't duplicate**. `services/dataset_refresh.py`: every refresh (full or incremental) writes/updates the parquet materialization + one Materialization manifest row (superseding rows pruned, files unlinked). Frame loading (`frame_cache.py`/`analytics.py` load path — grep) prefers a fresh materialization parquet over re-parsing the CSV when present and newer. Lineage (`/datasets/lineage/graph` load block) gains `materialized: bool` + row_count from the manifest.
- **Tests:** refresh creates/updates manifest + parquet (value-pinned row_count); superseded rows/files pruned; loader prefers parquet and falls back to CSV when the parquet is missing/stale (mtime discipline); lineage shows the flag; org scoping unaffected.

**Batching:** B1: O1 · B2: O2 · B3: O3 · final review + live deploy (image rebuild + bundle script dry-run) + merge.
