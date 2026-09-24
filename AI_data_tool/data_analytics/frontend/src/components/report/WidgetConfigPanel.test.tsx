import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import WidgetConfigPanel from './WidgetConfigPanel'
import { CrossFilterProvider } from './CrossFilterContext'
import type { Widget } from '../../types/report'
import type { ReportPage } from '../../types/report'
import type { HierarchyNode } from '../../types/report'
import type { DatasetColumn } from '../../services/api'
import { yAxisProps } from './chartRenderers/axisOptions'
import { boundarySetsApi } from '../../services/api'
import { axeViolations } from '../../test/axe'

// Spread the real module: a partial mock of `services/api` has broken an
// unrelated test file a hundred files later in this repo before.
vi.mock('../../services/api', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  boundarySetsApi: { list: vi.fn(), get: vi.fn(), create: vi.fn(), remove: vi.fn() },
}))

function widget(overrides: Partial<Widget> = {}): Widget {
  return {
    id: 1, page_id: 100, widget_type: 'bar', title: 'Sales', config: { dimension: 'region' },
    layout: { x: 0, y: 0, w: 6, h: 5 }, created_at: '2026-01-01', ...overrides,
  }
}

function page(id: number, name: string, page_type: ReportPage['page_type']): ReportPage {
  return { id, report_id: 1, name, page_type, position: 0, widgets: [], created_at: '2026-01-01', page_size: '16:9' }
}

const columns: DatasetColumn[] = [{ id: 1, name: 'region', dtype: 'text', missing_pct: 0, stats: {} }]

// ExpandableGroup persists its open/closed state to localStorage, which jsdom keeps
// alive across tests within this file — cleared here so one test's group toggle can't
// leak into the next test's initial render state.
beforeEach(() => { vi.useFakeTimers(); localStorage.clear() })
afterEach(() => vi.useRealTimers())

describe('WidgetConfigPanel drillthrough/tooltip config', () => {
  it('hides the drillthrough/tooltip selects when the report has no such pages', () => {
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget()} columns={columns} onUpdate={vi.fn()}
      pages={[page(100, 'Page 1', 'normal')]} /></CrossFilterProvider>)
    expect(screen.queryByText('Drillthrough page')).not.toBeInTheDocument()
    expect(screen.queryByText('Tooltip page')).not.toBeInTheDocument()
  })

  it('writes drillthroughPageId to config when a drillthrough page is selected', () => {
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget()} columns={columns} onUpdate={onUpdate}
      pages={[page(100, 'Page 1', 'normal'), page(200, 'Details', 'drillthrough')]} /></CrossFilterProvider>)

    fireEvent.change(screen.getByLabelText('Drillthrough page'), { target: { value: '200' } })
    act(() => { vi.advanceTimersByTime(700) })

    expect(onUpdate).toHaveBeenCalled()
    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.drillthroughPageId).toBe(200)
  })

  it('writes tooltipPageId to config when a tooltip page is selected', () => {
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget()} columns={columns} onUpdate={onUpdate}
      pages={[page(100, 'Page 1', 'normal'), page(300, 'Tip', 'tooltip')]} /></CrossFilterProvider>)

    fireEvent.change(screen.getByLabelText('Tooltip page'), { target: { value: '300' } })
    act(() => { vi.advanceTimersByTime(700) })

    expect(onUpdate).toHaveBeenCalled()
    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.tooltipPageId).toBe(300)
  })
})

function buttonWidget(overrides: Partial<Widget> = {}): Widget {
  return { id: 5, page_id: 100, widget_type: 'button', title: 'Btn', config: { label: 'Click me' },
    layout: { x: 0, y: 0, w: 2, h: 2 }, created_at: '2026-01-01', ...overrides }
}

function bookmark(id: number, name: string) {
  return { id, report_id: 1, name, position: 0, state: { pageId: 100, activeFilters: [], promptValues: {}, hiddenWidgetIds: [] }, created_at: '2026-01-01' }
}

describe('WidgetConfigPanel button actions', () => {
  it('hides the action selects for non-button widgets', () => {
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget()} columns={columns} onUpdate={vi.fn()}
      pages={[page(100, 'Page 1', 'normal')]} bookmarks={[bookmark(1, 'My bookmark')]} /></CrossFilterProvider>)
    expect(screen.queryByLabelText('Button action')).not.toBeInTheDocument()
  })

  it('writes actionPageId when the Navigate to page action is chosen', () => {
    const onUpdate = vi.fn()
    const pages = [page(100, 'Page 1', 'normal'), page(200, 'Page 2', 'normal')]
    render(<CrossFilterProvider><WidgetConfigPanel widget={buttonWidget()} columns={columns} onUpdate={onUpdate}
      pages={pages} bookmarks={[]} /></CrossFilterProvider>)

    fireEvent.change(screen.getByLabelText('Button action'), { target: { value: 'navigate' } })
    fireEvent.change(screen.getByLabelText('Target page'), { target: { value: '200' } })
    act(() => { vi.advanceTimersByTime(700) })

    expect(onUpdate).toHaveBeenCalled()
    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.action).toBe('navigate')
    expect(config.actionPageId).toBe(200)
  })

  it('writes actionBookmarkId when the Apply bookmark action is chosen', () => {
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel widget={buttonWidget()} columns={columns} onUpdate={onUpdate}
      pages={[page(100, 'Page 1', 'normal')]} bookmarks={[bookmark(7, 'Q1 view')]} /></CrossFilterProvider>)

    fireEvent.change(screen.getByLabelText('Button action'), { target: { value: 'bookmark' } })
    fireEvent.change(screen.getByLabelText('Target bookmark'), { target: { value: '7' } })
    act(() => { vi.advanceTimersByTime(700) })

    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.action).toBe('bookmark')
    expect(config.actionBookmarkId).toBe(7)
  })
})

describe('WidgetConfigPanel Actions group (relocated button action config)', () => {
  it('renders an Actions group, open by default, for a button widget', () => {
    render(<CrossFilterProvider><WidgetConfigPanel widget={buttonWidget()} columns={columns} onUpdate={vi.fn()}
      pages={[page(100, 'Page 1', 'normal')]} bookmarks={[]} /></CrossFilterProvider>)
    const header = screen.getByRole('button', { name: /^Actions$/i })
    expect(header).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByLabelText('Button action')).toBeInTheDocument()
  })

  it('does not render an Actions group for non-button widgets', () => {
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget()} columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    expect(screen.queryByRole('button', { name: /^Actions$/i })).not.toBeInTheDocument()
  })
})

describe('WidgetConfigPanel settings filter', () => {
  it('narrows visible groups to those matching the filter text and hides the rest', () => {
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget()} columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    expect(screen.getByRole('button', { name: /Sort & limit/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Appearance/i })).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Filter settings'), { target: { value: 'sort' } })

    expect(screen.getByRole('button', { name: /Sort & limit/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Appearance/i })).not.toBeInTheDocument()
  })

  it('force-opens a matching group while filtering, without persisting that open state', () => {
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget()} columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    // Sort & limit is collapsed by default.
    expect(screen.getByRole('button', { name: /Sort & limit/i })).toHaveAttribute('aria-expanded', 'false')

    fireEvent.change(screen.getByLabelText('Filter settings'), { target: { value: 'sort' } })
    expect(screen.getByRole('button', { name: /Sort & limit/i })).toHaveAttribute('aria-expanded', 'true')

    const stored = JSON.parse(localStorage.getItem('datalytics.panelGroups') ?? '{}')
    expect(stored.sort).toBeUndefined()
  })

  it('matches a group by one of its field labels even when the query is not in the group title', () => {
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget()} columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    // "Padding" is a field inside Appearance, but does not appear in the word "Appearance".
    fireEvent.change(screen.getByLabelText('Filter settings'), { target: { value: 'padding' } })

    expect(screen.getByRole('button', { name: /Appearance/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Appearance/i })).toHaveAttribute('aria-expanded', 'true')
    expect(screen.queryByRole('button', { name: /Sort & limit/i })).not.toBeInTheDocument()
  })

  it('matches no group on a garbage query', () => {
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget()} columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    fireEvent.change(screen.getByLabelText('Filter settings'), { target: { value: 'zzz-not-a-real-field' } })

    expect(screen.queryByRole('button', { name: /Fields/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Sort & limit/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Appearance/i })).not.toBeInTheDocument()
  })

  it('restores the previous set of visible groups once the filter is cleared', () => {
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget()} columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    fireEvent.change(screen.getByLabelText('Filter settings'), { target: { value: 'sort' } })
    expect(screen.queryByRole('button', { name: /Appearance/i })).not.toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Filter settings'), { target: { value: '' } })
    expect(screen.getByRole('button', { name: /Appearance/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Sort & limit/i })).toHaveAttribute('aria-expanded', 'false')
  })
})

describe('WidgetConfigPanel bar layout mode', () => {
  it('writes bar_mode when a stacking layout is chosen for a bar widget', () => {
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget()} columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)

    fireEvent.change(screen.getByLabelText('Bar layout'), { target: { value: 'stacked100' } })
    act(() => { vi.advanceTimersByTime(700) })

    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.bar_mode).toBe('stacked100')
  })

  it('does not show the bar layout select for non-bar widget types', () => {
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget({ widget_type: 'line', config: { dimension: 'region' } })} columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    expect(screen.queryByLabelText('Bar layout')).not.toBeInTheDocument()
  })
})

