import { describe, it, expect } from 'vitest'
import { mergeWidgetEdits, resolveMerge, type WidgetEdit } from './threeWayMerge'

const base: WidgetEdit = { widget_type: 'bar', title: 'Sales', config: { dimension: 'region', measure: 'sales', sort: 'desc' } }

describe('mergeWidgetEdits (E09)', () => {
  it('keeps both sides when they changed different settings, with no question', () => {
    const theirs = { ...base, config: { ...base.config, measure: 'profit' } }
    const mine = { ...base, title: 'Sales by region', config: { ...base.config, sort: 'asc' } }
    const r = mergeWidgetEdits(base, theirs, mine)
    expect(r.conflicts).toEqual([])
    expect(r.merged).toEqual({ widget_type: 'bar', title: 'Sales by region',
      config: { dimension: 'region', measure: 'profit', sort: 'asc' } })
    expect(r.fromMine).toBe(2)
    expect(r.fromTheirs).toBe(1)
  })

  it('asks only about a setting both changed differently', () => {
    const theirs = { ...base, config: { ...base.config, measure: 'profit' } }
    const mine = { ...base, config: { ...base.config, measure: 'units' } }
    const r = mergeWidgetEdits(base, theirs, mine)
    expect(r.conflicts).toEqual([{ key: 'measure', base: 'sales', theirs: 'profit', mine: 'units' }])
    expect(resolveMerge(r, { measure: 'mine' }).config.measure).toBe('units')
    expect(resolveMerge(r, { measure: 'theirs' }).config.measure).toBe('profit')
  })

  it('treats the same change on both sides as agreement', () => {
    const both = { ...base, config: { ...base.config, measure: 'profit' } }
    const r = mergeWidgetEdits(base, both, { ...both })
    expect(r.conflicts).toEqual([])
    expect(r.merged.config.measure).toBe('profit')
  })

  it('keeps a removal by one side and a key added by the other', () => {
    const { sort: _dropped, ...rest } = base.config
    const theirs = { ...base, config: rest }
    const mine = { ...base, config: { ...base.config, color: 'region' } }
    const r = mergeWidgetEdits(base, theirs, mine)
    expect(r.conflicts).toEqual([])
    expect(r.merged.config).toEqual({ dimension: 'region', measure: 'sales', color: 'region' })
  })

  it('a removal against a change is a conflict, and choosing the removal deletes the key', () => {
    const { sort: _dropped, ...rest } = base.config
    const r = mergeWidgetEdits(base, { ...base, config: rest }, { ...base, config: { ...base.config, sort: 'asc' } })
    expect(r.conflicts.map(c => c.key)).toEqual(['sort'])
    expect(resolveMerge(r, { sort: 'theirs' }).config).not.toHaveProperty('sort')
    expect(resolveMerge(r, { sort: 'mine' }).config.sort).toBe('asc')
  })

  it('compares nested settings whole, and handles the title and the type like any setting', () => {
    const theirs = { ...base, widget_type: 'line', config: { ...base.config, filters: [{ column: 'year', op: 'eq', value: 2025 }] } }
    const mine = { ...base, title: 'Mine', widget_type: 'pie', config: { ...base.config, filters: [{ column: 'year', op: 'eq', value: 2026 }] } }
    const r = mergeWidgetEdits(base, theirs, mine)
    expect(r.conflicts.map(c => c.key).sort()).toEqual(['filters', 'widget_type'])
    const out = resolveMerge(r, { widget_type: 'mine', filters: 'theirs' })
    expect(out.widget_type).toBe('pie')
    expect(out.title).toBe('Mine')
    expect(out.config.filters).toEqual([{ column: 'year', op: 'eq', value: 2025 }])
  })

  it('does not change the result it resolves', () => {
    const r = mergeWidgetEdits(base, { ...base, config: { ...base.config, measure: 'a' } },
      { ...base, config: { ...base.config, measure: 'b' } })
    resolveMerge(r, { measure: 'mine' })
    expect(r.merged.config.measure).toBe('a')
  })
})
