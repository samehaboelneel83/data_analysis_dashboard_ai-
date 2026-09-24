import { PieChart, Pie, Cell, Label, Tooltip, Legend, ResponsiveContainer, Customized } from 'recharts'
import { TT, fmtStr, getFillFactory, COLORS, fillPattern, PatternDefs } from '../chartUtils'
import type { ChartRendererProps } from './types'
import { legendProps } from './axisOptions'
import { seriesName } from './axisOptions'

export default function DonutChartRenderer({ rows, cfg, rtl, broadcasts, localSelected, onClickPoint, measureFmt, ruleStyles }: ChartRendererProps) {
  const getFill = getFillFactory(broadcasts, localSelected, ruleStyles?.rows)
  const patterns = !!cfg.series_patterns
  // Opt-out: the legend has been on, unconditionally, since this renderer was
  // written -- legendProps already defaults to shown-unless-cfg.legend===false,
  // which is exactly that historical look, so no extra gate is needed here.
  const legend = legendProps(cfg, rtl)
  // Opt-in, the opposite default from the legend above: this renderer has never
  // drawn a percent-of-total label, so an unset config must not suddenly add one.
  const showLabels = cfg.data_labels === true
  // The ring answers "how does this split"; the number in the hole answers "out
  // of how much". Opt-in, like the slice labels above and for the same reason:
  // this renderer has never drawn one, and an unset config must not put a number
  // in the middle of every donut that already exists.
  const showTotal = cfg.donut_total === true
  const total = showTotal
    ? rows.reduce((sum: number, r: { value?: unknown }) =>
        sum + (typeof r.value === 'number' ? r.value : 0), 0)
    : 0
  const totalCaption = (cfg.donut_total_label as string | undefined)
    ?? (cfg.measure as string | undefined) ?? ''
  return (
    <div dir={rtl ? 'rtl' : undefined} style={{ height: '100%' }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Customized component={() => <PatternDefs colors={rows.map((_: any, i: number) => COLORS[i % COLORS.length])} enabled={patterns} />} />
          <Pie data={rows} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius="40%" outerRadius="70%"
            isAnimationActive={false}
            onClick={broadcasts ? (d: any) => onClickPoint(d.name) : undefined}
            style={{ cursor: broadcasts ? 'pointer' : 'default' }}
            label={showLabels ? (({ name, percent }: any) => `${name} ${(percent * 100).toFixed(0)}%`) : false}
            labelLine={false}
          >
            {showTotal && (
              // Anchored to the PIE, not to the tile: a bottom legend shifts
              // the ring upward, and a total centred on the container would sit
              // below the hole it belongs in.
              <Label position="center" content={(props: unknown) => {
                // Recharts types this callback's props as its own internal
                // Props, whose viewBox union includes shapes without cx/cy; the
                // Pie always passes the polar one.
                const { cx = 0, cy = 0 } =
                  ((props as { viewBox?: { cx?: number; cy?: number } }).viewBox) ?? {}
                return (
                  <g>
                    <text x={cx} y={totalCaption ? cy - 4 : cy} textAnchor="middle"
                      dominantBaseline="central" fill="var(--text)"
                      style={{ fontSize: 26, fontWeight: 600 }}>
                      {fmtStr(total, measureFmt)}
                    </text>
                    {totalCaption && (
                      <text x={cx} y={cy + 18} textAnchor="middle" dominantBaseline="central"
                        fill="var(--muted)" style={{ fontSize: 11 }}>
                        {totalCaption}
                      </text>
                    )}
                  </g>
                )
              }} />
            )}
            {rows.map((r: any, i: number) => {
              const s = getFill(r.name, i)
              const fill = patterns && !ruleStyles?.rows?.[i]?.fill ? fillPattern(i, s.fill, true) : s.fill
              return <Cell key={i} fill={fill} opacity={s.opacity} />
            })}
          </Pie>
          <Tooltip contentStyle={TT} formatter={(v: unknown) => [fmtStr(v, measureFmt), seriesName(cfg)]} />
          {legend && <Legend iconType="circle" iconSize={8} {...legend} wrapperStyle={{ fontSize: 11, ...(legend.wrapperStyle ?? {}) }} />}
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}
