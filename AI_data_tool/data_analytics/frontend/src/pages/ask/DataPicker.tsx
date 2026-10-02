import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent } from 'react'
import { Link } from 'react-router-dom'
import { Check, ChevronDown, Database, Plug, Search, Upload } from 'lucide-react'
import { useT } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'
import { fmtDate } from './dates'

/**
 * Step 1 of Ask AI: choose the data. A searchable list instead of a native
 * <select> -- each row says what the thing IS (dataset or live connection),
 * how big it is, and how fresh -- so the choice is made on facts, not names.
 *
 * Keyboard: the trigger opens it (Enter/Space/ArrowDown); in the search box
 * ArrowUp/Down move, Enter chooses, Escape closes and returns focus. The
 * search input is the ARIA combobox and owns the listbox via
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

/** Search row + footer + gaps around the list: the popup's height minus its list. */
const POP_CHROME = 110
const LIST_MAX = 340
const LIST_MIN = 120
/** Below this much list room, a roomier side above wins. */
const LIST_COMFY = 200
const EDGE = 12

/** The box the popup can be seen in: the nearest ancestor that clips or
 *  scrolls (the app's content pane), else the window. The popup is absolutely
 *  positioned INSIDE that pane, so the window's height is the wrong measure. */
function visibleBounds(el: HTMLElement): { top: number; bottom: number } {
  for (let p = el.parentElement; p; p = p.parentElement) {
    const o = getComputedStyle(p).overflowY
    if (o === 'auto' || o === 'scroll' || o === 'hidden') {
      const r = p.getBoundingClientRect()
      return { top: Math.max(r.top, 0), bottom: Math.min(r.bottom, window.innerHeight) }
    }
  }
  return { top: 0, bottom: window.innerHeight }
}

/**
 * Where the popup opens. Downward is the default; it flips UP only when the
 * list would not fit below and there is more room above -- the hero picker
 * sits low on the page, and opening it downward pushed the list off-screen so
 * the user had to scroll to see what they were choosing from. The list's
 * max-height then shrinks to the side it opened on, so it never overflows.
 */
export function placePopup(trigger: DOMRect, bounds: { top: number; bottom: number }) {
  const below = bounds.bottom - trigger.bottom - EDGE
  const above = trigger.top - bounds.top - EDGE
  // Down is the natural direction: keep it whenever a usable list fits
  // (LIST_COMFY rows' worth), so the list does not jump up over the headline.
  const up = below < POP_CHROME + LIST_COMFY && above > below
  const room = (up ? above : below) - POP_CHROME
  return { up, listMax: Math.max(LIST_MIN, Math.min(LIST_MAX, Math.floor(room))) }
}

function shortDate(iso?: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  return isNaN(d.getTime()) ? '' : fmtDate(d, { month: 'short', day: 'numeric', year: 'numeric' })
}

