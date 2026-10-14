import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import MiniChart from './MiniChart'

describe('Guided setup — a suggested chart, drawn small', () => {
  it('shows a headline number, and a share as a percentage', () => {
    render(<MiniChart title="Late share" preview={{ kind: 'number', percent: true, rows: [['late', 17.24]] }} />)
    expect(screen.getByText('17.2%')).toBeInTheDocument()
  })

  it('draws one bar per group with its value, longest for the largest', () => {
    const { container } = render(<MiniChart title="By region" preview={{
      kind: 'bars', rows: [['Upper Egypt', 26.6], ['Canal', 13.3]], more: 2 }} />)
    expect(screen.getByText('Upper Egypt')).toBeInTheDocument()
    const bars = container.querySelectorAll<HTMLElement>('.mini__bar')
    expect(bars[0].style.width).toBe('100%')
    expect(bars[1].style.width).toBe('50%')
    expect(screen.getByText('+2')).toBeInTheDocument()
  })

  it('says each part with its share of the whole', () => {
    render(<MiniChart title="Status" preview={{ kind: 'parts', rows: [['Resolved', 235], ['Open', 15]] }} />)
    expect(screen.getByText('235 · 94%')).toBeInTheDocument()
  })

  it('draws a line and names where it starts and ends', () => {
    render(<MiniChart title="Per month" preview={{ kind: 'line', rows: [['2024-01', 1104], ['2025-01', 1800], ['2026-09', 2421]] }} />)
    expect(screen.getByRole('img', { name: 'Per month' })).toBeInTheDocument()
    expect(screen.getByText('2024-01: 1,104')).toBeInTheDocument()
    expect(screen.getByText('2026-09: 2,421')).toBeInTheDocument()
  })

  it('shows the first rows of a table', () => {
    render(<MiniChart title="Records" preview={{ kind: 'table', columns: ['tracking_no', 'city'],
                                                 rows: [['NX1', 'Cairo'], ['NX2', null]] }} />)
    expect(screen.getByText('tracking no')).toBeInTheDocument()
    expect(screen.getByText('NX1')).toBeInTheDocument()
    expect(screen.getByText('—')).toBeInTheDocument()
  })
})
