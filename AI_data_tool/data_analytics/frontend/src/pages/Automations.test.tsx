import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Automations from './Automations'
import { automationApi, datasetsApi } from '../services/api'

vi.mock('../services/api', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  automationApi: { list: vi.fn(), get: vi.fn(), start: vi.fn(), approve: vi.fn(), reject: vi.fn(), cancel: vi.fn(), retry: vi.fn() },
  datasetsApi: { list: vi.fn() },
}))

const steps = (states: string[]) => ['profile', 'describe', 'scan', 'propose', 'review', 'compose', 'notify']
  .map((name, i) => ({ name, label: name, order: i + 1, status: states[i] ?? 'pending', attempts: 1,
    error: states[i] === 'failed' ? 'source down' : null, next_attempt_at: null, started_at: null, finished_at: null }))

const run = (over: object = {}) => ({
  id: 5, status: 'running', trigger: 'manual', created_by: 1, dataset: { id: 3, name: 'Sales' },
  created_at: '2026-09-26T10:00:00Z', finished_at: null, error: null, summary: null, result_report: null,
  steps: steps(['ok', 'ok', 'running']), ...over,
})

const page = (url = '/automation') => render(<MemoryRouter initialEntries={[url]}><Automations /></MemoryRouter>)

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(datasetsApi.list).mockResolvedValue([
    { id: 3, name: 'Sales', mode: 'import' }, { id: 4, name: 'Live orders', mode: 'directquery' },
  ] as never)
  vi.mocked(automationApi.get).mockImplementation(async (id: number) => run({ id }) as never)
})

describe('Automations (E12)', () => {
  it('says what an automated analysis is when there are none, and offers live datasets too, marked', async () => {
    // HR evaluation, item 3.5: live datasets are analysed through their SQL.
    vi.mocked(automationApi.list).mockResolvedValue([])
    page()
    expect(await screen.findByText('No automated analyses yet')).toBeInTheDocument()
    await waitFor(() => expect(within(screen.getByRole('combobox')).getAllByRole('option')).toHaveLength(3))
    const options = within(screen.getByRole('combobox')).getAllByRole('option').map(o => o.textContent)
    expect(options).toContain('Live orders · live')
  })

  it('starts a run on the chosen dataset', async () => {
    vi.mocked(automationApi.list).mockResolvedValueOnce([]).mockResolvedValue([run()] as never)
    vi.mocked(automationApi.start).mockResolvedValue(run() as never)
    page()
    await screen.findByText('No automated analyses yet')
    await waitFor(() => expect(screen.getAllByRole('option')).toHaveLength(3))
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '3' } })
    fireEvent.click(screen.getByRole('button', { name: 'Start automated analysis' }))
    await waitFor(() => expect(automationApi.start).toHaveBeenCalledWith(3))
    expect(await screen.findByTestId('run-5')).toHaveTextContent('Sales')
  })

  it('shows each step and lets a failed run be retried or cancelled', async () => {
    vi.mocked(automationApi.list).mockResolvedValue([run({ status: 'failed', steps: steps(['ok', 'failed']) })] as never)
    vi.mocked(automationApi.retry).mockResolvedValue(run() as never)
    page()
    const row = await screen.findByTestId('run-5')
    expect(within(row).getByTestId('run-status')).toHaveTextContent('Failed, will retry')
    expect(within(row).getByLabelText('Describe the columns: Failed')).toBeInTheDocument()
    fireEvent.click(within(row).getByRole('button', { name: 'Retry now' }))
    await waitFor(() => expect(automationApi.retry).toHaveBeenCalledWith(5))
    expect(within(row).getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
  })

  it('a held run asks for the decision, with what review rejected and why', async () => {
    vi.mocked(automationApi.list).mockResolvedValue([run({ status: 'needs_review', steps: steps(['ok', 'ok', 'ok', 'ok', 'ok']) })] as never)
    vi.mocked(automationApi.get).mockResolvedValue(run({
      status: 'needs_review', widgets_accepted: 3, widgets_rejected: 2,
      rejection_reasons: [{ title: 'Revenue by id', reason: 'an identifier is not a category' }],
    }) as never)
    vi.mocked(automationApi.reject).mockResolvedValue(run({ status: 'cancelled' }) as never)
    page('/automation?run=5')
    const decision = await screen.findByTestId('run-decision')
    await waitFor(() => expect(decision).toHaveTextContent('Review kept 3 proposed charts and rejected 2'))
    expect(decision).toHaveTextContent('Revenue by id — an identifier is not a category')
    fireEvent.change(within(decision).getByLabelText('Why stop? (optional)'), { target: { value: 'wrong measure' } })
    fireEvent.click(within(decision).getByRole('button', { name: 'Stop' }))
    await waitFor(() => expect(automationApi.reject).toHaveBeenCalledWith(5, 'wrong measure'))
  })

  it('a held run with nothing kept says so and offers only to stop (found live)', async () => {
    vi.mocked(automationApi.list).mockResolvedValue([run({ status: 'needs_review', error: 'nothing was proposed to review' })] as never)
    vi.mocked(automationApi.get).mockResolvedValue(run({ status: 'needs_review', widgets_accepted: 0, widgets_rejected: 0 }) as never)
    page()
    const decision = await screen.findByTestId('run-decision')
    await waitFor(() => expect(decision).toHaveTextContent('Nothing passed review, so there is no report to build'))
    expect(decision).toHaveTextContent('nothing was proposed to review')
    expect(within(decision).queryByRole('button', { name: 'Build the report' })).not.toBeInTheDocument()
    expect(within(decision).getByRole('button', { name: 'Stop' })).toBeInTheDocument()
  })

  it('approving a held run builds the report', async () => {
    vi.mocked(automationApi.list).mockResolvedValue([run({ status: 'needs_review', widgets_accepted: 2 })] as never)
    vi.mocked(automationApi.approve).mockResolvedValue(run() as never)
    page()
    fireEvent.click(await screen.findByRole('button', { name: 'Build the report' }))
    await waitFor(() => expect(automationApi.approve).toHaveBeenCalledWith(5))
  })

  it('a finished run links to its report and has nothing to cancel', async () => {
    vi.mocked(automationApi.list).mockResolvedValue([run({
      status: 'done', result_report: { id: 42, name: 'Sales overview' }, summary: '"Sales overview" is ready.',
      steps: steps(['ok', 'ok', 'ok', 'ok', 'ok', 'ok', 'ok']) })] as never)
    page()
    const row = await screen.findByTestId('run-5')
    expect(within(row).getByRole('link', { name: 'Open report' })).toHaveAttribute('href', '/reports/42')
    expect(within(row).queryByRole('button', { name: 'Cancel' })).not.toBeInTheDocument()
    expect(row).toHaveTextContent('"Sales overview" is ready.')
  })

  it('the run a notification names is opened with its steps', async () => {
    vi.mocked(automationApi.list).mockResolvedValue([run()] as never)
    page('/automation?run=5')
    expect(await screen.findByTestId('run-steps')).toHaveTextContent('Scan for findings')
    expect(screen.getByRole('button', { name: 'Details' })).toHaveAttribute('aria-expanded', 'true')
  })
})

