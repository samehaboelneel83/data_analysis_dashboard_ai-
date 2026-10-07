import { memo, useState, useEffect, useLayoutEffect, useRef, useMemo, cloneElement, lazy, Suspense} from 'react'
import { keepUnmanaged, migrateWidgetConfig } from './widgetConfigPanel/configShape'
import RelativeDateEditor from './RelativeDateEditor'
import { LATTICE_WIDGETS } from './chartRenderers/LatticeRenderer'
import { ANIMATION_WIDGETS } from './chartRenderers/AnimatedRenderer'
const ANIMATION_SEARCH_TERMS = ['animation', 'play', 'time-lapse', 'frames', 'animate']
const LATTICE_SEARCH_TERMS = ['lattice', 'small multiples', 'trellis', 'facet', 'panels', 'grid']
import { DEFAULT_SPEC, parseSpec, specProblem } from '../../lib/relativeDates'
import type { Widget, WidgetType, ReportPage, HierarchyNode, Bookmark } from '../../types/report'
import BoundarySetPicker from './BoundarySetPicker'
import GeoMatchStatus from './GeoMatchStatus'
import { usePanelLabel, useRoleLabel } from './panelLabels'
import { useDirection } from '../../contexts/DirectionContext'
// Lazy: matching a column against map regions needs the bundled world geometry.
const GeoMatchLine = lazy(() => import('./GeoMatchLine'))
import { boundarySetsApi, calendarSettingsApi } from '../../services/api'
import { monthName } from '../../lib/fiscal'
import MapPinsEditor from './MapPinsEditor'
import GraphLayersEditor from './GraphLayersEditor'
import MapLayersEditor, { type MapLayerCfg } from './MapLayersEditor'
import type { GraphLayer } from './GraphLayersEditor'
import { toDraftPin, toStoredPin } from './MapPinsEditor'
import type { MapPin, StoredPin } from './MapPinsEditor'
import { ADDITIVE_AGGREGATIONS, BOUNDARY_SET_WIDGETS, PIN_WIDGETS, FACETABLE_WIDGETS, FACET_MAX_PANELS, FORECAST_DEFAULT_PERIODS, FORECAST_MAX_PERIODS, FORECAST_MIN_PERIODS, HIERARCHY_WIDGETS, HIER_MAX_DEPTH, PARTITION_WIDGETS } from '../../types/report'
import { AGGREGATIONS, DUAL_MEASURE_WIDGETS, MULTI_MEASURE_WIDGETS, PIVOT_WIDGETS, ROLE_SPECS, configKeyFor, roleAccepts } from '../../types/report'
import { ASSIGN_DATA_EVENT, ADD_DATASET_EVENT, emptyPickerReason } from './WidgetPlaceholder'
import { semanticAggregationWarning, nonAdditiveKind, SAFE_AGGREGATION } from '../../lib/semanticGuard'
import { savePending, clearPending } from '../../lib/pendingEdits'
import type { DatasetColumn, Dataset } from '../../services/api'
import InteractionSettings from './InteractionSettings'
import DataRolesList, { AddFieldDialog, AssignDataDialog, type FieldKind } from './DataRolesList'
import HierarchyTree from './HierarchyTree'
import DisplayRulesPanel from './DisplayRulesPanel'
import ExpandableGroup from './ExpandableGroup'
import type { DisplayRule } from '../../lib/displayRules'
import { flattenHierarchy } from '../../lib/hierarchyUtils'
import { isIdLikeColumn } from '../../lib/columnRole'
import { aggregationOffered, formattingCapabilities, sortLimitOptions, supportsRanking } from './widgetCapabilities'
import { aggregationWarning } from '../../lib/aggregateDisclosure'
import {
  CUSTOM_SHAPE_WIDGET_TYPES, RUNNING_OPTIONS, readCssVarColor,
  seedRoleValues, seedMultiRoleValues, widgetIcon,
} from './widgetConfigPanel/helpers'
import ModelSettings, { type ModelOpts, modelOptsConfig, seedModelOpts } from './ModelSettings'

interface Props {
  widget: Widget
  columns: DatasetColumn[]
  datasets?: Record<number, Dataset>
  primaryDatasetId?: number | null
  pages?: ReportPage[]
  hierarchy?: HierarchyNode[]
  onHierarchyRefresh?: () => void
  bookmarks?: Bookmark[]
  // rule_errors from the widget's last fetch (see WidgetRenderer.onFetchComplete /
  // ReportBuilder.perfStats) — the config panel never fetches data itself, so this is
  // the only channel by which it learns a rule failed to evaluate.
  ruleErrors?: { id?: string; message: string }[]
  /** Columns classified as geography and the set each draws with — the same
   *  mapping the renderers read, so the panel can say what the map is actually
   *  drawing rather than showing an empty picker beside governorates. */
  geography?: Record<string, number>
  /** Distinct values per field (from the builder's field analysis), shown in
   *  the role pickers -- "region · 4 values" is what tells a bar chart from a
   *  mistake before it is drawn. Optional: absent, the pickers show no counts. */
  distinctCounts?: Record<string, number>
  onUpdate: (config: Record<string, unknown>, title: string) => void
  /** The builder's Format / Data / Interactions (redesign 7e3): shows only
   *  that section's tabs, and "All" means all of it. Absent, the panel is
   *  v1's: every tab. Search always reaches everything. */
  section?: 'format' | 'data' | 'interactions'
  /** Asked when the panel itself moves to another section ("Assign data"
   *  opens Data roles). */
  onSection?: (s: 'format' | 'data' | 'interactions') => void
}

/** Which of v1's tabs each builder section holds. Every tab is in one. */
export const SECTION_TABS: Record<'format' | 'data' | 'interactions', string[]> = {
  format: ['Options', 'Display rules'],
  data: ['Data', 'Data roles', 'Filters', 'Ranks'],
  interactions: ['Actions'],
}

// Widget types dispatched to a shaper OTHER than shape_series
// (backend/app/services/widget_data.py SHAPERS) — their result has a bespoke shape
// (x/y/size, dual measures, heatmap cells, …) that this panel does not model, so the
// dimension-based branching below (which mirrors shape_series specifically) does not
// apply to them. Any WidgetType not in this set is dispatched to shape_series, either
// explicitly or via SHAPERS' fallback for unregistered types (e.g. 'slicer').
/** A stored list of field names, whatever was actually stored. */
function stringList(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string' && x !== '') : []
}

/** Where a role's second and later fields are saved. A crosstab or matrix
 *  takes several on Rows, Columns and Measures (a nested pivot); a bar, line
 *  or area several measures (one series each), never beside a series split. */
const EXTRA_KEY_OF: Record<string, string> = { category: 'rows_extra', category2: 'columns_extra', measure: 'extra_measures' }
function extraKeyFor(wt: string, role: string, roleValues: Record<string, string>): string | undefined {
  if (PIVOT_WIDGETS.includes(wt)) return EXTRA_KEY_OF[role]
  if (role === 'measure' && MULTI_MEASURE_WIDGETS.includes(wt) && !roleValues.category2) return 'extra_measures'
  return undefined
}
const seedExtras = (cfg: Record<string, unknown>): Record<string, string[]> =>
  Object.fromEntries(Object.values(EXTRA_KEY_OF).map(k => [k, stringList(cfg[k])]))

