import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import ChecksPanel, { ChecksBlockedDialog } from './ChecksPanel'

vi.mock('../../services/api', () => ({
  datasetsApi: { checks: vi.fn(), addCheck: vi.fn(), updateCheck: vi.fn(), deleteCheck: vi.fn(),
                 tryChecks: vi.fn(), refreshRuns: vi.fn(), list: vi.fn() },
}))
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))

import { datasetsApi } from '../../services/api'

const unique = { id: 1, kind: 'unique' as const, column: 'id', params: {}, severity: 'block' as const,
                 enabled: true, created_at: null }

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(datasetsApi.checks).mockResolvedValue([unique])
  vi.mocked(datasetsApi.refreshRuns).mockResolvedValue([
    { id: 9, trigger: 'schedule', status: 'blocked', started_at: '2026-10-03T07:00:00Z', rows: null,
      duration_ms: 40, error: 'Not published: Unique id: 3 repeated id values', error_code: 'checks_blocked',
      checks: [{ id: 1, kind: 'unique', column: 'id', severity: 'block', passed: false, detail: '3 repeated id values, e.g. [7]' }] },
  ])
})

describe('ChecksPanel (pipeline phase 3)', () => {
  it('lists checks in words and shows what past refreshes found', async () => {
    render(<ChecksPanel datasetId={5} columns={['id', 'status']} canEdit />)
    expect(await screen.findByText('id values are unique')).toBeInTheDocument()
    const history = await screen.findByTestId('checks-history')
    expect(history).toHaveTextContent('blocked')
    expect(history).toHaveTextContent('3 repeated id values')
  })

  it('adds a check from the form', async () => {
    vi.mocked(datasetsApi.addCheck).mockResolvedValue({ ...unique, id: 2, kind: 'accepted_values', column: 'status' })
    render(<ChecksPanel datasetId={5} columns={['id', 'status']} canEdit />)
    await screen.findByText('id values are unique')
    // The form opens from "+ Rule" (redesign 3c).
    fireEvent.click(screen.getByRole('button', { name: 'Add a check' }))
    fireEvent.change(screen.getByLabelText('Check'), { target: { value: 'accepted_values' } })
    fireEvent.change(screen.getByLabelText(/^Column/), { target: { value: 'status' } })
    fireEvent.change(screen.getByLabelText(/Allowed values/), { target: { value: 'open, closed' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    await waitFor(() => expect(datasetsApi.addCheck).toHaveBeenCalledWith(5, {
      kind: 'accepted_values', severity: 'block', column: 'status', params: { values: ['open', 'closed'] } }))
  })

  it('tries the checks on the current data', async () => {
    vi.mocked(datasetsApi.tryChecks).mockResolvedValue({ rows: 120, results: [
      { id: 1, kind: 'unique', column: 'id', severity: 'block', passed: false, detail: '2 repeated id values' }] })
    render(<ChecksPanel datasetId={5} columns={['id']} canEdit />)
    fireEvent.click(await screen.findByRole('button', { name: 'Try the checks on the current data' }))
    expect(await screen.findByText('Checked 120 rows')).toBeInTheDocument()
    expect(screen.getByTestId('checks-table')).toHaveTextContent('2 repeated id values')
  })

  it('is read-only for someone who cannot edit', async () => {
    render(<ChecksPanel datasetId={5} columns={['id']} canEdit={false} />)
    await screen.findByText('id values are unique')
    expect(screen.queryByText('Add a check')).toBeNull()
    expect(datasetsApi.refreshRuns).not.toHaveBeenCalled()
  })
})

describe('ChecksBlockedDialog', () => {
  it('names the failed check and offers both choices', () => {
    const onPublish = vi.fn()
    render(<ChecksBlockedDialog detail="x" onKeep={vi.fn()} onPublish={onPublish}
      checks={[{ kind: 'row_drop', column: null, severity: 'block', passed: false, detail: 'rows fell 70%' },
               { kind: 'unique', column: 'id', severity: 'block', passed: true, detail: null }]} />)
    expect(screen.getByRole('alertdialog')).toHaveTextContent('rows fell 70%')
    fireEvent.click(screen.getByRole('button', { name: 'Publish anyway' }))
    expect(onPublish).toHaveBeenCalled()
  })
})

describe('the Quality rules card (redesign 3c)', () => {
  it('shows each rule with its state, its result after Run now, and a Warn/Block pill', async () => {
    vi.mocked(datasetsApi.tryChecks).mockResolvedValue({ rows: 120, results: [
      { id: 1, kind: 'unique', column: 'id', severity: 'block', passed: false, detail: '2 repeated id values' }] })
    render(<ChecksPanel datasetId={5} columns={['id']} canEdit />)
    await screen.findByText('id values are unique')
    expect(screen.getByTestId('checks-table')).toHaveTextContent('Not run yet')
    expect((screen.getByLabelText('If it fails') as HTMLSelectElement).value).toBe('block')
    fireEvent.click(screen.getByRole('button', { name: 'Try the checks on the current data' }))
    await waitFor(() => expect(screen.getByTestId('checks-table')).toHaveTextContent('2 repeated id values'))
  })

  it('the add form closes again once the rule is saved', async () => {
    vi.mocked(datasetsApi.addCheck).mockResolvedValue({ ...unique, id: 2 })
    render(<ChecksPanel datasetId={5} columns={['id', 'status']} canEdit />)
    await screen.findByText('id values are unique')
    fireEvent.click(screen.getByRole('button', { name: 'Add a check' }))
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Add' })).toBeNull())
  })
})


describe('ChecksPanel: closing the pipeline gaps (2026-10-10)', () => {
  it('adds a "values exist in another dataset" check', async () => {
    vi.mocked(datasetsApi.list).mockResolvedValue([
      { id: 5, name: 'This one', columns: [] }, { id: 8, name: 'Customers', columns: [{ name: 'id' }, { name: 'email' }] },
    ] as never)
    vi.mocked(datasetsApi.addCheck).mockResolvedValue({ ...unique, id: 3 })
    render(<ChecksPanel datasetId={5} columns={['customer_id']} canEdit />)
    await screen.findByText('id values are unique')
    fireEvent.click(screen.getByRole('button', { name: 'Add a check' }))
    fireEvent.change(screen.getByLabelText('Check'), { target: { value: 'references' } })
    fireEvent.change(screen.getByLabelText(/^Column/), { target: { value: 'customer_id' } })
    await waitFor(() => expect(screen.getByRole('option', { name: 'Customers' })).toBeInTheDocument())
    expect(screen.queryByRole('option', { name: 'This one' })).toBeNull()        // not itself
    fireEvent.change(screen.getByLabelText('Must exist in dataset'), { target: { value: '8' } })
    fireEvent.change(screen.getByLabelText('Its column'), { target: { value: 'id' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    await waitFor(() => expect(datasetsApi.addCheck).toHaveBeenCalledWith(5, expect.objectContaining({
      kind: 'references', column: 'customer_id', params: { dataset_id: 8, column: 'id' } })))
  })

  it('a "columns stay the same" check can block', async () => {
    vi.mocked(datasetsApi.addCheck).mockResolvedValue({ ...unique, id: 4 })
    render(<ChecksPanel datasetId={5} columns={['id']} canEdit />)
    await screen.findByText('id values are unique')
    fireEvent.click(screen.getByRole('button', { name: 'Add a check' }))
    fireEvent.change(screen.getByLabelText('Check'), { target: { value: 'same_columns' } })
    fireEvent.click(screen.getByLabelText('A new column is fine'))
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    await waitFor(() => expect(datasetsApi.addCheck).toHaveBeenCalledWith(5, expect.objectContaining({
      kind: 'same_columns', column: null, severity: 'block', params: { allow_new: false } })))
  })

  it('run history shows speed and a run far slower than usual', async () => {
    vi.mocked(datasetsApi.refreshRuns).mockResolvedValue([
      { id: 10, trigger: 'schedule', status: 'ok', started_at: '2026-10-10T07:00:00Z', rows: 90000, duration_ms: 45000,
        error: null, error_code: null, checks: [],
        metrics: { rows_per_sec: 2000, slow: { median_ms: 12000, times: 3.8 } } },
    ])
    render(<ChecksPanel datasetId={5} columns={['id']} canEdit />)
    const history = await screen.findByTestId('checks-history')
    expect(history).toHaveTextContent('45 s')
    expect(history).toHaveTextContent('2,000 rows/s')
    expect(history).toHaveTextContent('3.8× slower than usual')
  })
})
