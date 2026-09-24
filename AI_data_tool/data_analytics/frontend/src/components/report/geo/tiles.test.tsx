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
