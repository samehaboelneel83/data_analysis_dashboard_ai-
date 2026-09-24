# Chart Type Expansion — Phase 3: Custom-Rendered Charts — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the final 7 chart types from `docs/superpowers/specs/2026-08-10-chart-type-expansion-design.md`'s Phase 3 inventory — Box Plot, Waterfall, Gauge, Schedule (Gantt), Butterfly, Word Cloud, Vector Plot — completing all 28 planned chart types (6 original + 10 Phase 1 + 5 Phase 2 + 7 here). Vector Plot is included despite the design doc flagging it as droppable, per the user's explicit full-scope request.

**Architecture:** Same `SHAPERS`/`CHART_RENDERERS`/`ROLE_SPECS` registry pattern established in Phase 0 and extended in Phases 1–2. Two of the seven types (Butterfly, Word Cloud) need no new backend shaper — they reuse `shape_dual_series` and `shape_series` respectively, since their data shape is identical to existing types. The other five get dedicated shapers. All five new frontend renderers are hand-built (Recharts composition for Waterfall/Gauge/Schedule/Butterfly using documented tricks; full custom SVG for Box Plot and Vector Plot, matching the pattern already proven 3-for-3 in Phase 2 for chart types Recharts has no native primitive for). This phase introduces three new roles: `end` (Schedule), `target` (Gauge), `direction` (Vector Plot) — and one new npm dependency, `d3-cloud`, for Word Cloud's layout algorithm.

**Tech Stack:** FastAPI + pandas/numpy (backend), React + TypeScript + Recharts + hand-rolled SVG (frontend), `d3-cloud` (new, Word Cloud only).

## Global Constraints

- TypeScript build baseline is exactly 10 pre-existing errors (6 in `chartUtils.tsx`, 1 in `Dashboard.tsx`, 2 in `Reports.tsx`, 1 in `api.ts`) — every task must leave this count unchanged, verified explicitly via `npm run build` from `frontend/`.
- Backend: use `.venv/Scripts/python.exe -m pytest` from `backend/` — a Python 3.11 venv is already set up in this worktree.
- House rule: any shaper that selects multiple columns into a single `df[cols]` or `.agg()` call must dedupe via `list(dict.fromkeys(...))` before use, with a dedicated test proving duplicate/colliding role values don't crash. Only two of this phase's new shapers (`shape_gantt`, `shape_vector_plot`) select multiple columns this way — both apply the dedupe. `shape_box_plot`, `shape_waterfall`, and `shape_gauge` each touch only one measure column at a time (no list selection, no `.reset_index()`/`.merge()` after a `groupby` that could collide) — no guard needed for those three; each task explains why, so a reviewer doesn't have to rediscover it.
- Every shaper uses `resolve_roles(config)` to read its roles (never raw `config["roles"]` or flat keys directly) and returns `{"type": "empty", "rows": [], "total": 0}` when required roles are missing or don't resolve to real columns — matching every existing shaper's contract.
- Every shaper's `"total"` key means the filtered row count (`len(df)`), matching every other shaper in the file — never repurposed for a different number (Waterfall's running grand total is returned under a separate `"grand_total"` key, not `"total"`).
- All numeric values in shaper output go through `_safe()` before being placed in the returned dict.
- Frontend: every new renderer follows `ChartRendererProps` (`frontend/src/components/report/chartRenderers/types.ts`) and is registered in `CHART_RENDERERS` (`frontend/src/components/report/chartRenderers/index.tsx`), `WidgetType`/`WIDGET_CATALOG`/`ROLE_SPECS` (`frontend/src/types/report.ts`), and `widgetIcon()` (`frontend/src/components/report/WidgetConfigPanel.tsx`).
- No new frontend component tests this phase, matching Phase 1/2's documented choice (Recharts+jsdom has limited rendering fidelity; Word Cloud additionally needs a real `<canvas>` for text measurement, which jsdom doesn't implement without the heavy native `canvas` package) — verification is build-clean + backend pytest + diff-based review, consistent with the existing `frontend/src/test/` suite staying at 3 tests.
- This host cannot run a second Docker stack. Every task's verification step is `pytest`/`npm run build` — no live browser check. Manual verification happens post-merge against the already-running production stack.

---

### Task 1: Backend `shape_box_plot` shaper

**Files:**
- Modify: `backend/app/services/widget_data.py`
- Test: `backend/tests/test_shape_box_plot.py`

**Interfaces:**
- Produces: `shape_box_plot(df, config) -> dict` — roles: `category` (required), `measure` (required). For each category, computes min/Q1/median/Q3/max (Q1/Q3 excluding 1.5×IQR outliers, which are reported separately) — the standard box-and-whisker statistics. Returns `{"type": "box_plot", "category": ..., "measure": ..., "rows": [{"name", "min", "q1", "median", "q3", "max", "outliers": [...]}], "total": ...}`.
- Registers: `SHAPERS["box_plot"] = shape_box_plot`.

**Why no collision guard is needed here:** unlike `shape_bubble`/`shape_heatmap`, this shaper never calls `.reset_index()` or `.merge()` after grouping — it iterates `df.groupby(cat)` directly and reads `sub[meas]` inside the loop. If `cat == meas`, that's just re-reading the same column per group (constant value, degenerate but harmless output) — no `ValueError: cannot insert` is possible here.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_shape_box_plot.py`:
```python
import pandas as pd
from app.services.widget_data import shape_box_plot, SHAPERS


def sample_df():
    return pd.DataFrame({
        "region": ["East"] * 6 + ["West"] * 6,
        "revenue": [10, 12, 13, 14, 15, 100,   # East: one clear outlier (100)
                    50, 51, 52, 53, 54, 55],    # West: tight cluster, no outliers
    })


def test_computes_quartiles_per_category():
    result = shape_box_plot(sample_df(), {"roles": {"category": "region", "measure": "revenue"}})
    assert result["type"] == "box_plot"
    names = [r["name"] for r in result["rows"]]
    assert names == ["East", "West"]
    west = next(r for r in result["rows"] if r["name"] == "West")
    assert west["min"] == 50 and west["max"] == 55
    assert west["q1"] < west["median"] < west["q3"]
    assert west["outliers"] == []


def test_separates_outliers_from_min_max():
    result = shape_box_plot(sample_df(), {"roles": {"category": "region", "measure": "revenue"}})
    east = next(r for r in result["rows"] if r["name"] == "East")
    assert 100 in east["outliers"]
    assert east["max"] < 100          # the outlier is excluded from max, not included in it
    assert east["min"] == 10


def test_single_point_category_does_not_crash():
    df = pd.DataFrame({"cat": ["A"], "val": [42]})
    result = shape_box_plot(df, {"roles": {"category": "cat", "measure": "val"}})
    row = result["rows"][0]
    assert row["min"] == row["q1"] == row["median"] == row["q3"] == row["max"] == 42
    assert row["outliers"] == []


def test_missing_required_role_returns_empty():
    result = shape_box_plot(sample_df(), {"roles": {"category": "region"}})
    assert result == {"type": "empty", "rows": [], "total": 0}


def test_respects_limit():
    df = pd.DataFrame({"cat": [f"c{i}" for i in range(30) for _ in range(3)],
                        "val": list(range(90))})
    result = shape_box_plot(df, {"roles": {"category": "cat", "measure": "val"}, "limit": 5})
    assert len(result["rows"]) == 5


def test_registered_in_shapers():
    assert SHAPERS["box_plot"] is shape_box_plot
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`):
```bash
.venv/Scripts/python.exe -m pytest tests/test_shape_box_plot.py -v
```
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement `shape_box_plot` and register it**

In `backend/app/services/widget_data.py`, add after `shape_parallel_coordinates`:
```python
def shape_box_plot(df: pd.DataFrame, config: dict) -> dict:
    """roles: category (required), measure (required). Computes per-category
    quartile summary (min, q1, median, q3, max) and outliers (values beyond
    1.5*IQR from q1/q3), the standard box-and-whisker statistics. min/max
    exclude outliers (fall back to q1/q3 when every value in a category is
    flagged as an outlier, so the whisker endpoints are never missing)."""
    filters = config.get("filters", [])
    roles = resolve_roles(config)
    cat = roles.get("category")
    meas = roles.get("measure")
    limit = int(config.get("limit") or 50)
    df = _apply_filters(df, filters)
    if df.empty or not cat or not meas or cat not in df.columns or meas not in df.columns:
        return {"type": "empty", "rows": [], "total": 0}
    rows = []
    for name, sub in df.groupby(cat):
        vals = sub[meas].dropna()
        if len(vals) == 0:
            continue
        q1, med, q3 = float(vals.quantile(.25)), float(vals.median()), float(vals.quantile(.75))
        iqr = q3 - q1
        lo_fence, hi_fence = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        inliers = vals[(vals >= lo_fence) & (vals <= hi_fence)]
        outliers = vals[(vals < lo_fence) | (vals > hi_fence)]
        rows.append({
            "name": _safe(name),
            "min": _safe(float(inliers.min())) if len(inliers) else _safe(q1),
            "q1": _safe(q1), "median": _safe(med), "q3": _safe(q3),
            "max": _safe(float(inliers.max())) if len(inliers) else _safe(q3),
            "outliers": [_safe(v) for v in outliers.tolist()],
        })
    rows.sort(key=lambda r: r["name"])
    rows = rows[:limit]
    return {"type": "box_plot", "category": cat, "measure": meas, "rows": rows, "total": len(df)}
```
Update the `SHAPERS` dict, adding:
```python
    "box_plot": shape_box_plot,
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `backend/`):
```bash
.venv/Scripts/python.exe -m pytest tests/test_shape_box_plot.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Run the full backend suite**

