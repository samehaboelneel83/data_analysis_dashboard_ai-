# Chart Type Expansion — Phase 2 (Relationship Plots) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the 6 Phase 2 chart types from `docs/superpowers/specs/2026-08-10-chart-type-expansion-design.md`: Bubble Plot, Bubble Change Plot, Correlation Matrix, Heat Map, Fit Lines (overlay), Parallel Coordinates Plot.

**Architecture:** Two foundational widenings precede the chart work, both flagged since Phase 0's final review: `ChartRendererProps` gains a `data: any` field carrying the FULL backend payload (not just `rows`) since Correlation Matrix and Parallel Coordinates don't fit a flat rows array; `WidgetConfigPanel` gains multi-select (ordered, click-to-add/remove) role field support for `RoleField.multi` roles. Four new backend shapers: `shape_bubble`, `shape_bubble_animated`, `shape_correlation_matrix`, `shape_heatmap`, `shape_parallel_coordinates` (5 functions — Bubble Change Plot needs its own shaper since it groups by an extra animation-frame dimension Bubble Plot doesn't). A shared `compute_fit_line()` regression helper (linear/quadratic/cubic/best-fit via `numpy.polyfit`) is invoked by `shape_bubble` when a `fit_line` config option is set.

**Tech Stack:** FastAPI + pandas + numpy (backend, no new dependencies — regression uses `numpy.polyfit`, correlation uses pandas' built-in `.corr()`), React 18 + TypeScript + Recharts (frontend, `ScatterChart`+`ZAxis` for Bubble, hand-built SVG for Correlation Matrix / Heat Map / Parallel Coordinates since Recharts has no native support for any of these three).

## Global Constraints

- Every new chart type is purely additive: no existing chart type's shaper, renderer, or config-panel behavior changes.
- Follow the established patterns: shapers are `(df, config) -> dict` functions registered in `SHAPERS`; renderers are `React.FC<ChartRendererProps>` registered in `CHART_RENDERERS`; role fields render via `ROLE_SPECS[wt]`.
- No new runtime dependencies.
- `npm run build` has a baseline of exactly 10 pre-existing TypeScript errors, unrelated to this and prior plans. Every task must leave this count unchanged.
- Backend regression tests dedupe any measure-role list before using it for pandas column selection (`list(dict.fromkeys(...))`) — this is now a hard house rule after Phase 1 shipped two shapers with an identical duplicate-column crash bug (`measure == measure2`) that both needed a fix round. Every new shaper in this phase that accepts more than one measure role must apply this pattern from the start, with a test proving it.
- **Documented v1 scope reductions** (explicitly out of scope for this phase, not oversights):
  - Fit Lines: only `linear`/`quadratic`/`cubic`/`best_fit` are implemented (via `numpy.polyfit` + R² comparison for best_fit). P-Spline is deferred — it needs `scipy.interpolate` machinery this phase doesn't build.
  - Fit Lines only apply to **Bubble Plot** in this phase, not Scatter — Scatter still uses Phase 0's fake `name`/`value`-as-`x`/`y` data (giving Scatter real two-measure backend data was explicitly deferred in Phase 0 and remains out of scope here; retrofitting it is a candidate for a future plan).
  - Bubble Plot's `color` role (when set without `group`) uses a simple two-stop linear color interpolation between the measure's min/max — no gradient legend is rendered in this phase.
  - Multi-select role fields (Correlation Matrix's `measures`, Parallel Coordinates' `measures`) use click-to-add/click-to-remove ordering (the order items were clicked in IS the display order) — no drag-to-reorder UI.
- This host cannot run a second Docker stack. Every "verify" step substitutes rigorous diff/code review plus `pytest`/`npm run test`/`npm run build` for a literal `docker compose` + browser check.
- New `WidgetType` union members this phase (snake_case): `bubble`, `bubble_change`, `correlation_matrix`, `heatmap`, `parallel_coordinates`.

---

## Task 1: Widen `ChartRendererProps` with the full `data` payload

**Files:**
- Modify: `frontend/src/components/report/chartRenderers/types.ts`
- Modify: `frontend/src/components/report/WidgetRenderer.tsx`

**Interfaces:**
- Produces: `ChartRendererProps.data: any` — the full, unshaped backend response object (e.g. `{type, matrix, axes, rows, ...}`), passed alongside the existing `rows` (kept for the 16 existing renderers, which continue to use it unchanged).
- Consumes (by Tasks 9, 13): `CorrelationMatrixRenderer` and `ParallelCoordinatesRenderer` read `data.matrix`/`data.axes` directly; they do not use `rows`.

- [ ] **Step 1: Add the field**

In `frontend/src/components/report/chartRenderers/types.ts`, add to the interface (after `rows: any[]`):
```ts
  data: any
```

- [ ] **Step 2: Pass it in the dispatch**

In `frontend/src/components/report/WidgetRenderer.tsx`, in the `CHART_RENDERERS` dispatch block inside `WidgetBody`, add `data={data}` to the props passed:
```tsx
  const ChartRenderer = CHART_RENDERERS[wt]
  if (ChartRenderer) {
    return (
      <ChartRenderer rows={rows} data={data} cfg={cfg} rtl={rtl} broadcasts={broadcasts}
        localSelected={localSelected} onClickPoint={onClickPoint}
        measureFmt={measureFmt} measure2Fmt={measure2Fmt} allFormats={allFormats} />
    )
  }
```
(`data` is already in scope in `WidgetBody` — it's the function's own parameter, the same object `rows` is derived from via `const rows = data.rows ?? []`.)

- [ ] **Step 3: Verify**

Run (from `frontend/`):
```bash
npm run build
```
Expected: exactly the 10 pre-existing errors — this is a pure additive prop, unused by all 16 existing renderers.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/report/chartRenderers/types.ts frontend/src/components/report/WidgetRenderer.tsx
git commit -m "feat: widen ChartRendererProps with the full data payload for Phase 2 charts"
```

---

## Task 2: Multi-select ordered role field UI in `WidgetConfigPanel`

**Files:**
- Modify: `frontend/src/components/report/WidgetConfigPanel.tsx`

**Interfaces:**
- Produces: `multiRoleValues: Record<string, string[]>` state, seeded/reset/emitted alongside `roleValues`, for any `RoleField` with `multi: true`.
- Produces: config emission for a multi role uses the role name directly as the config key (e.g. `config.measures = [...]`) — there's no legacy-key concept for multi roles since none existed before this phase.
- Consumes (by Tasks 9, 13): `ROLE_SPECS.correlation_matrix` and `ROLE_SPECS.parallel_coordinates` declare a `measures` role with `multi: true`.

- [ ] **Step 1: Add multi-role state**

In `frontend/src/components/report/WidgetConfigPanel.tsx`, add near the existing `roleValues` state:
```ts
  const [multiRoleValues, setMultiRoleValues] = useState<Record<string, string[]>>(() => seedMultiRoleValues(cfg, wt))
  const toggleMultiRole = (role: string, value: string) => setMultiRoleValues(prev => {
    const current = prev[role] ?? []
    const next = current.includes(value) ? current.filter(v => v !== value) : [...current, value]
    return { ...prev, [role]: next }
  })
```
Add the seeding helper next to `seedRoleValues`:
```ts
function seedMultiRoleValues(cfg: Record<string, unknown>, wt: WidgetType): Record<string, string[]> {
  const values: Record<string, string[]> = {}
  for (const rf of (ROLE_SPECS[wt] ?? []).filter(rf => rf.multi)) {
    values[rf.role] = Array.isArray(cfg[rf.role]) ? (cfg[rf.role] as string[]) : []
  }
  return values
}
```

- [ ] **Step 2: Reset on widget/dataset change**

In the widget-change `useEffect`, add:
```ts
    setMultiRoleValues(seedMultiRoleValues(cfg, wt))
```
In the dataset-change handler (inside the multi-dataset `<select>`'s `onChange`), add:
```ts
            setMultiRoleValues(Object.fromEntries((ROLE_SPECS[wt] ?? []).filter(rf => rf.multi).map(rf => [rf.role, []])))
```

- [ ] **Step 3: Emit in config**

In the config-emitting `useEffect`'s `else` branch, after the existing single-role loop, add:
```ts
      for (const rf of (ROLE_SPECS[wt] ?? []).filter(rf => rf.multi)) {
        const vals = multiRoleValues[rf.role] ?? []
        if (vals.length > 0) config[rf.role] = vals
      }
```
Add `JSON.stringify(multiRoleValues)` to the emitting effect's dependency array.

- [ ] **Step 4: Render multi-select checkbox-list fields**

In the role-field-rendering loop (`(ROLE_SPECS[wt] ?? []).map(rf => ...)`), branch on `rf.multi`. Replace the loop body with:
```tsx
          {(ROLE_SPECS[wt] ?? []).map(rf => {
            if (rf.multi) {
              const selected = multiRoleValues[rf.role] ?? []
              const options = colOptions.filter(o => numCols.some(c => c.name === o.value))
              return (
                <div key={rf.role}>
                  {fld(rf.label ?? rf.role, (
                    <div style={{ maxHeight:130, overflowY:'auto', display:'flex', flexDirection:'column', gap:3, background:'var(--surface2)', border:'1px solid var(--border)', borderRadius:6, padding:'6px 8px' }}>
                      {options.map(o => {
                        const idx = selected.indexOf(o.value)
                        return (
                          <label key={o.value} style={{ display:'flex', alignItems:'center', gap:6, fontSize:12, cursor:'pointer' }}>
                            <input type="checkbox" checked={idx !== -1} onChange={() => toggleMultiRole(rf.role, o.value)} />
                            <span style={{ color: idx !== -1 ? 'var(--text)' : 'var(--muted)' }}>{o.label}</span>
                            {idx !== -1 && <span style={{ marginLeft:'auto', fontSize:9, color:'var(--accent)' }}>#{idx + 1}</span>}
                          </label>
                        )
                      })}
                    </div>
                  ))}
                </div>
              )
            }
            const options = (rf.role === 'measure' || rf.role === 'measure2')
              ? numCols.map(c => ({ value: c.name, label: c.name }))
              : colOptions
            const placeholder = rf.role === 'measure' ? '— count rows —' : rf.role === 'category2' ? '— none —' : '— select column —'
            return (
              <div key={rf.role}>
                {fld(rf.label ?? rf.role, sel(roleValues[rf.role] ?? '', v => setRole(rf.role, v), options, placeholder))}
              </div>
            )
          })}
```
Note: this renders multi-select fields with numeric-column-only options — correct for both `correlation_matrix` (measures for correlation) and `parallel_coordinates` (measures to bin), and the `#N` badge shows the click-order (= display order) so the ordering is visible to the user without a drag interaction.

- [ ] **Step 5: Verify no regression for the 16 existing chart types**

Run (from `frontend/`):
```bash
npm run build
```
Expected: exactly the 10 pre-existing errors. None of the 16 existing `ROLE_SPECS` entries have `multi: true`, so `seedMultiRoleValues`/`multiRoleValues` are empty objects for all of them and the emission loop is a no-op — trace through `bar` by hand in your report to confirm.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/report/WidgetConfigPanel.tsx
git commit -m "feat: add multi-select ordered role field UI for Phase 2 multi-measure charts"
```

---

## Task 3: Backend `shape_bubble` shaper

**Files:**
- Modify: `backend/app/services/widget_data.py`
- Test: `backend/tests/test_shape_bubble.py`

**Interfaces:**
- Produces: `shape_bubble(df: pd.DataFrame, config: dict) -> dict` — roles (via `resolve_roles`): `category` (required — one bubble per distinct value), `measure`/x (required), `measure2`/y (required), `size` (required), `color` (optional numeric, aggregated like x/y/size), `group` (optional categorical, taken via `.first()` per category — used for legend coloring, not aggregated). Returns `{"type": "bubble_series", "x": ..., "y": ..., "size": ..., "color": ..., "rows": [{"name": ..., "x": ..., "y": ..., "size": ..., "color"?: ..., "group"?: ...}, ...], "total": ...}`.
- Registers: `SHAPERS["bubble"] = shape_bubble`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_shape_bubble.py`:
```python
import pandas as pd
from app.services.widget_data import shape_bubble, SHAPERS


def sample_df():
    return pd.DataFrame({
        "region": ["East", "East", "West", "West", "North"],
        "product_line": ["Toy", "Novelty", "Toy", "Toy", "Novelty"],
        "revenue": [100, 50, 200, 100, 300],
        "cost":    [60, 20, 90, 40, 120],
        "units":   [10, 5, 20, 10, 30],
    })


def test_aggregates_one_bubble_per_category():
    config = {"roles": {"category": "region", "measure": "revenue", "measure2": "cost", "size": "units"}}
    result = shape_bubble(sample_df(), config)
    assert result["type"] == "bubble_series"
    by_name = {r["name"]: r for r in result["rows"]}
    assert by_name["East"]["x"] == 150
    assert by_name["East"]["y"] == 80
    assert by_name["East"]["size"] == 15
    assert by_name["West"]["x"] == 300


def test_color_role_aggregated_like_other_measures():
    config = {"roles": {"category": "region", "measure": "revenue", "measure2": "cost", "size": "units", "color": "revenue"}}
    result = shape_bubble(sample_df(), config)
    by_name = {r["name"]: r for r in result["rows"]}
    assert by_name["East"]["color"] == 150


def test_group_role_taken_via_first_not_aggregated():
    config = {"roles": {"category": "region", "measure": "revenue", "measure2": "cost", "size": "units", "group": "product_line"}}
    result = shape_bubble(sample_df(), config)
    by_name = {r["name"]: r for r in result["rows"]}
    assert by_name["East"]["group"] == "Toy"  # first row for East is Toy
    assert by_name["West"]["group"] == "Toy"
    assert by_name["North"]["group"] == "Novelty"


def test_missing_required_role_returns_empty():
    config = {"roles": {"category": "region", "measure": "revenue", "measure2": "cost"}}  # no size
    result = shape_bubble(sample_df(), config)
    assert result == {"type": "empty", "rows": [], "total": 0}


def test_duplicate_measure_roles_do_not_crash():
    """Regression guard: same house rule as Phase 1's Task 6/15 fixes — a repeated column
    across x/y/size/color must not produce a pandas duplicate-column crash."""
    config = {"roles": {"category": "region", "measure": "revenue", "measure2": "revenue", "size": "revenue"}}
    result = shape_bubble(sample_df(), config)
    by_name = {r["name"]: r for r in result["rows"]}
    assert by_name["East"]["x"] == 150
    assert by_name["East"]["y"] == 150
    assert by_name["East"]["size"] == 150


def test_registered_in_shapers():
    assert SHAPERS["bubble"] is shape_bubble
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`):
```bash
pytest tests/test_shape_bubble.py -v
```
Expected: FAIL — `ImportError: cannot import name 'shape_bubble'`.

- [ ] **Step 3: Implement `shape_bubble` and register it**

In `backend/app/services/widget_data.py`, add after `shape_xy_numeric`:
```python
def shape_bubble(df: pd.DataFrame, config: dict) -> dict:
    """roles: category (required), measure(x)/measure2(y)/size (all required),
    color (optional numeric, aggregated), group (optional categorical, via first())."""
    filters = config.get("filters", [])
    roles = resolve_roles(config)
    cat = roles.get("category")
    x = roles.get("measure")
    y = roles.get("measure2")
    size = roles.get("size")
    color = roles.get("color")
    group = roles.get("group")
    agg = (config.get("aggregation") or "avg").lower()
    limit = int(config.get("limit") or 100)
    df = _apply_filters(df, filters)
    if df.empty or not cat or not x or not y or not size:
        return {"type": "empty", "rows": [], "total": 0}
    if cat not in df.columns or x not in df.columns or y not in df.columns or size not in df.columns:
        return {"type": "empty", "rows": [], "total": 0}
    agg_fn = _pandas_agg_fn(agg)
    num_cols = list(dict.fromkeys([c for c in (x, y, size, color) if c and c in df.columns]))
    grouped = df.groupby(cat)[num_cols].agg(agg_fn).reset_index()
    if group and group in df.columns:
        grp_vals = df.groupby(cat)[group].first().reset_index()
        grouped = grouped.merge(grp_vals, on=cat, how="left")
    grouped = grouped.sort_values(cat).head(limit)
    rows = []
    for _, row in grouped.iterrows():
        r = {"name": _safe(row[cat]), "x": _safe(row[x]), "y": _safe(row[y]), "size": _safe(row[size])}
        if color and color in num_cols:
            r["color"] = _safe(row[color])
        if group and group in grouped.columns:
            r["group"] = _safe(row[group])
        rows.append(r)
    return {"type": "bubble_series", "x": x, "y": y, "size": size, "color": color, "rows": rows, "total": len(df)}
```
Update the `SHAPERS` dict, adding:
```python
    "bubble": shape_bubble,
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `backend/`):
```bash
pytest tests/test_shape_bubble.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Run the full backend suite**

```bash
pytest -v
```
Expected: all passing, no regressions.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/widget_data.py backend/tests/test_shape_bubble.py
git commit -m "feat: add shape_bubble shaper for Bubble Plot chart type"
```

---

## Task 4: Frontend Bubble Plot

**Files:**
- Create: `frontend/src/components/report/chartRenderers/BubbleChartRenderer.tsx`
- Modify: `frontend/src/components/report/chartRenderers/index.tsx`
- Modify: `frontend/src/types/report.ts`

**Interfaces:**
- Produces: `BubbleChartRenderer: React.FC<ChartRendererProps>`, registered as `CHART_RENDERERS.bubble`.
- Produces: `'bubble'` added to `WidgetType`, `WIDGET_CATALOG`, `ROLE_SPECS` (`category` required, `measure` label "X axis" required, `measure2` label "Y axis" required, `size` label "Bubble size" required, `color` label "Color (numeric, optional)" not required, `group` label "Group (legend, optional)" not required).

- [ ] **Step 1: Create the renderer**

Create `frontend/src/components/report/chartRenderers/BubbleChartRenderer.tsx`:
```tsx
import { ScatterChart, Scatter, ZAxis, XAxis, YAxis, CartesianGrid, Tooltip, Legend, Cell, ResponsiveContainer } from 'recharts'
import { COLORS, TT, fmtStr } from '../chartUtils'
import type { ChartRendererProps } from './types'

// v1 simplification: when a numeric `color` role is set (no `group`), interpolate a single
// accent-to-warning color ramp by normalized value. No gradient legend is rendered yet.
function colorForValue(v: number, min: number, max: number): string {
  const t = max > min ? (v - min) / (max - min) : 0
  const r = Math.round(108 + t * (251 - 108))
  const g = Math.round(143 + t * (191 - 143))
  const b = Math.round(255 + t * (36 - 255))
  return `rgb(${r},${g},${b})`
}

export default function BubbleChartRenderer({ rows, rtl, broadcasts, localSelected, onClickPoint, measureFmt, measure2Fmt }: ChartRendererProps) {
  const groups = Array.from(new Set(rows.map((r: any) => r.group).filter((g: unknown) => g != null)))
  const colorVals = rows.map((r: any) => r.color).filter((c: unknown) => typeof c === 'number')
  const colorMin = colorVals.length ? Math.min(...colorVals) : 0
  const colorMax = colorVals.length ? Math.max(...colorVals) : 1

  const fillFor = (r: any, i: number) => {
    if (r.group != null) return COLORS[groups.indexOf(r.group) % COLORS.length]
    if (typeof r.color === 'number') return colorForValue(r.color, colorMin, colorMax)
    return COLORS[i % COLORS.length]
  }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <ScatterChart margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis type="number" dataKey="x" name="x" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} reversed={rtl} tickFormatter={v => fmtStr(v, measureFmt)} />
        <YAxis type="number" dataKey="y" name="y" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} orientation={rtl ? 'right' : 'left'} tickFormatter={v => fmtStr(v, measure2Fmt)} />
        <ZAxis type="number" dataKey="size" range={[60, 600]} />
        <Tooltip contentStyle={TT} cursor={{ strokeDasharray: '3 3' }}
          formatter={(v: unknown, name: string) => [name === 'x' ? fmtStr(v, measureFmt) : name === 'y' ? fmtStr(v, measure2Fmt) : String(v), name]} />
        {groups.length > 0 && <Legend wrapperStyle={{ fontSize: 11 }} />}
        <Scatter data={rows} name="bubbles"
          onClick={broadcasts ? (d: any) => onClickPoint(d.name) : undefined}
          style={{ cursor: broadcasts ? 'pointer' : 'default' }}
        >
          {rows.map((r: any, i: number) => (
            <Cell key={i} fill={fillFor(r, i)} opacity={broadcasts && localSelected !== null && localSelected !== r.name ? 0.35 : 0.75} />
          ))}
        </Scatter>
      </ScatterChart>
    </ResponsiveContainer>
  )
}
```

- [ ] **Step 2: Register it**

In `frontend/src/components/report/chartRenderers/index.tsx`, add:
```tsx
import BubbleChartRenderer from './BubbleChartRenderer'
```
```tsx
  bubble: BubbleChartRenderer,
