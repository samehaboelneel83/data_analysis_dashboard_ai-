/**
 * UAT-7: a Table would not take a second value field (quantity beside revenue).
 *
 * Not a picker bug: the Table type is one grouped value per row -- its role
 * spec has a single `measure`, and the server's table shaper (shape_series)
 * and its multi-measure path (MULTI_MEASURE_WIDGETS: bar, line, area) draw
 * one value. Several value columns are what a Matrix is for (its Values take
 * several fields, `extra_measures`). So the panel now says so where the
 * author is trying, and converts the table to a Matrix in one click, rather
 * than silently replacing revenue or making a new chart.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import WidgetConfigPanel from './WidgetConfigPanel'
import { CrossFilterProvider } from './CrossFilterContext'
import { CONVERT_WIDGET_EVENT } from './ConvertToMenu'
import type { Widget, ReportPage } from '../../types/report'
import type { DatasetColumn } from '../../services/api'

const COLUMNS: DatasetColumn[] = [
  { id: 1, name: 'region',   dtype: 'text',    missing_pct: 0, stats: {} },
  { id: 2, name: 'revenue',  dtype: 'numeric', missing_pct: 0, stats: {} },
  { id: 3, name: 'quantity', dtype: 'numeric', missing_pct: 0, stats: {} },
] as DatasetColumn[]
const PAGES: ReportPage[] = [{ id: 100, report_id: 1, name: 'Page 1', page_type: 'normal',
  position: 0, widgets: [], created_at: '2026-01-01', page_size: '16:9' }]
const table = (config: Record<string, unknown>): Widget => ({ id: 5, page_id: 100, widget_type: 'table', title: 'Revenue by region',
  config, layout: { x: 0, y: 0, w: 6, h: 4 }, created_at: '2026-01-01' } as Widget)

const panel = (w: Widget) => render(<CrossFilterProvider><WidgetConfigPanel widget={w} columns={COLUMNS}
  onUpdate={vi.fn()} pages={PAGES} /></CrossFilterProvider>)

afterEach(() => vi.restoreAllMocks())

describe('a table with its value', () => {
  it('says a table shows one value and offers a Matrix', () => {
    panel(table({ dimension: 'region', measure: 'revenue', aggregation: 'sum' }))
    const pane = screen.getByTestId('data-roles-pane')
    expect(within(pane).getByTestId('table-one-value').textContent).toMatch(/one value.*Matrix/i)
  })

  it('"Convert to Matrix" keeps the rows and the value, so quantity can be added beside it', () => {
    const seen: unknown[] = []
    const spy = (e: Event) => seen.push((e as CustomEvent).detail)
    window.addEventListener(CONVERT_WIDGET_EVENT, spy)
    panel(table({ dimension: 'region', measure: 'revenue', aggregation: 'sum' }))
    fireEvent.click(within(screen.getByTestId('data-roles-pane')).getByRole('button', { name: /Convert to Matrix/ }))
    window.removeEventListener(CONVERT_WIDGET_EVENT, spy)
    expect(seen).toHaveLength(1)
    expect(seen[0]).toMatchObject({ widgetId: 5, widget_type: 'matrix',
      config: { dimension: 'region', measure: 'revenue', aggregation: 'sum' } })
  })

  it('is said in Assign data too', () => {
    panel(table({ dimension: 'region', measure: 'revenue' }))
    fireEvent.click(screen.getByRole('button', { name: /^Assign data$/ }))
    const dialog = screen.getByRole('dialog', { name: /^Assign data/ })
    expect(within(dialog).getByTestId('table-one-value')).toBeTruthy()
  })

  it('a table with no value yet says nothing', () => {
    panel(table({ dimension: 'region' }))
    expect(screen.queryByTestId('table-one-value')).toBeNull()
  })
})
