import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell, ResponsiveContainer, LabelList } from 'recharts'
import { TT, seriesColor } from '../chartUtils'
import type { ChartRendererProps } from './types'
import { axisTitles, xAxisProps, yAxisProps, gridProps, labelListProps, chartMargin, valueTick } from './axisOptions'

export default function HistogramRenderer({ rows, cfg, rtl, ruleStyles, plotW }: ChartRendererProps) {
  // A histogram's x axis IS the measure -- its bins are that column's own
  // values -- and its y axis counts rows, which no column names.
  const titles = axisTitles(cfg)
  const grid = gridProps(cfg)
  // Bar values here are bin counts, not the measure, so no measure format is passed.
  const labels = labelListProps(cfg, undefined, 'value', rows.length)
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={rows} margin={chartMargin(rtl, { top: 4, right: 8, bottom: 24, left: 0 })}>
        {grid && <CartesianGrid {...grid} />}
        {/* interval={0} deliberately overrides the shared decluttering here.
            A histogram's categories are contiguous bins, not arbitrary labels:
            dropping every other one leaves an axis that reads as a different
            binning than the data was cut into. The bin count is already capped
            upstream, so the smear the shared default guards against cannot
            arise. */}
        <XAxis dataKey="name" {...xAxisProps(cfg, rtl, rows.map((r: any) => String(r.name)), plotW,
          // An author's own axis name wins; else the measure the bins are cut from.
          { title: (cfg.x_axis_label as string | undefined) ?? titles.measure })} tick={cfg.axis_ticks === false ? false : { fill: cfg.axis_tick_color ?? 'var(--muted)', fontSize: cfg.axis_tick_size ?? 9 }} interval={0} />
        <YAxis {...yAxisProps(cfg, rtl, undefined, undefined, undefined,
          { title: (cfg.y_axis_label as string | undefined) ?? 'count' })} tickFormatter={valueTick(cfg)} />
        <Tooltip contentStyle={TT} formatter={(v: unknown) => [String(v), 'count']} labelFormatter={(l: unknown) => `Bin: ${l}`} />
        <Bar dataKey="value" radius={[2, 2, 0, 0]}>
          {rows.map((_: any, i: number) => (
            <Cell key={i} fill={ruleStyles?.rows?.[i]?.fill ?? seriesColor(0)} />
          ))}
          {labels && <LabelList {...labels} />}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
