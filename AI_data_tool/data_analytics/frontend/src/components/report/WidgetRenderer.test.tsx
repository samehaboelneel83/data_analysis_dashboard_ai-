import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { withMeasuredTiles } from '../../test/measuredTiles'
import { memo, useEffect, useState } from 'react'
import { render, waitFor, screen, fireEvent, act } from '@testing-library/react'
import WidgetRenderer from './WidgetRenderer'
import { CrossFilterProvider, useCrossFilter } from './CrossFilterContext'
import { widgetDataApi, pinsApi } from '../../services/api'
import type { Widget, ReportPage, HierarchyNode } from '../../types/report'

vi.mock('../../services/api', () => ({
  pinsApi: { create: vi.fn().mockResolvedValue({ id: 1, widget_id: 1, already_pinned: false }), list: vi.fn().mockResolvedValue([]), remove: vi.fn().mockResolvedValue(undefined) },
  widgetDataApi: { query: vi.fn() },
  // The lazily-imported map renderers reach this module through
  // geo/regionSetCache. Without the export the dynamic import fails and the
  // widget sits on "Loading map…" forever, which reads as a renderer bug.
  boundarySetsApi: { list: vi.fn().mockResolvedValue([]), get: vi.fn(), create: vi.fn(), remove: vi.fn() },
}))

function barWidget(overrides: Partial<Widget> = {}): Widget {
  return {
    id: 1, page_id: 100, widget_type: 'bar', title: 'Sales', config: { dimension: 'region' },
    layout: { x: 0, y: 0, w: 6, h: 5 }, created_at: '2026-01-01', ...overrides,
  }
}

function reportPage(overrides: Partial<ReportPage> = {}): ReportPage {
  return { id: 100, report_id: 1, name: 'Page 1', page_type: 'normal', position: 0, widgets: [], created_at: '2026-01-01', page_size: '16:9', ...overrides }
}

function renderWidget(props: Partial<React.ComponentProps<typeof WidgetRenderer>> = {}) {
  return render(
    <CrossFilterProvider>
      <WidgetRenderer widget={barWidget()} datasetId={10} {...props} />
    </CrossFilterProvider>
  )
}

describe('WidgetRenderer performance reporting', () => {
  it('reports fetch duration and row count via onFetchComplete', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [{ name: 'A', value: 1 }, { name: 'B', value: 2 }], sampled: false })
    const onFetchComplete = vi.fn()
    renderWidget({ onFetchComplete })

    await waitFor(() => expect(onFetchComplete).toHaveBeenCalled())

    const [widgetId, info] = onFetchComplete.mock.calls[0]
    expect(widgetId).toBe(1)
    expect(info.rowCount).toBe(2)
    expect(info.sampled).toBe(false)
    expect(typeof info.durationMs).toBe('number')
  })
})

function MultiFilterInjector({ widgetId, pageId, column, values }: { widgetId: number; pageId: number; column: string; values: unknown[] }) {
  const { emitMultiFilter } = useCrossFilter()
  useEffect(() => { emitMultiFilter(widgetId, pageId, column, values, `${column} in (...)`) }, [])
  return null
}

describe('WidgetRenderer element skins', () => {
  it('applies a raised skin as a box-shadow on the widget container', () => {
    const { container } = renderWidget({ widget: barWidget({ config: { dimension: 'region', widget_skin: 'raised' }, title: 'T' }) })
    const fig = container.querySelector('[role="figure"]') as HTMLElement
    expect(fig).not.toBeNull()
    expect(fig.style.boxShadow).toContain('0 2px 8px')
  })

  it('leaves the container unshadowed when no skin is set', () => {
    const { container } = renderWidget({ widget: barWidget({ config: { dimension: 'region' }, title: 'T' }) })
    const fig = container.querySelector('[role="figure"]') as HTMLElement
    expect(fig.style.boxShadow === '' || fig.style.boxShadow === 'none').toBe(true)
  })
})

describe('WidgetRenderer crosstab sparkline', () => {
  const crosstab = {
    type: 'crosstab',
    columns: ['region', 'Q1', 'Q2', 'Q3', '__total__'],
    rows: [['US', 10, 40, 25, 75], ['CA', 5, 8, 6, 19]],
  }
  const ctWidget = (config: Record<string, unknown>): Widget =>
    barWidget({ widget_type: 'crosstab', title: 'By quarter', config })

  it('renders a Trend column of sparklines from each row series when enabled', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue(crosstab as never)
    const { container } = renderWidget({ widget: ctWidget({ dimension: 'region', dimension2: 'quarter', sparkline: true }) })
    await waitFor(() => expect(screen.getByText('Trend')).toBeInTheDocument())
    // one sparkline polyline per data row (value columns excl. __total__ = 3 points)
    const polylines = container.querySelectorAll('svg[aria-label="trend sparkline"] polyline')
    expect(polylines.length).toBe(2)
  })

  it('draws no Trend column unless the sparkline option is on', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue(crosstab as never)
    renderWidget({ widget: ctWidget({ dimension: 'region', dimension2: 'quarter' }) })
    await waitFor(() => expect(screen.getByText('Q1')).toBeInTheDocument())
    expect(screen.queryByText('Trend')).not.toBeInTheDocument()
  })
})

describe('WidgetRenderer custom visual', () => {
  it('renders a sandboxed iframe pointed at its url and still fetches data', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ type: 'series', rows: [{ name: 'US', value: 5 }] } as never)
    const { container } = renderWidget({ widget: barWidget({
      widget_type: 'custom_visual', title: 'CV',
      config: { url: 'https://viz.example/app', dimension: 'region', measure: 'revenue' },
    }) })
    const iframe = await waitFor(() => {
      const f = container.querySelector('iframe'); expect(f).not.toBeNull(); return f!
    })
    expect(iframe.getAttribute('src')).toBe('https://viz.example/app')
    expect(iframe.getAttribute('sandbox')).toBe('allow-scripts')   // opaque origin: can render, can't reach the app
    expect(widgetDataApi.query).toHaveBeenCalled()                  // it IS a data widget
  })

  it('shows a placeholder for a non-embeddable url', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ type: 'series', rows: [] } as never)
    renderWidget({ widget: barWidget({ widget_type: 'custom_visual', title: 'CV',
      config: { url: 'javascript:alert(1)' } }) })
    expect(await screen.findByText(/http\(s\) URL/i)).toBeInTheDocument()
  })
})

describe('WidgetRenderer web content', () => {
  const webWidget = (config: Record<string, unknown>): Widget =>
    barWidget({ widget_type: 'web_content', title: 'Docs', config })

  it('embeds an http(s) URL in a sandboxed iframe and never fetches data', () => {
    vi.mocked(widgetDataApi.query).mockClear()
    const { container } = renderWidget({ widget: webWidget({ url: 'https://example.com/dash' }) })
    const frame = container.querySelector('iframe')
    expect(frame).not.toBeNull()
    expect(frame!.getAttribute('src')).toBe('https://example.com/dash')
    expect(frame!.getAttribute('sandbox')).toContain('allow-scripts')
    // static widget: the data path is never touched
    expect(widgetDataApi.query).not.toHaveBeenCalled()
  })

  it('refuses a non-http(s) URL rather than making it an iframe src', () => {
    const { container } = renderWidget({ widget: webWidget({ url: 'javascript:alert(1)' }) })
    expect(container.querySelector('iframe')).toBeNull()
    expect(screen.getByText(/http\(s\) URL/i)).toBeInTheDocument()
  })

  it('shows a placeholder when no URL is set', () => {
    renderWidget({ widget: webWidget({}) })
    expect(screen.getByText(/No URL set/i)).toBeInTheDocument()
  })
})

describe('WidgetRenderer multi-value cross-filters', () => {
  it('builds an "in" filter when an incoming cross-filter carries multiple values', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
    render(
      <CrossFilterProvider>
        <MultiFilterInjector widgetId={1} pageId={100} column="region" values={['North', 'South']} />
        <WidgetRenderer widget={barWidget({ id: 2 })} datasetId={10} />
      </CrossFilterProvider>
    )

    await waitFor(() => expect(widgetDataApi.query).toHaveBeenCalled())
    const calls = vi.mocked(widgetDataApi.query).mock.calls
    const [, config] = calls[calls.length - 1]
    expect((config as any).filters).toContainEqual({ column: 'region', op: 'in', value: ['North', 'South'] })
  })
})

describe('WidgetRenderer cross-source column mapping', () => {
  const rels = [{ from_dataset_id: 10, from_column: 'country', to_dataset_id: 20, to_column: 'cust_country' }]
  const dsets = { 20: { id: 20, name: 'Shipments',
    columns: [{ id: 1, name: 'cust_country', dtype: 'categorical', missing_pct: 0, stats: {} },
              { id: 2, name: 'amount', dtype: 'numeric', missing_pct: 0, stats: {} }] } } as never

  it('renames a foreign cross-filter column through the modelled relationship', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
    render(
      <CrossFilterProvider>
        <MultiFilterInjector widgetId={1} pageId={100} column="country" values={['FR']} />
        <WidgetRenderer widget={barWidget({ id: 2, config: { dimension: 'cust_country', dataset_id: 20 } })}
          datasetId={20} datasets={dsets} relationships={rels} />
      </CrossFilterProvider>
    )
    await waitFor(() => expect(widgetDataApi.query).toHaveBeenCalled())
    const [, config] = vi.mocked(widgetDataApi.query).mock.calls.at(-1)!
    expect((config as any).filters).toContainEqual({ column: 'cust_country', op: 'in', value: ['FR'] })
  })

  it('leaves a shared column name untouched and an unmodelled one as-is', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
    render(
      <CrossFilterProvider>
        <MultiFilterInjector widgetId={1} pageId={100} column="amount" values={[5]} />
        <MultiFilterInjector widgetId={3} pageId={100} column="ghost" values={['x']} />
        <WidgetRenderer widget={barWidget({ id: 2, config: { dimension: 'cust_country', dataset_id: 20 } })}
          datasetId={20} datasets={dsets} relationships={rels} />
      </CrossFilterProvider>
    )
    await waitFor(() => expect(widgetDataApi.query).toHaveBeenCalled())
    const [, config] = vi.mocked(widgetDataApi.query).mock.calls.at(-1)!
    expect((config as any).filters).toContainEqual({ column: 'amount', op: 'in', value: [5] })
    expect((config as any).filters).toContainEqual({ column: 'ghost', op: 'in', value: ['x'] })
  })
})

function FilterReader() {
  const { activeFilters } = useCrossFilter()
  return <div data-testid="filters">{JSON.stringify(activeFilters.map(f => ({ column: f.column, value: f.value })))}</div>
}

describe('WidgetRenderer slicer', () => {
  it('renders a slicer as a checkbox list and emits the checked set as a multi-value filter', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [{ name: 'North', value: 3 }, { name: 'South', value: 5 }], sampled: false })
    render(
      <CrossFilterProvider>
        {/* mode pinned: on auto, two values render as a button bar */}
        <WidgetRenderer widget={barWidget({ id: 9, widget_type: 'slicer', config: { dimension: 'region', slicer_mode: 'list' } })} datasetId={10} />
        <FilterReader />
      </CrossFilterProvider>
    )

    expect(await screen.findByText('North')).toBeInTheDocument()
    expect(screen.getByText('South')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('checkbox', { name: /North/i }))
    fireEvent.click(screen.getByRole('checkbox', { name: /South/i }))

    expect(screen.getByTestId('filters')).toHaveTextContent(JSON.stringify([{ column: 'region', value: ['North', 'South'] }]))
  })

  it('auto mode renders few values as a button bar that still filters', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [{ name: 'North' }, { name: 'South' }], sampled: false })
    render(
      <CrossFilterProvider>
        <WidgetRenderer widget={barWidget({ id: 9, widget_type: 'slicer', config: { dimension: 'region' } })} datasetId={10} />
        <FilterReader />
      </CrossFilterProvider>
    )
    const btn = await screen.findByRole('button', { name: 'North' })
    expect(btn).toHaveAttribute('data-slicer-button')
    fireEvent.click(btn)
    expect(btn).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByTestId('filters')).toHaveTextContent('North')
  })

  it('auto mode renders many values as a searchable list', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      rows: Array.from({ length: 50 }, (_, i) => ({ name: `V${i}` })), sampled: false })
    render(
      <CrossFilterProvider>
        <WidgetRenderer widget={barWidget({ id: 9, widget_type: 'slicer', config: { dimension: 'region' } })} datasetId={10} />
      </CrossFilterProvider>
    )
    const search = await screen.findByLabelText('Search slicer values')
    fireEvent.change(search, { target: { value: 'V42' } })
    expect(screen.getByText('V42')).toBeInTheDocument()
    expect(screen.queryByText('V17')).not.toBeInTheDocument()
  })

  // The auto threshold was 40, which meant a 30-item checkbox list arrived
  // with no way to filter it: only as tall as the widget, so most of it was
  // scrolled out of sight, and finding one value meant reading all thirty.
  // Search only ADDS a filter box, so switching early costs a reader nothing.
  it('offers search once a list passes ten values', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      rows: Array.from({ length: 12 }, (_, i) => ({ name: `V${i}` })), sampled: false })
    render(
      <CrossFilterProvider>
        <WidgetRenderer widget={barWidget({ id: 9, widget_type: 'slicer', config: { dimension: 'region' } })} datasetId={10} />
      </CrossFilterProvider>
    )
    expect(await screen.findByLabelText('Search slicer values')).toBeInTheDocument()
  })

  it('leaves a short list as plain checkboxes', async () => {
    // A search box over six values is clutter: the reader can already see them
    // all, so the control would cost space and give nothing back.
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      rows: Array.from({ length: 6 }, (_, i) => ({ name: `V${i}` })), sampled: false })
    render(
      <CrossFilterProvider>
        <WidgetRenderer widget={barWidget({ id: 9, widget_type: 'slicer', config: { dimension: 'region' } })} datasetId={10} />
      </CrossFilterProvider>
    )
    expect(await screen.findByText('V0')).toBeInTheDocument()
    expect(screen.queryByLabelText('Search slicer values')).toBeNull()
  })
})

