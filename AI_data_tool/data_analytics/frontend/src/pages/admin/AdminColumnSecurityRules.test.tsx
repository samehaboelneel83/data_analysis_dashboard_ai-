import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import AdminColumnSecurityRules from './AdminColumnSecurityRules'
import { ConfirmProvider } from '../../components/ui/ConfirmDialog'
import type { Dataset } from '../../services/api'

const { dataset } = vi.hoisted(() => ({
  dataset: {
    id: 1, name: 'Orders', row_count: 10, col_count: 3, file_size: 0,
    created_at: '', updated_at: '', calculated_columns: [], measures: [],
    column_meta: {}, column_formats: {}, mode: 'import',
    columns: [
      { id: 1, name: 'region', dtype: 'text', missing_pct: 0, stats: {}, semantic_type: null },
      { id: 2, name: 'salary', dtype: 'numeric', missing_pct: 0, stats: {}, semantic_type: null },
      { id: 3, name: 'email', dtype: 'text', missing_pct: 0, stats: {}, semantic_type: 'email' },
    ],
  } as unknown as Dataset,
}))

vi.mock('../../services/api', () => ({
  columnSecurityApi: {
    list: vi.fn().mockResolvedValue([]),
    create: vi.fn().mockResolvedValue({ id: 7 }),
    remove: vi.fn().mockResolvedValue(undefined),
  },
  adminRolesApi: { list: vi.fn().mockResolvedValue([{ id: 1, name: 'Analyst', is_org_admin: false }]) },
  datasetsApi: { list: vi.fn().mockResolvedValue([dataset]) },
}))

import { columnSecurityApi } from '../../services/api'

const renderPage = () => render(<ConfirmProvider><AdminColumnSecurityRules /></ConfirmProvider>)

beforeEach(() => {
  vi.mocked(columnSecurityApi.list).mockResolvedValue([])
  vi.mocked(columnSecurityApi.create).mockClear()
  vi.mocked(columnSecurityApi.remove).mockClear()
})

describe('AdminColumnSecurityRules', () => {
  it('creates a rule from role + dataset + checked columns', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByRole('button', { name: '+ New Rule' })).not.toBeDisabled())
    fireEvent.click(screen.getByRole('button', { name: '+ New Rule' }))

    // Both columns checked -> exactly those names go to the API.
    fireEvent.click(screen.getByRole('checkbox', { name: /salary/ }))
    fireEvent.click(screen.getByRole('checkbox', { name: /email/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Create rule' }))

    await waitFor(() => expect(columnSecurityApi.create).toHaveBeenCalledWith({
      role_id: 1, dataset_id: 1, denied_columns: ['salary', 'email'],
    }))
    // The new rule appears in the list without a refetch.
    expect(await screen.findByText(/hides: salary, email/)).toBeInTheDocument()
  })

  it('refuses to create a rule with no columns picked', async () => {
    // An empty denied set is not a weaker rule, it is no rule -- the backend
    // 400s it, so the button must not fire at all.
    renderPage()
    await waitFor(() => expect(screen.getByRole('button', { name: '+ New Rule' })).not.toBeDisabled())
    fireEvent.click(screen.getByRole('button', { name: '+ New Rule' }))
    expect(screen.getByRole('button', { name: 'Create rule' })).toBeDisabled()
    expect(columnSecurityApi.create).not.toHaveBeenCalled()
  })

  it('delete asks first, and cancelling does not call the API', async () => {
    vi.mocked(columnSecurityApi.list).mockResolvedValue([
      { id: 5, role_id: 1, dataset_id: 1, denied_columns: ['salary'] },
    ])
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Delete' }))

    // The confirm dialog names what becomes visible again.
    const dialog = await screen.findByRole('alertdialog')
    expect(dialog.textContent).toContain('salary')
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(columnSecurityApi.remove).not.toHaveBeenCalled()
    expect(screen.getByText(/hides: salary/)).toBeInTheDocument()
  })

  it('confirming the delete removes the rule', async () => {
    vi.mocked(columnSecurityApi.list).mockResolvedValue([
      { id: 5, role_id: 1, dataset_id: 1, denied_columns: ['salary'] },
    ])
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Delete' }))
    const dialog = await screen.findByRole('alertdialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }))

    await waitFor(() => expect(columnSecurityApi.remove).toHaveBeenCalledWith(5))
    await waitFor(() => expect(screen.queryByText(/hides: salary/)).not.toBeInTheDocument())
  })

  it('shows a persistent error banner when the initial load fails, not only a toast', async () => {
    // The rules list, roles and datasets all come from one initial fetch --
    // losing it is the page's whole content going missing, not a transient
    // action failure that a toast can adequately report.
    vi.mocked(columnSecurityApi.list).mockRejectedValue(new Error('down'))
    renderPage()

    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })

  it('retries the load from the error banner and recovers', async () => {
    vi.mocked(columnSecurityApi.list)
      .mockRejectedValueOnce(new Error('down'))
      .mockResolvedValueOnce([{ id: 5, role_id: 1, dataset_id: 1, denied_columns: ['salary'] }])
    renderPage()

    await screen.findByRole('alert')
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))

    expect(await screen.findByText(/hides: salary/)).toBeInTheDocument()
  })
})
