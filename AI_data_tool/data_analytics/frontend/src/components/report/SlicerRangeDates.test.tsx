import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import SlicerRange, { rangeLabel } from './SlicerRange'

describe('a range control on a date', () => {
  const data = { column: 'when', kind: 'date', min: '2024-01-01', max: '2024-04-09' }

  it('takes two days from a calendar and applies them as they are', () => {
    const onApply = vi.fn()
    render(<SlicerRange data={data} value={null} onApply={onApply} />)
    const from = screen.getByLabelText('when from') as HTMLInputElement
    const to = screen.getByLabelText('when to') as HTMLInputElement
    expect(from.type).toBe('date')
    expect(from.min).toBe('2024-01-01')
    expect(to.max).toBe('2024-04-09')
    fireEvent.change(from, { target: { value: '2024-01-10' } })
    fireEvent.change(to, { target: { value: '2024-01-12' } })
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }))
    expect(onApply).toHaveBeenCalledWith(['2024-01-10', '2024-01-12'], 'when')
  })

  it('refuses a first day after the second, takes one open end, and clears with both empty', () => {
    const onApply = vi.fn()
    render(<SlicerRange data={data} value={['2024-02-01', null]} onApply={onApply} />)
    const from = screen.getByLabelText('when from') as HTMLInputElement
    const to = screen.getByLabelText('when to') as HTMLInputElement
    expect(from.value).toBe('2024-02-01')
    fireEvent.change(to, { target: { value: '2024-01-15' } })
    expect((screen.getByRole('button', { name: 'Apply' }) as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByText('The first date must not be after the second.')).toBeInTheDocument()
    fireEvent.change(from, { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }))
    expect(onApply).toHaveBeenLastCalledWith([null, '2024-01-15'], 'when')
    fireEvent.change(to, { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'Apply' }))
    expect(onApply).toHaveBeenLastCalledWith(null, 'when')
  })

  it('names the range on its chip', () => {
    expect(rangeLabel('when', ['2024-01-10', '2024-01-12'])).toBe('when 2024-01-10 – 2024-01-12')
    expect(rangeLabel('when', [null, '2024-01-12'])).toBe('when ≤ 2024-01-12')
    expect(rangeLabel('amount', [10, 5000])).toBe('amount 10 – 5,000')
  })
})
