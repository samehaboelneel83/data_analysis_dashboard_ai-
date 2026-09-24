import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { ConfirmProvider, useConfirm } from './ConfirmDialog'

/** Harness: a button that asks, and a readout of what the promise resolved to. */
function Harness({ onResult }: { onResult?: (ok: boolean) => void }) {
  const confirm = useConfirm()
  return (
    <button
      onClick={async () => {
        const ok = await confirm({ title: 'Delete "Q3 Report"?', body: 'This cannot be undone.' })
        onResult?.(ok)
      }}
    >
      Delete report
    </button>
  )
}

const open = async (onResult?: (ok: boolean) => void) => {
  render(<ConfirmProvider><Harness onResult={onResult} /></ConfirmProvider>)
  fireEvent.click(screen.getByRole('button', { name: 'Delete report' }))
  return await screen.findByRole('alertdialog')
}

describe('ConfirmDialog', () => {
  it('shows nothing until something asks', () => {
    render(<ConfirmProvider><Harness /></ConfirmProvider>)
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
  })

  it('names itself and its detail for assistive tech', async () => {
    const dlg = await open()
    expect(dlg).toHaveAttribute('aria-modal', 'true')
    expect(dlg).toHaveAccessibleName('Delete "Q3 Report"?')
    expect(dlg).toHaveAccessibleDescription('This cannot be undone.')
  })

  it('resolves true only when the affirmative action is chosen', async () => {
    const onResult = vi.fn()
    await open(onResult)
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(onResult).toHaveBeenCalledWith(true))
  })

  it('resolves false on cancel', async () => {
    const onResult = vi.fn()
    await open(onResult)
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(onResult).toHaveBeenCalledWith(false))
  })

  it('treats Escape as no, never as yes', async () => {
    const onResult = vi.fn()
    await open(onResult)
    fireEvent.keyDown(window, { key: 'Escape' })
    await waitFor(() => expect(onResult).toHaveBeenCalledWith(false))
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
  })

  it('treats a backdrop click as no', async () => {
    const onResult = vi.fn()
    const dlg = await open(onResult)
    fireEvent.mouseDown(dlg.parentElement!)
    await waitFor(() => expect(onResult).toHaveBeenCalledWith(false))
  })

  it('does not cancel when the click starts inside the dialog', async () => {
    const onResult = vi.fn()
    const dlg = await open(onResult)
    fireEvent.mouseDown(dlg)
    expect(onResult).not.toHaveBeenCalled()
    expect(screen.getByRole('alertdialog')).toBeInTheDocument()
  })

  it('focuses the affirmative action so the dialog is operable by keyboard at once', async () => {
    await open()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Delete' })).toHaveFocus())
  })

  it('keeps Tab inside the dialog rather than letting focus escape to the page behind', async () => {
    await open()
    const del = screen.getByRole('button', { name: 'Delete' })
    const cancel = screen.getByRole('button', { name: 'Cancel' })

    fireEvent.keyDown(window, { key: 'Tab' })          // from Delete (last) wraps to Cancel
    expect(cancel).toHaveFocus()
    fireEvent.keyDown(window, { key: 'Tab', shiftKey: true })
    expect(del).toHaveFocus()
  })

  it('restores focus to whatever opened it, so a keyboard user keeps their place', async () => {
    const trigger = () => screen.getByRole('button', { name: 'Delete report' })
    render(<ConfirmProvider><Harness /></ConfirmProvider>)
    trigger().focus()
    fireEvent.click(trigger())
    await screen.findByRole('alertdialog')

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(trigger()).toHaveFocus())
  })

  it('lets a caller name the action, since "OK" does not say what will happen', async () => {
    function Custom() {
      const confirm = useConfirm()
      return <button onClick={() => confirm({ title: 'Discard changes?', confirmLabel: 'Discard', cancelLabel: 'Keep editing' })}>go</button>
    }
    render(<ConfirmProvider><Custom /></ConfirmProvider>)
    fireEvent.click(screen.getByRole('button', { name: 'go' }))
    expect(await screen.findByRole('button', { name: 'Discard' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Keep editing' })).toBeInTheDocument()
  })

  it('fails loudly when used outside its provider rather than silently never confirming', () => {
    const quiet = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => render(<Harness />)).toThrow(/ConfirmProvider/)
    quiet.mockRestore()
  })
})
