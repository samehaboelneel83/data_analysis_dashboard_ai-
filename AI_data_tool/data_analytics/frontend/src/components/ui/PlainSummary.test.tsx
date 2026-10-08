import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import PlainSummary, { type PlainItem } from './PlainSummary'
import { writeAlwaysShowDetails } from '../../lib/detailsPreference'

const items: PlainItem[] = [
  {
    id: 'imported', tone: 'warning',
    what: '73% of "imported" is empty.',
    why: 'Counting blanks as "No" would undercount imported cars.',
    todo: 'Treat empty as "Unknown".',
  },
  { id: 'dups', tone: 'good', what: 'No duplicate rows.' },
]

describe('PlainSummary', () => {
  beforeEach(() => localStorage.clear())

  it('reads what, why and what to do for each line', () => {
    render(<PlainSummary items={items} />)
    expect(screen.getByText('73% of "imported" is empty.')).toBeInTheDocument()
    expect(screen.getByText('Counting blanks as "No" would undercount imported cars.')).toBeInTheDocument()
    expect(screen.getByText('What to do:')).toBeInTheDocument()
    expect(screen.getByText('No duplicate rows.')).toBeInTheDocument()
  })

  it('keeps the details closed until asked, then shows them', () => {
    render(<PlainSummary items={items} details={<p>full report</p>} />)
    expect(screen.queryByText('full report')).not.toBeInTheDocument()
    const toggle = screen.getByRole('button', { name: 'Show details' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(toggle)
    expect(screen.getByText('full report')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Hide details' })).toHaveAttribute('aria-expanded', 'true')
  })

  it('opens the details from the start for a user who always wants them', () => {
    writeAlwaysShowDetails(true)
    render(<PlainSummary items={items} details={<p>full report</p>} />)
    expect(screen.getByText('full report')).toBeInTheDocument()
  })

  it('follows the preference when it changes while on screen', () => {
    render(<PlainSummary items={items} details={<p>full report</p>} />)
    act(() => writeAlwaysShowDetails(true))
    expect(screen.getByText('full report')).toBeInTheDocument()
  })

  it('runs a line action and shows it done', () => {
    const onClick = vi.fn()
    const { rerender } = render(<PlainSummary items={[{ ...items[0], action: { label: 'Fix it', onClick } }]} />)
    fireEvent.click(screen.getByRole('button', { name: 'Fix it' }))
    expect(onClick).toHaveBeenCalledOnce()
    rerender(<PlainSummary items={[{ ...items[0], action: { label: 'Fix it', onClick, done: true } }]} />)
    expect(screen.getByRole('button', { name: 'Done' })).toBeDisabled()
  })

  it('says so when there is nothing to report', () => {
    render(<PlainSummary items={[]} empty="Nothing to fix." />)
    expect(screen.getByText('Nothing to fix.')).toBeInTheDocument()
  })
})
