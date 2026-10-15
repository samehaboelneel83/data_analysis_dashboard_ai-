import type { DatasetColumn } from '../../services/api'
import type { MessageKey } from '../../i18n'

/**
 * Starter questions for a dataset, built from its own columns.
 *
 * Nothing here is sent anywhere until the person clicks a chip -- the chip
 * then goes through the very same Send as a typed question. The templates are
 * plain and specific ("Total revenue by region") because a vague suggestion
 * ("Explore your data") teaches nothing about what the agent can do.
 */

export type Translate = (key: MessageKey, vars?: Record<string, string | number>) => string

const NUMERIC = /int|float|double|decimal|numeric|number|real/i
const DATE = /date|time/i
const ID_LIKE = /(^|_)(id|uuid|key|code)$/i

/** "order_date" -> "order date": what a person would type. */
export const humanize = (name: string) => name.replace(/[_\-.]+/g, ' ').replace(/\s+/g, ' ').trim()

export function classify(columns: Pick<DatasetColumn, 'name' | 'dtype'>[]) {
  const numeric: string[] = [], dates: string[] = [], labels: string[] = []
  for (const c of columns) {
    if (DATE.test(c.dtype) || /(^|_)(date|month|day|time|year)($|_)/i.test(c.name)) dates.push(c.name)
    else if (NUMERIC.test(c.dtype)) { if (!ID_LIKE.test(c.name)) numeric.push(c.name) }
    else if (!ID_LIKE.test(c.name)) labels.push(c.name)
  }
  return { numeric, dates, labels }
}

/** The stored classification of a column (ColumnMeta.number / .role), when known. */
export type ColumnClasses = Record<string, { number?: string; role?: string } | undefined>

const ADDS_UP = new Set(['amount', 'count'])

/* AD-11: when nothing is stored for a column, its NAME decides, by the same
 * rules the server's semantic guard uses (services/semantic_guard.py
 * _COORD_WORDS / _INTENSIVE_WORDS), plus body measures. A coordinate is never
 * a measure; a rate, share, level or body measure is averaged, never totalled. */
const COORD_WORDS = ['lat', 'latitude', 'lon', 'lng', 'long', 'longitude', 'خط_العرض', 'خط_الطول']
const INTENSIVE_WORDS = ['price', 'unit_price', 'unit_cost', 'rate', 'ratio', 'percent', 'percentage', 'pct', 'share',
  'avg', 'average', 'mean', 'median', 'age', 'score', 'grade', 'rating', 'temperature', 'temp', 'speed', 'margin',
  'probability', 'prob', 'index', 'level', 'height', 'weight', 'bmi',
  'سعر', 'السعر', 'نسبة', 'النسبة', 'معدل', 'المعدل', 'متوسط', 'المتوسط', 'عمر', 'العمر', 'درجة', 'الدرجة', 'تقييم', 'التقييم']
function nameHas(name: string, words: string[]): boolean {
  const low = name.trim().toLowerCase().replace(/[\s\-.]+/g, '_')
  return words.some(w => low === w || low.endsWith('_' + w) || low.startsWith(w + '_') || low.includes('_' + w + '_'))
}
/** The kind of number a column holds: the stored class first, else its name. */
function numberKind(c: string, classes?: ColumnClasses): string | undefined {
  const stored = classes?.[c]?.number
  if (stored) return stored
  if (nameHas(c, COORD_WORDS)) return 'coordinate'
  if (nameHas(c, INTENSIVE_WORDS) || /(^|_)per(_|$)/i.test(c)) return 'level'
  return undefined
}

/** AD-11 step 3: label columns with (nearly) a value per row -- a task name,
 *  an order number -- are not groups to compare. Read from the dataset's
 *  stored profile (GET /datasets/{id}/analysis: `categorical.columns[c].n_unique`
 *  over `overview.rows`, the rows it was computed on), which the server only
 *  returns to a reader with no row or column rule. No profile: nothing skipped. */
export const NEAR_UNIQUE = 0.9
export function nearUniqueLabels(profile: unknown): Set<string> {
  const p = profile as { overview?: { rows?: number }; categorical?: { columns?: Record<string, { n_unique?: number }> } } | null
  const rows = Number(p?.overview?.rows ?? 0)
  const out = new Set<string>()
  if (!(rows >= 20)) return out
  for (const [c, s] of Object.entries(p?.categorical?.columns ?? {})) {
    if (typeof s?.n_unique === 'number' && s.n_unique >= NEAR_UNIQUE * rows) out.add(c)
  }
  return out
}

