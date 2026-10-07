import { describe, it, expect } from 'vitest'
import { majorityDir } from './autoDir'

describe('majorityDir (redesign 1c)', () => {
  it('reads an Arabic answer that opens with a data value as RTL', () => {
    expect(majorityDir('Medicine الأعلى بمتوسط 83.9', 'ltr')).toBe('rtl')
  })

  it('reads an English answer as LTR in the Arabic UI', () => {
    expect(majorityDir('Arts is lowest', 'rtl')).toBe('ltr')
  })

  it('falls back to the UI direction with no letters, a tie or no text', () => {
    expect(majorityDir('83.9', 'rtl')).toBe('rtl')
    expect(majorityDir('ab جد', 'ltr')).toBe('ltr')
    expect(majorityDir('', 'rtl')).toBe('rtl')
  })

  it('does not count Arabic-Indic digits as letters', () => {
    expect(majorityDir('Total ٨٣٫٩٠٠٠', 'rtl')).toBe('ltr')
  })
})
