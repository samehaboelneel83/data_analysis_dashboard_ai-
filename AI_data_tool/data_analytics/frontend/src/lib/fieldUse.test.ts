import { describe, it, expect } from 'vitest'
import { fieldUse } from './semanticGuard'
import { storedNumberUse } from './dtypeName'
import { hierarchyChain } from './hierarchyUtils'
import type { HierarchyNode } from '../types/report'

/** QA6 B4: one rule for how a field is used, wherever it is shown. */
describe('fieldUse', () => {
  it('a stored number is a measure unless its name says otherwise', () => {
    expect(fieldUse({ name: 'revenue', dtype: 'numeric' })).toBe('measure')
    expect(fieldUse({ name: 'year', dtype: 'numeric' })).toBe('category')
    expect(fieldUse({ name: 'customer_id', dtype: 'numeric' })).toBe('category')
    expect(fieldUse({ name: 'latitude', dtype: 'numeric' })).toBe('geo')
  })
  it("the author's role wins, a calculated field is a measure, a date a date", () => {
    expect(fieldUse({ name: 'year', dtype: 'numeric' }, 'measure')).toBe('measure')
    expect(fieldUse({ name: 'revenue', dtype: 'numeric' }, 'category')).toBe('category')
    expect(fieldUse({ name: 'margin', dtype: 'calculated' })).toBe('measure')
    expect(fieldUse({ name: 'order_date', dtype: 'datetime' })).toBe('date')
    expect(fieldUse({ name: 'region', dtype: 'text' })).toBe('category')
  })
  it('the Data view names the use beside "Number" only where they differ', () => {
    const t = ((k: string) => k) as never
    expect(storedNumberUse(t, 'year', 'numeric')?.tag).toBe('pg.types.use.category')
    expect(storedNumberUse(t, 'revenue', 'numeric')).toBeNull()
    expect(storedNumberUse(t, 'region', 'text')).toBeNull()
  })
})

/** QA6 B2: a hierarchy folder as a sunburst's levels, outer first. */
describe('hierarchyChain', () => {
  const node = (id: number, parent_id: number | null, column_name?: string) =>
    ({ id, parent_id, column_name, name: column_name ?? 'Sales drill-down', node_type: column_name ? 'column' : 'folder' }) as unknown as HierarchyNode
  const nodes = [node(1, null), node(2, 1, 'region'), node(3, 2, 'country'), node(4, 3, 'city')]
  it('walks from the folder down, one column per level', () => {
    expect(hierarchyChain(nodes, 1)).toEqual(['region', 'country', 'city'])
    expect(hierarchyChain(nodes, 1, 2)).toEqual(['region', 'country'])
    expect(hierarchyChain(nodes, 99)).toEqual([])
  })
})
