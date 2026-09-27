import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import OpenReportsMenu from './OpenReportsMenu'

const reports = [{ id: 1, name: 'Blog - Cell Graphs' }, { id: 2, name: 'Blog - Object Templates' }, { id: 3, name: 'Report 1' }]

describe('Opened reports, in the report header', () => {
  it('one button with the count; the menu ticks the current report and switches to another', () => {
    const onOpen = vi.fn()
    render(<OpenReportsMenu reports={reports} currentId={1} onOpen={onOpen} onClose={vi.fn()} onCloseAll={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Opened reports (3)' }))
    const menu = screen.getByRole('menu', { name: 'Opened reports (3)' })
    expect(within(menu).getByRole('menuitemradio', { name: 'Blog - Cell Graphs' })).toHaveAttribute('aria-checked', 'true')
    fireEvent.click(within(menu).getByRole('menuitemradio', { name: 'Report 1' }))
    expect(onOpen).toHaveBeenCalledWith(3)
  })

  it('closes one report, or all of them', () => {
    const onClose = vi.fn(), onCloseAll = vi.fn()
    render(<OpenReportsMenu reports={reports} currentId={1} onOpen={vi.fn()} onClose={onClose} onCloseAll={onCloseAll} />)
    fireEvent.click(screen.getByRole('button', { name: 'Opened reports (3)' }))
    fireEvent.click(screen.getByRole('button', { name: 'Close Report 1' }))
    expect(onClose).toHaveBeenCalledWith(3)
    fireEvent.click(screen.getByRole('menuitem', { name: 'Close all reports' }))
    expect(onCloseAll).toHaveBeenCalled()
  })

  it('is absent with only the current report open', () => {
    const { container } = render(<OpenReportsMenu reports={[reports[0]]} currentId={1} onOpen={vi.fn()} onClose={vi.fn()} onCloseAll={vi.fn()} />)
    expect(container.innerHTML).toBe('')
  })
})
