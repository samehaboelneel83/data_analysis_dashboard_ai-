import { useEffect, useState } from 'react'
import {
  agentPoliciesApi, dataSourcesApi, metadataApi,
  type ConnectionRowPolicy,
} from '../../services/api'
import { adminRolesApi as rolesApi } from '../../services/api'
import { useT } from '../../i18n'

/** Row rules for a CONNECTION — the ones Ask AI obeys.
 *
 *  There are two row-security systems in this platform and they do not know
 *  about each other. `row_security_rules` narrow a DATASET, and every admin
 *  screen was about those. Ask AI reads the CONNECTION, which obeys
 *  `object_row_policies` — and those had no page at all.
 *
 *  The consequence, measured against the real app: a student narrowed to their
 *  own row by a dataset rule opened Ask AI and pulled five thousand other
 *  students' grades, with buttons to download them. The control existed and
 *  worked; an admin could not reach it and had no way to learn it was missing.
 *
 *  So the page is deliberately blunt about what it is for. A security control
 *  nobody knows about protects nobody. */
export default function ConnectionRowPolicies() {
  const t = useT()
  const [sources, setSources] = useState<{ id: number; name: string }[]>([])
  const [sourceId, setSourceId] = useState<number | null>(null)
  const [objects, setObjects] = useState<{ id: number; name: string }[]>([])
  const [roles, setRoles] = useState<{ id: number; name: string }[]>([])
  const [policies, setPolicies] = useState<ConnectionRowPolicy[]>([])
  const [objectId, setObjectId] = useState('')
  const [roleId, setRoleId] = useState('')
  const [predicate, setPredicate] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    void (async () => {
      const [srcs, rls] = await Promise.all([dataSourcesApi.list(), rolesApi.list()])
      setSources(srcs)
      setRoles(rls)
      if (srcs.length) setSourceId(srcs[0].id)
    })()
  }, [])

  useEffect(() => {
    if (sourceId == null) return
    void (async () => {
      const [review, pols] = await Promise.all([
        metadataApi.review(sourceId), agentPoliciesApi.list(sourceId),
      ])
      setObjects((review as unknown as { datasets: { id: number; name: string }[] }).datasets ?? [])
      setPolicies(pols)
    })()
  }, [sourceId])

  const reload = async () => {
    if (sourceId != null) setPolicies(await agentPoliciesApi.list(sourceId))
  }

  const add = async () => {
    setError('')
    if (!objectId || !roleId || !predicate.trim()) {
      setError(t('pg.adminSecurity.crp.incomplete'))
      return
    }
    setBusy(true)
    try {
      await agentPoliciesApi.create({
        source_object_id: Number(objectId), role_id: Number(roleId),
        predicate: predicate.trim(),
      })
      setPredicate('')
      await reload()
    } catch (e) {
      // The server parses the predicate in the source's own SQL dialect, so its
      // reason is more useful than anything this form could guess.
      const detail = (e as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail
      setError(detail || t('pg.adminSecurity.crp.saveFailed'))
    } finally {
      setBusy(false)
    }
  }

  const label: React.CSSProperties = {
    display: 'block', fontSize: 11, fontWeight: 700, color: 'var(--muted)',
    textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 4,
  }
  const cell: React.CSSProperties = {
    padding: '8px 10px', borderBottom: '1px solid var(--border)', fontSize: 13,
  }

  return (
    <div style={{ maxWidth: 980 }}>
      <h1 className="dl-page-title" style={{ margin: 0 }}>
        {t('pg.adminSecurity.crp.title')}
      </h1>

      <p style={{
        marginTop: 12, padding: '12px 14px', borderRadius: 6, fontSize: 13,
        background: 'var(--surface2)', borderInlineStart: '3px solid var(--accent)',
      }}>
        <strong>{t('pg.adminSecurity.crp.warnStrong')}</strong>{' '}
        {t('pg.adminSecurity.crp.warnBody')}
      </p>

      <div style={{ marginTop: 20 }}>
        <label htmlFor="crp-source" style={label}>{t('pg.adminSecurity.crp.connection')}</label>
        <select id="crp-source" value={sourceId ?? ''}
                onChange={e => setSourceId(Number(e.target.value))}
                style={{ minWidth: 320 }}>
          {sources.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
      </div>

      <h2 style={{ fontSize: 15, fontWeight: 700, marginTop: 24 }}>{t('pg.adminSecurity.crp.rulesHeading')}</h2>
      {policies.length === 0 ? (
        <p style={{ fontSize: 13, color: 'var(--danger, #b4232a)', marginTop: 8 }}>
          {t('pg.adminSecurity.crp.noRules')}
        </p>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 8 }}>
          <thead>
            <tr>
              <th style={{ ...cell, textAlign: 'start' }}>{t('pg.adminSecurity.crp.table')}</th>
              <th style={{ ...cell, textAlign: 'start' }}>{t('pg.adminSecurity.crp.role')}</th>
              <th style={{ ...cell, textAlign: 'start' }}>{t('pg.adminSecurity.crp.rule')}</th>
              <th style={cell} />
            </tr>
          </thead>
          <tbody>
            {policies.map(p => (
              <tr key={p.id}>
                <td style={cell}><bdi>{p.object_name}</bdi></td>
                <td style={cell}><bdi>{p.role_name}</bdi></td>
                <td style={{ ...cell, fontFamily: 'monospace' }}><bdi dir="ltr">{p.predicate}</bdi></td>
                <td style={cell}>
                  <button onClick={() => { void agentPoliciesApi.remove(p.id).then(reload) }}
                          style={{ fontSize: 12, cursor: 'pointer' }}>{t('pg.adminSecurity.crp.remove')}</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h2 style={{ fontSize: 15, fontWeight: 700, marginTop: 28 }}>{t('pg.adminSecurity.crp.addHeading')}</h2>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 8, alignItems: 'end' }}>
        <div>
          <label htmlFor="crp-table" style={label}>{t('pg.adminSecurity.crp.table')}</label>
          <select id="crp-table" value={objectId} onChange={e => setObjectId(e.target.value)}
                  style={{ minWidth: 220 }}>
            <option value="">{t('pg.adminSecurity.crp.choose')}</option>
            {objects.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="crp-role" style={label}>{t('pg.adminSecurity.crp.role')}</label>
          <select id="crp-role" value={roleId} onChange={e => setRoleId(e.target.value)}
                  style={{ minWidth: 180 }}>
            <option value="">{t('pg.adminSecurity.crp.choose')}</option>
            {roles.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
        </div>
        <div style={{ flex: 1, minWidth: 260 }}>
          <label htmlFor="crp-predicate" style={label}>{t('pg.adminSecurity.crp.rule')}</label>
          <input id="crp-predicate" value={predicate} placeholder="userid = USERID()" // i18n-ok: an expression
                 onChange={e => setPredicate(e.target.value)} style={{ width: '100%' }} />
        </div>
        <button onClick={() => void add()} disabled={busy}
                style={{
                  padding: '7px 14px', borderRadius: 6, border: 'none', fontSize: 13,
                  background: 'var(--accent)', color: 'var(--mc-accent-fg)', cursor: 'pointer',
                }}>
          {busy ? t('pg.adminSecurity.c.saving') : t('pg.adminSecurity.crp.addRule')}
        </button>
      </div>
      {error && (
        <p style={{ marginTop: 10, fontSize: 13, color: 'var(--danger, #b4232a)' }}>{error}</p>
      )}
    </div>
  )
}
