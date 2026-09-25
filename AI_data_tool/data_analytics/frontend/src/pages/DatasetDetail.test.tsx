import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders as render, screen, waitFor, fireEvent } from '../test/renderWithProviders'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import DatasetDetail from './DatasetDetail'
import { datasetsApi, analysisApi, dataPreviewApi } from '../services/api'
import { AuthContext } from '../contexts/AuthContext'
import type { Dataset, User } from '../services/api'
import { axeViolations } from '../test/axe'

vi.mock('../services/api', () => ({
  datasetsApi: { get: vi.fn(), refresh: vi.fn(), setSchedule: vi.fn(),
                 list: vi.fn().mockResolvedValue([]) },
  analysisApi: { get: vi.fn(), run: vi.fn(), segment: vi.fn(), keyInfluencers: vi.fn(), associationRules: vi.fn() },
  insightsApi: { run: vi.fn() },
  // Phase 7.6: the "Use in Python" snippet reads the API origin.
  api: { defaults: { baseURL: 'http://localhost:8000/api/v1' } },
  // Phase 7.3: the header's sensitivity control.
  sensitivityApi: { get: vi.fn().mockResolvedValue({ label: null, effective: null, reasons: [],
    options: ['Public', 'Internal', 'Confidential', 'Restricted'], redacted_on_share: [] }), set: vi.fn() },
  widgetDataApi: { query: vi.fn() },
  dataPreviewApi: { query: vi.fn() },
  filterExprApi: { update: vi.fn(), preview: vi.fn() },
  calcColumnsApi: { list: vi.fn().mockResolvedValue([]), save: vi.fn(), delete: vi.fn() },
  customFunctionsApi: { list: vi.fn().mockResolvedValue([]), save: vi.fn(), delete: vi.fn(), preview: vi.fn() },
  measuresApi: { list: vi.fn().mockResolvedValue([]), save: vi.fn(), delete: vi.fn(), preview: vi.fn() },
  dataSourcesApi: { list: vi.fn().mockResolvedValue([{ id: 5, name: 'Shop DB', type: 'sqlite', config: {} }]) },
  prepApi: { get: vi.fn().mockResolvedValue([]), set: vi.fn(), preview: vi.fn(),
             materialize: vi.fn(), rebuild: vi.fn() },
  // The prep panel reads these to suggest join keys.
  relationshipsApi: { list: vi.fn().mockResolvedValue([]) },
  adminUsersApi: { list: vi.fn().mockResolvedValue([]) },
  datasetSharesApi: { list: vi.fn().mockResolvedValue([]), create: vi.fn(), delete: vi.fn() },
  reportsApi: { create: vi.fn() },
}))

// Rendering the real QueryBuilderDialog would require its own full mock setup
// (schema/columns/compile) that is irrelevant to this page's "Edit query"
// gating -- stub it so these tests only assert the button's visibility/wiring.
vi.mock('../components/QueryBuilderDialog', () => ({
  default: (props: { existing?: { id: number; name: string } }) =>
    props.existing ? <div data-testid="qb-dialog">editing {props.existing.name}</div> : null,
}))

// clears CALL COUNTS only (implementations survive): the gating tests assert
// not-called, and calls from earlier describes must not leak into them.
// Segment/patterns/influencers now auto-run on every mount (no click
// required), so EVERY test that renders DatasetDetail triggers them in the
// background whether it cares or not -- an un-configured `vi.fn()` returns
// undefined, and `.then()` on that throws inside the effect and blanks the
// whole render. These three defaults keep tests that don't care about that
// analysis from crashing on it; tests that DO care still override per-test.
beforeEach(async () => {
  vi.clearAllMocks()
  vi.mocked(analysisApi.segment).mockResolvedValue(null as any)
  vi.mocked(analysisApi.associationRules).mockResolvedValue(null as any)
  vi.mocked(analysisApi.keyInfluencers).mockResolvedValue(null as any)
  const { widgetDataApi } = await import('../services/api')
  vi.mocked(widgetDataApi.query).mockResolvedValue({ rows: [] } as any)
})

function directQueryDataset(): Dataset {
  return {
    id: 28, name: 'Live Sales', row_count: 0, col_count: 2, file_size: 0,
    created_at: '2026-01-01', updated_at: '2026-01-01', columns: [],
    calculated_columns: [], measures: [], column_meta: {}, column_formats: {}, data_source_id: 5, mode: 'directquery',
  }
}

function importDataset(): Dataset {
  return {
    id: 29, name: 'CSV Upload', row_count: 10, col_count: 2, file_size: 100,
    created_at: '2026-01-01', updated_at: '2026-01-01', columns: [],
    calculated_columns: [], measures: [], column_meta: {}, column_formats: {}, data_source_id: 5, mode: 'import',
  }
}

function renderDetail(dsId: number) {
  return render(
    <MemoryRouter initialEntries={[`/datasets/${dsId}`]}>
      <Routes><Route path="/datasets/:id" element={<DatasetDetail />} /></Routes>
    </MemoryRouter>
  )
}

function adminAuthValue(): { user: User; loading: boolean; login: () => Promise<void>; logout: () => void } {
  return {
    user: { id: 1, email: 'admin@example.com', is_active: true,
      organization: { id: 1, name: 'Org' } as any, role: { id: 1, name: 'Admin', is_org_admin: true } },
    loading: false, login: vi.fn(), logout: vi.fn(),
  }
}

function renderDetailAsAdmin(dsId: number) {
  return render(
    <AuthContext.Provider value={adminAuthValue()}>
      <MemoryRouter initialEntries={[`/datasets/${dsId}`]}>
        <Routes><Route path="/datasets/:id" element={<DatasetDetail />} /></Routes>
      </MemoryRouter>
    </AuthContext.Provider>
  )
}

