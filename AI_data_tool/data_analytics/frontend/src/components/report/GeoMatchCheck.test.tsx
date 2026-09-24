import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import GeoMatchCheck from './GeoMatchCheck'
import { boundarySetsApi, widgetDataApi } from '../../services/api'

vi.mock('../../services/api', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  widgetDataApi: { query: vi.fn() },
  boundarySetsApi: { list: vi.fn(), get: vi.fn(), create: vi.fn(), remove: vi.fn(), setPins: vi.fn() },
}))

describe('GeoMatchCheck', () => {
  it('names the unmatched values with their rows before anything is saved', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      rows: [{ name: 'France', value: 5 }, { name: 'Atlantis', value: 2 }],
      truncation: { applied: false },
    } as never)
    const commit = vi.fn()
    render(<GeoMatchCheck datasetId={1} column="country" setId={null} setName="Countries"
      onCommit={commit} onClose={() => {}} />)
    expect(await screen.findByText('71%')).toBeTruthy()
    expect(screen.getByTestId('geo-check-unmatched').textContent).toContain('Atlantis')
    expect(screen.getByTestId('geo-check-unmatched').textContent).toContain('2 rows')
    fireEvent.click(screen.getByRole('button', { name: 'Use anyway (71% mapped)' }))
    expect(commit).toHaveBeenCalled()
    // It asked for every value, counted -- the same pipeline the map reads.
    expect(vi.mocked(widgetDataApi.query).mock.calls[0][1]).toMatchObject({ dimension: 'country', aggregation: 'count' })
  })

  it('says when every value was found, and discloses a capped check', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      rows: [{ name: 'Egypt', value: 9 }], truncation: { applied: true, shown: 1, of: 6000 },
    } as never)
    render(<GeoMatchCheck datasetId={1} column="country" setId={null} setName="Countries"
      onCommit={() => {}} onClose={() => {}} />)
    expect(await screen.findByText('Every value names a region.')).toBeTruthy()
    expect(screen.getByText(/most common of 6,000 values/)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Use as geography' })).toBeTruthy()
  })

  it('pins an unmatched value to a region by hand, and the match is re-checked', async () => {
    const sq = (x: number) => [[[x, 30], [x, 31], [x + 1, 31], [x + 1, 30], [x, 30]]]
    const geometry = { type: 'FeatureCollection', features: [
      { type: 'Feature', properties: { name: 'Cairo' }, geometry: { type: 'Polygon', coordinates: sq(31) } },
      { type: 'Feature', properties: { name: 'Giza' }, geometry: { type: 'Polygon', coordinates: sq(29) } },
    ] }
    vi.mocked(boundarySetsApi.get)
      .mockResolvedValueOnce({ id: 3, key_properties: ['name'], geometry } as never)
      .mockResolvedValueOnce({ id: 3, key_properties: ['name'], geometry: { ...geometry, x_pins: { 'Greater Cairo': 0 } } } as never)
    vi.mocked(boundarySetsApi.setPins).mockResolvedValue({ id: 3, pins: { 'Greater Cairo': 0 } } as never)
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      rows: [{ name: 'Giza', value: 1 }, { name: 'Greater Cairo', value: 3 }], truncation: { applied: false },
    } as never)
    render(<GeoMatchCheck datasetId={1} column="gov" setId={3} setName="Egypt"
      onCommit={() => {}} onClose={() => {}} />)
    expect(await screen.findByText('25%')).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Pin Greater Cairo to a region'), { target: { value: '0' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save 1 pin' }))
    expect(await screen.findByText('100%')).toBeTruthy()
    expect(boundarySetsApi.setPins).toHaveBeenCalledWith(3, { 'Greater Cairo': 0 })
  })
})
