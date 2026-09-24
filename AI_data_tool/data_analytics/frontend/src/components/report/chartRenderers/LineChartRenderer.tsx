import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer, Brush, LabelList } from 'recharts'
import { TT, fmtStr } from '../chartUtils'
import type { ChartRendererProps } from './types'
import { computeAnalyticsLines } from './analyticsLines'
import { xAxisProps, yAxisProps, gridProps, labelListProps, brushProps, chartMargin } from './axisOptions'
import { seriesName } from './axisOptions'

export default function LineChartRenderer({ rows, data, cfg, rtl, broadcasts, onClickPoint, measureFmt, plotW, plotH, onBrushChange }: ChartRendererProps) {
  const analyticsLines = computeAnalyticsLines(rows, cfg.analytics)
  const grid = gridProps(cfg)
  const brush = brushProps(cfg, { rows, dataKey: 'value', onChange: onBrushChange })
  const labels = labelListProps(cfg, measureFmt, 'value', rows.length)
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={rows} margin={chartMargin(rtl, { top: 4, right: 8, bottom: 20, left: 0 })}
        onClick={broadcasts ? (d: any) => d?.activePayload?.[0] && onClickPoint(d.activePayload[0].payload.name) : undefined}
        style={{ cursor: broadcasts ? 'pointer' : 'default' }}
      >
        {grid && <CartesianGrid {...grid} />}
        <XAxis dataKey="name" {...xAxisProps(cfg, rtl, rows.map((r: any) => String(r.name)), plotW)} />
        <YAxis {...yAxisProps(cfg, rtl, measureFmt, rows.map((r: any) => r.value), undefined, { height: plotH })} tickFormatter={v => fmtStr(v, measureFmt)} />
        <Tooltip contentStyle={TT} formatter={(v: unknown) => [fmtStr(v, measureFmt), seriesName(cfg)]}
          labelFormatter={(l: unknown) => data?.partial_period?.label != null && String(l) === data.partial_period.label
            ? `${String(l)} (partial — data to ${data.partial_period.through})` : String(l)} />
        <Line type="monotone" dataKey="value" stroke="var(--accent)" strokeWidth={2}
          dot={{ fill: 'var(--accent)', r: 3 }}
          activeDot={{ r: 5, fill: 'var(--accent)', stroke: '#fff', strokeWidth: 2 }}
        >
          {labels && <LabelList {...labels} />}
        </Line>
        {analyticsLines.map((l, i) => (
          <ReferenceLine key={i} y={l.value} stroke={l.color} strokeDasharray="4 4"
            label={{ value: l.label, position: 'insideTopRight', fill: l.color, fontSize: 10 }} />
        ))}
        {brush && <Brush {...brush} />}
      </LineChart>
    </ResponsiveContainer>
  )
}
