import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import CheckStep from './CheckStep'
import { setupApi, type SetupCheckStep, type SetupFindings } from '../../services/api'

vi.mock('../../services/api', async (orig) => {
  const real = await orig<typeof import('../../services/api')>()
  return { ...real, setupApi: { check: vi.fn(), runCheck: vi.fn(), fix: vi.fn() } }
})

const findings = (over: Partial<SetupFindings> = {}): SetupFindings => ({
  pending: false, failed: null, rows: 9319, columns: 11, fixed: [], language: 'en', checked: true,
  health: [
    { id: 'empty:imported:0', tone: 'warning', kind: 'empty', column: 'imported', what: '73% of “imported” is empty.',
      why: 'Charts describe only 27% of the rows.', todo: 'Treat empty values as “Unknown”.',
      action: { kind: 'fill', column: 'imported', label: 'Treat empty as “Unknown”' } },
    { id: 'rule:x:0', tone: 'warning', kind: 'rule', column: 'car_age, mileage', what: 'Old cars with almost no km (254 / 6,773)',
      why: 'Likely typos.', todo: 'Leave them out.',
      action: { kind: 'exclude', label: 'Leave those rows out', expression: 'e', rule: 'r' } },
  ],
  insights: [{ id: 'insight:0', tone: 'insight', kind: 'standout', what: 'Coupes sell for 5.7M on average.',
               why: 'A premium segment.', todo: null, action: null }],
  ...over,
})

const step = (f = findings()): SetupCheckStep => ({ datasets: [{ id: 226, name: 'Cars 2015+', mode: 'import', row_count: 9319, findings: f }] })

const renderStep = () => {
  const onNext = vi.fn()
  render(<MemoryRouter><CheckStep sourceId={38} onNext={onNext} onBack={vi.fn()} /></MemoryRouter>)
  return onNext
}

beforeEach(() => vi.clearAllMocks())

describe('Guided setup — Check & discover', () => {
  it('reads plainly: what, why, what to do, then what the data shows', async () => {
    vi.mocked(setupApi.check).mockResolvedValue(step())
    renderStep()
    expect(await screen.findByText('73% of “imported” is empty.')).toBeInTheDocument()
    expect(screen.getByText('2 things to know before you chart this data.')).toBeInTheDocument()
    expect(screen.getByText('Coupes sell for 5.7M on average.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Show details' }))
    expect(screen.getByRole('link', { name: /full quality report/ })).toHaveAttribute('href', '/datasets/226?tab=rules')
  })

  it('applies a fix, or saves a rule as a warning', async () => {
    vi.mocked(setupApi.check).mockResolvedValue(step())
    vi.mocked(setupApi.fix).mockResolvedValue({ findings: findings() })
    renderStep()
    fireEvent.click(await screen.findByRole('button', { name: 'Treat empty as “Unknown”' }))
    await waitFor(() => expect(setupApi.fix).toHaveBeenCalledWith(38, 226, 'empty:imported:0', 'fix', 'en'))
    fireEvent.click(screen.getByRole('button', { name: 'Warn me on every refresh' }))
    await waitFor(() => expect(setupApi.fix).toHaveBeenCalledWith(38, 226, 'rule:x:0', 'check', 'en'))
  })

  it('shows a fix already applied as done', async () => {
    vi.mocked(setupApi.check).mockResolvedValue(step(findings({ fixed: ['empty:imported:0|fix'] })))
    renderStep()
    expect(await screen.findByRole('button', { name: 'Done' })).toBeDisabled()
  })

  it('says it is checking while the check runs', async () => {
    vi.mocked(setupApi.check).mockResolvedValue(step(findings({ pending: true, health: [], insights: [] })))
    renderStep()
    expect(await screen.findByText(/Checking the data/)).toBeInTheDocument()
  })

  it('checks again only when asked', async () => {
    vi.mocked(setupApi.check).mockResolvedValue(step())
    vi.mocked(setupApi.runCheck).mockResolvedValue({ findings: findings() })
    renderStep()
    fireEvent.click(await screen.findByRole('button', { name: /Check again/ }))
    await waitFor(() => expect(setupApi.runCheck).toHaveBeenCalledWith(38, 226, 'en'))
  })

  it('moves on to the dashboard', async () => {
    vi.mocked(setupApi.check).mockResolvedValue(step())
    const onNext = renderStep()
    fireEvent.click(await screen.findByRole('button', { name: 'Next: Dashboard' }))
    expect(onNext).toHaveBeenCalled()
  })
})
