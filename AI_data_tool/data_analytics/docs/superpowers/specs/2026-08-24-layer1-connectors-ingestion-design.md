# Layer 1 — Connectors & Ingestion

Implements the Layer 1 gaps identified in `AI_data_tool/ARCHITECTURE_COMPARISON.md`
against `AI_data_tool/ARCHITECTURE.md`. First of eight phased layer builds.

**Guiding constraint:** additive only. Everything that works today keeps working
byte-for-byte. No table is renamed, no service is rewritten, no dependency is removed.
Layer 1 adds the metadata plane that Layers 3 and 4 will consume.

---

## 1. Scope

### In scope — the twelve Layer 1 gaps

| # | Gap | Architecture ref |
|---|---|---|
| 1 | Two planes: metadata (cached, agent-facing) vs data (live, user-facing) | L1 core principle |
| 2 | Persisted `column_stats` via engine statistics, not full scans | Stage 2 |
| 3 | `top_k` enum extraction where `distinct_count < 100` | Stage 2, "highest-value statistic" |
| 4 | Sample cache in DuckDB, ~1000 rows/object, LRU + size budget | Stage 3 |
| 5 | PII masking before any sample leaves the process | Stage 3.3 |
| 6 | FK inference with confidence and evidence | Stage 4 |
| 7 | Semantic inference: regex classifiers, roles, deprecation, LLM pass | Stage 5 |
| 8 | Schema fingerprint + drift detection | Stage 6 |
| 9 | `confidence` + `source` provenance on every derived fact | Principle 5 |
| 10 | Human confirmation UI — join graph + column review | Stage 7 |
| 11 | `sync_runs` + `watermarks` | Stages 1, 8 |
| 12 | Envelope encryption for source credentials | Stage 0.3 |

### Explicitly out of scope

- **Arrow end-to-end** (Principle 6). Replacing pandas is a Layer 2 concern and a
  breaking change to `widget_data.py`. Deferred.
- **psycopg2 to psycopg3**, **openpyxl to python-calamine**, **ConnectorX**. Stack
  swaps, not missing logic. Deferred.
- **Composite foreign keys.** The existing `relationships` table is single-column on
  each side, and `prep.py`, `query_builder.py` and join resolution all assume that.
  Inference proposes single-column keys only. Composite support is a Layer 3 item.
- Layers 2 through 8.

---

## 2. Schema mapping

The architecture names tables this project already has. Extend, do not duplicate.

| ARCHITECTURE.md | This project | Action |
|---|---|---|
| `connections` | `data_sources` | extend |
| `objects` | `datasets` | extend |
| `columns` | `dataset_columns` | extend |
| `relationships` | `relationships` | extend |
| `column_stats` | — | new table |
| `schema_versions` | — | new table |
| `sync_runs` | — | new table |
| `watermarks` | — | new table |

### 2.1 New tables

Created by `Base.metadata.create_all` — no migration statement needed.

```
column_stats
  id                 int pk
  dataset_column_id  int fk -> dataset_columns(id) on delete cascade, unique, indexed
  null_ratio         float
  distinct_count     bigint
  top_k              json          -- [{"value": "...", "count": n, "ratio": 0.0}, ...]
  min_value          text
  max_value          text
  avg_width          int
  exact              bool not null default false   -- false = engine estimate
  computed_at        timestamptz

schema_versions
  id              int pk
  data_source_id  int fk -> data_sources(id) on delete cascade, indexed
  org_id          int fk -> organizations(id) on delete cascade, indexed
  fingerprint     varchar(64) not null           -- SHA-256 hex
  diff            json                           -- {added: [], removed: [], changed: []}
  detected_at     timestamptz

sync_runs
  id              int pk
  data_source_id  int fk -> data_sources(id) on delete cascade, indexed
  org_id          int fk -> organizations(id) on delete cascade, indexed
  trigger         varchar(20) not null           -- manual | scheduled | drift
  status          varchar(20) not null           -- running | ok | failed | cancelled
  stages          json                           -- per-stage {name, status, ms, detail}
  error           text
  started_at      timestamptz
  finished_at     timestamptz

watermarks
  id              int pk
  dataset_id      int fk -> datasets(id) on delete cascade, unique, indexed
  strategy        varchar(20) not null           -- full | incremental
  cursor_column   varchar(255)
  cursor_value    text
  updated_at      timestamptz
```

