import { describe, it, expect } from 'vitest'
import { groupingExpression, binningExpression, defaultBinEdges } from './customCategories'

/**
 * Custom categories compile to expressions for the existing calculated-column
 * engine rather than introducing a parallel mechanism. That means the result is a
 * normal calculated column everywhere — query path, display formats, Fields pane —
 * with no new backend code. These tests pin the generated syntax, since a subtle
 * mistake there produces a column that silently evaluates to the wrong bucket.
 */

describe('groupingExpression', () => {
  it('maps each value in a group to that group name', () => {
    const expr = groupingExpression('region', [
      { name: 'Americas', values: ['US', 'CA'] },
      { name: 'Europe', values: ['UK'] },
    ], 'Other')

    expect(expr).toBe(
      `SWITCH(region, "US", "Americas", "CA", "Americas", "UK", "Europe", "Other")`,
    )
  })

  it('quotes a column name containing spaces with backticks', () => {
    const expr = groupingExpression('Order Region', [{ name: 'A', values: ['x'] }], 'Other')

    expect(expr).toContain('SWITCH(`Order Region`,')
  })

  it('escapes double quotes inside values so the expression stays parseable', () => {
    const expr = groupingExpression('size', [{ name: 'Big', values: ['12" pipe'] }], 'Other')

    expect(expr).toContain('\\"')
    expect(expr).not.toMatch(/"12" pipe"/)
  })

  it('omits empty groups rather than emitting a dangling condition', () => {
    const expr = groupingExpression('region', [
      { name: 'A', values: ['x'] },
      { name: 'Empty', values: [] },
    ], 'Other')

    expect(expr).toBe(`SWITCH(region, "x", "A", "Other")`)
  })

  it('returns an empty string when there is nothing to map', () => {
    expect(groupingExpression('region', [], 'Other')).toBe('')
    expect(groupingExpression('region', [{ name: 'A', values: [] }], 'Other')).toBe('')
  })
})

describe('binningExpression', () => {
  it('builds ascending nested IFs so the first matching edge wins', () => {
    const expr = binningExpression('sales', [0, 10, 20])

    // Below 10 -> "0-10"; below 20 -> "10-20"; otherwise the final open bucket.
    expect(expr).toBe(
      `IF(sales < 10, "0-10", IF(sales < 20, "10-20", "20+"))`,
    )
  })

  it('handles a single interval', () => {
    expect(binningExpression('sales', [0, 50])).toBe(`IF(sales < 50, "0-50", "50+")`)
  })

  it('quotes a spaced column name', () => {
    expect(binningExpression('Net Sales', [0, 5])).toContain('IF(`Net Sales` < 5')
  })

  it('returns an empty string for fewer than two edges', () => {
    expect(binningExpression('sales', [])).toBe('')
    expect(binningExpression('sales', [0])).toBe('')
  })

  it('drops duplicate and unsorted edges so buckets cannot overlap', () => {
    expect(binningExpression('sales', [20, 0, 10, 10])).toBe(
      `IF(sales < 10, "0-10", IF(sales < 20, "10-20", "20+"))`,
    )
  })
})

describe('defaultBinEdges', () => {
  it('produces n evenly spaced edges across the range', () => {
    expect(defaultBinEdges(0, 100, 4)).toEqual([0, 25, 50, 75, 100])
  })

  it('rounds to readable numbers rather than long decimals', () => {
    const edges = defaultBinEdges(0, 10, 3)
    expect(edges.every(e => Number.isFinite(e))).toBe(true)
    expect(edges[0]).toBe(0)
    expect(edges[edges.length - 1]).toBe(10)
  })

  it('returns an empty list when the range has no width', () => {
    expect(defaultBinEdges(5, 5, 4)).toEqual([])
  })
})

describe('bin labels when the data goes below zero', () => {
  /**
   * `-12012--4991` — four characters, three of which are a minus sign, and no
   * way for a reader to see where one number ends and the next begins. Seen on
   * a real binned column: the demo revenue data has refunds, so the lowest bin
   * spans two negative edges.
   *
   * The hyphen stays for the ordinary case, because "0-10" is exactly right and
   * every existing label is written that way. The separator changes only when a
   * bound is negative, which is the only time it is ambiguous.
   */
  it('keeps the hyphen when both bounds are positive', () => {
    expect(binningExpression('sales', [0, 10, 20]))
      .toBe(`IF(sales < 10, "0-10", IF(sales < 20, "10-20", "20+"))`)
  })

  it('reads a negative range as a range', () => {
    expect(binningExpression('revenue', [-12012, -4991, 2029]))
      .toBe(`IF(revenue < -4991, "-12012 to -4991", `
          + `IF(revenue < 2029, "-4991 to 2029", "2029+"))`)
  })

  it('switches when only the lower bound is negative', () => {
    expect(binningExpression('t', [-5, 5])).toBe(`IF(t < 5, "-5 to 5", "5+")`)
  })

  it('leaves the open top bucket alone', () => {
    // "2029+" is unambiguous either way.
    expect(binningExpression('t', [-5, 5])).toContain('"5+"')
  })
})
