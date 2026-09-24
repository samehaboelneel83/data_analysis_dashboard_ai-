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
    render(<ColumnMeaningPanel dataset={DATASET} canEdit />)
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
