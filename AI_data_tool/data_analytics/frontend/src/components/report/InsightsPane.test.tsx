import { describe, it, expect, vi, beforeEach } from 'vitest'
import toast from 'react-hot-toast'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import InsightsPane from './InsightsPane'
import { insightsApi, suggestApi } from '../../services/api'

vi.mock('../../services/api', () => ({
  insightsApi: { run: vi.fn() },
  suggestApi: { autoCompose: vi.fn(), forReport: vi.fn() },
}))
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))

const types = { region: 'categorical', revenue: 'numeric', target: 'numeric' }

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(insightsApi.run).mockResolvedValue({
    narrative: 'Across 2,000 rows: things.',
    findings: [
      { kind: 'standout', score: 0.8, title: 'A carries 60% of revenue', detail: 'd1', columns: ['region', 'revenue'] },
      { kind: 'correlation', score: 0.6, title: 'revenue moves with target', detail: 'd2', columns: ['revenue', 'target'] },
      { kind: 'data_quality', score: 0.5, title: 'notes is 40% missing', detail: 'd3', columns: ['notes'] },
    ],
  })
})

describe('InsightsPane', () => {
  it('scans on demand and infers the right chart per finding', async () => {
    const onAdd = vi.fn()
    render(<InsightsPane datasetId={5} columnTypes={types} onAdd={onAdd} />)
    fireEvent.click(screen.getByRole('button', { name: /Generate/ }))
    await waitFor(() => expect(screen.getByTestId('rb-insight-standout')).toBeInTheDocument())

    // category+measure -> bar
    fireEvent.click(screen.getAllByRole('button', { name: '+ Chart it' })[0])
    expect(onAdd.mock.calls[0][0]).toMatchObject({ widget_type: 'bar',
      config: { dimension: 'region', measure: 'revenue' } })
    // measure pair -> scatter
    fireEvent.click(screen.getAllByRole('button', { name: '+ Chart it' })[1])
    // shape_series semantics (dimension = x numeric, measure = y): the old
    // x_column/y_column keys existed in no shaper and rendered empty.
    expect(onAdd.mock.calls[1][0]).toMatchObject({ widget_type: 'scatter',
      config: { dimension: 'revenue', measure: 'target', aggregation: 'avg' } })
    // unknown columns -> no chart button, text only
    const dq = screen.getByTestId('rb-insight-data_quality')
    expect(dq).not.toHaveTextContent('+ Chart it')
  })

  it('adds a finding as a text widget carrying its sentence', async () => {
    const onAdd = vi.fn()
    render(<InsightsPane datasetId={5} columnTypes={types} onAdd={onAdd} />)
    fireEvent.click(screen.getByRole('button', { name: /Generate/ }))
    await waitFor(() => expect(screen.getAllByRole('button', { name: '+ Add as text' }).length).toBe(3))
    fireEvent.click(screen.getAllByRole('button', { name: '+ Add as text' })[0])
    expect(onAdd.mock.calls[0][0]).toMatchObject({ widget_type: 'text',
      config: { content: 'A carries 60% of revenue. d1' } })
  })

  it('asks for a dataset when the report has none', () => {
    render(<InsightsPane datasetId={null} columnTypes={{}} onAdd={() => {}} />)
    expect(screen.getByText(/Attach a dataset/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Generate/ })).toBeDisabled()
  })
})

