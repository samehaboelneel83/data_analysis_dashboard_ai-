import type { AgentResult } from '../../services/api'
import { chartColumns, groupedBars } from './ResultView'

/**
 * Can this answer become a dashboard widget -- honestly?
 *
 * A widget is not a picture of the answer: it re-queries the dataset through
 * the report engine (dimension + measure + aggregation). So an answer only
 * qualifies when its chart maps back onto the dataset's own columns:
 *   - the label column IS a dataset column, and
 *   - the value column is either a dataset column, or an alias the SQL
 *     defines as SUM/AVG/MIN/MAX/COUNT of one (or COUNT(*)).
 * Anything else (joins, expressions, window functions) returns null, and the
 * "Add to dashboard" control is not offered rather than offered and wrong.
 */
export interface WidgetDraft {
  widget_type: 'bar' | 'line' | 'kpi'
  config: Record<string, unknown>
}

const AGG: Record<string, string> = { sum: 'sum', avg: 'avg', min: 'min', max: 'max', count: 'count' }
const unquote = (s: string) => s.replace(/^["`[]|["`\]]$/g, '')

export function aliasAggregations(sql: string): Record<string, { agg: string; column: string | null }> {
  const out: Record<string, { agg: string; column: string | null }> = {}
  // The call must be the WHOLE select item (right after SELECT or a comma):
  // in `SUM(a)/COUNT(*) AS ratio` the alias names the ratio, not the count.
  const re = /(?<=(?:\bselect|,)\s*)\b(sum|avg|min|max|count)\s*\(\s*(distinct\s+)?([^()]+?)\s*\)\s+(?:as\s+)?("[^"]+"|`[^`]+`|\[[^\]]+\]|\w+)/gi
  for (const m of sql.matchAll(re)) {
    const agg = AGG[m[1].toLowerCase()]
    const inner = m[3].trim()
    const column = inner === '*' || inner === '1' ? null : unquote(inner.split('.').pop()!)
    out[unquote(m[4]).toLowerCase()] = { agg: m[2] && agg === 'count' ? 'countd' : agg, column }
  }
  return out
}

const looksLikeDate = (v: unknown) =>
  typeof v === 'string' && /^\d{4}-\d{2}(-\d{2})?/.test(v)

export function answerToWidget(
  result: AgentResult | undefined, sql: string[] | undefined, datasetColumns: string[],
  x?: string | null, y?: string | null,
): WidgetDraft | null {
  if (!result || result.total === 0 || datasetColumns.length === 0) return null
  const cols = new Set(datasetColumns.map(c => c.toLowerCase()))
  const real = (name: string) => datasetColumns.find(c => c.toLowerCase() === name.toLowerCase())
  const lastSql = (sql ?? []).at(-1) ?? ''
  const aliases = aliasAggregations(lastSql)

  // COUNT(*) counts rows; the widget engine wants a column to count, and any
  // non-null one gives the same number -- the dimension itself, or the first.
  const measureFor = (name: string | undefined, rowsOf?: string) => {
    if (!name) return null
    const a = aliases[name.toLowerCase()]
    if (a) {
      if (a.column == null) return { measure: rowsOf ?? datasetColumns[0], aggregation: 'count' }
      const col = real(a.column)
      return col ? { measure: col, aggregation: a.agg } : null
    }
    return cols.has(name.toLowerCase()) ? { measure: real(name), aggregation: 'sum' } : null
  }

  // One number: a KPI of its measure.
  if (result.columns.length === 1 && result.rows.length === 1) {
    const m = measureFor(result.columns[0])
    return m ? { widget_type: 'kpi', config: { ...m } } : null
  }
  // Two labels and a measure: the second label splits each bar (dimension2),
  // the same grouped chart the answer showed.
  const grouped = !(x && y) ? groupedBars(result) : null
  if (grouped) {
    const dim = real(grouped.x); const dim2 = real(grouped.series)
    const m = measureFor(grouped.y, dim)
    if (dim && dim2 && m) return { widget_type: 'bar', config: { dimension: dim, dimension2: dim2, ...m } }
  }
  const axes = chartColumns(result, x, y)
  if (!axes.x || !axes.y) return null
  const dim = real(axes.x)
  const m = measureFor(axes.y, dim)
  if (!dim || !m) return null
  const idx = result.columns.indexOf(axes.x)
  const dated = result.rows.slice(0, 5).every(r => looksLikeDate(r[idx]))
  return {
    widget_type: dated ? 'line' : 'bar',
    config: { dimension: dim, ...m, ...(dated ? { dimension_granularity: 'month' } : {}) },
  }
}
