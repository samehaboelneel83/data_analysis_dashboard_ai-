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
