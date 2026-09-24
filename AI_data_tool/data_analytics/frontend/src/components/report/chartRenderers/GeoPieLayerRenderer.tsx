import { useMemo, useState } from 'react'
import type { ChartRendererProps } from './types'
import { fmtStr } from '../chartUtils'
import { COLORS } from '../chartUtils'
import { COUNTRIES, matchCountry, countryCentroid, countryBoundsPoints, fittedProjection } from '../geo/worldGeometry'
import { MapSvg, MAP_WRAP_STYLE, useMapBox } from '../geo/MapFrame'
import GeoLayerStackRenderer from './GeoLayerStackRenderer'

function arcPath(cx: number, cy: number, r: number, a0: number, a1: number): string {
  const x0 = cx + r * Math.cos(a0), y0 = cy + r * Math.sin(a0)
  const x1 = cx + r * Math.cos(a1), y1 = cy + r * Math.sin(a1)
  const large = a1 - a0 > Math.PI ? 1 : 0
  return `M ${cx} ${cy} L ${x0} ${y0} A ${r} ${r} 0 ${large} 1 ${x1} ${y1} Z`
}

/**
 * A pie at each matched country's centroid, showing composition by the slice
 * role. Pie radius sqrt-scales with the location total so AREA carries the
 * magnitude; slice colours follow the theme palette by slice order.
 */
export function GeoPiesRenderer({ data, measureFmt, broadcasts, localSelected,
                                 onClickPoint, plotW, plotH }: ChartRendererProps) {
  const [hover, setHover] = useState<string | null>(null)
  const { ref, w, h, tiles } = useMapBox(plotW, plotH)
  const rows = (data as { rows?: { name: string; total: number; slices: { label: string; value: number }[] }[] })?.rows ?? []
  const padPx = Math.max(32, Math.min(w, h) * 0.12)
  // Framed on the regions that matched, so pies over one country are legible
  // instead of overlapping in a speck.
  const { projection, path } = useMemo(() => fittedProjection(w, h,
    rows.flatMap(r => {
      const f = matchCountry(r.name)
      return f ? countryBoundsPoints(f) : []
    }), padPx), [rows, w, h, padPx, tiles])

  const { pies, unmatched } = useMemo(() => {
    const out: { name: string; total: number; x: number; y: number; slices: { label: string; value: number }[] }[] = []
    // Counted, not silently skipped. This widget places rows by COUNTRY name, so
    // a dataset keyed by province or governorate matches nothing and drew a bare
    // world map with no explanation. The choropleth already reports this; a
    // reader deserves the same answer from every map that can fail this way.
    let unmatched = 0
    for (const r of rows) {
      const f = matchCountry(r.name)
      if (!f) { unmatched++; continue }
      const pt = projection(countryCentroid(f))
      if (pt) out.push({ ...r, x: pt[0], y: pt[1] })
    }
    return { pies: out, unmatched }
  }, [rows, projection])

  const maxT = Math.max(1e-9, ...pies.map(p => p.total))

  return (
    <div ref={ref} style={MAP_WRAP_STYLE}>
      <MapSvg w={w} h={h} projection={projection} tiles={tiles} role="img" aria-label="Pie map">
        {COUNTRIES.map(f => (
          <path key={f.properties.name} d={path(f) ?? undefined}
            fill="var(--surface2)" stroke="var(--border)" strokeWidth={0.5} />
        ))}
        {pies.map(p => {
          const r = 8 + 18 * Math.sqrt(p.total / maxT)
          let angle = -Math.PI / 2
          return (
            <g key={p.name} data-pie={p.name}
              data-selected={localSelected === p.name ? 'true' : undefined}
              style={broadcasts ? { cursor: 'pointer' } : undefined}
              onClick={broadcasts ? () => onClickPoint(p.name) : undefined}
              onMouseEnter={() => setHover(p.name)} onMouseLeave={() => setHover(null)}>
              {p.slices.map((s, i) => {
                const frac = p.total ? s.value / p.total : 0
                const a0 = angle
                angle += frac * 2 * Math.PI
                return (
                  <path key={i} d={arcPath(p.x, p.y, r, a0, angle)}
                    fill={COLORS[i % COLORS.length]} stroke="var(--surface)" strokeWidth={0.75}
                    opacity={hover == null || hover === p.name ? 0.9 : 0.3} />
                )
              })}
            </g>
          )
        })}
      </MapSvg>
      {hover && (() => {
        const p = pies.find(x => x.name === hover)
        if (!p) return null
        return (
          <div style={{ position: 'absolute', top: 8, left: 8, fontSize: 11, background: 'var(--surface)',
            border: '1px solid var(--border)', borderRadius: 6, padding: '6px 10px', lineHeight: 1.6 }}>
            <strong>{p.name}</strong> — {fmtStr(p.total, measureFmt)}
            {p.slices.map((s, i) => (
              <div key={s.label}>
                <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: 2,
                  background: COLORS[i % COLORS.length], marginRight: 5 }} />
                {s.label}: {fmtStr(s.value, measureFmt)}
              </div>
            ))}
          </div>
        )
      })()}
      {unmatched > 0 && (
        <div data-testid="geo-unmatched" style={{ position: 'absolute', bottom: 4, left: 8,
          fontSize: 10, color: 'var(--muted)' }}>
          {unmatched} row{unmatched === 1 ? '' : 's'} did not match a country
        </div>
      )}
    </div>
  )
}

