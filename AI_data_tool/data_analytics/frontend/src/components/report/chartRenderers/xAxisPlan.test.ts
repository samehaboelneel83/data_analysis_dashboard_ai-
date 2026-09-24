import { describe, it, expect } from 'vitest'
import { xAxisPlan, xAxisProps, clipLabel } from './axisOptions'

const mk = (n: number, word: string) => Array.from({ length: n }, (_, i) => `${word} ${i + 1}`)

/**
 * The planner is asserted directly, NOT through a rendered chart, and that is
 * deliberate: jsdom reports zero for every text metric, so a chart rendered
 * under test cannot show whether labels would have collided. Testing the
 * decision function is the only way this behaviour can be defended at all --
 * which is precisely why the old measured `preserveStartEnd` path shipped
 * crowded axes with a green suite.
 */
describe('xAxisPlan keeps category labels off each other', () => {
  it('leaves short labels upright rather than tilting them for no reason', () => {
    const p = xAxisPlan(mk(6, 'US'), { fontSize: 10, width: 560 })
    expect(p.angle).toBe(0)
    expect(p.textAnchor).toBe('middle')
    expect(p.interval).toBe(0)          // every label drawn
    expect(p.height).toBeLessThan(52)   // and the old fixed band is given back
  })

  it('rotates only once the labels stop fitting side by side', () => {
    const upright = xAxisPlan(mk(3, 'United States'), { fontSize: 10, width: 560 })
    const tilted = xAxisPlan(mk(12, 'United States'), { fontSize: 10, width: 560 })
    expect(upright.angle).toBe(0)
    expect(tilted.angle).toBeLessThan(0)
    // Rotating buys room, so nothing has to be dropped at this density.
    expect(tilted.interval).toBe(0)
  })

  it('escalates to steeper angles before it drops any label', () => {
    const medium = xAxisPlan(mk(12, 'United States'), { fontSize: 10, width: 560 })
    const dense = xAxisPlan(mk(30, 'United States'), { fontSize: 10, width: 560 })
    expect(Math.abs(dense.angle)).toBeGreaterThan(Math.abs(medium.angle))
    expect(dense.interval).toBe(0)      // still every label
  })

  it('skips ticks only when even vertical text collides', () => {
    const p = xAxisPlan(mk(200, 'US'), { fontSize: 10, width: 560 })
    expect(p.angle).toBe(-90)
    expect(p.interval).toBeGreaterThan(0)
    // Whatever survives must actually have room: interval counts SKIPPED ticks,
    // so the pitch between drawn labels is (interval + 1) slots.
    const pitch = (560 / 200) * (p.interval + 1)
    expect(pitch).toBeGreaterThanOrEqual(10 + 2)
  })

  it('grows the band for tilted labels instead of letting them overrun it', () => {
    const upright = xAxisPlan(mk(6, 'US'), { fontSize: 10, width: 560 })
    const tilted = xAxisPlan(mk(12, 'United States'), { fontSize: 10, width: 560 })
    expect(tilted.height).toBeGreaterThan(upright.height)
  })

  it('caps the band so the labels cannot eat the plot, clipping instead', () => {
    const p = xAxisPlan(mk(12, 'United States of America, Western Region'), { fontSize: 10, width: 560 })
    expect(p.height).toBeLessThanOrEqual(96)
    expect(Number.isFinite(p.maxChars)).toBe(true)
    expect(p.maxChars).toBeGreaterThanOrEqual(3)
  })

  it('honours an explicit author angle over the ladder', () => {
    const p = xAxisPlan(mk(12, 'United States'), { fontSize: 10, width: 560, angle: -45 })
    expect(p.angle).toBe(-45)
  })

  it('still protects an author who pins labels upright at high density', () => {
    // The angle is theirs; the collision maths is not negotiable.
    const p = xAxisPlan(mk(200, 'US'), { fontSize: 10, width: 560, angle: 0 })
    expect(p.angle).toBe(0)
    expect(p.interval).toBeGreaterThan(0)
  })

  it('mirrors the tilt anchor in a right-to-left page', () => {
    const ltr = xAxisPlan(mk(12, 'United States'), { fontSize: 10, width: 560 })
    const rtl = xAxisPlan(mk(12, 'United States'), { fontSize: 10, width: 560, rtl: true })
    expect(ltr.textAnchor).toBe('end')
    expect(rtl.textAnchor).toBe('start')
  })

  it('does not tilt an upright axis just because the page is mirrored', () => {
    const rtl = xAxisPlan(mk(4, 'US'), { fontSize: 10, width: 560, rtl: true })
    expect(rtl.angle).toBe(0)
    expect(rtl.textAnchor).toBe('middle')
  })

  it('survives an empty axis without dividing by zero', () => {
    const p = xAxisPlan([], { fontSize: 10, width: 560 })
    expect(Number.isFinite(p.height)).toBe(true)
    expect(p.interval).toBe(0)
  })

  it('accounts for a larger tick font needing more room', () => {
    const small = xAxisPlan(mk(12, 'United States'), { fontSize: 8, width: 560 })
    const large = xAxisPlan(mk(12, 'United States'), { fontSize: 16, width: 560 })
    expect(large.height).toBeGreaterThan(small.height)
  })

  it('gives a narrow chart a denser plan than a wide one', () => {
    const wide = xAxisPlan(mk(20, 'United States'), { fontSize: 10, width: 1200 })
    const narrow = xAxisPlan(mk(20, 'United States'), { fontSize: 10, width: 200 })
    expect(narrow.interval).toBeGreaterThanOrEqual(wide.interval)
    expect(Math.abs(narrow.angle)).toBeGreaterThanOrEqual(Math.abs(wide.angle))
  })
})

