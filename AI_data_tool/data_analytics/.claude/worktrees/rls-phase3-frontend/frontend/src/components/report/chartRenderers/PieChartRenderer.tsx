import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'
import { TT, fmtStr, SELECTED_STROKE, getFillFactory } from '../chartUtils'
import type { ChartRendererProps } from './types'

export default function PieChartRenderer({ rows, cfg, rtl, broadcasts, localSelected, onClickPoint, measureFmt }: ChartRendererProps) {
  const getFill = getFillFactory(broadcasts, localSelected)
  return (
    <div dir={rtl ? 'rtl' : undefined} style={{ height: '100%' }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie data={rows} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius="70%"
            onClick={broadcasts ? (d: any) => onClickPoint(d.name) : undefined}
            style={{ cursor: broadcasts ? 'pointer' : 'default' }}
            label={({ name, percent }: any) => `${name} ${(percent * 100).toFixed(0)}%`}
            labelLine={false}
          >
            {rows.map((r: any, i: number) => {
              const s = getFill(r.name, i)
              return <Cell key={i} fill={s.fill} opacity={s.opacity} stroke={localSelected === r.name ? SELECTED_STROKE : 'none'} strokeWidth={s.strokeWidth ?? 0} />
            })}
          </Pie>
          <Tooltip contentStyle={TT} formatter={(v: unknown) => [fmtStr(v, measureFmt), cfg.measure ?? 'value']} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}
