import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react'
import SuggestionsPane, { suggestWidgets } from './SuggestionsPane'
import { suggestApi, widgetDataApi } from '../../services/api'
import type { DatasetColumn } from '../../services/api'

vi.mock('../../services/api', () => ({
  suggestApi: { forReport: vi.fn(), feedback: vi.fn().mockResolvedValue({ dismissed: [], types: {}, org_types: {} }),
                sendFeedback: vi.fn().mockResolvedValue({ dismissed: [], types: {}, org_types: {} }) },
  widgetDataApi: { query: vi.fn().mockResolvedValue({ rows: [{ name: 'A', value: 8 }, { name: 'B', value: 2 }] }) },
}))

// No `stats` on any of them: that field is `{}` on every column the
// application actually produces, so a fixture that fills it tests nothing.
// Cardinality lives on the analysis profile below, where it really arrives.
const cols = [
  { id: 1, name: 'region', dtype: 'categorical', missing_pct: 0, stats: {} },
  { id: 2, name: 'date', dtype: 'datetime', missing_pct: 0, stats: {} },
  { id: 3, name: 'revenue', dtype: 'numeric', missing_pct: 0, stats: {} },
  { id: 4, name: 'cost', dtype: 'numeric', missing_pct: 0, stats: {} },
] as unknown as DatasetColumn[]

const analysis = {
  numeric: { correlation: { revenue: { cost: 0.9 }, cost: { revenue: 0.9 } } },
  categorical: { columns: { region: { n_unique: 4 } } },
}

describe('suggestWidgets', () => {
  it('suggests by dtype and cardinality: pie for few values, line for dates, scatter for correlation', () => {
    const s = suggestWidgets(cols, analysis)
    const types = s.map(x => x.widget_type)
    expect(types).toContain('pie')        // region has 4 uniques in the profile
    expect(types).toContain('line')       // date trend
    const scatter = suggestWidgets(cols, analysis, 1).concat(s).find(x => x.widget_type === 'scatter')
    expect(scatter?.reason).toMatch(/r = 0.90/)
  })

  it('is empty without numeric columns', () => {
    expect(suggestWidgets([cols[0]] as never, null)).toEqual([])
  })

  it('rotates deterministically for More', () => {
    const a = suggestWidgets(cols, analysis, 0)
    const b = suggestWidgets(cols, analysis, 1)
    expect(a.map(x => x.title)).not.toEqual(b.map(x => x.title))
  })
})

beforeEach(() => { localStorage.clear() })

const addButtons = () => screen.getAllByRole('button', { name: /^Add “/ })

describe('SuggestionsPane', () => {
  it('adds a suggestion on click, and then says so instead of offering it again', () => {
    const onAdd = vi.fn()
    render(<SuggestionsPane columns={cols} analysis={analysis} onAdd={onAdd} />)
    const before = addButtons().length
    fireEvent.click(addButtons()[0])
    expect(onAdd).toHaveBeenCalled()
    expect(onAdd.mock.calls[0][0].config).toHaveProperty('aggregation')
    expect(screen.getByText('Added')).toBeInTheDocument()
    expect(addButtons()).toHaveLength(before - 1)
  })

  it('"Add all shown" hands the filtered ideas over at once, and each then says Added (F-15)', async () => {
    const onAddMany = vi.fn().mockResolvedValue(true)
    render(<SuggestionsPane columns={cols} analysis={analysis} onAdd={vi.fn()} onAddMany={onAddMany} />)
    fireEvent.click(screen.getByRole('button', { name: /^Trend over time/ }))
    const shown = addButtons().length
    fireEvent.click(screen.getByRole('button', { name: `Add all shown (${shown})` }))
    await waitFor(() => expect(onAddMany).toHaveBeenCalled())
    const list = onAddMany.mock.calls[0][0]
    expect(list).toHaveLength(shown)
    await waitFor(() => expect(screen.queryAllByRole('button', { name: /^Add “/ })).toHaveLength(0))
    expect(screen.getAllByText('Added')).toHaveLength(shown)
    expect(screen.queryByRole('button', { name: /Add all shown/ })).toBeNull()
  })

  it('nothing is marked added when adding them all was cancelled (F-15)', async () => {
    const onAddMany = vi.fn().mockResolvedValue(false)
    render(<SuggestionsPane columns={cols} analysis={analysis} onAdd={vi.fn()} onAddMany={onAddMany} />)
    const before = addButtons().length
    fireEvent.click(screen.getByRole('button', { name: `Add all shown (${before})` }))
    await waitFor(() => expect(onAddMany).toHaveBeenCalled())
    expect(addButtons()).toHaveLength(before)
  })

  it('groups ideas under headings, with chips that filter them', () => {
    render(<SuggestionsPane columns={cols} analysis={analysis} onAdd={vi.fn()} />)
    expect(screen.getByRole('heading', { name: /Trend over time/ })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /^Trend over time/ }))
    expect(screen.queryByRole('heading', { name: /Compare/ })).toBeNull()
    expect(screen.getByRole('heading', { name: /Trend over time/ })).toBeInTheDocument()
  })
})

