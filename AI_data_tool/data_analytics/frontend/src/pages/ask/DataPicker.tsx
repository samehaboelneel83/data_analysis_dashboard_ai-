import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router-dom'
import { Check, ChevronDown, ChevronsUpDown, Database, Plug, Search, SearchX, Upload } from 'lucide-react'
import { useT } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'
import { fmtDate } from './dates'

/**
 * Step 1 of Ask AI: choose the data (step 10 design: `picker()` / `list()`).
 *
 * Three forms. `inline` (the empty page, owner's change to Part A): the list
 * itself, always open in its own column, with "Step 1 · Choose your data"
 * above it -- no trigger. `compact`: a chip in the "Asking about" row whose
 * list opens in a portal, fixed under it, flipping above when there is no
 * room below. `hero`: the large trigger ("Choose a dataset or connection",
 * the counts and the reader's last pick) with the same popover. All / Datasets /
 * Connections tabs; Recent first (this browser's own picks, then datasets made
 * in the last day), then datasets, then connections. Each row says what the
 * thing is, how big it is and how fresh (a connection has no sync time the
 * API gives, so it says only its type).
 *
 * Keyboard: the trigger opens it (Enter/Space/ArrowDown); in the search box
 * ArrowUp/Down/Home/End move, Enter chooses, Escape closes and returns focus.
 * The search input is the ARIA combobox and owns the listbox via
 * aria-activedescendant, so a screen reader follows the highlight.
 */

export interface PickerItem {
  key: string                 // "d:32" | "s:3" -- the page's scope key
  kind: 'dataset' | 'source'
  name: string
  rows?: number | null
  cols?: number | null
  sourceType?: string | null
  updated?: string | null
}

const RECENT_KEY = 'datalytics.ask.recent'

export function readRecent(): string[] {
  try {
    const v = JSON.parse(localStorage.getItem(RECENT_KEY) || '[]')
    return Array.isArray(v) ? v.filter(x => typeof x === 'string').slice(0, 3) : []
  } catch { return [] }
}
export function pushRecent(key: string) {
  try {
    const next = [key, ...readRecent().filter(k => k !== key)].slice(0, 3)
    localStorage.setItem(RECENT_KEY, JSON.stringify(next))
  } catch { /* private mode: recents are a convenience */ }
}

/** Search row + tabs + footer + gaps around the list: the popup's height minus its list. */
const POP_CHROME = 110
const LIST_MAX = 340
const LIST_MIN = 120
/** Below this much list room, a roomier side above wins. */
const LIST_COMFY = 200
const EDGE = 12
const GAP = 6

/**
 * Where the popup opens. Downward is the default; it flips UP only when the
 * list would not fit below and there is more room above. The list's
 * max-height then shrinks to the side it opened on, so it never overflows.
 */
export function placePopup(trigger: DOMRect, bounds: { top: number; bottom: number }) {
  const below = bounds.bottom - trigger.bottom - EDGE
  const above = trigger.top - bounds.top - EDGE
  const up = below < POP_CHROME + LIST_COMFY && above > below
  const room = (up ? above : below) - POP_CHROME
  return { up, listMax: Math.max(LIST_MIN, Math.min(LIST_MAX, Math.floor(room))) }
}

function shortDate(iso?: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  return isNaN(d.getTime()) ? '' : fmtDate(d, { month: 'short', day: 'numeric', year: 'numeric' })
}

/** The typed part of a name, in the accent (the design's search highlight). */
function marked(name: string, q: string): ReactNode {
  const i = q ? name.toLowerCase().indexOf(q) : -1
  if (i < 0) return name
  return <>{name.slice(0, i)}<b>{name.slice(i, i + q.length)}</b>{name.slice(i + q.length)}</>
}

type Tab = 'all' | 'dataset' | 'source'

