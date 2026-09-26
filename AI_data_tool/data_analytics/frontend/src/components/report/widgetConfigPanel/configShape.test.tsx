import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import WidgetConfigPanel from '../WidgetConfigPanel'
import { CrossFilterProvider } from '../CrossFilterContext'
import type { Widget, ReportPage } from '../../../types/report'
import type { DatasetColumn } from '../../../services/api'
import { FLAT_ROLE_KEYS, PANEL_KEYS, SETTING_VOCABULARIES, keepUnmanaged, migrateWidgetConfig, panelManagedKeys } from './configShape'
import panelSource from '../WidgetConfigPanel.tsx?raw'
import modelSource from '../ModelSettings.tsx?raw'
import migrations from './widgetConfigMigrations.json'

/**
 * E03: a panel edit keeps what the panel does not manage, legacy config
 * shapes open as what they are, and "Percentage %" is offered where it is
 * computed. See configShape.ts for why each matters.
 */

describe('legacy config shapes migrate (the cases the server is pinned to)', () => {
  for (const c of (migrations as { cases: { name: string; in: Record<string, unknown>; out: Record<string, unknown> }[] }).cases) {
    it(c.name, () => {
      const before = JSON.parse(JSON.stringify(c.in))
      expect(migrateWidgetConfig(c.in)).toEqual(c.out)
      expect(c.in).toEqual(before)                       // a copy; the input is untouched
      expect(migrateWidgetConfig(c.out)).toEqual(c.out)  // idempotent
    })
  }
})

