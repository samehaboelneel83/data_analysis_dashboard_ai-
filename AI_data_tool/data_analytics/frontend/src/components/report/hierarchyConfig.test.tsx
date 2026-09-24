import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import WidgetConfigPanel from './WidgetConfigPanel'
import { CrossFilterProvider } from './CrossFilterContext'
import { HIERARCHY_WIDGETS, PARTITION_WIDGETS } from '../../types/report'
import type { Widget } from '../../types/report'
import type { DatasetColumn } from '../../services/api'

/**
 * The hierarchy widgets shipped in the palette with no options block, so
 * every user-created one failed with "Choose the columns that form the
 * hierarchy" — advice the UI gave no way to follow.
 *
 * The property that matters most here is the MODE TOGGLE. The shaper branches
 * on `id_col && parent_col`, so a config carrying both a `levels` array and the
 * parent-child pair silently renders as parent-child — ignoring the levels the
 * user just picked. Switching mode must therefore DELETE the other mode's keys,
 * and that deletion is what these tests pin.
 */

const col = (name: string, dtype: string): DatasetColumn =>
  ({ id: 0, name, dtype, missing_pct: 0, stats: {} } as DatasetColumn)

const COLUMNS: DatasetColumn[] = [
  col('country', 'text'), col('region', 'text'), col('city', 'text'),
  col('employee_id', 'text'), col('manager_id', 'text'), col('revenue', 'numeric'),
]

function panel(widgetType: string, config: Record<string, unknown> = {}) {
  const onUpdate = vi.fn()
  const widget: Widget = {
    id: 1, page_id: 100, widget_type: widgetType as Widget['widget_type'],
    title: '', config, layout: { x: 0, y: 0, w: 6, h: 5 }, created_at: '2026-01-01',
  }
  render(
    <CrossFilterProvider>
      <WidgetConfigPanel widget={widget} columns={COLUMNS} onUpdate={onUpdate} />
    </CrossFilterProvider>,
  )
  return onUpdate
}

/** The last config the panel emitted. The save effect is debounced, so the
 *  timers have to be run forward before anything is asserted. */
const lastConfig = (onUpdate: ReturnType<typeof vi.fn>) => {
  // 600ms debounce, and the save effect skips the first render via a
  // mounted ref -- so the timers must be advanced past it inside act().
  act(() => { vi.advanceTimersByTime(1000) })
  const calls = onUpdate.mock.calls
  expect(calls.length).toBeGreaterThan(0)
  const arg = calls[calls.length - 1][0]
  return (arg?.config ?? arg) as Record<string, unknown>
}

beforeEach(() => { vi.clearAllMocks(); vi.useFakeTimers(); localStorage.clear() })
afterEach(() => vi.useRealTimers())

describe('hierarchy widget configuration', () => {
  it('emits levels in the order they were clicked', () => {
    // Click order is nesting order — outer first. Sorting them alphabetically
    // would silently restructure the user's hierarchy.
    const onUpdate = panel('sunburst')
    fireEvent.click(screen.getByLabelText('Level region'))
    fireEvent.click(screen.getByLabelText('Level country'))

    expect(lastConfig(onUpdate).levels).toEqual(['region', 'country'])
  })

  it('numbers each chosen level so the order is visible', () => {
    panel('tree')
    fireEvent.click(screen.getByLabelText('Level country'))
    fireEvent.click(screen.getByLabelText('Level region'))
    expect(screen.getByText('#1')).toBeInTheDocument()
    expect(screen.getByText('#2')).toBeInTheDocument()
  })

  it('offers only adding-up aggregations on a sunburst', () => {
    // A wedge is a share of its parent; an average does not add up across
    // levels, so offering it would let the user build a chart that lies.
    panel('sunburst')
    const agg = screen.getByLabelText(/aggregation/i) as HTMLSelectElement
    const values = Array.from(agg.options).map(o => o.value)
    expect(values).toContain('sum')
    expect(values).not.toContain('avg')
  })

  it('offers every aggregation on a tree', () => {
    // Nothing is area-encoded — the number is printed, so there is no geometry
    // to contradict.
    panel('tree')
    const agg = screen.getByLabelText(/aggregation/i) as HTMLSelectElement
    const values = Array.from(agg.options).map(o => o.value)
    expect(values).toContain('avg')
  })

  /**
   * Driven from the CONSTANT rather than a list written here, so the next
   * layout added to the family is covered the day it is added.
   *
   * This is the exact failure the file's header describes: five hierarchy
   * widgets reached the palette with no options block, and every user-created
   * one failed asking for columns the interface gave no way to choose. A test
   * naming each type by hand would have kept passing through that, because the
   * types it named were the ones someone remembered.
   */
  describe.each(HIERARCHY_WIDGETS.map(w => [w]))('%s', (wt) => {
    it('can be given its levels', () => {
      const onUpdate = panel(wt)
      fireEvent.click(screen.getByLabelText('Level region'))
      expect(lastConfig(onUpdate).levels).toEqual(['region'])
    })

    it('offers exactly the aggregations its geometry can tell the truth with', () => {
      panel(wt)
      const agg = screen.getByLabelText(/aggregation/i) as HTMLSelectElement
      const values = Array.from(agg.options).map(o => o.value)
      expect(values).toContain('sum')
      // A partition layout encodes value as extent, so a non-additive
      // aggregation must not even be offered; the others print the number.
      expect(values.includes('avg')).toBe(!PARTITION_WIDGETS.includes(wt))
    })
  })
})

