import { describe, it, expect } from 'vitest'
import { contrastTokens, parseColor } from './contrastTokens'

describe('text follows a custom widget background (QA4 V1)', () => {
  it('a light background (#fde68a) gets dark text in either theme', () => {
    expect(contrastTokens('#fde68a')['--text']).toBe('#1f2328')
  })
  it('a dark background gets light text', () => {
    expect(contrastTokens('#1e293b')['--text']).toBe('#f3f5f7')
    expect(contrastTokens('rgb(20, 30, 40)')['--text']).toBe('#f3f5f7')
  })
  it('no custom colour, a variable or a gradient changes nothing', () => {
    expect(contrastTokens(undefined)).toEqual({})
    expect(contrastTokens('var(--surface)')).toEqual({})
    expect(contrastTokens('linear-gradient(#fff, #000)')).toEqual({})
  })
  it('short hex forms parse', () => {
    expect(parseColor('#fff')).toEqual([255, 255, 255])
    expect(parseColor('#fde68aff')).toEqual([253, 230, 138])
  })
})