export default function DataPicker({ items, value, onChoose, size = 'hero', loading }: {
  items: PickerItem[]
  value: string
  onChoose: (key: string) => void
  size?: 'hero' | 'compact'
  loading?: boolean
}) {
  const t = useT()
  const uid = useId().replace(/:/g, '')
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const rootRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const [place, setPlace] = useState<{ up: boolean; listMax: number }>({ up: false, listMax: LIST_MAX })

  // Measured before paint, so the popup never flashes on the wrong side.
  useLayoutEffect(() => {
    if (!open || !triggerRef.current) return
    const measure = () => {
      const tr = triggerRef.current
      if (tr) setPlace(placePopup(tr.getBoundingClientRect(), visibleBounds(tr)))
    }
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [open])

  const selected = items.find(i => i.key === value)

  // Recent first (what this person picked last), then datasets, then connections.
  const groups = useMemo(() => {
    const q = query.trim().toLowerCase()
    const match = (i: PickerItem) => !q || i.name.toLowerCase().includes(q)
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
    const recent = q ? [] : recentKeys.map(k => items.find(i => i.key === k)!).filter(Boolean)
    const rest = items.filter(i => !recent.includes(i) && match(i))
    const out: { label: string; items: PickerItem[] }[] = []
    if (recent.length) out.push({ label: t('ask.picker.recent'), items: recent })
    const ds = rest.filter(i => i.kind === 'dataset')
    const src = rest.filter(i => i.kind === 'source')
    if (ds.length) out.push({ label: t('nav.datasets'), items: ds })
    if (src.length) out.push({ label: t('ask.liveConnections'), items: src })
    return out
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, query, open])
  const flat = groups.flatMap(g => g.items)

  useEffect(() => { setActive(0) }, [query, open])
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    requestAnimationFrame(() => inputRef.current?.focus())
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])
  useEffect(() => {
    document.getElementById(`${uid}-opt-${active}`)?.scrollIntoView?.({ block: 'nearest' })
  }, [active, uid])

  const choose = (item: PickerItem) => {
    pushRecent(item.key)
    onChoose(item.key)
    setOpen(false)
    setQuery('')
    requestAnimationFrame(() => triggerRef.current?.focus())
  }

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive(a => Math.min(a + 1, flat.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(a => Math.max(a - 1, 0)) }
    else if (e.key === 'Home') { e.preventDefault(); setActive(0) }
    else if (e.key === 'End') { e.preventDefault(); setActive(flat.length - 1) }
    else if (e.key === 'Enter') { e.preventDefault(); if (flat[active]) choose(flat[active]) }
    else if (e.key === 'Escape') { e.preventDefault(); setOpen(false); triggerRef.current?.focus() }
  }

  const meta = (i: PickerItem) => {
    const parts: string[] = []
    if (i.kind === 'dataset') {
      if (i.rows != null) parts.push(t('ask.picker.rows', { n: localDigits(i.rows.toLocaleString('en-US')) }))
      if (i.cols != null) parts.push(t('ask.picker.cols', { n: localDigits(String(i.cols)) }))
    } else {
      parts.push(i.sourceType ? `${i.sourceType} · ${t('ask.picker.live')}` : t('ask.picker.live'))
    }
    const d = shortDate(i.updated)
    if (d) parts.push(t('ask.picker.updated', { date: localDigits(d) }))
    return parts.join(' · ')
  }

  const Icon = ({ item }: { item: PickerItem }) => (
    <span className={`dl-pick__icon dl-pick__icon--${item.kind}`} aria-hidden>
      {item.kind === 'dataset' ? <Database size={16} /> : <Plug size={16} />}
    </span>
  )

  let n = -1
  return (
    <div ref={rootRef} className={`dl-pick dl-pick--${size}${open ? ' dl-pick--open' : ''}`}>
      <button ref={triggerRef} type="button" className="dl-pick__trigger"
        aria-label={t('ask.scope')} aria-haspopup="listbox" aria-expanded={open}
        disabled={loading}
        onClick={() => setOpen(o => !o)}
        onKeyDown={e => { if (e.key === 'ArrowDown') { e.preventDefault(); setOpen(true) } }}>
        {selected ? <Icon item={selected} /> : <span className="dl-pick__icon dl-pick__icon--empty" aria-hidden><Search size={16} /></span>}
        <span className="dl-pick__trigger-text">
          <span className="dl-pick__trigger-name">{selected ? selected.name : t('ask.choose')}</span>
          {selected && size === 'hero' && <span className="dl-pick__trigger-meta">{meta(selected)}</span>}
        </span>
        <ChevronDown size={16} className="dl-pick__chev" aria-hidden />
      </button>

      {open && (
        <div className={`dl-pick__pop${place.up ? ' dl-pick__pop--up' : ''}`}
          data-placement={place.up ? 'top' : 'bottom'}
          style={{ '--dl-pick-list-max': `${place.listMax}px` } as CSSProperties}>
          <div className="dl-pick__search">
            <Search size={15} aria-hidden />
            <input ref={inputRef} value={query} onChange={e => setQuery(e.target.value)} onKeyDown={onKey}
              role="combobox" aria-expanded="true" aria-autocomplete="list"
              aria-controls={`${uid}-list`} aria-label={t('ask.picker.search')}
              aria-activedescendant={flat[active] ? `${uid}-opt-${active}` : undefined}
              placeholder={t('ask.picker.search')} />
          </div>
          <div id={`${uid}-list`} role="listbox" aria-label={t('ask.scope')} className="dl-pick__list">
            {flat.length === 0 && <div className="dl-pick__none">{t('ask.picker.none')}</div>}
            {groups.map(g => (
              <div key={g.label} role="group" aria-label={g.label}>
                <div className="dl-pick__group" aria-hidden>{g.label}</div>
                {g.items.map(item => {
                  n += 1
                  const idx = n
                  return (
                    <div key={`${g.label}-${item.key}`} id={`${uid}-opt-${idx}`} role="option"
                      data-value={item.key}
                      aria-selected={item.key === value}
                      className={`dl-pick__opt${idx === active ? ' dl-pick__opt--active' : ''}`}
                      onMouseEnter={() => setActive(idx)}
                      onMouseDown={e => e.preventDefault()}
                      onClick={() => choose(item)}>
                      <Icon item={item} />
                      <span className="dl-pick__opt-text">
                        <span className="dl-pick__opt-name" dir="auto">{item.name}</span>
                        <span className="dl-pick__opt-meta">{meta(item)}</span>
                      </span>
                      {item.key === value && <Check size={15} className="dl-pick__check" aria-hidden />}
                    </div>
                  )
                })}
              </div>
            ))}
          </div>
          <div className="dl-pick__foot">
            <span className="dl-pick__keys" aria-hidden>
              <kbd>↑</kbd><kbd>↓</kbd> {t('ask.picker.move')} <kbd>Enter</kbd> {t('ask.picker.pick')} <kbd>Esc</kbd> {t('ask.picker.close')}
            </span>
            <Link to="/upload" className="dl-pick__upload"><Upload size={13} aria-hidden /> {t('ask.uploadDataset')}</Link>
          </div>
        </div>
      )}
    </div>
  )
}
