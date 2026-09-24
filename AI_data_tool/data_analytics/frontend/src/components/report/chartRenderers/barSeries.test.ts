import { describe, it, expect } from 'vitest'
import { toBarSeries } from './barSeries'

const crosstabData = {
  type: 'crosstab',
  columns: ['region', 'A', 'B', '__total__'],
  rows: [
    ['East', 10, 20, 30],
    ['West', 5, 5, 10],
  ],
}

describe('toBarSeries', () => {
  it('returns no series for non-crosstab data (single-series bar, unchanged)', () => {
    expect(toBarSeries({ type: 'series', rows: [] }, 'clustered')).toEqual({ rows: [], series: [] })
    expect(toBarSeries(null, 'clustered')).toEqual({ rows: [], series: [] })
  })

  it('reshapes crosstab rows into wide format for clustered/stacked, excluding __total__', () => {
    const result = toBarSeries(crosstabData, 'clustered')
    expect(result.series).toEqual(['A', 'B'])
    expect(result.rows).toEqual([
      { name: 'East', A: 10, B: 20 },
      { name: 'West', A: 5, B: 5 },
    ])
  })

  it('normalizes each row to percentages summing to 100 for stacked100 mode', () => {
    const result = toBarSeries(crosstabData, 'stacked100')
    expect(result.series).toEqual(['A', 'B'])
    expect(result.rows[0]).toEqual({ name: 'East', A: (10 / 30) * 100, B: (20 / 30) * 100 })
    expect(result.rows[1]).toEqual({ name: 'West', A: 50, B: 50 })
  })

  it('treats a row with all-zero series values as 0% rather than dividing by zero', () => {
    const result = toBarSeries({ ...crosstabData, rows: [['Zero', 0, 0, 0]] }, 'stacked100')
    expect(result.rows).toEqual([{ name: 'Zero', A: 0, B: 0 }])
  })
})
