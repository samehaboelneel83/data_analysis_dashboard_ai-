# Side Panes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close out the Feature Parity Audit's "Side panes" category — a Slicer widget, a
Selection pane, a Sync slicers pane, and Bookmarks — per the approved spec at
`docs/superpowers/specs/2026-08-16-side-panes-design.md`.

**Architecture:** Extend `CrossFilterContext` to carry multi-value, page-scoped filters (needed by
both the Slicer widget and Sync slicers). Add a new `slicer` widget type that reuses the existing
dimension-only query path. Generalize `ReportBuilder`'s single `showMobileEditor` boolean into a
`rightPanelMode` union so Selection/Sync-slicers/Bookmarks panes share the same right-panel slot
`MobileLayoutEditor` already uses. Bookmarks get a new backend model nested under `Report`
(mirroring `ReportPage`), added directly to the existing `reports.py` router rather than a new
file, since it's the same "resource nested under a report" pattern as pages/widgets.

**Tech Stack:** FastAPI + SQLAlchemy (backend), React + TypeScript + Vitest/Testing Library
(frontend), pytest + httpx (backend tests).

## Global Constraints

- TDD throughout: write the failing test, confirm it fails for the right reason, implement
  minimally, confirm green, run the full suite, commit — per `superpowers:test-driven-development`.
- `Widget.config` and `ReportPage.mobile_layout`-style JSON columns are the established way to
  add new per-widget/per-page state without backend schema changes — use this for `hidden` and
  `syncAllPages` rather than new columns.
- Every backend list/get/create/delete endpoint enforces org-scoping via `check_org()` → 404
  (never 403) on cross-org access, following the existing convention in `reports.py`/`relationships.py`.
- New DB columns: idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` in `_migrate()` inside
  `backend/app/main.py`'s `lifespan` — brand-new tables (`Bookmark`) need no migration statement,
  `Base.metadata.create_all` handles them.
- Bash/PowerShell commands for the frontend must run from `frontend/` explicitly (cwd has
  repeatedly drifted to the repo root mid-session, picking up a stray global `vitest` and
  breaking the jsdom environment) — always prefix `cd frontend &&` (or run from that directory).

---

## Task 1: CrossFilterContext — multi-value, page-scoped filters

**Files:**
- Modify: `frontend/src/components/report/CrossFilterContext.tsx`
- Test: `frontend/src/components/report/CrossFilterContext.test.tsx` (new)

**Interfaces:**
- Produces: `ActiveFilter.value: unknown | unknown[]`, `ActiveFilter.sourcePageId: number`,
  `emitFilter(widgetId, pageId, column, value, label)` (gains a `pageId` param),
  `emitMultiFilter(widgetId, pageId, column, values: unknown[], label)` (new),
  `getFiltersFor(widgetId, currentPageId)` (gains a `currentPageId` param),
  `WidgetInteraction.syncAllPages?: boolean`.

- [ ] **Step 1: Write the failing tests**

```tsx
// frontend/src/components/report/CrossFilterContext.test.tsx
import { describe, it, expect } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { CrossFilterProvider, useCrossFilter } from './CrossFilterContext'

function wrapper({ children }: { children: React.ReactNode }) {
  return <CrossFilterProvider>{children}</CrossFilterProvider>
}

describe('CrossFilterContext multi-value + page scoping', () => {
  it('carries an array value from emitMultiFilter and matches it with the in operator downstream', () => {
    const { result } = renderHook(() => useCrossFilter(), { wrapper })
    act(() => result.current.emitMultiFilter(1, 100, 'region', ['North', 'South'], 'region in (North, South)'))
    expect(result.current.activeFilters[0].value).toEqual(['North', 'South'])
    expect(result.current.activeFilters[0].sourcePageId).toBe(100)
  })

  it('only returns filters emitted on the same page by default', () => {
    const { result } = renderHook(() => useCrossFilter(), { wrapper })
    act(() => result.current.emitFilter(1, 100, 'region', 'North', 'region = North'))
    expect(result.current.getFiltersFor(2, 100)).toHaveLength(1)
    expect(result.current.getFiltersFor(2, 200)).toHaveLength(0)
  })

  it('lets a widget marked syncAllPages reach every page', () => {
    const { result } = renderHook(() => useCrossFilter(), { wrapper })
    act(() => {
      result.current.setInteraction(1, { broadcasts: true, receives: true, syncAllPages: true })
      result.current.emitFilter(1, 100, 'region', 'North', 'region = North')
    })
    expect(result.current.getFiltersFor(2, 200)).toHaveLength(1)
  })
})
```

- [ ] **Step 2: Run and confirm it fails** — `emitFilter`/`getFiltersFor` don't yet accept a page
  id, `emitMultiFilter` doesn't exist.

- [ ] **Step 3: Implement.** In `CrossFilterContext.tsx`:

```ts
export interface ActiveFilter {
  column: string
  value: unknown | unknown[]
  label: string
  sourceWidgetId: number
  sourcePageId: number
}

export interface WidgetInteraction {
  broadcasts: boolean
  receives: boolean
  syncAllPages?: boolean
}
```

`emitFilter(widgetId, pageId, column, value, label)` and the new
`emitMultiFilter(widgetId, pageId, column, values, label)` both stamp `sourcePageId: pageId` on
the stored `ActiveFilter` (share the underlying "replace existing filter for this column from
this source, toggle off on repeat" logic — extract a private `_setFilter(widgetId, pageId,
column, value, label)` both call). `getFiltersFor(widgetId, currentPageId)` becomes:

```ts
const getFiltersFor = useCallback((widgetId: number, currentPageId: number): ActiveFilter[] => {
  if (!(interactions[widgetId]?.receives ?? true)) return []
  return activeFilters.filter(f =>
    f.sourceWidgetId !== widgetId &&
    (f.sourcePageId === currentPageId || interactions[f.sourceWidgetId]?.syncAllPages)
  )
}, [activeFilters, interactions])
```

- [ ] **Step 4: Run and confirm it passes.**

- [ ] **Step 5: Fix call sites.** `WidgetRenderer.tsx`'s `handleClick` currently calls
  `emitFilter(widget.id, col, name, label)` — add `widget.page_id` as the second argument (it's
  already a field on every `Widget`, no new prop needed). Its `getFiltersFor(widget.id)` call
  becomes `getFiltersFor(widget.id, widget.page_id)`. Run the full frontend suite — expect
  `WidgetRenderer.test.tsx` and `ReportBuilder.test.tsx` to still pass unchanged (single-page
  tests, so page-scoping is a no-op for them).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/report/CrossFilterContext.tsx frontend/src/components/report/CrossFilterContext.test.tsx frontend/src/components/report/WidgetRenderer.tsx
git commit -m "Extend cross-filters to carry multi-value, page-scoped filters"
```

