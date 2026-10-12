import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import {
  AlertTriangle, ArrowUpRight, Braces, Calendar, Check, CheckCircle2, ChevronRight, Code2, Database, FileSpreadsheet, FileText,
  Hash, Layers, LayoutDashboard, Loader2, Plus, Sparkles, ToggleLeft, Type, Upload as UploadIcon, X,
} from 'lucide-react'
import { datasetsApi } from '../services/api'
import type { BatchUploadItem, Dataset } from '../services/api'
import { formatTimeAgo, useT } from '../i18n'
import { localDigits } from '../lib/arabicFormats'
import { kindOf, nameFromFile, readPreview, readable, type ColType, type Kind, type Preview } from './upload/readFile'
import './upload/upload.css'

/**
 * Upload (autopilot step 5, design `Upload Redesign.html`): file first.
 * Choose files, review them, then import.
 *
 *  - Choose: a drop zone (and Browse); beside it, Recent uploads (the
 *    reader's own datasets that came from files) and Tips.
 *  - Review: each file with its size and whether it has been read; the name
 *    fills itself in from the file; several files can be combined into one
 *    dataset (the batch "append"). A text or JSON file shows its first rows,
 *    read in the browser -- nothing is sent or saved before Import. A
 *    day/month date that could be read either way is pointed out.
 *  - Import: the request's real progress, then the server's own work.
 *  - Done: what was made, and where to go next; or what failed, and why.
 *
 * Kept from v1: the same two endpoints and their choice (one ordinary file
 * alone, else the batch), Access as one dataset per table, the sheet choice
 * when a workbook has several, the "same name" and "same content" warnings,
 * the in-flight lock, and the per-file errors of a batch.
 *
 * Left out (no API for them; backend rows): changing a column's type, the
 * header / delimiter / encoding / date-format settings, a sample dataset,
 * and a preview of Excel, Parquet, XML and Access files before import.
 */

const ACCEPT = '.csv,.tsv,.txt,.xlsx,.xls,.json,.xml,.parquet,.mdb,.accdb'
const ALL_SHEETS = '\u0000all'

const stemOf = (f: File) => f.name.replace(/\.[^.]+$/, '')

/**
 * The base name a batch of files suggests: what their names share. The
 * server appends each file's own stem to it, so the first file's whole stem
 * would repeat ("qa_sample — qa_sample"). A shared part too short to mean
 * anything falls back to the first stem.
 */
export const batchBaseName = (picked: File[]): string => {
  const stems = picked.map(stemOf)
  if (stems.length < 2) return stems[0] ?? ''
  let i = 0
  while (i < stems[0].length && stems.every(s => s[i] === stems[0][i])) i++
  const prefix = stems[0].slice(0, i).replace(/[\s._-]+$/, '')
  return prefix.length >= 2 ? prefix : stems[0]
}

const KIND: Record<Kind, { icon: typeof FileText; tag: string }> = {
  csv: { icon: FileText, tag: 'CSV' }, xlsx: { icon: FileSpreadsheet, tag: 'XLSX' }, json: { icon: Braces, tag: 'JSON' },
  xml: { icon: Code2, tag: 'XML' }, parquet: { icon: Layers, tag: 'PARQ' }, access: { icon: Database, tag: 'MDB' }, other: { icon: FileText, tag: 'FILE' },
}
const FORMAT_NAME: Record<Kind, string> = { csv: 'CSV', xlsx: 'XLSX', json: 'JSON', xml: 'XML', parquet: 'Parquet', access: 'Access', other: '' } // i18n-ok: format names
const TYPE_ICON: Record<ColType, typeof Hash> = { num: Hash, text: Type, date: Calendar, bool: ToggleLeft }

function FileTile({ name }: { name: string }) {
  const k = kindOf(name)
  const { icon: Icon, tag } = KIND[k]
  return <span className={`dl-up-fi dl-up-fi--${k}`} aria-hidden><Icon size={16} /><span>{tag}</span></span>
}

