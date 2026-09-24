import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { StrictMode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import SuggestDashboardsDialog from './SuggestDashboardsDialog'
import { datasetsApi, reportsApi } from '../../services/api'

/**
 * "Suggest dashboards", from the dataset list.
 *
 * The point of the feature is that the person says who they are in their own
 * words and gets a dashboard built for that. So the tests that matter are: their
 * words reach the request, what comes back is legible enough to choose between,
 * and accepting one actually builds it.
 *
 * The last group is the one that is easy to get wrong quietly. A proposal that
 * builds a page whose tiles are the wrong size is a page the person has to
 * repair before using — which is what happened to ten hand-built dashboards in
 * this repo, where a three-value card in an h=2 tile showed its middle value and
 * a sliver of the one above.
 */
const PROFILE = {
  row_count: 120000,
  columns: [
    { name: 'department', role: 'categorical', distinct: 12, missing_pct: 0,
      is_identifier: false, is_personal: false, top_values: [], min: null, max: null },
    { name: 'wait_minutes', role: 'numeric', distinct: 300, missing_pct: 0,
      is_identifier: false, is_personal: false, top_values: [], min: 1, max: 400 },
  ],
  other_columns: [],
  structure: { coordinate_pairs: [], parent_child: [], hierarchies: [],
               date_range: { column: 'arrived_at', from: '2024-09-01', to: '2026-09-01',
                             days: 730, granularity: 'month' } },
}

const PROPOSAL = {
  title: 'Emergency flow',
  rationale: 'for the ED manager: where the queue builds',
  widgets: [
    { widget_type: 'kpi', title: 'Median wait', why: 'the headline number',
      config: { dimension: 'department', measure: 'wait_minutes', aggregation: 'median' },
      row_count: 1 },
    { widget_type: 'bar', title: 'Wait by department', why: 'where it builds',
      config: { dimension: 'department', measure: 'wait_minutes', aggregation: 'avg' },
      row_count: 12 },
  ],
}

const navigate = vi.fn()
vi.mock('react-router-dom', async () => ({
  ...(await vi.importActual<typeof import('react-router-dom')>('react-router-dom')),
  useNavigate: () => navigate,
}))

function open(overrides: Record<string, unknown> = {}) {
  render(<MemoryRouter>
    <SuggestDashboardsDialog datasetId={7} datasetName="Encounters"
      onClose={overrides.onClose as () => void ?? vi.fn()} />
  </MemoryRouter>)
}

beforeEach(() => {
  navigate.mockClear()
  vi.spyOn(datasetsApi, 'suggestDashboards').mockResolvedValue(
    { proposals: [PROPOSAL], reason: '', profile: PROFILE } as never)
})
afterEach(() => vi.restoreAllMocks())

describe('asking', () => {
  it('offers a box for the person to say who they are', () => {
    open()
    expect(screen.getByLabelText(/what do you do/i)).toBeInTheDocument()
  })

  it('sends their words with the request', async () => {
    open()
    fireEvent.change(screen.getByLabelText(/what do you do/i),
      { target: { value: 'I am an instructor' } })
    fireEvent.click(screen.getByRole('button', { name: /suggest/i }))
    await waitFor(() => expect(datasetsApi.suggestDashboards).toHaveBeenCalledWith(
      7, expect.objectContaining({ goal: 'I am an instructor' })))
  })

  it('works without any words at all', async () => {
    open()
    fireEvent.click(screen.getByRole('button', { name: /suggest/i }))
    await waitFor(() => expect(datasetsApi.suggestDashboards).toHaveBeenCalled())
  })

  it('says it is working while it waits', async () => {
    let release: (v: unknown) => void = () => {}
    vi.spyOn(datasetsApi, 'suggestDashboards').mockReturnValue(
      new Promise(r => { release = r }) as never)
    open()
    fireEvent.click(screen.getByRole('button', { name: /suggest/i }))
    await waitFor(() => expect(screen.getByRole('status')).toBeInTheDocument())
    release({ proposals: [], reason: 'none', profile: PROFILE })
  })
})

describe('under StrictMode, which is how it runs in development', () => {
  /**
   * The panel spun forever in a real browser while the same request finished in
   * 28 seconds over the API.
   *
   * StrictMode mounts, unmounts and re-mounts every component. The unmount ran
   * the cleanup that sets the "still mounted" flag to false; the effect never
   * set it back to true on the second mount. So the answer arrived to a
   * component that believed it was gone, and neither the proposals nor the end
   * of the loading state was ever applied.
   *
   * Every test above passes without StrictMode, which is exactly why this one
   * exists.
   */
  it('still shows the proposals after a double mount', async () => {
    render(<StrictMode><MemoryRouter>
      <SuggestDashboardsDialog datasetId={7} datasetName="Encounters" onClose={vi.fn()} />
    </MemoryRouter></StrictMode>)
    fireEvent.click(screen.getByRole('button', { name: /suggest/i }))
    expect(await screen.findByText('Emergency flow')).toBeInTheDocument()
  })

  it('stops saying it is working', async () => {
    render(<StrictMode><MemoryRouter>
      <SuggestDashboardsDialog datasetId={7} datasetName="Encounters" onClose={vi.fn()} />
    </MemoryRouter></StrictMode>)
    fireEvent.click(screen.getByRole('button', { name: /suggest/i }))
    await screen.findByText('Emergency flow')
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})

describe('what comes back', () => {
  async function ask() {
    open()
    fireEvent.click(screen.getByRole('button', { name: /suggest/i }))
    await screen.findByText('Emergency flow')
  }

  it('shows each proposal and why it exists', async () => {
    await ask()
    expect(screen.getByText(/where the queue builds/)).toBeInTheDocument()
  })

  it('lists the widgets it would build', async () => {
    await ask()
    expect(screen.getByText('Wait by department')).toBeInTheDocument()
    expect(screen.getByText('Median wait')).toBeInTheDocument()
  })

  it('shows that each widget really returned data', async () => {
    /** The row counts come from executing every widget. Showing them is what
     *  separates this from a list of plausible-sounding chart titles. */
    await ask()
    // Built with the same formatter the component uses: this machine renders
    // digits in the OS locale (Arabic-Indic here), and pinning Latin digits
    // would be testing the locale rather than the feature.
    expect(screen.getByText(`${(12).toLocaleString()} rows`)).toBeInTheDocument()
  })

  it('shows what it understood about the data', async () => {
    await ask()
    expect(screen.getByText(`${(120000).toLocaleString()} rows`)).toBeInTheDocument()
    expect(screen.getAllByText(/department/).length).toBeGreaterThan(0)
  })

  it('explains itself when it has nothing to offer', async () => {
    vi.spyOn(datasetsApi, 'suggestDashboards').mockResolvedValue(
      { proposals: [], reason: 'the model endpoint is not configured',
        profile: PROFILE } as never)
    open()
    fireEvent.click(screen.getByRole('button', { name: /suggest/i }))
    expect(await screen.findByText(/model endpoint is not configured/)).toBeInTheDocument()
  })
})

describe('the relations between the widgets', () => {
  /**
   * Two charts cut by the same column are not merely both on the page: clicking
   * a department in one is a question the other can answer. The proposal says
   * which pairs those are; accepting it has to wire them up.
   *
   * The seam: the proposal numbers its widgets 0, 1, 2 — but the actions are
   * stored against real widget ids, which only exist after each one is created.
   * Writing a proposal index where an id belongs produces an action pointing at
   * whatever widget happens to own that id, which is a different chart on a
   * different page.
   */
  const RELATED = {
    ...PROPOSAL,
    widgets: [
      PROPOSAL.widgets[0],
      PROPOSAL.widgets[1],
      { widget_type: 'box_plot', title: 'Wait spread by department',
        why: 'where the variance is',
        config: { dimension: 'department', measure: 'wait_minutes' },
        row_count: 12 },
    ],
    relations: [
      { from: 1, to: 2, via: 'department', mode: 'filter',
        note: 'Wait by department filters Wait spread by department.' },
      { from: 2, to: 1, via: 'department', mode: 'filter',
        note: 'Wait spread by department filters Wait by department.' },
    ],
  }

  beforeEach(() => {
    vi.spyOn(datasetsApi, 'suggestDashboards').mockResolvedValue(
      { proposals: [RELATED], reason: '', profile: PROFILE,
        source: 'insights' } as never)
    vi.spyOn(reportsApi, 'create').mockResolvedValue(
      { id: 42, pages: [{ id: 99 }] } as never)
    // Real ids, deliberately far from the proposal indices 0/1/2.
    let next = 500
    vi.spyOn(reportsApi, 'addWidget').mockImplementation(
      async () => ({ id: next++ }) as never)
    vi.spyOn(reportsApi, 'updateWidget').mockResolvedValue({} as never)
  })

  async function build() {
    open()
    fireEvent.click(screen.getByRole('button', { name: /suggest/i }))
    await screen.findByText('Emergency flow')
    fireEvent.click(screen.getByRole('button', { name: /create this dashboard/i }))
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/reports/42'))
  }

  it('shows the reader what will be linked', async () => {
    open()
    fireEvent.click(screen.getByRole('button', { name: /suggest/i }))
    await screen.findByText('Emergency flow')
    expect(screen.getByText(/filters Wait spread by department/)).toBeInTheDocument()
  })

  it('wires the actions after every widget exists', async () => {
    await build()
    expect(reportsApi.updateWidget).toHaveBeenCalled()
  })

  it('points the action at the REAL widget id, not the proposal index', async () => {
    await build()
    const calls = (reportsApi.updateWidget as never as ReturnType<typeof vi.fn>).mock.calls
    const forSecond = calls.find(c => c[2] === 501)
    expect(forSecond).toBeTruthy()
    expect(forSecond![3].config.interaction.actions)
      .toEqual([{ targetId: 502, mode: 'filter' }])
  })

  it('keeps the widget config it was created with', async () => {
    await build()
    const calls = (reportsApi.updateWidget as never as ReturnType<typeof vi.fn>).mock.calls
    const forSecond = calls.find(c => c[2] === 501)!
    expect(forSecond[3].config).toMatchObject({ dimension: 'department' })
  })

  it('does nothing extra when a proposal has no relations', async () => {
    vi.spyOn(datasetsApi, 'suggestDashboards').mockResolvedValue(
      { proposals: [PROPOSAL], reason: '', profile: PROFILE } as never)
    await build()
    expect(reportsApi.updateWidget).not.toHaveBeenCalled()
  })
})

describe('saying which engine answered', () => {
  /** A person looking at a generated page should be able to tell whether a
   *  model chose these charts or the statistics did. The two are not equally
   *  trustworthy in the same ways, and only one of them is reproducible. */
  it('says so when no AI was used', async () => {
    vi.spyOn(datasetsApi, 'suggestDashboards').mockResolvedValue(
      { proposals: [{ ...PROPOSAL, source: 'insights' }], reason: '',
        profile: PROFILE, source: 'insights' } as never)
    open()
    fireEvent.click(screen.getByRole('button', { name: /suggest/i }))
    expect(await screen.findByText(/no AI/i)).toBeInTheDocument()
  })

  it('says so when the model was used', async () => {
    vi.spyOn(datasetsApi, 'suggestDashboards').mockResolvedValue(
      { proposals: [{ ...PROPOSAL, source: 'model' }], reason: '',
        profile: PROFILE, source: 'model' } as never)
    open()
    fireEvent.click(screen.getByRole('button', { name: /suggest/i }))
    await screen.findByText('Emergency flow')
    expect(screen.getByText(/chosen for what you described/i)).toBeInTheDocument()
  })

  it('tells the person up front what an empty box will do', () => {
    open()
    expect(screen.getByText(/leave it blank/i)).toBeInTheDocument()
  })
})

describe('accepting one', () => {
  beforeEach(() => {
    vi.spyOn(reportsApi, 'create').mockResolvedValue(
      { id: 42, pages: [{ id: 99 }] } as never)
    vi.spyOn(reportsApi, 'addWidget').mockResolvedValue({} as never)
  })

  async function build() {
    open()
    fireEvent.click(screen.getByRole('button', { name: /suggest/i }))
    await screen.findByText('Emergency flow')
    fireEvent.click(screen.getByRole('button', { name: /create this dashboard/i }))
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/reports/42'))
  }

  it('creates the report and opens it', async () => {
    await build()
    expect(reportsApi.create).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'Emergency flow', dataset_id: 7 }))
  })

  it('adds every widget with the config that was probed', async () => {
    await build()
    expect(reportsApi.addWidget).toHaveBeenCalledTimes(2)
    const [, , widget] = (reportsApi.addWidget as never as ReturnType<typeof vi.fn>)
      .mock.calls[1]
    expect(widget.widget_type).toBe('bar')
    expect(widget.config).toMatchObject({ dimension: 'department', aggregation: 'avg' })
  })

  it('gives a chart more room than a single number', async () => {
    /** The tile-height bug, in the one place that can prevent it recurring. */
    await build()
    const calls = (reportsApi.addWidget as never as ReturnType<typeof vi.fn>).mock.calls
    const kpi = calls[0][2].layout
    const bar = calls[1][2].layout
    expect(bar.h).toBeGreaterThan(kpi.h)
    expect(bar.h).toBeGreaterThanOrEqual(4)
  })

  it('never lays a tile out at a height that clips a chart', async () => {
    await build()
    const calls = (reportsApi.addWidget as never as ReturnType<typeof vi.fn>).mock.calls
    for (const [, , w] of calls) {
      if (w.widget_type !== 'kpi') expect(w.layout.h).toBeGreaterThanOrEqual(3)
    }
  })
})


