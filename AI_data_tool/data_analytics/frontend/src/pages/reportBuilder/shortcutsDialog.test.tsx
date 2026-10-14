import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import ShortcutsDialog from './ShortcutsDialog'

describe('shortcuts sheet (7e5)', () => {
  it('lists the canvas and report shortcuts, keys in their own chips', () => {
    render(<ShortcutsDialog onClose={vi.fn()} />)
    const d = screen.getByRole('dialog', { name: 'Keyboard shortcuts' })
    expect(within(d).getByRole('heading', { name: 'Canvas' })).toBeInTheDocument()
    expect(within(d).getByRole('heading', { name: 'Report' })).toBeInTheDocument()
    const dup = within(d).getByText('Duplicate').closest('div') as HTMLElement
    expect(Array.from(dup.querySelectorAll('kbd')).map(k => k.textContent)).toEqual(['Ctrl', 'D'])
    for (const what of ['Resize', 'Jump to a report, dataset or page', 'Ask AI']) expect(within(d).getByText(what)).toBeInTheDocument()
  })

  it('closes from its button and from Escape', () => {
    const onClose = vi.fn()
    render(<ShortcutsDialog onClose={onClose} />)
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(2)
  })
})
