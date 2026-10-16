/**
 * UAT-8: picking a measure in "Assign data" sometimes had no effect on a KPI
 * card, while the same pick in the Properties pane worked.
 *
 * "Sometimes" = when the card already had a measure (a KPI made from a field,
 * a suggestion or Copilot always does): Assign data drew the role's "+ Add"
 * greyed, because a one-field role is "full", and offered no other way to
 * choose -- although its own comment promised replacing from Assign data. The
 * click did nothing. Assign data now offers "Change" on a full one-field role
 * (the same picker; choosing replaces); the Properties pane keeps its greyed
 * "+ Add" and the field's ×.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, within, act } from '@testing-library/react'
import WidgetConfigPanel from './WidgetConfigPanel'
import { CrossFilterProvider } from './CrossFilterContext'
import { ASSIGN_DATA_EVENT } from './WidgetPlaceholder'
import type { Widget, ReportPage } from '../../types/report'
import type { DatasetColumn } from '../../services/api'

vi.mock('../../services/api', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  boundarySetsApi: { list: vi.fn().mockResolvedValue([]), get: vi.fn(), create: vi.fn(), remove: vi.fn() },
}))

const COLUMNS: DatasetColumn[] = [
  { id: 1, name: 'region',  dtype: 'text',    missing_pct: 0, stats: {} },
  { id: 2, name: 'revenue', dtype: 'numeric', missing_pct: 0, stats: {} },
  { id: 3, name: 'on_time', dtype: 'numeric', missing_pct: 0, stats: {} },
] as DatasetColumn[]
const kpi = (config: Record<string, unknown> = {}, id = 3): Widget => ({ id, page_id: 100, widget_type: 'kpi', title: 'KPI',
  config, layout: { x: 0, y: 0, w: 3, h: 2 }, created_at: '2026-01-01' } as Widget)
const pages = (ws: Widget[]): ReportPage[] => [{ id: 100, report_id: 1, name: 'Page 1', page_type: 'normal',
  position: 0, widgets: ws, created_at: '2026-01-01', page_size: '16:9' }]

beforeEach(() => { localStorage.clear(); vi.useFakeTimers() })
afterEach(() => { vi.useRealTimers(); vi.clearAllMocks() })

function pickMeasureInAssign(column: string) {
  const assign = screen.getByRole('dialog', { name: /^Assign data/ })
  const section = assign.querySelector<HTMLElement>('[data-roles-section="measure"]')!
  // A full one-field role says "Change" here (UAT-8); an empty one "+ Add".
  fireEvent.click(within(section).getByRole('button', { name: /^(Add|Change) / }))
  const picker = screen.getByRole('dialog', { name: /^Add / })
  expect(picker).toBeTruthy()
  fireEvent.click(within(picker).getAllByRole('option').find(o => o.textContent?.includes(column))!)
  act(() => { vi.advanceTimersByTime(700) })
}

describe('KPI: a measure picked in Assign data is saved', () => {
  it('from the pane\'s Assign data button', () => {
    const onUpdate = vi.fn()
    const w = kpi()
    render(<CrossFilterProvider><WidgetConfigPanel widget={w} columns={COLUMNS} onUpdate={onUpdate} pages={pages([w])} /></CrossFilterProvider>)
    fireEvent.click(screen.getByRole('button', { name: /^Assign data$/ }))
    pickMeasureInAssign('revenue')
    expect(onUpdate.mock.calls.at(-1)?.[0]).toMatchObject({ measure: 'revenue' })
  })

  it('from the tile\'s Assign data (the event), opened as the panel mounts', () => {
    const onUpdate = vi.fn()
    const w = kpi()
    render(<CrossFilterProvider><WidgetConfigPanel widget={w} columns={COLUMNS} onUpdate={onUpdate} pages={pages([w])} /></CrossFilterProvider>)
    act(() => { window.dispatchEvent(new CustomEvent(ASSIGN_DATA_EVENT, { detail: { widgetId: w.id } })) })
    pickMeasureInAssign('revenue')
    expect(onUpdate.mock.calls.at(-1)?.[0]).toMatchObject({ measure: 'revenue' })
  })

  it('replacing the measure a KPI already has', () => {
    const onUpdate = vi.fn()
    const w = kpi({ measure: 'revenue', aggregation: 'sum' })
    render(<CrossFilterProvider><WidgetConfigPanel widget={w} columns={COLUMNS} onUpdate={onUpdate} pages={pages([w])} /></CrossFilterProvider>)
    fireEvent.click(screen.getByRole('button', { name: /^Assign data$/ }))
    pickMeasureInAssign('on_time')
    expect(onUpdate.mock.calls.at(-1)?.[0]).toMatchObject({ measure: 'on_time' })
  })

  it('after the tile asks again with the panel already open (re-render with a new widget object)', () => {
    const onUpdate = vi.fn()
    const w = kpi()
    const view = render(<CrossFilterProvider><WidgetConfigPanel widget={w} columns={COLUMNS} onUpdate={onUpdate} pages={pages([w])} /></CrossFilterProvider>)
    act(() => { window.dispatchEvent(new CustomEvent(ASSIGN_DATA_EVENT, { detail: { widgetId: w.id } })) })
    const again = { ...w, config: { ...w.config } }
    view.rerender(<CrossFilterProvider><WidgetConfigPanel widget={again} columns={COLUMNS} onUpdate={onUpdate} pages={pages([again])} /></CrossFilterProvider>)
    pickMeasureInAssign('revenue')
    expect(onUpdate.mock.calls.at(-1)?.[0]).toMatchObject({ measure: 'revenue' })
  })

  it('Assign data says Change on a full role; the pane keeps its greyed + Add', () => {
    const w = kpi({ measure: 'revenue' })
    render(<CrossFilterProvider><WidgetConfigPanel widget={w} columns={COLUMNS} onUpdate={vi.fn()} pages={pages([w])} /></CrossFilterProvider>)
    const pane = screen.getByTestId('data-roles-pane')
    expect((within(pane).getByRole('button', { name: 'Add Measure' }) as HTMLButtonElement).disabled).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: /^Assign data$/ }))
    const assign = screen.getByRole('dialog', { name: /^Assign data/ })
    expect((within(assign).getByRole('button', { name: 'Change Measure' }) as HTMLButtonElement).disabled).toBe(false)
    // An empty role still reads "+ Add".
    expect(within(assign).getByRole('button', { name: 'Add Dimension' })).toBeTruthy()
  })
})
