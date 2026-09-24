import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Dashboard from './Dashboard'
import { datasetsApi, demoApi, pinsApi } from '../services/api'
import { ConfirmProvider } from '../components/ui/ConfirmDialog'

vi.mock('../services/api', () => ({
  pinsApi: { create: vi.fn().mockResolvedValue({ id: 1, widget_id: 1, already_pinned: false }), list: vi.fn().mockResolvedValue([]), remove: vi.fn().mockResolvedValue(undefined), update: vi.fn().mockResolvedValue({ id: 1, position: 1, size: 'm' }) },
  datasetsApi: { list: vi.fn(), delete: vi.fn() },
  demoApi: { seed: vi.fn(), unseed: vi.fn() },
  insightsApi: { run: vi.fn(), runShared: vi.fn().mockResolvedValue({ findings: [], narrative: '' }) },
  narrateApi: { one: vi.fn().mockResolvedValue(null) },
  findingKey: (f: { kind: string; columns: string[] }) => [f.kind, ...[...f.columns].sort()].join('|'),
  clearWidgetDataClientCache: vi.fn(),
}))
vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}))

const renderDashboard = () =>
  render(
    <ConfirmProvider>
      <MemoryRouter><Dashboard /></MemoryRouter>
    </ConfirmProvider>
  )

const dataset = (over = {}) => ({
  id: 1, name: 'sales', row_count: 10, col_count: 5, file_size: 283,
  created_at: '2026-08-22T00:00:00Z', ...over,
})

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(datasetsApi.list).mockResolvedValue([] as never)
  vi.mocked(demoApi.seed).mockResolvedValue({ datasets: 5, reports: 5, widgets: 44 } as never)
})

describe('Dashboard carries no demo-loading control', () => {
  // Seeding demo content is a setup chore, not part of managing your data, and
  // it sat in the page's primary action row next to Upload. It is a CLI job
  // now; the endpoint stays, the button does not.
  it('offers none in the empty state, where it used to be loudest', async () => {
    renderDashboard()
    await waitFor(() => expect(screen.getByText('No datasets yet')).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /demo/i })).toBeNull()
  })

  it('offers none beside Upload once datasets exist', async () => {
    vi.mocked(datasetsApi.list).mockResolvedValue([dataset()] as never)
    renderDashboard()
    await waitFor(() => expect(screen.getByText('sales')).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /demo/i })).toBeNull()
    expect(demoApi.seed).not.toHaveBeenCalled()
  })
})

describe('Dashboard row action menu (U1)', () => {
  it('deletes from the ⋯ menu', async () => {
    vi.mocked(datasetsApi.list).mockResolvedValue([dataset()] as never)
    vi.mocked(datasetsApi.delete).mockResolvedValue(undefined as never)
    renderDashboard()
    await waitFor(() => expect(screen.getByText('sales')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: 'More actions for dataset sales' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Delete dataset' }))

    const dlg = await screen.findByRole('alertdialog')
    fireEvent.click(within(dlg).getByRole('button', { name: /Delete/i }))

    await waitFor(() => expect(datasetsApi.delete).toHaveBeenCalledWith(1))
  })

  it('is the only way in -- no second delete control on the row', async () => {
    // A red trash icon repeated down every row is an alarm the page rings at
    // itself. Delete already lived in the menu; it lives there alone now.
    vi.mocked(datasetsApi.list).mockResolvedValue([dataset()] as never)
    renderDashboard()
    await waitFor(() => expect(screen.getByText('sales')).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: 'Delete dataset sales' })).toBeNull()
  })
})

describe('Suggest dashboards, from the dataset row', () => {
  // The menu item is the entire entry point for the feature. A service and an
  // endpoint that nothing calls have shipped in this repo three times, so the
  // item existing and opening the panel is worth pinning.
  it('offers it beside Delete', async () => {
    vi.mocked(datasetsApi.list).mockResolvedValue([dataset()] as never)
    renderDashboard()
    await waitFor(() => expect(screen.getByText('sales')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: 'More actions for dataset sales' }))
    expect(screen.getByRole('menuitem', { name: /Suggest dashboards/i })).toBeInTheDocument()
  })

  it('opens the panel for that dataset', async () => {
    vi.mocked(datasetsApi.list).mockResolvedValue([dataset()] as never)
    renderDashboard()
    await waitFor(() => expect(screen.getByText('sales')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: 'More actions for dataset sales' }))
    fireEvent.click(screen.getByRole('menuitem', { name: /Suggest dashboards/i }))

    expect(await screen.findByRole('dialog', { name: /Suggest dashboards for sales/i }))
      .toBeInTheDocument()
  })
})

