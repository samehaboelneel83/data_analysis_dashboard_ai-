import type { DisplayRule } from '../lib/displayRules'

export type WidgetType =
  | 'bar' | 'line' | 'pie' | 'donut' | 'scatter' | 'treemap' | 'step' | 'dot_plot' | 'needle'
  | 'histogram' | 'butterfly' | 'dual_axis_bar' | 'dual_axis_line' | 'dual_axis_bar_line' | 'dual_axis_time_series' | 'comparative_time_series' | 'numeric_series'
  | 'bubble' | 'bubble_change' | 'correlation_matrix' | 'heatmap' | 'parallel_coordinates' | 'box_plot' | 'waterfall' | 'gauge' | 'schedule' | 'vector_plot' | 'word_cloud'
  | 'kpi' | 'table' | 'crosstab' | 'list' | 'text' | 'button' | 'slicer'
  | 'area' | 'funnel' | 'ribbon' | 'card' | 'matrix' | 'image' | 'shape' | 'web_content' | 'custom_visual'
  | 'map_choropleth' | 'map_points' | 'map_bubbles' | 'map_lines' | 'map_clusters'
  | 'map_pie' | 'map_layers' | 'map_density' | 'map_network' | 'map_contour'
  | 'network'
  | 'container' | 'forecast' | 'sankey' | 'decomposition' | 'small_multiples'
  | 'script'
  | 'tree' | 'sunburst' | 'icicle' | 'dendrogram' | 'org' | 'circle_pack'
| 'custom_graph'
  | 'model_linear' | 'model_logistic' | 'model_tree' | 'model_cluster' | 'model_compare' | 'model_score'

export interface Widget {
  id: number
  page_id: number
  widget_type: WidgetType
  title: string
  config: Record<string, unknown>
  layout: { x: number; y: number; w: number; h: number }
  created_at: string
}

export type PageType = 'normal' | 'hidden' | 'popup' | 'tooltip' | 'drillthrough'

export interface ReportPage {
  id: number
  report_id: number
  name: string
  title?: string
  page_type: PageType
  prompt_column?: string
  prompt_label?: string
  position: number
  widgets: Widget[]
  created_at: string
  page_size: '16:9' | '4:3' | 'custom'
  custom_width?: number | null
  custom_height?: number | null
  /** A picture the page's objects sit on. Objects set to a transparent
   *  background let it show through. http(s) or a path on this server; the
   *  router refuses anything else. */
  background_url?: string | null
  /** packed = tiled recipes (default). free = opt-in canvas. Absent/null on
   *  legacy pages: the builder auto-packs them once into Executive. */
  layout_mode?: 'packed' | 'free' | null
  layout_template?: string | null
  /** Mobile order/hidden plus page-level settings that ride in the same JSON
      (interaction_mode) -- the pages table gains no new columns. */
  mobile_layout?: { order?: number[]; hidden?: number[]; interaction_mode?: 'manual' | 'linked' | 'oneway' | 'twoway' } | null
  /** The page's interaction mode as the PUBLIC surfaces publish it: shared
   *  links and embeds get this derived field instead of `mobile_layout`,
   *  because the rest of that blob is builder state an anonymous viewer has
   *  no use for. Absent in the authenticated payload, where the builder reads
   *  the mode out of `mobile_layout` directly. */
  interaction_mode?: 'manual' | 'linked' | 'oneway' | 'twoway'
}

export interface BookmarkState {
  pageId: number
  activeFilters: { column: string; value: unknown; label: string; sourceWidgetId: number; sourcePageId: number }[]
  promptValues: Record<number, string>
  hiddenWidgetIds: number[]
}

export interface Bookmark {
  id: number
  report_id: number
  name: string
  position: number
  state: BookmarkState
  created_at: string
}

export interface CommonFilter {
  id: number
  column: string
  op: string
  value: unknown
}

export interface Report {
  id: number
  name: string
  description?: string
  dataset_id: number | null
  additional_dataset_ids: number[]
  theme: string
  /** Bumped server-side by every mutation to this report or anything nested under
   *  it. Compared against a poll to notice that another session changed it. */
  revision?: number
  /** The requesting viewer's capability on this report: 'view' | 'edit' | 'data'.
      Set by the read endpoint; the client mirrors it to hide what the server refuses. */
  my_capability?: 'view' | 'edit' | 'data'
  /** Authorship: this viewer created the report. Set by the read AND list
      endpoints. Drives the My-workspaces/Granted grouping, never permissions
      (those are my_capability's job). Absent/false for pre-authorship rows. */
  is_mine?: boolean
  /** The author's user id; null/absent on legacy pre-authorship rows, where
      the publish/grant regime does not apply at all. */
  created_by?: number | null
  /** Direct publication flag on an authored dashboard. False = draft (private
      to the author, admins and grantees) -- though a published FOLDER may
      still publish it; the viewer-side truth is always my_capability. */
  published?: boolean
  /** Sensitivity label (Public/Internal/Confidential/Restricted) or null/absent. */
  classification?: string | null
  /** Report-level filters applied to every widget (defined once, propagate everywhere). */
  common_filters?: CommonFilter[]
  pages: ReportPage[]
  created_at: string
  updated_at: string
  /** Applied to every object on every page, ahead of any widget-level rules. */
  display_rules?: DisplayRule[]
}