---

## Task 2: mergedConfig handles array filter values

**Files:**
- Modify: `frontend/src/components/report/WidgetRenderer.tsx`
- Test: `frontend/src/components/report/WidgetRenderer.test.tsx`

**Interfaces:**
- Consumes: `ActiveFilter.value: unknown | unknown[]` (Task 1).
- Produces: widget query `config.filters` entries use `op: 'in'` when the incoming filter value
  is an array, `op: 'eq'` otherwise — matches the backend's existing `_apply_filters` support for
  both operators (`backend/app/services/widget_data.py`), so no backend change is needed.

- [ ] **Step 1: Write the failing test.** This test predates the Slicer widget (Task 3/4), so it
  injects a multi-value filter directly via `useCrossFilter()`, the same way
  `RibbonContext.test.tsx`'s `Injector` component injects ribbon content:

```tsx
// add near the top of WidgetRenderer.test.tsx, alongside the other imports/helpers
import { useEffect } from 'react'
import { useCrossFilter } from './CrossFilterContext'

function MultiFilterInjector({ widgetId, pageId, column, values }: { widgetId: number; pageId: number; column: string; values: unknown[] }) {
  const { emitMultiFilter } = useCrossFilter()
  useEffect(() => { emitMultiFilter(widgetId, pageId, column, values, `${column} in (...)`) }, [])
  return null
}
```

```tsx
it('builds an "in" filter when an incoming cross-filter carries multiple values', async () => {
  vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
  render(
    <CrossFilterProvider>
      <MultiFilterInjector widgetId={1} pageId={100} column="region" values={['North', 'South']} />
      <WidgetRenderer widget={barWidget({ id: 2 })} datasetId={10} />
    </CrossFilterProvider>
  )

  await waitFor(() => expect(widgetDataApi.query).toHaveBeenCalled())
  const [, config] = vi.mocked(widgetDataApi.query).mock.calls.at(-1)!
  expect((config as any).filters).toContainEqual({ column: 'region', op: 'in', value: ['North', 'South'] })
})
```

- [ ] **Step 2: Run and confirm it fails** — today's `mergedConfig` always emits `op: 'eq'`.

- [ ] **Step 3: Implement.** In `WidgetRenderer.tsx`'s `mergedConfig` `useMemo`:

```ts
const crossFilters = incomingFilters.map(f => ({
  column: f.column,
  op: Array.isArray(f.value) ? 'in' : 'eq',
  value: f.value,
}))
```

- [ ] **Step 4: Run and confirm it passes.**

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/report/WidgetRenderer.tsx frontend/src/components/report/WidgetRenderer.test.tsx
git commit -m "Support multi-value cross-filters as an 'in' query filter"
```

---

## Task 3: Slicer widget type registration

**Files:**
- Modify: `frontend/src/types/report.ts`

**Interfaces:**
- Produces: `WidgetType` includes `'slicer'`; `WIDGET_CATALOG` gains a `slicer` entry (category
  `'Controls'`); `ROLE_SPECS.slicer = [{ role: 'category', label: 'Field to filter by', required: true }]`.

- [ ] **Step 1: Implement** (pure data/type addition, exercised by Task 4's tests below — no
  standalone test needed for a type-only change, consistent with how `page_size`/`mobile_layout`
  were added to `ReportPage` earlier this session):

```ts
export type WidgetType =
  | 'bar' | 'line' | 'pie' | 'donut' | 'scatter' | 'treemap' | 'step' | 'dot_plot' | 'needle'
  | 'histogram' | 'butterfly' | 'dual_axis_bar' | 'dual_axis_line' | 'dual_axis_bar_line' | 'dual_axis_time_series' | 'comparative_time_series' | 'numeric_series'
  | 'bubble' | 'bubble_change' | 'correlation_matrix' | 'heatmap' | 'parallel_coordinates' | 'box_plot' | 'waterfall' | 'gauge' | 'schedule' | 'vector_plot' | 'word_cloud'
  | 'kpi' | 'table' | 'crosstab' | 'list' | 'text' | 'button' | 'slicer'
```

Add to `WIDGET_CATALOG` (in the `'Controls'` group, after `button`):
```ts
{ type: 'slicer' as WidgetType, label: 'Slicer', category: 'Controls', icon: '☑', defaultW: 3, defaultH: 5 },
```

Add to `ROLE_SPECS`:
```ts
slicer: [{ role: 'category', label: 'Field to filter by', required: true }],
```

- [ ] **Step 2: Run the full frontend suite** — confirm nothing that iterates `WIDGET_CATALOG` or
  `ROLE_SPECS` (e.g. the Insert-tab catalog render in `ReportBuilder.tsx`) breaks by gaining an
  extra entry.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/report.ts
git commit -m "Register the slicer widget type"
```

---

## Task 4: Slicer widget rendering

**Files:**
- Modify: `frontend/src/components/report/WidgetRenderer.tsx`
- Test: `frontend/src/components/report/WidgetRenderer.test.tsx`

**Interfaces:**
- Consumes: `emitMultiFilter` (Task 1), `WIDGET_CATALOG`/`ROLE_SPECS.slicer` (Task 3).
- Produces: a `slicer`-type widget renders a checkbox list of `data.rows` (each `{ name, value }`
  — the existing dimension-only query shape, `value` being the row count), checking/unchecking
  calls `emitMultiFilter` with the full set of currently-checked names.

