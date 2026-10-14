import { localDigits } from './arabicFormats'

/**
 * QA3 D4: one way to write a date and time, driven by the UI language rather
 * than the browser's own locale. `toLocaleString()` with no locale wrote
 * "10/7/2026 12:03 AM" in the Arabic UI and day/month in the English one,
 * depending only on the machine.
 *
 * English: day/month/year and a 24-hour clock (en-GB), as the version history
 * already wrote it (QA2 V10). Arabic: the Arabic calendar words with Latin
 * digits, then the reader's digit preference (localDigits).
 *
 * The language is the document's (`<html lang>`, set by DirectionContext), so
 * any code can call these without a hook; a component re-renders on a
 * language switch anyway.
 */
export type DateStyle = 'datetime' | 'date' | 'time'

const OPTS: Record<DateStyle, Intl.DateTimeFormatOptions> = {
  datetime: { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' },
  date: { year: 'numeric', month: 'short', day: 'numeric' },
  time: { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' },
}

export function uiLanguage(): 'ar' | 'en' {
  try { return document.documentElement.lang === 'ar' ? 'ar' : 'en' } catch { return 'en' }
}

export function dateLocale(lang: string = uiLanguage()): string {
  return lang === 'ar' ? 'ar-u-nu-latn' : 'en-GB'
}

/** A date (ISO string, epoch ms or Date) in the UI language; '' when it is not a date. */
export function formatDate(value: string | number | Date | null | undefined, style: DateStyle = 'datetime',
                           lang: string = uiLanguage()): string {
  if (value == null || value === '') return ''
  const d = value instanceof Date ? value : new Date(value)
  if (isNaN(d.getTime())) return ''
  const s = d.toLocaleString(dateLocale(lang), OPTS[style])
  return lang === 'ar' ? localDigits(s) : s
}
