import { ROLE_SPECS, MULTI_MEASURE_WIDGETS, configKeyFor, type WidgetType } from '../types/report'
import { aggregationOffered } from '../components/report/widgetCapabilities'

/**
 * "Convert to": which object types a widget can become, and the config it
 * becomes with. A type is offered only when every field it REQUIRES can be
 * filled from what the widget already holds -- a bar of revenue by region can
 * become a line, a pie, a treemap or a KPI of revenue; it cannot become a
 * scatter, which needs a second number it does not have.
 *
 * What travels: the fields (by role, with the measures pooled so a measure can
 * move between `measure`, `measure2`, `measures` and `extra_measures`), the
 * widget's filters, and its aggregation where the new type accepts it. The
 * formatting does not travel: each type's options are its own, and the server
 * refuses a formatting option a type would ignore.
 */

/** Objects that are not charts of the data, or that are built differently. */
const NOT_CONVERTIBLE = new Set([
  'text', 'button', 'image', 'shape', 'container', 'web_content', 'custom_visual', 'script', 'slicer',
])
const convertible = (t: string) => !NOT_CONVERTIBLE.has(t) && !t.startsWith('model_')
  && (ROLE_SPECS[t as WidgetType] ?? []).length > 0

type Cfg = Record<string, unknown>
const str = (v: unknown) => (typeof v === 'string' && v ? v : undefined)
const strs = (v: unknown) => (Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string' && !!x) : [])

/** Every measure the widget holds, first one first. */
export function measuresOf(cfg: Cfg): string[] {
  return [...new Set([str(cfg.measure), str(cfg.measure2), ...strs(cfg.extra_measures), ...strs(cfg.measures)]
    .filter((m): m is string => !!m))]
}

/** `cfg` rebuilt for `to`, or null when `to` needs a field the widget lacks. */
export function convertConfig(from: string, cfg: Cfg, to: string): Cfg | null {
  if (to === from || !convertible(to) || !convertible(from)) return null
  // A map needs a column KNOWN to be geography (and its boundary set), which
  // this menu cannot tell from a config -- a "map" of region names that are
  // not places draws nothing. Maps convert among themselves; a chart becomes
  // a map from the gallery, where the geography checks run.
  if (to.startsWith('map_') && !from.startsWith('map_')) return null
  const measures = measuresOf(cfg)
  const out: Cfg = {}
  for (const rf of ROLE_SPECS[to as WidgetType] ?? []) {
    if (rf.multi) {
      // A multi role of numbers takes the pooled measures; any other multi
      // role (a model's predictors) only what the widget held there.
      const values = rf.role === 'measures' ? measures : strs(cfg[rf.role])
      if (rf.required && values.length === 0) return null
      if (values.length) out[rf.role] = values
      continue
    }
    const key = configKeyFor(rf.role)
    const value = str(cfg[key])
      ?? (rf.role === 'measure' ? measures[0] : undefined)
      ?? (rf.role === 'measure2' ? measures[1] : undefined)
      // A time series names its date axis `start`; as a category it is the same column.
      ?? (rf.role === 'category' ? str(cfg.start) : undefined)
    if (rf.required && !value) return null
    if (value) out[key] = value
  }
  // Something must carry over: a type whose roles are all optional would
  // otherwise be offered as an empty chart.
  if (Object.keys(out).length === 0) return null
  // Several measures on the value axis where the new type draws them.
  if (MULTI_MEASURE_WIDGETS.includes(to) && !out.dimension2 && str(out.measure)) {
    const extra = measures.filter(m => m !== out.measure)
    if (extra.length) out.extra_measures = extra
  }
  // Keep how the category is bucketed when the category itself carried over.
  if (out.dimension && out.dimension === cfg.dimension) {
    for (const k of ['dimension_granularity', 'fiscal_start_month', 'hierarchyNodeId']) {
      if (cfg[k] != null && cfg[k] !== '') out[k] = cfg[k]
    }
  }
  // A grid's Columns hierarchy, when the new type is a grid with the same Columns.
  if (['crosstab', 'matrix'].includes(to) && out.dimension2 && out.dimension2 === cfg.dimension2 && cfg.hierarchyNodeId2 != null) {
    out.hierarchyNodeId2 = cfg.hierarchyNodeId2
  }
  if (Array.isArray(cfg.filters) && cfg.filters.length) out.filters = cfg.filters
  const agg = str(cfg.aggregation)
  if (agg && aggregationOffered(to, agg)) out.aggregation = agg
  return out
}

export interface Conversion { type: string; config: Cfg }

/** Every type this widget can become, in catalogue order. */
export function conversionsFor(from: string, cfg: Cfg): Conversion[] {
  if (!convertible(from)) return []
  const out: Conversion[] = []
  for (const to of Object.keys(ROLE_SPECS)) {
    const config = convertConfig(from, cfg, to)
    if (config) out.push({ type: to, config })
  }
  return out
}
