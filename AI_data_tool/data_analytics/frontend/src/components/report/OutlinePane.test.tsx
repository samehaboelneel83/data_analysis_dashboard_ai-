import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import OutlinePane from './OutlinePane'
import type { Report } from '../../types/report'

const report = {
  id: 1, name: 'R', dataset_id: 1, pages: [{
    id: 10, report_id: 1, name: 'Page 1', page_type: 'normal', position: 0,
    widgets: [
      { id: 1, page_id: 10, widget_type: 'container', title: 'Group A', config: {}, layout: { x: 0, y: 0, w: 6, h: 4 } },
      { id: 2, page_id: 10, widget_type: 'bar', title: 'Sales', config: { container_id: 1 }, layout: { x: 0, y: 0, w: 6, h: 4 } },
      { id: 3, page_id: 10, widget_type: 'kpi', title: '', config: {}, layout: { x: 6, y: 0, w: 3, h: 2 } },
    ],
  }],
} as unknown as Report

describe('OutlinePane', () => {
  it('shows pages with widgets, nesting container children', () => {
    render(<OutlinePane report={report} onSelect={() => {}} onRename={() => {}} onSetContainer={() => {}} />)
    expect(screen.getByText(/Page 1/)).toBeInTheDocument()
    expect(screen.getAllByText(/Group A/).length).toBeGreaterThan(0)  // node + container option
    expect(screen.getByText('Sales')).toBeInTheDocument()
    expect(screen.getByText('kpi 3')).toBeInTheDocument()   // untitled fall back to type+id
  })

  it('click selects; double-click renames', () => {
    const onSelect = vi.fn(); const onRename = vi.fn()
    render(<OutlinePane report={report} onSelect={onSelect} onRename={onRename} onSetContainer={() => {}} />)
    fireEvent.click(screen.getByText('Sales'))
    expect(onSelect).toHaveBeenCalledWith(2, 10)
    fireEvent.doubleClick(screen.getByText('Sales'))
    const input = screen.getByLabelText('Rename Sales')
    fireEvent.change(input, { target: { value: 'Revenue' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onRename).toHaveBeenCalledWith(2, 10, 'Revenue')
  })

  it('re-parents a widget through the container select', () => {
    const onSetContainer = vi.fn()
    render(<OutlinePane report={report} onSelect={() => {}} onRename={() => {}} onSetContainer={onSetContainer} />)
    fireEvent.change(screen.getByLabelText('Container for kpi 3'), { target: { value: '1' } })
    expect(onSetContainer).toHaveBeenCalledWith(3, 10, 1)
  })
})
