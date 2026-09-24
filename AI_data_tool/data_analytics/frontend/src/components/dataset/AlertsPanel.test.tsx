import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders as render, screen, fireEvent, waitFor } from '../../test/renderWithProviders'
import AlertsPanel from './AlertsPanel'
import { alertsApi } from '../../services/api'
import type { DatasetColumn } from '../../services/api'

/**
 * Alerts shipped complete and unreachable.
 *
 * The evaluator has run on every scheduler tick for months: it resolves RLS as
 * the alert's creator, fires only on the RISING edge, and emails through the
 * same delivery path as a scheduled report. Three endpoints served it. Nothing
 * in the product could create one, so in practice the platform had no alerts.
 *
 * This pane is the missing part, and it is deliberately small — list, create,
 * delete. The comparison called it "the cheapest real gain in the document".
 *
 * The two things it must get right beyond CRUD: the backend's own refusal has
 * to reach the user (an expression the sandbox rejects says WHY), and the
 * rising-edge behaviour has to be visible, because an alert whose condition is
 * already true and silent looks broken.
 */

vi.mock('../../services/api', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  alertsApi: { list: vi.fn(), create: vi.fn(), remove: vi.fn() },
}))

const col = (name: string): DatasetColumn =>
  ({ id: 0, name, dtype: 'numeric', missing_pct: 0, stats: {} } as DatasetColumn)
const COLUMNS = [col('revenue'), col('region')]

const EXISTING = [{
  id: 5, name: 'Revenue fell', expression: 'SUM(revenue) < 100000',
  interval_minutes: 60, recipients: ['ops@example.com'],
  last_state: false, last_status: 'ok', last_checked_at: '2026-09-10T10:00:00Z',
}]

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(alertsApi.list).mockResolvedValue(EXISTING as never)
  vi.mocked(alertsApi.create).mockResolvedValue({ id: 6, name: 'New' } as never)
  vi.mocked(alertsApi.remove).mockResolvedValue(undefined as never)
})

const panel = () => render(<AlertsPanel datasetId={1} columns={COLUMNS} />)

const openForm = async () => {
  panel()
  fireEvent.click(await screen.findByRole('button', { name: /new alert/i }))
}

describe('what is already watching', () => {
  it('lists the alerts on this dataset', async () => {
    panel()
    expect(await screen.findByText('Revenue fell')).toBeInTheDocument()
    expect(screen.getByText(/SUM\(revenue\) < 100000/)).toBeInTheDocument()
  })

  it('says who gets the email', async () => {
    // An alert nobody can see the recipients of is an alert nobody can audit.
    panel()
    expect(await screen.findByText(/ops@example\.com/)).toBeInTheDocument()
  })

  it('says when it last ran', async () => {
    // The leaf, not `/checked/i`: an ancestor's text content includes its
    // children's, so a loose matcher finds the row, the card and the list and
    // fails on "multiple elements" — which looks like a render bug and is not.
    panel()
    await screen.findByText('Revenue fell')
    expect(screen.getByText(
      (_, el) => el?.textContent?.startsWith('Checked ') === true
                 && el.children.length === 0)).toBeInTheDocument()
  })

  it('shows an alert that has never run as never run, not as healthy', async () => {
    vi.mocked(alertsApi.list).mockResolvedValue([
      { ...EXISTING[0], last_status: null, last_checked_at: null }] as never)
    panel()
    expect(await screen.findByText(/not yet checked/i)).toBeInTheDocument()
  })

  it('surfaces an evaluation failure rather than hiding it', async () => {
    // A broken alert that looks fine is worse than no alert: nobody learns the
    // condition stopped being watched.
    vi.mocked(alertsApi.list).mockResolvedValue([
      { ...EXISTING[0], last_status: 'error: column not found' }] as never)
    panel()
    expect(await screen.findByText(/column not found/i)).toBeInTheDocument()
  })

  it('reports a failure to load instead of an empty list', async () => {
    vi.mocked(alertsApi.list).mockRejectedValue(new Error('down'))
    panel()
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load/i)
  })

  it('says plainly when nothing is watching yet', async () => {
    vi.mocked(alertsApi.list).mockResolvedValue([] as never)
    panel()
    expect(await screen.findByText(/no alerts/i)).toBeInTheDocument()
  })
})

