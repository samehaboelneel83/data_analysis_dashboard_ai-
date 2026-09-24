# Architecture Conformance Plan

**Date:** 2026-08-28
**Scope:** Bring code and `ARCHITECTURE.md` into agreement, and make that agreement enforced rather than aspirational.
**Not in scope:** Competitive feature work (DAX-equivalents, Excel export, connector breadth). See the Power BI / SAS comparison for that; it is a product roadmap, not conformance.

---

## Premise, and an important caveat

`ARCHITECTURE.md` defines seven layers in data-flow order. A static import scan of
`backend/app/services/` found **12 upward imports** — modules importing from a layer
above their own, which the document says cannot happen.

**The caveat matters.** The seven-layer taxonomy was written in the same session as
this plan, *to describe the code as it already is*. So an upward import is ambiguous
evidence: it may mean the code is wrong, or it may mean the document put the module
in the wrong layer. Treating all 12 as refactors would manufacture work and churn
working code.

Every finding below therefore carries an explicit **verdict** before it becomes a
task. A reviewer can disagree per line.

| Verdict | Meaning | Count |
|---------|---------|-------|
| **Reclassify** | The doc is wrong; the code is fine. Fix the document. | 6 |
| **Defect** | A real coupling problem, independent of layer labels. | 4 |
| **Accept** | Correct as-is; document the intent. | 2 |

---

## Triage

### Finding 1 — `direct_query.py` is in the wrong layer

```
L1 direct_query -> L4 display_rules, query_log, sql_expr, widget_data
```

**Verdict: Reclassify (4 of the 12 violations).**

The document places `direct_query.py` in Layer 1 alongside connectors. Its own
docstring says otherwise:

> pushes aggregate-strategy widget queries (the `shape_series` config shape —
> dimension/measure/aggregation) down into SQL against a live data source

It takes a widget config, builds SQL, enforces grain-safety, and hands the result to
the same shaper import-mode datasets use. That is Layer 4's definition verbatim —
"translating widget intent into SQL that is correct, governed, and safe."

Layer 1 owns *reaching* a source and *describing its capability*. Layer 4 owns
*building and running the query*. `direct_query.py` does the latter.

**Fix:** Move it to Layer 4 in `ARCHITECTURE.md` and `ARCHITECTURE.html`. Layer 1
retains `connectors.py`, `connections.py`, `secrets.py`, `net_guard.py`. Zero code
changes; four violations dissolve.

---

### Finding 2 — `analytics.py` genuinely spans two layers

```
L4 widget_data   -> L5 analytics
L2 prep          -> L5 analytics
L3 frame_cache   -> L5 analytics
L2 dataset_refresh -> L5 analytics
```

**Verdict: Reclassify now (2), Defect deferred (2).**

`ARCHITECTURE.md` already lists `analytics.py` under *both* Layer 2 (type detection)
and Layer 5 (statistics). That dual listing is the tell. The module has two distinct
responsibilities:

| Function | Responsibility | True layer |
|----------|---------------|-----------|
| `load_file()` | Read CSV/XLSX/JSON/Parquet | 2 |
| `detect_types()` | Classify columns | 2 |
| `_safe()` | JSON-safe value coercion | shared utility |
| `analyze_numeric/categorical/datetime()` | Statistics | 5 |
| `run_full_analysis()` | Statistics orchestration | 5 |

Callers in Layers 2–4 import the *ingestion* half, not the statistics half. They are
not reaching upward; the module is two modules wearing one name.

**Fix (Phase 2):** Split into `services/ingest.py` (load, detect, `_safe`) at Layer 2
and leave statistics in `analytics.py` at Layer 5. Until then, document `analytics.py`
as a known dual-layer module so the conformance test can allowlist it honestly.

---

### Finding 3 — `direct_query` imports private symbols from `widget_data`

```python
from .widget_data import _safe, _widget_data_cache_get, _widget_data_cache_set, get_widget_data_from_df
```

**Verdict: Defect.** This survives reclassification — both modules land in Layer 4,
so it is no longer a *layer* violation, but importing three underscore-prefixed
symbols across a module boundary is a real coupling problem. `_safe` and the cache
accessors are private by naming convention and public by use.

The coupling is deliberate and load-bearing — the docstring explains the grain
invariant depends on sharing the exact same shaper, and the cache-key comment notes
it must match `widget_data._widget_data_cache_key` for role isolation. That is an
argument for making the contract *explicit*, not for leaving it implicit.

