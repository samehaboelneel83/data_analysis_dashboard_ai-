import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import type { WorkspaceNode, WorkspaceTree as Tree } from '../types/report'
import { reportsApi, workspaceApi } from '../services/api'
import {
  BarChart3, ChevronDown, ChevronRight, Eye, FileText, Folder, FolderOpen,
  FolderPlus, Lock, Megaphone, Pencil, Plus, Share2, Unlock, Users, X,
} from 'lucide-react'
import { useConfirm } from './ui/ConfirmDialog'
import { usePrompt } from './ui/PromptDialog'
import ActionMenu from './ActionMenu'
import FolderShareDialog from './FolderShareDialog'
import LoadError from './ui/LoadError'

/**
 * The org's report-navigation menu: folders, the reports filed in them, and
 * each report's pages.
 *
 * The server sends the tree already nested, with pages joined in and report
 * labels resolved, so this renders what it is given rather than reassembling a
 * flat list. `unfiled` reports render at the bottom -- every report must be
 * reachable, and one that exists without a way to open it is worse than the
 * flat list this replaces.
 *
 * Folders remember whether they were open across reloads. A menu that
 * re-collapses every time you navigate makes a deep tree unusable, and the
 * state is per-viewer and disposable, so localStorage is the right home for it.
 */

const OPEN_KEY = 'workspace.open-folders'

function loadOpen(): Set<number> {
  try {
    const raw = localStorage.getItem(OPEN_KEY)
    return new Set(raw ? (JSON.parse(raw) as number[]) : [])
  } catch {
    // A private window, cleared site data, or a browser blocking storage. An
    // unreadable preference is not worth failing the menu over.
    return new Set()
  }
}

function saveOpen(open: Set<number>) {
  try {
    localStorage.setItem(OPEN_KEY, JSON.stringify([...open]))
  } catch {
    /* see loadOpen */
  }
}

/** A folder and the dashboards anywhere beneath it. */
export interface FolderSelection {
  id: number
  name: string
  /** Every report_id in this folder's subtree, at any depth. Computed here
   *  because the tree owns the shape; the page that filters by it would
   *  otherwise have to fetch and walk the same tree a second time. */
  reportIds: number[]
}

interface Props {
  /** The folder currently filtering the page, if any. Purely presentational --
   *  the page owns the filter, this only marks the row. */
  selectedFolderId?: number | null
  /** Clicking a folder. Called with null when the same folder is clicked
   *  again, which clears the filter. Absent means folders only expand. */
  onSelectFolder?: (selection: FolderSelection | null) => void
}

/** Every report id beneath a node, itself included. */
function subtreeReportIds(node: WorkspaceNode): number[] {
  const out: number[] = []
  const walk = (n: WorkspaceNode) => {
    if (n.node_type === 'report' && n.report_id != null) out.push(n.report_id)
    n.children.forEach(walk)
  }
  walk(node)
  return out
}

