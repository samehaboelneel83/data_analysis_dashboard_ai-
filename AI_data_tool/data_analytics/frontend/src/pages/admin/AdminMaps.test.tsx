import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import AdminMaps from './AdminMaps'
import { mapSettingsApi, boundarySetsApi } from '../../services/api'

vi.mock('../../services/api', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  mapSettingsApi: { get: vi.fn(), set: vi.fn() },
  boundarySetsApi: { list: vi.fn(), packs: vi.fn(), installPack: vi.fn() },
}))

describe('AdminMaps', () => {
  it('saves a basemap and offers the packs not yet installed', async () => {
    vi.mocked(mapSettingsApi.get).mockResolvedValue({ tile_url: null, attribution: null, contrast_tile_url: null })
    vi.mocked(mapSettingsApi.set).mockImplementation(async b => ({ ...b }))
    vi.mocked(boundarySetsApi.list).mockResolvedValue([{ id: 1, name: 'Egypt governorates', feature_count: 27 }] as never)
    vi.mocked(boundarySetsApi.packs).mockResolvedValue([
      { id: 'egypt-governorates', name: 'Egypt governorates', feature_count: 27, license: 'PD', source: 'NE' },
      { id: 'us-states', name: 'US states', feature_count: 51, license: 'PD', source: 'NE' },
    ] as never)
    render(<AdminMaps />)
    const url = await screen.findByPlaceholderText(/tiles\.example\.local\/\{z\}/)
    fireEvent.change(url, { target: { value: 'https://t.local/{z}/{x}/{y}.png' } })
    fireEvent.change(screen.getByPlaceholderText('© OpenStreetMap contributors'), { target: { value: '© GIS' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(mapSettingsApi.set).toHaveBeenCalledWith(
      expect.objectContaining({ tile_url: 'https://t.local/{z}/{x}/{y}.png', attribution: '© GIS' })))
    expect(screen.getByText('US states')).toBeTruthy()
    expect(screen.queryAllByRole('button', { name: 'Install' })).toHaveLength(1)
  })
})
