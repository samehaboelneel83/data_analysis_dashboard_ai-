import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import {
  DirectionProvider, useDirection, widgetIsRtl, navArrows,
} from './DirectionContext'

/**
 * App-wide reading direction.
 *
 * jsdom performs no layout, so nothing here can prove a panel visually mirrors
 * — that is what the live check is for. What these tests CAN pin is the three
 * decisions that make mirroring reach the page at all:
 *
 *   1. the document root carries `dir`, since that is the single switch the
 *      browser acts on for flexbox, grid, scrollbars and logical properties;
 *   2. a widget with no explicit choice follows the app;
 *   3. navigational glyphs flip, because `dir` cannot rewrite a character.
 */
function Probe() {
  const { direction, rtl, setDirection } = useDirection()
  return (
    <div>
      <span data-testid="dir">{direction}</span>
      <span data-testid="rtl">{String(rtl)}</span>
      <button onClick={() => setDirection(rtl ? 'ltr' : 'rtl')}>flip</button>
    </div>
  )
}

beforeEach(() => {
  localStorage.clear()
  document.documentElement.dir = ''
})

describe('DirectionProvider', () => {
  it('defaults to left-to-right', () => {
    render(<DirectionProvider><Probe /></DirectionProvider>)
    expect(screen.getByTestId('dir')).toHaveTextContent('ltr')
  })

  it('puts the direction on the document root, not a wrapper', () => {
    // A wrapper div would leave portals and dialogs rendered outside the tree
    // pointing the wrong way.
    render(<DirectionProvider><Probe /></DirectionProvider>)
    act(() => { fireEvent.click(screen.getByRole('button', { name: 'flip' })) })
    expect(document.documentElement.dir).toBe('rtl')
  })

  it('remembers the choice across a remount', () => {
    const first = render(<DirectionProvider><Probe /></DirectionProvider>)
    act(() => { fireEvent.click(screen.getByRole('button', { name: 'flip' })) })
    first.unmount()

    render(<DirectionProvider><Probe /></DirectionProvider>)
    expect(screen.getByTestId('dir')).toHaveTextContent('rtl')
  })

  it('survives storage being unavailable', () => {
    // Private windows and blocked site-data THROW on access rather than
    // returning null, so a null check would not have covered this.
    const spy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    expect(() => render(<DirectionProvider><Probe /></DirectionProvider>)).not.toThrow()
    expect(screen.getByTestId('dir')).toHaveTextContent('ltr')
    spy.mockRestore()
  })

  it('falls back to left-to-right with no provider rather than throwing', () => {
    // A page rendered in isolation (a test, a print view) must still render.
    render(<Probe />)
    expect(screen.getByTestId('dir')).toHaveTextContent('ltr')
  })
})

describe('widgetIsRtl', () => {
  it('follows the app when the widget never opted in', () => {
    // THE decision that makes app-wide RTL work. WidgetConfigPanel writes `rtl`
    // into every saved config, so nearly every existing widget carries
    // `rtl: false` — meaning "never turned on", not "force left-to-right".
    // Reading it as a plain boolean would pin every widget to LTR and make the
    // app switch do nothing at all.
    expect(widgetIsRtl(false, true)).toBe(true)
    expect(widgetIsRtl(undefined, true)).toBe(true)
  })

  it('lets one widget opt in inside a left-to-right report', () => {
    expect(widgetIsRtl(true, false)).toBe(true)
  })

  it('leaves an untouched widget alone in a left-to-right app', () => {
    expect(widgetIsRtl(false, false)).toBe(false)
    expect(widgetIsRtl(undefined, false)).toBe(false)
  })
})

describe('navArrows', () => {
  it('points "back" toward the start of the reading direction', () => {
    // `dir` mirrors layout but cannot rewrite a character: a ← keeps pointing
    // left on an RTL page, where "back" is to the right.
    expect(navArrows(false).back).toBe('←')
    expect(navArrows(true).back).toBe('→')
  })

  it('flips chevrons too', () => {
    expect(navArrows(true).backChevron).toBe('›')
    expect(navArrows(true).forwardChevron).toBe('‹')
  })
})
