import { fmtStr } from '../chartUtils'
import type { ChartRendererProps } from './types'

const MARGIN_TOP = 20
const MARGIN_BOTTOM = 30
const MARGIN_LEFT = 50
const W = 1000
const H = 400

interface BoxRow { name: string; min: number; q1: number; median: number; q3: number; max: number; outliers: number[] }

export default function BoxPlotRenderer({ data, rtl, measureFmt }: ChartRendererProps) {
  const rows: BoxRow[] = data?.rows ?? []

  if (rows.length === 0) {
    return <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 12 }}>Configure widget to see data</div>
  }

  const allVals = rows.flatMap(r => [r.min, r.max, ...(r.outliers ?? [])])
  const yMin = Math.min(...allVals)
  const yMax = Math.max(...allVals)
  const yRange = yMax - yMin || 1
  const plotH = H - MARGIN_TOP - MARGIN_BOTTOM
  const plotW = W - MARGIN_LEFT - 10
  const yToPx = (v: number) => MARGIN_TOP + plotH - ((v - yMin) / yRange) * plotH

  const orderedRows = rtl ? [...rows].reverse() : rows
  const slotW = plotW / orderedRows.length
  const boxW = Math.min(slotW * 0.5, 60)

  return (
    <div style={{ height: '100%', width: '100%' }}>
      <svg width="100%" height="100%" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ display: 'block' }}>
        {[0, 0.25, 0.5, 0.75, 1].map(t => {
          const v = yMin + t * yRange
          const y = yToPx(v)
          return (
            <g key={t}>
              <line x1={MARGIN_LEFT} y1={y} x2={W - 10} y2={y} stroke="var(--border)" strokeWidth={1} strokeDasharray={t === 0 ? undefined : '2 3'} />
              <text x={MARGIN_LEFT - 6} y={y + 3} textAnchor="end" fontSize={9} fill="var(--muted)">{fmtStr(v, measureFmt)}</text>
            </g>
          )
        })}
        {orderedRows.map((r, i) => {
          const cx = MARGIN_LEFT + slotW * (i + 0.5)
          const yMinPx = yToPx(r.min), yQ1Px = yToPx(r.q1), yMedPx = yToPx(r.median), yQ3Px = yToPx(r.q3), yMaxPx = yToPx(r.max)
          return (
            <g key={r.name}>
              <line x1={cx} y1={yMaxPx} x2={cx} y2={yQ3Px} stroke="var(--accent)" strokeWidth={1.5} />
              <line x1={cx} y1={yQ1Px} x2={cx} y2={yMinPx} stroke="var(--accent)" strokeWidth={1.5} />
              <line x1={cx - boxW / 4} y1={yMaxPx} x2={cx + boxW / 4} y2={yMaxPx} stroke="var(--accent)" strokeWidth={1.5} />
              <line x1={cx - boxW / 4} y1={yMinPx} x2={cx + boxW / 4} y2={yMinPx} stroke="var(--accent)" strokeWidth={1.5} />
              <rect x={cx - boxW / 2} y={yQ3Px} width={boxW} height={Math.max(1, yQ1Px - yQ3Px)} fill="var(--accent)" fillOpacity={0.25} stroke="var(--accent)" strokeWidth={1.5} />
              <line x1={cx - boxW / 2} y1={yMedPx} x2={cx + boxW / 2} y2={yMedPx} stroke="var(--accent)" strokeWidth={2} />
              {(r.outliers ?? []).map((o, oi) => (
                <circle key={oi} cx={cx} cy={yToPx(o)} r={2.5} fill="var(--muted)" fillOpacity={0.7} />
              ))}
              <text x={cx} y={H - MARGIN_BOTTOM + 16} textAnchor="middle" fontSize={10} fill="var(--muted)">{r.name}</text>
              <title>{`${r.name}: min ${fmtStr(r.min, measureFmt)}, Q1 ${fmtStr(r.q1, measureFmt)}, median ${fmtStr(r.median, measureFmt)}, Q3 ${fmtStr(r.q3, measureFmt)}, max ${fmtStr(r.max, measureFmt)}`}</title>
            </g>
          )
        })}
      </svg>
    </div>
  )
}
