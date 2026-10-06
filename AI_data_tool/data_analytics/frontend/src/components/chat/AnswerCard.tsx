import { useEffect, useState, type ReactNode } from 'react'
import { ArrowRight, Bot, Code2, Copy, Download, Info, MoreHorizontal, ThumbsDown, ThumbsUp } from 'lucide-react'
import ActionMenu from '../ActionMenu'
import { useT } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'
import { formatProseNumber } from '../../lib/displayNumber'
import { agentApi, type AgentPresentation, type AgentResult, type AnswerEvidence, type EvidenceClaim } from '../../services/api'
import AnswerText from './AnswerText'
import ResultView, { ResultGrid, chartColumns, chartFormatFor, type EvidenceFocus } from './ResultView'
import './answerCard.css'

/**
 * One answer on the Ask AI page (redesign step 4a). The latest answer is the
 * full card: header with timing, key numbers, the sentence, the chart, the
 * rows beside "How it was worked out", SQL on request, the source line, the
 * actions and "Ask next". Older answers are compact: sentence, chart, actions.
 *
 * Everything shown is read from what the run already returned or stores:
 * the result rows (key numbers), `GET /agent/runs/{id}` (timing and steps --
 * fetched once, as "Show SQL" already did), and the server's evidence.
 * The builder's copilot mount keeps v1's rendering; this card is the page's.
 */

type Detail = Awaited<ReturnType<typeof agentApi.runDetail>>

export interface AnswerCardProps {
  full: boolean
  text: string
  runId?: number
  results?: AgentResult[]
  presentation?: AgentPresentation | null
  evidence?: AnswerEvidence | null
  focus?: EvidenceFocus | null
  onShowClaim?: (c: EvidenceClaim) => void
  datasetName?: string
  sqlable: boolean
  sqlOpen: boolean
  sqlLoading: boolean
  sql: string[]
  contextObjects?: string[] | null
  onToggleSql: () => void
  onCopy: () => void
  onCopySql: () => void
  onRetry?: () => void
  onSaveDataset?: () => void
  savingDataset?: boolean
  onCsv?: () => void
  onFile?: (f: 'xlsx' | 'pdf') => void
  addToDashboard?: ReactNode
  rating?: 'up' | 'down'
  onRate: (r: 'up' | 'down', comment?: string) => void
  source: ReactNode
  askNext: string[]
  onAsk: (q: string) => void
  busy: boolean
}

/** Highest, lowest, gap and rows back, from the answer's own rows. */
export function keyNumbers(result?: AgentResult) {
  if (!result || result.rows.length < 2) return null
  const { x, y } = chartColumns(result)
  if (!x || !y) return null
  const xi = result.columns.indexOf(x), yi = result.columns.indexOf(y)
  const rows = result.rows
    .map(r => ({ label: String(r[xi] ?? ''), value: Number(r[yi]) }))
    .filter(r => Number.isFinite(r.value))
  if (rows.length < 2) return null
  const hi = rows.reduce((a, b) => (b.value > a.value ? b : a))
  const lo = rows.reduce((a, b) => (b.value < a.value ? b : a))
  return { hi, lo, gap: hi.value - lo.value, groups: result.total }
}

// Read like the sentence: one decimal (the rows beside keep full precision).
const num = (v: number) => formatProseNumber(String(Number.isInteger(v) ? v : Number(v.toFixed(1))))

