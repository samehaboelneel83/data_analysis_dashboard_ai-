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
    for (const c of ['A_NUMBER', 'phone_number', 'invoice_no', 'serial_no', 'رقم_الطلب']) {
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
    for (const c of ['active_users', 'unique_customers', 'unique_products_sold', 'distinct_users', 'dau'])
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

describe('defaultSummary: a neutral vocabulary', () => {
  // A general-purpose platform: no noun of one field of work decides what a
  // column is. A reading such as a mileage is averaged because the dataset's
  // stored classification says it is a level, not because of its name.
  it('reads a reading from its classification, never from an industry noun', () => {
    for (const c of ['mileage_km', 'odometer', 'salary', 'gpa', 'premium']) expect(defaultSummary(c)).toBe('sum')
    expect(defaultSummary('mileage_km', { mileage_km: { number: 'level' } })).toBe('avg')
  })
  it('knows how a number is measured, in English and Arabic', () => {
    for (const c of ['unit_price', 'late_rate', 'avg_wait', 'سعر الوحدة', 'نسبة_التأخير']) expect(defaultSummary(c)).toBe('avg')
  })
})

// Mirrors TestOneReader in backend tests/test_column_classes.py: the two
// halves must read a column's stored classification the same way.
describe('the stored classification outranks the name', () => {
  it('reads a column with no hint in its name from its classification', async () => {
    const g = await import('./semanticGuard')
    const meta = { val2: { number: 'score' }, col_a: { number: 'amount' }, x9: { number: 'code' } }
    expect(g.defaultSummary('val2', meta)).toBe('avg')
    expect(g.isIntensive('val2', meta)).toBe(true)
    expect(g.defaultSummary('col_a', meta)).toBe('sum')
    expect(g.nonAdditiveKind('x9', meta)).toBe('identifier')
    expect(g.defaultSummary('x9', meta)).toBe('countd')
    expect(g.semanticAggregationWarning('x9', 'sum', meta)).not.toBeNull()
  })

  it('lets a confirmed classification overrule a misleading name', async () => {
    const g = await import('./semanticGuard')
    const meta = { invoice_no: { number: 'amount', class_source: 'confirmed' } }
    expect(g.nonAdditiveKind('invoice_no')).toBe('identifier')
    expect(g.nonAdditiveKind('invoice_no', meta)).toBeNull()
    expect(g.semanticAggregationWarning('invoice_no', 'sum', meta)).toBeNull()
  })

  it('still falls back to the name for a column nobody classified', async () => {
    const g = await import('./semanticGuard')
    expect(g.defaultSummary('unit_price', {})).toBe('avg')
    expect(g.isIdentifier('customer_id', {})).toBe(true)
  })

  it('knows an ordinal order and an outcome', async () => {
    const g = await import('./semanticGuard')
    const meta = { priority: { level: 'ordinal', order: ['Low', 'High'] }, is_late: { outcome: true } }
    expect(g.valueOrder('priority', meta)).toEqual(['Low', 'High'])
    expect(g.valueOrder('is_late', meta)).toBeNull()
    expect(g.isOutcome('is_late', meta)).toBe(true)
  })
})
