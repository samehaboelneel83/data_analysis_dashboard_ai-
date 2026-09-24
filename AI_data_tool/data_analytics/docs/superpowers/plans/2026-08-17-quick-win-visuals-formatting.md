# Quick-Win Visuals + Formatting & Layout Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close 6 Feature Parity Audit gaps per the approved spec at
`docs/superpowers/specs/2026-08-17-quick-win-visuals-formatting-design.md`: Area, Funnel, Card,
and Ribbon chart types; Themes; a Tab order pane; multi-select with Align/Distribute tools.

**Architecture:** Area/Funnel/Ribbon reuse existing backend shapers verbatim (one-line `SHAPERS`
dict aliases). Card gets one new, small shaper. Themes mutate `chartUtils.tsx`'s `COLORS` array in
place so every `getFillFactory`-based renderer picks it up with no per-renderer changes. Tab order
reuses the established `Widget.config` JSON-bag pattern (no migration). Multi-select is a new,
separate selection concept from the existing single-widget `selectedW`.

**Tech Stack:** FastAPI + SQLAlchemy + pandas (backend), React + TypeScript + recharts +
Vitest/Testing Library (frontend), pytest + httpx (backend tests).

## Global Constraints

- TDD throughout: failing test → confirm RED for the right reason → minimal implementation →
  confirm GREEN → full suite → commit.
- Frontend commands must run from `frontend/` explicitly (cwd has repeatedly drifted to the repo
  root mid-session, silently picking up a stray global `vitest` and breaking the jsdom
  environment).
- New per-widget/per-page settings go in the existing `config`/JSON-bag columns, not new migrated
  columns, unless the spec says otherwise (Theme is the one exception — a real new `Report`
  column).
- Every new chart type needs: `WidgetType` union entry, `WIDGET_CATALOG` entry, `ROLE_SPECS`
  entry (all in `frontend/src/types/report.ts`), a `SHAPERS` dict entry (backend), and — for
  Area/Funnel/Ribbon — a `CHART_RENDERERS` entry in `chartRenderers/index.tsx` pointing at a new
  renderer file implementing `ChartRendererProps`.

---

## Task 1: Area chart

**Files:**
- Modify: `backend/app/services/widget_data.py`
- Modify: `frontend/src/types/report.ts`
- Create: `frontend/src/components/report/chartRenderers/AreaChartRenderer.tsx`
- Modify: `frontend/src/components/report/chartRenderers/index.tsx`
- Test: `backend/tests/test_widget_data_area_funnel.py`, `frontend/src/components/report/chartRenderers/index.test.tsx`

**Interfaces:**
- Produces: `WidgetType` includes `'area'`; `SHAPERS["area"] = shape_series`.

- [ ] **Step 1: Write the failing backend test**

```python
# backend/tests/test_widget_data_area_funnel.py
import pandas as pd
from app.services.widget_data import get_widget_data_from_df


def test_area_widget_type_uses_the_same_shaper_as_bar():
    df = pd.DataFrame({"region": ["North", "South", "North"], "sales": [10, 20, 5]})
    config = {"roles": {"category": "region", "measure": "sales"}, "aggregation": "sum"}
    bar_result = get_widget_data_from_df(df, config, "bar")
    area_result = get_widget_data_from_df(df, config, "area")
    assert area_result == bar_result
```

- [ ] **Step 2: Run and confirm it fails** — `'area'` isn't in `SHAPERS`, so it currently falls
  back to `shape_series` anyway via `get_widget_data_from_df`'s default — **run this first to
  check**; if it already passes because of the fallback, this step's "RED" is establishing the
  explicit registration as a documented contract rather than an accidental fallback. Either way,
  proceed to Step 3 to make the mapping explicit.

- [ ] **Step 3: Implement (backend).** In `widget_data.py`'s `SHAPERS` dict, add:
```python
    "area": shape_series,
```
  In `frontend/src/types/report.ts`:
```ts
// WidgetType union: add | 'area'
// WIDGET_CATALOG: add after 'line' entry
{ type: 'area' as WidgetType, label: 'Area Chart', category: 'Charts', icon: '▲', defaultW: 6, defaultH: 5 },
// ROLE_SPECS: add
area: [{ role: 'category', label: 'Dimension (Group / X-axis)', required: true },
       { role: 'measure',  label: 'Measure (numeric column)',   required: false }],
```

- [ ] **Step 4: Create the renderer**

```tsx
// frontend/src/components/report/chartRenderers/AreaChartRenderer.tsx
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { TT, fmtStr, COLORS } from '../chartUtils'
import type { ChartRendererProps } from './types'

export default function AreaChartRenderer({ rows, cfg, rtl, broadcasts, onClickPoint, measureFmt }: ChartRendererProps) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={rows} margin={{ top: 4, right: 8, bottom: 20, left: 0 }}
        onClick={broadcasts ? (d: any) => d?.activePayload?.[0] && onClickPoint(d.activePayload[0].payload.name) : undefined}
        style={{ cursor: broadcasts ? 'pointer' : 'default' }}
      >
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis dataKey="name" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} angle={-30} textAnchor="end" reversed={rtl} />
        <YAxis tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} orientation={rtl ? 'right' : 'left'} tickFormatter={v => fmtStr(v, measureFmt)} allowDecimals={false} />
        <Tooltip contentStyle={TT} formatter={(v: unknown) => [fmtStr(v, measureFmt), cfg.measure ?? 'value']} />
        <Area type="monotone" dataKey="value" stroke={COLORS[0]} fill={COLORS[0]} fillOpacity={0.35} strokeWidth={2} />
      </AreaChart>
    </ResponsiveContainer>
  )
}
```

- [ ] **Step 5: Register in `chartRenderers/index.tsx`**

```ts
import AreaChartRenderer from './AreaChartRenderer'
// in CHART_RENDERERS:
area: AreaChartRenderer,
```