```bash
.venv/Scripts/python.exe -m pytest -q
```
Expected: all pass, no regressions (baseline was 83 before this task).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/widget_data.py backend/tests/test_shape_box_plot.py
git commit -m "feat: add shape_box_plot shaper for Box Plot chart type"
```

---

### Task 2: Frontend Box Plot

**Files:**
- Create: `frontend/src/components/report/chartRenderers/BoxPlotRenderer.tsx`
- Modify: `frontend/src/components/report/chartRenderers/index.tsx`
- Modify: `frontend/src/types/report.ts`
- Modify: `frontend/src/components/report/WidgetConfigPanel.tsx`

**Interfaces:**
- Produces: `BoxPlotRenderer: React.FC<ChartRendererProps>`, registered as `CHART_RENDERERS.box_plot`. Reads `data.rows` (each `{name, min, q1, median, q3, max, outliers}`). Full custom SVG — Recharts has no box-plot primitive, and (per Phase 2's precedent) hand-rolled SVG is the proven pattern here rather than fighting Recharts' range-bar API.
- Produces: `'box_plot'` added to `WidgetType`/`WIDGET_CATALOG`/`ROLE_SPECS` (`category`, `measure`, both required).

- [ ] **Step 1: Create the renderer**

Create `frontend/src/components/report/chartRenderers/BoxPlotRenderer.tsx`:
```tsx
import { fmtStr } from '../chartUtils'
import type { ChartRendererProps } from './types'

const MARGIN_TOP = 20
const MARGIN_BOTTOM = 30
const MARGIN_LEFT = 50
const W = 1000
const H = 400

interface BoxRow { name: string; min: number; q1: number; median: number; q3: number; max: number; outliers: number[] }

export default function BoxPlotRenderer({ data, rtl, measureFmt }: ChartRendererProps) {
  const rows: BoxRow[] = data?.rows ?? []

  if (rows.length === 0) {
    return <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 12 }}>Configure widget to see data</div>
  }

  const allVals = rows.flatMap(r => [r.min, r.max, ...(r.outliers ?? [])])
  const yMin = Math.min(...allVals)
  const yMax = Math.max(...allVals)
  const yRange = yMax - yMin || 1
  const plotH = H - MARGIN_TOP - MARGIN_BOTTOM
  const plotW = W - MARGIN_LEFT - 10
  const yToPx = (v: number) => MARGIN_TOP + plotH - ((v - yMin) / yRange) * plotH

  const orderedRows = rtl ? [...rows].reverse() : rows
  const slotW = plotW / orderedRows.length
  const boxW = Math.min(slotW * 0.5, 60)

  return (
    <div style={{ height: '100%', width: '100%' }}>
      <svg width="100%" height="100%" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ display: 'block' }}>
        {[0, 0.25, 0.5, 0.75, 1].map(t => {
          const v = yMin + t * yRange
          const y = yToPx(v)
          return (
            <g key={t}>
              <line x1={MARGIN_LEFT} y1={y} x2={W - 10} y2={y} stroke="var(--border)" strokeWidth={1} strokeDasharray={t === 0 ? undefined : '2 3'} />
              <text x={MARGIN_LEFT - 6} y={y + 3} textAnchor="end" fontSize={9} fill="var(--muted)">{fmtStr(v, measureFmt)}</text>
            </g>
          )
        })}
        {orderedRows.map((r, i) => {
          const cx = MARGIN_LEFT + slotW * (i + 0.5)
          const yMinPx = yToPx(r.min), yQ1Px = yToPx(r.q1), yMedPx = yToPx(r.median), yQ3Px = yToPx(r.q3), yMaxPx = yToPx(r.max)
          return (
            <g key={r.name}>
              <line x1={cx} y1={yMaxPx} x2={cx} y2={yQ3Px} stroke="var(--accent)" strokeWidth={1.5} />
              <line x1={cx} y1={yQ1Px} x2={cx} y2={yMinPx} stroke="var(--accent)" strokeWidth={1.5} />
              <line x1={cx - boxW / 4} y1={yMaxPx} x2={cx + boxW / 4} y2={yMaxPx} stroke="var(--accent)" strokeWidth={1.5} />
              <line x1={cx - boxW / 4} y1={yMinPx} x2={cx + boxW / 4} y2={yMinPx} stroke="var(--accent)" strokeWidth={1.5} />
              <rect x={cx - boxW / 2} y={yQ3Px} width={boxW} height={Math.max(1, yQ1Px - yQ3Px)} fill="var(--accent)" fillOpacity={0.25} stroke="var(--accent)" strokeWidth={1.5} />
              <line x1={cx - boxW / 2} y1={yMedPx} x2={cx + boxW / 2} y2={yMedPx} stroke="var(--accent)" strokeWidth={2} />
              {(r.outliers ?? []).map((o, oi) => (
                <circle key={oi} cx={cx} cy={yToPx(o)} r={2.5} fill="var(--muted)" fillOpacity={0.7} />
              ))}
              <text x={cx} y={H - MARGIN_BOTTOM + 16} textAnchor="middle" fontSize={10} fill="var(--muted)">{r.name}</text>
              <title>{`${r.name}: min ${fmtStr(r.min, measureFmt)}, Q1 ${fmtStr(r.q1, measureFmt)}, median ${fmtStr(r.median, measureFmt)}, Q3 ${fmtStr(r.q3, measureFmt)}, max ${fmtStr(r.max, measureFmt)}`}</title>
            </g>
          )
        })}
      </svg>
    </div>
  )
}
```

- [ ] **Step 2: Register it**

In `frontend/src/components/report/chartRenderers/index.tsx`, add:
```tsx
import BoxPlotRenderer from './BoxPlotRenderer'
```
```tsx
  box_plot: BoxPlotRenderer,
```

- [ ] **Step 3: Add `WidgetType`, `WIDGET_CATALOG`, `ROLE_SPECS` entries**

In `frontend/src/types/report.ts`:

1. Add `| 'box_plot'` to `WidgetType`.
2. Add to `WIDGET_CATALOG`:
```ts
  { type: 'box_plot' as WidgetType, label: 'Box Plot', category: 'Charts', icon: '⊡', defaultW: 6, defaultH: 5 },
```
3. Add to `ROLE_SPECS`:
```ts
  box_plot: [{ role: 'category', label: 'Dimension (one box per group)', required: true },
             { role: 'measure',  label: 'Measure (numeric column)',      required: true }],
```

- [ ] **Step 4: Add the icon**

Add `box_plot:'⊡'` to `WidgetConfigPanel.tsx`'s `widgetIcon()` map. Scan the existing map first to confirm `'⊡'` isn't already used (it isn't, as of Phase 2's close-out).

- [ ] **Step 5: Verify**

Run (from `frontend/`):
```bash
npm run build
```
Expected: exactly the 10 pre-existing errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/report/chartRenderers/BoxPlotRenderer.tsx frontend/src/components/report/chartRenderers/index.tsx frontend/src/types/report.ts frontend/src/components/report/WidgetConfigPanel.tsx
git commit -m "feat: add Box Plot chart type"
```

---

### Task 3: Backend `shape_waterfall` shaper

**Files:**
- Modify: `backend/app/services/widget_data.py`
- Test: `backend/tests/test_shape_waterfall.py`

**Interfaces:**
- Produces: `shape_waterfall(df, config) -> dict` — roles: `category` (required), `measure` (required, the per-category delta). Computes a running total across categories (in groupby-sorted order) and returns start/delta/end per bar for the classic waterfall stacked-bar-with-transparent-base rendering trick. Returns `{"type": "waterfall", "category": ..., "measure": ..., "bars": [{"name", "start", "delta", "end"}], "grand_total": <float>, "total": ...}`. Note `"grand_total"` (the final running sum) is distinct from `"total"` (row count) — this phase never repurposes `"total"`'s established meaning.
- Registers: `SHAPERS["waterfall"] = shape_waterfall`.

**Why no collision guard is needed here:** the groupby result is a `Series` (`df.groupby(cat)[meas].agg(agg_fn)`), iterated via `.items()` — no `.reset_index()`/`.merge()` call exists to collide. If `cat == meas`, each group's `meas` values are constant (equal to the group's `cat` value), producing a degenerate-but-non-crashing result.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_shape_waterfall.py`:
```python
import pandas as pd
from app.services.widget_data import shape_waterfall, SHAPERS


def sample_df():
    return pd.DataFrame({
        "stage": ["Start", "Start", "Gains", "Losses", "Losses"],
        "delta": [100, 100, 50, -20, -10],
    })


def test_computes_running_total_in_order():
    result = shape_waterfall(sample_df(), {"roles": {"category": "stage", "measure": "delta"}})
    assert result["type"] == "waterfall"
    names = [b["name"] for b in result["bars"]]
    assert names == sorted(names)   # groupby-sorted category order
    gains = next(b for b in result["bars"] if b["name"] == "Gains")
    assert gains["delta"] == 50
    assert gains["end"] == gains["start"] + 50