const count = (n: number) => n.toLocaleString('en-US')
const size = (bytes: number) => localDigits(bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`)

interface Picked { file: File; preview: Preview | null | undefined /* undefined: reading */ }
type Stage = 'choose' | 'review' | 'importing' | 'done' | 'failed'

export default function Upload() {
  const t = useT()
  const [stage, setStage] = useState<Stage>('choose')
  const [files, setFiles] = useState<Picked[]>([])
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [combine, setCombine] = useState(false)
  const [drag, setDrag] = useState(false)
  const [active, setActive] = useState(0)
  const [sheets, setSheets] = useState<string[]>([])
  const [sheet, setSheet] = useState('')
  const [sent, setSent] = useState(0)
  const [made, setMade] = useState<Dataset[]>([])
  const [failures, setFailures] = useState<BatchUploadItem[]>([])
  const [problem, setProblem] = useState<string | null>(null)
  const [recent, setRecent] = useState<Dataset[]>([])
  const [taken, setTaken] = useState<Set<string>>(new Set())
  const inputRef = useRef<HTMLInputElement>(null)
  // A synchronous lock: two clicks in one tick must not upload twice.
  const inFlight = useRef(false)
  // A typed name is the reader's to keep; an automatic one follows the files.
  const nameTyped = useRef(false)

  // Recent uploads, and the names already in use (a reused name is allowed,
  // and said out loud). A failed list just means neither is shown.
  useEffect(() => {
    datasetsApi.list().then(ds => {
      setTaken(new Set(ds.map(d => d.name.trim().toLowerCase())))
      setRecent(ds.filter(d => d.filename).sort((a, b) => (b.created_at ?? '').localeCompare(a.created_at ?? '')).slice(0, 5))
    }).catch(() => {})
  }, [])
  const nameTaken = name.trim() !== '' && taken.has(name.trim().toLowerCase())

  const addFiles = (picked: File[]) => {
    if (!picked.length) return
    const next = [...files.map(f => f.file), ...picked.filter(p => !files.some(f => f.file.name === p.name && f.file.size === p.size))]
    setFiles(next.map(file => files.find(f => f.file === file) ?? { file, preview: readable(kindOf(file.name)) ? undefined : null }))
    setSheets([]); setSheet(''); setFailures([]); setProblem(null)
    if (!nameTyped.current) setName(next.length === 1 ? nameFromFile(next[0].name) : batchBaseName(next))
    setStage('review')
    // Read the new ones in the browser, for the preview.
    for (const file of picked) {
      if (!readable(kindOf(file.name))) continue
      readPreview(file)
        .then(preview => setFiles(list => list.map(f => (f.file === file ? { ...f, preview } : f))))
        .catch(() => setFiles(list => list.map(f => (f.file === file ? { ...f, preview: null } : f))))
    }
  }
  const remove = (file: File) => {
    const next = files.filter(f => f.file !== file)
    setFiles(next); setActive(0)
    if (!next.length) { reset(); return }
    if (!nameTyped.current) setName(next.length === 1 ? nameFromFile(next[0].file.name) : batchBaseName(next.map(f => f.file)))
  }
  const reset = () => {
    setStage('choose'); setFiles([]); setName(''); setDesc(''); setCombine(false); setSheets([]); setSheet('')
    setMade([]); setFailures([]); setProblem(null); setSent(0); setActive(0); nameTyped.current = false
  }

  const many = files.length > 1
  const hasAccess = files.some(f => kindOf(f.file.name) === 'access')
  const willMake = many && !combine ? files.length : 1

  const submit = async () => {
    if (inFlight.current) return
    if (!files.length) return
    if (!name.trim()) { toast.error(t('up2.needName')); return }
    inFlight.current = true
    setStage('importing'); setSent(0); setFailures([]); setProblem(null)
    const list = files.map(f => f.file)
    try {
      // One ordinary file keeps the single-file endpoint; an Access file, all
      // the sheets of a workbook, or several files go to the batch one.
      if (list.length === 1 && kindOf(list[0].name) !== 'access' && sheet !== ALL_SHEETS) {
        const ds = await datasetsApi.uploadWithProgress(list[0], name.trim(), desc, sheet || undefined, setSent)
        setMade([ds]); setStage('done')
        return
      }
      const res = await datasetsApi.uploadBatchWithProgress(list, name.trim(), desc, combine ? 'append' : 'separate', setSent)
      const bad = res.items.filter(i => i.status === 'error')
      setMade(res.items.map(i => i.dataset).filter((d): d is Dataset => !!d))
      setFailures(bad)
      setStage(bad.length ? 'failed' : 'done')
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      if (detail?.items) {
        setFailures(detail.items.filter((i: BatchUploadItem) => i.status === 'error')); setMade([])
        setStage('failed')
      } else if (Array.isArray(detail?.sheets) && detail.sheets.length) {
        // A workbook with data on several sheets: back to the review, to choose.
        setSheets(detail.sheets); setSheet(detail.sheets[0]); setStage('review')
      } else {
        setProblem(typeof detail?.message === 'string' ? detail.message : typeof detail === 'string' ? detail : String(e?.message ?? ''))
        setMade([]); setStage('failed')
      }
    } finally {
      inFlight.current = false
    }
  }

  const step = stage === 'choose' ? 0 : stage === 'review' ? 1 : 2
  const first = made[0]
  const shown = files[active]
  const pv = shown?.preview

  return (
    <div className="dl-up">
      <header className="dl-up__head">
        <div>
          <h1 className="dl-page-title">{t('up2.title')}</h1>
          <p className="dl-page-head__sub">{t('up2.sub')}</p>
        </div>
        <ol className="dl-up-steps" aria-label={t('up2.steps')}>
          {(['choose', 'review', 'import'] as const).map((s, i) => (
            <li key={s} className={i < step || stage === 'done' ? 'is-done' : i === step ? 'is-now' : ''} aria-current={i === step ? 'step' : undefined}>
              <span className="dl-up-steps__n">{i < step || stage === 'done' ? <Check size={13} aria-hidden /> : localDigits(String(i + 1))}</span>
              {t(`up2.step.${s}`)}
            </li>
          ))}
        </ol>
      </header>

      <div className="dl-up__grid">
        <main className="dl-up__main">
          <input ref={inputRef} type="file" accept={ACCEPT} multiple hidden data-testid="upload-input"
            onChange={e => { addFiles(Array.from(e.target.files ?? [])); e.target.value = '' }} />

          {stage === 'choose' && (
            <>
              <div className={`dl-up-drop${drag ? ' is-over' : ''}`}
                onDragOver={e => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)}
                onDrop={e => { e.preventDefault(); setDrag(false); addFiles(Array.from(e.dataTransfer.files)) }}>
                <span className="dl-up-drop__art" aria-hidden>
                  <FileTile name="a.csv" /><FileTile name="a.xlsx" /><FileTile name="a.json" /><UploadIcon size={30} />
                </span>
                <h2>{drag ? t('up2.release') : t('up2.drop')}</h2>
                <p>{drag ? t('up2.dropOver') : t('up2.dropSub')}</p>
                <button type="button" className="btn btn-primary" onClick={() => inputRef.current?.click()}>
                  <UploadIcon size={16} aria-hidden /> {t('up2.browse')}
                </button>
                <ul className="dl-up-drop__fmts" aria-label={t('upload.formats')}>
                  {(['csv', 'xlsx', 'json', 'xml', 'parquet', 'access'] as Kind[]).map(k => <li key={k} className={`dl-up-fmt--${k}`} dir="ltr">{FORMAT_NAME[k]}</li>)}
                </ul>
              </div>
              <div className="dl-up-db">
                <span className="dl-up-db__ic" aria-hidden><Database size={18} /></span>
                <div><b>{t('up2.dbTitle')}</b><p>{t('up2.dbSub')}</p></div>
                <Link to="/connections" className="dl-up-db__go">{t('up2.dbGo')} <ChevronRight size={15} aria-hidden className="dl-flip" /></Link>
              </div>
            </>
          )}

          {stage === 'review' && (
            <>
              <section className="dl-up-card" aria-labelledby="dl-up-files">
                <header className="dl-up-card__h">
                  <h2 id="dl-up-files">{t('up2.files')} <span className="dl-up-n" dir="ltr">{localDigits(String(files.length))}</span></h2>
                  <button type="button" className="btn btn-ghost btn-sm" onClick={() => inputRef.current?.click()}><Plus size={15} aria-hidden /> {t('up2.addMore')}</button>
                </header>
                <ul className="dl-up-files">
                  {files.map((f, i) => (
                    <li key={f.file.name + f.file.size} className={many && i === active ? 'is-on' : undefined}>
                      <FileTile name={f.file.name} />
                      <div className="dl-up-files__tx">
                        <span className="dl-up-files__nm" dir="auto">{f.file.name}</span>
                        <span className="dl-up-files__meta">
                          <span dir="ltr">{size(f.file.size)}</span>
                          {f.preview === undefined
                            ? <span className="dl-up-st"><Loader2 size={13} aria-hidden className="dl-up-spin" /> {t('up2.reading')}</span>
                            : <span className="dl-up-st is-ok"><CheckCircle2 size={13} aria-hidden /> {t('up2.read')}</span>}
                        </span>
                      </div>
                      <button type="button" className="dl-up-ib" aria-label={t('up2.remove', { name: f.file.name })} title={t('up2.remove', { name: f.file.name })}
                        onClick={() => remove(f.file)}><X size={15} aria-hidden /></button>
                    </li>
                  ))}
                </ul>
                {many && (
                  <div className={`dl-up-comb${combine ? ' is-on' : ''}`}>
                    <div className="dl-up-comb__tx">
                      <b id="dl-up-comb">{t('up2.combine')}</b>
                      <p>{t('up2.combineSub')}</p>
                    </div>
                    <button type="button" role="switch" aria-checked={combine} aria-labelledby="dl-up-comb" className="dl-up-sw" onClick={() => setCombine(c => !c)}><i /></button>
                  </div>
                )}
                <div className="dl-up-fields">
                  <label className="dl-field">
                    <span className="dl-field__label">{many && !combine ? t('up2.baseName') : t('up2.name')}</span>
                    <input className="dl-field__input" value={name} maxLength={120} dir="auto"
                      onChange={e => { nameTyped.current = e.target.value.trim().length > 0; setName(e.target.value) }}
                      aria-describedby={nameTaken ? 'dl-up-taken' : undefined} />
                  </label>
                  <label className="dl-field">
                    <span className="dl-field__label">{t('up2.desc')} <small>{t('up2.optional')}</small></span>
                    <input className="dl-field__input" value={desc} onChange={e => setDesc(e.target.value)} placeholder={t('up2.descPh')} dir="auto" />
                  </label>
                </div>
                {nameTaken && <p id="dl-up-taken" role="status" className="dl-up-note is-warn">{t('upload.nameTaken', { name: name.trim() })}</p>}
                {many && !combine && (
                  <p className="dl-up-note">{t('up2.eachNamed', { example: `${name || nameFromFile(files[0].file.name)} — ${stemOf(files[0].file)}` })}</p>
                )}
                {hasAccess && <p className="dl-up-note">{t('up2.access')}</p>}
                {sheets.length > 0 && (
                  <div className="dl-up-sheet">
                    <p className="dl-up-note is-warn" role="status">{t('up2.sheetAsk')}</p>
                    <label className="dl-field">
                      <span className="dl-field__label">{t('up2.sheet')}</span>
                      <select className="dl-field__input" value={sheet} onChange={e => setSheet(e.target.value)}>
                        {sheets.map(s => <option key={s} value={s}>{s}</option>)}
                        <option value={ALL_SHEETS}>{t('up2.allSheets')}</option>
                      </select>
                    </label>
                  </div>
                )}
              </section>

              <section className="dl-up-card" aria-labelledby="dl-up-pv">
                <header className="dl-up-card__h">
                  <h2 id="dl-up-pv">{t('up2.preview')}{pv && <small> {localDigits(t('up2.firstRows', { n: Math.min(pv.rows.length, 20) }))}</small>}</h2>
                </header>
                {many && (
                  <div className="dl-up-tabs" role="tablist" aria-label={t('up2.files')}>
                    {files.map((f, i) => (
                      <button key={f.file.name} type="button" role="tab" aria-selected={i === active} onClick={() => setActive(i)} dir="auto">{f.file.name}</button>
                    ))}
                  </div>
                )}
                {shown && (pv === undefined ? (
                  <p className="dl-up-pv__none"><Loader2 size={15} aria-hidden className="dl-up-spin" /> {t('up2.reading')}</p>
                ) : pv === null ? (
                  <p className="dl-up-pv__none">{readable(kindOf(shown.file.name)) ? t('up2.unreadable') : t('up2.noPreview', { kind: KIND[kindOf(shown.file.name)].tag })}</p>
                ) : (
                  <>
                    <p className="dl-up-pv__stats" data-testid="preview-stats">
                      <span>{localDigits(pv.total != null ? t('up2.rows', { n: count(pv.total) }) : t('up2.rowsHead', { n: pv.rows.length }))}</span>
                      <span>{localDigits(t('up2.cols', { n: pv.columns.length }))}</span>
                      <span>{localDigits(t('up2.missing', { n: pv.missing }))}</span>
                    </p>
                    {pv.ambiguousDates.length > 0 && (
                      <p className="dl-up-note is-warn" role="note"><AlertTriangle size={15} aria-hidden />
                        {t('up2.dateWarn', { cols: pv.ambiguousDates.join(', ') })}</p>
                    )}
                    <div className="dl-up-table">
                      <table>
                        <thead>
                          <tr>
                            <th aria-hidden />
                            {pv.columns.map((c, i) => {
                              const Icon = TYPE_ICON[pv.types[i]]
                              return (
                                <th key={i} title={t('up2.typeHint', { type: t(`up2.t.${pv.types[i]}`) })}>
                                  <span className={`dl-up-ti dl-up-ti--${pv.types[i]}`} aria-hidden><Icon size={12} /></span>
                                  <span dir="auto">{c}</span>
                                  <span className="dl-sr-only">{t(`up2.t.${pv.types[i]}`)}</span>
                                </th>
                              )
                            })}
                          </tr>
                        </thead>
                        <tbody>
                          {pv.rows.map((r, i) => (
                            <tr key={i}>
                              <td className="dl-up-table__i" dir="ltr">{localDigits(String(i + 1))}</td>
                              {/* QAF 20: the cell keeps the page's direction (so a column
                                  aligns as one); the value is isolated inside it. */}
                              {r.map((v, j) => <td key={j} className={pv.types[j] === 'num' ? 'is-num' : undefined}>
                                <bdi dir={pv.types[j] === 'num' || pv.types[j] === 'date' ? 'ltr' : 'auto'}>{v}</bdi></td>)}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                ))}
              </section>

              <div className="dl-up-bar">
                <span>{localDigits(t('up2.ready', { n: willMake }))}</span>
                <span className="dl-up-grow" />
                <button type="button" className="btn btn-ghost" onClick={reset}>{t('up2.cancel')}</button>
                <button type="button" className="btn btn-primary" onClick={() => void submit()} disabled={files.some(f => f.preview === undefined)}>
                  <UploadIcon size={16} aria-hidden /> {localDigits(t('up2.import', { n: willMake }))}
                </button>
              </div>
            </>
          )}

          {stage === 'importing' && (
            <section className="dl-up-card dl-up-imp" aria-busy="true" aria-live="polite">
              <h2>{t('up2.importing', { name: name.trim() })}</h2>
              <p className="dl-up-muted">{t('up2.keepOpen')}</p>
              <div className="dl-up-prog" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(sent * 100)}
                aria-label={t('up2.s.uploading')}><i style={{ transform: `scaleX(${sent})` }} /></div>
              <ol className="dl-up-imp__steps">
                <li className="is-done"><CheckCircle2 size={16} aria-hidden /> {t('up2.s.reading')}</li>
                <li className={sent >= 1 ? 'is-done' : 'is-now'}>
                  {sent >= 1 ? <CheckCircle2 size={16} aria-hidden /> : <Loader2 size={16} aria-hidden className="dl-up-spin" />} {t('up2.s.uploading')}
                  {sent < 1 && <span className="dl-up-grow" />}{sent < 1 && <span dir="ltr">{localDigits(`${Math.round(sent * 100)}%`)}</span>}
                </li>
                <li className={sent >= 1 ? 'is-now' : ''}>
                  {sent >= 1 ? <Loader2 size={16} aria-hidden className="dl-up-spin" /> : <span className="dl-up-dot" aria-hidden />} {t('up2.s.saving')}
                </li>
              </ol>
            </section>
          )}

          {stage === 'done' && first && (
            <section className="dl-up-card dl-up-done" role="status">
              <span className="dl-up-done__ok" aria-hidden><Check size={30} /></span>
              <h2>{made.length > 1 ? localDigits(t('up2.doneMany', { n: made.length })) : t('up2.doneTitle')}</h2>
              {made.length === 1 ? (
                <>
                  <p>{(() => { const [a, b = ''] = t('up2.doneSub', { name: '\uE000' }).split('\uE000'); return <>{a}<bdi><b>{first.name}</b></bdi>{b}</> })()}</p>
                  <ul className="dl-up-chips">
                    <li dir="ltr">{localDigits(t('up2.rows', { n: count(first.row_count ?? 0) }))}</li>
                    <li dir="ltr">{localDigits(t('up2.cols', { n: count(first.col_count ?? 0) }))}</li>
                    {!!first.file_size && <li dir="ltr">{size(first.file_size)}</li>}
                  </ul>
                </>
              ) : (
                <ul className="dl-up-made">
                  {made.map(d => <li key={d.id}><Link to={`/datasets/${d.id}?new=1`} dir="auto">{d.name}</Link></li>)}
                </ul>
              )}
              {made.filter(d => d.duplicate_of).map(d => (
                <p key={d.id} className="dl-up-note is-warn" role="note"><AlertTriangle size={15} aria-hidden /> <bdi>{d.name}</bdi>: {t('up2.dup', { other: d.duplicate_of!.name })}</p>
              ))}
              <div className="dl-up-next">
                <Link to={`/datasets/${first.id}?new=1`} className="dl-up-next__c"><ArrowUpRight size={18} aria-hidden className="dl-flip" /><b>{t('up2.open')}</b><small>{t('up2.openSub')}</small></Link>
                <Link to={`/ask?dataset=${first.id}`} className="dl-up-next__c"><Sparkles size={18} aria-hidden /><b>{t('up2.ask')}</b><small>{t('up2.askSub')}</small></Link>
                <Link to="/reports?new=1" className="dl-up-next__c"><LayoutDashboard size={18} aria-hidden /><b>{t('up2.dash')}</b><small>{t('up2.dashSub')}</small></Link>
                <button type="button" className="dl-up-next__c" onClick={reset}><UploadIcon size={18} aria-hidden /><b>{t('up2.another')}</b><small>{t('up2.anotherSub')}</small></button>
              </div>
            </section>
          )}

          {stage === 'failed' && (
            <section className="dl-up-card dl-up-err" role="alert">
              <span className="dl-up-err__ic" aria-hidden><AlertTriangle size={22} /></span>
              <div className="dl-up-err__bd">
                <h2>{t('up2.errTitle', { name: name.trim() })}</h2>
                {failures.length > 0 ? (
                  <>
                    {made.length > 0 && <p>{localDigits(t('up2.errSome', { ok: made.length, bad: failures.length }))}</p>}
                    <p className="dl-up-muted">{t('up2.errSub')}</p>
                    <ul className="dl-up-errs">
                      {failures.map((f, i) => <li key={i}><b dir="auto">{f.source_filename}</b> <span dir="auto">{f.error}</span></li>)}
                    </ul>
                  </>
                ) : (
                  <p className="dl-up-muted">{t('upload.failed')}</p>
                )}
                {problem && (
                  <details className="dl-up-td">
                    <summary><ChevronRight size={15} aria-hidden className="dl-flip" /> {t('up2.details')}</summary>
                    <pre dir="ltr">{problem}</pre>
                  </details>
                )}
                <div className="dl-up-err__acts">
                  <button type="button" className="btn btn-primary" onClick={() => setStage('review')}>{t('up2.retry')}</button>
                  <button type="button" className="btn btn-ghost" onClick={() => { reset(); requestAnimationFrame(() => inputRef.current?.click()) }}>{t('up2.other')}</button>
                  {made.length > 0 && <Link to={`/datasets/${made[0].id}?new=1`} className="btn btn-ghost">{t('up2.open')}</Link>}
                </div>
              </div>
            </section>
          )}
        </main>

        <aside className="dl-up__side">
          <section className="dl-up-card">
            <header className="dl-up-card__h">
              <h2>{t('up2.recent')}</h2>
              <Link to="/datasets" className="dl-up-link">{t('up2.viewAll')}</Link>
            </header>
            {recent.length ? (
              <ul className="dl-up-recent">
                {recent.map(d => (
                  <li key={d.id}>
                    <FileTile name={d.filename ?? ''} />
                    <Link to={`/datasets/${d.id}`} className="dl-up-recent__tx">
                      <span dir="auto">{d.name}</span>
                      <small><span className="dl-up-dot is-ok" aria-hidden /> {localDigits(t('up2.imported', { when: formatTimeAgo(d.created_at, t) ?? '' }))}</small>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : <p className="dl-up-muted">{t('up2.noRecent')}</p>}
          </section>
          <section className="dl-up-card">
            <header className="dl-up-card__h"><h2>{t('up2.tips')}</h2></header>
            <ul className="dl-up-tips">
              {(['up2.tip1', 'up2.tip2', 'up2.tip3'] as const).map(k => <li key={k}><Check size={15} aria-hidden /> {t(k)}</li>)}
            </ul>
          </section>
        </aside>
      </div>
    </div>
  )
}