- [ ] **Step 1: Write the failing test.** Render the slicer alongside a `FilterReader` component
  (same "read context state into the DOM for assertions" trick as `RibbonContext.test.tsx`'s
  `Reader`) so the emitted filter is directly observable:

```tsx
function FilterReader() {
  const { activeFilters } = useCrossFilter()
  return <div data-testid="filters">{JSON.stringify(activeFilters.map(f => ({ column: f.column, value: f.value })))}</div>
}

it('renders a slicer as a checkbox list and emits the checked set as a multi-value filter', async () => {
  vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [{ name: 'North', value: 3 }, { name: 'South', value: 5 }], sampled: false })
  render(
    <CrossFilterProvider>
      <WidgetRenderer widget={barWidget({ id: 9, widget_type: 'slicer', config: { dimension: 'region' } })} datasetId={10} />
      <FilterReader />
    </CrossFilterProvider>
  )

  expect(await screen.findByText('North')).toBeInTheDocument()
  expect(screen.getByText('South')).toBeInTheDocument()

  fireEvent.click(screen.getByRole('checkbox', { name: /North/i }))
  fireEvent.click(screen.getByRole('checkbox', { name: /South/i }))

  expect(screen.getByTestId('filters')).toHaveTextContent(JSON.stringify([{ column: 'region', value: ['North', 'South'] }]))
})
```

- [ ] **Step 2: Run and confirm it fails** — `wt === 'slicer'` has no branch in `WidgetBody` yet.

- [ ] **Step 3: Implement.** In `WidgetRenderer.tsx`, add local state
  `const [checked, setChecked] = useState<Set<unknown>>(new Set())` (reset when `widget.id`
  changes, same pattern as `localSelected`), a handler:

```ts
const handleToggleSlicerValue = useCallback((value: unknown) => {
  setChecked(prev => {
    const next = new Set(prev)
    next.has(value) ? next.delete(value) : next.add(value)
    const cfg = widget.config as any
    const col = cfg.dimension
    if (col) emitMultiFilter(widget.id, widget.page_id, col, Array.from(next), `${col} in (${Array.from(next).join(', ')})`)
    return next
  })
}, [widget.id, widget.page_id, widget.config, emitMultiFilter])
```

Pass `checked`/`onToggleSlicerValue={handleToggleSlicerValue}` into `WidgetBody`, add a
`wt === 'slicer'` branch there rendering `data.rows.map(row => <label><input type="checkbox"
checked={checked.has(row.name)} onChange={() => onToggleSlicerValue(row.name)} />{row.name}
<span>{row.value}</span></label>)`.

- [ ] **Step 4: Run and confirm it passes.**

- [ ] **Step 5: Run the full frontend suite, commit**

```bash
git add frontend/src/components/report/WidgetRenderer.tsx frontend/src/components/report/WidgetRenderer.test.tsx
git commit -m "Render the slicer widget as a multi-select checkbox list"
```

---

## Task 5: Selection pane

**Files:**
- Create: `frontend/src/components/report/SelectionPane.tsx`
- Test: `frontend/src/components/report/SelectionPane.test.tsx`

**Interfaces:**
- Produces: `SelectionPane({ widgets, onUpdate }: { widgets: Widget[]; onUpdate: (widgetId:
  number, config: Record<string, unknown>) => void })` — a list of widgets with a visibility
  toggle each, writing `{ ...widget.config, hidden: !hidden }` via `onUpdate`.

