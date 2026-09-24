import { useMemo, useState } from 'react'
import ReactFlow, {
  Background, Controls, MarkerType,
  type Edge, type Node,
} from 'reactflow'
import 'reactflow/dist/style.css'
import type { ReviewQueue, ReviewRelationship } from '../../services/api'

/**
 * The join graph, for confirming what inference proposed.
 *
 * SHOW ONE NEIGHBOURHOOD, NOT THE WHOLE SCHEMA
 * ---------------------------------------------
 * Drawing every table at once produced an unreadable hairball on a real source:
 * 66 nodes and 132 edges, illegible at any zoom. The problem is not the layout
 * algorithm — it is that a whole schema is not a thing anyone reads at a glance.
 * Nobody asks "show me all 82 tables"; they ask "what does THIS table join to".
 *
 * So the graph centres on one table and draws only what it touches. Clicking a
 * neighbour re-centres. That turns 66 nodes into six or eight — a picture with
 * an answer in it — and the whole set stays one click away for anyone who wants
 * to squint at it.
 *
 * VIEWS ARE HIDDEN BY DEFAULT
 * ----------------------------
 * Half this source's objects are views (48 of 82), and a view's joins are
 * inherited from the tables underneath it rather than being facts about the
 * schema. Including them doubles the picture while adding nothing a reader can
 * act on. They remain one checkbox away.
 *
 * Edge styling carries provenance, which is the only thing being asked about:
 *   solid   confirmed or declared — settled, drawn for context
 *   dashed  inferred — a proposal awaiting a decision
 */

const CENTRE = { x: 340, y: 230 }

/** The circle has to grow with what is on it.
 *
 *  A fixed radius is fine for four neighbours and unreadable for twenty: the
 *  labels collide and the edge captions land on top of the nodes. Measured on a
 *  real hub table with 20 connections, which is what this spacing is set
 *  against. Two rings past a dozen, so a busy table stays legible instead of
 *  becoming a ring of overlapping boxes. */
function ringFor(count: number, index: number) {
  const perRing = count > 12 ? Math.ceil(count / 2) : count
  const ring = Math.floor(index / perRing)
  const positionInRing = index % perRing
  const angle = (positionInRing / Math.max(perRing, 1)) * Math.PI * 2
  const rx = 320 + ring * 250 + Math.min(count, 20) * 6
  const ry = 190 + ring * 150 + Math.min(count, 20) * 3
  return { angle, rx, ry }
}

function confidenceColor(rel: ReviewRelationship): string {
  if (rel.source !== 'inferred') return '#475569'          // settled: neutral
  if (rel.confidence >= 0.95) return '#16785a'             // high: ready to accept
  if (rel.confidence >= 0.85) return '#a86c15'             // mid: worth a look
  return '#b03a32'                                          // low: probably wrong
}

export interface JoinGraphProps {
  queue: ReviewQueue
  selectedIds: Set<number>
  onToggle: (relationshipId: number) => void
  filter?: string
}

