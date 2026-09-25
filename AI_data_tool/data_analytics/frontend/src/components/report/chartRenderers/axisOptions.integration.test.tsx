import { describe, it, expect, beforeAll } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import { legendProps } from './axisOptions'
import BarChartRenderer from './BarChartRenderer'
import DonutChartRenderer from './DonutChartRenderer'
import WaterfallChartRenderer from './WaterfallChartRenderer'
import ButterflyChartRenderer from './ButterflyChartRenderer'
import LineChartRenderer from './LineChartRenderer'
import AreaChartRenderer from './AreaChartRenderer'
import StepPlotRenderer from './StepPlotRenderer'
import ComparativeTimeSeriesRenderer from './ComparativeTimeSeriesRenderer'
import NumericSeriesPlotRenderer from './NumericSeriesPlotRenderer'
import DualAxisBarLineChartRenderer from './DualAxisBarLineChartRenderer'
import ScatterChartRenderer from './ScatterChartRenderer'
import BubbleChartRenderer from './BubbleChartRenderer'
import BubbleChangePlotRenderer from './BubbleChangePlotRenderer'
import RibbonChartRenderer from './RibbonChartRenderer'
import ScheduleChartRenderer from './ScheduleChartRenderer'
import HistogramRenderer from './HistogramRenderer'
import DotPlotRenderer from './DotPlotRenderer'

// recharts' ResponsiveContainer needs a non-zero measured size to render its children
// at all; jsdom's default 0x0 getBoundingClientRect makes every assertion here pass
// vacuously (nothing rendered) unless this is polyfilled -- same pattern already used
// in ruleFillWiring.test.tsx.
beforeAll(() => {
  Element.prototype.getBoundingClientRect = () => ({
    width: 600, height: 400, top: 0, left: 0, right: 600, bottom: 400, x: 0, y: 0, toJSON() {},
  }) as DOMRect
})

const rows = [{ name: 'US', value: 1500 }, { name: 'CA', value: 400 }]
const base = {
  rows, data: { rows }, rtl: false, broadcasts: false,
  localSelected: null, onClickPoint: () => {},
}

function renderBar(cfg: Record<string, unknown>, overrides: Record<string, unknown> = {}) {
  return render(<div style={{ width: 600, height: 400 }}><BarChartRenderer {...base} {...overrides} cfg={cfg} /></div>)
}

describe('a stacked value axis is sized by the stack total', () => {
  // The axis of a stacked chart tops out at the row SUM, not at any single
  // series value -- three series of 900,000 stack to 2,700,000, a digit longer
  // than anything actually plotted. Sizing the gutter from the plotted values
  // leaves the top tick overflowing into the bars, which is the bug this pins.
  // Asserting on the RENDERED width (not on yAxisWidth directly) is what makes
  // this test bind BarChartRenderer's choice of values: a unit test of the
  // width function alone stays green when the renderer passes the wrong array.
  const money = { type: 'currency', symbol: '$', decimals: 0 } as never
  const cross = (rows: unknown[][]) => ({
    type: 'crosstab', columns: ['name', 'A', 'B', 'C', '__total__'], rows,
  })

  function renderedAxisWidth(data: unknown, cfg: Record<string, unknown>) {
    const { container } = render(
      <div style={{ width: 600, height: 400 }}>
        <BarChartRenderer {...base} data={data} cfg={cfg} measureFmt={money} />
      </div>,
    )
    // Recharts lays the axis out from the width it was given; the tick line's
    // x is that gutter, so it reports what was actually reserved.
    const axis = container.querySelector('.recharts-yAxis')
    expect(axis).not.toBeNull()
    const tick = axis!.querySelector('.recharts-cartesian-axis-tick-value')
    expect(tick).not.toBeNull()
    return Number(tick!.getAttribute('x'))
  }

  it('reserves a wider gutter for a stack than its largest single value needs', () => {
    // Same per-series magnitudes in both charts; only the stacking differs, so
    // any width difference comes from summing.
    const rows = [['US', 900000, 900000, 900000, 2700000]]
    const clustered = renderedAxisWidth(cross(rows), { bar_mode: 'clustered' })
    const stacked = renderedAxisWidth(cross(rows), { bar_mode: 'stacked' })
    expect(stacked).toBeGreaterThan(clustered)
  })

  it('keeps every stacked tick label inside the chart', () => {
    const { container } = render(
      <div style={{ width: 600, height: 400 }}>
        <BarChartRenderer {...base} data={cross([['US', 900000, 900000, 900000, 2700000]])}
          cfg={{ bar_mode: 'stacked' }} measureFmt={money} />
      </div>,
    )
    const ticks = Array.from(container.querySelectorAll('.recharts-yAxis .recharts-cartesian-axis-tick-value'))
    expect(ticks.length).toBeGreaterThan(0)
    for (const t of ticks) expect(Number(t.getAttribute('x'))).toBeGreaterThanOrEqual(0)
  })
})

