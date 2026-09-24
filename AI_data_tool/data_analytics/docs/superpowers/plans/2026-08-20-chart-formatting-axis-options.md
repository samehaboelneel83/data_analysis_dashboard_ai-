# Chart Formatting & Axis Options Implementation Plan (Phase 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give chart authors control over axes, grid lines, legends and data labels, and finish the display-rule mark coverage phase 1 left at 12 of 31 renderers.

**Architecture:** One shared module of pure prop-builders (`chartRenderers/axisOptions.ts`) that returns Recharts props from a widget config, consumed by the 20 renderers built on Recharts' Cartesian primitives. Each renderer's hard-coded `<XAxis tick={…} axisLine={false} …>` becomes `<XAxis {...xAxisProps(cfg, rtl)} />` with today's values as the defaults, so an untouched widget renders identically. Because those same files are already open, the remaining renderers gain the `ruleStyles?.rows?.[i]?.fill ?? <existing>` fallback in the same pass.

**Tech Stack:** React 18, TypeScript, Recharts 2.12, vitest + @testing-library/react.

**Spec:** `docs/superpowers/specs/2026-08-18-formatting-display-rules-design.md` (phase 2 section, and the "Corrected 2026-08-20" note on renderer reach)

## Global Constraints

- **Defaults must reproduce today's rendering exactly.** Every builder's no-config path returns the values currently hard-coded in the renderers. A widget saved before this phase must look pixel-identical after it. This is the single most important constraint: the change touches 20 files and a silent visual regression would be found by users, not tests.
- **Only offer options a widget type can honour.** `WidgetConfigPanel` reads a capability map keyed on widget type. A Log-scale toggle that silently does nothing is worse than not shipping the option — this is the same defect class as phase 1's "Widget background" no-op, which shipped because a control was offered that nothing consumed.
- **Log scale cannot render zero or negative values** in Recharts. The panel says so at the point of choosing it, and the axis domain falls back to `auto` when the data contains a non-positive value rather than rendering an empty chart.
- **`ruleStyles` is optional on `ChartRendererProps`** and already plumbed. Rule fills override the palette colour but never the cross-filter selection treatment — dimming and selection strokes layer on top.
- Frontend tests run from `D:/data_analytics/frontend`. Iterate with `npx vitest run src/components/report/chartRenderers/`, full `npm test` before committing. **250 tests pass at the start of this phase.**
- Do not touch the non-Cartesian renderers (pie, donut, treemap, funnel, correlation matrix, heatmap, parallel coordinates, word cloud, vector, box plot) for axis options. They have no axes.

---

## Verified starting state

Counted at HEAD, not assumed — the previous phase's spec was wrong about exactly this and the error propagated into its plan.

**Already consume `ruleStyles` (12):** Bar, Bubble, Butterfly, Donut, DotPlot, Funnel, Gauge, Needle, Pie, Scatter, Treemap, Waterfall.

**Use Recharts axes (20):** Area, Bar, BubbleChange, Bubble, Butterfly, ComparativeTimeSeries, DotPlot, DualAxisBar, DualAxisBarLine, DualAxisLine, DualAxisTimeSeries, Histogram, Line, Needle, NumericSeries, Ribbon, Scatter, Schedule, Step, Waterfall.

**Cartesian renderers still lacking rule coverage (13):** Area, BubbleChange, ComparativeTimeSeries, DualAxisBar, DualAxisBarLine, DualAxisLine, DualAxisTimeSeries, Histogram, Line, NumericSeries, Ribbon, Schedule, Step.

Of those 13, the ones with genuine per-row marks that can take a fill are **Histogram, Ribbon, Schedule, BubbleChange, NumericSeries**. The line-shaped ones (Area, Line, Step, ComparativeTimeSeries, and the four dual-axis variants) have no per-row fill — a rule there applies to the point dots, which is a design decision Task 7 makes explicitly rather than by accident.

---

## File Structure

**Created:**
- `frontend/src/components/report/chartRenderers/axisOptions.ts` — pure prop-builders. No JSX, no React imports.
- `frontend/src/components/report/chartRenderers/axisOptions.test.ts` — unit tests per builder.
- `frontend/src/components/report/chartRenderers/axisOptions.integration.test.tsx` — one render-level test per behaviour proving props reach Recharts.
- `frontend/src/components/report/widgetCapabilities.ts` — which formatting options each widget type can honour.
- `frontend/src/components/report/widgetCapabilities.test.ts`

**Modified:**
- The 20 Cartesian renderers listed above (Tasks 3-6).
- `frontend/src/components/report/ExpandableGroup.tsx` — collapsible section wrapper (Task 8).
- `frontend/src/components/report/WidgetConfigPanel.tsx` — collapsible groups (Task 8), Formatting section (Task 9).
- The 5 renderers gaining rule fills (Task 7).
- `docs/superpowers/specs/2026-08-17-three-way-gap-analysis.md` (Task 10).

---

### Task 1: The axis and grid prop-builders

