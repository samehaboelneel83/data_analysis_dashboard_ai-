import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { ShieldCheck } from 'lucide-react'
import { datasetsApi, type CheckResult, type DataCheck, type DataCheckInput, type DataCheckKind,
         type DatasetRefreshRun } from '../../services/api'
import { useT, type MessageKey } from '../../i18n'
import EmptyState from '../ui/EmptyState'

/**
 * Pipeline plan, phase 3, on the dataset page: the checks every refresh runs
 * before its new data replaces the old, a "try them now" against what the
 * dataset holds, and what past refreshes found.
 */

const KINDS: DataCheckKind[] = ['not_null', 'unique', 'accepted_values', 'row_count', 'row_drop', 'rule']
const COLUMN_KINDS: DataCheckKind[] = ['not_null', 'unique', 'accepted_values']

const GOOD = 'color-mix(in oklab, var(--positive, #4caf82) 65%, var(--text))'
const BAD = 'color-mix(in oklab, var(--negative, #e2606c) 75%, var(--text))'
const WARN = 'color-mix(in oklab, #d9a441 60%, var(--text))'

function summary(c: DataCheckInput, t: ReturnType<typeof useT>): string {
  const p = c.params ?? {}
  switch (c.kind) {
    case 'not_null': return t('checks.sum.not_null', { col: c.column ?? '' })
    case 'unique': return t('checks.sum.unique', { col: c.column ?? '' })
    case 'accepted_values': return t('checks.sum.accepted_values', { col: c.column ?? '', values: (p.values ?? []).join(', ') })
    case 'row_count':
      return p.min != null && p.max != null ? t('checks.sum.row_between', { min: p.min.toLocaleString(), max: p.max.toLocaleString() })
        : p.min != null ? t('checks.sum.row_min', { min: p.min.toLocaleString() })
          : t('checks.sum.row_max', { max: (p.max ?? 0).toLocaleString() })
    case 'row_drop': return t('checks.sum.row_drop', { pct: p.max_drop_pct ?? 0 })
    case 'rule': return t('checks.sum.rule', { expr: p.expression ?? '' })
  }
}

/** The failed checks of one load, one line each. */
export function CheckResultList({ results }: { results: CheckResult[] }) {
  const failed = results.filter(r => !r.passed)
  if (!failed.length) return null
  return (
    <ul style={{ margin: '4px 0 0', paddingInlineStart: 18, fontSize: 12 }}>
      {failed.map((r, i) => (
        <li key={i} style={{ color: r.severity === 'block' ? BAD : WARN }}>
          {r.column ? <strong>{r.column}: </strong> : null}{r.detail}
        </li>
      ))}
    </ul>
  )
}

