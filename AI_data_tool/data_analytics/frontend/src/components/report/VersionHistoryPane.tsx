import { useEffect, useState } from 'react'
import { Bot, History, RotateCcw } from 'lucide-react'
import toast from 'react-hot-toast'
import { reportsApi } from '../../services/api'

/**
 * Version history for the open report (R2 of the competitive assessment).
 *
 * The revision counter always detected concurrent edits; this is the way
 * back. Every edit — from the GUI or the page copilot — leaves a restorable
 * content snapshot, listed newest first. Restore replaces the report's pages
 * and widgets with a chosen version's, and is itself captured first, so it
 * can be undone in turn.
 *
 * Deliberately narrow: it restores CONTENT (charts, layout, theme), never
 * identity (name, sharing, publish state) — the backend enforces that, and
 * the confirm copy says so, because "go back to Tuesday" must not also
 * un-share the dashboard.
 */
export interface VersionHistoryPaneProps {
  reportId: number
  /** The report's current revision, to mark "current" in the list. */
  currentRevision: number | null
  /** Reload the builder after a restore lands. */
  onRestored: () => void | Promise<void>
}

interface VersionRow {
  id: number
  revision: number
  created_at: string | null
  created_by: string | null
  pages: number
  widgets: number
  via?: string | null
  note?: string | null
}

function when(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit' })
}

export default function VersionHistoryPane({ reportId, currentRevision, onRestored }: VersionHistoryPaneProps) {
  const [rows, setRows] = useState<VersionRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [restoring, setRestoring] = useState<number | null>(null)

  const load = () => {
    setError(null)
    reportsApi.versions(reportId)
      .then(setRows)
      .catch(() => setError('Could not load version history.'))
  }
  useEffect(load, [reportId])

  const restore = async (v: VersionRow) => {
    if (!window.confirm(
      `Restore revision ${v.revision}? The current charts and layout are ` +
      `saved as a new version first, so you can undo this. The report's name ` +
      `and sharing are not changed.`)) return
    setRestoring(v.id)
    try {
      const got = await reportsApi.restoreVersion(reportId, v.id)
      toast.success(`Restored revision ${got.restored_revision}`)
      await onRestored()
      load()
    } catch {
      toast.error('Restore failed')
    } finally {
      setRestoring(null)
    }
  }

  const label: React.CSSProperties = { fontSize: 11, fontWeight: 700,
    color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em' }

  return (
    <div style={{ padding: '14px 14px 0', display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <History size={13} aria-hidden style={{ color: 'var(--muted)' }} />
        <span style={label}>Version history</span>
      </div>

      {error && <p role="alert" style={{ fontSize: 12, color: 'var(--danger)', margin: 0 }}>{error}</p>}
      {rows && rows.length === 0 && (
        <p style={{ fontSize: 12, color: 'var(--muted)', margin: 0 }}>
          No saved versions yet. The next edit captures one.
        </p>
      )}
      {!rows && !error && (
        <p style={{ fontSize: 12, color: 'var(--muted)', margin: 0 }}>Loading…</p>
      )}

      <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex',
        flexDirection: 'column', gap: 6, overflowY: 'auto' }}>
        {(rows ?? []).map(v => {
          const isCurrent = currentRevision != null && v.revision === currentRevision
          return (
            <li key={v.id} style={{ border: '1px solid var(--border)', borderRadius: 8,
              padding: '8px 10px', background: 'var(--surface)', display: 'flex',
              alignItems: 'center', gap: 8 }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12.5, fontWeight: 600, display: 'flex',
                  alignItems: 'center', gap: 6 }}>
                  Revision {v.revision}
                  {isCurrent && (
                    <span style={{ fontSize: 10.5, fontWeight: 700, padding: '1px 6px',
                      borderRadius: 999, background: 'var(--accent-soft, #e4edfd)',
                      color: 'var(--accent)', textTransform: 'uppercase', letterSpacing: '.04em' }}>
                      current
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 10.5, color: 'var(--muted)' }}>
                  {when(v.created_at)}{v.created_by ? ` · ${v.created_by}` : ''}
                </div>
                {v.via === 'copilot' && (
                  <div data-testid="version-copilot" style={{ fontSize: 10.5, color: 'var(--accent)', display: 'flex', alignItems: 'center', gap: 4 }}>
                    <Bot size={12} aria-hidden /> {v.note || 'Before a copilot change'}{v.created_by ? ` (asked by ${v.created_by})` : ''}
                  </div>
                )}
                <div style={{ fontSize: 10.5, color: 'var(--faint, var(--muted))' }}>
                  {v.pages} page{v.pages === 1 ? '' : 's'} · {v.widgets} widget{v.widgets === 1 ? '' : 's'}
                </div>
              </div>
              <button
                aria-label={`Restore revision ${v.revision}`}
                title="Restore this version"
                disabled={restoring != null}
                onClick={() => void restore(v)}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 4,
                  fontSize: 11.5, padding: '5px 9px', borderRadius: 6, cursor: 'pointer',
                  border: '1px solid var(--border)', background: 'var(--surface2)',
                  color: 'var(--text)', flexShrink: 0,
                  opacity: restoring != null && restoring !== v.id ? 0.5 : 1 }}>
                <RotateCcw size={12} aria-hidden />
                {restoring === v.id ? 'Restoring…' : 'Restore'}
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