def test_bars_chain_start_to_end():
    result = shape_waterfall(sample_df(), {"roles": {"category": "stage", "measure": "delta"}})
    bars = result["bars"]
    for i in range(1, len(bars)):
        assert bars[i]["start"] == bars[i - 1]["end"]


def test_grand_total_is_final_running_sum_not_row_count():
    result = shape_waterfall(sample_df(), {"roles": {"category": "stage", "measure": "delta"}})
    # Start: 100+100=200, Gains: +50=250, Losses: -20-10=-30 => 250-30=220
    assert result["grand_total"] == 220
    assert result["total"] == len(sample_df())   # total = row count, per every other shaper's contract
    assert result["grand_total"] != result["total"]


def test_missing_required_role_returns_empty():
    result = shape_waterfall(sample_df(), {"roles": {"category": "stage"}})
    assert result == {"type": "empty", "rows": [], "total": 0}


def test_registered_in_shapers():
    assert SHAPERS["waterfall"] is shape_waterfall
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`):
```bash
.venv/Scripts/python.exe -m pytest tests/test_shape_waterfall.py -v
```
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement `shape_waterfall` and register it**

In `backend/app/services/widget_data.py`, add after `shape_box_plot`:
```python
def shape_waterfall(df: pd.DataFrame, config: dict) -> dict:
    """roles: category (required), measure (required, the delta per category).
    Computes a running total across categories in groupby-sorted order,
    returning start/delta/end per bar for the classic waterfall
    transparent-base stacked-bar rendering trick."""
    filters = config.get("filters", [])
    roles = resolve_roles(config)
    cat = roles.get("category")
    meas = roles.get("measure")
    agg = (config.get("aggregation") or "sum").lower()
    limit = int(config.get("limit") or 50)
    df = _apply_filters(df, filters)
    if df.empty or not cat or not meas or cat not in df.columns or meas not in df.columns:
        return {"type": "empty", "rows": [], "total": 0}
    agg_fn = _pandas_agg_fn(agg)
    grouped = df.groupby(cat)[meas].agg(agg_fn).sort_index().head(limit)
    running = 0.0
    bars = []
    for name, delta in grouped.items():
        delta = float(delta)
        bars.append({"name": _safe(name), "start": _safe(running), "delta": _safe(delta), "end": _safe(running + delta)})
        running += delta
    return {"type": "waterfall", "category": cat, "measure": meas, "bars": bars, "grand_total": _safe(running), "total": len(df)}
```
Update the `SHAPERS` dict, adding:
```python
    "waterfall": shape_waterfall,
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `backend/`):
```bash
.venv/Scripts/python.exe -m pytest tests/test_shape_waterfall.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Run the full backend suite**

```bash
.venv/Scripts/python.exe -m pytest -q
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/widget_data.py backend/tests/test_shape_waterfall.py
git commit -m "feat: add shape_waterfall shaper for Waterfall chart type"
```

---

### Task 4: Frontend Waterfall Chart

**Files:**
- Create: `frontend/src/components/report/chartRenderers/WaterfallChartRenderer.tsx`
- Modify: `frontend/src/components/report/chartRenderers/index.tsx`
- Modify: `frontend/src/types/report.ts`
- Modify: `frontend/src/components/report/WidgetConfigPanel.tsx`

**Interfaces:**
- Produces: `WaterfallChartRenderer: React.FC<ChartRendererProps>`, registered as `CHART_RENDERERS.waterfall`. Reads `data.bars`. Uses Recharts `BarChart` with a transparent `base` bar stacked under a visible `delta` bar (green for increases, red for decreases) — the standard Recharts waterfall trick, per the design spec.
- Produces: `'waterfall'` added to `WidgetType`/`WIDGET_CATALOG`/`ROLE_SPECS` (`category`, `measure`, both required).

- [ ] **Step 1: Create the renderer**

Create `frontend/src/components/report/chartRenderers/WaterfallChartRenderer.tsx`:
```tsx
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell, ResponsiveContainer } from 'recharts'
import { fmtStr, TT } from '../chartUtils'
import type { ChartRendererProps } from './types'

interface Bar_ { name: string; start: number; delta: number; end: number }

export default function WaterfallChartRenderer({ data, rtl, measureFmt }: ChartRendererProps) {
  const bars: Bar_[] = data?.bars ?? []

  if (bars.length === 0) {
    return <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 12 }}>Configure widget to see data</div>
  }

  const chartData = bars.map(b => ({
    name: b.name,
    base: Math.min(b.start, b.end),
    delta: Math.abs(b.end - b.start),
    isIncrease: b.end >= b.start,
    start: b.start, end: b.end,
  }))

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 10 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis dataKey="name" tick={{ fontSize: 11 }} reversed={rtl} />
        <YAxis tick={{ fontSize: 11 }} tickFormatter={v => fmtStr(v, measureFmt)} orientation={rtl ? 'right' : 'left'} />
        <Tooltip contentStyle={TT} formatter={(v: any, name: string, props: any) =>
          name === 'delta' ? [`${fmtStr(props.payload.start, measureFmt)} → ${fmtStr(props.payload.end, measureFmt)}`, 'Change'] : [v, name]
        } />
        <Bar dataKey="base" stackId="wf" fill="transparent" isAnimationActive={false} />
        <Bar dataKey="delta" stackId="wf" isAnimationActive={false} radius={2}>
          {chartData.map((d, i) => <Cell key={i} fill={d.isIncrease ? '#34d399' : '#f87171'} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
```

- [ ] **Step 2: Register it**

In `frontend/src/components/report/chartRenderers/index.tsx`, add:
```tsx
import WaterfallChartRenderer from './WaterfallChartRenderer'
```
```tsx
  waterfall: WaterfallChartRenderer,
```

- [ ] **Step 3: Add `WidgetType`, `WIDGET_CATALOG`, `ROLE_SPECS` entries**

In `frontend/src/types/report.ts`:

1. Add `| 'waterfall'` to `WidgetType`.
2. Add to `WIDGET_CATALOG`:
```ts
  { type: 'waterfall' as WidgetType, label: 'Waterfall Chart', category: 'Charts', icon: '▨', defaultW: 6, defaultH: 5 },
```
3. Add to `ROLE_SPECS`:
```ts
  waterfall: [{ role: 'category', label: 'Dimension (running order)', required: true },
              { role: 'measure',  label: 'Delta (numeric column)',    required: true }],
```

- [ ] **Step 4: Add the icon**

Add `waterfall:'▨'` to `WidgetConfigPanel.tsx`'s `widgetIcon()` map.

- [ ] **Step 5: Verify**

Run (from `frontend/`):
```bash
npm run build
```
Expected: exactly the 10 pre-existing errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/report/chartRenderers/WaterfallChartRenderer.tsx frontend/src/components/report/chartRenderers/index.tsx frontend/src/types/report.ts frontend/src/components/report/WidgetConfigPanel.tsx
git commit -m "feat: add Waterfall Chart chart type"
```

---

### Task 5: Backend `shape_gauge` shaper

**Files:**
- Modify: `backend/app/services/widget_data.py`
- Test: `backend/tests/test_shape_gauge.py`

**Interfaces:**
- Produces: `shape_gauge(df, config) -> dict` — roles: `measure` (required, aggregated to a single value), `target` (optional column, aggregated the same way). If no `target` role is set, falls back to a literal `config["target_value"]` number when present. Returns `{"type": "gauge", "measure": ..., "value": <float|None>, "target": <float|None>, "total": ...}`.
- Registers: `SHAPERS["gauge"] = shape_gauge`.

**Why no collision guard is needed here:** `value` and `target` are each computed via an independent `_agg_series(df[col], agg)` call — never combined into a single list-selection or groupby/reset_index call. If `measure == target` column, both calls simply read the same Series independently; no crash, a degenerate-but-harmless "value equals target" result.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_shape_gauge.py`:
```python
import pandas as pd
from app.services.widget_data import shape_gauge, SHAPERS


def sample_df():
    return pd.DataFrame({"revenue": [10, 20, 30], "quota": [15, 15, 15]})


def test_aggregates_measure_to_a_single_value():
    result = shape_gauge(sample_df(), {"roles": {"measure": "revenue"}, "aggregation": "sum"})
    assert result["type"] == "gauge"
    assert result["value"] == 60
    assert result["target"] is None


def test_target_role_aggregated_same_way():
    result = shape_gauge(sample_df(), {"roles": {"measure": "revenue", "target": "quota"}, "aggregation": "sum"})
    assert result["value"] == 60
    assert result["target"] == 45   # sum of quota column


def test_literal_target_value_used_when_no_target_role():
    result = shape_gauge(sample_df(), {"roles": {"measure": "revenue"}, "aggregation": "sum", "target_value": 75})
    assert result["target"] == 75


def test_target_role_takes_priority_over_literal_target_value():
    result = shape_gauge(sample_df(), {"roles": {"measure": "revenue", "target": "quota"}, "aggregation": "sum", "target_value": 999})
    assert result["target"] == 45


def test_missing_measure_returns_empty():
    result = shape_gauge(sample_df(), {"roles": {}})
    assert result == {"type": "empty", "rows": [], "total": 0}


def test_registered_in_shapers():
    assert SHAPERS["gauge"] is shape_gauge
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`):
```bash
.venv/Scripts/python.exe -m pytest tests/test_shape_gauge.py -v
```
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement `shape_gauge` and register it**

In `backend/app/services/widget_data.py`, add after `shape_waterfall`:
```python
def shape_gauge(df: pd.DataFrame, config: dict) -> dict:
    """roles: measure (required, aggregated to a single value), target
    (optional column, aggregated the same way). config may also set a literal
    target_value (a plain number), used only when the target role isn't set —
    covers goals with no natural target column (e.g. a fixed KPI threshold)."""
    filters = config.get("filters", [])
    roles = resolve_roles(config)
    meas = roles.get("measure")
    target_col = roles.get("target")
    agg = (config.get("aggregation") or "sum").lower()
    df = _apply_filters(df, filters)
    if df.empty or not meas or meas not in df.columns:
        return {"type": "empty", "rows": [], "total": 0}
    value = _agg_series(df[meas], agg)
    target = None
    if target_col and target_col in df.columns:
        target = _agg_series(df[target_col], agg)
    elif config.get("target_value") is not None:
        try:
            target = float(config["target_value"])
        except (TypeError, ValueError):
            target = None
    return {"type": "gauge", "measure": meas, "value": value, "target": target, "total": len(df)}
```
Update the `SHAPERS` dict, adding:
```python
    "gauge": shape_gauge,
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `backend/`):
```bash
.venv/Scripts/python.exe -m pytest tests/test_shape_gauge.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Run the full backend suite**

```bash
.venv/Scripts/python.exe -m pytest -q
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/widget_data.py backend/tests/test_shape_gauge.py
git commit -m "feat: add shape_gauge shaper for Gauge chart type"
```

---

### Task 6: Frontend Gauge

**Files:**
- Create: `frontend/src/components/report/chartRenderers/GaugeRenderer.tsx`
- Modify: `frontend/src/components/report/chartRenderers/index.tsx`
- Modify: `frontend/src/types/report.ts`
- Modify: `frontend/src/components/report/WidgetConfigPanel.tsx`

**Interfaces:**
- Produces: `GaugeRenderer: React.FC<ChartRendererProps>`, registered as `CHART_RENDERERS.gauge`. Reads `data.value`/`data.target`. Uses Recharts `RadialBarChart`, per the design spec, with the numeric value overlaid as centered text.
- Produces: `'gauge'` added to `WidgetType`/`WIDGET_CATALOG`/`ROLE_SPECS` (`measure` required, `target` optional), plus a one-off "Target value (fixed, optional)" numeric field in the config panel (same pattern as Needle Plot's `baseline` field), bound to `config.target_value`.

- [ ] **Step 1: Create the renderer**

Create `frontend/src/components/report/chartRenderers/GaugeRenderer.tsx`:
```tsx
import { RadialBarChart, RadialBar, PolarAngleAxis, ResponsiveContainer } from 'recharts'
import { fmtStr } from '../chartUtils'
import type { ChartRendererProps } from './types'

export default function GaugeRenderer({ data, measureFmt }: ChartRendererProps) {
  const value: number | null = data?.value ?? null
  const target: number | null = data?.target ?? null

  if (value == null) {
    return <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 12 }}>Configure widget to see data</div>
  }

  const max = target != null && target > 0 ? Math.max(target, value) * 1.1 : (value > 0 ? value * 1.25 : 1)
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0
  const chartData = [{ name: 'value', value: pct, fill: target != null && value >= target ? '#34d399' : '#6c8fff' }]

  return (
    <div style={{ height: '100%', width: '100%', position: 'relative' }}>
      <ResponsiveContainer width="100%" height="100%">
        <RadialBarChart data={chartData} cx="50%" cy="55%" innerRadius="65%" outerRadius="100%" startAngle={180} endAngle={0} barSize={18}>
          <PolarAngleAxis type="number" domain={[0, 100]} angleAxisId={0} tick={false} />
          <RadialBar background dataKey="value" cornerRadius={9} isAnimationActive={false} />
        </RadialBarChart>
      </ResponsiveContainer>
      <div style={{ position: 'absolute', top: '55%', left: '50%', transform: 'translate(-50%, -20%)', textAlign: 'center', pointerEvents: 'none' }}>
        <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--text)' }}>{fmtStr(value, measureFmt)}</div>
        {target != null && <div style={{ fontSize: 11, color: 'var(--muted)' }}>of {fmtStr(target, measureFmt)}</div>}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Register it**

