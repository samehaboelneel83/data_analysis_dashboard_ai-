import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import DashboardStep from './DashboardStep'
import { reportsApi, setupApi, type SetupDashboardStep, type SetupDesign } from '../../services/api'
import { buildPages } from '../../lib/buildDashboard'

vi.mock('../../services/api', async (orig) => {
  const real = await orig<typeof import('../../services/api')>()
  return { ...real, setupApi: { dashboard: vi.fn(), suggestDashboards: vi.fn(), refineDashboard: vi.fn(),
                                designsUsed: vi.fn(), changeDemand: vi.fn() },
           reportsApi: { ...real.reportsApi, create: vi.fn() } }
})
vi.mock('../../lib/buildDashboard', () => ({ buildPages: vi.fn() }))

const design = (id: string, title: string): SetupDesign => ({
  id, dataset_id: 226, dataset_name: 'All parcels', history: [], derived: {},
  proposal: { title, rationale: 'Answers q1.', answer: `${title}: 17% of Express parcels arrive late.`, note: null, unanswered: [],
              widgets: [{ widget_type: 'text', title, config: { content: 'x' }, row_count: 1 },
                        { widget_type: 'kpi', title: 'Late share', why: 'The headline.', finding: '17.4', config: {}, row_count: 1 },
                        { widget_type: 'bar', title: 'Late by governorate', why: 'Where.', finding: 'Highest: Aswan (31); lowest: Cairo (12)',
                          config: {}, row_count: 16 }] } as never,
})

const step = (over: Partial<SetupDashboardStep['designs']> = {}): SetupDashboardStep => ({
  has_data: true, datasets: [{ id: 226, name: 'All parcels' }],
  demand: { pending: false, failed: null, written: true, sentence: 'Express parcels: how many are late, and where.',
            who: '', subject: 'Express parcels', questions: [], exclude: [], scope: [], source: 'ai', edits: [], language: 'en' },
  designs: { pending: false, failed: null, asked: true, report_id: null, used: [],
             items: [design('d1', 'Overview'), design('d2', 'Over time'), design('d3', 'The records')], ...over },
})

const renderStep = (onNewFlow = vi.fn()) => {
  render(
    <MemoryRouter initialEntries={['/setup/38']}>
      <Routes>
        <Route path="/setup/:id" element={<DashboardStep sourceId={38} flow={7} onBack={vi.fn()} onNewFlow={onNewFlow} />} />
        <Route path="/reports/:id" element={<p>builder</p>} />
      </Routes>
    </MemoryRouter>)
  return onNewFlow
}

beforeEach(() => vi.clearAllMocks())