- [ ] **Step 1: Write the failing test** (follow `MobileLayoutEditor.test.tsx`'s structure):

```tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import SelectionPane from './SelectionPane'
import type { Widget } from '../../types/report'

function widget(id: number, title: string, hidden = false): Widget {
  return { id, page_id: 100, widget_type: 'bar', title, config: { hidden }, layout: { x: 0, y: 0, w: 6, h: 5 }, created_at: '2026-01-01' }
}

describe('SelectionPane', () => {
  it('lists widgets with a visibility toggle', () => {
    render(<SelectionPane widgets={[widget(1, 'Sales'), widget(2, 'Costs')]} onUpdate={vi.fn()} />)
    expect(screen.getByText('Sales')).toBeInTheDocument()
    expect(screen.getByText('Costs')).toBeInTheDocument()
  })

  it('toggling a widget calls onUpdate with the flipped hidden flag', () => {
    const onUpdate = vi.fn()
    render(<SelectionPane widgets={[widget(1, 'Sales', false)]} onUpdate={onUpdate} />)
    fireEvent.click(screen.getByRole('button', { name: /Sales/i }))
    expect(onUpdate).toHaveBeenCalledWith(1, { hidden: true })
  })
})
```

- [ ] **Step 2: Run and confirm it fails** — module doesn't exist.

- [ ] **Step 3: Implement**

```tsx
// frontend/src/components/report/SelectionPane.tsx
import type { Widget } from '../../types/report'

export default function SelectionPane({ widgets, onUpdate }: {
  widgets: Widget[]
  onUpdate: (widgetId: number, config: Record<string, unknown>) => void
}) {
  return (
    <div style={{ padding: '14px 14px 0' }}>
      <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 8 }}>
        Selection
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {widgets.map(w => {
          const hidden = !!(w.config as any).hidden
          return (
            <button key={w.id} aria-label={`Toggle visibility: ${w.title}`}
              onClick={() => onUpdate(w.id, { ...w.config, hidden: !hidden })}
              style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 7px',
                background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 6,
                cursor: 'pointer', textAlign: 'left', opacity: hidden ? 0.5 : 1 }}>
              <span>{hidden ? '🚫' : '👁'}</span>
              <span style={{ flex: 1, fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{w.title}</span>
            </button>
          )
        })}
        {widgets.length === 0 && <span style={{ fontSize: 12, color: 'var(--muted)' }}>No widgets on this page.</span>}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run and confirm it passes.**

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/report/SelectionPane.tsx frontend/src/components/report/SelectionPane.test.tsx
git commit -m "Add Selection pane for per-widget visibility"
```

---

## Task 6: Wire Selection pane + widget-hidden filtering into ReportBuilder

**Files:**
- Modify: `frontend/src/pages/ReportBuilder.tsx`
- Test: `frontend/src/pages/ReportBuilder.test.tsx`

**Interfaces:**
- Consumes: `SelectionPane` (Task 5).
- Produces: view-strip gains a "👁 Selection" toggle; `rightPanelMode: 'default' | 'mobile' |
  'selection' | 'sync' | 'bookmarks'` state replaces the current `showMobileEditor` boolean;
  `!editMode` rendering (both the desktop grid and the mobile stack) skips widgets where
  `widget.config.hidden` is true; `editMode` rendering still shows them at reduced opacity.

- [ ] **Step 1: Write the failing test**

```tsx
it('hides a widget marked hidden in View mode but still shows it dimmed in Edit mode', async () => {
  const report = reportWithWidget()
  ;(report.pages[0].widgets[0] as any).config = { dimension: 'region', hidden: true }
  vi.mocked(reportsApi.get).mockResolvedValue(report as any)
  vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
  renderBuilder()
  await screen.findByTestId('view-strip')

  expect(screen.getByText('Sales by Region')).toBeInTheDocument() // dimmed but present, editMode defaults true

  fireEvent.click(screen.getByRole('button', { name: /Edit mode/i })) // switch to View mode
  expect(screen.queryByText('Sales by Region')).not.toBeInTheDocument()
})

it('shows the Selection pane in the right panel when toggled', async () => {
  vi.mocked(reportsApi.get).mockResolvedValue(reportWithWidget() as any)
  vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
  renderBuilder()
  await screen.findByTestId('view-strip')
  fireEvent.click(screen.getByRole('button', { name: /^Selection/i }))
  expect(screen.getByText('Sales by Region')).toBeInTheDocument() // now inside SelectionPane's list
})
```

- [ ] **Step 2: Run and confirm it fails.**

- [ ] **Step 3: Implement.** Replace `const [showMobileEditor, setShowMobileEditor] =
  useState(false)` with:

```ts
type RightPanelMode = 'default' | 'mobile' | 'selection' | 'sync' | 'bookmarks'
const [rightPanelMode, setRightPanelMode] = useState<RightPanelMode>('default')
```

Update the "📱 Mobile layout" button to toggle `rightPanelMode` between `'mobile'`/`'default'`;
add a "👁 Selection" button toggling `'selection'`/`'default'` next to it. In the right-panel
render block, branch on `rightPanelMode`:
```tsx
{rightPanelMode === 'mobile' && activePage && <MobileLayoutEditor page={activePage} widgets={pageWidgets} onUpdate={updatePageProps} />}
{rightPanelMode === 'selection' && <SelectionPane widgets={pageWidgets} onUpdate={(id, config) => reportsApi.updateWidget(reportId, activePage!.id, id, { config }).then(loadReport)} />}
{rightPanelMode === 'default' && ( /* existing selectedW ? WidgetConfigPanel : PagePropertiesPanel block */ )}
```
In both the desktop grid `.map(widget => ...)` and the mobile-stack widget list, filter
`pageWidgets` (or the stacked-order array) with `.filter(w => editMode || !(w.config as
any).hidden)` before mapping, and pass `opacity: (w.config as any).hidden ? 0.5 : 1` into the
widget's wrapper style when `editMode && (w.config as any).hidden`.

- [ ] **Step 4: Run and confirm it passes.**

- [ ] **Step 5: Run the full frontend suite, commit**

```bash
git add frontend/src/pages/ReportBuilder.tsx frontend/src/pages/ReportBuilder.test.tsx
git commit -m "Wire the Selection pane into ReportBuilder; hide widgets marked hidden in View mode"
```

---

## Task 7: Sync slicers pane

**Files:**
- Create: `frontend/src/components/report/SyncSlicersPane.tsx`
- Test: `frontend/src/components/report/SyncSlicersPane.test.tsx`

**Interfaces:**
- Produces: `SyncSlicersPane({ pages, interactions, onToggleSync }: { pages: ReportPage[];
  interactions: Record<number, WidgetInteraction>; onToggleSync: (widgetId: number, sync:
  boolean) => void })` — lists every `widget_type === 'slicer'` widget across all pages, grouped
  by page name, with a toggle.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/report/SyncSlicersPane.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import SyncSlicersPane from './SyncSlicersPane'
import type { ReportPage } from '../../types/report'

function page(id: number, name: string, widgets: ReportPage['widgets']): ReportPage {
  return { id, report_id: 1, name, page_type: 'normal', position: 0, widgets, created_at: '2026-01-01', page_size: '16:9' }
}

const SLICER = { id: 9, page_id: 1, widget_type: 'slicer' as const, title: 'Region filter', config: {}, layout: { x: 0, y: 0, w: 3, h: 5 }, created_at: '2026-01-01' }

describe('SyncSlicersPane', () => {
  it('lists slicer widgets across all pages, grouped by page', () => {
    render(<SyncSlicersPane pages={[page(1, 'Overview', [SLICER])]} interactions={{}} onToggleSync={vi.fn()} />)
    expect(screen.getByText('Overview')).toBeInTheDocument()
    expect(screen.getByText('Region filter')).toBeInTheDocument()
  })

  it('toggling calls onToggleSync with the new sync state', () => {
    const onToggleSync = vi.fn()
    render(<SyncSlicersPane pages={[page(1, 'Overview', [SLICER])]} interactions={{}} onToggleSync={onToggleSync} />)
    fireEvent.click(screen.getByRole('button', { name: /All pages/i }))
    expect(onToggleSync).toHaveBeenCalledWith(9, true)
  })
})
```

- [ ] **Step 2: Run and confirm it fails.**

- [ ] **Step 3: Implement**

```tsx
// frontend/src/components/report/SyncSlicersPane.tsx
import type { ReportPage } from '../../types/report'
import type { WidgetInteraction } from './CrossFilterContext'

export default function SyncSlicersPane({ pages, interactions, onToggleSync }: {
  pages: ReportPage[]
  interactions: Record<number, WidgetInteraction>
  onToggleSync: (widgetId: number, sync: boolean) => void
}) {
  const pagesWithSlicers = pages
    .map(p => ({ page: p, slicers: p.widgets.filter(w => w.widget_type === 'slicer') }))
    .filter(g => g.slicers.length > 0)

  return (
    <div style={{ padding: '14px 14px 0' }}>
      <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 8 }}>
        Sync slicers
      </div>
      {pagesWithSlicers.length === 0 && <span style={{ fontSize: 12, color: 'var(--muted)' }}>No slicers in this report yet.</span>}
      {pagesWithSlicers.map(({ page, slicers }) => (
        <div key={page.id} style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 4 }}>{page.name}</div>
          {slicers.map(s => {
            const synced = !!interactions[s.id]?.syncAllPages
            return (
              <div key={s.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 7px', fontSize: 12 }}>
                <span style={{ flex: 1 }}>{s.title}</span>
                <button onClick={() => onToggleSync(s.id, !synced)}
                  style={{ fontSize: 10, padding: '3px 8px', borderRadius: 99, border: '1px solid var(--border)',
                    background: synced ? 'var(--accent)' : 'var(--surface2)', color: synced ? '#fff' : 'var(--muted)', cursor: 'pointer' }}>
                  {synced ? 'All pages' : 'This page only'}
                </button>
              </div>
            )
          })}
        </div>
      ))}
    </div>
  )
}
```

- [ ] **Step 4: Run and confirm it passes.**

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/report/SyncSlicersPane.tsx frontend/src/components/report/SyncSlicersPane.test.tsx
git commit -m "Add Sync slicers pane"
```

