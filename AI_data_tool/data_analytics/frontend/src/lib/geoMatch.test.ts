import { describe, expect, it } from 'vitest'
import { buildRegionSet, COUNTRY_SET } from '../components/report/geo/worldGeometry'
import { geoMatchReport, geoMatchSentence } from './geoMatch'

const governorates = buildRegionSet({
  features: [
    { type: 'Feature', properties: { NAME_1: 'Cairo' }, geometry: { type: 'Polygon', coordinates: [[[31, 30], [31.5, 30], [31.5, 30.5], [31, 30]]] } },
    { type: 'Feature', properties: { NAME_1: 'Giza' }, geometry: { type: 'Polygon', coordinates: [[[30, 29], [30.5, 29], [30.5, 29.5], [30, 29]]] } },
  ],
}, ['NAME_1'])

describe('geoMatchReport', () => {
  it('weighs the match by rows and names the misses, biggest first', () => {
    const r = geoMatchReport([
      { name: 'Cairo', count: 70 }, { name: 'giza', count: 16 },
      { name: 'Alex', count: 4 }, { name: 'Luxor', count: 10 },
    ], governorates)
    expect(r.pctRows).toBe(86)
    expect(r.matchedValues).toBe(2)
    expect(r.unmatched).toEqual([{ name: 'Luxor', count: 10 }, { name: 'Alex', count: 4 }])
    expect(r.matchedFeatures.size).toBe(2)
    expect(geoMatchSentence(r)).toBe('86% of rows mapped · 2 of 4 values unmatched: Luxor (10 rows), Alex (4 rows)')
  })

  it('rounds down, so 100% means every row', () => {
    const r = geoMatchReport([{ name: 'Cairo', count: 999 }, { name: 'Nowhere', count: 1 }], governorates)
    expect(r.pctRows).toBe(99)
  })

  it('uses the same matcher as the maps (country codes and aliases)', () => {
    const r = geoMatchReport([{ name: 'US', count: 5 }, { name: 'France', count: 5 }], COUNTRY_SET)
    expect(r.pctRows).toBe(100)
    expect(geoMatchSentence(r)).toBe('100% of rows mapped · all 2 values found')
  })

  it('ignores blank values rather than counting them as misses', () => {
    const r = geoMatchReport([{ name: '', count: 3 }, { name: null, count: 2 }, { name: 'Cairo', count: 1 }], governorates)
    expect(r.totalRows).toBe(1)
    expect(r.pctRows).toBe(100)
  })
})
