import { describe, it, expect, beforeAll } from 'vitest'
import { render } from '@testing-library/react'
import DotPlotRenderer from './DotPlotRenderer'
import { yCategoryPlan, yTickCount, yAxisProps } from './axisOptions'

const W = 600, H = 400
beforeAll(() => {
  Element.prototype.getBoundingClientRect = () => ({
    width: W, height: H, top: 0, left: 0, right: W, bottom: H, x: 0, y: 0, toJSON() {},
  }) as DOMRect
})

const LONG = [
  'Engineering and Product Development',
  'Sales',
  'Customer Success and Support Operations',
]

describe('yCategoryPlan sizes the gutter to the names it must draw', () => {
  it('gives long names more room than short ones', () => {
    const short = yCategoryPlan(['A', 'B', 'C'], { fontSize: 10 })
    const long = yCategoryPlan(LONG, { fontSize: 10 })
    expect(long.width).toBeGreaterThan(short.width)
  })

  it('never returns less than the Recharts default gutter', () => {
    expect(yCategoryPlan(['A'], { fontSize: 10 }).width).toBeGreaterThanOrEqual(60)
  })

  it('caps the gutter and ellipsises rather than eating the plot', () => {
    const p = yCategoryPlan(['A department name far longer than any chart should try to show in full'],
      { fontSize: 10 })
    expect(p.width).toBeLessThanOrEqual(180 + 16)
    expect(Number.isFinite(p.maxChars)).toBe(true)
    expect(p.maxChars).toBeGreaterThanOrEqual(3)
  })

  it('reserves a lane for the axis title instead of letting labels run under it', () => {
    const bare = yCategoryPlan(LONG, { fontSize: 10 })
    const titled = yCategoryPlan(LONG, { fontSize: 10, hasTitle: true })
    expect(titled.width).toBeGreaterThan(bare.width)
  })

  it('thins the labels only when they collide vertically', () => {
    // Category labels stack, so they collide on HEIGHT. Rotation is not a
    // fallback here: a sideways label beside a horizontal bar is unreadable.
    expect(yCategoryPlan(LONG, { fontSize: 10, height: 400 }).interval).toBe(0)
    const crowded = yCategoryPlan(Array.from({ length: 80 }, (_, i) => `Row ${i}`),
      { fontSize: 10, height: 200 })
    expect(crowded.interval).toBeGreaterThan(0)
  })

  it('thins more on a short tile than a tall one, from the MEASURED height', () => {
    // The previous assertion passed whether or not the measured height was
    // actually used -- both branches landed on the same interval, so a
    // sabotage that ignored  entirely went undetected. This compares
    // two heights directly, so only real use of the measurement satisfies it.
    const rows = Array.from({ length: 20 }, (_, i) => `Row ${i}`)
    const tall = yCategoryPlan(rows, { fontSize: 10, height: 400 })
    const short = yCategoryPlan(rows, { fontSize: 10, height: 150 })
    expect(short.interval).toBeGreaterThan(tall.interval)
  })

  it('survives an empty axis', () => {
    expect(yCategoryPlan([], { fontSize: 10 }).width).toBe(60)
  })
})

describe('yTickCount thins a short chart without touching a normal one', () => {
  it('keeps the Recharts default of 5 at ordinary heights', () => {
    expect(yTickCount(400)).toBe(5)
    expect(yTickCount(undefined)).toBe(5)
  })
  it('reduces the count when the chart is too short to separate them', () => {
    expect(yTickCount(120)).toBeLessThan(5)
    expect(yTickCount(60)).toBeLessThanOrEqual(2)
  })
  it('never drops below two, which is what makes a scale a scale', () => {
    expect(yTickCount(10)).toBe(2)
  })
  it('asks for fewer ticks when the tick font is larger', () => {
    expect(yTickCount(150, 20)).toBeLessThanOrEqual(yTickCount(150, 8))
  })
})

describe('the value axis reserves room for its own title', () => {
  it('widens the gutter when a title is set', () => {
    const bare = yAxisProps({}, false, undefined, [2_000_000]).width
    const titled = yAxisProps({ y_axis_label: 'Revenue' }, false, undefined, [2_000_000]).width
    expect(titled).toBeGreaterThan(bare as number)
  })

  it('pins an explicit author angle and leaves automatic alone', () => {
    expect((yAxisProps({}, false, undefined, [10]) as { angle?: number }).angle).toBeUndefined()
    expect((yAxisProps({ y_axis_angle: -45 } as never, false, undefined, [10]) as { angle?: number }).angle)
      .toBe(-45)
  })

  it('uses a deterministic tick count rather than measured decluttering', () => {
    const p = yAxisProps({}, false, undefined, [10]) as { interval: number; tickCount: number }
    expect(p.interval).toBe(0)
    expect(p.tickCount).toBe(5)
  })
})

describe('a horizontal-bar chart draws its category names on the card', () => {
  it('keeps the longest name inside the gutter it was given', () => {
    const rows = LONG.map((name, i) => ({ name, value: 90 - i * 20 }))
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const props: any = { rows, data: { rows }, cfg: {}, rtl: false, broadcasts: false,
      localSelected: null, onClickPoint: () => {} }
    const { container } = render(<div style={{ width: W, height: H }}><DotPlotRenderer {...props} /></div>)
    const ticks = Array.from(
      container.querySelectorAll('.recharts-yAxis .recharts-cartesian-axis-tick-value'))
    expect(ticks.length).toBeGreaterThan(0)
    for (const t of ticks) {
      const endX = Number(t.getAttribute('x'))
      const text = t.textContent ?? ''
      // Right-anchored, so the label runs leftward from x. Before the gutter
      // was sized from the labels this evaluated to -127: 127px off the card.
      const startX = endX - text.length * 10 * 0.62
      expect(startX).toBeGreaterThanOrEqual(0)
    }
  })
})

describe('the value axis thins its ticks on a short tile', () => {
  it('asks for fewer ticks when the measured height is small', () => {
    const tall = yAxisProps({}, false, undefined, [10], undefined, { height: 400 })
    const short = yAxisProps({}, false, undefined, [10], undefined, { height: 140 })
    expect((short as { tickCount: number }).tickCount)
      .toBeLessThan((tall as { tickCount: number }).tickCount)
  })

  it('nets the category band off the tile before deciding', () => {
    // The value axis only gets the height left after the x-axis band, legend
    // and margins, so a 140px tile is not 140px of plot.
    expect((yAxisProps({}, false, undefined, [10], undefined, { height: 140 }) as
      { tickCount: number }).tickCount).toBeLessThanOrEqual(3)
  })

  it('falls back to the Recharts default when nothing measured yet', () => {
    // The measurement lands a frame after mount; until then a chart must look
    // exactly as it always has.
    expect((yAxisProps({}, false, undefined, [10]) as { tickCount: number }).tickCount).toBe(5)
  })
})
