import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Send } from 'lucide-react'
import { monitoringApi } from '../../services/api'
import type { MonitoringDeliveryRow } from '../../services/api'
import { useListFilter } from '../../components/ui/ListFilter'
import EmptyState from '../../components/ui/EmptyState'
import LoadError from '../../components/ui/LoadError'
import LoadingState from '../../components/ui/LoadingState'

/**
 * The org's delivery log, newest first -- every schedule send, alert fire and
 * manual export attempt, success and failure alike. The same rows the builder
 * shows per report, unscoped: "which deliveries failed last night" is a
 * cross-report question and had no cross-report answer.
 */
export default function MonitoringDeliveries() {
  const [rows, setRows] = useState<MonitoringDeliveryRow[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<unknown>(null)

  // A load failure gets the persistent inline banner below, not a toast: it is
  // this page's whole content going missing, not a transient action result.
  const load = () => {
    setLoading(true)
    setLoadError(null)
    return monitoringApi.deliveries().then(setRows).catch(setLoadError).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const { filtered, input, noMatches } = useListFilter(
    rows, r => [r.report_name, r.kind, r.status, r.error], 'Search deliveries…')

  return (
    <div style={{ padding: 24, maxWidth: 1000 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 4 }}>
        <h1 style={{ fontSize: 18, fontWeight: 700, margin: 0 }}>Deliveries</h1>
        {input}
      </div>
      <p style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 16 }}>
        Every scheduled send, alert email and export attempt across the organisation —
        including the ones that failed.
      </p>

      {loading && <LoadingState />}

      {!loading && loadError != null && (
        <LoadError what="deliveries" error={loadError} onRetry={load} />
      )}

      {!loading && loadError == null && rows.length === 0 && (
        <EmptyState icon={Send} title="No deliveries yet."
          description="Once a report schedule or data alert runs, each attempt is logged here." />
      )}
      {noMatches && <p style={{ color: 'var(--muted)' }}>No deliveries match.</p>}

      {!loading && loadError == null && filtered.length > 0 && (
        <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ textAlign: 'start', color: 'var(--muted)' }}>
              <th style={{ padding: '6px 8px' }}>When</th>
              <th style={{ padding: '6px 8px' }}>Report</th>
              <th style={{ padding: '6px 8px' }}>Kind</th>
              <th style={{ padding: '6px 8px' }}>Artifact</th>
              <th style={{ padding: '6px 8px' }}>Duration</th>
              <th style={{ padding: '6px 8px' }}>Status</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(r => (
              <tr key={r.id} style={{ borderTop: '1px solid var(--border)' }}>
                <td style={{ padding: '6px 8px', whiteSpace: 'nowrap' }}>{new Date(r.created_at).toLocaleString()}</td>
                <td style={{ padding: '6px 8px', fontWeight: 600 }}>
                  {r.report_id != null
                    ? <Link to={`/reports/${r.report_id}`} style={{ color: 'var(--text)' }}>{r.report_name ?? `#${r.report_id}`}</Link>
                    : <span style={{ color: 'var(--muted)' }}>—</span>}
                </td>
                <td style={{ padding: '6px 8px' }}>{r.kind}</td>
                <td style={{ padding: '6px 8px' }}>{r.artifact_kind === 'none' ? '—' : r.artifact_kind}</td>
                <td style={{ padding: '6px 8px', whiteSpace: 'nowrap' }}>
                  {r.duration_ms != null ? `${r.duration_ms} ms` : '—'}
                </td>
                <td style={{ padding: '6px 8px',
                  color: r.status === 'ok' ? 'var(--positive, #4caf82)' : 'var(--negative, #e2606c)' }}
                  title={r.error ?? undefined}>
                  {r.status === 'ok' ? 'ok' : `failed${r.error ? ` — ${r.error}` : ''}`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