describe('BarChartRenderer formatting options', () => {
  it('renders a grid by default', () => {
    const { container } = renderBar({})
    expect(container.querySelector('.recharts-cartesian-grid')).not.toBeNull()
  })

  it('omits the grid entirely when grid lines are turned off', () => {
    const { container } = renderBar({ grid: false })
    expect(container.querySelector('.recharts-cartesian-grid')).toBeNull()
  })

  // BarChartRenderer only renders a <Legend> on the multi-series (crosstab) path, so this
  // needs crosstab-shaped data — the plain { name, value } rows in `base` never produce a
  // series and would make this assertion pass vacuously regardless of the legend wiring.
  const crosstabData = {
    type: 'crosstab',
    columns: ['name', 'Series A', 'Series B', '__total__'],
    rows: [
      ['US', 1000, 500, 1500],
      ['CA', 300, 100, 400],
    ],
  }

  it('renders a legend by default on the multi-series path', () => {
    const { container } = renderBar({ bar_mode: 'stacked' }, { data: crosstabData })
    expect(container.querySelector('.recharts-legend-wrapper')).not.toBeNull()
  })

  it('omits the legend when it is turned off', () => {
    const { container } = renderBar({ legend: false, bar_mode: 'stacked' }, { data: crosstabData })
    expect(container.querySelector('.recharts-legend-wrapper')).toBeNull()
  })

  it('adds no fill patterns unless the accessibility toggle is on', () => {
    const { container } = renderBar({ bar_mode: 'stacked' }, { data: crosstabData })
    expect(container.querySelectorAll('pattern[id^="fillpat-"]').length).toBe(0)
  })

  it('hatches groups from the second one on when series_patterns is set', () => {
    // Redundant encoding: the first group stays a solid fill (nothing to distinguish it
    // from yet) and every later group gets its own <pattern>, so colour + texture carry
    // the same split for a greyscale or colour-blind viewer.
    const { container } = renderBar({ bar_mode: 'stacked', series_patterns: true }, { data: crosstabData })
    expect(container.querySelector('pattern#fillpat-0')).toBeNull()
    expect(container.querySelector('pattern#fillpat-1')).not.toBeNull()
  })

  it('renders data labels only when asked', async () => {
    expect(renderBar({}).container.querySelector('.recharts-label-list')).toBeNull()
    // Bar only emits its LabelList once its (default-active) entry animation finishes
    // (recharts' Bar.js: `(!isAnimationActive || isAnimationFinished) && LabelList...`),
    // so this needs waitFor rather than a synchronous assertion like the others above.
    const { container } = renderBar({ data_labels: true })
    await waitFor(() => {
      expect(container.querySelector('.recharts-label-list')).not.toBeNull()
    })
  })
})

// WaterfallChartRenderer never set axisLine/tickLine/allowDecimals explicitly, so Recharts'
// own `true` defaults applied to all three; the shared builder's defaults are `false`,
// `false`, `false`. Missing the after-spread override that keeps them `true` would make
// the axis lines vanish and the Y axis round every tick to a whole number on every existing
// waterfall widget -- this pins that divergence so it cannot silently regress.
describe('WaterfallChartRenderer formatting options', () => {
  const waterfallData = { bars: [{ name: 'A', start: 0, end: 0.75 }] }

  function renderWaterfall(cfg: Record<string, unknown>) {
    return render(<div style={{ width: 600, height: 400 }}><WaterfallChartRenderer {...base} data={waterfallData} cfg={cfg} /></div>)
  }

  it('keeps its axis lines and tick lines visible by default', () => {
    const { container } = renderWaterfall({})
    expect(container.querySelectorAll('.recharts-cartesian-axis-line').length).toBe(2)
    expect(container.querySelectorAll('.recharts-cartesian-axis-tick-line').length).toBeGreaterThan(0)
  })

  it('still allows a fractional y-axis tick by default', () => {
    const { container } = renderWaterfall({})
    // A 0-0.75 domain only shows a fractional tick when allowDecimals stayed true; under
    // the builder's own default (false) Recharts would round the domain to whole numbers.
    const yTicks = [...container.querySelectorAll('.recharts-yAxis .recharts-cartesian-axis-tick-value')]
      .map(t => t.textContent ?? '')
    expect(yTicks.some(t => /[.,٫]/.test(t))).toBe(true)
  })

  // Fix round 1 (Task 9 review): tick size/colour used to be hard-pinned to
  // `{ fontSize: 11 }` past the builder spread, discarding axis_tick_size/
  // axis_tick_color even though the Formatting panel offers 'axes' for `waterfall`.
  it('keeps its historical fontSize-11 tick by default, and honours a custom tick size once set', () => {
    const defaultTicks = [...renderWaterfall({}).container.querySelectorAll('.recharts-cartesian-axis-tick-value')]
    expect(defaultTicks.length).toBeGreaterThan(0)
    expect(defaultTicks.every(t => (t as SVGElement).getAttribute('font-size') === '11')).toBe(true)

    const sizedTicks = [...renderWaterfall({ axis_tick_size: 18 }).container.querySelectorAll('.recharts-cartesian-axis-tick-value')]
    expect(sizedTicks.length).toBeGreaterThan(0)
    expect(sizedTicks.every(t => (t as SVGElement).getAttribute('font-size') === '18')).toBe(true)
  })
})

// ButterflyChartRenderer's `left` bar stores its value as -(Math.abs(...)) purely to draw
// the bar leftward; the tooltip and the XAxis tickFormatter both display Math.abs(v). The
// opt-in data label must match rather than leak the sign encoding as a literal negative
// number that contradicts everything else on the same bar.
describe('ButterflyChartRenderer formatting options', () => {
  const butterflyData = { rows: [{ name: 'A', value: 1500, value2: 900 }] }

  function renderButterfly(cfg: Record<string, unknown>) {
    return render(<div style={{ width: 600, height: 400 }}><ButterflyChartRenderer {...base} data={butterflyData} cfg={cfg} /></div>)
  }

  it("shows the left bar's data label without a negative sign, matching its own tooltip", () => {
    // Butterfly's Bar elements render with isAnimationActive={false}, so the LabelList
    // (and its formatted text) is present synchronously, unlike BarChartRenderer's default.
    const { container } = renderButterfly({ data_labels: true })
    const labelTexts = [...container.querySelectorAll('.recharts-label-list text')].map(t => t.textContent ?? '')
    expect(labelTexts.length).toBeGreaterThan(0)
    expect(labelTexts.some(t => t.includes('-'))).toBe(false)
  })

  // Fix round 1 (Task 9 review): tick size/colour used to be hard-pinned to
  // `{ fontSize: 11 }` past the builder spread, discarding axis_tick_size/
  // axis_tick_color even though the Formatting panel offers 'axes' for `butterfly`.
  it('keeps its historical fontSize-11 tick by default, and honours a custom tick size once set', () => {
    const defaultTicks = [...renderButterfly({}).container.querySelectorAll('.recharts-cartesian-axis-tick-value')]
    expect(defaultTicks.length).toBeGreaterThan(0)
    expect(defaultTicks.every(t => (t as SVGElement).getAttribute('font-size') === '11')).toBe(true)

    const sizedTicks = [...renderButterfly({ axis_tick_size: 20 }).container.querySelectorAll('.recharts-cartesian-axis-tick-value')]
    expect(sizedTicks.length).toBeGreaterThan(0)
    expect(sizedTicks.every(t => (t as SVGElement).getAttribute('font-size') === '20')).toBe(true)
  })
})

