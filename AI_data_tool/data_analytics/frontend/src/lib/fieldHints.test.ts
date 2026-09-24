import { describe, it, expect } from 'vitest'
import { countLabel, fieldHints } from './fieldHints'

/**
 * The statistics behind these hints were already computed by `analyze_numeric` —
 * a Pearson matrix and per-column IQR outlier counts — and simply never surfaced.
 * This derives the hints SAS shows inline in its Data pane from that existing output.
 */

const analysis = (over: Record<string, unknown> = {}) => ({
  overview: { rows: 500, cols: 3, missing_pct: 0, type_counts: {} },
  numeric: {
    columns: {
      revenue: { iqr_outliers: 0, max: 10 },
      profit: { iqr_outliers: 4, max: 5 },
      cost: { iqr_outliers: 0, max: 8 },
    },
    correlation: {
      revenue: { revenue: 1, profit: 0.91, cost: 0.12 },
      profit: { revenue: 0.91, profit: 1, cost: -0.7 },
      cost: { revenue: 0.12, profit: -0.7, cost: 1 },
    },
  },
  ...over,
})

describe('fieldHints', () => {
  it('returns nothing when there is no analysis yet', () => {
    expect(fieldHints(null)).toEqual({})
    expect(fieldHints({})).toEqual({})
  })

  it('reports the outlier count for columns that have them', () => {
    const hints = fieldHints(analysis())

    expect(hints.profit.outliers).toBe(4)
    expect(hints.revenue.outliers).toBeUndefined()
  })

  it('pairs measures whose correlation clears the threshold', () => {
    const hints = fieldHints(analysis())

    expect(hints.revenue.related).toEqual([{ column: 'profit', r: 0.91 }])
  })

  it('counts a strong negative correlation as related, since sign is not strength', () => {
    const hints = fieldHints(analysis())

    expect(hints.cost.related).toEqual([{ column: 'profit', r: -0.7 }])
  })

  it('never reports a column as related to itself', () => {
    const hints = fieldHints(analysis())

    for (const [col, hint] of Object.entries(hints)) {
      expect((hint.related ?? []).map(r => r.column)).not.toContain(col)
    }
  })

  it('ignores weak correlations', () => {
    const hints = fieldHints(analysis())

    expect((hints.revenue.related ?? []).map(r => r.column)).not.toContain('cost')
  })

  it('orders related measures strongest first', () => {
    const hints = fieldHints(analysis({
      numeric: {
        columns: { a: {}, b: {}, c: {} },
        correlation: {
          a: { a: 1, b: 0.65, c: -0.95 },
          b: { a: 0.65, b: 1, c: 0.1 },
          c: { a: -0.95, b: 0.1, c: 1 },
        },
      },
    }))

    expect((hints.a.related ?? []).map(r => r.column)).toEqual(['c', 'b'])
  })

  it('raises the threshold on a small sample, where correlations arise by chance', () => {
    const small = analysis({ overview: { rows: 20, cols: 3, missing_pct: 0, type_counts: {} } })

    // 0.91 still clears the raised bar; -0.7 no longer does.
    expect((fieldHints(small).revenue.related ?? []).map(r => r.column)).toEqual(['profit'])
    // cost has neither outliers nor a surviving correlation, so it drops out entirely.
    expect(fieldHints(small).cost?.related).toBeUndefined()
  })

  it('skips correlation entirely when there are too many measures to be useful', () => {
    const many: Record<string, Record<string, number>> = {}
    const names = Array.from({ length: 200 }, (_, i) => `m${i}`)
    for (const a of names) {
      many[a] = {}
      for (const b of names) many[a][b] = a === b ? 1 : 0.99
    }
    const hints = fieldHints(analysis({ numeric: { columns: {}, correlation: many } }))

    expect(Object.values(hints).every(h => h.related === undefined)).toBe(true)
  })

  it('handles a missing correlation matrix, which happens with one numeric column', () => {
    const hints = fieldHints(analysis({
      numeric: { columns: { revenue: { iqr_outliers: 2 } } },
    }))

    expect(hints.revenue.outliers).toBe(2)
    expect(hints.revenue.related).toBeUndefined()
  })

  it('tolerates nulls in the matrix, which a constant column produces', () => {
    const hints = fieldHints(analysis({
      numeric: {
        columns: { a: {}, b: {} },
        correlation: { a: { a: 1, b: null }, b: { a: null, b: 1 } },
      },
    }))

    expect(hints.a?.related).toBeUndefined()
  })
})

describe('distinct values per field', () => {
  /**
   * SAS's data pane reads "Country - 47", "Order ID - 748K": every category item
   * carries how many distinct values it holds. That number is the single most
   * useful thing to know before charting a field — 47 countries is a bar chart,
   * 748K order IDs is a mistake — and `analyze_categorical` has computed it as
   * `n_unique` all along without ever showing it.
   */
  it('reads the count the profile already computed', () => {
    const hints = fieldHints({
      categorical: { columns: { country: { n_unique: 47 } } },
    })
    expect(hints.country.distinct).toBe(47)
  })

  it('leaves a field with no profile alone', () => {
    const hints = fieldHints({ categorical: { columns: {} } })
    expect(hints.country).toBeUndefined()
  })

  it('keeps the outlier and correlation hints beside it', () => {
    // The three share one entry per field; adding one must not drop the others.
    const hints = fieldHints({
      categorical: { columns: { region: { n_unique: 4 } } },
      numeric: { columns: { revenue: { iqr_outliers: 209 } } },
    })
    expect(hints.region.distinct).toBe(4)
    expect(hints.revenue.outliers).toBe(209)
  })

  it('survives a profile that has no categorical section at all', () => {
    expect(() => fieldHints({ numeric: { columns: {} } })).not.toThrow()
  })
})

describe('countLabel', () => {
  it('abbreviates the way SAS does', () => {
    // "Order ID - 748K" — the exact figure is noise at that size, and the field
    // list is a narrow column.
    expect(countLabel(47)).toBe('47')
    expect(countLabel(748_000)).toBe('748K')
    expect(countLabel(3_200)).toBe('3.2K')
    expect(countLabel(1_600_000)).toBe('1.6M')
  })

  it('leaves small counts exact', () => {
    expect(countLabel(3)).toBe('3')
    expect(countLabel(999)).toBe('999')
  })
})
