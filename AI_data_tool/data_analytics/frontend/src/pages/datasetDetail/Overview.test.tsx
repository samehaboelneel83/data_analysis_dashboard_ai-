import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, within, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Overview, { type OverviewProps } from './Overview'
import { adminAuditApi, datasetsApi, lineageApi, monitoringApi, type Dataset } from '../../services/api'

/**
 * Redesign step 3b: the dataset Overview. Trust checks, columns at a glance,
 * what uses the dataset, its lineage, insights and -- for admins only -- the
 * recent activity read from the two audit logs.
 */

vi.mock('../../services/api', () => ({
  datasetsApi: { tryChecks: vi.fn() },
  lineageApi: { graph: vi.fn() },
  monitoringApi: { activity: vi.fn() },
  adminAuditApi: { list: vi.fn() },
}))

const hoursAgo = (h: number) => new Date(Date.now() - h * 3600_000).toISOString()
const DS = {
  id: 1, name: 'Demo — Sales', row_count: 2000, col_count: 3, file_size: 226_918,
  created_at: hoursAgo(1), updated_at: hoursAgo(1), mode: 'import', data_source_id: null,
  columns: [
    { id: 1, name: 'region', dtype: 'categorical', missing_pct: 0, stats: {} },
    { id: 2, name: 'margin_pct', dtype: 'numeric', missing_pct: 0, stats: {} },
    { id: 3, name: 'date', dtype: 'datetime', missing_pct: 0, stats: {} },
  ],
  column_meta: {}, column_formats: {}, calculated_columns: [], measures: [],
} as unknown as Dataset

const ANALYSIS = {
  numeric: { columns: { margin_pct: { min: -4.1, p5: 2, p25: 10, median: 19, p75: 28, p95: 60, max: 104.2 } } },
  categorical: { columns: { region: { n_unique: 4, top_values: [{ value: 'Asia Pacific', count: 580, pct: 29 }] } } },
  datetime: { columns: { date: { min: '2025-01-01', max: '2026-09-30', monthly_counts: [{ period: '2025-01', count: 90 }, { period: '2025-02', count: 95 }] } } },
  overview: { missing_pct: 0 },
}

function show(over: Partial<OverviewProps> = {}) {
  const props: OverviewProps = {
    ds: DS, analysis: ANALYSIS, profiling: false, profileError: null, onProfile: vi.fn(),
    isAdmin: false, me: { id: 5, email: 'me@x.io' }, pipelineHealth: null, onCertify: vi.fn(),
    goTab: vi.fn(), insights: null, insightsBusy: false, onGenerateInsights: vi.fn(),
    firstRun: false, onBuild: vi.fn(), alerts: [], checks: [], ...over,
  }
  render(<MemoryRouter><Overview {...props} /></MemoryRouter>)
  return props
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(lineageApi.graph).mockResolvedValue({
    sources: [], reports: [{ id: 10, name: 'Sales Overview', dataset_ids: [1] }], datasets: [],
  })
  vi.mocked(monitoringApi.activity).mockResolvedValue([])
  vi.mocked(adminAuditApi.list).mockResolvedValue([])
})

describe('Overview trust checks (3b)', () => {
  it('says fresh, complete and not certified for a plain upload with no checks', () => {
    show()
    expect(screen.getByTestId('trust-fresh')).toHaveTextContent(/Uploaded .*Uploaded files don’t refresh on their own/)
    expect(screen.getByTestId('trust-complete')).toHaveTextContent('0.0% empty across 6,000 values')
    expect(screen.getByTestId('trust-checks')).toHaveTextContent('No saved checks yet.')
    expect(screen.getByTestId('trust-cert')).toHaveTextContent('Not certified')
  })

  it('names the failing check and flags its column, from the existing try call', async () => {
    vi.mocked(datasetsApi.tryChecks).mockResolvedValue({ rows: 2000, results: [
      { id: 1, kind: 'rule', column: 'margin_pct', severity: 'warn', passed: false, failing: 3, detail: null },
      { id: 2, kind: 'not_null', column: 'region', severity: 'warn', passed: true, detail: null },
    ] })
    show({ checks: [
      { id: 1, kind: 'rule', column: 'margin_pct', params: { expression: 'margin_pct <= 100' }, severity: 'warn', enabled: true, created_at: null },
      { id: 2, kind: 'not_null', column: 'region', severity: 'warn', enabled: true, created_at: null },
    ] })
    await waitFor(() => expect(screen.getByTestId('trust-checks')).toHaveTextContent(/1 of 2 saved checks pass — “.*margin_pct <= 100.*” fails on 3 rows/))
    expect(screen.getByText('1 check fails')).toBeInTheDocument()
    expect(screen.getByText('margin_pct').closest('tr')).toHaveAttribute('data-flagged', 'true')
  })

  it('offers Certify to admins only', () => {
    show({ isAdmin: true })
    expect(within(screen.getByTestId('trust-cert')).getByRole('button', { name: 'Certify' })).toBeInTheDocument()
  })
})

