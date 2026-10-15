import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import UnderstandStep from './UnderstandStep'
import { setupApi, metadataApi, type SetupSummary } from '../../services/api'

vi.mock('../../services/api', async (orig) => {
  const real = await orig<typeof import('../../services/api')>()
  return { ...real, setupApi: { ...real.setupApi, summary: vi.fn(), refreshSummary: vi.fn() },
    metadataApi: { ...real.metadataApi, sync: vi.fn(), latestSync: vi.fn(), cancelSync: vi.fn() } }
})

/** QA6 B1: a connection nothing is reading (never synced) must not leave
 *  step 1 waiting forever. */
const neverRead = (over: Partial<SetupSummary> = {}) => ({
  status: 'syncing', source: { id: 1, name: 'Demo — Live SQLite', type: 'sqlite', allow_ai: true },
  sync: { status: 'pending', last_synced_at: null }, can_edit: true, language: 'en',
  ...over,
}) as unknown as SetupSummary

const open = () => render(<MemoryRouter><UnderstandStep sourceId={1} onNext={() => {}} /></MemoryRouter>)

beforeEach(() => vi.clearAllMocks())

describe('guided setup step 1 on a connection that was never read (QA6 B1)', () => {
  it('says so, and an admin can read it now', async () => {
    vi.mocked(setupApi.summary).mockResolvedValue(neverRead())
    vi.mocked(metadataApi.sync).mockResolvedValue({ sync_run_id: 1, status: 'running', stages: [] } as never)
    open()
    expect(await screen.findByText(/has not read this database yet/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Back to Home' })).toHaveAttribute('href', '/')
    fireEvent.click(screen.getByRole('button', { name: /Read the database now/ }))
    await waitFor(() => expect(metadataApi.sync).toHaveBeenCalledWith(1))
    await waitFor(() => expect(setupApi.summary).toHaveBeenCalledTimes(2))
  })

  it('someone who is not an admin is told who can, and still has a way back', async () => {
    vi.mocked(setupApi.summary).mockResolvedValue(neverRead({ can_edit: false }))
    open()
    expect(await screen.findByText(/ask an admin/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Read the database now/ })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Back to Home' })).toBeInTheDocument()
  })

  it('a sync that is really running still just says it is reading', async () => {
    vi.mocked(setupApi.summary).mockResolvedValue(neverRead({ sync: { status: 'running', last_synced_at: null } }))
    open()
    expect(await screen.findByText(/still reading this database/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Read the database now/ })).not.toBeInTheDocument()
  })

  it('a failed read is said, never just swallowed (B-03)', async () => {
    vi.mocked(setupApi.summary).mockResolvedValue(neverRead({ latest_run: null }))
    vi.mocked(metadataApi.sync).mockRejectedValue({ response: { status: 500, data: { detail: 'The metadata cache is locked' } } })
    open()
    fireEvent.click(await screen.findByRole('button', { name: /Read the database now/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('The metadata cache is locked')
    expect(setupApi.summary).toHaveBeenCalledTimes(1)
  })

  it('a read that is already running is named, with the review link (B-03)', async () => {
    vi.mocked(setupApi.summary).mockResolvedValue(neverRead({ latest_run: null }))
    vi.mocked(metadataApi.sync).mockRejectedValue({ response: { status: 409, data: { detail: 'A sync is already running' } } })
    vi.mocked(metadataApi.latestSync).mockResolvedValue({ id: 9, status: 'running', trigger: 'manual',
      stages: [{ name: 'discover', status: 'ok' }, { name: 'sample', status: 'ok' }], error: null,
      started_at: '2026-10-15T09:30:00', finished_at: null } as never)
    open()
    fireEvent.click(await screen.findByRole('button', { name: /Read the database now/ }))
    expect(await screen.findByText(/A read is already running/)).toHaveTextContent(/step 3 of 8/)
    expect(screen.getAllByRole('link', { name: 'Open the review page' })[0]).toHaveAttribute('href', '/connections/1/review')
  })

  it('a running read in the summary is shown as progress, never "nothing is reading it" (B-03)', async () => {
    vi.mocked(setupApi.summary).mockResolvedValue(neverRead({ latest_run: {
      id: 9, status: 'running', started_at: '2026-10-15T09:30:00', stages_done: 4, stages_total: 8,
      current: 'describe', error: null } }))
    open()
    expect(await screen.findByText(/step 5 of 8/)).toBeInTheDocument()
    expect(screen.queryByText(/nothing is reading it now/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Read the database now/ })).not.toBeInTheDocument()
    vi.mocked(metadataApi.cancelSync).mockResolvedValue({} as never)
    fireEvent.click(screen.getByRole('button', { name: 'Cancel sync' }))
    await waitFor(() => expect(metadataApi.cancelSync).toHaveBeenCalledWith(1, 9))
  })

  it('a failed read shows its error and offers to read again (B-03)', async () => {
    vi.mocked(setupApi.summary).mockResolvedValue(neverRead({ status: 'failed', sync: { status: 'failed', last_synced_at: null },
      latest_run: { id: 9, status: 'failed', started_at: '2026-10-15T09:30:00', stages_done: 1, stages_total: 8,
                    current: null, error: 'could not connect to server' } }))
    open()
    expect(await screen.findByText(/could not connect to server/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Read the database now/ })).toBeInTheDocument()
  })
})
