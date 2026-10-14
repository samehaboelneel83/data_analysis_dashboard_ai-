import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { DirectionProvider } from '../../contexts/DirectionContext'
import PageTabs, { type PageTab } from './PageTabs'
import SaveState from './SaveState'
import ZoomControl from './ZoomControl'

/**
 * Redesign 7e1: the builder's second row (page tabs with a per-page menu,
 * zoom and Fit) and the header's save state.
 */

const PAGES: PageTab[] = [
  { id: 1, name: 'Page 1', page_type: 'normal' },
  { id: 2, name: 'Detail', page_type: 'normal' },
  { id: 3, name: 'Notes', page_type: 'hidden' },
]

function tabs(over: Partial<Parameters<typeof PageTabs>[0]> = {}) {
  const props = {
    pages: PAGES, activeId: 1, renamingId: null, renameValue: '', onRenameValue: vi.fn(),
    onSelect: vi.fn(), onStartRename: vi.fn(), onSaveName: vi.fn(), onDelete: vi.fn(), onMove: vi.fn(),
    onSettings: vi.fn(), onAdd: vi.fn(), label: (n: string) => n, ...over,
  }
  render(<PageTabs {...props} />)
  return props
}

describe('page tabs (7e1)', () => {
  it('a group of page buttons; the open one is current; a click opens another', () => {
    const p = tabs()
    expect(screen.getByRole('group', { name: 'Pages' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Page 1' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('button', { name: 'Detail' })).not.toHaveAttribute('aria-current')
    fireEvent.click(screen.getByRole('button', { name: 'Detail' }))
    expect(p.onSelect).toHaveBeenCalledWith(PAGES[1])
  })

  it('marks a hidden page, in words for a screen reader', () => {
    tabs()
    expect(screen.getByRole('button', { name: 'Notes (hidden page)' })).toBeInTheDocument()
  })

  it('each page has a menu: rename, move, page settings and delete', () => {
    const p = tabs()
    fireEvent.click(screen.getByRole('button', { name: 'Page options: Detail' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Move left' }))
    expect(p.onMove).toHaveBeenCalledWith(PAGES[1], -1)
    fireEvent.click(screen.getByRole('button', { name: 'Page options: Detail' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Delete page' }))
    expect(p.onDelete).toHaveBeenCalledWith(PAGES[1])
    fireEvent.click(screen.getByRole('button', { name: 'Page options: Page 1' }))
    expect(screen.getByRole('menuitem', { name: 'Move left' })).toBeDisabled()
    fireEvent.click(screen.getByRole('menuitem', { name: 'Rename' }))
    expect(p.onStartRename).toHaveBeenCalledWith(PAGES[0])
  })

  it('a double-click renames, as before; Enter saves', () => {
    const p = tabs({ renamingId: 2, renameValue: 'Detail' })
    const box = screen.getByRole('textbox', { name: 'Page name' })
    fireEvent.keyDown(box, { key: 'Enter' })
    expect(p.onSaveName).toHaveBeenCalledWith(PAGES[1])
  })

  it('in Arabic, "Move left" still moves the page to the LEFT: later in the order', () => {
    localStorage.setItem('datalytics.language', 'ar'); localStorage.setItem('datalytics.direction', 'rtl')
    try {
      const onMove = vi.fn()
      render(<DirectionProvider><PageTabs pages={PAGES} activeId={1} renamingId={null} renameValue="" onRenameValue={vi.fn()}
        onSelect={vi.fn()} onStartRename={vi.fn()} onSaveName={vi.fn()} onDelete={vi.fn()} onMove={onMove}
        onSettings={vi.fn()} onAdd={vi.fn()} label={n => n} /></DirectionProvider>)
      fireEvent.click(screen.getByRole('button', { name: 'خيارات الصفحة: Detail' }))
      fireEvent.click(screen.getByRole('menuitem', { name: 'نقل لليسار' }))
      expect(onMove).toHaveBeenCalledWith(PAGES[1], 1)
    } finally { localStorage.removeItem('datalytics.language'); localStorage.removeItem('datalytics.direction') }
  })

  it('the last page cannot be deleted', () => {
    tabs({ pages: [PAGES[0]] })
    fireEvent.click(screen.getByRole('button', { name: 'Page options: Page 1' }))
    expect(screen.queryByRole('menuitem', { name: 'Delete page' })).toBeNull()
  })

  it('adds a page', () => {
    const p = tabs()
    fireEvent.click(screen.getByRole('button', { name: 'Add page' }))
    expect(p.onAdd).toHaveBeenCalled()
  })
})

describe('save state (7e1)', () => {
  it('says Saving… while a save is in flight, then Saved with how long ago', () => {
    vi.useFakeTimers()
    try {
      const { rerender } = render(<SaveState saving />)
      expect(screen.getByRole('status')).toHaveTextContent('Saving…')
      rerender(<SaveState saving={false} />)
      expect(screen.getByRole('status')).toHaveTextContent(/^Saved · just now$/)
      act(() => { vi.advanceTimersByTime(60_000) })
      expect(screen.getByRole('status')).toHaveTextContent(/^Saved · 1 minute ago$/)
    } finally { vi.useRealTimers() }
  })

  it('says just Saved before anything was saved in this visit', () => {
    render(<SaveState saving={false} />)
    expect(screen.getByRole('status')).toHaveTextContent(/^Saved$/)
  })
})

describe('zoom (7e1)', () => {
  it('steps by 10 within 50–150, and Fit returns to the page width', () => {
    const on = vi.fn()
    const { rerender } = render(<ZoomControl zoom={100} onZoom={on} />)
    fireEvent.click(screen.getByRole('button', { name: 'Zoom in' }))
    expect(on).toHaveBeenLastCalledWith(110)
    rerender(<ZoomControl zoom={50} onZoom={on} />)
    expect(screen.getByRole('button', { name: 'Zoom out' })).toBeDisabled()
    rerender(<ZoomControl zoom={150} onZoom={on} />)
    expect(screen.getByRole('button', { name: 'Zoom in' })).toBeDisabled()
    expect(screen.getByText('150%')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Fit/ }))
    expect(on).toHaveBeenLastCalledWith(100)
  })
})
