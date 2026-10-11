import type { HierarchyNode } from '../types/report'

export function flattenHierarchy(nodes: HierarchyNode[]): { id: number; label: string; column_name: string; format?: string }[] {
  const byId = new Map(nodes.map(n => [n.id, n]))
  const pathLabel = (n: HierarchyNode): string => {
    const parent = n.parent_id != null ? byId.get(n.parent_id) : undefined
    if (!parent || parent.node_type === 'folder') return n.name
    return `${pathLabel(parent)} ▸ ${n.name}`
  }
  return nodes
    .filter((n): n is HierarchyNode & { column_name: string } => n.node_type !== 'folder' && !!n.column_name)
    .map(n => ({ id: n.id, label: pathLabel(n), column_name: n.column_name, format: n.format }))
}

export function getChildNode(nodes: HierarchyNode[], parentId: number): HierarchyNode | undefined {
  return nodes.find(n => n.parent_id === parentId)
}

export function walkToDepth(nodes: HierarchyNode[], startId: number, steps: number): number {
  let id = startId
  for (let i = 0; i < steps; i++) {
    const child = getChildNode(nodes, id)
    if (!child) break
    id = child.id
  }
  return id
}

/** QA6 B2: a hierarchy folder as the ordered columns a sunburst (or any
 *  hierarchy widget) nests by, outer level first: the folder's first level,
 *  then each level's child. A column is listed once; at most `max` levels. */
export function hierarchyChain(nodes: HierarchyNode[], folderId: number, max = 8): string[] {
  let node = nodes.find(n => n.parent_id === folderId && n.column_name) ?? nodes.find(n => n.id === folderId && n.column_name)
  const out: string[] = []
  const seen = new Set<number>()
  while (node && !seen.has(node.id) && out.length < max) {
    seen.add(node.id)
    if (node.column_name && !out.includes(node.column_name)) out.push(node.column_name)
    node = getChildNode(nodes, node.id)
  }
  return out
}
