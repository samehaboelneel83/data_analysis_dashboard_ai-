import { ComposedChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, LabelList } from 'recharts'
import { TT, fmtStr, seriesDash} from '../chartUtils'
import type { ChartRendererProps } from './types'
import { axisTitles, xAxisProps, yAxisProps, gridProps, legendProps, labelListProps, chartMargin } from './axisOptions'
import { seriesName } from './axisOptions'

export default function DualAxisTimeSeriesRenderer({ rows, cfg, rtl, measureFmt, measure2Fmt, plotW, plotH, broadcasts, onClickPoint }: ChartRendererProps) {
  // Two measures on two scales: the right axis is titled from the
  // SECOND one, never from the left axis's label.
  const titles = axisTitles(cfg)
  const grid = gridProps(cfg)
  const legend = legendProps(cfg, rtl)
  const labels1 = labelListProps(cfg, measureFmt, 'value', rows.length)
  const labels2 = labelListProps(cfg, measure2Fmt, 'value2', rows.length)
  // A dual-axis chart with one measure draws ONE series. Previously the second
  // series rendered unconditionally, named `cfg.measure2 ?? 'value2'` -- so a
  // chart built with a single measure showed the renderer's internal data key in
  // its legend, over an empty line and a right axis scaled to nothing. The rows
  // are checked as well as the config because a saved widget can carry the data
  // without the label.
  const hasSecond = cfg.measure2 != null || rows.some((r: any) => r?.value2 != null)
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={rows} margin={chartMargin(rtl, { top: 4, right: 8, bottom: 20, left: 0 })}
        // Filters the page by the clicked category, like every other category
        // chart; a second axis is no reason to be a dead end for cross-filtering.
        style={broadcasts ? { cursor: 'pointer' } : undefined}
        onClick={broadcasts ? (d: any) => d?.activePayload?.[0] && onClickPoint(d.activePayload[0].payload.name) : undefined}>
        {grid && <CartesianGrid {...grid} />}
        {/* no interval override here: this renderer never set interval before, so
            Recharts' own default ('preserveEnd') applied and must keep applying. */}
        <XAxis dataKey="name" {...xAxisProps(cfg, rtl, rows.map((r: any) => String(r.name)), plotW)} />
        {/* orientation re-applied after the spread: yAxisProps derives orientation from
            rtl alone for a single axis, but this is one of a left/right pair, so each
            side must reassert its own place after the builder's spread. */}
        <YAxis yAxisId="left" {...yAxisProps(cfg, rtl, measureFmt, rows.map((r: any) => r.value), undefined, { height: plotH })} orientation={rtl ? 'right' : 'left'} tickFormatter={v => fmtStr(v, measureFmt)} />
        {hasSecond && <YAxis yAxisId="right" {...yAxisProps(cfg, rtl, measure2Fmt, rows.map((r: any) => r.value2), undefined, { height: plotH, title: cfg.y2_axis_label ?? titles.measure2 ?? '' })} orientation={rtl ? 'left' : 'right'} tickFormatter={v => fmtStr(v, measure2Fmt)} />}
        <Tooltip contentStyle={TT} formatter={(v: unknown, name: string) => [fmtStr(v, name === (cfg.measure2 ?? 'value2') ? measure2Fmt : measureFmt), name]} />
        {legend && <Legend {...legend} wrapperStyle={{ fontSize: 11, ...(rtl ? { direction: 'ltr' as const } : {}) }} />}
        <Line yAxisId="left" type="monotone" dataKey="value" name={seriesName(cfg)} stroke="var(--accent)" strokeWidth={2} strokeDasharray={seriesDash(0, cfg.series_patterns)} dot={false}>
          {labels1 && <LabelList {...labels1} />}
        </Line>
        {hasSecond && (<Line yAxisId="right" type="monotone" dataKey="value2" name={cfg.measure2 ?? 'value2'} stroke="#a78bfa" strokeWidth={2} strokeDasharray={seriesDash(1, cfg.series_patterns)} dot={false}>
          {labels2 && <LabelList {...labels2} />}
        </Line>)}
      </ComposedChart>
    </ResponsiveContainer>
  )
}
