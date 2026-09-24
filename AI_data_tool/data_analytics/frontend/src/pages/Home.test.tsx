import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Home from './Home'
import { datasetsApi, reportsApi, pinsApi } from '../services/api'
import { axeViolations } from '../test/axe'

/**
 * Home is a landing page built from data the app already serves. The claims
 * worth pinning are about HONESTY: sections show real entities ordered by real
 * timestamps, an outage is never rendered as an empty workspace, and a failed
 * pin fetch does not silently read as "you have no pins".
 */

vi.mock('../services/api', () => ({
  reportsApi: { list: vi.fn(), recent: vi.fn() },
  datasetsApi: { list: vi.fn() },
  pinsApi: { list: vi.fn() },
}))

const renderHome = () => render(<MemoryRouter><Home /></MemoryRouter>)

const report = (over = {}) => ({
  id: 1, name: 'Sales', dataset_id: null, additional_dataset_ids: [], theme: 'default',
  pages: [], created_at: '2026-08-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z',
  is_mine: true, created_by: 9, published: true, ...over,
})
const dataset = (over = {}) => ({
  id: 1, name: 'orders', row_count: 2000, col_count: 13, file_size: 100,
  created_at: '2026-09-01T00:00:00Z', mode: 'import', ...over,
})

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(reportsApi.list).mockResolvedValue([] as never)
  vi.mocked(reportsApi.recent).mockResolvedValue([] as never)
  vi.mocked(datasetsApi.list).mockResolvedValue([] as never)
  vi.mocked(pinsApi.list).mockResolvedValue([] as never)
})

describe('Home', () => {
  it('renders recents in the order the server returned them', async () => {
    // Ordering is the SERVER's claim now (per-user view history), so the page
    // must not re-sort: re-sorting here by any client-side field would quietly
    // reintroduce the "what changed" ordering this feature replaced.
    vi.mocked(reportsApi.recent).mockResolvedValue([
      { id: 2, name: 'Newer', viewed_at: '2026-09-05T00:00:00Z', published: true,
        created_by: 9, is_mine: true, my_capability: 'data' },
      { id: 1, name: 'Older', viewed_at: '2026-08-01T00:00:00Z', published: true,
        created_by: 9, is_mine: true, my_capability: 'data' },
    ] as never)
    renderHome()

    const recents = await screen.findByTestId('home-recents')
    const names = within(recents).getAllByRole('link').map(a => a.textContent)
    expect(names[0]).toContain('Newer')
    expect(names[1]).toContain('Older')
  })

  it('says when YOU opened it, not when it was modified', async () => {
    vi.mocked(reportsApi.recent).mockResolvedValue([
      { id: 7, name: 'Q3', viewed_at: new Date(Date.now() - 3600_000).toISOString(),
        published: true, created_by: 9, is_mine: true, my_capability: 'data' },
    ] as never)
    renderHome()
    const card = await screen.findByTestId('home-recent-7')
    expect(card).toHaveAttribute('href', '/reports/7')
    expect(card).toHaveTextContent(/Opened/)
    expect(card).not.toHaveTextContent(/Modified/)
  })

  it('shows datasets with their real row and column counts', async () => {
    vi.mocked(datasetsApi.list).mockResolvedValue([
      dataset({ id: 4, name: 'orders', row_count: 2000, col_count: 13 }),
    ] as never)
    renderHome()

    const card = await screen.findByTestId('home-dataset-4')
    expect(card).toHaveAttribute('href', '/datasets/4')
    expect(card.textContent).toContain((2000).toLocaleString())
    expect(card.textContent).toContain((13).toLocaleString())
  })

  it('marks an unpublished dashboard as a draft', async () => {
    vi.mocked(reportsApi.recent).mockResolvedValue([
      { id: 3, name: 'WIP', viewed_at: '2026-09-01T00:00:00Z', published: false,
        created_by: 9, is_mine: true, my_capability: 'data' },
    ] as never)
    renderHome()
    expect(await screen.findByTestId('home-recent-3')).toHaveTextContent('draft')
  })

  it('does not mark a legacy (unowned) dashboard as a draft', async () => {
    // created_by null predates authorship: those are org-wide, not drafts.
    vi.mocked(reportsApi.recent).mockResolvedValue([
      { id: 5, name: 'Legacy', viewed_at: '2026-09-01T00:00:00Z', published: false,
        created_by: null, is_mine: false, my_capability: 'data' },
    ] as never)
    renderHome()
    const card = await screen.findByTestId('home-recent-5')
    expect(card).not.toHaveTextContent('draft')
  })

  it('renders an outage as an error, never as an empty workspace', async () => {
    // THE landing-page failure mode: telling someone with a full workspace
    // that they have nothing, and inviting them to rebuild it.
    vi.mocked(reportsApi.list).mockRejectedValue(new Error('down'))
    renderHome()
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.queryByTestId('home-recents')).not.toBeInTheDocument()
  })

  it('has no pinned or explore section, and no create buttons in the header', async () => {
    // Deliberately seeded with data so the Datasets empty state -- which keeps
    // its own "Upload data" call to action -- is not rendered. Without that,
    // this assertion would pass for the wrong reason.
    vi.mocked(datasetsApi.list).mockResolvedValue([
      { id: 4, name: 'Orders', row_count: 10, col_count: 3, mode: 'import' },
    ] as never)
    vi.mocked(reportsApi.list).mockResolvedValue([
      { id: 1, name: 'Sales', published: true, created_by: 9, is_mine: true,
        my_capability: 'data' },
    ] as never)
    renderHome()
    await screen.findByTestId('home-recents')

    expect(screen.queryByTestId('home-pinned')).not.toBeInTheDocument()
    expect(screen.queryByTestId('home-explore')).not.toBeInTheDocument()
    expect(screen.queryByText(/upload data/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/new dashboard/i)).not.toBeInTheDocument()
  })

  it('offers a way forward from an empty workspace', async () => {
    renderHome()
    expect(await screen.findByText(/Nothing yet/)).toBeInTheDocument()
    expect(screen.getByText(/upload a file or connect a database/i)).toBeInTheDocument()
  })

  it('sections collapse, and the choice sticks', async () => {
    vi.mocked(reportsApi.recent).mockResolvedValue([
      { id: 1, name: 'Sales', viewed_at: '2026-09-01T00:00:00Z', published: true,
        created_by: 9, is_mine: true, my_capability: 'data' },
    ] as never)
    renderHome()
    const recents = await screen.findByTestId('home-recents')
    const toggle = within(recents).getByRole('button', { name: 'Recents' })

    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(localStorage.getItem('home.section.Recents')).toBe('0')
  })
})

