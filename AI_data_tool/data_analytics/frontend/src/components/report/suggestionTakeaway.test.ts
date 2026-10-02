import { describe, it, expect } from 'vitest'
import { axisNames, short, signature, takeaway, thumbnail, when } from './suggestionTakeaway'

// The real numbers behind dashboard 213 (Olist_order_items, 100,000 rows).
const STATUS = [['delivered', 1952292], ['shipped', 23245], ['canceled', 9532], ['processing', 8034],
  ['invoiced', 6664], ['unavailable', 133], ['approved', 31]].map(([name, value]) => ({ name, value }))
const P_HIST = [94639, 3603, 1020, 328, 180, 119, 47, 23, 20, 5, 4, 5, 2, 3, 1, 0, 0, 0, 0, 1]
  .map((value, i) => ({ name: i === 0 ? '0.85–337.56' : `bin ${i}`, value }))

describe('takeaway: what the chart says, from its own rows', () => {
  it('a comparison leads with the biggest share', () => {
    const t = takeaway('bar', { dimension: 'order_status', measure: 'freight_value', aggregation: 'sum' }, STATUS)!
    expect(t.headline).toBe('Delivered has 98% of freight value')
    expect(t.detail).toMatch(/^Delivered accounts for 1,952,292 of 1,999,931 \(98%\)\. Next is shipped/)
    expect(t.strength).toBeGreaterThan(0.95)
  })

  it('a trend names its peak in words', () => {
    const rows = [['2018-06', 95586], ['2018-07', 163480], ['2018-08', 208716], ['2018-09', 47256]]
      .map(([name, value]) => ({ name, value }))
    expect(takeaway('line', { dimension: 'd', measure: 'freight_value' }, rows)!.headline)
      .toBe('Freight value peaked in Aug 2018 at 208.7K')
  })

  it('a weekly trend names the week by its first day', () => {
    expect(when({ name: '2018-W33', bin_start: '2018-08-13 00:00:00' })).toBe('the week of 13 Aug 2018')
  })

  it('a distribution says where most values sit', () => {
    const t = takeaway('histogram', { measure: 'price', bins: 20 }, P_HIST)!
    expect(t.headline).toBe('95% of rows have price under 338')
    expect(t.detail).toBe('94,639 of 100,000 rows (95%) have price in 0.85–337.56.')
  })

  it('has nothing to say without rows, so the card keeps its title', () => {
    expect(takeaway('bar', { dimension: 'a', measure: 'b' }, undefined)).toBeNull()
    expect(takeaway('bar', { dimension: 'a', measure: 'b' }, [])).toBeNull()
  })

  it('rounds for a headline', () => {
    expect([short(1178107), short(208716), short(337.56), short(20.48), short(6.5)]).toEqual(['1.18M', '208.7K', '338', '20.5', '6.5'])
  })
})

describe('axis names in words', () => {
  it('names both axes of a comparison', () => {
    expect(axisNames('bar', { dimension: 'order_status', measure: 'freight_value', aggregation: 'sum' }))
      .toEqual({ x: 'Order status', y: 'Total freight value' })
  })
  it('a histogram counts rows', () => {
    expect(axisNames('histogram', { measure: 'price' })).toEqual({ x: 'Price', y: 'Number of rows' })
  })
  it('a pie has no axes', () => {
    expect(axisNames('pie', { dimension: 'a', measure: 'b' })).toEqual({})
  })
})

describe('already on the page', () => {
  it('a donut of price by status is the same idea as a bar of it', () => {
    expect(signature('donut', { dimension: 'order_status', measure: 'price' }))
      .toBe(signature('bar', { dimension: 'order_status', measure: 'price', aggregation: 'sum' }))
    expect(signature('line', { dimension: 'd', measure: 'price' }))
      .not.toBe(signature('bar', { dimension: 'd', measure: 'price' }))
  })
})

describe('thumbnail', () => {
  it('draws bars for a comparison and a line for a trend', () => {
    expect(thumbnail('bar', STATUS)!.kind).toBe('bars')
    expect(thumbnail('line', STATUS)!.kind).toBe('line')
    expect(thumbnail('bar', [])).toBeNull()
  })
})

describe('takeaway for averages (HR evaluation)', () => {
  it('names the highest average instead of a share of a total', () => {
    const t = takeaway('bar', { measure: 'salary', aggregation: 'avg', dimension: 'dept_name' },
      [{ name: 'Sales', value: 88853 }, { name: 'Human Resources', value: 63922 }])
    expect(t?.headline).toMatch(/highest average salary/)
    expect(t?.headline).not.toMatch(/%/)
  })
})

describe('a flat comparison is called flat', () => {
  it('does not headline a winner when every group is within 2%', () => {
    const t = takeaway('bar', { dimension: 'gender', measure: 'salary', aggregation: 'avg' },
      [{ name: 'M', value: 72045 }, { name: 'F', value: 71964 }])
    expect(t?.headline).toBe('Average salary is about the same for every gender: 72K')
  })
})