**Fix:** Extract the shared surface into `services/widget_shaping.py` — `safe()`,
`widget_cache_get/set()`, `widget_cache_key()` — imported by both. The cache-key
isolation guarantee gets a docstring and a test in one place instead of a comment
warning in two.

---

### Finding 4 — `quotas.py` raises `HTTPException`

```python
from fastapi import HTTPException      # services/quotas.py:25
raise HTTPException(429, "Daily query quota exceeded …")
```

**Verdict: Defect.** The only service module importing FastAPI. Layer 6 owns the HTTP
surface; a Layer 3/6 service deciding on status codes couples quota logic to the web
framework, and makes quotas unusable from the scheduler or a CLI without a fake
request context.

Five raise sites: two 429s (query, agent-ask), one 413 (storage), one 429
(concurrency).

**Fix:** Define `QuotaExceeded(resource, limit, kind)` in the service; translate to
HTTP in an exception handler in `main.py` or at the router boundary. Mechanical.

---

### Finding 5 — `refresh_scheduler` reaches into delivery

```
L2 refresh_scheduler -> L6 alerts, delivery
```

**Verdict: Reclassify.** A scheduler that refreshes datasets *and then* fires alerts
and deliveries is operational orchestration, not ingestion. It sits at Layer 6 and
composes downward, which is exactly what Layer 6 is for.

**Fix:** Move `refresh_scheduler.py` to Layer 6 in both documents. `dataset_refresh.py`
— which performs the refresh itself — stays at Layer 2.

---

### Finding 6 — `dataset_refresh -> frame_cache`

**Verdict: Accept.** Layer 2 invalidating Layer 3's cache after a refresh is correct.
Cache invalidation flows from whoever changed the data. The document should state
that caching is a downward-callable utility, not a layer that only Layer 4 may touch.

---

### Finding 7 — DirectQuery capability gaps

`plan_query` rejects crosstab, running totals, `countd`, `std`, `variance`, `range`,
and percentile aggregations on non-Postgres/Oracle engines with `DirectQueryUnsupported`.

**Verdict: Accept — not a conformance issue.** `ARCHITECTURE.md` documents this as
deliberate fail-closed behaviour, and the grain-safety analysis in the docstring shows
it is correct: re-aggregating an already-aggregated value is only a no-op for
`sum/avg/min/max/median/percentiles`. Returning a number would mean returning a wrong
number.

Extending push-down to more engines is **product work, not conformance**. Recorded in
the appendix so it is not lost, and deliberately excluded from the phases below.

---

### Clean results worth recording

Three checks found nothing, which is a finding:

- **No frontend module bypasses `api.ts`.** Every network call in
  `frontend/src/**` goes through the Axios client. Layer 7 → 6 is clean.
- **No router executes raw SQL.** Zero `text("…")` calls in `routers/`. Layer 6 does
  not reach past Layer 4.
- **No service imports FastAPI except `quotas.py`.** Framework leakage is a single
  module, not a pattern.

---

## Phases

### Phase 0 — Make the boundary enforceable

The highest-value item, and nearly free. Without it every fix below silently regresses.

| Task | Detail | Effort |
|------|--------|--------|
| 0.1 | Add `backend/tests/test_layer_conformance.py`: walk `app/services/` and `app/core/`, parse imports, assert none targets a higher layer | S |
| 0.2 | Encode the layer map as data (`LAYER: dict[str, int]`) in the test, with a comment pointing at `ARCHITECTURE.md` as the source of truth | S |
| 0.3 | Seed `KNOWN_VIOLATIONS` with the post-triage remainder as an explicit allowlist | S |
| 0.4 | Assert the allowlist only shrinks — a new violation fails; a removed one fails until deleted from the list (ratchet) | S |

**Acceptance:** `pytest tests/test_layer_conformance.py` passes on current `main`,
and fails if a new upward import is introduced.

**Note:** the ratchet in 0.4 is what makes this a boundary rather than a report. A
plain "no violations" test would have to be disabled today; an allowlist that can only
shrink lets the codebase converge without blocking work.

### Done 2026-08-28 — and the findings changed

`backend/tests/test_layer_conformance.py`, 7 tests, green. Ratchet verified in both
directions before being trusted: a simulated new upward edge is caught, and a
simulated *fixed* violation left in the allowlist is caught as stale.

**The original 12 findings were produced by a regex scan, and it was wrong.** The test
parses imports with `ast`, and the real picture differs:

