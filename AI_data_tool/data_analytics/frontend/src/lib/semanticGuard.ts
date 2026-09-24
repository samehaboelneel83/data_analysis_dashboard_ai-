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

const ID_NAME = /(^id$|_id$|_key$|_uuid$|^uuid$|_code$)/i
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
