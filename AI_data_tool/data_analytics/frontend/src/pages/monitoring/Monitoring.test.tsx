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
  monitoringApi: { jobs: vi.fn(), deliveries: vi.fn(), activity: vi.fn(), refreshRuns: vi.fn(), automationRuns: vi.fn() },
}))

import { monitoringApi } from '../../services/api'

const renderIn = (ui: React.ReactElement) => render(<MemoryRouter>{ui}</MemoryRouter>)

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(monitoringApi.refreshRuns).mockResolvedValue([])
  vi.mocked(monitoringApi.automationRuns).mockResolvedValue([])
})

describe('MonitoringJobs', () => {
  it('shows the refresh history, and a failing job says when it is tried next (pipeline phase 1)', async () => {
    vi.mocked(monitoringApi.jobs).mockResolvedValue([
      { kind: 'dataset_refresh', id: 1, name: 'Orders', interval_minutes: 60,
        last_run_at: '2026-10-03T06:00:00Z', status: 'failed', error: 'Refresh failed: source down',
        next_retry_at: '2026-10-03T06:05:00Z' },
    ])
    vi.mocked(monitoringApi.refreshRuns).mockResolvedValue([
      { id: 2, kind: 'dataset', item_id: 1, name: 'Orders', trigger: 'schedule', status: 'failed',
        started_at: '2026-10-03T06:00:00Z', finished_at: '2026-10-03T06:00:01Z', rows: null,
        duration_ms: 1200, error: 'Refresh failed: source down', error_code: 'refresh_failed' },
      { id: 1, kind: 'dataset', item_id: 1, name: null, trigger: 'manual', status: 'ok',
        started_at: '2026-10-02T06:00:00Z', finished_at: '2026-10-02T06:00:03Z', rows: 1500,
        duration_ms: 3400, error: null, error_code: null },
    ])
    renderIn(<MonitoringJobs />)
    const table = await screen.findByTestId('refresh-history')
    expect(table).toHaveTextContent('1,500')
    expect(table).toHaveTextContent('1.2 s')
    expect(table).toHaveTextContent('(deleted)')
    expect(table).toHaveTextContent('manual')
    expect(screen.getAllByText('Refresh failed: source down').length).toBe(2)
    expect(screen.getByText(/next try/)).toBeInTheDocument()

    fireEvent.click(screen.getByLabelText('Failed only'))
    await waitFor(() => expect(monitoringApi.refreshRuns).toHaveBeenLastCalledWith({ status: 'failed' }))
  })

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

  it('lists automated analyses with a link to each run, and the checks of every refresh (AD-17)', async () => {
    vi.mocked(monitoringApi.jobs).mockResolvedValue([])
    vi.mocked(monitoringApi.automationRuns).mockResolvedValue([
      { id: 12, status: 'failed', dataset_id: 3, dataset_name: 'Sales', started_at: '2026-10-14T10:00:00Z',
        finished_at: null, step: 'Build the report', error: 'Build the report did not finish in 3 min' },
    ] as never)
    vi.mocked(monitoringApi.refreshRuns).mockResolvedValue([
      { id: 1, kind: 'dataset', item_id: 3, name: 'Sales', trigger: 'schedule', status: 'ok', started_at: '2026-10-14T09:00:00Z',
        finished_at: null, rows: 10, duration_ms: 100, error: null, error_code: null, checks_summary: { pass: 2, warn: 1, fail: 0 } },
    ] as never)
    renderIn(<MonitoringJobs />)
    const section = await screen.findByTestId('automation-runs')
    expect(section).toHaveTextContent('Sales')
    expect(section).toHaveTextContent('Build the report did not finish')
    expect(screen.getByRole('link', { name: /Run #12/ })).toHaveAttribute('href', '/automation?run=12')
    expect(await screen.findByText('2 pass · 1 warn')).toBeInTheDocument()
  })

  it('says Paused for an unscheduled job and marks a paused calendar (AD-16)', async () => {
    vi.mocked(monitoringApi.jobs).mockResolvedValue([
      { kind: 'alert', id: 3, name: 'Demo alert', interval_minutes: 0,
        last_run_at: null, status: null, error: null, dataset_id: 4 },
      { kind: 'report_schedule', id: 2, name: 'Demo weekly', interval_minutes: 0, last_run_at: null, status: null,
        error: null, report_id: 9, calendar: { kind: 'weekly', weekday: 0, hour: 9, minute: 0, paused: true } },
    ] as never)
    renderIn(<MonitoringJobs />)
    await screen.findByText('Demo alert')
    expect(screen.getByText('Paused (not scheduled)')).toBeInTheDocument()
    expect(screen.getByText(/weekly .*\(paused\)/i)).toBeInTheDocument()
  })

  it('links a dataflow job to the Dataflows page, opened on it (E12)', async () => {
    // Dataflows run on their schedule and belong in this list; their page
    // is back, so the row opens it on the dataflow.
    vi.mocked(monitoringApi.jobs).mockResolvedValue([
      { kind: 'dataflow', id: 5, name: 'Nightly rollup', interval_minutes: 1440,
        last_run_at: null, status: null, error: null },
    ])
    renderIn(<MonitoringJobs />)
    expect(await screen.findByText('Nightly rollup')).toBeInTheDocument()
    expect(screen.getByText('Dataflow')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Nightly rollup' })).toHaveAttribute('href', '/dataflows?flow=5')
  })

  it('says why a job was skipped (5.19)', async () => {
    vi.mocked(monitoringApi.jobs).mockResolvedValue([
      { kind: 'dataflow', id: 6, name: 'Headcount history', interval_minutes: 1440,
        last_run_at: new Date().toISOString(), status: 'skipped', error: 'no outputs yet' },
    ])
    renderIn(<MonitoringJobs />)
    expect(await screen.findByTestId('job-reason-dataflow-6'))
      .toHaveTextContent('Nothing to refresh yet: run this dataflow once into a new output')
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

  it('writes a legacy key=value detail in words: None is "no limit" (AD-18)', async () => {
    vi.mocked(monitoringApi.activity).mockResolvedValue([
      { id: 1, user_email: 'a@b.com', action: 'platform.set_org_quota', entity: 'organization',
        entity_id: 2, detail: 'queries=None asks=5', created_at: '2026-09-01T10:00:00Z' },
      { id: 2, user_email: 'a@b.com', action: 'report.unshare', entity: 'report',
        entity_id: 3, detail: 'grant:7', created_at: '2026-09-01T10:00:00Z' },
    ])
    renderIn(<MonitoringActivity />)
    expect(await screen.findByText('queries: no limit')).toBeInTheDocument()
    expect(screen.getByText('asks: 5')).toBeInTheDocument()
    expect(screen.queryByText(/None/)).toBeNull()
    expect(screen.getByText('share #7')).toBeInTheDocument()
  })

  it('pages with "Load more", filters by action on the server, and opens a row (AD-19)', async () => {
    const row = (id: number) => ({ id, user_email: 'a@b.com', action: 'report.create', entity: 'report',
      entity_id: id, detail: `detail ${id}`, created_at: '2026-09-01T10:00:00Z' })
    vi.mocked(monitoringApi.activity)
      .mockResolvedValueOnce(Array.from({ length: 100 }, (_, i) => row(500 - i)))
      .mockResolvedValueOnce([row(300)])
      .mockResolvedValue([row(42)])
    renderIn(<MonitoringActivity />)
    await screen.findByText('detail 500')
    expect(vi.mocked(monitoringApi.activity).mock.calls[0][0]).toMatchObject({ limit: 100 })
    fireEvent.click(screen.getByRole('button', { name: 'Load more' }))
    expect(await screen.findByText('detail 300')).toBeInTheDocument()
    expect(vi.mocked(monitoringApi.activity).mock.calls[1][0]).toMatchObject({ before_id: 401 })
    expect(screen.queryByRole('button', { name: 'Load more' })).toBeNull()   // a short page is the end

    fireEvent.change(screen.getByLabelText('Action'), { target: { value: 'report.create' } })
    await waitFor(() => expect(vi.mocked(monitoringApi.activity).mock.calls[2][0]).toMatchObject({ action: 'report.create' }))
    fireEvent.click(await screen.findByText('detail 42'))
    const detail = await screen.findByTestId('activity-detail-42')
    expect(detail).toHaveTextContent('detail 42')
    expect(detail.querySelector('a[href="/reports/42"]')).not.toBeNull()
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
