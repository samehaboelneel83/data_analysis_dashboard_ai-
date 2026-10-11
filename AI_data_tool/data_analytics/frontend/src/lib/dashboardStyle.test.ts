import { describe, expect, it } from 'vitest'
import { FONT_STACKS, SHADOWS, styleGap, styleVars, tidyStyle } from './dashboardStyle'

const vars = (s: Parameters<typeof styleVars>[0]) => styleVars(s) as Record<string, string>

describe('a dashboard style as CSS properties', () => {
  it('is nothing at all for an empty style', () => {
    expect(styleVars(null)).toEqual({})
    expect(styleVars({})).toEqual({})
  })
  it('carries the font, the title and the card', () => {
    const v = vars({ font_family: 'serif', font_size: 13, title_size: 18, title_weight: 700, title_align: 'center',
      border_style: 'dashed', border_width: 2, border_color: '#ff0000', radius: 6, shadow: 'raised' })
    expect(v.fontFamily).toBe(FONT_STACKS.serif)
    expect(v['--dl-s-title-size']).toBe('18px')
    expect(v['--dl-s-title-weight']).toBe('700')
    expect(v['--dl-s-title-align']).toBe('center')
    expect(v['--dl-s-border']).toBe('2px dashed #ff0000')
    expect(v['--dl-s-radius']).toBe('6px')
    expect(v['--dl-s-shadow']).toBe(SHADOWS.raised)
  })
  it('draws no border when the style says none, and a double one wide enough to read', () => {
    expect(vars({ border_style: 'none' })['--dl-s-border']).toBe('0 solid transparent')
    expect(vars({ border_style: 'double', border_width: 1 })['--dl-s-border']).toMatch(/^3px double /)
  })
  it('makes a dark dashboard dark whatever the app theme, and lets explicit colours win', () => {
    const v = vars({ mode: 'dark', card_background: '#101010' })
    expect(v['--surface']).toBe('#101010')
    expect(v['--text']).toBe('#e2e8f0')
    expect(v.colorScheme).toBe('dark')
    expect(vars({ mode: 'auto' })['--surface']).toBeUndefined()
  })
  it('turns density into a gap and keeps only what was set', () => {
    expect(styleGap({ density: 'compact' })).toBe(6)
    expect(styleGap({ gap: 20, density: 'compact' })).toBe(20)
    expect(styleGap({})).toBeUndefined()
    expect(tidyStyle({ radius: 4, title_color: '', font_family: undefined })).toEqual({ radius: 4 })
  })
})