export default function AnswerCard(p: AnswerCardProps) {
  const t = useT()
  const [detail, setDetail] = useState<Detail | null>(null)
  const [why, setWhy] = useState<string | null>(null)
  useEffect(() => {
    if (!p.full || p.runId == null) return
    let on = true
    Promise.resolve().then(() => agentApi?.runDetail?.(p.runId!))
      .then(d => { if (on && d) setDetail(d) }).catch(() => {})
    return () => { on = false }
  }, [p.full, p.runId])

  const first = p.results?.[0]
  const kn = p.full ? keyNumbers(first) : null
  const charted = !!first && !!chartFormatFor(first, p.presentation) && first.total > 0
  const secs = detail?.ms != null ? localDigits((detail.ms / 1000).toFixed(1)) : null
  const traced = p.evidence?.claims.filter(c => c.status === 'traced').length ?? 0
  const claims = p.evidence?.claims.length ?? 0

  const steps: { title: string; text: string }[] = []
  if (p.full && detail) {
    const plan = detail.plan?.[0]?.question
    if (plan) steps.push({ title: t('ans3.step.understood'), text: plan })
    const queries = detail.steps.filter(s => s.sql)
    if (queries.length) {
      const repairs = queries.reduce((n, s) => n + (s.repair_attempts ?? 0), 0)
      steps.push({ title: t(queries.length === 1 ? 'ans3.step.wroteOne' : 'ans3.step.wrote', { n: localDigits(String(queries.length)) }),
        text: repairs ? t('ans3.step.repaired', { n: localDigits(String(repairs)) }) : t('ans3.step.checked') })
      const back = queries.reduce((n, s) => n + (Number(s.rows_returned) || 0), 0)
      steps.push({ title: t('ans3.step.ran'), text: t('ans3.step.rows', { n: localDigits(back.toLocaleString('en-US')) }) })
    }
    steps.push({ title: t('ans3.step.answered'),
      text: claims ? (traced === claims ? t('ans3.step.allTraced', { n: localDigits(String(claims)) })
        : t('ans3.step.someTraced', { n: localDigits(String(traced)), total: localDigits(String(claims)) }))
        : t('ans3.step.words') })
  }

  const exportItems = [
    ...(p.onCsv ? [{ key: 'csv', label: 'CSV', icon: <Download size={16} />, onSelect: p.onCsv }] : []),
    ...(p.onFile ? [
      { key: 'xlsx', label: 'Excel', icon: <Download size={16} />, onSelect: () => p.onFile!('xlsx') },
      { key: 'pdf', label: 'PDF', icon: <Download size={16} />, onSelect: () => p.onFile!('pdf') },
    ] : []),
  ]
  const moreItems = [
    ...(p.onRetry ? [{ key: 'retry', label: t('ask.retry'), onSelect: p.onRetry }] : []),
    ...(p.sqlable ? [{ key: 'copysql', label: t('ask.copySql'), onSelect: p.onCopySql }] : []),
    ...(p.onSaveDataset ? [{ key: 'save', label: p.savingDataset ? t('ans3.saving') : t('ask.saveDataset'), onSelect: p.onSaveDataset }] : []),
  ]

  return (
    <div className={`dl-ans3${p.full ? '' : ' dl-ans3--compact'}`} data-testid={p.full ? 'answer-card' : 'answer-card-compact'}>
      <header className="dl-ans3__head">
        <span className="dl-ans3__badge" aria-hidden><Bot size={14} /></span>
        <strong>{t('ans3.answer')}</strong>
        {p.datasetName && <span className="dl-ans3__muted" dir="auto">· {p.datasetName}</span>}
        {secs && <span className="dl-ans3__muted dl-ans3__end">{t('ans3.secs', { n: secs })}</span>}
      </header>

      {kn && (
        <div className="dl-ans3__keys" data-testid="key-numbers">
          <div><span>{t('ans3.k.high')}</span><strong>{num(kn.hi.value)}</strong> <em dir="auto">{kn.hi.label}</em></div>
          <div><span>{t('ans3.k.low')}</span><strong>{num(kn.lo.value)}</strong> <em dir="auto">{kn.lo.label}</em></div>
          <div><span>{t('ans3.k.gap')}</span><strong>{num(kn.gap)}</strong></div>
          <div><span>{t('ans3.k.groups')}</span><strong>{localDigits(kn.groups.toLocaleString('en-US'))}</strong></div>
        </div>
      )}

      <AnswerText text={p.text} evidence={p.evidence} onShow={p.onShowClaim} />

      {p.results && p.results.length > 0 && (
        <ResultView results={p.results} presentation={p.presentation} focus={p.focus}
          rows={p.full && charted ? 'none' : 'toggle'} />
      )}

      {p.full && (charted || steps.length > 0) && (
        <div className="dl-ans3__split">
          {charted && first && (
            <section>
              <h4>{t('ans3.rows', { n: localDigits(first.total.toLocaleString('en-US')) })}</h4>
              <ResultGrid result={first} focus={p.focus && p.focus.result === 0 ? p.focus : null} />
            </section>
          )}
          {steps.length > 0 && (
            <section data-testid="answer-steps">
              <h4>{t('ans3.how')}</h4>
              <ol className="dl-ans3__steps">
                {steps.map((s, i) => (
                  <li key={i}><span aria-hidden>{localDigits(String(i + 1))}</span><div><strong>{s.title}</strong> · {s.text}</div></li>
                ))}
              </ol>
            </section>
          )}
        </div>
      )}

      {p.sqlOpen && (
        <div className="dl-sql">
          {p.sqlLoading ? <span className="dl-chat__note">{t('common.loading')}</span>
            : p.sql.map((sql, i) => <pre key={i} dir="ltr" className="dl-sql__code">{sql}</pre>)}
          {p.contextObjects && p.contextObjects.length > 0 && (
            <div className="dl-sql__tables">{t('ans3.tables', { list: p.contextObjects.join(', ') })}</div>
          )}
        </div>
      )}

      <div className="dl-ans3__source">
        <Info size={13} aria-hidden /> {p.source}
        {traced > 0 && <span className="dl-ans3__traced">{t('ans3.tracedNote')}</span>}
      </div>

      <div className="dl-ans3__actions">
        {p.sqlable && (
          <button type="button" className="dl-act" aria-expanded={p.sqlOpen} onClick={p.onToggleSql}>
            <Code2 size={14} aria-hidden /> {p.sqlOpen ? t('ask.hideSql') : t('ask.showSql')}
          </button>
        )}
        <button type="button" className="dl-act" onClick={p.onCopy} aria-label={t('ask.copyAnswer')}>
          <Copy size={14} aria-hidden /> <span className="dl-act__text">{t('ask.copy')}</span>
        </button>
        {p.addToDashboard}
        {exportItems.length > 0 && (
          <ActionMenu label={t('ans3.export')} items={exportItems} triggerClassName="dl-act"
            trigger={<><Download size={14} aria-hidden /> {t('ans3.export')}</>} />
        )}
        {moreItems.length > 0 && (
          <ActionMenu label={t('ans3.more')} items={moreItems} triggerClassName="dl-act dl-act--icon"
            trigger={<MoreHorizontal size={14} aria-hidden />} />
        )}
        <span className="dl-actions__sep" aria-hidden />
        <button type="button" className="dl-act dl-act--icon" aria-label={t('ask.good')} title={t('ask.good')}
          aria-pressed={p.rating === 'up'} onClick={() => { setWhy(null); p.onRate('up') }}>
          <ThumbsUp size={14} aria-hidden />
        </button>
        <button type="button" className="dl-act dl-act--icon" aria-label={t('ask.bad')} title={t('ask.bad')}
          aria-pressed={p.rating === 'down'} onClick={() => { p.onRate('down'); setWhy('') }}>
          <ThumbsDown size={14} aria-hidden />
        </button>
      </div>
      {why !== null && (
        <form className="dl-ans3__why" onSubmit={e => { e.preventDefault(); if (why.trim()) { p.onRate('down', why.trim()); setWhy(null) } }}>
          <label htmlFor={`why-${p.runId}`}>{t('ans3.whatWrong')}</label>
          <input id={`why-${p.runId}`} value={why} autoFocus dir="auto" onChange={e => setWhy(e.target.value)}
            placeholder={t('ans3.whatWrongHint')} />
          <button type="submit" className="btn btn-sm" disabled={!why.trim()}>{t('ans3.sendWhy')}</button>
          <button type="button" className="btn btn-sm" onClick={() => setWhy(null)}>{t('common.cancel')}</button>
        </form>
      )}

      {p.full && p.askNext.length > 0 && (
        <div className="dl-ans3__next" role="group" aria-label={t('ans3.askNext')}>
          <span>{t('ans3.askNext')}</span>
          {p.askNext.map(q => (
            <button key={q} type="button" className="dl-chip" disabled={p.busy} onClick={() => p.onAsk(q)}>
              <ArrowRight size={13} aria-hidden className="dl-flip" /> {q}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
