import { useEffect, useState, useCallback, useRef, useContext } from 'react'
import KeyInfluencersResultView from '../components/analysis/KeyInfluencersResult'
import { pickInfluencerOutcome } from './datasetDetail/influencerOutcome'
import AggregatesPanel from '../components/dataset/AggregatesPanel'
import ColumnMeaningPanel from '../components/dataset/ColumnMeaningPanel'
import AlertsPanel from '../components/dataset/AlertsPanel'
import PredictionModelsPanel from '../components/dataset/PredictionModelsPanel'
import { PipelineAlertsForm, PipelineHealthLine, usePipelineHealth } from '../components/dataset/PipelineHealth'
import ChecksPanel, { ChecksBlockedDialog } from '../components/dataset/ChecksPanel'
import IncrementalSettingsForm from '../components/dataset/IncrementalSettings'
import StatisticsPanel from '../components/StatisticsPanel'
import DatasetSensitivity from '../components/DatasetSensitivity'
import NotebookSnippet from '../components/NotebookSnippet'
import LoadError from '../components/ui/LoadError'
import LoadingState from '../components/ui/LoadingState'
import EmptyState from '../components/ui/EmptyState'
import { findingKey, pinsApi, reportsApi } from '../services/api'
import { navArrows, useDirection } from '../contexts/DirectionContext'
import { useParams, Link, useLocation, useSearchParams, useNavigate } from 'react-router-dom'
import { useCrumbTitle } from '../lib/crumb'
import NotFound from './NotFound'
import { useT } from '../i18n'
import OutlierDetailsDialog from '../components/report/OutlierDetailsDialog'
import IconLabel from '../components/ui/IconLabel'
import {
  Bot, Plug, FolderOpen, LayoutDashboard as OverviewIcon, Table2, Ruler, RefreshCw, Sparkles,
  Pin, Link2, TriangleAlert, Search, BellRing, Brain, Layers, BookOpen, ShieldCheck,
} from 'lucide-react'
import { insightsApi, datasetsApi, analysisApi, dataPreviewApi, filterExprApi, dataSourcesApi, prepApi } from '../services/api'
import type { PrepStep } from '../services/api'
import { mergeCellEdit } from '../lib/cellEdits'
import FindingChart from '../components/insights/FindingChart'
import type { Dataset, CalcColumn, CheckResult, DataPreviewFilter, DataSource, AssociationRulesResult, KeyInfluencersResult, SegmentResult } from '../services/api'
import CalcColumnsPanel from '../components/report/CalcColumnsPanel'
import PrepPipelinePanel from '../components/report/PrepPipelinePanel'
import MeasuresPanel from '../components/report/MeasuresPanel'
import CustomCategoryPanel from '../components/report/CustomCategoryPanel'
import ExpressionBuilder from '../components/expr/ExpressionBuilder'
import QueryBuilderDialog from '../components/QueryBuilderDialog'
import DatasetShareDialog from '../components/DatasetShareDialog'
import { AuthContext } from '../contexts/AuthContext'
import toast from 'react-hot-toast'
import SchemaBreakDialog, { type SchemaBreak } from '../components/dataset/SchemaBreakDialog'
import { useJob } from '../components/jobs/useJob'
import { newIdempotencyKey } from '../components/jobs/idempotency'
import { isJobActive, jobsApi, type Job } from '../services/api'
import DataQualityPanel from '../components/dataset/DataQualityPanel'

import { type Tab, OPS, FILTER_FUNC_CATS, PAGE_SIZE } from './datasetDetail/constants'
import { certificationOf, isCertified } from '../lib/cleanDatasets'

/** 5.5: a server error in an analysis panel reads as "run analysis first",
 *  never as a bare "Internal server error" on a dataset someone just made. */
const notReadyOr = (err: any, fallback: string, notReady: string): string => {
  const status = err?.response?.status
  const detail = err?.response?.data?.detail
  if ((typeof status === 'number' && status >= 500) || detail === 'Internal server error' || detail === 'Internal Server Error') {
    return notReady
  }
  return typeof detail === 'string' ? detail : fallback
}

export { fmtMean } from '../components/analysis/KeyInfluencersResult'

