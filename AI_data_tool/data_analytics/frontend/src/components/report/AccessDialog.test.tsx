import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import AccessDialog from './AccessDialog'
import { pageVisibilityApi, reportCapabilityApi } from '../../services/api'

vi.mock('../../services/api', () => ({
  pageVisibilityApi: { roles: vi.fn() },
  reportCapabilityApi: { get: vi.fn(), set: vi.fn() },
}))

describe('AccessDialog (HR evaluation 2.3)', () => {
  it('shows a role with no stored level as the real default, not as Full', async () => {
    vi.mocked(pageVisibilityApi.roles).mockResolvedValue([{ id: 7, name: 'HR managers' }])
    vi.mocked(reportCapabilityApi.get).mockResolvedValue({})
    render(<AccessDialog reportId={1} onClose={() => {}} />)
    const sel = await screen.findByLabelText('Access level for HR managers') as HTMLSelectElement
    expect(sel.value).toBe('')
    expect(sel.selectedOptions[0].textContent).toMatch(/Default/)
  })

  it('stores Full as a real row, and Default as no row', async () => {
    vi.mocked(pageVisibilityApi.roles).mockResolvedValue([{ id: 7, name: 'HR managers' }])
    vi.mocked(reportCapabilityApi.get).mockResolvedValue({})
    vi.mocked(reportCapabilityApi.set).mockImplementation(async (_id, levels) => levels as never)
    render(<AccessDialog reportId={1} onClose={() => {}} />)
    const sel = await screen.findByLabelText('Access level for HR managers')
    fireEvent.change(sel, { target: { value: 'data' } })
    await waitFor(() => expect(reportCapabilityApi.set).toHaveBeenLastCalledWith(1, { 7: 'data' }))
    fireEvent.change(sel, { target: { value: '' } })
    await waitFor(() => expect(reportCapabilityApi.set).toHaveBeenLastCalledWith(1, {}))
  })
})
