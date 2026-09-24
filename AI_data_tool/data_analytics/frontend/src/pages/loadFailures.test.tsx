import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ConfirmProvider } from '../components/ui/ConfirmDialog'
import { PromptProvider } from '../components/ui/PromptDialog'
import Lineage from './Lineage'
import Reports from './Reports'
import Dashboard from './Dashboard'
import ApiKeys from './admin/ApiKeys'
import { lineageApi, reportsApi, datasetsApi, apiKeysApi } from '../services/api'

/**
 * "We could not ask" is not "there is nothing".
 *
 * These pages used to conflate the two. Lineage caught a failed fetch and set
 * an EMPTY GRAPH, so a backend outage was rendered as a confident claim that
 * the org owns no data assets. Reports had no catch at all, so a 500 cleared
 * `loading` and fell straight through to "No reports yet" — which invites the
 * user to recreate work that already exists.
 *
 * Every test below asserts BOTH halves: that the error is shown, and that the
 * empty-state copy is ABSENT. The second assertion is the one that bites — a
 * test checking only for an error message still passes if the empty state
 * renders beside it, which is exactly the bug.
 */

vi.mock('../services/api', () => ({
  pinsApi: { create: vi.fn().mockResolvedValue({ id: 1, widget_id: 1, already_pinned: false }), list: vi.fn().mockResolvedValue([]), remove: vi.fn().mockResolvedValue(undefined) },
  lineageApi: { graph: vi.fn() },
  reportsApi: { list: vi.fn(), create: vi.fn(), delete: vi.fn() },
  datasetsApi: { list: vi.fn() },
  apiKeysApi: { list: vi.fn(), create: vi.fn(), revoke: vi.fn() },
  demoApi: { seed: vi.fn() },
}))

// Reports uses useConfirm for its delete action, so it needs the provider
// even though these tests never open a dialog.
const wrap = (ui: React.ReactElement) =>
  render(<MemoryRouter><ConfirmProvider><PromptProvider>{ui}</PromptProvider></ConfirmProvider></MemoryRouter>)

beforeEach(() => vi.clearAllMocks())

describe('Lineage', () => {
  it('says the graph could not be loaded rather than showing an empty one', async () => {
    vi.mocked(lineageApi.graph).mockRejectedValue(new Error('boom'))
    wrap(<Lineage />)

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load/i)
    // THE assertion. "No connections — uploads only" is a factual claim about
    // the user's estate, and it must not appear when we never got an answer.
    expect(screen.queryByText(/uploads only/i)).toBeNull()
  })

  it('still shows the genuine empty state when the server says empty', async () => {
    // A correction that suppressed the real empty state would be its own bug.
    vi.mocked(lineageApi.graph).mockResolvedValue(
      { sources: [], datasets: [], reports: [] } as never)
    wrap(<Lineage />)

    expect(await screen.findByText(/uploads only/i)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('offers a retry', async () => {
    vi.mocked(lineageApi.graph).mockRejectedValue(new Error('boom'))
    wrap(<Lineage />)
    expect(await screen.findByRole('button', { name: /try again/i })).toBeInTheDocument()
  })
})

describe('Reports', () => {
  it('does not invite the user to create a duplicate when the server is down', async () => {
    vi.mocked(reportsApi.list).mockRejectedValue(new Error('boom'))
    vi.mocked(datasetsApi.list).mockResolvedValue([] as never)
    wrap(<Reports />)

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load/i)
    expect(screen.queryByText(/no dashboards yet/i)).toBeNull()
    expect(screen.queryByRole('button', { name: /create your first report/i })).toBeNull()
  })

  it('still shows the empty state when there genuinely are none', async () => {
    vi.mocked(reportsApi.list).mockResolvedValue([] as never)
    vi.mocked(datasetsApi.list).mockResolvedValue([] as never)
    wrap(<Reports />)

    expect(await screen.findByText(/no dashboards yet/i)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('surfaces the server’s own message when it sends one', async () => {
    // More specific than anything generic we could write.
    vi.mocked(reportsApi.list).mockRejectedValue(
      { response: { data: { detail: 'Workspace is being migrated' } } })
    vi.mocked(datasetsApi.list).mockResolvedValue([] as never)
    wrap(<Reports />)

    expect(await screen.findByText(/being migrated/i)).toBeInTheDocument()
  })
})

describe('Dashboard', () => {
  // The landing page, and the worst instance: it had no `.catch` AT ALL, so a
  // failed load produced an unhandled rejection and rendered "No datasets yet"
  // to a user whose workspace is full -- inviting them to re-upload data they
  // already own.
  it('says the datasets could not be loaded rather than claiming there are none', async () => {
    vi.mocked(datasetsApi.list).mockRejectedValue(new Error('boom'))
    wrap(<Dashboard />)

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load/i)
    expect(screen.queryByText(/no datasets yet/i)).toBeNull()
  })

  it('still shows the genuine empty state when the server says empty', async () => {
    vi.mocked(datasetsApi.list).mockResolvedValue([])
    wrap(<Dashboard />)
    expect(await screen.findByText(/no datasets yet/i)).toBeInTheDocument()
  })
})

describe('ApiKeys', () => {
  it('says the keys could not be loaded rather than claiming there are none', async () => {
    // Security-relevant: "No API keys yet." tells an admin their keys are gone
    // when they are merely unreadable right now.
    vi.mocked(apiKeysApi.list).mockRejectedValue(new Error('boom'))
    wrap(<ApiKeys />)

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load/i)
    expect(screen.queryByText(/no api keys yet/i)).toBeNull()
  })

  it('still shows the genuine empty state when the server says empty', async () => {
    vi.mocked(apiKeysApi.list).mockResolvedValue([])
    wrap(<ApiKeys />)
    expect(await screen.findByText(/no api keys yet/i)).toBeInTheDocument()
  })
})
