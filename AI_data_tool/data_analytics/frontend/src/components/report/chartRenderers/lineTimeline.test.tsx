import { describe, expect, it, beforeAll, afterAll } from 'vitest'
import { render } from '@testing-library/react'
import LineChartRenderer from './LineChartRenderer'

/** A line that is READ: its expected range, the periods outside it and the
 *  place the level changed (server: widget_data.read_timeline). */
const original = Element.prototype.getBoundingClientRect
beforeAll(() => {
  Element.prototype.getBoundingClientRect = () => ({
    width: 600, height: 300, top: 0, left: 0, right: 600, bottom: 300, x: 0, y: 0, toJSON() {},
  }) as DOMRect
})
afterAll(() => { Element.prototype.getBoundingClientRect = original })

const base = { cfg: { dimension: 'when', measure: 'v', aggregation: 'sum' }, rtl: false, broadcasts: false,
  localSelected: null, onClickPoint: () => {}, plotW: 600, plotH: 300 }
const rows = [
  { name: 'p1', value: 100 }, { name: 'p2', value: 102, lo: 90, hi: 110 }, { name: 'p3', value: 180, lo: 90, hi: 110, anomaly: 'above' },
  { name: 'p4', value: 101, lo: 90, hi: 112 },
]

describe('LineChartRenderer, read', () => {
  it('marks the period outside its range and draws the range', () => {
    const { container } = render(<div style={{ width: 600, height: 300 }}>
      <LineChartRenderer {...(base as any)} rows={rows} data={{ type: 'series', rows }} /></div>)
    expect(container.querySelectorAll('[data-testid=anomaly-dot]').length).toBe(1)
    expect(container.querySelectorAll('path.recharts-line-curve').length).toBe(3)      // the line, and its low and high
  })

  it('a plain line has neither', () => {
    const plain = rows.map(r => ({ name: r.name, value: r.value }))
    const { container } = render(<div style={{ width: 600, height: 300 }}>
      <LineChartRenderer {...(base as any)} rows={plain} data={{ type: 'series', rows: plain }} /></div>)
    expect(container.querySelectorAll('[data-testid=anomaly-dot]').length).toBe(0)
    expect(container.querySelectorAll('path.recharts-line-curve').length).toBe(1)
  })

  it('marks where the level changed', () => {
    const { container } = render(<div style={{ width: 600, height: 300 }}>
      <LineChartRenderer {...(base as any)} rows={rows}
        data={{ type: 'series', rows, change_point: { period: 'p3', shift_pct: 42.4, before: 100, after: 142 } }} /></div>)
    expect(container.querySelector('.recharts-reference-line')).not.toBeNull()
    expect(container.textContent).toContain('+42%')
  })

  it('pins the server\'s notes to their periods and lists the sentences under the chart', () => {
    const notes = [{ n: 1, period: 'p3', kind: 'above', value: 180, text: 'p3: 180, where its history made at most 110 likely.' }]
    const { container, getByTestId } = render(<div style={{ width: 600, height: 300 }}>
      <LineChartRenderer {...(base as any)} rows={rows} data={{ type: 'series', rows, notes }} /></div>)
    expect(getByTestId('timeline-notes').textContent).toContain('at most 110 likely')
    expect(container.querySelectorAll('[data-testid=timeline-note]').length).toBe(1)
    expect(container.querySelectorAll('.recharts-reference-dot').length).toBe(1)
  })

  it('an author can turn the notes off, and a plain line has none', () => {
    const notes = [{ n: 1, period: 'p3', kind: 'above', value: 180, text: 'x' }]
    const { container } = render(<div style={{ width: 600, height: 300 }}>
      <LineChartRenderer {...(base as any)} cfg={{ ...base.cfg, timeline_notes: false }} rows={rows} data={{ type: 'series', rows, notes }} /></div>)
    expect(container.querySelector('[data-testid=timeline-notes]')).toBeNull()
  })

  it('a read line shows its whole history instead of a sliding window', () => {
    const many = Array.from({ length: 140 }, (_, i) => ({ name: `2024-W${String(i).padStart(3, '0')}`, value: 100 + (i % 5), lo: 90, hi: 110,
      ...(i === 10 ? { anomaly: 'above', value: 200 } : {}) }))
    const { container } = render(<div style={{ width: 600, height: 300 }}>
      <LineChartRenderer {...(base as any)} rows={many} data={{ type: 'series', rows: many }} /></div>)
    expect(container.querySelector('.recharts-brush')).toBeNull()
    expect(container.querySelectorAll('[data-testid=anomaly-dot]').length).toBe(1)      // near the start, and still drawn
  })
})
