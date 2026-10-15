import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { withMeasuredTiles } from '../test/measuredTiles'
import EmbeddedReport from './EmbeddedReport'
import { embedApi, mapSettingsApi, boundarySetsApi } from '../services/api'
import { activeTiles, setTileSettings } from '../components/report/geo/tiles'
import { _clearRegionSetCache } from '../components/report/geo/regionSetCache'
import { setRegionSetLoader } from '../components/report/geo/boundarySource'

/**
 * Same bug as SharedReport.maps.test (QA F2-55 / TODO_PLAN F-01) on the embed
 * surface: an iframe has no user session, so a map's signed-in requests 401'd
 * and the host page showed our login screen. The embed takes the basemap from
 * its payload and the shapes from the embed-session route.
 */
vi.mock('../services/api', () => ({
  embedApi: { report: vi.fn(), widgetData: vi.fn(), boundarySet: vi.fn() },
  widgetDataApi: { query: vi.fn() },
  mapSettingsApi: { get: vi.fn() },
  boundarySetsApi: { list: vi.fn().mockResolvedValue([]), get: vi.fn() },
}))

const SQUARE = { type: 'FeatureCollection', features: [{
  type: 'Feature', properties: { name: 'Cairo' },
  geometry: { type: 'Polygon', coordinates: [[[31, 30], [32, 30], [32, 31], [31, 31], [31, 30]]] },
}] }

const payload = {
  name: 'Embedded map', theme: 'default', dataset_id: 5, column_formats: {}, calculated_columns: [],
  geography: { region: 7 },
  map_settings: { tile_url: 'https://tiles.example/{z}/{x}/{y}.png', attribution: '© Example', contrast_tile_url: null },
  embed_session_token: 'sess-1',
  pages: [{ id: 1, name: 'P1', page_type: 'normal', position: 0,
    widgets: [{ id: 31, page_id: 1, widget_type: 'map_choropleth', title: 'By governorate',
      config: { dimension: 'region', measure: 'amount', boundary_set_id: 7 },
      layout: { x: 0, y: 0, w: 6, h: 4 } }] }],
}

function mount() {
  return render(
    <MemoryRouter initialEntries={['/embed?token=host-jwt']}>
      <Routes><Route path="/embed" element={<EmbeddedReport />} /></Routes>
    </MemoryRouter>
  )
}

describe('EmbeddedReport — maps without a user session', () => {
  withMeasuredTiles()

  beforeEach(() => {
    vi.clearAllMocks()
    _clearRegionSetCache()
    setRegionSetLoader(null)
    vi.mocked(embedApi.report).mockResolvedValue(payload)
    vi.mocked(embedApi.widgetData).mockResolvedValue({ rows: [{ name: 'Cairo', value: 3 }], total: 1 })
    vi.mocked(embedApi.boundarySet).mockResolvedValue({ id: 7, key_properties: ['name'], geometry: SQUARE } as never)
  })
  afterEach(() => { setTileSettings(null); setRegionSetLoader(null) })

  it('takes the basemap from the embed payload and the shapes from the embed session', async () => {
    mount()
    await screen.findByText('By governorate')
    await waitFor(() => expect(activeTiles()?.tile_url).toBe('https://tiles.example/{z}/{x}/{y}.png'))
    await waitFor(() => expect(embedApi.boundarySet).toHaveBeenCalledWith('sess-1', 7), { timeout: 20000 })
    expect(mapSettingsApi.get).not.toHaveBeenCalled()
    expect(boundarySetsApi.get).not.toHaveBeenCalled()
  })
})
