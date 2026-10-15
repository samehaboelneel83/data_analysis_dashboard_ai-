import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import CheckStep from './CheckStep'
import { setupApi, type SetupCheckStep, type SetupCleaning, type SetupDemand, type SetupFindings } from '../../services/api'

vi.mock('../../services/api', async (orig) => {
  const real = await orig<typeof import('../../services/api')>()
  return { ...real, setupApi: { check: vi.fn(), runCheck: vi.fn(), fix: vi.fn(), undoFix: vi.fn(), changeDemand: vi.fn() } }
})

const cleaning = (over: Partial<SetupCleaning> = {}): SetupCleaning => ({
  fixed: [{ id: 'a1', said: 'removed 420 copied rows', ai: false },
          { id: 'a2', said: 'left out rows that contradict themselves: delivered before created (55 / 60,000)', ai: true }],
  know: [{ id: 'outliers:fee:0', what: '“fee” has a few extreme values.' }],
  more: 0, rows_before: 64420, rows_after: 63945,
  actions: [{ id: 'a1', said: 'removed 420 copied rows', ai: false, state: 'applied', kind: 'dups', column: null, rows: 420 },
            { id: 'a2', said: 'left out rows that contradict themselves: delivered before created (55 / 60,000)', ai: true,
              state: 'applied', kind: 'rule', column: 'a, b', rows: 55 }],
  ...over,
})

const findings = (over: Partial<SetupFindings> = {}): SetupFindings => ({
  pending: false, failed: null, rows: 63945, columns: 11, fixed: [], language: 'en', checked: true,
  health: [
    { id: 'outliers:fee:0', tone: 'info', kind: 'outliers', column: 'fee', what: '“fee” has a few extreme values.',
      why: 'They pull the average.', todo: 'Prefer the median.', action: null },
    { id: 'empty:note:0', tone: 'warning', kind: 'empty', column: 'note', what: '73% of “note” is empty.',
      why: 'Charts describe only 27% of the rows.', todo: 'Treat empty values as “Unknown”.',
      action: { kind: 'fill', column: 'note', label: 'Treat empty as “Unknown”', rule: 'r' } },
  ],
  insights: [{ id: 'insight:0', tone: 'insight', kind: 'standout', what: 'Same Day parcels are late most often.',
               why: 'A service to watch.', todo: null, action: null }],
  cleaning: cleaning(),
  ...over,
})

const demand = (over: Partial<SetupDemand> = {}): SetupDemand => ({
  pending: false, failed: null, written: true, sentence: 'Express parcels: how many are late, and where.',
  who: 'operations manager', subject: 'Express parcels', questions: [{ id: 'q1', text: 'How many are late?' }],
  exclude: [], scope: [{ dataset_id: 226, said: 'Express', column: 'service_type', op: 'in', values: ['Express'],
                         matched_rows: 17427, of_rows: 64420, status: 'in_dashboard' }],
  source: 'ai', edits: [], language: 'en', ...over,
})

const step = (f = findings(), d: SetupDemand | undefined = demand()): SetupCheckStep => ({
  datasets: [{ id: 226, name: 'All parcels', mode: 'import', row_count: 63945, auto_clean: true, findings: f }], demand: d })

const renderStep = () => {
  const onNext = vi.fn()
  render(<MemoryRouter><CheckStep sourceId={38} flow={7} onNext={onNext} onBack={vi.fn()} /></MemoryRouter>)
  return onNext
}

beforeEach(() => vi.clearAllMocks())