- [ ] **Step 6: Write the frontend render test** in `chartRenderers/index.test.tsx`, following
  that file's existing pattern (check the file first for its exact per-type assertion shape —
  it likely renders each registered type with sample rows and asserts no crash / a data-testid
  from `ResponsiveContainer`'s children). Add an `'area'` case matching the existing ones exactly.

- [ ] **Step 7: Run backend + frontend tests, confirm both green.**

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/widget_data.py backend/tests/test_widget_data_area_funnel.py frontend/src/types/report.ts frontend/src/components/report/chartRenderers/AreaChartRenderer.tsx frontend/src/components/report/chartRenderers/index.tsx frontend/src/components/report/chartRenderers/index.test.tsx
git commit -m "Add Area chart type"
```

---

## Task 2: Funnel chart

**Files:**
- Modify: `backend/app/services/widget_data.py` (same test file as Task 1 — add a second test)
- Modify: `frontend/src/types/report.ts`
- Create: `frontend/src/components/report/chartRenderers/FunnelChartRenderer.tsx`
- Modify: `frontend/src/components/report/chartRenderers/index.tsx`, `index.test.tsx`

**Interfaces:**
- Produces: `WidgetType` includes `'funnel'`; `SHAPERS["funnel"] = shape_series`.

- [ ] **Step 1: Add the failing test** to `test_widget_data_area_funnel.py`:

```python
def test_funnel_widget_type_uses_the_same_shaper_as_bar():
    df = pd.DataFrame({"stage": ["Visit", "Signup", "Purchase"], "count": [100, 40, 10]})
    config = {"roles": {"category": "stage", "measure": "count"}, "aggregation": "sum"}
    bar_result = get_widget_data_from_df(df, config, "bar")
    funnel_result = get_widget_data_from_df(df, config, "funnel")
    assert funnel_result == bar_result
```

- [ ] **Step 2: Run and confirm the registration is explicit** (same fallback caveat as Task 1
  Step 2).

- [ ] **Step 3: Implement.** `SHAPERS["funnel"] = shape_series`. `types.ts`:
```ts
// WidgetType: add | 'funnel'
{ type: 'funnel' as WidgetType, label: 'Funnel', category: 'Charts', icon: '▽', defaultW: 5, defaultH: 6 },
funnel: [{ role: 'category', label: 'Stage', required: true },
         { role: 'measure',  label: 'Value',  required: false }],
```

- [ ] **Step 4: Create the renderer** — recharts' built-in Funnel components:

```tsx
// frontend/src/components/report/chartRenderers/FunnelChartRenderer.tsx
import { FunnelChart, Funnel, LabelList, Tooltip, Cell, ResponsiveContainer } from 'recharts'
import { TT, fmtStr, getFillFactory } from '../chartUtils'
import type { ChartRendererProps } from './types'

export default function FunnelChartRenderer({ rows, broadcasts, localSelected, onClickPoint, measureFmt }: ChartRendererProps) {
  const getFill = getFillFactory(broadcasts, localSelected)
  return (
    <ResponsiveContainer width="100%" height="100%">
      <FunnelChart>
        <Tooltip contentStyle={TT} formatter={(v: unknown) => fmtStr(v, measureFmt)} />
        <Funnel dataKey="value" data={rows} isAnimationActive={false}
          onClick={broadcasts ? (d: any) => onClickPoint(d.name) : undefined}
          style={{ cursor: broadcasts ? 'pointer' : 'default' }}
        >
          {rows.map((r: any, i: number) => {
            const s = getFill(r.name, i)
            return <Cell key={i} fill={s.fill} opacity={s.opacity} stroke={s.stroke} strokeWidth={s.strokeWidth} />
          })}
          <LabelList dataKey="name" position="right" fill="var(--text)" fontSize={11} />
        </Funnel>
      </FunnelChart>
    </ResponsiveContainer>
  )
}
```

- [ ] **Step 5: Register + test**, same pattern as Task 1 Steps 5-6, adding a `'funnel'` case.

- [ ] **Step 6: Run backend + frontend tests, confirm green.**

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/widget_data.py backend/tests/test_widget_data_area_funnel.py frontend/src/types/report.ts frontend/src/components/report/chartRenderers/FunnelChartRenderer.tsx frontend/src/components/report/chartRenderers/index.tsx frontend/src/components/report/chartRenderers/index.test.tsx
git commit -m "Add Funnel chart type"
```

---

## Task 3: Card / Multi-row card widget

**Files:**
- Modify: `backend/app/services/widget_data.py`
- Test: `backend/tests/test_shape_card.py`
- Modify: `frontend/src/types/report.ts`
- Modify: `frontend/src/components/report/WidgetRenderer.tsx`
- Test: `frontend/src/components/report/WidgetRenderer.test.tsx`

**Interfaces:**
- Produces: `shape_card(df, config) -> {"rows": [{"name": measure, "value": agg}], "total": int}`;
  `SHAPERS["card"] = shape_card`; `WidgetType` includes `'card'`;
  `ROLE_SPECS.card = [{ role: 'measures', label: 'Fields', multi: true, required: true }]`.

- [ ] **Step 1: Write the failing backend test**

```python
# backend/tests/test_shape_card.py
import pandas as pd
from app.services.widget_data import shape_card


def test_shape_card_aggregates_each_measure_independently():
    df = pd.DataFrame({"revenue": [10, 20, 30], "cost": [5, 5, 10]})
    config = {"roles": {"measures": ["revenue", "cost"]}, "aggregation": "sum"}
    result = shape_card(df, config)
    assert result["rows"] == [{"name": "revenue", "value": 60}, {"name": "cost", "value": 20}]


def test_shape_card_respects_the_configured_aggregation():
    df = pd.DataFrame({"revenue": [10, 20, 30]})
    config = {"roles": {"measures": ["revenue"]}, "aggregation": "avg"}
    result = shape_card(df, config)
    assert result["rows"] == [{"name": "revenue", "value": 20}]
```

