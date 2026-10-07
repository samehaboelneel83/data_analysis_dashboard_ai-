import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { CrossFilterProvider } from '../../components/report/CrossFilterContext'
import { EditToolbar, EmptyResultNote, GroupBox, HeavyPageBanner, HEAVY_PAGE, SelectionGuides } from './CanvasOverlays'

/** Redesign 7e4: the builder canvas's overlays. */

describe('canvas overlays (7e4)', () => {
  it('guides say where the selected widget sits and how many edges it shares', () => {
    render(<SelectionGuides layout={{ x: 0, y: 7, w: 6, h: 5 }} containerW={1200}
      others={[{ x: 0, y: 0, w: 3, h: 3 }, { x: 6, y: 7, w: 6, h: 5 }, { x: 8, y: 20, w: 2, h: 2 }]} />)
    expect(screen.getByTestId('selection-guides')).toHaveTextContent('col 1–6 · row 8 · aligned ×2')
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
