import { memo, useEffect, useState, useCallback, useMemo, useRef } from 'react'
import type { PartialPeriod, RelativeNote } from '../../lib/relativeDates'
import type { BrushRange } from './chartRenderers/axisOptions'
import { createPortal } from 'react-dom'
import { Copy, Trash2, MoreVertical, Link as LinkIcon } from 'lucide-react'
import { widgetDataApi } from '../../services/api'
import { svgToPngDataUrl } from '../../lib/widgetImage'
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
import { ASSIGN_DATA_EVENT, missingRequiredRoles } from './WidgetPlaceholder'

/** Charts whose bars/points are groups of rows two of which can be tested (Phase 7.2). */
const DIFFERENCE_TYPES: string[] = ['bar', 'line', 'area', 'pie', 'donut', 'dot_plot', 'step', 'treemap', 'funnel']
import { TruncationNote, PATCH_WIDGET_EVENT, missingCategorySentence } from './TruncationNote'
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

function WidgetRenderer({ widget, datasetId, calculatedColumns, columnFormats, geography, datasets, selected, isMultiSelected, onSelect, onDelete, onDuplicate, editMode, promptFilter, onDragStart, onResizeStart, isDragging, onFetchComplete, pages, reportDisplayRules, reportFilters, onDrillthrough, isPreview, hierarchy, bookmarks, onNavigateToPage, onApplyBookmark, reportId, parameters, onSetParameter, dataOverride, relationships, eagerFetch, allowExport = true, refreshNonce }: Props) {
  const { emitFilter, emitMultiFilter, getFiltersFor, canBroadcast, canReceive, activeFilters, clearAllFilters, clearFilter, interactions, getReceiveMode, carryFiltersTo } = useCrossFilter()
  const [data,    setData]    = useState<any>(null)
  const [loading, setLoading] = useState(
    () => widgetFetchesData(widget.widget_type, widget.config, dataOverride))
  // The backend's `code` beside its `detail` (services/error_codes.py). The
  // detail is what the reader sees; the code is what decides whether a
  // 'Try again' is offered -- `source_unavailable` and `quota` (after
  // Retry-After) are the two answers that can change on retry.
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
    const crossFilters = incomingFilters.map(f => ({ column: translate(f.column), op: Array.isArray(f.value) ? 'in' : 'eq', value: f.value }))
    const pagePrompt   = (promptFilter?.column && promptFilter?.value)
      ? [{ column: promptFilter.column, op: 'eq', value: promptFilter.value }]
      : []
    // Report-level common filters apply to every widget; translate columns across a
    // modelled relationship like cross-filters do, and let the shaper skip any that
    // this widget's dataset lacks (_apply_filters ignores unknown columns).
    const reportWide = (reportFilters ?? []).map(f => ({ column: translate(f.column), op: f.op, value: f.value }))
    cfg.filters = [...existing, ...reportWide, ...crossFilters, ...pagePrompt]
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
  }, [JSON.stringify(widget.config), JSON.stringify(incomingFilters), promptFilter?.column, promptFilter?.value, hierarchyNodeId, currentNode?.column_name, currentNode?.format, JSON.stringify(drillPath), JSON.stringify(decompPath), decompSplit, widget.widget_type, expandDepth, expandLevels.join(','), JSON.stringify(relationships ?? []), JSON.stringify(reportDisplayRules), JSON.stringify(reportFilters)])
  const mergedConfig = mergedPair.config
  const translatedCrossFilters = mergedPair.crossFilters

  /** The reader's transparency pane: every layer that decides this widget. */
  // Overview-axis zoom and the animation's current frame: widget-local,
  // never saved, shown in the header and the transparency pane.
  const [brushRange, setBrushRange] = useState<BrushRange | null>(null)
  const [brushNonce, setBrushNonce] = useState(0)
  const [animFrame, setAnimFrame] = useState<string | null>(null)
  useEffect(() => { setBrushRange(null) }, [data])
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
    const t = (data as { truncation?: { applied?: boolean; shown?: number; of?: number; reason?: string } } | null)?.truncation
    const rank = cfg0.rank as { mode?: string; n?: number; percent?: boolean; other?: boolean } | undefined
    const rules = [...(reportDisplayRules ?? []), ...((cfg0.display_rules as unknown[] | undefined) ?? [])]
    return [
      { title: 'What is measured', empty: '', items: [
        measureName ? `${agg} of ${measureName}` : 'number of rows',
        ...(typeof cfg0.dimension === 'string' ? [`for each ${cfg0.dimension}`] : []),
        ...(widgetDatasetId != null && datasets?.[widgetDatasetId]?.name ? [`from ${datasets[widgetDatasetId].name}`] : []),
      ] },
      { title: 'Set by the author (this widget)', empty: 'No filters.', items: own.map(describeFilter) },
      { title: 'Set by the author (whole report)', empty: 'No report filters.',
        items: report.map(f => `${describeFilter(f)}${applies(f.column) ? '' : ' — does not apply: this widget’s data has no such column'}`) },
      { title: 'Your selections', empty: 'None — click a mark on another widget to filter this one.',
        items: [
          ...translatedCrossFilters.map(f => describeFilter(f as FilterLikeLocal)),
          ...(promptFilter?.column && promptFilter?.value ? [`page prompt: ${promptFilter.column} is ${promptFilter.value}`] : []),
          ...drillPath.map(s => `drilled into ${s.column} = ${s.value}`),
        ] },
      ...(relNotes.length || partial ? [{ title: 'Date windows', empty: '', items: [
        ...relNotes.map(n => n.error ? `${n.column}: ${n.error} — nothing matches` : `${n.column}: ${n.text ?? n.label}`),
        ...(partial ? [partial.text] : []),
      ] }] : []),
      ...(brushRange || (data as { type?: string } | null)?.type === 'animated' ? [{ title: 'Your view of this chart', empty: '', items: [
        ...(brushRange ? [`Zoomed with the overview axis to ${brushRange.start} – ${brushRange.end} (${brushRange.endIndex - brushRange.startIndex + 1} of ${brushRange.of} points); the rest is hidden, not filtered out of any total`] : []),
        ...((data as { type?: string } | null)?.type === 'animated' && animFrame ? [`Showing the frame ${String((data as { animate_by?: string }).animate_by)} = ${animFrame} of an animation`] : []),
      ] }] : []),
      { title: 'Ranking and limits', empty: 'Every group is shown.', items: [
        ...(rank?.n ? [`${rank.mode === 'bottom' ? 'Bottom' : 'Top'} ${rank.n}${rank.percent ? '%' : ''}${rank.other ? ', the rest as “All other”' : ''}`] : []),
        ...(t?.applied ? [`Showing ${t.shown} of ${t.of} groups (${t.reason === 'limit' ? 'row limit' : t.reason})`] : []),
      ] },
      { title: 'Display rules', empty: 'None.', items: rules.length ? [`${rules.length} rule${rules.length === 1 ? '' : 's'} colour or hide values here`] : [] },
    ]
  }

  const fetchData = useCallback(async (fresh = false) => {
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
            effectiveCalcCols, 'kpi', { reportId, parameters, fresh })))
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
          widgetDataApi.query(widgetDatasetId, baseCfg, effectiveCalcCols, wt, { reportId, parameters, fresh }),
          widgetDataApi.query(widgetDatasetId, mergedConfig, effectiveCalcCols, wt, { reportId, parameters, fresh }),
        ])
        const partMap = new Map((part?.rows ?? []).map((r: any) => [r.name, r.value]))
        setData({ ...full, rows: (full?.rows ?? []).map((r: any) => ({ ...r, highlight: partMap.get(r.name) ?? 0 })) })
        onFetchComplete?.(widget.id, {
          durationMs: performance.now() - startedAt,
          rowCount: full?.rows?.length ?? 0, sampled: !!full?.sampled,
          ruleErrors: full?.rule_errors,
        })
        return
      }
      const result = await widgetDataApi.query(widgetDatasetId, mergedConfig, effectiveCalcCols, wt, { reportId, parameters, fresh })
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
    finally { setLoading(false) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [widgetDatasetId, widget.widget_type, JSON.stringify(mergedConfig), JSON.stringify(parameters ?? {}), dataOverride, getReceiveMode(widget.id), JSON.stringify(translatedCrossFilters), refreshNonce])

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
  useEffect(() => {
    if (!lazyEligible || hasBeenVisible) fetchData()
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
  }, [canBroadcast, widget.id, widget.config, localSelected, emitFilter, emitMultiFilter, hierarchyNodeId, hierarchy, currentNodeId, currentNode])

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
      toast.error('Could not export this widget')
    }
  }

  const widgetRootRef = useRef<HTMLDivElement>(null)

  const handleExportImage = async () => {
    setShowContextMenu(false)
    const svg = widgetRootRef.current?.querySelector('svg')
    if (!svg) { toast.error('This widget has no chart to export'); return }
    try {
      const dataUrl = await svgToPngDataUrl(svg as SVGSVGElement, 2)
      const a = document.createElement('a')
      a.href = dataUrl
      a.download = `${(widget.title || wt).replace(/[^A-Za-z0-9 _-]/g, '').slice(0, 60) || 'widget'}.png`
      a.click()
    } catch {
      toast.error('Could not export this widget as an image')
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
                Empty container — assign widgets to it from their settings
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
                Empty container — assign widgets to it from their settings
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
        onMouseDown={editMode && onDragStart ? e => { e.stopPropagation(); onDragStart(e) } : undefined}
        onPointerDown={editMode && onDragStart ? e => {
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
        <span style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
          <span role="heading" aria-level={3} title={title}
            style={{ fontWeight: 600, fontSize: 14, lineHeight: 1.3, color: 'var(--text)', minWidth: 0,
              whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{title}</span>
          {typeof cfg.subtitle === 'string' && cfg.subtitle && (
            <span data-testid="widget-subtitle" title={cfg.subtitle}
              style={{ fontSize: 12, lineHeight: 1.35, color: 'var(--muted)', whiteSpace: 'nowrap',
                overflow: 'hidden', textOverflow: 'ellipsis' }}>{cfg.subtitle}</span>
          )}
        </span>
        {data?.sampled && (
          <span title={`Showing a sample of ${data.sample_size} out of ${data.total_rows} rows`}
            style={{ fontSize: 9, background: 'rgba(230,160,60,.18)', color: '#e6a03c', padding: '1px 5px', borderRadius: 99 }}>
            sampled
          </span>
        )}
        {brushRange && (
          <span data-testid="brush-chip" title={`Zoomed with the overview axis: ${brushRange.start} – ${brushRange.end} of ${brushRange.of} points`}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: 9, padding: '1px 4px 1px 5px', borderRadius: 99,
              background: 'color-mix(in srgb, var(--accent) 14%, transparent)', color: 'var(--accent)', whiteSpace: 'nowrap' }}>
            zoomed {brushRange.endIndex - brushRange.startIndex + 1}/{brushRange.of}
            <button aria-label="Reset the overview zoom" title="Show the whole series"
              onClick={e => { e.stopPropagation(); setBrushRange(null); setBrushNonce(n => n + 1) }}
              style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', font: 'inherit', lineHeight: 1, padding: 0 }}>×</button>
          </span>
        )}
        {relNotes.length > 0 && (
          <span data-testid="relative-date-chip"
            title={relNotes.map(n => n.error ? `${n.column}: ${n.error}` : `${n.column} — ${n.text ?? n.label}`).join('\n')}
            style={{ fontSize: 9, padding: '1px 5px', borderRadius: 99, whiteSpace: 'nowrap',
              background: relNotes.some(n => n.error || n.incomplete) ? 'rgba(230,160,60,.18)' : 'color-mix(in srgb, var(--accent) 14%, transparent)',
              color: relNotes.some(n => n.error || n.incomplete) ? '#b7791f' : 'var(--accent)' }}>
            {relNotes[0].error ? 'date filter error' : relNotes[0].label}
            {relNotes.some(n => n.incomplete) ? ' · partial' : ''}
          </span>
        )}
        {incomingFilters.length > 0 && (
          <span title={`Filtered by: ${incomingFilters.map(f => f.label).join(', ')}`}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: 9, background: 'color-mix(in srgb, var(--accent) 20%, transparent)', color: 'var(--accent)', padding: '1px 4px 1px 5px', borderRadius: 99 }}>
            {incomingFilters.length} filter{incomingFilters.length > 1 ? 's' : ''}
            <button aria-label="Clear this filter" title="Clear this filter"
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
          <button title="Drill through with the selected value"
            style={{ fontSize: 9, background: 'color-mix(in srgb, var(--accent) 15%, transparent)', color: 'var(--accent)', border: 'none', borderRadius: 99, padding: '2px 7px', cursor: 'pointer' }}
            onClick={e => { e.stopPropagation(); handleDrillthrough() }}>
            ⤷ Drill through
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
        {broadcasts && <span title="Emits cross-filters" style={{ fontSize: 9, color: 'var(--accent)', opacity: .7 }}>→</span>}
        {receives && <span title="Receives cross-filters" style={{ fontSize: 9, color: 'var(--accent)', opacity: .7 }}>←</span>}
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
            { key: 'why', label: 'Why am I seeing this?', onSelect: () => setKitDialog('why') },
            ...(measure && live ? [{ key: 'explain', label: `Explain ${measure}`, onSelect: () => setKitDialog('explain') }] : []),
            ...(live && DIFFERENCE_TYPES.includes(widget.widget_type) && typeof cfgAny.dimension === 'string'
                && !cfgAny.dimension2 && rowsNow >= 2 && String(cfgAny.aggregation ?? 'sum') !== 'max'
                && String(cfgAny.aggregation ?? 'sum') !== 'min' && !(measure && measureNames.has(measure))
              ? [{ key: 'difference', label: 'Is this difference real?', onSelect: () => setKitDialog('difference') }] : []),
            ...(live && widget.widget_type === 'forecast' && measure && numericCols.length
              ? [{ key: 'whatif', label: 'What if…', onSelect: () => setKitDialog('scenario') }] : []),
            ...options.map(o => ({ key: `as-${o.type}`, label: `View as ${o.label}${o.recommended ? ' (recommended)' : ''}`,
                                   onSelect: () => setViewAs(o.type) })),
            ...(viewAs ? [{ key: 'as-original', label: 'Show as designed', onSelect: () => setViewAs(null) }] : []),
          ]
          return (
            <span onMouseDown={e => e.stopPropagation()} onClick={e => e.stopPropagation()}>
              <ActionMenu label={`Analyse ${title}`} items={items}
                trigger={<MoreVertical size={15} aria-hidden />} triggerClassName="dl-wicon" />
            </span>
          )
        })()}
        {editMode && onDelete && (
          <>
            <button className="dl-wicon" aria-label={`Delete widget ${title}`} title="Delete"
              onClick={e => { e.stopPropagation(); onDelete() }}><Trash2 size={15} aria-hidden /></button>
            <span onMouseDown={e => e.stopPropagation()} onClick={e => e.stopPropagation()}>
              <ActionMenu
                trigger={<MoreVertical size={15} aria-hidden />} triggerClassName="dl-wicon"
                label={`More actions for widget ${title}`}
                items={[
                  // Offered only when the caller can act on it: every existing
                  // caller passes onDelete alone, and a menu item wired to
                  // nothing is worse than an absent one.
                  ...(onDuplicate
                    ? [{ key: 'duplicate', label: 'Duplicate widget',
                         icon: <Copy size={12} />, onSelect: () => onDuplicate() }]
                    : []),
                  { key: 'delete', label: 'Delete widget', danger: true, icon: <Trash2 size={12} />, onSelect: () => onDelete() },
                ]}
              />
            </span>
          </>
        )}
        </span>
        {hierarchyNodeId != null && expandLevels.length > 1 && (
          <span style={{ display: 'flex', gap: 2 }}>
            <button aria-label="Expand hierarchy one level"
              title="Show the next level alongside this one (Power BI's expand)"
              disabled={expandDepth >= expandLevels.length - 1}
              onClick={e => { e.stopPropagation(); setDrillPath([]); setExpandDepth(d => Math.min(d + 1, expandLevels.length - 1)) }}
              style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 11,
                color: expandDepth >= expandLevels.length - 1 ? 'var(--border)' : 'var(--accent)', padding: '0 2px' }}>⊞</button>
            {expandDepth > 0 && (
              <button aria-label="Collapse hierarchy one level"
                onClick={e => { e.stopPropagation(); setExpandDepth(d => Math.max(0, d - 1)) }}
                style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 11, color: 'var(--accent)', padding: '0 2px' }}>⊟</button>
            )}
          </span>
        )}
        {drillPath.length > 0 && (
          <div style={{ display:'flex', gap:4, alignItems:'center', fontSize:10, color:'var(--muted)' }}>
            <button onClick={() => setDrillPath([])} style={{ background:'none', border:'none', color:'var(--accent)', cursor:'pointer', fontSize:10, padding:0 }}>All</button>
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
        {loading && <EmptyState msg="Loading…" />}
        {!loading && hiddenByRule && editMode && (
          <div data-testid="widget-hidden-by-rule" style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 12, textAlign: 'center', padding: 8 }}>
            Hidden by a display rule
          </div>
        )}
        {!loading && !hiddenByRule && (
          <WidgetBody widget={viewAs && !editMode ? { ...widget, widget_type: viewAs as Widget['widget_type'] } : widget} data={data} fetchError={fetchError} onRetry={() => { void fetchData(true) }} localSelected={localSelected} onClickPoint={handleClick} broadcasts={broadcasts} allFormats={allFormats} checked={checked} onToggleSlicerValue={handleToggleSlicerValue} onButtonClick={handleButtonClick} ruleStyles={ruleStyles} parameters={parameters} geography={geography}
            textFilter={textFilter} onSubmitTextFilter={handleSubmitTextFilter}
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
      {kitDialog === 'why' && createPortal(
        <WhyDialog title={title} sections={whySections()} onClose={() => setKitDialog(null)}
          footnote="Row-level security may also narrow the rows you can see; it is applied before everything above and is not shown here." />,
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
            detail: { widgetId: widget.id, patch: { limit }, label: `Show ${limit === data.truncation.of ? 'all ' : ''}${limit} ${(data.dimension ?? data.category) ? `${data.dimension ?? data.category} values` : 'groups'} in "${widget.title || widget.widget_type}"` },
          })) : undefined} />
      )}

      {!loading && !hiddenByRule && (data?.missing_category?.rows ?? 0) > 0 && missingRequiredRoles(widget).length === 0 && (
        <div data-testid="missing-category-note" role="note"
          style={{ fontSize: 10.5, color: 'var(--muted)', padding: '2px 8px 4px', lineHeight: 1.3 }}>
          {missingCategorySentence(data.missing_category.rows, data.dimension ?? data.category)}
        </div>
      )}

      {!loading && !hiddenByRule && partial && (
        <div data-testid="partial-period-note" role="note"
          style={{ fontSize: 10, color: '#b7791f', padding: '0 10px 4px', lineHeight: 1.3 }}>
          ◔ {partial.text}
        </div>
      )}

      {/* Resize handle — bottom-right corner */}
      {editMode && onResizeStart && (
        <div
          onMouseDown={e => { e.stopPropagation(); e.preventDefault(); onResizeStart(e) }}
          onPointerDown={e => {
            e.stopPropagation(); e.preventDefault()
            try { e.currentTarget.setPointerCapture(e.pointerId) } catch { /* jsdom */ }
            onResizeStart(e)
          }}
          style={{
            position: 'absolute', bottom: 0, insetInlineEnd: 0,
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
              ⤷ Drill through to {drillthroughTargetName ?? 'page'}
            </button>
          )}
          {/* Data actions (SAS's mark menu): act on the selected mark, re-sort,
              re-aggregate. Editors only, and each is an ordinary undoable config
              edit routed through the builder (PATCH_WIDGET_EVENT). */}
          {editMode && (() => {
            const c = widget.config as Record<string, any>
            const dim = typeof c.dimension === 'string' ? c.dimension : ''
            const name = `"${widget.title || widget.widget_type}"`
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
                      `Keep only ${dim} = ${selText} in ${name}`) }}>
                  ✓ Keep only “{selText}”
                </button>,
                <button key="exclude" role="menuitem" style={menuItemStyle}
                  onClick={e => { e.stopPropagation(); setLocalSelected(null)
                    patch({ filters: [...filters, { column: dim, op: 'neq', value: sel }] },
                      `Exclude ${dim} = ${selText} from ${name}`) }}>
                  ✕ Exclude “{selText}”
                </button>,
              )
            }
            if (filters.length) {
              items.push(
                <button key="clearf" role="menuitem" style={menuItemStyle}
                  onClick={e => { e.stopPropagation(); patch({ filters: [] }, `Remove ${filters.length} filter${filters.length === 1 ? '' : 's'} from ${name}`) }}>
                  ⊘ Remove this widget’s filters ({filters.length})
                </button>,
              )
            }
            if (dim) {
              items.push(
                <button key="sortv" role="menuitem" style={menuItemStyle}
                  onClick={e => { e.stopPropagation(); patch({ sort_by: 'value', sort: 'desc' }, `Sort ${name} by value, high to low`) }}>
                  ↓ Sort by value (high → low)
                </button>,
                <button key="sortn" role="menuitem" style={menuItemStyle}
                  onClick={e => { e.stopPropagation(); patch({ sort_by: 'name', sort: 'asc' }, `Sort ${name} by ${dim}, A to Z`) }}>
                  ↑ Sort by {dim} (A → Z)
                </button>,
              )
            }
            if (dim && typeof c.measure === 'string' && c.measure) {
              const aggs: [string, string][] = [['sum', 'Sum'], ['avg', 'Average'], ['min', 'Min'], ['max', 'Max'], ['count', 'Count']]
              items.push(
                <div key="agg" role="group" aria-label="Aggregation" style={{ display: 'flex', gap: 2, flexWrap: 'wrap', padding: '4px 8px', fontSize: 11, color: 'var(--muted)', alignItems: 'center' }}>
                  <span style={{ marginInlineEnd: 4 }}>Σ</span>
                  {aggs.map(([v, l]) => (
                    <button key={v} role="menuitemradio" aria-checked={(c.aggregation ?? 'sum') === v} type="button"
                      onClick={e => { e.stopPropagation(); if ((c.aggregation ?? 'sum') !== v) patch({ aggregation: v }, `Change aggregation of ${name} from ${c.aggregation ?? 'sum'} to ${v}`) }}
                      style={{ fontSize: 11, padding: '1px 6px', borderRadius: 4, cursor: 'pointer',
                        border: '1px solid ' + ((c.aggregation ?? 'sum') === v ? 'var(--accent)' : 'var(--border)'),
                        background: (c.aggregation ?? 'sum') === v ? 'var(--accent)' : 'transparent',
                        color: (c.aggregation ?? 'sum') === v ? 'var(--mc-accent-fg)' : 'var(--text)' }}>
                      {l}
                    </button>
                  ))}
                </div>,
              )
            }
            if (!items.length) return null
            return <>{items}<div role="separator" style={{ height: 1, background: 'var(--border)', margin: '4px 2px' }} /></>
          })()}
          {/* Object-level link: encodes page AND widget, so the recipient lands on
              the right page scrolled to this visual with a brief highlight. */}
          <button role="menuitem"
            onClick={e => {
              e.stopPropagation()
              const url = new URL(window.location.href)
              url.searchParams.set('page', String(widget.page_id))
              url.searchParams.set('widget', String(widget.id))
              navigator.clipboard.writeText(url.toString())
                .then(() => toast.success('Link to this visual copied'))
                .catch(() => toast.error('Could not copy the link'))
              setShowContextMenu(false)
            }}
            style={menuItemStyle}>
            <LinkIcon size={12} aria-hidden style={{ marginInlineEnd: 6, verticalAlign: '-2px' }} />Copy link to this visual
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
                ⤓ Export data as CSV
              </button>
              <button role="menuitem"
                onClick={e => { e.stopPropagation(); handleExport('xlsx') }}
                style={menuItemStyle}>
                ⤓ Export data as Excel
              </button>
              <button role="menuitem"
                onClick={e => { e.stopPropagation(); handleExportImage() }}
                style={menuItemStyle}>
                ⤓ Export as image
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
