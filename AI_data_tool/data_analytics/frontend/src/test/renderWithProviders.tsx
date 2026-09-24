import { fireEvent, render, screen, within } from '@testing-library/react'
import type { ReactElement } from 'react'
import { ConfirmProvider } from '../components/ui/ConfirmDialog'
import { PromptProvider } from '../components/ui/PromptDialog'

/**
 * `render` with the app-level providers a component may reach for.
 *
 * `useConfirm` throws when there is no `<ConfirmProvider>` above it, and that
 * throw is correct -- a confirmation that silently no-ops is precisely the
 * failure mode `ConfirmDialog` exists to prevent, so the hook refuses to be
 * used unguarded rather than degrading.
 *
 * The consequence is that every test rendering a component which guards a
 * destructive action -- including one that only renders it transitively, as
 * Layout does through WorkspaceTree -- needs the provider. Wrapping each
 * `render` call by hand would put that knowledge in a few dozen places and
 * make the next migration fail the same way again, so it lives here once.
 *
 * `App.tsx` mounts the real `ConfirmProvider` around the whole tree, so this
 * mirrors production rather than inventing a test-only arrangement.
 */
export function renderWithProviders(ui: ReactElement, options?: Parameters<typeof render>[1]) {
  return render(
    <ConfirmProvider><PromptProvider>{ui}</PromptProvider></ConfirmProvider>,
    options,
  )
}

/**
 * Answer the in-app prompt dialog the way a person would: type into the field
 * and press the affirmative button, or press Cancel for `null`.
 *
 * This replaces `vi.spyOn(window, 'prompt')`. The native dialog could only ever
 * be faked; this drives the real control, so a test fails if the field stops
 * being reachable -- which is the bug that made us stop using `window.prompt`.
 *
 * Call it AFTER the action that opens the dialog, not before.
 */
export async function answerPrompt(value: string | null) {
  const dialog = await screen.findByRole('dialog')
  if (value === null) {
    fireEvent.click(within(dialog).getByRole('button', { name: /cancel/i }))
    return
  }
  fireEvent.change(within(dialog).getByRole('textbox'), { target: { value } })
  fireEvent.submit(dialog)
}

export * from '@testing-library/react'
