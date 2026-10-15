import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act, within } from '@testing-library/react'
import WidgetConfigPanel from './WidgetConfigPanel'
import { CrossFilterProvider } from './CrossFilterContext'
import { ASSIGN_DATA_EVENT } from './WidgetPlaceholder'
import { AddFieldDialog } from './DataRolesList'
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
    const onUpdate = renderPanel(bar({ measure: 'sales' }))
    fireEvent.click(screen.getByRole('button', { name: 'Add Dimension' }))
    const dialog = screen.getByRole('dialog', { name: 'Add Dimension' })
    expect(within(dialog).getAllByRole('option')).toHaveLength(3)   // a dimension takes any field
    fireEvent.click(within(dialog).getAllByRole('option').find(o => (o.textContent ?? '').includes('region'))!)
    expect(screen.queryByRole('dialog')).toBeNull()
    act(() => { vi.advanceTimersByTime(700) })
    expect(lastConfig(onUpdate)).toMatchObject({ dimension: 'region', measure: 'sales' })
  })

  it('a bar chart takes several measures on its value axis, one series each', () => {
    const cols: DatasetColumn[] = [...COLUMNS,
      { id: 4, name: 'cost', dtype: 'numeric', missing_pct: 0, stats: {} }]
    const onUpdate = vi.fn()
    const w = bar({ dimension: 'region', measure: 'sales' })
    render(<CrossFilterProvider><WidgetConfigPanel widget={w} columns={cols}
      onUpdate={onUpdate} pages={page([w])} /></CrossFilterProvider>)
    const add = screen.getByRole('button', { name: 'Add Measure' }) as HTMLButtonElement
    expect(add.disabled).toBe(false)                        // not full with one measure
    fireEvent.click(add)
    const dialog = screen.getByRole('dialog', { name: 'Add Measure' })
    const box = (n: string) => within(dialog).getByRole('checkbox', { name: new RegExp(`^${n}`) }) as HTMLInputElement
    expect(box('sales').checked).toBe(true)
    expect(within(dialog).queryByRole('checkbox', { name: /region/ })).toBeNull()   // numbers only
    fireEvent.click(box('cost'))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Done' }))  // C-26: ticks apply at once
    act(() => { vi.advanceTimersByTime(700) })
    expect(lastConfig(onUpdate)).toMatchObject({ measure: 'sales', extra_measures: ['cost'] })
    expect(screen.getByRole('button', { name: 'cost, Measure' })).toBeTruthy()

    // A series split cannot sit beside several measures: Series says why.
    const series = screen.getByRole('button', { name: 'Add Series' }) as HTMLButtonElement
    expect(series.disabled).toBe(true)
    expect(series.title).toMatch(/cannot be drawn together/)

    // Removing the first measure promotes the next one.
    fireEvent.click(screen.getByRole('button', { name: 'Remove sales from Measure' }))
    act(() => { vi.advanceTimersByTime(700) })
    expect(lastConfig(onUpdate).measure).toBe('cost')
    expect(lastConfig(onUpdate).extra_measures).toBeUndefined()
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
    fireEvent.click(within(dialog).getByRole('button', { name: 'Done' }))  // C-26: ticks apply at once
    act(() => { vi.advanceTimersByTime(700) })
    expect(lastConfig(onUpdate).measures).toEqual(['sales', 'units', 'cost'])
  })
})

