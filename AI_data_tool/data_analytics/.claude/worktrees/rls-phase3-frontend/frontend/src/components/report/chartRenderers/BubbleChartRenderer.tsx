import { ScatterChart, Scatter, ZAxis, XAxis, YAxis, CartesianGrid, Tooltip, Legend, Cell, Line, ResponsiveContainer } from 'recharts'
import { COLORS, TT, fmtStr } from '../chartUtils'
import type { ChartRendererProps } from './types'

// v1 simplification: when a numeric `color` role is set (no `group`), interpolate a single
// accent-to-warning color ramp by normalized value. No gradient legend is rendered yet.
function colorForValue(v: number, min: number, max: number): string {
  const t = max > min ? (v - min) / (max - min) : 0
  const r = Math.round(108 + t * (251 - 108))
  const g = Math.round(143 + t * (191 - 143))
  const b = Math.round(255 + t * (36 - 255))
  return `rgb(${r},${g},${b})`
}

export default function BubbleChartRenderer({ rows, data, rtl, broadcasts, localSelected, onClickPoint, measureFmt, measure2Fmt }: ChartRendererProps) {
  const groups = Array.from(new Set(rows.map((r: any) => r.group).filter((g: unknown) => g != null)))
  const colorVals = rows.map((r: any) => r.color).filter((c: unknown) => typeof c === 'number')
  const colorMin = colorVals.length ? Math.min(...colorVals) : 0
  const colorMax = colorVals.length ? Math.max(...colorVals) : 1

  const fillForUngrouped = (r: any, i: number) => {
    if (typeof r.color === 'number') return colorForValue(r.color, colorMin, colorMax)
    return COLORS[i % COLORS.length]
  }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <ScatterChart margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis type="number" dataKey="x" name="x" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} reversed={rtl} tickFormatter={v => fmtStr(v, measureFmt)} />
        <YAxis type="number" dataKey="y" name="y" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} orientation={rtl ? 'right' : 'left'} tickFormatter={v => fmtStr(v, measure2Fmt)} />
        <ZAxis type="number" dataKey="size" range={[60, 600]} />
        <Tooltip contentStyle={TT} cursor={{ strokeDasharray: '3 3' }}
          formatter={(v: unknown, name: string) => [name === 'x' ? fmtStr(v, measureFmt) : name === 'y' ? fmtStr(v, measure2Fmt) : String(v), name]} />
        {groups.length > 0 && <Legend wrapperStyle={{ fontSize: 11 }} />}
        {groups.length > 0 ? (
          groups.map((g, gi) => (
            <Scatter key={String(g)} name={String(g)} data={rows.filter((r: any) => r.group === g)} fill={COLORS[gi % COLORS.length]}
              onClick={broadcasts ? (d: any) => onClickPoint(d.name) : undefined}
              style={{ cursor: broadcasts ? 'pointer' : 'default' }}
            >
              {rows.filter((r: any) => r.group === g).map((r: any, i: number) => (
                <Cell key={i} opacity={broadcasts && localSelected !== null && localSelected !== r.name ? 0.35 : 0.75} />
              ))}
            </Scatter>
          ))
        ) : (
          <Scatter data={rows} name="bubbles"
            onClick={broadcasts ? (d: any) => onClickPoint(d.name) : undefined}
            style={{ cursor: broadcasts ? 'pointer' : 'default' }}
          >
            {rows.map((r: any, i: number) => (
              <Cell key={i} fill={fillForUngrouped(r, i)} opacity={broadcasts && localSelected !== null && localSelected !== r.name ? 0.35 : 0.75} />
            ))}
          </Scatter>
        )}
        {data?.fit_line && (
          <Line data={data.fit_line} dataKey="y" type="monotone" stroke="var(--muted)" strokeWidth={1.5} strokeDasharray="4 3" dot={false} legendType="none" isAnimationActive={false} />
        )}
      </ScatterChart>
    </ResponsiveContainer>
  )
}
