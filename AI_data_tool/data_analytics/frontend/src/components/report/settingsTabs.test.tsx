import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import WidgetConfigPanel from './WidgetConfigPanel'
import { CrossFilterProvider } from './CrossFilterContext'
import type { Widget } from '../../types/report'
import type { DatasetColumn, Dataset } from '../../services/api'

/**
 * The settings rail: one object's settings, grouped the way SAS groups them.
 *
 * An author looking for a specific setting today scrolls ten accordions in a
 * single column. SAS splits the same settings across named tabs — Options, Data,
 * Data roles, Actions, Display rules, Filters, Ranks — so "where do I change
 * the ranking" has an answer you can point at rather than scroll for.
 *
 * This is a routing layer over groups that already exist, which is the whole
 * reason it is cheap. The two ways a routing layer goes wrong are what these
 * tests are about:
 *
 *   A group that belongs to no tab becomes unreachable — settings that exist,
 *   render, are tested, and cannot be found by anybody.
 *
 *   Search that only looks inside the current tab silently lies. An author who
 *   types "opacity" while on Ranks must be shown the match, not an empty panel:
 *   an empty result reads as "this setting does not exist", which is the one
 *   answer that must never be wrong.
 */

vi.mock('../../services/api', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  boundarySetsApi: { list: vi.fn(), get: vi.fn(), create: vi.fn(), remove: vi.fn() },
}))

const columns: DatasetColumn[] = [
  { id: 1, name: 'region', dtype: 'text', missing_pct: 0, stats: {} },
  { id: 2, name: 'amount', dtype: 'numeric', missing_pct: 0, stats: {} },
]

function widget(overrides: Partial<Widget> = {}): Widget {
  return {
    id: 1, page_id: 100, widget_type: 'bar', title: 'Sales',
    config: { dimension: 'region', measure: 'amount' },
    layout: { x: 0, y: 0, w: 6, h: 5 }, created_at: '2026-01-01', ...overrides,
  }
}

function panel(w: Partial<Widget> = {}, opts: {
  datasets?: Record<number, Dataset>
  primaryDatasetId?: number | null
  columns?: DatasetColumn[]
} = {}) {
  return render(
    <CrossFilterProvider>
      <WidgetConfigPanel widget={widget(w)} columns={opts.columns ?? columns} onUpdate={vi.fn()} pages={[]}
        datasets={opts.datasets} primaryDatasetId={opts.primaryDatasetId} />
    </CrossFilterProvider>,
  )
}

// ExpandableGroup stores open/closed state in localStorage, which jsdom keeps
// between tests in a file.
beforeEach(() => { localStorage.clear() })
afterEach(() => { localStorage.clear() })

/** The group headings, which are what a tab shows or hides. */
const groupHeading = (name: string | RegExp) =>
  screen.queryByRole('button', { name })

