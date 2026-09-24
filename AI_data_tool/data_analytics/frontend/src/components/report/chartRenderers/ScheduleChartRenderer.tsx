import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell, ResponsiveContainer } from 'recharts'
import { COLORS, TT } from '../chartUtils'
import type { ChartRendererProps } from './types'
import { axisTitles, xAxisProps, yAxisProps, gridProps } from './axisOptions'

function toMs(v: unknown): number {
  if (typeof v === 'number') return v
  const t = Date.parse(String(v))
  return isNaN(t) ? NaN : t
}

export default function ScheduleChartRenderer({ data, cfg, rtl, ruleStyles, plotH }: ChartRendererProps) {
  const rows: { name: string; start: unknown; end: unknown; group?: string }[] = data?.rows ?? []

  if (rows.length === 0) {
    return <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 12 }}>Configure widget to see data</div>
  }

  // origIndex tracks each row's position in the widget's original result rows, which is
  // what ruleStyles.rows is indexed by. Invalid-date rows get filtered out below, so
  // chartData's own index (used for React keys) is not a safe stand-in for that lookup.
  const parsed = rows.map((r, i) => ({ name: r.name, startMs: toMs(r.start), endMs: toMs(r.end), group: r.group, origIndex: i }))
  const validRows = parsed.filter(r => !isNaN(r.startMs) && !isNaN(r.endMs))

  if (validRows.length === 0) {
    return <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 12 }}>Configure widget to see data</div>
  }

  const minStart = Math.min(...validRows.map(r => r.startMs))
  const chartData = validRows.map(r => ({ name: r.name, offset: r.startMs - minStart, span: Math.max(0, r.endMs - r.startMs), group: r.group, origIndex: r.origIndex }))
  const groups = Array.from(new Set(chartData.map(d => d.group).filter((g): g is string => !!g)))
  const colorFor = (g?: string) => (g && groups.length > 0) ? COLORS[groups.indexOf(g) % COLORS.length] : COLORS[0]
  // A Gantt's axes are neither of the usual pair: the bottom is TIME, named
  // by the start-date column, and the side is the task, named by the
  // dimension. Both come from the config; neither is the builders' default.
  const titles = axisTitles(cfg)
  const timeTitle = typeof cfg.start === 'string' ? cfg.start : undefined
  const grid = gridProps(cfg)

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={chartData} layout="vertical" margin={{ top: 10, right: 10, left: 10, bottom: 10 }}>
        {grid && <CartesianGrid {...grid} />}
        {/* tick/axisLine/tickLine: fix round 1 (Task 9 review) -- these used to be
            hard-pinned to this Gantt axis's historical look ({fontSize:11} tick with no
            fill, axisLine/tickLine forced true) AFTER the builder spread, which discarded
            axis_tick_size/axis_tick_color/axis_line/tick_line even though the Formatting
            panel offers 'axes' for `schedule`. That was itself a silent no-op -- the exact
            defect class widgetCapabilities.ts exists to prevent, just introduced one layer
            lower (in the renderer instead of the capability map). Fixed by making the
            historical values DEFAULTS that config can still win over, not hard-codes:
            with no axis_tick_size/axis_tick_color/axis_line/tick_line set, this renders
            exactly as it always has (fontSize 11, no fill override, both lines shown).
            This axis intentionally does NOT get y_min/y_max/y_scale: it is wired
            through xAxisProps, which never carries domain/scale (that's yAxisProps'
            job) -- a log or fixed domain on a task-time axis would be meaningless. */}
        <XAxis type="number" {...xAxisProps(cfg, rtl, undefined, undefined,
          { title: timeTitle })}
          tick={{ fontSize: cfg.axis_tick_size ?? 11, ...(cfg.axis_tick_color ? { fill: cfg.axis_tick_color } : {}) }}
          axisLine={cfg.axis_line ?? true} tickLine={cfg.tick_line ?? true}
          tickFormatter={v => new Date(minStart + v).toLocaleDateString()} />
        {/* scale/domain/allowDecimals forced back to Recharts' own defaults after the
            spread: yAxisProps wires cfg.y_scale/y_min/y_max onto whatever <YAxis> it is
            spread onto, including this category axis. Recharts' parseScale
            (util/ChartUtils.js) maps the `scale` prop to a d3 factory WITHOUT consulting
            axis.type -- cfg.y_scale === 'log' would build scaleLog().domain(['Task A',
            'Task B']), coercing every category string to NaN and corrupting every row's
            position on the Gantt. `domain` alone is inert on a category axis
            (isDomainSpecifiedByUser returns false for non-number axes), but `scale` is
            not -- both are pinned back defensively, alongside allowDecimals. That guard is
            unaffected by the tick/axisLine/tickLine fix above: this category axis still
            never receives yAxisProps' own scale/domain, only its tick styling now reads
            config, with the same defaults-not-hard-codes treatment as the XAxis above. */}
        <YAxis type="category" dataKey="name"
          {...yAxisProps(cfg, rtl, undefined, undefined, undefined,
            { categoryLabels: rows.map((r: any) => String(r.name)), height: plotH,
              title: titles.category })}
          scale="auto" domain={undefined} allowDecimals
          tick={{ fontSize: cfg.axis_tick_size ?? 11, ...(cfg.axis_tick_color ? { fill: cfg.axis_tick_color } : {}) }}
          axisLine={cfg.axis_line ?? true} tickLine={cfg.tick_line ?? true} />
        <Tooltip contentStyle={TT} formatter={(_v: any, _n: string, props: any) =>
          [`${new Date(minStart + props.payload.offset).toLocaleDateString()} → ${new Date(minStart + props.payload.offset + props.payload.span).toLocaleDateString()}`, props.payload.name]
        } />
        <Bar dataKey="offset" stackId="gantt" fill="transparent" isAnimationActive={false} />
        <Bar dataKey="span" stackId="gantt" isAnimationActive={false} radius={3}>
          {chartData.map((d, i) => <Cell key={i} fill={ruleStyles?.rows?.[d.origIndex]?.fill ?? colorFor(d.group)} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
