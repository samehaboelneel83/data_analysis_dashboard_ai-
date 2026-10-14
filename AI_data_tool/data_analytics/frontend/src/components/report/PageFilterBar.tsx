import { useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent } from 'react'
import { ArrowLeft, Calendar, Check, Hash, ListFilter, Search, Type, X } from 'lucide-react'
import { useT, type MessageKey } from '../../i18n'
import { widgetDataApi } from '../../services/api'
import {
  describePageFilter, isActive, newFilterId,
  type ColumnKind, type PageFilter,
} from '../../lib/pageFilters'

/**
 * The page filter bar: "+ Filter" and one chip per filter, in the row above
 * the page. Filters here apply to every chart on the page that has the column.
 *
 *   + Filter  →  pick a column  →  a control that fits it:
 *     number  a from/to range (with a two-handle slider over the data's range)
 *     date    a from/to date range
 *     text    pick values (searchable, with counts) or "contains"
 *
 * The values, ranges and counts come from the same widget-data query the
 * charts use, so they work on every source (files, live databases) and
 * respect the viewer's row rules.
 */

export interface PageFilterColumn {
  name: string
  kind: ColumnKind
  datasetId: number
  datasetName?: string
}

const VALUE_LIMIT = 200
const SEARCH_DEBOUNCE_MS = 250

const KIND_ICON = { number: Hash, date: Calendar, text: Type } as const

type Draft = PageFilter

function defaultDraft(col: PageFilterColumn): Draft {
  const id = newFilterId()
  if (col.kind === 'number') return { id, column: col.name, kind: 'range', from: null, to: null }
  if (col.kind === 'date') return { id, column: col.name, kind: 'dates', from: null, to: null }
  return { id, column: col.name, kind: 'values', values: [] }
}

const toNum = (v: string): number | null => {
  if (v.trim() === '') return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}
const day = (v: unknown): string => (typeof v === 'string' ? v.slice(0, 10) : '')

