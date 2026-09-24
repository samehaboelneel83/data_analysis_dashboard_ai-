import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import TabOrderPane from './TabOrderPane'
import type { Widget } from '../../types/report'

function widget(id: number, title: string, tabIndex?: number): Widget {
  return { id, page_id: 100, widget_type: 'bar', title, config: { tabIndex }, layout: { x: 0, y: 0, w: 6, h: 5 }, created_at: '2026-01-01' }
}

describe('TabOrderPane', () => {
  it('lists widgets ordered by their current tabIndex', () => {
    render(<TabOrderPane widgets={[widget(1, 'Second', 2), widget(2, 'First', 1)]} onUpdate={vi.fn()} />)
    const rows = screen.getAllByTestId('tab-order-row')
    expect(rows[0]).toHaveTextContent('First')
    expect(rows[1]).toHaveTextContent('Second')
  })

  it('moving a widget down renumbers everyone sequentially', () => {
    const onUpdate = vi.fn()
    render(<TabOrderPane widgets={[widget(1, 'First', 1), widget(2, 'Second', 2)]} onUpdate={onUpdate} />)
    fireEvent.click(screen.getAllByRole('button', { name: '↓' })[0])
    expect(onUpdate).toHaveBeenCalledWith(1, { tabIndex: 2 })
    expect(onUpdate).toHaveBeenCalledWith(2, { tabIndex: 1 })
  })
})
