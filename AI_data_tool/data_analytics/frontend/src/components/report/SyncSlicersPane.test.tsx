import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import SyncSlicersPane from './SyncSlicersPane'
import type { ReportPage } from '../../types/report'

function page(id: number, name: string, widgets: ReportPage['widgets']): ReportPage {
  return { id, report_id: 1, name, page_type: 'normal', position: 0, widgets, created_at: '2026-01-01', page_size: '16:9' }
}

const SLICER = { id: 9, page_id: 1, widget_type: 'slicer' as const, title: 'Region filter', config: {}, layout: { x: 0, y: 0, w: 3, h: 5 }, created_at: '2026-01-01' }

describe('SyncSlicersPane', () => {
  it('lists slicer widgets across all pages, grouped by page', () => {
    render(<SyncSlicersPane pages={[page(1, 'Overview', [SLICER])]} interactions={{}} onToggleSync={vi.fn()} />)
    expect(screen.getByText('Overview')).toBeInTheDocument()
    expect(screen.getByText('Region filter')).toBeInTheDocument()
  })

  it('toggling calls onToggleSync with the new sync state', () => {
    const onToggleSync = vi.fn()
    render(<SyncSlicersPane pages={[page(1, 'Overview', [SLICER])]} interactions={{}} onToggleSync={onToggleSync} />)
    fireEvent.click(screen.getByRole('button', { name: /This page only/i }))
    expect(onToggleSync).toHaveBeenCalledWith(9, true)
  })
})
