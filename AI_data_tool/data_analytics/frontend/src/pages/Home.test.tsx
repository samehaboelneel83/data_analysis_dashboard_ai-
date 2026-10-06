import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'
import Home from './Home'
import {
  agentApi, dataSourcesApi, datasetsApi, lineageApi, monitoringApi, reportsApi,
} from '../services/api'
import { AuthContext } from '../contexts/AuthContext'
import { useAiOffline } from './ask/useAiOffline'
import { localDigits } from '../lib/arabicFormats'
import { renderWithProviders } from '../test/renderWithProviders'
import { axeViolations } from '../test/axe'

/**
 * Home is a landing page built from data the app already serves (redesign
 * 7a). The claims worth pinning are about HONESTY: real entities in real
 * order, an outage never rendered as an empty workspace, one failing section
 * never blanking the rest, admin-only data never requested for anyone else,
 * and a question box that never pretends to work while the model is down.
 */

vi.mock('../services/api', () => ({
  reportsApi: { list: vi.fn(), recent: vi.fn(), update: vi.fn(), delete: vi.fn(), downloadPdf: vi.fn(), create: vi.fn() },
  datasetsApi: { list: vi.fn(), queueRefresh: vi.fn() },
  lineageApi: { graph: vi.fn() },
  dataSourcesApi: { list: vi.fn() },
  agentApi: { listConversations: vi.fn() },
  monitoringApi: { refreshRuns: vi.fn(), activity: vi.fn() },
  authzApi: { decisions: vi.fn(async () => []) },
  shareLinksApi: { list: vi.fn(async () => []), create: vi.fn(), revoke: vi.fn() },
  embedConfigsApi: { list: vi.fn(async () => []), create: vi.fn(), setEnabled: vi.fn(), delete: vi.fn() },
}))
vi.mock('./ask/useAiOffline', () => ({ useAiOffline: vi.fn(() => ({ offline: false, checkedAt: null })) }))

const member = { id: 9, email: 'sara@example.com', is_active: true, organization: { id: 1, name: 'Org' },
  role: { id: 3, name: 'Analyst', is_org_admin: false } }
const admin = { ...member, id: 1, email: 'admin@example.com', role: { id: 2, name: 'Admin', is_org_admin: true } }

function Where() { const l = useLocation(); return <div data-testid="where">{l.pathname}{l.search}</div> }

const renderHome = (user: typeof member | null = member) => renderWithProviders(
  <AuthContext.Provider value={{ user: user as never, loading: false, login: async () => {}, logout: () => {} }}>
    <MemoryRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="*" element={<Where />} />
      </Routes>
    </MemoryRouter>
  </AuthContext.Provider>,
)

const report = (over = {}) => ({
  id: 1, name: 'Sales', dataset_id: null, additional_dataset_ids: [], theme: 'default',
  pages: [], created_at: '2026-08-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z',
  is_mine: true, created_by: 9, published: true, my_capability: 'data', ...over,
})
const dataset = (over = {}) => ({
  id: 1, name: 'orders', row_count: 2000, col_count: 13, file_size: 100, filename: 'orders.csv',
  created_at: '2026-09-01T00:00:00Z', mode: 'import', ...over,
})
const num = (v: number) => localDigits(v.toLocaleString('en-US'))

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  vi.mocked(useAiOffline).mockReturnValue({ offline: false, checkedAt: null })
  vi.mocked(reportsApi.list).mockResolvedValue([report()] as never)
  vi.mocked(reportsApi.recent).mockResolvedValue([] as never)
  vi.mocked(datasetsApi.list).mockResolvedValue([dataset()] as never)
  vi.mocked(lineageApi.graph).mockResolvedValue({ sources: [], datasets: [], reports: [] } as never)
  vi.mocked(dataSourcesApi.list).mockResolvedValue([] as never)
  vi.mocked(agentApi.listConversations).mockResolvedValue([] as never)
  vi.mocked(monitoringApi.refreshRuns).mockResolvedValue([] as never)
  vi.mocked(monitoringApi.activity).mockResolvedValue([] as never)
})