```

- [ ] **Step 3: Add `WidgetType`, `WIDGET_CATALOG`, `ROLE_SPECS` entries**

In `frontend/src/types/report.ts`:

1. Add `| 'bubble'` to `WidgetType`.
2. Add to `WIDGET_CATALOG`:
```ts
  { type: 'bubble' as WidgetType, label: 'Bubble Plot', category: 'Charts', icon: '◉', defaultW: 6, defaultH: 5 },
```
3. Add to `ROLE_SPECS`:
```ts
  bubble: [{ role: 'category', label: 'Dimension (one bubble per group)', required: true },
           { role: 'measure',  label: 'X axis',                          required: true },
           { role: 'measure2', label: 'Y axis',                          required: true },
           { role: 'size',     label: 'Bubble size',                     required: true },
           { role: 'color',    label: 'Color (numeric, optional)',       required: false },
           { role: 'group',    label: 'Group (legend, optional)',        required: false }],
```

- [ ] **Step 4: Add the icon**

Add `bubble:'◉'` to `WidgetConfigPanel.tsx`'s `widgetIcon()` map.

- [ ] **Step 5: Verify**

Run (from `frontend/`):
```bash
npm run build
```
Expected: exactly the 10 pre-existing errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/report/chartRenderers/BubbleChartRenderer.tsx frontend/src/components/report/chartRenderers/index.tsx frontend/src/types/report.ts frontend/src/components/report/WidgetConfigPanel.tsx
git commit -m "feat: add Bubble Plot chart type"
```

