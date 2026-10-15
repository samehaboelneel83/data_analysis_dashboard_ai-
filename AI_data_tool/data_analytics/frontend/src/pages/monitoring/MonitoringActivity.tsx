import { Fragment, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useT } from '../../i18n'
import { ACTIVITY_CODES, activityActionName } from '../../i18n/pages/dataPages'
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
/** AD-19: rows per request; a shorter page is the end of the log. */
const PAGE = 100

export default function MonitoringActivity() {
  const t = useT()
  const [rows, setRows] = useState<ActivityRow[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<unknown>(null)
  // AD-19: server-side filters, keyset paging, and one opened row.
  const [action, setAction] = useState('')
  const [who, setWho] = useState('')
  const [since, setSince] = useState('')
  const [until, setUntil] = useState('')
  const [hasMore, setHasMore] = useState(false)
  const [more, setMore] = useState(false)
  const [open, setOpen] = useState<number | null>(null)
  const [people, setPeople] = useState<string[]>([])
  const params = () => ({
    ...(action ? { action } : {}), ...(who ? { user_email: who } : {}),
    ...(since ? { since } : {}), ...(until ? { until: `${until}T23:59:59` } : {}),
  })
  const remember = (got: ActivityRow[]) => setPeople(p => [...new Set([...p,
    ...got.map(r => r.user_email).filter((e): e is string => !!e)])].sort())

  // A load failure gets the persistent inline banner below, not a toast: it is
  // this page's whole content going missing, not a transient action result.
  const load = () => {
    setLoading(true)
    setLoadError(null)
    setOpen(null)
    return monitoringApi.activity({ limit: PAGE, ...params() })
      .then(got => { setRows(got); setHasMore(got.length === PAGE); remember(got) })
      .catch(setLoadError).finally(() => setLoading(false))
  }
  const loadMore = () => {
    const last = rows[rows.length - 1]
    if (!last) return
    setMore(true)
    monitoringApi.activity({ limit: PAGE, before_id: last.id, ...params() })
      .then(got => { setRows(r => [...r, ...got]); setHasMore(got.length === PAGE); remember(got) })
      .catch(setLoadError).finally(() => setMore(false))
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load() }, [action, who, since, until])
  const actions = useMemo(() => [...ACTIVITY_CODES].sort(), [])
  const entityLink = (r: ActivityRow) => r.entity_id == null ? null
    : r.entity === 'report' ? `/reports/${r.entity_id}`
    : r.entity === 'dataset' ? `/datasets/${r.entity_id}`
    : r.entity === 'automation_run' ? `/automation?run=${r.entity_id}` : null

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

      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: 12, fontSize: 12 }}>
        <label style={{ display: 'grid', gap: 3 }}>{t('pg.dataPages.act.filterAction')}
          <select value={action} onChange={e => setAction(e.target.value)}>
            <option value="">{t('pg.dataPages.act.any')}</option>
            {actions.map(a => <option key={a} value={a}>{actionName(a)}</option>)}
          </select>
        </label>
        <label style={{ display: 'grid', gap: 3 }}>{t('pg.dataPages.act.filterUser')}
          <select value={who} onChange={e => setWho(e.target.value)}>
            <option value="">{t('pg.dataPages.act.any')}</option>
            {[...new Set([...people, ...(who ? [who] : [])])].map(p => <option key={p} value={p}>{p}</option>)}
          </select>
        </label>
        <label style={{ display: 'grid', gap: 3 }}>{t('pg.dataPages.act.from')}
          <input type="date" value={since} onChange={e => setSince(e.target.value)} />
        </label>
        <label style={{ display: 'grid', gap: 3 }}>{t('pg.dataPages.act.to')}
          <input type="date" value={until} onChange={e => setUntil(e.target.value)} />
        </label>
      </div>

      {loading && <LoadingState />}

      {!loading && loadError != null && (
        <LoadError what="activity" title={t('pg.dataPages.act.loadError')} error={loadError} onRetry={load} />
      )}

      {!loading && loadError == null && rows.length === 0 && (
        <EmptyState icon={ActivityIcon} title={t('activity.empty')} />
      )}
      {noMatches && <p style={{ color: 'var(--muted)' }}>{t('activity.noMatch')}</p>}

      {!loading && loadError == null && filtered.length > 0 && (
        <div className="card dl-table-card"><table className="dl-table dl-table--stack">
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
              <Fragment key={r.id}>
              <tr onClick={() => setOpen(open === r.id ? null : r.id)} aria-expanded={open === r.id}
                style={{ cursor: 'pointer' }}>
                <td data-label={t('col.when')} style={{ whiteSpace: 'nowrap' }}>{formatDate(r.created_at)}</td>
                <td data-label={t('col.who')}>{r.user_email ? <bdi dir="ltr">{r.user_email}</bdi> : '—'}</td>
                <td data-label={t('col.action')} style={{ fontWeight: 600 }}>
                  {actionName(r.action) === r.action
                    ? <bdi dir="ltr">{r.action}</bdi>
                    : <span title={r.action}>{actionName(r.action)}</span>}
                </td>
                <td data-label={t('col.entity')}>
                  {r.entity ? <bdi dir="ltr">{`${r.entity}${r.entity_id != null ? ` #${r.entity_id}` : ''}`}</bdi> : '—'}
                </td>
                <td data-label={t('col.detail')} style={{ color: 'var(--muted)' }}>
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
              {open === r.id && (
                <tr data-testid={`activity-detail-${r.id}`}>
                  <td data-label={t('col.detail')} colSpan={5} style={{ background: 'var(--surface2)', whiteSpace: 'normal' }}>
                    <div><b>{t('col.when')}:</b> {new Date(r.created_at).toISOString().replace('T', ' ').slice(0, 19)} UTC</div>
                    <div><b>{t('col.action')}:</b> <bdi dir="ltr">{r.action}</bdi></div>
                    {r.entity && <div><b>{t('col.entity')}:</b>{' '}
                      {entityLink(r) ? <Link to={entityLink(r)!}>{`${r.entity} #${r.entity_id}`}</Link>
                        : <bdi dir="ltr">{`${r.entity}${r.entity_id != null ? ` #${r.entity_id}` : ''}`}</bdi>}</div>}
                    <div style={{ whiteSpace: 'pre-wrap' }}><b>{t('col.detail')}:</b> {r.detail ?? '—'}</div>
                  </td>
                </tr>
              )}
              </Fragment>
            ))}
          </tbody>
        </table></div>
      )}
      {!loading && loadError == null && hasMore && (
        <div style={{ marginTop: 10 }}>
          <button type="button" className="btn btn-sm" disabled={more} onClick={loadMore}>{t('pg.dataPages.act.loadMore')}</button>
        </div>
      )}
    </div>
  )
}
