import { describe, it, expect } from 'vitest'
import { classify, datasetSuggestions, connectionSuggestions, humanize } from './suggestions'
import { aliasAggregations, answerToWidget } from '../../components/chat/answerWidget'
import { autoChart } from '../../components/chat/ResultView'
import { en } from '../../i18n/en'

const t = (key: string, vars?: Record<string, string | number>) =>
  ((en as Record<string, string>)[key] ?? key).replace(/\{(\w+)\}/g, (_, k) => String(vars?.[k] ?? ''))

const COLS = [
  { name: 'order_id', dtype: 'int64' }, { name: 'order_date', dtype: 'datetime64[ns]' },
  { name: 'region', dtype: 'object' }, { name: 'product_category', dtype: 'object' },
  { name: 'revenue', dtype: 'float64' },
]

describe('suggestions', () => {
  it('reads the columns the way a person would', () => {
    expect(humanize('product_category')).toBe('product category')
    expect(classify(COLS)).toEqual({
      numeric: ['revenue'], dates: ['order_date'], labels: ['region', 'product_category'] })
  })

  it('builds 4-6 specific questions from the dataset columns', () => {
    const s = datasetSuggestions(COLS, t as never)
    expect(s.length).toBeGreaterThanOrEqual(4)
    expect(s.length).toBeLessThanOrEqual(6)
    expect(s).toContain('Total revenue by region')
    expect(s).toContain('How has revenue changed over time?')
    expect(s.some(q => /id\b/.test(q))).toBe(false)   // ids are not measures
  })

  it('falls back to generic questions when the columns say little', () => {
    const s = datasetSuggestions([], t as never)
    expect(s.length).toBeGreaterThanOrEqual(3)
    expect(s).toContain('Summarize this data')
  })

  it('offers table-level questions for a live connection', () => {
    expect(connectionSuggestions(t as never)).toContain('What tables are in this connection?')
  })
})

describe('answerToWidget -- only offered when it maps onto the dataset', () => {
  const ds = ['region', 'revenue', 'order_date']
  const grouped = { step: 's1', columns: ['region', 'total'], rows: [['North', 10], ['South', 4]], total: 2, truncated: false }

  it('reads aggregate aliases out of the SQL', () => {
    expect(aliasAggregations('SELECT region, SUM(revenue) AS total, COUNT(*) n, count(distinct "region") AS k FROM t'))
      .toEqual({ total: { agg: 'sum', column: 'revenue' }, n: { agg: 'count', column: null },
                 k: { agg: 'countd', column: 'region' } })
  })

  it('maps SUM(col) grouped by a dataset column to a bar widget', () => {
    expect(answerToWidget(grouped as never, ['SELECT region, SUM(revenue) AS total FROM t GROUP BY 1'], ds))
      .toEqual({ widget_type: 'bar', config: { dimension: 'region', measure: 'revenue', aggregation: 'sum' } })
  })

  it('a dated dimension becomes a monthly line', () => {
    const r = { ...grouped, columns: ['order_date', 'total'], rows: [['2026-01-01', 1], ['2026-02-01', 2]] }
    expect(answerToWidget(r as never, ['SELECT order_date, AVG(revenue) total FROM t'], ds))
      .toMatchObject({ widget_type: 'line', config: { dimension_granularity: 'month', aggregation: 'avg' } })
  })

  it('one number becomes a KPI', () => {
    const r = { step: 's1', columns: ['total'], rows: [[14]], total: 1, truncated: false }
    expect(answerToWidget(r as never, ['SELECT SUM(revenue) AS total FROM t'], ds))
      .toEqual({ widget_type: 'kpi', config: { measure: 'revenue', aggregation: 'sum' } })
  })

  it('refuses what the report engine could not rebuild', () => {
    const expr = ['SELECT region, SUM(revenue) / COUNT(*) AS ratio FROM t GROUP BY 1']
    const r = { ...grouped, columns: ['region', 'ratio'] }
    expect(answerToWidget(r as never, expr, ds)).toBeNull()
    const joined = { ...grouped, columns: ['customer_name', 'total'] }
    expect(answerToWidget(joined as never, ['SELECT c.customer_name, SUM(o.revenue) AS total FROM o JOIN c'], ds)).toBeNull()
    expect(answerToWidget(grouped as never, [], [])).toBeNull()
  })
})

describe('autoChart', () => {
  const base = { step: 's', truncated: false }
  it('KPI for a single number, bar for a small grouped result', () => {
    expect(autoChart({ ...base, columns: ['n'], rows: [[3]], total: 1 } as never)).toBe('kpi')
    expect(autoChart({ ...base, columns: ['c', 'n'], rows: [['a', 1], ['b', 2]], total: 2 } as never)).toBe('bar')
    expect(autoChart({ ...base, columns: ['m', 'n'], rows: [['2026-01', 1], ['2026-02', 2]], total: 2 } as never)).toBe('line')
  })
  it('never charts a partial result as if it were whole', () => {
    expect(autoChart({ ...base, truncated: true, columns: ['c', 'n'], rows: [['a', 1], ['b', 2]], total: 250 } as never)).toBeNull()
  })
  it('leaves wide or text-only results to the grid', () => {
    expect(autoChart({ ...base, columns: ['a', 'b'], rows: [['x', 'y'], ['z', 'w']], total: 2 } as never)).toBeNull()
  })
})
