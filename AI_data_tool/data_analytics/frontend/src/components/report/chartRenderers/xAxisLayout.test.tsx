import { describe, it, expect, beforeAll } from 'vitest'
import { render } from '@testing-library/react'
import BarChartRenderer from './BarChartRenderer'
import { xAxisPlan } from './axisOptions'

const H = 400, W = 600

// recharts' ResponsiveContainer renders nothing at jsdom's default 0x0, so the
// suite's standard layout shim applies here too (same pattern as
// axisOptions.integration.test.tsx).
beforeAll(() => {
  Element.prototype.getBoundingClientRect = () => ({
    width: W, height: H, top: 0, left: 0, right: W, bottom: H, x: 0, y: 0, toJSON() {},
  }) as DOMRect
})

const mk = (n: number, word: string) =>
  Array.from({ length: n }, (_, i) => ({ name: `${word} ${i + 1}`, value: 10 + i }))

function draw(rows: unknown[], cfg: Record<string, unknown> = {}) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const props: any = {
    rows, data: { rows }, cfg, rtl: false, broadcasts: false,
    localSelected: null, onClickPoint: () => {},
  }
  const { container } = render(
    <div style={{ width: W, height: H }}>
      <BarChartRenderer {...props} />
    </div>)
  const gridYs = Array.from(container.querySelectorAll('.recharts-cartesian-grid-horizontal line'))
    .map(l => Number(l.getAttribute('y1')))
  const ticks = Array.from(
    container.querySelectorAll('.recharts-xAxis .recharts-cartesian-axis-tick-value'))
  return {
    plotBottom: gridYs.length ? Math.max(...gridYs) : NaN,
    tickTexts: ticks.map(t => t.textContent ?? ''),
    title: Array.from(container.querySelectorAll('text'))
      .find(t => t.textContent === 'CATEGORY TITLE'),
  }
}

describe('the category axis does not print over the plot', () => {
  it('draws its ticks at all', () => {
    // THE regression that hid the crowding. The axis used to ask Recharts to
    // declutter from MEASURED text width ('preserveStartEnd' + minTickGap);
    // jsdom measures every string as zero wide, so the whole axis collapsed to
    // a single tick under test while a browser drew all of them. A suite that
    // renders one tick can never notice twelve of them colliding.
    expect(draw(mk(12, 'United States')).tickTexts.length).toBeGreaterThan(1)
  })

  it('draws every label when they fit, and thins them out when they do not', () => {
    const sparse = draw(mk(12, 'United States'))
    expect(sparse.tickTexts).toHaveLength(12)

    const dense = draw(mk(200, 'US'))
    const plan = xAxisPlan(mk(200, 'US').map(r => r.name), { fontSize: 10 })
    expect(plan.interval).toBeGreaterThan(0)
    expect(dense.tickTexts.length).toBeLessThan(200)
    expect(dense.tickTexts.length).toBeGreaterThan(0)
  })

  it('gives the axis title a lane of its own instead of letting labels sit on it', () => {
    // The title is drawn at the bottom of the tick band ('insideBottom' of
    // the axis box) while the tick labels hang down from its top, so without
    // a lane of its own the lowest tilted label landed on the title's
    // baseline. The lane (X_TITLE_H) is added to the axis height.
    const withTitle = draw(mk(12, 'United States'), { x_axis_label: 'CATEGORY TITLE' })
    const without = draw(mk(12, 'United States'))
    expect(withTitle.title).toBeTruthy()
    // A reserved lane means the plot ends HIGHER up the card.
    expect(withTitle.plotBottom).toBeLessThan(without.plotBottom)
  })

  it('costs a chart nothing when it has no axis title', () => {
    const plain = draw(mk(12, 'United States'))
    expect(plain.title).toBeUndefined()
    expect(Number.isFinite(plain.plotBottom)).toBe(true)
  })

  it('gives more of the card back to short labels than to long ones', () => {
    // Short labels stay upright and need a shallow band; long ones tilt and
    // need a deep one. The old code reserved a flat 52px for both.
    const short = draw(mk(6, 'US')).plotBottom
    const long = draw(mk(60, 'United States of America West')).plotBottom
    expect(short).toBeGreaterThan(long)
  })

  it('ellipsises labels too long to fit rather than overrunning the band', () => {
    const { tickTexts } = draw(mk(30, 'United States of America, Western Region'))
    expect(tickTexts.length).toBeGreaterThan(0)
    expect(tickTexts.some(t => t.endsWith('…'))).toBe(true)
    // and nothing survives at its full untruncated length
    expect(tickTexts.every(t => t.length <= 40)).toBe(true)
  })
})
