import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { render, screen, fireEvent, within, waitFor, act } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import ReportBuilder from './ReportBuilder'
import { analysisApi, authzApi, reportsApi, datasetsApi, widgetDataApi, dataPreviewApi, dataSourcesApi } from '../services/api'
import { ConfirmProvider } from '../components/ui/ConfirmDialog'
import { axeViolations } from '../test/axe'

vi.mock('../services/api', () => ({
  // SubscribeButton sits in the always-visible header, so this page
  // renders it for every test here -- an unmocked call crashes them all.
  subscriptionApi: { get: vi.fn().mockResolvedValue({ subscribed: false }),
                     subscribe: vi.fn(), unsubscribe: vi.fn() },
  // Phase 7.3: the header asks what this user may do (share, download...).
  authzApi: { decisions: vi.fn().mockResolvedValue([]) },
  reportsApi: {
    get: vi.fn(), list: vi.fn().mockResolvedValue([]), update: vi.fn(), addPage: vi.fn(), updatePage: vi.fn(), deletePage: vi.fn(),
    addWidget: vi.fn(), updateWidget: vi.fn(), deleteWidget: vi.fn(),
    listBookmarks: vi.fn().mockResolvedValue([]), addBookmark: vi.fn(), deleteBookmark: vi.fn(),
    getRevision: vi.fn().mockResolvedValue(0),
    getClassification: vi.fn().mockResolvedValue({ label: null, options: [] }),
    setClassification: vi.fn(),
    addCommonFilter: vi.fn(), deleteCommonFilter: vi.fn(),
  },
  datasetsApi: { get: vi.fn(), list: vi.fn() },
  dataSourcesApi: { list: vi.fn().mockResolvedValue([]) },
  hierarchyApi: { get: vi.fn().mockResolvedValue([]) },
  analysisApi: { get: vi.fn().mockResolvedValue(null), run: vi.fn() },
  calcColumnsApi: { list: vi.fn().mockResolvedValue([]), save: vi.fn(), delete: vi.fn(), preview: vi.fn() },
  measuresApi: { list: vi.fn().mockResolvedValue([]), save: vi.fn(), delete: vi.fn(), preview: vi.fn() },
  customFunctionsApi: { list: vi.fn().mockResolvedValue([]), save: vi.fn(), delete: vi.fn(), preview: vi.fn() },
  columnFormatsApi: { get: vi.fn().mockResolvedValue({}), set: vi.fn() },
  dataPreviewApi: { query: vi.fn().mockResolvedValue({ columns: [], rows: [], total: 0 }) },
  prepApi: { get: vi.fn().mockResolvedValue([]), set: vi.fn(), preview: vi.fn() },
  dataViewsApi: { list: vi.fn().mockResolvedValue([]), save: vi.fn(), apply: vi.fn(), delete: vi.fn() },
  columnMetaApi: { get: vi.fn(), set: vi.fn() },
  // The field list's geography classification lists the org's uploaded
  // boundary sets. This mock is exhaustive: a missing export fails every
  // test in the file with a mock error rather than an import error.
  boundarySetsApi: { list: vi.fn().mockResolvedValue([]), get: vi.fn(), create: vi.fn(), remove: vi.fn() },
  translationsApi: { list: vi.fn().mockResolvedValue({}), save: vi.fn() },
  relationshipsApi: { list: vi.fn().mockResolvedValue([]), create: vi.fn(), delete: vi.fn() },
  widgetDataApi: { query: vi.fn().mockResolvedValue({ rows: [], sampled: false }) },
  themesApi: { list: vi.fn().mockResolvedValue([]), create: vi.fn(), delete: vi.fn() },
  parametersApi: { list: vi.fn().mockResolvedValue([]), save: vi.fn() },
  pageTemplatesApi: { builtins: vi.fn().mockResolvedValue([]), list: vi.fn().mockResolvedValue([]), saveFrom: vi.fn(), addFrom: vi.fn(), delete: vi.fn() },
  pageVisibilityApi: { roles: vi.fn().mockResolvedValue([]), get: vi.fn().mockResolvedValue({ role_ids: [] }), set: vi.fn() },
  schedulesApi: { list: vi.fn().mockResolvedValue([]), create: vi.fn(), delete: vi.fn(), runNow: vi.fn() },
  deliveriesApi: { list: vi.fn().mockResolvedValue([]) },
  COMMON_TIMEZONES: ['UTC', 'Asia/Riyadh'],
  widgetTemplatesApi: { list: vi.fn().mockResolvedValue([]), create: vi.fn(), delete: vi.fn() },
  columnsApi: { duplicate: vi.fn() },
}))

function baseReport() {
  return {
    id: 1, name: 'Sales', dataset_id: 10, additional_dataset_ids: [], created_at: '2026-01-01', updated_at: '2026-01-01',
    my_capability: 'data',
    pages: [{ id: 100, report_id: 1, name: 'Page 1', page_type: 'normal', position: 0, widgets: [], created_at: '2026-01-01', layout_mode: 'free' }],
  }
}

function reportWithWidget() {
  const r = baseReport()
  r.pages[0].widgets = [{
    id: 5, page_id: 100, widget_type: 'bar', title: 'Sales by Region', config: { dimension: 'region' },
    layout: { x: 0, y: 0, w: 6, h: 5 }, created_at: '2026-01-01',
  }] as any
  return r
}

/** The builder's left panel is tabbed (Fields / Charts / More); the widget
 *  catalog lives under Charts, templates and report filters under More. */
async function openLeftTab(name: 'Fields' | 'Charts' | 'More') {
  fireEvent.click(await screen.findByRole('tab', { name }))
}
// The chosen tab is remembered per viewer; a test that opened Charts must not
// leave the next one there.
beforeEach(() => { try { localStorage.removeItem('datalytics:builder-left-tab'); sessionStorage.removeItem('datalytics:open-reports') } catch { /* */ } })

function renderBuilder() {
  return render(
    // ConfirmProvider mirrors App.tsx: ReportBuilder's page delete asks through
    // useConfirm, which throws outside a provider by design rather than silently
    // never confirming.
    <ConfirmProvider>
      <MemoryRouter initialEntries={['/reports/1']}>
        <Routes><Route path="/reports/:id" element={<ReportBuilder />} /></Routes>
      </MemoryRouter>
    </ConfirmProvider>
  )
}

// Overflow panels (Selection, Tab order, Performance, Sync slicers, Bookmarks,
// Mobile layout, Report rules) live behind the toolbar's More menu.
function openOverflowPanel(name: RegExp) {
  fireEvent.click(screen.getByRole('button', { name: 'More panels' }))
  fireEvent.click(screen.getByRole('menuitem', { name }))
}

describe('ReportBuilder view switcher', () => {
  it('shows Report/Data/Model view icons and defaults to Report', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(baseReport() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    renderBuilder()
    const strip = within(await screen.findByTestId('view-strip'))
    expect(strip.getByRole('button', { name: /Report/i })).toBeInTheDocument()
    expect(strip.getByRole('button', { name: /Data/i })).toBeInTheDocument()
    expect(strip.getByRole('button', { name: /Model/i })).toBeInTheDocument()
  })

  it('switches to the Model view placeholder when clicked', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(baseReport() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    renderBuilder()
    const strip = within(await screen.findByTestId('view-strip'))
    fireEvent.click(strip.getByRole('button', { name: /Model/i }))
    expect(await screen.findByTestId('model-view')).toBeInTheDocument()
  })
})

describe('ReportBuilder page-size presets in Page Properties', () => {
  it('updates the active page size when a preset is chosen in the Page Properties panel', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(baseReport() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    vi.mocked(reportsApi.updatePage).mockResolvedValue({} as any)
    renderBuilder()
    await screen.findByTestId('view-strip')
    await screen.findByText('Page properties')

    fireEvent.click(screen.getByRole('button', { name: '4:3' }))

    await waitFor(() => expect(reportsApi.updatePage).toHaveBeenCalledWith(1, 100, expect.objectContaining({ page_size: '4:3' })), { timeout: 2000 })
  })
})

describe('ReportBuilder theme picker in the top bar', () => {
  it('applies the report theme on load and lets the user pick a different one from the top bar', async () => {
    const report = baseReport()
    ;(report as any).theme = 'default'
    vi.mocked(reportsApi.get).mockResolvedValue(report as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    vi.mocked(reportsApi.update).mockResolvedValue({ ...report, theme: 'ocean' } as any)
    renderBuilder()
    await screen.findByTestId('view-strip')

    fireEvent.click(screen.getByRole('button', { name: 'Ocean' }))

    expect(reportsApi.update).toHaveBeenCalledWith(1, { theme: 'ocean' })
  })
})

describe('ReportBuilder Data tab', () => {
  it('moves the Display Formats panel out of the always-visible sidebar and into the Data tab', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(baseReport() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [{ name: 'revenue', dtype: 'numeric' }] } as any)
    vi.mocked(dataPreviewApi.query).mockResolvedValue({ columns: ['revenue'], rows: [[100]], total: 1 })
    renderBuilder()
    await screen.findByTestId('view-strip')
    await screen.findAllByText('Sales Data')

    expect(screen.queryByText('Display Formats')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Data$/i }))
    expect(await screen.findByText('Display Formats')).toBeInTheDocument()
  })
})

