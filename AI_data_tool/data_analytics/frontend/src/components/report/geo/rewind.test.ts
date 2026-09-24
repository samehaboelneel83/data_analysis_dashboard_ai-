import { describe, expect, it } from 'vitest'
import { geoArea } from 'd3-geo'
import { buildRegionSet, rewindForD3 } from './worldGeometry'

// A 1°x1° square wound counter-clockwise, as RFC 7946 GeoJSON requires.
const ccw = { type: 'Feature', properties: { name: 'Cairo' },
  geometry: { type: 'Polygon', coordinates: [[[31, 30], [32, 30], [32, 31], [31, 31], [31, 30]]] } }

describe('boundary files wound the GeoJSON way', () => {
  it('draw as the shape, not as the world with a hole in it', () => {
    expect(geoArea(ccw as never)).toBeGreaterThan(2 * Math.PI) // how d3 reads it raw
    const set = buildRegionSet({ features: [ccw] }, ['name'])
    expect(geoArea(set.features[0] as never)).toBeLessThan(0.01)
  })

  it('leaves correctly wound shapes (and multipolygons) alone', () => {
    const cw = rewindForD3(rewindForD3(ccw as never))
    expect(geoArea(cw as never)).toBeLessThan(0.01)
    const multi = rewindForD3({ type: 'Feature', properties: {}, geometry: {
      type: 'MultiPolygon', coordinates: [ccw.geometry.coordinates] } } as never)
    expect(geoArea(multi as never)).toBeLessThan(0.01)
  })
})

describe('pinned values', () => {
  it('resolve like names, but never re-point a name the file already uses', async () => {
    const { matchRegion } = await import('./worldGeometry')
    const giza = { type: 'Feature', properties: { name: 'Giza' }, geometry: ccw.geometry }
    const set = buildRegionSet({ features: [ccw, giza], x_pins: { 'Greater Cairo': 0, Giza: 0 } } as never, ['name'])
    expect(matchRegion('greater cairo', set)?.properties.name).toBe('Cairo')
    expect(matchRegion('Giza', set)?.properties.name).toBe('Giza')
    expect(set.pins).toEqual({ 'Greater Cairo': 0, Giza: 0 })
  })
})
