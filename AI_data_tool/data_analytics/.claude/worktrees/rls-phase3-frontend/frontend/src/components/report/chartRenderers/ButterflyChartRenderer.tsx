import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer } from 'recharts'
import { fmtStr, TT } from '../chartUtils'
import type { ChartRendererProps } from './types'

export default function ButterflyChartRenderer({ data, rtl, measureFmt, measure2Fmt }: ChartRendererProps) {
  const rows: { name: string; value?: number; value2?: number }[] = data?.rows ?? []

  if (rows.length === 0) {
    return <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 12 }}>Configure widget to see data</div>
  }

  const chartData = rows.map(r => ({ name: r.name, left: -(Math.abs(r.value ?? 0)), right: Math.abs(r.value2 ?? 0) }))

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={chartData} layout="vertical" margin={{ top: 10, right: 20, left: 10, bottom: 10 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis type="number" tick={{ fontSize: 11 }} tickFormatter={v => fmtStr(Math.abs(v), measureFmt)} reversed={rtl} />
        <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={100} orientation={rtl ? 'right' : 'left'} />
        <Tooltip contentStyle={TT} formatter={(v: any, name: string) =>
          name === 'left' ? [fmtStr(Math.abs(v), measureFmt), 'Left'] : [fmtStr(v, measure2Fmt), 'Right']
        } />
        <ReferenceLine x={0} stroke="var(--border)" />
        <Bar dataKey="left" fill="#f87171" isAnimationActive={false} radius={3} />
        <Bar dataKey="right" fill="#6c8fff" isAnimationActive={false} radius={3} />
      </BarChart>
    </ResponsiveContainer>
  )
}
