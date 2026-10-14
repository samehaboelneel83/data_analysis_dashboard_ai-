import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Check, Download, FileWarning, Printer, RotateCcw, X } from 'lucide-react'
import { authzApi, reportsApi } from '../../../services/api'
import type { ReportPage } from '../../../types/report'
import { useModalDialog } from '../../ui/useModalDialog'
import { useT, type MessageKey } from '../../../i18n'
import { localDigits } from '../../../lib/arabicFormats'
import Thumb from '../../../pages/home/Thumb'
import './share.css'

/**
 * Export a dashboard (redesign 7c). The formats are the server's own: the
 * rendered PDF (paper, orientation, contents page, pages), the Excel
 * workbook (one sheet per chart, as the caller sees it), the offline HTML
 * package, and the browser's print view. The download is one request, so
 * "preparing" is a wait with a spinner, not invented steps.
 * Left out (no backend): PowerPoint, PNG of a page, CSV zip, choosing widgets,
 * filter summary / page numbers / AI appendix, background export and
 * download links (PLAN.md).
 */

type Format = 'pdf' | 'xlsx' | 'package' | 'print'
type Paper = 'A4' | 'Letter' | 'A3'
type Phase = 'opt' | 'busy' | 'done' | 'err'

const FORMATS: { k: Format; tag: string; bg: string; title: MessageKey; sub: MessageKey }[] = [
  { k: 'pdf', tag: 'PDF', bg: '#c2413b', title: 'shx.ex.pdf', sub: 'shx.ex.pdfSub' },
  { k: 'xlsx', tag: 'XLS', bg: '#1f7a4c', title: 'shx.ex.xlsx', sub: 'shx.ex.xlsxSub' },
  { k: 'package', tag: 'HTML', bg: '#5a67b8', title: 'shx.ex.package', sub: 'shx.ex.packageSub' },
  { k: 'print', tag: 'PRINT', bg: '#6b7280', title: 'shx.ex.print', sub: 'shx.ex.printSub' },
]

/** The server's reason, read out of a Blob response when that is what came back. */
async function reasonOf(e: unknown): Promise<string | null> {
  const data = (e as { response?: { data?: unknown } })?.response?.data
  try {
    if (data instanceof Blob) {
      const text = await new Promise<string>((ok, no) => { const r = new FileReader(); r.onload = () => ok(String(r.result)); r.onerror = no; r.readAsText(data) })
      return (JSON.parse(text) as { detail?: string }).detail ?? null
    }
    const d = (data as { detail?: unknown })?.detail
    return typeof d === 'string' ? d : null
  } catch { return null }
}

