import { afterEach, describe, expect, it, vi } from 'vitest'
import { render } from '@testing-library/react'
import { geoMercator } from 'd3-geo'
import { setTileSettings, tilesFor, tileUrl } from './tiles'
import { fittedProjection } from './worldGeometry'
import { MapSvg } from './MapFrame'

vi.mock('../../../services/api', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  mapSettingsApi: { get: vi.fn().mockResolvedValue({ tile_url: null, attribution: null, contrast_tile_url: null }), set: vi.fn() },
}))

afterEach(() => setTileSettings(null))

describe('tile maths', () => {
  it('fills the XYZ template, rotating {s}', () => {
    expect(tileUrl('https://tiles.corp/{z}/{x}/{y}.png', 3, 4, 2)).toBe('https://tiles.corp/3/4/2.png')
    expect(tileUrl('https://{s}.t/{z}/{x}/{y}', 1, 0, 1)).toBe('https://b.t/1/0/1')
  })

  it('covers a whole-world view with the zoom-level-0/1 pyramid, aligned to the projection', () => {
    // A 512px-wide world is exactly zoom 1: 2×2 tiles of 256px.
    const p = geoMercator().scale(512 / (2 * Math.PI)).translate([256, 256])
    const tiles = tilesFor(p, 512, 512, '{z}/{x}/{y}')
    expect(tiles.map(t => t.href).sort()).toEqual(['1/0/0', '1/0/1', '1/1/0', '1/1/1'])
    expect(tiles[0].size).toBeCloseTo(256)
    expect(Math.min(...tiles.map(t => t.x))).toBeCloseTo(0)
  })
})

describe('an org basemap', () => {
  it('switches maps to Web Mercator and draws the tiles under the layers, with attribution', () => {
    expect(fittedProjection(400, 300).projection.scale()).toBeGreaterThan(0) // Natural Earth by default
    setTileSettings({ tile_url: 'https://tiles.intra/{z}/{x}/{y}.png', attribution: '© Our GIS team', contrast_tile_url: null })
    const { projection } = fittedProjection(400, 300)
    const { container, getByText } = render(
      <MapSvg w={400} h={300} projection={projection} tiles={{ tile_url: 'https://tiles.intra/{z}/{x}/{y}.png', attribution: '© Our GIS team', contrast_tile_url: null }}>
        <circle data-mark cx={1} cy={1} r={1} />
      </MapSvg>)
    const images = container.querySelectorAll('[data-testid=map-tiles] image')
    expect(images.length).toBeGreaterThan(0)
    expect(images[0].getAttribute('href')).toMatch(/^https:\/\/tiles\.intra\/\d+\/\d+\/\d+\.png$/)
    // Tiles first, data on top.
    const svg = container.querySelector('svg')!
    expect(svg.firstElementChild?.getAttribute('data-testid')).toBe('map-tiles')
    expect(getByText('© Our GIS team')).toBeTruthy()
  })

  it('draws nothing extra without one', () => {
    const { container } = render(<MapSvg w={400} h={300}><circle cx={1} cy={1} r={1} /></MapSvg>)
    expect(container.querySelector('[data-testid=map-tiles]')).toBeNull()
    // A map is never mirrored in an RTL report.
    expect(container.querySelector('svg')?.getAttribute('dir')).toBe('ltr')
  })

  it('draws a boundary source’s required credit even with no basemap', () => {
    const { getByTestId, container } = render(
      <MapSvg w={400} h={300} credit="© EuroGeographics for the administrative boundaries">
        <circle cx={1} cy={1} r={1} />
      </MapSvg>)
    expect(container.querySelector('[data-testid=map-tiles]')).toBeNull()
    expect(getByTestId('map-boundary-credit')).toHaveTextContent('© EuroGeographics')
  })
})