describe('building a whole report from the findings', () => {
  // Adding findings one at a time was the only path: the engine had already
  // ranked them and already knew which chart showed each, but acting on that
  // meant clicking "+ Chart it" per finding and then sizing every widget by
  // hand. This composes the page in one call.
  const showWithReport = () =>
    render(<InsightsPane datasetId={5} columnTypes={types} onAdd={vi.fn()}
                         reportId={7} onComposed={vi.fn()} />)

  it('offers the action only once there are findings to build from', async () => {
    showWithReport()
    expect(screen.queryByRole('button', { name: /Build a report/i })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /Generate/ }))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /Build a report/i })).toBeInTheDocument())
  })

  it('composes and reports the page back to the builder', async () => {
    vi.mocked(suggestApi.autoCompose).mockResolvedValue(
      { page_id: 42, name: 'Auto-generated insights', widget_count: 9 })
    const onComposed = vi.fn()
    render(<InsightsPane datasetId={5} columnTypes={types} onAdd={vi.fn()}
                         reportId={7} onComposed={onComposed} />)
    fireEvent.click(screen.getByRole('button', { name: /Generate/ }))
    fireEvent.click(await screen.findByRole('button', { name: /Build a report/i }))

    await waitFor(() => expect(suggestApi.autoCompose).toHaveBeenCalledWith(7))
    // The builder must learn the new page id, or the user composes a page they
    // cannot see without reloading.
    await waitFor(() => expect(onComposed).toHaveBeenCalledWith(42))
  })

  it('surfaces the backend refusal rather than failing silently', async () => {
    // "No findings strong enough to build a report from" is a real answer for
    // a tiny or uniform dataset, and the user needs to read it.
    vi.mocked(suggestApi.autoCompose).mockRejectedValue(
      { response: { data: { detail: 'No findings strong enough' } } })
    const onComposed = vi.fn()
    render(<InsightsPane datasetId={5} columnTypes={types} onAdd={vi.fn()}
                         reportId={7} onComposed={onComposed} />)
    fireEvent.click(screen.getByRole('button', { name: /Generate/ }))
    fireEvent.click(await screen.findByRole('button', { name: /Build a report/i }))

    await waitFor(() => expect(toast.error).toHaveBeenCalled())
    expect(onComposed).not.toHaveBeenCalled()
  })

  it('hides the action when there is no report to write into', async () => {
    // The dataset page mounts this pane too, and there is no page to compose.
    render(<InsightsPane datasetId={5} columnTypes={types} onAdd={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /Generate/ }))
    await waitFor(() => expect(screen.getByTestId('rb-insight-standout')).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /Build a report/i })).toBeNull()
  })
})

describe('novelty badges', () => {
  // The scan now persists server-side and each run is annotated against the
  // previous one. The badge is the entire user-facing payoff of that work: a
  // finding seen daily and one that appeared this morning must not render
  // identically.
  const withNovelty = (novelty?: 'new' | 'changed' | 'unchanged') => {
    vi.mocked(insightsApi.run).mockResolvedValue({
      narrative: 'n',
      findings: [{ kind: 'standout', score: 0.8, title: 'A carries 60%',
                   detail: 'd', columns: ['region', 'revenue'],
                   ...(novelty ? { novelty } : {}) }],
    })
    render(<InsightsPane datasetId={5} columnTypes={types} onAdd={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /Generate/ }))
    return screen.findByTestId('rb-insight-standout')
  }

  it('marks a finding absent from the previous scan as NEW', async () => {
    await withNovelty('new')
    expect(screen.getByText('NEW')).toBeInTheDocument()
  })

  it('marks a materially moved finding as CHANGED', async () => {
    await withNovelty('changed')
    expect(screen.getByText('CHANGED')).toBeInTheDocument()
  })

  it('gives an unchanged finding no badge at all', async () => {
    // Labelling `unchanged` too would put a chip on every card, and the badge
    // would stop meaning anything.
    await withNovelty('unchanged')
    expect(screen.queryByText(/NEW|CHANGED|UNCHANGED/)).toBeNull()
  })

  it('renders no badge when the server sent no novelty at all', async () => {
    // First scan, or a restricted caller: the field is absent by design.
    await withNovelty(undefined)
    expect(screen.queryByText(/NEW|CHANGED/)).toBeNull()
  })
})


describe('evidence chips (Phase 7.2)', () => {
  it('a tested finding shows its test, effect, population and adjusted p', async () => {
    vi.mocked(insightsApi.run).mockResolvedValue({
      narrative: 'n',
      findings: [{ kind: 'standout', score: 0.8, title: 'A carries 60%', detail: 'd', columns: ['region', 'revenue'],
                   p_value: 0.0004, p_adjusted: 0.002, significant: true,
                   evidence: { test: 'Chi-square vs an even split', n: 2000, effect: '60% vs 25% expected' } },
                 { kind: 'trend', score: 0.5, title: 'Up', detail: 'd', columns: ['month'] }],
    })
    render(<InsightsPane datasetId={5} columnTypes={types} onAdd={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /Generate/ }))
    const chip = await screen.findByTestId('insight-evidence')
    expect(chip.textContent).toBe('Chi-square vs an even split · 60% vs 25% expected · n = 2,000 · p < 0.001 (adjusted 0.0020)')
    expect(screen.getAllByTestId('insight-evidence')).toHaveLength(1)
  })
})
