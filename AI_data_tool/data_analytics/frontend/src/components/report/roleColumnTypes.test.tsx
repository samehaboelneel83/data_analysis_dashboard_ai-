import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import WidgetConfigPanel from './WidgetConfigPanel'
import { CrossFilterProvider } from './CrossFilterContext'
import { roleAccepts } from '../../types/report'
import type { Widget, ReportPage } from '../../types/report'
import type { DatasetColumn } from '../../services/api'

/**
 * A field that wants a number must not offer text columns.
 *
 * Only `measure` and `measure2` were filtered by type. Every other numeric role
 * — a bar's per-bar `target`, a bubble's `size` and `color`, a map's `lat`/`lon`,
 * a vector plot's `direction` — was handed the whole column list, so a
 * categorical column was one click away in **sixteen** widget types. `color` is
 * even labelled "Color (numeric, optional)": the label says numeric and the
 * dropdown offered text.
 *
 * Nothing downstream complains. Asked for a bar with a text `target`, the server
 * returns 200 and silently drops the target. Asked for a map with text lat/lon
 * it returns `rows: [], dropped: 120000` — a blank map, no error. So the place
 * to stop it is the place that offered the choice.
 */
const COLUMNS: DatasetColumn[] = [
  { id: 1, name: 'department',   dtype: 'text',     missing_pct: 0, stats: {} },
  { id: 2, name: 'wait_minutes', dtype: 'numeric',  missing_pct: 0, stats: {} },
  { id: 3, name: 'total_cost',   dtype: 'numeric',  missing_pct: 0, stats: {} },
  { id: 4, name: 'arrived_at',   dtype: 'datetime', missing_pct: 0, stats: {} },
]
const PAGES: ReportPage[] = [{ id: 100, report_id: 1, name: 'Page 1', page_type: 'normal',
  position: 0, widgets: [], created_at: '2026-01-01', page_size: '16:9' }]

function widget(widget_type: string): Widget {
  return { id: 1, page_id: 100, widget_type, title: 'W', config: {},
           layout: { x: 0, y: 0, w: 6, h: 4 }, created_at: '2026-01-01' } as Widget
}

function optionsOf(labelPattern: RegExp, widget_type: string): string[] {
  render(<CrossFilterProvider><WidgetConfigPanel widget={widget(widget_type)}
    columns={COLUMNS} onUpdate={vi.fn()} pages={PAGES} /></CrossFilterProvider>)
  const select = screen.getByLabelText(labelPattern) as HTMLSelectElement
  return [...select.querySelectorAll('option')]
    .map(o => (o as HTMLOptionElement).value).filter(Boolean)
}

beforeEach(() => localStorage.clear())
afterEach(() => vi.restoreAllMocks())

describe('the rule itself', () => {
  it.each(['measure', 'measure2', 'size', 'target', 'color',
           'lat', 'lon', 'lat2', 'lon2', 'direction'])('%s wants a number', (role) => {
    expect(roleAccepts(role)).toBe('numeric')
  })

  it.each(['start', 'end'])('%s wants a date', (role) => {
    expect(roleAccepts(role)).toBe('datetime')
  })

  it.each(['category', 'category2', 'group'])('%s takes anything', (role) => {
    expect(roleAccepts(role)).toBe('any')
  })

  it('an unknown role takes anything, rather than offering nothing', () => {
    expect(roleAccepts('something_new')).toBe('any')
  })
})

describe('what each field offers', () => {
  it('a bar chart target offers only numbers', () => {
    const got = optionsOf(/target/i, 'bar')
    expect(got).toContain('wait_minutes')
    expect(got).not.toContain('department')
  })

  it('a bubble size offers only numbers', () => {
    const got = optionsOf(/bubble size/i, 'bubble')
    expect(got).not.toContain('department')
  })

  it('a bubble colour offers only numbers, as its own label promises', () => {
    const got = optionsOf(/colou?r/i, 'bubble')
    expect(got).not.toContain('department')
  })

  it('a map latitude offers only numbers', () => {
    const got = optionsOf(/latitude/i, 'map_points')
    expect(got).toContain('wait_minutes')
    expect(got).not.toContain('department')
  })

  it('a vector plot direction offers only numbers', () => {
    const got = optionsOf(/direction/i, 'vector_plot')
    expect(got).not.toContain('department')
  })

  it('a schedule start offers only dates', () => {
    const got = optionsOf(/start date/i, 'schedule')
    expect(got).toContain('arrived_at')
    expect(got).not.toContain('department')
    expect(got).not.toContain('wait_minutes')
  })
})

describe('the fields that take anything are untouched', () => {
  it('a dimension still offers text', () => {
    const got = optionsOf(/dimension/i, 'bar')
    expect(got).toContain('department')
  })

  it('a dimension still offers numbers and dates', () => {
    const got = optionsOf(/dimension/i, 'bar')
    expect(got).toContain('wait_minutes')
    expect(got).toContain('arrived_at')
  })
})

describe('a column already chosen is never hidden', () => {
  it('keeps a stored value in the list even when its type no longer qualifies', () => {
    // Otherwise opening the panel on a widget saved before this rule existed
    // would silently blank the field and save the blank on the next edit.
    const w = { ...widget('bar'), config: { dimension: 'department',
                                            measure: 'wait_minutes',
                                            target: 'department' } } as Widget
    render(<CrossFilterProvider><WidgetConfigPanel widget={w} columns={COLUMNS}
      onUpdate={vi.fn()} pages={PAGES} /></CrossFilterProvider>)
    const select = screen.getByLabelText(/target/i) as HTMLSelectElement
    expect(select.value).toBe('department')
  })
})