describe('WidgetConfigPanel forecast method', () => {
  function forecastWidget(overrides: Partial<Widget> = {}): Widget {
    return { id: 8, page_id: 100, widget_type: 'forecast', title: 'Trend', config: { dimension: 'region' },
      layout: { x: 0, y: 0, w: 6, h: 5 }, created_at: '2026-01-01', ...overrides }
  }

  it('defaults to ets and writes nothing to config when switched back to it', () => {
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel widget={forecastWidget()} columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)
    expect(screen.getByLabelText('Forecast method')).toHaveValue('ets')

    // Round-trip through 'simple' and back to the default -- the mount-only save
    // effect never fires without a change, so this is the only way to observe that
    // the default value writes nothing.
    fireEvent.change(screen.getByLabelText('Forecast method'), { target: { value: 'simple' } })
    fireEvent.change(screen.getByLabelText('Forecast method'), { target: { value: 'ets' } })
    act(() => { vi.advanceTimersByTime(700) })
    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.method).toBeUndefined()
  })

  it('writes method when simple smoothing is chosen', () => {
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel widget={forecastWidget()} columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)

    fireEvent.change(screen.getByLabelText('Forecast method'), { target: { value: 'simple' } })
    act(() => { vi.advanceTimersByTime(700) })

    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.method).toBe('simple')
  })

  it('does not show the forecast method select for non-forecast widget types', () => {
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget()} columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    expect(screen.queryByLabelText('Forecast method')).not.toBeInTheDocument()
  })
})

function imageWidget(overrides: Partial<Widget> = {}): Widget {
  return { id: 6, page_id: 100, widget_type: 'image', title: 'Pic', config: {},
    layout: { x: 0, y: 0, w: 4, h: 4 }, created_at: '2026-01-01', ...overrides }
}

function shapeWidget(overrides: Partial<Widget> = {}): Widget {
  return { id: 7, page_id: 100, widget_type: 'shape', title: 'Box', config: {},
    layout: { x: 0, y: 0, w: 3, h: 3 }, created_at: '2026-01-01', ...overrides }
}

describe('WidgetConfigPanel image widget', () => {
  it('writes config.url when the Image URL field changes', () => {
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel widget={imageWidget()} columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)

    fireEvent.change(screen.getByLabelText('Image URL'), { target: { value: 'https://example.com/a.png' } })
    act(() => { vi.advanceTimersByTime(700) })

    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.url).toBe('https://example.com/a.png')
  })

  it('does not show role/aggregation fields for an image widget', () => {
    render(<CrossFilterProvider><WidgetConfigPanel widget={imageWidget()} columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    expect(screen.queryByText('Aggregation')).not.toBeInTheDocument()
  })
})

describe('WidgetConfigPanel shape widget', () => {
  it('writes config.shape when the shape select changes', () => {
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel widget={shapeWidget()} columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)

    fireEvent.change(screen.getByLabelText('Shape'), { target: { value: 'circle' } })
    act(() => { vi.advanceTimersByTime(700) })

    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.shape).toBe('circle')
  })
})

describe('WidgetConfigPanel analytics lines', () => {
  it('writes analytics.showAverageLine when the average-line checkbox is checked', () => {
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget()} columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)

    fireEvent.click(screen.getByLabelText('Show average line'))
    act(() => { vi.advanceTimersByTime(700) })

    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.analytics).toEqual({ showAverageLine: true })
  })

  it('writes analytics.referenceValue and referenceLabel when a reference line is set', () => {
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget()} columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)

    fireEvent.change(screen.getByLabelText('Reference line value'), { target: { value: '100' } })
    fireEvent.change(screen.getByLabelText('Reference line label'), { target: { value: 'Target' } })
    act(() => { vi.advanceTimersByTime(700) })

    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.analytics.referenceValue).toBe(100)
    expect(config.analytics.referenceLabel).toBe('Target')
  })

  it('does not show the analytics section for widget types other than bar/line', () => {
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget({ widget_type: 'pie', config: { dimension: 'region' } })} columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    expect(screen.queryByLabelText('Show average line')).not.toBeInTheDocument()
  })
})

describe('WidgetConfigPanel display rules — result-column scoping', () => {
  const structuredRule = { id: 'r1', kind: 'expression' as const, target: 'mark' as const,
    column: 'value', condition: { op: 'gt' as const, value: 0 }, expression: 'value > 0', style: {} }

  // `ruleNumericColumns` (WidgetConfigPanel.tsx) is the seam that decides which
  // columns a Bands rule may name. Nothing pinned it before: if it regressed to [],
  // DisplayRulesPanel's old fallback offered EVERY column, an author would land on a
  // text column again, and B3 would reproduce with the whole new suite still green.
  // These two tests fail on that degradation — the first because the numeric column
  // stops being the only option, the second because the empty case is now handled
  // deliberately instead of falling back to "offer everything".
  const mixedColumns: DatasetColumn[] = [
    { id: 1, name: 'region', dtype: 'text', missing_pct: 0, stats: {} },
    { id: 2, name: 'sales', dtype: 'numeric', missing_pct: 0, stats: {} },
    { id: 3, name: 'notes', dtype: 'text', missing_pct: 0, stats: {} },
  ]

  function openBandsRuleEditor(cols: DatasetColumn[]) {
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ id: 40, widget_type: 'table', config: {} })}
      columns={cols} onUpdate={vi.fn()} /></CrossFilterProvider>)
    fireEvent.click(screen.getByRole('button', { name: /Display rules/i }))
    fireEvent.click(screen.getByRole('button', { name: /add rule/i }))
    fireEvent.change(screen.getByLabelText(/rule kind/i), { target: { value: 'interval' } })
  }

  it('passes the numeric result columns down, so a Bands rule can only name a number', () => {
    openBandsRuleEditor(mixedColumns)

    const select = screen.getByLabelText(/^column$/i) as HTMLSelectElement
    expect(Array.from(select.options).map(o => o.value)).toEqual(['sales'])
    expect(select.value).toBe('sales')
  })

  it('offers a Bands rule no column at all, with a reason, when nothing is numeric', () => {
    // Known dtypes, none numeric: falling back to "offer every column" here would walk
    // the author straight back into the float() error the control exists to prevent.
    openBandsRuleEditor([mixedColumns[0], mixedColumns[2]])

    expect(screen.queryByLabelText(/^column$/i)).not.toBeInTheDocument()
    expect(screen.getByRole('note')).toHaveTextContent(/no numeric column/i)
  })

  it('offers name/value for a table widget with a dimension configured (grouped-series shape)', () => {
    // shape_series dispatches on whether a dimension is configured, not on widget
    // type — a `table` widget with `dimension` set returns {name, value} rows just
    // like a bar chart, not its own raw column list.
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ id: 20, widget_type: 'table', config: { dimension: 'region', display_rules: [structuredRule] } })}
      columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)

    fireEvent.click(screen.getByRole('button', { name: /Display rules/i }))
    const options = Array.from((screen.getByLabelText(/^column$/i) as HTMLSelectElement).options).map(o => o.value)
    expect(options).toEqual(['name', 'value'])
  })

  it('offers the dimension name and __total__ for a crosstab with a pivot configured', () => {
    // The pivoted column names (dimension2's distinct values) aren't statically
    // knowable without fetching data — only the dimension column and the __total__
    // row-total shape_series always adds are guaranteed to exist.
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ id: 21, widget_type: 'crosstab', config: { dimension: 'region', dimension2: 'segment', display_rules: [structuredRule] } })}
      columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)

    fireEvent.click(screen.getByRole('button', { name: /Display rules/i }))
    const options = Array.from((screen.getByLabelText(/^column$/i) as HTMLSelectElement).options).map(o => o.value)
    expect(options).toEqual(['region', '__total__'])
  })

  it('offers the dataset columns for a table widget with no dimension configured (raw-table shape)', () => {
    // Neither `dimension` nor `measure` is set here — the true raw-table case
    // (widget_data.py's shape_series: "not dim and not meas"). This must not collapse
    // into the scalar/measure-only branch below.
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ id: 22, widget_type: 'table', config: { display_rules: [structuredRule] } })}
      columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)

    fireEvent.click(screen.getByRole('button', { name: /Display rules/i }))
    const options = Array.from((screen.getByLabelText(/^column$/i) as HTMLSelectElement).options).map(o => o.value)
    expect(options).toEqual(['region'])
  })

  it('offers name/value for a KPI widget with a measure and no dimension (scalar shape)', () => {
    // shape_series's raw-table branch requires "not dim AND not meas"
    // (widget_data.py:199) — a measure-only KPI card (no dimension) falls through to
    // the scalar branch (widget_data.py:287-305) instead, which returns a single
    // {name, value} row, not the dataset's column list. This is an entirely ordinary
    // KPI configuration, not an edge case.
    const numericColumns: DatasetColumn[] = [...columns, { id: 2, name: 'amount', dtype: 'numeric', missing_pct: 0, stats: {} }]
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ id: 23, widget_type: 'kpi', config: { measure: 'amount', display_rules: [structuredRule] } })}
      columns={numericColumns} onUpdate={vi.fn()} /></CrossFilterProvider>)

    fireEvent.click(screen.getByRole('button', { name: /Display rules/i }))
    const options = Array.from((screen.getByLabelText(/^column$/i) as HTMLSelectElement).options).map(o => o.value)
    expect(options).toEqual(['name', 'value'])
  })

  it('offers name/start/delta/end for a waterfall widget, with start/delta/end coerced as numeric', () => {
    // shape_waterfall (widget_data.py) returns {name, start, delta, end} bars, not
    // {name, value} — the previous ['name', 'value'] approximation left `delta` (and
    // start/end) unauthorable even though display_rules.py's waterfall branch already
    // evaluates rules against exactly these columns.
    const onUpdate = vi.fn()
    const waterfallRule = { id: 'wf1', kind: 'expression' as const, target: 'mark' as const,
      column: 'delta', condition: { op: 'gt' as const, value: 0 }, expression: 'delta > 0', style: {} }
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ id: 24, widget_type: 'waterfall', config: { category: 'region', measure: 'amount', display_rules: [waterfallRule] } })}
      columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)

    fireEvent.click(screen.getByRole('button', { name: /Display rules/i }))
    const options = Array.from((screen.getByLabelText(/^column$/i) as HTMLSelectElement).options).map(o => o.value)
    expect(options).toEqual(['name', 'start', 'delta', 'end'])

    // start/delta/end must be treated as numeric for the dtype-aware coercion --
    // typing "500" into the Value field on a `delta` rule must save a number, not the
    // string "500", or `delta > "500"` would compare a numeric Series to a string.
    fireEvent.change(screen.getByLabelText(/^value$/i), { target: { value: '500' } })
    act(() => { vi.advanceTimersByTime(700) })

    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.display_rules[0].condition.value).toBe(500)
  })
})

