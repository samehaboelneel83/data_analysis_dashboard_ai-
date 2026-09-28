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
    expect(h).toBeGreaterThanOrEqual(12)
  })

  it('moves the figures to the tooltip when rows are too thin to hold them', () => {
    const { container } = draw(grid, 300)
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
