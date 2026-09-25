import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import PrepStepsPanel, { describeStep } from './PrepStepsPanel'
import { datasetsApi, prepApi } from '../../services/api'

vi.mock('../../services/api', () => ({
  prepApi: { get: vi.fn(), set: vi.fn(), preview: vi.fn() },
  datasetsApi: { list: vi.fn(), get: vi.fn() },
}))

const previewResult = {
  before: { rows: 100, columns: ['a'] },
  after: { rows: 90, columns: ['a'] },
  steps: [],
  sample: { columns: ['a'], rows: [] },
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(prepApi.get).mockResolvedValue([])
  vi.mocked(prepApi.set).mockResolvedValue([])
  vi.mocked(prepApi.preview).mockResolvedValue(previewResult)
})

describe('describeStep', () => {
  it('renders each step as a human-readable sentence', () => {
    expect(describeStep({ kind: 'trim' })).toMatch(/Trim whitespace/)
    expect(describeStep({ kind: 'fill_nulls', column: 'amount', method: 'mean' })).toBe('Fill missing amount with mean')
    expect(describeStep({ kind: 'rename', column: 'a', to: 'b' })).toBe('Rename a → b')
    expect(describeStep({ kind: 'aggregate', group_by: ['region'], aggregations: [{ agg: 'sum', column: 'amount' }] }))
      .toBe('Group by region — sum(amount)')
  })
})

describe('PrepStepsPanel', () => {
  it('lists the saved pipeline in order', async () => {
    vi.mocked(prepApi.get).mockResolvedValue([
      { kind: 'trim' }, { kind: 'drop_duplicates' },
    ])
    render(<PrepStepsPanel datasetId={1} columns={['region']} />)
    await waitFor(() => expect(screen.getByText(/Trim whitespace/)).toBeInTheDocument())
    expect(screen.getByText(/Remove duplicates/)).toBeInTheDocument()
  })

  it('adds a step, saves it, and reports the row effect', async () => {
    const onPipelineChange = vi.fn()
    render(<PrepStepsPanel datasetId={1} columns={['region', 'amount']} onPipelineChange={onPipelineChange} />)
    fireEvent.click(await screen.findByRole('button', { name: '+ Add step' }))
    fireEvent.change(screen.getByLabelText('Step'), { target: { value: 'fill_nulls' } })
    fireEvent.change(screen.getByLabelText('Column'), { target: { value: 'amount' } })
    fireEvent.change(screen.getByLabelText('Fill with'), { target: { value: 'mean' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    await waitFor(() => expect(prepApi.set).toHaveBeenCalledWith(1,
      [{ kind: 'fill_nulls', column: 'amount', method: 'mean' }]))
    await waitFor(() => expect(screen.getByTestId('prep-effect')).toHaveTextContent('rows'))
    expect(onPipelineChange).toHaveBeenCalled()
  })

  it('surfaces the server validation message when a step is refused', async () => {
    vi.mocked(prepApi.set).mockRejectedValue({ response: { data: { detail: "step 1: column 'x' does not exist at this point in the pipeline" } } })
    render(<PrepStepsPanel datasetId={1} columns={['region']} />)
    fireEvent.click(await screen.findByRole('button', { name: '+ Add step' }))
    fireEvent.change(screen.getByLabelText('Step'), { target: { value: 'filter_rows' } })
    fireEvent.change(screen.getByLabelText('Expression'), { target: { value: '`x` > 0' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent("does not exist"))
  })

  it('deletes and reorders by saving the mutated pipeline', async () => {
    vi.mocked(prepApi.get).mockResolvedValue([{ kind: 'trim' }, { kind: 'drop_duplicates' }])
    render(<PrepStepsPanel datasetId={1} columns={[]} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Move step 2 up' }))
    await waitFor(() => expect(prepApi.set).toHaveBeenLastCalledWith(1,
      [{ kind: 'drop_duplicates' }, { kind: 'trim' }]))
    fireEvent.click(screen.getByRole('button', { name: 'Delete step 1' }))
    await waitFor(() => expect(prepApi.set).toHaveBeenLastCalledWith(1, [{ kind: 'trim' }]))
  })

  it('builds a join step from the dataset and key pickers', async () => {
    vi.mocked(datasetsApi.list).mockResolvedValue([
      { id: 5, name: 'Customers', mode: 'import', columns: [] } as never,
    ])
    vi.mocked(datasetsApi.get).mockResolvedValue(
      { id: 5, name: 'Customers', mode: 'import',
        columns: [{ id: 1, name: 'id', dtype: 'categorical', missing_pct: 0, stats: {} }] } as never)
    render(<PrepStepsPanel datasetId={1} columns={['cust', 'amount']} />)
    fireEvent.click(await screen.findByRole('button', { name: '+ Add step' }))
    fireEvent.change(screen.getByLabelText('Step'), { target: { value: 'join' } })
    await waitFor(() => expect(screen.getByLabelText('Dataset to join')).toBeInTheDocument())
    fireEvent.change(screen.getByLabelText('Dataset to join'), { target: { value: '5' } })
    fireEvent.change(screen.getByLabelText('Join type'), { target: { value: 'left' } })
    fireEvent.change(screen.getByLabelText("This dataset’s key"), { target: { value: 'cust' } })
    await waitFor(() => expect(screen.getByLabelText("Joined dataset's key")).not.toBeDisabled())
    fireEvent.change(screen.getByLabelText("Joined dataset's key"), { target: { value: 'id' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    await waitFor(() => expect(prepApi.set).toHaveBeenCalledWith(1,
      [{ kind: 'join', dataset_id: 5, how: 'left', left_on: 'cust', right_on: 'id' }]))
  })

  it('refuses to add an incomplete step locally, without a network call', async () => {
    render(<PrepStepsPanel datasetId={1} columns={['region']} />)
    fireEvent.click(await screen.findByRole('button', { name: '+ Add step' }))
    fireEvent.change(screen.getByLabelText('Step'), { target: { value: 'rename' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(/required fields/))
    expect(prepApi.set).not.toHaveBeenCalled()
  })
})

describe('a cell correction in the step list', () => {
  it('reads as a sentence, not as a raw kind', () => {
    // This editor never writes an edit_cells step -- the data grid does -- but
    // it renders the same saved list, and falling through to the default would
    // print "edit_cells" where every other step reads as English.
    expect(describeStep({ kind: 'edit_cells', key_column: 'order_id',
      column: 'region', edits: [{ key: 'A-1', value: 'North' }] } as never))
      .toBe('Correct 1 cell in region, matched on order_id')
  })

  it('counts several corrections', () => {
    expect(describeStep({ kind: 'edit_cells', key_column: 'order_id',
      column: 'region', edits: [{ key: 'A-1', value: 'N' }, { key: 'A-2', value: 'S' }] } as never))
      .toContain('2 cells')
  })
})
