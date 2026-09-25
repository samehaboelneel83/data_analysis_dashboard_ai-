/**
 * Building a graph from layers, and getting it into the widget's config.
 *
 * The editor and the save path can each be right while nothing reaches the
 * widget — the seam failure this codebase has hit often enough to name. So the
 * last block drives the real config panel rather than the editor alone.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import GraphLayersEditor from './GraphLayersEditor'
import WidgetConfigPanel from './WidgetConfigPanel'
import { CrossFilterProvider } from './CrossFilterContext'
import type { Widget } from '../../types/report'
import type { DatasetColumn } from '../../services/api'

const COLUMNS = [
  { id: 1, name: 'region', dtype: 'categorical', missing_pct: 0, stats: {} },
  { id: 2, name: 'revenue', dtype: 'numeric', missing_pct: 0, stats: {} },
  { id: 3, name: 'orders', dtype: 'numeric', missing_pct: 0, stats: {} },
] as DatasetColumn[]

describe('GraphLayersEditor', () => {
  it('explains what a layer is when there are none', () => {
    render(<GraphLayersEditor value={[]} columns={COLUMNS} onChange={vi.fn()} />)
    expect(screen.getByText(/no layers yet/i)).toBeInTheDocument()
  })

  it('adds a layer', () => {
    const onChange = vi.fn()
    render(<GraphLayersEditor value={[]} columns={COLUMNS} onChange={onChange} />)
    fireEvent.click(screen.getByRole('button', { name: /add layer/i }))
    expect(onChange).toHaveBeenCalledWith([expect.objectContaining({ mark: 'bar', axis: 'left' })])
  })

  it('offers only numeric columns as measures', () => {
    // A layer draws a number. Offering `region` produces a chart that cannot be
    // computed, discovered only after saving.
    render(<GraphLayersEditor value={[{ measure: 'revenue' }]} columns={COLUMNS} onChange={vi.fn()} />)
    const select = screen.getByLabelText(/measure for revenue/i) as HTMLSelectElement
    const options = Array.from(select.options).map(o => o.value)
    expect(options).toContain('revenue')
    expect(options).toContain('orders')
    expect(options).not.toContain('region')
  })

  it('keeps the aggregation on the layer', () => {
    // "Encounters counted, wait averaged" is the ordinary reason to put two
    // things on one chart, and one widget-level aggregation cannot say it.
    const onChange = vi.fn()
    render(<GraphLayersEditor value={[{ measure: 'revenue', aggregation: 'sum' }]}
      columns={COLUMNS} onChange={onChange} />)
    fireEvent.change(screen.getByLabelText(/aggregation for revenue/i), { target: { value: 'avg' } })
    expect(onChange).toHaveBeenCalledWith([expect.objectContaining({ aggregation: 'avg' })])
  })

  it('puts a layer on the right axis', () => {
    const onChange = vi.fn()
    render(<GraphLayersEditor value={[{ measure: 'orders' }]} columns={COLUMNS} onChange={onChange} />)
    fireEvent.change(screen.getByLabelText(/axis for orders/i), { target: { value: 'right' } })
    expect(onChange).toHaveBeenCalledWith([expect.objectContaining({ axis: 'right' })])
  })

  it("reorders layers, because draw order is the author's", () => {
    const onChange = vi.fn()
    render(<GraphLayersEditor value={[{ measure: 'revenue' }, { measure: 'orders' }]}
      columns={COLUMNS} onChange={onChange} />)
    fireEvent.click(screen.getByRole('button', { name: /move orders up/i }))
    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({ measure: 'orders' }),
      expect.objectContaining({ measure: 'revenue' }),
    ])
  })

  it('removes a layer', () => {
    const onChange = vi.fn()
    render(<GraphLayersEditor value={[{ measure: 'revenue' }, { measure: 'orders' }]}
      columns={COLUMNS} onChange={onChange} />)
    fireEvent.click(screen.getByRole('button', { name: /remove revenue/i }))
    expect(onChange).toHaveBeenCalledWith([expect.objectContaining({ measure: 'orders' })])
  })
})

describe('layers reach the widget config', () => {
  function panel(config: Record<string, unknown> = {}) {
    const onUpdate = vi.fn()
    const widget: Widget = {
      id: 1, page_id: 100, widget_type: 'custom_graph' as Widget['widget_type'],
      title: '', config, layout: { x: 0, y: 0, w: 6, h: 5 }, created_at: '2026-01-01',
    }
    render(
      <CrossFilterProvider>
        <WidgetConfigPanel widget={widget} columns={COLUMNS} onUpdate={onUpdate} />
      </CrossFilterProvider>,
    )
    return onUpdate
  }

  const lastConfig = (onUpdate: ReturnType<typeof vi.fn>) => {
    act(() => { vi.advanceTimersByTime(1000) })
    const calls = onUpdate.mock.calls
    expect(calls.length).toBeGreaterThan(0)
    const arg = calls[calls.length - 1][0]
    return (arg?.config ?? arg) as Record<string, unknown>
  }

  beforeEach(() => { vi.clearAllMocks(); vi.useFakeTimers(); localStorage.clear() })
  afterEach(() => vi.useRealTimers())

  it('offers the editor on a custom graph and saves what was built', () => {
    const onUpdate = panel()
    fireEvent.click(screen.getByRole('button', { name: /add layer/i }))
    fireEvent.change(screen.getByLabelText(/measure for layer 1/i), { target: { value: 'revenue' } })

    expect(lastConfig(onUpdate).layers)
      .toEqual([expect.objectContaining({ measure: 'revenue', mark: 'bar' })])
  })

  it('restores layers already on the widget', () => {
    panel({ layers: [{ measure: 'orders', mark: 'line', aggregation: 'sum', axis: 'right' }] })
    expect(screen.getByLabelText(/measure for orders/i)).toBeInTheDocument()
  })

  it('does not offer layers on an ordinary bar chart', () => {
    const onUpdate = vi.fn()
    const widget: Widget = {
      id: 2, page_id: 100, widget_type: 'bar' as Widget['widget_type'],
      title: '', config: {}, layout: { x: 0, y: 0, w: 6, h: 5 }, created_at: '2026-01-01',
    }
    render(
      <CrossFilterProvider>
        <WidgetConfigPanel widget={widget} columns={COLUMNS} onUpdate={onUpdate} />
      </CrossFilterProvider>,
    )
    expect(screen.queryByRole('button', { name: /add layer/i })).not.toBeInTheDocument()
  })
})