### 2.2 Columns added to existing tables

Appended to the `stmts` list in `app/main.py::_migrate`, following the existing
`ADD COLUMN IF NOT EXISTS` convention.

```sql
ALTER TABLE relationships    ADD COLUMN IF NOT EXISTS confidence DOUBLE PRECISION NOT NULL DEFAULT 1.0;
ALTER TABLE relationships    ADD COLUMN IF NOT EXISTS source VARCHAR(20) NOT NULL DEFAULT 'declared';
ALTER TABLE relationships    ADD COLUMN IF NOT EXISTS evidence JSON;
ALTER TABLE relationships    ADD COLUMN IF NOT EXISTS cardinality VARCHAR(20);
ALTER TABLE dataset_columns  ADD COLUMN IF NOT EXISTS semantic_type VARCHAR(40);
ALTER TABLE dataset_columns  ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE dataset_columns  ADD COLUMN IF NOT EXISTS description_source VARCHAR(20);
ALTER TABLE datasets         ADD COLUMN IF NOT EXISTS is_deprecated BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE datasets         ADD COLUMN IF NOT EXISTS description_source VARCHAR(20);
ALTER TABLE datasets         ADD COLUMN IF NOT EXISTS last_profiled_at TIMESTAMPTZ;
ALTER TABLE data_sources     ADD COLUMN IF NOT EXISTS allow_llm_sampling BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE data_sources     ADD COLUMN IF NOT EXISTS last_synced_at TIMESTAMPTZ;
ALTER TABLE data_sources     ADD COLUMN IF NOT EXISTS sync_status VARCHAR(20) NOT NULL DEFAULT 'pending';
```

`datasets.description` already exists and is reused; only its `_source` companion is new.

**Backwards compatibility:** existing `relationships` rows default to
`confidence=1.0, source='declared'`, which is correct — a user typed them in, so they
outrank anything inferred. No backfill script needed.

---

## 3. Provenance model

`source` takes exactly three values, in strict precedence order:

| Value | Meaning | Confidence | Resync behaviour |
|---|---|---|---|
| `confirmed` | A human approved it | always 1.0 | **never overwritten** |
| `declared` | Read from the source catalog (a real FK) | always 1.0 | refreshed from source |
| `inferred` | Derived by this layer | 0.0–1.0 | recomputed every sync |

This is Principle 5, and it is enforced in one place: `_upsert_inference()` in
`metadata/store.py` refuses to modify any row whose `source = 'confirmed'`. Every
inference stage writes through that function. A test asserts the refusal.

---

## 4. Modules

```
backend/app/services/metadata/
  __init__.py
  store.py           Provenance-aware upserts; the confirmed-wins rule lives here
  profile.py         Stage 2 - statistics, top_k
  sample.py          Stage 3 - sampling strategy selection
  cache.py           Stage 3 - DuckDB sample cache, LRU, size budget
  infer_keys.py      Stage 4 - FK inference
  infer_semantic.py  Stage 5 - semantic types, roles, deprecation, LLM descriptions
  drift.py           Stage 6 - fingerprint, diff, drift events
  sync.py            Orchestrates stages 1-6, writes sync_runs

backend/app/services/
  pii.py             Detection + masking
  envelope.py        Envelope encryption for source credentials
  llm.py             Offline vLLM/Qwen client
```

### 4.1 `llm.py` — the offline model client

Ported from `prompt.py`, without the Wren dependency.

```python
class LLMClient:
    async def complete(self, messages, *, max_tokens, temperature, timeout) -> str
    async def complete_json(self, messages, schema, *, retries=2) -> dict
```

- OpenAI-compatible `/v1/chat/completions`, configured by `LLM_BASE_URL` and
  `LLM_MODEL` env vars (defaults matching the current endpoint and `qwen3.5`).
