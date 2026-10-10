/**
 * A hierarchy slicer as a tree of tick boxes (hierarchy plan, step 2,
 * 2026-10-10): Egypt ▸ Cairo ▸ Nasr City. Ticking a parent ticks its whole
 * branch; a parent with only some ticked shows a dash. Search finds a value at
 * any level and opens the way to it. The ticks are read from the page's
 * filters (props.paths), so clearing the chip elsewhere -- or a bookmark --
 * moves them too. Rules: lib/slicerTree.ts.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { useT } from '../../i18n'
import { fromPaths, keyOf, leaves, searchTree, stateOf, toPaths, toggle, type CheckState, type Path, type TreeNode } from '../../lib/slicerTree'

interface Props {
  data: { nodes?: TreeNode[]; levels?: { column: string }[]; truncated?: boolean }
  paths: Path[] | null
  rtl?: boolean
  onChange?: (paths: Path[] | null) => void
}

function TickBox({ state, label, onClick }: { state: CheckState; label: string; onClick: () => void }) {
  const ref = useRef<HTMLInputElement>(null)
  useEffect(() => { if (ref.current) ref.current.indeterminate = state === 'mixed' }, [state])
  return (
    <input ref={ref} type="checkbox" checked={state === 'on'} aria-label={label}
      aria-checked={state === 'mixed' ? 'mixed' : state === 'on'}
      onChange={onClick} onClick={e => e.stopPropagation()} style={{ margin: 0 }} />
  )
}

const LINK: React.CSSProperties = { border: 'none', background: 'none', padding: 0, cursor: 'pointer', color: 'var(--accent)', font: 'inherit' }

export default function SlicerTree({ data, paths, rtl, onChange }: Props) {
  const t = useT()
  const nodes = data.nodes ?? []
  const ticked = useMemo(() => fromPaths(nodes, paths), [nodes, paths])
  const [open, setOpen] = useState<Set<string>>(new Set())
  const [query, setQuery] = useState('')
  const found = useMemo(() => searchTree(nodes, query), [nodes, query])
  const total = useMemo(() => leaves(nodes).length, [nodes])

  const commit = (next: Set<string>) => onChange?.(toPaths(nodes, next))
  const isOpen = (k: string) => found ? found.open.has(k) || open.has(k) : open.has(k)
  const flip = (k: string) => setOpen(prev => { const n = new Set(prev); if (n.has(k)) n.delete(k); else n.add(k); return n })

  const render = (ns: TreeNode[], prefix: Path, depth: number): React.ReactNode => ns.map(n => {
    const p = [...prefix, n.value]
    const k = keyOf(p)
    if (found && !found.visible.has(k)) return null
    const st = stateOf(n, p, ticked)
    const hasKids = n.children.length > 0
    const expanded = hasKids && isOpen(k)
    return (
      <li key={k} role="treeitem" aria-level={depth + 1} aria-expanded={hasKids ? expanded : undefined}
        aria-selected={st === 'on'} style={{ listStyle: 'none' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4, paddingInlineStart: depth * 14, minHeight: 22 }}>
          {hasKids ? (
            <button type="button" onClick={e => { e.stopPropagation(); flip(k) }}
              aria-label={expanded ? t('st.collapse', { name: n.value }) : t('st.expand', { name: n.value })}
              style={{ border: 'none', background: 'none', cursor: 'pointer', color: 'var(--muted)', width: 16, padding: 0, fontSize: 10 }}>
              {expanded ? '▾' : rtl ? '◂' : '▸'}
            </button>
          ) : <span style={{ width: 16 }} aria-hidden />}
          <TickBox state={st} label={p.join(' › ')}
            onClick={() => commit(toggle(n, p, ticked))} />
          <span dir="auto" style={{ fontSize: 12, flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
            title={p.join(' › ')}>{n.value}</span>
          <span style={{ fontSize: 10.5, color: 'var(--muted)', fontVariantNumeric: 'tabular-nums' }}>{n.count.toLocaleString()}</span>
        </div>
        {expanded && <ul role="group" style={{ margin: 0, padding: 0 }}>{render(n.children, p, depth + 1)}</ul>}
      </li>
    )
  })

  return (
    <div dir={rtl ? 'rtl' : undefined} data-testid="slicer-tree"
      style={{ display: 'flex', flexDirection: 'column', height: '100%', padding: 6, gap: 4 }}>
      <input type="search" value={query} onChange={e => setQuery(e.target.value)}
        aria-label={t('st.search')} placeholder={t('st.search')}
        style={{ fontSize: 12, padding: '4px 8px', border: '1px solid var(--border)', borderRadius: 6,
          background: 'var(--surface)', color: 'var(--text)' }} />
      <div style={{ display: 'flex', gap: 8, fontSize: 11 }}>
        <button type="button" style={LINK} onClick={() => commit(new Set(leaves(nodes).map(keyOf)))}>{t('st.all')}</button>
        <button type="button" style={LINK} disabled={!paths?.length} onClick={() => onChange?.(null)}>{t('st.clear')}</button>
        <span style={{ marginInlineStart: 'auto', color: 'var(--muted)' }}>
          {ticked.size ? t('st.ticked', { n: ticked.size.toLocaleString(), total: total.toLocaleString() }) : t('st.none')}
        </span>
      </div>
      <ul role="tree" aria-label={(data.levels ?? []).map(l => l.column).join(' › ')}
        aria-multiselectable="true" style={{ margin: 0, padding: 0, overflow: 'auto', flex: 1 }}>
        {render(nodes, [], 0)}
      </ul>
      {found && found.visible.size === 0 && <div style={{ fontSize: 11, color: 'var(--muted)' }}>{t('st.noMatch')}</div>}
      {data.truncated && <div style={{ fontSize: 10.5, color: 'var(--muted)' }}>{t('st.truncated')}</div>}
    </div>
  )
}
