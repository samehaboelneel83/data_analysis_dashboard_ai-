import { useEffect, useState, type ReactNode, type HTMLAttributes } from 'react'
import { reportGrantsApi } from '../../services/api'
import type { ReportSummary, ReportGrant } from '../../services/api'
import type { WorkspaceNode, WorkspaceTree } from '../../types/report'
import { ChevronDown, ChevronRight, Folder } from 'lucide-react'
import toast from 'react-hot-toast'
import { useModalDialog } from '../../components/ui/useModalDialog'
import { Z_OVERLAY } from '../../lib/zIndex'

/** "Share to": the author names a person (by email -- sharing must not double
 *  as an org-directory listing) and a level. Grants are the ONLY way another
 *  user gets design rights on an authored dashboard; publishing gives the org
 *  view-only access and locks the layout. */
export function ShareDialog({ report, onClose }: { report: ReportSummary; onClose: () => void }) {
  const dialogRef = useModalDialog<HTMLDivElement>(onClose)
  const [grants, setGrants] = useState<ReportGrant[] | null>(null)
  const [email, setEmail] = useState('')
  const [level, setLevel] = useState<'view' | 'edit' | 'data'>('edit')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    reportGrantsApi.list(report.id)
      .then(setGrants)
      .catch(() => { toast.error('Could not load who this is shared with'); setGrants([]) })
  }, [report.id])

  const add = async () => {
    if (!email.trim()) return
    setBusy(true)
    try {
      const g = await reportGrantsApi.create(report.id, { email: email.trim(), level })
      setGrants(prev => [...(prev ?? []).filter(x => x.user_id !== g.user_id), g])
      setEmail('')
      toast.success(`Shared with ${g.email}`)
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Could not share')
    } finally { setBusy(false) }
  }

  const remove = async (g: ReportGrant) => {
    try {
      await reportGrantsApi.remove(report.id, g.id)
      setGrants(prev => (prev ?? []).filter(x => x.id !== g.id))
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Could not remove the grant')
    }
  }

  const LEVEL_LABEL = { view: 'Can view', edit: 'Can edit', data: 'Can edit + data' } as const

  // The z-index is the one value that stays inline: it comes from the
  // app-wide stacking register, so it is data this component is given
  // rather than a style it chooses.
  return (
    <div className="dl-modal" style={{ zIndex: Z_OVERLAY }}>
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-label={`Share ${report.name}`}
        className="dl-modal__panel">
        <div className="dl-modal__head">
          <h2 className="dl-modal__title">Share “{report.name}”</h2>
          <button onClick={onClose} aria-label="Close"
            className="dl-modal__x">×</button>
        </div>
        <p className="dl-modal__note">
          Sharing gives one person access — including to a draft. Publishing (separate)
          makes it view-only for the whole organisation.
        </p>

        <div className="dl-modal__row">
          <input value={email} onChange={e => setEmail(e.target.value)}
            placeholder="colleague@company.com" aria-label="Email to share with"
            onKeyDown={e => { if (e.key === 'Enter') void add() }}
            className="dl-modal__input" />
          <select value={level} onChange={e => setLevel(e.target.value as typeof level)}
            aria-label="Access level"
            className="dl-modal__control">
            <option value="view">Can view</option>
            <option value="edit">Can edit</option>
            <option value="data">Can edit + data</option>
          </select>
          <button className="btn btn-primary btn-sm" onClick={add} disabled={busy || !email.trim()} title={!email.trim() ? 'Enter an email address first' : undefined}>
            Share
          </button>
        </div>

        {grants === null && <p className="dl-modal__note">Loading…</p>}
        {grants !== null && grants.length === 0 && (
          <p className="dl-modal__note">Not shared with anyone yet.</p>
        )}
        {grants !== null && grants.map(g => (
          <div key={g.id} className="dl-grant">
            <span className="dl-grant__email">{g.email}</span>
            <span className="dl-grant__level">{LEVEL_LABEL[g.level]}</span>
            <button className="btn btn-ghost btn-sm dl-grant__remove" onClick={() => remove(g)}
              aria-label={`Remove access for ${g.email}`}>
              Remove
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}

/** A folder with something to show: its own dashboards, then its subfolders. */
export interface FolderSection {
  id: number
  name: string
  direct: ReportSummary[]
  children: FolderSection[]
  /** Dashboards anywhere beneath, which is what a collapsed heading shows. */
  count: number
  /** Dashboards anywhere beneath in the UNFILTERED list -- zero means the
   *  folder is genuinely empty, as opposed to emptied by the search box. */
  total: number
  /** Whether THIS viewer may rename or delete it. The server's answer. */
  can_manage: boolean
}

/**
 * Which headings are folded shut, remembered per browser.
 *
 * Its own key rather than the tree's `workspace.open-folders`: that one lists
 * what is OPEN and defaults everything closed, which is right for a menu and
 * wrong for a page whose job is to show the dashboards. Here everything is
 * open until you fold it. Group headings share the set under their own keys.
 */
const COLLAPSED_KEY = 'dashboards.collapsed-sections'

export function loadCollapsed(): Set<string> {
  try {
    const raw = localStorage.getItem(COLLAPSED_KEY)
    return new Set(raw ? (JSON.parse(raw) as string[]) : [])
  } catch {
    // Private window, cleared site data, storage blocked: an unreadable
    // preference is not worth failing the page over.
    return new Set()
  }
}

export function saveCollapsed(collapsed: Set<string>) {
  try {
    localStorage.setItem(COLLAPSED_KEY, JSON.stringify([...collapsed]))
  } catch {
    /* see loadCollapsed */
  }
}

/**
 * One heading with a body under it, at any of the three tiers.
 *
 * The heading's text IS the toggle, so the whole name is a click target and
 * the heading's accessible name stays exactly the folder's name -- the count
 * sits beside the heading, not inside it, for the same reason. The body is
 * not rendered while folded rather than hidden: nothing under a closed
 * heading needs to exist.
 */
export function Fold({ name, tier, heading, count, note, actions, dropProps, dropActive, collapsed, onToggle, children }: {
  name: string
  tier: 'group' | 'folder'
  heading: 'h2' | 'h3' | 'h4' | 'h5' | 'h6'
  count: number
  note?: string
  /** Row-end controls -- a folder's menu. Revealed on hover and focus. */
  actions?: ReactNode
  /** Drag-and-drop handlers for the heading row, when it accepts a card. */
  dropProps?: HTMLAttributes<HTMLDivElement>
  /** A card is being held over this heading right now. */
  dropActive?: boolean
  collapsed: boolean
  onToggle: () => void
  children: ReactNode
}) {
  const Heading = heading
  return (
    <section className={`dl-fold dl-fold--${tier}`} aria-label={name}>
      <div className="dl-fold__head"
        data-drop-target={dropActive ? 'true' : undefined}
        {...dropProps}>
        <Heading className="dl-fold__title">
          <button type="button" className="dl-fold__toggle"
            aria-expanded={!collapsed} onClick={onToggle}>
            {/* Only the CLOSED chevron points along the reading direction,
                so only it mirrors in Arabic (index.css). */}
            <span className={`dl-fold__caret${collapsed ? ' dl-fold__caret--closed' : ''}`} aria-hidden>
              {collapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
            </span>
            {tier === 'folder' && <Folder size={13} aria-hidden className="dl-fold__glyph" />}
            <span className="dl-fold__name" title={name}>{name}</span>
          </button>
        </Heading>
        <span className="dl-fold__count"
          aria-label={`${count} ${count === 1 ? 'dashboard' : 'dashboards'}`}>
          {count}
        </span>
        {actions && <span className="dl-fold__actions">{actions}</span>}
      </div>
      {!collapsed && note && <p className="dl-group-note">{note}</p>}
      {!collapsed && <div className="dl-fold__body">{children}</div>}
    </section>
  )
}

/**
 * The rows arranged the way the workspace tree arranges them.
 *
 * Placement lives in workspace_nodes, not on the report row, so the tree is
 * the only thing that can answer "which folder". Folders come back in tree
 * order and a folder's dashboards in ITS order (the one you get by dragging),
 * because that order is the structure the headings exist to show.
 *
 * A folder contributing no card contributes no heading: this is a list of
 * dashboards, not a folder browser, and a search that empties a folder
 * removes its heading along with its cards. `loose` is everything the tree
 * does not place -- top-level report nodes and `unfiled` alike.
 */
export function sectionsFor(rows: ReportSummary[], tree: WorkspaceTree | null,
  opts: { all: ReportSummary[]; keepEmpty: boolean }) {
  const byId = new Map(rows.map(r => [r.id, r]))
  const known = new Set(opts.all.map(r => r.id))
  const placed = new Set<number>()
  const build = (node: WorkspaceNode): FolderSection | null => {
    const direct: ReportSummary[] = []
    const children: FolderSection[] = []
    let total = 0
    for (const c of node.children) {
      if (c.node_type === 'folder') {
        const s = build(c)
        if (s) { children.push(s); total += s.total }
      } else if (c.report_id != null) {
        if (known.has(c.report_id)) total += 1
        const r = byId.get(c.report_id)
        if (r && !placed.has(r.id)) { direct.push(r); placed.add(r.id) }
      }
    }
    const count = direct.length + children.reduce((n, c) => n + c.count, 0)
    // A folder shows when it has something to show -- or when it has NOTHING
    // AT ALL and the page is not mid-search. The page manages folders now, so
    // one you just created must be on screen to be named, filled or deleted;
    // it used to vanish, which made "New folder" look like it did nothing.
    // One the search box emptied stays hidden: it has dashboards, they just
    // do not match, and its heading would promise otherwise.
    if (count === 0 && !(total === 0 && opts.keepEmpty)) return null
    return {
      id: node.id, name: node.name ?? 'Untitled', direct, children, count, total,
      can_manage: node.can_manage,
    }
  }
  const sections = (tree?.roots ?? [])
    .filter(n => n.node_type === 'folder')
    .map(build)
    .filter((s): s is FolderSection => s !== null)
  return { sections, loose: rows.filter(r => !placed.has(r.id)) }
}

/**
 * report id -> its workspace node, for every dashboard the tree places.
 *
 * A move is a re-parent of the dashboard's NODE, not of the dashboard, and an
 * unfiled dashboard has no node yet (id 0) -- for it the move is the
 * creation of one. Loose dashboards at the top level do have a node, with a
 * null parent. Both facts live only in the tree.
 */
export function reportNodes(tree: WorkspaceTree | null): Map<number, { id: number; parent_id: number | null }> {
  const out = new Map<number, { id: number; parent_id: number | null }>()
  const walk = (n: WorkspaceNode) => {
    if (n.node_type === 'report' && n.report_id != null) {
      out.set(n.report_id, { id: n.id, parent_id: n.parent_id })
    }
    n.children.forEach(walk)
  }
  tree?.roots.forEach(walk)
  tree?.unfiled.forEach(walk)
  return out
}

export const SUGGESTED_PLAIN = 'Suggested from the data'
export const SUGGESTED_FOR = 'Suggested for:'
