import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders as render, screen, fireEvent, waitFor } from '../test/renderWithProviders'
import DatasetShareDialog from './DatasetShareDialog'
import { adminUsersApi, datasetSharesApi } from '../services/api'

vi.mock('../services/api', () => ({
  adminUsersApi: { list: vi.fn() },
  datasetSharesApi: { list: vi.fn(), create: vi.fn(), delete: vi.fn() },
}))

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(adminUsersApi.list).mockResolvedValue([
    { id: 1, email: 'alice@example.com', is_active: true, organization: { id: 1, name: 'Org' } as any, role: { id: 1, name: 'Analyst', is_org_admin: false } },
    { id: 2, email: 'bob@example.com', is_active: true, organization: { id: 1, name: 'Org' } as any, role: { id: 1, name: 'Analyst', is_org_admin: false } },
  ])
  vi.mocked(datasetSharesApi.list).mockResolvedValue([
    { id: 10, user_id: 2, email: 'bob@example.com', created_at: '2026-08-20' },
  ])
  vi.mocked(datasetSharesApi.create).mockResolvedValue({ id: 11, user_id: 1, email: 'alice@example.com', created_at: '2026-08-24' })
  vi.mocked(datasetSharesApi.delete).mockResolvedValue(undefined as never)
})

describe('DatasetShareDialog', () => {
  it('states the RLS/permission consequence up front', async () => {
    render(<DatasetShareDialog datasetId={5} onClose={() => {}} />)
    expect(await screen.findByText(/their own/i)).toBeInTheDocument()
  })

  it('lists existing shares and excludes already-shared users from the picker', async () => {
    render(<DatasetShareDialog datasetId={5} onClose={() => {}} />)
    expect(await screen.findByText('bob@example.com')).toBeInTheDocument()

    const picker = screen.getByLabelText('User to share with') as HTMLSelectElement
    const optionValues = Array.from(picker.options).map(o => o.textContent)
    expect(optionValues).toContain('alice@example.com')
    expect(optionValues).not.toContain('bob@example.com')
  })

  it('shares the dataset with the picked user', async () => {
    render(<DatasetShareDialog datasetId={5} onClose={() => {}} />)
    await screen.findByText('bob@example.com')

    fireEvent.change(screen.getByLabelText('User to share with'), { target: { value: '1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Share' }))

    await waitFor(() => expect(datasetSharesApi.create).toHaveBeenCalledWith(5, 1))
    expect(await screen.findByText('alice@example.com')).toBeInTheDocument()
  })

  it('removes a share', async () => {
    render(<DatasetShareDialog datasetId={5} onClose={() => {}} />)
    fireEvent.click(await screen.findByLabelText('Remove share for bob@example.com'))
    // Destructive actions are guarded, so the dialog has to be accepted.
    fireEvent.click(await screen.findByRole('button', { name: /remove access/i }))

    await waitFor(() => expect(datasetSharesApi.delete).toHaveBeenCalledWith(5, 10))
    await waitFor(() => expect(screen.getByText('Not shared with anyone yet.')).toBeInTheDocument())
    expect(screen.queryByLabelText('Remove share for bob@example.com')).not.toBeInTheDocument()
  })

  it('cancelling the confirm keeps the share', async () => {
    render(<DatasetShareDialog datasetId={5} onClose={() => {}} />)
    fireEvent.click(await screen.findByLabelText('Remove share for bob@example.com'))
    // Names WHO loses access -- the rows look alike, and a mis-click here cuts
    // off the wrong colleague.
    expect(await screen.findByRole('alertdialog')).toHaveTextContent(/bob@example\.com/)
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))

    await waitFor(() =>
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(datasetSharesApi.delete).not.toHaveBeenCalled()
  })
})
