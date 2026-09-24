import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import GeoLayerStackRenderer from './GeoLayerStackRenderer'

vi.mock('../../../services/api', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  boundarySetsApi: { list: vi.fn(), get: vi.fn(), create: vi.fn(), remove: vi.fn() },
}))

const base = { rows: [], cfg: {}, rtl: false, broadcasts: false, localSelected: null, onClickPoint: () => {}, plotW: 400, plotH: 300 }

describe('GeoLayerStackRenderer', () => {
  it('draws every layer in order and names the one it could not draw', () => {
    const { container } = render(<GeoLayerStackRenderer {...base} data={{ type: 'geo_layers', layers: [
      { id: 'r', kind: 'regions', title: 'Sales by country', regions: [{ name: 'Egypt', value: 5 }, { name: 'Atlantis', value: 1 }] },
      { id: 'b', kind: 'bubbles', title: 'Orders', regions: [{ name: 'France', value: 3 }] },
      { id: 'p', kind: 'points', title: 'Stores', points: [{ lat: 30, lon: 31, value: 2 }] },
      { id: 'l', kind: 'lines', title: 'Routes', lines: [{ lat: 30, lon: 31, lat2: 48.8, lon2: 2.3 }] },
      { id: 'x', kind: 'points', title: 'Depots', error: 'needs Longitude' },
    ] }} />)
    const kinds = [...container.querySelectorAll('[data-layer-kind]')].map(g => g.getAttribute('data-layer-kind'))
    expect(kinds).toEqual(['regions', 'bubbles', 'points', 'lines'])
    const legend = screen.getByTestId('layer-legend').textContent ?? ''
    expect(legend).toContain('Depots — not drawn: needs Longitude')
    expect(legend).toContain('not on the map: Atlantis')
  })
})
