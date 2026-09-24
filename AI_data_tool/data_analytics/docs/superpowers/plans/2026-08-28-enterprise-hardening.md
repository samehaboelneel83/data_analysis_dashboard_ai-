# Enterprise Hardening Plan

**Date:** 2026-08-28
**Goal:** Make the existing feature set production-trustworthy at enterprise scale.
**Scope:** Hardening only — scale ceilings, operational readiness, and correctness of
the record. No new user-facing features.

**Companion plan:** `2026-08-28-architecture-conformance.md`. That plan creates the
seams this one builds on (specifically task 2.1, `widget_shaping.py`). Land Phase 0 of
conformance first; the rest interleaves.

---

## Correction carried into this plan

The conformance plan's appendix claimed DirectQuery RLS push-down was unimplemented and
called it "the highest-value item." **That was wrong**, and the appendix has been
corrected in place.

RLS push-down is implemented and well covered:

- `run_direct_query(…, rls_filter_expr=…)` is a live parameter
- `_base_query_sql()` wraps the predicate around the base query before widget filters
- `routers/widget_data.py` passes `resolve_rls_expr(db, current_user, dataset_id)` on
  every call
- **14 tests** cover it, including fail-closed behaviour on untranslatable expressions
  and per-RLS-filter cache-key isolation
- There is **no admin-only gate**

The false claim originated in a stale module docstring (`direct_query.py`, lines 7–9)
that still describes "Phase 1 … row-level security pushdown (Phase 2) isn't implemented
yet … admin-only." That docstring has now misled an architecture document, a plan, and a
priority call. **Task 1.1 below fixes it**, and it is cheap relative to the damage it
has already done.

Lesson worth encoding: docstrings that describe *project phase* rather than *behaviour*
go stale silently, because no test asserts on prose.

---

## What the evidence actually says

Verified against the working tree, not assumed.

| Area | Finding | Verdict |
|------|---------|---------|
| DirectQuery RLS | Implemented, 14 tests, no admin gate | **Done** — correct the docstring |
| Import-mode memory | No source row cap; whole table materialises | **Gap — the real #1** |
| Health probes | `/health` exists; all 5 compose services have healthchecks | **Partial** — no readiness/liveness split |
| Metrics | OTLP **traces** export; no metrics, no `/metrics` | **Gap** |
| Backup / DR | No documented strategy for `postgres_data` | **Gap** |
| Test environment | Two known defects, still unfixed | **Gap — cheap** |
| Frontend → API | Every call routes through `api.ts` | **Clean** |
| Routers → SQL | Zero raw `text()` in routers | **Clean** |

---

### The memory ceiling, precisely

This is the top item now that RLS is settled.

Import-mode datasets **fully materialise before aggregating**. `widget_data.py` has a
result `limit` (default 50) but **no cap on the source frame** — searching for
`row_cap`, `MAX_ROWS`, `max_rows` in that module returns zero hits, while
`agent_row_cap=5000` exists for the agent path and `DEFAULT_ROW_CAP` exists for
DirectQuery.

So the two query paths are asymmetric:

| Path | Aggregation | Source rows loaded |
|------|-------------|--------------------|
| DirectQuery | Pushed into SQL | Bounded by `row_cap` |
| Import-mode | pandas `groupby` | **Unbounded** |

Materialisation points: `read_csv`/`read_parquet` in `frame_cache.py` (4 sites),
`analytics.py`, `dataset_refresh.py`; `SELECT *` in `connections.py` and
`dataset_refresh.py`.

A 100 MB upload (the documented ceiling) can expand several-fold in pandas memory, and
concurrent widgets each hold a frame. This is the single largest barrier to running the
platform at enterprise data volume — and it is what makes the DuckDB question worth
answering.

---

## Phases

### Phase 1 — Correctness of the record (S, do first)

Cheap, and two of these have already caused real damage.

| # | Task | Effort |
|---|------|--------|
| 1.1 | Rewrite the `direct_query.py` module docstring: state current behaviour (RLS push-down implemented, not admin-gated), delete the Phase 1/Phase 2 framing | S |
| 1.2 | Audit remaining docstrings for phase language — grep `Phase 1`, `not yet implemented`, `admin-only` across `services/`; each hit is either true or gets fixed | S |
| 1.3 | Replace box-drawing characters in `test_infer_keys_accuracy.py` so the suite passes on a default Windows console | S |
| 1.4 | Add a rootdir collection guard asserting a minimum collected-test count | S |
| 1.5 | Pin `pytest-timeout` in `backend/requirements.txt` | S |

