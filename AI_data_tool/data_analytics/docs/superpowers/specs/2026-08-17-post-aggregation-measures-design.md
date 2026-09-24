# Post-Aggregation Measures

**Date:** 2026-08-17
**Status:** Design spec — not yet implemented
**Supersedes:** the "Expression / Calculation Engine — Advanced" row in
`docs/superpowers/specs/2026-08-17-three-way-gap-analysis.md` as the authoritative
plan for the calc-engine's highest-leverage gap
**Depends on:** existing expression sandbox (`widget_data._validate_expr_safety`,
`_build_safe_ns`), row-level calculated columns, widget shaper registry, DirectQuery
aggregate pushdown (`docs/superpowers/specs/2026-08-15-directquery-design.md`)

## Overview

Every expression in this app today evaluates **per row before aggregation**. The
shaper then groups and aggregates a single column (`config.measure`) with a fixed
aggregation (`config.aggregation`). That makes `PCT_TOTAL(sales)` a row-level
percentage broadcast to every row in a group — not a dynamic percent-of-total that
changes when the visual's dimension crossing changes. SAS aggregated measures and
Power BI DAX measures both evaluate **after** aggregation, in the filter context and
visual grain of the requesting widget.

This spec adds **measures**: named, reusable expressions stored on the dataset,
evaluated after filters and row-level calculated columns but **at the visual's
grouping grain**, so ratios, margins, and percent-of-total vary correctly by chart
crossing. This is the single largest calc-engine gap identified in the three-way
gap analysis and is upstream of display rules, parameters, ranks, and quick
calculations all becoming meaningfully useful.

## Current State

- **Row-level calculated columns** — `Dataset.calculated_columns` JSON
  (`models.py:19`), CRUD at `routers/datasets.py`, evaluated by
  `apply_calculated_columns` (`widget_data.py:1042`) in the query pipeline **before**
  the shaper runs.
- **The query pipeline (import mode)** — `get_widget_data` (`widget_data.py:1139`):
  `load_file` → `apply_rls_filter` → `apply_filter_expr` →
  `apply_calculated_columns` → `get_widget_data_from_df` → shaper `groupby`/`agg`.
- **Aggregation functions in expressions** — `SUM`/`AVG`/etc. in `_build_safe_ns`
  (`widget_data.py:868-878`) return a **scalar broadcast across all rows** of the
  filtered dataframe. They do not know the widget's dimension assignments.
- **Fields pane** — `ReportBuilder.tsx:520` groups columns into Measures vs Dimensions
  by `dtype === 'numeric'`. Calculated columns appear in both lists by dtype. There
  is no distinct measure concept in the UI or API.
- **DirectQuery** — aggregate pushdown produces a pre-aggregated frame and hands it
  to the same shapers. Calculated columns are currently rejected for DirectQuery
  datasets (`routers/widget_data.py:28-29`). Measures will follow the same phased
  rollout: import mode first, DirectQuery in a later phase.
- **Broken UI snippets** — `CalcColumnsPanel.tsx` Text and Date palettes insert
  `.str.*` / `.dt.*` snippets that `_validate_expr_safety` rejects. A separate quick
  fix aligns those palettes with functions the row-level engine actually supports;
  measures are a distinct authoring surface.

## Goals

1. Authors can define a **measure** on a dataset — a named expression evaluated at
   query time in the widget's filter context and grouping grain.
2. **Percent-of-total works correctly**: a measure assigned to a bar chart's Y role
   shows each category's share of the filtered total, not a row-level constant.
3. Measures are **reusable** across widgets and reports on the same dataset, with
   optional default display format and default aggregation metadata.
4. The existing row-level calculated-column path is **unchanged**. Measures are a
   parallel concept, not a breaking change to `calculated_columns`.
5. Expression safety is **unchanged or stricter** — same AST allowlist, same
   fail-closed RLS semantics, measures included in cache keys when referenced.

## Non-Goals (this spec)

- Text functions, periodic functions, `AggregateTable`, `AggregateCells`, scoped
  per-intersection overrides (SAS-style), or full DAX parity — tracked separately
  in the gap analysis category 03 backlog.
- Post-aggregate **filters** (filter on aggregated value) — a natural follow-on once
  measures exist; not in the first delivery.
- DirectQuery SQL pushdown of measure expressions — Phase 4 of the implementation
  plan; Phases 0–3 are import-mode only with an explicit error for DirectQuery.
- Replacing widget-level `config.aggregation` with per-measure aggregation for every
  widget type in Phase 1 — Phase 1 covers the `shape_series` family only.

## Data Model

One new JSON column on `Dataset`, following the existing `_migrate()` convention in
`backend/app/main.py`:

```python
measures = Column(JSON, default=list)   # list[MeasureDef dicts]
```

Each measure is stored as:

```python
{
    "name": str,                          # unique within dataset, like calc column names
    "expression": str,                    # e.g. "SUM(profit) / SUM(revenue) * 100"
    "default_aggregation": str | None,  # hint for Fields pane / auto-assign; default "sum"
    "format": CalcColumnFormat | None,  # same shape as calculated_columns[].format
}
```

