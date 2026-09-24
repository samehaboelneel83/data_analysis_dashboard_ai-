# DirectQuery (Live Data Sources Without Import)

**Date:** 2026-08-15
**Status:** All 5 phases complete — aggregate pushdown, RLS pushdown, `sql_stat` strategy
(histogram + correlation_matrix, Postgres-only; `box_plot` deferred, see note below),
`row_capped` strategy with sampling + frontend indicator, and TTL caching + a dataset-creation
UI toggle between Import and DirectQuery

## Overview

Every dataset in this app today is **materialized to a file before it can be queried**. A user
connects a database, previews it, and imports it — `import_to_dataframe` pulls up to 100,000 rows
into a pandas DataFrame which is written to disk, and from then on every widget reads that file.
The live source is never touched again.

This spec adds **DirectQuery**: a dataset backed by a live connection, where each widget render
issues a query against the source and aggregation happens **in the source database** rather than
in pandas. This buys three things the import path structurally cannot: real-time freshness (no
sync lag), scale beyond what fits in memory or under the 100k row cap, and no duplication of
governed warehouse data onto this server's disk.

The design constraint that shapes everything below: **the existing shaper and renderer layers must
not change.** The `SHAPERS` registry in `backend/app/services/widget_data.py` maps **32 widget
types onto 14 shaper functions**, each widget type paired with its own React renderer in
`frontend/src/components/report/chartRenderers/`. Rewriting that for a second execution mode would
double the surface area of every future chart type. Instead
DirectQuery produces a small pandas DataFrame — pre-aggregated by the source — and feeds it to the
**same** `get_widget_data_from_df`. The section on the grain invariant explains why that is
correct and not a convenient fiction.

This builds on `docs/superpowers/specs/2026-08-13-row-level-security-design.md`, which is already
implemented. RLS is the hardest part of this spec: it currently filters a DataFrame, and under
DirectQuery it must become a SQL predicate or the whole point of not fetching rows is lost.

## Current State

- **The query pipeline** — `get_widget_data(...)` (`backend/app/services/widget_data.py:1088`) is
  the single entry point: `load_file` → `apply_rls_filter` → `apply_filter_expr` →
  `apply_calculated_columns` → `get_widget_data_from_df`. Every step operates on a DataFrame.
- **The shaper registry** — `SHAPERS: dict[str, Callable[[pd.DataFrame, dict], dict]]`
  (`widget_data.py:682`); `get_widget_data_from_df` (`:745`) dispatches on `widget_type`, falling
  back to `shape_series` for unregistered types. Each shaper does its own pandas `groupby`/`agg`.
- **Caching** — an LRU dict + lock (`:1036-1085`). The key (`:1040`) includes `file_stat`
  `(mtime, size)` so a re-upload invalidates, and `rls_filter_expr` **verbatim** so two roles can
  never share an entry. The docstring at `:1044` documents that isolation as load-bearing.
- **Connections are import-only** — `backend/app/services/connections.py` supports
  postgres/sqlserver/mysql/oracle/sqlite/api. `_build_url` builds the SQLAlchemy URL, `_limit_sql`
  already handles dialect differences (`TOP` / `FETCH FIRST` / `LIMIT`), and `import_to_dataframe`
  is the only path that runs a real query. `create_engine` is called per request and `dispose()`d
  immediately — no pooling, which is fine for occasional imports and not fine for per-widget reads.
- **Lineage fields already exist** — `Dataset.data_source_id`, `Dataset.source_table`,
  `Dataset.source_query` (`backend/app/models/models.py:22-24`) already record where an imported
  dataset came from. DirectQuery reuses these rather than adding parallel fields.
- **The blocker** — `backend/app/routers/widget_data.py:18`: `if not ds.filename: raise
  HTTPException(404, "Dataset not found")`. A dataset with no file is currently unqueryable by
  definition.
