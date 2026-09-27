import type { WidgetType } from '../../../types/report'
import { lazy } from 'react'
import ForecastChartRenderer from './ForecastChartRenderer'
import SankeyChartRenderer from './SankeyChartRenderer'
import HierarchyRenderer from './HierarchyRenderer'
import CustomGraphRenderer from './CustomGraphRenderer'

/* The map renderers pull in the bundled world geometry (~740 kB raw), which would
   otherwise ride along in the report-builder chunk for every author who never adds a
   map. React.lazy defers the download to the first render of a map widget;
   WidgetRenderer provides the Suspense boundary so only the map tile shows a loading
   state, not the page. */
const GeoChoroplethRenderer = lazy(() => import('./GeoChoroplethRenderer'))
const GeoPointsRenderer = lazy(() =>
  import('./GeoPointMapRenderer').then(m => ({ default: m.GeoPointsRenderer })))
const GeoLinesRenderer = lazy(() =>
  import('./GeoLineClusterRenderer').then(m => ({ default: m.GeoLinesRenderer })))
const GeoClustersRenderer = lazy(() =>
  import('./GeoLineClusterRenderer').then(m => ({ default: m.GeoClustersRenderer })))
const NetworkGraphRenderer = lazy(() => import('./NetworkGraphRenderer'))
const GeoPiesRenderer = lazy(() =>
  import('./GeoPieLayerRenderer').then(m => ({ default: m.GeoPiesRenderer })))
const GeoLayersRenderer = lazy(() =>
  import('./GeoPieLayerRenderer').then(m => ({ default: m.GeoLayersRenderer })))
const GeoDensityRenderer = lazy(() =>
  import('./GeoPieLayerRenderer').then(m => ({ default: m.GeoDensityRenderer })))
const GeoNetworkRenderer = lazy(() => import('./GeoNetworkRenderer'))
const GeoContourRenderer = lazy(() => import('./GeoContourRenderer'))
const DecompositionRenderer = lazy(() => import('./DecompositionRenderer'))
const SmallMultiplesRenderer = lazy(() => import('./SmallMultiplesRenderer'))
const GeoBubblesRenderer = lazy(() =>
  import('./GeoPointMapRenderer').then(m => ({ default: m.GeoBubblesRenderer })))
import type { ChartRendererProps } from './types'
import ModelRenderer from './ModelRenderer'
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
import AreaChartRenderer from './AreaChartRenderer'
import FunnelChartRenderer from './FunnelChartRenderer'
import RibbonChartRenderer from './RibbonChartRenderer'

export type { ChartRendererProps }

export const CHART_RENDERERS: Partial<Record<WidgetType, React.FC<ChartRendererProps>>> = {
  forecast: ForecastChartRenderer,
  sankey: SankeyChartRenderer,
  map_choropleth: GeoChoroplethRenderer,
  map_points: GeoPointsRenderer,
  map_bubbles: GeoBubblesRenderer,
  map_lines: GeoLinesRenderer,
  map_clusters: GeoClustersRenderer,
  map_pie: GeoPiesRenderer,
  map_layers: GeoLayersRenderer,
  map_density: GeoDensityRenderer,
  map_network: GeoNetworkRenderer,
  map_contour: GeoContourRenderer,
  decomposition: DecompositionRenderer,
  // Six layouts, one renderer -- it switches on data.type, which the
  // single hierarchy shaper sets from the widget type.
  tree: HierarchyRenderer,
  sunburst: HierarchyRenderer,
  icicle: HierarchyRenderer,
  dendrogram: HierarchyRenderer,
  org: HierarchyRenderer,
  circle_pack: HierarchyRenderer,
  custom_graph: CustomGraphRenderer,
  small_multiples: SmallMultiplesRenderer,
  network: NetworkGraphRenderer,
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
  area: AreaChartRenderer,
  funnel: FunnelChartRenderer,
  ribbon: RibbonChartRenderer,
  model_linear: ModelRenderer,
  model_logistic: ModelRenderer,
  model_tree: ModelRenderer,
  model_cluster: ModelRenderer,
  model_compare: ModelRenderer,
  model_score: ModelRenderer,
}
