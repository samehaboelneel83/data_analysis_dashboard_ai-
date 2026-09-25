import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell, ResponsiveContainer, LabelList } from 'recharts'
import { fmtStr, TT } from '../chartUtils'
import type { ChartRendererProps } from './types'
import { xAxisProps, yAxisProps, gridProps, labelListProps, chartMargin } from './axisOptions'

interface Bar_ { name: string; start: number; delta: number; end: number }

export default function WaterfallChartRenderer({ data, cfg, rtl, measureFmt, ruleStyles, plotW, plotH }: ChartRendererProps) {
  const bars: Bar_[] = data?.bars ?? []

  if (bars.length === 0) {
    return <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 12 }}>Configure widget to see data</div>
  }

  const chartData = bars.map(b => ({
    name: b.name,
    base: Math.min(b.start, b.end),
    delta: Math.abs(b.end - b.start),
    isIncrease: b.end >= b.start,
    start: b.start, end: b.end,
  }))

  const grid = gridProps(cfg)
  const labels = labelListProps(cfg, measureFmt, 'delta', chartData.length)

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={chartData} margin={chartMargin(rtl, { top: 10, right: 10, left: 0, bottom: 10 })}>
        {grid && <CartesianGrid {...grid} />}
        {/* tick/axisLine/tickLine: fix round 1 (Task 9 review) -- these used to be
            hard-pinned to this renderer's historical look ({fontSize:11} tick, axisLine/
            tickLine forced true, matching Recharts' own untouched defaults rather than the
            shared builder's false/false) AFTER the builder spread, which discarded
            axis_tick_size/axis_tick_color/axis_line/tick_line even though the Formatting
            panel offers 'axes' for `waterfall`. Fixed by making the historical values
            DEFAULTS that config can still win over: with no axis_tick_size/
            axis_tick_color/axis_line/tick_line set, this renders exactly as it always has. */}
        <XAxis dataKey="name" {...xAxisProps(cfg, rtl, chartData.map((d: any) => String(d.name)), plotW)}
          tick={{ fontSize: cfg.axis_tick_size ?? 11, ...(cfg.axis_tick_color ? { fill: cfg.axis_tick_color } : {}) }}
          axisLine={cfg.axis_line ?? true} tickLine={cfg.tick_line ?? true} />
        <YAxis {...yAxisProps(cfg, rtl, measureFmt, bars.flatMap(b => [b.start, b.end]), undefined, { height: plotH })}
          tick={{ fontSize: cfg.axis_tick_size ?? 11, ...(cfg.axis_tick_color ? { fill: cfg.axis_tick_color } : {}) }}
          axisLine={cfg.axis_line ?? true} tickLine={cfg.tick_line ?? true} allowDecimals
          tickFormatter={v => fmtStr(v, measureFmt)} />
        <Tooltip contentStyle={TT} formatter={(v: any, name: string, props: any) =>
          name === 'delta' ? [`${fmtStr(props.payload.start, measureFmt)} → ${fmtStr(props.payload.end, measureFmt)}`, 'Change'] : [v, name]
        } />
        <Bar dataKey="base" stackId="wf" fill="transparent" isAnimationActive={false} />
        <Bar dataKey="delta" stackId="wf" isAnimationActive={false} radius={2}>
          {chartData.map((d, i) => (
            <Cell key={i} fill={ruleStyles?.rows?.[i]?.fill ?? (d.isIncrease ? '#34d399' : '#f87171')} />
          ))}
          {labels && <LabelList {...labels} />}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
