/**
 * E10: chart marks recharts draws as role="img" without a name are hidden
 * from assistive technology (axe svg-img-alt found 150 on one scatter); a
 * mark that carries a name, like a pie slice, is left for screen readers.
 */
import { describe, it, expect } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import { useEffect, useState } from 'react'
import { MeasuredChart } from './MeasuredChart'

function Marks({ extra = 0 }: { extra?: number }) {
  return (
    <svg>
      <g role="img" data-testid="unnamed" />
      <path role="img" aria-label="North: 150" data-testid="named" />
      {Array.from({ length: extra }, (_, i) => <g key={i} role="img" data-testid={`later-${i}`} />)}
    </svg>
  )
}

function Redraws() {
  const [n, setN] = useState(0)
  useEffect(() => { const t = setTimeout(() => setN(2), 10); return () => clearTimeout(t) }, [])
  return <Marks extra={n} />
}

describe('MeasuredChart', () => {
  it('hides unnamed marks and keeps named ones', () => {
    const { getByTestId } = render(<MeasuredChart>{() => <Marks />}</MeasuredChart>)
    expect(getByTestId('unnamed')).toHaveAttribute('aria-hidden', 'true')
    expect(getByTestId('named')).not.toHaveAttribute('aria-hidden')
  })

  it('hides marks drawn after the first render too', async () => {
    const { getByTestId } = render(<MeasuredChart>{() => <Redraws />}</MeasuredChart>)
    await waitFor(() => expect(getByTestId('later-1')).toHaveAttribute('aria-hidden', 'true'))
  })
})

describe('MeasuredChart resizing', () => {
  it('redraws at once after a one-off change, and waits only while the size keeps changing', async () => {
    const { vi, act } = await import('vitest').then(async v => ({ vi: v.vi, act: (await import('@testing-library/react')).act }))
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'performance', 'Date'] })
    const callbacks: (() => void)[] = []
    const notify = () => callbacks.forEach(cb => cb())
    const Real = window.ResizeObserver
    window.ResizeObserver = class { constructor(cb: () => void) { callbacks.push(cb) } observe() {} disconnect() {} unobserve() {} } as never
    let w = 400
    const rect = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect')
      .mockImplementation(() => ({ width: w, height: 200, top: 0, left: 0, right: w, bottom: 200, x: 0, y: 0, toJSON: () => ({}) }) as DOMRect)
    const seen: number[] = []
    try {
      render(<MeasuredChart>{(pw) => { if (pw) seen.push(pw); return <svg /> }}</MeasuredChart>)
      expect(seen.at(-1)).toBe(400)
      // A panel closed: one jump, long after the last one -- drawn straight away.
      vi.advanceTimersByTime(1000)
      w = 600; act(() => notify())
      expect(seen.at(-1)).toBe(600)
      // A drag: changes every few ms -- the chart waits for the last one.
      w = 610; act(() => notify())
      w = 620; act(() => notify())
      expect(seen.at(-1)).not.toBe(620)
      act(() => { vi.advanceTimersByTime(200) })
      expect(seen.at(-1)).toBe(620)
    } finally {
      rect.mockRestore()
      window.ResizeObserver = Real
      vi.useRealTimers()
    }
  })
})
