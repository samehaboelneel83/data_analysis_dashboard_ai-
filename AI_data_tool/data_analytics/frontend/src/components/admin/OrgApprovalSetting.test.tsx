import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import OrgApprovalSetting from './OrgApprovalSetting'
import { ConfirmProvider } from '../ui/ConfirmDialog'

vi.mock('react-hot-toast', () => ({ default: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }))
vi.mock('../../services/api', () => ({ reviewApi: { settings: vi.fn(), setApproval: vi.fn() } }))

import { reviewApi } from '../../services/api'

const show = () => render(<ConfirmProvider><OrgApprovalSetting /></ConfirmProvider>)

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(reviewApi.settings).mockResolvedValue({ publish_gate: false, require_approval: false })
})

describe('the organisation approval switch on Admin settings (F-09)', () => {
  it('shows the current value and asks before turning it on, naming the organisation-wide effect', async () => {
    vi.mocked(reviewApi.setApproval).mockResolvedValue({ publish_gate: false, require_approval: true })
    show()
    const box = await screen.findByRole('checkbox', { name: /Ask for approval before anything is published/ })
    await waitFor(() => expect(box).toBeEnabled())
    expect(box).not.toBeChecked()
    fireEvent.click(box)
    const ask = await screen.findByRole('alertdialog')
    expect(ask).toHaveTextContent('every dashboard in the organisation')
    expect(reviewApi.setApproval).not.toHaveBeenCalled()
    fireEvent.click(within(ask).getByRole('button', { name: 'Turn on' }))
    await waitFor(() => expect(reviewApi.setApproval).toHaveBeenCalledWith(true))
    await waitFor(() => expect(box).toBeChecked())
  })

  it('cancelling changes nothing', async () => {
    vi.mocked(reviewApi.settings).mockResolvedValue({ publish_gate: false, require_approval: true })
    show()
    const box = await screen.findByRole('checkbox', { name: /Ask for approval/ })
    await waitFor(() => expect(box).toBeChecked())
    fireEvent.click(box)
    fireEvent.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(reviewApi.setApproval).not.toHaveBeenCalled()
    expect(box).toBeChecked()
  })
})
