import type { ReportSummary } from '../../services/api'
import type { WorkspaceNode, WorkspaceTree } from '../../types/report'
import { SUGGESTED_FOR, SUGGESTED_PLAIN } from './listParts'

/**
 * What the Dashboards list (redesign 7b) reads off the reports and the
 * workspace tree. Placement, sharing and folder management all live in the
 * tree (`/workspace/tree`); the reports list knows none of them.
 */

export interface FlatFolder {
  id: number
  name: string
  depth: number
  parent_id: number | null
  /** Dashboards anywhere beneath, among the ones this viewer can open. */
  count: number
  can_manage: boolean
}

const walk = (n: WorkspaceNode, f: (n: WorkspaceNode) => void) => { f(n); n.children.forEach(c => walk(c, f)) }

/** Every folder, depth-first in tree order, with what it holds. */
export function flatFolders(tree: WorkspaceTree | null, known: Set<number>): FlatFolder[] {
  const out: FlatFolder[] = []
  const visit = (n: WorkspaceNode, depth: number): number => {
    if (n.node_type !== 'folder') return n.report_id != null && known.has(n.report_id) ? 1 : 0
    const at = out.length
    out.push({ id: n.id, name: n.name ?? 'Untitled', depth, parent_id: n.parent_id, count: 0, can_manage: n.can_manage })
    out[at].count = n.children.reduce((s, c) => s + visit(c, depth + 1), 0)
    return out[at].count
  }
  ;(tree?.roots ?? []).forEach(r => { if (r.node_type === 'folder') visit(r, 0) })
  return out
}

/** The dashboards anywhere under one folder. */
export function reportsUnder(tree: WorkspaceTree | null, folderId: number): Set<number> {
  const ids = new Set<number>()
  const find = (ns: WorkspaceNode[]): WorkspaceNode | null => {
    for (const n of ns) {
      if (n.id === folderId && n.node_type === 'folder') return n
      const got = find(n.children)
      if (got) return got
    }
    return null
  }
  const root = find(tree?.roots ?? [])
  if (root) walk(root, n => { if (n.node_type === 'report' && n.report_id != null) ids.add(n.report_id) })
  return ids
}

/** Dashboards somebody deliberately gave this viewer: a folder grant over
 *  it, or a grant naming them (the tree's `shared_with_me`). Merely "not
 *  mine" is not shared -- see the server's comment on the field. */
export function sharedWithMe(tree: WorkspaceTree | null): Set<number> {
  const ids = new Set<number>()
  const visit = (n: WorkspaceNode, inherited: boolean) => {
    const on = inherited || !!n.shared_with_me
    if (n.node_type === 'report' && n.report_id != null && on && !n.is_mine) ids.add(n.report_id)
    n.children.forEach(c => visit(c, on))
  }
  tree?.roots.forEach(n => visit(n, false))
  tree?.unfiled.forEach(n => visit(n, false))
  return ids
}

/** report id -> the folder it sits in (null: not in a folder). */
export function folderOf(tree: WorkspaceTree | null): Map<number, number | null> {
  const out = new Map<number, number | null>()
  const visit = (n: WorkspaceNode, folder: number | null) => {
    if (n.node_type === 'report' && n.report_id != null) out.set(n.report_id, folder)
    n.children.forEach(c => visit(c, n.node_type === 'folder' ? n.id : folder))
  }
  tree?.roots.forEach(n => visit(n, null))
  return out
}

/** Draft / Published as the server means them. A legacy report (no author)
 *  is outside the publish regime and is neither. */
export function statusOf(r: ReportSummary): 'draft' | 'pub' | null {
  if (r.created_by == null) return null
  return r.published ? 'pub' : 'draft'
}

/** Suggest dashboards writes its provenance into the description, in one of
 *  two shapes. Read, never rewritten: "Suggested from the data" says nothing a
 *  badge cannot; "Suggested for: <goal>" keeps the goal and drops the prefix. */
export function provenance(r: ReportSummary): { suggested: boolean; blurb: string } {
  const goal = r.description?.startsWith(SUGGESTED_FOR) ? r.description.slice(SUGGESTED_FOR.length).trim() : null
  const suggested = r.description === SUGGESTED_PLAIN || goal !== null
  return { suggested, blurb: goal || (suggested ? '' : (r.description ?? '')) }
}

/** Most generated dashboards are NAMED after their dataset; the chip would say
 *  it twice. Kept where the name does not already say it. */
export function showsDataset(r: ReportSummary, datasetName: string | undefined): boolean {
  if (!datasetName) return false
  const flat = (v: string) => v.toLowerCase().replace(/\s+/g, ' ').trim()
  return !flat(r.name).includes(flat(datasetName))
}

/** Visible pages: the ones a reader can land on. */
export const pageCount = (r: ReportSummary) =>
  (r.pages ?? []).filter(p => !p.page_type || p.page_type === 'normal').length
