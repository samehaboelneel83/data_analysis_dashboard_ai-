import { ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { TT, fmtStr } from '../chartUtils'
import type { ChartRendererProps } from './types'

export default function DotPlotRenderer({ rows, cfg, rtl, broadcasts, onClickPoint, measureFmt }: ChartRendererProps) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ScatterChart data={rows} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis type="number" dataKey="value" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} reversed={rtl} tickFormatter={v => fmtStr(v, measureFmt)} />
        <YAxis type="category" dataKey="name" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} orientation={rtl ? 'right' : 'left'} width={90} />
        <Tooltip contentStyle={TT} formatter={(v: unknown) => [fmtStr(v, measureFmt), cfg.measure ?? 'value']} />
        <Scatter data={rows} fill="var(--accent)" shape="circle"
          onClick={broadcasts ? (d: any) => onClickPoint(d.name) : undefined}
          style={{ cursor: broadcasts ? 'pointer' : 'default' }}
        />
      </ScatterChart>
    </ResponsiveContainer>
  )
}