---

## Task 5: Backend `shape_bubble_animated` shaper (Bubble Change Plot)

**Files:**
- Modify: `backend/app/services/widget_data.py`
- Test: `backend/tests/test_shape_bubble_animated.py`

**Interfaces:**
- Produces: `shape_bubble_animated(df, config) -> dict` — same roles as `shape_bubble` plus `animation` (required — a category/date column whose distinct values become animation frames). Groups by `(category, animation)` instead of just `category`. Returns `{"type": "bubble_animated_series", "x":..., "y":..., "size":..., "color":..., "frames": [<sorted distinct animation values>], "rows": [{..bubble fields.., "frame": ...}, ...], "total": ...}`.
- Registers: `SHAPERS["bubble_change"] = shape_bubble_animated`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_shape_bubble_animated.py`:
```python
import pandas as pd
from app.services.widget_data import shape_bubble_animated, SHAPERS


def sample_df():
    return pd.DataFrame({
        "region": ["East", "East", "East", "East", "West", "West"],
        "year":   [2023, 2023, 2024, 2024, 2023, 2024],
        "revenue": [100, 50, 120, 60, 200, 220],
        "cost":    [60, 20, 70, 25, 90, 95],
        "units":   [10, 5, 12, 6, 20, 22],
    })


def test_groups_by_category_and_animation_frame():
    config = {"roles": {"category": "region", "measure": "revenue", "measure2": "cost", "size": "units", "animation": "year"}}
    result = shape_bubble_animated(sample_df(), config)
    assert result["type"] == "bubble_animated_series"
    assert result["frames"] == [2023, 2024]
    east_2023 = next(r for r in result["rows"] if r["name"] == "East" and r["frame"] == 2023)
    assert east_2023["x"] == 150  # 100 + 50


def test_missing_animation_role_returns_empty():
    config = {"roles": {"category": "region", "measure": "revenue", "measure2": "cost", "size": "units"}}
    result = shape_bubble_animated(sample_df(), config)
    assert result == {"type": "empty", "rows": [], "total": 0}


def test_registered_in_shapers():
    assert SHAPERS["bubble_change"] is shape_bubble_animated
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`):
```bash
pytest tests/test_shape_bubble_animated.py -v
```
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement `shape_bubble_animated` and register it**

In `backend/app/services/widget_data.py`, add after `shape_bubble`:
```python
def shape_bubble_animated(df: pd.DataFrame, config: dict) -> dict:
    """Same as shape_bubble but groups by (category, animation) — one bubble per
    category per animation frame, powering a client-side play/pause/scrub UI."""
    filters = config.get("filters", [])
    roles = resolve_roles(config)
    cat = roles.get("category")
    x = roles.get("measure")
    y = roles.get("measure2")
    size = roles.get("size")
    color = roles.get("color")
    anim = roles.get("animation")
    agg = (config.get("aggregation") or "avg").lower()
    limit = int(config.get("limit") or 500)
    df = _apply_filters(df, filters)
    if df.empty or not cat or not x or not y or not size or not anim:
        return {"type": "empty", "rows": [], "total": 0}
    if any(c not in df.columns for c in (cat, x, y, size, anim)):
        return {"type": "empty", "rows": [], "total": 0}
    agg_fn = _pandas_agg_fn(agg)
    num_cols = list(dict.fromkeys([c for c in (x, y, size, color) if c and c in df.columns]))
    grouped = df.groupby([cat, anim])[num_cols].agg(agg_fn).reset_index()
    grouped = grouped.sort_values([anim, cat]).head(limit)
    frames = sorted(df[anim].dropna().unique().tolist())
    rows = []
    for _, row in grouped.iterrows():
        r = {"name": _safe(row[cat]), "frame": _safe(row[anim]), "x": _safe(row[x]), "y": _safe(row[y]), "size": _safe(row[size])}
        if color and color in num_cols:
            r["color"] = _safe(row[color])
        rows.append(r)
    return {"type": "bubble_animated_series", "x": x, "y": y, "size": size, "color": color,
            "frames": [_safe(f) for f in frames], "rows": rows, "total": len(df)}
```
Update the `SHAPERS` dict, adding:
```python
    "bubble_change": shape_bubble_animated,
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `backend/`):
```bash
pytest tests/test_shape_bubble_animated.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Run the full backend suite**

```bash
pytest -v
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/widget_data.py backend/tests/test_shape_bubble_animated.py
git commit -m "feat: add shape_bubble_animated shaper for Bubble Change Plot"
```

---

## Task 6: Frontend Bubble Change Plot (animation player)

**Files:**
- Create: `frontend/src/components/report/chartRenderers/BubbleChangePlotRenderer.tsx`
- Modify: `frontend/src/components/report/chartRenderers/index.tsx`
- Modify: `frontend/src/types/report.ts`

**Interfaces:**
- Produces: `BubbleChangePlotRenderer: React.FC<ChartRendererProps>`, registered as `CHART_RENDERERS.bubble_change`. Reads `data.frames` (the full sorted frame list) and `rows` (already resolved by `WidgetRenderer`, but this renderer re-filters `data.rows` client-side by the currently-selected frame using local component state — a self-contained play/pause/scrub control, no config/backend round-trip per frame change).

- [ ] **Step 1: Create the renderer**

Create `frontend/src/components/report/chartRenderers/BubbleChangePlotRenderer.tsx`:
```tsx
import { useState, useEffect, useRef } from 'react'
import { ScatterChart, Scatter, ZAxis, XAxis, YAxis, CartesianGrid, Tooltip, Cell, ResponsiveContainer } from 'recharts'
import { COLORS, TT, fmtStr } from '../chartUtils'
import type { ChartRendererProps } from './types'

