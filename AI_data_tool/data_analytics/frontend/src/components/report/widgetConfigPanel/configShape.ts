/**
 * What the widget panel owns in a saved config, and the one legacy shape it
 * has to read (E03).
 *
 * The panel rebuilds the config from its own state on every edit, and the
 * server stores what it is sent. That is how "untouched leaves no key" works
 * -- clearing a control removes its key -- but it also dropped every key the
 * panel does not write: a widget's interactions, its hidden flag and tab
 * order (set in other panes), and settings only the API or the demo writes
 * (a map's `cluster_cell_degrees`, a decomposition's `split_by`). One title
 * edit and they were gone. So the panel now keeps whatever it does not
 * manage (`keepUnmanaged`), and `PANEL_KEYS` is the list of what it does --
 * pinned to the save effect by configShape.test.ts, so a new control cannot
 * forget to be listed.
 *
 * Two legacy shapes are migrated when the panel opens a widget
 * (`migrateWidgetConfig`), mirroring the server's migrate_widget_config
 * (services/widget_roles.py); both are pinned to the same cases in
 * widgetConfigMigrations.json beside this file:
 *   - a `roles` dict (the demo's map and flow widgets) is flattened into the
 *     keys the panel edits -- the panel read only those, so it opened such a
 *     widget with its roles empty, and its first save dropped them;
 *   - `agg` becomes `aggregation`;
 *   - `interaction.mode`, which nothing reads, is dropped.
 */
import { configKeyFor, ROLE_SPECS } from '../../../types/report'

/** Every top-level key the panel's save effect can write, besides role keys
 *  (which follow ROLE_SPECS, see `panelManagedKeys`). */
export const PANEL_KEYS: ReadonlySet<string> = new Set([
  // text, button, image, web content, shape
  'content', 'rtl', 'label', 'action', 'actionPageId', 'carry_filters', 'actionBookmarkId',
  'actionUrl', 'actionReportId', 'actionParamName', 'actionParamValue', 'url', 'alt', 'fit',
  'shape', 'fill', 'stroke',
  // data widgets
  'aggregation', 'limit', 'sort', 'sort_by', 'sort_col', 'running', 'slicer_mode',
  'boundary_set_id', 'pins', 'layers', 'id_col', 'parent_col', 'label_col', 'levels',
  'facet_by', 'inner_widget_type', 'facet_limit', 'forecast_periods', 'code', 'transparent',
  'legend_title', 'y2_axis_label', 'donut_total', 'donut_total_label', 'sort_custom',
  'sort_keys', 'having', 'filters', 'rank', 'quick_calc', 'suppress_below',
  'suppress_complement', 'columns', 'bins', 'baseline', 'fit_line', 'auto_reload_seconds',
  'target_value', 'gauge_shape', 'anim_label_position', 'anim_order', 'anim_label_size',
  'anim_label_style', 'anim_label_opacity', 'anim_label_box',
  // every type
  'dataset_id', 'drillthroughPageId', 'tooltipPageId', 'hierarchyNodeId',
  'dimension_granularity', 'aggregation2', 'bar_mode', 'centrality_metric', 'method',
  'event_value', 'max_depth', 'compare', 'prediction_model_id', 'forecast_target',
  'display_rules', 'analytics', 'container_mode', 'background_url', 'container_id', 'z',
  // formatting
  'x_axis_label', 'y_axis_label', 'axis_tick_size', 'axis_tick_color', 'x_axis_angle',
  'y_axis_angle', 'axis_line', 'tick_line', 'y_scale', 'y_min', 'y_max', 'grid',
  'grid_style', 'grid_color', 'wall_color', 'show_as_table', 'legend', 'legend_position',
  'overview_axis', 'lattice_rows', 'lattice_columns', 'animate_by', 'animate_granularity',
  'data_labels', 'series_patterns', 'show_totals', 'show_subtotals', 'totals_position',
  'totals_scope', 'table_row_numbers', 'table_row_lines', 'table_banding',
  'table_condensed', 'sparkline',
  // appearance
  'widget_background', 'widget_border_color', 'widget_border_width', 'widget_radius',
  'widget_padding', 'widget_skin', 'alt_text', 'subtitle',
])

