import { useCallback, useRef, useState } from 'react'

/**
 * The live width of an element, from the moment it exists.
 *
 * The report canvas used to do this with a ref, a `useState(900)` fallback and a
 * `useEffect(..., [])` that returned early when `ref.current` was null. The
 * canvas renders inside a branch that only exists once the report has loaded, so
 * on first paint the ref *was* null: the effect returned, never ran again, and
 * no observer was ever attached. The grid then laid every tile out at 900px for
 * the life of the page — measured live as a 1,098px canvas using 900 of it, and
 * in view mode an 843px canvas with tiles overflowing by 55.
 *
 * A callback ref cannot miss the node. It fires when the element attaches,
 * whatever order things render in, and fires again when a branch swap (view mode
 * to edit mode) destroys and recreates it.
 *
 * `ref` is exposed because other code — the drag and resize handlers — needs the
 * same element.
 */
export function useMeasuredWidth(initial: number) {
  const [width, setWidth] = useState(initial)
  const ref = useRef<HTMLElement | null>(null)
  const observer = useRef<ResizeObserver | null>(null)

  /** Zero is not a width. An element that is not laid out -- a collapsed panel,
   *  a hidden tab, anything at all under jsdom -- reports 0, and dividing a
   *  twelve-column grid by it gives every tile a negative cell width. Keep the
   *  last real number until a real one arrives. */
  const take = useCallback((px: number) => {
    if (px > 0) setWidth(px)
  }, [])

  const attach = useCallback((node: HTMLElement | null) => {
    observer.current?.disconnect()
    observer.current = null
    ref.current = node
    if (!node) return

    // Measured immediately as well as observed: a ResizeObserver reports the
    // first size on its own, but not until a frame has passed, and the grid
    // renders before that.
    take(node.clientWidth)
    if (typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(() => take(node.clientWidth))
    ro.observe(node)
    observer.current = ro
  }, [take])

  return { width, attach, ref }
}
