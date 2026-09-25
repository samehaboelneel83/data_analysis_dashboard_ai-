import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell, ResponsiveContainer } from 'recharts'
import { TT, fmtStr, getFillFactory } from '../chartUtils'
import type { ChartRendererProps } from './types'

export default function BarChartRenderer({ rows, cfg, rtl, broadcasts, localSelected, onClickPoint, measureFmt }: ChartRendererProps) {
  const getFill = getFillFactory(broadcasts, localSelected)
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={rows} margin={{ top: 4, right: 8, bottom: 20, left: 0 }}
        onClick={broadcasts ? (d: any) => d?.activePayload?.[0] && onClickPoint(d.activePayload[0].payload.name) : undefined}
        style={{ cursor: broadcasts ? 'pointer' : 'default' }}
      >
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis dataKey="name" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} angle={-30} textAnchor="end" interval={0} reversed={rtl} />
        <YAxis tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} orientation={rtl ? 'right' : 'left'} tickFormatter={v => fmtStr(v, measureFmt)} allowDecimals={false} />
        <Tooltip contentStyle={TT} formatter={(v: unknown) => [fmtStr(v, measureFmt), cfg.measure ?? 'value']} />
        <Bar dataKey="value" radius={[4,4,0,0]}>
          {rows.map((r: any, i: number) => {
            const s = getFill(r.name, i)
            return <Cell key={i} fill={s.fill} opacity={s.opacity} stroke={s.stroke} strokeWidth={s.strokeWidth} />
          })}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
