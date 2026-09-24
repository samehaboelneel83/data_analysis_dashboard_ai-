import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import WidgetConfigPanel from './WidgetConfigPanel'
import { CrossFilterProvider } from './CrossFilterContext'
import type { Widget, ReportPage } from '../../types/report'
import type { DatasetColumn } from '../../services/api'

/**
 * The second axis must be aggregable from the UI, not only from the API.
 *
 * A dual-axis chart exists because its two numbers are different kinds of
 * number — encounters COUNTED against wait AVERAGED — and until now one
 * aggregation was applied to both, so that pairing could not be built at all.
 * The server now accepts `aggregation2`; a setting only the API can reach is
 * not a feature an author has.
 *
 * The control appears only where the server actually reads it: the six widget
 * types served by the dual-series shaper, and only once a second measure is
 * chosen. Offering it elsewhere would be a control wired to nothing.
 */
const columns: DatasetColumn[] = [
  { id: 1, name: 'department',   dtype: 'text',   missing_pct: 0, stats: {} },
  { id: 2, name: 'encounter_id', dtype: 'int',    missing_pct: 0, stats: {} },
  { id: 3, name: 'wait_minutes', dtype: 'float',  missing_pct: 0, stats: {} },
]

function widget(widget_type: string, config: Record<string, unknown>): Widget {
  return { id: 1, page_id: 100, widget_type, title: 'Volume and wait', config,
           layout: { x: 0, y: 0, w: 6, h: 5 }, created_at: '2026-01-01' } as Widget
}
const pages: ReportPage[] = [{ id: 100, report_id: 1, name: 'Page 1', page_type: 'normal',
                               position: 0, widgets: [], created_at: '2026-01-01', page_size: '16:9' }]

const DUAL = { dimension: 'department', measure: 'encounter_id',
               measure2: 'wait_minutes', aggregation: 'count' }

function panel(w: Widget, onUpdate = vi.fn()) {
  render(<CrossFilterProvider><WidgetConfigPanel widget={w} columns={columns}
    onUpdate={onUpdate} pages={pages} /></CrossFilterProvider>)
  return onUpdate
}

const LABEL = 'Aggregation · second measure'

beforeEach(() => { vi.useFakeTimers(); localStorage.clear() })
afterEach(() => vi.useRealTimers())

describe('the second measure has its own aggregation', () => {
  it('offers the control on a dual-axis chart that has two measures', () => {
    panel(widget('dual_axis_bar_line', DUAL))
    expect(screen.getByLabelText(LABEL)).toBeInTheDocument()
  })

  it('writes aggregation2 into the config when one is chosen', () => {
    const onUpdate = panel(widget('dual_axis_bar_line', DUAL))
    fireEvent.change(screen.getByLabelText(LABEL), { target: { value: 'avg' } })
    act(() => { vi.advanceTimersByTime(700) })
    const [config] = onUpdate.mock.calls.at(-1)!
    expect(config.aggregation2).toBe('avg')
  })

  it('drops aggregation2 again when set back to "same as above"', () => {
    // The blank option must actually REMOVE the key, not write an empty string:
    // the server reads `aggregation2 or aggregation`, and "" would be a
    // falsy value that happens to work today for reasons the panel shouldn't
    // rely on.
    const onUpdate = panel(widget('dual_axis_bar_line', { ...DUAL, aggregation2: 'avg' }))
    fireEvent.change(screen.getByLabelText(LABEL), { target: { value: '' } })
    act(() => { vi.advanceTimersByTime(700) })
    const [config] = onUpdate.mock.calls.at(-1)!
    expect(config.aggregation2).toBeUndefined()
  })

  it('shows the saved value when reopening a widget that has one', () => {
    panel(widget('dual_axis_bar_line', { ...DUAL, aggregation2: 'avg' }))
    expect((screen.getByLabelText(LABEL) as HTMLSelectElement).value).toBe('avg')
  })
})

describe('it is not offered where the server would ignore it', () => {
  it('is hidden on a plain bar chart', () => {
    panel(widget('bar', { dimension: 'department', measure: 'wait_minutes' }))
    expect(screen.queryByLabelText(LABEL)).not.toBeInTheDocument()
  })

  it('is hidden on a dual-axis chart with no second measure yet', () => {
    panel(widget('dual_axis_bar_line',
      { dimension: 'department', measure: 'encounter_id', aggregation: 'count' }))
    expect(screen.queryByLabelText(LABEL)).not.toBeInTheDocument()
  })

  it('is hidden on a bubble chart, whose measure2 a different shaper handles', () => {
    panel(widget('bubble', { ...DUAL, size: 'wait_minutes' }))
    expect(screen.queryByLabelText(LABEL)).not.toBeInTheDocument()
  })
})
