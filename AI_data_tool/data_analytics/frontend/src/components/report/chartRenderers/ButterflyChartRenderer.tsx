import { BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer, LabelList } from 'recharts'
import { fmtStr, TT } from '../chartUtils'
import type { ChartRendererProps } from './types'
import { axisTitles, xAxisProps, yAxisProps, gridProps, labelListProps } from './axisOptions'

export default function ButterflyChartRenderer({ data, cfg, rtl, measureFmt, measure2Fmt, ruleStyles, plotH }: ChartRendererProps) {
  const rows: { name: string; value?: number; value2?: number }[] = data?.rows ?? []

  if (rows.length === 0) {
    return <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 12 }}>Configure widget to see data</div>
  }

  const chartData = rows.map(r => ({ name: r.name, left: -(Math.abs(r.value ?? 0)), right: Math.abs(r.value2 ?? 0) }))
  // The CATEGORY runs down the side here and the measure along the bottom,
  // so the two titles are the other way round from a bar chart.
  const titles = axisTitles(cfg)
  const grid = gridProps(cfg)
  const leftLabels = labelListProps(cfg, measureFmt, 'left', chartData.length)
  const rightLabels = labelListProps(cfg, measure2Fmt, 'right', chartData.length)

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={chartData} layout="vertical" margin={{ top: 10, right: 20, left: 10, bottom: 10 }}>
        {grid && <CartesianGrid {...grid} />}
        {/* tick/axisLine/tickLine: fix round 1 (Task 9 review) -- these used to be
            hard-pinned to this renderer's historical look ({fontSize:11} tick with no
            fill, axisLine/tickLine forced true, matching Recharts' own untouched defaults
            rather than the shared builder's false/false) AFTER the builder spread, which
            discarded axis_tick_size/axis_tick_color/axis_line/tick_line even though the
            Formatting panel offers 'axes' for `butterfly`. Fixed by making the historical
            values DEFAULTS that config can still win over: with no axis_tick_size/
            axis_tick_color/axis_line/tick_line set, this renders exactly as it always has. */}
        <XAxis type="number" {...xAxisProps(cfg, rtl, undefined, undefined, { title: titles.measure })}
          tick={{ fontSize: cfg.axis_tick_size ?? 11, ...(cfg.axis_tick_color ? { fill: cfg.axis_tick_color } : {}) }}
          axisLine={cfg.axis_line ?? true} tickLine={cfg.tick_line ?? true}
          tickFormatter={v => fmtStr(Math.abs(v), measureFmt)} />
        <YAxis type="category" dataKey="name"
          {...yAxisProps(cfg, rtl, undefined, undefined, undefined,
            { categoryLabels: rows.map((r: any) => String(r.name)), height: plotH,
              title: titles.category })}
          tick={{ fontSize: cfg.axis_tick_size ?? 11, ...(cfg.axis_tick_color ? { fill: cfg.axis_tick_color } : {}) }}
          axisLine={cfg.axis_line ?? true} tickLine={cfg.tick_line ?? true} />
        <Tooltip contentStyle={TT} formatter={(v: any, name: string) =>
          name === 'left' ? [fmtStr(Math.abs(v), measureFmt), 'Left'] : [fmtStr(v, measure2Fmt), 'Right']
        } />
        <ReferenceLine x={0} stroke="var(--border)" />
        <Bar dataKey="left" isAnimationActive={false} radius={3}>
          {chartData.map((_d, i) => <Cell key={i} fill={ruleStyles?.rows?.[i]?.fill ?? '#f87171'} />)}
          {/* left is stored negative purely to draw the bar leftward (see chartData above);
              the tooltip (line 28) and XAxis tickFormatter both display Math.abs, so the
              label must match rather than leak the sign encoding. */}
          {leftLabels && <LabelList {...leftLabels} formatter={(v: unknown) => fmtStr(Math.abs(Number(v)), measureFmt)} />}
        </Bar>
        <Bar dataKey="right" isAnimationActive={false} radius={3}>
          {chartData.map((_d, i) => <Cell key={i} fill={ruleStyles?.rows?.[i]?.fill ?? '#6c8fff'} />)}
          {rightLabels && <LabelList {...rightLabels} />}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