---

## Task 8: Wire Sync slicers pane into ReportBuilder

**Files:**
- Modify: `frontend/src/pages/ReportBuilder.tsx`
- Test: `frontend/src/pages/ReportBuilder.test.tsx`

**Interfaces:**
- Consumes: `SyncSlicersPane` (Task 7), `useCrossFilter().interactions`/`setInteraction` (Task 1).

- [ ] **Step 1: Write the failing test**

```tsx
it('toggling a slicer to All pages calls setInteraction with syncAllPages true', async () => {
  const report = reportWithWidget()
  report.pages[0].widgets = [{ id: 9, page_id: 100, widget_type: 'slicer', title: 'Region filter', config: { dimension: 'region' }, layout: { x: 0, y: 0, w: 3, h: 5 }, created_at: '2026-01-01' }] as any
  vi.mocked(reportsApi.get).mockResolvedValue(report as any)
  vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
  vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
  renderBuilder()
  await screen.findByTestId('view-strip')

  fireEvent.click(screen.getByRole('button', { name: /^Sync slicers/i }))
  fireEvent.click(await screen.findByRole('button', { name: /This page only/i }))
  expect(screen.getByRole('button', { name: /All pages/i })).toBeInTheDocument()
})
```

- [ ] **Step 2: Run and confirm it fails.**

- [ ] **Step 3: Implement.** Add a "🔗 Sync slicers" view-strip button toggling
  `rightPanelMode` to `'sync'`/`'default'`. Render `{rightPanelMode === 'sync' && <SyncSlicersPane
  pages={report.pages} interactions={interactions} onToggleSync={(id, sync) =>
  setInteraction(id, { ...(interactions[id] ?? { broadcasts: true, receives: true }),
  syncAllPages: sync })} />}` — `interactions`/`setInteraction` come from
  `useCrossFilter()`, already called once in this file's `CrossFilterProvider`-wrapped tree (note:
  `useCrossFilter` must be called from a component inside `CrossFilterProvider`; if
  `rightPanelMode === 'sync'` needs it above the provider, lift the pane inside the existing
  `<CrossFilterProvider>` block alongside the canvas).

- [ ] **Step 4: Run and confirm it passes.**

- [ ] **Step 5: Run the full frontend suite, commit**

```bash
git add frontend/src/pages/ReportBuilder.tsx frontend/src/pages/ReportBuilder.test.tsx
git commit -m "Wire the Sync slicers pane into ReportBuilder"
```

---

## Task 9: Bookmark model + migration + schemas

**Files:**
- Modify: `backend/app/models/models.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/schemas/schemas.py`
- Test: `backend/tests/test_bookmark_model.py`

**Interfaces:**
- Produces: `Bookmark(id, report_id, name, position, state: JSON, created_at)`;
  `BookmarkCreate(name: str, state: dict)`; `BookmarkOut(id, report_id, name, position, state, created_at)`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_bookmark_model.py
from app.models.models import Report, Bookmark


async def test_bookmark_persists_state_json(db_session):
    report = Report(name="R")
    db_session.add(report)
    await db_session.flush()
    bm = Bookmark(report_id=report.id, name="Q1 view", position=0,
                   state={"pageId": 1, "activeFilters": [], "promptValues": {}, "hiddenWidgetIds": []})
    db_session.add(bm)
    await db_session.commit()
    await db_session.refresh(bm)

    assert bm.state["pageId"] == 1
    assert bm.name == "Q1 view"
```

- [ ] **Step 2: Run and confirm it fails** — `Bookmark` doesn't exist.

- [ ] **Step 3: Implement.** In `models.py`, after the `Relationship` class:

```python
class Bookmark(Base):
    __tablename__ = "bookmarks"
    id         = Column(Integer, primary_key=True)
    report_id  = Column(Integer, ForeignKey("reports.id", ondelete="CASCADE"), nullable=False)
    name       = Column(String(255), nullable=False)
    position   = Column(Integer, nullable=False, default=0)
    state      = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    report     = relationship("Report", back_populates="bookmarks")
