import PdfOptionsDialog from '../components/report/PdfOptionsDialog'
import RelativeDateEditor from '../components/report/RelativeDateEditor'
import AccessExplainer from '../components/report/AccessExplainer'
import { DEFAULT_SPEC, PRESETS, describeSpec, parseSpec, specProblem, type RelativeSpec } from '../lib/relativeDates'
import { closeOpen, markOpen, readOpen, type OpenReport } from '../lib/openReports'
import GeoMatchCheck from '../components/report/GeoMatchCheck'
import { useEffect, useState, useCallback, useMemo, useRef } from 'react'
import LoadError from '../components/ui/LoadError'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useCrumbTitle } from '../lib/crumb'
import NotFound from './NotFound'
import { useDirection } from '../contexts/DirectionContext'
import { useT, type MessageKey } from '../i18n'
import { authzApi, type AuthzDecision, measuresApi, relationshipsApi, translationsApi, columnMetaApi, parametersApi, themesApi, reportsApi, datasetsApi, hierarchyApi, analysisApi, widgetTemplatesApi, dataSourcesApi } from '../services/api'
import type { Dataset, DatasetColumn, CalcColumn, CalcColumnFormat, MeasureDef, ColumnMeta, WidgetTemplate } from '../services/api'
import CalcColumnsPanel from '../components/report/CalcColumnsPanel'
import ColumnFormatsPanel from '../components/report/ColumnFormatsPanel'
import type { Report, ReportPage, Widget, WidgetType, PageType, Bookmark, BookmarkState } from '../types/report'
import { WIDGET_CATALOG, ROLE_SPECS, configKeyFor } from '../types/report'
import type { HierarchyNode, RoleField } from '../types/report'
import WidgetRenderer from '../components/report/WidgetRenderer'
import WidgetConfigPanel from '../components/report/WidgetConfigPanel'
import DisplayRulesPanel from '../components/report/DisplayRulesPanel'
import type { DisplayRule } from '../lib/displayRules'
import PagePropertiesPanel from '../components/report/PagePropertiesPanel'
import HierarchyTree from '../components/report/HierarchyTree'
import FilterBar from '../components/report/FilterBar'
import FloatingFilterWindow from '../components/report/FloatingFilterWindow'
import DataView from '../components/report/DataView'
import OutlierDetailsDialog from '../components/report/OutlierDetailsDialog'
import CommentsPane from '../components/report/CommentsPane'
import TranslationsPane from '../components/report/TranslationsPane'
import InsightsPane from '../components/report/InsightsPane'
import ShareLinksDialog from '../components/report/ShareLinksDialog'
import AccessDialog from '../components/report/AccessDialog'
import { useOptionalAuth } from '../contexts/AuthContext'
import ExplainDialog from '../components/report/ExplainDialog'
import OutlinePane from '../components/report/OutlinePane'
import SuggestionsPane, { type Suggestion } from '../components/report/SuggestionsPane'
import ModelView from '../components/report/ModelView'
import StatusBar from '../components/report/StatusBar'
import MobileLayoutEditor from '../components/report/MobileLayoutEditor'
import SelectionPane from '../components/report/SelectionPane'
import VersionHistoryPane from '../components/report/VersionHistoryPane'
import TabOrderPane from '../components/report/TabOrderPane'
import ChatPane from '../components/chat/ChatPane'
import CopilotChat from '../components/report/CopilotChat'
import IconLabel from '../components/ui/IconLabel'
import ChartGallery from '../components/report/ChartGallery'
import {
  LayoutDashboard as ViewReport, Table2 as ViewData, Waypoints as ViewModel,
  PanelLeft, Lightbulb, CheckCheck, MessageSquare, AtSign, Clock, Bot, Sparkles,
  Smartphone, MousePointerClick, Link2, Bookmark as BookmarkIcon, ArrowRightLeft, Gauge as PerfGauge, History,
  Palette, Languages, Copy, Globe, Shield as AccessShield, MoreHorizontal, LayoutTemplate,
  type LucideIcon,
} from 'lucide-react'
import { applyTheme } from '../components/report/chartUtils'
import { THEMES } from '../components/report/themes'
import { useMediaQuery, MOBILE_QUERY } from '../hooks/useMediaQuery'
import { Z_DROPDOWN, Z_DRAG } from '../lib/zIndex'
import { alignWidgets, distributeWidgets } from '../lib/alignment'
import { chartForFields, type AutoField } from '../lib/autoChart'
import { quickCalcsFor, uniqueMeasureName } from '../lib/quickCalcs'
import { countLabel } from '../lib/fieldHints'
import { boundarySetsApi, type BoundaryPack } from '../services/api'
import PackTermsConfirm from '../components/report/PackTermsConfirm'
import { describeFilter } from '../components/report/ViewerKit'
import { fieldHints, hintTitle } from '../lib/fieldHints'
import { PRE_AGGREGATED_HINT } from '../lib/aggregateDisclosure'
import { CrossFilterProvider, useCrossFilter } from '../components/report/CrossFilterContext'
import CollapsibleSide from '../components/report/CollapsibleSide'
import ReviewPane from '../components/report/ReviewPane'
import PopupOverlay from '../components/report/PopupOverlay'
import TooltipPageOverlay from '../components/report/TooltipPageOverlay'
import { ArrowLeft, Plus, Settings, Eye, Undo2, Redo2, KeyRound, ShieldCheck, Pause, Play, FileDown, Printer, FileText, Package } from 'lucide-react'
import { useUndoStack, IdAliases, describeConfigChange, changedKeys } from './reportBuilder/undo'
import { ASSIGN_DATA_EVENT, ADD_DATASET_EVENT, missingRequiredRoles } from '../components/report/WidgetPlaceholder'
import { PATCH_WIDGET_EVENT } from '../components/report/TruncationNote'
import { nonAdditiveKind, SAFE_AGGREGATION } from '../lib/semanticGuard'
import { readPending, clearPending, type PendingEdit } from '../lib/pendingEdits'
import DatasetPickerDialog from '../components/dataset/DatasetPickerDialog'
import toast from 'react-hot-toast'
import SubscribeButton from '../components/report/SubscribeButton'
import ToolbarMenu from '../components/report/ToolbarMenu'
import { useConfirm } from '../components/ui/ConfirmDialog'
import { useMeasuredWidth } from '../components/report/useMeasuredWidth'
import { useModalDialog } from '../components/ui/useModalDialog'
import {
  applyRecipe as applyLayoutRecipe,
  compact,
  dropFree,
  dropPacked,
  isPackedMode,
  isRecipeId,
  itemsOverlap,
  layoutChanged,
  minSize,
  needsAutoPack,
  RECIPES,
  resizeFree,
  resizePacked,
  toLayoutItems,
  DEFAULT_RECIPE,
} from '../lib/dashboardLayout'

import {
  COLS, ROW_H, GAP, LEFT_SIDEBAR_W, RIGHT_PANEL_W, MIN_CANVAS_W,
  CLASSIFICATION_LABELS, CLASSIFICATION_COLORS, gridStyle, canvasH,
} from './reportBuilder/grid'
import { SyncSlicersPaneConnected, BookmarksPaneConnected } from './reportBuilder/BookmarksConnected'
import { SchedulePanel } from './reportBuilder/SchedulePanel'
import { PageTemplateMenu } from './reportBuilder/PageTemplateMenu'

const EMPTY_RULES: DisplayRule[] = []

/** Display names for the built-in palettes. The keys stay what reports have
 *  stored all along; only the label a person picks from changes. */
const PALETTE_NAME: Record<string, string> = {
  default: 'Datalytics', ocean: 'Ocean', sunset: 'Ember', forest: 'Forest',
  mono: 'Graphite', contrast: 'High contrast',
}

/** The top-most, then left-most, grid position where a w×h box fits without
 *  overlapping any existing layout. Null if nothing fits above the last row. */
function firstFreeSlot(layouts: { x: number; y: number; w: number; h: number }[], w: number, h: number, cols: number) {
  const bottom = layouts.reduce((m, l) => Math.max(m, l.y + l.h), 0)
  const overlaps = (x: number, y: number) => layouts.some(l =>
    x < l.x + l.w && x + w > l.x && y < l.y + l.h && y + h > l.y)
  for (let y = 0; y <= bottom; y++) {
    for (let x = 0; x + w <= cols; x++) {
      if (!overlaps(x, y)) return { x, y }
    }
  }
  return null
}

/** Drop ?pick=data from the address without a navigation. */
function stripPickParam() {
  const params = new URLSearchParams(window.location.search)
  if (!params.has('pick')) return
  params.delete('pick')
  const qs = params.toString()
  window.history.replaceState(null, '', window.location.pathname + (qs ? `?${qs}` : ''))
}

