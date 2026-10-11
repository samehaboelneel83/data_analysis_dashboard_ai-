import { useEffect, useState } from 'react'
import { useT, type MessageKey } from '../../i18n'
import { decisionApi, type DecisionChoices, type DecisionShape, type DecisionSpecification } from '../../services/api'

/**
 * A decision the table has the SHAPE of (server: services/discovery/decision.py):
 * a choice among options, or a matching of two sets. The person says what to
 * make large or small and what is limited; the platform checks that on the
 * rows and writes the problem down as a document a solver can read.
 *
 * Nothing is solved here and nothing is guessed: every role a column plays is
 * the one chosen in this form. What was written is said in plain words first;
 * the document itself is behind "Show details".
 */
export default function DecisionProblemPanel({ datasetId }: { datasetId: number }) {
  const t = useT()
  const [shapes, setShapes] = useState<DecisionShape[] | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    let live = true
    setShapes(null); setFailed(false)
    decisionApi.problems(datasetId).then(r => { if (live) setShapes(r.problems) }).catch(() => { if (live) setFailed(true) })
    return () => { live = false }
  }, [datasetId])
  return (
    <section data-testid="decision-panel">
      <h2 style={{ fontSize: 15, fontWeight: 700, margin: '0 0 4px' }}>{t('dcp.title')}</h2>
      <p style={{ fontSize: 12, color: 'var(--muted)', margin: '0 0 14px', maxWidth: 680 }}>{t('dcp.lead')}</p>
      {failed && <p role="alert" style={{ fontSize: 13 }}>{t('dcp.failed')}</p>}
      {shapes && shapes.length === 0 && (
        <div className="card" data-testid="decision-none" style={{ padding: 16, fontSize: 13, maxWidth: 680 }}>
          <b>{t('dcp.none')}</b>
          <ul style={{ margin: '8px 0 0', paddingInlineStart: 18, color: 'var(--muted)', fontSize: 12 }}>
            <li>{t('dcp.shape.allocation')}</li>
            <li>{t('dcp.shape.assignment')}</li>
          </ul>
        </div>
      )}
      {(shapes ?? []).map((s, i) => <Problem key={i} datasetId={datasetId} shape={s} />)}
    </section>
  )
}