**Files:**
- Create: `frontend/src/components/report/chartRenderers/axisOptions.ts`
- Test: `frontend/src/components/report/chartRenderers/axisOptions.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: `xAxisProps(cfg, rtl)`, `yAxisProps(cfg, rtl, fmt?)`, `gridProps(cfg)`, plus the `FormatConfig` type.

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/components/report/chartRenderers/axisOptions.test.ts
import { describe, it, expect } from 'vitest'
import { xAxisProps, yAxisProps, gridProps } from './axisOptions'

describe('xAxisProps', () => {
  it('reproduces the current hard-coded defaults when no config is set', () => {
    const p = xAxisProps({}, false)
    expect(p.tick).toEqual({ fill: 'var(--muted)', fontSize: 10 })
    expect(p.axisLine).toBe(false)
    expect(p.tickLine).toBe(false)
    expect(p.angle).toBe(-30)
    expect(p.textAnchor).toBe('end')
    expect(p.interval).toBe(0)
    expect(p.reversed).toBe(false)
  })

  it('reverses for RTL', () => {
    expect(xAxisProps({}, true).reversed).toBe(true)
  })

  it('applies tick font size and colour overrides', () => {
    const p = xAxisProps({ axis_tick_size: 14, axis_tick_color: '#f00' }, false)
    expect(p.tick).toEqual({ fill: '#f00', fontSize: 14 })
  })

  it('shows the axis line when asked', () => {
    expect(xAxisProps({ axis_line: true }, false).axisLine).toBe(true)
  })

  it('applies a label when one is set, and omits it otherwise', () => {
    expect(xAxisProps({ x_axis_label: 'Region' }, false).label)
      .toEqual({ value: 'Region', position: 'insideBottom', offset: -5, fill: 'var(--muted)', fontSize: 11 })
    expect(xAxisProps({}, false).label).toBeUndefined()
  })
})

describe('yAxisProps', () => {
  it('reproduces the current hard-coded defaults', () => {
    const p = yAxisProps({}, false)
    expect(p.tick).toEqual({ fill: 'var(--muted)', fontSize: 10 })
    expect(p.axisLine).toBe(false)
    expect(p.tickLine).toBe(false)
    expect(p.orientation).toBe('left')
    expect(p.allowDecimals).toBe(false)
    expect(p.domain).toBeUndefined()
    expect(p.scale).toBeUndefined()
  })

  it('puts the axis on the right for RTL', () => {
    expect(yAxisProps({}, true).orientation).toBe('right')
  })

  it('builds a fixed domain from min and max', () => {
    expect(yAxisProps({ y_min: 0, y_max: 500 }, false).domain).toEqual([0, 500])
  })

  it('uses auto for the unset half of a partial domain', () => {
    expect(yAxisProps({ y_min: 10 }, false).domain).toEqual([10, 'auto'])
    expect(yAxisProps({ y_max: 90 }, false).domain).toEqual(['auto', 90])
  })

  it('applies a log scale when asked', () => {
    const p = yAxisProps({ y_scale: 'log' }, false)
    expect(p.scale).toBe('log')
    expect(p.domain).toEqual(['auto', 'auto'])
  })

  it('falls back to a linear auto domain when log is asked for but the data contains a non-positive value', () => {
    // Recharts cannot render a log axis through zero; an empty chart is a worse
    // answer than a linear one, so the caller passes the observed minimum.
    const p = yAxisProps({ y_scale: 'log' }, false, undefined, 0)
    expect(p.scale).toBeUndefined()
    expect(p.domain).toBeUndefined()
  })
})

describe('gridProps', () => {
  it('reproduces the current default dashed grid', () => {
    expect(gridProps({})).toEqual({ strokeDasharray: '3 3', stroke: 'var(--border)' })
  })

  it('returns null when grid lines are turned off, so the caller omits the element', () => {
    expect(gridProps({ grid: false })).toBeNull()
  })

  it('supports a solid grid and a custom colour', () => {
    expect(gridProps({ grid_style: 'solid', grid_color: '#333' }))
      .toEqual({ strokeDasharray: undefined, stroke: '#333' })
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/components/report/chartRenderers/axisOptions.test.ts`
Expected: FAIL — cannot resolve `./axisOptions`

- [ ] **Step 3: Write the module**

```typescript
// frontend/src/components/report/chartRenderers/axisOptions.ts
/**
 * Pure prop-builders for the Recharts Cartesian primitives.
 *
 * Every builder's no-config path returns the values that were hard-coded in the
 * renderers before this module existed, so a widget saved earlier renders
 * identically. That is load-bearing: this module is consumed by 20 renderers, and
 * a drifted default would be a silent visual regression across the whole app.
 *
 * These return props rather than components on purpose — each renderer keeps its
 * own JSX and its own layout quirks, and only the option plumbing is shared.
 */
import type { CalcColumnFormat } from '../../../services/api'

export interface FormatConfig {
  axis_tick_size?: number
  axis_tick_color?: string
  axis_line?: boolean
  tick_line?: boolean
  x_axis_label?: string
  y_axis_label?: string
  y_min?: number
  y_max?: number
  y_scale?: 'linear' | 'log'
  grid?: boolean
  grid_style?: 'dashed' | 'solid'
  grid_color?: string
  legend?: boolean
  legend_position?: 'top' | 'bottom' | 'left' | 'right'
  data_labels?: boolean
}

const DEFAULT_TICK_COLOR = 'var(--muted)'
const DEFAULT_TICK_SIZE = 10

function tick(cfg: FormatConfig) {
  return { fill: cfg.axis_tick_color ?? DEFAULT_TICK_COLOR, fontSize: cfg.axis_tick_size ?? DEFAULT_TICK_SIZE }
}

export function xAxisProps(cfg: FormatConfig, rtl: boolean) {
  return {
    tick: tick(cfg),
    axisLine: cfg.axis_line ?? false,
    tickLine: cfg.tick_line ?? false,
    angle: -30,
    textAnchor: 'end' as const,
    interval: 0,
    reversed: rtl,
    label: cfg.x_axis_label
      ? { value: cfg.x_axis_label, position: 'insideBottom' as const, offset: -5, fill: DEFAULT_TICK_COLOR, fontSize: 11 }
      : undefined,
  }
}

export function yAxisProps(
  cfg: FormatConfig,
  rtl: boolean,
  fmt?: CalcColumnFormat,
  observedMin?: number,
) {
  // Recharts cannot render a log axis through zero or negatives. Rendering an
  // empty chart is a worse answer than quietly rendering a linear one, so the
  // caller passes the observed minimum and we degrade when it is non-positive.
  const logRequested = cfg.y_scale === 'log'
  const logUsable = logRequested && (observedMin === undefined || observedMin > 0)

  let domain: [number | string, number | string] | undefined
  if (cfg.y_min !== undefined || cfg.y_max !== undefined) {
    domain = [cfg.y_min ?? 'auto', cfg.y_max ?? 'auto']
  } else if (logUsable) {
    domain = ['auto', 'auto']
  }

  return {
    tick: tick(cfg),
    axisLine: cfg.axis_line ?? false,
    tickLine: cfg.tick_line ?? false,
    orientation: (rtl ? 'right' : 'left') as 'left' | 'right',
    allowDecimals: false,
    scale: logUsable ? ('log' as const) : undefined,
    domain,
    label: cfg.y_axis_label
      ? { value: cfg.y_axis_label, angle: -90, position: 'insideLeft' as const, fill: DEFAULT_TICK_COLOR, fontSize: 11 }
      : undefined,
    _fmt: fmt,   // callers apply their own tickFormatter; kept for signature symmetry
  }
}

export function gridProps(cfg: FormatConfig) {
  if (cfg.grid === false) return null
  return {
    strokeDasharray: cfg.grid_style === 'solid' ? undefined : '3 3',
    stroke: cfg.grid_color ?? 'var(--border)',
  }
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/report/chartRenderers/axisOptions.test.ts`
Expected: PASS. If `yAxisProps`'s `_fmt` field makes the default-shape assertions awkward, drop the field and adjust — the tests are the contract, not the field.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/report/chartRenderers/axisOptions.ts frontend/src/components/report/chartRenderers/axisOptions.test.ts
git commit -m "Add shared axis and grid prop-builders for the Cartesian renderers"
```

---

### Task 2: Legend and data-label builders

**Files:**
- Modify: `frontend/src/components/report/chartRenderers/axisOptions.ts`
- Test: `frontend/src/components/report/chartRenderers/axisOptions.test.ts`

**Interfaces:**
- Consumes: `FormatConfig` from Task 1.
- Produces: `legendProps(cfg)` returning `null` when the legend is off; `labelListProps(cfg, fmt?)` returning `null` when data labels are off.

- [ ] **Step 1: Write the failing test**

```typescript
// append to axisOptions.test.ts
import { legendProps, labelListProps } from './axisOptions'