In `frontend/src/components/report/chartRenderers/index.tsx`, add:
```tsx
import GaugeRenderer from './GaugeRenderer'
```
```tsx
  gauge: GaugeRenderer,
```

- [ ] **Step 3: Add `WidgetType`, `WIDGET_CATALOG`, `ROLE_SPECS` entries**

In `frontend/src/types/report.ts`:

1. Add `| 'gauge'` to `WidgetType`.
2. Add to `WIDGET_CATALOG`:
```ts
  { type: 'gauge' as WidgetType, label: 'Gauge', category: 'Charts', icon: '◐', defaultW: 4, defaultH: 4 },
```
3. Add to `ROLE_SPECS`:
```ts
  gauge: [{ role: 'measure', label: 'Value',                    required: true },
          { role: 'target',  label: 'Target (column, optional)', required: false }],
```

- [ ] **Step 4: Add the icon and the target-value field**

1. Add `gauge:'◐'` to `WidgetConfigPanel.tsx`'s `widgetIcon()` map.
2. Add state, alongside the existing `baseline`/`bins`/`fitLine` one-off field state:
```ts
  const [targetValue, setTargetValue] = useState<string>((cfg.target_value != null ? String(cfg.target_value) : ''))
```
3. Add to the widget-change reset `useEffect`:
```ts
    setTargetValue(cfg.target_value != null ? String(cfg.target_value) : '')
```
4. Add to the config-emission object (only emit when non-empty and numeric):
```ts
      if (wt === 'gauge' && targetValue !== '' && !isNaN(Number(targetValue))) config.target_value = Number(targetValue)
```
5. Add `targetValue` to the emitting `useEffect`'s dependency array.
6. Add the field JSX, gated by widget type, near the other one-off fields:
```tsx
          {wt === 'gauge' && fld('Target value (fixed, optional)',
            <input type="number" value={targetValue} onChange={e => setTargetValue(e.target.value)} style={{ width:'100%' }} placeholder="leave blank to use Target column" />
          )}
```

- [ ] **Step 5: Verify**

Run (from `frontend/`):
```bash
npm run build
```
Expected: exactly the 10 pre-existing errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/report/chartRenderers/GaugeRenderer.tsx frontend/src/components/report/chartRenderers/index.tsx frontend/src/types/report.ts frontend/src/components/report/WidgetConfigPanel.tsx
git commit -m "feat: add Gauge chart type"
```

---

### Task 7: Backend `shape_gantt` shaper

**Files:**
- Modify: `backend/app/services/widget_data.py`
- Test: `backend/tests/test_shape_gantt.py`

**Interfaces:**
- Produces: `shape_gantt(df, config) -> dict` — roles: `category` (task label, required), `start` (required), `end` (required, **new role introduced by this task**), `group` (optional, for color-coding). Row-level detail, no aggregation — each source row becomes one task bar. Returns `{"type": "gantt", "category": ..., "start": ..., "end": ..., "rows": [{"name", "start", "end", "group"?}], "total": ...}`.
- Registers: `SHAPERS["gantt"] = shape_gantt`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_shape_gantt.py`:
```python
import pandas as pd
from app.services.widget_data import shape_gantt, SHAPERS


def sample_df():
    return pd.DataFrame({
        "task":  ["Design", "Build", "Test"],
        "begin": ["2026-01-01", "2026-01-05", "2026-01-15"],
        "finish":["2026-01-05", "2026-01-15", "2026-01-20"],
        "owner": ["Alice", "Bob", "Alice"],
    })


def test_builds_one_row_per_task():
    config = {"roles": {"category": "task", "start": "begin", "end": "finish"}}
    result = shape_gantt(sample_df(), config)
    assert result["type"] == "gantt"
    assert len(result["rows"]) == 3
    build = next(r for r in result["rows"] if r["name"] == "Build")
    assert build["start"] == "2026-01-05" and build["end"] == "2026-01-15"


def test_includes_group_when_role_set():
    config = {"roles": {"category": "task", "start": "begin", "end": "finish", "group": "owner"}}
    result = shape_gantt(sample_df(), config)
    build = next(r for r in result["rows"] if r["name"] == "Build")
    assert build["group"] == "Bob"


def test_excludes_group_key_when_role_not_set():
    config = {"roles": {"category": "task", "start": "begin", "end": "finish"}}
    result = shape_gantt(sample_df(), config)
    assert all("group" not in r for r in result["rows"])


def test_column_collision_does_not_crash():
    """House rule: category and start resolving to the same column must not crash."""
    config = {"roles": {"category": "begin", "start": "begin", "end": "finish"}}
    result = shape_gantt(sample_df(), config)
    assert result["type"] == "gantt"
    assert len(result["rows"]) == 3


def test_missing_required_role_returns_empty():
    config = {"roles": {"category": "task", "start": "begin"}}   # no end
    result = shape_gantt(sample_df(), config)
    assert result == {"type": "empty", "rows": [], "total": 0}


def test_respects_limit():
    config = {"roles": {"category": "task", "start": "begin", "end": "finish"}, "limit": 2}
    result = shape_gantt(sample_df(), config)
    assert len(result["rows"]) == 2


def test_registered_in_shapers():
    assert SHAPERS["gantt"] is shape_gantt
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`):
```bash
.venv/Scripts/python.exe -m pytest tests/test_shape_gantt.py -v
```
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement `shape_gantt` and register it**

