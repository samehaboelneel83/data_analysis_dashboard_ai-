import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { TT, fmtStr, getFillFactory } from '../chartUtils'
import type { ChartRendererProps } from './types'

export default function DonutChartRenderer({ rows, cfg, rtl, broadcasts, localSelected, onClickPoint, measureFmt }: ChartRendererProps) {
  const getFill = getFillFactory(broadcasts, localSelected)
  return (
    <div dir={rtl ? 'rtl' : undefined} style={{ height: '100%' }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie data={rows} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius="40%" outerRadius="70%"
            onClick={broadcasts ? (d: any) => onClickPoint(d.name) : undefined}
            style={{ cursor: broadcasts ? 'pointer' : 'default' }}
          >
            {rows.map((r: any, i: number) => {
              const s = getFill(r.name, i)
              return <Cell key={i} fill={s.fill} opacity={s.opacity} />
            })}
          </Pie>
          <Tooltip contentStyle={TT} formatter={(v: unknown) => [fmtStr(v, measureFmt), cfg.measure ?? 'value']} />
          <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 11 }} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}
