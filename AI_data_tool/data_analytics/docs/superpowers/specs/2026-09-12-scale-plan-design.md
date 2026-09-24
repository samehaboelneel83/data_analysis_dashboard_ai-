# Scale plan: both engines first-class

**Date:** 2026-09-12
**Status:** approved decomposition; sub-projects 1–5 bounded, 6 gets its own spec

## Why this exists

An external review of the 2026-09-12 scale measurements proposed a cost-based
query planner, an error taxonomy, aggregate tables and an RLS redesign. Checked
against the code, its P0 was wrong and most of the rest decomposed into bounded
work on paths that already exist. This records what was checked, what the
targets are, and what will be built in what order.

Target workload (decided): **both** — customer databases via DirectQuery at
10M–100M rows, and uploaded files at 5–50M rows.

## Targets (the definition of "acceptable")

| operation | target |
|---|---|
| simple dashboard, warm | < 1s |
| simple dashboard, cold | < 3s |
| filter interaction | < 1s |
| standard aggregation | < 2s |
| complex analytical query | < 5s |
| concurrency clause | the above hold with 10 users on one dashboard |

## What was measured (2026-09-12, dev box, unindexed Postgres, 1M-row/193 MB CSV)

| rows | import cold, one widget | DirectQuery bar chart |
|---|---|---|
| 100k | 0.52s | — |
| 1M | 5.6s no sidecar / **3.3s with sidecar** | 0.12s |
| 10M | refused (2M cap) unless DuckDB-eligible | 1.21s |

Against the targets exactly two things fail: the cold import render, and a
governed (RLS / column-security) widget over 2M rows on the import path.

Facts the plan rests on, each verified in code or by measurement:

- RLS on **DirectQuery is already a SQL predicate** (`direct_query._translate_rls`,
  its own subquery boundary). The review's "make RLS pushdown-compatible with
  DirectQuery" is done.
- The DuckDB shortcut on the **import** path is gated off by
  `not rls_filter_expr and not drop_columns and not filter_expr and not
  calculated_columns` (`widget_data.py:3234`). That gate is the real gap.
- `sql_expr.translate_filter_expr` already turns an RLS/filter expression into a
  SQL WHERE fragment with named params (`:r0`); DuckDB wants positional `?`.
- Of a 3.2s sidecar-backed cold render, **2.21s is `df.memory_usage(deep=True)`**
  in `frame_cache.get_frame`, sizing the frame for the memo by walking every
  Python string (11 text columns × 1M rows). Read 0.49s, null normalisation
  0.44s, store copy 0.09s.
- DirectQuery latency is flat in **memory**, linear in **time** on an unindexed
  table (sequential scan). The customer-side index is the lever.
- Widgets already render in parallel (each `WidgetRenderer` fetches on mount),
  bounded by `Semaphore(widget_work_max_concurrency=4)` per worker.
- `materialize_dataset` exists: import-only, one-shot snapshot, refuses governed
  data by design.
- Every DirectQuery execution is logged to `query_runs`.

## Rejected

- **Cost-based planner** (rows × joins × selectivity …): replaces a fail-safe
  allowlist pinned by 59 parity tests with estimates nobody has measured; its
  failure mode is a wrong result, not a slow one.
- **Raising the import cap**: moves the problem. The cap bounds pandas frames;
  DuckDB never materialises one, so widening DuckDB eligibility is the fix.
- **DuckDB as sole import engine**: revisit once sub-project 2 leaves DuckDB
  handling most renders — then it is a cleanup, not a bet.

## Sub-projects, in order

### 1. Frame memo sizing without the deep walk
**Closes:** cold render 3.2s → ~1s.
**Design:** `get_frame` sizes a frame to decide whether it fits
`frame_cache_max_total_bytes`. Replace `memory_usage(deep=True)` with
`memory_usage(deep=False)` plus an estimate for object columns from a sample of
rows (e.g. 10,000), scaled. The estimate only has to be good enough to keep the
cache within its bound; over-estimating slightly is the safe direction.
**Tests:** the estimate is within a tolerance of the deep figure on the bench
frame; a timing test that the sizing step on a 1M×11-object frame is under
0.2s; existing eviction tests unchanged.

