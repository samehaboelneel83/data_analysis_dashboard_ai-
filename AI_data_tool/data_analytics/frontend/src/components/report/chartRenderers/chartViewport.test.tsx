import { describe, it, expect, beforeAll, afterAll, vi } from 'vitest'
import { render, renderHook, act, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { autoViewport, readableCapacity, isTemporalAxis, MIN_WINDOW } from './axisOptions'
import { useChartViewport, StaticChartsContext } from './useChartViewport'
import BarChartRenderer from './BarChartRenderer'
import LineChartRenderer from './LineChartRenderer'
import AreaChartRenderer from './AreaChartRenderer'

// A congested category axis opens on a readable WINDOW with a range slider,
// instead of squeezing every point into the plot. These pin the three layers:
// the pure maths, the hook that owns the window, and what Recharts draws.

const cats = (n: number, prefix = 'Product ') => Array.from({ length: n }, (_, i) => `${prefix}${i + 1}`)
const months = (n: number) => Array.from({ length: n }, (_, i) =>
  `${2020 + Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, '0')}`)
const rowsOf = (labels: string[], extra: (i: number) => Record<string, unknown> = () => ({})) =>
  labels.map((name, i) => ({ name, value: (i % 7) + 1, ...extra(i) }))

describe('congestion is detected from the labels and the width', () => {
  it('a handful of categories fits: no window', () => {
    const v = autoViewport(cats(6), { width: 600 })
    expect(v).toEqual({ congested: false, startIndex: 0, endIndex: 5, size: 6 })
  })

  it('more categories than the width shows legibly: a window of what fits', () => {
    const labels = cats(80)
    const cap = readableCapacity(labels, { width: 600 })
    const v = autoViewport(labels, { width: 600 })
    expect(v.congested).toBe(true)
    expect(v.size).toBe(cap)
    expect(v.size).toBeLessThan(80)
    expect([v.startIndex, v.endIndex]).toEqual([0, cap - 1])
  })

  it('a wider tile shows more points; a narrower one fewer (responsive)', () => {
    const labels = cats(200)
    const narrow = autoViewport(labels, { width: 360 }).size
    const wide = autoViewport(labels, { width: 1400 }).size
    expect(wide).toBeGreaterThan(narrow)
  })

  it('never opens on fewer than MIN_WINDOW points, however little fits', () => {
    // Large axis text on the narrowest plot fits three labels; the window still shows four.
    expect(readableCapacity(cats(50), { width: 130, fontSize: 24 })).toBeLessThan(MIN_WINDOW)
    expect(autoViewport(cats(50), { width: 130, fontSize: 24 }).size).toBe(MIN_WINDOW)
  })

  it('Arabic labels (wider glyphs) get fewer points per window than Latin ones of the same length', () => {
    const latin = Array.from({ length: 100 }, (_, i) => `Governorate${i}xx`)
    const arabic = Array.from({ length: 100 }, (_, i) => `محافظةالقاهرة${i}`)
    expect(readableCapacity(arabic, { width: 700 })).toBeLessThanOrEqual(readableCapacity(latin, { width: 700 }))
  })

  it('a time axis opens on the newest points; any other axis on its first', () => {
    const t = autoViewport(months(60), { width: 500, anchor: 'end' })
    expect(t.endIndex).toBe(59)
    expect(t.startIndex).toBe(60 - t.size)
    const c = autoViewport(cats(60), { width: 500, anchor: 'start' })
    expect(c.startIndex).toBe(0)
  })

  it('recognises a time axis from the config or from the labels', () => {
    expect(isTemporalAxis({ dimension_granularity: 'month' } as never, ['a'])).toBe(true)
    expect(isTemporalAxis({} as never, months(24))).toBe(true)
    expect(isTemporalAxis({} as never, ['FY2025/26-Q1', 'FY2025/26-Q2'])).toBe(true)
    expect(isTemporalAxis({} as never, cats(24))).toBe(false)
  })
})

describe('the window the chart shows', () => {
  const view = (cfg: Record<string, unknown>, rows: Record<string, unknown>[], w = 600,
                wrapper?: ({ children }: { children: ReactNode }) => JSX.Element) =>
    renderHook(({ c, r, width }) => useChartViewport(c as never, r, width, { dataKey: 'value' }),
      { initialProps: { c: cfg, r: rows, width: w }, wrapper })

  it('congested: a slider pinned to a readable window, with every row still behind it', () => {
    const rows = rowsOf(cats(80))
    const { result } = view({}, rows)
    const b = result.current.brush!
    expect(b).toBeTruthy()
    expect(b.startIndex).toBe(0)
    expect(b.endIndex).toBe(result.current.end)
    expect(result.current.visible.length).toBe(result.current.end + 1)
    expect(result.current.visible.length).toBeLessThan(80)
    // The slider is keyed to the full series: every point is reachable.
    expect((b.children as { props: { data: unknown[] } }).props.data).toHaveLength(80)
  })

  it('not congested: no slider and the whole series', () => {
    const { result } = view({}, rowsOf(cats(5)))
    expect(result.current.brush).toBeNull()
    expect(result.current.visible).toHaveLength(5)
  })

  it('the author turned the overview axis off: no slider, ever', () => {
    const { result } = view({ overview_axis: false }, rowsOf(cats(80)))
    expect(result.current.brush).toBeNull()
    expect(result.current.visible).toHaveLength(80)
  })

  it('the author turned it on for a short series: the slider over the whole series, as before', () => {
    const { result } = view({ overview_axis: true }, rowsOf(cats(5)))
    expect(result.current.brush).toMatchObject({ startIndex: 0, endIndex: 4 })
  })

  it('on paper (the print page): every point, no slider', () => {
    const wrapper = ({ children }: { children: ReactNode }) =>
      <StaticChartsContext.Provider value={true}>{children}</StaticChartsContext.Provider>
    const { result } = view({}, rowsOf(cats(80)), 600, wrapper)
    expect(result.current.brush).toBeNull()
    expect(result.current.visible).toHaveLength(80)
  })

  it('re-fits when the tile is resized, until the reader drags', () => {
    const rows = rowsOf(cats(200))
    const { result, rerender } = view({}, rows, 400)
    const narrow = result.current.visible.length
    rerender({ c: {}, r: rows, width: 1200 })
    expect(result.current.visible.length).toBeGreaterThan(narrow)

    act(() => { result.current.brush!.onChange({ startIndex: 50, endIndex: 70 }) })
    expect([result.current.start, result.current.end]).toEqual([50, 70])
    rerender({ c: {}, r: rows, width: 500 })
    expect([result.current.start, result.current.end]).toEqual([50, 70])  // the reader's range is kept
  })

  it('new data starts again from the automatic window', () => {
    const { result, rerender } = view({}, rowsOf(cats(80)))
    act(() => { result.current.brush!.onChange({ startIndex: 60, endIndex: 79 }) })
    rerender({ c: {}, r: rowsOf(cats(90, 'Item ')), width: 600 })
    expect(result.current.start).toBe(0)
  })

  it('reports the automatic window, so the widget can say the chart is a slice', () => {
    const seen: unknown[] = []
    const onChange = vi.fn((r: unknown) => seen.push(r))
    const { result } = renderHook(() => useChartViewport({} as never, rowsOf(months(60)), 600, { dataKey: 'value', onChange }))
    // The automatic window says so: the widget shows "showing n/60" with no
    // reset, since the slider is the control.
    expect(seen.at(-1)).toMatchObject({ endIndex: 59, of: 60, end: '2024-12', auto: true })
    // A window the reader dragged to is theirs, and can be reset.
    act(() => { result.current.brush!.onChange({ startIndex: 0, endIndex: 9 }) })
    expect(seen.at(-1)).toEqual({ start: '2020-01', end: '2020-10', startIndex: 0, endIndex: 9, of: 60 })
  })

  it('reports nothing left on screen when the chart goes away', () => {
    const seen: unknown[] = []
    const { unmount } = renderHook(() => useChartViewport({} as never, rowsOf(cats(80)), 600, { onChange: r => seen.push(r) }))
    unmount()
    expect(seen.at(-1)).toBeNull()
  })
})

describe('what Recharts draws', () => {
  const original = Element.prototype.getBoundingClientRect
  beforeAll(() => {
    Element.prototype.getBoundingClientRect = () => ({
      width: 600, height: 400, top: 0, left: 0, right: 600, bottom: 400, x: 0, y: 0, toJSON() {},
    }) as DOMRect
  })
  afterAll(() => { Element.prototype.getBoundingClientRect = original })
  const base = { data: {}, cfg: {}, rtl: false, broadcasts: false, localSelected: null, onClickPoint: () => {}, plotW: 600, plotH: 400 }

  it('a congested bar chart draws a window of bars and a slider, not 80 squeezed bars', () => {
    const rows = rowsOf(cats(80))
    const { container } = render(<div style={{ width: 600, height: 400 }}><BarChartRenderer {...base} rows={rows} /></div>)
    const bars = container.querySelectorAll('.recharts-bar-rectangle').length
    expect(container.querySelector('.recharts-brush')).toBeTruthy()
    expect(bars).toBe(autoViewport(rows.map(r => r.name), { width: 600 }).size)
    expect(bars).toBeLessThan(80)
  })

  it('a short bar chart draws every bar and no slider', () => {
    const { container } = render(<div style={{ width: 600, height: 400 }}><BarChartRenderer {...base} rows={rowsOf(cats(5))} /></div>)
    expect(container.querySelector('.recharts-brush')).toBeNull()
    expect(container.querySelectorAll('.recharts-bar-rectangle')).toHaveLength(5)
  })

  it('per-bar colouring follows the bars on screen, not the first rows of the data', async () => {
    // A time axis opens on its newest months. Only those met their target; if
    // the cells were laid out from row 0, the drawn bars would say "missed".
    const labels = months(60)
    const rows = rowsOf(labels, i => ({ value: 10, target: i >= 30 ? 5 : 50 }))
    const { container } = render(<div style={{ width: 600, height: 400 }}><BarChartRenderer {...base} rows={rows} /></div>)
    // Recharts drops data-* attributes on bars; the attainment colour is the fill.
    // The bars grow in on animation frames, so wait for them to be drawn.
    const fillsNow = () => [...container.querySelectorAll('.recharts-bar-rectangle path')].map(e => e.getAttribute('fill'))
    await waitFor(() => expect(fillsNow().length).toBeGreaterThan(0), { timeout: 5000 })
    const fills = fillsNow()
    expect(fills.length).toBeLessThan(60)
    expect(new Set(fills)).toEqual(new Set(['var(--success)']))
  })

  it('several measures draw one line and one area each, with a legend', () => {
    // The server's merged shape (services/multi_measure.py): one column per measure.
    const data = { type: 'crosstab', columns: ['region', 'revenue', 'cost', '__total__'],
      rows: [['N', 30, 3, null], ['S', 300, 30, null], ['E', 7, 0.5, null]] }
    for (const R of [LineChartRenderer, AreaChartRenderer]) {
      const { container, unmount } = render(<div style={{ width: 600, height: 400 }}>
        <R {...base} rows={data.rows} data={data} /></div>)
      const cls = R === LineChartRenderer ? '.recharts-line' : '.recharts-area'
      expect(container.querySelectorAll(cls)).toHaveLength(2)
      const legend = [...container.querySelectorAll('.recharts-legend-item-text')].map(e => e.textContent)
      expect(legend).toEqual(['revenue', 'cost'])
      unmount()
    }
  })

  it('a congested line chart opens on its newest points', () => {
    const labels = months(72)
    const { container } = render(<div style={{ width: 600, height: 400 }}><LineChartRenderer {...base} rows={rowsOf(labels)} /></div>)
    expect(container.querySelector('.recharts-brush')).toBeTruthy()
    const ticks = [...container.querySelectorAll('.recharts-xAxis .recharts-cartesian-axis-tick-value')].map(t => t.textContent)
    expect(ticks).toContain('2025-12')
    expect(ticks).not.toContain('2020-01')
  })
})

describe('the value axis of a chart with several measures', () => {
  it('is not titled after the first measure alone; the legend names each series', async () => {
    const { axisTitles } = await import('./axisOptions')
    expect(axisTitles({ dimension: 'region', measure: 'revenue', aggregation: 'sum' } as never).measure).toBe('sum(revenue)')
    expect(axisTitles({ dimension: 'region', measure: 'revenue', aggregation: 'sum',
      extra_measures: ['cost'] } as never).measure).toBeUndefined()
  })
})
