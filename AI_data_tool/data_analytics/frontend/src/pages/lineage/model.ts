import type { LineageGraph } from '../../services/api'

/**
 * Lineage (step 11): the org's data estate as a graph -- sources, datasets and
 * reports in three columns -- built from `GET /datasets/lineage/graph` alone.
 * Pure functions, so the page only draws what these decide.
 *
 * Nothing here is invented: a node's status is the dataset's own health (and,
 * for a report, the health of what it reads); a dataset that came from a file
 * hangs off one "Uploaded files" node so it has a source like every other.
 * Owners, row counts and a connection's own status are not in the graph, so
 * they are not shown (backend rows in PLAN.md).
 */

export type Col = 0 | 1 | 2
export type Status = 'ok' | 'warn' | 'err'
/** Why a node is worth a look: its refresh fails, it reads data whose refresh
 *  fails, its data is past its freshness target, or nothing uses it. */
export type Issue = 'fail' | 'broken' | 'stale' | 'orphan' | null
export type EdgeKind = 'extract' | 'join' | 'derived' | 'reads'

export interface LNode {
  key: string                  // "src:3" | "src:upload" | "ds:5" | "rep:2"
  col: Col
  id: number | null            // null for the uploads node
  name: string
  sourceType?: string          // a source's type ("postgresql", "sqlite", "file")
  mode?: 'import' | 'directquery'
  steps?: number               // a dataset's active transform steps
  refreshed?: string | null    // a dataset's last refresh
  never?: boolean              // a dataset never refreshed
  reads?: number               // how many datasets a report reads
  status: Status
  issue: Issue
}
export interface LEdge { from: string; to: string; kind: EdgeKind; bad: boolean }
export interface Model { nodes: LNode[]; edges: LEdge[]; byKey: Record<string, LNode> }

export const UPLOADS = 'src:upload'

export function buildModel(g: LineageGraph, uploadsName: string): Model {
  const nodes: LNode[] = []
  const edges: LEdge[] = []
  for (const s of g.sources) nodes.push({ key: `src:${s.id}`, col: 0, id: s.id, name: s.name, sourceType: s.type, status: 'ok', issue: null })
  const fromFile = g.datasets.filter(d => d.source_id == null && !(d.derived_from ?? []).length && !d.joins.length)
  if (fromFile.length) nodes.push({ key: UPLOADS, col: 0, id: null, name: uploadsName, sourceType: 'file', status: 'ok', issue: null })
  for (const d of g.datasets) {
    const status: Status = d.health === 'failing' ? 'err' : d.health === 'stale' || d.load?.staleness === 'stale' ? 'warn' : 'ok'
    nodes.push({
      key: `ds:${d.id}`, col: 1, id: d.id, name: d.name, mode: d.mode === 'directquery' ? 'directquery' : 'import',
      steps: d.transform?.count ?? 0, refreshed: d.load?.last_refreshed_at ?? null, never: d.load?.staleness === 'never',
      status, issue: d.health === 'failing' ? 'fail' : status === 'warn' ? 'stale' : null,
    })
    if (d.source_id != null) edges.push({ from: `src:${d.source_id}`, to: `ds:${d.id}`, kind: 'extract', bad: false })
    else if (fromFile.includes(d)) edges.push({ from: UPLOADS, to: `ds:${d.id}`, kind: 'extract', bad: false })
    for (const j of d.joins) edges.push({ from: `ds:${j}`, to: `ds:${d.id}`, kind: 'join', bad: false })
    for (const x of d.derived_from ?? []) if (!d.joins.includes(x)) edges.push({ from: `ds:${x}`, to: `ds:${d.id}`, kind: 'derived', bad: false })
  }
  for (const r of g.reports) {
    nodes.push({ key: `rep:${r.id}`, col: 2, id: r.id, name: r.name, reads: r.dataset_ids.length, status: 'ok', issue: null })
    for (const id of r.dataset_ids) edges.push({ from: `ds:${id}`, to: `rep:${r.id}`, kind: 'reads', bad: false })
  }
  const byKey = Object.fromEntries(nodes.map(n => [n.key, n]))
  // Drop edges to anything the graph did not list (a dataset outside the reader's reach).
  const kept = edges.filter(e => byKey[e.from] && byKey[e.to])

  // A failing or stale dataset reaches every dataset and report downstream.
  const spread = (seed: string[]) => {
    const out = new Set(seed)
    let grew = true
    while (grew) {
      grew = false
      for (const e of kept) if (out.has(e.from) && !out.has(e.to)) { out.add(e.to); grew = true }
    }
    return out
  }
  const failing = spread(nodes.filter(n => n.status === 'err').map(n => n.key))
  const stale = spread(nodes.filter(n => n.status === 'warn').map(n => n.key))
  for (const n of nodes) {
    if (n.col === 2) {
      if (failing.has(n.key)) { n.status = 'err'; n.issue = 'broken' }
      else if (stale.has(n.key)) { n.status = 'warn'; n.issue = 'stale' }
    }
    if (n.col === 1 && !n.issue && !kept.some(e => e.from === n.key)) n.issue = 'orphan'
  }
  for (const e of kept) e.bad = failing.has(e.from) && byKey[e.from].status === 'err'
  return { nodes, edges: kept, byKey }
}

/** Columns in order, each sorted to cut crossings: a node sits near the
 *  average place of what feeds it (the design's barycentre ordering). */