describe('the keys the panel manages', () => {
  /** The keys the save effect writes, read from its source: `config.x =`,
   *  `config = { ... }` and `{ key: ... }` spreads inside it. Role keys are
   *  computed from ROLE_SPECS and model options come from modelOptsConfig. */
  function writtenKeys(): Set<string> {
    const start = panelSource.indexOf('let config: Record<string, unknown>')
    const end = panelSource.indexOf('savePending(pendingId, config, title)')
    expect(start).toBeGreaterThan(0)
    expect(end).toBeGreaterThan(start)
    const effect = panelSource.slice(start, end)
    const keys = new Set<string>()
    for (const m of effect.matchAll(/\bconfig\.(\w+)\s*=/g)) keys.add(m[1])
    for (const m of effect.matchAll(/\bconfig\s*=\s*\{([^\n]*)\}/g)) {
      for (const k of m[1].matchAll(/(?:^|[{,]\s*)(\w+)(?=\s*[:,}]|\s*$)/g)) keys.add(k[1])
    }
    const fn = modelSource.slice(modelSource.indexOf('export function modelOptsConfig'))
    const body = fn.slice(0, fn.indexOf('\n}\n'))
    for (const m of body.matchAll(/\{\s*(\w+):/g)) keys.add(m[1])
    return keys
  }

  it('every key the save effect writes is listed, so it is not carried over stale', () => {
    const written = writtenKeys()
    expect(written.size).toBeGreaterThan(100)
    const unlisted = [...written].filter(k => !PANEL_KEYS.has(k))
    expect(unlisted).toEqual([])
  })

  it('role keys are managed; what other panes write is not', () => {
    const keys = panelManagedKeys()
    for (const k of ['dimension', 'dimension2', 'measure', 'lat', 'lon2', 'measures', 'predictors']) {
      expect(keys.has(k), k).toBe(true)
    }
    for (const k of ['interaction', 'hidden', 'tabIndex', 'roles', 'cluster_cell_degrees', 'split_by']) {
      expect(keys.has(k), k).toBe(false)
    }
    expect(FLAT_ROLE_KEYS.every(k => keys.has(k))).toBe(true)
  })

  it('keepUnmanaged keeps exactly the unmanaged keys', () => {
    expect(keepUnmanaged({ measure: 'x', y_min: 3, interaction: { receives: false }, hidden: true, tabIndex: 2 }))
      .toEqual({ interaction: { receives: false }, hidden: true, tabIndex: 2 })
  })
})

// ── Through the panel ──────────────────────────────────────────────────────

const columns: DatasetColumn[] = [
  { id: 1, name: 'region',     dtype: 'text',  missing_pct: 0, stats: {} },
  { id: 2, name: 'revenue',    dtype: 'float', missing_pct: 0, stats: {} },
  { id: 3, name: 'origin_lat', dtype: 'float', missing_pct: 0, stats: {} },
  { id: 4, name: 'origin_lon', dtype: 'float', missing_pct: 0, stats: {} },
  { id: 5, name: 'shipments',  dtype: 'int',   missing_pct: 0, stats: {} },
]
const pages: ReportPage[] = [{ id: 100, report_id: 1, name: 'Page 1', page_type: 'normal',
                               position: 0, widgets: [], created_at: '2026-01-01', page_size: '16:9' }]
const widget = (widget_type: string, config: Record<string, unknown>): Widget =>
  ({ id: 1, page_id: 100, widget_type, title: 'Chart', config,
     layout: { x: 0, y: 0, w: 6, h: 5 }, created_at: '2026-01-01' }) as Widget

function panel(w: Widget) {
  const onUpdate = vi.fn()
  render(<CrossFilterProvider><WidgetConfigPanel widget={w} columns={columns}
    onUpdate={onUpdate} pages={pages} /></CrossFilterProvider>)
  return onUpdate
}
const retitle = () => {
  fireEvent.change(screen.getByPlaceholderText('Widget title'), { target: { value: 'Renamed' } })
  act(() => { vi.advanceTimersByTime(700) })
}

beforeEach(() => { vi.useFakeTimers(); localStorage.clear() })
afterEach(() => vi.useRealTimers())

describe('a panel edit keeps what other panes and the API wrote', () => {
  it('interactions, the hidden flag and tab order survive a title edit', () => {
    const onUpdate = panel(widget('bar', {
      dimension: 'region', measure: 'revenue', aggregation: 'sum',
      interaction: { broadcasts: false, receives: true }, hidden: true, tabIndex: 3,
    }))
    retitle()
    const [config, title] = onUpdate.mock.calls.at(-1)!
    expect(title).toBe('Renamed')
    expect(config).toMatchObject({ dimension: 'region', measure: 'revenue',
      interaction: { broadcasts: false, receives: true }, hidden: true, tabIndex: 3 })
  })

  it('a setting only the API writes survives too', () => {
    const onUpdate = panel(widget('bar', { dimension: 'region', measure: 'revenue', split_by: 'region' }))
    retitle()
    const [config] = onUpdate.mock.calls.at(-1)!
    expect(config.split_by).toBe('region')
  })
})

describe('a legacy config opens as what it is', () => {
  it('a roles dict (the demo maps) opens with its roles and saves them flat', () => {
    const onUpdate = panel(widget('map_clusters', {
      roles: { lat: 'origin_lat', lon: 'origin_lon', measure: 'shipments' }, cluster_cell_degrees: 10 }))
    retitle()
    const [config] = onUpdate.mock.calls.at(-1)!
    expect(config).toMatchObject({ lat: 'origin_lat', lon: 'origin_lon', measure: 'shipments',
                                   cluster_cell_degrees: 10 })
    expect(config).not.toHaveProperty('roles')
  })

  it('agg opens as the aggregation, and is saved as aggregation', () => {
    const onUpdate = panel(widget('bar', { dimension: 'region', measure: 'revenue', agg: 'avg' }))
    expect(screen.getByLabelText('Aggregation')).toHaveValue('avg')
    retitle()
    const [config] = onUpdate.mock.calls.at(-1)!
    expect(config.aggregation).toBe('avg')
    expect(config).not.toHaveProperty('agg')
  })
})

describe('"Percentage %" is offered where the chart computes it', () => {
  const offered = () => [...(screen.getByLabelText('Aggregation') as HTMLSelectElement).options].map(o => o.value)

  it('on a bar', () => {
    panel(widget('bar', { dimension: 'region', measure: 'revenue', aggregation: 'sum' }))
    expect(offered()).toContain('pct')
  })

  it('not on a KPI, which would show a sum labelled as a percentage', () => {
    panel(widget('kpi', { measure: 'revenue', aggregation: 'sum' }))
    expect(offered()).not.toContain('pct')
    expect(offered()).toContain('sum')
  })

  it('a stored one stays visible rather than being silently replaced', () => {
    panel(widget('kpi', { measure: 'revenue', aggregation: 'pct' }))
    expect(screen.getByLabelText('Aggregation')).toHaveValue('pct')
  })
})

describe('the panel offers exactly the values a save accepts', () => {
  /** The option values of the control whose change handler is `setter`,
   *  read from the panel's source: a <select> or a `sel(value, setter, [...])`. */
  function offered(setter: string): string[] {
    const src = panelSource
    let block = ''
    const selAt = src.search(new RegExp(`sel\\(\\w+, ${setter},`))
    if (selAt >= 0) {
      block = src.slice(selAt, src.indexOf(']', src.indexOf('[', selAt)))
    } else {
      const at = src.indexOf(`${setter}(e.target.value`)
      expect(at, setter).toBeGreaterThan(0)
      const open = src.lastIndexOf('<select', at)
      block = src.slice(open, src.indexOf('</select>', at))
    }
    const values = new Set<string>()
    for (const m of block.matchAll(/value="([^"]*)"|value: '([^']*)'/g)) values.add(m[1] ?? m[2])
    for (const m of block.matchAll(/\[([^\]]*)\]\.map/g)) {
      for (const q of m[1].matchAll(/'([^']+)'/g)) values.add(q[1])
    }
    values.delete('')
    return [...values].sort()
  }
  const SETTERS: Record<string, string> = {
    sort: 'setSort', sort_by: 'setSortBy', quick_calc: 'setQuickCalc',
    totals_position: 'setTotalsPosition', totals_scope: 'setTotalsScope', bar_mode: 'setBarMode',
    slicer_mode: 'setSlicerMode', legend_position: 'setLegendPosition', y_scale: 'setYScale',
    gauge_shape: 'setGaugeShape', container_mode: 'setContainerMode',
    dimension_granularity: 'setDimensionGranularity',
  }

  it('covers every setting with a vocabulary', () => {
    expect(Object.keys(SETTERS).sort()).toEqual(Object.keys(SETTING_VOCABULARIES).sort())
  })

  for (const [key, setter] of Object.entries(SETTERS)) {
    it(key, () => {
      expect(offered(setter)).toEqual([...SETTING_VOCABULARIES[key]].sort())
    })
  }
})

