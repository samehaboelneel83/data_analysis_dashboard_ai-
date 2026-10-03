import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import IncrementalSettingsForm from './IncrementalSettings'

vi.mock('../../services/api', () => ({ datasetsApi: { incremental: vi.fn(), setIncremental: vi.fn() } }))
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))

import { datasetsApi } from '../../services/api'

const full = { strategy: 'full' as const, cursor_column: null, key_column: null, lookback_hours: null,
               full_reload_days: null, cursor_value: null, last_full_at: null, after_source: false }

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(datasetsApi.incremental).mockResolvedValue(full)
})

describe('IncrementalSettingsForm (pipeline phase 4)', () => {
  it('saves an incremental load merged on a key, with a weekly full reload', async () => {
    vi.mocked(datasetsApi.setIncremental).mockImplementation(async (_id, body) => ({ ...full, ...body }))
    render(<IncrementalSettingsForm datasetId={3} columns={['order_id', 'updated_at', 'status']} />)
    fireEvent.change(await screen.findByLabelText('How'), { target: { value: 'incremental' } })
    fireEvent.change(screen.getByLabelText(/grows with new rows/), { target: { value: 'updated_at' } })
    fireEvent.change(screen.getByLabelText(/identifies a row/), { target: { value: 'order_id' } })
    expect(screen.getByText(/order_id is already loaded is replaced/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/re-read the last/), { target: { value: '24' } })
    fireEvent.change(screen.getByLabelText('Reload everything'), { target: { value: '7' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save loading' }))
    await waitFor(() => expect(datasetsApi.setIncremental).toHaveBeenCalledWith(3, {
      strategy: 'incremental', cursor_column: 'updated_at', key_column: 'order_id',
      lookback_hours: 24, full_reload_days: 7 }))
  })

  it('without a key it says changed rows are not updated, and offers no look-back', async () => {
    render(<IncrementalSettingsForm datasetId={3} columns={['id', 'ts']} />)
    fireEvent.change(await screen.findByLabelText('How'), { target: { value: 'incremental' } })
    expect(screen.getByText(/are not updated/)).toBeInTheDocument()
    expect(screen.queryByLabelText(/re-read the last/)).toBeNull()
    expect(screen.getByRole('button', { name: 'Save loading' })).toBeDisabled()     // no cursor yet
  })
})
