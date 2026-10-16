/**
 * UAT-6: after "Reset filters" a slicer stayed highlighted on its old value.
 *
 * The slicer kept its ticks in local state that nothing outside it ever
 * updated: Reset cleared the page's filters (the filter bar and the numbers
 * followed) while "Europe" stayed pressed -- and the next click re-emitted
 * Europe with the new value. The ticks now mirror the slicer's own active
 * filter.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import WidgetRenderer from './WidgetRenderer'
import { CrossFilterProvider, useCrossFilter } from './CrossFilterContext'
import { widgetDataApi } from '../../services/api'
import type { Widget } from '../../types/report'

vi.mock('../../services/api', () => ({
  pinsApi: { create: vi.fn(), list: vi.fn().mockResolvedValue([]), remove: vi.fn() },
  widgetDataApi: { query: vi.fn(), export: vi.fn() },
  boundarySetsApi: { list: vi.fn().mockResolvedValue([]), get: vi.fn(), create: vi.fn(), remove: vi.fn() },
}))

const slicer = (slicer_mode: string): Widget => ({
  id: 9, page_id: 100, widget_type: 'slicer', title: 'Region', config: { dimension: 'region', slicer_mode },
  layout: { x: 0, y: 0, w: 4, h: 3 }, created_at: '2026-01-01',
} as Widget)

function Controls() {
  const { activeFilters, clearAllFilters } = useCrossFilter()
  return (<>
    <button type="button" onClick={clearAllFilters}>Reset filters</button>
    <div data-testid="filters">{JSON.stringify(activeFilters.map(f => f.value))}</div>
  </>)
}

function renderSlicer(mode: string) {
  vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [{ name: 'Europe' }, { name: 'Asia' }, { name: 'Africa' }], sampled: false } as never)
  render(<CrossFilterProvider><WidgetRenderer widget={slicer(mode)} datasetId={10} /><Controls /></CrossFilterProvider>)
}

afterEach(() => vi.clearAllMocks())

describe('a slicer after Reset filters', () => {
  it('buttons: Europe is no longer pressed once the filters are reset', async () => {
    renderSlicer('buttons')
    const europe = await screen.findByRole('button', { name: 'Europe' })
    fireEvent.click(europe)
    expect(europe).toHaveAttribute('aria-pressed', 'true')
    act(() => { fireEvent.click(screen.getByRole('button', { name: 'Reset filters' })) })
    expect(screen.getByTestId('filters').textContent).toBe('[]')
    expect(screen.getByRole('button', { name: 'Europe' })).toHaveAttribute('aria-pressed', 'false')
  })

  it('the next pick after a reset filters on that value alone', async () => {
    renderSlicer('buttons')
    fireEvent.click(await screen.findByRole('button', { name: 'Europe' }))
    act(() => { fireEvent.click(screen.getByRole('button', { name: 'Reset filters' })) })
    fireEvent.click(screen.getByRole('button', { name: 'Asia' }))
    expect(screen.getByTestId('filters').textContent).toBe(JSON.stringify([['Asia']]))
    expect(screen.getByRole('button', { name: 'Europe' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('button', { name: 'Asia' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('list: the checkbox is unticked by a reset', async () => {
    renderSlicer('list')
    const box = await screen.findByRole('checkbox', { name: /Europe/ })
    fireEvent.click(box)
    expect(box).toBeChecked()
    act(() => { fireEvent.click(screen.getByRole('button', { name: 'Reset filters' })) })
    expect(screen.getByRole('checkbox', { name: /Europe/ })).not.toBeChecked()
  })
})
