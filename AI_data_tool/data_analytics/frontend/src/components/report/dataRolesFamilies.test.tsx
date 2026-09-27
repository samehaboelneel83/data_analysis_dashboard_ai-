import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act, within, cleanup } from '@testing-library/react'
import WidgetConfigPanel from './WidgetConfigPanel'
import { CrossFilterProvider } from './CrossFilterContext'
import { ROLE_SPECS, MULTI_MEASURE_WIDGETS, PIVOT_WIDGETS, roleAccepts, configKeyFor } from '../../types/report'
import type { Widget, ReportPage, WidgetType } from '../../types/report'
import type { DatasetColumn } from '../../services/api'

// "+ Add" on every role of every object family: bar, line, table, crosstab,
// maps, models... Each role's picker must offer exactly the fields that role
// can use -- a Y axis / measure numbers only, a start or end date dates only,
// an X axis / category anything -- and what is picked must land in the config
// key that role is saved under. A role that takes several fields (a card's
// fields, a model's predictors, the value axis of a bar, line or area chart)
// takes several, in the order ticked.
//
// Walks ROLE_SPECS itself, so a widget type or role added later is covered
// the day it lands, with no list here to forget to extend.

const COLUMNS: DatasetColumn[] = [
  { id: 1, name: 'region',     dtype: 'text',       missing_pct: 0, stats: {} },
  { id: 2, name: 'product',    dtype: 'text',       missing_pct: 0, stats: {} },
  { id: 3, name: 'sales',      dtype: 'numeric',    missing_pct: 0, stats: {} },
  { id: 4, name: 'cost',       dtype: 'numeric',    missing_pct: 0, stats: {} },
  { id: 5, name: 'ordered_at', dtype: 'datetime',   missing_pct: 0, stats: {} },
  { id: 6, name: 'margin',     dtype: 'calculated', missing_pct: 0, stats: {} },
]
const NUMBERS = ['sales', 'cost', 'margin']      // a formula column counts as a number
const DATES = ['ordered_at']
const EVERYTHING = COLUMNS.map(c => c.name)

const expectedFor = (role: string) => {
  const kind = roleAccepts(role)
  return kind === 'numeric' ? NUMBERS : kind === 'datetime' ? DATES : EVERYTHING
}

/** "Aa region · 4 values" / "# sales" / "sales" -> "region" / "sales". */
const fieldOf = (label: string) => label.replace(/^(ƒx|#|◷|Aa)\s+/, '').replace(/\s+·.*$/, '').replace(/\s+\(id\)$/, '').trim()

const page: ReportPage[] = [{ id: 100, report_id: 1, name: 'Page 1', page_type: 'normal', position: 0,
  widgets: [], created_at: '2026-01-01', page_size: '16:9' } as ReportPage]

function renderPanel(widget_type: string) {
  const onUpdate = vi.fn()
  const w = { id: 1, page_id: 100, widget_type, title: 'W', config: {},
              layout: { x: 0, y: 0, w: 6, h: 4 }, created_at: '2026-01-01' } as Widget
  render(<CrossFilterProvider><WidgetConfigPanel widget={w} columns={COLUMNS}
    onUpdate={onUpdate} pages={page} /></CrossFilterProvider>)
  return onUpdate
}

function openAdd(role: string) {
  const section = document.querySelector(`[data-roles-section="${role}"]`) as HTMLElement
  expect(section, `no Data roles section for ${role}`).toBeTruthy()
  const add = within(section).getByRole('button', { name: /^Add / }) as HTMLButtonElement
  expect(add.disabled, `+ Add is greyed on an empty ${role}`).toBe(false)
  fireEvent.click(add)
  return screen.getByRole('dialog', { name: /^Add / })
}

beforeEach(() => { localStorage.clear(); vi.useFakeTimers() })
afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks() })

/** Does this role take several fields on this widget type? */
const EXTRA_KEY: Record<string, string> = { category: 'rows_extra', category2: 'columns_extra', measure: 'extra_measures' }
/** Where a role's second and later fields are saved, when it takes several
 *  beyond its first (a crosstab's Rows / Columns / Measures, a chart's value axis). */