/**
 * Region + coordinate layers on one map: choropleth fills from the region rows,
 * point circles on top. Both layers optional — the shaper degrades to whichever
 * roles are assigned.
 */
export function GeoLayersRenderer(props: ChartRendererProps) {
  // An authored layer stack has its own renderer; the original two-layer
  // widget (one region layer + one point layer) keeps drawing as before.
  if (Array.isArray((props.data as { layers?: unknown })?.layers)) return <GeoLayerStackRenderer {...props} />
  return <TwoLayerMap {...props} />
}

function TwoLayerMap({ data, measureFmt, broadcasts, localSelected,
                       onClickPoint, plotW, plotH }: ChartRendererProps) {
  const [hover, setHover] = useState<string | null>(null)
  const { ref, w, h, tiles } = useMapBox(plotW, plotH)
  const regions = (data as { regions?: { name: string; value: number }[] })?.regions ?? []
  const points = (data as { points?: { lat: number; lon: number; value?: number }[] })?.points ?? []
  // Both layers frame the map: whichever of them the author assigned should fit.
  const { projection, path } = useMemo(() => fittedProjection(w, h, [
    ...regions.flatMap(r => {
      const f = matchCountry(r.name)
      return f ? countryBoundsPoints(f) : []
    }),
    ...points.map(p => [p.lon, p.lat] as [number, number]),
  ]), [regions, points, w, h, tiles])

  const valueByCountry = useMemo(() => {
    const m = new Map<string, number>()
    for (const r of regions) {
      const f = matchCountry(r.name)
      if (f) m.set(f.properties.name, r.value)
    }
    return m
  }, [regions])
  // What the DATA called the region, for the same reason the choropleth keeps
  // it: `region = United States of America` matches no row that says "US".
  const sourceByCountry = useMemo(() => {
    const m = new Map<string, string>()
    for (const r of regions) {
      const f = matchCountry(r.name)
      if (f) m.set(f.properties.name, r.name)
    }
    return m
  }, [regions])
  const maxR = Math.max(1e-9, ...[...valueByCountry.values()])

  const markers = useMemo(() => points
    .map(p => ({ pt: projection([p.lon, p.lat]), value: p.value ?? 1 }))
    .filter(m => m.pt) as { pt: [number, number]; value: number }[], [points, projection])
  const maxP = Math.max(1, ...markers.map(m => m.value))

  return (
    <div ref={ref} style={MAP_WRAP_STYLE}>
      <MapSvg w={w} h={h} projection={projection} tiles={tiles} role="img" aria-label="Layered map">
        {COUNTRIES.map(f => {
          const v = valueByCountry.get(f.properties.name)
          const source = sourceByCountry.get(f.properties.name)
          const t = v != null ? 0.15 + 0.85 * (v / maxR) : 0
          return (
            <path key={f.properties.name} d={path(f) ?? undefined} data-region={v != null ? f.properties.name : undefined}
              fill={v != null ? `color-mix(in srgb, var(--accent) ${Math.round(t * 100)}%, var(--surface2))` : 'var(--surface2)'}
              stroke={source != null && localSelected === source ? 'var(--accent)' : 'var(--border)'}
              strokeWidth={source != null && localSelected === source ? 2.5 : 0.5}
              data-selected={source != null && localSelected === source ? 'true' : undefined}
              style={broadcasts && source != null ? { cursor: 'pointer' } : undefined}
              onClick={broadcasts && source != null ? () => onClickPoint(source) : undefined}
              onMouseEnter={() => v != null && setHover(`${f.properties.name} — ${fmtStr(v, measureFmt)}`)}
              onMouseLeave={() => setHover(null)} />
          )
        })}
        {markers.map((m, i) => (
          <circle key={i} cx={m.pt[0]} cy={m.pt[1]} r={2.5 + 6 * Math.sqrt(m.value / maxP)}
            data-layer-point fill="var(--danger)" fillOpacity={0.75} stroke="#fff" strokeWidth={0.75} />
        ))}
      </MapSvg>
      {hover && (
        <div style={{ position: 'absolute', top: 8, left: 8, fontSize: 11, background: 'var(--surface)',
          border: '1px solid var(--border)', borderRadius: 6, padding: '4px 8px' }}>
          {hover}
        </div>
      )}
    </div>
  )
}

