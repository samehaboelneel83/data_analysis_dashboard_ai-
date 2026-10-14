/**
 * The query builder's conditions as nested boxes (query builder plan step 2):
 * a box says "Match all / any of these" and holds conditions and other boxes.
 * Each unfinished condition says, inside its own box and in plain words, what
 * it still needs; it is left out of the query until it is complete.
 * The tree logic is lib/conditionTree.ts; the SQL is compiled server-side.
 */
import { useT, type MessageKey } from '../i18n'
import type { SqlJoiner, SqlOperator } from '../lib/sqlWhere'
import {
  MAX_GROUP_DEPTH, newGroup, newRow, rowProblems, updateNode,
  type CondGroup, type CondNode, type CondRow,
} from '../lib/conditionTree'

const OPS: SqlOperator[] = ['eq', 'ne', 'gt', 'gte', 'lt', 'lte', 'contains', 'in', 'is_null', 'not_null']
/** One accent per nesting level, so a box's edge says which box it is in. */
const EDGE = ['var(--accent)', '#a78bfa', '#38bdf8', '#f59e0b', '#34d399', '#f472b6']

interface Props {
  nodes: CondNode[]
  joiner: SqlJoiner
  onChange: (nodes: CondNode[]) => void
  onJoiner: (j: SqlJoiner) => void
  tables: string[]
  base: string
  columnsOf: (table: string) => string[]
  /** The outer box's title; "Rows to keep" in the query builder. */
  rootLabel?: string
}

export default function ConditionBoxes({ nodes, joiner, onChange, onJoiner, tables, base, columnsOf, rootLabel }: Props) {
  const tr = useT()
  // Conditions are numbered across the whole tree, so every control's label
  // ("Value of condition 3") names exactly one condition.
  const numbers = new Map<string, number>()
  const walk = (ns: CondNode[]) => ns.forEach(n => n.kind === 'group' ? walk(n.items) : numbers.set(n.id, numbers.size + 1))
  walk(nodes)
  return (
    <Box depth={0} joiner={joiner} onJoiner={onJoiner} items={nodes}
      label={rootLabel ?? tr('qb.box.where')}
      setItems={onChange}
      ctx={{ all: nodes, onChange, tables, base, columnsOf, numbers }} />
  )
}

interface Ctx {
  all: CondNode[]
  onChange: (nodes: CondNode[]) => void
  tables: string[]
  base: string
  columnsOf: (table: string) => string[]
  numbers: Map<string, number>
}

