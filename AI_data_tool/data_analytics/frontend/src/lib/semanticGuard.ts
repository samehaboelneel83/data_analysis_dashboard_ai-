/**
 * The semantic veto (MASTER_PLAN Phase 0, constitution rule 3): a column can be
 * numeric without being a QUANTITY. Summing latitudes, years or customer ids
 * returns a number, every time, with no error -- and the number means nothing.
 * SAS defaults every numeric to Sum and its suggestion engine proposes summed
 * latitudes; about a third of its catalogued defects trace back to this.
 *
 * Classified by NAME, the way these columns are actually named, and mirroring
 * the backend's own rules so both halves agree: `_ID_NAME_PATTERN` in
 * services/widget_data.py, and the lat/lon words in services/dataset_profile.py.
 */
export type NonAdditiveKind = 'coordinate' | 'identifier' | 'year'

// Numbers that name something (A_NUMBER, phone_number, invoice_no) and the
// telecom identifiers a call record carries: live QA 2026-09-28 summed IMEI
// to 1.1e17 and led the insights with "66% of A_NUMBER".
// `_ref` (cohort_ref) is ahead of the backend pattern until KI-3 shares one list.
const ID_NAME = /(^id$|_id$|_ref$|_key$|_uuid$|^uuid$|_code$|^number$|_number$|_no$|(^|_)(imei|imsi|msisdn|iccid|lac)$)/i
const WORD = (name: string, words: string[]) => {
  const low = name.toLowerCase()
  return words.some(w => low === w || low.endsWith('_' + w) || low.startsWith(w + '_') || low.includes('_' + w + '_'))
}

export function nonAdditiveKind(column: string | undefined | null): NonAdditiveKind | null {
  if (!column) return null
  if (WORD(column, ['lat', 'latitude', 'lon', 'lng', 'long', 'longitude'])) return 'coordinate'
  if (ID_NAME.test(column)) return 'identifier'
  if (WORD(column, ['year', 'yr', 'fiscal_year'])) return 'year'
  return null
}

/** The aggregation that means something for each kind -- the one-click fix. */
export const SAFE_AGGREGATION: Record<NonAdditiveKind, { value: string; label: string }> = {
  coordinate: { value: 'avg', label: 'Average' },
  identifier: { value: 'countd', label: 'Distinct count' },
  year:       { value: 'max', label: 'Maximum' },
}

/** Aggregations that add values up (or average them) -- meaningless for these kinds. */
const ARITHMETIC: Record<NonAdditiveKind, Set<string>> = {
  coordinate: new Set(['sum']),
  identifier: new Set(['sum', 'avg', 'mean', 'average', 'median', 'stddev', 'variance']),
  year:       new Set(['sum', 'avg', 'mean', 'average']),
}

/** A warning for this (column, aggregation), or null when it is meaningful. */
export function semanticAggregationWarning(column: string | undefined | null, aggregation: string): string | null {
  const kind = nonAdditiveKind(column)
  if (!kind || !ARITHMETIC[kind].has((aggregation || '').toLowerCase())) return null
  const what = aggregation.toLowerCase() === 'sum' ? 'Summing' : 'Averaging'
  if (kind === 'coordinate') return `${what} ${column} adds up map coordinates — the result is not a place. Use Average for a centre point, or draw it on a map.`
  if (kind === 'identifier') return `${what} ${column} does arithmetic on identifiers — the result means nothing. Count distinct ${column} instead.`
  return `${what} ${column} adds up years — the result is not a year. Group by it, or take its Maximum.`
}

// ── Default summary: what a measure MEANS when it is rolled up ───────────────
// Mirrors `default_summary` in backend services/semantic_guard.py. HR
// evaluation, blocker 5: summing a salary by gender ("M has 60% of salary") is
// a head-count in disguise. A salary, price, rate, age or score is averaged;
// an amount, revenue, cost or count is summed.
const INTENSIVE_WORDS = [
  'salary', 'salaries', 'wage', 'wages', 'pay', 'price', 'unit_price',
  'unit_cost', 'rate', 'ratio', 'percent', 'percentage', 'pct', 'share',
  'avg', 'average', 'mean', 'median', 'age', 'score', 'grade', 'rating',
  'temperature', 'temp', 'speed', 'margin', 'probability', 'prob', 'index',
  'level', 'gpa', 'bmi', 'tenure_years',
]
const PER_INFIX = /(^|_)per(_|$)/i
// A distinct count already taken per row (a daily count of unique customers):
// summed over days it counts the same customer once per day. Mirrors
// _DISTINCT_SNAPSHOT in backend services/semantic_guard.py.
const DISTINCT_SNAPSHOT =
  /(^|_)(unique|distinct|dau|mau|wau)(_|$)|(^|_)active_(users|customers|sellers|members|accounts|subscribers|clients|visitors|devices)$/i
const SUMMARY_ALIASES: Record<string, string> = {
  sum: 'sum', avg: 'avg', mean: 'avg', average: 'avg', median: 'median',
  count: 'count', countd: 'countd', distinct: 'countd', nunique: 'countd',
  min: 'min', max: 'max', none: 'none', raw: 'none',
}

export function isIntensive(column: string | undefined | null): boolean {
  if (!column) return false
  return WORD(column, INTENSIVE_WORDS) || PER_INFIX.test(column) || DISTINCT_SNAPSHOT.test(column)
}

type MetaMap = Record<string, { role?: string; role_source?: string; aggregation?: string; hidden?: boolean } | undefined>

/** A person (or the catalog) said this column is a quantity. A role the
 *  metadata automation guessed (`role_source: 'inferred'`) does not override
 *  the veto -- it called hire_year a measure. Mirrors `marked_measure`. */
export function markedMeasure(m?: { role?: string; role_source?: string }): boolean {
  return m?.role === 'measure' && m?.role_source !== 'inferred'
}

/** How `column` rolls up when nobody said: the author's aggregation, then the
 *  role (an identifier is counted), then the name. */
export function defaultSummary(column: string | undefined | null, meta?: MetaMap): string {
  if (!column) return 'sum'
  const m = meta?.[column] ?? {}
  const agg = String(m.aggregation ?? '').trim().toLowerCase()
  if (SUMMARY_ALIASES[agg]) return SUMMARY_ALIASES[agg]
  if (m.role === 'identifier') return 'countd'
  const kind = nonAdditiveKind(column)
  if (kind && !markedMeasure(m)) return SAFE_AGGREGATION[kind].value
  return isIntensive(column) ? 'avg' : 'sum'
}

/** A recorded identifier, or one named like one and not marked a measure. */
export function isIdentifier(column: string | undefined | null, meta?: MetaMap): boolean {
  if (!column) return false
  const role = meta?.[column]?.role
  if (role === 'identifier') return true
  if (markedMeasure(meta?.[column])) return false
  return nonAdditiveKind(column) === 'identifier'
}
