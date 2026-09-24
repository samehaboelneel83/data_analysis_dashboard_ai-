# Hierarchy Drill-Down + In-Panel Editing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a widget's Dimension bind to a hierarchy node (e.g. a Year→Quarter→Month→Day date
chain), click-to-drill in place on six chart types, and jump to the hierarchy editor from the
widget config panel — per `docs/superpowers/specs/2026-08-17-hierarchy-drill-down-design.md`.

**Architecture:** Backend gains a `dimension_granularity` config key that truncates a datetime
column to a label (year/quarter/month/day) before `shape_series` groups by it, plus matching
support in `_apply_filters` for filtering by that same truncated label. Frontend gets a small pure
`hierarchyUtils.ts` (flatten the tree into pickable labeled options, find a node's child, walk N
levels deep) consumed by both `WidgetConfigPanel` (binding + edit shortcut) and `WidgetRenderer`
(drill state, derived fresh each render from a single `drillPath` array — no separately-tracked
"current node" state to desync).

**Tech Stack:** FastAPI + pandas (backend), React + TypeScript + Vitest/Testing Library (frontend).

## Global Constraints

- TDD throughout: failing test → confirm RED for the right reason → minimal implementation →
  confirm GREEN → full suite → commit.
- Frontend commands must run from `frontend/` explicitly (cwd has repeatedly drifted to the repo
  root mid-session, silently picking up a stray global `vitest` and breaking the jsdom
  environment).
- Drill position (`drillPath`) is session-local UI state, like today's cross-filter
  `localSelected` — never written to `Widget.config` or persisted.