describe('Guided setup — Dashboard', () => {
  it('shows each suggested page with its answer and what every chart shows', async () => {
    vi.mocked(setupApi.dashboard).mockResolvedValue(step())
    renderStep()
    expect(await screen.findByRole('heading', { name: 'Overview' })).toBeInTheDocument()
    expect(screen.getByText('Overview: 17% of Express parcels arrive late.')).toBeInTheDocument()
    expect(screen.getAllByText(/Highest: Aswan \(31\)/)).toHaveLength(3)
    // The answer block is not counted as a chart.
    expect(screen.getAllByText('2 charts')).toHaveLength(3)
    expect(screen.getByText('Express parcels: how many are late, and where.')).toBeInTheDocument()
    expect(setupApi.dashboard).toHaveBeenCalledWith(38, 'en', 7)
  })

  it('makes ONE dashboard whose pages are the suggestions ticked', async () => {
    vi.mocked(setupApi.dashboard).mockResolvedValue(step())
    vi.mocked(buildPages).mockResolvedValue(901)
    vi.mocked(setupApi.designsUsed).mockResolvedValue({} as never)
    renderStep()
    // Every suggestion starts ticked (persona test, plan 2.8); the person leaves one out.
    expect(await screen.findByRole('checkbox', { name: 'Use “Overview” as a page' })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: 'Use “The records” as a page' })).toBeChecked()
    fireEvent.click(screen.getByRole('checkbox', { name: 'Use “Over time” as a page' }))
    expect(screen.getByText('One dashboard with 2 pages.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Create my dashboard (2 pages)' }))
    expect(await screen.findByText('builder')).toBeInTheDocument()
    expect(buildPages).toHaveBeenCalledTimes(1)
    const [pages, name, description, reportId] = vi.mocked(buildPages).mock.calls[0]
    expect(pages.map(p => p.proposal.title)).toEqual(['Overview', 'The records'])
    expect(name).toBe('Express parcels')
    expect(description).toBe('Express parcels: how many are late, and where.')
    expect(reportId).toBeNull()
    expect(setupApi.designsUsed).toHaveBeenCalledWith(38, 901, ['d1', 'd3'], 7)
  })

  it('needs at least one page', async () => {
    vi.mocked(setupApi.dashboard).mockResolvedValue(step())
    renderStep()
    for (const name of ['Overview', 'Over time', 'The records']) {
      fireEvent.click(await screen.findByRole('checkbox', { name: `Use “${name}” as a page` }))
    }
    expect(screen.getByText('Tick at least one page.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Create my dashboard/ })).toBeDisabled()
  })

  it('adds more pages to the dashboard already made, never a second dashboard', async () => {
    vi.mocked(setupApi.dashboard).mockResolvedValue(step({ report_id: 901, used: ['d1'] }))
    vi.mocked(buildPages).mockResolvedValue(901)
    vi.mocked(setupApi.designsUsed).mockResolvedValue({} as never)
    renderStep()
    expect(await screen.findByText('Already a page')).toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: 'Use “Overview” as a page' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Add 1 page to my dashboard' }))
    await waitFor(() => expect(buildPages).toHaveBeenCalled())
    expect(vi.mocked(buildPages).mock.calls[0][3]).toBe(901)
    expect(vi.mocked(buildPages).mock.calls[0][0].map(p => p.proposal.title)).toEqual(['Over time'])
  })

  it('offers another analysis of the same database once the dashboard is made', async () => {
    vi.mocked(setupApi.dashboard).mockResolvedValue(step({ report_id: 901, used: ['d1'] }))
    const onNewFlow = renderStep()
    fireEvent.click(await screen.findByRole('button', { name: 'New analysis' }))
    expect(onNewFlow).toHaveBeenCalled()
  })

  it('can start blank', async () => {
    vi.mocked(setupApi.dashboard).mockResolvedValue(step())
    vi.mocked(reportsApi.create).mockResolvedValue({ id: 902 } as never)
    vi.mocked(setupApi.designsUsed).mockResolvedValue({} as never)
    renderStep()
    fireEvent.click(await screen.findByRole('button', { name: 'Create a blank dashboard' }))
    await waitFor(() => expect(reportsApi.create).toHaveBeenCalledWith({ name: 'All parcels dashboard', dataset_id: 226 }))
    await waitFor(() => expect(setupApi.designsUsed).toHaveBeenCalledWith(38, 902, [], 7))
  })

  it('changes a suggestion by asking', async () => {
    vi.mocked(setupApi.dashboard).mockResolvedValue(step({ items: [design('d1', 'Overview')] }))
    vi.mocked(setupApi.refineDashboard).mockResolvedValue({ designs: step().designs })
    renderStep()
    fireEvent.click(await screen.findByRole('button', { name: 'Change it' }))
    fireEvent.change(screen.getByRole('textbox', { name: /Ask for a change/ }), { target: { value: 'add a chart by month' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    await waitFor(() => expect(setupApi.refineDashboard).toHaveBeenCalledWith(38, 'd1', 'add a chart by month', 'en', 7))
  })

  it('says what could not be answered from this data', async () => {
    const d = design('d1', 'Overview')
    d.proposal.unanswered = ['This data could not answer: Which driver is slowest?']
    vi.mocked(setupApi.dashboard).mockResolvedValue(step({ items: [d] }))
    renderStep()
    expect(await screen.findByText('This data could not answer: Which driver is slowest?')).toBeInTheDocument()
  })

  it('says it is building while it works', async () => {
    vi.mocked(setupApi.dashboard).mockResolvedValue(step({ pending: true, items: [] }))
    renderStep()
    expect(await screen.findByText(/AI is building pages for what you asked/)).toBeInTheDocument()
  })
})
