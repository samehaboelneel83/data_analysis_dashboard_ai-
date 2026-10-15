import { useContext, useEffect, useState } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'
import { dataSourcesApi, datasetsApi } from '../services/api'
import { AuthContext } from '../contexts/AuthContext'
import GlossaryPanel from '../components/review/GlossaryPanel'
import { useT } from '../i18n'

/**
 * The business glossary, as its own page under Data.
 *
 * The terms and their rules already drove Ask AI and the dashboard designer,
 * but the only screen that wrote them sat on a connection's review page -- the
 * HR evaluation looked for "where do I tell the AI that current means to_date
 * 9999-01-01" and found nothing. Rules marked "always" are applied to every
 * question on the connection.
 *
 * B-21: a dataset is a scope too -- an uploaded file has no connection to hang
 * its terms on. `?dataset=<id>` opens one (the Columns tab links here), with
 * `&column=<name>` opening the add form linked to that column. "All data
 * (org-wide)" (first in the list) holds the terms that apply everywhere.
 */
const ORG_WIDE = 'o'

type Scope = { key: string; kind: 's' | 'd' | 'o'; id: number; name: string; columns?: string[] }

export default function Glossary() {
  const t = useT()
  const canEdit = !!useContext(AuthContext)?.user?.role?.is_org_admin
  const [params] = useSearchParams()
  const { hash } = useLocation()
  const asked = Number(params.get('dataset')) > 0 ? `d:${Number(params.get('dataset'))}` : null
  const column = params.get('column') ?? undefined
  const [scopes, setScopes] = useState<Scope[] | null>(null)
  const [key, setKey] = useState<string | null>(() => {
    if (asked) return asked
    try {
      const v = localStorage.getItem('datalytics:glossary-scope')
      if (v) return v
      const old = Number(localStorage.getItem('datalytics:glossary-source'))
      return old > 0 ? `s:${old}` : null
    } catch { return null }
  })

  useEffect(() => {
    let live = true
    Promise.all([
      dataSourcesApi.list().catch(() => []),
      Promise.resolve().then(() => datasetsApi.list()).catch(() => []),
    ]).then(([sources, datasets]) => {
      if (!live) return
      const rows: Scope[] = [
        ...(sources ?? []).map(s => ({ key: `s:${s.id}`, kind: 's' as const, id: s.id, name: s.name })),
        ...(datasets ?? []).map(d => ({ key: `d:${d.id}`, kind: 'd' as const, id: d.id, name: d.name,
                                        columns: (d.columns ?? []).map(c => c.name) })),
      ]
      setScopes(rows)
      // The org-wide choice is offered once there is data to apply it to, and
      // is opened when picked (or remembered) -- otherwise the first data scope.
      setKey(cur => (cur && (cur === ORG_WIDE || rows.some(r => r.key === cur))) ? cur : (rows[0]?.key ?? null))
    })
    return () => { live = false }
  }, [])

  useEffect(() => {
    // The Columns tab links to one term: bring it into view once listed.
    if (!hash.startsWith('#term-')) return
    const id = window.setTimeout(() => document.getElementById(hash.slice(1))?.scrollIntoView?.({ block: 'center' }), 400)
    return () => window.clearTimeout(id)
  }, [hash, key])

  const pick = (k: string) => {
    setKey(k)
    try { localStorage.setItem('datalytics:glossary-scope', k) } catch { /* a convenience */ }
  }
  const current: Scope | null = key === ORG_WIDE && scopes?.length
    ? { key: ORG_WIDE, kind: 'o', id: 0, name: t('pg.dataPages.gl.orgWideScope') }
    : scopes?.find(s => s.key === key) ?? null
  const sources = (scopes ?? []).filter(s => s.kind === 's')
  const datasets = (scopes ?? []).filter(s => s.kind === 'd')
  const selectStyle = { fontSize: 13, padding: '4px 8px', background: 'var(--surface2)', color: 'var(--text)',
    border: '1px solid var(--border)', borderRadius: 6 }

  return (
    <div style={{ height: '100%', overflowY: 'auto' }}>
      <h1 className="dl-page-title" style={{ marginBottom: 4 }}>{t('nav.glossary')}</h1>
      <p className="dl-page-head__sub" style={{ marginBottom: 18, maxWidth: 760 }}>
        {t('glossary.subtitle')}
      </p>
      {scopes === null ? null : scopes.length === 0 ? (
        <p style={{ fontSize: 13, color: 'var(--muted)' }}>
          {t('glossary.noSources')} <Link to="/connections">{t('nav.connections')}</Link>
        </p>
      ) : (
        <>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, marginBottom: 16 }}>
            {t('glossary.scope')}
            <select aria-label={t('glossary.scope')} value={key ?? ''} onChange={e => pick(e.target.value)} style={selectStyle}>
              <option value={ORG_WIDE}>{t('pg.dataPages.gl.orgWideScope')}</option>
              {sources.length > 0 && (
                <optgroup label={t('pg.dataPages.gl.connectionsGroup')}>
                  {sources.map(s => <option key={s.key} value={s.key}>{s.name}</option>)}
                </optgroup>
              )}
              {datasets.length > 0 && (
                <optgroup label={t('pg.dataPages.gl.datasetsGroup')}>
                  {datasets.map(s => <option key={s.key} value={s.key}>{s.name}</option>)}
                </optgroup>
              )}
            </select>
          </label>
          {current && (
            <div className="card" style={{ padding: 16 }}>
              {current.kind === 'o'
                ? <GlossaryPanel key={current.key} orgWide canEdit={canEdit} />
                : current.kind === 's'
                ? <GlossaryPanel key={current.key} sourceId={current.id} canEdit={canEdit} />
                : <GlossaryPanel key={current.key} datasetId={current.id} canEdit={canEdit}
                    columnNames={current.columns}
                    initialColumn={current.key === asked ? column : undefined} />}
            </div>
          )}
        </>
      )}
    </div>
  )
}
