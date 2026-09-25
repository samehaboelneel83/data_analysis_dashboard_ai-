import { useState } from 'react'
import {
  AreaChart, BarChart3, BarChart4, BarChartHorizontal, Blocks, Boxes, Brain, Building2, ChevronDown,
  Circle, CircleDashed, Cloud, Code2, Compass, CreditCard, Crosshair, Filter, Frame, Gauge,
  GanttChart, GitBranch, Globe, Grid3x3, Hash, Image, LayoutGrid, Layers, LineChart, ListFilter,
  ListTree, Map as MapIcon, MapPin, MousePointerClick, Move, Network, Orbit, PieChart, Puzzle,
  MoreVertical, Route, Rows3, Scale, ScatterChart, Search, Shapes, Sigma, SlidersHorizontal, Snowflake,
  Spline, Square, Sun, Table2, Target, Thermometer, TreeDeciduous, TrendingUp, Type, Waves, Workflow,
  type LucideIcon,
} from 'lucide-react'
import { WIDGET_CATALOG } from '../../types/report'
import { useDirection } from '../../contexts/DirectionContext'
import { useT, type MessageKey } from '../../i18n'

type CatalogEntry = typeof WIDGET_CATALOG[number]

/**
 * The chart-type gallery: the builder's "Charts" tab.
 *
 * Tiles in a three-column grid, grouped by what a reader wants to SEE
 * (compare, trend, distribution...) rather than by the catalog's storage
 * category, where thirty-two very different charts all sat under "Charts".
 *
 * The groups are a LOOKUP over the catalog, never a hardcoded list of tiles:
 * a type the lookup does not name falls back to its catalog category, so a
 * widget added to WIDGET_CATALOG still appears here without anyone touching
 * this file. (A hardcoded list once made the whole Maps category impossible
 * to add from the UI.)
 */

const GROUP_ORDER = [
  'Basic', 'Comparison', 'Trend', 'Distribution', 'Relationship', 'Part to whole',
  'Flow & hierarchy', 'Maps', 'Models', 'Tables & cards', 'Controls', 'Layout',
] as const

const GROUP_OF: Record<string, string> = {
  bar: 'Basic', line: 'Basic', area: 'Basic', pie: 'Basic', donut: 'Basic',
  table: 'Basic', kpi: 'Basic', treemap: 'Basic',

  dual_axis_bar: 'Comparison', dual_axis_line: 'Comparison', dual_axis_bar_line: 'Comparison',
  butterfly: 'Comparison', waterfall: 'Comparison', dot_plot: 'Comparison', ribbon: 'Comparison',
  gauge: 'Comparison', small_multiples: 'Comparison',

  step: 'Trend', dual_axis_time_series: 'Trend', comparative_time_series: 'Trend',
  numeric_series: 'Trend', forecast: 'Trend', schedule: 'Trend',

  histogram: 'Distribution', box_plot: 'Distribution', needle: 'Distribution',
  word_cloud: 'Distribution',

  scatter: 'Relationship', bubble: 'Relationship', bubble_change: 'Relationship',
  correlation_matrix: 'Relationship', heatmap: 'Relationship', parallel_coordinates: 'Relationship',
  vector_plot: 'Relationship', network: 'Relationship', custom_graph: 'Relationship',

  funnel: 'Part to whole', sunburst: 'Part to whole', icicle: 'Part to whole',
  circle_pack: 'Part to whole',

  sankey: 'Flow & hierarchy', decomposition: 'Flow & hierarchy', tree: 'Flow & hierarchy',
  dendrogram: 'Flow & hierarchy', org: 'Flow & hierarchy',

  crosstab: 'Tables & cards', matrix: 'Tables & cards', list: 'Tables & cards', card: 'Tables & cards',
}

