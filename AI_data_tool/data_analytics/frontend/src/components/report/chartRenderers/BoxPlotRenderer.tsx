import { useT } from '../../../i18n'
import { fmtStr, seriesColor } from '../chartUtils'
import { valueTick } from './axisOptions'
import type { ChartRendererProps } from './types'

const MARGIN_TOP = 20
const MARGIN_BOTTOM = 30
// 5.12: the value labels live in an HTML gutter beside the drawing, not in the
// SVG. The SVG stretches to the tile (preserveAspectRatio="none"), so its text
// stretched with it and a 50-unit margin was ~20px on a small tile: salary
// ticks like "38,735.12" were squashed past reading.
const MARGIN_LEFT = 6
const GUTTER_PX = 52
const W = 1000
const H = 400

interface BoxRow { name: string; min: number; q1: number; median: number; q3: number; max: number; outliers: number[] }

export default function BoxPlotRenderer({ data, rtl, measureFmt, cfg }: ChartRendererProps) {
  const t9 = useT()
  // The shared tick formatter, compact by default here: a gutter is narrow.
  const tick = valueTick({ ...(cfg ?? {}), labels_compact: cfg?.labels_compact ?? true }, measureFmt)
  const rows: BoxRow[] = data?.rows ?? []

  if (rows.length === 0) {
    return <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 12 }}>{t9('cr.configure')}</div>
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

  const TICKS = [0, 0.25, 0.5, 0.75, 1]
  return (
    <div style={{ height: '100%', width: '100%', position: 'relative', display: 'flex',
      flexDirection: rtl ? 'row-reverse' : 'row' }}>
      <div aria-hidden data-testid="boxplot-ticks" style={{ position: 'relative', width: GUTTER_PX, flexShrink: 0 }}>
        {TICKS.map(t => {
          const v = yMin + t * yRange
          return (
            <span key={t} style={{ position: 'absolute', insetInlineEnd: 4, top: `${(yToPx(v) / H) * 100}%`,
              transform: 'translateY(-50%)', fontSize: 10, color: 'var(--muted)', whiteSpace: 'nowrap',
              fontVariantNumeric: 'tabular-nums' }}>{tick(v)}</span>
          )
        })}
      </div>
      <div style={{ position: 'relative', flex: 1, minWidth: 0 }}>
      <svg width="100%" height="100%" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ display: 'block' }}>
        {TICKS.map(t => {
          const v = yMin + t * yRange
          const y = yToPx(v)
          return (
            <g key={t}>
              <line x1={MARGIN_LEFT} y1={y} x2={W - 10} y2={y} stroke="var(--border)" strokeWidth={1} strokeDasharray={t === 0 ? undefined : '2 3'} />
            </g>
          )
        })}
        {orderedRows.map((r, i) => {
          const cx = MARGIN_LEFT + slotW * (i + 0.5)
          const yMinPx = yToPx(r.min), yQ1Px = yToPx(r.q1), yMedPx = yToPx(r.median), yQ3Px = yToPx(r.q3), yMaxPx = yToPx(r.max)
          return (
            <g key={r.name}>
              <line x1={cx} y1={yMaxPx} x2={cx} y2={yQ3Px} stroke={seriesColor(0)} strokeWidth={1.5} />
              <line x1={cx} y1={yQ1Px} x2={cx} y2={yMinPx} stroke={seriesColor(0)} strokeWidth={1.5} />
              <line x1={cx - boxW / 4} y1={yMaxPx} x2={cx + boxW / 4} y2={yMaxPx} stroke={seriesColor(0)} strokeWidth={1.5} />
              <line x1={cx - boxW / 4} y1={yMinPx} x2={cx + boxW / 4} y2={yMinPx} stroke={seriesColor(0)} strokeWidth={1.5} />
              <rect x={cx - boxW / 2} y={yQ3Px} width={boxW} height={Math.max(1, yQ1Px - yQ3Px)} fill={seriesColor(0)} fillOpacity={0.25} stroke={seriesColor(0)} strokeWidth={1.5} />
              <line x1={cx - boxW / 2} y1={yMedPx} x2={cx + boxW / 2} y2={yMedPx} stroke={seriesColor(0)} strokeWidth={2} />
              {(r.outliers ?? []).map((o, oi) => (
                <circle key={oi} cx={cx} cy={yToPx(o)} r={2.5} fill="var(--muted)" fillOpacity={0.7} />
              ))}
              <title>{t9('cr.boxTitle', { name: String(r.name), min: fmtStr(r.min, measureFmt), q1: fmtStr(r.q1, measureFmt), median: fmtStr(r.median, measureFmt), q3: fmtStr(r.q3, measureFmt), max: fmtStr(r.max, measureFmt) })}</title>
            </g>
          )
        })}
      </svg>
      {/* C-16: the category names in HTML under the drawing, like the value
          gutter: as SVG text they stretched with the viewBox to ~4px glyphs. */}
      <div data-testid="boxplot-categories" style={{ position: 'absolute', left: 0, right: 0,
        top: `${((H - MARGIN_BOTTOM) / H) * 100}%`, bottom: 0 }}>
        {orderedRows.map((r, i) => (
          <span key={r.name} title={String(r.name)} style={{ position: 'absolute', top: 4,
            left: `${((MARGIN_LEFT + slotW * (i + 0.5)) / W) * 100}%`, transform: 'translateX(-50%)',
            maxWidth: `${(slotW / W) * 100}%`, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            fontSize: 11, color: 'var(--muted)' }}>{r.name}</span>
        ))}
      </div>
      </div>
    </div>
  )
}
