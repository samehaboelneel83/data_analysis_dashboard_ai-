# Three-Way Gap Analysis — datalytics vs SAS Visual Analytics vs Power BI

**Date:** 2026-08-17
**Status:** Reference document — no implementation implied
**Supersedes:** `docs/superpowers/specs/2026-08-13-platform-roadmap.md`

## Purpose

This app's feature list has been driven by two SAS Visual Analytics course transcripts
(`COURSE_1_narrations.txt` — VA 1: Basics; `COURSE_2_narrations.txt` — VA 2: Advanced) and, more
recently, by a Power BI feature-parity audit. Neither source gave a single view of where the app
actually stands, and the SAS side had never been scored at all.

This document scores every discrete capability across all three products so the next build decision
is made against evidence rather than against whichever vendor's checklist was open at the time.

## What has shipped since the 2026-08-13 roadmap

### Verification pass, 2026-08-22

Every category was re-checked against the code from 01 onward, rather than only the rows
recently touched. What was actually done, so the confidence level is explicit:

**Mechanical, exhaustive:**
- All **45 file references** the document makes resolve to files that exist.
- All **100 symbols** it asserts (functions, config keys, class names) are present in the
  codebase.
- All **52 config keys** `WidgetConfigPanel` writes have a consumer that reads them. This
  is the check that catches the Card-class defect — a control that looks configured and
  is wired to nothing. Zero orphans.

**Per category:**
- **01** verified: 5 SQL dialects plus an API source, `Dataset.mode`, scheduled refresh
  with its advisory lock, `cache_ttl_seconds`, `Report.revision`, and the PWA manifest,
  service worker and three icons all present. No embed surface exists, so that row's No
  is right.
- **03** counts confirmed against the evaluator: 45 functions total — 17 text, 10
  aggregations, 7 group-relative, 6 window — and `DAY`, `DATETRUNC`, `YTD`,
  `SAMEPERIODLASTYEAR`, `YOY_GROWTH` all exist as claimed.
- **04** is verified *empirically*, not by inspection: the demo content builds all 42
  widget types and asserts each returns a non-empty result through the real widget-data
  path.
- **05** confirmed genuinely empty. An initial grep appeared to find geo code; it was
  matching "geo" inside `PageOut`. There is no mapping capability.
- **06** confirmed: `analytics.py` computes descriptive statistics only. No ML,
  forecasting, network analysis or NLP exists, so 18 No rows are right.
- **07, 13** were verified during the 2026-08-21 phase and again by driving the app.
- **11** updated 2026-08-22 with the first export rows.

**Not verified this pass:** every individual Yes row in 02, 08, 09, 10 and 12 was checked
for the existence of its named component, not driven end to end. Existence is weaker
evidence than behaviour — the Card row read Yes for weeks while the widget rendered
nothing — so those rows carry the weaker guarantee, and the config-key check above is
what partially compensates.


### Shipped 2026-08-22 (not scored below)

Two items landed that this table has no row for. They are recorded here rather than
scored, because inventing a row to claim credit would move the denominator and the
headline percentage along with it:

- **Demo content.** `POST /api/v1/demo/seed` and a "Load demo content" button fill an
  org with five datasets and five reports covering **all 42 widget types**, plus display
  rules of all three kinds, a calculated column, a measure, column formats, table chrome,
  interactions and a DirectQuery dataset over SQLite. Its coverage test derives the
  expected set from the `WidgetType` union, so a newly added widget fails the demo until
  it is covered. Building it found two shipped-but-broken features — see the Card row in
  category 04 and the note below.
- **MCAIT design system.** Adopted as a token bridge: the app's own custom properties are
  redefined in terms of MCAIT's, so all 46 components took the brand at once. Brought a
  visible focus ring the app had never had (see category 13).

Two defects found by that work and fixed, neither of which changes a score because both
rows already read Yes — they were simply not true:

- the **Card widget** rendered zero rows for every card configured through the UI
- the **dual-axis and comparative charts** ignored `dimension_granularity` entirely, so
  "group by month" plotted one point per raw row


That roadmap named 8 sub-projects. Its factual claims are now partly wrong — most importantly it
states "No auth/user system at all", which has since been contradicted. Current status:

| Roadmap sub-project | Status now |
|---|---|
| 1. Row-Level Security (+ Auth foundation) | **Shipped** — JWT auth, `Organization`/`Role`/`User`, `RowSecurityRule` with fail-closed evaluation and SQL pushdown (`backend/app/core/rls.py`, `services/sql_expr.py`) |
| 2. Expression / Calculation Engine — Advanced | **Partial** — time-intelligence functions landed (`YEAR`/`QUARTER`/`MONTH`/`DAY`/`DATETRUNC`/`YTD`/`SAMEPERIODLASTYEAR`/`YOY_GROWTH`), and **post-aggregation measures shipped 2026-08-17** (`Dataset.measures`, `services/measure_eval.py`, `TOTAL()`). Text functions, periodic functions, `AggregateTable`, `AggregateCells`, per-intersection scope, data joins and aggregated data sources are all still absent |
| 3. Interactivity & Navigation (Parameters, Links) | **Partial** — drillthrough pages (button *and* right-click context menu), tooltip pages, page-navigation buttons and bookmark-apply buttons shipped. Parameters, report links, external URL links and set-prompt-bar-values did not |
| 4. Display Rules & Alerts | **Rules shipped 2026-08-18, authoring for all three kinds closed 2026-08-21** — expression, value-map and interval rules targeting mark, background or visibility (`services/display_rules.py`), plus report-level rules (`Report.display_rules`), on top of the per-column display *formats* that shipped earlier (bar / badge / trend / colour scale / icon set). `DisplayRulesPanel.tsx` now authors all three rule kinds, closing the value-map/interval authoring gap phase 1's review had left — and, after the 2026-08-21 whole-branch review found the two new editors emitted rules pointed at an unchangeable text column, every kind now carries a Column control (re-verified 2026-08-22). It is reachable both per widget and as a report-level pane (category 10). **Alerts are still not started** — no threshold-triggered notification of any kind exists |
| 5. Containers & Object Templates | **Not started** |
| 6. Sharing & Managing Reports | **Not started** — no export of any kind, no scheduling, no email |
| 7. Advanced Analytics / ML | **Not started** |
| 8. Custom Graph Builder | **Not started** |
| 9. Geo Maps (unordered) | **Not started** |

Work not on that roadmap that also shipped: the application shell (Report/Data/Model views,
page-size presets, status bar with zoom, mobile layout, tab order, performance panel), side panes
(slicer widget, selection pane, sync slicers, bookmarks), hierarchy drill-down with breadcrumbs,
DirectQuery mode, the Fields pane, and 13 additional chart/control types.

## How to read this

Per capability, one status per product:

| Status | Meaning |
|---|---|
| **Yes** | Shipped and broadly comparable to the strongest implementation in the row |
| **Partial** | Real but narrower — the note says *how* it is narrower |
| **No** | Verified absent |
| **Platform** | Vendor infrastructure, not a reproducible application feature (see exclusions) |
| **Add-on** | SAS column only — requires Visual Statistics / VDMML / Visual Forecasting |

datalytics claims are verified against the cited file paths. SAS claims are verified against the
cited transcript sections. **The Power BI column reflects Power BI Desktop + Service as of early
2026**; where a capability is gated behind Premium/Fabric capacity the note says so, and where my
confidence is lower than the other two columns the note says that too.

### Excluded as SAS-Viya platform, not app features

Scored `Platform` rather than counted as datalytics gaps: CAS internals and CASL/CAS actions, SAS
Environment Manager configuration, the `sas-viya` CLI and transfer plug-in, SAS Studio jobs behind
the job-content object, Model Studio / Model Manager handoff, ASTORE and DATA-step score code, SAS
Infrastructure Data Server template storage, Esri account/credit billing, and SAS for Microsoft 365.

### Excluded as author guidance, not features

COURSE_2's final lesson — Choose the Best Chart, Choose the Best Control, Consider the Layout,
Draft a Plan, Test Test and Test Again — is report-design pedagogy with no code deliverable.
**Accessibility Tips** and the **Report Review Pane** from that same lesson *are* scored, in
categories 13 and 12, because both describe checkable product behaviour.

---

## 01 — Platform & connectivity (15 rows)

| Capability | datalytics | SAS VA | Power BI | Note |
|---|---|---|---|---|
| In-memory analytic engine | Partial | Yes | Yes | datalytics evaluates in-process with pandas per request plus an LRU result cache (`services/widget_data.py`); SAS uses CAS (multi-threaded Controller/Worker); Power BI uses VertiPaq columnar compression. No distributed engine here. |
| Import / materialised mode | Yes | Yes | Yes | `Dataset.mode == "import"`; upload is materialised to CSV. |
| Live query against source DB | Yes | Partial | Yes | `Dataset.mode == "directquery"` with aggregate pushdown (`services/direct_query.py`). SAS requires the table to be loaded into CAS first — there is no per-visual live SQL to an external DB from VA itself. |
| Mixed / composite models | No | No | Yes | Power BI can combine import and DirectQuery tables in one model. Not planned: it requires a query planner that can split one visual's query across two engines and join the results, which is a different architecture from the per-dataset mode flag here. SAS does not do this either. |
| File upload formats | Yes | Yes | Yes | `.csv`, `.xlsx`, `.xls`, `.json` always, plus `.parquet` only when pyarrow imports successfully (`services/analytics.py:12-17`); SAS takes text, SAS datasets, Excel. |
| SQL database connectors | Yes | Yes | Yes | 5 dialects (`services/connections.py`), **all five now usable for DirectQuery** — sqlserver was added 2026-08-17 via `OFFSET/FETCH` instead of `TOP n`. **2026-08-23: a visual query builder** (Connections → Query builder) now compiles a table/joins/aggregations/filters model to dialect-correct SQL for every connection type, with identifiers membership-checked against the live schema rather than escaped, and saves the result as an import or DirectQuery dataset. **2026-08-24: a declarative connector registry** (`services/connectors.py`) turns the connection surface into data: a catalog of **43 connectors** grouped by category, resolved to one of the five SQL families at the dispatch sites while the SQL builders stay untouched (the five originals produce byte-identical URLs and SQL). Most named entries are **wire-compatible reuse of the bundled drivers** — Redshift/Aurora-PG/AlloyDB/CockroachDB/TimescaleDB/Citus/Greenplum/Yugabyte/Neon/Supabase over psycopg2; MariaDB/TiDB/SingleStore/PlanetScale/Vitess/OceanBase over pymysql; Azure SQL/Synapse over pymssql — plus **DuckDB bundled as a real in-process analytics engine** (verified end-to-end), a **generic SQLAlchemy-URL** connector for the long tail, and five **driver-gated cloud warehouses** (Snowflake/BigQuery/Databricks/ClickHouse/Trino) that surface a precise "install driver X" message and a URL fallback rather than a dead end. `type` is now validated on write (unknown → 400), the frontend renders the dropdown and forms from a `GET /data-sources/connectors` catalog (new connectors are backend-only), and connections are SSRF-guarded (`services/net_guard.py`: cloud-metadata IPs always blocked, private ranges gated by `connector_allow_private_hosts`). **Honest scope:** this is broad wire-reuse + a generic escape hatch + documented install paths, **not 100 bespoke integrations**; wire-compatible ≠ feature-identical, so histogram/correlation pushdown stays Postgres-family-only and percentile still excludes sqlserver (members lacking `CORR`/`WIDTH_BUCKET`/`PERCENTILE_CONT` carry capability overrides to avoid silent wrongness). **2026-08-24: connection secrets are now encrypted at rest** — `services/secrets.py` Fernet-encrypts the `password`/`token`/`api_key` fields of `DataSource.config` (key derived from `secret_key`, overridable via `connector_secret_key`), decrypting only when a live connection is built (`build_url` / `_api_request`) and redacting them on the wire; marker-prefixed so legacy plaintext rows keep working and re-encrypt on save, and an update that echoes the redaction sentinel keeps the stored secret. The generic SQLAlchemy-URL connector is the documented exception (its embedded credentials live in the free-form `url`). |
| REST / HTTP API source | Yes | Partial | Yes | `api` source type via httpx. |
| Scheduled data refresh | Yes | Platform | Yes | **Shipped 2026-08-17.** Per-dataset `refresh_interval_minutes` with an in-process loop guarded by a per-dataset `pg_try_advisory_lock`, so N uvicorn workers cannot refresh the same dataset simultaneously. No scheduler dependency added. 5-minute floor; DirectQuery and source-less datasets excluded. SAS schedules CAS loads outside VA. |
| Query result caching with TTL | Yes | Platform | Partial | Per-source `cache_ttl_seconds`; cache key includes the verbatim RLS expression so restricted and unrestricted results can never share an entry. |
| Progressive Web App install | Yes | Yes | No | **Shipped 2026-08-17.** Manifest plus 192/512/maskable icons and a service worker (`frontend/public/`). The worker never caches `/api/` responses, which are per-user and RLS-filtered, and is network-first for navigations so a deploy is never served a stale shell. Power BI ships a desktop app instead. |
| Native mobile app | No | Yes | Yes | datalytics has a responsive stacked mobile *layout* (`MobileLayoutEditor.tsx`) plus PWA install, which covers the install-to-home-screen case. A true native app is **deliberately not planned** — it needs a second codebase and app-store distribution, neither of which this rebuild targets. |
| Multiple reports open at once | No | Yes | Partial | One report per route. **Deferred deliberately**: browser tabs already give this, and an in-app tab bar would mean holding N report states plus N cross-filter providers in one page — a large refactor of `ReportBuilder` for something the browser does natively. SAS needs its own because its session is server-side. |
| Autosave & crash recovery | Yes | Yes | Partial | **Re-scored 2026-08-17 — this row was wrong.** datalytics has no explicit save and no dirty state: every mutation PATCHes immediately (widget drag on mouseup, config and page props on a short debounce), so there is nothing held locally to recover. SAS needs an autosave safety net precisely because it *does* hold unsaved changes. The only exposure is the ~600 ms debounce window on config edits. Different model, same outcome, so scored Yes rather than as a gap. |
| Save-conflict detection | Yes | Yes | Partial | **Shipped 2026-08-17.** `Report.revision` is bumped by every mutation including nested page/widget/bookmark changes; the builder polls `GET /reports/{id}/revision` and shows a non-blocking Reload banner when it moves. Warns rather than blocks, since with continuous autosave the other session's change is already saved. SAS instead blocks at save time and offers overwrite or Save As. |
| Embeddable SDK / iframe embedding | No | Yes | Yes | SAS Viya SDK for JavaScript; Power BI Embedded. |

