import { COLORS, EmptyState, fmtStr } from '../chartUtils'
import type { ChartRendererProps } from './types'
import { legendProps } from './axisOptions'

/**
 * A real ribbon chart, Power BI-style: within each period the series stack in
 * RANK order (largest on top), and flowing connectors join each series'
 * segment across adjacent periods — the crossings ARE the story, showing rank
 * changes over time. Hand-rolled SVG: recharts' stacking cannot reorder
 * per-category, which is exactly the capability this widget exists for.
 *
 * Consumes shape_heatmap's matrix result unchanged:
 *   rows_axis (periods, x) × cols_axis (series) with cells[i][j] values.
 * Display rules address rows_axis positions (ruleStyles.rows[i]), painting
 * every segment of that period — the same row semantics the previous
 * stacked-bar rendering used. RTL reverses the period order.
 */
export default function RibbonChartRenderer({ data, cfg, rtl, ruleStyles, broadcasts, onClickPoint }: ChartRendererProps) {
  const rowsAxis: string[] = data?.rows_axis ?? []
  const colsAxis: string[] = data?.cols_axis ?? []
  const cells: (number | null)[][] = data?.cells ?? []
  if (rowsAxis.length === 0 || colsAxis.length === 0) return <EmptyState msg="No data" />

  const W = 640, H = 330, padT = 8, padB = 24, padX = 8
  const plotH = H - padT - padB
  const n = rowsAxis.length
  const colW = (W - padX * 2) / n
  const barW = Math.min(colW * 0.45, 64)
  const segGap = 2

  // Display order of periods: RTL reverses, matching every Cartesian renderer.
  const displayIdx = rtl ? rowsAxis.map((_, i) => n - 1 - i) : rowsAxis.map((_, i) => i)

  const totals = rowsAxis.map((_, i) => colsAxis.reduce((s, _c, j) => s + (cells[i]?.[j] ?? 0), 0))
  const maxTotal = Math.max(...totals.map(t => t || 0), 1e-9)

  // Per period: segments sorted by value desc (the rank ordering), with pixel
  // y-ranges stacked from the top.
  type Seg = { j: number; v: number; y0: number; y1: number }
  const layout: Seg[][] = rowsAxis.map((_, i) => {
    const entries = colsAxis
      .map((_c, j) => ({ j, v: cells[i]?.[j] ?? 0 }))
      .filter(e => e.v != null && e.v > 0)
      .sort((a, b) => b.v - a.v)
    let y = padT
    return entries.map(e => {
      const h = (e.v / maxTotal) * plotH
      const seg = { j: e.j, v: e.v, y0: y, y1: y + h }
      y += h + segGap
      return seg
    })
  })

  const xCenter = (p: number) => padX + p * colW + colW / 2
  const fillFor = (period: number, j: number) =>
    ruleStyles?.rows?.[period]?.fill ?? COLORS[j % COLORS.length]

  const bars: React.ReactNode[] = []
  const ribbons: React.ReactNode[] = []
  displayIdx.forEach((i, p) => {
    for (const seg of layout[i]) {
      bars.push(
        <rect key={`b-${i}-${seg.j}`} className="ribbon-segment"
          data-period={rowsAxis[i]} data-series={colsAxis[seg.j]}
          x={xCenter(p) - barW / 2} y={seg.y0} width={barW} height={Math.max(seg.y1 - seg.y0, 1)}
          rx={2} fill={fillFor(i, seg.j)}
          style={{ cursor: broadcasts ? 'pointer' : 'default' }}
          onClick={broadcasts ? () => onClickPoint(rowsAxis[i]) : undefined}>
          <title>{`${colsAxis[seg.j]} — ${rowsAxis[i]}: ${fmtStr(seg.v, undefined)}`}</title>
        </rect>
      )
    }
    // Connectors to the NEXT displayed period: cubic bands, series colour at
    // half opacity, so crossings read without hiding the bars.
    if (p < displayIdx.length - 1) {
      const iNext = displayIdx[p + 1]
      const xR = xCenter(p) + barW / 2
      const xL = xCenter(p + 1) - barW / 2
      const midX = (xR + xL) / 2
      for (const seg of layout[i]) {
        const next = layout[iNext].find(s => s.j === seg.j)
        if (!next) continue
        ribbons.push(
          <path key={`r-${i}-${seg.j}`} className="ribbon-connector" data-series={colsAxis[seg.j]}
            d={`M ${xR} ${seg.y0} C ${midX} ${seg.y0}, ${midX} ${next.y0}, ${xL} ${next.y0}` +
               ` L ${xL} ${next.y1} C ${midX} ${next.y1}, ${midX} ${seg.y1}, ${xR} ${seg.y1} Z`}
            fill={COLORS[seg.j % COLORS.length]} opacity={0.35}>
            <title>{`${colsAxis[seg.j]}: ${fmtStr(seg.v, undefined)} → ${fmtStr(next.v, undefined)}`}</title>
          </path>
        )
      }
    }
  })

  const legend = legendProps(cfg, rtl)
  return (
    <div dir={rtl ? 'rtl' : undefined} style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {legend && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '2px 10px', justifyContent: 'center', padding: '4px 6px 0', fontSize: 10 }}>
          {colsAxis.map((c, j) => (
            <span key={c} style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
              <span className="ribbon-legend-swatch" style={{ width: 8, height: 8, borderRadius: 2, background: COLORS[j % COLORS.length] }} />
              {c}
            </span>
          ))}
        </div>
      )}
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet"
        style={{ flex: 1, width: '100%', minHeight: 0 }} role="img" aria-label="Ribbon chart">
        {ribbons}
        {bars}
        {/* Label decimation: at most ~10 period labels, always including the
            first and last displayed columns, so 24 months don't collide. */}
        {displayIdx.map((i, p) => {
          const step = Math.max(1, Math.ceil(n / 10))
          if (p % step !== 0 && p !== displayIdx.length - 1) return null
          return (
            <text key={`x-${i}`} x={xCenter(p)} y={H - 8} textAnchor="middle"
              style={{ fontSize: 10, fill: 'var(--muted)' }}>{rowsAxis[i]}</text>
          )
        })}
      </svg>
    </div>
  )
}
