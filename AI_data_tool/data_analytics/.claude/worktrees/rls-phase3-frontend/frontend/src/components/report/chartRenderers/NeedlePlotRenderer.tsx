import { ComposedChart, Bar, ReferenceLine, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { TT, fmtStr } from '../chartUtils'
import type { ChartRendererProps } from './types'

export default function NeedlePlotRenderer({ rows, cfg, rtl, broadcasts, onClickPoint, measureFmt }: ChartRendererProps) {
  const baseline = Number(cfg.baseline ?? 0)
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={rows} margin={{ top: 4, right: 8, bottom: 20, left: 0 }}
        onClick={broadcasts ? (d: any) => d?.activePayload?.[0] && onClickPoint(d.activePayload[0].payload.name) : undefined}
        style={{ cursor: broadcasts ? 'pointer' : 'default' }}
      >
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis dataKey="name" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} angle={-30} textAnchor="end" interval={0} reversed={rtl} />
        <YAxis tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} orientation={rtl ? 'right' : 'left'} tickFormatter={v => fmtStr(v, measureFmt)} allowDecimals={false} />
        <Tooltip contentStyle={TT} formatter={(v: unknown) => [fmtStr(v, measureFmt), cfg.measure ?? 'value']} />
        <ReferenceLine y={baseline} stroke="var(--muted)" strokeDasharray="3 3" />
        <Bar dataKey="value" fill="var(--accent)" barSize={3}>
        </Bar>
      </ComposedChart>
    </ResponsiveContainer>
  )
}