describe('Continue where you left off', () => {
  it('lists recents in the order the server returned them', async () => {
    // Ordering is the SERVER's claim (per-user view history); re-sorting here
    // would quietly bring back the "what changed" ordering it replaced.
    vi.mocked(reportsApi.recent).mockResolvedValue([
      { id: 2, name: 'Newer', viewed_at: '2026-09-05T00:00:00Z', published: true, created_by: 9, is_mine: true, my_capability: 'data' },
      { id: 1, name: 'Older', viewed_at: '2026-08-01T00:00:00Z', published: true, created_by: 9, is_mine: true, my_capability: 'data' },
    ] as never)
    renderHome()
    const recents = await screen.findByTestId('home-recents')
    const names = within(recents).getAllByRole('link').map(a => a.textContent)
    expect(names).toEqual(['Newer', 'Older'])
  })

  it('says when YOU opened it, not when it was modified', async () => {
    vi.mocked(reportsApi.recent).mockResolvedValue([
      { id: 7, name: 'Q3', viewed_at: new Date(Date.now() - 3600_000).toISOString(), published: true, created_by: 9, is_mine: true, my_capability: 'data' },
    ] as never)
    renderHome()
    const link = await screen.findByTestId('home-recent-7')
    expect(link).toHaveAttribute('href', '/reports/7')
    const card = link.closest('article')!
    expect(card).toHaveTextContent(/Opened/)
    expect(card).not.toHaveTextContent(/Modified/)
  })

  it('a failed recents call fails only its own section', async () => {
    vi.mocked(reportsApi.recent).mockRejectedValue(new Error('down'))
    renderHome()
    expect(await screen.findByText(/Couldn't load the dashboards you opened recently/)).toBeInTheDocument()
    expect(screen.getByTestId('home-dataset-1')).toBeInTheDocument()
  })
})

describe('Dashboards section', () => {
  it('marks an unpublished dashboard as a draft and a published one as published', async () => {
    vi.mocked(reportsApi.list).mockResolvedValue([
      report({ id: 3, name: 'WIP', published: false }), report({ id: 4, name: 'Live', published: true }),
    ] as never)
    renderHome()
    expect((await screen.findByTestId('home-dash-3')).closest('article')).toHaveTextContent('Draft')
    expect(screen.getByTestId('home-dash-4').closest('article')).toHaveTextContent('Published')
  })

  it('does not mark a legacy (unowned) dashboard as a draft', async () => {
    // created_by null predates authorship: those are org-wide, not drafts.
    vi.mocked(reportsApi.list).mockResolvedValue([report({ id: 5, name: 'Legacy', published: false, created_by: null, is_mine: false })] as never)
    renderHome()
    const card = (await screen.findByTestId('home-dash-5')).closest('article')!
    expect(card).not.toHaveTextContent('Draft')
  })

  it('Mine shows only the dashboards this person created', async () => {
    vi.mocked(reportsApi.list).mockResolvedValue([
      report({ id: 1, name: 'Mine one', is_mine: true }), report({ id: 2, name: 'Theirs', is_mine: false, created_by: 4 }),
    ] as never)
    renderHome()
    await screen.findByTestId('home-dash-2')
    fireEvent.click(screen.getByRole('button', { name: 'Mine' }))
    expect(screen.queryByTestId('home-dash-2')).not.toBeInTheDocument()
    expect(screen.getByTestId('home-dash-1')).toBeInTheDocument()
  })

  it('offers Share only where the server would allow it', async () => {
    vi.mocked(reportsApi.list).mockResolvedValue([
      report({ id: 1, name: 'Mine one', is_mine: true }),
      report({ id: 2, name: 'Theirs', is_mine: false, created_by: 4, my_capability: 'view' }),
    ] as never)
    renderHome()
    await screen.findByTestId('home-dash-2')
    expect(screen.getByRole('button', { name: 'Share Mine one' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Share Theirs' })).not.toBeInTheDocument()
  })

  it('a view-only dashboard says so instead of a modified time', async () => {
    vi.mocked(reportsApi.list).mockResolvedValue([report({ id: 2, name: 'Theirs', is_mine: false, created_by: 4, my_capability: 'view' })] as never)
    renderHome()
    expect((await screen.findByTestId('home-dash-2')).closest('article')).toHaveTextContent('View only')
  })
})

describe('Datasets section', () => {
  it('shows real row and column counts', async () => {
    vi.mocked(datasetsApi.list).mockResolvedValue([dataset({ id: 4, name: 'orders', row_count: 2000, col_count: 13 })] as never)
    renderHome()
    const row = await screen.findByTestId('home-dataset-4')
    expect(within(row).getByRole('link', { name: 'orders' })).toHaveAttribute('href', '/datasets/4')
    expect(row.textContent).toContain(num(2000))
    expect(row.textContent).toContain(num(13))
  })

  it('does not claim a live dataset has no rows', async () => {
    // A DirectQuery dataset is queried at its source: `row_count` is absent,
    // not zero, and "0 rows" states something false about the data.
    vi.mocked(datasetsApi.list).mockResolvedValue([
      dataset({ id: 9, name: 'Live Orders', mode: 'directquery', row_count: null, col_count: 8, filename: null, data_source_id: 2 }),
    ] as never)
    renderHome()
    const row = await screen.findByTestId('home-dataset-9')
    expect(row.textContent).not.toMatch(/0 ×/)
    expect(row.textContent).toContain(`${num(8)} columns`)
  })

  it('reads a failing refresh from the lineage graph', async () => {
    vi.mocked(lineageApi.graph).mockResolvedValue({ sources: [], reports: [], datasets: [
      { id: 1, name: 'orders', mode: 'import', source_id: null, joins: [], extraction_kind: 'x', transform: { count: 0, kinds: [] },
        load: { last_refreshed_at: null, strategy: null, cursor_column: null, staleness: 'stale' }, health: 'failing' },
    ] } as never)
    renderHome()
    await waitFor(() => expect(screen.getByTestId('home-dataset-1')).toHaveTextContent('Refresh failed'))
  })

  it('carries the full name as a tooltip', async () => {
    vi.mocked(datasetsApi.list).mockResolvedValue([dataset({ id: 11, name: 'A dataset with a very long name indeed' })] as never)
    renderHome()
    const el = await screen.findByRole('link', { name: 'A dataset with a very long name indeed' })
    expect(el).toHaveAttribute('title', 'A dataset with a very long name indeed')
  })
})

describe('the question box', () => {
  it('hands the question to Ask AI, which waits for data to be chosen', async () => {
    renderHome()
    const box = await screen.findByRole('textbox', { name: /Ask a question about your data/ })
    fireEvent.change(box, { target: { value: 'Which region grew?' } })
    fireEvent.submit(box.closest('form')!)
    expect(await screen.findByTestId('where')).toHaveTextContent('/ask?q=Which%20region%20grew%3F')
  })

  it('offers starters from the newest dataset it can ask about, scoped to it', async () => {
    vi.mocked(datasetsApi.list).mockResolvedValue([dataset({ id: 4, name: 'Sales',
      columns: [{ name: 'revenue', dtype: 'float64' }, { name: 'region', dtype: 'object' }] })] as never)
    renderHome()
    const group = await screen.findByRole('group', { name: 'Suggested questions about Sales' })
    fireEvent.click(within(group).getAllByRole('button')[0])
    expect(await screen.findByTestId('where')).toHaveTextContent('/ask?dataset=4&q=')
  })

  it('is locked, saying why, while the model server is unreachable', async () => {
    vi.mocked(useAiOffline).mockReturnValue({ offline: true, checkedAt: Date.now() })
    renderHome()
    const box = await screen.findByRole('textbox', { name: /Ask a question about your data/ })
    expect(box).toBeDisabled()
    expect(screen.getByText(/New questions are paused/)).toBeInTheDocument()
    // The rest of Home keeps working.
    expect(await screen.findByTestId('home-dataset-1')).toBeInTheDocument()
  })
})

describe('the tiles', () => {
  it('count what exists, from the lists the page already has', async () => {
    vi.mocked(reportsApi.list).mockResolvedValue([report({ id: 1, published: true }), report({ id: 2, published: false })] as never)
    vi.mocked(datasetsApi.list).mockResolvedValue([dataset({ id: 1, row_count: 300 }), dataset({ id: 2, row_count: 200 })] as never)
    vi.mocked(dataSourcesApi.list).mockResolvedValue([{ id: 1, name: 'WH', type: 'postgresql' }] as never)
    renderHome()
    expect(await screen.findByTestId('hm-tile-dashboards')).toHaveTextContent(`${num(1)} published`)
    expect(screen.getByTestId('hm-tile-datasets')).toHaveTextContent(`${num(500)} rows`)
    await waitFor(() => expect(screen.getByTestId('hm-tile-connections')).toHaveTextContent('PostgreSQL'))
  })
})

describe('admin-only sections', () => {
  it('are not requested, or shown, for a member', async () => {
    renderHome(member)
    await screen.findByTestId('home-dataset-1')
    expect(monitoringApi.activity).not.toHaveBeenCalled()
    expect(monitoringApi.refreshRuns).not.toHaveBeenCalled()
    expect(screen.queryByTestId('home-activity')).not.toBeInTheDocument()
    expect(screen.queryByTestId('home-jobs')).not.toBeInTheDocument()
  })

  it('show what happened and what is refreshing, for an org admin', async () => {
    vi.mocked(monitoringApi.activity).mockResolvedValue([
      { id: 2, user_email: 'omar@example.com', action: 'report.publish', entity: 'report', entity_id: 1, detail: null, created_at: new Date().toISOString() },
      { id: 1, user_email: 'omar@example.com', action: 'auth.login', entity: null, entity_id: null, detail: null, created_at: new Date().toISOString() },
    ] as never)
    const now = new Date().toISOString()
    vi.mocked(monitoringApi.refreshRuns).mockResolvedValue([
      { id: 1, kind: 'dataset', item_id: 1, name: 'orders', trigger: 'schedule', status: 'failed', started_at: now, finished_at: now, rows: null, duration_ms: 1, error: 'connection timed out', error_code: null },
      { id: 2, kind: 'dataset', item_id: 2, name: 'stock', trigger: 'schedule', status: 'ok', started_at: now, finished_at: now, rows: 5, duration_ms: 1, error: null, error_code: null },
    ] as never)
    renderHome(admin)
    const act = await screen.findByTestId('home-activity')
    await waitFor(() => expect(act).toHaveTextContent('omar published Sales'))
    // A raw action code is not a sentence; it stays on the Activity page.
    expect(act).not.toHaveTextContent('auth.login')
    const jobs = screen.getByTestId('home-jobs')
    await waitFor(() => expect(jobs).toHaveTextContent('connection timed out'))
    expect(within(jobs).getByRole('button', { name: /Retry/ })).toBeInTheDocument()
    expect(screen.getByTestId('hm-tile-refresh')).toHaveTextContent(`${num(1)} of ${num(2)} jobs failed`)
  })

  it('a failed activity call fails only its own card', async () => {
    vi.mocked(monitoringApi.activity).mockRejectedValue(new Error('down'))
    renderHome(admin)
    expect(await screen.findByText("Couldn't load recent activity.")).toBeInTheDocument()
    expect(screen.getByTestId('home-dataset-1')).toBeInTheDocument()
  })
})

describe('outage and first run', () => {
  it('renders an outage as an error, never as an empty workspace', async () => {
    // THE landing-page failure mode: telling someone with a full workspace
    // that they have nothing, and inviting them to rebuild it.
    vi.mocked(reportsApi.list).mockRejectedValue(new Error('down'))
    renderHome()
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.queryByTestId('home-onboarding')).not.toBeInTheDocument()
    expect(screen.queryByText(/No dashboards yet/)).not.toBeInTheDocument()
  })

  it('an empty workspace gets the setup steps, and the question box says why it is locked', async () => {
    vi.mocked(reportsApi.list).mockResolvedValue([] as never)
    vi.mocked(datasetsApi.list).mockResolvedValue([] as never)
    renderHome()
    expect(await screen.findByTestId('home-onboarding')).toHaveTextContent(`${num(0)} of ${num(3)} complete`)
    expect(screen.getByRole('textbox', { name: /Ask a question about your data/ })).toBeDisabled()
    expect(screen.getByPlaceholderText('Connect data first to ask questions')).toBeInTheDocument()
    expect(screen.getAllByText(/upload a file or connect a database/i).length).toBeGreaterThan(0)
  })

  it('counts a finished step from the data that exists', async () => {
    vi.mocked(reportsApi.list).mockResolvedValue([] as never)
    renderHome()
    expect(await screen.findByTestId('home-onboarding')).toHaveTextContent(`${num(1)} of ${num(3)} complete`)
  })
})

describe('Home accessibility', () => {
  it('has no structural accessibility violations', async () => {
    vi.mocked(reportsApi.recent).mockResolvedValue([{ id: 1, name: 'Sales', viewed_at: '2026-09-05T00:00:00Z',
      published: true, created_by: 9, is_mine: true, my_capability: 'data' }] as never)
    const { container } = renderHome(admin)
    await screen.findByTestId('home-recents')
    await screen.findByTestId('home-activity')
    expect(await axeViolations(container)).toEqual([])
  })
})

/**
 * Router 7 navigates inside a transition, so the route-level Suspense loader
 * never appears while the next page's chunk loads. Home must show it itself
 * the moment a link is clicked -- otherwise the click looks ignored.
 */
describe('opening something', () => {
  it('shows the loader as soon as a dataset is clicked', async () => {
    renderWithProviders(
      <MemoryRouter>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/datasets/:id" element={<Never />} />
        </Routes>
      </MemoryRouter>,
    )
    fireEvent.click(await screen.findByRole('link', { name: 'orders' }))
    expect(await screen.findByRole('status')).toBeInTheDocument()
  })

  it('does not swap in the loader for a modified click (new tab)', async () => {
    renderHome()
    const link = await screen.findByRole('link', { name: 'orders' })
    fireEvent.click(link, { ctrlKey: true })
    expect(screen.getByTestId('home-dataset-1')).toBeInTheDocument()
  })
})

function Never(): never { throw new Promise(() => {}) }
