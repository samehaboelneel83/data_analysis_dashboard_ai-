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
