import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import AggregatesPanel from './AggregatesPanel'
import { aggregatesApi } from '../../services/api'

/**
 * The Aggregates tab. The governance rule -- the grain must include every
 * column a row-level security rule reads -- is shown, not discovered: those
 * columns arrive pre-selected and locked, with the reason beside them.
 */
vi.mock('../../services/api', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  aggregatesApi: { preflight: vi.fn(), list: vi.fn(), create: vi.fn(), update: vi.fn() },
}))

const PRE = { rls_columns: ['tenant'], grain_candidates: ['amount', 'region', 'tenant', 'units'],
              measure_candidates: ['amount', 'units'] }

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(aggregatesApi.preflight).mockResolvedValue(PRE)
  vi.mocked(aggregatesApi.list).mockResolvedValue([])
})

describe('AggregatesPanel', () => {
  it('locks the RLS columns into the grain and says why', async () => {
    render(<AggregatesPanel datasetId={5} mode="directquery" />)
    const tenant = await screen.findByLabelText('tenant') as HTMLInputElement
    expect(tenant.checked).toBe(true)
    expect(tenant.disabled).toBe(true)
    expect(screen.getByText(/row-level security rule reads it/i)).toBeInTheDocument()
  })

  it('creates with the chosen grain, measures and schedule', async () => {
    vi.mocked(aggregatesApi.create).mockResolvedValue({ id: 9, name: 'by region' } as never)
    render(<AggregatesPanel datasetId={5} mode="directquery" />)
    await screen.findByLabelText('tenant')
    fireEvent.click(screen.getByLabelText('region'))
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'by region' } })
    fireEvent.change(screen.getByLabelText('Measure column'), { target: { value: 'amount' } })
    fireEvent.change(screen.getByLabelText('Aggregation'), { target: { value: 'sum' } })
    fireEvent.click(screen.getByRole('button', { name: /add measure/i }))
    fireEvent.change(screen.getByLabelText('Refresh every (minutes)'), { target: { value: '60' } })
    fireEvent.click(screen.getByRole('button', { name: /create aggregate/i }))
    await waitFor(() => expect(aggregatesApi.create).toHaveBeenCalledWith(5, {
      name: 'by region', grain: ['tenant', 'region'],
      measures: [{ column: 'amount', agg: 'sum' }], refresh_interval_minutes: 60,
    }))
  })

  it('shows the backend refusal verbatim', async () => {
    vi.mocked(aggregatesApi.create).mockRejectedValue({ response: { data: {
      detail: "The grain must include 'tenant': the row-level security rule for role 'Tenant' reads it" } } })
    render(<AggregatesPanel datasetId={5} mode="directquery" />)
    await screen.findByLabelText('tenant')
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'x' } })
    fireEvent.change(screen.getByLabelText('Measure column'), { target: { value: 'amount' } })
    fireEvent.click(screen.getByRole('button', { name: /add measure/i }))
    fireEvent.click(screen.getByRole('button', { name: /create aggregate/i }))
    expect(await screen.findByText(/The grain must include 'tenant'/)).toBeInTheDocument()
  })

  it('lists existing aggregates with the scheduler’s last failure', async () => {
    vi.mocked(aggregatesApi.list).mockResolvedValue([{
      dataset: { id: 9, name: 'by region', row_count: 120, refresh_interval_minutes: 60,
        aggregate_spec: { grain: ['tenant', 'region'], measures: [{ column: 'amount', agg: 'sum', name: 'amount_sum' }] } },
      last_error: "Not refreshed: the row-level security rule for role 'Tenant' reads 'product'",
      attempts: 3,
    }] as never)
    render(<AggregatesPanel datasetId={5} mode="directquery" />)
    expect(await screen.findByText('by region')).toBeInTheDocument()
    expect(screen.getByText(/reads 'product'/)).toBeInTheDocument()
    expect(screen.getByText(/tenant × region/)).toBeInTheDocument()
  })

  it('says why an import dataset has no aggregates tab content', async () => {
    render(<AggregatesPanel datasetId={5} mode="import" />)
    expect(await screen.findByText(/DirectQuery/)).toBeInTheDocument()
    expect(aggregatesApi.preflight).not.toHaveBeenCalled()
  })

  it('shows a message and a retry when the preflight/list load fails', async () => {
    vi.mocked(aggregatesApi.preflight).mockRejectedValue({ response: { data: {
      detail: 'Dataset not found' } } })
    render(<AggregatesPanel datasetId={5} mode="directquery" />)
    expect(await screen.findByText('Dataset not found')).toBeInTheDocument()
    const retry = screen.getByRole('button', { name: /try again/i })

    vi.mocked(aggregatesApi.preflight).mockResolvedValue(PRE)
    fireEvent.click(retry)
    expect(await screen.findByLabelText('tenant')).toBeInTheDocument()
  })

  const ITEM = {
    dataset: { id: 9, name: 'by region', row_count: 720, refresh_interval_minutes: 60,
      aggregate_spec: { grain: ['tenant', 'region'], measures: [{ column: 'amount', agg: 'sum', name: 'amount_sum' }] } },
    last_error: null, attempts: 0,
  }

  it('edits an existing aggregate through PUT with the form prefilled', async () => {
    vi.mocked(aggregatesApi.list).mockResolvedValue([ITEM as never])
    vi.mocked(aggregatesApi.update).mockResolvedValue({} as never)
    render(<AggregatesPanel datasetId={5} mode="directquery" />)
    fireEvent.click(await screen.findByRole('button', { name: /edit/i }))
    expect((screen.getByLabelText('region') as HTMLInputElement).checked).toBe(true)
    expect(screen.getByText(/sum\(amount\)/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Refresh every (minutes)'), { target: { value: '30' } })
    fireEvent.click(screen.getByRole('button', { name: /save changes/i }))
    await waitFor(() => expect(aggregatesApi.update).toHaveBeenCalledWith(5, 9, {
      grain: ['tenant', 'region'], measures: [{ column: 'amount', agg: 'sum', name: 'amount_sum' }],
      refresh_interval_minutes: 30,
    }))
  })

  it('offers Rebuild on a "query changed" failure and sends an empty PUT', async () => {
    vi.mocked(aggregatesApi.list).mockResolvedValue([{ ...ITEM,
      last_error: "Not refreshed: the source's query changed since this aggregate was built; rebuild the aggregate to pick it up." } as never])
    vi.mocked(aggregatesApi.update).mockResolvedValue({} as never)
    render(<AggregatesPanel datasetId={5} mode="directquery" />)
    fireEvent.click(await screen.findByRole('button', { name: /rebuild/i }))
    await waitFor(() => expect(aggregatesApi.update).toHaveBeenCalledWith(5, 9, {}))
  })

  it('offers NO Rebuild on a "filter expression" failure -- fixing it means removing the source filter, not rebuilding', async () => {
    vi.mocked(aggregatesApi.list).mockResolvedValue([{ ...ITEM,
      last_error: 'Not refreshed: the source has a report-level filter expression, which an '
        + 'aggregate would ignore. Remove the filter expression on the source, then rebuild this aggregate.' } as never])
    render(<AggregatesPanel datasetId={5} mode="directquery" />)
    expect(await screen.findByText(/filter expression/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /rebuild/i })).not.toBeInTheDocument()
  })

  it("carries a measure's custom name through the Edit round trip, instead of silently renaming it back to the default", async () => {
    vi.mocked(aggregatesApi.list).mockResolvedValue([{
      dataset: { id: 9, name: 'by region', row_count: 720, refresh_interval_minutes: 60,
        aggregate_spec: { grain: ['tenant', 'region'],
                          measures: [{ column: 'amount', agg: 'sum', name: 'revenue' }] } },
      last_error: null, attempts: 0,
    } as never])
    vi.mocked(aggregatesApi.update).mockResolvedValue({} as never)
    render(<AggregatesPanel datasetId={5} mode="directquery" />)
    fireEvent.click(await screen.findByRole('button', { name: /edit/i }))
    fireEvent.click(screen.getByRole('button', { name: /save changes/i }))
    await waitFor(() => expect(aggregatesApi.update).toHaveBeenCalledWith(5, 9, {
      grain: ['tenant', 'region'], measures: [{ column: 'amount', agg: 'sum', name: 'revenue' }],
      refresh_interval_minutes: 60,
    }))
  })

  it("seeds Edit's grain with the union of the stored spec and the source's current RLS columns", async () => {
    vi.mocked(aggregatesApi.preflight).mockResolvedValue({
      rls_columns: ['tenant', 'product'],
      grain_candidates: ['amount', 'product', 'region', 'tenant', 'units'],
      measure_candidates: ['amount', 'units'],
    })
    vi.mocked(aggregatesApi.list).mockResolvedValue([ITEM as never])
    vi.mocked(aggregatesApi.update).mockResolvedValue({} as never)
    render(<AggregatesPanel datasetId={5} mode="directquery" />)
    fireEvent.click(await screen.findByRole('button', { name: /edit/i }))
    const product = screen.getByLabelText('product') as HTMLInputElement
    expect(product.checked).toBe(true)
    expect(product.disabled).toBe(true)
    const region = screen.getByLabelText('region') as HTMLInputElement
    expect(region.checked).toBe(true)
    expect(region.disabled).toBe(false)
    fireEvent.click(screen.getByRole('button', { name: /save changes/i }))
    await waitFor(() => expect(aggregatesApi.update).toHaveBeenCalledWith(5, 9, {
      grain: ['tenant', 'product', 'region'], measures: [{ column: 'amount', agg: 'sum', name: 'amount_sum' }],
      refresh_interval_minutes: 60,
    }))
  })
})
