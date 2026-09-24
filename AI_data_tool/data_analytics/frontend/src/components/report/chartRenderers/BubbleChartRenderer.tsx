import { ScatterChart, Scatter, ZAxis, XAxis, YAxis, CartesianGrid, Tooltip, Legend, Cell, Line, ResponsiveContainer, LabelList } from 'recharts'
import { COLORS, TT, fmtStr } from '../chartUtils'
import type { ChartRendererProps } from './types'
import { axisTitles, xAxisProps, yAxisProps, gridProps, legendProps, labelListProps, chartMargin } from './axisOptions'

// v1 simplification: when a numeric `color` role is set (no `group`), interpolate a single
// accent-to-warning color ramp by normalized value. No gradient legend is rendered yet.
function colorForValue(v: number, min: number, max: number): string {
  const t = max > min ? (v - min) / (max - min) : 0
  const r = Math.round(108 + t * (251 - 108))
  const g = Math.round(143 + t * (191 - 143))
  const b = Math.round(255 + t * (36 - 255))
  return `rgb(${r},${g},${b})`
}

export default function BubbleChartRenderer({ rows, data, cfg, rtl, broadcasts, localSelected, onClickPoint, measureFmt, measure2Fmt, ruleStyles, plotH }: ChartRendererProps) {
  const groups = Array.from(new Set(rows.map((r: any) => r.group).filter((g: unknown) => g != null)))
  const colorVals = rows.map((r: any) => r.color).filter((c: unknown) => typeof c === 'number')
  const colorMin = colorVals.length ? Math.min(...colorVals) : 0
  const colorMax = colorVals.length ? Math.max(...colorVals) : 1
  // Both axes are measures: x is the first, y is the second. The builders'
  // default (the category on x) would name the wrong thing on each.
  const titles = axisTitles(cfg)
  const grid = gridProps(cfg)
  const legend = legendProps(cfg, rtl)
  const labels = labelListProps(cfg, measure2Fmt, 'y', rows.length)

  // An id-like or non-numeric color role (backend: shape_bubble's color_kind) is a
  // CATEGORY, not a measure -- state_id/student_id painted as a continuous gradient
  // means nothing, and neither does a gradient over text. Same value -> same discrete
  // palette color, keyed by first-seen order, not by row index (two rows with the
  // same category must not get two different colors just because they're far apart).
  const isCategoryColor = data?.color_kind === 'category'
    || (data?.color_kind !== 'measure' && rows.some((r: any) => r.color != null && typeof r.color !== 'number'))
  const colorValueIndex = new Map<string, number>()
  if (isCategoryColor) {
    for (const r of rows as any[]) {
      if (r.color == null) continue
      const key = String(r.color)
      if (!colorValueIndex.has(key)) colorValueIndex.set(key, colorValueIndex.size)
    }
  }

  const fillForUngrouped = (r: any, i: number) => {
    if (isCategoryColor) {
      if (r.color == null) return COLORS[i % COLORS.length]
      return COLORS[(colorValueIndex.get(String(r.color)) ?? 0) % COLORS.length]
    }
    if (typeof r.color === 'number') return colorForValue(r.color, colorMin, colorMax)
    return COLORS[i % COLORS.length]
  }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <ScatterChart margin={chartMargin(rtl, { top: 4, right: 16, bottom: 4, left: 0 })}>
        {grid && <CartesianGrid {...grid} />}
        <XAxis type="number" dataKey="x" name="x" {...xAxisProps(cfg, rtl, undefined, undefined, { title: titles.measure })} tickFormatter={v => fmtStr(v, measureFmt)} />
        {/* allowDecimals forced true after the spread: this axis never set it before, so
            Recharts' own default (true) applied, unlike the builder's false default. */}
        <YAxis type="number" dataKey="y" name="y" {...yAxisProps(cfg, rtl, measure2Fmt, rows.map((r: any) => r.y), undefined, { height: plotH, title: titles.measure2 })} allowDecimals tickFormatter={v => fmtStr(v, measure2Fmt)} />
        <ZAxis type="number" dataKey="size" range={[60, 600]} />
        <Tooltip contentStyle={TT} cursor={{ strokeDasharray: '3 3' }}
          formatter={(v: unknown, name: string) => [name === 'x' ? fmtStr(v, measureFmt) : name === 'y' ? fmtStr(v, measure2Fmt) : String(v), name]} />
        {groups.length > 0 && legend && <Legend {...legend} wrapperStyle={{ fontSize: 11, ...(rtl ? { direction: 'ltr' as const } : {}) }} />}
        {groups.length > 0 ? (
          groups.map((g, gi) => (
            <Scatter key={String(g)} name={String(g)} data={rows.filter((r: any) => r.group === g)} fill={COLORS[gi % COLORS.length]}
              onClick={broadcasts ? (d: any) => onClickPoint(d.name) : undefined}
              style={{ cursor: broadcasts ? 'pointer' : 'default' }}
            >
              {rows.filter((r: any) => r.group === g).map((r: any) => {
                const i = rows.indexOf(r)
                return <Cell key={i} fill={ruleStyles?.rows?.[i]?.fill ?? COLORS[gi % COLORS.length]}
                  opacity={broadcasts && localSelected !== null && localSelected !== r.name ? 0.35 : 0.75} />
              })}
              {labels && <LabelList {...labels} />}
            </Scatter>
          ))
        ) : (
          <Scatter data={rows} name="bubbles"
            onClick={broadcasts ? (d: any) => onClickPoint(d.name) : undefined}
            style={{ cursor: broadcasts ? 'pointer' : 'default' }}
          >
            {rows.map((r: any, i: number) => (
              <Cell key={i} fill={ruleStyles?.rows?.[i]?.fill ?? fillForUngrouped(r, i)} opacity={broadcasts && localSelected !== null && localSelected !== r.name ? 0.35 : 0.75} />
            ))}
            {labels && <LabelList {...labels} />}
          </Scatter>
        )}
        {data?.fit_line && (
          <Line data={data.fit_line} dataKey="y" type="monotone" stroke="var(--muted)" strokeWidth={1.5} strokeDasharray="4 3" dot={false} legendType="none" isAnimationActive={false} />
        )}
      </ScatterChart>
    </ResponsiveContainer>
  )
}