export interface HierarchyNode {
  id: number
  dataset_id: number
  parent_id: number | null
  name: string
  node_type: 'folder' | 'dimension' | 'measure' | 'date' | 'text'
  column_name?: string
  aggregation?: string
  format?: string
  position: number
  created_at: string
}

export const WIDGET_CATALOG = [
  { type: 'bar'      as WidgetType, label: 'Bar Chart',  category: 'Charts',   icon: '▬', defaultW: 6, defaultH: 5 },
  { type: 'line'     as WidgetType, label: 'Line Chart', category: 'Charts',   icon: '↗', defaultW: 6, defaultH: 5 },
  { type: 'pie'      as WidgetType, label: 'Pie Chart',  category: 'Charts',   icon: '◔', defaultW: 4, defaultH: 5 },
  { type: 'donut'    as WidgetType, label: 'Donut',      category: 'Charts',   icon: '◯', defaultW: 4, defaultH: 5 },
  { type: 'scatter'  as WidgetType, label: 'Scatter',    category: 'Charts',   icon: '⁘', defaultW: 6, defaultH: 5 },
  { type: 'treemap'  as WidgetType, label: 'Treemap',    category: 'Charts',   icon: '⊞', defaultW: 6, defaultH: 5 },
  { type: 'step' as WidgetType, label: 'Step Plot', category: 'Charts', icon: '⊓', defaultW: 6, defaultH: 5 },
  { type: 'dot_plot' as WidgetType, label: 'Dot Plot', category: 'Charts', icon: '⁚', defaultW: 6, defaultH: 5 },
  { type: 'needle' as WidgetType, label: 'Needle Plot', category: 'Charts', icon: '↕', defaultW: 6, defaultH: 5 },
  { type: 'histogram' as WidgetType, label: 'Histogram', category: 'Charts', icon: '▤', defaultW: 6, defaultH: 5 },
  { type: 'butterfly' as WidgetType, label: 'Butterfly Chart', category: 'Charts', icon: '⋈', defaultW: 6, defaultH: 5 },
  { type: 'dual_axis_bar' as WidgetType, label: 'Dual Axis Bar', category: 'Charts', icon: '▥', defaultW: 6, defaultH: 5 },
  { type: 'dual_axis_line' as WidgetType, label: 'Dual Axis Line', category: 'Charts', icon: '⤢', defaultW: 6, defaultH: 5 },
  { type: 'dual_axis_bar_line' as WidgetType, label: 'Dual Axis Bar-Line', category: 'Charts', icon: '▧', defaultW: 6, defaultH: 5 },
  { type: 'dual_axis_time_series' as WidgetType, label: 'Dual Axis Time Series', category: 'Charts', icon: '⟿', defaultW: 6, defaultH: 5 },
  { type: 'comparative_time_series' as WidgetType, label: 'Comparative Time Series', category: 'Charts', icon: '⇄', defaultW: 6, defaultH: 5 },
  { type: 'numeric_series' as WidgetType, label: 'Numeric Series Plot', category: 'Charts', icon: '∿', defaultW: 6, defaultH: 5 },
  { type: 'bubble' as WidgetType, label: 'Bubble Plot', category: 'Charts', icon: '◉', defaultW: 6, defaultH: 5 },
  { type: 'bubble_change' as WidgetType, label: 'Bubble Change Plot', category: 'Charts', icon: '◎', defaultW: 6, defaultH: 5 },
  { type: 'correlation_matrix' as WidgetType, label: 'Correlation Matrix', category: 'Charts', icon: '▦', defaultW: 6, defaultH: 6 },
  { type: 'heatmap' as WidgetType, label: 'Heat Map', category: 'Charts', icon: '▩', defaultW: 6, defaultH: 6 },
  { type: 'parallel_coordinates' as WidgetType, label: 'Parallel Coordinates', category: 'Charts', icon: '⫴', defaultW: 7, defaultH: 5 },
  { type: 'box_plot' as WidgetType, label: 'Box Plot', category: 'Charts', icon: '⊡', defaultW: 6, defaultH: 5 },
  { type: 'waterfall' as WidgetType, label: 'Waterfall Chart', category: 'Charts', icon: '▨', defaultW: 6, defaultH: 5 },
  { type: 'gauge' as WidgetType, label: 'Gauge', category: 'Charts', icon: '◐', defaultW: 4, defaultH: 4 },
  { type: 'schedule' as WidgetType, label: 'Schedule (Gantt)', category: 'Charts', icon: '▭', defaultW: 7, defaultH: 6 },
  { type: 'vector_plot' as WidgetType, label: 'Vector Plot', category: 'Charts', icon: '⇗', defaultW: 6, defaultH: 6 },
  { type: 'word_cloud' as WidgetType, label: 'Word Cloud', category: 'Charts', icon: '☁', defaultW: 6, defaultH: 5 },
  { type: 'area' as WidgetType, label: 'Area Chart', category: 'Charts', icon: '▲', defaultW: 6, defaultH: 5 },
  { type: 'funnel' as WidgetType, label: 'Funnel', category: 'Charts', icon: '▽', defaultW: 5, defaultH: 6 },
  { type: 'ribbon' as WidgetType, label: 'Ribbon Chart', category: 'Charts', icon: '▬', defaultW: 7, defaultH: 5 },
  { type: 'kpi'      as WidgetType, label: 'KPI Card',   category: 'Controls', icon: '◈', defaultW: 3, defaultH: 3 },
  { type: 'table'    as WidgetType, label: 'Table',      category: 'Controls', icon: '☰', defaultW: 6, defaultH: 6 },
  { type: 'crosstab' as WidgetType, label: 'Crosstab',   category: 'Controls', icon: '⊟', defaultW: 7, defaultH: 6 },
  { type: 'matrix'   as WidgetType, label: 'Matrix',     category: 'Controls', icon: '⊠', defaultW: 7, defaultH: 6 },
  { type: 'list'     as WidgetType, label: 'List',       category: 'Controls', icon: '≡', defaultW: 3, defaultH: 6 },
  { type: 'text'     as WidgetType, label: 'Text Block',  category: 'Controls', icon: 'T', defaultW: 4, defaultH: 3 },
  { type: 'image'    as WidgetType, label: 'Image',      category: 'Controls', icon: '⛶', defaultW: 4, defaultH: 4 },
  { type: 'web_content' as WidgetType, label: 'Web Content', category: 'Controls', icon: '🌐', defaultW: 5, defaultH: 5 },
  { type: 'custom_visual' as WidgetType, label: 'Custom Visual', category: 'Controls', icon: '🧩', defaultW: 5, defaultH: 5 },
  { type: 'script'   as WidgetType, label: 'Script',      category: 'Controls', icon: '⌨', defaultW: 6, defaultH: 5 },
  { type: 'shape'    as WidgetType, label: 'Shape',      category: 'Controls', icon: '▭', defaultW: 3, defaultH: 3 },
  { type: 'button'   as WidgetType, label: 'Button',     category: 'Controls', icon: '▶', defaultW: 2, defaultH: 2 },
  { type: 'slicer'   as WidgetType, label: 'Slicer',     category: 'Controls', icon: '☑', defaultW: 3, defaultH: 5 },
  { type: 'card'     as WidgetType, label: 'Card',       category: 'Controls', icon: '▤', defaultW: 4, defaultH: 3 },
  { type: 'map_choropleth' as WidgetType, label: 'Choropleth Map', category: 'Maps', icon: '🗺', defaultW: 6, defaultH: 5 },
  { type: 'map_points'     as WidgetType, label: 'Point Map',      category: 'Maps', icon: '📍', defaultW: 6, defaultH: 5 },
  { type: 'map_lines'      as WidgetType, label: 'Line Map',       category: 'Maps', icon: '🛫', defaultW: 6, defaultH: 5 },
  { type: 'map_clusters'   as WidgetType, label: 'Cluster Map',    category: 'Maps', icon: '🎯', defaultW: 6, defaultH: 5 },
  { type: 'map_pie'        as WidgetType, label: 'Pie Map',        category: 'Maps', icon: '🥧', defaultW: 6, defaultH: 5 },
  { type: 'map_layers'     as WidgetType, label: 'Layered Map',    category: 'Maps', icon: '🗺', defaultW: 6, defaultH: 5 },
  { type: 'map_density'    as WidgetType, label: 'Density Map',    category: 'Maps', icon: '🌡', defaultW: 6, defaultH: 5 },
  { type: 'map_contour'    as WidgetType, label: 'Contour Map',    category: 'Maps', icon: '〰', defaultW: 6, defaultH: 5 },
  { type: 'map_network'    as WidgetType, label: 'Geo Network',    category: 'Maps', icon: '🧭', defaultW: 6, defaultH: 5 },
  { type: 'map_bubbles'    as WidgetType, label: 'Bubble Map',     category: 'Maps', icon: '⬤', defaultW: 6, defaultH: 5 },
  { type: 'container'      as WidgetType, label: 'Container',      category: 'Layout', icon: '▣', defaultW: 6, defaultH: 6 },
  { type: 'forecast'       as WidgetType, label: 'Forecast',       category: 'Analytics', icon: '📈', defaultW: 6, defaultH: 5 },
  { type: 'sankey'         as WidgetType, label: 'Flow (Sankey)',  category: 'Analytics', icon: '⇶', defaultW: 6, defaultH: 5 },
  { type: 'network'        as WidgetType, label: 'Network Graph',  category: 'Analytics', icon: '🕸', defaultW: 6, defaultH: 5 },
  { type: 'decomposition'  as WidgetType, label: 'Decomposition Tree', category: 'Analytics', icon: '🌳', defaultW: 5, defaultH: 6 },
  { type: 'tree'           as WidgetType, label: 'Tree',            category: 'Analytics', icon: '🌲', defaultW: 4, defaultH: 6 },
  { type: 'sunburst'       as WidgetType, label: 'Sunburst',        category: 'Analytics', icon: '🌞', defaultW: 5, defaultH: 5 },
  { type: 'icicle'         as WidgetType, label: 'Icicle',          category: 'Analytics', icon: '🧊', defaultW: 6, defaultH: 4 },
  { type: 'circle_pack'    as WidgetType, label: 'Circle Packing', category: 'Analytics', icon: '⚪', defaultW: 5, defaultH: 5 },
  { type: 'custom_graph'   as WidgetType, label: 'Custom Graph',   category: 'Charts', icon: '🧩', defaultW: 6, defaultH: 5 },
  { type: 'dendrogram'     as WidgetType, label: 'Dendrogram',      category: 'Analytics', icon: '🌿', defaultW: 6, defaultH: 5 },
  { type: 'org'            as WidgetType, label: 'Org Chart',       category: 'Analytics', icon: '🏢', defaultW: 6, defaultH: 5 },
  { type: 'small_multiples' as WidgetType, label: 'Small Multiples', category: 'Analytics', icon: '▦', defaultW: 6, defaultH: 5 },
  // Models as living objects (Phase 3): each one re-fits under the page's
  // filters and renders its population, fit and diagnostics on the canvas.
  { type: 'model_linear'   as WidgetType, label: 'Linear Regression',   category: 'Models', icon: '⟋', defaultW: 7, defaultH: 7 },
  { type: 'model_logistic' as WidgetType, label: 'Logistic Regression', category: 'Models', icon: '∫', defaultW: 7, defaultH: 7 },
  { type: 'model_tree'     as WidgetType, label: 'Decision Tree',       category: 'Models', icon: '⑂', defaultW: 7, defaultH: 7 },
  { type: 'model_cluster'  as WidgetType, label: 'Clustering',          category: 'Models', icon: '⁂', defaultW: 7, defaultH: 7 },
  { type: 'model_compare'  as WidgetType, label: 'Model Comparison',    category: 'Models', icon: '⚖', defaultW: 7, defaultH: 6 },
  { type: 'model_score'    as WidgetType, label: 'Score with Saved Model', category: 'Models', icon: '🎯', defaultW: 6, defaultH: 6 },
]

