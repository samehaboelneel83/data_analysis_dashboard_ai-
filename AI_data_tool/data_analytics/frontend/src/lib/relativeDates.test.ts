import { describe, it, expect } from 'vitest'
import { DEFAULT_SPEC, describeSpec, isRelativeSpec, parseSpec, presetOf, specProblem } from './relativeDates'

describe('relativeDates', () => {
  it('describes specs in the server wording, naming the anchor', () => {
    expect(describeSpec({ mode: 'last', unit: 'day', n: 30, anchor: 'data_max' })).toBe('Last 30 days · from latest data')
    expect(describeSpec({ mode: 'last', unit: 'month', n: 3, anchor: 'today' })).toBe('Last 3 months (complete) · from today')
    expect(describeSpec({ mode: 'last', unit: 'month', n: 1, anchor: 'today', include_current: true })).toBe('Last 1 month (incl. current) · from today')
    expect(describeSpec({ mode: 'to_date', unit: 'year', anchor: 'today' })).toBe('Year to date · from today')
    expect(describeSpec({ mode: 'rolling', unit: 'month', n: 12, anchor: 'today' })).toBe('Rolling 12 months · from today')
  })

  it('parses stored JSON and falls back to the default on junk', () => {
    expect(parseSpec('{"mode":"to_date","unit":"month","anchor":"today"}').mode).toBe('to_date')
    expect(parseSpec('nope')).toEqual(DEFAULT_SPEC)
    expect(parseSpec({ mode: 'soon' })).toEqual(DEFAULT_SPEC)
    expect(isRelativeSpec({ mode: 'last', unit: 'day', anchor: 'yesterday' })).toBe(false)
  })

  it('refuses a period count outside 1..1000 only where a count is used', () => {
    expect(specProblem({ mode: 'last', unit: 'day', n: 0, anchor: 'today' })).toMatch(/1 to 1000/)
    expect(specProblem({ mode: 'last', unit: 'day', n: 2.5, anchor: 'today' })).toMatch(/whole number/)
    expect(specProblem({ mode: 'to_date', unit: 'month', anchor: 'today' })).toBeNull()
  })

  it('recognises presets and otherwise reports custom', () => {
    expect(presetOf({ mode: 'last', unit: 'day', n: 30, anchor: 'today' })).toBe('l30d')
    expect(presetOf({ mode: 'last', unit: 'day', n: 31, anchor: 'today' })).toBe('custom')
  })
})