- `DATETRUNC` (the existing calc-column formula function) is left untouched — it solves a
  different problem (returns a real datetime marking a period's start, for date arithmetic) from
  what drilling needs (a stable string/int *label* per bucket, e.g. `"2024-Q1"`). No shared
  refactor between them; the spec's mention of extraction was an overstatement corrected here.

---

## Task 1: Backend — `dimension_granularity` grouping + filtering

**Files:**
- Modify: `backend/app/services/widget_data.py`
- Test: `backend/tests/test_dimension_granularity.py`

**Interfaces:**
- Produces: `_dimension_granularity_label(series: pd.Series, granularity: str) -> pd.Series` —
  `'year'` → int year (e.g. `2024`), `'quarter'` → `"2024-Q1"`, `'month'` → `"2024-01"`,
  `'day'` → `"2024-01-15"`. `shape_series` honors `config["dimension_granularity"]`.
  `_apply_filters` honors an optional `"granularity"` key on a filter dict (only affects the
  `"eq"` op — the only op drilling needs).

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_dimension_granularity.py
import pandas as pd
from app.services.widget_data import _dimension_granularity_label, shape_series, _apply_filters


def test_dimension_granularity_label_year():
    s = pd.Series(pd.to_datetime(["2024-01-15", "2024-06-01", "2023-12-31"]))
    result = _dimension_granularity_label(s, "year")
    assert list(result) == [2024, 2024, 2023]


def test_dimension_granularity_label_quarter():
    s = pd.Series(pd.to_datetime(["2024-01-15", "2024-06-01", "2024-11-01"]))
    result = _dimension_granularity_label(s, "quarter")
    assert list(result) == ["2024-Q1", "2024-Q2", "2024-Q4"]


def test_dimension_granularity_label_month():
    s = pd.Series(pd.to_datetime(["2024-01-15", "2024-06-01"]))
    result = _dimension_granularity_label(s, "month")
    assert list(result) == ["2024-01", "2024-06"]


def test_shape_series_groups_by_year_when_dimension_granularity_set():
    df = pd.DataFrame({
        "order_date": pd.to_datetime(["2023-01-01", "2023-06-01", "2024-01-01"]),
        "sales": [10, 20, 30],
    })
    config = {"dimension": "order_date", "dimension_granularity": "year", "measure": "sales", "aggregation": "sum"}
    result = shape_series(df, config)
    rows = {r["name"]: r["value"] for r in result["rows"]}
    assert rows == {2023: 30, 2024: 30}


def test_apply_filters_eq_with_granularity_matches_truncated_value():
    df = pd.DataFrame({
        "order_date": pd.to_datetime(["2023-01-01", "2023-06-01", "2024-01-01"]),
        "sales": [10, 20, 30],
    })
    filtered = _apply_filters(df, [{"column": "order_date", "op": "eq", "value": 2023, "granularity": "year"}])
    assert list(filtered["sales"]) == [10, 20]
```

- [ ] **Step 2: Run and confirm it fails**

```
cd backend && python -m pytest tests/test_dimension_granularity.py -v
```
Expected: `ImportError: cannot import name '_dimension_granularity_label'`.

- [ ] **Step 3: Implement.** In `widget_data.py`, add near `_agg_series` (needs the same
  `_as_datetime`-style coercion `_build_safe_ns`'s closures use, but as its own standalone
  function — not shared with the formula engine, see Global Constraints):

```python
def _dimension_granularity_label(series: pd.Series, granularity: str) -> pd.Series:
    """Truncates a datetime series to a stable label per bucket for grouping/drilling.
    Distinct from the calc-column formula language's DATETRUNC, which returns a real
    datetime (period start) for date arithmetic -- this returns a display/filter label."""
    dt = series if pd.api.types.is_datetime64_any_dtype(series) else pd.to_datetime(series, errors="coerce")
    granularity = (granularity or "").lower()
    if granularity == "year":
        return dt.dt.year
    if granularity == "quarter":
        return dt.dt.year.astype("Int64").astype(str) + "-Q" + dt.dt.quarter.astype("Int64").astype(str)
    if granularity == "month":
        return dt.dt.strftime("%Y-%m")
    if granularity == "day":
        return dt.dt.strftime("%Y-%m-%d")
    raise ValueError(f"Unsupported granularity: {granularity}")
```

  In `shape_series`, right after `df = _apply_filters(df, filters)` and the `if df.empty` guard,
  before the dimension is used for grouping:
```python
    dim_granularity = config.get("dimension_granularity") or None
    if dim_granularity and dim and dim in df.columns:
        df = df.copy()
        df[dim] = _dimension_granularity_label(df[dim], dim_granularity)
```
  (Overwriting the `dim` column in place means every existing groupby/crosstab code path below
  it works unchanged — they already just do `df.groupby(dim)`.)

  In `_apply_filters`'s `"eq"` branch, add granularity support:
```python
            if op == "eq":
                granularity = f.get("granularity")
                if granularity:
                    truncated = _dimension_granularity_label(df[col], granularity)
                    df = df[truncated.astype(str) == str(val)]
                else:
                    df = df[df[col].astype(str) == str(val)] if df[col].dtype == object else df[df[col] == val]
```
  (Replaces the existing `elif op == "eq":` line — same behavior when no `granularity` key is
  present, since `f.get("granularity")` is `None` for every existing filter shape in the
  codebase.)

- [ ] **Step 4: Run and confirm it passes. Run the full backend suite** (`python -m pytest
  tests/ -q`) — confirms the `_apply_filters` change doesn't regress any existing filter test.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/widget_data.py backend/tests/test_dimension_granularity.py
git commit -m "Add dimension_granularity support for hierarchy drill grouping/filtering"
```

---

## Task 2: Frontend — hierarchy tree utilities

**Files:**
- Create: `frontend/src/lib/hierarchyUtils.ts`
- Test: `frontend/src/lib/hierarchyUtils.test.ts`

**Interfaces:**
- Produces: `flattenHierarchy(nodes: HierarchyNode[]): { id: number; label: string; column_name:
  string; format?: string }[]`, `getChildNode(nodes: HierarchyNode[], parentId: number):
  HierarchyNode | undefined`, `walkToDepth(nodes: HierarchyNode[], startId: number, steps:
  number): number`.

- [ ] **Step 1: Write the failing tests**

```ts
// frontend/src/lib/hierarchyUtils.test.ts
import { describe, it, expect } from 'vitest'
import { flattenHierarchy, getChildNode, walkToDepth } from './hierarchyUtils'
import type { HierarchyNode } from '../types/report'

function node(overrides: Partial<HierarchyNode>): HierarchyNode {
  return { id: 0, dataset_id: 10, parent_id: null, name: '', node_type: 'dimension', position: 0, created_at: '2026-01-01', ...overrides }
}

const dates = node({ id: 1, name: 'Dates', node_type: 'folder', parent_id: null })
const orderDate = node({ id: 2, name: 'Order Date', node_type: 'date', parent_id: 1, column_name: 'order_date' })
const year = node({ id: 3, name: 'Year', node_type: 'date', parent_id: 2, column_name: 'order_date', format: 'year' })
const quarter = node({ id: 4, name: 'Quarter', node_type: 'date', parent_id: 3, column_name: 'order_date', format: 'quarter' })
const nodes = [dates, orderDate, year, quarter]

describe('flattenHierarchy', () => {
  it('excludes folders and builds a breadcrumb-style path label for each remaining node', () => {
    const result = flattenHierarchy(nodes)
    expect(result.map(r => r.label)).toEqual(['Order Date', 'Order Date ▸ Year', 'Order Date ▸ Year ▸ Quarter'])
    expect(result.map(r => r.id)).toEqual([2, 3, 4])
  })
})

describe('getChildNode', () => {
  it('returns the single child of a node', () => {
    expect(getChildNode(nodes, 2)?.id).toBe(3)
    expect(getChildNode(nodes, 3)?.id).toBe(4)
  })
  it('returns undefined for a leaf node', () => {
    expect(getChildNode(nodes, 4)).toBeUndefined()
  })
})

describe('walkToDepth', () => {
  it('walks N child links from a starting node', () => {
    expect(walkToDepth(nodes, 2, 0)).toBe(2)
    expect(walkToDepth(nodes, 2, 1)).toBe(3)
    expect(walkToDepth(nodes, 2, 2)).toBe(4)
  })
  it('stops at a leaf if steps exceeds the chain depth', () => {
    expect(walkToDepth(nodes, 2, 10)).toBe(4)
  })
})
```

- [ ] **Step 2: Run and confirm it fails** — `frontend/src/lib/hierarchyUtils.ts` doesn't exist.

- [ ] **Step 3: Implement**

```ts
// frontend/src/lib/hierarchyUtils.ts
import type { HierarchyNode } from '../types/report'

export function flattenHierarchy(nodes: HierarchyNode[]): { id: number; label: string; column_name: string; format?: string }[] {
  const byId = new Map(nodes.map(n => [n.id, n]))
  const pathLabel = (n: HierarchyNode): string => {
    const parent = n.parent_id != null ? byId.get(n.parent_id) : undefined
    if (!parent || parent.node_type === 'folder') return n.name
    return `${pathLabel(parent)} ▸ ${n.name}`
  }
  return nodes
    .filter((n): n is HierarchyNode & { column_name: string } => n.node_type !== 'folder' && !!n.column_name)
    .map(n => ({ id: n.id, label: pathLabel(n), column_name: n.column_name, format: n.format }))
}

export function getChildNode(nodes: HierarchyNode[], parentId: number): HierarchyNode | undefined {
  return nodes.find(n => n.parent_id === parentId)
}

export function walkToDepth(nodes: HierarchyNode[], startId: number, steps: number): number {
  let id = startId
  for (let i = 0; i < steps; i++) {
    const child = getChildNode(nodes, id)
    if (!child) break
    id = child.id
  }
  return id
}
```

- [ ] **Step 4: Run and confirm it passes.**

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/hierarchyUtils.ts frontend/src/lib/hierarchyUtils.test.ts
git commit -m "Add pure hierarchy tree utilities (flatten, child lookup, depth walk)"
```

---

## Task 3: Frontend — WidgetConfigPanel hierarchy-aware Dimension picker + Edit-hierarchy shortcut

**Files:**
- Modify: `frontend/src/components/report/WidgetConfigPanel.tsx`
- Test: `frontend/src/components/report/WidgetConfigPanel.test.tsx`
- Modify: `frontend/src/pages/ReportBuilder.tsx`

**Interfaces:**
- Consumes: `flattenHierarchy` (Task 2).
- Produces: `WidgetConfigPanel` gains `hierarchy?: HierarchyNode[]` and `onHierarchyRefresh?: ()
  => void` props. When a hierarchy node is picked as Dimension, the emitted config gains
  `hierarchyNodeId: number` and (for date-chain nodes) `dimension_granularity: string`.

- [ ] **Step 1: Write the failing tests**

```tsx
// append to frontend/src/components/report/WidgetConfigPanel.test.tsx
import type { HierarchyNode } from '../../types/report'

function hNode(overrides: Partial<HierarchyNode>): HierarchyNode {
  return { id: 0, dataset_id: 10, parent_id: null, name: '', node_type: 'dimension', position: 0, created_at: '2026-01-01', ...overrides }
}

describe('WidgetConfigPanel hierarchy binding', () => {
  const hierarchy: HierarchyNode[] = [
    hNode({ id: 1, name: 'Dates', node_type: 'folder' }),
    hNode({ id: 2, name: 'Order Date', node_type: 'date', parent_id: 1, column_name: 'order_date' }),
    hNode({ id: 3, name: 'Year', node_type: 'date', parent_id: 2, column_name: 'order_date', format: 'year' }),
  ]

  it('writes hierarchyNodeId and dimension_granularity when a hierarchy option is picked', () => {
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget()} columns={columns} onUpdate={onUpdate}
      hierarchy={hierarchy} /></CrossFilterProvider>)

    fireEvent.change(screen.getByLabelText('Dimension (Group / X-axis)'), { target: { value: 'h:3' } })
    act(() => { vi.advanceTimersByTime(700) })

    expect(onUpdate).toHaveBeenCalled()
    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.dimension).toBe('order_date')
    expect(config.dimension_granularity).toBe('year')
    expect(config.hierarchyNodeId).toBe(3)
  })

  it('shows an Edit hierarchy link only once a hierarchy node is bound', () => {
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget({ config: { dimension: 'region' } })} columns={columns} onUpdate={vi.fn()}
      hierarchy={hierarchy} /></CrossFilterProvider>)
    expect(screen.queryByRole('button', { name: /Edit hierarchy/i })).not.toBeInTheDocument()
  })

  it('clears hierarchyNodeId when a plain column is picked instead', () => {
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget({ config: { hierarchyNodeId: 3, dimension: 'order_date', dimension_granularity: 'year' } })}
      columns={columns} onUpdate={onUpdate} hierarchy={hierarchy} /></CrossFilterProvider>)

    fireEvent.change(screen.getByLabelText('Dimension (Group / X-axis)'), { target: { value: 'region' } })
    act(() => { vi.advanceTimersByTime(700) })

    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.hierarchyNodeId).toBeUndefined()
    expect(config.dimension).toBe('region')
  })
})
```

  (Note: the third test's initial widget has `hierarchyNodeId` set, so per the second test's
  assertion pattern, an "Edit hierarchy" button IS expected there — that's covered implicitly by
  the picker re-render; no separate assertion needed since the focus is the clear-on-column-pick
  behavior.)

- [ ] **Step 2: Run and confirm it fails.**

Run: `cd frontend && npx vitest run src/components/report/WidgetConfigPanel.test.tsx`
Expected: `getByLabelText('Dimension (Group / X-axis)')` fails to find a labelled element (today's
generic `fld()`/`sel()` rendering has no `htmlFor`/`id` pairing).

- [ ] **Step 3: Implement.** In `WidgetConfigPanel.tsx`:
  - Add to `Props`: `hierarchy?: HierarchyNode[]`, `onHierarchyRefresh?: () => void`. Import
    `HierarchyNode` from `../../types/report`, `flattenHierarchy` from `../../lib/hierarchyUtils`,
    and `HierarchyTree` from `./HierarchyTree`.
  - Add state (seeded in both the initial `useState` and the widget-change sync `useEffect`,
    matching `drillthroughPageId`'s exact pattern):
```tsx
  const [hierarchyNodeId, setHierarchyNodeId] = useState<string>(cfg.hierarchyNodeId != null ? String(cfg.hierarchyNodeId) : '')
  const [dimensionGranularity, setDimensionGranularity] = useState<string>((cfg.dimension_granularity as string) ?? '')
  const [showHierarchyEditor, setShowHierarchyEditor] = useState(false)
