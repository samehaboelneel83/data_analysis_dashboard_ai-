/**
 * Which formatting options each widget type can actually honour.
 *
 * This exists because offering a control that silently does nothing is a real
 * defect, not a cosmetic one — phase 1 shipped a "Widget background" rule target
 * that painted nothing, and it survived 860 tests precisely because no one asked
 * whether the consumer existed. A Log-scale toggle on a word cloud is the same bug.
 *
 * Every bucket below was checked against its renderer file (chartRenderers/*.tsx),
 * not assumed:
 *
 *   - yScale/yDomain are withheld from the five dual-scale/time types
 *     (dual_axis_bar, dual_axis_line, dual_axis_bar_line, dual_axis_time_series,
 *     comparative_time_series). FormatConfig has a single y_min/y_max/y_scale, and
 *     each of these renderers spreads that one cfg onto TWO independently
 *     orientated <YAxis yAxisId="left"/"right"> elements (see e.g.
 *     DualAxisBarChartRenderer.tsx lines 19-20). A shared domain/scale would clip
 *     or flatten whichever axis it wasn't meant for.
 *
 *   - yScale/yDomain are withheld from `schedule`. Its value axis is the time
 *     XAxis (xAxisProps never carries scale/domain — that's yAxisProps' job), and
 *     its YAxis is a task-name category axis that ScheduleChartRenderer
 *     defensively pins back to `scale="auto" domain={undefined}` (lines 50-59)
 *     specifically because a log scale on category data corrupts every row's
 *     position — covered by axisOptions.integration.test.tsx's "keeps its
 *     category Y axis intact when y_scale is requested" test, which documents
 *     that without the guard the chart renders zero Y ticks and zero bars.
 *
 *   - yScale/yDomain are withheld from `dot_plot` and `butterfly`: both put their
 *     VALUE on the XAxis (DotPlotRenderer: `<XAxis type="number" dataKey="value">`;
 *     ButterflyChartRenderer: `<XAxis type="number">` carrying left/right bar
 *     values) and their category on the YAxis, so y_min/y_max/y_scale would apply
 *     to a category axis, not the value the option is meant to scale.
 *
 *   - `axes` has NO exceptions left to document. Fix round 1 found that `schedule`,
 *     `waterfall`, and `butterfly` each hard-overrode the tick object and the
 *     axisLine/tickLine props AFTER the builder spread (to preserve each
 *     renderer's own historical pixel appearance, which predates axisOptions.ts
 *     and legitimately differs from the shared builder's defaults) — which meant
 *     axis_tick_size/axis_tick_color/axis_line/tick_line were silently discarded
 *     on those three even though `axes` was offered for all of them. That was the
 *     same defect class this module exists to prevent, just one layer lower (in
 *     the renderer instead of the capability map). Round 1 fixed those three to use
 *     the renderer's historical value as a DEFAULT that config can still win over
 *     (e.g. `tick={{ fontSize: cfg.axis_tick_size ?? 11, ...(cfg.axis_tick_color
 *     ? { fill: cfg.axis_tick_color } : {}) }}`, `axisLine={cfg.axis_line ?? true}`,
 *     `tickLine={cfg.tick_line ?? true}`) — but round 1's "checked all 20, no other
 *     renderer has this pattern" claim was wrong: `histogram` had the identical
 *     hard-coded `tick={{ fill: 'var(--muted)', fontSize: 9 }}` on its XAxis and was
 *     missed. Fixed in this round the same way (default-not-hard-code, fontSize 9
 *     preserved as the default). All four renderers now use the historical value as
 *     a DEFAULT that config can still win over, so unset config still renders
 *     exactly as it always has and set config now actually reaches the DOM. See
 *     ScheduleChartRenderer.tsx, WaterfallChartRenderer.tsx,
 *     ButterflyChartRenderer.tsx, and HistogramRenderer.tsx, each covered by tests
 *     in axisOptions.integration.test.tsx proving both the unset-default and the
 *     config-wins halves. Re-checked all 20 renderers in this round (grepped every
 *     chartRenderers/*.tsx for a literal `tick={{` and for hard-coded
 *     `axisLine={true|false}`/`tickLine={true|false}` after the axisOptions spread):
 *     these four are the only ones with the pattern, so `axes` is a genuinely
 *     complete capability everywhere it is offered — but "checked all 20" is a claim
 *     that must be re-verified by grep each time a renderer changes, not trusted
 *     from a prior pass.
 *
 *   - `legend` is offered ONLY to the widget types whose renderer actually builds
 *     a <Legend> from legendProps(cfg): bar (its multi-series/crosstab path),
 *     bubble (its grouped path), ribbon, and the five dual/time types above.
 *     Grepping every chartRenderers/*.tsx file for a literal `<Legend` turns up
 *     exactly those eight (plus DonutChartRenderer's hardcoded, always-on Legend,
 *     which reads no FormatConfig key at all — see the pie/donut/treemap/funnel
 *     note below). Every other Cartesian renderer (line, area, step, histogram,
 *     waterfall, scatter, bubble_change, dot_plot, needle, butterfly,
 *     numeric_series) is a single-series chart with no <Legend> anywhere in its
 *     JSX; offering the control there would be the exact silent no-op this module
 *     exists to prevent.
 *
 *   - `dataLabels` is offered to every one of the 20 axisOptions-wired Cartesian
 *     types EXCEPT `schedule`, which is the one renderer that never calls
 *     labelListProps/<LabelList> at all.
 *
 *   - `pie`, `donut`, `treemap`, and `funnel` were wired up in a later round (none
 *     of the four import from axisOptions.ts — their controls are gated locally
 *     in each renderer instead of via xAxisProps/yAxisProps/legendProps' shared
 *     builder, since none of them has a Cartesian axis). Each kept its
 *     historical always-shown-or-never-shown look as the UNSET default, so a
 *     dashboard nobody has touched renders byte-identically to before:
 *       - pie: data_labels defaults ON (its percent-of-total label was always
 *         drawn); no legend was ever rendered, so that capability stays withheld.
 *       - donut: legend defaults ON (its <Legend> was always drawn, now gated via
 *         legendProps so cfg.legend===false can turn it off); data_labels
 *         defaults OFF (donut never drew one, so it is opt-IN, the opposite
 *         default from pie).
 *       - funnel: data_labels defaults ON (its <LabelList dataKey="name"> was
 *         always drawn); no legend exists.
 *       - treemap: data_labels defaults ON (a node's name was always drawn once
 *         its box was big enough); it has no groups to distinguish, so it does
 *         not get 'patterns' — same reasoning as a single-series bar chart.
 *     pie, donut, and funnel all read cfg.series_patterns to hatch their
 *     slices/segments; treemap does not yet — each node is painted by an
 *     independent content-render callback rather than a series of <Cell>
 *     children under one <Pie>/<Funnel>, so wiring it in means re-deriving each
 *     node's fill-or-pattern inside that callback instead of reusing the
 *     existing getFill/fillPattern pairing verbatim. Left out of this round as
 *     a scope decision, not a technical wall — a future round can still add it.
 *
 *   - Every other WidgetType (kpi, table, crosstab, matrix, list, text, image,
 *     shape, button, slicer, card, correlation_matrix, heatmap,
 *     parallel_coordinates, box_plot, gauge, vector_plot, word_cloud) is not a
 *     Recharts-Cartesian renderer at all and gets [] via the CAPABILITIES lookup's
 *     fallback.
 */
