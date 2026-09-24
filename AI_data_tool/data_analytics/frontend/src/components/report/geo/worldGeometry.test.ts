import { describe, it, expect } from 'vitest'
import {
  COUNTRIES, COUNTRY_SET, buildRegionSet, matchCountry, matchRegion,
  countryCentroid, regionCentroid, regionBoundsPoints, regionLabel, fittedProjection,
  mapViewSize,
} from './worldGeometry'

describe('worldGeometry', () => {
  it('does not invent a 16:9 box when the tile has not been measured', () => {
    expect(mapViewSize()).toEqual({ w: 0, h: 0 })
    expect(mapViewSize(0, 0)).toEqual({ w: 0, h: 0 })
    expect(mapViewSize(720, 180)).toEqual({ w: 720, h: 180 })
  })

  it('loads a full world of countries from the bundled atlas', () => {
    expect(COUNTRIES.length).toBeGreaterThan(150)
    expect(COUNTRIES[0].properties.name).toBeTruthy()
  })

  it('matches exact names case-insensitively', () => {
    expect(matchCountry('France')?.properties.name).toBe('France')
    expect(matchCountry('france')?.properties.name).toBe('France')
    expect(matchCountry('  BRAZIL  ')?.properties.name).toBe('Brazil')
  })

  it('matches the spellings real data actually uses', () => {
    // The atlas says "United States of America"; data says almost anything else. These
    // exact variants are what the demo dataset and common exports contain -- each one
    // failing to match paints a hole in the map.
    expect(matchCountry('US')?.properties.name).toBe('United States of America')
    expect(matchCountry('USA')?.properties.name).toBe('United States of America')
    expect(matchCountry('United States')?.properties.name).toBe('United States of America')
    expect(matchCountry('UK')?.properties.name).toBe('United Kingdom')
    expect(matchCountry('Russia')?.properties.name).toBe('Russia')
    expect(matchCountry('Czech Republic')?.properties.name).toBe('Czechia')
  })

  it('returns undefined rather than guessing at an unknown name', () => {
    // Never fuzzy: painting real data onto the wrong country is worse than a visible
    // unmatched entry. "Franceland" must not become France.
    expect(matchCountry('Franceland')).toBeUndefined()
    expect(matchCountry('Atlantis')).toBeUndefined()
    expect(matchCountry('')).toBeUndefined()
    expect(matchCountry(null)).toBeUndefined()
  })

  it('computes centroids that fall inside sane bounds', () => {
    const fr = matchCountry('France')!
    const [lon, lat] = countryCentroid(fr)
    // Metropolitan France sits near 2°E 46°N; the atlas includes overseas territories,
    // so allow slack -- but a centroid in the wrong hemisphere means the geometry and
    // the name index disagree, which is the failure this guards.
    expect(lon).toBeGreaterThan(-10)
    expect(lon).toBeLessThan(15)
    expect(lat).toBeGreaterThan(40)
    expect(lat).toBeLessThan(55)
  })

  it('projects every demo country into the pixel box it was fitted to', () => {
    const { projection } = fittedProjection(800, 500)
    for (const name of ['US', 'Canada', 'Brazil', 'France', 'Australia', 'Japan']) {
      const f = matchCountry(name)!
      const pt = projection(countryCentroid(f))!
      expect(pt[0]).toBeGreaterThanOrEqual(0)
      expect(pt[0]).toBeLessThanOrEqual(800)
      expect(pt[1]).toBeGreaterThanOrEqual(0)
      expect(pt[1]).toBeLessThanOrEqual(500)
    }
  })

  it('draws non-empty SVG paths', () => {
    const { path } = fittedProjection(800, 500)
    const d = path(matchCountry('Brazil')!)
    expect(d).toBeTruthy()
    expect(d!.length).toBeGreaterThan(50)
  })
})

