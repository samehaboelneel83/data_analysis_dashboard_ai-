/**
 * The page's filter strip.
 *
 * SAS keeps this strip on screen permanently and writes "Filters: No
 * selections" when nothing is filtering. Ours rendered nothing at all when the
 * list was empty, which looks identical to a page that has no filter strip —
 * so a reader could not tell "nothing is filtering" from "this page cannot be
 * filtered", and after clicking a chart they had no fixed place to look to
 * confirm what they had just done.
 *
 * That matters more now than it did: every map widget cross-filters, and a map
 * selection is easy to make by accident.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import FilterBar from './FilterBar'
import { CrossFilterProvider, useCrossFilter } from './CrossFilterContext'

/** Emits one filter as a widget would, then renders the bar beside it. */
function Harness({ emit }: { emit?: { column: string; value: unknown; label: string } }) {
  const { emitFilter } = useCrossFilter()
  return (
    <>
      <button onClick={() => emit && emitFilter(1, 100, emit.column, emit.value, emit.label)}>
        emit
      </button>
      <FilterBar />
    </>
  )
}

function renderBar(emit?: { column: string; value: unknown; label: string }) {
  return render(
    <CrossFilterProvider>
      <Harness emit={emit} />
    </CrossFilterProvider>
  )
}

describe('with nothing filtering', () => {
  it('still says so', () => {
    renderBar()
    expect(screen.getByText(/filters/i)).toBeInTheDocument()
    expect(screen.getByText(/no selections/i)).toBeInTheDocument()
  })

  it('offers no "clear all" there is nothing to clear', () => {
    renderBar()
    expect(screen.queryByRole('button', { name: /clear all/i })).not.toBeInTheDocument()
  })
})

describe('with a filter applied', () => {
  it('names it and drops the empty-state text', () => {
    renderBar({ column: 'region', value: 'North', label: 'region = North' })
    fireEvent.click(screen.getByRole('button', { name: 'emit' }))

    expect(screen.getByText('region = North')).toBeInTheDocument()
    expect(screen.queryByText(/no selections/i)).not.toBeInTheDocument()
  })

  it('clears one filter from its own chip', () => {
    renderBar({ column: 'region', value: 'North', label: 'region = North' })
    fireEvent.click(screen.getByRole('button', { name: 'emit' }))
    fireEvent.click(screen.getByRole('button', { name: /remove filter region = North/i }))

    expect(screen.queryByText('region = North')).not.toBeInTheDocument()
    expect(screen.getByText(/no selections/i)).toBeInTheDocument()
  })

  it('clears everything at once', () => {
    renderBar({ column: 'region', value: 'North', label: 'region = North' })
    fireEvent.click(screen.getByRole('button', { name: 'emit' }))
    fireEvent.click(screen.getByRole('button', { name: /clear all/i }))

    expect(screen.getByText(/no selections/i)).toBeInTheDocument()
  })

  it('gives each chip a named control rather than a bare ×', () => {
    // A row of unlabelled × buttons is unusable by keyboard or screen reader,
    // and this strip is the one place a filter can be removed without finding
    // the widget that set it.
    renderBar({ column: 'region', value: 'North', label: 'region = North' })
    fireEvent.click(screen.getByRole('button', { name: 'emit' }))
    expect(screen.getByRole('button', { name: /remove filter/i })).toBeInTheDocument()
  })
})

describe('reader-side undo (Phase 1 item 4)', () => {
  function Two() {
    const { emitFilter } = useCrossFilter()
    return (
      <>
        <button onClick={() => emitFilter(1, 100, 'region', 'Asia', 'region is Asia')}>asia</button>
        <button onClick={() => emitFilter(2, 100, 'product', 'a', 'product is a')}>prod</button>
        <FilterBar keyboard />
      </>
    )
  }

  it('steps back and forward through the reader’s own selections, by button and by Ctrl+Z', () => {
    render(<CrossFilterProvider><Two /></CrossFilterProvider>)
    expect(screen.queryByLabelText('Undo selection')).toBeNull()      // nothing to undo yet
    fireEvent.click(screen.getByText('asia'))
    fireEvent.click(screen.getByText('prod'))
    expect(screen.getByText('product is a')).toBeInTheDocument()
    expect(screen.getByLabelText('Undo selection').getAttribute('title')).toBe('Back to: region is Asia')
    fireEvent.click(screen.getByLabelText('Undo selection'))
    expect(screen.queryByText('product is a')).toBeNull()
    expect(screen.getByLabelText('Redo selection').getAttribute('title')).toBe('Forward to: region is Asia and product is a')
    fireEvent.keyDown(window, { key: 'z', ctrlKey: true })
    expect(screen.getByText('No selections')).toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'z', ctrlKey: true, shiftKey: true })
    expect(screen.getByText('region is Asia')).toBeInTheDocument()
    // a new selection after an undo drops the redo branch
    fireEvent.click(screen.getByText('prod'))
    expect(screen.getByLabelText('Redo selection').getAttribute('aria-disabled')).toBe('true')
  })

  it('does not bind Ctrl+Z unless asked (the builder owns it for the author)', () => {
    function One() {
      const { emitFilter } = useCrossFilter()
      return <><button onClick={() => emitFilter(1, 100, 'region', 'Asia', 'region is Asia')}>asia</button><FilterBar /></>
    }
    render(<CrossFilterProvider><One /></CrossFilterProvider>)
    fireEvent.click(screen.getByText('asia'))
    fireEvent.keyDown(window, { key: 'z', ctrlKey: true })
    expect(screen.getByText('region is Asia')).toBeInTheDocument()
  })
})

describe('carry my selections (follow-up)', () => {
  it('re-scopes this page’s selections to the target page, replacing its same-source ones', () => {
    function C() {
      const { emitFilter, carryFiltersTo, getFiltersFor } = useCrossFilter()
      const onTarget = getFiltersFor(999, 200).map(f => f.label).join('|')
      return (<>
        <button onClick={() => emitFilter(1, 100, 'region', 'Asia', 'region is Asia')}>asia</button>
        <button onClick={() => carryFiltersTo(100, 200)}>carry</button>
        <span data-testid="target">{onTarget || 'none'}</span>
      </>)
    }
    render(<CrossFilterProvider><C /></CrossFilterProvider>)
    fireEvent.click(screen.getByText('asia'))
    expect(screen.getByTestId('target').textContent).toBe('none')
    fireEvent.click(screen.getByText('carry'))
    expect(screen.getByTestId('target').textContent).toBe('region is Asia')
    fireEvent.click(screen.getByText('carry'))           // idempotent
    expect(screen.getByTestId('target').textContent).toBe('region is Asia')
  })
})