describe('DatasetDetail insights engine', () => {
  it('generates ranked findings and the narrative on demand', async () => {
    const { insightsApi } = await import('../services/api')
    vi.mocked(datasetsApi.get).mockResolvedValue(importDataset())
    vi.mocked(analysisApi.get).mockRejectedValue(new Error('none'))
    vi.mocked(insightsApi.run).mockResolvedValue({
      narrative: 'Across 2,000 rows: Software carries 40% of revenue.',
      findings: [
        { kind: 'standout', score: 0.8, title: 'Software carries 40% of revenue', detail: '3 values of category…', columns: ['category', 'revenue'] },
        { kind: 'data_quality', score: 0.5, title: 'notes is 52% missing', detail: 'Aggregations ignore the gaps.', columns: ['notes'] },
      ],
    })
    renderDetail(29)
    fireEvent.click(await screen.findByRole('button', { name: /Generate insights/ }))
    expect(await screen.findByTestId('insights-narrative')).toHaveTextContent('Across 2,000 rows')
    expect(screen.getByTestId('insight-standout')).toHaveTextContent('Software carries 40% of revenue')
    expect(screen.getByTestId('insight-data_quality')).toHaveTextContent('52% missing')
  })

  it('charts a finding inline once its column pairing is known', async () => {
    const { insightsApi, widgetDataApi } = await import('../services/api')
    const ds = importDataset()
    ds.columns = [{ name: 'category', dtype: 'categorical' } as any, { name: 'revenue', dtype: 'numeric' } as any]
    vi.mocked(datasetsApi.get).mockResolvedValue(ds)
    vi.mocked(analysisApi.get).mockRejectedValue(new Error('none'))
    vi.mocked(insightsApi.run).mockResolvedValue({
      narrative: 'n',
      findings: [
        { kind: 'standout', score: 0.8, title: 'Software carries 40% of revenue', detail: 'd', columns: ['category', 'revenue'] },
      ],
    })
    vi.mocked(widgetDataApi.query).mockResolvedValue({
      rows: [{ name: 'Software', value: 40 }, { name: 'Hardware', value: 10 }],
    } as any)

    renderDetail(29)
    fireEvent.click(await screen.findByRole('button', { name: /Generate insights/ }))

    expect(await screen.findByTestId('insight-standout'))
    await waitFor(() => expect(screen.getAllByTestId('mini-bar-row')).toHaveLength(2))
    expect(widgetDataApi.query).toHaveBeenCalledWith(
      29, { dimension: 'category', measure: 'revenue', aggregation: 'sum' }, [], 'bar')
  })
})

describe('DatasetDetail date & time profiling', () => {
  it('renders the datetime section with range, granularity and distributions', async () => {
    vi.mocked(datasetsApi.get).mockResolvedValue(importDataset())
    vi.mocked(analysisApi.get).mockResolvedValue({
      results: {},
      numeric: { columns: {} },
      categorical: { columns: {} },
      datetime: { columns: { order_date: {
        min: '2026-01-01 00:00:00', max: '2026-03-31 00:00:00', range_days: 89,
        n_values: 90, n_unique: 90, missing_pct: 0, gaps_over_7d: 0,
        granularity: 'date',
        weekday_counts: [
          { day: 'Mon', count: 13 }, { day: 'Tue', count: 13 }, { day: 'Wed', count: 13 },
          { day: 'Thu', count: 13 }, { day: 'Fri', count: 13 }, { day: 'Sat', count: 13 }, { day: 'Sun', count: 12 }],
        monthly_counts: [{ period: '2026-01', count: 31 }, { period: '2026-02', count: 28 }, { period: '2026-03', count: 31 }],
        busiest_period: { period: '2026-01', count: 31 },
      } } },
      overview: { rows: 90, cols: 2, missing_pct: 0, type_counts: {} },
    } as never)
    renderDetail(29)
    const card = await screen.findByTestId('dt-card-order_date')
    expect(card).toHaveTextContent('order_date')
    expect(card).toHaveTextContent('date')                       // granularity badge
    expect(card).toHaveTextContent('2026-01-01 → 2026-03-31')    // date-only slice
    expect(card).toHaveTextContent('89d span')
    expect(card).toHaveTextContent(`busiest 2026-01 (${(31).toLocaleString()})`)
  })

  it('renders the note for an unparseable column instead of crashing', async () => {
    vi.mocked(datasetsApi.get).mockResolvedValue(importDataset())
    vi.mocked(analysisApi.get).mockResolvedValue({
      numeric: { columns: {} }, categorical: { columns: {} },
      datetime: { columns: { junk: { note: 'no parseable date values' } } },
      overview: { rows: 1, cols: 1, missing_pct: 0, type_counts: {} },
    } as never)
    renderDetail(29)
    expect(await screen.findByText('no parseable date values')).toBeInTheDocument()
  })
})

describe('DatasetDetail segment (A2)', () => {
  it('auto-runs segmentation on arrival and renders per-cluster centroid rows, with no click needed', async () => {
    vi.mocked(datasetsApi.get).mockResolvedValue(importDataset())
    vi.mocked(analysisApi.get).mockRejectedValue(new Error('none'))
    vi.mocked(analysisApi.segment).mockResolvedValue({
      kind: 'segment',
      columns: [{ name: 'x', dtype: 'numeric' }, { name: 'y', dtype: 'numeric' }],
      rows: [{ row_index: 0, cluster: 0 }, { row_index: 1, cluster: 1 }],
      meta: {
        method: 'kmeans',
        params: { k: 2, k_range: [2, 8], columns: ['x', 'y'], random_state: 42 },
        silhouette: 0.87,
        centroids: [{ cluster: 0, size: 5, x: 1.23, y: 4.56 }, { cluster: 1, size: 5, x: 9.87, y: 6.54 }],
        n_rows_used: 10, n_rows_total: 10,
      },
      warnings: [],
    })

    renderDetail(29)

    expect(await screen.findByText(/k = 2 clusters/)).toBeInTheDocument()
    expect(screen.getByText(/silhouette 0.870/)).toBeInTheDocument()
    expect(screen.getByText('1.23')).toBeInTheDocument()
    expect(screen.getByText('9.87')).toBeInTheDocument()
    expect(analysisApi.segment).toHaveBeenCalledTimes(1)
  })

  it('the "Re-run segmentation" button still works after the automatic run', async () => {
    vi.mocked(datasetsApi.get).mockResolvedValue(importDataset())
    vi.mocked(analysisApi.get).mockRejectedValue(new Error('none'))
    vi.mocked(analysisApi.segment).mockResolvedValue({
      kind: 'segment', columns: [], rows: [],
      meta: { method: 'kmeans', params: { k: 2, k_range: [2, 8], columns: ['x'], random_state: 42 },
        silhouette: 0.5, centroids: [], n_rows_used: 1, n_rows_total: 1 },
      warnings: [],
    })
    renderDetail(29)
    await screen.findByRole('button', { name: /Re-run segmentation/ })

    fireEvent.click(screen.getByRole('button', { name: /Re-run segmentation/ }))

    await waitFor(() => expect(analysisApi.segment).toHaveBeenCalledTimes(2))
  })

  it('shows the 400 error message from the automatic run when the dataset is degenerate', async () => {
    vi.mocked(datasetsApi.get).mockResolvedValue(importDataset())
    vi.mocked(analysisApi.get).mockRejectedValue(new Error('none'))
    vi.mocked(analysisApi.segment).mockRejectedValue({ response: { data: { detail: 'Segmentation needs at least 2 usable numeric columns' } } })

    renderDetail(29)

    expect(await screen.findByText('Segmentation needs at least 2 usable numeric columns')).toBeInTheDocument()
  })

  it('does not offer segmentation for a DirectQuery dataset', async () => {
    vi.mocked(datasetsApi.get).mockResolvedValue(directQueryDataset())

    renderDetail(28)

    await screen.findByText('Live Sales')
    expect(screen.queryByRole('button', { name: /Segment rows/ })).not.toBeInTheDocument()
    expect(analysisApi.segment).not.toHaveBeenCalled()
  })
})

