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

/** 4-6 questions this dataset can answer; generic ones when the columns say little.
 *  With the stored classes, a level, a score, a duration or a share is averaged
 *  and never totalled, and a code is never a measure (persona test 2026-10-12:
 *  "Total car age years by make", "Total review score by days late"). */
export function datasetSuggestions(
  columns: Pick<DatasetColumn, 'name' | 'dtype'>[] | undefined, t: Translate, classes?: ColumnClasses,
): string[] {
  const kind = (c: string) => classes?.[c]?.number
  const isCode = (c: string) => kind(c) === 'code' || classes?.[c]?.role === 'identifier'
  const sorted = classify(columns ?? [])
  const numeric = sorted.numeric.filter(c => !isCode(c))
  // An amount first: what a "total" is about.
  numeric.sort((a, b) => Number(!ADDS_UP.has(kind(a) ?? 'amount')) - Number(!ADDS_UP.has(kind(b) ?? 'amount')))
  const { dates } = sorted
  const labels = sorted.labels.filter(c => !isCode(c))
  const out: string[] = []
  const num = numeric[0] && humanize(numeric[0])
  const adds = !numeric[0] || ADDS_UP.has(kind(numeric[0]) ?? 'amount')
  const cat = labels[0] && humanize(labels[0])
  const cat2 = labels[1] && humanize(labels[1])
  if (num && cat && adds) out.push(t('ask.sug.totalBy', { num, cat }))
  if (num && cat && adds) out.push(t('ask.sug.topBy', { num, cat }))
  if (num && dates[0]) out.push(t('ask.sug.trend', { num }))
  if (num && (adds ? cat2 : cat)) out.push(t('ask.sug.avgPer', { num, cat: (adds ? cat2 : cat) as string }))
  if (num && cat) out.push(t(adds ? 'ask.sug.highest' : 'ask.sug.highestAvg', { num, cat }))
  if (cat) out.push(t('ask.sug.countBy', { cat }))
  out.push(t('ask.sug.rows'))
  if (out.length < 4) out.push(t('ask.sug.summary'), t('ask.sug.columns'))
  return [...new Set(out)].slice(0, 6)
}

/** A live connection has tables, not columns, until a question names one. */
export function connectionSuggestions(t: Translate): string[] {
  return [t('ask.sug.tables'), t('ask.sug.biggest'), t('ask.sug.recentRows'), t('ask.sug.summary')]
}