| | Regex scan | AST scan |
|---|---|---|
| Violations found | 12 | **9** (after layer corrections) |
| Missed entirely | — | `metadata/sync`, `metadata/catalog_sync`, `metadata/infer_semantic` |
| False positives | `direct_query -> display_rules`, `query_log`, `sql_expr` | — |

The regex only matched single-line `from .x import y`; it missed multi-line and
`from . import x` forms, and counted docstring prose as imports. **Any conclusion in
the original triage that rested on the regex should be re-checked against the test's
output, which is now the source of truth.**

**Three more layer corrections, forced by evidence the regex never surfaced:**

| Module | Was | Now | Why |
|--------|-----|-----|-----|
| `services/pii` | L6 | **L2** | Masks personal data *during sampling*, before anything reaches the sample cache or the model. Ingestion, not API. |
| `services/prep` | L2 | **L4** | Calls `resolve_rls_expr`, `resolve_denied_columns`, `apply_rls_filter` — governed query work. |
| `services/direct_query` | L1→L4 (already corrected) | L4, **but dual-layer** | `metadata/*` imports `get_engine`/`get_metadata_engine` from it: connection acquisition, which is L1 work living in an L4 module. |

That last one mirrors the `analytics.py` finding exactly: **two modules are misfiled,
not two callers misbehaving.** `direct_query.py` should have its engine registry (an
LRU with its own settings) extracted to layer 1, the same way `analytics.py` should
have `ingest.py` extracted from it. Both are recorded in the allowlist with that
reasoning, and both dissolve in Phase 2.

**Implementation notes:**

- Imports are parsed with `ast`, never regex — this file's own history is the argument.
- Source is read as `utf-8-sig`: 12 modules carry a UTF-8 BOM, and `ast.parse` rejects
  U+FEFF even though Python's importer strips it silently. Reading as plain `utf-8`
  made the test fail on files that import perfectly well.
- `core/config` and `core/telemetry` are exempt as genuinely cross-cutting; treating
  them as layered would make nearly every module a violator.
- Three guard tests protect the map itself — every mapped module must exist, layers
  must be in range, and a minimum edge count must be found, so a resolver bug cannot
  make the suite vacuously green.
- Two invariant tests encode boundaries `ARCHITECTURE.md` states by name: no service
  imports FastAPI except `quotas`, and no router builds raw SQL with `text()`.

---

### Phase 1 — Reclassify (documentation only, zero code risk)

| Task | Detail | Effort |
|------|--------|--------|
| 1.1 | Move `direct_query.py` from Layer 1 → Layer 4 in `ARCHITECTURE.md` + `.html` | S |
| 1.2 | Move `refresh_scheduler.py` from Layer 2 → Layer 6 in both | S |
| 1.3 | Document caching as a downward-callable cross-cutting utility (Finding 6) | S |
| 1.4 | Mark `analytics.py` as a known dual-layer module pending the Phase 2 split | S |
| 1.5 | Update `KNOWN_VIOLATIONS` — 6 entries drop out | S |

**Acceptance:** conformance test green with a 6-entry-shorter allowlist; both documents
describe the same layer assignment as the test.

**Why documentation first:** these six were never code problems. Fixing the map before
moving the territory means Phase 2 refactors are chosen for engineering reasons, not to
satisfy a label I assigned last week.

### Done 2026-08-28

Four modules reassigned across `ARCHITECTURE.md`, `ARCHITECTURE.html`, and the
conformance test's `LAYER_MAP`, verified to agree in all three:

| Module | Was | Now |
|--------|-----|-----|
| `services/direct_query` | 1 | **4** |
| `services/prep` | 2 | **4** |
| `services/pii` | 6 | **2** |
| `services/refresh_scheduler` | 2 | **6** |

Prose changed with the labels, rather than only the tables:

- **Layer 1** loses its DirectQuery bullet and gains a "Known misfiling" note naming the
  engine registry (`get_engine`, `get_metadata_engine`) as the Layer 1 work still living
  inside a Layer 4 module — the reason two allowlist entries exist.
- **Layer 2** replaces the old "Preparation" section (which described `prep.py`, now
  Layer 4) with **PII masking** and **Refresh**. The PII text records *why* the mask
  carries a hash instead of being shape-preserving: foreign-key inference measures value
  overlap in the masked sample, and shape-only masking would collapse distinct values
  and invent relationships.
- **Layer 4** gains `prep.py` with its RLS justification, and a **Two execution paths**
  table contrasting import-mode with DirectQuery — aggregation strategy, source rows
  loaded, RLS enforcement point — plus the grain-safety rule that follows from both
  sharing one shaper. The unbounded source load is flagged there as the platform's main
  scale limit.
