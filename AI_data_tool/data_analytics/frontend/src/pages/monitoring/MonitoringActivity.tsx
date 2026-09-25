import { useEffect, useState } from 'react'
import { Activity as ActivityIcon } from 'lucide-react'
import { monitoringApi } from '../../services/api'
import type { ActivityRow } from '../../services/api'
import { useListFilter } from '../../components/ui/ListFilter'
import EmptyState from '../../components/ui/EmptyState'
import LoadError from '../../components/ui/LoadError'
import LoadingState from '../../components/ui/LoadingState'

/**
 * The org's general activity log -- logins, uploads, report edits, deletes.
 * The backend has recorded this since S4 (`/admin/audit-log`); this page is
 * its first reader. Distinct from Admin → Audit trail, which lists only
 * security-relevant ADMIN mutations: that page answers "who changed the
 * rules", this one answers "what happened".
 */
export default function MonitoringActivity() {
  const [rows, setRows] = useState<ActivityRow[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<unknown>(null)

  // A load failure gets the persistent inline banner below, not a toast: it is
  // this page's whole content going missing, not a transient action result.
  const load = () => {
    setLoading(true)
    setLoadError(null)
    return monitoringApi.activity().then(setRows).catch(setLoadError).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const { filtered, input, noMatches } = useListFilter(
    rows, r => [r.user_email, r.action, r.entity, r.detail], 'Search activity…')

  return (
    <div style={{ padding: 24, maxWidth: 1000 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 4 }}>
        <h1 style={{ fontSize: 18, fontWeight: 700, margin: 0 }}>Activity</h1>
        {input}
      </div>
      <p style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 16 }}>
        What happened in this organisation, newest first. Read-only. For admin security
        changes, see Admin → Audit trail.
      </p>

      {loading && <LoadingState />}

      {!loading && loadError != null && (
        <LoadError what="activity" error={loadError} onRetry={load} />
      )}

      {!loading && loadError == null && rows.length === 0 && (
        <EmptyState icon={ActivityIcon} title="Nothing recorded yet." />
      )}
      {noMatches && <p style={{ color: 'var(--muted)' }}>No activity matches.</p>}

      {!loading && loadError == null && filtered.length > 0 && (
        <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ textAlign: 'start', color: 'var(--muted)' }}>
              <th style={{ padding: '6px 8px' }}>When</th>
              <th style={{ padding: '6px 8px' }}>Who</th>
              <th style={{ padding: '6px 8px' }}>Action</th>
              <th style={{ padding: '6px 8px' }}>Entity</th>
              <th style={{ padding: '6px 8px' }}>Detail</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(r => (
              <tr key={r.id} style={{ borderTop: '1px solid var(--border)' }}>
                <td style={{ padding: '6px 8px', whiteSpace: 'nowrap' }}>{new Date(r.created_at).toLocaleString()}</td>
                <td style={{ padding: '6px 8px' }}>{r.user_email ?? '—'}</td>
                <td style={{ padding: '6px 8px', fontWeight: 600 }}>{r.action}</td>
                <td style={{ padding: '6px 8px' }}>
                  {r.entity ? `${r.entity}${r.entity_id != null ? ` #${r.entity_id}` : ''}` : '—'}
                </td>
                <td style={{ padding: '6px 8px', color: 'var(--muted)' }}>{r.detail ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