describe('DatasetDetail patterns / association rules', () => {
  const RULES_RESULT = {
    kind: 'association_rules' as const,
    columns: [],
    rows: [{ if: 'region = West', then: 'channel = Online', lift: 1.8, confidence: 0.62, base_rate: 0.34, support_rows: 120, support_pct: 0.15 }],
    meta: {},
    warnings: [],
  }

  it('auto-runs pattern mining on arrival, with no click needed', async () => {
    vi.mocked(datasetsApi.get).mockResolvedValue(importDataset())
    vi.mocked(analysisApi.get).mockRejectedValue(new Error('none'))
    vi.mocked(analysisApi.associationRules).mockResolvedValue(RULES_RESULT)

    renderDetail(29)

    expect(await screen.findByText('region = West')).toBeInTheDocument()
    expect(analysisApi.associationRules).toHaveBeenCalledTimes(1)
    expect(analysisApi.associationRules).toHaveBeenCalledWith(29)
  })

  it('the "Re-run" button still works after the automatic run', async () => {
    vi.mocked(datasetsApi.get).mockResolvedValue(importDataset())
    vi.mocked(analysisApi.get).mockRejectedValue(new Error('none'))
    vi.mocked(analysisApi.associationRules).mockResolvedValue(RULES_RESULT)
    renderDetail(29)
    await screen.findByRole('button', { name: /Re-run/ })

    fireEvent.click(screen.getByRole('button', { name: /Re-run/ }))

    await waitFor(() => expect(analysisApi.associationRules).toHaveBeenCalledTimes(2))
  })

  it('shows the server error from the automatic run', async () => {
    vi.mocked(datasetsApi.get).mockResolvedValue(importDataset())
    vi.mocked(analysisApi.get).mockRejectedValue(new Error('none'))
    vi.mocked(analysisApi.associationRules).mockRejectedValue({ response: { data: { detail: 'Too few rows to mine' } } })

    renderDetail(29)

    expect(await screen.findByText('Too few rows to mine')).toBeInTheDocument()
  })

  it('still auto-runs for a DirectQuery dataset -- the backend genuinely supports it', async () => {
    const ds = directQueryDataset()
    vi.mocked(datasetsApi.get).mockResolvedValue(ds)
    vi.mocked(analysisApi.associationRules).mockResolvedValue(RULES_RESULT)

    renderDetail(28)

    expect(await screen.findByText('region = West')).toBeInTheDocument()
  })
})

describe('DatasetDetail DirectQuery gating', () => {
  it('does not call analysisApi.get for a DirectQuery dataset', async () => {
    vi.mocked(datasetsApi.get).mockResolvedValue(directQueryDataset())

    renderDetail(28)

    await screen.findByText('Live Sales')
    expect(analysisApi.get).not.toHaveBeenCalled()
  })

  it('still calls analysisApi.get for an import-mode dataset', async () => {
    vi.mocked(datasetsApi.get).mockResolvedValue(importDataset())
    vi.mocked(analysisApi.get).mockRejectedValue(new Error('no analysis yet'))

    renderDetail(29)

    await screen.findByText('CSV Upload')
    await waitFor(() => expect(analysisApi.get).toHaveBeenCalledWith(29))
  })

  it('hides the "Refresh from source" button for a DirectQuery dataset', async () => {
    vi.mocked(datasetsApi.get).mockResolvedValue(directQueryDataset())

    renderDetail(28)

    await screen.findByText('Live Sales')
    expect(screen.queryByText(/Refresh from source/)).not.toBeInTheDocument()
  })

  it('shows the "Refresh from source" button for an import-mode dataset with a data source', async () => {
    vi.mocked(datasetsApi.get).mockResolvedValue(importDataset())
    vi.mocked(analysisApi.get).mockRejectedValue(new Error('no analysis yet'))

    renderDetail(29)

    await screen.findByText(/Refresh from source/)
  })

  it('shows the "Run analysis" button for a DirectQuery dataset', async () => {
    vi.mocked(datasetsApi.get).mockResolvedValue(directQueryDataset())

    renderDetail(28)

    await screen.findByText('Live Sales')
    expect(await screen.findByRole('button', { name: /Run analysis/ })).toBeInTheDocument()
  })

  it('shows a sample-based note after running analysis on a DirectQuery dataset', async () => {
    vi.mocked(datasetsApi.get).mockResolvedValue(directQueryDataset())
    vi.mocked(analysisApi.run).mockResolvedValue({
      overview: { rows: 10000, cols: 2, missing_pct: 0, type_counts: {} },
      sampled: true, sample_size: 10000, total_rows: 50000,
    })

    renderDetail(28)
    await screen.findByText('Live Sales')
    screen.getByRole('button', { name: /Run analysis/ }).click()

    expect(await screen.findByText(/sample/i)).toBeInTheDocument()
  })

  it('calls dataPreviewApi.query on the Data tab for a DirectQuery dataset, ignoring filters', async () => {
    vi.mocked(datasetsApi.get).mockResolvedValue(directQueryDataset())
    vi.mocked(dataPreviewApi.query).mockResolvedValue({ columns: ['region'], rows: [['north']], total: 1 })

    renderDetail(28)
    await screen.findByText('Live Sales')
    screen.getByRole('tab', { name: 'Data' }).click()

    await waitFor(() => expect(dataPreviewApi.query).toHaveBeenCalledWith(28, [], [], 100, 0))
    expect(await screen.findByText('north')).toBeInTheDocument()
  })

  it('shows a shared empty state instead of a bare table with no rows when the preview matches nothing', async () => {
    vi.mocked(datasetsApi.get).mockResolvedValue(directQueryDataset())
    vi.mocked(dataPreviewApi.query).mockResolvedValue({ columns: ['region'], rows: [], total: 0 })

    renderDetail(28)
    await screen.findByText('Live Sales')
    screen.getByRole('tab', { name: 'Data' }).click()

    await waitFor(() => expect(dataPreviewApi.query).toHaveBeenCalled())
    expect(await screen.findByText(/no rows match/i)).toBeInTheDocument()
  })
})

