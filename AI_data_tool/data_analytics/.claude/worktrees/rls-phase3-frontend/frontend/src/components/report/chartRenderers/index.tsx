import type { WidgetType } from '../../../types/report'
import type { ChartRendererProps } from './types'
import BarChartRenderer from './BarChartRenderer'
import LineChartRenderer from './LineChartRenderer'
import PieChartRenderer from './PieChartRenderer'
import DonutChartRenderer from './DonutChartRenderer'
import ScatterChartRenderer from './ScatterChartRenderer'
import TreemapChartRenderer from './TreemapChartRenderer'
import StepPlotRenderer from './StepPlotRenderer'
import DotPlotRenderer from './DotPlotRenderer'
import HistogramRenderer from './HistogramRenderer'
import ButterflyChartRenderer from './ButterflyChartRenderer'
import DualAxisBarChartRenderer from './DualAxisBarChartRenderer'
import DualAxisLineChartRenderer from './DualAxisLineChartRenderer'
import DualAxisBarLineChartRenderer from './DualAxisBarLineChartRenderer'
import DualAxisTimeSeriesRenderer from './DualAxisTimeSeriesRenderer'
import ComparativeTimeSeriesRenderer from './ComparativeTimeSeriesRenderer'
import NeedlePlotRenderer from './NeedlePlotRenderer'
import NumericSeriesPlotRenderer from './NumericSeriesPlotRenderer'
import BubbleChartRenderer from './BubbleChartRenderer'
import BubbleChangePlotRenderer from './BubbleChangePlotRenderer'
import CorrelationMatrixRenderer from './CorrelationMatrixRenderer'
import HeatMapRenderer from './HeatMapRenderer'
import ParallelCoordinatesRenderer from './ParallelCoordinatesRenderer'
import BoxPlotRenderer from './BoxPlotRenderer'
import WaterfallChartRenderer from './WaterfallChartRenderer'
import GaugeRenderer from './GaugeRenderer'
import ScheduleChartRenderer from './ScheduleChartRenderer'
import WordCloudRenderer from './WordCloudRenderer'
import VectorPlotRenderer from './VectorPlotRenderer'

export type { ChartRendererProps }

export const CHART_RENDERERS: Partial<Record<WidgetType, React.FC<ChartRendererProps>>> = {
  bar: BarChartRenderer,
  line: LineChartRenderer,
  pie: PieChartRenderer,
  donut: DonutChartRenderer,
  scatter: ScatterChartRenderer,
  treemap: TreemapChartRenderer,
  step: StepPlotRenderer,
  dot_plot: DotPlotRenderer,
  needle: NeedlePlotRenderer,
  histogram: HistogramRenderer,
  butterfly: ButterflyChartRenderer,
  dual_axis_bar: DualAxisBarChartRenderer,
  dual_axis_line: DualAxisLineChartRenderer,
  dual_axis_bar_line: DualAxisBarLineChartRenderer,
  dual_axis_time_series: DualAxisTimeSeriesRenderer,
  comparative_time_series: ComparativeTimeSeriesRenderer,
  numeric_series: NumericSeriesPlotRenderer,
  bubble: BubbleChartRenderer,
  bubble_change: BubbleChangePlotRenderer,
  correlation_matrix: CorrelationMatrixRenderer,
  heatmap: HeatMapRenderer,
  parallel_coordinates: ParallelCoordinatesRenderer,
  box_plot: BoxPlotRenderer,
  waterfall: WaterfallChartRenderer,
  gauge: GaugeRenderer,
  schedule: ScheduleChartRenderer,
  word_cloud: WordCloudRenderer,
  vector_plot: VectorPlotRenderer,
}
