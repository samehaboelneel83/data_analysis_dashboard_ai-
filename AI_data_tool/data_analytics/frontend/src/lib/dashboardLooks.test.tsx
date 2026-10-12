import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { LOOKS, lookOf } from './dashboardLooks'
import { styleVars, tidyStyle } from './dashboardStyle'
import { THEMES } from '../components/report/themes'
import DashboardStylePanel from '../components/report/DashboardStylePanel'
import { en } from '../i18n/en'
import { ar } from '../i18n/ar'

vi.mock('./dashboardFonts', () => ({ ensureFont: () => {} }))

describe('ready-made dashboard looks', () => {
  it('each is a complete style with a palette the charts know, named in both languages', () => {
    expect(LOOKS.length).toBeGreaterThanOrEqual(5)
    for (const l of LOOKS) {
      expect(THEMES[l.style.palette as string], l.key).toBeTruthy()
      expect(l.style.mode === 'dark' || l.style.mode === 'light').toBe(true)
      const vars = styleVars(l.style) as Record<string, string>
      expect(vars['--dl-s-card-bg']).toBe(l.style.card_background)
      expect(vars['--dl-s-radius']).toBe(`${l.style.radius}px`)
      for (const cat of [en, ar] as Record<string, string>[]) {
        expect(cat[`tpl.style.look.${l.key}`], l.key).toBeTruthy()
        expect(cat[`tpl.style.look.${l.key}.help`], l.key).toBeTruthy()
      }
    }
  })

  it('a dark look keeps its text readable on its cards', () => {
    const lum = (hex: string) => {
      const [r, g, b] = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255).map(v => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4))
      return 0.2126 * r + 0.7152 * g + 0.0722 * b
    }
    for (const l of LOOKS.filter(x => x.style.mode === 'dark')) {
      const [a, b] = [lum(l.style.text_color as string), lum(l.style.card_background as string)]
      expect((Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05), l.key).toBeGreaterThan(7)
    }
  })

  it('the panel applies a look in one click and marks the one in use until something is changed', () => {
    const onChange = vi.fn()
    const { rerender } = render(<DashboardStylePanel style={{}} onChange={onChange} />)
    fireEvent.click(screen.getByTestId('look-midnight'))
    const applied = onChange.mock.calls[0][0]
    expect(applied).toEqual(tidyStyle({ ...LOOKS[0].style }))
    expect(lookOf(applied)).toBe('midnight')
    rerender(<DashboardStylePanel style={applied} onChange={onChange} />)
    expect(screen.getByTestId('look-midnight').getAttribute('aria-pressed')).toBe('true')
    expect(lookOf({ ...applied, radius: 3 })).toBeUndefined()
  })
})