export const ROLE_TO_CONFIG_KEY: Record<string, string> = { category: 'dimension', category2: 'dimension2', measure: 'measure' }
export const configKeyFor = (role: string) => ROLE_TO_CONFIG_KEY[role] ?? role

export interface RoleField {
  role: string
  label?: string
  required: boolean
  multi?: boolean
}

// Declares which role fields WidgetConfigPanel should render for each widget type.
// Phase 0 mirrors today's dimension/dimension2/measure fields exactly — no new roles
// are introduced yet. Phase 1+ chart types add their own entries here (size/color/group/
// start/end roles) as they're built.
/**
 * Widget types whose data comes from the dual-series shaper, and therefore the
 * only ones where a SECOND aggregation means anything.
 *
 * Deliberately not "every widget with a measure2 role": a bubble chart has a
 * second measure too, but its shaper aggregates differently, so offering the
 * control there would be another instance of a setting the server ignores.
 * Mirrors the six entries mapped to `shape_dual_series` in widget_data.py.
 */
export const DUAL_MEASURE_WIDGETS: readonly string[] = [
  'butterfly', 'dual_axis_bar', 'dual_axis_line', 'dual_axis_bar_line',
  'dual_axis_time_series', 'comparative_time_series',
]

/** What kind of column a field role can actually use.
 *
 *  Only `measure` and `measure2` were ever filtered, so a bar chart's per-bar
 *  `target`, a bubble's `size` and `color`, every map's `lat`/`lon` and a vector
 *  plot's `direction` all offered the whole column list — a text column one click
 *  away in sixteen widget types. Nothing downstream objects: a text `target` is
 *  silently dropped and text coordinates return `rows: [], dropped: 120000`, a
 *  blank map with a 200 response. The only place to catch it is the list that
 *  offered the choice.
 *
 *  Unknown roles take anything, so a role added later is usable before it is
 *  classified here rather than presenting an empty dropdown.
 */
