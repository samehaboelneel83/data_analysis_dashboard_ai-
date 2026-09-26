import { AlertTriangle } from 'lucide-react'
import type { ReactNode } from 'react'
import { useT, type MessageKey, type TranslateFn } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'
import type { AnswerEvidence, EvidenceClaim } from '../../services/api'
import './answerEvidence.css'

/**
 * The answer's words, with its numbers picked out. The numbers are the part a
 * reader scans for ("12,400", "38%"), so each gets a quiet highlight -- and
 * dir="ltr", so "1,234.5" and "-3%" keep their shape inside an Arabic sentence.
 * Text only: no markup from the model is ever interpreted.
 *
 * E11: when the server traced the answer's numbers (`evidence`), each one it
 * found in the result rows is a button that shows the cell it came from, and
 * each it found nowhere is marked, with a note under the answer. The words are
 * the model's; the reader can see which numbers are the query's.
 */
const NUM = /([-+]?\d[\d,]*(?:\.\d+)?%?)/g

/** What a traced number is, in the reader's words. Rows count from 1. */
export function describeClaim(c: EvidenceClaim, t: TranslateFn): string {
  const s = c.source
  if (c.status === 'untraced' || !s) return t('ask.ev.notFound')
  const row = s.row != null ? localDigits(String(s.row + 1)) : ''
  const other = s.rows && s.rows.length > 1 ? localDigits(String(s.rows[1] + 1)) : ''
  return t(`ask.ev.${s.kind}` as MessageKey,
    { column: s.column ?? '', row, other })
}

/** The claims as spans over `text`, or null when they do not fit it (an
 *  answer edited since it was traced): then the plain highlight is used.
 *  The server counts characters (code points); a JS string counts UTF-16
 *  units, which differ after an emoji, so the offsets are converted. */
function spans(text: string, evidence?: AnswerEvidence | null): EvidenceClaim[] | null {
  if (!evidence) return null
  const units: number[] = [0]
  for (const ch of text) units.push(units[units.length - 1] + ch.length)
  const at16 = (i: number) => units[Math.min(i, units.length - 1)]
  const sorted = [...evidence.claims]
    .map(c => ({ ...c, start: at16(c.start), end: at16(c.end) }))
    .sort((a, b) => a.start - b.start)
  let at = 0
  for (const c of sorted) {
    if (c.start < at || text.slice(c.start, c.end) !== c.text) return null
    at = c.end
  }
  return sorted
}

export default function AnswerText({ text, evidence, onShow }: {
  text: string
  evidence?: AnswerEvidence | null
  /** Show where a traced number came from. */
  onShow?: (claim: EvidenceClaim) => void
}) {
  const t = useT()
  const claims = spans(text, evidence)
  if (!claims) {
    const parts = text.split(NUM)
    return (
      <p className="dl-answer-text" data-testid="answer-text" dir="auto">
        {parts.map((p, i) => (i % 2 === 1
          ? <mark key={i} className="dl-num" dir="ltr">{p}</mark>
          : p))}
      </p>
    )
  }
  const out: ReactNode[] = []
  let at = 0
  claims.forEach((c, i) => {
    if (c.start > at) out.push(text.slice(at, c.start))
    if (c.status === 'traced' && onShow) {
      const what = describeClaim(c, t)
      out.push(
        <button key={i} type="button" className="dl-num dl-num--traced" dir="ltr"
          data-evidence="traced" title={what} aria-label={`${c.text}: ${what}`}
          onClick={() => onShow(c)}>
          {c.text}
        </button>)
    } else if (c.status === 'untraced') {
      out.push(
        <mark key={i} className="dl-num dl-num--untraced" dir="ltr"
          data-evidence="untraced" title={t('ask.ev.notFound')}>
          {c.text}<span className="dl-sr-only"> ({t('ask.ev.notFound')})</span>
        </mark>)
    } else {
      out.push(<mark key={i} className="dl-num" dir="ltr">{c.text}</mark>)
    }
    at = c.end
  })
  if (at < text.length) out.push(text.slice(at))
  const untraced = claims.filter(c => c.status === 'untraced').length
  return (
    <>
      <p className="dl-answer-text" data-testid="answer-text" dir="auto">{out}</p>
      {untraced > 0 && (
        <p className="dl-answer-untraced" role="note" data-testid="answer-untraced">
          <AlertTriangle size={13} aria-hidden />
          {untraced === 1 ? t('ask.ev.untraced')
            : t('ask.ev.untracedMany', { n: localDigits(String(untraced)) })}
        </p>
      )}
    </>
  )
}