export default function ChecksPanel({ datasetId, columns, canEdit }: {
  datasetId: number; columns: string[]; canEdit: boolean
}) {
  const t = useT()
  const [checks, setChecks] = useState<DataCheck[]>([])
  const [runs, setRuns] = useState<DatasetRefreshRun[]>([])
  const [tried, setTried] = useState<{ rows: number; results: CheckResult[] } | null>(null)
  const [busy, setBusy] = useState(false)
  // The add form.
  const [kind, setKind] = useState<DataCheckKind>('not_null')
  const [column, setColumn] = useState(columns[0] ?? '')
  const [values, setValues] = useState('')
  const [min, setMin] = useState('')
  const [max, setMax] = useState('')
  const [pct, setPct] = useState('50')
  const [expr, setExpr] = useState('')
  const [severity, setSeverity] = useState<'warn' | 'block'>('block')

  const load = () => {
    datasetsApi.checks(datasetId).then(setChecks).catch(() => {})
    if (canEdit) datasetsApi.refreshRuns(datasetId, 20).then(setRuns).catch(() => {})
  }
  useEffect(load, [datasetId, canEdit])

  const err = (e: unknown) =>
    toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? String(e))

  const add = async () => {
    const body: DataCheckInput = { kind, severity, column: COLUMN_KINDS.includes(kind) ? column : null, params: {} }
    if (kind === 'accepted_values') body.params = { values: values.split(',').map(v => v.trim()).filter(Boolean) }
    if (kind === 'row_count') body.params = { min: min === '' ? null : Number(min), max: max === '' ? null : Number(max) }
    if (kind === 'row_drop') body.params = { max_drop_pct: Number(pct) }
    if (kind === 'rule') body.params = { expression: expr }
    setBusy(true)
    try {
      await datasetsApi.addCheck(datasetId, body)
      setValues(''); setMin(''); setMax(''); setExpr('')
      setTried(null)
      load()
    } catch (e) { err(e) } finally { setBusy(false) }
  }

  const update = async (c: DataCheck, change: Partial<DataCheckInput>) => {
    try {
      const next = await datasetsApi.updateCheck(datasetId, c.id,
        { kind: c.kind, column: c.column, params: c.params, severity: c.severity, enabled: c.enabled, ...change })
      setChecks(cs => cs.map(x => (x.id === c.id ? next : x)))
    } catch (e) { err(e) }
  }

  const remove = async (c: DataCheck) => {
    try {
      await datasetsApi.deleteCheck(datasetId, c.id)
      setChecks(cs => cs.filter(x => x.id !== c.id))
    } catch (e) { err(e) }
  }

  const tryNow = async () => {
    setBusy(true)
    try { setTried(await datasetsApi.tryChecks(datasetId)) } catch (e) { err(e) } finally { setBusy(false) }
  }

  const resultFor = (c: DataCheck) => tried?.results.find(r => r.id === c.id)
  const statusText = (st: string) => { const k = `jobs.status.${st}` as MessageKey; const v = t(k); return v && v !== k ? v : st }

  return (
    <div style={{ maxWidth: 900 }}>
      <p style={{ color: 'var(--muted)', fontSize: 13, marginTop: 0 }}>{t('checks.intro')}</p>

      {checks.length === 0 && !canEdit && (
        <EmptyState icon={ShieldCheck} title={t('checks.none')} description={t('checks.noneBody')} />
      )}

      {checks.length > 0 && (
        <div className="card dl-table-card" style={{ marginBottom: 16 }}><table className="dl-table" data-testid="checks-table">
          <thead><tr>
            <th>{t('checks.col.check')}</th>
            <th>{t('checks.col.ifFails')}</th>
            {tried && <th>{t('checks.col.now')}</th>}
            {canEdit && <th aria-label={t('checks.col.actions')} />}
          </tr></thead>
          <tbody>
            {checks.map(c => {
              const r = resultFor(c)
              return (
                <tr key={c.id} style={{ opacity: c.enabled ? 1 : 0.55 }}>
                  <td>{summary(c, t)}</td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    {canEdit ? (
                      <select aria-label={t('checks.col.ifFails')} value={c.severity} className="input" style={{ fontSize: 12 }}
                        onChange={e => void update(c, { severity: e.target.value as 'warn' | 'block' })}>
                        <option value="block">{t('checks.block')}</option>
                        <option value="warn">{t('checks.warn')}</option>
                      </select>
                    ) : t(c.severity === 'block' ? 'checks.block' : 'checks.warn')}
                  </td>
                  {tried && (
                    <td style={{ color: !r ? 'var(--muted)' : r.passed ? GOOD : c.severity === 'block' ? BAD : WARN, fontSize: 12 }}>
                      {!r ? '—' : r.passed ? t('checks.passes') : r.detail}
                    </td>
                  )}
                  {canEdit && (
                    <td style={{ whiteSpace: 'nowrap', textAlign: 'end' }}>
                      <label style={{ fontSize: 12, marginInlineEnd: 10 }}>
                        <input type="checkbox" checked={c.enabled} onChange={e => void update(c, { enabled: e.target.checked })} />{' '}
                        {t('checks.on')}
                      </label>
                      <button type="button" className="btn btn-ghost btn-sm" onClick={() => void remove(c)}>{t('checks.remove')}</button>
                    </td>
                  )}
                </tr>
              )
            })}
          </tbody>
        </table></div>
      )}

      {canEdit && checks.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          <button type="button" className="btn btn-sm" disabled={busy} onClick={() => void tryNow()}>{t('checks.tryNow')}</button>
          {tried && (
            <span style={{ fontSize: 12, color: 'var(--muted)', marginInlineStart: 10 }}>
              {t('checks.triedOn', { rows: tried.rows.toLocaleString() })}
            </span>
          )}
        </div>
      )}

      {canEdit && (
        <div className="card" style={{ padding: 14, marginBottom: 24 }}>
          <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 10 }}>{t('checks.add')}</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'flex-end' }}>
            <label style={{ fontSize: 12 }}>{t('checks.kindLabel')}<br />
              <select className="input" value={kind} onChange={e => setKind(e.target.value as DataCheckKind)} style={{ fontSize: 12 }}>
                {KINDS.map(k => <option key={k} value={k}>{t(`checks.kind.${k}` as MessageKey)}</option>)}
              </select>
            </label>
            {COLUMN_KINDS.includes(kind) && (
              <label style={{ fontSize: 12 }}>{t('checks.column')}<br />
                <select className="input" value={column} onChange={e => setColumn(e.target.value)} style={{ fontSize: 12 }}>
                  {columns.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </label>
            )}
            {kind === 'accepted_values' && (
              <label style={{ fontSize: 12, flex: 1, minWidth: 200 }}>{t('checks.values')}<br />
                <input className="input" dir="auto" value={values} onChange={e => setValues(e.target.value)}
                  placeholder="open, closed" style={{ fontSize: 12, width: '100%' }} />
              </label>
            )}
            {kind === 'row_count' && (<>
              <label style={{ fontSize: 12 }}>{t('checks.min')}<br />
                <input className="input" type="number" min={0} value={min} onChange={e => setMin(e.target.value)} style={{ fontSize: 12, width: 110 }} />
              </label>
              <label style={{ fontSize: 12 }}>{t('checks.max')}<br />
                <input className="input" type="number" min={0} value={max} onChange={e => setMax(e.target.value)} style={{ fontSize: 12, width: 110 }} />
              </label>
            </>)}
            {kind === 'row_drop' && (
              <label style={{ fontSize: 12 }}>{t('checks.maxDrop')}<br />
                <input className="input" type="number" min={1} max={100} value={pct} onChange={e => setPct(e.target.value)} style={{ fontSize: 12, width: 90 }} />
              </label>
            )}
            {kind === 'rule' && (
              <label style={{ fontSize: 12, flex: 1, minWidth: 220 }}>{t('checks.rule')}<br />
                <input className="input" dir="ltr" value={expr} onChange={e => setExpr(e.target.value)}
                  placeholder="amount >= 0" style={{ fontSize: 12, width: '100%', fontFamily: 'var(--mono)' }} />
              </label>
            )}
            <label style={{ fontSize: 12 }}>{t('checks.col.ifFails')}<br />
              <select className="input" value={severity} onChange={e => setSeverity(e.target.value as 'warn' | 'block')} style={{ fontSize: 12 }}>
                <option value="block">{t('checks.block')}</option>
                <option value="warn">{t('checks.warn')}</option>
              </select>
            </label>
            <button type="button" className="btn btn-primary btn-sm" disabled={busy} onClick={() => void add()}>{t('checks.addButton')}</button>
          </div>
        </div>
      )}

      {canEdit && runs.length > 0 && (<>
        <h3 style={{ fontSize: 14, margin: '0 0 8px' }}>{t('checks.history')}</h3>
        <div className="card dl-table-card"><table className="dl-table" data-testid="checks-history">
          <thead><tr>
            <th>{t('jobs.history.started')}</th>
            <th>{t('jobs.history.trigger')}</th>
            <th>{t('col.status')}</th>
            <th style={{ textAlign: 'end' }}>{t('jobs.history.rows')}</th>
          </tr></thead>
          <tbody>
            {runs.map(r => (
              <tr key={r.id}>
                <td style={{ whiteSpace: 'nowrap', verticalAlign: 'top' }}>{r.started_at ? new Date(r.started_at).toLocaleString() : '—'}</td>
                <td style={{ verticalAlign: 'top' }}>{t(r.trigger === 'manual' ? 'jobs.history.manual' : 'jobs.history.schedule')}</td>
                <td style={{ color: r.status === 'ok' ? GOOD : r.status === 'blocked' || r.status === 'failed' ? BAD : 'var(--muted)' }}>
                  {statusText(r.status)}
                  {r.status === 'failed' && r.error && (
                    <div style={{ fontSize: 11.5, color: 'var(--muted)' }}>{r.error.split('\n')[0].slice(0, 200)}</div>
                  )}
                  <CheckResultList results={r.checks ?? []} />
                </td>
                <td style={{ textAlign: 'end', verticalAlign: 'top', fontVariantNumeric: 'tabular-nums' }}>
                  {r.rows != null ? r.rows.toLocaleString() : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table></div>
      </>)}
    </div>
  )
}

/** A manual refresh that a blocking check stopped: what failed, and the choice. */
export function ChecksBlockedDialog({ detail, checks, onPublish, onKeep }: {
  detail: string; checks: CheckResult[]; onPublish: () => void; onKeep: () => void
}) {
  const t = useT()
  return (
    <div role="alertdialog" aria-labelledby="checks-blocked-title" className="card"
      style={{ padding: 14, margin: '10px 0', borderColor: BAD }}>
      <div id="checks-blocked-title" style={{ fontWeight: 600, color: BAD, marginBottom: 4 }}>{t('checks.blockedTitle')}</div>
      <div style={{ fontSize: 12.5, color: 'var(--muted)' }}>{t('checks.blockedBody')}</div>
      <CheckResultList results={checks.length ? checks : [{ kind: 'rule', column: null, severity: 'block', passed: false, detail }]} />
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 10 }}>
        <button type="button" className="btn btn-ghost btn-sm" onClick={onKeep}>{t('checks.keep')}</button>
        <button type="button" className="btn btn-sm" onClick={onPublish}>{t('checks.publishAnyway')}</button>
      </div>
    </div>
  )
}