function hNode(overrides: Partial<HierarchyNode>): HierarchyNode {
  return { id: 0, dataset_id: 10, parent_id: null, name: '', node_type: 'dimension', position: 0, created_at: '2026-01-01', ...overrides }
}

describe('WidgetRenderer hierarchy expand (PBI-style)', () => {
  const geo: HierarchyNode[] = [
    hNode({ id: 10, name: 'Geo', node_type: 'folder' }),
    hNode({ id: 11, name: 'Region', node_type: 'dimension', parent_id: 10, column_name: 'region' }),
    hNode({ id: 12, name: 'Country', node_type: 'dimension', parent_id: 11, column_name: 'country' }),
  ]

  it('expand queries all levels at once via dimension_levels; collapse restores', async () => {
    vi.mocked(widgetDataApi.query).mockReset()
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [{ name: 'EU', value: 3 }], sampled: false })
    renderWidget({
      widget: barWidget({ widget_type: 'list', config: { dimension: 'region', hierarchyNodeId: 11 } }),
      hierarchy: geo,
    })
    const expand = await screen.findByLabelText('Expand hierarchy one level')
    fireEvent.click(expand)
    await waitFor(() => {
      const calls = vi.mocked(widgetDataApi.query).mock.calls
      const [, cfg] = calls[calls.length - 1]
      expect((cfg as any).dimension_levels).toEqual(['region', 'country'])
    })
    // fully expanded: the button disables rather than over-walking the chain
    expect(screen.getByLabelText('Expand hierarchy one level')).toBeDisabled()
    fireEvent.click(screen.getByLabelText('Collapse hierarchy one level'))
    await waitFor(() => {
      const calls = vi.mocked(widgetDataApi.query).mock.calls
      const [, cfg] = calls[calls.length - 1]
      expect((cfg as any).dimension_levels).toBeUndefined()
    })
  })

  it('offers no expand on a granularity chain that reuses one column', async () => {
    vi.mocked(widgetDataApi.query).mockReset()
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [{ name: 2024, value: 1 }], sampled: false })
    const dates: HierarchyNode[] = [
      hNode({ id: 2, name: 'Year', node_type: 'date', column_name: 'order_date', format: 'year' }),
      hNode({ id: 3, name: 'Quarter', node_type: 'date', parent_id: 2, column_name: 'order_date', format: 'quarter' }),
    ]
    renderWidget({
      widget: barWidget({ widget_type: 'list', config: { dimension: 'order_date', dimension_granularity: 'year', hierarchyNodeId: 2 } }),
      hierarchy: dates,
    })
    await screen.findByText('2024')
    expect(screen.queryByLabelText('Expand hierarchy one level')).not.toBeInTheDocument()
  })
})

describe('WidgetRenderer hierarchy drill-down', () => {
  const hierarchy: HierarchyNode[] = [
    hNode({ id: 1, name: 'Dates', node_type: 'folder' }),
    hNode({ id: 2, name: 'Year', node_type: 'date', parent_id: 1, column_name: 'order_date', format: 'year' }),
    hNode({ id: 3, name: 'Quarter', node_type: 'date', parent_id: 2, column_name: 'order_date', format: 'quarter' }),
  ]

  it('drilling into a clicked row re-queries one level deeper and shows a breadcrumb', async () => {
    vi.mocked(widgetDataApi.query).mockReset()
    vi.mocked(widgetDataApi.query)
      .mockResolvedValueOnce({ rows: [{ name: 2024, value: 100 }], sampled: false })
      .mockResolvedValueOnce({ rows: [{ name: '2024-Q1', value: 40 }], sampled: false })
    renderWidget({
      widget: barWidget({ widget_type: 'list', config: { dimension: 'order_date', dimension_granularity: 'year', hierarchyNodeId: 2 } }),
      hierarchy,
    })

    const row = await screen.findByText('2024')
    fireEvent.click(row)

    expect(await screen.findByText('2024-Q1')).toBeInTheDocument()
    const calls = vi.mocked(widgetDataApi.query).mock.calls
    const [, drilledConfig] = calls[calls.length - 1]
    expect((drilledConfig as any).dimension_granularity).toBe('quarter')
    expect((drilledConfig as any).filters).toContainEqual({ column: 'order_date', op: 'eq', value: 2024, granularity: 'year' })
    expect(screen.getByText('2024')).toBeInTheDocument()
  })

  it('clicking the "All" breadcrumb resets back to the top level', async () => {
    vi.mocked(widgetDataApi.query).mockReset()
    vi.mocked(widgetDataApi.query)
      .mockResolvedValueOnce({ rows: [{ name: 2024, value: 100 }], sampled: false })
      .mockResolvedValueOnce({ rows: [{ name: '2024-Q1', value: 40 }], sampled: false })
      .mockResolvedValueOnce({ rows: [{ name: 2024, value: 100 }], sampled: false })
    renderWidget({
      widget: barWidget({ widget_type: 'list', config: { dimension: 'order_date', dimension_granularity: 'year', hierarchyNodeId: 2 } }),
      hierarchy,
    })
    fireEvent.click(await screen.findByText('2024'))
    await screen.findByText('2024-Q1')

    fireEvent.click(screen.getByRole('button', { name: 'All' }))

    await waitFor(() => expect(screen.queryByRole('button', { name: 'All' })).not.toBeInTheDocument())
  })

  it('a non-hierarchy widget click behaves exactly as before (no breadcrumb, no drill re-query)', async () => {
    vi.mocked(widgetDataApi.query).mockReset()
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [{ name: 'North', value: 5 }], sampled: false })
    renderWidget({ widget: barWidget({ widget_type: 'list' }), hierarchy })
    fireEvent.click(await screen.findByText('North'))
    expect(screen.queryByRole('button', { name: 'All' })).not.toBeInTheDocument()
  })
})

describe('WidgetRenderer button actions', () => {
  it('calls onNavigateToPage when clicked with a navigate action configured', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
    const onNavigateToPage = vi.fn()
    render(
      <CrossFilterProvider>
        <WidgetRenderer widget={barWidget({ widget_type: 'button', config: { label: 'Go', action: 'navigate', actionPageId: 200 } })}
          datasetId={10} onNavigateToPage={onNavigateToPage} />
      </CrossFilterProvider>
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Go' }))
    expect(onNavigateToPage).toHaveBeenCalledWith(200)
  })

  it('calls onApplyBookmark with the matching bookmark when clicked with a bookmark action configured', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
    const onApplyBookmark = vi.fn()
    const bookmark = { id: 7, report_id: 1, name: 'Q1 view', position: 0,
      state: { pageId: 100, activeFilters: [], promptValues: {}, hiddenWidgetIds: [] }, created_at: '2026-01-01' }
    render(
      <CrossFilterProvider>
        <WidgetRenderer widget={barWidget({ widget_type: 'button', config: { label: 'Apply', action: 'bookmark', actionBookmarkId: 7 } })}
          datasetId={10} bookmarks={[bookmark]} onApplyBookmark={onApplyBookmark} />
      </CrossFilterProvider>
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Apply' }))
    expect(onApplyBookmark).toHaveBeenCalledWith(bookmark)
  })

  it('does nothing when clicked with no action configured', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
    const onNavigateToPage = vi.fn()
    const onApplyBookmark = vi.fn()
    render(
      <CrossFilterProvider>
        <WidgetRenderer widget={barWidget({ widget_type: 'button', config: { label: 'Idle' } })}
          datasetId={10} onNavigateToPage={onNavigateToPage} onApplyBookmark={onApplyBookmark} />
      </CrossFilterProvider>
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Idle' }))
    expect(onNavigateToPage).not.toHaveBeenCalled()
    expect(onApplyBookmark).not.toHaveBeenCalled()
  })
})

describe('WidgetRenderer report-link and set-parameter button actions', () => {
  it('navigates the window to the target report on a report action', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
    const assign = vi.fn()
    const original = window.location
    Object.defineProperty(window, 'location', { value: { ...original, assign }, writable: true })
    try {
      render(
        <CrossFilterProvider>
          <WidgetRenderer widget={barWidget({ widget_type: 'button', config: { label: 'Open', action: 'report', actionReportId: 12 } })}
            datasetId={10} />
        </CrossFilterProvider>
      )
      fireEvent.click(await screen.findByRole('button', { name: 'Open' }))
      expect(assign).toHaveBeenCalledWith('/reports/12')
    } finally {
      Object.defineProperty(window, 'location', { value: original, writable: true })
    }
  })

  it('refuses a non-numeric report id — stored config is client input', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
    const assign = vi.fn()
    const original = window.location
    Object.defineProperty(window, 'location', { value: { ...original, assign }, writable: true })
    try {
      render(
        <CrossFilterProvider>
          <WidgetRenderer widget={barWidget({ widget_type: 'button', config: { label: 'Bad', action: 'report', actionReportId: '../admin' } })}
            datasetId={10} />
        </CrossFilterProvider>
      )
      fireEvent.click(await screen.findByRole('button', { name: 'Bad' }))
      expect(assign).not.toHaveBeenCalled()
    } finally {
      Object.defineProperty(window, 'location', { value: original, writable: true })
    }
  })

  it('calls onSetParameter with the configured name and value', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
    const onSetParameter = vi.fn()
    render(
      <CrossFilterProvider>
        <WidgetRenderer widget={barWidget({ widget_type: 'button', config: { label: 'Set', action: 'set_param', actionParamName: 'threshold', actionParamValue: '100' } })}
          datasetId={10} onSetParameter={onSetParameter} />
      </CrossFilterProvider>
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Set' }))
    expect(onSetParameter).toHaveBeenCalledWith('threshold', '100')
  })
})

describe('WidgetRenderer parameter placeholders in text', () => {
  it('substitutes {{@name}} with the live parameter value', () => {
    render(
      <CrossFilterProvider>
        <WidgetRenderer widget={barWidget({ widget_type: 'text', config: { content: 'Orders above {{@threshold}} only' } })}
          datasetId={10} parameters={{ threshold: 250 }} />
      </CrossFilterProvider>
    )
    expect(screen.getByText('Orders above 250 only')).toBeInTheDocument()
  })

  it('shows an em dash for an unset parameter rather than raw template braces', () => {
    render(
      <CrossFilterProvider>
        <WidgetRenderer widget={barWidget({ widget_type: 'text', config: { content: 'Cutoff: {{@missing}}' } })}
          datasetId={10} parameters={{}} />
      </CrossFilterProvider>
    )
    expect(screen.getByText('Cutoff: —')).toBeInTheDocument()
  })
})

describe('WidgetRenderer multi-select', () => {
  it('renders an outline when isMultiSelected is true, and none when false', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
    const selectedRender = renderWidget({ isMultiSelected: true })
    const selectedOuter = selectedRender.container.firstElementChild as HTMLElement
    expect(selectedOuter.style.outline).toBeTruthy()

    const unselectedRender = renderWidget({ isMultiSelected: false })
    const unselectedOuter = unselectedRender.container.firstElementChild as HTMLElement
    expect(unselectedOuter.style.outline).toBeFalsy()
  })

  it('passes the click MouseEvent through onSelect so the caller can check e.shiftKey', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
    const onSelect = vi.fn()
    const { container } = renderWidget({ onSelect })
    fireEvent.click(container.firstElementChild as Element, { shiftKey: true })
    expect(onSelect).toHaveBeenCalled()
    expect(onSelect.mock.calls[0][0].shiftKey).toBe(true)
  })
})

describe('WidgetRenderer matrix', () => {
  it('renders a matrix widget through the same pivoted-table layout as crosstab', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      type: 'crosstab', columns: ['region', 'A', 'B'], rows: [['East', 10, 20]], total: 1, sampled: false,
    })
    renderWidget({ widget: barWidget({ widget_type: 'matrix', config: { dimension: 'region', dimension2: 'product', measure: 'sales' } }) })
    expect(await screen.findByText('East')).toBeInTheDocument()
    expect(screen.getByText('region')).toBeInTheDocument()
  })
})

describe('WidgetRenderer card', () => {
  it('renders one label+value row per measure', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [{ name: 'revenue', value: 60 }, { name: 'cost', value: 20 }], sampled: false })
    renderWidget({ widget: barWidget({ widget_type: 'card', config: { measures: ['revenue', 'cost'] } }) })
    // Number formatting goes through Intl.toLocaleString, whose digit glyphs depend on
    // the environment's default locale — compute the expected string the same way rather
    // than hardcoding ASCII digits.
    const fmt = (n: number) => n.toLocaleString(undefined, { maximumFractionDigits: 2 })
    expect(await screen.findByText('revenue')).toBeInTheDocument()
    expect(screen.getByText(fmt(60))).toBeInTheDocument()
    expect(screen.getByText('cost')).toBeInTheDocument()
    expect(screen.getByText(fmt(20))).toBeInTheDocument()
  })
})

describe('WidgetRenderer image', () => {
  it('renders an img element sourced from config.url', async () => {
    renderWidget({ widget: barWidget({ widget_type: 'image', config: { url: 'https://example.com/pic.png', alt: 'A pic' } }) })
    const img = await screen.findByAltText('A pic')
    expect(img).toHaveAttribute('src', 'https://example.com/pic.png')
  })

  it('shows an empty-state placeholder when no url is configured', () => {
    renderWidget({ widget: barWidget({ widget_type: 'image', config: {} }) })
    expect(screen.getByText(/No image/i)).toBeInTheDocument()
  })

  it('does not query widget data for an image widget', async () => {
    vi.mocked(widgetDataApi.query).mockClear()
    renderWidget({ widget: barWidget({ widget_type: 'image', config: { url: 'https://example.com/pic.png' } }) })
    await screen.findByAltText('')
    expect(widgetDataApi.query).not.toHaveBeenCalled()
  })
})