describe('the settings rail', () => {
  it('offers the tabs an author of SAS reports already knows', () => {
    panel()
    const rail = screen.getByRole('tablist', { name: /settings/i })
    const names = Array.from(rail.querySelectorAll('[role="tab"]')).map(
      t => (t.textContent || '').trim())
    for (const expected of ['All', 'Options', 'Data', 'Data roles', 'Actions',
      'Display rules', 'Filters', 'Ranks']) {
      expect(names).toContain(expected)
    }
  })

  it('starts on All, so the panel an author already knows is unchanged', () => {
    panel()
    expect(screen.getByRole('tab', { name: 'All' })).toHaveAttribute('aria-selected', 'true')
    expect(groupHeading(/Ranking/)).toBeInTheDocument()
    expect(groupHeading(/Appearance/)).toBeInTheDocument()
  })

  it('shows one tab\'s groups and hides the rest', () => {
    panel()
    fireEvent.click(screen.getByRole('tab', { name: 'Ranks' }))

    expect(groupHeading(/Ranking/)).toBeInTheDocument()
    // Everything not on this tab is gone, not merely collapsed.
    expect(groupHeading(/Appearance/)).not.toBeInTheDocument()
    expect(groupHeading(/Formatting/)).not.toBeInTheDocument()
    expect(groupHeading(/Data & aggregation/)).not.toBeInTheDocument()
  })

  // Two widget types, because whole groups are gated on type: Actions only
  // renders for a button, so a bar-only walk would leave it unrouted and
  // unreachable with nothing failing.
  it.each(['bar', 'button'])(
    'puts every group of a %s on some tab, so no setting becomes unreachable',
    (wt) => {
    // The failure this prevents: a group added later, matching no tab, that
    // renders on "All" and nowhere else -- or on nothing at all.
    panel({ widget_type: wt as Widget['widget_type'] })
    const all = Array.from(document.querySelectorAll('[data-group-id]'))
      .map(el => el.getAttribute('data-group-id'))
    expect(all.length).toBeGreaterThan(2)

    const seen = new Set<string>()
    const tabs = ['Options', 'Data', 'Data roles', 'Actions', 'Display rules',
      'Filters', 'Ranks']
    for (const t of tabs) {
      fireEvent.click(screen.getByRole('tab', { name: t }))
      for (const el of Array.from(document.querySelectorAll('[data-group-id]'))) {
        seen.add(el.getAttribute('data-group-id') as string)
      }
    }
    expect([...all].sort()).toEqual([...seen].sort())
  })

  it('searches every tab, not just the one being looked at', () => {
    // The quiet lie: an author on Ranks types a word that lives under
    // Appearance and is shown nothing, which reads as "no such setting".
    panel()
    fireEvent.click(screen.getByRole('tab', { name: 'Ranks' }))
    expect(groupHeading(/Appearance/)).not.toBeInTheDocument()

    fireEvent.change(screen.getByLabelText(/Filter settings/i), {
      target: { value: 'Corner radius' },
    })

    expect(groupHeading(/Appearance/)).toBeInTheDocument()
    // And the tab the author was on does not keep its own groups on screen
    // just because it is selected -- a search narrows to the match.
    expect(groupHeading(/Ranking/)).not.toBeInTheDocument()
  })

  it('says which tab a searched-for setting was found on', () => {
    // Having crossed tabs to show the match, the panel has to say so, or the
    // author cannot get back to it once the box is cleared.
    panel()
    fireEvent.click(screen.getByRole('tab', { name: 'Ranks' }))
    fireEvent.change(screen.getByLabelText(/Filter settings/i), {
      target: { value: 'Corner radius' },
    })
    expect(screen.getByText(/searching all tabs/i)).toBeInTheDocument()
  })

  it('returns to the chosen tab when the search box is cleared', () => {
    panel()
    fireEvent.click(screen.getByRole('tab', { name: 'Ranks' }))
    const box = screen.getByLabelText(/Filter settings/i)
    fireEvent.change(box, { target: { value: 'Corner radius' } })
    fireEvent.change(box, { target: { value: '' } })

    expect(screen.getByRole('tab', { name: 'Ranks' })).toHaveAttribute('aria-selected', 'true')
    expect(groupHeading(/Ranking/)).toBeInTheDocument()
    expect(groupHeading(/Appearance/)).not.toBeInTheDocument()
  })

  it('says so when a tab has nothing for the selected object', () => {
    // Found in a browser, not here: on the live report the Ranks tab came up
    // completely blank, because ranking only renders for widget types that
    // support it (a KPI is not one). A rail that can route an author to an
    // empty pane with no explanation is worse than the scroll it replaced --
    // a blank panel reads as a broken one.
    panel({ widget_type: 'kpi' })
    fireEvent.click(screen.getByRole('tab', { name: 'Ranks' }))

    expect(document.querySelectorAll('[data-group-id]').length).toBe(0)
    expect(screen.getByText(/no ranks settings for this object/i)).toBeInTheDocument()
  })

  it('routes the ungrouped object fields too, not just the grouped ones', () => {
    // Also found in a browser. Title, right-to-left and transparent
    // background sit outside any ExpandableGroup, so the first version of the
    // rail left them on screen under every tab -- including under the
    // "No Ranks settings for this object" notice, which then contradicted the
    // four settings sitting right below it.
    panel()
    fireEvent.click(screen.getByRole('tab', { name: 'Ranks' }))
    expect(screen.queryByPlaceholderText('Widget title')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: 'Options' }))
    expect(screen.getByPlaceholderText('Widget title')).toBeInTheDocument()
  })

  it('counts those fields when deciding a tab is empty', () => {
    // Options always has the object's own fields, so it is never the empty
    // pane -- saying otherwise while showing a Title box would be a lie in
    // the other direction.
    panel({ widget_type: 'kpi' })
    fireEvent.click(screen.getByRole('tab', { name: 'Options' }))
    expect(screen.queryByText(/no options settings for this object/i))
      .not.toBeInTheDocument()
  })

  it('shows no such message on a tab that does have settings', () => {
    panel()
    fireEvent.click(screen.getByRole('tab', { name: 'Ranks' }))
    expect(groupHeading(/Ranking/)).toBeInTheDocument()
    expect(screen.queryByText(/nothing for this object|no ranks settings/i))
      .not.toBeInTheDocument()
  })
})

describe('pre-aggregated disclosure', () => {
  const aggregateDataset = {
    id: 9, name: 'orders by region', row_count: 720, col_count: 4, file_size: 0,
    created_at: '', updated_at: '', calculated_columns: [], measures: [],
    column_meta: {}, column_formats: {}, mode: 'import', aggregate_of_dataset_id: 5,
    aggregate_spec: { grain: ['tenant', 'region'], measures: [{ column: 'amount', agg: 'sum', name: 'amount_sum' }] },
    columns: [
      { id: 1, name: 'region', dtype: 'categorical', missing_pct: 0, stats: {}, semantic_type: null },
      { id: 2, name: 'amount_sum', dtype: 'numeric', missing_pct: 0, stats: {}, semantic_type: null },
      { id: 3, name: 'row_count', dtype: 'numeric', missing_pct: 0, stats: {}, semantic_type: null },
    ],
  } as unknown as Dataset

  const renderBar = (aggregation: string) => panel(
    { widget_type: 'bar', config: { dimension: 'region', measure: 'amount_sum', aggregation } },
    { datasets: { 9: aggregateDataset }, primaryDatasetId: 9, columns: aggregateDataset.columns },
  )

  it('warns when avg is chosen over a derived measure', () => {
    renderBar('avg')
    expect(screen.getByRole('note')).toHaveTextContent(/average of sums/)
  })
  it('is silent for sum', () => {
    renderBar('sum')
    expect(screen.queryByRole('note')).toBeNull()
  })
  it('warns when countd (the real select value for Count Distinct) is chosen', () => {
    renderBar('countd')
    expect(screen.getByRole('note')).toHaveTextContent(/counts groups/)
  })
})
