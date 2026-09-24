# Core Platform Architecture (Data Engine, Layout, Feature Modules, AI Insights)

**Date:** 2026-08-15
**Status:** Draft — architecture/vision

## Overview

This is a **forward-looking architecture spec**, not an implementation-ready design. Unlike
`2026-08-13-row-level-security-design.md`, which could be built directly from its phase list, most
of what follows describes systems that do not exist yet. Its job is to name the four subsystems
this platform is growing toward, record which decisions have already been made, and — critically —
draw an honest line between what is already built and what is aspiration, so that later specs can
be carved off it without re-litigating the shape of the whole.

The four subsystems:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          DATA PROCESSING ENGINE                             │
│                                                                             │
│  ┌──────────────────┐    ┌────────────────────┐    ┌─────────────────────┐  │
│  │ In-Memory        │    │ Semantic & Query   │    │ Pushdown & Vector   │  │
│  │ Columnar Storage │    │ Translation Layer  │    │ Aggregations        │  │
│  └────────┬─────────┘    └─────────┬──────────┘    └──────────┬──────────┘  │
└───────────┼────────────────────────┼──────────────────────────┼─────────────┘
            ▼                        ▼                          ▼
```

One piece of this is **not** vision-level and has already been carved off into its own
implementation-ready spec: **DirectQuery** — see
`docs/superpowers/specs/2026-08-15-directquery-design.md`. It is a firm near-term requirement, and
this document deliberately does not duplicate its detail.

A note on form: the other specs in this directory use prose, tables and code blocks with no
diagrams. This one keeps the block and pipeline diagrams because it is explicitly an architecture
document and the diagrams carry the decomposition — a deliberate departure, not an inconsistency.

## Current State (platform-wide)

Where this codebase actually stands today, since three of the four sections below build on top of it:

- **Everything is pandas.** No DuckDB, Polars or Arrow anywhere in `backend/`. Aggregation happens
  in `backend/app/services/widget_data.py` — `_agg_series`/`_pandas_agg_fn` (`:72`, `:95`) map an
  aggregation name onto a pandas operation against an already-loaded DataFrame.
- **Everything is a file.** `load_file` (`backend/app/services/analytics.py:20`) reads
  csv/xlsx/json/parquet from disk. External connections
  (`backend/app/services/connections.py`) exist but are import-only — they materialize to a file
  and are never consulted again at render time.
- **Multi-tenancy and row-level security are done.** `backend/app/core/org_scope.py` (`check_org`)
  and `backend/app/core/rls.py` (`resolve_rls_expr`) are implemented and wired into every router,
  with `apply_rls_filter` in the query path (`widget_data.py:1108`). New subsystems inherit these
  rather than re-inventing them.
- **There is already a caching layer.** An LRU widget-result cache
  (`widget_data.py:1036-1085`), keyed on file identity + config + RLS expression.

## 1. Data Processing Engine

### Current state

Aggregation is pandas groupby over a fully-materialized DataFrame, single-threaded, with the whole
dataset resident in memory. The "smart caching layer" described below is the one component that
partially exists: the LRU cache at `widget_data.py:1036` already memoizes widget results keyed on
config and RLS expression, though it caches only final results, not intermediate aggregates.

### Proposed

**In-Memory Columnar Database.** *(Greenfield — decision made: DuckDB.)*
- **Vectorized processing:** columnar chunk processing (SIMD) rather than row-at-a-time, for
  analytical aggregations (`SUM`, `COUNT`, `AVG`).
- **High-ratio compression:** Run-Length Encoding, dictionary encoding and bit-packing to compress
  raw datasets 80–90% in RAM.
- **Partitioning & chunking:** dividing large tables across memory spaces for parallel execution.

DuckDB was chosen over Polars/Arrow specifically because it is a *SQL* engine: it lets one query
translation layer serve both execution modes — DuckDB SQL over local parquet for import datasets,
native dialect SQL over the live source for DirectQuery — instead of maintaining a DataFrame API
path and a SQL path in parallel. `load_file` already reads parquet, so the storage format is
already compatible.

**Semantic Calculation & Translation Layer.** *(Mostly greenfield.)* A nascent semantic layer
exists: `Dataset.calculated_columns` and `Dataset.column_formats` (`models.py:19-20`, with
`CalcColumnsPanel.tsx`/`ColumnFormatsPanel.tsx` on the frontend), plus `HierarchyNode.aggregation`
and `format` (`models.py:103-104`) for hierarchy-level measures. There is a real, security-hardened
expression evaluator (`_validate_expr_safety`, `widget_data.py:766`) that the DirectQuery spec
reuses as its SQL translation front end.

What does not exist: a unified expression language with time-intelligence (YTD, YoY), dynamic
measures and window functions; a multi-dialect translator (drag-and-drop → AST → native SQL / DuckDB
/ Spark); and caching of *intermediate* aggregates rather than only final widget results.

**Pushdown & Vector Aggregations.** *(Specified separately.)* Fully designed in the DirectQuery
spec — including the grain invariant that makes pushed-down aggregation safe to feed into the
existing shapers unchanged.

### Computation Strategy Matrix

| Metric | Import Mode (In-Memory) | Direct Query (Live) | Hybrid / Dual Mode |
|---|---|---|---|
| Storage location | Internal columnar RAM | External warehouse | RAM (aggregates) + DB (raw) |
| Query latency | Sub-second (<100ms) | Source dependent (0.5s–5s) | Fast summary, sub-second drill-down |
| Max scale | Limited by memory allocation | Petabyte scale | Multi-terabyte scale |
| Data freshness | Scheduled / event-driven sync | 100% real-time | Near real-time |

Status per column: **Import Mode** exists today but as pandas-over-files, not a columnar engine —
the latency and compression claims describe the DuckDB target, not current behavior. **Direct
Query** is specified and scheduled. **Hybrid** is not designed; it depends on both of the others
and is explicitly excluded from the DirectQuery spec's v1.

## 2. Layout Engine

### Current state

**Grid mode already exists**, hand-rolled rather than from a library — there is no
`react-grid-layout` or `dnd-kit` dependency. `frontend/src/pages/ReportBuilder.tsx` implements a
12-column grid (`COLS = 12`, `ROW_H = 58`, `GAP = 8`, with `cellW` derived from container width at
`:25`) and manual mouse-driven drag and resize handlers that snap `x`/`y`/`w`/`h` to grid cells
(`:236`, `:243`). Layout persists as JSON on `ReportWidget.layout` (`models.py:90`, defaulting to
`{"x": 0, "y": 0, "w": 6, "h": 4}`).

Freeform mode and AI auto-layout are greenfield.

### Mode Comparison & Capabilities Matrix

| Capability | Freeform Mode | Grid Mode | AI Auto-Layout Mode |
|---|---|---|---|
| Design precision | Pixel-perfect (absolute) | Snap-to-grid alignment | Intelligent automated layout |
| User skill level | Advanced / designers | Intermediate / analysts | Beginner / speed-focused |
| Widget overlapping | Supported | Not supported | Not supported |
| Responsive behavior | Scale-to-fit aspect ratio | Column reflow per breakpoint | Smart auto-reflow by priority |
| Primary use case | Executive presentations | Operational dashboards | Rapid prototyping & AI insights |

The **Grid Mode** column describes today's behavior, with one gap: column reflow per breakpoint is
not implemented — the current grid is fixed at 12 columns and scales `cellW` with the container
rather than reflowing.

Because layout is already persisted as an open `{x, y, w, h}` JSON blob, adding modes is a matter of
tagging the report with a layout mode and extending that blob (absolute pixel coordinates plus a
z-index for freeform), not migrating a schema.

## 3. Key Feature Modules

| Category | Feature Module | Strategic Importance |
|---|---|---|
| User experience | Pixel-Perfect Canvas | Absolute positioning, responsive layouts, customizable themes, and cross-filtering |
| Data modeling | Visual Data Preparator | No-code ETL pipelines, join models, calculated columns, and measure definitions |
| Collaboration | Sharing & Embeddability | Web embedding (iframe/JS SDK), scheduled PDF export, and commentary/annotation layers |
| Extensibility | Custom Visual SDK | Open framework (Web Components/D3) letting developer teams build proprietary visuals |

Status per module:

- **Pixel-Perfect Canvas** — partially built. **Cross-filtering already works**: every chart
  renderer takes `broadcasts`, `localSelected` and `onClickPoint`
  (`frontend/src/components/report/chartRenderers/types.ts`), so clicking a mark in one widget
  broadcasts a selection to the others. Absolute positioning and themes are the gap (see §2).
- **Visual Data Preparator** — partially built. Calculated columns and column formats exist
  (`models.py:19-20`); no-code ETL pipelines and visual join models do not.
- **Sharing & Embeddability** — entirely greenfield. There are no share, token, embed or export
  fields on any model and no corresponding router. Note this module now has a real prerequisite in
  place: org scoping and RLS are implemented, so sharing can be designed against an existing
  permission model instead of inventing one.
- **Custom Visual SDK** — greenfield, but with a strong existing foundation. The
  `shape_*(df, config) -> dict` convention in `widget_data.py` (registry at `:682` mapping 32
  widget types onto 14 shapers, dispatch at `:745`), with each widget type paired to a renderer in
  `frontend/src/components/report/chartRenderers/`, is already the extension point an SDK would
  formalize. An SDK is mostly a matter of turning an internal convention into a stable, documented,
  versioned contract — with the shaper's DirectQuery strategy tag (see the DirectQuery spec) as
  part of that contract.

## 4. AI Insights Engine

```
                 DATASET
                    │
                    ▼
          ┌───────────────────┐
          │ Data Profiling    │
          │ & Type Detection  │
          └─────────┬─────────┘
                    │
                    ▼
          ┌───────────────────┐
          │ Semantic Role     │
          │ Detection         │
          └─────────┬─────────┘
                    │
        ┌───────────┼────────────┐
        ▼           ▼            ▼
   Feature       Association   Anomaly
   Selection      Mining       Detection
        │           │            │
        ▼           ▼            ▼
   MI / RF /     FP-Growth     Isolation
   SHAP / LASSO                 Forest
        │           │            │
        └───────────┼────────────┘
                    ▼
            AI INSIGHTS ENGINE
                    │
                    ▼
          ┌──────────────────────┐
          │ Recommended Charts   │
          │ Relationships        │
          │ Insights             │
          │ Predictions          │
          └──────────────────────┘