/** A line glyph per type, in the one stroke family the rest of the app uses. */
const ICON_OF: Record<string, LucideIcon> = {
  bar: BarChart3, line: LineChart, area: AreaChart, pie: PieChart, donut: CircleDashed,
  table: Table2, kpi: Hash, treemap: LayoutGrid,
  dual_axis_bar: BarChart4, dual_axis_line: Spline, dual_axis_bar_line: BarChart3,
  butterfly: Move, waterfall: BarChartHorizontal, dot_plot: MoreVertical, ribbon: Waves,
  gauge: Gauge, small_multiples: Grid3x3,
  step: TrendingUp, dual_axis_time_series: LineChart, comparative_time_series: Spline,
  numeric_series: Sigma, forecast: TrendingUp, schedule: GanttChart,
  histogram: BarChart4, box_plot: Boxes, needle: SlidersHorizontal, word_cloud: Cloud,
  scatter: ScatterChart, bubble: Circle, bubble_change: Orbit, correlation_matrix: Grid3x3,
  heatmap: Blocks, parallel_coordinates: Rows3, vector_plot: Compass, network: Network,
  custom_graph: Puzzle,
  funnel: Filter, sunburst: Sun, icicle: Snowflake, circle_pack: Circle,
  sankey: Workflow, decomposition: GitBranch, tree: TreeDeciduous, dendrogram: ListTree, org: Building2,
  crosstab: Table2, matrix: Grid3x3, list: Rows3, card: CreditCard,
  text: Type, image: Image, web_content: Globe, custom_visual: Puzzle, script: Code2,
  shape: Square, button: MousePointerClick, slicer: ListFilter,
  map_choropleth: MapIcon, map_points: MapPin, map_lines: Route, map_clusters: Crosshair,
  map_pie: PieChart, map_layers: Layers, map_density: Thermometer, map_contour: Waves,
  map_network: Compass, map_bubbles: Circle,
  container: Frame,
  model_linear: TrendingUp, model_logistic: Spline, model_tree: GitBranch, model_cluster: Shapes,
  model_compare: Scale, model_score: Target,
}

/** The gallery's glyph for a widget type, for anywhere else that names one. */
export const chartIcon = (type: string): LucideIcon => ICON_OF[type] ?? Brain

/** The catalog's display name for a widget type ("bar" -> "Bar Chart"). */
export const chartLabel = (type: string): string =>
  WIDGET_CATALOG.find(w => w.type === type)?.label ?? type

const groupOf = (w: CatalogEntry) => GROUP_OF[w.type] ?? w.category

/** The order a group's tiles appear in when it matters (the basics lead with
 *  the charts people reach for first); anything unlisted keeps catalog order. */
const TILE_ORDER = ['bar', 'line', 'area', 'pie', 'donut', 'table', 'kpi', 'treemap',
  'dual_axis_bar', 'dual_axis_line', 'dual_axis_bar_line', 'butterfly', 'waterfall', 'dot_plot']

/** Tile names: short enough for a third of the panel. The full catalog label
 *  stays the button's accessible name and its tooltip. */
const SHORT: Record<string, string> = {
  kpi: 'KPI', dual_axis_bar_line: 'Bar + line', dual_axis_time_series: 'Dual axis time',
  comparative_time_series: 'Compare series', numeric_series: 'Numeric series',
  schedule: 'Gantt', parallel_coordinates: 'Parallel', correlation_matrix: 'Correlation',
  bubble_change: 'Bubble change', decomposition: 'Decomposition', custom_visual: 'Custom visual',
  model_score: 'Score model', model_compare: 'Compare models', map_choropleth: 'Choropleth',
}

/** "Bar Chart" -> "Bar": the tile is small and the group already says chart. */
const shortLabel = (w: CatalogEntry) => SHORT[w.type] ?? w.label
  .replace(/\s+(Chart|Plot|Card)$/i, '')
  .replace(/^Dual Axis /, 'Dual axis ')