function WidgetConfigPanel({ widget, columns, datasets, primaryDatasetId, pages, hierarchy, onHierarchyRefresh, bookmarks, ruleErrors, geography, distinctCounts, onUpdate, section, onSection }: Props) {
  // E03: in the shape the panel edits -- a legacy `roles` dict flattened,
  // `agg` renamed (widgetConfigPanel/configShape.ts). Keyed on the stored
  // object, so it is recomputed when the widget or its config changes.
  const migrated = useMemo(() => migrateWidgetConfig(widget.config as Record<string, unknown>),
    [widget.config])
  const cfg = migrated as any
  const wt  = widget.widget_type
  // The panel's own words in the reader's language (panelLabels.ts). Field
  // names, option values and anything from the data stay as they are.
  const L = usePanelLabel()
  // Data-role names and field groups (Numbers, Dates...) in the reader's language.
  const roleL = useRoleLabel()
  const { language } = useDirection()

  // Panel search box — not part of the widget config, so it is never seeded/reset by
  // the widget-switch effect and never written by the save effect.
  const [filterText, setFilterText] = useState('')
  const [chosenTab, setSettingsTab] = useState('all')
  // In a builder section, a tab from another section reads as that
  // section's "All" (the choice is held, not rewritten).
  const inSection = section ? SECTION_TABS[section] : null
  const settingsTab = inSection && chosenTab !== 'all' && !inSection.includes(chosenTab) ? 'all' : chosenTab
  const onSectionRef = useRef(onSection)
  onSectionRef.current = onSection
  // "Assign data" (on the tile, or right after inserting a widget) opens the
  // one tab that can finish it -- SAS opens Assign data straight into the roles
  // pane. Only on that request: selecting an existing widget keeps the tab the
  // author was on, and hides nothing.
  // The Assign data dialog, and the role it was opened on ("+ Add" beside a
  // role scrolls to that role). The request also opens the dialog unless it
  // says `open: false` -- the pane's object picker only switches objects.
  const [assignOpen, setAssignOpen] = useState(false)
  const [assignRole, setAssignRole] = useState<string | null>(null)
  // "+ Add" on a role: a picker of just the fields that role accepts.
  const [addRole, setAddRole] = useState<string | null>(null)
  useEffect(() => {
    const onAssign = (e: Event) => {
      const detail = (e as CustomEvent<{ widgetId: number; open?: boolean; tab?: 'Filters' }>).detail
      if (detail?.widgetId !== widget.id) return
      // QA3 A4: the quick toolbar's Filters asks for the Filters tab.
      setSettingsTab(detail.tab ?? 'Data roles')
      onSectionRef.current?.('data')
      if (detail.open !== false) { setAssignRole(null); setAssignOpen(true) }
    }
    window.addEventListener(ASSIGN_DATA_EVENT, onAssign)
    return () => window.removeEventListener(ASSIGN_DATA_EVENT, onAssign)
  }, [widget.id])
  useEffect(() => { setAssignOpen(false); setAddRole(null) }, [widget.id])

  // Which shapes a map draws. Empty = the built-in countries, which is what
  // every map did before boundary sets existed.
  /** An object with no panel of its own, so a page background shows through it. */
  const [transparent, setTransparent] = useState<boolean>(cfg.transparent === true)
  /** A heading for the legend, naming the field its entries are values of. */
  const [legendTitle, setLegendTitle] = useState<string>((cfg.legend_title as string) ?? '')
  /** The RIGHT axis's title on a dual-axis chart. */
  const [y2AxisLabel, setY2AxisLabel] = useState<string>((cfg.y2_axis_label as string) ?? '')
  /** The total in the middle of a donut. */
  const [donutTotal, setDonutTotal] = useState<boolean>(cfg.donut_total !== false)
  const [donutTotalLabel, setDonutTotalLabel] = useState<string>((cfg.donut_total_label as string) ?? '')

  /** The Python a script tile runs on the server. */
  const [scriptCode, setScriptCode] = useState<string>((cfg.code as string) ?? '')
  /** Background image for a precision container: the floorplan, schematic or
   *  diagram that overlapping widgets are positioned over. */
  const [containerBackground, setContainerBackground] = useState<string>(
    (cfg.background_url as string) ?? '')
  /** Stacking order inside a precision container. Zero means unset, because
   *  document order is an accident of the sort rather than an intent. */
  const [layer, setLayer] = useState<string>(
    cfg.z != null ? String(cfg.z) : '')
  /** Which centrality sizes the nodes of a network. `shape_network` has always
   *  computed all four and the renderer has always read this key; nothing ever
   *  wrote it, so every network in the product was a degree map. */
  const [centralityMetric, setCentralityMetric] = useState<string>(
    (cfg.centrality_metric as string) ?? 'degree')
  /** "When will this reach X?" — the target a forecast is asked about. Empty
   *  means no question, which is what every forecast widget has always been. */
  const [forecastTarget, setForecastTarget] = useState<string>(
    cfg.forecast_target != null ? String(cfg.forecast_target) : '')
  const [boundarySetId, setBoundarySetId] = useState<string>(
    cfg.boundary_set_id != null ? String(cfg.boundary_set_id) : '')
  // Held as DRAFTS (string coordinates) for the same reason every other numeric
  // field in this panel is: an input bound to a parsed number cannot be typed
  // into -- "48." parses to 48 and re-renders without the dot. Converted to
  // numbers in the save block below, which is the only place the stored shape
  // exists.
  /** The set this widget's dimension column is classified with, if any. Named
   *  rather than shown as an id, because an id tells the author nothing. */
  const [inheritedBoundaryName, setInheritedBoundaryName] = useState<string | null>(null)
  useEffect(() => {
    const dim = cfg.dimension as string | undefined
    const setId = dim ? geography?.[dim] : undefined
    if (setId == null) { setInheritedBoundaryName(null); return }
    let live = true
    boundarySetsApi.list()
      .then(list => { if (live) setInheritedBoundaryName(
        list.find(b => b.id === setId)?.name ?? null) })
      .catch(() => { if (live) setInheritedBoundaryName(null) })
    return () => { live = false }
  }, [cfg.dimension, geography])

  /** The layers of a composed graph. Held here like every other structured
   *  config, and written back whole — the chart IS its layers, so a partial
   *  update would be a different chart. */
  const [graphLayers, setGraphLayers] = useState<GraphLayer[]>(
    Array.isArray(cfg.layers) ? (cfg.layers as GraphLayer[]) : [])

  /** A layered map's stack (config.layers), bottom first. */
  const [mapLayers, setMapLayers] = useState<MapLayerCfg[]>(
    wt === 'map_layers' && Array.isArray(cfg.layers) ? (cfg.layers as MapLayerCfg[]) : [])

  const [pins, setPins] = useState<MapPin[]>(
    Array.isArray(cfg.pins) ? (cfg.pins as StoredPin[]).map(toDraftPin) : [])
  const [title,      setTitle]      = useState(widget.title ?? '')
  const [datasetId,  setDatasetId]  = useState<number | ''>(cfg.dataset_id || '')
  const [roleValues, setRoleValues] = useState<Record<string, string>>(() => seedRoleValues(cfg, wt))
  const setRole = (role: string, value: string) => setRoleValues(prev => ({ ...prev, [role]: value }))
  const [multiRoleValues, setMultiRoleValues] = useState<Record<string, string[]>>(() => seedMultiRoleValues(cfg, wt))
  // Model widgets (Phase 3): aggregation/sort/limit mean nothing to a fitted
  // model, so those groups are not offered; its own options live here.
  const isModel = wt.startsWith('model_')
  const [modelOpts, setModelOpts] = useState<ModelOpts>(() => seedModelOpts(cfg))
  const toggleMultiRole = (role: string, value: string) => setMultiRoleValues(prev => {
    const current = prev[role] ?? []
    const next = current.includes(value) ? current.filter(v => v !== value) : [...current, value]
    return { ...prev, [role]: next }
  })
  const [agg,        setAgg]        = useState(cfg.aggregation ?? 'sum')
  // Blank means "same as the first" -- the behaviour every dual-axis chart had
  // before the second axis could aggregate on its own.
  const [agg2,       setAgg2]       = useState((cfg.aggregation2 as string) ?? '')
  // A role's second and later fields, by the key they are saved under
  // (extra_measures, rows_extra, columns_extra -- see extraKeyFor).
  const [extraFields, setExtraFields] = useState<Record<string, string[]>>(() => seedExtras(cfg))
  const extraMeasures = extraFields.extra_measures ?? []
  // No limit = full data (QA 2026-09-26). The panel used to stamp `limit: 20`
  // on every widget it saved, silently cutting charts the author never limited.
  const [limit,      setLimit]      = useState<number | null>(cfg.limit ?? null)
  const [autoReload, setAutoReload] = useState<string>(cfg.auto_reload_seconds != null ? String(cfg.auto_reload_seconds) : '')
  const [sort,       setSort]       = useState(cfg.sort       ?? 'desc')
  // '' means Automatic: write nothing and let the server choose by column type
  // (chronological for a date axis, by value otherwise). Writing 'value' here
  // unconditionally is what made that server-side default unreachable from the UI.
  const [sortBy,     setSortBy]     = useState(cfg.sort_by    ?? '')
  const [sortCustom, setSortCustom] = useState<string>(Array.isArray(cfg.sort_custom) ? (cfg.sort_custom as unknown[]).join(', ') : '')
  const [havingOp,   setHavingOp]   = useState<string>((cfg.having as {op?:string}[] | undefined)?.[0]?.op ?? '')
  const [objFilters, setObjFilters] = useState<{ column: string; op: string; value: string }[]>(
    ((cfg.filters as { column?: string; op?: string; value?: unknown }[] | undefined) ?? [])
      .map(f => ({ column: String(f.column ?? ''), op: String(f.op ?? 'eq'), value: f.op === 'relative' ? JSON.stringify(parseSpec(f.value)) : String(f.value ?? '') })))
  const [rankMode,   setRankMode]   = useState<string>((cfg.rank as {mode?:string} | undefined)?.mode ?? '')
  const [rankN,      setRankN]      = useState<string>((cfg.rank as {n?:number|string} | undefined)?.n != null ? String((cfg.rank as {n:number|string}).n) : '')
  const [rankPercent, setRankPercent] = useState<boolean>(!!(cfg.rank as {percent?:boolean} | undefined)?.percent)
  const [rankOther,   setRankOther]   = useState<boolean>(!!(cfg.rank as {other?:boolean} | undefined)?.other)
  const [quickCalc,  setQuickCalc]  = useState<string>((cfg.quick_calc as string) ?? '')
  const [suppressBelow, setSuppressBelow] = useState<string>(cfg.suppress_below != null ? String(cfg.suppress_below) : '')
  const [suppressComplement, setSuppressComplement] = useState<boolean>(!!cfg.suppress_complement)
  const [havingValue, setHavingValue] = useState<string>((cfg.having as {value?:unknown}[] | undefined)?.[0]?.value != null ? String((cfg.having as {value?:unknown}[])[0].value) : '')
  const [sortCol,    setSortCol]    = useState(cfg.sort_col   ?? '')
  const [sortKeys,   setSortKeys]   = useState<{ col: string; dir: string }[]>(
    Array.isArray(cfg.sort_keys) ? (cfg.sort_keys as { col: string; dir: string }[]) : [])
  const [running,    setRunning]    = useState(cfg.running    ?? '')
  const [content,    setContent]    = useState(cfg.content    ?? '')
  const [label,      setLabel]      = useState(cfg.label      ?? 'Click me')
  const [tableCols,  setTableCols]  = useState<string[]>(cfg.columns ?? [])
  const [rtl,        setRtl]        = useState<boolean>(cfg.rtl ?? false)
  const [bins,       setBins]       = useState<number>((cfg.bins as number) ?? 10)
  const [baseline,   setBaseline]   = useState<number>((cfg.baseline as number) ?? 0)
  const [fitLine,    setFitLine]    = useState<string>((cfg.fit_line as string) ?? '')
  const [targetValue, setTargetValue] = useState<string>((cfg.target_value != null ? String(cfg.target_value) : ''))
  const [gaugeShape, setGaugeShape] = useState<string>(String(cfg.gauge_shape ?? 'arc'))
  const [animPos,     setAnimPos]     = useState<string>(String(cfg.anim_label_position ?? 'none'))
  const [animOrder,   setAnimOrder]   = useState<string>(String(cfg.anim_order ?? 'asc'))
  const [animSize,    setAnimSize]    = useState<string>(cfg.anim_label_size != null ? String(cfg.anim_label_size) : '44')
  const [animStyle,   setAnimStyle]   = useState<string>(String(cfg.anim_label_style ?? 'bold'))
  const [animOpacity, setAnimOpacity] = useState<string>(cfg.anim_label_opacity != null ? String(cfg.anim_label_opacity) : '0.25')
  const [animBox,     setAnimBox]     = useState<boolean>(!!cfg.anim_label_box)
  const [drillthroughPageId, setDrillthroughPageId] = useState<string>(cfg.drillthroughPageId != null ? String(cfg.drillthroughPageId) : '')
  const [tooltipPageId, setTooltipPageId] = useState<string>(cfg.tooltipPageId != null ? String(cfg.tooltipPageId) : '')
  const [hierarchyNodeId, setHierarchyNodeId] = useState<string>(cfg.hierarchyNodeId != null ? String(cfg.hierarchyNodeId) : '')
  const [dimensionGranularity, setDimensionGranularity] = useState<string>((cfg.dimension_granularity as string) ?? '')
  // E10: a fiscal grouping follows the org's fiscal year ('') unless the
  // widget names its own first month.
  const [fiscalStart, setFiscalStart] = useState<string>(cfg.fiscal_start_month != null ? String(cfg.fiscal_start_month) : '')
  const [orgFiscalStart, setOrgFiscalStart] = useState<number | null>(null)
  useEffect(() => {
    if (!dimensionGranularity.startsWith('fiscal') || orgFiscalStart != null) return
    let live = true
    try {
      calendarSettingsApi.get()
        .then(s => { if (live) setOrgFiscalStart(s.fiscal_year_start_month) })
        .catch(() => {})
    } catch { /* no calendar endpoint (a test double): the note just omits the month */ }
    return () => { live = false }
  }, [dimensionGranularity, orgFiscalStart])
  const [showHierarchyEditor, setShowHierarchyEditor] = useState(false)
  const [action,           setAction]           = useState<string>((cfg.action as string) ?? '')
  const [actionPageId,     setActionPageId]     = useState<string>(cfg.actionPageId != null ? String(cfg.actionPageId) : '')
  const [carryFilters,     setCarryFilters]     = useState<boolean>(!!cfg.carry_filters)
  const [actionBookmarkId, setActionBookmarkId] = useState<string>(cfg.actionBookmarkId != null ? String(cfg.actionBookmarkId) : '')
  const [actionUrl,        setActionUrl]        = useState<string>((cfg.actionUrl as string) ?? '')
  const [actionReportId,   setActionReportId]   = useState<string>(cfg.actionReportId != null ? String(cfg.actionReportId) : '')
  const [actionParamName,  setActionParamName]  = useState<string>((cfg.actionParamName as string) ?? '')
  const [actionParamValue, setActionParamValue] = useState<string>((cfg.actionParamValue as string) ?? '')
  const [barMode,          setBarMode]          = useState<string>((cfg.bar_mode as string) ?? 'clustered')
  const [forecastMethod,   setForecastMethod]   = useState<string>((cfg.method as string) ?? 'ets')
  const [imageUrl,         setImageUrl]         = useState<string>((cfg.url as string) ?? '')
  const [imageAlt,         setImageAlt]         = useState<string>((cfg.alt as string) ?? '')
  const [imageFit,         setImageFit]         = useState<string>((cfg.fit as string) ?? 'contain')
  const [webUrl,           setWebUrl]           = useState<string>((cfg.url as string) ?? '')
  const [customUrl,        setCustomUrl]        = useState<string>((cfg.url as string) ?? '')
  const [shapeKind,        setShapeKind]        = useState<string>((cfg.shape as string) ?? 'rectangle')
  const [shapeFill,        setShapeFill]        = useState<string>((cfg.fill as string) ?? '#6c8fff')
  const [shapeStroke,      setShapeStroke]      = useState<string>((cfg.stroke as string) ?? '#6c8fff')
  const [showAverageLine,  setShowAverageLine]  = useState<boolean>(!!(cfg.analytics?.showAverageLine))
  const [referenceValue,   setReferenceValue]   = useState<string>(cfg.analytics?.referenceValue != null ? String(cfg.analytics.referenceValue) : '')
  const [referenceLabel,   setReferenceLabel]   = useState<string>((cfg.analytics?.referenceLabel as string) ?? '')
  const [referenceColor,   setReferenceColor]   = useState<string>((cfg.analytics?.referenceColor as string) ?? '#f59e0b')
  const [displayRules,     setDisplayRules]     = useState<DisplayRule[]>((cfg.display_rules as DisplayRule[]) ?? [])

  // Formatting (Task 9) — one state slot per FormatConfig key (axisOptions.ts). Only
  // rendered/written for the capabilities formattingCapabilities(wt) actually grants;
  // see widgetCapabilities.ts for why each type gets what it gets.
  //
  // Fix round 2: the boolean/enum toggles below are tri-state (`| undefined`), seeded
  // directly from `cfg` with NO `??` fallback, so "the user never touched this control"
  // stays distinguishable from "the user explicitly chose the default-looking value."
  // Only a defined value is ever written back to config (see the save effect below) --
  // an untouched control leaves no key behind. This matters because several renderers
  // (Schedule/Waterfall/Butterfly's axisLine/tickLine) default an unset prop to `true`,
  // the opposite of the `??` fallback this panel would otherwise have invented; writing
  // an invented `false` on every save would flip their axis lines off from an edit that
  // never touched formatting. The panel deliberately does NOT encode which renderer
  // defaults to what (that knowledge belongs in the renderers and would rot here) --
  // it just refuses to persist a value nobody chose. `??` fallbacks still appear at the
  // render call sites below, purely to pick what the control displays before the user
  // touches it; they are never involved in deciding what gets saved.
  const [xAxisLabel,    setXAxisLabel]    = useState<string>((cfg.x_axis_label as string) ?? '')
  const [yAxisLabel,    setYAxisLabel]    = useState<string>((cfg.y_axis_label as string) ?? '')
  const [axisTickSize,  setAxisTickSize]  = useState<string>(cfg.axis_tick_size != null ? String(cfg.axis_tick_size) : '')
  const [axisTickColor, setAxisTickColor] = useState<string>((cfg.axis_tick_color as string) ?? '')
  const [axisLine,      setAxisLine]      = useState<boolean | undefined>(cfg.axis_line)
  const [tickLine,      setTickLine]      = useState<boolean | undefined>(cfg.tick_line)
  // undefined means AUTOMATIC -- the axis planner picks the angle from the
  // labels. A number pins it. Absent from config entirely when automatic, so
  // a widget saved before this control existed keeps behaving as it did.
  const [xAxisAngle,    setXAxisAngle]    = useState<number | undefined>(
    typeof cfg.x_axis_angle === 'number' ? cfg.x_axis_angle : undefined)
  const [yAxisAngle,    setYAxisAngle]    = useState<number | undefined>(
    typeof cfg.y_axis_angle === 'number' ? cfg.y_axis_angle : undefined)
  const [yScale,        setYScale]        = useState<'linear' | 'log' | undefined>(cfg.y_scale)
  const [yMin,          setYMin]          = useState<string>(cfg.y_min != null ? String(cfg.y_min) : '')
  const [yMax,          setYMax]          = useState<string>(cfg.y_max != null ? String(cfg.y_max) : '')
  const [showGrid,      setShowGrid]      = useState<boolean | undefined>(cfg.grid)
  const [gridStyle,     setGridStyle]     = useState<'dashed' | 'solid' | undefined>(cfg.grid_style)
  const [gridColor,     setGridColor]     = useState<string>((cfg.grid_color as string) ?? '')
  const [wallColor,     setWallColor]     = useState<string>((cfg.wall_color as string) ?? '')
  const [showAsTable,   setShowAsTable]   = useState<boolean | undefined>(cfg.show_as_table as boolean | undefined)
  const [overviewAxis,  setOverviewAxis]  = useState<boolean | undefined>(cfg.overview_axis as boolean | undefined)
  const [latticeRows,   setLatticeRows]   = useState<string>((cfg.lattice_rows as string) ?? '')
  const [latticeCols,   setLatticeCols]   = useState<string>((cfg.lattice_columns as string) ?? '')
  const [animateBy,     setAnimateBy]     = useState<string>((cfg.animate_by as string) ?? '')
  const [animateGran,   setAnimateGran]   = useState<string>((cfg.animate_granularity as string) ?? '')
  const [slicerMode,    setSlicerMode]    = useState<string>((cfg.slicer_mode as string) ?? 'auto')
  // Hierarchy widgets. `mode` is derived from which keys the saved config has,
  // so reopening an existing widget lands on the mode it was authored in.
  const [hierMode, setHierMode] = useState<'levels' | 'parent_child'>(
    (cfg.id_col && cfg.parent_col) ? 'parent_child' : 'levels')
  const [hierLevels,    setHierLevels]    = useState<string[]>((cfg.levels as string[]) ?? [])
  const [hierIdCol,     setHierIdCol]     = useState<string>((cfg.id_col as string) ?? '')
  const [hierParentCol, setHierParentCol] = useState<string>((cfg.parent_col as string) ?? '')
  const [hierLabelCol,  setHierLabelCol]  = useState<string>((cfg.label_col as string) ?? '')
  const [facetBy,       setFacetBy]       = useState<string>((cfg.facet_by as string) ?? '')
  const [facetInner,    setFacetInner]    = useState<string>((cfg.inner_widget_type as string) ?? 'bar')
  const [facetLimit,    setFacetLimit]    = useState<string>(String(cfg.facet_limit ?? FACET_MAX_PANELS))
  const [forecastPeriods, setForecastPeriods] = useState<string>(
    String(cfg.forecast_periods ?? FORECAST_DEFAULT_PERIODS))
  const [containerMode, setContainerMode] = useState<string>((cfg.container_mode as string) ?? 'group')
  const [containerId,   setContainerId]   = useState<string>(cfg.container_id != null ? String(cfg.container_id) : '')
  const [showLegend,    setShowLegend]    = useState<boolean | undefined>(cfg.legend)
  const [legendPosition, setLegendPosition] = useState<'top' | 'bottom' | 'left' | 'right' | undefined>(
    cfg.legend_position as 'top' | 'bottom' | 'left' | 'right' | undefined)
  const [dataLabels,    setDataLabels]    = useState<boolean | undefined>(cfg.data_labels)
  const [seriesPatterns, setSeriesPatterns] = useState<boolean | undefined>(cfg.series_patterns as boolean | undefined)

  // Table options (Task 9) — same tri-state rule as the formatting block above: seed
  // from cfg with no `??` fallback, write only when touched. show_subtotals is the one
  // that actually matters: widget_data.py defaults it to True
  // (config.get("show_subtotals", True)), so an untouched control that wrote `false`
  // would silently drop the subtotal column from every existing crosstab on the very
  // next unrelated save (e.g. a title rename).
  const [showTotals,      setShowTotals]      = useState<boolean | undefined>(cfg.show_totals)
  const [showSubtotals,   setShowSubtotals]   = useState<boolean | undefined>(cfg.show_subtotals)
  // Same rule, same reason: absent means 'after' / 'all' (how every table saved
  // before these existed renders), so an untouched control writes nothing.
  const [totalsPosition,  setTotalsPosition]  = useState<'before' | 'after' | undefined>(cfg.totals_position as 'before' | 'after' | undefined)
  const [totalsScope,     setTotalsScope]     = useState<'all' | 'shown' | undefined>(cfg.totals_scope as 'all' | 'shown' | undefined)
  const [tableRowNumbers, setTableRowNumbers] = useState<boolean | undefined>(cfg.table_row_numbers)
  const [tableRowLines,   setTableRowLines]   = useState<boolean | undefined>(cfg.table_row_lines)
  const [tableBanding,    setTableBanding]    = useState<boolean | undefined>(cfg.table_banding)
  const [tableCondensed,  setTableCondensed]  = useState<boolean | undefined>(cfg.table_condensed)
  const [tableSparkline,  setTableSparkline]  = useState<boolean | undefined>(cfg.sparkline as boolean | undefined)

  // Appearance (Task 9) — offered to every widget type (WidgetRenderer.tsx reads these
  // regardless of wt), so this block lives outside the formatCaps gating below. String/
  // number fields follow the same "empty leaves no key" convention already used for
  // xAxisLabel/gridColor/axisTickSize above: an empty string IS the untouched state.
  const [widgetBackground,  setWidgetBackground]  = useState<string>((cfg.widget_background as string) ?? '')
  const [widgetBorderColor, setWidgetBorderColor] = useState<string>((cfg.widget_border_color as string) ?? '')
  const [widgetBorderWidth, setWidgetBorderWidth] = useState<string>(cfg.widget_border_width != null ? String(cfg.widget_border_width) : '')
  const [widgetRadius,      setWidgetRadius]      = useState<string>(cfg.widget_radius != null ? String(cfg.widget_radius) : '')
  const [widgetPadding,     setWidgetPadding]     = useState<string>(cfg.widget_padding != null ? String(cfg.widget_padding) : '')
  const [widgetSkin,        setWidgetSkin]        = useState<string>((cfg.widget_skin as string) ?? 'none')
  const [altText,           setAltText]           = useState<string>((cfg.alt_text as string) ?? '')
  const [subtitle,          setSubtitle]          = useState<string>((cfg.subtitle as string) ?? '')

  // Read once per mount -- purely to give the two colour swatches below a starting
  // look that matches the widget's real untouched appearance instead of a hardcoded
  // hex guess (see readCssVarColor above).
  const defaultSurfaceColor = useMemo(() => readCssVarColor('--surface', '#808080'), [])
  const defaultBorderColor  = useMemo(() => readCssVarColor('--border',  '#808080'), [])

  const formatCaps = useMemo(() => formattingCapabilities(wt), [wt])

  // Effective columns: use the selected widget dataset if specified, otherwise fall back to report-level columns
  const effectiveCols = useMemo<DatasetColumn[]>(() => {
    if (datasetId && datasets?.[datasetId]) {
      const ds = datasets[datasetId]
      const calcAsCol = (ds.calculated_columns ?? []).map(c => ({
        id: -1, name: c.name, dtype: 'calculated' as const, missing_pct: 0, stats: {},
      }))
      return [...ds.columns, ...calcAsCol]
    }
    return columns
  }, [datasetId, datasets, columns])

  // The dataset actually in play for this widget -- the explicit override if
  // one is set, else the report's primary dataset -- used only to decide
  // whether the chosen aggregation would misread a pre-aggregated dataset.
  const activeDs = (datasetId && datasets?.[datasetId]) ? datasets[datasetId]
    : (primaryDatasetId && datasets?.[primaryDatasetId]) ? datasets[primaryDatasetId]
    : undefined
  // Computed once here rather than twice at its JSX call site (the "is there a
  // warning" check and the rendered text were the same call, duplicated).
  const warning = aggregationWarning(activeDs, roleValues.measure ?? '', agg)

  // mounted tracks whether the first render after a widget-change has passed;
  // prevents auto-save firing on mount or when syncing state to a newly selected widget.
  const mounted = useRef(false)

  // Sync state when widget changes — reset mounted so the resulting re-render is skipped.
  useEffect(() => {
    mounted.current = false
    setTitle(widget.title ?? '')
    setDatasetId(cfg.dataset_id || '')
    setRoleValues(seedRoleValues(cfg, wt))
    setMultiRoleValues(seedMultiRoleValues(cfg, wt))
    setModelOpts(seedModelOpts(cfg))
    setAgg(cfg.aggregation ?? 'sum')
    setAgg2((cfg.aggregation2 as string) ?? '')
    setExtraFields(seedExtras(cfg))
    setLimit(cfg.limit ?? null)
    setSort(cfg.sort ?? 'desc')
    setSortBy(cfg.sort_by ?? '')
    setSortCustom(Array.isArray(cfg.sort_custom) ? (cfg.sort_custom as unknown[]).join(', ') : '')
    setHavingOp((cfg.having as {op?:string}[] | undefined)?.[0]?.op ?? '')
    setObjFilters(((cfg.filters as { column?: string; op?: string; value?: unknown }[] | undefined) ?? [])
      .map(f => ({ column: String(f.column ?? ''), op: String(f.op ?? 'eq'), value: f.op === 'relative' ? JSON.stringify(parseSpec(f.value)) : String(f.value ?? '') })))
    setRankMode((cfg.rank as {mode?:string} | undefined)?.mode ?? '')
    setRankN((cfg.rank as {n?:number} | undefined)?.n != null ? String((cfg.rank as {n:number}).n) : '')
    setQuickCalc((cfg.quick_calc as string) ?? '')
    setSuppressBelow(cfg.suppress_below != null ? String(cfg.suppress_below) : '')
    setSuppressComplement(!!cfg.suppress_complement)
    setHavingValue((cfg.having as {value?:unknown}[] | undefined)?.[0]?.value != null ? String((cfg.having as {value?:unknown}[])[0].value) : '')
    setSortCol(cfg.sort_col ?? '')
    setSortKeys(Array.isArray(cfg.sort_keys) ? (cfg.sort_keys as { col: string; dir: string }[]) : [])
    setRunning(cfg.running ?? '')
    setContent(cfg.content ?? '')
    setLabel(cfg.label ?? 'Click me')
    setTableCols(cfg.columns ?? [])
    setRtl(cfg.rtl ?? false)
    setBins((cfg.bins as number) ?? 10)
    setBaseline((cfg.baseline as number) ?? 0)
    setFitLine((cfg.fit_line as string) ?? '')
    setTargetValue(cfg.target_value != null ? String(cfg.target_value) : '')
    setDrillthroughPageId(cfg.drillthroughPageId != null ? String(cfg.drillthroughPageId) : '')
    setTooltipPageId(cfg.tooltipPageId != null ? String(cfg.tooltipPageId) : '')
    setHierarchyNodeId(cfg.hierarchyNodeId != null ? String(cfg.hierarchyNodeId) : '')
    setDimensionGranularity((cfg.dimension_granularity as string) ?? '')
    setFiscalStart(cfg.fiscal_start_month != null ? String(cfg.fiscal_start_month) : '')
    setAction((cfg.action as string) ?? '')
    setActionPageId(cfg.actionPageId != null ? String(cfg.actionPageId) : '')
    setCarryFilters(!!cfg.carry_filters)
    setActionBookmarkId(cfg.actionBookmarkId != null ? String(cfg.actionBookmarkId) : '')
    setActionUrl((cfg.actionUrl as string) ?? '')
    setActionReportId(cfg.actionReportId != null ? String(cfg.actionReportId) : '')
    setActionParamName((cfg.actionParamName as string) ?? '')
    setActionParamValue((cfg.actionParamValue as string) ?? '')
    setBarMode((cfg.bar_mode as string) ?? 'clustered')
    setForecastMethod((cfg.method as string) ?? 'ets')
    setImageUrl((cfg.url as string) ?? '')
    setImageAlt((cfg.alt as string) ?? '')
    setImageFit((cfg.fit as string) ?? 'contain')
    setWebUrl((cfg.url as string) ?? '')
    setCustomUrl((cfg.url as string) ?? '')
    setShapeKind((cfg.shape as string) ?? 'rectangle')
    setShapeFill((cfg.fill as string) ?? '#6c8fff')
    setShapeStroke((cfg.stroke as string) ?? '#6c8fff')
    setShowAverageLine(!!(cfg.analytics?.showAverageLine))
    setReferenceValue(cfg.analytics?.referenceValue != null ? String(cfg.analytics.referenceValue) : '')
    setReferenceLabel((cfg.analytics?.referenceLabel as string) ?? '')
    setReferenceColor((cfg.analytics?.referenceColor as string) ?? '#f59e0b')
    setDisplayRules((cfg.display_rules as DisplayRule[]) ?? [])
    setXAxisLabel((cfg.x_axis_label as string) ?? '')
    setYAxisLabel((cfg.y_axis_label as string) ?? '')
    setAxisTickSize(cfg.axis_tick_size != null ? String(cfg.axis_tick_size) : '')
    setAxisTickColor((cfg.axis_tick_color as string) ?? '')
    setAxisLine(cfg.axis_line)
    setTickLine(cfg.tick_line)
    setXAxisAngle(typeof cfg.x_axis_angle === 'number' ? cfg.x_axis_angle : undefined)
    setYAxisAngle(typeof cfg.y_axis_angle === 'number' ? cfg.y_axis_angle : undefined)
    setYScale(cfg.y_scale)
    setYMin(cfg.y_min != null ? String(cfg.y_min) : '')
    setYMax(cfg.y_max != null ? String(cfg.y_max) : '')
    setShowGrid(cfg.grid)
    setGridStyle(cfg.grid_style)
    setGridColor((cfg.grid_color as string) ?? '')
    setWallColor((cfg.wall_color as string) ?? '')
    setShowAsTable(cfg.show_as_table as boolean | undefined)
    setOverviewAxis(cfg.overview_axis as boolean | undefined)
    setLatticeRows((cfg.lattice_rows as string) ?? '')
    setLatticeCols((cfg.lattice_columns as string) ?? '')
    setAnimateBy((cfg.animate_by as string) ?? '')
    setAnimateGran((cfg.animate_granularity as string) ?? '')
    setSlicerMode((cfg.slicer_mode as string) ?? 'auto')
    setContainerMode((cfg.container_mode as string) ?? 'group')
    setContainerId(cfg.container_id != null ? String(cfg.container_id) : '')
    setShowLegend(cfg.legend)
    setLegendPosition(cfg.legend_position as 'top' | 'bottom' | 'left' | 'right' | undefined)
    setDataLabels(cfg.data_labels)
    setSeriesPatterns(cfg.series_patterns as boolean | undefined)
    setShowTotals(cfg.show_totals)
    setShowSubtotals(cfg.show_subtotals)
    setTotalsPosition(cfg.totals_position as 'before' | 'after' | undefined)
    setTotalsScope(cfg.totals_scope as 'all' | 'shown' | undefined)
    setTableRowNumbers(cfg.table_row_numbers)
    setTableRowLines(cfg.table_row_lines)
    setTableBanding(cfg.table_banding)
    setTableCondensed(cfg.table_condensed)
    setTableSparkline(cfg.sparkline as boolean | undefined)
    setWidgetBackground((cfg.widget_background as string) ?? '')
    setWidgetBorderColor((cfg.widget_border_color as string) ?? '')
    setWidgetBorderWidth(cfg.widget_border_width != null ? String(cfg.widget_border_width) : '')
    setWidgetRadius(cfg.widget_radius != null ? String(cfg.widget_radius) : '')
    setWidgetPadding(cfg.widget_padding != null ? String(cfg.widget_padding) : '')
    setWidgetSkin((cfg.widget_skin as string) ?? 'none')
    setAltText((cfg.alt_text as string) ?? '')
    setSubtitle((cfg.subtitle as string) ?? '')
    setBoundarySetId(cfg.boundary_set_id != null ? String(cfg.boundary_set_id) : '')
    setForecastTarget(cfg.forecast_target != null ? String(cfg.forecast_target) : '')
    setCentralityMetric((cfg.centrality_metric as string) ?? 'degree')
    setScriptCode((cfg.code as string) ?? '')
    setTransparent(cfg.transparent === true)
    setLegendTitle((cfg.legend_title as string) ?? '')
    setY2AxisLabel((cfg.y2_axis_label as string) ?? '')
    setDonutTotal(cfg.donut_total !== false)
    setDonutTotalLabel((cfg.donut_total_label as string) ?? '')
    setContainerBackground((cfg.background_url as string) ?? '')
    setLayer(cfg.z != null ? String(cfg.z) : '')
    setForecastTarget(cfg.forecast_target != null ? String(cfg.forecast_target) : '')
    setCentralityMetric((cfg.centrality_metric as string) ?? 'degree')
    setContainerBackground((cfg.background_url as string) ?? '')
    setLayer(cfg.z != null ? String(cfg.z) : '')
  }, [widget.id])

  // Emit config changes — debounced 600 ms, skips the first render after a widget switch.
  useEffect(() => {
    if (!mounted.current) { mounted.current = true; return }

    let config: Record<string, unknown>
    // Written only when they say something. The panel shows "Descending" and
    // an unticked RTL box for a config that has neither, and writing those
    // defaults back on the first unrelated edit changed meaning: a time axis
    // with no `sort` runs oldest first, and a stored `rtl: false` reads as
    // "force left to right" to anything that does not know better.
    const sortPart = cfg.sort !== undefined || sort !== 'desc' ? { sort } : {}
    const rtlPart = rtl ? { rtl: true } : {}
    if (wt === 'text')   { config = { content, ...rtlPart } }
    else if (wt === 'button') {
      config = { label, ...rtlPart }
      if (action) config.action = action
      if (action === 'navigate' && actionPageId) config.actionPageId = Number(actionPageId)
      if (action === 'navigate' && actionPageId && carryFilters) config.carry_filters = true
      if (action === 'bookmark' && actionBookmarkId) config.actionBookmarkId = Number(actionBookmarkId)
      if (action === 'url' && actionUrl) config.actionUrl = actionUrl
      if (action === 'report' && actionReportId) config.actionReportId = Number(actionReportId)
      if (action === 'set_param' && actionParamName) {
        config.actionParamName = actionParamName
        config.actionParamValue = actionParamValue
      }
    }
    else if (wt === 'image') { config = { url: imageUrl, alt: imageAlt, fit: imageFit } }
    else if (wt === 'web_content') { config = { url: webUrl.trim() } }
    else if (wt === 'shape') { config = { shape: shapeKind, fill: shapeFill, stroke: shapeStroke } }
    else {
      // A grid (a second dimension) reads neither a sort column nor a running
      // metric, and the panel hides both there: not written either (E08).
      const isGrid = !!roleValues.category2
      config = { aggregation: agg, ...(limit ? { limit } : {}), ...sortPart, ...(sortBy ? { sort_by: sortBy } : {}), ...(sortCol && !isGrid ? { sort_col: sortCol } : {}), ...rtlPart, ...(running && !isGrid ? { running } : {}) }
      if (wt === 'slicer' && slicerMode !== 'auto') config.slicer_mode = slicerMode
      // Only when set: an absent key means countries, and writing an explicit
      // null would make "unset" and "countries" two states that look different
      // in the stored config and identical on screen.
      if (BOUNDARY_SET_WIDGETS.has(wt) && boundarySetId) {
        config.boundary_set_id = Number(boundarySetId)
      }
      // Kept whole, half-typed pins included. Dropping the invalid ones here
      // would delete the row the author is still filling in and make the
      // editor fight the typing; the renderer skips them, and the editor says
      // which ones it will skip.
      if (PIN_WIDGETS.has(wt) && pins.length) config.pins = pins.map(toStoredPin)
      // Written even when empty: clearing every layer is how an author starts
      // again, and dropping the key would restore the previous graph.
      if (wt === 'custom_graph') config.layers = graphLayers
      // Only when there is a stack: without one the layered map keeps drawing
      // its two classic layers from the role fields.
      if (wt === 'map_layers' && mapLayers.length) config.layers = mapLayers
      // Only ONE mode's keys are ever written. The shaper branches on
      // `id_col && parent_col`, so leaving stale keys from the other mode
      // would silently pick parent-child over the levels the user just chose.
      if (HIERARCHY_WIDGETS.includes(wt as typeof HIERARCHY_WIDGETS[number])) {
        if (hierMode === 'parent_child') {
          if (hierIdCol) config.id_col = hierIdCol
          if (hierParentCol) config.parent_col = hierParentCol
          if (hierLabelCol) config.label_col = hierLabelCol
        } else if (hierLevels.length) {
          config.levels = hierLevels
        }
      }
      if (wt === 'small_multiples') {
        if (facetBy) config.facet_by = facetBy
        config.inner_widget_type = facetInner
        const lim = Number(facetLimit)
        if (lim > 0) config.facet_limit = Math.min(lim, FACET_MAX_PANELS)
      }
      if (wt === 'forecast') {
        const p = Number(forecastPeriods)
        if (p >= FORECAST_MIN_PERIODS) config.forecast_periods = Math.min(p, FORECAST_MAX_PERIODS)
      }
      if (wt === 'custom_visual' && customUrl.trim()) config.url = customUrl.trim()
      if (wt === 'script' && scriptCode.trim()) config.code = scriptCode
      if (transparent) config.transparent = true
      if (legendTitle.trim()) config.legend_title = legendTitle.trim()
      if (y2AxisLabel.trim()) config.y2_axis_label = y2AxisLabel.trim()
      // The total is on by default now (the donut's centre is where the reader
      // looks for "out of how much"), so only turning it OFF is stored.
      if (wt === 'donut' && !donutTotal) config.donut_total = false
      if (wt === 'donut' && donutTotal) {
        if (donutTotalLabel.trim()) config.donut_total_label = donutTotalLabel.trim()
      }
      const customList = sortCustom.split(',').map(x => x.trim()).filter(Boolean)
      if (customList.length > 0) config.sort_custom = customList
      // Multi-column sort is a raw table/list feature (the shaper's ungrouped branch);
      // only rows with a chosen column are persisted, and the order IS the priority.
      const keptSortKeys = sortKeys.filter(k => k.col)
      if ((wt === 'table' || wt === 'list') && keptSortKeys.length > 0) config.sort_keys = keptSortKeys
      if (havingOp && havingValue !== '' && !isNaN(Number(havingValue))) {
        config.having = [{ op: havingOp, value: Number(havingValue) }]
      }
      const keptFilters = objFilters.filter(f => f.column && f.value !== ''
          && (f.op !== 'relative' || specProblem(parseSpec(f.value)) === null))
        .map(f => ({ column: f.column, op: f.op,
          value: f.op === 'relative' ? parseSpec(f.value) as unknown as string | number | string[]
            : f.op === 'in' ? f.value.split(',').map(x => x.trim()).filter(Boolean)
            : isNaN(Number(f.value)) || f.value === '' ? f.value : Number(f.value) }))
      if (keptFilters.length > 0) config.filters = keptFilters
      if (rankMode && rankN !== '' && (rankN.startsWith('@') || Number(rankN) > 0)) {
        // '@name' passes through verbatim: the server substitutes the report
        // parameter's numeric value, so a slider can drive the rank count.
        config.rank = { mode: rankMode, n: rankN.startsWith('@') ? rankN : Number(rankN),
                        ...(rankPercent ? { percent: true } : {}),
                        ...(rankOther ? { other: true } : {}) }
      }
      if (quickCalc) config.quick_calc = quickCalc
      if (suppressBelow !== '' && !isNaN(Number(suppressBelow)) && Number(suppressBelow) > 0) {
        config.suppress_below = Number(suppressBelow)
        if (suppressComplement) config.suppress_complement = true
      }
      for (const rf of (ROLE_SPECS[wt] ?? []).filter(rf => !rf.multi)) {
        const v = roleValues[rf.role]
        if (v) config[configKeyFor(rf.role)] = v
      }
      for (const rf of (ROLE_SPECS[wt] ?? []).filter(rf => rf.multi)) {
        const vals = multiRoleValues[rf.role] ?? []
        if (vals.length > 0) config[rf.role] = vals
      }
      if (tableCols.length > 0) config.columns = tableCols
      if (wt === 'histogram') config.bins = bins
      if (wt === 'needle') config.baseline = baseline
      if (wt === 'bubble' && fitLine) config.fit_line = fitLine
      if (autoReload !== '' && Number(autoReload) >= 5) config.auto_reload_seconds = Number(autoReload)
      if (wt === 'gauge' && targetValue !== '' && !isNaN(Number(targetValue))) config.target_value = Number(targetValue)
      if (wt === 'gauge' && gaugeShape !== 'arc') config.gauge_shape = gaugeShape
      if (wt === 'bubble_change') {
        if (animPos !== 'none') config.anim_label_position = animPos
        if (animOrder === 'desc') config.anim_order = 'desc'
        if (animPos !== 'none') {
          if (Number(animSize) > 0 && Number(animSize) !== 44) config.anim_label_size = Number(animSize)
          if (animStyle !== 'bold') config.anim_label_style = animStyle
          const op = Number(animOpacity)
          if (!isNaN(op) && op >= 0 && op <= 1 && op !== 0.25) config.anim_label_opacity = op
          if (animBox) config.anim_label_box = true
        }
      }
    }
    if (datasetId) config.dataset_id = datasetId
    if (drillthroughPageId) config.drillthroughPageId = Number(drillthroughPageId)
    if (tooltipPageId) config.tooltipPageId = Number(tooltipPageId)
    if (hierarchyNodeId) config.hierarchyNodeId = Number(hierarchyNodeId)
    if (dimensionGranularity) config.dimension_granularity = dimensionGranularity
    if (dimensionGranularity.startsWith('fiscal') && fiscalStart) config.fiscal_start_month = Number(fiscalStart)
    if (agg2) config.aggregation2 = agg2
    if (wt === 'bar' && barMode !== 'clustered') config.bar_mode = barMode
    // Degree is the renderer's own fallback, so writing it explicitly would
    // make "unset" and "degree" two spellings of one state.
    if (wt === 'network' && centralityMetric !== 'degree') {
      config.centrality_metric = centralityMetric
    }
    if (wt === 'forecast' && forecastMethod !== 'ets') config.method = forecastMethod
    if (isModel) Object.assign(config, modelOptsConfig(wt, modelOpts))
    // Only when asked. An absent key means "no target": the shaper then does
    // no extra work and the chart carries no caption, which is what every
    // forecast widget has always been.
    if (wt === 'forecast' && forecastTarget.trim() !== ''
        && Number.isFinite(Number(forecastTarget))) {
      config.forecast_target = Number(forecastTarget)
    }
    if (displayRules.length > 0) config.display_rules = displayRules

    if (wt === 'bar' || wt === 'line') {
      const analytics: Record<string, unknown> = {}
      if (showAverageLine) analytics.showAverageLine = true
      if (referenceValue !== '' && !isNaN(Number(referenceValue))) {
        analytics.referenceValue = Number(referenceValue)
        if (referenceLabel) analytics.referenceLabel = referenceLabel
        analytics.referenceColor = referenceColor
      }
      if (Object.keys(analytics).length > 0) config.analytics = analytics
    }

    // Formatting (Task 9) — only write keys the capability map actually grants this
    // widget type, so a saved config never carries an option its renderer ignores.
    // Fix round 2: within a granted capability, a boolean/enum key is written ONLY when
    // its state is defined (i.e. the user actually touched that control) -- see the
    // state-declaration comment above for why an invented default must never be
    // persisted. String/number fields already only write when non-empty, which is the
    // same "untouched leaves no key" behaviour for their shape.
    const caps = formattingCapabilities(wt)
    // Containment is not axis formatting. These lived inside the `grid`
    // capability, and `container` HAS no capabilities -- so the container-style
    // select saved nothing, and an axis-less widget (pie, donut, KPI) could
    // never be placed in a container at all.
    if (wt === 'container') {
      if (containerMode !== 'group') config.container_mode = containerMode
      // Only on precision, and only when set: a background on a tabbed
      // container would be stored and never drawn.
      if (containerMode === 'precision' && containerBackground.trim()) {
        config.background_url = containerBackground.trim()
      }
    } else {
      if (containerId) config.container_id = Number(containerId)
      if (layer.trim() !== '' && Number(layer) !== 0) config.z = Number(layer)
    }
    if (caps.includes('axes')) {
      if (xAxisLabel) config.x_axis_label = xAxisLabel
      if (yAxisLabel) config.y_axis_label = yAxisLabel
      if (axisTickSize !== '' && !isNaN(Number(axisTickSize))) config.axis_tick_size = Number(axisTickSize)
      if (axisTickColor) config.axis_tick_color = axisTickColor
      // Only where the renderer feeds labels to the planner; elsewhere the key
      // would sit in the saved config doing nothing.
      if (xAxisAngle !== undefined && caps.includes('xCategoryAxis')) config.x_axis_angle = xAxisAngle
      if (yAxisAngle !== undefined) config.y_axis_angle = yAxisAngle
      if (axisLine !== undefined) config.axis_line = axisLine
      if (tickLine !== undefined) config.tick_line = tickLine
    }
    if (caps.includes('yScale')) {
      if (yScale !== undefined) config.y_scale = yScale
    }
    if (caps.includes('yDomain')) {
      if (yMin !== '' && !isNaN(Number(yMin))) config.y_min = Number(yMin)
      if (yMax !== '' && !isNaN(Number(yMax))) config.y_max = Number(yMax)
    }
    if (caps.includes('grid')) {
      if (showGrid !== undefined) config.grid = showGrid
      if (gridStyle !== undefined) config.grid_style = gridStyle
      if (gridColor) config.grid_color = gridColor
      if (wallColor) config.wall_color = wallColor
      if (showAsTable !== undefined) config.show_as_table = showAsTable
    }
    if (caps.includes('legend')) {
      if (showLegend !== undefined) config.legend = showLegend
      if (legendPosition !== undefined) config.legend_position = legendPosition
    }
    if (caps.includes('overview')) {
      if (overviewAxis !== undefined) config.overview_axis = overviewAxis
    }
    // A role's further fields, only beside its first one (extraKeyFor says
    // where each type keeps them; the server refuses them anywhere else).
    for (const role of Object.keys(EXTRA_KEY_OF)) {
      const key = extraKeyFor(wt, role, roleValues)
      const main = roleValues[role]
      if (!key || !main) continue
      const extra = (extraFields[key] ?? []).filter(v => v && v !== main)
      if (extra.length) config[key] = extra
    }
    if ((LATTICE_WIDGETS as readonly string[]).includes(wt)) {
      if (latticeRows) config.lattice_rows = latticeRows
      if (latticeCols) config.lattice_columns = latticeCols
    }
    if ((ANIMATION_WIDGETS as readonly string[]).includes(wt) && animateBy) {
      config.animate_by = animateBy
      if (animateGran) config.animate_granularity = animateGran
    }
    if (caps.includes('dataLabels')) {
      if (dataLabels !== undefined) config.data_labels = dataLabels
    }
    if (caps.includes('patterns')) {
      if (seriesPatterns !== undefined) config.series_patterns = seriesPatterns
    }
    if (caps.includes('tableOptions')) {
      if (showTotals !== undefined) config.show_totals = showTotals
      if (showSubtotals !== undefined) config.show_subtotals = showSubtotals
      if (totalsPosition !== undefined) config.totals_position = totalsPosition
      if (totalsScope !== undefined) config.totals_scope = totalsScope
      if (tableRowNumbers !== undefined) config.table_row_numbers = tableRowNumbers
      if (tableRowLines !== undefined) config.table_row_lines = tableRowLines
      if (tableBanding !== undefined) config.table_banding = tableBanding
      if (tableCondensed !== undefined) config.table_condensed = tableCondensed
      // Per-row trend sparkline: only crosstab/matrix rows carry a series across columns.
      if ((wt === 'crosstab' || wt === 'matrix') && tableSparkline !== undefined) config.sparkline = tableSparkline
    }

    // Appearance (Task 9) — every widget type gets these, so no capability gate.
    if (widgetBackground) config.widget_background = widgetBackground
    if (widgetBorderColor) config.widget_border_color = widgetBorderColor
    if (widgetBorderWidth !== '' && !isNaN(Number(widgetBorderWidth))) config.widget_border_width = Number(widgetBorderWidth)
    if (widgetRadius !== '' && !isNaN(Number(widgetRadius))) config.widget_radius = Number(widgetRadius)
    if (widgetPadding !== '' && !isNaN(Number(widgetPadding))) config.widget_padding = Number(widgetPadding)
    if (widgetSkin && widgetSkin !== 'none') config.widget_skin = widgetSkin
    if (altText) config.alt_text = altText
    if (subtitle.trim()) config.subtitle = subtitle.trim()

    // E03: the panel rebuilds only what it manages. Everything else the
    // stored config holds -- interactions, the hidden flag and tab order set
    // in other panes, settings only the API writes -- is carried through,
    // under what the panel wrote.
    config = { ...keepUnmanaged(migrated), ...config }

    // Journal first, so a tab closed inside the 600 ms window leaves a trace the
    // builder can offer to restore (lib/pendingEdits.ts); cleared once sent.
    const pendingId = widget.id
    savePending(pendingId, config, title)
    const timer = setTimeout(() => { onUpdate(config, title); clearPending(pendingId) }, 600)
    return () => clearTimeout(timer)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [title, datasetId, JSON.stringify(roleValues), JSON.stringify(multiRoleValues), JSON.stringify(modelOpts), agg, limit, sort, sortBy, sortCol, sortCustom, agg2, JSON.stringify(extraFields), havingOp, havingValue, JSON.stringify(objFilters), rankMode, rankN, rankPercent, rankOther, quickCalc, suppressBelow, suppressComplement, running, content, label, rtl, tableCols.join(','), JSON.stringify(sortKeys), bins, baseline, fitLine, targetValue, gaugeShape, animPos, animOrder, animSize, animStyle, animOpacity, animBox, autoReload, drillthroughPageId, tooltipPageId, hierarchyNodeId, dimensionGranularity, fiscalStart, action, actionPageId, carryFilters, actionBookmarkId, actionUrl, actionReportId, actionParamName, actionParamValue, barMode, forecastMethod, imageUrl, imageAlt, imageFit, webUrl, customUrl, shapeKind, shapeFill, shapeStroke, showAverageLine, referenceValue, referenceLabel, referenceColor, JSON.stringify(displayRules), xAxisLabel, yAxisLabel, axisTickSize, axisTickColor, axisLine, tickLine, xAxisAngle, yAxisAngle, yScale, yMin, yMax, showGrid, gridStyle, gridColor, wallColor, showAsTable, overviewAxis, latticeRows, latticeCols, animateBy, animateGran, slicerMode, containerMode, containerId, showLegend, legendPosition, dataLabels, seriesPatterns, showTotals, showSubtotals, totalsPosition, totalsScope, tableRowNumbers, tableRowLines, tableBanding, tableCondensed, tableSparkline, widgetBackground, widgetBorderColor, widgetBorderWidth, widgetRadius, widgetPadding, widgetSkin, altText, subtitle, boundarySetId, forecastTarget, centralityMetric,
      containerBackground, layer, scriptCode, transparent, legendTitle,
      y2AxisLabel, donutTotal, donutTotalLabel,
    // Hierarchy / faceting / forecast state. Omitting these would let the
    // panel BUILD the config and never re-emit it -- the controls would
    // appear to work and save nothing.
    hierMode, hierLevels, hierIdCol, hierParentCol, hierLabelCol,
    facetBy, facetInner, facetLimit, forecastPeriods,
    // Stringified because it is an array of objects: by identity it changes on
    // every keystroke that rebuilds the list, and by omission it never changes
    // at all -- which is the failure the comment above describes, and the one
    // the seam test in MapPinsEditor.test.tsx caught here.
    JSON.stringify(pins), JSON.stringify(graphLayers), JSON.stringify(mapLayers)])

  // Id-like numeric columns (state_id, student_id, ...) are categories wearing a
  // numeric dtype, not measures — offering them for SUM/AVG produces a number
  // nobody wants. Excluded from the general measure list, but a column already
  // selected on an existing widget stays offered (with an "(id)" suffix) so an
  // old config doesn't silently lose its selection.
  const isMeasureCol = (c: DatasetColumn) =>
    c.dtype === 'numeric' || c.dtype === 'calculated'
  const numCols = effectiveCols.filter(c => isMeasureCol(c) && !isIdLikeColumn(c))
  const idNumCols = effectiveCols.filter(c => c.dtype === 'numeric' && isIdLikeColumn(c))
  const measureOptions = (selected: (string | undefined)[]) => {
    const kept = idNumCols.filter(c => selected.includes(c.name))
    return [...numCols, ...kept].map(c => ({
      value: c.name,
      label: isIdLikeColumn(c) ? `${c.name} (id)` : c.name, // i18n-ok: a column name and its "id" tag
    }))
  }

  // Group aggregations for display
  const aggGroups = AGGREGATIONS.reduce<Record<string, typeof AGGREGATIONS[number][]>>((acc, a) => {
    ;(acc[a.group] ??= []).push(a)
    return acc
  }, {})
  /** The aggregations this widget type may use, grouped; `current` stays
   *  listed even when it would not be offered, so it is never silently
   *  replaced. A partition chart (sunburst, icicle) offers only additive ones:
   *  a wedge is a share of its parent. */
  const aggOptionGroups = (current: string, partitionRule: boolean) =>
    Object.entries(aggGroups).map(([group, items]) => (
      <optgroup key={group} label={`── ${L(group)} ──`}>
        {items
          .filter(a => !partitionRule || !PARTITION_WIDGETS.includes(wt) || ADDITIVE_AGGREGATIONS.includes(a.value))
          .filter(a => aggregationOffered(wt, a.value) || a.value === current)
          .map(a => <option key={a.value} value={a.value}>{L(a.label)}</option>)}
      </optgroup>
    ))

  // The label is a SIBLING of the control, so it needs htmlFor to be associated with
  // it -- without that the control has no accessible name at all, and a screen reader
  // announces a bare combobox or spinbutton. Found by driving the real app: every
  // field built through this helper was unreachable by its visible label.
  /** "Group dates by", under a dimension that is a date column. One control
   *  for both ways the dimension field is drawn: the hierarchy picker (a
   *  dataset with a drill hierarchy) used to leave it out, so a line chart
   *  over dates could not be grouped by month there. */
  const dateGrouping = () => (
    // Buckets for a date axis, including the Hijri calendar
    // (Phase 7.5): tabular Hijri, labelled 1448-03, month
    // named on the axis in the reader's language.
    <div style={{ margin:'-6px 0 10px' }}>
      <label htmlFor="date-granularity" style={{ fontSize: 11, color:'var(--muted)' }}>{L("Group dates by")}</label>
      <select id="date-granularity" aria-label={L("Group dates by")} value={dimensionGranularity}
        onChange={e => setDimensionGranularity(e.target.value)} style={{ width:'100%', fontSize:11 }}>
        <option value="">{L("each date")}</option>
        {['day', 'week', 'month', 'quarter', 'year'].map(g => <option key={g} value={g}>{g}</option>)}
        <option value="hour">{L("hour")}</option>
        <option value="hour_of_day">{L("hour of day (00–23)")}</option>
        <option value="hijri_month">{L("Hijri month (هجري)")}</option>
        <option value="hijri_year">{L("Hijri year (هجري)")}</option>
        {/* A forecast continues a calendar sequence (next month, next
            quarter); fiscal labels are not one it can extend. */}
        {wt !== 'forecast' && <option value="fiscal_quarter">{L("fiscal quarter")}</option>}
        {wt !== 'forecast' && <option value="fiscal_year">{L("fiscal year")}</option>}
      </select>
      {dimensionGranularity.startsWith('fiscal') && (
        <div style={{ marginTop: 4 }}>
          <label htmlFor="fiscal-start-month" style={{ fontSize: 11, color:'var(--muted)' }}>{L("Fiscal year starts in")}</label>
          <select id="fiscal-start-month" value={fiscalStart} onChange={e => setFiscalStart(e.target.value)}
            style={{ width:'100%', fontSize:11 }}>
            <option value="">{orgFiscalStart
              ? L("the organisation's month ({month})", { month: monthName(orgFiscalStart, language) })
              : L("the organisation's month")}</option>
            {Array.from({ length: 12 }, (_, i) => i + 1).map(m => (
              <option key={m} value={String(m)}>{monthName(m, language)}</option>
            ))}
          </select>
          <div style={{ fontSize: 11, color:'var(--muted)', marginTop:2 }}>
            {L("Labelled FY2025/26 and FY2025/26-Q1 (FY2025 when the year starts in January). Admin → Calendar sets the organisation's month.")}
          </div>
        </div>
      )}
      {dimensionGranularity.startsWith('hijri') && (
        <div style={{ fontSize: 11, color:'var(--muted)', marginTop:2 }}>
          {L("Tabular Hijri calendar: may differ by a day from Umm al-Qura at a month's start.")}
        </div>
      )}
    </div>
  )

  const fld = (lbl: string, el: React.ReactElement) => {
    const id = 'fld-' + lbl.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
    return (
      <div style={{ marginBottom: 12 }}>
        <label htmlFor={id} style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>{L(lbl)}</label>
        {/* An id already set by the caller wins, so a field that needs a specific id
            for other reasons is not silently renamed. */}
        {cloneElement(el, { id: (el.props as { id?: string }).id ?? id })}
      </div>
    )
  }

  // Options may carry a `group`; grouped options render under <optgroup>s in
  // first-seen order, so a picker reads Categories / Dates / Numbers instead
  // of one alphabet soup. Ungrouped callers are unchanged.
  const sel = (value: string, onChange: (v: string) => void, options: {value:string;label:string;group?:string}[], ph = '— none —') => {
    const groups = [...new Set(options.map(o => o.group).filter((g): g is string => !!g))]
    return (
      <select value={value} onChange={e => onChange(e.target.value)} style={{ width:'100%' }}>
        <option value="">{L(ph)}</option>
        {options.filter(o => !o.group).map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        {groups.map(g => (
          <optgroup key={g} label={roleL(g)}>
            {options.filter(o => o.group === g).map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </optgroup>
        ))}
      </select>
    )
  }

  /** "Aa region · 4 values": a type marker and, when known, the distinct count. */
  const fieldLabel = (c: DatasetColumn) => {
    const marker = c.dtype === 'calculated' ? 'ƒx' : c.dtype === 'numeric' ? '#' : c.dtype === 'datetime' ? '◷' : 'Aa'
    const n = distinctCounts?.[c.name]
    return `${marker} ${c.name}${n != null && c.dtype !== 'numeric' ? ` · ${L(n === 1 ? '{n} value' : '{n} values', { n: n.toLocaleString() })}` : ''}`
  }
  const fieldGroup = (c: DatasetColumn) =>
    c.dtype === 'calculated' ? 'Calculated' : c.dtype === 'numeric' ? 'Numbers' : c.dtype === 'datetime' ? 'Dates' : 'Categories'
  const colOptions = effectiveCols.map(c => ({ value: c.name, label: fieldLabel(c), group: fieldGroup(c) }))

  // A rule addresses the widget's RESULT columns, not its dataset columns. For the
  // widget types shape_series serves (backend/app/services/widget_data.py), the result
  // shape depends on which of dimension/dimension2/measure are configured — NOT on the
  // widget type — and mirrors shape_series's own dispatch order exactly:
  //   1. dimension + dimension2 -> crosstab: [dimension, '__total__'].
  //   2. dimension only         -> grouped series: {name, value} rows.
  //   3. no dimension, but a measure IS set -> the scalar/KPI branch
  //      (widget_data.py:287-305): a single {name, value} row, NOT dataset columns.
  //      A measure-only KPI card is an entirely ordinary configuration — RoleField's
  //      `required` is a UI label only, never enforced — so this is reachable for any
  //      shape_series-dispatched widget, KPI very much included.
  //   4. neither dimension nor measure -> the true raw-table case: the columns the
  //      author picked above (or every dataset column, if none picked).
  // Widget types with a bespoke shaper (bubble, heatmap, gauge, …) keep the previous
  // ['name', 'value'] approximation — their actual shape isn't modelled here.
  // waterfall is the one exception: shape_waterfall (widget_data.py) returns
  // {name, start, delta, end} rows, not {name, value} — display_rules.py's waterfall
  // branch evaluates rules against exactly those columns, so the panel must offer them
  // or an author can never author a numeric waterfall rule.
  const WATERFALL_RULE_COLUMNS = ['name', 'start', 'delta', 'end']
  const WATERFALL_NUMERIC_COLUMNS = new Set(['start', 'delta', 'end'])
  const dimension  = roleValues.category  || ''
  const dimension2 = roleValues.category2 || ''
  // E08: the "Sort & limit" controls this widget type actually honours.
  const sortOpts = sortLimitOptions(wt)
  const measure    = roleValues.measure   || ''
  const ruleColumns = wt === 'waterfall'
    ? WATERFALL_RULE_COLUMNS
    : CUSTOM_SHAPE_WIDGET_TYPES.has(wt)
    ? ['name', 'value']
    : dimension && dimension2
      // Crosstab: the pivoted column names (dimension2's distinct values) aren't
      // statically knowable without fetching data, which this panel must not do.
      // Only the dimension column and the `__total__` row-total shape_series always
      // adds are guaranteed to exist.
      ? [dimension, '__total__']
      : (dimension || measure)
        ? ['name', 'value']
        : (tableCols.length > 0 ? tableCols : effectiveCols.map(c => c.name))

  // Coercion must be dtype-aware, not just "looks numeric": `region == "2024"` on a
  // text column must stay a string comparison, the mirror image of the `value >
  // "1000"` bug numeric coercion exists to prevent. `value` and `__total__` are
  // numeric by construction; other result columns are real dataset columns, so their
  // dtype is looked up directly. Columns of unknown/uncertain dtype (e.g. calculated
  // columns) are left uncoerced on purpose.
  const numericDatasetCols = new Set(effectiveCols.filter(c => c.dtype === 'numeric' || c.dtype === 'calculated').map(c => c.name))
  const ruleNumericColumns = ruleColumns.filter(c =>
    c === 'value' || c === '__total__' || WATERFALL_NUMERIC_COLUMNS.has(c) || numericDatasetCols.has(c))

  // Text/button/image/shape widgets never fetch data (WidgetRenderer.fetchData returns
  // early for them), so no rule_styles are ever computed for them — there is nothing a
  // display rule could paint.
  const supportsDisplayRules = wt !== 'text' && wt !== 'button' && wt !== 'image' && wt !== 'shape' && wt !== 'web_content' && wt !== 'custom_visual'

  // Panel search — narrows the ExpandableGroups below by title OR by any of the
  // group's field labels (searchTerms), so finding a specific setting (e.g.
  // "opacity", "bookmark") actually works instead of only matching the ~9 group
  // headings. Matching groups are force-opened (via ExpandableGroup's forceOpen
  // prop) so a match is never hidden behind a collapsed accordion; non-matching
  // groups are unmounted (hidden) rather than merely collapsed, which is what
  // actually "narrows" the panel. Clearing the box removes both overrides and each
  // group falls straight back to whatever its own toggled/stored state already
  // was — nothing here ever writes to that state, so the filter itself leaves no
  // trace once cleared.
  const filterActive = filterText.trim() !== ''
  const filterNeedle = filterText.trim().toLowerCase()
  const groupMatches = (title: string, terms: string[] = []) =>
    title.toLowerCase().includes(filterNeedle) || terms.some(t => t.toLowerCase().includes(filterNeedle))
  // The settings rail: the same groups, routed into the tabs a SAS author
  // already looks for them under. Keyed by group title because that is what
  // the choke point below already receives; every group sits under exactly one
  // tab, and settingsTabs.test.tsx walks the rail and asserts the reachable set
  // equals the set that exists -- so a group added later with no home here
  // fails the suite rather than quietly becoming unreachable.
  const TAB_OF_GROUP: Record<string, string> = {
    'Appearance': 'Options', 'Formatting': 'Options', 'Sort & limit': 'Options',
    'Data & aggregation': 'Data',
    // Both repeat or play the same chart over another field -- a data
    // arrangement, like the aggregation beside them.
    'Lattice (small multiples)': 'Data', 'Animation (play through)': 'Data',
    'Fields': 'Data roles',
    'Actions': 'Actions', 'Interactions': 'Actions',
    'Display rules': 'Display rules',
    'Filters': 'Filters',
    'Ranking': 'Ranks',
  }
  const SETTINGS_TABS = ['All', 'Options', 'Data', 'Data roles', 'Actions',
    'Display rules', 'Filters', 'Ranks']

  // Search outranks the tab, always. An author sitting on Ranks who types a
  // word belonging to Appearance has to be shown the match: an empty panel
  // reads as "there is no such setting", which is the one answer that must
  // never be wrong. The rail says so while it happens, and the chosen tab is
  // only held -- never rewritten -- so clearing the box returns to it.
  const groupFilterProps = (title: string, terms: string[] = []) => {
    if (filterActive) {
      const hit = groupMatches(title, terms)
      return { hidden: !hit, forceOpen: hit }
    }
    if (settingsTab === 'all') return inSection ? { hidden: !inSection.includes(TAB_OF_GROUP[title]) } : {}
    return { hidden: TAB_OF_GROUP[title] !== settingsTab }
  }

  // Searchable field labels per group, declared here (next to the filter logic that
  // consumes them, and easy to find from any group's JSX below by its id) so a field
  // added to a group's JSX gets its label added to the matching array in the same
  // review. Fields group (roles) is genuinely dynamic per widget type (ROLE_SPECS),
  // so its terms are the generic vocabulary those role labels are built from rather
  // than a literal list. Display rules / Interactions render nested subcomponents
  // whose own field labels aren't authored here, so their terms are the vocabulary
  // an author would type looking for either section.
  const FIELDS_SEARCH_TERMS       = ['Dimension', 'Measure', 'Category', 'Series', 'Breakdown', 'Value', 'X-axis', 'Y-axis', 'Group']
  const DATA_SEARCH_TERMS         = ['Bar layout', 'Clustered', 'Stacked', 'Analytics', 'Show average line', 'Reference line value', 'Reference line label', 'Aggregation', 'Running metric', 'Visible columns']
  const FILTERS_SEARCH_TERMS      = ['column', 'operator', 'Add filter']
  const RANKING_SEARCH_TERMS = ['Ranking', 'Top N', 'Bottom N', 'Rank', 'All Other', 'Percent of categories']
const SORT_SEARCH_TERMS         = ['Sort order', 'Sort by', 'Sort column', 'Multi-column sort', 'Row limit', 'Auto-reload', 'Custom order', 'Filter aggregated values', 'Rank', 'Quick calculation', 'Suppress small groups', 'Bins', 'Baseline', 'Fit Line', 'Target value', 'Gauge shape', 'Animation value']
  const FORMATTING_SEARCH_TERMS   = ['X axis label', 'Y axis label', 'Category label angle', 'Value label angle', 'Tick size', 'Tick colour', 'Show axis line', 'Show tick marks', 'Y axis scale', 'Y axis min', 'Y axis max', 'Show gridlines', 'Gridline style', 'Gridline colour', 'Wall colour', 'Show legend', 'Legend position', 'Overview axis', 'Show data labels', 'Distinguish groups by pattern', 'Show as table', 'Show totals', 'Show row subtotals', 'Row numbers', 'Row lines', 'Banded rows', 'Condensed', 'Row trend sparkline']
  const APPEARANCE_SEARCH_TERMS   = ['Background', 'Border colour', 'Border width', 'Corner radius', 'Padding', 'Skin', 'Widget description']
  const ACTIONS_SEARCH_TERMS      = ['Button action', 'Navigate to page', 'Apply bookmark', 'Open external URL', 'Go to another report', 'Set a parameter', 'Target page', 'Target URL', 'Target report ID', 'Parameter name', 'Value to set', 'Target bookmark']
  const RULES_SEARCH_TERMS        = ['rule', 'condition', 'threshold', 'bands']
  const INTERACTIONS_SEARCH_TERMS = ['cross-filter', 'drillthrough', 'tooltip', 'sync']

  // Does the chosen tab actually have anything for THIS object? Ranking only
  // renders for widget types that support it, formatting varies by type, and
  // so on -- so a tab can route an author to a blank pane, which reads as a
  // broken panel rather than as "not applicable here".
  //
  // Measured from the DOM after paint rather than recomputed from the
  // widget-type conditions: those are dozens of separate gates spread through
  // this file, and a second copy of them would be wrong the first time one
  // changed. The groups carry data-group-id for exactly this.
  const bodyRef = useRef<HTMLDivElement | null>(null)
  const [tabEmpty, setTabEmpty] = useState(false)
  // No dependency array on purpose: what renders depends on the tab, the
  // search box, the widget's type and half its config, so any list of deps
  // would be a list to get wrong. Re-measuring every render is one DOM query,
  // and the state settles immediately because the value it writes is stable.
  useLayoutEffect(() => {
    const n = bodyRef.current?.querySelectorAll('[data-group-id]').length ?? 0
    setTabEmpty(n === 0)
  })

  // ── Data roles, laid out as SAS VA does ─────────────────────────────────
  // Two levels, as SAS draws them: this pane and the Assign data dialog list
  // the object's roles and what each holds; "+ Add" on a role opens a picker
  // of the fields that role accepts (roleChoices -- one set of rules).
  //
  // A bar, line or area chart's Measure takes several fields, one series
  // each: the first is `measure`, the rest `extra_measures`. Not beside a
  // series split, which fills the series slot already.
  const multiMeasure = MULTI_MEASURE_WIDGETS.includes(wt) && !roleValues.category2
  const extendable = (role: string) => !!extraKeyFor(wt, role, roleValues)
  const roleSpecs = (ROLE_SPECS[wt] ?? []).map(rf => extendable(rf.role) ? { ...rf, multi: true } : rf)
  type RoleSpec = (typeof roleSpecs)[number]
  const fieldsOf = (rf: RoleSpec): string[] =>
    extendable(rf.role) ? [roleValues[rf.role], ...(extraFields[extraKeyFor(wt, rf.role, roleValues)!] ?? [])].filter((m): m is string => !!m)
    : rf.multi ? (multiRoleValues[rf.role] ?? [])
    : (roleValues[rf.role] ? [roleValues[rf.role]] : [])
  const setFields = (rf: RoleSpec, values: string[]) => {
    if (extendable(rf.role)) {
      const key = extraKeyFor(wt, rf.role, roleValues)!
      if (rf.role === 'category') pickCategory(values[0] ?? '')
      else setRole(rf.role, values[0] ?? '')
      setExtraFields(prev => ({ ...prev, [key]: values.slice(1) }))
      return
    }
    if (rf.multi) { setMultiRoleValues(prev => ({ ...prev, [rf.role]: values })); return }
    if (rf.role === 'category') { pickCategory(values[0] ?? ''); return }
    setRole(rf.role, values[0] ?? '')
  }
  const assignedFields: Record<string, string[]> = Object.fromEntries(roleSpecs.map(rf => [rf.role, fieldsOf(rf)]))
  const fieldKind = (f: string): FieldKind => {
    const dtype = effectiveCols.find(c => c.name === f)?.dtype
    return dtype === 'datetime' ? 'date' : dtype === 'numeric' ? 'measure' : 'category'
  }
  const pageWidgets = (pages?.find(pg => pg.id === widget.page_id)?.widgets ?? [])
    .filter(w => (ROLE_SPECS[w.widget_type] ?? []).length > 0)
  const objectLabel = (w: { title?: string | null; widget_type: string; id: number }) =>
    w.title || `${w.widget_type.charAt(0).toUpperCase()}${w.widget_type.slice(1).replace(/_/g, ' ')} ${w.id}`
  const openAssign = (role: string | null) => { setAssignRole(role); setAssignOpen(true) }
  const removeField = (role: string, f: string) => {
    const rf = roleSpecs.find(r => r.role === role)
    if (!rf) return
    if (rf.multi) { setFields(rf, fieldsOf(rf).filter(v => v !== f)); return }
    setRole(role, '')
    if (role === 'category') { setHierarchyNodeId(''); setDimensionGranularity('') }
  }
  // A series split and several measures cannot both be drawn: each role says
  // why it is closed while the other is in use.
  const addBlocked = (role: string): string | null =>
    role === 'category2' && MULTI_MEASURE_WIDGETS.includes(wt) && extraMeasures.length > 0
      ? L('A series split and several measures cannot be drawn together. Keep one measure to split it by a series.')
      : null
  const displayName = (role: string, f: string) => role === 'category' && hierarchyNodeId ? L('{name} (hierarchy)', { name: f }) : f
  const detailLabel = { display:'block', fontSize: 12, color:'var(--muted)', marginBottom:3 } as const
  const nameField = (id: string, value: string, set: (v: string) => void, placeholder: string) => (
    <div style={{ marginBottom: 8 }}>
      <label htmlFor={id} style={detailLabel}>{L("Name:")}</label>
      <input id={id} value={value} placeholder={placeholder} onChange={e => set(e.target.value)} style={{ width:'100%' }} />
    </div>
  )
  // What a field opens with. Name is the title the chart shows for it (its
  // axis), so it exists only where this type draws axes; Aggregation is the
  // widget's own aggregation of its measures.
  const fieldDetails = (role: string, f: string) => {
    const axes = formatCaps.includes('axes')
    if (role === 'measure' && !isModel) {
      const first = f === roleValues.measure
      return (<>
        {axes && first && nameField('data-role-name-measure', yAxisLabel, setYAxisLabel, f)}
        <label htmlFor="data-role-aggregation" style={detailLabel}>{L("Aggregation:")}</label>
        <select id="data-role-aggregation" value={agg} onChange={e => setAgg(e.target.value)} style={{ width:'100%' }}>
          {aggOptionGroups(agg, true)}
        </select>
        {extraMeasures.length > 0 && multiMeasure && (
          <div style={{ fontSize: 11, color:'var(--muted)', marginTop: 4 }}>{L("Every measure on this chart uses it.")}</div>
        )}
      </>)
    }
    if (role === 'measure2' && DUAL_MEASURE_WIDGETS.includes(wt)) return (<>
      {axes && nameField('data-role-name-measure2', y2AxisLabel, setY2AxisLabel, f)}
      <label htmlFor="data-role-aggregation2" style={detailLabel}>{L("Aggregation:")}</label>
      <select id="data-role-aggregation2" value={agg2} onChange={e => setAgg2(e.target.value)} style={{ width:'100%' }}>
        <option value="">{L("Same as first measure")}</option>
        {aggOptionGroups(agg2, false)}
      </select>
    </>)
    if (role === 'category') {
      const isDate = !hierarchyNodeId && fieldKind(f) === 'date'
      if (!axes && !isDate && !hierarchyNodeId) return null
      return (<>
        {axes && nameField('data-role-name-category', xAxisLabel, setXAxisLabel, f)}
        {isDate && dateGrouping()}
        {hierarchyNodeId && (
          <button type="button" onClick={() => setShowHierarchyEditor(s => !s)}
            style={{ marginTop:4, background:'none', border:'none', color:'var(--accent)', cursor:'pointer', fontSize:11, padding:0 }}>
            {L("✎ Edit hierarchy")}
          </button>
        )}
        {hierarchyNodeId && showHierarchyEditor && (
          <div style={{ marginTop:8, border:'1px solid var(--border)', borderRadius:6, padding:8, maxHeight:220, overflowY:'auto' }}>
            <HierarchyTree nodes={hierarchy ?? []} datasetId={datasetId || (primaryDatasetId ?? 0)}
              onRefresh={() => onHierarchyRefresh?.()} />
          </div>
        )}
      </>)
    }
    return null
  }
  const dataRolesPane = (
    <div data-testid="data-roles-pane" style={{ marginBottom: 8 }}>
      {pageWidgets.length > 1 && (
        <select aria-label={L("Object")} value={widget.id} style={{ width:'100%', marginBottom:10 }}
          onChange={e => window.dispatchEvent(new CustomEvent(ASSIGN_DATA_EVENT,
            { detail: { widgetId: Number(e.target.value), open: false } }))}>
          {pageWidgets.map(w => <option key={w.id} value={w.id}>{objectLabel(w)}</option>)}
        </select>
      )}
      <button type="button" onClick={() => openAssign(null)}
        style={{ display:'flex', alignItems:'center', gap:6, background:'none', border:'none', padding:'4px 0',
          margin:'0 0 8px', cursor:'pointer', font:'inherit', fontSize:13, color:'var(--text)' }}>
        <span aria-hidden style={{ fontSize:17, lineHeight:1 }}>+</span> {L("Assign data")}
      </button>
      <DataRolesList specs={roleSpecs} values={assignedFields} kindOf={fieldKind} displayName={displayName}
        onAdd={role => setAddRole(role)} onRemove={removeField} renderDetails={fieldDetails} addBlocked={addBlocked} />
    </div>
  )
  // Which fields a role may be given -- the ONE rule both the dialog's pickers
  // and the pane's "+ Add" read. What the role already holds stays offered
  // whatever its type: a widget saved before a rule existed must not open with
  // its field blanked, which the next unrelated edit would then save.
  const hierarchyOptions = hierarchy && hierarchy.length > 0 ? flattenHierarchy(hierarchy) : []
  const roleChoices = (rf: (typeof roleSpecs)[number], selected: string[]): { value: string; label: string; group?: string }[] => {
    if (rf.multi) {
      // A numeric role lists numbers; any other multi role (a decision
      // tree's predictors) takes every column the dataset has.
      // A model's response is never one of its own predictors.
      const responseCol = isModel ? (roleValues.response || roleValues.measure) : undefined
      return (roleAccepts(rf.role) === 'numeric' ? measureOptions(selected) : colOptions)
        .filter(o => !responseCol || o.value !== responseCol || selected.includes(o.value))
    }
    const kind = roleAccepts(rf.role)
    const chosen = selected[0]
    const narrowed =
      kind === 'numeric'  ? measureOptions([chosen])
    : kind === 'datetime' ? colOptions.filter(o =>
        effectiveCols.find(c => c.name === o.value)?.dtype === 'datetime')
    : colOptions
    return (chosen && !narrowed.some(o => o.value === chosen))
      ? [...narrowed, { value: chosen, label: L('{name} (current)', { name: chosen }) }]
      : narrowed
  }
  /** The dimension, from a column or (`h:<id>`) a hierarchy level. */
  const pickCategory = (v: string) => {
    if (v.startsWith('h:')) {
      const picked = hierarchyOptions.find(o => `h:${o.id}` === v)
      if (picked) {
        setRole('category', picked.column_name)
        setHierarchyNodeId(String(picked.id))
        setDimensionGranularity(picked.format ?? '')
      }
    } else {
      setRole('category', v)
      setHierarchyNodeId('')
      setDimensionGranularity('')
    }
  }

  return (
    <div ref={bodyRef} style={{ fontSize:13 }}>
      <div style={{ padding:'14px 14px 0' }}>
        <div style={{ fontWeight:650, marginBottom:14, fontSize:14, display:'flex', alignItems:'center', gap:6, color:'var(--text)' }}>
          {widgetIcon(wt)} {L('{type} settings', { type: L(wt === 'kpi' ? 'KPI' : wt.charAt(0).toUpperCase() + wt.slice(1).replace(/_/g, ' ')) })}
        </div>

        <div style={{ marginBottom: 12 }}>
          <input
            type="search"
            value={filterText}
            onChange={e => setFilterText(e.target.value)}
            placeholder={L("Filter settings…")}
            aria-label={L("Filter settings")}
            style={{ width:'100%' }}
          />
          {filterActive && settingsTab !== 'all' && (
            <div style={{ fontSize: 11, color:'var(--muted)', marginTop:4 }}>
              {L('Searching all tabs — clear the box to return to {tab}.', { tab: L(settingsTab) })}
            </div>
          )}
        </div>

        {/* One object's settings under the headings an author already looks
            for them under, rather than ten accordions in a single column. */}
        <div role="tablist" aria-label={L("Settings sections")}
          style={{ display:'flex', flexWrap:'wrap', gap:2, margin:'8px 0 2px' }}>
          {(inSection ? ['All', ...inSection] : SETTINGS_TABS).map(t => {
            const key = t === 'All' ? 'all' : t
            const on = settingsTab === key
            return (
              <button key={t} type="button" role="tab" aria-selected={on}
                onClick={() => setSettingsTab(key)}
                style={{
                  font:'inherit', fontSize: 11, fontWeight:600, cursor:'pointer',
                  padding:'3px 7px', borderRadius:5,
                  border:'1px solid ' + (on ? 'var(--accent)' : 'var(--border)'),
                  background: on ? 'var(--accent)' : 'transparent',
                  color: on ? 'var(--mc-accent-fg)' : 'var(--muted)',
                }}>
                {L(t)}
              </button>
            )
          })}
        </div>
        {tabEmpty && !filterActive && settingsTab !== 'all' && (
          <div style={{ fontSize:11, color:'var(--muted)', padding:'10px 0 2px' }}>
            {L('No {tab} settings for this object.', { tab: L(settingsTab) })}
          </div>
        )}

        {/* The object's own fields -- title, direction, transparency and the
            per-type options -- belong to no ExpandableGroup, so the rail has to
            route them explicitly or they sit under every tab. They are Options
            content, and they carry a data-group-id so the emptiness measurement
            and the reachability pin count them like any other group. Left
            visible while a search is running, because that is what they did
            before the rail existed: the box narrows groups, not the object. */}
        {(filterActive || (settingsTab === 'all' && (!inSection || inSection.includes('Options'))) || settingsTab === 'Options') && (
        <div data-group-id="object">

        {/* Dataset override — only shown when multiple datasets are attached to the report */}
        {datasets && Object.keys(datasets).length > 1 && fld('Dataset',
          <select value={datasetId} onChange={e => {
            const newId = e.target.value ? Number(e.target.value) : ''
            setDatasetId(newId)
            setRoleValues(Object.fromEntries((ROLE_SPECS[wt] ?? []).map(rf => [rf.role, ''])))
            setMultiRoleValues(Object.fromEntries((ROLE_SPECS[wt] ?? []).filter(rf => rf.multi).map(rf => [rf.role, []])))
            setSortCol('')
            setTableCols([])
          }} style={{ width:'100%' }}>
            <option value="">{primaryDatasetId && datasets[primaryDatasetId] ? L('{name} (default)', { name: datasets[primaryDatasetId].name }) : L('— report default —')}</option>
            {Object.values(datasets).map(ds => (
              <option key={ds.id} value={ds.id}>{ds.name}{ds.aggregate_of_dataset_id ? ' · ' + L('pre-aggregated') : ''}</option>
            ))}
          </select>
        )}

        {/* `title` carries the whole value: the box cannot grow, and reading a
            long title otherwise means selecting the text and scrolling it. */}
        {fld('Title', <input value={title} title={title} onChange={e => setTitle(e.target.value)} style={{ width:'100%' }} placeholder={L("Widget title")} />)}
        {/* One line under the title saying what the numbers are: the scope
            ("Share of total · all time") or the unit ("Count of orders"). */}
        {fld('Subtitle', <input value={subtitle} title={subtitle} onChange={e => setSubtitle(e.target.value)} style={{ width:'100%' }} placeholder={L("Optional — e.g. Share of total · all time")} />)}

        <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
          <input
            id="rtl-toggle"
            type="checkbox"
            checked={rtl}
            onChange={e => setRtl(e.target.checked)}
          />
          <label htmlFor="rtl-toggle" style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', cursor: 'pointer' }}>
            {L("RTL (Right to Left)")}
          </label>
        </div>

        {/* Text / Button */}
        {wt === 'text'   && fld('Content', <textarea value={content} onChange={e => setContent(e.target.value)} rows={4} style={{ width:'100%', resize:'vertical' }} placeholder={L("Enter text…")} />)}
        {wt === 'button' && fld('Button label', <input value={label} onChange={e => setLabel(e.target.value)} style={{ width:'100%' }} />)}

        {/* Image */}
        {wt === 'image' && (<>
          <div style={{ marginBottom: 12 }}>
            <label htmlFor="image-url-input" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
              {L("Image URL")}
            </label>
            <input id="image-url-input" value={imageUrl} onChange={e => setImageUrl(e.target.value)} style={{ width:'100%' }} placeholder="https://…" /> {/* // i18n-ok: a URL / code sample */}
          </div>
          <div style={{ marginBottom: 12 }}>
            {/* Distinct from the Appearance group's "Widget description" control --
                this one is the <img> element's own alt attribute (cfg.alt), not the
                widget's aria-label (cfg.alt_text). Both are visible on an image
                widget at once, so the labels must say what each actually does. */}
            <label htmlFor="image-alt-input" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
              {L("Image alt text")}
            </label>
            <input id="image-alt-input" value={imageAlt} onChange={e => setImageAlt(e.target.value)} style={{ width:'100%' }} />
          </div>
          <div style={{ marginBottom: 12 }}>
            <label htmlFor="image-fit-select" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
              {L("Fit")}
            </label>
            <select id="image-fit-select" value={imageFit} onChange={e => setImageFit(e.target.value)} style={{ width:'100%' }}>
              <option value="contain">{L("Contain")}</option>
              <option value="cover">{L("Cover")}</option>
              <option value="fill">{L("Fill")}</option>
            </select>
          </div>
        </>)}

        {wt === 'web_content' && (
          <div style={{ marginBottom: 12 }}>
            <label htmlFor="web-url-input" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
              {L("Web page URL")}
            </label>
            <input id="web-url-input" value={webUrl} onChange={e => setWebUrl(e.target.value)} style={{ width:'100%' }} placeholder="https://…" /> {/* // i18n-ok: a URL / code sample */}
            <div style={{ fontSize: 11, color:'var(--muted)', marginTop:4 }}>
              {L("Embedded in a sandboxed frame. Only http(s) URLs load; some sites block being framed.")}
            </div>
          </div>
        )}

        {wt === 'custom_visual' && (
          <div style={{ marginBottom: 12 }}>
            <label htmlFor="custom-url-input" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
              {L("Visualisation URL")}
            </label>
            <input id="custom-url-input" value={customUrl} onChange={e => setCustomUrl(e.target.value)} style={{ width:'100%' }} placeholder="https://…" /> {/* // i18n-ok: a URL / code sample */}
            <div style={{ fontSize: 11, color:'var(--muted)', marginTop:4 }}>
              {L("A sandboxed page that receives this widget's data via")} <code>postMessage</code> {/* // i18n-ok: a URL / code sample */}
              (<code>{'{ type: "datalytics:data", version: 1, data, context }'}</code>{L("). Bind a dimension/measure below to choose the data. Build one with the SDK,")} <code>/sdk/datalytics-visual-1.js</code>; <code>/sdk/example-bars.html</code> {L("is a working example.")} {/* // i18n-ok: a URL / code sample */}
            </div>
          </div>
        )}

        {/* Style of the object itself. A page can carry a background image;
            an object that draws no panel lets it through. */}
        <div style={{ marginBottom: 12 }}>
          <label style={{ display:'flex', alignItems:'center', gap:6, fontSize:11 }}>
            <input type="checkbox" checked={transparent}
              onChange={e => setTransparent(e.target.checked)} style={{ margin:0 }} />
            {L("Transparent background")}
          </label>
          <div style={{ fontSize: 10.5, color:'var(--muted)', marginTop:3 }}>
            {L("No panel and no border, so the page's background image shows through.")}
          </div>
        </div>

        {wt === 'donut' && (
          <div style={{ marginBottom: 12 }}>
            <label style={{ display:'flex', alignItems:'center', gap:6, fontSize:11 }}>
              <input type="checkbox" checked={donutTotal}
                onChange={e => setDonutTotal(e.target.checked)} style={{ margin:0 }} />
              {L("Total in the centre")}
            </label>
            {donutTotal && (
              <div style={{ marginTop: 6 }}>
                <label htmlFor="donut-total-label" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                  {L("Caption under the total")}
                </label>
                <input id="donut-total-label" value={donutTotalLabel}
                  onChange={e => setDonutTotalLabel(e.target.value)}
                  placeholder={L("defaults to the measure's name")} style={{ width:'100%' }} />
              </div>
            )}
          </div>
        )}

        {wt === 'script' && (
          <div style={{ marginBottom: 12 }}>
            <label htmlFor="script-code" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
              {'Python' /* // i18n-ok: a language name */}
            </label>
            <textarea id="script-code" value={scriptCode} rows={10}
              onChange={e => setScriptCode(e.target.value)}
              spellCheck={false}
              placeholder={"result = df.groupby('region', as_index=False)['revenue'].sum()"} // i18n-ok: a code sample
              style={{ width:'100%', fontFamily:'var(--mono)', fontSize:11.5,
                boxSizing:'border-box', resize:'vertical' }} />
            <div style={{ fontSize: 11, color:'var(--muted)', marginTop:4 }}>
              {L("Runs on the server over this widget's own filtered, row- and column-secured frame, which arrives as")} <code>df</code>{L(". Assign what the tile should show to")} <code>result</code> {L("— a DataFrame, a Series or a single number.")} <code>print()</code> {L("output is shown under the table.")} {/* // i18n-ok: a URL / code sample */}
            </div>
            <div style={{ fontSize: 11, color:'var(--muted)', marginTop:4 }}>
              {L("Only an organisation admin can save a script tile: this is code running on the server, in a separate process with no access to the application's credentials, but with whatever access the server itself has.")}
            </div>
          </div>
        )}

        {/* Shape */}
        {wt === 'shape' && (<>
          <label htmlFor="shape-kind-select" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
            {L("Shape")}
          </label>
          <div style={{ marginBottom: 12 }}>
            <select id="shape-kind-select" value={shapeKind} onChange={e => setShapeKind(e.target.value)} style={{ width:'100%' }}>
              <option value="rectangle">{L("Rectangle")}</option>
              <option value="rounded">{L("Rounded rectangle")}</option>
              <option value="circle">{L("Circle / Oval")}</option>
              <option value="line">{L("Line")}</option>
            </select>
          </div>
          <div style={{ display:'flex', gap:8, marginBottom:12 }}>
            <label style={{ display:'flex', flexDirection:'column', gap:2 }}>
              <span style={{ fontSize: 10.5, color:'var(--muted)' }}>{L("Fill")}</span>
              <input type="color" value={shapeFill} onChange={e => setShapeFill(e.target.value)}
                style={{ width:36, height:26, padding:2, border:'1px solid var(--border)', borderRadius:4, cursor:'pointer', background:'var(--surface)' }} />
            </label>
            <label style={{ display:'flex', flexDirection:'column', gap:2 }}>
              <span style={{ fontSize: 10.5, color:'var(--muted)' }}>{L("Border")}</span>
              <input type="color" value={shapeStroke} onChange={e => setShapeStroke(e.target.value)}
                style={{ width:36, height:26, padding:2, border:'1px solid var(--border)', borderRadius:4, cursor:'pointer', background:'var(--surface)' }} />
            </label>
          </div>
        </>)}

        {wt === 'container' && (
          <div style={{ marginBottom: 12 }}>
            <label htmlFor="container-mode-select" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
              {L("Container style")}
            </label>
            <select id="container-mode-select" value={containerMode} onChange={e => setContainerMode(e.target.value)} style={{ width:'100%' }}>
              <option value="group">{L("Group (fixed layout)")}</option>
              <option value="tabs">{L("Tabs (one child at a time)")}</option>
              <option value="scroll">{L("Scrolling")}</option>
              <option value="prompt">{L("Collapsible")}</option>
              <option value="precision">{L("Precision (free positioning, overlapping)")}</option>
            </select>
            {containerMode === 'precision' && (
              <div style={{ marginTop: 8 }}>
                <label htmlFor="container-background" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                  {L("Background image")}
                </label>
                <input id="container-background" value={containerBackground}
                  onChange={e => setContainerBackground(e.target.value)}
                  placeholder={L("https://… floorplan or schematic")}
                  style={{ width:'100%' }} />
                <div style={{ fontSize: 10.5, color:'var(--muted)', marginTop:3 }}>
                  {L("Widgets are placed freely over it and may overlap. Use each widget's Layer to decide what sits in front.")}
                </div>
              </div>
            )}
          </div>
        )}

        {wt !== 'container' && (pages ?? []).length > 0 && (() => {
          const page = (pages ?? []).find(p => p.widgets?.some(w => w.id === widget.id))
          const containers = (page?.widgets ?? []).filter(w => w.widget_type === 'container' && w.id !== widget.id)
          if (containers.length === 0) return null
          return (
            <div style={{ marginBottom: 12 }}>
              <label htmlFor="container-parent-select" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                {L("Place inside container")}
              </label>
              <select id="container-parent-select" value={containerId} onChange={e => setContainerId(e.target.value)} style={{ width:'100%' }}>
                <option value="">{L("— on the page —")}</option>
                {containers.map(c => <option key={c.id} value={c.id}>{c.title || `Container ${c.id}`}</option>)}
              </select>
              {/* Stacking only means something where widgets can overlap, so
                  the control appears only for a precision parent rather than
                  offering a setting that silently does nothing. */}
              {(() => {
                const parent = containers.find(c => String(c.id) === String(containerId))
                const precise = ((parent?.config as { container_mode?: string })
                  ?.container_mode) === 'precision'
                if (!precise) return null
                return (
                  <div style={{ marginTop: 8 }}>
                    <label htmlFor="widget-layer" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                      {L("Layer")}
                    </label>
                    <input id="widget-layer" type="number" value={layer}
                      onChange={e => setLayer(e.target.value)}
                      placeholder="0" style={{ width:'100%' }} />
                    <div style={{ fontSize: 10.5, color:'var(--muted)', marginTop:3 }}>
                      {L("Higher sits in front. Leave empty for the default.")}
                    </div>
                  </div>
                )
              })()}
            </div>
          )
        })()}

        {wt === 'slicer' && (
          <div style={{ marginBottom: 12 }}>
            <label htmlFor="slicer-mode-select" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
              {L("Control type")}
            </label>
            <select id="slicer-mode-select" value={slicerMode} onChange={e => setSlicerMode(e.target.value)} style={{ width:'100%' }}>
              <option value="auto">{L("Auto (by value count)")}</option>
              <option value="buttons">{L("Button bar")}</option>
              <option value="list">{L("Checkbox list")}</option>
              <option value="dropdown">{L("Drop-down (multi)")}</option>
              <option value="search">{L("Searchable list")}</option>
              {/* For a column whose value list is useless — Customer ID with
                  hundreds of thousands of values. The server returns no values
                  for this mode at all, which is the cost being avoided. */}
              <option value="text">{L("Text input (type a value)")}</option>
              {/* A number column as from–to bounds: the server sends its min
                  and max, never the value list. */}
              <option value="range">{L("Number range (from – to)")}</option>
            </select>
            <span style={{ fontSize: 11, color:'var(--muted)' }}>{L("Auto picks by how many values there are: buttons under 5, a list up to 10, a searchable list beyond. A number column with more than 20 values gets a from – to range.")}</span>
          </div>
        )}

        </div>
        )}

        {/* Button action config — relocated (Task B1) from a flat always-visible block
            into its own named group, open by default for buttons since it's the whole
            reason to configure one. Same fields, same state keys as before. */}
        {wt === 'button' && (
          <ExpandableGroup id="actions" title="Actions" defaultOpen // i18n-ok: ExpandableGroup translates its title
            searchTerms={ACTIONS_SEARCH_TERMS} {...groupFilterProps('Actions', ACTIONS_SEARCH_TERMS)}>
            <div style={{ marginBottom: 12 }}>
              <label htmlFor="button-action-select" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                {L("Button action")}
              </label>
              <select id="button-action-select" value={action} onChange={e => setAction(e.target.value)} style={{ width:'100%' }}>
                <option value="">{L("— none —")}</option>
                <option value="navigate">{L("Navigate to page")}</option>
                <option value="bookmark">{L("Apply bookmark")}</option>
                <option value="url">{L("Open external URL")}</option>
                <option value="report">{L("Go to another report")}</option>
                <option value="set_param">{L("Set a parameter")}</option>
              </select>
            </div>

            {action === 'navigate' && (
              <div style={{ marginBottom: 12 }}>
                <label htmlFor="button-action-page-select" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                  {L("Target page")}
                </label>
                <select id="button-action-page-select" value={actionPageId} onChange={e => setActionPageId(e.target.value)} style={{ width:'100%' }}>
                  <option value="">{L("— none —")}</option>
                  {(pages ?? []).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
                {actionPageId && (
                  <label style={{ display:'flex', alignItems:'center', gap:6, fontSize:11, marginTop:6 }}
                    title={L("The reader arrives on the target page filtered the way they left this one")}>
                    <input type="checkbox" checked={carryFilters} onChange={e => setCarryFilters(e.target.checked)} />
                    {L("Carry the reader's selections to that page")}
                  </label>
                )}
              </div>
            )}

            {action === 'url' && (
              <div style={{ marginBottom: 12 }}>
                <label htmlFor="button-action-url-input" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                  {L("Target URL")}
                </label>
                <input id="button-action-url-input" value={actionUrl} onChange={e => setActionUrl(e.target.value)}
                  placeholder="https://…" style={{ width:'100%' }} /> {/* // i18n-ok: a URL / code sample */}
                <span style={{ fontSize: 11, color:'var(--muted)' }}>{L("Opens in a new tab. Only http(s) links are allowed.")}</span>
              </div>
            )}

            {action === 'report' && (
              <div style={{ marginBottom: 12 }}>
                <label htmlFor="button-action-report-input" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                  {L("Target report ID")}
                </label>
                <input id="button-action-report-input" type="number" min={1} value={actionReportId}
                  onChange={e => setActionReportId(e.target.value)} style={{ width:'100%' }} placeholder="e.g. 12" />
                <span style={{ fontSize: 11, color:'var(--muted)' }}>{L("The number in the report's URL: /reports/12. Viewers keep their own permissions on the target.")}</span>
              </div>
            )}

            {action === 'set_param' && (
              <div style={{ marginBottom: 12 }}>
                <label htmlFor="button-action-param-name" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                  {L("Parameter name")}
                </label>
                <input id="button-action-param-name" value={actionParamName}
                  onChange={e => setActionParamName(e.target.value)} style={{ width:'100%' }} placeholder={L("e.g. threshold")} />
                <label htmlFor="button-action-param-value" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', margin:'8px 0 4px' }}>
                  {L("Value to set")}
                </label>
                <input id="button-action-param-value" value={actionParamValue}
                  onChange={e => setActionParamValue(e.target.value)} style={{ width:'100%' }} placeholder="e.g. 100" />
                <span style={{ fontSize: 11, color:'var(--muted)' }}>{L("Clicking the button sets this report parameter for the viewer, refreshing every widget that uses it.")}</span>
              </div>
            )}

            {action === 'bookmark' && (
              <div style={{ marginBottom: 12 }}>
                <label htmlFor="button-action-bookmark-select" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                  {L("Target bookmark")}
                </label>
                <select id="button-action-bookmark-select" value={actionBookmarkId} onChange={e => setActionBookmarkId(e.target.value)} style={{ width:'100%' }}>
                  <option value="">{L("— none —")}</option>
                  {(bookmarks ?? []).map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
                </select>
              </div>
            )}
          </ExpandableGroup>
        )}

        {wt !== 'text' && wt !== 'button' && wt !== 'image' && wt !== 'shape' && (<>
          <ExpandableGroup id="roles" title="Fields" defaultOpen // i18n-ok: ExpandableGroup translates its title
            searchTerms={FIELDS_SEARCH_TERMS} {...groupFilterProps('Fields', FIELDS_SEARCH_TERMS)}>
          {dataRolesPane}
          {/* A model's own options (event level, depth, which models to compare)
              sit with its roles: together they ARE the model specification. */}
          {isModel && (
            <ModelSettings widget={widget} pages={pages} value={modelOpts} onChange={setModelOpts}
              datasetId={Number(datasetId) || primaryDatasetId || null} />
          )}
          </ExpandableGroup>

          {!isModel && (<>
          <ExpandableGroup id="data" title="Data & aggregation" defaultOpen // i18n-ok: ExpandableGroup translates its title
            searchTerms={DATA_SEARCH_TERMS} {...groupFilterProps('Data & aggregation', DATA_SEARCH_TERMS)}>
          {wt === 'bar' && (
            <div style={{ marginBottom: 12 }}>
              <label htmlFor="bar-mode-select" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                {L("Bar layout")}
              </label>
              <select id="bar-mode-select" value={barMode} onChange={e => setBarMode(e.target.value)} style={{ width:'100%' }}>
                <option value="clustered">{L("Clustered")}</option>
                <option value="stacked">{L("Stacked")}</option>
                <option value="stacked100">{L("100% Stacked")}</option>
              </select>
            </div>
          )}


          {/* ── Hierarchy: tree / sunburst / icicle / dendrogram / org ──────
              These five shipped in the palette with NO options block, so every
              user-created one failed with "Choose the columns that form the
              hierarchy" -- advice the UI gave no way to follow. The shaper has
              two mutually exclusive modes and picks parent-child whenever both
              id_col and parent_col are set, so the toggle must CLEAR the other
              mode's keys rather than leaving them behind. */}
          {/* Which shapes the map draws. Beside the fields it colours, not
              in an admin page: an author finds out they need this the moment
              their choropleth comes back blank. */}
          {BOUNDARY_SET_WIDGETS.has(wt) && (
            <BoundarySetPicker value={boundarySetId} onChange={setBoundarySetId}
              inheritedName={inheritedBoundaryName} />
          )}
          {wt === 'map_choropleth' && roleValues.category && (
            <Suspense fallback={(Number(datasetId) || primaryDatasetId)
              ? <GeoMatchStatus>{L('Checking {column} against the map…', { column: roleValues.category })}</GeoMatchStatus> : null}>
              <GeoMatchLine datasetId={Number(datasetId) || primaryDatasetId || null} column={roleValues.category}
                setId={boundarySetId ? Number(boundarySetId) : (geography?.[roleValues.category] ?? null)} />
            </Suspense>
          )}

          {/* Pins live on the widget's config, so they travel with the report
              to a shared link or an embed exactly as every other setting does.
              They are annotations rather than data, and the renderer keeps them
              out of cross-filtering for that reason. */}
          {wt === 'custom_graph' && (
            <GraphLayersEditor value={graphLayers} columns={effectiveCols}
              onChange={setGraphLayers} />
          )}

          {PIN_WIDGETS.has(wt) && (
            <MapPinsEditor value={pins} onChange={setPins} />
          )}

          {wt === 'map_layers' && (
            <MapLayersEditor value={mapLayers} onChange={setMapLayers} columns={effectiveCols} />
          )}

          {HIERARCHY_WIDGETS.includes(wt as typeof HIERARCHY_WIDGETS[number]) && (
            <div style={{ marginBottom: 12 }}>
              <label style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', marginBottom:4 }}>
                {L("Hierarchy source")}
              </label>
              <div style={{ display:'flex', gap:12, marginBottom:8, fontSize:12 }}>
                <label style={{ display:'flex', alignItems:'center', gap:4, cursor:'pointer' }}>
                  <input type="radio" name="hier-mode" checked={hierMode === 'levels'}
                    onChange={() => setHierMode('levels')} />
                  {L("Level columns")}
                </label>
                <label style={{ display:'flex', alignItems:'center', gap:4, cursor:'pointer' }}>
                  <input type="radio" name="hier-mode" checked={hierMode === 'parent_child'}
                    onChange={() => setHierMode('parent_child')} />
                  {L("Parent-child")}
                </label>
              </div>

              {hierMode === 'levels' ? (
                <>
                  <label style={{ display:'block', fontSize: 11, color:'var(--muted)', marginBottom:3 }}>
                    {L('Levels — click in order, outer first (max {n})', { n: HIER_MAX_DEPTH })}
                  </label>
                  <div style={{ maxHeight:130, overflowY:'auto', display:'flex', flexDirection:'column',
                                gap:3, background:'var(--bg)', padding:6, borderRadius:4 }}>
                    {effectiveCols.map(c => {
                      const idx = hierLevels.indexOf(c.name)
                      const atCap = idx === -1 && hierLevels.length >= HIER_MAX_DEPTH
                      return (
                        <label key={c.name} style={{ display:'flex', alignItems:'center', gap:6,
                                                     fontSize:12, cursor: atCap ? 'not-allowed' : 'pointer',
                                                     opacity: atCap ? 0.45 : 1 }}>
                          <input type="checkbox" checked={idx !== -1} disabled={atCap} title={atCap ? L('This role is full: remove a field to add another') : undefined}
                            aria-label={L('Level {name}', { name: c.name })}
                            onChange={() => setHierLevels(prev =>
                              prev.includes(c.name)
                                ? prev.filter(x => x !== c.name)
                                : [...prev, c.name])} />
                          <span style={{ color: idx !== -1 ? 'var(--text)' : 'var(--muted)' }}>{c.name}</span>
                          {idx !== -1 && (
                            <span style={{ marginInlineStart:'auto', fontSize: 10.5, color:'var(--accent)' }}>
                              #{idx + 1}
                            </span>
                          )}
                        </label>
                      )
                    })}
                  </div>
                </>
              ) : (
                <div style={{ display:'flex', flexDirection:'column', gap:6 }}>
                  <div>
                    <label htmlFor="hier-id" style={{ display:'block', fontSize: 11, color:'var(--muted)' }}>
                      {L("ID column")}
                    </label>
                    <select id="hier-id" value={hierIdCol} onChange={e => setHierIdCol(e.target.value)}
                      style={{ width:'100%' }}>
                      <option value="">{L("— choose —")}</option>
                      {effectiveCols.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
                    </select>
                  </div>
                  <div>
                    <label htmlFor="hier-parent" style={{ display:'block', fontSize: 11, color:'var(--muted)' }}>
                      {L("Parent column")}
                    </label>
                    <select id="hier-parent" value={hierParentCol}
                      onChange={e => setHierParentCol(e.target.value)} style={{ width:'100%' }}>
                      <option value="">{L("— choose —")}</option>
                      {effectiveCols.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
                    </select>
                  </div>
                  <div>
                    <label htmlFor="hier-label" style={{ display:'block', fontSize: 11, color:'var(--muted)' }}>
                      {L("Label column (optional)")}
                    </label>
                    <select id="hier-label" value={hierLabelCol}
                      onChange={e => setHierLabelCol(e.target.value)} style={{ width:'100%' }}>
                      <option value="">{L("— use the ID —")}</option>
                      {effectiveCols.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
                    </select>
                  </div>
                  <div style={{ fontSize: 11, color:'var(--muted)' }}>
                    {L("A row whose parent is missing becomes a root, so a hierarchy you can only partly see still renders.")}
                  </div>
                </div>
              )}

              {PARTITION_WIDGETS.includes(wt) && (
                <div style={{ fontSize: 11, color:'var(--muted)', marginTop:6 }}>
                  {L('This chart draws each value as a share of its parent, so only adding-up aggregations are offered.')}
                </div>
              )}
            </div>
          )}

          {/* ── Small multiples ─────────────────────────────────────────────
              Without facet_by the shaper degrades to ONE panel, so the widget
              silently became an ordinary chart with no indication. */}
          {wt === 'small_multiples' && (
            <div style={{ marginBottom: 12, display:'flex', flexDirection:'column', gap:6 }}>
              <div>
                <label htmlFor="facet-by" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)' }}>
                  {L("Facet by")}
                </label>
                <select id="facet-by" value={facetBy} onChange={e => setFacetBy(e.target.value)}
                  style={{ width:'100%' }}>
                  <option value="">{L("— choose a column —")}</option>
                  {effectiveCols.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
                </select>
              </div>
              <div>
                <label htmlFor="facet-inner" style={{ display:'block', fontSize: 11, color:'var(--muted)' }}>
                  {L("Panel chart type")}
                </label>
                <select id="facet-inner" value={facetInner} onChange={e => setFacetInner(e.target.value)}
                  style={{ width:'100%' }}>
                  {FACETABLE_WIDGETS.map(w => <option key={w} value={w}>{w}</option>)}
                </select>
              </div>
              <div>
                <label htmlFor="facet-limit" style={{ display:'block', fontSize: 11, color:'var(--muted)' }}>
                  {L('Max panels (1–{n})', { n: FACET_MAX_PANELS })}
                </label>
                <input id="facet-limit" type="number" min={1} max={FACET_MAX_PANELS}
                  value={facetLimit} onChange={e => setFacetLimit(e.target.value)}
                  style={{ width:'100%' }} />
              </div>
              <div style={{ fontSize: 11, color:'var(--muted)' }}>
                {L("Every panel shares one scale — comparing them is the point.")}
              </div>
            </div>
          )}

          {wt === 'forecast' && (
            <div style={{ marginBottom: 12 }}>
              <label htmlFor="forecast-periods" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)' }}>
                {L('Periods ahead ({min}–{max})', { min: FORECAST_MIN_PERIODS, max: FORECAST_MAX_PERIODS })}
              </label>
              <input id="forecast-periods" type="number"
                min={FORECAST_MIN_PERIODS} max={FORECAST_MAX_PERIODS}
                value={forecastPeriods} onChange={e => setForecastPeriods(e.target.value)}
                style={{ width:'100%' }} />
            </div>
          )}

          {/* All four centralities are computed for every network; this picks
              which one the node sizes mean. */}
          {wt === 'network' && (
            <div style={{ marginBottom: 12 }}>
              <label htmlFor="centrality-metric" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                {L("Node size")}
              </label>
              <select id="centrality-metric" value={centralityMetric}
                onChange={e => setCentralityMetric(e.target.value)} style={{ width:'100%' }}>
                <option value="degree">{L("Degree — how many it connects to")}</option>
                <option value="closeness">{L("Closeness — how near it is to everything")}</option>
                <option value="betweenness">{L("Betweenness — how much traffic must pass through it")}</option>
                <option value="reach">{L("Reach — how much of the network it can get to")}</option>
              </select>
            </div>
          )}

          {wt === 'forecast' && (
            <div style={{ marginBottom: 12 }}>
              <label htmlFor="forecast-target" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                {L("Reach target")}
              </label>
              <input id="forecast-target" type="number" value={forecastTarget}
                onChange={e => setForecastTarget(e.target.value)}
                placeholder="e.g. 500000" style={{ width:'100%' }} />
              <div style={{ fontSize: 10.5, color:'var(--muted)', marginTop:3 }}>
                {L("Answers when the projection reaches this value, with the range its confidence interval allows. Leave empty for no target.")}
              </div>
            </div>
          )}

          {wt === 'forecast' && (
            <div style={{ marginBottom: 12 }}>
              <label htmlFor="forecast-method-select" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                {L("Forecast method")}
              </label>
              <select id="forecast-method-select" value={forecastMethod} onChange={e => setForecastMethod(e.target.value)} style={{ width:'100%' }}>
                <option value="ets">{L("AutoETS (StatsForecast)")}</option>
                <option value="simple">{L("Simple smoothing")}</option>
              </select>
            </div>
          )}

          {(wt === 'bar' || wt === 'line') && (
            <div style={{ marginBottom: 12, border: '1px solid var(--border)', borderRadius: 6, padding: 8 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 8 }}>
                {L("Analytics")}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                <input id="average-line-toggle" type="checkbox" checked={showAverageLine} onChange={e => setShowAverageLine(e.target.checked)} />
                <label htmlFor="average-line-toggle" style={{ fontSize: 12, cursor: 'pointer' }}>{L("Show average line")}</label>
              </div>
              <div style={{ display: 'flex', gap: 6, alignItems: 'flex-end' }}>
                <label style={{ display: 'flex', flexDirection: 'column', gap: 2, flex: 1 }}>
                  <span style={{ fontSize: 10.5, color: 'var(--muted)' }}>{L("Reference line value")}</span>
                  <input id="reference-line-value" type="number" value={referenceValue} onChange={e => setReferenceValue(e.target.value)} style={{ width: '100%' }} placeholder="e.g. 100" aria-label={L("Reference line value")} />
                </label>
                <label style={{ display: 'flex', flexDirection: 'column', gap: 2, flex: 1 }}>
                  <span style={{ fontSize: 10.5, color: 'var(--muted)' }}>{L("Reference line label")}</span>
                  <input id="reference-line-label" value={referenceLabel} onChange={e => setReferenceLabel(e.target.value)} style={{ width: '100%' }} placeholder={L("Target")} aria-label={L("Reference line label")} />
                </label>
                <label style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                  <span style={{ fontSize: 10.5, color: 'var(--muted)' }}>{L("Color")}</span>
                  <input type="color" value={referenceColor} onChange={e => setReferenceColor(e.target.value)}
                    style={{ width: 36, height: 26, padding: 2, border: '1px solid var(--border)', borderRadius: 4, cursor: 'pointer', background: 'var(--surface)' }} />
                </label>
              </div>
            </div>
          )}

          {/* Aggregation — grouped select */}
          <div style={{ marginBottom:12 }}>
            <label htmlFor="cfg-aggregation" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
              {L("Aggregation")}
            </label>
            <select id="cfg-aggregation" value={agg} onChange={e => setAgg(e.target.value)} style={{ width:'100%' }}>
              {Object.entries(aggGroups).map(([group, items]) => (
                <optgroup key={group} label={`── ${L(group)} ──`}>
                  {items
                    // A sunburst/icicle wedge is a share of its parent, so an
                    // aggregation that does not add up would make the geometry
                    // lie. Filtering here means the user never picks one the
                    // shaper will refuse.
                    .filter(a => !PARTITION_WIDGETS.includes(wt)
                                 || ADDITIVE_AGGREGATIONS.includes(a.value))
                    // "Percentage %" only where the chart computes shares; a
                    // stored one stays visible so it is not silently replaced.
                    .filter(a => aggregationOffered(wt, a.value) || a.value === agg)
                    .map(a => <option key={a.value} value={a.value}>{L(a.label)}</option>)}
                </optgroup>
              ))}
            </select>
            <div style={{ fontSize: 11, color:'var(--muted)', marginTop:3 }}>
              {roleValues.measure
                ? L('{agg} of {measure}', { agg: L(AGGREGATIONS.find(a => a.value === agg)?.label ?? agg), measure: roleValues.measure })
                : L('{agg} (row count)', { agg: L(AGGREGATIONS.find(a => a.value === agg)?.label ?? agg) })}
            </div>
            {warning && (
              <div role="note" style={{ fontSize: 11, color:'var(--accent)', marginTop:4 }}>
                {warning}
              </div>
            )}
            {(() => {
              // The semantic veto, at the moment of choice: arithmetic over a
              // coordinate, an identifier or a year returns a confident number
              // that means nothing. Say so, and offer the aggregation that does.
              const sem = semanticAggregationWarning(roleValues.measure, agg)
              const kind = nonAdditiveKind(roleValues.measure)
              if (!sem || !kind) return null
              const fix = SAFE_AGGREGATION[kind]
              return (
                <div role="alert" data-testid="semantic-aggregation-warning"
                  style={{ fontSize:11, color:'var(--danger, #c0392b)', marginTop:6, lineHeight:1.4 }}>
                  {sem}{' '}
                  <button type="button" className="btn btn-ghost btn-sm" style={{ fontSize:11, padding:'0 6px' }}
                    onClick={() => setAgg(fix.value)}>
                    {L('Use {name}', { name: fix.label })}
                  </button>
                </div>
              )
            })()}
          </div>

          {/* Second aggregation — the reason a chart has two axes is usually
              that its two numbers are aggregated differently: encounters
              COUNTED against wait AVERAGED. Offered only where there is a
              second measure to aggregate, and blank means "same as above". */}
          {DUAL_MEASURE_WIDGETS.includes(wt) && roleValues.measure2 && (
            <div style={{ marginBottom:12 }}>
              <label htmlFor="cfg-aggregation2" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                {L("Aggregation · second measure")}
              </label>
              <select id="cfg-aggregation2" value={agg2} onChange={e => setAgg2(e.target.value)} style={{ width:'100%' }}>
                <option value="">{L("Same as above")}</option>
                {Object.entries(aggGroups).map(([group, items]) => (
                  <optgroup key={group} label={`── ${L(group)} ──`}>
                    {items.filter(a => aggregationOffered(wt, a.value) || a.value === agg2)
                      .map(a => <option key={a.value} value={a.value}>{L(a.label)}</option>)}
                  </optgroup>
                ))}
              </select>
              <div style={{ fontSize: 11, color:'var(--muted)', marginTop:3 }}>
                {L(AGGREGATIONS.find(a => a.value === (agg2 || agg))?.label ?? (agg2 || agg))}
                {' ' + L('of {measure}', { measure: roleValues.measure2 })}
              </div>
            </div>
          )}

          {/* Running metric */}
          {(wt === 'bar' || wt === 'line' || wt === 'list') && !dimension2 && fld('Running metric',
            sel(running, setRunning, RUNNING_OPTIONS)
          )}

          {/* Column selector for table/list */}
          {(wt === 'table' || wt === 'crosstab' || wt === 'list') && (
            <div style={{ marginBottom:12 }}>
              {/* A group of checkboxes, not a single control, so this is a group label
                  rather than a <label> -- a <label> pointing at nothing gives a screen
                  reader no association and is invalid besides. */}
              <div id="cfg-visible-columns-label" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                {L("Visible columns")}
              </div>
              <div role="group" aria-labelledby="cfg-visible-columns-label" style={{ maxHeight:130, overflowY:'auto', display:'flex', flexDirection:'column', gap:3, background:'var(--surface2)', border:'1px solid var(--border)', borderRadius:6, padding:'6px 8px' }}>
                {effectiveCols.map(c => (
                  <label key={c.name} style={{ display:'flex', alignItems:'center', gap:6, fontSize:12, cursor:'pointer' }}>
                    <input type="checkbox" checked={tableCols.includes(c.name)}
                      onChange={e => setTableCols(p => e.target.checked ? [...p, c.name] : p.filter(x => x !== c.name))} />
                    <span style={{ color: tableCols.includes(c.name) ? 'var(--text)' : 'var(--muted)' }}>{c.name}</span>
                    <span className={`badge badge-${c.dtype}`} style={{ marginInlineStart:'auto', padding:'1px 5px', fontSize: 10.5 }}>{c.dtype}</span>
                  </label>
                ))}
              </div>
            </div>
          )}
          </ExpandableGroup>
          </>)}

          {(LATTICE_WIDGETS as readonly string[]).includes(wt) && (
          <ExpandableGroup id="lattice" title="Lattice (small multiples)" // i18n-ok: ExpandableGroup translates its title
            searchTerms={LATTICE_SEARCH_TERMS} {...groupFilterProps('Lattice (small multiples)', LATTICE_SEARCH_TERMS)}>
            <p style={{ fontSize: 11, color:'var(--muted)', marginBottom:8 }}>
              {L("Repeat this chart once per value — a grid of panels on one shared axis, so panels compare honestly.")}
            </p>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8, marginBottom:8 }}>
              <label style={{ fontSize: 11, color:'var(--muted)' }}>{L("Rows")}
                <select aria-label={L("Lattice rows")} value={latticeRows} onChange={e => setLatticeRows(e.target.value)} style={{ width:'100%' }}>
                  <option value="">{L("— none —")}</option>
                  {colOptions.filter(o => o.value !== latticeCols).map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </label>
              <label style={{ fontSize: 11, color:'var(--muted)' }}>{L("Columns")}
                <select aria-label={L("Lattice columns")} value={latticeCols} onChange={e => setLatticeCols(e.target.value)} style={{ width:'100%' }}>
                  <option value="">{L("— none —")}</option>
                  {colOptions.filter(o => o.value !== latticeRows).map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </label>
            </div>
            {(latticeRows || latticeCols) && (
              <div style={{ fontSize: 11, color:'var(--muted)', marginBottom:6 }}>
                {L("Up to 8 rows × 8 columns (60 panels), the values with the most rows first; anything cut is named under the chart.")}
              </div>
            )}
          </ExpandableGroup>
          )}

          {(ANIMATION_WIDGETS as readonly string[]).includes(wt) && (
          <ExpandableGroup id="animation" title="Animation (play through)" // i18n-ok: ExpandableGroup translates its title
            searchTerms={ANIMATION_SEARCH_TERMS} {...groupFilterProps('Animation (play through)', ANIMATION_SEARCH_TERMS)}>
            <p style={{ fontSize: 11, color:'var(--muted)', marginBottom:8 }}>
              {L("Play this chart through an ordered field — a date, a year — one frame per value, on one fixed axis.")}
            </p>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8, marginBottom:8 }}>
              <label style={{ fontSize: 11, color:'var(--muted)' }}>{L("Play through")}
                <select aria-label={L("Animate by")} value={animateBy} onChange={e => setAnimateBy(e.target.value)} style={{ width:'100%' }}>
                  <option value="">{L("— off —")}</option>
                  {colOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </label>
              {animateBy && effectiveCols.find(c => c.name === animateBy)?.dtype === 'datetime' && (
                <label style={{ fontSize: 11, color:'var(--muted)' }}>{L("One frame per")}
                  <select aria-label={L("Animation step")} value={animateGran} onChange={e => setAnimateGran(e.target.value)} style={{ width:'100%' }}>
                    <option value="">{L("date")}</option>
                    {['week', 'month', 'quarter', 'year'].map(g => <option key={g} value={g}>{g}</option>)}
                  </select>
                </label>
              )}
            </div>
          </ExpandableGroup>
          )}

          <ExpandableGroup id="objfilters" title="Filters" // i18n-ok: ExpandableGroup translates its title
            searchTerms={FILTERS_SEARCH_TERMS} {...groupFilterProps('Filters', FILTERS_SEARCH_TERMS)}>
          <p style={{ fontSize: 11, color:'var(--muted)', marginBottom:8 }}>
            {L("This object's own row filters — applied before aggregation, on top of dataset filters and cross-filters.")}
          </p>
          {objFilters.map((f, i) => (
            <div key={i} style={{ display:'flex', gap:4, marginBottom:6, flexWrap:'wrap' }}>
              <select aria-label={L('Filter {n} column', { n: i + 1 })} value={f.column}
                onChange={e => setObjFilters(p => p.map((x, k) => k === i ? { ...x, column: e.target.value } : x))}
                style={{ fontSize:11, flex:1, minWidth:90 }}>
                <option value="">{L("— column —")}</option>
                {colOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
              <select aria-label={L('Filter {n} operator', { n: i + 1 })} value={f.op}
                onChange={e => {
                  const op = e.target.value
                  setObjFilters(p => p.map((x, k) => k !== i ? x : {
                    ...x, op,
                    value: op === 'relative' ? JSON.stringify(DEFAULT_SPEC) : (x.op === 'relative' ? '' : x.value) }))
                }}
                style={{ fontSize:11 }}>
                {['eq','neq','gt','gte','lt','lte','like','in'].map(o => <option key={o} value={o}>{o}</option>)}
                <option value="relative">{L("relative date")}</option>
              </select>
              {f.op === 'relative' ? (
                <RelativeDateEditor label={L('Filter {n}', { n: i + 1 })} value={parseSpec(f.value)}
                  onChange={spec => setObjFilters(p => p.map((x, k) => k === i ? { ...x, value: JSON.stringify(spec) } : x))} />
              ) : (
              <input aria-label={L('Filter {n} value', { n: i + 1 })} value={f.value}
                placeholder={f.op === 'in' ? 'a, b, c' : L('value')}
                onChange={e => setObjFilters(p => p.map((x, k) => k === i ? { ...x, value: e.target.value } : x))}
                style={{ fontSize:11, width:90 }} />
              )}
              <button aria-label={L('Remove filter {n}', { n: i + 1 })}
                onClick={() => setObjFilters(p => p.filter((_, k) => k !== i))}
                style={{ border:'none', background:'none', color:'var(--danger)', cursor:'pointer' }}>✕</button>
            </div>
          ))}
          <button className="btn" style={{ fontSize: 11, marginBottom:8 }}
            onClick={() => setObjFilters(p => [...p, { column: '', op: 'eq', value: '' }])}>{L("+ Add filter")}</button>
          </ExpandableGroup>

          {!isModel && (<>
          <ExpandableGroup id="sort" title="Sort & limit" // i18n-ok: ExpandableGroup translates its title
            searchTerms={SORT_SEARCH_TERMS} {...groupFilterProps('Sort & limit', SORT_SEARCH_TERMS)}>
          {/* Sort */}
          {sortOpts === 'all' && (
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8, marginBottom:8 }}>
            <div>
              <label htmlFor="cfg-sort-order" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>{L("Sort order")}</label>
              <select id="cfg-sort-order" value={sort} onChange={e => setSort(e.target.value)} style={{ width:'100%' }}>
                <option value="desc">{L("Descending")}</option>
                <option value="asc">{L("Ascending")}</option>
              </select>
            </div>
            <div>
              <label htmlFor="cfg-sort-by" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>{L("Sort by")}</label>
              <select id="cfg-sort-by" value={sortBy} onChange={e => setSortBy(e.target.value)} style={{ width:'100%' }}>
                <option value="">{L("Automatic")}</option>
                <option value="value">{L("By Value")}</option>
                <option value="name">{L("By Name")}</option>
              </select>
              {!sortBy && (
                <div style={{ fontSize: 11, color:'var(--muted)', marginTop:3 }}>
                  {dimension2 ? L('Rows in label order') : L('Dates in time order, everything else by value')}
                </div>
              )}
            </div>
          </div>
          )}
          {/* A grid (two dimensions) sorts its ROWS by their subtotal or their
              label; it has no per-row value of another column to sort by, so
              the control would save and do nothing (E08). */}
          {sortOpts === 'all' && !dimension2 && fld('Sort column (overrides sort by)',
            <select value={sortCol} onChange={e => setSortCol(e.target.value)} style={{ width:'100%' }}>
              <option value="">{L("— use sort by above —")}</option>
              {colOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          )}

          {(wt === 'table' || wt === 'list') && (
            <div style={{ marginBottom: 12 }}>
              <label style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                {L("Multi-column sort (priority order)")}
              </label>
              {sortKeys.map((k, i) => (
                <div key={i} style={{ display:'flex', gap:4, marginBottom:6, flexWrap:'wrap' }}>
                  <select aria-label={L('Sort key {n} column', { n: i + 1 })} value={k.col}
                    onChange={e => setSortKeys(p => p.map((x, j) => j === i ? { ...x, col: e.target.value } : x))}
                    style={{ fontSize:11, flex:1, minWidth:90 }}>
                    <option value="">{L("— column —")}</option>
                    {colOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                  <select aria-label={L('Sort key {n} direction', { n: i + 1 })} value={k.dir}
                    onChange={e => setSortKeys(p => p.map((x, j) => j === i ? { ...x, dir: e.target.value } : x))}
                    style={{ fontSize:11 }}>
                    <option value="asc">{L("Asc")}</option>
                    <option value="desc">{L("Desc")}</option>
                  </select>
                  <button aria-label={L('Remove sort key {n}', { n: i + 1 })}
                    onClick={() => setSortKeys(p => p.filter((_, j) => j !== i))}
                    style={{ border:'none', background:'none', color:'var(--danger)', cursor:'pointer' }}>✕</button>
                </div>
              ))}
              <button className="btn" style={{ fontSize: 11 }}
                onClick={() => setSortKeys(p => [...p, { col: '', dir: 'asc' }])}>{L("+ Add sort column")}</button>
              {sortKeys.filter(k => k.col).length > 0 && (
                <div style={{ fontSize: 11, color:'var(--muted)', marginTop:6 }}>
                  {L("Rows sort by the first column, ties broken by the next. Supersedes the single sort column above.")}
                </div>
              )}
            </div>
          )}

          {sortOpts !== 'none' && fld('Row limit',
            <input type="number" value={limit ?? ''} min={1} placeholder={L("All (full data)")}
              onChange={e => setLimit(e.target.value === '' ? null : Math.max(1, Math.round(Number(e.target.value))))}
              style={{ width:'100%' }} />
          )}

          {fld('Auto-reload (seconds)',
            <>
              <input type="number" value={autoReload} min={5} placeholder={L("off")}
                onChange={e => setAutoReload(e.target.value)}
                aria-label={L("Auto-reload seconds")} style={{ width:'100%' }} />
              <span style={{ fontSize: 11, color:'var(--muted)' }}>{L("Refetches this widget's data on the interval. Minimum 5s; blank turns it off.")}</span>
            </>
          )}

          {sortOpts === 'all' && fld('Custom order (comma-separated)',
            <input value={sortCustom} onChange={e => setSortCustom(e.target.value)} style={{ width:'100%' }}
              placeholder={L("e.g. Low, Medium, High")} aria-label={L("Custom category order")} />
          )}
          {sortOpts === 'all' && sortCustom.trim() !== '' && (
            <div style={{ fontSize: 11, color:'var(--muted)', marginTop:-8, marginBottom:12 }}>
              {L("Categories listed here come first, in this order; the rest follow. Overrides the sort above.")}
            </div>
          )}

          {sortOpts === 'all' && (
          <div style={{ marginBottom: 12 }}>
            <label htmlFor="cfg-having-op" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
              {L("Filter aggregated values")}
            </label>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8 }}>
              <select id="cfg-having-op" value={havingOp} onChange={e => setHavingOp(e.target.value)} style={{ width:'100%' }}>
                <option value="">{L("— no filter —")}</option>
                <option value="gt">{L("greater than")}</option>
                <option value="gte">{L("at least")}</option>
                <option value="lt">{L("less than")}</option>
                <option value="lte">{L("at most")}</option>
                <option value="eq">{L("equal to")}</option>
              </select>
              <input type="number" value={havingValue} onChange={e => setHavingValue(e.target.value)}
                aria-label={L("Aggregate filter value")} style={{ width:'100%' }} placeholder={L("value")} disabled={!havingOp} title={!havingOp ? L('Choose a condition first') : undefined} />
            </div>
            <span style={{ fontSize: 11, color:'var(--muted)' }}>{L("Applies to the aggregated value of each category — e.g. keep regions whose total exceeds 1000.")}</span>
          </div>
          )}

          {sortOpts === 'all' && fld('Quick calculation',
            <select value={quickCalc} onChange={e => setQuickCalc(e.target.value)} style={{ width:'100%' }} aria-label={L("Quick calculation")}>
              <option value="">{L("— none —")}</option>
              <option value="percent_of_total">{L("Percent of total")}</option>
              <option value="difference">{L("Difference from previous")}</option>
              <option value="percent_change">{L("Percent change from previous")}</option>
              <option value="rank">{L("Rank (1 = largest)")}</option>
            </select>
          )}

          {sortOpts === 'all' && (
          <div style={{ marginBottom: 12 }}>
            <label htmlFor="cfg-suppress" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
              {L("Suppress small groups")}
            </label>
            <input id="cfg-suppress" type="number" min={0} value={suppressBelow}
              onChange={e => setSuppressBelow(e.target.value)} style={{ width:'100%' }} placeholder={L("minimum rows per group (off)")} />
            <label style={{ display:'flex', alignItems:'center', gap:6, fontSize:11, marginTop:6, cursor:'pointer' }}>
              <input type="checkbox" checked={suppressComplement} onChange={e => setSuppressComplement(e.target.checked)}
                disabled={suppressBelow === '' || Number(suppressBelow) <= 0} title={suppressBelow === '' || Number(suppressBelow) <= 0 ? L('Set a minimum group size above first') : undefined} />
              {L("Also hide the smallest surviving group (blocks back-computation)")}
            </label>
            <span style={{ fontSize: 11, color:'var(--muted)' }}>{L("Hides any category aggregated from fewer rows than this — confidentiality suppression for small cells.")}</span>
          </div>
          )}

          {wt === 'histogram' && fld('Bins',
            <input type="number" value={bins} min={2} max={100} onChange={e => setBins(Number(e.target.value))} style={{ width:'100%' }} />
          )}

          {wt === 'needle' && fld('Baseline',
            <input type="number" value={baseline} onChange={e => setBaseline(Number(e.target.value))} style={{ width:'100%' }} />
          )}

          {wt === 'bubble' && fld('Fit Line',
            sel(fitLine, setFitLine, [
              { value: 'linear',    label: L("Linear") },
              { value: 'quadratic', label: L("Quadratic") },
              { value: 'cubic',     label: L("Cubic") },
              { value: 'best_fit',  label: L("Best Fit") },
            ], '— none —')
          )}

          {wt === 'gauge' && fld('Target value (fixed, optional)',
            <input type="number" value={targetValue} onChange={e => setTargetValue(e.target.value)} style={{ width:'100%' }} placeholder={L("leave blank to use Target column")} />
          )}
          {wt === 'bubble_change' && fld('Animation value',
            <>
              <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8, marginBottom:6 }}>
                <select aria-label={L("Animation value position")} value={animPos} onChange={e => setAnimPos(e.target.value)}>
                  <option value="none">{L("— hidden —")}</option>
                  {['top-left','top-center','top-right','middle-left','center','middle-right','bottom-left','bottom-center','bottom-right']
                    .map(p => <option key={p} value={p}>{p.replace('-', ' ')}</option>)}
                </select>
                <select aria-label={L("Frame order")} value={animOrder} onChange={e => setAnimOrder(e.target.value)}>
                  <option value="asc">{L("Order: ascending")}</option>
                  <option value="desc">{L("Order: descending")}</option>
                </select>
              </div>
              {animPos !== 'none' && (
                <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:8, alignItems:'center' }}>
                  <input type="number" aria-label={L("Animation value size")} min={10} max={120}
                    value={animSize} onChange={e => setAnimSize(e.target.value)} placeholder={L("size px")} />
                  <select aria-label={L("Animation value style")} value={animStyle} onChange={e => setAnimStyle(e.target.value)}>
                    <option value="bold">{L("Bold")}</option>
                    <option value="normal">{L("Normal")}</option>
                    <option value="italic">{L("Italic")}</option>
                  </select>
                  <input type="number" aria-label={L("Animation value opacity")} min={0} max={1} step={0.05}
                    value={animOpacity} onChange={e => setAnimOpacity(e.target.value)} placeholder={L("opacity")} />
                  <label style={{ fontSize:11, display:'flex', alignItems:'center', gap:4, gridColumn:'1 / -1' }}>
                    <input type="checkbox" checked={animBox} onChange={e => setAnimBox(e.target.checked)} />
                    {L("Contrast box behind the value")}
                  </label>
                </div>
              )}
            </>
          )}

          {wt === 'gauge' && fld('Gauge shape',
            sel(gaugeShape, setGaugeShape, [
              { value: 'arc', label: L("Arc (half donut)") },
              { value: 'speedometer', label: L("Speedometer (dial + needle)") },
              { value: 'bullet', label: L("Bullet (bar + target tick)") },
              { value: 'thermometer', label: L("Thermometer") },
              { value: 'progress', label: L("Progress bar") },
            ], 'Arc (half donut)')
          )}
          </ExpandableGroup>
          </>)}

          {/* Ranking: its own group, not a corner of Sort & limit. Selection
              is BY AGGREGATED VALUE, independent of the display sort -- that
              independence is the whole capability, and burying the controls
              under "Sort" taught authors the opposite. Gated per widget type:
              a shaper that ignores `rank` must not be offered the control
              (widgetCapabilities.ts -- a control wired to nothing is a
              defect, not a cosmetic). */}
          {supportsRanking(wt) && (
            <ExpandableGroup id="ranking" title="Ranking" // i18n-ok: ExpandableGroup translates its title
              searchTerms={RANKING_SEARCH_TERMS} {...groupFilterProps('Ranking', RANKING_SEARCH_TERMS)}>

          <div style={{ marginBottom: 12 }}>
            <label htmlFor="cfg-rank-mode" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
              {L("Rank")}
            </label>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8 }}>
              <select id="cfg-rank-mode" value={rankMode} onChange={e => setRankMode(e.target.value)} style={{ width:'100%' }}>
                <option value="">{L("— all values —")}</option>
                <option value="top">{L("Top N")}</option>
                <option value="bottom">{L("Bottom N")}</option>
              </select>
              <input type="text" value={rankN} onChange={e => setRankN(e.target.value)}
                aria-label={L("Rank count")} style={{ width:'100%' }} placeholder={L("N or @parameter")} disabled={!rankMode} title={!rankMode ? L('Choose Top or Bottom first') : undefined} />
            </div>
            <div style={{ display:'flex', gap:12, marginTop:4 }}>
              <label style={{ fontSize:11, display:'flex', alignItems:'center', gap:4 }}>
                <input type="checkbox" checked={rankPercent} onChange={e => setRankPercent(e.target.checked)} disabled={!rankMode} title={!rankMode ? L('Choose Top or Bottom first') : undefined} />
                {L("N is a percent of categories")}
              </label>
              <label style={{ fontSize:11, display:'flex', alignItems:'center', gap:4 }}>
                <input type="checkbox" checked={rankOther} onChange={e => setRankOther(e.target.checked)} disabled={!rankMode} title={!rankMode ? L('Choose Top or Bottom first') : undefined} />
                {L("Bucket the rest as “All Other”")}
              </label>
            </div>
            <span style={{ fontSize: 11, color:'var(--muted)' }}>{L("Selected by aggregated value, shown in the sort order above. Ties at the boundary are kept. “All Other” aggregates the excluded categories’ raw rows.")}</span>
          </div>
          </ExpandableGroup>
          )}

          {/* Formatting — only mounted when this widget type has at least one
              capability (widgetCapabilities.ts). Every control inside is further
              gated on the specific capability it writes, so a widget type never gets
              offered an option its renderer would silently ignore. */}
          {formatCaps.length > 0 && (
            <ExpandableGroup id="formatting" title="Formatting" defaultOpen={false} // i18n-ok: ExpandableGroup translates its title
              searchTerms={FORMATTING_SEARCH_TERMS} {...groupFilterProps('Formatting', FORMATTING_SEARCH_TERMS)}>
              {formatCaps.includes('axes') && (<>
                <div style={{ marginBottom: 12 }}>
                  <label htmlFor="format-x-axis-label" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                    {L("X axis label")}
                  </label>
                  <input id="format-x-axis-label" value={xAxisLabel} onChange={e => setXAxisLabel(e.target.value)} style={{ width:'100%' }} placeholder={L("(none)")} />
                </div>
                <div style={{ marginBottom: 12 }}>
                  <label htmlFor="format-y-axis-label" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                    {L("Y axis label")}
                  </label>
                  <input id="format-y-axis-label" value={yAxisLabel} onChange={e => setYAxisLabel(e.target.value)} style={{ width:'100%' }} placeholder={L("(none)")} />
                </div>
                {/* Only where a second axis exists. Offering it elsewhere would
                    be a control wired to nothing. */}
                {['dual_axis_bar', 'dual_axis_line', 'dual_axis_bar_line',
                  'dual_axis_time_series', 'comparative_time_series'].includes(wt) && (
                  <div style={{ marginBottom: 12 }}>
                    <label htmlFor="format-y2-axis-label" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                      {L("Right axis label")}
                    </label>
                    <input id="format-y2-axis-label" value={y2AxisLabel}
                      onChange={e => setY2AxisLabel(e.target.value)}
                      style={{ width:'100%' }} placeholder={L("(none)")} />
                  </div>
                )}
                <div style={{ display:'flex', gap:8, marginBottom:12 }}>
                  <div style={{ flex:1 }}>
                    <label htmlFor="format-tick-size" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                      {L("Tick size")}
                    </label>
                    <input id="format-tick-size" type="number" min={6} max={24} value={axisTickSize}
                      onChange={e => setAxisTickSize(e.target.value)} style={{ width:'100%' }} placeholder="10" />
                  </div>
                  <div>
                    <label htmlFor="format-tick-color" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                      {L("Tick colour")}
                    </label>
                    <input id="format-tick-color" type="color" value={axisTickColor || '#94a3b8'} onChange={e => setAxisTickColor(e.target.value)}
                      style={{ width:36, height:26, padding:2, border:'1px solid var(--border)', borderRadius:4, cursor:'pointer', background:'var(--surface)' }} />
                  </div>
                </div>
                {formatCaps.includes('xCategoryAxis') && (
                <div style={{ marginBottom: 12 }}>
                  <label htmlFor="format-x-axis-angle" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                    {L("Category label angle")}
                  </label>
                  {/* Automatic is the default and the right answer nearly always:
                      the axis draws its labels upright while they fit, tilts them
                      only as far as it must, and thins them out only when even
                      vertical text would collide. The explicit angles exist for the
                      author who wants one particular look -- the collision maths
                      still applies on top, so pinning 0 here cannot bring the
                      overprinting back. */}
                  <select id="format-x-axis-angle" value={xAxisAngle ?? ''}
                    onChange={e => setXAxisAngle(e.target.value === '' ? undefined : Number(e.target.value))}
                    style={{ width:'100%' }}>
                    <option value="">{L("Automatic (fit to the labels)")}</option>
                    <option value="0">{L("Horizontal")}</option>
                    <option value="-30">{L("Tilted 30°")}</option>
                    <option value="-45">{L("Tilted 45°")}</option>
                    <option value="-90">{L("Vertical")}</option>
                  </select>
                </div>
                )}
                <div style={{ marginBottom: 12 }}>
                  <label htmlFor="format-y-axis-angle" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                    {L("Value label angle")}
                  </label>
                  {/* Automatic leaves value labels upright, which is almost always
                      right -- they are short and read left to right. The gutter is
                      already sized to whatever they turn out to be. */}
                  <select id="format-y-axis-angle" value={yAxisAngle ?? ''}
                    onChange={e => setYAxisAngle(e.target.value === '' ? undefined : Number(e.target.value))}
                    style={{ width:'100%' }}>
                    <option value="">{L("Automatic (upright)")}</option>
                    <option value="-30">{L("Tilted 30°")}</option>
                    <option value="-45">{L("Tilted 45°")}</option>
                    <option value="-90">{L("Vertical")}</option>
                  </select>
                </div>
                <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
                  {/* checked falls back to false purely to give the checkbox a starting
                      look before the user touches it -- axisLine itself stays undefined
                      (and unsaved) until they do; see the state-declaration comment above. */}
                  <input id="format-axis-line" type="checkbox" checked={axisLine ?? false} onChange={e => setAxisLine(e.target.checked)} />
                  <label htmlFor="format-axis-line" style={{ fontSize: 12, cursor: 'pointer' }}>{L("Show axis line")}</label>
                </div>
                <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input id="format-tick-line" type="checkbox" checked={tickLine ?? false} onChange={e => setTickLine(e.target.checked)} />
                  <label htmlFor="format-tick-line" style={{ fontSize: 12, cursor: 'pointer' }}>{L("Show tick marks")}</label>
                </div>
              </>)}

              {formatCaps.includes('yScale') && (
                <div style={{ marginBottom: 12 }}>
                  <label htmlFor="format-y-scale" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                    {L("Y axis scale")}
                  </label>
                  <select id="format-y-scale" value={yScale ?? 'linear'} onChange={e => setYScale(e.target.value as 'linear' | 'log')} style={{ width:'100%' }}>
                    <option value="linear">{L("Linear")}</option>
                    <option value="log">{L("Logarithmic")}</option>
                  </select>
                  <div style={{ fontSize: 11, color:'var(--muted)', marginTop:3 }}>
                    {L("A log axis cannot show zero or negative values; the axis falls back to linear when the data contains one.")}
                  </div>
                </div>
              )}

              {formatCaps.includes('yDomain') && (
                <div style={{ display:'flex', gap:8, marginBottom:12 }}>
                  <div style={{ flex:1 }}>
                    <label htmlFor="format-y-min" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                      {L("Y axis min")}
                    </label>
                    <input id="format-y-min" type="number" value={yMin} onChange={e => setYMin(e.target.value)} style={{ width:'100%' }} placeholder={L("auto")} />
                  </div>
                  <div style={{ flex:1 }}>
                    <label htmlFor="format-y-max" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                      {L("Y axis max")}
                    </label>
                    <input id="format-y-max" type="number" value={yMax} onChange={e => setYMax(e.target.value)} style={{ width:'100%' }} placeholder={L("auto")} />
                  </div>
                </div>
              )}

              {formatCaps.includes('grid') && (<>
                <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input id="format-grid-toggle" type="checkbox" checked={showGrid ?? true} onChange={e => setShowGrid(e.target.checked)} />
                  <label htmlFor="format-grid-toggle" style={{ fontSize: 12, cursor: 'pointer' }}>{L("Show gridlines")}</label>
                </div>
                {(showGrid ?? true) && (<>
                  <div style={{ marginBottom: 12 }}>
                    <label htmlFor="format-grid-style" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                      {L("Gridline style")}
                    </label>
                    <select id="format-grid-style" value={gridStyle ?? 'solid'} onChange={e => setGridStyle(e.target.value as 'dashed' | 'solid')} style={{ width:'100%' }}>
                      <option value="dashed">{L("Dashed")}</option>
                      <option value="solid">{L("Solid")}</option>
                    </select>
                  </div>
                  <div style={{ marginBottom: 12 }}>
                    <label htmlFor="format-grid-color" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                      {L("Gridline colour")}
                    </label>
                    <input id="format-grid-color" type="color" value={gridColor || '#e2e8f0'} onChange={e => setGridColor(e.target.value)}
                      style={{ width:36, height:26, padding:2, border:'1px solid var(--border)', borderRadius:4, cursor:'pointer', background:'var(--surface)' }} />
                  </div>
                  <div>
                    <label htmlFor="format-wall-color" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                      {L("Wall colour")}
                    </label>
                    <input id="format-wall-color" type="color" value={wallColor || '#f8fafc'} onChange={e => setWallColor(e.target.value)}
                      style={{ width:36, height:26, padding:2, border:'1px solid var(--border)', borderRadius:4, cursor:'pointer', background:'var(--surface)' }} />
                  </div>
                </>)}
              </>)}

              {formatCaps.includes('legend') && (<>
                <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input id="format-legend-toggle" type="checkbox" checked={showLegend ?? true} onChange={e => setShowLegend(e.target.checked)} />
                  <label htmlFor="format-legend-toggle" style={{ fontSize: 12, cursor: 'pointer' }}>{L("Show legend")}</label>
                </div>
                {(showLegend ?? true) && (
                  <div style={{ marginBottom: 12 }}>
                    <label htmlFor="format-legend-position" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                      {L("Legend position")}
                    </label>
                    <select id="format-legend-position" value={legendPosition ?? 'bottom'}
                      onChange={e => setLegendPosition(e.target.value as 'top' | 'bottom' | 'left' | 'right')} style={{ width:'100%' }}>
                      <option value="top">{L("Top")}</option>
                      <option value="bottom">{L("Bottom")}</option>
                      <option value="left">{L("Left")}</option>
                      <option value="right">{L("Right")}</option>
                    </select>
                  </div>
                )}
                {(showLegend ?? true) && (
                  <div style={{ marginBottom: 12 }}>
                    <label htmlFor="format-legend-title" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                      {L("Legend title")}
                    </label>
                    <input id="format-legend-title" value={legendTitle}
                      onChange={e => setLegendTitle(e.target.value)}
                      style={{ width:'100%' }} placeholder={L("e.g. Customer Age Group")} />
                    <div style={{ fontSize: 10.5, color:'var(--muted)', marginTop:3 }}>
                      {L("Names the FIELD the entries are values of — the swatches already say which value each colour is.")}
                    </div>
                  </div>
                )}
              </>)}

              {formatCaps.includes('overview') && (
                <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input id="format-overview-axis" type="checkbox" checked={overviewAxis ?? false}
                    onChange={e => setOverviewAxis(e.target.checked)} />
                  <label htmlFor="format-overview-axis" style={{ fontSize: 12, cursor: 'pointer' }}>{L("Overview axis (zoom brush)")}</label>
                </div>
              )}

              {formatCaps.includes('dataLabels') && (
                <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input id="format-data-labels-toggle" type="checkbox" checked={dataLabels ?? false} onChange={e => setDataLabels(e.target.checked)} />
                  <label htmlFor="format-data-labels-toggle" style={{ fontSize: 12, cursor: 'pointer' }}>{L("Show data labels")}</label>
                </div>
              )}

              {formatCaps.includes('patterns') && (
                <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input id="format-series-patterns" type="checkbox" checked={seriesPatterns ?? false} onChange={e => setSeriesPatterns(e.target.checked)} />
                  <label htmlFor="format-series-patterns" style={{ fontSize: 12, cursor: 'pointer' }}>{L("Distinguish groups by pattern (accessible)")}</label>
                </div>
              )}

              {!formatCaps.includes('tableOptions') && (
                <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input id="format-show-as-table" type="checkbox" checked={showAsTable ?? false}
                    onChange={e => setShowAsTable(e.target.checked)} />
                  <label htmlFor="format-show-as-table" style={{ fontSize: 12, cursor: 'pointer' }}>{L("Show as table (accessible alternative)")}</label>
                </div>
              )}
              {formatCaps.includes('tableOptions') && (<>
                {/* show_totals reads false-ish when absent (widget_data.py: `if
                    config.get("show_totals"):`), so its display default matches every
                    other false-by-default toggle above. show_subtotals is the opposite —
                    widget_data.py defaults it to True — so its checkbox displays checked
                    out of the box, but (per the tri-state rule) that display default is
                    NEVER written back on its own; only an explicit click persists. */}
                <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input id="format-show-totals" type="checkbox" checked={showTotals ?? false} onChange={e => setShowTotals(e.target.checked)} />
                  <label htmlFor="format-show-totals" style={{ fontSize: 12, cursor: 'pointer' }}>{L("Show totals")}</label>
                </div>
                {/* The `__total__` row-subtotal column exists only on the pivoted
                    crosstab branch of shape_series, which is reached only when a
                    SECOND dimension is set. On a plain table, or a crosstab whose
                    Column Pivot is empty, there is no subtotal column in any
                    configuration — and this control shipped PRE-CHECKED, so it
                    actively asserted a column that did not exist. It is offered where
                    it has a consumer and nowhere else. Hiding it never drops a saved
                    value: showSubtotals is still seeded from cfg and still written
                    when it is defined, so an explicit false survives a round trip
                    through a config that cannot currently show the control. */}
                {dimension2 && (
                  <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
                    <input id="format-show-subtotals" type="checkbox" checked={showSubtotals ?? true} onChange={e => setShowSubtotals(e.target.checked)} />
                    <label htmlFor="format-show-subtotals" style={{ fontSize: 12, cursor: 'pointer' }}>{L("Show row subtotals")}</label>
                  </div>
                )}
                {/* Where totals sit, and what the grand total covers. Offered only
                    while something they act on is showing. Display defaults are the
                    read-time defaults ('after', 'all'), never written until touched. */}
                {((showTotals ?? false) || (dimension2 && (showSubtotals ?? true))) && (
                  <div style={{ marginBottom: 12 }}>
                    <label htmlFor="format-totals-position" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                      {L("Totals placement")}
                    </label>
                    <select id="format-totals-position" value={totalsPosition ?? 'after'}
                      onChange={e => setTotalsPosition(e.target.value as 'before' | 'after')} style={{ width:'100%' }}>
                      <option value="before">{L("Before the data")}</option>
                      <option value="after">{L("After the data")}</option>
                    </select>
                  </div>
                )}
                {(showTotals ?? false) && (
                  <div style={{ marginBottom: 12 }}>
                    <label htmlFor="format-totals-scope" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                      {L("Total covers")}
                    </label>
                    <select id="format-totals-scope" value={totalsScope ?? 'all'}
                      onChange={e => setTotalsScope(e.target.value as 'all' | 'shown')} style={{ width:'100%' }}>
                      <option value="all">{L("All rows")}</option>
                      <option value="shown">{L("Only the rows shown")}</option>
                    </select>
                  </div>
                )}
                <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input id="format-table-row-numbers" type="checkbox" checked={tableRowNumbers ?? false} onChange={e => setTableRowNumbers(e.target.checked)} />
                  <label htmlFor="format-table-row-numbers" style={{ fontSize: 12, cursor: 'pointer' }}>{L("Row numbers")}</label>
                </div>
                <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input id="format-table-row-lines" type="checkbox" checked={tableRowLines ?? false} onChange={e => setTableRowLines(e.target.checked)} />
                  <label htmlFor="format-table-row-lines" style={{ fontSize: 12, cursor: 'pointer' }}>{L("Row lines")}</label>
                </div>
                <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input id="format-table-banding" type="checkbox" checked={tableBanding ?? false} onChange={e => setTableBanding(e.target.checked)} />
                  <label htmlFor="format-table-banding" style={{ fontSize: 12, cursor: 'pointer' }}>{L("Banded rows")}</label>
                </div>
                <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input id="format-table-condensed" type="checkbox" checked={tableCondensed ?? false} onChange={e => setTableCondensed(e.target.checked)} />
                  <label htmlFor="format-table-condensed" style={{ fontSize: 12, cursor: 'pointer' }}>{L("Condensed")}</label>
                </div>
                {(wt === 'crosstab' || wt === 'matrix') && (
                  <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
                    <input id="format-table-sparkline" type="checkbox" checked={tableSparkline ?? false} onChange={e => setTableSparkline(e.target.checked)} />
                    <label htmlFor="format-table-sparkline" style={{ fontSize: 12, cursor: 'pointer' }}>{L("Row trend sparkline")}</label>
                  </div>
                )}
              </>)}
            </ExpandableGroup>
          )}
        </>)}

        {/* Appearance — offered to every widget type (WidgetRenderer.tsx reads
            widget_background, widget_border_width, widget_border_color, widget_radius,
            widget_padding and alt_text regardless of wt), so this group lives outside
            the type-conditional block above and is not gated on formattingCapabilities
            at all. */}
        <ExpandableGroup id="appearance" title="Appearance" defaultOpen={false} // i18n-ok: ExpandableGroup translates its title
          searchTerms={APPEARANCE_SEARCH_TERMS} {...groupFilterProps('Appearance', APPEARANCE_SEARCH_TERMS)}>
          <div style={{ display:'flex', gap:8, marginBottom:12 }}>
            <div>
              <label htmlFor="appearance-background" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                {L("Background")}
              </label>
              <input id="appearance-background" type="color" value={widgetBackground || defaultSurfaceColor} onChange={e => setWidgetBackground(e.target.value)}
                style={{ width:36, height:26, padding:2, border:'1px solid var(--border)', borderRadius:4, cursor:'pointer', background:'var(--surface)' }} />
            </div>
            <div>
              <label htmlFor="appearance-border-color" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                {L("Border colour")}
              </label>
              <input id="appearance-border-color" type="color" value={widgetBorderColor || defaultBorderColor} onChange={e => setWidgetBorderColor(e.target.value)}
                style={{ width:36, height:26, padding:2, border:'1px solid var(--border)', borderRadius:4, cursor:'pointer', background:'var(--surface)' }} />
            </div>
          </div>
          <div style={{ display:'flex', gap:8, marginBottom:12 }}>
            <div style={{ flex:1 }}>
              <label htmlFor="appearance-border-width" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                {L("Border width")}
              </label>
              <input id="appearance-border-width" type="number" min={0} max={20} value={widgetBorderWidth}
                onChange={e => setWidgetBorderWidth(e.target.value)} style={{ width:'100%' }} placeholder="1" />
            </div>
            <div style={{ flex:1 }}>
              <label htmlFor="appearance-radius" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                {L("Corner radius")}
              </label>
              <input id="appearance-radius" type="number" min={0} max={40} value={widgetRadius}
                onChange={e => setWidgetRadius(e.target.value)} style={{ width:'100%' }} placeholder={L("auto")} />
            </div>
          </div>
          <div style={{ marginBottom: 12 }}>
            <label htmlFor="appearance-padding" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
              {L("Padding")}
            </label>
            <input id="appearance-padding" type="number" min={0} max={60} value={widgetPadding}
              onChange={e => setWidgetPadding(e.target.value)} style={{ width:'100%' }} placeholder={L("auto")} />
          </div>
          <div style={{ marginBottom: 12 }}>
            <label htmlFor="appearance-skin" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
              {L("Skin")}
            </label>
            <select id="appearance-skin" value={widgetSkin} onChange={e => setWidgetSkin(e.target.value)} style={{ width:'100%' }}>
              <option value="none">{L("None")}</option>
              <option value="flat">{L("Flat")}</option>
              <option value="raised">{L("Raised")}</option>
              <option value="recessed">{L("Recessed")}</option>
              <option value="sheen">{L("Sheen")}</option>
              <option value="gloss">{L("Gloss")}</option>
              <option value="matte">{L("Matte")}</option>
            </select>
          </div>
          <div style={{ marginBottom: 12 }}>
            {/* Distinct from the Image section's own "Image alt text" control above,
                which writes cfg.alt -- this one is the whole widget's accessible name,
                consumed by WidgetRenderer.tsx as the aria-label on its role="figure"
                container (cfg.alt_text), not an <img> alt attribute. An image widget
                shows both controls at once, so the labels must not read the same. */}
            <label htmlFor="appearance-alt-text" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
              {L("Widget description (screen readers)")}
            </label>
            <input id="appearance-alt-text" value={altText} onChange={e => setAltText(e.target.value)} style={{ width:'100%' }} placeholder={L("Describes this widget for screen readers")} />
          </div>
        </ExpandableGroup>

        {pages?.some(p => p.page_type === 'drillthrough') && (
          <div style={{ marginBottom: 12 }}>
            <label htmlFor="drillthrough-page-select" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
              {L("Drillthrough page")}
            </label>
            <select id="drillthrough-page-select" value={drillthroughPageId} onChange={e => setDrillthroughPageId(e.target.value)} style={{ width:'100%' }}>
              <option value="">{L("— none —")}</option>
              {pages.filter(p => p.page_type === 'drillthrough').map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
        )}

        {pages?.some(p => p.page_type === 'tooltip') && (
          <div style={{ marginBottom: 12 }}>
            <label htmlFor="tooltip-page-select" style={{ display:'block', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
              {L("Tooltip page")}
            </label>
            <select id="tooltip-page-select" value={tooltipPageId} onChange={e => setTooltipPageId(e.target.value)} style={{ width:'100%' }}>
              <option value="">{L("— none —")}</option>
              {pages.filter(p => p.page_type === 'tooltip').map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
        )}
      </div>

      {/* Display rules */}
      {supportsDisplayRules && (
        <div style={{ borderTop: '1px solid var(--border)', padding: '12px 14px' }}>
          <ExpandableGroup id="rules" title="Display rules" // i18n-ok: ExpandableGroup translates its title
            searchTerms={RULES_SEARCH_TERMS} {...groupFilterProps('Display rules', RULES_SEARCH_TERMS)}>
            <DisplayRulesPanel
              key={widget.id}
              rules={displayRules}
              columns={ruleColumns}
              numericColumns={ruleNumericColumns}
              onChange={setDisplayRules}
              errors={ruleErrors}
            />
          </ExpandableGroup>
        </div>
      )}

      {/* Visual interaction settings */}
      <ExpandableGroup id="interactions" title="Interactions" // i18n-ok: ExpandableGroup translates its title
        searchTerms={INTERACTIONS_SEARCH_TERMS} {...groupFilterProps('Interactions', INTERACTIONS_SEARCH_TERMS)}>
        <InteractionSettings widget={widget}
          pageWidgets={pages?.find(pg => pg.id === widget.page_id)?.widgets ?? []} />
      </ExpandableGroup>
      {assignOpen && (
        <AssignDataDialog objectName={objectLabel({ title, widget_type: wt, id: widget.id })}
          focusRole={assignRole} onClose={() => setAssignOpen(false)}>
          <DataRolesList specs={roleSpecs} values={assignedFields} kindOf={fieldKind} displayName={displayName}
            onAdd={role => setAddRole(role)} onRemove={removeField} addBlocked={addBlocked} />
        </AssignDataDialog>
      )}
      {addRole && (() => {
        const rf = roleSpecs.find(r => r.role === addRole)
        if (!rf) return null
        const heading = (rf.label ?? rf.role).replace(/\s*\(.*\)\s*$/, '')
        const withHierarchy = rf.role === 'category' && hierarchyOptions.length > 0
        const current = fieldsOf(rf)
        const selected = withHierarchy && hierarchyNodeId ? [`h:${hierarchyNodeId}`] : current
        const choices = [...roleChoices(rf, current),
          ...(withHierarchy ? hierarchyOptions.map(o => ({ value: `h:${o.id}`, label: o.label, group: 'Hierarchies' })) : [])]
        return (
          <AddFieldDialog heading={heading} multi={!!rf.multi} choices={choices} selected={selected}
            emptyText={(r => r && L(r))(emptyPickerReason(effectiveCols.length > 0, roleAccepts(rf.role))) ?? undefined}
            onClose={() => setAddRole(null)}
            onApply={values => setFields(rf, values)} />
        )
      })()}
    </div>
  )
}



/**
 * The panel is the heaviest thing on the builder page (hundreds of controls
 * and column pickers), and the builder re-renders on every pointer move while
 * a tile is dragged or resized -- ~400ms a frame, which is what made resizing
 * feel frozen (QA 2026-09-26). Nothing the panel shows depends on layout, so
 * it re-renders only when what it DOES show changes.
 *
 * Compared by value where the builder rebuilds an equal object each render:
 * `columns` (a fresh array) and `distinctCounts` / `ruleErrors` (fresh
 * objects).
 */
function sameColumns(a: Props['columns'], b: Props['columns']): boolean {
  if (a === b) return true
  if (!a || !b || a.length !== b.length) return false
  return a.every((c, i) => c.name === b[i].name && c.dtype === b[i].dtype)
}
function panelPropsEqual(a: Props, b: Props): boolean {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]) as Set<keyof Props>
  for (const k of keys) {
    const va = a[k], vb = b[k]
    if (va === vb) continue
    // Only the hierarchy refresher is rebuilt each render and is safe to
    // keep stale (it reads the report's dataset id, which a new report brings
    // with new `pages` anyway). `onUpdate` is compared by identity: a stale
    // saver would write to the wrong widget or page.
    if (k === 'onHierarchyRefresh' && typeof va === 'function' && typeof vb === 'function') continue
    if (k === 'columns') { if (sameColumns(va as Props['columns'], vb as Props['columns'])) continue; return false }
    if (k === 'distinctCounts' || k === 'ruleErrors') {
      if (JSON.stringify(va ?? null) === JSON.stringify(vb ?? null)) continue
      return false
    }
    return false
  }
  return true
}

export default memo(WidgetConfigPanel, panelPropsEqual)