describe('WidgetConfigPanel collapsible groups', () => {
  function renderPanel() {
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget()} columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
  }

  it('collapses an occasional section by default and opens it on click', () => {
    renderPanel()
    // Queried by exact text, not by label: a regex would also match the "Sort column
    // (overrides sort by)" label further down the same group. (These labels ARE
    // associated with their controls now -- see the label-associations tests below.)
    expect(screen.queryByText('Sort by')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Sort & limit/i }))
    expect(screen.getByText('Sort by')).toBeInTheDocument()
  })

  it('keeps the fields section open by default', () => {
    renderPanel()
    expect(screen.getByRole('button', { name: /Fields/i })).toHaveAttribute('aria-expanded', 'true')
  })
})

describe('WidgetConfigPanel formatting section', () => {
  function openFormatting() {
    fireEvent.click(screen.getByRole('button', { name: /Formatting/i }))
  }

  it('collapses the Formatting group by default, like the other occasional sections', () => {
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget()} columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    expect(screen.getByRole('button', { name: /Formatting/i })).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByLabelText('X axis label')).not.toBeInTheDocument()
  })

  it('does not show a Formatting section for a KPI, which has no formatting capabilities', () => {
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'kpi', config: { measure: 'region' } })} columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    expect(screen.queryByRole('button', { name: /Formatting/i })).not.toBeInTheDocument()
  })

  it('writes axis label, tick size/colour and axis-line/tick-mark toggles into config for a bar chart', () => {
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget()} columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)
    openFormatting()

    fireEvent.change(screen.getByLabelText('X axis label'), { target: { value: 'Region' } })
    fireEvent.change(screen.getByLabelText('Y axis label'), { target: { value: 'Revenue' } })
    fireEvent.change(screen.getByLabelText('Tick size'), { target: { value: '14' } })
    fireEvent.change(screen.getByLabelText('Tick colour'), { target: { value: '#ff0000' } })
    fireEvent.click(screen.getByLabelText('Show axis line'))
    fireEvent.click(screen.getByLabelText('Show tick marks'))
    act(() => { vi.advanceTimersByTime(700) })

    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.x_axis_label).toBe('Region')
    expect(config.y_axis_label).toBe('Revenue')
    expect(config.axis_tick_size).toBe(14)
    expect(config.axis_tick_color).toBe('#ff0000')
    expect(config.axis_line).toBe(true)
    expect(config.tick_line).toBe(true)
  })

  it('writes y_scale, y_min and y_max for a bar chart', () => {
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget()} columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)
    openFormatting()

    fireEvent.change(screen.getByLabelText('Y axis scale'), { target: { value: 'log' } })
    fireEvent.change(screen.getByLabelText('Y axis min'), { target: { value: '0' } })
    fireEvent.change(screen.getByLabelText('Y axis max'), { target: { value: '5000' } })
    act(() => { vi.advanceTimersByTime(700) })

    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.y_scale).toBe('log')
    expect(config.y_min).toBe(0)
    expect(config.y_max).toBe(5000)

    // y_min:0 degrades log to linear, but the explicit y_min/y_max must still
    // reach the axis domain -- a degraded log must not also discard the bounds.
    const axis = yAxisProps(config, false)
    expect(axis.scale).toBeUndefined()
    expect(axis.domain).toEqual([0, 5000])
  })

  it('shows the log-scale helper text explaining the linear fallback', () => {
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget()} columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    openFormatting()
    expect(screen.getByText(/A log axis cannot show zero or negative values/i)).toBeInTheDocument()
  })

  it('writes grid style and colour without inventing an untouched grid key, then writes grid once its own toggle is touched', () => {
    // Fix round 2: touching "Gridline style"/"Gridline colour" must not also invent a
    // `grid: true` the user never chose by clicking "Show gridlines" -- only controls
    // actually touched leave a key behind.
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget()} columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)
    openFormatting()

    fireEvent.change(screen.getByLabelText('Gridline style'), { target: { value: 'solid' } })
    fireEvent.change(screen.getByLabelText('Gridline colour'), { target: { value: '#00ff00' } })
    act(() => { vi.advanceTimersByTime(700) })

    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.grid).toBeUndefined()
    expect(config.grid_style).toBe('solid')
    expect(config.grid_color).toBe('#00ff00')

    fireEvent.click(screen.getByLabelText('Show gridlines'))
    act(() => { vi.advanceTimersByTime(700) })
    const [config2] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config2.grid).toBe(false)
  })

  it('writes legend position without inventing an untouched legend key for a bar chart', () => {
    // Fix round 2: touching "Legend position" alone must not also invent a
    // `legend: true` the user never chose by clicking "Show legend".
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget()} columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)
    openFormatting()

    fireEvent.change(screen.getByLabelText('Legend position'), { target: { value: 'right' } })
    act(() => { vi.advanceTimersByTime(700) })

    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.legend).toBeUndefined()
    expect(config.legend_position).toBe('right')

    fireEvent.click(screen.getByLabelText('Show legend'))
    act(() => { vi.advanceTimersByTime(700) })
    const [config2] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config2.legend).toBe(false)
  })

  it('does not offer a legend control for a line chart, whose renderer has no <Legend>', () => {
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'line', config: { dimension: 'region' } })} columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    openFormatting()
    expect(screen.queryByLabelText('Show legend')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Legend position')).not.toBeInTheDocument()
    // But it still gets data labels, y-scale and y-domain, which its renderer does honour.
    expect(screen.getByLabelText('Show data labels')).toBeInTheDocument()
    expect(screen.getByLabelText('Y axis scale')).toBeInTheDocument()
    expect(screen.getByLabelText('Y axis min')).toBeInTheDocument()
  })

  it('writes data_labels for a bar chart', () => {
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget()} columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)
    openFormatting()

    fireEvent.click(screen.getByLabelText('Show data labels'))
    act(() => { vi.advanceTimersByTime(700) })

    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.data_labels).toBe(true)
  })

  it('does not offer yScale/yDomain for a dual-axis bar chart, but keeps axes/grid/legend/dataLabels', () => {
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'dual_axis_bar', config: { measure: 'a', measure2: 'b' } })} columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    openFormatting()
    expect(screen.queryByLabelText('Y axis scale')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Y axis min')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Y axis max')).not.toBeInTheDocument()
    expect(screen.getByLabelText('X axis label')).toBeInTheDocument()
    expect(screen.getByLabelText('Show gridlines')).toBeInTheDocument()
    expect(screen.getByLabelText('Show legend')).toBeInTheDocument()
    expect(screen.getByLabelText('Show data labels')).toBeInTheDocument()
  })

  it('does not offer yScale/yDomain or legend for the Gantt (schedule) chart', () => {
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'schedule', config: {} })} columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    openFormatting()
    expect(screen.queryByLabelText('Y axis scale')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Y axis min')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Show legend')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Show data labels')).not.toBeInTheDocument()
    expect(screen.getByLabelText('X axis label')).toBeInTheDocument()
    expect(screen.getByLabelText('Show gridlines')).toBeInTheDocument()
  })

  it('does not offer yScale/yDomain for dot_plot, whose value axis is the XAxis', () => {
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'dot_plot', config: { dimension: 'region', measure: 'amount' } })} columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    openFormatting()
    expect(screen.queryByLabelText('Y axis scale')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Y axis min')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Show legend')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Show data labels')).toBeInTheDocument()
  })

  it('does not persist axis_line/tick_line for a Schedule widget when only the title changes (fix round 2)', () => {
    // ScheduleChartRenderer defaults axisLine/tickLine to true when the key is absent
    // from config (round 1 fix); this panel's own checkbox display defaults to
    // unchecked/false purely as a starting look (see the state-declaration comment in
    // WidgetConfigPanel.tsx). Before this fix, EVERY debounced save wrote
    // `axis_line: false, tick_line: false` regardless of whether the user touched
    // those controls -- so editing only the title of an existing Schedule widget would
    // silently flip its axis lines and tick marks off, undoing exactly what round 1
    // protected. The Formatting group doesn't even need to be opened here: the bug (and
    // the fix) is in what the save effect writes, not in what's visible.
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'schedule', title: 'My Schedule', config: {} })}
      columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)

    fireEvent.change(screen.getByPlaceholderText('Widget title'), { target: { value: 'Renamed Schedule' } })
    act(() => { vi.advanceTimersByTime(700) })

    expect(onUpdate).toHaveBeenCalled()
    const [config, title] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(title).toBe('Renamed Schedule')
    expect('axis_line' in config).toBe(false)
    expect('tick_line' in config).toBe(false)
  })

  it('re-seeds formatting fields from config when switching to a different widget', () => {
    const w1 = widget({ id: 30, config: { dimension: 'region', x_axis_label: 'Region' } })
    const w2 = widget({ id: 31, config: { dimension: 'region', x_axis_label: 'Country' } })
    const { rerender } = render(<CrossFilterProvider><WidgetConfigPanel widget={w1} columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    openFormatting()
    expect(screen.getByLabelText('X axis label')).toHaveValue('Region')

    // ExpandableGroup's own open/closed state lives on this same mounted component and
    // is untouched by a widget switch, so it stays open across the rerender below —
    // openFormatting() must not be called again here, or it would toggle it shut.
    rerender(<CrossFilterProvider><WidgetConfigPanel widget={w2} columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    expect(screen.getByLabelText('X axis label')).toHaveValue('Country')
  })
})

