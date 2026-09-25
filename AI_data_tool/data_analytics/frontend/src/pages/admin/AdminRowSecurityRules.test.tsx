import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import AdminRowSecurityRules from './AdminRowSecurityRules'
import { ConfirmProvider } from '../../components/ui/ConfirmDialog'
import type { Dataset } from '../../services/api'

const { dataset, dataset2 } = vi.hoisted(() => ({
  dataset: {
    id: 1, name: 'Orders', row_count: 10, col_count: 2, file_size: 0,
    created_at: '', updated_at: '', calculated_columns: [], measures: [],
    column_meta: {}, column_formats: {}, mode: 'import',
    columns: [
      { id: 1, name: 'owner_email', dtype: 'text', missing_pct: 0, stats: {}, semantic_type: 'email' },
      { id: 2, name: 'region', dtype: 'categorical', missing_pct: 0, stats: {}, semantic_type: null },
    ],
  } satisfies Dataset,
  dataset2: {
    id: 2, name: 'Invoices', row_count: 5, col_count: 1, file_size: 0,
    created_at: '', updated_at: '', calculated_columns: [], measures: [],
    column_meta: {}, column_formats: {}, mode: 'import',
    columns: [
      { id: 3, name: 'amount', dtype: 'numeric', missing_pct: 0, stats: {}, semantic_type: null },
    ],
  } satisfies Dataset,
}))

vi.mock('../../services/api', () => ({
  adminRlsRulesApi: {
    list: vi.fn().mockResolvedValue([]), create: vi.fn(), update: vi.fn(), delete: vi.fn(),
    autoGenerate: vi.fn().mockResolvedValue({ proposals: [] }),
    preflight: vi.fn().mockResolvedValue({ columns: [], denied: [] }),
  },
  adminRolesApi: { list: vi.fn().mockResolvedValue([{ id: 1, name: 'Analyst', is_org_admin: false }]) },
  datasetsApi: { list: vi.fn().mockResolvedValue([dataset, dataset2]) },
}))

import { adminRlsRulesApi } from '../../services/api'

const renderPage = () => render(<ConfirmProvider><AdminRowSecurityRules /></ConfirmProvider>)

describe('AdminRowSecurityRules load failure', () => {
  it('shows a persistent LoadError banner instead of the empty-state cards when the initial load fails', async () => {
    vi.mocked(adminRlsRulesApi.list).mockRejectedValueOnce({ response: { data: { detail: 'db down' } } })
    renderPage()

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('db down')).toBeInTheDocument()
    // Neither the "no rules" empty state nor the "need a role and dataset" precondition
    // banner may render on a failed load -- both would misreport what actually happened.
    expect(screen.queryByText('No row-security rules yet')).not.toBeInTheDocument()
    expect(screen.queryByText(/You need at least one role and one dataset/)).not.toBeInTheDocument()
  })

  it('recovers on retry: the banner disappears and real content renders', async () => {
    vi.mocked(adminRlsRulesApi.list).mockRejectedValueOnce({ response: { data: { detail: 'db down' } } })
    renderPage()
    await screen.findByRole('alert')

    vi.mocked(adminRlsRulesApi.list).mockResolvedValueOnce([])
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))

    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
    expect(await screen.findByText('No row-security rules yet')).toBeInTheDocument()
  })
})

describe('AdminRowSecurityRules — S0b codeless builder', () => {
  it('pre-suggests the email-typed column over the plain one', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByRole('button', { name: 'New rule' })).not.toBeDisabled())
    fireEvent.click(screen.getByRole('button', { name: 'New rule' }))

    const columnSelect = screen.getByLabelText('Column') as HTMLSelectElement
    const suggestedGroup = columnSelect.querySelector('optgroup[label="Suggested (looks like a user/owner column)"]')
    expect(suggestedGroup).not.toBeNull()
    expect(suggestedGroup!.textContent).toContain('owner_email')
    expect(columnSelect.value).toBe('owner_email')
  })

  it('generates the exact expression for "current user email"', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByRole('button', { name: 'New rule' })).not.toBeDisabled())
    fireEvent.click(screen.getByRole('button', { name: 'New rule' }))

    expect(screen.getByText('owner_email == USEREMAIL()')).toBeInTheDocument()
  })

  it('generates a literal expression when "Literal value" is picked', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByRole('button', { name: 'New rule' })).not.toBeDisabled())
    fireEvent.click(screen.getByRole('button', { name: 'New rule' }))

    fireEvent.change(screen.getByLabelText('Column'), { target: { value: 'region' } })
    fireEvent.change(screen.getByLabelText('Match'), { target: { value: 'literal' } })
    fireEvent.change(screen.getByLabelText('Literal value'), { target: { value: 'North' } })

    expect(screen.getByText('region == "North"')).toBeInTheDocument()
  })

  it('"Use this expression" copies the generated text into the filter, and Save sends it through the existing API', async () => {
    vi.mocked(adminRlsRulesApi.create).mockResolvedValue({ id: 9, role_id: 1, dataset_id: 1, filter_expr: 'owner_email == USEREMAIL()', auto_generated: false, created_at: '' })
    renderPage()
    await waitFor(() => expect(screen.getByRole('button', { name: 'New rule' })).not.toBeDisabled())
    fireEvent.click(screen.getByRole('button', { name: 'New rule' }))

    fireEvent.click(screen.getByRole('button', { name: 'Use this expression' }))
    expect(screen.getByPlaceholderText("region == 'North'")).toHaveValue('owner_email == USEREMAIL()')

    fireEvent.click(screen.getByRole('button', { name: 'Create' }))

    await waitFor(() => expect(adminRlsRulesApi.create).toHaveBeenCalledWith({
      role_id: 1, dataset_id: 1, filter_expr: 'owner_email == USEREMAIL()',
    }))
  })

  it('re-derives the picked column and generated expression when the dataset is switched', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByRole('button', { name: 'New rule' })).not.toBeDisabled())
    fireEvent.click(screen.getByRole('button', { name: 'New rule' }))

    expect((screen.getByLabelText('Column') as HTMLSelectElement).value).toBe('owner_email')
    expect(screen.getByText('owner_email == USEREMAIL()')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Dataset *'), { target: { value: '2' } })

    // Invoices has no user-ish column, so the picker falls back to its only column.
    expect((screen.getByLabelText('Column') as HTMLSelectElement).value).toBe('amount')
    expect(screen.getByText('amount == USEREMAIL()')).toBeInTheDocument()
    expect(screen.queryByText('owner_email == USEREMAIL()')).not.toBeInTheDocument()
  })
})

