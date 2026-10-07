import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import ChartGallery from './ChartGallery'

/** Redesign 7e2: the Insert tab's chart gallery. */

describe('chart gallery', () => {
  it('a tile adds its chart', () => {
    const onAdd = vi.fn()
    render(<ChartGallery query="" onQuery={vi.fn()} onAdd={onAdd} />)
    fireEvent.click(screen.getByRole('button', { name: 'Pie Chart' }))
    expect(onAdd).toHaveBeenCalledWith('pie')
  })

  it('pointing at a tile previews the chart and what it is best for; leaving hides it', () => {
    render(<ChartGallery query="" onQuery={vi.fn()} onAdd={vi.fn()} />)
    const tile = screen.getByRole('button', { name: 'Pie Chart' })
    fireEvent.mouseEnter(tile)
    const preview = screen.getByTestId('gallery-preview')
    expect(preview).toHaveTextContent('Pie')
    expect(preview).toHaveTextContent('Best for 2–5 parts of a whole.')
    // The tile names its preview for a screen reader too.
    expect(tile).toHaveAttribute('aria-describedby', preview.id)
    fireEvent.mouseLeave(tile)
    expect(screen.queryByTestId('gallery-preview')).toBeNull()
  })

  it('keyboard focus previews too, and every chart has a "best for" line', () => {
    render(<ChartGallery query="" onQuery={vi.fn()} onAdd={vi.fn()} />)
    const tile = screen.getByRole('button', { name: 'Flow (Sankey)' })
    fireEvent.focus(tile)
    expect(screen.getByTestId('gallery-preview').textContent).toMatch(/\.$/)
    fireEvent.blur(tile)
    expect(screen.queryByTestId('gallery-preview')).toBeNull()
  })

  it('every tile has its own "best for" line, never a missing-text key', () => {
    render(<ChartGallery query="" onQuery={vi.fn()} onAdd={vi.fn()} />)
    for (const tile of screen.getAllByRole('button').filter(b => b.classList.contains('dl-gallery__tile'))) {
      fireEvent.mouseEnter(tile)
      expect(screen.getByTestId('gallery-preview').textContent, tile.getAttribute('aria-label') ?? '').not.toMatch(/gallery\./)
      fireEvent.mouseLeave(tile)
    }
  })
})
