import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import Dataflows from './Dataflows'
import { ConfirmProvider } from '../components/ui/ConfirmDialog'
import { dataflowsApi, datasetsApi } from '../services/api'

vi.mock('../services/api', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  dataflowsApi: { list: vi.fn(), get: vi.fn(), create: vi.fn(), update: vi.fn(), run: vi.fn(), remove: vi.fn() },
  datasetsApi: { list: vi.fn(), get: vi.fn() },
  prepApi: { get: vi.fn().mockResolvedValue([]), preview: vi.fn().mockResolvedValue({
    before: { rows: 3, columns: ['region'] }, after: { rows: 3, columns: ['region'] }, steps: [],
    sample: { columns: ['region'], rows: [] } }) },
  relationshipsApi: { list: vi.fn().mockResolvedValue([]) },
}))
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))

const flow = (over = {}) => ({
  id: 5, name: 'Nightly rollup', description: null, source_dataset_id: 1, join_dataset_ids: [],
  steps: [{ kind: 'trim', columns: ['region'] }], refresh_interval_minutes: 1440, created_by: 1,
  created_at: '2026-09-01T00:00:00Z', last_run_at: new Date(Date.now() - 2 * 3600_000).toISOString(),
  last_run_status: 'ok', last_run_rows: 1200, last_run_error: null,
  outputs: [{ id: 9, name: 'Sales rollup', row_count: 1200 }], your_capability: 'data', ...over,
})

function Where() { const l = useLocation(); return <div data-testid="where">{l.pathname + l.search}</div> }

const renderAt = (url = '/dataflows') => render(
  <ConfirmProvider>
    <MemoryRouter initialEntries={[url]}>
      <Routes><Route path="/dataflows" element={<><Dataflows /><Where /></>} /></Routes>
    </MemoryRouter>
  </ConfirmProvider>)

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(datasetsApi.list).mockResolvedValue([
    { id: 1, name: 'Sales', mode: 'import' }, { id: 2, name: 'Live orders', mode: 'directquery' },
  ] as never)
  vi.mocked(datasetsApi.get).mockResolvedValue({ id: 1, name: 'Sales', columns: [{ id: 1, name: 'region', dtype: 'categorical' }] } as never)
  vi.mocked(dataflowsApi.list).mockResolvedValue([flow()] as never)
})