describe('DatasetDetail source-backed re-import link', () => {
  it('links to the specific connection, not the generic Connections list, when the file is missing', async () => {
    vi.mocked(datasetsApi.get).mockResolvedValue(importDataset())  // data_source_id: 5, no source_table/source_query
    vi.mocked(dataPreviewApi.query).mockRejectedValue({ response: { data: { detail: 'Dataset file not found' } } })

    renderDetail(29)
    await screen.findByText('CSV Upload')
    fireEvent.click(screen.getByRole('tab', { name: 'Data' }))

    const link = await screen.findByRole('link', { name: /Re-import from this connection/ })
    expect(link).toHaveAttribute('href', '/connections/5/review')
    expect(screen.queryByRole('link', { name: /^Re-import from Connections$/ })).not.toBeInTheDocument()
  })
})

describe('DatasetDetail "Edit query" (D1)', () => {
  it('hides "Edit query" for a dataset with no saved query_model (upload / hand-SQL)', async () => {
    vi.mocked(datasetsApi.get).mockResolvedValue(importDataset())  // no query_model
    renderDetail(29)
    await screen.findByText('CSV Upload')
    expect(screen.queryByRole('button', { name: /Edit query/ })).not.toBeInTheDocument()
  })

  it('shows "Edit query" for a builder-created dataset and opens it hydrated', async () => {
    vi.mocked(datasetsApi.get).mockResolvedValue({
      ...importDataset(), query_model: { table: 'orders', columns: [{ column: 'region' }] },
    })
    renderDetail(29)
    const btn = await screen.findByRole('button', { name: /Edit query/ })
    fireEvent.click(btn)
    expect(await screen.findByTestId('qb-dialog')).toHaveTextContent('editing CSV Upload')
  })
})

describe('DatasetDetail sharing (SH1)', () => {
  it('hides the Share button for a non-admin (no auth context)', async () => {
    vi.mocked(datasetsApi.get).mockResolvedValue(importDataset())
    renderDetail(29)
    await screen.findByText('CSV Upload')
    expect(screen.queryByRole('button', { name: 'Share' })).not.toBeInTheDocument()
  })

  it('shows the Share button for an org admin and opens the share dialog', async () => {
    vi.mocked(datasetsApi.get).mockResolvedValue(importDataset())
    renderDetailAsAdmin(29)
    await screen.findByText('CSV Upload')

    fireEvent.click(await screen.findByRole('button', { name: 'Share' }))

    expect(await screen.findByRole('dialog', { name: 'Share dataset' })).toBeInTheDocument()
  })

  it('shows the "Shared with you" badge when the viewer has a share grant', async () => {
    vi.mocked(datasetsApi.get).mockResolvedValue({ ...importDataset(), shared: true })
    renderDetail(29)
    expect(await screen.findByText(/Shared with you/)).toBeInTheDocument()
  })
})

