import { describe, it, expect } from 'vitest'
import { translate } from './index'

/** QA5 word check: "7 يومًا" read wrong; 3–10 take أيام. */
describe('days in Arabic (share link expiry)', () => {
  it.each([[1, 'يوم واحد'], [2, 'يومان'], [7, '7 أيام'], [30, '30 يومًا']])('%i → %s', (n, want) => {
    expect(translate('ar', 'shx.gl.days', { n })).toBe(want)
  })
})