describe('matching a country CODE, not just a name', () => {
  /**
   * A `country_code` column silently painted nothing.
   *
   * The bundled atlas carries the ISO 3166-1 NUMERIC code as each feature's
   * `id` — 236 of its 241 geometries have one; the five without (Kosovo,
   * Somaliland, N. Cyprus, Indian Ocean Ter., Siachen Glacier) are disputed or
   * unassigned and genuinely have no ISO code. `CountryFeature` typed
   * `properties` as `{ name }` and nothing ever read `id`, so every code-based
   * column failed the name lookup and fell through to unmatched.
   *
   * Alpha-2 is derived at module load from the RUNTIME's own CLDR region names
   * (`Intl.DisplayNames`), then resolved through the same name path everything
   * else uses. Deriving beats hand-typing 236 rows: a mistyped row would paint
   * real data onto the wrong country, which is exactly what this module's
   * never-fuzzy rule exists to prevent, and a table nobody can check is a table
   * nobody should trust.
   */
  it('matches the ISO numeric code the atlas already carries', () => {
    expect(matchCountry('250')?.properties.name).toBe('France')
    expect(matchCountry(250)?.properties.name).toBe('France')
    expect(matchCountry('076')?.properties.name).toBe('Brazil')
  })

  it('accepts a numeric code that lost its leading zero to a spreadsheet', () => {
    // 076 arrives as the number 76 the moment the column is read as numeric.
    expect(matchCountry(76)?.properties.name).toBe('Brazil')
    expect(matchCountry('4')?.properties.name).toBe('Afghanistan')
  })

  it('matches ISO alpha-2 codes', () => {
    expect(matchCountry('FR')?.properties.name).toBe('France')
    expect(matchCountry('fr')?.properties.name).toBe('France')
    expect(matchCountry('DE')?.properties.name).toBe('Germany')
    expect(matchCountry('BR')?.properties.name).toBe('Brazil')
    expect(matchCountry('JP')?.properties.name).toBe('Japan')
  })

  it('resolves an alpha-2 whose CLDR name differs from the atlas spelling', () => {
    // CLDR says "Bosnia & Herzegovina", the atlas says "Bosnia and Herz." --
    // the derived code goes through the SAME alias path as a typed name, so
    // one entry serves both.
    expect(matchCountry('BA')?.properties.name).toBe('Bosnia and Herz.')
    expect(matchCountry('CF')?.properties.name).toBe('Central African Rep.')
  })

  it('covers the great majority of assigned alpha-2 codes', () => {
    // A guard on the derivation itself: if a future runtime changes its CLDR
    // names, or the atlas is swapped, coverage collapsing is the symptom and
    // this is where it shows up rather than in a blank map.
    const A = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('')
    let matched = 0
    for (const a of A) for (const b of A) {
      if (matchCountry(a + b)) matched++
    }
    expect(matched).toBeGreaterThan(180)
  })

  it('still refuses what it cannot resolve', () => {
    // The never-fuzzy rule holds for codes too: two letters is not a licence
    // to guess.
    expect(matchCountry('ZZ')).toBeUndefined()
    expect(matchCountry('QQ')).toBeUndefined()
    expect(matchCountry('999')).toBeUndefined()
  })

  it('does not let a code collide with a real country name', () => {
    // Names win. There is no country literally named "FR", but if the atlas
    // ever gained a two-letter name the name must not be shadowed by a code.
    expect(matchCountry('Chad')?.properties.name).toBe('Chad')
    expect(matchCountry('Cuba')?.properties.name).toBe('Cuba')
  })
})

describe('spelling differences that are not judgement calls', () => {
  /**
   * Two differences show up constantly between what an atlas, a locale
   * database and a spreadsheet call the same country: "&" vs "and", and curly
   * vs straight apostrophes. Collapsing them is safe in a way that trimming
   * words or edit distance is not — no two countries differ only by an
   * ampersand or a quote mark, so it can never resolve to the wrong one.
   *
   * This is what lets ONE alias entry serve both a typed name and a derived
   * ISO code: CLDR writes "Bosnia & Herzegovina", the alias table says "and".
   */
  it('treats & and "and" as the same word', () => {
    expect(matchCountry('Bosnia & Herzegovina')?.properties.name)
      .toBe('Bosnia and Herz.')
    expect(matchCountry('Antigua & Barbuda')?.properties.name)
      .toBe(matchCountry('Antigua and Barbuda')?.properties.name)
  })

  it('treats a curly apostrophe as a straight one', () => {
    // U+2019, which is what most word processors and CLDR emit.
    expect(matchCountry('Côte d\u2019Ivoire')?.properties.name)
      .toBe(matchCountry("Côte d'Ivoire")?.properties.name)
    expect(matchCountry('Côte d\u2019Ivoire')).toBeDefined()
  })

  it('collapses repeated whitespace', () => {
    expect(matchCountry('United   Kingdom')?.properties.name).toBe('United Kingdom')
  })

  it('normalising still does not make it fuzzy', () => {
    // The rule is "a different spelling of the same word", not "close enough".
    // ("Bosnia" alone is NOT an example — it is a deliberate alias, because a
    // dataset writing it means exactly one country.)
    expect(matchCountry('United Kingdoms')).toBeUndefined()
    expect(matchCountry('Franc')).toBeUndefined()
    expect(matchCountry('Germ&any')).toBeUndefined()
  })
})

