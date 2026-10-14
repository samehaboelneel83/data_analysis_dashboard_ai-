/**
 * The query builder's conditions as a tree of boxes (query builder plan step 2,
 * 2026-10-10): "Match all / Match any" groups that hold conditions and other
 * groups, so  condition = Used AND (make = Kia OR make = Hyundai)  is built
 * without the SQL tab.
 *
 * The saved model is the backend's (services/query_builder.py): a filter is a
 * condition {table, column, op, value} or a group {group: 'and'|'or',
 * filters: [...]}. The SQL that runs is compiled there, never here -- this
 * module only converts, previews and says what is unfinished.
 *
 * A saved condition this editor cannot show (a sub-query) is KEPT as it was:
 * reopening a saved query used to drop it without a word.
 */
import { compileConditionRow, type SqlConditionRow, type SqlJoiner, type SqlOperator } from './sqlWhere'

export interface CondRow {
  kind: 'row'
  id: string
  table: string
  column: string
  op: SqlOperator
  value: string
}
export interface CondGroup {
  kind: 'group'
  id: string
  joiner: SqlJoiner
  items: CondNode[]
}
/** A saved condition this editor does not edit, carried through unchanged. */
export interface CondKept {
  kind: 'kept'
  id: string
  raw: Record<string, unknown>
}
export type CondNode = CondRow | CondGroup | CondKept

/** The backend's nesting limit (_MAX_GROUP_DEPTH): deeper groups are refused. */
export const MAX_GROUP_DEPTH = 5

let seq = 0
export const newId = () => `c${++seq}`

export const newRow = (table: string): CondRow =>
  ({ kind: 'row', id: newId(), table, column: '', op: 'eq', value: '' })
export const newGroup = (joiner: SqlJoiner = 'or', table = ''): CondGroup =>
  ({ kind: 'group', id: newId(), joiner, items: [newRow(table)] })

const NO_VALUE: SqlOperator[] = ['is_null', 'not_null']

/** What still has to be filled in before a row counts; [] when complete. */
export function rowProblems(r: CondRow): ('needColumn' | 'needValue' | 'needList')[] {
  if (!r.column) return ['needColumn']
  if (NO_VALUE.includes(r.op)) return []
  if (r.op === 'in') return r.value.split(',').some(v => v.trim()) ? [] : ['needList']
  return r.value.trim() === '' ? ['needValue'] : []
}

/** Saved model filters -> boxes. */
export function fromModel(filters: unknown, base: string): CondNode[] {
  if (!Array.isArray(filters)) return []
  return filters.flatMap((f): CondNode[] => {
    if (!f || typeof f !== 'object') return []
    const o = f as Record<string, unknown>
    if ('group' in o) {
      return [{ kind: 'group', id: newId(), joiner: o.group === 'or' ? 'or' : 'and',
        items: fromModel(o.filters, base) }]
    }
    if (o.subquery && typeof o.subquery === 'object') return [{ kind: 'kept', id: newId(), raw: o }]
    const v = o.value
    return [{ kind: 'row', id: newId(), table: String(o.table || base), column: String(o.column ?? ''),
      op: (String(o.op || 'eq')) as SqlOperator,
      value: Array.isArray(v) ? v.join(', ') : v == null ? '' : String(v) }]
  })
}

/** Boxes -> saved model filters. Unfinished rows and empty groups are left
 *  out (they are shown as "to fix" on screen, never sent half-made). */
export function toModel(nodes: CondNode[], base: string): Record<string, unknown>[] {
  return nodes.flatMap((n): Record<string, unknown>[] => {
    if (n.kind === 'kept') return [n.raw]
    if (n.kind === 'group') {
      const items = toModel(n.items, base)
      return items.length ? [{ group: n.joiner, filters: items }] : []
    }
    if (rowProblems(n).length) return []
    const value = n.op === 'in' ? n.value.split(',').map(x => x.trim()).filter(Boolean)
      : NO_VALUE.includes(n.op) ? undefined
        : isNaN(Number(n.value)) || n.value.trim() === '' ? n.value : Number(n.value)
    return [{ table: n.table || base, column: n.column, op: n.op, ...(value === undefined ? {} : { value }) }]
  })
}

/** How many conditions will actually count (complete rows and kept ones). */
export function countConditions(nodes: CondNode[]): number {
  return nodes.reduce((n, c) => n + (c.kind === 'group' ? countConditions(c.items)
    : c.kind === 'kept' ? 1 : rowProblems(c).length ? 0 : 1), 0)
}

/** How many rows are unfinished, anywhere in the tree. */
export function countProblems(nodes: CondNode[]): number {
  return nodes.reduce((n, c) => n + (c.kind === 'group' ? countProblems(c.items)
    : c.kind === 'row' && rowProblems(c).length ? 1 : 0), 0)
}

/** A readable WHERE preview, brackets where the boxes are. The real SQL is
 *  the server's (shown in the SQL tab). */
export function previewWhere(nodes: CondNode[], joiner: SqlJoiner): string {
  const parts = nodes.map(n => {
    if (n.kind === 'kept') return '(…)'
    if (n.kind === 'group') {
      const inner = n.items.map(i => previewWhere([i], n.joiner)).filter(Boolean)
      return inner.length > 1 ? `(${inner.join(` ${n.joiner.toUpperCase()} `)})` : (inner[0] ?? '')
    }
    return compileConditionRow({ column: n.column, op: n.op, value: n.value } as SqlConditionRow)
  }).filter(Boolean)
  return parts.join(` ${joiner.toUpperCase()} `)
}

/** The tree with every row on `table` removed (the table left the query). */
export function dropTable(nodes: CondNode[], table: string, base: string): CondNode[] {
  return nodes.flatMap((n): CondNode[] => {
    if (n.kind === 'group') return [{ ...n, items: dropTable(n.items, table, base) }]
    if (n.kind === 'row') return (n.table || base) === table ? [] : [n]
    return [n]
  })
}

/** Replace the node with this id (null removes it), anywhere in the tree. */
export function updateNode(nodes: CondNode[], id: string, next: CondNode | null): CondNode[] {
  return nodes.flatMap((n): CondNode[] => {
    if (n.id === id) return next ? [next] : []
    if (n.kind === 'group') return [{ ...n, items: updateNode(n.items, id, next) }]
    return [n]
  })
}
