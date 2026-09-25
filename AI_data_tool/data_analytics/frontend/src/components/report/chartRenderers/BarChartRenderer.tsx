import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, Cell, ReferenceLine, ResponsiveContainer, Brush, LabelList, Customized } from 'recharts'
import { TT, fmtStr, getFillFactory, COLORS, fillPattern, PatternDefs } from '../chartUtils'
import type { ChartRendererProps } from './types'
import { toBarSeries } from './barSeries'
import { computeAnalyticsLines } from './analyticsLines'
import { xAxisProps, yAxisProps, gridProps, legendProps, labelListProps, brushProps, chartMargin } from './axisOptions'
import { seriesName } from './axisOptions'

function minOf(values: number[]): number | undefined {
  const finite = values.filter(n => !isNaN(n))
  return finite.length ? Math.min(...finite) : undefined
}

// ── The report design's bar look ─────────────────────────────────────────────
// Numbers (value ticks, value labels) in tabular figures so digits line up;
// a thin baseline under the bars and no axis titles unless the author typed
// one -- the card title already says what the bars are and what they count.
// Category ticks keep the shared size: a bigger face tilts labels sooner, the
// opposite of the upright axis the design draws. Every piece stays
// overridable from the Formatting panel: defaults, applied where cfg is silent.
//
// NOT the mono face the design sets them in: Recharts measures SVG text with
// its real font and wraps it at spaces when it overflows its box, and the
// gutters and bar widths are sized for the sans face. In mono, "$ 2,400,000"
// broke in two -- the "$" on a line of its own above the number (seen on the
// Sales Overview capture, 2026-09-24). Tabular figures give the alignment the
// mono face was there for, at the width everything was measured for.
const MONO = { fontVariantNumeric: 'tabular-nums' as const }
const BASELINE = { stroke: 'var(--border)', strokeWidth: 1 }

function designAxes(cfg: ChartRendererProps['cfg']) {
  return {
    xCfg: cfg,
    xOpts: { title: (cfg.x_axis_label as string | undefined) ?? '' },
    yOpts: { title: (cfg.y_axis_label as string | undefined) ?? '' },
    axisLine: cfg.axis_line ?? BASELINE,
  }
}

function monoTick(t: Record<string, unknown>) {
  return { ...t, style: { ...((t.style as object) ?? {}), ...MONO } }
}

