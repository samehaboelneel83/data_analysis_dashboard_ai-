# Aggregate datasets from DirectQuery sources

**Date:** 2026-09-12
**Status:** design approved in conversation; implementation plan next
**Parent:** `2026-09-12-scale-plan-design.md`, sub-project 6

## Why

A dashboard on a 100M-row DirectQuery table pays a sequential scan per widget
per render (measured: 1.2s per bar chart at 10M rows, linear in rows). The
answer is not to make the scan faster; it is to stop scanning: aggregate once,
where the data lives, on a schedule, and let dashboards read thousands of rows
instead of millions.

The platform already has every mechanical part of that. An import-mode dataset
with `refresh_interval_minutes` is re-pulled by the in-process scheduler via
`dataset_refresh.rewrite_dataset_file(source_cfg, filename, source_table,
source_query)`; a file dataset gets a parquet sidecar and the DuckDB path.
What it does not have is a safe way to do it for **governed** data, and
governed data is the point. `materialize_dataset` names the problem exactly
and refuses: a snapshot taken under one user's row-level security is a
silently truncated table for everyone else, and copying the rules onto the
copy breaks the moment the aggregation removes the rule's column.

This design chooses, for the first time, something other than refusal.

## Decisions taken

- **Explicit aggregates, chosen by an author.** Not transparent query
  rewriting. A rewriting planner has to prove that an aggregate answers *this*
  query at *this* grain, and a wrong match is a wrong number with no error
  anywhere. Explicit aggregates are datasets like any other; a widget on one
  is an author's decision that can be seen and reviewed.
- **Rules are never copied.** An aggregate resolves row-level and column
  security from its source at read time, through `aggregate_of_dataset_id`.
  No copy, no drift.
- **The grain must cover every RLS column, at creation and forever.**
  Creation refuses otherwise, naming the role and column. A rule added to the
  source later that the grain cannot express makes the aggregate fail closed
  for that role and flags the dataset. Nothing ever shows a row the source
  would have hidden.
- **Only additive aggregations:** `sum`, `count`, `min`, `max`. `row_count`
  is always present so averages are `x_sum / row_count`. No `avg`, no
  count-distinct: neither re-aggregates correctly at a coarser grain, and a
  widget on the aggregate will re-aggregate.

## The model

`Dataset` gains:

| column | type | meaning |
|---|---|---|
| `aggregate_of_dataset_id` | FK → datasets, nullable, `ondelete=CASCADE` | the DirectQuery source this dataset summarises; null for every other dataset |
| `aggregate_spec` | JSON, nullable | `{"grain": [...], "measures": [{"column", "agg", "name"}]}` — what was asked for, so the SQL can be recompiled and the UI can show it |

An aggregate dataset is otherwise an ordinary import-mode dataset: `mode =
"import"`, `data_source_id` = the source's, `source_query` = the compiled
aggregation, `refresh_interval_minutes` as chosen, a file and its sidecar.
Deleting the source cascades to its aggregates: an aggregate whose source is
gone cannot resolve rules and must not outlive it.

Alembic revision `0029_aggregate_datasets`.

## Compilation

```
SELECT <grain columns>,
       SUM("x")   AS "x_sum",  COUNT("y") AS "y_count", MIN(...), MAX(...),
       COUNT(*)   AS "row_count"
FROM (<source base query>) AS src
GROUP BY <grain columns>
```

- `<source base query>` is `direct_query._base_query_sql(dataset)` with **no**
  RLS predicate: the aggregate holds every row's contribution and RLS is
  applied when it is read, on grain columns that are guaranteed to be there.
- Identifiers are quoted with `direct_query._quote`; grain, measure columns
  and aggregation names are validated against the source's `DatasetColumn`s
  and a fixed allowlist. No user-supplied SQL fragment appears anywhere.
- Measure output names default to `<column>_<agg>`; `row_count` is reserved.
- The compiled text is stored in `source_query`, so the existing refresh path
  runs it unchanged and "Edit" can recompile from `aggregate_spec`.

## Governance, precisely

Let `R` be the set of `RowSecurityRule`s on the source (every role), `C(r)`
the columns rule `r`'s expression reads (`sql_expr.expression_columns`), and
`G` the grain.