**Acceptance:** suite green on a stock Windows shell without environment overrides; a
deliberately broken conftest fails the run rather than passing it.

### Implementation notes (recorded 2026-08-28, after doing the work)

Two things turned out differently from how this plan first described them.

**1.3 — the fix belongs in the test, not in config.** The first attempt set
`PYTHONUTF8=1` via an `env` key in `pytest.ini`. That key requires the `pytest-env`
plugin, which is not installed: pytest emitted `PytestConfigWarning: Unknown config
option: env` and the test kept failing. Adding a plugin dependency to work around one
decorative character is the wrong trade — the actual fix was one line, replacing `──`
with `--` in the report header at line 184. The test now passes on a stock cp1252
console with no environment setup and no new dependency.

**1.4 — the "exit 0 with zero tests" diagnosis was wrong, and the guard's placement
changed because of it.** Re-tested directly: a broken `tests/conftest.py` makes pytest
exit **4**, correctly non-zero, and it aborts *before* collection hooks run — so a
guard inside `conftest.py` could never fire for the case it was written for. The exit
code 0 originally observed came from the **RTK proxy wrapper** collapsing the run to
"Pytest: No tests collected" with a zero exit, not from pytest.

So the real false-green risk lives in the tooling layer, not the suite. The guard was
still added, at **rootdir** `backend/conftest.py` rather than `tests/conftest.py`, so
it survives whatever breaks the latter, and it covers the case pytest does not: enough
of the suite silently deselected or skipped to make a green run meaningless. It
imports only `pytest` and `os`, and it stands down for deliberate subset runs
(`-k`, `-m`, `--lf`, explicit paths, or `DATALYTICS_ALLOW_PARTIAL_COLLECTION=1`).

**Follow-up worth doing:** whatever CI or hook invokes pytest through a wrapper should
be checked for the same exit-code-swallowing behaviour. That is the actual defect this
task set out to fix.

---

### Phase 2 — The memory ceiling (M–L, the substantive work)

Runs as a **spike, then a decision**, not a predetermined rewrite. The question is
whether DuckDB should back import-mode aggregation.

| # | Task | Effort |
|---|------|--------|
| 2.1 | *(Depends on conformance 2.1)* — `widget_shaping.py` must exist first; it is the seam a second engine plugs into | — |
| 2.2 | Instrument the ceiling: measure peak RSS per widget query against realistic datasets (1 M / 10 M rows) on the current pandas path. Produce numbers, not estimates | M |
| 2.3 | Add a source-frame row cap to import-mode, mirroring `DEFAULT_ROW_CAP` — fail closed with a clear message rather than exhausting memory | S |
| 2.4 | Prototype a DuckDB backend behind `widget_shaping` for the aggregate path only (`groupby` + the 16 aggregations), keeping pandas for everything else | M |
| 2.5 | Benchmark 2.4 against 2.2's baseline; decide on evidence | S |
| 2.6 | If adopted: migrate the aggregate path, keeping pandas at the PyOD / scikit-learn / statsforecast boundaries | L |

**Acceptance for the spike (2.2–2.5):** a written comparison of peak memory and p95
latency at both dataset sizes, and a go/no-go recommendation. **2.6 does not start
without that.**

### Spike result 2026-08-28 — measured, and the answer is go

Peak RSS and wall time for one widget query (`GROUP BY region, SUM(sales), LIMIT 50`),
each measurement in a fresh subprocess so allocator free-lists and the frame memo
cannot inflate the next one. `pd` is the real `get_widget_data` path; `duck` is the
aggregate step alone, which is what a DuckDB backend behind `widget_shaping` replaces.

| shape | rows | csv MB | pandas MB | pandas s | duck MB | duck s | mem | speed |
|-------|------|--------|-----------|----------|---------|--------|-----|-------|
| narrow | 100,000 | 2 | 109 | 0.67 | 16 | 0.08 | 6.7× | 8.4× |
| narrow | 500,000 | 10 | 134 | 0.90 | 25 | 0.13 | 5.4× | 6.9× |
| narrow | 2,000,000 | 40 | 225 | 1.62 | 54 | 0.18 | 4.2× | 9.0× |
| wide | 100,000 | 20 | 159 | 0.99 | 35 | 0.27 | 4.5× | 3.7× |
| wide | 500,000 | 102 | 503 | 2.32 | 123 | 0.30 | 4.1× | 7.7× |
| **wide** | **2,000,000** | **406** | **1808** | **7.16** | **270** | **0.47** | **6.7×** | **15.2×** |