- **Request lifecycles** corrected: `frame_cache (3) or direct_query (4)`, previously
  `(3 / 1)`.

**Allowlist unchanged at 9.** Phase 1 was expected to drop six entries, but that
accounting came from the regex scan superseded in Phase 0. The reassignments here are
already reflected in the map the test enforces, so the allowlist now holds exactly the
nine real upward imports — seven of which dissolve in Phase 2 by extracting
`services/ingest.py` and the engine registry.

---

### Phase 2 — Real decoupling

| Task | Detail | Effort |
|------|--------|--------|
| 2.1 | Extract `services/widget_shaping.py` with `safe()`, `widget_cache_get/set()`, `widget_cache_key()`; update `widget_data.py` and `direct_query.py` to import from it | M |
| 2.2 | Move the role-isolation cache-key guarantee into one docstring + one test in the new module | S |
| 2.3 | Replace `HTTPException` in `quotas.py` with `QuotaExceeded`; add a handler in `main.py` mapping it to 429/413 | S |
| 2.4 | Split `analytics.py` → `services/ingest.py` (L2: `load_file`, `detect_types`, `_safe`) + `analytics.py` (L5: `analyze_*`, `run_full_analysis`); update ~4 call sites | M |
| 2.5 | Clear the remaining `KNOWN_VIOLATIONS` entries | S |

**Acceptance:** allowlist empty; conformance test asserts zero violations
unconditionally; full backend suite green (2,451 tests).

**Risk note for 2.4:** `_safe` is imported by both `analytics.py` and `widget_data.py`.
Land 2.1 first so there is one home for it, then 2.4 moves the ingestion half without
having to duplicate the helper.

### 2.1 and 2.2 done 2026-08-28

`services/widget_shaping.py` now holds `safe()`, the cache key, both accessors, the
backend factory, and `clear_widget_data_cache` / `reset_cache_backend`.
`direct_query.py` imports from it instead of reaching into `widget_data`'s privates;
`widget_data.py` re-exports every moved name under its original spelling, because
`routers/datasets.py` alone calls `_safe` thirteen times.

**The cache moved as one unit, deliberately.** `widget_cache_get/set` branch on
`backend is _inprocess_backend` — an identity check. Splitting the functions from the
singletons (`_inprocess_backend`, `_valkey_backend`, the lock) across two modules would
leave that comparison testing objects from different modules: the in-process fast path
would stop firing and every read would start round-tripping through JSON, silently and
without failing a test. Identity was verified explicitly after the move:

```
cache dict identity : True     # wd._WIDGET_DATA_CACHE is ws.WIDGET_DATA_CACHE
backend wraps store : True
_safe identity      : True     # wd._safe is ws.safe is dq._safe
cache_get identity  : True
in-process fastpath : True
```

**One test needed re-pointing, and it caught a real break.**
`test_widget_data_cache_valkey_wiring.py` assigns `wd._valkey_backend = ValkeyCache(...)`
at four sites. A `from … import` binds a *value*, not a live binding, so those
assignments were landing in `widget_data`'s namespace while the singleton being read
lived in `widget_shaping` — the fake client was never installed and both tests failed
against a real DNS lookup. They now assign `ws._valkey_backend`. This is exactly the
failure mode the identity check above guards against, surfaced by the existing suite
rather than by inspection.

**Task 2.2 folded in.** The RLS-isolation guarantee is now a docstring on
`widget_cache_key` in one place, and it names
`tests/test_direct_query_cache.py` as the other half of the contract — DirectQuery
builds its own key (different inputs: no `file_stat`, a TTL bucket participates) but
must preserve the same property.

**`get_widget_data_from_df` deliberately stayed in `widget_data`.** It is public and it
is that module's core; `direct_query` importing it is a same-layer public-API call, not
the defect. The defect was the three underscore-prefixed names.

**Two `_safe` implementations still exist** — `analytics.py` has its own, and it is
*not* equivalent: it lacks the `pd.Timestamp` / `datetime` / `NaT` → ISO handling that
the O2 docstring calls load-bearing for cache-backend type consistency. Unifying them
is a 2.4 decision, made when `ingest.py` is split out; doing it here would have widened
a mechanical extraction into a behaviour change.

**Allowlist unchanged at 9** — `direct_query → widget_data` was never in it (both are
layer 4). This task removed private-symbol coupling, which the conformance test does
not measure; the win is that the contract is now explicit and tested in one place.

