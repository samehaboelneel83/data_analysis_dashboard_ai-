import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import ColumnMeaningPanel from './ColumnMeaningPanel'
import { datasetsApi, type Dataset } from '../../services/api'

/**
 * Every AI path in this product reads column descriptions now — the dashboard
 * designer's prompt carries them, the agent renders them, the insights engine
 * writes its findings in their words. Until this panel there was nowhere in the
 * product to write one FOR A DATASET: they could only be inferred by a sync, or
 * typed on the source review page by an admin who knew it existed.
 *
 * The behaviour worth pinning is the surprising one: a description on a column
 * that came from a connected table is written to the SOURCE, so it is written
 * once and read by every dataset built from that table. A person typing into a
 * box labelled with THIS dataset's name has to be told that.
 */

const toastSuccess = vi.fn()
const toastError = vi.fn()
vi.mock('react-hot-toast', () => ({
  default: { success: (...a: unknown[]) => toastSuccess(...a),
             error: (...a: unknown[]) => toastError(...a) },
}))

const DATASET = {
  id: 4, name: 'Orders', mode: 'import',
  columns: [
    { id: 1, name: 'status', dtype: 'numeric' },
    { id: 2, name: 'total', dtype: 'numeric' },
  ],
  column_descriptions: { status: 'Where the order is in fulfilment.' },
  value_labels: { status: { '1': 'new', '2': 'paid' } },
  grain: 'One row per order placed.',
  business_name: 'Order',
} as unknown as Dataset

beforeEach(() => {
  vi.restoreAllMocks()
  toastSuccess.mockReset()
  toastError.mockReset()
})

// The spies live on a shared module object and vitest reuses the module registry
// across files in a worker; without this the last test's spies stay installed
// for every file that runs afterwards.
afterEach(() => { vi.restoreAllMocks() })

describe('ColumnMeaningPanel', () => {
  it('shows what the catalogue already knows, including what coded values mean', () => {
    render(<ColumnMeaningPanel dataset={DATASET} canEdit />)
    expect(screen.getByText('Where the order is in fulfilment.')).toBeInTheDocument()
    expect(screen.getByText('1 = new, 2 = paid')).toBeInTheDocument()
    expect(screen.getByText(/One row per order placed/)).toBeInTheDocument()
  })

  it('says plainly when a column has nothing written about it', () => {
    // An editor is invited to write one (redesign 3c); a reader is told there is none.
    const { unmount } = render(<ColumnMeaningPanel dataset={DATASET} canEdit />)
    expect(screen.getByRole('button', { name: 'Describe total' })).toHaveTextContent('Add a description…')
    unmount()
    render(<ColumnMeaningPanel dataset={DATASET} canEdit={false} />)
    expect(screen.getByText('Not described yet')).toBeInTheDocument()
  })

  it('saves a description and reloads so the resolved value comes back', async () => {
    const save = vi.spyOn(datasetsApi, 'setColumnDescription').mockResolvedValue(
      { written_to: 'dataset', shared: false, object: 'Orders', column: 'total' })
    const onSaved = vi.fn()
    render(<ColumnMeaningPanel dataset={DATASET} canEdit onSaved={onSaved} />)

    fireEvent.click(screen.getByLabelText('Describe total'))
    fireEvent.change(screen.getByPlaceholderText(/What is this column for/),
                     { target: { value: 'Order total, excluding tax.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(save).toHaveBeenCalledWith(
      4, 'total', 'Order total, excluding tax.'))
    await waitFor(() => expect(onSaved).toHaveBeenCalled())
  })

  it('tells the person when their sentence travelled further than this dataset', async () => {
    /* The surprising half. Writing to the source is deliberate -- copying the
       text onto each dataset is what lets two datasets from one table disagree
       about what `status` means -- but it must not be a silent surprise. */
    vi.spyOn(datasetsApi, 'setColumnDescription').mockResolvedValue(
      { written_to: 'source', shared: true, object: 'orders', column: 'status' })
    render(<ColumnMeaningPanel dataset={DATASET} canEdit />)

    fireEvent.click(screen.getByLabelText('Describe status'))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(toastSuccess).toHaveBeenCalledWith(
      expect.stringContaining('every dataset built from it')))
  })

  it('a reader sees the meanings and is offered no edit they cannot make', () => {
    render(<ColumnMeaningPanel dataset={DATASET} canEdit={false} />)
    expect(screen.getByText('Where the order is in fulfilment.')).toBeInTheDocument()
    expect(screen.queryByLabelText('Describe status')).toBeNull()
  })

  it('a refused save is reported, not swallowed', async () => {
    vi.spyOn(datasetsApi, 'setColumnDescription')
      .mockRejectedValue({ response: { data: { detail: 'You may only view this dataset' } } })
    render(<ColumnMeaningPanel dataset={DATASET} canEdit />)
    fireEvent.click(screen.getByLabelText('Describe total'))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(toastError).toHaveBeenCalledWith(
      'You may only view this dataset'))
  })
})