describe('dates can be grouped on a dataset that has a drill hierarchy', () => {
  // Found by the families browser journey: with a hierarchy, the dimension
  // field is drawn as the hierarchy picker, which left out "Group dates by" --
  // a line chart over dates could not be grouped by month.
  const withDate: DatasetColumn[] = [
    ...columns, { id: 9, name: 'order_date', dtype: 'datetime', missing_pct: 0, stats: {} },
  ]
  const hierarchy = [{ id: 1, dataset_id: 1, parent_id: null, name: 'Drill', node_type: 'folder',
                       position: 0, created_at: '2026-01-01' },
                     { id: 2, dataset_id: 1, parent_id: 1, name: 'Region', node_type: 'dimension',
                       column_name: 'region', position: 0, created_at: '2026-01-01' }] as never

  it('offers it under a date dimension, and saves the choice', () => {
    const onUpdate = vi.fn()
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget('line', { dimension: 'order_date', measure: 'revenue' })}
      columns={withDate} hierarchy={hierarchy} onUpdate={onUpdate} pages={pages} /></CrossFilterProvider>)
    fireEvent.change(screen.getByLabelText('Group dates by'), { target: { value: 'month' } })
    act(() => { vi.advanceTimersByTime(700) })
    expect(onUpdate.mock.calls.at(-1)![0]).toMatchObject({ dimension: 'order_date', dimension_granularity: 'month' })
  })

  it('not under a text dimension', () => {
    render(<CrossFilterProvider><WidgetConfigPanel widget={widget('line', { dimension: 'region', measure: 'revenue' })}
      columns={withDate} hierarchy={hierarchy} onUpdate={vi.fn()} pages={pages} /></CrossFilterProvider>)
    expect(screen.queryByLabelText('Group dates by')).toBeNull()
  })
})
