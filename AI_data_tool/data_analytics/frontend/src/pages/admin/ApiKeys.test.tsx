import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import toast from 'react-hot-toast'
import ApiKeys from './ApiKeys'
import { ConfirmProvider } from '../../components/ui/ConfirmDialog'

vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('../../services/api', () => ({
  apiKeysApi: {
    list: vi.fn().mockResolvedValue([{ id: 1, name: 'existing', prefix: 'abc123', last_used_at: null }]),
    create: vi.fn().mockResolvedValue({ id: 2, name: 'MCP agent', prefix: 'newpfx', key: 'dk_newpfx.thesecret' }),
    revoke: vi.fn(),
  },
}))

import { apiKeysApi } from '../../services/api'

const renderPage = () => render(<ConfirmProvider><ApiKeys /></ConfirmProvider>)

// Call history was never cleared between tests, so a `not.toHaveBeenCalled()`
// assertion saw the previous test's revoke. Return values are re-stubbed too,
// since clearAllMocks drops the inline mockResolvedValue defaults above.
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(apiKeysApi.list).mockResolvedValue(
    [{ id: 1, name: 'existing', prefix: 'abc123', last_used_at: null }] as never)
  vi.mocked(apiKeysApi.create).mockResolvedValue(
    { id: 2, name: 'MCP agent', prefix: 'newpfx', key: 'dk_newpfx.thesecret' } as never)
  vi.mocked(apiKeysApi.revoke).mockResolvedValue(undefined as never)
})

describe('ApiKeys', () => {
  it('shows the EmptyState card (icon + title + description) when there are no keys', async () => {
    vi.mocked(apiKeysApi.list).mockResolvedValueOnce([])
    renderPage()

    expect(await screen.findByText('No API keys yet')).toBeInTheDocument()
    expect(screen.getByText(/Create a key above/)).toBeInTheDocument()
  })

  it('creates a key and reveals the secret exactly once', async () => {
    renderPage()
    await screen.findByText('existing')

    fireEvent.change(screen.getByLabelText('Key name'), { target: { value: 'MCP agent' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create key' }))

    await waitFor(() => expect(apiKeysApi.create).toHaveBeenCalledWith('MCP agent'))
    // the full secret is shown for copying, with the once-only warning
    expect(await screen.findByText('dk_newpfx.thesecret')).toBeInTheDocument()
    expect(screen.getByText(/shown only once/i)).toBeInTheDocument()
  })
  // Revoking a LEAKED key is the moment this page exists for, and the failure
  // path was unguarded -- unlike `create` directly above it. The rejection
  // threw out of the handler before any toast, so an admin saw no success
  // message, no error message, and the key still listed. Nothing told them the
  // key was still live.
  const openRevokeDialog = async () => {
    renderPage()
    await screen.findByText('existing')
    fireEvent.click(screen.getByRole('button', { name: /revoke/i }))
    return screen.findByRole('alertdialog')
  }

  it('labels the confirm button for the action it performs', async () => {
    // The dialog's default label is "Delete", so this one read "Delete" while
    // the button that opened it said "Revoke".
    const dialog = await openRevokeDialog()
    expect(within(dialog).getByRole('button', { name: /revoke key/i })).toBeInTheDocument()
  })

  it('reports a failed revoke instead of failing silently', async () => {
    vi.mocked(apiKeysApi.revoke).mockRejectedValueOnce(
      { response: { data: { detail: 'Key is in use by a running agent' } } })
    const dialog = await openRevokeDialog()
    fireEvent.click(within(dialog).getByRole('button', { name: /revoke key/i }))

    await waitFor(() => expect(toast.error).toHaveBeenCalled())
    // THE assertion: it must not claim success for a key that is still live.
    expect(toast.success).not.toHaveBeenCalled()
    expect(screen.getByText('existing')).toBeInTheDocument()
  })

  it('confirms a successful revoke', async () => {
    vi.mocked(apiKeysApi.revoke).mockResolvedValueOnce(undefined as never)
    const dialog = await openRevokeDialog()
    fireEvent.click(within(dialog).getByRole('button', { name: /revoke key/i }))

    await waitFor(() => expect(apiKeysApi.revoke).toHaveBeenCalledWith(1))
    await waitFor(() => expect(toast.success).toHaveBeenCalled())
  })

  it('does not revoke when the dialog is cancelled', async () => {
    const dialog = await openRevokeDialog()
    fireEvent.click(within(dialog).getByRole('button', { name: /cancel/i }))
    await waitFor(() =>
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(apiKeysApi.revoke).not.toHaveBeenCalled()
  })
})