- [ ] **Step 2: Run and confirm it fails** — `shape_card` doesn't exist (`ImportError`).

- [ ] **Step 3: Implement.** In `widget_data.py`, near `shape_gauge` (reuses its `_agg_series`
  helper and `resolve_roles`/`_apply_filters` conventions):

```python
def shape_card(df: pd.DataFrame, config: dict) -> dict:
    """roles: measures (multi, required) — each aggregated independently to a single
    value using the widget's configured aggregation. Powers the Card / Multi-row card
    widget: one row per measure, same {name, value} shape the list widget already uses."""
    filters = config.get("filters", [])
    roles = resolve_roles(config)
    measures = roles.get("measures") or []
    agg = (config.get("aggregation") or "sum").lower()
    df = _apply_filters(df, filters)
    if df.empty or not measures:
        return {"rows": [], "total": 0}
    rows = [{"name": m, "value": _agg_series(df[m], agg)} for m in measures if m in df.columns]
    return {"rows": rows, "total": len(df)}
```
  Add `"card": shape_card` to `SHAPERS`.

- [ ] **Step 4: Run and confirm the backend test passes.**

- [ ] **Step 5: Frontend types.** In `types/report.ts`:
```ts
// WidgetType: add | 'card'
{ type: 'card' as WidgetType, label: 'Card', category: 'Controls', icon: '▤', defaultW: 4, defaultH: 3 },
card: [{ role: 'measures', label: 'Fields', multi: true, required: true }],
```

- [ ] **Step 6: Write the failing frontend test** in `WidgetRenderer.test.tsx`:

```tsx
describe('WidgetRenderer card', () => {
  it('renders one label+value row per measure', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [{ name: 'revenue', value: 60 }, { name: 'cost', value: 20 }], sampled: false })
    renderWidget({ widget: barWidget({ widget_type: 'card', config: { measures: ['revenue', 'cost'] } }) })
    expect(await screen.findByText('revenue')).toBeInTheDocument()
    expect(screen.getByText('60')).toBeInTheDocument()
    expect(screen.getByText('cost')).toBeInTheDocument()
    expect(screen.getByText('20')).toBeInTheDocument()
  })
})
```

- [ ] **Step 7: Run and confirm it fails** — no `wt === 'card'` branch in `WidgetBody`.

- [ ] **Step 8: Implement.** In `WidgetRenderer.tsx`'s `WidgetBody`, beside the existing `kpi`
  branch:

```tsx
// Card / multi-row card
if (wt === 'card') {
  const rows: any[] = data.rows ?? []
  return (
    <div dir={rtl ? 'rtl' : undefined} style={{ height: '100%', overflow: 'auto', display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 10, padding: 8 }}>
      {rows.map((row, i) => (
        <div key={i} style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'var(--mono)', color: 'var(--accent)' }}>
            {fmtStr(row.value, allFormats?.[row.name])}
          </div>
          <div style={{ fontSize: 10, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em' }}>{row.name}</div>
        </div>
      ))}
    </div>
  )
}
```
  (Place this branch after the `if (!data) return <EmptyState .../>` guard, alongside `kpi`.)

- [ ] **Step 9: Run and confirm it passes. Run the full frontend suite.**

- [ ] **Step 10: Commit**

```bash
git add backend/app/services/widget_data.py backend/tests/test_shape_card.py frontend/src/types/report.ts frontend/src/components/report/WidgetRenderer.tsx frontend/src/components/report/WidgetRenderer.test.tsx
git commit -m "Add Card / Multi-row card widget"
```

---

## Task 4: Ribbon chart (stacked-bar approximation)

**Files:**
- Modify: `backend/app/services/widget_data.py`
- Test: `backend/tests/test_widget_data_area_funnel.py` (rename mentally to "…and ribbon", just
  add a case)
- Modify: `frontend/src/types/report.ts`
- Create: `frontend/src/components/report/chartRenderers/RibbonChartRenderer.tsx`
- Modify: `frontend/src/components/report/chartRenderers/index.tsx`, `index.test.tsx`

**Interfaces:**
- Produces: `WidgetType` includes `'ribbon'`; `SHAPERS["ribbon"] = shape_heatmap`.

- [ ] **Step 1: Write the failing backend test**

```python
def test_ribbon_widget_type_uses_the_same_shaper_as_heatmap():
    df = pd.DataFrame({"month": ["Jan", "Jan", "Feb"], "product": ["A", "B", "A"], "sales": [10, 20, 15]})
    config = {"roles": {"category": "month", "category2": "product", "measure": "sales"}, "aggregation": "sum"}
    heatmap_result = get_widget_data_from_df(df, config, "heatmap")
    ribbon_result = get_widget_data_from_df(df, config, "ribbon")
    assert ribbon_result == heatmap_result
```

- [ ] **Step 2: Run and confirm it fails / registration is explicit** (same fallback caveat).

- [ ] **Step 3: Implement.** `SHAPERS["ribbon"] = shape_heatmap`. `types.ts`:
```ts
// WidgetType: add | 'ribbon'
{ type: 'ribbon' as WidgetType, label: 'Ribbon Chart', category: 'Charts', icon: '▬', defaultW: 7, defaultH: 5 },
ribbon: [{ role: 'category',  label: 'Rows (Y-axis)',    required: true },
         { role: 'category2', label: 'Columns (X-axis)', required: true },
         { role: 'measure',   label: 'Cell value',       required: true }],
```

- [ ] **Step 4: Create the renderer.** `shape_heatmap`'s actual output (confirmed by reading
  `widget_data.py`'s `shape_heatmap` and its existing consumer `HeatMapRenderer.tsx`) is
  **not** a `rows` array at all — it's `{ rows_axis: string[], cols_axis: string[], cells:
  (number|null)[][], min, max, total }`, delivered through the `data` prop, not `rows`
  (`ChartRendererProps.rows` comes from `data.rows ?? []`, which is empty for this shape). Reshape
  from `data` directly:

```tsx
// frontend/src/components/report/chartRenderers/RibbonChartRenderer.tsx
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { TT, COLORS } from '../chartUtils'
import type { ChartRendererProps } from './types'