In `backend/app/services/widget_data.py`, add after `shape_gauge`:
```python
def shape_gantt(df: pd.DataFrame, config: dict) -> dict:
    """roles: category (task label, required), start (required), end
    (required), group (optional, for color-coding). Row-level detail, no
    aggregation -- each source row becomes one task bar spanning start..end."""
    filters = config.get("filters", [])
    roles = resolve_roles(config)
    cat = roles.get("category")
    start = roles.get("start")
    end = roles.get("end")
    group = roles.get("group")
    limit = int(config.get("limit") or 100)
    df = _apply_filters(df, filters)
    if df.empty or not cat or not start or not end:
        return {"type": "empty", "rows": [], "total": 0}
    if any(c not in df.columns for c in (cat, start, end)):
        return {"type": "empty", "rows": [], "total": 0}
    cols = list(dict.fromkeys([cat, start, end] + ([group] if group and group in df.columns else [])))
    sub = df[cols].dropna(subset=list(dict.fromkeys([cat, start, end]))).head(limit)
    rows = []
    for _, row in sub.iterrows():
        r = {"name": _safe(row[cat]), "start": _safe(row[start]), "end": _safe(row[end])}
        if group and group in cols:
            r["group"] = _safe(row[group])
        rows.append(r)
    return {"type": "gantt", "category": cat, "start": start, "end": end, "rows": rows, "total": len(df)}
```
Update the `SHAPERS` dict, adding:
```python
    "gantt": shape_gantt,
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `backend/`):
```bash
.venv/Scripts/python.exe -m pytest tests/test_shape_gantt.py -v
```
Expected: 7 passed.

- [ ] **Step 5: Run the full backend suite**

```bash
.venv/Scripts/python.exe -m pytest -q
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/widget_data.py backend/tests/test_shape_gantt.py
git commit -m "feat: add shape_gantt shaper for Schedule (Gantt) chart type"
```

---

### Task 8: Frontend Schedule (Gantt) Chart

**Files:**
- Create: `frontend/src/components/report/chartRenderers/ScheduleChartRenderer.tsx`
- Modify: `frontend/src/components/report/chartRenderers/index.tsx`
- Modify: `frontend/src/types/report.ts`
- Modify: `frontend/src/components/report/WidgetConfigPanel.tsx`

**Interfaces:**
- Produces: `ScheduleChartRenderer: React.FC<ChartRendererProps>`, registered as `CHART_RENDERERS.schedule`. Reads `data.rows` (`{name, start, end, group?}`). Uses a horizontal Recharts `BarChart` with a transparent offset bar (positions each task relative to the earliest start date) stacked under a visible span bar — the horizontal analogue of Waterfall's trick, per the design spec.
- Produces: `'schedule'` added to `WidgetType`/`WIDGET_CATALOG`/`ROLE_SPECS` (`category` as "Task", `start`, `end` required; `group` optional).

- [ ] **Step 1: Create the renderer**

Create `frontend/src/components/report/chartRenderers/ScheduleChartRenderer.tsx`:
```tsx
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell, ResponsiveContainer } from 'recharts'
import { COLORS, TT } from '../chartUtils'
import type { ChartRendererProps } from './types'

function toMs(v: unknown): number {
  if (typeof v === 'number') return v
  const t = Date.parse(String(v))
  return isNaN(t) ? 0 : t
}

