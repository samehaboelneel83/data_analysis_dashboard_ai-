import { describe, it, expect, vi, beforeEach } from 'vitest'

const api = vi.hoisted(() => ({
  create: vi.fn(), addPage: vi.fn(), updatePage: vi.fn(), addWidget: vi.fn(), updateWidget: vi.fn(),
  update: vi.fn(), get: vi.fn(), addCommonFilter: vi.fn(),
}))
vi.mock('../services/api', () => ({
  reportsApi: api, calcColumnsApi: { save: vi.fn() }, measuresApi: { save: vi.fn() }, datasetsApi: { get: vi.fn() },
}))
import { datasetsApi } from '../services/api'

import { buildPages, filledLayout, sizeFor } from './buildDashboard'

const text = { widget_type: 'text', title: 't', config: { content: 'the answer' } }
const bar = (dim: string) => ({ widget_type: 'bar', title: dim, config: { dimension: dim, measure: 'amount', aggregation: 'sum' } })
const go = (title: string) => ({ widget_type: 'button', title: `Go to: ${title}`,
  config: { label: title, action: 'navigate', actionPageTitle: title, carry_filters: true } })
const plan = (title: string, widgets: unknown[], relations: unknown[] = []) =>
  ({ datasetId: 1, derived: { measures: [], calculated_columns: [] }, proposal: { title, rationale: '', widgets, relations } }) as never

let nextWidget = 100
beforeEach(() => {
  Object.values(api).forEach(f => f.mockReset())
  nextWidget = 100
  api.create.mockResolvedValue({ id: 9, pages: [{ id: 50 }] })
  api.addPage.mockImplementation(async (_r: number, body: { position: number }) => ({ id: 50 + body.position }))
  api.addWidget.mockImplementation(async () => ({ id: nextWidget++ }))
  api.updatePage.mockResolvedValue({})
  api.updateWidget.mockResolvedValue({})
  vi.mocked(datasetsApi.get).mockReset()
})

describe('pages built from the guided setup', () => {
  it('leaves out a widget naming a field that is neither on the dataset nor created for it (B-05)', async () => {
    vi.mocked(datasetsApi.get).mockResolvedValue({ id: 1, columns: [{ name: 'group' }, { name: 'amount' }],
      calculated_columns: [], measures: [] } as never)
    const broken = { widget_type: 'kpi', title: 'Late %', config: { measure: 'late_pct_vs_promised' } }
    await buildPages([plan('Overview', [text, bar('group'), broken])], 'Dash', '')
    const titles = api.addWidget.mock.calls.map(c => (c[2] as { title: string }).title)
    expect(titles).toContain('group')
    expect(titles).not.toContain('Late %')
  })

  it('keeps every widget when the dataset cannot be read for the check (B-05)', async () => {
    vi.mocked(datasetsApi.get).mockRejectedValue(new Error('offline'))
    const other = { widget_type: 'kpi', title: 'Late %', config: { measure: 'late_pct' } }
    await buildPages([plan('Overview', [text, other])], 'Dash', '')
    expect(api.addWidget.mock.calls.map(c => (c[2] as { title: string }).title)).toContain('Late %')
  })

  it('wires each button to the page of the title it names, once every page exists', async () => {
    await buildPages([
      plan('Overview', [text, go('By group'), go('Over time'), bar('group')]),
      plan('By group', [text, go('Overview'), bar('kind')]),
      plan('Over time', [text, go('Overview'), bar('day')]),
    ], 'Dash', '')
    const wired = api.updateWidget.mock.calls.filter(c => (c[3] as { config: { actionPageId?: number } }).config.actionPageId != null)
    // (report, page, widget, {config}) -- the Overview's two buttons point at pages 51 and 52; the others back at 50.
    expect(wired.map(c => [c[1], (c[3] as { config: { actionPageId: number } }).config.actionPageId]))
      .toEqual([[50, 51], [50, 52], [51, 50], [52, 50]])
    expect((wired[0][3] as { config: Record<string, unknown> }).config).toMatchObject({ action: 'navigate', carry_filters: true })
  })

  it('leaves out a button to a page the person did not keep, and keeps click-to-filter pointing at the right charts', async () => {
    // Overview: [text, button→By group, button→Over time, bar, bar]; the person keeps only Overview and By group.
    await buildPages([
      plan('Overview', [text, go('By group'), go('Over time'), bar('group'), bar('kind')], [{ from: 3, to: 4, mode: 'filter' }]),
      plan('By group', [text, go('Overview'), bar('kind')]),
    ], 'Dash', '')
    const made = api.addWidget.mock.calls.filter(c => c[1] === 50).map(c => (c[2] as { widget_type: string; title: string }).title)
    expect(made).toEqual(['t', 'Go to: By group', 'group', 'kind'])                 // no button to "Over time"
    // The relation moved with its charts: widget ids 102 (group) -> 103 (kind).
    const relation = api.updateWidget.mock.calls.find(c => (c[3] as { config: { interaction?: unknown } }).config.interaction)
    expect(relation?.[2]).toBe(102)
    expect((relation?.[3] as { config: { interaction: { actions: { targetId: number }[] } } }).config.interaction.actions)
      .toEqual([{ targetId: 103, mode: 'filter' }])
  })

  it('makes the drill-through page as one, and points the marked charts at it -- only when it was kept', async () => {
    const opens = { ...bar('group'), drill_to: 'drill' }
    const drill = { datasetId: 1, derived: { measures: [], calculated_columns: [] },
      proposal: { title: 'One group', rationale: '', page_type: 'drillthrough', prompt_column: 'group', prompt_label: 'Group',
        widgets: [go('Overview'), bar('day')], relations: [] } } as never
    await buildPages([plan('Overview', [text, opens]), drill], 'Dash', '')
    expect(api.addPage).toHaveBeenCalledWith(9, expect.objectContaining(
      { name: 'One group', page_type: 'drillthrough', prompt_column: 'group', prompt_label: 'Group' }))
    const linked = api.updateWidget.mock.calls.filter(c => (c[3] as { config: { drillthroughPageId?: number } }).config.drillthroughPageId != null)
    expect(linked.map(c => [c[1], c[2], (c[3] as { config: { drillthroughPageId: number } }).config.drillthroughPageId])).toEqual([[50, 101, 51]])

    Object.values(api).forEach(f => f.mockClear()); nextWidget = 100
    await buildPages([plan('Overview', [text, opens])], 'Dash', '')
    expect(api.updateWidget.mock.calls.some(c => (c[3] as { config: { drillthroughPageId?: number } }).config.drillthroughPageId != null)).toBe(false)
  })

  it('gives a button one short tile and does not stretch it or a filter across the row', () => {
    expect(sizeFor(go('x') as never)).toEqual({ w: 3, h: 1 })
    const slots = filledLayout([go('a'), go('b')] as never)
    expect(slots.map(s => s.w)).toEqual([3, 3])
  })
})