export default function DatasetDetail() {
  const arrows = navArrows(useDirection().rtl)
  const tr = useT()
  // In the interface's language, not the browser's: an English page read
  // "Last refreshed 28ص 1:38:17 2026/9/" on an Arabic-locale machine (live QA
  // 2026-09-28).
  const { language } = useDirection()
  const refreshedWhen = (iso: string) => {
    const d = new Date(iso)
    return isNaN(d.getTime()) ? '' : d.toLocaleString(language, { dateStyle: 'medium', timeStyle: 'short' })
  }
  const { id } = useParams<{ id: string }>()
  const dsId   = Number(id)
  const badId = !/^\d+$/.test(id ?? '')
  const navigate = useNavigate()
  // "Chart this data" from the page where a person is looking at it. Without
  // it the dataset page was a dead end: the way to a chart went back out to
  // Dashboards, New, Add data, and picking this same dataset again.
  const [building, setBuilding] = useState(false)
  const buildDashboard = async () => {
    if (!ds) return
    setBuilding(true)
    try {
      const report = await reportsApi.create({ name: ds.name, dataset_id: ds.id })
      navigate(`/reports/${(report as { id: number }).id}`)
    } catch (e) {
      toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        ?? 'Could not create the dashboard')
      setBuilding(false)
    }
  }

  const [ds,       setDs]       = useState<Dataset | null>(null)
  useCrumbTitle(ds?.name)
  const [analysis, setAnalysis] = useState<any>(null)
  const [loading,  setLoading]  = useState(true)
  const [running,  setRunning]  = useState(false)
  // The Insights hub deep-links here: `?tab=statistics` opens a tab directly,
  // and `#insights` / `#influencers` / `#associations` / `#segment` /
  // `#anomalies` land on an Overview section (scrolled to below, once the
  // sections exist in the DOM).
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const urlTab = searchParams.get('tab')
  const [tab,      setTab]      = useState<Tab>(
    urlTab === 'statistics' || urlTab === 'data' || urlTab === 'alerts' || urlTab === 'checks' ||
    urlTab === 'models' || urlTab === 'aggregates' || urlTab === 'meaning'
      ? urlTab : 'overview')

  // Anomaly inspection (the report builder's OutlierDetailsDialog, mounted
  // here too so it is reachable from the data itself, not only from a widget).
  const [outlierColumn, setOutlierColumn] = useState('')
  const [outlierOpen,   setOutlierOpen]   = useState(false)

  useEffect(() => {
    const anchor = location.hash.replace('#', '')
    if (!anchor || loading) return
    // Anchors live on the Overview tab; switch there first, then scroll once
    // React has painted the sections. jsdom has no scrollIntoView -- guarded.
    setTab('overview')
    const t = setTimeout(() => {
      const el = document.getElementById(anchor)
      el?.scrollIntoView?.({ block: 'start' })
    }, 60)
    return () => clearTimeout(t)
  }, [location.hash, loading])

  // Data tab state
  const [calcCols,   setCalcCols]   = useState<CalcColumn[]>([])
  const [filterRows, setFilterRows] = useState<{ id: number; column: string; op: DataPreviewFilter['op']; value: string }[]>([])
  const [nextFid,    setNextFid]    = useState(1)
  const [preview,    setPreview]    = useState<{ columns: string[]; rows: unknown[][]; total: number } | null>(null)
  const [pvError,    setPvError]    = useState<string | null>(null)
  const [pvLoading,  setPvLoading]  = useState(false)
  const [page,       setPage]       = useState(0)
  const [sortBy,     setSortBy]     = useState<string | null>(null)
  const [sortDir,    setSortDir]    = useState<'asc' | 'desc'>('asc')
  const [search,     setSearch]     = useState('')
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // ── In-place cell editing ───────────────────────────────────────────────────
  // SAS edits the source table; a correction typed here becomes an `edit_cells`
  // PREP STEP, so the uploaded file is never rewritten and the change is visible
  // in the pipeline beside every other transform. Merge rules: lib/cellEdits.ts.
  const [editCells,  setEditCells]  = useState(false)
  const [keyColumn,  setKeyColumn]  = useState<string>('')
  const [editingAt,  setEditingAt]  = useState<{ row: number; column: string } | null>(null)
  const [prepSteps,  setPrepSteps]  = useState<PrepStep[]>([])

  // Global filter state
  const [filterExpr,    setFilterExpr]    = useState('')
  const [savedFilter,   setSavedFilter]   = useState<string | null>(null)
  const [filterPreview, setFilterPreview] = useState<{ ok: boolean; passing?: number; total: number; error?: string } | null>(null)
  const [filterSaving,  setFilterSaving]  = useState(false)
  // E12: a refresh is a durable job. `queueing` covers the request that
  // queues it; the job itself is followed until it ends.
  const [queueing,      setQueueing]      = useState(false)
  const [refreshJobId,  setRefreshJobId]  = useState<number | null>(null)
  const [refreshByOther, setRefreshByOther] = useState(false)
  const refreshReq = useRef<{ mode: 'full' | 'incremental'; cursorColumn?: string }>({ mode: 'full' })
  const { job: refreshJob, setJob: setRefreshJob } = useJob(refreshJobId, j => { void onRefreshSettled(j) })
  const refreshing = queueing || (refreshJobId != null && (!refreshJob || isJobActive(refreshJob)))
  // F3: load-mode picker -- full reload vs. watermark-driven incremental append.
  const [showRefreshMenu, setShowRefreshMenu] = useState(false)
  const [refreshMode,     setRefreshMode]     = useState<'full' | 'incremental'>('full')
  const [refreshCursorCol, setRefreshCursorCol] = useState('')
  // The scheduling control lives in the SAME menu as the manual refresh: both
  // answer "when does this data update", and splitting them would leave a user
  // hunting for one having found the other.
  const [savingSchedule, setSavingSchedule] = useState(false)
  // D1: "Edit query" reopens the visual query builder hydrated from the
  // dataset's saved query_model -- only offered when there is one to restore.
  const [editingQuerySource, setEditingQuerySource] = useState<DataSource | null>(null)
  const [queryEditLoading, setQueryEditLoading] = useState(false)
  // SH1: share management is admin-gated (no owner concept on a dataset).
  // Reads the context directly (not the throwing useAuth()) so this page still
  // renders standalone in tests that don't wrap it in an AuthProvider -- an
  // absent context degrades to "not admin" (hide Share) rather than crashing.
  const isAdmin = !!useContext(AuthContext)?.user?.role?.is_org_admin
  const [showShareDialog, setShowShareDialog] = useState(false)
  const [rebuilding, setRebuilding] = useState(false)
  const [otherNames, setOtherNames] = useState<Record<number, string>>({})

  // Provenance for a dataset materialized from others. Read straight off
  // column_meta, where the backend records the recipe -- no extra endpoint.
  const derivedFrom = (ds?.column_meta as Record<string, any> | undefined)?.__derived_from__ as
    | { source_dataset_id?: number; join_dataset_ids?: number[]; built_at?: string
        dataflow_id?: number }
    | undefined

  // Three kinds of dataset can be scheduled, and only these three:
  //   * source-backed  -- re-reads its connection
  //   * derived        -- replays the recipe in __derived_from__
  //   * DirectQuery is excluded: nothing is cached, so there is nothing to refresh.
  // A dataflow's OUTPUT is deliberately excluded too. Its schedule lives on the
  // dataflow, which drives every output together; a second control here would
  // let one output silently drift from its siblings.
  const ownedByDataflow = typeof derivedFrom?.dataflow_id === 'number'
  const canSchedule = ds != null && ds.mode !== 'directquery' && !ownedByDataflow
    && (!!ds.data_source_id || (!!derivedFrom && !ownedByDataflow))

  useEffect(() => {
    if (!derivedFrom) return
    datasetsApi.list()
      .then(list => setOtherNames(Object.fromEntries(list.map(d => [d.id, d.name]))))
      .catch(() => {})
  }, [!!derivedFrom])

  const derivedSourceNames = derivedFrom
    ? [derivedFrom.source_dataset_id, ...(derivedFrom.join_dataset_ids ?? [])]
        .filter((id): id is number => typeof id === 'number')
        .map(id => otherNames[id] ?? `#${id}`)
        .join(' + ')
    : ''

  // The INNER analysis call was already guarded; the outer dataset fetch was
  // not, so a deleted dataset or a network blip left `ds` null and the page
  // showed "Loading…" with no error and no way out.
  const [loadError, setLoadError] = useState<unknown>(null)
  const loadDataset = useCallback(() => {
    setLoadError(null)
    if (!Number.isFinite(dsId)) return
    datasetsApi.get(dsId).then(ds => {
      setDs(ds)
      setCalcCols(ds.calculated_columns ?? [])
      const expr = ds.default_filter_expr ?? ''
      setFilterExpr(expr)
      setSavedFilter(expr || null)
      // Analysis needs a local file to load; DirectQuery datasets don't have
      // one (the backend would 400) — skip the request entirely rather than
      // firing a call that can only fail.
      if (ds.mode === 'directquery') { setLoading(false); return }
      analysisApi.get(dsId).then(setAnalysis)
        // E06: straight after an import the profile is run, not left behind a
        // button -- the first thing a person does with new data is look at it.
        // Only then: a normal visit does not trigger a full scan. `new` is
        // dropped from the address so a reload does not scan again.
        .catch(() => {
          // Once per dataset: the load runs twice (StrictMode in development,
          // or a reload of the same dataset), both GETs 404 before either
          // run lands, and `searchParams` still says new=1 after replaceState
          // -- two scans and two "Analysis complete" toasts (live QA 2026-09-28).
          if (searchParams.get('new') === '1' && autoAnalysedRef.current !== dsId) {
            autoAnalysedRef.current = dsId
            window.history.replaceState(null, '', window.location.pathname)
            void runAnalysisRef.current?.()
          }
        })
        .finally(() => setLoading(false))
    }).catch(e => { setLoadError(e ?? new Error('failed')); setLoading(false) })
  }, [dsId])
  useEffect(loadDataset, [loadDataset])

  const loadPreview = useCallback(async (
    pg    = page,
    frows = filterRows,
    cc    = calcCols,
    sb    = sortBy,
    sd    = sortDir,
    srch  = search,
  ) => {
    if (!ds) return
    setPvLoading(true)
    setPvError(null)
    try {
      if (ds.mode === 'directquery') {
        // Filtering/sorting/search/calculated columns aren't pushed down for
        // DirectQuery previews yet -- local filter/sort/search state is ignored
        // rather than silently sent and dropped server-side (see the note
        // rendered above the table for this same reason).
        const result = await dataPreviewApi.query(dsId, [], [], PAGE_SIZE, 0)
        setPreview(result)
        return
      }
      const activeFilters: DataPreviewFilter[] = frows
        .filter(f => f.column && f.value !== '')
        .map(f => ({ column: f.column, op: f.op, value: f.value }))
      const result = await dataPreviewApi.query(
        dsId, activeFilters, cc, PAGE_SIZE, pg * PAGE_SIZE,
        sb ?? undefined, sd, srch || undefined,
      )
      setPreview(result)
    } catch (err: any) {
      const msg = err?.response?.data?.detail ?? 'Failed to load data'
      setPvError(msg)
    } finally {
      setPvLoading(false)
    }
  }, [ds, dsId, page, filterRows, calcCols, sortBy, sortDir, search])

  /** Turn a typed cell into a saved prep step. The whole pipeline is written
   *  wholesale (the prep contract), so the steps the user already had are read
   *  first and carried through -- dropping them would be a silent data change. */
  const saveCellEdit = useCallback(async (
    rowIndex: number, column: string, raw: string,
  ) => {
    if (!preview) return
    const key = preview.columns.indexOf(keyColumn)
    const at  = preview.columns.indexOf(column)
    if (key === -1 || at === -1) return
    const row = preview.rows[rowIndex] as unknown[]
    const before = row[at]
    // An empty box means "clear this cell", which is a real correction; but an
    // empty box over an already-empty cell is somebody pressing Escape.
    const value: unknown = raw === '' ? null : raw
    if (String(before ?? '') === raw) return
    const rowKey = String(row[key] ?? '')
    try {
      const existing = await prepApi.get(dsId)
      const next = mergeCellEdit(existing, { keyColumn, column, key: rowKey, value })
      await prepApi.set(dsId, next)
      setPrepSteps(next)
      toast.success(`Saved as a prep step — ${column} for ${rowKey}`)
      await loadPreview()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail
      toast.error(detail ?? (err as Error)?.message ?? 'Could not save the correction')
    }
  }, [preview, keyColumn, dsId, loadPreview])

  // Load preview whenever tab is 'data' and ds is ready
  useEffect(() => {
    if (tab === 'data' && ds) loadPreview(0, filterRows, calcCols)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, ds])

  const runAnalysisRef = useRef<(() => Promise<void>) | null>(null)
  const runAnalysis = async () => {
    setRunning(true)
    try {
      const r = await analysisApi.run(dsId)
      setAnalysis(r)
      toast.success('Analysis complete')
    } catch { toast.error('Analysis failed') }
    finally { setRunning(false) }
  }
  runAnalysisRef.current = runAnalysis

  const applyFilters = () => {
    setPage(0)
    loadPreview(0, filterRows, calcCols, sortBy, sortDir, search)
  }

  const handleSort = (col: string) => {
    let newBy: string | null = col
    let newDir: 'asc' | 'desc' = 'asc'
    if (sortBy === col) {
      if (sortDir === 'asc') { newDir = 'desc' }
      else { newBy = null; newDir = 'asc' }
    }
    setSortBy(newBy)
    setSortDir(newDir)
    setPage(0)
    loadPreview(0, filterRows, calcCols, newBy, newDir, search)
  }

  const handleSearch = (val: string) => {
    setSearch(val)
    if (searchTimer.current) clearTimeout(searchTimer.current)
    searchTimer.current = setTimeout(() => {
      setPage(0)
      loadPreview(0, filterRows, calcCols, sortBy, sortDir, val)
    }, 350)
  }

  const addFilter = () => {
    const firstCol = ds?.columns?.[0]?.name ?? ''
    setFilterRows(p => [...p, { id: nextFid, column: firstCol, op: 'eq', value: '' }])
    setNextFid(p => p + 1)
  }

  const updateFilter = (id: number, key: string, val: string) =>
    setFilterRows(p => p.map(f => f.id === id ? { ...f, [key]: val } : f))

  const removeFilter = (id: number) =>
    setFilterRows(p => p.filter(f => f.id !== id))

  const handleCalcColsChanged = (cols: CalcColumn[]) => {
    setCalcCols(cols)
    setPage(0)
    loadPreview(0, filterRows, cols, sortBy, sortDir, search)
  }

  const testGlobalFilter = async () => {
    if (!filterExpr.trim()) return
    setFilterPreview(null)
    try {
      const result = await filterExprApi.preview(dsId, filterExpr, calcCols)
      setFilterPreview(result)
    } catch {
      setFilterPreview({ ok: false, error: 'Request failed', total: 0 })
    }
  }

  const saveGlobalFilter = async (expr?: string) => {
    const val = expr !== undefined ? expr : filterExpr
    setFilterSaving(true)
    try {
      const updated = await filterExprApi.update(dsId, val || null)
      setDs(updated)
      setSavedFilter(val || null)
      setFilterPreview(null)
      toast.success(val ? 'Global filter saved' : 'Global filter cleared')
      if (tab === 'data') loadPreview(0, filterRows, calcCols, sortBy, sortDir, search)
    } catch {
      toast.error('Failed to save filter')
    } finally {
      setFilterSaving(false)
    }
  }

  const handleRefresh = async (mode: 'full' | 'incremental' = 'full', cursorColumn?: string,
                               resolve?: { column_map?: Record<string, string>; force?: boolean; publish_anyway?: boolean }) => {
    setQueueing(true)
    setPvError(null)
    setShowRefreshMenu(false)
    setSchemaBreak(null)
    setChecksBlocked(null)
    refreshReq.current = { mode, cursorColumn }
    try {
      // Queued, not awaited: the reload runs in the server's worker, so a
      // closed tab or a proxy timeout loses nothing, and it can be stopped.
      const job = await datasetsApi.queueRefresh(dsId, {
        mode, cursor_column: mode === 'incremental' ? (cursorColumn || undefined) : undefined,
        ...resolve,
      }, newIdempotencyKey())
      setRefreshJobId(job.id)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? tr('refreshJob.failed'))
    } finally {
      setQueueing(false)
    }
  }

  /** The refresh job ended: show its data, its refusal or its stop. */
  const onRefreshSettled = async (job: Job) => {
    setRefreshJobId(null)
    if (job.state === 'succeeded') {
      const updated = await datasetsApi.get(dsId)
      setDs(updated)
      setCalcCols(updated.calculated_columns ?? [])
      if (job.result?.warning) {
        toast.error(job.result.warning)
      } else {
        toast.success(tr('refreshJob.done', { rows: (job.result?.row_count ?? updated.row_count).toLocaleString() }))
      }
      loadPreview(0, filterRows, updated.calculated_columns ?? [], sortBy, sortDir, search)
    } else if (job.state === 'failed' && job.error_code === 'schema_break' && job.result?.missing) {
      // E05: refused because the source dropped a column in use -- nothing
      // was written. Ask for the mapping instead of only toasting it.
      setSchemaBreak({
        info: { detail: job.error ?? '', missing: job.result.missing,
                suggestions: job.result.suggestions ?? {}, available: job.result.available ?? [],
                dependents: job.result.dependents ?? {} },
        mode: refreshReq.current.mode, cursorColumn: refreshReq.current.cursorColumn,
      })
    } else if (job.state === 'failed' && job.error_code === 'checks_blocked') {
      // Phase 3: a blocking check refused the new data; the old file stands.
      // Say which check, and let an editor publish anyway.
      setChecksBlocked({ detail: job.error ?? '', checks: job.result?.checks ?? [],
                         mode: refreshReq.current.mode, cursorColumn: refreshReq.current.cursorColumn })
      void datasetsApi.pipelineHealth(dsId).then(setPipelineHealth).catch(() => {})
    } else if (job.state === 'failed') {
      toast.error(job.error ?? tr('refreshJob.failed'))
    } else if (job.state === 'cancelled') {
      toast(tr('refreshJob.stopped'))
    }
  }

  // A page opened (or reloaded) while a refresh runs follows it.
  useEffect(() => {
    if (!Number.isFinite(dsId)) return
    let alive = true
    datasetsApi.activeRefresh(dsId).then(a => {
      if (!alive || !a) return
      if ('id' in a) setRefreshJobId(a.id)
      else if (a.by_someone_else) setRefreshByOther(true)
    }).catch(() => { /* the page works without it */ })
    return () => { alive = false }
  }, [dsId])

  const refreshStage = !refreshJob || !isJobActive(refreshJob) ? tr('dataset.refreshing')
    : refreshJob.cancel_requested ? tr('refreshJob.stopping')
    : refreshJob.state === 'queued' ? tr('refreshJob.queued')
    : refreshJob.progress?.stage === 'saving'
      ? tr('refreshJob.saving', { rows: (refreshJob.progress?.rows ?? 0).toLocaleString() })
      : tr('refreshJob.querying')
  const [schemaBreak, setSchemaBreak] = useState<
    { info: SchemaBreak; mode: 'full' | 'incremental'; cursorColumn?: string } | null>(null)
  const [checksBlocked, setChecksBlocked] = useState<
    { detail: string; checks: CheckResult[]; mode: 'full' | 'incremental'; cursorColumn?: string } | null>(null)

  /** Minutes, or null to clear. The server owns the 5-minute floor -- repeating
   *  the number here would be a second place to update when it changes, so the
   *  options simply start at it. */
  const handleSchedule = async (minutes: number | null) => {
    setSavingSchedule(true)
    try {
      const updated = await datasetsApi.setSchedule(dsId, minutes)
      setDs(updated)
      toast.success(minutes
        ? `Refreshing automatically every ${minutes} minutes`
        : 'Automatic refresh turned off')
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? 'Could not change the schedule')
    } finally {
      setSavingSchedule(false)
    }
  }

  const openEditQuery = async () => {
    if (!ds?.data_source_id) return
    setQueryEditLoading(true)
    try {
      const sources = await dataSourcesApi.list()
      const src = sources.find(s => s.id === ds.data_source_id)
      if (!src) { toast.error('Original connection no longer exists'); return }
      setEditingQuerySource(src)
    } catch {
      toast.error('Could not load the connection')
    } finally {
      setQueryEditLoading(false)
    }
  }

  const allColNames = [
    ...(ds?.columns ?? []).map(c => c.name),
    ...calcCols.map(c => c.name),
  ]

  const calcColNames = new Set(calcCols.map(c => c.name))

  // hooks live above the loading return -- a hook below it renders conditionally
  const [insights, setInsights] = useState<{ findings: { kind: string; score: number; title: string; detail: string; columns: string[]; novelty?: 'new' | 'changed' | 'unchanged' }[]; narrative: string } | null>(null)
  const [insightsBusy, setInsightsBusy] = useState(false)

  // A2: KMeans segmentation (automatic k) over the dataset's numeric columns.
  const [segment, setSegment] = useState<SegmentResult | null>(null)
  const [segmentBusy, setSegmentBusy] = useState(false)
  const [segmentError, setSegmentError] = useState<string | null>(null)
  const [influencers, setInfluencers] = useState<KeyInfluencersResult | null>(null)
  const [influencerTarget, setInfluencerTarget] = useState('')
  const [influencerBusy, setInfluencerBusy] = useState(false)
  const [influencerError, setInfluencerError] = useState<string | null>(null)
  // Numeric columns the default skipped as identifiers ("Left out"), and
  // whether there was no outcome to default to (then the reader picks).
  const [influencerSkipped, setInfluencerSkipped] = useState<string[]>([])
  const [influencerNeedsPick, setInfluencerNeedsPick] = useState(false)
  const [rules, setRules] = useState<AssociationRulesResult | null>(null)
  const [rulesBusy, setRulesBusy] = useState(false)
  const [rulesError, setRulesError] = useState<string | null>(null)

  // Auto-run: each of these fires once per dataset, the moment its section
  // exists, so a card clicked from the Insights hub lands on a result already
  // computed rather than one more button to press. A REF guard, not state --
  // it must survive the busy/error changes the run itself causes, or the
  // effect would refire the instant the first attempt finished.
  const segmentAutoRanFor = useRef<number | null>(null)
  const patternsAutoRanFor = useRef<number | null>(null)
  const autoAnalysedRef = useRef<number | null>(null)
  const influencersAutoRanFor = useRef<number | null>(null)

  const runSegment = useCallback(() => {
    if (!ds) return
    setSegmentBusy(true)
    setSegmentError(null)
    analysisApi.segment(ds.id)
      .then(setSegment)
      .catch((err: any) => setSegmentError(err?.response?.data?.detail ?? 'Segmentation failed'))
      .finally(() => setSegmentBusy(false))
  }, [ds])

  const runPatterns = useCallback(() => {
    if (!ds) return
    setRulesBusy(true)
    setRulesError(null)
    analysisApi.associationRules(ds.id)
      .then(setRules)
      .catch((err: any) => setRulesError(notReadyOr(err, 'Could not mine rules', tr('ov.notReady'))))
      .finally(() => setRulesBusy(false))
  }, [ds])

  const runInfluencers = useCallback((target: string) => {
    if (!ds || !target) return
    setInfluencerBusy(true)
    setInfluencerError(null)
    analysisApi.keyInfluencers(ds.id, target)
      .then(setInfluencers)
      .catch((err: any) => setInfluencerError(notReadyOr(err, 'Could not find influencers', tr('ov.notReady'))))
      .finally(() => setInfluencerBusy(false))
  }, [ds])

  useEffect(() => {
    // Mirrors the #segment section's own DirectQuery gate -- the section
    // never renders for one, and an effect is not tied to that JSX, so this
    // guard has to be restated here or a DirectQuery dataset would still
    // fire a call the backend has nothing to answer for that section.
    if (!ds || ds.mode === 'directquery' || segmentAutoRanFor.current === ds.id) return
    segmentAutoRanFor.current = ds.id
    runSegment()
  }, [ds, runSegment])

  useEffect(() => {
    if (!ds || patternsAutoRanFor.current === ds.id) return
    patternsAutoRanFor.current = ds.id
    runPatterns()
  }, [ds, runPatterns])

  useEffect(() => {
    if (!ds || influencersAutoRanFor.current === ds.id) return
    // The outcome to open on: a column marked worth explaining, then an
    // authored measure, then a numeric quantity -- never an identifier (KI-1,
    // see pickInfluencerOutcome). With none of those, nothing auto-runs and
    // the picker asks; a 1.00x table explaining `cohort_ref` was worse than
    // asking.
    influencersAutoRanFor.current = ds.id
    const pick = pickInfluencerOutcome(ds)
    setInfluencerSkipped(pick.skipped)
    setInfluencerNeedsPick(!pick.target)
    if (!pick.target) return
    setInfluencerTarget(pick.target)
    runInfluencers(pick.target)
  }, [ds, runInfluencers])

  // Pipeline phase 2: re-read on every finished refresh (the stamp moves),
  // so a fixed source clears the warning without a page reload.
  const [pipelineHealth, setPipelineHealth] = usePipelineHealth(
    badId || !ds || ds.mode === 'directquery' ? null : dsId, ds?.last_refreshed_at)
  // Phase 4: a dataset rebuilt from another can run after that source refreshes.
  const [afterSource, setAfterSource] = useState(false)
  useEffect(() => {
    if (badId || !ds || ds.data_source_id || ds.mode === 'directquery') return
    let live = true
    Promise.resolve().then(() => datasetsApi.incremental(dsId))
      .then(v => { if (live && v) setAfterSource(!!v.after_source) }).catch(() => {})
    return () => { live = false }
  }, [dsId, ds?.id, ds?.data_source_id])
  const chooseAfterSource = async () => {
    setSavingSchedule(true)
    try {
      setDs(await datasetsApi.setAfterSource(dsId, true))
      setAfterSource(true)
      toast.success(tr('dataset.afterSourceSet'))
    } catch (e) {
      toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? String(e))
    } finally { setSavingSchedule(false) }
  }

  if (badId) return <NotFound />
  if (loadError) {
    return <LoadError what="this dataset" error={loadError} onRetry={loadDataset} />
  }
  if (!ds) return <LoadingState />

  const numCols = Object.entries(analysis?.numeric?.columns  ?? {})
  const dtCols  = Object.entries(analysis?.datetime?.columns ?? {})
  const catCols = Object.entries(analysis?.categorical?.columns ?? {})

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {checksBlocked && (
        <ChecksBlockedDialog detail={checksBlocked.detail} checks={checksBlocked.checks}
          onKeep={() => setChecksBlocked(null)}
          onPublish={() => void handleRefresh(checksBlocked.mode, checksBlocked.cursorColumn, { publish_anyway: true })} />
      )}
      {schemaBreak && (
        <SchemaBreakDialog info={schemaBreak.info}
          onMap={column_map => void handleRefresh(schemaBreak.mode, schemaBreak.cursorColumn, { column_map })}
          onForce={column_map => void handleRefresh(schemaBreak.mode, schemaBreak.cursorColumn, { column_map, force: true })}
          onClose={() => setSchemaBreak(null)} />
      )}
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16, flexShrink: 0 }}>
        <Link to="/datasets" style={{ color: 'var(--muted)', fontSize: 12, textDecoration: 'none' }}>{arrows.back} {tr('dataset.back')}</Link>
        <h1 className="dl-page-title" style={{ flex: 1 }}>
          {ds.name}
          {ds.shared && (
            <span title={tr('dataset.sharedTitle')}
              style={{ fontSize: 11, fontWeight: 400, color: 'var(--accent)', marginInlineStart: 10,
                background: 'color-mix(in srgb, var(--accent) 15%, transparent)', borderRadius: 99, padding: '2px 8px', verticalAlign: 'middle' }}>
              <IconLabel icon={Link2}>{tr('dataset.sharedWithYou')}</IconLabel>
            </span>
          )}
        </h1>
        <DatasetSensitivity datasetId={ds.id} />
        {ds.mode !== 'directquery' && <NotebookSnippet datasetId={ds.id} datasetName={ds.name} />}
        {isAdmin && (
          <button className="btn btn-ghost btn-sm" onClick={() => setShowShareDialog(true)}>
            {tr('dataset.share')}
          </button>
        )}
        {isCertified(ds) && (
          <span data-testid="certified-badge" style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--success, #15803d)' }}
            title={tr('dsf.certifiedBy', { who: certificationOf(ds)?.by_email ?? '' })}>✓ {tr('dsf.badge')}</span>
        )}
        {isAdmin && (
          <button className="btn btn-ghost btn-sm" onClick={async () => {
            const on = !isCertified(ds)
            try {
              await datasetsApi.certify(ds.id, on)
              setDs(prev => prev ? { ...prev, column_meta: (() => {
                const m = { ...((prev.column_meta ?? {}) as unknown as Record<string, unknown>) }
                if (on) m['__certified__'] = { by_email: '', at: new Date().toISOString() }
                else delete m['__certified__']
                return m as unknown as typeof prev.column_meta
              })() } : prev)
            } catch { toast.error(tr('dsf.certify')) }
          }}>{isCertified(ds) ? tr('dsf.uncertify') : tr('dsf.certify')}</button>
        )}
        {ds.mode === 'directquery' && (
          <span title={tr('dataset.liveTitle')}
            style={{ fontSize: 11, color: 'var(--muted)', background: 'var(--surface2)',
              border: '1px solid var(--border)', borderRadius: 99, padding: '3px 10px' }}>
            <IconLabel icon={Plug}>{tr('dataset.live')}</IconLabel>
          </span>
        )}
        {/* E06 freshness: WHEN this data was loaded, for every imported
            dataset -- an uploaded file used to show nothing, so a stale
            upload read exactly like a fresh one. */}
        {!(ds.data_source_id || canSchedule) && ds.mode !== 'directquery' && ds.last_refreshed_at && (
          <div data-testid="dataset-freshness" style={{ fontSize: 11, color: 'var(--muted)', textAlign: 'end' }}>
            {tr('dataset.lastRefreshed', { when: refreshedWhen(ds.last_refreshed_at) })}
          </div>
        )}
        {(ds.data_source_id || canSchedule) && ds.mode !== 'directquery' && (
          <div style={{ position: 'relative' }}>
            {ds.last_refreshed_at && (
              <div style={{ fontSize: 11, color: 'var(--muted)', textAlign: 'end', marginBottom: 2 }}>
                {tr('dataset.lastRefreshed', { when: refreshedWhen(ds.last_refreshed_at) })}
              </div>
            )}
            <PipelineHealthLine health={pipelineHealth} />
            <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
              <button onClick={() => setShowRefreshMenu(v => !v)} disabled={refreshing || refreshByOther}
                className="btn btn-ghost btn-sm">
                {refreshing ? refreshStage
                  : <IconLabel icon={RefreshCw}>{ds.data_source_id ? tr('dataset.refreshFromSource') : tr('dataset.refreshSchedule')}</IconLabel>}
              </button>
              {refreshJob && isJobActive(refreshJob) && !refreshJob.cancel_requested && (
                <button className="btn btn-ghost btn-sm" data-testid="refresh-stop"
                  onClick={() => { void jobsApi.cancel(refreshJob.id).then(setRefreshJob).catch(() => {}) }}>
                  {tr('refreshJob.stop')}
                </button>
              )}
            </div>
            {/* Said once, politely: the stage is on the button above. */}
            <div role="status" style={{ fontSize: 11, color: 'var(--muted)', textAlign: 'end', marginTop: 2 }}>
              {refreshing && refreshJobId != null ? tr('refreshJob.background')
                : refreshByOther ? tr('refreshJob.someoneElse') : null}
            </div>
            {showRefreshMenu && (
              <div style={{ position: 'absolute', top: '100%', insetInlineEnd: 0, zIndex: 20, marginTop: 4,
                background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8,
                padding: 12, width: 240, boxShadow: '0 4px 16px rgba(0,0,0,0.15)' }}>
                {ds.data_source_id ? (<>
                <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>{tr('dataset.loadMode')}</div>
                <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, marginBottom: 6, cursor: 'pointer' }}>
                  <input type="radio" name="refresh-mode" checked={refreshMode === 'full'}
                    onChange={() => setRefreshMode('full')} />
                  {tr('dataset.fullReload')}
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, marginBottom: 8, cursor: 'pointer' }}>
                  <input type="radio" name="refresh-mode" checked={refreshMode === 'incremental'}
                    onChange={() => setRefreshMode('incremental')} />
                  {tr('dataset.incremental')}
                </label>
                {refreshMode === 'incremental' && (
                  <select value={refreshCursorCol} onChange={e => setRefreshCursorCol(e.target.value)}
                    className="input" style={{ width: '100%', fontSize: 12, marginBottom: 8 }}
                    aria-label="Watermark column">
                    <option value="">Watermark column…</option>
                    {ds.columns.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
                  </select>
                )}
                <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                  <button className="btn btn-ghost btn-sm" onClick={() => setShowRefreshMenu(false)}>{tr('common.cancel')}</button>
                  <button className="btn btn-primary btn-sm"
                    disabled={refreshMode === 'incremental' && !refreshCursorCol} title={refreshMode === 'incremental' && !refreshCursorCol ? 'An incremental refresh needs a cursor column: choose one first' : undefined}
                    onClick={() => handleRefresh(refreshMode, refreshCursorCol)}>
                    {tr('dataset.run')}
                  </button>
                </div>
                </>) : null}

                {/* Automatic refresh. Separated by a rule because it is a
                    different commitment from the button above: that one runs
                    now, this one keeps running without anybody present. */}
                <div style={ds.data_source_id
                  ? { borderTop: '1px solid var(--border)', marginTop: 12, paddingTop: 10 }
                  : {}}>
                  <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>{tr('dataset.autoRefresh')}</div>
                  <select
                    aria-label="Automatic refresh interval"
                    disabled={savingSchedule}
                    value={afterSource ? 'after' : ds.refresh_interval_minutes ?? ''}
                    onChange={e => {
                      const v = e.target.value
                      if (v === 'after') { void chooseAfterSource(); return }
                      if (afterSource) setAfterSource(false)
                      void handleSchedule(v ? Number(v) : null)
                    }}
                    className="input" style={{ width: '100%', fontSize: 12 }}>
                    <option value="">{tr('dataset.autoOff')}</option>
                    {!ds.data_source_id && <option value="after">{tr('dataset.afterSource')}</option>}
                    <option value="5">{tr('dataset.every5')}</option>
                    <option value="15">{tr('dataset.every15')}</option>
                    <option value="60">{tr('dataset.everyHour')}</option>
                    <option value="360">{tr('dataset.every6h')}</option>
                    <option value="1440">{tr('dataset.everyDay')}</option>
                  </select>
                  {ds.refresh_interval_minutes ? (
                    <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 4 }}>
                      {tr('dataset.autoNote')}
                    </div>
                  ) : null}
                </div>
                {pipelineHealth?.can_edit && ds.data_source_id && (
                  <IncrementalSettingsForm datasetId={ds.id} columns={(ds.columns ?? []).map(c => c.name)} />
                )}
                {pipelineHealth?.can_edit && (
                  <PipelineAlertsForm datasetId={ds.id} health={pipelineHealth} onSaved={setPipelineHealth} />
                )}
              </div>
            )}
          </div>
        )}
        {/* Admins only: the builder previews and re-imports straight from the
            source, and both are admin-only on the server (E01). */}
        {isAdmin && ds.data_source_id && ds.query_model && (
          <button onClick={openEditQuery} disabled={queryEditLoading} className="btn btn-ghost btn-sm">
            {queryEditLoading ? tr('common.loading') : tr('ds.editQuery')}
          </button>
        )}
        <button type="button" onClick={() => void buildDashboard()} disabled={building}
          className="btn btn-sm" title={tr('dataset.buildTitle')}>
          {building ? tr('dataset.building') : tr('dataset.build')}
        </button>
        <Link to={`/ask?dataset=${dsId}`} className="btn btn-ghost btn-sm"
          title={tr('dataset.askTitle')}>
          <IconLabel icon={Bot}>{tr('dataset.ask')}</IconLabel>
        </Link>
        {tab === 'overview' && (
          <button onClick={runAnalysis} disabled={running} className="btn btn-primary btn-sm">
            {running ? tr('dataset.running') : analysis ? tr('dataset.rerun') : tr('dataset.runAnalysis')}
          </button>
        )}
      </div>

      {/* Tab bar */}
      {/* Aggregates is offered only where it can do something: it is a
          DirectQuery feature, and on an import dataset the tab opened onto a
          paragraph explaining why it was empty. A bookmarked ?tab=aggregates
          still lands on that explanation. Scrolls sideways rather than
          wrapping on a phone. */}
      <div role="tablist" aria-label={tr('dataset.sections')} className="dl-tabs">
        {(['overview', 'data', 'meaning', 'statistics', 'alerts', 'checks', 'models', 'aggregates'] as Tab[])
          .filter(t => t !== 'aggregates' || ds?.mode === 'directquery' || tab === 'aggregates')
          // Checks run before a refreshed file is published: a live dataset has none.
          .filter(t => t !== 'checks' || ds?.mode !== 'directquery')
          .map(t => (
          <button key={t} type="button" role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
            className={`dl-tabs__tab${tab === t ? ' dl-tabs__tab--on' : ''}`}>
            {t === 'overview' ? <IconLabel icon={OverviewIcon}>{tr('dataset.tab.overview')}</IconLabel>
                      : t === 'data' ? <IconLabel icon={Table2}>{tr('dataset.tab.data')}</IconLabel>
                      : t === 'meaning' ? <IconLabel icon={BookOpen}>{tr('dataset.tab.meaning')}</IconLabel>
                      : t === 'statistics' ? <IconLabel icon={Ruler}>{tr('dataset.tab.analysis')}</IconLabel>
                      : t === 'alerts' ? <IconLabel icon={BellRing}>{tr('dataset.tab.alerts')}</IconLabel>
                      : t === 'checks' ? <IconLabel icon={ShieldCheck}>{tr('dataset.tab.checks')}</IconLabel>
                      // Named explicitly rather than falling off the end of the
                      // chain: the catch-all labelled every future tab "Alerts",
                      // and two tabs with one name is a tab bar that lies.
                      : t === 'models' ? <IconLabel icon={Brain}>{tr('dataset.tab.models')}</IconLabel>
                      : <IconLabel icon={Layers}>{tr('dataset.tab.aggregates')}</IconLabel>}
          </button>
        ))}
      </div>

      {/* ── Analysis tab ──
          Dataset-scoped and RLS-filtered against this dataset's frame, so this
          is where the analyses belong: the user is already looking at the
          columns they are about to name.

          Labelled "Analysis" but keyed `statistics`: the key is in the URL
          (`?tab=statistics`) and people have bookmarked it, so it stays. The
          LABEL had to change — the panel ran eight statistical tests when it
          was named, and now runs segmentation, association rules, key
          influencers, the SAS-style explanation and goal seek as well. A tab
          called Statistics is a tab nobody opens looking for those. */}
      {/* Meaning: what each column is FOR. Every AI path in this product now
          reads these -- the designer's prompt, the agent's context, the words
          the insights engine writes its findings in -- and until this tab there
          was nowhere in the product to write one for a dataset. A description on
          a column that came from a connected table is written to the SOURCE
          catalog, so it is written once and read by every dataset built from
          that table; the panel says so when that is what happened. */}
      {tab === 'meaning' && ds && (
        <ColumnMeaningPanel dataset={ds} canEdit onSaved={loadDataset} />
      )}

      {tab === 'statistics' && ds && (
        <StatisticsPanel mode={ds.mode} datasetId={ds.id} columns={ds.columns ?? []} />
      )}

      {/* ── Alerts tab ──
          The evaluator has run on every scheduler tick for months and nothing
          could create an alert, so the platform had none. This is the missing
          half. It lives beside the data rather than in Admin because an alert
          is a question about THIS dataset's columns, and it is checked as the
          person who made it — with their row-level security, not an admin's. */}
      {tab === 'alerts' && ds && (
        <AlertsPanel datasetId={ds.id} columns={ds.columns ?? []} />
      )}

      {/* Pipeline phase 3: what every refresh must pass before it is published. */}
      {tab === 'checks' && ds && (
        <ChecksPanel datasetId={ds.id} columns={(ds.columns ?? []).map(c => c.name)}
          canEdit={!!pipelineHealth?.can_edit} />
      )}

      {/* Saved models, beside the analyses they come from. Every other analysis
          here refits and discards; these are the ones kept so they can score
          rows whose outcome is not known yet. */}
      {tab === 'models' && ds && (
        <PredictionModelsPanel datasetId={ds.id} columns={ds.columns ?? []} mode={ds.mode}
          dataset={{ row_count: ds.row_count ?? null, content_sha256: (ds as { content_sha256?: string | null }).content_sha256 ?? null,
                     last_refreshed_at: (ds as { last_refreshed_at?: string | null }).last_refreshed_at ?? null }} />
      )}

      {/* Aggregates: a GROUP BY run at the source on a schedule, saved as a
          dataset dashboards can read in milliseconds. DirectQuery-only, since
          an import dataset's dashboards already read its file directly. */}
      {tab === 'aggregates' && ds && (
        <AggregatesPanel datasetId={ds.id} mode={ds.mode} />
      )}

      {/* ── Overview tab ── */}
      {tab === 'overview' && (
        <div>
          {ds.mode !== 'directquery' && <DataQualityPanel datasetId={dsId} />}
          {analysis?.sampled && (
            <div style={{ marginBottom: 12, fontSize: 12, color: 'var(--muted)', background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 6, padding: '6px 10px' }}>
              Based on a live sample of {analysis.sample_size?.toLocaleString()} of {analysis.total_rows?.toLocaleString()} rows.
            </div>
          )}
          {analysis && (
            // The same stat-card grammar as the Datasets page: label on top in
            // sentence case, the figure in the body face with tabular digits.
            // It was caps labels over teal monospace, which read as log output
            // and made "numeric: 4 · datetime: 1 · categorical: 2" wrap to
            // three ragged lines. Types are now the column-type badges used
            // everywhere else a type is shown.
            <div className="dl-stats" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))' }}>
              {[
                { label: tr('dataset.stat.rows'), value: analysis.overview?.rows?.toLocaleString() },
                { label: tr('dataset.stat.columns'), value: analysis.overview?.cols },
                { label: tr('dataset.stat.missing'), value: `${analysis.overview?.missing_pct}%` },
              ].map(card => (
                <div key={card.label} className="card dl-stat dl-stat--plain">
                  <div>
                    <div className="dl-stat__label">{card.label}</div>
                    <div className="dl-stat__figure">{card.value}</div>
                  </div>
                </div>
              ))}
              <div className="card dl-stat dl-stat--plain">
                <div>
                  <div className="dl-stat__label">{tr('dataset.stat.types')}</div>
                  <div className="dl-stat__badges">
                    {Object.entries(analysis.overview?.type_counts ?? {}).map(([k, v]) => (
                      <span key={k} className={`badge badge-${['numeric', 'datetime', 'categorical'].includes(k) ? k : 'text'}`}>
                        {k}: {String(v)}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}
          {!analysis && !loading && (
            <div style={{ padding: 40, textAlign: 'center', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', color: 'var(--muted)' }}>
              {tr('dataset.noAnalysis')}
            </div>
          )}
          {/* Live datasets too (HR evaluation, item 3.4): the scan reads up to
              250K rows from the source, and only when this button is pressed. */}
          {(
            <section id="insights" style={{ marginBottom: 24 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                <h2 style={{ fontSize: 15, fontWeight: 700 }}>{tr('dataset.insights')}</h2>
                <button className="btn btn-sm" disabled={insightsBusy}
                  onClick={() => {
                    setInsightsBusy(true)
                    insightsApi.run(ds.id).then(setInsights).finally(() => setInsightsBusy(false))
                  }}>
                  {insightsBusy ? tr('ov.scanning')
                    : insights ? <IconLabel icon={RefreshCw}>{tr('ov.rescan')}</IconLabel>
                    : <IconLabel icon={Sparkles}>{tr('ov.genInsights')}</IconLabel>}
                </button>
              </div>
              {insights && (
                <>
                  <p data-testid="insights-narrative" style={{ fontSize: 13, background: 'var(--surface)', border: '1px solid var(--border)',
                    borderRadius: 'var(--radius)', padding: '10px 14px', marginBottom: 10 }}>
                    {insights.narrative}
                  </p>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 10 }}>
                    {insights.findings.map((f, i) => (
                      <div key={i} data-testid={`insight-${f.kind}`}
                        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: 12 }}>
                        <div style={{ display: 'flex', gap: 6, alignItems: 'baseline', marginBottom: 4 }}>
                          <span style={{ fontSize: 10.5, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.06em',
                            color: f.kind === 'data_quality' ? '#e6a03c' : 'var(--accent)' }}>
                            {f.kind.replace('_', ' ')}
                          </span>
                          {(f.novelty === 'new' || f.novelty === 'changed') && (
                            <span style={{ background: 'var(--accent)', color: 'var(--surface)',
                              borderRadius: 3, padding: '0 4px', fontSize: 8, fontWeight: 700 }}>
                              {f.novelty === 'new' ? 'NEW' : 'CHANGED'}
                            </span>
                          )}
                          <button aria-label={`Pin finding: ${f.title}`}
                            title="Pin to your dashboard — re-evaluated live on every visit"
                            onClick={() => void pinsApi
                              .create({ dataset_id: ds.id,
                                        finding_key: findingKey(f) })
                              .then(r => toast.success(r.already_pinned
                                ? 'Already on your dashboard' : 'Pinned to your dashboard'))
                              .catch(() => toast.error('Could not pin this finding'))}
                            style={{ background: 'none', border: 'none', cursor: 'pointer',
                              fontSize: 11, padding: 0, marginInlineStart: 'auto' }}><Pin size={12} /></button>
                          <span style={{ fontSize: 10.5, color: 'var(--muted)', marginInlineStart: 'auto' }}>{Math.round(f.score * 100)}</span>
                        </div>
                        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 3 }}>{f.title}</div>
                        <div style={{ fontSize: 11, color: 'var(--muted)' }}>{f.detail}</div>
                        <FindingChart datasetId={ds.id} finding={f}
                          columnTypes={Object.fromEntries(ds.columns.map(c => [c.name, c.dtype ?? '']))} />
                      </div>
                    ))}
                  </div>
                </>
              )}
            </section>
          )}
          <section id="influencers" style={{ marginBottom: 24 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10, flexWrap: 'wrap' }}>
              <h2 style={{ fontSize: 15, fontWeight: 700 }}>{tr('ov.keyInfluencers')}</h2>
              <select value={influencerTarget} aria-label="Outcome to explain"
                onChange={e => { setInfluencerTarget(e.target.value); setInfluencers(null); setInfluencerNeedsPick(false) }}
                style={{ fontSize: 12 }}>
                <option value="">{tr('ki.chooseOutcome')}</option>
                {ds.columns.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
              </select>
              <button className="btn btn-sm" disabled={influencerBusy || !influencerTarget} title={!influencerTarget ? 'Choose the column to explain first' : undefined}
                onClick={() => runInfluencers(influencerTarget)}>
                {influencerBusy ? tr('ov.analysing')
                    : influencers ? <IconLabel icon={RefreshCw}>{tr('ov.rerun')}</IconLabel>
                    : <IconLabel icon={Sparkles}>{tr('ov.whatDrives')}</IconLabel>}
              </button>
            </div>
            {influencerNeedsPick && !influencerTarget && (
              <p data-testid="influencers-pick" style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 8 }}>
                {tr('ki.pickPrompt')}
              </p>
            )}
            {influencerError && (
              <p style={{ fontSize: 12, color: 'var(--danger)' }}>{influencerError}</p>
            )}
            {influencers && (
              <KeyInfluencersResultView result={influencers}
                leftOut={influencerSkipped.filter(c => c !== influencers.meta.target)} />
            )}
          </section>

          <section id="associations" style={{ marginBottom: 24 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
              <h2 style={{ fontSize: 15, fontWeight: 700 }}>{tr('ov.travelTogether')}</h2>
              <button className="btn btn-sm" disabled={rulesBusy} onClick={runPatterns}>
                {rulesBusy ? tr('ov.mining')
                    : rules ? <IconLabel icon={RefreshCw}>{tr('ov.rerun')}</IconLabel>
                    : <IconLabel icon={Sparkles}>{tr('ov.findPatterns')}</IconLabel>}
              </button>
            </div>
            {rulesError && (
              <p role="alert" style={{ fontSize: 12, color: 'var(--danger)' }}>{rulesError}</p>
            )}
            {rules && rules.rows.length === 0 && (
              <p style={{ fontSize: 12, color: 'var(--muted)' }}>
                {tr('ar.none')}
              </p>
            )}
            {rules && rules.rows.length > 0 && (
              <div style={{ background: 'var(--surface)', border: '1px solid var(--border)',
                borderRadius: 8, padding: 14, overflowX: 'auto' }}>
                <table>
                  <thead>
                    <tr>
                      <th>{tr('ki.when')}</th>
                      <th>{tr('ar.then')}</th>
                      {/* Lift first: it is the number that means something.
                          Confidence alone is unreadable without the base rate
                          beside it, which is why both are shown. */}
                      <th>{tr('ar.lift')}</th>
                      <th>{tr('ar.confidence')}</th>
                      <th>{tr('ar.baseRate')}</th>
                      <th>{tr('ki.rowsCol')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rules.rows.map((r, i) => (
                      <tr key={i}>
                        <td><strong>{r.if}</strong></td>
                        <td>{r.then}</td>
                        <td style={{ fontFamily: 'var(--mono)', color: 'var(--accent)' }}>
                          {r.lift.toFixed(2)}×
                        </td>
                        <td style={{ fontFamily: 'var(--mono)' }}>
                          {(r.confidence * 100).toFixed(0)}%
                        </td>
                        <td style={{ fontFamily: 'var(--mono)', color: 'var(--muted)' }}>
                          {(r.base_rate * 100).toFixed(0)}%
                        </td>
                        <td style={{ fontFamily: 'var(--mono)' }}>
                          {r.support_rows.toLocaleString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {rules.warnings.length > 0 && (
                  <ul style={{ fontSize: 11, color: 'var(--muted)', marginTop: 10, paddingInlineStart: 18 }}>
                    {rules.warnings.map((w, i) => <li key={i}>{w}</li>)}
                  </ul>
                )}
              </div>
            )}
          </section>

          {ds.mode !== 'directquery' && (
            <section id="segment" style={{ marginBottom: 24 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                <h2 style={{ fontSize: 15, fontWeight: 700 }}>{tr('ov.segment')}</h2>
                <button className="btn btn-sm" disabled={segmentBusy} onClick={runSegment}>
                  {segmentBusy ? tr('ov.clustering')
                    : segment ? <IconLabel icon={RefreshCw}>{tr('ov.rerunSegment')}</IconLabel>
                    : <IconLabel icon={Sparkles}>{tr('ov.segmentRows')}</IconLabel>}
                </button>
              </div>
              {segmentError && (
                <p style={{ fontSize: 12, color: 'var(--danger)' }}>{segmentError}</p>
              )}
              {segment && (
                <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: 14 }}>
                  <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 10 }}>
                    k = {segment.meta.params.k} clusters over {segment.meta.params.columns.join(', ')}
                    {' · '}silhouette {segment.meta.silhouette.toFixed(3)}
                    {' · '}{segment.meta.n_rows_used.toLocaleString()} rows clustered
                  </div>
                  <table>
                    <thead>
                      <tr>
                        <th>Cluster</th>
                        <th>Size</th>
                        {segment.meta.params.columns.map(c => <th key={c}>{c} (mean)</th>)}
                      </tr>
                    </thead>
                    <tbody>
                      {segment.meta.centroids.map((c: any) => (
                        <tr key={c.cluster}>
                          <td style={{ fontWeight: 600 }}>{c.cluster}</td>
                          <td style={{ fontFamily: 'var(--mono)' }}>{c.size}</td>
                          {segment.meta.params.columns.map(col => (
                            <td key={col} style={{ fontFamily: 'var(--mono)' }}>{Number(c[col]).toFixed(2)}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          )}

          {/* Anomalies -- the report builder's outlier-details dialog, opened
              from the data itself. The dialog owns the detector picker
              (IQR / Isolation Forest / ECOD); this section only chooses the
              column, because that is the one input the dialog does not own. */}
          {/* Import-only, like Insights and Segments: /outlier-details 400s on
              DirectQuery identically to /insights and /segment -- this guard
              was missing, so a DirectQuery user could pick a column and click
              straight into a guaranteed error the other two sections never expose. */}
          {ds.mode !== 'directquery' && ds.columns.some(c => c.dtype === 'numeric') && (
            <section id="anomalies" style={{ marginBottom: 24 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                <h2 style={{ fontSize: 15, fontWeight: 700 }}>{tr('ov.anomalies')}</h2>
                <select value={outlierColumn} aria-label="Column to inspect for outliers"
                  onChange={e => setOutlierColumn(e.target.value)} style={{ fontSize: 12 }}>
                  <option value="">choose a numeric column…</option>
                  {ds.columns.filter(c => c.dtype === 'numeric').map(c => (
                    <option key={c.name} value={c.name}>{c.name}</option>
                  ))}
                </select>
                <button className="btn btn-sm" disabled={!outlierColumn} title={!outlierColumn ? 'Choose a numeric column first' : undefined}
                  onClick={() => setOutlierOpen(true)}>
                  <IconLabel icon={TriangleAlert}>{tr('ov.inspectOutliers')}</IconLabel>
                </button>
              </div>
              <p style={{ fontSize: 12, color: 'var(--muted)' }}>
                Box-plot fences, the outlying rows themselves, and what they do to the total
                and the mean — on the same secured data widgets read.
              </p>
            </section>
          )}
          {numCols.length > 0 && (
            <section style={{ marginBottom: 24 }}>
              <h2 style={{ fontSize: 15, fontWeight: 700, marginBottom: 12 }}>
                {tr('ov.numericCols')} <span className="badge badge-numeric" style={{ marginInlineStart: 6 }}>{numCols.length}</span>
              </h2>
              <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', overflow: 'hidden' }}>
                <table>
                  <thead><tr><th>Column</th><th>Count</th><th>Mean</th><th>Std</th><th>Min</th><th>Median</th><th>Max</th><th>Missing%</th></tr></thead>
                  <tbody>
                    {numCols.map(([col, s]: [string, any]) => (
                      <tr key={col}>
                        <td style={{ fontWeight: 600 }}>{col}</td>
                        <td style={{ fontFamily: 'var(--mono)' }}>{s.count}</td>
                        <td style={{ fontFamily: 'var(--mono)' }}>{s.mean?.toFixed(2)}</td>
                        <td style={{ fontFamily: 'var(--mono)' }}>{s.std?.toFixed(2)}</td>
                        <td style={{ fontFamily: 'var(--mono)' }}>{s.min?.toFixed(2)}</td>
                        <td style={{ fontFamily: 'var(--mono)' }}>{s.median?.toFixed(2)}</td>
                        <td style={{ fontFamily: 'var(--mono)' }}>{s.max?.toFixed(2)}</td>
                        <td style={{ color: s.missing_pct > 10 ? 'var(--danger)' : 'var(--muted)', fontFamily: 'var(--mono)' }}>{s.missing_pct}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
          {dtCols.length > 0 && (
            <section style={{ marginBottom: 24 }}>
              <h2 style={{ fontSize: 15, fontWeight: 700, marginBottom: 12 }}>
                {tr('ov.dateCols')} <span className="badge badge-datetime" style={{ marginInlineStart: 6 }}>{dtCols.length}</span>
              </h2>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 12 }}>
                {dtCols.map(([col, s]: [string, any]) => (
                  <div key={col} data-testid={`dt-card-${col}`} style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: 14 }}>
                    <div style={{ fontWeight: 700, marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
                      {col}
                      {s.granularity && (
                        <span style={{ fontSize: 10.5, fontWeight: 400, color: 'var(--muted)', border: '1px solid var(--border)', borderRadius: 6, padding: '0 5px', textTransform: 'uppercase' }}>
                          {s.granularity}
                        </span>
                      )}
                    </div>
                    {s.note ? (
                      <div style={{ fontSize: 12, color: 'var(--muted)' }}>{s.note}</div>
                    ) : (
                      <>
                        <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 8 }}>
                          {String(s.min).slice(0, s.granularity === 'date' ? 10 : 16)} → {String(s.max).slice(0, s.granularity === 'date' ? 10 : 16)}
                          <span style={{ fontFamily: 'var(--mono)' }}> · {s.range_days}d span · {s.n_unique} unique</span>
                          {s.missing_pct > 0 && <span style={{ color: s.missing_pct > 10 ? 'var(--danger)' : undefined }}> · {s.missing_pct}% missing</span>}
                          {s.gaps_over_7d > 0 && <span> · {s.gaps_over_7d} gap{s.gaps_over_7d === 1 ? '' : 's'} &gt;7d</span>}
                        </div>
                        {s.monthly_counts && (() => {
                          const max = Math.max(...s.monthly_counts.map((m: any) => m.count), 1)
                          return (
                            <div style={{ marginBottom: 8 }}>
                              <div style={{ fontSize: 10.5, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 3 }}>
                                {tr('ov.byMonth')}{s.busiest_period ? ` — busiest ${s.busiest_period.period} (${s.busiest_period.count.toLocaleString()})` : ''}
                              </div>
                              <div style={{ display: 'flex', alignItems: 'flex-end', gap: 1, height: 28 }}>
                                {s.monthly_counts.map((m: any) => (
                                  <span key={m.period} title={`${m.period}: ${m.count.toLocaleString()}`}
                                    style={{ flex: 1, minWidth: 2, background: 'var(--accent)', opacity: 0.75,
                                      height: `${Math.max(8, (m.count / max) * 100)}%`, borderRadius: 1 }} />
                                ))}
                              </div>
                            </div>
                          )
                        })()}
                        {s.weekday_counts && (() => {
                          const max = Math.max(...s.weekday_counts.map((w: any) => w.count), 1)
                          return (
                            <div>
                              <div style={{ fontSize: 10.5, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 3 }}>{tr('ov.byWeekday')}</div>
                              <div style={{ display: 'flex', gap: 3 }}>
                                {s.weekday_counts.map((w: any) => (
                                  <div key={w.day} style={{ flex: 1, textAlign: 'center' }}>
                                    <div style={{ height: 22, display: 'flex', alignItems: 'flex-end' }}>
                                      <span title={`${w.day}: ${w.count.toLocaleString()}`}
                                        style={{ width: '100%', background: 'var(--accent)', opacity: 0.6,
                                          height: `${Math.max(4, (w.count / max) * 100)}%`, borderRadius: 1 }} />
                                    </div>
                                    <div style={{ fontSize: 8, color: 'var(--muted)' }}>{w.day[0]}</div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )
                        })()}
                      </>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}
          {catCols.length > 0 && (
            <section>
              <h2 style={{ fontSize: 15, fontWeight: 700, marginBottom: 12 }}>
                {tr('ov.catCols')} <span className="badge badge-categorical" style={{ marginInlineStart: 6 }}>{catCols.length}</span>
              </h2>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
                {catCols.map(([col, s]: [string, any]) => (
                  <div key={col} style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: 14 }}>
                    <div style={{ fontWeight: 700, marginBottom: 6 }}>{col} <span style={{ color: 'var(--muted)', fontSize: 12, fontWeight: 400 }}>({s.n_unique} unique)</span></div>
                    {(s.top_values ?? []).slice(0, 5).map((v: any) => (
                      <div key={v.value} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, padding: '2px 0', color: 'var(--muted)' }}>
                        <span style={{ color: 'var(--text)' }}>{v.value}</span>
                        <span style={{ fontFamily: 'var(--mono)' }}>{v.pct}%</span>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
      )}

      {/* ── Data tab ── */}
      {tab === 'data' && (
        <div className="dl-data-tab" style={{ display: 'flex', gap: 14, flex: 1, minHeight: 0 }}>

          {/* Left panel: Filters + CalcColumns */}
          <div className="dl-data-tab__panels" style={{ width: 260, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 14, overflowY: 'auto' }}>

            {/* Filters */}
            <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, padding: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em' }}>
                  Filters
                </span>
                <button className="btn btn-ghost btn-sm" onClick={addFilter} style={{ fontSize: 11, padding: '2px 7px' }}>
                  + Add
                </button>
              </div>

              {filterRows.length === 0 && (
                <p style={{ fontSize: 11, color: 'var(--muted)', textAlign: 'center', padding: '6px 0' }}>No filters</p>
              )}

              {filterRows.map(f => (
                <div key={f.id} style={{ marginBottom: 8, background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 6, padding: 7 }}>
                  <div style={{ display: 'flex', gap: 4, marginBottom: 4 }}>
                    <select value={f.column} onChange={e => updateFilter(f.id, 'column', e.target.value)}
                      style={{ flex: 1, fontSize: 11, padding: '3px 4px', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text)', minWidth: 0 }}>
                      {allColNames.map(c => <option key={c} value={c}>{c}</option>)}
                    </select>
                    <button onClick={() => removeFilter(f.id)}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--muted)', fontSize: 14, padding: '0 2px', flexShrink: 0 }}>×</button>
                  </div>
                  <div style={{ display: 'flex', gap: 4 }}>
                    <select value={f.op} onChange={e => updateFilter(f.id, 'op', e.target.value)}
                      style={{ width: 90, fontSize: 11, padding: '3px 4px', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text)' }}>
                      {OPS.map(op => <option key={op.value} value={op.value}>{op.label}</option>)}
                    </select>
                    <input value={f.value} onChange={e => updateFilter(f.id, 'value', e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && applyFilters()}
                      placeholder="value…"
                      style={{ flex: 1, fontSize: 11, padding: '3px 6px', minWidth: 0 }} />
                  </div>
                </div>
              ))}

              {filterRows.length > 0 && (
                <button className="btn btn-primary btn-sm" onClick={applyFilters}
                  style={{ width: '100%', fontSize: 11, marginTop: 4 }}>
                  Apply Filters
                </button>
              )}
            </div>

            {/* Global Filter */}
            <div style={{ background: 'var(--surface)', border: `1px solid ${savedFilter ? 'var(--accent)' : 'var(--border)'}`, borderRadius: 8, padding: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em' }}>
                  Global Filter
                </span>
                {savedFilter && (
                  <span style={{ fontSize: 11, color: 'var(--accent)', padding: '1px 6px', background: 'color-mix(in srgb, var(--accent) 15%, transparent)', borderRadius: 4 }}>
                    active
                  </span>
                )}
              </div>
              <p style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 8, lineHeight: 1.5 }}>
                Applied to all reports that use this dataset.
              </p>
              <ExpressionBuilder
                layout="flat"
                defaultMode="simple"
                columns={ds.columns}
                attributeExtras={calcCols.map(c => ({ name: c.name }))}
                functionsCatalog={FILTER_FUNC_CATS}
                value={filterExpr}
                onChange={next => { setFilterExpr(next); setFilterPreview(null) }}
                placeholder={"الفئة == 'ضابط' AND المرتب > 20000"}
                rows={3}
              />
              {filterPreview && (
                <div style={{ fontSize: 11, marginTop: 6, padding: '4px 8px', borderRadius: 4,
                  background: filterPreview.ok ? 'rgba(34,197,94,.1)' : 'rgba(239,68,68,.1)',
                  color: filterPreview.ok ? 'var(--success, #22c55e)' : 'var(--danger)' }}>
                  {filterPreview.ok
                    ? `✓ ${filterPreview.passing!.toLocaleString()} / ${filterPreview.total.toLocaleString()} rows pass`
                    : `✗ ${filterPreview.error}`}
                </div>
              )}
              <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
                <button className="btn btn-ghost btn-sm"
                  style={{ fontSize: 11, flex: 1 }}
                  onClick={testGlobalFilter}
                  disabled={!filterExpr.trim()} title={!filterExpr.trim() ? 'Write a filter expression first' : undefined}>
                  Test
                </button>
                <button className="btn btn-primary btn-sm"
                  style={{ fontSize: 11, flex: 1 }}
                  onClick={() => saveGlobalFilter()}
                  disabled={filterSaving}>
                  {filterSaving ? 'Saving…' : 'Save'}
                </button>
                {savedFilter && (
                  <button className="btn btn-ghost btn-sm"
                    style={{ fontSize: 11, color: 'var(--danger)', padding: '4px 8px' }}
                    onClick={() => { setFilterExpr(''); saveGlobalFilter('') }}>
                    ✕
                  </button>
                )}
              </div>
            </div>

            {/* Built from other datasets: a snapshot, so it needs to say when it
                was taken and offer the only thing that moves it forward. */}
            {derivedFrom && (
              <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, padding: 12,
                            display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                <span style={{ fontSize: 12 }}>
                  Built from {derivedSourceNames || 'other datasets'}
                  {derivedFrom.built_at && <> · {new Date(String(derivedFrom.built_at)).toLocaleString()}</>}
                </span>
                <button className="btn btn-ghost" style={{ fontSize: 12 }}
                  disabled={rebuilding}
                  onClick={async () => {
                    setRebuilding(true)
                    try {
                      const updated = await prepApi.rebuild(dsId)
                      setDs(updated)
                      toast.success('Rebuilt from the current source data')
                    } catch (e: any) {
                      // 409s name what broke (a deleted source, a vanished join
                      // key); showing the server's words is the whole point.
                      toast.error(e?.response?.data?.detail || 'Rebuild failed')
                    } finally {
                      setRebuilding(false)
                    }
                  }}>
                  {rebuilding ? 'Rebuilding…' : 'Rebuild'}
                </button>
                <span style={{ fontSize: 11, color: 'var(--muted)' }}>
                  This does not update on its own.
                </span>
              </div>
            )}

            {/* Transform pipeline (F2) — sort/filter/aggregate/etc, ordered, previewable */}
            {ds.mode !== 'directquery' && (
              <div id="prep-pipeline" style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, padding: 12 }}>
                <PrepPipelinePanel datasetId={dsId} columns={ds.columns} datasetName={ds.name} />
              </div>
            )}

            {/* Calculated columns */}
            <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, padding: 12 }}>
              <CalcColumnsPanel
                datasetId={dsId}
                columns={ds.columns}
                onChanged={handleCalcColsChanged}
              />
            </div>

            {/* Group & Bin — compiles to a calculated column, so it belongs beside them */}
            <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, padding: 12 }}>
              <CustomCategoryPanel
                datasetId={dsId}
                columns={ds.columns}
                onSaved={handleCalcColsChanged}
              />
            </div>

            {/* Measures — post-aggregation, so they sit below the row-level calc columns */}
            <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, padding: 12 }}>
              <MeasuresPanel
                datasetId={dsId}
                columns={ds.columns}
                onChanged={() => {}}
              />
            </div>
          </div>

          {/* Right panel: Data table */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
            {/* Search bar */}
            <div style={{ marginBottom: 8, flexShrink: 0 }}>
              <input
                value={search}
                onChange={e => handleSearch(e.target.value)}
                placeholder="Search all columns…"
                style={{ width: '100%', fontSize: 12, padding: '6px 10px',
                  background: 'var(--surface)', border: '1px solid var(--border)',
                  borderRadius: 6, color: 'var(--text)', boxSizing: 'border-box' }}
              />
            </div>

            {/* In-place editing. Import datasets only: prep steps do not run on
                DirectQuery, so a correction would save and never appear. */}
            {ds.mode !== 'directquery' && preview && preview.columns.length > 1 && (
              <div style={{ marginBottom: 8, flexShrink: 0, display: 'flex',
                alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <button className={editCells ? 'btn btn-sm' : 'btn btn-ghost btn-sm'}
                  style={{ fontSize: 11 }}
                  onClick={() => {
                    const on = !editCells
                    setEditCells(on)
                    setEditingAt(null)
                    if (on) {
                      if (!keyColumn) setKeyColumn(preview.columns[0])
                      prepApi.get(dsId).then(setPrepSteps).catch(() => setPrepSteps([]))
                    }
                  }}>
                  {editCells ? '✓ Editing cells' : '✎ Edit cells'}
                </button>
                {editCells && (
                  <>
                    <label htmlFor="cell-edit-key" style={{ fontSize: 11, color: 'var(--muted)' }}>
                      Rows identified by
                    </label>
                    <select id="cell-edit-key" value={keyColumn || preview.columns[0]}
                      onChange={e => { setKeyColumn(e.target.value); setEditingAt(null) }}
                      style={{ fontSize: 11, padding: '3px 6px', background: 'var(--surface)',
                        border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text)' }}>
                      {preview.columns.map(c => <option key={c} value={c}>{c}</option>)}
                    </select>
                    <span style={{ fontSize: 11, color: 'var(--muted)' }}>
                      Corrections are saved as a prep step — the uploaded file is
                      never changed, and removing the step restores the original.
                      Every row sharing the key value is corrected.
                    </span>
                  </>
                )}
              </div>
            )}

            {pvLoading && (
              <div style={{ textAlign: 'center', padding: 40 }}><LoadingState label="Loading data…" /></div>
            )}
            {!pvLoading && preview && preview.rows.length === 0 && (
              <EmptyState icon={Search} title="No rows match"
                description="Try adjusting or clearing the filters and search above." />
            )}
            {!pvLoading && preview && preview.rows.length > 0 && (
              <>
                {ds.mode === 'directquery' && (
                  <div style={{ marginBottom: 8, fontSize: 12, color: 'var(--muted)', background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 6, padding: '6px 10px', flexShrink: 0 }}>
                    Showing the first {PAGE_SIZE} rows live from the source. Filtering, sorting, search, and calculated columns aren't supported yet for DirectQuery previews.
                  </div>
                )}
                <div style={{ flex: 1, overflow: 'auto', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8 }}>
                  <table style={{ fontSize: 12 }}>
                    <thead>
                      <tr>
                        {preview.columns.map(c => {
                          const isSorted = sortBy === c
                          return (
                            <th key={c} style={{ whiteSpace: 'nowrap', userSelect: 'none' }}
                              // aria-sort tells a screen reader the current
                              // order; the arrow glyph alone conveys it only to
                              // people who can see it.
                              aria-sort={isSorted ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>
                              <button type="button" onClick={() => handleSort(c)}
                                // A real button, so the header is reachable by
                                // Tab and operable by Enter/Space -- a th with
                                // onClick is neither.
                                style={{ background: 'none', border: 'none', padding: 0, font: 'inherit',
                                  color: 'inherit', cursor: 'pointer', display: 'inline-flex', alignItems: 'center' }}>
                              {calcColNames.has(c) && <span style={{ color: 'var(--accent)', marginInlineEnd: 4, fontSize: 11 }}>ƒx</span>}
                              {c}
                              <span aria-hidden="true" style={{ marginInlineStart: 4, color: isSorted ? 'var(--accent)' : 'var(--border)', fontSize: 11 }}>
                                {isSorted ? (sortDir === 'asc' ? '↑' : '↓') : '↕'}
                              </span>
                              </button>
                            </th>
                          )
                        })}
                      </tr>
                    </thead>
                    <tbody>
                      {preview.rows.map((row, i) => {
                        const activeKey = keyColumn || preview.columns[0]
                        const keyAt = preview.columns.indexOf(activeKey)
                        const rowKey = String((row as unknown[])[keyAt] ?? '')
                        return (
                        <tr key={i}>
                          {(row as unknown[]).map((v, j) => {
                            const column = preview.columns[j]
                            // Never the key column: it is how the edit finds its
                            // row, and the backend refuses that step outright.
                            const canEdit = editCells && column !== activeKey && rowKey !== ''
                            const isEditing = editingAt?.row === i && editingAt?.column === column
                            return (
                            <td key={j} style={{ fontFamily: typeof v === 'number' ? 'var(--mono)' : undefined,
                              cursor: canEdit && !isEditing ? 'text' : undefined,
                              background: canEdit && !isEditing
                                ? 'color-mix(in srgb, var(--accent) 5%, transparent)' : undefined }}
                              onClick={canEdit && !isEditing
                                ? () => setEditingAt({ row: i, column }) : undefined}>
                              {isEditing ? (
                                <input autoFocus defaultValue={v == null ? '' : String(v)}
                                  aria-label={`Edit ${column} for ${rowKey}`}
                                  onBlur={e => { setEditingAt(null); saveCellEdit(i, column, e.target.value) }}
                                  onKeyDown={e => {
                                    if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
                                    // Escape abandons the edit: blur would save it.
                                    if (e.key === 'Escape') setEditingAt(null)
                                  }}
                                  style={{ font: 'inherit', width: '100%', boxSizing: 'border-box',
                                    padding: '1px 3px', background: 'var(--surface2)',
                                    border: '1px solid var(--accent)', borderRadius: 3,
                                    color: 'var(--text)' }} />
                              ) : v == null ? <span style={{ color: 'var(--muted)' }}>—</span> : String(v)}
                            </td>
                            )
                          })}
                        </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>

                {/* Pagination */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 0', flexShrink: 0 }}>
                  <span style={{ fontSize: 11, color: 'var(--muted)' }}>
                    Rows {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, preview.total)} of {preview.total.toLocaleString()}
                  </span>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button className="btn btn-ghost btn-sm" style={{ fontSize: 11 }}
                      disabled={page === 0}
                      onClick={() => { const p = page - 1; setPage(p); loadPreview(p, filterRows, calcCols, sortBy, sortDir, search) }}>
                      {arrows.back} Prev
                    </button>
                    <button className="btn btn-ghost btn-sm" style={{ fontSize: 11 }}
                      disabled={(page + 1) * PAGE_SIZE >= preview.total}
                      onClick={() => { const p = page + 1; setPage(p); loadPreview(p, filterRows, calcCols, sortBy, sortDir, search) }}>
                      Next {arrows.forward}
                    </button>
                  </div>
                </div>
              </>
            )}
            {!pvLoading && pvError && (
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 12, padding: 40 }}>
                <FolderOpen size={32} color="var(--muted)" aria-hidden />
                <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>Dataset file not found</div>
                <div style={{ fontSize: 12, color: 'var(--muted)', textAlign: 'center', maxWidth: 360 }}>{pvError}</div>
                {ds?.data_source_id && (ds?.source_table || ds?.source_query) ? (
                  <button className="btn btn-primary btn-sm" onClick={() => handleRefresh('full')} disabled={refreshing}
                    style={{ marginTop: 8 }}>
                    {refreshing ? refreshStage : '↻ Refresh from source'}
                  </button>
                ) : ds?.data_source_id ? (
                  <div style={{ fontSize: 12, color: 'var(--muted)', textAlign: 'center', maxWidth: 320 }}>
                    Original query not recorded.{' '}
                    <Link to={`/connections/${ds.data_source_id}/review`} style={{ color: 'var(--accent)' }}>Re-import from this connection</Link>{' '}
                    to restore this dataset.
                  </div>
                ) : (
                  <div style={{ fontSize: 11, color: 'var(--muted)' }}>Re-upload the file to restore this dataset.</div>
                )}
              </div>
            )}
            {!pvLoading && !preview && !pvError && (
              <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 13 }}>
                Loading data…
              </div>
            )}
          </div>
        </div>
      )}
      {showShareDialog && (
        <DatasetShareDialog datasetId={dsId} onClose={() => setShowShareDialog(false)} />
      )}
      {outlierOpen && outlierColumn && (
        <OutlierDetailsDialog datasetId={dsId} column={outlierColumn}
          onClose={() => setOutlierOpen(false)} />
      )}
      {editingQuerySource && ds.query_model && (
        <QueryBuilderDialog
          ds={editingQuerySource}
          existing={{ id: ds.id, name: ds.name, query_model: ds.query_model }}
          onClose={() => setEditingQuerySource(null)}
          onCreated={() => {
            datasetsApi.get(dsId).then(updated => {
              setDs(updated)
              setCalcCols(updated.calculated_columns ?? [])
              loadPreview(0, filterRows, updated.calculated_columns ?? [], sortBy, sortDir, search)
            })
          }}
        />
      )}
    </div>
  )
}
