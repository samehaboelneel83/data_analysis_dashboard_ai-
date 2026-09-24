import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import ReviewPane, { reviewReport } from './ReviewPane'
import type { Report } from '../../types/report'

const report = (widgets: object[]): Report => ({
  id: 1, name: 'R', dataset_id: 1, additional_dataset_ids: [],
  pages: [{ id: 10, report_id: 1, name: 'P1', page_type: 'normal', position: 0, widgets }],
} as never)

// A FINISHED bar by default (a dimension set): an unfinished one is itself a
// review error now (Phase 7.4), and each test adds only the problem it is about.
const w = (over: { config?: object } & Record<string, unknown>) => ({
  id: 1, page_id: 10, widget_type: 'bar', title: 'Titled', layout: { x: 0, y: 0, w: 6, h: 4 },
  ...over,
  config: { dimension: 'region', ...(over.config ?? {}) },
})

vi.mock('../../services/api', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  reviewApi: { settings: vi.fn().mockResolvedValue({ publish_gate: false }), evaluate: vi.fn(), setGate: vi.fn(), review: vi.fn() },
}))

describe('reviewReport', () => {
  it('flags an untitled chart with no alt text as an accessibility error', () => {
    const f = reviewReport(report([w({ title: '', config: {} })]), {})
    expect(f.some(x => x.severity === 'error' && /screen reader/.test(x.message))).toBe(true)
  })

  it('accepts alt text as a substitute for a title', () => {
    const f = reviewReport(report([w({ title: '', config: { alt_text: 'Revenue by region' } })]), {})
    expect(f.filter(x => x.severity === 'error')).toEqual([])
  })

  it('flags a widget that returned no rows, using the runtime stats', () => {
    const f = reviewReport(report([w({})]), { 1: { durationMs: 50, rowCount: 0 } })
    expect(f.some(x => /no rows/.test(x.message))).toBe(true)
  })

  it('flags broken display rules — the fail-open failure an author cannot see', () => {
    const f = reviewReport(report([w({})]),
      { 1: { durationMs: 50, rowCount: 5, ruleErrors: [{ message: 'x' }] } })
    expect(f.some(x => /fail open/.test(x.message))).toBe(true)
  })

  it('flags slow widgets and crowded pages', () => {
    const many = Array.from({ length: 15 }, (_, i) => w({ id: i + 1, title: `W${i}` }))
    const f = reviewReport(report(many), { 1: { durationMs: 3500, rowCount: 5 } })
    expect(f.some(x => /took 3.5s/.test(x.message))).toBe(true)
    expect(f.some(x => /15 widgets/.test(x.message))).toBe(true)
  })

  it('ranks errors before warnings before info', () => {
    const f = reviewReport(
      report([w({ id: 1, title: '' }), w({ id: 2 })]),
      { 2: { durationMs: 3000, rowCount: 5 } })
    const severities = f.map(x => x.severity)
    expect(severities).toEqual([...severities].sort(
      (a, b) => ({ error: 0, warning: 1, info: 2 }[a] - { error: 0, warning: 1, info: 2 }[b])))
  })

  it('reports a clean bill only when everything actually checks out', () => {
    const f = reviewReport(report([w({})]), { 1: { durationMs: 100, rowCount: 5 } })
    expect(f).toEqual([])
  })
})

/**
 * Reviewing the report as its READER receives it.
 *
 * Every check above is about the report an author is looking at. This group is
 * about the interaction wiring, where the failure mode is different in kind:
 * a dead edge does not error, does not log and looks correct in the builder —
 * the author clicks, something filters, and they move on. It is only wrong for
 * the person who opens the link, and only in the cases the author did not try.
 *
 * Each finding below corresponds to a branch of `getFiltersFor` /
 * `canBroadcast` in CrossFilterContext that silently drops a selection. SAS has
 * no equivalent check; it has the same failure modes.
 */
