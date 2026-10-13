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

/** Which picture a suggestion card shows (SuggestionGrid maps it to an icon). */
export type SuggestionIcon = 'total' | 'top' | 'trend' | 'average' | 'highest' | 'count' | 'rows' | 'summary' | 'columns' | 'tables'

/**
 * Step 10: a starter question as a card -- the question, a picture of the
 * kind of answer, and the dataset's own columns it uses (raw names, shown in
 * mono so they can be recognised in the data). Built only from the dataset's
 * real columns and types; nothing here is a canned example.
 */
export interface SuggestionCard { text: string; icon: SuggestionIcon; columns: string[] }

/** 4-6 cards this dataset can answer; generic ones when the columns say little. */
export function datasetSuggestionCards(
  columns: Pick<DatasetColumn, 'name' | 'dtype'>[] | undefined, t: Translate,
): SuggestionCard[] {
  const { numeric, dates, labels } = classify(columns ?? [])
  const out: SuggestionCard[] = []
  const [n0, c0, c1, d0] = [numeric[0], labels[0], labels[1], dates[0]]
  const num = n0 && humanize(n0)
  const cat = c0 && humanize(c0)
  const cat2 = c1 && humanize(c1)
  if (num && cat) out.push({ text: t('ask.sug.totalBy', { num, cat }), icon: 'total', columns: [c0, n0] })
  if (num && cat) out.push({ text: t('ask.sug.topBy', { num, cat }), icon: 'top', columns: [c0, n0] })
  if (num && d0) out.push({ text: t('ask.sug.trend', { num }), icon: 'trend', columns: [d0, n0] })
  if (num && cat2) out.push({ text: t('ask.sug.avgPer', { num, cat: cat2 }), icon: 'average', columns: [c1, n0] })
  if (num && cat) out.push({ text: t('ask.sug.highest', { num, cat }), icon: 'highest', columns: [c0, n0] })
  if (cat) out.push({ text: t('ask.sug.countBy', { cat }), icon: 'count', columns: [c0] })
  out.push({ text: t('ask.sug.rows'), icon: 'rows', columns: [] })
  if (out.length < 4) out.push({ text: t('ask.sug.summary'), icon: 'summary', columns: [] },
    { text: t('ask.sug.columns'), icon: 'columns', columns: [] })
  const seen = new Set<string>()
  return out.filter(c => !seen.has(c.text) && !!seen.add(c.text)).slice(0, 6)
}

/** 4-6 questions this dataset can answer; generic ones when the columns say little. */
export function datasetSuggestions(
  columns: Pick<DatasetColumn, 'name' | 'dtype'>[] | undefined, t: Translate,
): string[] {
  return datasetSuggestionCards(columns, t).map(c => c.text)
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
