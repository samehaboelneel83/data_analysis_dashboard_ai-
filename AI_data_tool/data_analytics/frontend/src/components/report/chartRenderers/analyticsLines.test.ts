import { describe, it, expect } from 'vitest'
import { computeAnalyticsLines } from './analyticsLines'

describe('computeAnalyticsLines', () => {
  it('returns no lines when no analytics config is set', () => {
    expect(computeAnalyticsLines([{ name: 'A', value: 10 }], undefined)).toEqual([])
  })

  it('returns a reference line at the configured constant value', () => {
    const lines = computeAnalyticsLines([{ name: 'A', value: 10 }], { referenceValue: 42, referenceLabel: 'Target', referenceColor: '#123456' })
    expect(lines).toEqual([{ value: 42, label: 'Target', color: '#123456' }])
  })

  it('defaults the reference line label and color when not provided', () => {
    const lines = computeAnalyticsLines([{ name: 'A', value: 10 }], { referenceValue: 5 })
    expect(lines[0].label).toBe('Reference')
    expect(lines[0].color).toBeTruthy()
  })

  it('computes an average line from the row values when showAverageLine is set', () => {
    const lines = computeAnalyticsLines([{ name: 'A', value: 10 }, { name: 'B', value: 20 }, { name: 'C', value: 30 }], { showAverageLine: true })
    expect(lines).toEqual([{ value: 20, label: 'Average', color: expect.any(String) }])
  })

  it('ignores non-numeric row values when computing the average', () => {
    const lines = computeAnalyticsLines([{ name: 'A', value: 10 }, { name: 'B', value: null }, { name: 'C', value: 30 }], { showAverageLine: true })
    expect(lines[0].value).toBe(20)
  })

  it('skips the average line when there is no numeric data at all', () => {
    const lines = computeAnalyticsLines([{ name: 'A', value: null }], { showAverageLine: true })
    expect(lines).toEqual([])
  })

  it('combines a reference line and an average line when both are configured', () => {
    const lines = computeAnalyticsLines([{ name: 'A', value: 10 }, { name: 'B', value: 30 }],
      { referenceValue: 50, showAverageLine: true })
    expect(lines).toHaveLength(2)
    expect(lines[0].label).toBe('Reference')
    expect(lines[1].label).toBe('Average')
    expect(lines[1].value).toBe(20)
  })
})
