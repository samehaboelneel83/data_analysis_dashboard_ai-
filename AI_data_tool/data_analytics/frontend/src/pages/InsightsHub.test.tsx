import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import InsightsHub from './InsightsHub'

/**
 * The hub navigates, it never analyses -- so its contract is exactly its
 * links: each capability card must point at the EXISTING DatasetDetail
 * section (anchor or tab param), and cards a DirectQuery dataset cannot serve
 * must be disabled rather than linked to a section that will not render.
 */

vi.mock('../services/api', () => ({
  datasetsApi: { list: vi.fn() },
  insightsApi: { runShared: vi.fn() },
  widgetDataApi: { query: vi.fn() },
}))

import { datasetsApi, insightsApi, widgetDataApi } from '../services/api'

// IMPORT_DS is the NEWER of the two -- existing tests below assume it is the
// auto-selected default, which is now recency-driven rather than list order.
const IMPORT_DS = { id: 5, name: 'Orders', mode: 'import', created_at: '2026-02-01T00:00:00Z', columns: [] } as any
const DQ_DS = { id: 6, name: 'Live warehouse', mode: 'directquery', created_at: '2026-01-01T00:00:00Z', columns: [] } as any

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(datasetsApi.list).mockResolvedValue([IMPORT_DS, DQ_DS])
  vi.mocked(insightsApi.runShared).mockResolvedValue({ findings: [], narrative: '' } as any)
  vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [] } as any)
})

const renderHub = () => render(<MemoryRouter><InsightsHub /></MemoryRouter>)

describe('InsightsHub', () => {

  it('defaults to the most recently CREATED dataset, not just the first one the API returned', async () => {
    // The API's own ordering is not a recency guarantee (nothing sorts it),
    // and the app has no "last opened" signal anywhere (Home.tsx's own
    // Recents falls back to created_at for exactly this reason) -- created_at
    // is the one honest signal available without inventing new backend state.
    const older = { id: 7, name: 'Old dataset', mode: 'import', created_at: '2025-01-01T00:00:00Z' } as any
    const newer = { id: 8, name: 'New dataset', mode: 'import', created_at: '2026-06-01T00:00:00Z' } as any
    // Listed in an order that would be WRONG if the code just took ds[0].
    vi.mocked(datasetsApi.list).mockResolvedValue([older, newer])

    renderHub()
    // Probed through the picker now that the capability cards are gone; it is
    // the same assertion about the same default.
    expect(await screen.findByLabelText('Dataset')).toHaveValue('8')
  })

  it('empty state when there are no datasets', async () => {
    vi.mocked(datasetsApi.list).mockResolvedValue([])
    renderHub()
    expect(await screen.findByText(/No datasets yet/)).toBeInTheDocument()
  })
})

