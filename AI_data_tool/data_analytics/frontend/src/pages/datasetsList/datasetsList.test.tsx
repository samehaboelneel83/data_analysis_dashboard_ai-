import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { ReactNode } from 'react'
import Dashboard from '../Dashboard'
import DatasetPreview from './DatasetPreview'
import { sourceKind, sourceWords, statusOf, freshnessWords } from './classify'
import { AuthContext } from '../../contexts/AuthContext'
import { ConfirmProvider } from '../../components/ui/ConfirmDialog'
import { translate } from '../../i18n'
import { dataPreviewApi, datasetsApi, lineageApi, sensitivityApi, type LineageGraph } from '../../services/api'

/**
 * Redesign step 3a: the Datasets list's health strip, facets, Source /
 * Freshness / Dashboards columns, preview panel and its states. Everything is
 * built from the list, its catalog and the lineage graph -- no new endpoint.
 */

vi.mock('../../services/api', () => ({
  datasetsApi: { list: vi.fn(), delete: vi.fn() },
  lineageApi: { graph: vi.fn() },
  dataPreviewApi: { query: vi.fn() },
  sensitivityApi: { get: vi.fn() },
  reportsApi: { create: vi.fn() },
}))
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))

const t = (k: string, p?: Record<string, unknown>) => translate('en', k as never, p as never)
const hoursAgo = (h: number) => new Date(Date.now() - h * 3600_000).toISOString()

const ds = (over: Record<string, unknown> = {}) => ({
  id: 1, name: 'Demo — Sales', description: 'Orders by region', row_count: 2000, col_count: 13,
  file_size: 226_918, created_at: hoursAgo(1), updated_at: hoursAgo(1), mode: 'import',
  columns: [], column_meta: {}, data_source_id: null,
  catalog: { kind: 'upload', freshness: 'fixed', as_of: hoursAgo(1), next_due: null, refresh_every_minutes: null },
  ...over,
}) as never

const lin = (id: number, over: Record<string, unknown> = {}) => ({
  id, name: `d${id}`, mode: 'import', source_id: null, joins: [], extraction_kind: 'upload',
  transform: { count: 0, kinds: [] },
  load: { last_refreshed_at: hoursAgo(6), strategy: null, cursor_column: null, staleness: 'fresh' },
  health: 'ok', ...over,
})

const GRAPH: LineageGraph = {
  sources: [{ id: 4, name: 'Warehouse', type: 'postgresql' }, { id: 5, name: 'Local', type: 'sqlite' }],
  datasets: [lin(1), lin(2, { health: 'stale' }), lin(3, { health: 'failing' }), lin(4)] as never,
  reports: [
    { id: 10, name: 'Sales Overview', dataset_ids: [1] },
    { id: 11, name: 'Regional performance', dataset_ids: [1, 2] },
  ],
}

const FOUR = [
  ds(),
  ds({ id: 2, name: 'Demo — Routes', data_source_id: 4, created_by: 5,
       catalog: { kind: 'connection', freshness: 'on_schedule', as_of: hoursAgo(6), next_due: null, refresh_every_minutes: 60, source: 'Warehouse' } }),
  ds({ id: 3, name: 'Demo — Feedback', data_source_id: 4,
       catalog: { kind: 'connection', freshness: 'on_schedule', as_of: hoursAgo(30), next_due: null, refresh_every_minutes: 60, source: 'Warehouse' } }),
  ds({ id: 4, name: 'Live Orders', mode: 'directquery', data_source_id: 5, row_count: 12000, file_size: 0,
       column_meta: { __certified__: { by_email: 'a@b.c' } },
       catalog: { kind: 'live', freshness: 'live', as_of: null, next_due: null, refresh_every_minutes: null, source: 'Local' } }),
]

function renderList(user: Record<string, unknown> | null = { id: 5, role: { is_org_admin: false } }) {
  const wrap = (ui: ReactNode) => (
    <AuthContext.Provider value={{ user, loading: false, login: vi.fn(), logout: vi.fn() } as never}>
      <ConfirmProvider><MemoryRouter>{ui}</MemoryRouter></ConfirmProvider>
    </AuthContext.Provider>
  )
  return render(wrap(<Dashboard />))
}
const tableNames = () => within(screen.getByRole('table')).getAllByRole('row').slice(1)
  .map(r => within(within(r).getAllByRole('cell')[1]).getByRole('link').textContent)

