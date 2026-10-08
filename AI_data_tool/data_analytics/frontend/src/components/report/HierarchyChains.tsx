import { useState } from 'react'
import { ArrowDown, ArrowUp, Calendar, Globe, GripVertical, Type } from 'lucide-react'
import type { HierarchyNode } from '../../types/report'
import { useT } from '../../i18n'

/** One drill chain: its title and its levels, outermost first. */
export interface Chain {
  key: string; title: string; kind: 'date' | 'geography' | 'other'; levels: HierarchyNode[]
  /** What a drag onto the canvas carries: the node whose first level charts
   *  (the date column, or the chain's folder). */
  anchor: number
}

/**
 * The drill chains a hierarchy holds: under each date column its Year >
 * Quarter > Month > Week > Date levels, and the Geography chain (Continent >
 * Country > City). A chain head is a non-folder node sitting directly under
 * a folder (or at the top) that has levels below it; a date column's own node
 * titles its chain rather than being a level of it.
 */
export function chainsOf(nodes: HierarchyNode[]): Chain[] {
  const byId = new Map(nodes.map(n => [n.id, n]))
  const kids = (id: number) => nodes.filter(n => n.parent_id === id).sort((a, b) => a.position - b.position)
  const follow = (n: HierarchyNode): HierarchyNode[] => {
    const out: HierarchyNode[] = []
    let cur = kids(n.id)[0]
    while (cur) { out.push(cur); cur = kids(cur.id)[0] }
    return out
  }
  const out: Chain[] = []
  for (const n of nodes) {
    if (n.node_type === 'folder') continue
    const parent = n.parent_id == null ? undefined : byId.get(n.parent_id)
    if (parent && parent.node_type !== 'folder') continue
    const below = follow(n)
    if (below.length === 0) continue
    const dateColumn = n.node_type === 'date' && !n.format
    const levels = dateColumn ? below : [n, ...below]
    if (levels.length < 2 && !dateColumn) continue
    out.push({
      key: String(n.id),
      title: dateColumn ? n.name : parent?.name ?? n.name,
      kind: dateColumn ? 'date' : /geograph/i.test(parent?.name ?? '') ? 'geography' : 'other',
      levels,
      anchor: dateColumn ? n.id : parent?.id ?? n.id,
    })
  }
  return out
}

/** `order` with the level at `from` moved to `to`. */
export function moved<T>(order: T[], from: number, to: number): T[] {
  const next = order.slice()
  const [x] = next.splice(from, 1)
  next.splice(to, 0, x)
  return next
}

/**
 * The Data pane's Hierarchies, as a tree: each chain folds under its title,
 * its levels nested one under another, each with a checkbox (staged like a
 * field) and a handle to drag it up or down the chain -- with arrow buttons
 * for the keyboard. A reorder is one call, the whole chain at once.
 */
export default function HierarchyChains({ nodes, isChecked, onToggle, onReorder, onPick, canEdit }: {
  nodes: HierarchyNode[]
  isChecked: (token: string) => boolean
  onToggle: (token: string) => void
  onReorder: (ids: number[]) => void
  /** Click a level's name: bind it to the selected widget. */
  onPick?: (node: HierarchyNode) => void
  canEdit: boolean
}) {
  const t = useT()
  const [folded, setFolded] = useState<Set<string>>(() => new Set())
  const [drag, setDrag] = useState<{ chain: string; from: number } | null>(null)
  const chains = chainsOf(nodes)
  if (chains.length === 0) return null
  const Icon = (k: Chain['kind']) => (k === 'date' ? Calendar : k === 'geography' ? Globe : Type)
  const btn: React.CSSProperties = { background: 'none', border: 'none', cursor: 'pointer', color: 'var(--muted)', padding: '0 2px', lineHeight: 1 }
  return (
    <div data-testid="hierarchy-chains" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      {chains.map(c => {
        const open = !folded.has(c.key)
        const LevelIcon = Icon(c.kind)
        const reorder = (from: number, to: number) => {
          if (from === to || to < 0 || to >= c.levels.length) return
          onReorder(moved(c.levels, from, to).map(l => l.id))
        }
        return (
          <div key={c.key} data-chain={c.title}>
            <button type="button" aria-expanded={open} draggable
              title={t('bc.panes.hc.dragHint')}
              onDragStart={e => { e.dataTransfer.setData('application/x-hierarchy', String(c.anchor)); e.dataTransfer.effectAllowed = 'copy' }}
              onClick={() => setFolded(p => { const n = new Set(p); if (n.has(c.key)) n.delete(c.key); else n.add(c.key); return n })}
              style={{ ...btn, color: 'var(--text)', display: 'flex', alignItems: 'center', gap: 4, fontSize: 11.5, fontWeight: 600, padding: '2px 0' }}>
              <span aria-hidden style={{ fontSize: 9, display: 'inline-block', transform: open ? 'none' : 'rotate(-90deg)' }}>▾</span>
              <LevelIcon size={12} aria-hidden /> {c.title}
            </button>
            {open && (
              <ol role="list" aria-label={t('bc.panes.hc.levels', { chain: c.title })} style={{ listStyle: 'none', margin: 0, padding: 0 }}>
                {c.levels.map((l, i) => {
                  const token = `h:${l.id}`
                  return (
                    <li key={l.id} data-level={l.name}
                      draggable={canEdit}
                      onDragStart={e => { setDrag({ chain: c.key, from: i }); e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('application/x-level', String(l.id)) }}
                      onDragOver={e => { if (drag?.chain === c.key) e.preventDefault() }}
                      onDrop={e => { e.preventDefault(); if (drag?.chain === c.key) reorder(drag.from, i); setDrag(null) }}
                      onDragEnd={() => setDrag(null)}
                      style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '2px 0',
                        paddingInlineStart: 10 + i * 12,
                        background: drag?.chain === c.key && drag.from === i ? 'var(--surface2)' : undefined }}>
                      <input type="checkbox" aria-label={t('bc.panes.hc.select', { chain: c.title, level: l.name })} checked={isChecked(token)}
                        onChange={() => onToggle(token)} style={{ margin: 0 }} />
                      {canEdit && <GripVertical size={12} aria-hidden style={{ color: 'var(--muted)', cursor: 'grab', flex: 'none' }} />}
                      <button type="button" onClick={() => (onPick ? onPick(l) : onToggle(token))}
                        title={onPick ? t('bc.panes.hc.pick', { level: l.name }) : undefined}
                        style={{ ...btn, color: 'var(--text)', fontSize: 11.5, flex: 1, textAlign: 'start', minWidth: 0,
                          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {l.name}
                      </button>
                      {canEdit && (<>
                        <button type="button" style={btn} aria-label={t('bc.panes.hc.up', { level: l.name })} disabled={i === 0}
                          onClick={() => reorder(i, i - 1)}><ArrowUp size={11} aria-hidden /></button>
                        <button type="button" style={btn} aria-label={t('bc.panes.hc.down', { level: l.name })} disabled={i === c.levels.length - 1}
                          onClick={() => reorder(i, i + 1)}><ArrowDown size={11} aria-hidden /></button>
                      </>)}
                    </li>
                  )
                })}
              </ol>
            )}
          </div>
        )
      })}
    </div>
  )
}