/** The flat keys the server reads roles from when a config has no `roles`
 *  dict. MIRRORS `_LEGACY_ROLE_KEYS` in backend services/widget_data.py
 *  (pinned by test_frontend_constant_mirrors.py). */
export const FLAT_ROLE_KEYS: readonly string[] = [
  'dimension', 'dimension2', 'measure', 'measure2', 'start', 'size', 'color', 'group',
  'animation', 'end', 'target', 'direction', 'measures', 'lat', 'lon', 'lat2', 'lon2',
]

/** The settings with a fixed vocabulary, and the values each accepts.
 *  MIRRORS `VOCABULARIES` in backend services/widget_roles.py, which refuses
 *  any other value on save (pinned by test_frontend_constant_mirrors.py);
 *  configShape.test.tsx checks the panel offers exactly these. */
export const SETTING_VOCABULARIES: Record<string, readonly string[]> = {
  sort: ['asc', 'desc'],
  sort_by: ['value', 'name'],
  quick_calc: ['percent_of_total', 'difference', 'percent_change', 'rank'],
  totals_position: ['before', 'after'],
  totals_scope: ['all', 'shown'],
  bar_mode: ['clustered', 'stacked', 'stacked100'],
  slicer_mode: ['auto', 'buttons', 'list', 'dropdown', 'search', 'text'],
  legend_position: ['top', 'bottom', 'left', 'right'],
  y_scale: ['linear', 'log'],
  gauge_shape: ['arc', 'speedometer', 'bullet', 'thermometer', 'progress'],
  container_mode: ['group', 'tabs', 'scroll', 'prompt', 'precision'],
  dimension_granularity: ['year', 'quarter', 'month', 'week', 'day', 'hijri_month', 'hijri_year'],
}

let managed: Set<string> | null = null

/** PANEL_KEYS plus every key a role of any widget type is written under. */
export function panelManagedKeys(): ReadonlySet<string> {
  if (!managed) {
    managed = new Set(PANEL_KEYS)
    for (const fields of Object.values(ROLE_SPECS)) {
      for (const rf of fields) managed.add(rf.multi ? rf.role : configKeyFor(rf.role))
    }
  }
  return managed
}

/** The stored keys the panel does not manage, to carry through its saves. */
export function keepUnmanaged(stored: Record<string, unknown> | null | undefined): Record<string, unknown> {
  const keys = panelManagedKeys()
  return Object.fromEntries(Object.entries(stored ?? {}).filter(([k]) => !keys.has(k)))
}

const blank = (v: unknown) => v == null || v === '' || (Array.isArray(v) && v.length === 0)

/** A saved config in the shape the panel edits. A copy; the input is untouched.
 *  A `roles` dict is flattened only when no flat role key disagrees with it:
 *  the server's role readers use `roles` alone when it is present, while the
 *  bar/line/table shaper reads the flat keys, so a config where they differ
 *  renders differently per chart and is left exactly as it is. */
export function migrateWidgetConfig(stored: Record<string, unknown> | null | undefined): Record<string, unknown> {
  const cfg: Record<string, unknown> = { ...(stored ?? {}) }
  if ('agg' in cfg) {
    if (!blank(cfg.aggregation)) delete cfg.agg
    else if (typeof cfg.agg === 'string' && cfg.agg) { cfg.aggregation = cfg.agg; delete cfg.agg }
  }
  // The demo wrote `interaction: {mode: 'two_way'}`; nothing reads `mode`.
  const inter = cfg.interaction
  if (inter && typeof inter === 'object' && !Array.isArray(inter) && 'mode' in inter) {
    const { mode: _dead, ...rest } = inter as Record<string, unknown>
    cfg.interaction = rest
  }
  const roles = cfg.roles
  if (roles && typeof roles === 'object' && !Array.isArray(roles)) {
    const flat: Record<string, unknown> = {}
    for (const [role, v] of Object.entries(roles as Record<string, unknown>)) {
      if (!blank(v)) flat[configKeyFor(role)] = v
    }
    const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b)
    const conflict = [...new Set([...FLAT_ROLE_KEYS, ...Object.keys(flat)])]
      .some(k => !blank(cfg[k]) && (!(k in flat) || !same(cfg[k], flat[k])))
    if (!conflict) {
      delete cfg.roles
      Object.assign(cfg, flat)
    }
  }
  return cfg
}
