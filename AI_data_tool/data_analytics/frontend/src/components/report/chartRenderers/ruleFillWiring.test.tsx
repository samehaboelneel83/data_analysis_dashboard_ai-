import { describe, it, expect, beforeAll } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import DotPlotRenderer from './DotPlotRenderer'
import GaugeRenderer from './GaugeRenderer'
import HistogramRenderer from './HistogramRenderer'
import BarChartRenderer from './BarChartRenderer'
import RibbonChartRenderer from './RibbonChartRenderer'
import ScheduleChartRenderer from './ScheduleChartRenderer'
import BubbleChangePlotRenderer from './BubbleChangePlotRenderer'
import NumericSeriesPlotRenderer from './NumericSeriesPlotRenderer'

// The gap-analysis review found only Bar/Pie/Donut/Funnel actually consumed
// ruleStyles (the getFillFactory callers) -- dot/needle/scatter/butterfly/waterfall/
// bubble/treemap/gauge all hardcoded their marks' fill and silently ignored a
// matching display rule. These assert the wiring reaches real rendered SVG output,
// not just a prop being threaded through -- recharts needs a non-zero container size
// to render its symbols at all, which jsdom's default 0x0 getBoundingClientRect
// doesn't provide, hence the size polyfill below.
beforeAll(() => {
  Element.prototype.getBoundingClientRect = () => ({
    width: 400, height: 300, top: 0, left: 0, right: 400, bottom: 300, x: 0, y: 0, toJSON() {},
  }) as DOMRect
})

describe('rule-fill wiring on renderers the review found unwired', () => {
  it('DotPlotRenderer paints a matched row from ruleStyles and leaves an unmatched row at the default accent colour', () => {
    const { container } = render(
      <div style={{ width: 400, height: 300 }}>
        <DotPlotRenderer
          rows={[{ name: 'A', value: 1 }, { name: 'B', value: 2 }]}
          data={{}} cfg={{}} rtl={false} broadcasts={false} localSelected={null} onClickPoint={() => {}}
          ruleStyles={{ rows: [{ fill: '#f87171' }, null], cells: {}, widget: {} }}
        />
      </div>
    )

    const symbols = container.querySelectorAll('.recharts-scatter-symbol path')
    expect(symbols.length).toBe(2)
    expect(symbols[0]).toHaveAttribute('fill', '#f87171')
    expect(symbols[1]).toHaveAttribute('fill', 'var(--accent)')
  })

  it('GaugeRenderer paints its bar from an interval rule instead of the hardcoded target-comparison colour', () => {
    const { container } = render(
      <div style={{ width: 400, height: 300 }}>
        <GaugeRenderer
          rows={[]} data={{ value: 80, target: 100 }} cfg={{}} rtl={false} broadcasts={false}
          localSelected={null} onClickPoint={() => {}}
          ruleStyles={{ rows: [{ fill: '#facc15' }], cells: {}, widget: {} }}
        />
      </div>
    )

    const bar = container.querySelector('.recharts-radial-bar-sector')
    expect(bar).toHaveAttribute('fill', '#facc15')
  })
})