describe('AdminRowSecurityRules — S0c auto-generate', () => {
  it('shows an "auto" badge on rules the server flags auto_generated', async () => {
    vi.mocked(adminRlsRulesApi.list).mockResolvedValueOnce([
      { id: 1, role_id: 1, dataset_id: 1, filter_expr: '`owner_email` == USEREMAIL()', auto_generated: true, created_at: '' },
    ])
    renderPage()

    await waitFor(() => expect(screen.getByText('auto')).toBeInTheDocument())
  })

  it('does not show an "auto" badge on a hand-written rule', async () => {
    vi.mocked(adminRlsRulesApi.list).mockResolvedValueOnce([
      { id: 1, role_id: 1, dataset_id: 1, filter_expr: "region == 'North'", auto_generated: false, created_at: '' },
    ])
    renderPage()

    await waitFor(() => expect(screen.getByText("region == 'North'")).toBeInTheDocument())
    expect(screen.queryByText('auto')).not.toBeInTheDocument()
  })

  it('opens proposals, applies checked ones, and adds the resulting rule to the list', async () => {
    vi.mocked(adminRlsRulesApi.autoGenerate).mockImplementation(async (datasetId, opts) => {
      if (!opts?.apply) {
        return { proposals: [{ column: 'owner_email', kind: 'user_email', expression: '`owner_email` == USEREMAIL()' }] }
      }
      return {
        proposals: [],
        created: { id: 5, role_id: opts.role_id!, dataset_id: datasetId, filter_expr: '`owner_email` == USEREMAIL()', auto_generated: true, created_at: '' },
      }
    })
    renderPage()
    await waitFor(() => expect(screen.getByRole('button', { name: /Auto-generate rules/ })).not.toBeDisabled())
    fireEvent.click(screen.getByRole('button', { name: /Auto-generate rules/ }))

    await waitFor(() => expect(screen.getByText('`owner_email` == USEREMAIL()')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: 'Apply selected' }))

    await waitFor(() => expect(adminRlsRulesApi.autoGenerate).toHaveBeenCalledWith(
      1, { role_id: 1, apply: true, columns: ['owner_email'] },
    ))
    await waitFor(() => expect(screen.getByText('auto')).toBeInTheDocument())
  })
})

describe('overlap notice', () => {
  it('tells the admin when the rule reads a column the role cannot see', async () => {
    vi.mocked(adminRlsRulesApi.preflight).mockResolvedValue({ columns: ['region'], denied: ['region'] })
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: /new rule/i }))
    fireEvent.change(screen.getByPlaceholderText("region == 'North'"), { target: { value: "region == 'North'" } })
    // 300 ms debounce inside a 1 s default findBy is the load-flake shape; give it room.
    expect(await screen.findByText(/reads region, which this role cannot see/i, {}, { timeout: 3000 })).toBeInTheDocument()
    expect(screen.getByText(/the rule still applies/i)).toBeInTheDocument()
    await waitFor(() => expect(adminRlsRulesApi.preflight).toHaveBeenCalledWith(1, 1, "region == 'North'"))
  })
})

describe('AdminRowSecurityRules — U1 row action menu', () => {
  it('the ⋯ menu Edit item opens the same edit form as the Edit button', async () => {
    vi.mocked(adminRlsRulesApi.list).mockResolvedValueOnce([
      { id: 1, role_id: 1, dataset_id: 1, filter_expr: "region == 'North'", auto_generated: false, created_at: '' },
    ])
    renderPage()
    await waitFor(() => expect(screen.getByText("region == 'North'")).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: 'More actions for rule Analyst on Orders' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Edit rule' }))

    expect(await screen.findByText('Edit Row-Security Rule')).toBeInTheDocument()
  })

  it('the ⋯ menu Delete item routes through the same confirm+delete flow as the Delete button', async () => {
    vi.mocked(adminRlsRulesApi.list).mockResolvedValueOnce([
      { id: 1, role_id: 1, dataset_id: 1, filter_expr: "region == 'North'", auto_generated: false, created_at: '' },
    ])
    vi.mocked(adminRlsRulesApi.delete).mockResolvedValue(undefined as never)
    renderPage()
    await waitFor(() => expect(screen.getByText("region == 'North'")).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: 'More actions for rule Analyst on Orders' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Delete rule' }))

    const dlg = await screen.findByRole('alertdialog')
    fireEvent.click(within(dlg).getByRole('button', { name: /Delete/i }))

    await waitFor(() => expect(adminRlsRulesApi.delete).toHaveBeenCalledWith(1))
  })
})
