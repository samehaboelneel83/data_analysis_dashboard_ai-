import type { ReactNode } from 'react'
import { useDirection } from '../../contexts/DirectionContext'
import { useT, type TranslateFn } from '../../i18n'
import { dtypeShort } from '../../lib/dtypeName'
import { localDigits } from '../../lib/arabicFormats'
import { nonAdditiveKind } from '../../lib/semanticGuard'
import { fmtStr } from '../../components/report/chartUtils'
import type { Dataset } from '../../services/api'

/**
 * A column's saved profile drawn small (redesign step 3): the distribution
 * picture and a one-line summary, shared by the Overview's "Columns at a
 * glance" and the Columns tab so the two screens never disagree.
 */

/** The saved profile (`GET /datasets/{id}/analysis`), as far as it is read here. */
export type Analysis = {
  numeric?: { columns?: Record<string, Record<string, number | null>> }
  categorical?: { columns?: Record<string, { top_values?: { value: string; count: number; pct: number }[]; n_unique?: number; missing_pct?: number }> }
  datetime?: { columns?: Record<string, { min?: string; max?: string; monthly_counts?: { period: string; count: number }[]; missing_pct?: number }> }
  overview?: { missing_pct?: number }
} | null

/** The column's type badge (NUM / DATE…), in the UI language (QA5 L3). */
export const typeTag = (t: TranslateFn, dtype: string) => dtypeShort(t, dtype)

/** Range bar for numbers, monthly bars for dates, top values for text. */
export function useColumnProfile(ds: Dataset, name: string, analysis: Analysis): { dist: ReactNode; sum: string } {
  const t = useT()
  const { language } = useDirection()
  if (!analysis) return { dist: null, sum: '' }
  const fmt = ds.column_formats?.[name]
  const num = analysis.numeric?.columns?.[name]
  const cat = analysis.categorical?.columns?.[name]
  const dt = analysis.datetime?.columns?.[name]
  // A year or an id is a label, not a quantity: "2024", never "2,024".
  const plain = !fmt && (nonAdditiveKind(name) === 'year' || nonAdditiveKind(name) === 'identifier')
  // Each value isolated (LRI…PDI): inside an Arabic sentence a range like
  // "$ -12,012 – $ 16,069" otherwise reorders around its signs and symbols.
  const iso = (x: string) => `\u2066${x}\u2069`
  const f = (v: number | null | undefined) => iso(v == null ? '—' : plain ? localDigits(String(Math.round(v))) : fmtStr(v, fmt))
  if (num) {
    return { dist: <RangeBar s={num} />, sum: t('ov3.glance.numSum', { min: f(num.min), max: f(num.max), median: f(num.median) }) }
  }
  if (dt) {
    const months = (dt.monthly_counts ?? []).slice(-21)
    const max = Math.max(1, ...months.map(m => m.count))
    // A date isolates by its own first strong letter (FSI), not forced left to
    // right: under LRI "1 يناير 2024" read backwards (QA V7). No-break spaces
    // keep each date on one line.
    const d = (s?: string) => `\u2068${s ? new Date(s).toLocaleDateString(language === 'ar' ? 'ar-u-nu-latn' : 'en-GB', { day: 'numeric', month: 'short', year: 'numeric' }).replace(/ /g, '\u00a0') : '—'}\u2069`
    return {
      dist: <span className="dl-ov__months">{months.map(m => <i key={m.period} title={`${m.period}: ${m.count}`} style={{ blockSize: `${Math.max(12, (m.count / max) * 100)}%` }} />)}</span>,
      sum: `${localDigits(d(dt.min))} – ${localDigits(d(dt.max))}`,
    }
  }
  if (cat) {
    const top = (cat.top_values ?? []).slice(0, 3)
    return {
      dist: (
        <span className="dl-ov__tops">
          {top.map(v => (
            <span key={v.value}><em dir="auto">{v.value}</em><b style={{ inlineSize: `${Math.max(4, v.pct * 0.4)}px` }} /><small>{localDigits(String(Math.round(v.pct)))}%</small></span>
          ))}
        </span>
      ),
      sum: t('ov3.glance.values', { n: localDigits(String(cat.n_unique ?? top.length)) }),
    }
  }
  return { dist: null, sum: '' }
}

/** p5–p95 line, p25–p75 box, median tick, on the column's min–max scale. */
export function RangeBar({ s }: { s: Record<string, number | null> }) {
  const lo = s.min ?? 0, hi = s.max ?? 0
  const span = hi - lo || 1
  const x = (v: number | null | undefined) => `${(((v ?? lo) - lo) / span) * 100}%`
  return (
    <svg className="dl-ov__range" viewBox="0 0 120 14" preserveAspectRatio="none" aria-hidden>
      <line x1="0" x2="120" y1="7" y2="7" className="dl-ov__range-axis" />
      <line x1={x(s.p5)} x2={x(s.p95)} y1="7" y2="7" className="dl-ov__range-whisker" />
      <rect x={x(s.p25)} y="3" width={`${Math.max(1, (((s.p75 ?? lo) - (s.p25 ?? lo)) / span) * 100)}%`} height="8" rx="1.5" className="dl-ov__range-box" />
      <line x1={x(s.median)} x2={x(s.median)} y1="1" y2="13" className="dl-ov__range-median" />
    </svg>
  )
}

