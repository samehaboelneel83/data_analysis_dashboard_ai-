/* What the chat shows while it is working.
 *
 * Found by timing the real thing. Asking "suggest a dashboard for me" against the
 * Moodle connection takes 25 seconds on a good run and 340 on a bad one — it
 * designs three dashboards, runs each proposed query against the database, and
 * repairs the ones that fail. All of that is legitimate work.
 *
 * The chat showed none of it. The Send button greyed out and nothing else
 * happened, sometimes for minutes. A person cannot tell a slow answer from a
 * hung one, so they press Send again, or reload, and lose the answer that was
 * about to arrive.
 *
 * So: a pending bubble that counts, and — once it is clear this is one of the
 * long ones — says what is actually taking the time.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act, render, screen, waitFor } from '@testing-library/react'
import Pending from './Pending'

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

describe('the pending indicator', () => {
  it('appears as soon as the question is sent', () => {
    render(<Pending question="what were total sales?" />)
    expect(screen.getByRole('status')).toBeInTheDocument()
  })

  it('counts the seconds, so a slow answer is visibly alive', () => {
    render(<Pending question="what were total sales?" />)
    act(() => { vi.advanceTimersByTime(3000) })
    expect(screen.getByRole('status').textContent).toMatch(/3\s*s/)
  })

  it('keeps counting past a minute in a readable form', () => {
    render(<Pending question="suggest a dashboard for me" />)
    act(() => { vi.advanceTimersByTime(95_000) })
    expect(screen.getByRole('status').textContent).toMatch(/1m\s*35s/)
  })

  it('says nothing extra while the wait is still ordinary', () => {
    render(<Pending question="what were total sales?" />)
    act(() => { vi.advanceTimersByTime(5000) })
    expect(screen.queryByText(/checked against your database/i)).toBeNull()
  })

  it('explains itself once the wait becomes unusual', () => {
    /* Twenty seconds is past every ordinary answer measured on this data, so a
       wait longer than that deserves a reason rather than a spinner. */
    render(<Pending question="suggest a dashboard for me" />)
    act(() => { vi.advanceTimersByTime(21_000) })
    expect(screen.getByText(/checked against your database/i)).toBeInTheDocument()
  })

  it('names dashboard design specifically, because that is the slow one', () => {
    render(<Pending question="Suggest a dashboard for me" />)
    act(() => { vi.advanceTimersByTime(21_000) })
    expect(screen.getByRole('status').textContent).toMatch(/dashboard/i)
  })

  it('does not claim to be designing dashboards for an ordinary question', () => {
    render(<Pending question="what were total sales last quarter?" />)
    act(() => { vi.advanceTimersByTime(21_000) })
    expect(screen.getByRole('status').textContent).not.toMatch(/designing/i)
  })

  it('is announced to a screen reader without shouting', () => {
    /* `polite`, not `assertive`: a progress counter that interrupts whatever the
       reader is saying every second is worse than no counter. */
    render(<Pending question="x" />)
    expect(screen.getByRole('status')).toHaveAttribute('aria-live', 'polite')
  })

  it('stops its timer when it goes away', () => {
    const { unmount } = render(<Pending question="x" />)
    unmount()
    // A leaked interval writing to an unmounted component is a console error in
    // React and a memory leak in a long chat session.
    expect(() => act(() => { vi.advanceTimersByTime(10_000) })).not.toThrow()
  })
})