- `chat_template_kwargs: {"enable_thinking": false}`, as `prompt.py` uses.
- `complete_json` validates against a JSON Schema and retries on mismatch. This is the
  honest version of D4.2 without XGrammar — the architecture wants token-level
  constraints; validate-and-retry is what a plain OpenAI-compatible endpoint allows, and
  Layer 4 can upgrade it.
- Token accounting recorded per call, for the Layer 8 quota work.
- **Never raises into a request path.** Every caller degrades to the deterministic
  result if the model is unreachable. Layer 1 must work with the GPU box switched off.

> **Note on Wren AI.** `prompt.py` executes SQL through the `wren` CLI. ARCHITECTURE.md
> lists WrenAI under "Avoided entirely" because it is AGPL. This layer takes the vLLM
> endpoint from `prompt.py` and nothing else; the semantic model that Wren's MDL provides
> is built natively in Layer 3.

### 4.2 `profile.py` — Stage 2

Branches on capability, per Principle 2 (read the engine's own statistics first):

| Source | Path |
|---|---|
| PostgreSQL family | `pg_stats`: `null_frac`, `n_distinct`, `most_common_vals`, `most_common_freqs`, `avg_width`. One query per table, no scan. `exact = false`. |
| Other SQL families | Single aggregate query: `count(*)`, `count(col)`, `count(distinct col)`, `min`, `max`. `exact = true`. |
| Import-mode datasets | Computed from the cached frame via `frame_cache.get_frame`. `exact = true`. |

Normalisation traps handled explicitly, per the doc:
- `n_distinct < 0` is a **fraction of rows**, not a count. Multiply by the row estimate.
- `most_common_vals` is a Postgres text-array literal, not JSON. Parsed, never `eval`ed.

`top_k` is always computed when `distinct_count < 100`. For Postgres it comes free from
`most_common_vals`; elsewhere it is a `GROUP BY ... ORDER BY count DESC LIMIT 100`.

### 4.3 `sample.py` + `cache.py` — Stage 3

Strategy selection:

| Condition | Strategy |
|---|---|
| Table, Postgres/SQL Server family | `TABLESAMPLE SYSTEM (n)` |
| View, or family without TABLESAMPLE | `ORDER BY <random fn> LIMIT 1000`, bounded by the governor |
| A dimension with `distinct_count <= 20` exists | Stratified — sample every value of it |
| Import-mode dataset | Reservoir sample from the cached frame |

Samples land in a DuckDB file at `settings.DUCKDB_CACHE_PATH` (default
`/app/uploads/metadata_cache.duckdb`, on the existing `uploaded_files` volume — no new
volume needed). One table per dataset, named `s_{dataset_id}`.

Budget: `METADATA_CACHE_MAX_MB`, default 512. LRU eviction driven by a `_cache_meta`
table tracking `(dataset_id, rows, bytes, last_used_at)`.

**PII masking runs between sampling and caching**, so no unmasked value is ever written
to the cache or reaches the model.

### 4.4 `pii.py` — Stage 3.3

Detectors: email, phone (E.164 and local), IBAN, credit card (Luhn-checked), national ID,
IP address, coordinates. Masking preserves shape and cardinality — the same input always
maps to the same token — because FK overlap testing in Stage 4 runs on masked values and
would break under random masking.

```
alice@corp.com -> a****@c***.com
```

Column-level: a column whose `semantic_type` is PII is masked wholesale. Detection runs
on the sample, not the full column.

### 4.5 `infer_keys.py` — Stage 4

Ordered, cheapest filter first:

1. **Seed** with declared FKs from the source catalog → `confidence=1.0, source='declared'`.
2. **Name candidates**: `customer_id` → `customers.id`; `<table>_id`; `fk_*`; shared
   prefixes; exact name match against a column that is a PK elsewhere.
3. **Type compatibility** filter — reject incompatible dtypes outright.
4. **Value overlap** on the DuckDB samples:
   `count(distinct child ∩ parent) / count(distinct child)`. A local DuckDB join, never
   a source query.
5. **Cardinality direction** — the side with the higher distinct ratio is the parent.
6. **Write** with evidence:
   `{overlap, name_score, sample_size, child_distinct, parent_distinct}`.

Thresholds, per the doc:

| Overlap | Outcome |
|---|---|
| >= 0.95 | `inferred`, high confidence, pre-checked in review |
| 0.70 – 0.95 | `inferred`, needs review |
| < 0.70 | discarded, not written |

### 4.6 `infer_semantic.py` — Stage 5

1. **Regex classifiers** → `semantic_type`: email, phone, url, ip, iban, national_id,
   coordinate, currency, percentage.
2. **Role heuristics** → measure / dimension / identifier / timestamp. Takes the existing
   `analytics.detect_types` output as its dtype input rather than re-detecting, and
   writes only where `column_meta` has no author override, so a human's choice always wins.
3. **Deprecation signals** → `datasets.is_deprecated`: name matches `_old`, `_bak`,
   `tmp_`, `_deprecated`; zero rows; or `last_profiled_at` far behind siblings.
4. **LLM description pass** — opt-in, gated on `data_sources.allow_llm_sampling`.
   Input per column: table name, column name, dtype, `top_k`, and a **masked** five-row
   sample. Output: a JSON object of one-sentence descriptions, validated by
   `complete_json`. Written as `description_source='inferred'`, never as fact. If the
   endpoint is unreachable the stage is skipped and the sync still succeeds.

### 4.7 `drift.py` — Stage 6

The fingerprint is SHA-256 over the sorted tuple list
`(schema, table, column, dtype, nullable)` for the whole data source, compared against
the newest `schema_versions` row.

On change: write a new `schema_versions` row with a structured diff, emit a
`notifications` row (reusing the existing notifications table), and **do not silently
resync**. Confirmed annotations attached to a removed column are flagged as orphaned in
the diff rather than deleted — the architecture is explicit about this.

### 4.8 `sync.py` — the pipeline

```
open sync_run(status=running)
  stage 1 discover   -> objects + columns upsert
  stage 2 profile    -> column_stats
  stage 3 sample     -> DuckDB cache (masked)
  stage 4 infer_keys -> relationships (inferred)
  stage 5 infer_sem  -> semantic_type, roles, descriptions
  stage 6 drift      -> schema_versions, notification
close sync_run(status=ok|failed, stages=[...])
```

Each stage is independently wrapped: a failed stage is recorded in `stages` and the
pipeline continues where the next stage does not depend on it. Stage 4 depends on stage 3
and is skipped if sampling failed.

Concurrency follows the existing `refresh_scheduler.py` convention: a Postgres advisory
lock per data source, so N uvicorn workers cannot run two syncs against one source.
Nightly scheduling reuses the existing scheduler loop rather than adding a second one.

---

## 5. API

All routes are org-scoped through the existing `org_scope` dependency, and admin-gated
where they touch a data source.

```
POST /api/v1/data-sources/{id}/sync                -> {sync_run_id}
GET  /api/v1/data-sources/{id}/sync/{run_id}       -> {status, stages, error}
GET  /api/v1/data-sources/{id}/sync/latest         -> most recent run
GET  /api/v1/data-sources/{id}/review              -> inferred items below threshold
POST /api/v1/data-sources/{id}/review/confirm      -> {relationship_ids, column_updates}
GET  /api/v1/datasets/{id}/columns/{name}/stats    -> column_stats incl. top_k
GET  /api/v1/data-sources/{id}/drift               -> schema_versions history
```

`GET /datasets/{id}/columns/{name}/stats` has immediate non-AI value: the frontend filter
UI can offer real enum dropdowns from `top_k` instead of free-text entry.

---

## 6. Frontend

New dependency: `reactflow` (MIT).

```
frontend/src/pages/SourceReview.tsx        Two-tab review page
frontend/src/components/review/
  JoinGraph.tsx        React Flow canvas - declared solid, inferred dashed,
                       edge label = confidence, click to confirm/reject
  ColumnReview.tsx     Per-column semantic_type, description, enum labels
  EvidencePopover.tsx  Why this was suggested: overlap, name score, sample size
  SyncProgress.tsx     Per-stage progress from sync_runs
```

Reached from the existing data-source admin screen. The target from the architecture is
**a correct model in under ten minutes**, so the graph opens with every `>= 0.95` edge
pre-selected behind one "Confirm all high-confidence" action.

---

## 7. Configuration

New settings in `core/config.py`, all with working defaults:

```
LLM_BASE_URL              http://10.125.18.189:8000/v1
LLM_MODEL                 qwen3.5
LLM_TIMEOUT_S             180
LLM_ENABLED               true
DUCKDB_CACHE_PATH         /app/uploads/metadata_cache.duckdb
METADATA_CACHE_MAX_MB     512
METADATA_SAMPLE_ROWS      1000
FK_OVERLAP_HIGH           0.95
FK_OVERLAP_REVIEW         0.70
ENVELOPE_MASTER_KEY       (falls back to SECRET_KEY)
```

---

## 8. Testing

TDD, matching the existing suite's conventions (`pytest-asyncio`, `conftest.py` fixtures,
SQLite for unit tests where the code is dialect-agnostic).

