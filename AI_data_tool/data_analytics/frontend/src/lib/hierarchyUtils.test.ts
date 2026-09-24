import { describe, it, expect } from 'vitest'
import { flattenHierarchy, getChildNode, walkToDepth } from './hierarchyUtils'
import type { HierarchyNode } from '../types/report'

function node(overrides: Partial<HierarchyNode>): HierarchyNode {
  return { id: 0, dataset_id: 10, parent_id: null, name: '', node_type: 'dimension', position: 0, created_at: '2026-01-01', ...overrides }
}

const dates = node({ id: 1, name: 'Dates', node_type: 'folder', parent_id: null })
const orderDate = node({ id: 2, name: 'Order Date', node_type: 'date', parent_id: 1, column_name: 'order_date' })
const year = node({ id: 3, name: 'Year', node_type: 'date', parent_id: 2, column_name: 'order_date', format: 'year' })
const quarter = node({ id: 4, name: 'Quarter', node_type: 'date', parent_id: 3, column_name: 'order_date', format: 'quarter' })
const nodes = [dates, orderDate, year, quarter]

describe('flattenHierarchy', () => {
  it('excludes folders and builds a breadcrumb-style path label for each remaining node', () => {
    const result = flattenHierarchy(nodes)
    expect(result.map(r => r.label)).toEqual(['Order Date', 'Order Date ▸ Year', 'Order Date ▸ Year ▸ Quarter'])
    expect(result.map(r => r.id)).toEqual([2, 3, 4])
  })
})

describe('getChildNode', () => {
  it('returns the single child of a node', () => {
    expect(getChildNode(nodes, 2)?.id).toBe(3)
    expect(getChildNode(nodes, 3)?.id).toBe(4)
  })
  it('returns undefined for a leaf node', () => {
    expect(getChildNode(nodes, 4)).toBeUndefined()
  })
})

describe('walkToDepth', () => {
  it('walks N child links from a starting node', () => {
    expect(walkToDepth(nodes, 2, 0)).toBe(2)
    expect(walkToDepth(nodes, 2, 1)).toBe(3)
    expect(walkToDepth(nodes, 2, 2)).toBe(4)
  })
  it('stops at a leaf if steps exceeds the chain depth', () => {
    expect(walkToDepth(nodes, 2, 10)).toBe(4)
  })
})
