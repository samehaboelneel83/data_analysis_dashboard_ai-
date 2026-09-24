import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import MonitoringJobs from './MonitoringJobs'
import MonitoringDeliveries from './MonitoringDeliveries'
import MonitoringActivity from './MonitoringActivity'

/**
 * The three Monitoring pages are read-only aggregations; what can go wrong in
 * them is presentation, so that is what these tests pin: the standard
 * loading -> list / empty / error triple, and the normalisation choices
 * (kind labels, "never" for a job that has not run, failure rows carrying
 * their error).
 */

vi.mock('../../services/api', () => ({
  monitoringApi: { jobs: vi.fn(), deliveries: vi.fn(), activity: vi.fn() },
}))

import { monitoringApi } from '../../services/api'

const renderIn = (ui: React.ReactElement) => render(<MemoryRouter>{ui}</MemoryRouter>)

beforeEach(() => vi.clearAllMocks())

describe('MonitoringJobs', () => {
  it('lists every job kind under its human label, with "never" for an unrun job', async () => {
    vi.mocked(monitoringApi.jobs).mockResolvedValue([
      { kind: 'dataset_refresh', id: 1, name: 'Orders', interval_minutes: 60,
        last_run_at: '2026-09-01T10:00:00Z', status: null, error: null },
      { kind: 'report_schedule', id: 2, name: 'Weekly digest', interval_minutes: 10080,
        last_run_at: null, status: null, error: null, report_id: 9 },
      { kind: 'alert', id: 3, name: 'Revenue floor', interval_minutes: 60,
        last_run_at: null, status: 'clear', error: null, dataset_id: 4 },
    ])
    renderIn(<MonitoringJobs />)
    expect(await screen.findByText('Orders')).toBeInTheDocument()
    expect(screen.getByText('Dataset refresh')).toBeInTheDocument()
    expect(screen.getByText('Report schedule')).toBeInTheDocument()
    expect(screen.getByText('Data alert')).toBeInTheDocument()
    expect(screen.getAllByText('never').length).toBe(2)
    // Each row links to where the job is configured.
    expect(screen.getByRole('link', { name: 'Weekly digest' })).toHaveAttribute('href', '/reports/9')
    expect(screen.getByRole('link', { name: 'Revenue floor' })).toHaveAttribute('href', '/datasets/4')
  })

  it('names a dataflow job without linking it -- the Dataflows page is gone', async () => {
    // Dataflows still run on their schedule and still belong in this list.
    // What they no longer have is a page to open, so the row states the job
    // rather than offering a link into a route that would 404.
    vi.mocked(monitoringApi.jobs).mockResolvedValue([
      { kind: 'dataflow', id: 5, name: 'Nightly rollup', interval_minutes: 1440,
        last_run_at: null, status: null, error: null },
    ])
    renderIn(<MonitoringJobs />)
    expect(await screen.findByText('Nightly rollup')).toBeInTheDocument()
    expect(screen.getByText('Dataflow')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Nightly rollup' })).toBeNull()
  })

  it('shows the empty state when nothing is scheduled', async () => {
    vi.mocked(monitoringApi.jobs).mockResolvedValue([])
    renderIn(<MonitoringJobs />)
    expect(await screen.findByText(/Nothing is scheduled yet/)).toBeInTheDocument()
  })

  it('surfaces a load failure as a retry-capable alert, not an empty list', async () => {
    // An error dressed as "no jobs" would read as "all quiet" -- the exact
    // opposite of the truth.
    vi.mocked(monitoringApi.jobs).mockRejectedValue({ response: { data: { detail: 'boom' } } })
    renderIn(<MonitoringJobs />)
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Could not load jobs')
    expect(alert).toHaveTextContent('boom')
    expect(screen.queryByText(/Nothing is scheduled yet/)).not.toBeInTheDocument()
  })

  it('retries the load when "Try again" is clicked, clearing the error once it succeeds', async () => {
    vi.mocked(monitoringApi.jobs)
      .mockRejectedValueOnce({ response: { data: { detail: 'boom' } } })
      .mockResolvedValueOnce([])
    renderIn(<MonitoringJobs />)

    await screen.findByRole('alert')
    fireEvent.click(screen.getByRole('button', { name: /try again/i }))

    await waitFor(() => expect(screen.getByText(/Nothing is scheduled yet/)).toBeInTheDocument())
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('MonitoringDeliveries', () => {
  it('lists deliveries with report links and honest failure rows', async () => {
    vi.mocked(monitoringApi.deliveries).mockResolvedValue([
      { id: 1, schedule_id: 3, kind: 'schedule', status: 'ok', error: null,
        artifact_kind: 'pdf', duration_ms: 812, created_at: '2026-09-01T10:00:00Z',
        report_id: 9, report_name: 'Sales' },
      { id: 2, schedule_id: null, kind: 'alert', status: 'error', error: 'SMTP down',
        artifact_kind: 'none', duration_ms: null, created_at: '2026-09-01T09:00:00Z',
        report_id: null, report_name: null },
    ])
    renderIn(<MonitoringDeliveries />)
    expect(await screen.findByRole('link', { name: 'Sales' })).toHaveAttribute('href', '/reports/9')
    expect(screen.getByText(/failed — SMTP down/)).toBeInTheDocument()
  })

  it('empty and error states are distinct', async () => {
    vi.mocked(monitoringApi.deliveries).mockResolvedValue([])
    const { unmount } = renderIn(<MonitoringDeliveries />)
    expect(await screen.findByText(/No deliveries yet/)).toBeInTheDocument()
    unmount()

    vi.mocked(monitoringApi.deliveries).mockRejectedValue({ response: { data: { detail: 'boom' } } })
    renderIn(<MonitoringDeliveries />)
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Could not load deliveries')
    expect(alert).toHaveTextContent('boom')
  })

  it('retries the load when "Try again" is clicked, clearing the error once it succeeds', async () => {
    vi.mocked(monitoringApi.deliveries)
      .mockRejectedValueOnce({ response: { data: { detail: 'boom' } } })
      .mockResolvedValueOnce([])
    renderIn(<MonitoringDeliveries />)

    await screen.findByRole('alert')
    fireEvent.click(screen.getByRole('button', { name: /try again/i }))

    await waitFor(() => expect(screen.getByText(/No deliveries yet/)).toBeInTheDocument())
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('MonitoringActivity', () => {
  it('lists the audit-log rows -- the first reader this endpoint has had', async () => {
    vi.mocked(monitoringApi.activity).mockResolvedValue([
      { id: 1, user_email: 'a@b.com', action: 'dataset.upload', entity: 'dataset',
        entity_id: 4, detail: 'orders.csv', created_at: '2026-09-01T10:00:00Z' },
    ])
    renderIn(<MonitoringActivity />)
    expect(await screen.findByText('dataset.upload')).toBeInTheDocument()
    expect(screen.getByText('dataset #4')).toBeInTheDocument()
    expect(screen.getByText('orders.csv')).toBeInTheDocument()
  })

  it('empty and error states are distinct', async () => {
    vi.mocked(monitoringApi.activity).mockResolvedValue([])
    const { unmount } = renderIn(<MonitoringActivity />)
    expect(await screen.findByText('Nothing recorded yet.')).toBeInTheDocument()
    unmount()

    vi.mocked(monitoringApi.activity).mockRejectedValue({ response: { data: { detail: 'boom' } } })
    renderIn(<MonitoringActivity />)
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Could not load activity')
    expect(alert).toHaveTextContent('boom')
  })

  it('retries the load when "Try again" is clicked, clearing the error once it succeeds', async () => {
    vi.mocked(monitoringApi.activity)
      .mockRejectedValueOnce({ response: { data: { detail: 'boom' } } })
      .mockResolvedValueOnce([])
    renderIn(<MonitoringActivity />)

    await screen.findByRole('alert')
    fireEvent.click(screen.getByRole('button', { name: /try again/i }))

    await waitFor(() => expect(screen.getByText('Nothing recorded yet.')).toBeInTheDocument())
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