/** Which picture a suggestion card shows (SuggestionGrid maps it to an icon). */
export type SuggestionIcon = 'total' | 'top' | 'trend' | 'average' | 'highest' | 'count' | 'rows' | 'summary' | 'columns' | 'tables'

/**
 * Step 10: a starter question as a card -- the question, a picture of the
 * kind of answer, and the dataset's own columns it uses (raw names, shown in
 * mono so they can be recognised in the data). Built only from the dataset's
 * real columns and types; nothing here is a canned example.
 */
export interface SuggestionCard { text: string; icon: SuggestionIcon; columns: string[] }

/** 4-6 cards this dataset can answer; generic ones when the columns say little.
 *  With the stored classes, a level, a score, a duration or a share is averaged
 *  and never totalled, and a code is never a measure (persona test 2026-10-12:
 *  "Total car age years by make", "Total review score by days late"). */
export function datasetSuggestionCards(
  columns: Pick<DatasetColumn, 'name' | 'dtype'>[] | undefined, t: Translate, classes?: ColumnClasses,
  perRow?: Set<string>,
): SuggestionCard[] {
  const kind = (c: string) => numberKind(c, classes)
  const isCode = (c: string) => kind(c) === 'code' || kind(c) === 'coordinate' || classes?.[c]?.role === 'identifier'
  const sorted = classify(columns ?? [])
  const numeric = sorted.numeric.filter(c => !isCode(c))
  // An amount first: what a "total" is about.
  numeric.sort((a, b) => Number(!ADDS_UP.has(kind(a) ?? 'amount')) - Number(!ADDS_UP.has(kind(b) ?? 'amount')))
  const { dates } = sorted
  const labels = sorted.labels.filter(c => !isCode(c) && !perRow?.has(c))
  const out: SuggestionCard[] = []
  const [n0, c0, c1, d0] = [numeric[0], labels[0], labels[1], dates[0]]
  const num = n0 && humanize(n0)
  const adds = !n0 || ADDS_UP.has(kind(n0) ?? 'amount')
  const cat = c0 && humanize(c0)
  const cat2 = c1 && humanize(c1)
  if (num && cat && adds) out.push({ text: t('ask.sug.totalBy', { num, cat }), icon: 'total', columns: [c0, n0] })
  if (num && cat && adds) out.push({ text: t('ask.sug.topBy', { num, cat }), icon: 'top', columns: [c0, n0] })
  if (num && d0) out.push({ text: t('ask.sug.trend', { num }), icon: 'trend', columns: [d0, n0] })
  const avgCol = adds ? c1 : c0
  const avgCat = adds ? cat2 : cat
  if (num && avgCat) out.push({ text: t('ask.sug.avgPer', { num, cat: avgCat }), icon: 'average', columns: [avgCol, n0] })
  if (num && cat) out.push({ text: t(adds ? 'ask.sug.highest' : 'ask.sug.highestAvg', { num, cat }), icon: 'highest', columns: [c0, n0] })
  if (cat) out.push({ text: t('ask.sug.countBy', { cat }), icon: 'count', columns: [c0] })
  out.push({ text: t('ask.sug.rows'), icon: 'rows', columns: [] })
  if (out.length < 4) out.push({ text: t('ask.sug.summary'), icon: 'summary', columns: [] },
    { text: t('ask.sug.columns'), icon: 'columns', columns: [] })
  const seen = new Set<string>()
  return out.filter(c => !seen.has(c.text) && !!seen.add(c.text)).slice(0, 6)
}

/** 4-6 questions this dataset can answer; generic ones when the columns say little. */
export function datasetSuggestions(
  columns: Pick<DatasetColumn, 'name' | 'dtype'>[] | undefined, t: Translate, classes?: ColumnClasses,
  perRow?: Set<string>,
): string[] {
  return datasetSuggestionCards(columns, t, classes, perRow).map(c => c.text)
}

/** A live connection has tables, not columns, until a question names one. */
export function connectionSuggestionCards(t: Translate): SuggestionCard[] {
  return [
    { text: t('ask.sug.tables'), icon: 'tables', columns: [] },
    { text: t('ask.sug.biggest'), icon: 'top', columns: [] },
    { text: t('ask.sug.recentRows'), icon: 'rows', columns: [] },
    { text: t('ask.sug.summary'), icon: 'summary', columns: [] },
  ]
}

/** A live connection has tables, not columns, until a question names one. */
export function connectionSuggestions(t: Translate): string[] {
  return connectionSuggestionCards(t).map(c => c.text)
}
