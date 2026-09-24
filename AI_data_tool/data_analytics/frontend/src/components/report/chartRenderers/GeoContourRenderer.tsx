/**
 * Geo contour (MASTER_PLAN Phase 4 item 5): the density surface the server
 * estimates from coordinates, shaded, with its isolines on top.
 */
import { useMemo } from 'react'
import type { ChartRendererProps } from './types'
import { COUNTRIES, fittedProjection } from '../geo/worldGeometry'
import { MapSvg, MAP_WRAP_STYLE, useMapBox } from '../geo/MapFrame'
import { isolines } from '../../../lib/contours'

interface Grid { west: number; east: number; south: number; north: number; nx: number; ny: number; values: number[] }

export default function GeoContourRenderer({ data, plotW, plotH }: ChartRendererProps) {
  const { ref, w, h, tiles } = useMapBox(plotW, plotH)
  const d = data as { grid?: Grid | null; levels?: number[]; reason?: string; points_used?: number; dropped?: number;
    sampled_from?: number | null; weighted_by?: string | null }
  const g = d?.grid ?? null
  const toLonLat = (x: number, y: number): [number, number] => g
    ? [g.west + (x / (g.nx - 1)) * (g.east - g.west), g.south + (y / (g.ny - 1)) * (g.north - g.south)]
    : [0, 0]
  const { projection, path } = useMemo(() => fittedProjection(w, h,
    g ? [[g.west, g.south], [g.east, g.north]] : []), [g, w, h, tiles])

  const cells = useMemo(() => {
    if (!g) return []
    const out: { d: string; v: number }[] = []
    for (let y = 0; y < g.ny - 1; y++) {
      for (let x = 0; x < g.nx - 1; x++) {
        const v = (g.values[y * g.nx + x] + g.values[y * g.nx + x + 1] + g.values[(y + 1) * g.nx + x] + g.values[(y + 1) * g.nx + x + 1]) / 4
        if (v < 0.05) continue
        const ring = [toLonLat(x, y), toLonLat(x, y + 1), toLonLat(x + 1, y + 1), toLonLat(x + 1, y), toLonLat(x, y)]
        const dd = path({ type: 'Polygon', coordinates: [ring] } as never)
        if (dd) out.push({ d: dd, v })
      }
    }
    return out
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [g, path])

  const lines = useMemo(() => {
    if (!g) return []
    return (d.levels ?? []).map(level => {
      const segs = isolines(g.values, g.nx, g.ny, level)
      const dd = path({ type: 'MultiLineString', coordinates: segs.map(([a, b]) => [toLonLat(...a), toLonLat(...b)]) } as never)
      return { level, d: dd ?? '' }
    })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [g, d?.levels, path])

  if (!g) {
    return <div role="note" style={{ padding: 12, fontSize: 12, color: 'var(--muted)' }}>{d?.reason ?? 'Nothing to map.'}</div>
  }
  return (
    <div ref={ref} style={MAP_WRAP_STYLE}>
      <MapSvg w={w} h={h} projection={projection} tiles={tiles} role="img"
        aria-label={`Density contours of ${d.points_used?.toLocaleString()} located rows`}>
        {COUNTRIES.map(f => <path key={f.properties.name} d={path(f) ?? undefined} fill="var(--surface2)" stroke="var(--border)" strokeWidth={0.4} />)}
        <g data-testid="contour-surface">
          {cells.map((c, i) => <path key={i} d={c.d} fill="var(--accent)" fillOpacity={0.08 + 0.55 * c.v} stroke="none" />)}
        </g>
        <g data-testid="contour-lines" fill="none">
          {lines.map(l => <path key={l.level} d={l.d} stroke="var(--accent)" strokeOpacity={0.35 + 0.6 * l.level} strokeWidth={0.6 + l.level} />)}
        </g>
      </MapSvg>
      <div style={{ position: 'absolute', bottom: 4, left: 8, fontSize: 10, color: 'var(--muted)' }}>
        {d.points_used?.toLocaleString()} located rows{d.weighted_by ? `, weighted by ${d.weighted_by}` : ''}
        {d.dropped ? ` · ${d.dropped.toLocaleString()} without usable coordinates` : ''}
        {d.sampled_from ? ` · surface estimated from a ${d.sampled_from.toLocaleString()}-row sample` : ''}
      </div>
    </div>
  )
}