```

Add `bookmarks = relationship("Bookmark", back_populates="report", cascade="all, delete-orphan", order_by="Bookmark.position")`
to the `Report` class (alongside its existing `pages` relationship). No `_migrate()` entry needed
— `Bookmark` is a brand-new table, created by `Base.metadata.create_all`.

In `schemas.py`:
```python
class BookmarkCreate(BaseModel):
    name: str
    position: int = 0
    state: dict

class BookmarkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    report_id: int
    name: str
    position: int
    state: dict
    created_at: datetime
```

- [ ] **Step 4: Run and confirm it passes.**

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/models.py backend/app/schemas/schemas.py backend/tests/test_bookmark_model.py
git commit -m "Add Bookmark model for saved report state"
```

---

## Task 10: Bookmark CRUD router + org-scoping tests

**Files:**
- Modify: `backend/app/routers/reports.py`
- Test: `backend/tests/test_bookmarks_org_scoping.py`

**Interfaces:**
- Produces: `GET /reports/{report_id}/bookmarks`, `POST /reports/{report_id}/bookmarks`,
  `DELETE /reports/{report_id}/bookmarks/{bookmark_id}`.

- [ ] **Step 1: Write the failing tests** (mirror `test_relationships_org_scoping.py`'s fixtures
  — `client`, `db_session`, `two_orgs`, `auth_headers` — and `test_reports_org_scoping.py`'s
  `_seed_report` helper for creating an org-owned report):

```python
# backend/tests/test_bookmarks_org_scoping.py
from app.models.models import Report, Bookmark


async def _seed_report(db_session, org_id, name="Test Report"):
    r = Report(name=name, org_id=org_id)
    db_session.add(r)
    await db_session.commit()
    await db_session.refresh(r)
    return r


async def test_create_and_list_bookmark(client, db_session, two_orgs, auth_headers):
    org_id = two_orgs["a"]["org"].id
    report = await _seed_report(db_session, org_id)

    resp = await client.post(f"/api/v1/reports/{report.id}/bookmarks",
        json={"name": "Q1 view", "position": 0,
              "state": {"pageId": 1, "activeFilters": [], "promptValues": {}, "hiddenWidgetIds": []}},
        headers=auth_headers["a"])
    assert resp.status_code == 200

    resp = await client.get(f"/api/v1/reports/{report.id}/bookmarks", headers=auth_headers["a"])
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["name"] == "Q1 view"


async def test_bookmark_endpoints_cross_org_report_404(client, db_session, two_orgs, auth_headers):
    org_a_report = await _seed_report(db_session, two_orgs["a"]["org"].id)

    resp = await client.get(f"/api/v1/reports/{org_a_report.id}/bookmarks", headers=auth_headers["b"])
    assert resp.status_code == 404

    resp = await client.post(f"/api/v1/reports/{org_a_report.id}/bookmarks",
        json={"name": "X", "position": 0, "state": {}}, headers=auth_headers["b"])
    assert resp.status_code == 404


async def test_delete_bookmark_cross_org_404(client, db_session, two_orgs, auth_headers):
    org_id = two_orgs["b"]["org"].id
    report = await _seed_report(db_session, org_id)
    bm = Bookmark(report_id=report.id, name="Q1 view", position=0, state={})
    db_session.add(bm)
    await db_session.commit()
    await db_session.refresh(bm)

    resp = await client.delete(f"/api/v1/reports/{report.id}/bookmarks/{bm.id}", headers=auth_headers["a"])
    assert resp.status_code == 404
```

- [ ] **Step 2: Run and confirm it fails** — 404, no such route.

- [ ] **Step 3: Implement.** In `reports.py`, alongside the existing pages/widgets sections:

```python
from ..models.models import Bookmark
from ..schemas.schemas import BookmarkCreate, BookmarkOut

@router.get("/{report_id}/bookmarks", response_model=list[BookmarkOut])
async def list_bookmarks(report_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    result = await db.execute(select(Bookmark).where(Bookmark.report_id == report_id).order_by(Bookmark.position))
    return result.scalars().all()


@router.post("/{report_id}/bookmarks", response_model=BookmarkOut)
async def create_bookmark(report_id: int, body: BookmarkCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    bm = Bookmark(report_id=report_id, **body.model_dump())
    db.add(bm)
    await db.commit()
    await db.refresh(bm)
    return bm


@router.delete("/{report_id}/bookmarks/{bookmark_id}", status_code=204)
async def delete_bookmark(report_id: int, bookmark_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    report = await db.get(Report, report_id)
    check_org(report, current_user, "Report not found")
    result = await db.execute(select(Bookmark).where(Bookmark.id == bookmark_id, Bookmark.report_id == report_id))
    bm = result.scalar_one_or_none()
    if not bm:
        raise HTTPException(404, "Bookmark not found")
    await db.delete(bm)
    await db.commit()
```

- [ ] **Step 4: Run and confirm it passes.**

- [ ] **Step 5: Run the full backend suite, commit**

```bash
git add backend/app/routers/reports.py backend/tests/test_bookmarks_org_scoping.py
git commit -m "Add Bookmark CRUD endpoints nested under reports"
```

---

## Task 11: Frontend Bookmark type + reportsApi methods

**Files:**
- Modify: `frontend/src/types/report.ts`
- Modify: `frontend/src/services/api.ts`

**Interfaces:**
- Produces: `Bookmark` interface; `reportsApi.listBookmarks(rid)`,
  `reportsApi.addBookmark(rid, data)`, `reportsApi.deleteBookmark(rid, bid)`.

- [ ] **Step 1: Implement** (pure type/API-client addition, exercised by Task 12's tests — same
  no-standalone-test rationale as Task 3):

```ts
// types/report.ts
export interface BookmarkState {
  pageId: number
  activeFilters: { column: string; value: unknown; label: string; sourceWidgetId: number; sourcePageId: number }[]
  promptValues: Record<number, string>
  hiddenWidgetIds: number[]
}

export interface Bookmark {
  id: number
  report_id: number
  name: string
  position: number
  state: BookmarkState
  created_at: string
}
```

