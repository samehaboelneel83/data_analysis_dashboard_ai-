import { nonAdditiveKind } from '../../lib/semanticGuard'
import type { Dataset } from '../../services/api'

/**
 * Whether a column's NAME says it identifies rows rather than measures them.
 * There is no uniqueness signal on the frontend (DatasetColumn.stats is always
 * empty), so the name is the signal: `sample_id`, `cohort_ref`, `invoice_no`,
 * `item_num`, `region_code`, `order_key`.
 */
export const looksLikeIdentifier = (name: string) =>
  /(^|_)(id|uuid|guid|pk|ref)$/i.test(name)
  || /_(no|num|code|key)$/i.test(name)
  || /^(id|index|row_?num(ber)?)$/i.test(name)

export interface OutcomePick {
  /** The column to explain, or null: then nothing runs until the reader picks. */
  target: string | null
  /** Why it was picked, for the line under the picker. */
  reason: 'marked' | 'measure' | 'inferred' | null
  /** Numeric columns skipped because their names read as identifiers. */
  skipped: string[]
}

/**
 * The outcome Key influencers opens on (redesign step 2, KI-1).
 *
 * In order: the column recorded as most worth explaining (`column_targets`,
 * higher priority first); then a column the author set as a measure; then the
 * inferred rule -- numeric, not identifier-like, not a coordinate or year by
 * the semantic veto, and not all empty.
 *
 * There is deliberately NO fallback past that. The old default reached for an
 * identifier as a last resort ("better than none"), and the result was a
 * confident 1.00x table explaining `cohort_ref` -- an answer to nobody's
 * question. When nothing qualifies the reader picks, and nothing auto-runs.
 */
export function pickInfluencerOutcome(ds: Dataset): OutcomePick {
  const names = new Set(ds.columns.map(c => c.name))
  const numeric = ds.columns.filter(c => c.dtype === 'numeric')
  const skipped = numeric.filter(c => looksLikeIdentifier(c.name)).map(c => c.name)

  const marked = Object.entries(ds.column_targets ?? {})
    .filter(([name]) => names.has(name))
    .sort((a, b) => b[1] - a[1])[0]?.[0]
  if (marked) return { target: marked, reason: 'marked', skipped }

  const measure = ds.columns.find(c => ds.column_meta?.[c.name]?.role === 'measure')?.name
  if (measure) return { target: measure, reason: 'measure', skipped }

  const inferred = numeric.find(c => !looksLikeIdentifier(c.name) && nonAdditiveKind(c.name) === null
                                     && (c.missing_pct ?? 0) < 100)?.name
  if (inferred) return { target: inferred, reason: 'inferred', skipped }
  return { target: null, reason: null, skipped }
}
