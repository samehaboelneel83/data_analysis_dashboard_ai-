/**
 * The filters, reachable from anywhere on a long page.
 *
 * `FilterBar` sits at the top of the canvas, which is fine until the page is
 * taller than the screen: scroll down and the one place that says what is
 * filtering — and the only way to clear it without finding the widget that set
 * it — has scrolled away with it. On a dashboard of twenty tiles that is most
 * of the time.
 *
 * So this is a small window pinned to the VIEWPORT rather than the document,
 * draggable out of the way, and present only while something is actually
 * filtering: a permanent floating box on a page with no filters is clutter
 * that teaches a reader to ignore it.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import FloatingFilterWindow from './FloatingFilterWindow'
import { CrossFilterProvider, useCrossFilter } from './CrossFilterContext'

/** Emits filters the way a widget does, then mounts the window beside them. */
function Harness({ emit }: { emit?: { column: string; value: unknown; label: string }[] }) {
  const { emitFilter } = useCrossFilter()
  return (
    <>
      <button onClick={() => (emit ?? []).forEach((f, i) =>
        emitFilter(i + 1, 100, f.column, f.value, f.label))}>emit</button>
      <FloatingFilterWindow />
    </>
  )
}

const mount = (emit?: { column: string; value: unknown; label: string }[]) => render(
  <CrossFilterProvider>
    <Harness emit={emit} />
  </CrossFilterProvider>
)

const ONE = [{ column: 'region', value: 'North', label: 'region = North' }]
const TWO = [...ONE, { column: 'year', value: 2026, label: 'year = 2026' }]

describe('FloatingFilterWindow', () => {
  it('stays out of the way when nothing is filtering', () => {
    mount()
    expect(screen.queryByRole('button', { name: /filters/i })).not.toBeInTheDocument()
  })

  it('appears with a count once something is', () => {
    mount(TWO)
    fireEvent.click(screen.getByRole('button', { name: 'emit' }))
    expect(screen.getByRole('button', { name: /2 filters/i })).toBeInTheDocument()
  })

  it('is pinned to the viewport, so scrolling cannot take it away', () => {
    // The whole reason it exists. `position: fixed` is the behaviour under
    // test, not a style detail: `absolute` would scroll away with the canvas
    // exactly as the strip does.
    mount(ONE)
    fireEvent.click(screen.getByRole('button', { name: 'emit' }))
    const win = screen.getByTestId('floating-filters')
    expect(win.style.position).toBe('fixed')
  })

  it('opens to name each filter', () => {
    mount(TWO)
    fireEvent.click(screen.getByRole('button', { name: 'emit' }))
    fireEvent.click(screen.getByRole('button', { name: /2 filters/i }))

    expect(screen.getByText('region = North')).toBeInTheDocument()
    expect(screen.getByText('year = 2026')).toBeInTheDocument()
  })

  it('clears one filter from its own row', () => {
    mount(TWO)
    fireEvent.click(screen.getByRole('button', { name: 'emit' }))
    fireEvent.click(screen.getByRole('button', { name: /2 filters/i }))
    fireEvent.click(screen.getByRole('button', { name: /remove filter region = North/i }))

    expect(screen.queryByText('region = North')).not.toBeInTheDocument()
    expect(screen.getByText('year = 2026')).toBeInTheDocument()
  })

  it('clears everything at once', () => {
    mount(TWO)
    fireEvent.click(screen.getByRole('button', { name: 'emit' }))
    fireEvent.click(screen.getByRole('button', { name: /2 filters/i }))
    fireEvent.click(screen.getByRole('button', { name: /clear all/i }))

    // Nothing filtering means the window goes too, rather than sitting there
    // empty.
    expect(screen.queryByRole('button', { name: /filters/i })).not.toBeInTheDocument()
  })

  it('can be dragged off whatever it is covering', () => {
    mount(ONE)
    fireEvent.click(screen.getByRole('button', { name: 'emit' }))
    // The grip is the open window's header: the collapsed pill is a corner
    // button that is not covering anything worth moving it off.
    fireEvent.click(screen.getByRole('button', { name: /1 filter/i }))
    const win = screen.getByTestId('floating-filters')
    const before = win.style.insetInlineEnd || win.style.right

    fireEvent.mouseDown(screen.getByTestId('floating-filters-grip'), { clientX: 500, clientY: 500 })
    fireEvent.mouseMove(window, { clientX: 400, clientY: 300 })
    fireEvent.mouseUp(window)

    expect(win.style.right || win.style.insetInlineEnd).not.toBe(before)
  })

  it('closes back to the pill without clearing anything', () => {
    // Dismissing the window is not dismissing the filters — they are still
    // narrowing every number on the page.
    mount(ONE)
    fireEvent.click(screen.getByRole('button', { name: 'emit' }))
    fireEvent.click(screen.getByRole('button', { name: /1 filter/i }))
    fireEvent.click(screen.getByRole('button', { name: /collapse/i }))

    expect(screen.queryByText('region = North')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /1 filter/i })).toBeInTheDocument()
  })
})
