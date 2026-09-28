import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode, type Ref, type SVGProps } from 'react'
import { geoPath, type GeoProjection } from 'd3-geo'
import { fittedProjection, mapViewSize, MAP_SVG_STYLE, MAP_WRAP_STYLE } from './worldGeometry'
import { tilesFor, useTileSettings, type TileImage } from './tiles'
import { isVectorTemplate, loadVectorTile, VECTOR_MAX_ZOOM, type BasemapFeature, type BasemapKind } from './vectorTiles'
import type { MapSettings } from '../../../services/api'

type MapProjection = { scale(): number; (p: [number, number]): [number, number] | null }

/** Paint order and look of the vector basemap, quiet so data stays the figure:
 *  land cover first, water over it, roads and borders on top, then names. */
const VECTOR_STYLE: { kind: BasemapKind; fill?: string; stroke?: string; width?: number; dash?: string }[] = [
  { kind: 'landcover', fill: 'color-mix(in srgb, #34d399 10%, transparent)' },
  { kind: 'park', fill: 'color-mix(in srgb, #34d399 14%, transparent)' },
  { kind: 'landuse', fill: 'color-mix(in srgb, var(--muted) 10%, transparent)' },
  { kind: 'water', fill: 'color-mix(in srgb, #5b7cfa 22%, var(--surface))' },
  { kind: 'waterway', stroke: 'color-mix(in srgb, #5b7cfa 45%, var(--surface))', width: 0.8 },
  { kind: 'minor_road', stroke: 'color-mix(in srgb, var(--muted) 35%, transparent)', width: 0.5 },
  { kind: 'road', stroke: 'color-mix(in srgb, var(--muted) 55%, transparent)', width: 0.9 },
  { kind: 'boundary', stroke: 'color-mix(in srgb, var(--muted) 70%, transparent)', width: 0.8, dash: '3 2' },
]
const MAX_PLACE_LABELS = 40

function pageLang(): string {
  try { return document.documentElement.lang || 'en' } catch { return 'en' }
}

