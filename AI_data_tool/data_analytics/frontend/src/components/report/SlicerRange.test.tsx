import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import SlicerRange, { rangeLabel } from './SlicerRange'

const data = { type: 'slicer_range', column: 'amount', min: 10, max: 214.5, integer: false }

describe('SlicerRange (live check item 12)', () => {
  it('shows the data bounds and applies both ends', () => {
    const onApply = vi.fn()
    render(<SlicerRange data={data} value={null} onApply={onApply} />)
    expect(screen.getByTestId('slicer-range')).toHaveTextContent('Data runs 10 to 214.5')
    fireEvent.change(screen.getByLabelText('amount from'), { target: { value: '20' } })
    fireEvent.change(screen.getByLabelText('amount to'), { target: { value: '50' } })
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }))
    expect(onApply).toHaveBeenCalledWith([20, 50], 'amount')
  })

  it('leaves an empty end open, and both empty clears', () => {
    const onApply = vi.fn()
    render(<SlicerRange data={data} value={[20, 50]} onApply={onApply} />)
    fireEvent.change(screen.getByLabelText('amount to'), { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }))
    expect(onApply).toHaveBeenLastCalledWith([20, null], 'amount')
    fireEvent.change(screen.getByLabelText('amount from'), { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }))
    expect(onApply).toHaveBeenLastCalledWith(null, 'amount')
  })

  it('refuses a reversed range', () => {
    const onApply = vi.fn()
    render(<SlicerRange data={data} value={null} onApply={onApply} />)
    fireEvent.change(screen.getByLabelText('amount from'), { target: { value: '60' } })
    fireEvent.change(screen.getByLabelText('amount to'), { target: { value: '50' } })
    expect(screen.getByRole('button', { name: 'Apply' })).toBeDisabled()
    expect(screen.getByTestId('slicer-range')).toHaveTextContent('must not be larger')
  })

  it('empties when the filter is cleared elsewhere', () => {
    const { rerender } = render(<SlicerRange data={data} value={[20, 50]} />)
    expect(screen.getByLabelText('amount from')).toHaveValue(20)
    rerender(<SlicerRange data={data} value={null} />)
    expect(screen.getByLabelText('amount from')).toHaveValue(null)
  })

  it('says when the column is not a number', () => {
    render(<SlicerRange data={{ column: 'region', error: 'not_numeric' }} value={null} />)
    expect(screen.getByRole('status')).toHaveTextContent('region holds text')
  })

  it('labels the chip by which ends are set', () => {
    expect(rangeLabel('amount', [10, 50])).toBe('amount 10 – 50')
    expect(rangeLabel('amount', [10, null])).toBe('amount ≥ 10')
    expect(rangeLabel('amount', [null, 50])).toBe('amount ≤ 50')
  })
})