export default function WorkspaceTree({ selectedFolderId, onSelectFolder }: Props) {
  const confirm = useConfirm()
  const prompt = usePrompt()
  const [tree, setTree] = useState<Tree>({ roots: [], unfiled: [] })
  const [open, setOpen] = useState<Set<number>>(loadOpen)
  const [busy, setBusy] = useState(false)
  const [shareNode, setShareNode] = useState<WorkspaceNode | null>(null)
  // Three states, three different claims. This used to swallow the failure and
  // render an empty tree, so "the request died" and "you have no folders" were
  // the same picture -- and the first invites nobody to retry.
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<unknown>(null)
  const navigate = useNavigate()

  const refresh = async () => {
    setLoadError(null)
    try {
      setTree(await workspaceApi.tree())
    } catch (e) {
      setLoadError(e ?? new Error('failed'))
      setTree({ roots: [], unfiled: [] })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void refresh() }, [])

  // `reportIds` is a snapshot of the subtree at the moment it was clicked, and
  // this component refreshes itself after every action it owns -- create,
  // rename, move, delete. Without this the page keeps filtering by a shape
  // that is no longer on screen: a dashboard dragged into the selected folder
  // stays hidden, and deleting the selected folder leaves a chip naming a
  // folder that no longer exists.
  //
  // Deliberately keyed on `tree` alone. Adding selectedFolderId would re-emit
  // on every selection change, which is both redundant and a loop hazard.
  useEffect(() => {
    // Not while the tree is unknown. `tree` starts as an empty shape, so
    // without this the effect fires on mount against that placeholder, finds
    // nothing, and clears a selection the user still has. A failed load is
    // the same situation: we could not ask, so we cannot say the folder is
    // gone -- the filter stays and the tree shows its own error.
    if (loading || loadError != null) return
    if (selectedFolderId == null || !onSelectFolder) return
    const find = (nodes: WorkspaceNode[]): WorkspaceNode | null => {
      for (const n of nodes) {
        if (n.node_type === 'folder' && n.id === selectedFolderId) return n
        const hit = find(n.children)
        if (hit) return hit
      }
      return null
    }
    const node = find(tree.roots)
    onSelectFolder(node
      ? { id: node.id, name: node.name ?? 'Untitled', reportIds: subtreeReportIds(node) }
      : null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tree])

  const toggle = (id: number) => {
    setOpen(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      saveOpen(next)
      return next
    })
  }

  /** Expand a folder so something just created inside it is actually visible.
   *  Creating into a collapsed folder and leaving it collapsed reads as
   *  "nothing happened". */
  const openFolder = (id: number) => {
    setOpen(prev => {
      if (prev.has(id)) return prev
      const next = new Set(prev)
      next.add(id)
      saveOpen(next)
      return next
    })
  }

  /** A workspace, or a subfolder inside one. `parentId` null means top level.
   *
   *  The root call sends NO parent_id rather than an explicit null: that is
   *  the wire shape the server has always received for a top-level folder,
   *  and widening it here would be a change nobody asked for. */
  const addFolder = async (parentId: number | null = null) => {
    const name = (await prompt({
      title: parentId === null ? 'New folder' : 'New subfolder',
      label: 'Folder name', placeholder: 'e.g. Finance', confirmLabel: 'Create',
    }))?.trim()
    if (!name) return
    setBusy(true)
    try {
      await workspaceApi.create({
        node_type: 'folder', name,
        ...(parentId === null ? {} : { parent_id: parentId }),
      })
      if (parentId !== null) openFolder(parentId)
      await refresh()
      toast.success(`Created ${name}`)
    } catch {
      toast.error('Could not create the folder')
    } finally {
      setBusy(false)
    }
  }

  /**
   * A new dashboard, filed straight into this folder and opened for design.
   *
   * Two writes, reported separately on purpose. If the dashboard is created
   * but filing it fails, saying "could not create the dashboard" would be a
   * lie about a dashboard that now exists -- so that case names what
   * happened and where to find it, and still opens the builder.
   */
  const addDashboard = async (parentId: number | null) => {
    const name = (await prompt({
      title: 'New dashboard', label: 'Dashboard name',
      placeholder: 'e.g. Q3 revenue', confirmLabel: 'Create',
    }))?.trim()
    if (!name) return
    setBusy(true)
    try {
      let report
      try {
        report = await reportsApi.create({ name })
      } catch {
        toast.error('Could not create the dashboard')
        return
      }
      try {
        await workspaceApi.create({
          node_type: 'report', report_id: report.id, parent_id: parentId,
        })
        if (parentId !== null) openFolder(parentId)
        toast.success(`Created ${name}`)
      } catch {
        toast.error(`${name} was created but could not be filed here — it is under Unfiled`)
      }
      await refresh()
      navigate(`/reports/${report.id}`)
    } finally {
      setBusy(false)
    }
  }

  const togglePublish = async (node: WorkspaceNode) => {
    try {
      await workspaceApi.update(node.id, { published: !node.published })
      await refresh()
      toast.success(node.published
        ? `${node.name} is a private workspace again`
        : `${node.name} published — its dashboards are now open to everyone, view-only`)
    } catch {
      toast.error('Could not change publication')
    }
  }

  const renameFolder = async (node: WorkspaceNode) => {
    const name = (await prompt({
      title: 'Rename folder', defaultValue: node.name ?? '', confirmLabel: 'Rename',
    }))?.trim()
    if (!name || name === node.name) return
    await workspaceApi.update(node.id, { name })
    await refresh()
  }

  const removeNode = async (node: WorkspaceNode) => {
    // Says what actually happens. Deleting a folder re-parents its contents
    // rather than deleting them, and users who have been burned by other tools
    // will not believe that unless it is written down.
    const isFolder = node.node_type === 'folder'
    if (!await confirm({
      title: isFolder ? `Delete the folder "${node.name}"?` : 'Remove this dashboard from the tree?',
      body: isFolder
        ? 'Anything inside it moves up a level — no dashboards are deleted.'
        : 'The dashboard itself is kept.',
      confirmLabel: isFolder ? 'Delete folder' : 'Remove',
    })) return
    await workspaceApi.delete(node.id)
    await refresh()
  }

  /**
   * Restrict a folder to specific roles, or clear the restriction.
   *
   * Deliberately blunt -- a comma-separated prompt rather than a role picker.
   * The picker belongs in the admin screens where roles are actually managed,
   * and a half-built one here would become the thing people remember about the
   * feature.
   *
   * An EMPTY answer clears the restriction, and the prompt says so: visible to
   * everyone is the default, so getting back to it must not require guessing
   * that "no roles" is how you spell it.
   */
  const editRoles = async (node: WorkspaceNode) => {
    const answer = await prompt({
      title: 'Who can see this folder?',
      body: 'Role IDs allowed to see it, comma-separated. '
          + 'Leave empty for everyone in the organisation.',
      label: 'Role IDs',
      defaultValue: node.role_ids.join(', '),
      placeholder: 'e.g. 2, 5',
      confirmLabel: 'Save',
      // An empty answer is the documented way to clear the restriction, so it
      // must be submittable rather than blocked as "nothing entered".
      required: false,
    })
    if (answer === null) return
    const ids = answer
      .split(',')
      .map(part => Number(part.trim()))
      .filter(n => Number.isInteger(n) && n > 0)
    try {
      await workspaceApi.setRoles(node.id, ids)
      await refresh()
      toast.success(ids.length
        ? `Restricted to ${ids.length} role(s)`
        : 'Visible to everyone')
    } catch {
      toast.error('Could not change who can see this folder')
    }
  }

  const fileReport = async (node: WorkspaceNode, parentId: number | null) => {
    if (!node.report_id) return
    await workspaceApi.create({
      node_type: 'report', report_id: node.report_id, parent_id: parentId,
    })
    await refresh()
  }

  /**
   * Drag a node onto a folder to move it, or onto the Workspace header to send
   * it back to the root.
   *
   * The server rejects a move into the dragged node's own subtree, so the UI
   * does not duplicate that walk -- it surfaces the refusal. Re-implementing
   * the check here would give two places to keep in agreement, and the one that
   * matters is the one holding the data.
   */
  const [dragId, setDragId] = useState<number | null>(null)
  const [overId, setOverId] = useState<number | null>(null)

  const move = async (nodeId: number, parentId: number | null) => {
    if (nodeId === parentId) return
    try {
      await workspaceApi.update(nodeId, { parent_id: parentId })
      await refresh()
    } catch {
      // The commonest refusal is the cycle guard; anything else is equally
      // worth showing rather than silently leaving the tree unchanged.
      toast.error('That move is not allowed')
    } finally {
      setDragId(null)
      setOverId(null)
    }
  }

  const dropTargetProps = (targetId: number | null) => ({
    onDragOver: (e: React.DragEvent) => { e.preventDefault(); setOverId(targetId) },
    onDragLeave: () => setOverId(prev => (prev === targetId ? null : prev)),
    onDrop: (e: React.DragEvent) => {
      e.preventDefault()
      e.stopPropagation()
      if (dragId !== null) void move(dragId, targetId)
    },
  })

  const renderNode = (node: WorkspaceNode, depth: number) => {
    const isFolder = node.node_type === 'folder'
    const isOpen = open.has(node.id)
    const hasChildren = node.children.length > 0 || node.pages.length > 0
    const isSelected = isFolder && selectedFolderId === node.id

    return (
      <div key={`${node.node_type}-${node.id}-${node.report_id ?? 0}`}>
        <div
          draggable={node.id > 0}
          onDragStart={e => { e.stopPropagation(); setDragId(node.id) }}
          onDragEnd={() => { setDragId(null); setOverId(null) }}
          {...(isFolder ? dropTargetProps(node.id) : {})}
          data-drop-target={isFolder && overId === node.id ? 'true' : undefined}
          data-dragging={dragId === node.id ? 'true' : undefined}
          className={`dl-tree__row${isSelected ? ' dl-tree__row--selected' : ''}`}
          aria-current={isSelected || undefined}
          // Indent is the only per-row value, because it is data (depth), not
          // styling. The drop outline and the drag fade are attribute
          // selectors in index.css.
          style={{ paddingInlineStart: 6 + depth * 12 }}
          onClick={() => {
            if (isFolder && onSelectFolder) {
              // Selecting and opening are ONE gesture, but selecting must not
              // CLOSE anything: open folders persist across reloads, so the
              // folder you want to filter by is usually already open, and an
              // unconditional toggle meant the click that filtered the list
              // also collapsed the folder it was filtering by. Deselecting
              // still closes, so the round trip is symmetric.
              if (isSelected) {
                toggle(node.id)
                onSelectFolder(null)
              } else {
                if (!isOpen) toggle(node.id)
                onSelectFolder({
                  id: node.id,
                  name: node.name ?? 'Untitled',
                  reportIds: subtreeReportIds(node),
                })
              }
            } else if (isFolder) toggle(node.id)
            else if (node.report_id) navigate(`/reports/${node.report_id}`)
          }}
        >
          {/* A report with pages gets its OWN disclosure control. Making the
              whole row toggle would mean a report could never be opened; making
              it navigate would mean its pages could never be reached. The
              caret expands, the label opens. */}
          <span
            aria-hidden={!hasChildren || isFolder}
            {...(hasChildren && !isFolder
              ? { role: 'button', 'aria-label': `Expand ${node.name ?? 'report'}` }
              : {})}
            onClick={e => {
              if (!isFolder && hasChildren) { e.stopPropagation(); toggle(node.id) }
            }}
            className={`dl-tree__caret${(hasChildren || isFolder) && !isOpen ? ' dl-tree__caret--closed' : ''}`
              + (hasChildren && !isFolder ? ' dl-tree__caret--clickable' : '')}
          >
            {/* Only the CLOSED chevron points along the reading direction, so
                only it mirrors in Arabic. The open one points down, which is
                the same down in every script. */}
            {hasChildren || isFolder ? (isOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />) : ''}
          </span>
          <span aria-hidden className="dl-tree__glyph">
            {isFolder ? (isOpen ? <FolderOpen size={16} /> : <Folder size={16} />) : <BarChart3 size={16} />}
          </span>
          <span title={node.name ?? 'Untitled'} className="dl-tree__name">
            {node.name ?? 'Untitled'}
          </span>
          {/* A granted report the viewer cannot design is marked where it is
              listed -- discovering it only inside the builder ("why is
              everything disabled?") is the surprise this icon prevents. */}
          {!isFolder && node.my_capability === 'view' && (
            <span title="View only" aria-label="View only"
              className="dl-tree__badge"><Eye size={12} /></span>
          )}
          {/* The viewer's side of a share: this workspace reaches them
              through a folder grant. The badge answers "why can I see
              this?" where the folder is listed. */}
          {isFolder && node.shared_with_me && (
            <span title="Shared with you" aria-label="Shared with you"
              className="dl-tree__badge"><Users size={12} /></span>
          )}

          {/* Controls appear only where the SERVER says this viewer may manage
              the node. Creating stays open to everyone (the + in the header);
              changing or removing what somebody else filed does not. The flag
              is computed server-side so this does not re-implement the rule. */}
          {node.id > 0 && node.can_manage && (
            <span className="dl-tree__actions">
              {isFolder ? (
                <>
                  {/* STATE, not controls. A restriction or a publication
                      nobody can see is one nobody remembers -- so those two
                      keep a glyph in the row. They appear only when the state
                      is actually on, which means an ordinary folder spends
                      its whole width on its NAME. */}
                  {node.role_ids.length > 0 && (
                    <span aria-label={`${node.name} is restricted to ${node.role_ids.length} role(s)`}
                      title={`Restricted to ${node.role_ids.length} role(s)`}
                      className="dl-tree__badge dl-tree__state">
                      <Lock size={12} />
                    </span>
                  )}
                  {node.published && (
                    <span aria-label={`${node.name} is published to everyone`}
                      title="Published — its dashboards are open to everyone, view-only"
                      className="dl-tree__badge dl-tree__state dl-tree__state--published">
                      <Megaphone size={12} />
                    </span>
                  )}
                  {/* ONE menu where six bare icon buttons used to sit. Six left
                      the folder's own name about five characters wide in a
                      248px rail, and each action was a glyph you had to guess;
                      the menu spells them out. This is precisely what
                      ActionMenu exists for -- the rail was the last cluster of
                      bare icons in the app.

                      The wrapper swallows the click so opening the menu does
                      not also collapse the folder underneath it. */}
                  <span onClick={e => e.stopPropagation()} className="dl-tree__glyph">
                    <ActionMenu
                      label={`Actions for ${node.name}`}
                      triggerClassName="dl-tree__btn"
                      triggerStyle={undefined}
                      // The rail is `overflow-x: hidden` and 248px wide, so a
                      // popup hanging off the LEADING edge of a control this
                      // far along the row is simply cut in half -- and the
                      // viewport flip cannot help, because the viewport has
                      // room the rail does not.
                      align="end"
                      items={[
                        { key: 'dashboard', label: 'New dashboard',
                          icon: <BarChart3 size={13} />,
                          onSelect: () => void addDashboard(node.id) },
                        { key: 'subfolder', label: 'New subfolder',
                          icon: <FolderPlus size={13} />,
                          onSelect: () => void addFolder(node.id) },
                        { key: 'rename', label: 'Rename', icon: <Pencil size={13} />,
                          onSelect: () => void renameFolder(node) },
                        { key: 'share', label: 'Share with people',
                          icon: <Share2 size={13} />,
                          onSelect: () => setShareNode(node) },
                        { key: 'publish',
                          label: node.published ? 'Make private again' : 'Publish to everyone',
                          icon: <Megaphone size={13} />,
                          onSelect: () => void togglePublish(node) },
                        { key: 'roles', label: 'Who can see it',
                          icon: node.role_ids.length ? <Lock size={13} /> : <Unlock size={13} />,
                          onSelect: () => void editRoles(node) },
                        { key: 'delete', label: 'Delete folder', icon: <X size={13} />,
                          danger: true, onSelect: () => void removeNode(node) },
                      ]}
                    />
                  </span>
                </>
              ) : (
                <button
                  aria-label={`Remove ${node.name ?? 'report'} from the tree`}
                  title="Remove from tree"
                  onClick={e => { e.stopPropagation(); void removeNode(node) }}
                  className="dl-tree__btn"
                ><X size={14} /></button>
              )}
            </span>
          )}
        </div>

        {/* A report's pages: one click straight to the page, which is the whole
            reason pages appear in the menu at all. */}
        {!isFolder && isOpen && node.pages.map((page, i) => (
          <div
            key={page.id}
            onClick={() => navigate(`/reports/${node.report_id}?page=${i}`)}
            className="dl-tree__page"
            style={{ paddingInlineStart: 6 + (depth + 1) * 12 + 12 }}
          >
            <span aria-hidden className="dl-tree__glyph"><FileText size={12} /></span>
            <span title={page.name} className="dl-tree__name">
              {page.name}
            </span>
          </div>
        ))}

        {isOpen && node.children.map(child => renderNode(child, depth + 1))}
      </div>
    )
  }

  // THREE groups, and the middle one is a claim about privilege, so it has to
  // be true. "Shared with me" means somebody DELIBERATELY gave it to me -- a
  // folder share, or my name on a dashboard's grant list (the server decides,
  // and sends `shared_with_me`). Everything else that is not mine is the
  // organisation's general furniture: demo folders, anything published to the
  // whole org, and -- for an admin -- every colleague's folder, which an admin
  // sees by office, not by gift. Filing those under "Shared with me" claimed a
  // privilege nobody granted.
  //
  // Grouping spans roots AND unfiled reports: an unfiled report is still
  // somebody's work or somebody's grant, and filing it must not be the price
  // of appearing in the right section.
  const bucket = (n: WorkspaceNode) =>
    n.is_mine ? 'mine' : n.shared_with_me ? 'shared' : 'org'
  const roots = {
    mine: tree.roots.filter(n => bucket(n) === 'mine'),
    shared: tree.roots.filter(n => bucket(n) === 'shared'),
    org: tree.roots.filter(n => bucket(n) === 'org'),
  }
  const loose = {
    mine: tree.unfiled.filter(n => bucket(n) === 'mine'),
    shared: tree.unfiled.filter(n => bucket(n) === 'shared'),
    org: tree.unfiled.filter(n => bucket(n) === 'org'),
  }
  const filled = (['mine', 'shared', 'org'] as const)
    .filter(k => roots[k].length + loose[k].length > 0)
  // One group needs no heading -- a lone label over the entire tree says
  // nothing. The exception is a share: "somebody gave you this" is a claim
  // worth making even when it is all you have, which is exactly the first day
  // of the person a workspace was just shared with.
  const grouped = filled.length > 1 || filled.includes('shared')

  if (loading) {
    return (
      <div data-testid="workspace-tree" className="dl-tree">
        {[0, 1, 2, 3].map(i => (
          <div key={i} className="dl-tree__skeleton" aria-hidden />
        ))}
        <span className="dl-sr-only">Loading your workspaces…</span>
      </div>
    )
  }

  if (loadError != null) {
    // Bordered and tinted, so it cannot be mistaken for the deliberate empty
    // tree below it. The page around this still renders its dashboards.
    return (
      <div data-testid="workspace-tree" className="dl-tree">
        <LoadError what="your workspaces" error={loadError} onRetry={() => void refresh()} />
      </div>
    )
  }

  const renderUnfiled = (node: WorkspaceNode) => (
    <div
      key={`unfiled-${node.report_id}`}
      onClick={() => node.report_id && navigate(`/reports/${node.report_id}`)}
      className="dl-tree__row"
      style={{ paddingInlineStart: 18 }}
    >
      <span aria-hidden className="dl-tree__glyph"><BarChart3 size={16} /></span>
      <span title={node.name ?? undefined} className="dl-tree__name">{node.name}</span>
      {node.my_capability === 'view' && (
        <span title="View only" aria-label="View only"
          className="dl-tree__badge"><Eye size={12} /></span>
      )}
      <span className="dl-tree__actions">
        <button
          aria-label={`File ${node.name} in the tree`}
          title="Add to tree"
          onClick={e => { e.stopPropagation(); void fileReport(node, null) }}
          className="dl-tree__btn"
        ><Plus size={14} /></button>
      </span>
    </div>
  )

  return (
    <div data-testid="workspace-tree" className="dl-tree">
      <div
        {...dropTargetProps(null)}
        data-drop-target={overId === null && dragId !== null ? 'true' : undefined}
        className="dl-tree__head">
        {/* Dropping on the header moves a node back to the root -- otherwise
            anything dragged into a folder could never come out again. */}
        <span title="Drop here to move to the top level">Workspaces</span>
        <button
          // Wrapped, not passed by reference: addFolder now takes a parent and
          // the click event would arrive as one.
          onClick={() => void addFolder(null)}
          disabled={busy}
          aria-label="New folder"
          title="New folder"
          className="dl-tree__btn dl-tree__btn--end"
        ><Plus size={14} /></button>
      </div>

      {/* Group by OWNERSHIP, not by permission. An admin can manage every
          node in the org, so grouping on can_manage would file the whole tree
          under "mine". is_mine answers the question the heading asks -- and
          for report entries it now carries the REPORT's author, so unfiled
          reports land in the right section too.

          Both headings are suppressed unless both groups exist: an admin who
          owns nothing should not read "Granted to me" over the entire org's
          tree, and a new user with one folder should not see an empty
          "My workspaces" above it. */}
      {/* Rendered empty on purpose, and quietly: a workspace with no folders
          is a normal thing to have, not a failure. The failure has its own
          bordered block above and never borrows this copy. */}
      {tree.roots.length === 0 && tree.unfiled.length === 0 && (
        <p className="dl-tree__empty">
          No folders yet. Create one to group your dashboards.
        </p>
      )}

      {grouped ? (
        (['mine', 'shared', 'org'] as const).filter(k => filled.includes(k)).map(k => (
          <div key={k} className="dl-rail__group">
            <div className="dl-tree__group">{SECTION_TITLE[k]}</div>
            {roots[k].map(node => renderNode(node, 0))}
            {loose[k].map(renderUnfiled)}
          </div>
        ))
      ) : (
        <>
          {tree.roots.map(node => renderNode(node, 0))}
          {tree.unfiled.length > 0 && (
            <>
              <div className="dl-tree__group">Unfiled</div>
              {tree.unfiled.map(renderUnfiled)}
            </>
          )}
        </>
      )}

      {shareNode && (
        <FolderShareDialog node={shareNode}
          onClose={() => setShareNode(null)}
          onChanged={() => void refresh()} />
      )}
    </div>
  )
}

/** Only "Shared with me" is a claim about privilege; the other two describe
 *  where a thing came from. "Organisation" is deliberately not "Shared": an
 *  admin seeing a colleague's folder was given nothing. */
const SECTION_TITLE = {
  mine: 'My workspaces',
  shared: 'Shared with me',
  org: 'Organisation',
} as const