### 2. Governed and richer widgets on DuckDB
**Closes:** the refusal for governed data over 2M rows; the review's real P0.
**Design:** `duck_agg` gains a `where_extra: (sql, params)` input. The gate at
`widget_data.py:3234` passes `rls_filter_expr` and `filter_expr` through
`translate_filter_expr`; an adapter rewrites `:rN` to `?` in first-occurrence
order and builds the positional list. Column security: `drop_columns` become
ineligible only if the dimension or measure is denied (then the pandas path
refuses as today); otherwise they simply never appear in the SELECT.
`calculated_columns`, `prep_steps` and `measures` stay ineligible.
**Fail-closed rules kept:** untranslatable expression → `Ineligible` (pandas
path, which then applies the cap as today). Any DuckDB error → pandas.
**Tests:** parity (same values as pandas at rel=1e-9) for RLS, filter_expr and
denied columns; a value test that an RLS-filtered widget over a frame above
the cap is ANSWERED by DuckDB and that the answer contains only the caller's
rows; sabotage: dropping the WHERE fails the row-containment test.

### 3. Benchmarks the targets need
**Design:** `bench_widget_data.py` writes the sidecar before timing (what an
upload does). New `bench_dashboard.py`: the 11-case battery as one page, cold
then warm, then the same with 10 concurrent clients via `bench_http.py`'s
storm. `bench_directquery.py` gains an RLS predicate column and an `--index`
flag to show the lever. New test: concurrent A/B/A/B schema isolation across
two sources that differ only by schema. Report format: a table with a column
per target and pass/fail.

### 4. Error taxonomy as a contract — done 2026-09-12

Shipped as designed, with two findings: the 200-with-`type:error` channel had
**no frontend reader** (a failed measure drew an empty chart, message lost), and
the first cut put `HTTPException` in a service, which `test_layer_conformance`
refused -- the exception lives in `core/widget_errors.py`, the code set stays
pure data in `services/error_codes.py`. Contract documented in ARCHITECTURE.md
("Error contract on the widget path").

Two divergences from the design below, both deliberate: there is **no
`query_error` code** — a SQL fault on DirectQuery (a renamed table) stays a
500 `internal`, by the earlier decision not to give our own faults a
comfortable explanation; and **`quota` was added** — `QuotaExceeded` is not an
HTTPException, so the router's pin never sees it and its own handler writes
the code. It is the second retryable answer, after `Retry-After`.

**Original design:**
**Design:** every widget-data error response carries `{"code": ..., "detail":
...}` with codes `source_unavailable`, `query_error`, `unsupported`,
`row_cap`, `forbidden_column`, `not_found`, `parameter`. HTTP status stays as
it is; the code is additive. The frontend widget error state switches on the
code for its message and retry affordance (`source_unavailable` retries; the
rest do not). Documented in ARCHITECTURE.md as the API contract.
**Tests:** one per code at the endpoint; a parity pin that every
`HTTPException` raised in `routers/widget_data.py` carries a code.

### 5. Index recommendations from observed queries — done 2026-09-12

