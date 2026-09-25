import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { COLORS, applyTheme, fmtStr, formatValue, getFillFactory } from './chartUtils'
import { THEMES } from './themes'

describe('applyTheme', () => {
  it('mutates the shared COLORS array in place so existing imports see the update', () => {
    applyTheme('ocean')
    expect(COLORS).toEqual(THEMES.ocean)
    applyTheme('default')
    expect(COLORS).toEqual(THEMES.default)
  })

  it('falls back to the default theme for an unknown name', () => {
    applyTheme('not-a-real-theme')
    expect(COLORS).toEqual(THEMES.default)
  })
})

describe('colorscale format', () => {
  it('renders a cell whose background is the low color at the minimum and the high color at the maximum', () => {
    const fmt = { type: 'colorscale' as const, min: 0, max: 100, scaleMinColor: '#ff0000', scaleMaxColor: '#00ff00' }
    const { container: lowContainer } = render(formatValue(0, fmt))
    const { container: highContainer } = render(formatValue(100, fmt))
    expect((lowContainer.firstElementChild as HTMLElement).style.backgroundColor).toBe('rgb(255, 0, 0)')
    expect((highContainer.firstElementChild as HTMLElement).style.backgroundColor).toBe('rgb(0, 255, 0)')
  })

  it('shows the em-dash for a non-numeric value', () => {
    render(formatValue('n/a', { type: 'colorscale' }))
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('formats as a non-dash string for a valid number and a dash for an invalid one, via fmtStr', () => {
    expect(fmtStr(42, { type: 'colorscale', decimals: 0 })).not.toBe('—')
    expect(fmtStr('n/a', { type: 'colorscale' })).toBe('—')
  })
})

describe('icon format', () => {
  it('shows a red/yellow/green icon based on the configured thresholds', () => {
    const fmt = { type: 'icon' as const, thresholds: [33, 66] as [number, number] }
    render(formatValue(10, fmt))
    expect(screen.getByText(/🔴/)).toBeInTheDocument()
  })

  it('formats as a non-dash string for a valid number and a dash for an invalid one, via fmtStr', () => {
    expect(fmtStr(42, { type: 'icon', decimals: 0 })).not.toBe('—')
    expect(fmtStr('n/a', { type: 'icon' })).toBe('—')
  })
})

describe('getFillFactory with rule styles', () => {
  it('uses the rule fill instead of the palette colour', () => {
    const getFill = getFillFactory(false, null, [{ fill: '#f87171' }, null])

    expect(getFill('US', 0).fill).toBe('#f87171')
  })

  it('falls back to the palette where no rule matched', () => {
    const getFill = getFillFactory(false, null, [{ fill: '#f87171' }, null])
    const plain = getFillFactory(false, null)

    expect(getFill('CA', 1).fill).toBe(plain('CA', 1).fill)
  })

  it('keeps cross-filter dimming on top of a rule fill', () => {
    const getFill = getFillFactory(true, 'US', [{ fill: '#f87171' }, null])

    // index 0 carries the rule fill; 'CA' is not the selected value, so it must
    // dim — but the rule's fill must survive the dimming, not be swapped out.
    const dimmed = getFill('CA', 0)
    expect(dimmed.fill).toBe('#f87171')
    expect(dimmed.opacity).toBeLessThan(1)
  })
})

describe('formatValue on unformatted numbers', () => {
  it('does not leak binary floating-point error into the UI', () => {
    // Real values from a table totals row over exact inputs: summing 1200.50, 800.00,
    // 450.75, -120.00, 990.25, 310.10, 1500.00, 75.50, 640.00, 220.80 produced
    // 6067.900000000001, and the margin column produced 0.8800000000000001. Both were
    // rendered verbatim in the app.
    expect(formatValue(6067.900000000001)).toBe('6067.9')
    expect(formatValue(0.8800000000000001)).toBe('0.88')
    expect(formatValue(0.1 + 0.2)).toBe('0.3')
  })

  it('leaves genuine decimals and integers exactly as they were', () => {
    expect(formatValue(1200.5)).toBe('1200.5')
    expect(formatValue(-120)).toBe('-120')
    expect(formatValue(0)).toBe('0')
    // Large integers must not be re-precisioned -- that would corrupt ids.
    expect(formatValue(123456789012345)).toBe('123456789012345')
  })

  it('still passes non-numbers and nullish values through unchanged', () => {
    expect(formatValue('US')).toBe('US')
    expect(formatValue(null)).toBe('—')
    expect(formatValue(undefined)).toBe('—')
    expect(formatValue(NaN)).toBe('NaN')
  })
})

describe('value labels survive a right-to-left chart', () => {
  // The bug from the Arabic dashboard: "$ 2,000,000" rendered as "2,000,000 $"
  // on the value axis, because a Latin symbol + Latin digits is one bidi run
  // that an RTL context reorders.
  const LRI = '⁦'
  const PDI = '⁩'

  it('wraps a currency label in a directional isolate', () => {
    const out = fmtStr(2000000, { type: 'currency', symbol: '$', decimals: 0 } as never)
    expect(out.startsWith(LRI)).toBe(true)
    expect(out.endsWith(PDI)).toBe(true)
    // The symbol still PRECEDES the digits inside the isolate.
    expect(out.slice(1, -1)).toBe(`$ ${(2000000).toLocaleString(undefined, {
      minimumFractionDigits: 0, maximumFractionDigits: 0 })}`)
  })

  it('wraps a percent label too', () => {
    const out = fmtStr(12.5, { type: 'percent', decimals: 1 } as never)
    expect(out).toBe(`${LRI}12.5%${PDI}`)
  })

  it('leaves a plain number alone -- digits need no isolate', () => {
    // Over-applying would put invisible characters into every label and into
    // any test or export that compares them.
    expect(fmtStr(1234, { type: 'number', decimals: 0 } as never)).not.toContain(LRI)
  })

  it('does not isolate the em-dash used for non-numbers', () => {
    expect(fmtStr('abc', { type: 'currency' } as never)).toBe('—')
  })
})

describe('display units', () => {
  /**
   * The axis in a SAS dashboard reads "$1.2" under a title that says "Profit
   * (millions)" — the numbers are divided by a unit and the unit is named once
   * rather than repeated as six zeroes on every tick.
   *
   * This does the same division, and by default names the unit ON the value
   * (`$1.2M`) instead of relying on the reader finding the title: a tooltip, a
   * data label and a table cell all carry the number away from its axis, and a
   * bare "1.2" in any of those is a wrong number rather than a compact one. An
   * author who wants SAS's exact look turns the suffix off and titles the axis
   * themselves.
   *
   * Expected digits come from `toLocaleString` rather than being written out:
   * this environment renders Arabic-Indic digits, and hard-coded "1.2" fails
   * for a reason that has nothing to do with the formatter.
   */
  const dec1 = (n: number) => n.toLocaleString(undefined,
    { minimumFractionDigits: 1, maximumFractionDigits: 1 })

  it('divides by a million and says so', () => {
    const out = fmtStr(1_200_000, { type: 'currency', symbol: '$', decimals: 1, scale: 'millions' })
    expect(out).toContain(dec1(1.2))
    expect(out).toContain('M')
  })

  it('divides by a thousand', () => {
    expect(fmtStr(748_000, { type: 'integer', scale: 'thousands' }))
      .toBe(`${(748).toLocaleString()}K`)
  })

  it('divides by a billion', () => {
    expect(fmtStr(2_500_000_000, { type: 'number', decimals: 1, scale: 'billions' }))
      .toBe(`${dec1(2.5)}B`)
  })

  it('can leave the unit off the value, for an axis that names it in its title', () => {
    expect(fmtStr(1_200_000, { type: 'number', decimals: 1, scale: 'millions', scale_suffix: false }))
      .toBe(dec1(1.2))
  })

  it('auto picks the unit from the size of the number', () => {
    // One setting that reads well across a chart whose values span orders of
    // magnitude, which is the common case for "revenue".
    expect(fmtStr(950, { type: 'integer', scale: 'auto' })).toBe((950).toLocaleString())
    expect(fmtStr(12_400, { type: 'integer', scale: 'auto' })).toBe(`${(12).toLocaleString()}K`)
    expect(fmtStr(3_400_000, { type: 'number', decimals: 1, scale: 'auto' })).toBe(`${dec1(3.4)}M`)
  })

  it('keeps the sign', () => {
    expect(fmtStr(-2_000_000, { type: 'number', decimals: 1, scale: 'millions' }))
      .toBe(`${dec1(-2)}M`)
  })

  it('leaves a value alone when no scale is set', () => {
    // Every existing format must render exactly as it did.
    expect(fmtStr(1_200_000, { type: 'integer' })).toBe((1200000).toLocaleString())
  })

  it('never scales a percentage', () => {
    // A percent is already a small number in its own unit; dividing it by a
    // thousand would produce a silently wrong figure.
    expect(fmtStr(42, { type: 'percent', decimals: 0, scale: 'thousands' })).toContain('42')
  })
})