export default function PageFilterBar({ columns, filters, onChange, reportId }: {
  columns: PageFilterColumn[]
  filters: PageFilter[]
  onChange: (next: PageFilter[]) => void
  reportId?: number
}) {
  const t = useT()
  const tr = (k: string, v?: Record<string, string | number>) => t(k as MessageKey, v)
  const [open, setOpen] = useState<null | { editing: string | null; column: PageFilterColumn | null; draft: Draft | null }>(null)
  const rootRef = useRef<HTMLDivElement>(null)
  // The popup gets the room between the bar and the bottom of the window; its
  // middle scrolls, so Apply is always on screen, even in a short window.
  const [room, setRoom] = useState<number | null>(null)
  useLayoutEffect(() => {
    if (!open) return
    const measure = () => {
      const r = rootRef.current?.getBoundingClientRect()
      if (r) setRoom(Math.max(220, Math.floor(window.innerHeight - r.bottom - 16)))
    }
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [open])

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(null)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  const colByName = useMemo(() => new Map(columns.map(c => [c.name, c])), [columns])
  const active = filters.filter(isActive)

  const startNew = () => setOpen({ editing: null, column: null, draft: null })
  const edit = (f: PageFilter) => {
    const col = colByName.get(f.column)
    if (!col) return
    setOpen({ editing: f.id, column: col, draft: { ...f } as Draft })
  }
  const remove = (id: string) => onChange(filters.filter(f => f.id !== id))
  const apply = (d: Draft) => {
    const exists = filters.some(f => f.id === d.id)
    const next = !isActive(d) ? filters.filter(f => f.id !== d.id)
      : exists ? filters.map(f => (f.id === d.id ? d : f)) : [...filters, d]
    onChange(next)
    setOpen(null)
  }

  if (columns.length === 0) return null

  return (
    <div ref={rootRef} className="dl-pf" role="group" aria-label={tr('pf.label')}>
      <button type="button" className="dl-pf__add" data-testid="page-filter-add"
        aria-haspopup="dialog" aria-expanded={!!open && !open.editing}
        title={tr('pf.addTitle')} onClick={() => (open ? setOpen(null) : startNew())}>
        <ListFilter size={14} aria-hidden />
        <span>{tr('pf.add')}</span>
        {active.length > 0 && <span className="dl-pf__count">{active.length}</span>}
      </button>

      {active.map(f => (
        <span key={f.id} className="dl-pf__chip" data-testid="page-filter-chip">
          <button type="button" className="dl-pf__chip-text" title={tr('pf.editTitle')}
            onClick={() => edit(f)}>{describePageFilter(f, tr)}</button>
          <button type="button" className="dl-pf__chip-x" aria-label={`${tr('pf.remove')}: ${describePageFilter(f, tr)}`}
            onClick={() => remove(f.id)}><X size={12} aria-hidden /></button>
        </span>
      ))}
      {active.length > 1 && (
        <button type="button" className="dl-pf__clear" onClick={() => onChange([])}>{tr('pf.clear')}</button>
      )}

      {open && (
        <div className="dl-pf__pop" role="dialog" aria-label={tr('pf.label')}
          style={room ? ({ '--pf-room': `${room}px` } as CSSProperties) : undefined}
          onKeyDown={(e: KeyboardEvent) => { if (e.key === 'Escape') { e.stopPropagation(); setOpen(null) } }}>
          {!open.column ? (
            <ColumnStep columns={columns} tr={tr}
              onPick={col => setOpen({ editing: null, column: col, draft: defaultDraft(col) })} />
          ) : (
            <ValueStep column={open.column} draft={open.draft!} reportId={reportId} tr={tr}
              isNew={!open.editing}
              onBack={() => setOpen({ editing: null, column: null, draft: null })}
              onDraft={d => setOpen(o => (o ? { ...o, draft: d } : o))}
              onApply={apply}
              onRemove={open.editing ? () => { remove(open.editing!); setOpen(null) } : undefined}
              onCancel={() => setOpen(null)} />
          )}
        </div>
      )}
    </div>
  )
}

type Tr = (k: string, v?: Record<string, string | number>) => string

function ColumnStep({ columns, onPick, tr }: { columns: PageFilterColumn[]; onPick: (c: PageFilterColumn) => void; tr: Tr }) {
  const [q, setQ] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  useEffect(() => { requestAnimationFrame(() => inputRef.current?.focus()) }, [])
  const shown = columns.filter(c => c.name.toLowerCase().includes(q.trim().toLowerCase()))
  const multi = new Set(columns.map(c => c.datasetId)).size > 1
  return (
    <>
      <div className="dl-pf__head">{tr('pf.chooseColumn')}</div>
      <label className="dl-pf__search">
        <Search size={14} aria-hidden />
        <input ref={inputRef} value={q} onChange={e => setQ(e.target.value)} placeholder={tr('pf.searchColumns')}
          aria-label={tr('pf.searchColumns')}
          onKeyDown={e => { if (e.key === 'Enter' && shown[0]) onPick(shown[0]) }} />
      </label>
      <div className="dl-pf__list" role="listbox" aria-label={tr('pf.chooseColumn')}>
        {shown.length === 0 && <div className="dl-pf__empty">{tr('pf.noColumns')}</div>}
        {shown.map(c => {
          const Icon = KIND_ICON[c.kind]
          return (
            <button key={`${c.datasetId}:${c.name}`} type="button" role="option" aria-selected={false}
              className="dl-pf__opt" onClick={() => onPick(c)}>
              <span className={`dl-pf__kind dl-pf__kind--${c.kind}`} aria-hidden><Icon size={13} /></span>
              <span className="dl-pf__opt-name" dir="auto">{c.name}</span>
              <span className="dl-pf__opt-meta">{multi && c.datasetName ? c.datasetName : tr(`pf.kind.${c.kind}`)}</span>
            </button>
          )
        })}
      </div>
    </>
  )
}

function ValueStep({ column, draft, reportId, isNew, onBack, onDraft, onApply, onRemove, onCancel, tr }: {
  column: PageFilterColumn; draft: Draft; reportId?: number; isNew: boolean
  onBack: () => void; onDraft: (d: Draft) => void; onApply: (d: Draft) => void
  onRemove?: () => void; onCancel: () => void; tr: Tr
}) {
  const Icon = KIND_ICON[column.kind]
  return (
    <>
      <div className="dl-pf__head dl-pf__head--col">
        {isNew && (
          <button type="button" className="dl-pf__back" aria-label={tr('pf.back')} onClick={onBack}>
            <ArrowLeft size={14} className="flip-rtl" aria-hidden />
          </button>
        )}
        <span className={`dl-pf__kind dl-pf__kind--${column.kind}`} aria-hidden><Icon size={13} /></span>
        <span className="dl-pf__col" dir="auto">{column.name}</span>
      </div>
      <div className="dl-pf__body">
        {draft.kind === 'range' && <RangeControl column={column} draft={draft} reportId={reportId} onDraft={onDraft} tr={tr} />}
        {draft.kind === 'dates' && <DateControl column={column} draft={draft} reportId={reportId} onDraft={onDraft} tr={tr} />}
        {(draft.kind === 'values' || draft.kind === 'contains') && (
          <TextControl column={column} draft={draft} reportId={reportId} onDraft={onDraft} tr={tr} />
        )}
        <p className="dl-pf__note">{tr('pf.appliesNote')}</p>
      </div>
      <div className="dl-pf__foot">
        {onRemove && <button type="button" className="dl-pf__btn dl-pf__btn--danger" onClick={onRemove}>{tr('pf.remove')}</button>}
        <span className="dl-pf__grow" />
        <button type="button" className="dl-pf__btn" onClick={onCancel}>{tr('pf.cancel')}</button>
        <button type="button" className="dl-pf__btn dl-pf__btn--primary" data-testid="page-filter-apply"
          onClick={() => onApply(draft)}>{tr('pf.apply')}</button>
      </div>
    </>
  )
}

/**
 * Where the column's data starts and ends -- over ALL rows the viewer may see.
 *
 * Asked as an ordinary chart grouped by the column: that path aggregates at
 * the source (no 10,000-row sample, unlike a KPI) and applies the viewer's
 * row rules. A column with few values comes back exact; a big one comes back
 * in the auto-bin's rounded groups, so the range is "about" (0 – 6,800 for
 * prices that run 3.50 – 6,735). A server-side MIN/MAX would be exact, but it
 * would also reveal values from rows a row rule hides.
 */
function useExtent(column: PageFilterColumn, reportId?: number) {
  const [ext, setExt] = useState<{ min: unknown; max: unknown; approx: boolean } | null>(null)
  useEffect(() => {
    let alive = true
    widgetDataApi.query(column.datasetId, { dimension: column.name, aggregation: 'count' }, [], 'bar', { reportId })
      .then((d: any) => {
        if (!alive) return
        const rows: any[] = Array.isArray(d?.rows) ? d.rows.filter((r: any) => r && r.name != null && !r.other) : []
        const grouped = !!d?.binning?.grouped
        if (column.kind === 'date') {
          const starts = rows.map(r => String(r.bin_start ?? r.name)).filter(Boolean).sort()
          const ends = rows.map(r => {
            if (r.bin_end == null) return String(r.name)
            // bin_end is the NEXT period's first moment: the day before it is the last one in the data.
            const e = new Date(String(r.bin_end).replace(' ', 'T'))
            return isNaN(e.getTime()) ? String(r.bin_end) : new Date(e.getTime() - 86400000).toISOString()
          }).filter(Boolean).sort()
          setExt({ min: starts[0] ?? null, max: ends[ends.length - 1] ?? null, approx: grouped })
        } else {
          const nums = rows.flatMap(r => (r.bin_start != null ? [Number(r.bin_start), Number(r.bin_end)] : [Number(r.name)]))
            .filter(n => Number.isFinite(n))
          setExt(nums.length ? { min: Math.min(...nums), max: Math.max(...nums), approx: grouped } : { min: null, max: null, approx: false })
        }
      })
      .catch(() => { if (alive) setExt({ min: null, max: null, approx: false }) })
    return () => { alive = false }
  }, [column.datasetId, column.name, column.kind, reportId])
  return ext
}

const fmt = (n: number) => n.toLocaleString('en-US', { maximumFractionDigits: 4 })

function RangeControl({ column, draft, reportId, onDraft, tr }: {
  column: PageFilterColumn; draft: Extract<Draft, { kind: 'range' }>; reportId?: number
  onDraft: (d: Draft) => void; tr: Tr
}) {
  const ext = useExtent(column, reportId)
  const lo = typeof ext?.min === 'number' ? ext.min : null
  const hi = typeof ext?.max === 'number' ? ext.max : null
  const [fromText, setFromText] = useState(draft.from != null ? String(draft.from) : '')
  const [toText, setToText] = useState(draft.to != null ? String(draft.to) : '')
  const set = (from: string, to: string) => {
    setFromText(from); setToText(to)
    onDraft({ ...draft, from: toNum(from), to: toNum(to) })
  }
  const span = lo != null && hi != null && hi > lo
  const step = span ? (Number.isInteger(lo) && Number.isInteger(hi) ? 1 : (hi! - lo!) / 1000) : 1
  const fromV = toNum(fromText) ?? lo ?? 0
  const toV = toNum(toText) ?? hi ?? 0
  const bad = draft.from != null && draft.to != null && draft.from > draft.to
  return (
    <div className="dl-pf__range">
      <div className="dl-pf__pair">
        <label>{tr('pf.from')}
          <input type="number" inputMode="decimal" value={fromText} placeholder={lo != null ? fmt(lo) : ''}
            aria-label={tr('pf.from')} data-testid="page-filter-from"
            onChange={e => set(e.target.value, toText)} />
        </label>
        <span aria-hidden className="dl-pf__dash">–</span>
        <label>{tr('pf.to')}
          <input type="number" inputMode="decimal" value={toText} placeholder={hi != null ? fmt(hi) : ''}
            aria-label={tr('pf.to')} data-testid="page-filter-to"
            onChange={e => set(fromText, e.target.value)} />
        </label>
      </div>
      {span && (
        <div className="dl-pf__slider" aria-hidden>
          <div className="dl-pf__track">
            <span className="dl-pf__fill" style={{
              insetInlineStart: `${((Math.max(lo!, Math.min(fromV, hi!)) - lo!) / (hi! - lo!)) * 100}%`,
              insetInlineEnd: `${100 - ((Math.max(lo!, Math.min(toV, hi!)) - lo!) / (hi! - lo!)) * 100}%`,
            }} />
          </div>
          <input type="range" tabIndex={-1} min={lo!} max={hi!} step={step} value={Math.min(fromV, toV)}
            onChange={e => set(e.target.value === String(lo) ? '' : e.target.value, toText)} />
          <input type="range" tabIndex={-1} min={lo!} max={hi!} step={step} value={Math.max(fromV, toV)}
            onChange={e => set(fromText, e.target.value === String(hi) ? '' : e.target.value)} />
        </div>
      )}
      <div className="dl-pf__hint">
        {bad ? <span className="dl-pf__warn">{tr('pf.badRange')}</span>
          : ext == null ? tr('pf.loading')
          : lo != null && hi != null ? tr(ext.approx ? 'pf.inDataAbout' : 'pf.inData', { min: fmt(lo), max: fmt(hi) }) : ''}
      </div>
    </div>
  )
}

function DateControl({ column, draft, reportId, onDraft, tr }: {
  column: PageFilterColumn; draft: Extract<Draft, { kind: 'dates' }>; reportId?: number
  onDraft: (d: Draft) => void; tr: Tr
}) {
  const ext = useExtent(column, reportId)
  const lo = day(ext?.min), hi = day(ext?.max)
  const bad = !!draft.from && !!draft.to && draft.from > draft.to
  return (
    <div className="dl-pf__range">
      <div className="dl-pf__pair">
        <label>{tr('pf.from')}
          <input type="date" value={draft.from ?? ''} min={lo || undefined} max={hi || undefined}
            aria-label={tr('pf.from')} data-testid="page-filter-from"
            onChange={e => onDraft({ ...draft, from: e.target.value || null })} />
        </label>
        <span aria-hidden className="dl-pf__dash">–</span>
        <label>{tr('pf.to')}
          <input type="date" value={draft.to ?? ''} min={lo || undefined} max={hi || undefined}
            aria-label={tr('pf.to')} data-testid="page-filter-to"
            onChange={e => onDraft({ ...draft, to: e.target.value || null })} />
        </label>
      </div>
      <div className="dl-pf__hint">
        {bad ? <span className="dl-pf__warn">{tr('pf.badRange')}</span>
          : ext == null ? tr('pf.loading')
          : lo && hi ? tr(ext!.approx ? 'pf.inDataAbout' : 'pf.inData', { min: lo, max: hi }) : ''}
      </div>
    </div>
  )
}

function TextControl({ column, draft, reportId, onDraft, tr }: {
  column: PageFilterColumn; draft: Extract<Draft, { kind: 'values' | 'contains' }>; reportId?: number
  onDraft: (d: Draft) => void; tr: Tr
}) {
  const mode = draft.kind
  const picked = draft.kind === 'values' ? draft.values : []
  const [q, setQ] = useState('')
  const [rows, setRows] = useState<{ name: string; value: number | null }[] | null>(null)

  // Values with their counts, largest first; typing narrows on the server, so
  // a column with 100,000 distinct ids is searchable, not a 100,000-row list.
  useEffect(() => {
    if (mode !== 'values') return
    let alive = true
    setRows(null)
    const timer = setTimeout(() => {
      const filters = q.trim() ? [{ column: column.name, op: 'like', value: q.trim() }] : []
      widgetDataApi.query(column.datasetId, { dimension: column.name, aggregation: 'count', filters }, [], 'slicer', { reportId })
        .then((d: any) => {
          if (!alive) return
          const got = Array.isArray(d?.rows) ? d.rows : []
          setRows(got.slice(0, VALUE_LIMIT).map((r: any) => ({ name: String(r.name), value: typeof r.value === 'number' ? r.value : null })))
        })
        .catch(() => { if (alive) setRows([]) })
    }, q ? SEARCH_DEBOUNCE_MS : 0)
    return () => { alive = false; clearTimeout(timer) }
  }, [mode, q, column.datasetId, column.name, reportId])

  const toggle = (v: string) => {
    const next = picked.includes(v) ? picked.filter(x => x !== v) : [...picked, v]
    onDraft({ id: draft.id, column: draft.column, kind: 'values', values: next })
  }
  // Picked values stay visible (and first) even when the search hides them.
  const list = rows ? [
    ...picked.filter(p => !rows.some(r => r.name === p)).map(p => ({ name: p, value: null as number | null })),
    ...rows,
  ] : null

  return (
    <div className="dl-pf__text">
      <div role="group" className="dl-seg dl-pf__modes" aria-label={tr('pf.textMode')}>
        <button type="button" aria-pressed={mode === 'values'}
          className={`dl-seg__btn${mode === 'values' ? ' dl-seg__btn--on' : ''}`}
          onClick={() => onDraft({ id: draft.id, column: draft.column, kind: 'values', values: [] })}>{tr('pf.pick')}</button>
        <button type="button" aria-pressed={mode === 'contains'}
          className={`dl-seg__btn${mode === 'contains' ? ' dl-seg__btn--on' : ''}`}
          onClick={() => onDraft({ id: draft.id, column: draft.column, kind: 'contains', text: '' })}>{tr('pf.contains')}</button>
      </div>
      {mode === 'contains' ? (
        <input className="dl-pf__input" autoFocus value={draft.kind === 'contains' ? draft.text : ''}
          placeholder={tr('pf.textHint')} aria-label={tr('pf.contains')} data-testid="page-filter-contains"
          onChange={e => onDraft({ id: draft.id, column: draft.column, kind: 'contains', text: e.target.value })} />
      ) : (
        <>
          <label className="dl-pf__search">
            <Search size={14} aria-hidden />
            <input value={q} onChange={e => setQ(e.target.value)} placeholder={tr('pf.searchValues')}
              aria-label={tr('pf.searchValues')} />
          </label>
          <div className="dl-pf__list dl-pf__list--values" role="listbox" aria-multiselectable="true" aria-label={column.name}>
            {list == null && <div className="dl-pf__empty">{tr('pf.loading')}</div>}
            {list && list.length === 0 && <div className="dl-pf__empty">{tr('pf.noValues')}</div>}
            {list?.map(r => {
              const on = picked.includes(r.name)
              return (
                <button key={r.name} type="button" role="option" aria-selected={on}
                  className={`dl-pf__val${on ? ' dl-pf__val--on' : ''}`} onClick={() => toggle(r.name)}>
                  <span className="dl-pf__box" aria-hidden>{on && <Check size={11} />}</span>
                  <span className="dl-pf__opt-name" dir="auto">{r.name}</span>
                  {r.value != null && <span className="dl-pf__opt-meta">{r.value.toLocaleString('en-US')}</span>}
                </button>
              )
            })}
          </div>
          <div className="dl-pf__hint">
            {picked.length > 0 ? tr('pf.selected', { n: picked.length }) : ''}
            {rows && rows.length >= VALUE_LIMIT ? <span> · {tr('pf.moreValues', { n: VALUE_LIMIT })}</span> : null}
          </div>
        </>
      )}
    </div>
  )
}