describe('Guided setup — Check & discover', () => {
  it('says first that the data is ready, what was fixed and what to know', async () => {
    vi.mocked(setupApi.check).mockResolvedValue(step())
    renderStep()
    expect(await screen.findByText('Your data is ready — 63,945 rows.')).toBeInTheDocument()
    expect(screen.getByText('We fixed 2 things for you:')).toBeInTheDocument()
    expect(screen.getByText('removed 420 copied rows')).toBeInTheDocument()
    expect(screen.getByText('found by AI')).toBeInTheDocument()
    expect(screen.getByText(/64,420 rows before, 63,945 now/)).toBeInTheDocument()
    expect(screen.getByText('1 thing to know:')).toBeInTheDocument()
    expect(screen.getByText('Same Day parcels are late most often.')).toBeInTheDocument()
    // The full list and every button stay behind the details.
    expect(screen.queryByRole('button', { name: 'Treat empty as “Unknown”' })).not.toBeInTheDocument()
    expect(setupApi.check).toHaveBeenCalledWith(38, 'en', 7)
  })

  it('keeps every detail and manual fix one click away', async () => {
    vi.mocked(setupApi.check).mockResolvedValue(step())
    vi.mocked(setupApi.fix).mockResolvedValue({ findings: findings() })
    renderStep()
    fireEvent.click(await screen.findByRole('button', { name: 'Show details and undo' }))
    expect(screen.getByRole('link', { name: /full quality report/ })).toHaveAttribute('href', '/datasets/226?tab=rules')
    fireEvent.click(screen.getByRole('button', { name: 'Treat empty as “Unknown”' }))
    await waitFor(() => expect(setupApi.fix).toHaveBeenCalledWith(38, 226, 'empty:note:0', 'fix', 'en', 7))
    fireEvent.click(screen.getByRole('button', { name: 'Warn me on every refresh' }))
    await waitFor(() => expect(setupApi.fix).toHaveBeenCalledWith(38, 226, 'empty:note:0', 'check', 'en', 7))
  })

  it('shows a failed fix inline, next to the findings, not only as a toast (B-02)', async () => {
    vi.mocked(setupApi.check).mockResolvedValue(step())
    vi.mocked(setupApi.fix).mockRejectedValue({ response: { status: 400, data: {
      detail: 'A live (DirectQuery) dataset is never refreshed into a file' } } })
    renderStep()
    fireEvent.click(await screen.findByRole('button', { name: 'Show details and undo' }))
    fireEvent.click(screen.getByRole('button', { name: 'Warn me on every refresh' }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Could not apply this fix')
    expect(alert).toHaveTextContent('A live (DirectQuery) dataset is never refreshed into a file')
  })

  it('shows the plain findings while the AI ideas are still coming, and keeps asking (B-12)', async () => {
    vi.mocked(setupApi.check).mockResolvedValue(step(findings({ ai_pending: true, insights: [] })))
    const onNext = renderStep()
    expect(await screen.findByText(/AI ideas are still coming/)).toBeInTheDocument()
    expect(screen.getByText(/ready/i)).toBeInTheDocument()
    // Next is not held back by the AI part.
    fireEvent.click(screen.getByRole('button', { name: /Next/ }))
    expect(onNext).toHaveBeenCalled()
  })

  it('undoes one automatic fix, or all of them', async () => {
    vi.mocked(setupApi.check).mockResolvedValue(step())
    vi.mocked(setupApi.undoFix).mockResolvedValue({ findings: findings() })
    renderStep()
    fireEvent.click(await screen.findByRole('button', { name: 'Show details and undo' }))
    fireEvent.click(screen.getByRole('button', { name: 'Undo: removed 420 copied rows' }))
    await waitFor(() => expect(setupApi.undoFix).toHaveBeenCalledWith(38, 226, 'a1', false, 7))
    fireEvent.click(screen.getByRole('button', { name: 'Undo all fixes' }))
    await waitFor(() => expect(setupApi.undoFix).toHaveBeenCalledWith(38, 226, null, false, 7))
  })

  it('offers to apply again a fix that was undone', async () => {
    const c = cleaning()
    c.actions[0].state = 'undone'
    c.fixed = [c.fixed[1]]
    vi.mocked(setupApi.check).mockResolvedValue(step(findings({ cleaning: c })))
    vi.mocked(setupApi.undoFix).mockResolvedValue({ findings: findings() })
    renderStep()
    fireEvent.click(await screen.findByRole('button', { name: 'Show details and undo' }))
    fireEvent.click(screen.getByRole('button', { name: 'Apply again: removed 420 copied rows' }))
    await waitFor(() => expect(setupApi.undoFix).toHaveBeenCalledWith(38, 226, 'a1', true, 7))
  })

  it('does not clean a dataset that was already in use, and says so', async () => {
    const s = step(findings({ cleaning: cleaning({ fixed: [], actions: [] }) }))
    s.datasets[0].auto_clean = false
    vi.mocked(setupApi.check).mockResolvedValue(s)
    renderStep()
    expect(await screen.findByText(/already in use, so nothing was changed/)).toBeInTheDocument()
  })

  it('shows what it understood the person wants, and takes a correction', async () => {
    vi.mocked(setupApi.check).mockResolvedValue(step())
    vi.mocked(setupApi.changeDemand).mockResolvedValue({ demand: demand({ pending: true }) })
    renderStep()
    const card = (await screen.findByRole('heading', { name: 'What you want' })).closest('section')!
    expect(within(card).getByText('Express parcels: how many are late, and where.')).toBeInTheDocument()
    expect(within(card).getByText('Only service type: Express')).toBeInTheDocument()
    fireEvent.click(within(card).getByRole('button', { name: 'Not right? Change it' }))
    fireEvent.change(within(card).getByRole('textbox', { name: 'Say what you want instead' }), { target: { value: 'Same Day only' } })
    fireEvent.click(within(card).getByRole('button', { name: 'Send' }))
    await waitFor(() => expect(setupApi.changeDemand).toHaveBeenCalledWith(38, 'Same Day only', 'en', 7))
  })

  it('says plainly when the subject asked for is not in the data, and offers what is', async () => {
    const d = demand({ scope: [{ dataset_id: 226, said: 'drone deliveries', column: null, op: 'in', values: [],
                                 matched_rows: 0, of_rows: 64420, status: 'unmatched',
                                 candidates: [{ column: 'service_type', values: ['Express', 'Same Day'] }] }] })
    vi.mocked(setupApi.check).mockResolvedValue(step(findings(), d))
    vi.mocked(setupApi.changeDemand).mockResolvedValue({ demand: demand({ pending: true }) })
    renderStep()
    expect(await screen.findByText(/could not find “drone deliveries”/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Same Day' }))
    await waitFor(() => expect(setupApi.changeDemand).toHaveBeenCalledWith(
      38, 'By “drone deliveries” I mean Same Day (in service_type).', 'en', 7))
  })

  it('says it is checking while the check runs', async () => {
    vi.mocked(setupApi.check).mockResolvedValue(step(findings({ pending: true, health: [], insights: [], cleaning: undefined })))
    renderStep()
    expect(await screen.findByText(/Checking the data/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Next: Dashboard' })).toBeDisabled()
  })

  it('checks again only when asked', async () => {
    vi.mocked(setupApi.check).mockResolvedValue(step())
    vi.mocked(setupApi.runCheck).mockResolvedValue({ findings: findings() })
    renderStep()
    fireEvent.click(await screen.findByRole('button', { name: /Check again/ }))
    await waitFor(() => expect(setupApi.runCheck).toHaveBeenCalledWith(38, 226, 'en', 7))
  })

  it('moves on to the dashboard', async () => {
    vi.mocked(setupApi.check).mockResolvedValue(step())
    const onNext = renderStep()
    fireEvent.click(await screen.findByRole('button', { name: 'Next: Dashboard' }))
    expect(onNext).toHaveBeenCalled()
  })
})
