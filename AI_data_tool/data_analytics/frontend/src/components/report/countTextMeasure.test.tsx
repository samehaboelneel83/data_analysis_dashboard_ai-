/**
 * UAT-2: "Orders = Count distinct of order_id" could not be built.
 *
 * The Measure accepted only numeric columns whatever the aggregation, so a
 * text id could not be counted: clicking order_id onto a KPI put it in the
 * card's optional Dimension, and the card read "3" -- the first order's row
 * count. The server always supported it (measure order_id + countd returns
 * 4,200). Now a text field may sit in a Measure, counted (Count, Count
 * distinct; distinct by default for an id), from the Fields panel and from
 * Assign data; sum/average stay unavailable for it; maps keep numeric
 * coordinates (C-09).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, within, act } from '@testing-library/react'
import WidgetConfigPanel from './WidgetConfigPanel'
import WidgetRenderer from './WidgetRenderer'
import { WidgetBody } from './WidgetBody'
import { CrossFilterProvider } from './CrossFilterContext'
import { roleForField } from '../../lib/fieldPlacement'
import { countSummary } from '../../lib/semanticGuard'
import { ROLE_SPECS, COUNT_MEASURE_WIDGETS } from '../../types/report'
import { widgetDataApi } from '../../services/api'
import type { Widget, ReportPage } from '../../types/report'
import type { DatasetColumn } from '../../services/api'

vi.mock('../../services/api', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  widgetDataApi: { query: vi.fn() },
  pinsApi: { create: vi.fn(), list: vi.fn().mockResolvedValue([]), remove: vi.fn() },
  boundarySetsApi: { list: vi.fn().mockResolvedValue([]), get: vi.fn(), create: vi.fn(), remove: vi.fn() },
}))

const COLUMNS: DatasetColumn[] = [
  { id: 1, name: 'order_id', dtype: 'text',     missing_pct: 0, stats: {} },
  { id: 2, name: 'region',   dtype: 'text',     missing_pct: 0, stats: {} },
  { id: 3, name: 'revenue',  dtype: 'numeric',  missing_pct: 0, stats: {} },
  { id: 4, name: 'order_date', dtype: 'datetime', missing_pct: 0, stats: {} },
] as DatasetColumn[]
const PAGES: ReportPage[] = [{ id: 100, report_id: 1, name: 'Page 1', page_type: 'normal',
  position: 0, widgets: [], created_at: '2026-01-01', page_size: '16:9' }]

function widget(widget_type: string, config: Record<string, unknown> = {}): Widget {
  return { id: 1, page_id: 100, widget_type, title: 'W', config,
           layout: { x: 0, y: 0, w: 6, h: 4 }, created_at: '2026-01-01' } as Widget
}

function panel(w: Widget, onUpdate = vi.fn()) {
  render(<CrossFilterProvider><WidgetConfigPanel widget={w} columns={COLUMNS}
    onUpdate={onUpdate} pages={PAGES} /></CrossFilterProvider>)
  return onUpdate
}

/** Assign data -> the Measure role's "+ Add" picker. */
function openMeasurePicker() {
  fireEvent.click(screen.getByRole('button', { name: /^Assign data$/ }))
  const assign = screen.getByRole('dialog', { name: /^Assign data/ })
  const section = [...assign.querySelectorAll<HTMLElement>('[data-roles-section]')]
    .find(sec => /measure/i.test(sec.querySelector('button')?.textContent ?? ''))!
  fireEvent.click(within(section).getByRole('button', { name: /^Add / }))
  return screen.getByRole('dialog', { name: /^Add / })
}

const lastConfig = (onUpdate: ReturnType<typeof vi.fn>) => onUpdate.mock.calls.at(-1)![0] as Record<string, unknown>

beforeEach(() => { localStorage.clear() })
afterEach(() => { vi.useRealTimers(); vi.clearAllMocks() })

describe('placing a text field (Fields panel click / drop)', () => {
  it('order_id clicked onto a KPI fills its Measure, not its Dimension', () => {
    const role = roleForField(ROLE_SPECS.kpi, {}, 'order_id', false, COUNT_MEASURE_WIDGETS.has('kpi'))
    expect(role?.role).toBe('measure')
  })

  it('is counted distinct for an id, counted for any other text', () => {
    expect(countSummary('order_id')).toBe('countd')
    expect(countSummary('region')).toBe('count')
    expect(countSummary('region', { region: { aggregation: 'countd' } })).toBe('countd')
  })

  it('a bar that has its category still splits by a second text field (unchanged)', () => {
    const role = roleForField(ROLE_SPECS.bar, { dimension: 'region' }, 'order_id', false, true)
    expect(role?.role).toBe('category2')
  })

  it('a text field never lands in a map coordinate (C-09)', () => {
    const role = roleForField(ROLE_SPECS.map_points, { dimension: 'region' }, 'order_id', false,
      COUNT_MEASURE_WIDGETS.has('map_points'))
    expect(String(role?.role ?? '')).not.toMatch(/^(lat|lon)/)
  })
})