// Fix wave (2026-08-20 gap review, FIX 3): HistogramRenderer's XAxis hard-coded
// `tick={{ fill: 'var(--muted)', fontSize: 9 }}` after the axisOptions spread --
// the fourth renderer with this pattern, after schedule/waterfall/butterfly were
// fixed in round 1. axis_tick_size/axis_tick_color silently did nothing even though
// the Formatting panel offers 'axes' for `histogram`.
describe('HistogramRenderer formatting options', () => {
  const histogramRows = [{ name: '0-10', value: 5 }, { name: '10-20', value: 9 }]

  function renderHistogram(cfg: Record<string, unknown>) {
    return render(<div style={{ width: 600, height: 400 }}><HistogramRenderer {...base} rows={histogramRows} cfg={cfg} /></div>)
  }

  // Scoped to the X axis specifically: it is the one whose tick was hard-coded past
  // the axisOptions spread (see HistogramRenderer.tsx), while the Y axis already
  // took its tick from yAxisProps(cfg, rtl) and defaults to fontSize 10, not 9 -- an
  // unscoped query across both axes would pass even with the bug still in place.
  it('keeps its historical fontSize-9 X-axis tick by default, and honours a custom tick size once set', () => {
    const defaultTicks = [...renderHistogram({}).container.querySelectorAll('.recharts-xAxis .recharts-cartesian-axis-tick-value')]
    expect(defaultTicks.length).toBeGreaterThan(0)
    expect(defaultTicks.every(t => (t as SVGElement).getAttribute('font-size') === '9')).toBe(true)

    const sizedTicks = [...renderHistogram({ axis_tick_size: 15 }).container.querySelectorAll('.recharts-xAxis .recharts-cartesian-axis-tick-value')]
    expect(sizedTicks.length).toBeGreaterThan(0)
    expect(sizedTicks.every(t => (t as SVGElement).getAttribute('font-size') === '15')).toBe(true)
  })

  it('keeps its historical muted X-axis tick colour by default, and honours a custom tick colour once set', () => {
    const defaultTicks = [...renderHistogram({}).container.querySelectorAll('.recharts-xAxis .recharts-cartesian-axis-tick-value')]
    expect(defaultTicks.length).toBeGreaterThan(0)
    expect(defaultTicks.every(t => (t as SVGElement).getAttribute('fill') === 'var(--muted)')).toBe(true)

    const colouredTicks = [...renderHistogram({ axis_tick_color: '#ff0000' }).container.querySelectorAll('.recharts-xAxis .recharts-cartesian-axis-tick-value')]
    expect(colouredTicks.length).toBeGreaterThan(0)
    expect(colouredTicks.every(t => (t as SVGElement).getAttribute('fill') === '#ff0000')).toBe(true)
  })
})

describe('LineChartRenderer formatting options', () => {
  const renderLine = (cfg: Record<string, unknown>) =>
    render(<div style={{ width: 600, height: 400 }}><LineChartRenderer {...base} cfg={cfg} /></div>)

  it('omits the grid when turned off', () => {
    expect(renderLine({ grid: false }).container.querySelector('.recharts-cartesian-grid')).toBeNull()
  })

  it('applies a fixed y-axis domain', () => {
    // With an explicit 0-5000 domain, Recharts must pick "nice" tick values that span
    // up to 5000, whereas the auto-scaled axis only needs to span up to the data's own
    // max (1500) -- so the two tick sets differ in count/value regardless of how the
    // numbers are formatted. Comparing the tick *sets* structurally (rather than
    // asserting one exact formatted string) keeps this locale-agnostic: fmtStr formats
    // via `toLocaleString(undefined, ...)`, which follows the process's ICU default
    // locale -- ar-EG here, producing Arabic-Indic digits -- and would differ, and
    // fail, on a machine defaulting to en-US or anything else.
    const getYTicks = (cfg: Record<string, unknown>) =>
      [...renderLine(cfg).container.querySelectorAll('.recharts-yAxis .recharts-cartesian-axis-tick-value')]
        .map(t => t.textContent)
    const autoTicks = getYTicks({})
    const fixedTicks = getYTicks({ y_min: 0, y_max: 5000 })
    expect(fixedTicks).not.toEqual(autoTicks)
  })

  it('renders a data label as a child of the Line element when asked', async () => {
    // Line only emits its LabelList once its (default-active) entry animation
    // finishes, same as Bar above, so this needs waitFor. Line's default
    // animationDuration is 1500ms (vs Bar's 400ms), which exceeds waitFor's
    // default 1000ms timeout, so it needs a longer one here.
    const { container } = renderLine({ data_labels: true })
    await waitFor(() => {
      expect(container.querySelector('.recharts-line .recharts-label-list')).not.toBeNull()
    }, { timeout: 2000 })
  })
})

describe('AreaChartRenderer formatting options', () => {
  const renderArea = (cfg: Record<string, unknown>) =>
    render(<div style={{ width: 600, height: 400 }}><AreaChartRenderer {...base} cfg={cfg} /></div>)

  it('omits the grid when turned off', () => {
    expect(renderArea({ grid: false }).container.querySelector('.recharts-cartesian-grid')).toBeNull()
  })

  it('renders a data label as a child of the Area element when asked', async () => {
    // Area's default animationDuration is also 1500ms; see the Line test above.
    const { container } = renderArea({ data_labels: true })
    await waitFor(() => {
      expect(container.querySelector('.recharts-area .recharts-label-list')).not.toBeNull()
    }, { timeout: 2000 })
  })
})

describe('StepPlotRenderer formatting options', () => {
  const renderStep = (cfg: Record<string, unknown>) =>
    render(<div style={{ width: 600, height: 400 }}><StepPlotRenderer {...base} cfg={cfg} /></div>)

  it('omits the grid when turned off', () => {
    expect(renderStep({ grid: false }).container.querySelector('.recharts-cartesian-grid')).toBeNull()
  })

  it('keeps the step curve type regardless of formatting config', () => {
    const { container } = renderStep({ grid: false })
    // Recharts renders <Line type="stepAfter"> as a path whose "d" contains only
    // horizontal/vertical segments; a stray curve/monotone smoothing would introduce
    // the "C" cubic-bezier command instead.
    const path = container.querySelector('.recharts-line-curve') as SVGPathElement | null
    expect(path).not.toBeNull()
    expect(path!.getAttribute('d') ?? '').not.toContain('C')
  })
})