export default function ChartGallery({ query, onQuery, onAdd }: {
  query: string
  onQuery: (q: string) => void
  onAdd: (type: CatalogEntry['type']) => void
}) {
  const [closed, setClosed] = useState<Record<string, boolean>>({})
  const t = useT()
  // Arabic names for the groups and the common tiles; everything else keeps
  // the catalog's English label. Search matches BOTH, so either works.
  const ar = useDirection().language === 'ar'
  const groupKey = (g: string) => `gallery.group.${g.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')}` as MessageKey
  const groupName = (g: string) => { const k = groupKey(g); const v = t(k); return v && v !== k ? v : g }
  const tileName = (w: CatalogEntry) => {
    if (!ar) return shortLabel(w)
    const k = `gallery.tile.${w.type}` as MessageKey
    const v = t(k)
    return v && v !== k ? v : shortLabel(w)
  }
  const q = query.trim().toLowerCase()
  const hit = (w: CatalogEntry) => !q
    || w.label.toLowerCase().includes(q)
    || w.category.toLowerCase().includes(q)
    || groupOf(w).toLowerCase().includes(q)
    || w.type.toLowerCase().includes(q)
    || tileName(w).toLowerCase().includes(q)
    || groupName(groupOf(w)).toLowerCase().includes(q)

  const groups = [...new Set(WIDGET_CATALOG.map(groupOf))]
    .sort((a, b) => {
      const ia = GROUP_ORDER.indexOf(a as typeof GROUP_ORDER[number])
      const ib = GROUP_ORDER.indexOf(b as typeof GROUP_ORDER[number])
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib)
    })

  const anyHit = WIDGET_CATALOG.some(hit)

  return (
    <div className="dl-gallery">
      <label className="dl-gallery__search">
        <Search size={14} aria-hidden />
        <input value={query} onChange={e => onQuery(e.target.value)}
          aria-label={t('gallery.find')} placeholder={t('gallery.search', { n: WIDGET_CATALOG.length })} />
      </label>

      {!anyHit && (
        <p className="dl-gallery__none">{t('gallery.none', { q: query })}</p>
      )}

      {groups.map(group => {
        const rank = (w: CatalogEntry) => { const i = TILE_ORDER.indexOf(w.type); return i === -1 ? 999 : i }
        const items = WIDGET_CATALOG.filter(w => groupOf(w) === group && hit(w))
          .map((w, i) => ({ w, i })).sort((a, b) => rank(a.w) - rank(b.w) || a.i - b.i).map(x => x.w)
        if (items.length === 0) return null
        // A search opens every group it matched: a hit hidden inside a folded
        // section is a result the reader cannot see.
        const isClosed = !q && closed[group]
        const bodyId = `gallery-${group.toLowerCase().replace(/\W+/g, '-')}`
        return (
          <section key={group} className="dl-gallery__group">
            <button type="button" className="dl-gallery__head" aria-expanded={!isClosed} aria-controls={bodyId}
              onClick={() => setClosed(c => ({ ...c, [group]: !c[group] }))}>
              <span aria-hidden className={`dl-gallery__chev${isClosed ? ' dl-gallery__chev--closed' : ''}`}>
                <ChevronDown size={13} />
              </span>
              <span className="dl-gallery__name">{groupName(group)}</span>
              <span className="dl-gallery__count">{items.length}</span>
            </button>
            {!isClosed && (
              <div id={bodyId} className="dl-gallery__grid">
                {items.map(w => {
                  const Icon = ICON_OF[w.type] ?? Brain
                  return (
                    <button key={w.type} type="button" className="dl-gallery__tile"
                      onClick={() => onAdd(w.type)} title={w.label} aria-label={w.label}>
                      <Icon size={18} strokeWidth={1.9} aria-hidden />
                      <span className="dl-gallery__label">{tileName(w)}</span>
                    </button>
                  )
                })}
              </div>
            )}
          </section>
        )
      })}
    </div>
  )
}