describe('reading each idea from its own data', () => {
  beforeEach(() => { vi.mocked(suggestApi.forReport).mockReset() })

  it('leads with the finding, not the column names', async () => {
    render(<SuggestionsPane columns={cols} analysis={null} onAdd={vi.fn()} datasetId={10} />)
    // region × revenue: A holds 8 of 10.
    expect((await screen.findAllByText('A has 80% of revenue')).length).toBeGreaterThan(0)
    expect(screen.getAllByText('Revenue · by region').length).toBeGreaterThan(0)
    expect(screen.getAllByTestId('suggestion-thumb').length).toBeGreaterThan(0)
  })

  it('opens the full live chart, with the numbers behind the headline, on click', async () => {
    const onAdd = vi.fn()
    render(<SuggestionsPane columns={cols} analysis={null} onAdd={onAdd} datasetId={10} />)
    const title = (await screen.findAllByText('A has 80% of revenue'))[0]
    expect(screen.queryByTestId('suggestion-preview')).toBeNull()
    fireEvent.click(title.closest('button')!)
    const preview = screen.getByTestId('suggestion-preview')
    expect(preview.style.pointerEvents).toBe('none')
    expect(preview.getAttribute('aria-hidden')).toBe('true')
    expect(screen.getByText(/^A accounts for 8 of 10 \(80%\)/)).toBeInTheDocument()
    // What is added is what was previewed: axes named in words.
    fireEvent.click(screen.getByRole('button', { name: 'Add to page' }))
    expect(onAdd.mock.calls[0][0].config).toMatchObject({ x_axis_label: 'Region', y_axis_label: 'Total revenue' })
  })

  it('folds away an idea that is already a chart on the page, with a way to it', () => {
    const pageWidgets = [{ id: 9, page_id: 1, widget_type: 'donut', title: 'Revenue split',
      config: { dimension: 'region', measure: 'revenue' }, layout: { x: 0, y: 0, w: 4, h: 4 }, created_at: '' }] as never
    render(<SuggestionsPane columns={cols} analysis={null} onAdd={vi.fn()} pageWidgets={pageWidgets} />)
    const toggle = screen.getByRole('button', { name: /already on this page/ })
    expect(screen.queryByText(/On this page as/)).toBeNull()
    fireEvent.click(toggle)
    expect(screen.getByText('On this page as “Revenue split”')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Go to chart/ })).toBeInTheDocument()
  })

  it('"Not useful" hides an idea, and it stays hidden next time', async () => {
    vi.mocked(suggestApi.forReport).mockResolvedValue([])
    const { unmount } = render(<SuggestionsPane columns={cols} analysis={null} onAdd={vi.fn()} reportId={3} datasetId={10} />)
    const title = (await screen.findAllByText('A has 80% of revenue'))[0]
    const count = addButtons().length
    fireEvent.click(title.closest('button')!)
    fireEvent.click(screen.getByRole('button', { name: /Not useful/ }))
    expect(addButtons()).toHaveLength(count - 1)
    unmount()
    render(<SuggestionsPane columns={cols} analysis={null} onAdd={vi.fn()} reportId={3} datasetId={10} />)
    await waitFor(() => expect(vi.mocked(widgetDataApi.query)).toHaveBeenCalled())
    expect(addButtons()).toHaveLength(count - 1)
  })
})