describe('ComparativeTimeSeriesRenderer formatting options', () => {
  const comparativeRows = [{ name: 'US', value: 1500, value2: 900 }, { name: 'CA', value: 400, value2: 300 }]
  const renderComparative = (cfg: Record<string, unknown>) =>
    render(<div style={{ width: 600, height: 400 }}><ComparativeTimeSeriesRenderer {...base} rows={comparativeRows} data={{ rows: comparativeRows }} cfg={cfg} /></div>)

  it('renders a legend by default', () => {
    expect(renderComparative({}).container.querySelector('.recharts-legend-wrapper')).not.toBeNull()
  })

  it('omits the legend when it is turned off', () => {
    expect(renderComparative({ legend: false }).container.querySelector('.recharts-legend-wrapper')).toBeNull()
  })

  it('omits the grid when turned off', () => {
    expect(renderComparative({ grid: false }).container.querySelector('.recharts-cartesian-grid')).toBeNull()
  })

  it('renders two independently orientated y-axes', () => {
    const { container } = renderComparative({})
    const yAxes = container.querySelectorAll('.recharts-yAxis')
    expect(yAxes.length).toBe(2)
    // Node count alone doesn't prove the axes sit on opposite sides -- a build that
    // flattened both onto the same orientation (the exact bug the after-the-spread
    // yAxisId/orientation re-application guards against) would still render two
    // .recharts-yAxis nodes. Recharts places a left-oriented tick's text well left of
    // center (text-anchor="end") and a right-oriented tick's text well right of center
    // (text-anchor="start"); their x coordinates diverge accordingly, so pin that they
    // actually differ and land on opposite sides of the chart's horizontal midpoint.
    const xs = [...yAxes].map(ax => Number(ax.querySelector('.recharts-cartesian-axis-tick-value')?.getAttribute('x')))
    expect(xs.every(x => !Number.isNaN(x))).toBe(true)
    expect(xs[0]).not.toBe(xs[1])
    expect(xs[0]).toBeLessThan(300)
    expect(xs[1]).toBeGreaterThan(300)
  })

  it('renders a data label on both series when asked', async () => {
    const { container } = renderComparative({ data_labels: true })
    await waitFor(() => {
      const lineLabelLists = container.querySelectorAll('.recharts-line .recharts-label-list')
      expect(lineLabelLists.length).toBe(2)
    }, { timeout: 2000 })
  })
})

describe('NumericSeriesPlotRenderer formatting options', () => {
  const numericRows = [{ x: 1, y: 1.5 }, { x: 2, y: 2.25 }, { x: 3, y: 0.75 }]
  const renderNumeric = (cfg: Record<string, unknown>) =>
    render(<div style={{ width: 600, height: 400 }}><NumericSeriesPlotRenderer {...base} rows={numericRows} data={{ rows: numericRows }} cfg={cfg} /></div>)

  it('omits the grid when turned off', () => {
    expect(renderNumeric({ grid: false }).container.querySelector('.recharts-cartesian-grid')).toBeNull()
  })

  it('still allows a fractional y-axis tick by default', () => {
    // This renderer's y-axis never set allowDecimals before, so Recharts' own default
    // (true) applied; the shared builder's default is false. Losing the after-spread
    // override would round every fractional y value to a whole number.
    const { container } = renderNumeric({})
    const yTicks = [...container.querySelectorAll('.recharts-yAxis .recharts-cartesian-axis-tick-value')]
      .map(t => t.textContent ?? '')
    expect(yTicks.some(t => /[.,٫]/.test(t))).toBe(true)
  })

  it('renders a data label on the line when asked', async () => {
    const { container } = renderNumeric({ data_labels: true })
    await waitFor(() => {
      expect(container.querySelector('.recharts-line .recharts-label-list')).not.toBeNull()
    }, { timeout: 2000 })
  })
})

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
    // Two axis nodes sharing a tick size doesn't prove they weren't both flattened onto
    // the same side -- that's exactly what the after-the-spread yAxisId/orientation
    // re-application in each renderer exists to prevent, and it's the one bug this test's
    // name claims to cover. A left-oriented tick renders with text-anchor="end" positioned
    // well left of center; a right-oriented tick renders with text-anchor="start" well
    // right of center. Pin that the two axes' tick x coordinates actually diverge and land
    // on opposite sides of the chart's horizontal midpoint.
    const xs = [...yAxes].map(ax => Number(ax.querySelector('.recharts-cartesian-axis-tick-value')?.getAttribute('x')))
    expect(xs.every(x => !Number.isNaN(x))).toBe(true)
    expect(xs[0]).not.toBe(xs[1])
    expect(xs[0]).toBeLessThan(300)
    expect(xs[1]).toBeGreaterThan(300)
  })
})

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

  it('still allows a fractional y-axis tick by default', () => {
    // Scatter's Y axis never set allowDecimals before, so Recharts' own default (true)
    // applied; the shared builder's default is false. Losing the after-spread override
    // would round every fractional y value to a whole number.
    const scatterRows = [{ x: 1, y: 1.5 }, { x: 2, y: 2.25 }, { x: 3, y: 0.75 }]
    const { container } = render(
      <div style={{ width: 600, height: 400 }}>
        <ScatterChartRenderer {...base} rows={scatterRows} data={{ rows: scatterRows }} cfg={{}} />
      </div>
    )
    const yTicks = [...container.querySelectorAll('.recharts-yAxis .recharts-cartesian-axis-tick-value')]
      .map(t => t.textContent ?? '')
    expect(yTicks.some(t => /[.,٫]/.test(t))).toBe(true)
  })
})

