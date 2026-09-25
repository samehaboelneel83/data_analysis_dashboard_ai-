import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import CollapsibleSide, { RAIL_W, MIN_PANEL_W, MAX_PANEL_W } from './CollapsibleSide'

beforeEach(() => localStorage.clear())

const renderPanel = (over: Partial<React.ComponentProps<typeof CollapsibleSide>> = {}) =>
  render(
    <CollapsibleSide id="cfg" side="right" width={245} title="Settings" {...over}>
      <p>panel body</p>
    </CollapsibleSide>
  )

describe('CollapsibleSide', () => {
  it('starts expanded, so the panel is not hidden from an author who never asked for that', () => {
    renderPanel()
    expect(screen.getByRole('button', { name: /Collapse Settings/i })).toHaveAttribute('aria-expanded', 'true')
  })

  it('gives the panel width back to the canvas when collapsed', () => {
    const { container } = renderPanel()
    const shell = container.firstElementChild as HTMLElement
    expect(shell).toHaveStyle({ width: '245px' })

    fireEvent.click(screen.getByRole('button', { name: /Collapse Settings/i }))
    expect(shell).toHaveStyle({ width: `${RAIL_W}px` })
  })

  it('leaves a rail wide enough to reopen from, never collapsing to nothing', () => {
    renderPanel()
    fireEvent.click(screen.getByRole('button', { name: /Collapse Settings/i }))
    // The reopen control must still be reachable -- a zero-width panel would strand it.
    expect(RAIL_W).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: /Expand Settings/i })).toBeInTheDocument()
  })

  it('keeps children mounted while collapsed so an in-progress edit survives', () => {
    renderPanel()
    fireEvent.click(screen.getByRole('button', { name: /Collapse Settings/i }))
    // Present in the DOM (state preserved) but not exposed to assistive tech.
    expect(screen.getByText('panel body')).toBeInTheDocument()
    expect(screen.getByText('panel body').closest('[aria-hidden]')).toHaveAttribute('aria-hidden', 'true')
  })

  it('reports its state to assistive tech and relabels the control', () => {
    renderPanel()
    const btn = screen.getByRole('button', { name: /Collapse Settings/i })
    fireEvent.click(btn)
    expect(screen.getByRole('button', { name: /Expand Settings/i })).toHaveAttribute('aria-expanded', 'false')
  })

  it('remembers the collapse across remounts, so it is not re-collapsed every visit', () => {
    const { unmount } = renderPanel()
    fireEvent.click(screen.getByRole('button', { name: /Collapse Settings/i }))
    unmount()

    renderPanel()
    expect(screen.getByRole('button', { name: /Expand Settings/i })).toBeInTheDocument()
  })

  it('keeps each panel independent', () => {
    render(
      <>
        <CollapsibleSide id="left" side="left" width={220} title="Fields"><p>l</p></CollapsibleSide>
        <CollapsibleSide id="right" side="right" width={245} title="Settings"><p>r</p></CollapsibleSide>
      </>
    )
    fireEvent.click(screen.getByRole('button', { name: /Collapse Fields/i }))
    expect(screen.getByRole('button', { name: /Expand Fields/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Collapse Settings/i })).toBeInTheDocument()
  })

  it('survives unreadable storage rather than failing to render', () => {
    localStorage.setItem('datalytics.builderPanels', 'not json')
    renderPanel()
    expect(screen.getByText('panel body')).toBeInTheDocument()
  })
})

