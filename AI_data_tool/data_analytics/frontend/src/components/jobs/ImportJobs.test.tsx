import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { dataSourcesApi, jobsApi } from '../../services/api'
import type { DataSource, Job } from '../../services/api'
import { SchemaBrowser } from '../../pages/connections/SchemaBrowser'
import ImportJobRow from './ImportJobRow'
import ImportQueue from './ImportQueue'
import { newIdempotencyKey } from './idempotency'

const navigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useNavigate: () => navigate }
})

vi.mock('../../services/api', async () => ({
  ...(await vi.importActual<Record<string, unknown>>('../../services/api')),
  dataSourcesApi: { schema: vi.fn(), preview: vi.fn(), import: vi.fn(), queueImport: vi.fn() },
  jobsApi: { list: vi.fn(), get: vi.fn(), cancel: vi.fn(), retry: vi.fn() },
}))

const DS: DataSource = { id: 1, name: 'Live DB', type: 'postgresql', config: {}, created_at: '2026-01-01' }

function job(over: Partial<Job> = {}): Job {
  return {
    id: 77, kind: 'dataset.import', state: 'queued', subject: 'Live DB · sales → sales',
    progress: { stage: 'queued' }, result: null, error: null, error_code: null,
    attempt: 0, max_attempts: 3, cancel_requested: false, retry_of: null, created_by: 1,
    created_at: null, started_at: null, finished_at: null, updated_at: null, ...over,
  }
}

async function openAndImport() {
  vi.mocked(dataSourcesApi.schema).mockResolvedValue({ tables: [{ name: 'sales', kind: 'table' }] })
  vi.mocked(dataSourcesApi.preview).mockResolvedValue({ columns: ['region'], rows: [['east']], total: 1 })
  render(<MemoryRouter><SchemaBrowser ds={DS} onClose={() => {}} /></MemoryRouter>)
  fireEvent.click(await screen.findByText('sales'))
  await screen.findByText(/1 rows preview/)
  fireEvent.click(screen.getByText(/Import as Dataset/))
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('SchemaBrowser follows its import job', () => {
  it('lands on the dataset when the job succeeds', async () => {
    vi.mocked(dataSourcesApi.queueImport).mockResolvedValue(job())
    vi.mocked(jobsApi.get).mockResolvedValue(job({
      state: 'succeeded', progress: { stage: 'done' },
      result: { dataset_id: 12, dataset_name: 'sales', row_count: 3400, col_count: 2, replaced: false } }))
    await openAndImport()
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/datasets/12?new=1'))
  })

  it('shows the reason when the job fails, and Retry follows the new job', async () => {
    vi.mocked(dataSourcesApi.queueImport).mockResolvedValue(job())
    vi.mocked(jobsApi.get).mockResolvedValueOnce(job({
      state: 'failed', error: 'no such table: sales', error_code: 'refused' }))
    vi.mocked(jobsApi.retry).mockResolvedValue(job({ id: 78, retry_of: 77, state: 'queued' }))
    await openAndImport()

    expect(await screen.findByRole('alert')).toHaveTextContent('no such table: sales')
    vi.mocked(jobsApi.get).mockResolvedValue(job({ id: 78, retry_of: 77, state: 'running',
      progress: { stage: 'querying' } }))
    fireEvent.click(screen.getByText('Retry'))
    await waitFor(() => expect(jobsApi.retry).toHaveBeenCalledWith(77))
    expect(await screen.findByText('Reading from the source')).toBeInTheDocument()
    await waitFor(() => expect(jobsApi.get).toHaveBeenCalledWith(78))
    expect(navigate).not.toHaveBeenCalled()
  })

  it('reuses its idempotency key when the same import is sent again', async () => {
    vi.mocked(dataSourcesApi.queueImport).mockRejectedValueOnce(new Error('network'))
      .mockResolvedValue(job())
    vi.mocked(jobsApi.get).mockResolvedValue(job())
    await openAndImport()
    await waitFor(() => expect(dataSourcesApi.queueImport).toHaveBeenCalledTimes(1))
    // The request failed in transit: the same click again must carry the same
    // key, so if the first one did reach the server no second job is made.
    fireEvent.click(await screen.findByText(/Import as Dataset/))
    await waitFor(() => expect(dataSourcesApi.queueImport).toHaveBeenCalledTimes(2))
    const [first, second] = vi.mocked(dataSourcesApi.queueImport).mock.calls
    expect(second[2]).toBe(first[2])
  })

  it('still connects DirectQuery at once, without a job', async () => {
    vi.mocked(dataSourcesApi.schema).mockResolvedValue({ tables: [{ name: 'sales', kind: 'table' }] })
    vi.mocked(dataSourcesApi.preview).mockResolvedValue({ columns: ['region'], rows: [['east']], total: 1 })
    vi.mocked(dataSourcesApi.import).mockResolvedValue({ id: 5, name: 'sales', row_count: 0, col_count: 1, mode: 'directquery' })
    render(<MemoryRouter><SchemaBrowser ds={DS} onClose={() => {}} /></MemoryRouter>)
    fireEvent.click(await screen.findByText('sales'))
    await screen.findByText(/1 rows preview/)
    fireEvent.click(screen.getByText('DirectQuery'))
    fireEvent.click(screen.getByText(/Create DirectQuery Dataset/))
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/datasets/5?new=1'))
    expect(dataSourcesApi.queueImport).not.toHaveBeenCalled()
  })
})

describe('ImportJobRow', () => {
  const renderRow = (j: Job, onChange = vi.fn()) =>
    render(<MemoryRouter><ImportJobRow job={j} onChange={onChange} /></MemoryRouter>)

  it('offers Cancel while running and reports the stage', async () => {
    const onChange = vi.fn()
    vi.mocked(jobsApi.cancel).mockResolvedValue(job({ state: 'running', cancel_requested: true }))
    renderRow(job({ state: 'running', progress: { stage: 'writing', rows: 3400 } }), onChange)
    expect(screen.getByText('Importing')).toBeInTheDocument()
    expect(screen.getByText(/Writing 3,400 rows/)).toBeInTheDocument()
    fireEvent.click(screen.getByText('Cancel import'))
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ cancel_requested: true })))
  })

  it('says Stopping once a cancel is requested, and offers no second Cancel', () => {
    renderRow(job({ state: 'running', cancel_requested: true }))
    expect(screen.getByText('Stopping…')).toBeInTheDocument()
    expect(screen.queryByText('Cancel import')).not.toBeInTheDocument()
  })

  it('says a job was resumed after a restart', () => {
    renderRow(job({ state: 'running', attempt: 2, progress: { stage: 'querying', resumed: true } }))
    expect(screen.getByText('Resumed after a server restart')).toBeInTheDocument()
    expect(screen.getByText('Attempt 2 of 3')).toBeInTheDocument()
  })

  it('opens the dataset a finished job made, and says when it beat a cancel', () => {
    renderRow(job({ state: 'succeeded', cancel_requested: true,
      result: { dataset_id: 9, row_count: 10 } }))
    expect(screen.getByText('Finished before it could be cancelled')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Open dataset'))
    expect(navigate).toHaveBeenCalledWith('/datasets/9')
  })

  it('offers Retry for a cancelled job', () => {
    renderRow(job({ state: 'cancelled' }))
    expect(screen.getByText('Retry')).toBeInTheDocument()
    expect(screen.queryByText('Cancel import')).not.toBeInTheDocument()
  })
})

