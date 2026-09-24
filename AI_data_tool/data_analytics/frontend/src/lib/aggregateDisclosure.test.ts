import { describe, it, expect } from 'vitest'
import { aggregationWarning, PRE_AGGREGATED_HINT } from './aggregateDisclosure'
import type { Dataset } from '../services/api'

const agg = { id: 9, name: 'by region', aggregate_of_dataset_id: 5,
  aggregate_spec: { grain: ['tenant', 'region'], measures: [{ column: 'amount', agg: 'sum', name: 'amount_sum' }] } } as unknown as Dataset
const plain = { id: 5, name: 'orders' } as unknown as Dataset

describe('aggregationWarning', () => {
  it('is silent on an ordinary dataset', () => {
    expect(aggregationWarning(plain, 'amount', 'avg')).toBeNull()
    expect(aggregationWarning(undefined, 'amount', 'count')).toBeNull()
  })
  it('warns that avg over a derived measure averages sums', () => {
    expect(aggregationWarning(agg, 'amount_sum', 'avg')).toMatch(/average of sums.*sum\(amount_sum\) \/ sum\(row_count\)/)
  })
  it('warns that count counts groups, with or without a measure', () => {
    expect(aggregationWarning(agg, '', 'count')).toMatch(/counts groups, not rows.*sum\(row_count\)/)
    // 'countd' is the real select value (AGGREGATIONS in types/report.ts);
    // 'count_distinct' is a backend synonym (e.g. suggest_dataset_dashboard
    // normalises count_distinct -> countd) -- both must warn.
    expect(aggregationWarning(agg, 'amount_sum', 'countd')).toMatch(/counts groups/)
    expect(aggregationWarning(agg, 'amount_sum', 'count_distinct')).toMatch(/counts groups/)
    // frequency and pct never read the measure: the shaper takes groupby.size()
    // (widget_data.py) and pct divides that by the total. Over a grain column,
    // the common case, they count groups exactly as count does.
    expect(aggregationWarning(agg, 'region', 'frequency')).toMatch(/counts groups/)
    expect(aggregationWarning(agg, '', 'pct')).toMatch(/counts groups/)
    // backend synonym for countd
    expect(aggregationWarning(agg, '', 'distinct')).toMatch(/counts groups/)
  })
  it('is silent for sum, min and max, which re-aggregate correctly', () => {
    expect(aggregationWarning(agg, 'amount_sum', 'sum')).toBeNull()
    expect(aggregationWarning(agg, 'row_count', 'sum')).toBeNull()
  })
  it('warns that avg over the reserved row_count measure is rows per group, with a remedy that is not a constant', () => {
    const msg = aggregationWarning(agg, 'row_count', 'avg')
    expect(msg).toMatch(/rows per group/)
    expect(msg).not.toMatch(/sum\(row_count\) \/ sum\(row_count\)/)
  })
  it('treats the backend synonyms mean and average like avg', () => {
    expect(aggregationWarning(agg, 'amount_sum', 'mean')).toMatch(/average of sums/)
    expect(aggregationWarning(agg, 'amount_sum', 'average')).toMatch(/average of sums/)
  })
  it('warns for any other non-additive aggregation over a derived measure, naming it by its select label', () => {
    expect(aggregationWarning(agg, 'amount_sum', 'median')).toBe(
      'On a pre-aggregated dataset Median is computed over group totals, not rows, and does not re-aggregate correctly.')
    expect(aggregationWarning(agg, 'amount_sum', 'p90')).toBe(
      'On a pre-aggregated dataset P90 is computed over group totals, not rows, and does not re-aggregate correctly.')
    expect(aggregationWarning(agg, 'row_count', 'stderr')).toMatch(/Standard Error is computed over group totals/)
  })
  it('stays silent for a non-additive aggregation over a GRAIN column, which is not derived', () => {
    expect(aggregationWarning(agg, 'tenant', 'p90')).toBeNull()
    expect(aggregationWarning(agg, 'region', 'median')).toBeNull()
  })
  it('has one sentence of hint copy', () => {
    expect(PRE_AGGREGATED_HINT).toMatch(/row_count/)
  })
})
