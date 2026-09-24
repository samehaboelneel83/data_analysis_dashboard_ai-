/* The chat's answer to "suggest a dashboard for me".
 *
 * The proposals arrive on the agent run's `presentation` field — the channel the
 * chat already uses for its other structured replies — so they render inside the
 * conversation rather than in a dialog somewhere else. Three of them, because a
 * person who asks for a dashboard has not decided what they want yet: one answer
 * is a decision made for them.
 *
 * Creating is deliberately a separate click on a named card. The agent proposes;
 * the person chooses.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import DashboardProposals from './DashboardProposals'
import { dataSourcesApi, reportsApi } from '../../services/api'

vi.mock('../../services/api', () => ({
  dataSourcesApi: { import: vi.fn() },
  reportsApi: { create: vi.fn(), addWidget: vi.fn() },
}))

const navigate = vi.fn()
// Spread the real module, don't replace it. A bare `{ useNavigate }` mock leaves
// every other export undefined for the rest of the run, and vitest shares the
// module registry across files in a worker: this file passed on its own and made
// AdminAudit fail 100 files later. The repo's own pattern (Upload.test.tsx,
// WorkspaceTree.test.tsx) is `importActual` + spread, and this is why.
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('react-router-dom')
  return { ...actual, useNavigate: () => navigate }
})

const PRESENTATION = {
  kind: 'dashboard_proposals' as const,
  source_id: 18,
  for_role: 'Instructor',
  proposals: [
    {
      title: 'Morning briefing',
      sql: 'SELECT c.fullname AS course, g.finalgrade AS grade FROM mdl_course c',
      widgets: [
        { widget_type: 'kpi', title: 'Average grade', dimension: '', measure: 'grade', aggregation: 'avg' },
        { widget_type: 'bar', title: 'Grade by course', dimension: 'course', measure: 'grade', aggregation: 'avg' },
      ],
    },
    {
      title: 'Who is falling behind',
      sql: 'SELECT u.name AS student FROM mdl_user u',
      widgets: [{ widget_type: 'table', title: 'At risk', dimension: 'student', measure: 'student', aggregation: 'count' }],
    },
    {
      title: 'The term so far',
      sql: 'SELECT c.term AS term FROM mdl_course c',
      widgets: [{ widget_type: 'line', title: 'Trend', dimension: 'term', measure: 'term', aggregation: 'count' }],
    },
  ],
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(dataSourcesApi.import).mockResolvedValue({ id: 99, name: 'x', row_count: 10, col_count: 2, mode: 'import' })
  vi.mocked(reportsApi.create).mockResolvedValue({ id: 55, name: 'Morning briefing', pages: [{ id: 7, widgets: [] }] } as never)
  vi.mocked(reportsApi.addWidget).mockResolvedValue({ id: 1 } as never)
})

describe('DashboardProposals', () => {
  it('shows every proposal it was given', () => {
    render(<DashboardProposals presentation={PRESENTATION} />)
    expect(screen.getByText('Morning briefing')).toBeInTheDocument()
    expect(screen.getByText('Who is falling behind')).toBeInTheDocument()
    expect(screen.getByText('The term so far')).toBeInTheDocument()
  })

  it('says what each dashboard would contain, so the choice is informed', () => {
    render(<DashboardProposals presentation={PRESENTATION} />)
    expect(screen.getByText(/Average grade/)).toBeInTheDocument()
    expect(screen.getByText(/Grade by course/)).toBeInTheDocument()
  })

  it('keeps the SQL available but out of the way', async () => {
    render(<DashboardProposals presentation={PRESENTATION} />)
    const toggles = screen.getAllByText(/show sql/i)
    expect(toggles).toHaveLength(3)
    fireEvent.click(toggles[0])
    expect(screen.getByText(/SELECT c.fullname AS course/)).toBeInTheDocument()
  })

  it('builds the chosen dashboard: dataset, report, widgets, then opens it', async () => {
    render(<DashboardProposals presentation={PRESENTATION} />)
    fireEvent.click(screen.getAllByRole('button', { name: /create dashboard/i })[0])

    await waitFor(() => expect(dataSourcesApi.import).toHaveBeenCalled())
    expect(dataSourcesApi.import).toHaveBeenCalledWith(
      18, 'Morning briefing', undefined, PRESENTATION.proposals[0].sql, 'import')
    await waitFor(() => expect(reportsApi.create).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'Morning briefing', dataset_id: 99 })))
    await waitFor(() => expect(reportsApi.addWidget).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/reports/55'))
  })

  it('creates only the dashboard that was clicked', async () => {
    render(<DashboardProposals presentation={PRESENTATION} />)
    fireEvent.click(screen.getAllByRole('button', { name: /create dashboard/i })[1])
    await waitFor(() => expect(dataSourcesApi.import).toHaveBeenCalledTimes(1))
    expect(dataSourcesApi.import).toHaveBeenCalledWith(
      18, 'Who is falling behind', undefined, PRESENTATION.proposals[1].sql, 'import')
  })

  it('reports a failure instead of leaving a dead button', async () => {
    vi.mocked(dataSourcesApi.import).mockRejectedValue(new Error('no such column'))
    render(<DashboardProposals presentation={PRESENTATION} />)
    fireEvent.click(screen.getAllByRole('button', { name: /create dashboard/i })[0])
    expect(await screen.findByText(/could not build/i)).toBeInTheDocument()
    expect(navigate).not.toHaveBeenCalled()
  })

  it('renders nothing for a presentation of another kind', () => {
    const { container } = render(
      <DashboardProposals presentation={{ format: 'table', limit: null } as never} />)
    expect(container).toBeEmptyDOMElement()
  })
})

// ---------------------------------------------------------------------------
// Round 5. The attribute-review pass explains itself: "Limiting to the top 15
// courses and sorting by enrolment ensures the bar chart remains readable". The
// card showed that sentence, the person read it, pressed Create — and it was
// thrown away. The built dashboard carried a `limit: 15` nobody could account
// for, on a chart nobody had chosen it for.
//
// The reason travels with the widget now, so the next person to open the
// dashboard can see why it looks the way it does, and disagree with it.
// ---------------------------------------------------------------------------

const REVIEWED = {
  ...PRESENTATION,
  proposals: [{
    title: 'Course health',
    sql: 'SELECT c.fullname AS course, g.finalgrade AS grade FROM mdl_course c',
    widgets: [
      { widget_type: 'bar', title: 'Grade by course', dimension: 'course',
        measure: 'grade', aggregation: 'avg', limit: 15, sort: 'desc',
        sort_by: 'value',
        note: 'Top 15 of 400 courses, largest first, so the chart stays readable.' },
      { widget_type: 'kpi', title: 'Average grade', dimension: '',
        measure: 'grade', aggregation: 'avg' },
    ],
  }],
}

describe('the reason the AI gave', () => {
  it('is carried onto the widget that was built', async () => {
    render(<DashboardProposals presentation={REVIEWED as never} />)
    fireEvent.click(screen.getAllByRole('button', { name: /create dashboard/i })[0])

    await waitFor(() => expect(reportsApi.addWidget).toHaveBeenCalledTimes(2))
    const [, , first] = vi.mocked(reportsApi.addWidget).mock.calls[0]
    expect((first as { config: Record<string, unknown> }).config.note)
      .toMatch(/Top 15 of 400 courses/)
  })

  it('carries the settings it explains, so the two cannot disagree', async () => {
    render(<DashboardProposals presentation={REVIEWED as never} />)
    fireEvent.click(screen.getAllByRole('button', { name: /create dashboard/i })[0])

    await waitFor(() => expect(reportsApi.addWidget).toHaveBeenCalledTimes(2))
    const [, , first] = vi.mocked(reportsApi.addWidget).mock.calls[0]
    const config = (first as { config: Record<string, unknown> }).config
    expect(config.limit).toBe(15)
    expect(config.sort).toBe('desc')
  })

  it('adds no note to a widget the reviewer did not change', async () => {
    render(<DashboardProposals presentation={REVIEWED as never} />)
    fireEvent.click(screen.getAllByRole('button', { name: /create dashboard/i })[0])

    await waitFor(() => expect(reportsApi.addWidget).toHaveBeenCalledTimes(2))
    const [, , second] = vi.mocked(reportsApi.addWidget).mock.calls[1]
    expect((second as { config: Record<string, unknown> }).config)
      .not.toHaveProperty('note')
  })
})