describe('the Columns tab (redesign 3c)', () => {
  const WIDE = {
    ...DATASET,
    columns: [
      { id: 1, name: 'status', dtype: 'numeric', missing_pct: 0 },
      { id: 2, name: 'total', dtype: 'numeric', missing_pct: 2 },
      { id: 3, name: 'region', dtype: 'categorical', missing_pct: 0 },
      { id: 4, name: 'ordered_at', dtype: 'datetime', missing_pct: 0 },
      { id: 5, name: 'notes', dtype: 'categorical', missing_pct: 40 },
    ],
    column_meta: { notes: { hidden: true }, total: { role: 'measure', aggregation: 'avg' } },
  } as unknown as Dataset
  const ANALYSIS = {
    numeric: { columns: { total: { min: 1, p5: 2, p25: 5, median: 9, p75: 14, p95: 30, max: 40 } } },
    categorical: { columns: { region: { n_unique: 4, top_values: [{ value: 'West', count: 10, pct: 40 }] } } },
  }

  it('shows one row per visible column with its distribution, empty share, summary and use', () => {
    render(<ColumnMeaningPanel dataset={WIDE} canEdit analysis={ANALYSIS} />)
    const row = screen.getByText('total').closest('tr')!
    expect(row).toHaveTextContent('2%')
    expect(row).toHaveTextContent('1 – 40 · median 9')
    expect(row).toHaveTextContent('Measure · average')
    expect(screen.getByText('region').closest('tr')).toHaveTextContent('Dimension')
    expect(screen.getByText('ordered_at').closest('tr')).toHaveTextContent('Time')
    expect(screen.queryByText('notes')).toBeNull()
    expect(screen.getByText('1 of 5 described')).toBeInTheDocument()
  })

  it('filters by type and by name', () => {
    render(<ColumnMeaningPanel dataset={WIDE} canEdit />)
    fireEvent.click(screen.getByRole('radio', { name: /^Date/ }))
    expect(screen.getByText('ordered_at')).toBeInTheDocument()
    expect(screen.queryByText('region')).toBeNull()
    fireEvent.click(screen.getByRole('radio', { name: /^All/ }))
    fireEvent.change(screen.getByLabelText('Find a column'), { target: { value: 'reg' } })
    expect(screen.getAllByRole('row')).toHaveLength(2)
  })

  it('lists hidden columns apart, behind their own button', () => {
    render(<ColumnMeaningPanel dataset={WIDE} canEdit />)
    fireEvent.click(screen.getByRole('button', { name: 'Hidden columns (1)' }))
    expect(screen.getByText('notes')).toBeInTheDocument()
    expect(screen.queryByText('region')).toBeNull()
  })

  it('opens the role, summary, outcome, suggestion and hidden settings from the Use as pill', () => {
    render(<ColumnMeaningPanel dataset={WIDE} canEdit />)
    fireEvent.click(screen.getByRole('button', { name: 'How total is used' }))
    for (const label of ['Role for total', 'Summary for total', 'Explain total', 'Suggest total', 'Hide total']) {
      expect(screen.getByLabelText(label)).toBeInTheDocument()
    }
  })

  it('offers a reader no settings', () => {
    render(<ColumnMeaningPanel dataset={WIDE} canEdit={false} />)
    expect(screen.queryByRole('button', { name: 'How total is used' })).toBeNull()
  })
})