describe('the mode toggle clears the other mode', () => {
  it('drops levels when switching to parent-child', () => {
    // THE test. The shaper prefers parent-child whenever both keys are set, so
    // a stale `levels` array is not merely untidy — it would be ignored, and
    // the user would see a hierarchy they did not ask for.
    const onUpdate = panel('org', { levels: ['country', 'region'] })
    fireEvent.click(screen.getByLabelText(/parent-child/i))
    fireEvent.change(screen.getByLabelText(/^ID column$/i), { target: { value: 'employee_id' } })
    fireEvent.change(screen.getByLabelText(/^Parent column$/i), { target: { value: 'manager_id' } })

    const c = lastConfig(onUpdate)
    expect(c.id_col).toBe('employee_id')
    expect(c.parent_col).toBe('manager_id')
    expect(c.levels).toBeUndefined()
  })

  it('drops the parent-child pair when switching back to levels', () => {
    const onUpdate = panel('org', { id_col: 'employee_id', parent_col: 'manager_id' })
    fireEvent.click(screen.getByLabelText(/level columns/i))
    fireEvent.click(screen.getByLabelText('Level country'))

    const c = lastConfig(onUpdate)
    expect(c.levels).toEqual(['country'])
    expect(c.id_col).toBeUndefined()
    expect(c.parent_col).toBeUndefined()
  })

  it('opens in the mode the saved widget was authored in', () => {
    panel('org', { id_col: 'employee_id', parent_col: 'manager_id' })
    expect((screen.getByLabelText(/parent-child/i) as HTMLInputElement).checked).toBe(true)
  })
})

describe('small multiples', () => {
  it('emits facet_by so the widget actually faces', () => {
    // Without it the shaper degrades to a single panel and the widget silently
    // becomes an ordinary bar chart.
    const onUpdate = panel('small_multiples')
    fireEvent.change(screen.getByLabelText(/facet by/i), { target: { value: 'region' } })
    expect(lastConfig(onUpdate).facet_by).toBe('region')
  })

  it('never offers small multiples as its own panel type', () => {
    // Recursion would be an infinite request, not a clever feature.
    panel('small_multiples')
    const inner = screen.getByLabelText(/panel chart type/i) as HTMLSelectElement
    const values = Array.from(inner.options).map(o => o.value)
    expect(values).not.toContain('small_multiples')
    expect(values).toContain('bar')
  })
})

describe('forecast', () => {
  it('lets the user choose how far ahead', () => {
    const onUpdate = panel('forecast')
    fireEvent.change(screen.getByLabelText(/periods ahead/i), { target: { value: '12' } })
    expect(lastConfig(onUpdate).forecast_periods).toBe(12)
  })

  it('clamps to the range the shaper accepts', () => {
    const onUpdate = panel('forecast')
    fireEvent.change(screen.getByLabelText(/periods ahead/i), { target: { value: '999' } })
    expect(lastConfig(onUpdate).forecast_periods).toBe(36)
  })
})
