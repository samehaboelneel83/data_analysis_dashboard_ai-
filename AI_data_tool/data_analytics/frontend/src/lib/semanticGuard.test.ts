import { describe, it, expect } from 'vitest'
import { nonAdditiveKind, semanticAggregationWarning, SAFE_AGGREGATION, defaultSummary } from './semanticGuard'

describe('nonAdditiveKind', () => {
  it('recognises coordinates, identifiers and years by name', () => {
    expect(nonAdditiveKind('latitude')).toBe('coordinate')
    expect(nonAdditiveKind('store_lng')).toBe('coordinate')
    expect(nonAdditiveKind('customer_id')).toBe('identifier')
    expect(nonAdditiveKind('zip_code')).toBe('identifier')
    expect(nonAdditiveKind('year')).toBe('year')
    expect(nonAdditiveKind('fiscal_year')).toBe('year')
    for (const c of ['A_NUMBER', 'phone_number', 'invoice_no', 'IMEI', 'imsi', 'MSISDN', 'LAC', 'cell_lac']) {
      expect(nonAdditiveKind(c)).toBe('identifier')
    }
  })
  it('recognises the identifier suffixes Key influencers relies on (redesign KI-2)', () => {
    expect(nonAdditiveKind('cohort_ref')).toBe('identifier')
    expect(nonAdditiveKind('invoice_no')).toBe('identifier')
    expect(nonAdditiveKind('order_key')).toBe('identifier')
    expect(nonAdditiveKind('region_code')).toBe('identifier')
    expect(nonAdditiveKind('preference')).toBeNull()
  })
  it('leaves quantities alone', () => {
    for (const c of ['revenue', 'units', 'margin_pct', 'plateau', 'yearly_revenue', 'longevity', 'valid',
                     'number_of_calls', 'phone_calls', 'lace', 'imei_count', 'casino']) {
      expect(nonAdditiveKind(c)).toBeNull()
    }
  })
})

describe('semanticAggregationWarning', () => {
  it('warns on sum of a latitude, but not its average', () => {
    expect(semanticAggregationWarning('latitude', 'sum')).toMatch(/not a place/)
    expect(semanticAggregationWarning('latitude', 'avg')).toBeNull()
  })
  it('warns on any arithmetic over an identifier', () => {
    expect(semanticAggregationWarning('order_id', 'sum')).toMatch(/Count distinct/)
    expect(semanticAggregationWarning('order_id', 'avg')).toMatch(/identifiers/)
    expect(semanticAggregationWarning('order_id', 'countd')).toBeNull()
  })
  it('warns on summing years', () => {
    expect(semanticAggregationWarning('year', 'sum')).toMatch(/not a year/)
    expect(semanticAggregationWarning('year', 'max')).toBeNull()
  })
  it('never warns about a real quantity', () => {
    expect(semanticAggregationWarning('revenue', 'sum')).toBeNull()
  })
  it('offers a safe aggregation for every kind', () => {
    expect(SAFE_AGGREGATION.identifier.value).toBe('countd')
  })
})

describe('defaultSummary: per-row distinct counts', () => {
  // Mirrors tests/test_suggest_gap_review.py: a daily count of unique
  // customers summed over days counts each customer once per day.
  it('averages them and keeps totals summing', () => {
    for (const c of ['active_sellers', 'unique_customers', 'unique_products_sold', 'distinct_users', 'dau'])
      expect(defaultSummary(c)).toBe('avg')
    for (const c of ['total_orders', 'total_revenue', 'active_minutes'])
      expect(defaultSummary(c)).toBe('sum')
  })
})

describe('an inferred role does not override the veto', () => {
  it('sums nothing just because automation guessed "measure"', () => {
    expect(defaultSummary('hire_year', { hire_year: { role: 'measure', role_source: 'inferred' } })).toBe('max')
    expect(defaultSummary('hire_year', { hire_year: { role: 'measure' } })).toBe('sum')
  })
})