export type RoleColumnKind = 'numeric' | 'datetime' | 'any'

const NUMERIC_ROLES = new Set([
  'measure', 'measure2', 'measures', 'size', 'target', 'color',
  'lat', 'lon', 'lat2', 'lon2', 'direction',
])
//: `animation` is deliberately absent: bubble_change animates over a date OR an
//: ordered category, and narrowing it would remove a legitimate choice.
const DATE_ROLES = new Set(['start', 'end'])

export function roleAccepts(role: string): RoleColumnKind {
  if (NUMERIC_ROLES.has(role)) return 'numeric'
  if (DATE_ROLES.has(role)) return 'datetime'
  return 'any'
}

/**
 * Map widgets that draw filled REGIONS, and so can be pointed at an uploaded
 * boundary set instead of the built-in countries.
 *
 * Only the shape-filling maps. A point, bubble, cluster, line or network map
 * plots coordinates and uses the world purely as a backdrop — swapping that
 * backdrop for a set of governorates would hide every mark outside them, which
 * is a different feature and probably a bug.
 */
export const BOUNDARY_SET_WIDGETS = new Set<string>([
  'map_choropleth',
])

/** Maps that accept author-placed pins.
 *
 *  The coordinate maps only. A pin is a lat/lon annotation, so it belongs where
 *  the map already projects coordinates — on a choropleth the author would be
 *  placing a point on a chart made of shapes, with no coordinate to anchor it
 *  to and nothing on screen at that scale to relate it to. */