Naming rules match calculated columns: unique within the dataset, no collision with
base column names. A widget role may reference either a base column, a calculated
column, or a measure by name — resolution checks `measures` first when the name is
not a physical column.

## Measure Expression Semantics

### Filter context

A measure evaluates over the dataframe **after** all of these have been applied, in
order:

1. Row-level security (`apply_rls_filter`)
2. Dataset default filter expression (`apply_filter_expr`)
3. Widget-level filters (`config.filters` — includes cross-filters merged by the
   frontend)

Row-level calculated columns are applied before the shaper, so measure expressions
may reference calculated column names as if they were base columns.

### Visual grain

The **grouping columns** come from the widget config:

| Widget shape | Grouping columns |
|---|---|
| `shape_series` (bar, line, pie, …) | `config.dimension` |
| Crosstab | `config.dimension`, `config.dimension2` |
| KPI / scalar (no dimension) | `[]` (single aggregate row) |
| Card (multi-measure) | `[]` per measure independently |

All aggregation functions inside a measure expression (`SUM`, `AVG`, `COUNT`, …)
aggregate **within each group** defined by the visual grain, not over the entire
dataframe.

### TOTAL — grand total ignoring dimension breakdown

`TOTAL(expr)` evaluates `expr` over the **entire filter context** with **no
dimension grouping** — the visual equivalent of Power BI's `ALL(dim)` on the
selected dimension or SAS's report-level total. Used for percent-of-total:

```
SUM(sales) / TOTAL(SUM(sales)) * 100
```

`TOTAL` accepts any sub-expression that itself uses aggregation functions. Nested
`TOTAL(TOTAL(...))` is rejected at validation time.

### Column references

Bare column names in measure expressions refer to **physical or calculated columns**
on the filtered row set. They do **not** auto-aggregate — authors must wrap them in
`SUM(col)` / `AVG(col)` / etc., matching DAX/SAS aggregated-measure authoring style.

### Measure-on-measure references

Phase 1: **not supported** (expressions may reference base and calculated columns
only). Phase 2 adds `[Other Measure]` / bare measure-name references with dependency
ordering and cycle detection.

### Shared function catalog

Measures reuse the same `_validate_expr_safety` check and the same function names as
row-level expressions, but aggregation functions (`SUM`, `AVG`, …) bind to
**group-aware** implementations provided by the measure evaluator — not the
row-broadcast scalars in `_build_safe_ns`.

Functions available in measure expressions at launch:

- Conditional: `IF`, `SWITCH`, `isnull`
- Scalar math: `abs`, `round`, `min`, `max`, `int`, `float`, `str`, `len`, `pow`,
  `log`, `sqrt`, `exp`, `floor`, `ceil`
- Group aggregations: `SUM`, `AVG`, `MEDIAN`, `COUNT`, `COUNTD`, `STDEV`, `VARIANCE`
- Grand total: `TOTAL` (new, measure-only)
- No row-level window functions (`CUMSUM`, `LAG`, `GROUPSUM`, …) in Phase 1 —
  they require a row ordering concept that does not exist at aggregated grain.

## Query Path

### Import mode (Phases 1–3)

New module `backend/app/services/measure_eval.py`:

```
evaluate_measure(expr, df, group_cols, agg_fn_map) -> pd.Series | scalar
build_grouped_frame(df, group_cols, referenced_cols, agg_fn_map) -> DataFrame
resolve_widget_measures(df, config, widget_type, measures) -> effective measure values
```

Integration point — **inside shapers**, not after them, so each shaper's output
shape stays the same:

```python
# shape_series, simplified
group_cols = [dim] if dim else []
if meas_is_measure_name:
    values = evaluate_measure(measure_expr, df, group_cols)
    grouped = pd.DataFrame({dim: ..., "value": values})
else:
    grouped = df.groupby(dim)[meas].agg(agg_fn)   # existing path
```

`get_widget_data` pipeline becomes:

```
load → RLS → filter_expr → apply_calculated_columns → get_widget_data_from_df
                                                              ↓
                                                    shaper (measure-aware)
```

No change to the cache key structure except adding `measures` to the payload when
the widget config references a measure name (same pattern as `calculated_columns`).

### DirectQuery (Phase 4 — deferred)

DirectQuery datasets reject measure roles in Phases 0–3 with an explicit 400:
`"Measures are not yet supported for DirectQuery datasets"`.

Phase 4 explores SQL pushdown for measure expressions that translate to
`SUM(col) / SUM(col) OVER ()`-style window aggregates. Expressions that cannot be
translated fail closed with `DirectQueryUnsupported` — never silently wrong, per the
DirectQuery spec's rule.

## API

Mirror the calculated-columns CRUD on `routers/datasets.py`:

| Method | Path | Purpose |
|---|---|---|
| GET | `/{dataset_id}/measures` | List measures |
| POST | `/{dataset_id}/measures` | Create or replace by name |
| DELETE | `/{dataset_id}/measures/{name}` | Delete |
| POST | `/{dataset_id}/measures/preview` | Preview with optional `group_by` column |

Preview request:

```python
class MeasurePreviewRequest(BaseModel):
    expression: str
    group_by: Optional[str] = None   # simulate visual grain; None = scalar
    filters: list[dict] = []
    calculated_columns: list[Any] = []
```

Preview response matches calc-column preview: `{ ok, dtype, sample, error? }`. When
`group_by` is set, `sample` is the first N group values.

Widget-data requests pass measures from the dataset automatically (like
`calculated_columns` are merged in `routers/widget_data.py:25`):

```python
measure_defs = list(ds.measures or [])
# passed into get_widget_data(..., measures=measure_defs)
```

## Frontend

### MeasuresPanel

New component `frontend/src/components/report/MeasuresPanel.tsx`, structurally
parallel to `CalcColumnsPanel.tsx`:

- Header: "ƒx Measures" with Add button
- Expression builder modal reuses the same palette layout but:
  - **Aggregation** category functions bind to group-aware semantics (tooltip copy
    says "within current visual group")
  - Adds **TOTAL(expr)** to the Aggregation category
  - **No** Running & Rank or Group By categories (row-level only)
  - Text category remains removed/disabled until text functions ship
- Default aggregation dropdown: sum / avg / count / min / max (stored on measure def)

Mounted in `DatasetDetail.tsx` below calculated columns and in the Report builder
Fields sidebar (new "Measures" group above numeric columns).

### Fields pane

`ReportBuilder.tsx` Fields section becomes three groups:

1. **Measures** — dataset measures (ƒx icon, accent color)
2. **Columns** — numeric base + calculated columns (existing Measures group renamed)
3. **Dimensions** — unchanged

Clicking a measure assigns it to the selected widget's measure role. The widget-data
request sends the measure name in `config.measure` / `config.roles.measure`; the
backend resolves it against `dataset.measures`.

### Widget config / formats

When a measure has a `format`, it applies in renderers the same way calculated-column
formats do (`WidgetRenderer.tsx` effectiveCalcCols pattern extended to measures).

## Security

- Measures use `_validate_expr_safety` — no change to the AST allowlist.
- RLS is applied **before** measure evaluation; measures cannot bypass RLS.
- Measure preview endpoint requires auth + org scope, same as calculated-column preview.
- Cache keys include the verbatim measure expression when a measure is referenced,
  plus `rls_filter_expr` (unchanged isolation rule).
- Fail-closed: if measure evaluation raises, return `{ type: "error", message: ... }`
  from the widget-data endpoint rather than falling back to a base column.

## Testing Strategy

- **Unit tests** (`backend/tests/test_measure_eval.py`): `evaluate_measure` with
  synthetic DataFrames — percent-of-total, ratio, scalar KPI, empty filter context,
  single-group edge case.
- **Integration tests** (`backend/tests/test_widget_data_measures.py`): full
  `get_widget_data` path with CSV fixture, bar chart + measure, cross-filter
  simulation via `config.filters`.
- **Preview router tests**: preview endpoint returns expected sample for
  `SUM(sales) / TOTAL(SUM(sales)) * 100` grouped by region.
- **Frontend**: `MeasuresPanel` smoke test (list, add modal opens); Fields pane lists
  measures separately from columns.

## Phased Delivery

See `docs/superpowers/plans/2026-08-17-post-aggregation-measures.md` for task-level
detail. Summary:

| Phase | Delivers |
|---|---|
| **0 — Foundation** | Schema migration, schemas, CRUD + preview API, MeasuresPanel UI |
| **1 — Core engine** | `measure_eval.py`, `TOTAL`, `shape_series` + scalar KPI path, import mode |
| **2 — Coverage** | Card, crosstab, dual-axis; measure format in renderers; Fields pane wiring |
| **3 — Hardening** | Measure name collision validation, cache key update, error surfaces, docs |
| **4 — DirectQuery** | SQL window-aggregate translation for simple measures; explicit reject otherwise |

Each phase produces working, testable software on import-mode datasets.

## Success Criteria

1. A measure `Sales % of Total` with expression `SUM(sales) / TOTAL(SUM(sales)) * 100`
   on a bar chart by Region shows values summing to ~100% across visible categories,
   and changes when a cross-filter narrows the filter context.
2. A measure `Profit Margin` with `SUM(profit) / SUM(revenue) * 100` on a KPI card
   returns a single scalar without a dimension.
3. Row-level calculated columns and existing widgets without measures behave
   identically to today (no regressions in `backend/tests/`).
4. DirectQuery datasets return a clear 400 if a measure is assigned before Phase 4.

## Open Questions (resolved for v1)

| Question | Decision |
|---|---|
| Store measures separately or extend `calculated_columns` with a `kind` field? | **Separate `measures` column** — avoids breaking existing calc-column consumers and matches the semantic distinction. |
| Reuse `_build_safe_ns` or separate namespace? | **Separate `_build_measure_ns(grouped_df, grand_totals)`** — aggregation functions must not broadcast row-level scalars. |
| Which shapers in Phase 1? | **`shape_series` + scalar branch only** — covers bar, line, pie, KPI, treemap, funnel, area, step, dot, needle, word_cloud, ribbon. |
| Measure-on-measure in v1? | **No** — Phase 2. |
