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
