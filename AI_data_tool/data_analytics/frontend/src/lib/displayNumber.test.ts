import { describe, it, expect, beforeEach } from 'vitest'
import { formatCell, formatProseNumber, readingValue } from './displayNumber'
import { resetDigitsCache, setDigits } from './arabicFormats'

beforeEach(() => { localStorage.clear(); resetDigitsCache() })

describe('formatProseNumber (redesign 1b)', () => {
  it('rounds a long float in a sentence', () => {
    expect(formatProseNumber('61.53500000000001')).toBe('61.5')
    expect(formatProseNumber('83.88833333333332')).toBe('83.9')
    expect(formatProseNumber('3.14159')).toBe('3.14')
    expect(formatProseNumber('0.123456')).toBe('0.123')
  })

  it('leaves integers and anything at 2 dp or fewer as written', () => {
    expect(formatProseNumber('1,234.5')).toBe('1,234.5')
    expect(formatProseNumber('2025')).toBe('2025')
    expect(formatProseNumber('19.05')).toBe('19.05')
  })

  it('keeps the sign, % and thousands separators', () => {
    expect(formatProseNumber('-12.3456%')).toBe('-12.3%')
    expect(formatProseNumber('+0.04567')).toBe('+0.0457')
    expect(formatProseNumber('12,431.98765')).toBe('12,432')
  })

  it('writes the digits the reader asked for', () => {
    setDigits('arab')
    expect(formatProseNumber('61.53500000000001')).toBe('٦١٫٥')
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
    expect(readingValue(83.88833333333332)).toBe(83.9)
    expect(readingValue(-61.53500000000001)).toBe(-61.5)
    expect(readingValue(18.04)).toBe(18.04)
    expect(readingValue(2024)).toBe(2024)
  })
})
