import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import ActionMenu, { type ActionMenuItem } from './ActionMenu'

function makeItems(overrides?: Partial<ActionMenuItem>[]): { items: ActionMenuItem[]; onEdit: ReturnType<typeof vi.fn>; onDelete: ReturnType<typeof vi.fn> } {
  const onEdit = vi.fn()
  const onDelete = vi.fn()
  const items: ActionMenuItem[] = [
    { key: 'edit', label: 'Edit', onSelect: onEdit },
    { key: 'delete', label: 'Delete', onSelect: onDelete, danger: true },
  ]
  if (overrides) overrides.forEach((o, i) => Object.assign(items[i], o))
  return { items, onEdit, onDelete }
}

describe('ActionMenu', () => {
  it('is closed by default and opens the menu on trigger click', () => {
    const { items } = makeItems()
    render(<ActionMenu items={items} label="Row actions" />)
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Row actions' }))
    expect(screen.getByRole('menu')).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Edit' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Delete' })).toBeInTheDocument()
  })

  it('clicking the trigger again closes it', () => {
    const { items } = makeItems()
    render(<ActionMenu items={items} label="Row actions" />)
    const trigger = screen.getByRole('button', { name: 'Row actions' })
    fireEvent.click(trigger)
    expect(screen.getByRole('menu')).toBeInTheDocument()
    fireEvent.click(trigger)
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })

  it('Escape closes the menu and returns focus to the trigger', () => {
    const { items } = makeItems()
    render(<ActionMenu items={items} label="Row actions" />)
    const trigger = screen.getByRole('button', { name: 'Row actions' })
    fireEvent.click(trigger)
    fireEvent.keyDown(screen.getByRole('menu'), { key: 'Escape' })
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('ArrowDown navigates and Enter activates the focused item', () => {
    const { items, onDelete } = makeItems()
    render(<ActionMenu items={items} label="Row actions" />)
    fireEvent.click(screen.getByRole('button', { name: 'Row actions' }))
    const menu = screen.getByRole('menu')
    fireEvent.keyDown(menu, { key: 'ArrowDown' }) // Edit -> Delete
    fireEvent.keyDown(menu, { key: 'Enter' })
    expect(onDelete).toHaveBeenCalledTimes(1)
    // Activating closes the menu and returns focus.
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Row actions' })).toHaveFocus()
  })

  it('ArrowUp wraps to the last item', () => {
    const { items, onDelete } = makeItems()
    render(<ActionMenu items={items} label="Row actions" />)
    fireEvent.click(screen.getByRole('button', { name: 'Row actions' }))
    const menu = screen.getByRole('menu')
    fireEvent.keyDown(menu, { key: 'ArrowUp' }) // Edit -> wraps to Delete
    fireEvent.keyDown(menu, { key: 'Enter' })
    expect(onDelete).toHaveBeenCalledTimes(1)
  })

  it('clicking a menu item fires its handler', () => {
    const { items, onEdit } = makeItems()
    render(<ActionMenu items={items} label="Row actions" />)
    fireEvent.click(screen.getByRole('button', { name: 'Row actions' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'Edit' }))
    expect(onEdit).toHaveBeenCalledTimes(1)
  })

  it('outside click closes the menu without returning focus', () => {
    const { items } = makeItems()
    render(
      <div>
        <button>elsewhere</button>
        <ActionMenu items={items} label="Row actions" />
      </div>
    )
    fireEvent.click(screen.getByRole('button', { name: 'Row actions' }))
    expect(screen.getByRole('menu')).toBeInTheDocument()
    fireEvent.mouseDown(screen.getByRole('button', { name: 'elsewhere' }))
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })

  it('a disabled item is inert: click and Enter do not fire its handler', () => {
    const { items, onDelete } = makeItems([{}, { disabled: true }])
    render(<ActionMenu items={items} label="Row actions" />)
    fireEvent.click(screen.getByRole('button', { name: 'Row actions' }))
    const deleteItem = screen.getByRole('menuitem', { name: 'Delete' })
    expect(deleteItem).toBeDisabled()
    fireEvent.click(deleteItem)
    expect(onDelete).not.toHaveBeenCalled()
    // Menu stays open — nothing happened.
    expect(screen.getByRole('menu')).toBeInTheDocument()
  })

  it('applies danger styling to items marked danger', () => {
    const { items } = makeItems()
    render(<ActionMenu items={items} label="Row actions" />)
    fireEvent.click(screen.getByRole('button', { name: 'Row actions' }))
    const del = screen.getByRole('menuitem', { name: 'Delete' })
    expect(del).toHaveStyle({ color: 'var(--danger)' })
  })
  describe('trigger and alignment', () => {
    it('defaults to the ⋯ ghost button', () => {
      const { items } = makeItems()
      render(<ActionMenu items={items} label="Row actions" />)
      const trigger = screen.getByRole('button', { name: 'Row actions' })
      expect(trigger).toHaveTextContent('⋯')
      expect(trigger.className).toBe('btn btn-ghost btn-sm')
    })

    it('renders a custom trigger and its classes instead', () => {
      // The prop was documented but ignored, so the dense nav rail could not
      // use this component without a second copy of it.
      const { items } = makeItems()
      render(<ActionMenu items={items} label="Add to Sales" triggerClassName=""
        trigger={<span data-testid="plus">+</span>} />)
      const trigger = screen.getByRole('button', { name: 'Add to Sales' })
      expect(within(trigger).getByTestId('plus')).toBeInTheDocument()
      expect(trigger).not.toHaveTextContent('⋯')
      expect(trigger.className).toBe('')
    })

    it('align="end" hangs the popup off the trailing edge, logically', () => {
      // Physical left/right would escape the rail under RTL; the viewport flip
      // cannot help inside a narrow overflow-hidden container either.
      const { items } = makeItems()
      render(<ActionMenu items={items} label="Add to Sales" align="end" />)
      fireEvent.click(screen.getByRole('button', { name: 'Add to Sales' }))
      const menu = screen.getByRole('menu')
      // jsdom serialises a logical inset unitless, unlike physical `left`.
      expect(menu.style.insetInlineEnd).toBe('0')
      expect(menu.style.insetInlineStart).toBe('auto')
    })

    it('still hangs off the leading edge by default', () => {
      const { items } = makeItems()
      render(<ActionMenu items={items} label="Row actions" />)
      fireEvent.click(screen.getByRole('button', { name: 'Row actions' }))
      const menu = screen.getByRole('menu')
      expect(menu.style.left).toBe('0px')
      expect(menu.style.insetInlineEnd).toBe('')
    })
  })
})