### 2.3 done 2026-08-28

`services/quotas.py` no longer imports FastAPI. Its four `HTTPException` raises became
`QuotaExceeded(detail, status_code=…, headers=…)`, translated by an exception handler in
`main.py`.

`status_code` and `headers` live on the exception rather than in the handler: the domain
knows *which* limit was hit and when it resets (`Retry-After` is computed from the org's
own midnight-UTC window), while the handler only knows how to write a response. The
handler is registered after `CORSMiddleware` for the same reason the generic one is —
a response produced outside it carries no `Access-Control-Allow-Origin`, and the browser
would report a CORS violation instead of the 429.

Wire behaviour is unchanged: the router-level tests asserting `429` + `Retry-After` and
`413` pass untouched. Two service-level tests that asserted
`isinstance(exc, HTTPException)` now assert `QuotaExceeded`.

**The conformance test tightened as a result.**
`test_no_service_imports_fastapi_except_quotas` became
`test_no_service_imports_fastapi`, asserting `not offenders` rather than
`offenders <= {"services/quotas"}`. **There are now no exemptions**, so the next service
that imports FastAPI fails the build rather than quietly joining an allowlist.

### 2.4 done 2026-08-28 — allowlist 9 → 5

`services/ingest.py` (layer 2) now holds `SUPPORTED`, `load_file` and `detect_types`.
`analytics.py` keeps the statistics surface and re-exports the three moved names, since
eighteen call sites imported them from there.

**The split unwound a real cycle, which was the point.** `frame_cache.py` needed
`SUPPORTED` but could not import it at module scope — `analytics.load_file` calls
`frame_cache.get_frame` — so it carried two function-local imports with the comment
*"local import; analytics imports us"*. With ingestion separated, `frame_cache` imports
`ingest` normally at the top of the file. What remains is one-directional:
`ingest.load_file` reads through the frame memo, allowlisted as accepted-by-design
alongside the other layer-2-reads-layer-3-cache entries.

**Callers repointed** — `widget_data`, `prep`, `dataset_refresh` and `metadata/sync`
now import from `.ingest` rather than through the re-export. That is what actually
shrinks the allowlist: the re-export keeps old code working, but a caller importing
`analytics` still records an L2→L5 edge.

**The ratchet did its job twice.** Adding `ingest` to the layer map surfaced a new
`ingest → frame_cache` edge *and* flagged `frame_cache → analytics` as stale in the same
run; repointing the four callers then flagged all four `→ analytics` entries as stale.
Each time the test named exactly what to delete, so the allowlist shrank by evidence
rather than by my recollection.

| | Before | After |
|---|--------|-------|
| Allowlisted violations | 9 | **5** |
| `→ analytics` entries | 5 | **0** |

The five survivors: three layer-2-reads-layer-3-cache (accepted by design) and two
`metadata/* → direct_query`, which dissolve when the engine registry is extracted to
layer 1 — the remaining known misfiling.

**`_safe` deliberately not unified.** `analytics.py` keeps its own, and it is *not*
equivalent to `widget_shaping.safe`: it lacks the `pd.Timestamp` / `datetime` / `NaT`
→ ISO handling that the O2 docstring calls load-bearing for cache-backend type
consistency. Unifying them would change what `run_full_analysis` returns for datetime
columns — a behaviour change wearing a refactor's clothes. Left as a separate decision.

### 2.5 done 2026-08-28 — allowlist 5 → 3, every misfiling resolved

`services/engines.py` (layer 1) now owns the pooled SQLAlchemy engine registry:
`_ENGINE_REGISTRY` and its lock, `_engine_key`, `get_engine`, `get_metadata_engine`,
`dispose_engine`. `direct_query.py` re-exports them.

This was the second known misfiling, and the conformance test is what made its cost
visible: `metadata/sync.py` and `metadata/catalog_sync.py` (layer 2) were importing a
layer 4 module purely to open a connection. Opening a connection is acquisition — layer
1 — and the registry's only dependencies were `_build_url`, `connectors` and `settings`,
all layer 1 or below, so it extracted cleanly.

Consumers repointed at `.engines`: `metadata/sync`, `metadata/catalog_sync`,
`agent/executor`, `demo_content`.

**Two tests needed repointing, for the same reason as the Valkey test in 2.1.**
`test_engine_pool.py` patches `create_engine` and `test_connect_timeout.py` patches both
`create_engine` and `_build_url` — on the module where the call happens. That module is
now `engines`, so the patches were landing somewhere the code no longer runs. This is
the recurring hazard of extractions: a re-export keeps *callers* working, but a test
that patches a name has to follow the code. Registry identity was verified explicitly
(`dq._ENGINE_REGISTRY is en._ENGINE_REGISTRY`) so pooling behaviour is unchanged.