const extraKey = (type: string, role: string) =>
  PIVOT_WIDGETS.includes(type) ? EXTRA_KEY[role]
  : role === 'measure' && MULTI_MEASURE_WIDGETS.includes(type) ? 'extra_measures' : undefined
const takesSeveral = (type: string, rf: { role: string; multi?: boolean }) => !!rf.multi || !!extraKey(type, rf.role)

const FAMILIES = (Object.entries(ROLE_SPECS) as [WidgetType, typeof ROLE_SPECS[WidgetType]][])
  .filter(([, specs]) => specs.length > 0)

describe('+ Add offers the fields each role can use, for every object family', () => {
  it('covers the whole catalogue', () => {
    // A sanity floor: if ROLE_SPECS were ever emptied by mistake this file
    // would silently test nothing.
    expect(FAMILIES.length).toBeGreaterThan(60)
  })

  for (const [type, specs] of FAMILIES) {
    describe(type, () => {
      for (const rf of specs) {
        const want = expectedFor(rf.role)
        const kind = roleAccepts(rf.role)
        it(`${rf.label ?? rf.role}: offers ${kind === 'any' ? 'every field' : kind === 'numeric' ? 'numbers only' : 'dates only'}, and saves to ${configKeyFor(rf.role)}`, () => {
          const onUpdate = renderPanel(type)
          const dialog = openAdd(rf.role)

          if (takesSeveral(type, rf)) {
            const boxes = within(dialog).getAllByRole('checkbox') as HTMLInputElement[]
            const offered = boxes.map(b => fieldOf(b.closest('label')!.textContent ?? '')).sort()
            expect(offered).toEqual([...want].sort())
            // Several fields: tick two, in reverse of the listed order, and the
            // role keeps them in the order ticked.
            // (Names read before ticking: a ticked box also shows its "#1".)
            const [first, second] = [boxes[1], boxes[0]]
            const order = [first, second].map(b => fieldOf(b.closest('label')!.textContent ?? ''))
            fireEvent.click(first); fireEvent.click(second)
            fireEvent.click(within(dialog).getByRole('button', { name: 'Add' }))
            act(() => { vi.advanceTimersByTime(700) })
            const saved = onUpdate.mock.calls.at(-1)![0]
            if (rf.multi) expect(saved[configKeyFor(rf.role)]).toEqual(order)
            // The first field in the role's own key, the rest in its extra key.
            else expect([saved[configKeyFor(rf.role)], ...(saved[extraKey(type, rf.role)!] ?? [])]).toEqual(order)
          } else {
            const options = within(dialog).getAllByRole('option')
            const offered = options.map(o => fieldOf(o.textContent ?? '')).sort()
            expect(offered).toEqual([...want].sort())
            // One field: a click assigns it and closes the picker.
            const pick = options[options.length - 1]
            const name = fieldOf(pick.textContent ?? '')
            fireEvent.click(pick)
            expect(screen.queryByRole('dialog', { name: /^Add / })).toBeNull()
            act(() => { vi.advanceTimersByTime(700) })
            expect(onUpdate.mock.calls.at(-1)![0][configKeyFor(rf.role)]).toBe(name)
            // And the role is full now: its + Add is greyed, as SAS draws it.
            const section = document.querySelector(`[data-roles-section="${rf.role}"]`) as HTMLElement
            expect((within(section).getByRole('button', { name: /^Add / }) as HTMLButtonElement).disabled).toBe(true)
          }
        })
      }
    })
  }
})

describe('roles that take one field vs several', () => {
  it('only the multi roles are checklists; every other role is a single choice', () => {
    for (const [type, specs] of FAMILIES) {
      for (const rf of specs.filter(r => takesSeveral(type, r))) {
        renderPanel(type)
        expect(within(openAdd(rf.role)).queryAllByRole('option')).toHaveLength(0)
        cleanup()
      }
    }
  })
})