export default function DataPicker({ items, value, onChoose, size = 'hero', loading }: {
  items: PickerItem[]
  value: string
  onChoose: (key: string) => void
  size?: 'hero' | 'compact' | 'inline'
  loading?: boolean
}) {
  const t = useT()
  const inline = size === 'inline'
  const uid = useId().replace(/:/g, '')
  const [openState, setOpen] = useState(false)
  // The inline list is always open; the others open from their trigger.
  const open = inline || openState
  const [query, setQuery] = useState('')
  const [tab, setTab] = useState<Tab>('all')
  const [active, setActive] = useState(0)
  const rootRef = useRef<HTMLDivElement>(null)
  const popRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const [pos, setPos] = useState<{ up: boolean; listMax: number; style: CSSProperties }>(
    { up: false, listMax: LIST_MAX, style: {} })

  // Measured before paint, so the popup never flashes on the wrong side. It is
  // fixed to the window (it lives in a portal), so the window is its bounds.
  useLayoutEffect(() => {
    if (inline || !open || !triggerRef.current) return
    const measure = () => {
      const tr = triggerRef.current
      if (!tr) return
      const r = tr.getBoundingClientRect()
      const p = placePopup(r, { top: 0, bottom: window.innerHeight })
      const width = Math.min(size === 'hero' ? r.width : 460, window.innerWidth - 2 * EDGE)
      const rtl = getComputedStyle(tr).direction === 'rtl'
      const left = Math.max(EDGE, Math.min(rtl ? r.right - width : r.left, window.innerWidth - width - EDGE))
      setPos({ up: p.up, listMax: p.listMax, style: {
        left, width,
        ...(p.up ? { bottom: window.innerHeight - r.top + GAP } : { top: r.bottom + GAP }),
      } })
    }
    measure()
    window.addEventListener('resize', measure)
    window.addEventListener('scroll', measure, true)
    return () => { window.removeEventListener('resize', measure); window.removeEventListener('scroll', measure, true) }
  }, [open, size, inline])

  const selected = items.find(i => i.key === value)
  const nDatasets = items.filter(i => i.kind === 'dataset').length
  const nSources = items.length - nDatasets
  const lastPick = items.find(i => i.key === readRecent()[0])

  // Recent first (what this person picked last), then datasets, then connections.
  const groups = useMemo(() => {
    const q = query.trim().toLowerCase()
    const match = (i: PickerItem) => (!q || i.name.toLowerCase().includes(q) || (i.sourceType ?? '').toLowerCase().includes(q))
      && (tab === 'all' || i.kind === tab)
    let recentKeys = readRecent().filter(k => items.some(i => i.key === k))
    if (!recentKeys.length) {
      // No history yet: the three most recently updated datasets stand in.
      recentKeys = items.filter(i => i.kind === 'dataset' && i.updated)
        .sort((a, b) => (b.updated ?? '').localeCompare(a.updated ?? '')).slice(0, 3).map(i => i.key)
    }
    // 5.20: a dataset made in the last day is what someone came to ask about,
    // even before they have asked about it once -- it joins Recent.
    const DAY = 24 * 3600_000
    const fresh = items.filter(i => i.kind === 'dataset' && i.updated && !recentKeys.includes(i.key)
      && Date.now() - Date.parse(i.updated) < DAY)
      .sort((a, b) => (b.updated ?? '').localeCompare(a.updated ?? '')).map(i => i.key)
    recentKeys = [...recentKeys, ...fresh].slice(0, 5)
    const recent = q || tab !== 'all' ? [] : recentKeys.map(k => items.find(i => i.key === k)!).filter(Boolean)
    const rest = items.filter(i => !recent.includes(i) && match(i))
    const out: { label: string; items: PickerItem[] }[] = []
    if (recent.length) out.push({ label: t('ask2.pick.recent'), items: recent })
    const ds = rest.filter(i => i.kind === 'dataset')
    const src = rest.filter(i => i.kind === 'source')
    if (ds.length) out.push({ label: t('ask2.pick.tabDatasets'), items: ds })
    if (src.length) out.push({ label: t('ask2.pick.tabConnections'), items: src })
    return out
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, query, tab, open])
  const flat = groups.flatMap(g => g.items)

  useEffect(() => { setActive(0) }, [query, tab, open])
  useEffect(() => {
    if (!open || inline) return
    const onDown = (e: MouseEvent) => {
      const n = e.target as Node
      if (!rootRef.current?.contains(n) && !popRef.current?.contains(n)) setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    requestAnimationFrame(() => inputRef.current?.focus())
    return () => document.removeEventListener('mousedown', onDown)
  }, [open, inline])
  useEffect(() => {
    document.getElementById(`${uid}-opt-${active}`)?.scrollIntoView?.({ block: 'nearest' })
  }, [active, uid])

  const close = () => {
    // Inline, Escape only clears the search: there is nothing to close.
    if (inline) { setQuery(''); return }
    setOpen(false); setQuery(''); setTab('all'); requestAnimationFrame(() => triggerRef.current?.focus())
  }
  const choose = (item: PickerItem) => {
    pushRecent(item.key)
    onChoose(item.key)
    close()
  }

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive(a => Math.min(a + 1, flat.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(a => Math.max(a - 1, 0)) }
    else if (e.key === 'Home') { e.preventDefault(); setActive(0) }
    else if (e.key === 'End') { e.preventDefault(); setActive(flat.length - 1) }
    else if (e.key === 'Enter') { e.preventDefault(); if (flat[active]) choose(flat[active]) }
    else if (e.key === 'Escape') { e.preventDefault(); close() }
  }

  const num = (n: number) => localDigits(n.toLocaleString('en-US'))
  const meta = (i: PickerItem) => {
    if (i.kind === 'source') return i.sourceType ? t('ask2.pick.liveType', { type: i.sourceType }) : t('ask2.pick.live')
    const parts: string[] = []
    if (i.rows != null) parts.push(t('ask2.pick.rows', { n: num(i.rows) }))
    if (i.cols != null) parts.push(t('ask2.pick.cols', { n: num(i.cols) }))
    return parts.join(' · ')
  }
  const updated = (i: PickerItem) => {
    const d = i.kind === 'dataset' ? shortDate(i.updated) : ''
    return d ? t('ask2.pick.updated', { date: localDigits(d) }) : ''
  }

  const Tile = ({ item, xs }: { item: PickerItem; xs?: boolean }) => (
    <span className={`dl-pick__tile dl-pick__tile--${item.kind}${xs ? ' dl-pick__tile--xs' : ''}`} aria-hidden>
      {item.kind === 'dataset' ? <Database size={xs ? 13 : 16} /> : <Plug size={xs ? 13 : 16} />}
    </span>
  )

  const counts = [
    nDatasets ? t('ask2.pick.datasets', { n: num(nDatasets) }) : '',
    nSources ? t('ask2.pick.connections', { n: num(nSources) }) : '',
    lastPick ? t('ask2.pick.try', { name: lastPick.name }) : '',
  ].filter(Boolean)

  const q = query.trim().toLowerCase()
  let n = -1
  const pop = open && (
    <div ref={popRef} className={inline ? 'dl-pick__panel' : `dl-pick__pop${pos.up ? ' dl-pick__pop--up' : ''}`}
      role={inline ? 'group' : 'dialog'} aria-label={t('ask2.pick.dialog')}
      data-placement={inline ? undefined : pos.up ? 'top' : 'bottom'}
      style={inline ? undefined : { ...pos.style, '--dl-pick-list-max': `${pos.listMax}px` } as CSSProperties}>
      <div className="dl-pick__search">
        <Search size={16} aria-hidden />
        <input ref={inputRef} value={query} onChange={e => setQuery(e.target.value)} onKeyDown={onKey}
          role="combobox" aria-expanded="true" aria-autocomplete="list"
          aria-controls={`${uid}-list`} aria-label={t('ask2.pick.search')}
          aria-activedescendant={flat[active] ? `${uid}-opt-${active}` : undefined}
          placeholder={t('ask2.pick.search')} autoComplete="off" />
        {nSources > 0 && nDatasets > 0 && (
          <div className="dl-pick__seg" role="tablist" aria-label={t('ask2.pick.dialog')}>
            {(['all', 'dataset', 'source'] as const).map(k => (
              <button key={k} type="button" role="tab" aria-selected={tab === k}
                onMouseDown={e => e.preventDefault()} onClick={() => { setTab(k); inputRef.current?.focus() }}>
                {t(k === 'all' ? 'ask2.pick.all' : k === 'dataset' ? 'ask2.pick.tabDatasets' : 'ask2.pick.tabConnections')}
              </button>
            ))}
          </div>
        )}
      </div>
      <div id={`${uid}-list`} role="listbox" aria-label={t('ask2.pick.dialog')} className="dl-pick__list">
        {flat.length === 0 && (
          <div className="dl-pick__none"><SearchX size={18} aria-hidden />
            <span>{q ? t('ask2.pick.noMatch', { q: query.trim() }) : t('ask.picker.none')}</span></div>
        )}
        {groups.map(g => (
          <div key={g.label} role="group" aria-label={g.label}>
            <div className="dl-pick__group" aria-hidden>{g.label}</div>
            {g.items.map(item => {
              n += 1
              const idx = n
              const up = updated(item)
              return (
                <div key={`${g.label}-${item.key}`} id={`${uid}-opt-${idx}`} role="option"
                  data-value={item.key}
                  aria-selected={item.key === value}
                  className={`dl-pick__opt${idx === active ? ' dl-pick__opt--active' : ''}`}
                  onMouseEnter={() => setActive(idx)}
                  onMouseDown={e => e.preventDefault()}
                  onClick={() => choose(item)}>
                  <Tile item={item} />
                  <span className="dl-pick__opt-text">
                    <span className="dl-pick__opt-name" dir="auto">{marked(item.name, q)}</span>
                    <span className="dl-pick__opt-meta">{meta(item)}</span>
                  </span>
                  {up && <span className="dl-pick__opt-up">{up}</span>}
                  {item.key === value && <Check size={15} className="dl-pick__check" aria-hidden />}
                </div>
              )
            })}
          </div>
        ))}
      </div>
      <div className="dl-pick__foot">
        <span aria-hidden><kbd>↑</kbd> <kbd>↓</kbd> {t('ask2.pick.move')}</span>
        <span aria-hidden><kbd>Enter</kbd> {t('ask2.pick.select')}</span>
        <span aria-hidden><kbd>Esc</kbd> {t(inline ? 'ask2.pick.clear' : 'ask2.pick.close')}</span>
        <Link to="/upload" className="dl-pick__upload"><Upload size={14} aria-hidden /> {t('ask2.pick.upload')}</Link>
      </div>
    </div>
  )

  if (inline) {
    return (
      <div ref={rootRef} className="dl-pick dl-pick--inline">
        <div className="dl-pick__step">
          <span className="dl-hero__stn">{t('ask2.step', { n: 1 })}</span>{t('ask2.step1')}
        </div>
        {pop}
      </div>
    )
  }

  return (
    <div ref={rootRef} className={`dl-pick dl-pick--${size}${open ? ' dl-pick--open' : ''}`}>
      {size === 'hero' ? (
        <button ref={triggerRef} type="button" className="dl-pick__trigger"
          aria-label={t('ask.scope')} aria-haspopup="listbox" aria-expanded={open} disabled={loading}
          onClick={() => setOpen(o => !o)}
          onKeyDown={e => { if (e.key === 'ArrowDown') { e.preventDefault(); setOpen(true) } }}>
          <span className="dl-pick__ic" aria-hidden><Database size={20} /></span>
          <span className="dl-pick__trigger-text">
            <span className="dl-pick__l1">{selected ? selected.name : t('ask2.pick.trigger')}</span>
            {counts.length > 0 && <span className="dl-pick__l2">{counts.join(' · ')}</span>}
          </span>
          <ChevronsUpDown size={18} className="dl-pick__chev" aria-hidden />
        </button>
      ) : (
        <button ref={triggerRef} type="button" className="dl-pick__chip"
          aria-label={t('ask.scope')} title={selected ? t('ask2.pick.change', { name: selected.name }) : undefined}
          aria-haspopup="listbox" aria-expanded={open} disabled={loading}
          onClick={() => setOpen(o => !o)}
          onKeyDown={e => { if (e.key === 'ArrowDown') { e.preventDefault(); setOpen(true) } }}>
          {selected ? <Tile item={selected} xs /> : <span className="dl-pick__tile dl-pick__tile--xs" aria-hidden><Search size={13} /></span>}
          <span className="dl-pick__chip-name" dir="auto">{selected ? selected.name : t('ask2.pick.trigger')}</span>
          <ChevronDown size={16} className="dl-pick__chev" aria-hidden />
        </button>
      )}
      {pop && createPortal(pop, document.body)}
    </div>
  )
}

/** The "rows · columns" (or connection type) line for an item, for the context row. */
export function useItemMeta() {
  const t = useT()
  return (i: PickerItem | undefined) => {
    if (!i) return ''
    if (i.kind === 'source') return i.sourceType ? t('ask2.pick.liveType', { type: i.sourceType }) : t('ask2.pick.live')
    const num = (n: number) => localDigits(n.toLocaleString('en-US'))
    return [i.rows != null ? t('ask2.pick.rows', { n: num(i.rows) }) : '', i.cols != null ? t('ask2.pick.cols', { n: num(i.cols) }) : '']
      .filter(Boolean).join(' · ')
  }
}