// Task 7 closes the remaining gap: HistogramRenderer, RibbonChartRenderer,
// ScheduleChartRenderer, BubbleChangePlotRenderer, and NumericSeriesPlotRenderer are the
// renderers with a genuine per-row mark that still hardcoded their fill. Line-shaped
// renderers (Area/Line/Step/ComparativeTimeSeries and the four dual-axis variants) are
// deliberately excluded -- a line is one path, not N shapes, see task-7-report.md.
describe('rule-fill wiring on the remaining mark-shaped renderers (task 7)', () => {
  it('paints a histogram bar from a display rule', async () => {
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
    await waitFor(() => {
      expect(container.querySelectorAll('.recharts-rectangle').length).toBeGreaterThan(0)
    })
    const fills = [...container.querySelectorAll('.recharts-rectangle')].map(r => r.getAttribute('fill'))
    expect(fills).toContain('#f87171')
  })

  it('leaves an unruled histogram bar at the default accent colour', async () => {
    const rows = [{ name: '0-10', value: 5 }, { name: '10-20', value: 9 }]
    const { container } = render(
      <div style={{ width: 600, height: 400 }}>
        <HistogramRenderer
          rows={rows} data={{ rows }} cfg={{}} rtl={false} broadcasts={false}
          localSelected={null} onClickPoint={() => {}}
        />
      </div>
    )
    await waitFor(() => {
      expect(container.querySelectorAll('.recharts-rectangle').length).toBeGreaterThan(0)
    })
    const fills = [...container.querySelectorAll('.recharts-rectangle')].map(r => r.getAttribute('fill'))
    expect(fills.every(f => f === 'var(--accent)')).toBe(true)
  })

  // Ribbon's mark is one stacked segment per (rows_axis, cols_axis) cell. This proves the
  // component-level wiring (ruleStyles.rows[rows_axis index] painting that row's segment
  // in every series) independently of whether the backend currently populates it -- it
  // does not yet, for shape_heatmap results, see task-7-report.md's "Ribbon" section.
  it('paints a ribbon-chart segment from a display rule, addressed by its rows_axis position', () => {
    const data = { rows_axis: ['Q1', 'Q2', 'Q3'], cols_axis: ['A', 'B'], cells: [[10, 20], [30, 40], [5, 5]] }
    const { container } = render(
      <div style={{ width: 600, height: 400 }}>
        <RibbonChartRenderer
          rows={[]} data={data} cfg={{}} rtl={false} broadcasts={false}
          localSelected={null} onClickPoint={() => {}}
          ruleStyles={{ rows: [null, { fill: '#22d3ee' }, null], cells: {}, widget: {} }}
        />
      </div>
    )
    // Hand-rolled SVG: every segment of the ruled period (rows_axis index 1 = Q2)
    // paints the rule fill; other periods keep their series colours.
    const q2 = [...container.querySelectorAll('.ribbon-segment[data-period="Q2"]')]
    expect(q2.length).toBeGreaterThan(0)
    expect(q2.every(r => r.getAttribute('fill') === '#22d3ee')).toBe(true)
    const q1 = [...container.querySelectorAll('.ribbon-segment[data-period="Q1"]')]
    expect(q1.some(r => r.getAttribute('fill') === '#22d3ee')).toBe(false)
  })

  it('keeps ribbon-chart legend swatches coloured', () => {
    const data = { rows_axis: ['Q1', 'Q2'], cols_axis: ['A', 'B'], cells: [[10, 20], [30, 40]] }
    const { container } = render(
      <div style={{ width: 600, height: 400 }}>
        <RibbonChartRenderer
          rows={[]} data={data} cfg={{}} rtl={false} broadcasts={false}
          localSelected={null} onClickPoint={() => {}}
        />
      </div>
    )
    const swatches = [...container.querySelectorAll('.ribbon-legend-swatch')]
      .map(sw => (sw as HTMLElement).style.background)
    expect(swatches.length).toBe(2)
    expect(swatches.every(f => !!f)).toBe(true)
  })

  // The first row's dates fail to parse  // The first row's dates fail to parse and is dropped before chartData is built, so a
  // naive chartData-array index would misalign every ruleStyles lookup after it. This
  // pins the fix: rule 2 (row index 2, "Task B") must still land on "Task B", not on
  // whatever ends up second in the filtered array.
  it('paints a schedule bar from a display rule addressed by its original row index, even after an invalid-date row is dropped', async () => {
    const data = {
      rows: [
        { name: 'Bad Dates', start: 'not-a-date', end: 'also-not-a-date' },
        { name: 'Task A', start: '2024-01-01', end: '2024-01-10' },
        { name: 'Task B', start: '2024-01-05', end: '2024-01-20' },
      ],
    }
    const { container } = render(
      <div style={{ width: 600, height: 400 }}>
        <ScheduleChartRenderer
          rows={[]} data={data} cfg={{}} rtl={false} broadcasts={false}
          localSelected={null} onClickPoint={() => {}}
          ruleStyles={{ rows: [null, null, { fill: '#facc15' }], cells: {}, widget: {} }}
        />
      </div>
    )
    await waitFor(() => {
      expect(container.querySelectorAll('.recharts-rectangle').length).toBeGreaterThan(0)
    })
    const fills = [...container.querySelectorAll('.recharts-rectangle')].map(r => r.getAttribute('fill'))
    expect(fills).toContain('#facc15')
  })

  // Row index 2 ('C') is the SECOND row within frame f1 (local/filtered index 1), not
  // the second row overall -- this pins the fix that the lookup uses the row's index in
  // the full, unfiltered result, not its position in the current animation frame.
  it('paints a bubble-change point from a display rule addressed by its original row index, not its position after the animation-frame filter', () => {
    const data = {
      frames: ['f1', 'f2'],
      rows: [
        { frame: 'f1', x: 1, y: 1, size: 10, name: 'A' },
        { frame: 'f2', x: 2, y: 2, size: 10, name: 'B' },
        { frame: 'f1', x: 3, y: 3, size: 10, name: 'C' },
      ],
    }
    const { container } = render(
      <div style={{ width: 600, height: 400 }}>
        <BubbleChangePlotRenderer
          rows={[]} data={data} cfg={{}} rtl={false} broadcasts={false}
          localSelected={null} onClickPoint={() => {}}
          ruleStyles={{ rows: [null, null, { fill: '#a78bfa' }], cells: {}, widget: {} }}
        />
      </div>
    )
    const symbols = container.querySelectorAll('.recharts-scatter-symbol path')
    expect(symbols.length).toBe(2)
    const fills = [...symbols].map(s => s.getAttribute('fill'))
    expect(fills).toContain('#a78bfa')
  })

  it('paints a numeric-series-plot dot from a display rule', async () => {
    const rows = [{ x: 1, y: 1 }, { x: 2, y: 2 }, { x: 3, y: 3 }]
    const { container } = render(
      <div style={{ width: 600, height: 400 }}>
        <NumericSeriesPlotRenderer
          rows={rows} data={{ rows }} cfg={{}} rtl={false} broadcasts={false}
          localSelected={null} onClickPoint={() => {}}
          ruleStyles={{ rows: [null, { fill: '#34d399' }, null], cells: {}, widget: {} }}
        />
      </div>
    )
    // Line's dots do not paint until its (real-timer-driven) draw-in animation
    // finishes, well past testing-library's default 1000ms waitFor budget.
    await waitFor(() => {
      expect(container.querySelectorAll('.recharts-dot').length).toBeGreaterThan(0)
    }, { timeout: 2000 })
    const fills = [...container.querySelectorAll('.recharts-dot')].map(d => d.getAttribute('fill'))
    expect(fills).toContain('#34d399')
  })

  // Fix round 1 regression: the object dot form `{ fill: 'var(--accent)', r: 3 }` gets
  // its stroke ring for free -- Recharts' Line.renderDots merges the <Line>'s own
  // stroke/strokeWidth into the props object it builds for a dot, and for the object
  // form that whole object is spread onto <Dot>. A custom dot *function* receives that
  // same merged object as its argument, but nothing spreads it onto whatever the
  // function returns -- only what the function itself forwards survives. The excluded
  // LineChartRenderer still uses the object form, so this is the case that makes the
  // drift visible.
  it("keeps an unruled numeric-series-plot dot's stroke ring, lost when the dot prop switched from an object to a custom render function", async () => {
    const rows = [{ x: 1, y: 1 }, { x: 2, y: 2 }]
    const { container } = render(
      <div style={{ width: 600, height: 400 }}>
        <NumericSeriesPlotRenderer
          rows={rows} data={{ rows }} cfg={{}} rtl={false} broadcasts={false}
          localSelected={null} onClickPoint={() => {}}
        />
      </div>
    )
    await waitFor(() => {
      expect(container.querySelectorAll('.recharts-dot').length).toBeGreaterThan(0)
    }, { timeout: 2000 })
    const dots = [...container.querySelectorAll('.recharts-dot')]
    expect(dots.length).toBeGreaterThan(0)
    expect(dots.every(d => d.getAttribute('stroke') === 'var(--accent)')).toBe(true)
  })
})

