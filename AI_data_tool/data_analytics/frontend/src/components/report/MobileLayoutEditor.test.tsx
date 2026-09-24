import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import MobileLayoutEditor from './MobileLayoutEditor'
import type { ReportPage, Widget } from '../../types/report'

function page(overrides: Partial<ReportPage> = {}): ReportPage {
  return {
    id: 100, report_id: 1, name: 'Page 1', page_type: 'normal', position: 0,
    widgets: [], created_at: '2026-01-01', page_size: '16:9', ...overrides,
  }
}

function widget(id: number, title: string): Widget {
  return { id, page_id: 100, widget_type: 'bar', title, config: {}, layout: { x: 0, y: 0, w: 6, h: 5 }, created_at: '2026-01-01' }
}

describe('MobileLayoutEditor', () => {
  it('lists widgets in their default order when no mobile_layout is set', () => {
    const widgets = [widget(1, 'Sales'), widget(2, 'Costs')]
    render(<MobileLayoutEditor page={page()} widgets={widgets} onUpdate={vi.fn()} />)
    const rows = screen.getAllByTestId('mobile-layout-row')
    expect(rows[0]).toHaveTextContent('Sales')
    expect(rows[1]).toHaveTextContent('Costs')
  })

  it('moves a widget down and calls onUpdate with the new order', () => {
    const widgets = [widget(1, 'Sales'), widget(2, 'Costs')]
    const onUpdate = vi.fn()
    render(<MobileLayoutEditor page={page()} widgets={widgets} onUpdate={onUpdate} />)
    fireEvent.click(screen.getAllByRole('button', { name: '↓' })[0])
    expect(onUpdate).toHaveBeenCalledWith({ mobile_layout: { order: [2, 1], hidden: [] } })
  })

  it('toggles a widget hidden and calls onUpdate with the updated hidden list', () => {
    const widgets = [widget(1, 'Sales'), widget(2, 'Costs')]
    const onUpdate = vi.fn()
    render(<MobileLayoutEditor page={page()} widgets={widgets} onUpdate={onUpdate} />)
    fireEvent.click(screen.getAllByRole('checkbox')[0])
    expect(onUpdate).toHaveBeenCalledWith({ mobile_layout: { order: [1, 2], hidden: [1] } })
  })

  it('respects an existing mobile_layout order and appends widgets missing from it', () => {
    const widgets = [widget(1, 'Sales'), widget(2, 'Costs'), widget(3, 'New Widget')]
    render(<MobileLayoutEditor page={page({ mobile_layout: { order: [2, 1], hidden: [] } })} widgets={widgets} onUpdate={vi.fn()} />)
    const rows = screen.getAllByTestId('mobile-layout-row')
    expect(rows.map(r => r.textContent)).toEqual([
      expect.stringContaining('Costs'),
      expect.stringContaining('Sales'),
      expect.stringContaining('New Widget'),
    ])
  })
})