describe('BubbleChartRenderer formatting options', () => {
  const bubbleRows = [
    { x: 1, y: 1.5, size: 10, name: 'A' },
    { x: 2, y: 2.25, size: 20, name: 'B' },
    { x: 3, y: 0.75, size: 15, name: 'C' },
  ]
  const groupedRows = bubbleRows.map((r, i) => ({ ...r, group: i === 0 ? 'G1' : 'G2' }))

  it('still allows a fractional y-axis tick by default', () => {
    // Same divergence as Scatter: this Y axis never set allowDecimals before, so
    // Recharts' true default applied; yAxisProps defaults to false.
    const { container } = render(
      <div style={{ width: 600, height: 400 }}>
        <BubbleChartRenderer {...base} rows={bubbleRows} data={{ rows: bubbleRows }} cfg={{}} />
      </div>
    )
    const yTicks = [...container.querySelectorAll('.recharts-yAxis .recharts-cartesian-axis-tick-value')]
      .map(t => t.textContent ?? '')
    expect(yTicks.some(t => /[.,٫]/.test(t))).toBe(true)
  })

  it('omits the legend when it is turned off, even with groups present', () => {
    const render1 = () => render(
      <div style={{ width: 600, height: 400 }}>
        <BubbleChartRenderer {...base} rows={groupedRows} data={{ rows: groupedRows }} cfg={{ legend: false }} />
      </div>
    )
    expect(render1().container.querySelector('.recharts-legend-wrapper')).toBeNull()
  })

  it('renders a legend by default when groups are present', () => {
    const { container } = render(
      <div style={{ width: 600, height: 400 }}>
        <BubbleChartRenderer {...base} rows={groupedRows} data={{ rows: groupedRows }} cfg={{}} />
      </div>
    )
    expect(container.querySelector('.recharts-legend-wrapper')).not.toBeNull()
  })

  // The bug report: "the colors that act as id -- it is not measure, it is category."
  // shape_bubble marks an id-like/non-numeric color role with color_kind: "category" --
  // the renderer must paint same value -> same discrete color, not a continuous ramp.
  it('gives two rows with the same category color value the same fill', () => {
    const rows = [
      { x: 1, y: 1, size: 10, name: 'A', color: 7 },
      { x: 2, y: 2, size: 10, name: 'B', color: 9 },
      { x: 3, y: 3, size: 10, name: 'C', color: 7 },
    ]
    const { container } = render(
      <div style={{ width: 600, height: 400 }}>
        <BubbleChartRenderer {...base} rows={rows} data={{ rows, color_kind: 'category' }} cfg={{}} />
      </div>
    )
    const fills = [...container.querySelectorAll('.recharts-scatter-symbol path')].map(s => s.getAttribute('fill'))
    expect(fills.length).toBe(3)
    expect(fills[0]).toBe(fills[2])   // both color: 7
    expect(fills[0]).not.toBe(fills[1]) // color: 9 is a different value
  })

  it('still uses the continuous ramp when color_kind is measure', () => {
    const rows = [
      { x: 1, y: 1, size: 10, name: 'A', color: 0 },
      { x: 2, y: 2, size: 10, name: 'B', color: 50 },
      { x: 3, y: 3, size: 10, name: 'C', color: 100 },
    ]
    const { container } = render(
      <div style={{ width: 600, height: 400 }}>
        <BubbleChartRenderer {...base} rows={rows} data={{ rows, color_kind: 'measure' }} cfg={{}} />
      </div>
    )
    const fills = [...container.querySelectorAll('.recharts-scatter-symbol path')].map(s => s.getAttribute('fill'))
    // A ramp gives every distinct numeric value its own shade -- all three differ.
    expect(new Set(fills).size).toBe(3)
    expect(fills.every(f => f?.startsWith('rgb('))).toBe(true)
  })
})

describe('BubbleChangePlotRenderer formatting options', () => {
  const frameData = {
    frames: ['f1'],
    rows: [
      { frame: 'f1', x: 1, y: 1.5, size: 10, name: 'A' },
      { frame: 'f1', x: 2, y: 2.25, size: 20, name: 'B' },
      { frame: 'f1', x: 3, y: 0.75, size: 15, name: 'C' },
    ],
  }

  it('still allows a fractional y-axis tick by default', () => {
    // Same divergence as Scatter/Bubble: this Y axis never set allowDecimals before,
    // so Recharts' true default applied; yAxisProps defaults to false.
    const { container } = render(
      <div style={{ width: 600, height: 400 }}>
        <BubbleChangePlotRenderer {...base} data={frameData} cfg={{}} />
      </div>
    )
    const yTicks = [...container.querySelectorAll('.recharts-yAxis .recharts-cartesian-axis-tick-value')]
      .map(t => t.textContent ?? '')
    expect(yTicks.some(t => /[.,٫]/.test(t))).toBe(true)
  })
})

describe('RibbonChartRenderer formatting options', () => {
  // The ribbon renderer is hand-rolled SVG (recharts' stacking cannot rank-
  // reorder per category, which is the widget's point), so these assert its
  // own contract: RTL period reversal, rank ordering, connectors, legend.
  const ribbonData = { rows_axis: ['Q1', 'Q2', 'Q3'], cols_axis: ['A', 'B'], cells: [[10, 20], [30, 40], [5, 5]] }
  const renderRibbon = (rtl: boolean, cfg: Record<string, unknown> = {}) => render(
    <div style={{ width: 600, height: 400 }}>
      <RibbonChartRenderer {...base} data={ribbonData} rtl={rtl} cfg={cfg} />
    </div>
  ).container

  it('reverses the period order under RTL, matching every other Cartesian renderer', () => {
    const q1x = (container: HTMLElement) =>
      Number(container.querySelector('.ribbon-segment[data-period="Q1"]')?.getAttribute('x'))
    const ltr = q1x(renderRibbon(false))
    const rtl = q1x(renderRibbon(true))
    expect(Number.isNaN(ltr)).toBe(false)
    expect(Number.isNaN(rtl)).toBe(false)
    // viewBox is 640 wide: Q1 sits in the leftmost slot in LTR, rightmost in RTL.
    expect(ltr).toBeLessThan(320)
    expect(rtl).toBeGreaterThan(320)
  })

  it('stacks each period in rank order: the larger series sits on top', () => {
    const container = renderRibbon(false)
    // Q1: A=10, B=20 -> B's segment starts higher (smaller y) than A's
    const yOf = (series: string) =>
      Number(container.querySelector(`.ribbon-segment[data-period="Q1"][data-series="${series}"]`)?.getAttribute('y'))
    expect(yOf('B')).toBeLessThan(yOf('A'))
  })

  it('draws connectors between adjacent periods for each surviving series', () => {
    const container = renderRibbon(false)
    // 2 series x 2 adjacent-period gaps = 4 connectors
    expect(container.querySelectorAll('.ribbon-connector').length).toBe(4)
  })

  it('omits the grid when turned off', () => {
    const container = renderRibbon(false, { grid: false })
    expect(container.querySelector('.recharts-cartesian-grid')).toBeNull()
  })
})

