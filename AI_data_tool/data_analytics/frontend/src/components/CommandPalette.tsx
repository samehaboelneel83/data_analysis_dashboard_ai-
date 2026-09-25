import { Fragment, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { datasetsApi, reportsApi, dataSourcesApi } from '../services/api'
import { useModalDialog } from './ui/useModalDialog'
import { AuthContext } from '../contexts/AuthContext'
import { ArrowRight, Cable, Database, LayoutDashboard, Zap } from 'lucide-react'
import { useT, type MessageKey } from '../i18n'

interface Entry { kind: 'report' | 'dataset' | 'connection' | 'page' | 'command'; label: string; hint: string; to: string; labelKey?: MessageKey; hintKey?: MessageKey }

const STATIC_PAGES: Entry[] = [
  { kind: 'page', label: 'Home', hint: 'page', to: '/', labelKey: 'nav.home', hintKey: 'palette.page' },
  { kind: 'page', label: 'Ask AI', hint: 'page', to: '/ask', labelKey: 'nav.askAi', hintKey: 'palette.page' },
  { kind: 'page', label: 'Upload', hint: 'page', to: '/upload', labelKey: 'nav.upload', hintKey: 'palette.page' },
  { kind: 'page', label: 'Dashboards', hint: 'page', to: '/reports', labelKey: 'nav.dashboards', hintKey: 'palette.page' },
  { kind: 'page', label: 'Insights', hint: 'page', to: '/insights', labelKey: 'nav.insights', hintKey: 'palette.page' },
  { kind: 'page', label: 'Connections', hint: 'page', to: '/connections', labelKey: 'nav.connections', hintKey: 'palette.page' },
  { kind: 'page', label: 'Lineage', hint: 'page', to: '/lineage', labelKey: 'nav.lineage', hintKey: 'palette.page' },
]

// Shown only to org admins -- same gate as the rail's Monitoring and Admin
// sections. A palette entry a role cannot open is a dead control with a
// friendlier font.
const ADMIN_PAGES: Entry[] = [
  { kind: 'page', label: 'Refresh & jobs', hint: 'monitoring', to: '/monitoring/jobs', labelKey: 'nav.jobs', hintKey: 'palette.monitoring' },
  { kind: 'page', label: 'Deliveries', hint: 'monitoring', to: '/monitoring/deliveries', labelKey: 'nav.deliveries', hintKey: 'palette.monitoring' },
  { kind: 'page', label: 'Activity', hint: 'monitoring', to: '/monitoring/activity', labelKey: 'nav.activity', hintKey: 'palette.monitoring' },
  { kind: 'page', label: 'Column security', hint: 'admin', to: '/admin/column-security-rules', labelKey: 'nav.columnSecurity', hintKey: 'palette.admin' },
  { kind: 'page', label: 'Row security', hint: 'admin', to: '/admin/row-security-rules', labelKey: 'nav.rowSecurity', hintKey: 'palette.admin' },
  { kind: 'page', label: 'Connection rules (Ask AI)', hint: 'admin', to: '/admin/connection-rules', hintKey: 'palette.admin' },
]

/** Things to DO rather than places to go. `to` is either a route or a
 *  `cmd:` id the palette runs itself. */
const COMMANDS: Entry[] = [
  { kind: 'command', label: 'Create a dashboard', hint: 'command', to: '/reports?new=1', labelKey: 'palette.cmd.newDashboard', hintKey: 'palette.command' },
  { kind: 'command', label: 'Upload a file', hint: 'command', to: '/upload', labelKey: 'palette.cmd.upload', hintKey: 'palette.command' },
  { kind: 'command', label: 'Ask a question about your data', hint: 'command', to: '/ask', labelKey: 'palette.cmd.ask', hintKey: 'palette.command' },
  { kind: 'command', label: 'Connect a data source', hint: 'command', to: '/connections', labelKey: 'palette.cmd.connect', hintKey: 'palette.command' },
  { kind: 'command', label: 'Switch light / dark theme', hint: 'command', to: 'cmd:theme', labelKey: 'palette.cmd.theme', hintKey: 'palette.command' },
]

const KIND_ICON: Record<Entry['kind'], React.ReactNode> = {
  report: <LayoutDashboard size={13} />, dataset: <Database size={13} />,
  connection: <Cable size={13} />, page: <ArrowRight size={13} />, command: <Zap size={13} />,
}

/** Result groups, in the order they are listed. */
const GROUP_ORDER: Entry['kind'][] = ['command', 'page', 'report', 'dataset', 'connection']
const GROUP_LABEL: Record<Entry['kind'], MessageKey> = {
  command: 'palette.group.commands', page: 'palette.group.pages', report: 'palette.group.dashboards',
  dataset: 'palette.group.datasets', connection: 'palette.group.connections',
}

/**
 * How well `q` names `hay`, lower is better, -1 for no match.
 *   0 the label starts with it, 1 a WORD in it does, 2 it appears inside,
 *   3 its letters appear in order, starting at a word and close together.
 * The last used to be any in-order subsequence anywhere, so "sales" matched
 * half the index ("S...a...l...e...s" across a long dataset name) and the
 * useful hits were buried.
 */
export function matchScore(hay: string, q: string): number {
  if (!q) return 0
  if (hay.startsWith(q)) return 0
  if (hay.split(/[\s_\-·/()]+/).some(w => w.startsWith(q))) return 1
  if (hay.includes(q)) return 2
  if (q.length < 3) return -1
  for (let start = 0; start < hay.length; start++) {
    if (hay[start] !== q[0] || (start > 0 && /[a-z0-9\u0600-\u06ff]/i.test(hay[start - 1]))) continue
    let i = 1, j = start + 1
    for (; j < hay.length && i < q.length; j++) if (hay[j] === q[i]) i++
    if (i === q.length && j - start <= q.length * 3) return 3
  }
  return -1
}

/**
 * Ctrl+K, anywhere: type a few letters, land on any report, dataset,
 * connection or page. The index is fetched lazily on first open (three list
 * calls) and kept for the session — the palette must feel instant, and all
 * three lists are small.
 */
export default function CommandPalette() {
  // autoFocus: false -- the palette puts the caret in its own search box, and
  // the trap must not steal that. It already handles Escape itself; what it
  // lacked was the trap and aria-modal.
  const dialogRef = useModalDialog<HTMLDivElement>(() => setOpen(false), { autoFocus: false })
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [index, setIndex] = useState<Entry[] | null>(null)
  const [selected, setSelected] = useState(0)
  const navigate = useNavigate()
  const inputRef = useRef<HTMLInputElement>(null)
  // Context read directly (not the throwing useAuth()) so the palette still
  // renders in tests without an AuthProvider -- absent context = not admin.
  const isAdmin = !!useContext(AuthContext)?.user?.role?.is_org_admin
  const t = useT()

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setOpen(o => !o)
        setQuery('')
        setSelected(0)
      }
      if (e.key === 'Escape') setOpen(false)
    }
    // The top bar's search button opens the same palette -- one search, two
    // doors, rather than a second weaker search box beside the real one.
    const onOpen = () => { setOpen(true); setQuery(''); setSelected(0) }
    window.addEventListener('keydown', onKey)
    window.addEventListener('datalytics:open-palette', onOpen)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('datalytics:open-palette', onOpen)
    }
  }, [])

  const load = useCallback(async () => {
    if (index) return
    try {
      const [reports, datasets, connections] = await Promise.all([
        reportsApi.list(), datasetsApi.list(),
        dataSourcesApi.list().catch(() => []),  // non-admins may lack access; degrade quietly
      ])
      setIndex([
        ...COMMANDS,
        ...STATIC_PAGES,
        ...(isAdmin ? ADMIN_PAGES : []),
        ...reports.map(r => ({ kind: 'report' as const, label: r.name, hint: 'dashboard', hintKey: 'palette.dashboard' as const, to: `/reports/${r.id}` })),
        ...datasets.map(d => ({ kind: 'dataset' as const, label: d.name,
          hint: d.mode === 'directquery' ? 'dataset · live' : 'dataset',
          hintKey: (d.mode === 'directquery' ? 'palette.datasetLive' : 'palette.dataset') as MessageKey,
          to: `/datasets/${d.id}` })),
        ...connections.map(c => ({ kind: 'connection' as const, label: c.name,
          hint: 'connection', hintKey: 'palette.connection' as const, to: `/connections/${c.id}/review` })),
      ])
    } catch { setIndex([...COMMANDS, ...STATIC_PAGES, ...(isAdmin ? ADMIN_PAGES : [])]) }
  }, [index, isAdmin])

  useEffect(() => { if (open) { void load(); setTimeout(() => inputRef.current?.focus(), 30) } }, [open, load])

  const displayLabel = (e: Entry) => e.labelKey ? t(e.labelKey) : e.label
  const displayHint = (e: Entry) => e.hintKey ? t(e.hintKey) : e.hint

  const matches = useMemo(() => {
    const all = index ?? []
    if (!query.trim()) {
      // Empty query = recents first: navigation is mostly returning to the same
      // few places, so the palette's default answer is "where you just were".
      let recents: Entry[] = []
      try { recents = JSON.parse(localStorage.getItem('palette-recents') ?? '[]') } catch { /* fresh */ }
      const recentTos = new Set(recents.map(r => r.to))
      return [...recents, ...all.filter(e => !recentTos.has(e.to))].slice(0, 10)
    }
    const q = query.trim().toLowerCase()
    const scored = all.map(e => {
      const scores = [displayLabel(e).toLowerCase(), e.label.toLowerCase()]
        .map(h => matchScore(h, q)).filter(x => x >= 0)
      return { e, score: scores.length ? Math.min(...scores) : -1 }
    }).filter(x => x.score >= 0)
    scored.sort((a, b) => a.score - b.score || displayLabel(a.e).localeCompare(displayLabel(b.e)))
    // Grouped by kind, groups in a fixed order, at most five per group: a
    // search for "sales" should show the dashboards AND the dataset, not ten
    // dashboards and a dataset scrolled out of sight.
    const perKind = new Map<Entry['kind'], Entry[]>()
    for (const { e } of scored) {
      const list = perKind.get(e.kind) ?? []
      if (list.length < 5) list.push(e)
      perKind.set(e.kind, list)
    }
    return GROUP_ORDER.flatMap(k => perKind.get(k) ?? []).slice(0, 14)
  }, [index, query, t])

  // Where each group heading goes: before the first result of its kind. With
  // an empty query the recents lead, under their own heading.
  const recentCount = useMemo(() => {
    if (query.trim()) return 0
    try { return Math.min((JSON.parse(localStorage.getItem('palette-recents') ?? '[]') as Entry[]).length, 10) }
    catch { return 0 }
  }, [query, open])
  const headingAt = (i: number): MessageKey | null => {
    if (!query.trim()) {
      if (i === 0 && recentCount > 0) return 'palette.group.recent'
      if (i < recentCount) return null
    }
    const k = matches[i].kind
    const prev = i > 0 && !(i === recentCount && !query.trim()) ? matches[i - 1].kind : null
    return prev === k ? null : GROUP_LABEL[k]
  }

  const go = (entry: Entry) => {
    try {
      let recents: Entry[] = JSON.parse(localStorage.getItem('palette-recents') ?? '[]')
      recents = [entry, ...recents.filter(r => r.to !== entry.to)].slice(0, 6)
      localStorage.setItem('palette-recents', JSON.stringify(recents))
    } catch { /* recents are a convenience, never a blocker */ }
    setOpen(false)
    if (entry.to === 'cmd:theme') { window.dispatchEvent(new CustomEvent('datalytics:toggle-theme')); return }
    navigate(entry.to)
  }

  if (!open) return null
  return (
    <div onClick={() => setOpen(false)}
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.4)', zIndex: 1200,
        display: 'flex', justifyContent: 'center', paddingTop: '15vh' }}>
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-label={t('palette.aria')}
        onClick={e => e.stopPropagation()}
        style={{ width: 520, maxWidth: '92vw', alignSelf: 'flex-start', background: 'var(--surface)',
          border: '1px solid var(--border)', borderRadius: 12, boxShadow: '0 16px 48px rgba(0,0,0,.35)', overflow: 'hidden' }}>
        <input ref={inputRef} value={query} aria-label={t('palette.search')}
          placeholder={t('palette.placeholder')}
          onChange={e => { setQuery(e.target.value); setSelected(0) }}
          onKeyDown={e => {
            if (e.key === 'ArrowDown') { e.preventDefault(); setSelected(s => Math.min(s + 1, matches.length - 1)) }
            if (e.key === 'ArrowUp') { e.preventDefault(); setSelected(s => Math.max(0, s - 1)) }
            if (e.key === 'Enter' && matches[selected]) go(matches[selected])
          }}
          style={{ width: '100%', border: 'none', outline: 'none', background: 'transparent',
            padding: '14px 16px', fontSize: 14, color: 'var(--text)', borderBottom: '1px solid var(--border)' }} />
        <ul role="listbox" aria-label={t('palette.results')} style={{ listStyle: 'none', maxHeight: 380, overflowY: 'auto', padding: 6, margin: 0 }}>
          {matches.length === 0 && (
            <li style={{ padding: '10px 12px', fontSize: 12, color: 'var(--muted)' }}>{t('palette.empty')}</li>
          )}
          {matches.map((m, i) => {
            const heading = headingAt(i)
            return (<Fragment key={`${m.kind}:${m.to}`}>
            {heading && (
              <li role="presentation" className="dl-palette__group">{t(heading)}</li>
            )}
            <li role="option" aria-selected={i === selected}>
              <button onClick={() => go(m)} onMouseEnter={() => setSelected(i)}
                style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', textAlign: 'start',
                  padding: '8px 10px', border: 'none', borderRadius: 8, cursor: 'pointer', fontSize: 13,
                  background: i === selected ? 'color-mix(in srgb, var(--accent) 14%, transparent)' : 'transparent', color: 'var(--text)' }}>
                <span aria-hidden style={{ width: 18, display: 'inline-flex', justifyContent: 'center', color: 'var(--muted)' }}>{KIND_ICON[m.kind]}</span>
                <span style={{ flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{displayLabel(m)}</span>
                <span style={{ fontSize: 11, color: 'var(--muted)' }}>{displayHint(m)}</span>
              </button>
            </li>
            </Fragment>)
          })}
        </ul>
        <div style={{ padding: '7px 12px', borderTop: '1px solid var(--border)', fontSize: 11, color: 'var(--muted)' }}>
          {t('palette.hint')}
        </div>
      </div>
    </div>
  )
}