describe('insight-driven suggestions', () => {
  beforeEach(() => { vi.mocked(suggestApi.forReport).mockReset() })
  it('leads with server suggestions, marking description-aligned ones', async () => {
    vi.mocked(suggestApi.forReport).mockResolvedValue([
      { widget_type: 'bar', title: 'A carries 80% of revenue',
        reason: 'A carries 80% of revenue — matches revenue in the report description',
        config: { dimension: 'region', measure: 'revenue', aggregation: 'sum' },
        score: 1.1, kind: 'standout', aligned: true },
    ])
    const onAdd = vi.fn()
    render(<SuggestionsPane columns={cols} analysis={null} onAdd={onAdd} reportId={7} />)

    const item = await screen.findByTestId('insight-suggestion-standout')
    expect(item.querySelector('[title="Matches the report description"]')).not.toBeNull()
    // First in its section: the engine's ranked findings lead.
    const section = item.closest('section')!
    expect(within(section).getAllByRole('listitem')[0]).toBe(item)

    fireEvent.click(within(item).getByRole('button', { name: /^Add “/ }))
    expect(onAdd).toHaveBeenCalledWith(expect.objectContaining({
      widget_type: 'bar',
      config: expect.objectContaining({ dimension: 'region', measure: 'revenue', aggregation: 'sum' }),
    }))
  })

  it('shows what the chart actually shows, read back from its drawn result', async () => {
    vi.mocked(suggestApi.forReport).mockResolvedValue([
      { widget_type: 'bar', title: 'Pay by gender', reason: 'Is there a pay gap?',
        config: { dimension: 'gender', measure: 'salary', aggregation: 'avg' },
        score: 9, kind: 'baseline', aligned: false,
        takeaway: 'Average salary is essentially the same for every gender (71,964–72,045).' },
    ])
    render(<SuggestionsPane columns={cols} analysis={null} onAdd={vi.fn()} reportId={7} />)
    const item = await screen.findByTestId('insight-suggestion-baseline')
    expect(item.textContent).toContain('essentially the same for every gender')
    fireEvent.click(within(item).getAllByRole('button')[0])
    expect(within(item).getByTestId('suggestion-takeaway').textContent).toContain('Data shows:')
  })

  it('renders only heuristics when no reportId is given', () => {
    render(<SuggestionsPane columns={cols} analysis={null} onAdd={vi.fn()} />)
    expect(suggestApi.forReport).not.toHaveBeenCalled()
  })
})

describe('without data to read', () => {
  it('draws no live chart without a datasetId, even when opened', () => {
    vi.mocked(suggestApi.forReport).mockReset()
    render(<SuggestionsPane columns={cols} analysis={null} onAdd={vi.fn()} />)
    fireEvent.click(screen.getAllByRole('button', { expanded: false })[0])
    expect(screen.queryByTestId('suggestion-preview')).toBeNull()
  })
})