| File | Covers |
|---|---|
| `test_metadata_store.py` | **confirmed is never overwritten** — the provenance rule |
| `test_profile_pg_stats.py` | `n_distinct < 0` fraction handling; `most_common_vals` array parsing |
| `test_profile_generic.py` | Fallback aggregate path; `exact` flag correctness |
| `test_top_k.py` | Computed under 100 distinct, skipped above |
| `test_sample_strategies.py` | Strategy selection per family and object kind |
| `test_metadata_cache.py` | LRU eviction, size budget, cache hit and miss |
| `test_pii.py` | Each detector; **masking is deterministic** (same in, same out) |
| `test_infer_keys.py` | Each stage in isolation |
| `test_infer_keys_accuracy.py` | **Measured precision and recall** on a seeded 8-table schema |
| `test_infer_semantic.py` | Classifiers; author overrides beat inference |
| `test_drift.py` | Fingerprint stability, diff shape, orphaned-annotation flagging |
| `test_sync_pipeline.py` | Stage isolation — one stage failing does not abort the run |
| `test_llm_client.py` | JSON validation and retry; **unreachable endpoint degrades, never raises** |
| `test_envelope.py` | Round trip; ciphertext never equals plaintext |
| `test_metadata_api.py` | Org scoping and admin gating on every new route |

