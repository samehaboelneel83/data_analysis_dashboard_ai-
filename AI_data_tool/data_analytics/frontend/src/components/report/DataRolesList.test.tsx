import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act, within } from '@testing-library/react'
import WidgetConfigPanel from './WidgetConfigPanel'
import { CrossFilterProvider } from './CrossFilterContext'
import { ASSIGN_DATA_EVENT } from './WidgetPlaceholder'
import type { Widget, ReportPage } from '../../types/report'
import type { DatasetColumn } from '../../services/api'

// The Data roles pane, laid out as SAS VA does: roles as sections with "+ Add",
// assigned fields as links that open their own settings, and "Assign data" as
// a dialog holding every role's picker.

const COLUMNS: DatasetColumn[] = [
  { id: 1, name: 'region',     dtype: 'text',     missing_pct: 0, stats: {} },
  { id: 2, name: 'sales',      dtype: 'numeric',  missing_pct: 0, stats: {} },
  { id: 3, name: 'ordered_at', dtype: 'datetime', missing_pct: 0, stats: {} },
]

function bar(config: Record<string, unknown> = {}, id = 1): Widget {
  return { id, page_id: 100, widget_type: 'bar', title: `Sales by region ${id}`, config,
           layout: { x: 0, y: 0, w: 6, h: 4 }, created_at: '2026-01-01' } as Widget
}
const page = (widgets: Widget[]): ReportPage[] => [{ id: 100, report_id: 1, name: 'Page 1',
  page_type: 'normal', position: 0, widgets, created_at: '2026-01-01', page_size: '16:9' } as ReportPage]

function renderPanel(w: Widget, onUpdate = vi.fn(), pages = page([w])) {
  render(<CrossFilterProvider><WidgetConfigPanel widget={w} columns={COLUMNS}
    onUpdate={onUpdate} pages={pages} /></CrossFilterProvider>)
  return onUpdate
}
const lastConfig = (onUpdate: ReturnType<typeof vi.fn>) => onUpdate.mock.calls.at(-1)![0]

beforeEach(() => { localStorage.clear(); vi.useFakeTimers() })
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })

describe('the pane', () => {
  it('lists each role with what it holds; + Add is greyed where the role is full', () => {
    renderPanel(bar({ dimension: 'region', measure: 'sales' }))
    const pane = screen.getByTestId('data-roles-list')
    expect(within(pane).getByRole('button', { name: 'region, Dimension' })).toBeTruthy()
    expect(within(pane).getByRole('button', { name: 'sales, Measure' })).toBeTruthy()
    // Dimension and Measure are single-field roles and full; Series is empty.
    expect((within(pane).getByRole('button', { name: 'Add Dimension' }) as HTMLButtonElement).disabled).toBe(true)
    expect((within(pane).getByRole('button', { name: 'Add Series' }) as HTMLButtonElement).disabled).toBe(false)
  })

  it('a measure opens Name and Aggregation, and the aggregation is saved', () => {
    const onUpdate = renderPanel(bar({ dimension: 'region', measure: 'sales' }))
    fireEvent.click(screen.getByRole('button', { name: 'sales, Measure' }))
    expect(screen.getByLabelText('Name:', { selector: '#data-role-name-measure' })).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Aggregation:'), { target: { value: 'avg' } })
    act(() => { vi.advanceTimersByTime(700) })
    expect(lastConfig(onUpdate)).toMatchObject({ measure: 'sales', aggregation: 'avg' })
  })

  it('the measure name is the axis title', () => {
    const onUpdate = renderPanel(bar({ dimension: 'region', measure: 'sales' }))
    fireEvent.click(screen.getByRole('button', { name: 'sales, Measure' }))
    fireEvent.change(screen.getByLabelText('Name:', { selector: '#data-role-name-measure' }),
      { target: { value: 'Revenue' } })
    act(() => { vi.advanceTimersByTime(700) })
    expect(lastConfig(onUpdate)).toMatchObject({ y_axis_label: 'Revenue' })
  })

  it('a date dimension opens its date grouping', () => {
    renderPanel(bar({ dimension: 'ordered_at', measure: 'sales' }))
    expect(screen.queryByLabelText('Group dates by')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'ordered_at, Dimension' }))
    expect(screen.getByLabelText('Group dates by')).toBeTruthy()
  })

  it('× removes the field from its role', () => {
    const onUpdate = renderPanel(bar({ dimension: 'region', measure: 'sales' }))
    fireEvent.click(screen.getByRole('button', { name: 'Remove sales from Measure' }))
    act(() => { vi.advanceTimersByTime(700) })
    expect(lastConfig(onUpdate).measure).toBeFalsy()
    expect(lastConfig(onUpdate).dimension).toBe('region')
  })
})

