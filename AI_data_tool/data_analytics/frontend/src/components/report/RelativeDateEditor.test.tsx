import { describe, it, expect, vi } from 'vitest'
import { useState } from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import RelativeDateEditor from './RelativeDateEditor'
import { DEFAULT_SPEC, type RelativeSpec } from '../../lib/relativeDates'

function Harness({ onSpec }: { onSpec: (s: RelativeSpec) => void }) {
  const [v, setV] = useState<RelativeSpec>(DEFAULT_SPEC)
  return <RelativeDateEditor label="F" value={v} onChange={s => { setV(s); onSpec(s) }} />
}

describe('RelativeDateEditor', () => {
  it('is one click for a preset and keeps the anchor choice', () => {
    const onSpec = vi.fn()
    render(<Harness onSpec={onSpec} />)
    expect(screen.getByText('Last 30 days · from latest data')).toBeTruthy()
    fireEvent.change(screen.getByLabelText('F period'), { target: { value: 'ytd' } })
    expect(onSpec).toHaveBeenLastCalledWith({ mode: 'to_date', unit: 'year', anchor: 'data_max' })
    fireEvent.change(screen.getByLabelText('F counted from'), { target: { value: 'today' } })
    expect(screen.getByText('Year to date · from today')).toBeTruthy()
  })

  it('Custom… opens the parts even when the spec matches a preset', () => {
    const onSpec = vi.fn()
    render(<Harness onSpec={onSpec} />)
    expect(screen.queryByLabelText('F number of periods')).toBeNull()
    fireEvent.change(screen.getByLabelText('F period'), { target: { value: 'custom' } })
    fireEvent.change(screen.getByLabelText('F number of periods'), { target: { value: '45' } })
    expect(onSpec).toHaveBeenLastCalledWith({ mode: 'last', unit: 'day', n: 45, anchor: 'data_max' })
    expect(screen.getByText('Last 45 days · from latest data')).toBeTruthy()
  })

  it('shows the include-current option for calendar units and an error for 0 periods', () => {
    const spec: RelativeSpec = { mode: 'last', unit: 'month', n: 0, anchor: 'today' }
    render(<RelativeDateEditor label="G" value={spec} onChange={() => {}} />)
    expect(screen.getByLabelText('G mode')).toBeTruthy()
    expect(screen.getByText(/include the current month/)).toBeTruthy()
    expect(screen.getByRole('alert').textContent).toMatch(/1 to 1000/)
  })
})