```

### Current state

**The first box is real.** `run_full_analysis` (`backend/app/services/analytics.py:130`, exposed via
`backend/app/routers/analysis.py` as `POST`/`GET /datasets/{id}/analysis`) already performs
genuine classical profiling: type detection over numeric/datetime/categorical/text heuristics
(`detect_types`, `:35`), numeric descriptive statistics with IQR outliers and skew/kurtosis
(`analyze_numeric`, `:57`), a Pearson correlation matrix, categorical value counts and entropy with
chi-square tests (`analyze_categorical`, `:82`), and datetime range/gap analysis
(`analyze_datetime`, `:110`). Results persist to `AnalysisResult` (`models.py:44`).

**Everything below that box is greenfield.** There is no scikit-learn dependency and no anomaly
detection, feature selection, association mining or recommendation code anywhere in `backend/app`.

### Proposed

- **Semantic role detection** — beyond dtype inference: identifying identifiers, measures,
  dimensions, geography, currency and time grain, so the recommendation stage knows what a column
  *means*, not just what it holds. This is the layer that feeds `resolve_roles`
  (`widget_data.py:726`) automatically instead of relying on the user's drag-and-drop.
- **Feature selection** — mutual information, random-forest importance, SHAP, LASSO.
- **Association mining** — FP-Growth over categorical co-occurrence.
- **Anomaly detection** — Isolation Forest, complementing the existing IQR outlier detection which
  is univariate only.
- **Outputs** — recommended charts (a ranked list of widget configs the existing `SHAPERS` registry
  can already render), discovered relationships, natural-language insights, and predictions.

Recommended charts are the highest-leverage output and the cheapest to reach: because a widget is
just a `{widget_type, config}` pair the existing pipeline renders, the recommender only has to emit
configs, not draw anything.

## Sequencing

The subsystems are ordered by dependency, not ambition:

1. **DirectQuery** (specified, `2026-08-15-directquery-design.md`) — everything else queries data;
   the execution model should settle first.
2. **Columnar engine (DuckDB) for import mode** — reuses the SQL translation layer DirectQuery
   introduces, which is why DirectQuery's SQL builder is designed for two dialects from the start.
3. **Layout Engine and Key Feature Modules** — largely frontend, independent of the above, and
   parallelizable.
4. **AI Insights Engine** — last. It is the most research-heavy, has the least certain output
   quality, and benefits from a stable query layer beneath it.
5. **Hybrid/dual mode** — requires both 1 and 2, so it cannot be scheduled before them.

Each of these needs its own design spec before implementation; only DirectQuery has one so far.

## Open Questions

- **Semantic layer scope.** Time-intelligence and window functions imply a measure definition
  language. Whether that is a new DSL or an extension of the existing calculated-column expression
  syntax (`_validate_expr_safety`) is undecided and materially affects the translation layer.
- **Where the AI in "AI Auto-Layout" and the insights engine comes from.** Classical ML
  (scikit-learn, in-process) and LLM-based generation are very different dependency, latency, cost
  and privacy profiles — sending customer data to a model provider is a governance decision, not a
  technical one, and should be settled before either subsystem is specified.
- **Breakpoint reflow for grid mode** — listed as current capability in the matrix above but not
  implemented; worth confirming whether it belongs to the Layout Engine work or is a bug-level gap.

## Files Changed

Nothing is implemented from this document — it is an index of intent. Representative future
touch-points, by subsystem:

| File | Change | Subsystem |
|---|---|---|
| `backend/app/services/direct_query.py` | New — see the DirectQuery spec | §1 (specified) |
| `backend/app/services/columnar.py` | New — DuckDB engine, parquet-backed import mode | §1 (future) |
| `backend/app/services/semantic.py` | New — measure/time-intelligence definitions, AST → dialect | §1 (future) |
| `backend/app/services/widget_data.py` | Aggregation delegated to the engine rather than pandas | §1 (future) |
| `frontend/src/pages/ReportBuilder.tsx` | Freeform + AI auto-layout modes alongside the existing grid | §2 (future) |
| `backend/app/models/models.py` | `Report.layout_mode`; share/embed/export fields | §2, §3 (future) |
| `backend/app/routers/sharing.py` | New — share links, embed tokens, scheduled export | §3 (future) |
| `docs/` visual SDK contract | New — formalize the `shape_*` + renderer pairing | §3 (future) |
| `backend/app/services/insights.py` | New — role detection, feature selection, anomalies, recommendations | §4 (future) |
| `backend/requirements.txt` | `duckdb`; `scikit-learn`/`mlxtend` if §4 goes the classical-ML route | §1, §4 (future) |