export default function BubbleChangePlotRenderer({ data, rtl, broadcasts, localSelected, onClickPoint, measureFmt, measure2Fmt }: ChartRendererProps) {
  const frames: unknown[] = data?.frames ?? []
  const allRows: any[] = data?.rows ?? []
  const [frameIdx, setFrameIdx] = useState(0)
  const [playing, setPlaying] = useState(false)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!playing || frames.length === 0) return
    timerRef.current = setInterval(() => {
      setFrameIdx(i => (i + 1) % frames.length)
    }, 900)
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [playing, frames.length])

  useEffect(() => { setFrameIdx(0); setPlaying(false) }, [frames.length])

  if (frames.length === 0) {
    return <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 12 }}>Configure widget to see data</div>
  }

  const currentFrame = frames[frameIdx]
  const rows = allRows.filter(r => r.frame === currentFrame)

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{ flex: 1, minHeight: 0 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis type="number" dataKey="x" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} reversed={rtl} tickFormatter={v => fmtStr(v, measureFmt)} />
            <YAxis type="number" dataKey="y" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} orientation={rtl ? 'right' : 'left'} tickFormatter={v => fmtStr(v, measure2Fmt)} />
            <ZAxis type="number" dataKey="size" range={[60, 600]} />
            <Tooltip contentStyle={TT} cursor={{ strokeDasharray: '3 3' }}
              formatter={(v: unknown, name: string) => [name === 'x' ? fmtStr(v, measureFmt) : name === 'y' ? fmtStr(v, measure2Fmt) : String(v), name]} />
            <Scatter data={rows} name="bubbles"
              onClick={broadcasts ? (d: any) => onClickPoint(d.name) : undefined}
              style={{ cursor: broadcasts ? 'pointer' : 'default' }}
            >
              {rows.map((r: any, i: number) => (
                <Cell key={i} fill={COLORS[i % COLORS.length]} opacity={broadcasts && localSelected !== null && localSelected !== r.name ? 0.35 : 0.75} />
              ))}
            </Scatter>
          </ScatterChart>
        </ResponsiveContainer>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 8px', borderTop: '1px solid var(--border)', flexShrink: 0 }}>
        <button className="btn" style={{ padding: '2px 8px', fontSize: 11 }} onClick={() => setPlaying(p => !p)}>{playing ? '⏸' : '▶'}</button>
        <input type="range" min={0} max={frames.length - 1} value={frameIdx}
          onChange={e => { setPlaying(false); setFrameIdx(Number(e.target.value)) }}
          style={{ flex: 1 }} />
        <span style={{ fontSize: 11, color: 'var(--muted)', minWidth: 48, textAlign: 'right' }}>{String(currentFrame)}</span>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Register it**

In `frontend/src/components/report/chartRenderers/index.tsx`, add:
```tsx
import BubbleChangePlotRenderer from './BubbleChangePlotRenderer'
```
```tsx
  bubble_change: BubbleChangePlotRenderer,
```

- [ ] **Step 3: Add `WidgetType`, `WIDGET_CATALOG`, `ROLE_SPECS` entries**

In `frontend/src/types/report.ts`:

1. Add `| 'bubble_change'` to `WidgetType`.
2. Add to `WIDGET_CATALOG`:
```ts
  { type: 'bubble_change' as WidgetType, label: 'Bubble Change Plot', category: 'Charts', icon: '◎', defaultW: 6, defaultH: 5 },
```
3. Add to `ROLE_SPECS`:
```ts
  bubble_change: [{ role: 'category',   label: 'Dimension (one bubble per group)', required: true },
                  { role: 'measure',    label: 'X axis',                          required: true },
                  { role: 'measure2',   label: 'Y axis',                          required: true },
                  { role: 'size',       label: 'Bubble size',                     required: true },
                  { role: 'color',      label: 'Color (numeric, optional)',       required: false },
                  { role: 'animation',  label: 'Animate by',                      required: true }],
```

- [ ] **Step 4: Add the icon**

Add `bubble_change:'◎'` to `WidgetConfigPanel.tsx`'s `widgetIcon()` map.

- [ ] **Step 5: Verify**

Run (from `frontend/`):
```bash
npm run build
```
Expected: exactly the 10 pre-existing errors.

Diff-review note for your report: this renderer reads `data.frames`/`data.rows` (the full payload, via Task 1's widening) rather than the pre-filtered `rows` prop, since it needs the complete unfiltered row set to filter client-side per frame — confirm this is exactly how it's written.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/report/chartRenderers/BubbleChangePlotRenderer.tsx frontend/src/components/report/chartRenderers/index.tsx frontend/src/types/report.ts frontend/src/components/report/WidgetConfigPanel.tsx
git commit -m "feat: add Bubble Change Plot chart type with play/pause/scrub animation"
```

---

## Task 7: Backend `compute_fit_line` regression helper + Bubble Plot integration

**Files:**
- Modify: `backend/app/services/widget_data.py`
- Test: `backend/tests/test_compute_fit_line.py`

**Interfaces:**
- Produces: `compute_fit_line(xs: list[float], ys: list[float], kind: str) -> list[dict] | None` — `kind` is `"linear"`, `"quadratic"`, `"cubic"`, or `"best_fit"`. Fits via `numpy.polyfit(xs, ys, degree)` (degree 1/2/3; `best_fit` tries all three and picks the highest R²), then evaluates the fitted polynomial at 20 evenly-spaced x-points across `[min(xs), max(xs)]`, returning `[{"x": ..., "y": ...}, ...]`. Returns `None` if fewer than `degree + 1` distinct x-values exist (can't fit).
- Modifies: `shape_bubble` — when `config.get("fit_line")` is a valid `kind` string, computes the fit line over the bubble rows' `(x, y)` pairs and adds `"fit_line": [...]` to the returned dict (or omits the key if fitting isn't possible).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_compute_fit_line.py`:
```python
from app.services.widget_data import compute_fit_line


def test_linear_fit_recovers_a_known_line():
    xs = [0, 1, 2, 3, 4]
    ys = [1, 3, 5, 7, 9]  # y = 2x + 1
    points = compute_fit_line(xs, ys, "linear")
    assert points is not None
    assert len(points) == 20
    # endpoints should closely match the known line
    assert abs(points[0]["y"] - (2 * points[0]["x"] + 1)) < 0.01
    assert abs(points[-1]["y"] - (2 * points[-1]["x"] + 1)) < 0.01


def test_quadratic_fit_recovers_a_known_parabola():
    xs = [-2, -1, 0, 1, 2]
    ys = [4, 1, 0, 1, 4]  # y = x^2
    points = compute_fit_line(xs, ys, "quadratic")
    mid = points[len(points) // 2]
    assert abs(mid["y"] - mid["x"] ** 2) < 0.5


def test_best_fit_picks_highest_r_squared():
    xs = [0, 1, 2, 3, 4]
    ys = [1, 3, 5, 7, 9]  # perfectly linear
    points = compute_fit_line(xs, ys, "best_fit")
    assert points is not None
    assert abs(points[0]["y"] - (2 * points[0]["x"] + 1)) < 0.5


def test_insufficient_points_returns_none():
    assert compute_fit_line([1], [1], "linear") is None
    assert compute_fit_line([], [], "linear") is None


def test_invalid_kind_returns_none():
    assert compute_fit_line([1, 2, 3], [1, 2, 3], "pspline") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`):
```bash
pytest tests/test_compute_fit_line.py -v
```
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement `compute_fit_line` and wire it into `shape_bubble`**

In `backend/app/services/widget_data.py`, add after `shape_bubble_animated`:
```python
_FIT_DEGREES = {"linear": 1, "quadratic": 2, "cubic": 3}


def _r_squared(xs: np.ndarray, ys: np.ndarray, coeffs: np.ndarray) -> float:
    fitted = np.polyval(coeffs, xs)
    ss_res = np.sum((ys - fitted) ** 2)
    ss_tot = np.sum((ys - ys.mean()) ** 2)
    return 1 - ss_res / ss_tot if ss_tot > 0 else 0.0


def compute_fit_line(xs: list, ys: list, kind: str) -> list[dict] | None:
    """Fit linear/quadratic/cubic (numpy.polyfit) or best_fit (highest R^2 among the three)
    and return 20 evenly-spaced {x, y} points across the observed x-range. None if it can't fit."""
    xs_arr = np.array(xs, dtype=float)
    ys_arr = np.array(ys, dtype=float)
    if len(xs_arr) < 2 or len(set(xs_arr.tolist())) < 2:
        return None

    def _fit(degree: int):
        if len(set(xs_arr.tolist())) < degree + 1:
            return None
        return np.polyfit(xs_arr, ys_arr, degree)

    if kind in _FIT_DEGREES:
        coeffs = _fit(_FIT_DEGREES[kind])
        if coeffs is None:
            return None
    elif kind == "best_fit":
        candidates = [(deg, _fit(deg)) for deg in (1, 2, 3)]
        candidates = [(deg, c) for deg, c in candidates if c is not None]
        if not candidates:
            return None
        _, coeffs = max(candidates, key=lambda dc: _r_squared(xs_arr, ys_arr, dc[1]))
    else:
        return None

    x_min, x_max = float(xs_arr.min()), float(xs_arr.max())
    if x_min == x_max:
        return None
    step = (x_max - x_min) / 19
    points = []
    for i in range(20):
        x = x_min + i * step
        y = float(np.polyval(coeffs, x))
        points.append({"x": _safe(x), "y": _safe(y)})
    return points
```
Then modify `shape_bubble` — right before its `return {"type": "bubble_series", ...}` statement, insert:
```python
    result = {"type": "bubble_series", "x": x, "y": y, "size": size, "color": color, "rows": rows, "total": len(df)}
    fit_kind = config.get("fit_line")
    if fit_kind:
        fit_points = compute_fit_line([r["x"] for r in rows], [r["y"] for r in rows], fit_kind)
        if fit_points:
            result["fit_line"] = fit_points
    return result
```
(replacing the original `return {"type": "bubble_series", ...}` line — the dict is now built as `result` first, optionally augmented, then returned.)