describe('WidgetConfigPanel table options (Task 9)', () => {
  function openFormatting() {
    fireEvent.click(screen.getByRole('button', { name: /Formatting/i }))
  }

  it('offers table option controls for a crosstab widget', () => {
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'crosstab', config: { dimension: 'region', dimension2: 'segment' } })}
      columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    openFormatting()
    expect(screen.getByLabelText('Show totals')).toBeInTheDocument()
    expect(screen.getByLabelText('Show row subtotals')).toBeInTheDocument()
    expect(screen.getByLabelText('Row numbers')).toBeInTheDocument()
    expect(screen.getByLabelText('Row lines')).toBeInTheDocument()
    expect(screen.getByLabelText('Banded rows')).toBeInTheDocument()
    expect(screen.getByLabelText('Condensed')).toBeInTheDocument()
  })

  it('does not offer Show row subtotals where no subtotal column can exist', () => {
    // The `__total__` row-subtotal column is added only on shape_series's pivoted
    // crosstab branch, which needs a SECOND dimension. On a plain table, or a crosstab
    // whose Column Pivot is empty, the control had no consumer at all — and it shipped
    // PRE-CHECKED, so it asserted a column that did not exist in any configuration.
    const { unmount } = render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'table', config: { dimension: 'region' } })}
      columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    openFormatting()
    expect(screen.getByLabelText('Show totals')).toBeInTheDocument()
    expect(screen.queryByLabelText('Show row subtotals')).not.toBeInTheDocument()
    unmount()

    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'crosstab', config: { dimension: 'region' } })}
      columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    openFormatting()
    expect(screen.queryByLabelText('Show row subtotals')).not.toBeInTheDocument()
  })

  it('keeps a saved show_subtotals value through a config that cannot show the control', () => {
    // Hiding the control must not silently rewrite the widget: an explicit false saved
    // earlier survives, and no key is invented for a widget that never had one.
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'crosstab', title: 'Sales', config: { dimension: 'region', show_subtotals: false } })}
      columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)

    fireEvent.change(screen.getByPlaceholderText('Widget title'), { target: { value: 'Renamed' } })
    act(() => { vi.advanceTimersByTime(700) })

    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.show_subtotals).toBe(false)
  })

  it('does not offer table option controls for a bar chart', () => {
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget()} columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    openFormatting()
    expect(screen.queryByLabelText('Show totals')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Show row subtotals')).not.toBeInTheDocument()
  })

  it('leaves show_subtotals and show_totals absent from a saved crosstab config that was never touched', () => {
    // The hazard this test exists for: widget_data.py defaults show_subtotals to True
    // (config.get("show_subtotals", True)). If an untouched "Show row subtotals"
    // control wrote `false` on every debounced save, every existing crosstab would
    // silently lose its subtotal column the moment an author edited anything else
    // (e.g. renamed the widget) without ever visiting the Formatting group.
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'crosstab', title: 'Sales by region', config: { dimension: 'region', dimension2: 'segment' } })}
      columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)

    fireEvent.change(screen.getByPlaceholderText('Widget title'), { target: { value: 'Renamed crosstab' } })
    act(() => { vi.advanceTimersByTime(700) })

    expect(onUpdate).toHaveBeenCalled()
    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect('show_subtotals' in config).toBe(false)
    expect('show_totals' in config).toBe(false)
    expect('table_row_numbers' in config).toBe(false)
    expect('table_row_lines' in config).toBe(false)
    expect('table_banding' in config).toBe(false)
    expect('table_condensed' in config).toBe(false)
  })

  it('writes show_totals once its own checkbox is touched, without inventing show_subtotals', () => {
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'crosstab', config: { dimension: 'region', dimension2: 'segment' } })}
      columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)
    openFormatting()

    fireEvent.click(screen.getByLabelText('Show totals'))
    act(() => { vi.advanceTimersByTime(700) })

    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.show_totals).toBe(true)
    expect('show_subtotals' in config).toBe(false)
  })

  it('writes show_subtotals: false once the Show row subtotals control is explicitly unchecked', () => {
    // Show row subtotals displays checked by default (matching the backend's True
    // default) purely as a starting look, but clicking it to uncheck must actually
    // persist the explicit false -- that is the one case where writing false is correct.
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'crosstab', config: { dimension: 'region', dimension2: 'segment' } })}
      columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)
    openFormatting()

    fireEvent.click(screen.getByLabelText('Show row subtotals'))
    act(() => { vi.advanceTimersByTime(700) })

    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.show_subtotals).toBe(false)
  })

  it('leaves totals placement and basis absent until they are touched', () => {
    // Absent means 'after' / 'all' -- how every table saved before these controls
    // existed renders. An untouched control that wrote a value on the next save
    // would move a saved table's totals row with no one asking.
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'crosstab', config: { dimension: 'region', dimension2: 'segment', show_totals: true } })}
      columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)
    openFormatting()

    expect(screen.getByLabelText('Totals placement')).toHaveValue('after')
    expect(screen.getByLabelText('Total covers')).toHaveValue('all')
    fireEvent.change(screen.getByPlaceholderText('Widget title'), { target: { value: 'Renamed' } })
    act(() => { vi.advanceTimersByTime(700) })

    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect('totals_position' in config).toBe(false)
    expect('totals_scope' in config).toBe(false)
  })

  it('writes totals placement and basis once they are chosen', () => {
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'table', config: { dimension: 'region', show_totals: true } })}
      columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)
    openFormatting()

    fireEvent.change(screen.getByLabelText('Totals placement'), { target: { value: 'before' } })
    fireEvent.change(screen.getByLabelText('Total covers'), { target: { value: 'shown' } })
    act(() => { vi.advanceTimersByTime(700) })

    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.totals_position).toBe('before')
    expect(config.totals_scope).toBe('shown')
  })

  it('offers no totals placement or basis while there is nothing for them to act on', () => {
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'table', config: { dimension: 'region' } })}
      columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    openFormatting()

    expect(screen.queryByLabelText('Totals placement')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Total covers')).not.toBeInTheDocument()
  })

  it('writes row numbers, row lines, banding and condensed once their checkboxes are touched', () => {
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'table', config: {} })}
      columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)
    openFormatting()

    fireEvent.click(screen.getByLabelText('Row numbers'))
    fireEvent.click(screen.getByLabelText('Row lines'))
    fireEvent.click(screen.getByLabelText('Banded rows'))
    fireEvent.click(screen.getByLabelText('Condensed'))
    act(() => { vi.advanceTimersByTime(700) })

    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.table_row_numbers).toBe(true)
    expect(config.table_row_lines).toBe(true)
    expect(config.table_banding).toBe(true)
    expect(config.table_condensed).toBe(true)
  })
})

