import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import MapLayersEditor, { type MapLayerCfg } from './MapLayersEditor'

vi.mock('../../services/api', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  boundarySetsApi: { list: vi.fn().mockResolvedValue([]), get: vi.fn(), create: vi.fn(), remove: vi.fn() },
}))

const cols = [
  { id: 1, name: 'country', dtype: 'categorical', missing_pct: 0, stats: {} },
  { id: 2, name: 'lat', dtype: 'numeric', missing_pct: 0, stats: {} },
  { id: 3, name: 'lon', dtype: 'numeric', missing_pct: 0, stats: {} },
]

describe('MapLayersEditor', () => {
  it('adds a regions layer first, then points, and asks for each kind’s own fields', () => {
    const onChange = vi.fn()
    const { rerender } = render(<MapLayersEditor value={[]} onChange={onChange} columns={cols as never} />)
    fireEvent.click(screen.getByRole('button', { name: '+ Add layer' }))
    const first = onChange.mock.calls[0][0] as MapLayerCfg[]
    expect(first[0].kind).toBe('regions')
    rerender(<MapLayersEditor value={first} onChange={onChange} columns={cols as never} />)
    expect(screen.getByLabelText('Layer 1 Region')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '+ Add layer' }))
    const second = onChange.mock.calls[1][0] as MapLayerCfg[]
    expect(second[1].kind).toBe('points')
    rerender(<MapLayersEditor value={second} onChange={onChange} columns={cols as never} />)
    // Latitude lists numbers only.
    const lat = screen.getByLabelText('Layer 2 Latitude') as HTMLSelectElement
    expect([...lat.options].map(o => o.value)).toEqual(['', 'lat', 'lon'])
  })

  it('reorders and removes layers, and stops at six', () => {
    const onChange = vi.fn()
    const six = Array.from({ length: 6 }, (_, i) => ({ id: String(i), kind: 'points' as const, title: `L${i}` }))
    render(<MapLayersEditor value={six} onChange={onChange} columns={cols as never} />)
    expect((screen.getByRole('button', { name: '+ Add layer' }) as HTMLButtonElement).disabled).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Move layer 1 up' }))
    expect((onChange.mock.calls[0][0] as MapLayerCfg[]).map(l => l.id).slice(0, 2)).toEqual(['1', '0'])
    fireEvent.click(screen.getByRole('button', { name: 'Remove layer 3' }))
    expect((onChange.mock.calls[1][0] as MapLayerCfg[])).toHaveLength(5)
  })
})
