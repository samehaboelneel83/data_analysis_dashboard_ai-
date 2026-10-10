import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { Check, Minus, Plus, ShieldCheck } from 'lucide-react'
import '../../pages/datasetDetail/rules.css'
import { datasetsApi, type CheckResult, type DataCheck, type DataCheckInput, type DataCheckKind,
         type DatasetRefreshRun } from '../../services/api'
import { useT, type MessageKey } from '../../i18n'
import EmptyState from '../ui/EmptyState'
import { formatDate } from '../../lib/dateFormat'

/**
 * Pipeline plan, phase 3, on the dataset page: the checks every refresh runs
 * before its new data replaces the old, a "try them now" against what the
 * dataset holds, and what past refreshes found.
 */

const KINDS: DataCheckKind[] = ['not_null', 'unique', 'accepted_values', 'row_count', 'row_drop', 'rule',
  'references', 'same_columns']
const COLUMN_KINDS: DataCheckKind[] = ['not_null', 'unique', 'accepted_values', 'references']

const GOOD = 'color-mix(in oklab, var(--positive, #4caf82) 65%, var(--text))'
const BAD = 'color-mix(in oklab, var(--negative, #e2606c) 75%, var(--text))'
const WARN = 'color-mix(in oklab, #d9a441 60%, var(--text))'