describe('WidgetConfigPanel appearance options (Task 9)', () => {
  function openAppearance() {
    fireEvent.click(screen.getByRole('button', { name: /Appearance/i }))
  }

  it('offers an Appearance group for a KPI, which has no chart formatting capabilities at all', () => {
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'kpi', config: { measure: 'region' } })} columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    expect(screen.getByRole('button', { name: /Appearance/i })).toBeInTheDocument()
  })

  it('offers an Appearance group for a text widget, which has no Fields/Data sections at all', () => {
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'text', config: { content: 'hi' } })} columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    openAppearance()
    expect(screen.getByLabelText('Background')).toBeInTheDocument()
    expect(screen.getByLabelText('Widget description (screen readers)')).toBeInTheDocument()
  })

  it('labels the image widget alt attribute and the widget-wide accessible description distinctly', () => {
    // Finding from review: both controls write different config keys (`alt` -- the
    // <img> element's own attribute -- vs `alt_text` -- the aria-label on the whole
    // widget's role="figure" container, per WidgetRenderer.tsx:252) and both are
    // visible at once on an image widget. Identical labels would make it impossible
    // for an author to tell which field does what; getAllByLabelText('Alt text')
    // returning 2 was exactly that ambiguity.
    render(<CrossFilterProvider><WidgetConfigPanel widget={imageWidget()} columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    openAppearance()
    expect(screen.getByLabelText('Image alt text')).toBeInTheDocument()
    expect(screen.getByLabelText('Widget description (screen readers)')).toBeInTheDocument()
    expect(screen.queryAllByLabelText('Alt text')).toHaveLength(0)
  })

  it('collapses the Appearance group by default, like the other occasional sections', () => {
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget()} columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    expect(screen.getByRole('button', { name: /Appearance/i })).toHaveAttribute('aria-expanded', 'false')
  })

  it('leaves every appearance key absent from a saved config that was never touched', () => {
    // Runs under plain jsdom (no getComputedStyle mock), which resolves the
    // --surface/--border custom properties to '' -- this exercises the
    // readCssVarColor fallback path directly.
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget({ title: 'Sales' })} columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)

    fireEvent.change(screen.getByPlaceholderText('Widget title'), { target: { value: 'Renamed' } })
    act(() => { vi.advanceTimersByTime(700) })

    expect(onUpdate).toHaveBeenCalled()
    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    for (const key of ['widget_background', 'widget_border_color', 'widget_border_width', 'widget_radius', 'widget_padding', 'alt_text']) {
      expect(key in config).toBe(false)
    }
  })

  it('shows the swatches at the theme\'s real --surface/--border colours, without writing them until touched', () => {
    // Finding from review: the swatches previously showed a hardcoded dark-theme hex
    // guess (#111827/#94a3b8) that didn't match WidgetRenderer.tsx's actual untouched
    // defaults (var(--surface)/var(--border)) and would be flat wrong under a light
    // theme. Mocking getComputedStyle simulates a real browser resolving those custom
    // properties (jsdom itself resolves them to '', which is the fallback-path case
    // covered by the untouched-key-absence test below).
    const original = window.getComputedStyle.bind(window)
    const spy = vi.spyOn(window, 'getComputedStyle').mockImplementation((el, pseudo) => {
      const cs = original(el, pseudo)
      return { ...cs, getPropertyValue: (prop: string) => {
        if (prop === '--surface') return '#181c27'
        if (prop === '--border') return '#2a3045'
        return cs.getPropertyValue(prop)
      } } as CSSStyleDeclaration
    })

    try {
      render(<CrossFilterProvider><WidgetConfigPanel widget={widget()} columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
      fireEvent.click(screen.getByRole('button', { name: /Appearance/i }))
      expect(screen.getByLabelText('Background')).toHaveValue('#181c27')
      expect(screen.getByLabelText('Border colour')).toHaveValue('#2a3045')
    } finally {
      spy.mockRestore()
    }
  })

  it('leaves every appearance key absent from a saved config that was never touched, even when getComputedStyle resolves a real theme colour', () => {
    // The absence guarantee must hold in both the jsdom fallback-empty-string path AND
    // the "getComputedStyle actually resolved a colour" path exercised above -- the
    // swatch's displayed value must never leak into what gets saved either way.
    const original = window.getComputedStyle.bind(window)
    const spy = vi.spyOn(window, 'getComputedStyle').mockImplementation((el, pseudo) => {
      const cs = original(el, pseudo)
      return { ...cs, getPropertyValue: (prop: string) => {
        if (prop === '--surface') return '#181c27'
        if (prop === '--border') return '#2a3045'
        return cs.getPropertyValue(prop)
      } } as CSSStyleDeclaration
    })

    const onUpdate = vi.fn()
    try {
      render(<CrossFilterProvider><WidgetConfigPanel widget={widget({ title: 'Sales' })} columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)

      fireEvent.change(screen.getByPlaceholderText('Widget title'), { target: { value: 'Renamed' } })
      act(() => { vi.advanceTimersByTime(700) })

      expect(onUpdate).toHaveBeenCalled()
      const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
      for (const key of ['widget_background', 'widget_border_color', 'widget_border_width', 'widget_radius', 'widget_padding', 'alt_text']) {
        expect(key in config).toBe(false)
      }
    } finally {
      spy.mockRestore()
    }
  })

  it('writes background, border colour/width, corner radius, padding and alt text once touched', () => {
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget()} columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)
    openAppearance()

    fireEvent.change(screen.getByLabelText('Background'), { target: { value: '#112233' } })
    fireEvent.change(screen.getByLabelText('Border colour'), { target: { value: '#445566' } })
    fireEvent.change(screen.getByLabelText('Border width'), { target: { value: '2' } })
    fireEvent.change(screen.getByLabelText('Corner radius'), { target: { value: '8' } })
    fireEvent.change(screen.getByLabelText('Padding'), { target: { value: '12' } })
    fireEvent.change(screen.getByLabelText('Widget description (screen readers)'), { target: { value: 'A chart' } })
    act(() => { vi.advanceTimersByTime(700) })

    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.widget_background).toBe('#112233')
    expect(config.widget_border_color).toBe('#445566')
    expect(config.widget_border_width).toBe(2)
    expect(config.widget_radius).toBe(8)
    expect(config.widget_padding).toBe(12)
    expect(config.alt_text).toBe('A chart')
  })
})

function hNode(overrides: Partial<HierarchyNode>): HierarchyNode {
  return { id: 0, dataset_id: 10, parent_id: null, name: '', node_type: 'dimension', position: 0, created_at: '2026-01-01', ...overrides }
}

describe('WidgetConfigPanel hierarchy binding', () => {
  const hierarchy: HierarchyNode[] = [
    hNode({ id: 1, name: 'Dates', node_type: 'folder' }),
    hNode({ id: 2, name: 'Order Date', node_type: 'date', parent_id: 1, column_name: 'order_date' }),
    hNode({ id: 3, name: 'Year', node_type: 'date', parent_id: 2, column_name: 'order_date', format: 'year' }),
  ]

  it('writes hierarchyNodeId and dimension_granularity when a hierarchy option is picked', () => {
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget()} columns={columns} onUpdate={onUpdate}
      hierarchy={hierarchy} /></CrossFilterProvider>)

    fireEvent.change(screen.getByLabelText('Dimension (Group / X-axis)'), { target: { value: 'h:3' } })
    act(() => { vi.advanceTimersByTime(700) })

    expect(onUpdate).toHaveBeenCalled()
    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.dimension).toBe('order_date')
    expect(config.dimension_granularity).toBe('year')
    expect(config.hierarchyNodeId).toBe(3)
  })

  it('shows an Edit hierarchy link only once a hierarchy node is bound', () => {
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget({ config: { dimension: 'region' } })} columns={columns} onUpdate={vi.fn()}
      hierarchy={hierarchy} /></CrossFilterProvider>)
    expect(screen.queryByRole('button', { name: /Edit hierarchy/i })).not.toBeInTheDocument()
  })

  it('clears hierarchyNodeId when a plain column is picked instead', () => {
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget({ config: { hierarchyNodeId: 3, dimension: 'order_date', dimension_granularity: 'year' } })}
      columns={columns} onUpdate={onUpdate} hierarchy={hierarchy} /></CrossFilterProvider>)

    fireEvent.change(screen.getByLabelText('Dimension (Group / X-axis)'), { target: { value: 'region' } })
    act(() => { vi.advanceTimersByTime(700) })

    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.hierarchyNodeId).toBeUndefined()
    expect(config.dimension).toBe('region')
  })
})


describe('WidgetConfigPanel label associations', () => {
  const renderPanel = () =>
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget()} columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)

  it('associates every sibling-label field with its control, so it has an accessible name', () => {
    // The `fld` helper renders <label> as a SIBLING of the control. Without htmlFor the
    // control has no accessible name at all -- a screen reader announces a bare
    // combobox/spinbutton, and getByLabelText cannot find it. This was live in the app:
    // driving the real builder, "Row limit" was unreachable by its visible label.
    renderPanel()
    fireEvent.click(screen.getByRole('button', { name: /Sort & limit/i }))

    // getByLabelText resolves through htmlFor/id, so it fails outright if the
    // association is missing -- which is the whole point of asserting it this way
    // rather than asserting the label text is present.
    expect(screen.getByLabelText(/Row limit/i)).toHaveAttribute('type', 'number')

    // The hand-written labels are wired up too now. Five others in this panel wrap
    // their input instead (<label><span>Fill</span><input/></label>), which is already
    // a valid association and needs no htmlFor.
    expect(screen.getByLabelText(/Sort order/i).tagName).toBe('SELECT')
    expect(screen.getByLabelText(/^Sort by$/i).tagName).toBe('SELECT')
  })

  it('labels the visible-columns checkbox list as a group, not with a stray <label>', () => {
    // It labels a LIST of checkboxes, not one control. A <label> there points at
    // nothing; a labelled group is what conveys the relationship.
    // Rendered for table-shaped widgets, which is where a column picker applies.
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget({ widget_type: 'table' })} columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    expect(screen.getByRole('group', { name: /Visible columns/i })).toBeInTheDocument()
  })

  it('does not rename a control that already carries its own id', () => {
    // Some fields need a specific id for other reasons; the helper must not clobber it.
    // Needs a table widget -- table options are gated behind the tableOptions capability.
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget({ widget_type: 'table' })} columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    fireEvent.click(screen.getByRole('button', { name: /Formatting/i }))
    expect(screen.getByLabelText('Show totals')).toHaveAttribute('id', 'format-show-totals')
  })
})