```ts
// services/api.ts, added to reportsApi
listBookmarks: (rid: number) => api.get<Bookmark[]>(`/reports/${rid}/bookmarks`).then(r => r.data),
addBookmark:   (rid: number, data: { name: string; position: number; state: BookmarkState }) =>
  api.post<Bookmark>(`/reports/${rid}/bookmarks`, data).then(r => r.data),
deleteBookmark:(rid: number, bid: number) => api.delete(`/reports/${rid}/bookmarks/${bid}`),
```

(Import `Bookmark`/`BookmarkState` from `../types/report` into `api.ts`.)

- [ ] **Step 2: Run the full frontend suite** — confirm the `vi.mock('../services/api', ...)`
  blocks in existing test files don't need updating yet (they will in Task 12, once something
  actually calls these methods).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/report.ts frontend/src/services/api.ts
git commit -m "Add Bookmark type and reportsApi bookmark methods"
```

---

## Task 12: BookmarksPane — list + capture

**Files:**
- Create: `frontend/src/components/report/BookmarksPane.tsx`
- Test: `frontend/src/components/report/BookmarksPane.test.tsx`

**Interfaces:**
- Produces: `BookmarksPane({ reportId, bookmarks, onCaptured, onApply, onDeleted }: { reportId:
  number; bookmarks: Bookmark[]; onCaptured: (b: Bookmark) => void; onApply: (b: Bookmark) =>
  void; onDeleted: (id: number) => void })` — "+ Add bookmark" calls `reportsApi.addBookmark`
  with a state snapshot supplied by the parent (see Task 13), then `onCaptured`; clicking a row
  calls `onApply(bookmark)`; a delete button calls `reportsApi.deleteBookmark` then `onDeleted`.

  To keep this component decoupled from `ReportBuilder`'s state, it does **not** compute the
  snapshot itself — it receives a `captureState: () => BookmarkState` prop and calls that when
  "+ Add" is clicked, matching the same "dumb component, parent supplies the callback" shape as
  `MobileLayoutEditor`.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/report/BookmarksPane.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import BookmarksPane from './BookmarksPane'
import { reportsApi } from '../../services/api'

vi.mock('../../services/api', () => ({
  reportsApi: { addBookmark: vi.fn(), deleteBookmark: vi.fn() },
}))

const BM = { id: 1, report_id: 1, name: 'Q1 view', position: 0,
  state: { pageId: 100, activeFilters: [], promptValues: {}, hiddenWidgetIds: [] }, created_at: '2026-01-01' }

describe('BookmarksPane', () => {
  it('lists saved bookmarks and applies one on click', () => {
    const onApply = vi.fn()
    render(<BookmarksPane reportId={1} bookmarks={[BM]} captureState={() => BM.state}
      onCaptured={vi.fn()} onApply={onApply} onDeleted={vi.fn()} />)
    fireEvent.click(screen.getByText('Q1 view'))
    expect(onApply).toHaveBeenCalledWith(BM)
  })

  it('captures and saves a new bookmark', async () => {
    vi.mocked(reportsApi.addBookmark).mockResolvedValue({ ...BM, id: 2, name: 'New view' } as any)
    const onCaptured = vi.fn()
    render(<BookmarksPane reportId={1} bookmarks={[]} captureState={() => BM.state}
      onCaptured={onCaptured} onApply={vi.fn()} onDeleted={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /Add bookmark/i }))
    const input = await screen.findByPlaceholderText(/bookmark name/i)
    fireEvent.change(input, { target: { value: 'New view' } })
    fireEvent.click(screen.getByRole('button', { name: /Save/i }))
    await waitFor(() => expect(reportsApi.addBookmark).toHaveBeenCalledWith(1, { name: 'New view', position: 0, state: BM.state }))
    expect(onCaptured).toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run and confirm it fails.**

- [ ] **Step 3: Implement**

```tsx
// frontend/src/components/report/BookmarksPane.tsx
import { useState } from 'react'
import { reportsApi } from '../../services/api'
import type { Bookmark, BookmarkState } from '../../types/report'

