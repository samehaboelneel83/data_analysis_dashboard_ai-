import { describe, expect, it } from 'vitest'
import type { ReportPage, Widget } from '../types/report'
import { candidateBlockReason, compareCandidates, modelSnapshot, refreshSnapshots, staleSnapshots } from './modelCompare'

const w = (id: number, widget_type: string, config: Record<string, unknown>, page_id = 1, title = `W${id}`): Widget =>
  ({ id, page_id, widget_type, config, title } as unknown as Widget)
const page = (id: number, widgets: Widget[]): ReportPage =>
  ({ id, name: `P${id}`, widgets } as unknown as ReportPage)

describe('modelSnapshot', () => {
  it('reads a linear response from `measure` and the others from `response`', () => {
    expect(modelSnapshot(w(1, 'model_linear', { measure: 'revenue', predictors: ['units'] }))).toMatchObject(
      { id: 1, model: 'linear', response: 'revenue', predictors: ['units'] })
    expect(modelSnapshot(w(2, 'model_logistic', { response: 'churned', predictors: ['units'], event_value: 'yes' }))).toMatchObject(
      { model: 'logistic', response: 'churned', event_value: 'yes' })
    expect(modelSnapshot(w(3, 'model_tree', { response: 'churned', predictors: ['a', 'b'], max_depth: 3 }))).toMatchObject(
      { model: 'tree', predictors: ['a', 'b'], max_depth: 3 })
  })
  it('is null for anything that is not a comparable model', () => {
    expect(modelSnapshot(w(4, 'bar', {}))).toBeNull()
    expect(modelSnapshot(w(5, 'model_cluster', { measures: ['a', 'b'] }))).toBeNull()
  })
})

describe('compareCandidates', () => {
  it('lists every comparable model but itself, its own page first', () => {
    const self = w(9, 'model_compare', {}, 2)
    const pages = [page(1, [w(1, 'model_linear', { measure: 'r' }, 1)]),
                   page(2, [self, w(2, 'model_tree', { response: 'r' }, 2), w(3, 'bar', {}, 2)])]
    expect(compareCandidates(pages, self).map(c => c.widget.id)).toEqual([2, 1])
  })
})

describe('candidateBlockReason', () => {
  const a = modelSnapshot(w(1, 'model_linear', { measure: 'revenue' }))!
  const b = modelSnapshot(w(2, 'model_tree', { response: 'churned' }))!
  const c = modelSnapshot(w(3, 'model_tree', {}))!
  it('says why a model of another response cannot join', () => {
    expect(candidateBlockReason(b, [a])).toBe('predicts churned, the others predict revenue')
  })
  it('says a model with no response cannot join', () => {
    expect(candidateBlockReason(c, [])).toBe('has no response yet')
  })
  it('says why a model holding out another partition cannot join', () => {
    const p1 = modelSnapshot(w(4, 'model_linear', { measure: 'revenue', partition: '_Partition_' }))!
    const p2 = modelSnapshot(w(5, 'model_linear', { measure: 'revenue', partition: 'other' }))!
    expect(candidateBlockReason(p2, [p1])).toBe('holds out other, the others hold out _Partition_')
  })
  it('lets a first pick or a same-response model join', () => {
    expect(candidateBlockReason(a, [])).toBeNull()
    expect(candidateBlockReason(a, [a])).toBeNull()
  })
})

describe('stale snapshots', () => {
  it('names snapshots whose model changed or was deleted, and refreshes them', () => {
    const stored = [modelSnapshot(w(1, 'model_linear', { measure: 'r', measures: ['a'] }, 1, 'Lin'))!,
                    modelSnapshot(w(2, 'model_linear', { measure: 'r', measures: ['b'] }, 1, 'Gone'))!]
    const pages = [page(1, [w(1, 'model_linear', { measure: 'r', measures: ['a', 'c'] }, 1, 'Lin')])]
    expect(staleSnapshots(stored, pages)).toEqual(['Lin', 'Gone'])
    const fresh = refreshSnapshots(stored, pages)
    expect(fresh).toHaveLength(1)
    expect(fresh[0].predictors).toEqual(['a', 'c'])
    expect(staleSnapshots(fresh, pages)).toEqual([])
  })
  it('does not call a snapshot stale because its keys came back reordered', () => {
    const live = w(1, 'model_linear', { measure: 'r', predictors: ['a'] }, 1, 'Lin')
    const snap = modelSnapshot(live)!
    const reordered = Object.fromEntries(Object.entries(snap).reverse()) as typeof snap
    expect(staleSnapshots([reordered], [page(1, [live])])).toEqual([])
  })
})
