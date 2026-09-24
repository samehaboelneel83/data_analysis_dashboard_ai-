import { useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { datasetsApi, reportsApi, dataSourcesApi } from '../services/api'
import { useModalDialog } from './ui/useModalDialog'
import { AuthContext } from '../contexts/AuthContext'
import { ArrowRight, Cable, Database, LayoutDashboard } from 'lucide-react'
import { useT, type MessageKey } from '../i18n'

interface Entry { kind: 'report' | 'dataset' | 'connection' | 'page'; label: string; hint: string; to: string; labelKey?: MessageKey; hintKey?: MessageKey }

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

const KIND_ICON: Record<Entry['kind'], React.ReactNode> = {
  report: <LayoutDashboard size={13} />, dataset: <Database size={13} />,
  connection: <Cable size={13} />, page: <ArrowRight size={13} />,
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
    } catch { setIndex(isAdmin ? [...STATIC_PAGES, ...ADMIN_PAGES] : STATIC_PAGES) }
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
    const q = query.toLowerCase()
    // rank: prefix beats substring beats fuzzy-subsequence
    const scored = all.map(e => {
      const l = displayLabel(e).toLowerCase()
      const en = e.label.toLowerCase()
      let score = -1
      for (const hay of [l, en]) {
        if (hay.startsWith(q)) { score = 0; break }
        if (hay.includes(q)) { score = 1; break }
        let i = 0
        for (const ch of hay) if (ch === q[i]) i++
        if (i === q.length) { score = 2; break }
      }
      return { e, score }
    }).filter(x => x.score >= 0)
    scored.sort((a, b) => a.score - b.score || displayLabel(a.e).localeCompare(displayLabel(b.e)))
    return scored.slice(0, 10).map(x => x.e)
  }, [index, query, t])

  const go = (entry: Entry) => {
    try {
      let recents: Entry[] = JSON.parse(localStorage.getItem('palette-recents') ?? '[]')
      recents = [entry, ...recents.filter(r => r.to !== entry.to)].slice(0, 6)
      localStorage.setItem('palette-recents', JSON.stringify(recents))
    } catch { /* recents are a convenience, never a blocker */ }
    setOpen(false)
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
        <ul role="listbox" aria-label={t('palette.results')} style={{ listStyle: 'none', maxHeight: 320, overflowY: 'auto', padding: 6 }}>
          {matches.length === 0 && (
            <li style={{ padding: '10px 12px', fontSize: 12, color: 'var(--muted)' }}>{t('palette.empty')}</li>
          )}
          {matches.map((m, i) => (
            <li key={m.to} role="option" aria-selected={i === selected}>
              <button onClick={() => go(m)} onMouseEnter={() => setSelected(i)}
                style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', textAlign: 'start',
                  padding: '8px 10px', border: 'none', borderRadius: 8, cursor: 'pointer', fontSize: 13,
                  background: i === selected ? 'color-mix(in srgb, var(--accent) 14%, transparent)' : 'transparent', color: 'var(--text)' }}>
                <span aria-hidden style={{ width: 18, display: 'inline-flex', justifyContent: 'center', color: 'var(--muted)' }}>{KIND_ICON[m.kind]}</span>
                <span style={{ flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{displayLabel(m)}</span>
                <span style={{ fontSize: 10, color: 'var(--muted)' }}>{displayHint(m)}</span>
              </button>
            </li>
          ))}
        </ul>
        <div style={{ padding: '6px 12px', borderTop: '1px solid var(--border)', fontSize: 10, color: 'var(--muted)' }}>
          {t('palette.hint')}
        </div>
      </div>
    </div>
  )
}
