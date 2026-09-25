import { useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'

export interface CanvasJoin { left_table: string; left_column: string; table: string; right_column: string; how: string }

/** Every join the compiler accepts, with the shape each one keeps.
 *  `cross` needs no ON clause, which is why it is offered here and NOT
 *  reachable by drawing a line between two columns. */
export const JOIN_TYPES: { how: string; label: string; hint: string }[] = [
  { how: 'inner', label: 'Inner', hint: 'Only rows that match on both sides' },
  { how: 'left', label: 'Left', hint: 'Every row from the left table; nulls where none matches' },
  { how: 'right', label: 'Right', hint: 'Every row from the right table; nulls where none matches' },
  { how: 'full', label: 'Full outer', hint: 'Every row from both sides' },
  { how: 'cross', label: 'Cross', hint: 'Every row against every row — no matching column' },
]

const colKey = (table: string, column: string) => `${table}.${column}`

/**
 * The diagram half of the query builder: each active table or view is a
 * draggable box listing its columns; join edges are drawn between the exact
 * column rows they connect. Authoring is click-to-connect — click a column in
 * one box, then a column in another, and the join exists (left by default;
 * the edge label opens a picker for all five join types, ✕ removes it). Each
 * non-base table can be closed from its own header, which also drops the joins
 * that touched it. The canvas and the form rows below it edit the SAME model,
 * so neither can drift.
 */
export default function QueryCanvas({ tables, kinds, columnsByTable, joins, onAddJoin, onCycleJoin, onRemoveJoin,
  onSetJoinType, onCloseTable,
  selectedColumns = new Set(), aggByColumn = {}, onToggleColumn, onCycleAggregation }: {
  tables: string[]                       // base first
  kinds: Record<string, string>          // table|view
  columnsByTable: Record<string, string[]>
  joins: CanvasJoin[]
  onAddJoin: (j: CanvasJoin) => void
  onCycleJoin: (index: number) => void
  onRemoveJoin: (index: number) => void
  /** Set one join's type outright. Preferred over cycling now that five types
   *  exist -- `onCycleJoin` stays for callers that have not migrated. */
  onSetJoinType?: (index: number, how: string) => void
  /** Remove a table from the diagram, with the joins that touched it. Absent
   *  for the base table: closing the thing every join hangs off would empty
   *  the query rather than tidy it. */
  onCloseTable?: (table: string) => void
  // D3: column checkboxes + per-column aggregation badge -- the SAME output-
  // column list the form rows below edit (this canvas never keeps its own
  // copy), keyed "table.column".
  selectedColumns?: Set<string>
  aggByColumn?: Record<string, string>
  onToggleColumn?: (table: string, column: string) => void
  onCycleAggregation?: (table: string, column: string) => void
}) {
  const [positions, setPositions] = useState<Record<string, { x: number; y: number }>>({})
  const [pending, setPending] = useState<{ table: string; column: string } | null>(null)
  const [picking, setPicking] = useState<number | null>(null)
  const [drag, setDrag] = useState<{ table: string; dx: number; dy: number } | null>(null)
  const rootRef = useRef<HTMLDivElement>(null)
  const colRefs = useRef<Record<string, HTMLElement | null>>({})
  const [edges, setEdges] = useState<{ x1: number; y1: number; x2: number; y2: number; how: string; i: number }[]>([])

  // default layout: base at the left, each further table one column to the right
  useEffect(() => {
    setPositions(prev => {
      const next = { ...prev }
      tables.forEach((t, i) => { if (!next[t]) next[t] = { x: 20 + i * 230, y: 16 + (i % 2) * 30 } })
      for (const k of Object.keys(next)) if (!tables.includes(k)) delete next[k]
      return next
    })
  }, [tables])

  // measured edges: endpoints read from the rendered column rows, so the lines
  // always match what the user actually sees (the Lineage page's approach)
  useEffect(() => {
    const root = rootRef.current
    if (!root) return
    const base = root.getBoundingClientRect()
    const next: typeof edges = []
    joins.forEach((j, i) => {
      const a = colRefs.current[`${j.left_table}.${j.left_column}`]?.getBoundingClientRect()
      const b = colRefs.current[`${j.table}.${j.right_column}`]?.getBoundingClientRect()
      if (!a || !b) return
      const leftFirst = a.left <= b.left
      next.push({
        x1: (leftFirst ? a.right : a.left) - base.left, y1: a.top + a.height / 2 - base.top,
        x2: (leftFirst ? b.left : b.right) - base.left, y2: b.top + b.height / 2 - base.top,
        how: j.how, i,
      })
    })
    setEdges(next)
  }, [joins, positions, columnsByTable, tables])

  const clickColumn = (table: string, column: string) => {
    if (!pending) { setPending({ table, column }); return }
    if (pending.table === table) { setPending({ table, column }); return }
    onAddJoin({ left_table: pending.table, left_column: pending.column,
      table, right_column: column, how: 'left' })
    setPending(null)
  }

  const onMouseMove = (e: React.MouseEvent) => {
    if (!drag || !rootRef.current) return
    const base = rootRef.current.getBoundingClientRect()
    setPositions(p => ({ ...p, [drag.table]: {
      x: Math.max(0, e.clientX - base.left - drag.dx),
      y: Math.max(0, e.clientY - base.top - drag.dy) } }))
  }

  return (
    <div ref={rootRef} data-testid="query-canvas"
      onMouseMove={onMouseMove} onMouseUp={() => setDrag(null)} onMouseLeave={() => setDrag(null)}
      style={{ position: 'relative', minHeight: 240, border: '1px solid var(--border)', borderRadius: 8,
        background: 'var(--surface2)', overflow: 'hidden', marginBottom: 12 }}>
      <svg aria-hidden style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}>
        {edges.map(e => (
          <line key={e.i} x1={e.x1} y1={e.y1} x2={e.x2} y2={e.y2}
            stroke="var(--accent)" strokeWidth={2} opacity={0.8} />
        ))}
      </svg>
      {edges.map(e => (
        <span key={`lbl-${e.i}`} style={{ position: 'absolute', left: (e.x1 + e.x2) / 2 - 30, top: (e.y1 + e.y2) / 2 - 10,
          display: 'flex', gap: 2, alignItems: 'center', zIndex: 2 }}>
          {/* A PICKER, not a cycle button. Cycling was fine for three types;
              with five it makes finding "full outer" a guessing game, and it
              can never offer `cross` -- which has no ON clause and so cannot
              be produced by drawing a line between two columns at all. The
              button keeps its old test id and still shows the current type. */}
          <button data-testid={`join-label-${e.i}`}
            onClick={() => setPicking(picking === e.i ? null : e.i)}
            aria-haspopup="menu" aria-expanded={picking === e.i}
            title={JOIN_TYPES.find(t => t.how === e.how)?.hint ?? 'Change join type'}
            style={{ fontSize: 10.5, fontWeight: 700, padding: '1px 6px', borderRadius: 8, cursor: 'pointer',
              border: '1px solid var(--accent)', background: 'var(--surface)', color: 'var(--accent)' }}>
            {e.how}
          </button>
          <button aria-label={`Remove join ${e.i + 1}`} onClick={() => onRemoveJoin(e.i)}
            style={{ fontSize: 10.5, border: 'none', background: 'none', color: 'var(--danger)', cursor: 'pointer', padding: 0 }}>✕</button>
          {picking === e.i && (
            <div role="menu" aria-label="Join type"
              style={{ position: 'absolute', top: '120%', insetInlineStart: 0, zIndex: 5, minWidth: 190,
                background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8,
                boxShadow: '0 8px 24px rgba(0,0,0,.2)', padding: 4 }}>
              {JOIN_TYPES.map(t => (
                <button key={t.how} role="menuitemradio" aria-checked={t.how === e.how}
                  onClick={() => { onSetJoinType?.(e.i, t.how); setPicking(null) }}
                  style={{ display: 'block', width: '100%', textAlign: 'start', border: 'none',
                    cursor: 'pointer', borderRadius: 6, padding: '5px 7px', fontSize: 10.5,
                    fontFamily: 'var(--sans)',
                    background: t.how === e.how ? 'var(--accent-soft)' : 'transparent',
                    color: t.how === e.how ? 'var(--accent)' : 'var(--text)',
                    fontWeight: t.how === e.how ? 700 : 400 }}>
                  {t.label}
                  <span style={{ display: 'block', fontSize: 10.5, color: 'var(--muted)', fontWeight: 400 }}>
                    {t.hint}
                  </span>
                </button>
              ))}
            </div>
          )}
        </span>
      ))}
      {tables.map(t => (
        <div key={t} data-testid={`canvas-table-${t}`}
          style={{ position: 'absolute', left: positions[t]?.x ?? 20, top: positions[t]?.y ?? 16,
            width: 200, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8,
            boxShadow: '0 2px 8px rgba(0,0,0,.12)', zIndex: 1, userSelect: 'none' }}>
          <div onMouseDown={e => {
              const box = (e.currentTarget.parentElement as HTMLElement).getBoundingClientRect()
              setDrag({ table: t, dx: e.clientX - box.left, dy: e.clientY - box.top })
            }}
            style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '5px 8px', cursor: 'grab',
              borderBottom: '1px solid var(--border)', fontSize: 11, fontWeight: 700 }}>
            {t}
            <span style={{ marginInlineStart: 'auto', fontSize: 8, fontWeight: 400, color: 'var(--muted)',
              border: '1px solid var(--border)', borderRadius: 6, padding: '0 5px', textTransform: 'uppercase' }}>
              {kinds[t] ?? 'table'}
            </span>
            {/* Closing a table takes its joins with it -- leaving an edge
                pointing at a box that is gone would compile to a join on a
                table the query no longer selects from. The BASE table has no
                close button: removing it would not tidy the diagram, it would
                empty the query. */}
            {onCloseTable && t !== tables[0] && (
              <button data-testid={`close-table-${t}`} aria-label={`Remove ${t} from the query`}
                title={`Remove ${t} and its joins`}
                onMouseDown={e => e.stopPropagation()}
                onClick={e => { e.stopPropagation(); onCloseTable(t) }}
                style={{ display: 'inline-flex', border: 'none', background: 'none', cursor: 'pointer',
                  color: 'var(--muted)', padding: 0, marginInlineStart: 2 }}>
                <X size={11} />
              </button>
            )}
          </div>
          <div style={{ maxHeight: 150, overflowY: 'auto' }}>
            {(columnsByTable[t] ?? []).map(c => {
              const isPending = pending?.table === t && pending?.column === c
              const key = colKey(t, c)
              const isSelected = selectedColumns.has(key)
              return (
                <div key={c} style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '1px 4px',
                  background: isPending ? 'color-mix(in srgb, var(--accent) 20%, transparent)' : 'transparent' }}>
                  <input type="checkbox" aria-label={`Include ${key}`} checked={isSelected}
                    onChange={() => onToggleColumn?.(t, c)}
                    style={{ margin: 0, cursor: onToggleColumn ? 'pointer' : 'default' }} />
                  <button ref={el => { colRefs.current[key] = el }}
                    onClick={() => clickColumn(t, c)}
                    title={pending && pending.table !== t ? `Join ${pending.table}.${pending.column} = ${t}.${c}` : 'Click, then a column in another table, to join'}
                    style={{ display: 'block', flex: 1, textAlign: 'start', fontSize: 11, padding: '2px 4px',
                      border: 'none', cursor: 'pointer', color: 'var(--text)', background: 'transparent' }}>
                    {c}
                  </button>
                  {isSelected && (
                    <button aria-label={`Aggregation ${key}`} title="Click to cycle aggregation"
                      onClick={() => onCycleAggregation?.(t, c)}
                      style={{ fontSize: 8, fontWeight: 700, padding: '1px 5px', borderRadius: 6, cursor: 'pointer',
                        border: '1px solid var(--accent)', background: 'var(--surface2)', color: 'var(--accent)',
                        textTransform: 'uppercase', whiteSpace: 'nowrap' }}>
                      {aggByColumn[key] || 'raw'}
                    </button>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      ))}
      {pending && (
        <div style={{ position: 'absolute', bottom: 6, insetInlineStart: 8, fontSize: 11, color: 'var(--accent)', zIndex: 2 }}>
          Joining from {pending.table}.{pending.column} — click a column in another table (Esc to cancel)
        </div>
      )}
    </div>
  )
}
