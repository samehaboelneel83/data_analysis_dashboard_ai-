import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import SubscribeButton from './SubscribeButton'
import { subscriptionApi } from '../../services/api'

vi.mock('../../services/api', () => ({
  subscriptionApi: { get: vi.fn(), subscribe: vi.fn(), unsubscribe: vi.fn() },
}))
vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}))

/**
 * Self-serve subscriptions shipped working over HTTP and unreachable in the UI
 * — three endpoints with zero frontend callers. These tests cover the control
 * that closes that, and one property in particular:
 *
 * the cadence-dependent fields must match what the server accepts. `weekday`
 * only means something for a weekly schedule and `monthday` only for a monthly
 * one; sending the wrong one is a 400, and sending neither when it is required
 * silently accepts a default the reader never chose.
 */
const openDialog = async () => {
  fireEvent.click(await screen.findByRole('button', { name: /Subscribe/ }))
  return screen.findByRole('dialog')
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(subscriptionApi.get).mockResolvedValue({ subscribed: false } as never)
  vi.mocked(subscriptionApi.subscribe).mockResolvedValue({ subscribed: true } as never)
  vi.mocked(subscriptionApi.unsubscribe).mockResolvedValue(undefined as never)
})

describe('SubscribeButton', () => {
  it('offers to subscribe when the reader is not subscribed', async () => {
    render(<SubscribeButton reportId={7} />)
    expect(await screen.findByRole('button', { name: '🔔 Subscribe' })).toBeInTheDocument()
  })

  it('shows the subscribed state when they already are', async () => {
    vi.mocked(subscriptionApi.get).mockResolvedValue({
      subscribed: true, calendar: { kind: 'weekly', hour: 9, minute: 0, weekday: 2 },
      format: 'pdf',
    } as never)
    render(<SubscribeButton reportId={7} />)
    const btn = await screen.findByRole('button', { name: '🔔 Subscribed' })
    expect(btn).toHaveAttribute('aria-pressed', 'true')
  })

  it('says whose data the copy contains', async () => {
    // Non-obvious and load-bearing: the schedule is owned by the SUBSCRIBER, so
    // RLS resolves as them. A reader assuming they get the author's numbers
    // would misread every figure.
    render(<SubscribeButton reportId={7} />)
    await openDialog()
    expect(screen.getByText(/rows you can see/i)).toBeInTheDocument()
  })

  it('sends a daily schedule with neither weekday nor monthday', async () => {
    render(<SubscribeButton reportId={7} />)
    await openDialog()
    fireEvent.click(screen.getByRole('button', { name: 'Subscribe' }))

    await waitFor(() => expect(subscriptionApi.subscribe).toHaveBeenCalled())
    const body = vi.mocked(subscriptionApi.subscribe).mock.calls[0][1]
    expect(body.cadence).toBe('daily')
    expect(body).not.toHaveProperty('weekday')
    expect(body).not.toHaveProperty('monthday')
  })

  it('sends weekday only for a weekly schedule', async () => {
    render(<SubscribeButton reportId={7} />)
    await openDialog()
    fireEvent.change(screen.getByLabelText('How often'), { target: { value: 'weekly' } })
    fireEvent.change(await screen.findByLabelText('Day of week'), { target: { value: '3' } })
    fireEvent.click(screen.getByRole('button', { name: 'Subscribe' }))

    await waitFor(() => expect(subscriptionApi.subscribe).toHaveBeenCalled())
    const body = vi.mocked(subscriptionApi.subscribe).mock.calls[0][1]
    expect(body).toMatchObject({ cadence: 'weekly', weekday: 3 })
    expect(body).not.toHaveProperty('monthday')
  })

  it('sends monthday only for a monthly schedule', async () => {
    render(<SubscribeButton reportId={7} />)
    await openDialog()
    fireEvent.change(screen.getByLabelText('How often'), { target: { value: 'monthly' } })
    fireEvent.click(screen.getByRole('button', { name: 'Subscribe' }))

    await waitFor(() => expect(subscriptionApi.subscribe).toHaveBeenCalled())
    const body = vi.mocked(subscriptionApi.subscribe).mock.calls[0][1]
    expect(body).toMatchObject({ cadence: 'monthly', monthday: 1 })
    expect(body).not.toHaveProperty('weekday')
  })

  it('never offers a day of month the calendar lacks', async () => {
    // The server caps this at 28 — the only day every month actually has.
    // Offering the 31st would produce a schedule that silently skips February.
    render(<SubscribeButton reportId={7} />)
    await openDialog()
    fireEvent.change(screen.getByLabelText('How often'), { target: { value: 'monthly' } })
    const opts = Array.from(
      (await screen.findByLabelText('Day of month')).querySelectorAll('option'))
    expect(opts).toHaveLength(28)
    expect(opts[opts.length - 1]).toHaveValue('28')
  })

  it('pre-fills the dialog from an existing subscription', async () => {
    // Reopening must show what you chose, not the defaults — otherwise
    // "Update" silently rewrites a schedule the reader did not mean to change.
    vi.mocked(subscriptionApi.get).mockResolvedValue({
      subscribed: true, calendar: { kind: 'weekly', hour: 17, minute: 0, weekday: 4 },
      format: 'pdf',
    } as never)
    render(<SubscribeButton reportId={7} />)
    fireEvent.click(await screen.findByRole('button', { name: '🔔 Subscribed' }))

    expect(await screen.findByLabelText('How often')).toHaveValue('weekly')
    expect(screen.getByLabelText('Day of week')).toHaveValue('4')
    expect(screen.getByLabelText('Hour')).toHaveValue('17')
    expect(screen.getByLabelText('Format')).toHaveValue('pdf')
  })

  it('offers to unsubscribe only when subscribed', async () => {
    render(<SubscribeButton reportId={7} />)
    await openDialog()
    expect(screen.queryByRole('button', { name: 'Unsubscribe' })).toBeNull()
  })

  it('unsubscribes on request', async () => {
    vi.mocked(subscriptionApi.get).mockResolvedValue({
      subscribed: true, calendar: { kind: 'daily', hour: 8, minute: 0 },
    } as never)
    render(<SubscribeButton reportId={7} />)
    fireEvent.click(await screen.findByRole('button', { name: '🔔 Subscribed' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Unsubscribe' }))

    await waitFor(() => expect(subscriptionApi.unsubscribe).toHaveBeenCalledWith(7))
  })

  it('survives a failure to read the current state', async () => {
    // Losing the subscription status must not break the report the reader
    // actually came to look at.
    vi.mocked(subscriptionApi.get).mockRejectedValue(new Error('down'))
    render(<SubscribeButton reportId={7} />)
    expect(await screen.findByRole('button', { name: '🔔 Subscribe' })).toBeInTheDocument()
  })
})