describe('DatasetDetail key influencers', () => {
  /**
   * "What drives churn?" answered without a data scientist. The panel has one
   * job beyond showing numbers: never let a lift be read as good news when the
   * outcome is bad, and never let it be read as causation.
   */
  const result = {
    kind: 'key_influencers' as const,
    columns: [{ name: 'plan', dtype: 'object' }],
    rows: [
      { factor: 'support', group: 'many', grouped_by: 'value' as const,
        rate: 0.455, baseline: 0.236, lift: 1.92, rows: 121, share_of_rows: 0.15 },
      { factor: 'plan', group: 'Pro', grouped_by: 'value' as const,
        rate: 0.09, baseline: 0.236, lift: 0.38, rows: 244, share_of_rows: 0.3 },
    ],
    meta: {
      method: 'group lift against baseline', target: 'churned', target_value: 'yes',
      measure: 'rate' as const, baseline: 0.236, n_rows_used: 800, n_rows_total: 800,
      sampled: false, groups_considered: 6,
      caveat: 'These factors move with the outcome; that is not proof they cause it.',
    },
    warnings: [],
  }

  const withChurnColumns = () => {
    const ds = importDataset()
    ds.columns = [
      { id: 1, name: 'churned', dtype: 'categorical', missing_pct: 0, stats: {} },
      { id: 2, name: 'plan', dtype: 'categorical', missing_pct: 0, stats: {} },
    ]
    vi.mocked(datasetsApi.get).mockResolvedValue(ds)
    vi.mocked(analysisApi.get).mockResolvedValue(null)
    return ds
  }

  const openAndRun = async () => {
    withChurnColumns()
    vi.mocked(analysisApi.keyInfluencers).mockResolvedValue(result)
    renderDetail(29)
    fireEvent.change(await screen.findByLabelText('Outcome to explain'),
                     { target: { value: 'churned' } })
    fireEvent.click(screen.getByRole('button', { name: /What drives this/ }))
    return screen.findByText(/is many/)
  }

  it('asks for an outcome before it will run', async () => {
    withChurnColumns()
    renderDetail(29)
    await screen.findByLabelText('Outcome to explain')
    const btn = screen.getByRole('button', { name: /What drives this/ }) as HTMLButtonElement
    expect(btn.disabled).toBe(true)
  })

  it('lists each influencer as a readable rule', async () => {
    await openAndRun()
    expect(screen.getByText(/is many/)).toBeInTheDocument()
    expect(screen.getByText('45.5%')).toBeInTheDocument()
  })

  it('says whether a factor raises or lowers the outcome', async () => {
    // "1.92x" alone reads as good news even when the outcome is churn.
    await openAndRun()
    expect(screen.getByText(/1\.92× more/)).toBeInTheDocument()
    expect(screen.getByText(/0\.38× less/)).toBeInTheDocument()
  })

  it('always shows the not-causation caveat', async () => {
    await openAndRun()
    expect(screen.getByText(/not proof they cause it/)).toBeInTheDocument()
  })

  it('surfaces the server message when it refuses', async () => {
    withChurnColumns()
    vi.mocked(analysisApi.keyInfluencers).mockRejectedValue({
      response: { data: { detail: "'churned' has only one value" } },
    })
    renderDetail(29)
    fireEvent.change(await screen.findByLabelText('Outcome to explain'),
                     { target: { value: 'churned' } })
    fireEvent.click(screen.getByRole('button', { name: /What drives this/ }))
    expect(await screen.findByText(/only one value/)).toBeInTheDocument()
  })

  describe('auto-run with a numeric column present', () => {
    // withChurnColumns() has no numeric column at all, which is exactly why
    // every test above needs a manual outcome pick -- there is nothing to
    // default to. A dataset that DOES have one gets a free first run.
    const withRevenueColumn = () => {
      const ds = importDataset()
      ds.columns = [
        { id: 1, name: 'region', dtype: 'categorical', missing_pct: 0, stats: {} },
        { id: 2, name: 'revenue', dtype: 'numeric', missing_pct: 0, stats: {} },
      ]
      vi.mocked(datasetsApi.get).mockResolvedValue(ds)
      vi.mocked(analysisApi.get).mockResolvedValue(null)
      return ds
    }

    it('auto-selects the first numeric column as the outcome and auto-runs, with no click needed', async () => {
      withRevenueColumn()
      vi.mocked(analysisApi.keyInfluencers).mockResolvedValue(result)

      renderDetail(29)

      expect(await screen.findByText(/is many/)).toBeInTheDocument()
      expect(analysisApi.keyInfluencers).toHaveBeenCalledWith(29, 'revenue')
      expect(analysisApi.keyInfluencers).toHaveBeenCalledTimes(1)
      await waitFor(() => expect(
        (screen.getByLabelText('Outcome to explain') as HTMLSelectElement).value).toBe('revenue'))
    })

    it('skips an identifier-shaped numeric column and defaults to the first real one instead', async () => {
      // Observed live: a dataset whose first numeric column is a row index
      // ("sample_id") auto-selected it as the OUTCOME to explain -- a
      // technically-valid but useless first result ("what drives sample_id?"
      // is nobody's question). There is no cardinality/uniqueness signal
      // exposed to the frontend to detect this statistically, so the name
      // pattern is the honest, frontend-only signal available.
      const ds = importDataset()
      ds.columns = [
        { id: 1, name: 'sample_id', dtype: 'numeric', missing_pct: 0, stats: {} },
        { id: 2, name: 'id', dtype: 'numeric', missing_pct: 0, stats: {} },
        { id: 3, name: 'revenue', dtype: 'numeric', missing_pct: 0, stats: {} },
      ]
      vi.mocked(datasetsApi.get).mockResolvedValue(ds)
      vi.mocked(analysisApi.get).mockResolvedValue(null)
      vi.mocked(analysisApi.keyInfluencers).mockResolvedValue(result)

      renderDetail(29)

      expect(await screen.findByText(/is many/)).toBeInTheDocument()
      expect(analysisApi.keyInfluencers).toHaveBeenCalledWith(29, 'revenue')
    })

    it('falls back to an identifier-shaped column rather than staying manual, if it is the only numeric one', async () => {
      // An imperfect default beats none: the "Re-run" button is right there
      // to retarget once the reader sees it, and "no numeric column at all"
      // (the churn-columns case above) is the only situation left fully manual.
      const ds = importDataset()
      ds.columns = [{ id: 1, name: 'user_id', dtype: 'numeric', missing_pct: 0, stats: {} }]
      vi.mocked(datasetsApi.get).mockResolvedValue(ds)
      vi.mocked(analysisApi.get).mockResolvedValue(null)
      vi.mocked(analysisApi.keyInfluencers).mockResolvedValue(result)

      renderDetail(29)

      expect(await screen.findByText(/is many/)).toBeInTheDocument()
      expect(analysisApi.keyInfluencers).toHaveBeenCalledWith(29, 'user_id')
    })

    it('changing the outcome after the automatic run still re-runs manually', async () => {
      withRevenueColumn()
      vi.mocked(analysisApi.keyInfluencers).mockResolvedValue(result)
      renderDetail(29)
      await screen.findByText(/is many/)

      fireEvent.change(screen.getByLabelText('Outcome to explain'), { target: { value: 'region' } })
      fireEvent.click(screen.getByRole('button', { name: /What drives this/ }))

      await waitFor(() => expect(analysisApi.keyInfluencers).toHaveBeenCalledWith(29, 'region'))
    })
  })
})


/**
 * Automatic refresh: the interval was reachable only by an API call until now.
 *
 * The case worth pinning is the DERIVED dataset. The refresh block was gated on
 * `data_source_id`, which a derived dataset never has -- the same shape as the
 * backend bug where PATCH /refresh-schedule refused exactly the datasets it was
 * meant to serve. A test that only covered source-backed datasets would have
 * shipped that bug a second time, one layer up.
 */