export default function ReportBuilder() {
  const { language } = useDirection()
  const tr = useT()
  const { id } = useParams<{ id: string }>()
  const reportId = Number(id)
  const badId = !/^\d+$/.test(id ?? '')

  const [report,     setReport]     = useState<Report | null>(null)
  useCrumbTitle(report?.name)
  const [activePage, setActivePage] = useState<ReportPage | null>(null)
  const [selectedW,  setSelectedW]  = useState<Widget | null>(null)
  const [templates,  setTemplates]  = useState<WidgetTemplate[]>([])
  const [tplName,    setTplName]    = useState('')
  const [cfCol, setCfCol] = useState('')
  const [cfOp,  setCfOp]  = useState('eq')
  const [cfVal, setCfVal] = useState('')
  const [cfSpec, setCfSpec] = useState<RelativeSpec>({ ...DEFAULT_SPEC })
  // Phase 7.3: what this user may do here, with reasons, and the sensitivity in force.
  const [access, setAccess] = useState<Record<string, AuthzDecision>>({})
  const [sens, setSens] = useState<{ floor?: string | null; floor_reasons?: string[]; effective?: string | null; effective_reasons?: string[] } | null>(null)
  const [accessOpen2, setAccessOpen2] = useState(false)
  const [dataset,    setDataset]    = useState<Dataset | null>(null)
  const [datasets,   setDatasets]   = useState<Record<number, Dataset>>({})
  // True once the datasets map (calc columns, formats, meta) has resolved --
  // the widget canvas waits on it; see the loading effect below.
  const [datasetsReady, setDatasetsReady] = useState(false)
  const [allDatasets,setAllDatasets]= useState<Dataset[]>([])
  // Primary dataset's connection name, for the header breadcrumb -- fetched only
  // when there is one (source-backed dataset); an upload's dataset has no
  // data_source_id and the breadcrumb degrades to no source link.
  const [sourceName, setSourceName] = useState<string | null>(null)
  const [showDsMenu, setShowDsMenu] = useState(false)
  /** The widget a dragged field is hovering, outlined as the drop target. */
  const [dropTargetId, setDropTargetId] = useState<number | null>(null)
  // The left panel's three tabs. Fields first: SAS's rail opens on Data, and
  // browsing the data must never require first finding the right chart among
  // sixty buttons. Remembered per viewer (a convenience -- guarded storage).
  const [leftTab, setLeftTabState] = useState<'fields' | 'charts' | 'more'>(() => {
    try {
      const v = localStorage.getItem('datalytics:builder-left-tab')
      return v === 'charts' || v === 'more' ? v : 'fields'
    } catch { return 'fields' }
  })
  const setLeftTab = (t: 'fields' | 'charts' | 'more') => {
    setLeftTabState(t)
    try { localStorage.setItem('datalytics:builder-left-tab', t) } catch { /* storage unavailable */ }
  }
  const [hierarchy,  setHierarchy]  = useState<HierarchyNode[]>([])
  const [calcCols,      setCalcCols]      = useState<CalcColumn[]>([])
  const [measures,      setMeasures]      = useState<MeasureDef[]>([])
  const [columnMeta,    setColumnMeta]    = useState<Record<string, ColumnMeta>>({})
  // Cached analysis, used only for the inline field hints. Its statistics were
  // already computed server-side and simply never surfaced next to the fields.
  const [analysis,      setAnalysis]      = useState<any>(null)
  const [columnFormats, setColumnFormats] = useState<Record<string, CalcColumnFormat>>({})
  const [activeView, setActiveView] = useState<'report' | 'data' | 'model'>('report')
  // A phone opens a dashboard to READ it: the studio's two side panels left
  // no room for the canvas at 390px. It starts in View there (Edit remains a
  // tap away for someone who needs it).
  const [editModeWanted, setEditMode] = useState(() => !window.matchMedia(MOBILE_QUERY).matches)
  // Capability mirror (server enforces; this hides what it would refuse):
  // 'view' can't edit, only 'data' can reach the Data/Model authoring tabs.
  const myCapability = report?.my_capability ?? 'view'
  const canEdit = myCapability !== 'view'
  const canData = myCapability === 'data'
  // DERIVED, not corrected afterwards. A view-only viewer can never be in edit
  // mode for even one frame, and the ~40 `editMode &&` gates below (right
  // panel, toolbars, drag/resize, add-widget, page controls, shortcuts,
  // copilot) all answer to capability through this single line instead of
  // each having to remember to ask.
  const editMode = editModeWanted && canEdit
  // Measured from the canvas element itself; 900 is only the value before one
  // exists. See useMeasuredWidth for why this cannot be an effect.
  const { width: containerW, attach: attachCanvas, ref: canvasRef } =
    useMeasuredWidth(900)
  const [editPid,      setEditPid]      = useState<number | null>(null)
  const [editPname,    setEditPname]    = useState('')
  const [promptValues, setPromptValues] = useState<Record<number, string>>({})
  const [saving, setSavingState] = useState(false)
  // Mirrors `saving` for the revision poll, whose interval closure would otherwise
  // capture a stale value and misread our own in-flight write as someone else's.
  //
  // Written SYNCHRONOUSLY, not from an effect. An effect only runs once React has
  // committed, and a poll tick landing in that window read `false` while a write
  // was already in flight -- which is how "This report was changed in another
  // session" appeared on a page only this session had touched.
  const savingRef = useRef(false)
  const setSaving = useCallback((next: boolean) => {
    savingRef.current = next
    setSavingState(next)
  }, [])
  const [zoom, setZoom] = useState(100)
  const [multiSelectedIds, setMultiSelectedIds] = useState<Set<number>>(new Set())
  useEffect(() => { setZoom(100); setMultiSelectedIds(new Set()) }, [activePage?.id])
  type RightPanelMode = 'default' | 'mobile' | 'selection' | 'sync' | 'bookmarks' | 'taborder' | 'performance' | 'reportrules' | 'parameters' | 'schedule' | 'review' | 'comments' | 'outline' | 'suggestions' | 'translations' | 'insights' | 'ask' | 'history'
  const [rightPanelMode, setRightPanelMode] = useState<RightPanelMode>('default')
  const [pageMenuOpen, setPageMenuOpen] = useState(false)
  const [layoutMenuOpen, setLayoutMenuOpen] = useState(false)
  const [shortcutsOpen, setShortcutsOpen] = useState(false)
  // Kiosk playback: pages auto-advance on an interval; any key or click exits.
  const [kiosk, setKiosk] = useState(false)

  // Report parameters: definitions from the report, values from this viewer --
  // seeded from ?p.<name>= so a shared link can preset them (URL parameter presets).
  const [translations, setTranslations] = useState<Record<string, Record<string, string>>>({})
  useEffect(() => { translationsApi.list(reportId).then(setTranslations).catch(() => setTranslations({})) }, [reportId])
  // View-time localisation: the language switcher picks the override set
  // ('ar' matches report translations saved as `ar`). Authored strings stay
  // the source of truth and the builder always edits them, so translations
  // apply in VIEW mode only.
  const activeTranslation = !editMode
    ? (translations[language] ?? null)
    : null
  const localise = useCallback((w: Widget): Widget => {
    if (!activeTranslation) return w
    const title = activeTranslation[`w${w.id}`]
    const content = w.widget_type === 'text' ? activeTranslation[`c${w.id}`] : undefined
    if (!title && !content) return w
    return { ...w, ...(title ? { title } : {}),
      ...(content ? { config: { ...(w.config as object), content } } : {}) }
  }, [activeTranslation])
  const [relationships, setRelationships] = useState<{ from_dataset_id: number; from_column: string; to_dataset_id: number; to_column: string }[]>([])
  useEffect(() => { relationshipsApi.list().then(setRelationships).catch(() => setRelationships([])) }, [])
  const [outlierColumn, setOutlierColumn] = useState<string | null>(null)
  const [toolbarMoreOpen, setToolbarMoreOpen] = useState(false)
  const [shareOpen, setShareOpen] = useState(false)
  const [accessOpen, setAccessOpen] = useState(false)
  const isAdmin = !!useOptionalAuth()?.user?.role?.is_org_admin
  const [explainColumn, setExplainColumn] = useState<string | null>(null)
  const [paramDefs, setParamDefs] = useState<import('../services/api').ReportParameterDef[]>([])
  /** The parameters as last saved, so a Save can be undone back to them. */
  const savedParams = useRef<import('../services/api').ReportParameterDef[]>([])
  const [paramValues, setParamValues] = useState<Record<string, string>>(() => {
    const seed: Record<string, string> = {}
    new URLSearchParams(window.location.search).forEach((v, k) => {
      if (k.startsWith('p.')) seed[k.slice(2)] = v
    })
    return seed
  })
  useEffect(() => {
    parametersApi.list(reportId).then(d => { setParamDefs(d); savedParams.current = d }).catch(() => setParamDefs([]))
  }, [reportId])

  // What widgets and {{@name}} text actually see: each definition's default,
  // overlaid by anything the viewer set (parameter bar, URL seed, or a
  // set-parameter button). Without the defaults layer, prose placeholders and
  // brand-new viewers would see em dashes until someone touched the bar --
  // exactly the bug the first in-browser drive of {{@threshold}} surfaced.
  const effectiveParams = useMemo(() => {
    const merged: Record<string, string> = {}
    for (const d of paramDefs) if (d.default_value != null) merged[d.name] = d.default_value
    return { ...merged, ...paramValues }
  }, [paramDefs, paramValues])

  // Org-defined palettes, keyed "custom:<id>" to match what Report.theme stores.
  const [orgThemes, setOrgThemes] = useState<Record<string, { name: string; colors: string[] }>>({})
  useEffect(() => {
    themesApi.list()
      .then(list => setOrgThemes(Object.fromEntries(list.map(t => [`custom:${t.id}`, t]))))
      .catch(() => {})
  }, [])

  // Narrow-viewport detection for switching to the stacked mobile layout in View mode.
  const isNarrowViewport = useMediaQuery(MOBILE_QUERY)

  // Drag / resize state
  const [dragging,  setDragging]  = useState<{ widgetId:number; startX:number; startY:number; layout:Widget['layout']; offsetX:number; offsetY:number; packed:boolean; items:ReturnType<typeof toLayoutItems> } | null>(null)
  const [resizing,  setResizing]  = useState<{ widgetId:number; startX:number; startY:number; layout:Widget['layout']; packed:boolean; items:ReturnType<typeof toLayoutItems> } | null>(null)
  const [localLayouts, setLocalLayouts] = useState<Record<number, Widget['layout']>>({})
  // Mirrored in a ref so the drag effect's mouseup can read the LATEST layout
  // without listing localLayouts in its deps -- with it listed, every
  // mousemove re-attached the window listeners.
  const localLayoutsRef = useRef(localLayouts)
  useEffect(() => { localLayoutsRef.current = localLayouts }, [localLayouts])
  // Writes go through this, never through setLocalLayouts alone: the effect
  // above only syncs the ref AFTER React commits and flushes passive effects.
  // A fast drag (pointermove and pointerup landing in the same task) reached
  // `onUp` with the ref still holding the PREVIOUS value -- on the first move
  // of a drag that is `{}`, so `Object.keys(layouts).length` was 0 and the
  // move was silently dropped instead of saved.
  const commitLocalLayouts = useCallback((next: Record<number, Widget['layout']>) => {
    localLayoutsRef.current = next
    setLocalLayouts(next)
  }, [])

  // Every edit here persists immediately with no explicit save, so two people on
  // one report otherwise silently last-write-wins. knownRevision tracks the counter
  // as of our own most recent load; a poll that finds a higher one means somebody
  // else wrote. Warn rather than block: their change is already saved, and refusing
  // our writes mid-drag would be worse than telling us to reload.
  const [loadedRevision, setLoadedRevision] = useState<number | null>(null)
  const loadedRevisionRef = useRef<number | null>(null)
  const [staleRevision, setStaleRevision] = useState<number | null>(null)
  useEffect(() => { loadedRevisionRef.current = loadedRevision }, [loadedRevision])

  // Load report
  const [loadError, setLoadError] = useState<unknown>(null)
  const loadReport = useCallback(async () => {
    setLoadError(null)
    if (!Number.isFinite(reportId)) return
    const r = await reportsApi.get(reportId)
    // A shared link can name the page to open (?page=<id>). Honoured once per load;
    // an unknown id falls back to the first page rather than erroring.
    const wanted = Number(new URLSearchParams(window.location.search).get('page'))
    setReport(r)
    setLoadedRevision(r.revision ?? 0)
    setStaleRevision(null)
    localLayoutsRef.current = {}
    setLocalLayouts({})
    applyTheme(r.theme ?? 'default',
      Object.fromEntries(Object.entries(orgThemes).map(([k, v]) => [k, v.colors])))
    setActivePage(prev =>
      r.pages.find(p => p.id === prev?.id)
      ?? r.pages.find(p => p.id === wanted)
      ?? r.pages[0]
      ?? null)
    // The selection is a snapshot of a widget; refresh it from the reloaded
    // page so every consumer (field click, template save, hierarchy assign)
    // sees the config that was just saved rather than the one before it.
    setSelectedW(prev => {
      if (!prev) return prev
      for (const p of r.pages) { const fresh = p.widgets.find(w => w.id === prev.id); if (fresh) return fresh }
      return prev
    })
    // orgThemes in the deps: a report saved with a custom theme needs the palette map
    // at apply time. The one extra reload when themes arrive is the cost of the
    // colours being right.
  }, [reportId, orgThemes])

  // Unguarded, this left `report` null on any failure -- a deleted report or a
  // 500 pinned the page on "Loading…" with no error and no way out.
  useEffect(() => { loadReport().catch(e => setLoadError(e ?? new Error('failed'))) },
            [loadReport])

  // ── Undo / redo ─────────────────────────────────────────────────────────────
  // A command log over the server writes this builder makes (see
  // reportBuilder/undo.ts). Undoing a delete recreates the widget under a new
  // id, so every command resolves its widget through `widgetIds` when it RUNS.
  const widgetIds = useRef(new IdAliases())
  // Pages too: undoing a page delete recreates it under a new id, and every
  // older entry that names the page (its widgets' edits) must follow it.
  const pageIds = useRef(new IdAliases())
  const pid = (id: number) => pageIds.current.resolve(id)
  const undoStack = useUndoStack(
    async () => { await loadReport() },
    (label) => toast.error(`Could not undo "${label}" — what it changed no longer exists`),
  )
  const pushUndo = undoStack.push
  const recreateWidget = useCallback(async (
    pageId: number, oldId: number, snap: Partial<Widget>,
  ) => {
    const created = await reportsApi.addWidget(reportId, pageIds.current.resolve(pageId), snap)
    widgetIds.current.set(widgetIds.current.resolve(oldId), created.id)
    return created
  }, [reportId])
  const removeWidgetById = useCallback(async (pageId: number, id: number) => {
    await reportsApi.deleteWidget(reportId, pageIds.current.resolve(pageId), widgetIds.current.resolve(id))
  }, [reportId])

  const persistWidgetLayouts = useCallback(async (
    page: ReportPage,
    layouts: Record<number, Widget['layout']>,
    pagePatch?: Partial<ReportPage>,
    /** When set, the layout change is one undoable step with this sentence. */
    undoLabel?: string,
  ) => {
    const writes: Promise<unknown>[] = []
    const before: Record<number, Widget['layout']> = {}
    const after: Record<number, Widget['layout']> = {}
    if (pagePatch) writes.push(reportsApi.updatePage(reportId, page.id, pagePatch))
    for (const w of page.widgets) {
      const next = layouts[w.id]
      if (next && layoutChanged(w.layout, next)) {
        writes.push(reportsApi.updateWidget(reportId, page.id, w.id, { layout: next }))
        before[w.id] = w.layout
        after[w.id] = next
      }
    }
    if (!writes.length) return
    if (undoLabel && Object.keys(before).length) {
      const apply = (m: Record<number, Widget['layout']>) => Promise.all(Object.entries(m).map(([id, layout]) =>
        reportsApi.updateWidget(reportId, pageIds.current.resolve(page.id), widgetIds.current.resolve(Number(id)), { layout }))).then(() => {})
      pushUndo({ label: undoLabel, undo: () => apply(before), redo: () => apply(after) })
    }
    const alreadySaving = savingRef.current
    if (!alreadySaving) setSaving(true)
    try {
      await Promise.all(writes)
      await loadReport()
    } finally {
      if (!alreadySaving) setSaving(false)
    }
  }, [reportId, loadReport, pushUndo])

  const packingPageRef = useRef<Set<number>>(new Set())
  useEffect(() => {
    if (!editMode || !canEdit || !activePage) return
    if (!needsAutoPack(activePage.layout_mode)) return
    if (packingPageRef.current.has(activePage.id)) return
    packingPageRef.current.add(activePage.id)
    const layouts = applyLayoutRecipe(toLayoutItems(activePage.widgets), DEFAULT_RECIPE)
    void persistWidgetLayouts(activePage, layouts, {
      layout_mode: 'packed',
      layout_template: DEFAULT_RECIPE,
    })
  }, [activePage, editMode, canEdit, persistWidgetLayouts])

  useEffect(() => {
    if (!editMode || !activePage || dragging || resizing) return
    if (!isPackedMode(activePage.layout_mode) || needsAutoPack(activePage.layout_mode)) return
    const items = toLayoutItems(activePage.widgets)
    if (!itemsOverlap(items)) return
    void persistWidgetLayouts(activePage, compact(items))
  }, [activePage, editMode, dragging, resizing, persistWidgetLayouts])

  const applyPageRecipe = async (choice: 'free' | typeof DEFAULT_RECIPE | string) => {
    if (!activePage) return
    setLayoutMenuOpen(false)
    if (choice === 'free') {
      await persistWidgetLayouts(activePage, {}, { layout_mode: 'free', layout_template: activePage.layout_template })
      return
    }
    const recipe = isRecipeId(choice) ? choice : DEFAULT_RECIPE
    const layouts = applyLayoutRecipe(toLayoutItems(activePage.widgets), recipe)
    await persistWidgetLayouts(activePage, layouts, { layout_mode: 'packed', layout_template: recipe })
  }

  // (No effect needed: `editMode` above is derived from capability, so a
  // view-only viewer is never in edit mode rather than being put back.)

  // Object-level deep link: ?widget=<id> (paired with ?page=, which loadReport
  // honours) scrolls the visual into view and flashes its outline once the
  // canvas is up. One-shot -- later page flips must not re-scroll.
  const deepLinkDone = useRef(false)
  useEffect(() => {
    if (deepLinkDone.current || !activePage) return
    const wid = Number(new URLSearchParams(window.location.search).get('widget'))
    if (!wid) { deepLinkDone.current = true; return }
    const t = setTimeout(() => {
      const el = document.querySelector(`[data-widget-id="${wid}"]`) as HTMLElement | null
      if (el) {
        deepLinkDone.current = true
        el.scrollIntoView({ block: 'center', behavior: 'smooth' })
        el.animate?.([
          { outline: '3px solid var(--accent)', outlineOffset: '2px' },
          { outline: '3px solid transparent', outlineOffset: '2px' },
        ], { duration: 2500, easing: 'ease-out' })
      }
    }, 900)
    return () => clearTimeout(t)
  }, [activePage?.id])  // eslint-disable-line react-hooks/exhaustive-deps

  // Depends on loadedRevision so the first check runs once we actually know what we
  // loaded — on mount alone it would race the initial fetch and always no-op.
  useEffect(() => {
    if (loadedRevision === null) return
    let cancelled = false
    const check = async () => {
      // Skip while one of our own writes is in flight: it bumps the counter and then
      // reloads, and reporting that as somebody else's edit would be a false alarm.
      if (savingRef.current) return
      try {
        const remote = await reportsApi.getRevision(reportId)
        // The fetch may have started before our save; ignore if we wrote meanwhile
        // or if loadReport already caught up.
        if (savingRef.current) return
        const known = loadedRevisionRef.current
        if (!cancelled && known != null && remote > known) setStaleRevision(remote)
      } catch {
        // Offline or transient. Nothing to warn about — the next tick retries.
      }
    }
    check()
    const timer = setInterval(check, 20_000)
    return () => { cancelled = true; clearInterval(timer) }
  }, [reportId, loadedRevision])

  const [bookmarks, setBookmarks] = useState<Bookmark[]>([])
  useEffect(() => { reportsApi.listBookmarks(reportId).then(setBookmarks) }, [reportId])

  // Load all attached datasets (primary + additional) into the datasets map.
  // Widgets wait for this (datasetsReady) before mounting: a widget that
  // queries before calc columns arrive sends calculated_columns: [] -- a
  // subtly wrong query that also defeats the client result cache, because
  // the remount after any tab flip re-sends it with the real list.
  const reloadAttachedDatasets = useCallback(async (
    r: { dataset_id?: number | null; additional_dataset_ids?: number[] | null },
  ) => {
    const ids = [
      ...(r.dataset_id ? [r.dataset_id] : []),
      ...(r.additional_dataset_ids ?? []),
    ]
    if (ids.length === 0) { setDatasetsReady(true); return }
    try {
      const list = await Promise.all(ids.map(id => datasetsApi.get(id)))
      const map: Record<number, Dataset> = {}
      list.forEach(ds => { map[ds.id] = ds })
      setDatasets(map)
      const primary = r.dataset_id ? map[r.dataset_id] : null
      if (primary) {
        setDataset(primary)
        setCalcCols(primary.calculated_columns ?? [])
        setMeasures(primary.measures ?? [])
        setColumnMeta(primary.column_meta ?? {})
        setColumnFormats(primary.column_formats ?? {})
      }
      setDatasetsReady(true)
    } catch {
      // A failed dataset fetch must not blank the canvas forever.
      setDatasetsReady(true)
    }
  }, [])

  // Repair reports stranded by the old attach path: datasets attached while the
  // report had no primary all landed in additional_dataset_ids, leaving the
  // builder with no fields. Promote the first one, once, for an editor only.
  const repairedPrimary = useRef(false)
  useEffect(() => {
    if (!report || repairedPrimary.current) return
    const extra = report.additional_dataset_ids ?? []
    if (report.dataset_id || extra.length === 0) return
    if ((report.my_capability ?? 'view') === 'view') return
    repairedPrimary.current = true
    reportsApi.update(report.id, { dataset_id: extra[0], additional_dataset_ids: extra.slice(1) })
      .then(() => loadReport())
      .catch(() => { /* leave as is; the fields pane still says what to do */ })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [report?.id, report?.dataset_id, JSON.stringify(report?.additional_dataset_ids)])

  useEffect(() => {
    if (!report) return
    void reloadAttachedDatasets(report)
    if (report.dataset_id) {
      hierarchyApi.get(report.dataset_id).then(setHierarchy)
      // Read-only: never triggers a run, so a dataset with no analysis yet simply
      // shows no hints rather than paying for one on every report open.
      analysisApi.get(report.dataset_id).then(setAnalysis).catch(() => setAnalysis(null))
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [report?.dataset_id, JSON.stringify(report?.additional_dataset_ids), reloadAttachedDatasets])

  useEffect(() => {
    if (!report?.id) return
    let live = true
    authzApi.decisions(['view', 'edit', 'data', 'share_link', 'download'].map(action => ({ resource: 'report' as const, id: report.id, action })))
      .then(ds => { if (live) setAccess(Object.fromEntries(ds.map(d => [d.action, d]))) })
      .catch(() => { if (live) setAccess({}) })
    reportsApi.getClassification(report.id)
      .then(c => { if (live) setSens(c) })
      .catch(() => { if (live) setSens(null) })
    return () => { live = false }
  // Re-asked when the label changes (it changes what may be shared/downloaded).
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [report?.id, report?.classification])

  const onCopilotApplied = useCallback(async (change?: { beforeVersionId: number | null; summary: string | null }) => {
    // Copilot can write calculated columns onto the dataset, which loadReport
    // does not refetch (its effect is keyed on dataset ids, not revision).
    await loadReport()
    if (report) await reloadAttachedDatasets(report)
    // The accountable assistant (Phase 7.1): the AI's change is ONE entry on
    // the same undo stack as the author's own edits, named as the AI's.
    // Undo restores the version captured just before it; that restore saves
    // the post-change state as a version, which is what redo goes back to.
    const before = change?.beforeVersionId
    if (before != null) {
      let after: number | null = null
      pushUndo({
        label: `Copilot: ${change?.summary ?? 'page edit'}`,
        undo: async () => {
          const r = await reportsApi.restoreVersion(reportId, before)
          after = r.saved_current_as_version_id ?? null
        },
        redo: async () => {
          if (after == null) throw new Error('nothing to redo')
          await reportsApi.restoreVersion(reportId, after)
        },
      })
    }
  }, [loadReport, report, reloadAttachedDatasets, pushUndo, reportId])

  // Breadcrumb source name: only for a source-backed primary dataset, resolved
  // from the connections list (dataset GET carries the id, not the name).
  useEffect(() => {
    const srcId = dataset?.data_source_id
    if (srcId == null) { setSourceName(null); return }
    let cancelled = false
    dataSourcesApi.list().then(list => {
      if (cancelled) return
      setSourceName(list.find(s => s.id === srcId)?.name ?? null)
    }).catch(() => { if (!cancelled) setSourceName(null) })
    return () => { cancelled = true }
  }, [dataset?.data_source_id])

  const refreshHierarchy = () => {
    if (report?.dataset_id) hierarchyApi.get(report.dataset_id).then(setHierarchy)
  }

  // Report-level rules apply across every widget on every page, ahead of each widget's
  // own rules (WidgetRenderer merges report rules first, widget rules second so the
  // widget can override).
  //
  // DisplayRulesPanel's onChange fires on every keystroke and continuously while
  // dragging the colour input -- unlike the other loadReport()-on-write handlers in
  // this file (theme, layout, ...), which only fire on a discrete user action.
  // Firing reportsApi.update on every one of those events, plus a full loadReport()
  // after each, would spam the API and let two in-flight PATCHes land out of order
  // (an older list persisting over a newer one). So this follows
  // WidgetConfigPanel's own debounced-save pattern (~600ms) instead of the write-then-
  // reload pattern used elsewhere on this page: update local state immediately so the
  // UI stays responsive, debounce the actual persist, and skip the reload -- local
  // state is already the source of truth for what was just typed, and reloading would
  // only risk clobbering it with a stale server copy if the PATCH is still in flight.
  const reportRulesSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Holds the latest not-yet-persisted { id, rules } payload while a debounced write is
  // pending, so the unmount cleanup below has something concrete to send -- a cleanup
  // closure can't read fresh component state, only a ref kept current alongside each
  // (re)scheduled debounce. Cleared once the debounced write actually fires so unmount
  // doesn't re-send an already-persisted payload.
  const pendingReportRules = useRef<{ id: number; rules: DisplayRule[] } | null>(null)
  useEffect(() => () => {
    if (reportRulesSaveTimer.current) clearTimeout(reportRulesSaveTimer.current)
    // Flush rather than discard: local state already shows the edit applied (see
    // updateReportDisplayRules below), so cancelling the timer here without sending
    // the write would silently lose it if the author navigates away mid-debounce.
    // Fire-and-forget -- cleanup must stay synchronous -- with a no-op catch so an
    // unmount can't produce an unhandled rejection. A full-page navigation can still
    // drop this in flight; that's fine, the case being fixed is in-app unmount.
    if (pendingReportRules.current) {
      const pending = pendingReportRules.current
      // Fires during unmount, where a toast cannot render -- so this one is
      // explicitly acknowledged rather than silently discarded. The save is
      // genuinely lost and the next load shows stale rules.
      reportsApi.update(pending.id, { display_rules: pending.rules })
        .catch(e => { void e })
    }
  }, [])
  const updateReportDisplayRules = (rules: DisplayRule[]) => {
    if (!report) return
    const id = report.id
    const before = report.display_rules ?? []
    // One entry per burst of rule editing (typing a threshold, dragging a
    // colour): coalescing keeps the state from before the burst as the undo.
    pushUndo({ label: 'Change report display rules', coalesceKey: `report-rules:${id}`,
      undo: () => reportsApi.update(id, { display_rules: before }).then(() => {}),
      redo: () => reportsApi.update(id, { display_rules: rules }).then(() => {}) })
    setReport(r => (r ? { ...r, display_rules: rules } : r))
    if (reportRulesSaveTimer.current) clearTimeout(reportRulesSaveTimer.current)
    pendingReportRules.current = { id, rules }
    reportRulesSaveTimer.current = setTimeout(() => {
      pendingReportRules.current = null
      reportsApi.update(id, { display_rules: rules }).catch(() => {
        toast.error('Failed to save display rules')
      })
    }, 600)
  }

  const attachDataset = async (dsId: number) => {
    if (!report) return
    const current = report.additional_dataset_ids ?? []
    if (current.includes(dsId) || dsId === report.dataset_id) return
    // A report created with "add data later" has no primary dataset. The field
    // list, hierarchy and every widget's role pickers read the PRIMARY, so the
    // first dataset attached must become it -- appending it to the additional
    // list left the builder with no columns anywhere and no message saying why.
    const name = allDatasets.find(d => d.id === dsId)?.name ?? `dataset ${dsId}`
    if (!report.dataset_id) {
      await reportsApi.update(report.id, { dataset_id: dsId })
      pushUndo({ label: `Attach data "${name}"`,
        undo: () => reportsApi.update(reportId, { dataset_id: null as unknown as number }).then(() => {}),
        redo: () => reportsApi.update(reportId, { dataset_id: dsId }).then(() => {}) })
    } else {
      await reportsApi.update(report.id, { additional_dataset_ids: [...current, dsId] })
      pushUndo({ label: `Attach data "${name}"`,
        undo: () => reportsApi.update(reportId, { additional_dataset_ids: current }).then(() => {}),
        redo: () => reportsApi.update(reportId, { additional_dataset_ids: [...current, dsId] }).then(() => {}) })
    }
    await loadReport()
  }

  const detachDataset = async (dsId: number) => {
    if (!report) return
    const current = report.additional_dataset_ids ?? []
    await reportsApi.update(report.id, { additional_dataset_ids: current.filter(id => id !== dsId) })
    pushUndo({ label: `Remove data "${datasets[dsId]?.name ?? `dataset ${dsId}`}"`,
      undo: () => reportsApi.update(reportId, { additional_dataset_ids: current }).then(() => {}),
      redo: () => reportsApi.update(reportId, { additional_dataset_ids: current.filter(id => id !== dsId) }).then(() => {}) })
    setDatasets(p => { const n = { ...p }; delete n[dsId]; return n })
    await loadReport()
  }

  // â”€â”€ Widgets â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const addWidget = async (type: WidgetType, config: Record<string, unknown> = {}, title?: string) => {
    if (!activePage) return toast.error('Select a page first')
    const ws = activePage.widgets
    const maxY = ws.length ? Math.max(...ws.map(w => w.layout.y + w.layout.h)) : 0
    const cat = WIDGET_CATALOG.find(c => c.type === type)
    const min = minSize(type)
    const w = Math.min(COLS, Math.max(cat?.defaultW ?? 6, min.w))
    const h = Math.max(cat?.defaultH ?? 5, min.h)
    setSaving(true)
    savingRef.current = true
    try {
      // The first gap that fits, scanning top-to-bottom, left-to-right --
      // not always a new row at x=0, which stacked every new widget in one
      // half-width column and grew a 74-widget page to 25,000px.
      const slot = firstFreeSlot(ws.map(x => x.layout), w, h, COLS) ?? { x: 0, y: maxY }
      const widget = await reportsApi.addWidget(reportId, activePage.id, {
        widget_type: type,
        title: title ?? cat?.label ?? type,
        config,
        layout: { x: slot.x, y: slot.y, w, h },
      })
      {
        const pageId = activePage.id
        const snap: Partial<Widget> = { widget_type: type, title: title ?? cat?.label ?? type, config, layout: widget.layout }
        pushUndo({
          label: `Add ${snap.title}`,
          undo: () => removeWidgetById(pageId, widget.id),
          redo: async () => { await recreateWidget(pageId, widget.id, snap) },
        })
      }
      if (isPackedMode(activePage.layout_mode) && !needsAutoPack(activePage.layout_mode)) {
        const nextWidgets = [...ws, widget]
        await persistWidgetLayouts(
          { ...activePage, widgets: nextWidgets },
          compact(toLayoutItems(nextWidgets)),
        )
      }
      // Always reload: persistWidgetLayouts no-ops when compact did not move
      // anything, which left the new widget on the server only and made the
      // revision poll look like another session had edited the report.
      await loadReport()
      setSelectedW(widget)
      // Bring the new widget into view: added below the fold, it looked as if
      // the click had done nothing.
      setTimeout(() => document.querySelector(`[data-widget-id="${widget.id}"]`)
        ?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' }), 60)
      // A freshly inserted widget that still needs data opens its Data roles --
      // after a tick, so the settings panel for it has mounted to hear it.
      if (missingRequiredRoles(widget).length) {
        setTimeout(() => window.dispatchEvent(new CustomEvent(ASSIGN_DATA_EVENT, { detail: { widgetId: widget.id } })), 0)
      }
      toast.success(`${title ?? cat?.label ?? type} added`)
    } finally {
      setSaving(false)
    }
  }

  // Object templates: save the selected widget's type+config under a name, then
  // insert new widgets from it. Loaded once; the picker lives in the Insert panel.
  const loadTemplates = () => { widgetTemplatesApi.list().then(setTemplates).catch(() => {}) }
  useEffect(loadTemplates, [])

  const saveAsTemplate = async () => {
    const name = tplName.trim()
    if (!selectedW) return toast.error('Select a widget first')
    if (!name) return toast.error('Name the template first')
    await widgetTemplatesApi.create({ name, widget_type: selectedW.widget_type,
      config: selectedW.config as Record<string, unknown> })
    setTplName('')
    loadTemplates()
    toast.success(`Saved template "${name}"`)
  }

  const insertFromTemplate = (t: WidgetTemplate) =>
    addWidget(t.widget_type as WidgetType, { ...t.config }, t.name)

  const deleteTemplate = async (t: WidgetTemplate) => {
    if (!await confirm({ title: `Delete template "${t.name}"?`, body: 'This cannot be undone.' })) return
    await widgetTemplatesApi.delete(t.id)
    loadTemplates()
  }

  // Report-level common filters: defined once, applied to every widget (the shaper
  // skips any whose column a given widget's dataset lacks). Edits update local state
  // directly so all widgets re-query at once, which is what "propagates" means here.
  const addReportFilter = async () => {
    if (!cfCol) return toast.error('Choose a column')
    if (cfOp === 'relative' && specProblem(cfSpec)) return toast.error(specProblem(cfSpec)!)
    const value = cfOp === 'relative' ? cfSpec : cfOp === 'in'
      ? cfVal.split(',').map(s => s.trim()).filter(Boolean)
      : (cfVal.trim() === '' ? '' : (isNaN(Number(cfVal)) ? cfVal.trim() : Number(cfVal)))
    const body = { column: cfCol, op: cfOp, value }
    const created = await reportsApi.addCommonFilter(reportId, body)
    setReport(r => (r ? { ...r, common_filters: [...(r.common_filters ?? []), created] } : r))
    void syncRevisionAfterOwnWrite()
    {
      // Redo mints a new filter id; the holder keeps undo pointing at the live one.
      const live = { id: created.id as number }
      pushUndo({ label: `Add report filter "${describeFilter(body)}"`,
        undo: () => reportsApi.deleteCommonFilter(reportId, live.id).then(() => {}),
        redo: async () => { live.id = (await reportsApi.addCommonFilter(reportId, body)).id as number } })
    }
    setCfCol(''); setCfVal('')
    toast.success('Report filter added')
  }
  /** "Last 30 days is one click" (Part IV criterion 9): a preset applied to
   *  the dataset's date column as a report filter. A second preset REPLACES the
   *  relative filter already on that column rather than stacking two windows
   *  that would intersect to nonsense -- and the swap is one undo step. */
  // A function, not a value: `columns` is declared further down this component.
  const dateColumnOf = (): string | null =>
    columns.find(c => c.dtype === 'datetime' || c.dtype === 'date')?.name ?? null
  const applyDatePreset = async (presetId: string) => {
    const dateColumn = dateColumnOf()
    const preset = PRESETS.find(p => p.id === presetId)
    if (!preset || !dateColumn) return
    const spec = { ...preset.spec, anchor: 'data_max' } as RelativeSpec
    const old = (report?.common_filters ?? []).find(f => f.column === dateColumn && f.op === 'relative')
    const body = { column: dateColumn, op: 'relative', value: spec }
    if (old) await reportsApi.deleteCommonFilter(reportId, old.id)
    const created = await reportsApi.addCommonFilter(reportId, body)
    setReport(r => (r ? { ...r, common_filters: [
      ...(r.common_filters ?? []).filter(f => f.id !== old?.id), created] } : r))
    void syncRevisionAfterOwnWrite()
    const live = { id: created.id as number }
    const oldBody = old ? { column: old.column, op: old.op, value: old.value } : null
    pushUndo({ label: `Filter the report to ${preset.label.toLowerCase()}`,
      undo: async () => {
        await reportsApi.deleteCommonFilter(reportId, live.id)
        if (oldBody) await reportsApi.addCommonFilter(reportId, oldBody as never)
      },
      redo: async () => {
        const cur = (await reportsApi.get(reportId)).common_filters
          ?.find(f => f.column === dateColumn && f.op === 'relative')
        if (cur) await reportsApi.deleteCommonFilter(reportId, cur.id)
        live.id = (await reportsApi.addCommonFilter(reportId, body)).id as number
      } })
    toast.success(`Report filtered to ${preset.label.toLowerCase()} of ${dateColumn}`)
  }
  const removeReportFilter = async (fid: number) => {
    const gone = (report?.common_filters ?? []).find(f => f.id === fid)
    await reportsApi.deleteCommonFilter(reportId, fid)
    if (gone) {
      const body = { column: gone.column, op: gone.op, value: gone.value }
      const live = { id: fid }
      pushUndo({ label: `Remove report filter "${describeFilter(body as never)}"`,
        undo: async () => { live.id = (await reportsApi.addCommonFilter(reportId, body as never)).id as number },
        redo: () => reportsApi.deleteCommonFilter(reportId, live.id).then(() => {}) })
    }
    setReport(r => (r ? { ...r, common_filters: (r.common_filters ?? []).filter(f => f.id !== fid) } : r))
    void syncRevisionAfterOwnWrite()
  }
  // A report-filter write bumps the server's revision without reloading the
  // report; without catching up here, the revision poll reported our own edit
  // as "changed in another session".
  const syncRevisionAfterOwnWrite = async () => {
    try { setLoadedRevision(await reportsApi.getRevision(reportId)) } catch { /* next poll decides */ }
  }

  /** Switch the report theme as one undoable step (loadReport applies it). */
  const setThemeUndoable = async (next: string) => {
    const prev = report?.theme ?? 'default'
    if (prev === next) return
    await reportsApi.update(reportId, { theme: next })
    pushUndo({ label: `Change theme to ${orgThemes[next]?.name ?? next}`,
      undo: () => reportsApi.update(reportId, { theme: prev }).then(() => {}),
      redo: () => reportsApi.update(reportId, { theme: next }).then(() => {}) })
    await loadReport()
  }

  // Auto-chart from a dragged field: the chart type is inferred from what the
  // field IS -- a date becomes a trend line, a category a bar of counts, a
  // measure a histogram -- so dragging data onto empty canvas always lands
  // something sensible to refine, never a config dialog.
  // A hierarchy behaves as a DATA ITEM, the SAS/PBI way: its chip assigns the
  // whole level chain (bound at the first level; drill and expand walk the
  // rest), and dragging it onto empty canvas auto-charts at level one.
  const firstHierarchyNode = (folderId: number) => {
    const child = hierarchy.find(n => n.parent_id === folderId && n.column_name)
    return child ?? hierarchy.find(n => n.id === folderId && n.column_name)
  }

  const assignHierarchyToWidget = (folderId: number) => {
    if (!selectedW || !activePage) return
    const node = firstHierarchyNode(folderId)
    if (!node) return
    const config = { ...(selectedW.config as Record<string, unknown>),
      dimension: node.column_name, hierarchyNodeId: node.id,
      ...(node.format ? { dimension_granularity: node.format } : {}) }
    const before = (selectedW.config ?? {}) as Record<string, unknown>
    const pageId = activePage.id, wid = selectedW.id
    const write = (c: Record<string, unknown>) =>
      reportsApi.updateWidget(reportId, pid(pageId), widgetIds.current.resolve(wid), { config: c }).then(() => {})
    reportsApi.updateWidget(reportId, activePage.id, selectedW.id, { config }).then(() => {
      pushUndo({ label: `Set ${selectedW.title || 'widget'} to hierarchy ${node.name || node.column_name}`,
        undo: () => write(before), redo: () => write(config) })
      return loadReport()
    })
  }

  const addWidgetFromHierarchy = async (folderId: number) => {
    const node = firstHierarchyNode(folderId)
    if (!node) return
    await addSuggestedWidget({
      widget_type: 'bar', title: `By ${node.name || node.column_name}`, reason: '',
      config: { dimension: node.column_name, hierarchyNodeId: node.id,
        aggregation: 'count',
        ...(node.format ? { dimension_granularity: node.format } : {}) },
    })
  }

  /** Which field's geography menu is open, and the org's uploaded boundary
   *  sets to choose from. Loaded once the menu is first opened rather than on
   *  every builder mount: most reports have no geography at all. */
  /** Columns classified as geography, as the renderers want them. Derived from
   *  `columnMeta` rather than stored twice: the classification is authored here
   *  and must take effect the moment it changes, not on the next reload. The
   *  shared link and the embed get the same mapping from their own payloads. */
  const geography = useMemo(() => {
    const out: Record<string, number> = {}
    for (const [column, meta] of Object.entries(columnMeta)) {
      if (column.startsWith('__')) continue
      const m = meta as { role?: string; boundary_set_id?: number }
      if (m?.role === 'geography' && typeof m.boundary_set_id === 'number') {
        out[column] = m.boundary_set_id
      }
    }
    return out
  }, [columnMeta])

  /** What the author typed to find a chart. 67 widget types grouped into
   *  categories is still 67 buttons to scroll, and the properties panel beside
   *  this one already searches its settings. */
  const [paletteQuery, setPaletteQuery] = useState('')

  const [geoField, setGeoField] = useState<string | null>(null)
  /** The validation panel for a pending geography classification: the author
   *  sees the match rate and the unmatched values BEFORE it is saved. */
  const [geoCheck, setGeoCheck] = useState<{ column: string; setId: number; setName: string } | null>(null)
  const [boundarySets, setBoundarySets] = useState<{ id: number; name: string }[]>([])
  /** Starter packs not yet installed in the org, offered in the same menu so
   *  "these are Egyptian governorates" is one click even with nothing uploaded. */
  const [boundaryPacks, setBoundaryPacks] = useState<BoundaryPack[]>([])
  /** A pack whose source attaches terms (EU NUTS): shown in the menu until
   *  accepted, never installed on the one click that opened it. */
  const [packTerms, setPackTerms] = useState<{ column: string; pack: BoundaryPack } | null>(null)
  const installPackAndCheck = async (column: string, pack: BoundaryPack, accepted = false) => {
    if (pack.requires_acceptance && !accepted) { setPackTerms({ column, pack }); return }
    setGeoField(null)
    setPackTerms(null)
    try {
      const made = await boundarySetsApi.installPack(pack.id, accepted)
      setBoundarySets(prev => [...prev, { id: made.id, name: made.name }])
      setBoundaryPacks(prev => prev.filter(p => p.id !== pack.id))
      setGeoCheck({ column, setId: made.id, setName: made.name })
    } catch (e) {
      toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        ?? `Could not install ${pack.name}`)
    }
  }

  /** Write the dataset's column metadata as one undoable step. */
  const setColumnMetaUndoable = async (dsId: number, next: Record<string, ColumnMeta>, label: string) => {
    const prev: Record<string, ColumnMeta> = {}
    for (const [k, v] of Object.entries(columnMeta)) if (!k.startsWith('__')) prev[k] = { ...(v as ColumnMeta) }
    const saved = await columnMetaApi.set(dsId, next)
    setColumnMeta(saved)
    pushUndo({ label,
      undo: async () => { setColumnMeta(await columnMetaApi.set(dsId, prev)) },
      redo: async () => { setColumnMeta(await columnMetaApi.set(dsId, next)) } })
    return saved
  }

  /** Classify a column as geography drawn with a given boundary set, or clear
   *  the classification. Stored in column_meta beside the other data-item
   *  properties, so it travels with the DATASET rather than with one report. */
  const classifyGeography = async (columnName: string, setId: number | null) => {
    if (!report?.dataset_id) return
    const meta: Record<string, ColumnMeta> = {}
    for (const [k, v] of Object.entries(columnMeta)) {
      if (!k.startsWith('__')) meta[k] = { ...(v as ColumnMeta) }
    }
    const entry = { ...(meta[columnName] ?? {}) }
    if (setId == null) {
      delete entry.role
      delete entry.boundary_set_id
    } else {
      entry.role = 'geography'
      entry.boundary_set_id = setId
    }
    if (Object.keys(entry).length === 0) delete meta[columnName]
    else meta[columnName] = entry
    setGeoField(null)
    try {
      await setColumnMetaUndoable(report.dataset_id, meta,
        setId == null ? `Make ${columnName} an ordinary category` : `Make ${columnName} geography`)
      toast.success(setId == null
        ? `${columnName} is an ordinary category again`
        : `${columnName} is geography`)
    } catch { toast.error('Could not save the classification') }
  }

  /** Narrows the field list. SAS's Data pane has had one since forever, and a
   *  dataset of forty columns is unusable without it. */
  const [fieldFilter, setFieldFilter] = useState('')

  /** Fields gathered with ctrl/cmd-click, charted together on one drop. A plain
   *  click still assigns a single field to the selected widget, because that is
   *  what the field list has always done and is what most clicks mean. */
  const [gatheredFields, setGatheredFields] = useState<string[]>([])

  /** Which field's one-click calculation menu is open. SAS offers these from
   *  the data item, and the honest result is a MEASURE: it evaluates at the
   *  requesting widget's grain, so a percent-of-total re-bases when the
   *  crossing changes -- which a row-level calculated column cannot. */
  const [quickCalcField, setQuickCalcField] = useState<string | null>(null)
  // A menu that only its own button can close outlives everything the author
  // does next (found: it stayed open through ten unrelated clicks). Outside
  // click and Escape close it, like every other menu.
  useEffect(() => {
    if (!quickCalcField) return
    const onDown = (e: MouseEvent) => {
      if (!(e.target as HTMLElement | null)?.closest?.('[data-quickcalc-menu]')) setQuickCalcField(null)
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setQuickCalcField(null) }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey) }
  }, [quickCalcField])

  const runQuickCalc = async (columnName: string, key: string) => {
    const col = columns.find(c => c.name === columnName)
    if (!col) return
    const choice = quickCalcsFor(
      { name: col.name, dtype: col.dtype, numeric: isNumericField(col) })
      .find(c => c.key === key)
    setQuickCalcField(null)
    if (!choice) return
    // Never overwrite: measuresApi.save upserts by name, so a collision would
    // silently replace somebody else's definition.
    const name = uniqueMeasureName(choice.name, measures.map(m => m.name))
    try {
      const dsId = dataset!.id
      const def = { name, expression: choice.expression }
      const next = await measuresApi.save(dsId, def)
      setMeasures(next)
      pushUndo({ label: `Add measure "${name}"`,
        undo: async () => { setMeasures(await measuresApi.delete(dsId, name)) },
        redo: async () => { setMeasures(await measuresApi.save(dsId, def)) } })
      toast.success(`Added measure "${name}"`)
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      toast.error(detail || 'Could not add the calculation')
    }
  }

  const toAutoField = (name: string): AutoField | null => {
    const col = columns.find(c => c.name === name)
    // `geography` comes from the same classification the renderers read, so a
    // column an author marked as geography drops as a map instead of a bar --
    // which is the point of assigning the role at all.
    return col ? {
      name: col.name, dtype: col.dtype, numeric: isNumericField(col),
      geography: geography[col.name] != null,
    } : null
  }

  /** One chart from however many fields were dropped. Fields the rule could not
   *  place are NAMED rather than silently left out -- a chart quietly built from
   *  half a drop is a wrong answer wearing the shape of a right one. */
  const addWidgetFromFields = async (names: string[]) => {
    if (!activePage) return
    const fields = names.map(toAutoField).filter(Boolean) as AutoField[]
    const choice = chartForFields(fields)
    setGatheredFields([])
    if (!choice) return
    await addSuggestedWidget(choice.suggestion as Suggestion)
    if (choice.ignored.length) {
      toast(`${choice.ignored.join(', ')} could not be used in this chart`)
    }
  }

  // One field and several now share one rule table (lib/autoChart.ts): two
  // copies of "what should this become" would drift, and the single-field rules
  // are the ones people already rely on.
  const addWidgetFromField = async (columnName: string) => addWidgetFromFields([columnName])

  const addSuggestedWidget = async (sug: Suggestion) => {
    if (!activePage) return toast.error('Select a page first')
    const ws = activePage.widgets
    const maxY = ws.length ? Math.max(...ws.map(w => w.layout.y + w.layout.h)) : 0
    setSaving(true)
    try {
      const widget = await reportsApi.addWidget(reportId, activePage.id, {
        widget_type: sug.widget_type as WidgetType,
        title: sug.title,
        config: sug.config,
        layout: { x: 0, y: maxY, w: Math.max(6, minSize(sug.widget_type).w), h: Math.max(5, minSize(sug.widget_type).h) },
      })
      {
        // A chart made from a field is an edit like any other: one Ctrl+Z away.
        const pageId = activePage.id
        const snap: Partial<Widget> = { widget_type: sug.widget_type as WidgetType, title: sug.title, config: sug.config, layout: widget.layout }
        pushUndo({
          label: `Add ${sug.title}`,
          undo: () => removeWidgetById(pageId, widget.id),
          redo: async () => { await recreateWidget(pageId, widget.id, snap) },
        })
      }
      if (isPackedMode(activePage.layout_mode) && !needsAutoPack(activePage.layout_mode)) {
        const nextWidgets = [...ws, widget]
        await persistWidgetLayouts(
          { ...activePage, widgets: nextWidgets },
          compact(toLayoutItems(nextWidgets)),
        )
      }
      await loadReport()
      setSelectedW(widget)
      toast.success(`${sug.title} added`)
    } finally {
      setSaving(false)
    }
  }

  const applyAlign = async (mode: Parameters<typeof alignWidgets>[1]) => {
    if (!activePage) return
    const selected = pageWidgets.filter(w => multiSelectedIds.has(w.id))
    const layoutMap = Object.fromEntries(selected.map(w => [w.id, w.layout]))
    const patch = alignWidgets(layoutMap, mode)
    const merged = pageWidgets.map(w => ({
      ...w,
      layout: patch[w.id] ? { ...w.layout, ...patch[w.id] } : w.layout,
    }))
    const layouts = isPackedMode(activePage.layout_mode)
      ? compact(toLayoutItems(merged))
      : Object.fromEntries(merged.map(w => [w.id, w.layout]))
    await persistWidgetLayouts(activePage, layouts, undefined, `Align ${selected.length} widgets`)
  }
  const applyDistribute = async (axis: Parameters<typeof distributeWidgets>[1]) => {
    if (!activePage) return
    const selected = pageWidgets.filter(w => multiSelectedIds.has(w.id))
    const layoutMap = Object.fromEntries(selected.map(w => [w.id, w.layout]))
    const patch = distributeWidgets(layoutMap, axis)
    const merged = pageWidgets.map(w => ({
      ...w,
      layout: patch[w.id] ? { ...w.layout, ...patch[w.id] } : w.layout,
    }))
    const layouts = isPackedMode(activePage.layout_mode)
      ? compact(toLayoutItems(merged))
      : Object.fromEntries(merged.map(w => [w.id, w.layout]))
    await persistWidgetLayouts(activePage, layouts, undefined, `Distribute ${selected.length} widgets`)
  }

  // Per-widget query performance, reported by WidgetRenderer after each fetch; surfaced
  // read-only in the Performance right-panel mode, slowest widget first.
  const [perfStats, setPerfStats] = useState<Record<number, { durationMs: number; rowCount: number; sampled: boolean; ruleErrors?: { id?: string; message: string }[] }>>({})
  // Fetch completions are batched through a ref + one trailing flush: N
  // widgets finishing a page load used to mean N setPerfStats calls, each
  // re-rendering the whole builder and therefore every widget -- O(N^2)
  // renders. Consumers (Performance pane, ReviewPane, config panel) read the
  // state exactly as before, just ~150ms later.
  const perfStatsRef = useRef<Record<number, { durationMs: number; rowCount: number; sampled: boolean; ruleErrors?: { id?: string; message: string }[] }>>({})
  const perfFlushTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const handleFetchComplete = useCallback((id: number, info: { durationMs: number; rowCount: number; sampled: boolean; ruleErrors?: { id?: string; message: string }[] }) => {
    perfStatsRef.current[id] = info
    if (perfFlushTimer.current == null) {
      perfFlushTimer.current = setTimeout(() => {
        perfFlushTimer.current = null
        setPerfStats(p => ({ ...p, ...perfStatsRef.current }))
      }, 150)
    }
  }, [])
  useEffect(() => () => { if (perfFlushTimer.current != null) clearTimeout(perfFlushTimer.current) }, [])

  // Report-rule errors arrive per-widget (WidgetRenderer reports rule_errors from its
  // own query result via onFetchComplete -> perfStats[id].ruleErrors), because that's
  // where the engine actually evaluates them -- there is no single "report rules"
  // fetch. DisplayRulesPanel matches errors to rules by id, so without this the
  // report-rules pane always showed no errors, even though a report rule (which can
  // only offer ['name','value'] as columns) errors on every table/crosstab widget.
  // Aggregated across widgets and de-duped by rule id, filtered to ids that are
  // actually report-level rules (a widget-level rule sharing an id would be a
  // coincidence, not a report-rule error).
  const reportRuleErrors = useMemo(() => {
    const reportRuleIds = new Set((report?.display_rules ?? []).map(r => r.id))
    if (reportRuleIds.size === 0) return undefined
    const byId = new Map<string, { id?: string; message: string }>()
    for (const stat of Object.values(perfStats)) {
      for (const err of stat.ruleErrors ?? []) {
        if (err.id && reportRuleIds.has(err.id) && !byId.has(err.id)) byId.set(err.id, err)
      }
    }
    return byId.size > 0 ? Array.from(byId.values()) : undefined
  }, [report?.display_rules, perfStats])

  // Drillthrough reuses the existing per-page prompt-filter mechanism (promptValues +
  // ReportPage.prompt_column) rather than inventing a second filter-seeding path.
  const handleDrillthrough = useCallback((targetPageId: number, filterValue: unknown) => {
    const target = report?.pages.find(p => p.id === targetPageId)
    if (!target) return
    // A pop-up target opens OVER the page the reader is on (SAS's drill to a
    // pop-up page), seeded with the clicked value through its prompt, and
    // closing it returns them exactly where they were.
    if (!editMode && target.page_type === 'popup') {
      if (target.prompt_column) setPromptValues(p => ({ ...p, [target.id]: String(filterValue) }))
      setPopupPage(target)
      return
    }
    setActivePage(target)
    setSelectedW(null)
    if (target.prompt_column) setPromptValues(p => ({ ...p, [target.id]: String(filterValue) }))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [report, editMode])

  // A popup page renders as a modal OVER the current page in view mode, rather than
  // switching the active tab to it (Power BI / SAS popup-page semantics) -- edit mode
  // is unaffected: authors still land on it as a normal tab so they can edit it.
  const [popupPage, setPopupPage] = useState<ReportPage | null>(null)
  useEffect(() => { if (editMode) setPopupPage(null) }, [editMode])
  // Any OTHER navigation away from the underlying page (tab click, bookmark apply,
  // ...) should drop a stray popup rather than leave it floating over a page it
  // no longer belongs to. Opening the popup itself never touches activePage, so
  // this never fires as a side-effect of the open.
  useEffect(() => { setPopupPage(null) }, [activePage?.id])

  const handleButtonNavigate = useCallback((pageId: number) => {
    const target = report?.pages.find(p => p.id === pageId)
    if (!target) return
    if (!editMode && target.page_type === 'popup') { setPopupPage(target); return }
    setActivePage(target); setSelectedW(null)
  }, [report, editMode])

  // Tooltip-page hover (view mode only): a widget bound via config.tooltipPageId
  // floats that page's widgets in a small panel near the cursor after a short
  // delay, Power BI / SAS "report page tooltip" style. Not modal -- dismissed on
  // mouseleave rather than an explicit close, and it never touches activePage.
  const [tooltipHover, setTooltipHover] = useState<{ widgetId: number; page: ReportPage; x: number; y: number } | null>(null)
  const tooltipTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const clearTooltipTimer = useCallback(() => {
    if (tooltipTimerRef.current != null) { clearTimeout(tooltipTimerRef.current); tooltipTimerRef.current = null }
  }, [])
  const handleTooltipEnter = useCallback((widget: Widget, e: React.MouseEvent) => {
    const tooltipPageId = (widget.config as { tooltipPageId?: number }).tooltipPageId
    if (tooltipPageId == null) return
    const page = report?.pages.find(p => p.id === tooltipPageId && p.page_type === 'tooltip')
    if (!page) return
    const x = e.clientX, y = e.clientY
    clearTooltipTimer()
    tooltipTimerRef.current = setTimeout(() => {
      setTooltipHover({ widgetId: widget.id, page, x, y })
    }, 300)
  }, [report, clearTooltipTimer])
  const handleTooltipLeave = useCallback((widgetId: number) => {
    clearTooltipTimer()
    setTooltipHover(cur => (cur?.widgetId === widgetId ? null : cur))
  }, [clearTooltipTimer])
  useEffect(() => { if (editMode) { clearTooltipTimer(); setTooltipHover(null) } }, [editMode, clearTooltipTimer])
  useEffect(() => { clearTooltipTimer(); setTooltipHover(null) }, [activePage?.id, clearTooltipTimer])
  useEffect(() => clearTooltipTimer, [clearTooltipTimer])

  // Handles the non-cross-filter side of a button-triggered bookmark apply --
  // the cross-filter emission itself already happened in WidgetRenderer, which
  // has its own useCrossFilter() access (ReportBuilder's own body doesn't,
  // see SyncSlicersPaneConnected/BookmarksPaneConnected above for why).
  const handleButtonApplyBookmark = useCallback(async (bookmark: Bookmark) => {
    if (!report) return
    const target = report.pages.find(p => p.id === bookmark.state.pageId)
    if (!target) return
    setActivePage(target)
    setPromptValues(p => ({ ...p, ...bookmark.state.promptValues }))
    const hiddenSet = new Set(bookmark.state.hiddenWidgetIds)
    // A viewer may APPLY a bookmark (it is navigation), but persisting which
    // widgets are hidden is an edit the server refuses -- so for them the
    // page and prompt values move and the layout is left alone, rather than
    // firing PUTs that 403 behind their back.
    if (!canEdit) return
    const toFix = target.widgets.filter(w => !!(w.config as any).hidden !== hiddenSet.has(w.id))
    await Promise.all(toFix.map(w =>
      reportsApi.updateWidget(reportId, target.id, w.id, { config: { ...w.config, hidden: hiddenSet.has(w.id) } })
    ))
    if (toFix.length > 0) await loadReport()
  }, [report, reportId, loadReport, canEdit])

  // Undo/redo as the toolbar and the keyboard run them: toast the sentence, and
  // drop the selection -- it may name a widget the step just removed.
  const runUndo = async () => {
    const label = await undoStack.undo()
    if (label) { setSelectedW(null); toast.success(`Undone: ${label}`) }
  }
  const runRedo = async () => {
    const label = await undoStack.redo()
    if (label) { setSelectedW(null); toast.success(`Redone: ${label}`) }
  }
  // "Assign data" on an unfinished widget: select it and bring its settings
  // up (the panel itself switches to Data roles on the same event).
  const [rightOpenSignal, setRightOpenSignal] = useState(0)
  useEffect(() => {
    const onAssign = (e: Event) => {
      const id = (e as CustomEvent<{ widgetId: number }>).detail?.widgetId
      const w = activePage?.widgets.find(x => x.id === id)
      if (!w) return
      setRightPanelMode('default')
      setMultiSelectedIds(new Set())
      setSelectedW(w)
      setRightOpenSignal(n => n + 1)
    }
    window.addEventListener(ASSIGN_DATA_EVENT, onAssign)
    return () => window.removeEventListener(ASSIGN_DATA_EVENT, onAssign)
  }, [activePage])
  // "Add data", from anywhere (an empty role picker, the empty page): open the
  // dataset list WHERE IT LIVES -- the Fields tab. The empty page's button used
  // to open the menu without switching tabs, so with the left panel on Charts
  // or More (it remembers) the click did nothing a person could see: a dead
  // end on the very first step of building a dashboard.
  const openDatasetPicker = () => {
    setLeftTab('fields')
    setShowDsMenu(true)
    datasetsApi.list().then(setAllDatasets).catch(() => {})
    requestAnimationFrame(() => document.getElementById('add-dataset-button')?.scrollIntoView?.({ block: 'center' }))
  }
  useEffect(() => {
    const onAdd = () => openDatasetPicker()
    window.addEventListener(ADD_DATASET_EVENT, onAdd)
    return () => window.removeEventListener(ADD_DATASET_EVENT, onAdd)
  }, [])
  // A one-click fix offered ON a widget (e.g. "Show all" under a truncated
  // chart): an ordinary config edit, so it is undoable like any other.
  useEffect(() => {
    const onPatch = async (e: Event) => {
      const d = (e as CustomEvent<{ widgetId: number; patch: Record<string, unknown>; label: string }>).detail
      const page = report?.pages.find(pg => (pg.widgets ?? []).some(w => w.id === d?.widgetId))
      const w = page?.widgets?.find(x => x.id === d.widgetId)
      if (!page || !w) return
      const before = (w.config ?? {}) as Record<string, unknown>
      const after = { ...before, ...d.patch }
      const write = (c: Record<string, unknown>) =>
        reportsApi.updateWidget(reportId, pid(page.id), widgetIds.current.resolve(w.id), { config: c }).then(() => {})
      await write(after)
      pushUndo({ label: d.label, undo: () => write(before), redo: () => write(after) })
      await loadReport()
    }
    window.addEventListener(PATCH_WIDGET_EVENT, onPatch)
    return () => window.removeEventListener(PATCH_WIDGET_EVENT, onPatch)
  }, [report, reportId, pushUndo, loadReport])
  // Session recovery: settings-panel edits still in the journal when the
  // report opens never reached the server (the tab closed inside the panel's
  // 600 ms batch). Offered once per open, editors only, and only where the
  // journal actually differs from what is saved.
  const [recoverable, setRecoverable] = useState<PendingEdit[]>([])
  const recoveryChecked = useRef<number | null>(null)
  useEffect(() => {
    if (!report || !canEdit || recoveryChecked.current === report.id) return
    recoveryChecked.current = report.id
    const widgets = report.pages.flatMap(pg => pg.widgets ?? [])
    const byId = new Map(widgets.map(w => [w.id, w]))
    const found = readPending(widgets.map(w => w.id)).filter(e => {
      const w = byId.get(e.widgetId)
      const differs = !!w && (changedKeys((w.config ?? {}) as Record<string, unknown>, e.config).length > 0 || w.title !== e.title)
      if (!differs) clearPending(e.widgetId)
      return differs
    })
    setRecoverable(found)
  }, [report, canEdit])
  const restorePending = async () => {
    if (!report) return
    const items = recoverable.map(e => {
      const page = report.pages.find(pg => (pg.widgets ?? []).some(w => w.id === e.widgetId))
      const w = page?.widgets?.find(x => x.id === e.widgetId)
      return page && w ? { e, pageId: page.id, before: { config: (w.config ?? {}) as Record<string, unknown>, title: w.title } } : null
    }).filter((x): x is NonNullable<typeof x> => !!x)
    const apply = (which: 'before' | 'after') => Promise.all(items.map(({ e, pageId, before }) =>
      reportsApi.updateWidget(reportId, pid(pageId), widgetIds.current.resolve(e.widgetId),
        which === 'after' ? { config: e.config, title: e.title } : before))).then(() => {})
    await apply('after')
    pushUndo({ label: `Restore unsaved changes to ${items.length} widget${items.length === 1 ? '' : 's'}`,
      undo: () => apply('before'), redo: () => apply('after') })
    recoverable.forEach(e => clearPending(e.widgetId))
    setRecoverable([])
    await loadReport()
    toast.success('Unsaved changes restored')
  }
  const discardPending = () => { recoverable.forEach(e => clearPending(e.widgetId)); setRecoverable([]) }
  // A dashboard just created from "New dashboard" arrives with ?pick=data: ask
  // for its data first, in the picker, instead of a blank canvas. Once only --
  // the parameter is removed so a reload does not ask again.
  // A dashboard created a moment ago by "New dashboard" and left without any
  // content (no data, no widgets, default name) is removed on the way out,
  // so trying the button leaves nothing behind. Only the one this tab just
  // made -- never an existing dashboard, and never one with anything in it.
  const reportRef = useRef<Report | null>(null)
  reportRef.current = report
  useEffect(() => () => {
    let fresh: string | null = null
    try { fresh = sessionStorage.getItem('datalytics:fresh-report') } catch { /* */ }
    if (fresh !== String(reportId)) return
    const r = reportRef.current
    if (!r) return
    const empty = !r.dataset_id && r.pages.every(p => p.widgets.length === 0) && /^Untitled dashboard( \d+)?$/.test(r.name)
    try { sessionStorage.removeItem('datalytics:fresh-report') } catch { /* */ }
    if (empty) reportsApi.delete(r.id).catch(() => { /* best effort */ })
  }, [reportId])

  // The parameter is removed when the picker CLOSES, not when it opens: React
  // StrictMode mounts twice in development, and stripping it on open meant
  // the second mount found no parameter and the picker never appeared.
  const pickerOpenedForNew = useRef(false)
  useEffect(() => {
    if (!report || !canEdit) return
    const params = new URLSearchParams(window.location.search)
    if (params.get('pick') !== 'data') return
    if (report.dataset_id) { stripPickParam(); return }
    datasetsApi.list().then(setAllDatasets)
    setShowDsMenu(true)
    pickerOpenedForNew.current = true
  }, [report, canEdit])
  useEffect(() => {
    if (!showDsMenu && pickerOpenedForNew.current) { pickerOpenedForNew.current = false; stripPickParam() }
  }, [showDsMenu])
  // Rename in place: a new dashboard is "Untitled dashboard" until its author
  // knows what it is -- the name is edited where it is read, and undoable.
  const [renaming, setRenaming] = useState(false)
  const navigate = useNavigate()
  /** Reports open in this session (SAS's "Opened reports (N)"), for one-click switching. */
  const [openReports, setOpenReports] = useState<OpenReport[]>(() => readOpen())
  const [pdfDialog, setPdfDialog] = useState(false)
  useEffect(() => {
    if (report?.id != null) setOpenReports(markOpen({ id: report.id, name: report.name }))
  }, [report?.id, report?.name])
  const commitRename = async (raw: string) => {
    setRenaming(false)
    const next = raw.trim()
    if (!report || !next || next === report.name) return
    const before = report.name
    const write = (name: string) => reportsApi.update(report.id, { name }).then(() => {})
    // Shown at once, not after the reload: saving on blur used to leave the
    // OLD name in the header (a reload raced it) while the server, the tab
    // strip and the Dashboards list already had the new one.
    setReport(r => r ? { ...r, name: next } : r)
    try {
      await write(next)
    } catch (e: any) {
      setReport(r => r ? { ...r, name: before } : r)
      toast.error(e?.response?.data?.detail ?? 'Could not rename the dashboard')
      return
    }
    toast.success('Renamed')
    pushUndo({ label: `Rename dashboard "${before}" to "${next}"`, undo: () => write(before), redo: () => write(next) })
    await loadReport()
  }
  const runUndoRef = useRef(runUndo)
  const runRedoRef = useRef(runRedo)
  runUndoRef.current = runUndo
  runRedoRef.current = runRedo

  // ── Keyboard shortcuts (edit mode) ──────────────────────────────────────────
  // Arrows nudge the selected widget one grid cell (Shift resizes), Delete removes
  // it, Escape deselects, ? opens the reference. Bound at the document so the canvas
  // needs no focus, but every handler bails inside form fields -- an author typing
  // "?" into a text block must not open a dialog.
  useEffect(() => {
    if (!editMode) return
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable) return
      if (e.key === '?') { e.preventDefault(); setShortcutsOpen(o => !o); return }
      const mod = e.ctrlKey || e.metaKey
      if (mod && e.key.toLowerCase() === 'z') { e.preventDefault(); void (e.shiftKey ? runRedoRef.current() : runUndoRef.current()); return }
      if (mod && e.key.toLowerCase() === 'y') { e.preventDefault(); void runRedoRef.current(); return }
      if (e.key === 'Escape') { setSelectedW(null); setShortcutsOpen(false); return }
      if (!selectedW || !activePage) return
      const arrows: Record<string, [number, number]> = {
        ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1],
      }
      if (e.key in arrows) {
        e.preventDefault()
        const [dx, dy] = arrows[e.key]
        const items = toLayoutItems(activePage.widgets)
        const packed = isPackedMode(activePage.layout_mode)
        const next = e.shiftKey
          ? (packed
            ? resizePacked(items, selectedW.id, selectedW.layout.w + dx, selectedW.layout.h + dy)
            : resizeFree(items, selectedW.id, selectedW.layout.w + dx, selectedW.layout.h + dy))
          : (packed
            ? dropPacked(items, selectedW.id, { x: selectedW.layout.x + dx, y: selectedW.layout.y + dy })
            : dropFree(items, selectedW.id, { x: selectedW.layout.x + dx, y: selectedW.layout.y + dy }))
        void persistWidgetLayouts(activePage, next, undefined,
          `${e.shiftKey ? 'Resize' : 'Move'} "${selectedW.title || selectedW.widget_type}"`)
        if (next[selectedW.id]) setSelectedW({ ...selectedW, layout: next[selectedW.id] })
      } else if (e.key === 'Delete' || e.key === 'Backspace') {
        e.preventDefault()
        deleteWidget(selectedW)
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [editMode, selectedW, activePage, persistWidgetLayouts])

  // ── Kiosk playback ──────────────────────────────────────────────────────────
  useEffect(() => {
    document.documentElement.dataset.presenting = kiosk ? '1' : ''
    window.dispatchEvent(new CustomEvent('datalytics:present', { detail: kiosk }))
    if (!kiosk) {
      delete document.documentElement.dataset.presenting
    }
    return () => {
      delete document.documentElement.dataset.presenting
      window.dispatchEvent(new CustomEvent('datalytics:present', { detail: false }))
    }
  }, [kiosk])

  useEffect(() => {
    if (!kiosk || !report) return
    const id = setInterval(() => {
      setActivePage(prev => {
        const pages = report.pages.filter(p => p.page_type === 'normal')
        if (pages.length < 2) return prev
        const i = pages.findIndex(p => p.id === prev?.id)
        return pages[(i + 1) % pages.length]
      })
    }, 8000)
    const exit = () => setKiosk(false)
    document.addEventListener('keydown', exit)
    return () => { clearInterval(id); document.removeEventListener('keydown', exit) }
  }, [kiosk, report])

  /** SAS's Duplicate Object: another one of these, beside it.
   *
   *  Distinct from a widget template, which is for reuse ACROSS reports. The
   *  copy carries the whole config -- roles, formatting, rules, filters, ranks,
   *  sorting -- because everything that makes the original worth copying lives
   *  there, and it lands BELOW the original rather than on top of it: placed at
   *  the same coordinates it would be invisible, and the author would think
   *  nothing had happened and press it again.
   */
  const duplicateWidget = async (w: Widget) => {
    if (!activePage) return
    setSaving(true)
    try {
      const copy = await reportsApi.addWidget(reportId, activePage.id, {
        widget_type: w.widget_type,
        title: `${w.title || w.widget_type} (copy)`,
        // A table made before the totals defaults changed carries neither key, and
        // the server stamps NEW tables with the new defaults -- so the copy states
        // the defaults its original was built with, or it would render differently.
        config: {
          ...(['table', 'crosstab', 'matrix'].includes(w.widget_type)
            ? { show_subtotals: true, totals_position: 'after' } : {}),
          ...(w.config as Record<string, unknown>),
        },
        layout: { ...w.layout, y: w.layout.y + w.layout.h },
      })
      {
        const pageId = activePage.id
        const snap: Partial<Widget> = { widget_type: copy.widget_type, title: copy.title, config: copy.config, layout: copy.layout }
        pushUndo({
          label: `Duplicate "${w.title || w.widget_type}"`,
          undo: () => removeWidgetById(pageId, copy.id),
          redo: async () => { await recreateWidget(pageId, copy.id, snap) },
        })
      }
      if (isPackedMode(activePage.layout_mode) && !needsAutoPack(activePage.layout_mode)) {
        const nextWidgets = [...activePage.widgets, copy]
        await persistWidgetLayouts(
          { ...activePage, widgets: nextWidgets },
          compact(toLayoutItems(nextWidgets)),
        )
      }
      await loadReport()
      setSelectedW(copy)
      toast.success('Duplicated')
    } catch {
      toast.error('Could not duplicate this widget')
    } finally {
      setSaving(false)
    }
  }

  const deleteWidget = async (w: Widget) => {
    if (!activePage) return
    setSaving(true)
    try {
      await reportsApi.deleteWidget(reportId, activePage.id, w.id)
      {
        const pageId = activePage.id
        const snap: Partial<Widget> = { widget_type: w.widget_type, title: w.title, config: w.config, layout: w.layout }
        pushUndo({
          label: `Delete "${w.title || w.widget_type}"`,
          undo: async () => { await recreateWidget(pageId, w.id, snap) },
          redo: () => removeWidgetById(pageId, w.id),
        })
      }
      if (selectedW?.id === w.id) setSelectedW(null)
      const remaining = activePage.widgets.filter(x => x.id !== w.id)
      if (isPackedMode(activePage.layout_mode) && !needsAutoPack(activePage.layout_mode)) {
        await persistWidgetLayouts(
          { ...activePage, widgets: remaining },
          compact(toLayoutItems(remaining)),
        )
      }
      await loadReport()
    } finally {
      setSaving(false)
    }
  }

  // ── Stable per-widget callbacks (render discipline) ────────────────────────
  // WidgetRenderer is React.memo'd; that only helps if its props keep their
  // identity between unrelated renders. Handlers route through refs holding
  // the LATEST implementation, so the callback identities never change while
  // the behavior always tracks current state.
  const widgetActionsRef = useRef({ deleteWidget, duplicateWidget, selectWidget: (w: Widget, e: React.MouseEvent) => {
    if (e.shiftKey) {
      setMultiSelectedIds(prev => { const next = new Set(prev); next.has(w.id) ? next.delete(w.id) : next.add(w.id); return next })
    } else {
      setSelectedW(w)
      setMultiSelectedIds(new Set())
    }
  } })
  // Both refreshed every render, not just seeded in the initial ref value: the
  // one in the initial value is a closure over the FIRST render, where
  // `activePage` is still null and the action returns immediately.
  widgetActionsRef.current.deleteWidget = deleteWidget
  widgetActionsRef.current.duplicateWidget = duplicateWidget
  const stableOnSetParameter = useCallback((name: string, value: string) =>
    setParamValues(prev => ({ ...prev, [name]: value })), [])

  const updateWidgetConfig = useCallback(async (config: Record<string, unknown>, title: string) => {
    if (!selectedW || !activePage) return
    const before = activePage.widgets.find(x => x.id === selectedW.id) ?? selectedW
    const beforeCfg = (before.config ?? {}) as Record<string, unknown>
    const beforeTitle = before.title
    setSaving(true)
    try {
      await reportsApi.updateWidget(reportId, activePage.id, selectedW.id, { config, title })
      const keys = changedKeys(beforeCfg, config)
      if (keys.length || beforeTitle !== title) {
        const pageId = activePage.id
        const id = selectedW.id
        const write = (c: Record<string, unknown>, t: string) =>
          reportsApi.updateWidget(reportId, pid(pageId), widgetIds.current.resolve(id), { config: c, title: t }).then(() => {})
        pushUndo({
          label: describeConfigChange(beforeTitle || before.widget_type, beforeCfg, config, beforeTitle, title),
          // One step per burst of edits to the same setting (typing a title).
          coalesceKey: `cfg:${id}:${keys.join(',')}:${beforeTitle !== title}`,
          undo: () => write(beforeCfg, beforeTitle),
          redo: () => write(config, title),
        })
      }
      await loadReport()
    } finally {
      setSaving(false)
    }
  }, [selectedW, activePage, reportId, loadReport, pushUndo])

  /** Write one widget's interaction into its own config.
   *
   *  The Interactions panel used to change React state and nothing else, so
   *  every direction, receive mode and per-pair action was lost on reload.
   *  `config.interaction` is the widget's own JSON, so this is the PATCH the
   *  builder already makes for every other setting -- no new column, no
   *  migration. The report is NOT reloaded afterwards: the provider already
   *  holds the new value, and a reload here would remount the canvas under the
   *  user mid-click.
   */
  const persistInteraction = useCallback(async (widgetId: number, interaction: unknown) => {
    const page = report?.pages.find(pg => (pg.widgets ?? []).some(w => w.id === widgetId))
    const widget = page?.widgets?.find(w => w.id === widgetId)
    if (!page || !widget) return
    await reportsApi.updateWidget(reportId, page.id, widgetId, {
      config: { ...(widget.config ?? {}), interaction },
    } as never)
  }, [report, reportId])

  const isNumericRole = (rf: RoleField) => /numeric/i.test(rf.label ?? '') || rf.role.startsWith('measure') || rf.role === 'size'

  // SAS's 'change classification' / PBI's summarization override: flip a column
  // between measure and category. Detection stays the truth of dtype; the role
  // is an OVERRIDE stored in column_meta, so flipping back to the detected
  // default removes the key rather than pinning it. Only numeric columns can
  // become measures -- there is no sum of a text column.
  const flipFieldRole = async (c: DatasetColumn) => {
    if (!report?.dataset_id) return
    const next = isNumericField(c) ? 'category' : 'measure'
    if (next === 'measure' && c.dtype !== 'numeric') return
    const detectedDefault = c.dtype === 'numeric' ? 'measure' : 'category'
    const meta: Record<string, ColumnMeta> = {}
    for (const [k, v] of Object.entries(columnMeta)) {
      if (!k.startsWith('__')) meta[k] = { ...(v as ColumnMeta) }
    }
    const entry = { ...(meta[c.name] ?? {}) }
    if (next === detectedDefault) delete entry.role
    else entry.role = next
    if (Object.keys(entry).length === 0) delete meta[c.name]
    else meta[c.name] = entry
    await setColumnMetaUndoable(report.dataset_id, meta,
      `Make ${c.name} a ${next === 'measure' ? 'measure' : 'category'}`)
    toast.success(`${c.name} is now a ${next === 'measure' ? 'measure' : 'category'}`)
  }

  /** Where a field would go on this widget: the config with it placed in the
   *  next empty compatible role, and that role's name -- or null when the
   *  widget has no empty role left. One rule for click-to-assign and for a
   *  drop onto the widget, so the two gestures can never disagree. */
  const planFieldOnWidget = useCallback((w: Widget, columnName: string, isNumericField: boolean) => {
    const specs = (ROLE_SPECS[w.widget_type] ?? []).filter(rf => !rf.multi)
    const cfg = w.config as Record<string, unknown>
    const empty = specs.filter(rf => !cfg[configKeyFor(rf.role)])
    if (empty.length === 0) return null
    const target = empty.find(rf => isNumericRole(rf) === isNumericField) ?? empty.find(rf => rf.required) ?? empty[0]
    const next = { ...cfg, [configKeyFor(target.role)]: columnName }
    // The point of classifying a column as geography: a map built from it draws
    // the right shapes without the author choosing them again. Applied here,
    // beside the default aggregation, so the choice is visible and editable in
    // the config panel rather than resolved invisibly at query time.
    const geoSet = columnMeta[columnName]?.boundary_set_id
    if (geoSet != null && w.widget_type.startsWith('map_')
        && next.boundary_set_id == null) {
      next.boundary_set_id = geoSet
    }
    // A column's default aggregation is applied here rather than at query time, so
    // the resulting choice is visible and editable in the widget config panel
    // instead of being an invisible server-side default.
    const defaultAgg = columnMeta[columnName]?.aggregation
    if (defaultAgg && target.role.startsWith('measure')) next.aggregation = defaultAgg
    // The semantic veto on the drag path: a dragged latitude, id or year starts
    // on the aggregation that means something for it, never on Sum.
    else if (target.role.startsWith('measure')) {
      const kind = nonAdditiveKind(columnName)
      if (kind) next.aggregation = SAFE_AGGREGATION[kind].value
    }
    return { config: next, roleLabel: (target.label ?? target.role).replace(/\s*\(.*\)\s*$/, '') }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [columnMeta])

  // `selectedW` is a SNAPSHOT taken at selection time; after a save the
  // page reloads but the snapshot keeps the old config. Planning from the
  // snapshot sent `{dimension}` alone and wiped the measure set a click
  // earlier (and vice versa), so a chart could never be built by clicking.
  // Always plan from the live widget on the page.
  const liveSelected = useCallback(() =>
    (selectedW && activePage?.widgets.find(x => x.id === selectedW.id)) ?? selectedW, [selectedW, activePage])
  const assignFieldToWidget = useCallback((columnName: string, isNumericField: boolean) => {
    const w = liveSelected()
    if (!w) return
    const plan = planFieldOnWidget(w, columnName, isNumericField)
    if (!plan) {
      toast(`"${w.title || w.widget_type}" has no empty field left for ${columnName}`)
      return
    }
    updateWidgetConfig(plan.config, w.title)
  }, [liveSelected, updateWidgetConfig, planFieldOnWidget])

  // A measure always goes to the measure role — it is already an aggregate, so it has
  // no meaning as a dimension, and the widget's own aggregation setting is bypassed.
  const assignMeasureToWidget = useCallback((measureName: string) => {
    const w = liveSelected()
    if (!w) return
    const cfg = w.config as Record<string, unknown>
    updateWidgetConfig({ ...cfg, measure: measureName }, w.title)
  }, [liveSelected, updateWidgetConfig])

  // â”€â”€ Pages â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const addPage = async () => {
    const pos = report?.pages.length ?? 0
    setSaving(true)
    try {
      const spec = { name: `Page ${pos + 1}`, position: pos, layout_mode: 'packed' as const, layout_template: DEFAULT_RECIPE }
      const page = await reportsApi.addPage(reportId, spec)
      pushUndo({ label: `Add page "${spec.name}"`,
        undo: () => reportsApi.deletePage(reportId, pid(page.id)).then(() => {}),
        redo: async () => { const again = await reportsApi.addPage(reportId, spec); pageIds.current.set(pid(page.id), again.id) } })
      await loadReport()
      setActivePage(page)
      toast.success('Page added')
    } finally {
      setSaving(false)
    }
  }

  const confirm = useConfirm()
  const shortcutsRef = useModalDialog<HTMLDivElement>(() => setShortcutsOpen(false))
  const deletePage = async (page: ReportPage) => {
    if (!await confirm({ title: `Delete page "${page.name}"?`, body: 'Its widgets are deleted with it.' })) return
    setSaving(true)
    try {
      await reportsApi.deletePage(reportId, page.id)
      // Undo rebuilds the page and its widgets; both come back under new ids,
      // which the alias maps carry for every older entry.
      const snapshot = { ...page, widgets: [...(page.widgets ?? [])] }
      pushUndo({ label: `Delete page "${page.name}"`,
        undo: async () => {
          const { id: _id, widgets: ws, report_id: _r, created_at: _c, ...props } = snapshot as ReportPage & Record<string, unknown>
          const again = await reportsApi.addPage(reportId, props as Partial<ReportPage> & { name: string; position: number })
          pageIds.current.set(pid(page.id), again.id)
          for (const w of ws ?? []) {
            const made = await reportsApi.addWidget(reportId, again.id, {
              widget_type: w.widget_type, title: w.title, config: w.config, layout: w.layout })
            widgetIds.current.set(widgetIds.current.resolve(w.id), made.id)
          }
        },
        redo: () => reportsApi.deletePage(reportId, pid(page.id)).then(() => {}) })
      await loadReport()
      toast.success('Page deleted')
    } finally {
      setSaving(false)
    }
  }

  const savePageName = async (page: ReportPage) => {
    setSaving(true)
    try {
      const before = page.name, after = editPname
      await reportsApi.updatePage(reportId, page.id, { name: after })
      if (before !== after) {
        pushUndo({ label: `Rename page "${before}" to "${after}"`,
          undo: () => reportsApi.updatePage(reportId, pid(page.id), { name: before }).then(() => {}),
          redo: () => reportsApi.updatePage(reportId, pid(page.id), { name: after }).then(() => {}) })
      }
      setEditPid(null)
      await loadReport()
    } finally {
      setSaving(false)
    }
  }

  const updatePageProps = useCallback(async (data: Partial<ReportPage>) => {
    if (!activePage) return
    setSaving(true)
    try {
      await reportsApi.updatePage(reportId, activePage.id, data)
      const pageId = activePage.id
      const before = Object.fromEntries(Object.keys(data).map(k => [k, (activePage as unknown as Record<string, unknown>)[k] ?? null])) as Partial<ReportPage>
      pushUndo({ label: `Change page ${Object.keys(data).join(', ').replace(/_/g, ' ')}`,
        coalesceKey: `page:${pageId}:${Object.keys(data).sort().join(',')}`,
        undo: () => reportsApi.updatePage(reportId, pid(pageId), before).then(() => {}),
        redo: () => reportsApi.updatePage(reportId, pid(pageId), data).then(() => {}) })
      await loadReport()
    } finally {
      setSaving(false)
    }
  }, [activePage, reportId, loadReport, pushUndo])

  const autoGenHierarchy = async () => {
    if (!report?.dataset_id) return toast.error('Attach a dataset first')
    try {
      const nodes = await hierarchyApi.autoGenerate(report.dataset_id)
      setHierarchy(nodes)
      toast.success('Hierarchy generated from column types')
    } catch (err: any) {
      const msg = err?.response?.data?.detail ?? 'Failed to generate hierarchy'
      toast.error(msg)
    }
  }

  // ── Drag ─────────────────────────────────────────────────────────────────
  const handleDragStart = useCallback((widget: Widget) => (e: React.MouseEvent) => {
    e.preventDefault()
    const canvasEl = canvasRef.current
    if (!canvasEl || !activePage) return
    const target = e.currentTarget as HTMLElement
    if ('pointerId' in e && typeof target.setPointerCapture === 'function') {
      try { target.setPointerCapture((e as React.PointerEvent).pointerId) } catch { /* jsdom */ }
    }
    const rect = canvasEl.getBoundingClientRect()
    const scale = zoom / 100
    const cellW = (containerW - GAP * (COLS - 1)) / COLS
    const widgetLeft = widget.layout.x * (cellW + GAP)
    const widgetTop  = widget.layout.y * (ROW_H + GAP)
    const items = toLayoutItems(activePage.widgets.map(w => ({
      ...w,
      layout: localLayoutsRef.current[w.id] ?? w.layout,
    })))
    setDragging({
      widgetId: widget.id,
      startX: e.clientX, startY: e.clientY,
      layout: widget.layout,
      offsetX: (e.clientX - rect.left) / scale - widgetLeft,
      offsetY: (e.clientY - rect.top)  / scale - widgetTop,
      packed: isPackedMode(activePage.layout_mode),
      items,
    })
  }, [containerW, zoom, activePage])

  const handleResizeStart = useCallback((widget: Widget) => (e: React.MouseEvent) => {
    e.preventDefault()
    if (!activePage) return
    setResizing({
      widgetId: widget.id, startX: e.clientX, startY: e.clientY, layout: widget.layout,
      packed: isPackedMode(activePage.layout_mode),
      items: toLayoutItems(activePage.widgets.map(w => ({
        ...w,
        layout: localLayoutsRef.current[w.id] ?? w.layout,
      }))),
    })
  }, [activePage])

  // Per-widget callback bundle for the memo'd WidgetRenderer: identities are
  // stable for as long as the page's widget list is, while behavior always
  // routes through the refs to the latest implementations above.
  const dragStartRef = useRef(handleDragStart);  dragStartRef.current = handleDragStart
  const resizeStartRef = useRef(handleResizeStart); resizeStartRef.current = handleResizeStart
  const perWidgetHandlers = useMemo(() => {
    const m = new Map<number, { onSelect: (e: React.MouseEvent) => void; onDelete: () => void
      onDuplicate: () => void
      onDragStart: (e: React.MouseEvent) => void; onResizeStart: (e: React.MouseEvent) => void }>()
    for (const w of (activePage?.widgets ?? [])) {
      m.set(w.id, {
        onSelect: (e) => widgetActionsRef.current.selectWidget(w, e),
        onDelete: () => { void widgetActionsRef.current.deleteWidget(w) },
        onDuplicate: () => { void widgetActionsRef.current.duplicateWidget(w) },
        onDragStart: (e) => dragStartRef.current(w)(e),
        onResizeStart: (e) => resizeStartRef.current(w)(e),
      })
    }
    return m
  }, [activePage?.widgets])

  useEffect(() => {
    if (!dragging && !resizing) return
    const scale = zoom / 100
    const cellW = (containerW - GAP * (COLS - 1)) / COLS

    const onMove = (e: MouseEvent | PointerEvent) => {
      const canvasEl = canvasRef.current
      if (dragging && canvasEl) {
        const rect = canvasEl.getBoundingClientRect()
        const relX = (e.clientX - rect.left) / scale - dragging.offsetX
        const relY = (e.clientY - rect.top)  / scale - dragging.offsetY
        const newX = Math.max(0, Math.min(COLS - dragging.layout.w, Math.round(relX / (cellW + GAP))))
        const newY = Math.max(0, Math.round(relY / (ROW_H + GAP)))
        const next = dragging.packed
          ? dropPacked(dragging.items, dragging.widgetId, { x: newX, y: newY })
          : dropFree(dragging.items, dragging.widgetId, { x: newX, y: newY })
        commitLocalLayouts(next)
      }
      if (resizing) {
        const dx = (e.clientX - resizing.startX) / scale
        const dy = (e.clientY - resizing.startY) / scale
        const rawW = resizing.layout.w + Math.round(dx / (cellW + GAP))
        const rawH = resizing.layout.h + Math.round(dy / (ROW_H + GAP))
        const next = resizing.packed
          ? resizePacked(resizing.items, resizing.widgetId, rawW, rawH)
          : resizeFree(resizing.items, resizing.widgetId, rawW, rawH)
        commitLocalLayouts(next)
      }
    }

    let finished = false
    const onUp = async () => {
      if (finished) return
      finished = true
      const page = activePage
      const layouts = localLayoutsRef.current
      setDragging(null)
      setResizing(null)
      if (page && Object.keys(layouts).length) {
        const moved = dragging ?? resizing
        const mw = moved ? page.widgets.find(x => x.id === moved.widgetId) : undefined
        const name = mw ? `"${mw.title || mw.widget_type}"` : 'widget'
        await persistWidgetLayouts(page, layouts, undefined, `${dragging ? 'Move' : 'Resize'} ${name}`)
      }
    }

    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
    window.addEventListener('pointercancel', onUp)
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup',   onUp)
    return () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      window.removeEventListener('pointercancel', onUp)
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    // localLayouts deliberately absent (read via ref): listeners attach once
    // per drag session, not once per mousemove.
  }, [dragging, resizing, containerW, zoom, activePage, persistWidgetLayouts, commitLocalLayouts])

  // Localised widget objects, memoized per (widgets, layouts, translations):
  // a fresh object per render would defeat React.memo on WidgetRenderer.
  // Declared ABOVE the !report early return -- hooks must run every render.
  const packedPreview = useMemo(() => {
    if (!activePage?.widgets.length || dragging || resizing) return {} as Record<number, Widget['layout']>
    if (!needsAutoPack(activePage.layout_mode)) return {}
    return applyLayoutRecipe(toLayoutItems(activePage.widgets), DEFAULT_RECIPE)
  }, [activePage, dragging, resizing])
  const localisedWidgets = useMemo(() => {
    const m = new Map<number, Widget>()
    for (const w of (activePage?.widgets ?? [])) {
      m.set(w.id, localise({ ...w, layout: localLayouts[w.id] ?? packedPreview[w.id] ?? w.layout }))
    }
    return m
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activePage?.widgets, localLayouts, packedPreview, localise])
  const activePromptFilter = useMemo(() =>
    activePage && activePage.prompt_column && promptValues[activePage.id]
      ? { column: activePage.prompt_column, value: promptValues[activePage.id] }
      : null,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [activePage?.id, activePage?.prompt_column, promptValues])

  if (badId) return <NotFound />
  if (loadError) {
    return (
      <div style={{ padding: 32 }}>
        <LoadError what="this report" error={loadError}
          onRetry={() => { loadReport().catch(e => setLoadError(e ?? new Error('failed'))) }} />
      </div>
    )
  }
  if (!report) return <p style={{ color: 'var(--muted)', padding: 32 }}>Loading…</p>

  const columns: DatasetColumn[] = [
    ...(dataset?.columns ?? []),
    ...calcCols.map(c => ({ id: -1, name: c.name, dtype: 'calculated', missing_pct: 0, stats: {} })),
  ]
  // Everything this report is bound to (primary + additional datasets), for the
  // "Ask" pane's file-based target when the primary dataset isn't DirectQuery-backed.
  const chatDatasetIds = [report.dataset_id, ...(report.additional_dataset_ids ?? [])]
    .filter((id): id is number => id != null)
  // column_meta overrides detected types. `role` decides which Fields group a column
  // lands in — a numeric ZIP code belongs under Dimensions — and `hidden` removes it
  // from the picker without deleting anything.
  const isNumericField = (c: DatasetColumn) => {
    const role = columnMeta[c.name]?.role
    if (role) return role === 'measure'
    return c.dtype === 'numeric' || c.dtype === 'calculated'
  }
  const visibleColumns = columns.filter(c => !columnMeta[c.name]?.hidden)
  const hints = fieldHints(analysis)
  const pageWidgets = activePage?.widgets ?? []

  return (
    // Negative margin cancels Layout's <main> padding so the editor stays edge-to-edge, and
    // height is 100% (not 100vh) now that this renders inside Layout's flex row rather than
    // as its own full-page route -- 100vh would overflow past the ribbon/rail above it.
    <div className="dl-bleed" style={{ display:'flex', overflow:'hidden', background:'var(--bg)' }}>

      {/* Integrated left sidebar. Titled "Fields", not "Data": the view strip already has
          a Data button, and two controls whose accessible names both end in "Data" are
          ambiguous to a screen reader and to any by-name query. */}
      {/* Authoring surface, hidden outright from a view-only viewer: the
          dataset attach/detach, hierarchy and calculated-column controls
          inside are dataset-scoped, so unlike the rest of the builder they
          would not be refused by the report's own capability check. A viewer
          gets the dashboard and its filters -- nothing that changes it. */}
      {/* View mode is for reading the report: the studio's field list beside
          it only took width from the charts. */}
      {canEdit && editMode && !kiosk && (
      <CollapsibleSide
        id="builder-left"
        side="left"
        width={LEFT_SIDEBAR_W}
        title="Fields"
        style={{ background:'var(--surface)', borderInlineEnd:'1px solid var(--border)' }}
      >

        {/* Analytics section */}
        <div style={{ margin:'12px 0 0', flexShrink:0 }} />
        {editMode && activeView === 'report' ? (
          // A segmented control, like Report / Data / Model: one of three is
          // always on, and the track says so.
          <div style={{ padding:'4px 10px 8px', flexShrink:0 }}>
            <div role="tablist" aria-label={tr('builder.panel')} className="dl-seg" style={{ display:'flex' }}>
              {([['charts', tr('builder.tab.charts')], ['fields', tr('builder.tab.fields')], ['more', tr('builder.tab.more')]] as const).map(([k, l]) => (
                <button key={k} type="button" role="tab" aria-selected={leftTab === k} onClick={() => setLeftTab(k)}
                  className={`dl-seg__btn${leftTab === k ? ' dl-seg__btn--on' : ''}`}
                  style={{ flex: 1, justifyContent: 'center' }}>
                  {l}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div style={{ padding:'9px 16px 5px', fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.08em', flexShrink:0 }}>
            Analytics
          </div>
        )}

        {/* Panel content — this panel always shows the fields/hierarchy content
            that used to live behind the "Data View" tab. */}
        <div style={{ flex:1, overflowY:'auto', overflowX:'auto', padding:10 }}>
          <>
              {/* Widget catalog — add-widget buttons, edit mode only */}
              {editMode && activeView === 'report' && leftTab === 'charts' && (
                // The chart-type gallery lives in its own component; the
                // catalog stays the single source of what can be inserted.
                <ChartGallery query={paletteQuery} onQuery={setPaletteQuery} onAdd={addWidget} />
              )}

              {/* Object templates — save the selected widget's whole configuration by
                  name, then drop it onto any report. The object-level analogue of a
                  DataView; apply is a plain insert carrying the saved config. */}
              {editMode && activeView === 'report' && leftTab === 'more' && (
                <div style={{ marginBottom:12, paddingBottom:12, borderBottom:'1px solid var(--border)' }}>
                  <div style={{ fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:6 }}>Templates</div>
                  <div style={{ display:'flex', gap:4, marginBottom:6 }}>
                    <input value={tplName} onChange={e => setTplName(e.target.value)}
                      placeholder={selectedW ? 'Template name' : 'Select a widget first'}
                      aria-label="Template name" disabled={!selectedW} title={!selectedW ? 'Select a widget first' : undefined}
                      style={{ flex:1, minWidth:0, fontSize: 11 }} />
                    <button onClick={saveAsTemplate} disabled={!selectedW || !tplName.trim()}
                      title="Save the selected widget as a reusable template"
                      style={{ padding:'4px 7px', background:'var(--surface2)', border:'1px solid var(--border)',
                        borderRadius:6, cursor:'pointer', fontSize: 11, color:'var(--text)', whiteSpace:'nowrap' }}>
                      Save
                    </button>
                  </div>
                  {templates.length === 0 && (
                    <div style={{ fontSize: 11, color:'var(--muted)' }}>No saved templates yet</div>
                  )}
                  <div style={{ display:'flex', flexWrap:'wrap', gap:4 }}>
                    {templates.map(t => (
                      <span key={t.id} style={{ display:'inline-flex', alignItems:'center', gap:3,
                        background:'var(--surface2)', border:'1px solid var(--border)', borderRadius:6, fontSize: 11 }}>
                        <button onClick={() => insertFromTemplate(t)} title={`Insert ${t.widget_type} from template`}
                          style={{ padding:'4px 6px', background:'none', border:'none', cursor:'pointer',
                            color:'var(--text)', fontSize: 11, fontFamily:'var(--sans)' }}>
                          {t.name}
                        </button>
                        <button onClick={() => deleteTemplate(t)} aria-label={`Delete template ${t.name}`}
                          style={{ padding:'0 5px 0 0', background:'none', border:'none', cursor:'pointer', color:'var(--muted)' }}>✕</button>
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Report filters — one filter definition applied to every widget on the
                  report. Defined once here, it propagates everywhere; a widget whose
                  dataset lacks the column is simply unaffected. */}
              {editMode && activeView === 'report' && leftTab === 'more' && (
                <div style={{ marginBottom:12, paddingBottom:12, borderBottom:'1px solid var(--border)' }}>
                  <div style={{ fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:6 }}>Report filters</div>
                  {dateColumnOf() && (
                    <div role="group" aria-label={`Quick date filters on ${dateColumnOf()}`} data-testid="date-presets"
                      style={{ display:'flex', flexWrap:'wrap', gap:4, marginBottom:6 }}>
                      {['l7d', 'l30d', 'mtd', 'ytd', 'pm'].map(id => {
                        const p = PRESETS.find(x => x.id === id)!
                        return (
                          <button key={id} type="button" className="btn btn-ghost btn-sm" style={{ fontSize: 11, padding:'1px 6px' }}
                            title={`Show only ${p.label.toLowerCase()} of ${dateColumnOf()}, counted back from the latest date in the data`}
                            onClick={() => void applyDatePreset(id)}>{p.label}</button>
                        )
                      })}
                    </div>
                  )}
                  <div style={{ display:'flex', flexWrap:'wrap', gap:4, marginBottom:6 }}>
                    <select aria-label="Report filter column" value={cfCol} onChange={e => setCfCol(e.target.value)}
                      style={{ fontSize: 11, flex:1, minWidth:80 }}>
                      <option value="">— column —</option>
                      {visibleColumns.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
                    </select>
                    <select aria-label="Report filter operator" value={cfOp} onChange={e => setCfOp(e.target.value)} style={{ fontSize: 11 }}>
                      {['eq','neq','gt','gte','lt','lte','in','like'].map(o => <option key={o} value={o}>{o}</option>)}
                      <option value="relative">relative date</option>
                    </select>
                  </div>
                  <div style={{ display:'flex', gap:4, marginBottom:6, flexWrap: cfOp === 'relative' ? 'wrap' : undefined }}>
                    {cfOp === 'relative'
                      ? <RelativeDateEditor label="Report filter" value={cfSpec} onChange={setCfSpec} compact />
                      : <input aria-label="Report filter value" value={cfVal} onChange={e => setCfVal(e.target.value)}
                      placeholder={cfOp === 'in' ? 'a, b, c' : 'value'} style={{ fontSize: 11, flex:1, minWidth:0 }} />}
                    <button className="btn" style={{ fontSize: 11, whiteSpace:'nowrap' }} onClick={addReportFilter}>+ Add report filter</button>
                  </div>
                  {(report.common_filters ?? []).length === 0 && (
                    <div style={{ fontSize: 11, color:'var(--muted)' }}>No report filters</div>
                  )}
                  <div style={{ display:'flex', flexWrap:'wrap', gap:4 }}>
                    {(report.common_filters ?? []).map(f => (
                      <span key={f.id} title="Applies to every widget" style={{ display:'inline-flex', alignItems:'center', gap:3,
                        background:'var(--surface2)', border:'1px solid var(--border)', borderRadius:6, fontSize: 11, padding:'2px 4px 2px 7px' }}>
                        {f.op === 'relative' ? `${f.column}: ${describeSpec(parseSpec(f.value))}`
                          : <>{f.column} {f.op} {Array.isArray(f.value) ? (f.value as unknown[]).join(', ') : String(f.value)}</>}
                        <button onClick={() => removeReportFilter(f.id)} aria-label={`Remove report filter ${f.column}`}
                          style={{ background:'none', border:'none', cursor:'pointer', color:'var(--muted)' }}>✕</button>
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Fields — always-visible field picker; clicking a field assigns it to the
                  selected widget's next open role matching the field's numeric-ness. */}
              {editMode && activeView === 'report' && leftTab === 'fields' && (
                <div style={{ marginBottom:12, paddingBottom:12, borderBottom:'1px solid var(--border)' }}>
                  {!selectedW && (
                    <div style={{ fontSize: 11, color:'var(--muted)', marginBottom:6 }}>{tr('fields.hint')}</div>
                  )}
                  <input aria-label="Filter fields" value={fieldFilter}
                    onChange={e => setFieldFilter(e.target.value)}
                    placeholder="Filter…"
                    style={{ width:'100%', fontSize:11, padding:'4px 7px', marginBottom:6,
                      background:'var(--surface2)', border:'1px solid var(--border)',
                      borderRadius:6, color:'var(--text)', boxSizing:'border-box' }} />
                  {/* Dataset measures — post-aggregation expressions. Listed first and
                      separately from numeric columns because they are a different thing:
                      they compute at the widget's grain rather than being aggregated. */}
                  {measures.length > 0 && (
                    <div style={{ marginBottom: 6 }}>
                      <div style={{ fontSize: 10.5, fontWeight: 700, color: 'var(--accent)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 4 }}>{tr('fields.Measures')}</div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                        {measures.filter(m => !fieldFilter.trim()
                          || m.name.toLowerCase().includes(fieldFilter.trim().toLowerCase())).map(m => (
                          <button key={m.name} onClick={() => assignMeasureToWidget(m.name)}
                            disabled={!selectedW}
                            title={m.expression}
                            style={{ display: 'flex', alignItems: 'center', gap: 3, padding: '4px 7px',
                              background: 'var(--surface2)', border: '1px solid var(--accent)', borderRadius: 6,
                              cursor: selectedW ? 'pointer' : 'not-allowed', opacity: selectedW ? 1 : .5,
                              fontSize: 11, color: 'var(--text)', fontFamily: 'var(--sans)', whiteSpace: 'nowrap' }}>
                            <span style={{ fontSize: 11, color: 'var(--accent)' }}>ƒx</span>{m.name}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                  {gatheredFields.length > 0 && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6,
                      padding: '4px 6px', borderRadius: 6, fontSize: 11,
                      background: 'color-mix(in srgb, var(--accent) 12%, transparent)',
                      border: '1px solid var(--accent)' }}>
                      <span>{gatheredFields.length} field{gatheredFields.length === 1 ? '' : 's'} selected — drag onto the canvas to chart them together</span>
                      <button onClick={() => setGatheredFields([])}
                        style={{ marginInlineStart: 'auto', background: 'none', border: 'none',
                          color: 'var(--muted)', cursor: 'pointer', fontSize: 11 }}>Clear</button>
                    </div>
                  )}
                  {(['Columns', 'Dimensions'] as const).map(group => {
                    // column_meta can hide a column and override which group it lands
                    // in — a ZIP code is stored numeric but is really a category.
                    const needle = fieldFilter.trim().toLowerCase()
                    const cols = visibleColumns
                      .filter(c => isNumericField(c) === (group === 'Columns'))
                      // Matched on what the reader SEES: a renamed column is
                      // searched by its label, not by the name in the file.
                      .filter(c => !needle
                        || (columnMeta[c.name]?.label || c.name).toLowerCase().includes(needle))
                    if (cols.length === 0) return null
                    return (
                      <div key={group} style={{ marginBottom: 6 }}>
                        <div style={{ fontSize: 10.5, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 4 }}>{tr(`fields.${group}` as MessageKey)}</div>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                          {cols.map(c => (
                            <span key={c.name} style={{ display: 'inline-flex', alignItems: 'center', gap: 2 }}>
                            <button onClick={e => {
                                // Ctrl/cmd-click gathers instead of assigning:
                                // charting several fields together is a
                                // different intent from "add this one here".
                                if (e.ctrlKey || e.metaKey) {
                                  e.preventDefault()
                                  setGatheredFields(g => g.includes(c.name)
                                    ? g.filter(n => n !== c.name) : [...g, c.name])
                                  return
                                }
                                // With a widget selected the field joins it; with
                                // none, it lands on the page as the right chart --
                                // exactly what dropping it would do. (It used to
                                // do nothing at all: a silent refusal.)
                                if (selectedW) assignFieldToWidget(c.name, isNumericField(c))
                                else void addWidgetFromField(c.name)
                              }}
                              draggable
                              aria-pressed={gatheredFields.includes(c.name) || undefined}
                              onDragStart={e => {
                                // Dragging a GATHERED field drags the whole set;
                                // dragging an ungathered one is still a
                                // single-field drag, so the old gesture is
                                // untouched.
                                if (gatheredFields.includes(c.name) && gatheredFields.length > 1) {
                                  e.dataTransfer.setData('application/x-fields', JSON.stringify(gatheredFields))
                                }
                                e.dataTransfer.setData('application/x-field', c.name)
                                e.dataTransfer.effectAllowed = 'copy'
                              }}
                              title={[selectedW ? `Add ${c.name} to ${selectedW.title}` : `Add ${c.name} to the page as a chart (or drag it where you want it)`,
                                      hintTitle(hints[c.name])].filter(Boolean).join(' — ')}
                              style={{ display: 'flex', alignItems: 'center', gap: 3, padding: '4px 7px',
                                background: gatheredFields.includes(c.name)
                                  ? 'color-mix(in srgb, var(--accent) 22%, var(--surface2))' : 'var(--surface2)',
                                border: `1px solid ${gatheredFields.includes(c.name) ? 'var(--accent)' : 'var(--border)'}`,
                                borderRadius: 6,
                                cursor: 'pointer',
                                fontSize: 11, color: 'var(--text)', fontFamily: 'var(--sans)', whiteSpace: 'nowrap' }}>
                              <span style={{ fontSize: 11 }}>{c.dtype === 'calculated' ? 'ƒx' : isNumericField(c) ? '#' : 'Aa'}</span>
                              {columnMeta[c.name]?.label || c.name}
                              {/* "Country - 47": how many distinct values this
                                  category holds, which is what decides whether
                                  it is a bar chart or a mistake. */}
                              {hints[c.name]?.distinct != null && (
                                <span style={{ color: 'var(--muted)' }}>
                                  {' - '}{countLabel(hints[c.name].distinct as number)}
                                </span>
                              )}
                              {hints[c.name]?.related && (
                                <span title={hintTitle(hints[c.name])} style={{ color: 'var(--accent)', fontSize: 11 }}>≈</span>
                              )}
                            </button>
                            {/* Classification, the way SAS's data pane offers it:
                                a category can also be geography, and then every
                                map built from it inherits its boundary set. Not
                                offered on a measure -- there is no map of a
                                number. */}
                            {!isNumericField(c) && (
                              <span style={{ position: 'relative' }}>
                                <button
                                  aria-label={`Classify ${c.name}`}
                                  title={columnMeta[c.name]?.role === 'geography'
                                    ? `${c.name} is geography` : `Classify ${c.name}`}
                                  onClick={() => {
                                    setGeoField(f => f === c.name ? null : c.name)
                                    if (boundarySets.length === 0) {
                                      boundarySetsApi.list().then(sets => {
                                        setBoundarySets(sets)
                                        Promise.resolve().then(() => boundarySetsApi.packs?.())
                                          .then(p => setBoundaryPacks((Array.isArray(p) ? p : [])
                                            .filter(pk => !sets.some(s => s.name === pk.name))))
                                          .catch(() => {})
                                      }).catch(() => {})
                                    }
                                  }}
                                  style={{ background: 'none', border: 'none', cursor: 'pointer',
                                    color: columnMeta[c.name]?.role === 'geography'
                                      ? 'var(--accent)' : 'var(--muted)',
                                    fontSize: 11, padding: '0 2px' }}>
                                  ⌖
                                </button>
                                {geoField === c.name && (
                                  <div role="menu" style={{ position: 'absolute', zIndex: 30, top: '100%',
                                    insetInlineStart: 0, minWidth: 170, padding: 4,
                                    background: 'var(--surface)', border: '1px solid var(--border)',
                                    borderRadius: 6, boxShadow: '0 6px 20px rgba(0,0,0,.25)' }}>
                                    <div style={{ fontSize: 10.5, fontWeight: 700, color: 'var(--muted)',
                                      textTransform: 'uppercase', padding: '4px 6px' }}>Classification</div>
                                    <button role="menuitem"
                                      onClick={() => void classifyGeography(c.name, null)}
                                      style={{ display: 'block', width: '100%', textAlign: 'start',
                                        background: 'none', border: 'none', cursor: 'pointer',
                                        padding: '4px 6px', fontSize: 11, color: 'var(--text)' }}>
                                      Not geography
                                    </button>
                                    {boundarySets.map(bs => (
                                      <button key={bs.id} role="menuitem"
                                        onClick={() => { setGeoField(null); setGeoCheck({ column: c.name, setId: bs.id, setName: bs.name }) }}
                                        style={{ display: 'block', width: '100%', textAlign: 'start',
                                          background: 'none', border: 'none', cursor: 'pointer',
                                          padding: '4px 6px', fontSize: 11, color: 'var(--text)' }}>
                                        Geography — {bs.name}
                                      </button>
                                    ))}
                                    {boundaryPacks.map(pk => (
                                      <button key={pk.id} role="menuitem"
                                        onClick={() => void installPackAndCheck(c.name, pk)}
                                        style={{ display: 'block', width: '100%', textAlign: 'start',
                                          background: 'none', border: 'none', cursor: 'pointer',
                                          padding: '4px 6px', fontSize: 11, color: 'var(--text)' }}>
                                        Geography — {pk.name} <span style={{ color: 'var(--muted)' }}>
                                          (starter pack{pk.requires_acceptance ? ', terms' : ''})</span>
                                      </button>
                                    ))}
                                    {packTerms && packTerms.column === c.name && (
                                      <div style={{ width: 260 }}>
                                        <PackTermsConfirm pack={packTerms.pack}
                                          onAccept={() => void installPackAndCheck(c.name, packTerms.pack, true)}
                                          onCancel={() => setPackTerms(null)} />
                                      </div>
                                    )}
                                    {boundarySets.length === 0 && boundaryPacks.length === 0 && (
                                      <div style={{ fontSize: 10.5, color: 'var(--muted)', padding: '4px 6px' }}>
                                        No boundary sets uploaded yet.
                                      </div>
                                    )}
                                  </div>
                                )}
                              </span>
                            )}
                            {/* One-click calculations, offered per field the way SAS
                                offers them from the data item. Outside the field
                                button for the same reason as the note below. A field
                                the measure language cannot NAME (a space, a hyphen,
                                a leading digit) gets no button rather than a menu of
                                expressions that would fail to evaluate. */}
                            {quickCalcsFor({ name: c.name, dtype: c.dtype, numeric: isNumericField(c) }).length > 0 && (
                              <span data-quickcalc-menu style={{ position: 'relative' }}>
                                <button
                                  aria-label={`Calculations from ${c.name}`}
                                  title={`Calculations from ${c.name}`}
                                  onClick={() => setQuickCalcField(f => f === c.name ? null : c.name)}
                                  style={{ background: 'none', border: 'none', cursor: 'pointer',
                                    color: 'var(--muted)', fontSize: 11, padding: '0 2px' }}>
                                  Σ
                                </button>
                                {quickCalcField === c.name && (
                                  <div role="menu" style={{ position: 'absolute', zIndex: 30, top: '100%',
                                    insetInlineStart: 0, minWidth: 150, padding: 4,
                                    background: 'var(--surface)', border: '1px solid var(--border)',
                                    borderRadius: 6, boxShadow: '0 6px 20px rgba(0,0,0,.25)' }}>
                                    {quickCalcsFor({ name: c.name, dtype: c.dtype, numeric: isNumericField(c) }).map(qc => (
                                      <button key={qc.key} role="menuitem"
                                        onClick={() => void runQuickCalc(c.name, qc.key)}
                                        style={{ display: 'block', width: '100%', textAlign: 'start',
                                          background: 'none', border: 'none', cursor: 'pointer',
                                          padding: '4px 6px', fontSize: 11, color: 'var(--text)' }}>
                                        {qc.label}
                                      </button>
                                    ))}
                                    <div style={{ fontSize: 10.5, color: 'var(--muted)', padding: '2px 6px' }}>
                                      Saved as a measure, computed at each widget's grain
                                    </div>
                                  </div>
                                )}
                              </span>
                            )}
                            {/* Outside the field button on purpose: that button is
                                disabled until a widget is selected, and a disabled
                                parent swallows every child click -- the first drive
                                of this dialog found exactly that. */}
                            {c.dtype === 'numeric' && (
                              <span role="button" tabIndex={0}
                                aria-label={`Reclassify ${c.name} as ${isNumericField(c) ? 'category' : 'measure'}`}
                                title={isNumericField(c)
                                  ? `Treat ${c.name} as a category (group by it instead of summing it)`
                                  : `Treat ${c.name} as a measure again`}
                                onClick={e => { e.stopPropagation(); void flipFieldRole(c) }}
                                onKeyDown={e => { if (e.key === 'Enter') { e.stopPropagation(); void flipFieldRole(c) } }}
                                style={{ color: 'var(--muted)', fontSize: 11, cursor: 'pointer' }}>⇄</span>
                            )}
                            {isNumericField(c) && (
                              <span role="button" tabIndex={0} aria-label={`Explain ${c.name}`}
                                title={`What moves ${c.name}? Ranked factor importance`}
                                onClick={e => { e.stopPropagation(); setExplainColumn(c.name) }}
                                onKeyDown={e => { if (e.key === 'Enter') { e.stopPropagation(); setExplainColumn(c.name) } }}
                                style={{ color: 'var(--accent)', fontSize: 11, cursor: 'pointer' }}>?</span>
                            )}
                            {hints[c.name]?.outliers && (
                              <span role="button" tabIndex={0} aria-label={`Show outlier details for ${c.name}`}
                                title={hintTitle(hints[c.name]) + ' — click for details'}
                                onClick={e => { e.stopPropagation(); setOutlierColumn(c.name) }}
                                onKeyDown={e => { if (e.key === 'Enter') { e.stopPropagation(); setOutlierColumn(c.name) } }}
                                style={{ color: '#e6a03c', fontSize: 11, cursor: 'pointer' }}>⚠</span>
                            )}
                            </span>
                          ))}
                        </div>
                      </div>
                    )
                  })}
                  {fieldFilter.trim() && visibleColumns.every(c =>
                    !(columnMeta[c.name]?.label || c.name).toLowerCase()
                      .includes(fieldFilter.trim().toLowerCase())) && (
                    <div style={{ fontSize: 11, color: 'var(--muted)', padding: '6px 2px' }}>
                      No fields match “{fieldFilter.trim()}”
                    </div>
                  )}
                  {hierarchy.filter(n => n.parent_id == null).length > 0 && (
                    <div style={{ marginBottom: 6 }}>
                      <div style={{ fontSize: 10.5, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 4 }}>Hierarchies</div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                        {hierarchy.filter(n => n.parent_id == null).map(root => (
                          <button key={root.id}
                            onClick={() => assignHierarchyToWidget(root.id)}
                            draggable
                            onDragStart={e => { e.dataTransfer.setData('application/x-hierarchy', String(root.id)); e.dataTransfer.effectAllowed = 'copy' }}
                            title={selectedW ? `Bind the ${root.name} hierarchy to ${selectedW.title}` : 'Drag onto the canvas to chart the first level, or select a widget first'}
                            style={{ display: 'flex', alignItems: 'center', gap: 3, padding: '4px 7px',
                              background: 'var(--surface2)', border: '1px solid var(--accent)', borderRadius: 6,
                              cursor: 'pointer', fontSize: 11, color: 'var(--text)', fontFamily: 'var(--sans)', whiteSpace: 'nowrap' }}>
                            <span aria-hidden style={{ fontSize: 11 }}>⛓</span>
                            {root.name}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {(!editMode || activeView !== 'report' || leftTab === 'fields') && (<>
              {/* Datasets section */}
              <div style={{ marginBottom:12, paddingBottom:12, borderBottom:'1px solid var(--border)' }}>
                <div style={{ fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:6 }}>{tr('builder.datasets')}</div>

                {report.dataset_id && datasets[report.dataset_id] && (
                  <div style={{ display:'flex', alignItems:'center', gap:5, padding:'4px 7px', background:'var(--surface2)', borderRadius:5, marginBottom:3, fontSize:11 }}>
                    <span style={{ color:'var(--accent)' }}>★</span>
                    <span style={{ flex:1, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{datasets[report.dataset_id].name}</span>
                    {datasets[report.dataset_id].aggregate_of_dataset_id && (
                      <span title={PRE_AGGREGATED_HINT} style={{ fontSize: 10.5, color:'var(--accent)', background:'color-mix(in srgb, var(--accent) 15%, transparent)', borderRadius:3, padding:'1px 4px', flexShrink:0 }}>Σ pre-aggregated</span>
                    )}
                    {datasets[report.dataset_id].default_filter_expr
                      ? <span title={datasets[report.dataset_id].default_filter_expr!} style={{ fontSize: 10.5, color:'var(--accent)', background:'color-mix(in srgb, var(--accent) 15%, transparent)', borderRadius:3, padding:'1px 4px', flexShrink:0 }}>⊙ filtered</span>
                      : <span style={{ fontSize: 10.5, color:'var(--muted)', flexShrink:0 }}>primary</span>
                    }
                  </div>
                )}

                {(report.additional_dataset_ids ?? []).map(dsId => (
                  <div key={dsId} style={{ display:'flex', alignItems:'center', gap:5, padding:'4px 7px', background:'var(--surface2)', borderRadius:5, marginBottom:3, fontSize:11 }}>
                    <span style={{ color:'var(--muted)' }}>◉</span>
                    <span style={{ flex:1, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{datasets[dsId]?.name ?? `Unavailable dataset (#${dsId})`}</span>
                    {datasets[dsId]?.aggregate_of_dataset_id && (
                      <span title={PRE_AGGREGATED_HINT} style={{ fontSize: 10.5, color:'var(--accent)', background:'color-mix(in srgb, var(--accent) 15%, transparent)', borderRadius:3, padding:'1px 4px', flexShrink:0 }}>Σ pre-aggregated</span>
                    )}
                    {datasets[dsId]?.default_filter_expr && (
                      <span title={datasets[dsId].default_filter_expr!} style={{ fontSize: 10.5, color:'var(--accent)', background:'color-mix(in srgb, var(--accent) 15%, transparent)', borderRadius:3, padding:'1px 4px', flexShrink:0 }}>⊙ filtered</span>
                    )}
                    <button onClick={() => detachDataset(dsId)} title="Remove"
                      style={{ background:'none', border:'none', color:'var(--muted)', cursor:'pointer', fontSize:14, lineHeight:1, padding:'0 2px', flexShrink:0 }}>×</button>
                  </div>
                ))}

                <div style={{ position:'relative', marginTop:5 }}>
                  <button id="add-dataset-button" className="btn btn-ghost btn-sm" style={{ width:'100%', fontSize: 11 }}
                    onClick={() => { setShowDsMenu(m => !m); if (!showDsMenu) datasetsApi.list().then(setAllDatasets) }}>
                    + Add Dataset
                  </button>
                  {showDsMenu && (
                    <DatasetPickerDialog
                      datasets={allDatasets}
                      excludeIds={[...(report.dataset_id ? [report.dataset_id] : []), ...(report.additional_dataset_ids ?? [])]}
                      title={report.dataset_id ? 'Add another dataset to this dashboard' : 'Choose the data for this dashboard'}
                      onPick={d => { void attachDataset(d.id); setShowDsMenu(false) }}
                      onClose={() => setShowDsMenu(false)} />
                  )}
                </div>
              </div>

              <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:8 }}>
                <span style={{ fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em' }}>{tr('builder.hierarchy')}</span>
                {dataset && (
                  <button className="btn btn-ghost btn-sm" onClick={autoGenHierarchy} style={{ fontSize: 11, padding:'2px 6px' }}>
                    Auto
                  </button>
                )}
              </div>
              {!dataset
                ? <p style={{ fontSize:12, color:'var(--muted)', textAlign:'center', marginTop:20 }}>Attach a dataset to this report to browse columns.</p>
                : <HierarchyTree nodes={hierarchy} datasetId={dataset.id} onRefresh={refreshHierarchy} />
              }

              {dataset && (
                <div style={{ marginTop:16, borderTop:'1px solid var(--border)', paddingTop:12 }}>
                  <CalcColumnsPanel
                    datasetId={dataset.id}
                    columns={dataset.columns}
                    onChanged={setCalcCols}
                  />
                </div>
              )}
              </>)}

          </>
        </div>
      </CollapsibleSide>
      )}

      {/* Right section: top bar + page tabs + canvas */}
      <div style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden' }}>

        {/* Top bar */}
        {/* flexWrap is load-bearing, not cosmetic. This row sits inside a parent
            with overflow:hidden, so without it the rightmost controls are simply
            CUT OFF at narrow widths -- measured in a browser at 1366x850 (one of
            the commonest laptop resolutions): "Edit mode" sat 150px past the
            window edge with no scrollable ancestor and no document overflow, so
            there was no way for a person to reach the button that puts a report
            into edit mode. Wrapping costs a second row; not wrapping costs the
            control. */}
        <div data-testid="builder-header"
          style={{ display:'flex', alignItems:'center', flexWrap:'wrap', gap:10, padding:'10px 20px', borderBottom:'1px solid var(--border)', flexShrink:0, background:'var(--surface)' }}>
          <Link to="/reports" style={{ color:'var(--muted)', display:'flex', alignItems:'center', gap:4, fontSize:12, textDecoration:'none' }}>
            <ArrowLeft size={13} /> Reports
          </Link>
          <span style={{ color:'var(--border)' }}>|</span>
          {editMode && renaming ? (
            <input autoFocus aria-label="Dashboard name" defaultValue={report.name} maxLength={120}
              style={{ fontWeight:700, fontSize:16, padding:'1px 6px', minWidth:220 }}
              onBlur={e => void commitRename(e.currentTarget.value)}
              onKeyDown={e => {
                if (e.key === 'Enter') e.currentTarget.blur()
                if (e.key === 'Escape') { e.stopPropagation(); setRenaming(false) }
              }} />
          ) : editMode ? (
            <button type="button" title={report.name} aria-label="Rename this dashboard" onClick={() => setRenaming(true)}
              className="dl-report-name"
              style={{ fontWeight:700, fontSize:16, background:'none', border:'1px dashed transparent', borderRadius:4,
                padding:'1px 4px', cursor:'text', color:'var(--text)', font:'inherit' }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--border)' }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = 'transparent' }}>
              {report.name}
            </button>
          ) : (
            <span style={{ fontWeight:700, fontSize:16 }}>{report.name}</span>
          )}
          {dataset && canEdit && (
            <nav aria-label="Breadcrumb" style={{ display:'flex', alignItems:'center', gap:4 }}>
              <span aria-hidden style={{ color:'var(--muted)', fontSize:12 }}>▸</span>
              {[dataset, ...(report.additional_dataset_ids ?? []).map(id => datasets[id]).filter((d): d is Dataset => !!d)]
                .map((d, i) => (
                  <span key={d.id} style={{ display:'flex', alignItems:'center', gap:4 }}>
                    {i > 0 && <span aria-hidden style={{ color:'var(--muted)', fontSize:11 }}>,</span>}
                    <Link to={`/datasets/${d.id}`} className="badge badge-categorical" style={{ textDecoration:'none' }}>{d.name}</Link>
                  </span>
              ))}
              {dataset.data_source_id != null && (
                <>
                  <span aria-hidden style={{ color:'var(--muted)', fontSize:12 }}>▸</span>
                  <Link to={`/connections/${dataset.data_source_id}/review`} style={{ fontSize:11, color:'var(--accent)' }}>
                    {sourceName ?? 'Source'}
                  </Link>
                </>
              )}
            </nav>
          )}
          {(sens?.effective ?? report.classification) && (() => {
            const shown = (sens?.effective ?? report.classification) as string
            const inherited = shown !== report.classification
            return (
              <span data-testid="sensitivity-badge"
                title={inherited
                  ? `Sensitivity in force: ${shown}, inherited from its data — ${sens?.effective_reasons?.[0] ?? ''}`
                  : 'Sensitivity label'}
                style={{
                fontSize: 11, fontWeight: 800, letterSpacing: '.06em', textTransform: 'uppercase',
                color: '#fff', padding: '2px 7px', borderRadius: 4,
                background: CLASSIFICATION_COLORS[shown] ?? '#666' }}>
                {shown}{inherited ? ' ⤴' : ''}
              </span>
            )
          })()}
          {editMode && (
            <span style={{ display: 'inline-flex', gap: 2 }}>
              {/* aria-disabled, not disabled: a disabled button shows no tooltip,
                  and "why can't I" must always have an answer. */}
              <button className="btn btn-ghost btn-sm" aria-label="Undo"
                aria-disabled={!undoStack.undoLabel || undoStack.busy}
                title={undoStack.undoLabel ? `Undo: ${undoStack.undoLabel} (Ctrl+Z)` : 'Nothing to undo yet'}
                style={{ opacity: undoStack.undoLabel ? 1 : 0.4 }}
                onClick={() => { if (undoStack.undoLabel) void runUndo() }}>
                <Undo2 size={14} />
              </button>
              <button className="btn btn-ghost btn-sm" aria-label="Redo"
                aria-disabled={!undoStack.redoLabel || undoStack.busy}
                title={undoStack.redoLabel ? `Redo: ${undoStack.redoLabel} (Ctrl+Y)` : 'Nothing to redo'}
                style={{ opacity: undoStack.redoLabel ? 1 : 0.4 }}
                onClick={() => { if (undoStack.redoLabel) void runRedo() }}>
                <Redo2 size={14} />
              </button>
            </span>
          )}
          {editMode && (
            <select aria-label="Sensitivity label" value={report.classification ?? ''}
              title="Classify this report" style={{ fontSize: 11, padding: '2px 4px' }}
              onChange={async e => {
                try {
                  const prev = report.classification ?? ''
                  const next = e.target.value
                  const updated = await reportsApi.setClassification(reportId, next)
                  setReport(updated)
                  pushUndo({ label: next ? `Classify report ${next}` : 'Clear report classification',
                    undo: () => reportsApi.setClassification(reportId, prev).then(() => {}),
                    redo: () => reportsApi.setClassification(reportId, next).then(() => {}) })
                  toast.success(e.target.value ? `Classified ${e.target.value}` : 'Classification cleared')
                } catch (err) {
                  toast.error((err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Could not classify')
                }
              }}>
              {(() => {
                // The label cannot go below its data (Phase 7.3): lower options
                // stay visible, disabled, and say why.
                const floorIdx = sens?.floor ? CLASSIFICATION_LABELS.indexOf(sens.floor) : -1
                const why = sens?.floor_reasons?.[0] ?? ''
                return (<>
                  <option value="" disabled={floorIdx >= 0}>— Unclassified —</option>
                  {CLASSIFICATION_LABELS.map((l, i) => (
                    <option key={l} value={l} disabled={i < floorIdx}
                      title={i < floorIdx ? `Below its data: ${why}` : undefined}>
                      {l}{i < floorIdx ? ' (below its data)' : ''}
                    </option>
                  ))}
                </>)
              })()}
            </select>
          )}
          {/* Share and Export are menus, not seven buttons in a row: the old
              header wrapped onto a second line on a laptop. Each item keeps its
              own gate -- a viewer sees no Share menu at all (every item in it is
              edit/admin-only), and keeps Export and Subscribe. */}
          <ToolbarMenu label={<IconLabel icon={Globe}>{tr('builder.share')}</IconLabel>} title="Links, guest access and permissions"
            items={[
              ...(canEdit ? [{ key: 'link', label: <IconLabel icon={Copy}>Copy link to this page</IconLabel>,
                onSelect: () => {
                  // The link encodes the active page, so a colleague lands where the
                  // sender was looking rather than on page 1.
                  const url = new URL(window.location.href)
                  if (activePage) url.searchParams.set('page', String(activePage.id))
                  navigator.clipboard.writeText(url.toString())
                    .then(() => toast.success('Link copied'))
                    .catch(() => toast.error('Could not copy the link'))
                } }] : []),
              ...(canEdit ? [{ key: 'guest', label: <IconLabel icon={Globe}>Guest links…</IconLabel>,
                title: access.share_link && !access.share_link.allowed ? access.share_link.reason : 'Read-only access without a login',
                disabled: access.share_link ? !access.share_link.allowed : false,
                onSelect: () => setShareOpen(true) }] : []),
              ...(Object.keys(access).length ? [{ key: 'why', label: <IconLabel icon={KeyRound}>Your access, and why…</IconLabel>,
                title: 'What you can do here, and the rule behind each', onSelect: () => setAccessOpen2(true) }] : []),
              ...(isAdmin ? [{ key: 'access', label: <IconLabel icon={ShieldCheck}>Access by role…</IconLabel>,
                title: 'Set per-role capability levels for this report', onSelect: () => setAccessOpen(true) }] : []),
            ]} />
          {canEdit && (
          <button className="btn btn-ghost btn-sm" title="Kiosk playback: pages advance every 8s; any key exits"
            aria-pressed={kiosk}
            onClick={() => { setEditMode(false); setKiosk(k => !k) }}>
            {kiosk ? <IconLabel icon={Pause}>{tr('builder.stop')}</IconLabel> : <IconLabel icon={Play}>{tr('builder.present')}</IconLabel>}
          </button>
          )}
          <ToolbarMenu label={<IconLabel icon={FileDown}>{tr('builder.export')}</IconLabel>} title="Print or download this dashboard"
            items={[
              { key: 'print', label: <IconLabel icon={Printer}>Print…</IconLabel>, title: 'Print or save as PDF from the browser',
                onSelect: () => navigate(`/reports/${reportId}/print`) },
              { key: 'pdf', label: <IconLabel icon={FileText}>Download PDF…</IconLabel>,
                title: access.download && !access.download.allowed ? access.download.reason
                  : "Server-rendered PDF: cover, contents, every page's visuals — choose paper, orientation and pages",
                disabled: access.download ? !access.download.allowed : false,
                onSelect: () => setPdfDialog(true) },
              { key: 'package', label: <IconLabel icon={Package}>Offline package</IconLabel>,
                disabled: access.download ? !access.download.allowed : false,
                title: access.download && !access.download.allowed ? access.download.reason
                  : 'One HTML file that opens without the platform: every visible page, frozen as you see it now',
                onSelect: () => { reportsApi.downloadPackage(reportId, report.name)
                  .then(() => toast.success('Offline package downloaded'))
                  .catch(() => toast.error('Could not build the package')) } },
            ]} />
          {/* Beside PDF on purpose: a subscription is the recurring version of
              that same export, and it needs only view -- so it must sit OUTSIDE
              the editMode-gated toolbar, which a viewer never sees. */}
          <SubscribeButton reportId={reportId} />
          <div style={{ marginInlineStart:'auto', display:'flex', alignItems:'center', gap:8 }}>
            {canEdit ? (
              // A two-way segmented switch, not a button labelled with the
              // CURRENT state: "Edit mode" on a button read as the action it
              // would take, so people clicked it to start editing and left.
              <div role="group" aria-label={tr('builder.mode')} className="dl-seg">
                <button type="button" aria-label="View mode" aria-pressed={!editMode}
                  className={`dl-seg__btn${!editMode ? ' dl-seg__btn--on' : ''}`}
                  onClick={() => setEditMode(false)}>
                  <Eye size={12} aria-hidden /> {tr('builder.view')}
                </button>
                <button type="button" aria-label="Edit mode" aria-pressed={editMode}
                  className={`dl-seg__btn${editMode ? ' dl-seg__btn--on' : ''}`}
                  onClick={() => setEditMode(true)}>
                  <Settings size={12} aria-hidden /> {tr('builder.edit')}
                </button>
              </div>
            ) : (
              <button type="button" className="btn btn-ghost btn-sm" data-testid="view-only-why"
                title={access.edit?.reason ? `View only — ${access.edit.reason}` : 'You have view-only access to this report'}
                onClick={() => { if (Object.keys(access).length) setAccessOpen2(true) }}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 12, color: 'var(--muted)', padding: '0 8px' }}>
                <Eye size={12}/> View only · why?
              </button>
            )}
          </div>
        </div>

        {!kiosk && openReports.length > 1 && (
          // Navigation, not tabs: each entry opens another report (a new URL),
          // and a tablist may hold only tabs -- the close buttons made it invalid.
          <div role="navigation" aria-label={`Opened reports (${openReports.length})`} data-testid="open-reports"
            style={{ display: 'flex', gap: 2, padding: '4px 12px 0', overflowX: 'auto', borderBottom: '1px solid var(--border)' }}>
            {openReports.map(r => {
              const current = r.id === reportId
              return (
                // The name is a BUTTON with the close button beside it, not inside
                // it: a control nested in another is unreachable to a screen
                // reader (axe: nested-interactive), and the old span could not be
                // reached from the keyboard at all.
                <span key={r.id} role="presentation"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '3px 8px', fontSize: 11.5,
                    borderRadius: '6px 6px 0 0', whiteSpace: 'nowrap',
                    background: current ? 'var(--surface)' : 'transparent', border: '1px solid var(--border)',
                    borderBottom: current ? '1px solid var(--surface)' : '1px solid var(--border)', marginBottom: -1,
                    color: current ? 'var(--text)' : 'var(--muted)' }}>
                  <button type="button" aria-current={current ? 'page' : undefined}
                    onClick={() => { if (!current) navigate(`/reports/${r.id}`) }}
                    style={{ background: 'none', border: 'none', padding: 0, font: 'inherit', color: 'inherit',
                      cursor: current ? 'default' : 'pointer' }}>
                    {r.name}
                  </button>
                  <button type="button" aria-label={`Close ${r.name}`} title="Close this tab (the report is not deleted)"
                    onClick={e => {
                      e.stopPropagation()
                      const next = closeOpen(r.id)
                      setOpenReports(next)
                      if (current) navigate(next.length ? `/reports/${next[next.length - 1].id}` : '/reports')
                    }}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--muted)', padding: 0, fontSize: 12, lineHeight: 1 }}>×</button>
                </span>
              )
            })}
          </div>
        )}

        {/* Report / Data / Model view strip — authors only. A viewer has one
            surface (the dashboard); these tabs are the studio. */}
        {canEdit && !kiosk && (
        <div className="dl-panebar">
          {/* Scoped to just these three: other tests use `within(view-strip)` to look
              for a button named /Report/i, and "Report rules" below would otherwise
              also match that regex if it shared this container.
              Drawn as a segmented control: these three are WHERE you are (one
              is always on), which is a different kind of thing from the panel
              toggles to the right, and they used to look identical to them. */}
          <div data-testid="view-strip" className="dl-seg">
            {(['report', 'data', 'model'] as const).filter(v => v === 'report' || canData).map(v => (
              <button key={v} onClick={() => setActiveView(v)} aria-pressed={activeView === v}
                className={`dl-seg__btn${activeView === v ? ' dl-seg__btn--on' : ''}`}>
                {v === 'report' ? <IconLabel icon={ViewReport}>{tr('builder.viewReport')}</IconLabel>
                  : v === 'data' ? <IconLabel icon={ViewData}>{tr('builder.viewData')}</IconLabel>
                  : <IconLabel icon={ViewModel}>{tr('builder.viewModel')}</IconLabel>}
              </button>
            ))}
          </div>
          {activeView === 'report' && editMode && (() => {
            // Toolbar architecture: the most-used panels stay as buttons; the
            // rest live behind ⋯ More. Thirteen co-equal toggles overflowed the
            // strip and made every panel equally hard to find. The primaries
            // are further split into three families with a hairline between
            // them -- build, AI, collaborate -- so eight buttons read as three
            // small groups rather than one long run of words.
            const pl = (m: RightPanelMode) => tr(`builder.pane.${m}` as MessageKey)
            const GROUPS: [RightPanelMode, string, LucideIcon][][] = [
              [['outline', pl('outline'), PanelLeft], ['parameters', pl('parameters'), AtSign]],
              // Ask and Insights sit side by side as primaries: same AI
              // family, same discoverability. Insights was in the overflow,
              // which left the engine's builder surface effectively hidden
              // while its lesser sibling had a top-level button.
              [['suggestions', pl('suggestions'), Lightbulb], ['ask', pl('ask'), Bot], ['insights', pl('insights'), Sparkles]],
              [['review', pl('review'), CheckCheck], ['comments', pl('comments'), MessageSquare], ['schedule', pl('schedule'), Clock]],
            ]
            const OVERFLOW: [RightPanelMode, string, LucideIcon][] = [
              ['mobile', pl('mobile'), Smartphone], ['selection', pl('selection'), MousePointerClick],
              ['sync', pl('sync'), Link2], ['bookmarks', pl('bookmarks'), BookmarkIcon],
              ['taborder', pl('taborder'), ArrowRightLeft], ['performance', pl('performance'), PerfGauge],
              ['reportrules', pl('reportrules'), Palette], ['translations', pl('translations'), Languages],
              ['history', pl('history'), History],
            ]
            const overflowActive = OVERFLOW.find(([m]) => m === rightPanelMode)
            const toggleMode = (m: RightPanelMode) => setRightPanelMode(cur => cur === m ? 'default' : m)
            const paneClass = (active: boolean) => `dl-panebtn${active ? ' dl-panebtn--on' : ''}`
            return (
              <div className="dl-panebar__tools">
                {GROUPS.map((group, gi) => (
                  <div key={gi} className="dl-panebar__group">
                    {group.map(([m, label, Icon]) => (
                      <button key={m} onClick={() => toggleMode(m)} aria-pressed={rightPanelMode === m}
                        className={paneClass(rightPanelMode === m)} title={label}>
                        {/* The word collapses to the icon when the strip is narrow
                            (a container query in index.css), except on the open
                            panel; it stays in the accessible name either way. */}
                        <IconLabel icon={Icon}><span className="dl-panebtn__text">{label}</span></IconLabel>
                      </button>
                    ))}
                  </div>
                ))}
                <div style={{ position: 'relative' }}>
                  <button onClick={() => setToolbarMoreOpen(o => !o)}
                    aria-label={tr('builder.morePanels')} aria-expanded={toolbarMoreOpen}
                    className={paneClass(!!overflowActive || toolbarMoreOpen)}>
                    {overflowActive
                      ? <IconLabel icon={overflowActive[2]}>{overflowActive[1]}</IconLabel>
                      : <IconLabel icon={MoreHorizontal}>{tr('builder.more')}</IconLabel>}
                  </button>
                  {toolbarMoreOpen && (
                    <div role="menu" aria-label={tr('builder.morePanels')} className="dl-menu"
                      style={{ position: 'absolute', insetInlineEnd: 0, top: '110%', zIndex: 700, minWidth: 180 }}>
                      {OVERFLOW.map(([m, label, Icon]) => (
                        <button key={m} role="menuitem"
                          onClick={() => { toggleMode(m); setToolbarMoreOpen(false) }}
                          className={`dl-menu__item${rightPanelMode === m ? ' dl-menu__item--on' : ''}`}>
                          <IconLabel icon={Icon}>{label}</IconLabel>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )
          })()}
        </div>
        )}

        {activeView === 'data' && dataset && (
          <div style={{ display:'flex', flex:1, overflow:'hidden' }}>
            <div style={{ flex:1, overflow:'auto' }}>
              <DataView datasetId={dataset.id} mode={dataset.mode} />
            </div>
            <div style={{ width:RIGHT_PANEL_W, flexShrink:0, borderInlineStart:'1px solid var(--border)', padding:12, overflowY:'auto' }}>
              <ColumnFormatsPanel
                datasetId={dataset.id}
                columns={dataset.columns}
                columnFormats={columnFormats}
                onChanged={setColumnFormats}
              />
            </div>
          </div>
        )}
        {activeView === 'model' && report && <ModelView report={report} datasets={datasets} />}

        {activeView === 'report' && (
        <>
        {/* Concurrent-edit warning. Non-blocking on purpose: the other session's
            change is already saved, so the useful action is to pull it in. */}
        {staleRevision !== null && canEdit && (
          <div style={{ display:'flex', alignItems:'center', gap:10, padding:'7px 14px',
            background:'rgba(230,160,60,.14)', borderBottom:'1px solid rgba(230,160,60,.4)',
            fontSize:12, color:'var(--text)', flexShrink:0 }}>
            <span style={{ fontSize:13 }}>⚠</span>
            <span style={{ flex:1 }}>
              This report was changed in another session. Reload to see those edits —
              anything you change first may overwrite them.
            </span>
            <button className="btn btn-sm" onClick={() => loadReport()}
              style={{ fontSize:11, background:'var(--accent)', color:'var(--mc-accent-fg)', border:'none' }}>
              Reload
            </button>
            <button onClick={() => setStaleRevision(null)} title="Dismiss"
              style={{ background:'none', border:'none', color:'var(--muted)', cursor:'pointer', fontSize:15, lineHeight:1 }}>
              ×
            </button>
          </div>
        )}

        {/* Report parameters: the viewer's controls. Rendered whenever the report
            defines any -- this is the report-level prompt surface. */}
        {paramDefs.some(d => d.param_type !== 'expression') && (
          <div data-testid="parameter-bar" style={{ display:'flex', gap:12, alignItems:'center', padding:'6px 16px',
            borderBottom:'1px solid var(--border)', background:'var(--surface)', flexWrap:'wrap' }}>
            {/* Expression parameters are computed server-side and immune to filters —
                a viewer never sets them, so they never appear in this prompt bar. */}
            {paramDefs.filter(d => d.param_type !== 'expression').map(d => {
              const id = `param-${d.name}`
              const value = paramValues[d.name] ?? d.default_value ?? ''
              const set = (v: string) => setParamValues(prev => ({ ...prev, [d.name]: v }))
              return (
                <label key={d.name} htmlFor={id} style={{ display:'flex', alignItems:'center', gap:5, fontSize:11, color:'var(--muted)' }}>
                  {d.label || d.name}
                  {d.param_type === 'number' && (d.options?.length ?? 0) === 3
                    && d.options!.every(o => !isNaN(Number(o))) ? (
                    /* Power BI's what-if parameter: a range slider whose bounds and
                       step ARE the parameter's options triple. Every widget bound to
                       @name re-queries as the thumb moves and settles. */
                    <span style={{ display:'flex', alignItems:'center', gap:6 }}>
                      <input id={id} type="range"
                        min={Number(d.options![0])} max={Number(d.options![1])} step={Number(d.options![2])}
                        value={Number(value) || Number(d.options![0])}
                        onChange={e => set(e.target.value)}
                        style={{ width: 130 }} />
                      <span style={{ fontFamily:'var(--mono)', fontSize:11, minWidth:44, color:'var(--text)' }}
                        data-testid={`whatif-${d.name}`}>{String(value) || d.options![0]}</span>
                    </span>
                  ) : (d.options?.length ?? 0) > 0 ? (
                    <select id={id} value={String(value)} onChange={e => set(e.target.value)} style={{ fontSize:11 }}>
                      {(d.options ?? []).map(o => <option key={o} value={o}>{o}</option>)}
                    </select>
                  ) : (
                    <input id={id} type={d.param_type === 'number' ? 'number' : d.param_type === 'date' ? 'date' : 'text'}
                      value={String(value)} onChange={e => set(e.target.value)}
                      style={{ fontSize:11, width: d.param_type === 'number' ? 90 : 130 }} />
                  )}
                </label>
              )
            })}
          </div>
        )}

        {/* Page tabs */}
        <div style={{ display:'flex', alignItems:'center', gap:3, padding:'0 16px', borderBottom:'1px solid var(--border)', flexShrink:0, background:'var(--surface)' }}>
          {report.pages
            .filter(page => (editMode || (page.page_type !== 'hidden' && page.page_type !== 'popup')) && page.page_type !== 'tooltip' && page.page_type !== 'drillthrough')
            .map(page => {
              const typeIcon = page.page_type === 'hidden' ? ' [H]' : page.page_type === 'popup' ? ' [P]' : ''
              const isActive = page.id === activePage?.id
              return (
                <div key={page.id} style={{ display:'flex', alignItems:'center', borderBottom: isActive ? '2px solid var(--accent)' : '2px solid transparent', marginBottom:-1,
                  opacity: page.page_type === 'hidden' ? 0.55 : 1 }}>
                  {editPid === page.id ? (
                    <input value={editPname} onChange={e => setEditPname(e.target.value)}
                      onBlur={() => savePageName(page)} onKeyDown={e => e.key==='Enter' && savePageName(page)}
                      style={{ fontSize:12, padding:'5px 8px', width:90 }} autoFocus />
                  ) : (
                    <button
                      style={{ padding:'7px 13px', border:'none', background:'none', cursor:'pointer', fontSize:12,
                        color: isActive ? 'var(--accent)' : 'var(--muted)',
                        fontWeight: isActive ? 600 : 400, fontFamily:'var(--sans)' }}
                      onClick={() => { setActivePage(page); setSelectedW(null) }}
                      onDoubleClick={() => {
                        if (!editMode) return
                        setEditPid(page.id); setEditPname(page.name)
                      }}
                    >{page.name}{typeIcon}</button>
                  )}
                  {editMode && report.pages.length > 1 && (
                    <button style={{ background:'none', border:'none', color:'var(--muted)', cursor:'pointer', padding:'0 4px', fontSize:13 }}
                      aria-label={`Delete page "${page.name}"`} title={`Delete page "${page.name}" (undoable)`}
                      onClick={() => deletePage(page)}>x</button>
                  )}
                </div>
              )
            })}
          {editMode && (
            <div style={{ position: 'relative', display: 'inline-flex', gap: 2 }}>
              <button className="btn btn-ghost btn-sm" onClick={addPage} style={{ marginBottom:3, fontSize:11 }}>
                <Plus size={11}/> {tr('builder.page')}
              </button>
              <button className="btn btn-ghost btn-sm" aria-label="Add page from a template"
                aria-expanded={pageMenuOpen}
                onClick={() => setPageMenuOpen(o => !o)} style={{ marginBottom:3, fontSize:11, padding:'4px 6px' }}>
                ▾
              </button>
              {pageMenuOpen && (
                <PageTemplateMenu
                  reportId={reportId}
                  activePageId={activePage?.id ?? null}
                  onClose={() => setPageMenuOpen(false)}
                  onAdded={() => { setPageMenuOpen(false); loadReport() }}
                />
              )}
            </div>
          )}
          {editMode && (
            <div style={{ position: 'relative', marginInlineStart: 8, marginBottom: 3 }}>
              <button className="btn btn-ghost btn-sm" aria-label="Page layout"
                aria-expanded={layoutMenuOpen}
                onClick={() => setLayoutMenuOpen(o => !o)}
                style={{ fontSize: 11 }}>
                <IconLabel icon={LayoutTemplate}>{tr('builder.layout')}</IconLabel>
              </button>
              {layoutMenuOpen && (
                <div role="menu" aria-label="Page layout"
                  style={{ position: 'absolute', insetInlineStart: 0, top: '110%', zIndex: 700, minWidth: 220,
                    background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8,
                    boxShadow: '0 8px 24px rgba(0,0,0,.25)', padding: 4, display: 'flex', flexDirection: 'column', gap: 2 }}>
                  {RECIPES.map(r => {
                    const on = activePage?.layout_mode !== 'free' && (activePage?.layout_template === r.id || (!activePage?.layout_template && r.id === DEFAULT_RECIPE))
                    return (
                      <button key={r.id} role="menuitem"
                        onClick={() => { void applyPageRecipe(r.id) }}
                        style={{ textAlign: 'start', width: '100%', padding: '6px 8px', border: 'none', borderRadius: 6,
                          background: on ? 'var(--accent)' : 'transparent', color: on ? 'var(--mc-accent-fg)' : 'var(--text)',
                          cursor: 'pointer', fontSize: 12 }}>
                        <div style={{ fontWeight: 600 }}>{r.label}{r.id === DEFAULT_RECIPE ? ' (default)' : ''}</div>
                        <div style={{ fontSize: 11, opacity: 0.8 }}>{r.hint}</div>
                      </button>
                    )
                  })}
                  <button role="menuitem"
                    onClick={() => { void applyPageRecipe('free') }}
                    style={{ textAlign: 'start', width: '100%', padding: '6px 8px', border: 'none', borderRadius: 6, marginTop: 4,
                      background: activePage?.layout_mode === 'free' ? 'var(--accent)' : 'transparent',
                      color: activePage?.layout_mode === 'free' ? 'var(--mc-accent-fg)' : 'var(--text)',
                      cursor: 'pointer', fontSize: 12 }}>
                    <div style={{ fontWeight: 600 }}>Free layout</div>
                    <div style={{ fontSize: 11, opacity: 0.8 }}>Place tiles by hand; still no overlap or tiny charts</div>
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        {editMode && multiSelectedIds.size >= 2 && (
          <div style={{ display: 'flex', gap: 4, alignItems: 'center', padding: '6px 16px', borderBottom: '1px solid var(--border)', background: 'var(--surface)' }}>
            <span style={{ fontSize: 11, color: 'var(--muted)', marginInlineEnd: 4 }}>Align/Distribute:</span>
            {([
              ['Align Left', () => applyAlign('left')], ['Align Center', () => applyAlign('center')], ['Align Right', () => applyAlign('right')],
              ['Align Top', () => applyAlign('top')], ['Align Middle', () => applyAlign('middle')], ['Align Bottom', () => applyAlign('bottom')],
              ['Distribute Horizontally', () => applyDistribute('horizontal')], ['Distribute Vertically', () => applyDistribute('vertical')],
            ] as const).map(([label, fn]) => (
              <button key={label} onClick={fn} style={{ fontSize: 11, padding: '4px 8px', border: '1px solid var(--border)', borderRadius: 6, background: 'var(--surface2)', color: 'var(--text)', cursor: 'pointer' }}>{label}</button>
            ))}
          </div>
        )}

        {/* Canvas + right panel */}
        <CrossFilterProvider
          pageMode={(activePage?.mobile_layout as { interaction_mode?: 'manual' | 'linked' | 'oneway' | 'twoway' } | null)?.interaction_mode ?? 'manual'}
          widgets={activePage?.widgets ?? []}
          onPersistInteraction={persistInteraction}>
        <div style={{ display:'flex', flex:1, gap:10, padding:'10px 16px', overflow:'hidden', minHeight:0 }}>

          {/* Canvas */}
          <div style={{ flex:1, overflowY:'auto', overflowX:'auto' }}>
            {editMode && recoverable.length > 0 && (
              <div role="status" data-testid="recovery-banner"
                style={{ display:'flex', alignItems:'center', gap:8, flexWrap:'wrap', margin:'0 0 8px', padding:'6px 10px',
                  fontSize:12, background:'color-mix(in srgb, var(--accent) 10%, var(--surface))',
                  border:'1px solid color-mix(in srgb, var(--accent) 35%, var(--border))', borderRadius:'var(--radius)' }}>
                <span style={{ flex:1, minWidth:200 }}>
                  Changes to {recoverable.length === 1 ? 'one widget' : `${recoverable.length} widgets`} from your last session were not saved
                  {' '}({recoverable.map(e => `"${e.title || 'untitled'}"`).join(', ')}).
                </span>
                <button className="btn btn-primary btn-sm" onClick={() => void restorePending()}>{tr('builder.restore')}</button>
                <button className="btn btn-ghost btn-sm" onClick={discardPending}>{tr('builder.discard')}</button>
              </div>
            )}
            <FilterBar />
            {/* The same filters, reachable after scrolling: the strip above is
                at the top of the canvas and a tall dashboard scrolls it away. */}
            <FloatingFilterWindow />
            {activePage?.prompt_column && (
              <div style={{ display:'flex', alignItems:'center', gap:10, padding:'8px 12px', background:'var(--surface)', borderBottom:'1px solid var(--border)', flexShrink:0, marginBottom:8 }}>
                <span style={{ fontSize:12, fontWeight:600, color:'var(--muted)', whiteSpace:'nowrap' }}>
                  {activePage.prompt_label || ('Filter by ' + activePage.prompt_column)}
                </span>
                <input value={promptValues[activePage.id] ?? ''}
                  onChange={e => setPromptValues(p => ({ ...p, [activePage.id]: e.target.value }))}
                  placeholder={'Enter ' + activePage.prompt_column + '...'}
                  style={{ flex:1, fontSize:12, padding:'4px 8px' }} />
                {promptValues[activePage.id] && (
                  <button onClick={() => setPromptValues(p => { const n = {...p}; delete n[activePage.id]; return n })}
                    style={{ background:'none', border:'none', cursor:'pointer', color:'var(--muted)', fontSize:16 }}>x</button>
                )}
              </div>
            )}
            {/* On a phone the page is always a single column: the free/packed
                desktop layout clipped widgets off the side. A saved mobile
                layout decides the order; without one, top-to-bottom,
                left-to-right, the order a reader scans the desktop page. */}
            {!editMode && isNarrowViewport && activePage ? (
              <div data-testid="mobile-stack" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {(() => {
                  if (!datasetsReady) return null
                  const byPosition = [...pageWidgets].sort((a, b) =>
                    ((a.layout as any)?.y ?? 0) - ((b.layout as any)?.y ?? 0) || ((a.layout as any)?.x ?? 0) - ((b.layout as any)?.x ?? 0))
                  const knownIds = byPosition.map(w => w.id)
                  const savedOrder = (activePage.mobile_layout?.order ?? []).filter(id => knownIds.includes(id))
                  const missing = knownIds.filter(id => !savedOrder.includes(id))
                  const hidden = activePage.mobile_layout?.hidden ?? []
                  const widgetsById = new Map(pageWidgets.map(w => [w.id, w]))
                  return [...savedOrder, ...missing]
                    .filter(id => !hidden.includes(id))
                    .map(id => widgetsById.get(id))
                    .filter((w): w is Widget => !!w && !(w.config as any).hidden)
                    .map(widget => (
                      <div key={widget.id} style={{ width: '100%', height: 360 }}>
                        <WidgetRenderer
                          widget={localisedWidgets.get(widget.id) ?? widget}
                          datasetId={report.dataset_id}
                          reportId={reportId}
                          parameters={effectiveParams}
                          onSetParameter={stableOnSetParameter}
                          calculatedColumns={calcCols}
                          columnFormats={columnFormats} geography={geography}
                          datasets={datasets} relationships={relationships}
                          editMode={false}
                          promptFilter={activePromptFilter}
                          onFetchComplete={handleFetchComplete}
                          pages={report.pages}
                          reportDisplayRules={report.display_rules ?? EMPTY_RULES}
                          reportFilters={report.common_filters ?? []}
                          onDrillthrough={handleDrillthrough}
                          hierarchy={hierarchy}
                          bookmarks={bookmarks}
                          onNavigateToPage={handleButtonNavigate}
                          onApplyBookmark={handleButtonApplyBookmark}
                          eagerFetch={kiosk}
                        />
                      </div>
                    ))
                })()}
              </div>
            ) : (
            <div style={{ height: canvasH(pageWidgets.map(w => ({ ...w, layout: localLayouts[w.id] ?? packedPreview[w.id] ?? w.layout }))) * (zoom / 100), minWidth: MIN_CANVAS_W }}>
              <div ref={attachCanvas}
                data-canvas
                onDragOver={e => { if (e.dataTransfer.types.includes('application/x-fields') || e.dataTransfer.types.includes('application/x-field') || e.dataTransfer.types.includes('application/x-hierarchy')) {
                  e.preventDefault(); e.dataTransfer.dropEffect = 'copy'
                  const single = e.dataTransfer.types.includes('application/x-field') && !e.dataTransfer.types.includes('application/x-fields')
                  const wid = single ? Number((e.target as HTMLElement).closest?.('[data-widget-id]')?.getAttribute('data-widget-id')) || null : null
                  if (wid !== dropTargetId) setDropTargetId(wid)
                } }}
                onDragLeave={e => { if (!(e.currentTarget as HTMLElement).contains(e.relatedTarget as Node | null)) setDropTargetId(null) }}
                onDrop={e => {
                  // The gathered set first. A multi-field drag carries BOTH
                  // payloads, so a drop target that only knows the old one
                  // still gets a field rather than nothing.
                  const many = e.dataTransfer.getData('application/x-fields')
                  const field = e.dataTransfer.getData('application/x-field')
                  const hier = e.dataTransfer.getData('application/x-hierarchy')
                  if (many) {
                    e.preventDefault()
                    try { void addWidgetFromFields(JSON.parse(many) as string[]) }
                    catch { if (field) void addWidgetFromField(field) }
                  }
                  else if (field) {
                    e.preventDefault()
                    setDropTargetId(null)
                    // Dropped ON a widget: fill its next empty compatible role
                    // (SAS's drop-onto-object). Anywhere else, or a widget with
                    // no room left, makes a new chart -- and says which.
                    const wid = Number((e.target as HTMLElement).closest?.('[data-widget-id]')?.getAttribute('data-widget-id'))
                    const target = wid ? pageWidgets.find(w => w.id === wid) : undefined
                    const col = columns.find(c => c.name === field)
                    const plan = target && col ? planFieldOnWidget(target, field, isNumericField(col)) : null
                    if (target && plan) {
                      window.dispatchEvent(new CustomEvent(PATCH_WIDGET_EVENT, { detail: { widgetId: target.id, patch: plan.config,
                        label: `Set ${plan.roleLabel} of "${target.title || target.widget_type}" to ${field}` } }))
                      toast.success(`${field} → ${plan.roleLabel} of "${target.title || target.widget_type}"`)
                    } else {
                      if (target) toast(`"${target.title || target.widget_type}" has no empty field for ${field}, so it became a new chart`)
                      void addWidgetFromField(field)
                    }
                  }
                  else if (hier) { e.preventDefault(); void addWidgetFromHierarchy(Number(hier)) }
                }}
                style={{ position:'relative', minHeight:canvasH(pageWidgets.map(w => ({ ...w, layout: localLayouts[w.id] ?? packedPreview[w.id] ?? w.layout }))),
                // The page's own backdrop, with objects that opt into
                // transparency floating on it. `cover` rather than `contain`:
                // a page is a fixed aspect box and a letterboxed photograph
                // with two grey bands reads as a mistake.
                ...(activePage?.background_url
                  ? { backgroundImage: `url(${activePage.background_url})`,
                      backgroundSize: 'cover', backgroundPosition: 'center' }
                  : { background:'var(--surface2)' }),
                borderRadius:'var(--radius)', border:'1px solid var(--border)',
                transform: `scale(${zoom / 100})`, transformOrigin: 'top left' }}>
                {pageWidgets.length === 0 && (
                  // An empty page TEACHES (SAS: "Drag objects or data items onto
                  // the page, or start from a page template"). The drag-a-field
                  // gesture is the builder's best one -- a field dropped here
                  // becomes the right chart -- and nothing used to mention it.
                  <div data-testid="empty-page" style={{ position:'absolute', inset:0, display:'flex', alignItems:'center', justifyContent:'center', flexDirection:'column', gap:10, color:'var(--muted)', pointerEvents:'none', textAlign:'center', padding:16 }}>
                    <span style={{ fontSize:36, opacity:.2 }}>⊞</span>
                    {!editMode && <span style={{ fontSize:13 }}>{tr('builder.noWidgets')}</span>}
                    {editMode && (<>
                      <span style={{ fontSize:15, fontWeight:600, color:'var(--text)' }}>{tr('builder.designPage')}</span>
                      <span style={{ fontSize:13, maxWidth:440 }}>
                        {report.dataset_id
                          ? <>Drag a <b>field</b> from the left panel onto the page and it becomes the right chart — or pick a chart type and assign data to it.</>
                          : <>{tr('builder.startData')}</>}
                      </span>
                      <span style={{ display:'flex', gap:8, flexWrap:'wrap', justifyContent:'center', pointerEvents:'auto' }}>
                        {!report.dataset_id && (
                          <button type="button" className="btn btn-primary btn-sm"
                            onClick={openDatasetPicker}>
                            {tr('builder.addData')}
                          </button>
                        )}
                        <button type="button" className="btn btn-ghost btn-sm"
                          onClick={() => { window.scrollTo({ top: 0 }); setPageMenuOpen(true) }}>
                          {tr('builder.addFromTemplate')}
                        </button>
                      </span>
                    </>)}
                  </div>
                )}
                {datasetsReady && pageWidgets
                  .filter(w => editMode || !(w.config as any).hidden)
                  /* A widget assigned to a container renders INSIDE it, so it is
                     skipped at canvas level -- rendering both places would fetch and
                     draw it twice, and edits to one copy would look ignored. In edit
                     mode it stays visible here at half opacity so it can be selected
                     and reassigned even if the container hides or clips it. */
                  .filter(w => editMode || !(w.config as any).container_id)
                  .map(widget => {
                  const effLayout = localLayouts[widget.id] ?? packedPreview[widget.id] ?? widget.layout
                  const isBeingDragged = dragging?.widgetId === widget.id || resizing?.widgetId === widget.id
                  const isHidden = editMode && !!(widget.config as any).hidden
                  return (
                    <div key={widget.id} data-widget-id={widget.id}
                      tabIndex={!editMode ? (widget.config as any).tabIndex : undefined}
                      onMouseEnter={!editMode ? (e) => handleTooltipEnter(widget, e) : undefined}
                      onMouseLeave={!editMode ? () => handleTooltipLeave(widget.id) : undefined}
                      style={{ ...gridStyle(effLayout, containerW), padding: GAP/2,
                      transition: isBeingDragged ? 'none' : 'left .12s, top .12s, width .12s, height .12s',
                      zIndex: isBeingDragged ? Z_DRAG : 1,
                      opacity: isHidden || (editMode && (widget.config as any).container_id) ? 0.5 : 1,
                      ...(dropTargetId === widget.id ? { outline: '2px dashed var(--accent)', outlineOffset: -2, borderRadius: 'var(--radius)' } : {}) }}
                      title={dropTargetId === widget.id ? `Drop to add the field to "${widget.title || widget.widget_type}"` : undefined}>
                      <WidgetRenderer
                        widget={localisedWidgets.get(widget.id) ?? widget}
                        datasetId={report.dataset_id}
                        reportId={reportId}
                        parameters={effectiveParams}
                        onSetParameter={stableOnSetParameter}
                        calculatedColumns={calcCols}
                        columnFormats={columnFormats} geography={geography}
                        datasets={datasets} relationships={relationships}
                        selected={selectedW?.id === widget.id}
                        isMultiSelected={multiSelectedIds.has(widget.id)}
                        onSelect={editMode ? perWidgetHandlers.get(widget.id)?.onSelect : undefined}
                        onDelete={editMode ? perWidgetHandlers.get(widget.id)?.onDelete : undefined}
                        onDuplicate={editMode ? perWidgetHandlers.get(widget.id)?.onDuplicate : undefined}
                        editMode={editMode}
                        promptFilter={activePromptFilter}
                        onDragStart={editMode ? perWidgetHandlers.get(widget.id)?.onDragStart : undefined}
                        onResizeStart={editMode ? perWidgetHandlers.get(widget.id)?.onResizeStart : undefined}
                        isDragging={isBeingDragged}
                        onFetchComplete={handleFetchComplete}
                        pages={report.pages}
                        reportDisplayRules={report.display_rules ?? EMPTY_RULES}
                          reportFilters={report.common_filters ?? []}
                        onDrillthrough={handleDrillthrough}
                        hierarchy={hierarchy}
                        bookmarks={bookmarks}
                        onNavigateToPage={handleButtonNavigate}
                        onApplyBookmark={handleButtonApplyBookmark}
                        eagerFetch={kiosk}
                      />
                    </div>
                  )
                })}
              </div>
            </div>
            )}
          </div>

          {/* Right: config panel */}
          {editMode && (
            <CollapsibleSide
              id="builder-right"
              side="right"
              width={RIGHT_PANEL_W}
              title="Settings"
              openSignal={rightOpenSignal}
              style={{ background:'var(--surface)', border:'1px solid var(--border)', borderRadius:'var(--radius)' }}
              scrollResetKey={rightPanelMode !== 'default' ? rightPanelMode : selectedW ? `widget-${selectedW.id}` : activePage ? `page-${activePage.id}` : 'none'}
            >
              {rightPanelMode === 'mobile' && (
                activePage && <MobileLayoutEditor page={activePage} widgets={pageWidgets} onUpdate={updatePageProps} />
              )}
              {rightPanelMode === 'selection' && (
                <SelectionPane widgets={pageWidgets} onUpdate={(id, config) =>
                  reportsApi.updateWidget(reportId, activePage!.id, id, { config }).then(loadReport)} />
              )}
              {rightPanelMode === 'sync' && <SyncSlicersPaneConnected pages={report.pages} />}
              {rightPanelMode === 'history' && (
                <VersionHistoryPane reportId={reportId} currentRevision={loadedRevision}
                  onRestored={loadReport} />
              )}
              {rightPanelMode === 'taborder' && (
                <TabOrderPane widgets={pageWidgets} onUpdate={(id, config) =>
                  reportsApi.updateWidget(reportId, activePage!.id, id, { config }).then(loadReport)} />
              )}
              {rightPanelMode === 'performance' && (
                <div style={{ padding: '14px 14px 0' }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 8 }}>
                    Performance
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 11 }}>
                    {pageWidgets.length === 0 && <span style={{ color: 'var(--muted)' }}>No widgets on this page</span>}
                    {[...pageWidgets]
                      .sort((a, b) => (perfStats[b.id]?.durationMs ?? -1) - (perfStats[a.id]?.durationMs ?? -1))
                      .map(w => {
                        const stat = perfStats[w.id]
                        return (
                          <div key={w.id} style={{ display: 'flex', flexDirection: 'column', gap: 2, padding: '5px 7px', background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 6 }}>
                            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                              <span style={{ flex: 1, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{w.title || w.widget_type}</span>
                              {stat?.sampled && (
                                <span style={{ fontSize: 10.5, background: 'rgba(230,160,60,.18)', color: '#e6a03c', padding: '1px 5px', borderRadius: 99 }}>sampled</span>
                              )}
                            </div>
                            <div style={{ display: 'flex', gap: 10, color: 'var(--muted)' }}>
                              <span>{w.widget_type}</span>
                              <span style={{ fontFamily: 'var(--mono)' }}>{stat ? `${stat.durationMs.toFixed(0)} ms` : '—'}</span>
                              <span>{stat ? `${stat.rowCount} rows` : ''}</span>
                            </div>
                          </div>
                        )
                      })}
                  </div>
                </div>
              )}
              {rightPanelMode === 'bookmarks' && (
                <BookmarksPaneConnected reportId={reportId} report={report} activePage={activePage}
                  pageWidgets={pageWidgets} promptValues={promptValues} bookmarks={bookmarks}
                  setActivePage={setActivePage} setPromptValues={setPromptValues} setBookmarks={setBookmarks}
                  loadReport={loadReport} />
              )}
              {rightPanelMode === 'review' && report && (
                <ReviewPane report={report} perfStats={perfStats}
                  mapping={{ datasets, relationships }} canEdit={canEdit} isAdmin={isAdmin}
                  onSelectWidget={(wid, pid) => {
                    const page = report.pages.find(p => p.id === pid)
                    if (page) setActivePage(page)
                    const w = page?.widgets.find(x => x.id === wid)
                    if (w) setSelectedW(w)
                    setRightPanelMode('default')
                  }} />
              )}
              {rightPanelMode === 'outline' && report && (
                <OutlinePane report={report} activePageId={activePage?.id} selectedWidgetId={selectedW?.id}
                  onSelect={(wid, pid) => {
                    const page = report.pages.find(p => p.id === pid)
                    if (page) setActivePage(page)
                    const w = page?.widgets.find(x => x.id === wid)
                    if (w) setSelectedW(w)
                  }}
                  onRename={(wid, pid, title) =>
                    reportsApi.updateWidget(reportId, pid, wid, { title }).then(loadReport)}
                  onSetContainer={(wid, pid, containerId) => {
                    const w = report.pages.find(p => p.id === pid)?.widgets.find(x => x.id === wid)
                    if (!w) return
                    const config = { ...(w.config as Record<string, unknown>) }
                    if (containerId == null) delete config.container_id
                    else config.container_id = containerId
                    reportsApi.updateWidget(reportId, pid, wid, { config }).then(loadReport)
                  }} />
              )}
              {rightPanelMode === 'suggestions' && (
                <SuggestionsPane columns={columns} analysis={analysis} onAdd={addSuggestedWidget} reportId={reportId} datasetId={report.dataset_id} />
              )}
              {rightPanelMode === 'insights' && (
                <InsightsPane datasetId={report.dataset_id ?? null}
                  columnTypes={Object.fromEntries(columns.map(c => [c.name,
                    columnMeta[c.name]?.role === 'category' ? 'categorical'
                      : columnMeta[c.name]?.role === 'measure' ? 'numeric' : c.dtype]))}
                  onAdd={s => { void addSuggestedWidget(s); setRightPanelMode('default') }}
                  reportId={reportId}
                  onComposed={() => { void loadReport(); setRightPanelMode('default') }} />
              )}
              {rightPanelMode === 'translations' && report && (
                <TranslationsPane report={report} onSaved={() => translationsApi.list(reportId).then(setTranslations)} />
              )}
              {rightPanelMode === 'comments' && report && (
                <CommentsPane reportId={report.id} activePageId={activePage?.id}
                  pageNames={Object.fromEntries(report.pages.map(p => [p.id, p.name]))} />
              )}
              {rightPanelMode === 'schedule' && (
                <SchedulePanel reportId={reportId} />
              )}
              {rightPanelMode === 'parameters' && (
                <div style={{ padding: 12 }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 8 }}>
                    Report parameters
                  </div>
                  <p style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 10 }}>
                    Reference a parameter as @name in a filter value or a calculated expression.
                    Viewers set values in the bar above the canvas.
                  </p>

                  {/* System parameters -- always available, no setup needed. Expanded
                      server-side (apply_user_context) wherever an author expression is
                      evaluated: dataset filters, calculated columns, measures, RLS rules. */}
                  <div style={{ border: '1px solid var(--border)', borderRadius: 6, padding: 8, marginBottom: 10 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 6 }}>
                      System parameters
                    </div>
                    <p style={{ fontSize: 10.5, color: 'var(--muted)', margin: '0 0 6px' }}>
                      Always available in any expression -- no setup needed. Resolve to the
                      viewing user, so e.g. <code>owner == USEREMAIL()</code> scopes a filter
                      to "my data" for everyone who opens the report.
                    </p>
                    {[
                      { token: 'USEREMAIL()', label: 'Current user email' },
                      { token: 'USERID()',    label: 'Current user id' },
                      { token: 'ORGID()',     label: 'Current organization id' },
                      { token: 'ORGNAME()',   label: 'Current organization name' },
                    ].map(p => (
                      <div key={p.token} style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 10.5, padding: '2px 0' }}>
                        <span style={{ fontFamily: 'var(--mono)', color: 'var(--accent)' }}>{p.token}</span>
                        <span style={{ color: 'var(--muted)' }}>{p.label}</span>
                      </div>
                    ))}
                  </div>

                  {paramDefs.map((d, i) => (
                    <div key={i} style={{ border: '1px solid var(--border)', borderRadius: 6, padding: 8, marginBottom: 8, display: 'flex', flexDirection: 'column', gap: 5 }}>
                      <input aria-label={`Parameter ${i + 1} name`} value={d.name} placeholder="name"
                        onChange={e => setParamDefs(defs => defs.map((x, j) => j === i ? { ...x, name: e.target.value } : x))}
                        style={{ fontSize: 11 }} />
                      <select aria-label={`Parameter ${i + 1} type`} value={d.param_type}
                        onChange={e => setParamDefs(defs => defs.map((x, j) => j === i ? { ...x, param_type: e.target.value as never } : x))}
                        style={{ fontSize: 11 }}>
                        <option value="number">Number</option>
                        <option value="text">Text</option>
                        <option value="date">Date</option>
                        <option value="expression">Expression (computed)</option>
                      </select>
                      <input aria-label={`Parameter ${i + 1} default`} value={d.default_value ?? ''}
                        placeholder={d.param_type === 'expression' ? 'expression e.g. AVG(revenue)' : 'default value'}
                        onChange={e => setParamDefs(defs => defs.map((x, j) => j === i ? { ...x, default_value: e.target.value } : x))}
                        style={{ fontSize: 11 }} />
                      {d.param_type === 'expression' && (
                        <span style={{ fontSize: 10.5, color: 'var(--muted)' }}>Computed over the whole source (immune to filters); viewers cannot change it. Import datasets only.</span>
                      )}
                      {d.param_type === 'number' && (
                        <div style={{ display: 'flex', gap: 4 }}>
                          {(['min', 'max', 'step'] as const).map((part, k) => (
                            <input key={part} aria-label={`Parameter ${i + 1} ${part}`}
                              placeholder={part} type="number"
                              value={(d.options ?? [])[k] ?? ''}
                              onChange={e => setParamDefs(defs => defs.map((x, j) => {
                                if (j !== i) return x
                                const opts = [...(x.options ?? ['', '', ''])]
                                while (opts.length < 3) opts.push('')
                                opts[k] = e.target.value
                                return { ...x, options: opts.some(o => o !== '') ? opts : [] }
                              }))}
                              style={{ fontSize: 11, width: 62 }} />
                          ))}
                        </div>
                      )}
                      {d.param_type === 'number' && (
                        <span style={{ fontSize: 10.5, color: 'var(--muted)' }}>min/max/step turn this into a what-if slider</span>
                      )}
                      {d.param_type === 'text' && (
                        <input aria-label={`Parameter ${i + 1} options`} value={(d.options ?? []).join(', ')} placeholder="options, comma separated (optional)"
                          onChange={e => setParamDefs(defs => defs.map((x, j) => j === i ? { ...x, options: e.target.value.split(',').map(o => o.trim()).filter(Boolean) } : x))}
                          style={{ fontSize: 11 }} />
                      )}
                      <button className="btn btn-ghost btn-sm" style={{ alignSelf: 'flex-end', fontSize: 11 }}
                        onClick={() => setParamDefs(defs => defs.filter((_, j) => j !== i))}>
                        Remove
                      </button>
                    </div>
                  ))}
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button className="btn btn-ghost btn-sm" style={{ fontSize: 11 }}
                      onClick={() => setParamDefs(defs => [...defs, { name: '', param_type: 'number', default_value: '' }])}>
                      + Add parameter
                    </button>
                    <button className="btn btn-primary btn-sm" style={{ fontSize: 11 }}
                      onClick={() => {
                        const prev = savedParams.current
                        const next = paramDefs
                        return parametersApi.save(reportId, next)
                        .then(saved => {
                          setParamDefs(saved); savedParams.current = saved
                          pushUndo({ label: 'Change report parameters',
                            undo: async () => { const r = await parametersApi.save(reportId, prev); setParamDefs(r); savedParams.current = r },
                            redo: async () => { const r = await parametersApi.save(reportId, next); setParamDefs(r); savedParams.current = r } })
                        })
                        .then(() => toast.success('Parameters saved'))
                        .catch(e => toast.error(e?.response?.data?.detail ?? 'Could not save parameters'))
                      }}>
                      Save
                    </button>
                  </div>
                </div>
              )}
              {rightPanelMode === 'reportrules' && (
                <div style={{ padding: '14px 14px 0' }}>
                  {/* Report-level rules apply to every widget on every page, so there is no
                      single widget result shape to pull column names from. 'name' and 'value'
                      are the two columns every series- and scalar-shaped widget result exposes
                      (bar/line/pie category+measure, KPI/gauge scalar, etc.), so they're the
                      only columns that are safe to offer generically here. */}
                  <DisplayRulesPanel
                    rules={report.display_rules ?? []}
                    columns={['name', 'value']}
                    onChange={updateReportDisplayRules}
                    errors={reportRuleErrors}
                  />
                </div>
              )}
              {rightPanelMode === 'ask' && (
                dataset?.data_source_id != null ? (
                  <ChatPane dataSourceId={dataset.data_source_id} />
                ) : chatDatasetIds.length > 0 ? (
                  <ChatPane datasetIds={chatDatasetIds} />
                ) : (
                  <div style={{ padding: 14, fontSize: 12, color: 'var(--muted)' }}>
                    Attach a dataset to this report before asking questions.
                  </div>
                )
              )}
              {rightPanelMode === 'default' && (
                <>
                  <div style={{ padding:'9px 13px', borderBottom:'1px solid var(--border)', display:'flex', alignItems:'center', justifyContent:'space-between', gap:8 }}>
                    <span style={{ fontSize:12, fontWeight:600, color:'var(--text)', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
                      {selectedW
                        ? `Widget: ${selectedW.title || WIDGET_CATALOG.find(w => w.type === selectedW.widget_type)?.label || selectedW.widget_type}`
                        : `Page: ${activePage?.name ?? ''}`}
                    </span>
                    <div style={{ display:'flex', alignItems:'center', gap:8, flexShrink:0 }}>
                      <button style={{ background:'none', border:'none', color:'var(--accent)', cursor:'pointer', fontSize:11, padding:0 }}
                        onClick={() => setRightPanelMode('parameters')}>
                        {tr('builder.reportSettings')}
                      </button>
                      {selectedW && (
                        <button aria-label="Deselect widget" title="Deselect widget"
                          style={{ background:'none', border:'none', color:'var(--muted)', cursor:'pointer', fontSize:14 }}
                          onClick={() => setSelectedW(null)}>
                          x
                        </button>
                      )}
                    </div>
                  </div>
                  {/* Pick the object to edit, rather than finding it on the
                      canvas. Every settings pane in SAS carries this, and it is
                      what makes an object's settings reachable at all: a widget
                      inside a container, a small one, or one sitting under
                      another in a precision layout can be genuinely hard to
                      click. The page is in the same list, because page settings
                      are settings too. */}
                  {activePage && (pageWidgets.length > 0) && (
                    <div style={{ padding: '0 14px 8px' }}>
                      <label htmlFor="object-picker" style={{ display: 'block', fontSize: 11,
                        fontWeight: 700, color: 'var(--muted)', marginBottom: 4 }}>
                        {tr('builder.objectToEdit')}
                      </label>
                      <select id="object-picker" style={{ width: '100%', fontSize: 12 }}
                        value={selectedW ? String(selectedW.id) : 'page'}
                        onChange={e => {
                          const v = e.target.value
                          setSelectedW(v === 'page' ? null
                            : pageWidgets.find(w => String(w.id) === v) ?? null)
                        }}>
                        <option value="page">Page — {activePage.name}</option>
                        {pageWidgets.map(w => (
                          <option key={w.id} value={String(w.id)}>
                            {w.title || w.widget_type} ({w.widget_type})
                          </option>
                        ))}
                      </select>
                    </div>
                  )}

                  {selectedW
                    ? <WidgetConfigPanel geography={geography} widget={selectedW} columns={columns} datasets={datasets} primaryDatasetId={report.dataset_id} pages={report.pages} hierarchy={hierarchy} onHierarchyRefresh={refreshHierarchy} bookmarks={bookmarks} onUpdate={updateWidgetConfig} ruleErrors={perfStats[selectedW.id]?.ruleErrors}
                      distinctCounts={Object.fromEntries(Object.entries(hints).flatMap(([k, h]) => typeof (h as { distinct?: unknown })?.distinct === 'number' ? [[k, (h as { distinct: number }).distinct]] : []))} />
                    : activePage && <PagePropertiesPanel reportId={reportId} page={activePage} columns={columns} onUpdate={updatePageProps}
                        pages={report.pages} bookmarks={bookmarks} onSelectWidget={setSelectedW}
                        // The palette picker moved here from a row of unlabeled
                        // dots in the header, where each theme was one colour
                        // and no name.
                        palettes={[
                          ...Object.keys(THEMES).map(key => ({ key, name: PALETTE_NAME[key] ?? key[0].toUpperCase() + key.slice(1), colors: THEMES[key] })),
                          ...Object.entries(orgThemes).map(([key, t]) => ({ key, name: t.name, colors: t.colors })),
                        ]}
                        currentPalette={report.theme ?? 'default'}
                        onPalette={setThemeUndoable} />
                  }
                </>
              )}
            </CollapsibleSide>
          )}
        </div>
        </CrossFilterProvider>
        </>
        )}

        {pdfDialog && (
          <PdfOptionsDialog pages={report.pages.filter(p => (p.page_type ?? 'normal') === 'normal').map(p => ({ id: p.id, name: p.name }))}
            onClose={() => setPdfDialog(false)}
            onDownload={o => {
              setPdfDialog(false)
              reportsApi.downloadPdf(reportId, report.name, o)
                .then(() => toast.success('PDF downloaded'))
                .catch(() => toast.error('Could not generate the PDF'))
            }} />
        )}

        {geoCheck && report.dataset_id != null && (
          <GeoMatchCheck datasetId={report.dataset_id} column={geoCheck.column}
            setId={geoCheck.setId} setName={geoCheck.setName}
            onClose={() => setGeoCheck(null)}
            onCommit={() => { const g = geoCheck; setGeoCheck(null); void classifyGeography(g.column, g.setId) }} />
        )}

        {shortcutsOpen && (
          <div
            onClick={() => setShortcutsOpen(false)}
            style={{ position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0,0,0,.45)',
              display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            {/* The role belongs on the panel; the backdrop is the scrim, not
                the dialog. And a keyboard-shortcuts reference that cannot be
                closed from the keyboard is its own contradiction. */}
            <div ref={shortcutsRef} role="dialog" aria-modal="true" aria-label="Keyboard shortcuts"
              onClick={e => e.stopPropagation()}
              style={{ background: 'var(--surface)', border: '1px solid var(--border)',
                borderRadius: 'var(--radius)', padding: 20, minWidth: 320, fontSize: 13 }}>
              <div style={{ fontWeight: 700, marginBottom: 10 }}>Keyboard shortcuts</div>
              <table style={{ borderCollapse: 'collapse' }}>
                <tbody>
                  {[['Ctrl+K', 'Jump to any report, dataset or page'],
                    ['Arrow keys', 'Move the selected widget'],
                    ['Shift + arrows', 'Resize the selected widget'],
                    ['Delete', 'Remove the selected widget'],
                    ['Ctrl+Z', 'Undo the last change (the toolbar names it)'],
                    ['Ctrl+Y / Ctrl+Shift+Z', 'Redo'],
                    ['Escape', 'Deselect / close'],
                    ['?', 'Toggle this reference']].map(([k, d]) => (
                    <tr key={k}>
                      <td style={{ padding: '3px 14px 3px 0' }}><kbd style={{ background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 4, padding: '1px 6px', fontSize: 11 }}>{k}</kbd></td>
                      <td style={{ padding: '3px 0', color: 'var(--muted)' }}>{d}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        <StatusBar
          pageIndex={report.pages.findIndex(p => p.id === activePage?.id)}
          pageCount={report.pages.length}
          saveState={saving ? 'saving' : 'saved'}
          zoom={zoom}
          onZoomChange={setZoom}
        />
      </div>
      {/* The page copilot: edit THIS page in plain language. Edit mode only —
          it writes through the same endpoints as the GUI, so offering it to a
          view-only user would be offering edits the server refuses. Keyed by
          page so switching pages starts a fresh, page-scoped conversation. */}
      {canEdit && editMode && activePage && (
        <CopilotChat key={activePage.id} reportId={reportId} pageId={activePage.id}
          selectedWidgetId={selectedW?.id ?? null}
          onApplied={onCopilotApplied} />
      )}
      {shareOpen && (
        <ShareLinksDialog reportId={report.id} onClose={() => setShareOpen(false)} />
      )}
      {accessOpen2 && (
        <AccessExplainer decisions={Object.values(access)}
          sensitivity={sens ? { effective: sens.effective, reasons: sens.effective_reasons } : null}
          onClose={() => setAccessOpen2(false)} />
      )}
      {accessOpen && (
        <AccessDialog reportId={report.id} onClose={() => setAccessOpen(false)} />
      )}
      {explainColumn != null && report.dataset_id && (
        <ExplainDialog datasetId={report.dataset_id} column={explainColumn}
          onClose={() => setExplainColumn(null)} />
      )}
      {outlierColumn != null && report.dataset_id && (
        <OutlierDetailsDialog datasetId={report.dataset_id} column={outlierColumn}
          onClose={() => setOutlierColumn(null)} />
      )}
      {!editMode && popupPage && (
        <PopupOverlay page={popupPage} onClose={() => setPopupPage(null)}
          onExport={access.download && !access.download.allowed ? undefined : () => {
            reportsApi.downloadPdf(reportId, `${report.name} — ${popupPage.name}`, { pages: [popupPage.id] })
              .then(() => toast.success('PDF downloaded'))
              .catch(() => toast.error('Could not build the PDF'))
          }}
          renderWidget={widget => (
            <WidgetRenderer
              widget={localise(widget)}
              datasetId={report.dataset_id}
              reportId={reportId}
              parameters={effectiveParams}
              onSetParameter={stableOnSetParameter}
              calculatedColumns={calcCols}
              columnFormats={columnFormats} geography={geography}
              datasets={datasets} relationships={relationships}
              editMode={false}
              promptFilter={popupPage.prompt_column && promptValues[popupPage.id]
                ? { column: popupPage.prompt_column, value: promptValues[popupPage.id] } : activePromptFilter}
              onFetchComplete={handleFetchComplete}
              pages={report.pages}
              reportDisplayRules={report.display_rules ?? EMPTY_RULES}
              reportFilters={report.common_filters ?? []}
              onDrillthrough={handleDrillthrough}
              hierarchy={hierarchy}
              bookmarks={bookmarks}
              onNavigateToPage={handleButtonNavigate}
              onApplyBookmark={handleButtonApplyBookmark}
              eagerFetch={kiosk}
            />
          )} />
      )}
      {!editMode && tooltipHover && (
        <TooltipPageOverlay page={tooltipHover.page} x={tooltipHover.x} y={tooltipHover.y}
          onDismiss={() => setTooltipHover(null)}
          renderWidget={widget => (
            <WidgetRenderer
              widget={localise(widget)}
              datasetId={report.dataset_id}
              reportId={reportId}
              parameters={effectiveParams}
              onSetParameter={stableOnSetParameter}
              calculatedColumns={calcCols}
              columnFormats={columnFormats} geography={geography}
              datasets={datasets} relationships={relationships}
              editMode={false}
              promptFilter={activePromptFilter}
              onFetchComplete={handleFetchComplete}
              pages={report.pages}
              reportDisplayRules={report.display_rules ?? EMPTY_RULES}
              reportFilters={report.common_filters ?? []}
              onDrillthrough={handleDrillthrough}
              hierarchy={hierarchy}
              bookmarks={bookmarks}
              onNavigateToPage={handleButtonNavigate}
              onApplyBookmark={handleButtonApplyBookmark}
              eagerFetch={kiosk}
            />
          )} />
      )}
    </div>
  )
}
