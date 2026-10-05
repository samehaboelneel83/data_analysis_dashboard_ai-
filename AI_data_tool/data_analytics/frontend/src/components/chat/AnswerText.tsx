import { AlertTriangle } from 'lucide-react'
import type { ReactNode } from 'react'
import { useDirection } from '../../contexts/DirectionContext'
import { useT, type MessageKey, type TranslateFn } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'
import { majorityDir } from '../../lib/autoDir'
import { formatProseNumber } from '../../lib/displayNumber'
import { markupSpans, renderMarkup, type MarkupSpan } from '../../lib/inlineMarkup'
import type { AnswerEvidence, EvidenceClaim } from '../../services/api'
import './answerEvidence.css'

/**
 * The answer's words, with its numbers picked out. The numbers are the part a
 * reader scans for ("12,400", "38%"), so each gets a quiet highlight -- and
 * dir="ltr", so "1,234.5" and "-3%" keep their shape inside an Arabic sentence.
 *
 * Redesign step 1: the model's **bold**, *italic* and https links render (the
 * shared `lib/inlineMarkup` set, nothing more); long floats are rounded for
 * reading at render time; and the paragraph's direction is the text's majority
 * script, so an Arabic answer that opens with a data value still reads RTL.
 *
 * E11: when the server traced the answer's numbers (`evidence`), each one it
 * found in the result rows is a button that shows the cell it came from, and
 * each it found nowhere is marked, with a note under the answer. The words are
 * the model's; the reader can see which numbers are the query's.
 *
 * The claims' offsets count the RAW answer, markdown markers included, so the
 * markup is located on the raw text too and the two are merged -- the markers
 * are never stripped before the offsets are applied.
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

/** Markup that a claim would straddle is dropped (shown as typed), so a
 *  traced number always stays one whole button. */
function fitting(spans: MarkupSpan[], claims: EvidenceClaim[]): MarkupSpan[] {
  return spans
    .filter(s => claims.every(c => c.end <= s.start || c.start >= s.end
      || (c.start >= s.innerStart && c.end <= s.innerEnd)))
    .map(s => ({ ...s, children: fitting(s.children, claims) }))
}

/** Plain text with its numbers rounded for reading; `mark` highlights them. */
function numbers(text: string, key: string, mark: boolean): ReactNode[] {
  return text.split(NUM).map((p, i) => (i % 2 === 1
    ? (mark ? <mark key={`${key}-${i}`} className="dl-num" dir="ltr">{formatProseNumber(p)}</mark>
      : formatProseNumber(p))
    : p))
}

export default function AnswerText({ text, evidence, onShow }: {
  text: string
  evidence?: AnswerEvidence | null
  /** Show where a traced number came from. */
  onShow?: (claim: EvidenceClaim) => void
}) {
  const t = useT()
  const { direction } = useDirection()
  const dir = majorityDir(text, direction)
  const claims = spans(text, evidence)
  const markup = markupSpans(text, { httpsOnly: true })
  if (!claims) {
    return (
      <p className="dl-answer-text" data-testid="answer-text" dir={dir}>
        {renderMarkup(text, markup, 0, text.length, (a, b) => numbers(text.slice(a, b), `n${a}`, true))}
      </p>
    )
  }
  const claim = (c: EvidenceClaim, i: number): ReactNode => {
    const shown = formatProseNumber(c.text)
    if (c.status === 'traced' && onShow) {
      const what = describeClaim(c, t)
      return (
        <button key={`c${i}`} type="button" className="dl-num dl-num--traced" dir="ltr"
          data-evidence="traced" title={what} aria-label={`${shown}: ${what}`}
          onClick={() => onShow(c)}>
          {shown}
        </button>)
    }
    if (c.status === 'untraced') {
      return (
        <mark key={`c${i}`} className="dl-num dl-num--untraced" dir="ltr"
          data-evidence="untraced" title={t('ask.ev.notFound')}>
          {shown}<span className="dl-sr-only"> ({t('ask.ev.notFound')})</span>
        </mark>)
    }
    return <mark key={`c${i}`} className="dl-num" dir="ltr">{shown}</mark>
  }
  // Text between claims stays unhighlighted, as before; only its rounding is new.
  const leaf = (a: number, b: number): ReactNode[] => {
    const out: ReactNode[] = []
    let at = a
    claims.forEach((c, i) => {
      if (c.start < a || c.end > b) return
      if (c.start > at) out.push(...numbers(text.slice(at, c.start), `t${at}`, false))
      out.push(claim(c, i))
      at = c.end
    })
    if (at < b) out.push(...numbers(text.slice(at, b), `t${at}`, false))
    return out
  }
  const out = renderMarkup(text, fitting(markup, claims), 0, text.length, leaf)
  const untraced = claims.filter(c => c.status === 'untraced').length
  return (
    <>
      <p className="dl-answer-text" data-testid="answer-text" dir={dir}>{out}</p>
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
