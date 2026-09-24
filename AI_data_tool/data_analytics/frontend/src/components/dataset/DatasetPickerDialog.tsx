/**
 * One way to choose a dataset, used wherever a dataset is chosen.
 *
 * It replaces a raw <select> that listed every dataset in id order -- test
 * uploads named "kjhkjhkjhkjh" and "2" sitting beside real data, no search, and
 * nothing to tell a 2,000-row table from an empty one. SAS's Choose Data dialog
 * has search, recents and a preview; this has search, "recently used" first,
 * and each row's size, so the right table is recognisable at a glance.
 *
 * Recents are this viewer's own picks in this browser (localStorage) -- a
 * convenience, never a source of truth, so every access is guarded.
 */
import { useMemo, useState } from 'react'
import { Database, Search } from 'lucide-react'
import type { Dataset } from '../../services/api'
import { useModalDialog } from '../ui/useModalDialog'

const RECENT_KEY = 'datalytics:recent-datasets'
const RECENT_MAX = 5

export function readRecentDatasetIds(): number[] {
  try {
    const v = JSON.parse(localStorage.getItem(RECENT_KEY) ?? '[]')
    return Array.isArray(v) ? v.filter((x): x is number => typeof x === 'number') : []
  } catch { return [] }
}

export function rememberDataset(id: number): void {
  try {
    const next = [id, ...readRecentDatasetIds().filter(x => x !== id)].slice(0, RECENT_MAX)
    localStorage.setItem(RECENT_KEY, JSON.stringify(next))
  } catch { /* storage unavailable */ }
}

/** Recently used first (in use order), then everything else by name. */
export function orderDatasets(all: Dataset[], recentIds: number[], query: string): { recent: Dataset[]; rest: Dataset[] } {
  const q = query.trim().toLowerCase()
  const match = (d: Dataset) => !q || d.name.toLowerCase().includes(q) || (d.description ?? '').toLowerCase().includes(q)
  const byId = new Map(all.map(d => [d.id, d]))
  const recent = recentIds.map(id => byId.get(id)).filter((d): d is Dataset => !!d && match(d))
  const recentSet = new Set(recent.map(d => d.id))
  const rest = all.filter(d => !recentSet.has(d.id) && match(d))
    .sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base', numeric: true }))
  return { recent, rest }
}

export function sizeLabel(d: Dataset): string {
  // A DirectQuery dataset is never loaded, so its stored row count is 0 --
  // "0 rows" beside the one live table would read as the empty one.
  const rows = d.mode === 'directquery' ? 'live query'
    : typeof d.row_count === 'number' ? `${d.row_count.toLocaleString()} rows` : ''
  const cols = typeof d.col_count === 'number' ? `${d.col_count} columns` : ''
  return [rows, cols].filter(Boolean).join(' · ')
}

export default function DatasetPickerDialog({ datasets, onPick, onClose, title = 'Choose the data for this dashboard', excludeIds = [] }: {
  datasets: Dataset[]
  onPick: (d: Dataset) => void
  onClose: () => void
  title?: string
  excludeIds?: number[]
}) {
  const ref = useModalDialog<HTMLDivElement>(onClose)
  const [query, setQuery] = useState('')
  const available = useMemo(() => datasets.filter(d => !excludeIds.includes(d.id)), [datasets, excludeIds])
  const { recent, rest } = useMemo(() => orderDatasets(available, readRecentDatasetIds(), query), [available, query])

  const pick = (d: Dataset) => { rememberDataset(d.id); onPick(d) }
  const row = (d: Dataset) => (
    <li key={d.id}>
      <button type="button" onClick={() => pick(d)}
        style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', textAlign: 'start', padding: '8px 10px',
          background: 'none', border: 'none', borderRadius: 6, cursor: 'pointer', color: 'var(--text)', font: 'inherit' }}
        onMouseEnter={e => { e.currentTarget.style.background = 'var(--surface2)' }}
        onMouseLeave={e => { e.currentTarget.style.background = 'none' }}>
        <Database size={16} style={{ color: 'var(--accent)', flexShrink: 0 }} />
        <span style={{ flex: 1, minWidth: 0 }}>
          <span style={{ display: 'block', fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.name}</span>
          {d.description && <span style={{ display: 'block', fontSize: 11, color: 'var(--muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.description}</span>}
        </span>
        <span style={{ fontSize: 11, color: 'var(--muted)', flexShrink: 0 }}>{sizeLabel(d)}</span>
      </button>
    </li>
  )
  const heading = (text: string) => (
    <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', margin: '10px 10px 4px' }}>{text}</div>
  )

  return (
    <div onClick={onClose}
      style={{ position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0,0,0,.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
      <div ref={ref} role="dialog" aria-modal="true" aria-label={title} onClick={e => e.stopPropagation()}
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', width: 'min(560px, 100%)',
          maxHeight: 'min(620px, 90vh)', display: 'flex', flexDirection: 'column', boxShadow: '0 12px 40px rgba(0,0,0,.25)' }}>
        <div style={{ padding: '16px 16px 8px' }}>
          <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 10 }}>{title}</div>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, border: '1px solid var(--border)', borderRadius: 6, padding: '6px 10px', background: 'var(--surface2)' }}>
            <Search size={14} style={{ color: 'var(--muted)' }} />
            <input autoFocus value={query} onChange={e => setQuery(e.target.value)} placeholder="Search datasets…" aria-label="Search datasets"
              style={{ border: 'none', background: 'transparent', outline: 'none', flex: 1, font: 'inherit', color: 'var(--text)' }} />
          </label>
        </div>
        <div style={{ overflowY: 'auto', padding: '0 6px 8px' }}>
          {recent.length > 0 && <>{heading('Recently used')}<ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>{recent.map(row)}</ul></>}
          {rest.length > 0 && <>{heading(recent.length ? 'All datasets' : `${rest.length} dataset${rest.length === 1 ? '' : 's'}`)}<ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>{rest.map(row)}</ul></>}
          {recent.length + rest.length === 0 && (
            <p style={{ padding: 16, color: 'var(--muted)', fontSize: 13 }}>
              {available.length === 0 ? 'There are no datasets yet. Upload a file or connect a database first.' : `Nothing matches "${query}".`}
            </p>
          )}
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, padding: '10px 16px', borderTop: '1px solid var(--border)' }}>
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>Not now — I'll add data later</button>
        </div>
      </div>
    </div>
  )
}
