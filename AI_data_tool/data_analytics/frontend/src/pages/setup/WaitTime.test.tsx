import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import WaitTime from './WaitTime'

describe('WaitTime (persona test 3.6)', () => {
  it('says how long the step has run and its usual time', () => {
    const since = new Date(Date.now() - 42_000).toISOString().replace('Z', '')   // server UTC, no zone mark
    render(<WaitTime since={since} usual={75} />)
    const text = screen.getByTestId('setup-wait').textContent ?? ''
    expect(text).toMatch(/Running for 0:4[1-3]\./)
    expect(text).toContain('Usually about 75 seconds here.')
  })

  it('rounds long waits to minutes, and says nothing when nothing is known', () => {
    const { container, rerender } = render(<WaitTime usual={200} />)
    expect(container.textContent).toContain('Usually about 3 min here.')
    rerender(<WaitTime />)
    expect(container.textContent).toBe('')
  })
})