- [ ] **Step 4: Run tests to verify they pass**

Run (from `backend/`):
```bash
pytest tests/test_compute_fit_line.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Add a bubble-shaper test confirming the integration**

Add to `backend/tests/test_shape_bubble.py`:
```python
def test_fit_line_included_when_requested():
    config = {"roles": {"category": "region", "measure": "revenue", "measure2": "cost", "size": "units"}, "fit_line": "linear"}
    result = shape_bubble(sample_df(), config)
    assert "fit_line" in result
    assert len(result["fit_line"]) == 20


def test_fit_line_omitted_when_not_requested():
    config = {"roles": {"category": "region", "measure": "revenue", "measure2": "cost", "size": "units"}}
    result = shape_bubble(sample_df(), config)
    assert "fit_line" not in result
```
Run (from `backend/`):
```bash
pytest tests/test_shape_bubble.py -v
```
Expected: 8 passed (6 original + 2 new).

- [ ] **Step 6: Run the full backend suite**

```bash
pytest -v
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/widget_data.py backend/tests/test_compute_fit_line.py backend/tests/test_shape_bubble.py
git commit -m "feat: add compute_fit_line regression helper, wire into shape_bubble"
```

---

## Task 8: Frontend Fit Line overlay on Bubble Plot

**Files:**
- Modify: `frontend/src/components/report/chartRenderers/BubbleChartRenderer.tsx`
- Modify: `frontend/src/components/report/WidgetConfigPanel.tsx`

**Interfaces:**
- Modifies: `BubbleChartRenderer` reads `data.fit_line` (present only when Task 7's backend integration computed one) and overlays a `Line` through those points on the same `x`/`y` axes.
- Produces: a `Fit Line` dropdown field in `WidgetConfigPanel.tsx`, shown only for `wt === 'bubble'`, emitting `config.fit_line`.

- [ ] **Step 1: Add the Fit Line dropdown to the config panel**

In `frontend/src/components/report/WidgetConfigPanel.tsx`:

1. Add state:
```ts
  const [fitLine, setFitLine] = useState<string>((cfg.fit_line as string) ?? '')
```
2. Add to the widget-change reset `useEffect`:
```ts
    setFitLine((cfg.fit_line as string) ?? '')
```
3. Add to the config-emission object:
```ts
      if (wt === 'bubble' && fitLine) config.fit_line = fitLine
```
4. Add `fitLine` to the emitting `useEffect`'s dependency array.
5. Add the field JSX, gated by widget type, near the other one-off fields (Bins/Baseline):
```tsx
          {wt === 'bubble' && fld('Fit Line',
            sel(fitLine, setFitLine, [
              { value: 'linear',    label: 'Linear' },
              { value: 'quadratic', label: 'Quadratic' },
              { value: 'cubic',     label: 'Cubic' },
              { value: 'best_fit',  label: 'Best Fit' },
            ], '— none —')
          )}
```

- [ ] **Step 2: Overlay the fit line in the renderer**

In `frontend/src/components/report/chartRenderers/BubbleChartRenderer.tsx`:

1. Add `Line` to the recharts import:
```tsx
import { ScatterChart, Scatter, ZAxis, XAxis, YAxis, CartesianGrid, Tooltip, Legend, Cell, Line, ResponsiveContainer } from 'recharts'
```
2. Destructure `data` from props (add to the function signature): `{ rows, data, rtl, broadcasts, localSelected, onClickPoint, measureFmt, measure2Fmt }`.
3. Right before the closing `</ScatterChart>`, add:
```tsx
        {data?.fit_line && (
          <Line data={data.fit_line} dataKey="y" type="monotone" stroke="var(--muted)" strokeWidth={1.5} strokeDasharray="4 3" dot={false} legendType="none" isAnimationActive={false} />
        )}
```
Note: mixing a `Scatter` (using the chart-level implicit `x`/`y`/`size` dataKeys) with a `Line` that has its OWN `data` prop works in Recharts' `ScatterChart` because `ScatterChart` is built on the same `ComposedChart` internals — both series share the same `XAxis`/`YAxis` scale, and `Line`'s own `data` prop overrides the chart-level data for that one series.

- [ ] **Step 3: Verify**

Run (from `frontend/`):
```bash
npm run build
```
Expected: exactly the 10 pre-existing errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/report/chartRenderers/BubbleChartRenderer.tsx frontend/src/components/report/WidgetConfigPanel.tsx
git commit -m "feat: overlay fit line on Bubble Plot with config-panel selector"
```

---

## Task 9: Backend `shape_correlation_matrix` shaper

**Files:**
- Modify: `backend/app/services/widget_data.py`
- Test: `backend/tests/test_shape_correlation_matrix.py`

**Interfaces:**
- Produces: `shape_correlation_matrix(df, config) -> dict` — reads `config["measures"]` (a list of column names, NOT a `resolve_roles` role — this is the multi-select field from Task 2, emitted directly as `config.measures`). Computes pairwise Pearson correlation via `df[measures].corr()`. Returns `{"type": "matrix", "measures": [...], "matrix": [[<float>, ...], ...], "total": ...}` — `matrix[i][j]` is the correlation between `measures[i]` and `measures[j]` (symmetric, diagonal is 1.0).
- Registers: `SHAPERS["correlation_matrix"] = shape_correlation_matrix`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_shape_correlation_matrix.py`:
```python
import pandas as pd
from app.services.widget_data import shape_correlation_matrix, SHAPERS


def sample_df():
    return pd.DataFrame({
        "a": [1, 2, 3, 4, 5],
        "b": [2, 4, 6, 8, 10],     # perfectly correlated with a
        "c": [5, 4, 3, 2, 1],      # perfectly anti-correlated with a
        "unrelated": ["x", "y", "z", "x", "y"],
    })


def test_matrix_is_symmetric_with_unit_diagonal():
    result = shape_correlation_matrix(sample_df(), {"measures": ["a", "b", "c"]})
    assert result["type"] == "matrix"
    assert result["measures"] == ["a", "b", "c"]
    m = result["matrix"]
    assert m[0][0] == 1.0 and m[1][1] == 1.0 and m[2][2] == 1.0
    assert abs(m[0][1] - m[1][0]) < 1e-9


def test_perfect_positive_and_negative_correlation():
    result = shape_correlation_matrix(sample_df(), {"measures": ["a", "b", "c"]})
    m = result["matrix"]
    assert abs(m[0][1] - 1.0) < 1e-9    # a vs b: perfectly correlated
    assert abs(m[0][2] - (-1.0)) < 1e-9  # a vs c: perfectly anti-correlated


def test_fewer_than_two_measures_returns_empty():
    result = shape_correlation_matrix(sample_df(), {"measures": ["a"]})
    assert result == {"type": "empty", "rows": [], "total": 0}


def test_missing_measures_key_returns_empty():
    result = shape_correlation_matrix(sample_df(), {})
    assert result == {"type": "empty", "rows": [], "total": 0}


def test_nonexistent_column_in_measures_is_dropped_not_crashed():
    result = shape_correlation_matrix(sample_df(), {"measures": ["a", "b", "does_not_exist"]})
    assert result["measures"] == ["a", "b"]


def test_duplicate_measure_names_deduped():
    """House rule: repeated column selection must never crash a pandas column operation."""
    result = shape_correlation_matrix(sample_df(), {"measures": ["a", "a", "b"]})
    assert result["measures"] == ["a", "b"]


def test_registered_in_shapers():
    assert SHAPERS["correlation_matrix"] is shape_correlation_matrix
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`):
```bash
pytest tests/test_shape_correlation_matrix.py -v
```
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement `shape_correlation_matrix` and register it**

In `backend/app/services/widget_data.py`, add after `compute_fit_line`:
```python
def shape_correlation_matrix(df: pd.DataFrame, config: dict) -> dict:
    """config keys: measures (list[str], the multi-select role — not resolved via resolve_roles,
    since it's a plain multi-value list emitted directly by WidgetConfigPanel), filters."""
    filters = config.get("filters", [])
    measures = list(dict.fromkeys(config.get("measures") or []))
    df = _apply_filters(df, filters)
    measures = [m for m in measures if m in df.columns]
    if df.empty or len(measures) < 2:
        return {"type": "empty", "rows": [], "total": 0}
    corr = df[measures].corr(method="pearson")
    matrix = [[_safe(corr.loc[m1, m2]) for m2 in measures] for m1 in measures]
    return {"type": "matrix", "measures": measures, "matrix": matrix, "total": len(df)}