describe('when the request fails', () => {

  it('shows the reason the server gave, not the transport message', async () => {
    /* "Request failed with status code 400" is the least useful sentence a UI
       can print: the server said exactly why, and this used to throw it away
       and send the person to the logs for a line the response already had. */
    vi.spyOn(datasetsApi, 'suggestDashboards').mockRejectedValue({
      response: { data: { detail: 'Dashboard suggestions run over import-mode datasets' } },
      message: 'Request failed with status code 400',
    })
    render(<SuggestDashboardsDialog datasetId={4} datasetName="Clinic" onClose={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: /Suggest/i }))

    expect(await screen.findByText(/run over import-mode datasets/)).toBeInTheDocument()
    expect(screen.queryByText(/status code 400/)).toBeNull()
  })

  it('falls back to the transport message when there is no detail', async () => {
    vi.spyOn(datasetsApi, 'suggestDashboards').mockRejectedValue(new Error('Network Error'))
    render(<SuggestDashboardsDialog datasetId={4} datasetName="Clinic" onClose={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: /Suggest/i }))
    expect(await screen.findByText(/Network Error/)).toBeInTheDocument()
  })
})

describe('when nothing could be designed', () => {
  /* A reason is a dead end -- the person is left rereading their own sentence
     wondering which part of it was wrong. The agent's D4.3 node solved the same
     problem for questions; this is that, for dashboards. */

  it('shows the question the designer asked back', async () => {
    vi.spyOn(datasetsApi, 'suggestDashboards').mockResolvedValue({
      proposals: [], reason: 'the goal names no column in this data',
      question: 'Do you mean waiting time per department, or per clinician?',
      profile: { row_count: 30, columns: [], structure: {} } as never,
      source: 'model',
    } as never)
    render(<SuggestDashboardsDialog datasetId={4} datasetName="Clinic" onClose={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: /Suggest/i }))

    expect(await screen.findByText(/Do you mean waiting time per department/))
      .toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Answer this' })).toBeInTheDocument()
  })

  it('shows the plain refusal when there is no question to ask', async () => {
    /* No model, or a model that declined. An invented question would be worse
       than the refusal it replaced. */
    vi.spyOn(datasetsApi, 'suggestDashboards').mockResolvedValue({
      proposals: [], reason: 'the model endpoint is not configured',
      question: null,
      profile: { row_count: 30, columns: [], structure: {} } as never,
      source: 'model',
    } as never)
    render(<SuggestDashboardsDialog datasetId={4} datasetName="Clinic" onClose={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: /Suggest/i }))

    expect(await screen.findByText(/model endpoint is not configured/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Answer this' })).toBeNull()
  })
})