describe('legendProps', () => {
  it('reproduces the current default legend styling', () => {
    expect(legendProps({})).toEqual({
      wrapperStyle: { fontSize: 10 }, verticalAlign: 'bottom', align: 'center', layout: 'horizontal',
    })
  })

  it('returns null when the legend is turned off, so the caller omits the element', () => {
    expect(legendProps({ legend: false })).toBeNull()
  })

  it('places the legend on the right as a vertical list', () => {
    const p = legendProps({ legend_position: 'right' })!
    expect(p.align).toBe('right')
    expect(p.layout).toBe('vertical')
    expect(p.verticalAlign).toBe('middle')
  })

  it('places the legend on top', () => {
    const p = legendProps({ legend_position: 'top' })!
    expect(p.verticalAlign).toBe('top')
    expect(p.layout).toBe('horizontal')
  })
})

describe('labelListProps', () => {
  it('returns null by default, since data labels are opt-in', () => {
    expect(labelListProps({})).toBeNull()
  })

  it('returns a LabelList config when data labels are on', () => {
    const p = labelListProps({ data_labels: true })!
    expect(p.dataKey).toBe('value')
    expect(p.position).toBe('top')
    expect(p.style).toEqual({ fill: 'var(--muted)', fontSize: 10 })
  })

  it('formats label values with the measure format when one is given', () => {
    const p = labelListProps({ data_labels: true }, { type: 'currency', symbol: '$', decimals: 0 })!
    expect(typeof p.formatter).toBe('function')
    expect(p.formatter!(1234)).toContain('$')
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/components/report/chartRenderers/axisOptions.test.ts`
Expected: FAIL — `legendProps` and `labelListProps` are not exported

- [ ] **Step 3: Implement**

```typescript
// append to axisOptions.ts
import { fmtStr } from '../chartUtils'

const LEGEND_PLACEMENT = {
  bottom: { verticalAlign: 'bottom' as const, align: 'center' as const, layout: 'horizontal' as const },
  top:    { verticalAlign: 'top' as const,    align: 'center' as const, layout: 'horizontal' as const },
  left:   { verticalAlign: 'middle' as const, align: 'left' as const,   layout: 'vertical' as const },
  right:  { verticalAlign: 'middle' as const, align: 'right' as const,  layout: 'vertical' as const },
}

export function legendProps(cfg: FormatConfig) {
  if (cfg.legend === false) return null
  return { wrapperStyle: { fontSize: 10 }, ...LEGEND_PLACEMENT[cfg.legend_position ?? 'bottom'] }
}

export function labelListProps(cfg: FormatConfig, fmt?: CalcColumnFormat) {
  // Opt-in, not opt-out: switching every existing chart to labelled would be a
  // visual change to widgets nobody edited.
  if (!cfg.data_labels) return null
  return {
    dataKey: 'value',
    position: 'top' as const,
    style: { fill: 'var(--muted)', fontSize: 10 },
    formatter: (v: unknown) => fmtStr(v, fmt),
  }
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/report/chartRenderers/axisOptions.test.ts`
Expected: PASS (all Task 1 and Task 2 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/report/chartRenderers/axisOptions.ts frontend/src/components/report/chartRenderers/axisOptions.test.ts
git commit -m "Add legend and data-label prop-builders"
```

---

### Task 3: Apply the builders to the bar-shaped renderers

**Files:**
- Modify: `BarChartRenderer.tsx`, `HistogramRenderer.tsx`, `WaterfallChartRenderer.tsx`, `ButterflyChartRenderer.tsx`, `NeedlePlotRenderer.tsx`, `DotPlotRenderer.tsx`
- Test: `frontend/src/components/report/chartRenderers/axisOptions.integration.test.tsx` (create)

**Interfaces:**
- Consumes: `xAxisProps`, `yAxisProps`, `gridProps`, `legendProps`, `labelListProps`.
- Produces: nothing new.

- [ ] **Step 1: Write the failing integration test**

```tsx
// frontend/src/components/report/chartRenderers/axisOptions.integration.test.tsx
import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import BarChartRenderer from './BarChartRenderer'

const rows = [{ name: 'US', value: 1500 }, { name: 'CA', value: 400 }]
const base = {
  rows, data: { rows }, rtl: false, broadcasts: false,
  localSelected: null, onClickPoint: () => {},
}

function renderBar(cfg: Record<string, unknown>) {
  return render(<div style={{ width: 600, height: 400 }}><BarChartRenderer {...base} cfg={cfg} /></div>)
}

describe('BarChartRenderer formatting options', () => {
  it('renders a grid by default', () => {
    const { container } = renderBar({})
    expect(container.querySelector('.recharts-cartesian-grid')).not.toBeNull()
  })

  it('omits the grid entirely when grid lines are turned off', () => {
    const { container } = renderBar({ grid: false })
    expect(container.querySelector('.recharts-cartesian-grid')).toBeNull()
  })

  it('omits the legend when it is turned off', () => {
    const { container } = renderBar({ legend: false, bar_mode: 'stacked' })
    expect(container.querySelector('.recharts-legend-wrapper')).toBeNull()
  })

  it('renders data labels only when asked', () => {
    expect(renderBar({}).container.querySelector('.recharts-label-list')).toBeNull()
    expect(renderBar({ data_labels: true }).container.querySelector('.recharts-label-list')).not.toBeNull()
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/components/report/chartRenderers/axisOptions.integration.test.tsx`
Expected: FAIL on the grid-off and data-label cases — those options are not read yet.

- [ ] **Step 3: Apply the builders**

In each of the six files, replace the hard-coded elements. `BarChartRenderer` is the worked example; the other five take the identical transformation against whatever their current hard-coded values are.

```tsx
// BarChartRenderer.tsx — imports
import { xAxisProps, yAxisProps, gridProps, legendProps, labelListProps } from './axisOptions'
import { LabelList } from 'recharts'

// inside the component, before the return:
const grid = gridProps(cfg)
const legend = legendProps(cfg)
const labels = labelListProps(cfg, measureFmt)
const observedMin = Math.min(...rows.map((r: any) => Number(r.value)).filter((n: number) => !isNaN(n)))

// in the JSX, each hard-coded element becomes:
{grid && <CartesianGrid {...grid} />}
<XAxis dataKey="name" {...xAxisProps(cfg, rtl)} />
<YAxis {...yAxisProps(cfg, rtl, measureFmt, observedMin)}
  tickFormatter={v => isPercent ? `${v}%` : fmtStr(v, measureFmt)} />
{legend && <Legend {...legend} />}
```

and inside the `<Bar>` element, `{labels && <LabelList {...labels} />}`.

**Rules for the other five:**
- Keep each renderer's own `dataKey`, `tickFormatter` and any renderer-specific prop — the builders supply styling and behaviour options only, never the data binding.
- Where a renderer currently passes a prop the builder also sets, the builder wins; delete the local one so there is a single source.
- `ButterflyChartRenderer` has two value axes; call `yAxisProps` for each and keep their existing `orientation` overrides, since butterfly deliberately mirrors its axes.
- `DotPlotRenderer` and `NeedlePlotRenderer` use a category Y axis; pass `xAxisProps`/`yAxisProps` to match their existing orientation rather than forcing the bar layout.

- [ ] **Step 4: Run the tests**

Run: `cd frontend && npx vitest run src/components/report/chartRenderers/`
Expected: PASS, including the pre-existing `ruleFillWiring.test.tsx` and `barSeries.test.ts`.

- [ ] **Step 5: Verify no visual default drifted**

Run: `cd frontend && npm test`
Expected: 250+ passing with no failures. Any pre-existing renderer test that breaks means a default drifted — fix the builder, not the test.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/report/chartRenderers/
git commit -m "Apply shared axis options to the bar-shaped renderers"
```

---

### Task 4: Apply the builders to the line-shaped renderers

**Files:**
- Modify: `LineChartRenderer.tsx`, `AreaChartRenderer.tsx`, `StepPlotRenderer.tsx`, `ComparativeTimeSeriesRenderer.tsx`, `NumericSeriesPlotRenderer.tsx`
- Test: `axisOptions.integration.test.tsx`

**Interfaces:**
- Consumes: the five builders.
- Produces: nothing new.

- [ ] **Step 1: Write the failing test**

```tsx
// append to axisOptions.integration.test.tsx
import LineChartRenderer from './LineChartRenderer'

describe('LineChartRenderer formatting options', () => {
  const renderLine = (cfg: Record<string, unknown>) =>
    render(<div style={{ width: 600, height: 400 }}><LineChartRenderer {...base} cfg={cfg} /></div>)

  it('omits the grid when turned off', () => {
    expect(renderLine({ grid: false }).container.querySelector('.recharts-cartesian-grid')).toBeNull()
  })

  it('applies a fixed y-axis domain', () => {
    // With an explicit 0-5000 domain the 1500 tick is not the axis maximum, so the
    // rendered tick set differs from the auto-scaled one.
    const { container } = renderLine({ y_min: 0, y_max: 5000 })
    const ticks = [...container.querySelectorAll('.recharts-yAxis .recharts-cartesian-axis-tick-value')]
      .map(t => t.textContent)
    expect(ticks).toContain('5,000')
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/components/report/chartRenderers/axisOptions.integration.test.tsx`
Expected: FAIL — the domain is auto-scaled and `grid: false` is ignored.

- [ ] **Step 3: Apply the builders**

Same transformation as Task 3. Line-shaped specifics:

- Data labels on a line series attach to the `<Line>`/`<Area>` element as a `<LabelList>` child, exactly as they do on `<Bar>`.
- `ComparativeTimeSeriesRenderer` and `NumericSeriesPlotRenderer` each render two series; give both the same axis props so the pair stays visually consistent.
- `StepPlotRenderer` keeps its `type="step"` — the builders never touch the curve type.

- [ ] **Step 4: Run the tests**

Run: `cd frontend && npx vitest run src/components/report/chartRenderers/` then `npm test`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/report/chartRenderers/
git commit -m "Apply shared axis options to the line-shaped renderers"
```

---

### Task 5: Apply the builders to the dual-axis renderers

**Files:**
- Modify: `DualAxisBarChartRenderer.tsx`, `DualAxisLineChartRenderer.tsx`, `DualAxisBarLineChartRenderer.tsx`, `DualAxisTimeSeriesRenderer.tsx`
- Test: `axisOptions.integration.test.tsx`

**Interfaces:**
- Consumes: the five builders.
- Produces: nothing new.

- [ ] **Step 1: Write the failing test**

```tsx
// append to axisOptions.integration.test.tsx
import DualAxisBarLineChartRenderer from './DualAxisBarLineChartRenderer'

describe('Dual-axis renderers keep both axes independent', () => {
  it('applies shared styling to both axes without collapsing their orientations', () => {
    const rows2 = [{ name: 'US', value: 1500, value2: 12 }, { name: 'CA', value: 400, value2: 30 }]
    const { container } = render(
      <div style={{ width: 600, height: 400 }}>
        <DualAxisBarLineChartRenderer {...base} rows={rows2} data={{ rows: rows2 }}
          cfg={{ measure: 'value', measure2: 'value2', axis_tick_size: 14 }} />
      </div>
    )
    const yAxes = container.querySelectorAll('.recharts-yAxis')
    expect(yAxes.length).toBe(2)
    const sizes = [...container.querySelectorAll('.recharts-yAxis .recharts-cartesian-axis-tick-value')]
      .map(t => (t as SVGElement).getAttribute('font-size'))
    expect(sizes.every(s => s === '14')).toBe(true)
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/components/report/chartRenderers/axisOptions.integration.test.tsx`
Expected: FAIL — tick size is hard-coded at 10.

- [ ] **Step 3: Apply the builders**

Each dual-axis renderer has a left and a right `<YAxis>` distinguished by `yAxisId`. Apply `yAxisProps` to both, then re-apply each axis's own `orientation` and `yAxisId` AFTER the spread so the builder cannot flatten them:

```tsx
<YAxis yAxisId="left"  {...yAxisProps(cfg, rtl, measureFmt)}  orientation={rtl ? 'right' : 'left'} />
<YAxis yAxisId="right" {...yAxisProps(cfg, rtl, measure2Fmt)} orientation={rtl ? 'left' : 'right'} />
```

The ordering matters: `yAxisProps` sets `orientation` from `rtl` alone and knows nothing about left/right pairs, so the explicit prop must come last.

- [ ] **Step 4: Run the tests**

Run: `cd frontend && npx vitest run src/components/report/chartRenderers/` then `npm test`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/report/chartRenderers/
git commit -m "Apply shared axis options to the dual-axis renderers"
```

---

### Task 6: Apply the builders to the remaining Cartesian renderers

**Files:**
- Modify: `ScatterChartRenderer.tsx`, `BubbleChartRenderer.tsx`, `BubbleChangePlotRenderer.tsx`, `RibbonChartRenderer.tsx`, `ScheduleChartRenderer.tsx`
- Test: `axisOptions.integration.test.tsx`

**Interfaces:**
- Consumes: the five builders.
- Produces: nothing new.

- [ ] **Step 1: Write the failing test**

```tsx
// append to axisOptions.integration.test.tsx
import ScatterChartRenderer from './ScatterChartRenderer'

describe('ScatterChartRenderer formatting options', () => {
  it('honours a custom tick colour on both axes', () => {
    const { container } = render(
      <div style={{ width: 600, height: 400 }}>
        <ScatterChartRenderer {...base} cfg={{ axis_tick_color: '#ff0000' }} />
      </div>
    )
    const fills = [...container.querySelectorAll('.recharts-cartesian-axis-tick-value')]
      .map(t => (t as SVGElement).getAttribute('fill'))
    expect(fills.length).toBeGreaterThan(0)
    expect(fills.every(f => f === '#ff0000')).toBe(true)
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/components/report/chartRenderers/axisOptions.integration.test.tsx`
Expected: FAIL — tick fill is hard-coded to `var(--muted)`

- [ ] **Step 3: Apply the builders**

Same transformation. Specifics:

- `ScatterChartRenderer` and the two bubble renderers use numeric X axes with `type="number"` — keep that prop and their `dataKey`s; the builders supply styling only.
- `ScheduleChartRenderer` (Gantt) has a time X axis. Apply the styling props but **do not** apply `y_scale`/`y_min`/`y_max` — a log or fixed domain on a task-time axis is meaningless. Task 9's capability map is what stops those options being offered; this task simply must not wire them.
- `RibbonChartRenderer` renders stacked bars over `shape_heatmap`; treat it as bar-shaped.

- [ ] **Step 4: Run the tests**

Run: `cd frontend && npx vitest run src/components/report/chartRenderers/` then `npm test`
Expected: PASS. All 20 Cartesian renderers now read the shared options.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/report/chartRenderers/
git commit -m "Apply shared axis options to the scatter, bubble, ribbon and schedule renderers"
```

---

### Task 7: Finish display-rule mark coverage

**Files:**
- Modify: `HistogramRenderer.tsx`, `RibbonChartRenderer.tsx`, `ScheduleChartRenderer.tsx`, `BubbleChangePlotRenderer.tsx`, `NumericSeriesPlotRenderer.tsx`
- Test: `frontend/src/components/report/chartRenderers/ruleFillWiring.test.tsx` (exists)

**Interfaces:**
- Consumes: `ruleStyles` on `ChartRendererProps` (already present).
- Produces: nothing new.

This closes the gap phase 1's review found: the rules panel offers mark rules on widget types that cannot paint them.

- [ ] **Step 1: Write the failing test**

```tsx
// append to ruleFillWiring.test.tsx
import HistogramRenderer from './HistogramRenderer'

it('paints a histogram bar from a display rule', () => {
  const rows = [{ name: '0-10', value: 5 }, { name: '10-20', value: 9 }]
  const { container } = render(
    <div style={{ width: 600, height: 400 }}>
      <HistogramRenderer
        rows={rows} data={{ rows }} cfg={{}} rtl={false} broadcasts={false}
        localSelected={null} onClickPoint={() => {}}
        ruleStyles={{ rows: [{ fill: '#f87171' }, null], cells: {}, widget: {} }}
      />
    </div>
  )
  const fills = [...container.querySelectorAll('.recharts-rectangle')].map(r => r.getAttribute('fill'))
  expect(fills).toContain('#f87171')
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/components/report/chartRenderers/ruleFillWiring.test.tsx`
Expected: FAIL — histogram bars use their own colour

- [ ] **Step 3: Wire the fallback**

In each of the five, resolve the per-row fill through the rule style first, falling back to the existing colour expression so an unruled chart is unchanged:

```tsx
// the pattern, applied per renderer inside its per-row <Cell> mapping
<Cell key={i} fill={ruleStyles?.rows?.[i]?.fill ?? /* the renderer's existing colour expression */} />
```

Destructure `ruleStyles` from props in each renderer that does not already.

**Line-shaped renderers are deliberately excluded.** Area, Line, Step, ComparativeTimeSeries and the four dual-axis variants have no per-row mark to fill — a line is one path, not N shapes. Painting their dots would give a rule a different visual meaning on those charts than everywhere else. Record this in your report; Task 9 records it in the gap doc.

**If `WaterfallChartRenderer`'s wiring is still inert** — phase 1 wired it but `result_frame()` in `backend/app/services/display_rules.py` does not recognise `shape_waterfall`'s `bars`-keyed result, so `rows` is always empty for waterfall — either add a `waterfall` branch to `result_frame` returning a frame over `bars`, or leave it and note it. Say which you did.

- [ ] **Step 4: Run the tests**

Run: `cd frontend && npx vitest run src/components/report/chartRenderers/` then `npm test`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/report/chartRenderers/
git commit -m "Wire display-rule fills into the remaining mark-shaped renderers"
```

---

### Task 8: Collapsible groups in the widget settings panel

**Files:**
- Create: `frontend/src/components/report/ExpandableGroup.tsx`, `frontend/src/components/report/ExpandableGroup.test.tsx`
- Modify: `frontend/src/components/report/WidgetConfigPanel.tsx`
- Test: `frontend/src/components/report/WidgetConfigPanel.test.tsx`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `<ExpandableGroup id="..." title="..." defaultOpen={boolean}>children</ExpandableGroup>`, and the localStorage key `datalytics.panelGroups` holding `Record<string, boolean>`.

`WidgetConfigPanel` is the longest surface in the app — roles, dataset override, aggregation, limit, sort, running totals, interactions, hierarchy, display rules, column formats — and Task 9 adds a Formatting section on top. Flat, it is a scroll marathon: an author hunting the sort order scrolls past six sections that do not concern them.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/report/ExpandableGroup.test.tsx
import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import ExpandableGroup from './ExpandableGroup'

beforeEach(() => localStorage.clear())

describe('ExpandableGroup', () => {
  it('renders its children when open', () => {
    render(<ExpandableGroup id="roles" title="Roles" defaultOpen><p>inner</p></ExpandableGroup>)
    expect(screen.getByText('inner')).toBeInTheDocument()
  })

  it('hides its children when collapsed, and the header stays visible', () => {
    render(<ExpandableGroup id="roles" title="Roles" defaultOpen={false}><p>inner</p></ExpandableGroup>)
    expect(screen.queryByText('inner')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Roles/i })).toBeInTheDocument()
  })

  it('toggles on click', () => {
    render(<ExpandableGroup id="roles" title="Roles" defaultOpen={false}><p>inner</p></ExpandableGroup>)
    fireEvent.click(screen.getByRole('button', { name: /Roles/i }))
    expect(screen.getByText('inner')).toBeInTheDocument()
  })

  it('exposes its state to assistive tech via aria-expanded', () => {
    render(<ExpandableGroup id="roles" title="Roles" defaultOpen={false}><p>inner</p></ExpandableGroup>)
    const header = screen.getByRole('button', { name: /Roles/i })
    expect(header).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(header)
    expect(header).toHaveAttribute('aria-expanded', 'true')
  })

  it('persists its state so the author is not re-opening the same group every time', () => {
    const { unmount } = render(<ExpandableGroup id="sorting" title="Sorting" defaultOpen={false}><p>inner</p></ExpandableGroup>)
    fireEvent.click(screen.getByRole('button', { name: /Sorting/i }))
    unmount()

    render(<ExpandableGroup id="sorting" title="Sorting" defaultOpen={false}><p>inner</p></ExpandableGroup>)
    expect(screen.getByText('inner')).toBeInTheDocument()
  })

  it('keeps each group independent', () => {
    render(
      <>
        <ExpandableGroup id="a" title="Group A" defaultOpen={false}><p>a-inner</p></ExpandableGroup>
        <ExpandableGroup id="b" title="Group B" defaultOpen={false}><p>b-inner</p></ExpandableGroup>
      </>
    )
    fireEvent.click(screen.getByRole('button', { name: /Group A/i }))
    expect(screen.getByText('a-inner')).toBeInTheDocument()
    expect(screen.queryByText('b-inner')).not.toBeInTheDocument()
  })

  it('survives unreadable storage rather than failing to render', () => {
    localStorage.setItem('datalytics.panelGroups', 'not json')
    render(<ExpandableGroup id="roles" title="Roles" defaultOpen><p>inner</p></ExpandableGroup>)
    expect(screen.getByText('inner')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/components/report/ExpandableGroup.test.tsx`
Expected: FAIL — cannot resolve `./ExpandableGroup`

- [ ] **Step 3: Write the component**

```tsx
// frontend/src/components/report/ExpandableGroup.tsx
import { useState, useCallback } from 'react'

const STORAGE_KEY = 'datalytics.panelGroups'

/** Read the whole map. Storage is shared with other tabs and can hold anything, so a
 *  parse failure degrades to "no remembered state" rather than breaking the panel. */
function readState(): Record<string, boolean> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : null
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {}
  } catch {
    return {}
  }
}

function writeState(id: string, open: boolean) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...readState(), [id]: open }))
  } catch {
    // Storage full or blocked (private mode). Collapsing still works for this session;
    // only the memory across navigations is lost, which is not worth failing a render over.
  }
}

interface Props {
  id: string
  title: string
  defaultOpen?: boolean
  children: React.ReactNode
}

export default function ExpandableGroup({ id, title, defaultOpen = false, children }: Props) {
  const [open, setOpen] = useState(() => readState()[id] ?? defaultOpen)

  const toggle = useCallback(() => {
    setOpen(prev => {
      writeState(id, !prev)
      return !prev
    })
  }, [id])

  return (
    <div style={{ borderBottom: '1px solid var(--border)' }}>
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        style={{
          display: 'flex', alignItems: 'center', gap: 6, width: '100%',
          background: 'none', border: 'none', cursor: 'pointer',
          padding: '9px 2px', color: 'var(--text)', font: 'inherit',
          fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.05em',
        }}
      >
        <span aria-hidden style={{ color: 'var(--muted)', fontSize: 9, transition: 'transform .12s',
          transform: open ? 'rotate(90deg)' : 'none', display: 'inline-block' }}>&#9654;</span>
        <span style={{ color: 'var(--muted)' }}>{title}</span>
      </button>
      {open && <div style={{ paddingBottom: 10 }}>{children}</div>}
    </div>
  )
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/report/ExpandableGroup.test.tsx`
Expected: PASS (7 tests)

- [ ] **Step 5: Wrap the config panel's sections**

In `WidgetConfigPanel.tsx`, wrap each existing section in an `ExpandableGroup`. Do **not** restructure the sections' contents — this step only adds the wrapper, so the diff stays reviewable and any behaviour change is obviously unintended.

Group ids and default open state:

| id | Title | Default |
|---|---|---|
| `roles` | Fields | open |
| `data` | Data & aggregation | open |
| `sort` | Sort & limit | closed |
| `interactions` | Interactions | closed |
| `hierarchy` | Hierarchy | closed |
| `rules` | Display rules | closed |
| `formats` | Column formats | closed |

Fields and Data stay open because they are what an author touches on nearly every visit; the rest are occasional. Keep the widget title input and the widget-type label OUTSIDE any group — they identify what is being edited and must never be hidden.

- [ ] **Step 6: Add panel-level tests**

```tsx
// append to WidgetConfigPanel.test.tsx — use the file's existing render harness
it('collapses an occasional section by default and opens it on click', () => {
  renderPanel()   // use whatever helper the file already defines
  expect(screen.queryByLabelText(/Sort by/i)).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: /Sort & limit/i }))
  expect(screen.getByLabelText(/Sort by/i)).toBeInTheDocument()
})

it('keeps the fields section open by default', () => {
  renderPanel()
  expect(screen.getByRole('button', { name: /Fields/i })).toHaveAttribute('aria-expanded', 'true')
})
```

Existing panel tests that query controls inside now-collapsed sections will fail. **That is a real finding, not test noise:** each one tells you a control moved behind a collapsed header. Fix each by opening the group first (`fireEvent.click(screen.getByRole('button', { name: /…/i }))`) — never by deleting the assertion, and never by defaulting every group to open, which would discard the feature.

- [ ] **Step 7: Run the full suite**

Run: `cd frontend && npm test`
Expected: PASS. Report how many pre-existing tests needed a group opened — that number measures how much this changes the panel.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/report/ExpandableGroup.tsx frontend/src/components/report/ExpandableGroup.test.tsx frontend/src/components/report/WidgetConfigPanel.tsx frontend/src/components/report/WidgetConfigPanel.test.tsx
git commit -m "Make the widget settings panel a list of collapsible groups"
```

---

### Task 9: The capability map and the config-panel UI

**Files:**
- Create: `frontend/src/components/report/widgetCapabilities.ts`, `frontend/src/components/report/widgetCapabilities.test.ts`
- Modify: `frontend/src/components/report/WidgetConfigPanel.tsx`

**Interfaces:**
- Consumes: `WidgetType` from `types/report.ts`.
- Produces: `formattingCapabilities(wt: WidgetType): FormattingCapability[]` where `FormattingCapability` is `'axes' | 'yScale' | 'yDomain' | 'grid' | 'legend' | 'dataLabels'`.

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/components/report/widgetCapabilities.test.ts
import { describe, it, expect } from 'vitest'
import { formattingCapabilities } from './widgetCapabilities'

describe('formattingCapabilities', () => {
  it('gives a bar chart the full Cartesian option set', () => {
    const caps = formattingCapabilities('bar')
    expect(caps).toEqual(expect.arrayContaining(['axes', 'yScale', 'yDomain', 'grid', 'legend', 'dataLabels']))
  })

  it('gives a pie chart no axis options at all', () => {
    const caps = formattingCapabilities('pie')
    expect(caps).not.toContain('axes')
    expect(caps).not.toContain('yScale')
    expect(caps).toContain('legend')
  })

  it('withholds log scale and a fixed domain from the Gantt chart, whose axis is time', () => {
    const caps = formattingCapabilities('schedule')
    expect(caps).toContain('axes')
    expect(caps).not.toContain('yScale')
    expect(caps).not.toContain('yDomain')
  })

  it('gives a KPI no chart formatting options', () => {
    expect(formattingCapabilities('kpi')).toEqual([])
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/components/report/widgetCapabilities.test.ts`
Expected: FAIL — module does not exist

- [ ] **Step 3: Implement the map and the panel section**

```typescript
// frontend/src/components/report/widgetCapabilities.ts
/**
 * Which formatting options each widget type can actually honour.
 *
 * This exists because offering a control that silently does nothing is a real
 * defect, not a cosmetic one — phase 1 shipped a "Widget background" rule target
 * that painted nothing, and it survived 860 tests precisely because no one asked
 * whether the consumer existed. A Log-scale toggle on a word cloud is the same bug.
 */
import type { WidgetType } from '../../types/report'

export type FormattingCapability = 'axes' | 'yScale' | 'yDomain' | 'grid' | 'legend' | 'dataLabels'

const FULL: FormattingCapability[] = ['axes', 'yScale', 'yDomain', 'grid', 'legend', 'dataLabels']
const TIME_AXIS: FormattingCapability[] = ['axes', 'grid', 'legend']
const LEGEND_ONLY: FormattingCapability[] = ['legend', 'dataLabels']

const CAPABILITIES: Partial<Record<WidgetType, FormattingCapability[]>> = {
  bar: FULL, line: FULL, area: FULL, step: FULL, histogram: FULL, waterfall: FULL,
  scatter: FULL, bubble: FULL, bubble_change: FULL, dot_plot: FULL, needle: FULL,
  butterfly: FULL, numeric_series: FULL, ribbon: FULL,
  dual_axis_bar: FULL, dual_axis_line: FULL, dual_axis_bar_line: FULL,
  dual_axis_time_series: TIME_AXIS, comparative_time_series: TIME_AXIS, schedule: TIME_AXIS,
  pie: LEGEND_ONLY, donut: LEGEND_ONLY, treemap: LEGEND_ONLY, funnel: LEGEND_ONLY,
}

export function formattingCapabilities(wt: WidgetType): FormattingCapability[] {
  return CAPABILITIES[wt] ?? []
}
```

In `WidgetConfigPanel.tsx`, add a **Formatting** section — wrapped in an `ExpandableGroup` with `id="formatting"` and `defaultOpen={false}`, matching the groups Task 8 introduced — rendered only when `formattingCapabilities(wt).length > 0`, showing one control per capability the type has:

- `axes` — X label, Y label, tick size, tick colour, show axis line, show tick marks.
- `yScale` — Linear / Logarithmic select, with the helper text: *"A log axis cannot show zero or negative values; the axis falls back to linear when the data contains one."*
- `yDomain` — Min and Max number inputs, both optional.
- `grid` — show/hide, dashed/solid, colour.
- `legend` — show/hide, position (top/bottom/left/right).
- `dataLabels` — show/hide.

Write each value into `config` with the exact `FormatConfig` key names from Task 1, and persist through the panel's existing debounced `onUpdate` — do not add a new save path.

- [ ] **Step 4: Run the tests**

Run: `cd frontend && npx vitest run src/components/report/` then `npm test`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/report/widgetCapabilities.ts frontend/src/components/report/widgetCapabilities.test.ts frontend/src/components/report/WidgetConfigPanel.tsx
git commit -m "Offer formatting options only where a widget type can honour them"
```

---

### Task 10: Update the gap analysis

**Files:**
- Modify: `docs/superpowers/specs/2026-08-17-three-way-gap-analysis.md`

**Interfaces:**
- Consumes: everything above.
- Produces: six re-scored rows and a corrected tally.

- [ ] **Step 1: Run both suites and record the output**

Run: `cd frontend && npm test` and `cd backend && python -m pytest -q`
Expected: PASS. Do not re-score a row on a red suite — a gap row is a factual claim.

- [ ] **Step 2: Re-score the six category-07 rows**

| Row | From | To |
|---|---|---|
| Fixed axis minimum / maximum | No | Yes |
| Logarithmic axis | No | Yes |
| Axis label / line / tick styling | No | Yes |
| Grid lines & wall background | Partial | Yes |
| Legend visibility & placement | Partial | Yes |
| Data labels | Partial | Yes |

Follow the note style of the rows re-scored on 2026-08-17 and 2026-08-18: a `**Shipped 2026-08-20.**` prefix, the mechanism, then the honest limitation. Limitations that must appear:

- Options are offered per widget type through a capability map; non-Cartesian visuals get legend and data-label options only, and the Gantt/time-axis types get no log scale or fixed domain.
- Log scale degrades to linear when the data contains a zero or negative value, because Recharts cannot render one.
- Wall background is not configurable — only grid lines are. SAS treats the wall as a separate surface, so if you claim the "Grid lines & wall background" row, say plainly that the wall half is not covered.

- [ ] **Step 3: Record the renderer-coverage outcome**

Add a line to the category 07 notes (or the "Expression-based display rules" row) recording that mark rules now paint on N of 31 renderers, and that the line-shaped renderers are deliberately excluded because a line has no per-row mark to fill. Count the actual number after Task 7 — do not assume.

- [ ] **Step 4: Update the tally and verify the arithmetic**

Category 07 currently reads `| 28 | 9 | 6 | 13 |`. Six rows move to Yes: three from No (fixed min/max, log axis, axis styling) and three from Partial (grid, legend, data labels) → `| 28 | 15 | 3 | 10 |`. The Total moves from `| 276 | 111 | 30 | 135 |` to `| 276 | 117 | 27 | 132 |`.

Verify by counting the actual table rows, not by trusting this arithmetic — every category row must sum to its row count and the total must sum to 276.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/2026-08-17-three-way-gap-analysis.md
git commit -m "Update gap analysis: chart formatting and axis options shipped"
```

---

## Verification checklist

- [ ] `cd frontend && npm test` passes
- [ ] `cd backend && python -m pytest -q` passes (unchanged unless Task 7 touched `result_frame`)
- [ ] A widget saved before this phase renders identically — no default drifted
- [ ] Turning the grid off omits the element rather than drawing an invisible one
- [ ] A log axis with a zero in the data renders linear instead of empty
- [ ] No formatting control appears on a widget type that cannot honour it
- [ ] Mark rules paint on every renderer that has per-row marks
- [ ] The gap-analysis tally sums to 276
