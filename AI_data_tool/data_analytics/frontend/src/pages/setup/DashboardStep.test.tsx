import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import DashboardStep from './DashboardStep'
import { reportsApi, setupApi, type SetupDashboardStep } from '../../services/api'
import { buildDashboard } from '../../lib/buildDashboard'

vi.mock('../../services/api', async (orig) => {
  const real = await orig<typeof import('../../services/api')>()
  return { ...real, setupApi: { dashboard: vi.fn(), suggestDashboards: vi.fn(), refineDashboard: vi.fn(), update: vi.fn() },
           reportsApi: { ...real.reportsApi, create: vi.fn() } }
})
vi.mock('../../lib/buildDashboard', () => ({ buildDashboard: vi.fn() }))

const step = (over: Partial<SetupDashboardStep['designs']> = {}): SetupDashboardStep => ({
  has_data: true, datasets: [{ id: 226, name: 'Cars 2015+' }],
  designs: { pending: false, failed: null, asked: true, report_id: null, items: [{
    id: 'd1', dataset_id: 226, dataset_name: 'Cars 2015+', history: [], derived: {},
    proposal: { title: 'Pricing & market', rationale: 'What a car is worth.', source: 'llm',
                widgets: [{ widget_type: 'slicer', title: 'Filter by fuel', config: {}, row_count: 0 },
                          { widget_type: 'kpi', title: 'Median price', why: 'Ignores extreme prices.', config: {}, row_count: 1 }] } as never,
  }], ...over },
})

const renderStep = () => render(
  <MemoryRouter initialEntries={['/setup/38']}>
    <Routes>
      <Route path="/setup/:id" element={<DashboardStep sourceId={38} onBack={vi.fn()} />} />
      <Route path="/reports/:id" element={<p>builder</p>} />
    </Routes>
  </MemoryRouter>)

beforeEach(() => vi.clearAllMocks())

describe('Guided setup — Dashboard', () => {
  it('shows each proposal with every chart and why it is there', async () => {
    vi.mocked(setupApi.dashboard).mockResolvedValue(step())
    renderStep()
    expect(await screen.findByRole('heading', { name: 'Pricing & market' })).toBeInTheDocument()
    expect(screen.getByText('Median price')).toBeInTheDocument()
    expect(screen.getByText(/Ignores extreme prices/)).toBeInTheDocument()
    expect(screen.getByText('1 chart')).toBeInTheDocument()
    expect(screen.getByText('1 filter')).toBeInTheDocument()
  })

  it('creates the dashboard, finishes the setup and opens the builder', async () => {
    vi.mocked(setupApi.dashboard).mockResolvedValue(step())
    vi.mocked(buildDashboard).mockResolvedValue(901)
    vi.mocked(setupApi.update).mockResolvedValue({} as never)
    renderStep()
    fireEvent.click(await screen.findByRole('button', { name: 'Create this dashboard' }))
    expect(await screen.findByText('builder')).toBeInTheDocument()
    expect(setupApi.update).toHaveBeenCalledWith(38, { report_id: 901, step: 'done' })
  })

  it('can start blank', async () => {
    vi.mocked(setupApi.dashboard).mockResolvedValue(step())
    vi.mocked(reportsApi.create).mockResolvedValue({ id: 902 } as never)
    vi.mocked(setupApi.update).mockResolvedValue({} as never)
    renderStep()
    fireEvent.click(await screen.findByRole('button', { name: 'Create a blank dashboard' }))
    await waitFor(() => expect(reportsApi.create).toHaveBeenCalledWith({ name: 'Cars 2015+ dashboard', dataset_id: 226 }))
  })

  it('changes a proposal by asking', async () => {
    vi.mocked(setupApi.dashboard).mockResolvedValue(step())
    vi.mocked(setupApi.refineDashboard).mockResolvedValue({ designs: step().designs })
    renderStep()
    fireEvent.click(await screen.findByRole('button', { name: 'Change it' }))
    fireEvent.change(screen.getByRole('textbox', { name: /Ask for a change/ }), { target: { value: 'add a map' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    await waitFor(() => expect(setupApi.refineDashboard).toHaveBeenCalledWith(38, 'd1', 'add a map', 'en'))
  })

  it('says it is designing while it works', async () => {
    vi.mocked(setupApi.dashboard).mockResolvedValue(step({ pending: true, items: [] }))
    renderStep()
    expect(await screen.findByText(/AI is designing dashboards/)).toBeInTheDocument()
  })
})