describe('ScheduleChartRenderer formatting options', () => {
  const scheduleData = {
    rows: [
      { name: 'Task A', start: '2024-01-01', end: '2024-01-10' },
      { name: 'Task B', start: '2024-01-05', end: '2024-01-20' },
    ],
  }
  const renderSchedule = (cfg: Record<string, unknown>) => render(
    <div style={{ width: 600, height: 400 }}>
      <ScheduleChartRenderer {...base} data={scheduleData} cfg={cfg} />
    </div>
  )

  // ScheduleChartRenderer never set axisLine/tickLine explicitly, so Recharts' own
  // `true` defaults applied to both axes; the shared builder's defaults are
  // `false`/`false`. Missing the after-spread override that keeps them `true` would
  // make the Gantt chart's axis lines vanish on every existing schedule widget.
  it('keeps its axis lines and tick lines visible by default', () => {
    const { container } = renderSchedule({})
    expect(container.querySelectorAll('.recharts-cartesian-axis-line').length).toBe(2)
    expect(container.querySelectorAll('.recharts-cartesian-axis-tick-line').length).toBeGreaterThan(0)
  })

  // Fix round 1 (Task 9 review): ScheduleChartRenderer's tick/axisLine/tickLine used to
  // be hard-pinned to `{ fontSize: 11 }` with no fill, axisLine/tickLine forced true --
  // AFTER the builder spread, discarding axis_tick_size/axis_tick_color/axis_line/
  // tick_line even though the Formatting panel offers 'axes' for `schedule`. That was a
  // silent no-op in its own right (the exact defect class widgetCapabilities.ts exists
  // to prevent, one layer lower than the capability map). Fixed by making the historical
  // values DEFAULTS a config value can still win over, not hard-codes. This replaces the
  // old "does not apply a custom tick colour" test, which asserted the no-op as if it
  // were intended behaviour.
  it('renders its historical tick appearance (fontSize 11, Recharts\' own #666 default fill) when no formatting config is set', () => {
    // Recharts' <Text> applies its own '#666' fill whenever the tick object carries no
    // `fill` key -- true both before and after this fix, since neither the old hard-code
    // nor the new default adds a `fill` key unless axis_tick_color is set. '#666' here is
    // that Recharts default, not something this renderer ever set explicitly.
    const { container } = renderSchedule({})
    const ticks = [...container.querySelectorAll('.recharts-cartesian-axis-tick-value')]
    expect(ticks.length).toBeGreaterThan(0)
    expect(ticks.every(t => (t as SVGElement).getAttribute('font-size') === '11')).toBe(true)
    expect(ticks.every(t => (t as SVGElement).getAttribute('fill') === '#666')).toBe(true)
  })

  it('applies a custom tick colour and size once formatting config sets them', () => {
    const { container } = renderSchedule({ axis_tick_color: '#ff0000', axis_tick_size: 16 })
    const ticks = [...container.querySelectorAll('.recharts-cartesian-axis-tick-value')]
    expect(ticks.length).toBeGreaterThan(0)
    expect(ticks.every(t => (t as SVGElement).getAttribute('fill') === '#ff0000')).toBe(true)
    expect(ticks.every(t => (t as SVGElement).getAttribute('font-size') === '16')).toBe(true)
  })

  it('still keeps its axis/tick lines visible by default, and can hide them via config', () => {
    // Restates the "keeps its axis lines and tick lines visible by default" guarantee
    // above (unset config: identical to today), then proves the other half: config now
    // actually reaches these two props instead of being discarded.
    const shown = renderSchedule({}).container
    expect(shown.querySelectorAll('.recharts-cartesian-axis-line').length).toBe(2)
    expect(shown.querySelectorAll('.recharts-cartesian-axis-tick-line').length).toBeGreaterThan(0)

    const hidden = renderSchedule({ axis_line: false, tick_line: false }).container
    expect(hidden.querySelectorAll('.recharts-cartesian-axis-line').length).toBe(0)
    expect(hidden.querySelectorAll('.recharts-cartesian-axis-tick-line').length).toBe(0)
  })

  it('omits the grid when turned off', () => {
    const { container } = renderSchedule({ grid: false })
    expect(container.querySelector('.recharts-cartesian-grid')).toBeNull()
  })

  // Fix round 1, finding 1: yAxisProps wires cfg.y_scale/y_min/y_max onto whatever
  // <YAxis> it is spread onto -- including this category axis, which the brief
  // explicitly withholds a log/fixed domain from because it is meaningless on a
  // task-time axis. Recharts' parseScale maps the `scale` prop to a d3 factory
  // without consulting axis.type, so an unguarded spread would build
  // scaleLog().domain(['Task A','Task B']), coercing every category to NaN.
  // Empirically (a throwaway debug render, not committed) this doesn't just shift
  // pixels: with the guard removed, the Y axis renders ZERO ticks and the Bar
  // rectangles never paint a <path> at all -- the Gantt chart goes fully blank.
  it("keeps its category Y axis intact when y_scale is requested (log scale is meaningless on task rows)", async () => {
    const { container } = renderSchedule({ y_scale: 'log' })
    await waitFor(() => {
      expect(container.querySelectorAll('.recharts-bar-rectangle path').length).toBeGreaterThan(0)
    })
    const yTicks = [...container.querySelectorAll('.recharts-yAxis .recharts-cartesian-axis-tick-value')]
      .map(t => t.textContent ?? '')
    expect(yTicks.some(t => t.includes('Task'))).toBe(true)
  })
})

