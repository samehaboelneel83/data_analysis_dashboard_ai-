import { describe, it, expect } from 'vitest'
import { cellText, toCsv } from './ResultView'

/**
 * Ask AI's result grid was printing a summed currency column as
 * "2010526.4600000004" -- the double's honest answer to adding .46 a few
 * hundred times, and a number no one reads as a total.
 */
describe('cellText', () => {
  it('drops binary-float noise from a summed value', () => {
    expect(cellText(2010526.4600000004)).toBe('2010526.46')
    expect(cellText(0.1 + 0.2)).toBe('0.3')
  })

  it('leaves integers and ids exactly as they are', () => {
    expect(cellText(2024)).toBe('2024')
    expect(cellText(8632597)).toBe('8632597')
  })

  it('does not group digits', () => {
    // This grid shows whatever columns the question returned, ids included.
    expect(cellText(12345.5)).toBe('12345.5')
  })

  it('keeps a value someone actually typed', () => {
    expect(cellText(19.05)).toBe('19.05')
    expect(cellText(-0.125)).toBe('-0.125')
  })

  it('passes non-numbers through', () => {
    expect(cellText('Europe')).toBe('Europe')
    expect(cellText(null)).toBe('')
    expect(cellText(true)).toBe('true')
  })

  it('rounds long floats for reading (redesign 1b)', () => {
    expect(cellText(61.53500000000001)).toBe('61.54')
    expect(cellText(83.8883333333)).toBe('83.89')
    expect(cellText(2024)).toBe('2024')
    expect(cellText(0.123456)).toBe('0.123')
  })
})

describe('toCsv', () => {
  // Owner decision (redesign 1b): exports carry raw values at full precision;
  // the screen rounds for reading.
  it('exports raw values at full precision', () => {
    const csv = toCsv([{ columns: ['faculty', 'average_final_score'],
      rows: [['Arts', 61.53500000000001], ['Region', 2010526.4600000004]] } as any])
    expect(csv).toContain('61.53500000000001')
    expect(csv).toContain('2010526.4600000004')
  })
})