describe('WidgetRenderer shape', () => {
  it('renders a rectangle shape with the configured fill and border color', () => {
    const { container } = renderWidget({ widget: barWidget({ widget_type: 'shape', config: { shape: 'rectangle', fill: '#ff0000', stroke: '#0000ff' } }) })
    const shapeEl = container.querySelector('[data-testid="shape-render"]') as HTMLElement
    expect(shapeEl.style.backgroundColor).toBe('rgb(255, 0, 0)')
    expect(shapeEl.style.borderColor).toBe('rgb(0, 0, 255)')
  })

  it('renders a circle as a fully rounded shape', () => {
    const { container } = renderWidget({ widget: barWidget({ widget_type: 'shape', config: { shape: 'circle' } }) })
    const shapeEl = container.querySelector('[data-testid="shape-render"]') as HTMLElement
    expect(shapeEl.style.borderRadius).toBe('50%')
  })
})

describe('WidgetRenderer drillthrough', () => {
  it('shows a drill-through button after clicking a data point, and calls onDrillthrough with the clicked value', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [{ name: 'North', value: 5 }], sampled: false })
    const onDrillthrough = vi.fn()
    const pages = [reportPage(), reportPage({ id: 200, name: 'Details', page_type: 'drillthrough' })]
    renderWidget({
      widget: barWidget({ widget_type: 'list', config: { dimension: 'region', drillthroughPageId: 200 } }),
      pages, onDrillthrough,
    })

    const row = await screen.findByText('North')
    fireEvent.click(row)

    const btn = await screen.findByRole('button', { name: /Drill through/i })
    fireEvent.click(btn)
    expect(onDrillthrough).toHaveBeenCalledWith(200, 'North')
  })

  it('drills on a double-click, with the value the reader clicked (SAS: click selects, double-click drills)', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [{ name: 'North', value: 5 }], sampled: false })
    const onDrillthrough = vi.fn()
    const pages = [reportPage(), reportPage({ id: 200, name: 'Details', page_type: 'popup' })]
    renderWidget({
      widget: barWidget({ widget_type: 'list', config: { dimension: 'region', drillthroughPageId: 200 } }),
      pages, onDrillthrough,
    })
    const row = await screen.findByText('North')
    fireEvent.click(row)
    fireEvent.click(row) // the second click of the double-click toggles the selection off
    fireEvent.doubleClick(row)
    expect(onDrillthrough).toHaveBeenCalledWith(200, 'North')
  })

  it('does not show a drill-through button when no drillthroughPageId is configured', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [{ name: 'North', value: 5 }], sampled: false })
    renderWidget({ widget: barWidget({ widget_type: 'list', config: { dimension: 'region' } }), pages: [reportPage()] })

    const row = await screen.findByText('North')
    fireEvent.click(row)
    expect(screen.queryByRole('button', { name: /Drill through/i })).not.toBeInTheDocument()
  })
})

describe('WidgetRenderer drillthrough context menu', () => {
  it('shows a right-click context menu with a Drill through option once a data point is selected, and selecting it navigates', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [{ name: 'North', value: 5 }], sampled: false })
    const onDrillthrough = vi.fn()
    const pages = [reportPage(), reportPage({ id: 200, name: 'Details', page_type: 'drillthrough' })]
    const { container } = renderWidget({
      widget: barWidget({ widget_type: 'list', config: { dimension: 'region', drillthroughPageId: 200 } }),
      pages, onDrillthrough,
    })

    fireEvent.click(await screen.findByText('North'))
    fireEvent.contextMenu(container.firstElementChild as Element)

    const menuItem = await screen.findByRole('menuitem', { name: /Drill through to Details/i })
    fireEvent.click(menuItem)

    expect(onDrillthrough).toHaveBeenCalledWith(200, 'North')
    expect(screen.queryByRole('menuitem')).not.toBeInTheDocument()
  })

  it('offers export but not drill-through when no data point is selected yet', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [{ name: 'North', value: 5 }], sampled: false })
    const pages = [reportPage(), reportPage({ id: 200, name: 'Details', page_type: 'drillthrough' })]
    const { container } = renderWidget({
      widget: barWidget({ widget_type: 'list', config: { dimension: 'region', drillthroughPageId: 200 } }),
      pages,
    })
    await screen.findByText('North')

    fireEvent.contextMenu(container.firstElementChild as Element)

    // Drill-through needs a selected point to drill FROM; export does not. The menu
    // used to require a selection to open at all, which left most widgets with no
    // context menu and no way to reach export.
    expect(await screen.findByRole('menuitem', { name: /Export data as CSV/i })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: /Drill through/i })).not.toBeInTheDocument()
  })

  it('hides export menu items when allowExport is false (S4: guest view)', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [{ name: 'North', value: 5 }], sampled: false })
    const { container } = renderWidget({
      widget: barWidget({ widget_type: 'list', config: { dimension: 'region' } }),
      allowExport: false,
    })
    await screen.findByText('North')

    fireEvent.contextMenu(container.firstElementChild as Element)

    expect(screen.queryByRole('menuitem', { name: /Export data as CSV/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: /Export data as Excel/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: /Export as image/i })).not.toBeInTheDocument()
  })

  it('closes the context menu when clicking elsewhere without choosing an item', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [{ name: 'North', value: 5 }], sampled: false })
    const pages = [reportPage(), reportPage({ id: 200, name: 'Details', page_type: 'drillthrough' })]
    const { container } = renderWidget({
      widget: barWidget({ widget_type: 'list', config: { dimension: 'region', drillthroughPageId: 200 } }),
      pages,
    })
    fireEvent.click(await screen.findByText('North'))
    fireEvent.contextMenu(container.firstElementChild as Element)
    await screen.findAllByRole('menuitem')      // drill-through plus the two exports

    fireEvent.click(document.body)
    expect(screen.queryByRole('menuitem')).not.toBeInTheDocument()
  })
})

describe('WidgetRenderer display rules', () => {
  it('sends report rules ahead of widget rules so the widget rule wins', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
    const widgetRule = { id: 'w', kind: 'expression' as const, target: 'mark' as const,
      expression: 'value > 1000', style: { fill: '#f87171' } }
    const reportRules = [{ id: 'r', kind: 'expression' as const, target: 'mark' as const,
      expression: 'value > 0', style: { fill: '#aaa' } }]

    renderWidget({
      widget: barWidget({ config: { dimension: 'region', measure: 'sales', display_rules: [widgetRule] } }),
      reportDisplayRules: reportRules,
    })

    await waitFor(() => expect(widgetDataApi.query).toHaveBeenCalled())
    const calls = vi.mocked(widgetDataApi.query).mock.calls
    const sentConfig = calls[calls.length - 1][1] as any
    expect(sentConfig.display_rules.map((r: any) => r.id)).toEqual(['r', 'w'])
  })

  it('does not set display_rules on the sent config when there are no rules', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
    renderWidget({ widget: barWidget({ config: { dimension: 'region' } }) })

    await waitFor(() => expect(widgetDataApi.query).toHaveBeenCalled())
    const calls = vi.mocked(widgetDataApi.query).mock.calls
    const sentConfig = calls[calls.length - 1][1] as any
    expect(sentConfig.display_rules).toBeUndefined()
  })
})

describe('WidgetRenderer tooltip preview', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('shows a floating preview of the tooltip page on hover, and hides it on mouse-leave', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
    const tooltipWidget: Widget = {
      id: 50, page_id: 300, widget_type: 'text', title: 'Details', config: { content: 'Extra info' },
      layout: { x: 0, y: 0, w: 4, h: 2 }, created_at: '2026-01-01',
    }
    const pages = [reportPage(), reportPage({ id: 300, name: 'Tip', page_type: 'tooltip', widgets: [tooltipWidget] })]
    const { container } = renderWidget({
      widget: barWidget({ widget_type: 'text', config: { content: 'Main', tooltipPageId: 300 } }),
      pages,
    })

    fireEvent.mouseEnter(container.firstElementChild as Element)
    await act(async () => { vi.advanceTimersByTime(200) })
    expect(screen.getByText('Extra info')).toBeInTheDocument()

    fireEvent.mouseLeave(container.firstElementChild as Element)
    expect(screen.queryByText('Extra info')).not.toBeInTheDocument()
  })

  it('clamps the preview position so it stays within the viewport when hovering near an edge', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
    const tooltipWidget: Widget = {
      id: 50, page_id: 300, widget_type: 'text', title: 'Details', config: { content: 'Extra info' },
      layout: { x: 0, y: 0, w: 4, h: 2 }, created_at: '2026-01-01',
    }
    const pages = [reportPage(), reportPage({ id: 300, name: 'Tip', page_type: 'tooltip', widgets: [tooltipWidget] })]
    const { container } = renderWidget({
      widget: barWidget({ widget_type: 'text', config: { content: 'Main', tooltipPageId: 300 } }),
      pages,
    })

    // Near the bottom-right corner of jsdom's default 1024x768 viewport.
    fireEvent.mouseEnter(container.firstElementChild as Element, { clientX: 1000, clientY: 760 })
    await act(async () => { vi.advanceTimersByTime(200) })

    const preview = screen.getByText('Extra info').closest('[style*="position: fixed"]') as HTMLElement
    const left = parseFloat(preview.style.left)
    const top = parseFloat(preview.style.top)
    expect(left).toBeLessThanOrEqual(window.innerWidth - 320)
    expect(top).toBeLessThanOrEqual(window.innerHeight - 400)
  })

  it('does not wire hover/drillthrough on preview widgets, even if configured', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
    const pages = [reportPage(), reportPage({ id: 300, name: 'Tip', page_type: 'tooltip' })]
    const { container } = renderWidget({
      widget: barWidget({ widget_type: 'text', config: { content: 'Preview widget', tooltipPageId: 300 } }),
      pages, isPreview: true,
    })

    fireEvent.mouseEnter(container.firstElementChild as Element)
    await act(async () => { vi.advanceTimersByTime(200) })
    expect(container.querySelectorAll('[style*="position: fixed"]').length).toBe(0)
  })
})

describe('WidgetRenderer display-rule styles', () => {
  it('in edit mode, hides the widget body behind a placeholder when a visibility rule matched, so the widget stays selectable', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      type: 'series', rows: [{ name: 'US', value: 5 }], total: 1,
      rule_styles: { rows: [null], cells: {}, widget: { hidden: true } }, rule_errors: [],
    } as any)

    renderWidget({ editMode: true })

    expect(await screen.findByTestId('widget-hidden-by-rule')).toBeInTheDocument()
  })

  it('in view mode, renders nothing at all when a visibility rule matched -- not an empty titled box', async () => {
    // The widget must vanish completely, not just its body: a border/title around an
    // empty body reads as a broken widget, not an intentionally hidden one.
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      type: 'series', rows: [{ name: 'US', value: 5 }], total: 1,
      rule_styles: { rows: [null], cells: {}, widget: { hidden: true } }, rule_errors: [],
    } as any)

    const { container } = renderWidget({})

    await waitFor(() => expect(widgetDataApi.query).toHaveBeenCalled())
    expect(screen.queryByTestId('widget-hidden-by-rule')).not.toBeInTheDocument()
    expect(screen.queryByText('US')).not.toBeInTheDocument()
    expect(screen.queryByText('Sales')).not.toBeInTheDocument()  // the widget's title
    expect(container.querySelector('[style]')).not.toBeInTheDocument()  // no frame at all
  })

  it('paints the widget container background from a widget-level rule style', async () => {
    // Regression: DisplayRulesPanel used to write a "Widget background" rule's colour to
    // style.fill instead of style.background, so this key never landed here and nothing
    // painted. The panel now keys by target; this asserts the consumer side of that
    // contract — a `rule_styles.widget.background` value actually reaches the container.
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      type: 'series', rows: [{ name: 'US', value: 5 }], total: 1,
      rule_styles: { rows: [null], cells: {}, widget: { background: '#123456' } }, rule_errors: [],
    } as any)

    const { container } = renderWidget({ widget: barWidget({ widget_type: 'list', config: { dimension: 'region' } }) })

    await screen.findByText('US')
    const outer = container.firstElementChild as HTMLElement
    expect(outer).toHaveStyle({ background: '#123456' })
  })

  it('paints a table cell with the style the engine resolved', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      type: 'table', columns: ['region', 'sales'], rows: [['US', 1500]], total: 1,
      rule_styles: { rows: [null], cells: { '0': { sales: { fill: '#f87171' } } }, widget: {} },
      rule_errors: [],
    } as any)

    renderWidget({ widget: barWidget({ widget_type: 'table' }) })

    // The value now renders inside a span (alongside an optional icon/data-bar),
    // so the styled element is the value's ANCESTOR cell, not the text node itself.
    const value = await screen.findByText('1500')
    expect(value.closest('td')).toHaveStyle({ background: '#f87171' })
  })

  it('layers the selection tint on top of a rule fill on a list row instead of replacing it', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      type: 'series', rows: [{ name: 'US', value: 5 }, { name: 'CA', value: 3 }], total: 2,
      rule_styles: { rows: [{ fill: '#f87171' }, null], cells: {}, widget: {} }, rule_errors: [],
    } as any)

    renderWidget({ widget: barWidget({ widget_type: 'list', config: { dimension: 'region' } }) })

    const nameSpan = await screen.findByText('US')
    fireEvent.click(nameSpan)

    const row = nameSpan.closest('div') as HTMLElement
    // The rule's fill must still be the background once the row is selected —
    // selection is a translucent tint layered on top (box-shadow), not a swap
    // of the rule's colour.
    expect(row).toHaveStyle({ backgroundColor: 'rgb(248, 113, 113)' })
    expect(row.style.boxShadow).toContain('color-mix(in srgb, var(--accent) 12%, transparent)')
  })
})

