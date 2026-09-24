import { useMemo, useRef, useState } from 'react'
import type { ChartRendererProps } from './types'
import { fmtStr, TT } from '../chartUtils'
import { COUNTRIES, matchCountry, countryCentroid, fittedProjection } from '../geo/worldGeometry'
import { MapSvg, MAP_WRAP_STYLE, useMapBox } from '../geo/MapFrame'

interface Marker { name: string; value: number; x: number; y: number
                   /** Index in the ORIGINAL rows, so a display rule that
                    *  colours the third bar colours the third marker.
                    *  Markers skip unmatched rows, so marker position and
                    *  row position are not the same number. */
                   row: number }

/** The markers inside a drawn circle, by name.

 *  Radius selection is the one gesture a map offers that no other chart can:
 *  "the sites within this circle" is not a value in any column, so it cannot be
 *  expressed as a click. Distance from the CENTRE, never a bounding box -- a
 *  box quietly includes the corners the user drew a circle around and left out.
 *  Pure, and tested as such: the drag that feeds it depends on element
 *  geometry, which jsdom reports as zero. */
export function markersWithin(markers: { name: string; x: number; y: number }[],
                              circle: { cx: number; cy: number; r: number }): string[] {
  if (!(circle.r > 0)) return []
  const out: string[] = []
  for (const m of markers) {
    const dx = m.x - circle.cx
    const dy = m.y - circle.cy
    if (dx * dx + dy * dy <= circle.r * circle.r && !out.includes(m.name)) out.push(m.name)
  }
  return out
}

/**
 * Point and bubble maps on the same world outline. Two data modes:
 *
 *  - lat/lon rows ({lat, lon, name?, value?}) from shape_geo_points -- plotted directly
 *  - series rows ({name, value}) keyed by country -- plotted at the country's centroid,
 *    which is what makes these widgets usable on data that has no coordinate columns
 *
 * `variant` decides the radius: fixed for map_points, sqrt-scaled by value for
 * map_bubbles -- sqrt so AREA is proportional to value; a radius proportional to value
 * quadruples the visual weight of a doubled number.
 */