export default function ExportDialog({ report, activePageId, onClose }: {
  report: { id: number; name: string; pages: ReportPage[] }
  activePageId?: number | null
  onClose: () => void
}) {
  const t = useT()
  const navigate = useNavigate()
  const ref = useModalDialog<HTMLDivElement>(onClose)
  const pages = report.pages.filter(p => (p.page_type ?? 'normal') === 'normal')
  const [fmt, setFmt] = useState<Format>('pdf')
  const [paper, setPaper] = useState<Paper>('A4')
  const [orientation, setOrientation] = useState<'landscape' | 'portrait'>('landscape')
  const [contents, setContents] = useState(true)
  const [chosen, setChosen] = useState<number[]>(pages.map(p => p.id))
  const [phase, setPhase] = useState<Phase>('opt')
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<string>('')
  // Downloads follow the export policy; when it refuses, every download is
  // greyed with the server's reason, and Print stays (it is the browser's).
  const [blocked, setBlocked] = useState<string | null>(null)
  useEffect(() => {
    Promise.resolve().then(() => authzApi.decisions([{ resource: 'report', id: report.id, action: 'download' }]))
      .then(ds => { const d = ds?.find(x => x.action === 'download'); setBlocked(d && !d.allowed ? d.reason : null) })
      .catch(() => setBlocked(null))
  }, [report.id])
  useEffect(() => { if (blocked && fmt !== 'print') setFmt('print') }, [blocked, fmt])

  const run = async () => {
    if (fmt === 'print') { onClose(); navigate(`/reports/${report.id}/print`); return }
    setPhase('busy'); setError(null)
    try {
      if (fmt === 'pdf') {
        await reportsApi.downloadPdf(report.id, report.name, { paper, orientation, contents, pages: chosen })
        setResult(t('shx.ex.pdfReady', { n: localDigits(String(chosen.length)) }))
      } else if (fmt === 'xlsx') {
        const r = await reportsApi.downloadXlsx(report.id, report.name)
        setResult(r.withheld
          ? t('export.xlsxDoneWithheld', { n: String(r.sheets), w: String(r.withheld) })
          : t('export.xlsxDone', { n: String(r.sheets) }))
      } else {
        await reportsApi.downloadPackage(report.id, report.name)
        setResult(t('export.packageDone'))
      }
      setPhase('done')
    } catch (e) {
      setError(await reasonOf(e))
      setPhase('err')
    }
  }
  const togglePage = (id: number) => setChosen(c => c.includes(id) ? c.filter(x => x !== id) : [...c, id])
  const seg = <T extends string>(value: T, options: [T, MessageKey][], onChange: (v: T) => void, label: string) => (
    <div className="shx-seg" role="group" aria-label={label}>
      {options.map(([k, l]) => <button key={k} type="button" aria-pressed={value === k} onClick={() => onChange(k)}>{t(l)}</button>)}
    </div>
  )
  const close = <button type="button" className="shx-ib" onClick={onClose} aria-label={t('hm.close')} title={t('hm.close')}><X size={16} aria-hidden /></button>
  const ext = fmt === 'pdf' ? 'pdf' : fmt === 'xlsx' ? 'xlsx' : 'html'

  if (phase !== 'opt') {
    return (
      <div className="shx-scrim">
        <div ref={ref} className="shx-dlg sm" role="dialog" aria-modal="true" aria-label={t('shx.ex.title', { name: report.name })} aria-busy={phase === 'busy' || undefined}>
          <div className="shx-h" style={{ paddingBottom: 0 }}><div className="tt" />{close}</div>
          {phase === 'busy' && (
            <div className="shx-state" role="status">
              <span className="shx-spin" aria-hidden />
              <h3>{t('shx.ex.busy')}</h3>
              <p>{t('shx.ex.busySub')}</p>
            </div>
          )}
          {phase === 'done' && (
            <div className="shx-state" role="status">
              <span className="ok" aria-hidden><Check size={26} /></span>
              <h3>{t('shx.ex.done')}</h3>
              <p>{result}</p>
              <p dir="ltr" style={{ fontWeight: 600, color: 'var(--text)' }}>{report.name}.{ext}</p>
              <div className="acts"><button type="button" className="btn btn-primary" onClick={onClose}>{t('shx.done')}</button></div>
            </div>
          )}
          {phase === 'err' && (
            <div className="shx-state" role="alert">
              <span className="ok er" aria-hidden><FileWarning size={26} /></span>
              <h3>{t('shx.ex.failed')}</h3>
              <p>{error ?? t('shx.ex.failedSub')}</p>
              <div className="acts">
                <button type="button" className="btn btn-primary" onClick={() => void run()}><RotateCcw size={14} aria-hidden />{t('shx.ex.retry')}</button>
                <button type="button" className="btn btn-ghost" onClick={() => setPhase('opt')}>{t('shx.ex.back')}</button>
              </div>
            </div>
          )}
        </div>
      </div>
    )
  }

  const shown = pages.filter(p => fmt !== 'pdf' || chosen.includes(p.id))
  const first = shown.find(p => p.id === activePageId) ?? shown[0]
  return (
    <div className="shx-scrim" onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div ref={ref} className="shx-dlg wide" role="dialog" aria-modal="true" aria-label={t('shx.ex.title', { name: report.name })}>
        <div className="shx-h"><div className="tt"><h2>{t('shx.ex.title', { name: report.name })}</h2></div>{close}</div>
        <div className="shx-ex">
          <div className="shx-b">
            <div className="shx-sec">{t('shx.ex.format')}</div>
            <div className="shx-fmt" role="radiogroup" aria-label={t('shx.ex.format')}>
              {FORMATS.map(f => (
                <button key={f.k} type="button" role="radio" aria-checked={fmt === f.k} className="shx-fc" onClick={() => setFmt(f.k)}
                  disabled={!!blocked && f.k !== 'print'} title={blocked && f.k !== 'print' ? blocked : undefined}>
                  <span className="ic" style={{ background: f.bg }} aria-hidden>{f.tag}</span>
                  <span className="tx"><b>{t(f.title)}</b>{t(f.sub)}</span>
                </button>
              ))}
            </div>
            {blocked && <p className="shx-note" role="note">{blocked}</p>}
            {fmt === 'pdf' && (<>
              <div className="shx-row"><span className="lb">{t('shx.ex.paper')}</span>{seg(paper, [['A4', 'shx.ex.a4'], ['Letter', 'shx.ex.letter'], ['A3', 'shx.ex.a3']], setPaper, t('shx.ex.paper'))}</div>
              <div className="shx-row"><span className="lb">{t('shx.ex.orientation')}</span>{seg(orientation, [['landscape', 'shx.ex.landscape'], ['portrait', 'shx.ex.portrait']], setOrientation, t('shx.ex.orientation'))}</div>
              <div className="shx-row"><label className="shx-ck"><input type="checkbox" checked={contents} onChange={e => setContents(e.target.checked)} />{t('shx.ex.contents')}</label></div>
              {pages.length > 1 && (<>
                <div className="shx-sec">{t('shx.ex.pages')}</div>
                <div className="shx-pgs" role="group" aria-label={t('shx.ex.pages')}>
                  {pages.map(p => (
                    <button key={p.id} type="button" className="shx-pg" aria-pressed={chosen.includes(p.id)} onClick={() => togglePage(p.id)}>
                      {chosen.includes(p.id) && <Check size={13} aria-hidden />}<bdi>{p.title || p.name}</bdi>
                    </button>
                  ))}
                </div>
                {chosen.length === 0 && <p className="shx-err" role="alert">{t('shx.ex.nonePicked')}</p>}
              </>)}
            </>)}
            {fmt === 'xlsx' && <p className="shx-note">{t('shx.ex.xlsxNote')}</p>}
            {fmt === 'package' && <p className="shx-note">{t('shx.ex.packageNote')}</p>}
            {fmt === 'print' && <p className="shx-note">{t('shx.ex.printNote')}</p>}
          </div>
          <div className="shx-pv" aria-label={t('shx.ex.preview')}>
            <span className="lb">{t('shx.ex.preview')}</span>
            {first ? (
              <div className={`shx-sheet${fmt === 'pdf' && orientation === 'portrait' ? ' pt' : ''}`} dir="ltr">
                <div className="sh"><bdi>{report.name}</bdi><span><bdi>{first.title || first.name}</bdi></span></div>
                <Thumb widgets={first.widgets ?? []} />
              </div>
            ) : <p className="shx-note">{t('shx.ex.nothing')}</p>}
            {fmt === 'pdf' && pages.length > 1 && (
              <div className="shx-thumbs">{pages.map((p, i) => <span key={p.id} data-on={chosen.includes(p.id) || undefined}>{localDigits(String(i + 1))}</span>)}</div>
            )}
            <p className="shx-note" style={{ marginTop: 0 }}>{t('shx.ex.asYouSee')}</p>
          </div>
        </div>
        <div className="shx-f">
          <span className="shx-note" style={{ margin: 0 }}>
            {fmt === 'pdf' ? t('shx.ex.nPages', { n: localDigits(String(chosen.length)) }) : ''}
          </span>
          <span className="shx-sp" />
          <button type="button" className="btn btn-ghost" onClick={onClose}>{t('common.cancel')}</button>
          <button type="button" className="btn btn-primary" onClick={() => void run()}
            disabled={(fmt === 'pdf' && chosen.length === 0) || (!!blocked && fmt !== 'print')}>
            {fmt === 'print' ? <Printer size={14} aria-hidden /> : <Download size={14} aria-hidden />}
            {t(fmt === 'pdf' ? 'shx.ex.goPdf' : fmt === 'xlsx' ? 'shx.ex.goXlsx' : fmt === 'package' ? 'shx.ex.goPackage' : 'shx.ex.goPrint')}
          </button>
        </div>
      </div>
    </div>
  )
}