## 02 — Data preparation (19 rows)

| Capability | datalytics | SAS VA | Power BI | Note |
|---|---|---|---|---|
| Automatic column type detection | Yes | Yes | Yes | `detect_types` — numeric / datetime (>80% parse) / categorical / text (`services/analytics.py:35`). |
| User-changeable item classification | Yes | Yes | Yes | **Shipped 2026-08-17.** `Dataset.column_meta[col].role` overrides the detected dtype, so a numeric ZIP sits under Dimensions rather than being offered as something to sum. Detection stays the source of truth for `dtype` — this only overrides it, so a re-upload cannot strand an override. **2026-08-23:** the override gained its authoring surface — a reclassify toggle on numeric field chips flips measure↔category in place, removing the override when it matches detection again. |
| Persistent default aggregation per measure | Yes | Yes | Yes | **Shipped 2026-08-17.** `column_meta[col].aggregation` is applied when the column is assigned to a measure role. Applied client-side at assign time rather than at query time, so the result is visible and editable in the widget config panel instead of being an invisible server-side default. |
| Per-column display format | Yes | Yes | Yes | `Dataset.column_formats` → number/integer/currency/percent/bar/badge/trend/colourscale/icon (`ColumnFormatsPanel.tsx`). SAS offers 30+ currency formats. |
| Bulk property edits across items | Yes | Yes | Partial | **Shipped 2026-08-17.** `PUT /column-meta` replaces the whole map, so changing N columns is one request — and a property is cleared by omission rather than needing a separate delete. |
| Duplicate a data item | Yes | Yes | Yes | **Shipped 2026-08-22.** Any column duplicates as an identity calculated column (`` `col` `` through the ordinary calc engine), carrying its own default aggregation and format while reading the original's values. Names count up so duplicates stay distinguishable. |
| Show / hide data items | Yes | Yes | Yes | **Shipped 2026-08-17.** `column_meta[col].hidden` removes a column from the Fields pane without deleting it. |
| Group category values into custom categories | Yes | Yes | Yes | **Shipped 2026-08-17.** `CustomCategoryPanel` lists a column's distinct values and assigns them to named groups, compiling to `SWITCH(col, v, name, …, 'Other')` for the existing calculated-column engine — so the result is an ordinary column everywhere, with no new backend code. |
| Bin numeric values into intervals | Yes | Yes | Yes | **Shipped 2026-08-17.** Same panel, chosen automatically for numeric columns: a bin count derives evenly spaced edges from the column's min/max and compiles to ascending nested `IF`s. The top interval is closed when the last edge is the true maximum, so asking for 2 bins gives 2 buckets rather than a third holding only the max. |
| User-defined hierarchies | Yes | Yes | Yes | `HierarchyNode` self-referencing tree with a tree editor (`HierarchyTree.tsx`). |
| Auto-generated date hierarchy | Yes | Yes | Yes | `POST /{id}/hierarchy/auto-generate` builds Year→Quarter→Month→Day. |
| Reusable data view / semantic bundle | Yes | Yes | Partial | SAS data views bundle names, formats, classifications, aggregations, filters, hierarchies, calc items and custom categories for reuse across reports, with user- and admin-level defaults. Power BI's shared semantic model is the closest analogue. **Shipped 2026-08-23.** A named `DataView` bundles a dataset's semantic layer — roles/aggregations/labels/hidden, formats, calc columns (custom categories compile to these), measures, filter, prep steps, hierarchy — org-wide. Apply matches by column name and reports every skipped piece with the columns it needed; reserved __keys never travel and the target's own survive, so a bundle can't become a governance bypass. No user/admin default levels — a bundle is applied deliberately, not imposed. |
| Cross-source column mapping | Yes | Yes | Yes | `Relationship` rows exist and drive Model view. **Completed 2026-08-23:** cross-filters now translate through the modelled relationship — a filter arriving from another dataset is renamed to this dataset's mapped column when the local one is absent, so actions cross sources; unmodelled pairs stay no-ops, the honest outcome. |
| Auto-correlation hints between measures | Yes | Yes | No | **Shipped 2026-08-17.** A ≈ badge on each field in the Fields pane naming the measures it moves with, ordered by magnitude, from the Pearson matrix `analyze_numeric` already produced. Uses SAS's stated ±0.6 threshold and its 150-measure cutoff; the small-sample threshold is this app's choice since SAS does not state one. |
| Automatic outlier detection & impact | Yes | Yes | No | **Completed 2026-08-23.** The ⚠ badge (shipped 2026-08-17) now opens the details SAS pairs with it: box-plot stats with the 1.5×IQR fences, the outlier rows themselves, and an impact assessment — share of the column total the outliers carry, and the mean with versus without them — computed on the same secured frame every widget reads (denied columns 404). Report-level Insights remain out of scope; the row's named capability (detection + details + impact) is here. |
| Step-based transformation editor | Yes | Partial | Yes | Power Query/M is Power BI's decisive advantage here. **Shipped 2026-08-23.** An ordered, persisted prep pipeline (`services/prep.py`, editor in the Data tab): dedupe, drop/fill nulls, trim, case, replace values, rename, retype, split, filter rows, remove columns, group & summarise — applied to EVERY read of an import dataset (widgets, exports, digests, alerts, profiling) at load → security → RLS → prep → filter → calc. Non-destructive: the file is never rewritten, so removing a step undoes it. Validated hard at save time against a column set that evolves through the pipeline; fail-soft at apply time. Narrower than M (no custom functions, no query folding), but the step-editor capability this row names is here. |
| Source-table cell editing | Partial | Yes | No | SAS's source table editor edits cells, replaces values, inserts/deletes columns and saves back to CAS. **2026-08-23:** the prep pipeline's replace-values, rename and remove-columns steps cover the value-correction half non-destructively. Partial, not Yes: there is no per-cell editing and nothing writes back to the source file — deliberately, since non-destructive steps are undoable and the SAS behaviour is not. |
| Data joins in the report layer | Yes | Yes | Yes | SAS supports left/right/inner/full as a temporary table re-run on every report open. **Shipped 2026-08-23.** A `join` prep step merges another same-org import dataset (left/right/inner/full, one key per side, `_2` suffix on collisions), re-run on every read like SAS's temporary table. The joined dataset's own RLS, column mask and prep all apply to its frame — as the requesting identity — before the merge, so a join can never widen what a restricted role sees. Joined reads bypass the result cache (the key cannot see the other file's mtime). |
| Aggregated / pre-summarised source | Yes | Yes | Yes | **Shipped 2026-08-23.** The prep pipeline's group & summarise step pre-aggregates the dataset at load time (group-by columns + sum/avg/min/max/count/median/nunique with output names), and because it runs before calc columns and measures, downstream aggregation over the summarised frame — SAS's nested aggregated measures — works as ordinary widget aggregation. Applied after RLS, so the summary only ever includes rows the viewer may see. |

## 03 — Calculation engine (23 rows)

| Capability | datalytics | SAS VA | Power BI | Note |
|---|---|---|---|---|
| Row-level calculated columns | Yes | Yes | Yes | `Dataset.calculated_columns` JSON, evaluated by `apply_calculated_columns`. |
| Post-aggregation measures | Yes | Yes | Yes | **Completed 2026-08-23.** `Dataset.measures` + `services/measure_eval.py` evaluate a named expression at the requesting widget's grouping grain, with `TOTAL()` for grand totals. Coverage now spans the shape_series family, the scalar KPI path, the multi-measure card (a measure name beside raw columns just works), and crosstab INTERSECTIONS — evaluated per (row, column) cell, with row subtotals and column/grand totals RE-EVALUATED at their own grain rather than summed (a ratio's row total is not the sum of its cell ratios). Measure-on-measure references are still rejected at save time; DirectQuery pushdown of measures remains absent (the DirectQuery mode refuses measures loudly rather than approximating). |
| ByGroup / ForAll aggregation context | Yes | Yes | Yes | **Completed 2026-08-23.** Measures derive their group context from the widget's dimension (SAS's ByGroup) and `TOTAL()` is its ForAll — and now `BYGROUP(expr, "col", ...)` declares a DIFFERENT grouping context per aggregation WITHIN one expression: `SUM(sales) / BYGROUP(SUM(sales), "region")` is each group's share of its region, re-basing per region whatever the visual groups by. Evaluated by AST rewrite at its own grain and broadcast to the outer group index (like TOTAL, but a Series not a scalar); nesting either context inside the other is refused, as is BYGROUP at grand-total grain. Authored from the measure editor's Grouping-context palette. Row-level `GROUPSUM`/`GROUPAVG` in calculated columns remain fixed at definition time by design — that is the row-level engine, not the measure engine this row is about. |
| Scoped expression per data crossing | No | Yes | Partial | SAS defines a base expression plus per-intersection overrides. Power BI approximates with `ISINSCOPE`. |
| Expression sandbox / injection safety | Yes | Platform | Platform | AST allowlist rejects attribute access and dunder names; `df.eval` resolvers pinned empty; RLS evaluation is **fail-closed to zero rows** (`widget_data.py:805-1004`). Genuinely stronger than a "just eval it" approach. |
| Live expression preview | Yes | Yes | Partial | `POST /{id}/calculated-columns/preview`. |
| Conditional operators | Yes | Yes | Yes | `IF`, `SWITCH`, `isnull`. SAS's `IFELSE` is the same idea. |
| Scalar math & cast functions | Yes | Yes | Yes | 14 names: abs, round, min, max, int, float, str, len, pow, log, sqrt, exp, floor, ceil. |
| Simple aggregations in expressions | Yes | Yes | Yes | 10: `SUM`, `AVG`, `MEDIAN`, `COUNT`, `COUNTD`, `STDEV`, `VARIANCE`, `PCT_TOTAL`, `NORMALIZE`, `ZSCORE`. |
| Running / window functions | Yes | Yes | Yes | 6: `CUMSUM`, `CUMPCT`, `RANK`, `DIFF`, `LAG`, `LEAD`. |
| Group-relative window functions | Yes | Yes | Yes | 7: `GROUPSUM`, `GROUPAVG`, `GROUPCOUNT`, `GROUPRANK`, `GROUPMIN`, `GROUPMAX`, `GROUPPCT`. |
| Text functions | Yes | Yes | Yes | **Shipped 2026-08-17.** 17 functions: UPPER, LOWER, TRIM, LEN, REVERSE, LEFT, RIGHT, SUBSTRING, CONCAT, REPLACE, FIND, CONTAINS, STARTSWITH, ENDSWITH, SPLIT, LPAD, RPAD. Real namespace functions rather than a `.str` accessor, since the validator forbids attribute access — which is why the palette once shipped snippets that could never run. Positions are 1-based and FIND returns 0 when absent, matching SAS and DAX rather than Python. A structural guard test now fails if any palette snippet reintroduces attribute access. |
| Date component extraction | Yes | Yes | Yes | **Completed 2026-08-22.** The three gaps this row named are closed: `WEEKDAY` (SAS's DayOfWeek, 1 = Monday), `DAY` (DayOfMonth) and `HOUR`. `WEEK`, `MINUTE`, `SECOND`, `DAYOFYEAR`, `MONTHNAME` and `DAYNAME` shipped alongside them, all offered in the palette. |
| Date construction | Yes | Yes | Yes | **Shipped 2026-08-22.** `DATEFROMYMD`, `DATEADD`, `DATEDIFF`, `TODAY`, `NOW`. Months and years use `DateOffset`, so 2024-03-31 plus one month is 2024-04-30 and a calendar month boundary counts as one month rather than zero. SAS: `DateFromMDY`, `DateFromYQ`, `DateTimeFromHMS`, `Now`, `DatePart`, `TimePart`. |
| Type coercion between date and number | Yes | Yes | Yes | **Completed 2026-08-22.** `TODATE` turns text or an epoch-day number into a real date — the direction SAS's `TreatAs` provides, and what makes a numeric aggregate render as a date — and `TONUMBER` goes back. The pair round-trips, pinned by a test. |
| Time-intelligence (YTD, prior year) | Yes | Yes | Yes | **Completed 2026-08-23.** The family now spans yearly, quarterly and weekly grains: `YTD`/`QTD`/`WTD` running sums resetting at their boundaries, `SAMEPERIODLASTYEAR`/`SAMEPERIODLASTQUARTER`/`SAMEPERIODLASTWEEK` prior-period lookups, and `YOY_GROWTH`/`QOQ_GROWTH` with zero/missing masked to NaN, never inf. Fiscal calendars remain absent — the honest note, not a Partial: the row's named capability (YTD, prior year, plus period variants) is fully here. |
| Periodic functions with interval/offset/scope | No | Yes | Partial | SAS: 5 functions × 6 intervals, with offset, starting point and scope. |
| Filter-context control inside period calcs | No | Yes | Yes | SAS offers ApplyAllFilters / IgnoreAllTimeFrameFilters / IgnoreInteractiveTimeFrameFilters. Power BI does this with `CALCULATE` modifiers. |
| Advanced statistical functions in expressions | Yes | Yes | Yes | **Extended 2026-08-22.** `PERCENTILE` (0-100 like SAS), `MODE`, `CORR`, `COVAR`, `SKEW`, `KURTOSIS`, `IQR`, `SE`, `COEFVAR`, `CSS`, `FIRST`, `LAST` joined `STDEV`/`VARIANCE`. Of the seven SAS names this row listed, six are now present. **Completed 2026-08-23:** `PVALT` (two-sided one-sample t-test) joined — and the earlier note claiming it needed a scipy dependency decision was wrong; scipy was in requirements all along. All seven SAS names are present. |
| Confidentiality suppression | Yes | Yes | No | SAS's `Suppress` hides aggregates below a threshold, with a `withComplement` mode that also hides the next-closest value so the suppressed one cannot be back-computed. **Shipped 2026-08-23.** `suppress_below` hides categories aggregated from fewer than N source rows (thresholded on ROW COUNT, the small-cell privacy semantic), and the complement option hides the smallest surviving group whenever anything was suppressed. Totals describe only what is shown. |
| Cell-range aggregation in tables | No | Yes | Partial | SAS `AggregateCells` with direction Default/Column/Row/Temporal and `CellIndex(start\|current\|end, offset)`. |
| Cross-crossing table aggregation | No | Yes | Yes | SAS `AggregateTable` with Fixed/Add/Remove group context; Power BI `SUMMARIZE`/`CALCULATETABLE`. |
| Quick one-click calculations | Yes | Yes | Yes | SAS generates an aggregated measure from a right-click; Power BI has quick measures. **Shipped 2026-08-23.** A 'Quick calculation' select on any aggregating widget: percent of total, difference from previous, percent change, rank — applied after HAVING and before the row limit, so top-N pages keep each bar's true share of the whole. |

## 04 — Visual types (45 rows)

| Capability | datalytics | SAS VA | Power BI | Note |
|---|---|---|---|---|
| Bar / column — clustered, stacked, 100% | Yes | Yes | Yes | `bar_mode` config drives all three via `toBarSeries` (`chartRenderers/barSeries.ts`). |
| Line | Yes | Yes | Yes | |
| Area | Yes | Yes | Yes | |
| Step plot | Yes | Yes | No | Power BI needs a custom visual. |
| Combo bar + line | Yes | Yes | Yes | `dual_axis_bar_line`. |
| Dual-axis bar / line / time-series variants | Yes | Yes | Partial | Four separate widget types here and in SAS; Power BI has one combo chart with a secondary axis. |
| Ribbon chart | Yes | No | Yes | **Completed 2026-08-23.** A real ribbon: hand-rolled SVG that rank-orders each period's series (largest on top) and joins segments across periods with flowing connectors — the crossings show rank changes, which is the widget's point and what recharts stacking could not do. RTL reverses period order; display rules address rows_axis positions; labels decimate above ~10 periods. Not a SAS object at all. |
| Waterfall | Yes | Yes | Yes | |
| Funnel | Yes | Yes | Yes | |
| Pie / donut | Yes | Yes | Yes | |
| Treemap | Yes | Yes | Yes | |
| Histogram | Yes | Yes | Partial | Native `shape_histogram` with a bin count; Power BI requires manual binning plus a column chart. |
| Box plot | Yes | Yes | No | Quartiles, whiskers and 1.5×IQR outliers computed server-side. |
| Dot plot | Yes | Yes | No | |
| Needle plot | Yes | Yes | No | |
| Butterfly / tornado | Yes | Yes | No | |
| Bar with target line | Yes | Yes | Partial | **Completed 2026-08-22.** A bar binds a target *column*: aggregated per group with the same function as the measure, drawn as a per-bar tick from the live y-scale, and bars recolour by attainment — yielding to an explicit display-rule fill. Reference and average lines were already present. |
| Scatter | Yes | Yes | Yes | |
| Bubble | Yes | Yes | Yes | |
| Animated bubble (play axis) | Yes | Yes | No | `bubble_change` → `shape_bubble_animated` frames by an animation column. |
| Bubble change plot (start→end vectors) | Yes | Yes | No | |
| Vector plot | Yes | Yes | No | |
| Correlation matrix | Yes | Yes | No | `shape_correlation_matrix`, pushed down as `CORR` on Postgres. |
| Heat map | Yes | Yes | Partial | `shape_heatmap`; Power BI approximates with a matrix plus conditional formatting. |
| Parallel coordinates | Yes | Yes | No | |
| Numeric series plot | Yes | Yes | No | |
| Comparative time series | Yes | Yes | No | |
| Schedule / Gantt | Yes | Yes | No | `shape_gantt`. |
| Word cloud | Yes | Yes | No | `d3-cloud`. Frequency/weight only — no NLP behind it. |
| Gauge | Yes | Yes | Yes | **Completed 2026-08-23.** Five shapes — arc (half donut), speedometer (dial + needle over a 240° band), bullet (Few-style bar with target tick), thermometer, progress bar — selectable per widget (`gauge_shape`), all reading the same value+target result, all honouring display-rule interval fills over the attainment colour. SAS's 6×6 style grid and active-range-only variant are not replicated; the row's capability (multiple gauge shapes) is here. |
| KPI / key value | Yes | Yes | Yes | |
| Card / multi-row card | Yes | Yes | Yes | `shape_card` aggregates each measure independently. **This row was overstated until 2026-08-22:** the panel writes multi-value roles at top level while `_LEGACY_ROLE_KEYS` had no `measures` entry, so every card configured through the UI resolved to no measures and rendered zero rows. Fixed, and pinned by a test over the form the panel actually emits. SAS's key value adds a lattice category for small multiples. |
| Table / list table | Yes | Yes | Yes | |
| Crosstab / matrix | Yes | Yes | Yes | Both `crosstab` and `matrix` widget types map to `shape_series`'s pivot branch. |
| Sparkline inside a table | Yes | Yes | Yes | **Shipped 2026-08-24.** A crosstab/matrix row already holds a series across its (time- or category-ordered) value columns, so a per-row **Trend** column draws that series as an inline SVG sparkline — no new backend shaping. The series is the row's numeric cells excluding the category label and `__total__`; scaled to the row's own min/max so the shape reads at a glance, with an end-point dot. Off by default via a "Row trend sparkline" toggle in the Formatting panel, offered only on crosstab/matrix (a raw table's columns aren't a per-row series). Aligns with row windowing, banding, rule styles and the totals row. Verified live on the Region × Category crosstab. |
| Slicer | Yes | Yes | Yes | Multi-select checkbox list emitting an `in` filter. |
| Text block | Yes | Yes | Yes | |
| Dynamic text bound to a measure | Yes | Yes | Yes | **Completed 2026-08-23.** Text blocks resolve `{{agg(column)}}` placeholders as one KPI query each through the ordinary widget-data path — same filters, cross-filters and RLS as any chart, so prose and chart cannot disagree; `{{@name}}` embeds the live parameter value. Display rules now apply to text exactly as SAS does: each placeholder's KPI result carries the server-evaluated rule styles, and the matched value renders as a coloured span (widget-level background/visibility rules apply to the block). |
| Image | Yes | Yes | Yes | URL-sourced with a Fit mode. |
| Shape | Yes | Partial | Yes | rectangle / rounded / circle / line. |
| Button | Yes | Partial | Yes | Wired to navigate-to-page and apply-bookmark. |
| Web content / iframe | Yes | Yes | Partial | **Shipped 2026-08-24.** A `web_content` widget (Insert → Controls → Web Content) embeds a page in a sandboxed `<iframe>`. Static like image/shape/text — no dataset, no data fetch (`WidgetRenderer` early-returns it). Only `http(s)` URLs become a src; `javascript:`/`data:`/blank fall back to a placeholder, so an author-typed URL can't be an injection vector. The frame carries `sandbox="allow-scripts allow-same-origin allow-popups allow-forms allow-presentation"`, `referrerPolicy="no-referrer"`, `loading="lazy"`; sites that forbid framing (X-Frame-Options / CSP frame-ancestors) simply won't load, which is the remote site's choice. Excluded from cross-filter actions, display rules, and the alt-text/zero-rows review checks (it has no data). Verified live: an inserted widget rendered example.com in the builder canvas. |
| Custom third-party visualisation | Yes | Yes | Yes | **Shipped 2026-08-24.** A `custom_visual` widget binds a dataset (dimension/measure/aggregation, like a chart) and hands its shaped result to an author-supplied page in a **sandboxed iframe** (`allow-scripts`, opaque origin) via a documented postMessage contract: `{ type: "datalytics:data", data }`, sent on load and on every data change. This is SAS's data-driven-content / Power BI's custom-visual model. Only http(s) or a same-origin path is embeddable; the frame can render but cannot reach the app. A reference visual ships at `/custom-visual-demo.html`. Verified live: the sandboxed frame received the region/revenue series and rendered 4 rows. (Selection messages back from the visual are a future addition; v1 is one-way data delivery.) |
| Code-driven visual | No | Yes | Yes | SAS job content runs SAS code; Power BI has R and Python visuals. |
| Visual marketplace | No | Partial | Yes | |

## 05 — Geo & mapping (15 rows)

**First maps shipped 2026-08-22** — choropleth, point and bubble maps over bundled
world-atlas 50m geometry (d3-geo, SVG, offline-first, lazily loaded). Region-mode maps
consume ordinary series output, so filters, RLS and display rules apply with no
geo-specific backend; name matching is alias-aware but never fuzzy, with unmatched rows
surfaced as a visible count. The remaining rows need clustering, layering, shape import
or paid geo services, and stay honestly No.

Nothing in this category exists in datalytics: there is no mapping library in `package.json` and no
map widget type or renderer. This is the largest single contiguous gap against **both** competitors.

| Capability | datalytics | SAS VA | Power BI | Note |
|---|---|---|---|---|
| Region / choropleth map | Yes | Yes | Yes | Power BI Filled map. |
| Coordinate / point map | Yes | Yes | Yes | |
| Bubble map | Yes | Yes | Yes | |
| Cluster map | Yes | Yes | Partial | Azure Maps clustering. **Shipped 2026-08-23.** `map_clusters`: server-side grid clustering (configurable cell size in degrees); each occupied cell renders one marker carrying its point count and summed measure, with the count inside the marker when it fits. |
| Contour / density map | Yes | Yes | No | **Shipped 2026-08-23.** `map_density`: grid-density heat map — the cluster shaper's cells drawn as filled squares, intensity by point count, cell size configurable in degrees. Density, not smoothed contour lines; the row's density half is fully here. |
| Line / polyline map | Yes | Yes | Partial | **Shipped 2026-08-23.** `map_lines`: origin→destination arcs from lat/lon + lat2/lon2 roles, stroke sqrt-scaled by weight, invalid endpoints dropped-and-counted. | Azure Maps line layer. |
| Network map on a geographic background | Yes | Yes | No | **Shipped 2026-08-23.** `map_network`: named nodes anchored at the mean of their observed coordinates, links weighted by the measure, node size by degree, hover lifting a node's links — the network widget's structure on real geography. | |
| Pie map | Yes | Yes | No | **Shipped 2026-08-23.** `map_pie`: a pie per country at its centroid, composition by a slice role, radius sqrt-scaled by total, top-6 + Other so pies stay readable at map scale; hover lists every slice. |
| Multi-layer maps (region + coordinate) | Yes | Yes | Yes | **Shipped 2026-08-23.** `map_layers`: a choropleth region layer and a coordinate point layer from one dataset's roles, on one map; either layer alone degrades to what its roles describe. |
| Custom region shapes | No | Yes | Yes | SAS via a geographic data provider; Power BI Shape map. |
| Geographic name / code lookup roles | Yes | Yes | Yes | SAS: country names, ISO-2/ISO-3/ISO-numeric, subdivisions, US states, US ZIP. |
| Latitude / longitude from data columns | Yes | Yes | Yes | |
| Map background providers | No | Yes | Yes | SAS: OpenStreetMap plus 5 Esri basemaps. |
| Pins, radius areas, direct routes | No | Yes | Partial | |
| Drive / truck / walk isochrones + demographics | No | Add-on | Partial | SAS Esri Premium, credit-billed. |

## 06 — Advanced & augmented analytics (20 rows)

| Capability | datalytics | SAS VA | Power BI | Note |
|---|---|---|---|---|
| Automated explanation of a response variable | Yes | Yes | Partial | SAS produces summary text, a relative-importance bar chart (top factor = 1, rest proportional) and a type-dependent relationship plot, plus optional High/Low group tabs. Power BI's Key Influencers is the nearest thing. **Shipped 2026-08-23.** A ? on every numeric field opens the ranked relative-importance list — numeric factors by \|r\|, categorical by √η², one comparable scale, top = 1 — plus the top factor's relationship (scatter / group means), on the same secured frame widgets read. High/Low group tabs and prose summary are the honest remainder; the row's core (auto importance + relationship plot) is here. |
| Automated prediction with model selection | No | Yes | No | SAS runs logistic regression / gradient boosting / decision tree for a category response (champion by accuracy) or linear regression / gradient boosting / decision tree for a measure (champion by ASE). |
| Interactive prediction input form | No | Yes | No | Change an input, the model re-runs and the prediction updates. |
| Decision tree visual | No | Yes | Partial | C4.5 with an icicle plot; base licence is explanation-only. Power BI's decomposition tree is a drill aid, not a fitted model. |
| Model assessment plots | No | Add-on | No | ROC + cutoff, lift, misclassification, confusion matrix — Visual Statistics only. |
| Interactive tree pruning / split editing | No | Yes | No | |
| Forecasting | Yes | Yes | Yes | SAS auto-selects among ARIMA, damped-trend / linear / seasonal / simple exponential smoothing, and Winters additive/multiplicative. Power BI's Analytics pane offers exponential smoothing on line charts. datalytics has neither. **Shipped 2026-08-23.** A `forecast` widget: exponential smoothing (additive trend; seasonality only with ≥2 full cycles) over the same shaped history a line chart shows. SAS auto-selects among more model families; this is one, honestly. |
| Confidence-interval band | Yes | Yes | Yes | Configurable in SAS, default 95%. **Shipped 2026-08-23.** 95% band from residual spread, widened with √horizon — deterministic so the chart does not flicker its uncertainty, and the demo validator asserts the band widens. |
| Underlying-factor contribution to a forecast | No | Yes | No | Non-contributing measures are discarded; contributing ones narrow the confidence band. |
| What-if scenario analysis | Partial | Yes | Partial | SAS edits future factor values via table or draggable chart. Power BI's what-if parameters are a numeric slider feeding a measure — much narrower. **Shipped 2026-08-23 at exactly PBI's level:** a number parameter with a min/max/step triple renders as a viewer-bar slider; every `@name`-bound widget and `{{@name}}` placeholder follows the thumb. SAS's editable future factor values on a forecast remain absent — Partial, same as PBI. |
| Goal-seeking | Yes | Yes | No | **Completed 2026-08-23.** In the Explain dialog: set a target for the response and Solve answers the required factor value on a linear fit, with r² and an explicit extrapolation flag. Per-factor min/max bounds (SAS's constraint) now ship: a feasible solve confirms it sits within bounds; an infeasible one reports the binding bound and the BEST ACHIEVABLE response there — what a constrained solver actually optimises to. One factor at a time, matching the dialog's one-relationship-at-a-time frame; SAS solves across a forecast model's underlying factors simultaneously, a model datalytics does not have. |
| Network / link analysis | Yes | Yes | No | Ungrouped (source→target) and hierarchical structures, directed or undirected. **Shipped 2026-08-23.** `network` widget: source/target/weight roles, aggregated links, self-loops dropped, nodes capped by degree, seeded deterministic Fruchterman-Reingold layout shipped from the shaper so the same data always lands in the same shape. |
| Automatic network centrality metrics | Yes | Yes | No | Betweenness, closeness and reach centrality, plus community and disconnected-network ID, assignable to Size or Colour. **Shipped 2026-08-23.** Degree, closeness, betweenness (Brandes) and reach per node, computed in the shaper; `centrality_metric` assigns one to node SIZE and the hover readout shows all four. Community detection and colour assignment are the honest remainder — the row's named metrics are all present. |
| Path / flow (Sankey) analysis | Yes | Yes | No | Built from identifier-event pairs with a sequence order; link colour by path, event or drop-off. **Shipped 2026-08-23.** Source→target→weight shaper feeding Recharts' sankey layout; self-loops dropped, node identity split by side. |
| Text topic modelling | No | Yes | No | NLP parse → stop list → term-document matrix → SVD → 2–25 topics, with POS tagging, entity extraction, stemming, and cell weight (none/logarithmic) × term weight (none/entropy). |
| Sentiment analysis | No | Yes | Partial | Optional in SAS, off by default; per-document negative/neutral/positive averaged and rolled up per topic. |
| Natural-language Q&A | No | Partial | Yes | |
| Smart narrative / generated summary | Partial | Yes | Yes | SAS puts a natural-language explanation on a maximise tab for path analysis, text topics and decision trees. **Shipped 2026-08-23:** the insights engine generates a dataset-level narrative from its ranked findings (trends, standouts, correlations, outlier impact, data quality), every sentence carrying computed numbers. Partial: dataset-level template prose, not SAS's per-object analysis narratives. |
| Trend / fit lines | Yes | Yes | Yes | `compute_fit_line` does linear, quadratic, cubic and best-fit (highest R²) via `numpy.polyfit`. SAS adds a penalised B-spline (PSpline) and reports R², slope and the fit function on a details tab. |
| Reference & average lines | Yes | Yes | Yes | `computeAnalyticsLines` — constant reference line with label and colour, plus an average line. Power BI's Analytics pane additionally offers min/max/median/percentile lines and error bars. |

## 07 — Formatting & display rules (28 rows)

| Capability | datalytics | SAS VA | Power BI | Note |
|---|---|---|---|---|
| Per-object title | Yes | Yes | Yes | |
| Per-object alternative text | Yes | Yes | Yes | **Shipped 2026-08-21.** `cfg.alt_text`, authored via the config panel's "Widget description (screen readers)" field (`WidgetConfigPanel.tsx:1038`), is read by `WidgetRenderer.tsx` as the `aria-label` on the widget's `role="figure"` container (`WidgetRenderer.tsx:251-252`) — covered by a passing render test. See category 13. |
| Per-object background / border / padding | Yes | Yes | Yes | **Shipped 2026-08-21.** `widget_background`, `widget_border_color`, `widget_border_width`, `widget_radius`, `widget_padding` are authored in the config panel's Appearance group (`WidgetConfigPanel.tsx:992-1041`) and read by `WidgetRenderer.tsx` for every widget type, ungated by `widgetCapabilities.ts` since container chrome applies regardless of widget shape (background `WidgetRenderer.tsx:265`, border/radius `:261-262`, padding `:330`). A rule-driven background still wins over a configured one (`ruleStyles?.widget?.background ?? cfg.widget_background`), covered by a passing test. Object chrome is background, border, radius and padding. **Data skins remain out of scope** — SAS's eight skins are a visual design system of their own. |
| Data skins / element styling | Yes | Yes | Partial | **Shipped 2026-08-24.** A per-widget `widget_skin` (none / flat / raised / recessed / sheen / gloss / matte — SAS's default/pressed/sheen/gloss/matte/flat set) applied as a box-shadow treatment on the widget container (`SKIN_SHADOWS` in `WidgetRenderer`), so it composes with the author's background/border rather than overriding them. Drag and selection feedback take precedence over the skin. Chosen from a Skin dropdown in the Appearance config section; off ("none") by default, so existing widgets are unchanged. Verified live: a gloss skin rendered its sheen + drop shadow on a chart. Frontend-only (widget config is JSON — no schema change). |
| Report-level theme | Yes | Yes | Yes | 5 palettes (`themes.ts`); `applyTheme` mutates the shared `COLORS` array so every category-coloured chart retints with no renderer changes. |
| Custom / imported theme | Yes | Yes | Yes | **Shipped 2026-08-22.** Org-scoped palettes (`org_themes`), validated #rrggbb, selectable per report as `custom:<id>` beside the built-ins. Power BI theme JSON. |
| Axis label / line / tick styling | Yes | Yes | Yes | **Shipped 2026-08-20.** `x_axis_label`/`y_axis_label`/`axis_tick_size`/`axis_tick_color`/`axis_line`/`tick_line` flow through the shared `xAxisProps`/`yAxisProps` builders (`chartRenderers/axisOptions.ts`), offered as the `axes` capability to all 20 Recharts-Cartesian renderers with no exceptions — fix round 1 found `schedule`, `waterfall` and `butterfly` were hard-overriding the builder's tick/axisLine/tickLine props *after* the spread to preserve their pre-existing pixel look, which silently discarded these four keys on exactly those three renderers even though `axes` was already offered for them. All three now treat their historical values as defaults that config can still win over, verified by `axisOptions.integration.test.tsx`. |
| Fixed axis minimum / maximum | Yes | Yes | Yes | **Shipped 2026-08-20.** `y_min`/`y_max` on `FormatConfig` flow through `yAxisProps` into a Recharts `domain` tuple, authored via the new Formatting section of `WidgetConfigPanel` and gated by `widgetCapabilities.ts` so the control only appears where a renderer can honour it: of the 20 Recharts-Cartesian renderers, the five dual-scale/time types (`dual_axis_bar`, `dual_axis_line`, `dual_axis_bar_line`, `dual_axis_time_series`, `comparative_time_series`) and `schedule` do not get it, because `FormatConfig` carries a single `y_min`/`y_max` pair and each of those renderers has two independently-scaled `<YAxis>` elements (or, for `schedule`, a defensively-pinned task-name category axis) that a shared domain would clip or corrupt. `pie`, `donut`, `treemap` and `funnel` are outside the 20 wired renderers entirely and read no `FormatConfig` key at all. Also an accessibility feature — see category 13. |
| Logarithmic axis | Yes | Yes | Yes | **Shipped 2026-08-20.** `y_scale: 'log'` flows through the same `yAxisProps` builder, withheld by the capability map from the same dual-scale/Gantt set as the row above for the same reason — a shared scale across two independently-scaled axes is the same problem as a shared domain. Recharts cannot render a log axis through a zero or negative value, so `yAxisProps` accepts an `observedMin` argument and degrades the scale to linear whenever that minimum (or an explicit `y_min`) is non-positive — but `BarChartRenderer` is the only one of the 20 renderers that actually computes and threads an `observedMin` from its own row data; every other renderer calls `yAxisProps` without it, so on those the degrade fires only off an explicit `y_min`, not the data actually being plotted. An author who turns on log scale on, say, `LineChartRenderer` without also setting a positive `y_min` gets no automatic protection if that series later contains a zero or negative value. |
| Overview / scrolling axis | Yes | Yes | No | **Shipped 2026-08-23.** Opt-in Formatting checkbox mounts a Recharts `<Brush>` (miniature of the whole series with draggable handles) on line, area, step and bar — offered only where the renderer actually honours it, via the 'overview' capability in `widgetCapabilities.ts`. |
| Grid lines & wall background | Yes | Yes | Yes | **Shipped 2026-08-20.** `grid`/`grid_style`/`grid_color` flow through `gridProps` (`chartRenderers/axisOptions.ts`); when `grid` is set false the renderer omits `<CartesianGrid>` entirely rather than drawing an invisible one. **Completed 2026-08-22:** the wall paints through CartesianGrid's fill (`wall_color`), the one Recharts surface covering exactly the plotting rectangle, and survives grid lines being turned off. Both surfaces the row names now have controls. |
| Legend visibility & placement | Yes | Yes | Yes | **Shipped 2026-08-20.** `legend`/`legend_position` flow through `legendProps`, which returns `null` (omitting `<Legend>`) when turned off and otherwise maps a `top`/`bottom`/`left`/`right` choice onto Recharts' `verticalAlign`/`align`/`layout`. The capability map offers this control only on the 8 of 20 renderers whose JSX actually builds a `<Legend>` from `legendProps(cfg)` — `bar` (its multi-series/crosstab path), `bubble` (its grouped path), `ribbon`, and the five dual-scale/time types; every other Cartesian renderer is single-series with no `<Legend>` in its JSX, and the pie family (`pie`/`donut`/`treemap`/`funnel`) reads no `FormatConfig` key at all — `DonutChartRenderer` keeps its old unconditional, always-on `<Legend>`, untouched by this option. |
| User-defined reference lines | Yes | Yes | Yes | Value + label + colour per widget. |
| Data labels | Yes | Yes | Yes | **Shipped 2026-08-20.** `data_labels` flows through `labelListProps`, opt-in so no existing widget's rendering changes until an author turns it on, offered to 19 of the 20 axisOptions-wired renderers (every one except `schedule`, whose renderer never calls `<LabelList>`). Still not a uniform option: `ButterflyChartRenderer` plots signed left/right values sharing one axis, so its own `<LabelList>` wraps `labelListProps`' formatter with `Math.abs()` — without that per-renderer override, the left series would show its value as negative on screen. |
| Animation playback options | Yes | Yes | No | **Completed 2026-08-23.** The animation value can render on-chart with all of SAS's options: 9 placement positions, ascending/descending frame order, text size and style (normal/bold/italic), transparency, and a contrast box — authored per widget in the config panel; 'hidden' (the default) keeps the previous control-bar-only presentation. |
| Per-object data-limit override | Yes | Yes | No | **Shipped 2026-08-22.** Per-widget `data_limit` overrides the DirectQuery row cap, clamped to [100, 10× default] — the cap protects the source database, so an unbounded override would defeat it. |
| Periodic auto-reload of object data | Yes | Yes | Partial | **Shipped 2026-08-22.** Per-widget `auto_reload_seconds`, opt-in, clamped to ≥ 5s so a typo cannot hammer the backend; **2026-08-23** the interval gained its authoring surface (Sort & limit group of the config panel) — it was config-only before, which overstated this row. Auto-reload fetches bypass the client result cache (`fresh`), so a periodic reload can never serve stale data. Power BI auto page refresh (DirectQuery, Premium). |
| Table cell styling | Yes | Yes | Yes | **Shipped 2026-08-21.** `table_row_numbers`, `table_row_lines`, `table_banding`, `table_condensed` are authored via the config panel's table-options group (`WidgetConfigPanel.tsx:951-982`, gated by the `tableOptions` capability on `table`/`crosstab`/`matrix` only — `widgetCapabilities.ts:129,157-159`) and read directly by `WidgetRenderer.tsx`'s table branch (`:506-509`). `table_row_numbers` and `table_banding` are pinned by passing render tests; `table_row_lines` and `table_condensed` have a writer and a reader but no renderer test, and were verified by reading the render path only. Cell styling covers row numbers, row lines, banding and condensed height. SAS also offers vertical lines and per-column alignment. |
| In-cell data bar | Yes | Yes | Yes | `bar` column format. |
| In-cell colour scale | Yes | Yes | Yes | `colorscale` format with 2- or 3-colour interpolation (`interpolateColor`). |
| In-cell icon set | Yes | Partial | Yes | `icon` format on a 3-way threshold. |
| Table totals | Yes | Yes | Yes | **Shipped 2026-08-21; re-verified 2026-08-22.** A whole-branch review found this control inert in the one configuration the panel requires, and wrong on DirectQuery; both are fixed and the row was re-checked end to end afterwards. Authored by the "Show totals" checkbox in the config panel's table-options group (`WidgetConfigPanel.tsx:959-960`, persisted at `:360-364`) and now honoured on **all three** shapes a table/crosstab/matrix widget can take: the raw-table branch (`backend/app/services/widget_data.py:210-216`), the pivoted crosstab branch (`:242-247`), and — the fix — the grouped-series branch that a table carrying the `category` role `ROLE_SPECS` marks *required* actually lands on (`:321-323`), where `totals` is aligned positionally to the row-dict keys the renderer builds its columns from. On DirectQuery the shaper's own sums would have described a random sample, so a raw-table result re-measures every column in SQL (`build_row_totals_sql`, `direct_query.py:313`, consumed at `:811-826`), a grouped result re-runs the same GROUP BY with no limit (`build_group_total_sql`, `:280`, consumed at `:672-688`), and a grouped *sampled* result refuses to guess — it drops `totals` and sets `totals_unavailable` (`:828-836`), which the renderer states out loud instead of showing a number (`WidgetRenderer.tsx:589-594`). Rendered as a `<tfoot>` row (`WidgetRenderer.tsx:543-577`, `data-testid="table-totals-row"`); the "Total" label yields to a real number when the first column is numeric, moving into the row-number cell or a visually-hidden span so the row keeps an accessible name. Covered by `backend/tests/test_table_totals.py` (15 tests, including `test_show_totals_is_live_for_a_table_configured_with_the_required_dimension` and `test_dimensioned_table_totals_align_with_the_renderer_columns`) and `backend/tests/test_direct_query_totals.py`. Totals are a **grand total only** — SAS also offers per-group subtotals within a crosstab's row axis, and placement before or after the group. Ours is one row at the foot. |
| Crosstab subtotals | Yes | Yes | Yes | **Shipped 2026-08-21; re-verified 2026-08-22.** The `__total__` row-subtotal column (`widget_data.py:231-233`) is gated by `show_subtotals`, authored by a "Show row subtotals" checkbox (`WidgetConfigPanel.tsx:974-975`) — `backend/tests/test_table_totals.py::test_row_subtotal_column_can_be_turned_off` confirms turning it off. The checkbox used to be offered, pre-checked, on plain tables and on crosstabs with no Column Pivot, where the `__total__` column exists in no configuration at all and the control therefore did nothing; it is now rendered only when a second dimension is set (`WidgetConfigPanel.tsx:972`), which is exactly the branch that builds the column, and a saved explicit `false` still round-trips through a config that cannot currently show the control. The column defaults ON because it shipped unconditionally before it was configurable; turning it off is opt-in. SAS also offers row/column axis choice and before/after placement. |
| Expression-based display rules | Yes | Yes | Yes | **Shipped 2026-08-18.** Boolean/comparison rules run through the existing AST-allowlist sandbox (`app/services/display_rules.py`) against the already-shaped widget result, restyling mark, background or visibility. A broken rule is recorded in `rule_errors` and every other rule still applies — fails OPEN, deliberately the opposite of `apply_rls_filter`. Narrower than SAS in two ways: a rule addresses the SHAPED result's columns (a series widget exposes `name`/`value`; a crosstab exposes its dimension and `__total__`), not arbitrary source data items, and there are no parameters anywhere in this app, so parameter-driven rules — which the SAS column claims — have no equivalent. **Mark coverage updated 2026-08-20:** rule-driven mark restyling (`ruleStyles`) now paints on 17 of 31 `chartRenderers/*.tsx` files (was 12), verified by grepping every renderer file for `ruleStyles`. The line-shaped renderers (`line`, `area`, `step`, and the dual/comparative time-series types) are deliberately excluded — a line is one continuous path, not N discrete marks, so there is no per-row mark for a rule to restyle. `numeric_series` looks line-shaped but is not excluded: `NumericSeriesPlotRenderer` wires rule fills into a custom per-point dot renderer (covered by a passing test), which is one of the five renderers that took coverage from 12 to 17. `DualAxisBarChartRenderer` is a known misclassification carried over from the original plan: it renders two `<Bar>` series and no `<Line>` at all, yet remains uncovered, and up to six further renderers are unaudited against this list. |
| Colour-mapped-value rules by category | Yes | Yes | Partial | **Shipped 2026-08-21.** `DisplayRulesPanel.tsx` now offers a "Colour map" rule kind (`RULE_KINDS`, `:7-11`) that renders `ValueMapEditor.tsx` — an Any-Category checkbox plus an editable value→colour mapping list, writing exactly the `mappings`/`any_category` shape `_value_map_style` reads (`backend/app/services/display_rules.py:67-82`) — closing the authoring gap phase 1's review identified; the engine was already shipped and tested. **Re-verified 2026-08-22:** a whole-branch review found the reused Fill swatch above this editor painted nothing at the default `mark` target (the matched mapping carries its own colour), and that a rule naming a column the result lacks failed *silently*. Both fixed — the swatch is rendered only where `rule.style` has a consumer (`ruleCapabilities.ts`; `DisplayRulesPanel.tsx:207-217`), and a missing column is now recorded in `rule_errors` like every other kind (`display_rules.py:83-85`). A Column select is rendered for this kind too, hidden only in Any-Category mode, which reads no column. Covered by `ValueMapEditor.test.tsx` and by `DisplayRulesPanel.test.tsx`, whose "Colour map and Bands authoring" block (11 tests) now exercises the panel wiring end to end — when this row was first scored Yes, that second claim was not yet true. Narrower than SAS in the ways already noted for expression rules above: it addresses the shaped result's columns, and there is no parameter-driven mode. |
| Gauge interval rules | Yes | Yes | Partial | **Shipped 2026-08-21.** `DisplayRulesPanel.tsx` now offers a "Bands" rule kind that renders `IntervalEditor.tsx` — an add/remove list of numeric min/max/colour bands, writing exactly the `bands` shape `_interval_style` reads (`backend/app/services/display_rules.py:85-103`) — closing the authoring gap phase 1's review identified; the engine and `GaugeRenderer.tsx`'s `ruleStyles.rows[0].fill` paint were already shipped and tested (2026-08-19). **Re-verified 2026-08-22.** A whole-branch review found this row's authoring surface produced a rule that errored on every render: the `interval` branch rendered no Column control, so a rule switched to "Bands" kept the categorical `columns[0]` and `float("US")` raised on each evaluation, with nothing on screen the author could change. Fixed — the Column select is now shared by all three rule kinds (`DisplayRulesPanel.tsx:171-186`), narrowed for a Bands rule to the columns the caller has told the panel are numeric (`intervalColumns`, `:107-121`; `ruleNumericColumns`, `WidgetConfigPanel.tsx:454-456`), and switching kind lands the rule on a numeric column instead of inheriting the categorical one (`:95-99`). For a gauge that resolves to `value`, which is what `_interval_styles` brackets (`display_rules.py:182-201`) and what `GaugeRenderer.tsx:18` paints from. Where the caller knows the dtypes and none are numeric, no select is rendered and the panel says why instead. Covered by `IntervalEditor.test.tsx` and by `DisplayRulesPanel.test.tsx`'s authoring block, which now mounts the panel and pins this default — when this row was first scored Yes, that second claim was not yet true. Still narrower than SAS on the shape itself: these are generic numeric bands, not gauge shapes — SAS ships four purpose-built gauge types (icon, bullet, slider, thermometer) with their own rendering, and this work did not add any of them. |
| Report-level display rules | Yes | Yes | No | **Shipped 2026-08-18.** `Report.display_rules` resolves ahead of each widget's own rules, so one rule list covers every object on every page; a widget rule overrides a report rule targeting the same mark by list order. Unlike SAS, ours is not data-source independent — a report rule still evaluates against each widget's own shaped result columns, so it only takes effect where the referenced column name exists in that widget's output. |
| Rule-driven conditional visibility | Yes | Partial | Yes | **Shipped 2026-08-18; corrected 2026-08-19.** A `visibility`-target rule now hides its widget in view mode completely — `WidgetRenderer.tsx` renders nothing at all, not the frame around an empty body. (Between 2026-08-18 and 2026-08-19 it only hid the widget's *body*, leaving the border, header and title visible around a blank space, which read as a broken widget rather than a hidden one — fixed rather than left as a documentation caveat.) In edit mode the widget still renders the full frame with a "Hidden by a display rule" placeholder body, so an author can select and reconfigure whatever a rule would hide. Still condition-driven only — no bookmark/button interaction model, so Power BI's authored show/hide flows have no equivalent here. Presentational only, like every display-rule target: the rows a hidden widget would have shown are still in the response the client already received (see the module docstring in `display_rules.py`) — this is not a substitute for row-level security. |

## 08 — Interactivity (32 rows)

| Capability | datalytics | SAS VA | Power BI | Note |
|---|---|---|---|---|
| Cross-filter between visuals | Yes | Yes | Yes | `CrossFilterContext` with page scoping. |
| Cross-highlight (linked selection) | Yes | Yes | Yes | **Completed 2026-08-23.** A per-widget receive mode (Interactions panel): 'Filter' narrows the widget to the selection (previous behaviour, still the default); 'Highlight' keeps the FULL result and saturates each mark's selected share — two queries (unfiltered baseline + selected slice) merged per category, the saturated fraction being exactly the shared-observation percentage SAS shades. Overlay rendering ships for bar charts; other types receive as filters. |
| Per-visual interaction direction | Yes | Partial | Yes | two-way / broadcast-only / receive-only / isolated (`InteractionSettings.tsx`). |
| Page-wide automatic action modes | Yes | Yes | Partial | **Completed 2026-08-23.** Page properties gains an Interactions mode — Manual (per-widget settings, default), Linked selection (everyone broadcasts, receivers highlight), One-way filter (single source at a time: a new selection replaces other sources' filters), Two-way filter (filters accumulate) — persisted in the page's settings JSON, overriding every widget's own interaction settings exactly as SAS's mutually-exclusive page modes do. |
| Manual per-pair actions | Yes | Yes | Partial | **Shipped 2026-08-24.** A widget's Interactions pane defines named actions on specific other widgets (filter or highlight per target); declaring any action replaces broadcast-to-all, exactly as SAS's Actions pane does. **Transitivity added 2026-08-24** to match SAS: `getFiltersFor` resolves reach through the transitive closure of the action graph (`actionReaches` in `CrossFilterContext`), so an action A→B and B→C means a selection in A reaches C — walked breadth-first with a visited set so a cycle (A→B→A) terminates instead of looping. Per-pair action *type* still resolves from the direct edge. Interaction settings are session state (not persisted), like the page-level modes they coexist with. |
| Multi-value filter emission | Yes | Yes | Yes | `emitMultiFilter` → `in` operator. |
| Object-level filters | Yes | Yes | Yes | Per-widget `filters` config. |
| Advanced expression filters | Yes | Yes | Yes | `apply_filter_expr` over the same 47-name namespace. |
| Post-aggregate filters | Yes | Yes | Yes | Filter on the aggregated value, not the row value. **Shipped 2026-08-23.** `config.having` compares each category's aggregated value on the grouped frame (before sort/limit) — a row filter at 25 would drop a region whose rows are 10+20; HAVING keeps it. Panel: "Filter aggregated values" under Sort & limit. |
| Reusable common filters | Yes | Yes | No | **Shipped 2026-08-24.** Report-level filters defined once and applied to every widget on every page (SAS's shared common filter; Power BI's "filters on all pages"). Stored in a `common_filters` table (create_all-created, one row per filter) and attached to `ReportOut`/the shared payload as a transient list; `POST`/`DELETE /reports/{id}/common-filters` back it, through the standard edit gate + revision bump. The frontend merges them into every widget's query filters (translating the column across a modelled relationship, like cross-filters) — no backend query-path change, because the shaper's `_apply_filters` already skips columns a widget's dataset lacks, so a report-wide filter cleanly no-ops on unrelated widgets. Authored in the builder's Report filters panel (column/op/value); edits propagate to all widgets at once. Verified live: one `region = Asia Pacific` filter narrowed every KPI and chart on the report. Report-wide rather than per-object opt-in, so edits propagate everywhere by construction. |
| Dataset-level pre-filter | Yes | Yes | Yes | `Dataset.default_filter_expr`. |
| Rank top / bottom N | Yes | Yes | Yes | **Completed 2026-08-23.** `rank {mode: top|bottom, n, percent?, other?}` on shape_series: boundary ties kept (SAS's include-ties), `percent` reads n as a share of the category count, `other` collapses the excluded categories into one "All Other" row aggregated from their RAW rows (an aggregate of aggregates would be wrong for avg/median — skipped only for measure expressions, where no honest bucket exists), and `n: "@param"` drives the count from a report parameter, typed and validated at the router. Config panel exposes all of it. |
| Custom sort order for category values | Yes | Yes | Yes | **Shipped 2026-08-23.** `config.sort_custom` is an explicit ordered list that beats any computed sort; categories missing from the list follow rather than vanish, so a typo can never silently hide data. |
| Multi-column sort | Yes | Yes | Partial | **Shipped 2026-08-24.** Raw table / list widgets take an ordered `sort_keys` list `[{col, dir}]` — sort by the first column, ties broken by the next, and so on. Applied in the shaper's ungrouped branch (`widget_data.py`) with a stable mergesort so rows equal on every key keep source order; unknown columns (since removed from the dataset) are skipped rather than raising, and the list supersedes the single `sort_col`. Authored via a per-widget add/remove editor in the Sort & limit panel, gated to table/list (a grouped chart has no ungrouped rows to order this way). Verified end-to-end: the "Largest Transactions" demo table sorted region-asc then revenue-desc in the live builder, and the widget-data endpoint returns the same order. Scope is the raw table, matching where "sort by A then B then C" is the canonical operation; aggregated crosstab ordering is unchanged. |
| Report-level prompts | Yes | Yes | Partial | datalytics prompts are per-page only (`ReportPage.prompt_column`). **Shipped 2026-08-22.** A report's parameters render as a prompt bar above the canvas for every viewer; `@name` references drive filter values and calculated expressions. |
| Page-level prompts | Yes | Yes | Yes | Single free-text value applied as a filter. |
| Cascading prompts | Yes | Yes | Partial | SAS chains controls so each narrows the next. **Proven 2026-08-23** rather than built: slicer queries merge incoming cross-filters like any widget, so a selection in one slicer narrows every other slicer's value list — driven live (region=Europe cut the country slicer from 14 values to Europe's). Chaining is selection-driven and automatic, not authored per-pair as in SAS. |
| Control type variety | Yes | Yes | Yes | SAS picks from slider, list, drop-down, button bar and text input by cardinality (<5 button bar, 5–40 drop-down, >40 text input). **Shipped 2026-08-23.** Button bar, checkbox list, multi-select drop-down and searchable list, with the cardinality rule on auto (buttons <5, list to 40, searchable beyond) and an author override. A numeric slider control is the remainder — the named variety-by-cardinality behaviour is here. |
| Numeric parameters | Yes | Yes | Yes | **Shipped 2026-08-22.** `ReportParameter` type `number`; substituted server-side as a float literal, so `os.system` fed to a number parameter is a 400, not an expression. |
| Character parameters | Yes | Yes | Partial | SAS supports multi-value character parameters with In/NotIn/IsSet. **Shipped 2026-08-22.** Type `text`, optional fixed options (rendered as a dropdown); values quoted by repr so a quote-carrying value cannot terminate the literal it sits in. |
| Date parameters | Yes | Yes | Partial | **Shipped 2026-08-22.** Type `date`, validated via Timestamp, emitted as an ISO literal; the viewer control is a native date input. |
| Expression-based parameters | Yes | Yes | No | **Shipped 2026-08-24.** A new `expression` parameter type whose value is computed over the WHOLE source at query time — RLS-scoped but immune to report/widget filters — so a benchmark like `AVG(revenue)` or a self-updating slider bound to `MAX(revenue)` reflects the data, not a typed constant. The measure expression rides in `default_value` (no schema change); `widget_data._apply_report_parameters` evaluates it via `evaluate_measure(expr, rls_frame, [])` on a worker thread and the computed scalar **wins over any viewer value** (a benchmark is not something a viewer overrides). Referenced as `@name` in filters/calc expressions like any parameter, encoded as a numeric literal. Import datasets only (a warehouse benchmark would need a SQL aggregate → clear 400). Authored in the Parameters pane's type dropdown; expression params never appear in the viewer prompt bar. Verified live: `AVG(revenue)` over the demo dataset drove a calc column across 957 rows. |
| Page navigation links | Yes | Yes | Yes | Button action `navigate`. |
| Report-to-report links | Yes | Yes | Yes | **Shipped 2026-08-23.** Button action 'Go to another report' navigates to `/reports/<id>` with a `Number()` cast so edited config cannot smuggle a path; the target report enforces its own permissions on arrival. |
| External URL links | Yes | Yes | Yes | **Completed 2026-08-23.** A button's 'Open external URL' action now parameterises the URL: `{{@name}}` placeholders substitute the live report-parameter value — SAS's role-bound data value, expressed through the parameter mechanism. Values are URL-encoded before splicing and the http(s) allowlist runs on the substituted result, so a parameter value can never rewrite the scheme (an attempted `javascript:` becomes an inert encoded path). Still opened with `noopener,noreferrer`. |
| Links from text | Yes | Yes | Yes | **Shipped 2026-08-22.** Markdown-style `[label](https://url)` in text blocks, rendered by splitting rather than innerHTML so only the explicit link syntax becomes an anchor; non-http(s) schemes stay literal text. |
| Set prompt values instead of filtering | Yes | Yes | No | SAS's "Set Prompt Bar values of target page" — navigate and *select* rather than navigate and *filter*. **Shipped 2026-08-23.** Button action 'Set a parameter' writes a named report-parameter value; every widget bound to `@name` refreshes, and `{{@name}}` prose updates with it. |
| Drillthrough to a detail page | Yes | Yes | Yes | Header button **and** right-click context menu, seeding the target page's prompt filter. |
| Report-page tooltips | Yes | Partial | Yes | Hover renders the tooltip page's widgets in an isolated `CrossFilterProvider`. |
| Bookmarks | Yes | Partial | Yes | Captures page, cross-filters, prompt values and hidden widgets. SAS has no bookmark object. |
| Slicer sync across pages | Yes | Partial | Yes | |
| Hierarchy drill down / up | Yes | Yes | Yes | In-place re-query one level deeper with a breadcrumb, plus date-granularity drill. **2026-08-23:** hierarchies also act as data items the SAS/PBI way — Fields-pane chips bind the whole level chain (click-assign or drag-to-auto-chart), and PBI's EXPAND joins several levels into path labels ('Asia Pacific › Australia') alongside drill, the two modes exclusive as in PBI. Expand is offered only across distinct-column levels; a Year→Quarter granularity chain shows no dead control. |

## 09 — Layout, containers & templates (16 rows)

| Capability | datalytics | SAS VA | Power BI | Note |
|---|---|---|---|---|
| Grid layout with snap | Yes | Yes | Yes | 12-column absolute grid with drag and resize. |
| Overlapping / precision placement | No | Yes | Yes | SAS's precision container is the only one permitting overlap, using percentage offsets so it adapts to resolution. |
| Align / distribute | Yes | Yes | Yes | All 8 operations against pure functions in `lib/alignment.ts`. |
| Standard container (grouping / nesting) | Yes | Yes | No | **`ReportWidget` has no parent field** — nesting is a schema change, not just UI. **Shipped 2026-08-22.** A `container` widget; children are ordinary page widgets carrying `container_id`, so rules, cross-filters, parameters and RLS apply to a child exactly as anywhere. Canvas renders each child once, inside its container. |
| Stacking container (slide-deck / tabs) | Yes | Yes | Partial | SAS navigation via buttons, dots, links, tabs or numbers. **Shipped 2026-08-22.** `container_mode: tabs` — real `role=tab`/`tablist`, one child mounted at a time (absent, not hidden). |
| Scrolling container | Yes | Yes | No | **Shipped 2026-08-22.** `container_mode: scroll` — the container's grid overflows vertically. |
| Prompt container (collapsible) | Yes | Yes | No | Also the only way SAS gets a list control into a prompt area. **Shipped 2026-08-22.** `container_mode: prompt` — a collapse header with `aria-expanded`, children stacked when open. |
| Object templates | Yes | Yes | No | **Shipped 2026-08-24.** Save a configured widget by name and drop it onto any report — the object-level analogue of a DataView. A new `WidgetTemplate` table (org-scoped, auto-created by create_all) stores the widget's type + whole config (roles, formatting, rules, filters, ranks, sorting); `GET/POST/DELETE /widget-templates` back it. Reserved `__keys` and `container_id` are stripped on save, so a template carries appearance and logic but no placement/governance state, and apply is a plain client-side insert of a new widget carrying the config — it binds to no dataset ids, matching by column name like the rest of the builder. Authored from the builder's Insert → Templates panel: name the selected widget and Save; click a saved template to insert. Verified live: saved a bar and inserted a working copy. No org-published/admin-default tier yet — templates are org-wide and applied deliberately. |
| Built-in page templates | Yes | Yes | No | **Shipped 2026-08-23.** Two structural layouts (KPI overview, chart + detail) in the + Page menu — deliberately unbound to data, since a template's value is layout and wiring, not guessed column names. SAS ships six with predefined actions. |
| Custom page templates | Yes | Yes | No | **Shipped 2026-08-23.** Save-current-page-as-template into org-scoped `page_templates`; cross-widget references serialise as indices and rehydrate to new ids, so a templated container keeps its children (pinned by the round-trip test). |
| Import pages from another report | Yes | Yes | Partial | SAS carries layout, objects, calc items and parameters, with per-item data-conflict resolution. **Shipped 2026-08-23** at the API (`from-template` with a source report/page, org-checked at both ends, tested). **Completed 2026-08-23:** the + Page template menu gained the picker (choose a report, pick a page). |
| Page types (hidden / popup) | Yes | Yes | Partial | `PageType`: normal, hidden, popup, tooltip, drillthrough. |
| Per-user page visibility | Yes | Yes | No | **Shipped 2026-08-23.** Per-role restriction on a page, enforced server-side: the page is absent from an excluded viewer's payload, never merely hidden client-side. Admins exempt; foreign role ids rejected. |
| Page size presets | Yes | Yes | Yes | 16:9, 4:3, custom (`PagePropertiesPanel.tsx`). |
| Mobile / phone layout | Yes | Partial | Yes | Per-page widget order and hidden list, applied on narrow viewports in view mode. |
| Canvas zoom | Yes | Partial | Yes | 50–150% with the scroll area scaled to match. |

## 10 — Report editor shell (17 rows)

Scored against SAS VA's 11-pane taxonomy.

| Capability | datalytics | SAS VA | Power BI | Note |
|---|---|---|---|---|
| Data / fields pane | Yes | Yes | Yes | Sidebar Fields section grouped into Measures and Dimensions; clicking a field assigns it to the selected widget's next open matching role. |
| Objects / visual gallery pane | Yes | Yes | Yes | Sidebar Insert section, `WIDGET_CATALOG` split Charts / Controls. |
| Outline / structure pane | Yes | Yes | Partial | SAS's Outline is also how you move objects into containers and rename them. **Shipped 2026-08-23.** ⊟ Outline: pages → widgets with container nesting; click selects, double-click renames, and a per-widget select re-parents via the same `config.container_id` the canvas reads, so the tree and the canvas can never disagree. |
| Suggestions pane | Yes | Yes | Partial | SAS generates candidate visuals from cardinality and correlation, with Refresh and More. **Shipped 2026-08-23.** 💡 Suggest: pie for low-cardinality categories, bar otherwise, line for date columns, scatter for correlated pairs (stored analysis, strongest first), histograms — deterministic heuristics, ↻ More rotates the window, one click adds an ordinary widget. |
| Review / linting pane | Yes | Yes | No | See category 12. **Shipped 2026-08-23.** ✓ Review in the toolbar: untitled/alt-less widgets, empty results, broken display rules (fail-open makes them invisible otherwise), slow widgets, empty containers, crowded pages — ranked, each finding selecting its widget. |
| Options / format pane | Yes | Yes | Yes | **Re-scored Yes 2026-08-23 — every residual the 2026-08-21 note named has since shipped and been verified in the panel:** per-object data-limit override (Row limit, Sort & limit group), custom/imported themes (org_themes), and periodic auto-reload (interval field added 2026-08-23 — the last piece with no authoring surface). What ships: collapsible groups with persisted open/closed state — Fields, Data & aggregation, Filters, Sort & limit, Formatting (axis label/tick/line styling, fixed min/max, log scale, grid, legend, data labels, table totals/cell styling), Appearance (background/border/radius/padding, alt text), Display rules, Interactions. Data skins remain deliberately out of scope and score No on their own row. |
| Roles pane | Yes | Yes | Yes | Driven by `ROLE_SPECS`, so each widget type declares its own fields. |
| Actions pane | Yes | Yes | Partial | **Completed 2026-08-23.** The Interactions panel now defines named per-pair actions: for each other data widget on the page, choose Filter or Highlight — and defining any action makes the source's selections reach ONLY its listed targets, replacing broadcast-to-all exactly as adding actions does in SAS. The pair's action type drives the target's receive presentation; page-wide automatic modes remain mutually exclusive and override. |
| Display rules pane | Yes | Yes | Partial | **Corrected 2026-08-22 — this row was scored No against a pane that already existed, and under-scoring misdirects planning as much as over-scoring does.** Two author-reachable surfaces render `DisplayRulesPanel.tsx`: a per-widget "Display rules" group in the settings panel (`WidgetConfigPanel.tsx:1083-1095`, fed frame-aware `ruleColumns`/`ruleNumericColumns` and that widget's own `rule_errors`), and a dedicated report-level pane in the right panel, toggled from the builder toolbar (`ReportBuilder.tsx:890`, rendered at `:1167-1180`). The pane lists the object's rules, adds and removes them, and authors all three kinds the engine supports — expression, Colour map, Bands — with a Rule kind select, a Column select, an Applies-to target, per-mapping and per-band colours, and the engine's error for a rule it could not evaluate shown on the offending row. Scored Yes only as of the 2026-08-21 fix wave: before it, the Bands and Colour map branches rendered no Column control and the pane could not produce a working band rule by any path an author would find. Narrower than SAS in the same ways category 07 records for the rules themselves — rules address the shaped result's columns rather than arbitrary data items, and there are no parameters — and the report-level pane offers only `name`/`value` and passes no dtype information, so a Bands rule added there opens on `name` and has to be pointed at `value` by hand (the control is present and the error is surfaced, unlike the widget-level defect above). |
| Filters pane | Yes | Yes | Yes | `FilterBar` shows and clears *active cross-filters*. **Completed 2026-08-23:** a Filters group in the widget settings AUTHORS the object's own row filters (column/op/value rows, in-lists, numeric coercion), writing the `config.filters` the engine always supported — the missing half was the authoring surface. |
| Ranks pane | Yes | Yes | Partial | **Shipped 2026-08-23.** Rank in the Sort & limit group: top/bottom N selected by AGGREGATED value, independent of the display sort (bottom-5-shown-alphabetically is two orderings, which is why sort+limit could never express it). Boundary ties are kept, as SAS keeps them. |
| Selection pane (show / hide) | Yes | Partial | Yes | |
| Performance analyzer | Yes | Yes | Yes | Per-widget fetch duration, row count and sampled badge. SAS has Query Diagnostics (Ctrl+Alt+Q). |
| Automatic chart from dragged fields | Yes | Yes | Yes | **Shipped 2026-08-23.** Field chips drag onto the canvas and land as the inferred widget: dates as trend lines, categories as count bars, measures as histograms — refine from there, never a config dialog first. |
| Edit / view mode toggle | Yes | Yes | Yes | |
| Model / relationship view | Yes | Partial | Yes | `ModelView.tsx` lists and edits `Relationship` rows. |
| Data grid view | Yes | Yes | Yes | `DataView.tsx` with per-column filters, global search, sort and paging. |

## 11 — Distribution & export (21 rows)

Nothing in this category exists in datalytics. Neither `backend/requirements.txt` nor
`frontend/package.json` contains a PDF, image-export, print, mail or scheduler library.

| Capability | datalytics | SAS VA | Power BI | Note |
|---|---|---|---|---|
| Export report to PDF | Yes | Yes | Yes | **Completed 2026-08-24.** A genuine SERVER-rendered PDF (matplotlib headless Agg for chart images, reportlab for layout — no browser in the loop), not just the browser's print-to-PDF: cover (title, description, generated timestamp), a table of contents, then one section per page with each visual drawn — bar/line/area/pie/donut/scatter as chart images, KPIs as figures, everything else falling back to its shaped data as a table so nothing is dropped. Downloadable via `GET /reports/{id}/pdf` (📄 PDF toolbar button; RLS applied as the caller, page-visibility honoured) AND selectable as a scheduled-delivery attachment (Attachment = PDF), so it is the emailable artifact this row wanted. SAS's appendix is not replicated; page setup (landscape A4) and TOC are. |
| Export visual data to Excel | Yes | Yes | Yes | **Shipped 2026-08-22.** `POST /datasets/{id}/widget-data/export?format=xlsx`, reached from the widget context menu. Resolves through the same `_resolve_widget_data` the display path uses, so row-level security, calculated columns, measures and the DirectQuery pushdown all apply — proven by a test where a CA-restricted user downloads only CA rows. Structure follows the shaped result via `result_frame`, so a crosstab exports as a crosstab. **Formats, cell visualisations and display rules are not carried into the workbook**, which is where SAS still leads. |
| Export to CSV / TSV | Yes | Yes | Yes | **Completed 2026-08-22.** TSV joined CSV on the widget export, and `GET /datasets/{id}/export` downloads the whole table — with row-level security applied identically to display, pinned by a test where a restricted user receives only their slice. |
| Export visual as an image | Yes | Yes | Partial | **Shipped 2026-08-22.** Context menu → PNG at 2x, client-side from the live SVG with theme colours inlined (CSS custom properties do not exist inside an isolated image document). |
| Export to PowerPoint | Yes | Partial | Yes | SAS via the Microsoft 365 add-in. **Shipped 2026-08-23.** Native 'Download PowerPoint' on the print route: one widescreen slide per page, charts rasterised from their live SVGs and placed at authored positions, text-shaped widgets as text boxes carrying their rendered numbers. Verified as a real .pptx (PK magic, slide XML, embedded media). |
| Offline report package | No | Yes | No | Snapshot of data and query results, hostable on a web server. |
| Print layout | Yes | Yes | Yes | **Shipped 2026-08-22.** `/reports/:id/print`: linear pages, chrome stripped, one report page per sheet, hidden pages excluded — a printout is view mode on paper. |
| Scheduled report distribution | Yes | Yes | Yes | **Completed 2026-08-23.** `report_schedules` on the shared scheduler loop, now with calendar semantics: daily / weekly (day-of-week) / monthly (day 1–28, so every month qualifies) at a stated UTC clock time, alongside the original minute intervals; authored in the Schedule panel, validated at the API, and stored as a reserved entry in the recipients JSON (the table gains no column; delivery ignores non-string entries by contract). Due-ness compares tz-normalized datetimes — the Postgres-aware-vs-naive trap is handled in every comparison this module makes. Runs AS THE CREATOR; run-now for verification; status per run. The attachment remains the xlsx data digest — a rendered-PDF artifact is row 'Export report to PDF', still open. |
| Email delivery | Yes | Yes | Yes | **Shipped 2026-08-22.** SMTP via env settings; the delivery is an xlsx digest (one sheet per data widget, resolved through the display pipeline) plus a link to the print view. Unconfigured SMTP records why nothing arrived rather than raising. |
| Microsoft Teams delivery | Yes | Yes | Yes | **Shipped 2026-08-23.** An https:// incoming-webhook URL as a schedule recipient routes the delivery summary + link there; http:// refused. |
| Data-condition alerts | Yes | Yes | Yes | **Shipped 2026-08-22.** An aggregate expression over a dataset, validated by the widgets' own sandbox gate, evaluated on its own interval with creator-resolved RLS, firing on the rising edge only and re-arming after a clear pass. SAS separates notification frequency from query frequency; here they are one interval. |
| In-app notifications | Yes | Yes | Yes | **Shipped 2026-08-23.** A per-user bell in the rail (60s poll, unread badge, open-marks-read): alert rising edges, failed scheduled deliveries, and comments on reports you've participated in. Produced by the background loop alongside email, because a failure only an SMTP log knows about is a failure nobody knows about. Rows capped at 200 per user; the router exposes own-rows only. |
| Copy link at report / page / object level | Yes | Yes | Partial | **Completed 2026-08-23** at all three levels: report, page (`?page=`), and object — every widget's context menu offers "Copy link to this visual", encoding `?page=&widget=`; on load the builder opens the right page, scrolls the visual into view and flashes its outline (one-shot, so later page flips never re-scroll). |
| URL parameter presets | Yes | Yes | Yes | **Shipped 2026-08-22.** `?p.<name>=value` seeds the viewer's parameter values on load, and combines with the copied page link. |
| Guest / anonymous access | Yes | Yes | Partial | Power BI's Publish to Web is public-internet only. **Shipped 2026-08-23.** Signed guest links (🌐 Share): sha256-only storage, 1–90 day expiry, revocation, and a public surface of exactly two read-only routes — everything JWT-guarded still 401s the token, proven by test. Data resolves from SAVED widget configs only, as the LINK'S CREATOR, so a link exposes exactly the sharer's RLS slice and can never run arbitrary queries; the mint dialog states this before the URL exists. |
| Localisation of report text | Yes | Yes | Partial | SAS translates object titles, tooltips and descriptive text per locale, selected by browser locale. **Shipped 2026-08-23:** per-locale overrides for widget titles and text-widget content (`report_translations`), authored in a Translations pane, applied in view mode by the viewer's browser locale with pt-BR→pt fallback; authored strings stay the single source the builder edits. Chart hover-tooltips are the untranslated remainder. Per-widget RTL already shipped. |
| Kiosk / playback mode | Yes | Yes | Partial | Timed page advance with an optional countdown. **Shipped 2026-08-23.** ▶ Present: pages auto-advance every 8s; any key exits. SAS adds a configurable countdown. |
| Comments / discussion | Yes | Yes | Yes | **Shipped 2026-08-23.** Flat per-report discussion (💬 toolbar pane), optionally pinned to the page it was written on; own-delete only, org admins can moderate. Posting notifies every prior participant's bell except the author. No threaded replies or @-mentions — the row's capability (discussion on a report) is here. |
| Workspaces / app packaging | No | Platform | Yes | |
| Dashboards pinning tiles from many reports | No | No | Yes | Genuinely a Power-BI-only concept. |
| Lineage view | Yes | Platform | Yes | **Shipped 2026-08-23.** `/lineage`: sources → datasets → reports as measured columns with SVG edges — dataset joins from prep steps, and report edges built from what widgets ACTUALLY read (`config.dataset_id`), not just the report's declared dataset. Click a node to trace; titles link to the object. |

## 12 — Governance & security (15 rows)

This is datalytics' strongest category relative to both competitors, because multi-tenancy and RLS
were built in rather than bolted on.

| Capability | datalytics | SAS VA | Power BI | Note |
|---|---|---|---|---|
| Authentication | Yes | Platform | Platform | JWT login with constant-time comparison against unknown emails (`routers/auth.py`). |
| Single sign-on (SSO) | Yes | Platform | Platform | **Shipped 2026-08-24 — OIDC + SAML 2.0**, per organization, resolved by the user's email domain, configured at `/admin/sso`. **OIDC** (Authorization Code + PKCE): discovery from the issuer, `state`+`nonce`+PKCE sealed in a short-lived HttpOnly cookie (no server session store → multi-worker safe), and full id_token validation (JWKS signature, `iss`/`aud`/`exp`/`nonce`); client secret encrypted at rest. Covers Azure AD/Entra, Okta, Google, Auth0, Keycloak. **SAML 2.0** (SP-initiated Web SSO): AuthnRequest over HTTP-Redirect, assertion consumed over HTTP-POST; the XML signature is verified with **signxml** (pip-only — no native xmlsec/libxmlsec1 build), and identity is read **only from the verified subtree**, which defeats XML Signature Wrapping — proven by a test that injects an unsigned attacker assertion beside the signed one and shows it is ignored. Plus condition checks: NotBefore/NotOnOrAfter, Audience==our SP entityID, Recipient==our ACS, and InResponseTo bound to a pending request tracked server-side and consumed once (the ACS is a cross-site POST where a SameSite cookie would not be sent). SP metadata is published at `/auth/sso/saml/metadata`. **Match-existing only** for both: an authenticated identity with no local account is refused, never provisioned. Password login is untouched and works alongside SSO. Verified live: OIDC builds a real Google authorize redirect; SAML builds a valid deflated AuthnRequest to the IdP. 28 backend tests (OIDC callback + SAML ACS against mocked IdPs with real RS256/XML signatures) cover signature/audience/expiry/nonce/state/recipient/replay/unknown-account/XSW. Not yet: JIT provisioning, more than one IdP per org, Single Logout, IdP-initiated flow, or encrypted assertions. |
| Row-level security | Yes | Yes | Yes | `RowSecurityRule` per (role, dataset); evaluated server-side in the query path so client-side config edits cannot bypass it, **fail-closed to zero rows** on a malformed rule, and translated to SQL for DirectQuery pushdown. **2026-08-24: dynamic user context** — `USEREMAIL()`/`USER()`/`USERID()` tokens in a rule resolve to the caller's identity (`core/rls.py` `apply_user_context`), so one role-level rule like `owner == USEREMAIL()` scopes every user to their own rows without a role-per-user explosion. Substituted as a safe literal (email via `repr`, id as int) before either evaluator, so it binds as a query parameter under DirectQuery and an AST literal under import; the per-user expression naturally makes the DirectQuery cache key per-user. Authored in the admin RLS editor (hint surfaces the tokens); the creation-time validator resolves them against a placeholder identity. |
| Column-level security | Yes | Yes | Yes | Power BI OLS. **Shipped 2026-08-23.** Per-role denied columns: import mode drops them before anything can read them, DirectQuery fails closed (silently rewriting SQL is worse than refusing), the whole-table export drops them, and the mask feeds the cache key so roles never share entries — pinned by a cache-poisoning test. Admin CRUD at /admin/column-security-rules. |
| Organisation / tenant scoping | Yes | Platform | Partial | Every dataset, report, data source and relationship carries `org_id`, enforced by `core/org_scope.py`. |
| Roles & permissions | Yes | Yes | Yes | `Role.is_org_admin` bypasses RLS by design. |
| Per-report viewer capability levels | Yes | Yes | Partial | **Completed 2026-08-23.** Three additive levels per report per role, SAS-style: `view` (read + interact only), `edit` (change report structure), `data` (edit PLUS the dataset's calc columns / measures / prep). Enforced SERVER-SIDE — `edit` at `_bump_revision`, the choke every report mutation passes through, plus explicit gates on delete/params/translations/schedules/share-links; `data` on the calc/measure/prep endpoints via the user's best capability across reports using that dataset. No capability row = the `data` default, so it is an opt-in restriction that doesn't break today's everyone-can-edit behaviour; org admins are always `data`. Authored on an admin-only Access dialog (role × level); the builder mirrors the level (view-only users get no edit toggle and no Data/Model tabs). |
| Granular export disablement | Yes | Yes | Partial | **Completed 2026-08-23.** Per-destination now: the policy is `true` (everything off, the original contract) or `{formats: [csv/tsv/xlsx], auto_private}` — listed destinations refuse while others keep working, and `auto_private` disables every export WHILE the dataset carries row- or column-security rules, checked live at export time so a rule added later closes exports with no policy revisit (SAS's auto-disable-when-private). Enforced on both export routes; authored on a new admin Export policy page (dataset × destination checkbox grid with a live security-rules column); changes audited; org-admin only to read or write. |
| Sensitivity labels / data classification | Yes | Partial | Yes | **Shipped 2026-08-24.** A report can carry a sensitivity label from a fixed, ordered set (Public / Internal / Confidential / Restricted). Stored in its own `report_classifications` table (create_all-created, one row per report) since Report predates it and create_all never ALTERs a live table; the read endpoint attaches it to `ReportOut` as a transient field, the same way `my_capability` is. `PUT /reports/{id}/classification` sets or clears it through the standard edit-capability gate and revision bump. Shown as a colour-coded badge in the builder top bar (with a picker) and on the shared read-only view, and **stamped on the PDF cover** — a document outlives the app's access controls, so the label travels on it. Verified live: classified a report, saw the badge, generated a stamped PDF. No admin-defined label catalog or export-blocking enforcement yet (the set is built in). |
| Client-side data limits | Yes | Yes | Yes | `DEFAULT_ROW_CAP = 10_000` with random-ordered sampling and a `sampled` flag surfaced in the widget header. SAS uses `maxRowsLookup` per object type (list table default 40,000). |
| Query diagnostics | Yes | Yes | Yes | |
| Performance + accessibility linting | Yes | Yes | Partial | SAS's Review pane covers both, ranks findings High/Medium/Low across 10+ issue types with published thresholds (object load >19 s, report load >25 s, ≥9 data sources, nested containers), exports a PDF and auto-fixes some issues. Power BI's Performance Analyzer covers performance only. **Shipped 2026-08-23.** The Review pane covers both: runtime perf stats (duration, row counts, rule errors) and the accessibility checks, in one ranked list. |
| Audit log | Yes | Platform | Yes | **Shipped 2026-08-22.** Append-only `audit_log` written in the mutating transaction (the entry lands iff the action lands), covering report create/delete, dataset delete and whole-table export — the read that moves data out of the org boundary. Denormalised email so the trail outlives the user row; admin-only org-scoped reads. |
| Gateway management | No | Platform | Yes | |
| Deployment pipelines (dev → test → prod) | No | Yes | Yes | |

## 13 — Accessibility (11 rows)

| Capability | datalytics | SAS VA | Power BI | Note |
|---|---|---|---|---|
| Alternative text per object | Yes | Yes | Yes | **Shipped 2026-08-21.** `cfg.alt_text`, authored via the config panel's "Widget description (screen readers)" field, is read by `WidgetRenderer.tsx` as the `aria-label` on the widget's `role="figure"` container (`WidgetRenderer.tsx:251-252`), verified by a passing render test. SAS's identification order is alt text → title → object name; datalytics's alt text simply overrides the title-derived label when set. |
| Heading styles for screen readers | Yes | Yes | Partial | **Shipped 2026-08-22.** Widget titles are `role="heading"` `aria-level={3}`, under the report name and page title, so a screen-reader user can navigate a report by its headings. |
| Keyboard navigation | Yes | Yes | Yes | Widgets are focusable, tab order is editable, and a visible focus ring landed with the MCAIT design system (`index.css`, `:focus-visible`) — until then the custom button and input styling suppressed the browser default, so keyboard users had no indicator at all. **Completed 2026-08-23:** a real shortcut set (arrows move, shift-arrows resize, Delete, Escape) with an in-product reference on `?`. |
| Tab order control | Yes | Yes | Yes | `TabOrderPane.tsx` writes sequential `tabIndex` values into widget config. |
| High-contrast theme | Yes | Yes | Yes | **Shipped 2026-08-22.** A `contrast` palette (`themes.ts`) built from Okabe-Ito and reordered by alternating luminance, so consecutive series differ in brightness as well as hue and stay separable in greyscale. Selected from the report theme picker like any other palette. |
| Line patterns to distinguish series | Yes | Yes | Partial | **Shipped 2026-08-22.** `seriesDash` applies a per-series dash pattern on the multi-series line renderers when `series_patterns` is set, as redundant encoding alongside colour. Off by default; the first series stays solid. Enabled by the viewer via SAS's high-contrast theme override — datalytics makes it an author choice instead. |
| Fill patterns to distinguish groups | Yes | Yes | No | **Shipped 2026-08-24.** The filled-mark counterpart to line patterns: `PatternDefs`/`fillPattern` (`chartUtils.tsx`) hatch grouped-bar series and pie/donut slices with per-group SVG textures (diagonal, dots, grid, checker, …) as redundant encoding alongside colour, so groups stay separable in greyscale or under colour blindness. Each tile keeps the group's colour as its ground and draws a luminance-chosen motif on top, so colour is preserved *and* textured. Injected into the recharts SVG via `<Customized>`; the first group stays solid (a lone group needs no texture). Gated by the same `series_patterns` opt-in as line dashes, now given a real author control — a `patterns` formatting capability (`widgetCapabilities.ts`) surfaces a "Distinguish groups by pattern (accessible)" toggle only on the bar/pie/donut and dual-axis/comparative renderers that honour it. Off by default, so existing reports are unchanged. This also makes row *Line patterns to distinguish series* an actual author choice rather than an orphaned flag. |
| RTL / bidirectional text | Yes | Partial | Partial | Per-widget `rtl` flag flips axis orientation and text direction across every renderer. **datalytics leads here.** |
| Fixed axis ranges for sonification | Partial | Yes | Partial | Fixed Y min/max shipped 2026-08-20 (`y_min`/`y_max`, the yDomain capability) — the range-pinning half of this row. Partial, not Yes: sonification itself does not exist here, and this row is about ranges *in service of* stable pitch mapping. |
| Accessible table alternative to a chart | Yes | Yes | Yes | **Completed 2026-08-23:** per-visual "Show as table" renders the chart's own shaped result as real cells, so the two presentations cannot disagree. |
| In-product accessibility linting | Yes | Yes | No | Part of SAS's Review pane. **Shipped 2026-08-23.** Alt-text and title checks in the Review pane, severity `error` — they exclude a viewer, not merely degrade. |

---

## Tally

| Category | Rows | datalytics Yes | Partial | No |
|---|---|---|---|---|
| 01 Platform & connectivity | 15 | 9 | 2 | 4 |
| 02 Data preparation | 19 | 18 | 1 | 0 |
| 03 Calculation engine | 23 | 16 | 2 | 5 |
| 04 Visual types | 45 | 37 | 3 | 5 |
| 05 Geo & mapping | 15 | 11 | 0 | 4 |
| 06 Advanced & augmented analytics | 20 | 8 | 3 | 9 |
| 07 Formatting & display rules | 28 | 26 | 1 | 1 |
| 08 Interactivity | 32 | 24 | 4 | 4 |
| 09 Layout, containers & templates | 16 | 14 | 0 | 2 |
| 10 Report editor shell | 17 | 15 | 2 | 0 |
| 11 Distribution & export | 21 | 15 | 3 | 3 |
| 12 Governance & security | 14 | 9 | 2 | 3 |
| 13 Accessibility | 11 | 9 | 1 | 1 |
| **Total** | **276** | **211** | **24** | **41** |

**276 rows: 211 Yes, 24 Partial, 41 No** (≈76.4% Yes). That overshoots the 150–200 target set when planning —
the visual-types and interactivity categories turned out genuinely that granular. Counts above are
machine-counted from the tables in this file (a scratch `count_gap_tally.py` over the scored column,
re-run 2026-08-22), not estimates; per-category
counts sum to 276 and match each category's declared row count. The counter reads only the `datalytics`
column and stops at this section: the Tally header row's own cells include the literal words "Partial"
and "No", which a counter run past the last category reports as one extra scored row.

**Re-scored 2026-08-22 against the code at `8d34757`.** The 2026-08-21 figure was 124/26/126 (≈44.9%).
A whole-branch review then found four blocking interaction defects, and its finding I4 held that three rows
scored Yes — table totals, crosstab subtotals and gauge interval rules — overstated capability, because
the control was inert or broken in the configuration the panel itself produces. All four defects were fixed
(`81a2b44` through `8d34757`) and each of those three rows was re-traced end to end here: an author-reachable
control writes a config key, a backend branch on the path the panel's own output takes reads it, and a
renderer acts on it. All three hold as Yes on the evidence in their row notes; none was marked down and none
was waved through. The net change is in the other direction: **category 10's "Display rules pane" was
scored No against a pane that has existed since 2026-08-18** and became fully functional in the same fix
wave, so it moves from No to Yes, taking 10 from 8/3/6 to 9/3/5 and the total from 124/26/126 to 125/26/125.

**Re-scored 2026-08-23 against the code at `b8a89a9`.** The table above carries the current machine count
(180/26/70, ≈65.2% Yes); the paragraph before this one describes the 2026-08-22 state it superseded. The
movement since is the roadmap phases A–F (geo, export, parameters, scheduled delivery, containers/templates,
forecasting/sankey), the full row-by-row recount, the excellence sprint (Review pane, show-as-table,
keyboard navigation, kiosk), and today's batch of six: post-aggregate HAVING filters, custom category
order, the overview/scrolling axis, report-to-report links, set-parameter buttons, and `{{@name}}`
parameter embedding in text (which also moved "Fixed axis ranges for sonification" No→Partial on the
strength of the shipped y_min/y_max, with sonification itself honestly absent). Every moved row names its
mechanism in its own notes column, and each was driven in the running app before scoring.

**Re-scored 2026-08-23 (later the same day) against `a8e3eda`.** The step-based prep pipeline moved
data preparation from 12/2/5 to 14/3/2: the transformation editor and aggregated/pre-summarised source
to Yes, source-table cell editing to Partial (value replacement ships non-destructively; per-cell edits
and write-back deliberately do not). The same commit closed a latent governance hole the feature would
have made live: PUT /column-meta replaced the whole map and would have wiped `__exports_disabled__` and
the new `__prep_steps__` on any bulk column edit — it now preserves reserved keys and refuses to write
them directly. Report-layer joins followed the same day (`ffda3dc`), taking the category to
15/3/1 — its last No, the reusable data view / semantic bundle, closed the same day (`70f0abe`) — the category's first-ever zero-No state, with the honest Partials (cross-source mapping, cell editing) as the remainder — outlier impact completed later the same day (`ef364e9`).

## Where datalytics leads

Three areas where this app is ahead of at least one competitor, and one where it is ahead of both:

1. **Governance was built in, not bolted on.** Org-level multi-tenancy, roles, and row-level
   security with fail-closed semantics and SQL pushdown exist without a licence tier or a separate
   admin product. In Power BI, tenant isolation is a service concern; in SAS, RLS lives in CAS
   authorisation and Environment Manager.
2. **Live query needs no premium tier.** DirectQuery-equivalent behaviour — aggregate pushdown, row
   caps with honest `sampled` flags, per-source cache TTL — ships in the base product. SAS requires
   the data to be loaded into CAS first.
3. **SAS-native chart types Power BI has no native answer to.** Eleven of them, already shipped:
   needle plot, dot plot, butterfly, vector plot, bubble change, comparative time series, numeric
   series, parallel coordinates, schedule/Gantt, step plot, word cloud — plus box plot, histogram
   and correlation matrix, which Power BI either lacks or requires manual workarounds for.
4. **RTL support is per-widget and pervasive**, threaded through every renderer rather than being a
   report-level setting. Both competitors treat bidirectional text more shallowly.

## The three gaps that matter most

Ranked by how much they constrain what a user can accomplish, not by implementation cost:

1. **Export and distribution** (category 11) — **first rows closed 2026-08-22**, now 1 Yes /
   2 Partial / 18 No. Per-widget data export to Excel and CSV shipped, resolving through the same
   path the display uses so row-level security reaches the file. Still the top-ranked gap by a wide
   margin: there is no PDF, no image, no print layout, no scheduling, no email or Teams delivery, no
   alerts, no shareable link. The next most valuable pieces are **PDF/print** (the format people
   actually circulate) and **scheduled email delivery** (what makes a report arrive without anyone
   opening the app); both are larger than the data export was, since PDF needs headless rendering
   and scheduling needs a job runner and SMTP.
2. **Geo mapping** (category 05) — zero of 15 rows, and the only category where both competitors
   score near-full marks. It is also the most self-contained: one library, one shaper family, one
   renderer family, no changes to the calculation or security model.
3. **Formatting and display rules** (category 07) — **largely closed 2026-08-18, then corrected
   2026-08-19.** The display-rules engine shipped: expression, value-map and interval rules
   targeting mark, background or visibility, plus report-level rules, moving 11 of 28 rows off No
   (row detail above). Only 9 of those 11 landed as a clean Yes, though — a whole-branch review
   found `DisplayRulesPanel.tsx`, the only UI for authoring a rule, builds exclusively
   `kind: "expression"` rules, so `value_map` and `interval` rules (colour-mapped categories and
   gauge/KPI bands) are reachable only by hand-editing JSON through the API and score Partial, not
   Yes, until the panel grows editors for them. The same review also found a "Widget background"
   rule wrote its colour to the wrong style key end-to-end (silently doing nothing), DirectQuery's
   histogram/correlation-matrix/count-series pushdown paths bypassed the rule engine entirely, only
   4 of the app's 31 chart renderers actually painted a mark from a rule, and a rule-hidden widget
   left its frame on screen around an empty body in view mode — all fixed 2026-08-19, alongside a
   rule-count/expression-length cap since a rule list is attacker-choosable client input that runs
   a sandboxed eval per entry. This claim rests on the automated backend and frontend suites — it
   was not additionally confirmed by hand in a running app for this document.

   **Updated 2026-08-20.** Axis and chart formatting then shipped — fixed axis min/max, logarithmic
   scale, axis label/tick/line styling, configurable grid lines, legend placement and opt-in data
   labels, threaded through all 20 Recharts-Cartesian renderers behind a capability map so an option
   is never offered where no renderer can honour it. That left 10 rows still No in this category:
   table totals and subtotals, cell styling, per-object background/border/padding, alternative text,
   the per-object data-limit override, data skins, a custom theme format, the overview/scrolling
   axis (closed 2026-08-23), and periodic auto-reload.

   **Closed 2026-08-21.** Table totals, crosstab subtotals, table cell styling (row numbers, row
   lines, banding, condensed height), per-object background/border/radius/padding, and per-object
   alternative text all shipped, moving five rows off No. The `DisplayRulesPanel.tsx` authoring gap
   flagged in the paragraph above also closed: it now offers "Colour map" and "Bands" rule kinds
   (`ValueMapEditor.tsx`, `IntervalEditor.tsx`), so `value_map` and `interval` rules move from
   Partial to Yes — the engines were already shipped and tested, this only added the missing
   authoring surface. That leaves **5 rows still No** in this category: the per-object data-limit
   override, data skins, a custom theme format, the overview/scrolling axis (since closed,
   2026-08-23), and periodic
   auto-reload — plus alerts, which is not a row in this category at all (it is the other half of
   the roadmap's sub-project 4, "Display Rules & **Alerts**", and remains entirely unbuilt). Category
   07 is no longer the second-largest block of unshipped rows (categories 05, 08 and 11 all have
   more); it stays listed here because a data-limit override and a custom theme are the kind of
   thing an author reaches for constantly, not because of row count.

   **Verified 2026-08-22, and the 2026-08-21 claim above was premature.** The whole-branch review of
   `table-chrome-and-rule-editors` found that four of the capabilities counted as closed on 2026-08-21
   did not work when reached through the UI: `show_totals`/`show_subtotals` were read only on a code
   path a table with the *required* `category` role never takes, so the checkbox did nothing in the
   configuration the Fields pane steers every author into; "Show row subtotals" was offered pre-checked
   on plain tables where no subtotal column can exist; the new Colour map and Bands editors rendered no
   Column control, so a Bands rule authored the obvious way pointed at the categorical column and errored
   on every render with nothing on screen to fix; a Fill swatch above both editors painted nothing at the
   default target; and DirectQuery totals summed a random 10,000-row sample. All are fixed and re-reviewed
   clean, and the affected rows were re-traced writer — reader — renderer for this document rather than
   trusted. The lesson the category keeps re-teaching is that a config key with a live consumer is not the
   same claim as a capability an author can reach: check the branch the panel's own output actually
   takes.

**Closed since this document was first written:** post-aggregation measures, which had been ranked
first here, and **text functions**, which had been ranked third — 17 of them shipped on 2026-08-17
(category 03). Each category row records what shipped and what is still outstanding inside it.

Categories 06 (advanced analytics) and 09 (containers) are larger in row count but each needs new
dependency surface — ML/stats libraries, or a `parent_id` on `ReportWidget` plus recursive layout —
so they are better sequenced after the three above.
