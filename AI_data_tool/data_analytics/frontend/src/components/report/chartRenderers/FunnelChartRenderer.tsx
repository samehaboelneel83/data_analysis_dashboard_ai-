import { FunnelChart, Funnel, LabelList, Tooltip, Cell, ResponsiveContainer, Customized } from 'recharts'
import { TT, fmtStr, getFillFactory, COLORS, fillPattern, PatternDefs } from '../chartUtils'
import type { ChartRendererProps } from './types'

export default function FunnelChartRenderer({ rows, cfg, rtl, broadcasts, localSelected, onClickPoint, measureFmt, ruleStyles }: ChartRendererProps) {
  const getFill = getFillFactory(broadcasts, localSelected, ruleStyles?.rows)
  const patterns = !!cfg.series_patterns
  // Opt-out: the segment name has been labelled, unconditionally, since this
  // renderer was written -- an unset config must keep showing it.
  const showLabels = cfg.data_labels !== false
  return (
    <div dir={rtl ? 'rtl' : undefined} style={{ height: '100%' }}>
      <ResponsiveContainer width="100%" height="100%">
        <FunnelChart>
          <Customized component={() => <PatternDefs colors={rows.map((_: any, i: number) => COLORS[i % COLORS.length])} enabled={patterns} />} />
          <Tooltip contentStyle={TT} formatter={(v: unknown) => fmtStr(v, measureFmt)} />
          <Funnel dataKey="value" data={rows} isAnimationActive={false}
            onClick={broadcasts ? (d: any) => onClickPoint(d.name) : undefined}
            style={{ cursor: broadcasts ? 'pointer' : 'default' }}
          >
            {rows.map((r: any, i: number) => {
              const s = getFill(r.name, i)
              // A display-rule fill is an explicit author statement and keeps its
              // solid colour; otherwise a segment takes its palette hatch when enabled
              // -- same rule PieChartRenderer/DonutChartRenderer already apply.
              const fill = patterns && !ruleStyles?.rows?.[i]?.fill ? fillPattern(i, s.fill, true) : s.fill
              return <Cell key={i} fill={fill} opacity={s.opacity} stroke={s.stroke} strokeWidth={s.strokeWidth} />
            })}
            {showLabels && <LabelList dataKey="name" position="right" fill="var(--text)" fontSize={11} />}
          </Funnel>
        </FunnelChart>
      </ResponsiveContainer>
    </div>
  )
}
