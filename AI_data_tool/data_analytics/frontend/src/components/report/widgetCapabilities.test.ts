import { describe, it, expect } from 'vitest'
import { formattingCapabilities } from './widgetCapabilities'

describe('formattingCapabilities', () => {
  it('gives a bar chart the full Cartesian option set', () => {
    // BarChartRenderer is the one single-Y-axis renderer that also renders a real
    // <Legend> (on its multi-series/crosstab path — see
    // chartRenderers/axisOptions.integration.test.tsx "renders a legend by default on
    // the multi-series path"), so it is the only FULL_NO_LEGEND-shaped type that also
    // gets 'legend'.
    const caps = formattingCapabilities('bar')
    expect(caps).toEqual(expect.arrayContaining(['axes', 'yScale', 'yDomain', 'grid', 'legend', 'dataLabels']))
  })

  it('gives a pie chart patterns and data labels, but no legend', () => {
    // PieChartRenderer now gates its percent-of-total label behind cfg.data_labels
    // (default on, preserving its historical always-shown look) — see the module
    // docstring's pie/donut/treemap/funnel note. It never renders a <Legend>, so
    // that capability stays withheld.
    const caps = formattingCapabilities('pie')
    expect(caps).toEqual(expect.arrayContaining(['patterns', 'dataLabels']))
    expect(caps).not.toContain('legend')
  })

  it('gives a donut chart legend and data labels in addition to patterns', () => {
    // DonutChartRenderer's <Legend> is now gated on cfg.legend (default on,
    // preserving its historical always-shown look) via legendProps, and it gained a
    // percent-of-total <label> gated on cfg.data_labels (default OFF: donut never
    // drew one before, so offering it un-set must not change existing widgets).
    const caps = formattingCapabilities('donut')
    expect(caps).toEqual(expect.arrayContaining(['patterns', 'legend', 'dataLabels']))
  })

  it('gives funnel patterns and data labels, but no legend', () => {
    // FunnelChartRenderer's <LabelList dataKey="name"> is now gated on
    // cfg.data_labels (default on, preserving its historical always-shown look), and
    // it gained fillPattern/PatternDefs hatching like pie/donut. No <Legend> exists.
    const caps = formattingCapabilities('funnel')
    expect(caps).toEqual(expect.arrayContaining(['patterns', 'dataLabels']))
    expect(caps).not.toContain('legend')
  })

  it('gives treemap only data labels', () => {
    // TreemapChartRenderer's node-name text is now gated on cfg.data_labels (default
    // on, preserving its historical size-gated-but-otherwise-always-shown look).
    // Its rectangles are solid fills, not grouped series, so 'patterns' stays
    // withheld the same way a single-series bar would get none.
    expect(formattingCapabilities('treemap')).toEqual(['dataLabels'])
  })

  it('gives forecast the axis/grid options its renderer already honours', () => {
    // ForecastChartRenderer already imports gridProps/xAxisProps/yAxisProps from
    // axisOptions.ts (it was missed by the "only 20 renderers" audit this module's
    // docstring warns is stale-prone) — it was simply never given a CAPABILITIES
    // entry, so none of those working controls had a UI. It has no <Legend> and no
    // <LabelList> (two Lines, one solid one dashed, share one series each), so
    // those two stay withheld like every other single-series line-shaped chart.
    const caps = formattingCapabilities('forecast')
    expect(caps).toEqual(expect.arrayContaining(['axes', 'yScale', 'yDomain', 'grid', 'xCategoryAxis']))
    expect(caps).not.toContain('legend')
    expect(caps).not.toContain('dataLabels')
  })

  it('withholds log scale and a fixed domain from the Gantt chart, whose axis is time', () => {
    const caps = formattingCapabilities('schedule')
    expect(caps).toContain('axes')
    expect(caps).not.toContain('yScale')
    expect(caps).not.toContain('yDomain')
    // ScheduleChartRenderer also never calls legendProps/labelListProps at all (no
    // <Legend>, no <LabelList> anywhere in the file) — those two would be no-ops too.
    expect(caps).not.toContain('legend')
    expect(caps).not.toContain('dataLabels')
  })

  it('gives a KPI no chart formatting options', () => {
    expect(formattingCapabilities('kpi')).toEqual([])
  })

  it('withholds yScale and yDomain from the three dual-axis widget types', () => {
    // Each of these renderers spreads the single FormatConfig y_min/y_max/y_scale onto
    // TWO independently-orientated <YAxis> elements (yAxisId="left"/"right"), e.g.
    // DualAxisBarChartRenderer.tsx lines 19-20. A shared domain/scale would clip or
    // flatten whichever axis it wasn't meant for.
    for (const wt of ['dual_axis_bar', 'dual_axis_line', 'dual_axis_bar_line'] as const) {
      const caps = formattingCapabilities(wt)
      expect(caps).not.toContain('yScale')
      expect(caps).not.toContain('yDomain')
      // They DO still get a real legend and real data labels — legendProps/<Legend>
      // and labelListProps/<LabelList> are both wired in every one of these three files.
      expect(caps).toContain('legend')
      expect(caps).toContain('dataLabels')
      expect(caps).toContain('axes')
      expect(caps).toContain('grid')
    }
  })

  it('withholds yScale and yDomain from the two dual-scale time-axis types, but keeps legend and data labels', () => {
    // Same two-<YAxis>-sharing-one-cfg problem as the dual_axis_* bar/line types above.
    // Deviation from the phase draft's TIME_AXIS bucket: both
    // DualAxisTimeSeriesRenderer and ComparativeTimeSeriesRenderer DO call
    // labelListProps for both series (labels1/labels2, each wired to a <LabelList>)
    // and DO call legendProps/<Legend> — confirmed directly in
    // axisOptions.integration.test.tsx ("renders a legend by default" /
    // "renders a data label on both series when asked" under the
    // ComparativeTimeSeriesRenderer describe block). Excluding dataLabels for these
    // two, as the draft did, would withhold a control that actually works.
    for (const wt of ['dual_axis_time_series', 'comparative_time_series'] as const) {
      const caps = formattingCapabilities(wt)
      expect(caps).not.toContain('yScale')
      expect(caps).not.toContain('yDomain')
      expect(caps).toContain('legend')
      expect(caps).toContain('dataLabels')
    }
  })

  it('withholds yScale and yDomain from dot_plot and butterfly, whose value sits on the XAxis', () => {
    // DotPlotRenderer: <XAxis type="number" dataKey="value" .../>, <YAxis type="category"
    // dataKey="name" .../>. ButterflyChartRenderer: <XAxis type="number" .../> carrying
    // left/right bar values, <YAxis type="category" dataKey="name" .../>. y_min/y_max/
    // y_scale would target the category axis, not the value the option is meant to scale.
    for (const wt of ['dot_plot', 'butterfly'] as const) {
      const caps = formattingCapabilities(wt)
      expect(caps).not.toContain('yScale')
      expect(caps).not.toContain('yDomain')
      expect(caps).toContain('axes')
      expect(caps).toContain('grid')
      expect(caps).toContain('dataLabels')
      // Neither renderer imports legendProps or renders a <Legend>.
      expect(caps).not.toContain('legend')
    }
  })

  it('withholds legend from every single-series Cartesian renderer with no <Legend> in its JSX', () => {
    // Deviation from the phase draft's FULL bucket, which offered 'legend' to all of
    // these. Grepping chartRenderers/*.tsx for a literal `<Legend` turns up exactly:
    // BarChartRenderer, BubbleChartRenderer, RibbonChartRenderer, the three dual_axis_*
    // bar/line renderers, and the two time-series renderers — nowhere else. None of the
    // types below import legendProps or render <Legend>; offering the control would be
    // a pure no-op.
    const noLegendTypes = [
      'line', 'area', 'step', 'histogram', 'waterfall',
      'scatter', 'bubble_change', 'needle', 'numeric_series',
    ] as const
    for (const wt of noLegendTypes) {
      expect(formattingCapabilities(wt)).not.toContain('legend')
    }
  })

  it('offers legend to bubble and ribbon, whose renderers wire legendProps into a real <Legend>', () => {
    expect(formattingCapabilities('bubble')).toContain('legend')
    expect(formattingCapabilities('ribbon')).toContain('legend')
  })

  it('offers table options only to the table-shaped types', () => {
    for (const wt of ['table', 'crosstab', 'matrix'] as const) {
      expect(formattingCapabilities(wt)).toContain('tableOptions')
    }
    for (const wt of ['bar', 'line', 'pie', 'kpi', 'gauge'] as const) {
      expect(formattingCapabilities(wt)).not.toContain('tableOptions')
    }
  })

  it('offers accessible patterns only to the renderers that read cfg.series_patterns', () => {
    // Grepping chartRenderers/*.tsx for `series_patterns` turns up exactly the grouped
    // bar (fill hatch), pie + donut (slice hatch), and the dual-axis / comparative line
    // charts (per-series dash). Offering it elsewhere would be a silent no-op.
    for (const wt of ['bar', 'pie', 'donut', 'dual_axis_line', 'dual_axis_bar_line',
                      'dual_axis_time_series', 'comparative_time_series'] as const) {
      expect(formattingCapabilities(wt)).toContain('patterns')
    }
    // Single-series charts have no groups to distinguish; tables/kpi have no marks.
    for (const wt of ['line', 'area', 'step', 'bubble', 'ribbon', 'dual_axis_bar',
                      'table', 'kpi', 'histogram'] as const) {
      expect(formattingCapabilities(wt)).not.toContain('patterns')
    }
  })
})

describe('the category-label angle is offered only where it does something', () => {
  it('offers it to the renderers whose x axis holds names', () => {
    for (const wt of ['bar', 'line', 'area', 'step', 'histogram', 'waterfall', 'needle',
                      'dual_axis_bar', 'dual_axis_line', 'dual_axis_bar_line',
                      'dual_axis_time_series', 'comparative_time_series'] as const) {
      expect(formattingCapabilities(wt), wt).toContain('xCategoryAxis')
    }
  })

  it('withholds it from every numeric-x renderer, which passes the planner no labels', () => {
    // xAxisProps skips the planner without labels, so an angle set on these
    // would be silently discarded -- the no-op this module exists to prevent.
    for (const wt of ['scatter', 'bubble', 'bubble_change', 'numeric_series',
                      'dot_plot', 'butterfly', 'schedule'] as const) {
      expect(formattingCapabilities(wt), wt).not.toContain('xCategoryAxis')
    }
  })

  it('still grants those renderers the general axes options', () => {
    // The narrower capability must not have taken anything away.
    for (const wt of ['scatter', 'dot_plot', 'butterfly', 'schedule'] as const) {
      expect(formattingCapabilities(wt), wt).toContain('axes')
    }
  })
})