describe('auto-reload authoring', () => {
  it('writes auto_reload_seconds into config when set to a valid interval', () => {
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget()} columns={columns} onUpdate={onUpdate}
      pages={[page(100, 'Page 1', 'normal')]} /></CrossFilterProvider>)
    fireEvent.click(screen.getByRole('button', { name: /Sort & limit/i }))
    fireEvent.change(screen.getByLabelText('Auto-reload seconds'), { target: { value: '30' } })
    act(() => { vi.advanceTimersByTime(700) })
    expect(onUpdate).toHaveBeenCalled()
    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.auto_reload_seconds).toBe(30)
  })

  it('omits the key when below the 5s floor', () => {
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget()} columns={columns} onUpdate={onUpdate}
      pages={[page(100, 'Page 1', 'normal')]} /></CrossFilterProvider>)
    fireEvent.click(screen.getByRole('button', { name: /Sort & limit/i }))
    fireEvent.change(screen.getByLabelText('Auto-reload seconds'), { target: { value: '2' } })
    act(() => { vi.advanceTimersByTime(700) })
    expect(onUpdate).toHaveBeenCalled()
    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.auto_reload_seconds).toBeUndefined()
  })
})

describe('measure dropdown excludes id-like numeric columns', () => {
  const colsWithId: DatasetColumn[] = [
    { id: 1, name: 'region', dtype: 'text', missing_pct: 0, stats: {} },
    { id: 2, name: 'amount', dtype: 'numeric', missing_pct: 0, stats: {} },
    { id: 3, name: 'state_id', dtype: 'numeric', missing_pct: 0, stats: {} },
  ]

  it('does not offer state_id (id-like) as a measure on a fresh widget', () => {
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'bar', config: { dimension: 'region' } })}
      columns={colsWithId} onUpdate={vi.fn()} /></CrossFilterProvider>)
    const options = Array.from((screen.getByLabelText('Measure (numeric column)') as HTMLSelectElement).options)
      .map(o => o.value)
    expect(options).toContain('amount')
    expect(options).not.toContain('state_id')
  })

  it('keeps a currently-selected id-like measure in the options, suffixed "(id)"', () => {
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'bar', config: { dimension: 'region', measure: 'state_id' } })}
      columns={colsWithId} onUpdate={vi.fn()} /></CrossFilterProvider>)
    const select = screen.getByLabelText('Measure (numeric column)') as HTMLSelectElement
    const options = Array.from(select.options).map(o => o.value)
    expect(options).toContain('state_id')
    expect(select.value).toBe('state_id')
    const idOption = Array.from(select.options).find(o => o.value === 'state_id')!
    expect(idOption.label).toBe('state_id (id)')
  })

  it('offers a calculated column (fx) as a measure', () => {
    // Calculated columns were injected with dtype 'calculated', and the
    // measure picker only listed dtype 'numeric', so a formula visible on
    // the dataset Data tab could not be bound to a KPI.
    const cols: DatasetColumn[] = [
      { id: 1, name: 'region', dtype: 'text', missing_pct: 0, stats: {} },
      { id: 2, name: 'employee_count', dtype: 'numeric', missing_pct: 0, stats: {} },
      { id: 3, name: 'all_employee_count', dtype: 'calculated', missing_pct: 0, stats: {} },
    ]
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'kpi', config: {} })}
      columns={cols} onUpdate={vi.fn()} /></CrossFilterProvider>)
    const options = Array.from((screen.getByLabelText('Measure (numeric column)') as HTMLSelectElement).options)
      .map(o => o.value)
    expect(options).toContain('all_employee_count')
    expect(options).toContain('employee_count')
  })
})

describe('multi-column sort authoring', () => {
  const tableCols: DatasetColumn[] = [
    { id: 1, name: 'region', dtype: 'text', missing_pct: 0, stats: {} },
    { id: 2, name: 'sales', dtype: 'numeric', missing_pct: 0, stats: {} },
  ]

  it('writes an ordered sort_keys list for a table widget', () => {
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'table', config: {} })} columns={tableCols} onUpdate={onUpdate}
      pages={[page(100, 'Page 1', 'normal')]} /></CrossFilterProvider>)
    fireEvent.click(screen.getByRole('button', { name: /Sort & limit/i }))

    fireEvent.click(screen.getByRole('button', { name: '+ Add sort column' }))
    fireEvent.click(screen.getByRole('button', { name: '+ Add sort column' }))
    fireEvent.change(screen.getByLabelText('Sort key 1 column'), { target: { value: 'region' } })
    fireEvent.change(screen.getByLabelText('Sort key 2 column'), { target: { value: 'sales' } })
    fireEvent.change(screen.getByLabelText('Sort key 2 direction'), { target: { value: 'desc' } })
    act(() => { vi.advanceTimersByTime(700) })

    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.sort_keys).toEqual([
      { col: 'region', dir: 'asc' },
      { col: 'sales', dir: 'desc' },
    ])
  })

  it('is not offered on a chart widget, whose shaper has no ungrouped table branch', () => {
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'bar' })} columns={tableCols} onUpdate={vi.fn()}
      pages={[page(100, 'Page 1', 'normal')]} /></CrossFilterProvider>)
    fireEvent.click(screen.getByRole('button', { name: /Sort & limit/i }))
    expect(screen.queryByText('Multi-column sort (priority order)')).not.toBeInTheDocument()
  })
})

describe('crosstab row-sparkline authoring', () => {
  const tableCols: DatasetColumn[] = [
    { id: 1, name: 'region', dtype: 'text', missing_pct: 0, stats: {} },
    { id: 2, name: 'sales', dtype: 'numeric', missing_pct: 0, stats: {} },
  ]

  it('writes sparkline into a crosstab config when toggled on', () => {
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'crosstab', config: {} })} columns={tableCols} onUpdate={onUpdate}
      pages={[page(100, 'Page 1', 'normal')]} /></CrossFilterProvider>)
    fireEvent.click(screen.getByRole('button', { name: /Formatting/i }))
    fireEvent.click(screen.getByLabelText('Row trend sparkline'))
    act(() => { vi.advanceTimersByTime(700) })
    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.sparkline).toBe(true)
  })

  it('is not offered on a raw table, whose columns are not a per-row series', () => {
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'table', config: {} })} columns={tableCols} onUpdate={vi.fn()}
      pages={[page(100, 'Page 1', 'normal')]} /></CrossFilterProvider>)
    fireEvent.click(screen.getByRole('button', { name: /Formatting/i }))
    expect(screen.getByLabelText('Condensed')).toBeInTheDocument()  // table options ARE shown
    expect(screen.queryByText('Row trend sparkline')).not.toBeInTheDocument()
  })
})

describe('element skin authoring', () => {
  it('writes widget_skin into config when a skin is chosen', () => {
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'bar', config: { dimension: 'region' } })} columns={columns} onUpdate={onUpdate}
      pages={[page(100, 'Page 1', 'normal')]} /></CrossFilterProvider>)
    fireEvent.click(screen.getByRole('button', { name: /Appearance/i }))
    fireEvent.change(screen.getByLabelText('Skin'), { target: { value: 'raised' } })
    act(() => { vi.advanceTimersByTime(700) })
    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.widget_skin).toBe('raised')
  })
})

