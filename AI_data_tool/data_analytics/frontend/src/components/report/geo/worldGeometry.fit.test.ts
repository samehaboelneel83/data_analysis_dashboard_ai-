import { describe, it, expect } from 'vitest'
import { fittedProjection, countryBoundsPoints, matchCountry } from './worldGeometry'

/**
 * A map should frame the data it is drawing.
 *
 * Every map widget fitted the projection to the whole world regardless of what
 * it plotted, so a hospital's referral map — every point inside Egypt — drew a
 * world map with a speck on it. Six maps on one dashboard, each showing the
 * Pacific Ocean at full size and the actual subject at about four pixels.
 *
 * Passing the plotted coordinates makes the projection frame them instead. With
 * nothing to frame it still fits the world, which is what a map with no rows
 * should show.
 */
const W = 400, H = 300

// Referring clinics across Egypt: roughly 25-32E, 24-31N.
const EGYPT: [number, number][] = [
  [31.24, 30.05],  // Cairo
  [29.92, 31.20],  // Alexandria
  [32.90, 24.09],  // Aswan
  [25.69, 25.69],  // Kharga
]

function spanOf(pts: [number, number][], focus?: [number, number][]) {
  const { projection } = fittedProjection(W, H, focus)
  const xy = pts.map(p => projection(p)!).filter(Boolean)
  const xs = xy.map(p => p[0]), ys = xy.map(p => p[1])
  return { w: Math.max(...xs) - Math.min(...xs), h: Math.max(...ys) - Math.min(...ys), xy }
}

describe('a map fitted to its own data', () => {
  it('fills the box along whichever dimension constrains it', () => {
    // A roughly square country in a 4:3 box is limited by height, so demanding
    // that BOTH dimensions fill would be demanding the map distort the geometry.
    // What "fitted" means is that the binding dimension is used up.
    const { w, h } = spanOf(EGYPT, EGYPT)
    expect(Math.max(w / W, h / H)).toBeGreaterThan(0.6)
  })

  it('is dramatically tighter than the world fit it replaces', () => {
    const world = spanOf(EGYPT)
    const fitted = spanOf(EGYPT, EGYPT)
    expect(fitted.w).toBeGreaterThan(world.w * 5)
  })

  it('keeps every point inside the box', () => {
    const { xy } = spanOf(EGYPT, EGYPT)
    for (const [x, y] of xy) {
      expect(x).toBeGreaterThanOrEqual(0); expect(x).toBeLessThanOrEqual(W)
      expect(y).toBeGreaterThanOrEqual(0); expect(y).toBeLessThanOrEqual(H)
    }
  })

  it('frames the data in a wide short box, not a leftover 16:9 world', () => {
    const wide = 800, short = 160
    const { projection } = fittedProjection(wide, short, EGYPT)
    const xy = EGYPT.map(p => projection(p)!).filter(Boolean)
    for (const [x, y] of xy) {
      expect(x).toBeGreaterThanOrEqual(0); expect(x).toBeLessThanOrEqual(wide)
      expect(y).toBeGreaterThanOrEqual(0); expect(y).toBeLessThanOrEqual(short)
    }
    const ys = xy.map(p => p[1])
    // Height is the binding dimension of a ~square country in a 5:1 tile.
    expect(Math.max(...ys) - Math.min(...ys)).toBeGreaterThan(short * 0.45)
  })

  it('pixel padding keeps edge marks inside the box', () => {
    const pad = 20
    const { projection } = fittedProjection(W, H, EGYPT, pad)
    for (const [x, y] of EGYPT.map(p => projection(p)!)) {
      expect(x).toBeGreaterThanOrEqual(pad - 0.5); expect(x).toBeLessThanOrEqual(W - pad + 0.5)
      expect(y).toBeGreaterThanOrEqual(pad - 0.5); expect(y).toBeLessThanOrEqual(H - pad + 0.5)
    }
  })

  it('keeps worldwide route ends inside a wide short tile', () => {
    const wide = 520, short = 200
    const pts: [number, number][] = [
      [-118.24, 34.05], [ -74.00, 40.71], [0.13, 51.51],
      [139.69, 35.69], [151.21, -33.87],
    ]
    const pad = Math.max(16, Math.min(wide, short) * 0.1)
    const { projection } = fittedProjection(wide, short, pts, pad)
    for (const p of pts) {
      const xy = projection(p)!
      expect(xy[0]).toBeGreaterThanOrEqual(0)
      expect(xy[0]).toBeLessThanOrEqual(wide)
      expect(xy[1]).toBeGreaterThanOrEqual(0)
      expect(xy[1]).toBeLessThanOrEqual(short)
    }
  })
})