describe('DatasetDetail automatic refresh', () => {
  function derivedDataset(over: Record<string, unknown> = {}): Dataset {
    return {
      id: 31, name: 'Joined', row_count: 5, col_count: 2, file_size: 50,
      created_at: '2026-01-01', updated_at: '2026-01-01', columns: [],
      calculated_columns: [], measures: [], column_formats: {},
      // No data_source_id at all -- that is what makes it derived.
      data_source_id: null, mode: 'import',
      column_meta: { __derived_from__: { source_dataset_id: 29, steps: [] } },
      ...over,
    } as unknown as Dataset
  }

  beforeEach(() => {
    vi.mocked(analysisApi.get).mockRejectedValue(new Error('none'))
    vi.mocked(dataPreviewApi.query).mockResolvedValue(
      { rows: [], total: 0, columns: [] } as never)
  })

  const openMenu = async () => {
    fireEvent.click(await screen.findByRole('button', { name: /Refresh/ }))
    return screen.findByLabelText('Automatic refresh interval')
  }

  it('offers an interval on a source-backed dataset', async () => {
    vi.mocked(datasetsApi.get).mockResolvedValue(importDataset())
    renderDetail(29)
    expect(await openMenu()).toBeInTheDocument()
  })

  it('offers an interval on a DERIVED dataset, which has no connection', async () => {
    vi.mocked(datasetsApi.get).mockResolvedValue(derivedDataset())
    renderDetail(31)
    expect(await openMenu()).toBeInTheDocument()
  })

  it('does not offer to re-read a source a derived dataset does not have', async () => {
    // The manual refresh posts to /refresh, which needs a connection. Offering
    // it here would be a button that can only fail.
    vi.mocked(datasetsApi.get).mockResolvedValue(derivedDataset())
    renderDetail(31)
    await openMenu()
    expect(screen.queryByText('Load mode')).toBeNull()
  })

  it('leaves a dataflow-owned output alone', async () => {
    // Its schedule lives on the dataflow, which drives every output together.
    // A second control here would let one output drift from its siblings.
    vi.mocked(datasetsApi.get).mockResolvedValue(derivedDataset({
      column_meta: { __derived_from__: { source_dataset_id: 29, dataflow_id: 7 } },
    }))
    renderDetail(31)
    await screen.findByText('Joined')
    expect(screen.queryByRole('button', { name: /Refresh/ })).toBeNull()
  })

  it('offers nothing for a plain upload, which has neither connection nor recipe', async () => {
    // Found by looking at the live stack: MOST datasets in the demo org are
    // plain uploads. The server refuses them ("not imported from a database
    // connection and has no recipe to replay"), so a control here would be one
    // that can only fail. The gate must require a source OR a recipe, never
    // just "not DirectQuery".
    vi.mocked(datasetsApi.get).mockResolvedValue(derivedDataset({
      data_source_id: null, column_meta: {},
    }))
    renderDetail(31)
    await screen.findByText('Joined')
    expect(screen.queryByRole('button', { name: /Refresh/ })).toBeNull()
  })

  it('never offers a schedule for DirectQuery — nothing is cached to refresh', async () => {
    vi.mocked(datasetsApi.get).mockResolvedValue(directQueryDataset())
    renderDetail(28)
    await screen.findByText('Live Sales')
    expect(screen.queryByLabelText('Automatic refresh interval')).toBeNull()
  })

  it('saves the chosen interval', async () => {
    vi.mocked(datasetsApi.get).mockResolvedValue(importDataset())
    vi.mocked(datasetsApi.setSchedule).mockResolvedValue(
      { ...importDataset(), refresh_interval_minutes: 60 } as never)
    renderDetail(29)
    fireEvent.change(await openMenu(), { target: { value: '60' } })
    await waitFor(() => expect(datasetsApi.setSchedule).toHaveBeenCalledWith(29, 60))
  })

  it('clears the schedule with null rather than zero', async () => {
    // The server reads null as "off"; 0 would be an interval of no minutes.
    vi.mocked(datasetsApi.get).mockResolvedValue(
      { ...importDataset(), refresh_interval_minutes: 60 } as never)
    vi.mocked(datasetsApi.setSchedule).mockResolvedValue(importDataset() as never)
    renderDetail(29)
    fireEvent.change(await openMenu(), { target: { value: '' } })
    await waitFor(() => expect(datasetsApi.setSchedule).toHaveBeenCalledWith(29, null))
  })

  it('shows the server’s refusal rather than a generic failure', async () => {
    const detail = 'Minimum refresh interval is 5 minutes'
    vi.mocked(datasetsApi.get).mockResolvedValue(importDataset())
    vi.mocked(datasetsApi.setSchedule).mockRejectedValue(
      { response: { data: { detail } } } as never)
    renderDetail(29)
    fireEvent.change(await openMenu(), { target: { value: '5' } })
    await waitFor(() => expect(datasetsApi.setSchedule).toHaveBeenCalled())
  })
})

// ── Insights-hub deep links ──────────────────────────────────────────────────
// The hub's cards point at anchors and tab params on this page; these pin the
// receiving half of that contract. (vi.mock is hoisted, so the stub below
// applies file-wide -- no other test opens the Statistics tab.)
vi.mock('../components/StatisticsPanel', () => ({
  default: () => <div data-testid="statistics-panel" />,
}))
vi.mock('../components/dataset/AlertsPanel', () => ({
  default: () => <div data-testid="alerts-panel" />,
}))
vi.mock('../components/dataset/PredictionModelsPanel', () => ({
  default: () => <div data-testid="prediction-models-panel" />,
}))

function renderDetailAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes><Route path="/datasets/:id" element={<DatasetDetail />} /></Routes>
    </MemoryRouter>
  )
}