describe('a dual-axis chart titles each axis separately', () => {
  /**
   * The SAS page this was measured against titles its left axis "Profit
   * (millions)" and its right one "Number of Orders" — two different measures,
   * two different scales, two different names. Both of ours read
   * `cfg.y_axis_label`, so the only choices were one title on both axes (a
   * lie on one of them) or none at all.
   */
  const rows = [
    { name: 'January', value: 700000, value2: 60000 },
    { name: 'February', value: 620000, value2: 52000 },
  ]

  function renderDual(cfg: Record<string, unknown>) {
    return render(<DualAxisBarLineChartRenderer
      rows={rows} data={{ rows }} cfg={cfg} rtl={false} broadcasts={false}
      localSelected={null} onClickPoint={() => {}} plotW={600} plotH={300} />)
  }

  it('puts a different title on the right axis', async () => {
    const { container } = renderDual({
      measure: 'profit', measure2: 'orders',
      y_axis_label: 'Profit', y2_axis_label: 'Number of Orders',
    })
    await waitFor(() => {
      const text = container.textContent ?? ''
      expect(text).toContain('Profit')
      expect(text).toContain('Number of Orders')
    })
  })

  it('does not put the left title on the right axis', async () => {
    // The old behaviour, and the reason this was worse than no title: both
    // axes claimed to be Profit.
    const { container } = renderDual({
      measure: 'profit', measure2: 'orders', y_axis_label: 'Profit',
    })
    await waitFor(() => expect(container.textContent).toContain('Profit'))
    const titles = [...container.querySelectorAll('text')]
      .filter(t => (t.textContent ?? '').trim() === 'Profit')
    expect(titles.length).toBe(1)
  })

  it('titles only the right axis when that is all the author set', async () => {
    const { container } = renderDual({
      measure: 'profit', measure2: 'orders', y2_axis_label: 'Number of Orders',
    })
    await waitFor(() => expect(container.textContent).toContain('Number of Orders'))
  })
})

describe('a legend can be titled', () => {
  /**
   * The SAS donut this was measured against carries "Customer Age Group" under
   * its swatches, and its treemap carries "Product Category". The swatches say
   * WHICH value each colour is; the title says what the values ARE, and without
   * it a legend of "29 and below / 30-44 years" leaves the reader to infer the
   * field from the labels.
   *
   * Asserted on the BUILDER and the component rather than through a chart:
   * Recharts sizes its legend wrapper from measured layout, which is zero in
   * jsdom, so a legend rendered inside a chart here draws nothing at all — for
   * the same reason the axis planners in this file compute numeric intervals
   * instead of trusting Recharts' measured decluttering.
   */
  it('hands Recharts a content renderer only when a title is set', () => {
    expect(legendProps({ legend_title: 'Customer Age Group' } as never))
      .toHaveProperty('content')
    expect(legendProps({} as never)).not.toHaveProperty('content')
  })

  it('still returns null when the legend is switched off', () => {
    expect(legendProps({ legend: false, legend_title: 'X' } as never)).toBeNull()
  })

  it('draws the title and the entries', () => {
    const props = legendProps({ legend_title: 'Customer Age Group' } as never)!
    const content = (props as { content: (p: unknown) => React.ReactNode }).content
    const { container } = render(<>{content({ payload: [
      { value: '29 and below', color: '#111' },
      { value: '30-44 years', color: '#222' },
    ] })}</>)
    expect(container.querySelector('[data-legend-title]')).toHaveTextContent('Customer Age Group')
    expect(container.textContent).toContain('29 and below')
    expect(container.textContent).toContain('30-44 years')
  })

  it('puts the title under the entries on a bottom legend, as SAS does', () => {
    const props = legendProps({ legend_title: 'Customer Age Group' } as never)!
    const content = (props as { content: (p: unknown) => React.ReactNode }).content
    const { container } = render(<>{content({ payload: [{ value: 'A', color: '#111' }] })}</>)
    const text = (container.textContent ?? '')
    expect(text.indexOf('A')).toBeLessThan(text.indexOf('Customer Age Group'))
  })

  it('puts it above the entries when the legend is on top', () => {
    const props = legendProps({ legend_title: 'Group', legend_position: 'top' } as never)!
    const content = (props as { content: (p: unknown) => React.ReactNode }).content
    const { container } = render(<>{content({ payload: [{ value: 'A', color: '#111' }] })}</>)
    const text = (container.textContent ?? '')
    expect(text.indexOf('Group')).toBeLessThan(text.indexOf('A'))
  })

  it('survives a legend with no payload at all', () => {
    const props = legendProps({ legend_title: 'Group' } as never)!
    const content = (props as { content: (p: unknown) => React.ReactNode }).content
    const { container } = render(<>{content({})}</>)
    expect(container.querySelector('[data-legend-title]')).toBeInTheDocument()
  })
})

describe('a donut can carry its total in the middle', () => {
  /**
   * The SAS donut this was measured against reads "748K" in the hole. The ring
   * answers "how does this split"; the number in the middle answers "out of how
   * much", and without it a reader has to add the slices up themselves.
   *
   * Opt-in: this renderer has never drawn one, and an unset config must not
   * suddenly put a number in the middle of every existing donut.
   */
  const rows = [{ name: '29 and below', value: 300000 }, { name: '30-44 years', value: 448000 }]

  function renderDonut(cfg: Record<string, unknown>) {
    return render(<DonutChartRenderer
      rows={rows} data={{ rows }} cfg={cfg} rtl={false} broadcasts={false}
      localSelected={null} onClickPoint={() => {}} plotW={400} plotH={400} />)
  }

  it('sums the slices and shows the total', async () => {
    const { container } = renderDonut({ measure: 'orders', donut_total: true })
    await waitFor(() => expect(container.textContent).toContain((748000).toLocaleString()))
  })

  it('shows it in the measure’s own format, units and all', async () => {
    // 748,000 orders reads as "748K" in the hole of a donut this size, which is
    // the whole reason display units exist.
    const { container } = renderDonut({ measure: 'orders', donut_total: true,
      measureFmt: undefined })
    await waitFor(() => expect(container.textContent).toBeTruthy())
    const { container: scaled } = render(<DonutChartRenderer
      rows={rows} data={{ rows }} cfg={{ measure: 'orders', donut_total: true }}
      rtl={false} broadcasts={false} localSelected={null} onClickPoint={() => {}}
      measureFmt={{ type: 'integer', scale: 'thousands' }} plotW={400} plotH={400} />)
    await waitFor(() => expect(scaled.textContent).toContain(`${(748).toLocaleString()}K`))
  })

  it('is on by default, and draws nothing extra once turned off', async () => {
    const { container: on } = renderDonut({ measure: 'orders' })
    await waitFor(() => expect(on.textContent).toContain((748000).toLocaleString()))
    const { container } = renderDonut({ measure: 'orders', donut_total: false })
    await waitFor(() => expect(container.querySelector('svg')).not.toBeNull())
    expect(container.textContent).not.toContain((748000).toLocaleString())
  })

  it('can be given its own caption instead of the measure name', async () => {
    const { container } = renderDonut({ measure: 'orders', donut_total: true,
      donut_total_label: 'Orders' })
    await waitFor(() => expect(container.textContent).toContain('Orders'))
  })
})