// Reshapes shape_heatmap's matrix ({ rows_axis, cols_axis, cells }) into recharts' stacked-bar
// wide format: one object per rows_axis value, with one numeric key per cols_axis value.
function toStacked(data: any) {
  const rowsAxis: string[] = data?.rows_axis ?? []
  const colsAxis: string[] = data?.cols_axis ?? []
  const cells: (number | null)[][] = data?.cells ?? []
  const stacked = rowsAxis.map((r, i) => {
    const obj: Record<string, unknown> = { name: r }
    colsAxis.forEach((c, j) => { obj[c] = cells[i]?.[j] ?? 0 })
    return obj
  })
  return { stacked, cols: colsAxis }
}

export default function RibbonChartRenderer({ data }: ChartRendererProps) {
  const { stacked, cols } = toStacked(data)
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={stacked} margin={{ top: 4, right: 8, bottom: 20, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis dataKey="name" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} allowDecimals={false} />
        <Tooltip contentStyle={TT} />
        <Legend wrapperStyle={{ fontSize: 10 }} />
        {cols.map((c, i) => (
          <Bar key={c} dataKey={c} stackId="ribbon" fill={COLORS[i % COLORS.length]} radius={i === cols.length - 1 ? [4, 4, 0, 0] : undefined} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  )
}
```

- [ ] **Step 5: Register + test**, same pattern as prior tasks, adding a `'ribbon'` case with
  sample `data: { rows_axis, cols_axis, cells }` input (not `rows` — see Step 4) matching what
  `index.test.tsx`'s existing per-type cases pass as their mock `data` prop.

- [ ] **Step 6: Run backend + frontend tests, confirm green.**

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/widget_data.py backend/tests/test_widget_data_area_funnel.py frontend/src/types/report.ts frontend/src/components/report/chartRenderers/RibbonChartRenderer.tsx frontend/src/components/report/chartRenderers/index.tsx frontend/src/components/report/chartRenderers/index.test.tsx
git commit -m "Add Ribbon chart type (stacked-bar approximation)"
```

---

## Task 5: Report theme — backend

**Files:**
- Modify: `backend/app/models/models.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/schemas/schemas.py`
- Test: `backend/tests/test_report_theme.py`

**Interfaces:**
- Produces: `Report.theme: str` (default `"default"`); `ReportUpdate.theme: Optional[str]`;
  `ReportOut.theme: str`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_report_theme.py
from app.models.models import Report


async def test_report_theme_defaults_to_default(db_session):
    report = Report(name="R")
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)
    assert report.theme == "default"


async def test_report_theme_can_be_set(db_session):
    report = Report(name="R", theme="ocean")
    db_session.add(report)
    await db_session.commit()
    await db_session.refresh(report)
    assert report.theme == "ocean"
```

- [ ] **Step 2: Run and confirm it fails** — `'theme'` is an invalid keyword argument.

- [ ] **Step 3: Implement.** In `models.py`'s `Report` class:
```python
    theme = Column(String(20), nullable=False, default="default", server_default="default")
```
  In `main.py`'s `_migrate()`:
```python
        "ALTER TABLE reports ADD COLUMN IF NOT EXISTS theme VARCHAR(20) NOT NULL DEFAULT 'default'",
```
  In `schemas.py`: add `theme: Optional[str] = None` to `ReportUpdate`, `theme: str = "default"` to
  `ReportOut`.

- [ ] **Step 4: Run and confirm it passes. Run the full backend suite.**

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/models.py backend/app/main.py backend/app/schemas/schemas.py backend/tests/test_report_theme.py
git commit -m "Add Report.theme column"
```

---

## Task 6: Themes — frontend

**Files:**
- Create: `frontend/src/components/report/themes.ts`
- Modify: `frontend/src/components/report/chartUtils.tsx`
- Test: `frontend/src/components/report/chartUtils.test.ts`
- Modify: `frontend/src/pages/ReportBuilder.tsx`
- Test: `frontend/src/pages/ReportBuilder.test.tsx`

**Interfaces:**
- Produces: `THEMES: Record<string, string[]>`; `applyTheme(name: string): void` (exported from
  `chartUtils.tsx`, mutates `COLORS` in place).

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/components/report/chartUtils.test.ts
import { describe, it, expect } from 'vitest'
import { COLORS, applyTheme } from './chartUtils'
import { THEMES } from './themes'

describe('applyTheme', () => {
  it('mutates the shared COLORS array in place so existing imports see the update', () => {
    const originalLength = COLORS.length
    applyTheme('ocean')
    expect(COLORS).toEqual(THEMES.ocean)
    applyTheme('default')
    expect(COLORS).toEqual(THEMES.default)
    expect(COLORS.length).toBe(originalLength === THEMES.default.length ? THEMES.default.length : COLORS.length)
  })

  it('falls back to the default theme for an unknown name', () => {
    applyTheme('not-a-real-theme')
    expect(COLORS).toEqual(THEMES.default)
  })
})
```

- [ ] **Step 2: Run and confirm it fails** — `applyTheme`/`THEMES` don't exist.

- [ ] **Step 3: Implement.**

```ts
// frontend/src/components/report/themes.ts
export const THEMES: Record<string, string[]> = {
  default: ['#6c8fff','#a78bfa','#34d399','#fbbf24','#f87171','#38bdf8','#fb7185','#4ade80','#c084fc','#e879f9'],
  ocean:   ['#0ea5e9','#06b6d4','#14b8a6','#22d3ee','#3b82f6','#0891b2','#0284c7','#67e8f9','#38bdf8','#7dd3fc'],
  sunset:  ['#f97316','#fb923c','#f59e0b','#fbbf24','#ef4444','#f87171','#fb7185','#fda4af','#facc15','#fdba74'],
  forest:  ['#22c55e','#16a34a','#4ade80','#84cc16','#65a30d','#a3e635','#15803d','#86efac','#bef264','#166534'],
  mono:    ['#94a3b8','#64748b','#475569','#cbd5e1','#334155','#e2e8f0','#1e293b','#f1f5f9','#0f172a','#f8fafc'],
}
```

  In `chartUtils.tsx`, add (below the existing `COLORS` export):
```ts
import { THEMES } from './themes'

export function applyTheme(name: string) {
  const next = THEMES[name] ?? THEMES.default
  COLORS.length = 0
  COLORS.push(...next)
}
```

- [ ] **Step 4: Run and confirm it passes.**

- [ ] **Step 5: Write the failing ReportBuilder test**

```tsx
it('applies the report theme on load and lets the user pick a different one from the Home tab', async () => {
  const report = baseReport()
  ;(report as any).theme = 'default'
  vi.mocked(reportsApi.get).mockResolvedValue(report as any)
  vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
  vi.mocked(reportsApi.update).mockResolvedValue({ ...report, theme: 'ocean' } as any)
  renderBuilder()
  await screen.findByTestId('view-strip')

  fireEvent.click(screen.getByRole('tab', { name: 'Home' }))
  const ribbonContent = within(screen.getByTestId('ribbon-content'))
  fireEvent.click(ribbonContent.getByRole('button', { name: /Ocean/i }))

  expect(reportsApi.update).toHaveBeenCalledWith(1, { theme: 'ocean' })
})
```

- [ ] **Step 6: Run and confirm it fails.**

- [ ] **Step 7: Implement.** In `ReportBuilder.tsx`:
  - Call `applyTheme(report.theme ?? 'default')` inside `loadReport` right after `setReport(r)`
    (import `applyTheme` from `../components/report/chartUtils`).
  - Add a `useEffect` injecting the theme picker into the ribbon's Home tab, mirroring the
    Insert/View/Optimize tab injection pattern already in this file:
```tsx
useEffect(() => {
  setTabContent('home', (
    <div style={{ display: 'flex', gap: 4 }}>
      {Object.keys(THEMES).map(name => (
        <button key={name} onClick={() => reportsApi.update(reportId, { theme: name }).then(() => { applyTheme(name); loadReport() })}
          title={name} style={{ width: 20, height: 20, borderRadius: '50%', border: report?.theme === name ? '2px solid var(--text)' : '1px solid var(--border)',
            background: THEMES[name][0], cursor: 'pointer' }} />
      ))}
    </div>
  ))
  return () => clearTabContent('home')
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, [report?.theme, reportId, setTabContent, clearTabContent])
```
    (Import `THEMES` from `../components/report/themes`.) Note the test above clicks a button
    named `/Ocean/i` — since these buttons currently have no visible text (just a `title`), give
    each an `aria-label={name}` too so `getByRole('button', { name })` matches; capitalize for
    display via `title`/`aria-label={name[0].toUpperCase() + name.slice(1)}`.

- [ ] **Step 8: Run and confirm it passes. Run the full frontend suite.**

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/report/themes.ts frontend/src/components/report/chartUtils.tsx frontend/src/components/report/chartUtils.test.ts frontend/src/pages/ReportBuilder.tsx frontend/src/pages/ReportBuilder.test.tsx
git commit -m "Add report Themes: 5 built-in palettes, picker in the ribbon Home tab"
```

---

## Task 7: Tab order pane

**Files:**
- Create: `frontend/src/components/report/TabOrderPane.tsx`
- Test: `frontend/src/components/report/TabOrderPane.test.tsx`
- Modify: `frontend/src/pages/ReportBuilder.tsx`
- Test: `frontend/src/pages/ReportBuilder.test.tsx`

**Interfaces:**
- Produces: `TabOrderPane({ widgets, onUpdate }: { widgets: Widget[]; onUpdate: (widgetId: number,
  config: Record<string, unknown>) => void })` — reorder list writing sequential `tabIndex`
  values; `rightPanelMode` gains `'taborder'`.

- [ ] **Step 1: Write the failing test** (mirrors `SelectionPane.test.tsx`/
  `MobileLayoutEditor.test.tsx`):

```tsx
// frontend/src/components/report/TabOrderPane.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import TabOrderPane from './TabOrderPane'
import type { Widget } from '../../types/report'

function widget(id: number, title: string, tabIndex?: number): Widget {
  return { id, page_id: 100, widget_type: 'bar', title, config: { tabIndex }, layout: { x: 0, y: 0, w: 6, h: 5 }, created_at: '2026-01-01' }
}

describe('TabOrderPane', () => {
  it('lists widgets ordered by their current tabIndex', () => {
    render(<TabOrderPane widgets={[widget(1, 'Second', 2), widget(2, 'First', 1)]} onUpdate={vi.fn()} />)
    const rows = screen.getAllByTestId('tab-order-row')
    expect(rows[0]).toHaveTextContent('First')
    expect(rows[1]).toHaveTextContent('Second')
  })

  it('moving a widget down renumbers everyone sequentially', () => {
    const onUpdate = vi.fn()
    render(<TabOrderPane widgets={[widget(1, 'First', 1), widget(2, 'Second', 2)]} onUpdate={onUpdate} />)
    fireEvent.click(screen.getAllByRole('button', { name: '↓' })[0])
    expect(onUpdate).toHaveBeenCalledWith(1, { tabIndex: 2 })
    expect(onUpdate).toHaveBeenCalledWith(2, { tabIndex: 1 })
  })
})
```

- [ ] **Step 2: Run and confirm it fails.**

- [ ] **Step 3: Implement**, following `MobileLayoutEditor.tsx`'s exact structure (order derived
  from current state, up/down buttons, `onUpdate` per affected widget):

```tsx
// frontend/src/components/report/TabOrderPane.tsx
import type { Widget } from '../../types/report'

export default function TabOrderPane({ widgets, onUpdate }: {
  widgets: Widget[]
  onUpdate: (widgetId: number, config: Record<string, unknown>) => void
}) {
  const ordered = [...widgets].sort((a, b) => ((a.config as any).tabIndex ?? 999) - ((b.config as any).tabIndex ?? 999))

  const move = (idx: number, dir: -1 | 1) => {
    const target = idx + dir
    if (target < 0 || target >= ordered.length) return
    const next = [...ordered]
    ;[next[idx], next[target]] = [next[target], next[idx]]
    next.forEach((w, i) => onUpdate(w.id, { ...w.config, tabIndex: i + 1 }))
  }

  return (
    <div style={{ padding: '14px 14px 0' }}>
      <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 8 }}>
        Tab order
      </div>
      <p style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 10 }}>
        Controls keyboard-Tab order through widgets in View mode.
      </p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {ordered.map((w, idx) => (
          <div key={w.id} data-testid="tab-order-row" style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '5px 7px', background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 6 }}>
            <span style={{ fontSize: 10, color: 'var(--muted)', fontFamily: 'var(--mono)', width: 16 }}>{idx + 1}</span>
            <span style={{ flex: 1, fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{w.title || w.widget_type}</span>
            <button onClick={() => move(idx, -1)} disabled={idx === 0} style={{ background: 'none', border: '1px solid var(--border)', borderRadius: 4, cursor: idx === 0 ? 'default' : 'pointer', fontSize: 11, padding: '1px 6px' }}>↑</button>
            <button onClick={() => move(idx, 1)} disabled={idx === ordered.length - 1} style={{ background: 'none', border: '1px solid var(--border)', borderRadius: 4, cursor: idx === ordered.length - 1 ? 'default' : 'pointer', fontSize: 11, padding: '1px 6px' }}>↓</button>
          </div>
        ))}
        {ordered.length === 0 && <span style={{ fontSize: 12, color: 'var(--muted)' }}>No widgets on this page.</span>}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run and confirm it passes.**

- [ ] **Step 5: Wire into ReportBuilder.** Add `'taborder'` to the `RightPanelMode` union. Add a
  "⇥ Tab order" view-strip button (same style/pattern as "👁 Selection"/"🔗 Sync slicers"/
  "🔖 Bookmarks"). Render `{rightPanelMode === 'taborder' && <TabOrderPane widgets={pageWidgets}
  onUpdate={(id, config) => reportsApi.updateWidget(reportId, activePage!.id, id, {
  config }).then(loadReport)} />}` (identical shape to the existing Selection pane wiring). In the
  desktop-grid widget-mapping loop, add `tabIndex={!editMode ? (widget.config as any).tabIndex :
  undefined}` to each widget's wrapper `<div>`.

- [ ] **Step 6: Write the failing ReportBuilder test**

```tsx
it('shows the Tab order pane and writes sequential tabIndex values on reorder', async () => {
  const report = reportWithWidget()
  report.pages[0].widgets.push({ id: 6, page_id: 100, widget_type: 'bar', title: 'Second Widget', config: { dimension: 'region' }, layout: { x: 0, y: 5, w: 6, h: 5 }, created_at: '2026-01-01' } as any)
  vi.mocked(reportsApi.get).mockResolvedValue(report as any)
  vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
  vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
  vi.mocked(reportsApi.updateWidget).mockResolvedValue({} as any)
  renderBuilder()
  await screen.findByTestId('view-strip')

  fireEvent.click(screen.getByRole('button', { name: /Tab order/i }))
  expect(await screen.findAllByTestId('tab-order-row')).toHaveLength(2)
})
```

- [ ] **Step 7: Run and confirm it passes. Run the full frontend suite.**

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/report/TabOrderPane.tsx frontend/src/components/report/TabOrderPane.test.tsx frontend/src/pages/ReportBuilder.tsx frontend/src/pages/ReportBuilder.test.tsx
git commit -m "Add Tab order pane for keyboard-navigation accessibility"
```

---

## Task 8: Align/Distribute pure functions

Landing the math first, with no UI, means Task 9 can wire a complete, fully-functional 8-button
toolbar in a single commit — no partially-wired/inert buttons ever get shipped.

**Files:**
- Create: `frontend/src/lib/alignment.ts`
- Test: `frontend/src/lib/alignment.test.ts`

**Interfaces:**
- Produces: `alignWidgets(layouts: Record<number, Widget['layout']>, mode:
  'left'|'center'|'right'|'top'|'middle'|'bottom'): Record<number, Partial<Widget['layout']>>` and
  `distributeWidgets(layouts: Record<number, Widget['layout']>, axis: 'horizontal'|'vertical'):
  Record<number, Partial<Widget['layout']>>` — pure functions, return only the changed `x`/`y`
  keys per widget id.

- [ ] **Step 1: Write the failing unit tests**

```ts
// frontend/src/lib/alignment.test.ts
import { describe, it, expect } from 'vitest'
import { alignWidgets, distributeWidgets } from './alignment'

const layouts = {
  1: { x: 0, y: 0, w: 2, h: 2 },
  2: { x: 4, y: 3, w: 2, h: 2 },
  3: { x: 8, y: 6, w: 2, h: 2 },
}

describe('alignWidgets', () => {
  it('aligns left to the minimum x', () => {
    expect(alignWidgets(layouts, 'left')).toEqual({ 1: { x: 0 }, 2: { x: 0 }, 3: { x: 0 } })
  })
  it('aligns right to the maximum right edge (x + w)', () => {
    expect(alignWidgets(layouts, 'right')).toEqual({ 1: { x: 8 }, 2: { x: 8 }, 3: { x: 8 } })
  })
  it('aligns top to the minimum y', () => {
    expect(alignWidgets(layouts, 'top')).toEqual({ 1: { y: 0 }, 2: { y: 0 }, 3: { y: 0 } })
  })
})

describe('distributeWidgets', () => {
  it('spaces widgets evenly between the first and last horizontally', () => {
    const result = distributeWidgets(layouts, 'horizontal')
    expect(result[1].x).toBe(0)
    expect(result[3].x).toBe(8)
    expect(result[2].x).toBe(4)
  })
})
```

- [ ] **Step 2: Run and confirm it fails** — `frontend/src/lib/alignment.ts` doesn't exist.

- [ ] **Step 3: Implement**

```ts
// frontend/src/lib/alignment.ts
import type { Widget } from '../types/report'

type Layout = Widget['layout']
type LayoutMap = Record<number, Layout>
type Patch = Record<number, Partial<Layout>>

export function alignWidgets(layouts: LayoutMap, mode: 'left' | 'center' | 'right' | 'top' | 'middle' | 'bottom'): Patch {
  const entries = Object.entries(layouts).map(([id, l]) => [Number(id), l] as const)
  const patch: Patch = {}
  if (mode === 'left' || mode === 'center' || mode === 'right') {
    const lefts = entries.map(([, l]) => l.x)
    const rights = entries.map(([, l]) => l.x + l.w)
    const target = mode === 'left' ? Math.min(...lefts) : mode === 'right' ? Math.max(...rights) : Math.round((Math.min(...lefts) + Math.max(...rights)) / 2)
    for (const [id, l] of entries) {
      patch[id] = { x: mode === 'right' ? target - l.w : mode === 'center' ? target - Math.round(l.w / 2) : target }
    }
  } else {
    const tops = entries.map(([, l]) => l.y)
    const bottoms = entries.map(([, l]) => l.y + l.h)
    const target = mode === 'top' ? Math.min(...tops) : mode === 'bottom' ? Math.max(...bottoms) : Math.round((Math.min(...tops) + Math.max(...bottoms)) / 2)
    for (const [id, l] of entries) {
      patch[id] = { y: mode === 'bottom' ? target - l.h : mode === 'middle' ? target - Math.round(l.h / 2) : target }
    }
  }
  return patch
}

export function distributeWidgets(layouts: LayoutMap, axis: 'horizontal' | 'vertical'): Patch {
  const entries = Object.entries(layouts).map(([id, l]) => [Number(id), l] as const)
  const key = axis === 'horizontal' ? 'x' : 'y'
  const sorted = [...entries].sort((a, b) => a[1][key] - b[1][key])
  if (sorted.length < 3) {
    // Nothing to distribute with fewer than 3 widgets — the first/last already anchor the ends.
    return {}
  }
  const first = sorted[0][1][key]
  const last = sorted[sorted.length - 1][1][key]
  const step = (last - first) / (sorted.length - 1)
  const patch: Patch = {}
  sorted.forEach(([id], i) => { patch[id] = { [key]: Math.round(first + step * i) } as Partial<Layout> })
  return patch
}
```

- [ ] **Step 4: Run and confirm it passes.**

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/alignment.ts frontend/src/lib/alignment.test.ts
git commit -m "Add pure Align/Distribute layout math"
```

---

## Task 9: Multi-select + Align/Distribute toolbar

**Files:**
- Modify: `frontend/src/components/report/WidgetRenderer.tsx`
- Test: `frontend/src/components/report/WidgetRenderer.test.tsx`
- Modify: `frontend/src/pages/ReportBuilder.tsx`
- Test: `frontend/src/pages/ReportBuilder.test.tsx`

**Interfaces:**
- Consumes: `alignWidgets`/`distributeWidgets` (Task 8).
- Produces: `WidgetRenderer`'s `onSelect` prop becomes `(e: React.MouseEvent) => void` (was `()
  => void`); new `isMultiSelected?: boolean` prop. `ReportBuilder` gains `multiSelectedIds:
  Set<number>` state and a fully-wired 8-button Home-tab toolbar.

- [ ] **Step 1: Write the failing WidgetRenderer tests**

```tsx
it('renders a distinct outline when isMultiSelected is true, separate from the single-selected outline', async () => {
  vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
  const { container } = renderWidget({ isMultiSelected: true })
  const outer = container.firstElementChild as HTMLElement
  expect(outer.style.outline || outer.style.boxShadow).toBeTruthy()
})

it('passes the click MouseEvent through onSelect so the caller can check e.shiftKey', async () => {
  vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
  const onSelect = vi.fn()
  const { container } = renderWidget({ onSelect })
  fireEvent.click(container.firstElementChild as Element, { shiftKey: true })
  expect(onSelect).toHaveBeenCalled()
  expect(onSelect.mock.calls[0][0].shiftKey).toBe(true)
})
```

- [ ] **Step 2: Run and confirm it fails.**

- [ ] **Step 3: Implement.** In `WidgetRenderer.tsx`: change `onSelect?: () => void` to
  `onSelect?: (e: React.MouseEvent) => void` in `Props`; add `isMultiSelected?: boolean` to
  `Props`; change `onClick={onSelect}` to `onClick={e => onSelect?.(e)}`; add `outline:
  isMultiSelected ? '2px solid var(--success)' : undefined` to the outer container's style object,
  alongside the existing `border`/`boxShadow` selected-state logic.

- [ ] **Step 4: Run and confirm it passes.**

- [ ] **Step 5: Write the failing ReportBuilder test**

```tsx
it('shift+click multi-selects widgets, and Align Left moves them all to the leftmost x', async () => {
  const report = reportWithWidget()
  report.pages[0].widgets.push({ id: 6, page_id: 100, widget_type: 'bar', title: 'Second Widget', config: { dimension: 'region' }, layout: { x: 6, y: 0, w: 6, h: 5 }, created_at: '2026-01-01' } as any)
  vi.mocked(reportsApi.get).mockResolvedValue(report as any)
  vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
  vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
  vi.mocked(reportsApi.updateWidget).mockResolvedValue({} as any)
  renderBuilder()
  await screen.findByTestId('view-strip')

  fireEvent.click(screen.getByText('Sales by Region'), { shiftKey: true })
  fireEvent.click(screen.getByText('Second Widget'), { shiftKey: true })
  fireEvent.click(screen.getByRole('tab', { name: 'Home' }))
  const ribbonContent = within(screen.getByTestId('ribbon-content'))
  fireEvent.click(ribbonContent.getByRole('button', { name: /Align Left/i }))

  expect(reportsApi.updateWidget).toHaveBeenCalledWith(1, 100, 6, { layout: expect.objectContaining({ x: 0 }) })
})
```

- [ ] **Step 6: Run and confirm it fails** — no multi-select state, no alignment toolbar yet.

- [ ] **Step 7: Implement.** In `ReportBuilder.tsx`:
  - Add `const [multiSelectedIds, setMultiSelectedIds] = useState<Set<number>>(new Set())`; clear
    it in the existing `useEffect(() => { setZoom(100) }, [activePage?.id])` (rename/extend that
    effect to also `setMultiSelectedIds(new Set())`).
  - Change each `<WidgetRenderer onSelect={() => setSelectedW(widget)} .../>` call site to:
```tsx
onSelect={(e: React.MouseEvent) => {
  if (e.shiftKey) {
    setMultiSelectedIds(prev => { const next = new Set(prev); next.has(widget.id) ? next.delete(widget.id) : next.add(widget.id); return next })
  } else {
    setSelectedW(widget)
    setMultiSelectedIds(new Set())
  }
}}
isMultiSelected={multiSelectedIds.has(widget.id)}
```
  - Extend the Home-tab `setTabContent('home', ...)` effect from Task 6 (theme picker) to also
    render the alignment toolbar when `multiSelectedIds.size >= 2`:
```tsx
{multiSelectedIds.size >= 2 && (
  <div style={{ display: 'flex', gap: 4, marginLeft: 12, borderLeft: '1px solid var(--border)', paddingLeft: 12 }}>
    {([
      ['Align Left', () => applyAlign('left')], ['Align Center', () => applyAlign('center')], ['Align Right', () => applyAlign('right')],
      ['Align Top', () => applyAlign('top')], ['Align Middle', () => applyAlign('middle')], ['Align Bottom', () => applyAlign('bottom')],
      ['Distribute Horizontally', () => applyDistribute('horizontal')], ['Distribute Vertically', () => applyDistribute('vertical')],
    ] as const).map(([label, fn]) => (
      <button key={label} onClick={fn} style={{ fontSize: 10, padding: '4px 8px', border: '1px solid var(--border)', borderRadius: 6, background: 'var(--surface2)', color: 'var(--text)', cursor: 'pointer' }}>{label}</button>
    ))}
  </div>
)}
```
    (This block joins the existing theme-picker `<div>` as a sibling inside the same
    `setTabContent('home', <>...</>)` call — wrap both in a fragment.) Add `multiSelectedIds` and
    the two handler functions below to that effect's dependency array.
  - Define `applyAlign`/`applyDistribute` (import `alignWidgets`/`distributeWidgets` from
    `../lib/alignment`):
```tsx
const applyAlign = async (mode: Parameters<typeof alignWidgets>[1]) => {
  if (!activePage) return
  const selected = pageWidgets.filter(w => multiSelectedIds.has(w.id))
  const layoutMap = Object.fromEntries(selected.map(w => [w.id, w.layout]))
  const patch = alignWidgets(layoutMap, mode)
  await Promise.all(selected.map(w => reportsApi.updateWidget(reportId, activePage.id, w.id, { layout: { ...w.layout, ...patch[w.id] } })))
  await loadReport()
}
const applyDistribute = async (axis: Parameters<typeof distributeWidgets>[1]) => {
  if (!activePage) return
  const selected = pageWidgets.filter(w => multiSelectedIds.has(w.id))
  const layoutMap = Object.fromEntries(selected.map(w => [w.id, w.layout]))
  const patch = distributeWidgets(layoutMap, axis)
  await Promise.all(selected.map(w => reportsApi.updateWidget(reportId, activePage.id, w.id, { layout: { ...w.layout, ...patch[w.id] } })))
  await loadReport()
}
```

- [ ] **Step 8: Run and confirm it passes. Run the full frontend suite.**

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/report/WidgetRenderer.tsx frontend/src/components/report/WidgetRenderer.test.tsx frontend/src/pages/ReportBuilder.tsx frontend/src/pages/ReportBuilder.test.tsx
git commit -m "Add multi-select and a fully-wired Align/Distribute toolbar"
```

---

## Final Verification

- [ ] **Backend:** `cd backend && python -m pytest tests/ -q` — full suite green (439 passing
  before this plan).
- [ ] **Frontend:** `cd frontend && npx vitest run` — full suite green (86 passing before this
  plan).
- [ ] **Typecheck:** `cd frontend && npx tsc --noEmit` — no new errors.
- [ ] **Manual smoke test:** add an Area/Funnel/Card/Ribbon widget each and confirm they render
  real data; switch a report's theme from the Home tab and confirm bar/pie/heatmap-style widgets
  retint; open the Tab order pane, reorder, and confirm keyboard-Tab in View mode follows it;
  Shift+click two widgets and confirm the alignment toolbar appears and each of the 8 actions
  moves widgets as expected.
- [ ] Refresh the Feature Parity Audit artifact: Visual types gains 4 exists (Area, Funnel, Card,
  Ribbon chart — note Ribbon chart's note should say "approximation, not the flow-connector
  visual"); Formatting & layout controls category moves toward full closure (Align/distribute
  tools, Themes, Tab order pane all Exists).