describe('Dashboard sharing badge (SH1)', () => {
  it('badges the datasets handed over explicitly, not every one the viewer can read', async () => {
    // Sharing used to be badge-only over org-wide read access; since dataset
    // ownership it also GRANTS. The badge's job is unchanged: mark the ones
    // somebody chose to give you, not the ones you own or reach via a
    // dashboard.
    vi.mocked(datasetsApi.list).mockResolvedValue([
      dataset({ id: 1, name: 'sales', shared: true }),
      dataset({ id: 2, name: 'invoices', shared: false }),
    ] as never)
    renderDashboard()

    await waitFor(() => expect(screen.getByText('sales')).toBeInTheDocument())
    const salesRow = screen.getByText('sales').closest('tr')!
    const invoicesRow = screen.getByText('invoices').closest('tr')!
    expect(salesRow).toHaveTextContent('Shared')
    expect(invoicesRow).not.toHaveTextContent('Shared')
  })
})

describe('the personal pinned dashboard is gone', () => {
  const TILE = {
    id: 7, pin_type: 'widget', position: 1, size: 'm',
    widget_id: 42, widget_type: 'kpi', title: 'Revenue',
    config: { measure: 'revenue', aggregation: 'sum' },
    report_id: 26, report_name: 'Sales report', dataset_id: 32,
    page_id: 1, created_at: '2026-09-01',
  }

  it('renders no pinned tiles even when the server still holds some', async () => {
    // The rows survive in the database and the endpoint still answers. What
    // changed is that Datasets is an inventory of your data, not a second
    // dashboard, so it no longer renders anybody's pins.
    vi.mocked(pinsApi.list).mockResolvedValue([TILE] as never)
    renderDashboard()
    await screen.findByRole('heading', { name: 'Datasets' })
    expect(screen.queryByTestId('pin-tile-42')).toBeNull()
    expect(screen.queryByRole('heading', { name: 'Pinned' })).toBeNull()
  })

  it('never asks for them -- a request whose answer is discarded is waste', async () => {
    renderDashboard()
    await screen.findByRole('heading', { name: 'Datasets' })
    expect(pinsApi.list).not.toHaveBeenCalled()
  })
})


describe('Home summary strip', () => {
  const figure = (summary: HTMLElement, key: string) =>
    within(summary).getByTestId(`stat-${key}`).querySelector('[data-figure]')!.textContent

  it('totals rows and stored bytes across the datasets', async () => {
    vi.mocked(datasetsApi.list).mockResolvedValue([
      dataset({ id: 1, name: 'a', row_count: 2000, col_count: 13, file_size: 227_000 }),
      dataset({ id: 2, name: 'b', row_count: 300, col_count: 8, file_size: 25_500 }),
    ] as never)
    renderDashboard()

    const summary = await screen.findByRole('region', { name: 'Summary' })
    // Locale-aware: toLocaleString renders Arabic-Indic digits under an ar
    // locale, so comparing against a hardcoded "2,300" fails there. Compare
    // against the same formatter the component uses.
    expect(figure(summary, 'datasets')).toBe((2).toLocaleString())
    expect(figure(summary, 'rows')).toBe((2300).toLocaleString())
  })

  it('does not total columns -- 21 columns across two unrelated tables is not a quantity', async () => {
    // Rows and bytes add up because they measure the same thing in each
    // dataset. Column counts describe two different shapes, and their sum
    // answers no question anybody asks.
    vi.mocked(datasetsApi.list).mockResolvedValue([
      dataset({ id: 1, name: 'a', row_count: 2000, col_count: 13, file_size: 227_000 }),
      dataset({ id: 2, name: 'b', row_count: 300, col_count: 8, file_size: 25_500 }),
    ] as never)
    renderDashboard()

    const summary = await screen.findByRole('region', { name: 'Summary' })
    expect(within(summary).queryByTestId('stat-columns')).toBeNull()
    expect(summary).not.toHaveTextContent((21).toLocaleString())
  })

  it('stays hidden when there is nothing to summarise', async () => {
    // "0 datasets · 0 rows" above an empty state is noise; the empty state
    // already says it, and better.
    vi.mocked(datasetsApi.list).mockResolvedValue([] as never)
    renderDashboard()
    await screen.findByText(/No datasets yet/i)
    expect(screen.queryByRole('region', { name: 'Summary' })).not.toBeInTheDocument()
  })

  it('is absent when the list failed -- totals of nothing would be a lie', async () => {
    vi.mocked(datasetsApi.list).mockRejectedValue(new Error('down'))
    renderDashboard()
    await waitFor(() =>
      expect(screen.queryByRole('region', { name: 'Summary' })).not.toBeInTheDocument())
  })
})

