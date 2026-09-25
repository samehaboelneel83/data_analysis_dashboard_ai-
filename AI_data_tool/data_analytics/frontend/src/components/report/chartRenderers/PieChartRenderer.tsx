import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Customized } from 'recharts'
import { TT, sliceLabel, fmtStr, SELECTED_STROKE, getFillFactory, COLORS, fillPattern, PatternDefs } from '../chartUtils'
import type { ChartRendererProps } from './types'
import { seriesName } from './axisOptions'

export default function PieChartRenderer({ rows, cfg, rtl, broadcasts, localSelected, onClickPoint, measureFmt, ruleStyles }: ChartRendererProps) {
  const getFill = getFillFactory(broadcasts, localSelected, ruleStyles?.rows)
  const patterns = !!cfg.series_patterns
  // Opt-out, not opt-in, because a percent-of-total label next to every slice is
  // this chart's historical always-on look -- unlike the 20 axisOptions-wired
  // Cartesian types, where dataLabels defaults OFF to avoid relabelling widgets
  // nobody touched, here the no-op to avoid is the opposite direction: an unset
  // config must keep showing what every existing pie widget already shows.
  const showLabels = cfg.data_labels !== false
  return (
    <div dir={rtl ? 'rtl' : undefined} style={{ height: '100%' }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Customized component={() => <PatternDefs colors={rows.map((_: any, i: number) => COLORS[i % COLORS.length])} enabled={patterns} />} />
          <Pie data={rows} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius="70%"
            isAnimationActive={false}
            onClick={broadcasts ? (d: any) => onClickPoint(d.name) : undefined}
            style={{ cursor: broadcasts ? 'pointer' : 'default' }}
            label={showLabels ? sliceLabel : false}
            labelLine={false}
          >
            {rows.map((r: any, i: number) => {
              const s = getFill(r.name, i)
              // A display-rule fill is an explicit author statement and keeps its solid
              // colour; otherwise a slice takes its palette-coloured hatch when enabled.
              const fill = patterns && !ruleStyles?.rows?.[i]?.fill ? fillPattern(i, s.fill, true) : s.fill
              return <Cell key={i} fill={fill} opacity={s.opacity} stroke={localSelected === r.name ? SELECTED_STROKE : 'none'} strokeWidth={s.strokeWidth ?? 0} />
            })}
          </Pie>
          <Tooltip contentStyle={TT} formatter={(v: unknown) => [fmtStr(v, measureFmt), seriesName(cfg)]} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}