export default function BookmarksPane({ reportId, bookmarks, captureState, onCaptured, onApply, onDeleted }: {
  reportId: number
  bookmarks: Bookmark[]
  captureState: () => BookmarkState
  onCaptured: (b: Bookmark) => void
  onApply: (b: Bookmark) => void
  onDeleted: (id: number) => void
}) {
  const [naming, setNaming] = useState(false)
  const [name, setName] = useState('')

  const save = async () => {
    if (!name.trim()) return
    const bm = await reportsApi.addBookmark(reportId, { name, position: bookmarks.length, state: captureState() })
    onCaptured(bm)
    setNaming(false)
    setName('')
  }

  return (
    <div style={{ padding: '14px 14px 0' }}>
      <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 8 }}>
        Bookmarks
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 10 }}>
        {bookmarks.map(b => (
          <div key={b.id} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <button onClick={() => onApply(b)} style={{ flex: 1, textAlign: 'left', padding: '5px 7px',
              background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 6,
              cursor: 'pointer', fontSize: 12 }}>
              {b.name}
            </button>
            <button onClick={() => reportsApi.deleteBookmark(reportId, b.id).then(() => onDeleted(b.id))}
              style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer' }}>×</button>
          </div>
        ))}
      </div>
      {naming ? (
        <div style={{ display: 'flex', gap: 6 }}>
          <input value={name} onChange={e => setName(e.target.value)} placeholder="Bookmark name…" style={{ flex: 1, fontSize: 12 }} autoFocus />
          <button className="btn btn-primary btn-sm" onClick={save}>Save</button>
        </div>
      ) : (
        <button className="btn btn-ghost btn-sm" onClick={() => setNaming(true)}>+ Add bookmark</button>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run and confirm it passes.**

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/report/BookmarksPane.tsx frontend/src/components/report/BookmarksPane.test.tsx
git commit -m "Add Bookmarks pane: list, capture, delete"
```

---

## Task 13: Wire Bookmarks into ReportBuilder — capture and restore

**Files:**
- Modify: `frontend/src/pages/ReportBuilder.tsx`
- Test: `frontend/src/pages/ReportBuilder.test.tsx`

**Interfaces:**
- Consumes: `BookmarksPane` (Task 12), `reportsApi.listBookmarks` (Task 11),
  `useCrossFilter().activeFilters/clearAllFilters/emitFilter/emitMultiFilter` (Task 1).

- [ ] **Step 1: Write the failing test**

```tsx
it('applying a bookmark switches page, restores prompt values, and restores hidden widgets', async () => {
  const report = reportWithWidget()
  const detailWidget = { id: 20, page_id: 200, widget_type: 'bar', title: 'Detail Chart', config: { dimension: 'region' }, layout: { x: 0, y: 0, w: 6, h: 5 }, created_at: '2026-01-01' }
  report.pages.push({ id: 200, report_id: 1, name: 'Details', page_type: 'normal', position: 1,
    prompt_column: 'region', prompt_label: 'Region', widgets: [detailWidget], created_at: '2026-01-01' } as any)
  vi.mocked(reportsApi.get).mockResolvedValue(report as any)
  vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
  vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
  vi.mocked(reportsApi.updateWidget).mockResolvedValue({} as any)
  vi.mocked(reportsApi.listBookmarks).mockResolvedValue([{
    id: 1, report_id: 1, name: 'Q1 view', position: 0,
    state: { pageId: 200, activeFilters: [], promptValues: { 200: 'North' }, hiddenWidgetIds: [20] },
    created_at: '2026-01-01',
  }] as any)
  renderBuilder()
  await screen.findByTestId('view-strip')

  fireEvent.click(screen.getByRole('button', { name: /^Bookmarks/i }))
  fireEvent.click(await screen.findByText('Q1 view'))

  const promptInput = await screen.findByPlaceholderText('Enter region...')
  expect(promptInput).toHaveValue('North')
  await waitFor(() => expect(reportsApi.updateWidget).toHaveBeenCalledWith(
    1, 200, 20, { config: expect.objectContaining({ hidden: true }) }
  ))
})
```

- [ ] **Step 2: Run and confirm it fails.**

- [ ] **Step 3: Implement.**
  - Load bookmarks once the report loads: `const [bookmarks, setBookmarks] =
    useState<Bookmark[]>([])`, in `loadReport` (or a sibling effect keyed on `reportId`) call
    `reportsApi.listBookmarks(reportId).then(setBookmarks)`.
  - A "🔖 Bookmarks" view-strip button toggling `rightPanelMode` to `'bookmarks'`/`'default'`.
  - `captureState = (): BookmarkState => ({ pageId: activePage!.id, activeFilters, promptValues,
    hiddenWidgetIds: pageWidgets.filter(w => (w.config as any).hidden).map(w => w.id) })` —
    `activeFilters` comes from `useCrossFilter()`.
  - `applyBookmark = async (b: Bookmark) => { const target = report.pages.find(p => p.id ===
    b.state.pageId); if (!target) return; setActivePage(target); setPromptValues(p => ({ ...p,
    ...b.state.promptValues })); clearAllFilters(); b.state.activeFilters.forEach(f =>
    Array.isArray(f.value) ? emitMultiFilter(f.sourceWidgetId, f.sourcePageId, f.column, f.value,
    f.label) : emitFilter(f.sourceWidgetId, f.sourcePageId, f.column, f.value, f.label));
    const hiddenSet = new Set(b.state.hiddenWidgetIds); const toFix = target.widgets.filter(w =>
    !!(w.config as any).hidden !== hiddenSet.has(w.id)); await Promise.all(toFix.map(w =>
    reportsApi.updateWidget(reportId, target.id, w.id, { config: { ...w.config, hidden:
    hiddenSet.has(w.id) } }))); if (toFix.length > 0) await loadReport(); }` — restores each
    widget's hidden flag on the target page to match the bookmark's `hiddenWidgetIds`, reusing
    the same `config` JSON key Task 6 established.
  - Render `{rightPanelMode === 'bookmarks' && <BookmarksPane reportId={reportId}
    bookmarks={bookmarks} captureState={captureState} onCaptured={b => setBookmarks(p =>
    [...p, b])} onApply={applyBookmark} onDeleted={id => setBookmarks(p => p.filter(b => b.id !==
    id))} />}` inside the `CrossFilterProvider` block (needs `activeFilters`/`emitFilter`/etc.).

- [ ] **Step 4: Run and confirm it passes.**

- [ ] **Step 5: Run the full frontend suite, commit**

```bash
git add frontend/src/pages/ReportBuilder.tsx frontend/src/pages/ReportBuilder.test.tsx
git commit -m "Wire Bookmarks into ReportBuilder: capture and restore page/filters/prompt state"
```

---

## Final Verification

- [ ] **Backend:** `cd backend && python -m pytest tests/ -q` — full suite green, no regressions
  against the pre-existing baseline (435 passing before this plan).
- [ ] **Frontend:** `cd frontend && npx vitest run` — full suite green (68 passing before this
  plan).
- [ ] **Typecheck:** `cd frontend && npx tsc --noEmit` — no new errors beyond the pre-existing
  unrelated ones (`chartUtils.tsx`, `Dashboard.tsx`/`Reports.tsx` summary types, `api.ts`'s
  `import.meta.env` typing).
- [ ] **Manual smoke test:** add a Slicer widget, confirm checking values filters other widgets
  on the same page but not other pages; open Sync slicers, mark it "All pages", confirm it now
  filters a second page too; open Selection pane, hide a widget, confirm it disappears in View
  mode but stays visible (dimmed) in Edit mode; create a bookmark, navigate away, click it, confirm
  page/filters/prompt restore.
- [ ] Refresh the Feature Parity Audit artifact: Side panes category should move from
  1 exists/2 partial/3 missing toward full or near-full closure; the Visual Types category's
  "Slicer" row moves from Missing to Exists.
