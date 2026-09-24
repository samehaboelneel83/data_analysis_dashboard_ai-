import { ComposedChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { TT, fmtStr } from '../chartUtils'
import type { ChartRendererProps } from './types'

export default function DualAxisBarChartRenderer({ rows, cfg, rtl, measureFmt, measure2Fmt }: ChartRendererProps) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={rows} margin={{ top: 4, right: 8, bottom: 20, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis dataKey="name" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} angle={-30} textAnchor="end" interval={0} reversed={rtl} />
        <YAxis yAxisId="left" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} orientation={rtl ? 'right' : 'left'} tickFormatter={v => fmtStr(v, measureFmt)} allowDecimals={false} />
        <YAxis yAxisId="right" orientation={rtl ? 'left' : 'right'} tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={v => fmtStr(v, measure2Fmt)} allowDecimals={false} />
        <Tooltip contentStyle={TT} formatter={(v: unknown, name: string) => [fmtStr(v, name === (cfg.measure2 ?? 'value2') ? measure2Fmt : measureFmt), name]} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Bar yAxisId="left" dataKey="value" name={cfg.measure ?? 'value'} fill="var(--accent)" radius={[3, 3, 0, 0]} />
        <Bar yAxisId="right" dataKey="value2" name={cfg.measure2 ?? 'value2'} fill="#a78bfa" radius={[3, 3, 0, 0]} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}
