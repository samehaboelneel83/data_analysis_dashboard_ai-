import { useMemo, useState } from 'react'
import type { ChartRendererProps } from './types'

interface NetNode { id: string; x: number; y: number; degree: number; closeness: number; betweenness: number; reach: number; community?: number }
interface NetLink { source: string; target: string; value: number }
interface SuggestedLink { source: string; target: string; score: number; shared_neighbours: number }

const METRICS = ['degree', 'closeness', 'betweenness', 'reach'] as const

/** Community colours. Distinct hues rather than a sequential ramp: community
 *  ids are nominal, and a ramp would imply an order they do not have. */
const COMMUNITY_COLORS = [
  '#6c8fff', '#f0883e', '#3fb950', '#d29922', '#bc8cff', '#39c5cf',
  '#f778ba', '#8b949e',
]

/**
 * Link-analysis graph. Positions and centralities arrive from shape_network
 * (deterministic server-side layout), so this stays a pure draw: node radius
 * encodes the configured centrality metric, link width the aggregated weight.
 * Hovering a node lifts it and its links and shows all four centralities —
 * the metrics ARE the analysis, so they are never more than a hover away.
 */
export default function NetworkGraphRenderer({ data, cfg }: ChartRendererProps) {
  const [hover, setHover] = useState<string | null>(null)
  const nodes: NetNode[] = (data as { nodes?: NetNode[] })?.nodes ?? []
  const links: NetLink[] = (data as { links?: NetLink[] })?.links ?? []
  // Predicted, not observed. Drawn dashed and faint, and never as an ordinary
  // link -- a suggested edge shown like a real one would have the chart assert
  // a relationship the data does not contain.
  const suggested: SuggestedLink[] =
    (data as { suggested_links?: SuggestedLink[] })?.suggested_links ?? []
  const communities = (data as { communities?: number })?.communities ?? 0
  const [showSuggested, setShowSuggested] = useState(false)
  const metric: typeof METRICS[number] = METRICS.includes(cfg.centrality_metric) ? cfg.centrality_metric : 'degree'

  const W = 960, H = 540, PAD = 50
  const pos = useMemo(() => Object.fromEntries(nodes.map(n =>
    [n.id, { x: PAD + n.x * (W - 2 * PAD), y: PAD + n.y * (H - 2 * PAD) }])), [nodes])

  const maxW = Math.max(1, ...links.map(l => l.value))
  const maxM = Math.max(1e-9, ...nodes.map(n => n[metric]))
  const radius = (n: NetNode) => 5 + 14 * Math.sqrt(n[metric] / maxM)
  const touches = (l: NetLink) => hover != null && (l.source === hover || l.target === hover)

  if (nodes.length === 0) {
    return <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--muted)', fontSize: 12 }}>No links to draw</div>
  }
  const hovered = nodes.find(n => n.id === hover)

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: '100%' }} role="img" aria-label="Network graph">
        {links.map((l, i) => {
          const a = pos[l.source], b = pos[l.target]
          if (!a || !b) return null
          return (
            <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y}
              stroke="var(--accent)" strokeOpacity={hover == null ? 0.35 : touches(l) ? 0.9 : 0.08}
              strokeWidth={0.5 + 3 * Math.sqrt(l.value / maxW)} />
          )
        })}
        {showSuggested && suggested.map((l, i) => {
          const a = pos[l.source], b = pos[l.target]
          if (!a || !b) return null
          return (
            <line key={`s${i}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y}
              stroke="var(--muted)" strokeOpacity={0.5} strokeDasharray="4 4"
              strokeWidth={1} />
          )
        })}
        {nodes.map(n => (
          <g key={n.id} data-node={n.id}
            onMouseEnter={() => setHover(n.id)} onMouseLeave={() => setHover(null)}>
            <circle cx={pos[n.id].x} cy={pos[n.id].y} r={radius(n)}
              fill={n.community == null ? 'var(--accent)'
                : COMMUNITY_COLORS[n.community % COMMUNITY_COLORS.length]}
              fillOpacity={hover == null || hover === n.id ? 0.8 : 0.25}
              stroke="var(--surface)" strokeWidth={1.5} />
            <text x={pos[n.id].x} y={pos[n.id].y - radius(n) - 4} textAnchor="middle"
              fontSize={10} fill="var(--text)"
              opacity={hover == null ? (radius(n) > 10 ? 1 : 0) : hover === n.id ? 1 : 0.15}>
              {n.id}
            </text>
          </g>
        ))}
      </svg>
      {(communities > 1 || suggested.length > 0) && (
        <div style={{ position: 'absolute', top: 8, right: 8, fontSize: 10,
          display: 'flex', alignItems: 'center', gap: 8 }}>
          {communities > 1 && (
            <span style={{ color: 'var(--muted)' }}>{communities} communities</span>
          )}
          {suggested.length > 0 && (
            <label style={{ display: 'flex', alignItems: 'center', gap: 4, cursor: 'pointer' }}>
              <input type="checkbox" checked={showSuggested}
                onChange={e => setShowSuggested(e.target.checked)} />
              <span style={{ color: 'var(--muted)' }}>
                Suggested links ({suggested.length})
              </span>
            </label>
          )}
        </div>
      )}
      {hovered && (
        <div style={{ position: 'absolute', top: 8, left: 8, fontSize: 11, background: 'var(--surface)',
          border: '1px solid var(--border)', borderRadius: 6, padding: '6px 10px', lineHeight: 1.6 }}>
          <strong>{hovered.id}</strong>
          {METRICS.map(m => (
            <div key={m} style={{ color: m === metric ? 'var(--accent)' : 'var(--muted)' }}>
              {m}: {hovered[m].toFixed(3)}{m === metric ? ' ← size' : ''}
            </div>
          ))}
          {hovered.community != null && (
            <div style={{ color: COMMUNITY_COLORS[hovered.community % COMMUNITY_COLORS.length] }}>
              community: {hovered.community} ← colour
            </div>
          )}
        </div>
      )}
    </div>
  )
}