function GeoPointMapRenderer({ rows, cfg, measureFmt, ruleStyles, variant, broadcasts,
                              localSelected, onClickPoint, plotW, plotH }: ChartRendererProps & { variant: 'points' | 'bubbles' }) {
  const { ref, w, h, tiles } = useMapBox(plotW, plotH)
  const [hover, setHover] = useState<Marker | null>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  //: The circle being drawn, in viewBox units. Null when no drag is in flight.
  const [circle, setCircle] = useState<{ cx: number; cy: number; r: number } | null>(null)

  // Resolved BEFORE the projection, because the projection is now fitted to
  // these coordinates: a map of one governorate should show that governorate,
  // not the globe with a dot on it.
  const { placed, unmatched } = useMemo(() => {
    const placed: { name: string; value: number; coord: [number, number]; row: number }[] = []
    let unmatched = 0
    // The index is carried, not recomputed: an unmatched row is skipped here, so
    // the marker list is shorter than the row list and using a marker's position
    // to look up its rule would shift every rule up by one -- colouring the
    // wrong country, silently, which is the whole failure mode this file's
    // never-fuzzy matching exists to avoid.
    ;(rows as Record<string, unknown>[]).forEach((r, row) => {
      const value = typeof r.value === 'number' ? r.value : 1
      if (typeof r.lat === 'number' && typeof r.lon === 'number') {
        placed.push({ name: String(r.name ?? `${r.lat}, ${r.lon}`), value, coord: [r.lon, r.lat], row })
        return
      }
      const f = matchCountry(r.name)
      if (!f) { unmatched++; return }
      placed.push({ name: f.properties.name, value, coord: countryCentroid(f), row })
    })
    return { placed, unmatched }
  }, [rows])

  /**
   * Author-placed annotations: "our new depot", "the flood line". Read from the
   * widget's own config, never from the data, and kept OUT of `markers` on
   * purpose -- a pin is not a row, so it must not broadcast a filter and must
   * not be caught by the lasso. Filtering the page to a label no row holds
   * would answer every other widget with "no rows" and give the reader nothing
   * to explain it.
   *
   * Coordinates are hand-typed, so a half-filled pin is ordinary rather than
   * exceptional. Non-finite ones are dropped here: d3 throws on a NaN
   * coordinate and would take the whole map down with it.
   */
  const pins = useMemo(() => {
    const raw = (cfg as { pins?: unknown } | undefined)?.pins
    if (!Array.isArray(raw)) return []
    return raw.flatMap((p) => {
      const pin = p as { lat?: unknown; lon?: unknown; label?: unknown }
      const lat = typeof pin.lat === 'number' ? pin.lat : NaN
      const lon = typeof pin.lon === 'number' ? pin.lon : NaN
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) return []
      return [{ label: String(pin.label ?? `${lat}, ${lon}`), coord: [lon, lat] as [number, number] }]
    })
  }, [cfg])

  // Pins join the FIT but not the markers. A pin outside the data's extent
  // would otherwise project off-canvas -- in the DOM, invisible on screen --
  // and an author who placed a pin plainly meant to see it.
  const padPx = Math.max(36, Math.min(w, h) * 0.14)
  const { projection, path } = useMemo(
    () => fittedProjection(w, h, [...placed.map(p => p.coord), ...pins.map(p => p.coord)], padPx),
    [placed, pins, w, h, padPx, tiles])

  const placedPins = useMemo(() => pins.flatMap(p => {
    const pt = projection(p.coord)
    return pt ? [{ label: p.label, x: pt[0], y: pt[1] }] : []
  }), [pins, projection])

  const { markers, maxValue } = useMemo(() => {
    const markers: Marker[] = []
    for (const p of placed) {
      const pt = projection(p.coord)
      if (pt) markers.push({ name: p.name, value: p.value, x: pt[0], y: pt[1], row: p.row })
    }
    return { markers, maxValue: Math.max(1, ...markers.map(m => m.value)) }
  }, [placed, projection])

  const radius = (v: number) =>
    variant === 'bubbles' ? 4 + 24 * Math.sqrt(v / maxValue) : 5

  /** Screen pixels to viewBox units. Returns null when the element has no size
   *  -- jsdom always, and a tile that has not been laid out yet -- because the
   *  conversion divides by the measured width. */
  const toViewBox = (clientX: number, clientY: number): [number, number] | null => {
    const box = svgRef.current?.getBoundingClientRect()
    if (!box || !box.width || !box.height) return null
    return [(clientX - box.left) / box.width * w, (clientY - box.top) / box.height * h]
  }

  return (
    <div ref={ref} style={MAP_WRAP_STYLE}>
      <MapSvg w={w} h={h} projection={projection} tiles={tiles} svgRef={svgRef} role="img"
        aria-label={variant === 'bubbles' ? 'Bubble map' : 'Point map'}
        onMouseDown={broadcasts ? e => {
          // SHIFT-drag, not plain drag: plain dragging is how a reader selects
          // text or scrolls, and taking it over makes the map feel broken.
          if (!e.shiftKey) return
          const at = toViewBox(e.clientX, e.clientY)
          if (at) { e.preventDefault(); setCircle({ cx: at[0], cy: at[1], r: 0 }) }
        } : undefined}
        onMouseMove={circle ? e => {
          const at = toViewBox(e.clientX, e.clientY)
          if (!at) return
          setCircle(c => c && ({ ...c, r: Math.hypot(at[0] - c.cx, at[1] - c.cy) }))
        } : undefined}
        onMouseUp={circle ? () => {
          const names = markersWithin(markers, circle)
          setCircle(null)
          // An empty circle emits nothing. Filtering to an empty set would
          // answer every widget on the page with "no rows", which is a worse
          // outcome than the user's aim being slightly off.
          if (names.length) onClickPoint(names)
        } : undefined}
        onMouseLeave={circle ? () => setCircle(null) : undefined}>
        {COUNTRIES.map(f => (
          <path key={f.properties.name} d={path(f) ?? undefined}
            fill="var(--surface2)" stroke="var(--border)" strokeWidth={0.5} />
        ))}
        {/* Display rules reach the markers: colour everywhere else in the app,
            and an ICON here, which is the one thing a map does that a bar chart
            cannot -- "flag the sites that missed target" is a question about
            WHERE. Both were already computed and carried on `ruleStyles`; this
            renderer simply never read them. */}
        {markers.map((m, i) => {
          const style = ruleStyles?.rows?.[m.row] ?? undefined
          const r = radius(m.value)
          const selected = Array.isArray(localSelected)
            ? (localSelected as unknown[]).includes(m.name)
            : localSelected === m.name
          const hover = (e: React.MouseEvent) => {
            const box = (e.currentTarget as SVGElement).ownerSVGElement!.getBoundingClientRect()
            setHover({ ...m, x: e.clientX - box.left, y: e.clientY - box.top })
          }
          return (
            <g key={i}>
              <circle cx={m.x} cy={m.y} r={r}
                fill={style?.fill ?? 'var(--accent)'} fillOpacity={style?.fill ? 0.85 : 0.6}
                stroke={selected ? 'var(--text)' : (style?.fill ?? 'var(--accent)')}
                strokeWidth={selected ? 3 : 1}
                data-marker={m.name} data-value={m.value}
                data-selected={selected ? 'true' : undefined}
                style={broadcasts ? { cursor: 'pointer' } : undefined}
                onClick={broadcasts ? () => onClickPoint(m.name) : undefined}
                onMouseMove={hover} onMouseLeave={() => setHover(null)} />
              {style?.icon && (
                // Centred on the marker and non-interactive, so it never steals
                // the circle's hover -- the tooltip is how the value is read.
                <text data-marker-icon={m.name} x={m.x} y={m.y}
                  textAnchor="middle" dominantBaseline="central"
                  fontSize={Math.max(10, r)} pointerEvents="none"
                  style={{ userSelect: 'none' }}>{style.icon}</text>
              )}
            </g>
          )
        })}
        {/* Drawn AFTER the markers so an annotation is never hidden under the
            data it annotates, and entirely `pointerEvents: none` -- that is
            what keeps a pin out of the click and hover paths rather than a
            handler that remembers to opt out. */}
        {placedPins.map((p, i) => (
          <g key={`pin-${i}`} pointerEvents="none">
            {/* A teardrop, not a circle: a pin has to read as "placed here by a
                person" against markers that are circles. Drawn from its point,
                so the tip is the coordinate. */}
            {/* No <title>: the label is already drawn below the pin, and a
                tooltip could never fire on a group with pointerEvents none --
                it would only have made the name ambiguous to a screen reader
                and to anything else reading the text twice. */}
            <path data-pin={p.label} data-x={p.x} data-y={p.y}
              d={`M${p.x},${p.y} l-6,-9 a7,7 0 1,1 12,0 z`}
              fill="var(--danger)" stroke="var(--surface)" strokeWidth={1} />
            <circle cx={p.x} cy={p.y - 11} r={2.5} fill="var(--surface)" />
            <text x={p.x} y={p.y + 11} textAnchor="middle" fontSize={10}
              fill="var(--text)" style={{ userSelect: 'none' }}
              stroke="var(--surface)" strokeWidth={3} paintOrder="stroke">
              {p.label}
            </text>
          </g>
        ))}
        {circle && circle.r > 0 && (
          <circle data-selection-circle cx={circle.cx} cy={circle.cy} r={circle.r}
            fill="var(--accent)" fillOpacity={0.12}
            stroke="var(--accent)" strokeWidth={1.5} strokeDasharray="6 4"
            pointerEvents="none" />
        )}
      </MapSvg>
      {broadcasts && markers.length > 0 && (
        <div style={{ position: 'absolute', top: 4, right: 8, fontSize: 10,
          color: 'var(--muted)', pointerEvents: 'none' }}>
          Shift-drag to select an area
        </div>
      )}
      {hover && (
        <div style={{ ...TT, position: 'absolute', left: hover.x + 10, top: hover.y + 10,
          padding: '4px 8px', pointerEvents: 'none' }}>
          {hover.name}: {fmtStr(hover.value, measureFmt)}
        </div>
      )}
      {unmatched > 0 && (
        <div data-testid="geo-unmatched" style={{ position: 'absolute', bottom: 4, left: 8,
          fontSize: 10, color: 'var(--muted)' }}>
          {unmatched} row{unmatched === 1 ? '' : 's'} did not match a country
        </div>
      )}
    </div>
  )
}

/* Registered as two catalog entries rather than one widget with a mode switch, so each
   keeps its own name, icon and defaults in the gallery -- and the variant is decided by
   the widget type the author picked, not by config that could drift. */
export function GeoPointsRenderer(props: ChartRendererProps) {
  return <GeoPointMapRenderer {...props} variant="points" />
}
export function GeoBubblesRenderer(props: ChartRendererProps) {
  return <GeoPointMapRenderer {...props} variant="bubbles" />
}
