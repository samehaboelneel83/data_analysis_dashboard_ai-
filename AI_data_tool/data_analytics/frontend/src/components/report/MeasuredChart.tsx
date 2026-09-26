import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { watchDeclutter } from '../../lib/chartDeclutter'

/**
 * Reports the tile's measured size to the chart inside it.
 *
 * The axis planners in chartRenderers/axisOptions decide rotation, band depth
 * and tick density from how much room the labels actually have. Recharts'
 * ResponsiveContainer measures the same box but never exposes it to a prop
 * builder, so before this the planners used a nominal 560x300 -- fine on a
 * full-width tile, far too optimistic on a narrow one, and the labels
 * collided anyway. Arabic showed it first only because its glyphs are wider,
 * so the same nominal ran out sooner.
 *
 * A render-prop rather than a hook in WidgetRenderer: that component returns
 * early down a dozen branches, and a hook here would be conditional.
 */
/** How long a resize must pause before the chart redraws at the new size. */
export const RESIZE_SETTLE_MS = 150

export function MeasuredChart({ children }: {
  children: (plotW?: number, plotH?: number) => ReactNode
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState<{ w: number; h: number } | null>(null)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    // While a tile is being dragged to a new size the box changes every
    // frame. Redrawing a chart with thousands of marks per frame froze the
    // page (QA 2026-09-26), so the first size lands at once and later ones
    // settle: the chart keeps its last drawn size (clipped or with room to
    // spare) until the drag pauses for RESIZE_SETTLE_MS, then redraws once.
    let timer: ReturnType<typeof setTimeout> | undefined
    const commit = (w: number, h: number) =>
      setSize(p => (p && Math.abs(p.w - w) < 1 && Math.abs(p.h - h) < 1) ? p : { w, h })
    let first = true
    const measure = () => {
      const r = el.getBoundingClientRect()
      if (!(r.width > 8 && r.height > 8)) return
      if (first) { first = false; commit(r.width, r.height); return }
      clearTimeout(timer)
      timer = setTimeout(() => commit(r.width, r.height), RESIZE_SETTLE_MS)
    }
    measure()
    // E10: recharts draws each scatter point, radial bar and pie slice as
    // role="img". One without a name is an image with no text alternative
    // (axe svg-img-alt) -- a scatter of 150 points was 150 of them. The chart
    // as a whole is described by its tile, and its numbers are one click away
    // as a table, so an UNNAMED mark is decorative: hidden from assistive
    // technology, re-applied whenever recharts redraws. A mark a renderer
    // names (pie slices carry "name: value") is left alone.
    const hideUnnamedMarks = () => {
      el.querySelectorAll('svg [role="img"]:not([aria-label]):not([aria-labelledby]):not([aria-hidden])')
        .forEach(m => m.setAttribute('aria-hidden', 'true'))
    }
    hideUnnamedMarks()
    // Once per frame at most: during an animation recharts mutates every
    // frame, and rescanning thousands of marks each time was a long task.
    let hideRaf = 0
    const hideSoon = () => {
      if (hideRaf || typeof requestAnimationFrame === 'undefined') { if (!hideRaf) hideUnnamedMarks(); return }
      hideRaf = requestAnimationFrame(() => { hideRaf = 0; hideUnnamedMarks() })
    }
    const mo = typeof MutationObserver === 'undefined' ? null : new MutationObserver(hideSoon)
    mo?.observe(el, { childList: true, subtree: true })
    const cleanup = () => { clearTimeout(timer); if (hideRaf) cancelAnimationFrame(hideRaf); mo?.disconnect() }
    if (typeof ResizeObserver === 'undefined') return cleanup
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => { ro.disconnect(); cleanup() }
  }, [])
  // No two labels may overlap and none may be cut at the tile's edge, at any
  // tile size: measured on the drawn SVG, after every redraw (QA 2026-09-26).
  useEffect(() => {
    const el = ref.current
    if (!el || typeof requestAnimationFrame === 'undefined') return
    return watchDeclutter(el)
  }, [])
  return (
    <div ref={ref} style={{
      position: 'relative', width: '100%', height: '100%',
      minWidth: 0, minHeight: 0, overflow: 'hidden',
    }}>
      {/* The chart is drawn at the SETTLED size, so recharts' own
          ResponsiveContainer sees one change per resize, not one per frame. */}
      <div style={size ? { width: size.w, height: size.h } : { width: '100%', height: '100%' }}>
        {children(size?.w || undefined, size?.h || undefined)}
      </div>
    </div>
  )
}