| | Start of Phase 2 | Now |
|---|---|---|
| Allowlisted violations | 9 | **3** |
| Known misfilings | 2 | **0** |

**All three survivors are the same accepted-by-design pattern** — layer 2 reading layer
3's frame cache (`dataset_refresh`, `ingest`, `metadata/sync`). Cache reads and
invalidation both flow from whoever touches the data, so these are correct as they
stand. There is no remaining entry that represents a module in the wrong place.

### The recurring hazard, and one test that was never isolated

Four tests across this phase patched a name on the module that *re-exports* it rather
than the one where the call happens: the Valkey backend in 2.1, `create_engine` and
`_build_url` in 2.5, then `get_engine` in `test_stage_sample.py` and
`test_declared_fk_seeding.py`. **A re-export keeps callers working; a test that patches
a name has to follow the code.** `monkeypatch.setattr(dq, "create_engine", …)` fails
silently — it patches something real, just not the thing being executed.

One of those was worse than a broken patch.
`test_stage_sample.py::test_builds_a_bounded_query_for_the_right_dialect` says in its
own docstring that it exercises the SQL path *"without a live database"*. With its
patch inert, it opened a **real psycopg2 connection to localhost:5432** and failed on
connection refused. On a developer machine with Postgres running it would have passed
while silently querying a live database — a test asserting isolation it did not have.

`test_declared_fk_seeding.py` had the same stale target but passed either way, because
it patches in a real SQLite engine; its patch was simply inert. Both are repointed at
`app.services.engines.get_engine`.

Worth carrying into any future extraction: **run the full suite between steps, not
after a batch of them.** A targeted run over the modules you touched will not catch a
test that reaches the network from somewhere else in the tree — this one was found only
by the full run.

---

## Sequencing and effort

```
Phase 0  ──▶  Phase 1  ──▶  Phase 2
enforce       reclassify     decouple
  S             S              M
```

Phase 0 must land first — it is the ratchet everything else reports against. Phase 1
is documentation-only and can land the same day. Phase 2 is the only phase that
changes behaviour-bearing code and is independently reviewable per task.

Total: 4 small tasks, then 5 small, then 3 small + 2 medium. No task requires a
migration, a schema change, or coordinated deploy.

---

## What this does not fix

Stated plainly so the plan is not mistaken for a roadmap:

- **DirectQuery breadth** — stats/percentile push-down beyond Postgres and Oracle
  (Finding 7). Product work.
- **The 2 test-environment issues** — `PYTHONUTF8` for `test_infer_keys_accuracy.py`,
  and the zero-collection false pass when `pytest_asyncio` is absent. Both are recorded
  in `ARCHITECTURE.md` under Testing. Worth fixing, unrelated to layering.
- **Competitive gaps** — expression language depth, Excel export, connector count.

---

## Appendix — adjacent capability work

Not conformance; recorded so Finding 7's analysis is not lost.

| Item | Note |
|------|------|
| DirectQuery on MySQL/SQL Server families | Requires per-dialect `WIDTH_BUCKET`/`CORR` equivalents or documented refusal |
| Crosstab push-down | `dimension2` unsupported; currently materialises |
| Running totals push-down | Window-function emission per dialect |
| ~~RLS push-down (DirectQuery Phase 2)~~ | **Correction (2026-08-28, same day):** this row was wrong. RLS push-down **is implemented** — `run_direct_query` takes `rls_filter_expr`, `_base_query_sql` wraps the predicate around the base query, and `routers/widget_data.py` passes `resolve_rls_expr(...)` on every call. 14 tests cover it, including fail-closed on untranslatable expressions and per-RLS cache-key isolation. There is **no admin-only gate**. The claim came from a stale module docstring (`direct_query.py` lines 7–9) that still describes a Phase 1 that has since shipped. Fixing that docstring is a task in the hardening plan. |

---

## Verification

Every phase ends with the same two commands:

```bash
# conformance
python -m pytest tests/test_layer_conformance.py -q

# no regression
python -m pytest -q            # expect 2451 passed, 1 skipped
```

Run backend tests with `PYTHONUTF8=1` on Windows, and from a virtualenv built from
`backend/requirements.txt` — a missing `pytest_asyncio` makes pytest collect zero tests
and exit 0.
