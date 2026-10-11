import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import UnderstandStep from './UnderstandStep'
import { setupApi, metadataApi, type SetupSummary } from '../../services/api'

vi.mock('../../services/api', async (orig) => {
  const real = await orig<typeof import('../../services/api')>()
  return { ...real, setupApi: { ...real.setupApi, summary: vi.fn(), refreshSummary: vi.fn() },
    metadataApi: { ...real.metadataApi, sync: vi.fn() } }
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
})