**The headline number: a 406 MB CSV costs 1.8 GB of RSS to answer a five-row question.**
That is ~4.5× amplification of the file, and it is memory the process holds for the
duration of the query. The documented upload ceiling is 100 MB; at that size the wide
shape already costs ~500 MB per concurrent render. Four simultaneous widgets on one
dataset is 2 GB.

**Results verified identical, not assumed.** Both engines were checked against each
other on the 2M-row fixtures: five groups each, maximum absolute difference 1e-6 on
sums of order 1e9 — relative error 3.7e-15 (narrow) and 1.3e-15 (wide), i.e. float64
rounding, not a semantic difference.

**Recommendation: proceed with 2.6**, scoped to the aggregate path only. The gain is
largest exactly where the platform hurts most (wide frames, where pandas carries every
column the query never touches and DuckDB reads only the two it needs), and it grows
with dataset size rather than washing out.

**Caveats that survive the spike:**

- These measure the *engine*, not the whole request. `get_widget_data` also shapes,
  caches, and applies RLS; those costs are unchanged and are not in the duck column.
  Expect the end-to-end win to be smaller than 15×.
- `read_csv_auto` re-parses the file per query. Import-mode currently amortises parsing
  through the frame memo, so a naive swap trades memory for repeated parse cost on
  cache misses. Converting uploads to Parquet once at ingest, and pointing DuckDB at
  that, is the shape that keeps both wins.
- The grain-safety rules in `direct_query.py` apply unchanged — `count`, `countd`,
  `std`, `variance`, `range` are not safe to re-aggregate through the shared shaper.
- Task 2.3 (a source-frame row cap) is still worth doing regardless, and is cheaper: it
  bounds the worst case now, before any engine work lands.

**Instrumentation note.** The first run of the harness reported `0.0 MB` for every
measurement. `GetProcessMemoryInfo` was being called without `argtypes`/`restype`, so
ctypes truncated the 64-bit process HANDLE, the call failed, and the struct stayed
zeroed — a silent zero rather than an error. Declaring the signatures fixed it, and the
meter was then validated against a known 229 MB allocation before any figure above was
believed.

---

### 2.6 done 2026-08-28 — shipped dark

`services/duck_agg.py` (layer 4) behind `settings.widget_duckdb_pushdown`, default
**off**. 45 tests in `tests/test_duck_agg.py`.

**The design is `direct_query`'s, not a rewrite of `shape_series`.** An eligible config
is aggregated by DuckDB into a small pre-aggregated frame, which `get_widget_data_from_df`
then shapes exactly as it already does for `run_direct_query`. `shape_series` has ~15
features (hierarchy levels, granularity labels, crosstab, post-aggregation measures,
quick calcs, running totals, multi-key sort); translating them all into SQL was never in
scope. `plan()` recognises the plain dimension + measure + grain-safe-aggregation shape —
the memory-dominant case — and declines the rest **with a reason**.

**Declining is free, and that is the whole safety argument.** DirectQuery must raise when
a config is unsupported: there is no local frame to fall back to. Here the fallback *is*
the pandas path, so every failure mode — ineligible config, unreadable header, an
unexpected DuckDB exception — is "slower, never wrong". The gate additionally requires
that no column denial, RLS filter, prep step, filter expression, calculated column or
measure definition is present, since each is a pandas transformation of the full frame.

**End-to-end, measured on a 422 MB / 2M-row / 30-column CSV:**

| | peak RSS | query RSS | time |
|---|---|---|---|
| pushdown off | 1627 MB | 1545 MB | 1.64s |
| pushdown on | 143 MB | **60 MB** | 0.84s |

**25.6× less memory** with a parquet sidecar present (uploads and refreshes write one).
Without a sidecar it is 8.4× — DuckDB re-parses the CSV — so the sidecar branch matters
and is now tested. The speed ratio narrows *because* both engines read parquet; the
memory gap is the point.

**Two divergences found, both real, both fixed or contracted:**

1. **`total` counted groups, not rows.** The shaper derives `total` from `len(df)`,
   which on a pre-aggregated frame is the group count. `plan()` now emits a `count_sql`
   that counts *after* the user's filters but *before* the null-dimension drop, matching
   what `shape_series` reports. Caught by the parity tests, not by inspection.