describe('ImportQueue', () => {
  it('renders nothing when there are no imports', async () => {
    vi.mocked(jobsApi.list).mockResolvedValue([])
    const { container } = render(<MemoryRouter><ImportQueue /></MemoryRouter>)
    await waitFor(() => expect(jobsApi.list).toHaveBeenCalledWith({ kind: 'dataset.import', limit: 8 }))
    expect(container).toBeEmptyDOMElement()
  })

  it('lists recent imports with their state', async () => {
    vi.mocked(jobsApi.list).mockResolvedValue([
      job({ id: 2, state: 'failed', subject: 'Live DB · orders → Orders', error: 'timeout' }),
      job({ id: 1, state: 'succeeded', subject: 'Live DB · sales → Sales', result: { dataset_id: 3, row_count: 5 } }),
    ])
    render(<MemoryRouter><ImportQueue /></MemoryRouter>)
    expect(await screen.findByRole('heading', { name: 'Imports' })).toBeInTheDocument()
    expect(screen.getByText('Live DB · orders → Orders')).toBeInTheDocument()
    expect(screen.getByText('Failed')).toBeInTheDocument()
    expect(screen.getByText('Done')).toBeInTheDocument()
  })
})

describe('newIdempotencyKey', () => {
  it('works without crypto.randomUUID (plain http on a LAN address)', () => {
    const orig = globalThis.crypto.randomUUID
    Object.defineProperty(globalThis.crypto, 'randomUUID', { value: undefined, configurable: true })
    try {
      const a = newIdempotencyKey()
      const b = newIdempotencyKey()
      expect(a).toMatch(/^k-/)
      expect(a).not.toBe(b)
    } finally {
      Object.defineProperty(globalThis.crypto, 'randomUUID', { value: orig, configurable: true })
    }
  })
})
