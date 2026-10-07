import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { CrossFilterProvider } from '../../components/report/CrossFilterContext'
import { EditToolbar, EmptyResultNote, GroupBox, HeavyPageBanner, HEAVY_PAGE, SelectionGuides } from './CanvasOverlays'

/** Redesign 7e4: the builder canvas's overlays. */

describe('canvas overlays (7e4)', () => {
  it('guides say where the selected widget sits and how many edges it shares', () => {
    render(<SelectionGuides layout={{ x: 0, y: 7, w: 6, h: 5 }} containerW={1200}
      others={[{ x: 0, y: 0, w: 3, h: 3 }, { x: 6, y: 7, w: 6, h: 5 }, { x: 8, y: 20, w: 2, h: 2 }]} />)
    expect(screen.getByTestId('selection-guides')).toHaveTextContent('col 1–6 · row 8–12 · aligned ×2')
  })

  it('QA3 B2: the tag sits in the gutter under the widget, inside the canvas; ranges are isolated left-to-right', () => {
    const { container } = render(<SelectionGuides layout={{ x: 0, y: 0, w: 6, h: 2 }} containerW={1200} canvasH={8 * 66}
      others={[{ x: 0, y: 2, w: 6, h: 3 }]} />)
    const tag = container.querySelector('.dl-bd-coord') as HTMLElement
    // just under the widget (2 rows × 66 − gap), not inside it over its own controls
    expect(parseFloat(tag.style.top)).toBeGreaterThanOrEqual(2 * 66 - 8)
    expect(tag.querySelectorAll('bdi[dir="ltr"]')).toHaveLength(2)
    expect(tag.querySelector('bdi')!.textContent).toBe('1–6')
  })

  it('QA3 B2: at the canvas bottom it goes above the widget, never off the canvas', () => {
    const { container } = render(<SelectionGuides layout={{ x: 0, y: 5, w: 6, h: 3 }} containerW={1200} canvasH={8 * 66} others={[]} />)
    const top = parseFloat((container.querySelector('.dl-bd-coord') as HTMLElement).style.top)
    expect(top + 16).toBeLessThanOrEqual(8 * 66)
    expect(top).toBeLessThan(5 * 66)
  })

  it('QA3 B2: one-row and one-column spans read as one number', () => {
    render(<SelectionGuides layout={{ x: 2, y: 0, w: 1, h: 1 }} containerW={1200} others={[]} />)
    expect(screen.getByTestId('selection-guides')).toHaveTextContent('col 3 · row 1')
  })

  it('the group box counts the selection and lays it out', () => {
    const left = vi.fn(), top = vi.fn(), spread = vi.fn()
    render(<GroupBox containerW={1200} layouts={[{ x: 0, y: 0, w: 3, h: 3 }, { x: 3, y: 0, w: 3, h: 3 }, { x: 6, y: 1, w: 3, h: 3 }]}
      onAlignLeft={left} onAlignTop={top} onDistribute={spread} />)
    expect(screen.getByRole('toolbar')).toHaveTextContent('3 selected')
    fireEvent.click(screen.getByRole('button', { name: 'Line up left edges' }))
    fireEvent.click(screen.getByRole('button', { name: 'Line up top edges' }))
    fireEvent.click(screen.getByRole('button', { name: 'Even out the spacing' }))
    expect(left).toHaveBeenCalled(); expect(top).toHaveBeenCalled(); expect(spread).toHaveBeenCalled()
  })

  it('the edit toolbar duplicates, assigns data and opens filters', () => {
    const dup = vi.fn(), data = vi.fn(), filt = vi.fn()
    render(<EditToolbar title="Revenue" onDuplicate={dup} onAssign={data} onFilters={filt} />)
    fireEvent.click(screen.getByRole('button', { name: 'Duplicate Revenue' }))
    fireEvent.click(screen.getByRole('button', { name: 'Assign data to Revenue' }))
    fireEvent.click(screen.getByRole('button', { name: 'Filters of Revenue' }))
    expect(dup).toHaveBeenCalled(); expect(data).toHaveBeenCalled(); expect(filt).toHaveBeenCalled()
  })

  it('an empty result under page filters offers to clear them; with data, or no filters, it says nothing', () => {
    const clear = vi.fn()
    const { rerender } = render(<CrossFilterProvider><EmptyResultNote rowCount={0} pageFiltered onClearPage={clear} /></CrossFilterProvider>)
    expect(screen.getByRole('status')).toHaveTextContent('No rows match these filters')
    fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect(clear).toHaveBeenCalled()
    rerender(<CrossFilterProvider><EmptyResultNote rowCount={4} pageFiltered onClearPage={clear} /></CrossFilterProvider>)
    expect(screen.queryByRole('status')).toBeNull()
    rerender(<CrossFilterProvider><EmptyResultNote rowCount={0} pageFiltered={false} onClearPage={clear} /></CrossFilterProvider>)
    expect(screen.queryByRole('status')).toBeNull()
  })

  it('a heavy page says so past the Review threshold, and opens Performance', () => {
    const perf = vi.fn()
    const { rerender } = render(<HeavyPageBanner n={HEAVY_PAGE} onPerformance={perf} />)
    expect(screen.queryByRole('note')).toBeNull()
    rerender(<HeavyPageBanner n={26} onPerformance={perf} />)
    expect(screen.getByRole('note')).toHaveTextContent('This page has 26 widgets that all query on load')
    fireEvent.click(screen.getByRole('button', { name: 'Performance' }))
    expect(perf).toHaveBeenCalled()
  })
})

describe('the col · row tag at the canvas edge (QA4 V4)', () => {
  it('a widget ending at the bottom of the canvas gets its tag above it, inside the canvas', () => {
    const props = (proto: object, k: string) => Object.getOwnPropertyDescriptor(proto, k)!
    const real = { ow: props(HTMLElement.prototype, 'offsetWidth'), oh: props(HTMLElement.prototype, 'offsetHeight'),
      cw: props(Element.prototype, 'clientWidth'), ch: props(Element.prototype, 'clientHeight') }
    Object.defineProperty(HTMLElement.prototype, 'offsetWidth', { configurable: true, get: () => 160 })
    Object.defineProperty(HTMLElement.prototype, 'offsetHeight', { configurable: true, get: () => 16 })
    Object.defineProperty(Element.prototype, 'clientWidth', { configurable: true, get: () => 1200 })
    // the canvas is only as tall as the widget's bottom edge (5 rows)
    Object.defineProperty(Element.prototype, 'clientHeight', { configurable: true, get: () => 5 * 66 - 8 })
    try {
      const { container } = render(<SelectionGuides layout={{ x: 0, y: 2, w: 6, h: 3 }} containerW={1200} others={[]} />)
      const tag = container.querySelector('.dl-bd-coord') as HTMLElement
      const top = parseFloat(tag.style.top)
      expect(top + 16).toBeLessThanOrEqual(5 * 66 - 8)
      expect(top).toBeLessThan(2 * 66)
    } finally {
      Object.defineProperty(HTMLElement.prototype, 'offsetWidth', real.ow)
      Object.defineProperty(HTMLElement.prototype, 'offsetHeight', real.oh)
      Object.defineProperty(Element.prototype, 'clientWidth', real.cw)
      Object.defineProperty(Element.prototype, 'clientHeight', real.ch)
    }
  })
})
