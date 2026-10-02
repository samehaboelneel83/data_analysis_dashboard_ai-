import { describe, it, expect } from 'vitest'
import { updatedAgo } from './viewStyle'

describe('updatedAgo', () => {
  const now = Date.parse('2026-09-27T12:00:00Z')
  it('says how long ago, in the reader language, with Latin digits', () => {
    expect(updatedAgo('2026-09-27T11:48:00Z', 'en', now)).toBe('12 minutes ago')
    expect(updatedAgo('2026-09-27T09:00:00Z', 'en', now)).toBe('3 hours ago')
    expect(updatedAgo('2026-09-25T12:00:00Z', 'en', now)).toBe('2 days ago')
    expect(updatedAgo('2026-09-27T11:59:30Z', 'en', now)).toBe('now')
    expect(updatedAgo('2026-09-27T11:48:00Z', 'ar', now)).toMatch(/12/)
  })
  it('says nothing when there is no time to report', () => {
    expect(updatedAgo(null, 'en', now)).toBeNull()
    expect(updatedAgo('not a date', 'en', now)).toBeNull()
  })
})
