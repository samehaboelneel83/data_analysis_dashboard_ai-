import { useCallback, useEffect, useRef, useState } from 'react'

/** Below this row count, render everything exactly as before. This is the
 *  test-compatibility keystone: existing fixtures are small (and jsdom
 *  reports clientHeight 0), so nothing about their rendering changes. */
export const WINDOW_THRESHOLD = 150
const OVERSCAN = 10

/**
 * Hand-rolled row windowing for the table and list widgets: track scrollTop
 * (rAF-throttled) and the container height (ResizeObserver), return the slice
 * to render plus the pixel heights of the spacers that stand in for the rest.
 * The server caps results around 1,000 rows, so this turns a 1,000-row DOM
 * into ~40 rows without a dependency.
 */
export function useWindowedRows(rowCount: number, estRowHeight: number, enabled: boolean) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [scrollTop, setScrollTop] = useState(0)
  const [viewportH, setViewportH] = useState(0)
  const rafRef = useRef<number | null>(null)

  const onScroll = useCallback(() => {
    if (rafRef.current != null) return
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = null
      const el = containerRef.current
      if (el) setScrollTop(el.scrollTop)
    })
  }, [])

  useEffect(() => {
    if (!enabled) return
    const el = containerRef.current
    if (!el) return
    setViewportH(el.clientHeight)
    if (typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(() => { setViewportH(el.clientHeight) })
    ro.observe(el)
    return () => ro.disconnect()
  }, [enabled])

  useEffect(() => () => {
    if (rafRef.current != null) cancelAnimationFrame(rafRef.current)
  }, [])

  if (!enabled) {
    return { containerRef, onScroll, start: 0, end: rowCount, padTop: 0, padBottom: 0 }
  }
  // clientHeight 0 (jsdom, or a not-yet-laid-out container) falls back to a
  // sane window instead of rendering nothing.
  const visibleRows = viewportH > 0 ? Math.ceil(viewportH / estRowHeight) : 20
  const start = Math.max(0, Math.floor(scrollTop / estRowHeight) - OVERSCAN)
  const end = Math.min(rowCount, start + visibleRows + OVERSCAN * 2)
  return {
    containerRef, onScroll, start, end,
    padTop: start * estRowHeight,
    padBottom: (rowCount - end) * estRowHeight,
  }
}