describe('+ Add', () => {
  it('offers only the fields the role accepts, and a click assigns a one-field role', () => {
    const onUpdate = renderPanel(bar({ dimension: 'region' }))
    fireEvent.click(screen.getByRole('button', { name: 'Add Measure' }))
    const dialog = screen.getByRole('dialog', { name: 'Add Measure' })
    const offered = within(dialog).getAllByRole('option').map(o => o.textContent)
    expect(offered).toEqual(['sales'])                      // numbers only
    fireEvent.click(within(dialog).getByRole('option', { name: 'sales' }))
    expect(screen.queryByRole('dialog')).toBeNull()
    act(() => { vi.advanceTimersByTime(700) })
    expect(lastConfig(onUpdate)).toMatchObject({ dimension: 'region', measure: 'sales' })
  })

  it('a role that takes several fields is a checklist, appended in the order ticked', () => {
    const cols: DatasetColumn[] = [...COLUMNS,
      { id: 4, name: 'cost', dtype: 'numeric', missing_pct: 0, stats: {} },
      { id: 5, name: 'units', dtype: 'numeric', missing_pct: 0, stats: {} }]
    const w = { ...bar({ measures: ['sales'] }), widget_type: 'card' } as Widget
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel widget={w} columns={cols}
      onUpdate={onUpdate} pages={page([w])} /></CrossFilterProvider>)
    fireEvent.click(screen.getByRole('button', { name: 'Add Fields' }))
    const dialog = screen.getByRole('dialog', { name: 'Add Fields' })
    const box = (name: string) => within(dialog).getByRole('checkbox', { name: new RegExp(`^${name}`) }) as HTMLInputElement
    expect(box('sales').checked).toBe(true)                 // what it holds, ticked
    expect(within(dialog).queryByRole('checkbox', { name: /region/ })).toBeNull()
    fireEvent.click(box('units'))
    fireEvent.click(box('cost'))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Add' }))
    act(() => { vi.advanceTimersByTime(700) })
    expect(lastConfig(onUpdate).measures).toEqual(['sales', 'units', 'cost'])
  })
})

describe('Assign data', () => {
  it('opens a dialog holding every role picker, and Done closes it', () => {
    const onUpdate = renderPanel(bar())
    fireEvent.click(screen.getByRole('button', { name: /^Assign data$/ }))
    const dialog = screen.getByRole('dialog', { name: /Assign data/ })
    fireEvent.change(within(dialog).getByLabelText(/^Dimension/), { target: { value: 'region' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Done' }))
    expect(screen.queryByRole('dialog')).toBeNull()
    act(() => { vi.advanceTimersByTime(700) })
    expect(lastConfig(onUpdate)).toMatchObject({ dimension: 'region' })
    expect(screen.getByRole('button', { name: 'region, Dimension' })).toBeTruthy()
  })


  it('opens by itself when a chart is inserted', () => {
    renderPanel(bar())
    expect(screen.queryByRole('dialog')).toBeNull()
    act(() => { window.dispatchEvent(new CustomEvent(ASSIGN_DATA_EVENT, { detail: { widgetId: 1 } })) })
    expect(screen.getByRole('dialog', { name: /Assign data/ })).toBeTruthy()
  })

  it('switching objects from the pane does not open it', () => {
    const w1 = bar({}, 1), w2 = bar({}, 2)
    const seen: unknown[] = []
    const spy = (e: Event) => seen.push((e as CustomEvent).detail)
    window.addEventListener(ASSIGN_DATA_EVENT, spy)
    renderPanel(w1, vi.fn(), page([w1, w2]))
    fireEvent.change(screen.getByLabelText('Object'), { target: { value: '2' } })
    window.removeEventListener(ASSIGN_DATA_EVENT, spy)
    expect(seen).toEqual([{ widgetId: 2, open: false }])
    expect(screen.queryByRole('dialog')).toBeNull()
  })
})