describe('DatasetDetail deep links from the Insights hub', () => {
  it('#anomalies lands on the Overview anomalies section', async () => {
    const ds = importDataset()
    ds.columns = [{ id: 1, name: 'revenue', dtype: 'numeric', missing_pct: 0, stats: {} } as any]
    vi.mocked(datasetsApi.get).mockResolvedValue(ds)
    vi.mocked(analysisApi.get).mockRejectedValue(new Error('none'))

    renderDetailAt('/datasets/29#anomalies')
    const heading = await screen.findByRole('heading', { name: 'Anomalies' })
    expect(heading.closest('section')).toHaveAttribute('id', 'anomalies')
    // The dialog's one external input is the column; the section owns it.
    expect(screen.getByLabelText('Column to inspect for outliers')).toBeInTheDocument()
  })

  it('hides Anomalies for a DirectQuery dataset, matching Insights and Segments', async () => {
    // /datasets/{id}/outlier-details hard-400s for mode=="directquery"
    // (backend/app/routers/datasets.py) -- identical guard to /insights and
    // /segment, both of which already hide their section for DirectQuery.
    // Anomalies didn't, so a DirectQuery user could pick a column and click
    // "Inspect outliers" straight into a guaranteed error.
    const ds = directQueryDataset()
    ds.columns = [{ id: 1, name: 'revenue', dtype: 'numeric', missing_pct: 0, stats: {} } as any]
    vi.mocked(datasetsApi.get).mockResolvedValue(ds)
    vi.mocked(analysisApi.get).mockRejectedValue(new Error('none'))

    renderDetail(28)
    await screen.findByText('Live Sales')
    expect(screen.queryByRole('heading', { name: 'Anomalies' })).toBeNull()
  })

  it('every hub anchor has a section to land on', async () => {
    // The linking half lives in InsightsHub.test.tsx; this is the receiving
    // half. A hub card pointing at an id this page stops rendering is a dead
    // link the router cannot see.
    const ds = importDataset()
    ds.columns = [{ id: 1, name: 'revenue', dtype: 'numeric', missing_pct: 0, stats: {} } as any]
    vi.mocked(datasetsApi.get).mockResolvedValue(ds)
    vi.mocked(analysisApi.get).mockRejectedValue(new Error('none'))

    const { container } = renderDetailAt('/datasets/29#insights')
    await screen.findByRole('heading', { name: 'Anomalies' })
    for (const id of ['insights', 'influencers', 'associations', 'segment', 'anomalies']) {
      expect(container.querySelector(`#${id}`), id).not.toBeNull()
    }
  })

  it('?tab=statistics opens the Statistics tab directly', async () => {
    vi.mocked(datasetsApi.get).mockResolvedValue(importDataset())
    vi.mocked(analysisApi.get).mockRejectedValue(new Error('none'))

    renderDetailAt('/datasets/29?tab=statistics')
    expect(await screen.findByTestId('statistics-panel')).toBeInTheDocument()
  })
})

describe('the alerts tab', () => {
  /**
   * The reachability half. `AlertsPanel` is tested next door and that says
   * nothing about whether anything renders it — which is exactly how the alert
   * endpoints came to run on every scheduler tick for months with no caller.
   * A panel nobody can open is a panel nobody has.
   */
  it('opens from the tab bar', async () => {
    renderDetailAt('/datasets/29')
    fireEvent.click(await screen.findByRole('tab', { name: /alerts/i }))
    expect(await screen.findByTestId('alerts-panel')).toBeInTheDocument()
  })

  it('the models tab has its own name, not the one next to it', async () => {
    // The tab labels ended in a catch-all `else`, so a fifth tab silently
    // rendered as "Alerts" -- two buttons, one name, and the wrong panel one
    // click away.
    renderDetailAt('/datasets/29')
    expect(await screen.findByRole('tab', { name: /models/i })).toBeInTheDocument()
    expect(screen.getAllByRole('tab', { name: /alerts/i })).toHaveLength(1)
  })

  it('the models tab opens from the tab bar', async () => {
    renderDetailAt('/datasets/29')
    fireEvent.click(await screen.findByRole('tab', { name: /models/i }))
    expect(await screen.findByTestId('prediction-models-panel')).toBeInTheDocument()
  })

  it('?tab=models opens it directly', async () => {
    renderDetailAt('/datasets/29?tab=models')
    expect(await screen.findByTestId('prediction-models-panel')).toBeInTheDocument()
  })

  it('?tab=alerts opens it directly, so a link can point at it', async () => {
    renderDetailAt('/datasets/29?tab=alerts')
    expect(await screen.findByTestId('alerts-panel')).toBeInTheDocument()
  })

  it('is not what an unknown tab falls back to', async () => {
    // `?tab=nonsense` must land on Overview, not on the newest tab added.
    renderDetailAt('/datasets/29?tab=nonsense')
    await waitFor(() =>
      expect(screen.queryByTestId('alerts-panel')).not.toBeInTheDocument())
  })
})

