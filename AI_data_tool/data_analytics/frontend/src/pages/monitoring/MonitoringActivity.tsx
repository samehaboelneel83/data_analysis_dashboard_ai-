import { useEffect, useState } from 'react'
import { useT } from '../../i18n'
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
  const t = useT()
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
    rows, r => [r.user_email, r.action, r.entity, r.detail], t('search.activity'))

  return (
    <div style={{ maxWidth: 1200 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 4 }}>
        <h1 className="dl-page-title" style={{ margin: 0 }}>{t('nav.activity')}</h1>
        {input}
      </div>
      <p className="dl-page-head__sub" style={{ marginBottom: 16, marginTop: 4 }}>
        {t('activity.subtitle')}
      </p>

      {loading && <LoadingState />}

      {!loading && loadError != null && (
        <LoadError what="activity" error={loadError} onRetry={load} />
      )}

      {!loading && loadError == null && rows.length === 0 && (
        <EmptyState icon={ActivityIcon} title={t('activity.empty')} />
      )}
      {noMatches && <p style={{ color: 'var(--muted)' }}>{t('activity.noMatch')}</p>}

      {!loading && loadError == null && filtered.length > 0 && (
        <div className="card dl-table-card"><table className="dl-table">
          <thead>
            <tr>
              <th>{t('col.when')}</th>
              <th>{t('col.who')}</th>
              <th>{t('col.action')}</th>
              <th>{t('col.entity')}</th>
              <th>{t('col.detail')}</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(r => (
              <tr key={r.id}>
                <td style={{ whiteSpace: 'nowrap' }}>{new Date(r.created_at).toLocaleString()}</td>
                <td>{r.user_email ?? '—'}</td>
                <td style={{ fontWeight: 600 }}>{r.action}</td>
                <td>
                  {r.entity ? `${r.entity}${r.entity_id != null ? ` #${r.entity_id}` : ''}` : '—'}
                </td>
                <td style={{ color: 'var(--muted)' }}>{r.detail ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table></div>
      )}
    </div>
  )
}
