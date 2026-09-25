export type WidgetType =
  | 'bar' | 'line' | 'pie' | 'donut' | 'scatter' | 'treemap' | 'step' | 'dot_plot' | 'needle'
  | 'histogram' | 'butterfly' | 'dual_axis_bar' | 'dual_axis_line' | 'dual_axis_bar_line' | 'dual_axis_time_series' | 'comparative_time_series' | 'numeric_series'
  | 'bubble' | 'bubble_change' | 'correlation_matrix' | 'heatmap' | 'parallel_coordinates' | 'box_plot' | 'waterfall' | 'gauge' | 'schedule' | 'vector_plot' | 'word_cloud'
  | 'kpi' | 'table' | 'crosstab' | 'list' | 'text' | 'button'

export interface Widget {
  id: number
  page_id: number
  widget_type: WidgetType
  title: string
  config: Record<string, unknown>
  layout: { x: number; y: number; w: number; h: number }
  created_at: string
}

export type PageType = 'normal' | 'hidden' | 'popup'

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
}

export interface Report {
  id: number
  name: string
  description?: string
  dataset_id: number | null
  additional_dataset_ids: number[]
  pages: ReportPage[]
  created_at: string
  updated_at: string
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
  { type: 'kpi'      as WidgetType, label: 'KPI Card',   category: 'Controls', icon: '◈', defaultW: 3, defaultH: 3 },
  { type: 'table'    as WidgetType, label: 'Table',      category: 'Controls', icon: '☰', defaultW: 6, defaultH: 6 },
  { type: 'crosstab' as WidgetType, label: 'Crosstab',   category: 'Controls', icon: '⊟', defaultW: 7, defaultH: 6 },
  { type: 'list'     as WidgetType, label: 'List',       category: 'Controls', icon: '≡', defaultW: 3, defaultH: 6 },
  { type: 'text'     as WidgetType, label: 'Text Block',  category: 'Controls', icon: 'T', defaultW: 4, defaultH: 3 },
  { type: 'button'   as WidgetType, label: 'Button',     category: 'Controls', icon: '▶', defaultW: 2, defaultH: 2 },
]

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
export const ROLE_SPECS: Record<WidgetType, RoleField[]> = {
  bar:      [{ role: 'category', label: 'Dimension (Group / X-axis)', required: true },
             { role: 'measure',  label: 'Measure (numeric column)',   required: false }],
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
  kpi:      [{ role: 'category', label: 'Dimension (Group / X-axis)', required: true },
             { role: 'measure',  label: 'Measure (numeric column)',   required: false }],
  table:    [{ role: 'category', label: 'Dimension (Group / X-axis)', required: true },
             { role: 'measure',  label: 'Measure (numeric column)',   required: false }],
  crosstab: [{ role: 'category',  label: 'Dimension (Group / X-axis)', required: true },
             { role: 'category2', label: 'Column Pivot',               required: false },
             { role: 'measure',   label: 'Measure (numeric column)',   required: false }],
  list:     [{ role: 'category', label: 'Dimension (Group / X-axis)', required: true },
             { role: 'measure',  label: 'Measure (numeric column)',   required: false }],
  text:     [],
  button:   [],
}

export const AGGREGATIONS = [
  { value: 'sum',      label: 'Sum',           group: 'Numeric' },
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
]