export default function JoinGraph({ queue, selectedIds, onToggle, filter }: JoinGraphProps) {
  const [focusId, setFocusId] = useState<number | null>(null)
  const [showViews, setShowViews] = useState(false)
  const [showAll, setShowAll] = useState(false)

  const model = useMemo(() => {
    const term = (filter ?? '').trim().toLowerCase()
    const byId = new Map(queue.datasets.map(d => [d.id, d]))

    const isDrawable = (id: number) => {
      const object = byId.get(id)
      return !!object && (showViews || object.kind !== 'view')
    }

    let edges = queue.relationships.filter(
      r => isDrawable(r.from_dataset_id) && isDrawable(r.to_dataset_id))

    if (term) {
      edges = edges.filter(r =>
        r.from_dataset?.toLowerCase().includes(term) ||
        r.to_dataset?.toLowerCase().includes(term))
    }

    // How many edges each table takes part in. The busiest one is the most
    // useful place to start reading a schema you have never seen.
    const degree = new Map<number, number>()
    edges.forEach(r => {
      degree.set(r.from_dataset_id, (degree.get(r.from_dataset_id) ?? 0) + 1)
      degree.set(r.to_dataset_id, (degree.get(r.to_dataset_id) ?? 0) + 1)
    })

    const connected = [...degree.keys()]
    const busiest = connected.sort((a, b) => (degree.get(b) ?? 0) - (degree.get(a) ?? 0))[0]
    const centre = focusId != null && degree.has(focusId) ? focusId : busiest

    const focused = !showAll && centre != null
    const visibleEdges = focused
      ? edges.filter(r => r.from_dataset_id === centre || r.to_dataset_id === centre)
      : edges

    const nodeIds = new Set<number>()
    visibleEdges.forEach(r => { nodeIds.add(r.from_dataset_id); nodeIds.add(r.to_dataset_id) })

    return {
      centre, focused, visibleEdges,
      nodeIds: [...nodeIds],
      degree,
      totalConnected: connected.length,
      totalEdges: edges.length,
      byId,
    }
  }, [queue.datasets, queue.relationships, filter, focusId, showViews, showAll])

  const nodes: Node[] = useMemo(() => {
    const { nodeIds, centre, focused, byId, degree } = model
    const others = nodeIds.filter(id => id !== centre)

    return nodeIds.map(id => {
      const object = byId.get(id)!
      const isCentre = id === centre
      // The focused view is a star: the subject in the middle, its neighbours
      // evenly around it. Position is derived, so nothing shifts when an edge
      // is confirmed.
      let position = { x: CENTRE.x, y: CENTRE.y }
      if (!isCentre) {
        if (focused) {
          const index = others.indexOf(id)
          const { angle, rx, ry } = ringFor(others.length, index)
          position = {
            x: CENTRE.x + Math.cos(angle) * rx,
            y: CENTRE.y + Math.sin(angle) * ry,
          }
        } else {
          const index = nodeIds.indexOf(id)
          position = { x: (index % 6) * 230, y: Math.floor(index / 6) * 120 }
        }
      }

      return {
        id: String(id),
        position,
        data: {
          label: `${object.name}${object.kind === 'view' ? ' (view)' : ''}`
            + (isCentre ? '' : `  ·  ${degree.get(id) ?? 0}`),
        },
        style: {
          padding: isCentre ? '10px 16px' : '7px 12px',
          borderRadius: 6,
          border: isCentre ? '2px solid #2d5ba8' : '1px solid #cbd5e1',
          background: object.is_deprecated ? '#f1f5f9' : '#ffffff',
          opacity: object.is_deprecated ? 0.6 : 1,
          fontSize: isCentre ? 13 : 12,
          fontWeight: isCentre ? 700 : 500,
          maxWidth: 220,
          cursor: 'pointer',
        },
      }
    })
  }, [model])

  const edges: Edge[] = useMemo(() => model.visibleEdges.map(r => {
    const selected = selectedIds.has(r.id)
    const color = confidenceColor(r)
    return {
      id: String(r.id),
      source: String(r.from_dataset_id),
      target: String(r.to_dataset_id),
      // Column names are dropped once the star is busy: twenty captions
      // radiating from one node overlap each other and the nodes themselves,
      // and the same text is already on every row below with room to read it.
      label: model.visibleEdges.length <= 8
        ? `${r.from_column} → ${r.to_column}`
        : undefined,
      labelStyle: { fontSize: 10, fill: color },
      labelBgStyle: { fill: '#ffffff', fillOpacity: 0.92 },
      style: {
        stroke: color,
        strokeWidth: selected ? 3 : 1.5,
        strokeDasharray: r.needs_review ? '6 3' : undefined,
      },
      markerEnd: { type: MarkerType.ArrowClosed, color },
    } satisfies Edge
  }), [model, selectedIds])

  if (!queue.datasets.length) {
    return (
      <div style={{ padding: 32, color: '#64748b', fontSize: 14 }}>
        No tables yet. Run a sync to read this connection&apos;s schema.
      </div>
    )
  }

  const centreName = model.centre != null ? model.byId.get(model.centre)?.name : null

  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap',
                    fontSize: 12, color: '#64748b', margin: '0 0 8px' }}>
        {model.centre != null && !showAll && (
          <span>
            Showing <strong style={{ color: '#101822' }}>{centreName}</strong> and what
            it joins to. Click another table to centre on it.
          </span>
        )}
        <span style={{ flex: 1 }} />
        <label style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <input type="checkbox" checked={showViews}
                 onChange={e => setShowViews(e.target.checked)} />
          Include views
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <input type="checkbox" checked={showAll}
                 onChange={e => setShowAll(e.target.checked)} />
          Show every table at once
        </label>
      </div>

      {!nodes.length ? (
        <div style={{ padding: 28, border: '1px solid #e2e8f0', borderRadius: 6,
                      color: '#64748b', fontSize: 13 }}>
          {filter
            ? `No relationships involve a table matching “${filter}”.`
            : showViews
              ? 'No relationships found between these objects yet.'
              : 'No relationships between tables. Tick “Include views” to see '
                + 'relationships involving views.'}
        </div>
      ) : (
        <div style={{ height: 460, border: '1px solid #e2e8f0', borderRadius: 6 }}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodeClick={(_, node) => { setShowAll(false); setFocusId(Number(node.id)) }}
            onEdgeClick={(_, edge) => onToggle(Number(edge.id))}
            fitView
            minZoom={0.2}
            proOptions={{ hideAttribution: false }}
          >
            <Background gap={16} color="#e2e8f0" />
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>
      )}

      <p style={{ fontSize: 12, color: '#64748b', margin: '6px 0 0' }}>
        {showAll
          ? `All ${model.totalConnected} connected objects, ${model.totalEdges} relationships.`
          : `${nodes.length} of ${model.totalConnected} connected objects shown, `
            + `${edges.length} of ${model.totalEdges} relationships.`}
        {' '}Dashed edges are proposals; solid ones are already settled.
        {' '}Click an edge to select it.
      </p>
    </>
  )
}
