import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ReferenceLine, ReferenceDot, ResponsiveContainer, Brush, LabelList } from 'recharts'
import { TT, fmtStr, COLORS, seriesColor } from '../chartUtils'
import type { ChartRendererProps } from './types'
import { computeAnalyticsLines } from './analyticsLines'
import { xAxisProps, yAxisProps, gridProps, labelListProps, legendProps, chartMargin, valueTick } from './axisOptions'
import { useChartViewport } from './useChartViewport'
import { seriesName } from './axisOptions'
import { toBarSeries } from './barSeries'
import { ANIMATE_MAX_POINTS } from '../../../lib/pointThinning'
import { useT } from '../../../i18n'
import { takeawayText, type SaidI18n } from '../../../lib/readbackText'

export default function LineChartRenderer({ rows, data, cfg, rtl, broadcasts, onClickPoint, measureFmt, plotW, plotH, onBrushChange }: ChartRendererProps) {
  // Several measures on the value axis arrive as a crosstab, one column per
  // measure (backend services/multi_measure.py): one line each, with a legend.
  const { rows: seriesRows, series } = toBarSeries(data, 'clustered')
  const multi = series.length > 0
  const plotted = multi ? seriesRows : rows
  const analyticsLines = multi ? [] : computeAnalyticsLines(rows, cfg.analytics)
  const grid = gridProps(cfg)
  // A congested axis opens on a readable window with a slider (useChartViewport).
  // A line that is READ shows its whole history: what it marks -- a shift, a
  // period outside its range -- may be anywhere, and a window that opens on
  // the last few periods hid 22 of 24 marks (browser check, 2026-10-11).
  const read = !multi && (data?.change_point != null || (Array.isArray(data?.notes) && data.notes.length > 0)
    || rows.some((r: any) => r?.lo != null && r?.hi != null))
  const view = useChartViewport(read && cfg.overview_axis == null ? { ...cfg, overview_axis: false } : cfg,
    plotted, plotW, { dataKey: multi ? undefined : 'value', onChange: onBrushChange })
  const brush = view.brush
  const labels = multi ? null : labelListProps(cfg, measureFmt, 'value', view.visible.length)
  const legend = multi ? legendProps(cfg, rtl) : null
  const values = multi
    ? seriesRows.flatMap((r: any) => series.map(s => r[s]))
    : rows.map((r: any) => r.value)
  const dots = plotted.length <= ANIMATE_MAX_POINTS
  // A line that is READ (server: widget_data.read_timeline): the range each
  // period's own history made likely, the periods outside it, and the place
  // the level changed. Drawn only when the server sent them.
  const banded = !multi && rows.some((r: any) => r?.lo != null && r?.hi != null)
  const changeAt = !multi ? (data?.change_point?.period as string | undefined) : undefined
  const flagged = (payload: any) => payload?.anomaly === 'above' || payload?.anomaly === 'below'
  // Notes pinned to their periods (server: widget_data.timeline_notes): a
  // number on the line, the sentence under the chart.
  const tr = useT()
  const notes: { n: number; period: string; kind: string; text: string; text_i18n?: SaidI18n | null; value?: number | null }[] =
    !multi && cfg.timeline_notes !== false && Array.isArray(data?.notes) ? data.notes : []
  const chart = (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={plotted} margin={chartMargin(rtl, { top: labels ? 20 : 4, right: 8, bottom: 20, left: 0 })}
        onClick={broadcasts ? (d: any) => d?.activePayload?.[0] && onClickPoint(d.activePayload[0].payload.name) : undefined}
        style={{ cursor: broadcasts ? 'pointer' : 'default' }}
      >
        {grid && <CartesianGrid {...grid} />}
        <XAxis dataKey="name" {...xAxisProps(cfg, rtl, view.visible.map((r: any) => String(r.name)), plotW)} />
        <YAxis {...yAxisProps(cfg, rtl, measureFmt, values, undefined, { height: plotH })} tickFormatter={valueTick(cfg, measureFmt)} />
        <Tooltip contentStyle={TT} formatter={(v: unknown, name: unknown) =>
            [fmtStr(v, measureFmt), multi ? String(name ?? '')
              : name === 'lo' ? 'expected at least' : name === 'hi' ? 'expected at most' : seriesName(cfg)]}
          labelFormatter={(l: unknown) => data?.partial_period?.label != null && String(l) === data.partial_period.label
            ? `${String(l)} (partial — data to ${data.partial_period.through})` : String(l)} />
        {legend && <Legend {...legend} wrapperStyle={{ fontSize: 10 }} />}
        {/* Past a few hundred points a dot per point is a solid band and a
            DOM node each; the line alone reads the same, and the hover dot
            still marks the point under the pointer. */}
        {multi ? series.map((s, i) => (
          <Line key={s} type="monotone" dataKey={s} name={s} stroke={COLORS[i % COLORS.length]} strokeWidth={2}
            isAnimationActive={dots} connectNulls
            dot={dots ? { fill: COLORS[i % COLORS.length], r: 3 } : false}
            activeDot={{ r: 5, fill: COLORS[i % COLORS.length], stroke: '#fff', strokeWidth: 2 }} />
        )) : (
          <Line type="monotone" dataKey="value" stroke={seriesColor(0)} strokeWidth={2}
            isAnimationActive={dots && !banded}
            dot={banded
              // A period outside its expected range is marked whatever the
              // number of points; the others keep the usual rule.
              ? ((p: any) => flagged(p.payload)
                ? <circle key={`a${p.index}`} data-testid="anomaly-dot" cx={p.cx} cy={p.cy} r={5}
                    fill="var(--danger, #dc2626)" stroke="#fff" strokeWidth={1.5} />
                : dots ? <circle key={`d${p.index}`} cx={p.cx} cy={p.cy} r={3} fill={seriesColor(0)} /> : <g key={`n${p.index}`} />)
              : dots ? { fill: seriesColor(0), r: 3 } : false}
            activeDot={{ r: 5, fill: seriesColor(0), stroke: '#fff', strokeWidth: 2 }}
          >
            {labels && <LabelList {...labels} />}
          </Line>
        )}
        {banded && ['lo', 'hi'].map(k => (
          <Line key={k} type="monotone" dataKey={k} stroke="var(--muted)" strokeWidth={1} strokeDasharray="3 3"
            dot={false} activeDot={false} isAnimationActive={false} connectNulls legendType="none" />
        ))}
        {changeAt && (
          <ReferenceLine x={changeAt} stroke={seriesColor(1)} strokeDasharray="5 4"
            label={{ value: `${data.change_point.shift_pct > 0 ? '+' : ''}${Number(data.change_point.shift_pct).toFixed(0)}%`,
              position: 'insideTopLeft', fill: seriesColor(1), fontSize: 10 }} />
        )}
        {analyticsLines.map((l, i) => (
          <ReferenceLine key={i} y={l.value} stroke={l.color} strokeDasharray="4 4"
            label={{ value: l.label, position: 'insideTopRight', fill: l.color, fontSize: 10 }} />
        ))}
        {notes.filter(n => typeof n.value === 'number').map(n => (
          <ReferenceDot key={`note${n.n}`} x={n.period} y={n.value as number} r={8} fill="var(--surface, #fff)"
            stroke={seriesColor(1)} strokeWidth={1.5} isFront
            label={{ value: String(n.n), position: 'center', fontSize: 10, fontWeight: 700, fill: seriesColor(1) }} />
        ))}
        {brush && <Brush {...brush} />}
      </LineChart>
    </ResponsiveContainer>
  )
  if (notes.length === 0) return chart
  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <div style={{ flex: '1 1 0', minHeight: 0 }}>{chart}</div>
      <ol data-testid="timeline-notes" dir={rtl ? 'rtl' : undefined}
        style={{ flex: '0 0 auto', margin: 0, padding: '2px 8px 0', listStyle: 'none', fontSize: 10.5, color: 'var(--muted)',
          maxHeight: '38%', overflow: 'auto' }}>
        {notes.map(n => (
          <li key={n.n} data-testid="timeline-note" style={{ display: 'flex', gap: 6, alignItems: 'baseline' }}>
            <b style={{ color: seriesColor(1), flex: '0 0 auto' }}>{n.n}</b>
            <span>{takeawayText(tr, { takeaway: n.text, takeaway_i18n: n.text_i18n }) ?? n.text}</span>
          </li>
        ))}
      </ol>
    </div>
  )
}