export default function ScheduleChartRenderer({ data, rtl }: ChartRendererProps) {
  const rows: { name: string; start: unknown; end: unknown; group?: string }[] = data?.rows ?? []

  if (rows.length === 0) {
    return <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 12 }}>Configure widget to see data</div>
  }

  const parsed = rows.map(r => ({ name: r.name, startMs: toMs(r.start), endMs: toMs(r.end), group: r.group }))
  const minStart = Math.min(...parsed.map(r => r.startMs))
  const chartData = parsed.map(r => ({ name: r.name, offset: r.startMs - minStart, span: Math.max(0, r.endMs - r.startMs), group: r.group }))
  const groups = Array.from(new Set(chartData.map(d => d.group).filter((g): g is string => !!g)))
  const colorFor = (g?: string) => (g && groups.length > 0) ? COLORS[groups.indexOf(g) % COLORS.length] : COLORS[0]

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={chartData} layout="vertical" margin={{ top: 10, right: 10, left: 10, bottom: 10 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis type="number" tick={{ fontSize: 11 }} tickFormatter={v => new Date(minStart + v).toLocaleDateString()} reversed={rtl} />
        <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={100} orientation={rtl ? 'right' : 'left'} />
        <Tooltip contentStyle={TT} formatter={(_v: any, _n: string, props: any) =>
          [`${new Date(minStart + props.payload.offset).toLocaleDateString()} → ${new Date(minStart + props.payload.offset + props.payload.span).toLocaleDateString()}`, props.payload.name]
        } />
        <Bar dataKey="offset" stackId="gantt" fill="transparent" isAnimationActive={false} />
        <Bar dataKey="span" stackId="gantt" isAnimationActive={false} radius={3}>
          {chartData.map((d, i) => <Cell key={i} fill={colorFor(d.group)} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
```

- [ ] **Step 2: Register it**

In `frontend/src/components/report/chartRenderers/index.tsx`, add:
```tsx
import ScheduleChartRenderer from './ScheduleChartRenderer'
```
```tsx
  schedule: ScheduleChartRenderer,
```

- [ ] **Step 3: Add `WidgetType`, `WIDGET_CATALOG`, `ROLE_SPECS` entries**

In `frontend/src/types/report.ts`:

1. Add `| 'schedule'` to `WidgetType`.
2. Add to `WIDGET_CATALOG`:
```ts
  { type: 'schedule' as WidgetType, label: 'Schedule (Gantt)', category: 'Charts', icon: '▭', defaultW: 7, defaultH: 6 },
```
3. Add to `ROLE_SPECS`:
```ts
  schedule: [{ role: 'category', label: 'Task',                      required: true },
             { role: 'start',    label: 'Start date',                required: true },
             { role: 'end',      label: 'End date',                  required: true },
             { role: 'group',    label: 'Group (color, optional)',   required: false }],
```

- [ ] **Step 4: Add the icon**

Add `schedule:'▭'` to `WidgetConfigPanel.tsx`'s `widgetIcon()` map.

- [ ] **Step 5: Verify**

Run (from `frontend/`):
```bash
npm run build
```
Expected: exactly the 10 pre-existing errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/report/chartRenderers/ScheduleChartRenderer.tsx frontend/src/components/report/chartRenderers/index.tsx frontend/src/types/report.ts frontend/src/components/report/WidgetConfigPanel.tsx
git commit -m "feat: add Schedule (Gantt) chart type"
```

---

### Task 9: Butterfly Chart (registration + frontend renderer)

**Files:**
- Modify: `backend/app/services/widget_data.py`
- Create: `backend/tests/test_phase3_registrations.py`
- Create: `frontend/src/components/report/chartRenderers/ButterflyChartRenderer.tsx`
- Modify: `frontend/src/components/report/chartRenderers/index.tsx`
- Modify: `frontend/src/types/report.ts`
- Modify: `frontend/src/components/report/WidgetConfigPanel.tsx`

**Interfaces:**
- Backend: Butterfly's data shape (`{name, value, value2}` rows) is identical to `shape_dual_series`'s existing output — no new shaper needed. `SHAPERS["butterfly"] = shape_dual_series` (already fully tested by `test_shape_dual_series.py` from Phase 1, including its dedup guard for `measure == measure2`).
- Produces: `ButterflyChartRenderer: React.FC<ChartRendererProps>`, registered as `CHART_RENDERERS.butterfly`. Reads `data.rows`. Mirrored horizontal bars via negated `value` (left side) and `value2` (right side), per the design spec.
- Produces: `'butterfly'` added to `WidgetType`/`WIDGET_CATALOG`/`ROLE_SPECS` (`category`, `measure` as "Left side", `measure2` as "Right side", all required).

- [ ] **Step 1: Write the failing registration test**

Create `backend/tests/test_phase3_registrations.py`:
```python
from app.services.widget_data import shape_dual_series, SHAPERS


def test_butterfly_reuses_shape_dual_series():
    """Butterfly's data shape ({name, value, value2}) is identical to dual_series'
    output -- no dedicated shaper needed, same pattern as bar/line/pie reusing
    shape_series in Phase 0."""
    assert SHAPERS["butterfly"] is shape_dual_series
```
(Task 10 appends a second test, `test_word_cloud_reuses_shape_series`, to this same file — kept out of this task so the suite stays fully green after every task, with no test left intentionally red between tasks.)

- [ ] **Step 2: Run test to verify it fails**

Run (from `backend/`):
```bash
.venv/Scripts/python.exe -m pytest tests/test_phase3_registrations.py -v
```
Expected: FAIL — `KeyError` (`"butterfly"` not registered yet).

- [ ] **Step 3: Register `butterfly` in `SHAPERS`**

In `backend/app/services/widget_data.py`, in the `SHAPERS` dict, add:
```python
    "butterfly": shape_dual_series,
```

- [ ] **Step 4: Run the registration test, confirm it passes**

Run (from `backend/`):
```bash
.venv/Scripts/python.exe -m pytest tests/test_phase3_registrations.py -v
```
Expected: 1 passed.

- [ ] **Step 5: Run the full backend suite**

```bash
.venv/Scripts/python.exe -m pytest -q
```
Expected: all pass, no regressions.

- [ ] **Step 6: Create the frontend renderer**

Create `frontend/src/components/report/chartRenderers/ButterflyChartRenderer.tsx`:
```tsx
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer } from 'recharts'
import { fmtStr, TT } from '../chartUtils'
import type { ChartRendererProps } from './types'

export default function ButterflyChartRenderer({ data, rtl, measureFmt, measure2Fmt }: ChartRendererProps) {
  const rows: { name: string; value?: number; value2?: number }[] = data?.rows ?? []

  if (rows.length === 0) {
    return <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 12 }}>Configure widget to see data</div>
  }

  const chartData = rows.map(r => ({ name: r.name, left: -(Math.abs(r.value ?? 0)), right: Math.abs(r.value2 ?? 0) }))

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={chartData} layout="vertical" margin={{ top: 10, right: 20, left: 10, bottom: 10 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis type="number" tick={{ fontSize: 11 }} tickFormatter={v => fmtStr(Math.abs(v), measureFmt)} reversed={rtl} />
        <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={100} orientation={rtl ? 'right' : 'left'} />
        <Tooltip contentStyle={TT} formatter={(v: any, name: string) =>
          name === 'left' ? [fmtStr(Math.abs(v), measureFmt), 'Left'] : [fmtStr(v, measure2Fmt), 'Right']
        } />
        <ReferenceLine x={0} stroke="var(--border)" />
        <Bar dataKey="left" fill="#f87171" isAnimationActive={false} radius={3} />
        <Bar dataKey="right" fill="#6c8fff" isAnimationActive={false} radius={3} />
      </BarChart>
    </ResponsiveContainer>
  )
}
```

- [ ] **Step 7: Register it**

In `frontend/src/components/report/chartRenderers/index.tsx`, add:
```tsx
import ButterflyChartRenderer from './ButterflyChartRenderer'
```
```tsx
  butterfly: ButterflyChartRenderer,
```

- [ ] **Step 8: Add `WidgetType`, `WIDGET_CATALOG`, `ROLE_SPECS` entries**

In `frontend/src/types/report.ts`:

1. Add `| 'butterfly'` to `WidgetType`.
2. Add to `WIDGET_CATALOG`:
```ts
  { type: 'butterfly' as WidgetType, label: 'Butterfly Chart', category: 'Charts', icon: '⋈', defaultW: 6, defaultH: 5 },
```
3. Add to `ROLE_SPECS`:
```ts
  butterfly: [{ role: 'category', label: 'Dimension (Y-axis)', required: true },
              { role: 'measure',  label: 'Left side',          required: true },
              { role: 'measure2', label: 'Right side',         required: true }],
```

- [ ] **Step 9: Add the icon**

Add `butterfly:'⋈'` to `WidgetConfigPanel.tsx`'s `widgetIcon()` map.

- [ ] **Step 10: Verify**

Run (from `frontend/`):
```bash
npm run build
```
Expected: exactly the 10 pre-existing errors.

- [ ] **Step 11: Commit**

```bash
git add backend/app/services/widget_data.py backend/tests/test_phase3_registrations.py frontend/src/components/report/chartRenderers/ButterflyChartRenderer.tsx frontend/src/components/report/chartRenderers/index.tsx frontend/src/types/report.ts frontend/src/components/report/WidgetConfigPanel.tsx
git commit -m "feat: add Butterfly Chart chart type (reuses shape_dual_series)"
```

---

### Task 10: Word Cloud (d3-cloud dependency + registration + frontend renderer)

**Files:**
- Modify: `backend/app/services/widget_data.py`
- Modify: `backend/tests/test_phase3_registrations.py`
- Modify: `frontend/package.json`
- Create: `frontend/src/components/report/chartRenderers/WordCloudRenderer.tsx`
- Modify: `frontend/src/components/report/chartRenderers/index.tsx`
- Modify: `frontend/src/types/report.ts`
- Modify: `frontend/src/components/report/WidgetConfigPanel.tsx`

**Interfaces:**
- Backend: Word Cloud's data shape (`{name, value}` per word) is identical to `shape_series`'s grouped-series output — no new shaper needed. `SHAPERS["word_cloud"] = shape_series`.
- Produces: `WordCloudRenderer: React.FC<ChartRendererProps>`, registered as `CHART_RENDERERS.word_cloud`. Reads `rows` (not `data` — this type reuses `shape_series` exactly like `bar`/`pie`/etc, so it uses the same `rows` prop those renderers use). Uses `d3-cloud` for word-placement layout, rendered as SVG `<text>` elements.
- Produces: `'word_cloud'` added to `WidgetType`/`WIDGET_CATALOG`/`ROLE_SPECS` (`category` as "Word text" required, `measure` as "Size weight" optional).
- New dependency: `d3-cloud` (~5KB, per the design spec) plus its type declarations.

**No new Vitest test for this renderer:** jsdom (the test environment) has no `<canvas>` implementation, which `d3-cloud` requires for text-width measurement during layout — adding real canvas support would require the heavy native `canvas` npm package. This matches Phase 1/2's already-documented choice to rely on build-clean + backend pytest + diff-based review instead of new component tests, and is an even stronger case for it here.

- [ ] **Step 1: Write the failing registration test**

Append to `backend/tests/test_phase3_registrations.py` (add the import and the new test, keep `test_butterfly_reuses_shape_dual_series` from Task 9 unchanged):
```python
from app.services.widget_data import shape_dual_series, shape_series, SHAPERS


def test_butterfly_reuses_shape_dual_series():
    """Butterfly's data shape ({name, value, value2}) is identical to dual_series'
    output -- no dedicated shaper needed, same pattern as bar/line/pie reusing
    shape_series in Phase 0."""
    assert SHAPERS["butterfly"] is shape_dual_series


def test_word_cloud_reuses_shape_series():
    """Word Cloud's data shape ({name, value} per word) is identical to
    shape_series' grouped-series output -- no dedicated shaper needed."""
    assert SHAPERS["word_cloud"] is shape_series
```
(The whole file is shown above for clarity — only the `shape_series` import and the new test function are actually new; `test_butterfly_reuses_shape_dual_series` is unchanged from Task 9.)

- [ ] **Step 2: Run test to verify it fails**

Run (from `backend/`):
```bash
.venv/Scripts/python.exe -m pytest tests/test_phase3_registrations.py -v
```
Expected: `test_butterfly_reuses_shape_dual_series` passes (from Task 9), `test_word_cloud_reuses_shape_series` FAILS — `KeyError` (`"word_cloud"` not registered yet).

- [ ] **Step 3: Register `word_cloud` in `SHAPERS`**

In `backend/app/services/widget_data.py`, in the `SHAPERS` dict, add:
```python
    "word_cloud": shape_series,
```

- [ ] **Step 4: Run the registration tests, confirm both pass**

Run (from `backend/`):
```bash
.venv/Scripts/python.exe -m pytest tests/test_phase3_registrations.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Run the full backend suite**

```bash
.venv/Scripts/python.exe -m pytest -q
```
Expected: all pass, no regressions.

- [ ] **Step 6: Add the `d3-cloud` dependency**

From `frontend/`, run:
```bash
npm install d3-cloud
npm view @types/d3-cloud version
```
If `@types/d3-cloud` exists on the registry (it does, as a DefinitelyTyped package, as of this plan's writing — the `npm view` command above confirms the currently published version), install it as a dev dependency:
```bash
npm install -D @types/d3-cloud
```
If that command fails (package no longer published), instead create a minimal ambient declaration at `frontend/src/types/d3-cloud.d.ts`:
```ts
declare module 'd3-cloud' {
  interface Word { text?: string; size?: number; x?: number; y?: number; rotate?: number; [key: string]: unknown }
  interface Cloud<T extends Word = Word> {
    size(wh: [number, number]): Cloud<T>
    words(words: T[]): Cloud<T>
    padding(p: number | ((d: T) => number)): Cloud<T>
    rotate(fn: () => number): Cloud<T>
    font(name: string): Cloud<T>
    fontSize(fn: (d: T) => number): Cloud<T>
    on(event: 'end', cb: (words: T[]) => void): Cloud<T>
    start(): Cloud<T>
  }
  export default function cloud<T extends Word = Word>(): Cloud<T>
}
```
Report in your task report which path was taken.

- [ ] **Step 7: Create the renderer**

Create `frontend/src/components/report/chartRenderers/WordCloudRenderer.tsx`:
```tsx
import { useEffect, useRef, useState } from 'react'
import cloud from 'd3-cloud'
import { COLORS } from '../chartUtils'
import type { ChartRendererProps } from './types'

interface PlacedWord { text: string; size: number; x: number; y: number; rotate: number; fill: string }

export default function WordCloudRenderer({ rows, onClickPoint, broadcasts, localSelected }: ChartRendererProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ width: 600, height: 400 })
  const [placed, setPlaced] = useState<PlacedWord[]>([])

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const observer = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect
      if (width > 0 && height > 0) setSize({ width, height })
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    const words = (rows ?? []).filter(r => r.name != null)
    if (words.length === 0) { setPlaced([]); return }
    const values = words.map(w => Math.abs(Number(w.value) || 0))
    const maxV = Math.max(...values, 1)
    const minV = Math.min(...values, 0)
    const scaleSize = (v: number) => {
      const t = maxV > minV ? (Math.abs(v) - minV) / (maxV - minV) : 0.5
      return 14 + t * 46
    }
    let cancelled = false
    const layout = cloud()
      .size([size.width, size.height])
      .words(words.map(w => ({ text: String(w.name), value: Number(w.value) || 0 })))
      .padding(3)
      .rotate(() => (Math.random() < 0.7 ? 0 : 90))
      .font('sans-serif')
      .fontSize((d: any) => scaleSize(d.value))
      .on('end', (computed: any[]) => {
        if (cancelled) return
        setPlaced(computed.map((w, i) => ({
          text: w.text ?? '', size: w.size ?? 14, x: w.x ?? 0, y: w.y ?? 0, rotate: w.rotate ?? 0,
          fill: COLORS[i % COLORS.length],
        })))
      })
    layout.start()
    return () => { cancelled = true }
  }, [JSON.stringify(rows), size.width, size.height])

  if ((rows ?? []).length === 0) {
    return <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 12 }}>Configure widget to see data</div>
  }

  return (
    <div ref={containerRef} style={{ height: '100%', width: '100%', overflow: 'hidden' }}>
      <svg width={size.width} height={size.height}>
        <g transform={`translate(${size.width / 2},${size.height / 2})`}>
          {placed.map((w, i) => (
            <text key={i} textAnchor="middle"
              transform={`translate(${w.x},${w.y}) rotate(${w.rotate})`}
              style={{ fontSize: w.size, fontFamily: 'sans-serif', fill: w.fill, cursor: 'pointer',
                opacity: !broadcasts || localSelected === null || localSelected === w.text ? 1 : 0.35 }}
              onClick={() => onClickPoint(w.text)}>
              {w.text}
            </text>
          ))}
        </g>
      </svg>
    </div>
  )
}
```

- [ ] **Step 8: Register it**

In `frontend/src/components/report/chartRenderers/index.tsx`, add:
```tsx
import WordCloudRenderer from './WordCloudRenderer'
```
```tsx
  word_cloud: WordCloudRenderer,