import type { WidgetType } from '../../types/report'

// 'xCategoryAxis' is narrower than 'axes' on purpose. The category-label angle
// control is honoured by xAxisProps ONLY when the renderer hands it the category
// labels, which is exactly the renderers whose x axis holds names. The ones with
// a NUMERIC x axis -- scatter, bubble, bubble_change, numeric_series, and the
// value-on-x pair dot_plot/butterfly plus the Gantt -- pass no labels, so the
// planner is skipped and an angle set there would be silently discarded. That is
// the silent no-op this module exists to prevent, so they do not get the
// capability. (`forecast` already imports gridProps/xAxisProps/yAxisProps from
// axisOptions.ts -- missed by this module's own "only 20 renderers" audit, which
// the top-of-file warning says must be re-verified by grep, not trusted from a
// prior pass. It now gets those already-working controls a real capability
// entry; it has no <Legend> and no <LabelList> in its file, so those two stay
// withheld like every other single-series line-shaped chart.)
export type FormattingCapability = 'axes' | 'xCategoryAxis' | 'yScale' | 'yDomain' | 'grid' | 'legend' | 'dataLabels' | 'tableOptions' | 'overview' | 'patterns'

// Single-Y-axis Cartesian charts whose renderer also builds a real <Legend> from
// legendProps(cfg): bar (crosstab/multi-series path), bubble (grouped path), ribbon
// (stacked columns, always has >=1 series with a Legend swatch per column).
const FULL_WITH_LEGEND: FormattingCapability[] = ['axes', 'yScale', 'yDomain', 'grid', 'legend', 'dataLabels']

// Single-Y-axis Cartesian charts that are always exactly one series, so their
// renderer never grew a <Legend> — legendProps/<Legend> do not appear in these files.
const FULL_NO_LEGEND: FormattingCapability[] = ['axes', 'yScale', 'yDomain', 'grid', 'dataLabels']

// Two independently-scaled <YAxis> elements fed by the one shared cfg — see the
// module docstring's first bullet for why yScale/yDomain can't be offered here.
const DUAL_SCALE: FormattingCapability[] = ['axes', 'grid', 'legend', 'dataLabels']

// Value sits on the XAxis, category on the YAxis — y_min/y_max/y_scale would target
// the wrong axis entirely, and neither renderer has a <Legend>.
const VALUE_ON_X_AXIS: FormattingCapability[] = ['axes', 'grid', 'dataLabels']