describe('InsightsHub inline top-insights preview', () => {
  // The whole point of this panel: seeing whether a dataset has anything
  // worth looking at must not require clicking into the Insight scan card
  // first. It auto-fires the moment a dataset is selected.

  it('auto-runs the scan for the default dataset and shows its top findings, without any click', async () => {
    vi.mocked(insightsApi.runShared).mockResolvedValue({
      narrative: 'Revenue is trending up across most regions.',
      findings: [
        { kind: 'trend', score: 0.9, title: 'Revenue up 12%', detail: 'Q2 vs Q1', columns: ['revenue'] },
        { kind: 'outlier', score: 0.7, title: 'One region lags', detail: 'APAC flat', columns: ['region'] },
        { kind: 'gap', score: 0.5, title: 'Missing cost data', detail: '3% nulls', columns: ['cost'] },
        { kind: 'corr', score: 0.2, title: 'Weak signal', detail: 'below the fold', columns: [] },
      ],
    } as any)

    renderHub()

    expect(await screen.findByText('Revenue is trending up across most regions.')).toBeInTheDocument()
    expect(insightsApi.runShared).toHaveBeenCalledWith(5)
    expect(screen.getByText('Revenue up 12%')).toBeInTheDocument()
    expect(screen.getByText('One region lags')).toBeInTheDocument()
    expect(screen.getByText('Missing cost data')).toBeInTheDocument()
    // Only the top 3 by score -- the backend already returns them sorted.
    expect(screen.queryByText('Weak signal')).toBeNull()
  })

  it('links from the preview into the full scan', async () => {
    vi.mocked(insightsApi.runShared).mockResolvedValue({
      narrative: 'n', findings: [{ kind: 'trend', score: 0.9, title: 'T', detail: 'd', columns: [] }],
    } as any)
    renderHub()

    expect(await screen.findByRole('link', { name: /view full scan/i }))
      .toHaveAttribute('href', '/datasets/5#insights')
  })

  it('re-runs the scan when the selected dataset changes', async () => {
    vi.mocked(insightsApi.runShared).mockResolvedValue({ narrative: 'n1', findings: [] } as any)
    renderHub()
    await waitFor(() => expect(insightsApi.runShared).toHaveBeenCalledWith(5))

    vi.mocked(insightsApi.runShared).mockResolvedValue({ narrative: 'n2 about the DQ source', findings: [] } as any)
    fireEvent.change(await screen.findByLabelText('Dataset'), { target: { value: '6' } })

    // DQ_DS is DirectQuery -- scan is import-only, so switching to it must
    // NOT fire a second scan (it would just 400).
    await waitFor(() => expect(datasetsApi.list).toHaveBeenCalled())
    expect(insightsApi.runShared).toHaveBeenCalledTimes(1)
  })

  it('explains why a DirectQuery dataset has no preview, instead of a blank panel', async () => {
    vi.mocked(datasetsApi.list).mockResolvedValue([DQ_DS])
    renderHub()

    await screen.findByLabelText('Dataset')
    expect(insightsApi.runShared).not.toHaveBeenCalled()
    expect(screen.getByText(/live dataset/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /open dataset/i }))
      .toHaveAttribute('href', '/datasets/6')
  })

  it('shows nothing extra when the scan finds nothing worth surfacing', async () => {
    vi.mocked(insightsApi.runShared).mockResolvedValue({ narrative: '', findings: [] } as any)
    renderHub()
    await waitFor(() => expect(insightsApi.runShared).toHaveBeenCalled())
    expect(screen.queryByRole('link', { name: /view full scan/i })).toBeNull()
  })

  it('charts a top finding inline once its column pairing is known', async () => {
    vi.mocked(datasetsApi.list).mockResolvedValue([{
      ...IMPORT_DS,
      columns: [{ name: 'region', dtype: 'categorical' }, { name: 'revenue', dtype: 'numeric' }],
    }])
    vi.mocked(insightsApi.runShared).mockResolvedValue({
      narrative: 'n',
      findings: [{ kind: 'standout', score: 0.9, title: 'APAC leads', detail: 'd', columns: ['region', 'revenue'] }],
    } as any)
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      rows: [{ name: 'APAC', value: 40 }, { name: 'EMEA', value: 10 }],
    } as any)

    renderHub()

    expect(await screen.findAllByTestId('mini-bar-row')).toHaveLength(2)
    expect(widgetDataApi.query).toHaveBeenCalledWith(
      5, { dimension: 'region', measure: 'revenue', aggregation: 'sum' }, [], 'bar')
  })

  it('shows a retry-capable error instead of leaving the preview stuck loading', async () => {
    vi.mocked(insightsApi.runShared).mockRejectedValue({ response: { data: { detail: 'Scan failed' } } })
    renderHub()

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('Scan failed')).toBeInTheDocument()
  })
})

describe('InsightsHub loading and error states', () => {
  it('shows a retry-capable error banner, not a silent empty hub, when the dataset list fails to load', async () => {
    vi.mocked(datasetsApi.list).mockRejectedValueOnce({ response: { data: { detail: 'Not authorized' } } })
    renderHub()

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.getByText('Not authorized')).toBeInTheDocument()
    expect(screen.queryByText(/No datasets yet/)).toBeNull()
  })

  it('retries the load when "Try again" is clicked, and clears the error once it succeeds', async () => {
    vi.mocked(datasetsApi.list)
      .mockRejectedValueOnce({ response: { data: { detail: 'Not authorized' } } })
      .mockResolvedValueOnce([IMPORT_DS, DQ_DS])
    renderHub()

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /try again/i }))

    // The picker is what proves the load succeeded now.
    expect(await screen.findByLabelText('Dataset')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
  })
})