describe('Assign data: a KPI measure from a text field', () => {
  it('offers order_id in the Measure and saves it counted distinct', () => {
    vi.useFakeTimers()
    const onUpdate = panel(widget('kpi'))
    const picker = openMeasurePicker()
    const offered = within(picker).getAllByRole('option').map(o => o.textContent)
    expect(offered.some(t => t?.includes('order_id'))).toBe(true)
    fireEvent.click(within(picker).getAllByRole('option').find(o => o.textContent?.includes('order_id'))!)
    act(() => { vi.advanceTimersByTime(700) })
    const cfg = lastConfig(onUpdate)
    expect(cfg.measure).toBe('order_id')
    expect(cfg.aggregation).toBe('countd')
  })

  it('offers only counting aggregations for a text measure', () => {
    panel(widget('kpi', { measure: 'order_id', aggregation: 'countd' }))
    const sel = document.getElementById('cfg-aggregation') as HTMLSelectElement
    const values = [...sel.options].map(o => o.value)
    expect(values.sort()).toEqual(['count', 'countd'])
  })

  it('a numeric measure keeps every aggregation (unchanged)', () => {
    panel(widget('kpi', { measure: 'revenue', aggregation: 'sum' }))
    const sel = document.getElementById('cfg-aggregation') as HTMLSelectElement
    const values = [...sel.options].map(o => o.value)
    expect(values).toEqual(expect.arrayContaining(['sum', 'avg', 'median', 'count', 'countd']))
  })

  it('a map latitude still offers no text field', () => {
    panel(widget('map_points'))
    fireEvent.click(screen.getByRole('button', { name: /^Assign data$/ }))
    const assign = screen.getByRole('dialog', { name: /^Assign data/ })
    const section = [...assign.querySelectorAll<HTMLElement>('[data-roles-section]')]
      .find(sec => /latitude/i.test(sec.querySelector('button')?.textContent ?? ''))!
    fireEvent.click(within(section).getByRole('button', { name: /^Add / }))
    const picker = screen.getByRole('dialog', { name: /^Add / })
    const offered = within(picker).queryAllByRole('option').map(o => o.textContent ?? '')
    expect(offered.some(t => t.includes('order_id'))).toBe(false)
  })
})

describe('the request a counted KPI sends', () => {
  it('carries measure order_id with countd', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({ type: 'scalar', rows: [{ value: 4200 }], value: 4200 } as never)
    render(<CrossFilterProvider><WidgetRenderer widget={widget('kpi', { measure: 'order_id', aggregation: 'countd' })}
      datasetId={1} /></CrossFilterProvider>)
    await screen.findByText('4,200')
    const [, cfg, , type] = vi.mocked(widgetDataApi.query).mock.calls[0] as unknown as [number, Record<string, unknown>, unknown, string]
    expect(type).toBe('kpi')
    expect(cfg.measure).toBe('order_id')
    expect(cfg.aggregation).toBe('countd')
  })
})

describe('a KPI with a text dimension', () => {
  const body = (config: Record<string, unknown>, data: Record<string, unknown>) => render(<WidgetBody
    widget={{ id: 1, page_id: 1, widget_type: 'kpi', title: 'Orders', config, layout: { x: 0, y: 0, w: 3, h: 3 } } as never}
    data={data as never} localSelected={null} onClickPoint={() => {}} broadcasts={false} />)

  it('says the number is one group of many, never just "order_id"', () => {
    const { container } = body({ dimension: 'order_id', aggregation: 'count' },
      { type: 'series', rows: [{ name: 'ORD-0001', value: 3 }, { name: 'ORD-0002', value: 1 }, { name: 'ORD-0003', value: 2 }] })
    expect(container.textContent).toContain('Rows for order_id ORD-0001 (1 of 3 groups)')
  })

  it('a plain counted KPI keeps its caption', () => {
    const { container } = body({ measure: 'order_id', aggregation: 'countd' },
      { type: 'scalar', rows: [{ name: 'order_id', value: 4200 }] })
    expect(container.textContent).toContain('Distinct order id')
    expect(container.textContent).not.toContain('groups')
  })
})
