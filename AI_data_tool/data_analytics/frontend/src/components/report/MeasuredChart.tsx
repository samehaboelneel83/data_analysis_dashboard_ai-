import { useLayoutEffect, useRef, useState, type ReactNode } from 'react'

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
export function MeasuredChart({ children }: {
  children: (plotW?: number, plotH?: number) => ReactNode
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState<{ w: number; h: number } | null>(null)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const measure = () => {
      const r = el.getBoundingClientRect()
      if (!(r.width > 8 && r.height > 8)) return
      // Only on a real change: setState on every observer callback would
      // re-render the chart continuously while a tile is being resized.
      setSize(p => (p && Math.abs(p.w - r.width) < 1 && Math.abs(p.h - r.height) < 1)
        ? p : { w: r.width, h: r.height })
    }
    measure()
    if (typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return (
    <div ref={ref} style={{
      position: 'relative', width: '100%', height: '100%',
      minWidth: 0, minHeight: 0, overflow: 'hidden',
    }}>
      {children(size?.w || undefined, size?.h || undefined)}
    </div>
  )
}
