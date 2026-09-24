import { useLayoutEffect, useRef, useState, type ReactNode, type Ref, type SVGProps } from 'react'
import { mapViewSize, MAP_SVG_STYLE, MAP_WRAP_STYLE } from './worldGeometry'
import { tilesFor, useTileSettings } from './tiles'
import type { MapSettings } from '../../../services/api'

/**
 * Live size of the map tile. Prefers the wrap's own box so a stale 16:9
 * `plotW` from a first paint cannot lock the projection to 960px (which is
 * what clipped London / Tokyo on a ~500px widget). Falls back to `plotW` /
 * `plotH` when jsdom has no layout.
 */
export function useMapBox(plotW?: number, plotH?: number) {
  const ref = useRef<HTMLDivElement>(null)
  const [box, setBox] = useState({ w: 0, h: 0 })
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const measure = () => {
      const r = el.getBoundingClientRect()
      const w = r.width, h = r.height
      if (w > 8 && h > 8) {
        setBox(p => (Math.abs(p.w - w) < 1 && Math.abs(p.h - h) < 1) ? p : { w, h })
      }
    }
    measure()
    if (typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  const fallback = mapViewSize(plotW, plotH)
  // The org basemap, if any. Renderers put it in their projection memo's
  // dependencies, so a map re-projects to Mercator when the setting arrives.
  const tiles = useTileSettings()
  return {
    ref,
    tiles,
    w: box.w > 8 ? box.w : fallback.w,
    h: box.h > 8 ? box.h : fallback.h,
  }
}

export { MAP_WRAP_STYLE }

/** SVG that fills its tile. Width/height *attributes* (not only CSS) stop the
 *  viewBox from becoming the intrinsic size that overflow:hidden then clips. */
function prefersContrast(): boolean {
  try { return typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-contrast: more)').matches } catch { return false }
}

export function MapSvg({ w, h, svgRef, children, projection, tiles, credit, ...rest }: {
  w: number
  h: number
  svgRef?: Ref<SVGSVGElement>
  children?: ReactNode
  /** The map's projection and the org basemap: together they draw the tiles
   *  under the vector layers. Either absent = no basemap, as before. */
  projection?: { scale(): number; (p: [number, number]): [number, number] | null }
  tiles?: MapSettings | null
  /** The boundary source's required credit (a pack installed under terms).
   *  Drawn whether or not there is a basemap, bottom-left so it never sits
   *  on the tile attribution. */
  credit?: string | null
} & Omit<SVGProps<SVGSVGElement>, 'width' | 'height' | 'viewBox' | 'ref'>) {
  if (!(w > 8 && h > 8)) return null
  const template = tiles ? ((prefersContrast() && tiles.contrast_tile_url) || tiles.tile_url) : null
  const images = template && projection ? tilesFor(projection, w, h, template) : []
  return (
    <svg
      ref={svgRef}
      width="100%"
      height="100%"
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="xMidYMid meet"
      // A map is never mirrored in RTL. `dir` is a valid SVG presentation
      // attribute that React's SVG typings omit, hence the spread.
      {...{ dir: 'ltr' } as Record<string, string>}
      overflow="hidden"
      // Over a basemap the land fill goes clear, so the tiles show through
      // every shape that is not carrying data, and data fills (colour-mixed
      // with the same variable) turn translucent over them.
      style={images.length ? { ...MAP_SVG_STYLE, ['--surface2' as string]: 'transparent' } : MAP_SVG_STYLE}
      data-basemap={images.length ? 'tiles' : undefined}
      {...rest}
    >
      {images.length > 0 && (
        <g data-testid="map-tiles" aria-hidden="true" pointerEvents="none">
          {images.map(t => (
            <image key={t.key} href={t.href} x={t.x} y={t.y} width={t.size + 0.5} height={t.size + 0.5}
              preserveAspectRatio="none" />
          ))}
        </g>
      )}
      {children}
      {images.length > 0 && tiles?.attribution && (
        <text x={w - 4} y={h - 4} textAnchor="end" fontSize={9} fill="var(--muted)"
          style={{ paintOrder: 'stroke', stroke: 'var(--surface)', strokeWidth: 3 }}>{tiles.attribution}</text>
      )}
      {credit && (
        <text data-testid="map-boundary-credit" x={4} y={h - 4} textAnchor="start" fontSize={9} fill="var(--muted)"
          style={{ paintOrder: 'stroke', stroke: 'var(--surface)', strokeWidth: 3 }}>{credit}</text>
      )}
    </svg>
  )
}
