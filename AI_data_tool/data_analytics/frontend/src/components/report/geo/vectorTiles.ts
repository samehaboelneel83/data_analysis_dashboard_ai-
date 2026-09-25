/**
 * Vector basemap tiles (Mapbox Vector Tile / OpenMapTiles schema).
 *
 * The org tile server may serve only VECTOR tiles -- TileServer GL "light",
 * like the customer's Egypt server, renders no PNGs. A browser cannot show a
 * .pbf as an <image>, and pulling in a WebGL map engine would replace the d3
 * maps rather than sit under them. So the tiles are decoded here into GeoJSON
 * (lon/lat) and drawn as SVG paths through the map's OWN projection -- the
 * same Web Mercator the raster path uses -- so the basemap lines up with every
 * data layer exactly, and the world outline stays the fallback when the server
 * is down (a tile that fails to load simply draws nothing).
 */
import { VectorTile } from '@mapbox/vector-tile'
import { PbfReader } from 'pbf'
import type { Feature } from 'geojson'

/** A template for vector tiles: the path ends in .pbf or .mvt. */
export function isVectorTemplate(template: string | null | undefined): boolean {
  return !!template && /\.(pbf|mvt)$/i.test(template.split(/[?#]/)[0])
}

/**
 * Most self-hosted extracts stop at z12-14. A request past the server's own
 * max zoom 404s and would blank the basemap, while a z12 tile drawn larger is
 * the same vector geometry, only less detailed -- so vector requests stop here.
 */
export const VECTOR_MAX_ZOOM = 12

export type BasemapKind = 'water' | 'landcover' | 'landuse' | 'park' | 'waterway' | 'road' | 'minor_road'
  | 'boundary' | 'place'

export interface BasemapFeature {
  kind: BasemapKind
  geo: Feature
  /** Place labels only. */
  label?: string
  rank?: number
}

const MAJOR_ROADS = new Set(['motorway', 'trunk', 'primary'])
const MINOR_ROADS = new Set(['secondary', 'tertiary'])
const GREEN = new Set(['wood', 'grass', 'farmland', 'wetland', 'forest'])
const PLACE_CLASSES = new Set(['city', 'capital', 'town'])

/** Which basemap kind an OpenMapTiles feature is, or null to leave it out. */
function kindOf(layer: string, cls: unknown, props: Record<string, unknown>): BasemapKind | null {
  switch (layer) {
    case 'water': return 'water'
    case 'waterway': return 'waterway'
    case 'landcover': return GREEN.has(String(cls)) ? 'landcover' : null
    case 'landuse': return cls === 'residential' ? 'landuse' : null
    case 'park': return 'park'
    case 'transportation':
      if (MAJOR_ROADS.has(String(cls))) return 'road'
      if (MINOR_ROADS.has(String(cls))) return 'minor_road'
      return null
    case 'boundary': {
      const level = Number(props.admin_level)
      return level > 0 && level <= 4 && !props.maritime ? 'boundary' : null
    }
    case 'place': return PLACE_CLASSES.has(String(cls)) ? 'place' : null
    default: return null
  }
}

/** Decode one tile into the features the basemap draws, as lon/lat GeoJSON.
 *  `lang` picks the label (`name:ar` for Arabic, else the Latin name). */
export function decodeVectorTile(buf: ArrayBuffer | Uint8Array, z: number, x: number, y: number,
                                 lang: string = 'en'): BasemapFeature[] {
  const tile = new VectorTile(new PbfReader(buf instanceof Uint8Array ? buf : new Uint8Array(buf)))
  const out: BasemapFeature[] = []
  for (const [name, layer] of Object.entries(tile.layers)) {
    for (let i = 0; i < layer.length; i++) {
      const f = layer.feature(i)
      const props = f.properties as Record<string, unknown>
      const kind = kindOf(name, props.class, props)
      if (!kind) continue
      const geo = f.toGeoJSON(x, y, z)
      if (kind === 'place') {
        const label = (lang.startsWith('ar') ? props['name:ar'] : undefined)
          ?? props['name:latin'] ?? props['name:en'] ?? props.name
        if (!label) continue
        out.push({ kind, geo, label: String(label), rank: Number(props.rank) || 99 })
      } else {
        out.push({ kind, geo })
      }
    }
  }
  return out
}

// One decode per tile URL for the life of the page: every map on a page shares
// the tiles, and panning back to a tile never refetches it. A failed tile is
// remembered as empty so a down server is asked once, not on every render.
const cache = new Map<string, Promise<BasemapFeature[]>>()

export function loadVectorTile(href: string, z: number, x: number, y: number,
                               lang: string): Promise<BasemapFeature[]> {
  const key = `${lang}|${href}`
  let hit = cache.get(key)
  if (!hit) {
    hit = fetch(href)
      .then(r => (r.ok ? r.arrayBuffer() : null))
      .then(b => (b && b.byteLength ? decodeVectorTile(b, z, x, y, lang) : []))
      .catch(() => [])
    cache.set(key, hit)
  }
  return hit
}

/** For tests. */
export function clearVectorTileCache() { cache.clear() }
