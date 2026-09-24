import { useEffect, useState } from 'react'
import { adminAuditApi } from '../../services/api'
import type { AdminAuditRow } from '../../services/api'
import LoadError from '../../components/ui/LoadError'
import LoadingState from '../../components/ui/LoadingState'

/**
 * S5: read-only trail of security-relevant admin mutations -- row/column
 * security rules, share-link create/revoke, export policy, API keys. Same
 * "an audit log that can be edited by the actions it audits is theatre"
 * principle as the general audit log: nothing here is editable, this page
 * only lists and filters.
 */
export default function AdminAudit() {
  const [rows, setRows] = useState<AdminAuditRow[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [action, setAction] = useState('')
  const [q, setQ] = useState('')

  // A failed fetch is this page's whole content going missing -- the
  // persistent banner below, not a toast that fades and leaves an admin
  // staring at a blank page with no explanation.
  const load = () => {
    setLoading(true)
    setLoadError(null)
    adminAuditApi.list({ action: action || undefined, q: q || undefined })
      .then(setRows)
      .catch(setLoadError)
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const actions = Array.from(new Set(rows.map(r => r.action))).sort()

  const inp = {
    style: { fontSize: 12, padding: '5px 8px', boxSizing: 'border-box' as const,
      background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text)' },
  }

  return (
    <div style={{ padding: 24, maxWidth: 1000 }}>
      <h1 style={{ fontSize: 18, fontWeight: 700, marginBottom: 4 }}>Admin audit trail</h1>
      <p style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 16 }}>
        Read-only. Every security-relevant admin change -- row/column security rules, share-link
        create/revoke, export policy, API keys -- lands here and cannot be edited or deleted.
      </p>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' }}>
        <select value={action} onChange={e => setAction(e.target.value)} aria-label="Filter by action" {...inp}>
          <option value="">All actions</option>
          {actions.map(a => <option key={a} value={a}>{a}</option>)}
        </select>
        <input
          placeholder="Filter by target…"
          value={q}
          onChange={e => setQ(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') load() }}
          aria-label="Filter by target"
          {...inp}
          style={{ ...inp.style, minWidth: 220 }}
        />
        <button className="btn btn-ghost btn-sm" onClick={load} style={{ fontSize: 12 }}>Apply</button>
      </div>

      {loading && <LoadingState />}

      {!loading && loadError != null && (
        <LoadError what="the audit trail" error={loadError} onRetry={load} />
      )}

      {!loading && loadError == null && rows.length === 0 && (
        <div className="card" style={{ padding: '40px 24px', textAlign: 'center', color: 'var(--muted)' }}>
          No audit entries match.
        </div>
      )}

      {!loading && loadError == null && rows.length > 0 && (
        <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ textAlign: 'start', color: 'var(--muted)' }}>
              <th style={{ padding: '6px 8px' }}>When</th>
              <th style={{ padding: '6px 8px' }}>Actor</th>
              <th style={{ padding: '6px 8px' }}>Action</th>
              <th style={{ padding: '6px 8px' }}>Target</th>
              <th style={{ padding: '6px 8px' }}>Detail</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(r => (
              <tr key={r.id} style={{ borderTop: '1px solid var(--border)' }}>
                <td style={{ padding: '6px 8px', whiteSpace: 'nowrap' }}>{new Date(r.created_at).toLocaleString()}</td>
                <td style={{ padding: '6px 8px' }}>{r.actor_email ?? '—'}</td>
                <td style={{ padding: '6px 8px', fontWeight: 600 }}>{r.action}</td>
                <td style={{ padding: '6px 8px' }}>{r.target ?? '—'}</td>
                <td style={{ padding: '6px 8px', color: 'var(--muted)' }}>{r.detail ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
