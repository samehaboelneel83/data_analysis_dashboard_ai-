import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { useModalDialog } from './useModalDialog'

/**
 * Nine dialogs shipped with no Escape, no focus trap and no `aria-modal`: a
 * keyboard user could enter any of them and not get out, because Tab walks
 * straight past the dialog into the page behind it while the dialog still
 * covers the screen.
 *
 * The trap is the property worth testing hardest. `ConfirmDialog`'s original
 * queried `'button'`, which is right for a dialog holding exactly two buttons
 * and wrong for everything else -- so these use a dialog with an input, a
 * select and a disabled button, which is what the real ones look like.
 */

function Dialog({ onClose, autoFocus }: { onClose: () => void; autoFocus?: boolean }) {
  const ref = useModalDialog<HTMLDivElement>(onClose, { autoFocus })
  return (
    <div ref={ref} role="dialog" aria-modal="true" aria-label="Test dialog">
      <input aria-label="first" />
      <select aria-label="middle"><option>a</option></select>
      <button disabled>skipped</button>
      <button>last</button>
    </div>
  )
}

const setup = (autoFocus?: boolean) => {
  const onClose = vi.fn()
  render(
    <div>
      <button>outside before</button>
      <Dialog onClose={onClose} autoFocus={autoFocus} />
      <button>outside after</button>
    </div>,
  )
  return onClose
}

describe('useModalDialog', () => {
  it('closes on Escape', () => {
    const onClose = setup()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('focuses the first focusable control on open', () => {
    setup()
    expect(document.activeElement).toBe(screen.getByLabelText('first'))
  })

  it('leaves focus alone when the caller opts out', () => {
    // A dialog that manages its own initial focus -- a search palette putting
    // the caret in its query box -- must not be overridden.
    setup(false)
    expect(document.activeElement).not.toBe(screen.getByLabelText('first'))
  })

  it('cycles forward from the last control back into the dialog', () => {
    // THE test. Without the trap this lands on "outside after" and the user is
    // tabbing through a page they cannot see.
    setup()
    screen.getByRole('button', { name: 'last' }).focus()
    fireEvent.keyDown(window, { key: 'Tab' })
    expect(document.activeElement).toBe(screen.getByLabelText('first'))
  })

  it('cycles backward from the first control', () => {
    setup()
    screen.getByLabelText('first').focus()
    fireEvent.keyDown(window, { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'last' }))
  })

  it('includes inputs and selects, not just buttons', () => {
    // ConfirmDialog's trap queried 'button' because it has exactly two. A
    // generic dialog holds inputs and selects, and skipping them would trap
    // the user on the buttons while the fields stayed unreachable.
    setup()
    screen.getByLabelText('first').focus()
    fireEvent.keyDown(window, { key: 'Tab' })
    expect(document.activeElement).toBe(screen.getByLabelText('middle'))
  })

  it('skips a disabled control', () => {
    setup()
    screen.getByLabelText('middle').focus()
    fireEvent.keyDown(window, { key: 'Tab' })
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'last' }))
  })

  it('restores focus to whatever opened it', () => {
    // Otherwise focus falls back to <body> and a keyboard user loses their
    // place in the page entirely.
    const onClose = vi.fn()
    render(<div><button>opener</button></div>)
    const opener = screen.getByRole('button', { name: 'opener' })
    opener.focus()

    const { unmount } = render(<Dialog onClose={onClose} />)
    expect(document.activeElement).not.toBe(opener)
    unmount()
    expect(document.activeElement).toBe(opener)
  })
})