describe('reviewReport: interaction wiring', () => {
  /** Two pages, so cross-page routing can be expressed. */
  const twoPageReport = (p1: object[], p2: object[] = [], mode?: string): Report => ({
    id: 1, name: 'R', dataset_id: 1, additional_dataset_ids: [],
    pages: [
      { id: 10, report_id: 1, name: 'P1', page_type: 'normal', position: 0, widgets: p1,
        ...(mode ? { mobile_layout: { interaction_mode: mode } } : {}) },
      { id: 20, report_id: 1, name: 'P2', page_type: 'normal', position: 1, widgets: p2 },
    ],
  } as never)

  const wi = (id: number, interaction?: object, over: object = {}) => ({
    id, page_id: 10, widget_type: 'bar', title: `W${id}`,
    config: interaction ? { dimension: 'region', interaction } : { dimension: 'region' }, layout: { x: 0, y: 0, w: 6, h: 4 }, ...over,
  })

  it('flags an action aimed at a widget that no longer exists', () => {
    // Deleting the target leaves the edge behind. `actionReaches` walks to an
    // id nothing matches and returns false — for ever, silently.
    const f = reviewReport(twoPageReport([
      wi(1, { broadcasts: true, receives: true, actions: [{ targetId: 99, mode: 'filter' }] }),
      wi(2),
    ]), {})
    expect(f.some(x => x.severity === 'error' && /no longer exists|deleted/.test(x.message))).toBe(true)
  })

  it('flags an action aimed at another page, which page scoping drops', () => {
    // getFiltersFor keeps a filter only when `f.sourcePageId === currentPageId`
    // or the SOURCE is marked syncAllPages. Neither holds here.
    const f = reviewReport(twoPageReport(
      [wi(1, { broadcasts: true, receives: true, actions: [{ targetId: 5, mode: 'filter' }] })],
      [{ id: 5, page_id: 20, widget_type: 'bar', title: 'Far', config: {}, layout: { x: 0, y: 0, w: 6, h: 4 } }],
    ), {})
    expect(f.some(x => x.severity === 'error' && /another page/.test(x.message))).toBe(true)
  })

  it('accepts a cross-page action when the source syncs across pages', () => {
    const f = reviewReport(twoPageReport(
      [wi(1, { broadcasts: true, receives: true, syncAllPages: true, actions: [{ targetId: 5, mode: 'filter' }] })],
      [{ id: 5, page_id: 20, widget_type: 'bar', title: 'Far', config: {}, layout: { x: 0, y: 0, w: 6, h: 4 } }],
    ), {})
    expect(f.some(x => /another page/.test(x.message))).toBe(false)
  })

  it('flags an action aimed at a widget that refuses to receive', () => {
    const f = reviewReport(twoPageReport([
      wi(1, { broadcasts: true, receives: true, actions: [{ targetId: 2, mode: 'filter' }] }),
      wi(2, { broadcasts: true, receives: false }),
    ]), {})
    expect(f.some(x => /refuses|does not receive|set not to receive/.test(x.message))).toBe(true)
  })

  it("flags per-pair actions on a page whose automatic mode ignores them", () => {
    // Documented as mutually exclusive, and the code agrees: the `acts` branch
    // of getFiltersFor is guarded by `pageMode === 'manual'`. Under an
    // automatic mode the author's careful wiring is simply not consulted.
    const f = reviewReport(twoPageReport([
      wi(1, { broadcasts: true, receives: true, actions: [{ targetId: 2, mode: 'filter' }] }),
      wi(2),
    ], [], 'twoway'), {})
    expect(f.some(x => /two-way|automatic/.test(x.message) && /action/.test(x.message))).toBe(true)
  })

  it('flags a page where no widget will accept a selection', () => {
    // Every widget opted out of receiving, so a reader can click all day and
    // nothing on the page will ever change.
    const f = reviewReport(twoPageReport([
      wi(1, { broadcasts: true, receives: false }),
      wi(2, { broadcasts: true, receives: false }),
    ]), {})
    const dead = f.find(x => /nothing on this page will react/i.test(x.message))
    expect(dead).toBeDefined()
    expect(dead!.message).toMatch(/"P1"/)        // names the page, not just the problem
    expect(dead!.widgetId).toBeUndefined()       // a page-level finding, not a widget one
  })

  it('stays quiet on a page that is wired correctly', () => {
    const f = reviewReport(twoPageReport([
      wi(1, { broadcasts: true, receives: true, actions: [{ targetId: 2, mode: 'filter' }] }),
      wi(2, { broadcasts: false, receives: true }),
    ]), {})
    expect(f).toEqual([])
  })

  it('says nothing about a report that never configured interactions at all', () => {
    // The defaults broadcast and receive, so an author who never opened the
    // pane has nothing wrong. A review that nags about untouched defaults
    // trains people to ignore it.
    const f = reviewReport(twoPageReport([wi(1), wi(2)]), {})
    expect(f).toEqual([])
  })
})

