import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders as render, screen, fireEvent, waitFor, within } from '../../test/renderWithProviders'
import ShareLinksDialog from './ShareLinksDialog'
import { shareLinksApi, embedConfigsApi } from '../../services/api'

vi.mock('../../services/api', () => ({
  shareLinksApi: { create: vi.fn(), list: vi.fn(), revoke: vi.fn() },
  embedConfigsApi: { create: vi.fn(), list: vi.fn(), setEnabled: vi.fn(), delete: vi.fn() },
}))

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(shareLinksApi.list).mockResolvedValue([
    { id: 1, creator: 'me@x.com', created_at: '2026-08-23', expires_at: '2026-08-30', active: true, pinned: false,
      access_count: 3, last_access_at: '2026-08-24T00:00:00Z' },
  ])
  vi.mocked(shareLinksApi.create).mockResolvedValue(
    { id: 2, token: 'tok123', expires_at: '2026-08-30', pinned: false, note: '' })
  vi.mocked(shareLinksApi.revoke).mockResolvedValue(undefined as never)
  vi.mocked(embedConfigsApi.list).mockResolvedValue([
    { id: 5, name: 'portal', allowed_origins: ['https://app.customer.com'], enabled: true,
      created_at: '2026-08-23', last_used_at: null },
  ])
  vi.mocked(embedConfigsApi.create).mockResolvedValue(
    { id: 6, name: 'new-cfg', secret: 'embed-secret-xyz', allowed_origins: [], enabled: true,
      created_at: '2026-08-24', note: '' })
  vi.mocked(embedConfigsApi.setEnabled).mockResolvedValue(undefined as never)
  vi.mocked(embedConfigsApi.delete).mockResolvedValue(undefined as never)
})

describe('ShareLinksDialog', () => {
  it('states the permission consequence before anything is minted', async () => {
    render(<ShareLinksDialog reportId={7} onClose={() => {}} />)
    expect(await screen.findByText(/with your data permissions/i)).toBeInTheDocument()
  })

  it('shows per-link access count and last-access', async () => {
    render(<ShareLinksDialog reportId={7} onClose={() => {}} />)
    expect(await screen.findByText(/3 views/)).toBeInTheDocument()
  })

  it('mints a link and shows the one-time URL', async () => {
    render(<ShareLinksDialog reportId={7} onClose={() => {}} />)
    fireEvent.change(await screen.findByLabelText(/Expires after/), { target: { value: '14' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create guest link' }))
    await waitFor(() => expect(shareLinksApi.create).toHaveBeenCalledWith(7, 14, false))
    expect(screen.getByLabelText('Guest link URL')).toHaveValue(`${window.location.origin}/shared/tok123`)
    expect(screen.getByText(/shown only once/)).toBeInTheDocument()
  })

  it('sends pinned:true when "Pin current layout" is checked', async () => {
    render(<ShareLinksDialog reportId={7} onClose={() => {}} />)
    fireEvent.click(await screen.findByLabelText(/Pin current layout/))
    fireEvent.click(screen.getByRole('button', { name: 'Create guest link' }))
    await waitFor(() => expect(shareLinksApi.create).toHaveBeenCalledWith(7, 7, true))
  })

  it('revokes an active link', async () => {
    render(<ShareLinksDialog reportId={7} onClose={() => {}} />)
    fireEvent.click(await screen.findByLabelText('Revoke link 1'))
    // Destructive actions are guarded, so the dialog has to be accepted.
    // The row's trigger carries the same label, so scope to the dialog.
    fireEvent.click(within(await screen.findByRole('alertdialog'))
      .getByRole('button', { name: /revoke link/i }))
    await waitFor(() => expect(shareLinksApi.revoke).toHaveBeenCalledWith(7, 1))
  })

  it('cancelling the confirm leaves the link working', async () => {
    // The blast radius sits outside the system: the URL is already in other
    // people's hands, and revoking cannot be undone.
    render(<ShareLinksDialog reportId={7} onClose={() => {}} />)
    fireEvent.click(await screen.findByLabelText('Revoke link 1'))
    expect(await screen.findByRole('alertdialog')).toHaveTextContent(/cannot be restored/i)
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))

    await waitFor(() =>
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(shareLinksApi.revoke).not.toHaveBeenCalled()
  })

  it('lists existing embed configs', async () => {
    render(<ShareLinksDialog reportId={7} onClose={() => {}} />)
    expect(await screen.findByText(/portal/)).toBeInTheDocument()
  })

  it('creates an embed config and shows the one-time secret plus sample code', async () => {
    render(<ShareLinksDialog reportId={7} onClose={() => {}} />)
    fireEvent.change(await screen.findByLabelText(/Config name/), { target: { value: 'new-cfg' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create embed config' }))
    await waitFor(() => expect(embedConfigsApi.create).toHaveBeenCalledWith(7, 'new-cfg', []))
    expect(screen.getByLabelText('Embed secret')).toHaveValue('embed-secret-xyz')
    expect(screen.getByText(/shown only once/)).toBeInTheDocument()
    expect(screen.getByText(/Python/)).toBeInTheDocument()
    expect(screen.getByText(/Node/)).toBeInTheDocument()
  })

  it('disables and deletes an embed config', async () => {
    render(<ShareLinksDialog reportId={7} onClose={() => {}} />)
    fireEvent.click(await screen.findByLabelText('Disable embed config 5'))
    await waitFor(() => expect(embedConfigsApi.setEnabled).toHaveBeenCalledWith(7, 5, false))
    fireEvent.click(screen.getByLabelText('Delete embed config 5'))
    await waitFor(() => expect(embedConfigsApi.delete).toHaveBeenCalledWith(7, 5))
  })
})
