import { describe, it, expect } from 'vitest'
import { nonAdditiveKind, semanticAggregationWarning, SAFE_AGGREGATION } from './semanticGuard'

describe('nonAdditiveKind', () => {
  it('recognises coordinates, identifiers and years by name', () => {
    expect(nonAdditiveKind('latitude')).toBe('coordinate')
    expect(nonAdditiveKind('store_lng')).toBe('coordinate')
    expect(nonAdditiveKind('customer_id')).toBe('identifier')
    expect(nonAdditiveKind('zip_code')).toBe('identifier')
    expect(nonAdditiveKind('year')).toBe('year')
    expect(nonAdditiveKind('fiscal_year')).toBe('year')
  })
  it('leaves quantities alone', () => {
    for (const c of ['revenue', 'units', 'margin_pct', 'plateau', 'yearly_revenue', 'longevity', 'valid']) {
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