describe('a VECTOR tile server (TileServer GL light, .pbf only)', () => {
  // A real z8 tile from the customer's Egypt server (8/149/110, decompressed,
  // around Aswan: lon 29.53..30.94, lat 23.24..24.53):
  // lakes, a trunk road, residential land and city/town places.
  const fixture = async () => {
    const fs = await import('node:fs')
    const path = await import('node:path')
    const url = await import('node:url')
    const here = path.dirname(url.fileURLToPath(import.meta.url))
    return new Uint8Array(fs.readFileSync(path.join(here, '__fixtures__', 'egypt_z8_149_110.pbf')))
  }
  const TEMPLATE = 'http://192.168.50.208:8080/data/egypt_osm/{z}/{x}/{y}.pbf'

  it('recognises a .pbf/.mvt template and leaves raster ones alone', async () => {
    const { isVectorTemplate } = await import('./vectorTiles')
    expect(isVectorTemplate(TEMPLATE)).toBe(true)
    expect(isVectorTemplate('https://t/{z}/{x}/{y}.mvt?key=1')).toBe(true)
    expect(isVectorTemplate('https://tiles.intra/{z}/{x}/{y}.png')).toBe(false)
    expect(isVectorTemplate(null)).toBe(false)
  })

  it('decodes a real tile into lon/lat features inside the tile it came from', async () => {
    const { decodeVectorTile } = await import('./vectorTiles')
    const features = decodeVectorTile(await fixture(), 8, 149, 110)
    const kinds = new Set(features.map(f => f.kind))
    expect(kinds.has('water') && kinds.has('road') && kinds.has('place')).toBe(true)
    // The decode is checked against the real world, not the tile box: this
    // build buffers place points far past the tile edge (raw -3166..8024 on a
    // 4096 extent), so the tile carries its neighbours' towns too -- the
    // renderer de-duplicates labels by name. Mut is at 25.49N 28.98E and Kharga
    // at 25.44N 30.55E. (Villages such as Abu Simbel are not drawn at all.)
    const at = (name: string) => {
      const f = features.find(p => p.kind === 'place' && p.label === name)
      return (f?.geo.geometry as { coordinates: number[] } | undefined)?.coordinates
    }
    const [mutLon, mutLat] = at('Mut')!
    expect(mutLon).toBeCloseTo(28.98, 1); expect(mutLat).toBeCloseTo(25.49, 1)
    const [asLon, asLat] = at('Al Kharja Oases')!
    expect(at('Abu Simbel')).toBeUndefined()
    expect(asLon).toBeCloseTo(30.55, 1); expect(asLat).toBeCloseTo(25.44, 1)
  })

  it('labels in Arabic on an Arabic page', async () => {
    const { decodeVectorTile } = await import('./vectorTiles')
    const ar = decodeVectorTile(await fixture(), 8, 149, 110, 'ar').filter(f => f.kind === 'place')
    expect(ar.some(f => /[\u0600-\u06FF]/.test(f.label ?? ''))).toBe(true)
  })

  it('draws the decoded tiles as paths under the data layers, capped at an extract zoom', async () => {
    const { clearVectorTileCache, VECTOR_MAX_ZOOM } = await import('./vectorTiles')
    clearVectorTileCache()
    const bytes = await fixture()
    const fetchMock = vi.fn(async (href: string) => (href.includes('/8/149/110.pbf')
      ? new Response(bytes, { status: 200 }) : new Response(null, { status: 404 })))
    vi.stubGlobal('fetch', fetchMock)
    // A Mercator view at zoom 8 centred inside that tile.
    const projection = geoMercator().center([30.2, 23.9]).scale(256 * 2 ** 8 / (2 * Math.PI)).translate([200, 150])
    const tiles = { tile_url: TEMPLATE, attribution: 'OpenMapTiles', contrast_tile_url: null }
    const { container, findByTestId } = render(
      <MapSvg w={400} h={300} projection={projection} tiles={tiles}><circle data-mark cx={1} cy={1} r={1} /></MapSvg>)

    const g = await findByTestId('map-vector-tiles')
    expect(g.querySelector('path[data-kind=water]')?.getAttribute('d')).toMatch(/^M/)
    expect(g.querySelector('path[data-kind=road]')).not.toBeNull()
    expect(g.querySelectorAll('text').length).toBeGreaterThan(0)
    // Basemap first, data on top; no raster <image> for a vector server.
    const svg = container.querySelector('svg')!
    expect(svg.firstElementChild).toBe(g)
    expect(container.querySelector('[data-testid=map-tiles] image')).toBeNull()
    // A tile the server does not have (404) simply draws nothing, and no
    // request goes past the extract's zoom.
    expect(fetchMock.mock.calls.every(([u]) => Number(String(u).split('/').slice(-3)[0]) <= VECTOR_MAX_ZOOM)).toBe(true)
    vi.unstubAllGlobals()
  })
})
