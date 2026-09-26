/**
 * E15: a map says what it shows to someone who cannot see it, and a keyboard
 * reaches the places a mouse can click.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import GeoChoroplethRenderer from '../chartRenderers/GeoChoroplethRenderer'
import { GeoPointsRenderer, GeoBubblesRenderer } from '../chartRenderers/GeoPointMapRenderer'
import type { ChartRendererProps } from '../chartRenderers/types'
import { mapSummary } from './MapDataTable'

vi.mock('../../../services/api', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  boundarySetsApi: { list: vi.fn(), get: vi.fn(), create: vi.fn(), remove: vi.fn() },
}))

const base: Omit<ChartRendererProps, 'rows'> = {
  data: {}, cfg: { measure: 'sales', dimension: 'country' } as never, rtl: false,
  broadcasts: false, localSelected: null, onClickPoint: () => {}, plotW: 960, plotH: 540,
}
const ROWS = [{ name: 'US', value: 100 }, { name: 'France', value: 50 }, { name: 'Egypt', value: 5 }]

describe('mapSummary', () => {
  it('names what is plotted, how many places, and the extremes', () => {
    expect(mapSummary('Map of sales', [{ label: 'A', value: 3 }, { label: 'B', value: 9 }]))
      .toBe('Map of sales: 2 places; highest B 9, lowest A 3')
  })
  it('says so when there is nothing to show', () => {
    expect(mapSummary('Map of sales', [])).toBe('Map of sales: no values to show')
  })
  it('does not call one place both highest and lowest', () => {
    expect(mapSummary('Map of sales', [{ label: 'A', value: 3 }])).toBe('Map of sales: 1 place, A 3')
  })
})

describe('a choropleth, read without seeing it', () => {
  it('is an image whose name is the summary when it cannot be clicked', () => {
    render(<GeoChoroplethRenderer {...base} rows={ROWS} />)
    const map = screen.getByRole('img', { name: /Map of sales by country: 3 places/ })
    expect(map.getAttribute('aria-label')).toMatch(/highest United States of America 100, lowest Egypt 5/)
  })

  it('carries its values as a table, largest first', () => {
    render(<GeoChoroplethRenderer {...base} rows={ROWS} />)
    const table = screen.getByTestId('map-data-table')
    const cells = within(table).getAllByRole('rowheader').map(c => c.textContent)
    expect(cells).toEqual(['United States of America', 'France', 'Egypt'])
    expect(within(table).getByText('Map of sales by country')).toBeInTheDocument()
  })

  it('counts rows it could not place in the table caption', () => {
    render(<GeoChoroplethRenderer {...base} rows={[...ROWS, { name: 'Atlantis', value: 1 }]} />)
    expect(screen.getByTestId('map-data-table')).toHaveTextContent('1 row not placed on the map')
  })

  it('lets a keyboard filter by a region, with Enter or Space', () => {
    const onClickPoint = vi.fn()
    render(<GeoChoroplethRenderer {...base} rows={ROWS} broadcasts onClickPoint={onClickPoint} />)
    expect(screen.getByRole('group', { name: /Map of sales/ })).toBeInTheDocument()
    const france = screen.getByRole('button', { name: 'France: 50' })
    expect(france).toHaveAttribute('tabindex', '0')
    fireEvent.keyDown(france, { key: 'Enter' })
    expect(onClickPoint).toHaveBeenCalledWith('France')
    fireEvent.keyDown(screen.getByRole('button', { name: 'Egypt: 5' }), { key: ' ' })
    expect(onClickPoint).toHaveBeenLastCalledWith('Egypt')
    // Only regions with data are stops: the rest of the world is not 170 tabs.
    expect(screen.getAllByRole('button')).toHaveLength(3)
  })

  it('shows the value when a region takes focus, as hover does', () => {
    render(<GeoChoroplethRenderer {...base} rows={ROWS} broadcasts />)
    fireEvent.focus(screen.getByRole('button', { name: 'France: 50' }))
    expect(screen.getAllByText(/France/).length).toBeGreaterThan(1)
  })
})

describe('point and bubble maps, read without seeing them', () => {
  it('a bubble map summarises its values', () => {
    render(<GeoBubblesRenderer {...base} rows={ROWS} />)
    expect(screen.getByRole('img', { name: /Bubble map of sales by country: 3 places; highest/ }))
      .toBeInTheDocument()
    expect(within(screen.getByTestId('map-data-table')).getAllByRole('row')).toHaveLength(4)
  })

  it('a point map without a measure names places, not a value of 1', () => {
    render(<GeoPointsRenderer {...base} cfg={{} as never}
      rows={[{ lat: 48.85, lon: 2.35, name: 'Paris' }, { lat: 30.04, lon: 31.24, name: 'Cairo' }]} />)
    const map = screen.getByRole('img', { name: 'Point map: 2 places' })
    expect(map.getAttribute('aria-label')).not.toMatch(/highest/)
    expect(screen.getByTestId('map-data-table')).toHaveTextContent('Paris')
  })

  it('lets a keyboard filter by a marker', () => {
    const onClickPoint = vi.fn()
    render(<GeoPointsRenderer {...base} rows={ROWS} broadcasts onClickPoint={onClickPoint} />)
    fireEvent.keyDown(screen.getByRole('button', { name: 'France: 50' }), { key: 'Enter' })
    expect(onClickPoint).toHaveBeenCalledWith('France')
  })
})
