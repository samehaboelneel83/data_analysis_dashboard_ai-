import { describe, it, expect } from 'vitest'
import { conversionsFor, convertConfig, measuresOf } from './convertWidget'
import { ROLE_SPECS, MULTI_MEASURE_WIDGETS, configKeyFor, type WidgetType } from '../types/report'
import { PERCENT_WIDGETS } from '../components/report/widgetCapabilities'

const types = (from: string, cfg: Record<string, unknown>) => conversionsFor(from, cfg).map(c => c.type)

describe('what an object can become', () => {
  const bar = { dimension: 'region', measure: 'revenue', aggregation: 'sum' }

  it('a bar of one measure by a category: other one-category, one-measure charts, and a KPI', () => {
    const got = types('bar', bar)
    for (const t of ['line', 'area', 'pie', 'donut', 'treemap', 'funnel', 'kpi', 'table']) expect(got).toContain(t)
    expect(got).not.toContain('bar')                 // not itself
  })

  it('never a type that needs a field the widget does not hold', () => {
    const got = types('bar', bar)
    expect(got).not.toContain('dual_axis_bar')       // needs a second measure
    expect(got.some(x => x.startsWith('map_'))).toBe(false)   // a map needs known geography
    expect(got).not.toContain('schedule')            // needs start and end dates
  })

  it('a second measure opens the two-measure charts', () => {
    const got = types('bar', { ...bar, extra_measures: ['cost'] })
    expect(got).toContain('dual_axis_bar')
    const dual = convertConfig('bar', { ...bar, extra_measures: ['cost'] }, 'dual_axis_bar')!
    expect(dual).toMatchObject({ dimension: 'region', measure: 'revenue', measure2: 'cost' })
  })

  it('measures move between measure, measure2, measures and extra_measures', () => {
    expect(measuresOf({ measure: 'a', measure2: 'b', extra_measures: ['c'], measures: ['a', 'd'] }))
      .toEqual(['a', 'b', 'c', 'd'])
    expect(convertConfig('card', { measures: ['revenue', 'cost'] }, 'kpi')).toMatchObject({ measure: 'revenue' })
    expect(convertConfig('dual_axis_line', { dimension: 'm', measure: 'a', measure2: 'b' }, 'line'))
      .toMatchObject({ measure: 'a', extra_measures: ['b'] })
  })

  it('filters and the category bucketing travel; formatting does not', () => {
    const cfg = { dimension: 'ordered_at', dimension_granularity: 'month', measure: 'revenue', aggregation: 'avg',
      filters: [{ column: 'region', op: 'eq', value: 'N' }], y_axis_label: 'Revenue', bar_mode: 'stacked', legend: false }
    const line = convertConfig('bar', cfg, 'line')!
    expect(line).toEqual({ dimension: 'ordered_at', dimension_granularity: 'month', measure: 'revenue',
      aggregation: 'avg', filters: cfg.filters })
  })

  it('a percentage aggregation only where the new type computes shares', () => {
    const pct = { dimension: 'region', measure: 'revenue', aggregation: 'pct' }
    for (const c of conversionsFor('pie', pct)) {
      if (c.config.aggregation === 'pct') expect(PERCENT_WIDGETS.has(c.type)).toBe(true)
    }
  })

  it('never offered as an empty chart: at least one field carries over', () => {
    for (const c of conversionsFor('kpi', { measure: 'revenue' })) {
      expect(Object.keys(c.config).length).toBeGreaterThan(0)
    }
  })

  it('maps convert among themselves', () => {
    expect(types('map_choropleth', { dimension: 'governorate', measure: 'revenue' }).some(x => x.startsWith('map_'))).toBe(true)
  })

  it('objects that are not data charts are not converted, nor converted to', () => {
    expect(conversionsFor('text', { content: 'hi' })).toEqual([])
    expect(types('bar', bar).some(t => t === 'text' || t === 'button' || t.startsWith('model_'))).toBe(false)
  })
})

describe('every conversion is one the server accepts', () => {
  // The server refuses formatting a type would ignore and checks nested
  // settings; a converted config carries none of those -- only these keys.
  const ROLE_KEYS = new Set(Object.values(ROLE_SPECS).flatMap(specs => specs.map(rf => rf.multi ? rf.role : configKeyFor(rf.role))))
  const ALLOWED = new Set([...ROLE_KEYS, 'filters', 'aggregation', 'extra_measures',
    'dimension_granularity', 'fiscal_start_month', 'hierarchyNodeId'])

  /** A config with every role of `type` filled, numbers for number roles. */
  const full = (type: WidgetType) => Object.fromEntries((ROLE_SPECS[type] ?? []).map(rf =>
    rf.multi ? [rf.role, ['n1', 'n2']] : [configKeyFor(rf.role), `${rf.role}_col`]))

  it.each(Object.keys(ROLE_SPECS) as WidgetType[])('from %s', from => {
    for (const { type, config } of conversionsFor(from, { ...full(from), aggregation: 'sum', filters: [] })) {
      for (const k of Object.keys(config)) expect(ALLOWED.has(k), `${from} -> ${type} carried ${k}`).toBe(true)
      for (const rf of ROLE_SPECS[type as WidgetType]) {
        if (!rf.required) continue
        const v = config[rf.multi ? rf.role : configKeyFor(rf.role)]
        expect(Array.isArray(v) ? v.length > 0 : !!v, `${from} -> ${type} lacks required ${rf.role}`).toBe(true)
      }
      if (config.extra_measures) {
        expect(MULTI_MEASURE_WIDGETS.includes(type)).toBe(true)
        expect(config.dimension2).toBeUndefined()
      }
    }
  })
})
