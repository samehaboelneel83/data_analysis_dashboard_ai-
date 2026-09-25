import { useEffect, useState } from 'react'
import { inlineFieldStyle } from '../../components/ui/fieldStyle'
import { useT } from '../../i18n'
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
  const t = useT()
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

  const inp = { style: inlineFieldStyle }

  return (
    <div style={{ maxWidth: 1000 }}>
      <h1 className="dl-page-title" style={{ marginBottom: 4 }}>{t('nav.audit')}</h1>
      <p className="dl-page-head__sub" style={{ marginBottom: 16, maxWidth: 760 }}>
        {t('audit.subtitle')}
      </p>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' }}>
        <select value={action} onChange={e => setAction(e.target.value)} aria-label={t('audit.byAction')} {...inp}>
          <option value="">{t('audit.allActions')}</option>
          {actions.map(a => <option key={a} value={a}>{a}</option>)}
        </select>
        <input
          placeholder={t('audit.byTargetPh')}
          value={q}
          onChange={e => setQ(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') load() }}
          aria-label={t('audit.byTarget')}
          {...inp}
          style={{ ...inp.style, minWidth: 220 }}
        />
        <button className="btn btn-ghost btn-sm" onClick={load} style={{ fontSize: 12 }}>{t('audit.apply')}</button>
      </div>

      {loading && <LoadingState />}

      {!loading && loadError != null && (
        <LoadError what="the audit trail" error={loadError} onRetry={load} />
      )}

      {!loading && loadError == null && rows.length === 0 && (
        <div className="card" style={{ padding: '40px 24px', textAlign: 'center', color: 'var(--muted)' }}>
          {t('audit.none')}
        </div>
      )}

      {!loading && loadError == null && rows.length > 0 && (
        <div className="card dl-table-card">
        <table className="dl-table">
          <thead>
            <tr>
              <th>{t('col.when')}</th>
              <th>{t('col.actor')}</th>
              <th>{t('col.action')}</th>
              <th>{t('col.target')}</th>
              <th>{t('col.detail')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(r => (
              <tr key={r.id}>
                <td style={{ whiteSpace: 'nowrap' }}>{new Date(r.created_at).toLocaleString()}</td>
                <td>{r.actor_email ?? '—'}</td>
                <td style={{ fontWeight: 600 }}>{r.action}</td>
                <td>{r.target ?? '—'}</td>
                <td style={{ color: 'var(--muted)' }}>{r.detail ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}
    </div>
  )
}
