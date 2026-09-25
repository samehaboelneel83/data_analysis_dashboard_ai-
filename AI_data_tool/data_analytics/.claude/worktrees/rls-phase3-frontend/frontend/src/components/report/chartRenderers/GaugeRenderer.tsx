import { RadialBarChart, RadialBar, PolarAngleAxis, ResponsiveContainer } from 'recharts'
import { fmtStr } from '../chartUtils'
import type { ChartRendererProps } from './types'

export default function GaugeRenderer({ data, measureFmt }: ChartRendererProps) {
  const value: number | null = data?.value ?? null
  const target: number | null = data?.target ?? null

  if (value == null) {
    return <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 12 }}>Configure widget to see data</div>
  }

  const max = target != null && target > 0 ? Math.max(target, value) * 1.1 : (value > 0 ? value * 1.25 : 1)
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0
  const chartData = [{ name: 'value', value: pct, fill: target != null && value >= target ? '#34d399' : '#6c8fff' }]

  return (
    <div style={{ height: '100%', width: '100%', position: 'relative' }}>
      <ResponsiveContainer width="100%" height="100%">
        <RadialBarChart data={chartData} cx="50%" cy="55%" innerRadius="65%" outerRadius="100%" startAngle={180} endAngle={0} barSize={18}>
          <PolarAngleAxis type="number" domain={[0, 100]} angleAxisId={0} tick={false} />
          <RadialBar background dataKey="value" cornerRadius={9} isAnimationActive={false} />
        </RadialBarChart>
      </ResponsiveContainer>
      <div style={{ position: 'absolute', top: '55%', left: '50%', transform: 'translate(-50%, -20%)', textAlign: 'center', pointerEvents: 'none' }}>
        <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--text)' }}>{fmtStr(value, measureFmt)}</div>
        {target != null && <div style={{ fontSize: 11, color: 'var(--muted)' }}>of {fmtStr(target, measureFmt)}</div>}
      </div>
    </div>
  )
}