function Problem({ datasetId, shape }: { datasetId: number; shape: DecisionShape }) {
  const t = useT()
  const numbers = shape.problem === 'allocation' ? shape.amounts : shape.numbers
  const [objective, setObjective] = useState(numbers[0] ?? '')
  const [direction, setDirection] = useState<'largest' | 'smallest'>(shape.problem === 'allocation' ? 'largest' : 'smallest')
  const [limited, setLimited] = useState(shape.problem === 'allocation' ? (shape.amounts[1] ?? '') : '')
  const [limit, setLimit] = useState('')
  const [atMost, setAtMost] = useState('')
  const [eachFrom, setEachFrom] = useState<'exactly_one' | 'at_most_one'>('at_most_one')
  const [eachTo, setEachTo] = useState('1')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [spec, setSpec] = useState<DecisionSpecification | null>(null)
  const [open, setOpen] = useState(false)

  const write = async () => {
    setBusy(true); setError(null); setSpec(null)
    const body: DecisionChoices = shape.problem === 'allocation'
      ? { problem: 'allocation', key: shape.key, objective, direction,
          ...(limited ? { limited } : {}), ...(limit !== '' ? { limit: Number(limit) } : {}),
          ...(atMost !== '' ? { at_most: Number(atMost) } : {}) }
      : { problem: 'assignment', from_col: shape.from, to_col: shape.to, objective, direction, each_from: eachFrom,
          ...(eachTo !== '' ? { each_to_at_most: Number(eachTo) } : {}) }
    try { setSpec(await decisionApi.specification(datasetId, body)) }
    catch (e) {
      const detail = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : t('dcp.failed'))
    }
    finally { setBusy(false) }
  }
  const download = () => {
    if (!spec) return
    const url = URL.createObjectURL(new Blob([JSON.stringify(spec, null, 2)], { type: 'application/json' }))
    const a = document.createElement('a')
    a.href = url; a.download = `decision-problem-${datasetId}.json`; a.click()
    URL.revokeObjectURL(url)
  }
  const label = { display: 'block', fontSize: 12, color: 'var(--muted)', margin: '10px 0 2px' } as const
  const n = (v: number) => v.toLocaleString()
  return (
    <div className="card" data-testid={`decision-${shape.problem}`} style={{ padding: 16, marginBottom: 14, maxWidth: 680 }}>
      <b style={{ fontSize: 14 }}>
        {shape.problem === 'allocation' ? t('dcp.alloc.title', { n: n(shape.options) }) : t('dcp.assign.title', { a: shape.from, b: shape.to })}
      </b>
      <p style={{ fontSize: 12, color: 'var(--muted)', margin: '4px 0 0' }}>
        {shape.problem === 'allocation' ? t('dcp.alloc.what', { k: shape.key }) : t('dcp.assign.what', { a: shape.from, b: shape.to, n: n(shape.pairs) })}
      </p>

      <label style={label} htmlFor={`dcp-obj-${shape.problem}`}>{t('dcp.objective')}</label>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <select id={`dcp-obj-${shape.problem}`} value={objective} onChange={e => setObjective(e.target.value)}>
          {numbers.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <select aria-label={t('dcp.direction')} value={direction} onChange={e => setDirection(e.target.value as 'largest' | 'smallest')}>
          <option value="largest">{t('dcp.largest')}</option>
          <option value="smallest">{t('dcp.smallest')}</option>
        </select>
      </div>

      {shape.problem === 'allocation' ? (<>
        <label style={label} htmlFor="dcp-limited">{t('dcp.limited')}</label>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <select id="dcp-limited" value={limited} onChange={e => setLimited(e.target.value)}>
            <option value="">{t('dcp.noLimited')}</option>
            {shape.amounts.filter(c => c !== objective).map(c => <option key={c} value={c}>{c}</option>)}
          </select>
          {limited && <input type="number" aria-label={t('dcp.limit')} placeholder={t('dcp.limit')} value={limit}
            onChange={e => setLimit(e.target.value)} style={{ width: 160 }} />}
        </div>
        <label style={label} htmlFor="dcp-atmost">{t('dcp.atMost')}</label>
        <input id="dcp-atmost" type="number" min={1} value={atMost} onChange={e => setAtMost(e.target.value)} style={{ width: 160 }} />
      </>) : (<>
        <label style={label} htmlFor="dcp-eachfrom">{t('dcp.eachFrom', { a: shape.from })}</label>
        <select id="dcp-eachfrom" value={eachFrom} onChange={e => setEachFrom(e.target.value as 'exactly_one' | 'at_most_one')}>
          <option value="at_most_one">{t('dcp.atMostOne')}</option>
          <option value="exactly_one">{t('dcp.exactlyOne')}</option>
        </select>
        <label style={label} htmlFor="dcp-eachto">{t('dcp.eachTo', { b: shape.to })}</label>
        <input id="dcp-eachto" type="number" min={1} value={eachTo} onChange={e => setEachTo(e.target.value)} style={{ width: 160 }} />
      </>)}

      <div style={{ marginTop: 14 }}>
        <button type="button" className="btn btn-primary btn-sm" disabled={busy || !objective} onClick={() => void write()}>
          {busy ? t('dcp.writing') : t('dcp.write')}
        </button>
      </div>
      {error && <p role="alert" dir="auto" style={{ fontSize: 12, color: 'var(--danger)', margin: '10px 0 0' }}>{error}</p>}

      {spec && (
        <div data-testid="decision-spec" style={{ marginTop: 14, borderTop: '1px solid var(--border)', paddingTop: 12, fontSize: 13 }}>
          <b>{t('dcp.written')}</b>
          <ul style={{ margin: '6px 0 0', paddingInlineStart: 18 }}>
            <li>{t(spec.objective.direction === 'maximize' ? 'dcp.say.max' : 'dcp.say.min', { c: spec.objective.column })}</li>
            <li>{spec.problem === 'allocation' ? t('dcp.say.choose', { n: n(spec.decisions.count) }) : t('dcp.say.pairs', { n: n(spec.decisions.count) })}</li>
            {spec.constraints.map((c, i) => (
              <li key={i}>{t(`dcp.con.${c.kind}${c.rule ? `.${c.rule}` : ''}` as MessageKey,
                { c: c.column ?? '', v: c.value != null ? n(c.value) : '' })}</li>
            ))}
          </ul>
          {spec.checks.length > 0 && (
            <ul data-testid="decision-checks" style={{ margin: '8px 0 0', paddingInlineStart: 18, fontSize: 12, color: 'var(--muted)' }}>
              {spec.checks.map((c, i) => (
                <li key={i}>{t(`dcp.chk.${c.code}` as MessageKey, { c: c.column ?? '', rows: n(c.rows ?? 0), options: n(c.options ?? 0),
                  of: n(c.of ?? 0), pairs: n(c.pairs ?? 0), total: n(c.total ?? 0) })}</li>
              ))}
            </ul>
          )}
          <p style={{ fontSize: 12, color: 'var(--muted)', margin: '8px 0 0' }}>{t('dcp.notSolved')}</p>
          <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
            <button type="button" className="btn btn-sm" onClick={download}>{t('dcp.download')}</button>
            <button type="button" className="btn btn-ghost btn-sm" aria-expanded={open} onClick={() => setOpen(o => !o)}>
              {open ? t('dcp.hide') : t('dcp.show')}
            </button>
          </div>
          {open && <pre dir="ltr" data-testid="decision-json" style={{ fontSize: 11, background: 'var(--surface2)', padding: 10, borderRadius: 6,
            overflow: 'auto', margin: '10px 0 0', maxHeight: 320 }}>{JSON.stringify(spec, null, 2)}</pre>}
        </div>
      )}
    </div>
  )
}
