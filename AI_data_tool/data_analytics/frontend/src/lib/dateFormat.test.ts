import { describe, it, expect, afterEach } from 'vitest'
import { formatDate, dateLocale } from './dateFormat'

describe('one date format, driven by the UI language (QA3 D4)', () => {
  afterEach(() => { document.documentElement.lang = '' })
  const at = '2026-10-07T00:03:00'

  it('English: day before month, 24-hour clock', () => {
    document.documentElement.lang = 'en'
    expect(formatDate(at)).toBe('7 Oct 2026, 00:03')
  })

  it('Arabic: Arabic month name, 24-hour clock, never the US m/d/yyyy h:mm AM', () => {
    document.documentElement.lang = 'ar'
    const s = formatDate(at)
    expect(s).toMatch(/أكتوبر/)
    expect(s).toMatch(/00:03/)
    expect(s).not.toMatch(/AM|PM|10\/7\/2026/)
  })

  it('date only and time only; nothing for a non-date', () => {
    expect(formatDate(at, 'date', 'en')).toBe('7 Oct 2026')
    expect(formatDate(at, 'time', 'en')).toBe('00:03')
    expect(formatDate('not a date')).toBe('')
    expect(formatDate(null)).toBe('')
    expect(dateLocale('ar')).toBe('ar-u-nu-latn')
  })
})

describe('no date written in the browser\'s own locale (QA3 D4)', () => {
  it('no `new Date(…).toLocaleString()` / `toLocaleDateString()` without a locale in src', async () => {
    const fs = await import('node:fs'); const path = await import('node:path')
    const root = path.join(__dirname, '..')
    const offenders: string[] = []
    const walk = (d: string) => {
      for (const e of fs.readdirSync(d, { withFileTypes: true })) {
        const p = path.join(d, e.name)
        if (e.isDirectory()) walk(p)
        else if (/\.tsx?$/.test(e.name) && !/\.test\.tsx?$/.test(e.name)) {
          const src = fs.readFileSync(p, 'utf8')
          if (/new Date\([^)]*\)\.toLocale(String|DateString|TimeString)\(\)/.test(src)) offenders.push(path.relative(root, p))
        }
      }
    }
    walk(root)
    expect(offenders).toEqual([])
  })
})
