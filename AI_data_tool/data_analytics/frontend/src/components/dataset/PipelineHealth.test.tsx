import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { PipelineAlertsForm, PipelineHealthLine } from './PipelineHealth'
import type { PipelineHealth } from '../../services/api'
import { MemoryRouter } from 'react-router-dom'
import { AuthContext } from '../../contexts/AuthContext'

vi.mock('../../services/api', () => ({
  datasetsApi: { pipelineHealth: vi.fn(), setPipelineWatch: vi.fn() },
}))
vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))

import { datasetsApi } from '../../services/api'

const base: PipelineHealth = {
  state: 'ok', last_refreshed_at: '2026-10-03T06:21:00Z', freshness_hours: null, recipients: [],
  last_run: null, next_retry_at: null, can_edit: true, freshness_choices: [2, 6, 26, 72, 192],
}

beforeEach(() => vi.clearAllMocks())

describe('PipelineHealthLine (pipeline phase 2)', () => {
  it('says nothing when the data is healthy', () => {
    const { container } = render(<PipelineHealthLine health={base} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('names a failing refresh, its error and the next try', () => {
    render(<PipelineHealthLine health={{ ...base, state: 'failing', next_retry_at: '2026-10-03T07:27:00Z',
      last_run: { status: 'failed', trigger: 'schedule', started_at: null, rows: null, duration_ms: 12,
        error: 'Refresh failed: unable to open database file\n(Background on this error)' } }} />)
    const line = screen.getByTestId('pipeline-health')
    expect(line).toHaveTextContent('Last refresh failed')
    expect(line).toHaveTextContent('unable to open database file')
    expect(line).not.toHaveTextContent('Background')
    expect(line).toHaveTextContent('Next try')
  })

  it('says when data is past its freshness target', () => {
    render(<PipelineHealthLine health={{ ...base, state: 'stale', freshness_hours: 26 }} />)
    expect(screen.getByTestId('pipeline-health')).toHaveTextContent('26 hours')
  })
})

describe('PipelineAlertsForm', () => {
  it('saves the target and the recipients', async () => {
    const onSaved = vi.fn()
    vi.mocked(datasetsApi.setPipelineWatch).mockResolvedValue({ ...base, freshness_hours: 26, recipients: ['ops@example.com'] })
    render(<PipelineAlertsForm datasetId={7} health={base} onSaved={onSaved} />)

    fireEvent.change(screen.getByLabelText('Warn when older than'), { target: { value: '26' } })
    fireEvent.change(screen.getByLabelText(/Also tell/), { target: { value: 'ops@example.com, https://hooks.example.com/x' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save alerts' }))

    await waitFor(() => expect(datasetsApi.setPipelineWatch).toHaveBeenCalledWith(7, {
      freshness_hours: 26, recipients: ['ops@example.com', 'https://hooks.example.com/x'] }))
    expect(onSaved).toHaveBeenCalled()
  })

  it('names who is always told', () => {
    render(<PipelineAlertsForm datasetId={7} health={{ ...base, owners: ['owner@example.com'] }} onSaved={vi.fn()} />)
    expect(screen.getByText(/works again: owner@example.com\./)).toBeInTheDocument()
  })

  it('offers the server choices, days for the long ones', () => {
    render(<PipelineAlertsForm datasetId={7} health={base} onSaved={vi.fn()} />)
    const options = Array.from((screen.getByLabelText('Warn when older than') as HTMLSelectElement).options).map(o => o.text)
    expect(options).toEqual(['No target', '2 hours', '6 hours', '26 hours', '3 days', '8 days'])
  })

  it('"Notify me" adds the caller to the in-app notices', async () => {
    const onSaved = vi.fn()
    vi.mocked(datasetsApi.setPipelineWatch).mockResolvedValue({ ...base, following: true })
    render(<PipelineAlertsForm datasetId={7} health={base} onSaved={onSaved} />)
    fireEvent.click(screen.getByLabelText('Notify me in the app too'))
    await waitFor(() => expect(datasetsApi.setPipelineWatch).toHaveBeenCalledWith(7, { follow: true }))
    expect(onSaved).toHaveBeenCalledWith(expect.objectContaining({ following: true }))
  })

  it('warns that typed emails go nowhere while email is not set up', () => {
    render(<PipelineAlertsForm datasetId={7} health={{ ...base, email_ready: false }} onSaved={vi.fn()} />)
    expect(screen.queryByTestId('health-email-off')).toBeNull()
    fireEvent.change(screen.getByLabelText(/Also tell/), { target: { value: 'ops@example.com' } })
    expect(screen.getByTestId('health-email-off')).toHaveTextContent('Ask an admin')
  })

  it('links an admin to the email settings', () => {
    const auth = { user: { role: { is_org_admin: true } } } as unknown as React.ContextType<typeof AuthContext>
    render(<MemoryRouter><AuthContext.Provider value={auth}>
      <PipelineAlertsForm datasetId={7} health={{ ...base, email_ready: false, recipients: ['ops@example.com'] }} onSaved={vi.fn()} />
    </AuthContext.Provider></MemoryRouter>)
    expect(screen.getByRole('link', { name: 'Set up email' })).toHaveAttribute('href', '/admin/settings')
  })

  it('says nothing about email when it is set up', () => {
    render(<PipelineAlertsForm datasetId={7} health={{ ...base, email_ready: true, recipients: ['ops@example.com'] }} onSaved={vi.fn()} />)
    expect(screen.queryByTestId('health-email-off')).toBeNull()
  })
})