/** A check in words ("margin_pct ≤ 100"); the Overview's trust card names a failing one with it. */
export function summary(c: DataCheckInput, t: ReturnType<typeof useT>,
  /** Dataset names by id, for a `references` check; "#id" without it. */
  names?: Record<number, string>): string {
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
    case 'references': return t('checks.sum.references', { col: c.column ?? '',
      ds: (p.dataset_id != null && names?.[p.dataset_id]) || `#${p.dataset_id ?? '?'}`, ref: p.column ?? '' })
    case 'same_columns': return t(p.allow_new === false ? 'checks.sum.same_columns_strict' : 'checks.sum.same_columns')
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

export default function ChecksPanel({ datasetId, columns, canEdit, children }: {
  datasetId: number; columns: string[]; canEdit: boolean
  /** Shown at the foot of the Quality rules card (the one-off quality report). */
  children?: React.ReactNode
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
  // 2026-10-10: the dataset a `references` check compares against, and whether
  // a `same_columns` check lets a new column through.
  const [others, setOthers] = useState<{ id: number; name: string; columns: string[] }[] | null>(null)
  const [refDs, setRefDs] = useState('')
  const [refCol, setRefCol] = useState('')
  const [allowNew, setAllowNew] = useState(true)
  const names = Object.fromEntries((others ?? []).map(o => [o.id, o.name]))
  useEffect(() => {
    if (others || !(kind === 'references' || checks.some(c => c.kind === 'references'))) return
    datasetsApi.list().then(list => setOthers(list.filter(d => d.id !== datasetId)
      .map(d => ({ id: d.id, name: d.name, columns: (d.columns ?? []).map(c => c.name) })))).catch(() => setOthers([]))
  }, [kind, checks, others, datasetId])
  // The add form opens from "+ Rule" (redesign 3c), and on its own while there is nothing to list.
  const [adding, setAdding] = useState(false)

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
    if (kind === 'references') body.params = { dataset_id: Number(refDs), column: refCol }
    if (kind === 'same_columns') body.params = { allow_new: allowNew }
    setBusy(true)
    try {
      await datasetsApi.addCheck(datasetId, body)
      setAdding(false)
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
    <div className="dl-rules__checks">
      <section className="dl-rules__card">
        <header className="dl-rules__head">
          <div>
            <h3>{t('rules3.quality')}</h3>
            <p>{t('rules3.qualityCopy')}</p>
          </div>
          {canEdit && (
            <div className="dl-rules__actions">
              {checks.length > 0 && (
                <button type="button" className="btn btn-sm" disabled={busy} onClick={() => void tryNow()}
                  aria-label={t('checks.tryNow')}>{t('rules3.runNow')}</button>
              )}
              <button type="button" className="btn btn-primary btn-sm" aria-expanded={adding}
                aria-label={t('checks.add')} onClick={() => setAdding(a => !a)}>
                <Plus size={14} aria-hidden /> {t('rules3.rule')}
              </button>
            </div>
          )}
        </header>
        {tried && <p className="dl-rules__note">{t('checks.triedOn', { rows: tried.rows.toLocaleString() })}</p>}

        {checks.length === 0 && !adding && (
          canEdit
            ? <p className="dl-rules__empty">{t('checks.noneBody')}</p>
            : <EmptyState icon={ShieldCheck} title={t('checks.none')} description={t('checks.noneBody')} />
        )}

        {checks.length > 0 && (
          <ul className="dl-rules__list" data-testid="checks-table">
            {checks.map(c => {
              const r = resultFor(c)
              const state = !r ? 'none' : r.passed ? 'ok' : c.severity === 'block' ? 'bad' : 'warn'
              return (
                <li key={c.id} data-off={!c.enabled || undefined}>
                  <span className={`dl-ov__state dl-ov__state--${state}`} aria-hidden>
                    {state === 'ok' ? <Check size={12} /> : state === 'none' ? <Minus size={12} /> : '!'}
                  </span>
                  <div className="dl-rules__what">
                    <strong>{summary(c, t, names)}</strong>
                    <span>{t(`checks.kind.${c.kind}` as MessageKey)}</span>
                  </div>
                  <span className="dl-rules__result" style={{ color: state === 'bad' ? BAD : state === 'warn' ? WARN : undefined }}>
                    {!r ? (tried ? '—' : t('rules3.notRun')) : r.passed ? t('rules3.allPass') : r.detail}
                  </span>
                  {canEdit ? (
                    <select aria-label={t('checks.col.ifFails')} value={c.severity}
                      className={`dl-rules__sev dl-rules__sev--${c.severity}`}
                      onChange={e => void update(c, { severity: e.target.value as 'warn' | 'block' })}>
                      <option value="block">{t('rules3.block')}</option>
                      <option value="warn">{t('rules3.warn')}</option>
                    </select>
                  ) : (
                    <span className={`dl-rules__sev dl-rules__sev--${c.severity}`}>{t(c.severity === 'block' ? 'rules3.block' : 'rules3.warn')}</span>
                  )}
                  {canEdit && (
                    <span className="dl-rules__row-actions">
                      <label>
                        <input type="checkbox" checked={c.enabled} onChange={e => void update(c, { enabled: e.target.checked })} />{' '}
                        {t('checks.on')}
                      </label>
                      <button type="button" className="dl-ov__linkish" onClick={() => void remove(c)}>{t('checks.remove')}</button>
                    </span>
                  )}
                </li>
              )
            })}
          </ul>
        )}

        {canEdit && adding && (
          <div className="dl-rules__form">
            <div className="dl-rules__form-title">{t('checks.add')}</div>
            <div className="dl-rules__form-row">
              <label>{t('checks.kindLabel')}<br />
                <select className="input" value={kind} onChange={e => setKind(e.target.value as DataCheckKind)} style={{ fontSize: 12 }}>
                  {KINDS.map(k => <option key={k} value={k}>{t(`checks.kind.${k}` as MessageKey)}</option>)}
                </select>
              </label>
              {COLUMN_KINDS.includes(kind) && (
                <label>{t('checks.column')}<br />
                  <select className="input" value={column} onChange={e => setColumn(e.target.value)} style={{ fontSize: 12 }}>
                    {columns.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                </label>
              )}
              {kind === 'accepted_values' && (
                <label style={{ flex: 1, minWidth: 200 }}>{t('checks.values')}<br />
                  <input className="input" dir="auto" value={values} onChange={e => setValues(e.target.value)}
                    placeholder="open, closed" style={{ fontSize: 12, width: '100%' }} />
                </label>
              )}
              {kind === 'row_count' && (<>
                <label>{t('checks.min')}<br />
                  <input className="input" type="number" min={0} value={min} onChange={e => setMin(e.target.value)} style={{ fontSize: 12, width: 110 }} />
                </label>
                <label>{t('checks.max')}<br />
                  <input className="input" type="number" min={0} value={max} onChange={e => setMax(e.target.value)} style={{ fontSize: 12, width: 110 }} />
                </label>
              </>)}
              {kind === 'row_drop' && (
                <label>{t('checks.maxDrop')}<br />
                  <input className="input" type="number" min={1} max={100} value={pct} onChange={e => setPct(e.target.value)} style={{ fontSize: 12, width: 90 }} />
                </label>
              )}
              {kind === 'references' && (<>
                <label>{t('checks.refDataset')}<br />
                  <select className="input" aria-label={t('checks.refDataset')} value={refDs}
                    onChange={e => { setRefDs(e.target.value); setRefCol('') }} style={{ fontSize: 12 }}>
                    <option value="">—</option>
                    {(others ?? []).map(o => <option key={o.id} value={o.id}>{o.name}</option>)}
                  </select>
                </label>
                <label>{t('checks.refColumn')}<br />
                  <select className="input" aria-label={t('checks.refColumn')} value={refCol}
                    onChange={e => setRefCol(e.target.value)} style={{ fontSize: 12 }}>
                    <option value="">—</option>
                    {(others ?? []).find(o => String(o.id) === refDs)?.columns.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                </label>
              </>)}
              {kind === 'same_columns' && (
                <label style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 12 }}>
                  <input type="checkbox" checked={allowNew} onChange={e => setAllowNew(e.target.checked)} />
                  {t('checks.allowNew')}
                </label>
              )}
              {kind === 'rule' && (
                <label style={{ flex: 1, minWidth: 220 }}>{t('checks.rule')}<br />
                  <input className="input" dir="ltr" value={expr} onChange={e => setExpr(e.target.value)}
                    placeholder="amount >= 0" style={{ fontSize: 12, width: '100%', fontFamily: 'var(--mono)' }} />
                </label>
              )}
              <label>{t('checks.col.ifFails')}<br />
                <select className="input" value={severity} onChange={e => setSeverity(e.target.value as 'warn' | 'block')} style={{ fontSize: 12 }}>
                  <option value="block">{t('checks.block')}</option>
                  <option value="warn">{t('checks.warn')}</option>
                </select>
              </label>
              <button type="button" className="btn btn-primary btn-sm"
                disabled={busy || (kind === 'references' && (!refDs || !refCol))} onClick={() => void add()}>{t('checks.addButton')}</button>
            </div>
          </div>
        )}
        {children}
      </section>

      {canEdit && runs.length > 0 && (<>
        <h3 style={{ fontSize: 14, margin: '0 0 8px' }}>{t('checks.history')}</h3>
        <div className="card dl-table-card"><table className="dl-table" data-testid="checks-history">
          <thead><tr>
            <th>{t('jobs.history.started')}</th>
            <th>{t('jobs.history.trigger')}</th>
            <th>{t('col.status')}</th>
            <th style={{ textAlign: 'end' }}>{t('jobs.history.rows')}</th>
            <th style={{ textAlign: 'end' }}>{t('checks.speed')}</th>
          </tr></thead>
          <tbody>
            {runs.map(r => (
              <tr key={r.id}>
                <td style={{ whiteSpace: 'nowrap', verticalAlign: 'top' }}>{r.started_at ? formatDate(r.started_at) : '—'}</td>
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
                {/* How fast it went, and (2026-10-10) a run far slower than usual. */}
                <td style={{ textAlign: 'end', verticalAlign: 'top', fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}>
                  {r.duration_ms != null ? `${(r.duration_ms / 1000).toLocaleString(undefined, { maximumFractionDigits: 1 })} s` : '—'}
                  {r.metrics?.rows_per_sec != null && (
                    <div style={{ fontSize: 11, color: 'var(--muted)' }}>{t('checks.rowsPerSec', { n: r.metrics.rows_per_sec.toLocaleString() })}</div>
                  )}
                  {r.metrics?.slow && (
                    <div style={{ fontSize: 11, color: WARN }} title={t('checks.slowHint', { usual: Math.round(r.metrics.slow.median_ms / 1000) })}>
                      {t('checks.slow', { times: r.metrics.slow.times })}
                    </div>
                  )}
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
