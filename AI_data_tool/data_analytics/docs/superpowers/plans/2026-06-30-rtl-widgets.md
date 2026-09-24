# RTL Widgets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-widget RTL (Right-to-Left) toggle that flips axis direction in charts and text/layout direction in HTML widgets.

**Architecture:** `rtl: boolean` is stored in each widget's existing `config` object. `WidgetConfigPanel` adds a checkbox that emits the flag; `WidgetRenderer`'s `WidgetBody` reads it and applies either Recharts axis props (charts) or `dir="rtl"` (HTML widgets).

**Tech Stack:** React, TypeScript, Recharts (BarChart, LineChart, ScatterChart, PieChart, Treemap)

## Global Constraints

- No backend changes — `rtl` lives entirely in the frontend config JSON
- No new files — modify only the two files listed below
- Default RTL = `false` (absent key treated as false)
- Two files changed: `frontend/src/components/report/WidgetConfigPanel.tsx` and `frontend/src/components/report/WidgetRenderer.tsx`

---

### Task 1: RTL toggle in WidgetConfigPanel

**Files:**
- Modify: `frontend/src/components/report/WidgetConfigPanel.tsx`

**Interfaces:**
- Produces: emits `rtl: boolean` in every config branch passed to `onUpdate`

- [ ] **Step 1: Add `rtl` state and sync it on widget change**

In `WidgetConfigPanel.tsx`, add the state variable after the existing state declarations (around line 39):

```tsx
const [rtl, setRtl] = useState<boolean>(cfg.rtl ?? false)
```

In the first `useEffect` (the one that resets state when `widget.id` changes, starting around line 46), add the sync line after the existing `setTableCols` call:

```tsx
setRtl(cfg.rtl ?? false)
```

- [ ] **Step 2: Include `rtl` in the config emission useEffect**

In the second `useEffect` (the one that calls `onUpdate` with a debounce, starting around line 63), update all three config branches to include `rtl`:

```tsx
if (wt === 'text')        { config = { content, rtl } }
else if (wt === 'button') { config = { label, rtl } }
else {
  config = { aggregation: agg, limit, sort, sort_by: sortBy, rtl, ...(running ? { running } : {}) }
  if (dimension)          config.dimension  = dimension
  if (dimension2)         config.dimension2 = dimension2
  if (measure)            config.measure    = measure
  if (tableCols.length > 0) config.columns  = tableCols
}
```

Also add `rtl` to the dependency array at the bottom of that `useEffect`:

```tsx
}, [title, dimension, dimension2, measure, agg, limit, sort, sortBy, running, content, label, rtl, tableCols.join(',')])
```

- [ ] **Step 3: Add the RTL checkbox to the UI**

In the JSX `return`, add this block immediately after the Title field (after the `{fld('Title', ...)}` call, around line 111):

```tsx
<div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
  <input
    id="rtl-toggle"
    type="checkbox"
    checked={rtl}
    onChange={e => setRtl(e.target.checked)}
  />
  <label htmlFor="rtl-toggle" style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', cursor: 'pointer' }}>
    RTL (Right to Left)
  </label>
</div>
```

- [ ] **Step 4: Manual verification**

1. Open the report builder in the browser
2. Select any widget and open its config panel
3. Confirm the "RTL (Right to Left)" checkbox appears below the Title field for every widget type (bar, table, text, button, kpi, etc.)
4. Check and uncheck the box — confirm the widget's config updates (no console errors, the `onUpdate` callback fires after ~600ms)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/report/WidgetConfigPanel.tsx
git commit -m "feat: add RTL toggle to widget config panel"
```

---

### Task 2: RTL rendering for chart widgets (bar, line, scatter)

**Files:**
- Modify: `frontend/src/components/report/WidgetRenderer.tsx`

**Interfaces:**
- Consumes: `cfg.rtl` (boolean, may be undefined — treat as false)

- [ ] **Step 1: Read `rtl` flag at the top of `WidgetBody`**

In `WidgetBody` (starting around line 182), add this line right after the existing `const cfg = widget.config as any` line:

```tsx
const rtl = !!(cfg.rtl)
```

- [ ] **Step 2: Apply RTL to the Bar chart**

Find the Bar chart block (around line 293). Update `XAxis` to add `reversed={rtl}` and `YAxis` to add `orientation`:

```tsx
<XAxis dataKey="name" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} angle={-30} textAnchor="end" interval={0} reversed={rtl} />
<YAxis tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} orientation={rtl ? 'right' : 'left'} />
```

- [ ] **Step 3: Apply RTL to the Line chart**

Find the Line chart block (around line 314). Same pattern:

```tsx
<XAxis dataKey="name" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} angle={-30} textAnchor="end" reversed={rtl} />
<YAxis tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} orientation={rtl ? 'right' : 'left'} />
```

- [ ] **Step 4: Apply RTL to the Scatter chart**

Find the Scatter chart block (around line 372). Same pattern:

```tsx
<XAxis dataKey="x" type="number" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} reversed={rtl} />
<YAxis dataKey="y" type="number" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} orientation={rtl ? 'right' : 'left'} />
```

- [ ] **Step 5: Manual verification**

1. Add a bar chart widget, set some data, enable RTL in its config
2. Confirm X-axis reverses (rightmost value is the first data point) and Y-axis moves to the right side
3. Repeat for line and scatter widgets
4. Disable RTL — confirm charts return to normal LTR layout

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/report/WidgetRenderer.tsx
git commit -m "feat: RTL axis flip for bar, line, scatter charts"
```

---

