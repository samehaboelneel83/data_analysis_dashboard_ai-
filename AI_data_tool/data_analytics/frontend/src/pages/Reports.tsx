import { useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import {
  ArrowDownUp, ArrowRight, ChevronDown, Database, Download, Folder, FolderInput, FolderOpen, FolderPlus, LayoutDashboard,
  LayoutGrid, LayoutTemplate, Link2, List, Pencil, Plus, Search, SearchX, Share2, Sparkles, SquareDashedBottom, Trash2, X,
  Globe, GlobeLock, Users, Clock,
} from 'lucide-react'
import toast from 'react-hot-toast'
import LoadError from '../components/ui/LoadError'
import Loader from '../components/ui/Loader'
import ActionMenu, { type ActionMenuItem } from '../components/ActionMenu'
import { useBulkSelection } from '../lib/useBulkSelection'
import { looksLikeTestData } from '../lib/testData'
import { pageTemplatesApi, reportsApi, datasetsApi, workspaceApi } from '../services/api'
import type { ReportSummary, DatasetSummary } from '../services/api'
import type { WorkspaceTree } from '../types/report'
import { useConfirm } from '../components/ui/ConfirmDialog'
import { usePrompt } from '../components/ui/PromptDialog'
import { useListFilter } from '../components/ui/ListFilter'
import { AuthContext } from '../contexts/AuthContext'
import { formatTimeAgo, useT } from '../i18n'
import { localDigits } from '../lib/arabicFormats'
import SuggestDashboardsDialog from '../components/dataset/SuggestDashboardsDialog'
import ShareDashboardDialog from '../components/report/share/ShareDashboardDialog'
import { loadCollapsed, saveCollapsed, sectionsFor, reportNodes, type FolderSection } from './reports/listParts'
import { flatFolders, folderOf, reportsUnder, sharedWithMe, statusOf, type FlatFolder } from './reports/model'
import FolderNav, { type View } from './reports/FolderNav'
import { DashCard, DashRow } from './reports/DashCard'
import { MoveDialog, NewDashboardDialog, type NewChoice, type NewMode } from './reports/dialogs'
import Thumb from './home/Thumb'
import { nextUntitledName } from '../lib/untitledName'
import './home/home.css'
import './reports/dashboards.css'
export { nextUntitledName }

/**
 * The Dashboards page (redesign 7b): views and folders on the left, then the
 * dashboards -- grouped by folder, or narrowed by a view, a search, a status
 * or a dataset -- as cards or a table, with bulk actions.
 *
 * Placement, folder management and "Shared with me" come from the workspace
 * tree; the tree failing fails only them. What the design shows but the
 * backend cannot answer is left out, not stubbed: favourites, owner names,
 * view counts, Duplicate, stored AI proposals, a "Shared" status
 * (PLAN.md, Backend follow-ups). Kept from v1: subfolders, folder rename and
 * delete, the move confirmation, Publish / Unpublish, delete confirmation,
 * the dataset chip rule and Suggest dashboards' goal text.
 */

const SORT_KEY = 'datalytics:dashboards-sort'
const LAYOUT_KEY = 'datalytics:dashboards-layout'
const read = (k: string, ok: string[], d: string) => { try { const v = localStorage.getItem(k); return v && ok.includes(v) ? v : d } catch { return d } }
const save = (k: string, v: string) => { try { localStorage.setItem(k, v) } catch { /* a convenience */ } }
const detail = (e: unknown, fallback: string) => {
  const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof d === 'string' ? d : (d as { message?: string })?.message ?? fallback
}

export default function Reports() {
  const t = useT()
  const navigate = useNavigate()
  const confirm = useConfirm()
  const prompt = usePrompt()
  const isAdmin = !!useContext(AuthContext)?.user?.role?.is_org_admin

  const [reports, setReports] = useState<ReportSummary[]>([])
  const [datasets, setDatasets] = useState<DatasetSummary[] | null>(null)
  const [tree, setTree] = useState<WorkspaceTree | null>(null)
  const [treeFailed, setTreeFailed] = useState(false)
  const [recentIds, setRecentIds] = useState<number[] | null>(null)
  const [loading, setLoading] = useState(true)
  // Three states, not two: a failed load must never read as "no dashboards".
  const [loadError, setLoadError] = useState<unknown>(null)

  const dsName = (r: ReportSummary) => datasets?.find(d => d.id === r.dataset_id)?.name
  const repFilter = useListFilter(reports, r => [r.name, r.description, dsName(r)], t('dsh.search'))

  const [view, setView] = useState<View>('all')
  const [status, setStatus] = useState<'all' | 'draft' | 'pub'>('all')
  const [dsFilter, setDsFilter] = useState<number | null>(null)
  const [sort, setSortState] = useState(() => read(SORT_KEY, ['recent', 'name'], 'recent') as 'recent' | 'name')
  const [layout, setLayoutState] = useState(() => read(LAYOUT_KEY, ['grid', 'list'], 'grid') as 'grid' | 'list')
  const setSort = (v: 'recent' | 'name') => { setSortState(v); save(SORT_KEY, v) }
  const setLayout = (v: 'grid' | 'list') => { setLayoutState(v); save(LAYOUT_KEY, v) }
  const [collapsed, setCollapsed] = useState<Set<string>>(loadCollapsed)
  const toggleFold = (key: string) => setCollapsed(prev => {
    const next = new Set(prev)
    if (next.has(key)) next.delete(key); else next.add(key)
    saveCollapsed(next)
    return next
  })

  // Placement and recents are courtesies on top of the list, so each fails on
  // its own. Async wrappers: under a partial module mock, reading the api
  // object can throw synchronously, which a .catch() would not see.
  const loadTree = async () => { try { const tr = await workspaceApi.tree(); setTree(tr); setTreeFailed(false) } catch { setTree(null); setTreeFailed(true) } }
  const loadRecent = async () => { try { setRecentIds((await reportsApi.recent(50)).map(r => r.id)) } catch { setRecentIds(null) } }
  const loadDatasets = async () => { try { setDatasets(await datasetsApi.list()) } catch { setDatasets(null) } }

  const load = useCallback(() => {
    setLoading(true); setLoadError(null)
    reportsApi.list()
      .then(r => { setReports(r); void loadTree(); void loadRecent(); void loadDatasets() })
      .catch(e => setLoadError(e ?? new Error('failed')))
      .finally(() => setLoading(false))
  }, [])
  useEffect(load, [load])

  // ── opening ──
  // Router 7 navigates inside a transition, so the route loader never shows
  // while the builder loads; the list shows it itself.
  const [opening, setOpening] = useState(false)
  const openReport = (to: string) => { setOpening(true); navigate(to) }

  // ── creating ──
  const [newDlg, setNewDlg] = useState<{ mode: NewMode; folder: number | null } | null>(null)
  const [creating, setCreating] = useState(false)
  const [suggest, setSuggest] = useState<{ id: number; name: string; goal: string } | null>(null)
  const openNew = (mode: NewMode = 'blank', folder: number | null = view.startsWith('f:') ? Number(view.slice(2)) : null) =>
    setNewDlg({ mode, folder })
  // "Create a dashboard" from the command palette or Home lands here as ?new=1.
  const [params, setParams] = useSearchParams()
  const wantsNew = params.get('new') === '1'
  useEffect(() => {
    if (!wantsNew || loading) return
    setParams(p => { p.delete('new'); return p }, { replace: true })
    openNew('blank', null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wantsNew, loading])

  const fileInto = async (reportId: number, folderId: number | null) => {
    if (folderId == null) return
    try { await workspaceApi.create({ node_type: 'report', report_id: reportId, parent_id: folderId }) }
    catch (e) { toast.error(detail(e, t('dsh.toast.fileFailed'))) }
  }
  const create = async (c: NewChoice) => {
    if (c.mode === 'ai') {
      const ds = datasets?.find(d => d.id === c.datasetId)
      if (ds) { setNewDlg(null); setSuggest({ id: ds.id, name: ds.name, goal: c.goal }) }
      return
    }
    setCreating(true)
    try {
      const name = c.name || nextUntitledName(reports.map(x => x.name), t('dsh.untitled'))
      const r = await reportsApi.create({ name, ...(c.datasetId != null ? { dataset_id: c.datasetId } : {}) })
      if (c.mode === 'tpl' && c.template) {
        // A template adds its page; the empty default page goes, so the new
        // dashboard opens on the template rather than on a blank first page.
        await pageTemplatesApi.addFrom(r.id, { builtin: c.template })
        const first = r.pages?.[0]?.id
        if (first != null) await reportsApi.deletePage(r.id, first).catch(() => {})
      }
      await fileInto(r.id, c.folderId)
      // Blank with no data: marked fresh for this tab, so the builder removes
      // it again if the author leaves without adding anything (v1), and the
      // builder asks for data first.
      if (c.mode === 'blank' && c.datasetId == null) {
        try { sessionStorage.setItem('datalytics:fresh-report', String(r.id)) } catch { /* private mode */ }
        openReport(`/reports/${r.id}?pick=data`)
      } else openReport(`/reports/${r.id}`)
    } catch (e) {
      toast.error(detail(e, t('dsh.toast.createFailed')))
      setCreating(false)
    }
  }

  // ── folders ──
  const [newFolder, setNewFolder] = useState(false)
  const createFolder = async (name: string, parentId: number | null = null) => {
    try {
      await workspaceApi.create({ node_type: 'folder', name, ...(parentId === null ? {} : { parent_id: parentId }) })
      setNewFolder(false)
      await loadTree()
      toast.success(t('dsh.toast.folderCreated', { name }))
    } catch (e) { toast.error(detail(e, t('dsh.toast.folderFailed'))) }
  }
  const subfolder = async (f: FlatFolder) => {
    const name = (await prompt({ title: t('folders.new'), label: t('dsh.folderName'), confirmLabel: t('dsh.createFolder') }))?.trim()
    if (name) await createFolder(name, f.id)
  }
  const renameFolder = async (f: FlatFolder) => {
    const name = (await prompt({ title: t('folders.rename'), defaultValue: f.name, confirmLabel: t('dsh.rename') }))?.trim()
    if (!name || name === f.name) return
    try { await workspaceApi.update(f.id, { name }); await loadTree() } catch (e) { toast.error(detail(e, t('dsh.toast.folderFailed'))) }
  }
  const removeFolder = async (f: FlatFolder) => {
    // Says what actually happens: a folder's contents move up a level.
    if (!await confirm({ title: t('dsh.folderDeleteTitle', { name: f.name }), body: t('dsh.folderDeleteBody'), confirmLabel: t('folders.delete') })) return
    try {
      await workspaceApi.delete(f.id)
      if (view === `f:${f.id}`) setView('all')
      await loadTree()
    } catch (e) { toast.error(detail(e, t('dsh.toast.folderFailed'))) }
  }

  // ── moving ──
  const nodes = reportNodes(tree)
  const [dragging, setDragging] = useState<ReportSummary | null>(null)
  const [overTarget, setOverTarget] = useState<string | null>(null)
  const [moving, setMoving] = useState<ReportSummary[] | null>(null)
  const endDrag = () => { setDragging(null); setOverTarget(null) }

  /** One move, already confirmed. Throws the server's refusal. */
  const moveOne = async (r: ReportSummary, parentId: number | null) => {
    const node = nodes.get(r.id)
    if ((node?.parent_id ?? null) === parentId) return false
    if (node && node.id > 0) await workspaceApi.update(node.id, { parent_id: parentId })
    else await workspaceApi.create({ node_type: 'report', report_id: r.id, parent_id: parentId })
    return true
  }
  const moveMany = async (rs: ReportSummary[], parentId: number | null, targetName: string | null) => {
    let moved = 0
    try {
      for (const r of rs) if (await moveOne(r, parentId)) moved++
      if (moved) toast.success(rs.length === 1
        ? t('dsh.toast.moved', { name: rs[0].name, to: targetName ?? t('dsh.notInFolder') })
        : t('dsh.toast.movedMany', { n: localDigits(String(moved)), to: targetName ?? t('dsh.notInFolder') }))
    } catch (e) {
      // The server's answer is the answer: a folder this viewer cannot manage,
      // the cycle guard. Shown as given, never pre-empted.
      toast.error(detail(e, t('dsh.toast.moveRefused')))
    } finally { await loadTree() }
  }
  const dropOn = async (r: ReportSummary, parentId: number | null, targetName: string | null) => {
    if ((nodes.get(r.id)?.parent_id ?? null) === parentId) { endDrag(); return }
    // A drop is the easiest gesture to make by accident, and a move can widen
    // who sees the dashboard, so it is confirmed and the confirmation says so.
    const ok = await confirm({
      title: t('dsh.move.confirmTitle', { name: r.name, to: targetName ?? t('dsh.notInFolder') }),
      body: t('dsh.move.note'), confirmLabel: t('dsh.move.go'), destructive: false,
    })
    endDrag()
    if (ok) await moveMany([r], parentId, targetName)
  }
  const dropFor = (key: string, parentId: number | null, name: string | null) => ({
    onDragOver: (e: React.DragEvent) => { if (!dragging) return; e.preventDefault(); setOverTarget(key) },
    onDragLeave: () => setOverTarget(prev => (prev === key ? null : prev)),
    onDrop: (e: React.DragEvent) => { e.preventDefault(); e.stopPropagation(); if (dragging) void dropOn(dragging, parentId, name) },
  })

  // ── per-dashboard actions ──
  const [sharing, setSharing] = useState<ReportSummary | null>(null)
  const canEdit = (r: ReportSummary) => (r.my_capability ?? 'view') !== 'view'
  // Publish and Share are the author's controls (admins too), on authored
  // dashboards only: a legacy row would be a button the server 400s.
  const canAdminister = (r: ReportSummary) => r.created_by != null && (!!r.is_mine || isAdmin)

  const rename = async (r: ReportSummary) => {
    const name = (await prompt({ title: t('dsh.renameTitle'), defaultValue: r.name, confirmLabel: t('dsh.rename') }))?.trim()
    if (!name || name === r.name) return
    try {
      await reportsApi.update(r.id, { name })
      setReports(prev => prev.map(x => x.id === r.id ? { ...x, name } : x))
      toast.success(t('dsh.toast.renamed'))
    } catch (e) { toast.error(detail(e, t('dsh.toast.renameFailed'))) }
  }
  const remove = async (r: ReportSummary) => {
    if (!await confirm({ title: t('dsh.deleteTitle', { name: r.name }), body: t('dsh.deleteBody'), confirmLabel: t('dsh.delete') })) return
    try {
      await reportsApi.delete(r.id)
      setReports(prev => prev.filter(x => x.id !== r.id))
      // Placement is the server's: read the tree again so folder counts and
      // empty folders are its answer, not a guess (QA B7).
      void loadTree()
      toast.success(t('dsh.toast.deleted'))
    } catch (e) { toast.error(detail(e, t('dsh.toast.deleteFailed'))) }
  }
  const publish = async (r: ReportSummary) => {
    const next = !r.published
    try {
      await reportsApi.setPublished(r.id, next)
      setReports(prev => prev.map(x => x.id === r.id ? { ...x, published: next } : x))
      toast.success(t(next ? 'dsh.toast.published' : 'dsh.toast.unpublished'))
    } catch (e) {
      // The publish gate answers with {message, findings}.
      toast.error(detail(e, t('dsh.toast.publishFailed')))
    }
  }
  const copyLink = async (r: ReportSummary) => {
    try { await navigator.clipboard.writeText(`${window.location.origin}/reports/${r.id}`); toast.success(t('dsh.toast.copied')) }
    catch { toast.error(t('dsh.toast.copyFailed')) }
  }
  const exportPdf = (r: ReportSummary) => reportsApi.downloadPdf(r.id, r.name)
    .then(() => toast.success(t('dsh.toast.pdf', { name: r.name })))
    .catch(e => toast.error(detail(e, t('dsh.toast.pdfFailed'))))

  const menu = (r: ReportSummary): ActionMenuItem[] => {
    const edit = canEdit(r)
    return [
      { key: 'open', label: t('dsh.open'), icon: <ArrowRight size={14} />, onSelect: () => openReport(`/reports/${r.id}`) },
      ...(canAdminister(r) ? [{ key: 'share', label: t('dsh.shareDots'), icon: <Share2 size={14} />, onSelect: () => setSharing(r) }] : []),
      { key: 'link', label: t('dsh.copyLink'), icon: <Link2 size={14} />, onSelect: () => void copyLink(r) },
      ...(edit && tree ? [{ key: 'move', label: t('dsh.moveDots'), icon: <FolderInput size={14} />, onSelect: () => setMoving([r]) }] : []),
      ...(edit ? [{ key: 'rename', label: t('dsh.rename'), icon: <Pencil size={14} />, onSelect: () => void rename(r) }] : []),
      ...(canAdminister(r) ? [{ key: 'publish', label: t(r.published ? 'dsh.unpublish' : 'dsh.publish'),
        icon: r.published ? <GlobeLock size={14} /> : <Globe size={14} />, onSelect: () => void publish(r) }] : []),
      { key: 'pdf', label: t('dsh.exportPdf'), icon: <Download size={14} />, onSelect: () => void exportPdf(r) },
      ...(edit ? [{ key: 'delete', label: t('dsh.delete'), icon: <Trash2 size={14} />, danger: true, onSelect: () => void remove(r) }] : []),
    ]
  }

  // ── selection ──
  const bulk = useBulkSelection<ReportSummary>({
    remove: id => reportsApi.delete(id),
    onRemoved: ids => { setReports(r => r.filter(x => !ids.includes(x.id))); void loadTree() },
    noun: t('noun.dashboards'),
  })
  const selected = reports.filter(r => bulk.selected.has(r.id))
  const testLike = reports.filter(r => canEdit(r) && looksLikeTestData(r.name))
  const bulkExport = async () => {
    for (const r of selected) {
      try { await reportsApi.downloadPdf(r.id, r.name) } catch (e) { toast.error(detail(e, t('dsh.toast.pdfFailed'))); return }
    }
    toast.success(t('dsh.toast.pdfMany', { n: localDigits(String(selected.length)) }))
  }

  // ── what is shown ──
  const known = useMemo(() => new Set(reports.map(r => r.id)), [reports])
  const folders = useMemo(() => flatFolders(tree, known), [tree, known])
  const shared = useMemo(() => sharedWithMe(tree), [tree])
  const placedIn = useMemo(() => folderOf(tree), [tree])
  const folderName = (id: number | null | undefined) => id == null ? null : folders.find(f => f.id === id)?.name ?? null
  const recentSet = useMemo(() => recentIds ? new Set(recentIds) : null, [recentIds])
  const counts = {
    all: reports.length,
    recent: recentIds ? recentIds.filter(id => known.has(id)).length : null,
    shared: tree ? reports.filter(r => shared.has(r.id)).length : null,
  }
  const statusCount = (s: 'all' | 'draft' | 'pub') => reports.filter(r => s === 'all' || statusOf(r) === s).length
  const usedDatasets = (datasets ?? []).filter(d => reports.some(r => r.dataset_id === d.id))

  // Leaving a view that no longer exists (a deleted folder, a failed tree).
  useEffect(() => {
    if (view.startsWith('f:') && tree && !folders.some(f => `f:${f.id}` === view)) setView('all')
  }, [view, tree, folders])

  const narrowed = repFilter.query.trim() !== '' || status !== 'all' || dsFilter != null
  const clearFilters = () => { repFilter.setQuery(''); setStatus('all'); setDsFilter(null) }

  /** The filtered rows, narrowed by the view and the facets, then sorted.
   *  Takes the search hook's rows whole (listFilterWiring.test pins that). */
  const arrange = (rows: ReportSummary[], v: View) => {
    let xs = rows
    if (v === 'recent') xs = xs.filter(r => recentSet?.has(r.id))
    else if (v === 'shared') xs = xs.filter(r => shared.has(r.id))
    else if (v.startsWith('f:')) { const under = reportsUnder(tree, Number(v.slice(2))); xs = xs.filter(r => under.has(r.id)) }
    if (status !== 'all') xs = xs.filter(r => statusOf(r) === status)
    if (dsFilter != null) xs = xs.filter(r => r.dataset_id === dsFilter)
    const byRecent = v === 'recent' && recentIds
      ? (a: ReportSummary, b: ReportSummary) => recentIds.indexOf(a.id) - recentIds.indexOf(b.id)
      : (a: ReportSummary, b: ReportSummary) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
    return [...xs].sort(sort === 'name' ? (a, b) => a.name.localeCompare(b.name) : byRecent)
  }
  const shown = arrange(repFilter.filtered, view)
  const selectMode = bulk.selected.size > 0

  // ── rendering ──
  const props = (r: ReportSummary) => ({
    r, datasetName: dsName(r), folderName: folderName(placedIn.get(r.id)),
    canEdit: canEdit(r), canShare: canAdminister(r), selected: bulk.selected.has(r.id), selectMode,
    draggable: canEdit(r) && !!tree, dragging: dragging?.id === r.id, menu: menu(r),
    onToggle: () => bulk.toggle(r.id), onShare: () => setSharing(r), onOpen: () => setOpening(true),
    onDragStart: () => setDragging(r), onDragEnd: endDrag,
  })
  /** The heading above an ungrouped grid: how many, and the level-2 heading
   *  the cards' names sit under. */
  const countLine = (n: number, results = false) =>
    <h2 className="dsh-count">{t(results ? (n === 1 ? 'dsh.oneResult' : 'dsh.results') : (n === 1 ? 'dsh.oneDashboard' : 'dsh.nDashboards'), { n: localDigits(String(n)) })}</h2>
  const grid = (rs: ReportSummary[]) => <div className="dsh-grid">{rs.map(r => <DashCard key={r.id} {...props(r)} />)}</div>

  const sectionHead = (key: string, icon: React.ReactNode, name: string, count: number, drop?: { id: number | null; name: string | null },
    actions?: React.ReactNode, depth = 0) => {
    const H = depth ? 'h3' : 'h2'
    return (
    <div className="dsh-sh" data-drop={overTarget === `sec:${key}` || undefined} {...(drop ? dropFor(`sec:${key}`, drop.id, drop.name) : {})}>
      <H className="dsh-shh">
        <button type="button" className="fold" aria-expanded={!collapsed.has(key)} onClick={() => toggleFold(key)}>
          <ChevronDown size={16} className="chev" aria-hidden />{icon}<span className="name"><bdi>{name}</bdi></span>
        </button>
      </H>
      <span className="cnt" aria-label={t('dsh.countAria', { n: count })}>{localDigits(String(count))}</span>
      <span className="dsh-sp" />
      {actions}
    </div>
    )
  }
  const folderActions = (f: FolderSection) => f.can_manage && (
    <span className="dsh-shmenu">
      <ActionMenu label={t('folders.actions', { name: f.name })} portal align="end" triggerClassName="dsh-ib" items={[
        { key: 'sub', label: t('folders.new'), icon: <FolderPlus size={14} />, onSelect: () => void subfolder({ id: f.id, name: f.name } as FlatFolder) },
        { key: 'rename', label: t('folders.rename'), icon: <Pencil size={14} />, onSelect: () => void renameFolder({ id: f.id, name: f.name } as FlatFolder) },
        { key: 'delete', label: t('folders.delete'), icon: <Trash2 size={14} />, danger: true, onSelect: () => void removeFolder({ id: f.id, name: f.name } as FlatFolder) },
      ]} />
    </span>
  )
  /** A folder at any depth: its own dashboards, then its subfolders inside it. */
  const folderSection = (f: FolderSection, depth = 0): React.ReactNode => {
    const key = `folder:${f.id}`
    return (
      <section key={f.id} className="dsh-sec" aria-label={f.name}>
        {sectionHead(key, <Folder size={16} className="ficon" aria-hidden />, f.name, f.count, { id: f.id, name: f.name }, folderActions(f), depth)}
        {!collapsed.has(key) && <>
          {f.direct.length > 0 && grid(sorted(f.direct))}
          {f.children.map(c => folderSection(c, depth + 1))}
          {f.count === 0 && f.children.length === 0 && <p className="dsh-empty-line">{t('folders.empty')}</p>}
        </>}
      </section>
    )
  }
  const sorted = (rs: ReportSummary[]) => arrange(rs, 'all')

  const listTable = (groups: { key: string; label: React.ReactNode; rows: ReportSummary[] }[]) => (
    <div className="dsh-tblw"><table className="dsh-tbl" data-testid="dash-table">
      <thead><tr>
        <th className="c-ck"><span className="dl-sr-only">{t('dsh.select')}</span></th>
        <th className="c-nm">{t('dsh.col.name')}</th><th className="c-fd">{t('dsh.folder')}</th><th className="c-ds">{t('dsh.dataset')}</th>
        <th className="c-st">{t('dsh.col.status')}</th><th className="c-mod">{t('dsh.col.modified')}</th>
        <th className="c-act"><span className="dl-sr-only">{t('dsh.col.actions')}</span></th>
      </tr></thead>
      <tbody>{groups.map(g => [
        g.label ? <tr key={`g-${g.key}`} className="dsh-grp"><td colSpan={7}><span>{g.label} · {localDigits(String(g.rows.length))}</span></td></tr> : null,
        ...g.rows.map(r => <DashRow key={r.id} {...props(r)} />),
      ])}</tbody>
    </table></div>
  )

  const content = () => {
    if (loading) {
      return (
        <div className="dsh-grid" aria-busy="true" aria-label={t('dsh.loading')}>
          {Array.from({ length: 8 }, (_, i) => (
            <div key={i} className="dsh-card" aria-hidden="true">
              <span className="sk" style={{ aspectRatio: '16/9', borderRadius: '13px 13px 0 0' }} />
              <div className="dsh-bd">
                <span className="sk" style={{ height: 14, width: '78%' }} /><span className="sk" style={{ height: 10, width: '56%', marginTop: 6 }} />
                <div className="dsh-mt"><span className="sk" style={{ height: 20, width: 64, borderRadius: 999 }} /><span className="dsh-sp" /><span className="sk" style={{ height: 12, width: 70 }} /></div>
              </div>
            </div>
          ))}
        </div>
      )
    }
    if (loadError) return <LoadError what={t('dsh.what')} error={loadError} onRetry={load} />
    if (!reports.length) {
      return (
        <>
          <div className="dsh-hero" data-testid="dash-firstrun">
            <div className="art"><Thumb widgets={null} /></div>
            <div><h2>{t('dsh.first.title')}</h2><p>{t('dsh.first.text')}</p></div>
          </div>
          <div className="dsh-first">
            {([['blank', SquareDashedBottom, 'dsh.first.blank', 'dsh.first.blankSub'], ['tpl', LayoutTemplate, 'dsh.first.tpl', 'dsh.first.tplSub'],
              ['ai', Sparkles, 'dsh.first.ai', 'dsh.first.aiSub']] as const).map(([m, Icon, b, s]) => (
              <button key={m} type="button" className="dsh-start" onClick={() => openNew(m)}>
                <span className="ic" aria-hidden><Icon size={22} /></span><b>{t(b)}</b><span>{t(s)}</span>
                <span className="go">{t('dsh.first.go')}<ArrowRight size={15} aria-hidden /></span>
              </button>
            ))}
          </div>
        </>
      )
    }
    if (!shown.length) {
      if (repFilter.noMatches || repFilter.query.trim()) {
        const near = (recentIds ?? []).map(id => reports.find(r => r.id === id)).filter(Boolean).slice(0, 3) as ReportSummary[]
        return (
          <div className="dsh-empty" role="status">
            <span className="ic" aria-hidden><SearchX size={26} /></span>
            {/* The query in a <bdi>: "QA-" in the Arabic title read "-QA". */}
            <h2>{t('dsh.nomatch.title', { q: '\u0000' }).split('\u0000').flatMap((part, i) => i ? [<bdi key={i}>{repFilter.query.trim()}</bdi>, part] : [part])}</h2>
            <p>{t('dsh.nomatch.text')}</p>
            <div className="dsh-acts">
              <button type="button" className="btn btn-ghost dsh-btn-line" onClick={clearFilters}><X size={14} aria-hidden />{t('dsh.clearSearch')}</button>
              <button type="button" className="btn btn-primary" onClick={() => openNew('ai')}><Sparkles size={14} aria-hidden />{t('dsh.nomatch.ai')}</button>
            </div>
            {near.length > 0 && (
              <div className="dsh-near">
                <div className="l">{t('dsh.view.recent')}</div>
                {near.map(r => (
                  <Link key={r.id} to={`/reports/${r.id}`} onClick={() => setOpening(true)}>
                    <LayoutDashboard size={16} aria-hidden /><bdi>{r.name}</bdi><span className="tm">{formatTimeAgo(r.updated_at, t)}</span>
                  </Link>
                ))}
              </div>
            )}
          </div>
        )
      }
      if (narrowed) {
        return (
          <div className="dsh-empty" role="status">
            <span className="ic" aria-hidden><SearchX size={26} /></span>
            <h2>{t('dsh.nofilter.title')}</h2><p>{t('dsh.nofilter.text')}</p>
            <div className="dsh-acts"><button type="button" className="btn btn-ghost dsh-btn-line" onClick={clearFilters}><X size={14} aria-hidden />{t('dsh.clearFilters')}</button></div>
          </div>
        )
      }
      if (view === 'recent') return <div className="dsh-empty"><span className="ic" aria-hidden><Clock size={26} /></span><h2>{t('dsh.recent.empty')}</h2><p>{t('dsh.recent.emptyText')}</p></div>
      if (view === 'shared') return <div className="dsh-empty"><span className="ic" aria-hidden><Users size={26} /></span><h2>{t('dsh.shared.empty')}</h2><p>{t('dsh.shared.emptyText')}</p></div>
    }
    if (view.startsWith('f:')) {
      const id = Number(view.slice(2))
      const here = findSection(id)
      if (!here || (here.count === 0 && here.children.length === 0)) {
        return (
          <div className="dsh-empty" data-testid="dash-folder-empty">
            <span className="ic" aria-hidden><FolderOpen size={26} /></span>
            <h2>{t('dsh.folderEmpty')}</h2><p>{t('dsh.folderEmptyText')}</p>
            <div className="dsh-acts"><button type="button" className="btn btn-primary" onClick={() => openNew('blank', id)}><Plus size={14} aria-hidden />{t('dsh.newHere')}</button></div>
          </div>
        )
      }
      if (!narrowed) {
        if (layout === 'list') {
          const groups = [{ key: 'here', label: null as React.ReactNode, rows: sorted(here.direct) },
            ...flattenSections(here.children).map(s => ({ key: String(s.id), label: <><Folder size={14} aria-hidden /><bdi>{s.path}</bdi></>, rows: sorted(s.direct) }))]
          return listTable(groups.filter(g => g.rows.length))
        }
        return <>{countLine(here.count)}{here.direct.length > 0 && grid(sorted(here.direct))}{here.children.map(c => folderSection(c))}</>
      }
    }
    // Grouped by folder: the All view with nothing narrowing it.
    if (view === 'all' && !narrowed && tree) {
      const { sections, loose } = sectionsFor(shown, tree, { all: reports, keepEmpty: true })
      if (layout === 'list') {
        const groups = [
          ...flattenSections(sections).map(s => ({ key: String(s.id), label: <><Folder size={14} aria-hidden /><bdi>{s.path}</bdi></>, rows: sorted(s.direct) })),
          { key: 'root', label: sections.length ? <><FolderOpen size={14} aria-hidden />{t('dsh.notInFolder')}</> : null, rows: sorted(loose) },
        ]
        return listTable(groups.filter(g => g.rows.length))
      }
      return (
        <>
          {!sections.length && countLine(loose.length)}
          {sections.map(c => folderSection(c))}
          {loose.length > 0 && (sections.length ? (
            <section className="dsh-sec" aria-label={t('dsh.notInFolder')}>
              {sectionHead('root', <FolderOpen size={16} className="ficon" aria-hidden />, t('dsh.notInFolder'), loose.length, { id: null, name: null })}
              {!collapsed.has('root') && grid(sorted(loose))}
            </section>
          ) : grid(sorted(loose)))}
        </>
      )
    }
    // Flat: a view, a search or a facet narrowing the page.
    return (
      <>
        {countLine(shown.length, narrowed)}
        {layout === 'list' ? listTable([{ key: 'flat', label: null, rows: shown }]) : grid(shown)}
      </>
    )
  }
  function findSection(id: number): FolderSection | null {
    const { sections } = sectionsFor(arrange(reports, 'all'), tree, { all: reports, keepEmpty: true })
    const walk = (ss: FolderSection[]): FolderSection | null => {
      for (const s of ss) { if (s.id === id) return s; const got = walk(s.children); if (got) return got }
      return null
    }
    return walk(sections)
  }
  function flattenSections(ss: FolderSection[], prefix = ''): (FolderSection & { path: string })[] {
    return ss.flatMap(s => {
      const path = prefix ? `${prefix} / ${s.name}` : s.name
      return [{ ...s, path }, ...flattenSections(s.children, path)]
    })
  }

  // "/" focuses the search box, as the prototype's hint says.
  const searchWrap = useRef<HTMLLabelElement>(null)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement
      if (e.key !== '/' || e.ctrlKey || e.metaKey || e.altKey || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName) || el.isContentEditable) return
      const input = searchWrap.current?.querySelector('input')
      if (input) { e.preventDefault(); input.focus() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  if (opening) return <Loader label={t('common.loading')} />

  const sortLabel = t(sort === 'recent' ? 'dsh.sort.recent' : 'dsh.sort.name')
  const dsLabel = dsFilter == null ? t('dsh.any') : usedDatasets.find(d => d.id === dsFilter)?.name ?? t('dsh.any')

  return (
    <div className="dl-bleed dsh">
      <FolderNav view={view} onView={v => { setView(v); bulk.clear() }} counts={counts} folders={folders}
        treeFailed={treeFailed} onRetryTree={() => void loadTree()}
        creating={newFolder} onStartFolder={() => setNewFolder(true)} onCreateFolder={name => void createFolder(name)}
        onCancelFolder={() => setNewFolder(false)} onSubfolder={f => void subfolder(f)} onRename={f => void renameFolder(f)}
        onDelete={f => void removeFolder(f)} dropFor={dropFor} overTarget={overTarget}
        dragHint={reports.some(canEdit)} ready={!loading && !loadError} />
      <div className={`dsh-main${selectMode ? ' dsh-selmode' : ''}`}>
        <div className="dsh-page">
          <div className="dsh-hd">
            <div className="tt">
              <h1>{t('nav.dashboards')}</h1>
              <p>{t('dsh.subtitle')}</p>
            </div>
            <div className="dsh-acts">
              {!treeFailed && !loading && !loadError && (
                <button type="button" className="btn btn-ghost dsh-btn-line" onClick={() => setNewFolder(true)}>
                  <FolderPlus size={15} aria-hidden />{t('folders.newTop')}
                </button>
              )}
              <button type="button" className="btn btn-primary" onClick={() => openNew()} disabled={creating}>
                <Plus size={15} aria-hidden />{t('dashboards.new')}
              </button>
            </div>
          </div>

          {!loading && !loadError && reports.length > 0 && (
            <div className="dsh-tb" role="search">
              {repFilter.input && (
                <label className="dsh-srch" ref={searchWrap}>
                  <Search size={16} aria-hidden />
                  {repFilter.input}
                  {repFilter.query
                    ? <button type="button" className="dsh-ib" onClick={() => repFilter.setQuery('')} aria-label={t('dsh.clearSearch')} title={t('dsh.clearSearch')}><X size={14} aria-hidden /></button>
                    : <kbd aria-hidden>/</kbd>}
                </label>
              )}
              <div className="dsh-seg" role="group" aria-label={t('dsh.col.status')}>
                {(['all', 'draft', 'pub'] as const).map(s => (
                  <button key={s} type="button" aria-pressed={status === s} onClick={() => setStatus(s)}>
                    {t(s === 'all' ? 'dsh.st.all' : s === 'draft' ? 'dsh.st.drafts' : 'dsh.st.published')}
                    <span className="n">{localDigits(String(statusCount(s)))}</span>
                  </button>
                ))}
              </div>
              {usedDatasets.length > 0 && (
                <ActionMenu label={t('dsh.datasetIs', { name: dsLabel })} triggerClassName="dsh-dd"
                  trigger={<><Database size={15} aria-hidden /><span className="v">{t('dsh.dataset')}:</span> <span className="val"><bdi>{dsLabel}</bdi></span><ChevronDown size={14} aria-hidden /></>}
                  items={[{ key: 'any', label: t('dsh.any'), onSelect: () => setDsFilter(null) },
                    ...usedDatasets.map(d => ({ key: String(d.id), label: d.name, onSelect: () => setDsFilter(d.id) }))]} />
              )}
              <span className="dsh-sp" />
              <ActionMenu label={t('dsh.sortIs', { sort: sortLabel })} align="end" triggerClassName="dsh-dd"
                trigger={<><ArrowDownUp size={15} aria-hidden /><span className="v">{t('dsh.sort')}:</span> {sortLabel}<ChevronDown size={14} aria-hidden /></>}
                items={[{ key: 'recent', label: t('dsh.sort.recent'), onSelect: () => setSort('recent') },
                  { key: 'name', label: t('dsh.sort.name'), onSelect: () => setSort('name') }]} />
              <div className="dsh-seg ic" role="group" aria-label={t('dashboards.view')} data-testid="dashboards-layout">
                <button type="button" aria-pressed={layout === 'grid'} onClick={() => setLayout('grid')} aria-label={t('dsh.grid')} title={t('dsh.grid')}><LayoutGrid size={15} aria-hidden /></button>
                <button type="button" aria-pressed={layout === 'list'} onClick={() => setLayout('list')} aria-label={t('dsh.list')} title={t('dsh.list')}><List size={15} aria-hidden /></button>
              </div>
            </div>
          )}

          {content()}

          {selectMode && (
            <div className="dsh-bulk" role="toolbar" aria-label={t('bulk.aria')}>
              <span>{bulk.selected.size === 1 ? t('dsh.bulk.one') : t('dsh.bulk.many', { n: localDigits(String(bulk.selected.size)) })}</span>
              <span className="vr" />
              {tree && <button type="button" className="btn" onClick={() => setMoving(selected)}><FolderInput size={15} aria-hidden />{t('dsh.bulk.move')}</button>}
              <button type="button" className="btn" onClick={() => void bulkExport()}><Download size={15} aria-hidden />{t('dsh.bulk.export')}</button>
              <button type="button" className="btn dng" disabled={bulk.busy} onClick={() => void bulk.deleteSelected(reports)}><Trash2 size={15} aria-hidden />{t('bulk.delete')}</button>
              {testLike.some(r => !bulk.selected.has(r.id)) && (
                <button type="button" className="btn" onClick={() => bulk.setMany(testLike.map(r => r.id), true)}>
                  {testLike.length === 1 ? t('dsh.bulk.selectTestOne') : t('bulk.selectTest', { n: localDigits(String(testLike.length)) })}
                </button>
              )}
              <span className="vr" />
              <button type="button" className="dsh-ib" onClick={bulk.clear} aria-label={t('bulk.clear')} title={t('bulk.clear')}><X size={15} aria-hidden /></button>
            </div>
          )}
        </div>
      </div>

      {newDlg && (
        <NewDashboardDialog datasets={datasets ?? []} folders={folders} initialMode={newDlg.mode} initialFolder={newDlg.folder}
          placeholderName={nextUntitledName(reports.map(x => x.name), t('dsh.untitled'))} busy={creating}
          onClose={() => setNewDlg(null)} onCreate={c => void create(c)} />
      )}
      {suggest && <SuggestDashboardsDialog datasetId={suggest.id} datasetName={suggest.name} initialGoal={suggest.goal} onClose={() => setSuggest(null)} />}
      {moving && (
        <MoveDialog names={moving.map(r => r.name)} folders={folders}
          current={moving.length === 1 ? (nodes.get(moving[0].id)?.parent_id ?? null) : undefined}
          onClose={() => setMoving(null)}
          onMove={(id, name) => { const rs = moving; setMoving(null); bulk.clear(); void moveMany(rs, id, name) }} />
      )}
      {sharing && (
        <ShareDashboardDialog report={sharing} canEdit={canEdit(sharing)} isAdmin={isAdmin} onClose={() => setSharing(null)}
          onPublishedChange={published => setReports(prev => prev.map(x => x.id === sharing.id ? { ...x, published } : x))} />
      )}
    </div>
  )
}
