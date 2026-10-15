import { useEffect, useState } from 'react'
import { useT } from '../../i18n'
import { activityActionName } from '../../i18n/pages/dataPages'
import { Activity as ActivityIcon } from 'lucide-react'
import { monitoringApi } from '../../services/api'
import type { ActivityRow } from '../../services/api'
import { useListFilter } from '../../components/ui/ListFilter'
import EmptyState from '../../components/ui/EmptyState'
import LoadError from '../../components/ui/LoadError'
import LoadingState from '../../components/ui/LoadingState'
import { formatDate } from '../../lib/dateFormat'

/** AD-18: older rows were written as code -- "queries=None asks=5",
 *  "grant:3". Newer writers use words; for the legacy shapes, split
 *  key=value pairs into "key: value" chips (None reads "no limit") and
 *  name a bare grant id as a share. Anything else is shown as written. */
export function detailParts(detail: string | null | undefined, noLimit: string): string[] | null {
  if (!detail) return null
  const text = detail.replace(/\bgrant:(\d+)/g, 'share #$1')
  const tokens = text.trim().split(/\s+/)
  if (tokens.length > 0 && tokens.every(tok => /^[A-Za-z_]+=\S*$/.test(tok))) {
    return tokens.map(tok => {
      const [k, v] = [tok.slice(0, tok.indexOf('=')), tok.slice(tok.indexOf('=') + 1)]
      return `${k.replace(/_/g, ' ')}: ${v === 'None' || v === '' ? noLimit : v}`
    })
  }
  return [text]
}

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

  // A known action code reads as words in the reader's language; English keeps
  // the code itself (it is what admins search for and what the docs name). An
  // unknown code — a newer server — is shown raw rather than guessed at.
  const actionName = (code: string): string => activityActionName(t, code)

  const { filtered, input, noMatches } = useListFilter(
    rows, r => [r.user_email, r.action, actionName(r.action), r.entity, r.detail], t('search.activity'))

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
        <LoadError what="activity" title={t('pg.dataPages.act.loadError')} error={loadError} onRetry={load} />
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
                <td style={{ whiteSpace: 'nowrap' }}>{formatDate(r.created_at)}</td>
                <td>{r.user_email ? <bdi dir="ltr">{r.user_email}</bdi> : '—'}</td>
                <td style={{ fontWeight: 600 }}>
                  {actionName(r.action) === r.action
                    ? <bdi dir="ltr">{r.action}</bdi>
                    : <span title={r.action}>{actionName(r.action)}</span>}
                </td>
                <td>
                  {r.entity ? <bdi dir="ltr">{`${r.entity}${r.entity_id != null ? ` #${r.entity_id}` : ''}`}</bdi> : '—'}
                </td>
                <td style={{ color: 'var(--muted)' }}>
                  {(() => {
                    const parts = detailParts(r.detail, t('pg.dataPages.act.noLimit'))
                    if (!parts) return '—'
                    if (parts.length === 1) return parts[0]
                    return <span style={{ display: 'inline-flex', flexWrap: 'wrap', gap: 4 }}>
                      {parts.map((p, i) => <span key={i} className="dl-chip-sm" style={{ border: '1px solid var(--border)',
                        borderRadius: 999, padding: '0 6px', fontSize: 11.5 }}>{p}</span>)}
                    </span>
                  })()}
                </td>
              </tr>
            ))}
          </tbody>
        </table></div>
      )}
    </div>
  )
}