describe('cardinality comes from the profile, not from a field nothing writes', () => {
  /**
   * The pie rule had never fired in production.
   *
   * `card()` read `DatasetColumn.stats.unique`. `stats` is a declared field
   * that **nothing in the application ever writes** — `stats={}` is passed
   * literally at all three creation sites, and 0 of 506 columns in the dev
   * database carry any. So `card()` was always NaN, `low` was always false, and
   * every categorical column got a bar. Never a pie, for any dataset, ever.
   *
   * The fixture at the top of this file is what hid it: `stats: { unique: 4 }`
   * invents data the app does not produce, so the test asserted a rule that
   * only ran here. This is the third place in this codebase where a fabricated
   * fixture certified a dead branch.
   *
   * The cardinality it needs already arrives: the analysis profile carries
   * `categorical.columns[name].n_unique`, and this function is already handed
   * that profile.
   */
  const realCols = [
    { id: 1, name: 'region', dtype: 'categorical', missing_pct: 0, stats: {} },
    { id: 2, name: 'product', dtype: 'categorical', missing_pct: 0, stats: {} },
    { id: 3, name: 'revenue', dtype: 'numeric', missing_pct: 0, stats: {} },
  ] as unknown as DatasetColumn[]

  const profile = {
    numeric: {},
    categorical: { columns: {
      region: { n_unique: 4 },      // few values -> parts of a whole
      product: { n_unique: 40 },    // too many to read as a pie
    } },
  }

  it('suggests a pie for a low-cardinality column', () => {
    const types = suggestWidgets(realCols, profile).map(x => x.widget_type)
    expect(types).toContain('pie')
  })

  it('still suggests a bar for a high-cardinality one', () => {
    // A forty-slice pie is unreadable; the rule has to cut both ways or it is
    // just a different constant.
    const s = suggestWidgets(realCols, profile)
    expect(s.find(x => x.title.includes('product'))?.widget_type).toBe('bar')
    expect(s.find(x => x.title.includes('region'))?.widget_type).toBe('pie')
  })

  it('falls back to a bar when the profile has no cardinality', () => {
    // Unknown is not "few". A bar is readable at any width; a pie is not.
    const types = suggestWidgets(realCols, { numeric: {} }).map(x => x.widget_type)
    expect(types).not.toContain('pie')
  })

  it('does not fall over when there is no profile at all', () => {
    expect(() => suggestWidgets(realCols, null)).not.toThrow()
  })
})

describe('suggestWidgets on an HR table (evaluation 2026-10-01)', () => {
  const hr = [
    { id: 1, name: 'emp_no', dtype: 'numeric', missing_pct: 0, stats: {} },
    { id: 2, name: 'gender', dtype: 'categorical', missing_pct: 0, stats: {} },
    { id: 3, name: 'dept_name', dtype: 'categorical', missing_pct: 0, stats: {} },
    { id: 4, name: 'hire_date', dtype: 'datetime', missing_pct: 0, stats: {} },
    { id: 5, name: 'salary', dtype: 'numeric', missing_pct: 0, stats: {} },
  ] as unknown as DatasetColumn[]
  const prof = { numeric: {}, categorical: { columns: { gender: { n_unique: 2 }, dept_name: { n_unique: 9 } } } }
  // The dataset as the server hands it over: each number classified once.
  const hrMeta = { salary: { number: 'level' as const } }
  const all = [0, 1, 2, 3].flatMap(seed => suggestWidgets(hr, prof, seed, hrMeta))

  it('never sums or averages an identifier', () => {
    for (const s of all) {
      if (s.config.measure === 'emp_no') expect(s.config.aggregation).toBe('countd')
    }
    expect(all.some(s => /^Emp no by/i.test(s.title))).toBe(false)
  })

  it('leads with head-counts, and averages salary', () => {
    const first = suggestWidgets(hr, prof, 0, hrMeta)[0]
    expect(first.config).toMatchObject({ measure: 'emp_no', aggregation: 'countd' })
    const pay = all.find(s => s.config.measure === 'salary' && s.config.dimension === 'gender')
    expect(pay?.config.aggregation).toBe('avg')
    expect(pay?.widget_type).toBe('bar')            // an average has no whole for a pie
  })

  it('respects a recorded role over the name', () => {
    const s = suggestWidgets(hr, prof, 0, { salary: { aggregation: 'sum' } })
    const pay = [0, 1, 2].flatMap(seed => suggestWidgets(hr, prof, seed, { salary: { aggregation: 'sum' } }))
      .find(x => x.config.measure === 'salary' && x.config.dimension === 'dept_name')
    expect(s.length).toBeGreaterThan(0)
    expect(pay?.config.aggregation).toBe('sum')
  })
})

