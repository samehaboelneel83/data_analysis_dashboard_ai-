import { describe, it, expect } from 'vitest'
import { ar } from './ar'
import { en } from './en'
import { translate, messageForPath, pluralize } from './index'

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

describe('Arabic column counts agree with the number (QA T2)', () => {
  it('"8 أعمدة", not "8 عمود", whichever digits the reader uses', () => {
    expect(translate('ar', 'home.colsOnly', { cols: '8' })).toBe('8 أعمدة · مباشر')
    expect(translate('ar', 'home.colsOnly', { cols: '٨' })).toBe('٨ أعمدة · مباشر')
    expect(translate('ar', 'home.colsOnly', { cols: '12' })).toBe('12 عمودًا · مباشر')
    expect(translate('ar', 'ov3.trust.headerCols', { n: '3' })).toBe('قُرئت 3 أعمدة من صف العناوين')
    expect(translate('ar', 'ov3.first.body', { rows: '2,000', cols: '13' })).toMatch(/^قرأنا 2,000 صف و13 عمودًا\./)
    expect(translate('ar', 'ov3.glance.profiling', { n: '5' })).toBe('جارٍ تحليل 5 أعمدة…')
  })

  it('the plural rule reads Arabic-Indic digits too', () => {
    expect(pluralize('{n, plural, one{صف واحد} two{صفّان} few{# صفوف} many{# صفًا} other{# صف}}', 'ar', { n: '٣' })).toBe('٣ صفوف')
  })
})

describe('Arabic product names read naturally (QA T2)', () => {
  it('Ask AI, Lineage and Automations', () => {
    expect(ar['nav.askAi']).toBe('اسأل الذكاء الاصطناعي')
    expect(ar['copilot.title']).toBe('اسأل الذكاء الاصطناعي')
    // "النسب" reads as ratios or family lineage; "التحليلات الآلية" as
    // automated analytics, not automations.
    expect(ar['nav.lineage']).toBe('تتبّع المصدر')
    expect(ar['ov3.lineage.open']).not.toMatch(/النسب/)
    expect(ar['nav.automations']).toBe('الأتمتة')
  })
})

describe('my own activity reads in the first person (QA T2)', () => {
  it('"حذفتَ …", not "تم حذف … بواسطة أنت", for every action', () => {
    const acts = Object.keys(en).filter(k => /^hm\.act\.(upload|refresh|share|create|publish|unpublish|release|restore|delete)$/.test(k))
    expect(acts).toHaveLength(9)
    for (const k of acts) {
      const mine = k.replace('hm.act.', 'hm.actMine.') as keyof typeof en
      expect(en[mine], mine).toMatch(/^You .*\{name\}/)
      expect(ar[mine], mine).toContain('{name}')
      expect(ar[mine], mine).not.toMatch(/بواسطة|\{who\}/)
    }
    expect(ar['hm.actMine.delete' as keyof typeof ar]).toBe('حذفتَ {name}')
  })
})

describe('the Columns tab header (QA T2)', () => {
  it('"Use as" is a whole word in Arabic, not a dangling "كـ" that reads as cut off', () => {
    expect(ar['cols3.useAs']).not.toMatch(/ـ$/)
    expect(ar['cols3.useAs']).toBe('الاستخدام')
  })
})
