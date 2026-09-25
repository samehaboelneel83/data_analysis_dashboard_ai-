import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import SuggestionsPane, { suggestWidgets } from './SuggestionsPane'
import { suggestApi } from '../../services/api'
import type { DatasetColumn } from '../../services/api'

vi.mock('../../services/api', () => ({
  suggestApi: { forReport: vi.fn() },
  widgetDataApi: { query: vi.fn().mockResolvedValue({ rows: [{ name: 'A', value: 1 }] }) },
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

describe('SuggestionsPane', () => {
  it('adds a suggestion on click', () => {
    const onAdd = vi.fn()
    render(<SuggestionsPane columns={cols} analysis={analysis} onAdd={onAdd} />)
    fireEvent.click(screen.getAllByRole('button', { name: 'Add to page' })[0])
    expect(onAdd).toHaveBeenCalled()
    expect(onAdd.mock.calls[0][0].config).toHaveProperty('aggregation')
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
    expect(screen.getByText(/From this data's insights/i)).toBeInTheDocument()
    expect(screen.getByText(/From column shapes/i)).toBeInTheDocument()

    fireEvent.click(item.querySelector('button')!)
    expect(onAdd).toHaveBeenCalledWith(expect.objectContaining({
      widget_type: 'bar',
      config: { dimension: 'region', measure: 'revenue', aggregation: 'sum' },
    }))
  })

  it('renders only heuristics when no reportId is given', () => {
    render(<SuggestionsPane columns={cols} analysis={null} onAdd={vi.fn()} />)
    expect(suggestApi.forReport).not.toHaveBeenCalled()
    expect(screen.queryByText(/From this data's insights/i)).toBeNull()
  })
})

describe('live previews', () => {
  it('renders a mini live chart per suggestion when datasetId is given', async () => {
    vi.mocked(suggestApi.forReport).mockResolvedValue([
      { widget_type: 'bar', title: 'A carries 80% of revenue', reason: 'standout',
        config: { dimension: 'region', measure: 'revenue', aggregation: 'sum' },
        score: 1, kind: 'standout', aligned: false },
    ])
    render(<SuggestionsPane columns={cols} analysis={null} onAdd={vi.fn()} reportId={7} datasetId={10} />)
    const previews = await screen.findAllByTestId('suggestion-preview')
    // one per insight suggestion PLUS one per heuristic card
    expect(previews.length).toBeGreaterThan(1)
    // non-interactive and decorative
    expect(previews[0].style.pointerEvents).toBe('none')
    expect(previews[0].getAttribute('aria-hidden')).toBe('true')
  })

  it('renders no previews without a datasetId', () => {
    vi.mocked(suggestApi.forReport).mockReset()
    render(<SuggestionsPane columns={cols} analysis={null} onAdd={vi.fn()} />)
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