describe('creating one', () => {
  it('posts the name, expression, interval and recipients', async () => {
    await openForm()
    fireEvent.change(screen.getByLabelText(/^name/i), { target: { value: 'Watch it' } })
    fireEvent.change(screen.getByLabelText(/^condition/i),
      { target: { value: 'SUM(revenue) < 50' } })
    fireEvent.change(screen.getByLabelText(/^email/i),
      { target: { value: 'a@example.com, b@example.com' } })
    fireEvent.change(screen.getByLabelText(/^check every/i), { target: { value: '30' } })
    fireEvent.click(screen.getByRole('button', { name: /^create$/i }))

    await waitFor(() => expect(alertsApi.create).toHaveBeenCalledWith(1, {
      name: 'Watch it', expression: 'SUM(revenue) < 50',
      interval_minutes: 30, recipients: ['a@example.com', 'b@example.com'],
    }))
  })

  it('will not submit without a name, a condition and a recipient', async () => {
    await openForm()
    const create = screen.getByRole('button', { name: /^create$/i })
    expect(create).toBeDisabled()

    fireEvent.change(screen.getByLabelText(/^name/i), { target: { value: 'x' } })
    expect(create).toBeDisabled()
    fireEvent.change(screen.getByLabelText(/^condition/i), { target: { value: 'SUM(revenue) < 1' } })
    expect(create).toBeDisabled()
    fireEvent.change(screen.getByLabelText(/^email/i), { target: { value: 'a@example.com' } })
    await waitFor(() => expect(create).toBeEnabled())
  })

  it('shows the new alert without a reload', async () => {
    await openForm()
    fireEvent.change(screen.getByLabelText(/^name/i), { target: { value: 'Watch it' } })
    fireEvent.change(screen.getByLabelText(/^condition/i), { target: { value: 'SUM(revenue) < 50' } })
    fireEvent.change(screen.getByLabelText(/^email/i), { target: { value: 'a@example.com' } })
    vi.mocked(alertsApi.list).mockResolvedValue(
      [...EXISTING, { ...EXISTING[0], id: 6, name: 'Watch it' }] as never)
    fireEvent.click(screen.getByRole('button', { name: /^create$/i }))
    expect(await screen.findByText('Watch it')).toBeInTheDocument()
  })

  it('surfaces the backend’s own refusal', async () => {
    /**
     * The expression is checked at CREATION by the same sandbox gate widgets
     * use, because an alert that fails validation would otherwise report an
     * evaluation error every tick forever. That refusal names the problem;
     * "something went wrong" does not.
     */
    vi.mocked(alertsApi.create).mockRejectedValue({
      response: { data: { detail: "expression rejected: name 'os' is not defined" } } })
    await openForm()
    fireEvent.change(screen.getByLabelText(/^name/i), { target: { value: 'x' } })
    fireEvent.change(screen.getByLabelText(/^condition/i), { target: { value: 'os.system()' } })
    fireEvent.change(screen.getByLabelText(/^email/i), { target: { value: 'a@example.com' } })
    fireEvent.click(screen.getByRole('button', { name: /^create$/i }))
    expect(await screen.findByText(/expression rejected/i)).toBeInTheDocument()
  })

  it('explains that it fires on the rising edge only', async () => {
    // Without this the feature reads as broken: a condition that is already
    // true sends nothing, and the person who set it waits for an email that
    // is never coming.
    await openForm()
    expect(screen.getByText(/becomes true/i)).toBeInTheDocument()
  })
})

describe('removing one', () => {
  it('deletes after confirmation and drops it from the list', async () => {
    panel()
    fireEvent.click(await screen.findByRole('button', { name: /delete Revenue fell/i }))
    fireEvent.click(await screen.findByRole('button', { name: /^delete$/i }))
    await waitFor(() => expect(alertsApi.remove).toHaveBeenCalledWith(1, 5))
  })

  it('does not delete when the confirmation is dismissed', async () => {
    panel()
    fireEvent.click(await screen.findByRole('button', { name: /delete Revenue fell/i }))
    fireEvent.click(await screen.findByRole('button', { name: /cancel/i }))
    await waitFor(() =>
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
    expect(alertsApi.remove).not.toHaveBeenCalled()
  })
})

describe('an alert that is not scheduled', () => {
  /**
   * Caught by photographing the real page, not by a unit test.
   *
   * `interval_minutes = 0` is how this codebase spells "inert": the demo
   * seeder uses it deliberately, and `refresh_scheduler.is_due` returns false
   * for anything <= 0 before it looks at any other field. Rendered arithmetically
   * that became "every 0 minutes", which reads as either a bug or an alert
   * hammering the database every tick — the opposite of what it means.
   */
  it('says it is not scheduled rather than "every 0 minutes"', async () => {
    vi.mocked(alertsApi.list).mockResolvedValue([
      { ...EXISTING[0], interval_minutes: 0 }] as never)
    panel()
    await screen.findByText('Revenue fell')
    expect(screen.queryByText(/every 0 minutes/i)).not.toBeInTheDocument()
    expect(screen.getByText(/not scheduled/i)).toBeInTheDocument()
  })

  it('still shows a real interval as an interval', async () => {
    panel()
    await screen.findByText('Revenue fell')
    expect(screen.getByText(/every 1 hour/i)).toBeInTheDocument()
  })
})
