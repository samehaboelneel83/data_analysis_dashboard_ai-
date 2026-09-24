import {
  ComposedChart, Bar, Line, Area, Scatter, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { TT, COLORS } from '../chartUtils'
import type { ChartRendererProps } from './types'
import { axisTitles, xTitleLabel, yTitleLabel, X_TITLE_H } from './axisOptions'

/**
 * A chart the author composed from plot layers — SAS calls this Graph Builder.
 *
 * The catalogue already had three fixed combinations (dual-axis bar, line and
 * bar-line). What this adds is that the COMBINATION is the author's: how many
 * layers, which mark each draws, which axis each belongs to. Saving the result
 * as an object template — which this codebase already does — is what makes it a
 * reusable graph rather than one chart.
 *
 * Every layer the author added is drawn, on the axis they chose. The two things
 * this must not do are draw fewer layers than were asked for, and put a count
 * and an average on one scale: that misreading is the whole reason a second
 * axis exists.
 */
interface Layer {
  key: string
  label: string
  mark: string
  axis: 'left' | 'right'
  measure?: string
  aggregation?: string
}

export default function CustomGraphRenderer(
  { data, cfg, rtl, measureFmt }: ChartRendererProps,
) {
  const layers: Layer[] = data?.layers ?? []
  const rows: Record<string, unknown>[] = data?.rows ?? []
  // This renderer draws its own axes rather than going through axisOptions,
  // so the titles are named here too. The x axis is the dimension, as
  // everywhere. A y axis is titled only when ONE layer sits on it: two
  // measures sharing a side have no single name, and the legend already says
  // which is which -- a title naming one of them would be false about the
  // other.
  const titles = axisTitles(cfg ?? {})
  const sideTitle = (side: 'left' | 'right') => {
    const mine = layers.filter(l => (l.axis ?? 'left') === side)
    return mine.length === 1 ? (mine[0].label || mine[0].measure) : undefined
  }
  // Placed by the shared builders' own measured props, not by numbers
  // eyeballed here -- this renderer draws its axes itself, which is exactly
  // how a second, drifted copy of them would get in.
  const sideLabel = (side: 'left' | 'right') => {
    const value = sideTitle(side)
    return value ? yTitleLabel(value, rtl, side === 'right') : undefined
  }
  const skipped: string[] = data?.skipped ?? []

  if (!layers.length) {
    return (
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center', gap: 4,
        color: 'var(--muted)', fontSize: 12, textAlign: 'center', padding: 10 }}>
        <span>Add a layer to build this graph.</span>
        <span style={{ fontSize: 11 }}>
          Each layer is a measure drawn as bars, a line, an area or points.
        </span>
      </div>
    )
  }

  // Only when a layer actually asked for it. A second axis nobody uses is an
  // extra scale for the reader to reconcile against nothing.
  const usesRight = layers.some(l => l.axis === 'right')

  const draw = (layer: Layer, i: number) => {
    const colour = COLORS[i % COLORS.length]
    const shared = {
      key: layer.key, dataKey: layer.key, name: layer.label,
      yAxisId: layer.axis === 'right' ? 'right' : 'left',
    } as const
    switch (layer.mark) {
      case 'line':
        return <Line {...shared} type="monotone" stroke={colour} strokeWidth={2} dot={false} />
      case 'area':
        return <Area {...shared} type="monotone" stroke={colour} fill={colour} fillOpacity={0.3} />
      case 'scatter':
        return <Scatter {...shared} fill={colour} />
      // Anything else is a bar, matching the shaper: marks come from stored
      // config, which outlives the list either side knows about.
      default:
        return <Bar {...shared} fill={colour} />
    }
  }

  return (
    <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{ flex: 1, minHeight: 0 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis dataKey="name" tick={{ fontSize: 11 }} reversed={rtl}
              height={titles.category ? 30 + X_TITLE_H : undefined}
              label={titles.category ? xTitleLabel(titles.category) : undefined} />
            <YAxis yAxisId="left" tick={{ fontSize: 11 }}
              orientation={rtl ? 'right' : 'left'}
              label={sideLabel('left')} />
            {usesRight && (
              <YAxis yAxisId="right" orientation={rtl ? 'left' : 'right'} tick={{ fontSize: 11 }}
                label={sideLabel('right')} />
            )}
            <Tooltip contentStyle={TT} formatter={(v: unknown) => (
              measureFmt ? String(v) : (v as number))} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            {layers.map(draw)}
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {skipped.length > 0 && (
        // Named, because a layer that silently never appears sends the author
        // looking for a bug in the chart rather than at a column that has gone.
        <div style={{ fontSize: 10, color: '#f59e0b', padding: '2px 6px' }}>
          Not drawn — no such column: {skipped.join(', ')}
        </div>
      )}
    </div>
  )
}
