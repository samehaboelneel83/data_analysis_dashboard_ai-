import { describe, it, expect } from 'vitest'
import { translate, en, ar, type TranslateFn } from '../i18n'
import { dtypeName, dtypeShort, KNOWN_DTYPES } from './dtypeName'

const tEn: TranslateFn = (k, v) => translate('en', k, v)
const tAr: TranslateFn = (k, v) => translate('ar', k, v)

const FULL: Record<string, [string, string]> = {
  numeric: ['Number', 'رقم'], number: ['Number', 'رقم'],
  integer: ['Whole number', 'عدد صحيح'], int: ['Whole number', 'عدد صحيح'],
  float: ['Decimal number', 'عدد عشري'],
  categorical: ['Category', 'فئة'],
  text: ['Text', 'نص'], string: ['Text', 'نص'], object: ['Text', 'نص'],
  datetime: ['Date & time', 'تاريخ ووقت'], date: ['Date', 'تاريخ'], time: ['Time', 'وقت'],
  boolean: ['True/false', 'صح/خطأ'], bool: ['True/false', 'صح/خطأ'],
  geometry: ['Geometry', 'شكل جغرافي'],
  calculated: ['Calculated', 'محسوب'],
}
const SHORT: Record<string, [string, string]> = {
  numeric: ['NUM', 'رقم'], number: ['NUM', 'رقم'],
  integer: ['INT', 'صحيح'], int: ['INT', 'صحيح'], float: ['DEC', 'عشري'],
  categorical: ['TXT', 'نص'], text: ['TXT', 'نص'], string: ['TXT', 'نص'], object: ['TXT', 'نص'],
  datetime: ['DATE', 'تاريخ'], date: ['DATE', 'تاريخ'], time: ['TIME', 'وقت'],
  boolean: ['BOOL', 'منطقي'], bool: ['BOOL', 'منطقي'],
  geometry: ['GEO', 'جغرافي'], calculated: ['CALC', 'محسوب'],
}

describe('dtypeName (QA5 L3)', () => {
  it('covers every known code in the table above', () => {
    expect(Object.keys(FULL).sort()).toEqual([...KNOWN_DTYPES].sort())
    expect(Object.keys(SHORT).sort()).toEqual([...KNOWN_DTYPES].sort())
  })

  it.each(Object.entries(FULL))('%s → full name in English and Arabic', (code, [e, a]) => {
    expect(dtypeName(tEn, code)).toBe(e)
    expect(dtypeName(tAr, code)).toBe(a)
  })

  it.each(Object.entries(SHORT))('%s → badge in English and Arabic', (code, [e, a]) => {
    expect(dtypeShort(tEn, code)).toBe(e)
    expect(dtypeShort(tAr, code)).toBe(a)
  })

  it('reads the code case-insensitively', () => {
    expect(dtypeName(tAr, 'NUMERIC')).toBe('رقم')
  })

  it('an unknown code comes back raw (badge: first four letters, upper-cased)', () => {
    for (const t of [tEn, tAr]) {
      expect(dtypeName(t, 'VARCHAR(20)')).toBe('VARCHAR(20)')
      expect(dtypeName(t, '')).toBe('')
      expect(dtypeName(t, undefined)).toBe('')
      expect(dtypeShort(t, 'uuid')).toBe('UUID')
      expect(dtypeShort(t, 'decimal')).toBe('DECI')
    }
  })

  it('every pg.types key exists in both catalogs, and Arabic never repeats the English', () => {
    const keys = Object.keys(en).filter(k => k.startsWith('pg.types.'))
    expect(keys.length).toBeGreaterThan(0)
    for (const k of keys) {
      const a = (ar as Record<string, string>)[k]
      expect(a).toBeTruthy()
      expect(a).not.toBe((en as Record<string, string>)[k])
    }
  })
})