```
Update the `SHAPERS` dict, adding:
```python
    "correlation_matrix": shape_correlation_matrix,
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `backend/`):
```bash
pytest tests/test_shape_correlation_matrix.py -v
```
Expected: 7 passed.

- [ ] **Step 5: Run the full backend suite**

```bash
pytest -v
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/widget_data.py backend/tests/test_shape_correlation_matrix.py
git commit -m "feat: add shape_correlation_matrix shaper for Correlation Matrix chart type"
```

---

## Task 10: Frontend Correlation Matrix

**Files:**
- Create: `frontend/src/components/report/chartRenderers/CorrelationMatrixRenderer.tsx`
- Modify: `frontend/src/components/report/chartRenderers/index.tsx`
- Modify: `frontend/src/types/report.ts`

**Interfaces:**
- Produces: `CorrelationMatrixRenderer: React.FC<ChartRendererProps>`, registered as `CHART_RENDERERS.correlation_matrix`. Reads `data.measures`/`data.matrix` (NOT `rows` — this is the first renderer to actually need Task 1's `data` widening). Custom hand-built SVG/HTML grid — Recharts has no matrix/heatmap primitive.
- Produces: `'correlation_matrix'` added to `WidgetType`/`WIDGET_CATALOG`/`ROLE_SPECS` (a single `measures` role, `multi: true`, `required: true`).

- [ ] **Step 1: Create the renderer**

Create `frontend/src/components/report/chartRenderers/CorrelationMatrixRenderer.tsx`:
```tsx
import type { ChartRendererProps } from './types'

// Diverging color scale: strong negative -> red, 0 -> neutral surface, strong positive -> accent blue.
function cellColor(v: number): string {
  const t = Math.max(-1, Math.min(1, v))
  if (t >= 0) {
    const alpha = 0.12 + t * 0.75
    return `rgba(108,143,255,${alpha})`
  }
  const alpha = 0.12 + -t * 0.75
  return `rgba(248,113,113,${alpha})`
}

export default function CorrelationMatrixRenderer({ data, rtl }: ChartRendererProps) {
  const measures: string[] = data?.measures ?? []
  const matrix: number[][] = data?.matrix ?? []

  if (measures.length < 2) {
    return <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 12 }}>Select at least 2 measures</div>
  }

  return (
    <div dir={rtl ? 'rtl' : undefined} style={{ height: '100%', overflow: 'auto', padding: 4 }}>
      <table style={{ borderCollapse: 'collapse', fontSize: 11, width: '100%' }}>
        <thead>
          <tr>
            <th style={{ padding: 4 }}></th>
            {measures.map(m => (
              <th key={m} style={{ padding: 4, fontWeight: 600, color: 'var(--muted)', writingMode: 'vertical-rl', transform: 'rotate(180deg)', maxHeight: 90 }}>{m}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {measures.map((rowMeasure, i) => (
            <tr key={rowMeasure}>
              <td style={{ padding: 4, fontWeight: 600, color: 'var(--muted)', whiteSpace: 'nowrap' }}>{rowMeasure}</td>
              {measures.map((colMeasure, j) => {
                const v = matrix[i]?.[j] ?? 0
                return (
                  <td key={colMeasure} title={`${rowMeasure} × ${colMeasure}: ${v.toFixed(3)}`}
                    style={{ padding: 0, border: '1px solid var(--border)' }}>
                    <div style={{ background: cellColor(v), width: '100%', height: 36, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, color: 'var(--text)' }}>
                      {v.toFixed(2)}
                    </div>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
```

- [ ] **Step 2: Register it**

In `frontend/src/components/report/chartRenderers/index.tsx`, add:
```tsx
import CorrelationMatrixRenderer from './CorrelationMatrixRenderer'
```
```tsx
  correlation_matrix: CorrelationMatrixRenderer,
```

- [ ] **Step 3: Add `WidgetType`, `WIDGET_CATALOG`, `ROLE_SPECS` entries**

In `frontend/src/types/report.ts`:

1. Add `| 'correlation_matrix'` to `WidgetType`.
2. Add to `WIDGET_CATALOG`:
```ts
  { type: 'correlation_matrix' as WidgetType, label: 'Correlation Matrix', category: 'Charts', icon: '▦', defaultW: 6, defaultH: 6 },
```
3. Add to `ROLE_SPECS`:
```ts
  correlation_matrix: [{ role: 'measures', label: 'Measures', multi: true, required: true }],
```

- [ ] **Step 4: Add the icon**

Add `correlation_matrix:'▦'` to `WidgetConfigPanel.tsx`'s `widgetIcon()` map.

- [ ] **Step 5: Verify**

Run (from `frontend/`):
```bash
npm run build
```
Expected: exactly the 10 pre-existing errors.

Confirm in your report: this renderer reads exclusively from `data` (via Task 1's widening), never from `rows` — the first of the 17 chart types (16 existing + this one) to do so.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/report/chartRenderers/CorrelationMatrixRenderer.tsx frontend/src/components/report/chartRenderers/index.tsx frontend/src/types/report.ts frontend/src/components/report/WidgetConfigPanel.tsx
git commit -m "feat: add Correlation Matrix chart type"
```

---

## Task 11: Backend `shape_heatmap` shaper

**Files:**
- Modify: `backend/app/services/widget_data.py`
- Test: `backend/tests/test_shape_heatmap.py`

**Interfaces:**
- Produces: `shape_heatmap(df, config) -> dict` — roles: `category` (required, rows of the grid), `category2` (required, columns of the grid), `measure` (required, the color-scaled cell value; aggregated per `config["aggregation"]`, default `sum`). Returns `{"type": "heatmap", "rows_axis": [...distinct category values...], "cols_axis": [...distinct category2 values...], "cells": [[<float|None>, ...], ...], "min": <float>, "max": <float>, "total": ...}` — `cells[i][j]` is the aggregated measure for `(rows_axis[i], cols_axis[j])`, `None` where that combination doesn't exist in the data.
- Registers: `SHAPERS["heatmap"] = shape_heatmap`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_shape_heatmap.py`:
```python
import pandas as pd
from app.services.widget_data import shape_heatmap, SHAPERS


def sample_df():
    return pd.DataFrame({
        "region":  ["East", "East", "West", "West"],
        "product": ["Toy", "Novelty", "Toy", "Toy"],
        "revenue": [100, 50, 200, 100],
    })


def test_builds_a_grid_of_aggregated_values():
    config = {"roles": {"category": "region", "category2": "product", "measure": "revenue"}}
    result = shape_heatmap(sample_df(), config)
    assert result["type"] == "heatmap"
    assert set(result["rows_axis"]) == {"East", "West"}
    assert set(result["cols_axis"]) == {"Toy", "Novelty"}
    ri = result["rows_axis"].index("West")
    ci = result["cols_axis"].index("Toy")
    assert result["cells"][ri][ci] == 300  # West/Toy: 200 + 100


def test_missing_combination_is_none():
    config = {"roles": {"category": "region", "category2": "product", "measure": "revenue"}}
    result = shape_heatmap(sample_df(), config)
    ri = result["rows_axis"].index("West")
    ci = result["cols_axis"].index("Novelty")
    assert result["cells"][ri][ci] is None  # West/Novelty never occurs


def test_min_max_reflect_actual_cell_range():
    config = {"roles": {"category": "region", "category2": "product", "measure": "revenue"}}
    result = shape_heatmap(sample_df(), config)
    assert result["min"] == 50
    assert result["max"] == 300


def test_missing_required_role_returns_empty():
    config = {"roles": {"category": "region", "measure": "revenue"}}  # no category2
    result = shape_heatmap(sample_df(), config)
    assert result == {"type": "empty", "rows": [], "total": 0}


def test_registered_in_shapers():
    assert SHAPERS["heatmap"] is shape_heatmap
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`):
```bash
pytest tests/test_shape_heatmap.py -v
```
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement `shape_heatmap` and register it**

In `backend/app/services/widget_data.py`, add after `shape_correlation_matrix`:
```python
def shape_heatmap(df: pd.DataFrame, config: dict) -> dict:
    """roles: category (rows), category2 (columns), measure (cell value, aggregated)."""
    filters = config.get("filters", [])
    roles = resolve_roles(config)
    cat = roles.get("category")
    cat2 = roles.get("category2")
    meas = roles.get("measure")
    agg = (config.get("aggregation") or "sum").lower()
    df = _apply_filters(df, filters)
    if df.empty or not cat or not cat2 or not meas:
        return {"type": "empty", "rows": [], "total": 0}
    if cat not in df.columns or cat2 not in df.columns or meas not in df.columns:
        return {"type": "empty", "rows": [], "total": 0}
    agg_fn = _pandas_agg_fn(agg)
    pivot = df.groupby([cat, cat2])[meas].agg(agg_fn).unstack(cat2)
    rows_axis = [str(v) for v in pivot.index.tolist()]
    cols_axis = [str(v) for v in pivot.columns.tolist()]
    cells = [[_safe(v) if pd.notna(v) else None for v in row] for row in pivot.values]
    flat_vals = [v for row in cells for v in row if v is not None]
    return {
        "type": "heatmap", "rows_axis": rows_axis, "cols_axis": cols_axis, "cells": cells,
        "min": min(flat_vals) if flat_vals else 0, "max": max(flat_vals) if flat_vals else 0,
        "total": len(df),
    }
```
Update the `SHAPERS` dict, adding:
```python
    "heatmap": shape_heatmap,
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `backend/`):
```bash
pytest tests/test_shape_heatmap.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Run the full backend suite**

```bash
pytest -v
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/widget_data.py backend/tests/test_shape_heatmap.py
git commit -m "feat: add shape_heatmap shaper for Heat Map chart type"
```

---

## Task 12: Frontend Heat Map

**Files:**
- Create: `frontend/src/components/report/chartRenderers/HeatMapRenderer.tsx`
- Modify: `frontend/src/components/report/chartRenderers/index.tsx`
- Modify: `frontend/src/types/report.ts`

**Interfaces:**
- Produces: `HeatMapRenderer: React.FC<ChartRendererProps>`, registered as `CHART_RENDERERS.heatmap`. Reads `data.rows_axis`/`data.cols_axis`/`data.cells`/`data.min`/`data.max`.
- Produces: `'heatmap'` added to `WidgetType`/`WIDGET_CATALOG`/`ROLE_SPECS` (`category`, `category2`, `measure`, all required).

- [ ] **Step 1: Create the renderer**

Create `frontend/src/components/report/chartRenderers/HeatMapRenderer.tsx`:
```tsx
import { fmtStr } from '../chartUtils'
import type { ChartRendererProps } from './types'

function cellColor(v: number, min: number, max: number): string {
  const t = max > min ? (v - min) / (max - min) : 0.5
  const alpha = 0.1 + t * 0.85
  return `rgba(108,143,255,${alpha})`
}

export default function HeatMapRenderer({ data, rtl, measureFmt }: ChartRendererProps) {
  const rowsAxis: string[] = data?.rows_axis ?? []
  const colsAxis: string[] = data?.cols_axis ?? []
  const cells: (number | null)[][] = data?.cells ?? []
  const min: number = data?.min ?? 0
  const max: number = data?.max ?? 1

  if (rowsAxis.length === 0 || colsAxis.length === 0) {
    return <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 12 }}>Configure widget to see data</div>
  }

  return (
    <div dir={rtl ? 'rtl' : undefined} style={{ height: '100%', overflow: 'auto', padding: 4 }}>
      <table style={{ borderCollapse: 'collapse', fontSize: 11, width: '100%' }}>
        <thead>
          <tr>
            <th style={{ padding: 4 }}></th>
            {colsAxis.map(c => (
              <th key={c} style={{ padding: 4, fontWeight: 600, color: 'var(--muted)', whiteSpace: 'nowrap' }}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rowsAxis.map((r, i) => (
            <tr key={r}>
              <td style={{ padding: 4, fontWeight: 600, color: 'var(--muted)', whiteSpace: 'nowrap' }}>{r}</td>
              {colsAxis.map((c, j) => {
                const v = cells[i]?.[j]
                return (
                  <td key={c} title={v == null ? 'No data' : `${r} × ${c}: ${fmtStr(v, measureFmt)}`}
                    style={{ padding: 0, border: '1px solid var(--border)' }}>
                    <div style={{ background: v == null ? 'var(--surface2)' : cellColor(v, min, max), width: '100%', height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, color: 'var(--text)' }}>
                      {v == null ? '—' : fmtStr(v, measureFmt)}
                    </div>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
```

- [ ] **Step 2: Register it**

In `frontend/src/components/report/chartRenderers/index.tsx`, add:
```tsx
import HeatMapRenderer from './HeatMapRenderer'
```
```tsx
  heatmap: HeatMapRenderer,
```

- [ ] **Step 3: Add `WidgetType`, `WIDGET_CATALOG`, `ROLE_SPECS` entries**

In `frontend/src/types/report.ts`:

1. Add `| 'heatmap'` to `WidgetType`.
2. Add to `WIDGET_CATALOG` (icon `'▩'`, distinct from `dual_axis_bar_line`'s `'▧'`):
```ts
  { type: 'heatmap' as WidgetType, label: 'Heat Map', category: 'Charts', icon: '▩', defaultW: 6, defaultH: 6 },
```
3. Add to `ROLE_SPECS`:
```ts
  heatmap: [{ role: 'category',  label: 'Rows (Y-axis)',    required: true },
            { role: 'category2', label: 'Columns (X-axis)', required: true },
            { role: 'measure',   label: 'Cell value',       required: true }],
```

- [ ] **Step 4: Add the icon**

Add `heatmap:'▩'` to `WidgetConfigPanel.tsx`'s `widgetIcon()` map, matching the `WIDGET_CATALOG` icon from Step 3.

- [ ] **Step 5: Verify**

Run (from `frontend/`):
```bash
npm run build
```
Expected: exactly the 10 pre-existing errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/report/chartRenderers/HeatMapRenderer.tsx frontend/src/components/report/chartRenderers/index.tsx frontend/src/types/report.ts frontend/src/components/report/WidgetConfigPanel.tsx
git commit -m "feat: add Heat Map chart type"
```

---

## Task 13: Backend `shape_parallel_coordinates` shaper

**Files:**
- Modify: `backend/app/services/widget_data.py`
- Test: `backend/tests/test_shape_parallel_coordinates.py`

**Interfaces:**
- Produces: `shape_parallel_coordinates(df, config) -> dict` — reads `config["measures"]` (multi-select, list of numeric column names, order preserved). For each measure, computes `min`/`max` across the filtered data. For each row (capped at `config["limit"]`, default 200 — this is a detail-level plot, not aggregated), returns a polyline as normalized `[0,1]` positions per axis (so the frontend can map directly to pixel Y without re-deriving scale). Returns `{"type": "parallel_coordinates", "axes": [{"name": ..., "min": ..., "max": ...}, ...], "lines": [[<0..1 per axis>, ...], ...], "total": ...}`.
- Registers: `SHAPERS["parallel_coordinates"] = shape_parallel_coordinates`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_shape_parallel_coordinates.py`:
```python
import pandas as pd
from app.services.widget_data import shape_parallel_coordinates, SHAPERS


def sample_df():
    return pd.DataFrame({
        "revenue": [0, 50, 100],
        "cost":    [0, 25, 50],
        "units":   [0, 5, 10],
    })


def test_normalizes_each_axis_to_0_1():
    result = shape_parallel_coordinates(sample_df(), {"measures": ["revenue", "cost", "units"]})
    assert result["type"] == "parallel_coordinates"
    assert [a["name"] for a in result["axes"]] == ["revenue", "cost", "units"]
    assert result["axes"][0]["min"] == 0 and result["axes"][0]["max"] == 100
    # first row is all-zero -> normalized to 0.0 on every axis
    assert result["lines"][0] == [0.0, 0.0, 0.0]
    # last row is all-max -> normalized to 1.0 on every axis
    assert result["lines"][2] == [1.0, 1.0, 1.0]
    # middle row is exactly halfway on every axis
    assert result["lines"][1] == [0.5, 0.5, 0.5]


def test_respects_measure_order_not_alphabetical():
    result = shape_parallel_coordinates(sample_df(), {"measures": ["units", "revenue"]})
    assert [a["name"] for a in result["axes"]] == ["units", "revenue"]


def test_fewer_than_two_measures_returns_empty():
    result = shape_parallel_coordinates(sample_df(), {"measures": ["revenue"]})
    assert result == {"type": "empty", "rows": [], "total": 0}


def test_respects_limit():
    df = pd.DataFrame({"a": list(range(500)), "b": list(range(500))})
    result = shape_parallel_coordinates(df, {"measures": ["a", "b"], "limit": 10})
    assert len(result["lines"]) == 10


def test_duplicate_measures_deduped():
    result = shape_parallel_coordinates(sample_df(), {"measures": ["revenue", "revenue", "cost"]})
    assert [a["name"] for a in result["axes"]] == ["revenue", "cost"]


def test_registered_in_shapers():
    assert SHAPERS["parallel_coordinates"] is shape_parallel_coordinates
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `backend/`):
```bash
pytest tests/test_shape_parallel_coordinates.py -v
```
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement `shape_parallel_coordinates` and register it**

In `backend/app/services/widget_data.py`, add after `shape_heatmap`:
```python
def shape_parallel_coordinates(df: pd.DataFrame, config: dict) -> dict:
    """config keys: measures (list[str], ordered, multi-select — plain list, not a resolve_roles
    role), limit (default 200, this is detail-level, not aggregated), filters."""
    filters = config.get("filters", [])
    measures = list(dict.fromkeys(config.get("measures") or []))
    limit = int(config.get("limit") or 200)
    df = _apply_filters(df, filters)
    measures = [m for m in measures if m in df.columns]
    if df.empty or len(measures) < 2:
        return {"type": "empty", "rows": [], "total": 0}
    sub = df[measures].dropna().head(limit)
    axes = []
    bounds = {}
    for m in measures:
        lo, hi = float(sub[m].min()), float(sub[m].max())
        axes.append({"name": m, "min": _safe(lo), "max": _safe(hi)})
        bounds[m] = (lo, hi)
    lines = []
    for _, row in sub.iterrows():
        line = []
        for m in measures:
            lo, hi = bounds[m]
            norm = 0.5 if hi == lo else (float(row[m]) - lo) / (hi - lo)
            line.append(round(norm, 4))
        lines.append(line)
    return {"type": "parallel_coordinates", "axes": axes, "lines": lines, "total": len(df)}
```
Update the `SHAPERS` dict, adding:
```python
    "parallel_coordinates": shape_parallel_coordinates,
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `backend/`):
```bash
pytest tests/test_shape_parallel_coordinates.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Run the full backend suite**

```bash
pytest -v
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/widget_data.py backend/tests/test_shape_parallel_coordinates.py
git commit -m "feat: add shape_parallel_coordinates shaper for Parallel Coordinates chart type"
```

---

## Task 14: Frontend Parallel Coordinates Plot

**Files:**
- Create: `frontend/src/components/report/chartRenderers/ParallelCoordinatesRenderer.tsx`
- Modify: `frontend/src/components/report/chartRenderers/index.tsx`
- Modify: `frontend/src/types/report.ts`

**Interfaces:**
- Produces: `ParallelCoordinatesRenderer: React.FC<ChartRendererProps>`, registered as `CHART_RENDERERS.parallel_coordinates`. Reads `data.axes`/`data.lines`. Hand-built SVG — Recharts has no parallel-coordinates primitive.
- Produces: `'parallel_coordinates'` added to `WidgetType`/`WIDGET_CATALOG`/`ROLE_SPECS` (a single `measures` role, `multi: true`, `required: true`).

- [ ] **Step 1: Create the renderer**

Create `frontend/src/components/report/chartRenderers/ParallelCoordinatesRenderer.tsx`:
```tsx
import { fmtStr } from '../chartUtils'
import type { ChartRendererProps } from './types'

const MARGIN_TOP = 24
const MARGIN_BOTTOM = 20
const LABEL_HEIGHT = 14

export default function ParallelCoordinatesRenderer({ data, rtl, measureFmt }: ChartRendererProps) {
  const axes: { name: string; min: number; max: number }[] = data?.axes ?? []
  const lines: number[][] = data?.lines ?? []

  if (axes.length < 2) {
    return <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 12 }}>Select at least 2 measures</div>
  }

  const orderedAxes = rtl ? [...axes].reverse() : axes
  const orderedLines = rtl ? lines.map(l => [...l].reverse()) : lines

  return (
    <div style={{ height: '100%', width: '100%' }}>
      <svg width="100%" height="100%" viewBox="0 0 1000 400" preserveAspectRatio="none" style={{ display: 'block' }}>
        {orderedAxes.map((axis, i) => {
          const x = orderedAxes.length === 1 ? 500 : (i / (orderedAxes.length - 1)) * 960 + 20
          return (
            <g key={axis.name}>
              <line x1={x} y1={MARGIN_TOP} x2={x} y2={400 - MARGIN_BOTTOM} stroke="var(--border)" strokeWidth={1} />
              <text x={x} y={MARGIN_TOP - 8} textAnchor="middle" fontSize={10} fill="var(--muted)">{axis.name}</text>
              <text x={x} y={MARGIN_TOP + 10} textAnchor="middle" fontSize={9} fill="var(--muted)">{fmtStr(axis.max, measureFmt)}</text>
              <text x={x} y={400 - MARGIN_BOTTOM + LABEL_HEIGHT} textAnchor="middle" fontSize={9} fill="var(--muted)">{fmtStr(axis.min, measureFmt)}</text>
            </g>
          )
        })}
        {orderedLines.map((line, li) => {
          const points = line.map((norm, i) => {
            const x = orderedAxes.length === 1 ? 500 : (i / (orderedAxes.length - 1)) * 960 + 20
            const y = 400 - MARGIN_BOTTOM - norm * (400 - MARGIN_TOP - MARGIN_BOTTOM)
            return `${x},${y}`
          }).join(' ')
          return (
            <polyline key={li} points={points} fill="none" stroke="var(--accent)" strokeWidth={1} strokeOpacity={0.35} />
          )
        })}
      </svg>
    </div>
  )
}
```
Each axis renders three labels: its name above the line, the max value near the top of the line, and the min value near the bottom.

- [ ] **Step 2: Register it**

In `frontend/src/components/report/chartRenderers/index.tsx`, add:
```tsx
import ParallelCoordinatesRenderer from './ParallelCoordinatesRenderer'
```
```tsx
  parallel_coordinates: ParallelCoordinatesRenderer,
