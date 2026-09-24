/**
 * World geometry for the map widgets: features, name matching, centroids.
 *
 * Everything geographic lives here so the renderers stay pure drawing. The geometry is
 * world-atlas 50m (739 kB raw, ~250 kB over the wire, 241 countries), bundled rather
 * than fetched -- a map that breaks without internet is a demo liability, and
 * choropleths need no tile server. 50m over the smaller 110m deliberately: the 110m
 * atlas simply omits small states -- Singapore first among them, which the demo data
 * contains -- and a world map missing countries is factually wrong, not merely coarse.
 * The geometry lives in the lazily-loaded charts chunk, so the login path never pays
 * for it.
 *
 * Centroids are computed from the geometry itself via d3-geo rather than shipped as a
 * hand-typed coordinate table, so there is no second data source to drift out of sync
 * with the shapes.
 */
import { activeTiles } from './tiles'
import { geoNaturalEarth1, geoPath, geoCentroid, geoBounds, geoArea, geoMercator } from 'd3-geo'
import { feature } from 'topojson-client'
import type { Feature, FeatureCollection, Geometry } from 'geojson'
import world from 'world-atlas/countries-50m.json'

import type { GeoProjection } from 'd3-geo'
/** What d3's projection.fitSize / fitExtent accept. */
type GeoFittable = Parameters<GeoProjection['fitSize']>[1]

export interface CountryFeature extends Feature<Geometry> {
  properties: { name: string }
  /** ISO 3166-1 NUMERIC, as a string, on 236 of the atlas's 241 geometries.
   *  The five without one (Kosovo, Somaliland, N. Cyprus, Indian Ocean Ter.,
   *  Siachen Glacier) are disputed or unassigned and genuinely have no ISO
   *  code. This was always in the data and never read, so every `country_code`
   *  column failed the name lookup and painted nothing. */
  id?: string | number
}

const collection = feature(
  world as unknown as Parameters<typeof feature>[0],
  (world as unknown as { objects: { countries: Parameters<typeof feature>[1] } }).objects.countries,
) as unknown as FeatureCollection<Geometry, { name: string }>

export const COUNTRIES: CountryFeature[] = collection.features as CountryFeature[]

/** Common variants -> the world-atlas feature name. The atlas uses formal names
 *  ("United States of America"), while data almost never does. Lowercased keys;
 *  extend as real datasets surface new spellings. */
const ALIASES: Record<string, string> = {
  'us': 'United States of America',
  'usa': 'United States of America',
  'united states': 'United States of America',
  'uk': 'United Kingdom',
  'great britain': 'United Kingdom',
  'south korea': 'South Korea',
  'korea, rep.': 'South Korea',
  'north korea': 'North Korea',
  'russia': 'Russia',
  'russian federation': 'Russia',
  'czech republic': 'Czechia',
  'ivory coast': "Côte d'Ivoire",
  'dr congo': 'Dem. Rep. Congo',
  'democratic republic of the congo': 'Dem. Rep. Congo',
  'republic of the congo': 'Congo',
  'myanmar (burma)': 'Myanmar',
  'burma': 'Myanmar',
  'uae': 'United Arab Emirates',
  'vietnam': 'Vietnam',
  'viet nam': 'Vietnam',
  'bosnia': 'Bosnia and Herz.',
  'bosnia and herzegovina': 'Bosnia and Herz.',
  'macedonia': 'North Macedonia',
  'laos': 'Laos',
  'syria': 'Syria',
  'venezuela': 'Venezuela',
  'bolivia': 'Bolivia',
  'tanzania': 'Tanzania',
  'moldova': 'Moldova',
  'iran': 'Iran',
  'western sahara': 'W. Sahara',
  'central african republic': 'Central African Rep.',
  'south sudan': 'S. Sudan',
  'dominican republic': 'Dominican Rep.',
  'equatorial guinea': 'Eq. Guinea',
  'eswatini': 'eSwatini',
  'swaziland': 'eSwatini',
}

const byName = new Map<string, CountryFeature>()
for (const f of COUNTRIES) byName.set(f.properties.name.toLowerCase(), f)

/**
 * Spelling normalisation, not fuzzy matching.
 *
 * Two differences show up constantly between what an atlas, a locale database
 * and a spreadsheet call the same country, and neither is a judgement call:
 * "&" versus "and" (CLDR writes "Bosnia & Herzegovina"; this atlas and most
 * data write "and"), and curly versus straight apostrophes ("Côte d'Ivoire"
 * arrives both ways depending on what typed it).
 *
 * Collapsing those is safe in a way that trimming words or edit distance is
 * not: no two countries differ only by an ampersand or a quote mark, so this
 * can never resolve to the wrong one.
 */
