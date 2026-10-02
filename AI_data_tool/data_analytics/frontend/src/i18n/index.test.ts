import { describe, it, expect } from 'vitest'
import { ar } from './ar'
import { en } from './en'
import { translate, messageForPath } from './index'

describe('i18n catalogs', () => {
  it('Arabic has every English key', () => {
    const missing = Object.keys(en).filter(k => !(k in ar))
    expect(missing).toEqual([])
  })

  it('translates interpolation and falls back to English', () => {
    expect(translate('en', 'lang.aria', { name: 'English' })).toBe('Language: English')
    expect(translate('ar', 'nav.home')).toBe('الرئيسية')
    expect(translate('ar', 'home.opened', { when: 'منذ ساعة' })).toBe('فُتحت منذ ساعة')
  })

  it('maps routes to nav keys', () => {
    expect(messageForPath('/monitoring/jobs')).toBe('nav.jobs')
    expect(messageForPath('/')).toBe('nav.home')
    expect(messageForPath('/datasets/3')).toBe('nav.datasets')
  })
})

describe('Arabic plurals (HR re-test 2026-10-01)', () => {
  it('chooses the Arabic form for the number', async () => {
    const { translate } = await import('./index')
    expect(translate('ar', 'time.hoursAgo_other', { n: 2 })).toBe('منذ ساعتين')
    expect(translate('ar', 'time.hoursAgo_other', { n: 3 })).toBe('منذ 3 ساعات')
    expect(translate('ar', 'time.hoursAgo_other', { n: 11 })).toBe('منذ 11 ساعة')
    expect(translate('ar', 'home.rowsCols', { rows: '240,124', cols: 7 })).toBe('240,124 صفًا · 7 أعمدة')
    expect(translate('ar', 'home.rowsCols', { rows: 9, cols: 3 })).toBe('9 صفوف · 3 أعمدة')
  })
  it('leaves English and plain templates alone', async () => {
    const { translate, pluralize } = await import('./index')
    expect(pluralize('{n} rows', 'en', { n: 3 })).toBe('{n} rows')
    expect(translate('en', 'time.hoursAgo_other', { n: 2 })).toMatch(/2/)
  })
})
