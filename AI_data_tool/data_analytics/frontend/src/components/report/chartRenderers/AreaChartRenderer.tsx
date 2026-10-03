import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Brush, LabelList } from 'recharts'
import { TT, fmtStr, COLORS } from '../chartUtils'
import type { ChartRendererProps } from './types'
import { xAxisProps, yAxisProps, gridProps, labelListProps, legendProps, chartMargin } from './axisOptions'
import { useChartViewport } from './useChartViewport'
import { seriesName } from './axisOptions'
import { toBarSeries } from './barSeries'

export default function AreaChartRenderer({ rows, data, cfg, rtl, broadcasts, onClickPoint, measureFmt, plotW, plotH, onBrushChange }: ChartRendererProps) {
  const grid = gridProps(cfg)
  // Several measures on the value axis arrive as a crosstab, one column per
  // measure (backend services/multi_measure.py): one area each, with a legend.
  const { rows: seriesRows, series } = toBarSeries(data, 'clustered')
  const multi = series.length > 0
  const plotted = multi ? seriesRows : rows
  // A congested axis opens on a readable window with a slider (useChartViewport).
  const view = useChartViewport(cfg, plotted, plotW, { dataKey: multi ? undefined : 'value', onChange: onBrushChange })
  const brush = view.brush
  const labels = multi ? null : labelListProps(cfg, measureFmt, 'value', view.visible.length)
  const legend = multi ? legendProps(cfg, rtl) : null
  const values = multi
    ? seriesRows.flatMap((r: any) => series.map(s => r[s]))
    : rows.map((r: any) => r.value)
  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={plotted} margin={chartMargin(rtl, { top: labels ? 20 : 4, right: 8, bottom: 20, left: 0 })}
        onClick={broadcasts ? (d: any) => d?.activePayload?.[0] && onClickPoint(d.activePayload[0].payload.name) : undefined}
        style={{ cursor: broadcasts ? 'pointer' : 'default' }}
      >
        {grid && <CartesianGrid {...grid} />}
        <XAxis dataKey="name" {...xAxisProps(cfg, rtl, view.visible.map((r: any) => String(r.name)), plotW)} />
        <YAxis {...yAxisProps(cfg, rtl, measureFmt, values, undefined, { height: plotH })} tickFormatter={v => fmtStr(v, measureFmt)} />
        <Tooltip contentStyle={TT} formatter={(v: unknown, name: unknown) =>
          [fmtStr(v, measureFmt), multi ? String(name ?? '') : seriesName(cfg)]} />
        {legend && <Legend {...legend} wrapperStyle={{ fontSize: 10 }} />}
        {multi ? series.map((s, i) => (
          <Area key={s} type="monotone" dataKey={s} name={s} stroke={COLORS[i % COLORS.length]}
            fill={COLORS[i % COLORS.length]} fillOpacity={0.22} strokeWidth={2} connectNulls />
        )) : (
          <Area type="monotone" dataKey="value" stroke={COLORS[0]} fill={COLORS[0]} fillOpacity={0.35} strokeWidth={2}>
            {labels && <LabelList {...labels} />}
          </Area>
        )}
        {brush && <Brush {...brush} />}
      </AreaChart>
    </ResponsiveContainer>
  )
}