describe('the boundary set a region map draws on', () => {
  /**
   * The seam: `BoundarySetPicker` is tested next door and that proves nothing
   * about whether the panel ever renders it, or whether the choice survives
   * into `config`. A picker whose value never reaches the widget is the same
   * kind of defect as an endpoint with no caller.
   */
  it('offers the picker on a choropleth', () => {
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'map_choropleth' })}
      columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    expect(screen.getByLabelText(/^boundaries$/i)).toBeInTheDocument()
  })

  it('does not offer it on a chart that draws no regions', () => {
    // A bar chart has no shapes to swap, and a point map uses the world purely
    // as a backdrop — replacing that with governorates would hide every mark
    // outside them.
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget({ widget_type: 'bar' })}
      columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    expect(screen.queryByLabelText(/^boundaries$/i)).not.toBeInTheDocument()
  })

  beforeEach(() => {
    // The option must EXIST before `fireEvent.change` can select it — a select
    // whose options come from a fetch silently selects nothing otherwise, which
    // has cost this repo an afternoon before.
    vi.mocked(boundarySetsApi.list).mockResolvedValue([{
      id: 7, name: 'Egypt governorates', feature_count: 27,
      key_properties: ['name'], sample_names: ['Cairo'],
      created_by: 1, created_at: null,
    }] as never)
  })

  it('writes boundary_set_id into config when one is chosen', async () => {
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'map_choropleth' })}
      columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)

    // The list arrives on a real microtask; the panel's debounce is faked.
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    fireEvent.change(screen.getByLabelText(/^boundaries$/i), { target: { value: '7' } })
    await act(async () => { await vi.advanceTimersByTimeAsync(700) })

    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.boundary_set_id).toBe(7)
  })

  it('writes no key at all for the built-in countries', () => {
    /**
     * "Unset" and "countries" must not be two states that look different in
     * the stored config and identical on screen — a widget saved before
     * boundary sets existed has no key, and choosing Countries has to leave it
     * that way.
     */
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'map_choropleth', config: { boundary_set_id: 7 } })}
      columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)

    fireEvent.change(screen.getByLabelText(/^boundaries$/i), { target: { value: '' } })
    act(() => { vi.advanceTimersByTime(700) })

    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config).not.toHaveProperty('boundary_set_id')
  })

  it('shows the set a widget was saved with', () => {
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'map_choropleth', config: { boundary_set_id: 7 } })}
      columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    expect((screen.getByLabelText(/^boundaries$/i) as HTMLSelectElement).value)
      .toBe('7')
  })
})

describe('the target a forecast is asked about', () => {
  /**
   * The seam. `forecast_goal` is unit-tested on the backend and the caption is
   * tested in the renderer — neither says whether anything can ever SET a
   * target. Without this input the whole feature is unreachable, which is the
   * failure this codebase has now recorded six times.
   */
  it('offers a target on a forecast widget', () => {
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'forecast' })}
      columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    expect(screen.getByLabelText(/reach target/i)).toBeInTheDocument()
  })

  it('does not offer one on a chart that projects nothing', () => {
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget({ widget_type: 'bar' })}
      columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    expect(screen.queryByLabelText(/reach target/i)).not.toBeInTheDocument()
  })

  it('writes it as a number', () => {
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'forecast' })}
      columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)

    fireEvent.change(screen.getByLabelText(/reach target/i), { target: { value: '500000' } })
    act(() => { vi.advanceTimersByTime(700) })

    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.forecast_target).toBe(500000)
  })

  it('writes no key when the target is cleared', () => {
    // An absent key is "no question asked" — the shaper then does no extra work
    // and attaches no caption, which is what every forecast has always done.
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'forecast', config: { forecast_target: 500000 } })}
      columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)

    fireEvent.change(screen.getByLabelText(/reach target/i), { target: { value: '' } })
    act(() => { vi.advanceTimersByTime(700) })

    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config).not.toHaveProperty('forecast_target')
  })

  it('shows the target a widget was saved with', () => {
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'forecast', config: { forecast_target: 500000 } })}
      columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    expect((screen.getByLabelText(/reach target/i) as HTMLInputElement).value)
      .toBe('500000')
  })
})

describe('which centrality drives node size', () => {
  /**
   * `shape_network` has always computed degree, closeness, betweenness and
   * reach per node, and `NetworkGraphRenderer` has always read
   * `cfg.centrality_metric` to decide which one sizes the nodes. Nothing ever
   * SET it, so every network in the product has been a degree map and the other
   * three were computed and thrown away — the seventh time in this codebase
   * that a finished capability shipped with no control.
   */
  it('offers the choice on a network widget', () => {
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'network' })}
      columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    const select = screen.getByLabelText(/node size/i) as HTMLSelectElement
    expect(Array.from(select.options).map(o => o.value))
      .toEqual(['degree', 'closeness', 'betweenness', 'reach'])
  })

  it('does not offer it on a chart with no nodes', () => {
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget({ widget_type: 'bar' })}
      columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    expect(screen.queryByLabelText(/node size/i)).not.toBeInTheDocument()
  })

  it('writes the chosen metric', () => {
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'network' })}
      columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)

    fireEvent.change(screen.getByLabelText(/node size/i), { target: { value: 'betweenness' } })
    act(() => { vi.advanceTimersByTime(700) })

    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.centrality_metric).toBe('betweenness')
  })

  it('writes no key for the default', () => {
    // Degree is what the renderer falls back to, so an explicit "degree" and an
    // absent key must not be two ways of storing one state.
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'network', config: { centrality_metric: 'reach' } })}
      columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)

    fireEvent.change(screen.getByLabelText(/node size/i), { target: { value: 'degree' } })
    act(() => { vi.advanceTimersByTime(700) })

    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config).not.toHaveProperty('centrality_metric')
  })

  it('shows the metric a widget was saved with', () => {
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'network', config: { centrality_metric: 'betweenness' } })}
      columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    expect((screen.getByLabelText(/node size/i) as HTMLSelectElement).value)
      .toBe('betweenness')
  })
})

describe('the precision container', () => {
  /**
   * Overlapping widgets over a background image. The renderer already placed
   * children absolutely, so what the config has to add is the mode, the
   * background to position over, and a stacking order — without which "bring to
   * front" is whatever the sort happened to do.
   */
  const containerWidget = (mode: string) => ({
    id: 20, page_id: 100, widget_type: 'container', title: 'Floorplan',
    config: { container_mode: mode }, layout: { x: 0, y: 0, w: 6, h: 6 },
    created_at: '2026-01-01',
  } as never)

  const pageWithContainer = (mode: string): ReportPage[] => ([{
    id: 100, report_id: 1, name: 'P', page_type: 'normal', position: 0,
    created_at: '2026-01-01', page_size: '16:9',
    widgets: [containerWidget(mode), widget({ id: 1 })],
  } as never])

  it('offers precision as a container style', () => {
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'container' })}
      columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    const select = screen.getByLabelText(/container style/i) as HTMLSelectElement
    expect(Array.from(select.options).map(o => o.value)).toContain('precision')
  })

  it('asks for a background only once precision is chosen', () => {
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'container' })}
      columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    expect(screen.queryByLabelText(/background image/i)).not.toBeInTheDocument()

    fireEvent.change(screen.getByLabelText(/container style/i),
      { target: { value: 'precision' } })
    expect(screen.getByLabelText(/background image/i)).toBeInTheDocument()
  })

  it('writes the background', () => {
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'container', config: { container_mode: 'precision' } })}
      columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)

    fireEvent.change(screen.getByLabelText(/background image/i),
      { target: { value: 'https://x.invalid/plan.png' } })
    act(() => { vi.advanceTimersByTime(700) })

    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.background_url).toBe('https://x.invalid/plan.png')
  })

  it('offers a layer only for a widget inside a precision container', () => {
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ id: 1, config: { dimension: 'region', container_id: 20 } })}
      columns={columns} pages={pageWithContainer('precision')}
      onUpdate={vi.fn()} /></CrossFilterProvider>)
    expect(screen.getByLabelText(/^layer$/i)).toBeInTheDocument()
  })

  it('offers no layer inside an ordinary container', () => {
    // Stacking means nothing where widgets cannot overlap, and a setting that
    // silently does nothing is worse than its absence.
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ id: 1, config: { dimension: 'region', container_id: 20 } })}
      columns={columns} pages={pageWithContainer('tabs')}
      onUpdate={vi.fn()} /></CrossFilterProvider>)
    expect(screen.queryByLabelText(/^layer$/i)).not.toBeInTheDocument()
  })
})

describe('container settings are not axis formatting', () => {
  /**
   * They were persisted inside `caps.includes('grid')`, and `container` has NO
   * formatting capabilities at all — so the container-style select could be
   * changed and never saved, and a widget with no axes (pie, donut, KPI) could
   * be assigned to a container and never land in one. Found by adding the
   * precision option and watching its background fail to persist.
   */
  it('saves the container style at all', () => {
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'container' })}
      columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)

    fireEvent.change(screen.getByLabelText(/container style/i),
      { target: { value: 'tabs' } })
    act(() => { vi.advanceTimersByTime(700) })

    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.container_mode).toBe('tabs')
  })

  it('puts an axis-less widget into a container', () => {
    const onUpdate = vi.fn()
    const pages = [{
      id: 100, report_id: 1, name: 'P', page_type: 'normal', position: 0,
      created_at: '2026-01-01', page_size: '16:9',
      widgets: [{ id: 20, page_id: 100, widget_type: 'container', title: 'Box',
                  config: {}, layout: { x:0, y:0, w:6, h:6 },
                  created_at: '2026-01-01' },
                widget({ id: 1, widget_type: 'pie' })],
    }] as never as ReportPage[]

    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ id: 1, widget_type: 'pie', config: { dimension: 'region' } })}
      columns={columns} pages={pages} onUpdate={onUpdate} /></CrossFilterProvider>)

    fireEvent.change(screen.getByLabelText(/place inside container/i),
      { target: { value: '20' } })
    act(() => { vi.advanceTimersByTime(700) })

    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.container_id).toBe(20)
  })
})

