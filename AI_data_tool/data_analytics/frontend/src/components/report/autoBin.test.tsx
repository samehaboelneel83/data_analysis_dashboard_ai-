import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import WidgetRenderer, { binningLabel, binningTitle, type Binning } from './WidgetRenderer'
import { CrossFilterProvider } from './CrossFilterContext'
import { widgetDataApi } from '../../services/api'
import type { Widget } from '../../types/report'

/**
 * Auto-bin on the page: when the server grouped a chart's axis
 * (services/auto_bin.py), the header says how, and the slider under the chart
 * becomes the overview a reader zooms with.
 */

vi.mock('../../services/api', () => ({
  pinsApi: { create: vi.fn(), list: vi.fn().mockResolvedValue([]), remove: vi.fn() },
  widgetDataApi: { query: vi.fn() },
  boundarySetsApi: { list: vi.fn().mockResolvedValue([]), get: vi.fn(), create: vi.fn(), remove: vi.fn() },
}))

const weeks = Array.from({ length: 20 }, (_, i) => {
  const start = new Date(Date.UTC(2023, 0, 2 + 7 * i))
  const end = new Date(Date.UTC(2023, 0, 9 + 7 * i))
  return { name: `2023-W${String(i + 1).padStart(2, '0')}`, value: i,
    bin_start: start.toISOString().slice(0, 10), bin_end: end.toISOString().slice(0, 10) }
})
const binning: Binning = { column: 'd', kind: 'date', grouped: true, grain: 'week', target: 150, distinct: 700, buckets: 20 }

function lineWidget(): Widget {
  return { id: 7, page_id: 1, widget_type: 'line', title: 'Orders', config: { dimension: 'd', measure: 'qty' },
    layout: { x: 0, y: 0, w: 6, h: 5 }, created_at: '2026-01-01' } as Widget
}

beforeEach(() => { vi.mocked(widgetDataApi.query).mockReset() })

describe('auto-bin labels', () => {
  it('names the grain or the range width', () => {
    expect(binningLabel(binning)).toBe('by week')
    expect(binningLabel({ ...binning, kind: 'number', grain: null, width: 500 })).toBe('ranges of 500')
    expect(binningLabel({ ...binning, grouped: false })).toBe('')
  })
  it('says no row was dropped', () => {
    expect(binningTitle(binning)).toMatch(/700 different d values.*grouped by week.*Every row is still counted/)
  })
})

describe('a grouped chart on the page', () => {
  it('shows how it was grouped and the overview slider', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ type: 'series', rows: weeks, binning } as never)
    render(<CrossFilterProvider><WidgetRenderer widget={lineWidget()} datasetId={3} eagerFetch /></CrossFilterProvider>)
    expect(await screen.findByTestId('binning-chip')).toHaveTextContent('by week')
    await waitFor(() => expect(screen.getByTestId('overview-strip')).toBeInTheDocument())
  })

  it('an ungrouped chart keeps its ordinary slider', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ type: 'series', rows: weeks.map(({ name, value }) => ({ name, value })) } as never)
    render(<CrossFilterProvider><WidgetRenderer widget={lineWidget()} datasetId={3} eagerFetch /></CrossFilterProvider>)
    await waitFor(() => expect(widgetDataApi.query).toHaveBeenCalled())
    await new Promise(r => setTimeout(r, 20))
    expect(screen.queryByTestId('binning-chip')).not.toBeInTheDocument()
    expect(screen.queryByTestId('overview-strip')).not.toBeInTheDocument()
  })
})

describe('Top N + All Other on a text axis', () => {
  const topBinning: Binning = { column: 'product', kind: 'text', grouped: true, top_n: 10,
    top_n_choices: [10, 20, 50], target: 10, distinct: 32951, buckets: 11 }
  const donut = (): Widget => ({ id: 8, page_id: 1, widget_type: 'donut', title: 'Products',
    config: { dimension: 'product', measure: 'price' }, layout: { x: 0, y: 0, w: 6, h: 5 }, created_at: '2026-01-01' } as Widget)
  const rows = [...Array.from({ length: 10 }, (_, i) => ({ name: `p${i}`, value: 100 - i })),
    { name: 'All Other', value: 5000, other: true }]

  it('labels the chip and says every row is counted', () => {
    expect(binningLabel(topBinning)).toBe('top 10 + other')
    expect(binningTitle(topBinning)).toMatch(/32,951 different product values.*top 10.*All Other.*Every row is still counted/)
  })

  it('lets the reader ask for 50, which asks the server again', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ type: 'series', rows, binning: topBinning } as never)
    render(<CrossFilterProvider><WidgetRenderer widget={donut()} datasetId={3} eagerFetch /></CrossFilterProvider>)
    const select = await screen.findByTestId('top-n-select')
    expect(select).toHaveValue('10')
    const { fireEvent } = await import('@testing-library/react')
    fireEvent.change(select, { target: { value: '50' } })
    await waitFor(() => expect(vi.mocked(widgetDataApi.query).mock.calls.some(c => (c[1] as any).top_n === 50)).toBe(true))
  })
})
