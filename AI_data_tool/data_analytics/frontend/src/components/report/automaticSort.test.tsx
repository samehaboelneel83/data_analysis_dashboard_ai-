import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import WidgetConfigPanel from './WidgetConfigPanel'
import { CrossFilterProvider } from './CrossFilterContext'
import type { Widget, ReportPage } from '../../types/report'
import type { DatasetColumn } from '../../services/api'

/**
 * A chart built in the UI must be able to NOT state a sort.
 *
 * The server now puts a date axis in date order when the config says nothing
 * about sorting — the fix for a monthly chart drawing December before January.
 * But the panel wrote `sort_by: 'value'` into every config unconditionally,
 * from a state that defaults to 'value'. So every chart an author builds
 * through the UI states rank order explicitly, and the server's default never
 * applies: the fix worked only for charts built through the API.
 *
 * "Automatic" is now the default choice and writes nothing, which lets the
 * server decide by column type. Picking a sort explicitly still pins it.
 * Charts already saved carry `sort_by` and keep exactly the order they have.
 */
const columns: DatasetColumn[] = [
  { id: 1, name: 'arrived_at', dtype: 'datetime', missing_pct: 0, stats: {} },
  { id: 2, name: 'department', dtype: 'text', missing_pct: 0, stats: {} },
]
const pages: ReportPage[] = [{ id: 100, report_id: 1, name: 'Page 1', page_type: 'normal',
                              position: 0, widgets: [], created_at: '2026-01-01', page_size: '16:9' }]

function widget(config: Record<string, unknown>): Widget {
  return { id: 1, page_id: 100, widget_type: 'line', title: 'Arrivals', config,
           layout: { x: 0, y: 0, w: 6, h: 5 }, created_at: '2026-01-01' } as Widget
}

function panel(config: Record<string, unknown>) {
  const onUpdate = vi.fn()
  render(<CrossFilterProvider><WidgetConfigPanel widget={widget(config)} columns={columns}
    onUpdate={onUpdate} pages={pages} /></CrossFilterProvider>)
  // The sort controls live in a collapsed group, as in the panel's own tests.
  fireEvent.click(screen.getByRole('button', { name: /Sort & limit/i }))
  return onUpdate
}

beforeEach(() => { vi.useFakeTimers(); localStorage.clear() })
afterEach(() => vi.useRealTimers())

describe('a new chart leaves the sort to the server', () => {
  it('offers Automatic as the default choice', () => {
    panel({ dimension: 'arrived_at' })
    expect((screen.getByLabelText('Sort by') as HTMLSelectElement).value).toBe('')
  })

  it('writes no sort_by while the choice is Automatic', () => {
    const onUpdate = panel({ dimension: 'arrived_at' })
    // Any edit that is not the sort itself, so the panel emits a config.
    fireEvent.change(screen.getByLabelText('Sort order'), { target: { value: 'asc' } })
    act(() => { vi.advanceTimersByTime(700) })
    const [config] = onUpdate.mock.calls.at(-1)!
    expect(config.sort_by).toBeUndefined()
  })
})

describe('an explicit choice is still written', () => {
  it('pins by value when the author picks it', () => {
    const onUpdate = panel({ dimension: 'arrived_at' })
    fireEvent.change(screen.getByLabelText('Sort by'), { target: { value: 'value' } })
    act(() => { vi.advanceTimersByTime(700) })
    const [config] = onUpdate.mock.calls.at(-1)!
    expect(config.sort_by).toBe('value')
  })

  it('pins by name when the author picks it', () => {
    const onUpdate = panel({ dimension: 'department' })
    fireEvent.change(screen.getByLabelText('Sort by'), { target: { value: 'name' } })
    act(() => { vi.advanceTimersByTime(700) })
    const [config] = onUpdate.mock.calls.at(-1)!
    expect(config.sort_by).toBe('name')
  })
})

describe('charts already saved do not move', () => {
  it('shows and keeps a stored sort_by', () => {
    const onUpdate = panel({ dimension: 'arrived_at', sort_by: 'value' })
    expect((screen.getByLabelText('Sort by') as HTMLSelectElement).value).toBe('value')
    // Any edit that is not the sort itself, so the panel emits a config.
    fireEvent.change(screen.getByLabelText('Sort order'), { target: { value: 'asc' } })
    act(() => { vi.advanceTimersByTime(700) })
    const [config] = onUpdate.mock.calls.at(-1)!
    expect(config.sort_by).toBe('value')
  })
})