describe('CollapsibleSide scroll reset', () => {
  it('resets the content scroll position when scrollResetKey changes', () => {
    const { rerender, getByLabelText } = renderPanel({ scrollResetKey: 'widget-1' })
    const scrollBox = getByLabelText('Settings')
    Object.defineProperty(scrollBox, 'scrollTop', { value: 240, writable: true })
    expect(scrollBox.scrollTop).toBe(240)

    rerender(
      <CollapsibleSide id="cfg" side="right" width={245} title="Settings" scrollResetKey="widget-2">
        <p>panel body</p>
      </CollapsibleSide>
    )
    expect(scrollBox.scrollTop).toBe(0)
  })

  it('leaves scroll position alone when the key does not change', () => {
    const { rerender, getByLabelText } = renderPanel({ scrollResetKey: 'widget-1' })
    const scrollBox = getByLabelText('Settings')
    Object.defineProperty(scrollBox, 'scrollTop', { value: 240, writable: true })

    rerender(
      <CollapsibleSide id="cfg" side="right" width={245} title="Settings" scrollResetKey="widget-1">
        <p>panel body changed</p>
      </CollapsibleSide>
    )
    expect(scrollBox.scrollTop).toBe(240)
  })
})

describe('CollapsibleSide resizing', () => {
  const sep = () => screen.getByRole('separator', { name: /Resize Settings/i })

  it('offers a resize separator only while expanded -- a rail has no width to drag', () => {
    renderPanel()
    expect(sep()).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Collapse Settings/i }))
    expect(screen.queryByRole('separator')).not.toBeInTheDocument()
  })

  it('widens with the arrow key that moves away from the canvas', () => {
    const { container } = renderPanel()
    const shell = container.firstElementChild as HTMLElement
    // Right-edge panel: ArrowLeft grows it, because its inner edge moves left.
    fireEvent.keyDown(sep(), { key: 'ArrowLeft' })
    expect(shell).toHaveStyle({ width: '253px' })
    fireEvent.keyDown(sep(), { key: 'ArrowRight' })
    expect(shell).toHaveStyle({ width: '245px' })
  })

  it('mirrors the key directions for a left-edge panel', () => {
    const { container } = render(
      <CollapsibleSide id="lhs" side="left" width={220} title="Fields"><p>b</p></CollapsibleSide>
    )
    const shell = container.firstElementChild as HTMLElement
    // Left-edge panel: ArrowRight grows it. Asserting the OPPOSITE key from the test
    // above is the point -- a component that ignored `side` would pass one, not both.
    fireEvent.keyDown(screen.getByRole('separator', { name: /Resize Fields/i }), { key: 'ArrowRight' })
    expect(shell).toHaveStyle({ width: '228px' })
  })

  it('clamps to a floor and a ceiling so the panel cannot swallow or vanish from the canvas', () => {
    const { container } = renderPanel()
    const shell = container.firstElementChild as HTMLElement
    fireEvent.keyDown(sep(), { key: 'Home' })
    expect(shell).toHaveStyle({ width: `${MIN_PANEL_W}px` })
    fireEvent.keyDown(sep(), { key: 'ArrowRight' })   // already at the floor
    expect(shell).toHaveStyle({ width: `${MIN_PANEL_W}px` })

    fireEvent.keyDown(sep(), { key: 'End' })
    expect(shell).toHaveStyle({ width: `${MAX_PANEL_W}px` })
    fireEvent.keyDown(sep(), { key: 'ArrowLeft' })    // already at the ceiling
    expect(shell).toHaveStyle({ width: `${MAX_PANEL_W}px` })
  })

  it('remembers a resized width across remounts', () => {
    const { unmount } = renderPanel()
    fireEvent.keyDown(sep(), { key: 'ArrowLeft' })
    unmount()

    const { container } = renderPanel()
    expect(container.firstElementChild).toHaveStyle({ width: '253px' })
  })

  it('ignores a corrupt stored width rather than rendering an unusable panel', () => {
    localStorage.setItem('datalytics.builderPanelWidths', JSON.stringify({ cfg: 'wide' }))
    const { container } = renderPanel()
    expect(container.firstElementChild).toHaveStyle({ width: '245px' })
  })

  it('exposes the current width to assistive tech', () => {
    renderPanel()
    expect(sep()).toHaveAttribute('aria-valuenow', '245')
    expect(sep()).toHaveAttribute('aria-valuemin', String(MIN_PANEL_W))
    expect(sep()).toHaveAttribute('aria-valuemax', String(MAX_PANEL_W))
  })
})
