import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import LoadError from '../components/ui/LoadError'
import LoadingState from '../components/ui/LoadingState'
import { Link } from 'react-router-dom'
import { lineageApi, type LineageGraph } from '../services/api'
import { useDirection } from '../contexts/DirectionContext'
import { useT } from '../i18n'

function timeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime()
  const mins = Math.round(ms / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.round(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.round(hours / 24)
  return `${days}d ago`
}

/**
 * The org's data estate as three columns — sources → datasets → reports — with
 * edges for feeds, joins and reads. Answers both lineage questions: where a
 * number came from, and what breaks if a dataset is deleted.
 *
 * Layout is measured, not simulated: nodes are plain DOM in columns, and edge
 * endpoints are read from the rendered boxes, so the SVG always matches what
 * the user actually sees.
 */
export default function Lineage() {
  const [graph, setGraph] = useState<LineageGraph | null>(null)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [selected, setSelected] = useState<string | null>(null)   // "ds:5" | "rep:2" | "src:1"
  const containerRef = useRef<HTMLDivElement>(null)
  const nodeRefs = useRef<Record<string, HTMLElement | null>>({})
  const [paths, setPaths] = useState<{ d: string; key: string; active: boolean; label?: string; lx?: number; ly?: number }[]>([])
  const { rtl } = useDirection()
  const t = useT()

  // An API failure used to be rendered as an EMPTY GRAPH -- a confident,
  // wrong statement that the org has no data assets. `graph` now stays null on
  // failure so the empty-state branch cannot run, and the error says plainly
  // that we could not ask rather than that there is nothing to find.
  const load = useCallback(() => {
    setLoadError(null)
    lineageApi.graph().then(setGraph).catch(e => setLoadError(e ?? new Error('failed')))
  }, [])
  useEffect(load, [load])

  const edges = useMemo(() => {
    if (!graph) return []
    const out: { from: string; to: string; label?: string }[] = []
    for (const d of graph.datasets) {
      if (d.source_id != null) out.push({ from: `src:${d.source_id}`, to: `ds:${d.id}`, label: 'extract' })
      for (const j of d.joins) out.push({ from: `ds:${j}`, to: `ds:${d.id}` })
    }
    for (const r of graph.reports) for (const id of r.dataset_ids) out.push({ from: `ds:${id}`, to: `rep:${r.id}` })
    return out
  }, [graph])

  const touching = useMemo(() => {
    if (!selected) return null
    const set = new Set([selected])
    for (const e of edges) {
      if (e.from === selected) set.add(e.to)
      if (e.to === selected) set.add(e.from)
    }
    return set
  }, [selected, edges])

  const measure = useCallback(() => {
    const container = containerRef.current
    if (!container || !graph) return
    const base = container.getBoundingClientRect()
    const next: { d: string; key: string; active: boolean; label?: string; lx?: number; ly?: number }[] = []
    for (const e of edges) {
      const a = nodeRefs.current[e.from]?.getBoundingClientRect()
      const b = nodeRefs.current[e.to]?.getBoundingClientRect()
      if (!a || !b) continue
      // An edge leaves the side of the source that FACES the target, and
      // arrives on the target's facing side. Hardcoding right->left assumed the
      // source column always sits to the left, which `dir="rtl"` reverses: the
      // browser mirrors the columns but knows nothing about these SVG
      // coordinates, so the curves kept sweeping out of the wrong edge and no
      // longer met the nodes they connect.
      //
      // The facing side is DERIVED from the measured boxes rather than from the
      // direction flag -- the same technique QueryCanvas already uses for its
      // join lines. Measuring is strictly better than asking: it stays correct
      // for a back-edge that points against the general flow (a join between
      // two datasets in the SAME column), which a direction-only rule gets
      // backwards in either direction.
      const leftFirst = a.left <= b.left
      const x1 = (leftFirst ? a.right : a.left) - base.left
      const y1 = a.top + a.height / 2 - base.top
      const x2 = (leftFirst ? b.left : b.right) - base.left
      const y2 = b.top + b.height / 2 - base.top
      const mid = (x1 + x2) / 2
      next.push({
        key: `${e.from}->${e.to}`,
        d: `M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}`,
        active: !touching || (touching.has(e.from) && touching.has(e.to)),
        label: e.label, lx: mid, ly: (y1 + y2) / 2,
      })
    }
    setPaths(next)
  }, [graph, edges, touching])

  /**
   * Re-measure whenever the LAYOUT changes, not merely when React re-renders.
   *
   * Measuring in a plain effect was reliably stale on a direction switch, and
   * not by a race: `dir` is applied in DirectionProvider's effect, and React
   * runs a CHILD's effects before its ancestors' -- so this page measured the
   * columns before the browser had mirrored them, and the curves kept the old
   * geometry until something else forced a re-render. That is the "needs a
   * manual refresh" bug.
   *
   * A ResizeObserver on the container removes the dependency on effect order
   * entirely: the mirrored layout IS a resize/reflow of the node boxes, so the
   * measurement happens after the browser has done the work, whatever caused
   * it -- direction, window resize, a font finally loading, or a node's text
   * wrapping differently.
   */
  useEffect(() => {
    measure()
    const container = containerRef.current
    if (!container || typeof ResizeObserver === 'undefined') return
    // Observing the container alone is not enough: mirroring moves the CHILDREN
    // without changing the container's own box, so each node is observed too.
    const ro = new ResizeObserver(() => measure())
    ro.observe(container)
    for (const el of Object.values(nodeRefs.current)) if (el) ro.observe(el)
    return () => ro.disconnect()
  }, [measure])

  // Direction is not a resize of any single box -- the columns swap places
  // while keeping their sizes -- so the observer above can miss it. Measuring
  // on the next frame lets the browser finish the mirrored layout first.
  useEffect(() => {
    const id = requestAnimationFrame(() => measure())
    return () => cancelAnimationFrame(id)
  }, [rtl, measure])

  if (loadError) {
    return (
      <div style={{ padding: 24 }}>
        <LoadError what="the lineage graph" error={loadError} onRetry={load} />
      </div>
    )
  }
  if (!graph) return <div style={{ padding: 24 }}><LoadingState /></div>

  const node = (key: string, title: string, subtitle: string, link?: string, badges?: React.ReactNode) => {
    const dimmed = touching ? !touching.has(key) : false
    return (
      // The BOX (border, position, the ref the edges are drawn to) wraps two
      // siblings: the selectable node itself, and the link that opens it. The
      // link used to sit INSIDE the role="button", which a screen reader
      // cannot reach (axe: nested-interactive, 74 times on this page).
      <div key={key} ref={el => { nodeRefs.current[key] = el }}
        style={{ border: '1px solid var(--border)', borderRadius: 8, padding: '8px 10px',
          background: 'var(--surface)', opacity: dimmed ? 0.3 : 1, position: 'relative',
          outline: selected === key ? '2px solid var(--accent)' : 'none', transition: 'opacity .12s' }}>
        <div
          // "Click a node to trace its connections" is what this page is FOR, and
          // it was a bare div: no role, no tabIndex, no key handler, so a keyboard
          // user could read the graph but never select anything in it.
          role="button"
          tabIndex={0}
          aria-pressed={selected === key}
          aria-label={`${title} — ${subtitle}`}
          onClick={() => setSelected(s => (s === key ? null : key))}
          onKeyDown={e => {
            // Enter and Space are what a real button answers to; without both,
            // the node is reachable by Tab but still not operable.
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault()
              setSelected(s => (s === key ? null : key))
            }
          }}
          style={{ cursor: 'pointer', paddingInlineEnd: link ? 22 : 0 }}>
          <div style={{ fontSize: 12, fontWeight: 600 }}>{title}</div>
          <div style={{ fontSize: 10, color: 'var(--muted)' }}>{subtitle}</div>
          {badges && <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 5 }}>{badges}</div>}
        </div>
        {link && (
          <Link to={link} aria-label={`Open ${title}`} title={`Open ${title}`}
            // A 24px hit area (WCAG 2.5.8), not the 9px glyph.
            style={{ position: 'absolute', top: 2, insetInlineEnd: 2, fontSize: 12,
              minWidth: 24, minHeight: 24, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
              color: 'var(--muted)', textDecoration: 'none' }}>↗</Link>
        )}
      </div>
    )
  }

  const badge = (label: string, title: string, color?: string) => (
    <span key={label + title} title={title} style={{ fontSize: 9, fontWeight: 700, lineHeight: 1,
      padding: '2px 5px', borderRadius: 4, border: '1px solid var(--border)',
      color: color ?? 'var(--muted)', background: 'var(--surface2)' }}>
      {label}
    </span>
  )

  const etlBadges = (d: LineageGraph['datasets'][number]) => {
    const out: React.ReactNode[] = []
    if (d.extraction_kind) out.push(badge('E', `Extracted from: ${d.extraction_kind}`))
    const t = d.transform ?? { count: 0, kinds: [] }
    if (t.count > 0) {
      const kindsPreview = t.kinds.slice(0, 3).join(', ') + (t.kinds.length > 3 ? '…' : '')
      out.push(badge('T', `${t.count} active step${t.count === 1 ? '' : 's'}: ${kindsPreview || t.kinds.join(', ')}`))
    }
    const l = d.load ?? { last_refreshed_at: null, strategy: null, cursor_column: null, staleness: 'never' as const }
    if (l.staleness === 'never') {
      out.push(badge('L', 'Never refreshed', 'var(--muted)'))
    } else if (l.last_refreshed_at) {
      const label = `Refreshed ${timeAgo(l.last_refreshed_at)}${l.strategy ? ` · ${l.strategy}` : ''}`
      out.push(badge('L', label, l.staleness === 'stale' ? 'var(--warning)' : 'var(--success)'))
    }
    return out
  }

  const col = (title: string, children: React.ReactNode) => (
    <div style={{ flex: 1, minWidth: 200, display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em' }}>{title}</div>
      {children}
    </div>
  )

  return (
    <div style={{ padding: 24, height: '100%', overflowY: 'auto' }}>
      <h1 style={{ fontSize: 18, marginBottom: 4 }}>{t('nav.lineage')}</h1>
      <p style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 18 }}>
        {t('lineage.subtitle')}
      </p>
      <div ref={containerRef} style={{ position: 'relative', display: 'flex', gap: 80, alignItems: 'flex-start' }}>
        <svg aria-hidden style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}>
          {paths.map(p => (
            <g key={p.key}>
              <path d={p.d} fill="none"
                stroke={p.active ? 'var(--accent)' : 'var(--border)'}
                strokeWidth={p.active && touching ? 2 : 1.25} opacity={p.active ? 0.85 : 0.35} />
              {p.label && (
                <text x={p.lx} y={(p.ly ?? 0) - 4} textAnchor="middle" fontSize={9}
                  fill="var(--muted)" opacity={p.active ? 0.9 : 0.4}>{p.label}</text>
              )}
            </g>
          ))}
        </svg>
        {col(t('lineage.sources'), graph.sources.length
          ? graph.sources.map(s => node(`src:${s.id}`, s.name, s.type, '/connections'))
          : <p style={{ fontSize: 11, color: 'var(--muted)' }}>No connections — uploads only.</p>)}
        {col(t('lineage.datasets'), graph.datasets.length
          ? graph.datasets.map(d =>
              node(`ds:${d.id}`, d.name,
                [d.mode === 'directquery' ? 'DirectQuery' : 'Import', d.joins.length ? `joins ${d.joins.length}` : '']
                  .filter(Boolean).join(' · '),
                `/datasets/${d.id}#prep-pipeline`, etlBadges(d)))
          : <p style={{ fontSize: 11, color: 'var(--muted)' }}>No datasets yet.</p>)}
        {col(t('lineage.reports'), graph.reports.length
          ? graph.reports.map(r =>
              node(`rep:${r.id}`, r.name, `reads ${r.dataset_ids.length} dataset${r.dataset_ids.length === 1 ? '' : 's'}`,
                `/reports/${r.id}`))
          : <p style={{ fontSize: 11, color: 'var(--muted)' }}>No reports yet.</p>)}
      </div>
    </div>
  )
}
