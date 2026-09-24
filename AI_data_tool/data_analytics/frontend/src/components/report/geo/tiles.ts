/**
 * The org's basemap tile server (MASTER_PLAN Phase 4 item 4).
 *
 * Off unless an org admin sets one. The platform runs air-gapped, so there is
 * no default public tile service: a map with tiles fetches them from the
 * customer's OWN server, and a map without draws exactly as it always has.
 *
 * Module-level store, loaded once per page: every map on a page shares one
 * answer, and the maps re-project (to Web Mercator, which raster tiles are
 * cut in) when it arrives.
 */
import { useEffect, useState } from 'react'
import { mapSettingsApi, type MapSettings } from '../../../services/api'

let current: MapSettings | null = null
let loaded: Promise<MapSettings | null> | null = null
const listeners = new Set<(s: MapSettings | null) => void>()

/** Tiles in force right now, or null. Read by `fittedProjection`. */
export function activeTiles(): MapSettings | null {
  return current && current.tile_url ? current : null
}

export function loadTileSettings(): Promise<MapSettings | null> {
  if (!loaded) {
    loaded = Promise.resolve()
      .then(() => mapSettingsApi.get?.())
      .then(s => {
        current = s && s.tile_url ? s : null
        listeners.forEach(l => l(current))
        return current
      })
      .catch(() => null)
  }
  return loaded
}

/** For the settings page after a save, and for tests. */
export function setTileSettings(s: MapSettings | null) {
  current = s && s.tile_url ? s : null
  loaded = Promise.resolve(current)
  listeners.forEach(l => l(current))
}

export function useTileSettings(): MapSettings | null {
  const [s, setS] = useState<MapSettings | null>(activeTiles())
  useEffect(() => {
    listeners.add(setS)
    void loadTileSettings()
    return () => { listeners.delete(setS) }
  }, [])
  return s && s.tile_url ? s : null
}

/** The URL for one tile; `{s}` rotates a/b/c like every XYZ server expects. */
export function tileUrl(template: string, z: number, x: number, y: number): string {
  return template.replace('{z}', String(z)).replace('{x}', String(x)).replace('{y}', String(y))
    .replace('{s}', 'abc'[(x + y) % 3])
}

export interface TileImage { key: string; href: string; x: number; y: number; size: number }

/**
 * The tiles that cover a w×h view of a d3 Web-Mercator projection.
 *
 * d3's Mercator draws the whole world 2π·scale pixels wide; a z-level tile
 * pyramid is 256·2^z. The nearest integer zoom is used and each tile is
 * stretched to fit, so the basemap lines up with the vector layers exactly.
 */
export function tilesFor(projection: { scale(): number; (p: [number, number]): [number, number] | null },
                         w: number, h: number, template: string, maxZoom = 18): TileImage[] {
  const worldPx = 2 * Math.PI * projection.scale()
  if (!(worldPx > 0) || !(w > 0) || !(h > 0)) return []
  const z = Math.max(0, Math.min(maxZoom, Math.round(Math.log2(worldPx / 256))))
  const n = 2 ** z
  const size = worldPx / n
  const origin = projection([-180, 85.0511287798])
  if (!origin) return []
  const [x0, y0] = origin
  const out: TileImage[] = []
  // Half-open [0, w): a tile that only touches the right/bottom edge is not drawn.
  const i0 = Math.floor(-x0 / size), i1 = Math.ceil((w - x0) / size) - 1
  const j0 = Math.max(0, Math.floor(-y0 / size)), j1 = Math.min(n - 1, Math.ceil((h - y0) / size) - 1)
  if (i1 - i0 > 64 || j1 - j0 > 64) return [] // a degenerate fit; never flood the tile server
  for (let i = i0; i <= i1; i++) {
    for (let j = j0; j <= j1; j++) {
      const tx = ((i % n) + n) % n
      out.push({ key: `${z}/${i}/${j}`, href: tileUrl(template, z, tx, j), x: x0 + i * size, y: y0 + j * size, size })
    }
  }
  return out
}
