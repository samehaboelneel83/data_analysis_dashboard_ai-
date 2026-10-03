import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ReferenceLine, ResponsiveContainer, Brush, LabelList } from 'recharts'
import { TT, fmtStr, COLORS, seriesColor } from '../chartUtils'
import type { ChartRendererProps } from './types'
import { computeAnalyticsLines } from './analyticsLines'
import { xAxisProps, yAxisProps, gridProps, labelListProps, legendProps, chartMargin, valueTick } from './axisOptions'
import { useChartViewport } from './useChartViewport'
import { seriesName } from './axisOptions'
import { toBarSeries } from './barSeries'
import { ANIMATE_MAX_POINTS } from '../../../lib/pointThinning'

export default function LineChartRenderer({ rows, data, cfg, rtl, broadcasts, onClickPoint, measureFmt, plotW, plotH, onBrushChange }: ChartRendererProps) {
  // Several measures on the value axis arrive as a crosstab, one column per
  // measure (backend services/multi_measure.py): one line each, with a legend.
  const { rows: seriesRows, series } = toBarSeries(data, 'clustered')
  const multi = series.length > 0
  const plotted = multi ? seriesRows : rows
  const analyticsLines = multi ? [] : computeAnalyticsLines(rows, cfg.analytics)
  const grid = gridProps(cfg)
  // A congested axis opens on a readable window with a slider (useChartViewport).
  const view = useChartViewport(cfg, plotted, plotW, { dataKey: multi ? undefined : 'value', onChange: onBrushChange })
  const brush = view.brush
  const labels = multi ? null : labelListProps(cfg, measureFmt, 'value', view.visible.length)
  const legend = multi ? legendProps(cfg, rtl) : null
  const values = multi
    ? seriesRows.flatMap((r: any) => series.map(s => r[s]))
    : rows.map((r: any) => r.value)
  const dots = plotted.length <= ANIMATE_MAX_POINTS
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={plotted} margin={chartMargin(rtl, { top: labels ? 20 : 4, right: 8, bottom: 20, left: 0 })}
        onClick={broadcasts ? (d: any) => d?.activePayload?.[0] && onClickPoint(d.activePayload[0].payload.name) : undefined}
        style={{ cursor: broadcasts ? 'pointer' : 'default' }}
      >
        {grid && <CartesianGrid {...grid} />}
        <XAxis dataKey="name" {...xAxisProps(cfg, rtl, view.visible.map((r: any) => String(r.name)), plotW)} />
        <YAxis {...yAxisProps(cfg, rtl, measureFmt, values, undefined, { height: plotH })} tickFormatter={valueTick(cfg, measureFmt)} />
        <Tooltip contentStyle={TT} formatter={(v: unknown, name: unknown) =>
            [fmtStr(v, measureFmt), multi ? String(name ?? '') : seriesName(cfg)]}
          labelFormatter={(l: unknown) => data?.partial_period?.label != null && String(l) === data.partial_period.label
            ? `${String(l)} (partial — data to ${data.partial_period.through})` : String(l)} />
        {legend && <Legend {...legend} wrapperStyle={{ fontSize: 10 }} />}
        {/* Past a few hundred points a dot per point is a solid band and a
            DOM node each; the line alone reads the same, and the hover dot
            still marks the point under the pointer. */}
        {multi ? series.map((s, i) => (
          <Line key={s} type="monotone" dataKey={s} name={s} stroke={COLORS[i % COLORS.length]} strokeWidth={2}
            isAnimationActive={dots} connectNulls
            dot={dots ? { fill: COLORS[i % COLORS.length], r: 3 } : false}
            activeDot={{ r: 5, fill: COLORS[i % COLORS.length], stroke: '#fff', strokeWidth: 2 }} />
        )) : (
          <Line type="monotone" dataKey="value" stroke={seriesColor(0)} strokeWidth={2}
            isAnimationActive={dots}
            dot={dots ? { fill: seriesColor(0), r: 3 } : false}
            activeDot={{ r: 5, fill: seriesColor(0), stroke: '#fff', strokeWidth: 2 }}
          >
            {labels && <LabelList {...labels} />}
          </Line>
        )}
        {analyticsLines.map((l, i) => (
          <ReferenceLine key={i} y={l.value} stroke={l.color} strokeDasharray="4 4"
            label={{ value: l.label, position: 'insideTopRight', fill: l.color, fontSize: 10 }} />
        ))}
        {brush && <Brush {...brush} />}
      </LineChart>
    </ResponsiveContainer>
  )
}
