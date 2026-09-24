import { describe, it, expect } from 'vitest'
import { fitFontSize } from './WidgetBody'

/**
 * A KPI value is centred inside its tile, so a number wider than the tile
 * overflows on BOTH sides and the widget's clipping removes the LEADING
 * characters: "$8,632,597" was rendering as ",632,597" on a default-width card.
 * A number that has quietly lost its most significant digits is worse than one
 * that is obviously cut, so the size steps down with length (and the call site
 * ellipsises the tail for whatever is still too long).
 */
describe('fitFontSize', () => {
  it('leaves a short value at full size', () => {
    expect(fitFontSize('402,108', 36)).toBe(36)
  })

  it('steps a long currency value down', () => {
    // The BUILD-03 value.
    expect(fitFontSize('$8,632,597', 36)).toBeLessThan(36)
  })

  it('never returns a smaller size for a shorter value', () => {
    const samples = ['1', '1,000', '$8,632,597', '$8,632,597.00', '1,234,567,890,123']
    const sizes = samples.map(s => fitFontSize(s, 36))
    for (let i = 1; i < sizes.length; i++) expect(sizes[i]).toBeLessThanOrEqual(sizes[i - 1])
  })

  it('stays legible however long the value is', () => {
    expect(fitFontSize('x'.repeat(200), 36)).toBeGreaterThanOrEqual(12)
  })
})