describe('the script tile editor', () => {
  /**
   * The tile runs server-side Python (services/script_tile.py: a subprocess, a
   * scrubbed environment, a timeout, admin-only authoring). Without a place to
   * type the code it would be authorable only through the API — which is
   * precisely how several features in this codebase shipped with no caller.
   */
  const scriptWidget = (config: Record<string, unknown> = {}) =>
    widget({ widget_type: 'script', title: 'Backlog', config })

  it('offers a code box', () => {
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={scriptWidget()} columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    expect(screen.getByLabelText(/python/i)).toBeInTheDocument()
  })

  it('saves the code', () => {
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={scriptWidget()} columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)

    fireEvent.change(screen.getByLabelText(/python/i),
      { target: { value: "result = df.head()" } })
    act(() => { vi.advanceTimersByTime(700) })

    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.code).toBe('result = df.head()')
  })

  it('loads the code that was saved', () => {
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={scriptWidget({ code: 'result = df' })}
      columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    expect(screen.getByLabelText(/python/i)).toHaveValue('result = df')
  })

  it('states the contract and who may write one', () => {
    // Both halves matter: an author who does not know to set `result` gets an
    // error, and one who does not know this is admin-gated server code cannot
    // judge whether to write it at all.
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={scriptWidget()} columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    expect(screen.getByText(/result/)).toBeInTheDocument()
    expect(screen.getByText(/admin/i)).toBeInTheDocument()
  })

  it('shows no code box on an ordinary chart', () => {
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ config: { dimension: 'region' } })}
      columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    expect(screen.queryByLabelText(/python/i)).not.toBeInTheDocument()
  })
})

describe('the options a SAS-style page needs', () => {
  /**
   * Measured against four SAS pages: a dual-axis chart titling each axis
   * separately, a donut with its total in the hole, a legend headed by the
   * field its entries belong to, and objects floating on a page background with
   * no panel of their own. Every one of these renders already — these are the
   * controls that let an author reach them, without which they are four
   * features nobody can turn on.
   */
  it('titles the right axis of a dual-axis chart', () => {
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'dual_axis_bar',
        config: { dimension: 'month', measure: 'profit', measure2: 'orders' } })}
      columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)

    // Axis and legend options live in the collapsed Formatting group, which is
    // how an author reaches them too.
    fireEvent.click(screen.getByRole('button', { name: /Formatting/i }))
    fireEvent.change(screen.getByLabelText(/right axis label/i),
      { target: { value: 'Number of Orders' } })
    act(() => { vi.advanceTimersByTime(700) })
    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.y2_axis_label).toBe('Number of Orders')
  })

  it('offers no right-axis title where there is no right axis', () => {
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ config: { dimension: 'region' } })}
      columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    fireEvent.click(screen.getByRole('button', { name: /Formatting/i }))
    expect(screen.queryByLabelText(/right axis label/i)).not.toBeInTheDocument()
  })

  it('titles the legend', () => {
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ config: { dimension: 'region' } })}
      columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)

    fireEvent.click(screen.getByRole('button', { name: /Formatting/i }))
    fireEvent.change(screen.getByLabelText(/legend title/i),
      { target: { value: 'Customer Age Group' } })
    act(() => { vi.advanceTimersByTime(700) })
    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.legend_title).toBe('Customer Age Group')
  })

  it('puts the total in the middle of a donut', () => {
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'donut', config: { dimension: 'region' } })}
      columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)

    fireEvent.click(screen.getByLabelText(/total in the centre/i))
    act(() => { vi.advanceTimersByTime(700) })
    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.donut_total).toBe(true)
  })

  it('offers the donut total only on a donut', () => {
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ config: { dimension: 'region' } })}
      columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    expect(screen.queryByLabelText(/total in the centre/i)).not.toBeInTheDocument()
  })

  it('makes an object transparent so a page background shows through', () => {
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ config: { dimension: 'region' } })}
      columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)

    fireEvent.click(screen.getByLabelText(/transparent background/i))
    act(() => { vi.advanceTimersByTime(700) })
    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.transparent).toBe(true)
  })

  it('loads the settings a widget already carries', () => {
    render(<CrossFilterProvider><WidgetConfigPanel
      widget={widget({ widget_type: 'donut', config: { dimension: 'region',
        transparent: true, legend_title: 'Age', donut_total: true } })}
      columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    expect(screen.getByLabelText(/transparent background/i)).toBeChecked()
    fireEvent.click(screen.getByRole('button', { name: /Formatting/i }))
    expect(screen.getByLabelText(/legend title/i)).toHaveValue('Age')
    expect(screen.getByLabelText(/total in the centre/i)).toBeChecked()
  })
})

/**
 * A widget title longer than its box.
 *
 * Photographed on the running app: the Title field showed "Revenue - reach 400k
 * (already p" with no way to see the rest without selecting the text and
 * scrolling through it. The input cannot grow, so the full value belongs on the
 * element where a hover can reach it.
 */
describe('a long widget title', () => {
  it('is readable on hover', () => {
    const long = 'Revenue - reach 400k (already passed) and then some more words'
    render(
      <CrossFilterProvider>
        <WidgetConfigPanel
          widget={{ id: 1, page_id: 100, widget_type: 'bar', title: long, config: {},
            layout: { x: 0, y: 0, w: 6, h: 5 }, created_at: '2026-01-01' } as never}
          columns={[]} onUpdate={vi.fn()} />
      </CrossFilterProvider>,
    )
    expect(screen.getByLabelText(/^title$/i)).toHaveAttribute('title', long)
  })
})

describe('WidgetConfigPanel relative date filters (Phase 6.4)', () => {
  it('round-trips a saved relative filter and writes the edited spec', () => {
    const onUpdate = vi.fn()
    const w = widget({ config: { dimension: 'region', filters: [{ column: 'region', op: 'relative',
      value: { mode: 'last', unit: 'day', n: 30, anchor: 'data_max' } }] } })
    render(<CrossFilterProvider><WidgetConfigPanel widget={w} columns={columns} onUpdate={onUpdate} /></CrossFilterProvider>)
    fireEvent.click(screen.getByRole('button', { name: /^Filters$/i }))
    expect(screen.getByText('Last 30 days · from latest data')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Filter 1 period'), { target: { value: 'mtd' } })
    act(() => { vi.advanceTimersByTime(700) })
    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.filters).toEqual([{ column: 'region', op: 'relative',
      value: { mode: 'to_date', unit: 'month', anchor: 'data_max' } }])
  })

  it('switching the operator to relative date starts from the default window', () => {
    const w = widget({ config: { dimension: 'region', filters: [{ column: 'region', op: 'eq', value: 'East' }] } })
    render(<CrossFilterProvider><WidgetConfigPanel widget={w} columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    fireEvent.click(screen.getByRole('button', { name: /^Filters$/i }))
    fireEvent.change(screen.getByLabelText('Filter 1 operator'), { target: { value: 'relative' } })
    expect(screen.getByLabelText('Filter 1 counted from')).toHaveValue('data_max')
    expect(screen.queryByLabelText('Filter 1 value')).toBeNull()
  })
})

describe('WidgetConfigPanel lattice roles (Phase 6.2)', () => {
  it('writes lattice rows/columns for a cartesian chart', () => {
    const onUpdate = vi.fn()
    const cols: DatasetColumn[] = [...columns, { id: 2, name: 'channel', dtype: 'text', missing_pct: 0, stats: {} }]
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget()} columns={cols} onUpdate={onUpdate} /></CrossFilterProvider>)
    fireEvent.click(screen.getByRole('button', { name: /^Lattice \(small multiples\)$/i }))
    fireEvent.change(screen.getByLabelText('Lattice rows'), { target: { value: 'channel' } })
    act(() => { vi.advanceTimersByTime(700) })
    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.lattice_rows).toBe('channel')
    // the other role cannot pick the same column
    expect([...(screen.getByLabelText('Lattice columns') as HTMLSelectElement).options].map(o => o.value)).not.toContain('channel')
  })

  it('is not offered on a pie', () => {
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget({ widget_type: 'pie' })} columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    expect(screen.queryByRole('button', { name: /^Lattice/i })).toBeNull()
  })
})

describe('WidgetConfigPanel animation role (Phase 6.3)', () => {
  it('writes animate_by and a step for a date field', () => {
    const onUpdate = vi.fn()
    const cols: DatasetColumn[] = [...columns, { id: 3, name: 'order_date', dtype: 'datetime', missing_pct: 0, stats: {} }]
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget()} columns={cols} onUpdate={onUpdate} /></CrossFilterProvider>)
    fireEvent.click(screen.getByRole('button', { name: /^Animation \(play through\)$/i }))
    fireEvent.change(screen.getByLabelText('Animate by'), { target: { value: 'order_date' } })
    fireEvent.change(screen.getByLabelText('Animation step'), { target: { value: 'month' } })
    act(() => { vi.advanceTimersByTime(700) })
    const [config] = onUpdate.mock.calls[onUpdate.mock.calls.length - 1]
    expect(config.animate_by).toBe('order_date')
    expect(config.animate_granularity).toBe('month')
  })
})

describe('WidgetConfigPanel accessibility', () => {
  it('has no structural accessibility violations', async () => {
    // axe schedules its own work on timers; this file fakes them for every test.
    vi.useRealTimers()
    const { container } = render(<CrossFilterProvider><WidgetConfigPanel widget={widget()} columns={columns} onUpdate={vi.fn()} /></CrossFilterProvider>)
    expect(await axeViolations(container)).toEqual([])
  }, 30000)   // the panel is large; axe walks all of it
})
