import { PieChart, Pie, Cell, Label, Tooltip, Legend, ResponsiveContainer, Customized } from 'recharts'
import { TT, fmtStr, getFillFactory, COLORS, fillPattern, PatternDefs } from '../chartUtils'
import type { ChartRendererProps } from './types'
import { legendProps } from './axisOptions'
import { seriesName } from './axisOptions'

export default function DonutChartRenderer({ rows, cfg, rtl, broadcasts, localSelected, onClickPoint, measureFmt, ruleStyles, plotW }: ChartRendererProps) {
  const getFill = getFillFactory(broadcasts, localSelected, ruleStyles?.rows)
  const patterns = !!cfg.series_patterns
  // Opt-out: the legend has been on, unconditionally, since this renderer was
  // written -- legendProps already defaults to shown-unless-cfg.legend===false,
  // which is exactly that historical look, so no extra gate is needed here.
  // With room beside it, the legend sits to the side as a key with each
  // slice's share -- dot, name, percent -- which is what a donut is read for.
  // Narrow tiles keep it underneath. An explicit position always wins.
  const sideLegend = cfg.legend_position === undefined && !cfg.legend_title && (plotW ?? 0) >= 380
  const legend = legendProps(sideLegend ? { ...cfg, legend_position: 'right' } : cfg, rtl)
  // Opt-in, the opposite default from the legend above: this renderer has never
  // drawn a percent-of-total label, so an unset config must not suddenly add one.
  const showLabels = cfg.data_labels === true
  // The ring answers "how does this split"; the number in the hole answers "out
  // of how much". On unless turned off: the redesign reads every donut this
  // way, and the centre is otherwise empty space.
  const showTotal = cfg.donut_total !== false
  const total = rows.reduce((sum: number, r: { value?: unknown }) =>
    sum + (typeof r.value === 'number' ? r.value : 0), 0)
  const totalCaption = (cfg.donut_total_label as string | undefined)
    ?? (cfg.measure ? `Total ${String(cfg.measure).replace(/_/g, ' ')}` : '')
  const pct = (v: unknown) => total > 0 && typeof v === 'number' ? `${Math.round((v / total) * 100)}%` : ''
  return (
    <div dir={rtl ? 'rtl' : undefined} style={{ height: '100%' }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Customized component={() => <PatternDefs colors={rows.map((_: any, i: number) => COLORS[i % COLORS.length])} enabled={patterns} />} />
          {/* The design's ring: a band about a third of the radius, sized so
              the total in the hole has room and the slices still read. */}
          <Pie data={rows} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius="62%" outerRadius="92%"
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
                      style={{ fontSize: 22, fontWeight: 600, letterSpacing: '-.02em', fontVariantNumeric: 'tabular-nums' }}>
                      {/* A seven-digit total in the hole reads as a barcode; with
                          no format of its own it is shortened (4.82M), and the
                          exact figure stays one hover away in the tooltip. */}
                      {measureFmt || Math.abs(total) < 1e6
                        ? fmtStr(total, measureFmt)
                        : new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 2 }).format(total)}
                    </text>
                    {totalCaption && (
                      <text x={cx} y={cy + 18} textAnchor="middle" dominantBaseline="central"
                        fill="var(--muted)" style={{ fontSize: 11.5 }}>
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
              // A hairline of the card colour between slices, so adjacent
              // hues never bleed into one another.
              return <Cell key={i} fill={fill} opacity={s.opacity} stroke="var(--surface)" strokeWidth={2} />
            })}
          </Pie>
          <Tooltip contentStyle={TT} formatter={(v: unknown) => [fmtStr(v, measureFmt), seriesName(cfg)]} />
          {legend && (sideLegend
            ? <Legend {...legend} wrapperStyle={{ ...(legend.wrapperStyle ?? {}), paddingInlineStart: 12 }}
                content={() => (
                  <ul data-testid="donut-key" style={{ listStyle: 'none', margin: 0, padding: 0,
                    display: 'grid', gridTemplateColumns: 'auto 1fr auto', columnGap: 10, rowGap: 8,
                    alignItems: 'center', fontSize: 12.5, minWidth: 150 }}>
                    {rows.map((r: any, i: number) => (
                      <li key={i} style={{ display: 'contents' }}>
                        {/* Square key, name, then the share in the mono face so
                            the percentages line up as a column. */}
                        <span aria-hidden style={{ inlineSize: 10, blockSize: 10, borderRadius: 3,
                          background: getFill(r.name, i).fill }} />
                        <span style={{ color: 'var(--text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{String(r.name)}</span>
                        <span style={{ fontWeight: 500, textAlign: 'end', fontFamily: 'var(--mono)', fontVariantNumeric: 'tabular-nums', paddingInlineStart: 16 }}>{pct(r.value)}</span>
                      </li>
                    ))}
                  </ul>
                )} />
            // Names in the ink colour, as in the side key: the swatch carries
            // the slice's identity, and pale series colours (yellow, green)
            // are unreadable as text on a white card.
            : <Legend iconType="square" iconSize={9}
                formatter={(value: unknown) => <span style={{ color: 'var(--text)' }}>{String(value)}</span>}
                {...legend} wrapperStyle={{ fontSize: 11, ...(legend.wrapperStyle ?? {}) }} />)}
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}
