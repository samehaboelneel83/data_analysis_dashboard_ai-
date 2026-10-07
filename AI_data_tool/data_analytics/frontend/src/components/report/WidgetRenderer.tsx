import { formatDate } from '../../lib/dateFormat'
import { lazy, memo, Suspense, useContext, useEffect, useState, useCallback, useMemo, useRef } from 'react'
import type { PartialPeriod, RelativeNote } from '../../lib/relativeDates'
import { partialPeriodEnd } from '../../lib/relativeDates'
import type { BrushRange } from './chartRenderers/axisOptions'
import OverviewStrip from './chartRenderers/OverviewStrip'
import { StaticChartsContext } from './chartRenderers/useChartViewport'
import { createPortal } from 'react-dom'
import { Copy, Trash2, MoreVertical, Link as LinkIcon } from 'lucide-react'
import { widgetDataApi } from '../../services/api'
import { isCanceledRequest } from '../../lib/canceledRequest'
import { useT, type MessageKey, type TranslateFn } from '../../i18n'
import { usePanelLabel } from './panelLabels'
import { useDirection } from '../../contexts/DirectionContext'
import ConvertToMenu from './ConvertToMenu'
import { pickChartSvg, svgToPng } from '../../lib/widgetImage'
import toast from 'react-hot-toast'
import ActionMenu from '../ActionMenu'
import { DifferenceDialog, ExplainDialog, ScenarioDialog, WhyDialog, describeFilter, useViewAs, viewAsOptions, type WhySection } from './ViewerKit'
import type { CalcColumn, CalcColumnFormat, Dataset } from '../../services/api'
import { useCrossFilter, CrossFilterProvider } from './CrossFilterContext'
import { EmptyState } from './chartUtils'
import type { Widget, ReportPage, HierarchyNode, Bookmark } from '../../types/report'
import type { DisplayRule, RuleStyles } from '../../lib/displayRules'
import { Z_OVERLAY, Z_DROPDOWN } from '../../lib/zIndex'
import { getChildNode, walkToDepth } from '../../lib/hierarchyUtils'

import { WidgetBody } from './WidgetBody'
const ReconcileDialog = lazy(() => import('./ReconcileDialog'))
import { ASSIGN_DATA_EVENT, missingRequiredRoles } from './WidgetPlaceholder'
import { rangeLabel, type RangeValue } from './SlicerRange'

/** Charts whose bars/points are groups of rows two of which can be tested (Phase 7.2). */
const DIFFERENCE_TYPES: string[] = ['bar', 'line', 'area', 'pie', 'donut', 'dot_plot', 'step', 'treemap', 'funnel']
import { TruncationNote, PATCH_WIDGET_EVENT, missingCategorySentence, suppressedCellsSentence, ignoredFiltersSentence } from './TruncationNote'
export { CustomVisual } from './CustomVisual'

const PREVIEW_W = 320
const PREVIEW_H = 400

// Element styling "skins" (SAS's default/none/pressed/sheen/gloss/matte/flat): a
// visual treatment applied to the widget container as a box-shadow, so it composes
// with the author's background/border rather than overriding them. Drag and select
// feedback take precedence over the skin (see the container's boxShadow below).
export const SKIN_SHADOWS: Record<string, string> = {
  flat:     'none',
  raised:   '0 2px 8px rgba(0,0,0,.18)',
  recessed: 'inset 0 2px 6px rgba(0,0,0,.22)',
  sheen:    'inset 0 22px 30px -22px rgba(255,255,255,.55)',
  gloss:    'inset 0 26px 26px -22px rgba(255,255,255,.7), 0 2px 6px rgba(0,0,0,.15)',
  matte:    'inset 0 0 40px rgba(0,0,0,.05)',
}
export const SKIN_OPTIONS = ['none', 'flat', 'raised', 'recessed', 'sheen', 'gloss', 'matte']

function skinShadow(skin: unknown): string {
  return (typeof skin === 'string' && SKIN_SHADOWS[skin]) || 'none'
}

// ── Value formatters ──────────────────────────────────────────────────────────

interface Props {
  widget:            Widget
  datasetId:         number | null
  calculatedColumns?: CalcColumn[]
  columnFormats?:    Record<string, CalcColumnFormat>
  /** Columns classified as geography and the boundary set each draws with.
   *  Travels beside columnFormats for the same reason: it is DATASET metadata
   *  the renderer needs and the widget config does not carry. */
  geography?:        Record<string, number>
  datasets?:         Record<number, Dataset>
  selected?:         boolean
  isMultiSelected?:  boolean
  onSelect?:     (e: React.MouseEvent) => void
  onDelete?:     () => void
  /** "Another one of these" -- SAS's Duplicate Object. Separate from widget
   *  templates, which are for reuse ACROSS reports rather than beside this one. */
  onDuplicate?:  () => void
  editMode?:     boolean
  promptFilter?: { column: string; value: string } | null
  onDragStart?:  (e: React.MouseEvent) => void
  onResizeStart?:(e: React.MouseEvent) => void
  isDragging?:   boolean
  onFetchComplete?: (widgetId: number, info: { durationMs: number; rowCount: number; sampled: boolean; ruleErrors?: { id?: string; message: string }[] }) => void
  pages?:        ReportPage[]
  reportDisplayRules?: DisplayRule[]
  /** Report-level filters applied to every widget (defined once for the whole report). */
  reportFilters?: { column: string; op: string; value: unknown }[]
  /** The reader's own filters for the whole page (the filter bar above the
   *  page). Applied only where this widget's data HAS the column -- a live
   *  (DirectQuery) source refuses an unknown column outright. */
  pageFilters?: { column: string; op: string; value: unknown }[]
  onDrillthrough?: (targetPageId: number, filterValue: unknown) => void
  isPreview?:    boolean
  hierarchy?:    HierarchyNode[]
  bookmarks?:    Bookmark[]
  onNavigateToPage?: (pageId: number) => void
  onApplyBookmark?: (bookmark: Bookmark) => void
  reportId?: number
  parameters?: Record<string, unknown>
  onSetParameter?: (name: string, value: string) => void
  /** Pre-resolved result: when set, the widget renders THIS and never fetches.
      The shared (guest) view resolves data server-side per saved widget --
      the anonymous session has no API credentials to fetch with. */
  dataOverride?: unknown
  /** Org relationships, for cross-source filter translation: a cross-filter
      whose column this widget's dataset lacks is renamed through the mapped
      relationship instead of silently filtering nothing. */
  relationships?: { from_dataset_id: number; from_column: string; to_dataset_id: number; to_column: string }[]
  /** Fetch immediately instead of waiting for the widget to scroll into view.
      Kiosk ticks, print and export flows pass this: they read from mounted
      widgets whether or not a human ever scrolled to them. */
  eagerFetch?: boolean
  /** S4: hides the export-data/export-image menu items. Defaults to true (the
      builder's own behaviour); the guest (SharedReport) view passes false --
      handleExport calls the AUTHENTICATED /datasets/.../export route, which an
      anonymous session has no bearer token for, so offering it there is a dead
      button at best and a governance gap at worst (a signed-in in-org viewer
      could use it to sidestep the guest surface's own page-visibility rules). */
  allowExport?: boolean
  /** Bump to force a refetch -- the dashboard's Refresh button. It rides the
   *  fetchData dependency list, so a change re-arms the fetch effect; combined
   *  with clearWidgetDataClientCache() it bypasses the 30s client TTL. */
  refreshNonce?: number
}

/**
 * Does this widget go to the server for its data?
 *
 * Mirrors `fetchData`'s early returns, and exists so `loading` can START true
 * for anything that fetches. It used to start false while `data` was still
 * null, and every renderer reads null data as "nothing configured" -- so a
 * dashboard opened with thirty tiles all reading "Configure widget to see
 * data", blaming the author for a configuration mistake they had not made.
 * Worse for a tile below the fold: fetching is lazy (IntersectionObserver), so
 * one that is never scrolled to never fetches, and that placeholder was not
 * transient at all -- it was the permanent resting state of an off-screen
 * widget. Same principle the fetch-error path already follows.
 */