/** The decoded vector tiles, drawn through the map's own projection. */
function VectorBasemap({ tiles, projection }: { tiles: TileImage[]; projection: MapProjection }) {
  const lang = pageLang()
  const [features, setFeatures] = useState<BasemapFeature[]>([])
  const key = tiles.map(t => t.href).join('|')
  useEffect(() => {
    let live = true
    Promise.all(tiles.map(t => loadVectorTile(t.href, t.z, t.tx, t.ty, lang)))
      .then(parts => { if (live) setFeatures(parts.flat()) })
    return () => { live = false }
    // `key` stands for `tiles`, which is a fresh array every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, lang])
  const path = useMemo(() => geoPath(projection as unknown as GeoProjection), [projection])
  const labels = useMemo(() => {
    const seen = new Set<string>()
    return features.filter(f => f.kind === 'place' && f.label && !seen.has(f.label) && seen.add(f.label))
      .sort((a, b) => (a.rank ?? 99) - (b.rank ?? 99)).slice(0, MAX_PLACE_LABELS)
  }, [features])
  if (!features.length) return null
  return (
    <g data-testid="map-vector-tiles" aria-hidden="true" pointerEvents="none">
      {VECTOR_STYLE.map(s => {
        const d = features.filter(f => f.kind === s.kind).map(f => path(f.geo) || '').join('')
        return d ? <path key={s.kind} data-kind={s.kind} d={d} fill={s.fill ?? 'none'} stroke={s.stroke ?? 'none'}
          strokeWidth={s.width} strokeDasharray={s.dash} vectorEffect="non-scaling-stroke" /> : null
      })}
      {labels.map(f => {
        const c = f.geo.geometry.type === 'Point' ? projection(f.geo.geometry.coordinates as [number, number]) : null
        return c ? (
          <text key={f.label} x={c[0]} y={c[1]} fontSize={9} textAnchor="middle" fill="var(--muted)"
            style={{ paintOrder: 'stroke', stroke: 'var(--surface)', strokeWidth: 3 }}>{f.label}</text>
        ) : null
      })}
    </g>
  )
}

/**
 * Live size of the map tile. Prefers the wrap's own box so a stale 16:9
 * `plotW` from a first paint cannot lock the projection to 960px (which is
 * what clipped London / Tokyo on a ~500px widget). Falls back to `plotW` /
 * `plotH` when jsdom has no layout.
 */
export function useMapBox(plotW?: number, plotH?: number) {
  const ref = useRef<HTMLDivElement>(null)
  const [box, setBox] = useState({ w: 0, h: 0 })
  const view = useMapView()
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
    view,
    w: box.w > 8 ? box.w : fallback.w,
    h: box.h > 8 ? box.h : fallback.h,
  }
}

/** Zoom of 1 is the fitted frame; past this the map is street scale. */
const MAX_ZOOM = 64

/**
 * The reader's zoom and pan over a map, as one transform on its projection:
 * every screen point s of the fitted frame is drawn at k*s + (x, y).
 *
 * Applied to the PROJECTION rather than as an SVG scale, so shapes re-project
 * crisply, markers and lines keep their size, and the basemap fetches tiles
 * at the zoom the reader is looking at. Requested 2026-09-28: "zoom in or
 * zoom out on the geographical objects".
 */
export interface MapView {
  k: number
  x: number
  y: number
  /** `fittedProjection`, with the reader's zoom applied. */
  fit: typeof fittedProjection
  /** Zoom by `factor`, keeping the point `at` (viewBox units) where it is. */
  zoomBy: (factor: number, at: [number, number]) => void
  panBy: (dx: number, dy: number) => void
  reset: () => void
}

export function useMapView(): MapView {
  const [t, setT] = useState({ k: 1, x: 0, y: 0 })
  return useMemo(() => ({
    ...t,
    fit: ((...args: Parameters<typeof fittedProjection>) => {
      const fitted = fittedProjection(...args)
      if (t.k === 1 && t.x === 0 && t.y === 0) return fitted
      const p = fitted.projection
      const [tx, ty] = p.translate()
      p.scale(p.scale() * t.k).translate([tx * t.k + t.x, ty * t.k + t.y])
      return { projection: p, path: geoPath(p) }
    }) as typeof fittedProjection,
    zoomBy: (factor: number, [px, py]: [number, number]) => setT(prev => {
      const k = Math.min(MAX_ZOOM, Math.max(1, prev.k * factor))
      if (k === 1) return { k: 1, x: 0, y: 0 }
      const f = k / prev.k
      return { k, x: px - (px - prev.x) * f, y: py - (py - prev.y) * f }
    }),
    panBy: (dx: number, dy: number) => setT(prev => (prev.k === 1 ? prev : { ...prev, x: prev.x + dx, y: prev.y + dy })),
    reset: () => setT({ k: 1, x: 0, y: 0 }),
  }), [t])
}

/** The +, - and reset buttons, drawn in the map's own corner. */
function ZoomControls({ view, w, h }: { view: MapView; w: number; h: number }) {
  const centre: [number, number] = [w / 2, h / 2]
  const btn = (label: string, glyph: string, y: number, act: () => void, disabled: boolean) => (
    <g key={label} role="button" aria-label={label} tabIndex={disabled ? -1 : 0} aria-disabled={disabled || undefined}
      transform={`translate(8, ${y})`} style={{ cursor: disabled ? 'default' : 'pointer', opacity: disabled ? 0.45 : 1 }}
      onClick={e => { e.stopPropagation(); if (!disabled) act() }}
      onPointerDown={e => e.stopPropagation()}
      onDoubleClick={e => e.stopPropagation()}
      onKeyDown={e => { if (!disabled && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); act() } }}>
      <rect width={24} height={24} rx={4} fill="var(--surface)" stroke="var(--border)" />
      <text x={12} y={12.5} textAnchor="middle" dominantBaseline="central" fontSize={15}
        fill="var(--text)" style={{ userSelect: 'none' }}>{glyph}</text>
    </g>
  )
  return (
    <g data-testid="map-zoom-controls">
      {btn('Zoom in', '+', 8, () => view.zoomBy(2, centre), view.k >= MAX_ZOOM)}
      {btn('Zoom out', '−', 36, () => view.zoomBy(0.5, centre), view.k <= 1)}
      {btn('Reset zoom', '⟲', 64, view.reset, view.k === 1 && view.x === 0 && view.y === 0)}
    </g>
  )
}

export { MAP_WRAP_STYLE }

/** SVG that fills its tile. Width/height *attributes* (not only CSS) stop the
 *  viewBox from becoming the intrinsic size that overflow:hidden then clips. */
function prefersContrast(): boolean {
  try { return typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-contrast: more)').matches } catch { return false }
}

