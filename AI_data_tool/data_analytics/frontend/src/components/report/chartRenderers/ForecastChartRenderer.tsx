import { ComposedChart, Line, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'
import { TT, fmtStr } from '../chartUtils'
import type { ChartRendererProps } from './types'
import { gridProps, xAxisProps, yAxisProps, chartMargin } from './axisOptions'

/**
 * History as a solid line, forecast as a dashed one, the 95% interval as a band.
 *
 * Rows are merged onto one axis: history points carry `value`, forecast points carry
 * `yhat`/`lo`/`hi`, and the join point carries both so the two lines meet instead of
 * leaving a gap at "now". The band is drawn from `lo` with a stacked delta to `hi` --
 * Recharts has no native band, but a transparent base area plus a filled delta area
 * is exactly one.
 *
 * When the widget config carries a target, the payload also carries `goal` --
 * "when does this reach X". That is computed by the SHAPER, from the same
 * history and projection drawn here; a caption computed separately could
 * disagree with the chart it sits under.
 */

interface ForecastGoal {
  target: number
  direction: 'rise' | 'fall'
  reached_in_history: { period: string; value: number } | null
  expected_period: string | null
  earliest_period: string | null
  latest_period: string | null
  within_horizon: boolean
  horizon: number
  end_period: string
  end_value: number | null
}
export default function ForecastChartRenderer({ data, cfg, rtl, measureFmt, plotW, plotH }: ChartRendererProps) {
  const history: { name: string; value: number }[] = data?.rows ?? []
  const forecast: { name: string; yhat: number; lo: number; hi: number }[] = data?.forecast ?? []

  const joined = [
    ...history.map(r => ({ name: r.name, value: r.value })),
    ...forecast.map((f, i) => ({
      name: f.name, yhat: f.yhat, lo: f.lo, band: f.hi - f.lo,
      // The first forecast point also carries the last history value under `value`,
      // so the solid line's end and the dashed line's start share an x position.
      ...(i === 0 && history.length ? {} : {}),
    })),
  ]
  if (history.length && forecast.length) {
    // Join the lines: give the last history point a yhat equal to its value.
    const idx = history.length - 1
    ;(joined[idx] as Record<string, number | string>).yhat = history[idx].value
  }

  const grid = gridProps(cfg)
  const boundary = history.length ? history[history.length - 1].name : undefined
  const goal: ForecastGoal | undefined = (data as { goal?: ForecastGoal })?.goal

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
    <div style={{ flex: 1, minHeight: 0 }}>
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={joined} margin={chartMargin(rtl, { top: 4, right: 8, bottom: 20, left: 0 })}>
        {grid && <CartesianGrid {...grid} />}
        <XAxis dataKey="name" {...xAxisProps(cfg, rtl, joined.map((d: any) => String(d.name)), plotW)} />
        <YAxis {...yAxisProps(cfg, rtl, measureFmt, [...history.map(r => r.value), ...forecast.map(f => f.hi)], undefined, { height: plotH })} tickFormatter={v => fmtStr(v, measureFmt)} />
        <Tooltip contentStyle={TT} formatter={(v: unknown, name: string) =>
          [fmtStr(v, measureFmt), name === 'yhat' ? 'forecast' : name === 'band' ? 'interval' : name]} />
        {/* The interval band: an invisible base to `lo`, then the lo->hi delta. */}
        <Area dataKey="lo" stackId="band" stroke="none" fill="transparent" isAnimationActive={false} />
        <Area dataKey="band" stackId="band" stroke="none" fill="var(--accent)" fillOpacity={0.12} isAnimationActive={false} />
        <Line dataKey="value" stroke="var(--accent)" strokeWidth={2} dot={false} isAnimationActive={false} />
        <Line dataKey="yhat" stroke="var(--accent)" strokeWidth={2} strokeDasharray="6 3" dot={false} isAnimationActive={false} />
        {boundary && <ReferenceLine x={boundary} stroke="var(--muted)" strokeDasharray="2 3"
          label={{ value: 'now', position: 'insideTopRight', fill: 'var(--muted)', fontSize: 10 }} />}
        {/* The target as a level, and the period it is met. Both drawn only
            when the answer exists -- a line with no explanation is a puzzle. */}
        {goal && <ReferenceLine y={goal.target} stroke="var(--accent)" strokeDasharray="4 4"
          strokeOpacity={0.6} />}
        {goal?.expected_period && <ReferenceLine x={goal.expected_period}
          stroke="var(--accent)" strokeDasharray="2 3" />}
      </ComposedChart>
    </ResponsiveContainer>
    </div>
    {goal && <GoalCaption goal={goal} fmt={measureFmt} />}
    </div>
  )
}

/**
 * The answer in a sentence.
 *
 * Four cases, and the difference between them is the whole value: a date, a
 * date already past, a range the band allows but the estimate does not, and a
 * plain "not this far" that says how far short it ends up instead. "Not within
 * the horizon" on its own reads as broken.
 */
function GoalCaption({ goal, fmt }: { goal: ForecastGoal; fmt?: unknown }) {
  const value = (v: number | null) => v == null ? '—' : fmtStr(v, fmt as never)
  const verb = goal.direction === 'rise' ? 'reach' : 'fall to'

  let body: React.ReactNode
  if (goal.expected_period) {
    body = <>Expected to {verb} <strong>{value(goal.target)}</strong> by{' '}
      <strong>{goal.expected_period}</strong>
      {goal.earliest_period && goal.earliest_period !== goal.expected_period && (
        <> — as early as {goal.earliest_period}</>)}
      {goal.latest_period && goal.latest_period !== goal.expected_period && (
        <>, as late as {goal.latest_period}</>)}
      {!goal.latest_period && <> ; the interval does not rule out later</>}
    </>
  } else if (goal.reached_in_history) {
    // Both halves, when both are true. Saying only "not expected to return"
    // drops precisely what the interval exists to carry — and the live demo
    // case is exactly this one: revenue passed the target a year ago, the
    // central estimate has settled below it, and the optimistic edge clears it
    // from the first projected period.
    body = <>Already reached {value(goal.target)} in{' '}
      <strong>{goal.reached_in_history.period}</strong>
      {' '}({value(goal.reached_in_history.value)}) — the projection is not
      {' '}expected to return there within {goal.horizon} periods
      {goal.earliest_period
        ? <>, though it is possible from <strong>{goal.earliest_period}</strong>
            {' '}at the optimistic edge of the interval.</>
        : <>.</>}
    </>
  } else if (goal.earliest_period) {
    body = <>Not expected to {verb} {value(goal.target)} — though it is
      {' '}possible as early as <strong>{goal.earliest_period}</strong> at the
      {' '}optimistic edge of the interval.</>
  } else {
    body = <>Not expected to {verb} {value(goal.target)} within{' '}
      {goal.horizon} periods — the projection ends near{' '}
      <strong>{value(goal.end_value)}</strong> in {goal.end_period}.</>
  }

  return (
    <div data-testid="forecast-goal" style={{
      fontSize: 11, color: 'var(--muted)', padding: '4px 8px 2px',
      lineHeight: 1.45, flexShrink: 0,
    }}>{body}</div>
  )
}