describe('Overview columns at a glance (3b)', () => {
  it('draws a range bar for numbers, top values for text and a range for dates', () => {
    show()
    const glance = screen.getByTestId('overview-glance')
    expect(within(glance).getByText('-4.1 – 104.2 · median 19')).toBeInTheDocument()
    expect(within(glance).getByText('4 values')).toBeInTheDocument()
    expect(within(glance).getByText('Asia Pacific')).toBeInTheDocument()
    expect(glance.querySelector('.dl-ov__range')).not.toBeNull()
  })

  it('offers to profile when there is no saved profile, and says so when it fails', () => {
    const p = show({ analysis: null })
    fireEvent.click(screen.getByRole('button', { name: 'Profile the columns' }))
    expect(p.onProfile).toHaveBeenCalled()
  })

  it('shows the failure with Retry profile and Open the data', () => {
    const p = show({ analysis: null, profileError: 'timeout after 60 s' })
    expect(screen.getByRole('alert')).toHaveTextContent('The profile couldn’t be calculated')
    fireEvent.click(screen.getByRole('button', { name: 'Open the data' }))
    expect(p.goTab).toHaveBeenCalledWith('data')
  })

  it('an empty dataset is not usable yet, and lists its columns', () => {
    show({ ds: { ...DS, row_count: 0 } as Dataset })
    expect(screen.getByText('Not usable yet')).toBeInTheDocument()
    expect(screen.getByText('This dataset has columns but no rows')).toBeInTheDocument()
    expect(screen.getByTestId('trust-cert')).toHaveTextContent('Can’t certify an empty dataset')
  })
})

describe('Overview side column (3b)', () => {
  it('lists dashboards and alerts that use it, and the lineage', async () => {
    show({ alerts: [{ id: 3, name: 'Margin below target', expression: '', interval_minutes: 60, recipients: [], last_state: null } as never] })
    const used = screen.getByTestId('overview-used-by')
    expect(await within(used).findByRole('link', { name: 'Sales Overview' })).toHaveAttribute('href', '/reports/10')
    expect(within(used).getByText('Margin below target')).toBeInTheDocument()
    expect(within(screen.getByTestId('overview-lineage')).getByText('1 dashboards')).toBeInTheDocument()
  })

  it('first run: three next steps', () => {
    const p = show({ firstRun: true })
    expect(screen.getByText('Your data is in')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Build something/ }))
    expect(p.onBuild).toHaveBeenCalled()
  })
})

describe('Overview recent activity (3b)', () => {
  it('is hidden from non-admins, who never call the audit endpoints', async () => {
    show({ isAdmin: false })
    await waitFor(() => expect(lineageApi.graph).toHaveBeenCalled())
    expect(screen.queryByTestId('overview-activity')).toBeNull()
    expect(monitoringApi.activity).not.toHaveBeenCalled()
    expect(adminAuditApi.list).not.toHaveBeenCalled()
  })

  it('calls each log once with limit 200 and keeps only this exact dataset', async () => {
    vi.mocked(monitoringApi.activity).mockResolvedValue([
      { id: 1, user_email: 'me@x.io', action: 'dataset.upload', entity: 'dataset', entity_id: 1, detail: null, created_at: hoursAgo(2) },
      { id: 2, user_email: 'a@x.io', action: 'dataset.upload', entity: 'dataset', entity_id: 12, detail: null, created_at: hoursAgo(1) },
    ])
    vi.mocked(adminAuditApi.list).mockResolvedValue([
      { id: 7, actor_email: 'me@x.io', action: 'dataset_share.create', target: 'dataset:1', detail: 'omar@x.io', created_at: hoursAgo(1) },
      { id: 8, actor_email: 'me@x.io', action: 'dataset_share.create', target: 'dataset:12', detail: 'z@x.io', created_at: hoursAgo(0.5) },
    ])
    show({ isAdmin: true })
    const card = await screen.findByTestId('overview-activity')
    await waitFor(() => expect(within(card).getAllByRole('listitem')).toHaveLength(2))
    expect(monitoringApi.activity).toHaveBeenCalledWith(200)
    expect(adminAuditApi.list).toHaveBeenCalledWith({ limit: 200, q: 'dataset:1' })
    expect(card).toHaveTextContent('You shared it omar@x.io')
    expect(card).toHaveTextContent('You uploaded it')
    expect(card).not.toHaveTextContent('z@x.io')
    expect(within(card).getByRole('link', { name: 'View in Audit' })).toHaveAttribute('href', '/admin/audit')
  })

  it('says so when nothing was recorded', async () => {
    show({ isAdmin: true })
    expect(await screen.findByText('No recent changes recorded')).toBeInTheDocument()
  })
})

describe('Overview number formats (3b)', () => {
  it('shows a year column without thousands separators', () => {
    show({ ds: { ...DS, columns: [{ id: 9, name: 'year', dtype: 'numeric', missing_pct: 0, stats: {} }] } as Dataset,
      analysis: { numeric: { columns: { year: { min: 2024, p5: 2024, p25: 2024, median: 2024, p75: 2025, p95: 2025, max: 2025 } } } } })
    expect(screen.getByText('2024 – 2025 · median 2024')).toBeInTheDocument()
  })
})
