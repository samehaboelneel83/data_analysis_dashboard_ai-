import { fmtStr } from '../chartUtils'
import type { ChartRendererProps } from './types'

const MARGIN_TOP = 24
const MARGIN_BOTTOM = 20
const LABEL_HEIGHT = 14

export default function ParallelCoordinatesRenderer({ data, rtl, measureFmt }: ChartRendererProps) {
  const axes: { name: string; min: number; max: number }[] = data?.axes ?? []
  const lines: number[][] = data?.lines ?? []

  if (axes.length < 2) {
    return <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 12 }}>Select at least 2 measures</div>
  }

  const orderedAxes = rtl ? [...axes].reverse() : axes
  const orderedLines = rtl ? lines.map(l => [...l].reverse()) : lines

  return (
    <div style={{ height: '100%', width: '100%' }}>
      <svg width="100%" height="100%" viewBox="0 0 1000 400" preserveAspectRatio="none" style={{ display: 'block' }}>
        {orderedAxes.map((axis, i) => {
          const x = orderedAxes.length === 1 ? 500 : (i / (orderedAxes.length - 1)) * 960 + 20
          return (
            <g key={axis.name}>
              <line x1={x} y1={MARGIN_TOP} x2={x} y2={400 - MARGIN_BOTTOM} stroke="var(--border)" strokeWidth={1} />
              <text x={x} y={MARGIN_TOP - 8} textAnchor="middle" fontSize={10} fill="var(--muted)">{axis.name}</text>
              <text x={x} y={MARGIN_TOP + 10} textAnchor="middle" fontSize={9} fill="var(--muted)">{fmtStr(axis.max, measureFmt)}</text>
              <text x={x} y={400 - MARGIN_BOTTOM + LABEL_HEIGHT} textAnchor="middle" fontSize={9} fill="var(--muted)">{fmtStr(axis.min, measureFmt)}</text>
            </g>
          )
        })}
        {orderedLines.map((line, li) => {
          const points = line.map((norm, i) => {
            const x = orderedAxes.length === 1 ? 500 : (i / (orderedAxes.length - 1)) * 960 + 20
            const y = 400 - MARGIN_BOTTOM - norm * (400 - MARGIN_TOP - MARGIN_BOTTOM)
            return `${x},${y}`
          }).join(' ')
          return (
            <polyline key={li} points={points} fill="none" stroke="var(--accent)" strokeWidth={1} strokeOpacity={0.35} />
          )
        })}
      </svg>
    </div>
  )
}
