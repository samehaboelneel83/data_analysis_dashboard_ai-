import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import HeatMapRenderer from './HeatMapRenderer'

const HOURS = Array.from({ length: 24 }, (_, h) => String(h).padStart(2, '0'))
const grid = {
  type: 'heatmap', rows_axis: HOURS, cols_axis: ['INC', 'OUT'],
  cells: HOURS.map((_, h) => [h % 3, h * 2]), min: 0, max: 46, total: 3576,
}

const draw = (data: unknown, plotH?: number) => render(
  <HeatMapRenderer rows={[]} data={data as any} cfg={{}} rtl={false} broadcasts={false}
    localSelected={null} onClickPoint={() => {}} plotW={500} plotH={plotH} />)

describe('a heatmap of the day', () => {
  // Live QA 2026-09-28: 7 of 24 hours were visible, the rest behind a scrollbar.
  it('shares the tile height between its rows', () => {
    const { container } = draw(grid, 500)
    const cell = container.querySelector('tbody td div') as HTMLElement
    const h = parseInt(cell.style.height)
    expect(h * 24).toBeLessThanOrEqual(500)
    expect(h).toBeGreaterThanOrEqual(14)
  })

  it('moves the figures to the tooltip when rows are too thin to hold them', () => {
    const { container } = draw(grid, 360)
    const cells = [...container.querySelectorAll('tbody td[title]')]
    expect(cells[1].textContent).toBe('')
    expect(cells[1].getAttribute('title')).toMatch(/00 × OUT: 0/)
  })

  it('keeps its figures with room to spare', () => {
    const { container } = draw(grid, 1000)
    expect(container.querySelectorAll('tbody td[title]')[3].textContent).toBe('2')
  })

  it('says "no data" for an emptied result, and "configure" only when nothing ran', () => {
    draw({ type: 'empty', rows: [], total: 0 })
    expect(screen.getByText('No data for the current selection')).toBeInTheDocument()
    draw(null)
    expect(screen.getByText('Configure widget to see data')).toBeInTheDocument()
  })
})

describe('a grid of differences', () => {
  // server: widget_data.shape_heatmap with `difference_of`
  it('colours by sign around zero and shows the sign of a surplus', () => {
    const { container } = draw({ type: 'heatmap', diverging: true, rows_axis: ['a', 'b'], cols_axis: ['2024-01', '2024-02'],
      cells: [[12, -13], [0, null]], min: -13, max: 12, total: 4 }, 300)
    const cells = [...container.querySelectorAll('tbody td div')] as HTMLElement[]
    expect(cells[0].style.background).toContain('--ok')
    expect(cells[1].style.background).toContain('--danger')
    expect(cells[0].textContent).toBe('+12')
    expect(cells[1].textContent).toContain('13')
    expect(cells[3].textContent).toBe('—')
  })
})