2. **NULL grouping.** pandas `groupby` drops NaN keys; SQL `GROUP BY` keeps NULL as a
   group. Without a predicate this renders an extra bar the pandas path never produced.
   `WHERE dim IS NOT NULL` restores parity, pinned by a test with nulls in both columns.

**The float64 contract, now explicit.** Two engines summing the same column in different
orders cannot agree bit-for-bit — pandas pairwise-sums, DuckDB sums in scan order, both
within an ulp of `math.fsum`. Measured worst relative difference on 2M rows: **1.43e-14**.
The parity helper asserts **exact** equality on structure, group names, ordering, row
count and `total`, and `pytest.approx(rel=1e-9)` on float values only. This is the same
property DirectQuery has always had against Postgres/MySQL; it is now written down rather
than implied.

The small parity fixtures summed exactly, so `==` passed while the true contract was
approximate — a 200k-row case was added specifically to exercise the tolerance path in
the suite rather than only in a scratchpad.

**Not yet done:** the `executor="duckdb"` value now reaches `query_runs`, so adoption and
fallback rates are observable, but nothing surfaces them. Enabling the flag on a real
deployment should watch that column before it is considered for a default change.

#### The flag-ON sweep found a real bug, and the gate was the wrong shape

Running the whole suite with pushdown forced on produced 10 failures. Nine were tests
asserting pandas-path internals (how many times `load_file` ran, the `executor` tag) —
they now pin their engine explicitly, which they should always have done. **One was a
genuine defect.**

A butterfly chart passes `measure2` for its second series. The eligibility gate was a
**blocklist** of ten features to decline, and `measure2` was not on it — so the config
looked eligible, DuckDB aggregated `measure` alone, and every `value2` came back
missing. The widget renders, and renders wrong.

That is the failure mode a blocklist has: **it fails open.** There are 34 distinct
`config.get(...)` keys across `app/`, and any future one would have inherited the same
silent-wrong behaviour. The gate is now an **allowlist** of the nine keys this path
actually understands; anything else — including a key invented next year — is ineligible
by default. `test_an_unknown_future_key_is_ineligible_by_default` pins that direction.

Worth stating plainly: the parity tests did not catch this, because they only ever
exercised configs I had already decided were eligible. The sweep caught it by running
*real* demo report configs through the new path. **A parity suite tests the cases you
thought of; a sweep tests the ones you did not.**

#### Two engines, one suite

`tests/conftest.py` now pins `widget_duckdb_pushdown` off by default — matching the
shipping default, and matching the precedent the embeddings fixture already set — so an
ambient environment variable cannot silently decide which engine the suite exercises.
`DATALYTICS_TEST_DUCKDB_PUSHDOWN=1` sweeps everything through DuckDB. It is deliberately
a *different* variable from the production `WIDGET_DUCKDB_PUSHDOWN`: configuring a
deployment and choosing what the tests exercise are different intentions, and conflating
them is how a suite ends up testing something other than what it reports.

#### The row cap and DuckDB

An eligible DuckDB query is **exempt** from `import_row_cap`, and that is deliberate: the
cap bounds frame materialisation, which this path does not do. Refusing a query whose
memory cost is already bounded would cost the operator a render for no benefit. Enabling
pushdown does **not** relax the cap for queries that still take the pandas path — both
directions are pinned in `TestDuckDBIsExempt`.

**Constraints established by the code, which the spike must respect:**

- **Pandas cannot be removed.** PyOD (`anomaly.py`), scikit-learn (`segment.py`) and
  statsforecast all take pandas/numpy objects. `requirements.txt` carries an explicit
  warning that numpy 1.26.4 / pandas 2.2.2 / scipy / sklearn / statsmodels / pyarrow are
  resolved as a set. This is a targeted addition, never a swap.
- **Grain-safety rules already exist.** `direct_query.py` documents which aggregations
  survive re-aggregation (`sum/avg/min/max/median/percentiles`) and which do not
  (`count`, `countd`, `std`, `variance`, `range`). A DuckDB path must honour the same
  distinction — the analysis is already written, do not re-derive it.
- **`_safe()` semantics must be preserved.** DuckDB's type mapping differs from pandas';
  JSON coercion needs explicit handling or API responses change shape.
- **`frame_cache` serialisation changes** if frames become Arrow tables. Cache-key
  isolation per RLS filter must survive — there are tests asserting this for DirectQuery
  and they are the model to follow.

