import { describe, it, expect } from 'vitest'
import { roleForField } from './fieldPlacement'
import { ROLE_SPECS } from '../types/report'

const bar = ROLE_SPECS.bar
const kpi = ROLE_SPECS.kpi

describe('which role a dropped field fills (QA4 E2)', () => {
  it('the same column is never placed in a second role', () => {
    expect(roleForField(bar, { dimension: 'region', measure: 'revenue' }, 'region', false)).toBeNull()
    expect(roleForField(bar, { dimension: 'region', measure: 'revenue' }, 'revenue', true)).toBeNull()
  })

  it('a text field never goes into Measure or Target', () => {
    // dimension and series taken: nothing left a category can fill
    expect(roleForField(bar, { dimension: 'region', dimension2: 'channel' }, 'product', false)).toBeNull()
    expect(roleForField(kpi, { dimension: 'region' }, 'product', false)).toBeNull()
  })

  it('a second text field on a bar becomes its Series', () => {
    expect(roleForField(bar, { dimension: 'region', measure: 'revenue' }, 'channel', false)?.role).toBe('category2')
  })

  it('a number fills the measure first, then Target', () => {
    expect(roleForField(bar, { dimension: 'region' }, 'revenue', true)?.role).toBe('measure')
    expect(roleForField(bar, { dimension: 'region', measure: 'revenue' }, 'target', true)?.role).toBe('target')
  })

  it('a text field on an empty bar takes its dimension; a measure on a KPI that needs one fills it', () => {
    expect(roleForField(bar, {}, 'region', false)?.role).toBe('category')
    expect(roleForField(kpi, {}, 'units', true)?.role).toBe('measure')
  })
})

describe('a hierarchy widget takes fields as its levels (QA6 B2)', () => {
  const sunburst = ROLE_SPECS.sunburst

  it('offers a Levels role, so Assign data shows it', () => {
    expect(sunburst.find(rf => rf.role === 'levels')).toMatchObject({ multi: true })
    for (const wt of ['tree', 'sunburst', 'icicle', 'circle_pack', 'dendrogram', 'org'] as const)
      expect(ROLE_SPECS[wt].some(rf => rf.role === 'levels')).toBe(true)
  })

  it('a category field dropped on a sunburst fills its levels, and the next one goes on the end', () => {
    expect(roleForField(sunburst, {}, 'region', false)?.role).toBe('levels')
    expect(roleForField(sunburst, { levels: ['region'] }, 'country', false)?.role).toBe('levels')
  })

  it('never the same column twice, never a quantity, never past the deepest level', () => {
    expect(roleForField(sunburst, { levels: ['region'] }, 'region', false)).toBeNull()
    expect(roleForField(sunburst, { measure: 'revenue' }, 'units', true)).toBeNull()
    expect(roleForField(sunburst, {}, 'revenue', true)?.role).toBe('measure')
    expect(roleForField(sunburst, { levels: ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'] }, 'i', false)).toBeNull()
  })

  it('not while the widget is drawn parent-child, which ignores levels', () => {
    expect(roleForField(sunburst, { id_col: 'id', parent_col: 'parent' }, 'region', false)).toBeNull()
  })
})