/**
 * A live dataset has no row count, and zero is not the same as unknown.
 *
 * Photographed on the running app: "Demo — Live Orders (DirectQuery)" read
 * "0 rows · 8 columns" beside a LIVE badge. A DirectQuery dataset is queried at
 * its source, so nobody has counted its rows — `row_count` is simply absent.
 * Rendering that as 0 states something false about the data, and an empty
 * dataset is exactly the thing a reader would act on.
 */
describe('a DirectQuery dataset card', () => {
  it('does not claim the dataset has no rows', async () => {
    vi.mocked(datasetsApi.list).mockResolvedValue([
      dataset({ id: 9, name: 'Live Orders', mode: 'directquery',
        row_count: null, col_count: 8 }),
    ] as never)
    renderHome()

    expect(await screen.findByText('Live Orders')).toBeInTheDocument()
    // `toLocaleString()` renders Arabic-Indic digits in this environment, so a
    // Latin "8" matches nothing -- assert through the same formatter.
    const card = screen.getByTestId('home-dataset-9')
    expect(card.textContent).not.toMatch(new RegExp(`${(0).toLocaleString()} rows`))
    // The columns ARE known, so they are still worth saying.
    expect(card.textContent).toContain(`${(8).toLocaleString()} columns`)
  })

  it('still counts rows for an imported dataset', async () => {
    vi.mocked(datasetsApi.list).mockResolvedValue([
      dataset({ id: 10, name: 'Sales', mode: 'import', row_count: 300, col_count: 8 }),
    ] as never)
    renderHome()
    await screen.findByText('Sales')
    expect(screen.getByTestId('home-dataset-10').textContent)
      .toContain(`${(300).toLocaleString()} rows`)
  })
})

/**
 * A name that does not fit must still be readable.
 *
 * Photographed on the running app: dashboard cards read "Boundary set veri…".
 * CSS truncation is right — the card cannot grow — but without the full text on
 * the element there is no way to find out what was cut, and two dashboards
 * whose names differ after the twentieth character are indistinguishable.
 */
describe('truncated names', () => {
  it('carries the full name as a tooltip', async () => {
    vi.mocked(datasetsApi.list).mockResolvedValue([
      dataset({ id: 11, name: 'A dataset with a very long name indeed' }),
    ] as never)
    renderHome()

    const el = await screen.findByText('A dataset with a very long name indeed')
    expect(el).toHaveAttribute('title', 'A dataset with a very long name indeed')
  })
})

describe('Home accessibility', () => {
  it('has no structural accessibility violations', async () => {
    vi.mocked(reportsApi.recent).mockResolvedValue([{ id: 2, name: 'Newer', viewed_at: '2026-09-05T00:00:00Z',
      published: true, created_by: 9, is_mine: true, my_capability: 'data' }] as never)
    const { container } = renderHome()
    await screen.findByTestId('home-recents')
    expect(await axeViolations(container)).toEqual([])
  })
})
