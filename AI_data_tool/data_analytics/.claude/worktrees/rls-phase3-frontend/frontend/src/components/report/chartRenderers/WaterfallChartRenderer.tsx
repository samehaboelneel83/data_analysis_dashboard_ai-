import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell, ResponsiveContainer } from 'recharts'
import { fmtStr, TT } from '../chartUtils'
import type { ChartRendererProps } from './types'

interface Bar_ { name: string; start: number; delta: number; end: number }

export default function WaterfallChartRenderer({ data, rtl, measureFmt }: ChartRendererProps) {
  const bars: Bar_[] = data?.bars ?? []

  if (bars.length === 0) {
    return <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 12 }}>Configure widget to see data</div>
  }

  const chartData = bars.map(b => ({
    name: b.name,
    base: Math.min(b.start, b.end),
    delta: Math.abs(b.end - b.start),
    isIncrease: b.end >= b.start,
    start: b.start, end: b.end,
  }))

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 10 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis dataKey="name" tick={{ fontSize: 11 }} reversed={rtl} />
        <YAxis tick={{ fontSize: 11 }} tickFormatter={v => fmtStr(v, measureFmt)} orientation={rtl ? 'right' : 'left'} />
        <Tooltip contentStyle={TT} formatter={(v: any, name: string, props: any) =>
          name === 'delta' ? [`${fmtStr(props.payload.start, measureFmt)} → ${fmtStr(props.payload.end, measureFmt)}`, 'Change'] : [v, name]
        } />
        <Bar dataKey="base" stackId="wf" fill="transparent" isAnimationActive={false} />
        <Bar dataKey="delta" stackId="wf" isAnimationActive={false} radius={2}>
          {chartData.map((d, i) => <Cell key={i} fill={d.isIncrease ? '#34d399' : '#f87171'} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