- **RLS** — `resolve_rls_expr(db, current_user, dataset_id)` (`backend/app/core/rls.py`) returns
  the caller's filter expression string or `None` (org admins bypass), and `apply_rls_filter`
  (`widget_data.py:980`) applies it to the DataFrame at `:1108`, before any other filtering.
- **Expression safety** — `_validate_expr_safety` (`widget_data.py:766`) validates filter
  expressions against an AST allowlist that structurally excludes `ast.Attribute`, blocking dunder
  and method-call escapes. This is the parser DirectQuery reuses to compile expressions to SQL.

## Data Model

One new column, following the existing `_migrate()` convention in `backend/app/main.py`
(idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` on startup — no Alembic, per the RLS spec's
documented decision):

```python
    mode = Column(String(20), nullable=False, server_default="import")   # 'import' | 'directquery'
```

A DirectQuery dataset has `mode='directquery'`, a non-null `data_source_id`, exactly one of
`source_table` / `source_query`, and `filename` **NULL**. An import dataset is unchanged —
`server_default="import"` means every existing row is already correct after the migration, with no
backfill step.

`DatasetColumn` rows are still populated for a DirectQuery dataset, from a one-time schema probe at
creation (`LIMIT 0`, or the existing `preview_table` at a small limit). These are not decorative:
they are the **allowlist** that identifier validation checks against when building SQL, so the
field-picker UI and the SQL safety layer read from the same source of truth.

## Query Path

`backend/app/routers/widget_data.py` branches on mode. The filename guard at `:18` becomes
import-mode-only — that is the entire change to the existing path:

```python
    rls_filter_expr = await resolve_rls_expr(db, current_user, dataset_id)

    if ds.mode == "directquery":
        source = await db.get(DataSource, ds.data_source_id)
        check_org(source, current_user, "Data source not found")   # re-check: never trust the FK alone
        return run_direct_query(
            source.config, ds, req.config, widget_type=req.widget_type,
            calculated_columns=calc_cols or None, filter_expr=ds.default_filter_expr or None,
            rls_filter_expr=rls_filter_expr,
        )

    if not ds.filename:
        raise HTTPException(404, "Dataset not found")
    return get_widget_data(ds.filename, ...)   # unchanged
```

The org check on the `DataSource` is deliberate and not redundant: `data_source_id` is a plain FK
and a dataset could in principle reference a source belonging to another org (through a bug, an
import, or a future sharing feature). Re-checking means a DirectQuery dataset can never become a
lateral path to another org's credentials.

New module `backend/app/services/direct_query.py`:

- `plan_query(dataset, config, widget_type) -> QueryPlan` — resolves roles via the existing
  `resolve_roles(config)` (`widget_data.py:726`) and picks a strategy from the capability matrix.
- `build_sql(plan, source_cfg, rls_expr, filter_expr) -> (sql, params)` — pure, no I/O, so it is
  directly unit-testable as golden SQL per dialect.
- `run_direct_query(...) -> dict` — executes, wraps the result in a DataFrame, and hands it to the
  existing `get_widget_data_from_df(df, config, widget_type)`.

## Aggregation Pushdown and the Grain Invariant

A widget like a bar chart of `SUM(revenue)` by `region` becomes:

```sql
SELECT "region" AS dim, SUM("revenue") AS measure
FROM (<base>) AS src
WHERE <rls predicate> AND <report filter>
GROUP BY "region"
ORDER BY 2 DESC
LIMIT <category cap>
```

The result — one row per region — is loaded into a DataFrame and passed to `shape_series`, which
performs its **own** pandas `groupby('region').sum()` on it.

That double aggregation is safe because of a specific invariant, and it is worth stating precisely
because the whole no-shaper-rewrite strategy rests on it:

> **Grain invariant.** When the pushed-down `GROUP BY` keys are exactly the keys the shaper groups
> by, every resulting group contains exactly one row. Re-aggregating a single value is the identity
> for `SUM`, `MIN`, `MAX`, `AVG` and `FIRST` alike — so the shaper's second pass is a structural
> pass-through, not a second computation.

The invariant holds only at **exactly** matching grain, which produces two hard rules:

1. `plan_query` derives its `GROUP BY` from `resolve_roles(config)` — the same function the shaper
   uses to decide its grouping. Both sides read one source of truth; they cannot drift.
2. **Non-decomposable aggregates must be computed at the final grain and never re-derived.**
   `COUNT(DISTINCT x)` and `median`/percentiles are not re-aggregatable — a distinct count of
   distinct counts, or a median of medians, is simply wrong. At matching grain they are safe
   (there is nothing to re-combine); at any other grain they must not be pushed down at all. If a
   plan cannot express the requested aggregate at the shaper's grain, it falls back to the
   `row_capped` strategy rather than emitting a subtly wrong number.

A silent wrong number is the worst failure mode this feature could have — worse than an error,
because a dashboard reporting a plausible-but-wrong total gets acted on. The equivalence test in
the Testing section exists specifically to hold this invariant down.

## Shaper Capability Matrix

Not every chart can be answered by a `GROUP BY`. Each entry in `SHAPERS` gains a DirectQuery
strategy tag, kept in a parallel `DQ_STRATEGY: dict[str, str]` in `direct_query.py` (parallel
rather than folded into `SHAPERS` so the import path keeps working untouched, and an unlisted
chart type safely defaults to `row_capped`):

| Strategy | Shapers | How it executes |
|---|---|---|
| `aggregate` | `shape_series`, `shape_dual_series`, `shape_waterfall`, `shape_gauge`, `shape_heatmap` | Pushed-down `GROUP BY` at the shaper's grain (above) |
| `sql_stat` | `shape_histogram`, `shape_correlation_matrix` (Postgres only — see correction below) | Dialect statistical SQL — `width_bucket` for bins, `corr()` for the matrix |
| `row_capped` | `shape_xy_numeric`, `shape_bubble`, `shape_bubble_animated`, `shape_parallel_coordinates`, `shape_gantt`, `shape_vector_plot` | Raw rows fetched under a configurable cap, sampled if exceeded |

`sql_stat` shapers get a small adapter each: the SQL returns the same summary the shaper would have
computed (bin edges and counts, the correlation pairs), and the adapter reshapes it into the frame
the shaper expects. These are genuinely row-level computations that cannot be a `GROUP BY`, but
every supported dialect can express them natively — which is the whole reason to prefer this over
dragging millions of rows across the wire.

**Correction from the originally-approved design, found during implementation:** this section
originally listed `shape_box_plot` under `sql_stat` alongside histogram and correlation_matrix.
Building it revealed a real problem: `shape_box_plot`'s output includes an `outliers` field — the
actual raw values beyond 1.5×IQR from q1/q3 — which is irreducible row-level detail, not a
statistic `PERCENTILE_CONT` (or any aggregate) can produce. A correct implementation would need a
window-function two-pass query (per-category quartiles via a window, then a second pass selecting
rows outside the computed fences), which is closer in shape to `row_capped` than to the other two
`sql_stat` shapers and was judged out of proportion to add under time pressure without dedicated
design and dialect testing. `shape_box_plot` is deferred to a future phase rather than shipped with
a silently-empty `outliers` list. Separately, `width_bucket`/`CORR` were verified directly against
a live Postgres instance during implementation (see `tests/test_direct_query_stat_postgres.py`,
skipped when no Postgres container is reachable) but **not** MySQL/SQLite (no native
`WIDTH_BUCKET`) or Oracle (boundary behavior unverified) — `sql_stat` is Postgres-only until those
are individually verified, rather than shipping untested dialect SQL.

`row_capped` shapers are irreducibly row-level: a scatter plot *is* one mark per row. They fetch up
to `directquery_row_cap` rows (default 10,000). When the underlying row count exceeds the cap the
query samples rather than truncating — an unsampled `LIMIT` on an unordered scan produces a
misleading chart that looks complete — and the response carries `{"sampled": true, "sample_size":
n, "total_rows": N}` so the renderer can badge the widget. **Truncation must never be silent**, for
the same reason a wrong aggregate must not be: the user has to know they are looking at a sample.

`shape_gantt` and `shape_vector_plot` are listed as `row_capped` because they plot per-row marks;
in practice their datasets are small enough that the cap will rarely bind.

## Row-Level Security Pushdown

This is the security-critical section. Under import mode, `apply_rls_filter(df, expr)` filters an
already-loaded DataFrame. Under DirectQuery, filtering after the fetch would defeat the entire
feature — the aggregate would already have been computed over rows the user may not see. So the
RLS expression must become a SQL predicate applied **before** aggregation:

```sql
FROM (SELECT * FROM <base> WHERE <rls predicate>) AS src
```

Wrapping in a CTE/subquery rather than appending to the outer `WHERE` is deliberate: it makes the
RLS predicate structurally impossible to be defeated by an `OR` in a report-level filter, and it
means every aggregate in the outer query is definitionally computed over permitted rows only.

Translation reuses the AST walk behind `_validate_expr_safety` (`widget_data.py:766`) rather than
introducing a second expression parser — the allowlist that makes an expression safe to `eval` is
the same allowlist that makes it mechanically translatable to SQL. Each allowed node maps to its
SQL equivalent; column names resolve against the `DatasetColumn` allowlist; literals become bound
parameters.

**Fail-closed is mandatory.** If any part of an RLS expression cannot be translated — an
unsupported function, a pandas-specific idiom, anything the mapper does not recognise — the request
**raises**. It must never emit the query without the predicate, and it must never fall back to
fetching rows and filtering locally, because both silently hand the user rows their role forbids.

This is the exact opposite of the import path's behavior, and the contrast is intentional:
`apply_rls_filter` degrades silently by design so one malformed rule does not 500 an entire report.
That trade-off is only acceptable because in import mode a malformed expression yields an *empty*
result (fail-closed already). In DirectQuery, "no predicate" would mean *all rows*. Same
philosophy, opposite implementation.

Rules are validated at authoring time against the live source (the RLS spec already validates
expressions when a rule is created), so an untranslatable rule surfaces to the admin who wrote it
rather than to the viewer whose dashboard breaks.

## SQL Safety

Every identifier that reaches generated SQL is validated against the dataset's known
`DatasetColumn` names and then dialect-quoted — an allowlist, not an escaping routine, so a column
name that is not real cannot reach the database at all. `source_table` is validated against the
schema probe the same way.

Literals are **always** bound parameters, never interpolated, including values coming from filter
expressions and cross-filter selections.

A user-supplied `source_query` is wrapped as a subquery (`FROM (<source_query>) AS src`) and never
string-concatenated with generated fragments. The query is the user's own authored SQL against
their own connection, so it is trusted to the same degree the connection is — but it is
syntactically isolated so it cannot alter the shape of the predicates wrapped around it.

## Caching

The existing cache needs three changes to be correct for live sources.

**Key collisions.** `file_stat` is `None` for a DirectQuery dataset — but `None` already means
"file missing/unreadable" (`:1099`), so a DirectQuery entry could collide with a file-based one.
The key gains an explicit source discriminator: `("directquery", data_source_id, hash(source_table
or source_query))`.

**Invalidation.** There is no mtime to watch. Replace it with a TTL bucket — `floor(now / ttl)` as
a key component, so entries age out by construction without a sweeper. `DataSource` gains
`cache_ttl_seconds` (default 60), where **0 disables caching entirely** for sources where true
real-time matters and a minute of staleness is unacceptable.

**Isolation is preserved unchanged.** `rls_filter_expr` stays in the key verbatim and
un-normalized, keeping the guarantee documented at `:1044`: a role with tighter RLS can never be
served an entry computed for a role with looser RLS. This property is if anything more important
here, since a DirectQuery cache entry holds live governed data.

## Connection Pooling

Import runs a query occasionally; DirectQuery runs one **per widget per render**, so a dashboard
with twelve widgets opens twelve connections on every load under the current
`create_engine`/`dispose` pattern. `direct_query.py` introduces a module-level engine registry
keyed by a hash of the data-source config, with `pool_pre_ping=True` (so a connection dropped by
the source is retried rather than surfaced as a widget error) and a per-query statement timeout
(`directquery_statement_timeout_seconds`, default 30) so one pathological query cannot pin a
worker. Engines are disposed when their `DataSource` is updated or deleted.

## DuckDB

DuckDB is adopted as the in-memory columnar engine for **import** mode and as the local SQL
executor. This is what makes one translation layer serve both modes: `build_sql` emits DuckDB SQL
over the dataset's parquet/CSV file for import datasets, and dialect SQL over the live source for
DirectQuery ones. `load_file` (`backend/app/services/analytics.py:20`) already reads parquet, so
the file format needs no change.

Adopting it for import mode is deliberately **out of scope for this spec's rollout** — it is
recorded here because the SQL builder must be designed with two dialects in mind from the start
rather than being retrofitted, and is specified in
`docs/superpowers/specs/2026-08-15-core-platform-architecture-design.md`.

## Testing

- **Golden SQL per dialect (pytest):** `build_sql` is pure, so assert exact generated SQL and bound
  parameters for each strategy across postgres/mysql/sqlserver/oracle/sqlite — especially the
  dialect-divergent pieces (`_limit_sql`'s existing `TOP`/`FETCH FIRST`/`LIMIT` split, and
  `percentile_cont`/`width_bucket` availability).
- **Grain-invariant equivalence (the most important test):** load a fixture into both a SQLite
  source and a file, then assert `run_direct_query(...) == get_widget_data(...)` for every
  `aggregate`-strategy chart type across a matrix of aggregations (`sum`, `count`, `avg`, `min`,
  `max`, `distinct count`) and one/two grouping roles. This is the test that holds the invariant
  down as shapers evolve; a new shaper that breaks it fails here rather than in a user's dashboard.
- **RLS pushdown:** the predicate appears in the wrapping subquery, not the outer `WHERE`; a role
  with a rule sees only matching rows; an org admin's query carries no predicate; an
  **untranslatable expression raises and emits no SQL at all** (assert the executor is never
  called — this is the fail-closed guarantee, so test the absence of the call, not just the raise).
- **SQL safety:** hostile column/table names (quotes, semicolons, comment sequences) are rejected
  by the allowlist rather than escaped; filter literals appear only as bound parameters.
- **Caching:** a DirectQuery key never collides with a file-based key for the same dataset id; two
  roles with different RLS expressions get different entries (mirroring the `:1044` guarantee);
  `cache_ttl_seconds=0` bypasses the cache; entries expire when the TTL bucket rolls over.
- **Sampling:** exceeding the row cap sets `sampled: true` and samples rather than truncating.

## Explicit v1 Exclusions

- **No cross-data-source joins.** A DirectQuery dataset is one table or one query against one
  connection. Federation is the natural next step once DuckDB is in place, but it is a separate
  design problem (predicate pushdown across heterogeneous sources) and is not attempted here.
- **No `api`-type sources.** `_fetch_api` retrieves a JSON document; REST endpoints cannot express
  `GROUP BY`, so there is nothing to push down. API sources remain import-only.
- **No hybrid/dual mode.** The Computation Strategy Matrix in the architecture doc describes a
  hybrid mode (cached aggregates in RAM, drill-through live). That depends on both a working
  DirectQuery path and the columnar engine, and is deliberately sequenced after both.
- **Calculated columns are rejected outright, not translated.** `widget_data.py`'s router branch
  returns 400 for any DirectQuery widget-data request carrying calculated columns (dataset- or
  report-level) — there is no attempt to translate calculated-column expressions to SQL. The
  original plan described authoring-time translatability checking; that was not built. A
  DirectQuery dataset needing calculated columns must stay on (or move to) import mode for now.
- **No write-back, no scheduled refresh.** DirectQuery is read-only; there is nothing to refresh.

## Rollout (phases — each gets its own implementation plan)

All 5 phases are implemented and merged.

1. **Phase 1 — Aggregate pushdown, admin-only.** `Dataset.mode` + migration, the router branch, the
   engine registry, `build_sql`/`build_count_sql` for the `aggregate` strategy, and
   `run_direct_query`. Restricted to org-admin users so no RLS translation was needed yet. Proved
   the grain invariant end-to-end against a real on-disk SQLite database
   (`tests/test_direct_query_execution.py`).
2. **Phase 2 — RLS pushdown.** `sql_expr.translate_filter_expr` (fail-closed AST→SQL translation,
   reusing `_validate_expr_safety`'s allowlist), wired into `run_direct_query` and into
   `admin.py`'s `RowSecurityRule` authoring-time validation (which previously required a file to
   sample against — a real gap found while implementing this phase, since DirectQuery datasets have
   none). Lifted the admin-only restriction.
3. **Phase 3 — `sql_stat` strategy.** Histogram and correlation_matrix, Postgres-only; `box_plot`
   deferred (see the correction note above).
4. **Phase 4 — `row_capped` strategy.** Row cap + random-order sampling + `sampled`/`sample_size`/
   `total_rows` fields, surfaced as a header-level badge in `WidgetRenderer.tsx` (one shared badge
   for all row-capped chart types, not six separate renderer changes).
5. **Phase 5 — Caching and UI.** TTL-bucket cache keys reusing `widget_data`'s existing LRU cache
   (not a second cache), `DataSource.cache_ttl_seconds`, and an Import/DirectQuery toggle in the
   dataset-creation flow.

## Files Changed

| File | Change |
|---|---|
| `backend/app/services/direct_query.py` | New — `plan_query`/`build_sql`/`build_count_sql` (aggregate), `plan_histogram`/`plan_correlation_matrix` + builders (sql_stat), `plan_row_fetch`/`build_row_fetch_sql` (row_capped), `_directquery_cache_key`, `run_direct_query`, engine registry |
| `backend/app/services/sql_expr.py` | New — `translate_filter_expr`, reusing `widget_data._validate_expr_safety`'s AST allowlist |
| `backend/app/models/models.py` | `Dataset.mode`; `DataSource.cache_ttl_seconds` |
| `backend/app/main.py` | `_migrate()` gains the `mode` and `cache_ttl_seconds` column statements |
| `backend/app/routers/widget_data.py` | Branches on `ds.mode`; filename guard is import-only; org-checks the `DataSource`; passes `cache_ttl_seconds` through |
| `backend/app/routers/data_sources.py` | `POST /{id}/import` gained `mode` — `directquery` skips materialization, does a schema probe (`preview_table`) to populate `DatasetColumn` instead |
| `backend/app/routers/admin.py` | `RowSecurityRule` create/update validate via `translate_filter_expr` for DirectQuery datasets instead of requiring a file |
| `backend/app/services/widget_data.py` | `_widget_data_cache_get`/`_widget_data_cache_set`/`clear_widget_data_cache` reused as-is by `direct_query.py`, unchanged |
| `frontend/src/components/report/WidgetRenderer.tsx` | Header-level "sampled" badge, shared across every row-capped chart type |
| `frontend/src/pages/Connections.tsx` | Import vs. DirectQuery toggle in the schema browser's import bar |
| `frontend/src/services/api.ts` | `dataSourcesApi.import` gained a `mode` parameter |
| `backend/requirements.txt` | `duckdb` (Phase 5 / architecture spec) |
| `frontend/src/components/report/chartRenderers/*` | "Sampled" indicator for `row_capped` charts (Phase 4) |
| `frontend/src/pages/Connections.tsx` | Import vs. DirectQuery choice when creating a dataset from a connection (Phase 5) |
