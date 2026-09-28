import { describe, it, expect, afterAll } from 'vitest'
import { displayLocaleFor, installDisplayLocale, setDisplayLocale } from './displayLocale'

// Live QA 2026-09-28: on a Windows machine set to Arabic, an English page read
// "Last refreshed 28ص 1:38:17 2026/9/". Bare formatting follows the INTERFACE
// language now.
describe('dates and numbers follow the interface language', () => {
  // Arabic is a pass-through: the call reaches whatever sits beneath (the
  // browser -- or, in this suite, the en-US pin in test/setup.ts).
  afterAll(() => setDisplayLocale('ar'))

  const day = new Date(2026, 8, 27, 16, 7, 9)

  it('English formats a bare call as en-GB: day/month/year', () => {
    installDisplayLocale('en')
    expect(day.toLocaleDateString()).toBe('27/09/2026')
    expect((1234.5).toLocaleString()).toBe('1,234.5')
    expect(new Intl.DateTimeFormat(undefined, { month: 'short' }).format(day)).toBe('Sept')
  })

  it('a call that names its locale is never touched', () => {
    installDisplayLocale('en')
    expect(day.toLocaleDateString('en-US')).toBe('9/27/2026')
    expect((1234).toLocaleString('ar-EG')).toBe('١٬٢٣٤')
  })

  it('switching to Arabic hands bare calls back to the default', () => {
    installDisplayLocale('en')
    setDisplayLocale('ar')
    expect(day.toLocaleDateString()).toBe('9/27/2026')          // the suite's own en-US pin
    expect(displayLocaleFor('ar')).toBeUndefined()
    expect(displayLocaleFor('en')).toBe('en-GB')
  })
})
