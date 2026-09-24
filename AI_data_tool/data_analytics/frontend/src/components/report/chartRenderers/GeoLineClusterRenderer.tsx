import { useMemo, useState } from 'react'
import type { ChartRendererProps } from './types'
import { fmtStr } from '../chartUtils'
import { COUNTRIES, fittedProjection } from '../geo/worldGeometry'
import { MapSvg, MAP_WRAP_STYLE, useMapBox } from '../geo/MapFrame'

/**
 * Origin→destination lines over the world outline. Each row carries both
 * endpoints ({lat, lon, lat2, lon2, name?, value?}); lines are drawn as
 * quadratic arcs lifted toward the pole so parallel routes stay separable,
 * with stroke width sqrt-scaled by value (weight reads as ink, and linear
 * scaling makes a doubled value look quadrupled).
 */
export function GeoLinesRenderer({ rows, measureFmt, broadcasts, localSelected,
                                  onClickPoint, plotW, plotH }: ChartRendererProps) {
  const [hover, setHover] = useState<string | null>(null)
  const { ref, w, h, tiles } = useMapBox(plotW, plotH)
  const padPx = Math.max(16, Math.min(w, h) * 0.1)
  // BOTH ends frame the map -- a route is only visible if its origin and its
  // destination are both on screen.
  const { projection, path } = useMemo(() => {
    const pts: [number, number][] = []
    for (const r of rows as Record<string, unknown>[]) {
      if (typeof r.lat === 'number' && typeof r.lon === 'number') pts.push([r.lon, r.lat])
      if (typeof r.lat2 === 'number' && typeof r.lon2 === 'number') pts.push([r.lon2, r.lat2])
    }
    return fittedProjection(w, h, pts, padPx)
  }, [rows, w, h, padPx, tiles])

  const lines = useMemo(() => {
    const out: { d: string; name: string; value: number }[] = []
    for (const r of rows as Record<string, unknown>[]) {
      if (typeof r.lat !== 'number' || typeof r.lon !== 'number'
        || typeof r.lat2 !== 'number' || typeof r.lon2 !== 'number') continue
      const a = projection([r.lon, r.lat])
      const b = projection([r.lon2, r.lat2])
      if (!a || !b) continue
      const mx = (a[0] + b[0]) / 2
      const lift = Math.min(h * 0.08, Math.hypot(b[0] - a[0], b[1] - a[1]) / 4)
      const my = (a[1] + b[1]) / 2 - lift
      out.push({
        d: `M ${a[0]} ${a[1]} Q ${mx} ${my} ${b[0]} ${b[1]}`,
        name: String(r.name ?? `${r.lat},${r.lon} → ${r.lat2},${r.lon2}`),
        value: typeof r.value === 'number' ? r.value : 1,
      })
    }
    return out
  }, [rows, projection, h])

  const maxV = Math.max(1, ...lines.map(l => l.value))

  return (
    <div ref={ref} style={MAP_WRAP_STYLE}>
      <MapSvg w={w} h={h} projection={projection} tiles={tiles} role="img" aria-label="Line map">
        {COUNTRIES.map(f => (
          <path key={f.properties.name} d={path(f) ?? undefined}
            fill="var(--surface2)" stroke="var(--border)" strokeWidth={0.5} />
        ))}
        {lines.map((l, i) => (
          <path key={i} d={l.d} fill="none" data-line={l.name}
            stroke={localSelected === l.name ? 'var(--text)' : 'var(--accent)'}
            strokeOpacity={hover === l.name || localSelected === l.name ? 1 : 0.65}
            strokeWidth={(localSelected === l.name ? 2 : 0) + 1 + 4 * Math.sqrt(l.value / maxV)}
            strokeLinecap="round"
            data-selected={localSelected === l.name ? 'true' : undefined}
            style={broadcasts ? { cursor: 'pointer' } : undefined}
            onClick={broadcasts ? () => onClickPoint(l.name) : undefined}
            onMouseEnter={() => setHover(l.name)} onMouseLeave={() => setHover(null)} />
        ))}
      </MapSvg>
      {hover && (
        <div style={{ position: 'absolute', top: 8, left: 8, fontSize: 11, background: 'var(--surface)',
          border: '1px solid var(--border)', borderRadius: 6, padding: '4px 8px' }}>
          {hover}{(() => { const l = lines.find(x => x.name === hover); return l && l.value !== 1 ? ` — ${fmtStr(l.value, measureFmt)}` : '' })()}
        </div>
      )}
    </div>
  )
}

