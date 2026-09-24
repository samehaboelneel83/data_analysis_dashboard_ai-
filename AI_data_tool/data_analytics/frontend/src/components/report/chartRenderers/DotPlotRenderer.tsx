import { ScatterChart, Scatter, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LabelList } from 'recharts'
import { TT, fmtStr } from '../chartUtils'
import type { ChartRendererProps } from './types'
import { axisTitles, xAxisProps, yAxisProps, gridProps, labelListProps } from './axisOptions'
import { seriesName } from './axisOptions'

export default function DotPlotRenderer({ rows, cfg, rtl, broadcasts, onClickPoint, measureFmt, ruleStyles, plotH }: ChartRendererProps) {
  // The CATEGORY runs down the side here and the measure along the bottom,
  // so the two titles are the other way round from a bar chart.
  const titles = axisTitles(cfg)
  const grid = gridProps(cfg)
  const labels = labelListProps(cfg, measureFmt, 'value', rows.length)
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ScatterChart data={rows} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 8 }}>
        {grid && <CartesianGrid {...grid} />}
        <XAxis type="number" dataKey="value" {...xAxisProps(cfg, rtl, undefined, undefined, { title: titles.measure })} tickFormatter={v => fmtStr(v, measureFmt)} />
        <YAxis type="category" dataKey="name"
          {...yAxisProps(cfg, rtl, undefined, undefined, undefined,
            { categoryLabels: rows.map((r: any) => String(r.name)), height: plotH,
              title: titles.category })} />
        <Tooltip contentStyle={TT} formatter={(v: unknown) => [fmtStr(v, measureFmt), seriesName(cfg)]} />
        <Scatter data={rows} shape="circle"
          onClick={broadcasts ? (d: any) => onClickPoint(d.name) : undefined}
          style={{ cursor: broadcasts ? 'pointer' : 'default' }}
        >
          {rows.map((_r: any, i: number) => (
            <Cell key={i} fill={ruleStyles?.rows?.[i]?.fill ?? 'var(--accent)'} />
          ))}
          {labels && <LabelList {...labels} />}
        </Scatter>
      </ScatterChart>
    </ResponsiveContainer>
  )
}
