import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { AiTabs, PanelHead, RightRail } from './RightRail'

/** Redesign 7e3: the builder's right rail. */

const V1_PANELS = ['Outline', 'Selection', 'Parameters', 'Bookmarks', 'Sync slicers', 'AI', 'Comments', 'Version history',
  'Review', 'Performance', 'Tab order', 'Report rules', 'Schedule', 'Translations', 'Mobile layout']

describe('right rail (7e3)', () => {
  it('has a button for Properties and for every v1 panel, in named groups', () => {
    render(<RightRail mode="default" pinned={false} onPick={vi.fn()} />)
    const rail = screen.getByRole('navigation', { name: 'Panels' })
    expect(screen.getByRole('button', { name: 'Properties' })).toHaveAttribute('aria-pressed', 'true')
    for (const name of V1_PANELS) expect(screen.getByRole('button', { name }), name).toHaveAttribute('aria-pressed', 'false')
    expect(rail.querySelectorAll('[role="separator"]')).toHaveLength(5)
  })

  it('a press opens that panel; AI stays pressed on any of its three tabs', () => {
    const onPick = vi.fn()
    const { rerender } = render(<RightRail mode="default" pinned={false} onPick={onPick} />)
    fireEvent.click(screen.getByRole('button', { name: 'Review' }))
    expect(onPick).toHaveBeenCalledWith('review')
    fireEvent.click(screen.getByRole('button', { name: 'AI' }))
    expect(onPick).toHaveBeenCalledWith('ask')
    rerender(<RightRail mode="insights" pinned={false} onPick={onPick} />)
    expect(screen.getByRole('button', { name: 'AI' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('pinned, Properties stays pressed beside the other panel', () => {
    render(<RightRail mode="review" pinned onPick={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Properties' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Review' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('the panel head names the panel; Properties carries the pin', () => {
    const onPin = vi.fn()
    render(<PanelHead mode="default" onPin={onPin} pinned={false} />)
    expect(screen.getByRole('heading', { name: 'Properties' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Pin Properties open' }))
    expect(onPin).toHaveBeenCalled()
  })

  it('AI switches between Ask, Insights and Suggest by tabs', () => {
    const onPick = vi.fn()
    render(<AiTabs mode="ask" onPick={onPick} />)
    expect(screen.getByRole('tab', { name: 'Ask' })).toHaveAttribute('aria-selected', 'true')
    fireEvent.click(screen.getByRole('tab', { name: 'Suggest' }))
    expect(onPick).toHaveBeenCalledWith('suggestions')
  })
})