function Box({ depth, joiner, onJoiner, items, setItems, label, onRemove, ctx }: {
  depth: number
  joiner: SqlJoiner
  onJoiner: (j: SqlJoiner) => void
  items: CondNode[]
  setItems: (items: CondNode[]) => void
  label: string
  onRemove?: () => void
  ctx: Ctx
}) {
  const tr = useT()
  const edge = EDGE[depth % EDGE.length]
  return (
    <div role="group" aria-label={label} data-testid={depth === 0 ? 'qb-conditions' : 'qb-condition-group'}
      style={{ border: '1px solid var(--border)', borderInlineStart: `3px solid ${edge}`, borderRadius: 8,
        padding: '6px 8px', marginBottom: 6, background: depth % 2 ? 'var(--surface2)' : 'transparent' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: items.length ? 6 : 0, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: edge }}>{label}</span>
        <select aria-label={tr('qb.box.matchAria', { box: label })} value={joiner}
          onChange={e => onJoiner(e.target.value as SqlJoiner)} style={{ fontSize: 11 }}>
          <option value="and">{tr('qb.box.matchAll')}</option>
          <option value="or">{tr('qb.box.matchAny')}</option>
        </select>
        {onRemove && (
          <button type="button" onClick={onRemove} aria-label={tr('qb.box.removeGroup')}
            style={{ marginInlineStart: 'auto', fontSize: 11, border: 'none', background: 'none',
              color: 'var(--danger)', cursor: 'pointer', textDecoration: 'underline' }}>
            {tr('qb.box.removeGroup')}
          </button>
        )}
      </div>
      {items.length === 0 && depth > 0 && (
        <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>{tr('qb.box.emptyGroup')}</div>
      )}
      {items.map((n, i) => (
        <div key={n.id}>
          {i > 0 && (
            <div aria-hidden style={{ fontSize: 10, fontWeight: 700, color: edge, margin: '2px 0 2px 4px' }}>
              {joiner === 'and' ? tr('qb.box.and') : tr('qb.box.or')}
            </div>
          )}
          {n.kind === 'group'
            ? <Box depth={depth + 1} joiner={n.joiner} items={n.items} ctx={ctx}
                label={tr('qb.box.group')}
                onJoiner={j => ctx.onChange(updateNode(ctx.all, n.id, { ...n, joiner: j }))}
                setItems={next => ctx.onChange(updateNode(ctx.all, n.id, { ...n, items: next } as CondGroup))}
                onRemove={() => ctx.onChange(updateNode(ctx.all, n.id, null))} />
            : n.kind === 'kept'
              ? <div data-testid="qb-condition-kept" style={{ fontSize: 11, color: 'var(--muted)', border: '1px dashed var(--border)',
                  borderRadius: 6, padding: '4px 8px', display: 'flex', gap: 6, alignItems: 'center' }}>
                  <span>{tr('qb.box.kept', { col: String(n.raw.column ?? '') })}</span>
                  <button type="button" onClick={() => ctx.onChange(updateNode(ctx.all, n.id, null))}
                    aria-label={tr('qb.box.remove')} style={{ border: 'none', background: 'none', color: 'var(--danger)', cursor: 'pointer' }}>✕</button>
                </div>
              : <Row row={n} n={ctx.numbers.get(n.id) ?? i + 1} ctx={ctx} />}
        </div>
      ))}
      <div style={{ display: 'flex', gap: 6, marginTop: 4 }}>
        <button type="button" className="btn" style={{ fontSize: 11 }} disabled={!ctx.base}
          title={!ctx.base ? tr('qb.chooseBase') : undefined}
          onClick={() => setItems([...items, newRow(ctx.base)])}>{tr('qb.box.addCondition')}</button>
        {depth + 1 < MAX_GROUP_DEPTH && (
          <button type="button" className="btn" style={{ fontSize: 11 }} disabled={!ctx.base}
            title={tr('qb.box.addGroupHint')}
            onClick={() => setItems([...items, newGroup(joiner === 'and' ? 'or' : 'and', ctx.base)])}>
            {tr('qb.box.addGroup')}
          </button>
        )}
      </div>
    </div>
  )
}

function Row({ row, n, ctx }: { row: CondRow; n: number; ctx: Ctx }) {
  const tr = useT()
  const set = (patch: Partial<CondRow>) => ctx.onChange(updateNode(ctx.all, row.id, { ...row, ...patch }))
  const problems = rowProblems(row)
  const table = row.table || ctx.base
  return (
    <div data-testid="qb-condition" style={{ border: `1px solid ${problems.length ? 'var(--danger)' : 'var(--border)'}`,
      borderRadius: 6, padding: '4px 6px' }}>
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', alignItems: 'center' }}>
        {ctx.tables.length > 1 && (
          <select aria-label={tr('qb.box.table', { n })} value={table} style={{ fontSize: 11 }}
            onChange={e => set({ table: e.target.value, column: '' })}>
            {ctx.tables.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        )}
        <select aria-label={tr('qb.box.column', { n })} value={row.column} style={{ fontSize: 11 }}
          onChange={e => set({ column: e.target.value })}>
          <option value="">{tr('qb.box.pickColumn')}</option>
          {ctx.columnsOf(table).map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <select aria-label={tr('qb.box.op', { n })} value={row.op} style={{ fontSize: 11 }}
          onChange={e => set({ op: e.target.value as SqlOperator })}>
          {OPS.map(o => <option key={o} value={o}>{tr(`qb.op.${o}` as MessageKey)}</option>)}
        </select>
        {row.op !== 'is_null' && row.op !== 'not_null' && (
          <input aria-label={tr('qb.box.value', { n })} value={row.value} style={{ fontSize: 11, width: 120 }}
            placeholder={row.op === 'in' ? tr('qb.box.listHint') : tr('qb.box.valueHint')}
            onChange={e => set({ value: e.target.value })} />
        )}
        <button type="button" onClick={() => ctx.onChange(updateNode(ctx.all, row.id, null))}
          aria-label={tr('qb.box.removeN', { n })} title={tr('qb.box.remove')}
          style={{ border: 'none', background: 'none', color: 'var(--danger)', cursor: 'pointer' }}>✕</button>
      </div>
      {problems.length > 0 && (
        <div role="status" style={{ fontSize: 11, color: 'var(--danger)', marginTop: 3 }}>
          {tr(`qb.box.${problems[0]}` as MessageKey)} — {tr('qb.box.leftOut')}
        </div>
      )}
    </div>
  )
}