```

- [ ] **Step 9: Add `WidgetType`, `WIDGET_CATALOG`, `ROLE_SPECS` entries**

In `frontend/src/types/report.ts`:

1. Add `| 'word_cloud'` to `WidgetType`.
2. Add to `WIDGET_CATALOG`:
```ts
  { type: 'word_cloud' as WidgetType, label: 'Word Cloud', category: 'Charts', icon: '☁', defaultW: 6, defaultH: 5 },
```
3. Add to `ROLE_SPECS`:
```ts
  word_cloud: [{ role: 'category', label: 'Word text',                required: true },
               { role: 'measure',  label: 'Size weight (optional)',   required: false }],
```

- [ ] **Step 10: Add the icon**

Add `word_cloud:'☁'` to `WidgetConfigPanel.tsx`'s `widgetIcon()` map.

- [ ] **Step 11: Verify**

Run (from `frontend/`):
```bash
npm run build
```
Expected: exactly the 10 pre-existing errors (confirm the new `d3-cloud` import doesn't introduce any new TypeScript errors — if it does, and Step 6's `@types/d3-cloud` install didn't resolve them, fall back to the ambient declaration file from Step 6).

- [ ] **Step 12: Commit**

```bash
git add backend/app/services/widget_data.py frontend/package.json frontend/package-lock.json frontend/src/components/report/chartRenderers/WordCloudRenderer.tsx frontend/src/components/report/chartRenderers/index.tsx frontend/src/types/report.ts frontend/src/components/report/WidgetConfigPanel.tsx
git add frontend/src/types/d3-cloud.d.ts 2>/dev/null || true
git commit -m "feat: add Word Cloud chart type (reuses shape_series, adds d3-cloud dependency)"
```

---

### Task 11: Backend `shape_vector_plot` shaper

**Files:**
- Modify: `backend/app/services/widget_data.py`
- Test: `backend/tests/test_shape_vector_plot.py`

**Interfaces:**
- Produces: `shape_vector_plot(df, config) -> dict` — roles: `measure` (x, required), `measure2` (y, required), `size` (magnitude, required), `direction` (**new role introduced by this task**, required — angle in degrees, `0` = pointing right/east, increasing counter-clockwise, standard math convention). Row-level detail, no aggregation. Returns `{"type": "vector_plot", "x": ..., "y": ..., "size": ..., "direction": ..., "rows": [{"x", "y", "size", "direction"}], "total": ...}`.
- Registers: `SHAPERS["vector_plot"] = shape_vector_plot`.

**Dedup house rule applies:** `x`/`y`/`size`/`direction` are selected together via `df[cols]`, so `list(dict.fromkeys(cols))` is required before the selection (matching `shape_gantt`'s pattern) — with a dedicated test.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_shape_vector_plot.py`:
```python
import pandas as pd
from app.services.widget_data import shape_vector_plot, SHAPERS


def sample_df():
    return pd.DataFrame({
        "px": [0, 1, 2],
        "py": [0, 1, 2],
        "magnitude": [5, 10, 15],
        "angle": [0, 90, 180],
    })


def test_builds_one_row_per_point():
    config = {"roles": {"measure": "px", "measure2": "py", "size": "magnitude", "direction": "angle"}}
    result = shape_vector_plot(sample_df(), config)
    assert result["type"] == "vector_plot"
    assert len(result["rows"]) == 3
    r = result["rows"][1]
    assert r["x"] == 1 and r["y"] == 1 and r["size"] == 10 and r["direction"] == 90


def test_column_collision_does_not_crash():
    """House rule: size and direction resolving to the same column must not crash."""
    config = {"roles": {"measure": "px", "measure2": "py", "size": "magnitude", "direction": "magnitude"}}
    result = shape_vector_plot(sample_df(), config)
    assert result["type"] == "vector_plot"
    assert len(result["rows"]) == 3
    assert result["rows"][0]["size"] == result["rows"][0]["direction"]


def test_missing_required_role_returns_empty():
    config = {"roles": {"measure": "px", "measure2": "py", "size": "magnitude"}}   # no direction
    result = shape_vector_plot(sample_df(), config)
    assert result == {"type": "empty", "rows": [], "total": 0}


def test_respects_limit():
    df = pd.DataFrame({"a": list(range(500)), "b": list(range(500)), "s": list(range(500)), "d": list(range(500))})
    config = {"roles": {"measure": "a", "measure2": "b", "size": "s", "direction": "d"}, "limit": 10}
    result = shape_vector_plot(df, config)
    assert len(result["rows"]) == 10


def test_registered_in_shapers():
    assert SHAPERS["vector_plot"] is shape_vector_plot
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`):
```bash
.venv/Scripts/python.exe -m pytest tests/test_shape_vector_plot.py -v
```
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement `shape_vector_plot` and register it**

In `backend/app/services/widget_data.py`, add after `shape_gantt`:
```python
def shape_vector_plot(df: pd.DataFrame, config: dict) -> dict:
    """roles: measure (x), measure2 (y), size (magnitude/length), direction
    (angle in degrees, 0 = pointing right/east, counter-clockwise -- standard
    math convention). Row-level detail -- each source row becomes one arrow,
    no aggregation."""
    filters = config.get("filters", [])
    roles = resolve_roles(config)
    x = roles.get("measure")
    y = roles.get("measure2")
    size = roles.get("size")
    direction = roles.get("direction")
    limit = int(config.get("limit") or 300)
    df = _apply_filters(df, filters)
    if df.empty or not x or not y or not size or not direction:
        return {"type": "empty", "rows": [], "total": 0}
    cols = list(dict.fromkeys([x, y, size, direction]))
    if any(c not in df.columns for c in cols):
        return {"type": "empty", "rows": [], "total": 0}
    sub = df[cols].dropna().head(limit)
    rows = []
    for _, row in sub.iterrows():
        rows.append({
            "x": _safe(row[x]), "y": _safe(row[y]),
            "size": _safe(row[size]), "direction": _safe(row[direction]),
        })
    return {"type": "vector_plot", "x": x, "y": y, "size": size, "direction": direction, "rows": rows, "total": len(df)}
```
Update the `SHAPERS` dict, adding:
```python
    "vector_plot": shape_vector_plot,
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `backend/`):
```bash
.venv/Scripts/python.exe -m pytest tests/test_shape_vector_plot.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Run the full backend suite**