describe('a boundary set that is not countries', () => {
  /**
   * The bundled atlas is countries and only countries, so a dataset keyed by
   * Egyptian governorates, US states or UK counties drew a bare world map with
   * nothing on it. Admin-1 for every country is tens of megabytes and cannot
   * ship with the app, so the customer supplies the file — and this module has
   * to stop assuming there is exactly one world.
   *
   * The awkward part was never the renderers. It was that everything here was
   * built at IMPORT time from one static file: the features, the name index,
   * the alias table, the alpha-2 probe. A set has to be a value you can build a
   * second of.
   */
  const square = (x: number, y: number) => ({
    type: 'Polygon' as const,
    coordinates: [[[x, y], [x + 1, y], [x + 1, y + 1], [x, y + 1], [x, y]]],
  })
  const gov = (name: string, ar: string, x: number, y: number) => ({
    type: 'Feature' as const, geometry: square(x, y),
    properties: { name, name_ar: ar },
  })
  // Synthetic shapes, deliberately: these are unit-test fixtures, not a claim
  // about where Egyptian governorates actually are.
  const EGYPT = {
    type: 'FeatureCollection' as const,
    features: [gov('Cairo', 'القاهرة', 31, 30), gov('Giza', 'الجيزة', 30, 29)],
  }

  it('matches a region by its name property', () => {
    const set = buildRegionSet(EGYPT, ['name'])
    expect(matchRegion('Cairo', set)?.properties.name).toBe('Cairo')
  })

  it('matches case-insensitively and ignores surrounding space', () => {
    const set = buildRegionSet(EGYPT, ['name'])
    expect(matchRegion('  cairo ', set)?.properties.name).toBe('Cairo')
  })

  it('matches on every detected key, not just the first', () => {
    // A file carrying both `name` and `name_ar` matches data in either
    // language. Several exact lookups — not fuzziness.
    const set = buildRegionSet(EGYPT, ['name', 'name_ar'])
    expect(matchRegion('الجيزة', set)?.properties.name).toBe('Giza')
  })

  it('is still never fuzzy', () => {
    const set = buildRegionSet(EGYPT, ['name'])
    expect(matchRegion('Cair', set)).toBeUndefined()
    expect(matchRegion('Kairo', set)).toBeUndefined()
  })

  it('applies the same spelling normalisation countries get', () => {
    const set = buildRegionSet({
      type: 'FeatureCollection',
      features: [gov("Sha'rqia", 'x', 0, 0)],
    }, ['name'])
    expect(matchRegion('Sha\u2019rqia', set)).toBeDefined()
  })

  it('carries the features so a renderer can draw the backdrop', () => {
    const set = buildRegionSet(EGYPT, ['name'])
    expect(set.features).toHaveLength(2)
  })

  it('gives every region a centroid and bounds, like a country', () => {
    const set = buildRegionSet(EGYPT, ['name'])
    const cairo = matchRegion('Cairo', set)!
    expect(regionCentroid(cairo)).toHaveLength(2)
    expect(regionBoundsPoints(cairo)).toHaveLength(2)
  })

  it('the built-in countries are just the default set', () => {
    // The point of the refactor: one code path, two values. If countries were
    // still special-cased, an uploaded set would drift from them.
    expect(matchRegion('France', COUNTRY_SET)?.properties.name).toBe('France')
    expect(matchRegion('FR', COUNTRY_SET)?.properties.name).toBe('France')
    expect(COUNTRY_SET.features.length).toBe(COUNTRIES.length)
  })

  it('a set with no usable keys matches nothing rather than throwing', () => {
    // The endpoint refuses these at upload, but a renderer must not crash on
    // one that predates the check or arrives from anywhere else.
    const set = buildRegionSet(EGYPT, [])
    expect(matchRegion('Cairo', set)).toBeUndefined()
    expect(set.features).toHaveLength(2)
  })

  it('does not let one set answer for another', () => {
    const set = buildRegionSet(EGYPT, ['name'])
    expect(matchRegion('France', set)).toBeUndefined()
    expect(matchRegion('Cairo', COUNTRY_SET)).toBeUndefined()
  })
})