1. **Creation:** refuse with 400 unless `C(r) ⊆ G` for every `r ∈ R`. The
   message names the first offending role and column. A rule whose
   expression cannot be translated at all refuses too (fail closed, as
   `_translate_rls` already does).
2. **Read-time RLS:** `core.rls.resolve_rls_expr(db, user, dataset_id)`
   follows `aggregate_of_dataset_id` and returns the *source's* rule for the
   caller's role. The expression references grain columns, which exist on the
   aggregate with the same names, so `apply_rls_filter` / the DuckDB predicate
   apply unchanged. Admin bypass is inherited from the same function.
3. **Read-time column security:** `resolve_denied_columns` follows the same
   link. A denied source column `x` denies, on the aggregate, `x` itself (if
   in the grain) and every measure derived from `x` (`x_sum`, `x_min`, …),
   read from `aggregate_spec`. `row_count` is never denied.
4. **Later misfit rule:** if a rule is added to the source whose `C(r) ⊄ G`,
   a read by that role finds a rule referencing a column the aggregate lacks.
   `apply_rls_filter` already fails closed on that (zero rows); the DuckDB path
   declines and falls to pandas, which fails closed. The next scheduled or
   manual refresh re-checks rule 1 and, on failure, records it the way every
   scheduler failure is recorded — a `ScheduleFailure` row (`kind="dataset"`,
   `item_id`, `last_error`, attempts and backoff) via `record_failure` — with a
   message naming the role and column. `GET /datasets/{id}/aggregates`
   surfaces that row's `last_error`, and the Aggregates tab shows it. The
   aggregate keeps serving other roles.
5. **Export policy** is copied from the source at creation, as
   `materialize_dataset` does.
6. **Who may create:** `require_dataset_capability(db, user, source_id,
   "data")` — the same gate as materialize.

## Surfaces

Backend (`routers/datasets.py`):

- `POST /datasets/{id}/aggregates` — body `{name, grain: [str],
  measures: [{column, agg, name?}], refresh_interval_minutes?}`. Validates,
  compiles, creates the dataset, runs the first refresh synchronously (so the
  response carries row count and a real error if the source rejects the SQL),
  returns the new dataset.
- `GET /datasets/{id}/aggregates` — the aggregates of a source, with their
  spec, last refresh and any refresh error.
- `GET /datasets/{id}/aggregate-preflight` — for the UI: the source's RLS
  columns (which the grain must include), the columns eligible as grain and
  as measures.
- Deletion: the ordinary dataset delete.

Frontend: on a DirectQuery dataset's page, an **Aggregates** tab. Grain
picker with the RLS columns pre-selected and locked (with the reason shown),
measure picker restricted to numeric columns and the four aggregations, a
schedule field, a list of existing aggregates with their refresh state. The
tab copy says measures are pre-aggregated and that averages are
`sum / row_count`.

## Tests

- **Compilation** pins the SQL for a grain of two columns and three measures,
  the reserved `row_count`, identifier quoting, and refusal of a disallowed
  aggregation or an unknown column.
- **Creation refusal** names the role and column when an RLS rule reads a
  column outside the grain; passes when the grain covers it.
- **Value test — the security property.** A source with rows for tenants A
  and B and a rule per role; an aggregate over `tenant × day`; a user in
  role A reads the aggregate and gets only A's rows and totals. Sabotage:
  removing the `aggregate_of_dataset_id` redirect in `resolve_rls_expr` makes
  the same read return both tenants — the test fails.
- **Denied measure inheritance:** a role denied `amount` cannot see
  `amount_sum` on the aggregate; `row_count` remains.
- **Later misfit rule:** add a rule on a non-grain column after creation; that
  role reads zero rows; refresh sets the named error; another role still reads.
- **Scheduler:** an aggregate with an interval is picked up by the existing
  due-item scan and refreshed through `rewrite_dataset_file`.
- **Cascade:** deleting the source deletes the aggregate.
- **Live:** the 10M-row bench table (`bench_directquery.py --keep`) as a
  DirectQuery dataset, aggregated to `order_date × region`, a dashboard on the
  aggregate timed cold and warm against the scale targets, then dropped.

## Follow-ups from the whole-branch review (2026-09-13)

Deliberately not in the merge; each is a ticket, in priority order:

1. **Consumption-side disclosure.** The tab says measures are pre-aggregated;
   the report builder does not. `avg` over `amount_sum` is an average of sums,
   and `count` counts groups, not rows — a KPI can read "2 orders" where the
   truth is 5, with no error. `DatasetOut` already carries `aggregate_spec`:
   badge the dataset in the builder and warn when `avg`/`count`/`count_distinct`
   is chosen over a measure column. Spec-level gap, not an implementation one.
2. **Export policy is copied, which contradicts "never copy, always resolve".**
   Make the export-disabled check follow `aggregate_of_dataset_id` the way
   `_dataset_has_security` now does, and drop the copy at creation.
3. **A `default_filter_expr` on the source is neither applied nor refused** at
   creation; the source itself refuses to render with one. Refuse at create.
4. **The security fixture never takes the DuckDB path** (no sidecar); add a
   variant with a sidecar and pushdown on — it is the path production uses.
5. **No Edit/recompile endpoint**, though `aggregate_spec` is kept for one;
   today a changed source query means delete and recreate.
6. **Migration tests** compare table names only and never run `downgrade`.
7. **The `row_count` grain test pins check ordering, not the fail-open.** The
   compile test's known columns do not include `row_count`, so it proves
   "reserved beats unknown column"; add a case where the source really has a
   `row_count` column.
8. **`ScheduleFailure` rows outlive their dataset.** The table is keyed
   `(kind, item_id)` with no FK; deleting a source leaves its row and each
   cascaded aggregate's row behind. Nothing reads them, but nothing reaps them.
9. **Deleting a `DataSource`** (`routers/data_sources.py`) cascades every
   dataset and aggregate with no file cleanup at all; wider than the dataset
   delete fixed in the merge.
10. **Any change to `compile_aggregate_sql`'s output** flags every existing
    aggregate as "query changed" until rebuilt. Intended semantics, but the
    recompile endpoint (item 5) is what makes it cheap to act on.

## Follow-up design (approved 2026-09-13)

The ten follow-ups above plus one item from the row-security work, decided
one per ticket. Plan: `docs/superpowers/plans/2026-09-13-aggregate-followups.md`.

1. **Disclosure in the builder.** Frontend only; `DatasetOut.aggregate_spec`
   is already delivered. A "Pre-aggregated" tag beside the dataset name in the
   report builder's Datasets sidebar and in the widget's Dataset select, with
   the copy "measures are pre-aggregated; an average is `x_sum / row_count`".
   Under the aggregation select, when the dataset is an aggregate and the
   chosen measure is a derived measure or `row_count`: `avg` warns "average of
   sums, not of rows: use sum(x_sum) / sum(row_count)"; `count` and
   `count_distinct` warn "counts groups, not rows: use sum(row_count)". Warn,
   never block: a widget on an aggregate is an author's decision.
2. **Export policy resolves, never copies.** `_exports_disabled` callers pass
   the policy-bearing dataset: the aggregate's SOURCE, found through
   `core.rls._aggregate_source`, for an aggregate. The copy of
   `__exports_disabled__` at creation is removed. Existing aggregates keep the
   copied key; it is no longer consulted.