describe('WidgetRenderer totals row', () => {
  it('renders a totals row beneath the table when the server sent totals', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      type: 'table', columns: ['region', 'sales'],
      rows: [['US', 100], ['CA', 200]], total: 2, totals: [null, 1500],
    } as any)

    render(
      <CrossFilterProvider>
        <WidgetRenderer widget={{ ...barWidget(), widget_type: 'table' }} datasetId={1} />
      </CrossFilterProvider>
    )

    const footRow = await screen.findByTestId('table-totals-row')
    expect(footRow).toHaveTextContent('1500')
    expect(footRow).toHaveTextContent('Total')
  })

  it('prints the total of a numeric first column instead of throwing it away', async () => {
    // A raw table can perfectly well start with a numeric column (columns:
    // ['sales','units']). The backend computes totals[0] for it, and the renderer used
    // to overwrite that cell with the word "Total" unconditionally — discarding a real
    // number. The label is only the fallback for a column with no total of its own.
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      type: 'table', columns: ['sales', 'units'],
      rows: [[100, 1], [200, 2]], total: 2, totals: [1500, 15],
    } as any)

    render(
      <CrossFilterProvider>
        <WidgetRenderer widget={{ ...barWidget(), widget_type: 'table' }} datasetId={1} />
      </CrossFilterProvider>
    )

    const footRow = await screen.findByTestId('table-totals-row')
    const cells = footRow.querySelectorAll('td')
    expect(cells[0]).toHaveTextContent('1500')
    expect(cells[1]).toHaveTextContent('15')
    // The number is what is PRINTED — the label survives only as the off-screen
    // accessible name asserted in the next test, never painted over the total.
    expect(cells[0].textContent).toContain('1500')
  })

  it('keeps an accessible name on the totals row when the label is displaced', async () => {
    // With a numeric first column and row numbers off there is no visible "Total"
    // anywhere, and a title attribute is not a reliable accessible name.
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      type: 'table', columns: ['sales', 'units'],
      rows: [[100, 1]], total: 1, totals: [1500, 15],
    } as any)

    render(
      <CrossFilterProvider>
        <WidgetRenderer widget={{ ...barWidget(), widget_type: 'table' }} datasetId={1} />
      </CrossFilterProvider>
    )

    const footRow = await screen.findByRole('row', { name: /total/i })
    expect(footRow).toHaveAttribute('data-testid', 'table-totals-row')
    // ...and the word reaches a screen reader from the cell itself, not just the row.
    expect(footRow.querySelectorAll('td')[0].textContent).toContain('Total')
  })

  it('still labels the totals row when its first column has no total', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      type: 'table', columns: ['region', 'sales'],
      rows: [['US', 100]], total: 1, totals: [null, 100],
    } as any)

    render(
      <CrossFilterProvider>
        <WidgetRenderer widget={{ ...barWidget(), widget_type: 'table' }} datasetId={1} />
      </CrossFilterProvider>
    )

    const footRow = await screen.findByTestId('table-totals-row')
    expect(footRow.querySelectorAll('td')[0]).toHaveTextContent('Total')
  })

  it('moves the label into the row-number cell when the first column carries a number', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      type: 'table', columns: ['sales', 'units'],
      rows: [[100, 1]], total: 1, totals: [100, 1],
    } as any)

    render(
      <CrossFilterProvider>
        <WidgetRenderer
          widget={{ ...barWidget(), widget_type: 'table', config: { table_row_numbers: true } }}
          datasetId={1}
        />
      </CrossFilterProvider>
    )

    const footRow = await screen.findByTestId('table-totals-row')
    expect(footRow.querySelectorAll('td')[0]).toHaveTextContent('Total')
    expect(footRow.querySelectorAll('td')[1]).toHaveTextContent('100')
  })

  it('says so when the server had to suppress the totals row rather than total a sample', async () => {
    // DirectQuery above the row cap on a grouped table: the only number available
    // locally would describe a 10,000-row sample. The server drops the row and sets
    // totals_unavailable; the widget must say that out loud, or the author reads a
    // missing row as a checkbox that did nothing.
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      type: 'series', rows: [{ name: 'US', value: 100 }], total: 4000000,
      totals_unavailable: 'sampled',
    } as any)

    render(
      <CrossFilterProvider>
        <WidgetRenderer
          widget={{ ...barWidget(), widget_type: 'table', config: { dimension: 'region', show_totals: true } }}
          datasetId={1}
        />
      </CrossFilterProvider>
    )

    expect(await screen.findByTestId('table-totals-unavailable')).toBeInTheDocument()
    expect(screen.queryByTestId('table-totals-row')).not.toBeInTheDocument()
  })

  it('renders a totals row for a grouped table, whose rows are objects not arrays', async () => {
    // The shape a table configured with the required Dimension actually returns.
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      type: 'series', dimension: 'region', measure: 'sales',
      rows: [{ name: 'US', value: 100 }, { name: 'CA', value: 200 }],
      total: 2, totals: [null, 1500],
    } as any)

    render(
      <CrossFilterProvider>
        <WidgetRenderer widget={{ ...barWidget(), widget_type: 'table' }} datasetId={1} />
      </CrossFilterProvider>
    )

    const footRow = await screen.findByTestId('table-totals-row')
    expect(footRow).toHaveTextContent('Total')
    expect(footRow).toHaveTextContent('1500')
  })

  it('renders no totals row when the server sent none', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      type: 'table', columns: ['region', 'sales'], rows: [['US', 100]], total: 1,
    } as any)

    render(
      <CrossFilterProvider>
        <WidgetRenderer widget={{ ...barWidget(), widget_type: 'table' }} datasetId={1} />
      </CrossFilterProvider>
    )

    await screen.findByText('US')
    expect(screen.queryByTestId('table-totals-row')).not.toBeInTheDocument()
  })
})

describe('WidgetRenderer totals placement and basis', () => {
  const crosstab = {
    type: 'crosstab', columns: ['region', 'Q1', 'Q2', '__total__'],
    rows: [['A', 15, 60, 30], ['B', 100, 0, 100]], total: 2,
    totals: [null, 43.3, 60, 47.5],
  }
  function renderWith(data: Record<string, unknown>, config: Record<string, unknown>) {
    vi.mocked(widgetDataApi.query).mockResolvedValue(data as any)
    return render(
      <CrossFilterProvider>
        <WidgetRenderer widget={{ ...barWidget(), widget_type: 'crosstab', config }} datasetId={1} />
      </CrossFilterProvider>
    )
  }

  it("draws the totals row above the data when placement is 'before'", async () => {
    const { container } = renderWith(crosstab, { show_totals: true, totals_position: 'before' })

    const totalsRow = await screen.findByTestId('table-totals-row')
    // In <thead>, so every data row keeps its index -- banding, display rules and
    // clicks are keyed off it.
    expect(totalsRow.closest('thead')).not.toBeNull()
    expect(container.querySelector('tfoot')).toBeNull()
    expect(container.querySelectorAll('tbody tr')[0]).toHaveTextContent('A')
  })

  it('keeps the totals row after the data when placement is unset -- every saved table', async () => {
    const { container } = renderWith(crosstab, { show_totals: true })

    const totalsRow = await screen.findByTestId('table-totals-row')
    expect(totalsRow.closest('tfoot')).not.toBeNull()
    expect(container.querySelectorAll('thead th')[3]).toHaveTextContent('__total__')
  })

  it("puts the row subtotal column before the value columns when placement is 'before'", async () => {
    const { container } = renderWith(crosstab, { show_totals: true, totals_position: 'before' })

    await screen.findByTestId('table-totals-row')
    const headers = [...container.querySelectorAll('thead th')].map(th => th.textContent)
    expect(headers).toEqual(['region', '__total__', 'Q1', 'Q2'])
    // Cells and totals move with their header, not just the header.
    const firstRow = [...container.querySelectorAll('tbody tr')[0].querySelectorAll('td')].map(td => td.textContent)
    expect(firstRow).toEqual(['A', '30', '15', '60'])
    const totals = [...screen.getByTestId('table-totals-row').querySelectorAll('td')].map(td => td.textContent)
    expect(totals[1]).toContain('47.5')
  })

  it("labels an all-rows total when the page shows only some of the groups", async () => {
    renderWith({
      type: 'series', rows: [{ name: 'B', value: 100 }], total: 4,
      totals: [null, 47.5], totals_shown: [null, 100],
      totals_basis: { unit: 'groups', shown: 1, of: 2, truncated: true, suppressed_excluded: false },
    }, { show_totals: true })

    const totalsRow = await screen.findByTestId('table-totals-row')
    expect(totalsRow).toHaveTextContent('Total (all rows)')
    expect(totalsRow).toHaveTextContent('47.5')
  })

  it("shows the shown-rows total, labelled as such, when the author picks that basis", async () => {
    renderWith({
      type: 'series', rows: [{ name: 'B', value: 100 }], total: 4,
      totals: [null, 47.5], totals_shown: [null, 100],
      totals_basis: { unit: 'groups', shown: 1, of: 2, truncated: true, suppressed_excluded: false },
    }, { show_totals: true, totals_scope: 'shown' })

    const totalsRow = await screen.findByTestId('table-totals-row')
    expect(totalsRow).toHaveTextContent('Total (1 shown)')
    expect(totalsRow).toHaveTextContent('100')
    expect(totalsRow).not.toHaveTextContent('47.5')
  })

  it('says why when a quick calculation withholds the total', async () => {
    renderWith({ type: 'series', rows: [{ name: 'B', value: 1 }], total: 4,
      totals_unavailable: 'quick_calc' }, { show_totals: true })

    expect(await screen.findByTestId('table-totals-unavailable')).toHaveTextContent(/quick calculation/i)
  })

  it('says why when suppression withholds the total', async () => {
    renderWith({ type: 'series', rows: [{ name: 'B', value: 1 }], total: 4,
      totals_unavailable: 'suppressed' }, { show_totals: true })

    expect(await screen.findByTestId('table-totals-unavailable')).toHaveTextContent(/suppressed/i)
  })
})

describe('WidgetRenderer table cell styling', () => {
  async function renderTable(config: Record<string, unknown>) {
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      type: 'table', columns: ['region', 'sales'],
      rows: [['US', 100], ['CA', 200]], total: 2,
    } as any)
    const r = render(
      <CrossFilterProvider>
        <WidgetRenderer widget={{ ...barWidget(), widget_type: 'table', config }} datasetId={1} />
      </CrossFilterProvider>
    )
    await screen.findByText('US')
    return r
  }

  it('adds a row-number column only when asked', async () => {
    const { container, unmount } = await renderTable({})
    expect(container.querySelectorAll('thead th').length).toBe(2)
    unmount()

    const { container: c2 } = await renderTable({ table_row_numbers: true })
    expect(c2.querySelectorAll('thead th').length).toBe(3)
    expect(c2.querySelectorAll('tbody tr:first-child td')[0]).toHaveTextContent('1')
  })

  it('bands alternate rows only when asked', async () => {
    const { container, unmount } = await renderTable({})
    const plain = container.querySelectorAll('tbody tr')[1] as HTMLElement
    expect(plain.style.background).toBe('')
    unmount()

    const { container: c2 } = await renderTable({ table_banding: true })
    const banded = c2.querySelectorAll('tbody tr')[1] as HTMLElement
    expect(banded.style.background).not.toBe('')
  })

  it('a rule-painted cell still wins over banding', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      type: 'table', columns: ['region', 'sales'], rows: [['US', 100], ['CA', 200]], total: 2,
      rule_styles: { rows: [null, null], cells: { '1': { sales: { fill: '#f87171' } } }, widget: {} },
      rule_errors: [],
    } as any)
    const { container } = render(
      <CrossFilterProvider>
        <WidgetRenderer widget={{ ...barWidget(), widget_type: 'table', config: { table_banding: true } }} datasetId={1} />
      </CrossFilterProvider>
    )
    await screen.findByText('US')
    const cell = container.querySelectorAll('tbody tr')[1].querySelectorAll('td')[1] as HTMLElement
    expect(cell.style.background).toContain('248')   // rgb(248, 113, 113) — normalised from #f87171
  })

  it('keeps the header, a body row, and the totals footer the same width when row numbers and totals are both on', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      type: 'table', columns: ['region', 'sales'],
      rows: [['US', 100], ['CA', 200]], total: 2, totals: [null, 300],
    } as any)
    const { container } = render(
      <CrossFilterProvider>
        <WidgetRenderer
          widget={{ ...barWidget(), widget_type: 'table', config: { table_row_numbers: true, show_totals: true } }}
          datasetId={1}
        />
      </CrossFilterProvider>
    )
    await screen.findByText('US')
    const headerCount = container.querySelectorAll('thead th').length
    const bodyRowCount = container.querySelectorAll('tbody tr')[0].querySelectorAll('td').length
    const footRow = await screen.findByTestId('table-totals-row')
    const footCount = footRow.querySelectorAll('td').length
    expect(headerCount).toBe(3)
    expect(bodyRowCount).toBe(3)
    expect(footCount).toBe(3)
  })
})

describe('WidgetRenderer totals-row accessible name', () => {
  it('names the row only when a numeric first column has displaced the visible label', async () => {
    // totals[0] is a number, so no cell renders the word "Total" -- without a name here
    // the row would be announced as bare numbers.
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      type: 'table', columns: ['qty', 'amount'], rows: [[1, 2]], totals: [1, 2], total: 1,
    } as any)
    render(
      <CrossFilterProvider>
        <WidgetRenderer widget={{ ...barWidget(), widget_type: 'table', config: { show_totals: true } }} datasetId={1} />
      </CrossFilterProvider>
    )
    const footRow = await screen.findByTestId('table-totals-row')
    expect(footRow).toHaveAttribute('aria-label', 'Total')
  })

  it('leaves the row unnamed when the label is visible, so it is not announced twice', async () => {
    // totals[0] is null, so the first cell renders "Total" itself. An aria-label here
    // would make a screen reader say "Total" for the row and then read a cell saying
    // "Total" again. Asserting the ABSENCE is the point: the previous implementation
    // set the attribute unconditionally and this is the only case that distinguishes them.
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      type: 'table', columns: ['region', 'amount'], rows: [['US', 2]], totals: [null, 2], total: 1,
    } as any)
    render(
      <CrossFilterProvider>
        <WidgetRenderer widget={{ ...barWidget(), widget_type: 'table', config: { show_totals: true } }} datasetId={1} />
      </CrossFilterProvider>
    )
    const footRow = await screen.findByTestId('table-totals-row')
    expect(footRow).not.toHaveAttribute('aria-label')
    expect(footRow).toHaveTextContent('Total')
  })
})

