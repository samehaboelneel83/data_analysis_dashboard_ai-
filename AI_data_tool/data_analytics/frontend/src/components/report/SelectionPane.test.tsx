import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import SelectionPane from './SelectionPane'
import type { Widget } from '../../types/report'

function widget(id: number, title: string, hidden = false): Widget {
  return { id, page_id: 100, widget_type: 'bar', title, config: { hidden }, layout: { x: 0, y: 0, w: 6, h: 5 }, created_at: '2026-01-01' }
}

describe('SelectionPane', () => {
  it('lists widgets with a visibility toggle', () => {
    render(<SelectionPane widgets={[widget(1, 'Sales'), widget(2, 'Costs')]} onUpdate={vi.fn()} />)
    expect(screen.getByText('Sales')).toBeInTheDocument()
    expect(screen.getByText('Costs')).toBeInTheDocument()
  })

  it('toggling a widget calls onUpdate with the flipped hidden flag', () => {
    const onUpdate = vi.fn()
    render(<SelectionPane widgets={[widget(1, 'Sales', false)]} onUpdate={onUpdate} />)
    fireEvent.click(screen.getByRole('button', { name: /Sales/i }))
    expect(onUpdate).toHaveBeenCalledWith(1, { hidden: true })
  })
})
