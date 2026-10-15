import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import BoxPlotRenderer from './BoxPlotRenderer'

describe('box plot value axis (5.12)', () => {
  it('draws readable, compact tick labels in a gutter beside the plot', () => {
    const props = { data: { rows: [
      { name: 'Engineer', min: 38735.12, q1: 50000, median: 59000, q3: 70000, max: 120000, outliers: [] },
      { name: 'Staff', min: 40000, q1: 52000, median: 61000, q3: 72000, max: 158220, outliers: [] }] },
      rows: [], rtl: false, cfg: {} } as unknown as Parameters<typeof BoxPlotRenderer>[0]
    render(<BoxPlotRenderer {...props} />)
    const ticks = screen.getByTestId('boxplot-ticks').textContent
    expect(ticks).toContain('38.74K')
    expect(ticks).toContain('158.22K')
    expect(ticks).not.toContain('38,735.12')
  })
})

/** C-16: the category names were SVG <text> inside a viewBox stretched with
 *  preserveAspectRatio="none", so they were squashed to ~4px glyphs. */
const rows = ['Europe', 'Asia', 'Americas', 'Africa'].map((name, i) => ({
  name, min: 1 + i, q1: 2 + i, median: 3 + i, q3: 4 + i, max: 5 + i, outliers: [] }))
const base = { rows: [], cfg: {}, rtl: false, broadcasts: false, localSelected: null, onClickPoint: () => {} } as any

describe('BoxPlotRenderer category labels (C-16)', () => {
  it('are HTML text at a readable size, not stretched SVG text', () => {
    const { container, getByText } = render(<BoxPlotRenderer {...base} data={{ rows }} />)
    expect(container.querySelectorAll('svg text')).toHaveLength(0)
    for (const r of rows) {
      const el = getByText(r.name)
      expect(el.closest('svg')).toBeNull()
      expect(parseFloat(el.style.fontSize)).toBeGreaterThanOrEqual(10)
      expect(el.getAttribute('title')).toBe(r.name)
    }
  })
})

describe('BoxPlotRenderer crowded category labels (C-16 round 2)', () => {
  const many = (n: number, prefix = 'Department ') => Array.from({ length: n }, (_, i) => ({
    name: `${prefix}${i + 1}`, min: 1, q1: 2, median: 3, q3: 4, max: 5, outliers: [] }))
  it('labels that fit their slot stay level', () => {
    const { getByTestId } = render(<BoxPlotRenderer {...base} data={{ rows }} plotW={800} plotH={300} />)
    expect(getByTestId('boxplot-categories').getAttribute('data-layout')).toBe('level')
  })
  it('labels wider than their slot are rotated, with room made under the plot', () => {
    const { getByTestId, getByText } = render(<BoxPlotRenderer {...base} data={{ rows: many(8) }} plotW={600} plotH={300} />)
    const strip = getByTestId('boxplot-categories')
    expect(strip.getAttribute('data-layout')).toBe('rotated')
    expect(getByText('Department 1').style.transform).toMatch(/rotate\(-\d+deg\)/)
  })
  it('too many to show even rotated: every k-th is shown, the rest keep their name on the box tooltip', () => {
    const { getByTestId } = render(<BoxPlotRenderer {...base} data={{ rows: many(60, 'D') }} plotW={400} plotH={300} />)
    const shown = getByTestId('boxplot-categories').querySelectorAll('span')
    expect(shown.length).toBeGreaterThan(0)
    expect(shown.length).toBeLessThan(60)
    expect(shown[0].textContent).toBe('D1')
  })
})
