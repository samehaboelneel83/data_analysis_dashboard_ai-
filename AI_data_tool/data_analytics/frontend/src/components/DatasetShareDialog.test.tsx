import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders as render, screen, fireEvent, waitFor } from '../test/renderWithProviders'
import DatasetShareDialog from './DatasetShareDialog'
import { DirectionProvider } from '../contexts/DirectionContext'
import { adminUsersApi, datasetSharesApi, lineageApi } from '../services/api'

vi.mock('../services/api', () => ({
  adminUsersApi: { list: vi.fn() },
  datasetSharesApi: { list: vi.fn(), create: vi.fn(), delete: vi.fn(), createGroup: vi.fn(), deleteGroup: vi.fn() },
  adminRolesApi: { list: vi.fn().mockResolvedValue([{ id: 3, name: 'HR managers', is_org_admin: false }]) },
  orgUnitsApi: { list: vi.fn().mockResolvedValue([]) },
  lineageApi: { graph: vi.fn().mockResolvedValue({ sources: [], datasets: [], reports: [] }) },
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

    await waitFor(() => expect(datasetSharesApi.create).toHaveBeenCalledWith(5, 1, 'view'))
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

  it('shares with a whole role, view-only (HR evaluation 2.5)', async () => {
    vi.mocked(datasetSharesApi.createGroup).mockResolvedValue({ id: 20, kind: 'role', role_id: 3, name: 'HR managers', level: 'view', created_at: '2026-10-01' })
    render(<DatasetShareDialog datasetId={5} onClose={() => {}} />)
    await screen.findByText('bob@example.com')
    fireEvent.click(screen.getByRole('radio', { name: 'Role' }))
    await waitFor(() => expect((screen.getByLabelText('Role to share with') as HTMLSelectElement).options.length).toBe(2))
    fireEvent.change(screen.getByLabelText('Role to share with'), { target: { value: '3' } })
    fireEvent.click(screen.getByRole('button', { name: 'Share' }))
    await waitFor(() => expect(datasetSharesApi.createGroup).toHaveBeenCalledWith(5, { role_id: 3, level: 'view' }))
    expect(await screen.findByText('HR managers')).toBeInTheDocument()
  })
})

describe('the redesigned share dialog (3c)', () => {
  it('names the dataset and lists who can also open it, dashboards counted from lineage', async () => {
    vi.mocked(lineageApi.graph).mockResolvedValue({ sources: [], datasets: [],
      reports: [{ id: 1, name: 'A', dataset_ids: [5] }, { id: 2, name: 'B', dataset_ids: [5, 6] }, { id: 3, name: 'C', dataset_ids: [6] }] })
    render(<DatasetShareDialog datasetId={5} datasetName="Demo — Sales" createdByMe onClose={() => {}} />)
    expect(await screen.findByRole('heading', { name: 'Share “Demo — Sales”' })).toBeInTheDocument()
    expect(await screen.findByText('Anyone who can open its 2 dashboards')).toBeInTheDocument()
    expect(screen.getByText('You created this dataset')).toBeInTheDocument()
    expect(screen.getByText('Workspace admins')).toBeInTheDocument()
  })

  it('does not claim the reader created it when they did not', async () => {
    render(<DatasetShareDialog datasetId={5} onClose={() => {}} />)
    expect(await screen.findByText('Its creator')).toBeInTheDocument()
    expect(screen.queryByText('You created this dataset')).toBeNull()
  })
})

describe('the share dialog in Arabic (QA T1)', () => {
  it('the avatars speak Arabic, not "YOU"', async () => {
    localStorage.setItem('datalytics.language', 'ar')
    try {
      vi.mocked(lineageApi.graph).mockResolvedValue({ sources: [], datasets: [], reports: [] })
      const { container } = render(<DirectionProvider><DatasetShareDialog datasetId={5} datasetName="Demo — Sales" createdByMe onClose={() => {}} /></DirectionProvider>)
      await waitFor(() => expect(container.ownerDocument.querySelectorAll('.dl-share__avatar').length).toBeGreaterThan(1))
      const avatars = [...container.ownerDocument.querySelectorAll('.dl-share__avatar')].map(a => a.textContent)
      expect(avatars).toContain('أنت')
      expect(avatars.join(' ')).not.toMatch(/YOU|CR|AD/)
    } finally { localStorage.removeItem('datalytics.language') }
  })
})
