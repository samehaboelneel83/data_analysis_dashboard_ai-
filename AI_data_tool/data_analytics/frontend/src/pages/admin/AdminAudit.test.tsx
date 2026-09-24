import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders as render, screen, waitFor, fireEvent } from '../../test/renderWithProviders'
import AdminAudit from './AdminAudit'

vi.mock('../../services/api', () => ({
  adminAuditApi: { list: vi.fn() },
}))

import { adminAuditApi } from '../../services/api'

const ROWS = [
  { id: 1, actor_email: 'admin@x.com', action: 'row_security_rule.create', target: 'dataset:1',
    detail: "region == 'North'", created_at: '2026-01-01T00:00:00Z' },
  { id: 2, actor_email: 'admin@x.com', action: 'api_key.create', target: 'prefix:abcd',
    detail: 'ci-key', created_at: '2026-01-02T00:00:00Z' },
]

describe('AdminAudit', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('lists rows returned by the API', async () => {
    vi.mocked(adminAuditApi.list).mockResolvedValue(ROWS)
    render(<AdminAudit />)

    expect(await screen.findByText('dataset:1')).toBeInTheDocument()
    expect(screen.getAllByText('row_security_rule.create').length).toBeGreaterThan(0)
    expect(screen.getAllByText('api_key.create').length).toBeGreaterThan(0)
  })

  it('shows an empty state when there are no rows', async () => {
    vi.mocked(adminAuditApi.list).mockResolvedValue([])
    render(<AdminAudit />)

    expect(await screen.findByText(/No audit entries match/)).toBeInTheDocument()
  })

  it('re-queries the API with the action filter when Apply is clicked', async () => {
    vi.mocked(adminAuditApi.list).mockResolvedValue(ROWS)
    render(<AdminAudit />)
    await waitFor(() => expect(adminAuditApi.list).toHaveBeenCalled())
    // Nothing is cleared, and nothing is counted. Two earlier attempts to make
    // this test stable both did: first "exactly one call so far", then a
    // mockClear before the click. Both still raced the MOUNT fetch, which
    // resolves on its own schedule -- under a loaded full-suite run the cleared
    // spy would record only that late mount call and the assertion below timed
    // out against `action: undefined`.
    //
    // The mount fetch passes no action, so it can never satisfy the assertion.
    // "A call with these arguments happened at some point" is exactly what this
    // test means, and it is true regardless of what else happened or when.

    // The action filter is a <select> whose options are built from the rows the
    // MOUNT fetch returns. Until that has resolved the option does not exist, so
    // `fireEvent.change` selects nothing, the value stays '' and Apply queries
    // with `action: undefined` -- which is what this test used to see under a
    // loaded full-suite run, and what two rounds of longer timeouts could not
    // fix, because nothing was slow: the option simply was not there yet.
    await screen.findByRole('option', { name: 'api_key.create' })

    fireEvent.change(screen.getByLabelText('Filter by action'), { target: { value: 'api_key.create' } })
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }))

    await waitFor(() => expect(adminAuditApi.list).toHaveBeenCalledWith(
      { action: 'api_key.create', q: undefined }), { timeout: 5000 })
  })

  it('re-queries the API with the target filter when Apply is clicked', async () => {
    vi.mocked(adminAuditApi.list).mockResolvedValue(ROWS)
    render(<AdminAudit />)
    await waitFor(() => expect(adminAuditApi.list).toHaveBeenCalled())
    vi.mocked(adminAuditApi.list).mockClear()

    fireEvent.change(screen.getByLabelText('Filter by target'), { target: { value: 'dataset:1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }))

    await waitFor(() => expect(adminAuditApi.list).toHaveBeenCalledWith(
      { action: undefined, q: 'dataset:1' }))
  })

  it('shows a persistent error banner when the initial load fails, not only a fading toast', async () => {
    // A failed fetch is this page's whole content going missing -- a toast that
    // has already faded leaves an admin staring at a blank page with no
    // explanation and no way to retry.
    vi.mocked(adminAuditApi.list).mockRejectedValue({ response: { data: { detail: 'db down' } } })
    render(<AdminAudit />)

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('db down')).toBeInTheDocument()
  })

  it('retries the load from the error banner and recovers', async () => {
    vi.mocked(adminAuditApi.list)
      .mockRejectedValueOnce(new Error('down'))
      .mockResolvedValueOnce(ROWS)
    render(<AdminAudit />)

    await screen.findByRole('alert')
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))

    expect(await screen.findByText('dataset:1')).toBeInTheDocument()
  })
})
