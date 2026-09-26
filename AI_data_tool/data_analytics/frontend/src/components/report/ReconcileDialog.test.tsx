import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import ReconcileDialog from './ReconcileDialog'
import { migrationApi, widgetDataApi } from '../../services/api'

vi.mock('../../services/api', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  widgetDataApi: { query: vi.fn(), reconcile: vi.fn() },
  migrationApi: { list: vi.fn() },
}))

const BODY = { config: { dimension: 'region', measure: 'sales' }, widget_type: 'bar', report_id: 3, parameters: {} }
const RESULT = {
  mapping: { keys: [['name', 'Region']], values: [['value', 'Sales']] },
  columns: { widget: ['name', 'value'], file: ['Region', 'Sales', 'Units'] },
  counts: { match: 2, mismatch: 1, missing_in_widget: 1, missing_in_file: 0 },
  rows: [
    { key: { Region: 'South' }, status: 'mismatch', values: [{ column: 'Sales', expected: '299', actual: 300, difference: 1, ok: false }] },
    { key: { Region: 'West' }, status: 'missing_in_widget', values: [] },
    { key: { Region: 'North' }, status: 'match', values: [{ column: 'Sales', expected: '150.3', actual: 150.25, difference: -0.05, ok: true }] },
  ],
  totals: [{ column: 'Sales', expected: 456.3, actual: 457.75, difference: 1.45 }],
  duplicate_keys: { widget: 0, file: 0 }, reconciled: false, file: 'sas.csv',
}

const pick = (name = 'sas.csv') => {
  const input = screen.getByLabelText('Export file (CSV or Excel)')
  fireEvent.change(input, { target: { files: [new File(['Region,Sales\n'], name, { type: 'text/csv' })] } })
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(migrationApi.list).mockResolvedValue({ items: [], summary: {}, can_manage: false } as never)
})

describe('reconcile a widget with the old report (E17)', () => {
  it('compares the chosen file and shows what differs, by how much, and the totals', async () => {
    vi.mocked(widgetDataApi.reconcile).mockResolvedValue(RESULT as never)
    render(<ReconcileDialog title="Sales by region" datasetId={7} body={BODY} onClose={() => {}} />)
    pick()
    await waitFor(() => expect(widgetDataApi.reconcile).toHaveBeenCalledWith(7, BODY, expect.any(File), undefined))
    expect(await screen.findByTestId('rec-summary')).toHaveTextContent('2 agree, 1 differ, 1 only in the file, 0 only in the widget.')
    const rows = within(screen.getByTestId('rec-rows'))
    expect(rows.getByText('South')).toBeInTheDocument()
    expect(rows.getByText('Differs')).toBeInTheDocument()
    expect(rows.getByText('Only in the file')).toBeInTheDocument()
    // The row that agrees is not listed among the differences.
    expect(rows.queryByText('North')).toBeNull()
    expect(within(screen.getByTestId('rec-totals')).getByText('1.45')).toBeInTheDocument()
  })

  it('compares again with the columns the owner pairs', async () => {
    vi.mocked(widgetDataApi.reconcile).mockResolvedValue(RESULT as never)
    render(<ReconcileDialog title="Sales by region" datasetId={7} body={BODY} onClose={() => {}} />)
    pick()
    const valueFile = await screen.findByRole('combobox', { name: 'Values compared 1: file column' })
    fireEvent.change(valueFile, { target: { value: 'Units' } })
    fireEvent.click(screen.getByRole('button', { name: 'Compare again' }))
    await waitFor(() => expect(widgetDataApi.reconcile).toHaveBeenLastCalledWith(7, BODY, expect.any(File),
      { keys: [['name', 'Region']], values: [['value', 'Units']] }))
  })

  it('says so when every row agrees', async () => {
    vi.mocked(widgetDataApi.reconcile).mockResolvedValue({ ...RESULT, reconciled: true,
      counts: { match: 3, mismatch: 0, missing_in_widget: 0, missing_in_file: 0 },
      rows: RESULT.rows.slice(2) } as never)
    render(<ReconcileDialog title="Sales by region" datasetId={7} body={BODY} onClose={() => {}} />)
    pick()
    expect(await screen.findByTestId('rec-summary')).toHaveTextContent('Every row agrees: 3 rows, and the totals.')
    expect(screen.queryByTestId('rec-rows')).toBeNull()
  })

  it('shows the server\'s reason when a file cannot be compared', async () => {
    vi.mocked(widgetDataApi.reconcile).mockRejectedValue({ response: { data: { detail: 'Reconcile with a CSV or Excel file' } } })
    render(<ReconcileDialog title="Sales by region" datasetId={7} body={BODY} onClose={() => {}} />)
    pick('report.pdf')
    expect(await screen.findByRole('alert')).toHaveTextContent('Reconcile with a CSV or Excel file')
  })

  it('keeps the result on the migration item this report replaces (E17)', async () => {
    const item = (over = {}) => ({ id: 41, name: 'Sales pack (SAS)', report: { id: 3, name: 'Sales', can_open: true },
      can_edit: true, ...over })
    vi.mocked(migrationApi.list).mockResolvedValue({ items: [item(),
      item({ id: 42, name: 'Another report', report: { id: 9, name: 'X', can_open: true } }),
      item({ id: 43, name: 'Not mine', can_edit: false })], summary: {}, can_manage: false } as never)
    vi.mocked(widgetDataApi.reconcile).mockResolvedValue({ ...RESULT, recorded_on: 41 } as never)
    render(<ReconcileDialog title="Sales by region" datasetId={7} body={BODY} widgetKey="w12" onClose={() => {}} />)
    const select = await screen.findByRole('combobox', { name: 'Keep the result on the migration item' })
    // Only this report's items that the reader may record on; the one there is, chosen.
    expect(within(select).getAllByRole('option').map(o => o.textContent)).toEqual(["Don’t keep it", 'Sales pack (SAS)'])
    expect(select).toHaveValue('41')
    pick()
    await waitFor(() => expect(widgetDataApi.reconcile).toHaveBeenCalledWith(7, BODY, expect.any(File), undefined,
      { itemId: 41, widgetKey: 'w12', widgetTitle: 'Sales by region' }))
    expect(await screen.findByTestId('rec-recorded')).toHaveTextContent('Kept on “Sales pack (SAS)” in Migration.')
  })

  it('compares without keeping when the reader chooses not to', async () => {
    vi.mocked(migrationApi.list).mockResolvedValue({ items: [{ id: 41, name: 'Sales pack', report: { id: 3 }, can_edit: true }],
      summary: {}, can_manage: false } as never)
    vi.mocked(widgetDataApi.reconcile).mockResolvedValue(RESULT as never)
    render(<ReconcileDialog title="Sales by region" datasetId={7} body={BODY} onClose={() => {}} />)
    fireEvent.change(await screen.findByRole('combobox', { name: 'Keep the result on the migration item' }), { target: { value: '' } })
    pick()
    await waitFor(() => expect(widgetDataApi.reconcile).toHaveBeenCalledWith(7, BODY, expect.any(File), undefined))
    expect(screen.queryByTestId('rec-recorded')).toBeNull()
  })
})
