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

// THE VOCABULARY HERE IS NEUTRAL ON PURPOSE, as in backend
// services/semantic_guard.py: only words about measurement and structure (an
// id, a year, a rate, an average, a price), in English and Arabic. No noun of
// one business area: what such a column is comes from the classification the
// server stores per column (measured, asked of the model, or set by the author).
// Numbers that name something (A_NUMBER, serial_no).
const ID_NAME = /(^id$|_id$|_ref$|_key$|_uuid$|^uuid$|_code$|^number$|_number$|_no$|^(رقم|كود|معرف|مسلسل)(_|$)|(^|_)(رقم|كود|معرف)$)/i
const WORD = (name: string, words: string[]) => {
  const low = name.trim().toLowerCase().replace(/[\s\-.]+/g, '_')
  return words.some(w => low === w || low.endsWith('_' + w) || low.startsWith(w + '_') || low.includes('_' + w + '_'))
}

// ── The stored classification: what the column IS, read before its name ──────
// Mirrors backend services/semantic_guard.py (docs/suggestions/PLAN.md, phase 1).
// A column is classified once on the server (services/column_classes.py) and
// the result travels in `column_meta`; the name is only the fallback for a
// column nobody classified.
export type NumberKind = 'amount' | 'count' | 'level' | 'duration' | 'score' | 'share' | 'code'
export const NUMBER_KINDS: NumberKind[] = ['amount', 'count', 'level', 'duration', 'score', 'share', 'code']
const ADDITIVE_KINDS = new Set<string>(['amount', 'count'])
const INTENSIVE_KINDS = new Set<string>(['level', 'duration', 'score', 'share'])

type ClassEntry = {
  role?: string; role_source?: string; aggregation?: string; hidden?: boolean
  number?: string; direction?: string; level?: string; order?: string[]; outcome?: boolean; class_source?: string
  geo_level?: string
}
type MetaMap = Record<string, ClassEntry | undefined>

/** The kind of number a column was classified as, or null when nobody
 *  classified it. An authored "measure" still wins over a GUESSED code. */
export function recordedNumber(column: string | undefined | null, meta?: MetaMap): NumberKind | null {
  if (!column) return null
  const m = meta?.[column]
  const kind = m?.number
  if (!kind || !(NUMBER_KINDS as string[]).includes(kind)) return null
  if (kind === 'code' && m?.role === 'measure' && m?.role_source !== 'inferred' && m?.class_source !== 'confirmed') return null
  return kind as NumberKind
}

/** The values of an ordinal column in their real order, or null. */
export function valueOrder(column: string | undefined | null, meta?: MetaMap): string[] | null {
  if (!column) return null
  const m = meta?.[column]
  return m?.level === 'ordinal' && Array.isArray(m.order) && m.order.length ? m.order.map(String) : null
}

export function isOutcome(column: string | undefined | null, meta?: MetaMap): boolean {
  return !!column && meta?.[column]?.outcome === true
}

export function nonAdditiveKind(column: string | undefined | null, meta?: MetaMap): NonAdditiveKind | null {
  if (!column) return null
  // A stored latitude or longitude is a coordinate whatever kind of number it
  // was also given: averaged for a centre, never added up.
  const geo = meta?.[column]?.geo_level
  if (geo === 'latitude' || geo === 'longitude') return 'coordinate'
  const recorded = recordedNumber(column, meta)
  // Classified: a code is never calculated; anything else IS a quantity.
  if (recorded) return recorded === 'code' ? 'identifier' : null
  if (WORD(column, ['lat', 'latitude', 'lon', 'lng', 'long', 'longitude', 'خط_العرض', 'خط_الطول'])) return 'coordinate'
  if (ID_NAME.test(column)) return 'identifier'
  if (WORD(column, ['year', 'yr', 'fiscal_year', 'سنة', 'السنة', 'عام'])) return 'year'
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
export function semanticAggregationWarning(column: string | undefined | null, aggregation: string, meta?: MetaMap): string | null {
  const kind = nonAdditiveKind(column, meta)
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
  // How a number is MEASURED, not what business it belongs to.
  'price', 'unit_price', 'unit_cost', 'rate', 'ratio', 'percent', 'percentage', 'pct', 'share',
  'avg', 'average', 'mean', 'median', 'age', 'score', 'grade', 'rating',
  'temperature', 'temp', 'speed', 'margin', 'probability', 'prob', 'index', 'level',
  'سعر', 'السعر', 'نسبة', 'النسبة', 'معدل', 'المعدل', 'متوسط', 'المتوسط', 'عمر', 'العمر',
  'درجة', 'الدرجة', 'تقييم', 'التقييم',
]
const PER_INFIX = /(^|_)per(_|$)/i
// A distinct count already taken per row (a daily count of unique customers):
// summed over days it counts the same customer once per day. Mirrors
// _DISTINCT_SNAPSHOT in backend services/semantic_guard.py.
const DISTINCT_SNAPSHOT =
  /(^|_)(unique|distinct|dau|mau|wau)(_|$)|(^|_)active_(users|accounts|members|clients|visitors|devices|sessions)$/i
const SUMMARY_ALIASES: Record<string, string> = {
  sum: 'sum', avg: 'avg', mean: 'avg', average: 'avg', median: 'median',
  count: 'count', countd: 'countd', distinct: 'countd', nunique: 'countd',
  min: 'min', max: 'max', none: 'none', raw: 'none',
}

export function isIntensive(column: string | undefined | null, meta?: MetaMap): boolean {
  if (!column) return false
  const recorded = recordedNumber(column, meta)
  if (recorded) return INTENSIVE_KINDS.has(recorded)
  return WORD(column, INTENSIVE_WORDS) || PER_INFIX.test(column) || DISTINCT_SNAPSHOT.test(column)
}

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
  const recorded = recordedNumber(column, meta)
  if (recorded) return recorded === 'code' ? 'countd' : ADDITIVE_KINDS.has(recorded) ? 'sum' : 'avg'
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
  return nonAdditiveKind(column, meta) === 'identifier'
}

/** How a field is USED, which can differ from how it is STORED: "year" is
 *  stored as a number and used as a category. */
export type FieldUse = 'measure' | 'category' | 'date' | 'geo'

/**
 * QA6 B4: the one rule for a field's use. "year" was a category (Aa) in the
 * Fields panel, "Number" in the Data view, and a measure in Assign data --
 * three places, three answers. Now each asks this, and shows the storage
 * type beside the use where they differ ("Number · category").
 *
 * The author's role wins; a calculated field is a measure; a stored date is a
 * date; a stored number is a measure unless its name says it is an
 * identifier, a year (category) or a coordinate (geography); anything else
 * is a category.
 */
export function fieldUse(col: { name: string; dtype?: string | null }, role?: string | null): FieldUse {
  if (role === 'measure') return 'measure'
  if (role === 'geography') return 'geo'
  if (role === 'temporal') return 'date'
  if (role) return 'category'
  if (col.dtype === 'calculated') return 'measure'
  if (col.dtype === 'datetime' || col.dtype === 'date') return 'date'
  if (col.dtype === 'numeric') {
    const kind = nonAdditiveKind(col.name)
    return kind === 'coordinate' ? 'geo' : kind ? 'category' : 'measure'
  }
  return 'category'
}
