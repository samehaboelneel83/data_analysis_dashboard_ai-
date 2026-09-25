import { useEffect, useState } from 'react'
import { useT } from '../../i18n'
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
  const t = useT()
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
    rows, r => [r.report_name, r.kind, r.status, r.error], t('search.deliveries'))

  return (
    <div style={{ maxWidth: 1200 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 4 }}>
        <h1 className="dl-page-title" style={{ margin: 0 }}>{t('nav.deliveries')}</h1>
        {input}
      </div>
      <p className="dl-page-head__sub" style={{ marginBottom: 16, marginTop: 4 }}>
        {t('deliveries.subtitle')}
      </p>

      {loading && <LoadingState />}

      {!loading && loadError != null && (
        <LoadError what="deliveries" error={loadError} onRetry={load} />
      )}

      {!loading && loadError == null && rows.length === 0 && (
        <EmptyState icon={Send} title={t('deliveries.empty')}
          description={t('deliveries.emptyBody')} />
      )}
      {noMatches && <p style={{ color: 'var(--muted)' }}>{t('deliveries.noMatch')}</p>}

      {!loading && loadError == null && filtered.length > 0 && (
        <div className="card dl-table-card"><table className="dl-table">
          <thead>
            <tr>
              <th>{t('col.when')}</th>
              <th>{t('col.report')}</th>
              <th>{t('col.kind')}</th>
              <th>{t('col.artifact')}</th>
              <th>{t('col.duration')}</th>
              <th>{t('col.status')}</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(r => (
              <tr key={r.id}>
                <td style={{ whiteSpace: 'nowrap' }}>{new Date(r.created_at).toLocaleString()}</td>
                <td style={{ fontWeight: 600 }}>
                  {r.report_id != null
                    ? <Link to={`/reports/${r.report_id}`} style={{ color: 'var(--text)' }}>{r.report_name ?? `#${r.report_id}`}</Link>
                    : <span style={{ color: 'var(--muted)' }}>—</span>}
                </td>
                <td>{r.kind}</td>
                <td>{r.artifact_kind === 'none' ? '—' : r.artifact_kind}</td>
                <td style={{ whiteSpace: 'nowrap' }}>
                  {r.duration_ms != null ? `${r.duration_ms} ms` : '—'}
                </td>
                <td style={{
                  color: r.status === 'ok' ? 'var(--success)' : 'var(--danger)' }}
                  title={r.error ?? undefined}>
                  {r.status === 'ok' ? 'ok' : `failed${r.error ? ` — ${r.error}` : ''}`}
                </td>
              </tr>
            ))}
          </tbody>
        </table></div>
      )}
    </div>
  )
}