/**
 * Density map: the cluster shaper's grid cells drawn as filled squares, colour
 * intensity by point count — the heat-grid reading of the same aggregation the
 * cluster map sizes bubbles with.
 */
export function GeoDensityRenderer({ rows, data, plotW, plotH }: ChartRendererProps) {
  const { ref, w, h, tiles } = useMapBox(plotW, plotH)
  const cell = (data as { cell_degrees?: number })?.cell_degrees ?? 5
  const cells = (rows as { lat: number; lon: number; count: number }[]).filter(
    r => typeof r.lat === 'number' && typeof r.lon === 'number')
  // The cells are resolved first so the projection can be fitted to them; the
  // grid is what this map is, and it was previously framed on the whole world.
  const { projection, path } = useMemo(() => fittedProjection(w, h,
    cells.map(c => [c.lon, c.lat] as [number, number])), [rows, w, h, tiles])
  const maxC = Math.max(1, ...cells.map(c => c.count))

  return (
    <div ref={ref} style={MAP_WRAP_STYLE}>
      <MapSvg w={w} h={h} projection={projection} tiles={tiles} role="img" aria-label="Density map">
      {COUNTRIES.map(f => (
        <path key={f.properties.name} d={path(f) ?? undefined}
          fill="var(--surface2)" stroke="var(--border)" strokeWidth={0.5} />
      ))}
      {cells.map((c, i) => {
        const tl = projection([c.lon - cell / 2, Math.min(89.9, c.lat + cell / 2)])
        const br = projection([c.lon + cell / 2, Math.max(-89.9, c.lat - cell / 2)])
        if (!tl || !br) return null
        const t = 0.25 + 0.75 * (c.count / maxC)
        return (
          <rect key={i} x={tl[0]} y={tl[1]} width={Math.max(1, br[0] - tl[0])} height={Math.max(1, br[1] - tl[1])}
            data-density-cell={c.count} fill="var(--accent)" opacity={t * 0.8} rx={1}>
            <title>{c.count.toLocaleString()} points</title>
          </rect>
        )
      })}
      </MapSvg>
    </div>
  )
}
