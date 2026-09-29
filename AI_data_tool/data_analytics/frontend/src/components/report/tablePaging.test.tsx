import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import WidgetRenderer, { isRawTable, mergeTablePage, TABLE_PAGE } from './WidgetRenderer'
import { CrossFilterProvider } from './CrossFilterContext'
import { widgetDataApi } from '../../services/api'
import type { Widget } from '../../types/report'

/**
 * A raw table reads its rows a page at a time. Dashboard 213's "All data"
 * table downloaded 10,000 rows (2.9 MB) on every open; now the first request
 * asks for TABLE_PAGE rows and the rest follow as the reader scrolls.
 */

vi.mock('../../services/api', () => ({
  pinsApi: { create: vi.fn(), list: vi.fn().mockResolvedValue([]), remove: vi.fn() },
  widgetDataApi: { query: vi.fn() },
  boundarySetsApi: { list: vi.fn().mockResolvedValue([]), get: vi.fn(), create: vi.fn(), remove: vi.fn() },
}))

const TOTAL = 450
function serve(_ds: number, cfg: any) {
  const { offset = 0, size = 10_000 } = cfg.page ?? {}
  const rows = Array.from({ length: Math.max(0, Math.min(size, TOTAL - offset)) }, (_, i) => [offset + i, `r${offset + i}`])
  return Promise.resolve({ type: 'table', columns: ['id', 'name'], rows, total: TOTAL,
    ...(cfg.page ? { page: { offset, size, total: TOTAL } } : {}) })
}

const table = (config: Record<string, unknown> = { aggregation: 'none' }): Widget => ({
  id: 9, page_id: 1, widget_type: 'table', title: 'All data', config,
  layout: { x: 0, y: 0, w: 6, h: 5 }, created_at: '2026-01-01' } as Widget)

beforeEach(() => { vi.mocked(widgetDataApi.query).mockReset().mockImplementation(serve as never) })

describe('which tables are paged', () => {
  it('a raw table is; a grouped one is not', () => {
    expect(isRawTable('table', { aggregation: 'none' })).toBe(true)
    expect(isRawTable('table', {})).toBe(true)
    expect(isRawTable('table', { dimension: 'region' })).toBe(false)
    expect(isRawTable('table', { measure: 'amount', aggregation: 'sum' })).toBe(false)
    expect(isRawTable('bar', {})).toBe(false)
  })
})

describe('appending a page', () => {
  it('shifts the display-rule styles by the page offset', () => {
    const prev = { rows: [[0], [1]], rule_styles: { rows: [null, { fill: 'red' }], cells: { '1': { a: { fill: 'x' } } }, widget: {} }, page: {} }
    const next = { rows: [[2], [3]], rule_styles: { rows: [{ fill: 'blue' }, null], cells: { '0': { a: { fill: 'y' } } }, widget: {} } }
    const out = mergeTablePage(prev, next, 2)
    expect(out.rows).toEqual([[0], [1], [2], [3]])
    expect(out.rule_styles.rows).toEqual([null, { fill: 'red' }, { fill: 'blue' }, null])
    expect(Object.keys(out.rule_styles.cells).sort()).toEqual(['1', '2'])
  })
})

describe('a table on the page', () => {
  it('asks for one page first, then the rest until every row is there', async () => {
    render(<CrossFilterProvider><WidgetRenderer widget={table()} datasetId={3} eagerFetch /></CrossFilterProvider>)
    await waitFor(() => expect(widgetDataApi.query).toHaveBeenCalled())
    expect((vi.mocked(widgetDataApi.query).mock.calls[0][1] as any).page).toEqual({ offset: 0, size: TABLE_PAGE })
    // jsdom has no layout, so the table never fills its tile: each page asks for the next.
    await waitFor(() => expect(vi.mocked(widgetDataApi.query).mock.calls.length).toBe(3))
    const offsets = vi.mocked(widgetDataApi.query).mock.calls.map(c => (c[1] as any).page.offset)
    expect(offsets).toEqual([0, 200, 400])
    await waitFor(() => expect(screen.queryByTestId('table-footer')).toBeNull())   // all 450 on screen
  })

  it('a grouped table is not paged', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ type: 'series', rows: [{ name: 'a', value: 1 }], total: 1 } as never)
    render(<CrossFilterProvider><WidgetRenderer widget={table({ dimension: 'region', measure: 'x', aggregation: 'sum' })} datasetId={3} eagerFetch /></CrossFilterProvider>)
    await waitFor(() => expect(widgetDataApi.query).toHaveBeenCalled())
    expect((vi.mocked(widgetDataApi.query).mock.calls[0][1] as any).page).toBeUndefined()
  })
})