describe('DirectQuery rows report what they know, not zero', () => {
  // A DirectQuery dataset keeps its rows in the connection, so the platform
  // stores none and measures no bytes. Printing "0" and "0 B" states something
  // false about the data; an em dash states the truth, which is that the
  // figure does not apply here.
  const live = { id: 3, name: 'live_orders', mode: 'directquery',
                 row_count: 0, col_count: 8, file_size: 0,
                 created_at: '2026-09-07T00:00:00Z' }

  it('dashes the row count and the size', async () => {
    vi.mocked(datasetsApi.list).mockResolvedValue([live] as never)
    renderDashboard()
    const row = (await screen.findByText('live_orders')).closest('tr')!
    const cells = within(row).getAllByRole('cell')
    expect(cells[1]).toHaveTextContent('—')
    expect(cells[3]).toHaveTextContent('—')
  })

  it('still counts the columns, which it does know', async () => {
    vi.mocked(datasetsApi.list).mockResolvedValue([live] as never)
    renderDashboard()
    const row = (await screen.findByText('live_orders')).closest('tr')!
    expect(within(row).getAllByRole('cell')[2]).toHaveTextContent((8).toLocaleString())
  })

  it('leaves an import dataset showing its real zero', async () => {
    // An empty imported file genuinely has no rows. The dash is for "not
    // applicable", never for "none" -- collapsing the two would hide a
    // failed upload behind a tidy dash.
    vi.mocked(datasetsApi.list).mockResolvedValue([
      dataset({ name: 'empty_upload', mode: 'import', row_count: 0, file_size: 0 }),
    ] as never)
    renderDashboard()
    const row = (await screen.findByText('empty_upload')).closest('tr')!
    expect(within(row).getAllByRole('cell')[1]).toHaveTextContent((0).toLocaleString())
  })
})

describe('file sizes survive a right-to-left page', () => {
  // THE bug from the Arabic screenshot: "25.0 KB" rendered as "KB 25.0",
  // because the bidi algorithm reorders a Latin number+unit run inside an RTL
  // paragraph. The isolate characters keep the pair in reading order.
  const LRI = '⁦'   // LEFT-TO-RIGHT ISOLATE
  const PDI = '⁩'   // POP DIRECTIONAL ISOLATE

  it('wraps the number and its unit in a directional isolate', async () => {
    vi.mocked(datasetsApi.list).mockResolvedValue([
      dataset({ file_size: 25_600 }),
    ] as never)
    renderDashboard()
    await screen.findByText('sales')

    const table = screen.getByRole('table')
    const cell = within(table).getByText(
      (_t, node) => node?.tagName === 'TD' && node.textContent === `${LRI}25.0 KB${PDI}`)
    expect(cell).toBeInTheDocument()
    // The digits still precede the unit inside the isolate.
    expect(cell.textContent!.replace(LRI, '').replace(PDI, '')).toBe('25.0 KB')
  })

  it('applies to bytes and megabytes too, not just kilobytes', async () => {
    vi.mocked(datasetsApi.list).mockResolvedValue([
      dataset({ id: 1, name: 'tiny', file_size: 512 }),
      dataset({ id: 2, name: 'big', file_size: 5 * 1024 ** 2 }),
    ] as never)
    renderDashboard()
    await screen.findByText('tiny')

    const table = screen.getByRole('table')
    for (const expected of ['512 B', '5.0 MB']) {
      expect(within(table).getByText(
        (_t, node) => node?.tagName === 'TD' && node.textContent === `${LRI}${expected}${PDI}`))
        .toBeInTheDocument()
    }
  })
})