describe('suggestWidgets reads each column\'s stored classification', () => {
  const cols = [
    { id: 1, name: 'priority', dtype: 'categorical', missing_pct: 0, stats: {} },
    { id: 2, name: 'region', dtype: 'categorical', missing_pct: 0, stats: {} },
    { id: 3, name: 'is_late', dtype: 'categorical', missing_pct: 0, stats: {} },
    { id: 4, name: 'val2', dtype: 'numeric', missing_pct: 0, stats: {} },
    { id: 5, name: 'ref9', dtype: 'numeric', missing_pct: 0, stats: {} },
  ] as unknown as DatasetColumn[]
  const prof = { numeric: {}, categorical: { columns: { priority: { n_unique: 3 }, region: { n_unique: 4 }, is_late: { n_unique: 2 } } } }
  const meta = {
    priority: { level: 'ordinal' as const, order: ['Low', 'Medium', 'High'] },
    is_late: { outcome: true },
    val2: { number: 'score' as const },
    ref9: { number: 'code' as const },
  }
  const all = [0, 1, 2, 3, 4].flatMap(seed => suggestWidgets(cols, prof, seed, meta))

  it('draws an ordered category in its order, as bars', () => {
    const byPriority = all.filter(s => s.config.dimension === 'priority' && !s.config.dimension2)
    expect(byPriority.length).toBeGreaterThan(0)
    for (const s of byPriority) {
      expect(s.widget_type).toBe('bar')
      expect(s.config).toMatchObject({ sort_by: 'order', category_order: ['Low', 'Medium', 'High'] })
    }
  })

  it('offers the share with an outcome per group, never the outcome as its own breakdown', () => {
    const share = all.find(s => s.config.dimension2 === 'is_late')
    expect(share?.title).toBe('Share of is_late by priority')
    expect(share?.config).toMatchObject({ aggregation: 'count', bar_mode: 'stacked100' })
    expect(all.some(s => s.config.dimension === 'is_late')).toBe(false)
  })

  it('averages a score and never calculates a code, whatever they are called', () => {
    const score = all.find(s => s.config.measure === 'val2')
    expect(score?.config.aggregation).toBe('avg')
    expect(all.some(s => s.config.measure === 'ref9' && s.config.aggregation !== 'countd')).toBe(false)
  })
})

describe('suggestions that remember (server side)', () => {
  it('sinks a kind of chart this person keeps dismissing and lifts one they keep adding', async () => {
    const { typeBias } = await import('./SuggestionsPane')
    const fb = { dismissed: [], org_types: {},
                 types: { histogram: { added: 0, dismissed: 4 }, bar: { added: 5, dismissed: 1 }, pie: { added: 1, dismissed: 1 } } }
    expect(typeBias('histogram', fb)).toBeLessThan(0)
    expect(typeBias('bar', fb)).toBeGreaterThan(0)
    expect(typeBias('pie', fb)).toBe(0)                 // too little to judge
    expect(typeBias('line', fb)).toBe(0)
    expect(typeBias('bar', null)).toBe(0)
  })

  it('uses the organisation\'s experience for a kind the person has not judged', async () => {
    const { typeBias } = await import('./SuggestionsPane')
    const fb = { dismissed: [], types: {}, org_types: { treemap: { added: 0, dismissed: 9 } } }
    expect(typeBias('treemap', fb)).toBeLessThan(0)
  })
})

describe('C-18: a year is not an identifier to head-count', () => {
  it('never suggests a distinct count of year', () => {
    const withYear = [...cols, { id: 5, name: 'year', dtype: 'numeric', missing_pct: 0, stats: {} }] as unknown as DatasetColumn[]
    const s = suggestWidgets(withYear, analysis, 0, { year: { number: 'code' } } as never)
    expect(s.length).toBeGreaterThan(0)
    for (const x of s) {
      const c = x.config as Record<string, unknown>
      expect(c.measure === 'year' && c.aggregation === 'countd').toBe(false)
    }
  })
})
