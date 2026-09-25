import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import IntervalEditor from './IntervalEditor'

const rule = { id: 'r1', kind: 'interval' as const, target: 'mark' as const, column: 'value', bands: [] }

describe('IntervalEditor', () => {
  it('adds a band with numeric bounds', () => {
    const onChange = vi.fn()
    render(<IntervalEditor rule={rule} onChange={onChange} />)

    fireEvent.click(screen.getByRole('button', { name: /add band/i }))
    const calls = onChange.mock.calls
    const emitted = calls[calls.length - 1][0]
    expect(emitted.kind).toBe('interval')
    expect(emitted.bands).toHaveLength(1)
  })

  it('stores bounds as numbers, not strings', () => {
    const onChange = vi.fn()
    const withOne = { ...rule, bands: [{ min: 0, max: 0, color: '#f87171' }] }
    render(<IntervalEditor rule={withOne} onChange={onChange} />)

    fireEvent.change(screen.getByLabelText(/band 1 minimum/i), { target: { value: '60' } })
    const calls = onChange.mock.calls
    expect(calls[calls.length - 1][0].bands[0].min).toBe(60)
  })

  it('explains the boundary convention, which an author cannot infer', () => {
    render(<IntervalEditor rule={rule} onChange={vi.fn()} />)
    expect(screen.getByText(/last band/i)).toBeInTheDocument()
  })

  it('removes a band', () => {
    const onChange = vi.fn()
    const withOne = { ...rule, bands: [{ min: 0, max: 60, color: '#f87171' }] }
    render(<IntervalEditor rule={withOne} onChange={onChange} />)

    fireEvent.click(screen.getByRole('button', { name: /remove band/i }))
    const calls = onChange.mock.calls
    expect(calls[calls.length - 1][0].bands).toEqual([])
  })

  it('leaves a cleared bound visibly blank and does not substitute a number the author never entered', () => {
    const onChange = vi.fn()
    const withOne = { ...rule, bands: [{ min: 10, max: 60, color: '#f87171' }] }
    render(<IntervalEditor rule={withOne} onChange={onChange} />)

    const input = screen.getByLabelText(/band 1 minimum/i) as HTMLInputElement
    fireEvent.change(input, { target: { value: '' } })

    expect(input.value).toBe('')
    // Number('') is 0 — the bug this guards against is a blank field silently
    // snapping to a real value (0) the author never typed.
    expect(onChange).not.toHaveBeenCalled()
  })

  it('allows typing a negative bound keystroke by keystroke', () => {
    const onChange = vi.fn()
    const withOne = { ...rule, bands: [{ min: 0, max: 60, color: '#f87171' }] }
    render(<IntervalEditor rule={withOne} onChange={onChange} />)

    const input = screen.getByLabelText(/band 1 minimum/i) as HTMLInputElement

    // First keystroke: just the minus sign. Number('-') is NaN — must not emit,
    // and the field must still show '-' rather than snapping back to '0'.
    fireEvent.change(input, { target: { value: '-' } })
    expect(input.value).toBe('-')
    expect(onChange).not.toHaveBeenCalled()

    // Second keystroke completes a valid negative number.
    fireEvent.change(input, { target: { value: '-5' } })
    expect(input.value).toBe('-5')
    const calls = onChange.mock.calls
    expect(calls[calls.length - 1][0].bands[0].min).toBe(-5)
  })

  it('allows typing a decimal bound keystroke by keystroke without eating the point', () => {
    const onChange = vi.fn()
    const withOne = { ...rule, bands: [{ min: 0, max: 60, color: '#f87171' }] }
    render(<IntervalEditor rule={withOne} onChange={onChange} />)

    const input = screen.getByLabelText(/band 1 minimum/i) as HTMLInputElement

    // First keystroke: trailing point. Number('0.') is 0 (finite!) — a naive
    // finite-check alone would emit and, if the input then re-renders from the
    // numeric prop, the '.' the author just typed would vanish from the screen.
    fireEvent.change(input, { target: { value: '0.' } })
    expect(input.value).toBe('0.')

    // Second keystroke completes the fraction.
    fireEvent.change(input, { target: { value: '0.5' } })
    expect(input.value).toBe('0.5')
    const calls = onChange.mock.calls
    expect(calls[calls.length - 1][0].bands[0].min).toBe(0.5)
  })

  it('gives each band a distinct accessible name for its Remove button', () => {
    const onChange = vi.fn()
    const withTwo = {
      ...rule,
      bands: [{ min: 0, max: 30, color: '#f87171' }, { min: 30, max: 60, color: '#34d399' }],
    }
    render(<IntervalEditor rule={withTwo} onChange={onChange} />)

    const removeButtons = screen.getAllByRole('button', { name: /remove band/i })
    expect(removeButtons).toHaveLength(2)
    const names = removeButtons.map(b => b.textContent)
    expect(new Set(names).size).toBe(2)

    // The second band's own button removes only that band.
    fireEvent.click(screen.getByRole('button', { name: /remove band 2/i }))
    const calls = onChange.mock.calls
    expect(calls[calls.length - 1][0].bands).toEqual([{ min: 0, max: 30, color: '#f87171' }])
  })

  it('lets an author pick an icon for a band, Power-BI icon-set style', () => {
    const onChange = vi.fn()
    const withOne = { ...rule, bands: [{ min: 0, max: 60, color: '#f87171' }] }
    render(<IntervalEditor rule={withOne} onChange={onChange} />)

    fireEvent.change(screen.getByLabelText(/icon for band 1/i), { target: { value: '⚠️' } })
    const calls = onChange.mock.calls
    expect(calls[calls.length - 1][0].bands[0]).toEqual({ min: 0, max: 60, color: '#f87171', icon: '⚠️' })
  })

  it('lets an author clear a band back to no icon', () => {
    const onChange = vi.fn()
    const withOne = { ...rule, bands: [{ min: 0, max: 60, color: '#f87171', icon: '⚠️' }] }
    render(<IntervalEditor rule={withOne} onChange={onChange} />)

    fireEvent.change(screen.getByLabelText(/icon for band 1/i), { target: { value: '' } })
    const calls = onChange.mock.calls
    expect(calls[calls.length - 1][0].bands[0].icon).toBeUndefined()
  })

  it("gives each band's icon picker a distinct accessible name", () => {
    const onChange = vi.fn()
    const withTwo = {
      ...rule,
      bands: [{ min: 0, max: 30, color: '#f87171' }, { min: 30, max: 60, color: '#34d399' }],
    }
    render(<IntervalEditor rule={withTwo} onChange={onChange} />)

    expect(screen.getByLabelText(/icon for band 1/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/icon for band 2/i)).toBeInTheDocument()
  })
})