describe('Dataflows (E12)', () => {
  it('lists each dataflow with its source, schedule, last run and outputs', async () => {
    renderAt()
    const row = await screen.findByTestId('flow-5')
    expect(row).toHaveTextContent('Nightly rollup')
    expect(row).toHaveTextContent('1 steps')
    expect(within(row).getByRole('link', { name: 'Sales' })).toHaveAttribute('href', '/datasets/1')
    expect(row).toHaveTextContent('Every day')
    expect(row).toHaveTextContent('Succeeded, 1,200 rows, 2 hours ago')
    expect(within(row).getByRole('link', { name: 'Sales rollup' })).toHaveAttribute('href', '/datasets/9')
  })

  it('creates a dataflow from an import dataset and opens it', async () => {
    vi.mocked(dataflowsApi.create).mockResolvedValue(flow({ id: 6, name: 'Clean sales', steps: [], outputs: [], last_run_at: null }) as never)
    renderAt()
    await screen.findByTestId('flow-5')
    const source = screen.getByLabelText('Source dataset') as HTMLSelectElement
    // 4.6: a live dataset feeds dataflows too, marked as live.
    expect([...source.options].map(o => o.textContent)).toContain('Live orders · Live')
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Clean sales' } })
    fireEvent.change(source, { target: { value: '1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))
    await waitFor(() => expect(dataflowsApi.create).toHaveBeenCalledWith({ name: 'Clean sales', source_dataset_id: 1, steps: [] }))
    expect(await screen.findByRole('heading', { name: 'Clean sales' })).toBeInTheDocument()
    expect(screen.getByTestId('where')).toHaveTextContent('/dataflows?flow=6')
  })

  it('creates a monthly snapshot of a live dataset, run daily (4.6)', async () => {
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 2, name: 'Live orders', columns: [
      { id: 1, name: 'dept', dtype: 'categorical' }, { id: 2, name: 'from_date', dtype: 'datetime' },
      { id: 3, name: 'to_date', dtype: 'datetime' }] } as never)
    vi.mocked(dataflowsApi.create).mockResolvedValue(flow({ id: 7, name: 'Headcount', steps: [], outputs: [], last_run_at: null,
      source_dataset_id: 2, snapshot: { every: 'month', group_by: ['dept'], measure: null, agg: 'count', as: 'headcount',
        backfill: { from_column: 'from_date', to_column: 'to_date', start: '2025-01-01' } } }) as never)
    renderAt()
    await screen.findByTestId('flow-5')
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Headcount' } })
    fireEvent.change(screen.getByLabelText('Source dataset'), { target: { value: '2' } })
    fireEvent.click(screen.getByRole('radio', { name: 'Monthly snapshot' }))
    const form = await screen.findByTestId('snapshot-form')
    await waitFor(() => expect(within(form).getByLabelText('Split by')).toHaveTextContent('dept'))
    fireEvent.change(within(form).getByLabelText('Split by'), { target: { value: 'dept' } })
    fireEvent.click(within(form).getByLabelText('Rebuild past months from start and end dates'))
    expect(within(form).getByLabelText('Start date column')).toHaveValue('from_date')
    expect(within(form).getByLabelText('End date column')).toHaveValue('to_date')
    fireEvent.change(within(form).getByLabelText('From month'), { target: { value: '2025-01-01' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))
    await waitFor(() => expect(dataflowsApi.create).toHaveBeenCalledWith({
      name: 'Headcount', source_dataset_id: 2, steps: [], refresh_interval_minutes: 1440,
      snapshot: { every: 'month', group_by: ['dept'], measure: null, agg: 'count', as: 'headcount',
        backfill: { from_column: 'from_date', to_column: 'to_date', start: '2025-01-01' } } }))
    expect(await screen.findByTestId('snapshot-summary')).toHaveTextContent(/split by dept/)
  })

  it('opened on one: saves its recipe, its schedule, and runs it', async () => {
    vi.mocked(dataflowsApi.update).mockImplementation(async (_id, body) => flow(body) as never)
    vi.mocked(dataflowsApi.run).mockResolvedValue({ rows: 1300, outputs: [] } as never)
    renderAt('/dataflows?flow=5')
    expect(await screen.findByRole('heading', { name: 'Nightly rollup' })).toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: 'Save recipe' }))
    await waitFor(() => expect(dataflowsApi.update).toHaveBeenCalledWith(5, { steps: [{ kind: 'trim', columns: ['region'] }] }))
    fireEvent.change(screen.getByRole('combobox', { name: 'Refresh' }), { target: { value: '60' } })
    await waitFor(() => expect(dataflowsApi.update).toHaveBeenCalledWith(5, { refresh_interval_minutes: 60 }))
    fireEvent.click(screen.getByRole('button', { name: 'Refresh outputs now' }))
    await waitFor(() => expect(dataflowsApi.run).toHaveBeenCalledWith(5, undefined))
    fireEvent.change(screen.getByLabelText('New dataset name'), { target: { value: 'Sales v2' } })
    fireEvent.click(screen.getByRole('button', { name: 'Run into a new dataset' }))
    await waitFor(() => expect(dataflowsApi.run).toHaveBeenCalledWith(5, 'Sales v2'))
  })

  it('turning the schedule off sends 0, which the API reads as off', async () => {
    vi.mocked(dataflowsApi.update).mockImplementation(async (_id, body) => flow({ refresh_interval_minutes: null, ...body }) as never)
    renderAt('/dataflows?flow=5')
    fireEvent.change(await screen.findByRole('combobox', { name: 'Refresh' }), { target: { value: '0' } })
    // Off also stops following the source (pipeline phase 4).
    await waitFor(() => expect(dataflowsApi.update).toHaveBeenCalledWith(5, { refresh_interval_minutes: 0, run_after_source: false }))
  })

  it('can run after its source refreshes instead of on a timer (pipeline phase 4)', async () => {
    vi.mocked(dataflowsApi.update).mockImplementation(async (_id, body) =>
      flow({ refresh_interval_minutes: null, run_after_source: true, ...body }) as never)
    renderAt('/dataflows?flow=5')
    fireEvent.change(await screen.findByRole('combobox', { name: 'Refresh' }), { target: { value: '-1' } })
    await waitFor(() => expect(dataflowsApi.update).toHaveBeenCalledWith(5, { run_after_source: true }))
    expect(await screen.findAllByText('After its source refreshes')).not.toHaveLength(0)
  })

  it('a dataflow with no outputs cannot be refreshed, only run into a new dataset', async () => {
    vi.mocked(dataflowsApi.list).mockResolvedValue([flow({ outputs: [], last_run_at: null })] as never)
    renderAt('/dataflows?flow=5')
    expect(await screen.findByRole('button', { name: 'Refresh outputs now' })).toBeDisabled()
    expect(screen.getByTestId('flow-5')).toHaveTextContent('Not run yet')
  })

  it('a failed run says why', async () => {
    vi.mocked(dataflowsApi.list).mockResolvedValue([flow({ last_run_status: 'failed', last_run_error: 'source dataset or creator is gone' })] as never)
    renderAt()
    expect(await screen.findByText(/Failed .*: source dataset or creator is gone/)).toBeInTheDocument()
  })

  it('someone with view only sees the recipe and no controls', async () => {
    vi.mocked(dataflowsApi.list).mockResolvedValue([flow({ your_capability: 'view' })] as never)
    renderAt('/dataflows?flow=5')
    expect(await screen.findByRole('note')).toHaveTextContent('needs the edit capability')
    expect(screen.queryByRole('button', { name: 'Save recipe' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Run into a new dataset' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Delete dataflow' })).toBeNull()
    expect(screen.getByRole('combobox', { name: 'Refresh' })).toBeDisabled()
  })

  it('deletes after confirming, leaving its outputs', async () => {
    vi.mocked(dataflowsApi.remove).mockResolvedValue(undefined as never)
    renderAt('/dataflows?flow=5')
    fireEvent.click(await screen.findByRole('button', { name: 'Delete dataflow' }))
    const dialog = await screen.findByRole('alertdialog')
    expect(dialog).toHaveTextContent('Its output datasets stay')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(dataflowsApi.remove).toHaveBeenCalledWith(5))
    await waitFor(() => expect(screen.queryByTestId('flow-5')).toBeNull())
  })
})