/**
 * Grid-cluster map: each marker is one occupied grid cell from
 * shape_geo_clusters ({lat, lon, count, value?}). Radius is sqrt-scaled by the
 * point count; the count renders inside the marker when it fits — the whole
 * point of clustering is knowing how many points a dot stands for.
 */
/* No cross-filter here, deliberately. `shape_geo_clusters` snaps points to a
   lat/lon grid and returns a COUNT per cell -- there is no dimension value
   behind a cluster, so a click has nothing truthful to filter by. Filtering by
   a grid cell the data never names would be a wrong answer dressed as a
   feature; pinned by a test in geoRenderers.test.tsx. */
export function GeoClustersRenderer({ rows, measureFmt, plotW, plotH }: ChartRendererProps) {
  const [hover, setHover] = useState<string | null>(null)
  const { ref, w, h, tiles } = useMapBox(plotW, plotH)
  // Largest bubble is r=30; without that much pad the eastmost cluster (Tokyo
  // in the demo) is drawn on the viewBox edge and the tile clips it.
  const padPx = Math.max(32, Math.min(w, h) * 0.12)
  const { projection, path } = useMemo(() => fittedProjection(w, h,
    (rows as Record<string, unknown>[])
      .filter(r => typeof r.lat === 'number' && typeof r.lon === 'number')
      .map(r => [r.lon as number, r.lat as number] as [number, number]), padPx), [rows, w, h, padPx, tiles])

  const markers = useMemo(() => {
    const out: { x: number; y: number; count: number; value?: number }[] = []
    for (const r of rows as Record<string, unknown>[]) {
      if (typeof r.lat !== 'number' || typeof r.lon !== 'number') continue
      const pt = projection([r.lon, r.lat])
      if (pt) out.push({ x: pt[0], y: pt[1], count: Number(r.count ?? 1),
        value: typeof r.value === 'number' ? r.value : undefined })
    }
    return out
  }, [rows, projection])

  const maxC = Math.max(1, ...markers.map(m => m.count))
  const radius = (c: number) => 8 + 22 * Math.sqrt(c / maxC)

  return (
    <div ref={ref} style={MAP_WRAP_STYLE}>
      <MapSvg w={w} h={h} projection={projection} tiles={tiles} role="img" aria-label="Cluster map">
        {COUNTRIES.map(f => (
          <path key={f.properties.name} d={path(f) ?? undefined}
            fill="var(--surface2)" stroke="var(--border)" strokeWidth={0.5} />
        ))}
        {markers.map((m, i) => (
          <g key={i} data-cluster={m.count}
            onMouseEnter={() => setHover(`${m.count.toLocaleString()} points${m.value != null ? ` — ${fmtStr(m.value, measureFmt)}` : ''}`)}
            onMouseLeave={() => setHover(null)}>
            <circle cx={m.x} cy={m.y} r={radius(m.count)}
              fill="var(--accent)" fillOpacity={0.55} stroke="var(--accent)" strokeWidth={1.5} />
            {radius(m.count) > 11 && (
              <text x={m.x} y={m.y + 3} textAnchor="middle" fontSize={10} fontWeight={700} fill="#fff">
                {m.count > 999 ? `${(m.count / 1000).toFixed(1)}k` : m.count}
              </text>
            )}
          </g>
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
