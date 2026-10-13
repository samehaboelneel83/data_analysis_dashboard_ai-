import { describe, it, expect } from 'vitest'
import { buildModel, downstream, layout, matches, orderColumns, reach, NO_FILTERS, SHOW, type LEdge } from './model'
import { lineageSvg } from './exportPng'
import type { LineageGraph } from '../../services/api'

const ds = (id: number, over: Partial<LineageGraph['datasets'][number]> = {}): LineageGraph['datasets'][number] => ({
  id, name: `D${id}`, mode: 'import', source_id: 1, joins: [], extraction_kind: 'query', transform: { count: 0, kinds: [] },
  load: { last_refreshed_at: null, strategy: null, cursor_column: null, staleness: 'fresh' }, ...over,
})

describe('lineage model', () => {
  it('spreads a failing refresh to every report downstream, through joins', () => {
    const m = buildModel({ sources: [{ id: 1, name: 'S', type: 'sqlite' }],
      datasets: [ds(1, { health: 'failing' }), ds(2, { joins: [1], source_id: null }), ds(3)],
      reports: [{ id: 1, name: 'R1', dataset_ids: [2] }, { id: 2, name: 'R2', dataset_ids: [3] }] }, 'Uploads')
    expect(m.byKey['ds:1'].issue).toBe('fail')
    expect(m.byKey['rep:1'].issue).toBe('broken')
    expect(m.byKey['rep:2'].issue).toBeNull()
    // A joined dataset is not hung off the uploads node.
    expect(m.byKey['src:upload']).toBeUndefined()
  })

  it('reach: one hop or all, upstream, downstream or both', () => {
    const edges: LEdge[] = [['a', 'b'], ['b', 'c'], ['c', 'd']].map(([from, to]) => ({ from, to, kind: 'reads', bad: false }))
    expect([...reach(edges, 'b', 'both', 'all')!.nodes].sort()).toEqual(['a', 'b', 'c', 'd'])
    expect([...reach(edges, 'b', 'down', 'one')!.nodes].sort()).toEqual(['b', 'c'])
    expect([...reach(edges, 'c', 'up', 'all')!.nodes].sort()).toEqual(['a', 'b', 'c'])
    expect(reach(edges, null)).toBeNull()
    expect([...downstream(edges, 'a')].sort()).toEqual(['b', 'c', 'd'])
  })

  it('orders a column by what feeds it, folds after ten and keeps the focus shown', () => {
    const m = buildModel({ sources: [{ id: 1, name: 'A', type: 'x' }, { id: 2, name: 'B', type: 'x' }],
      datasets: [ds(1, { source_id: 2 }), ds(2, { source_id: 1 }), ...Array.from({ length: 12 }, (_, i) => ds(10 + i))], reports: [] }, 'U')
    const cols = orderColumns(m)
    // D1 is fed by the second source, so it sinks below everything fed by the first.
    expect(cols[1].at(-1)!.key).toBe('ds:1')
    const lay = layout(cols, {}, new Set(['ds:21']), false)
    expect(cols[1].filter(n => lay.visible[n.key])).toHaveLength(SHOW + 1)
    expect(lay.more).toEqual([expect.objectContaining({ col: 1, hidden: 3 })])
    expect(layout(cols, {}, new Set(), true).x(0)).toBeGreaterThan(layout(cols, {}, new Set(), true).x(2))
  })

  it('a dataset-level filter passes the source and reports next to a match', () => {
    const m = buildModel({ sources: [{ id: 1, name: 'S', type: 'x' }], datasets: [ds(1, { mode: 'directquery' }), ds(2)],
      reports: [{ id: 1, name: 'R', dataset_ids: [1] }] }, 'U')
    const f = { ...NO_FILTERS, mode: 'directquery' as const }
    expect(matches(m, m.byKey['ds:1'], f)).toBe(true)
    expect(matches(m, m.byKey['ds:2'], f)).toBe(false)
    expect(matches(m, m.byKey['src:1'], f)).toBe(true)
    expect(matches(m, m.byKey['rep:1'], f)).toBe(true)
  })
})

describe('Export PNG', () => {
  it('draws every visible card, its name and the edges, with the theme colours', () => {
    const m = buildModel({ sources: [{ id: 1, name: 'S & co', type: 'x' }], datasets: [ds(1)], reports: [{ id: 1, name: 'R', dataset_ids: [1] }] }, 'U')
    const cols = orderColumns(m)
    const lay = layout(cols, {}, new Set(), false)
    const svg = lineageSvg(m, cols, lay, [{ d: 'M0 0L1 1', on: true, dim: false, dashed: false, bad: false }], new Set(['ds:1']),
      { bg: '#fff', surface: '#fff', border: '#ddd', edge: '#ccc', accent: '#0a7', danger: '#d00', text: '#111', muted: '#666', font: 'Inter' }, ['Sources 1', 'Datasets 1', 'Reports 1'])
    expect(svg.startsWith('<svg xmlns="http://www.w3.org/2000/svg"')).toBe(true)
    expect(svg).toContain('S &amp; co')
    expect(svg.match(/<rect x=/g)).toHaveLength(3)
    expect(svg).toContain('stroke="#0a7"')
    expect(svg).toContain('Datasets 1')
  })
})