```

- [ ] **Step 3: Add `WidgetType`, `WIDGET_CATALOG`, `ROLE_SPECS` entries**

In `frontend/src/types/report.ts`:

1. Add `| 'parallel_coordinates'` to `WidgetType`.
2. Add to `WIDGET_CATALOG`:
```ts
  { type: 'parallel_coordinates' as WidgetType, label: 'Parallel Coordinates', category: 'Charts', icon: '⫴', defaultW: 7, defaultH: 5 },
```
3. Add to `ROLE_SPECS`:
```ts
  parallel_coordinates: [{ role: 'measures', label: 'Measures (ordered)', multi: true, required: true }],
```

- [ ] **Step 4: Add the icon**

Add `parallel_coordinates:'⫴'` to `WidgetConfigPanel.tsx`'s `widgetIcon()` map. Before finalizing, scan the existing `widgetIcon()` map for a collision with `'⫴'` (and re-check `'◉'`/`'◎'`/`'▦'`/`'▩'` from Tasks 4/6/10/12 too) — if any glyph in this whole phase collides with an existing one or with each other, pick a distinct replacement; report which (if any) needed changing.

- [ ] **Step 5: Verify**

Run (from `frontend/`):
```bash
npm run build
```
Expected: exactly the 10 pre-existing errors.

Confirm in your report: RTL support here means reversing the axis ORDER (not mirroring each axis's own min/max direction), consistent with how a right-to-left reader would expect the first-declared measure to appear on the right rather than the left.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/report/chartRenderers/ParallelCoordinatesRenderer.tsx frontend/src/components/report/chartRenderers/index.tsx frontend/src/types/report.ts frontend/src/components/report/WidgetConfigPanel.tsx
git commit -m "feat: add Parallel Coordinates Plot chart type"
```