### Task 3: RTL rendering for pie, donut, treemap

**Files:**
- Modify: `frontend/src/components/report/WidgetRenderer.tsx`

**Interfaces:**
- Consumes: `rtl` boolean already declared in `WidgetBody` from Task 2

- [ ] **Step 1: Wrap the Pie chart's ResponsiveContainer**

Find the Pie chart block (around line 333). Wrap its `<ResponsiveContainer>` in a div:

```tsx
if (wt === 'pie') return (
  <div dir={rtl ? 'rtl' : undefined} style={{ height: '100%' }}>
    <ResponsiveContainer width="100%" height="100%">
      <PieChart>
        {/* existing content unchanged */}
      </PieChart>
    </ResponsiveContainer>
  </div>
)
```

- [ ] **Step 2: Wrap the Donut chart's ResponsiveContainer**

Find the Donut chart block (around line 353). Same wrapper:

```tsx
if (wt === 'donut') return (
  <div dir={rtl ? 'rtl' : undefined} style={{ height: '100%' }}>
    <ResponsiveContainer width="100%" height="100%">
      <PieChart>
        {/* existing content unchanged */}
      </PieChart>
    </ResponsiveContainer>
  </div>
)
```

- [ ] **Step 3: Wrap the Treemap's ResponsiveContainer**

Find the Treemap block (around line 391). Same wrapper:

```tsx
if (wt === 'treemap') return (
  <div dir={rtl ? 'rtl' : undefined} style={{ height: '100%' }}>
    <ResponsiveContainer width="100%" height="100%">
      <Treemap {/* existing props unchanged */}>
        {/* existing content unchanged */}
      </Treemap>
    </ResponsiveContainer>
  </div>
)
```

- [ ] **Step 4: Manual verification**

1. Add a donut widget with data, enable RTL — confirm the legend shifts to the left (RTL side)
2. Add a pie widget, enable RTL — confirm legend alignment flips
3. Treemap: enable RTL — confirm the container flips (text inside SVG cells stays centered, which is acceptable)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/report/WidgetRenderer.tsx
git commit -m "feat: RTL layout for pie, donut, treemap widgets"
```

---

### Task 4: RTL rendering for HTML widgets (kpi, table, crosstab, list, text, button)

**Files:**
- Modify: `frontend/src/components/report/WidgetRenderer.tsx`

**Interfaces:**
- Consumes: `rtl` boolean already declared in `WidgetBody` from Task 2

- [ ] **Step 1: Apply RTL to the KPI widget**

Find the KPI block (around line 200). Add `dir` to the outer container div:

```tsx
if (wt === 'kpi') {
  const val = data.rows?.[0]?.value ?? '—'
  return (
    <div dir={rtl ? 'rtl' : undefined} style={{ height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 4 }}>
      <div style={{ fontSize: 36, fontWeight: 700, fontFamily: 'var(--mono)', color: 'var(--accent)' }}>
        {typeof val === 'number' ? val.toLocaleString(undefined, { maximumFractionDigits: 2 }) : val}
      </div>
      <div style={{ fontSize: 11, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em' }}>
        {cfg.measure || cfg.dimension || 'Value'}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Apply RTL to table and crosstab**

Find the table/crosstab block (around line 215). Add `dir` to the scroll container:

```tsx
return (
  <div dir={rtl ? 'rtl' : undefined} style={{ overflow: 'auto', height: '100%' }}>
    <table style={{ fontSize: 12 }}>
      {/* existing content unchanged */}
    </table>
    {data.total > rows.length && (
      <div style={{ padding: '6px 12px', color: 'var(--muted)', fontSize: 11, borderTop: '1px solid var(--border)' }}>
        Showing {rows.length} of {data.total}
      </div>
    )}
  </div>
)
```

- [ ] **Step 3: Apply RTL to the list widget**

Find the list block (around line 250). Add `dir` to the scroll container:

```tsx
return (
  <div dir={rtl ? 'rtl' : undefined} style={{ overflow: 'auto', height: '100%' }}>
    {(data.rows ?? []).map((row: any, i: number) => {
      {/* existing map content unchanged */}
    })}
  </div>
)
```

- [ ] **Step 4: Apply RTL to the text widget**

Find the text block (around line 188). Add `dir` to its div:

```tsx
if (wt === 'text') return (
  <div dir={rtl ? 'rtl' : undefined} style={{ padding: 12, fontSize: 13, whiteSpace: 'pre-wrap' }}>{cfg.content || 'Text block'}</div>
)
```

- [ ] **Step 5: Apply RTL to the button widget**

Find the button block (around line 191). Add `dir` to the centering div:

```tsx
if (wt === 'button') return (
  <div dir={rtl ? 'rtl' : undefined} style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
    <button className="btn btn-primary" style={{ pointerEvents: 'none' }}>{cfg.label || 'Button'}</button>
  </div>
)
```

- [ ] **Step 6: Manual verification**

1. **Text widget**: Enable RTL — confirm text flows right-to-left (especially visible with Arabic/Hebrew or when text wraps)
2. **Table**: Enable RTL — confirm header and cell text aligns right, scroll starts from the right
3. **Crosstab**: Same as table
4. **List**: Enable RTL — confirm name appears on the right and value on the left
5. **KPI**: Enable RTL — confirm label text aligns to the right
6. **Button**: Enable RTL — confirm button label aligns right within the widget
7. For each: disable RTL and confirm it returns to normal LTR

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/report/WidgetRenderer.tsx
git commit -m "feat: RTL layout for kpi, table, crosstab, list, text, button widgets"
```