export const PIN_WIDGETS = new Set<string>([
  'map_points', 'map_bubbles',
])

export const ROLE_SPECS: Record<WidgetType, RoleField[]> = {
  bar:      [{ role: 'category',  label: 'Dimension (Group / X-axis)',   required: true },
             { role: 'category2', label: 'Series (for stacking)',        required: false },
             { role: 'measure',   label: 'Measure (numeric column)',     required: false },
             { role: 'target',    label: 'Target (per-bar attainment)', required: false }],
  line:     [{ role: 'category', label: 'Dimension (Group / X-axis)', required: true },
             { role: 'measure',  label: 'Measure (numeric column)',   required: false }],
  pie:      [{ role: 'category', label: 'Dimension (Group / X-axis)', required: true },
             { role: 'measure',  label: 'Measure (numeric column)',   required: false }],
  donut:    [{ role: 'category', label: 'Dimension (Group / X-axis)', required: true },
             { role: 'measure',  label: 'Measure (numeric column)',   required: false }],
  scatter:  [{ role: 'category', label: 'Dimension (Group / X-axis)', required: true },
             { role: 'measure',  label: 'Measure (numeric column)',   required: false }],
  treemap:  [{ role: 'category', label: 'Dimension (Group / X-axis)', required: true },
             { role: 'measure',  label: 'Measure (numeric column)',   required: false }],
  step: [{ role: 'category', label: 'Dimension (X-axis)',       required: true },
         { role: 'measure',  label: 'Measure (numeric column)', required: false }],
  dot_plot: [{ role: 'category', label: 'Dimension (Y-axis)',       required: true },
             { role: 'measure',  label: 'Measure (numeric column)', required: false }],
  needle: [{ role: 'category', label: 'Dimension (X-axis)',       required: true },
           { role: 'measure',  label: 'Measure (numeric column)', required: false }],
  histogram: [{ role: 'measure', label: 'Measure (numeric column)', required: true }],
  butterfly: [{ role: 'category', label: 'Dimension (Y-axis)', required: true },
              { role: 'measure',  label: 'Left side',          required: true },
              { role: 'measure2', label: 'Right side',         required: true }],
  dual_axis_bar: [{ role: 'category', label: 'Dimension (X-axis)', required: true },
                  { role: 'measure',  label: 'Bars (left axis)',   required: true },
                  { role: 'measure2', label: 'Bars (right axis)',  required: true }],
  dual_axis_line: [{ role: 'category', label: 'Dimension (X-axis)', required: true },
                   { role: 'measure',  label: 'Line (left axis)',   required: true },
                   { role: 'measure2', label: 'Line (right axis)',  required: true }],
  dual_axis_bar_line: [{ role: 'category', label: 'Dimension (X-axis)', required: true },
                       { role: 'measure',  label: 'Bars (left axis)',  required: true },
                       { role: 'measure2', label: 'Line (right axis)', required: true }],
  dual_axis_time_series: [{ role: 'start',    label: 'Date',              required: true },
                          { role: 'measure',  label: 'Line (left axis)',  required: true },
                          { role: 'measure2', label: 'Line (right axis)', required: true }],
  comparative_time_series: [{ role: 'start',    label: 'Date',     required: true },
                            { role: 'measure',  label: 'Series A', required: true },
                            { role: 'measure2', label: 'Series B', required: true }],
  numeric_series: [{ role: 'measure',  label: 'X axis (numeric)', required: true },
                   { role: 'measure2', label: 'Y axis (numeric)', required: true }],
  bubble: [{ role: 'category', label: 'Dimension (one bubble per group)', required: true },
           { role: 'measure',  label: 'X axis',                          required: true },
           { role: 'measure2', label: 'Y axis',                          required: true },
           { role: 'size',     label: 'Bubble size',                     required: true },
           { role: 'color',    label: 'Color (numeric, optional)',       required: false },
           { role: 'group',    label: 'Group (legend, optional)',        required: false }],
  bubble_change: [{ role: 'category',   label: 'Dimension (one bubble per group)', required: true },
                  { role: 'measure',    label: 'X axis',                          required: true },
                  { role: 'measure2',   label: 'Y axis',                          required: true },
                  { role: 'size',       label: 'Bubble size',                     required: true },
                  { role: 'color',      label: 'Color (numeric, optional)',       required: false },
                  { role: 'animation',  label: 'Animate by',                      required: true }],
  correlation_matrix: [{ role: 'measures', label: 'Measures', multi: true, required: true }],
  heatmap: [{ role: 'category',  label: 'Rows (Y-axis)',    required: true },
            { role: 'category2', label: 'Columns (X-axis)', required: true },
            { role: 'measure',   label: 'Cell value',       required: true }],
  parallel_coordinates: [{ role: 'measures', label: 'Measures (ordered)', multi: true, required: true }],
  box_plot: [{ role: 'category', label: 'Dimension (one box per group)', required: true },
             { role: 'measure',  label: 'Measure (numeric column)',      required: true }],
  waterfall: [{ role: 'category', label: 'Dimension (running order)', required: true },
              { role: 'measure',  label: 'Delta (numeric column)',    required: true }],
  gauge: [{ role: 'measure', label: 'Value',                    required: true },
          { role: 'target',  label: 'Target (column, optional)', required: false }],
  schedule: [{ role: 'category', label: 'Task',                      required: true },
             { role: 'start',    label: 'Start date',                required: true },
             { role: 'end',      label: 'End date',                  required: true },
             { role: 'group',    label: 'Group (color, optional)',   required: false }],
  vector_plot: [{ role: 'measure',   label: 'X axis',                          required: true },
                { role: 'measure2',  label: 'Y axis',                          required: true },
                { role: 'size',      label: 'Magnitude',                       required: true },
                { role: 'direction', label: 'Direction (degrees, 0=east, CCW)', required: true }],
  word_cloud: [{ role: 'category', label: 'Word text',                required: true },
               { role: 'measure',  label: 'Size weight (optional)',   required: false }],
  area:     [{ role: 'category', label: 'Dimension (Group / X-axis)', required: true },
             { role: 'measure',  label: 'Measure (numeric column)',   required: false }],
  funnel:   [{ role: 'category', label: 'Stage', required: true },
             { role: 'measure',  label: 'Value',  required: false }],
  ribbon:   [{ role: 'category',  label: 'Rows (Y-axis)',    required: true },
             { role: 'category2', label: 'Columns (X-axis)', required: true },
             { role: 'measure',   label: 'Cell value',       required: true }],
  // A KPI is one number: the measure is what it needs; a dimension is optional
  // (it turns the card into "the value for the top group").
  kpi:      [{ role: 'category', label: 'Dimension (Group / X-axis)', required: false },
             { role: 'measure',  label: 'Measure (numeric column)',   required: true }],
  table:    [{ role: 'category', label: 'Dimension (Group / X-axis)', required: true },
             { role: 'measure',  label: 'Measure (numeric column)',   required: false }],
  crosstab: [{ role: 'category',  label: 'Dimension (Group / X-axis)', required: true },
             { role: 'category2', label: 'Column Pivot',               required: false },
             { role: 'measure',   label: 'Measure (numeric column)',   required: false }],
  matrix:   [{ role: 'category',  label: 'Rows',                       required: true },
             { role: 'category2', label: 'Columns',                    required: false },
             { role: 'measure',   label: 'Values (numeric column)',    required: false }],
  list:     [{ role: 'category', label: 'Dimension (Group / X-axis)', required: true },
             { role: 'measure',  label: 'Measure (numeric column)',   required: false }],
  text:     [],
  button:   [],
  image:    [],
  shape:    [],
  web_content: [],
  custom_visual: [{ role: 'category', label: 'Dimension (Group)', required: false },
                  { role: 'measure',  label: 'Measure (numeric column)', required: false }],
  // A script picks its own columns out of `df`; a role field here would be a
  // second, contradictory answer to a question the code already answers.
  script:   [],
  slicer:   [{ role: 'category', label: 'Field to filter by', required: true }],
  card:     [{ role: 'measures', label: 'Fields', multi: true, required: true }],
  map_choropleth: [
    { role: 'category', label: 'Country', required: true },
    { role: 'measure',  label: 'Measure', required: true },
  ],
  // Country OR lat/lon: the country role is what makes these usable on data with no
  // coordinate columns (plotted at the country centroid); lat/lon takes over when set.
  map_points: [
    { role: 'category', label: 'Country', required: false },
    { role: 'lat',      label: 'Latitude', required: false },
    { role: 'lon',      label: 'Longitude', required: false },
    { role: 'measure',  label: 'Measure', required: false },
  ],
  container: [],
  forecast: [
    { role: 'category', label: 'Date column',  required: true },
    { role: 'measure',  label: 'Measure',      required: true },
  ],
  sankey: [
    { role: 'category',  label: 'Source',      required: true },
    { role: 'category2', label: 'Target',      required: true },
    { role: 'measure',   label: 'Weight',      required: false },
  ],
  map_bubbles: [
    { role: 'category', label: 'Country', required: false },
    { role: 'lat',      label: 'Latitude', required: false },
    { role: 'lon',      label: 'Longitude', required: false },
    { role: 'measure',  label: 'Size', required: false },
  ],
  map_lines: [
    { role: 'lat',      label: 'Origin latitude',  required: true },
    { role: 'lon',      label: 'Origin longitude', required: true },
    { role: 'lat2',     label: 'Destination latitude',  required: true },
    { role: 'lon2',     label: 'Destination longitude', required: true },
    { role: 'category', label: 'Label',  required: false },
    { role: 'measure',  label: 'Line weight', required: false },
  ],
  map_clusters: [
    { role: 'lat',      label: 'Latitude',  required: true },
    { role: 'lon',      label: 'Longitude', required: true },
    { role: 'measure',  label: 'Measure (summed per cluster)', required: false },
  ],
  network: [
    { role: 'category',  label: 'Source', required: true },
    { role: 'category2', label: 'Target', required: true },
    { role: 'measure',   label: 'Link weight', required: false },
  ],
  // Only the number is configured. The fields to break it down BY are chosen
  // while reading, not while authoring -- that is the whole point of the
  // visual, so pinning them into the config would defeat it.
  decomposition: [
    { role: 'measure', label: 'Number to explain', required: false },
  ],
  // `facet_by` and `inner_widget_type` are widget options rather than field
  // roles: the panels are the SAME chart, so the chart's own roles apply
  // inside each one.
  // One shaper drives all six, so they share one set of roles. `levels`
  // (and the parent-child pair) are widget options rather than field roles:
  // a hierarchy is an ORDERED list of columns, which a role slot cannot express.
  tree: [{ role: 'measure', label: 'Value (optional)', required: false }],
  sunburst: [{ role: 'measure', label: 'Value', required: false }],
  icicle: [{ role: 'measure', label: 'Value', required: false }],
  circle_pack: [{ role: 'measure', label: 'Value', required: false }],
  // The category only: each LAYER carries its own measure, so a measure role
  // here would be a seventh field the builder never reads.
  custom_graph: [{ role: 'category', label: 'Category', required: true }],
  dendrogram: [{ role: 'measure', label: 'Value (optional)', required: false }],
  org: [{ role: 'measure', label: 'Value (optional)', required: false }],
  small_multiples: [
    { role: 'category', label: 'Category', required: true },
    { role: 'measure',  label: 'Measure', required: false },
  ],
  map_pie: [
    { role: 'category',  label: 'Country',   required: true },
    { role: 'category2', label: 'Slice by',  required: true },
    { role: 'measure',   label: 'Measure',   required: false },
  ],
  map_layers: [
    { role: 'category',  label: 'Country (region layer)', required: false },
    { role: 'measure',   label: 'Region measure',         required: false },
    { role: 'lat',       label: 'Latitude (point layer)', required: false },
    { role: 'lon',       label: 'Longitude (point layer)', required: false },
    { role: 'measure2',  label: 'Point size',             required: false },
  ],
  map_density: [
    { role: 'lat',      label: 'Latitude',  required: true },
    { role: 'lon',      label: 'Longitude', required: true },
    { role: 'measure',  label: 'Measure (summed per cell)', required: false },
  ],
  map_contour: [
    { role: 'lat',     label: 'Latitude',  required: true },
    { role: 'lon',     label: 'Longitude', required: true },
    { role: 'measure', label: 'Weight (optional)', required: false },
  ],
  map_network: [
    { role: 'category',  label: 'Source name', required: true },
    { role: 'category2', label: 'Target name', required: true },
    { role: 'lat',       label: 'Source latitude',  required: true },
    { role: 'lon',       label: 'Source longitude', required: true },
    { role: 'lat2',      label: 'Target latitude',  required: true },
    { role: 'lon2',      label: 'Target longitude', required: true },
    { role: 'measure',   label: 'Link weight', required: false },
  ],
  // Mirrors REQUIRED_ROLES in backend widget_roles.py (pinned by the parity test).
  model_linear: [
    { role: 'measure',  label: 'Response (numeric)', required: true },
    { role: 'predictors', label: 'Predictors (text columns compare levels)', required: true, multi: true },
    { role: 'partition', label: 'Partition (Training / Validation)', required: false },
  ],
  model_logistic: [
    { role: 'response', label: 'Response (yes/no outcome)', required: true },
    { role: 'predictors', label: 'Predictors (text columns compare levels)', required: true, multi: true },
    { role: 'partition', label: 'Partition (Training / Validation)', required: false },
  ],
  model_tree: [
    { role: 'response',   label: 'Response', required: true },
    { role: 'predictors', label: 'Predictors (blank = every other column)', required: false, multi: true },
  ],
  model_cluster: [
    { role: 'measures', label: 'Variables (at least two)', required: true, multi: true },
  ],
  // Its inputs are OTHER model widgets on the page, chosen in the panel.
  model_compare: [],
  // The saved model is chosen in the panel (it is not a column).
  model_score: [{ role: 'category', label: 'Break down by', required: false }],
}