```bash
.venv/Scripts/python.exe -m pytest -q
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/widget_data.py backend/tests/test_shape_vector_plot.py
git commit -m "feat: add shape_vector_plot shaper for Vector Plot chart type"
```

---

### Task 12: Frontend Vector Plot

**Files:**
- Create: `frontend/src/components/report/chartRenderers/VectorPlotRenderer.tsx`
- Modify: `frontend/src/components/report/chartRenderers/index.tsx`
- Modify: `frontend/src/types/report.ts`
- Modify: `frontend/src/components/report/WidgetConfigPanel.tsx`

**Interfaces:**
- Produces: `VectorPlotRenderer: React.FC<ChartRendererProps>`, registered as `CHART_RENDERERS.vector_plot`. Reads `data.rows` (`{x, y, size, direction}`). Full custom SVG with `<marker>`-based arrowheads — Recharts has no vector-field primitive.
- Produces: `'vector_plot'` added to `WidgetType`/`WIDGET_CATALOG`/`ROLE_SPECS` (`measure`, `measure2`, `size`, `direction`, all required).

- [ ] **Step 1: Create the renderer**

Create `frontend/src/components/report/chartRenderers/VectorPlotRenderer.tsx`:
```tsx
import type { ChartRendererProps } from './types'

const W = 1000
const H = 500
const PAD = 40

interface VecRow { x: number; y: number; size: number; direction: number }

export default function VectorPlotRenderer({ data, rtl }: ChartRendererProps) {
  const rows: VecRow[] = data?.rows ?? []

  if (rows.length === 0) {
    return <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 12 }}>Configure widget to see data</div>
  }

  const xs = rows.map(r => r.x), ys = rows.map(r => r.y), sizes = rows.map(r => Math.abs(r.size))
  const xMin = Math.min(...xs), xMax = Math.max(...xs)
  const yMin = Math.min(...ys), yMax = Math.max(...ys)
  const xRange = xMax - xMin || 1, yRange = yMax - yMin || 1
  const maxSize = Math.max(...sizes, 1)
  const plotW = W - PAD * 2, plotH = H - PAD * 2
  const toPxX = (v: number) => PAD + ((v - xMin) / xRange) * plotW
  const toPxY = (v: number) => H - PAD - ((v - yMin) / yRange) * plotH
  const maxArrowLen = Math.min(plotW, plotH) / 12

  return (
    <div style={{ height: '100%', width: '100%' }}>
      <svg width="100%" height="100%" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ display: 'block' }}>
        <defs>
          <marker id="vec-arrowhead" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
            <path d="M0,0 L6,3 L0,6 Z" fill="var(--accent)" />
          </marker>
        </defs>
        {rows.map((r, i) => {
          const cx = toPxX(r.x), cy = toPxY(r.y)
          const len = (Math.abs(r.size) / maxSize) * maxArrowLen
          const rad = (rtl ? 180 - r.direction : r.direction) * (Math.PI / 180)
          const dx = Math.cos(rad) * len, dy = -Math.sin(rad) * len
          return (
            <g key={i}>
              <line x1={cx} y1={cy} x2={cx + dx} y2={cy + dy} stroke="var(--accent)" strokeWidth={1.5} markerEnd="url(#vec-arrowhead)" />
              <title>{`(${r.x}, ${r.y}) size ${r.size} @ ${r.direction}°`}</title>
            </g>
          )
        })}
      </svg>
    </div>
  )
}
```

- [ ] **Step 2: Register it**

In `frontend/src/components/report/chartRenderers/index.tsx`, add:
```tsx
import VectorPlotRenderer from './VectorPlotRenderer'
```
```tsx
  vector_plot: VectorPlotRenderer,
```

- [ ] **Step 3: Add `WidgetType`, `WIDGET_CATALOG`, `ROLE_SPECS` entries**

In `frontend/src/types/report.ts`:

1. Add `| 'vector_plot'` to `WidgetType`.
2. Add to `WIDGET_CATALOG`:
```ts
  { type: 'vector_plot' as WidgetType, label: 'Vector Plot', category: 'Charts', icon: '⇗', defaultW: 6, defaultH: 6 },
```
3. Add to `ROLE_SPECS`:
```ts
  vector_plot: [{ role: 'measure',   label: 'X axis',                          required: true },
                { role: 'measure2',  label: 'Y axis',                          required: true },
                { role: 'size',      label: 'Magnitude',                       required: true },
                { role: 'direction', label: 'Direction (degrees, 0=east, CCW)', required: true }],
```

- [ ] **Step 4: Add the icon**

Add `vector_plot:'⇗'` to `WidgetConfigPanel.tsx`'s `widgetIcon()` map.

- [ ] **Step 5: Verify**

Run (from `frontend/`):
```bash
npm run build
```
Expected: exactly the 10 pre-existing errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/report/chartRenderers/VectorPlotRenderer.tsx frontend/src/components/report/chartRenderers/index.tsx frontend/src/types/report.ts frontend/src/components/report/WidgetConfigPanel.tsx
git commit -m "feat: add Vector Plot chart type"
```

---

### Task 13: Full regression pass and Phase 3 close-out

**Files:** none (verification only), plus the spec doc status line.

- [ ] **Step 1: Run the full automated test suite**

Backend (from `backend/`):
```bash
.venv/Scripts/python.exe -m pytest -v
```
Expected: all tests pass, including this phase's new ones across `shape_box_plot`, `shape_waterfall`, `shape_gauge`, `shape_gantt`, `shape_vector_plot`, and both Phase 3 registration tests.

Frontend (from `frontend/`):
```bash
npm run build
npm run test -- --run
```
Expected: build shows exactly the 10 pre-existing errors; Vitest still shows the same 3 tests as before this phase (no new component tests added, per this plan's Global Constraints).

- [ ] **Step 2: Icon collision audit**

Read through `frontend/src/components/report/WidgetConfigPanel.tsx`'s `widgetIcon()` map in full and confirm all 28 chart-type icons (21 from Phases 0–2 + 7 new: `box_plot`, `waterfall`, `gauge`, `schedule`, `butterfly`, `word_cloud`, `vector_plot`) are visually distinct glyphs with no duplicates. Cross-check against `WIDGET_CATALOG` in `frontend/src/types/report.ts` to confirm both places agree on the same icon per type. Write a small script (as Phase 2's close-out did) rather than eyeballing — parse both maps programmatically and diff them.

- [ ] **Step 3: Full manual regression read**

1. Read through `frontend/src/components/report/chartRenderers/index.tsx` and confirm all 28 chart types are registered with distinct keys.
2. Read through `backend/app/services/widget_data.py`'s `SHAPERS` dict and confirm all 28 chart types plus `kpi`/`table`/`crosstab`/`list` map to real, defined functions (`butterfly`/`word_cloud` correctly point at `shape_dual_series`/`shape_series`, not placeholder stubs).
3. **`_LEGACY_ROLE_KEYS` check — this exact check caught a Critical, production-breaking bug at the end of BOTH Phase 1 and Phase 2.** This phase introduces three new roles: `end` (Schedule), `target` (Gauge), `direction` (Vector Plot). Trace whether `WidgetConfigPanel.tsx`'s `configKeyFor` emits these as their own role name (the default `?? role` fallback — check `ROLE_TO_CONFIG_KEY`, which currently only remaps `category`/`category2`/`measure`), meaning `_LEGACY_ROLE_KEYS` would ALSO need `end`/`target`/`direction` entries for `resolve_roles`'s legacy-key fallback path to recognize them (the frontend never sends a `roles` object in production, only flat legacy keys — this is why the gap is silent and dangerous). If confirmed (expected, given the established pattern), add `"end": "end", "target": "target", "direction": "direction"` to `_LEGACY_ROLE_KEYS` in `backend/app/services/widget_data.py`, and add a test to `backend/tests/test_resolve_roles.py` confirming `resolve_roles({"category": "task", "start": "s", "end": "e", "measure": "x", "target": "t", "direction": "d"})` returns all six roles correctly — mirroring the exact contract-locking test pattern used for Phase 1's `measure2`/`start` fix and Phase 2's `size`/`color`/`group`/`animation` fix. Update the existing `test_all_legacy_role_keys_map_to_themselves_or_a_known_rename` test's expected dict to include the three new entries so it doesn't silently pass while missing coverage.

- [ ] **Step 4: Update the design spec status**

In `docs/superpowers/specs/2026-08-10-chart-type-expansion-design.md`, change the `**Status:**` line from `Phase 2 Complete` to `Phase 3 Complete — all 28 planned chart types live (Vector Plot included per full-scope request, despite being flagged as droppable in the original phasing)`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/widget_data.py backend/tests/test_resolve_roles.py docs/superpowers/specs/2026-08-10-chart-type-expansion-design.md
git commit -m "fix: extend _LEGACY_ROLE_KEYS for Phase 3 roles (end/target/direction); docs: mark Phase 3 complete"
```

**Phase 3 is now done — all 28 planned chart types are live. This completes the entire "chart type expansion" sub-project.** Per the roadmap, the next sub-project is the auth/user system, which is a prerequisite for the row-level security work requested alongside it.