---

### Finding 2026-08-28 — the test suite cannot see a cascade regression

Surfaced while building the demo use-case layer, whose teardown test failed on
`report parameters outlived their report`.

**Ten of the twelve tables that reference `reports.id` have no ORM-level cascade** —
including `ShareLink` and `EmbedConfig`, the two that carry credentials:

| Has ORM cascade | No ORM cascade |
|-----------------|----------------|
| `ReportPage`, `Bookmark` | `ShareLink`, `EmbedConfig`, `ReportParameter`, `ReportSchedule`, `ReportComment`, `ReportTranslation`, `ReportCapability`, `ReportClassification`, `CommonFilter`, `Delivery` |

`routers/reports.py::delete_report` does a bare `db.delete(obj)`, so those ten rows are
removed **only** by the schema's `ON DELETE CASCADE`.

**Production is fine** — Postgres always enforces foreign keys. **The test suite is
not**: SQLite ignores them unless a connection asks, and `tests/conftest.py` never did.
Verified on a two-table fixture: FKs off leaves the child row, FKs on removes it. So a
change that broke a cascade — or an endpoint that deleted a report while orphaning its
share links — would pass the suite.

**Fix:** `PRAGMA foreign_keys=ON` in the `db_session` fixture, so the test database
matches the database the product runs on. Measured blast radius: **8 failures and 12
errors out of 2,585**, all from fixtures that reference an `org_id` (or other parent)
with no row behind it — dangling-FK inserts that only ever worked because nothing was
checking. That is fixture debt, not product breakage.

Second, independent fix applied in the demo layer: `_remove_existing_use_cases` deletes
what it created **explicitly** rather than relying on a cascade whose enforcement varies
by database. For rows that grant access, teardown should not depend on the schema being
configured a particular way.

---

### Phase 3 — Operational readiness (S–M)

What an operator needs at 3 a.m., and what a deployment review asks for.

| # | Task | Effort |
|---|------|--------|
| 3.1 | Split `/health` into `/health/live` (process up) and `/health/ready` (Postgres reachable, Valkey reachable, migrations at head); point the compose healthcheck at the right one | S |
| 3.2 | Add metrics export alongside the existing OTLP traces — request rate/latency/error by route, query duration, cache hit rate, quota rejections. `telemetry.py` already wires the tracer; this extends it to a meter | M |
| 3.3 | Document and script the Postgres backup/restore path for `postgres_data`; include a restore drill in the runbook | M |
| 3.4 | Document what is *not* durable — `uploaded_files` volume, Valkey cache — and the recovery expectation for each | S |
| 3.5 | Surface migration state at startup: refuse to serve if the schema is behind head, rather than failing at first query | S |

**Acceptance:** an operator can answer "is it healthy," "is it slow, and where," and
"can we restore it" without reading source. A restore drill has been performed once and
written down.

### Progress (2026-08-28)

**3.1 — done.** `/health` kept as-is (static, liveness) because the compose healthcheck
and any external monitor already point there, and a liveness probe that touches Postgres
turns a brief blip into a restart loop. Added `/health/live` as a conventionally-named
alias, and `/health/ready`, which grades dependencies:

- **postgres** — required; unreachable returns 503
- **valkey** — optional, and only probed when `valkey_url` is set. `ValkeyCache`
  already fails soft behind a circuit breaker onto an in-process cache, so a degraded
  Valkey reports `"degraded"` and still returns 200. Failing readiness there would turn
  a cache slowdown into a full outage
- **migrations** — read from a new `_STARTUP_COMPLETE` flag set at the end of lifespan

Error bodies carry the exception *type name* only — a connection error can embed the
DSN, and this endpoint is unauthenticated. There is a test asserting a password in a
connection string never reaches the response.

Covered by `tests/test_health_probes.py` (9 tests), including
`test_live_does_not_touch_the_database`, which fails if someone later "improves"
liveness by adding a DB check.

**3.5 — folded into 3.1.** Migrations already run inside lifespan under a Postgres
advisory lock, so a serving app is by construction at head. The work was surfacing that
fact, not re-deriving it per request.

**Two compose defects found and fixed while doing 3.1:**

1. **The backend had no healthcheck at all.** Postgres, Valkey and embeddings each had
   one; the backend did not. Added, pointing at `/health/ready` with a 60s
   `start_period` to cover the migration window.
