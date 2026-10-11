import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { RotateCcw, X } from 'lucide-react'
import { datasetsApi, templatesApi, type Dataset, type TemplateCard, type TemplateMatch } from '../../services/api'
import { useModalDialog } from '../../components/ui/useModalDialog'
import { useT } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'
import { kindName, slotLabel, templateName } from './words'

/**
 * Template -> dashboard, in one dialog: the dataset, then which column fills
 * each slot. The server suggests a mapping from what each column IS, checks
 * every change before anything is made, and says what the result will hold:
 * how many charts, which are left out and why, which measures get defined.
 */
export default function UseTemplateDialog({ template, datasetId: initial, onClose }: {
  template: TemplateCard
  datasetId?: number | null
  onClose: () => void
}) {
  const t = useT()
  const navigate = useNavigate()
  const ref = useModalDialog<HTMLDivElement>(onClose)
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [datasetId, setDatasetId] = useState<number | null>(initial ?? null)
  const [match, setMatch] = useState<TemplateMatch | null>(null)
  const [mapping, setMapping] = useState<Record<string, string[]>>({})
  const [checking, setChecking] = useState(false)
  const [failed, setFailed] = useState(false)
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  /** A dataset for each additional dataset the template reads (optional). */
  const [others, setOthers] = useState<Record<string, number>>({})
  const seq = useRef(0)
  const title = templateName(template, t)

  useEffect(() => { datasetsApi.list().then(setDatasets).catch(() => setDatasets([])) }, [])

  const check = (id: number, chosen?: Record<string, string[]>, extra: Record<string, number> = others) => {
    const mine = ++seq.current
    setChecking(true)
    setFailed(false)
    templatesApi.match(template.ref, id, chosen, Object.keys(extra).length ? extra : undefined)
      .then(got => { if (mine === seq.current) { setMatch(got); setMapping(got.mapping) } })
      .catch(() => { if (mine === seq.current) { setMatch(null); setFailed(true) } })
      .finally(() => { if (mine === seq.current) setChecking(false) })
  }
  useEffect(() => { if (datasetId != null) check(datasetId) }, [datasetId])  // eslint-disable-line react-hooks/exhaustive-deps

  const change = (slot: string, columns: string[]) => {
    if (datasetId == null) return
    const next = { ...mapping }
    if (columns.length) next[slot] = columns
    else delete next[slot]
    setMapping(next)
    check(datasetId, next)
  }

  const labelOf = useMemo(() => {
    const by: Record<string, string> = {}
    for (const s of match?.slots ?? template.slots) by[s.id] = slotLabel(s, t)
    return (id: string) => by[id] ?? id
  }, [match, template.slots, t])

  const create = async () => {
    if (datasetId == null || !match?.check.ok || busy) return
    setBusy(true)
    try {
      const made = await templatesApi.use(template.ref, { dataset_id: datasetId, mapping, name: name.trim() || undefined,
        ...(Object.keys(others).length ? { datasets: others } : {}) })
      const left = made.dropped.length + made.refused.length
      toast.success(left ? t('tpl.use.createdSome', { n: localDigits(String(left)) }) : t('tpl.use.created'))
      navigate(`/reports/${made.report_id}?edit=1`)
    } catch {
      toast.error(t('tpl.use.failed'))
      setBusy(false)
    }
  }

  const check_ = match?.check
  return (
    <div className="dsh-scrim">
      <div ref={ref} className="dsh-dlg" role="dialog" aria-modal="true" aria-labelledby="tpl-use-t">
        <div className="dsh-dh">
          <div className="tt">
            <h2 id="tpl-use-t">{t('tpl.use.title', { name: title })}</h2>
            <p>{t('tpl.use.sub')}</p>
          </div>
          <button type="button" className="dsh-ib" onClick={onClose} aria-label={t('tpl.close')} title={t('tpl.close')}><X size={16} aria-hidden /></button>
        </div>
        <div className="dsh-db">
          <div className="tpl-row2">
            <div>
              <label className="dsh-lbl" htmlFor="tpl-use-ds">{t('tpl.use.dataset')}</label>
              <select id="tpl-use-ds" className="dsh-in" value={datasetId ?? ''} onChange={e => setDatasetId(e.target.value ? Number(e.target.value) : null)}>
                <option value="">{t('tpl.use.datasetPh')}</option>
                {datasets.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
              </select>
            </div>
            <div>
              <label className="dsh-lbl" htmlFor="tpl-use-name">{t('tpl.use.name')}</label>
              <input id="tpl-use-name" className="dsh-in" value={name} onChange={e => setName(e.target.value)} dir="auto" maxLength={255}
                placeholder={datasets.find(d => d.id === datasetId) ? `${title} — ${datasets.find(d => d.id === datasetId)!.name}` : title} />
            </div>
          </div>

          {match?.datasets?.map(d => (
            <div key={d.key} style={{ marginTop: 14 }}>
              <label className="dsh-lbl" htmlFor={`tpl-use-other-${d.key}`}>{t('tpl.use.other', { name: d.label })}</label>
              <select id={`tpl-use-other-${d.key}`} className="dsh-in" value={others[d.key] ?? ''}
                onChange={e => {
                  const next = { ...others }
                  if (e.target.value) next[d.key] = Number(e.target.value)
                  else delete next[d.key]
                  setOthers(next)
                  // A new dataset for this part: its columns are suggested afresh.
                  if (datasetId != null) check(datasetId, undefined, next)
                }}>
                <option value="">{t('tpl.use.other.none')}</option>
                {datasets.filter(x => x.id !== datasetId).map(x => <option key={x.id} value={x.id}>{x.name}</option>)}
              </select>
            </div>
          ))}

          {failed && <p className="dsh-note" role="alert">{t('tpl.use.matchFailed')}</p>}

          {match && (
            <>
              <p className="dsh-note" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ flex: 1 }}>{t('tpl.use.suggested')}</span>
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => datasetId != null && check(datasetId)}>
                  <RotateCcw size={13} aria-hidden /> {t('tpl.use.reset')}
                </button>
              </p>
              <div className="tpl-map">
                {match.slots.filter(s => !s.dataset || others[s.dataset] != null).map(s => {
                  const options = match.candidates[s.id] ?? []
                  const chosen = mapping[s.id] ?? []
                  const id = `tpl-slot-${s.id}`
                  return (
                    <div key={s.id} style={{ display: 'contents' }}>
                      <label className="lbl" htmlFor={id}>
                        <span dir="auto">{slotLabel(s, t)}</span>
                        {s.required && <span className="tpl-req" title={t('tpl.use.required')} aria-label={t('tpl.use.required')}>*</span>}
                        <small>{kindName(s.kind, t)} · {t(s.required ? 'tpl.use.required' : 'tpl.use.optional')}
                          {s.dataset && <> · {t('tpl.use.other.of', { name: match.datasets?.find(d => d.key === s.dataset)?.label ?? s.dataset })}</>}</small>
                      </label>
                      {options.length === 0 ? (
                        <span id={id} className="dsh-note" style={{ margin: 0 }}>{t('tpl.use.noCandidate')}</span>
                      ) : s.many ? (
                        <div id={id} className="tpl-many" role="group" aria-label={slotLabel(s, t)}>
                          {options.map(c => (
                            <label key={c}>
                              <input type="checkbox" checked={chosen.includes(c)}
                                onChange={e => change(s.id, e.target.checked ? [...chosen, c] : chosen.filter(x => x !== c))} />
                              <bdi>{c}</bdi>
                            </label>
                          ))}
                        </div>
                      ) : (
                        <select id={id} className="dsh-in" value={chosen[0] ?? ''} onChange={e => change(s.id, e.target.value ? [e.target.value] : [])}>
                          {!s.required && <option value="">{t('tpl.use.none')}</option>}
                          {s.required && !chosen[0] && <option value="">{t('tpl.use.none')}</option>}
                          {options.map(c => <option key={c} value={c}>{c}</option>)}
                        </select>
                      )}
                    </div>
                  )
                })}
              </div>

              <div className="tpl-sum" aria-live="polite">
                {checking ? t('tpl.use.checking') : check_ && (
                  <>
                    <strong>{t('tpl.use.willDraw', { kept: localDigits(String(check_.widgets.kept)), n: localDigits(String(check_.widgets.total)) })}</strong>
                    {check_.problems.length > 0 && (
                      <ul className="bad">
                        {check_.problems.map((p, i) => (
                          <li key={i}>{t(`tpl.p.${p.code}`, { slot: labelOf(p.slot), column: p.column ?? '' })}</li>
                        ))}
                      </ul>
                    )}
                    {match.preview && match.preview.dropped.length > 0 && (
                      <>
                        <h4>{t('tpl.use.leftOut')}</h4>
                        <ul>
                          {match.preview.dropped.map((d, i) => (
                            <li key={i}><bdi>{d.title}</bdi>{d.needs.length > 0 && <> — {t('tpl.use.leftOut.why', { what: d.needs.map(labelOf).join('، ') })}</>}</li>
                          ))}
                        </ul>
                      </>
                    )}
                    {match.preview && match.preview.measures.length > 0 && (
                      <>
                        <h4>{t('tpl.use.measures')}</h4>
                        <ul>{match.preview.measures.map(m => <li key={m.name}><bdi>{m.name}</bdi> = <code dir="ltr">{m.expression}</code></li>)}</ul>
                      </>
                    )}
                    {match.preview && match.preview.skipped_metrics.some(m => m.why === 'no_permission') && (
                      <p className="dsh-note">{t('tpl.use.noMeasures')}</p>
                    )}
                    {match.preview && match.preview.filters.length > 0 && (
                      <>
                        <h4>{t('tpl.use.filters')}</h4>
                        <ul><li><bdi>{match.preview.filters.map(f => f.column).join(', ')}</bdi></li></ul>
                      </>
                    )}
                  </>
                )}
              </div>
            </>
          )}
        </div>
        <div className="dsh-df">
          <span className="dsh-sp" />
          <button type="button" className="btn btn-ghost dsh-btn-line" onClick={onClose}>{t('common.cancel')}</button>
          <button type="button" className="btn btn-primary" disabled={busy || checking || !match?.check.ok} onClick={() => void create()}>
            {t(busy ? 'tpl.use.creating' : 'tpl.use.create')}
          </button>
        </div>
      </div>
    </div>
  )
}
