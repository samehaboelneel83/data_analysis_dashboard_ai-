import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import ChecksPanel, { ChecksBlockedDialog } from './ChecksPanel'

vi.mock('../../services/api', () => ({
  datasetsApi: { checks: vi.fn(), addCheck: vi.fn(), updateCheck: vi.fn(), deleteCheck: vi.fn(),
                 tryChecks: vi.fn(), refreshRuns: vi.fn() },
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
    fireEvent.change(screen.getAllByRole('combobox')[1], { target: { value: 'accepted_values' } })
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
