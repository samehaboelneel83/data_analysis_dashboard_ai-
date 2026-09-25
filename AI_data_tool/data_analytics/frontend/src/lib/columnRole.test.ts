import { describe, it, expect } from 'vitest'
import { isIdLikeColumn } from './columnRole'

describe('isIdLikeColumn', () => {
  it('matches common id-name patterns', () => {
    expect(isIdLikeColumn({ name: 'id' })).toBe(true)
    expect(isIdLikeColumn({ name: 'state_id' })).toBe(true)
    expect(isIdLikeColumn({ name: 'student_id' })).toBe(true)
    expect(isIdLikeColumn({ name: 'account_key' })).toBe(true)
    expect(isIdLikeColumn({ name: 'session_uuid' })).toBe(true)
    expect(isIdLikeColumn({ name: 'uuid' })).toBe(true)
    expect(isIdLikeColumn({ name: 'product_code' })).toBe(true)
  })

  it('does not flag ordinary measures or dimensions', () => {
    expect(isIdLikeColumn({ name: 'revenue' })).toBe(false)
    expect(isIdLikeColumn({ name: 'quantity' })).toBe(false)
    expect(isIdLikeColumn({ name: 'region' })).toBe(false)
    // "identity" contains "id" but not as a delimited token — must not match.
    expect(isIdLikeColumn({ name: 'identity_score' })).toBe(false)
    expect(isIdLikeColumn({ name: 'valid' })).toBe(false)
  })

  it('falls back to near-uniqueness from stats when present', () => {
    expect(isIdLikeColumn({ name: 'order_ref', stats: { distinct_count: 995, row_count: 1000 } })).toBe(true)
    expect(isIdLikeColumn({ name: 'order_ref', stats: { distinct_count: 5, row_count: 1000 } })).toBe(false)
    // Missing one side of the ratio: no unwarranted claim of identity.
    expect(isIdLikeColumn({ name: 'order_ref', stats: { distinct_count: 995 } })).toBe(false)
    expect(isIdLikeColumn({ name: 'order_ref', stats: {} })).toBe(false)
  })
})