Shipped as designed. `query_runs` gained `source_table`, `filter_columns` and
`group_column` (migration `0028`; names only, never values or SQL), collected
at the DirectQuery log site — the RLS rule's columns come from the same
translator that executes it. `services/index_advice.py` ranks
(table, filter column) by runs × mean duration, skips columns already leading
an index (read from the customer's `pg_indexes` through the metadata engine),
needs ≥ 3 runs, and never reads `group_column` — sabotaging it to do so fails
two tests. `GET /data-sources/{id}/index-advice`; a "Source health" tab on the
source review page with the paste-ready statement. Proved live: four filtered
renders on the demo DirectQuery source produced one recommendation and
`index_check: "checked"` against its real catalog.

Two corrections from review before it shipped: the customer's indexes are read
from the **catalog** (`pg_index.indkey[0]` → `pg_attribute`), not parsed from
`pg_indexes.indexdef` — the first version's regex read `(region DESC)` as a
column called "region DESC" and would have told a DBA to create an index that
existed (proved against real indexes: plain and `DESC` both report, an
expression index reports nothing). And a non-Postgres source now answers
`index_check: "unsupported"` with no statement, instead of a false "checked"
and Postgres syntax for MySQL.

**Original design:**
**Design:** a service reads `query_runs` for a source over the last N days,
extracts the columns used in **WHERE and RLS predicates** from the stored plan
shape (never SQL text — none is stored), and compares against `pg_indexes` for
the source table. Not GROUP BY columns: measured at 10M rows, an index on the
grouped column changed nothing (a full scan either way) while one on the
filtered column cut the governed query by a quarter — see "Results" below. Output: per table, columns used ≥ K times with no index, ranked
by count × average duration. Shown on the data-source page as "Source health".
Recommendations only; the platform never creates indexes on a customer
database.
**Open question for its own design pass:** what the stored plan shape must
carry, since `query_runs.sql_hash` is `None` today for DirectQuery.

### 6. Scheduled aggregates from DirectQuery sources — done 2026-09-12

Shipped as `services/aggregates.py` + `POST /datasets/{id}/aggregates`: a
scheduled `GROUP BY` compiled over the source's own base query and saved as an
ordinary import dataset, refreshed by the existing scheduler. The known
constraint held and became the design: the aggregate carries **no rules of its
own** — `core/rls.py` follows `aggregate_of_dataset_id` and applies the
SOURCE's row- and column rules at read time — so creation refuses a grain that
does not carry every column an RLS rule reads, and every refresh re-checks and
records a `ScheduleFailure` instead of rewriting a file it can no longer
govern. Only `sum`/`count`/`min`/`max` (they re-aggregate at a coarser grain);
`row_count` is always present.

**Proved live, 2026-09-12**, against `bench_scale_orders` — 10,000,000 rows,
639 MB, unindexed, in the app's own Postgres — attached as a DirectQuery
dataset and aggregated on `order_date × region` with `sum(amount)`,
`sum(units)`, refresh every 60 minutes:

| measurement | number | target | verdict |
|---|---|---|---|
| rows in the aggregate | **720** (the generator makes `region` a function of `order_date`, so the grain is 720 pairs, not 720×12) | — | — |
| first refresh (the 10M-row GROUP BY on the source, run synchronously by the create call) | **1.12s** | — | — |
| dashboard on the aggregate, cold (bar `region`, line `order_date` monthly, KPI — three widgets at once over HTTP) | **0.17s** | < 3s | **pass** |
| dashboard on the aggregate, warm | **0.10s** | < 1s | **pass** |
| the same bar rendered straight against the DirectQuery source | 1.28s cold / 0.05s warm (result cache) | — | the aggregate answers the cold bar **~9× faster** |

So a dashboard on the aggregate reads 720 rows instead of scanning 10M, and
the scan is paid once an hour by the scheduler rather than by every first
visitor — which is the whole bet. The source-side number also repeats the
sub-project 3 finding: an unindexed 10M-row GROUP BY is a sequential scan and
costs about a second every time it is not cached.

## Results after sub-projects 1–3 (same box, same day)

| target | before | after | verdict |
|---|---|---|---|
| dashboard cold (7 widgets, 400k rows, HTTP) | — | **2.5s** | pass at 400k (< 3s); **at 1M, `line_month` alone measures 5.35s cold, so the same page would fail** — the 100 MB upload cap kept this run at 400k |
| dashboard warm | — | **0.22s** | pass (< 1s) |
| 10 users, one dashboard, p95 | — | **1.9s** | **fail** (< 1s) |
| 10 users, ten distinct dashboards, p95 | — | 21.8s | (no target; the gap to the row above is the result cache) |
| governed widget over the cap, 1M rows | refused | **0.56s cold, contained** | pass |
| cold `get_frame`, 1M rows, sidecar | 3.20s | **1.08s** | — |
| widget battery cold, 1M rows | 63.1s (no sidecar, deep sizing) | 16.8s (sidecar **and** sampled sizing — two fixes, one arrow) | — |
| DirectQuery bar, 10M rows, unindexed → indexed | 1.08s → 1.10s | — | index does **not** help a full GROUP BY |
| DirectQuery governed (RLS filter), 10M, unindexed → indexed | 0.95s → 0.71s | — | index helps the **filter**, ~25% |

What the numbers changed in the plan:

- **Sub-project 5's advice must target filter and RLS columns, not GROUP BY
  columns.** An index on the grouped column did nothing for the aggregation
  (a full scan either way); an index on the filtered column cut the governed
  query by a quarter. A recommender that said "index `category`" because it is
  grouped would be giving wrong advice with a confident number.
- **The concurrency fail is DB round-trips per request, measured in tiers.**
  70 concurrent requests each, idle box, one `--reload` worker:

  | tier | single | ×70 wall | per request, serialised |
  |---|---|---|---|
  | `/health` — no auth, no DB | 5 ms | 0.17s | 2 ms |
  | `/auth/me` — auth + one row | 10 ms | 0.65s | 9 ms |
  | cache-hit widget POST | 42 ms | 1.65s | **24 ms** |
  | `/datasets` — 4 queries + 1 per dataset | 51 ms | 2.18s | 31 ms |

  The event loop is not the cost (2 ms). Authentication is 9 ms of it. The
  other ~15 ms of a widget request is the dataset / quota / parameters / RLS
  / column-rule lookups that run before the result cache is consulted — six
  awaited queries, each a round-trip, serialised across one process's
  connection pool. The `Semaphore(4)` render gate never enters into it.
  (An earlier draft of this paragraph blamed "whatever every authenticated
  request pays" from a `/datasets` comparison; `/datasets` turned out to be
  4+N queries, which proved nothing. The tiers above replace it.)
  Levers, in order of what the numbers say: (1) a **page-level batch
  endpoint** — one auth + one set of lookups for N widgets, dividing the
  per-page cost by ~7; (2) **memoise the per-(user, dataset) lookups** for a
  few seconds — the 15 ms is the majority of the 24; (3) worker count /
  pool size (`UVICORN_WORKERS`; the engine runs SQLAlchemy's default pool of
  5+10) — multiplies throughput, needs a restart to measure, the user's call.
- **`dimension_granularity` on the DuckDB allowlist — done, same day.**
  `line_month` cold at 1M rows: **5.35s → 0.22s**; battery 16.8s → 11.7s.
  Labels match pandas for all five granularities (ISO week via `%G-W%V`;
  year as text because the shaper re-buckets DuckDB's output and an integer
  year re-parses as 1970). DuckDB declines when any non-null value fails
  `TRY_CAST` (pandas parses "01/02/2024", DuckDB does not) or when nothing
  parses (pandas hands the raw column back). Found on the way: pandas labelled
  a **null date as the string `"<NA>-Q<NA>"`** for quarter and week — a
  garbage bar on any chart with one missing date — fixed to label as missing,
  as month and day already did. What remains in the battery is pandas-path
  widgets at ~1.2–2s, which is the 1.15s frame load plus shaping.

## Sequencing rationale

1 and 2 are the two rows that fail the targets. 3 makes the targets a
measurement instead of a claim and must follow 1–2 so it measures the fixed
paths. 4 and 5 are the SAS-beating work and touch nothing the first three
depend on. 6 is the only item with real design risk.
