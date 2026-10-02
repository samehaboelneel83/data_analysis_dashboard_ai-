import { useContext, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { dataSourcesApi } from '../services/api'
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
 */
export default function Glossary() {
  const t = useT()
  const canEdit = !!useContext(AuthContext)?.user?.role?.is_org_admin
  const [sources, setSources] = useState<{ id: number; name: string }[] | null>(null)
  const [sourceId, setSourceId] = useState<number | null>(() => {
    try { const v = Number(localStorage.getItem('datalytics:glossary-source')); return v > 0 ? v : null } catch { return null }
  })

  useEffect(() => {
    dataSourcesApi.list()
      .then(list => {
        const rows = list.map(s => ({ id: s.id, name: s.name }))
        setSources(rows)
        setSourceId(cur => (cur && rows.some(r => r.id === cur)) ? cur : (rows[0]?.id ?? null))
      })
      .catch(() => setSources([]))
  }, [])

  const pick = (id: number) => {
    setSourceId(id)
    try { localStorage.setItem('datalytics:glossary-source', String(id)) } catch { /* a convenience */ }
  }

  return (
    <div style={{ height: '100%', overflowY: 'auto' }}>
      <h1 className="dl-page-title" style={{ marginBottom: 4 }}>{t('nav.glossary')}</h1>
      <p className="dl-page-head__sub" style={{ marginBottom: 18, maxWidth: 760 }}>
        {t('glossary.subtitle')}
      </p>
      {sources === null ? null : sources.length === 0 ? (
        <p style={{ fontSize: 13, color: 'var(--muted)' }}>
          {t('glossary.noSources')} <Link to="/connections">{t('nav.connections')}</Link>
        </p>
      ) : (
        <>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, marginBottom: 16 }}>
            {t('glossary.connection')}
            <select aria-label={t('glossary.connection')} value={sourceId ?? ''}
              onChange={e => pick(Number(e.target.value))}
              style={{ fontSize: 13, padding: '4px 8px', background: 'var(--surface2)', color: 'var(--text)',
                border: '1px solid var(--border)', borderRadius: 6 }}>
              {sources.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </label>
          {sourceId != null && (
            <div className="card" style={{ padding: 16 }}>
              <GlossaryPanel key={sourceId} sourceId={sourceId} canEdit={canEdit} />
            </div>
          )}
        </>
      )}
    </div>
  )
}
