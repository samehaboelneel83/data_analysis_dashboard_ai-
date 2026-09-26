import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import Migration from './Migration'
import { ConfirmProvider } from '../components/ui/ConfirmDialog'
import { adminUsersApi, migrationApi, reportsApi } from '../services/api'

vi.mock('../services/api', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  migrationApi: { list: vi.fn(), featureMap: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn(),
                  import: vi.fn(), scan: vi.fn(), signOff: vi.fn(), withdrawSignOff: vi.fn() },
  reportsApi: { list: vi.fn() },
  adminUsersApi: { list: vi.fn() },
}))
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))

const TABULATE = { key: 'proc_tabulate', label: 'PROC TABULATE', target: 'Pivot table with subtotals and grand totals',
  fit: 'native', note: '', count: 2 }
const XCMD = { key: 'os_command', label: 'X / CALL SYSTEM / %SYSEXEC', target: 'No equivalent', fit: 'manual',
  note: 'Datalytics does not run operating-system commands.', count: 1 }
const CLEAN = { match: 3, mismatch: 0, missing_in_widget: 0, missing_in_file: 0 }

const item = (over = {}) => ({
  id: 1, name: 'Sales pack', kind: 'report', source_system: 'SAS', source_path: '/Shared/Sales',
  decision: 'migrate', notes: null, owner: { id: 7, email: 'owner@example.com' },
  report: { id: 3, name: 'Sales', can_open: true },
  features: { features: [TABULATE, XCMD], unknown_procs: [], libnames: ['DW'], lines: 40, file: 'sales.sas' },
  fit: 'manual',
  reconciles: [{ widget_key: 'w12', title: 'Sales by region', file: 'export.csv', at: new Date().toISOString(),
                 by_email: 'owner@example.com', counts: CLEAN, report_id: 3, revision: 4 }],
  sign_off: null, report_changed_since_sign_off: false, status: 'reconciled', can_edit: true, can_sign_off: true,
  ...over,
})
const SUMMARY = { to_map: 1, mapped: 0, differences: 0, reconciled: 1, signed_off: 0, retired: 0 }

const renderAt = (url = '/migration') => render(
  <ConfirmProvider>
    <MemoryRouter initialEntries={[url]}>
      <Routes><Route path="/migration" element={<Migration />} /></Routes>
    </MemoryRouter>
  </ConfirmProvider>)

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(migrationApi.list).mockResolvedValue({ items: [item(),
    item({ id: 2, name: 'Old extract', kind: 'job', owner: null, report: null, features: null, fit: null,
           reconciles: [], status: 'to_map', can_edit: false, can_sign_off: false })],
  summary: SUMMARY, can_manage: false } as never)
  vi.mocked(reportsApi.list).mockResolvedValue([{ id: 3, name: 'Sales' }, { id: 4, name: 'Sales v2' }] as never)
  vi.mocked(adminUsersApi.list).mockResolvedValue([
    { id: 7, email: 'owner@example.com', is_active: true }, { id: 8, email: 'gone@example.com', is_active: false },
  ] as never)
})