describe('the degenerate cases stay finite', () => {
  it('a single point produces a usable map, not an infinite zoom', () => {
    const { projection } = fittedProjection(W, H, [[31.24, 30.05]])
    const p = projection([31.24, 30.05])!
    expect(Number.isFinite(p[0])).toBe(true)
    expect(Number.isFinite(p[1])).toBe(true)
    expect(p[0]).toBeGreaterThan(0); expect(p[0]).toBeLessThan(W)
  })

  it('identical points behave like a single one', () => {
    const same: [number, number][] = [[31.24, 30.05], [31.24, 30.05]]
    const p = fittedProjection(W, H, same).projection([31.24, 30.05])!
    expect(Number.isFinite(p[0]) && Number.isFinite(p[1])).toBe(true)
  })

  it('no points at all still fits the world', () => {
    const a = fittedProjection(W, H, [])
    const b = fittedProjection(W, H)
    expect(a.projection([0, 0])).toEqual(b.projection([0, 0]))
  })

  it('ignores coordinates that are not real numbers', () => {
    const dirty = [...EGYPT, [NaN, 5], [null as any, 2]] as [number, number][]
    const clean = fittedProjection(W, H, EGYPT).projection(EGYPT[0])!
    const got = fittedProjection(W, H, dirty).projection(EGYPT[0])!
    expect(got[0]).toBeCloseTo(clean[0], 6)
  })
})

describe('the world outline still draws', () => {
  it('returns a path generator whatever the focus', () => {
    const { path } = fittedProjection(W, H, EGYPT)
    expect(typeof path).toBe('function')
  })
})

describe('a shape map is framed on the shape, not its middle', () => {
  // A choropleth of one country fitted to that country's CENTROID frames a few
  // degrees around the middle and draws the country many times the size of the
  // tile. Its bounds are what has to be fitted.
  const egypt = matchCountry('Egypt')!

  it('knows a country covers more than its centre point', () => {
    const [sw, ne] = countryBoundsPoints(egypt)
    expect(ne[0] - sw[0]).toBeGreaterThan(5)   // degrees of longitude
    expect(ne[1] - sw[1]).toBeGreaterThan(5)   // degrees of latitude
  })

  it('keeps the whole country inside the box when fitted to its bounds', () => {
    const { projection } = fittedProjection(W, H, countryBoundsPoints(egypt))
    for (const corner of countryBoundsPoints(egypt)) {
      const [x, y] = projection(corner)!
      expect(x).toBeGreaterThanOrEqual(0); expect(x).toBeLessThanOrEqual(W)
      expect(y).toBeGreaterThanOrEqual(0); expect(y).toBeLessThanOrEqual(H)
    }
  })

  it('clips the country when fitted to the centroid instead', () => {
    // The bug this replaces, pinned so nobody reintroduces centroid fitting.
    const { projection } = fittedProjection(W, H, [projectionCentre(egypt)])
    const outside = countryBoundsPoints(egypt)
      .map(c => projection(c)!)
      .some(([x, y]) => x < 0 || x > W || y < 0 || y > H)
    expect(outside).toBe(true)
  })
})

function projectionCentre(f: any): [number, number] {
  const [sw, ne] = countryBoundsPoints(f)
  return [(sw[0] + ne[0]) / 2, (sw[1] + ne[1]) / 2]
}