beforeEach(() => {
  vi.clearAllMocks()
  try { localStorage.clear() } catch { /* jsdom */ }
  vi.mocked(datasetsApi.list).mockResolvedValue(FOUR as never)
  vi.mocked(lineageApi.graph).mockResolvedValue(GRAPH)
  vi.mocked(dataPreviewApi.query).mockResolvedValue({ columns: ['date', 'region', 'revenue'],
    rows: [['2026-09-30', 'Asia Pacific', 4812.2], ['2026-09-29', 'Europe', 3382.234567]], total: 2000 })
  vi.mocked(sensitivityApi.get).mockResolvedValue({ label: 'Internal', effective: 'Internal', reasons: [], options: [], redacted_on_share: [] })
})

describe('classify (3a)', () => {
  it('names the source from the lineage graph type, and falls back to the catalog', () => {
    expect(sourceKind(FOUR[0])).toBe('upload')
    expect(sourceWords(FOUR[1], GRAPH, t as never)).toBe('Import · PostgreSQL')
    expect(sourceWords(FOUR[3], GRAPH, t as never)).toBe('Live · SQLite')
    expect(sourceWords(FOUR[1], null, t as never)).toBe('Copied from Warehouse')
  })

  it('takes failing and stale from pipeline health; live is always current', () => {
    expect(statusOf(FOUR[1], GRAPH.datasets[1])).toBe('stale')
    expect(statusOf(FOUR[2], GRAPH.datasets[2])).toBe('failing')
    expect(statusOf(FOUR[3], { ...GRAPH.datasets[3], health: 'failing' })).toBe('fresh')
    expect(freshnessWords(FOUR[2], GRAPH.datasets[2], t as never).text).toMatch(/^Refresh failing · last refreshed/)
    expect(freshnessWords(FOUR[1], GRAPH.datasets[1], t as never).text).toMatch(/^Stale · refreshed 6 hours ago/)
  })
})

describe('Datasets list health strip (3a)', () => {
  it('counts by kind and status, and links to the one stale and the one failing dataset', async () => {
    renderList()
    const strip = await screen.findByRole('region', { name: 'Summary' })
    await waitFor(() => expect(within(strip).getByTestId('health-stale')).toBeInTheDocument())
    expect(within(strip).getByTestId('health-upload')).toHaveTextContent('1 uploaded files')
    expect(within(strip).getByTestId('health-live')).toHaveTextContent('1 live')
    expect(within(strip).getByRole('link', { name: 'Demo — Routes' })).toHaveAttribute('href', '/datasets/2')
    expect(within(strip).getByRole('link', { name: 'Demo — Feedback' })).toHaveAttribute('href', '/datasets/3')
  })
})

describe('Datasets list table (3a)', () => {
  it('shows Source, Freshness and the dashboards built on each dataset', async () => {
    renderList()
    await waitFor(() => expect(screen.getByTestId('dashboards-1')).toHaveTextContent('2'))
    expect(screen.getByTestId('source-2')).toHaveTextContent('Import · PostgreSQL')
    expect(screen.getByTestId('catalog-3')).toHaveTextContent(/Refresh failing/)
    expect(screen.getByTestId('dashboards-4')).toHaveTextContent('0')
  })

  it('still lists everything, with catalog words, when the lineage graph fails', async () => {
    vi.mocked(lineageApi.graph).mockRejectedValue(new Error('down'))
    renderList()
    await screen.findByTestId('source-2')
    expect(screen.getByTestId('source-2')).toHaveTextContent('Copied from Warehouse')
    expect(screen.getByTestId('dashboards-1')).toHaveTextContent('—')
  })
})