describe('WidgetRenderer chrome styling', () => {
  it('applies a configured background and border to the widget chrome', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ type: 'series', rows: [{ name: 'US', value: 1 }], total: 1 } as any)
    const { container } = render(
      <CrossFilterProvider>
        <WidgetRenderer widget={{ ...barWidget(), config: { widget_background: '#fee2e2', widget_border_width: 3 } }} datasetId={1} />
      </CrossFilterProvider>
    )
    await waitFor(() => expect(widgetDataApi.query).toHaveBeenCalled())
    const chrome = container.firstElementChild as HTMLElement
    expect(chrome.style.background).toContain('254')     // rgb(254, 226, 226)
    expect(chrome.style.border).toContain('3px')
  })

  it('lets a display rule background win over the configured one', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      type: 'series', rows: [{ name: 'US', value: 1 }], total: 1,
      rule_styles: { rows: [null], cells: {}, widget: { background: '#000000' } }, rule_errors: [],
    } as any)
    const { container } = render(
      <CrossFilterProvider>
        <WidgetRenderer widget={{ ...barWidget(), config: { widget_background: '#fee2e2' } }} datasetId={1} />
      </CrossFilterProvider>
    )
    await waitFor(() => expect(widgetDataApi.query).toHaveBeenCalled())
    const chrome = container.firstElementChild as HTMLElement
    expect(chrome.style.background).toContain('0, 0, 0')
  })

  it('renders with default values when no config is provided', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ type: 'series', rows: [{ name: 'US', value: 1 }], total: 1 } as any)
    const { container } = render(
      <CrossFilterProvider>
        <WidgetRenderer widget={barWidget()} datasetId={1} />
      </CrossFilterProvider>
    )
    await waitFor(() => expect(widgetDataApi.query).toHaveBeenCalled())
    const chrome = container.firstElementChild as HTMLElement
    // Check that unconfigured widget uses the default values
    expect(chrome.style.border).toContain('1px')
    expect(chrome.style.border).toContain('var(--border)')
    expect(chrome.style.borderRadius).toBe('var(--radius)')
    expect(chrome.style.background).toBe('var(--surface)')
  })
})

describe('WidgetRenderer alternative text', () => {
  it('labels the widget with its alt text when set', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ type: 'series', rows: [], total: 0 } as any)
    render(
      <CrossFilterProvider>
        <WidgetRenderer widget={{ ...barWidget(), title: 'Sales', config: { alt_text: 'Quarterly sales by region' } }} datasetId={1} />
      </CrossFilterProvider>
    )
    expect(await screen.findByLabelText('Quarterly sales by region')).toBeInTheDocument()
  })

  it('falls back to the title, then the widget type, when no alt text is set', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ type: 'series', rows: [], total: 0 } as any)
    const { unmount } = render(
      <CrossFilterProvider>
        <WidgetRenderer widget={{ ...barWidget(), title: 'Sales' }} datasetId={1} />
      </CrossFilterProvider>
    )
    expect(await screen.findByLabelText('Sales')).toBeInTheDocument()
    unmount()

    render(
      <CrossFilterProvider>
        <WidgetRenderer widget={{ ...barWidget(), title: '' }} datasetId={1} />
      </CrossFilterProvider>
    )
    expect(await screen.findByLabelText('bar')).toBeInTheDocument()
  })
})


describe('WidgetRenderer external links', () => {
  it('opens an http(s) URL from a button in a new, severed tab', async () => {
    const open = vi.spyOn(window, 'open').mockReturnValue(null)
    render(
      <CrossFilterProvider>
        <WidgetRenderer
          widget={{ ...barWidget(), widget_type: 'button', config: { label: 'Docs', action: 'url', actionUrl: 'https://example.com/docs' } }}
          datasetId={1}
        />
      </CrossFilterProvider>
    )
    fireEvent.click(screen.getByRole('button', { name: 'Docs' }))
    expect(open).toHaveBeenCalledWith('https://example.com/docs', '_blank', 'noopener,noreferrer')
    open.mockRestore()
  })

  it('refuses to open a javascript: URL -- stored config must not become XSS', async () => {
    // The URL lives in persisted widget config, so anyone who can edit a report could
    // otherwise plant a link that runs script in the viewer's session. The click must
    // do nothing at all.
    const open = vi.spyOn(window, 'open').mockReturnValue(null)
    render(
      <CrossFilterProvider>
        <WidgetRenderer
          widget={{ ...barWidget(), widget_type: 'button', config: { label: 'Evil', action: 'url', actionUrl: 'javascript:alert(1)' } }}
          datasetId={1}
        />
      </CrossFilterProvider>
    )
    fireEvent.click(screen.getByRole('button', { name: 'Evil' }))
    expect(open).not.toHaveBeenCalled()
    open.mockRestore()
  })

  it('renders markdown-style links in a text block as severed anchors', () => {
    render(
      <CrossFilterProvider>
        <WidgetRenderer
          widget={{ ...barWidget(), widget_type: 'text', config: { content: 'See [the docs](https://example.com) for more.' } }}
          datasetId={1}
        />
      </CrossFilterProvider>
    )
    const link = screen.getByRole('link', { name: 'the docs' })
    expect(link).toHaveAttribute('href', 'https://example.com')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
    // The surrounding prose is still there as text.
    expect(screen.getByText(/for more/)).toBeInTheDocument()
  })

  it('leaves a javascript: pseudo-link in text as inert text', () => {
    render(
      <CrossFilterProvider>
        <WidgetRenderer
          widget={{ ...barWidget(), widget_type: 'text', config: { content: 'Click [here](javascript:alert(1)) now' } }}
          datasetId={1}
        />
      </CrossFilterProvider>
    )
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    // The literal text survives, so the author sees what they typed rather than a
    // silently swallowed link.
    expect(screen.getByText(/javascript:alert/)).toBeInTheDocument()
  })
})


describe('WidgetRenderer sweep features', () => {
  it('exposes the widget title as a level-3 heading for screen readers', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ type: 'series', rows: [{ name: 'US', value: 1 }], total: 1 } as any)
    render(
      <CrossFilterProvider>
        <WidgetRenderer widget={{ ...barWidget(), title: 'Sales by Region' }} datasetId={1} />
      </CrossFilterProvider>
    )
    const heading = await screen.findByRole('heading', { name: 'Sales by Region' })
    expect(heading).toHaveAttribute('aria-level', '3')
  })

  it('resolves {{agg(column)}} placeholders through the real data path', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [{ name: 'revenue', value: 6067.9 }], value: 6067.9 } as any)
    render(
      <CrossFilterProvider>
        <WidgetRenderer
          widget={{ ...barWidget(), widget_type: 'text', config: { content: 'Total: {{sum(revenue)}} this year' } }}
          datasetId={1}
        />
      </CrossFilterProvider>
    )
    // Locale-agnostic on purpose: fmtStr renders via toLocaleString(undefined, ...),
    // which on an ar-EG machine produces Arabic-Indic digits. Asserting the literal
    // "6,067.9" is the locale-pinned-test mistake this project has made before, so the
    // expectation is computed with the same API the code uses.
    const expected = `Total: ${(6067.9).toLocaleString(undefined, { maximumFractionDigits: 2 })} this year`
    // The value renders as its own span (so display rules can colour it), so the
    // assertion matches the assembled textContent rather than one text node.
    await waitFor(() => expect(screen.getAllByText(
      (_, el) => el?.tagName === 'DIV' && el.textContent === expected).length).toBeGreaterThan(0))
    // The query went through the widget-data path as a KPI, which is what makes the
    // number obey the same filters and RLS as every chart.
    expect(widgetDataApi.query).toHaveBeenCalledWith(1,
      expect.objectContaining({ measure: 'revenue', aggregation: 'sum' }),
      expect.anything(), 'kpi', expect.anything())
  })

  it('shows an em dash for an unresolvable placeholder, never raw braces', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], value: undefined } as any)
    render(
      <CrossFilterProvider>
        <WidgetRenderer
          widget={{ ...barWidget(), widget_type: 'text', config: { content: 'X: {{sum(nope)}}' } }}
          datasetId={1}
        />
      </CrossFilterProvider>
    )
    await waitFor(() => expect(screen.getAllByText(
      (_, el) => el?.tagName === 'DIV' && /X: —/.test(el.textContent ?? '')).length).toBeGreaterThan(0))
    expect(screen.queryByText(/\{\{/)).not.toBeInTheDocument()
  })

  it('leaves a plain text block alone: no fetch, no placeholders, no change', async () => {
    // Compared against the count BEFORE render: this file's mocks accumulate calls
    // across tests, so "not called at all" would fail for reasons unrelated to this
    // widget. What matters is that THIS render added none.
    const before = vi.mocked(widgetDataApi.query).mock.calls.length
    render(
      <CrossFilterProvider>
        <WidgetRenderer
          widget={{ ...barWidget(), widget_type: 'text', config: { content: 'Just words.' } }}
          datasetId={1}
        />
      </CrossFilterProvider>
    )
    expect(screen.getByText('Just words.')).toBeInTheDocument()
    await new Promise(r => setTimeout(r, 50))
    expect(vi.mocked(widgetDataApi.query).mock.calls.length).toBe(before)
  })

  it('re-fetches on the configured auto-reload interval', async () => {
    vi.useFakeTimers()
    try {
      vi.mocked(widgetDataApi.query).mockResolvedValue({ type: 'series', rows: [{ name: 'US', value: 1 }], total: 1 } as any)
      render(
        <CrossFilterProvider>
          <WidgetRenderer widget={{ ...barWidget(), config: { dimension: 'region', auto_reload_seconds: 10 } }} datasetId={1} />
        </CrossFilterProvider>
      )
      await act(async () => { await vi.advanceTimersByTimeAsync(50) })
      const initial = vi.mocked(widgetDataApi.query).mock.calls.length
      await act(async () => { await vi.advanceTimersByTimeAsync(10_000) })
      expect(vi.mocked(widgetDataApi.query).mock.calls.length).toBe(initial + 1)
    } finally {
      vi.useRealTimers()
    }
  })

  it('never auto-reloads without the opt-in', async () => {
    vi.useFakeTimers()
    try {
      vi.mocked(widgetDataApi.query).mockResolvedValue({ type: 'series', rows: [{ name: 'US', value: 1 }], total: 1 } as any)
      render(
        <CrossFilterProvider>
          <WidgetRenderer widget={barWidget()} datasetId={1} />
        </CrossFilterProvider>
      )
      await act(async () => { await vi.advanceTimersByTimeAsync(50) })
      const initial = vi.mocked(widgetDataApi.query).mock.calls.length
      await act(async () => { await vi.advanceTimersByTimeAsync(60_000) })
      expect(vi.mocked(widgetDataApi.query).mock.calls.length).toBe(initial)
    } finally {
      vi.useRealTimers()
    }
  })
})

describe('viewport-lazy fetch', () => {
  beforeEach(() => {
    // this file has no global mock hygiene; call counts leak across tests
    vi.mocked(widgetDataApi.query).mockReset()
  })
  afterEach(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    delete (globalThis as any).IntersectionObserver
  })

  it('fetches on mount when IntersectionObserver is unavailable (jsdom default)', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [{ name: 'A', value: 1 }] })
    renderWidget()
    await waitFor(() => expect(widgetDataApi.query).toHaveBeenCalled())
  })

  it('defers the fetch until the widget intersects, then fetches once visible', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [{ name: 'A', value: 1 }] })
    let trigger: ((entries: { isIntersecting: boolean }[]) => void) | null = null
    class FakeIO {
      constructor(cb: (entries: { isIntersecting: boolean }[]) => void) { trigger = cb }
      observe() {}
      disconnect() {}
      unobserve() {}
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(globalThis as any).IntersectionObserver = FakeIO

    renderWidget()
    await act(async () => { await Promise.resolve() })
    expect(widgetDataApi.query).not.toHaveBeenCalled()

    await act(async () => { trigger?.([{ isIntersecting: true }]) })
    await waitFor(() => expect(widgetDataApi.query).toHaveBeenCalled())
  })

  it('eagerFetch overrides laziness even with an observer present', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [{ name: 'A', value: 1 }] })
    class InertIO {
      observe() {}
      disconnect() {}
      unobserve() {}
    }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(globalThis as any).IntersectionObserver = InertIO

    renderWidget({ eagerFetch: true })
    await waitFor(() => expect(widgetDataApi.query).toHaveBeenCalled())
  })
})