2. **`frontend: depends_on: [backend]` waited only for container start**, so the
   frontend could come up while the backend was still migrating and answer its first
   API calls with errors. Now `condition: service_healthy`.

**3.3 — done.** `docs/BACKUP_AND_RECOVERY.md`. The point worth carrying: `postgres_data`
and `uploaded_files` must be backed up **as a pair, files first**. A database restored
without the uploads volume produces a system that looks intact — datasets listed,
reports openable — and fails at the first import-mode widget render. The runbook's
verification drill explicitly renders such a widget, because every cheaper check passes
against an empty uploads volume.

**3.2 — done 2026-08-28.** Metrics export, alongside the existing OTLP traces.
13 tests in `tests/test_metrics.py`.

Four instruments, deliberately few — metrics are cheap to emit and expensive to
maintain, and a dashboard nobody reads is worse than none. Each answers a question an
operator actually asks during an incident:

| Instrument | Answers | Labels |
|-----------|---------|--------|
| `widget.query.duration` | is it slow, and where? | executor, cache_hit |
| `widget.query.total` | how much traffic, how much failing? | executor, cache_hit |
| `cache.operations` | is the cache working, or are we recomputing? | result |
| `quota.rejections` | are tenants hitting limits? | quota |

The last one closes a real gap: quota rejections were previously visible only by
reading logs, which is the wrong tool for "is this tenant being throttled?".

**It reuses the tracer's contract exactly**, because that contract is good:
`_NullMeter`/`_NullInstrument` mirror `_NullTracer`/`_NullSpan`, so with otel disabled
(the default) nothing imports `opentelemetry`, nothing allocates, and a render pays one
attribute lookup and a discarded call. Instruments are module attributes reassigned at
setup, so call sites must use `telemetry.<name>` and never a `from` import — the test
fixture patches them the same way the real setup installs them, so a call site that
froze the no-op would fail.

**Metrics setup is isolated inside its own `try`.** A collector that accepts traces but
rejects metrics must degrade to "tracing works, metrics do not" rather than losing both;
`otel_metrics_enabled` additionally lets a deployment opt out without giving up traces.

**One detail worth knowing:** OTLP/HTTP routes the two signals to *different paths*
(`/v1/traces`, `/v1/metrics`), so the metrics exporter cannot reuse `otel_endpoint`
verbatim. It is derived by swapping the signal path, with `otel_metrics_endpoint` as an
override; a non-standard endpoint is passed through untouched rather than guessed at.

`get_widget_data` has three return paths — cache hit, DuckDB, pandas — and a metric
missing from one would silently skew every rate built on it, so one helper emits at all
three and a test asserts each path counts **exactly once** (double-counting inflates
rates as surely as under-counting deflates them).

**Note on 3.3:** `postgres_data` is the only durable state in the stack and there is no
documented backup story. For an air-gapped deployment, where there is no managed
database service to fall back on, this is a genuine deployment blocker rather than a
nice-to-have.

---

## Sequencing

```
conformance Phase 0 ─┐
                     ├─▶ hardening Phase 1 ─▶ Phase 3   (independent)
conformance 2.1 ─────┘                    ─▶ Phase 2   (needs the seam)
```

Phase 1 and Phase 3 are independent and can run in parallel. Phase 2 is gated on the
conformance plan's `widget_shaping.py` extraction, and its second half is gated on its
own benchmark.

Effort: Phase 1 is five small tasks. Phase 3 is three small, two medium. Phase 2 is the
only one carrying a large task, and only conditionally.

---

## Explicitly out of scope

The mandate was hardening what exists. These were considered and excluded:

- **Enterprise buyer requirements** — SCIM, encryption at rest, DR SLAs, pen-test
  readiness, compliance evidence. A separate track; ask if it becomes procurement-driven.
- **Competitive features** — expression-language depth, Excel export, connector breadth.
  See the Power BI / SAS comparison.
- **DirectQuery capability breadth** — crosstab, running totals, and stats push-down on
  non-Postgres engines. These fail closed by design, which is correct behaviour, not a
  hardening defect.

---

## Verification

```bash
# every phase
python -m pytest -q                              # expect 2451 passed, 1 skipped
python -m pytest tests/test_layer_conformance.py -q

# Phase 1 specifically — must pass with no env overrides
python -m pytest -q                              # stock Windows console

# Phase 3
curl -f localhost:8000/health/ready
docker compose down && docker compose up -d && <restore drill>
```