describe('Datasets list facets (3a)', () => {
  it('narrows by source and by status', async () => {
    renderList()
    await waitFor(() => expect(screen.getByTestId('dashboards-1')).toHaveTextContent('2'))
    fireEvent.change(screen.getByLabelText(/^Source/), { target: { value: 'live' } })
    expect(tableNames()).toEqual(['Live Orders'])
    fireEvent.change(screen.getByLabelText(/^Source/), { target: { value: 'all' } })
    fireEvent.change(screen.getByLabelText(/^Status/), { target: { value: 'failing' } })
    expect(tableNames()).toEqual(['Demo — Feedback'])
  })

  it('"Mine only" keeps what the signed-in user created; "Certified only" the certified ones', async () => {
    renderList()
    await screen.findByTestId('source-2')
    fireEvent.click(screen.getByRole('button', { name: /Mine only/ }))
    expect(tableNames()).toEqual(['Demo — Routes'])
    fireEvent.click(screen.getByRole('button', { name: /Mine only/ }))
    fireEvent.click(screen.getByRole('button', { name: /Certified only/ }))
    expect(tableNames()).toEqual(['Live Orders'])
  })

  it('says when the filters match nothing, and offers to show all', async () => {
    renderList()
    await screen.findByTestId('source-2')
    fireEvent.click(screen.getByRole('button', { name: /Certified only/ }))
    fireEvent.change(screen.getByLabelText(/^Source/), { target: { value: 'upload' } })
    expect(screen.getByText('No dataset matches these filters.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Show all 4' }))
    expect(tableNames()).toHaveLength(4)
  })

  it('a search with no match names the text and clears it', async () => {
    vi.mocked(datasetsApi.list).mockResolvedValue(
      Array.from({ length: 9 }, (_, i) => ds({ id: i + 1, name: `set ${i + 1}` })) as never)
    renderList()
    const box = await screen.findByRole('searchbox')
    fireEvent.change(box, { target: { value: 'zzqx' } })
    expect(screen.getByText('Nothing matches “zzqx”')).toBeInTheDocument()
    fireEvent.click(screen.getAllByRole('button', { name: 'Clear search' })[0])
    expect(tableNames()).toHaveLength(8)
  })
})

describe('Datasets list states (3a)', () => {
  it('first run: the way in, with sample data offered to admins only', async () => {
    vi.mocked(datasetsApi.list).mockResolvedValue([] as never)
    const { unmount } = renderList({ id: 1, role: { is_org_admin: true } })
    expect(await screen.findByText('Add your first dataset')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Sample data/ })).toHaveAttribute('href', '/admin/settings')
    unmount()
    renderList({ id: 2, role: { is_org_admin: false } })
    await screen.findByText('Add your first dataset')
    expect(screen.queryByRole('link', { name: /Sample data/ })).toBeNull()
  })

  it('an outage is an interruption with a retry, not the empty state', async () => {
    vi.mocked(datasetsApi.list).mockRejectedValueOnce(new Error('timeout'))
    renderList()
    expect(await screen.findByRole('alert')).toHaveTextContent('Couldn’t load your datasets')
    expect(screen.queryByText('Add your first dataset')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    await screen.findByTestId('source-2')
    expect(datasetsApi.list).toHaveBeenCalledTimes(2)
  })

  it('selecting a row moves the preview to it', async () => {
    renderList()
    const preview = await screen.findByTestId('dataset-preview')
    expect(within(preview).getByRole('heading', { name: 'Demo — Sales' })).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('source-3'))
    expect(within(screen.getByTestId('dataset-preview')).getByRole('heading', { name: 'Demo — Feedback' })).toBeInTheDocument()
  })
})

describe('DatasetPreview (3a)', () => {
  const sales = ds({ created_by: 5, columns: [
    { id: 1, name: 'date', dtype: 'datetime', missing_pct: 0, stats: {} },
    { id: 2, name: 'region', dtype: 'categorical', missing_pct: 0, stats: {} },
    { id: 3, name: 'revenue', dtype: 'numeric', missing_pct: 0, stats: {} },
  ] })
  const show = (meId: number | null) => render(
    <MemoryRouter><DatasetPreview ds={sales} graph={GRAPH} meId={meId} fmtBytes={b => `${b} B`} /></MemoryRouter>)

  it('shows its facts, columns, first rows, dashboards and the three next steps', async () => {
    show(5)
    expect(screen.getByText(/Created by you/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open' })).toHaveAttribute('href', '/datasets/1')
    expect(screen.getByRole('link', { name: 'Ask' })).toHaveAttribute('href', '/ask?dataset=1')
    expect(screen.getByRole('button', { name: 'Build dashboard' })).toBeInTheDocument()
    expect(screen.getByText('3 columns')).toBeInTheDocument()
    expect(await screen.findByText('Internal')).toBeInTheDocument()
    expect(await screen.findByText('Asia Pacific')).toBeInTheDocument()
    expect(screen.getByText('3382.23')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Sales Overview/ })).toHaveAttribute('href', '/reports/10')
  })

  it('leaves the owner out when someone else created it (no owner names yet, P1)', () => {
    show(9)
    expect(screen.queryByText(/Created by/)).toBeNull()
  })
})