/** Model widgets: their data is a fitted model, not an aggregated series. */
export const MODEL_WIDGETS: readonly string[] = [
  'model_linear', 'model_logistic', 'model_tree', 'model_cluster', 'model_compare', 'model_score',
]

export const AGGREGATIONS = [
  { value: 'sum',      label: 'Sum',           group: 'Numeric' },
  { value: 'none',     label: 'None (row values)', group: 'Numeric' },
  { value: 'avg',      label: 'Average',        group: 'Numeric' },
  { value: 'median',   label: 'Median',         group: 'Numeric' },
  { value: 'min',      label: 'Min',            group: 'Numeric' },
  { value: 'max',      label: 'Max',            group: 'Numeric' },
  { value: 'std',      label: 'Std Deviation',  group: 'Numeric' },
  { value: 'variance', label: 'Variance',       group: 'Numeric' },
  { value: 'range',    label: 'Range',          group: 'Numeric' },
  { value: 'p25',      label: 'P25',            group: 'Numeric' },
  { value: 'p75',      label: 'P75',            group: 'Numeric' },
  { value: 'p90',      label: 'P90',            group: 'Numeric' },
  { value: 'p95',      label: 'P95',            group: 'Numeric' },
  { value: 'count',    label: 'Count',          group: 'Count' },
  { value: 'countd',   label: 'Count Distinct', group: 'Count' },
  { value: 'frequency',label: 'Frequency',      group: 'Count' },
  { value: 'pct',      label: 'Percentage %',   group: 'Count' },
  // The statistical half of SAS's aggregation menu. Grouped apart because they
  // answer a different kind of question -- how spread out, how skewed, how sure
  // -- and because a first-draft dashboard almost never wants one. Each is
  // pinned against the engine by test_frontend_constant_mirrors.py, which runs
  // every value here rather than trusting the allowlist: `_agg_series` falls
  // back to SUM for a name it does not know, so an unimplemented aggregation
  // would return a plausible number and never raise.
  { value: 'stderr',   label: 'Standard Error', group: 'Statistical' },
  { value: 'cv',       label: 'Coefficient of Variation', group: 'Statistical' },
  { value: 'skewness', label: 'Skewness',       group: 'Statistical' },
  { value: 'kurtosis', label: 'Kurtosis',       group: 'Statistical' },
  { value: 'uss',      label: 'Uncorrected Sum of Squares', group: 'Statistical' },
  { value: 'css',      label: 'Corrected Sum of Squares',   group: 'Statistical' },
  { value: 'tstat',    label: 'T Statistic (mean = 0)',     group: 'Statistical' },
  { value: 'pvalue',   label: 'P-value (for T statistic)',  group: 'Statistical' },
]