function widgetFetchesData(widgetType: string, config: unknown, dataOverride: unknown): boolean {
  if (dataOverride !== undefined) return false
  if (widgetType === 'text') {
    // Only a text block carrying {{agg(column)}} placeholders queries.
    return /\{\{\s*(sum|avg|min|max|count|median)\(/i
      .test(String((config as { content?: unknown } | undefined)?.content ?? ''))
  }
  return !['button', 'image', 'shape', 'container', 'web_content'].includes(widgetType)
}

type FilterLikeLocal = { column: string; op?: string; value: unknown; granularity?: string }


/** True when a pointer event started on an interactive control inside a
 *  widget header, so the header's drag handler must leave it alone. */
function isHeaderControl(target: EventTarget | null): boolean {
  return target instanceof Element
    && !!target.closest('button, a, input, select, textarea, [role="menu"], [role="menuitem"], .dl-whead__ctl')
}

/** The server's account of auto-binning (services/auto_bin.py `finish`). */
export interface Binning {
  column: string; kind: 'date' | 'number' | 'text'; grouped: boolean
  top_n?: number | null; top_n_choices?: number[] | null
  grain?: string | null; width?: number | null; target?: number; distinct?: number
  buckets?: number | null; window?: [unknown, unknown] | null; finest?: boolean
}
interface StripRowLike { name?: unknown; value?: unknown; bin_start?: unknown; bin_end?: unknown }

/** How long a chart waits after a filter change for the next one before it
 *  asks the server again. Long enough to swallow a burst of clicks, short
 *  enough not to be felt. */
export const FILTER_SETTLE_MS = 250

/** Rows a raw table asks the server for at a time (and again on each scroll
 *  to the bottom). A tile shows about twenty; the rest are one scroll away. */
export const TABLE_PAGE = 200

/** A table of the data's own rows -- no grouping -- which the server can page. */
export function isRawTable(widgetType: string, cfg: Record<string, unknown>): boolean {
  if (widgetType !== 'table') return false
  if (cfg.dimension || cfg.dimension2 || cfg.dimension_levels) return false
  const agg = String(cfg.aggregation ?? '').toLowerCase()
  return !cfg.measure || agg === 'none' || agg === 'raw'
}

/** Append the next page to what is on screen. Display-rule styles arrive
 *  indexed from the page's first row, so they are shifted by `offset`. */
export function mergeTablePage(prev: any, next: any, offset: number): any {
  const rows = [...(prev.rows ?? []), ...(next.rows ?? [])]
  let rule_styles = prev.rule_styles
  const nr = next.rule_styles
  if (nr && (nr.rows?.length || (nr.cells && Object.keys(nr.cells).length))) {
    const baseRows: any[] = [...(prev.rule_styles?.rows ?? [])]
    while (baseRows.length < offset) baseRows.push(null)
    const cells: Record<string, any> = { ...(prev.rule_styles?.cells ?? {}) }
    Object.entries(nr.cells ?? {}).forEach(([k, v]) => { cells[String(Number(k) + offset)] = v })
    rule_styles = { ...(prev.rule_styles ?? { widget: {} }), rows: [...baseRows.slice(0, offset), ...(nr.rows ?? [])], cells }
  }
  return { ...prev, rows, rule_styles, page: { ...(prev.page ?? {}), loaded: rows.length } }
}

/** Charts whose axis the smart slider zooms: a continuous axis of dates or numbers. */
const SMART_ZOOM_TYPES = new Set(['line', 'area', 'step', 'bar'])

const GRAIN_WORD: Record<string, string> = {
  hour: 'hour', day: 'day', week: 'week', month: 'month', quarter: 'quarter', year: 'year',
}

const GRAIN_KEY: Record<string, MessageKey> = {
  hour: 'bc.canvas.grain.hour', day: 'bc.canvas.grain.day', week: 'bc.canvas.grain.week',
  month: 'bc.canvas.grain.month', quarter: 'bc.canvas.grain.quarter', year: 'bc.canvas.grain.year',
}
/** A grain in the reader's words when a translator is given. */
function grainWord(grain: string | null | undefined, t?: TranslateFn): string {
  const g = grain ?? ''
  return t && GRAIN_KEY[g] ? t(GRAIN_KEY[g]) : GRAIN_WORD[g] ?? String(grain)
}

/** The binning chip's words; in the reader's language when given `t`. */
export function binningLabel(b: Binning | undefined | null, t?: TranslateFn): string {
  if (!b?.grouped) return ''
  if (b.kind === 'date' && b.grain) {
    return t ? t('bc.canvas.bin.by', { grain: grainWord(b.grain, t) }) : `by ${GRAIN_WORD[b.grain] ?? b.grain}`
  }
  if (b.kind === 'number' && b.width) {
    const w = b.width.toLocaleString('en-US')
    return t ? t('bc.canvas.bin.ranges', { width: w }) : `ranges of ${w}`
  }
  if (b.kind === 'text' && b.top_n) return t ? t('bc.canvas.bin.topN', { n: b.top_n }) : `top ${b.top_n} + other`
  return t ? t('bc.canvas.bin.grouped') : 'grouped'
}

export function binningTitle(b: Binning | undefined | null, t?: TranslateFn): string {
  if (!b?.grouped) return ''
  if (t) {
    const distinct = (b.distinct ?? 0).toLocaleString('en-US')
    const column = String(b.column ?? '')
    if (b.kind === 'text') return t('bc.canvas.bin.titleText', { distinct, column, n: b.top_n ?? '' })
    return b.kind === 'date'
      ? t('bc.canvas.bin.titleDate', { distinct, column, grain: grainWord(b.grain, t), buckets: b.buckets ?? '?' })
      : t('bc.canvas.bin.titleRanges', { distinct, column, width: (b.width ?? 0).toLocaleString('en-US'), buckets: b.buckets ?? '?' })
  }
  if (b.kind === 'text') {
    return `${(b.distinct ?? 0).toLocaleString('en-US')} different ${b.column} values are too many to draw, so the chart shows the top ${b.top_n} and puts the rest together as "All Other". `
      + 'Every row is still counted. Pick 10, 20 or 50 to see more or fewer.'
  }
  const what = b.kind === 'date'
    ? `grouped by ${GRAIN_WORD[b.grain ?? ''] ?? b.grain}`
    : `grouped into ranges of ${(b.width ?? 0).toLocaleString('en-US')}`
  return `${(b.distinct ?? 0).toLocaleString('en-US')} different ${b.column} values are too many to draw, so the chart is ${what} (${b.buckets ?? '?'} points). `
    + 'Every row is still counted. Drag the slider under the chart to zoom in and see more detail.'
}

function WidgetRenderer({ widget, datasetId, calculatedColumns, columnFormats, geography, datasets, selected, isMultiSelected, onSelect, onDelete, onDuplicate, editMode, promptFilter, onDragStart, onResizeStart, isDragging, onFetchComplete, pages, reportDisplayRules, reportFilters, pageFilters, onDrillthrough, isPreview, hierarchy, bookmarks, onNavigateToPage, onApplyBookmark, reportId, parameters, onSetParameter, dataOverride, relationships, eagerFetch, allowExport = true, refreshNonce }: Props) {
  const { emitFilter, emitMultiFilter, getFiltersFor, canBroadcast, canReceive, activeFilters, clearAllFilters, clearFilter, interactions, getReceiveMode, carryFiltersTo } = useCrossFilter()
  const [data,    setData]    = useState<any>(null)
  const [loading, setLoading] = useState(
    () => widgetFetchesData(widget.widget_type, widget.config, dataOverride))
  // The backend's `code` beside its `detail` (services/error_codes.py). The
  // detail is what the reader sees; the code is what decides whether a
  // 'Try again' is offered -- `source_unavailable`, `source_busy` and `quota`
  // (after Retry-After) are the answers that can change on retry.
  const [fetchError, setFetchError] = useState<{ detail: string; code?: string } | null>(null)

  // Per-widget dataset override: if the widget has dataset_id in its config, use that dataset's
  // calc columns and formats; otherwise fall back to the report-level ones.
  const cfgDatasetId = (widget.config as { dataset_id?: number }).dataset_id
  const widgetDatasetId: number | null = cfgDatasetId ?? datasetId
  const overrideDataset: Dataset | undefined = (widgetDatasetId != null && datasets) ? datasets[widgetDatasetId] : undefined
  const effectiveCalcCols: CalcColumn[] = overrideDataset?.calculated_columns ?? calculatedColumns ?? []
  const effectiveFormats: Record<string, CalcColumnFormat> = overrideDataset?.column_formats ?? columnFormats ?? {}

  // Active value selected FROM this widget (for highlight)
  const [localSelected, setLocalSelected] = useState<unknown>(null)
  const [checked, setChecked] = useState<Set<unknown>>(new Set())

  useEffect(() => { setChecked(new Set()) }, [widget.id])

  const [containerTab, setContainerTab] = useState(0)
  const [containerOpen, setContainerOpen] = useState(true)
  const [drillPath, setDrillPath] = useState<{ column: string; granularity?: string; value: unknown; label: string }[]>([])
  // Decomposition drilling. Held here rather than in the widget's saved config
  // for the same reason hierarchy drilling is: a reader exploring a dashboard
  // is not editing it, and their path must not be written back to a report
  // other people are looking at.
  const [decompPath, setDecompPath] = useState<{ field: string; value: string }[]>([])
  const [decompSplit, setDecompSplit] = useState<string | null>(null)
  useEffect(() => { setDrillPath([]) }, [widget.id])

  const hierarchyNodeId = (widget.config as any).hierarchyNodeId as number | undefined
  // Power BI's expand: 0 = one level (drill mode), N = the bound level plus N
  // deeper levels shown together as a path label. Expanding and drilling are
  // exclusive -- each clears the other, matching how PBI's toolbar behaves.
  const [expandDepth, setExpandDepth] = useState(0)
  const currentNodeId = hierarchyNodeId != null && hierarchy ? walkToDepth(hierarchy, hierarchyNodeId, drillPath.length) : undefined
  const currentNode = currentNodeId != null ? hierarchy?.find(n => n.id === currentNodeId) : undefined
  // the chain of DISTINCT column levels reachable from the bound node -- expand
  // is only meaningful across different columns (a Year->Quarter granularity
  // chain reuses one date column and expands to nothing new)
  const expandLevels = (() => {
    if (hierarchyNodeId == null || !hierarchy) return []
    const cols: string[] = []
    let id: number | undefined = hierarchyNodeId
    while (id != null) {
      const node = hierarchy.find(n => n.id === id)
      if (!node?.column_name) break
      if (!cols.includes(node.column_name)) cols.push(node.column_name)
      const child = getChildNode(hierarchy, id)
      id = child?.id
    }
    return cols
  })()

  // Cross-filters coming from OTHER widgets
  const incomingFilters = getFiltersFor(widget.id, widget.page_id)

  // Rebuild merged config — useMemo with serialised deps so it only changes when
  // content changes, not on every render (avoids an infinite-fetch loop).
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const mergedPair = useMemo(() => {
    const cfg = { ...(widget.config as any) }
    const existing: any[] = cfg.filters ?? []
    const myCols = widgetDatasetId != null
      ? new Set((datasets?.[widgetDatasetId]?.columns ?? []).map(c => c.name))
      : null
    const translate = (column: string): string => {
      // Cross-source column mapping: a filter arriving from another dataset is
      // renamed through the modelled relationship, so "country on Sales" acts
      // as "cust_country on Shipments". Only when the local dataset LACKS the
      // column -- a shared name needs no mapping -- and only when the model
      // actually declares one: an unmapped foreign column stays as-is and
      // no-ops downstream, which is the honest outcome for an unmodelled pair.
      if (!myCols || myCols.size === 0 || myCols.has(column)) return column
      for (const r of relationships ?? []) {
        if (r.to_dataset_id === widgetDatasetId && r.from_column === column && myCols.has(r.to_column)) return r.to_column
        if (r.from_dataset_id === widgetDatasetId && r.to_column === column && myCols.has(r.from_column)) return r.from_column
      }
      return column
    }
    const crossFilters = incomingFilters.flatMap(f => {
      const between = (f.value as { between?: [number | null, number | null] } | null)?.between
      // A map area arrives as a range on each coordinate axis.
      if (Array.isArray(between) && between.length === 2) {
        // An open end (a range slicer with one bound) is null: no predicate.
        return [
          ...(between[0] != null ? [{ column: translate(f.column), op: 'gte', value: between[0] }] : []),
          ...(between[1] != null ? [{ column: translate(f.column), op: 'lte', value: between[1] }] : []),
        ]
      }
      return [{ column: translate(f.column), op: Array.isArray(f.value) ? 'in' : 'eq', value: f.value }]
    })
    const pagePrompt   = (promptFilter?.column && promptFilter?.value)
      ? [{ column: promptFilter.column, op: 'eq', value: promptFilter.value }]
      : []
    // Report-level common filters apply to every widget; translate columns across a
    // modelled relationship like cross-filters do, and let the shaper skip any that
    // this widget's dataset lacks (_apply_filters ignores unknown columns).
    const reportWide = (reportFilters ?? []).map(f => ({ column: translate(f.column), op: f.op, value: f.value }))
    const pageWide = (pageFilters ?? [])
      .map(f => ({ column: translate(f.column), op: f.op, value: f.value }))
      .filter(f => !myCols || myCols.size === 0 || myCols.has(f.column))
    cfg.filters = [...existing, ...reportWide, ...pageWide, ...crossFilters, ...pagePrompt]
    if (hierarchyNodeId != null && expandDepth > 0 && expandLevels.length > 1) {
      cfg.dimension_levels = expandLevels.slice(0, expandDepth + 1)
      cfg.dimension = expandLevels[0]
      delete cfg.dimension_granularity
    } else if (hierarchyNodeId != null && currentNode?.column_name) {
      cfg.dimension = currentNode.column_name
      if (currentNode.format) cfg.dimension_granularity = currentNode.format
      else delete cfg.dimension_granularity
      cfg.filters = [
        ...cfg.filters,
        ...drillPath.map(step => ({ column: step.column, op: 'eq', value: step.value, ...(step.granularity ? { granularity: step.granularity } : {}) })),
      ]
    }
    if (widget.widget_type === 'decomposition') {
      cfg.path = decompPath
      // An explicit choice wins; auto_split only fills the gap when the reader
      // has not picked a field, which is what keeps a suggestion a suggestion.
      if (decompSplit) cfg.split_by = decompSplit
      else if (!cfg.split_by) cfg.auto_split = true
    }
    // Report rules first, widget rules second: the engine lets a later rule win for the
    // same target, so widget-over-report precedence is list order, not a flag.
    const widgetRules = (cfg.display_rules as DisplayRule[] | undefined) ?? []
    const allRules = [...(reportDisplayRules ?? []), ...widgetRules]
    if (allRules.length > 0) cfg.display_rules = allRules
    // The translated cross-filters travel separately so highlight mode can
    // rebuild this exact config WITHOUT them for its unfiltered baseline.
    return { config: cfg, crossFilters }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(widget.config), JSON.stringify(incomingFilters), promptFilter?.column, promptFilter?.value, hierarchyNodeId, currentNode?.column_name, currentNode?.format, JSON.stringify(drillPath), JSON.stringify(decompPath), decompSplit, widget.widget_type, expandDepth, expandLevels.join(','), JSON.stringify(relationships ?? []), JSON.stringify(reportDisplayRules), JSON.stringify(reportFilters), JSON.stringify(pageFilters)])
  const mergedConfig = mergedPair.config
  const translatedCrossFilters = mergedPair.crossFilters

  /** The reader's transparency pane: every layer that decides this widget. */
  // Overview-axis zoom and the animation's current frame: widget-local,
  // never saved, shown in the header and the transparency pane.
  const [brushRange, setBrushRange] = useState<BrushRange | null>(null)
  const [brushNonce, setBrushNonce] = useState(0)
  const [animFrame, setAnimFrame] = useState<string | null>(null)

  // ── Smart slider (auto-bin zoom) ───────────────────────────────────────────
  // When the server grouped this chart's axis (data.binning, services/
  // auto_bin.py), the slider is an overview of the whole series. Dragging
  // shows the coarse rows inside the window at once; letting go asks the
  // server for that window again, at a finer grain. The base `data` is never
  // replaced -- it IS the overview -- so a zoom is always one step from undone.
  const binning = (data as { binning?: Binning } | null)?.binning
  const baseRows = (data as { rows?: StripRowLike[] } | null)?.rows
  const smartZoom = !!binning?.grouped && SMART_ZOOM_TYPES.has(widget.widget_type)
    && Array.isArray(baseRows) && baseRows.length > 2
    && baseRows.every(r => r && r.bin_start != null && r.bin_end != null)
  const [zoomSel, setZoomSel] = useState<{ a: number; b: number } | null>(null)
  const [zoom, setZoom] = useState<{ a: number; b: number; data: any } | null>(null)
  const [zoomLoading, setZoomLoading] = useState(false)
  const zoomCtl = useRef<AbortController | null>(null)
  // New base data (a filter, a refresh, a setting): the old window means nothing.
  useEffect(() => {
    zoomCtl.current?.abort()
    setZoomSel(null); setZoom(null); setZoomLoading(false)
  }, [data])
  useEffect(() => () => zoomCtl.current?.abort(), [])

  // ── Paged raw table ───────────────────────────────────────────────────────
  // Printed and static charts read every row (a page cannot be scrolled on
  // paper); everything interactive asks for TABLE_PAGE rows, then more.
  const isStaticChart = useContext(StaticChartsContext)
  const [loadingMore, setLoadingMore] = useState(false)
  // The reader's own Top N choice (10 / 20 / 50) for a text axis the server
  // cut down to its largest values. Widget-local and never saved, like a zoom.
  const [topN, setTopN] = useState<number | null>(null)
  const moreCtl = useRef<AbortController | null>(null)
  useEffect(() => { moreCtl.current?.abort(); setLoadingMore(false) }, [refreshNonce])
  useEffect(() => () => moreCtl.current?.abort(), [])
  // No clearing on new data here: the chart owns its window (useChartViewport)
  // and reports it for every series it draws, then null when it unmounts. A
  // parent effect runs AFTER the child's, so clearing here wiped the window
  // the chart had just opened on.
  const relNotes: RelativeNote[] = Array.isArray((data as { relative_dates?: unknown } | null)?.relative_dates)
    ? (data as { relative_dates: RelativeNote[] }).relative_dates : []
  const partial = ((data as { partial_period?: PartialPeriod } | null)?.partial_period) ?? null
  const whySections = (): WhySection[] => {
    const cfg0 = widget.config as Record<string, unknown>
    const cols = new Set((widgetDatasetId != null ? datasets?.[widgetDatasetId]?.columns ?? [] : []).map(c => c.name))
    const applies = (c: string) => cols.size === 0 || cols.has(c)
    const own = ((cfg0.filters as FilterLikeLocal[] | undefined) ?? [])
    const report = reportFilters ?? []
    const measureName = typeof cfg0.measure === 'string' ? cfg0.measure : null
    const agg = String(cfg0.aggregation ?? (measureName ? 'sum' : 'count'))
    const trunc = (data as { truncation?: { applied?: boolean; shown?: number; of?: number; reason?: string } } | null)?.truncation
    const notApply = (f: FilterLikeLocal) => applies(f.column) ? describeFilter(f, t) : t('bc.canvas.why.notApply', { filter: describeFilter(f, t) })
    const shownN = brushRange ? brushRange.endIndex - brushRange.startIndex + 1 : 0
    const rank = cfg0.rank as { mode?: string; n?: number; percent?: boolean; other?: boolean } | undefined
    const rankN = rank?.n ? `${rank.n}${rank.percent ? '%' : ''}` : ''
    const rules = [...(reportDisplayRules ?? []), ...((cfg0.display_rules as unknown[] | undefined) ?? [])]
    return [
      { title: t('bc.canvas.why.measured'), empty: '', items: [
        // QA3 C8: the aggregation in words in Arabic ("avg" glued to an Arabic
        // sentence read garbled); English keeps the code as before.
        measureName ? t('bc.canvas.why.aggOf', { agg: (() => {
          if (document.documentElement.lang !== 'ar') return agg
          const k = `rb.agg.${agg}` as MessageKey; const v = t(k); return v !== k ? v : agg })(), measure: measureName })
          : t('bc.canvas.why.rowCount'),
        ...(typeof cfg0.dimension === 'string' ? [t('bc.canvas.why.forEach', { dimension: cfg0.dimension })] : []),
        ...(widgetDatasetId != null && datasets?.[widgetDatasetId]?.name ? [t('bc.canvas.why.from', { dataset: datasets[widgetDatasetId].name })] : []),
      ] },
      { title: t('bc.canvas.why.ownTitle'), empty: t('bc.canvas.why.ownEmpty'), items: own.map(f => describeFilter(f, t)) },
      { title: t('bc.canvas.why.reportTitle'), empty: t('bc.canvas.why.reportEmpty'),
        items: report.map(f => notApply(f)) },
      { title: t('bc.canvas.why.pageTitle'), empty: t('bc.canvas.why.pageEmpty'),
        items: (pageFilters ?? []).map(f => notApply(f as FilterLikeLocal)) },
      { title: t('bc.canvas.why.selTitle'), empty: t('bc.canvas.why.selEmpty'),
        items: [
          ...translatedCrossFilters.map(f => describeFilter(f as FilterLikeLocal, t)),
          ...(promptFilter?.column && promptFilter?.value ? [t('bc.canvas.why.prompt', { column: promptFilter.column, value: String(promptFilter.value) })] : []),
          ...drillPath.map(s => t('bc.canvas.why.drilled', { column: s.column, value: String(s.value) })),
        ] },
      ...(relNotes.length || partial ? [{ title: t('bc.canvas.why.datesTitle'), empty: '', items: [
        ...relNotes.map(n => n.error ? t('bc.canvas.why.dateError', { column: n.column, error: n.error }) : `${n.column}: ${n.text ?? n.label}`),
        ...(partial ? [partial.text] : []),
      ] }] : []),
      ...(brushRange || (data as { type?: string } | null)?.type === 'animated' ? [{ title: t('bc.canvas.why.viewTitle'), empty: '', items: [
        ...(brushRange ? [t(brushRange.auto ? 'bc.canvas.why.brushAuto' : 'bc.canvas.why.brushZoom',
          { start: String(brushRange.start), end: String(brushRange.end), n: shownN, of: brushRange.of })] : []),
        ...((data as { type?: string } | null)?.type === 'animated' && animFrame
          ? [t('bc.canvas.why.animFrame', { field: String((data as { animate_by?: string }).animate_by), frame: String(animFrame) })] : []),
      ] }] : []),
      { title: t('bc.canvas.why.rankTitle'), empty: t('bc.canvas.why.rankEmpty'), items: [
        ...(rank?.n ? [t(rank.mode === 'bottom'
          ? (rank.other ? 'bc.canvas.why.rankBottomOther' : 'bc.canvas.why.rankBottom')
          : (rank.other ? 'bc.canvas.why.rankTopOther' : 'bc.canvas.why.rankTop'), { n: rankN })] : []),
        ...(trunc?.applied ? [trunc.reason === 'limit'
          ? t('bc.canvas.why.truncLimit', { shown: String(trunc.shown), of: String(trunc.of) })
          : t('bc.canvas.why.truncReason', { shown: String(trunc.shown), of: String(trunc.of), reason: String(trunc.reason) })] : []),
      ] },
      { title: t('bc.canvas.why.rulesTitle'), empty: t('bc.canvas.why.rulesEmpty'),
        items: rules.length ? [t(rules.length === 1 ? 'bc.canvas.why.rulesOne' : 'bc.canvas.why.rulesMany', { n: rules.length })] : [] },
    ]
  }

  // E14: the request this widget is waiting on. A newer fetch (a filter or
  // setting changed) or leaving the page lets go of it: still queued, it is
  // never sent; in flight, the server drops it if it has not started. It
  // also means a slow old answer can no longer overwrite a newer one.
  const inflightRef = useRef<AbortController | null>(null)
  useEffect(() => () => inflightRef.current?.abort(), [])

  const fetchData = useCallback(async (fresh = false) => {
    inflightRef.current?.abort()
    const ctl = new AbortController()
    inflightRef.current = ctl
    const signal = ctl.signal
    if (dataOverride !== undefined) { setData(dataOverride); setLoading(false); return }
    if (!widgetDatasetId) { setLoading(false); return }
    const wt = widget.widget_type
    if (wt === 'text' && /\{\{\s*(sum|avg|min|max|count|median)\(/i.test(String((widget.config as any).content ?? ''))) {
      // A text block with {{agg(column)}} placeholders is dynamic text: resolve the
      // aggregates through the same widget-data path as every chart, so filters, RLS
      // and cross-filters shape the number in prose exactly as they would in a chart.
    } else if (wt === 'text' || wt === 'button' || wt === 'image' || wt === 'shape' || wt === 'container' || wt === 'web_content') { setLoading(false); return }
    setLoading(true)
    setFetchError(null)
    const startedAt = performance.now()
    try {
      if (wt === 'text') {
        // One KPI query per distinct {{agg(column)}} pair: each returns a scalar shaped
        // by the same filters, cross-filters and RLS as any chart, so the number in
        // prose can never disagree with the chart beside it. Distinct pairs only --
        // the same placeholder repeated costs one call.
        const placeholders = [...String((widget.config as any).content ?? '')
          .matchAll(/\{\{\s*(sum|avg|min|max|count|median)\(\s*([^)\s]+)\s*\)\s*\}\}/gi)]
        const pairs = [...new Map(placeholders.map(m =>
          [`${m[1].toLowerCase()}(${m[2]})`, { agg: m[1].toLowerCase(), col: m[2] }])).values()]
        const results = await Promise.all(pairs.map(pv =>
          widgetDataApi.query(widgetDatasetId,
            { ...mergedConfig, measure: pv.col, aggregation: pv.agg === 'count' ? 'count' : pv.agg },
            effectiveCalcCols, 'kpi', { reportId, parameters, fresh, signal })))
        if (signal.aborted) return
        const values: Record<string, unknown> = {}
        const valueStyles: Record<string, { fill?: string; text?: string }> = {}
        pairs.forEach((pv, i) => {
          const key = `${pv.agg}(${pv.col})`
          values[key] = results[i]?.rows?.[0]?.value ?? results[i]?.value
          // Display rules evaluated server-side against each placeholder's
          // scalar result: the number in prose colours by the same rules as
          // the chart beside it (SAS applies display rules to dynamic text).
          const s = results[i]?.rule_styles?.rows?.[0]
          if (s) valueStyles[key] = s
        })
        // Widget-level rule outcomes (background, visibility) from the first
        // placeholder's evaluation apply to the block itself.
        setData({ type: 'text_values', values, value_styles: valueStyles,
                  rule_styles: results[0]?.rule_styles })
        onFetchComplete?.(widget.id, { durationMs: performance.now() - startedAt,
          rowCount: pairs.length, sampled: false })
        return
      }
      // Cross-HIGHLIGHT (SAS's linked selection, Power BI's default): instead
      // of filtering this widget down to the selection, show the FULL result
      // with each mark's selected share saturated -- two queries, the
      // unfiltered baseline and the selected slice, merged per category. The
      // saturated fraction IS the shared-observation percentage.
      const receiveMode = getReceiveMode(widget.id)
      if (receiveMode === 'highlight' && translatedCrossFilters.length > 0 && wt === 'bar') {
        const baseCfg = { ...mergedConfig,
          filters: (mergedConfig.filters ?? []).filter((f: any) => !translatedCrossFilters.includes(f)) }
        const [full, part] = await Promise.all([
          widgetDataApi.query(widgetDatasetId, baseCfg, effectiveCalcCols, wt, { reportId, parameters, fresh, signal }),
          widgetDataApi.query(widgetDatasetId, mergedConfig, effectiveCalcCols, wt, { reportId, parameters, fresh, signal }),
        ])
        if (signal.aborted) return
        const partMap = new Map((part?.rows ?? []).map((r: any) => [r.name, r.value]))
        setData({ ...full, rows: (full?.rows ?? []).map((r: any) => ({ ...r, highlight: partMap.get(r.name) ?? 0 })) })
        onFetchComplete?.(widget.id, {
          durationMs: performance.now() - startedAt,
          rowCount: full?.rows?.length ?? 0, sampled: !!full?.sampled,
          ruleErrors: full?.rule_errors,
        })
        return
      }
      // A raw table asks for its first page only (see TABLE_PAGE / loadMore).
      const queryConfig = !isStaticChart && isRawTable(wt, mergedConfig as Record<string, unknown>)
        ? { ...mergedConfig, page: { offset: 0, size: TABLE_PAGE } }
        : topN ? { ...mergedConfig, top_n: topN } : mergedConfig
      moreCtl.current?.abort(); setLoadingMore(false)
      const result = await widgetDataApi.query(widgetDatasetId, queryConfig, effectiveCalcCols, wt, { reportId, parameters, fresh, signal })
      if (signal.aborted) return
      setData(result)
      onFetchComplete?.(widget.id, {
        durationMs: performance.now() - startedAt,
        // Count whatever the shape actually carries: matrix results (heatmap,
        // ribbon), waterfall bars, sankey links and forecasts have no `rows` key,
        // and counting only rows reported healthy widgets as empty -- the Review
        // pane's first-ever finding was exactly that false positive.
        rowCount: result?.rows?.length
          || result?.matrix?.length || result?.cells?.length || result?.bars?.length
          || result?.links?.length || result?.forecast?.length
          || (result?.value != null ? 1 : 0) || 0,
        sampled: !!result?.sampled,
        ruleErrors: result?.rule_errors,
      })
    } catch (e: unknown) {
      if (signal.aborted || isCanceledRequest(e)) return
      setData(null)
      // The backend's own message is the useful one -- "Dataset has 2,400,000
      // rows, above the import row cap of 2,000,000. Raise `import_row_cap`, or
      // use a DirectQuery data source..." names the limit, the actual size and
      // the two remedies. Discarding it left the widget rendering "Configure
      // widget to see data", which blames the author for a configuration
      // mistake they did not make.
      const body = (e as { response?: { data?: { detail?: string; code?: string } } })
        ?.response?.data
      setFetchError(body?.detail ? { detail: body.detail, code: body.code } : null)
    }
    finally { if (!signal.aborted) setLoading(false) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [widgetDatasetId, widget.widget_type, JSON.stringify(mergedConfig), JSON.stringify(parameters ?? {}), dataOverride, getReceiveMode(widget.id), JSON.stringify(translatedCrossFilters), refreshNonce, isStaticChart, topN])

  // Opt-in periodic reload interval (used below and by the lazy-fetch gate).
  // Clamped to >= 5s: a sub-second interval is a typo that would hammer the
  // backend, and nothing on a dashboard changes that fast.
  const reloadSeconds = Number((widget.config as { auto_reload_seconds?: number }).auto_reload_seconds) || 0

  // ── Viewport-lazy fetch ────────────────────────────────────────────────────
  // A widget below the fold fetches when it approaches the viewport (300px
  // early), not on mount -- a long page stops costing its full query fan-out
  // up front. Once visible, always visible: scrolling away never un-fetches.
  // Eager (fetch-on-mount) cases: an explicit eagerFetch prop (kiosk, print,
  // export read from widgets nobody scrolled to), tooltip previews (mounted
  // only when shown), dataOverride (shared view -- no network anyway),
  // auto-reload widgets (they promised liveness), and environments without
  // IntersectionObserver (jsdom -- which is what keeps every existing test's
  // mount-then-assert-fetch flow working unchanged).
  const lazyEligible = typeof IntersectionObserver !== 'undefined'
    && !eagerFetch && !isPreview && dataOverride === undefined && reloadSeconds < 5
  const [hasBeenVisible, setHasBeenVisible] = useState(false)
  useEffect(() => {
    if (!lazyEligible || hasBeenVisible) return
    const el = widgetRootRef.current
    if (!el) { setHasBeenVisible(true); return }  // no root to observe: fetch
    const io = new IntersectionObserver(entries => {
      if (entries.some(e => e.isIntersecting)) setHasBeenVisible(true)
    }, { rootMargin: '300px' })
    io.observe(el)
    return () => io.disconnect()
  }, [lazyEligible, hasBeenVisible])

  // Refetch only when config content actually changes (or first visibility).
  // The first load goes at once. A CHANGE (a filter clicked, a slicer ticked)
  // waits FILTER_SETTLE_MS for the next one: three quick clicks used to send
  // three rounds of queries for every chart on the page, two of them for
  // selections the reader had already moved past.
  const firstFetchDone = useRef(false)
  useEffect(() => {
    if (lazyEligible && !hasBeenVisible) return
    if (!firstFetchDone.current || dataOverride !== undefined) {
      firstFetchDone.current = true
      fetchData()
      return
    }
    const id = setTimeout(() => { fetchData() }, FILTER_SETTLE_MS)
    return () => clearTimeout(id)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetchData, lazyEligible, hasBeenVisible])

  useEffect(() => {
    if (reloadSeconds < 5) return
    // fresh: a periodic reload that could be served from the client cache
    // would be a lie about liveness.
    const id = setInterval(() => fetchData(true), reloadSeconds * 1000)
    return () => clearInterval(id)
  }, [reloadSeconds, fetchData])

/** Two selections are the same when they hold the same values, so clicking the
 *  same region twice toggles it off even though each click builds a new array. */
function sameSelection(a: unknown, b: unknown[]): boolean {
  return Array.isArray(a) && a.length === b.length
    && b.every((v, i) => (a as unknown[])[i] === v)
}

  // When a user clicks a data point on THIS widget
  // The last value a reader clicked, for double-click drill: the second click
  // of a double-click toggles the selection off again, so the drill cannot
  // read `localSelected` -- it reads what was clicked.
  const lastClickedRef = useRef<{ value: unknown; at: number } | null>(null)
  // The reader's analysis kit: a local re-type, an explanation, a what-if.
  const { viewAs, setViewAs } = useViewAs(widget.id)
  const [kitDialog, setKitDialog] = useState<'explain' | 'scenario' | 'why' | 'difference' | null>(null)
  const handleClick = useCallback((name: unknown) => {
    lastClickedRef.current = { value: name, at: Date.now() }
    // A decomposition drill is navigation, not a cross-filter selection. It
    // has to be intercepted here: the cross-filter path below returns early
    // without a `dimension`, so the payload would be silently dropped.
    if (name && typeof name === 'object' && (name as any).__decomposition) {
      const p = name as { path: { field: string; value: string }[]; split_by: string | null }
      setDecompPath(p.path ?? [])
      setDecompSplit(p.split_by ?? null)
      return
    }
    // QA3 A6: while building, a click on a mark selects the widget and
    // nothing else. It used to also pick the bar under the pointer and
    // cross-filter the page. Readers (View, Present) still filter by clicking.
    if (editMode) return
    // A map area: the extent of the sites a reader circled, as latitude and
    // longitude ranges. One filter per axis, each a `{ between }` value the
    // receiving widgets turn into >= and <= (see mergedPair). Two emits, so
    // each axis has its own chip and clears on its own.
    if (name && typeof name === 'object' && (name as any).area) {
      if (!canBroadcast(widget.id)) return
      const { lat, lon } = (name as { area: { lat: [number, number]; lon: [number, number] } }).area
      const c = widget.config as any
      const latCol = c.lat ?? c.roles?.lat, lonCol = c.lon ?? c.roles?.lon
      if (!latCol || !lonCol) return
      const fmt = (v: number) => String(Math.round(v * 10000) / 10000)
      emitFilter(widget.id, widget.page_id, latCol, { between: lat }, `${latCol} ${fmt(lat[0])} – ${fmt(lat[1])}`)
      emitFilter(widget.id, widget.page_id, lonCol, { between: lon }, `${lonCol} ${fmt(lon[0])} – ${fmt(lon[1])}`)
      return
    }
    if (!canBroadcast(widget.id)) return
    const cfg = widget.config as any
    // The column the clicked mark stands for. `start` is the grouping role of
    // the dual-axis time series; `roles.category` is a config saved with the
    // roles model. Missing either made those charts' clicks vanish silently.
    const col = cfg.dimension ?? cfg.column ?? cfg.roles?.category ?? cfg.start ?? null
    if (!col) return
    // A SET of values rather than one: a map region two spellings merged into,
    // or a shift-drag that circled several points. It goes through the same
    // toggle and the same gate; only the shape differs, and `emitMultiFilter`
    // is what the slicer already uses for exactly this.
    if (Array.isArray(name)) {
      const label = name.length === 1
        ? `${col} = ${name[0]}` : `${col}: ${name.length} selected`
      setLocalSelected(sameSelection(localSelected, name) ? null : name)
      emitMultiFilter(widget.id, widget.page_id, col, name, label)
      return
    }
    // A grouped number range ("500 – 1,000") is not a value of the column:
    // the other charts are filtered to the range it stands for. Date buckets
    // need nothing here -- their labels are the ones the server already reads
    // as a grain (infer_date_filter_grains).
    const shownBin = (zoom?.data ?? data) as { binning?: Binning; rows?: StripRowLike[] } | null
    // "All Other" is not a value of the column: filtering the page to it would
    // blank every other chart. It stays a slice to read, not to click.
    if (shownBin?.binning?.kind === 'text' && shownBin.rows?.some(r => r.name === name && (r as { other?: boolean }).other)) return
    if (shownBin?.binning?.grouped && shownBin.binning.kind === 'number' && shownBin.binning.column === col) {
      const row = shownBin.rows?.find(r => r.name === name)
      if (row && typeof row.bin_start === 'number' && typeof row.bin_end === 'number') {
        setLocalSelected(localSelected === name ? null : name)
        emitFilter(widget.id, widget.page_id, col, { between: [row.bin_start, row.bin_end] }, `${col} ${String(name)}`)
        return
      }
    }
    // Toggle: clicking the same value clears the filter
    if (localSelected === name) {
      setLocalSelected(null)
      emitFilter(widget.id, widget.page_id, col, name, `${col} = ${name}`)  // emitFilter toggles on repeat
    } else {
      setLocalSelected(name)
      emitFilter(widget.id, widget.page_id, col, name, `${col} = ${name}`)
    }
    if (hierarchyNodeId != null && hierarchy && currentNodeId != null && currentNode?.column_name) {
      const child = getChildNode(hierarchy, currentNodeId)
      if (child) {
        setExpandDepth(0)
        setDrillPath(p => [...p, { column: currentNode.column_name!, granularity: currentNode.format, value: name, label: String(name) }])
      }
    }
  }, [canBroadcast, widget.id, widget.config, localSelected, emitFilter, emitMultiFilter, hierarchyNodeId, hierarchy, currentNodeId, currentNode, binning, baseRows, zoom, editMode])

  const commitZoom = useCallback((a: number, b: number) => {
    zoomCtl.current?.abort()
    if (!smartZoom || !baseRows || !widgetDatasetId) return
    if (a <= 0 && b >= baseRows.length - 1) {
      setZoomSel(null); setZoom(null); setZoomLoading(false); setBrushRange(null)
      return
    }
    const ctl = new AbortController()
    zoomCtl.current = ctl
    setZoomLoading(true)
    const bin_range = { start: baseRows[a].bin_start, end: baseRows[b].bin_end }
    widgetDataApi.query(widgetDatasetId, { ...mergedConfig, bin_range }, effectiveCalcCols,
      widget.widget_type, { reportId, parameters, signal: ctl.signal })
      .then(res => { if (!ctl.signal.aborted) setZoom({ a, b, data: res }) })
      .catch(() => { /* the coarse window stays on screen: nothing is lost */ })
      .finally(() => { if (!ctl.signal.aborted) setZoomLoading(false) })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [smartZoom, baseRows, widgetDatasetId, JSON.stringify(mergedConfig), JSON.stringify(effectiveCalcCols), widget.widget_type, reportId, JSON.stringify(parameters ?? {})])

  /** The next page of a paged raw table, appended when the reader scrolls
   *  near the bottom. One request at a time; a new base fetch cancels it. */
  const loadMore = useCallback(() => {
    const d = data as { page?: unknown; rows?: unknown[]; total?: number } | null
    if (!d?.page || loadingMore || !widgetDatasetId) return
    const have = d.rows?.length ?? 0
    if (have >= (d.total ?? 0)) return
    const ctl = new AbortController()
    moreCtl.current = ctl
    setLoadingMore(true)
    widgetDataApi.query(widgetDatasetId, { ...mergedConfig, page: { offset: have, size: TABLE_PAGE } },
      effectiveCalcCols, 'table', { reportId, parameters, signal: ctl.signal })
      .then(res => {
        if (ctl.signal.aborted) return
        setData((prev: any) => prev?.page && (prev.rows?.length ?? 0) === have ? mergeTablePage(prev, res, have) : prev)
      })
      .catch(() => { /* the rows already on screen stay; the next scroll retries */ })
      .finally(() => { if (!ctl.signal.aborted) setLoadingMore(false) })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, loadingMore, widgetDatasetId, JSON.stringify(mergedConfig), JSON.stringify(effectiveCalcCols), reportId, JSON.stringify(parameters ?? {})])

  const onZoomDrag = useCallback((a: number, b: number) => {
    if (!baseRows) return
    const whole = a <= 0 && b >= baseRows.length - 1
    setZoomSel(whole ? null : { a, b })
    setBrushRange(whole ? null : {
      start: String(baseRows[a].name ?? a), end: String(baseRows[b].name ?? b),
      startIndex: a, endIndex: b, of: baseRows.length,
    })
  }, [baseRows])

  // The reset button on the "zoomed" chip clears the smart zoom too.
  useEffect(() => {
    if (!brushNonce) return
    zoomCtl.current?.abort()
    setZoomSel(null); setZoom(null); setZoomLoading(false)
  }, [brushNonce])

  //: What a text control currently filters by. The input is uncontrolled and
  //: this is the mirror: re-rendering on every keystroke would move the caret.
  const [textFilter, setTextFilter] = useState('')

  /** A typed value becomes this widget's filter. An EMPTY box clears it rather
   *  than filtering on "" — which would match nothing and read as a page that
   *  had broken rather than one with no filter. */
  const handleSubmitTextFilter = useCallback((value: string, column: string) => {
    setTextFilter(value)
    if (!column) return
    if (value) emitFilter(widget.id, widget.page_id, column, value, `${column} = ${value}`)
    else clearFilter(column, widget.id)
  }, [widget.id, widget.page_id, emitFilter, clearFilter])

  /** A range slicer's bounds, read back from the page's filters so a chip
   *  cleared elsewhere empties the boxes too. */
  const rangeFilter = useMemo((): RangeValue | null => {
    const mine = activeFilters.find(f => f.sourceWidgetId === widget.id
      && Array.isArray((f.value as { between?: unknown } | null)?.between))
    return mine ? (mine.value as { between: RangeValue }).between : null
  }, [activeFilters, widget.id])

  /** Bounds become one `between` filter; an open end is null. Both empty
   *  clears it, like an empty text box. */
  const handleSubmitRangeFilter = useCallback((range: RangeValue | null, column: string) => {
    if (!column) return
    if (!range) { clearFilter(column, widget.id); return }
    emitFilter(widget.id, widget.page_id, column, { between: range }, rangeLabel(column, range))
  }, [widget.id, widget.page_id, emitFilter, clearFilter])

  // Slicer: toggling a checkbox re-emits the full checked set as a multi-value filter.
  const handleToggleSlicerValue = useCallback((value: unknown) => {
    const next = new Set(checked)
    next.has(value) ? next.delete(value) : next.add(value)
    setChecked(next)
    const cfg = widget.config as any
    const col = cfg.dimension ?? cfg.column ?? null
    if (!col) return
    const values = Array.from(next)
    // Unticking the LAST value is "no filter", not "filter on nothing". Emitting
    // the empty set left a chip reading `region in ()` on the page and handed
    // every receiving widget an impossible predicate, so tiles went blank and
    // one fell back to its unconfigured placeholder. Same guard the text filter
    // above already has.
    if (values.length === 0) { clearFilter(col, widget.id); return }
    emitMultiFilter(widget.id, widget.page_id, col, values, `${col} in (${values.join(', ')})`)
  }, [checked, widget.id, widget.page_id, widget.config, emitMultiFilter, clearFilter])

  // Clear local selection when our own emitted filter is cleared externally
  useEffect(() => {
    const ours = activeFilters.filter(f => f.sourceWidgetId === widget.id)
    if (ours.length === 0) setLocalSelected(null)
  }, [activeFilters, widget.id])

  // Tooltip-page hover preview — a floating panel rendering another page's widgets.
  // Never wired on isPreview instances, which caps recursion at one level.
  const tooltipPageId = (mergedConfig as { tooltipPageId?: number }).tooltipPageId
  const tooltipPage = !isPreview && tooltipPageId ? pages?.find(p => p.id === tooltipPageId) : undefined
  const [showTooltipPreview, setShowTooltipPreview] = useState(false)
  const [previewPos, setPreviewPos] = useState({ x: 0, y: 0 })
  const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const handleMouseEnter = (e: React.MouseEvent) => {
    if (!tooltipPage) return
    const x = Math.max(8, Math.min(e.clientX + 12, window.innerWidth  - PREVIEW_W - 8))
    const y = Math.max(8, Math.min(e.clientY + 12, window.innerHeight - PREVIEW_H - 8))
    setPreviewPos({ x, y })
    hoverTimer.current = setTimeout(() => setShowTooltipPreview(true), 150)
  }
  const handleMouseLeave = () => {
    if (hoverTimer.current) clearTimeout(hoverTimer.current)
    setShowTooltipPreview(false)
  }

  const drillthroughPageId = (mergedConfig as { drillthroughPageId?: number }).drillthroughPageId
  const drillthroughTargetName = pages?.find(p => p.id === drillthroughPageId)?.name
  const handleDrillthrough = () => {
    if (drillthroughPageId != null && localSelected != null) onDrillthrough?.(drillthroughPageId, localSelected)
  }

  // Right-click context menu — mirrors the header button's drill-through action, closer to
  // Power BI's actual right-click-a-data-point trigger.
  const [showContextMenu, setShowContextMenu] = useState(false)
  const [reconcileOpen, setReconcileOpen] = useState(false)
  const t = useT()
  const L = usePanelLabel()
  const { language } = useDirection()
  const [contextMenuPos, setContextMenuPos] = useState({ x: 0, y: 0 })
  useEffect(() => {
    if (!showContextMenu) return
    const close = () => setShowContextMenu(false)
    document.addEventListener('click', close)
    return () => document.removeEventListener('click', close)
  }, [showContextMenu])
  const menuItemStyle: React.CSSProperties = {
    display: 'block', width: '100%', textAlign: 'start', background: 'none', border: 'none',
    padding: '6px 10px', fontSize: 12, color: 'var(--text)', cursor: 'pointer',
    whiteSpace: 'nowrap', borderRadius: 4,
  }

  const canDrillthrough = drillthroughPageId != null && localSelected != null

  const handleExport = async (format: 'csv' | 'xlsx') => {
    setShowContextMenu(false)
    if (widgetDatasetId == null) return
    try {
      await widgetDataApi.export(widgetDatasetId, mergedConfig, wt, format, effectiveCalcCols)
    } catch {
      toast.error(t('bc.canvas.exportFailed'))
    }
  }

  const widgetRootRef = useRef<HTMLDivElement>(null)

  const handleExportImage = async () => {
    setShowContextMenu(false)
    const svg = pickChartSvg(widgetRootRef.current)
    if (!svg) { toast.error(t('bc.canvas.noChartToExport')); return }
    try {
      const { dataUrl, dropped } = await svgToPng(svg, 2)
      const a = document.createElement('a')
      a.href = dataUrl
      a.download = `${(widget.title || wt).replace(/[^A-Za-z0-9 _-]/g, '').slice(0, 60) || 'widget'}.png`
      a.click()
      if (dropped > 0) {
        toast(t('bc.canvas.mapTilesDropped'))
      }
    } catch {
      toast.error(t('bc.canvas.exportImageFailed'))
    }
  }

  const handleContextMenu = (e: React.MouseEvent) => {
    // Opens when there is anything to offer -- and copy-link applies to EVERY
    // widget (a text block is as linkable as a chart), so only previews opt out.
    if (isPreview) return
    e.preventDefault()
    e.stopPropagation()
    setContextMenuPos({ x: e.clientX, y: e.clientY })
    setShowContextMenu(true)
  }

  // The keyboard's way to the same menu: the context-menu key or Shift+F10,
  // opened at the widget's corner. Only 2 of 12 widgets on a dashboard could
  // be reached by Tab at all, and none could open its menu (live QA 2026-09-28).
  const handleFigureKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (isPreview || e.target !== e.currentTarget) return
    if (e.key === 'ContextMenu' || (e.key === 'F10' && e.shiftKey)) {
      e.preventDefault()
      const box = e.currentTarget.getBoundingClientRect()
      setContextMenuPos({ x: box.left + 16, y: box.top + 16 })
      setShowContextMenu(true)
    }
  }

  const handleButtonClick = () => {
    const cfg = widget.config as any
    if (cfg.action === 'navigate' && cfg.actionPageId != null) {
      // "Carry my selections": the reader arrives on the target page filtered
      // the way they left this one (per link, the author's choice).
      if (cfg.carry_filters) carryFiltersTo(widget.page_id, Number(cfg.actionPageId))
      onNavigateToPage?.(cfg.actionPageId)
    } else if (cfg.action === 'url' && cfg.actionUrl) {
      // The URL is author-stored config, i.e. persisted client input. Parsing and
      // allowlisting the scheme is what keeps a stored `javascript:` URL from being
      // an XSS that fires on a click in view mode. noopener/noreferrer severs the
      // opener handle so the target page cannot script this one.
      //
      // {{@name}} placeholders substitute the live report-parameter value
      // (SAS parameterises link URLs from a bound data value; parameters are
      // that binding here). Values are URL-ENCODED before splicing, and the
      // scheme allowlist runs on the SUBSTITUTED result -- a parameter value
      // must never be able to rewrite the protocol.
      try {
        const raw = String(cfg.actionUrl).replace(
          /\{\{\s*@([A-Za-z_][A-Za-z0-9_]*)\s*\}\}/g,
          (_, name: string) => encodeURIComponent(String(parameters?.[name] ?? '')))
        const url = new URL(raw, window.location.href)
        if (url.protocol === 'http:' || url.protocol === 'https:') {
          window.open(url.href, '_blank', 'noopener,noreferrer')
        }
      } catch { /* an unparseable URL does nothing, matching a button with no action */ }
    } else if (cfg.action === 'report' && cfg.actionReportId != null) {
      // Cross-report link. Number() strips anything an edited config could smuggle
      // into the path; the target report enforces its own permissions on arrival.
      const id = Number(cfg.actionReportId)
      if (Number.isFinite(id) && id > 0) window.location.assign(`/reports/${id}`)
    } else if (cfg.action === 'set_param' && cfg.actionParamName) {
      onSetParameter?.(String(cfg.actionParamName), String(cfg.actionParamValue ?? ''))
    } else if (cfg.action === 'bookmark' && cfg.actionBookmarkId != null) {
      const bookmark = bookmarks?.find(b => b.id === cfg.actionBookmarkId)
      if (bookmark) {
        clearAllFilters()
        bookmark.state.activeFilters.forEach(f =>
          Array.isArray(f.value)
            ? emitMultiFilter(f.sourceWidgetId, f.sourcePageId, f.column, f.value, f.label)
            : emitFilter(f.sourceWidgetId, f.sourcePageId, f.column, f.value, f.label)
        )
        onApplyBookmark?.(bookmark)
      }
    }
  }

  const wt = widget.widget_type
  const title = widget.title || wt
  const broadcasts = canBroadcast(widget.id)
  const receives   = canReceive(widget.id)

  const allFormats = useMemo<Record<string, CalcColumnFormat | undefined>>(() => {
    const calcFmts = Object.fromEntries(
      effectiveCalcCols.filter(c => c.format).map(c => [c.name, c.format])
    )
    return { ...effectiveFormats, ...calcFmts }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(effectiveCalcCols), JSON.stringify(effectiveFormats)])

  const ruleStyles = data?.rule_styles as RuleStyles | undefined
  const hiddenByRule = !!ruleStyles?.widget?.hidden
  const cfg = widget.config as any

  // A rule-hidden widget in view mode renders nothing at all -- not the frame (border,
  // title, header) around an empty body, which would read as a broken widget rather
  // than an intentionally hidden one. Edit mode still renders the full frame with the
  // "Hidden by a display rule" placeholder body below, so an author can select and
  // reconfigure whatever the rule would hide; view mode is the only audience this rule
  // needs to be invisible to.
  if (!loading && hiddenByRule && !editMode) return null

  // ── Containers ─────────────────────────────────────────────────────────────
  // A container renders the page widgets whose config.container_id points at it,
  // positioned on the container's own 12-column grid. The canvas skips those same
  // widgets at top level, so each child renders exactly once.
  const containerChildren = wt === 'container'
    ? (pages?.find(p => p.id === widget.page_id)?.widgets ?? [])
        .filter(w => (w.config as { container_id?: number })?.container_id === widget.id)
    : []

  if (wt === 'container') {
    const mode = ((cfg.container_mode as string) || 'group')
    // Same embeddable rule the image and custom-visual widgets apply: an
    // http(s) URL or a same-origin path, never a javascript: or data: source.
    const rawBackground = typeof cfg.background_url === 'string'
      ? cfg.background_url.trim() : ''
    const precisionBackground = (/^https?:\/\//i.test(rawBackground)
      || rawBackground.startsWith('/')) ? rawBackground : ''
    const cell = 100 / 12
    const renderChild = (w: typeof widget) => (
      <WidgetRenderer key={w.id}
        widget={w} datasetId={datasetId} calculatedColumns={calculatedColumns}
        columnFormats={columnFormats} geography={geography} datasets={datasets} editMode={editMode}
        promptFilter={promptFilter} pages={pages} reportDisplayRules={reportDisplayRules} reportFilters={reportFilters}
        onDrillthrough={onDrillthrough} hierarchy={hierarchy} bookmarks={bookmarks}
        onNavigateToPage={onNavigateToPage} onApplyBookmark={onApplyBookmark}
        reportId={reportId} parameters={parameters}
        onSelect={onSelect ? (e) => onSelect(e) : undefined}
      />
    )
    const sorted = [...containerChildren].sort((a, b) =>
      ((a.layout?.y ?? 0) - (b.layout?.y ?? 0)) || ((a.layout?.x ?? 0) - (b.layout?.x ?? 0)))
    const title = widget.title || 'Container'
    return (
      <div role="group" aria-label={title} onClick={e => onSelect?.(e)} onContextMenu={handleContextMenu}
        style={{ height: '100%', display: 'flex', flexDirection: 'column',
          border: selected ? '2px solid var(--accent)' : '1px solid var(--border)',
          borderRadius: 'var(--radius)', background: 'var(--surface)', overflow: 'hidden' }}>
        {mode === 'tabs' ? (
          <>
            <div role="tablist" style={{ display: 'flex', gap: 2, borderBottom: '1px solid var(--border)', padding: '4px 6px 0' }}>
              {sorted.map((w, i) => (
                <button key={w.id} role="tab" aria-selected={i === containerTab}
                  onClick={e => { e.stopPropagation(); setContainerTab(i) }}
                  style={{ padding: '4px 10px', fontSize: 11, border: 'none', cursor: 'pointer',
                    background: 'none', color: i === containerTab ? 'var(--text)' : 'var(--muted)',
                    borderBottom: `2px solid ${i === containerTab ? 'var(--accent)' : 'transparent'}` }}>
                  {w.title || w.widget_type}
                </button>
              ))}
            </div>
            <div style={{ flex: 1, minHeight: 0 }}>
              {sorted[Math.min(containerTab, Math.max(0, sorted.length - 1))]
                ? renderChild(sorted[Math.min(containerTab, sorted.length - 1)]) : null}
            </div>
          </>
        ) : mode === 'prompt' ? (
          <>
            <button type="button" aria-expanded={containerOpen}
              onClick={e => { e.stopPropagation(); setContainerOpen(o => !o) }}
              style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 10px',
                background: 'none', border: 'none', borderBottom: containerOpen ? '1px solid var(--border)' : 'none',
                color: 'var(--muted)', cursor: 'pointer', font: 'inherit', fontSize: 11, fontWeight: 600 }}>
              <span aria-hidden style={{ transform: containerOpen ? 'rotate(90deg)' : 'none', display: 'inline-block', transition: 'transform .12s' }}>▶</span>
              {title}
            </button>
            {containerOpen && (
              <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8, padding: 8 }}>
                {sorted.map(w => <div key={w.id} style={{ minHeight: 120 }}>{renderChild(w)}</div>)}
              </div>
            )}
          </>
        ) : mode === 'precision' ? (
          /* Precision: overlapping objects positioned freely over a background.
             Children were ALREADY placed absolutely by `group`, so overlap was
             always possible -- what a precision layout adds is something to
             position over, and a stacking order, since two overlapping widgets
             with no z sit in whatever order the sort produced. */
          <div style={{ flex: 1, minHeight: 0, position: 'relative', overflow: 'hidden' }}>
            {precisionBackground && (
              <div data-precision-background aria-hidden style={{
                position: 'absolute', inset: 0,
                backgroundImage: `url(${precisionBackground})`,
                backgroundSize: 'contain', backgroundRepeat: 'no-repeat',
                backgroundPosition: 'center',
              }} />
            )}
            {sorted.length === 0 && (
              <div style={{ position: 'absolute', inset: 0, display: 'flex',
                alignItems: 'center', justifyContent: 'center',
                color: 'var(--muted)', fontSize: 11 }}>
                {t('bc.canvas.containerEmpty')}
              </div>
            )}
            {sorted.map(w => {
              const l = w.layout ?? { x: 0, y: 0, w: 6, h: 4 }
              // Zero when unset: document order is an accident of the sort, and
              // treating it as intent would make "bring to front" mean whatever
              // the sort happened to do that render.
              const z = Number((w.config as { z?: unknown })?.z) || 0
              return (
                <div key={w.id} data-precision-child style={{ position: 'absolute',
                  left: `${l.x * cell}%`, width: `${l.w * cell}%`,
                  top: l.y * 62, height: l.h * 56, zIndex: z }}>
                  {renderChild(w)}
                </div>
              )
            })}
          </div>
        ) : (
          /* group and scroll share the grid layout; scroll allows overflow. */
          <div style={{ flex: 1, minHeight: 0, position: 'relative',
            overflowY: mode === 'scroll' ? 'auto' : 'hidden' }}>
            {sorted.length === 0 && (
              <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center',
                justifyContent: 'center', color: 'var(--muted)', fontSize: 11 }}>
                {t('bc.canvas.containerEmpty')}
              </div>
            )}
            {sorted.map(w => {
              const l = w.layout ?? { x: 0, y: 0, w: 6, h: 4 }
              return (
                <div key={w.id} style={{ position: 'absolute',
                  left: `${l.x * cell}%`, width: `${l.w * cell}%`,
                  top: l.y * 62, height: l.h * 56 }}>
                  {renderChild(w)}
                </div>
              )
            })}
            {mode === 'scroll' && sorted.length > 0 && (
              <div style={{ height: Math.max(0, ...sorted.map(w => ((w.layout?.y ?? 0) + (w.layout?.h ?? 4)) * 62 + 10)) }} />
            )}
          </div>
        )}
      </div>
    )
  }

  return (
    <div
      ref={widgetRootRef}
      className={`dl-widget${selected ? ' dl-widget--selected' : ''}`}
      role="figure"
      aria-label={(cfg.alt_text as string) || widget.title || wt}
      tabIndex={isPreview ? undefined : 0}
      onKeyDown={handleFigureKeyDown}
      onClick={e => onSelect?.(e)}
      onContextMenu={handleContextMenu}
      onMouseEnter={tooltipPage ? handleMouseEnter : undefined}
      onMouseLeave={tooltipPage ? handleMouseLeave : undefined}
      style={{
        height: '100%', width: '100%', minWidth: 0, minHeight: 0,
        display: 'flex', flexDirection: 'column',
        // A transparent object draws no panel and no border, so a page
        // background shows through it -- how a chart, a headline number and a
        // line plot sit directly on a photograph. Opt-in: every dashboard that
        // exists was authored against the card look. The selection ring still
        // wins, or an author could not see what they had clicked.
        border: selected
          ? '2px solid var(--accent)'
          : cfg.transparent === true
            ? '0 solid transparent'
            : `${cfg.widget_border_width ?? 1}px solid ${cfg.widget_border_color ?? 'var(--border)'}`,
        borderRadius: cfg.widget_radius != null ? cfg.widget_radius : 'var(--radius)',
        // A rule background beats a static one: the rule reacts to the data, which is
        // the entire point of phase 1's `background` target.
        background: ruleStyles?.widget?.background ?? cfg.widget_background
          ?? (cfg.transparent === true ? 'transparent' : 'var(--surface)'),
        // QA3 B4: the header controls paint on the widget's own colour, not a
        // white (surface) box over a custom one. Transparent tiles keep surface.
        ['--dl-wbg' as string]: (() => { const bg = ruleStyles?.widget?.background ?? cfg.widget_background
          return bg && bg !== 'transparent' ? bg : 'var(--surface)' })(),
        overflow: 'hidden', cursor: 'default',
        boxShadow: isDragging ? '0 8px 24px rgba(0,0,0,.25)' : selected ? '0 0 0 3px color-mix(in srgb, var(--accent) 20%, transparent)' : skinShadow(cfg.widget_skin),
        outline: isMultiSelected ? '2px solid var(--success)' : undefined,
        opacity: isDragging ? 0.7 : 1,
        transition: isDragging ? 'none' : 'border-color .15s, box-shadow .15s',
        position: 'relative',
        userSelect: 'none',
      }}
    >
      {/* Header — drag handle in edit mode */}
      <div
        // A press that starts on one of the header's own controls (delete, the
        // ⋮ menu, drill-through, hierarchy arrows) is a click, not a drag. The
        // pointer capture below otherwise retargets the release -- and so the
        // click -- to this div, and the buttons never fire (QA 2026-09-26).
        onMouseDown={editMode && onDragStart ? e => {
          if (isHeaderControl(e.target)) return
          e.stopPropagation(); onDragStart(e)
        } : undefined}
        onPointerDown={editMode && onDragStart ? e => {
          if (isHeaderControl(e.target)) return
          e.stopPropagation()
          try { e.currentTarget.setPointerCapture(e.pointerId) } catch { /* jsdom */ }
          onDragStart(e)
        } : undefined}
        className="dl-whead"
        // No rule under the header: title and chart read as one card, the way
        // the reference design sets them; the space does the separating.
        style={{
          padding: '12px 14px 4px',
          display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0, position: 'relative',
          cursor: editMode && onDragStart ? 'grab' : 'default',
          background: isDragging ? 'color-mix(in srgb, var(--accent) 6%, transparent)' : undefined,
        }}
      >
        {editMode && onDragStart && (
          <span style={{ color: 'var(--border)', fontSize: 12, lineHeight: 1, letterSpacing: 1, flexShrink: 0 }}>⠿</span>
        )}
        {/* A real heading, not a styled span: screen-reader users navigate a report by
            its headings, and a page of anonymous spans gives them nothing to jump
            between. Level 3 sits under the report name and page title. */}
        {/* One line, sentence case, ellipsis -- the full title rides on the
            tooltip. Uppercase with tracking made "Revenue, cost and units"
            wrap to four lines in a quarter-width tile and pushed the chart
            below the fold of its own card. */}
        <span className="dl-whead__title" style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
          <span role="heading" aria-level={3} title={title} dir="auto"
            style={{ fontWeight: 600, fontSize: 14, lineHeight: 1.3, color: 'var(--text)', minWidth: 0,
              whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{title}</span>
          {typeof cfg.subtitle === 'string' && cfg.subtitle && (
            <span data-testid="widget-subtitle" title={cfg.subtitle}
              style={{ fontSize: 12, lineHeight: 1.35, color: 'var(--muted)', whiteSpace: 'nowrap',
                overflow: 'hidden', textOverflow: 'ellipsis' }}>{cfg.subtitle}</span>
          )}
        </span>
        {/* Pipeline phase 2: the data behind this chart stopped refreshing,
            or is past its freshness target. The chart still draws the last
            good data -- this says so, and since when. */}
        {(data as { data_health?: { state: string; last_refreshed_at: string | null } } | null)?.data_health && (() => {
          const h = (data as { data_health: { state: string; last_refreshed_at: string | null } }).data_health
          const failing = h.state === 'failing'
          const since = h.last_refreshed_at ? formatDate(h.last_refreshed_at) : null
          return (
            <span data-testid="data-health-chip" role="status"
              title={t(failing ? 'health.tip.failing' : 'health.tip.stale')
                + (since ? ` ${t('health.tip.since', { when: since })}` : '')}
              style={{ fontSize: 9, padding: '1px 5px', borderRadius: 99, whiteSpace: 'nowrap',
                background: failing ? 'rgba(226,96,108,.16)' : 'rgba(230,160,60,.18)',
                color: failing ? 'color-mix(in oklab, #e2606c 75%, var(--text))' : 'color-mix(in oklab, #e6a03c 70%, var(--text))' }}>
              {t(failing ? 'health.chip.failing' : 'health.chip.stale')}
            </span>
          )
        })()}
        {data?.sampled && (
          <span title={t('bc.canvas.sampleTitle', { n: String(data.sample_size), total: String(data.total_rows) })}
            style={{ fontSize: 9, background: 'rgba(230,160,60,.18)', color: '#e6a03c', padding: '1px 5px', borderRadius: 99 }}>
            {t('bc.canvas.sampled')}
          </span>
        )}
        {binning?.grouped && (
          <span data-testid="binning-chip" title={binningTitle(zoom?.data?.binning ?? binning, t)}
            style={{ fontSize: 9, padding: '1px 5px', borderRadius: 99, whiteSpace: 'nowrap',
              background: 'color-mix(in srgb, var(--accent) 14%, transparent)', color: 'var(--accent)' }}>
            {binning.kind === 'text' && binning.top_n_choices?.length ? (
              <select aria-label={t('bc.canvas.topNAria')} data-testid="top-n-select"
                value={binning.top_n ?? ''} onClick={e => e.stopPropagation()}
                onChange={e => setTopN(Number(e.target.value))}
                style={{ font: 'inherit', color: 'inherit', background: 'transparent', border: 0, padding: 0, cursor: 'pointer' }}>
                {binning.top_n_choices.map(n => <option key={n} value={n}>{t('bc.canvas.bin.topN', { n })}</option>)}
              </select>
            ) : binningLabel(zoom?.data?.binning ?? binning, t)}
          </span>
        )}
        {brushRange && (
          <span data-testid="brush-chip" title={t(brushRange.auto ? 'bc.canvas.brushTitleAuto' : 'bc.canvas.brushTitleZoom',
              { start: String(brushRange.start), end: String(brushRange.end), of: brushRange.of })}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: 9, padding: '1px 4px 1px 5px', borderRadius: 99,
              background: 'color-mix(in srgb, var(--accent) 14%, transparent)', color: 'var(--accent)', whiteSpace: 'nowrap' }}>
            {t(brushRange.auto ? 'bc.canvas.chipShowing' : 'bc.canvas.chipZoomed')} <bdi dir="ltr">{brushRange.endIndex - brushRange.startIndex + 1}/{brushRange.of}</bdi>
            {/* An automatic window has nothing to reset: the slider is the
                control. A dragged one goes back to how the chart opened. */}
            {!brushRange.auto && (
            <button aria-label={t('bc.canvas.resetZoom')} title={t('bc.canvas.resetZoomTitle')}
              onClick={e => { e.stopPropagation(); setBrushRange(null); setBrushNonce(n => n + 1) }}
              style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', font: 'inherit', lineHeight: 1, padding: 0 }}>×</button>
            )}
          </span>
        )}
        {relNotes.length > 0 && (
          <span data-testid="relative-date-chip"
            title={relNotes.map(n => n.error ? `${n.column}: ${n.error}` : `${n.column} — ${n.text ?? n.label}`).join('\n')}
            style={{ fontSize: 9, padding: '1px 5px', borderRadius: 99, whiteSpace: 'nowrap',
              background: relNotes.some(n => n.error || n.incomplete) ? 'rgba(230,160,60,.18)' : 'color-mix(in srgb, var(--accent) 14%, transparent)',
              color: relNotes.some(n => n.error || n.incomplete) ? '#b7791f' : 'var(--accent)' }}>
            {relNotes[0].error ? t('bc.canvas.dateFilterError') : relNotes[0].label}
            {relNotes.some(n => n.incomplete) ? ' · ' + t('bc.canvas.partial') : ''}
          </span>
        )}
        {incomingFilters.length > 0 && (
          <span title={t('bc.canvas.filteredBy', { list: incomingFilters.map(f => f.label).join(', ') })}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: 9, background: 'color-mix(in srgb, var(--accent) 20%, transparent)', color: 'var(--accent)', padding: '1px 4px 1px 5px', borderRadius: 99 }}>
            {t(incomingFilters.length > 1 ? 'bc.canvas.chipFiltersN' : 'bc.canvas.chipFilters1', { n: incomingFilters.length })}
            <button aria-label={t('bc.canvas.clearFilter')} title={t('bc.canvas.clearFilter')}
              style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', font: 'inherit', lineHeight: 1, padding: 0 }}
              onClick={e => {
                e.stopPropagation()
                for (const f of incomingFilters) clearFilter(f.column, f.sourceWidgetId)
              }}>
              ×
            </button>
          </span>
        )}
        {!isPreview && drillthroughPageId != null && localSelected != null && (
          <button title={t('bc.canvas.drillThroughTitle')}
            style={{ fontSize: 9, background: 'color-mix(in srgb, var(--accent) 15%, transparent)', color: 'var(--accent)', border: 'none', borderRadius: 99, padding: '2px 7px', cursor: 'pointer' }}
            onClick={e => { e.stopPropagation(); handleDrillthrough() }}>
            ⤷ {t('bc.canvas.drillThrough')}
          </button>
        )}
        {/* Pinning used to send a widget to a personal dashboard rendered on
            the Datasets page. That section is gone, so the button promised a
            destination nothing displays. `pinsApi` and its endpoints survive
            untouched, ready for a surface that actually shows them. */}
        {/* The header's controls ride on top of its end edge and appear when
            the pointer, the keyboard focus or the selection is on this widget.
            Laid out inline they took ~90px of every header, so in a quarter-
            width tile "Total revenue" printed as "Tot…"; now the title owns the
            row at rest. Touch screens get them outright (index.css). */}
        <span className="dl-whead__ctl">
        {broadcasts && <span className="dl-wmark" title={t('bc.canvas.emits')} style={{ fontSize: 9, color: 'var(--accent)', opacity: .7 }}>→</span>}
        {receives && <span className="dl-wmark" title={t('bc.canvas.receives')} style={{ fontSize: 9, color: 'var(--accent)', opacity: .7 }}>←</span>}
        {!editMode && !isPreview && widgetDatasetId != null && !['text', 'button', 'image', 'shape', 'web_content', 'container', 'slicer'].includes(widget.widget_type) && (() => {
          const cfgAny = mergedConfig as Record<string, unknown>
          const cols = datasets?.[widgetDatasetId]?.columns ?? []
          const rowsNow = Array.isArray((data as { rows?: unknown[] } | null)?.rows) ? (data as { rows: unknown[] }).rows.length : 0
          const options = viewAsOptions(widget.widget_type, cfgAny, cols, rowsNow)
          const measure = typeof cfgAny.measure === 'string' ? cfgAny.measure : null
          const numericCols = cols.filter(c => c.dtype === 'numeric' && c.name !== measure).map(c => c.name)
          // A saved measure is an expression over groups, not a row column: there are no
          // per-row values behind it to test.
          const measureNames = new Set(((datasets?.[widgetDatasetId] as { measures?: { name: string }[] } | undefined)?.measures ?? []).map(m => m.name))
          // A share link or embed hands the widget its data (`dataOverride`)
          // and has no session to run an analysis with: it gets the parts
          // that need no request -- the transparency pane and re-typing.
          const live = dataOverride === undefined
          const items = [
            // QA2 T11: the menu's words in the reader's language (labels only).
            { key: 'why', label: t('wr.menu.why'), onSelect: () => setKitDialog('why') },
            ...(measure && live ? [{ key: 'explain', label: t('wr.menu.explain', { m: measure }), onSelect: () => setKitDialog('explain') }] : []),
            ...(live && DIFFERENCE_TYPES.includes(widget.widget_type) && typeof cfgAny.dimension === 'string'
                && !cfgAny.dimension2 && rowsNow >= 2 && String(cfgAny.aggregation ?? 'sum') !== 'max'
                && String(cfgAny.aggregation ?? 'sum') !== 'min' && !(measure && measureNames.has(measure))
              ? [{ key: 'difference', label: t('wr.menu.difference'), onSelect: () => setKitDialog('difference') }] : []),
            ...(live && widget.widget_type === 'forecast' && measure && numericCols.length
              ? [{ key: 'whatif', label: t('wr.menu.whatif'), onSelect: () => setKitDialog('scenario') }] : []),
            ...options.map(o => ({ key: `as-${o.type}`, label: t(o.recommended ? 'wr.menu.viewAsRec' : 'wr.menu.viewAs', { chart: (() => { const k = `gallery.tile.${o.type}` as MessageKey; const v = t(k); return v !== k ? v : o.label })() }),
                                   onSelect: () => setViewAs(o.type) })),
            ...(viewAs ? [{ key: 'as-original', label: t('wr.menu.original'), onSelect: () => setViewAs(null) }] : []),
            // The data behind this chart, from the visible menu -- it used to be
            // reachable only by right-clicking (HR evaluation, item 3.2).
            ...(live && widgetDatasetId != null && allowExport ? [
              { key: 'export-csv', label: t('wr.menu.csv'), onSelect: () => handleExport('csv') },
              { key: 'export-xlsx', label: t('wr.menu.xlsx'), onSelect: () => handleExport('xlsx') },
            ] : []),
          ]
          return (
            <span onMouseDown={e => e.stopPropagation()} onClick={e => e.stopPropagation()}>
              <ActionMenu portal label={t('wr.menu.aria', { title })} items={items}
                trigger={<MoreVertical size={15} aria-hidden />} triggerClassName="dl-wicon" />
            </span>
          )
        })()}
        {editMode && onDelete && (
          <>
            <button className="dl-wicon dl-wdel" aria-label={t('bc.canvas.deleteWidgetAria', { title })} title={t('bc.canvas.delete')}
              onClick={e => { e.stopPropagation(); onDelete() }}><Trash2 size={15} aria-hidden /></button>
            <span onMouseDown={e => e.stopPropagation()} onClick={e => e.stopPropagation()}>
              <ActionMenu portal
                trigger={<MoreVertical size={15} aria-hidden />} triggerClassName="dl-wicon"
                label={t('bc.canvas.moreActions', { title })}
                items={[
                  // Offered only when the caller can act on it: every existing
                  // caller passes onDelete alone, and a menu item wired to
                  // nothing is worse than an absent one.
                  ...(onDuplicate
                    ? [{ key: 'duplicate', label: t('bc.canvas.duplicateWidget'),
                         icon: <Copy size={12} />, onSelect: () => onDuplicate() }]
                    : []),
                  { key: 'delete', label: t('bc.canvas.deleteWidget'), danger: true, icon: <Trash2 size={12} />, onSelect: () => onDelete() },
                ]}
              />
            </span>
          </>
        )}
        </span>
        {hierarchyNodeId != null && expandLevels.length > 1 && (
          <span style={{ display: 'flex', gap: 2 }}>
            <button aria-label={t('bc.canvas.expandLevel')}
              title={t('bc.canvas.expandLevelTitle')}
              disabled={expandDepth >= expandLevels.length - 1}
              onClick={e => { e.stopPropagation(); setDrillPath([]); setExpandDepth(d => Math.min(d + 1, expandLevels.length - 1)) }}
              style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 11,
                color: expandDepth >= expandLevels.length - 1 ? 'var(--border)' : 'var(--accent)', padding: '0 2px' }}>⊞</button>
            {expandDepth > 0 && (
              <button aria-label={t('bc.canvas.collapseLevel')}
                onClick={e => { e.stopPropagation(); setExpandDepth(d => Math.max(0, d - 1)) }}
                style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 11, color: 'var(--accent)', padding: '0 2px' }}>⊟</button>
            )}
          </span>
        )}
        {drillPath.length > 0 && (
          <div style={{ display:'flex', gap:4, alignItems:'center', fontSize:10, color:'var(--muted)' }}>
            <button onClick={() => setDrillPath([])} style={{ background:'none', border:'none', color:'var(--accent)', cursor:'pointer', fontSize:10, padding:0 }}>{t('bc.canvas.drillAll')}</button>
            {drillPath.map((step, i) => (
              <span key={i} style={{ display:'flex', alignItems:'center', gap:4 }}>
                <span>▸</span>
                <button onClick={() => setDrillPath(p => p.slice(0, i + 1))}
                  style={{ background:'none', border:'none', color: i === drillPath.length - 1 ? 'var(--text)' : 'var(--accent)', cursor:'pointer', fontSize:10, padding:0 }}>
                  {step.label}
                </button>
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Body */}
      <div style={{ flex: 1, minWidth: 0, minHeight: 0, overflow: 'hidden', position: 'relative',
        padding: cfg.widget_padding != null ? cfg.widget_padding : (['table','crosstab','list'].includes(wt) ? 0 : '4px 10px 10px') }}
        // Double-click a mark to drill (SAS's split: single click selects,
        // double click drills). Only with a drill target, only for readers.
        onDoubleClick={!editMode && drillthroughPageId != null ? () => {
          const last = lastClickedRef.current
          if (last && Date.now() - last.at < 1500 && last.value != null && typeof last.value !== 'object') {
            onDrillthrough?.(drillthroughPageId, last.value)
          }
        } : undefined}>
        {loading && <EmptyState msg={t('common.loading')} />}
        {!loading && hiddenByRule && editMode && (
          <div data-testid="widget-hidden-by-rule" style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 12, textAlign: 'center', padding: 8 }}>
            {t('bc.canvas.hiddenByRule')}
          </div>
        )}
        {!loading && !hiddenByRule && smartZoom && (
          <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
            <div style={{ flex: 1, minHeight: 0, position: 'relative', opacity: zoomLoading ? 0.55 : 1, transition: 'opacity .15s' }}>
              <WidgetBody widget={{ ...(viewAs && !editMode ? { ...widget, widget_type: viewAs as Widget['widget_type'] } : widget),
                  config: { ...(widget.config as object), overview_axis: false } } as Widget}
                data={zoom && zoomSel && zoom.a === zoomSel.a && zoom.b === zoomSel.b ? zoom.data
                  : zoomSel ? { ...data, rows: baseRows!.slice(zoomSel.a, zoomSel.b + 1) } : data}
                fetchError={fetchError} onRetry={() => { void fetchData(true) }} localSelected={localSelected} onClickPoint={handleClick} broadcasts={broadcasts} allFormats={allFormats} checked={checked} onToggleSlicerValue={handleToggleSlicerValue} onButtonClick={handleButtonClick} ruleStyles={ruleStyles} parameters={parameters} geography={geography}
                textFilter={textFilter} onSubmitTextFilter={handleSubmitTextFilter}
            rangeFilter={rangeFilter} onSubmitRangeFilter={handleSubmitRangeFilter}
                onBrushChange={undefined} brushNonce={brushNonce} onAnimationFrame={setAnimFrame} />
              {zoomLoading && (
                <span data-testid="zoom-loading" role="status" style={{ position: 'absolute', top: 2, insetInlineEnd: 4, fontSize: 10, color: 'var(--muted)' }}>
                  {t('bc.canvas.loadingMore')}
                </span>
              )}
            </div>
            <OverviewStrip rows={baseRows!} start={zoomSel?.a ?? 0} end={zoomSel?.b ?? baseRows!.length - 1}
              onChange={onZoomDrag} onCommit={commitZoom} resetNonce={brushNonce} />
          </div>
        )}
        {!loading && !hiddenByRule && !smartZoom && (
          <WidgetBody onLoadMore={loadMore} loadingMore={loadingMore} widget={viewAs && !editMode ? { ...widget, widget_type: viewAs as Widget['widget_type'] } : widget} data={data} fetchError={fetchError} onRetry={() => { void fetchData(true) }} localSelected={localSelected} onClickPoint={handleClick} broadcasts={broadcasts} allFormats={allFormats} checked={checked} onToggleSlicerValue={handleToggleSlicerValue} onButtonClick={handleButtonClick} ruleStyles={ruleStyles} parameters={parameters} geography={geography}
            textFilter={textFilter} onSubmitTextFilter={handleSubmitTextFilter}
            rangeFilter={rangeFilter} onSubmitRangeFilter={handleSubmitRangeFilter}
            onBrushChange={setBrushRange} brushNonce={brushNonce} onAnimationFrame={setAnimFrame}
            onAssignData={editMode ? () => window.dispatchEvent(new CustomEvent(ASSIGN_DATA_EVENT, { detail: { widgetId: widget.id } })) : undefined}
            onApplyFix={editMode ? (patch, label) => window.dispatchEvent(new CustomEvent(PATCH_WIDGET_EVENT, { detail: { widgetId: widget.id, patch, label } })) : undefined} />
        )}
      </div>
      {/* Portalled like the context menu: the canvas's scale transform
          makes position:fixed relative to the canvas, not the screen. */}
      {kitDialog === 'explain' && widgetDatasetId != null && typeof (mergedConfig as { measure?: unknown }).measure === 'string' && createPortal(
        <ExplainDialog datasetId={widgetDatasetId} measure={(mergedConfig as { measure: string }).measure}
          filters={((mergedConfig as { filters?: unknown[] }).filters) ?? []} onClose={() => setKitDialog(null)} />,
        document.body)}
      {kitDialog === 'difference' && widgetDatasetId != null && createPortal((() => {
        const c = mergedConfig as Record<string, unknown>
        const rowsNow = ((data as { rows?: { name: unknown; value: unknown }[] } | null)?.rows ?? [])
        const names = rowsNow.map(r => String(r.name))
        const ranked = [...rowsNow].sort((x, y) => Number(y.value) - Number(x.value)).map(r => String(r.name))
        const first = localSelected != null && names.includes(String(localSelected)) ? String(localSelected) : ranked[0]
        const second = ranked.find(n => n !== first) ?? ''
        return (
          <DifferenceDialog datasetId={widgetDatasetId} dimension={String(c.dimension)}
            measure={typeof c.measure === 'string' ? c.measure : null}
            aggregation={String(c.aggregation ?? (typeof c.measure === 'string' ? 'sum' : 'count'))}
            granularity={(c.dimension_granularity as string) ?? null}
            filters={(c.filters as unknown[]) ?? []} names={names} initial={[first, second]}
            onClose={() => setKitDialog(null)} />
        )
      })(), document.body)}
      {reconcileOpen && widgetDatasetId != null && createPortal(
        <Suspense fallback={null}>
          <ReconcileDialog title={widget.title || wt} datasetId={widgetDatasetId} widgetKey={`w${widget.id}`}
            body={{ config: mergedConfig as Record<string, unknown>, widget_type: wt,
                    calculated_columns: effectiveCalcCols, report_id: reportId, parameters: parameters ?? {} }}
            onClose={() => setReconcileOpen(false)} />
        </Suspense>, document.body)}
      {kitDialog === 'why' && createPortal(
        <WhyDialog title={title} sections={whySections()} onClose={() => setKitDialog(null)}
          footnote={t('bc.canvas.why.footnote')} />,
        document.body)}
      {kitDialog === 'scenario' && widgetDatasetId != null && createPortal(
        <ScenarioDialog datasetId={widgetDatasetId}
          dateColumn={String((mergedConfig as { dimension?: unknown }).dimension ?? '')}
          measure={String((mergedConfig as { measure?: unknown }).measure ?? '')}
          candidates={(datasets?.[widgetDatasetId]?.columns ?? [])
            .filter(c => c.dtype === 'numeric' && c.name !== (mergedConfig as { measure?: unknown }).measure).map(c => c.name)}
          onClose={() => setKitDialog(null)} />,
        document.body)}
      {/* Not under a placeholder: an unfinished widget draws no data, so a
          sentence about what it cut would describe something not on screen. */}
      {!loading && !hiddenByRule && data?.truncation?.applied && missingRequiredRoles(widget).length === 0 && (
        <TruncationNote t={data.truncation} dimension={data.dimension ?? data.category}
          onShowMore={editMode ? (limit: number) => window.dispatchEvent(new CustomEvent(PATCH_WIDGET_EVENT, {
            detail: { widgetId: widget.id, patch: { limit }, label: t((data.dimension ?? data.category)
              ? (limit === data.truncation.of ? 'bc.canvas.undo.showAllValues' : 'bc.canvas.undo.showValues')
              : (limit === data.truncation.of ? 'bc.canvas.undo.showAllGroups' : 'bc.canvas.undo.showGroups'),
              { n: limit, dim: String(data.dimension ?? data.category ?? ''), title: widget.title || widget.widget_type }) },
          })) : undefined} />
      )}

      {!loading && !hiddenByRule && (data?.missing_category?.rows ?? 0) > 0 && missingRequiredRoles(widget).length === 0 && (
        <div data-testid="missing-category-note" role="note"
          style={{ fontSize: 10.5, color: 'var(--muted)', padding: '2px 8px 4px', lineHeight: 1.3 }}>
          {missingCategorySentence(data.missing_category.rows,
            Array.isArray(data.missing_category.columns) ? data.missing_category.columns.join(' or ') : (data.dimension ?? data.category))}
        </div>
      )}

      {!loading && !hiddenByRule && Array.isArray(data?.ignored_filters) && data.ignored_filters.length > 0 && (
        <div data-testid="ignored-filters-note" role="note"
          style={{ fontSize: 10.5, color: 'var(--muted)', padding: '2px 8px 4px', lineHeight: 1.3 }}>
          {ignoredFiltersSentence(data.ignored_filters as string[])}
        </div>
      )}

      {/* E08: a grid's small cells are blank, and the reader is told why. */}
      {!loading && !hiddenByRule && (data?.suppressed_cells ?? 0) > 0 && (
        <div data-testid="suppressed-cells-note" role="note"
          style={{ fontSize: 10.5, color: 'var(--muted)', padding: '2px 8px 4px', lineHeight: 1.3 }}>
          {suppressedCellsSentence(data.suppressed_cells, Number((widget.config as { suppress_below?: unknown }).suppress_below) || 0)}
        </div>
      )}

      {!loading && !hiddenByRule && partial && (
        <div data-testid="partial-period-note" role="note"
          style={{ fontSize: 10, color: '#b7791f', padding: '0 10px 4px', lineHeight: 1.3 }}>
          {/* QA2 T14: in Arabic the sentence is composed from the fields (the
              server writes English); the period label is isolated so
              "2025-12" keeps its order. English keeps the server's words. */}
          {language === 'ar' && partialPeriodEnd(partial) ? (() => {
            const f = (d: Date) => d.toLocaleDateString('ar-u-nu-latn', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' })
            return <span dir="rtl">◔ <bdi dir="ltr">{partial.label}</bdi> {t('wr.partial', {
              through: f(new Date(partial.through + 'T00:00:00Z')), unit: t(`wr.unit.${partial.granularity}` as MessageKey), end: f(partialPeriodEnd(partial)!) })}</span>
          })() : <>◔ {partial.text}</>}
        </div>
      )}

      {/* Resize handle — bottom-right corner, in BOTH directions. The canvas
          places widgets from the left in Arabic too (layout x is a left
          offset), so a resize always grows the widget rightward and down; a
          handle mirrored to the bottom-left in RTL pointed the wrong way
          (HR re-test 2026-10-01). Physical `right`, LTR-pinned contents. */}
      {editMode && onResizeStart && (
        <div
          data-testid="widget-resize-handle"
          onMouseDown={e => { e.stopPropagation(); e.preventDefault(); onResizeStart(e) }}
          onPointerDown={e => {
            e.stopPropagation(); e.preventDefault()
            try { e.currentTarget.setPointerCapture(e.pointerId) } catch { /* jsdom */ }
            onResizeStart(e)
          }}
          style={{
            position: 'absolute', bottom: 0, right: 0, direction: 'ltr',
            width: 18, height: 18, cursor: 'nwse-resize',
            display: 'flex', alignItems: 'flex-end', justifyContent: 'flex-end',
            padding: '3px',
          }}
        >
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
            <path d="M9 1L1 9M9 5L5 9M9 9" stroke="var(--muted)" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>
        </div>
      )}

      {showTooltipPreview && tooltipPage && (
        <div style={{
          position: 'fixed', left: previewPos.x, top: previewPos.y, zIndex: Z_OVERLAY,
          width: PREVIEW_W, maxHeight: PREVIEW_H, overflow: 'auto', display: 'flex', flexDirection: 'column', gap: 8,
          padding: 10, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)',
          boxShadow: '0 8px 24px rgba(0,0,0,.25)', pointerEvents: 'none',
        }}>
          <CrossFilterProvider>
            {tooltipPage.widgets.map(w => (
              <div key={w.id} style={{ height: 180 }}>
                <WidgetRenderer
                  widget={w}
                  datasetId={datasetId}
                  calculatedColumns={calculatedColumns}
                  columnFormats={columnFormats}
                  datasets={datasets}
                  isPreview
                />
              </div>
            ))}
          </CrossFilterProvider>
        </div>
      )}

      {/* Portalled to <body>: the canvas is `transform: scale(zoom)`, and a
          transformed ancestor becomes the containing block for position:fixed --
          so the menu opened hundreds of pixels away from the cursor. */}
      {showContextMenu && createPortal(
        <div role="menu" style={{
          position: 'fixed', left: contextMenuPos.x, top: contextMenuPos.y, zIndex: Z_DROPDOWN,
          background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 6,
          boxShadow: '0 8px 24px rgba(0,0,0,.25)', padding: 4, minWidth: 160,
        }}>
          {canDrillthrough && (
            <button role="menuitem"
              onClick={e => { e.stopPropagation(); handleDrillthrough(); setShowContextMenu(false) }}
              style={menuItemStyle}>
              {drillthroughTargetName != null
                ? t('bc.canvas.drillToPage', { page: drillthroughTargetName })
                : t('bc.canvas.drillToAnyPage')}
            </button>
          )}
          {/* Data actions (SAS's mark menu): act on the selected mark, re-sort,
              re-aggregate. Editors only, and each is an ordinary undoable config
              edit routed through the builder (PATCH_WIDGET_EVENT). */}
          {editMode && (() => {
            const c = widget.config as Record<string, any>
            const dim = typeof c.dimension === 'string' ? c.dimension : ''
            const name = widget.title || widget.widget_type
            const patch = (p: Record<string, unknown>, label: string) => {
              window.dispatchEvent(new CustomEvent(PATCH_WIDGET_EVENT, { detail: { widgetId: widget.id, patch: p, label } }))
              setShowContextMenu(false)
            }
            const filters = Array.isArray(c.filters) ? c.filters : []
            const sel = localSelected
            const selText = sel == null ? '' : String(sel)
            const items: React.ReactNode[] = []
            if (dim && sel != null && typeof sel !== 'object') {
              items.push(
                <button key="keep" role="menuitem" style={menuItemStyle}
                  onClick={e => { e.stopPropagation(); setLocalSelected(null)
                    patch({ filters: [...filters.filter((f: any) => f?.column !== dim), { column: dim, op: 'eq', value: sel }] },
                      t('bc.canvas.undo.keep', { dim, value: selText, title: name })) }}>
                  {t('bc.canvas.keepOnly', { value: selText })}
                </button>,
                <button key="exclude" role="menuitem" style={menuItemStyle}
                  onClick={e => { e.stopPropagation(); setLocalSelected(null)
                    patch({ filters: [...filters, { column: dim, op: 'neq', value: sel }] },
                      t('bc.canvas.undo.exclude', { dim, value: selText, title: name })) }}>
                  {t('bc.canvas.exclude', { value: selText })}
                </button>,
              )
            }
            if (filters.length) {
              items.push(
                <button key="clearf" role="menuitem" style={menuItemStyle}
                  onClick={e => { e.stopPropagation(); patch({ filters: [] }, t(filters.length === 1 ? 'bc.canvas.undo.removeFilter1' : 'bc.canvas.undo.removeFiltersN', { n: filters.length, title: name })) }}>
                  {t('bc.canvas.removeWidgetFilters', { n: filters.length })}
                </button>,
              )
            }
            if (dim) {
              items.push(
                <button key="sortv" role="menuitem" style={menuItemStyle}
                  onClick={e => { e.stopPropagation(); patch({ sort_by: 'value', sort: 'desc' }, t('bc.canvas.undo.sortValue', { title: name })) }}>
                  {t('bc.canvas.sortByValue')}
                </button>,
                <button key="sortn" role="menuitem" style={menuItemStyle}
                  onClick={e => { e.stopPropagation(); patch({ sort_by: 'name', sort: 'asc' }, t('bc.canvas.undo.sortName', { title: name, dim })) }}>
                  {t('bc.canvas.sortByName', { dim })}
                </button>,
              )
            }
            if (dim && typeof c.measure === 'string' && c.measure) {
              const aggs: [string, string][] = [['sum', 'Sum'], ['avg', 'Average'], ['min', 'Min'], ['max', 'Max'], ['count', 'Count']]
              items.push(
                <div key="agg" role="group" aria-label={t('bc.canvas.aggregation')} style={{ display: 'flex', gap: 2, flexWrap: 'wrap', padding: '4px 8px', fontSize: 11, color: 'var(--muted)', alignItems: 'center' }}>
                  <span style={{ marginInlineEnd: 4 }}>Σ</span>
                  {aggs.map(([v, l]) => (
                    <button key={v} role="menuitemradio" aria-checked={(c.aggregation ?? 'sum') === v} type="button"
                      onClick={e => { e.stopPropagation(); if ((c.aggregation ?? 'sum') !== v) patch({ aggregation: v }, t('bc.canvas.undo.aggregation', { title: name, from: String(c.aggregation ?? 'sum'), to: v })) }}
                      style={{ fontSize: 11, padding: '1px 6px', borderRadius: 4, cursor: 'pointer',
                        border: '1px solid ' + ((c.aggregation ?? 'sum') === v ? 'var(--accent)' : 'var(--border)'),
                        background: (c.aggregation ?? 'sum') === v ? 'var(--accent)' : 'transparent',
                        color: (c.aggregation ?? 'sum') === v ? 'var(--mc-accent-fg)' : 'var(--text)' }}>
                      {L(l)}
                    </button>
                  ))}
                </div>,
              )
            }
            if (!items.length) return null
            return <>{items}<div role="separator" style={{ height: 1, background: 'var(--border)', margin: '4px 2px' }} /></>
          })()}
          {/* Convert to another object type the widget's fields can fill. */}
          {editMode && (
            <ConvertToMenu widget={widget} itemStyle={menuItemStyle} onDone={() => setShowContextMenu(false)} />
          )}
          {/* Object-level link: encodes page AND widget, so the recipient lands on
              the right page scrolled to this visual with a brief highlight. */}
          <button role="menuitem"
            onClick={e => {
              e.stopPropagation()
              const url = new URL(window.location.href)
              url.searchParams.set('page', String(widget.page_id))
              url.searchParams.set('widget', String(widget.id))
              navigator.clipboard.writeText(url.toString())
                .then(() => toast.success(t('bc.canvas.linkCopied')))
                .catch(() => toast.error(t('bc.canvas.linkCopyFailed')))
              setShowContextMenu(false)
            }}
            style={menuItemStyle}>
            <LinkIcon size={12} aria-hidden style={{ marginInlineEnd: 6, verticalAlign: '-2px' }} />{t('bc.canvas.copyLink')}
          </button>
          {/* Export is offered on every widget with a dataset behind it, drill-through
              or not -- the previous menu rendered only when a drill-through target
              existed, so most widgets had no menu at all. Guest views opt out
              (allowExport=false) -- see the prop doc. */}
          {widgetDatasetId != null && allowExport && (
            <>
              <button role="menuitem"
                onClick={e => { e.stopPropagation(); handleExport('csv') }}
                style={menuItemStyle}>
                ⤓ {t('bc.canvas.exportCsv')}
              </button>
              <button role="menuitem"
                onClick={e => { e.stopPropagation(); handleExport('xlsx') }}
                style={menuItemStyle}>
                ⤓ {t('bc.canvas.exportXlsx')}
              </button>
              <button role="menuitem"
                onClick={e => { e.stopPropagation(); handleExportImage() }}
                style={menuItemStyle}>
                ⤓ {t('bc.canvas.exportImage')}
              </button>
              {/* E17: the migration check -- beside the exports, because the
                  file it compares with is the old report's export. */}
              <button role="menuitem"
                onClick={e => { e.stopPropagation(); setShowContextMenu(false); setReconcileOpen(true) }}
                style={menuItemStyle}>
                ⇄ {t('rec.menu')}
              </button>
            </>
          )}
        </div>,
        document.body,
      )}
    </div>
  )
}

// Default shallow compare on purpose: a custom comparator is where stale-render
// bugs live. Every prop ReportBuilder passes is either a primitive or has a
// memoized identity (see the per-widget handler bundles there); cross-filter
// updates flow through context, which memo never blocks.
export default memo(WidgetRenderer)