describe('render discipline (React.memo)', () => {
  it('a parent re-render with stable props does not re-run the widget body', async () => {
    vi.mocked(widgetDataApi.query).mockReset()
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [{ name: 'A', value: 1 }] })
    // Body executions are counted through a config getter: the component reads
    // widget.config during every body run, so a memo bailout reads nothing.
    let configReads = 0
    const cfg = { dimension: 'region' }
    const widget = barWidget()
    Object.defineProperty(widget, 'config', { get() { configReads += 1; return cfg } })

    function Harness() {
      const [, force] = useState(0)
      return (
        <CrossFilterProvider>
          <WidgetRenderer widget={widget} datasetId={10} />
          <button onClick={() => force(x => x + 1)}>bump</button>
        </CrossFilterProvider>
      )
    }
    render(<Harness />)
    await waitFor(() => expect(widgetDataApi.query).toHaveBeenCalled())
    await act(async () => { await new Promise(r => setTimeout(r, 50)) })
    const before = configReads

    fireEvent.click(screen.getByText('bump'))
    await act(async () => { await new Promise(r => setTimeout(r, 50)) })
    expect(configReads).toBe(before)
  })

  it('a provider parent re-render does not re-render memoized context consumers', async () => {
    // Pins the CrossFilterContext value memoization: an inline object literal
    // there would invalidate every consumer on every provider render and
    // silently defeat React.memo on all widgets.
    let consumerRenders = 0
    function Consumer() {
      useCrossFilter()
      consumerRenders += 1
      return null
    }
    const MemoConsumer = memo(Consumer)
    function Harness() {
      const [, force] = useState(0)
      return (
        <CrossFilterProvider>
          <MemoConsumer />
          <button onClick={() => force(x => x + 1)}>bump</button>
        </CrossFilterProvider>
      )
    }
    render(<Harness />)
    const before = consumerRenders
    fireEvent.click(screen.getByText('bump'))
    await act(async () => { await Promise.resolve() })
    expect(consumerRenders).toBe(before)
  })
})

describe('table/list virtualization', () => {
  beforeEach(() => { vi.mocked(widgetDataApi.query).mockReset() })

  const bigTable = (n: number) => ({
    columns: ['name', 'value'],
    rows: Array.from({ length: n }, (_, i) => [`row-${i}`, i * 10]),
    total: n,
  })

  it('renders every row below the threshold, exactly as before', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue(bigTable(40))
    renderWidget({ widget: barWidget({ widget_type: 'table', config: { columns: ['name', 'value'] } }) })
    await waitFor(() => expect(screen.getByText('row-0')).toBeInTheDocument())
    expect(screen.getByText('row-39')).toBeInTheDocument()
  })

  it('windows a large table: spacer rows stand in for off-screen rows', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue(bigTable(1000))
    const { container } = renderWidget({ widget: barWidget({ widget_type: 'table', config: { columns: ['name', 'value'] } }) })
    await waitFor(() => expect(screen.getByText('row-0')).toBeInTheDocument())
    // window = 20 fallback rows + overscan, far below 1000
    const bodyRows = container.querySelectorAll('tbody tr')
    expect(bodyRows.length).toBeLessThan(100)
    expect(screen.queryByText('row-500')).toBeNull()
    // bottom spacer carries the off-screen height
    const spacer = container.querySelector('tbody tr[aria-hidden="true"]')
    expect(spacer).not.toBeNull()
  })

  it('scrolling moves the window and keeps absolute row numbering', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue(bigTable(1000))
    const { container } = renderWidget({
      widget: barWidget({ widget_type: 'table', config: { columns: ['name', 'value'], table_row_numbers: true } }),
    })
    await waitFor(() => expect(screen.getByText('row-0')).toBeInTheDocument())
    const scroller = container.querySelector('div[style*="overflow: auto"]') as HTMLElement
    Object.defineProperty(scroller, 'scrollTop', { value: 31 * 500, configurable: true })
    fireEvent.scroll(scroller)
    // rAF flush
    await act(async () => { await new Promise(r => setTimeout(r, 50)) })
    await waitFor(() => expect(screen.getByText('row-500')).toBeInTheDocument())
    expect(screen.queryByText('row-0')).toBeNull()
    // absolute row number: row-500 sits beside the number 491..501 range cell "501"
    expect(screen.getByText('501')).toBeInTheDocument()
  })

  it('windows a large list the same way', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      rows: Array.from({ length: 800 }, (_, i) => ({ name: `item-${i}`, value: i })), total: 800,
    })
    renderWidget({ widget: barWidget({ widget_type: 'list', config: { dimension: 'name' } }) })
    await waitFor(() => expect(screen.getByText('item-0')).toBeInTheDocument())
    expect(screen.queryByText('item-400')).toBeNull()
  })
})

describe('conditional formatting: icons and data bars', () => {
  beforeEach(() => { vi.mocked(widgetDataApi.query).mockReset() })

  it('shows an interval band icon next to a table cell it painted', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      columns: ['name', 'value'], rows: [['A', 5]], total: 1,
      rule_styles: { rows: [null], cells: { '0': { value: { fill: '#f87171', icon: '⚠️' } } }, widget: {} },
    })
    renderWidget({ widget: barWidget({ widget_type: 'table', config: { columns: ['name', 'value'] } }) })

    await waitFor(() => expect(screen.getByText('5')).toBeInTheDocument())
    expect(screen.getByText('⚠️')).toBeInTheDocument()
  })

  it('renders no icon glyph for a cell no rule painted', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      columns: ['name', 'value'], rows: [['A', 5]], total: 1,
    })
    renderWidget({ widget: barWidget({ widget_type: 'table', config: { columns: ['name', 'value'] } }) })

    await waitFor(() => expect(screen.getByText('5')).toBeInTheDocument())
    expect(screen.queryByText('⚠️')).toBeNull()
  })

  it('shows an icon beside the KPI value the matching rule carries', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      rows: [{ name: 'sum(revenue)', value: 42 }],
      rule_styles: { rows: [{ fill: '#f87171', icon: '❌' }], cells: {}, widget: {} },
    })
    renderWidget({ widget: barWidget({ widget_type: 'kpi', config: { measure: 'revenue' } }) })

    // Localised: fmtStr goes through toLocaleString, and this environment does
    // not render Latin digits (see DecompositionRenderer.test.tsx).
    await waitFor(() => expect(screen.getByText((42).toLocaleString())).toBeInTheDocument())
    expect(screen.getByText('❌')).toBeInTheDocument()
  })

  it('draws an in-cell data bar sized to the rule-resolved proportion', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      columns: ['name', 'value'], rows: [['A', 25], ['B', 100]], total: 2,
      rule_styles: {
        rows: [null, null],
        cells: { '0': { value: { bar: 0.25 } }, '1': { value: { bar: 1.0 } } },
        widget: {},
      },
    })
    const { container } = renderWidget({
      widget: barWidget({ widget_type: 'table', config: { columns: ['name', 'value'] } }),
    })

    await waitFor(() => expect(screen.getByText('25')).toBeInTheDocument())
    const bars = container.querySelectorAll('[data-testid="cell-data-bar"]')
    expect(bars).toHaveLength(2)
    expect((bars[0] as HTMLElement).style.width).toBe('25%')
    expect((bars[1] as HTMLElement).style.width).toBe('100%')
  })

  it('draws no data bar for a cell with no bar rule', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      columns: ['name', 'value'], rows: [['A', 25]], total: 1,
    })
    const { container } = renderWidget({
      widget: barWidget({ widget_type: 'table', config: { columns: ['name', 'value'] } }),
    })

    await waitFor(() => expect(screen.getByText('25')).toBeInTheDocument())
    expect(container.querySelectorAll('[data-testid="cell-data-bar"]')).toHaveLength(0)
  })
})

describe('WidgetRenderer cross-filter indicators', () => {
  it('marks a widget that can receive cross-filters, mirroring the existing emit arrow', () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
    renderWidget()
    expect(screen.getByTitle('Receives cross-filters')).toBeInTheDocument()
    // Both indicators coexist -- a widget is commonly both a source and a sink.
    expect(screen.getByTitle('Emits cross-filters')).toBeInTheDocument()
  })

  it('omits the receive indicator once the widget is marked as not receiving', () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
    function NotReceiving() {
      const { setInteraction } = useCrossFilter()
      useEffect(() => { setInteraction(1, { broadcasts: true, receives: false }) }, [])
      return null
    }
    render(
      <CrossFilterProvider>
        <NotReceiving />
        <WidgetRenderer widget={barWidget()} datasetId={10} />
      </CrossFilterProvider>
    )
    expect(screen.queryByTitle('Receives cross-filters')).toBeNull()
  })

  it('clears an incoming cross-filter from its own badge, without touching other widgets', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [], sampled: false })
    render(
      <CrossFilterProvider>
        <MultiFilterInjector widgetId={1} pageId={100} column="region" values={['North']} />
        <WidgetRenderer widget={barWidget({ id: 2 })} datasetId={10} />
      </CrossFilterProvider>
    )

    await waitFor(() => expect(screen.getByTitle(/Filtered by: region/i)).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /clear this filter/i }))

    await waitFor(() => expect(screen.queryByTitle(/Filtered by: region/i)).toBeNull())
    expect(screen.queryByText(/1 filter/i)).toBeNull()
  })
})

describe('display rules on dynamic text', () => {
  beforeEach(() => { vi.mocked(widgetDataApi.query).mockReset() })

  it('colours a placeholder value by the rule its KPI result matched', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      rows: [{ name: 'sum(revenue)', value: 42 }],
      rule_styles: { rows: { 0: { fill: 'rgb(200, 30, 30)' } }, widget: {} },
    } as any)
    render(
      <CrossFilterProvider>
        <WidgetRenderer
          widget={{ ...barWidget(), widget_type: 'text',
            config: { content: 'Revenue: {{sum(revenue)}}',
              display_rules: [{ id: 'r1', expression: 'value < 100', style: { fill: 'rgb(200, 30, 30)' } }] } }}
          datasetId={1}
        />
      </CrossFilterProvider>
    )
    const styled = await screen.findByTestId('text-rule-styled')
    expect(styled).toHaveStyle({ color: 'rgb(200, 30, 30)' })
    expect(styled.textContent).toBe((42).toLocaleString(undefined, { maximumFractionDigits: 2 }))
  })

  it('renders unstyled when no rule matched', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      rows: [{ name: 'sum(revenue)', value: 42 }], rule_styles: { rows: {}, widget: {} },
    } as any)
    render(
      <CrossFilterProvider>
        <WidgetRenderer
          widget={{ ...barWidget(), widget_type: 'text', config: { content: 'Revenue: {{sum(revenue)}}' } }}
          datasetId={1}
        />
      </CrossFilterProvider>
    )
    await waitFor(() => expect(screen.getAllByText(
      (_, el) => el?.tagName === 'DIV' && /Revenue: /.test(el.textContent ?? '')).length).toBeGreaterThan(0))
    expect(screen.queryByTestId('text-rule-styled')).toBeNull()
  })
})

describe('object-level copy link', () => {
  it('the context menu offers Copy link to this visual and writes page+widget params', async () => {
    vi.mocked(widgetDataApi.query).mockReset()
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [{ name: 'A', value: 1 }] })
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })

    renderWidget()
    await waitFor(() => expect(widgetDataApi.query).toHaveBeenCalled())
    fireEvent.contextMenu(screen.getByRole('figure'))
    fireEvent.click(await screen.findByRole('menuitem', { name: /Copy link to this visual/ }))

    await waitFor(() => expect(writeText).toHaveBeenCalled())
    const url = new URL(writeText.mock.calls[0][0])
    expect(url.searchParams.get('page')).toBe('100')   // barWidget().page_id
    expect(url.searchParams.get('widget')).toBe('1')   // barWidget().id
  })
})

