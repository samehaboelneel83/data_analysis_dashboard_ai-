import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import GeoContourRenderer from './GeoContourRenderer'

const base = { rows: [], cfg: {}, rtl: false, broadcasts: false, localSelected: null, onClickPoint: () => {}, plotW: 400, plotH: 300 }

describe('GeoContourRenderer', () => {
  it('shades the surface, draws isolines and states the population', () => {
    const nx = 5, ny = 5
    const values = Array.from({ length: nx * ny }, (_, i) => {
      const x = i % nx, y = Math.floor(i / nx)
      return Math.max(0, 1 - (Math.abs(x - 2) + Math.abs(y - 2)) / 3)
    })
    const { container } = render(<GeoContourRenderer {...base} data={{ type: 'geo_contour', points_used: 480, dropped: 20,
      grid: { west: 29, east: 33, south: 28, north: 32, nx, ny, values }, levels: [0.25, 0.7] }} />)
    expect(container.querySelectorAll('[data-testid=contour-surface] path').length).toBeGreaterThan(0)
    expect(container.querySelectorAll('[data-testid=contour-lines] path')).toHaveLength(2)
    expect(screen.getByText(/480 located rows · 20 without usable coordinates/)).toBeTruthy()
  })

  it('says why there is no surface', () => {
    render(<GeoContourRenderer {...base} data={{ type: 'geo_contour', grid: null, reason: 'A density surface needs at least 3 located rows; 1 have usable coordinates.' }} />)
    expect(screen.getByRole('note').textContent).toContain('at least 3')
  })
})
