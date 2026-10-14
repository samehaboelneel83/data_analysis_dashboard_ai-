/**
 * A hierarchy slicer's tree (hierarchy plan, step 2, 2026-10-10): Egypt ▸
 * Cairo ▸ Nasr City with tick boxes. Pure, so the rules can be tested apart
 * from the screen.
 *
 * The selection is a set of LEAF paths. A parent is ticked when every leaf
 * under it is, half-ticked when some are. What is sent to the other widgets
 * is the shortest list of paths that says the same thing: a fully ticked
 * country is the one path ["Egypt"], not each of its cities -- and everything
 * ticked is no filter at all. The server applies it exactly (filter op
 * "paths"), so Egypt › Alexandria and US › Boston never let in a US Alexandria.
 */

export interface TreeNode { value: string; count: number; children: TreeNode[] }
export type Path = string[]
export type CheckState = 'on' | 'off' | 'mixed'

const SEP = '\u0000'
export const keyOf = (path: Path) => path.join(SEP)

/** Every leaf path under `nodes` (a node with no children is a leaf). */
export function leaves(nodes: TreeNode[], prefix: Path = []): Path[] {
  return nodes.flatMap(n => {
    const p = [...prefix, n.value]
    return n.children.length ? leaves(n.children, p) : [p]
  })
}

/** The tick state of the node at `path`, from the ticked leaves. */
export function stateOf(node: TreeNode, path: Path, ticked: Set<string>): CheckState {
  const under = node.children.length ? leaves(node.children, path) : [path]
  const on = under.filter(p => ticked.has(keyOf(p))).length
  return on === 0 ? 'off' : on === under.length ? 'on' : 'mixed'
}

/** Tick or untick a node: every leaf under it follows. */
export function toggle(node: TreeNode, path: Path, ticked: Set<string>): Set<string> {
  const under = node.children.length ? leaves(node.children, path) : [path]
  const next = new Set(ticked)
  const turnOn = stateOf(node, path, ticked) !== 'on'
  for (const p of under) {
    if (turnOn) next.add(keyOf(p))
    else next.delete(keyOf(p))
  }
  return next
}

/** The shortest paths saying what is ticked; null when everything is (no filter). */
export function toPaths(nodes: TreeNode[], ticked: Set<string>): Path[] | null {
  const all = leaves(nodes)
  if (all.length && all.every(p => ticked.has(keyOf(p)))) return null
  const out: Path[] = []
  const walk = (ns: TreeNode[], prefix: Path) => {
    for (const n of ns) {
      const p = [...prefix, n.value]
      const st = stateOf(n, p, ticked)
      if (st === 'on') out.push(p)
      else if (st === 'mixed') walk(n.children, p)
    }
  }
  walk(nodes, [])
  return out
}

/** The ticked leaves a filter's paths stand for (a branch path ticks its whole branch). */
export function fromPaths(nodes: TreeNode[], paths: Path[] | null | undefined): Set<string> {
  if (!paths?.length) return new Set()
  const keys = paths.map(p => keyOf(p))
  return new Set(leaves(nodes).map(keyOf).filter(k => keys.some(b => k === b || k.startsWith(b + SEP))))
}

/** Search: the paths whose label contains the text, plus every ancestor of
 *  one (to show it and open the way to it). null = no search. */
export function searchTree(nodes: TreeNode[], text: string): { visible: Set<string>; open: Set<string> } | null {
  const q = text.trim().toLocaleLowerCase()
  if (!q) return null
  const visible = new Set<string>()
  const open = new Set<string>()
  const walk = (ns: TreeNode[], prefix: Path): boolean => {
    let any = false
    for (const n of ns) {
      const p = [...prefix, n.value]
      const self = n.value.toLocaleLowerCase().includes(q)
      const below = walk(n.children, p)
      if (self || below) {
        visible.add(keyOf(p))
        any = true
        if (below) open.add(keyOf(p))
        // A matching parent shows its whole branch, so a reader can tick within it.
        if (self) leaves(n.children, p).forEach(l => l.forEach((_, i) => visible.add(keyOf(l.slice(0, i + 1)))))
      }
    }
    return any
  }
  walk(nodes, [])
  return { visible, open }
}

/** "Egypt › Alexandria, US" -- a selection in words, for the filter chip. */
export function describePaths(paths: Path[], max = 3): string {
  const shown = paths.slice(0, max).map(p => p.join(' › '))
  return paths.length > max ? `${shown.join(', ')} +${paths.length - max}` : shown.join(', ')
}
