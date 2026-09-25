import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell, ResponsiveContainer } from 'recharts'
import { COLORS, TT } from '../chartUtils'
import type { ChartRendererProps } from './types'

function toMs(v: unknown): number {
  if (typeof v === 'number') return v
  const t = Date.parse(String(v))
  return isNaN(t) ? NaN : t
}

export default function ScheduleChartRenderer({ data, rtl }: ChartRendererProps) {
  const rows: { name: string; start: unknown; end: unknown; group?: string }[] = data?.rows ?? []

  if (rows.length === 0) {
    return <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 12 }}>Configure widget to see data</div>
  }

  const parsed = rows.map(r => ({ name: r.name, startMs: toMs(r.start), endMs: toMs(r.end), group: r.group }))
  const validRows = parsed.filter(r => !isNaN(r.startMs) && !isNaN(r.endMs))

  if (validRows.length === 0) {
    return <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 12 }}>Configure widget to see data</div>
  }

  const minStart = Math.min(...validRows.map(r => r.startMs))
  const chartData = validRows.map(r => ({ name: r.name, offset: r.startMs - minStart, span: Math.max(0, r.endMs - r.startMs), group: r.group }))
  const groups = Array.from(new Set(chartData.map(d => d.group).filter((g): g is string => !!g)))
  const colorFor = (g?: string) => (g && groups.length > 0) ? COLORS[groups.indexOf(g) % COLORS.length] : COLORS[0]

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={chartData} layout="vertical" margin={{ top: 10, right: 10, left: 10, bottom: 10 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis type="number" tick={{ fontSize: 11 }} tickFormatter={v => new Date(minStart + v).toLocaleDateString()} reversed={rtl} />
        <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={100} orientation={rtl ? 'right' : 'left'} />
        <Tooltip contentStyle={TT} formatter={(_v: any, _n: string, props: any) =>
          [`${new Date(minStart + props.payload.offset).toLocaleDateString()} → ${new Date(minStart + props.payload.offset + props.payload.span).toLocaleDateString()}`, props.payload.name]
        } />
        <Bar dataKey="offset" stackId="gantt" fill="transparent" isAnimationActive={false} />
        <Bar dataKey="span" stackId="gantt" isAnimationActive={false} radius={3}>
          {chartData.map((d, i) => <Cell key={i} fill={colorFor(d.group)} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