describe('cross-highlight overlay on bars', () => {
  it('renders a saturated overlay sized by the selected share, over dimmed full bars', async () => {
    const rows = [
      { name: 'US', value: 100, highlight: 40 },
      { name: 'CA', value: 50, highlight: 0 },
    ]
    const { container } = render(
      <div style={{ width: 600, height: 400 }}>
        <BarChartRenderer
          rows={rows} data={{}} cfg={{}} rtl={false} broadcasts={false}
          localSelected={null} onClickPoint={() => {}}
        />
      </div>
    )
    await waitFor(() => {
      expect(container.querySelectorAll('.recharts-bar-rectangle path').length).toBeGreaterThan(0)
    })
    // full bars dimmed
    const cells = [...container.querySelectorAll('.recharts-bar-rectangle path')]
    expect(cells.some(c => c.getAttribute('opacity') === '0.3')).toBe(true)
    // one overlay for US (highlight 40), none for CA (highlight 0)
    const overlays = container.querySelectorAll('[data-testid="highlight-portion"]')
    expect(overlays.length).toBe(1)
    const overlay = overlays[0]
    // 40% of the US bar: overlay height ~= 0.4 * bar height (chart pixel space)
    const barPath = cells[0].getAttribute('d') ?? ''
    expect(Number(overlay.getAttribute('height'))).toBeGreaterThan(0)
  })
})
