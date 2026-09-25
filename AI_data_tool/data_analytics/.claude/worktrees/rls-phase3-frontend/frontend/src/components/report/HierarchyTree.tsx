import { useState } from 'react'
import type { HierarchyNode } from '../../types/report'
import { hierarchyApi } from '../../services/api'
import toast from 'react-hot-toast'

interface Props {
  nodes: HierarchyNode[]
  datasetId: number
  onRefresh: () => void
}

const TYPE_ICON: Record<string, string> = {
  folder: '📁', dimension: '🔤', measure: '🔢', date: '📅', text: '📝',
}

export default function HierarchyTree({ nodes, datasetId, onRefresh }: Props) {
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
    await hierarchyApi.delete(datasetId, node.id)
    onRefresh()
  }

  const renderNode = (node: HierarchyNode, depth = 0) => (
    <div key={node.id}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 5,
        padding: `4px ${8 + depth * 14}px`, borderRadius: 5,
        fontSize: 12, cursor: 'default',
      }}
        onMouseEnter={e => (e.currentTarget.style.background = 'var(--surface2)')}
        onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
      >
        <span style={{ fontSize: 13 }}>{TYPE_ICON[node.node_type] ?? '◻'}</span>
        {editId === node.id ? (
          <input value={editName} onChange={e => setEditName(e.target.value)}
            onBlur={() => saveEdit(node)} onKeyDown={e => e.key === 'Enter' && saveEdit(node)}
            style={{ flex: 1, fontSize: 12, padding: '1px 4px' }} autoFocus />
        ) : (
          <span style={{ flex: 1, color: node.node_type === 'folder' ? 'var(--text)' : 'var(--muted)', fontWeight: node.node_type === 'folder' ? 600 : 400 }}>
            {node.name}
          </span>
        )}
        <div style={{ display: 'flex', gap: 2, opacity: 0 }} className="node-actions"
          onMouseEnter={e => { (e.currentTarget as HTMLElement).style.opacity = '1' }}
        >
          <button onClick={() => { setEditId(node.id); setEditName(node.name) }}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--muted)', fontSize: 11, padding: '0 2px' }}>✏</button>
          <button onClick={() => deleteNode(node)}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--danger)', fontSize: 11, padding: '0 2px' }}>×</button>
        </div>
      </div>
      {children(node.id).map(c => renderNode(c, depth + 1))}
    </div>
  )

  if (nodes.length === 0)
    return <p style={{ fontSize: 12, color: 'var(--muted)', textAlign: 'center', marginTop: 16 }}>No hierarchy yet. Click ✦ Auto to generate.</p>

  return <div>{roots.map(n => renderNode(n))}</div>
}