export default function BarChartRenderer({ rows, data, cfg, rtl, broadcasts, localSelected, onClickPoint, measureFmt, ruleStyles, plotW, plotH, onBrushChange }: ChartRendererProps) {
  const getFill = getFillFactory(broadcasts, localSelected, ruleStyles?.rows)
  const look = designAxes(cfg)
  const mode = (cfg.bar_mode as string) || 'clustered'
  const { rows: seriesRows, series } = toBarSeries(data, mode)
  const analyticsLines = computeAnalyticsLines(rows, cfg.analytics)
  const grid = gridProps(cfg)
  const brush = series.length > 0
    ? brushProps(cfg, { rows: seriesRows, onChange: onBrushChange })
    : brushProps(cfg, { rows, dataKey: 'value', onChange: onBrushChange })

  if (series.length > 0) {
    const isPercent = mode === 'stacked100'
    const stackId = mode === 'clustered' ? undefined : 'stack'
    const legend = legendProps(cfg, rtl)
    const observedMin = minOf(seriesRows.flatMap((r: any) => series.map(s => Number(r[s]))))
    // What the VALUE AXIS spans, which is not what the bars plot: a stack tops
    // out at the row's SUM (three series of $900,000 stack to $2,700,000, a
    // digit longer than any single value), while clustered bars top out at the
    // largest individual value. Sizing the gutter from the plotted values
    // would undersize every stacked chart -- the same trap as Waterfall, whose
    // axis spans start..end while it plots the delta. stacked100 is excluded
    // by the caller: it relabels ticks 0-100 with its own formatter.
    const axisValues = stackId
      ? seriesRows.map((r: any) => series.reduce((a, s) => a + (Number(r[s]) || 0), 0))
      : seriesRows.flatMap((r: any) => series.map(s => r[s]))
    return (
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={seriesRows} margin={chartMargin(rtl, { top: 4, right: 8, bottom: 20, left: 0 })}
          // A split bar (region x channel) filters by its CATEGORY, the same as
          // an unsplit one. Without this, adding a colour to a chart silently
          // took away its ability to filter the page.
          style={broadcasts ? { cursor: 'pointer' } : undefined}
          onClick={broadcasts ? (d: any) => d?.activePayload?.[0] && onClickPoint(d.activePayload[0].payload.name) : undefined}>
          <Customized component={() => <PatternDefs colors={series.map((_, i) => COLORS[i % COLORS.length])} enabled={!!cfg.series_patterns} />} />
          {grid && <CartesianGrid {...grid} />}
          <XAxis dataKey="name" {...xAxisProps(look.xCfg, rtl, seriesRows.map((r: any) => String(r.name)), plotW, look.xOpts)}
            axisLine={look.axisLine} />
          {(() => {
            const y = yAxisProps(cfg, rtl, measureFmt, isPercent ? undefined : axisValues, observedMin, { height: plotH, ...look.yOpts })
            return <YAxis {...y} tick={monoTick(y.tick as Record<string, unknown>)}
              tickFormatter={v => isPercent ? `${v}%` : fmtStr(v, measureFmt)} />
          })()}
          {/* Each line names its series ("Online: 138"). The name used to be
              blanked, so a four-series tooltip was four bare numbers told
              apart only by colour. */}
          <Tooltip contentStyle={TT} formatter={(v: unknown, name: unknown) =>
            [isPercent ? `${Number(v).toFixed(1)}%` : fmtStr(v, measureFmt), String(name ?? '')]} />
          {legend && <Legend {...legend} wrapperStyle={{ fontSize: 10 }} />}
          {series.map((s, i) => {
            const labels = labelListProps(cfg, measureFmt, s, seriesRows.length)
            return (
              <Bar key={s} dataKey={s} stackId={stackId} fill={fillPattern(i, COLORS[i % COLORS.length], !!cfg.series_patterns)}
                radius={stackId ? (i === series.length - 1 ? [4, 4, 0, 0] : undefined) : [4, 4, 0, 0]}>
                {/* The selected category stays solid and the rest dim, as on
                    an unsplit bar: the click has to show what it did. */}
                {broadcasts && localSelected != null && seriesRows.map((r: any, j: number) => (
                  <Cell key={j} fillOpacity={r.name === localSelected
                    || (Array.isArray(localSelected) && (localSelected as unknown[]).includes(r.name)) ? 1 : 0.3} />
                ))}
                {labels && <LabelList {...labels} />}
              </Bar>
            )
          })}
          {brush && <Brush {...brush} />}
      </BarChart>
      </ResponsiveContainer>
    )
  }

  const observedMin = minOf(rows.map((r: any) => Number(r.value)))
  // A simple bar chart prints its values on the bars unless the author said
  // otherwise: with a dozen bars or fewer the number IS the reading, and the
  // axis becomes a guide rather than the only way to get it. Past twelve the
  // labels start to crowd, so it stays opt-in there.
  const autoLabels = cfg.data_labels === undefined && rows.length > 0 && rows.length <= 12
  const baseLabels = labelListProps(autoLabels ? { ...cfg, data_labels: true } : cfg, measureFmt, 'value', rows.length)
  const labels = baseLabels
    ? { ...baseLabels, offset: 6, style: { fill: 'var(--text)', fillOpacity: 0.8, fontSize: 11, fontWeight: 500, ...MONO },
        // One line, always. Recharts wraps a label at spaces once it is wider
        // than its bar, and a slim bar is narrower than "$ 2,221,092" -- the
        // "$" landed on a line of its own above the number. Non-breaking
        // spaces are not in Recharts' break set, so the value stays whole.
        valueAccessor: (entry: Record<string, unknown>, index: number) =>
          String(baseLabels.valueAccessor(entry, index)).replace(/ /g, ' ') }
    : null
  const y = yAxisProps(cfg, rtl, measureFmt, rows.map((r: any) => r.value), observedMin, { height: plotH, ...look.yOpts })
  // A bound target column (rows carry `target`): each bar gets a tick at its own
  // target and is recoloured by attainment. Attainment colouring yields to an explicit
  // display-rule fill -- a rule is the author saying what a mark means, and the
  // implicit convention must not override the explicit one.
  const hasTargets = rows.some((r: any) => typeof r.target === 'number')
  // Cross-highlight rows carry `highlight`: the full bar renders translucent
  // and a saturated overlay shows the selected share -- the shaded percentage
  // IS the shared-observation fraction (SAS's linked selection shading).
  const hasHighlights = rows.some((r: any) => typeof r.highlight === 'number')
  // The bucket the data has not finished (a September bar from data through the
  // 14th) is drawn faded with a dashed outline and says so in its tooltip, so a
  // half-month never reads as a collapse.
  const partialLabel: string | undefined = data?.partial_period?.label
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={rows} margin={chartMargin(rtl, { top: labels ? 20 : 4, right: 8, bottom: 20, left: 0 })}
        // Slim bars with air between them, as the design draws them: a bar is
        // read by its height, and a wide one adds ink without adding meaning.
        barCategoryGap="36%" maxBarSize={96}
        onClick={broadcasts ? (d: any) => d?.activePayload?.[0] && onClickPoint(d.activePayload[0].payload.name) : undefined}
        style={{ cursor: broadcasts ? 'pointer' : 'default' }}
      >
        {grid && <CartesianGrid {...grid} />}
        <XAxis dataKey="name" {...xAxisProps(look.xCfg, rtl, rows.map((r: any) => String(r.name)), plotW, look.xOpts)}
          axisLine={look.axisLine} />
        <YAxis {...y} tick={monoTick(y.tick as Record<string, unknown>)} tickFormatter={v => fmtStr(v, measureFmt)} />
        <Tooltip contentStyle={TT} cursor={{ fill: 'var(--surface2)' }} formatter={(v: unknown) => [fmtStr(v, measureFmt), seriesName(cfg)]}
          labelFormatter={(l: unknown) => partialLabel != null && String(l) === partialLabel
            ? `${String(l)} (partial — data to ${data.partial_period.through})` : String(l)} />
        <Bar dataKey="value" radius={[6, 6, 0, 0]}>
          {rows.map((r: any, i: number) => {
            const s = getFill(r.name, i)
            const attainment = hasTargets && !ruleStyles?.rows?.[i]?.fill && typeof r.target === 'number'
              ? (r.value >= r.target ? 'var(--success)' : 'var(--danger)')
              : undefined
            const isPartial = partialLabel != null && String(r.name) === partialLabel
            return <Cell key={i} fill={attainment ?? s.fill}
              opacity={hasHighlights ? 0.3 : isPartial ? Math.min(s.opacity ?? 1, 0.45) : s.opacity}
              stroke={isPartial ? 'var(--text)' : s.stroke} strokeWidth={isPartial ? 1 : s.strokeWidth}
              strokeDasharray={isPartial ? '3 2' : undefined}
              data-partial={isPartial ? 'true' : undefined}
              data-attainment={attainment ? (r.value >= r.target ? 'met' : 'missed') : undefined} />
          })}
          {labels && <LabelList {...labels} />}
        </Bar>
        {hasHighlights && (
          <Customized component={(props: any) => {
            // Saturated overlays drawn from the live scales, same pattern as
            // the per-bar target ticks below.
            const { formattedGraphicalItems, yAxisMap } = props
            const bars = formattedGraphicalItems?.[0]?.props?.data ?? []
            const yScale = (Object.values(yAxisMap ?? {})[0] as any)?.scale
            if (!yScale || !bars.length) return null
            return (
              <g data-testid="highlight-overlays">
                {bars.map((b: any, i: number) => {
                  const hv = rows[i]?.highlight
                  if (typeof hv !== 'number' || hv <= 0 || b?.x == null) return null
                  const yTop = yScale(hv)
                  const yBase = b.y + b.height
                  const h = Math.max(0, yBase - yTop)
                  const s = getFill(rows[i].name, i)
                  return <rect key={i} data-testid="highlight-portion" x={b.x} y={yBase - h}
                    width={b.width} height={h} fill={s.fill} rx={2} pointerEvents="none" />
                })}
              </g>
            )
          }} />
        )}
        {hasTargets && (
          <Customized component={(props: any) => {
            // Per-bar target ticks, drawn from the live scales so they stay aligned
            // under zoom, RTL and axis overrides. A step Line would join targets into
            // a trend, which a per-category target is not.
            const { formattedGraphicalItems, yAxisMap } = props
            const bars = formattedGraphicalItems?.[0]?.props?.data ?? []
            const yScale = (Object.values(yAxisMap ?? {})[0] as any)?.scale
            if (!yScale || !bars.length) return null
            return (
              <g data-testid="target-ticks">
                {bars.map((b: any, i: number) => {
                  const t = rows[i]?.target
                  if (typeof t !== 'number' || b?.x == null) return null
                  const y = yScale(t)
                  return <line key={i} x1={b.x - 2} x2={b.x + b.width + 2} y1={y} y2={y}
                    stroke="var(--text)" strokeWidth={2} />
                })}
              </g>
            )
          }} />
        )}
        {analyticsLines.map((l, i) => (
          <ReferenceLine key={i} y={l.value} stroke={l.color} strokeDasharray="4 4"
            label={{ value: l.label, position: 'insideTopRight', fill: l.color, fontSize: 10 }} />
        ))}
          {brush && <Brush {...brush} />}
      </BarChart>
    </ResponsiveContainer>
  )
}
