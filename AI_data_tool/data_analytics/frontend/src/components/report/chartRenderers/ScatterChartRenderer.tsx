import { ScatterChart, Scatter, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LabelList } from 'recharts'
import { TT, fmtStr } from '../chartUtils'
import type { ChartRendererProps } from './types'
import { xAxisProps, yAxisProps, gridProps, labelListProps, chartMargin } from './axisOptions'

export default function ScatterChartRenderer({ rows, cfg, rtl, broadcasts, onClickPoint, measureFmt, allFormats, ruleStyles, plotH }: ChartRendererProps) {
  const scatterData = rows.map((r: any) => ({ x: r.x ?? r.name, y: r.y ?? r.value }))
  const xFmt = allFormats?.[cfg.x_axis]
  const yFmt = allFormats?.[cfg.y_axis] ?? measureFmt
  const grid = gridProps(cfg)
  const labels = labelListProps(cfg, yFmt, 'y', scatterData.length)
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ScatterChart margin={chartMargin(rtl, { top: 4, right: 8, bottom: 4, left: 0 })}>
        {grid && <CartesianGrid {...grid} />}
        <XAxis dataKey="x" type="number" {...xAxisProps(cfg, rtl)} tickFormatter={v => fmtStr(v, xFmt)} />
        {/* allowDecimals forced true after the spread: this axis never set it before, so
            Recharts' own default (true) applied, unlike the builder's false default. */}
        <YAxis dataKey="y" type="number" {...yAxisProps(cfg, rtl, yFmt, scatterData.map(d => d.y), undefined, { height: plotH })} allowDecimals tickFormatter={v => fmtStr(v, yFmt)} />
        <Tooltip contentStyle={TT} formatter={(v: unknown, name: string) => [fmtStr(v, name === 'x' ? xFmt : yFmt), name]} />
        <Scatter data={scatterData}
          onClick={broadcasts ? (d: any) => onClickPoint(d.x) : undefined}
          style={{ cursor: broadcasts ? 'pointer' : 'default' }}
        >
          {scatterData.map((_d, i) => (
            <Cell key={i} fill={ruleStyles?.rows?.[i]?.fill ?? 'var(--accent)'} />
          ))}
          {labels && <LabelList {...labels} />}
        </Scatter>
      </ScatterChart>
    </ResponsiveContainer>
  )
}