describe('paging through a long inventory', () => {
  // CLIENT-SIDE, of necessity: `GET /datasets` takes no page/limit/offset and
  // returns no total (routers/datasets.py::list_datasets), so the browser
  // already holds every row and slices what it shows. These tests describe the
  // behaviour a server-side version would have to keep.
  const many = (n: number) => Array.from({ length: n }, (_, i) =>
    dataset({ id: i + 1, name: `ds_${String(i + 1).padStart(2, '0')}` }))

  /** The footer sentence, built with the component's own number formatter:
   *  this suite runs under a locale where toLocaleString emits Arabic-Indic
   *  digits, so a hardcoded "1 to 8 of 19" matches nothing. */
  const showing = (from: number, to: number, total: number) =>
    `Showing ${from.toLocaleString()} to ${to.toLocaleString()} of `
    + `${total.toLocaleString()} datasets`

  const rowNames = () =>
    within(screen.getByRole('table')).getAllByRole('row')
      .slice(1)                                   // drop the header row
      .map(r => within(r).getAllByRole('cell')[0].textContent)

  it('shows only the first eight of nineteen', async () => {
    vi.mocked(datasetsApi.list).mockResolvedValue(many(19) as never)
    renderDashboard()
    await screen.findByText('ds_01')

    expect(rowNames()).toHaveLength(8)
    expect(screen.queryByText('ds_09')).toBeNull()
  })

  it('says which slice of the whole it is showing', async () => {
    vi.mocked(datasetsApi.list).mockResolvedValue(many(19) as never)
    renderDashboard()
    await screen.findByText('ds_01')
    expect(screen.getByText(showing(1, 8, 19))).toBeInTheDocument()
  })

  it('moves to the next page and counts from there', async () => {
    vi.mocked(datasetsApi.list).mockResolvedValue(many(19) as never)
    renderDashboard()
    await screen.findByText('ds_01')

    fireEvent.click(screen.getByRole('button', { name: 'Page 2' }))

    expect(rowNames()[0]).toBe('ds_09')
    expect(screen.queryByText('ds_01')).toBeNull()
    expect(screen.getByText(showing(9, 16, 19))).toBeInTheDocument()
  })

  it('counts the last page by what is actually on it, not by the page size', async () => {
    vi.mocked(datasetsApi.list).mockResolvedValue(many(19) as never)
    renderDashboard()
    await screen.findByText('ds_01')

    fireEvent.click(screen.getByRole('button', { name: 'Page 3' }))
    expect(rowNames()).toHaveLength(3)
    expect(screen.getByText(showing(17, 19, 19))).toBeInTheDocument()
  })

  it('disables Previous and Next at the ends rather than hiding them', async () => {
    // A control that vanishes moves everything beside it, and the reader has to
    // work out whether they ran out of pages or lost a button.
    vi.mocked(datasetsApi.list).mockResolvedValue(many(19) as never)
    renderDashboard()
    await screen.findByText('ds_01')

    const prev = () => screen.getByRole('button', { name: /Previous/ })
    const next = () => screen.getByRole('button', { name: /Next/ })

    expect(prev()).toBeDisabled()
    expect(next()).toBeEnabled()

    fireEvent.click(screen.getByRole('button', { name: 'Page 3' }))
    expect(prev()).toBeEnabled()
    expect(next()).toBeDisabled()
  })

  it('marks the current page for assistive tech', async () => {
    vi.mocked(datasetsApi.list).mockResolvedValue(many(19) as never)
    renderDashboard()
    await screen.findByText('ds_01')

    expect(screen.getByRole('button', { name: 'Page 1' })).toHaveAttribute('aria-current', 'page')
    fireEvent.click(screen.getByRole('button', { name: 'Page 2' }))
    expect(screen.getByRole('button', { name: 'Page 2' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('button', { name: 'Page 1' })).not.toHaveAttribute('aria-current')
  })

  it('returns to page 1 when the search changes', async () => {
    // Otherwise narrowing to three results while on page 3 shows an empty
    // table, which reads as "no matches" when there are three.
    vi.mocked(datasetsApi.list).mockResolvedValue(many(19) as never)
    renderDashboard()
    await screen.findByText('ds_01')

    fireEvent.click(screen.getByRole('button', { name: 'Page 3' }))
    // Matches ds_10 .. ds_19 -- ten rows, so two pages where there were three.
    fireEvent.change(screen.getByLabelText('Search datasets'), { target: { value: 'ds_1' } })

    expect(screen.getByRole('button', { name: 'Page 1' })).toHaveAttribute('aria-current', 'page')
    expect(rowNames()[0]).toBe('ds_10')
    expect(screen.getByText(showing(1, 8, 10))).toBeInTheDocument()
  })

  it('falls back to the last page that still exists when rows are deleted', async () => {
    // The search-reset effect does NOT cover this: the query never changes, so
    // nothing pushes you back to page 1. Deleting the only row on the last page
    // makes the page you are standing on cease to exist, and without a clamp
    // the table renders empty -- which reads as "no datasets" on a page with
    // sixteen of them.
    vi.mocked(datasetsApi.list).mockResolvedValue(many(17) as never)
    vi.mocked(datasetsApi.delete).mockResolvedValue(undefined as never)
    renderDashboard()
    await screen.findByText('ds_01')

    fireEvent.click(screen.getByRole('button', { name: 'Page 3' }))
    expect(rowNames()).toEqual(['ds_17'])

    fireEvent.click(screen.getByRole('button', { name: 'More actions for dataset ds_17' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Delete dataset' }))
    const dlg = await screen.findByRole('alertdialog')
    fireEvent.click(within(dlg).getByRole('button', { name: /Delete/i }))
    await waitFor(() => expect(datasetsApi.delete).toHaveBeenCalled())

    await waitFor(() => expect(rowNames()).toHaveLength(8))
    expect(screen.getByText(showing(9, 16, 16))).toBeInTheDocument()
  })

  it('shows no footer at all when there are no datasets', async () => {
    vi.mocked(datasetsApi.list).mockResolvedValue([] as never)
    renderDashboard()
    await screen.findByText('No datasets yet')
    expect(screen.queryByRole('navigation', { name: 'Dataset pages' })).toBeNull()
  })

  it('keeps the page out of the URL, which documents no query parameters', async () => {
    vi.mocked(datasetsApi.list).mockResolvedValue(many(19) as never)
    renderDashboard()
    await screen.findByText('ds_01')
    fireEvent.click(screen.getByRole('button', { name: 'Page 2' }))
    expect(window.location.search).toBe('')
  })
})

describe('the pager arrows mirror in Arabic', () => {
  /**
   * jsdom applies no stylesheet, so the rule itself is pinned by CONTENT --
   * the same technique svgDirection.test.ts uses for the Recharts direction
   * rule, and for the same reason.
   *
   * `dir` cannot fix a glyph: a chevron drawn pointing left keeps pointing
   * left on an RTL page, where "previous" is to the right. The layout mirrors
   * around it and the arrow ends up contradicting the button it sits in.
   */
  it('index.css flips the pager chevrons under dir=rtl', async () => {
    const fs = await import('node:fs')
    const path = await import('node:path')
    const url = await import('node:url')
    const here = path.dirname(url.fileURLToPath(import.meta.url))
    const css = fs.readFileSync(path.resolve(here, '../index.css'), 'utf8')

    const rule = css.match(/\[dir="rtl"\]\s*\.dl-pager__icon\s*\{[^}]*\}/)
    expect(rule, 'no [dir=rtl] .dl-pager__icon rule in index.css').toBeTruthy()
    expect(rule![0]).toMatch(/scaleX\(\s*-1\s*\)/)
  })

  it('renders the icon with the class that rule targets', async () => {
    vi.mocked(datasetsApi.list).mockResolvedValue(
      Array.from({ length: 19 }, (_, i) => dataset({ id: i + 1, name: `d${i}` })) as never)
    renderDashboard()
    await screen.findByText('d0')
    const prev = screen.getByRole('button', { name: /Previous/ })
    expect(prev.querySelector('.dl-pager__icon')).toBeTruthy()
  })
})
