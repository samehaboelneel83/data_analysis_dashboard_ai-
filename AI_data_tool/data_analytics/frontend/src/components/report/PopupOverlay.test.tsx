import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import PopupOverlay from './PopupOverlay'
import type { ReportPage } from '../../types/report'

const page = { id: 7, report_id: 1, name: 'Details', page_type: 'popup', position: 1, widgets: [], created_at: '', page_size: '16:9' } as unknown as ReportPage
beforeEach(() => localStorage.clear())

describe('PopupOverlay resize and export (follow-up)', () => {
  it('resizes, remembers the size, and exports just this page', () => {
    const onExport = vi.fn()
    const { unmount } = render(<PopupOverlay page={page} onClose={vi.fn()} renderWidget={() => null} onExport={onExport} />)
    const dialog = screen.getByTestId('popup-overlay')
    expect(dialog.style.width).toContain('760px')
    fireEvent.change(screen.getByLabelText('Pop-up size'), { target: { value: 'large' } })
    expect(screen.getByTestId('popup-overlay').style.width).toContain('1100px')
    fireEvent.click(screen.getByRole('button', { name: /PDF/ }))
    expect(onExport).toHaveBeenCalledTimes(1)
    unmount()
    render(<PopupOverlay page={page} onClose={vi.fn()} renderWidget={() => null} />)
    expect(screen.getByTestId('popup-overlay').style.width).toContain('1100px')
    expect(screen.queryByRole('button', { name: /PDF/ })).toBeNull()      // no export offered when not allowed
  })
})
