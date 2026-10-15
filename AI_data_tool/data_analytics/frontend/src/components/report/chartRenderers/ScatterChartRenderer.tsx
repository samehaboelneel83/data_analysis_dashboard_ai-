import { ScatterChart, Scatter, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LabelList } from 'recharts'
import { TT, fmtStr, seriesColor, EmptyState } from '../chartUtils'
import { useT } from '../../../i18n'
import type { ChartRendererProps } from './types'
import { xAxisProps, yAxisProps, gridProps, labelListProps, chartMargin, valueTick } from './axisOptions'
import { thinPoints, ANIMATE_MAX_POINTS } from '../../../lib/pointThinning'

export default function ScatterChartRenderer({ rows, cfg, rtl, broadcasts, onClickPoint, measureFmt, allFormats, ruleStyles, plotW, plotH }: ChartRendererProps) {
  const t = useT()
  const allPoints = rows.map((r: any) => ({ x: r.x ?? r.name, y: r.y ?? r.value }))
  // C-07: recharts drops every point whose x is not a number, so a text
  // dimension on X drew bare axes and said nothing.
  const numericX = allPoints.some(p => p.x !== null && p.x !== '' && Number.isFinite(Number(p.x)))
  if (allPoints.length > 0 && !numericX) return <EmptyState msg={t('cr.scatterNeedsNumericX')} />
  // Every row is data; only points that would overlap on screen are skipped
  // when DRAWING (lib/pointThinning). Axis ranges use every point.
  const { points: scatterData, index: drawnIndex } = thinPoints(allPoints, plotW, plotH)
  const animate = scatterData.length <= ANIMATE_MAX_POINTS
  const hasRuleFills = !!ruleStyles?.rows
  // C-07: with an X measure (measure2) each point is a category at (X, Y).
  const xFmt = allFormats?.[cfg.x_axis] ?? (cfg.measure2 ? allFormats?.[cfg.measure2] : undefined)
  const yFmt = allFormats?.[cfg.y_axis] ?? measureFmt
  const grid = gridProps(cfg)
  const labels = labelListProps(cfg, yFmt, 'y', scatterData.length)
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ScatterChart margin={chartMargin(rtl, { top: 4, right: 8, bottom: 4, left: 0 })}>
        {grid && <CartesianGrid {...grid} />}
        <XAxis dataKey="x" type="number" {...xAxisProps(cfg, rtl)} tickFormatter={valueTick(cfg, xFmt)} />
        {/* allowDecimals forced true after the spread: this axis never set it before, so
            Recharts' own default (true) applied, unlike the builder's false default. */}
        <YAxis dataKey="y" type="number" {...yAxisProps(cfg, rtl, yFmt, allPoints.map(d => d.y), undefined, { height: plotH })} allowDecimals tickFormatter={valueTick(cfg, yFmt)} />
        <Tooltip contentStyle={TT} formatter={(v: unknown, name: string) => [fmtStr(v, name === 'x' ? xFmt : yFmt), name]} />
        <Scatter data={scatterData} isAnimationActive={animate} fill={seriesColor(0)}
          onClick={broadcasts ? (d: any) => onClickPoint(d.x) : undefined}
          style={{ cursor: broadcasts ? 'pointer' : 'default' }}
        >
          {/* A Cell per point only when display rules colour points: thousands
              of identical Cells cost a component each and draw the same fill. */}
          {hasRuleFills && drawnIndex.map((rowIdx, i) => (
            <Cell key={i} fill={ruleStyles?.rows?.[rowIdx]?.fill ?? seriesColor(0)} />
          ))}
          {labels && <LabelList {...labels} />}
        </Scatter>
      </ScatterChart>
    </ResponsiveContainer>
  )
}
