import { describe, it, expect } from 'vitest'
import { seriesDash, fillPattern } from './chartUtils'
import { THEMES, SERIES_DASHES, SERIES_PATTERNS } from './themes'

describe('accessible series encoding', () => {
  it('stays off unless a report opts in, so nothing changes for existing reports', () => {
    expect(seriesDash(0)).toBeUndefined()
    expect(seriesDash(1)).toBeUndefined()
    expect(seriesDash(1, false)).toBeUndefined()
  })

  it('leaves the first series solid and distinguishes the rest', () => {
    // Redundant encoding only has to separate series from EACH OTHER; a lone line
    // needs no pattern, so index 0 stays solid and the chart keeps its clean default.
    expect(seriesDash(0, true)).toBeUndefined()
    expect(seriesDash(1, true)).toBeDefined()
    expect(seriesDash(2, true)).toBeDefined()
    expect(seriesDash(1, true)).not.toBe(seriesDash(2, true))
  })

  it('wraps rather than running out of patterns', () => {
    const n = SERIES_DASHES.length
    expect(seriesDash(n + 1, true)).toBe(seriesDash(1, true))
  })

  it('fills marks with the plain colour unless a report opts in', () => {
    // Same off-by-default contract as seriesDash, so existing bar/pie/donut reports
    // render byte-identically until an author turns the accessibility toggle on.
    expect(fillPattern(1, '#123456')).toBe('#123456')
    expect(fillPattern(1, '#123456', false)).toBe('#123456')
  })

  it('leaves the first group a solid fill and hatches the rest', () => {
    // A lone group needs no texture; index 0 keeps the clean solid fill and later
    // groups reference their own <pattern> so colour + hatch carry the same split.
    expect(fillPattern(0, '#123456', true)).toBe('#123456')
    expect(fillPattern(1, '#123456', true)).toBe('url(#fillpat-1)')
    expect(fillPattern(2, '#123456', true)).toBe('url(#fillpat-2)')
  })

  it('ships a fill motif for every dash slot so the two encodings stay aligned', () => {
    expect(SERIES_PATTERNS.length).toBe(SERIES_DASHES.length)
    // both keep the first slot solid/undefined -- the "lone series is clean" rule
    expect(SERIES_PATTERNS[0]).toBeUndefined()
  })

  it('ships a high-contrast palette alongside the decorative ones', () => {
    expect(THEMES.contrast).toBeDefined()
    expect(THEMES.contrast.length).toBeGreaterThanOrEqual(8)
  })

  it('separates the contrast palette by lightness, not only by hue', () => {
    // The point of this palette is that it survives greyscale and colour blindness, so
    // adjacent entries must differ in luminance. A palette of equally-bright hues would
    // pass a "has ten colours" check and fail the users it exists for.
    const lum = (hex: string) => {
      const [r, g, b] = [0, 2, 4].map(i => parseInt(hex.slice(1 + i, 3 + i), 16) / 255)
      return 0.2126 * r + 0.7152 * g + 0.0722 * b
    }
    const spread = THEMES.contrast.map(lum)
    expect(Math.max(...spread) - Math.min(...spread)).toBeGreaterThan(0.8)

    const adjacentDiffs = spread.slice(1).map((v, i) => Math.abs(v - spread[i]))
    expect(Math.min(...adjacentDiffs)).toBeGreaterThan(0.01)
  })
})
