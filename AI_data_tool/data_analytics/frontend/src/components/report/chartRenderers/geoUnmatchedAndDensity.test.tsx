import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { GeoPiesRenderer, GeoDensityRenderer } from './GeoPieLayerRenderer'

/**
 * Two more ways a map could show nothing without saying so.
 *
 * The pie map matches each row to a COUNTRY. Given Egyptian governorates it
 * matched none of them and drew a bare world map — no pies, no message, no clue
 * that "Cairo" is not a country as far as this widget is concerned. The
 * choropleth beside it already reports the same situation ("27 rows did not
 * match a country"), and says in its own comment why: a hole in the map should
 * read as rows that didn't match, not as zero.
 *
 * The density map had the framing bug the other maps had — it computed its grid
 * cells after fitting the projection, so it could never be fitted to them.
 */
const base = { cfg: {}, rtl: false, broadcasts: false, localSelected: null,
               onClickPoint: () => {}, rows: [] as any[], plotW: 960, plotH: 540 }

describe('the pie map says when it matched nothing', () => {
  const GOVERNORATES = {
    rows: [{ name: 'Cairo', total: 10, slices: [{ label: 'Surgery', value: 10 }] },
           { name: 'Giza',  total: 5,  slices: [{ label: 'Surgery', value: 5 }] }],
  }

  it('reports the rows it could not place', () => {
    render(<GeoPiesRenderer {...base} data={GOVERNORATES} />)
    expect(screen.getByTestId('geo-unmatched').textContent)
      .toContain('2 rows did not match a country')
  })

  it('says nothing when every row matched', () => {
    render(<GeoPiesRenderer {...base} data={{
      rows: [{ name: 'Egypt', total: 10, slices: [{ label: 'Surgery', value: 10 }] }] }} />)
    expect(screen.queryByTestId('geo-unmatched')).not.toBeInTheDocument()
  })

  it('uses the singular for one row', () => {
    render(<GeoPiesRenderer {...base} data={{
      rows: [{ name: 'Cairo', total: 1, slices: [{ label: 'A', value: 1 }] }] }} />)
    expect(screen.getByTestId('geo-unmatched').textContent)
      .toContain('1 row did not match a country')
  })
})

describe('the density map frames its own cells', () => {
  // Cells clustered over Egypt. Fitted, they must span a real part of the
  // drawing; fitted to the world they occupy a few pixels.
  const CELLS = [{ lat: 30.05, lon: 31.24, count: 40 }, { lat: 31.2, lon: 29.92, count: 12 },
                 { lat: 24.09, lon: 32.9, count: 7 }]

  function spanOfRects(container: HTMLElement) {
    const rects = [...container.querySelectorAll('rect')]
      .map(r => Number(r.getAttribute('x')))
      .filter(Number.isFinite)
    return rects.length ? Math.max(...rects) - Math.min(...rects) : 0
  }

  it('spreads its cells across the drawing', () => {
    const { container } = render(
      <GeoDensityRenderer {...base} rows={CELLS} data={{ cell_degrees: 1 }} />)
    // 960 wide viewBox; a world fit puts all three inside ~20px.
    expect(spanOfRects(container)).toBeGreaterThan(100)
  })

  it('draws one cell per row', () => {
    const { container } = render(
      <GeoDensityRenderer {...base} rows={CELLS} data={{ cell_degrees: 1 }} />)
    expect(container.querySelectorAll('rect').length).toBe(CELLS.length)
  })
})
