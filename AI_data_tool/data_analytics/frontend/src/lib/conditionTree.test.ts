import { describe, it, expect } from 'vitest'
import {
  countConditions, countProblems, dropTable, fromModel, previewWhere, rowProblems, toModel, updateNode,
  type CondNode, type CondRow,
} from './conditionTree'

const row = (column: string, op: CondRow['op'], value: string, table = 't'): CondRow =>
  ({ kind: 'row', id: `${column}${value}`, table, column, op, value })

describe('condition boxes ↔ the saved model', () => {
  it('round-trips groups, values, lists and kept sub-queries', () => {
    const saved = [
      { table: 't', column: 'a', op: 'eq', value: 'x' },
      { group: 'or', filters: [{ table: 't', column: 'b', op: 'gte', value: 5 },
        { table: 't', column: 'c', op: 'in', value: ['p', 'q'] }] },
      { table: 't', column: 'd', op: 'in', subquery: { table: 'u', columns: [{ column: 'd' }] } },
    ]
    expect(toModel(fromModel(saved, 't'), 't')).toEqual(saved)
  })

  it('unfinished rows and empty groups never reach the query', () => {
    const nodes: CondNode[] = [row('a', 'eq', ''), { kind: 'group', id: 'g', joiner: 'or', items: [row('', 'eq', 'x')] },
      row('b', 'is_null', '')]
    expect(toModel(nodes, 't')).toEqual([{ table: 't', column: 'b', op: 'is_null' }])
    expect(countProblems(nodes)).toBe(2)
    expect(countConditions(nodes)).toBe(1)
  })

  it('says what a row still needs', () => {
    expect(rowProblems(row('', 'eq', 'x'))).toEqual(['needColumn'])
    expect(rowProblems(row('a', 'eq', ' '))).toEqual(['needValue'])
    expect(rowProblems(row('a', 'in', ' , '))).toEqual(['needList'])
    expect(rowProblems(row('a', 'not_null', ''))).toEqual([])
  })
})

describe('editing the tree', () => {
  const tree: CondNode[] = [row('a', 'eq', '1'), { kind: 'group', id: 'g', joiner: 'or',
    items: [row('b', 'eq', '2'), row('c', 'eq', '3', 'u')] }]

  it('previews brackets where the boxes are', () => {
    expect(previewWhere(tree, 'and')).toBe('a = 1 AND (b = 2 OR c = 3)')
  })

  it('removes a table\'s rows anywhere in the tree', () => {
    expect(previewWhere(dropTable(tree, 'u', 't'), 'and')).toBe('a = 1 AND b = 2')
  })

  it('updates or removes a node by id, however deep', () => {
    const next = updateNode(tree, 'b2', { ...row('b', 'eq', '9'), id: 'b2' })
    expect(previewWhere(next, 'and')).toBe('a = 1 AND (b = 9 OR c = 3)')
    expect(previewWhere(updateNode(tree, 'g', null), 'and')).toBe('a = 1')
  })
})