describe('data-driven external URLs', () => {
  it('substitutes {{@param}} URL-encoded and opens the result', async () => {
    const open = vi.fn()
    vi.stubGlobal('open', open)
    renderWidget({
      widget: barWidget({ widget_type: 'button',
        config: { label: 'Go', action: 'url', actionUrl: 'https://example.com/search?q={{@term}}' } }),
      parameters: { term: 'a b&c' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Go' }))
    expect(open).toHaveBeenCalledWith('https://example.com/search?q=a%20b%26c', '_blank', 'noopener,noreferrer')
    vi.unstubAllGlobals()
  })

  it('a parameter value cannot smuggle a scheme: encoding defuses it into a path', () => {
    const open = vi.fn()
    vi.stubGlobal('open', open)
    renderWidget({
      widget: barWidget({ widget_type: 'button',
        config: { label: 'Go', action: 'url', actionUrl: '{{@u}}' } }),
      parameters: { u: 'javascript:alert(1)' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Go' }))
    // The value is URL-encoded BEFORE parsing, so 'javascript:' becomes an
    // inert path segment resolved against the app origin -- never a scheme.
    if (open.mock.calls.length > 0) {
      const opened = new URL(open.mock.calls[0][0])
      expect(['http:', 'https:']).toContain(opened.protocol)
      expect(opened.href).not.toMatch(/^javascript:/i)
    }
    vi.unstubAllGlobals()
  })
})

function HighlightModeInjector({ widgetId, pageId, column, value }: { widgetId: number; pageId: number; column: string; value: unknown }) {
  const { emitFilter, setInteraction } = useCrossFilter()
  useEffect(() => {
    setInteraction(2, { broadcasts: true, receives: true, receiveMode: 'highlight' })
    emitFilter(widgetId, pageId, column, value, `${column} = ${value}`)
  }, [])
  return null
}

describe('cross-highlight receive mode', () => {
  it('queries baseline AND selection, merging the selected share per category', async () => {
    vi.mocked(widgetDataApi.query).mockReset()
    vi.mocked(widgetDataApi.query).mockImplementation(async (_ds, config: any) => {
      const hasCross = (config.filters ?? []).some((f: any) => f.column === 'region')
      return hasCross
        ? { rows: [{ name: 'A', value: 40 }] }                       // selected slice
        : { rows: [{ name: 'A', value: 100 }, { name: 'B', value: 50 }] }  // baseline
    })
    const onFetchComplete = vi.fn()
    render(
      <CrossFilterProvider>
        <HighlightModeInjector widgetId={1} pageId={100} column="region" value="North" />
        <WidgetRenderer widget={barWidget({ id: 2, config: { dimension: 'city' } })} datasetId={10}
          onFetchComplete={onFetchComplete} />
      </CrossFilterProvider>
    )
    await waitFor(() => expect(vi.mocked(widgetDataApi.query).mock.calls.length).toBeGreaterThanOrEqual(2))
    // both queries went out: one without the incoming filter, one with
    const configs = vi.mocked(widgetDataApi.query).mock.calls.map(c => c[1] as any)
    expect(configs.some(c => (c.filters ?? []).some((f: any) => f.column === 'region'))).toBe(true)
    expect(configs.some(c => !(c.filters ?? []).some((f: any) => f.column === 'region'))).toBe(true)
    // the reported result is the BASELINE (all categories), not the selection:
    // highlight keeps every bar and saturates the selected share
    await waitFor(() => expect(onFetchComplete).toHaveBeenCalled())
    const [, info] = onFetchComplete.mock.calls[onFetchComplete.mock.calls.length - 1]
    expect(info.rowCount).toBe(2)
  })
})

describe('page-wide automatic action modes', () => {
  function Probe({ out }: { out: Record<string, unknown> }) {
    const { getReceiveMode, canBroadcast, emitFilter, activeFilters } = useCrossFilter()
    out.receiveMode = getReceiveMode(7)
    out.canBroadcast = canBroadcast(7)
    out.emitFilter = emitFilter
    out.activeFilters = activeFilters
    return null
  }

  it('linked mode: everyone broadcasts and receivers highlight, overriding per-widget settings', () => {
    const out: Record<string, any> = {}
    function Setup() {
      const { setInteraction } = useCrossFilter()
      useEffect(() => { setInteraction(7, { broadcasts: false, receives: false, receiveMode: 'filter' }) }, [])
      return null
    }
    render(
      <CrossFilterProvider pageMode="linked">
        <Setup />
        <Probe out={out} />
      </CrossFilterProvider>
    )
    expect(out.receiveMode).toBe('highlight')
    expect(out.canBroadcast).toBe(true)
  })

  it('one-way mode: a new source replaces filters from other sources', async () => {
    const out: Record<string, any> = {}
    const { rerender } = render(
      <CrossFilterProvider pageMode="oneway"><Probe out={out} /></CrossFilterProvider>
    )
    act(() => { out.emitFilter(1, 100, 'region', 'North', 'r=N') })
    rerender(<CrossFilterProvider pageMode="oneway"><Probe out={out} /></CrossFilterProvider>)
    act(() => { out.emitFilter(2, 100, 'city', 'Cairo', 'c=C') })
    rerender(<CrossFilterProvider pageMode="oneway"><Probe out={out} /></CrossFilterProvider>)
    expect(out.activeFilters).toHaveLength(1)
    expect(out.activeFilters[0].sourceWidgetId).toBe(2)
  })

  it('two-way mode: filters from multiple sources accumulate', () => {
    const out: Record<string, any> = {}
    const { rerender } = render(
      <CrossFilterProvider pageMode="twoway"><Probe out={out} /></CrossFilterProvider>
    )
    act(() => { out.emitFilter(1, 100, 'region', 'North', 'r=N') })
    rerender(<CrossFilterProvider pageMode="twoway"><Probe out={out} /></CrossFilterProvider>)
    act(() => { out.emitFilter(2, 100, 'city', 'Cairo', 'c=C') })
    rerender(<CrossFilterProvider pageMode="twoway"><Probe out={out} /></CrossFilterProvider>)
    expect(out.activeFilters).toHaveLength(2)
  })
})

describe('named per-pair actions (Actions pane)', () => {
  function Probe({ out, widgetId }: { out: Record<string, any>; widgetId: number }) {
    const { getFiltersFor, getReceiveMode, emitFilter, setInteraction } = useCrossFilter()
    out.filtersFor = (id: number) => getFiltersFor(id, 100)
    out.receiveMode = (id: number) => getReceiveMode(id)
    out.emitFilter = emitFilter
    out.setInteraction = setInteraction
    void widgetId
    return null
  }

  it('a source with explicit actions reaches only its listed targets', () => {
    const out: Record<string, any> = {}
    const { rerender } = render(
      <CrossFilterProvider><Probe out={out} widgetId={1} /></CrossFilterProvider>)
    act(() => {
      out.setInteraction(1, { broadcasts: true, receives: true,
        actions: [{ targetId: 2, mode: 'filter' }] })
      out.emitFilter(1, 100, 'region', 'North', 'r=N')
    })
    rerender(<CrossFilterProvider><Probe out={out} widgetId={1} /></CrossFilterProvider>)
    expect(out.filtersFor(2)).toHaveLength(1)   // listed target receives
    expect(out.filtersFor(3)).toHaveLength(0)   // unlisted target does not
  })

  it("the pair's action type drives the target's receive mode", () => {
    const out: Record<string, any> = {}
    const { rerender } = render(
      <CrossFilterProvider><Probe out={out} widgetId={1} /></CrossFilterProvider>)
    act(() => {
      out.setInteraction(1, { broadcasts: true, receives: true,
        actions: [{ targetId: 2, mode: 'highlight' }, { targetId: 3, mode: 'filter' }] })
      out.emitFilter(1, 100, 'region', 'North', 'r=N')
    })
    rerender(<CrossFilterProvider><Probe out={out} widgetId={1} /></CrossFilterProvider>)
    expect(out.receiveMode(2)).toBe('highlight')
    expect(out.receiveMode(3)).toBe('filter')
  })
})

describe('widget header action menu (U1)', () => {
  it('the ⋯ menu delete item fires the same onDelete handler as the × icon', () => {
    const onDelete = vi.fn()
    renderWidget({ editMode: true, onDelete })

    fireEvent.click(screen.getByRole('button', { name: 'More actions for widget Sales' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Delete widget' }))

    expect(onDelete).toHaveBeenCalledTimes(1)
  })
})

describe('a refused request explains itself', () => {
  // The import row cap is enforced server-side and returns 413 with a message
  // naming the limit, the actual row count and the two remedies. The widget
  // discarded it and rendered "Configure widget to see data" -- blaming the
  // author for a configuration mistake they did not make, and sending them to
  // edit a config that was already correct.
  const CAP_413 = {
    response: { status: 413, data: { detail:
      'Dataset has 2,400,000 rows, above the import row cap of 2,000,000. ' +
      'Raise `import_row_cap`, or use a DirectQuery data source, which ' +
      'pushes aggregation into SQL instead of loading the whole table.' } },
  }

  it('shows the backend’s reason instead of blaming the configuration', async () => {
    vi.mocked(widgetDataApi.query).mockRejectedValue(CAP_413)
    renderWidget()
    expect(await screen.findByText(/above the import row cap/i)).toBeInTheDocument()
    expect(screen.queryByText(/configure widget/i)).not.toBeInTheDocument()
  })

  it('names the remedy the user can actually act on', async () => {
    vi.mocked(widgetDataApi.query).mockRejectedValue(CAP_413)
    renderWidget()
    expect(await screen.findByText(/DirectQuery/i)).toBeInTheDocument()
  })

  it('still says "configure" when there is genuinely no config', async () => {
    // The original message is right for its own case, and must survive.
    vi.mocked(widgetDataApi.query).mockResolvedValue(null as never)
    renderWidget()
    expect(await screen.findByText(/configure widget/i)).toBeInTheDocument()
  })

  it('goes back to showing data once a later fetch succeeds', async () => {
    // Not a test that `fetchError` is cleared: the render guard is
    // `!data && fetchError`, so a successful refetch hides the message by
    // giving `data` a value, whether or not the state was reset. Asserting the
    // reset directly would be asserting something unobservable -- this asserts
    // what the user actually sees.
    vi.mocked(widgetDataApi.query).mockRejectedValueOnce(CAP_413)
    const tree = (cfg: Record<string, unknown>) => (
      <CrossFilterProvider>
        <WidgetRenderer widget={barWidget({ config: cfg })} datasetId={10} />
      </CrossFilterProvider>
    )
    const { rerender } = render(tree({ dimension: 'region' }))
    await screen.findByText(/above the import row cap/i)

    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [{ name: 'A', value: 1 }] } as never)
    rerender(tree({ dimension: 'country' }))

    await waitFor(() =>
      expect(screen.queryByText(/above the import row cap/i)).not.toBeInTheDocument())
  })

})

describe('pin to dashboard, withdrawn', () => {
  // Pinning wrote to a personal dashboard that the Datasets page used to
  // render. That section is gone, so the button promised a destination
  // nothing displays -- a write-only control. It goes with it; the endpoint
  // stays, so the feature can come back with a surface to land on.
  it('offers no pin inside a report context', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [{ name: 'A', value: 1 }] } as never)
    renderWidget({ reportId: 7 })
    await screen.findByText('Sales')
    expect(screen.queryByRole('button', { name: /Pin Sales/ })).toBeNull()
  })

  it('never calls the pin API', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [{ name: 'A', value: 1 }] } as never)
    renderWidget({ reportId: 7 })
    await screen.findByText('Sales')
    expect(pinsApi.create).not.toHaveBeenCalled()
  })
})


describe('WidgetRenderer script tile', () => {
  /**
   * SAS's Job content object: server-side code, its output on the report. The
   * backend decides what the code may do (services/script_tile.py); this half
   * has to show the result, the printed output an author debugs with, and —
   * above all — the error, because the person looking at a broken script tile
   * is usually the person who wrote it.
   */
  const scriptWidget = (config: Record<string, unknown> = {}): Widget =>
    barWidget({ widget_type: 'script', title: 'Backlog', config })

  it('draws the rows the script returned', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      type: 'script', columns: ['region', 'amount'],
      rows: [['North', 10], ['South', 20]], stdout: '', truncated: false, error: null,
    } as never)
    renderWidget({ widget: scriptWidget({ code: 'result = df' }) })
    expect(await screen.findByText('North')).toBeInTheDocument()
    expect(screen.getByText('region')).toBeInTheDocument()
    expect(screen.getByText((20).toLocaleString())).toBeInTheDocument()
  })

  it('shows the error instead of an empty tile', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      type: 'script', columns: [], rows: [], stdout: '', truncated: false,
      error: "KeyError: 'nope'",
    } as never)
    renderWidget({ widget: scriptWidget({ code: "result = df['nope']" }) })
    expect(await screen.findByText(/KeyError: 'nope'/)).toBeInTheDocument()
  })

  it('shows what the script printed', async () => {
    // print() is how anyone debugs one of these; hiding it makes the tile
    // unusable for the person writing it.
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      type: 'script', columns: ['a'], rows: [[1]], truncated: false, error: null,
      stdout: 'checked 402 rows',
    } as never)
    renderWidget({ widget: scriptWidget({ code: 'print(1)\nresult = df' }) })
    expect(await screen.findByText(/checked 402 rows/)).toBeInTheDocument()
  })

  it('says when the output was truncated', async () => {
    // A tile silently showing the first 5,000 of 40,000 rows is a wrong answer
    // presented as a complete one.
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      type: 'script', columns: ['a'], rows: [[1]], stdout: '', truncated: true,
      row_count: 40000, error: null,
    } as never)
    renderWidget({ widget: scriptWidget({ code: 'result = df' }) })
    expect(await screen.findByText(/truncated|first/i)).toBeInTheDocument()
  })

  it('asks for code when there is none', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      type: 'script', columns: [], rows: [], stdout: '', truncated: false,
      error: 'There is no code to run.',
    } as never)
    renderWidget({ widget: scriptWidget({}) })
    expect(await screen.findByText(/no code to run/i)).toBeInTheDocument()
  })

  it('is a data widget: it goes through the same secured query path', async () => {
    vi.mocked(widgetDataApi.query).mockClear()
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      type: 'script', columns: ['a'], rows: [[1]], stdout: '', truncated: false, error: null,
    } as never)
    renderWidget({ widget: scriptWidget({ code: 'result = df' }) })
    await waitFor(() => expect(widgetDataApi.query).toHaveBeenCalled())
  })
})

describe('a script tile that only saw part of the data', () => {
  it('says so, because the number would otherwise read as the total', async () => {
    // Output truncation was always declared; the INPUT cap was silent, and a
    // sum over the first 200,000 of 900,000 rows is simply a wrong answer.
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      type: 'script', columns: ['total'], rows: [[123]], stdout: '',
      truncated: false, error: null, input_truncated: true, rows_in: 200000,
    } as never)
    renderWidget({ widget: barWidget({ widget_type: 'script', title: 'T',
      config: { code: "result = df['amount'].sum()" } }) })
    expect(await screen.findByText(/first (200,000|٢٠٠٬٠٠٠|200000)|only the first/i))
      .toBeInTheDocument()
  })

  it('says nothing when the script saw everything', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      type: 'script', columns: ['total'], rows: [[123]], stdout: '',
      truncated: false, error: null, input_truncated: false, rows_in: 40,
    } as never)
    renderWidget({ widget: barWidget({ widget_type: 'script', title: 'T',
      config: { code: 'result = df' } }) })
    await screen.findByText('total')
    expect(screen.queryByText(/only the first/i)).not.toBeInTheDocument()
  })
})