`test_infer_keys_accuracy.py` is the M1.4 checkpoint: it reports precision and recall and
fails below a floor. If the metadata model is not rich enough to infer keys well, this is
where that surfaces — while the schema is still cheap to change.

**Regression guarantee:** the full existing suite must stay green, and no existing test is
modified. This is an acceptance criterion, not an aspiration.

---

## 9. Acceptance criteria

Layer 1 is done when:

1. All ~190 existing backend tests pass unchanged.
2. All new tests pass, and `test_infer_keys_accuracy.py` reports precision and recall.
3. `docker compose up` against an existing database migrates cleanly — no data loss, no
   manual step.
4. A sync run against a live Postgres source completes all six stages and produces
   `column_stats` with `top_k`, cached samples, and inferred relationships with evidence.
5. The review UI confirms an inferred FK, and a later resync does not overwrite it.
6. With `LLM_ENABLED=false`, or the endpoint down, every stage except 5.4 still completes.

---

## 10. Sequencing

| Step | Deliverable | Architecture milestone |
|---|---|---|
| 1 | Models, migrations, `store.py` provenance rule + tests | — |
| 2 | `llm.py` + `envelope.py` + `pii.py` + tests | M1.1 |
| 3 | `profile.py` + `top_k` + stats API + tests | M1.2 |
| 4 | `sample.py` + `cache.py` (DuckDB) + tests | M1.2 |
| 5 | `infer_keys.py` + accuracy test | M1.4 |
| 6 | `infer_semantic.py` + `drift.py` + tests | — |
| 7 | `sync.py` pipeline + API + tests | M1.5 |
| 8 | Review UI (React Flow) | M1.6 |

Guard and provenance before inference, inference before job plumbing — the order
ARCHITECTURE.md recommends, for the reason it gives.
