import { describe, it, expect, beforeEach } from 'vitest'
import { getDigits, hijriLabel, localDigits, resetDigitsCache, setDigits, symbolAfter } from './arabicFormats'
import { fmtStr } from '../components/report/chartUtils'

beforeEach(() => { localStorage.clear(); resetDigitsCache() })

describe('Arabic formats (Phase 7.5)', () => {
  it('keeps Western digits by default and converts on request, separators included', () => {
    expect(getDigits()).toBe('latn')
    expect(localDigits('1,234.5 units')).toBe('1,234.5 units')
    setDigits('arab')
    expect(localDigits('1,234.5 units')).toBe('١٬٢٣٤٫٥ units')
    expect(localStorage.getItem('datalytics.digits')).toBe('arab')
  })

  it('formats every number through the preference, and puts an Arabic symbol after the amount', () => {
    setDigits('arab')
    expect(fmtStr(1234.5, { type: 'number', decimals: 1 })).toContain('١٬٢٣٤٫٥')
    const riyal = fmtStr(1200, { type: 'currency', symbol: 'ر.س', decimals: 0 })
    expect(riyal.indexOf('ر.س')).toBeGreaterThan(riyal.indexOf('١'))
    setDigits('latn')
    const dollars = fmtStr(1200, { type: 'currency', symbol: '$', decimals: 0 })
    expect(dollars.indexOf('$')).toBeLessThan(dollars.indexOf('1'))
    expect(symbolAfter('SAR')).toBe(false)
    expect(symbolAfter('SAR', 'after')).toBe(true)
  })

  it('names Hijri buckets in the reader language', () => {
    expect(hijriLabel('1444-09', 'en')).toBe('Ramadan 1444')
    expect(hijriLabel('1444-09', 'ar')).toBe('رمضان 1444 هـ')
    expect(hijriLabel('1444', 'en')).toBe('1444 AH')
    expect(hijriLabel('2026-09-01', 'en')).toBe('2026-09-01')
  })
})
