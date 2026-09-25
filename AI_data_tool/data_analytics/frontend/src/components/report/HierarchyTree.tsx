import { useState } from 'react'
import type { HierarchyNode } from '../../types/report'
import { hierarchyApi } from '../../services/api'
import toast from 'react-hot-toast'
import { useConfirm } from '../ui/ConfirmDialog'
import { Folder, Type, Hash, Calendar, FileText, Square, type LucideIcon } from 'lucide-react'
import { useT } from '../../i18n'

interface Props {
  nodes: HierarchyNode[]
  datasetId: number
  onRefresh: () => void
}

// Line glyphs in the one stroke family, not emoji: the platform emoji drew
// a different coloured picture per OS and outshouted the node names.
const TYPE_ICON: Record<string, LucideIcon> = {
  folder: Folder, dimension: Type, measure: Hash, date: Calendar, text: FileText,
}

export default function HierarchyTree({ nodes, datasetId, onRefresh }: Props) {
  const confirm = useConfirm()
  const t = useT()
  const [editId,   setEditId]   = useState<number | null>(null)
  const [editName, setEditName] = useState('')

  const roots   = nodes.filter(n => n.parent_id === null)
  const children = (id: number) => nodes.filter(n => n.parent_id === id)

  const saveEdit = async (node: HierarchyNode) => {
    await hierarchyApi.update(datasetId, node.id, { name: editName })
    setEditId(null)
    onRefresh()
    toast.success('Renamed')
  }

  const deleteNode = async (node: HierarchyNode) => {
    // destructive: false deliberately. The backend HEALS the chain -- children
    // re-parent to this node's parent (routers/hierarchy.py) -- so nothing is
    // lost, and styling it as a destructive delete would overstate it.
    if (!await confirm({
      title: `Remove the level "${node.name}"?`,
      body: 'Anything under it moves up to take its place. No fields are deleted.',
      confirmLabel: 'Remove level',
      destructive: false,
    })) return
    await hierarchyApi.delete(datasetId, node.id)
    onRefresh()
  }

  // Reclassifying a dimension/measure node also re-parents it under the matching
  // top-level folder (auto-generate creates "Dimensions"/"Measures" root folders —
  // just flipping node_type would leave it visually stuck under the old folder).
  const toggleMeasureCategory = async (node: HierarchyNode) => {
    const nextType = node.node_type === 'measure' ? 'dimension' : 'measure'
    const targetFolder = nodes.find(n => n.node_type === 'folder' && n.name === (nextType === 'measure' ? 'Measures' : 'Dimensions'))
    await hierarchyApi.update(datasetId, node.id, {
      node_type: nextType,
      ...(targetFolder ? { parent_id: targetFolder.id } : {}),
    })
    onRefresh()
  }

  // Swap a level with its parent: node takes the grandparent, the old parent
  // becomes node's child, and node's old child re-parents to the old parent --
  // three PATCHes on the existing endpoint, no new API. Only offered when the
  // parent is itself a LEVEL (not a folder): reordering into a folder header
  // means nothing.
  const moveLevelUp = async (node: HierarchyNode) => {
    const parent = nodes.find(n => n.id === node.parent_id)
    if (!parent || parent.node_type === 'folder') return
    const child = nodes.find(n => n.parent_id === node.id)
    await hierarchyApi.update(datasetId, node.id, { parent_id: parent.parent_id ?? null } as never)
    await hierarchyApi.update(datasetId, parent.id, { parent_id: node.id })
    if (child) await hierarchyApi.update(datasetId, child.id, { parent_id: parent.id })
    onRefresh()
    toast.success(`${node.name} moved up`)
  }

  const setGranularity = async (node: HierarchyNode, format: string) => {
    await hierarchyApi.update(datasetId, node.id, { format })
    onRefresh()
  }

  const renderNode = (node: HierarchyNode, depth = 0) => (
    <div key={node.id}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 5,
        padding: `4px ${8 + depth * 14}px`, borderRadius: 5,
        fontSize: 12, cursor: 'default',
      }}
        onMouseEnter={e => {
          e.currentTarget.style.background = 'var(--surface2)'
          const actions = e.currentTarget.querySelector('.node-actions') as HTMLElement | null
          if (actions) actions.style.opacity = '1'
        }}
        onMouseLeave={e => {
          e.currentTarget.style.background = 'transparent'
          const actions = e.currentTarget.querySelector('.node-actions') as HTMLElement | null
          if (actions) actions.style.opacity = '0'
        }}
      >
        <span aria-hidden style={{ display: 'inline-flex', color: node.node_type === 'folder' ? 'var(--accent)' : 'var(--muted)' }}>
          {(() => { const I = TYPE_ICON[node.node_type] ?? Square; return <I size={14} strokeWidth={1.9} /> })()}
        </span>
        {editId === node.id ? (
          <input value={editName} onChange={e => setEditName(e.target.value)}
            onBlur={() => saveEdit(node)} onKeyDown={e => e.key === 'Enter' && saveEdit(node)}
            style={{ flex: 1, fontSize: 12, padding: '1px 4px' }} autoFocus />
        ) : (
          <span style={{ flex: 1, color: node.node_type === 'folder' ? 'var(--text)' : 'var(--muted)', fontWeight: node.node_type === 'folder' ? 600 : 400 }}>
            {node.name}
          </span>
        )}
        {node.node_type === 'date' && node.format && (
          <select aria-label={`Granularity of ${node.name}`} value={node.format}
            onClick={e => e.stopPropagation()}
            onChange={e => setGranularity(node, e.target.value)}
            style={{ fontSize: 10.5, color: 'var(--muted)', background: 'var(--surface2)',
              border: '1px solid var(--border)', borderRadius: 4 }}>
            {['year', 'quarter', 'month', 'week', 'day'].map(g => <option key={g} value={g}>{g}</option>)}
          </select>
        )}
        <div style={{ display: 'flex', gap: 2, opacity: 0 }} className="node-actions">
          {(node.node_type === 'dimension' || node.node_type === 'measure') && (
            <button onClick={() => toggleMeasureCategory(node)}
              title={node.node_type === 'measure' ? 'Switch to Category' : 'Switch to Measure'}
              aria-label={node.node_type === 'measure' ? 'Switch to Category' : 'Switch to Measure'}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--muted)', fontSize: 11, padding: '0 2px' }}>⇄</button>
          )}
          {(() => {
            const parent = nodes.find(n => n.id === node.parent_id)
            return parent && parent.node_type !== 'folder' ? (
              <button onClick={() => moveLevelUp(node)} title="Move this level up"
                aria-label={`Move ${node.name} up`}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--muted)', fontSize: 11, padding: '0 2px' }}>↑</button>
            ) : null
          })()}
          <button onClick={() => { setEditId(node.id); setEditName(node.name) }}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--muted)', fontSize: 11, padding: '0 2px' }}>✏</button>
          <button onClick={() => deleteNode(node)} title="Remove this level (children re-attach to its parent)"
            aria-label={`Remove ${node.name}`}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--danger)', fontSize: 11, padding: '0 2px' }}>×</button>
        </div>
      </div>
      {children(node.id).map(c => renderNode(c, depth + 1))}
    </div>
  )

  if (nodes.length === 0)
    return <p style={{ fontSize: 12, color: 'var(--muted)', textAlign: 'center', marginTop: 16 }}>{t('hier.none')}</p>

  return <div>{roots.map(n => renderNode(n))}</div>
}
