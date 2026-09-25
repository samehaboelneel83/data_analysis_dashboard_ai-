import type { ChartRendererProps } from './types'

const W = 1000
const H = 500
const PAD = 40

interface VecRow { x: number; y: number; size: number; direction: number }

export default function VectorPlotRenderer({ data, rtl }: ChartRendererProps) {
  const rows: VecRow[] = data?.rows ?? []

  if (rows.length === 0) {
    return <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 12 }}>Configure widget to see data</div>
  }

  const xs = rows.map(r => r.x), ys = rows.map(r => r.y), sizes = rows.map(r => Math.abs(r.size))
  const xMin = Math.min(...xs), xMax = Math.max(...xs)
  const yMin = Math.min(...ys), yMax = Math.max(...ys)
  const xRange = xMax - xMin || 1, yRange = yMax - yMin || 1
  const maxSize = Math.max(...sizes, 1)
  const plotW = W - PAD * 2, plotH = H - PAD * 2
  const toPxX = (v: number) => PAD + ((rtl ? xMax - v : v - xMin) / xRange) * plotW
  const toPxY = (v: number) => H - PAD - ((v - yMin) / yRange) * plotH
  const maxArrowLen = Math.min(plotW, plotH) / 12

  return (
    <div style={{ height: '100%', width: '100%' }}>
      <svg width="100%" height="100%" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ display: 'block' }}>
        <defs>
          <marker id="vec-arrowhead" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
            <path d="M0,0 L6,3 L0,6 Z" fill="var(--accent)" />
          </marker>
        </defs>
        {rows.map((r, i) => {
          const cx = toPxX(r.x), cy = toPxY(r.y)
          const len = (Math.abs(r.size) / maxSize) * maxArrowLen
          const rad = (rtl ? 180 - r.direction : r.direction) * (Math.PI / 180)
          const dx = Math.cos(rad) * len, dy = -Math.sin(rad) * len
          return (
            <g key={i}>
              <line x1={cx} y1={cy} x2={cx + dx} y2={cy + dy} stroke="var(--accent)" strokeWidth={1.5} markerEnd="url(#vec-arrowhead)" />
              <title>{`(${r.x}, ${r.y}) size ${r.size} @ ${r.direction}°`}</title>
            </g>
          )
        })}
      </svg>
    </div>
  )
}