describe('Migration (E17)', () => {
  it('lists each item with its owner, replacement, fit, evidence and status', async () => {
    renderAt()
    const row = await screen.findByTestId('mig-1')
    expect(row).toHaveTextContent('Sales pack')
    expect(row).toHaveTextContent('Report · /Shared/Sales')
    expect(row).toHaveTextContent('owner@example.com')
    expect(within(row).getByRole('link', { name: 'Sales' })).toHaveAttribute('href', '/reports/3')
    expect(row).toHaveTextContent('By hand')
    expect(row).toHaveTextContent('1 compared, all agree')
    expect(row).toHaveTextContent('Reconciled')
    const other = screen.getByTestId('mig-2')
    expect(other).toHaveTextContent('No owner')
    expect(other).toHaveTextContent('Not mapped yet')
    expect(other).toHaveTextContent('Not compared')
    // Members do not see the admin tools.
    expect(screen.queryByText('Add to the inventory')).toBeNull()
  })

  it('filters by status', async () => {
    renderAt()
    await screen.findByTestId('mig-1')
    fireEvent.click(screen.getByRole('button', { name: 'Not mapped · 1' }))
    expect(screen.queryByTestId('mig-1')).toBeNull()
    expect(screen.getByTestId('mig-2')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'All · 2' }))
    expect(screen.getByTestId('mig-1')).toBeInTheDocument()
  })

  it('a report the reader cannot open is not named', async () => {
    vi.mocked(migrationApi.list).mockResolvedValue({ items: [item({ report: { id: 3, name: null, can_open: false } })],
      summary: SUMMARY, can_manage: false } as never)
    renderAt()
    const row = await screen.findByTestId('mig-1')
    expect(row).toHaveTextContent('A report you cannot open')
    expect(within(row).queryByRole('link')).toBeNull()
  })

  it('an admin adds an item with an owner and imports files, and sees what the import skipped', async () => {
    vi.mocked(migrationApi.list).mockResolvedValue({ items: [], summary: SUMMARY, can_manage: true } as never)
    vi.mocked(migrationApi.create).mockResolvedValue(item() as never)
    vi.mocked(migrationApi.import).mockResolvedValue({ created: 2, updated: 1, warnings: ['inv.csv row 3: no active user x@y'] } as never)
    renderAt()
    await screen.findByText('Add to the inventory')
    fireEvent.change(screen.getByRole('textbox', { name: 'Name' }), { target: { value: 'Churn pack' } })
    fireEvent.change(screen.getByRole('combobox', { name: 'Kind' }), { target: { value: 'stored_process' } })
    const owner = screen.getByRole('combobox', { name: 'Owner' })
    await waitFor(() => expect(within(owner).getAllByRole('option')).toHaveLength(2))   // inactive users are not offered
    fireEvent.change(owner, { target: { value: '7' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    await waitFor(() => expect(migrationApi.create).toHaveBeenCalledWith(
      { name: 'Churn pack', kind: 'stored_process', owner_id: 7 }))

    const input = screen.getByLabelText('Import an inventory (.csv) or SAS programs (.sas)')
    const files = [new File(['Name\nA\n'], 'inv.csv'), new File(['proc sql; quit;'], 'a.sas')]
    fireEvent.change(input, { target: { files } })
    await waitFor(() => expect(migrationApi.import).toHaveBeenCalledWith(files))
    expect(await screen.findByRole('status', { name: 'Import notes' })).toHaveTextContent('no active user x@y')
  })

  it('the owner links a report, reads the scan and the comparisons, and signs off', async () => {
    vi.mocked(migrationApi.update).mockResolvedValue(item({ report: { id: 4, name: 'Sales v2', can_open: true },
      reconciles: [], status: 'mapped' }) as never)
    vi.mocked(migrationApi.signOff).mockResolvedValue(item({ status: 'signed_off',
      sign_off: { by_email: 'owner@example.com', at: new Date().toISOString(), basis: 'reconciled', note: null } }) as never)
    renderAt('/migration?item=1')
    const panel = await screen.findByRole('region', { name: 'Sales pack' })
    expect(within(panel).getByText('PROC TABULATE')).toBeInTheDocument()
    expect(within(panel).getByText('Libraries it opens: DW')).toBeInTheDocument()
    expect(within(panel).getByText('Sales by region')).toBeInTheDocument()
    expect(panel).toHaveTextContent('3 agree, 0 differ, 0 only in the old export, 0 only in the widget')

    fireEvent.click(within(panel).getByRole('button', { name: 'Sign off' }))
    await waitFor(() => expect(migrationApi.signOff).toHaveBeenCalledWith(1, { note: '', accept_differences: false }))
    expect(await within(panel).findByText(/Signed off by owner@example.com/)).toBeInTheDocument()
    expect(within(panel).getByText('Every comparison agreed')).toBeInTheDocument()
    expect(within(panel).getByRole('button', { name: 'Withdraw sign-off' })).toBeInTheDocument()

    fireEvent.change(within(panel).getByRole('combobox', { name: 'Replaced by' }), { target: { value: '4' } })
    fireEvent.click(within(panel).getByRole('button', { name: 'Link' }))
    await waitFor(() => expect(migrationApi.update).toHaveBeenCalledWith(1, { report_id: 4 }))
  })

  it('accepting differences is offered only when there are some', async () => {
    vi.mocked(migrationApi.list).mockResolvedValue({ items: [item({ status: 'differences',
      reconciles: [{ ...item().reconciles[0], counts: { ...CLEAN, mismatch: 1 } }] })],
    summary: SUMMARY, can_manage: false } as never)
    vi.mocked(migrationApi.signOff).mockResolvedValue(item() as never)
    renderAt('/migration?item=1')
    const panel = await screen.findByRole('region', { name: 'Sales pack' })
    expect(await screen.findByTestId('mig-1')).toHaveTextContent('1 of 1 differ')
    fireEvent.change(within(panel).getByRole('textbox', { name: /^Note \(/ }), { target: { value: 'rounding' } })
    fireEvent.click(within(panel).getByRole('checkbox', { name: 'Accept the differences' }))
    fireEvent.click(within(panel).getByRole('button', { name: 'Sign off' }))
    await waitFor(() => expect(migrationApi.signOff).toHaveBeenCalledWith(1, { note: 'rounding', accept_differences: true }))
  })

  it('says when the report changed after the sign-off', async () => {
    vi.mocked(migrationApi.list).mockResolvedValue({ items: [item({ status: 'signed_off', report_changed_since_sign_off: true,
      sign_off: { by_email: 'owner@example.com', at: new Date().toISOString(), basis: 'accepted', note: 'rounding' } })],
    summary: SUMMARY, can_manage: false } as never)
    renderAt('/migration?item=1')
    expect(await screen.findByTestId('mig-1')).toHaveTextContent('Report changed since')
    const panel = screen.getByRole('region', { name: 'Sales pack' })
    expect(panel).toHaveTextContent('Differences accepted — rounding')
    expect(within(panel).getByRole('note')).toHaveTextContent('The report has changed since it was signed off')
  })

  it('someone else\'s item is read only, and says who signs it off', async () => {
    vi.mocked(migrationApi.list).mockResolvedValue({ items: [item({ can_edit: false, can_sign_off: false })],
      summary: SUMMARY, can_manage: false } as never)
    renderAt('/migration?item=1')
    const panel = await screen.findByRole('region', { name: 'Sales pack' })
    expect(within(panel).getByText('You can view this item. Its owner or an admin changes it.')).toBeInTheDocument()
    expect(within(panel).getByText('owner@example.com signs this off.')).toBeInTheDocument()
    expect(within(panel).queryByRole('button', { name: 'Sign off' })).toBeNull()
    expect(within(panel).queryByRole('button', { name: 'Link' })).toBeNull()
  })

  it('loads the feature map when it is opened', async () => {
    vi.mocked(migrationApi.featureMap).mockResolvedValue([{ ...TABULATE, count: undefined }] as never)
    renderAt()
    await screen.findByTestId('mig-1')
    const details = screen.getByText('How SAS maps to Datalytics').closest('details')!
    details.open = true
    fireEvent(details, new Event('toggle'))
    expect(await within(details).findByText('Pivot table with subtotals and grand totals')).toBeInTheDocument()
    expect(migrationApi.featureMap).toHaveBeenCalledTimes(1)
  })
})