```
    In the sync effect: `setHierarchyNodeId(cfg.hierarchyNodeId != null ? String(cfg.hierarchyNodeId) : '')`,
    `setDimensionGranularity((cfg.dimension_granularity as string) ?? '')`.
  - In the debounced save effect, after the existing role-field loop (still inside the `else`
    branch that handles non-text/button widgets):
```tsx
      if (hierarchyNodeId) config.hierarchyNodeId = Number(hierarchyNodeId)
      if (dimensionGranularity) config.dimension_granularity = dimensionGranularity
```
    Add `hierarchyNodeId, dimensionGranularity` to that effect's dependency array.
  - Replace the generic role-field loop's handling of the category role when hierarchy data
    exists. Change:
```tsx
          {(ROLE_SPECS[wt] ?? []).map(rf => {
            if (rf.multi) {
```
    to insert a new branch immediately before the `if (rf.multi)` check:
```tsx
          {(ROLE_SPECS[wt] ?? []).map(rf => {
            if (rf.role === 'category' && hierarchy && hierarchy.length > 0) {
              const hOptions = flattenHierarchy(hierarchy)
              const currentValue = hierarchyNodeId ? `h:${hierarchyNodeId}` : (roleValues[rf.role] ?? '')
              return (
                <div key={rf.role} style={{ marginBottom: 12 }}>
                  <label htmlFor="dimension-select" style={{ display:'block', fontSize:10, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                    {rf.label ?? rf.role}
                  </label>
                  <select id="dimension-select" value={currentValue} onChange={e => {
                    const v = e.target.value
                    if (v.startsWith('h:')) {
                      const picked = hOptions.find(o => `h:${o.id}` === v)
                      if (picked) {
                        setRole('category', picked.column_name)
                        setHierarchyNodeId(String(picked.id))
                        setDimensionGranularity(picked.format ?? '')
                      }
                    } else {
                      setRole('category', v)
                      setHierarchyNodeId('')
                      setDimensionGranularity('')
                    }
                  }} style={{ width:'100%' }}>
                    <option value="">— select column —</option>
                    <optgroup label="Columns">
                      {colOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                    </optgroup>
                    <optgroup label="Hierarchies">
                      {hOptions.map(o => <option key={o.id} value={`h:${o.id}`}>{o.label}</option>)}
                    </optgroup>
                  </select>
                  {hierarchyNodeId && (
                    <button type="button" onClick={() => setShowHierarchyEditor(s => !s)}
                      style={{ marginTop:4, background:'none', border:'none', color:'var(--accent)', cursor:'pointer', fontSize:11, padding:0 }}>
                      ✎ Edit hierarchy
                    </button>
                  )}
                  {hierarchyNodeId && showHierarchyEditor && (
                    <div style={{ marginTop:8, border:'1px solid var(--border)', borderRadius:6, padding:8, maxHeight:220, overflowY:'auto' }}>
                      <HierarchyTree nodes={hierarchy} datasetId={datasetId || (primaryDatasetId ?? 0)}
                        onRefresh={() => onHierarchyRefresh?.()} />
                    </div>
                  )}
                </div>
              )
            }
            if (rf.multi) {
```
    (The rest of the `.map(rf => ...)` body — the `multi` branch and the plain-select fallback —
    is unchanged. The fallback plain-select branch is what still renders for every widget type
    when `hierarchy` is empty/undefined, so nothing regresses for reports with no hierarchy set
    up yet.)

- [ ] **Step 4: Wire `ReportBuilder.tsx`.** Pass `hierarchy={hierarchy}
  onHierarchyRefresh={refreshHierarchy}` into the existing `<WidgetConfigPanel>` call
  (`ReportBuilder.tsx`'s `rightPanelMode === 'default'` block, `selectedW` branch).

- [ ] **Step 5: Run and confirm it passes. Run the full frontend suite.**

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/report/WidgetConfigPanel.tsx frontend/src/components/report/WidgetConfigPanel.test.tsx frontend/src/pages/ReportBuilder.tsx
git commit -m "Add hierarchy-aware Dimension picker and in-panel hierarchy editor shortcut"
```

---

## Task 4: Frontend — WidgetRenderer drill state, click-to-drill, breadcrumb

**Files:**
- Modify: `frontend/src/components/report/WidgetRenderer.tsx`
- Test: `frontend/src/components/report/WidgetRenderer.test.tsx`
- Modify: `frontend/src/pages/ReportBuilder.tsx`

**Interfaces:**
- Consumes: `getChildNode`, `walkToDepth` (Task 2); `config.hierarchyNodeId`/
  `config.dimension_granularity` (Task 3's output shape).
- Produces: `WidgetRenderer` gains a `hierarchy?: HierarchyNode[]` prop. Clicking a data point on
  a hierarchy-bound widget both emits the existing cross-filter and drills one level; a breadcrumb
  renders in the widget header while `drillPath.length > 0`.

- [ ] **Step 1: Write the failing tests.** `handleClick` is one handler shared by every
  category-clickable widget type (`list` included — see `WidgetBody`'s `list` branch, `onClick={()
  => broadcasts && onClickPoint(row.name)}`), so these tests use `widget_type: 'list'` rather than
  `'bar'`: recharts renders nothing textually inside jsdom's zero-width `ResponsiveContainer`
  (every existing passing `findByText` in this file already avoids `'bar'`/`'pie'`/etc. for
  exactly this reason — check the file before assuming otherwise), while `list` renders plain
  `<div>{row.name}</div>` and exercises the identical `handleClick` code path bar/pie/donut/
  treemap/heatmap/line would also call in a real browser.

```tsx
// append to frontend/src/components/report/WidgetRenderer.test.tsx
import type { HierarchyNode } from '../../types/report'

function hNode(overrides: Partial<HierarchyNode>): HierarchyNode {
  return { id: 0, dataset_id: 10, parent_id: null, name: '', node_type: 'dimension', position: 0, created_at: '2026-01-01', ...overrides }
}

describe('WidgetRenderer hierarchy drill-down', () => {
  const hierarchy: HierarchyNode[] = [
    hNode({ id: 1, name: 'Dates', node_type: 'folder' }),
    hNode({ id: 2, name: 'Year', node_type: 'date', parent_id: 1, column_name: 'order_date', format: 'year' }),
    hNode({ id: 3, name: 'Quarter', node_type: 'date', parent_id: 2, column_name: 'order_date', format: 'quarter' }),
  ]

  it('drilling into a clicked row re-queries one level deeper and shows a breadcrumb', async () => {
    vi.mocked(widgetDataApi.query)
      .mockResolvedValueOnce({ rows: [{ name: 2024, value: 100 }], sampled: false })
      .mockResolvedValueOnce({ rows: [{ name: '2024-Q1', value: 40 }], sampled: false })
    renderWidget({
      widget: barWidget({ widget_type: 'list', config: { dimension: 'order_date', dimension_granularity: 'year', hierarchyNodeId: 2 } }),
      hierarchy,
    })

    const row = await screen.findByText('2024')
    fireEvent.click(row)

    expect(await screen.findByText('2024-Q1')).toBeInTheDocument()
    const calls = vi.mocked(widgetDataApi.query).mock.calls
    const [, drilledConfig] = calls[calls.length - 1]
    expect((drilledConfig as any).dimension_granularity).toBe('quarter')
    expect((drilledConfig as any).filters).toContainEqual({ column: 'order_date', op: 'eq', value: 2024, granularity: 'year' })
    expect(screen.getByText('2024')).toBeInTheDocument() // breadcrumb crumb for the drilled-from value
  })

  it('clicking the "All" breadcrumb resets back to the top level', async () => {
    vi.mocked(widgetDataApi.query)
      .mockResolvedValueOnce({ rows: [{ name: 2024, value: 100 }], sampled: false })
      .mockResolvedValueOnce({ rows: [{ name: '2024-Q1', value: 40 }], sampled: false })
      .mockResolvedValueOnce({ rows: [{ name: 2024, value: 100 }], sampled: false })
    renderWidget({
      widget: barWidget({ widget_type: 'list', config: { dimension: 'order_date', dimension_granularity: 'year', hierarchyNodeId: 2 } }),
      hierarchy,
    })
    fireEvent.click(await screen.findByText('2024'))
    await screen.findByText('2024-Q1')

    fireEvent.click(screen.getByRole('button', { name: 'All' }))

    await waitFor(() => expect(screen.queryByRole('button', { name: 'All' })).not.toBeInTheDocument())
  })

  it('a non-hierarchy widget click behaves exactly as before (no breadcrumb, no drill re-query)', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [{ name: 'North', value: 5 }], sampled: false })
    renderWidget({ widget: barWidget({ widget_type: 'list' }), hierarchy })
    fireEvent.click(await screen.findByText('North'))
    expect(screen.queryByRole('button', { name: 'All' })).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run and confirm it fails** — no `hierarchy` prop, no drilling, no breadcrumb.

Run: `cd frontend && npx vitest run src/components/report/WidgetRenderer.test.tsx -t "hierarchy drill-down"`

- [ ] **Step 3: Implement.** In `WidgetRenderer.tsx`:
  - Add `hierarchy?: HierarchyNode[]` to `Props` and the destructured parameter list. Import
    `HierarchyNode` from `../../types/report`, `getChildNode`/`walkToDepth` from
    `../../lib/hierarchyUtils`.
  - Add drill state right after the existing `checked` state:
```tsx
  const [drillPath, setDrillPath] = useState<{ column: string; granularity?: string; value: unknown; label: string }[]>([])
  useEffect(() => { setDrillPath([]) }, [widget.id])
```
  - Compute the hierarchy-bound node ids (right before `mergedConfig`):
```tsx
  const hierarchyNodeId = (widget.config as any).hierarchyNodeId as number | undefined
  const currentNodeId = hierarchyNodeId != null && hierarchy ? walkToDepth(hierarchy, hierarchyNodeId, drillPath.length) : undefined
  const currentNode = currentNodeId != null ? hierarchy?.find(n => n.id === currentNodeId) : undefined
```
  - Extend `mergedConfig`'s `useMemo` body (after the existing `cfg.filters = [...]` line, before
    `return cfg`):
```tsx
    if (hierarchyNodeId != null && currentNode?.column_name) {
      cfg.dimension = currentNode.column_name
      if (currentNode.format) cfg.dimension_granularity = currentNode.format
      else delete cfg.dimension_granularity
      cfg.filters = [
        ...cfg.filters,
        ...drillPath.map(step => ({ column: step.column, op: 'eq', value: step.value, ...(step.granularity ? { granularity: step.granularity } : {}) })),
      ]
    }
```
    Add `hierarchyNodeId, currentNode?.column_name, currentNode?.format, JSON.stringify(drillPath)`
    to the `useMemo`'s dependency array (it already has an eslint-disable comment above it — keep
    that, just extend the array).
  - Extend `handleClick` to also push a drill step when applicable, right after the existing
    `emitFilter` calls in both branches (the toggle-off and toggle-on cases) — simplest is to add
    the drill push once, after the existing if/else, since drilling should happen regardless of
    which branch fired:
```tsx
  const handleClick = useCallback((name: unknown) => {
    if (!canBroadcast(widget.id)) return
    const cfg = widget.config as any
    const col = cfg.dimension ?? cfg.column ?? null
    if (!col) return
    if (localSelected === name) {
      setLocalSelected(null)
      emitFilter(widget.id, widget.page_id, col, name, `${col} = ${name}`)
    } else {
      setLocalSelected(name)
      emitFilter(widget.id, widget.page_id, col, name, `${col} = ${name}`)
    }
    if (hierarchyNodeId != null && hierarchy && currentNodeId != null && currentNode?.column_name) {
      const child = getChildNode(hierarchy, currentNodeId)
      if (child) {
        setDrillPath(p => [...p, { column: currentNode.column_name!, granularity: currentNode.format, value: name, label: String(name) }])
      }
    }
  }, [canBroadcast, widget.id, widget.config, localSelected, emitFilter, hierarchyNodeId, hierarchy, currentNodeId, currentNode])
```
  - Add a breadcrumb row. In the widget's header `<div>` (the one containing the title `<span>`
    and the broadcast-arrow badge, right before its closing tag), add:
```tsx
        {drillPath.length > 0 && (
          <div style={{ display:'flex', gap:4, alignItems:'center', fontSize:10, color:'var(--muted)' }}>
            <button onClick={() => setDrillPath([])} style={{ background:'none', border:'none', color:'var(--accent)', cursor:'pointer', fontSize:10, padding:0 }}>All</button>
            {drillPath.map((step, i) => (
              <span key={i} style={{ display:'flex', alignItems:'center', gap:4 }}>
                <span>▸</span>
                <button onClick={() => setDrillPath(p => p.slice(0, i + 1))}
                  style={{ background:'none', border:'none', color: i === drillPath.length - 1 ? 'var(--text)' : 'var(--accent)', cursor:'pointer', fontSize:10, padding:0 }}>
                  {step.label}
                </button>
              </span>
            ))}
          </div>
        )}
```

- [ ] **Step 4: Wire `ReportBuilder.tsx`.** Pass `hierarchy={hierarchy}` into both
  `<WidgetRenderer>` call sites (the mobile-stack view-only render and the desktop-grid editable
  render).

- [ ] **Step 5: Run and confirm it passes. Run the full frontend suite.**

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/report/WidgetRenderer.tsx frontend/src/components/report/WidgetRenderer.test.tsx frontend/src/pages/ReportBuilder.tsx
git commit -m "Add click-to-drill and a breadcrumb for hierarchy-bound widgets"
```

---

## Final Verification

- [ ] **Backend:** `cd backend && python -m pytest tests/ -q` — full suite green, no regressions.
- [ ] **Frontend:** `cd frontend && npx vitest run` — full suite green, no regressions.
- [ ] **Typecheck:** `cd frontend && npx tsc --noEmit` — no new errors beyond the pre-existing
  baseline (`chartUtils.tsx` ReactNode errors, `Dashboard.tsx`/`Reports.tsx` missing exports,
  `api.ts`'s `ImportMeta.env` — none of these files are touched by this plan).
- [ ] **Manual smoke test:** bind a bar chart's Dimension to a date column's "Year" hierarchy
  level, confirm it renders yearly totals; click a bar and confirm it re-renders at Quarter
  granularity filtered to that year, with a breadcrumb showing "All ▸ 2024"; click "All" and
  confirm it resets; click "✎ Edit hierarchy" and confirm the tree editor opens inline and a
  rename there is reflected after refresh.
- [ ] Refresh the Feature Parity Audit artifact: "Drill down / up on hierarchies" moves from
  Partial to Exists.
