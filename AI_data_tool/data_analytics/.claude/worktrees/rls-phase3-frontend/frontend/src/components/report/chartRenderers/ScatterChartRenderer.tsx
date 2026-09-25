import { ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { TT, fmtStr } from '../chartUtils'
import type { ChartRendererProps } from './types'

export default function ScatterChartRenderer({ rows, cfg, rtl, broadcasts, onClickPoint, measureFmt, allFormats }: ChartRendererProps) {
  const scatterData = rows.map((r: any) => ({ x: r.x ?? r.name, y: r.y ?? r.value }))
  const xFmt = allFormats?.[cfg.x_axis]
  const yFmt = allFormats?.[cfg.y_axis] ?? measureFmt
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ScatterChart margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis dataKey="x" type="number" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} reversed={rtl} tickFormatter={v => fmtStr(v, xFmt)} />
        <YAxis dataKey="y" type="number" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} orientation={rtl ? 'right' : 'left'} tickFormatter={v => fmtStr(v, yFmt)} />
        <Tooltip contentStyle={TT} formatter={(v: unknown, name: string) => [fmtStr(v, name === 'x' ? xFmt : yFmt), name]} />
        <Scatter data={scatterData} fill="var(--accent)"
          onClick={broadcasts ? (d: any) => onClickPoint(d.x) : undefined}
          style={{ cursor: broadcasts ? 'pointer' : 'default' }}
        />
      </ScatterChart>
    </ResponsiveContainer>
  )
}