function normalise(key: string): string {
  return key
    .replace(/[‘’ʼ]/g, "'")
    .replace(/\s*&\s*/g, ' and ')
    .replace(/\s+/g, ' ')
    .trim()
}

/**
 * The last exact form a region name is tried under: without the administrative
 * word real exports add ("Cairo Governorate", "Governorate of Giza", "محافظة
 * القاهرة", "Ontario Province") and without spaces, hyphens, apostrophes and the
 * Arabic tatweel ("بور سعيد" = "بورسعيد", "Kafr-el-Sheikh" = "Kafr El Sheikh").
 *
 * Still not fuzzy: two strings meet only when they are the same letters in the
 * same order. It runs only after the name and its normalised form both missed,
 * so it can never re-point a name the file itself gives to another region.
 */
const ADMIN_WORDS = /^(governorate|province|prefecture|emirate|region) of |\s+(governorate|province|prefecture|emirate)$|^(محافظة|محافظه|إمارة|امارة|منطقة)\s+/giu
export function compactRegionKey(key: string): string {
  return normalise(key.toLowerCase())
    .replace(ADMIN_WORDS, '')
    .replace(/[\s\-'’`ـ.]+/gu, '')
}

/** Resolve a name or a known alias. The shared tail of every lookup below, so a
 *  code and a typed name always agree about which feature they mean. */
function byNameOrAlias(key: string): CountryFeature | undefined {
  const lookup = (k: string) =>
    byName.get(k) ?? (ALIASES[k] ? byName.get(ALIASES[k].toLowerCase()) : undefined)
  const direct = lookup(key)
  if (direct) return direct
  const norm = normalise(key)
  return norm === key ? undefined : lookup(norm)
}

/**
 * A set of drawable regions with a name index — countries, or a file somebody
 * uploaded.
 *
 * Everything in this module used to be built at IMPORT time from one static
 * atlas: the features, the name index, the alias table, the alpha-2 probe. That
 * was correct while there was exactly one world, and it is why a dataset keyed
 * by governorates drew a bare map — there was no way to have a second set.
 *
 * `COUNTRY_SET` below is now just the first instance. Keeping countries on the
 * same code path is the point: a special case for the built-in set is a place
 * for the two to drift, and the never-fuzzy rule has to hold for both.
 */
export interface RegionFeature extends Feature<Geometry> {
  properties: Record<string, unknown> & { name?: string }
  id?: string | number
}

export interface RegionSet {
  features: RegionFeature[]
  /** Lowercased, normalised value -> feature. Built once per set. */
  index: Map<string, RegionFeature>
  /** The properties this set names its regions by, best first. A set uploaded
   *  from a real boundary file may call that `NAME_1`, `shapeName` or
   *  `ADM1_EN` and have no `name` at all — without this a renderer has nothing
   *  to put in a tooltip and falls back to the array index, which is how the
   *  first live check of this feature came back labelling France "6". */
  labelKeys: string[]
  /** Values a person pinned to a region (value -> feature index), stored on
   *  the set as the GeoJSON foreign member `x_pins`. */
  pins?: Record<string, number>
  /** The credit the boundary source requires on every map drawn from it
   *  (e.g. "© EuroGeographics for the administrative boundaries"), stored on
   *  the set as the GeoJSON foreign member `x_attribution` when a pack with
   *  terms is installed. */
  attribution?: string
}

/**
 * Index a feature collection by every property the caller says can name a
 * region.
 *
 * Several keys, not one: a real boundary file often carries both `name` and
 * `name_ar`, and a dataset may be written in either. That is several EXACT
 * lookups, which is not the same thing as fuzzy matching — the rule that a
 * value either names a region or does not is unchanged.
 *
 * First key wins a collision. Two regions claiming one name is a defect in the
 * file, and silently preferring the later one would move data between shapes
 * depending on file order.
 */
export function buildRegionSet(
  collectionIn: { features?: unknown[] } | Record<string, unknown> | null | undefined,
  keyProperties: readonly string[],
): RegionSet {
  const raw = (collectionIn as { features?: unknown[] } | null | undefined)?.features
  const features = ((raw ?? []) as RegionFeature[])
    .filter(f => f && typeof f === 'object')
    .map(rewindForD3)
  const index = new Map<string, RegionFeature>()
  for (const f of features) {
    const props = (f.properties ?? {}) as Record<string, unknown>
    for (const key of keyProperties) {
      const value = props[key]
      if (typeof value !== 'string' || !value.trim()) continue
      for (const form of [value.trim().toLowerCase(),
                          normalise(value.trim().toLowerCase())]) {
        if (!index.has(form)) index.set(form, f)
      }
      const compact = '~' + compactRegionKey(value.trim())
      if (compact.length > 1 && !index.has(compact)) index.set(compact, f)
    }
  }
  // Pins after the file's own names: a pin fills a gap, it never re-points a
  // name the file already gives to a different region.
  const pins = (collectionIn as { x_pins?: Record<string, number> } | null | undefined)?.x_pins ?? {}
  for (const [value, i] of Object.entries(pins)) {
    const f = features[i]
    if (!f || !value.trim()) continue
    for (const form of [value.trim().toLowerCase(), normalise(value.trim().toLowerCase())]) {
      if (!index.has(form)) index.set(form, f)
    }
  }
  const credit = (collectionIn as { x_attribution?: unknown } | null | undefined)?.x_attribution
  return {
    features, index, labelKeys: [...keyProperties], pins: { ...pins },
    ...(typeof credit === 'string' && credit.trim() ? { attribution: credit.trim() } : {}),
  }
}

/**
 * Put polygon rings in the winding d3 expects.
 *
 * GeoJSON (RFC 7946) winds exterior rings counter-clockwise; d3-geo works on
 * the sphere and reads that as "everything EXCEPT this shape". A standards-
 * compliant boundary file therefore drew as a map-sized blob with a hole, and
 * framed the whole world instead of the country. A ring whose spherical area
 * is more than half the globe is the inverted reading, so it is reversed.
 */
export function rewindForD3<F extends RegionFeature>(f: F): F {
  const g = f?.geometry as { type?: string; coordinates?: unknown } | null
  if (!g || (g.type !== 'Polygon' && g.type !== 'MultiPolygon')) return f
  const fix = (poly: number[][][]) =>
    geoArea({ type: 'Polygon', coordinates: poly } as never) > 2 * Math.PI
      ? poly.map(ring => [...ring].reverse())
      : poly
  const coordinates = g.type === 'Polygon'
    ? fix(g.coordinates as number[][][])
    : (g.coordinates as number[][][][]).map(fix)
  if (coordinates === g.coordinates) return f
  return { ...f, geometry: { ...g, coordinates } as F['geometry'] }
}

/** Resolve a data value against a region set. Never fuzzy, for the same reason
 *  country matching is not: painting real data onto the wrong shape is worse
 *  than leaving it visibly unmatched. */
export function matchRegion(value: unknown, set: RegionSet): RegionFeature | undefined {
  if (value == null) return undefined
  const key = String(value).trim().toLowerCase()
  if (!key) return undefined
  return set.index.get(key) ?? set.index.get(normalise(key))
    // Prefixed so a compact form can never collide with a real name.
    ?? set.index.get('~' + compactRegionKey(key))
}

/** What to call a region on screen: the first key property that names it.
 *
 *  Falls back to `name` (which the built-in countries use) and finally to the
 *  empty string, so a caller can decide what an unnamed shape looks like rather
 *  than being handed an index that means nothing to a reader. */
export function regionLabel(f: RegionFeature, set: RegionSet): string {
  for (const key of [...set.labelKeys, 'name']) {
    const value = (f.properties ?? {})[key]
    if (typeof value === 'string' && value.trim()) return value
  }
  return ''
}

/** [lon, lat] centre of any region. */
export function regionCentroid(f: RegionFeature): [number, number] {
  return geoCentroid(f)
}

/** The south-west and north-east corners of any region, as [lon, lat] pairs. */
export function regionBoundsPoints(f: RegionFeature): [number, number][] {
  const [sw, ne] = geoBounds(f)
  return [sw as [number, number], ne as [number, number]]
}

/** ISO 3166-1 numeric -> feature, from the atlas's own `id`. Keyed on the
 *  zero-padded three-digit form AND the unpadded one: 076 arrives as the number
 *  76 the moment a spreadsheet reads the column as numeric, and both spellings
 *  mean Brazil. */
const byNumeric = new Map<string, CountryFeature>()
for (const f of COUNTRIES) {
  if (f.id == null) continue
  const padded = String(f.id).padStart(3, '0')
  byNumeric.set(padded, f)
  byNumeric.set(String(Number(padded)), f)
}

/**
 * ISO 3166-1 alpha-2 -> feature, DERIVED rather than typed.
 *
 * `Intl.DisplayNames` turns a region code into the runtime's own CLDR name,
 * which is then resolved through `byNameOrAlias` — the same path a typed name
 * takes, so one alias entry serves both and the two can never disagree. There
 * is no enumeration API for assigned codes, so all 676 two-letter combinations
 * are probed and the ones that resolve are kept.
 *
 * Derived beats hand-written here. A 236-row table typed from memory would put
 * a wrong country behind some code, silently, and painting real data onto the
 * wrong shape is precisely what this module's never-fuzzy rule exists to
 * prevent. Anything CLDR does not name, or names something the atlas does not
 * have, is simply absent — never guessed.
 *
 * Alpha-3 is NOT covered: nothing available offline maps it, and inventing the
 * table is the risk this comment just described. A dataset keyed on alpha-3
 * still reports its values as unmatched, visibly, in the footer that already
 * exists for that.
 */
const byAlpha2 = new Map<string, CountryFeature>()
try {
  const display = new Intl.DisplayNames(['en'], { type: 'region' })
  const LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
  for (const a of LETTERS) for (const b of LETTERS) {
    const code = a + b
    let label: string | undefined
    try { label = display.of(code) } catch { continue }
    // An unassigned code comes back as itself.
    if (!label || label === code) continue
    const hit = byNameOrAlias(label.toLowerCase())
    if (hit) byAlpha2.set(code.toLowerCase(), hit)
  }
} catch {
  // No Intl.DisplayNames: names and numeric codes still work, alpha-2 does not.
  // A map with fewer matches is a worse map; a module that throws at import
  // time is no map at all.
}

/** Resolve a data value -- a country name in any common spelling, an ISO 3166-1
 *  alpha-2 code, or the ISO numeric code -- to its feature, or undefined.
 *
 *  Case-insensitive and alias-aware but NEVER fuzzy: a fuzzy match that grabs the
 *  wrong country paints real data on the wrong shape, which is worse than leaving
 *  it visibly unmatched.
 *
 *  Names are tried first so a real country name can never be shadowed by a code
 *  that happens to look like it. */
export function matchCountry(value: unknown): CountryFeature | undefined {
  if (value == null) return undefined
  const key = String(value).trim().toLowerCase()
  if (!key) return undefined
  return byNameOrAlias(key) ?? byAlpha2.get(key) ?? byNumeric.get(key)
}

/**
 * The built-in set: every country, indexed by name, alias, ISO alpha-2 and ISO
 * numeric.
 *
 * Built from `matchCountry` rather than from `buildRegionSet`, because
 * countries have three extra ways to be named that an uploaded file does not
 * (a hand-curated alias table, alpha-2 derived from CLDR, and the numeric code
 * the atlas carries). The INDEX is therefore the union of every key those
 * resolve, so `matchRegion(value, COUNTRY_SET)` and `matchCountry(value)` can
 * never disagree — which is what lets a renderer take one code path for both.
 */
export const COUNTRY_SET: RegionSet = (() => {
  const index = new Map<string, RegionFeature>()
  const put = (key: string, f: CountryFeature) => {
    if (key && !index.has(key)) index.set(key, f as RegionFeature)
  }
  for (const [key, f] of byName) put(key, f)
  for (const [key, f] of byAlpha2) put(key, f)
  for (const [key, f] of byNumeric) put(key, f)
  for (const [alias, target] of Object.entries(ALIASES)) {
    const f = byName.get(target.toLowerCase())
    if (f) { put(alias, f); put(normalise(alias), f) }
  }
  // The atlas's own names again, normalised, so a curly apostrophe or an
  // ampersand resolves here exactly as it does through matchCountry.
  for (const [key, f] of byName) put(normalise(key), f)
  return { features: COUNTRIES as RegionFeature[], index, labelKeys: ['name'] }
})()

/** [lon, lat] centre of a country, from its geometry. */
export function countryCentroid(f: CountryFeature): [number, number] {
  return geoCentroid(f)
}

/** The south-west and north-east corners of a country, as [lon, lat] pairs.
 *
 *  What a shape-drawing map must be framed on. Its centroid is one point, and
 *  fitting a projection to a single point frames a few degrees around the middle
 *  of the country -- drawing the country itself many times larger than the tile
 *  and clipping most of it away. */
export function countryBoundsPoints(f: CountryFeature): [number, number][] {
  const [sw, ne] = geoBounds(f)
  return [sw as [number, number], ne as [number, number]]
}

/** Pixel size a map draws into. Missing measure is 0, never a 16:9 960×540
 *  fallback: that box is wider than a typical tile, so overflow:hidden showed
 *  the Pacific and clipped London / Asia on the right. */
export function mapViewSize(plotW?: number, plotH?: number): { w: number; h: number } {
  const w = typeof plotW === 'number' && Number.isFinite(plotW) && plotW > 8 ? plotW : 0
  const h = typeof plotH === 'number' && Number.isFinite(plotH) && plotH > 8 ? plotH : 0
  return { w, h }
}

/** Out of flow, pinned to the measured tile. A relative 100% wrap still grew
 *  with the SVG's intrinsic viewBox size and the flex parent then clipped it. */
export const MAP_WRAP_STYLE = {
  position: 'absolute', top: 0, right: 0, bottom: 0, left: 0,
  minWidth: 0, minHeight: 0, overflow: 'hidden',
} as const

/** Fill that wrap. Pair with width/height="100%" attributes on the svg. */
export const MAP_SVG_STYLE = {
  position: 'absolute', top: 0, right: 0, bottom: 0, left: 0,
  width: '100%', height: '100%', maxWidth: '100%', maxHeight: '100%',
  display: 'block', direction: 'ltr',
} as const

/** A projection + path generator fitted to the given pixel box. NaturalEarth1: the
 *  standard compromise projection for world thematic maps -- equal-area enough that a
 *  choropleth does not visually overweight the poles the way Mercator does. */
export function fittedProjection(
  width: number, height: number, focus?: readonly (readonly [number, number])[],
  padPx = 0,
) {
  // With an org basemap the vector layers must sit on the tiles' own
  // projection (Web Mercator); without one, Natural Earth reads better.
  const mercator = !!activeTiles()
  const projection = mercator ? geoMercator() : geoNaturalEarth1()
  // Mercator runs to infinity at the poles, so its "whole world" is the
  // inhabited band, not the country outlines (Antarctica reaches -90°).
  const world: GeoFittable = mercator
    ? ({ type: 'MultiPoint', coordinates: [[-180, -58], [180, 78]] } as GeoFittable)
    : (collection as unknown as GeoFittable)
  if (!(width > 8 && height > 8)) {
    return { projection, path: geoPath(projection) }
  }
  const pad = Math.max(0, padPx)
  const fit = (geo: GeoFittable) => {
    const innerW = width - pad * 2
    const innerH = height - pad * 2
    if (innerW > 1 && innerH > 1) {
      projection.fitExtent([[pad, pad], [width - pad, height - pad]], geo)
    } else {
      projection.fitSize([width, height], geo)
    }
  }

  // Frame what is actually plotted. Fitting every map to the whole world meant a
  // dataset confined to one country drew that country a few pixels wide with an
  // ocean around it -- correct, and unreadable. `focus` is the [lon, lat] pairs
  // the caller is about to draw; without it the world is still the right frame,
  // which is what a map with no rows should show.
  const pts = (focus ?? []).filter(
    p => Array.isArray(p) && Number.isFinite(p[0]) && Number.isFinite(p[1]))
  if (pts.length === 0) {
    fit(world)
    return { projection, path: geoPath(projection) }
  }

  const lons = pts.map(p => p[0]), lats = pts.map(p => p[1])
  const minLon = Math.min(...lons), maxLon = Math.max(...lons)
  const minLat = Math.min(...lats), maxLat = Math.max(...lats)
  // A near-global spread cannot be framed from a lon/lat box: Natural Earth
  // bends meridians, and two corners over-zoom until Tokyo / London sit past
  // the viewBox. Fit the world outline instead, which is what these maps draw.
  if ((maxLon - minLon) > 150 || (maxLat - minLat) > 100) {
    fit(world)
    return { projection, path: geoPath(projection) }
  }
  // A margin so marks on the edge are not half-clipped, and -- the reason for the
  // floor -- so a single point, whose extent is zero, gets a real neighbourhood
  // instead of an infinite scale factor.
  const padLon = Math.max((maxLon - minLon) * 0.15, 1.5)
  const padLat = Math.max((maxLat - minLat) * 0.15, 1.5)
  // All plotted points, not just the SW/NE corners. Natural Earth bends meridians,
  // so two geographic corners under-state the equatorial width of a worldwide
  // bbox and the eastmost city (Tokyo, Sydney, London on a clipped tile) lands
  // past the viewBox edge.
  fit({
    type: 'MultiPoint',
    coordinates: [
      ...pts.map(p => [p[0], p[1]]),
      [minLon - padLon, minLat - padLat],
      [maxLon + padLon, maxLat + padLat],
      [minLon - padLon, maxLat + padLat],
      [maxLon + padLon, minLat - padLat],
    ],
  } as GeoJSON.MultiPoint)
  return { projection, path: geoPath(projection) }
}