describe('ReportBuilder header breadcrumb', () => {
  it('links the dataset and, for a source-backed dataset, the connection review page', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(baseReport() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [], data_source_id: 5 } as any)
    vi.mocked(dataSourcesApi.list).mockResolvedValue([{ id: 5, name: 'Prod Postgres', type: 'postgres', config: {}, created_at: '2026-01-01' }] as any)
    renderBuilder()
    await screen.findByTestId('view-strip')

    const datasetLink = await screen.findByRole('link', { name: 'Sales Data' })
    expect(datasetLink).toHaveAttribute('href', '/datasets/10')
    const sourceLink = await screen.findByRole('link', { name: 'Prod Postgres' })
    expect(sourceLink).toHaveAttribute('href', '/connections/5/review')
  })

  it('degrades to no source link for an upload with no data source', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(baseReport() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    renderBuilder()
    await screen.findByTestId('view-strip')

    expect(await screen.findByRole('link', { name: 'Sales Data' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /review/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Source' })).not.toBeInTheDocument()
  })
})

describe('ReportBuilder return to Widget panel', () => {
  it('keeps the selected widget remembered after closing the Selection pane', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(reportWithWidget() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
    renderBuilder()
    await screen.findByTestId('view-strip')

    fireEvent.click(screen.getByText('Sales by Region'))
    expect(await screen.findByText('Widget: Sales by Region')).toBeInTheDocument()

    openOverflowPanel(/Selection/i)
    expect(screen.queryByText('Widget: Sales by Region')).not.toBeInTheDocument()

    openOverflowPanel(/Selection/i)
    expect(await screen.findByText('Widget: Sales by Region')).toBeInTheDocument()
  })
})

describe('ReportBuilder right-panel object bar', () => {
  it('shows "Page: <name>" when no widget is selected, and switches to "Widget: <title>" on selection', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(reportWithWidget() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
    renderBuilder()
    await screen.findByTestId('view-strip')

    expect(await screen.findByText('Page: Page 1')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Sales by Region'))
    expect(await screen.findByText('Widget: Sales by Region')).toBeInTheDocument()
    expect(screen.queryByText('Page: Page 1')).not.toBeInTheDocument()
  })

  it('the x button deselects the widget, falling back to the page panel', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(reportWithWidget() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
    renderBuilder()
    await screen.findByTestId('view-strip')

    fireEvent.click(screen.getByText('Sales by Region'))
    await screen.findByText('Widget: Sales by Region')

    fireEvent.click(screen.getByRole('button', { name: 'Deselect widget' }))

    expect(screen.queryByText('Widget: Sales by Region')).not.toBeInTheDocument()
    expect(await screen.findByText('Page: Page 1')).toBeInTheDocument()
  })

  it('"Report settings" opens the parameters mode', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(reportWithWidget() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
    renderBuilder()
    await screen.findByTestId('view-strip')

    fireEvent.click(screen.getByRole('button', { name: 'Report settings' }))

    expect(await screen.findByText('Report parameters')).toBeInTheDocument()
  })
})

describe('ReportBuilder Tab order pane', () => {
  it('shows the Tab order pane and writes sequential tabIndex values on reorder', async () => {
    const report = reportWithWidget()
    ;(report.pages[0].widgets as any[]).push({ id: 6, page_id: 100, widget_type: 'bar', title: 'Second Widget', config: { dimension: 'region' }, layout: { x: 0, y: 5, w: 6, h: 5 }, created_at: '2026-01-01' })
    vi.mocked(reportsApi.get).mockResolvedValue(report as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
    vi.mocked(reportsApi.updateWidget).mockResolvedValue({} as any)
    renderBuilder()
    await screen.findByTestId('view-strip')

    openOverflowPanel(/Tab order/i)
    expect(await screen.findAllByTestId('tab-order-row')).toHaveLength(2)
  })
})

describe('ReportBuilder multi-select and Align/Distribute toolbar', () => {
  it('shift+click multi-selects widgets, and Align Left moves them all to the leftmost x', async () => {
    const report = reportWithWidget()
    ;(report.pages[0].widgets as any[]).push({ id: 6, page_id: 100, widget_type: 'bar', title: 'Second Widget', config: { dimension: 'region' }, layout: { x: 6, y: 0, w: 6, h: 5 }, created_at: '2026-01-01' })
    vi.mocked(reportsApi.get).mockResolvedValue(report as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
    vi.mocked(reportsApi.updateWidget).mockResolvedValue({} as any)
    renderBuilder()
    await screen.findByTestId('view-strip')
    fireEvent.click(await screen.findByText('Sales by Region'), { shiftKey: true })
    fireEvent.click(await screen.findByText('Second Widget'), { shiftKey: true })
    fireEvent.click(screen.getByRole('button', { name: /Align Left/i }))

    expect(reportsApi.updateWidget).toHaveBeenCalledWith(1, 100, 6, { layout: expect.objectContaining({ x: 0 }) })
  })
})

describe('ReportBuilder Performance panel', () => {
  it('shows a widget\'s query time after its data loads', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(reportWithWidget() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [{ name: 'A', value: 1 }], sampled: false })
    renderBuilder()
    await screen.findByTestId('view-strip')

    openOverflowPanel(/Performance/i)

    await waitFor(async () => expect((await screen.findAllByText('Sales by Region')).length).toBeGreaterThan(1))
    await screen.findByText(/ms/)
  })
})

describe('ReportBuilder concurrent-edit detection', () => {
  it('warns when another session has bumped the report revision', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue({ ...baseReport(), revision: 3 } as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    // A different session saved twice since we loaded.
    vi.mocked(reportsApi.getRevision).mockResolvedValue(5)
    renderBuilder()
    await screen.findByTestId('view-strip')

    expect(await screen.findByText(/changed in another session/i)).toBeInTheDocument()
  })

  it('stays quiet while the revision matches what we loaded', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue({ ...baseReport(), revision: 3 } as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    vi.mocked(reportsApi.getRevision).mockResolvedValue(3)
    renderBuilder()
    await screen.findByTestId('view-strip')

    await waitFor(() => expect(reportsApi.getRevision).toHaveBeenCalled())
    expect(screen.queryByText(/changed in another session/i)).not.toBeInTheDocument()
  })

  it('reloads the report when the warning is acted on', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue({ ...baseReport(), revision: 1 } as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    vi.mocked(reportsApi.getRevision).mockResolvedValue(9)
    renderBuilder()
    const banner = await screen.findByText(/changed in another session/i)
    const callsBefore = vi.mocked(reportsApi.get).mock.calls.length

    fireEvent.click(within(banner.closest('div')!).getByRole('button', { name: /Reload/i }))

    await waitFor(() => expect(vi.mocked(reportsApi.get).mock.calls.length).toBeGreaterThan(callsBefore))
  })
})

describe('ReportBuilder measure/category reclassification', () => {
  it('flips a numeric column to a category via the role override and moves its chip', async () => {
    const { columnMetaApi } = await import('../services/api')
    vi.mocked(reportsApi.get).mockResolvedValue(baseReport() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data',
      columns: [{ name: 'zip', dtype: 'numeric' }], column_meta: {} } as any)
    vi.mocked(columnMetaApi.set).mockResolvedValue({ zip: { role: 'category' } } as never)
    renderBuilder()
    await screen.findByTestId('view-strip')
    await screen.findAllByText('Sales Data')

    // numeric zip starts under Columns with a reclassify affordance
    fireEvent.click(await screen.findByLabelText('Reclassify zip as category'))
    await waitFor(() => expect(columnMetaApi.set).toHaveBeenCalledWith(10,
      { zip: { role: 'category' } }))
    // the returned override moves the chip: it now offers the reverse flip
    expect(await screen.findByLabelText('Reclassify zip as measure')).toBeInTheDocument()
  })
})

describe('ReportBuilder Fields pane', () => {
  function datasetWithColumns() {
    return {
      id: 10, name: 'Sales Data',
      columns: [
        { id: 1, name: 'region', dtype: 'text', missing_pct: 0, stats: {} },
        { id: 2, name: 'sales', dtype: 'numeric', missing_pct: 0, stats: {} },
      ],
    }
  }

  it('lists dataset columns grouped into Columns and Dimensions', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(reportWithWidget() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue(datasetWithColumns() as any)
    renderBuilder()
    await screen.findByTestId('view-strip')

    expect(await screen.findByText('Fields')).toBeInTheDocument()
    // Numeric columns sit under "Columns"; "Measures" is reserved for dataset measures,
    // which are post-aggregation expressions rather than aggregatable columns.
    expect(screen.getByText('Columns')).toBeInTheDocument()
    expect(screen.queryByText('Measures')).not.toBeInTheDocument()
    expect(screen.getByText('Dimensions')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^[#ƒx Aa]* ?sales$/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^[#ƒx Aa]* ?region$/ })).toBeInTheDocument()
  })

  it('assigns a clicked field to the selected widget\'s next open matching role', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(reportWithWidget() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue(datasetWithColumns() as any)
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
    vi.mocked(reportsApi.updateWidget).mockResolvedValue({} as any)
    renderBuilder()
    await screen.findByTestId('view-strip')

    fireEvent.click(screen.getByText('Sales by Region'))
    await screen.findByText('Widget: Sales by Region')

    fireEvent.click(screen.getByRole('button', { name: /^[#ƒx Aa]* ?sales$/ }))

    await waitFor(() => expect(reportsApi.updateWidget).toHaveBeenCalledWith(
      1, 100, 5, { config: expect.objectContaining({ dimension: 'region', measure: 'sales' }), title: 'Sales by Region' },
    ))
  })

  it('a second clicked field is ADDED to the config saved by the first, not swapped for it', async () => {
    // The selection used to be a stale snapshot, so the second click planned
    // from the pre-save config and sent {dimension} alone, wiping the measure.
    const first = reportWithWidget(); (first.pages[0].widgets[0] as any).config = {}
    const second = reportWithWidget(); (second.pages[0].widgets[0] as any).config = { measure: 'sales' }
    vi.mocked(reportsApi.get).mockResolvedValueOnce(first as any).mockResolvedValue(second as any)
    vi.mocked(datasetsApi.get).mockResolvedValue(datasetWithColumns() as any)
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
    vi.mocked(reportsApi.updateWidget).mockResolvedValue({} as any)
    renderBuilder()
    await screen.findByTestId('view-strip')
    fireEvent.click(await screen.findByText('Sales by Region', {}, { timeout: 3000 }))
    await screen.findByText('Widget: Sales by Region')

    fireEvent.click(screen.getByRole('button', { name: /^[#ƒx Aa]* ?sales$/ }))
    await waitFor(() => expect(reportsApi.updateWidget).toHaveBeenCalledWith(
      1, 100, 5, { config: expect.objectContaining({ measure: 'sales' }), title: 'Sales by Region' }))
    await waitFor(() => expect(vi.mocked(reportsApi.get).mock.calls.length).toBeGreaterThan(1))

    fireEvent.click(screen.getByRole('button', { name: /^[#ƒx Aa]* ?region$/ }))
    await waitFor(() => expect(reportsApi.updateWidget).toHaveBeenLastCalledWith(
      1, 100, 5, { config: expect.objectContaining({ measure: 'sales', dimension: 'region' }), title: 'Sales by Region' }))
  })

  it('lists dataset measures under their own heading, separate from numeric columns', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(reportWithWidget() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({
      ...datasetWithColumns(),
      measures: [{ name: 'Sales % of Total', expression: 'SUM(sales) / TOTAL(SUM(sales)) * 100' }],
    } as any)
    renderBuilder()
    await screen.findByTestId('view-strip')

    expect(await screen.findByText('Measures')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Sales % of Total/ })).toBeInTheDocument()
  })

  it('assigns a clicked measure to the selected widget\'s measure role', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(reportWithWidget() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({
      ...datasetWithColumns(),
      measures: [{ name: 'Margin', expression: 'SUM(profit) / SUM(sales) * 100' }],
    } as any)
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
    vi.mocked(reportsApi.updateWidget).mockResolvedValue({} as any)
    renderBuilder()
    await screen.findByTestId('view-strip')

    fireEvent.click(screen.getByText('Sales by Region'))
    await screen.findByText('Widget: Sales by Region')

    fireEvent.click(screen.getByRole('button', { name: /Margin/ }))

    await waitFor(() => expect(reportsApi.updateWidget).toHaveBeenCalledWith(
      1, 100, 5, { config: expect.objectContaining({ measure: 'Margin' }), title: 'Sales by Region' },
    ))
  })

  it('hides columns marked hidden in column_meta', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(reportWithWidget() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({
      ...datasetWithColumns(),
      column_meta: { sales: { hidden: true } },
    } as any)
    renderBuilder()
    await screen.findByTestId('view-strip')
    await screen.findByText('Fields')

    expect(screen.getByRole('button', { name: /^[#ƒx Aa]* ?region$/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^[#ƒx Aa]* ?sales$/ })).not.toBeInTheDocument()
  })

  it('groups a numeric column under Dimensions when column_meta overrides its role', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(reportWithWidget() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({
      ...datasetWithColumns(),
      // A ZIP code is stored numeric but is really a category.
      columns: [
        { id: 1, name: 'region', dtype: 'text', missing_pct: 0, stats: {} },
        { id: 2, name: 'zip', dtype: 'numeric', missing_pct: 0, stats: {} },
      ],
      column_meta: { zip: { role: 'category' } },
    } as any)
    renderBuilder()
    await screen.findByTestId('view-strip')
    await screen.findByText('Fields')

    // No numeric columns remain, so the Columns group should not render at all.
    expect(screen.queryByText('Columns')).not.toBeInTheDocument()
    expect(screen.getByText('Dimensions')).toBeInTheDocument()
  })

  it('shows the column_meta label instead of the raw column name', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(reportWithWidget() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({
      ...datasetWithColumns(),
      column_meta: { sales: { label: 'Net Revenue' } },
    } as any)
    renderBuilder()
    await screen.findByTestId('view-strip')
    await screen.findByText('Fields')

    expect(screen.getByRole('button', { name: /Net Revenue/ })).toBeInTheDocument()
  })

  it('applies the column_meta default aggregation when assigning a field', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(reportWithWidget() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({
      ...datasetWithColumns(),
      column_meta: { sales: { aggregation: 'avg' } },
    } as any)
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
    vi.mocked(reportsApi.updateWidget).mockResolvedValue({} as any)
    renderBuilder()
    await screen.findByTestId('view-strip')

    fireEvent.click(screen.getByText('Sales by Region'))
    await screen.findByText('Widget: Sales by Region')
    fireEvent.click(screen.getByRole('button', { name: /^[#ƒx Aa]* ?sales$/ }))

    await waitFor(() => expect(reportsApi.updateWidget).toHaveBeenCalledWith(
      1, 100, 5,
      { config: expect.objectContaining({ measure: 'sales', aggregation: 'avg' }), title: 'Sales by Region' },
    ))
  })

  it('does nothing when a field is clicked with no widget selected', async () => {
    vi.mocked(reportsApi.updateWidget).mockClear()
    vi.mocked(reportsApi.get).mockResolvedValue(reportWithWidget() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue(datasetWithColumns() as any)
    renderBuilder()
    await screen.findByTestId('view-strip')

    fireEvent.click(screen.getByRole('button', { name: /^[#ƒx Aa]* ?sales$/ }))
    expect(reportsApi.updateWidget).not.toHaveBeenCalled()
  })
})

describe('ReportBuilder Selection pane', () => {
  it('hides a widget marked hidden in View mode but still shows it dimmed in Edit mode', async () => {
    const report = reportWithWidget()
    ;(report.pages[0].widgets[0] as any).config = { dimension: 'region', hidden: true }
    vi.mocked(reportsApi.get).mockResolvedValue(report as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    renderBuilder()
    await screen.findByTestId('view-strip')

    expect(screen.getByText('Sales by Region')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'View mode' }))
    expect(screen.queryByText('Sales by Region')).not.toBeInTheDocument()
  })

  it('shows the Selection pane in the right panel when toggled', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(reportWithWidget() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    renderBuilder()
    await screen.findByTestId('view-strip')
    openOverflowPanel(/Selection/i)
    // The widget still renders on the canvas behind the panel, plus now once more in the Selection pane's list.
    expect(screen.getAllByText('Sales by Region').length).toBeGreaterThanOrEqual(2)
  })
})

describe('ReportBuilder Sync slicers pane', () => {
  it('toggling a slicer to All pages calls setInteraction with syncAllPages true', async () => {
    const report = reportWithWidget()
    report.pages[0].widgets = [{ id: 9, page_id: 100, widget_type: 'slicer', title: 'Region filter', config: { dimension: 'region' }, layout: { x: 0, y: 0, w: 3, h: 5 }, created_at: '2026-01-01' }] as any
    vi.mocked(reportsApi.get).mockResolvedValue(report as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
    renderBuilder()
    await screen.findByTestId('view-strip')

    openOverflowPanel(/Sync slicers/i)
    fireEvent.click(await screen.findByRole('button', { name: /This page only/i }))
    expect(screen.getByRole('button', { name: /All pages/i })).toBeInTheDocument()
  })
})

describe('ReportBuilder Bookmarks', () => {
  it('applying a bookmark switches page, restores prompt values, and restores hidden widgets', async () => {
    const report = reportWithWidget()
    const detailWidget = { id: 20, page_id: 200, widget_type: 'bar', title: 'Detail Chart', config: { dimension: 'region' }, layout: { x: 0, y: 0, w: 6, h: 5 }, created_at: '2026-01-01' }
    report.pages.push({ id: 200, report_id: 1, name: 'Details', page_type: 'normal', position: 1,
      prompt_column: 'region', prompt_label: 'Region', widgets: [detailWidget], created_at: '2026-01-01' } as any)
    vi.mocked(reportsApi.get).mockResolvedValue(report as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
    vi.mocked(reportsApi.updateWidget).mockResolvedValue({} as any)
    vi.mocked(reportsApi.listBookmarks).mockResolvedValue([{
      id: 1, report_id: 1, name: 'Q1 view', position: 0,
      state: { pageId: 200, activeFilters: [], promptValues: { 200: 'North' }, hiddenWidgetIds: [20] },
      created_at: '2026-01-01',
    }] as any)
    renderBuilder()
    await screen.findByTestId('view-strip')

    openOverflowPanel(/Bookmarks/i)
    fireEvent.click(await screen.findByText('Q1 view'))

    const promptInput = await screen.findByPlaceholderText('Enter region...')
    expect(promptInput).toHaveValue('North')
    await waitFor(() => expect(reportsApi.updateWidget).toHaveBeenCalledWith(
      1, 200, 20, { config: expect.objectContaining({ hidden: true }) }
    ))
  })
})

describe('ReportBuilder mobile layout editor', () => {
  it('shows the mobile layout editor in the right panel when toggled', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(reportWithWidget() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    renderBuilder()
    await screen.findByTestId('view-strip')

    openOverflowPanel(/Mobile layout/i)
    expect(await screen.findByTestId('mobile-layout-row')).toHaveTextContent('Sales by Region')
  })

  it('renders widgets as a stacked single column on a narrow viewport in view mode', async () => {
    const report = reportWithWidget()
    ;(report.pages[0] as any).mobile_layout = { order: [5], hidden: [] }
    vi.mocked(reportsApi.get).mockResolvedValue(report as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    const realMatchMedia = window.matchMedia
    window.matchMedia = (query: string) => ({
      matches: query.includes('max-width'), media: query, onchange: null,
      addListener: () => {}, removeListener: () => {},
      addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => false,
    }) as unknown as MediaQueryList

    renderBuilder()
    await screen.findByTestId('view-strip')
    fireEvent.click(screen.getByRole('button', { name: 'View mode' }))

    expect(await screen.findByTestId('mobile-stack')).toBeInTheDocument()
    window.matchMedia = realMatchMedia
  })
})

describe('ReportBuilder drillthrough navigation', () => {
  it('clicking Drill through switches to the target page with the clicked value seeded as its prompt filter', async () => {
    const report = baseReport()
    report.pages[0].widgets = [{
      id: 5, page_id: 100, widget_type: 'list', title: 'Regions', config: { dimension: 'region', drillthroughPageId: 200 },
      layout: { x: 0, y: 0, w: 6, h: 5 }, created_at: '2026-01-01',
    }] as any
    report.pages.push({
      id: 200, report_id: 1, name: 'Details', page_type: 'drillthrough', position: 1,
      prompt_column: 'region', prompt_label: 'Region', widgets: [], created_at: '2026-01-01',
    } as any)
    vi.mocked(reportsApi.get).mockResolvedValue(report as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [{ name: 'North', value: 5 }], sampled: false })

    renderBuilder()
    await screen.findByTestId('view-strip')

    const row = await screen.findByText('North')
    fireEvent.click(row)
    const drillBtn = await screen.findByRole('button', { name: /Drill through/i })
    fireEvent.click(drillBtn)

    const promptInput = await screen.findByPlaceholderText('Enter region...')
    expect(promptInput).toHaveValue('North')
  })

  it('never shows a drillthrough page as a tab -- it is reachable only by drilling', async () => {
    const report = baseReport()
    report.pages[0].widgets = [{
      id: 5, page_id: 100, widget_type: 'list', title: 'Regions', config: { dimension: 'region', drillthroughPageId: 200 },
      layout: { x: 0, y: 0, w: 6, h: 5 }, created_at: '2026-01-01',
    }] as any
    report.pages.push({
      id: 200, report_id: 1, name: 'Details', page_type: 'drillthrough', position: 1,
      prompt_column: 'region', prompt_label: 'Region', widgets: [], created_at: '2026-01-01',
    } as any)
    vi.mocked(reportsApi.get).mockResolvedValue(report as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [{ name: 'North', value: 5 }], sampled: false })

    renderBuilder()
    await screen.findByTestId('view-strip')
    // Absent as a tab in edit mode...
    expect(screen.queryByRole('button', { name: 'Details' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'View mode' }))
    // ...and absent in view mode too.
    expect(screen.queryByRole('button', { name: 'Details' })).not.toBeInTheDocument()
  })

  it('a report with no drillthrough pages behaves exactly as before -- no drill-through affordance appears', async () => {
    const report = baseReport()
    report.pages[0].widgets = [{
      id: 5, page_id: 100, widget_type: 'list', title: 'Regions', config: { dimension: 'region' },
      layout: { x: 0, y: 0, w: 6, h: 5 }, created_at: '2026-01-01',
    }] as any
    vi.mocked(reportsApi.get).mockResolvedValue(report as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [{ name: 'North', value: 5 }], sampled: false })

    renderBuilder()
    await screen.findByTestId('view-strip')

    const row = await screen.findByText('North')
    fireEvent.click(row)

    expect(screen.queryByRole('button', { name: /Drill through/i })).not.toBeInTheDocument()
  })
})

describe('ReportBuilder popup overlay (view mode)', () => {
  function popupReport() {
    const report = baseReport()
    report.pages[0].widgets = [{
      id: 5, page_id: 100, widget_type: 'button', title: 'Open KPIs',
      config: { label: 'Open KPIs', action: 'navigate', actionPageId: 300 },
      layout: { x: 0, y: 0, w: 3, h: 3 }, created_at: '2026-01-01',
    }] as any
    report.pages.push({
      id: 300, report_id: 1, name: 'Popup KPIs', page_type: 'popup', position: 1,
      widgets: [{
        id: 6, page_id: 300, widget_type: 'text', title: 'Popup body',
        config: { content: 'Popup content' }, layout: { x: 0, y: 0, w: 6, h: 3 }, created_at: '2026-01-01',
      }],
      created_at: '2026-01-01',
    } as any)
    return report
  }

  function enterViewMode() {
    fireEvent.click(screen.getByRole('button', { name: 'View mode' }))
  }

  it('renders the popup page as a centred overlay instead of switching the active tab', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(popupReport() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    renderBuilder()
    await screen.findByTestId('view-strip')
    enterViewMode()

    // The underlying page (Page 1) is still what's active -- its button stays mounted.
    const openBtn = await screen.findByRole('button', { name: 'Open KPIs' })
    fireEvent.click(openBtn)

    const overlay = await screen.findByTestId('popup-overlay')
    expect(overlay).toBeInTheDocument()
    expect(overlay).toHaveTextContent('Popup content')
    // The underlying page's own widget is still in the DOM behind the overlay --
    // navigating to the popup did NOT switch the active tab away from Page 1.
    expect(screen.getByRole('button', { name: 'Open KPIs' })).toBeInTheDocument()
  })

  it('closes the overlay on Escape and returns to the underlying page', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(popupReport() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    renderBuilder()
    await screen.findByTestId('view-strip')
    enterViewMode()
    fireEvent.click(await screen.findByRole('button', { name: 'Open KPIs' }))
    await screen.findByTestId('popup-overlay')

    fireEvent.keyDown(document, { key: 'Escape' })

    await waitFor(() => expect(screen.queryByTestId('popup-overlay')).not.toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Open KPIs' })).toBeInTheDocument()
  })

  it('closes the overlay via the close button', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(popupReport() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    renderBuilder()
    await screen.findByTestId('view-strip')
    enterViewMode()
    fireEvent.click(await screen.findByRole('button', { name: 'Open KPIs' }))
    await screen.findByTestId('popup-overlay')

    fireEvent.click(screen.getByRole('button', { name: 'Close' }))

    await waitFor(() => expect(screen.queryByTestId('popup-overlay')).not.toBeInTheDocument())
  })

  it('a double-click drill to a pop-up page opens it over the page, seeded with the clicked value', async () => {
    const report = popupReport()
    report.pages[0].widgets = [{
      id: 7, page_id: 100, widget_type: 'list', title: 'Regions',
      config: { dimension: 'region', drillthroughPageId: 300 },
      layout: { x: 0, y: 0, w: 4, h: 4 }, created_at: '2026-01-01',
    }] as any
    ;(report.pages[1] as any).prompt_column = 'region'
    vi.mocked(reportsApi.get).mockResolvedValue(report as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [{ name: 'North', value: 5 }], sampled: false } as any)
    renderBuilder()
    await screen.findByTestId('view-strip')
    enterViewMode()
    const row = await screen.findByText('North')
    fireEvent.click(row)
    fireEvent.doubleClick(row)
    const overlay = await screen.findByTestId('popup-overlay')
    expect(overlay).toHaveTextContent('Popup content')
    // Still on Page 1 underneath.
    expect(screen.getByText('North')).toBeInTheDocument()
  })

  it('excludes popup pages from the view-mode tab strip', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(popupReport() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    renderBuilder()
    await screen.findByTestId('view-strip')
    enterViewMode()

    expect(screen.queryByRole('button', { name: 'Popup KPIs' })).not.toBeInTheDocument()
  })

  it('still shows the popup page as a tab (with the [P] badge) in edit mode, and navigating switches to it', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(popupReport() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    renderBuilder()
    await screen.findByTestId('view-strip')
    // Default state is edit mode.
    expect(screen.getByRole('button', { name: /Popup KPIs.*\[P\]/ })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Open KPIs' }))

    // Edit mode: this is a plain tab switch, never an overlay.
    expect(screen.queryByTestId('popup-overlay')).not.toBeInTheDocument()
    expect(await screen.findByText('Popup content')).toBeInTheDocument()
  })

  it('leaves non-popup navigation unchanged in view mode', async () => {
    const report = baseReport()
    report.pages[0].widgets = [{
      id: 5, page_id: 100, widget_type: 'button', title: 'Go to Page 2',
      config: { label: 'Go to Page 2', action: 'navigate', actionPageId: 400 },
      layout: { x: 0, y: 0, w: 3, h: 3 }, created_at: '2026-01-01',
    }] as any
    report.pages.push({
      id: 400, report_id: 1, name: 'Page 2', page_type: 'normal', position: 1,
      widgets: [{
        id: 7, page_id: 400, widget_type: 'text', title: 'Page 2 body',
        config: { content: 'Second page content' }, layout: { x: 0, y: 0, w: 6, h: 3 }, created_at: '2026-01-01',
      }],
      created_at: '2026-01-01',
    } as any)
    vi.mocked(reportsApi.get).mockResolvedValue(report as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    renderBuilder()
    await screen.findByTestId('view-strip')
    enterViewMode()

    fireEvent.click(await screen.findByRole('button', { name: 'Go to Page 2' }))

    expect(screen.queryByTestId('popup-overlay')).not.toBeInTheDocument()
    expect(await screen.findByText('Second page content')).toBeInTheDocument()
    // It really switched tabs away from Page 1 -- the button that triggered it is gone.
    expect(screen.queryByRole('button', { name: 'Go to Page 2' })).not.toBeInTheDocument()
  })
})

describe('ReportBuilder tooltip page hover (view mode)', () => {
  function tooltipReport(bound = true) {
    const report = baseReport()
    report.pages[0].widgets = [{
      id: 5, page_id: 100, widget_type: 'text', title: 'Main widget',
      config: { content: 'Main body', ...(bound ? { tooltipPageId: 300 } : {}) },
      layout: { x: 0, y: 0, w: 6, h: 3 }, created_at: '2026-01-01',
    }] as any
    report.pages.push({
      id: 300, report_id: 1, name: 'Hover detail', page_type: 'tooltip', position: 1,
      widgets: [{
        id: 6, page_id: 300, widget_type: 'text', title: 'Tip body',
        config: { content: 'Tooltip content' }, layout: { x: 0, y: 0, w: 6, h: 3 }, created_at: '2026-01-01',
      }],
      created_at: '2026-01-01',
    } as any)
    return report
  }

  function enterViewMode() {
    fireEvent.click(screen.getByRole('button', { name: 'View mode' }))
  }

  async function widgetWrapper() {
    const el = await screen.findByText('Main body')
    return el.closest('[data-widget-id]') as HTMLElement
  }

  afterEach(() => { vi.useRealTimers() })

  it('renders the bound tooltip page in a floating panel after a hover delay', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(tooltipReport() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    renderBuilder()
    await screen.findByTestId('view-strip')
    enterViewMode()
    const el = await widgetWrapper()

    vi.useFakeTimers()
    fireEvent.mouseEnter(el, { clientX: 50, clientY: 60 })
    expect(screen.queryByText('Tooltip content')).not.toBeInTheDocument()
    act(() => { vi.advanceTimersByTime(300) })
    expect(screen.getByText('Tooltip content')).toBeInTheDocument()
  })

  it('dismisses the tooltip page on mouseleave', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(tooltipReport() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    renderBuilder()
    await screen.findByTestId('view-strip')
    enterViewMode()
    const el = await widgetWrapper()

    vi.useFakeTimers()
    fireEvent.mouseEnter(el)
    act(() => { vi.advanceTimersByTime(300) })
    expect(screen.getByText('Tooltip content')).toBeInTheDocument()

    fireEvent.mouseLeave(el)
    expect(screen.queryByText('Tooltip content')).not.toBeInTheDocument()
  })

  it('cancels the pending hover timer if the mouse leaves before the delay elapses', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(tooltipReport() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    renderBuilder()
    await screen.findByTestId('view-strip')
    enterViewMode()
    const el = await widgetWrapper()

    vi.useFakeTimers()
    fireEvent.mouseEnter(el)
    fireEvent.mouseLeave(el)
    act(() => { vi.advanceTimersByTime(300) })
    expect(screen.queryByText('Tooltip content')).not.toBeInTheDocument()
  })

  it('does nothing for a widget with no tooltipPageId bound', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(tooltipReport(false) as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    renderBuilder()
    await screen.findByTestId('view-strip')
    enterViewMode()
    const el = await widgetWrapper()

    vi.useFakeTimers()
    fireEvent.mouseEnter(el)
    act(() => { vi.advanceTimersByTime(500) })
    expect(screen.queryByText('Tooltip content')).not.toBeInTheDocument()
  })

  it('does nothing in edit mode', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(tooltipReport() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    renderBuilder()
    await screen.findByTestId('view-strip')
    // Default state is edit mode -- stay there.
    const el = await widgetWrapper()

    vi.useFakeTimers()
    fireEvent.mouseEnter(el)
    act(() => { vi.advanceTimersByTime(500) })
    expect(screen.queryByText('Tooltip content')).not.toBeInTheDocument()
  })

  it('excludes tooltip pages from the view-mode tab strip', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(tooltipReport() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    renderBuilder()
    await screen.findByTestId('view-strip')
    enterViewMode()

    expect(screen.queryByRole('button', { name: 'Hover detail' })).not.toBeInTheDocument()
  })
})

describe('ReportBuilder zoom-aware drag math', () => {
  it('computes the dropped grid position correctly when the canvas is zoomed, not just at 100%', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(reportWithWidget() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    vi.mocked(reportsApi.updateWidget).mockClear()
    vi.mocked(reportsApi.updateWidget).mockResolvedValue({} as any)
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })

    const realRect = Element.prototype.getBoundingClientRect
    Element.prototype.getBoundingClientRect = vi.fn(() => ({
      left: 0, top: 0, right: 900, bottom: 600, width: 900, height: 600, x: 0, y: 0, toJSON: () => {},
    })) as any

    try {
      renderBuilder()
      await screen.findByTestId('view-strip')

      const zoomIn = screen.getByRole('button', { name: '+' })
      for (let i = 0; i < 5; i++) fireEvent.click(zoomIn)
      expect(screen.getByText('150%')).toBeInTheDocument()

      const dragHandle = screen.getByText('⠿').closest('div') as HTMLElement
      fireEvent.mouseDown(dragHandle, { clientX: 0, clientY: 0 })
      // 1 grid column at 150% zoom, expressed in real screen pixels the mouse moved.
      fireEvent.mouseMove(window, { clientX: 113.5, clientY: 0 })
      fireEvent.mouseUp(window)

      await waitFor(() => expect(reportsApi.updateWidget).toHaveBeenCalled())
      const [, , , data] = vi.mocked(reportsApi.updateWidget).mock.calls[0]
      expect((data as any).layout.x).toBe(1)
    } finally {
      Element.prototype.getBoundingClientRect = realRect
    }
  })
})

describe('ReportBuilder status bar zoom', () => {
  it('zooms the canvas in and updates the displayed percentage', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(baseReport() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    renderBuilder()
    await screen.findByTestId('view-strip')

    expect(screen.getByText('100%')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '+' }))
    expect(screen.getByText('110%')).toBeInTheDocument()
  })
})

describe('ReportBuilder widget catalog in the left sidebar', () => {
  it('puts the widget catalog in the sidebar and adds a widget when clicked', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(baseReport() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    vi.mocked(reportsApi.addWidget).mockResolvedValue({
      id: 999, page_id: 100, widget_type: 'bar', title: 'Bar Chart', config: {},
      layout: { x: 0, y: 0, w: 6, h: 5 }, created_at: '2026-01-01',
    } as any)
    renderBuilder()
    await openLeftTab('Charts')
    await screen.findByTestId('view-strip')

    fireEvent.click(screen.getByRole('button', { name: /Bar Chart/i }))

    expect(reportsApi.addWidget).toHaveBeenCalledWith(1, 100, expect.objectContaining({ widget_type: 'bar' }))
  })

  it('shows the new widget on a packed empty page without a false conflict banner', async () => {
    // Executive packing runs on a new dashboard, then adding the first chart
    // used to bump the server revision without reloading local state. The
    // canvas stayed empty and the poll treated our own write as "another session".
    const widget = {
      id: 999, page_id: 100, widget_type: 'bar', title: 'Bar Chart', config: {},
      layout: { x: 0, y: 0, w: 6, h: 5 }, created_at: '2026-01-01',
    }
    const packedEmpty = {
      ...baseReport(),
      revision: 1,
      pages: [{ ...baseReport().pages[0], layout_mode: 'packed', layout_template: 'executive', widgets: [] }],
    }
    const packedWithBar = {
      ...packedEmpty,
      revision: 2,
      pages: [{ ...packedEmpty.pages[0], widgets: [widget] }],
    }
    vi.mocked(reportsApi.get).mockResolvedValue(packedEmpty as any)
    vi.mocked(reportsApi.getRevision).mockResolvedValue(1)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    vi.mocked(reportsApi.addWidget).mockImplementation(async () => {
      vi.mocked(reportsApi.getRevision).mockResolvedValue(2)
      vi.mocked(reportsApi.get).mockResolvedValue(packedWithBar as any)
      return widget as any
    })
    renderBuilder()
    await openLeftTab('Charts')
    await screen.findByTestId('view-strip')

    fireEvent.click(screen.getByRole('button', { name: /Bar Chart/i }))

    await waitFor(() => expect(document.querySelector('[data-widget-id="999"]')).toBeTruthy())
    expect(screen.queryByText(/changed in another session/i)).not.toBeInTheDocument()
  })
})

describe('ReportBuilder Present', () => {
  it('hides edit chrome and marks the document as presenting', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(reportWithWidget() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    renderBuilder()
    await screen.findByTestId('view-strip')

    fireEvent.click(screen.getByRole('button', { name: /Present/i }))

    expect(document.documentElement.dataset.presenting).toBe('1')
    expect(screen.queryByText('Analytics')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Stop/i })).toBeInTheDocument()
  })
})

describe('ReportBuilder report-level display rules', () => {
  it('persists report-level rules through reportsApi.update', async () => {
    const report = baseReport()
    vi.mocked(reportsApi.get).mockResolvedValue(report as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    vi.mocked(reportsApi.update).mockResolvedValue({ ...report, display_rules: [] } as any)
    renderBuilder()
    await screen.findByTestId('view-strip')

    await screen.findByRole('button', { name: 'More panels' }); openOverflowPanel(/report rules/i)
    fireEvent.click(screen.getByRole('button', { name: /add rule/i }))

    await waitFor(() => expect(reportsApi.update).toHaveBeenCalledWith(
      1,
      expect.objectContaining({ display_rules: expect.any(Array) }),
    ))
  })

  // Covers the other half: a report-level rule must actually reach the widget's own
  // query, merged ahead of the widget's own rules (WidgetRenderer.tsx builds
  // cfg.display_rules = [...reportDisplayRules, ...widgetRules]). The prior test only
  // asserted persistence and would stay green even if reportDisplayRules were dropped
  // from both <WidgetRenderer> call sites in ReportBuilder.tsx -- this one would not.
  it('merges a report-level rule into the config a widget sends to widgetDataApi.query', async () => {
    const reportRule = {
      id: 'report-rule-1', kind: 'expression', target: 'mark',
      column: 'value', condition: { op: 'gt', value: 0 },
      expression: 'value > 0', style: { fill: '#f87171' },
    }
    const report = reportWithWidget()
    ;(report as any).display_rules = [reportRule]
    vi.mocked(reportsApi.get).mockResolvedValue(report as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
    // widgetDataApi.query is shared across every test in this file and is never
    // cleared, so a call count snapshotted before render (rather than
    // toHaveBeenCalled(), which would trivially already be true) is what lets us
    // wait for THIS test's fetch, and reading the last call afterward is what lets
    // us read THIS test's config rather than some earlier test's.
    const callsBefore = vi.mocked(widgetDataApi.query).mock.calls.length
    renderBuilder()
    await screen.findByTestId('view-strip')
    await screen.findByText('Sales by Region')

    await waitFor(() => expect(vi.mocked(widgetDataApi.query).mock.calls.length).toBeGreaterThan(callsBefore))

    const calls = vi.mocked(widgetDataApi.query).mock.calls
    const [, lastConfig] = calls[calls.length - 1]
    expect((lastConfig as any).display_rules).toEqual(
      expect.arrayContaining([expect.objectContaining({ id: 'report-rule-1' })]),
    )
  })

  // Report-level rule edits are debounced ~600ms before persisting (see the block
  // comment above updateReportDisplayRules in ReportBuilder.tsx). Unmounting inside
  // that window -- e.g. the author edits a rule and immediately navigates away --
  // must flush the pending write rather than cancel it, or the edit that local state
  // already showed as applied is silently lost.
  it('flushes a pending report-rules write on unmount instead of dropping it', async () => {
    const report = baseReport()
    vi.mocked(reportsApi.get).mockResolvedValue(report as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    vi.mocked(reportsApi.update).mockClear()
    vi.mocked(reportsApi.update).mockResolvedValue({ ...report, display_rules: [] } as any)
    const { unmount } = renderBuilder()
    await screen.findByTestId('view-strip')

    await screen.findByRole('button', { name: 'More panels' }); openOverflowPanel(/report rules/i)
    fireEvent.click(screen.getByRole('button', { name: /add rule/i }))

    // Unmount immediately -- well inside the 600ms debounce window -- rather than
    // waiting for the timer to fire on its own.
    unmount()

    expect(reportsApi.update).toHaveBeenCalledWith(
      1,
      expect.objectContaining({
        display_rules: expect.arrayContaining([expect.objectContaining({ column: 'name' })]),
      }),
    )
  })
})

describe('ReportBuilder object templates', () => {
  it('inserts a new widget carrying the template type and config', async () => {
    const { widgetTemplatesApi } = await import('../services/api')
    vi.mocked(widgetTemplatesApi.list).mockResolvedValue([
      { id: 7, name: 'My Bar', widget_type: 'bar', config: { dimension: 'region', measure: 'sales' } },
    ])
    vi.mocked(reportsApi.addWidget).mockResolvedValue({
      id: 99, page_id: 100, widget_type: 'bar', title: 'My Bar',
      config: { dimension: 'region', measure: 'sales' }, layout: { x: 0, y: 0, w: 6, h: 5 }, created_at: '2026-01-01',
    } as any)
    renderBuilder()
    await openLeftTab('More')

    const tpl = await screen.findByRole('button', { name: 'My Bar' })
    fireEvent.click(tpl)

    await waitFor(() => expect(reportsApi.addWidget).toHaveBeenCalledWith(
      1, 100,
      expect.objectContaining({
        widget_type: 'bar',
        title: 'My Bar',
        config: expect.objectContaining({ dimension: 'region', measure: 'sales' }),
      }),
    ))
  })
})

describe('ReportBuilder sensitivity classification', () => {
  it('sets a report classification through the label picker', async () => {
    vi.mocked(reportsApi.setClassification).mockResolvedValue({ ...baseReport(), classification: 'Confidential' } as any)
    renderBuilder()
    await screen.findByTestId('view-strip')

    const picker = await screen.findByLabelText('Sensitivity label')
    fireEvent.change(picker, { target: { value: 'Confidential' } })

    await waitFor(() => expect(reportsApi.setClassification).toHaveBeenCalledWith(1, 'Confidential'))
    // the badge reflects the new label
    await waitFor(() => expect(screen.getAllByText('Confidential').length).toBeGreaterThan(0))
  })
})

describe('ReportBuilder report-level common filters', () => {
  it('adds a common filter that then travels to widgets as reportFilters', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(baseReport() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales', columns: [{ name: 'region', dtype: 'text' }] } as any)
    vi.mocked(reportsApi.addCommonFilter).mockResolvedValue({ id: 9, column: 'region', op: 'eq', value: 'North' })
    renderBuilder()
    await openLeftTab('More')
    await screen.findByTestId('view-strip')

    fireEvent.change(await screen.findByLabelText('Report filter column'), { target: { value: 'region' } })
    fireEvent.change(screen.getByLabelText('Report filter value'), { target: { value: 'North' } })
    fireEvent.click(screen.getByRole('button', { name: '+ Add report filter' }))

    await waitFor(() => expect(reportsApi.addCommonFilter).toHaveBeenCalledWith(1, { column: 'region', op: 'eq', value: 'North' }))
    // the active filter chip is shown
    await waitFor(() => expect(screen.getByText(/region eq North/)).toBeInTheDocument())
  })

  it('parses a comma list into an array for the in operator', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(baseReport() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales', columns: [{ name: 'region', dtype: 'text' }] } as any)
    vi.mocked(reportsApi.addCommonFilter).mockResolvedValue({ id: 10, column: 'region', op: 'in', value: ['A', 'B'] })
    renderBuilder()
    await openLeftTab('More')
    await screen.findByTestId('view-strip')

    fireEvent.change(await screen.findByLabelText('Report filter column'), { target: { value: 'region' } })
    fireEvent.change(screen.getByLabelText('Report filter operator'), { target: { value: 'in' } })
    fireEvent.change(screen.getByLabelText('Report filter value'), { target: { value: 'A, B' } })
    fireEvent.click(screen.getByRole('button', { name: '+ Add report filter' }))

    await waitFor(() => expect(reportsApi.addCommonFilter).toHaveBeenCalledWith(1, { column: 'region', op: 'in', value: ['A', 'B'] }))
  })

  it('adds a relative date report filter as a spec, and catches up on its own revision bump', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue({ ...baseReport(), revision: 3 } as any)
    vi.mocked(reportsApi.getRevision).mockResolvedValue(3)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales', columns: [{ name: 'order_date', dtype: 'datetime' }] } as any)
    const spec = { mode: 'to_date', unit: 'year', anchor: 'data_max' }
    vi.mocked(reportsApi.addCommonFilter).mockResolvedValue({ id: 11, column: 'order_date', op: 'relative', value: spec })
    renderBuilder()
    await openLeftTab('More')
    await screen.findByTestId('view-strip')

    fireEvent.change(await screen.findByLabelText('Report filter column'), { target: { value: 'order_date' } })
    fireEvent.change(screen.getByLabelText('Report filter operator'), { target: { value: 'relative' } })
    fireEvent.change(screen.getByLabelText('Report filter period'), { target: { value: 'ytd' } })
    const callsBefore = vi.mocked(reportsApi.getRevision).mock.calls.length
    vi.mocked(reportsApi.getRevision).mockResolvedValue(4)
    fireEvent.click(screen.getByRole('button', { name: '+ Add report filter' }))

    await waitFor(() => expect(reportsApi.addCommonFilter).toHaveBeenCalledWith(1, { column: 'order_date', op: 'relative', value: spec }))
    expect(await screen.findByText('order_date: Year to date · from latest data')).toBeInTheDocument()
    await waitFor(() => expect(vi.mocked(reportsApi.getRevision).mock.calls.length).toBeGreaterThan(callsBefore))
    // our own write is not somebody else's edit
    await new Promise(r => setTimeout(r, 50))
    expect(screen.queryByText(/changed in another session/i)).not.toBeInTheDocument()
  })
})

describe('ReportBuilder expression parameters', () => {
  it('keeps computed expression parameters out of the viewer prompt bar', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(baseReport() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales', columns: [] } as any)
    const { parametersApi } = await import('../services/api')
    vi.mocked(parametersApi.list).mockResolvedValue([
      { name: 'benchmark', param_type: 'expression', default_value: 'AVG(revenue)' },
      { name: 'chosen', param_type: 'text', default_value: 'US' },
    ] as any)
    renderBuilder()
    await screen.findByTestId('view-strip')

    const bar = await screen.findByTestId('parameter-bar')
    // the viewer-set text parameter shows; the computed expression one does not
    expect(within(bar).getByText('chosen')).toBeInTheDocument()
    expect(within(bar).queryByText('benchmark')).not.toBeInTheDocument()
  })
})

describe('ReportBuilder — a view-only viewer gets the dashboard, not the studio', () => {
  // The requirement in the owner's words: "he will see dashboard and can
  // filter only". Everything that changes the report is gone; everything that
  // explores it stays.
  function viewOnly(extra: Record<string, unknown> = {}) {
    return { ...reportWithWidget(), my_capability: 'view', ...extra } as any
  }

  async function renderViewOnly(report = viewOnly()) {
    vi.mocked(reportsApi.get).mockResolvedValue(report)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    renderBuilder()
    await screen.findByText('Sales by Region')
  }

  it('hides the Fields sidebar outright', async () => {
    // Its dataset attach/detach, hierarchy and calculated-column controls are
    // DATASET-scoped, so the report's own capability check would not have
    // refused them -- leaving them on screen was a live write path.
    await renderViewOnly()
    expect(screen.queryByText('Analytics')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Add Dataset/i })).not.toBeInTheDocument()
  })

  it('offers no way into edit mode, and says why', async () => {
    await renderViewOnly()
    expect(screen.queryByRole('button', { name: /Edit mode/i })).not.toBeInTheDocument()
    expect(screen.getByText(/View only/i)).toBeInTheDocument()
  })

  it('drops the authoring chrome: panels, add-widget, page controls, copilot', async () => {
    await renderViewOnly()
    for (const gone of [/More panels/i, /Add widget/i, /^\+ Page$/i, /Ask the page/i]) {
      expect(screen.queryByRole('button', { name: gone })).not.toBeInTheDocument()
    }
    expect(screen.queryByTestId('view-strip')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Outline/i })).not.toBeInTheDocument()
    expect(screen.queryByText(/PAGE PROPERTIES/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Copy link/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Present/i })).not.toBeInTheDocument()
  })

  it('hides guest-link sharing, which the server refuses below edit', async () => {
    await renderViewOnly()
    expect(screen.queryByRole('button', { name: /^Share$/i })).not.toBeInTheDocument()
  })

  it('does not let a double-click start renaming a page', async () => {
    await renderViewOnly()
    fireEvent.doubleClick(screen.getByRole('button', { name: 'Page 1' }))
    // The rename input never appears, so nothing can get stuck open on a 403.
    expect(screen.queryByDisplayValue('Page 1')).not.toBeInTheDocument()
  })

  it('KEEPS what a viewer is there for: the dashboard and its navigation', async () => {
    // The chart itself, the page tabs, and the cross-filter/slicer machinery
    // that rides with the render path -- none of it is edit-gated.
    await renderViewOnly()
    expect(screen.getByText('Sales by Region')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Page 1' })).toBeInTheDocument()
  })

  it('leaves a page prompt filter usable', async () => {
    // The one filter surface that renders without prior interaction, so it is
    // the one that can be asserted directly.
    await renderViewOnly(viewOnly({
      pages: [{ ...reportWithWidget().pages[0], prompt_column: 'region',
                prompt_label: 'Region' }],
    }))
    expect(await screen.findByPlaceholderText(/Region/i)).toBeInTheDocument()
  })

  it('still gives an editor the studio', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(
      { ...reportWithWidget(), my_capability: 'data' } as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    renderBuilder()
    await screen.findByText('Sales by Region')
    expect(screen.getByRole('group', { name: 'Report mode' })).toBeInTheDocument()
    // The studio's left panel: Fields / Charts / More tabs (was an "Analytics" header).
    expect(screen.getByRole('tablist', { name: 'Builder panel' })).toBeInTheDocument()
  })
})

describe('dropping several fields on the canvas', () => {
  /**
   * One field already auto-charted. SAS handles a multi-field drop, and the
   * comparison called that "the gap — not the rule". The rule table itself is
   * `lib/autoChart.ts`, tested there; this is the half that decides whether
   * anyone can reach it: ctrl-click to gather fields, drag, drop.
   */
  const columns = [
    { id: 1, name: 'region', dtype: 'categorical', missing_pct: 0, stats: {} },
    { id: 2, name: 'revenue', dtype: 'numeric', missing_pct: 0, stats: {} },
    { id: 3, name: 'cost', dtype: 'numeric', missing_pct: 0, stats: {} },
  ]

  async function builderWithFields() {
    // Counts are asserted below, and this file does not clear between tests:
    // without this the second test sees the first test's call.
    vi.mocked(reportsApi.addWidget).mockClear()
    vi.mocked(reportsApi.get).mockResolvedValue(baseReport() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue(
      { id: 10, name: 'Sales Data', columns } as any)
    vi.mocked(reportsApi.addWidget).mockResolvedValue({
      id: 999, page_id: 100, widget_type: 'bar', title: 'x', config: {},
      layout: { x: 0, y: 0, w: 6, h: 5 }, created_at: '2026-01-01',
    } as any)
    renderBuilder()
    await screen.findByTestId('view-strip')
  }

  /** A DataTransfer stub: jsdom's drag events carry none. */
  function transfer(store: Record<string, string> = {}) {
    return {
      data: store,
      types: Object.keys(store),
      setData(k: string, v: string) { store[k] = v; this.types = Object.keys(store) },
      getData(k: string) { return store[k] ?? '' },
      dropEffect: '', effectAllowed: '',
    }
  }

  /** The field chips are buttons labelled with a type glyph and the column name
   *  ("Aa region", "# revenue"), matched on their text. Awaited, because the
   *  chips appear only once `datasetsApi.get` resolves -- which is AFTER the
   *  view strip this file's setup waits for.
   *
   *  Not a template-literal regex: `\s` inside backticks is just "s" in
   *  JavaScript, which silently produces a pattern matching nothing. */
  const fieldButton = async (name: string) => await waitFor(() => {
    const el = screen.getAllByRole('button')
      .find(b => (b.textContent ?? '').trim().replace(/^(#|Aa|ƒx)\s*/, '') === name)
    if (!el) throw new Error(`no field chip for ${name}`)
    return el
  })

  it('ctrl-clicking gathers fields instead of assigning one', async () => {
    await builderWithFields()
    fireEvent.click(await fieldButton('region'), { ctrlKey: true })
    fireEvent.click(await fieldButton('revenue'), { ctrlKey: true })
    expect(await screen.findByText(/2 fields selected/i)).toBeInTheDocument()
  })

  it('dropping the gathered fields builds ONE chart from all of them', async () => {
    await builderWithFields()
    fireEvent.click(await fieldButton('region'), { ctrlKey: true })
    fireEvent.click(await fieldButton('revenue'), { ctrlKey: true })

    const dt = transfer()
    fireEvent.dragStart(await fieldButton('region'), { dataTransfer: dt })
    const canvas = document.querySelector('[data-canvas]')!
    fireEvent.drop(canvas, { dataTransfer: dt })

    await waitFor(() => expect(reportsApi.addWidget).toHaveBeenCalledTimes(1))
    expect(reportsApi.addWidget).toHaveBeenCalledWith(1, 100, expect.objectContaining({
      widget_type: 'bar',
      config: expect.objectContaining({ dimension: 'region', measure: 'revenue' }),
    }))
  })

  it('two measures with a category become one dual-axis chart, not two bars', async () => {
    await builderWithFields()
    fireEvent.click(await fieldButton('region'), { ctrlKey: true })
    fireEvent.click(await fieldButton('revenue'), { ctrlKey: true })
    fireEvent.click(await fieldButton('cost'), { ctrlKey: true })

    const dt = transfer()
    fireEvent.dragStart(await fieldButton('revenue'), { dataTransfer: dt })
    fireEvent.drop(document.querySelector('[data-canvas]')!, { dataTransfer: dt })

    await waitFor(() => expect(reportsApi.addWidget).toHaveBeenCalledTimes(1))
    expect(reportsApi.addWidget).toHaveBeenCalledWith(1, 100, expect.objectContaining({
      widget_type: 'dual_axis_bar' }))
  })

  it('a single field still drops the way it always did', async () => {
    // The one-field path is what everyone already uses; the multi-field work
    // must not change it.
    await builderWithFields()
    const dt = transfer()
    fireEvent.dragStart(await fieldButton('region'), { dataTransfer: dt })
    fireEvent.drop(document.querySelector('[data-canvas]')!, { dataTransfer: dt })

    await waitFor(() => expect(reportsApi.addWidget).toHaveBeenCalledTimes(1))
    expect(reportsApi.addWidget).toHaveBeenCalledWith(1, 100, expect.objectContaining({
      widget_type: 'bar',
      config: expect.objectContaining({ dimension: 'region', aggregation: 'count' }),
    }))
  })

  it('clears the gathered fields once they have been charted', async () => {
    // Otherwise the next drag silently carries the last drop's fields.
    await builderWithFields()
    fireEvent.click(await fieldButton('region'), { ctrlKey: true })
    fireEvent.click(await fieldButton('revenue'), { ctrlKey: true })
    const dt = transfer()
    fireEvent.dragStart(await fieldButton('region'), { dataTransfer: dt })
    fireEvent.drop(document.querySelector('[data-canvas]')!, { dataTransfer: dt })

    await waitFor(() => expect(reportsApi.addWidget).toHaveBeenCalled())
    await waitFor(() =>
      expect(screen.queryByText(/fields selected/i)).not.toBeInTheDocument())
  })
})

describe('one-click calculations from the field list', () => {
  /**
   * SAS offers quick calculations from the DATA ITEM, not just as a setting on
   * one chart. The result here is a saved MEASURE, which is the honest mapping:
   * `measure_eval` computes at the requesting widget's grain, so a
   * percent-of-total re-bases when the crossing changes.
   *
   * The rule table and the expressions are `lib/quickCalcs.ts`, pinned against
   * the real engine by test_frontend_constant_mirrors.py. This is the half that
   * decides whether anyone can reach them.
   */
  const cols = [
    { id: 1, name: 'region', dtype: 'categorical', missing_pct: 0, stats: {} },
    { id: 2, name: 'revenue', dtype: 'numeric', missing_pct: 0, stats: {} },
    { id: 3, name: 'net revenue', dtype: 'numeric', missing_pct: 0, stats: {} },
  ]

  async function builder(measures: unknown[] = []) {
    vi.mocked(reportsApi.get).mockResolvedValue(baseReport() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue(
      { id: 10, name: 'Sales Data', columns: cols, measures } as any)
    renderBuilder()
    await screen.findByTestId('view-strip')
  }

  const calcButton = async (field: string) => await waitFor(() => {
    const el = screen.queryByRole('button', { name: new RegExp(`calculations from ${field}`, 'i') })
    if (!el) throw new Error(`no quick-calc button for ${field}`)
    return el
  })

  it('offers a quick calculation on a numeric field', async () => {
    await builder()
    fireEvent.click(await calcButton('revenue'))
    expect(await screen.findByRole('menuitem', { name: '% of total' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Average' })).toBeInTheDocument()
  })

  it('saves the chosen one as a measure', async () => {
    const { measuresApi } = await import('../services/api')
    vi.mocked(measuresApi.save).mockResolvedValue(
      [{ name: '% of total revenue', expression: 'x' }] as never)
    await builder()
    fireEvent.click(await calcButton('revenue'))
    fireEvent.click(await screen.findByRole('menuitem', { name: '% of total' }))

    await waitFor(() => expect(measuresApi.save).toHaveBeenCalledWith(10,
      expect.objectContaining({
        name: '% of total revenue',
        expression: 'SUM(revenue) / TOTAL(SUM(revenue)) * 100',
      })))
  })

  it('never overwrites a measure that already has the name', async () => {
    // measuresApi.save upserts by name: colliding would silently replace
    // somebody else's definition.
    const { measuresApi } = await import('../services/api')
    vi.mocked(measuresApi.save).mockResolvedValue([] as never)
    await builder([{ name: '% of total revenue', expression: 'whatever' }])
    fireEvent.click(await calcButton('revenue'))
    fireEvent.click(await screen.findByRole('menuitem', { name: '% of total' }))

    await waitFor(() => expect(measuresApi.save).toHaveBeenCalledWith(10,
      expect.objectContaining({ name: '% of total revenue (2)' })))
  })

  it('offers a category only what suits one', async () => {
    await builder()
    fireEvent.click(await calcButton('region'))
    expect(await screen.findByRole('menuitem', { name: 'Distinct values' })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'Average' })).not.toBeInTheDocument()
  })

  it('offers nothing on a field the measure language cannot name', async () => {
    // "net revenue" cannot appear in an expression at all — the engine binds
    // columns to Python identifiers — so there is no button to press.
    await builder()
    await waitFor(() => expect(screen.getAllByRole('button').length).toBeGreaterThan(5))
    expect(screen.queryByRole('button', { name: /calculations from net revenue/i }))
      .not.toBeInTheDocument()
  })

  it('the new measure appears in the field list without a reload', async () => {
    const { measuresApi } = await import('../services/api')
    vi.mocked(measuresApi.save).mockResolvedValue(
      [{ name: 'Average revenue', expression: 'AVG(revenue)' }] as never)
    await builder()
    fireEvent.click(await calcButton('revenue'))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Average' }))
    expect(await screen.findByRole('button', { name: /Average revenue/ })).toBeInTheDocument()
  })
})

describe('managing saved page templates', () => {
  /**
   * SAS's template dialog has "Manage Templates" and a tip that says to give
   * templates meaningful names. Ours had neither: the save button named every
   * template `Template <today's date>`, and nothing could delete one — so a
   * name typed wrong, or a layout that turned out badly, stayed in a list every
   * author in the org sees, forever.
   */
  async function builderWithTemplates(saved: { id: number; name: string; widgets: number }[]) {
    const { pageTemplatesApi } = await import('../services/api')
    // This file does not clear between tests and the counts below are asserted.
    vi.mocked(pageTemplatesApi.delete).mockClear()
    vi.mocked(pageTemplatesApi.saveFrom).mockClear()
    vi.mocked(pageTemplatesApi.builtins).mockResolvedValue([])
    vi.mocked(pageTemplatesApi.list).mockResolvedValue(saved)
    vi.mocked(reportsApi.get).mockResolvedValue(baseReport() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    renderBuilder()
    await screen.findByTestId('view-strip')
    fireEvent.click(screen.getByRole('button', { name: /add page from a template/i }))
    return pageTemplatesApi
  }

  it('deletes a saved template', async () => {
    const api = await builderWithTemplates([{ id: 5, name: 'Quarterly layout', widgets: 3 }])
    vi.mocked(api.delete).mockResolvedValue(undefined as never)

    fireEvent.click(await screen.findByRole('button', { name: /delete template quarterly layout/i }))
    // Destructive, so it asks first — the same confirm the widget templates use.
    fireEvent.click(await screen.findByRole('button', { name: /^delete$/i }))

    await waitFor(() => expect(api.delete).toHaveBeenCalledWith(5))
  })

  it('asks before deleting', async () => {
    const api = await builderWithTemplates([{ id: 5, name: 'Quarterly layout', widgets: 3 }])
    fireEvent.click(await screen.findByRole('button', { name: /delete template quarterly layout/i }))
    expect(await screen.findByText(/cannot be undone/i)).toBeInTheDocument()
    expect(api.delete).not.toHaveBeenCalled()
  })

  it('lets the author name the template they save', async () => {
    // "Template 9/11/2026" tells nobody anything, which is exactly what SAS's
    // own tip warns about.
    const api = await builderWithTemplates([])
    vi.mocked(api.saveFrom).mockResolvedValue({ id: 9, name: 'x' } as never)

    fireEvent.click(await screen.findByRole('menuitem', { name: /save current page as a template/i }))
    const input = await screen.findByLabelText(/new template name/i)
    fireEvent.change(input, { target: { value: 'Quarterly layout' } })
    fireEvent.click(screen.getByRole('button', { name: /save page template/i }))

    await waitFor(() => expect(api.saveFrom)
      .toHaveBeenCalledWith(1, 100, 'Quarterly layout'))
  })

  it('will not save a template with no name', async () => {
    const api = await builderWithTemplates([])
    fireEvent.click(await screen.findByRole('menuitem', { name: /save current page as a template/i }))
    fireEvent.click(await screen.findByRole('button', { name: /save page template/i }))
    expect(api.saveFrom).not.toHaveBeenCalled()
  })
})

describe('the data pane', () => {
  /**
   * Measured against SAS's Data pane, which carries a Filter box over the items
   * and reads "Country - 47", "Order ID - 748K" — every category showing how
   * many distinct values it holds. That number is the most useful thing to know
   * before charting a field, and `analyze_categorical` has computed it as
   * `n_unique` since the beginning without anything showing it.
   */
  const manyColumns = [
    { id: 1, name: 'country', dtype: 'categorical', missing_pct: 0, stats: {} },
    { id: 2, name: 'order_id', dtype: 'categorical', missing_pct: 0, stats: {} },
    { id: 3, name: 'revenue', dtype: 'numeric', missing_pct: 0, stats: {} },
  ]

  async function builderWithProfile() {
    vi.mocked(reportsApi.get).mockResolvedValue(baseReport() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue(
      { id: 10, name: 'Sales Data', columns: manyColumns } as any)
    vi.mocked(analysisApi.get).mockResolvedValue({
      categorical: { columns: { country: { n_unique: 47 }, order_id: { n_unique: 748000 } } },
      numeric: { columns: {} },
    } as any)
    renderBuilder()
    await screen.findByTestId('view-strip')
  }

  it('shows how many distinct values a category holds', async () => {
    await builderWithProfile()
    expect(await screen.findByText(/47/)).toBeInTheDocument()
    expect(screen.getByText(/748K/)).toBeInTheDocument()
  })

  it('filters the field list', async () => {
    await builderWithProfile()
    const box = await screen.findByLabelText(/filter fields/i)
    fireEvent.change(box, { target: { value: 'coun' } })

    await waitFor(() => {
      const names = screen.getAllByRole('button')
        .map(b => (b.textContent ?? '').trim().replace(/^(#|Aa|ƒx)\s*/, ''))
      expect(names.some(n => n.startsWith('country'))).toBe(true)
      expect(names.some(n => n.startsWith('revenue'))).toBe(false)
    })
  })

  it('matches without case', async () => {
    await builderWithProfile()
    fireEvent.change(await screen.findByLabelText(/filter fields/i),
      { target: { value: 'REVEN' } })
    await waitFor(() => {
      const names = screen.getAllByRole('button')
        .map(b => (b.textContent ?? '').trim().replace(/^(#|Aa|ƒx)\s*/, ''))
      expect(names.some(n => n.startsWith('revenue'))).toBe(true)
    })
  })

  it('says so rather than showing an empty pane when nothing matches', async () => {
    await builderWithProfile()
    fireEvent.change(await screen.findByLabelText(/filter fields/i),
      { target: { value: 'zzzz' } })
    expect(await screen.findByText(/no fields match/i)).toBeInTheDocument()
  })
})

describe('classifying a field as geography', () => {
  /**
   * SAS's data pane classifies a data item as Category or Geography, and every
   * map built from it inherits that. Here the boundary set has always been a
   * per-WIDGET choice, so a dataset with a governorate column and six maps
   * meant choosing the same shapes six times — and getting it wrong once meant
   * one map silently drawing nothing.
   *
   * The classification lives in column_meta (backend `role: 'geography'` plus
   * `boundary_set_id`); this is the half that lets an author set it, and the
   * moment it pays off: dropping the column on a map.
   */
  const cols = [
    { id: 1, name: 'governorate', dtype: 'categorical', missing_pct: 0, stats: {} },
    { id: 2, name: 'sales', dtype: 'numeric', missing_pct: 0, stats: {} },
  ]

  async function builder(meta: Record<string, unknown> = {}) {
    const { columnMetaApi, boundarySetsApi } = await import('../services/api')
    vi.mocked(columnMetaApi.get).mockResolvedValue(meta as never)
    vi.mocked(columnMetaApi.set).mockImplementation(async (_id, m) => m as never)
    vi.mocked(boundarySetsApi.list).mockResolvedValue(
      [{ id: 7, name: 'Egypt governorates', feature_count: 27,
         key_properties: ['name'], created_at: '2026-01-01', created_by: 1 }] as never)
    vi.mocked(reportsApi.get).mockResolvedValue(baseReport() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue(
      { id: 10, name: 'Sales', columns: cols, column_meta: meta } as any)
    renderBuilder()
    await screen.findByTestId('view-strip')
    return columnMetaApi
  }

  it('offers the classification on a category field', async () => {
    await builder()
    expect(await screen.findByRole('button', { name: 'Classify governorate' }))
      .toBeInTheDocument()
  })

  it('does not offer it on a measure', async () => {
    // There is no map of a number: geography is a property of a category.
    await builder()
    await screen.findByRole('button', { name: 'Classify governorate' })
    // Exact: there is already a "Reclassify sales as category" control beside
    // every field, and a loose pattern matches that instead.
    expect(screen.queryByRole('button', { name: 'Classify sales' })).not.toBeInTheDocument()
  })

  it('saves the classification and the boundary set together', async () => {
    // "This column is geography" is not useful on its own; "drawn with THESE
    // shapes" is, and that is what saves repeating the choice per map.
    const api = await builder()
    const { boundarySetsApi } = await import('../services/api')
    vi.mocked(boundarySetsApi.get).mockResolvedValue({ id: 7, name: 'Egypt governorates', key_properties: ['name'],
      geometry: { type: 'FeatureCollection', features: [] } } as never)
    fireEvent.click(await screen.findByRole('button', { name: 'Classify governorate' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: /Egypt governorates/ }))
    // The validation panel comes first: the match is shown before it is saved.
    expect(await screen.findByRole('dialog', { name: /Check governorate against Egypt governorates/ })).toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: /Use as geography|Use anyway/ }))

    await waitFor(() => expect(api.set).toHaveBeenCalledWith(10,
      expect.objectContaining({
        governorate: expect.objectContaining({ role: 'geography', boundary_set_id: 7 }),
      })))
  })

  it('can be turned back into an ordinary category', async () => {
    const api = await builder({ governorate: { role: 'geography', boundary_set_id: 7 } })
    fireEvent.click(await screen.findByRole('button', { name: 'Classify governorate' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: /not geography/i }))

    await waitFor(() => {
      const [, saved] = vi.mocked(api.set).mock.calls[vi.mocked(api.set).mock.calls.length - 1]
      expect((saved as Record<string, { role?: string }>).governorate?.role).toBeUndefined()
    })
  })
})

describe('duplicating a widget on the page', () => {
  /**
   * The other half of SAS's Duplicate Object: the ⋯ item exists in the renderer,
   * and this is whether it does anything. Build a chart, copy it, change one
   * field — the commonest authoring move there is, and until now the only way
   * was to build the second one from scratch.
   */
  async function builderWithWidget() {
    vi.mocked(reportsApi.get).mockResolvedValue(reportWithWidget() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue(
      { id: 10, name: 'Sales Data', columns: [] } as any)
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false } as never)
    vi.mocked(reportsApi.addWidget).mockClear()
    vi.mocked(reportsApi.addWidget).mockResolvedValue({
      id: 77, page_id: 100, widget_type: 'bar', title: 'Sales by Region (copy)',
      config: {}, layout: { x: 0, y: 5, w: 6, h: 5 }, created_at: '2026-01-01',
    } as any)
    renderBuilder()
    await screen.findByTestId('view-strip')
  }

  it('copies the widget with its configuration', async () => {
    await builderWithWidget()
    fireEvent.click(await screen.findByRole('button', { name: /More actions for widget Sales by Region/ }))
    fireEvent.click(await screen.findByRole('menuitem', { name: /duplicate widget/i }))

    await waitFor(() => expect(reportsApi.addWidget).toHaveBeenCalledTimes(1))
    const [, , body] = vi.mocked(reportsApi.addWidget).mock.calls[0]
    expect(body).toMatchObject({
      widget_type: 'bar',
      config: expect.objectContaining({ dimension: 'region' }),
    })
  })

  it('names the copy so the two can be told apart', async () => {
    await builderWithWidget()
    fireEvent.click(await screen.findByRole('button', { name: /More actions for widget Sales by Region/ }))
    fireEvent.click(await screen.findByRole('menuitem', { name: /duplicate widget/i }))

    await waitFor(() => expect(reportsApi.addWidget).toHaveBeenCalled())
    const [, , body] = vi.mocked(reportsApi.addWidget).mock.calls[0]
    expect((body as { title: string }).title).toMatch(/copy/i)
  })

  it('puts the copy below the original rather than on top of it', async () => {
    // Placed at the same x/y it would be invisible — the author would think
    // nothing happened and press it again.
    await builderWithWidget()
    fireEvent.click(await screen.findByRole('button', { name: /More actions for widget Sales by Region/ }))
    fireEvent.click(await screen.findByRole('menuitem', { name: /duplicate widget/i }))

    await waitFor(() => expect(reportsApi.addWidget).toHaveBeenCalled())
    const [, , body] = vi.mocked(reportsApi.addWidget).mock.calls[0]
    const layout = (body as { layout: { x: number; y: number } }).layout
    expect(layout.y).toBeGreaterThan(0)
  })
})

/**
 * Reaching an object's settings without hunting for it on the canvas.
 *
 * Every pane in SAS carries an object selector at the top, and that is the
 * thing that makes "all the settings of an object" reachable: you pick the
 * object from a list rather than finding it among overlapping tiles, small
 * tiles, or tiles on a part of the page you have scrolled away from. A widget
 * inside a container, or one sitting under another in a precision layout, can
 * otherwise be genuinely hard to click.
 */
describe('the object selector', () => {
  /** Two widgets, so choosing between them is a real choice. */
  function twoWidgets() {
    const r = baseReport()
    r.pages[0].widgets = [
      { id: 5, page_id: 100, widget_type: 'bar', title: 'Sales by Region',
        config: { dimension: 'region' }, layout: { x: 0, y: 0, w: 6, h: 5 }, created_at: '2026-01-01' },
      { id: 6, page_id: 100, widget_type: 'line', title: 'Orders over time',
        config: { dimension: 'ordered_at' }, layout: { x: 6, y: 0, w: 6, h: 5 }, created_at: '2026-01-01' },
    ] as never
    return r
  }

  beforeEach(() => {
    vi.mocked(reportsApi.get).mockResolvedValue(twoWidgets() as never)
    vi.mocked(datasetsApi.get).mockResolvedValue(
      { id: 10, name: 'Sales Data', columns: [] } as never)
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false } as never)
  })

  it('opens the object chosen from the list', async () => {
    renderBuilder()
    const picker = await screen.findByLabelText(/object to edit/i)

    fireEvent.change(picker, { target: { value: '6' } })

    // The properties panel follows the selection, which is the whole point: a
    // widget inside a container or under another in a precision layout can be
    // genuinely hard to click.
    await waitFor(() =>
      expect((screen.getByLabelText(/^title$/i) as HTMLInputElement).value)
        .toBe('Orders over time'))
  })

  it('offers the page itself, so page settings are in the same place', async () => {
    renderBuilder()
    const picker = await screen.findByLabelText(/object to edit/i) as HTMLSelectElement
    const labels = Array.from(picker.options).map(o => o.textContent ?? '')
    expect(labels.some(l => /page/i.test(l))).toBe(true)
    expect(labels.some(l => l.includes('Sales by Region'))).toBe(true)
    expect(labels.some(l => l.includes('Orders over time'))).toBe(true)
  })
})

/**
 * Finding a chart among sixty-seven of them.
 *
 * The insert palette lists every widget type as a button, grouped by category —
 * which was the fix for an earlier bug where a hardcoded list hid the whole
 * Maps category. Grouped or not, 67 buttons in one scrolling column means
 * scrolling to find "waterfall", and the properties panel beside it already has
 * a "Filter settings" box, so the pattern exists in the product.
 */
describe('the insert palette', () => {
  it('filters to what was typed', async () => {
    renderBuilder()
    await openLeftTab('Charts')
    const box = await screen.findByLabelText(/find a chart/i)

    fireEvent.change(box, { target: { value: 'waterfall' } })

    expect(screen.getByRole('button', { name: /waterfall/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /bar chart/i })).not.toBeInTheDocument()
  })

  it('matches however the reader thinks of it, not just the label', async () => {
    // Somebody looking for a map does not necessarily know it is called
    // "Choropleth"; the category is part of what they are searching.
    renderBuilder()
    await openLeftTab('Charts')
    const box = await screen.findByLabelText(/find a chart/i)

    fireEvent.change(box, { target: { value: 'maps' } })
    expect(screen.getAllByRole('button', { name: /map/i }).length).toBeGreaterThan(0)
  })

  it('says so when nothing matches, rather than showing an empty panel', async () => {
    renderBuilder()
    await openLeftTab('Charts')
    fireEvent.change(await screen.findByLabelText(/find a chart/i),
      { target: { value: 'zzzz' } })
    expect(screen.getByText(/no chart matches/i)).toBeInTheDocument()
  })

  it('shows everything again when the box is cleared', async () => {
    renderBuilder()
    await openLeftTab('Charts')
    const box = await screen.findByLabelText(/find a chart/i)
    fireEvent.change(box, { target: { value: 'waterfall' } })
    fireEvent.change(box, { target: { value: '' } })
    expect(screen.getByRole('button', { name: /bar chart/i })).toBeInTheDocument()
  })
})

/**
 * The report header must wrap.
 *
 * Measured in a real browser at 1366x850 — one of the commonest laptop
 * resolutions — the "Edit mode" button sat 150px past the window edge, with no
 * scrollable ancestor and no document overflow: the control that puts a report
 * into edit mode was simply unreachable. The row is inside a parent with
 * overflow:hidden, so a non-wrapping flex row loses whatever does not fit.
 *
 * jsdom has no layout, so this cannot measure the overflow — it guards the one
 * declaration that prevents it. The real proof is
 * `backend/scripts/ui_walkthrough.py` and the browser measurement beside it.
 */
describe('the builder header', () => {
  it('wraps rather than clipping its controls', async () => {
    renderBuilder()
    const header = await screen.findByTestId('builder-header')
    expect(header).toHaveStyle({ flexWrap: 'wrap' })
  })
})

describe('ReportBuilder page layout recipes', () => {
  it('opens a Layout menu with Executive as default and Free layout as an option', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(reportWithWidget() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
    renderBuilder()
    await screen.findByTestId('view-strip')

    fireEvent.click(screen.getByRole('button', { name: 'Page layout' }))
    expect(screen.getByRole('menuitem', { name: /Executive/ })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: /Free layout/ })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: /2 × 2/ })).toBeInTheDocument()
  })

  it('reflows existing charts into Executive and saves packed mode', async () => {
    const report = reportWithWidget()
    ;(report.pages[0].widgets as any[]).push({
      id: 6, page_id: 100, widget_type: 'kpi', title: 'Total', config: {},
      layout: { x: 8, y: 8, w: 3, h: 3 }, created_at: '2026-01-01',
    })
    vi.mocked(reportsApi.get).mockResolvedValue(report as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
    vi.mocked(reportsApi.updatePage).mockResolvedValue({} as any)
    vi.mocked(reportsApi.updateWidget).mockResolvedValue({} as any)
    renderBuilder()
    await screen.findByTestId('view-strip')

    fireEvent.click(screen.getByRole('button', { name: 'Page layout' }))
    fireEvent.click(screen.getByRole('menuitem', { name: /Executive/ }))

    await waitFor(() => expect(reportsApi.updatePage).toHaveBeenCalledWith(
      1, 100, expect.objectContaining({ layout_mode: 'packed', layout_template: 'executive' })))
    expect(reportsApi.updateWidget).toHaveBeenCalled()
  })

  it('auto-packs a legacy page that has no layout_mode', async () => {
    const report = reportWithWidget()
    delete (report.pages[0] as any).layout_mode
    vi.mocked(reportsApi.get).mockResolvedValue(report as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [] } as any)
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
    vi.mocked(reportsApi.updatePage).mockResolvedValue({} as any)
    vi.mocked(reportsApi.updateWidget).mockResolvedValue({} as any)
    renderBuilder()
    await screen.findByTestId('view-strip')

    await waitFor(() => expect(reportsApi.updatePage).toHaveBeenCalledWith(
      1, 100, expect.objectContaining({ layout_mode: 'packed', layout_template: 'executive' })))
  })
})


describe('ReportBuilder explains permissions and sensitivity (Phase 7.3)', () => {
  it('greys out Guest links with the server\'s reason and lists every decision on request', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(baseReport() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales', columns: [] } as any)
    vi.mocked(authzApi.decisions).mockResolvedValue([
      { resource: 'report', id: 1, action: 'view', allowed: true, reason: 'You created this report.' },
      { resource: 'report', id: 1, action: 'edit', allowed: true, reason: 'You created this report.' },
      { resource: 'report', id: 1, action: 'data', allowed: true, reason: 'You created this report.' },
      { resource: 'report', id: 1, action: 'share_link', allowed: false, reason: 'The report is Restricted (People is labelled Restricted); share it with named people instead.' },
      { resource: 'report', id: 1, action: 'download', allowed: true, reason: 'You created this report.' },
    ])
    vi.mocked(reportsApi.getClassification).mockResolvedValue({ label: null, options: [], floor: 'Restricted',
      floor_reasons: ['People is labelled Restricted'], effective: 'Restricted', effective_reasons: ['People is labelled Restricted'] })
    renderBuilder()
    await screen.findByTestId('view-strip')
    expect((await screen.findByTestId('sensitivity-badge')).textContent).toContain('Restricted')
    fireEvent.click(screen.getByRole('button', { name: /Share/ }))
    const guest = await screen.findByRole('menuitem', { name: /Guest links/ })
    expect(guest.getAttribute('aria-disabled')).toBe('true')
    expect(guest.getAttribute('title')).toContain('share it with named people instead')
    fireEvent.click(screen.getByRole('menuitem', { name: /Your access, and why/ }))
    const list = await screen.findByTestId('access-decisions')
    expect(list.textContent).toContain('Share it by guest link')
    expect(screen.getByTestId('access-sensitivity').textContent).toContain('No guest links or embeds')
  })
})

describe('ReportBuilder empty page: Add data', () => {
  it('opens the dataset chooser even when the left panel was left on another tab', async () => {
    // The left tab is remembered; with it on More the button used to open a
    // menu inside the (hidden) Fields tab, so the click did nothing visible --
    // a dead end on the first step of building a dashboard.
    try { localStorage.setItem('datalytics:builder-left-tab', 'more') } catch { /* */ }
    const r = baseReport()
    ;(r as { dataset_id: number | null }).dataset_id = null
    vi.mocked(reportsApi.get).mockResolvedValue(r as never)
    vi.mocked(datasetsApi.list).mockResolvedValue([] as never)
    renderBuilder()
    fireEvent.click(await screen.findByRole('button', { name: 'Add data' }))
    expect(await screen.findByText('Choose the data for this dashboard')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Fields' })).toHaveAttribute('aria-selected', 'true')
  })
})

describe('ReportBuilder: every edit is one undo step', () => {
  const ds = {
    id: 10, name: 'Sales Data',
    columns: [
      { id: 1, name: 'region', dtype: 'text', missing_pct: 0, stats: {} },
      { id: 2, name: 'sales', dtype: 'numeric', missing_pct: 0, stats: {} },
    ],
  }
  const undoTitle = () => screen.getByRole('button', { name: 'Undo' }).getAttribute('title') ?? ''

  it('a chart made by clicking a field is undoable', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(baseReport() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue(ds as any)
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
    vi.mocked(reportsApi.addWidget).mockResolvedValue({
      id: 77, page_id: 100, widget_type: 'bar', title: 'Count by region',
      config: { dimension: 'region' }, layout: { x: 0, y: 0, w: 6, h: 5 },
    } as any)
    vi.mocked(reportsApi.deleteWidget).mockResolvedValue(undefined as any)
    renderBuilder()
    await screen.findByTestId('view-strip')
    fireEvent.click(await screen.findByRole('button', { name: /^[#ƒx Aa]* ?region/ }))
    await waitFor(() => expect(undoTitle()).toMatch(/^Undo: Add /))
    fireEvent.click(screen.getByRole('button', { name: 'Undo' }))
    await waitFor(() => expect(reportsApi.deleteWidget).toHaveBeenCalledWith(1, 100, 77))
  })

  it('adding a page is undoable', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(baseReport() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue(ds as any)
    vi.mocked(reportsApi.addPage).mockResolvedValue({ id: 101, report_id: 1, name: 'Page 2', position: 1, widgets: [] } as any)
    vi.mocked(reportsApi.deletePage).mockResolvedValue(undefined as any)
    renderBuilder()
    await screen.findByTestId('view-strip')
    fireEvent.click(screen.getByRole('button', { name: /^\+?\s*Page$/ }))
    await waitFor(() => expect(undoTitle()).toBe('Undo: Add page "Page 2" (Ctrl+Z)'))
    fireEvent.click(screen.getByRole('button', { name: 'Undo' }))
    await waitFor(() => expect(reportsApi.deletePage).toHaveBeenCalledWith(1, 101))
  })

  it('switching the theme is undoable', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue({ ...baseReport(), theme: 'default' } as any)
    vi.mocked(datasetsApi.get).mockResolvedValue(ds as any)
    vi.mocked(reportsApi.update).mockResolvedValue({} as any)
    renderBuilder()
    await screen.findByTestId('view-strip')
    fireEvent.click(screen.getByRole('button', { name: 'Ocean' }))
    await waitFor(() => expect(undoTitle()).toMatch(/^Undo: Change theme to ocean/))
    vi.mocked(reportsApi.update).mockClear()
    fireEvent.click(screen.getByRole('button', { name: 'Undo' }))
    await waitFor(() => expect(reportsApi.update).toHaveBeenCalledWith(1, { theme: 'default' }))
  })

  it('deleting a page is undoable, widgets and all', async () => {
    const r = baseReport()
    r.pages.push({ id: 101, report_id: 1, name: 'Detail', page_type: 'normal', position: 1, created_at: '2026-01-01', layout_mode: 'free',
      widgets: [{ id: 9, page_id: 101, widget_type: 'bar', title: 'By region', config: { dimension: 'region' },
        layout: { x: 0, y: 0, w: 6, h: 5 }, created_at: '2026-01-01' }] } as any)
    vi.mocked(reportsApi.get).mockResolvedValue(r as any)
    vi.mocked(datasetsApi.get).mockResolvedValue(ds as any)
    vi.mocked(reportsApi.deletePage).mockResolvedValue(undefined as any)
    vi.mocked(reportsApi.addPage).mockResolvedValue({ id: 202, report_id: 1, name: 'Detail', position: 1, widgets: [] } as any)
    vi.mocked(reportsApi.addWidget).mockClear().mockResolvedValue({ id: 90 } as any)
    renderBuilder()
    await screen.findByTestId('view-strip')
    fireEvent.click(screen.getByRole('button', { name: 'Delete page "Detail"' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(reportsApi.deletePage).toHaveBeenCalledWith(1, 101))
    await waitFor(() => expect(undoTitle()).toBe('Undo: Delete page "Detail" (Ctrl+Z)'))
    fireEvent.click(screen.getByRole('button', { name: 'Undo' }))
    await waitFor(() => expect(reportsApi.addWidget).toHaveBeenCalledWith(1, 202,
      expect.objectContaining({ widget_type: 'bar', title: 'By region', config: { dimension: 'region' } })))
    expect(reportsApi.addPage).toHaveBeenCalledWith(1, expect.objectContaining({ name: 'Detail', position: 1 }))
  })

  it('"Last 30 days" is one click, and one undo', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue({ ...baseReport(), common_filters: [] } as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ ...ds, columns: [...ds.columns,
      { id: 3, name: 'order_date', dtype: 'datetime', missing_pct: 0, stats: {} }] } as any)
    vi.mocked(reportsApi.addCommonFilter).mockResolvedValue({ id: 55, column: 'order_date', op: 'relative',
      value: { mode: 'last', unit: 'day', n: 30, anchor: 'data_max' } } as any)
    vi.mocked(reportsApi.deleteCommonFilter).mockResolvedValue(undefined as any)
    renderBuilder()
    await screen.findByTestId('view-strip')
    await openLeftTab('More')
    fireEvent.click(await screen.findByRole('button', { name: 'Last 30 days' }))
    await waitFor(() => expect(reportsApi.addCommonFilter).toHaveBeenCalledWith(1, {
      column: 'order_date', op: 'relative', value: { mode: 'last', unit: 'day', n: 30, anchor: 'data_max' } }))
    await waitFor(() => expect(undoTitle()).toBe('Undo: Filter the report to last 30 days (Ctrl+Z)'))
    fireEvent.click(screen.getByRole('button', { name: 'Undo' }))
    await waitFor(() => expect(reportsApi.deleteCommonFilter).toHaveBeenCalledWith(1, 55))
  })
})

describe('ReportBuilder accessibility', () => {
  it('has no structural accessibility violations in edit mode', async () => {
    vi.mocked(reportsApi.get).mockResolvedValue(reportWithWidget() as any)
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 10, name: 'Sales Data', columns: [
      { id: 1, name: 'region', dtype: 'text', missing_pct: 0, stats: {} },
      { id: 2, name: 'sales', dtype: 'numeric', missing_pct: 0, stats: {} }] } as any)
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
    const { container } = renderBuilder()
    await screen.findByTestId('view-strip')
    expect(await axeViolations(container)).toEqual([])
  }, 20000)
})
