import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { RightRail } from './RightRail'
import { EditToolbar } from './CanvasOverlays'

/** Autopilot step 8 (9-polish): the rail's review count and the toolbar's grip. */
describe('the builder rail', () => {
  it('counts open review findings on the Review item, and says so', () => {
    render(<RightRail mode="default" pinned={false} onPick={() => {}} counts={{ review: 3 }} />)
    const review = screen.getByRole('button', { name: 'Review (3 open)' })
    expect(review.querySelector('.dl-bd-ri__n')).toHaveTextContent('3')
  })
  it('shows no count when there is nothing open', () => {
    const { container } = render(<RightRail mode="default" pinned={false} onPick={() => {}} counts={{ review: 0 }} />)
    expect(container.querySelector('.dl-bd-ri__n')).toBeNull()
  })
})

describe('the quick toolbar', () => {
  it('has a grip that starts the widget’s move', () => {
    const onDragStart = vi.fn()
    const { container } = render(<EditToolbar title="Sales" onAssign={() => {}} onFilters={() => {}} onDragStart={onDragStart} />)
    fireEvent.mouseDown(container.querySelector('.dl-bd-wt__grip')!)
    expect(onDragStart).toHaveBeenCalled()
  })
})