describe('every chart says what its axes are', () => {
  /**
   * The titles derive from the config (axisOptions.axisTitles), but WHICH
   * title belongs on WHICH axis is the renderer's own knowledge: a dot plot
   * lays the category down the side, a histogram bins the measure along the
   * bottom and counts up the side, a bubble chart has measures on both. Only
   * a rendered chart can pin that, which is why these are here and not in the
   * unit file -- a builder test would stay green while a renderer titled the
   * wrong axis.
   */
  const cfg = { dimension: 'region', measure: 'total', aggregation: 'sum',
                measure2: 'orders' }
  const titles = (c: HTMLElement) =>
    [...c.querySelectorAll('.recharts-label')].map(el => el.textContent)

  it('a bar chart draws no derived axis titles: the card title already names it', () => {
    // The report design (2026-09-24): upright categories, value ticks, and no
    // axis titles unless the author typed one. The derived names still reach
    // the tooltip through seriesName, so the reading is never lost.
    const { container } = renderBar(cfg)
    const found = titles(container)
    expect(found).not.toContain('region')
    expect(found).not.toContain('sum(total)')
  })

  it('a dot plot, which is the same chart lying down, swaps them', () => {
    const { container } = render(
      <div style={{ width: 600, height: 400 }}>
        <DotPlotRenderer {...base} cfg={cfg} /></div>)
    // The category is on the Y axis here; the measure runs along the bottom.
    const found = titles(container)
    expect(found).toEqual(expect.arrayContaining(['region', 'sum(total)']))
  })

  it('a histogram counts rows, and says so', () => {
    const bins = [{ name: '0-10', value: 3 }, { name: '10-20', value: 5 }]
    const { container } = render(
      <div style={{ width: 600, height: 400 }}>
        <HistogramRenderer {...base} rows={bins} data={{ rows: bins }}
          cfg={{ measure: 'total' }} /></div>)
    const found = titles(container)
    // Its bins ARE the measure's values, so the measure names the x axis --
    // never the dimension, which a histogram does not have.
    expect(found).toContain('total')
    expect(found).toContain('count')
  })

  it('a bubble chart has a measure on each axis', () => {
    const points = [{ name: 'US', x: 1, y: 2, z: 3 }]
    const { container } = render(
      <div style={{ width: 600, height: 400 }}>
        <BubbleChartRenderer {...base} rows={points} data={{ rows: points }}
          cfg={cfg} /></div>)
    const found = titles(container)
    expect(found).toContain('sum(total)')
    expect(found).toContain('sum(orders)')
    // The dimension names the bubbles, not an axis.
    expect(found).not.toContain('region')
  })

  it('a dual-axis chart names its two scales separately', () => {
    const two = [{ name: 'US', value: 10, value2: 3 }]
    const { container } = render(
      <div style={{ width: 600, height: 400 }}>
        <DualAxisBarLineChartRenderer {...base} rows={two} data={{ rows: two }}
          cfg={cfg} /></div>)
    const found = titles(container)
    // The right axis is the SECOND measure -- titling it from the left one
    // would state something false about it.
    expect(found).toEqual(expect.arrayContaining(['sum(total)', 'sum(orders)']))
  })

  it('mirrors the value-axis title with the axis in RTL', () => {
    // The value axis moves to the RIGHT in a mirrored page, and the title has
    // to move and rotate with it -- pinned to the left it lands on the data.
    // A bar chart only draws titles an author typed (see above), so this
    // mirrors authored ones -- the same Label path the derived ones used.
    const { container } = render(
      <div style={{ width: 600, height: 400 }}>
        <BarChartRenderer {...base} rtl
          cfg={{ ...cfg, x_axis_label: 'region', y_axis_label: 'sum(total)' }} /></div>)
    const rotated = [...container.querySelectorAll('.recharts-label')]
      .find(el => el.textContent === 'sum(total)')
    expect(rotated).toBeTruthy()
    expect(rotated?.getAttribute('transform') ?? '').toContain('rotate(90')
    // ...and the category title is still there, unrotated.
    expect(titles(container)).toContain('region')
  })

  it('a small tile still draws its bars as well as its titles', () => {
    // A title costs 16px of height and 16px of width, so the smallest tile on
    // a dense dashboard is the one to check -- with typed titles, the only
    // ones a bar chart draws.
    const { container } = render(
      <div style={{ width: 260, height: 140 }}>
        <BarChartRenderer {...base} plotW={260} plotH={140}
          cfg={{ ...cfg, x_axis_label: 'region', y_axis_label: 'sum(total)' }} /></div>)
    expect(container.querySelectorAll('.recharts-bar-rectangle').length)
      .toBeGreaterThan(0)
    expect(titles(container)).toEqual(expect.arrayContaining(['region', 'sum(total)']))
  })

  it('an author who typed a title still gets theirs', () => {
    const { container } = renderBar({ ...cfg, x_axis_label: 'Governorate' })
    const found = titles(container)
    expect(found).toContain('Governorate')
    expect(found).not.toContain('region')
  })
})
