/**
 * E08: the crosstab on screen, and the panel around it.
 *
 * The server's grid is pinned by backend/tests/test_pivot_goldens.py. These
 * tests pin what the reader sees of it: the subtotal column is called
 * "Total", an intersection with no value is a dash (never "null" or 0), small
 * cells hidden by suppression are said to be hidden, rows with no category
 * on either axis are counted, and the panel offers no control the grid
 * ignores.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import WidgetRenderer from './WidgetRenderer'
import WidgetConfigPanel from './WidgetConfigPanel'
import { CrossFilterProvider } from './CrossFilterContext'
import { widgetDataApi } from '../../services/api'
import type { Widget } from '../../types/report'
import type { DatasetColumn } from '../../services/api'

vi.mock('../../services/api', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  widgetDataApi: { query: vi.fn() },
  pinsApi: { create: vi.fn(), list: vi.fn().mockResolvedValue([]), remove: vi.fn() },
  boundarySetsApi: { list: vi.fn().mockResolvedValue([]), get: vi.fn(), create: vi.fn(), remove: vi.fn() },
}))

function crosstab(config: Record<string, unknown> = {}, type: Widget['widget_type'] = 'crosstab'): Widget {
  return {
    id: 7, page_id: 100, widget_type: type, title: 'Revenue by region and quarter',
    config: { dimension: 'region', dimension2: 'quarter', measure: 'revenue', ...config },
    layout: { x: 0, y: 0, w: 6, h: 5 }, created_at: '2026-01-01',
  }
}

const GRID = {
  type: 'crosstab', dimension: 'region', dimension2: 'quarter',
  columns: ['region', 'Q1', 'Q2', '__total__'],
  rows: [['North', 150, null, 150], ['South', null, 100, 100], ['West', 50, null, 50]],
  total: 3, rows_scanned: 13,
  missing_category: { rows: 2, columns: ['region', 'quarter'] },
  truncation: { applied: false, shown: 3, of: 3, limit: 50, reason: 'limit', unit: 'groups' },
  suppressed_cells: 4,
  totals: [null, 200, 100, 300],
}

async function renderGrid(config: Record<string, unknown> = {}) {
  vi.mocked(widgetDataApi.query).mockResolvedValue(GRID as any)
  const view = render(<CrossFilterProvider><WidgetRenderer widget={crosstab(config)} datasetId={1} /></CrossFilterProvider>)
  await screen.findByTestId('table-totals-row')
  return view
}

describe('the crosstab on screen', () => {
  it('heads the row subtotal column "Total", not its internal name', async () => {
    const { container } = await renderGrid({ show_totals: true, suppress_below: 2 })
    const headers = [...container.querySelectorAll('thead th')].map(th => th.textContent)
    expect(headers).toEqual(['region', 'Q1', 'Q2', 'Total'])
    expect(container.textContent).not.toContain('__total__')
  })

  it('draws a cell with no value as a dash, never "null" or 0', async () => {
    const { container } = await renderGrid({ show_totals: true, suppress_below: 2 })
    const north = [...container.querySelectorAll('tbody tr')[0].querySelectorAll('td')].map(td => td.textContent)
    expect(north[0]).toBe('North')
    expect(north[2]).toBe('—')
    expect(container.textContent).not.toMatch(/null|NaN/)
  })

  it('says how many cells suppression hid, and why', async () => {
    await renderGrid({ show_totals: true, suppress_below: 2 })
    expect(screen.getByTestId('suppressed-cells-note')).toHaveTextContent('4 cells hidden: fewer than 2 rows each')
  })

  it('names both axes when rows are missing a category', async () => {
    await renderGrid({ show_totals: true })
    expect(screen.getByTestId('missing-category-note')).toHaveTextContent('2 rows with no region or quarter are not shown')
  })
})

describe('the panel offers only what the grid does', () => {
  const columns: DatasetColumn[] = [
    { id: 1, name: 'region', dtype: 'text', missing_pct: 0, stats: {} },
    { id: 2, name: 'quarter', dtype: 'text', missing_pct: 0, stats: {} },
    { id: 3, name: 'revenue', dtype: 'numeric', missing_pct: 0, stats: {} },
  ]
  beforeEach(() => { vi.useFakeTimers(); localStorage.clear() })
  afterEach(() => vi.useRealTimers())

  function openSort(widget: Widget, onUpdate = vi.fn()) {
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget} columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)
    fireEvent.click(screen.getByRole('button', { name: /Sort & limit/i }))
    return onUpdate
  }

  it('hides the sort column on a grid: a grid sorts rows by subtotal or label', () => {
    openSort(crosstab())
    expect(screen.queryByText('Sort column (overrides sort by)')).not.toBeInTheDocument()
    // Everything the grid does honour is still there.
    expect(screen.getByText('Sort by')).toBeInTheDocument()
    expect(screen.getByText('Row limit')).toBeInTheDocument()
    expect(screen.getByText('Quick calculation')).toBeInTheDocument()
    expect(screen.getByText('Suppress small groups')).toBeInTheDocument()
    expect(screen.getByText('Rows in label order')).toBeInTheDocument()
  })

  it('keeps the sort column on a one-dimension chart', () => {
    openSort({ ...crosstab(), widget_type: 'bar', config: { dimension: 'region', measure: 'revenue' } })
    expect(screen.getByText('Sort column (overrides sort by)')).toBeInTheDocument()
  })

  it('offers no running metric on a two-dimension bar, and does not save a stale one', () => {
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel widget={crosstab({ running: 'sum', sort_col: 'revenue' }, 'bar')}
      columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)
    expect(screen.queryByText('Running metric')).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Aggregation'), { target: { value: 'avg' } })
    act(() => { vi.advanceTimersByTime(700) })
    expect(onUpdate).toHaveBeenCalled()
    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.running).toBeUndefined()
    expect(config.sort_col).toBeUndefined()
  })

  it('offers a KPI no sort, limit or aggregate filter: it has one number', () => {
    openSort({ ...crosstab(), widget_type: 'kpi', config: { measure: 'revenue' } })
    for (const label of ['Sort by', 'Row limit', 'Quick calculation', 'Suppress small groups',
      'Filter aggregated values', 'Custom order (comma-separated)']) {
      expect(screen.queryByText(label)).not.toBeInTheDocument()
    }
    // Auto-reload is the browser's, and works for every widget.
    expect(screen.getByText('Auto-reload (seconds)')).toBeInTheDocument()
  })

  it('offers a two-measure chart the row limit alone: its shaper honours nothing else', () => {
    openSort({ ...crosstab(), widget_type: 'butterfly',
      config: { dimension: 'region', measure: 'revenue', measure2: 'revenue' } })
    expect(screen.getByText('Row limit')).toBeInTheDocument()
    expect(screen.queryByText('Sort by')).not.toBeInTheDocument()
    expect(screen.queryByText('Quick calculation')).not.toBeInTheDocument()
  })
})