describe('editing a cell in the data grid', () => {
  /**
   * The SAS feature is "edit the source table in place". This types into the
   * grid the same way and records the correction as a prep step, so the file is
   * never rewritten and the change is visible in the pipeline. The merge rules
   * are unit-tested in lib/cellEdits.test.ts; these are the reachability half —
   * that a person can actually get from a wrong value on screen to a saved step.
   */
  function editable() {
    const ds = importDataset()
    ds.columns = [
      { id: 1, name: 'order_id', dtype: 'text', missing_pct: 0, stats: {} },
      { id: 2, name: 'region', dtype: 'text', missing_pct: 0, stats: {} },
    ] as never
    vi.mocked(datasetsApi.get).mockResolvedValue(ds)
    vi.mocked(analysisApi.get).mockRejectedValue(new Error('none'))
    vi.mocked(dataPreviewApi.query).mockResolvedValue({
      columns: ['order_id', 'region'],
      rows: [['A-1', 'Nrth'], ['A-2', 'South']],
      total: 2,
    } as never)
  }

  async function openDataTab() {
    renderDetailAt('/datasets/29?tab=data')
    return screen.findByText('Nrth')
  }

  it('does not turn cells into inputs until editing is switched on', async () => {
    // The Data tab is a reading surface first; a grid where every cell is a
    // text box invites corrections nobody meant to make.
    editable()
    await openDataTab()
    expect(screen.queryByLabelText(/edit region for A-1/i)).not.toBeInTheDocument()
  })

  it('saves a typed correction as an edit_cells prep step', async () => {
    editable()
    const { prepApi } = await import('../services/api')
    vi.mocked(prepApi.get).mockResolvedValue([])
    vi.mocked(prepApi.set).mockResolvedValue([] as never)

    await openDataTab()
    fireEvent.click(screen.getByRole('button', { name: /edit cells/i }))
    fireEvent.click(screen.getByText('Nrth'))
    const input = await screen.findByLabelText(/edit region for A-1/i)
    fireEvent.change(input, { target: { value: 'North' } })
    fireEvent.blur(input)

    await waitFor(() => expect(prepApi.set).toHaveBeenCalled())
    const [, steps] = vi.mocked(prepApi.set).mock.calls[0]
    expect(steps).toEqual([{ kind: 'edit_cells', key_column: 'order_id',
      column: 'region', edits: [{ key: 'A-1', value: 'North' }] }])
  })

  it('keeps the pipeline that was already there', async () => {
    // Saving the whole list wholesale is the prep contract; dropping the steps
    // the user already had would be a silent data change.
    editable()
    const { prepApi } = await import('../services/api')
    vi.mocked(prepApi.get).mockResolvedValue([{ kind: 'trim' }] as never)
    vi.mocked(prepApi.set).mockResolvedValue([] as never)

    await openDataTab()
    fireEvent.click(screen.getByRole('button', { name: /edit cells/i }))
    fireEvent.click(screen.getByText('Nrth'))
    fireEvent.change(await screen.findByLabelText(/edit region for A-1/i),
      { target: { value: 'North' } })
    fireEvent.blur(screen.getByLabelText(/edit region for A-1/i))

    await waitFor(() => expect(prepApi.set).toHaveBeenCalled())
    const [, steps] = vi.mocked(prepApi.set).mock.calls[0]
    expect((steps as { kind: string }[])[0]).toEqual({ kind: 'trim' })
  })

  it('reloads the data so the correction is on screen', async () => {
    editable()
    const { prepApi } = await import('../services/api')
    vi.mocked(prepApi.get).mockResolvedValue([])
    vi.mocked(prepApi.set).mockResolvedValue([] as never)

    await openDataTab()
    const before = vi.mocked(dataPreviewApi.query).mock.calls.length
    fireEvent.click(screen.getByRole('button', { name: /edit cells/i }))
    fireEvent.click(screen.getByText('Nrth'))
    fireEvent.change(await screen.findByLabelText(/edit region for A-1/i),
      { target: { value: 'North' } })
    fireEvent.blur(screen.getByLabelText(/edit region for A-1/i))

    await waitFor(() => expect(
      vi.mocked(dataPreviewApi.query).mock.calls.length).toBeGreaterThan(before))
  })

  it('saves nothing when the value was not changed', async () => {
    editable()
    const { prepApi } = await import('../services/api')
    vi.mocked(prepApi.get).mockResolvedValue([])
    vi.mocked(prepApi.set).mockResolvedValue([] as never)

    await openDataTab()
    fireEvent.click(screen.getByRole('button', { name: /edit cells/i }))
    fireEvent.click(screen.getByText('Nrth'))
    fireEvent.blur(await screen.findByLabelText(/edit region for A-1/i))

    await waitFor(() => expect(prepApi.set).not.toHaveBeenCalled())
  })

  it('will not edit the key column itself', async () => {
    // The key is how the edit finds its row; the backend refuses the step, so
    // offering the cell would be offering a guaranteed error.
    editable()
    await openDataTab()
    fireEvent.click(screen.getByRole('button', { name: /edit cells/i }))
    fireEvent.click(screen.getByText('A-1'))
    expect(screen.queryByLabelText(/edit order_id for A-1/i)).not.toBeInTheDocument()
  })

  it('is not offered for a DirectQuery dataset', async () => {
    // Prep steps do not run on DirectQuery: the correction would save and
    // never appear, which is worse than not offering it.
    const ds = directQueryDataset()
    vi.mocked(datasetsApi.get).mockResolvedValue(ds)
    vi.mocked(analysisApi.get).mockRejectedValue(new Error('none'))
    vi.mocked(dataPreviewApi.query).mockResolvedValue({
      columns: ['order_id', 'region'], rows: [['A-1', 'Nrth']], total: 1 } as never)

    renderDetailAt('/datasets/28?tab=data')
    await screen.findByText('Nrth')
    expect(screen.queryByRole('button', { name: /edit cells/i })).not.toBeInTheDocument()
  })

  it('says where the correction went', async () => {
    // Nobody should have to discover from the prep panel that their edit is a
    // pipeline step rather than a change to the file.
    editable()
    await openDataTab()
    fireEvent.click(screen.getByRole('button', { name: /edit cells/i }))
    expect(screen.getByText(/saved as a prep step/i)).toBeInTheDocument()
    expect(screen.getByText(/uploaded file is never changed/i)).toBeInTheDocument()
  })
})

describe('DatasetDetail: from data to a chart', () => {
  it('builds a dashboard on this dataset and opens it', async () => {
    const { reportsApi } = await import('../services/api')
    vi.mocked(datasetsApi.get).mockResolvedValue(importDataset())
    vi.mocked(analysisApi.get).mockRejectedValue(new Error('none'))
    vi.mocked(reportsApi.create).mockResolvedValue({ id: 321 } as never)
    render(
      <MemoryRouter initialEntries={['/datasets/29']}>
        <Routes>
          <Route path="/datasets/:id" element={<DatasetDetail />} />
          <Route path="/reports/:id" element={<div>report page</div>} />
        </Routes>
      </MemoryRouter>
    )
    fireEvent.click(await screen.findByRole('button', { name: /Build a dashboard/ }))
    expect(await screen.findByText('report page')).toBeInTheDocument()
    expect(reportsApi.create).toHaveBeenCalledWith({ name: 'CSV Upload', dataset_id: 29 })
  })
})

describe('DatasetDetail accessibility', () => {
  it('has no structural accessibility violations', async () => {
    vi.mocked(datasetsApi.get).mockResolvedValue(importDataset())
    vi.mocked(analysisApi.get).mockRejectedValue(new Error('none'))
    const { container } = renderDetail(29)
    await screen.findAllByText('CSV Upload')
    expect(await axeViolations(container)).toEqual([])
  })
})