export function orderColumns(m: Model): LNode[][] {
  const cols: LNode[][] = [0, 1, 2].map(c => m.nodes.filter(n => n.col === c))
  const idx: Record<string, number> = {}
  cols[0].forEach((n, i) => { idx[n.key] = i })
  const centre = (n: LNode) => {
    const up = m.edges.filter(e => e.to === n.key && idx[e.from] != null).map(e => idx[e.from] + (m.byKey[e.from].col === n.col ? 0.5 : 0))
    return up.length ? up.reduce((a, b) => a + b, 0) / up.length : 1e6
  }
  for (const c of [1, 2]) {
    cols[c] = [...cols[c]].sort((a, b) => centre(a) - centre(b) || a.name.localeCompare(b.name))
    cols[c].forEach((n, i) => { idx[n.key] = i })
  }
  return cols
}

// Geometry, in the drawing's own units (the design's).
export const CW = 260, NH = 60, GAP = 12, TOP = 56, SHOW = 10
export const COLX = [40, 420, 800] as const
export const WIDTH = COLX[2] + CW + 40

export interface Layout {
  y: Record<string, number>
  visible: Record<string, boolean>
  more: { col: Col; y: number; hidden: number }[]
  height: number
  /** The left edge of a column, mirrored in right-to-left. */
  x: (col: Col) => number
}

/** Each column top to bottom. Datasets and reports fold after ten into
 *  "+ N more" unless expanded; `keep` (the focus, a search hit) always shows. */
export function layout(cols: LNode[][], expanded: Partial<Record<Col, boolean>>, keep: Set<string>, rtl: boolean): Layout {
  const y: Record<string, number> = {}
  const visible: Record<string, boolean> = {}
  const more: Layout['more'] = []
  let height = 0
  cols.forEach((list, c) => {
    const limit = c === 0 || expanded[c as Col] ? list.length : SHOW
    list.forEach((n, i) => { visible[n.key] = i < limit || keep.has(n.key) })
    let at = TOP
    for (const n of list) if (visible[n.key]) { y[n.key] = at; at += NH + GAP }
    const hidden = list.filter(n => !visible[n.key]).length
    if (hidden || (c > 0 && expanded[c as Col] && list.length > SHOW)) {
      more.push({ col: c as Col, y: at, hidden })
      // A folded node's edges meet the "+ N more" row.
      for (const n of list) if (!visible[n.key]) y[n.key] = at + 20 - NH / 2
      at += 40 + GAP
    }
    height = Math.max(height, at)
  })
  return { y, visible, more, height: height + 20, x: c => (rtl ? WIDTH - COLX[c] - CW : COLX[c]) }
}

export type Direction = 'up' | 'both' | 'down'
export type Depth = 'one' | 'all'

/** What the focus lights: the node, and its upstream and/or downstream, one
 *  hop or all the way. Edges by index into `edges`. */
export function reach(edges: LEdge[], key: string | null, dir: Direction = 'both', depth: Depth = 'all'):
  { nodes: Set<string>; edges: Set<number> } | null {
  if (!key) return null
  const nodes = new Set([key])
  const lit = new Set<number>()
  const walk = (from: string, down: boolean) => {
    edges.forEach((e, i) => {
      const next = down ? (e.from === from ? e.to : null) : (e.to === from ? e.from : null)
      if (!next) return
      lit.add(i)
      if (!nodes.has(next)) { nodes.add(next); if (depth === 'all') walk(next, down) }
    })
  }
  if (dir !== 'down') walk(key, false)
  if (dir !== 'up') walk(key, true)
  return { nodes, edges: lit }
}

/** Everything downstream of a node, all the way (what a change would touch). */
export function downstream(edges: LEdge[], key: string): Set<string> {
  const out = new Set<string>()
  const stack = [key]
  while (stack.length) {
    const cur = stack.pop()!
    for (const e of edges) if (e.from === cur && !out.has(e.to)) { out.add(e.to); stack.push(e.to) }
  }
  return out
}

export interface Filters { types: Set<Col>; sourceType: string | null; mode: 'import' | 'directquery' | null; issues: boolean }
export const NO_FILTERS: Filters = { types: new Set(), sourceType: null, mode: null, issues: false }
export const filtersOn = (f: Filters) => f.types.size > 0 || f.sourceType != null || f.mode != null || f.issues

/** Does a node pass the filters? A source or report passes a dataset-level
 *  filter (mode) through a dataset next to it that does; a dataset or report
 *  passes the source-type filter through the source it comes from. Filters
 *  fade what fails them; nothing moves. */
export function matches(m: Model, n: LNode, f: Filters): boolean {
  if (f.types.size && !f.types.has(n.col)) return false
  if (f.issues && !n.issue) return false
  const near = (pred: (x: LNode) => boolean) => pred(n) || m.edges.some(e =>
    (e.from === n.key && pred(m.byKey[e.to])) || (e.to === n.key && pred(m.byKey[e.from])))
  if (f.mode && !near(x => x.col === 1 && x.mode === f.mode)) return false
  if (f.sourceType) {
    const st = f.sourceType
    const fromSource = (x: LNode): boolean => x.col === 0 ? x.sourceType === st
      : m.edges.some(e => e.to === x.key && m.byKey[e.from].col === 0 && m.byKey[e.from].sourceType === st)
    if (n.col === 2 ? !m.edges.some(e => e.to === n.key && fromSource(m.byKey[e.from])) : !fromSource(n)) return false
  }
  return true
}

/** A connection type as people write it. */
export function sourceTypeName(type: string | undefined): string {
  const known: Record<string, string> = { postgresql: 'PostgreSQL', postgres: 'PostgreSQL', sqlite: 'SQLite', mysql: 'MySQL',
    mssql: 'SQL Server', sqlserver: 'SQL Server', oracle: 'Oracle', snowflake: 'Snowflake', bigquery: 'BigQuery', duckdb: 'DuckDB' }
  return type ? known[type.toLowerCase()] ?? type : ''
}
