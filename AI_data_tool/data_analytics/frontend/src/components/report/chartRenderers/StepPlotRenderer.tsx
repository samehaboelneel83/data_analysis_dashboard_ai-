import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Brush, LabelList } from 'recharts'
import { TT, fmtStr } from '../chartUtils'
import type { ChartRendererProps } from './types'
import { xAxisProps, yAxisProps, gridProps, labelListProps, brushProps, chartMargin } from './axisOptions'
import { seriesName } from './axisOptions'

export default function StepPlotRenderer({ rows, cfg, rtl, broadcasts, onClickPoint, measureFmt, plotW, plotH, onBrushChange }: ChartRendererProps) {
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
        <Tooltip contentStyle={TT} formatter={(v: unknown) => [fmtStr(v, measureFmt), seriesName(cfg)]} />
        <Line type="stepAfter" dataKey="value" stroke="var(--accent)" strokeWidth={2} dot={{ fill: 'var(--accent)', r: 3 }}
          activeDot={{ r: 5, fill: 'var(--accent)', stroke: '#fff', strokeWidth: 2 }}>
          {labels && <LabelList {...labels} />}
        </Line>
        {brush && <Brush {...brush} />}
      </LineChart>
    </ResponsiveContainer>
  )
}