describe('clicking a map filters the page', () => {
  withMeasuredTiles()
  /**
   * The other half of the map cross-filter work. The renderers now call
   * `onClickPoint`; this is whether the click actually reaches the page's
   * filter state, which is the seam the renderer tests cannot see.
   */
  const mapWidget = () => barWidget({
    id: 31, widget_type: 'map_choropleth', title: 'Sales by country',
    config: { dimension: 'country', measure: 'revenue' },
  })

  /** The map renderers are lazy and pull the world-atlas JSON with them, which
   *  takes several seconds the first time in this environment — well past
   *  waitFor's default second. Waiting the default here fails with "expected
   *  null not to be null", which reads as a renderer bug rather than a slow
   *  chunk. */
  const findRegion = (container: HTMLElement, label: string) =>
    waitFor(() => {
      const el = container.querySelector(`[data-country="${label}"]`)
      expect(el).not.toBeNull()
      return el as Element
    }, { timeout: 20000 })

  it('a region click becomes a page filter', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      type: 'series', rows: [{ name: 'France', value: 3 }], sampled: false } as never)
    const { container } = render(
      <CrossFilterProvider>
        <WidgetRenderer widget={mapWidget()} datasetId={10} />
        <FilterReader />
      </CrossFilterProvider>
    )
    fireEvent.click(await findRegion(container, 'France'))
    await waitFor(() => expect(screen.getByTestId('filters').textContent)
      .toContain('France'))
    expect(screen.getByTestId('filters').textContent).toContain('country')
  }, 30000)

  it('two spellings of one region filter by both', async () => {
    // The merged-region case: filtering by "US" alone would drop every "USA"
    // row from the rest of the page, which is a wrong answer, not a partial one.
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      type: 'series', rows: [{ name: 'US', value: 3 }, { name: 'USA', value: 4 }],
      sampled: false } as never)
    const { container } = render(
      <CrossFilterProvider>
        <WidgetRenderer widget={mapWidget()} datasetId={10} />
        <FilterReader />
      </CrossFilterProvider>
    )
    const us = await findRegion(container, 'United States of America')
    fireEvent.click(us)
    await waitFor(() => {
      const text = screen.getByTestId('filters').textContent ?? ''
      expect(text).toContain('US')
      expect(text).toContain('USA')
    })
  }, 30000)

  it('clicking the same region again clears the filter', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      type: 'series', rows: [{ name: 'France', value: 3 }], sampled: false } as never)
    const { container } = render(
      <CrossFilterProvider>
        <WidgetRenderer widget={mapWidget()} datasetId={10} />
        <FilterReader />
      </CrossFilterProvider>
    )
    const fr = await findRegion(container, 'France')
    fireEvent.click(fr)
    await waitFor(() => expect(screen.getByTestId('filters').textContent).toContain('France'))
    fireEvent.click(container.querySelector('[data-country="France"]')!)
    await waitFor(() => expect(screen.getByTestId('filters').textContent).toBe('[]'))
  }, 30000)
})

describe('a multi-value map selection toggles like any other', () => {
  withMeasuredTiles()
  it('clicking a merged region twice clears it', async () => {
    // Each click builds a NEW array, so identity comparison would never match
    // and the selection could be turned on but never off.
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      type: 'series', rows: [{ name: 'US', value: 3 }, { name: 'USA', value: 4 }],
      sampled: false } as never)
    const { container } = render(
      <CrossFilterProvider>
        <WidgetRenderer widget={barWidget({ id: 32, widget_type: 'map_choropleth',
          title: 'M', config: { dimension: 'country', measure: 'revenue' } })} datasetId={10} />
        <FilterReader />
      </CrossFilterProvider>
    )
    const us = await waitFor(() => {
      const el = container.querySelector('[data-country="United States of America"]')
      expect(el).not.toBeNull(); return el as Element
    }, { timeout: 20000 })

    fireEvent.click(us)
    await waitFor(() => expect(screen.getByTestId('filters').textContent).toContain('USA'))
    fireEvent.click(container.querySelector('[data-country="United States of America"]')!)
    await waitFor(() => expect(screen.getByTestId('filters').textContent).toBe('[]'))
  }, 30000)
})

describe('an object that lets the page show through', () => {
  /**
   * The SAS page this was measured against is a photograph with a bar chart,
   * two big numbers and a line chart floating on it — no card, no border, no
   * panel behind any of them. Every widget here draws `var(--surface)` and a
   * border unconditionally, so the same page would be four opaque cards sitting
   * on a picture.
   */
  it('draws no panel or border when the object is transparent', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      type: 'series', rows: [{ name: 'A', value: 1 }], sampled: false } as never)
    const { container } = renderWidget({ widget: barWidget({
      config: { dimension: 'region', transparent: true } }) })
    const figure = await waitFor(() => {
      const el = container.querySelector('[role="figure"]')
      expect(el).not.toBeNull(); return el as HTMLElement
    })
    expect(figure.style.background).toBe('transparent')
    // A zero-width border rather than `none`: jsdom's CSSOM drops the `none`
    // shorthand entirely, so nothing could be asserted about it.
    expect(figure.style.borderWidth).toBe('0px')
  })

  it('still draws its panel by default', async () => {
    // Opt-in: every dashboard that exists was authored against the card look.
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      type: 'series', rows: [{ name: 'A', value: 1 }], sampled: false } as never)
    const { container } = renderWidget({ widget: barWidget({ config: { dimension: 'region' } }) })
    const figure = await waitFor(() => {
      const el = container.querySelector('[role="figure"]')
      expect(el).not.toBeNull(); return el as HTMLElement
    })
    expect(figure.style.background).not.toBe('transparent')
  })
})

describe('duplicating a widget', () => {
  /**
   * SAS's "Duplicate Object". Building a chart, copying it and changing one
   * field is the commonest authoring move there is, and the only way to do it
   * here was to build the second one from scratch — widget templates exist, but
   * they are for reuse ACROSS reports, not for "another one of these".
   */
  it('offers duplicate in the ⋯ menu', () => {
    renderWidget({ editMode: true, onDelete: vi.fn(), onDuplicate: vi.fn() })
    fireEvent.click(screen.getByRole('button', { name: 'More actions for widget Sales' }))
    expect(screen.getByRole('menuitem', { name: /duplicate widget/i })).toBeInTheDocument()
  })

  it('fires the handler', () => {
    const onDuplicate = vi.fn()
    renderWidget({ editMode: true, onDelete: vi.fn(), onDuplicate })
    fireEvent.click(screen.getByRole('button', { name: 'More actions for widget Sales' }))
    fireEvent.click(screen.getByRole('menuitem', { name: /duplicate widget/i }))
    expect(onDuplicate).toHaveBeenCalledTimes(1)
  })

  it('offers nothing to duplicate with when the page cannot be edited', () => {
    renderWidget({ editMode: false, onDelete: vi.fn(), onDuplicate: vi.fn() })
    expect(screen.queryByRole('button', { name: /More actions/ })).not.toBeInTheDocument()
  })

  it('still shows delete when duplication is not offered', () => {
    // The menu must not become duplicate-or-nothing for a caller that passes
    // only onDelete — every existing caller does exactly that.
    renderWidget({ editMode: true, onDelete: vi.fn() })
    fireEvent.click(screen.getByRole('button', { name: 'More actions for widget Sales' }))
    expect(screen.getByRole('menuitem', { name: 'Delete widget' })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: /duplicate/i })).not.toBeInTheDocument()
  })
})

/**
 * A text control, for the column a list cannot serve.
 *
 * `Customer ID` with 748,000 distinct values is the case every list control
 * gets wrong: the list is unreadable, and building it is the expensive part.
 * SAS offers a text input for exactly this — the reader types the value they
 * already know.
 *
 * The properties worth pinning are the ones that make it a CONTROL rather than
 * a search box over a list that was fetched anyway: it draws no options, and
 * an empty box means no filter rather than a filter on "".
 */
describe('the text slicer control', () => {
  const textSlicer = () => barWidget({
    id: 77, widget_type: 'slicer', title: 'Customer',
    config: { dimension: 'customer_id', slicer_mode: 'text' },
  })

  it('draws an input and no list', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue(
      { type: 'slicer_text', rows: [], total: 0, column: 'customer_id' } as never)
    const { container } = renderWidget({ widget: textSlicer() })

    const box = await screen.findByRole('textbox', { name: /customer_id/i })
    expect(box).toBeInTheDocument()
    // No checkbox list, no button bar, no multi-select: those are the controls
    // this one exists to replace.
    expect(container.querySelector('[data-slicer-button]')).toBeNull()
    expect(container.querySelector('select')).toBeNull()
  })

  it('filters the page by what was typed', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue(
      { type: 'slicer_text', rows: [], total: 0, column: 'customer_id' } as never)
    // FilterReader beside it: the question is whether the typed value reaches
    // the page's filter state, which the widget alone cannot show.
    render(
      <CrossFilterProvider>
        <WidgetRenderer widget={textSlicer()} datasetId={10} />
        <FilterReader />
      </CrossFilterProvider>
    )

    const box = await screen.findByRole('textbox', { name: /customer_id/i })
    fireEvent.change(box, { target: { value: 'C-1042' } })
    fireEvent.keyDown(box, { key: 'Enter' })

    await waitFor(() => expect(screen.getByTestId('filters').textContent).toContain('C-1042'))
  })

  it('clears the filter when the box is emptied', async () => {
    // An empty box means "no filter", not a filter matching the empty string —
    // which would return nothing and look like a broken page.
    vi.mocked(widgetDataApi.query).mockResolvedValue(
      { type: 'slicer_text', rows: [], total: 0, column: 'customer_id' } as never)
    render(
      <CrossFilterProvider>
        <WidgetRenderer widget={textSlicer()} datasetId={10} />
        <FilterReader />
      </CrossFilterProvider>
    )

    const box = await screen.findByRole('textbox', { name: /customer_id/i })
    fireEvent.change(box, { target: { value: 'C-1042' } })
    fireEvent.keyDown(box, { key: 'Enter' })
    await waitFor(() => expect(screen.getByTestId('filters').textContent).toContain('C-1042'))

    fireEvent.change(box, { target: { value: '' } })
    fireEvent.keyDown(box, { key: 'Enter' })
    await waitFor(() => expect(screen.getByTestId('filters').textContent).not.toContain('C-1042'))
  })
})

describe('every widget error has a code the widget can act on', () => {
  // Two error channels reach a widget. HTTP errors carried `detail` and the
  // widget showed it. A 200 whose body is {type:'error', message} -- a measure
  // that could not be evaluated -- was never read: the widget fell through to
  // the chart renderer with empty rows and drew nothing, message discarded.
  // Both now carry `code`, and the widget renders both.

  it('shows the message from the 200-with-type:error channel', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      type: 'error', code: 'measure_error', rows: [], total: 0,
      message: 'Measure "margin" failed: unknown column cost',
    } as never)
    renderWidget()
    expect(await screen.findByText(/Measure "margin" failed/i)).toBeInTheDocument()
    expect(screen.queryByText(/configure widget/i)).not.toBeInTheDocument()
  })

  it('offers to try again only when the source was unreachable', async () => {
    vi.mocked(widgetDataApi.query).mockRejectedValue({
      response: { status: 502, data: { code: 'source_unavailable',
        detail: "Could not reach the data source 'Warehouse'." } },
    })
    renderWidget()
    expect(await screen.findByText(/Could not reach/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()
  })

  it('trying again really refetches', async () => {
    vi.mocked(widgetDataApi.query)
      .mockRejectedValueOnce({ response: { status: 502, data: {
        code: 'source_unavailable', detail: 'Could not reach the data source.' } } })
      .mockResolvedValue({ rows: [{ name: 'A', value: 1 }] } as never)
    renderWidget()
    const button = await screen.findByRole('button', { name: /try again/i })
    // The widget may fetch more than once on mount (StrictMode, the lazy
    // viewport gate), so the property is 'one more fetch after the click and
    // the error gone', not an exact count.
    const before = vi.mocked(widgetDataApi.query).mock.calls.length
    fireEvent.click(button)
    await waitFor(() => expect(vi.mocked(widgetDataApi.query).mock.calls.length).toBeGreaterThan(before))
    await waitFor(() => expect(screen.queryByText(/Could not reach/i)).not.toBeInTheDocument())
  })

  it('offers to try again after a quota 429 as well', async () => {
    vi.mocked(widgetDataApi.query).mockRejectedValue({
      response: { status: 429, data: { code: 'quota',
        detail: 'Daily query quota reached; try again after 09:00.' } },
    })
    renderWidget()
    expect(await screen.findByText(/quota reached/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()
  })

  it('does not offer a retry for an error retrying cannot fix', async () => {
    vi.mocked(widgetDataApi.query).mockRejectedValue({
      response: { status: 413, data: { code: 'row_cap',
        detail: 'Dataset has 2,400,000 rows, above the import row cap of 2,000,000.' } },
    })
    renderWidget()
    expect(await screen.findByText(/above the import row cap/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /try again/i })).not.toBeInTheDocument()
  })
})

describe('WidgetRenderer relative dates and partial periods (Phase 6.4)', () => {
  it('names the resolved window in a header chip and flags the partial last bucket', async () => {
    const data = {
      type: 'series', rows: [{ name: '2026-08', value: 5 }, { name: '2026-09', value: 2 }], total: 2,
      relative_dates: [{ column: 'order_date', label: 'Last 2 months (incl. current)', incomplete: true,
        text: 'Last 2 months (incl. current): 1 Aug 2026 – 30 Sep 2026, counted back from latest data (14 Sep 2026)' }],
      partial_period: { label: '2026-09', through: '2026-09-14', granularity: 'month',
        text: '2026-09 is partial: the data runs to 14 Sep 2026, the month ends 30 Sep 2026' },
    }
    renderWidget({ dataOverride: data })
    const chip = await screen.findByTestId('relative-date-chip')
    expect(chip.textContent).toContain('Last 2 months (incl. current) · partial')
    expect(chip.getAttribute('title')).toContain('counted back from latest data (14 Sep 2026)')
    expect(screen.getByTestId('partial-period-note').textContent).toContain('2026-09 is partial')
  })

  it('shows no chip or note for an ordinary result', async () => {
    renderWidget({ dataOverride: { type: 'series', rows: [{ name: 'A', value: 1 }], total: 1 } })
    await waitFor(() => expect(screen.queryByTestId('relative-date-chip')).toBeNull())
    expect(screen.queryByTestId('partial-period-note')).toBeNull()
  })
})

describe('WidgetRenderer animated result (Phase 6.3)', () => {
  it('renders the play control for an animated result', async () => {
    renderWidget({ dataOverride: { type: 'animated', inner: 'bar', animate_by: 'year', domain: [0, 5],
      frames: [{ label: '2025', result: { type: 'series', rows: [{ name: 'A', value: 5 }] } }] } })
    expect(await screen.findByTestId('animated')).toBeTruthy()
    expect(screen.getByTestId('anim-label').textContent).toBe('2025')
  })
})