describe('ReviewPane badges', () => {
  const wiringReport = (): Report => ({
    id: 1, name: 'R', dataset_id: 1, additional_dataset_ids: [],
    pages: [{ id: 10, report_id: 1, name: 'P1', page_type: 'normal', position: 0, widgets: [
      { id: 1, page_id: 10, widget_type: 'bar', title: 'Sales', layout: { x: 0, y: 0, w: 6, h: 4 },
        config: { interaction: { broadcasts: true, receives: true, actions: [{ targetId: 99, mode: 'filter' }] } } },
    ] }],
  } as never)

  it('does not label a wiring error as an accessibility one', () => {
    // The badge was keyed on severity alone, and every `error` read "A11Y".
    // A broken action is an error, and calling it an accessibility problem
    // sends the author looking in the wrong place.
    render(<ReviewPane report={wiringReport()} perfStats={{}} onSelectWidget={vi.fn()} />)
    expect(screen.getByText(/no longer exists/)).toBeInTheDocument()
    expect(screen.queryByText('A11Y')).not.toBeInTheDocument()
  })

  it('still labels an accessibility error A11Y', () => {
    const r = {
      id: 1, name: 'R', dataset_id: 1, additional_dataset_ids: [],
      pages: [{ id: 10, report_id: 1, name: 'P1', page_type: 'normal', position: 0, widgets: [
        { id: 1, page_id: 10, widget_type: 'bar', title: '', config: {}, layout: { x: 0, y: 0, w: 6, h: 4 } },
      ] }],
    } as never as Report
    render(<ReviewPane report={r} perfStats={{}} onSelectWidget={vi.fn()} />)
    expect(screen.getByText('A11Y')).toBeInTheDocument()
  })
})

describe('reviewReport cross-dataset clicks (Phase 6.1)', () => {
  const two = [
    w({ id: 1, title: 'Sales by country', config: { dimension: 'country' } }),
    w({ id: 2, title: 'Shipping days', config: { dataset_id: 2, dimension: 'carrier' } }),
  ]
  const datasets = { 1: { name: 'Sales', columns: [{ name: 'country' }] }, 2: { name: 'Shipments', columns: [{ name: 'cust_country' }, { name: 'carrier' }] } }

  it('names a click that cannot reach a widget on another dataset', () => {
    const f = reviewReport(report(two), {}, { datasets, relationships: [] })
    const hit = f.find(x => /will not filter widgets on Shipments/.test(x.message))
    expect(hit?.severity).toBe('info')
    expect(hit?.widgetId).toBe(1)
  })

  it('is quiet once a mapping connects the columns', () => {
    const f = reviewReport(report(two), {}, { datasets, relationships: [
      { from_dataset_id: 1, from_column: 'country', to_dataset_id: 2, to_column: 'cust_country' }] })
    expect(f.some(x => /Clicks on "Sales by country"/.test(x.message))).toBe(false)
  })

  it('is quiet when the other dataset shares the column name', () => {
    const f = reviewReport(report(two), {}, { datasets: { ...datasets, 2: { name: 'Shipments', columns: [{ name: 'country' }] } }, relationships: [] })
    expect(f.some(x => /Clicks on "Sales by country"/.test(x.message))).toBe(false)
  })
})


describe('report quality as CI (Phase 7.4)', () => {
  it('flags an unfinished widget as an error, like the server gate does', () => {
    const f = reviewReport(report([{ id: 3, page_id: 10, widget_type: 'bar', title: 'Half done', config: {},
      layout: { x: 0, y: 0, w: 6, h: 4 } }]), {})
    expect(f.some(x => x.severity === 'error' && /"Half done" is unfinished/.test(x.message))).toBe(true)
  })

  it('evaluates performance and states the publish gate', async () => {
    const { reviewApi } = await import('../../services/api')
    vi.mocked(reviewApi.settings).mockResolvedValue({ publish_gate: true })
    vi.mocked(reviewApi.evaluate).mockResolvedValue({
      widgets: [{ widget_id: 1, title: 'Titled', page: 'P1', widget_type: 'bar', dataset_id: 1, ms: 2600, rows: 800,
                  error: null, advice: ['Slow for every reader: filter it to fewer rows.'] }],
      total_ms: 2600, slow_ms: 2000, slow: 1, measured_at: 'now',
      history: { '1': { runs: 40, median_ms: 120, p95_ms: 900, cache_hit_share: 0.5 } },
    })
    render(<ReviewPane report={report([w({ title: '', config: {} })])} perfStats={{}} onSelectWidget={vi.fn()} canEdit isAdmin />)
    expect((await screen.findByTestId('publish-gate')).textContent).toContain('publishing is blocked until the 1 error above is fixed')
    fireEvent.click(screen.getByRole('button', { name: /Evaluate performance/ }))
    const perf = await screen.findByTestId('perf-eval')
    expect(perf.textContent).toContain('2,600 ms')
    expect(perf.textContent).toContain('median 120 ms, p95 900 ms, 50% from cache')
    expect(perf.textContent).toContain('Slow for every reader')
  })
})