describe('Assign data', () => {
  it('two levels: the roles, then "+ Add" opens the fields that role accepts on top', () => {
    const onUpdate = renderPanel(bar())
    fireEvent.click(screen.getByRole('button', { name: /^Assign data$/ }))
    const roles = screen.getByRole('dialog', { name: /^Assign data/ })
    // Level one lists every role of the object.
    expect(roles.querySelectorAll('[data-roles-section]').length).toBeGreaterThanOrEqual(3)
    fireEvent.click(within(roles).getByRole('button', { name: 'Add Dimension' }))
    const fields = screen.getByRole('dialog', { name: 'Add Dimension' })
    fireEvent.click(within(fields).getAllByRole('option').find(o => (o.textContent ?? '').includes('region'))!)
    // Level two closes; level one stays, now showing the field under its role.
    expect(screen.queryByRole('dialog', { name: 'Add Dimension' })).toBeNull()
    expect(within(roles).getByRole('button', { name: 'region, Dimension' })).toBeTruthy()
    fireEvent.click(within(roles).getByRole('button', { name: 'Done' }))
    expect(screen.queryByRole('dialog')).toBeNull()
    act(() => { vi.advanceTimersByTime(700) })
    expect(lastConfig(onUpdate)).toMatchObject({ dimension: 'region' })
  })

  it('Escape in level two closes only level two', () => {
    renderPanel(bar())
    fireEvent.click(screen.getByRole('button', { name: /^Assign data$/ }))
    const roles = screen.getByRole('dialog', { name: /^Assign data/ })
    fireEvent.click(within(roles).getByRole('button', { name: 'Add Dimension' }))
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByRole('dialog', { name: 'Add Dimension' })).toBeNull()
    expect(screen.getByRole('dialog', { name: /^Assign data/ })).toBeTruthy()
  })


  it('C-04: a press on the backdrop alone does not close it; a full click on the backdrop does', () => {
    renderPanel(bar())
    fireEvent.click(screen.getByRole('button', { name: /^Assign data$/ }))
    const backdrop = screen.getByRole('dialog', { name: /^Assign data/ }).parentElement!
    // Closing on mousedown let the release land on whatever was under the
    // backdrop (the page-tab "+" created a page).
    fireEvent.mouseDown(backdrop)
    expect(screen.getByRole('dialog', { name: /^Assign data/ })).toBeTruthy()
    fireEvent.click(backdrop)
    expect(screen.queryByRole('dialog', { name: /^Assign data/ })).toBeNull()
  })

  it('C-04: a press that starts inside the dialog and ends on the backdrop does not close it', () => {
    renderPanel(bar())
    fireEvent.click(screen.getByRole('button', { name: /^Assign data$/ }))
    const dialog = screen.getByRole('dialog', { name: /^Assign data/ })
    fireEvent.mouseDown(dialog)
    fireEvent.click(dialog.parentElement!)
    expect(screen.getByRole('dialog', { name: /^Assign data/ })).toBeTruthy()
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

describe('C-26: a several-field role applies each tick at once', () => {
  it('ticking a field calls onApply without a footer button, and the dialog stays open', () => {
    const onApply = vi.fn(), onClose = vi.fn()
    render(<AddFieldDialog heading="Rows" multi selected={[]} onApply={onApply} onClose={onClose}
      choices={[{ value: 'region', label: 'region' }, { value: 'product', label: 'product' }]} />)
    const dialog = screen.getByRole('dialog', { name: 'Add Rows' })
    fireEvent.click(within(dialog).getByRole('checkbox', { name: /^region/ }))
    expect(onApply).toHaveBeenLastCalledWith(['region'])
    fireEvent.click(within(dialog).getByRole('checkbox', { name: /^product/ }))
    expect(onApply).toHaveBeenLastCalledWith(['region', 'product'])
    expect(onClose).not.toHaveBeenCalled()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Done' }))
    expect(onClose).toHaveBeenCalled()
  })
})

describe('C-27: a field dropped onto a role in the Properties pane', () => {
  const dt = (field: string) => ({ types: ['application/x-field'], getData: (k: string) => (k === 'application/x-field' ? field : ''),
    dropEffect: 'none', effectAllowed: 'all' })
  it('a numeric field dropped on the Measure role fills it', () => {
    const onUpdate = renderPanel(bar({ dimension: 'region' }))
    const section = document.querySelector('[data-roles-section="measure"]') as HTMLElement
    fireEvent.dragOver(section, { dataTransfer: dt('sales') })
    fireEvent.drop(section, { dataTransfer: dt('sales') })
    act(() => { vi.advanceTimersByTime(700) })
    expect(lastConfig(onUpdate)).toMatchObject({ dimension: 'region', measure: 'sales' })
  })
  it('a text field dropped on the Measure role is refused', () => {
    const onUpdate = renderPanel(bar({ dimension: 'ordered_at' }))
    const section = document.querySelector('[data-roles-section="measure"]') as HTMLElement
    fireEvent.drop(section, { dataTransfer: dt('region') })
    act(() => { vi.advanceTimersByTime(700) })
    expect(onUpdate.mock.calls.every(c => c[0].measure !== 'region')).toBe(true)
  })
})

describe('C-28: the field picker from the keyboard', () => {
  const choices = [{ value: 'origin_lat', label: 'origin_lat' }, { value: 'origin_lon', label: 'origin_lon' },
                   { value: 'dest_lat', label: 'dest_lat' }]
  it('Enter takes the single match', () => {
    const onApply = vi.fn(), onClose = vi.fn()
    render(<AddFieldDialog heading="Latitude" multi={false} selected={[]} choices={choices} onApply={onApply} onClose={onClose} />)
    const search = screen.getByRole('searchbox')
    fireEvent.change(search, { target: { value: 'origin_la' } })
    fireEvent.keyDown(search, { key: 'Enter' })
    expect(onApply).toHaveBeenCalledWith(['origin_lat'])
  })
  it('Enter with several matches does nothing', () => {
    const onApply = vi.fn()
    render(<AddFieldDialog heading="Latitude" multi={false} selected={[]} choices={choices} onApply={onApply} onClose={vi.fn()} />)
    const search = screen.getByRole('searchbox')
    fireEvent.change(search, { target: { value: 'lat' } })
    fireEvent.keyDown(search, { key: 'Enter' })
    expect(onApply).not.toHaveBeenCalled()
  })
  it('each option is named with its role, unlike the field-list button of the same field', () => {
    render(<AddFieldDialog heading="Latitude" multi={false} selected={[]} choices={choices} onApply={vi.fn()} onClose={vi.fn()} />)
    expect(screen.getByRole('option', { name: 'Use origin_lat for Latitude' })).toBeTruthy()
  })
})

describe('C-06: a number chosen as Word text', () => {
  it('is flagged in the Data roles pane', () => {
    const w = { ...bar({ dimension: 'sales' }), widget_type: 'word_cloud' } as Widget
    render(<CrossFilterProvider><WidgetConfigPanel widget={w} columns={COLUMNS}
      onUpdate={vi.fn()} pages={page([w])} /></CrossFilterProvider>)
    expect(screen.getByTestId('word-text-numeric')).toHaveTextContent(/number/i)
  })
  it('a text column raises no flag', () => {
    const w = { ...bar({ dimension: 'region' }), widget_type: 'word_cloud' } as Widget
    render(<CrossFilterProvider><WidgetConfigPanel widget={w} columns={COLUMNS}
      onUpdate={vi.fn()} pages={page([w])} /></CrossFilterProvider>)
    expect(screen.queryByTestId('word-text-numeric')).toBeNull()
  })
})

describe('C-10: a point map says how it places its markers', () => {
  const map = (config: Record<string, unknown>) => ({ ...bar(config), widget_type: 'map_points' } as Widget)
  it('by coordinates when both are set, by country otherwise', () => {
    const { unmount } = render(<CrossFilterProvider><WidgetConfigPanel widget={map({ lat: 'a', lon: 'b', dimension: 'region' })}
      columns={COLUMNS} onUpdate={vi.fn()} pages={page([map({})])} /></CrossFilterProvider>)
    expect(screen.getByTestId('map-mode-hint')).toHaveTextContent(/coordinates/i)
    unmount()
    render(<CrossFilterProvider><WidgetConfigPanel widget={map({ dimension: 'region' })}
      columns={COLUMNS} onUpdate={vi.fn()} pages={page([map({})])} /></CrossFilterProvider>)
    expect(screen.getByTestId('map-mode-hint')).toHaveTextContent(/country/i)
  })
})

describe('C-09 step 3: the Latitude / Longitude pickers', () => {
  const cols: DatasetColumn[] = [
    { id: 1, name: 'from_city',  dtype: 'text',    missing_pct: 0, stats: {} },
    { id: 2, name: 'revenue',    dtype: 'numeric', missing_pct: 0, stats: {} },
    { id: 3, name: 'shipments',  dtype: 'numeric', missing_pct: 0, stats: {} },
    { id: 4, name: 'origin_lat', dtype: 'numeric', missing_pct: 0, stats: {} },
    { id: 5, name: 'origin_lon', dtype: 'numeric', missing_pct: 0, stats: {} },
  ]
  const ranges = { revenue: { min: 0, max: 98000 }, shipments: { min: 2, max: 40 },
                   origin_lat: { min: 24, max: 31 }, origin_lon: { min: 29, max: 35 } }
  const map = (config: Record<string, unknown>) => ({ ...bar(config), widget_type: 'map_points' } as Widget)
  const open = (config: Record<string, unknown>, role: string) => {
    const w = map(config)
    render(<CrossFilterProvider><WidgetConfigPanel widget={w} columns={cols} valueRanges={ranges}
      onUpdate={vi.fn()} pages={page([w])} /></CrossFilterProvider>)
    fireEvent.click(screen.getByRole('button', { name: `Add ${role}` }))
    return screen.getByRole('dialog', { name: `Add ${role}` })
  }
  it('lists coordinate fields first, under Geography, the matching axis on top', () => {
    const dialog = open({}, 'Longitude')
    const names = within(dialog).getAllByRole('option').map(o => o.textContent ?? '')
    expect(names[0]).toMatch(/^origin_lon/)
    expect(names[1]).toMatch(/^origin_lat/)
    expect(within(dialog).getByText('Geography')).toBeTruthy()
    expect(names.some(n => /from_city/.test(n))).toBe(false)     // text never offered
  })
  it('flags a number whose values cannot be a longitude', () => {
    const dialog = open({}, 'Longitude')
    const revenue = within(dialog).getAllByRole('option').find(o => /revenue/.test(o.textContent ?? ''))!
    expect(revenue.textContent).toMatch(/out of range/i)
    const shipments = within(dialog).getAllByRole('option').find(o => /shipments/.test(o.textContent ?? ''))!
    expect(shipments.textContent).not.toMatch(/out of range/i)
  })
  it('warns in the pane when an out-of-range field is chosen', () => {
    const w = map({ lat: 'origin_lat', lon: 'revenue' })
    render(<CrossFilterProvider><WidgetConfigPanel widget={w} columns={cols} valueRanges={ranges}
      onUpdate={vi.fn()} pages={page([w])} /></CrossFilterProvider>)
    expect(screen.getByTestId('coord-range-warning')).toHaveTextContent(/revenue/)
  })
  it('no warning for real coordinates', () => {
    const w = map({ lat: 'origin_lat', lon: 'origin_lon' })
    render(<CrossFilterProvider><WidgetConfigPanel widget={w} columns={cols} valueRanges={ranges}
      onUpdate={vi.fn()} pages={page([w])} /></CrossFilterProvider>)
    expect(screen.queryByTestId('coord-range-warning')).toBeNull()
  })
})
