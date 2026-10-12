import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import AskFab from './AskFab'

/** Autopilot step 6: the floating Ask AI button. */

const box = () => {
  const host = document.createElement('div')
  document.body.appendChild(host)
  host.getBoundingClientRect = () => ({ left: 0, top: 0, right: 1000, bottom: 800, width: 1000, height: 800, x: 0, y: 0, toJSON: () => ({}) })
  return host
}
// jsdom has no PointerEvent: mouse events carrying the pointer's fields.
const ptr = (el: Element, type: string, x: number, y: number) =>
  fireEvent(el, Object.assign(new MouseEvent(type, { bubbles: true, clientX: x, clientY: y, button: 0 }), { pointerId: 1 }))

beforeEach(() => { localStorage.clear(); document.body.innerHTML = '' })

describe('the Ask AI button', () => {
  it('opens the page’s panel; it names itself and its shortcut', () => {
    const onOpen = vi.fn()
    render(<AskFab onOpen={onOpen} alive />, { container: box() })
    const b = screen.getByRole('button', { name: 'Ask AI about this dashboard' })
    expect(b).toHaveAttribute('aria-keyshortcuts', 'Control+/')
    expect(screen.getByRole('tooltip')).toHaveTextContent('Ask AI about this dashboard Ctrl /')
    fireEvent.click(b)
    expect(onOpen).toHaveBeenCalledTimes(1)
  })

  it('sits at the bottom inline end at first, and a drag moves it to the nearest corner, remembered', () => {
    const onOpen = vi.fn()
    const { container, unmount } = render(<AskFab onOpen={onOpen} alive />, { container: box() })
    const wrap = container.querySelector('.dl-fab')!
    expect(wrap).toHaveClass('dl-fab--be')
    const b = screen.getByRole('button')
    ptr(b, 'pointerdown', 900, 700); ptr(b, 'pointermove', 400, 300); ptr(b, 'pointerup', 100, 100)
    expect(wrap).toHaveClass('dl-fab--ts')
    fireEvent.click(b)   // the click that follows a drag
    expect(onOpen).not.toHaveBeenCalled()
    fireEvent.click(b)
    expect(onOpen).toHaveBeenCalledTimes(1)
    unmount()
    const again = render(<AskFab onOpen={onOpen} alive />, { container: box() })
    expect(again.container.querySelector('.dl-fab')).toHaveClass('dl-fab--ts')
  })

  it('goes quiet while the canvas scrolls, and comes back', () => {
    vi.useFakeTimers()
    try {
      const host = box()
      const { container } = render(<AskFab onOpen={() => {}} alive />, { container: host })
      const inner = document.createElement('div'); host.appendChild(inner)
      fireEvent.scroll(inner)
      expect(container.querySelector('.dl-fab')).toHaveClass('is-quiet')
      act(() => { vi.advanceTimersByTime(700) })
      expect(container.querySelector('.dl-fab')).not.toHaveClass('is-quiet')
    } finally { vi.useRealTimers() }
  })
})
