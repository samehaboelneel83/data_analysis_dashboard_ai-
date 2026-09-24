/**
 * One-click calculations from the field list.
 *
 * The widget already had quick calcs — percent of total, difference, percent
 * change, rank — applied to the values a visual has aggregated. SAS also offers
 * them from the DATA ITEM, where the result is a new, reusable field rather
 * than a setting on one chart. That is the gap this closes, and the honest
 * mapping is a **measure**: `measure_eval` evaluates at the requesting widget's
 * grain, so `SUM(x) / TOTAL(SUM(x)) * 100` is a real percent-of-total that
 * changes when the visual's crossing changes — which a row-level calculated
 * column can never be.
 *
 * Every expression here must be valid in that language. The whole value of a
 * one-click calculation is that it cannot be typed wrong, so an offer that
 * saves and then fails to evaluate would be worse than no offer at all.
 */
import { describe, it, expect } from 'vitest'
import { quickCalcsFor, uniqueMeasureName } from './quickCalcs'

const numeric = { name: 'revenue', dtype: 'numeric', numeric: true }
const category = { name: 'region', dtype: 'categorical', numeric: false }

describe('what is offered', () => {
  it('offers a percent of total for a measure', () => {
    const pct = quickCalcsFor(numeric).find(c => c.key === 'percent_of_total')!
    expect(pct.expression).toBe('SUM(revenue) / TOTAL(SUM(revenue)) * 100')
  })

  it('offers the ordinary summaries for a measure', () => {
    const keys = quickCalcsFor(numeric).map(c => c.key)
    expect(keys).toEqual(expect.arrayContaining(
      ['percent_of_total', 'average', 'median', 'stdev', 'distinct']))
  })

  it('offers a category only what makes sense for one', () => {
    // AVG(region) is not a question; a distinct count and a share of rows are.
    const keys = quickCalcsFor(category).map(c => c.key)
    expect(keys).toEqual(expect.arrayContaining(['distinct', 'percent_of_rows']))
    expect(keys).not.toContain('average')
    expect(keys).not.toContain('stdev')
  })

  it('uses COUNT rather than SUM for a category share', () => {
    const share = quickCalcsFor(category).find(c => c.key === 'percent_of_rows')!
    expect(share.expression).toBe('COUNT(region) / TOTAL(COUNT(region)) * 100')
  })

  it('names each one after the field it came from', () => {
    for (const c of quickCalcsFor(numeric)) {
      expect(c.name.toLowerCase()).toContain('revenue')
    }
  })

  it('every offered expression uses only functions the measure language has', () => {
    // The property that matters: a one-click calculation that saves and then
    // fails to evaluate is worse than no offer at all.
    const allowed = /^(SUM|AVG|MEDIAN|COUNT|COUNTD|STDEV|VARIANCE|TOTAL|BYGROUP|CALC)$/
    for (const field of [numeric, category]) {
      for (const c of quickCalcsFor(field)) {
        const called = [...c.expression.matchAll(/([A-Z]+)\s*\(/g)].map(m => m[1])
        expect(called.length).toBeGreaterThan(0)
        for (const fn of called) expect(fn).toMatch(allowed)
      }
    }
  })

  it('offers nothing for a field the measure language cannot name', () => {
    /**
     * `measure_eval` binds each column to a Python identifier and `eval`s the
     * expression, so `AVG(net revenue)` is a syntax error and there is no
     * quoting form that would rescue it. Offering a one-click calculation that
     * saves and then cannot evaluate is worse than offering none: the whole
     * point of one click is that it cannot be typed wrong.
     */
    expect(quickCalcsFor({ name: 'net revenue', dtype: 'numeric', numeric: true }))
      .toEqual([])
    expect(quickCalcsFor({ name: 'gross-margin', dtype: 'numeric', numeric: true }))
      .toEqual([])
    expect(quickCalcsFor({ name: '2024', dtype: 'numeric', numeric: true }))
      .toEqual([])
  })

  it('still offers them for an ordinary name', () => {
    expect(quickCalcsFor({ name: 'net_revenue', dtype: 'numeric', numeric: true }).length)
      .toBeGreaterThan(0)
  })
})

describe('naming', () => {
  it('leaves a free name alone', () => {
    expect(uniqueMeasureName('% of total revenue', [])).toBe('% of total revenue')
  })

  it('never silently overwrites an existing measure', () => {
    // measuresApi.save is an upsert by name: colliding would replace someone
    // else's definition with this one and say nothing.
    expect(uniqueMeasureName('% of total revenue', ['% of total revenue']))
      .toBe('% of total revenue (2)')
  })

  it('keeps counting past the second collision', () => {
    expect(uniqueMeasureName('Average revenue',
      ['Average revenue', 'Average revenue (2)'])).toBe('Average revenue (3)')
  })
})
