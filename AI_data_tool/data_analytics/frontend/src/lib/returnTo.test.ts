import { describe, it, expect, beforeEach } from 'vitest'
import { rememberReturnTo, safeReturnTo, takeReturnTo } from './returnTo'

describe('returnTo (AD-12)', () => {
  beforeEach(() => sessionStorage.clear())

  it('accepts a path on this site only', () => {
    expect(safeReturnTo('/reports/1?x=1#w')).toBe('/reports/1?x=1#w')
    for (const bad of ['//evil.example', '/\\evil.example', 'https://evil.example', 'reports/1', '/login', '/login?x', 42, null]) {
      expect(safeReturnTo(bad)).toBeNull()
    }
    expect(safeReturnTo('/logins')).toBe('/logins')
  })

  it('is read once after an SSO round trip', () => {
    rememberReturnTo('/reports/3')
    expect(takeReturnTo()).toBe('/reports/3')
    expect(takeReturnTo()).toBeNull()
  })
})
