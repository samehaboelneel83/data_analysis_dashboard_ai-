import { describe, it, expect } from 'vitest'
import { aiLimitMessage } from './aiLimit'
import type { TranslateFn } from '../i18n'
import { en } from '../i18n/en'

const t = ((key: string, vars?: Record<string, string | number>) =>
  (en as Record<string, string>)[key].replace(/\{(\w+)\}/g, (_, k) => String(vars?.[k] ?? `{${k}}`))) as TranslateFn

const refused = (retryAfter?: string) => ({ response: { status: 429, headers: retryAfter ? { 'retry-after': retryAfter } : {} } })

describe('aiLimitMessage (E11)', () => {
  it('is null for anything that is not a limit', () => {
    expect(aiLimitMessage(new Error('down'), t)).toBeNull()
    expect(aiLimitMessage({ response: { status: 502 } }, t)).toBeNull()
    expect(aiLimitMessage(null, t)).toBeNull()
  })

  it('says when the limit resets, in the largest unit that fits', () => {
    expect(aiLimitMessage(refused('90'), t)).toMatch(/resets in 2 min\.$/)
    expect(aiLimitMessage(refused('3600'), t)).toMatch(/resets in 1 h\.$/)
    expect(aiLimitMessage(refused(String(3 * 86400 - 10)), t)).toMatch(/resets in 3 days\.$/)
  })

  it('without a usable Retry-After it still names the limit', () => {
    expect(aiLimitMessage(refused(), t)).toBe('Your organization has reached its AI limit for now. Try again later.')
    expect(aiLimitMessage(refused('soon'), t)).toMatch(/Try again later/)
  })
})
