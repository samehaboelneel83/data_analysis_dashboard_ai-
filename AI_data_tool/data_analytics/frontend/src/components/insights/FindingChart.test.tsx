import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import FindingChart from './FindingChart'

vi.mock('../../services/api', () => ({
  widgetDataApi: { query: vi.fn() },
}))

import { widgetDataApi } from '../../services/api'

const COLUMN_TYPES = { region: 'categorical', revenue: 'numeric', cost: 'numeric' }

describe('FindingChart', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [] } as any)
  })

  it('charts a category+measure finding as a grouped bar', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      rows: [{ name: 'APAC', value: 40 }, { name: 'EMEA', value: 10 }],
    } as any)

    render(<FindingChart datasetId={5} columnTypes={COLUMN_TYPES}
      finding={{ kind: 'standout', title: 'APAC leads', columns: ['region', 'revenue'] }} />)

    await waitFor(() => expect(widgetDataApi.query).toHaveBeenCalledWith(
      5, { dimension: 'region', measure: 'revenue', aggregation: 'sum' }, [], 'bar'))
    expect(await screen.findAllByTestId('mini-bar-row')).toHaveLength(2)
  })

  it('says what the bars are of', async () => {
    // Each bar names its own category; nothing named the MEASURE, so a
    // reader could see "APAC 40" without knowing what 40 counts. That is the
    // axis-title job, at a size that has no room for axes.
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      rows: [{ name: 'APAC', value: 40 }],
    } as any)
    render(<FindingChart datasetId={5} columnTypes={COLUMN_TYPES}
      finding={{ kind: 'standout', title: 'APAC leads', columns: ['region', 'revenue'] }} />)
    expect(await screen.findByTestId('mini-bar-caption'))
      .toHaveTextContent('sum(revenue) by region')
  })

  it('says a histogram counts rows', async () => {
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      rows: [{ name: '0-10', value: 3, bin_start: 0, bin_end: 10 }],
    } as any)
    render(<FindingChart datasetId={5} columnTypes={COLUMN_TYPES}
      finding={{ kind: 'spread', title: 'revenue spread', columns: ['revenue'] }} />)
    expect(await screen.findByTestId('mini-bar-caption'))
      .toHaveTextContent('count of rows by revenue')
  })

  it('charts a single-measure finding as a histogram', async () => {
    render(<FindingChart datasetId={5} columnTypes={COLUMN_TYPES}
      finding={{ kind: 'outlier_impact', title: 'Cost has outliers', columns: ['cost'] }} />)

    await waitFor(() => expect(widgetDataApi.query).toHaveBeenCalledWith(
      5, { measure: 'cost', bins: 20 }, [], 'histogram'))
  })

  it('renders nothing for a two-measure correlation finding -- no chartable pairing', async () => {
    const { container } = render(<FindingChart datasetId={5} columnTypes={COLUMN_TYPES}
      finding={{ kind: 'correlation', title: 'Revenue vs cost', columns: ['revenue', 'cost'] }} />)

    await new Promise(r => setTimeout(r, 0))
    expect(widgetDataApi.query).not.toHaveBeenCalled()
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing for a finding with no columns', async () => {
    const { container } = render(<FindingChart datasetId={5} columnTypes={COLUMN_TYPES}
      finding={{ kind: 'data_quality', title: 'Some nulls', columns: [] }} />)

    await new Promise(r => setTimeout(r, 0))
    expect(widgetDataApi.query).not.toHaveBeenCalled()
    expect(container).toBeEmptyDOMElement()
  })

  it('fails silently -- a chart fetch error leaves no error UI, just no chart', async () => {
    vi.mocked(widgetDataApi.query).mockRejectedValue(new Error('boom'))

    const { container } = render(<FindingChart datasetId={5} columnTypes={COLUMN_TYPES}
      finding={{ kind: 'standout', title: 'APAC leads', columns: ['region', 'revenue'] }} />)

    await waitFor(() => expect(widgetDataApi.query).toHaveBeenCalled())
    await new Promise(r => setTimeout(r, 0))
    expect(container).toBeEmptyDOMElement()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('re-fetches when the finding changes', async () => {
    const { rerender } = render(<FindingChart datasetId={5} columnTypes={COLUMN_TYPES}
      finding={{ kind: 'standout', title: 'APAC leads', columns: ['region', 'revenue'] }} />)
    await waitFor(() => expect(widgetDataApi.query).toHaveBeenCalledTimes(1))

    rerender(<FindingChart datasetId={5} columnTypes={COLUMN_TYPES}
      finding={{ kind: 'laggard', title: 'EMEA lags', columns: ['region', 'cost'] }} />)
    await waitFor(() => expect(widgetDataApi.query).toHaveBeenCalledTimes(2))
    expect(widgetDataApi.query).toHaveBeenLastCalledWith(
      5, { dimension: 'region', measure: 'cost', aggregation: 'sum' }, [], 'bar')
  })
})