describe('what a region is called on screen', () => {
  /**
   * Caught by photographing a real map, not by a unit test: a choropleth drawn
   * on an uploaded set labelled its regions "1", "6", "7".
   *
   * The renderer looked for a `name` property. Real boundary files often have
   * none — they name regions `NAME_1`, `shapeName`, `ADM1_EN`, `REGION_NAME` —
   * so every tooltip and every `data-country` fell back to the array index,
   * which means nothing to a reader and nothing to a test either.
   */
  const named = (key: string, value: string) => ({
    type: 'FeatureCollection' as const,
    features: [{
      type: 'Feature' as const,
      geometry: { type: 'Polygon' as const, coordinates: [[[0, 0], [1, 0], [1, 1], [0, 0]]] },
      properties: { [key]: value },
    }],
  })

  it('uses the property the set is keyed on', () => {
    const set = buildRegionSet(named('REGION_NAME', 'France'), ['REGION_NAME'])
    expect(regionLabel(set.features[0], set)).toBe('France')
  })

  it('prefers the first key when a set has several', () => {
    const both = {
      type: 'FeatureCollection' as const,
      features: [{
        type: 'Feature' as const,
        geometry: { type: 'Polygon' as const, coordinates: [[[0, 0], [1, 0], [1, 1], [0, 0]]] },
        properties: { name: 'Cairo', name_ar: 'القاهرة' },
      }],
    }
    const set = buildRegionSet(both, ['name', 'name_ar'])
    expect(regionLabel(set.features[0], set)).toBe('Cairo')
  })

  it('still finds `name` on a set that never declared it as a key', () => {
    const set = buildRegionSet(named('name', 'Giza'), [])
    expect(regionLabel(set.features[0], set)).toBe('Giza')
  })

  it('returns empty rather than an index for a nameless shape', () => {
    // So the caller decides what an unnamed region looks like. An index in a
    // tooltip is worse than nothing, because it reads as data.
    const set = buildRegionSet(named('area_km2', ''), ['area_km2'])
    expect(regionLabel(set.features[0], set)).toBe('')
  })

  it('names countries the way it always did', () => {
    expect(regionLabel(matchRegion('France', COUNTRY_SET)!, COUNTRY_SET)).toBe('France')
  })
})

describe('boundary credit', () => {
  const fc = (extra: Record<string, unknown>) => ({
    type: 'FeatureCollection',
    features: [{ type: 'Feature', properties: { name: 'Bayern' },
      geometry: { type: 'Polygon', coordinates: [[[10, 48], [12, 48], [12, 50], [10, 50], [10, 48]]] } }],
    ...extra,
  })

  it('carries the credit a pack installed under terms requires', () => {
    const set = buildRegionSet(fc({ x_attribution: '© EuroGeographics for the administrative boundaries' }), ['name'])
    expect(set.attribution).toBe('© EuroGeographics for the administrative boundaries')
  })

  it('has none for an ordinary upload', () => {
    expect(buildRegionSet(fc({}), ['name']).attribution).toBeUndefined()
    expect(buildRegionSet(fc({ x_attribution: '  ' }), ['name']).attribution).toBeUndefined()
  })
})

describe('region names as real exports write them', () => {
  const sq = (x: number) => ({ type: 'Polygon', coordinates: [[[x, 0], [x + 1, 0], [x + 1, 1], [x, 1], [x, 0]]] })
  const set = buildRegionSet({
    type: 'FeatureCollection',
    features: [
      { type: 'Feature', properties: { name: 'Cairo', name_ar: 'القاهرة' }, geometry: sq(0) },
      { type: 'Feature', properties: { name: 'Port Said', name_ar: 'بورسعيد' }, geometry: sq(2) },
      { type: 'Feature', properties: { name: 'Kafr el-Sheikh' }, geometry: sq(4) },
    ],
  }, ['name', 'name_ar'])

  it.each([
    ['Cairo Governorate', 'Cairo'], ['Governorate of Cairo', 'Cairo'], ['محافظة القاهرة', 'Cairo'],
    ['بور سعيد', 'Port Said'], ['PortSaid', 'Port Said'], ['Kafr El Sheikh', 'Kafr el-Sheikh'],
    ['Kafr-el-Sheikh governorate', 'Kafr el-Sheikh'],
  ])('%s is %s', (value, expected) => {
    expect(matchRegion(value, set)?.properties.name).toBe(expected)
  })

  it('is still not fuzzy: a different name stays unmatched', () => {
    expect(matchRegion('Cairoo', set)).toBeUndefined()
    expect(matchRegion('Port Saidi', set)).toBeUndefined()
    expect(matchRegion('Governorate', set)).toBeUndefined()
  })
})