export function MapSvg({ w, h, svgRef, children, projection, tiles, credit, view, ...rest }: {
  /** The reader's zoom (useMapBox's `view`): zoom buttons, the wheel, a drag
   *  to pan and a double-click to zoom in. Absent = a fixed map, as before. */
  view?: MapView
  w: number
  h: number
  svgRef?: Ref<SVGSVGElement>
  children?: ReactNode
  /** The map's projection and the org basemap: together they draw the tiles
   *  under the vector layers. Either absent = no basemap, as before. */
  projection?: MapProjection
  tiles?: MapSettings | null
  /** The boundary source's required credit (a pack installed under terms).
   *  Drawn whether or not there is a basemap, bottom-left so it never sits
   *  on the tile attribution. */
  credit?: string | null
} & Omit<SVGProps<SVGSVGElement>, 'width' | 'height' | 'viewBox' | 'ref'>) {
  const inner = useRef<SVGSVGElement | null>(null)
  const setRefs = (el: SVGSVGElement | null) => {
    inner.current = el
    if (typeof svgRef === 'function') svgRef(el)
    else if (svgRef && typeof svgRef === 'object') (svgRef as { current: SVGSVGElement | null }).current = el
  }
  // Screen pixels -> viewBox units (the SVG scales to its tile).
  const toBox = (clientX: number, clientY: number): [number, number] => {
    const r = inner.current?.getBoundingClientRect()
    if (!r || !r.width || !r.height) return [w / 2, h / 2]
    return [(clientX - r.left) / r.width * w, (clientY - r.top) / r.height * h]
  }
  // The wheel zooms around the pointer. Registered non-passive, or its
  // preventDefault is ignored and the page scrolls under the map as well.
  const viewRef = useRef(view)
  viewRef.current = view
  const hasView = !!view
  useEffect(() => {
    const el = inner.current
    if (!el || !hasView) return
    const onWheel = (e: WheelEvent) => {
      const v = viewRef.current
      if (!v) return
      e.preventDefault()
      const r = el.getBoundingClientRect()
      const at: [number, number] = r.width && r.height
        ? [(e.clientX - r.left) / r.width * w, (e.clientY - r.top) / r.height * h] : [w / 2, h / 2]
      v.zoomBy(e.deltaY < 0 ? 1.25 : 0.8, at)
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [hasView, w, h])
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null)
  if (!(w > 8 && h > 8)) return null
  const template = tiles ? ((prefersContrast() && tiles.contrast_tile_url) || tiles.tile_url) : null
  // A .pbf/.mvt template is a VECTOR tile server (no PNGs to show as images):
  // decoded and drawn as paths instead, capped at a zoom extracts carry.
  const vector = isVectorTemplate(template)
  const images = template && projection
    ? tilesFor(projection, w, h, template, vector ? VECTOR_MAX_ZOOM : undefined) : []
  return (
    <svg
      ref={setRefs}
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
      data-zoom={view ? view.k : undefined}
      {...rest}
      // Drag to pan once zoomed in (shift-drag stays the area selection), and
      // a double-click zooms in on the point.
      onPointerDown={view ? e => {
        rest.onPointerDown?.(e)
        if (e.shiftKey || e.button !== 0 || view.k <= 1) return
        drag.current = { x: e.clientX, y: e.clientY, moved: false }
      } : rest.onPointerDown}
      onPointerMove={view ? e => {
        rest.onPointerMove?.(e)
        const d = drag.current
        if (!d) return
        const [ax, ay] = toBox(d.x, d.y)
        const [bx, by] = toBox(e.clientX, e.clientY)
        if (!d.moved && Math.hypot(bx - ax, by - ay) < 3) return
        view.panBy(bx - ax, by - ay)
        drag.current = { x: e.clientX, y: e.clientY, moved: true }
      } : rest.onPointerMove}
      onPointerUp={view ? e => { rest.onPointerUp?.(e); drag.current = null } : rest.onPointerUp}
      onPointerLeave={view ? e => { rest.onPointerLeave?.(e); drag.current = null } : rest.onPointerLeave}
      onDoubleClick={view ? e => { rest.onDoubleClick?.(e); view.zoomBy(2, toBox(e.clientX, e.clientY)) } : rest.onDoubleClick}
    >
      {images.length > 0 && vector && projection && <VectorBasemap tiles={images} projection={projection} />}
      {images.length > 0 && !vector && (
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
      {view && <ZoomControls view={view} w={w} h={h} />}
    </svg>
  )
}
