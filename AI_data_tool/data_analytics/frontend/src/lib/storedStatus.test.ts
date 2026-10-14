import { describe, expect, it } from 'vitest'
import { translate, type TranslateFn } from '../i18n'
import { storedStatus } from './storedStatus'

const ar: TranslateFn = (k, v) => translate('ar', k, v)
const en: TranslateFn = (k, v) => translate('en', k, v)

describe('a stored status line in the reader\'s language', () => {
  it('reads the same in English as it was stored', () => {
    for (const s of ['clear', 'still firing (no re-send)', 'fired, emailed 2', 'posted to webhook',
      'nothing to send', 'emailed 3', 'sending (job 7)']) {
      expect(storedStatus(s, en)).toBe(s)
    }
  })
  it('is said in Arabic, part by part', () => {
    const out = storedStatus('fired, emailed 2; posted to webhook', ar)
    expect(out).not.toMatch(/[a-z]{3}/)
    expect(out).toContain('2')
  })
  it('keeps the reason of a failure as it was written', () => {
    const out = storedStatus('evaluation failed: column x is gone', ar)
    expect(out).toContain('column x is gone')
    expect(out).not.toContain('evaluation failed')
  })
  it('shows what it does not know as stored', () => {
    expect(storedStatus('SMTP said no', ar)).toBe('SMTP said no')
    expect(storedStatus(null, ar)).toBe('')
  })
  it('drops the empty reason of a blocked delivery', () => {
    expect(storedStatus('blocked: the report is Restricted -- e-mail would send its rows outside the product', en))
      .toBe('blocked: the report is Restricted -- e-mail would send its rows outside the product')
  })
})