describe('clipLabel', () => {
  it('leaves a label that fits completely alone', () => {
    expect(clipLabel('Cairo', 10)).toBe('Cairo')
  })
  it('ellipsises a label that does not fit', () => {
    const out = clipLabel('United States of America', 10)
    expect(out).toHaveLength(10)
    expect(out.endsWith('…')).toBe(true)
  })
  it('is a no-op when the plan set no limit', () => {
    expect(clipLabel('United States of America', Infinity)).toBe('United States of America')
  })
})

describe('the Formatting panel angle actually reaches the axis', () => {
  it('pins the angle the author chose', () => {
    // Guards the "shipped a config key with no effect" failure mode: the panel
    // writes cfg.x_axis_angle, and xAxisProps must honour it.
    const labels = Array.from({ length: 6 }, (_, i) => `US ${i + 1}`)
    expect(xAxisProps({}, false, labels).angle).toBe(0)             // auto: they fit
    expect(xAxisProps({ x_axis_angle: -90 } as never, false, labels).angle).toBe(-90)
    expect(xAxisProps({ x_axis_angle: -45 } as never, false, labels).angle).toBe(-45)
  })

  it('leaves a numeric x axis alone, which passes no labels', () => {
    const p = xAxisProps({}, false)
    expect(p.angle).toBeUndefined()
    expect(p.interval).toBe('preserveStartEnd')
  })
})

describe('thinning keeps both ends of the axis', () => {
  const labels = Array.from({ length: 200 }, (_, i) => `US ${i + 1}`)

  it('names the surviving labels instead of letting Recharts walk past the last', () => {
    // Measured: Recharts' own interval walk ends at Cat11 of 12 at interval 1,
    // Cat10 at interval 2, Cat9 at interval 3 -- the final category, which on
    // a time series is the newest point, is silently dropped.
    const p = xAxisPlan(labels, { fontSize: 10, width: 560 })
    expect(p.ticks).toBeDefined()
    expect(p.ticks![0]).toBe('US 1')
    expect(p.ticks![p.ticks!.length - 1]).toBe('US 200')
  })

  it('spaces the survivors evenly', () => {
    const p = xAxisPlan(labels, { fontSize: 10, width: 560 })
    const idx = p.ticks!.map(t => labels.indexOf(t))
    const gaps = idx.slice(1).map((v, i) => v - idx[i])
    // Every gap is the stride, except possibly the first, which absorbs the
    // remainder when index 0 is added back.
    expect(new Set(gaps.slice(1)).size).toBe(1)
  })

  it('does not name ticks when nothing has to be dropped', () => {
    expect(xAxisPlan(Array.from({ length: 6 }, (_, i) => `US ${i}`),
      { fontSize: 10, width: 560 }).ticks).toBeUndefined()
  })

  it('hands the axis the named ticks with interval 0 so all of them draw', () => {
    const p = xAxisProps({}, false, labels)
    expect(p.interval).toBe(0)
    expect((p as { ticks?: string[] }).ticks).toBeDefined()
    expect((p as { ticks?: string[] }).ticks!.at(-1)).toBe('US 200')
  })
})