describe('Automations polish (5.15, 5.21)', () => {
  it('shows the first unfinished step of a moving run as running', async () => {
    const { shownStepStatus } = await import('./Automations')
    const run = { status: 'running', steps: [
      { name: 'profile', status: 'ok' }, { name: 'describe', status: 'pending' }, { name: 'scan', status: 'pending' }] } as never
    expect(shownStepStatus(run, 1)).toBe('running')
    expect(shownStepStatus(run, 2)).toBe('pending')
    const done = { status: 'failed', steps: [{ name: 'profile', status: 'pending' }] } as never
    expect(shownStepStatus(done, 0)).toBe('pending')
  })

  it('estimates the duration from the rows', async () => {
    const { estimateMinutes } = await import('./Automations')
    expect(estimateMinutes(240_124)).toBe(2)
    expect(estimateMinutes(2_844_047)).toBe(13)
    expect(estimateMinutes(0)).toBe(1)
  })
})

describe('run summary in the reader\'s language', () => {
  it('builds the sentence from the counts', async () => {
    const { runSummary } = await import('./Automations')
    const tt = (k: string, v?: Record<string, string | number>) => `${k}:${JSON.stringify(v ?? {})}`
    const base = { status: 'done', result_report: { id: 1, name: 'HR overview' }, dataset: null, error: null } as never
    expect(runSummary({ ...(base as object), widgets_accepted: 5, widgets_rejected: 0 } as never, tt as never)).toContain('auto.sum.all')
    expect(runSummary({ ...(base as object), widgets_accepted: 0, widgets_rejected: 2 } as never, tt as never)).toContain('auto.sum.nothing')
    expect(runSummary({ ...(base as object) } as never, tt as never)).toBeNull()
  })
})