// ── Workspace tree ────────────────────────────────────────────────────────────
// The org's report-navigation menu. Folders and filed reports share one sibling
// `position`, so they interleave rather than reports always sorting last.
//
// `pages` and a report node's `name` are DERIVED server-side, not stored: pages
// come from ReportPage at read time (so adding a page in the builder cannot
// leave the menu stale) and a report node reads its label through the report
// (so a rename is one edit with no second title to drift).

export interface WorkspacePage {
  id: number
  name: string
  position: number
}

export interface WorkspaceNode {
  id: number            // 0 for an unfiled report: no node row exists yet
  parent_id: number | null
  node_type: 'folder' | 'report'
  name: string | null
  report_id: number | null
  position: number
  /** Whether THIS viewer may rename/move/delete it. Computed server-side so the
   *  UI never re-implements the ownership rule. */
  can_manage: boolean
  /** Whether THIS viewer created it. Separate from can_manage, which is true
   *  for an admin on every node and so cannot answer "is this mine?". For a
   *  report node this is the REPORT's author, not whoever filed it. */
  is_mine: boolean
  /** The viewer's capability on the report ('view'|'edit'|'data'); only
   *  meaningful on report nodes. Marks granted view-only entries. */
  my_capability?: 'view' | 'edit' | 'data'
  /** Folder-level publish: this folder publishes its subtree's authored
   *  dashboards. Meaningful on folders only. */
  published?: boolean
  /** Roles this folder is restricted to; empty means everyone in the org sees
   *  it. Only populated for viewers who may manage the node. */
  role_ids: number[]
  /** Workspace sharing, from the viewer's side: a folder grant on this node or
   *  an ancestor reaches them and the node is not their own. Roots wearing it
   *  group under "Shared with me"; deeper nodes badge in place. */
  shared_with_me?: boolean
  pages: WorkspacePage[]
  children: WorkspaceNode[]
}

