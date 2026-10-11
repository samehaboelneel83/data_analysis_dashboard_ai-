import { describe, it, expect } from 'vitest'
import { translate } from '../i18n'
import { takeawayText } from './readbackText'

const said = {
  key: 'highest',
  vars: { top: 'Sales', v: '88,853', bottom: 'Human Resources', vb: '63,922',
          what: { key: 'what.agg', vars: { agg: { key: 'agg.avg', vars: { agg: 'avg' } }, m: 'salary' } } },
}
const english = 'Sales is highest at 88,853 and Human Resources lowest at 63,922 (average salary).'

describe('the readback sentence in the reader\'s language', () => {
  it('reads the same as the server in English', () => {
    const tr = (k: never, v?: never) => translate('en', k, v)
    expect(takeawayText(tr as never, { takeaway: english, takeaway_i18n: said })).toBe(english)
  })

  it('is said in Arabic, nested phrases included', () => {
    const tr = (k: never, v?: never) => translate('ar', k, v)
    expect(takeawayText(tr as never, { takeaway: english, takeaway_i18n: said }))
      .toBe('الأعلى Sales بـ 88,853 والأدنى Human Resources بـ 63,922 (متوسط salary).')
  })

  it('falls back to the English sentence for a key it does not know', () => {
    const tr = (k: never, v?: never) => translate('ar', k, v)
    expect(takeawayText(tr as never, { takeaway: english, takeaway_i18n: { key: 'nope', vars: {} } })).toBe(english)
    expect(takeawayText(tr as never, { takeaway: null })).toBeUndefined()
  })
})

describe('the discovery engine\'s sentences in Arabic', () => {
  const ar = ((k: never, v?: never) => translate('ar', k, v)) as never
  it('says a health check, a timeline note and a finding with their own numbers', () => {
    expect(takeawayText(ar, { takeaway: '104 rows are exact copies of another row (1.2%); every total counts them twice.',
      takeaway_i18n: { key: 'health.dup.some', vars: { n: '104', pct: '1.2' } } }))
      .toBe('104 صفًا نسخ مطابقة لصف آخر (1.2%)؛ كل مجموع يحسبها مرتين.')
    expect(takeawayText(ar, { takeaway: 'x', takeaway_i18n: { key: 'tl.above', vars: { period: '2024-W45', value: '117,334', bound: '67,288' } } }))
      .toBe('2024-W45: 117,334، بينما كان المتوقع من تاريخها 67,288 على الأكثر.')
    // Nested pieces (a month's name) are said in Arabic too.
    expect(takeawayText(ar, { takeaway: 'x', takeaway_i18n: { key: 'ev.season',
      vars: { top: { key: 'mon.nov' }, top_pct: '+86', low: { key: 'mon.feb' }, low_pct: '-22' } } }))
      .toContain('نوفمبر')
  })
  it('falls back to the English sentence for a key it does not know', () => {
    expect(takeawayText(ar, { takeaway: 'Plain words.', takeaway_i18n: { key: 'health.not.there' } })).toBe('Plain words.')
  })
})
