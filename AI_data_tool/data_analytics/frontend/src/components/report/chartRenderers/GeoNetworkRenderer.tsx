import { useMemo, useState } from 'react'
import type { ChartRendererProps } from './types'
import { fmtStr } from '../chartUtils'
import { COUNTRIES, fittedProjection } from '../geo/worldGeometry'
import { MapSvg, MAP_WRAP_STYLE, useMapBox } from '../geo/MapFrame'
import { placeLabels } from '../geo/labelPlacement'

/**
 * The network widget's structure anchored to real geography: nodes at their
 * observed coordinates, straight links weighted by value, node radius by
 * degree. Hovering a node lifts its links and shows its degree — the same
 * emphasis behaviour as the abstract network graph, on a map.
 */
export default function GeoNetworkRenderer({ data, measureFmt, broadcasts,
                                            localSelected, onClickPoint, plotW, plotH }: ChartRendererProps) {
  const [hover, setHover] = useState<string | null>(null)
  const { ref, w, h, tiles } = useMapBox(plotW, plotH)
  const nodes = (data as { nodes?: { id: string; lat: number; lon: number; degree: number }[] })?.nodes ?? []
  const links = (data as { links?: { source: string; target: string; value: number }[] })?.links ?? []
  // Labels sit above the node (up to ~40px). Without pad, London on a world
  // frame is drawn on the viewBox edge and the tile clips the name.
  const padPx = Math.max(40, Math.min(w, h) * 0.12)
  // Framed on the nodes, so a referral network inside one country fills the tile.
  const { projection, path } = useMemo(
    () => fittedProjection(w, h, nodes.map(n => [n.lon, n.lat] as [number, number]), padPx), [nodes, w, h, padPx, tiles])

  const pos = useMemo(() => {
    const m: Record<string, [number, number]> = {}
    for (const n of nodes) {
      const pt = projection([n.lon, n.lat])
      if (pt) m[n.id] = pt
    }
    return m
  }, [nodes, projection])

  const labelPos = useMemo(() => {
    const anchors = nodes.flatMap(n => {
      const p = pos[n.id]
      if (!p) return []
      const r = 4 + 9 * Math.sqrt(n.degree / Math.max(1, ...nodes.map(x => x.degree)))
      return [{ id: n.id, x: p[0], y: p[1] - 10 - r, text: n.id }]
    })
    return placeLabels(anchors)
  }, [nodes, pos])

  const maxW = Math.max(1, ...links.map(l => l.value))
  const maxD = Math.max(1, ...nodes.map(n => n.degree))
  const touches = (l: { source: string; target: string }) =>
    hover != null && (l.source === hover || l.target === hover)

  return (
    <div ref={ref} style={MAP_WRAP_STYLE}>
      <MapSvg w={w} h={h} projection={projection} tiles={tiles} role="img" aria-label="Geographic network">
        {COUNTRIES.map(f => (
          <path key={f.properties.name} d={path(f) ?? undefined}
            fill="var(--surface2)" stroke="var(--border)" strokeWidth={0.5} />
        ))}
        {links.map((l, i) => {
          const a = pos[l.source], b = pos[l.target]
          if (!a || !b) return null
          return (
            <line key={i} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} data-geolink={`${l.source}→${l.target}`}
              stroke="var(--accent)" strokeOpacity={hover == null ? 0.45 : touches(l) ? 0.95 : 0.08}
              strokeWidth={0.75 + 3.5 * Math.sqrt(l.value / maxW)} strokeLinecap="round" />
          )
        })}
        {nodes.map(n => pos[n.id] && (
          <g key={n.id} data-geonode={n.id}
            data-selected={localSelected === n.id ? 'true' : undefined}
            style={broadcasts ? { cursor: 'pointer' } : undefined}
            onClick={broadcasts ? () => onClickPoint(n.id) : undefined}
            onMouseEnter={() => setHover(n.id)} onMouseLeave={() => setHover(null)}>
            <circle cx={pos[n.id][0]} cy={pos[n.id][1]} r={4 + 9 * Math.sqrt(n.degree / maxD)}
              fill="var(--accent)" fillOpacity={hover == null || hover === n.id ? 0.85 : 0.3}
              stroke={localSelected === n.id ? 'var(--text)' : 'var(--surface)'}
              strokeWidth={localSelected === n.id ? 3 : 1.5} />
            <text x={labelPos[n.id]?.x ?? pos[n.id][0]}
              y={labelPos[n.id]?.y ?? pos[n.id][1] - 10 - 9 * Math.sqrt(n.degree / maxD)}
              textAnchor="middle" fontSize={10} fill="var(--text)"
              opacity={hover == null || hover === n.id ? 1 : 0.2}>
              {n.id}
            </text>
          </g>
        ))}
      </MapSvg>
      {hover && (() => {
        const n = nodes.find(x => x.id === hover)
        const linked = links.filter(touches)
        return n && (
          <div style={{ position: 'absolute', top: 8, left: 8, fontSize: 11, background: 'var(--surface)',
            border: '1px solid var(--border)', borderRadius: 6, padding: '6px 10px', lineHeight: 1.6 }}>
            <strong>{n.id}</strong> — {n.degree} link{n.degree === 1 ? '' : 's'}
            {linked.slice(0, 6).map(l => (
              <div key={`${l.source}-${l.target}`} style={{ color: 'var(--muted)' }}>
                {l.source} → {l.target}: {fmtStr(l.value, measureFmt)}
              </div>
            ))}
          </div>
        )
      })()}
    </div>
  )
}
