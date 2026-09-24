import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import DataBarEditor from './DataBarEditor'

const rule = { id: 'r1', kind: 'data_bar' as const, target: 'mark' as const, column: 'value' }

describe('DataBarEditor', () => {
  it('leaves min/max blank by default, meaning auto-scaled to the column', () => {
    render(<DataBarEditor rule={rule} onChange={vi.fn()} />)
    expect((screen.getByLabelText(/minimum/i) as HTMLInputElement).value).toBe('')
    expect((screen.getByLabelText(/maximum/i) as HTMLInputElement).value).toBe('')
  })

  it('emits a numeric minimum as the author types it', () => {
    const onChange = vi.fn()
    render(<DataBarEditor rule={rule} onChange={onChange} />)

    fireEvent.change(screen.getByLabelText(/minimum/i), { target: { value: '10' } })
    const last = onChange.mock.calls[onChange.mock.calls.length - 1][0]
    expect(last.min).toBe(10)
    expect(last.kind).toBe('data_bar')
  })

  it('emits a numeric maximum as the author types it', () => {
    const onChange = vi.fn()
    render(<DataBarEditor rule={rule} onChange={onChange} />)

    fireEvent.change(screen.getByLabelText(/maximum/i), { target: { value: '200' } })
    expect(onChange.mock.calls[onChange.mock.calls.length - 1][0].max).toBe(200)
  })

  it('clearing a bound back to blank emits undefined, restoring auto-scaling', () => {
    const onChange = vi.fn()
    const withMin = { ...rule, min: 10 }
    render(<DataBarEditor rule={withMin} onChange={onChange} />)

    fireEvent.change(screen.getByLabelText(/minimum/i), { target: { value: '' } })
    expect(onChange.mock.calls[onChange.mock.calls.length - 1][0].min).toBeUndefined()
  })

  it('does not emit for an incomplete bound like a bare minus sign', () => {
    const onChange = vi.fn()
    render(<DataBarEditor rule={rule} onChange={onChange} />)

    const input = screen.getByLabelText(/minimum/i) as HTMLInputElement
    fireEvent.change(input, { target: { value: '-' } })
    expect(input.value).toBe('-')
    expect(onChange).not.toHaveBeenCalled()
  })

  it('lets an author pick the bar colour, defaulting to a sensible blue', () => {
    render(<DataBarEditor rule={rule} onChange={vi.fn()} />)
    expect((screen.getByLabelText(/bar colour/i) as HTMLInputElement).value).toBe('#60a5fa')
  })

  it('emits a chosen bar colour', () => {
    const onChange = vi.fn()
    render(<DataBarEditor rule={rule} onChange={onChange} />)

    fireEvent.change(screen.getByLabelText(/bar colour/i), { target: { value: '#22c55e' } })
    expect(onChange.mock.calls[onChange.mock.calls.length - 1][0].color).toBe('#22c55e')
  })
})
