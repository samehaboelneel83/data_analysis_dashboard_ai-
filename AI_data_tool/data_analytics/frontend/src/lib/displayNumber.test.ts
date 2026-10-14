import { describe, it, expect, beforeEach } from 'vitest'
import { formatCell, formatProseNumber, readingValue } from './displayNumber'
import { resetDigitsCache, setDigits } from './arabicFormats'

beforeEach(() => { localStorage.clear(); resetDigitsCache() })

describe('formatProseNumber (redesign 1b)', () => {
  it('rounds a long float in a sentence', () => {
    expect(formatProseNumber('61.53500000000001')).toBe('61.54')
    expect(formatProseNumber('83.88833333333332')).toBe('83.89')
    expect(formatProseNumber('3.14159')).toBe('3.14')
    expect(formatProseNumber('0.123456')).toBe('0.123')
  })

  it('leaves integers and anything at 2 dp or fewer as written', () => {
    expect(formatProseNumber('1,234.5')).toBe('1,234.5')
    expect(formatProseNumber('2025')).toBe('2025')
    expect(formatProseNumber('19.05')).toBe('19.05')
  })

  it('keeps the sign, % and thousands separators', () => {
    expect(formatProseNumber('-12.3456%')).toBe('-12.35%')
    expect(formatProseNumber('+0.04567')).toBe('+0.0457')
    expect(formatProseNumber('12,431.98765')).toBe('12,432')
  })

  it('writes the digits the reader asked for', () => {
    setDigits('arab')
    expect(formatProseNumber('61.53500000000001')).toBe('٦١٫٥٤')
  })
})

describe('numbers stay distinguishable (QA V9)', () => {
  // Average margin by region was 19.00 / 18.04 / 18.96 / 20.04 in the rows,
  // but 19 / 18 / 19 / 20 in the sentence and over the bars: 1 dp then
  // trimmed made 18.958 and 19.0 the same "19".
  it('the sentence and the chart keep 2 dp below 100, as the grid does', () => {
    expect(formatProseNumber('18.958333333')).toBe('18.96')
    expect(formatProseNumber('18.041666667')).toBe('18.04')
    expect(formatProseNumber('19.000000001')).toBe('19')
    expect(readingValue(18.958333333)).toBe(18.96)
    expect(readingValue(18.041666667)).toBe(18.04)
  })

  it('from 100 up, 1 dp is enough to tell values apart', () => {
    expect(formatProseNumber('123.456789')).toBe('123.5')
  })
})

describe('formatCell (redesign 1b)', () => {
  it('gives floats at most 2 dp, 3 significant digits below 1', () => {
    expect(formatCell(83.8883333333)).toBe('83.89')
    expect(formatCell(0.000123456)).toBe('0.000123')
    expect(formatCell('61.53500000000001')).toBe('61.54')
  })

  it('keeps integers exactly, with no thousands separators', () => {
    expect(formatCell(8632597)).toBe('8632597')
    expect(formatCell('101')).toBe('101')
  })
})

describe('readingValue (chart value labels)', () => {
  it('rounds long decimals like the sentence, and leaves short ones alone', () => {
    expect(readingValue(83.88833333333332)).toBe(83.89)
    expect(readingValue(-61.53500000000001)).toBe(-61.54)
    expect(readingValue(18.04)).toBe(18.04)
    expect(readingValue(2024)).toBe(2024)
  })
})

describe('formatTableCell (9-polish)', () => {
  it('groups a quantity, but never a year, id or a whole number written as text', async () => {
    const { formatTableCell } = await import('./displayNumber')
    expect(formatTableCell(2348914, true)).toBe('2,348,914')
    expect(formatTableCell(-1234.5678, true)).toBe('-1,234.57')
    expect(formatTableCell(2026, false)).toBe('2026')
    expect(formatTableCell('104233', true)).toBe('104233')
    expect(formatTableCell(null, true)).toBe('')
  })
  it('uses the column’s own number format: currency, decimals, percent', async () => {
    const { formatTableCell } = await import('./displayNumber')
    expect(formatTableCell(1234.5, true, { type: 'currency', symbol: '$', decimals: 2 })).toBe('$ 1,234.50')
    expect(formatTableCell(1234.5, true, { type: 'currency', symbol: 'ر.س', decimals: 0 })).toBe('1,235 ر.س')
    expect(formatTableCell(12.345, true, { type: 'percent', decimals: 1 })).toBe('12.3%')
    expect(formatTableCell(9.876, true, { type: 'integer' })).toBe('10')
    expect(formatTableCell('abc', true, { type: 'currency' })).toBe('abc')
  })
})