// Time axis on X (guarded against scale/domain by xAxisProps never carrying them),
// task-name category axis on Y (defensively pinned back in the renderer itself), no
// <Legend>, no <LabelList> anywhere in ScheduleChartRenderer.
const GANTT: FormattingCapability[] = ['axes', 'grid']

// Table-shaped renderers (WidgetRenderer.tsx's table branch, ~line 506) read
// table_row_numbers/table_row_lines/table_banding/table_condensed directly off cfg,
// and widget_data.py's crosstab/table shapers read show_totals/show_subtotals — none
// of that is an axisOptions.ts Cartesian concept, hence its own capability bucket.
const TABLE_OPTIONS: FormattingCapability[] = ['tableOptions']

// 'patterns' (accessible fill/line hatching, redundant with colour) is granted only
// to the renderers that actually read cfg.series_patterns: the grouped bar and the
// pie/donut slices honour it as a fill hatch, and the dual-axis / comparative line
// charts honour it as a per-series dash. Offering it on a single-series chart with
// nothing to distinguish would be the silent no-op this module exists to prevent.
const CAPABILITIES: Partial<Record<WidgetType, FormattingCapability[]>> = {
  // 'overview' appears only on the four renderers that actually mount <Brush>
  // from brushProps (line, area, step, bar) -- offering it elsewhere would be the
  // silent no-op this module exists to prevent.
  bar: [...FULL_WITH_LEGEND, 'overview', 'patterns', 'xCategoryAxis'],
  bubble: FULL_WITH_LEGEND,
  ribbon: FULL_WITH_LEGEND,

  line: [...FULL_NO_LEGEND, 'overview', 'xCategoryAxis'],
  area: [...FULL_NO_LEGEND, 'overview', 'xCategoryAxis'],
  step: [...FULL_NO_LEGEND, 'overview', 'xCategoryAxis'],
  histogram: [...FULL_NO_LEGEND, 'xCategoryAxis'],
  waterfall: [...FULL_NO_LEGEND, 'xCategoryAxis'],
  scatter: FULL_NO_LEGEND,
  bubble_change: FULL_NO_LEGEND,
  needle: [...FULL_NO_LEGEND, 'xCategoryAxis'],
  numeric_series: FULL_NO_LEGEND,

  pie: ['patterns', 'dataLabels'],
  donut: ['patterns', 'legend', 'dataLabels'],
  funnel: ['patterns', 'dataLabels'],
  treemap: ['dataLabels'],

  // Already imports gridProps/xAxisProps/yAxisProps -- see the xCategoryAxis
  // docstring above for why it was missing an entry until now, not why it gets
  // this particular one. Two Lines sharing one Y axis (solid history, dashed
  // continuation), no <Legend>, no <LabelList>: same shape as FULL_NO_LEGEND
  // minus dataLabels.
  forecast: ['axes', 'yScale', 'yDomain', 'grid', 'xCategoryAxis'],

  dual_axis_bar: [...DUAL_SCALE, 'xCategoryAxis'],
  dual_axis_line: [...DUAL_SCALE, 'patterns', 'xCategoryAxis'],
  dual_axis_bar_line: [...DUAL_SCALE, 'patterns', 'xCategoryAxis'],
  dual_axis_time_series: [...DUAL_SCALE, 'patterns', 'xCategoryAxis'],
  comparative_time_series: [...DUAL_SCALE, 'patterns', 'xCategoryAxis'],

  dot_plot: VALUE_ON_X_AXIS,
  butterfly: VALUE_ON_X_AXIS,

  schedule: GANTT,

  table: TABLE_OPTIONS,
  crosstab: TABLE_OPTIONS,
  matrix: TABLE_OPTIONS,
}

export function formattingCapabilities(wt: WidgetType): FormattingCapability[] {
  return CAPABILITIES[wt] ?? []
}

/** Widget types whose shaper honours `config.rank` (Top/Bottom N, percent
 *  mode, the "All Other" bucket). MIRRORS `RANKED_WIDGETS` in
 *  backend services/widget_data.py -- derived there from the dispatch table,
 *  pinned here by test_frontend_constant_mirrors.py in both directions. The
 *  hierarchy family is absent on purpose (its own reconciling top-N applies),
 *  and kpi has nothing to rank. */
export const RANKING_WIDGETS = new Set([
  'area', 'bar', 'butterfly', 'comparative_time_series', 'crosstab', 'donut',
  'dot_plot', 'dual_axis_bar', 'dual_axis_bar_line', 'dual_axis_line',
  'dual_axis_time_series', 'funnel', 'heatmap', 'line', 'list',
  'map_choropleth', 'matrix', 'needle', 'pie', 'ribbon', 'scatter', 'step',
  'table', 'treemap', 'word_cloud',
])

export function supportsRanking(widgetType: string): boolean {
  return RANKING_WIDGETS.has(widgetType)
}

