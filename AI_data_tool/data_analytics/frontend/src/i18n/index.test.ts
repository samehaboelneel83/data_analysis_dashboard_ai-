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
