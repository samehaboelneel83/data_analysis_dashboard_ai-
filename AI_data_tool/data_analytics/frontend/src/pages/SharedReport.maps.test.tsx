import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { withMeasuredTiles } from '../test/measuredTiles'
import SharedReport from './SharedReport'
import { sharedApi, mapSettingsApi, boundarySetsApi } from '../services/api'
import { activeTiles, setTileSettings } from '../components/report/geo/tiles'
import { loadRegionSet, _clearRegionSetCache } from '../components/report/geo/regionSetCache'
import { setRegionSetLoader } from '../components/report/geo/boundarySource'

/**
 * QA F2-55 / TODO_PLAN F-01: a guest link to any dashboard with a map bounced
 * the logged-out viewer to /login. Every map asked two SIGNED-IN routes for
 * what it draws with -- the basemap (`/map-settings`) and custom boundaries
 * (`/boundary-sets/{id}`) -- and their 401 tripped the global login redirect.
 * The guest page must take both from the guest surface instead.
 */
vi.mock('../services/api', () => ({
  sharedApi: { report: vi.fn(), widgetData: vi.fn(), boundarySet: vi.fn() },
  widgetDataApi: { query: vi.fn() },
  mapSettingsApi: { get: vi.fn() },
  boundarySetsApi: { list: vi.fn().mockResolvedValue([]), get: vi.fn() },
}))

const SQUARE = { type: 'FeatureCollection', features: [{
  type: 'Feature', properties: { name: 'Cairo' },
  geometry: { type: 'Polygon', coordinates: [[[31, 30], [32, 30], [32, 31], [31, 31], [31, 30]]] },
}] }

const payload = {
  name: 'Governorates', theme: 'default', dataset_id: 5, column_formats: {}, calculated_columns: [],
  geography: { region: 7 },
  map_settings: { tile_url: 'https://tiles.example/{z}/{x}/{y}.png', attribution: '© Example', contrast_tile_url: null },
  pages: [{ id: 1, name: 'P1', page_type: 'normal', position: 0,
    widgets: [{ id: 31, page_id: 1, widget_type: 'map_choropleth', title: 'By governorate',
      config: { dimension: 'region', measure: 'amount', boundary_set_id: 7 },
      layout: { x: 0, y: 0, w: 6, h: 4 } }] }],
}

function mount() {
  return render(
    <MemoryRouter initialEntries={['/shared/tok']}>
      <Routes><Route path="/shared/:token" element={<SharedReport />} /></Routes>
    </MemoryRouter>
  )
}

describe('SharedReport — maps for a logged-out guest', () => {
  withMeasuredTiles()

  beforeEach(() => {
    vi.clearAllMocks()
    _clearRegionSetCache()
    setRegionSetLoader(null)
    vi.mocked(sharedApi.report).mockResolvedValue(payload)
    vi.mocked(sharedApi.widgetData).mockResolvedValue({ rows: [{ name: 'Cairo', value: 3 }], total: 1 })
    vi.mocked(sharedApi.boundarySet).mockResolvedValue({ id: 7, key_properties: ['name'], geometry: SQUARE } as never)
  })
  afterEach(() => { setTileSettings(null); setRegionSetLoader(null) })

  it('uses the basemap that came with the shared report, never the signed-in route', async () => {
    mount()
    await screen.findByText('Governorates')
    await waitFor(() => expect(activeTiles()?.tile_url).toBe('https://tiles.example/{z}/{x}/{y}.png'))
    expect(mapSettingsApi.get).not.toHaveBeenCalled()
  })

  it('draws the boundary set through the guest route, never the signed-in one', async () => {
    mount()
    await screen.findByText('Governorates')
    await waitFor(() => expect(sharedApi.boundarySet).toHaveBeenCalledWith('tok', 7), { timeout: 20000 })
    expect(boundarySetsApi.get).not.toHaveBeenCalled()
    expect(mapSettingsApi.get).not.toHaveBeenCalled()
  })

  it('hands boundary loading back to the signed-in route when the guest page closes', async () => {
    const view = mount()
    await screen.findByText('Governorates')
    await waitFor(() => expect(sharedApi.boundarySet).toHaveBeenCalled(), { timeout: 20000 })
    view.unmount()
    _clearRegionSetCache()
    vi.mocked(boundarySetsApi.get).mockResolvedValue({ id: 8, key_properties: ['name'], geometry: SQUARE } as never)
    await loadRegionSet(8)
    expect(boundarySetsApi.get).toHaveBeenCalledWith(8)
  })
})