export interface WorkspaceTree {
  roots: WorkspaceNode[]
  /** Reports with no node. Every report must be reachable from the menu, so
   *  these render at the bottom rather than being hidden. */
  unfiled: WorkspaceNode[]
}


// ── Hierarchy widgets ───────────────────────────────────────────────────────
// Mirrors of real backend limits in services/widget_data.py. Each is pinned by
// a test against the Python source, because a silently-drifted copy is worse
// than no copy: the panel would promise something the shaper then refuses.

export const HIERARCHY_WIDGETS = ['tree', 'sunburst', 'icicle', 'dendrogram', 'org', 'circle_pack'] as const

/** Sunburst, icicle and circle packing draw value as an angle, a width, or the
 *  area a parent circle must contain -- so a parent's extent IS the sum of its
 *  children's. A non-additive aggregation makes the geometry state something the
 *  data does not: children that visibly fail to fill their parent, with nothing
 *  to say the picture is wrong rather than the data. */
export const PARTITION_WIDGETS: readonly string[] = ['sunburst', 'icicle', 'circle_pack']

/** Marks a composed graph can draw. Mirrors `GRAPH_MARKS` in widget_data.py —
 *  the panel must not offer a mark the shaper will quietly turn into a bar. */
export const GRAPH_MARKS: readonly string[] = ['bar', 'line', 'area', 'scatter']
export const ADDITIVE_AGGREGATIONS: readonly string[] = ['sum', 'count', 'frequency']

/** Each level multiplies the node count; deeper than this is navigation nobody
 *  follows. */
export const HIER_MAX_DEPTH = 8

/** Panels beyond this stop being comparable and the labels stop fitting. */
export const FACET_MAX_PANELS = 12

/** Charts a small multiple may repeat. Deliberately a curated list rather than
 *  every shaper key: most widget types make no sense faceted, and
 *  `small_multiples` itself would recurse. */
export const FACETABLE_WIDGETS = ['bar', 'line', 'area', 'pie', 'scatter'] as const

export const FORECAST_MIN_PERIODS = 1
export const FORECAST_MAX_PERIODS = 36
export const FORECAST_DEFAULT_PERIODS = 6
