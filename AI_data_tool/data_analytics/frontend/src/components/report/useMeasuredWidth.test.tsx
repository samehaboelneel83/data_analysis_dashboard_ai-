import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { useCallback, useState } from 'react'
import { useMeasuredWidth } from './useMeasuredWidth'

/**
 * The canvas must be laid out at the width it actually has.
 *
 * The report canvas sized its grid from `useState(900)` and a `ResizeObserver`
 * attached in a `useEffect` with `[]` deps that returned early when the ref was
 * still null. The canvas renders inside a branch that only exists once the
 * report has loaded, so on first paint the ref WAS null — the effect returned,
 * never ran again, and no observer was ever attached.
 *
 * Measured live: a canvas 1,098px wide laying its tiles out at 900px, leaving
 * 200px of empty page; in view mode a canvas of 843px with tiles overflowing it
 * by 55px. On a wide screen the wasted strip is several hundred pixels.
 *
 * A callback ref cannot miss the node: it fires when the element attaches,
 * whatever order things render in, and again when a branch swap replaces it.
 */
let observed: { el: Element; cb: ResizeObserverCallback }[] = []

class FakeResizeObserver {
  constructor(private cb: ResizeObserverCallback) {}
  observe(el: Element) { observed.push({ el, cb: this.cb }) }
  disconnect() { observed = observed.filter(o => o.cb !== this.cb) }
  unobserve() {}
}

beforeEach(() => {
  observed = []
  vi.stubGlobal('ResizeObserver', FakeResizeObserver)
})
afterEach(() => vi.unstubAllGlobals())

/** Fires every live observer, as the browser would after a layout change. */
function resizeTo(px: number) {
  for (const o of observed) {
    Object.defineProperty(o.el, 'clientWidth', { value: px, configurable: true })
  }
  act(() => { for (const o of [...observed]) o.cb([], {} as ResizeObserver) })
}

function Probe({ initial = 900, show = true, width = 1400 }:
               { initial?: number; show?: boolean; width?: number }) {
  const { width: measured, attach } = useMeasuredWidth(initial)
  // Stable, and it stubs the width only ONCE. An inline ref re-runs on every
  // render, so React detaches and re-attaches the node each time -- and a stub
  // applied on every pass would overwrite whatever a simulated resize just set,
  // testing the harness instead of the hook.
  const ref = useCallback((node: HTMLDivElement | null) => {
    if (node && !Object.getOwnPropertyDescriptor(node, 'clientWidth')) {
      Object.defineProperty(node, 'clientWidth', { value: width, configurable: true })
    }
    attach(node)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attach])
  return (
    <div>
      <span data-testid="w">{measured}</span>
      {show && <div data-testid="canvas" ref={ref} />}
    </div>
  )
}

const read = () => Number(screen.getByTestId('w').textContent)

describe('measuring on attach', () => {
  it('uses the fallback before anything is attached', () => {
    render(<Probe initial={900} show={false} />)
    expect(read()).toBe(900)
  })

  it('measures the node the moment it attaches', () => {
    // The failure this replaces: the node attached AFTER the effect had already
    // given up, so the fallback stood for the life of the page.
    render(<Probe initial={900} width={1400} />)
    expect(read()).toBe(1400)
  })

  it('observes the node it attached to', () => {
    render(<Probe />)
    expect(observed.length).toBe(1)
  })
})

describe('following the element', () => {
  it('updates when the element is resized', () => {
    render(<Probe width={1400} />)
    resizeTo(1000)
    expect(read()).toBe(1000)
  })

  it('re-measures when a branch swap replaces the node', () => {
    // View mode and edit mode render the canvas from different branches, so the
    // element is destroyed and recreated. An effect with [] deps never notices.
    function Swapper() {
      const [wide, setWide] = useState(false)
      const { width, attach } = useMeasuredWidth(900)
      return (
        <div>
          <span data-testid="w">{width}</span>
          <button onClick={() => setWide(true)}>swap</button>
          {wide
            ? <div key="b" ref={n => { if (n) Object.defineProperty(n, 'clientWidth', { value: 1600, configurable: true }); attach(n) }} />
            : <div key="a" ref={n => { if (n) Object.defineProperty(n, 'clientWidth', { value: 800, configurable: true }); attach(n) }} />}
        </div>
      )
    }
    render(<Swapper />)
    expect(read()).toBe(800)
    act(() => { screen.getByText('swap').click() })
    expect(read()).toBe(1600)
  })

  it('stops observing the node it let go of', () => {
    const { rerender } = render(<Probe show />)
    expect(observed.length).toBe(1)
    rerender(<Probe show={false} />)
    expect(observed.length).toBe(0)
  })
})

describe('a width of zero is not a measurement', () => {
  /**
   * An element that is not laid out reports 0: a canvas inside a collapsed
   * panel, a hidden tab, or anything in jsdom, which has no layout at all.
   *
   * Taking that at face value collapses the grid — twelve columns out of zero
   * pixels is a negative cell width, and every tile lands in the wrong place.
   * Keeping the last real number leaves the layout as it was until a genuine
   * measurement arrives.
   */
  it('keeps the fallback when the element measures zero', () => {
    render(<Probe initial={900} width={0} />)
    expect(read()).toBe(900)
  })

  it('keeps the last real width when the element is later hidden', () => {
    render(<Probe initial={900} width={1400} />)
    expect(read()).toBe(1400)
    resizeTo(0)
    expect(read()).toBe(1400)
  })

  it('takes a real width once one arrives', () => {
    render(<Probe initial={900} width={0} />)
    resizeTo(1200)
    expect(read()).toBe(1200)
  })
})

describe('the ref other code reads', () => {
  it('exposes the attached element', () => {
    function WithRef() {
      const { attach, ref } = useMeasuredWidth(900)
      return (
        <div>
          <span data-testid="tag">{ref.current?.tagName ?? 'none'}</span>
          <section ref={attach} />
        </div>
      )
    }
    const { rerender } = render(<WithRef />)
    rerender(<WithRef />)
    expect(screen.getByTestId('tag').textContent).toBe('SECTION')
  })
})
