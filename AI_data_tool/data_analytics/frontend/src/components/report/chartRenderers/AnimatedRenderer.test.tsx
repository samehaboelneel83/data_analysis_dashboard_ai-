import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import AnimatedRenderer, { FRAME_MS } from './AnimatedRenderer'
import type { ChartRendererProps } from './types'

const base: Omit<ChartRendererProps, 'data'> = { rows: [], cfg: {}, rtl: false, broadcasts: false,
  localSelected: null, onClickPoint: () => {} }
const data = {
  type: 'animated', inner: 'bar', animate_by: 'year', granularity: null, domain: [0, 60],
  frames: [
    { label: '2024', result: { type: 'series', rows: [{ name: 'N', value: 20 }] } },
    { label: '2025', result: { type: 'series', rows: [{ name: 'N', value: 40 }] } },
    { label: '2026', result: { type: 'empty', rows: [] } },
  ],
}
function Probe() { return <div /> }
afterEach(() => vi.useRealTimers())

describe('AnimatedRenderer (Phase 6.3)', () => {
  it('opens on the latest frame, plays from the start and stops on the last', () => {
    vi.useFakeTimers()
    const onFrame = vi.fn()
    render(<AnimatedRenderer Inner={Probe} onFrame={onFrame} props={{ ...base, data }} />)
    expect(screen.getByTestId('anim-label').textContent).toBe('2026')
    expect(screen.getByText('No rows in 2026')).toBeTruthy()
    fireEvent.click(screen.getByTestId('anim-play'))          // at the end: replays from 0
    expect(screen.getByTestId('anim-label').textContent).toBe('2024')
    act(() => { vi.advanceTimersByTime(FRAME_MS) })
    expect(screen.getByTestId('anim-label').textContent).toBe('2025')
    act(() => { vi.advanceTimersByTime(FRAME_MS * 3) })
    expect(screen.getByTestId('anim-label').textContent).toBe('2026')
    expect(screen.getByLabelText('Play')).toBeTruthy()           // stopped, not looping
    expect(onFrame).toHaveBeenLastCalledWith('2026')
  })

  it('the scrubber pauses and jumps', () => {
    render(<AnimatedRenderer Inner={Probe} props={{ ...base, data }} />)
    fireEvent.change(screen.getByLabelText('year frame'), { target: { value: '0' } })
    expect(screen.getByTestId('anim-label').textContent).toBe('2024')
    expect(screen.getByText(/3 frames by year · one axis for every frame/)).toBeTruthy()
  })
})
