import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import SuggestFromSourceDialog from './SuggestFromSourceDialog'
import { dataSourcesApi, reportsApi } from '../../services/api'

/**
 * The step before a dataset exists: somebody has connected a database, has no
 * dataset, and does not know which of its tables to join.
 *
 * `POST /data-sources/{id}/suggest-dashboard` has answered that since it
 * shipped — complete, probe-validated, and with zero callers anywhere in the
 * product. These tests pin the caller, and the two things that make it safe to
 * press: the backend creates nothing, and the person is told when they already
 * have a dataset covering the same ground.
 */

const navigate = vi.fn()
vi.mock('react-router-dom', async () => ({
  ...(await vi.importActual<typeof import('react-router-dom')>('react-router-dom')),
  useNavigate: () => navigate,
}))

const SUGGESTION = {
  title: 'Emergency department flow',
  sql: 'SELECT department, AVG(wait_minutes) AS wait FROM visits GROUP BY department',
  widgets: [
    { widget_type: 'bar', title: 'Average wait by department', dimension: 'department',
      measure: 'wait_minutes', aggregation: 'avg', note: 'limited to the ten busiest' },
  ],
}

function open(props: Partial<React.ComponentProps<typeof SuggestFromSourceDialog>> = {}) {
  return render(
    <MemoryRouter>
      <SuggestFromSourceDialog sourceId={3} sourceName="hospital db" synced
        onClose={() => {}} {...props} />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.restoreAllMocks()
  navigate.mockReset()
  vi.spyOn(dataSourcesApi, 'similarDatasets').mockResolvedValue({ matches: [] })
})

// The spies above live on a SHARED module object, and vitest reuses the module
// registry across files in a worker. `restoreAllMocks` in beforeEach protects
// only this file's own tests -- without this afterEach the last test's spies
// stay installed for every file that runs after it. That is exactly how this
// suite has broken an unrelated page before.
afterEach(() => { vi.restoreAllMocks() })

describe('SuggestFromSourceDialog', () => {
  it('asks the catalogue for a dashboard for a named person', async () => {
    const ask = vi.spyOn(dataSourcesApi, 'suggestDashboard')
      .mockResolvedValue({ ok: true, reason: '', suggestion: SUGGESTION })
    open()
    fireEvent.change(screen.getByPlaceholderText(/ward sister/),
                     { target: { value: 'a ward sister' } })
    fireEvent.change(screen.getByPlaceholderText(/queue builds up/),
                     { target: { value: 'night shifts' } })
    fireEvent.click(screen.getByRole('button', { name: 'Suggest' }))

    await waitFor(() => expect(ask).toHaveBeenCalledWith(
      3, { for_role: 'a ward sister', goal: 'night shifts' }))
    expect(await screen.findByText('Emergency department flow')).toBeInTheDocument()
    expect(screen.getByText(/limited to the ten busiest/)).toBeInTheDocument()
  })

  it('shows the reason when nothing could be designed, rather than an error', async () => {
    /* 200 with a reason, not a failure: "the model is off" and "nothing safe
       could be proposed" are both normal answers to a request for a suggestion. */
    vi.spyOn(dataSourcesApi, 'suggestDashboard')
      .mockResolvedValue({ ok: false, reason: 'the model endpoint is not configured',
                           suggestion: null })
    open()
    fireEvent.change(screen.getByPlaceholderText(/ward sister/), { target: { value: 'me' } })
    fireEvent.click(screen.getByRole('button', { name: 'Suggest' }))
    expect(await screen.findByText(/model endpoint is not configured/)).toBeInTheDocument()
  })

  it('will not ask a connection that has never been read', async () => {
    const ask = vi.spyOn(dataSourcesApi, 'suggestDashboard')
    open({ synced: false })
    expect(screen.getByText(/has not been read yet/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Suggest' })).toBeDisabled()
    expect(ask).not.toHaveBeenCalled()
  })

  it('warns that a dataset already covers this, without preventing the build', async () => {
    vi.spyOn(dataSourcesApi, 'suggestDashboard')
      .mockResolvedValue({ ok: true, reason: '', suggestion: SUGGESTION })
    vi.spyOn(dataSourcesApi, 'similarDatasets').mockResolvedValue({
      matches: [{ dataset_id: 12, name: 'ED waits', mode: 'import', row_count: 4000,
                  overlap: 2, coverage: 1, matched_columns: ['department', 'wait_minutes'],
                  by_name: false }],
    })
    open()
    fireEvent.change(screen.getByPlaceholderText(/ward sister/), { target: { value: 'me' } })
    fireEvent.click(screen.getByRole('button', { name: 'Suggest' }))

    expect(await screen.findByText('You may already have this')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'ED waits' })).toBeInTheDocument()
    // Advisory, never a refusal: the person asked for something and still gets it.
    expect(screen.getByRole('button', { name: 'Create it' })).toBeEnabled()
  })

  it('builds the dataset, the report and its tiles, then opens it', async () => {
    vi.spyOn(dataSourcesApi, 'suggestDashboard')
      .mockResolvedValue({ ok: true, reason: '', suggestion: SUGGESTION })
    const imp = vi.spyOn(dataSourcesApi, 'import')
      .mockResolvedValue({ id: 7, name: 'Emergency department flow', row_count: 3,
                           col_count: 2, mode: 'import' })
    const create = vi.spyOn(reportsApi, 'create')
      .mockResolvedValue({ id: 5, pages: [{ id: 50 }] } as never)
    const addWidget = vi.spyOn(reportsApi, 'addWidget').mockResolvedValue({} as never)

    open()
    fireEvent.change(screen.getByPlaceholderText(/ward sister/), { target: { value: 'me' } })
    fireEvent.click(screen.getByRole('button', { name: 'Suggest' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Create it' }))

    // The backend proposes and creates nothing; these three calls, which the
    // person already has permission to make, are what build it.
    await waitFor(() => expect(imp).toHaveBeenCalledWith(
      3, 'Emergency department flow', undefined, SUGGESTION.sql, 'import'))
    await waitFor(() => expect(create).toHaveBeenCalled())
    await waitFor(() => expect(addWidget).toHaveBeenCalledWith(
      5, 50, expect.objectContaining({
        widget_type: 'bar',
        config: expect.objectContaining({ note: 'limited to the ten busiest' }),
      })))
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/reports/5'))
  })

  it('a failed build is named, not swallowed', async () => {
    vi.spyOn(dataSourcesApi, 'suggestDashboard')
      .mockResolvedValue({ ok: true, reason: '', suggestion: SUGGESTION })
    vi.spyOn(dataSourcesApi, 'import')
      .mockRejectedValue({ response: { data: { detail: 'the query timed out' } } })
    open()
    fireEvent.change(screen.getByPlaceholderText(/ward sister/), { target: { value: 'me' } })
    fireEvent.click(screen.getByRole('button', { name: 'Suggest' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Create it' }))
    /* The query already ran against the database when it was proposed, so a
       failure here is worth reading rather than silently retrying. */
    expect(await screen.findByText('the query timed out')).toBeInTheDocument()
  })
})
