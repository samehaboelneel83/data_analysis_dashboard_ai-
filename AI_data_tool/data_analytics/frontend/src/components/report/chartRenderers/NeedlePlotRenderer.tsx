import { ComposedChart, Bar, Cell, ReferenceLine, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LabelList } from 'recharts'
import { TT, fmtStr } from '../chartUtils'
import type { ChartRendererProps } from './types'
import { xAxisProps, yAxisProps, gridProps, labelListProps, chartMargin } from './axisOptions'
import { seriesName } from './axisOptions'

export default function NeedlePlotRenderer({ rows, cfg, rtl, broadcasts, onClickPoint, measureFmt, ruleStyles, plotW, plotH }: ChartRendererProps) {
  const baseline = Number(cfg.baseline ?? 0)
  const grid = gridProps(cfg)
  const labels = labelListProps(cfg, measureFmt, 'value', rows.length)
  const values = rows.map((r: any) => Number(r.value)).filter((n: number) => !isNaN(n))
  const observedMin = values.length ? Math.min(...values) : undefined
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={rows} margin={chartMargin(rtl, { top: 4, right: 8, bottom: 20, left: 0 })}
        onClick={broadcasts ? (d: any) => d?.activePayload?.[0] && onClickPoint(d.activePayload[0].payload.name) : undefined}
        style={{ cursor: broadcasts ? 'pointer' : 'default' }}
      >
        {grid && <CartesianGrid {...grid} />}
        <XAxis dataKey="name" {...xAxisProps(cfg, rtl, rows.map((r: any) => String(r.name)), plotW)} />
        <YAxis {...yAxisProps(cfg, rtl, measureFmt, rows.map((r: any) => r.value), observedMin, { height: plotH })} tickFormatter={v => fmtStr(v, measureFmt)} />
        <Tooltip contentStyle={TT} formatter={(v: unknown) => [fmtStr(v, measureFmt), seriesName(cfg)]} />
        <ReferenceLine y={baseline} stroke="var(--muted)" strokeDasharray="3 3" />
        <Bar dataKey="value" barSize={3}>
          {rows.map((_r: any, i: number) => (
            <Cell key={i} fill={ruleStyles?.rows?.[i]?.fill ?? 'var(--accent)'} />
          ))}
          {labels && <LabelList {...labels} />}
        </Bar>
      </ComposedChart>
    </ResponsiveContainer>
  )
}