3. **Default filter on the source.** `create_aggregate` refuses with 400 when
   the source has a `default_filter_expr` ("the source has a report-level
   filter expression; an aggregate would ignore it"), since the source itself
   refuses to render with one. `refresh_one` re-checks and records the failure
   the way the grain check does; the aggregate is not rewritten.
4. **Security fixture on the DuckDB path.** The value tests in
   `test_aggregate_security.py` run in two variants: as today, and with a
   parquet sidecar written and `widget_duckdb_pushdown` on, a spy asserting
   DuckDB answered. Same assertions, both engines.
5. **Edit and rebuild.** `PUT /datasets/{source_id}/aggregates/{agg_id}` with
   body `{grain?, measures?, refresh_interval_minutes?}` (omitted fields keep
   the stored spec): same gate as create, every creation check re-run against
   the CURRENT source (grain covers RLS, no default filter, allowlist, interval
   floor), recompile, synchronous `rewrite_dataset_file`, row cap and quota,
   `DatasetColumn`s replaced from the new frame, `clear_failure`, audit.
   Frontend: Edit on each row of the Aggregates tab (the create form,
   prefilled) and a Rebuild button on a row whose `last_error` says the
   query changed (PUT with an empty body).
6. **Migration tests.** `test_alembic_migrations.py` gains a round trip:
   upgrade head, downgrade base, upgrade head, on SQLite; and the
   create_all-vs-alembic comparison widens from table names to the set of
   `(table, column)` pairs.
7. **`row_count` grain pin.** `test_aggregates_compile.py` gains a source whose
   known columns include `row_count`; the grain refusal must still fire.
8. **Orphaned `ScheduleFailure` rows.** `delete_dataset` deletes the failure
   rows of the dataset and of each aggregate it cascades. A startup reaper,
   `reap_orphaned_failures(session)`, beside `reap_stuck_sync_runs`, deletes
   `kind="dataset"` rows whose `item_id` no longer exists.
9. **Data source delete.** Inapplicable: `Dataset.data_source_id` is ON
   DELETE SET NULL, so no dataset cascades with its connection; a connection
   delete must not remove datasets users built on. The re-review's claim was
   wrong. No change.
10. Covered by 5.
11. **Overlap notice on the Row security form.** Backend
    `GET /admin/row-security-rules/preflight?role_id&dataset_id&filter_expr`
    (org admin) returns `{"columns": [...], "denied": [...]}`: the columns the
    expression reads, via `sql_expr.expression_columns` (the parser evaluation
    uses), and those among them that the role's column rules deny on that
    dataset. The modal calls it as the expression settles and shows a
    non-blocking notice: "This rule reads `tenant_id`, which this role cannot
    see. The rule still applies: the role gets the rows it selects and never
    the column." No frontend parser: a second parser would drift from the one
    that evaluates rules.

### After the final review

Found by the final whole-branch review of this plan and its fix wave
(`.superpowers/sdd/2026-09-13-aggregate-followups/`); none block ship.

12. **Preflight under-reports on import-mode datasets.**
    `admin.rule_preflight` names what `sql_expr.expression_columns` (the SQL
    translator's own parser) can read. An import-mode dataset's rule is
    evaluated by pandas, not translated to SQL, and pandas' `.eval()` accepts
    a wider grammar -- function calls, `%`, `**`, chained comparisons -- that
    the translator rejects outright. Such an expression reports `columns: []`
    today, understating what the rule actually reads. Wanted: a pandas-side
    column extraction for import-mode datasets, so the preflight is honest
    about both engines.
13. **Edit or removal of a measure orphans widgets bound to it.** Nothing
    warns before save: a widget referencing a measure that Edit drops, or
    renames via a changed default (`column`/`agg` pair), silently breaks with
    no error at save time -- only later, when the widget renders. Warn before
    save.
14. **`AdminExportPolicy` should render an aggregate's policy as inherited.**
    `GET /datasets/{id}/export-policy` now returns `inherited_from` (Commit C
    of the fix wave); the admin screen does not yet consume it. Wanted: show
    the policy as inherited from the source and disable the toggle, the way
    the Aggregates tab already shows governance as resolved, not owned.
15. **`services/delivery.py` performs no export-policy check.** Pre-existing,
    unrelated to this wave: a scheduled delivery is not itself an export
    format this design's policy gates, but the gap was never closed either.
16. **Postgres `downgrade()` paths are unexercised.**
    `test_alembic_migrations.py`'s upgrade/downgrade/upgrade round trip
    (Commit B of the fix wave) runs on SQLite, in batch mode, only -- the
    Postgres `downgrade()` bodies (plain `ALTER`, no batch rewrite) have no
    equivalent test against a real Postgres engine.
17. **The RLS-grain guard is still invisible for an unscheduled aggregate.**
    `aggregate_staleness` covers the default-filter and query-changed checks
    for the Aggregates tab; the grain-coverage check stays in `refresh_one`
    because it needs the source's rules. An unscheduled aggregate whose source
    gains a rule outside the grain shows nothing in the tab (reads for that
    role fail closed, so no leak). Closing it is one `_source_rules` query per
    source in `list_aggregates`.

## Out of scope

Transparent rewriting of widgets to a matching aggregate (option B; revisit
only once real aggregates exist to learn from). Incremental refresh (an
aggregate is recomputed whole on each refresh; a partition-by-date refresh is
a later optimisation with its own correctness questions). Non-SQL sources.