---

## Task 15: Full regression pass and Phase 2 close-out

**Files:** none (verification only), plus the spec doc status line.

- [ ] **Step 1: Run the full automated test suite**

Backend (from `backend/`):
```bash
.venv/Scripts/python.exe -m pytest -v
```
Expected: all tests pass (Phase 0/1's tests + this phase's new ones across `shape_bubble`, `shape_bubble_animated`, `compute_fit_line`, `shape_correlation_matrix`, `shape_heatmap`, `shape_parallel_coordinates`).

Frontend (from `frontend/`):
```bash
npm run build
npm run test
```
Expected: build shows exactly the 10 pre-existing errors; all Vitest tests pass (still just Phase 0's 3 — this phase, like Phase 1, adds no new component-level Vitest tests, relying on diff-based review given Recharts+jsdom's limited rendering fidelity and the custom-SVG renderers' complexity).

- [ ] **Step 2: Icon collision audit**

Read through `frontend/src/components/report/WidgetConfigPanel.tsx`'s `widgetIcon()` map in full and confirm all 21 chart-type icons (16 from Phases 0-1 + 5 new: `bubble`, `bubble_change`, `correlation_matrix`, `heatmap`, `parallel_coordinates`) are visually distinct glyphs with no duplicates. Cross-check against `WIDGET_CATALOG` in `frontend/src/types/report.ts` to confirm both places agree on the same icon per type.

- [ ] **Step 3: Full manual regression read**

Read through `frontend/src/components/report/chartRenderers/index.tsx` and confirm all 21 chart types are registered with distinct keys.

Read through `backend/app/services/widget_data.py`'s `SHAPERS` dict and confirm all 21 chart types plus `kpi`/`table`/`crosstab`/`list` map to real, defined functions.

Confirm `_LEGACY_ROLE_KEYS` doesn't need updating for this phase's new roles (`size`, `color`, `group`, `animation`) — these are all consumed via `resolve_roles` only by `shape_bubble`/`shape_bubble_animated`, and check: does `WidgetConfigPanel.tsx`'s `configKeyFor` emit these as their own role name (the default `?? role` fallback), meaning `_LEGACY_ROLE_KEYS` would ALSO need `size`/`color`/`group`/`animation` entries for `resolve_roles`'s legacy-key fallback path to recognize them (exactly the class of bug Phase 1's final review caught for `measure2`/`start`)? If so, add them now — do not repeat that mistake. Specifically: add `"size": "size", "color": "color", "group": "group", "animation": "animation"` to `_LEGACY_ROLE_KEYS` in `backend/app/services/widget_data.py`, and add a test to `backend/tests/test_resolve_roles.py` confirming `resolve_roles({"category": "region", "measure": "x", "measure2": "y", "size": "s", "color": "c", "group": "g"})` returns all six roles correctly — mirroring the exact contract-locking test pattern Phase 1's final-review fix added for `measure2`/`start`. Update the existing `test_all_legacy_role_keys_map_to_themselves_or_a_known_rename` test's expected dict to include the four new entries.

- [ ] **Step 4: Update the design spec status**

In `docs/superpowers/specs/2026-08-10-chart-type-expansion-design.md`, change the `**Status:**` line from `Phase 1 Complete` to `Phase 2 Complete`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/widget_data.py backend/tests/test_resolve_roles.py docs/superpowers/specs/2026-08-10-chart-type-expansion-design.md
git commit -m "fix: extend _LEGACY_ROLE_KEYS for Phase 2 roles (size/color/group/animation); docs: mark Phase 2 complete"
```

**Phase 2 is now done — 21 of 28 target chart types are live.** Phase 3 (Box Plot, Waterfall, Gauge, Schedule/Gantt, Butterfly, Word Cloud, Vector Plot — 7 types, the last phase of the chart-type-expansion sub-project) gets its own plan document.
