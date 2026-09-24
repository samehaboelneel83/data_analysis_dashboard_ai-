import { useCallback, useContext, useEffect, useState } from 'react'
import LoadError from '../components/ui/LoadError'
import { Link, useNavigate } from 'react-router-dom'
import { reportsApi, datasetsApi, workspaceApi } from '../services/api'
import type { ReportSummary, DatasetSummary } from '../services/api'
import type { WorkspaceTree } from '../types/report'
import { FileBarChart, FolderPlus, Pencil, Plus, Trash2, Share2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { useConfirm } from '../components/ui/ConfirmDialog'
import { usePrompt } from '../components/ui/PromptDialog'
import { useListFilter } from '../components/ui/ListFilter'
import { AuthContext } from '../contexts/AuthContext'
import { Eye, Globe, GlobeLock } from 'lucide-react'
import IconLabel from '../components/ui/IconLabel'
import ActionMenu from '../components/ActionMenu'
import { useT } from '../i18n'

import {
  ShareDialog, Fold, loadCollapsed, saveCollapsed, sectionsFor, reportNodes,
  SUGGESTED_PLAIN, SUGGESTED_FOR,
} from './reports/listParts'
import type { FolderSection } from './reports/listParts'
import { nextUntitledName } from '../lib/untitledName'
export { nextUntitledName }

export default function Reports() {
  const t = useT()
  const [reports, setReports]   = useState<ReportSummary[]>([])
  const repFilter = useListFilter(reports,
    r => [r.name, r.description], 'Search dashboards')
  const [datasets, setDatasets] = useState<DatasetSummary[]>([])
  const [loading, setLoading]   = useState(true)
  const [creating, setCreating] = useState(false)

  // Three states, not two. Without the catch a server error cleared `loading`
  // and fell through to "No reports yet" -- which invites the user to recreate
  // work that already exists.
  const [loadError, setLoadError] = useState<unknown>(null)
  const [sharing, setSharing] = useState<ReportSummary | null>(null)
  const [tree, setTree] = useState<WorkspaceTree | null>(null)
  const [collapsed, setCollapsed] = useState<Set<string>>(loadCollapsed)
  const [folderBusy, setFolderBusy] = useState(false)
  // The card being dragged, and the heading it is over. State rather than
  // dataTransfer: the tree did it this way too, and jsdom's drag events carry
  // no dataTransfer at all.
  const [dragging, setDragging] = useState<ReportSummary | null>(null)
  const [overTarget, setOverTarget] = useState<string | null>(null)
  const toggleFold = (key: string) => setCollapsed(prev => {
    const next = new Set(prev)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    saveCollapsed(next)
    return next
  })
  // Context read directly (not the throwing useAuth()) so tests without an
  // AuthProvider degrade to "not admin" rather than crashing.
  const isAdmin = !!useContext(AuthContext)?.user?.role?.is_org_admin
  // Folder placement is a courtesy on top of the list, so it fails on its own:
  // an async wrapper, because reading `workspaceApi.tree` can throw
  // SYNCHRONOUSLY under a partial module mock, which would escape a .catch()
  // attached inside the Promise.all array and take the whole page down.
  const loadFolders = async (): Promise<WorkspaceTree | null> => {
    try {
      return await workspaceApi.tree()
    } catch {
      return null
    }
  }

  const load = useCallback(() => {
    setLoading(true); setLoadError(null)
    Promise.all([reportsApi.list(), datasetsApi.list(), loadFolders()])
      .then(([r, d, tree]) => {
        setReports(r); setDatasets(d)
        setTree(tree)
      })
      .catch(e => setLoadError(e ?? new Error('failed')))
      .finally(() => setLoading(false))
  }, [])
  useEffect(load, [load])

  // SAS's "New report" opens the editor at once, as "Report N", and you name
  // it when you know what it is. The old form demanded a name first and
  // offered the dataset as an unsorted <select> -- two decisions before the
  // author had seen anything. The builder now asks for data itself, in the
  // dataset picker (?pick=data), and the title is renamed in place.
  const handleCreate = async () => {
    if (creating) return
    setCreating(true)
    try {
      const r = await reportsApi.create({ name: nextUntitledName(reports.map(x => x.name)) })
      openReport(`/reports/${r.id}?pick=data`)
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Could not create a dashboard')
    } finally {
      setCreating(false)
    }
  }

  const openReport = useNavigate()

  const confirm = useConfirm()
  const prompt = usePrompt()
  const handleDelete = async (id: number, name: string) => {
    if (!await confirm({ title: `Delete dashboard "${name}"?`, body: 'This cannot be undone.' })) return
    await reportsApi.delete(id)
    setReports(r => r.filter(x => x.id !== id))
    toast.success('Dashboard deleted')
  }

  const handleRename = async (r: ReportSummary) => {
    const name = (await prompt({
      title: 'Rename dashboard', defaultValue: r.name, confirmLabel: 'Rename',
    }))?.trim()
    if (!name || name === r.name) return
    await reportsApi.update(r.id, { name })
    setReports(prev => prev.map(x => x.id === r.id ? { ...x, name } : x))
    toast.success('Dashboard renamed')
  }

  // ---- folders: the actions the tree had, with the tree's own words --------
  // The page reloads the tree after each one rather than patching its copy:
  // the server decides where a deleted folder's contents land and what the
  // new node looks like, and a guess here would be a second source of truth.
  const refreshTree = async () => setTree(await loadFolders())

  const addFolder = async (parentId: number | null = null) => {
    const name = (await prompt({
      title: parentId === null ? 'New folder' : 'New subfolder',
      label: 'Folder name', placeholder: 'e.g. Finance', confirmLabel: 'Create',
    }))?.trim()
    if (!name) return
    setFolderBusy(true)
    try {
      await workspaceApi.create({
        node_type: 'folder', name,
        ...(parentId === null ? {} : { parent_id: parentId }),
      })
      await refreshTree()
      toast.success(`Created ${name}`)
    } catch {
      toast.error('Could not create the folder')
    } finally {
      setFolderBusy(false)
    }
  }

  const renameFolder = async (f: FolderSection) => {
    const name = (await prompt({
      title: 'Rename folder', defaultValue: f.name, confirmLabel: 'Rename',
    }))?.trim()
    if (!name || name === f.name) return
    await workspaceApi.update(f.id, { name })
    await refreshTree()
  }

  const removeFolder = async (f: FolderSection) => {
    // Says what actually happens. Deleting a folder re-parents its contents
    // rather than deleting them, and users who have been burned by other tools
    // will not believe that unless it is written down.
    if (!await confirm({
      title: `Delete the folder "${f.name}"?`,
      body: 'Anything inside it moves up a level — no dashboards are deleted.',
      confirmLabel: 'Delete folder',
    })) return
    await workspaceApi.delete(f.id)
    await refreshTree()
  }

  // ---- moving a dashboard: a drop, then a question, then the server -------
  const nodes = reportNodes(tree)

  const endDrag = () => { setDragging(null); setOverTarget(null) }

  const moveDashboard = async (r: ReportSummary, parentId: number | null, targetName: string | null) => {
    const node = nodes.get(r.id)
    // Dropped where it already is: nothing to ask, nothing to send.
    if ((node?.parent_id ?? null) === parentId) { endDrag(); return }
    // A drop is the easiest gesture to make by accident, and a move can widen
    // who sees the dashboard -- a folder's grants reach everything in it. So
    // it is confirmed, and the confirmation says that much.
    const ok = await confirm({
      title: `Move "${r.name}" to ${targetName === null ? 'the top level' : `"${targetName}"`}?`,
      body: 'Nothing is copied or deleted. Anyone the destination folder is shared with will be able to open it there.',
      confirmLabel: 'Move',
      destructive: false,
    })
    if (!ok) { endDrag(); return }
    try {
      if (node && node.id > 0) {
        await workspaceApi.update(node.id, { parent_id: parentId })
      } else {
        // No node row yet: the move IS the creation of one.
        await workspaceApi.create({ node_type: 'report', report_id: r.id, parent_id: parentId })
      }
      await refreshTree()
      toast.success(`Moved ${r.name} to ${targetName ?? 'the top level'}`)
    } catch (e) {
      // The server's answer is the answer -- a folder the viewer cannot
      // manage, the cycle guard -- shown as it was given, never pre-empted.
      const detail = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      toast.error(typeof detail === 'string' ? detail : 'That move is not allowed')
    } finally {
      endDrag()
    }
  }

  const dropTargetProps = (key: string, parentId: number | null, targetName: string | null) => ({
    onDragOver: (e: React.DragEvent<HTMLDivElement>) => { e.preventDefault(); setOverTarget(key) },
    onDragLeave: () => setOverTarget(prev => (prev === key ? null : prev)),
    onDrop: (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault()
      e.stopPropagation()
      if (dragging) void moveDashboard(dragging, parentId, targetName)
    },
  })

  const handlePublish = async (r: ReportSummary) => {
    const next = !r.published
    try {
      await reportsApi.setPublished(r.id, next)
      setReports(prev => prev.map(x => x.id === r.id ? { ...x, published: next } : x))
      toast.success(next
        ? 'Published — everyone in your organisation can now open it, view-only'
        : 'Unpublished — back to a private draft')
    } catch (e: any) {
      // The publish gate (Phase 7.4) answers with {message, findings}.
      const d = e?.response?.data?.detail
      toast.error(typeof d === 'string' ? d : d?.message ?? 'Could not change publication')
    }
  }

  return (
    <div>
      <div className="dl-page-head">
        <div>
          <h1 className="dl-page-head__title">{t('nav.dashboards')}</h1>
          <p className="dl-page-head__sub">{t('dashboards.subtitle')}</p>
        </div>
        <div className="dl-page-head__tools">
          {repFilter.input}
          <button className="btn btn-ghost" onClick={() => void addFolder(null)} disabled={folderBusy}>
            <FolderPlus size={14} /> New folder
          </button>
          <button className="btn btn-primary" onClick={() => void handleCreate()} disabled={creating}>
            <Plus size={14} /> {t('dashboards.new')}
          </button>
        </div>
      </div>

      {loading && <p className="dl-muted-line">Loading…</p>}

      {!loading && !!loadError && (
        <LoadError what="reports" error={loadError} onRetry={load} />
      )}

      {!loading && !loadError && reports.length === 0 && (
        <div className="card dl-empty">
          <FileBarChart size={40} className="dl-empty__icon" />
          <p className="dl-empty__title">No dashboards yet</p>
          <p className="dl-empty__body">Create a dashboard and design it with charts, tables, KPIs, and more.</p>
          <button className="btn btn-primary" onClick={() => setCreating(true)}>Create your first dashboard</button>
        </div>
      )}

      {repFilter.noMatches && (
        <p className="dl-nomatch">
          Nothing matches “{repFilter.query}”.
        </p>
      )}
      {reports.length > 0 && (() => {
        const renderCard = (r: ReportSummary) => {
          const ds = datasets.find(d => d.id === r.dataset_id)
          // Mirrors the server exactly: delete_report requires >= edit, so a
          // view-level viewer gets no Delete control, and "Open designer"
          // becomes plain "Open" -- a designer link over a report whose every
          // edit the server refuses is a dead control with extra steps.
          const canEdit = (r.my_capability ?? 'view') !== 'view'
          // Publish and Share are the AUTHOR's controls (admins too) and only
          // exist on authored dashboards -- a legacy row (created_by null) is
          // outside the regime, and offering Publish there would be a button
          // the server 400s.
          const owned = r.created_by != null
          const canAdminister = owned && (r.is_mine || isAdmin)
          // Suggest dashboards writes its provenance into the DESCRIPTION
          // (SuggestDashboardsDialog), in one of two shapes. Read, never
          // rewritten -- the API value is untouched and this is purely how the
          // card draws it.
          //
          //   "Suggested from the data"  -> says nothing a chip cannot, and
          //                                 said it identically on every such
          //                                 card, costing a full line each.
          //   "Suggested for: <goal>"    -> the goal IS worth reading; only
          //                                 the prefix is redundant once a
          //                                 chip says "Suggested".
          const suggestedFor = r.description?.startsWith(SUGGESTED_FOR)
            ? r.description.slice(SUGGESTED_FOR.length).trim()
            : null
          const isSuggested = r.description === SUGGESTED_PLAIN || suggestedFor !== null
          const blurb = suggestedFor || (isSuggested ? '' : r.description)
          // Almost every generated dashboard is NAMED after its dataset --
          // "What stands out in Demo Sales", "Enrolments 2025 - escalated to
          // registrar" -- and the footer then printed that name again two
          // lines below. One fact, two labels, on most of the grid.
          //
          // Not dropped outright: on "What stands out in this data" the chip
          // is the only thing distinguishing one card from the next.
          const flat = (v: string) => v.toLowerCase().replace(/\s+/g, ' ').trim()
          const showDataset = !!ds && !flat(r.name).includes(flat(ds.name))
          return (
            <div key={r.id} className="card dl-dash-card"
              draggable
              data-dragging={dragging?.id === r.id ? 'true' : undefined}
              onDragStart={e => {
                // Some browsers refuse to start a drag with no payload.
                e.dataTransfer?.setData('text/plain', String(r.id))
                setDragging(r)
              }}
              onDragEnd={endDrag}
              // The whole card opens the dashboard, because the whole card is
              // what people aim at. One guard instead of a stopPropagation on
              // every control: a link or a button inside the card handles its
              // own click, and a control added later is covered without anyone
              // remembering to opt it out.
              onClick={e => {
                if ((e.target as HTMLElement).closest('a, button')) return
                openReport(`/reports/${r.id}`)
              }}
              // Deliberately NOT tabIndex/role=link. The title below is a real
              // anchor: it already carries the route for the keyboard, for a
              // screen reader, and for middle-click and "open in new tab". A
              // second focusable wrapper would put two tab stops and two
              // announcements on one destination.
              >
              <div className="dl-dash-card__head">
                {/* The title owns the row. It used to share it with the chips
                    at flex-shrink: 0, which left "What stands out in Route
                    planning extract output" about eight characters wide and
                    six lines tall. */}
                <Link to={`/reports/${r.id}`} className="dl-dash-card__title"
                  title={r.name}>
                  {r.name}
                </Link>
                <div className="dl-dash-card__controls">
                  {canAdminister && (
                    <span className="dl-card-actions">
                      <button className="btn btn-ghost btn-sm" onClick={() => setSharing(r)}
                        aria-label={`Share ${r.name}`} title={`Share ${r.name} with a person`}>
                        <Share2 size={12} />
                      </button>
                      <button className="btn btn-ghost btn-sm" onClick={() => handlePublish(r)}
                        aria-label={r.published ? `Unpublish ${r.name}` : `Publish ${r.name}`}
                        title={r.published
                          ? 'Unpublish — back to a private draft'
                          : 'Publish — everyone in your organisation can open it, view-only'}>
                        {r.published ? <GlobeLock size={14} /> : <Globe size={14} />}
                      </button>
                    </span>
                  )}
                  {/* Icon-only, so it needs an explicit name: a screen reader otherwise
                      announces "button" with nothing to distinguish one row's delete
                      from another's. Names the report, so the row is identified too. */}
                  {canEdit && (
                    <span className="dl-card-actions">
                      <button className="btn btn-ghost btn-sm"
                        onClick={() => void handleRename(r)}
                        aria-label={`Rename dashboard ${r.name}`} title={`Rename dashboard ${r.name}`}>
                        <Pencil size={14} />
                      </button>
                      <button className="btn btn-ghost btn-sm dl-danger-item"
                        onClick={() => handleDelete(r.id, r.name)}
                        aria-label={`Delete dashboard ${r.name}`} title={`Delete dashboard ${r.name}`}>
                        <Trash2 size={14} />
                      </button>
                    </span>
                  )}
                </div>
              </div>
              {blurb && <p className="dl-dash-card__blurb">{blurb}</p>}
              {/* Every chip on one row, beside the dataset it describes. Three
                  of them used to sit up beside the title, where each one cost
                  the name a few more characters of width. */}
              <div className="dl-dash-card__foot">
                {/* "No dataset" used to render here. It is an absence, not a
                    fact about the dashboard, and it cost a label on every card
                    that had one. */}
                {showDataset && <span className="badge badge-categorical">{ds!.name}</span>}
                {isSuggested && (
                  <span className="dl-chip dl-chip--suggested"
                    title="Created by Suggest dashboards from this dataset">
                    Suggested
                  </span>
                )}
                {owned && r.published && (
                  <span className="dl-chip dl-chip--published"
                    title="Published — everyone in your organisation can open it, view-only">
                    published
                  </span>
                )}
                {!canEdit && (
                  <span className="dl-chip dl-chip--viewonly" title="View only">
                    <IconLabel icon={Eye} size={11}>view only</IconLabel>
                  </span>
                )}
                <span className="dl-dash-card__date">
                  {new Date(r.created_at).toLocaleDateString()}
                </span>
              </div>
            </div>
          )
        }

        const grid = (items: ReportSummary[]) => (
          <div className="dl-dash-grid">{items.map(renderCard)}</div>
        )

        // One shape at every depth: the folder's own cards, then its
        // subfolders as smaller headings inside it. Nesting the <section>s
        // is what indents them (index.css), so depth is never a prop.
        const renderFolder = (f: FolderSection, depth: number) => (
          <Fold key={f.id} name={f.name} tier="folder" count={f.count}
            heading={`h${Math.min(3 + depth, 6)}` as 'h3' | 'h4' | 'h5' | 'h6'}
            collapsed={collapsed.has(`folder:${f.id}`)}
            onToggle={() => toggleFold(`folder:${f.id}`)}
            dropProps={dropTargetProps(`folder:${f.id}`, f.id, f.name)}
            dropActive={overTarget === `folder:${f.id}`}
            // can_manage is the server's answer: no menu rather than a menu
            // of items it would refuse.
            actions={f.can_manage && (
              <ActionMenu
                label={`Actions for ${f.name}`}
                items={[
                  { key: 'subfolder', label: 'New subfolder', icon: <FolderPlus size={14} />,
                    onSelect: () => void addFolder(f.id) },
                  { key: 'rename', label: 'Rename', icon: <Pencil size={14} />,
                    onSelect: () => void renameFolder(f) },
                  { key: 'delete', label: 'Delete folder', icon: <Trash2 size={14} />, danger: true,
                    onSelect: () => void removeFolder(f) },
                ]}
              />
            )}>
            {f.direct.length > 0 && grid(f.direct)}
            {f.children.map(c => renderFolder(c, depth + 1))}
            {f.count === 0 && f.children.length === 0 && (
              <p className="dl-fold__empty">Empty folder</p>
            )}
          </Fold>
        )

        // Loose dashboards FIRST. A run of cards after a heading reads as
        // belonging to it; a run before the first heading reads as belonging
        // to nothing, which is the truth -- and it avoids inventing an
        // "Unfiled" label for the absence.
        // Empty folders are the viewer's own and show only where their own
        // dashboards do -- never under "Granted to me" -- and never while a
        // search is narrowing the page.
        const arranged = (items: ReportSummary[], keepEmpty: boolean) => {
          const { sections, loose } = sectionsFor(items, tree, {
            all: reports, keepEmpty: keepEmpty && !repFilter.query.trim(),
          })
          return (
            <>
              {loose.length > 0 && grid(loose)}
              {sections.map(s => renderFolder(s, 0))}
            </>
          )
        }

        // Same grouping contract as the workspace tree: authorship, not
        // permission, and headings only when the viewer actually has both
        // kinds -- a user who authored everything reads a plain grid. Both
        // paths render subsets of repFilter.filtered, so the search box keeps
        // filtering the grouped view too (listFilterWiring.test pins the flat
        // path textually; the grouped one derives from the same array).
        const mine = repFilter.filtered.filter(r => r.is_mine)
        const granted = repFilter.filtered.filter(r => !r.is_mine)
        if (mine.length === 0 || granted.length === 0) {
          return arranged(repFilter.filtered, true)
        }
        return (
          <>
            <Fold name="My workspaces" tier="group" heading="h2" count={mine.length}
              collapsed={collapsed.has('group:mine')}
              onToggle={() => toggleFold('group:mine')}
              dropProps={dropTargetProps('root', null, null)}
              dropActive={overTarget === 'root'}>
              {arranged(mine, true)}
            </Fold>
            <Fold name="Granted to me" tier="group" heading="h2" count={granted.length}
              note="Published or shared with you by others. View-only dashboards open without design controls."
              collapsed={collapsed.has('group:granted')}
              onToggle={() => toggleFold('group:granted')}>
              {arranged(granted, false)}
            </Fold>
          </>
        )
      })()}
      {sharing && <ShareDialog report={sharing} onClose={() => setSharing(null)} />}
    </div>
  )
}