describe('the narrative earns its place or is not shown', () => {
  const finding = (n: number) => ({
    kind: 'trend', score: 1 - n / 10, title: `Finding ${n}`,
    detail: `detail ${n}`, columns: [],
  })

  it('hides the paragraph when there is exactly ONE finding', async () => {
    // Live, the paragraph and the single bullet stated the same fact about the
    // same outlying row -- the narrative was the bullet again, in prose.
    vi.mocked(insightsApi.runShared).mockResolvedValue({
      narrative: '1 outlying rows carry 43% of symbol_code.',
      findings: [finding(1)],
    } as any)
    renderHub()

    expect(await screen.findByText('Finding 1')).toBeInTheDocument()
    expect(screen.queryByText('1 outlying rows carry 43% of symbol_code.')).toBeNull()
  })

  it('still shows the panel and its link with one finding', async () => {
    // Hiding the paragraph must not hide the finding or the way through to
    // the full scan.
    vi.mocked(insightsApi.runShared).mockResolvedValue({
      narrative: 'just the one', findings: [finding(1)],
    } as any)
    renderHub()

    expect(await screen.findByText('Finding 1')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /view full scan/i })).toBeInTheDocument()
  })

  it('shows the paragraph with THREE findings, where it connects them', async () => {
    vi.mocked(insightsApi.runShared).mockResolvedValue({
      narrative: 'Revenue is up while costs drift, and one region lags both.',
      findings: [finding(1), finding(2), finding(3)],
    } as any)
    renderHub()

    expect(await screen.findByText(
      'Revenue is up while costs drift, and one region lags both.')).toBeInTheDocument()
    for (const n of [1, 2, 3]) {
      expect(screen.getByText(`Finding ${n}`)).toBeInTheDocument()
    }
  })

  it('shows the paragraph when there are NO findings, where it is the only content', async () => {
    // "Nothing notable in this data" is worth saying, and with no bullets
    // there is nothing for it to repeat.
    vi.mocked(insightsApi.runShared).mockResolvedValue({
      narrative: 'Nothing notable in this data.', findings: [],
    } as any)
    renderHub()
    expect(await screen.findByText('Nothing notable in this data.')).toBeInTheDocument()
  })
})

describe("the preview shows only findings worth the reader's attention", () => {
  it('drops a weak finding even when it is in the top three', async () => {
    // The preview used to slice the first three whatever they scored, so on a
    // quiet dataset a 0.05 finding earned a card purely by being third.
    vi.mocked(insightsApi.runShared).mockResolvedValue({
      narrative: 'n',
      findings: [
        { kind: 'trend', score: 0.9, title: 'Strong one', detail: 'd', columns: [] },
        { kind: 'trend', score: 0.05, title: 'Barely anything', detail: 'd', columns: [] },
      ],
    } as any)
    renderHub()

    expect(await screen.findByText('Strong one')).toBeInTheDocument()
    expect(screen.queryByText('Barely anything')).toBeNull()
  })

  it('keeps the panel and its link when NOTHING clears the bar', async () => {
    // Otherwise a quiet dataset loses its only route into the full scan --
    // exactly when someone wants to go and look for themselves.
    vi.mocked(insightsApi.runShared).mockResolvedValue({
      narrative: 'Nothing stands out strongly here.',
      findings: [{ kind: 'trend', score: 0.1, title: 'Faint', detail: 'd', columns: [] }],
    } as any)
    renderHub()

    expect(await screen.findByRole('link', { name: /view full scan/i })).toBeInTheDocument()
    expect(screen.getByText('Nothing stands out strongly here.')).toBeInTheDocument()
    expect(screen.queryByText('Faint')).toBeNull()
  })

  it('counts only the STRONG findings when deciding to show the narrative', async () => {
    // Two findings but one weak = one thing on screen, so the paragraph would
    // be restating that single bullet again.
    vi.mocked(insightsApi.runShared).mockResolvedValue({
      narrative: 'This should not appear.',
      findings: [
        { kind: 'trend', score: 0.9, title: 'The only real one', detail: 'd', columns: [] },
        { kind: 'trend', score: 0.05, title: 'Noise', detail: 'd', columns: [] },
      ],
    } as any)
    renderHub()

    expect(await screen.findByText('The only real one')).toBeInTheDocument()
    expect(screen.queryByText('This should not appear.')).toBeNull()
  })
})
