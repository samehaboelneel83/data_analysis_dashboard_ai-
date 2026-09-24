# Chart Type Expansion (SAS VA Feature Parity — Phase 1: Charts)

**Date:** 2026-08-10
**Status:** Phase 3 Complete — all 28 planned chart types live (Vector Plot included per full-scope request, despite being flagged as droppable in the original phasing)

## Overview

`COURSE_1_narrations.txt` and `COURSE_2_narrations.txt` are the full transcripts of the SAS Visual Analytics 1 (Basics) and 2 (Advanced) training courses — together they describe ~150 distinct product features. That's too large for one design; it's being decomposed into independent sub-projects (chart types, expression/calculation engine, interactivity & navigation, display rules & alerts, geo maps, data joins, containers/templates, advanced analytics/ML, sharing/export), each specced and built separately.

This spec covers the first sub-project: **expanding the chart-type library** from the current 6 (Bar, Line, Pie, Donut, Scatter, Treemap) to 28, by adding 22 new chart types plus a cross-cutting Fit Lines overlay option. It also covers the architectural foundation needed to add them without the existing rendering/data-shaping code collapsing under its own weight.

## Problem: Current Architecture Doesn't Scale

- `ReportWidget.config` (`backend/app/models/models.py`) is a schema-less JSON blob. The 6 existing chart types overload the same `dimension`/`measure`/`aggregation` keys — there's no representation for multiple measures, size/color/group roles, or start/end ranges.
- `query_widget` (`backend/app/services/widget_data.py:115-242`) branches purely on which config keys are present (not on `widget_type`) and only ever produces two shapes: `{name, value}` series or a 2D pivot. This can't represent bubble (x/y/size/color), box plot (quartiles), waterfall (running deltas), gantt (start/end), correlation matrix (pairwise stats), or parallel coordinates (multi-column rows).
- `WidgetBody` in `frontend/src/components/report/WidgetRenderer.tsx` (543 lines) is a sequential `if (wt === 'bar') return (...)` chain, not a dispatch table. `WidgetConfigPanel.tsx` similarly gates field pickers with hardcoded `if (wt === ...)` conditionals rather than a declarative spec.
- Scatter already shows the strain: it fakes x/y from `r.x ?? r.name, r.y ?? r.value` because there's no real two-measure data shape, and `WidgetConfigPanel` never actually sets `cfg.x_axis`/`y_axis` — that formatting path is dead code today.

Continuing to bolt 22 more types onto this pattern would make both files unmaintainable and several chart types (bubble, correlation matrix, parallel coordinates) literally cannot be expressed in the current shape.

## Phase 0: Foundation (no visible feature change)

### Roles model

`config.roles` replaces/augments the ad-hoc keys with a typed set of role slots. Which roles apply is declared per chart type (see Role Spec below):

```json
{ "roles": { "category": "region", "measure": "revenue", "measure2": "cost",
             "size": "unit_count", "color": "segment", "group": "channel",
             "start": "start_date", "end": "end_date", "label": "task_name" } }
```

Existing `dimension`/`measure`/`dimension2` keys remain readable (mapped to `category`/`measure`/`category2`) so existing saved reports don't need a migration script — old configs are interpreted the same way through a compatibility shim in the shaper lookup.

### Backend: shaper registry

`backend/app/services/widget_data.py` gains:

```python
SHAPERS: dict[str, Callable[[pd.DataFrame, dict], dict]] = {
    "bar": shape_series, "line": shape_series, "pie": shape_series,
    "donut": shape_series, "scatter": shape_xy, "treemap": shape_series,
    # ... new entries added per phase, see below
}

def get_widget_data(df, config, widget_type):
    shaper = SHAPERS.get(widget_type, shape_series)  # fallback preserves current behavior
    return shaper(df, config)
```

Each shaper returns a typed payload (`series`, `xy_series`, `matrix`, `multi_series`, `range_series`, `quartile_series`, etc.). The 6 existing types are migrated onto thin shapers wrapping their current logic — output must be verified identical before new types are added.

### Frontend: renderer registry

`frontend/src/components/report/WidgetRenderer.tsx` gains:

```ts
const CHART_RENDERERS: Record<WidgetType, React.FC<ChartRendererProps>> = {
  bar: BarChartRenderer, line: LineChartRenderer, /* ... */
}
```

`WidgetBody` becomes `const Renderer = CHART_RENDERERS[wt]; return <Renderer {...props} />` instead of the if-chain. Non-chart types (table, crosstab, list, text, button, kpi) keep their existing dedicated rendering (they aren't part of this chart-type expansion).

### Role spec table (drives config panel UI)

`frontend/src/types/report.ts` gains:

```ts
export const ROLE_SPECS: Record<WidgetType, RoleField[]> = {
  bar: [{ role: 'category', required: true }, { role: 'measure', required: true }],
  bubble: [{ role: 'category', required: false }, { role: 'measure', label: 'X axis', required: true },
           { role: 'measure2', label: 'Y axis', required: true }, { role: 'size', required: true },
           { role: 'color', required: false }, { role: 'group', required: false }],
  waterfall: [{ role: 'category', required: true }, { role: 'measure', label: 'Delta', required: true }],
  gantt: [{ role: 'category', label: 'Task', required: true }, { role: 'start', required: true },
          { role: 'end', required: true }, { role: 'group', required: false }],
  correlation_matrix: [{ role: 'measures', label: 'Measures', multi: true, required: true }],
  // ... one row per type
}
```

`WidgetConfigPanel.tsx` renders field pickers by iterating `ROLE_SPECS[wt]` instead of hardcoded conditionals. Adding a chart type never touches the panel's rendering logic — only adds a table row.

### Migration verification

After Phase 0 lands, manually re-open several existing saved reports and confirm bar/line/pie/donut/scatter/treemap render identically (same data, same visual output) before any new chart type is added.

## Chart Inventory & Phasing

22 new chart types (filtered from the raw transcript headers — "Descriptive Charts", "Part-to-Whole Charts", and "Time Variant Charts" are lesson-overview/category headers, not real chart types) plus one cross-cutting overlay:

### Phase 1 — Native Recharts composition (10 types)

Reuses `category`/`measure`/`measure2` roles. No custom SVG — built from `ComposedChart`, `LineChart`, `ScatterChart` primitives already available via Recharts.

| Chart | Roles | Recharts basis |
|---|---|---|
| Histogram | measure (binned server-side) | `BarChart` |
| Dual Axis Bar Chart | category, measure, measure2 | `ComposedChart`, 2 `YAxis` |
| Dual Axis Line Chart | category, measure, measure2 | `ComposedChart` |
| Dual Axis Bar-Line Chart | category, measure, measure2 | `ComposedChart` mixed `Bar`+`Line` |
| Dual Axis Time Series Plot | start(date), measure, measure2 | `ComposedChart`, time x-axis |
| Comparative Time Series Plot | start(date), measure, measure2 | `ComposedChart`, 2 `YAxis`, shared x-axis |
| Step Plot | category, measure | `LineChart` `type="stepAfter"` |
| Dot Plot | category, measure | `ScatterChart`, categorical y-axis |
| Needle Plot | category, measure | `ComposedChart` + `ReferenceLine` baseline |
| Numeric Series Plot | measure (x), measure2 (y) | `LineChart`, both axes numeric |

### Phase 2 — Relationship plots (6 items)

New `size`/`color`/`group` roles. Backend stats via existing numpy/scipy dependency. Moderate custom rendering.

| Chart | Roles | Notes |
|---|---|---|
| Bubble Plot | category?, measure(x), measure2(y), size, color?, group? | `ScatterChart` + `ZAxis` |
| Bubble Change Plot | Bubble Plot roles + animation(time) | Adds a time-scrubber player; depends on Bubble Plot |
| Correlation Matrix | measures (multi) | Custom grid; backend computes pairwise Pearson correlation |
| Heat Map | category, category2, measure | Custom grid, color-scaled cells |
| Fit Lines *(overlay, not standalone)* | — | Backend regression (linear/quadratic/cubic/best-fit/P-spline via numpy/scipy); overlay `Line` on scatter/bubble/heatmap |
| Parallel Coordinates Plot | measures/categories (multi, ordered) | Custom SVG; backend bins each measure |

### Phase 3 — Custom-rendered / niche (7 types)

Hand-built SVG or creative Recharts composition. `start`/`end` roles introduced here. Highest build cost.

| Chart | Roles | Rendering approach |
|---|---|---|
| Box Plot | category, measure | Custom shape (quartiles computed server-side) on `ComposedChart` |
| Waterfall Chart | category, measure | Stacked `Bar` with transparent base-value trick |
| Gauge | measure, target? | `RadialBarChart` |
| Schedule Chart (Gantt) | category(task), start, end, group? | Horizontal `BarChart` with transparent offset trick |
| Butterfly Chart | category, measure, measure2 | Mirrored horizontal bars via negative values |
| Word Cloud | category, measure(size) | New dependency: `d3-cloud` (~5KB) for layout |
| Vector Plot | measure(x), measure2(y), size, direction | Custom SVG arrows. Lowest priority/ROI — candidate to drop if time-constrained |

**Key Values** (a stylized single-value display from the transcript) is treated as an enhancement to the existing `kpi` widget (style: Text/Infographic options) rather than a new chart type, since it overlaps almost entirely with KPI's existing purpose.

## Data Flow Example (Waterfall)

Backend shaper:

```python
def shape_waterfall(df, config):
    roles = config["roles"]
    grouped = df.groupby(roles["category"])[roles["measure"]].agg(agg_fn(config))
    running = 0.0
    bars = []
    for name, delta in grouped.items():
        bars.append({"name": name, "start": running, "delta": delta, "end": running + delta})
        running += delta
    return {"type": "waterfall", "bars": bars, "total": running}
```

Frontend renderer: `WaterfallChart` reads `data.bars` directly (no shape-guessing) and renders a `ComposedChart` with a transparent `Bar` for `start` stacked under a visible `Bar` for `delta`.

The same pattern (one shaper function + one renderer component + one `ROLE_SPECS` row) repeats for all 22 types.

## Testing

- **Backend:** pytest unit tests per shaper — feed a small fixed DataFrame, assert exact output shape/values. Fit-line regression tests use synthetic data with a known slope/coefficients.
- **Frontend:** no existing frontend test suite exists in the repo today. Add lightweight Vitest + React Testing Library coverage limited to renderer-registry dispatch (does `wt` route to the right component), not full visual/pixel testing — visual correctness is checked by hand in the running app per project norms.
- **Manual verification:** each phase is checked in the browser against a real dataset before being considered done (golden path + at least one edge case per chart: empty data, single category, missing optional role).

## Rollout

Each phase ships as its own commit set / PR:

1. **Phase 0** lands alone first — pure refactor, no visible UI change. Verify existing 6 chart types are pixel/data identical.
2. **Phase 1** (10 types) — additive, low risk, no new dependencies.
3. **Phase 2** (6 items) — additive, introduces size/color/group roles and backend regression stats.
4. **Phase 3** (7 types) — additive, introduces `d3-cloud` dependency and start/end roles; Vector Plot may be deferred or dropped.

## Files Changed (representative, grows per phase)

| File | Change |
|---|---|
| `backend/app/models/models.py` | No schema change — `config` JSON already supports the `roles` key |
| `backend/app/services/widget_data.py` | `SHAPERS` registry; one shaper function per chart type/family |
| `frontend/src/components/report/WidgetRenderer.tsx` | `CHART_RENDERERS` registry; one renderer component per chart type/family |
| `frontend/src/components/report/WidgetConfigPanel.tsx` | `ROLE_SPECS`-driven field picker rendering, replacing hardcoded conditionals |
| `frontend/src/types/report.ts` | `WidgetType` union +22 members; `WIDGET_CATALOG` +22 entries; `ROLE_SPECS` table |
| `frontend/package.json` | +`d3-cloud` (Phase 3, Word Cloud only) |

## Out of Scope (deferred to future sub-projects)

Geo maps, data joins, the expression/calculation engine (IFELSE, text/date functions, periodic/tabular aggregates), interactivity & navigation (actions, links, parameters, prompts), display rules & alerts, containers & object templates, advanced analytics/ML (automated explanation/prediction, decision tree, forecasting, network/path analysis, text topics), and sharing/export. Each is its own future spec.
