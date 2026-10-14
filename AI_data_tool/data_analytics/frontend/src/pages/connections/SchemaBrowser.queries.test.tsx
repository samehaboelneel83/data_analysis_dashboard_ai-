import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { renderWithProviders } from '../../test/renderWithProviders'
import { SchemaBrowser } from './SchemaBrowser'
import { dataSourcesApi } from '../../services/api'
import type { DataSource } from '../../services/api'

vi.mock('react-hot-toast', () => ({ default: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }))
vi.mock('../../services/api', () => ({
  dataSourcesApi: { schema: vi.fn(), preview: vi.fn(), import: vi.fn(), queueImport: vi.fn(),
                    queries: vi.fn(), saveQuery: vi.fn(), deleteQuery: vi.fn(), downloadCsv: vi.fn() },
  queryBuilderApi: { columns: vi.fn().mockResolvedValue([]) },
  jobsApi: { get: vi.fn() },
}))

const render = (ui: React.ReactElement) => renderWithProviders(<MemoryRouter>{ui}</MemoryRouter>)
const ds = { id: 4, name: 'HR', type: 'postgres', config: {} } as unknown as DataSource
const Q = 'SELECT dept_no, count(*) FROM dept_emp GROUP BY 1'

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(dataSourcesApi.schema).mockResolvedValue({ tables: [{ name: 'dept_emp', kind: 'table' }, { name: 'departments', kind: 'table' }] } as never)
  vi.mocked(dataSourcesApi.queries).mockResolvedValue({
    saved: [{ id: 1, name: 'Workforce', sql: Q, created_at: null }],
    history: [{ id: 2, name: null, sql: 'SELECT 1', created_at: null }] })
  vi.mocked(dataSourcesApi.preview).mockResolvedValue({ columns: ['dept', 'n'], rows: [['b', 2], ['a', 10], ['c', 1]], total: 3 })
  vi.mocked(dataSourcesApi.saveQuery).mockResolvedValue({ id: 3, name: 'Mine', sql: 'SELECT 2', created_at: null })
  vi.mocked(dataSourcesApi.downloadCsv).mockResolvedValue({ rows: 3, truncated: false })
})

describe('Browse saved queries, history, sorting and CSV (4.2–4.4)', () => {
  it('reopens a saved query and a past run from the lists', async () => {
    render(<SchemaBrowser ds={ds} onClose={() => {}} />)
    fireEvent.change(await screen.findByLabelText('Saved queries'), { target: { value: '1' } })
    expect(screen.getByLabelText('Custom Query')).toHaveValue(Q)
    fireEvent.change(screen.getByLabelText('Recent runs'), { target: { value: '2' } })
    expect(screen.getByLabelText('Custom Query')).toHaveValue('SELECT 1')
  })

  it('saves the query under a name', async () => {
    render(<SchemaBrowser ds={ds} onClose={() => {}} />)
    fireEvent.change(await screen.findByLabelText('Custom Query'), { target: { value: 'SELECT 2' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save query…' }))
    fireEvent.change(screen.getByLabelText('Query name'), { target: { value: 'Mine' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(dataSourcesApi.saveQuery).toHaveBeenCalledWith(4, 'Mine', 'SELECT 2'))
  })

  it('sorts the preview by a clicked column and downloads CSV', async () => {
    render(<SchemaBrowser ds={ds} onClose={() => {}} />)
    fireEvent.change(await screen.findByLabelText('Custom Query'), { target: { value: Q } })
    fireEvent.click(screen.getByRole('button', { name: /Run Preview/ }))
    const region = await screen.findByRole('region', { name: 'Preview' })
    await within(region).findByText('a')
    fireEvent.click(within(region).getByRole('button', { name: 'n' }))
    const firsts = within(region).getAllByRole('row').slice(1).map(r => r.textContent)
    expect(firsts).toEqual(['c1', 'b2', 'a10'])
    fireEvent.click(screen.getByRole('button', { name: /Download CSV/ }))
    await waitFor(() => expect(dataSourcesApi.downloadCsv).toHaveBeenCalledWith(4, undefined, Q))
    expect(screen.getByTestId('mode-explainer')).toHaveTextContent(/no Models, Data quality or Segment/)
  })

  it('Escape in a typed query leaves the editor instead of closing the dialog', async () => {
    const onClose = vi.fn()
    render(<SchemaBrowser ds={ds} onClose={onClose} />)
    const box = await screen.findByLabelText('Custom Query')
    fireEvent.change(box, { target: { value: 'SELECT 1 AS n' } })
    fireEvent.keyDown(box, { key: 'Escape' })
    expect(onClose).not.toHaveBeenCalled()
    expect(screen.getByLabelText('Custom Query')).toHaveValue('SELECT 1 AS n')
  })
})
