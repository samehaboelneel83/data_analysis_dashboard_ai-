import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Dot, ResponsiveContainer, LabelList } from 'recharts'
import { TT, fmtStr } from '../chartUtils'
import type { ChartRendererProps } from './types'
import { axisTitles, xAxisProps, yAxisProps, gridProps, labelListProps, chartMargin } from './axisOptions'

export default function NumericSeriesPlotRenderer({ rows, cfg, rtl, measureFmt, measure2Fmt, ruleStyles, plotH }: ChartRendererProps) {
  // Both axes are measures: x is the first, y is the second. The builders'
  // default (the category on x) would name the wrong thing on each.
  const titles = axisTitles(cfg)
  const grid = gridProps(cfg)
  const labels = labelListProps(cfg, measure2Fmt, 'y', rows.length)
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={rows} margin={chartMargin(rtl, { top: 4, right: 8, bottom: 4, left: 0 })}>
        {grid && <CartesianGrid {...grid} />}
        <XAxis dataKey="x" type="number" {...xAxisProps(cfg, rtl, undefined, undefined, { title: titles.measure })} tickFormatter={v => fmtStr(v, measureFmt)} />
        {/* allowDecimals forced true after the spread: this axis never set it before, so
            Recharts' own default (true) applied, unlike the builder's false default. */}
        <YAxis dataKey="y" type="number" {...yAxisProps(cfg, rtl, measure2Fmt, rows.map((r: any) => r.y), undefined, { height: plotH, title: titles.measure2 })} allowDecimals tickFormatter={v => fmtStr(v, measure2Fmt)} />
        <Tooltip contentStyle={TT} formatter={(v: unknown, name: string) => [fmtStr(v, name === 'x' ? measureFmt : measure2Fmt), name]} />
        {/* Every row here is its own (x, y) pair -- shape_xy_numeric is row-level, not a
            time series -- so unlike Area/Line/Step/ComparativeTimeSeries (one continuous
            trend, excluded from rule-fill coverage by design), each dot is a genuine
            per-row mark. <Line> has no <Cell> slot the way <Bar>/<Scatter> do, so the
            per-row fill is resolved through a custom dot renderer instead.
            stroke/strokeWidth are forwarded from `props` (Recharts' renderDots merges
            the <Line>'s own stroke/strokeWidth into the object handed to a custom dot
            renderer) rather than hardcoded, so an unruled dot keeps the same ring the
            old `{ fill, r }` object form got for free -- dropping them left every
            unruled dot's stroke missing. */}
        <Line type="monotone" dataKey="y" stroke="var(--accent)" strokeWidth={2}
          dot={(props: any) => {
            const { key, cx, cy, index, stroke, strokeWidth } = props
            return (
              <Dot key={key ?? index} cx={cx} cy={cy} r={3} stroke={stroke} strokeWidth={strokeWidth}
                fill={ruleStyles?.rows?.[index]?.fill ?? 'var(--accent)'} />
            )
          }}
        >
          {labels && <LabelList {...labels} />}
        </Line>
      </LineChart>
    </ResponsiveContainer>
  )
}
