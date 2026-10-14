import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import DatasetAllowAi from './DatasetAllowAi'
import { allowAiApi } from '../services/api'

vi.mock('../services/api', () => ({ allowAiApi: { get: vi.fn(), set: vi.fn() } }))
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))

beforeEach(() => vi.clearAllMocks())

describe('DatasetAllowAi', () => {
  it('lets an uploaded dataset be switched off, and says what is in force', async () => {
    vi.mocked(allowAiApi.get).mockResolvedValue({ own: null, effective: true, decided_by: 'default', connection: null })
    vi.mocked(allowAiApi.set).mockResolvedValue({ own: false, effective: false, decided_by: 'dataset', connection: null })
    render(<DatasetAllowAi datasetId={7} />)
    const box = await screen.findByRole('combobox', { name: 'Allow AI on this dataset' })
    fireEvent.change(box, { target: { value: 'off' } })
    await waitFor(() => expect(allowAiApi.set).toHaveBeenCalledWith(7, false))
    await waitFor(() => expect((box as HTMLSelectElement).value).toBe('off'))
  })

  it('cannot switch on what its connection switched off', async () => {
    vi.mocked(allowAiApi.get).mockResolvedValue({ own: null, effective: false, decided_by: 'connection', connection: 'Warehouse' })
    render(<DatasetAllowAi datasetId={7} />)
    const box = await screen.findByRole('combobox', { name: 'Allow AI on this dataset' })
    expect([...(box as HTMLSelectElement).options].map(o => o.value)).toEqual(['', 'off'])   // no "on"
    expect(screen.getByTestId('dataset-allow-ai').getAttribute('title')).toContain('Warehouse')
  })
})
