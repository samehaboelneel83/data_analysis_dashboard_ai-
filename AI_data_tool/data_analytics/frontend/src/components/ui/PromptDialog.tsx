import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { useModalDialog } from './useModalDialog'

export interface PromptOptions {
  /** Short question. Rendered as the dialog's accessible name. */
  title: string
  /** Optional detail line under the title. */
  body?: string
  /** Label for the text field. Defaults to the title, visually hidden. */
  label?: string
  /** Pre-filled value — the equivalent of window.prompt's second argument. */
  defaultValue?: string
  placeholder?: string
  /** Label for the affirmative button. Say the verb ("Rename"), not "OK". */
  confirmLabel?: string
  cancelLabel?: string
  /** When true (the default) the affirmative button stays disabled while the
   *  field is blank, so a caller never has to re-check for an empty string. */
  required?: boolean
}

type Resolver = (value: string | null) => void

const PromptContext = createContext<((opts: PromptOptions) => Promise<string | null>) | null>(null)

/**
 * Promise-based replacement for `window.prompt`, the sibling of `useConfirm`.
 *
 * The same three reasons apply. The native dialog blocks the JS thread, cannot be
 * themed, and browsers let a user tick "prevent this page from creating additional
 * dialogs" — after which `prompt()` returns null forever and every rename, every
 * new folder, silently does nothing with no way for the app to tell it was
 * suppressed. It is also invisible to the DOM: assistive technology, automated
 * tests and browser automation cannot see or drive it, so a rename typed into a
 * native prompt lands wherever the browser decides, not in the field.
 *
 * Usage mirrors the call it replaces:
 *
 *   const name = await prompt({ title: 'Rename folder', defaultValue: folder.name })
 *   if (name === null) return   // cancelled
 */
export function usePrompt() {
  const ctx = useContext(PromptContext)
  if (!ctx) throw new Error('usePrompt must be used inside a <PromptProvider>')
  return ctx
}

export function PromptProvider({ children }: { children: React.ReactNode }) {
  const [opts, setOpts] = useState<PromptOptions | null>(null)
  const [value, setValue] = useState('')
  const resolverRef = useRef<Resolver | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const prompt = useCallback((next: PromptOptions) => {
    setValue(next.defaultValue ?? '')
    setOpts(next)
    return new Promise<string | null>(resolve => { resolverRef.current = resolve })
  }, [])

  const settle = useCallback((result: string | null) => {
    setOpts(null)
    resolverRef.current?.(result)
    resolverRef.current = null
  }, [])

  // Escape, the focus trap and focus restoration come from the shared hook, so
  // this dialog cannot drift from the nine others that use it.
  const dialogRef = useModalDialog<HTMLFormElement>(() => settle(null))

  // The hook focuses the field; this selects what is already in it. That is the
  // behaviour a rename box needs: start typing and the old name is replaced,
  // without reaching for Ctrl+A -- which is exactly what a native prompt failed
  // to give us.
  useEffect(() => {
    if (opts) inputRef.current?.select()
  }, [opts])

  const trimmed = value.trim()
  const blocked = (opts?.required ?? true) && trimmed === ''

  return (
    <PromptContext.Provider value={prompt}>
      {children}
      {opts && (
        <div
          onMouseDown={e => { if (e.target === e.currentTarget) settle(null) }}
          style={{
            position: 'fixed', inset: 0, zIndex: 1000,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: 'rgba(0,0,0,.45)', padding: 16,
          }}
        >
          <form
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-label={opts.title}
            aria-describedby={opts.body ? 'prompt-dialog-body' : undefined}
            onSubmit={e => { e.preventDefault(); if (!blocked) settle(trimmed) }}
            style={{
              width: 'min(420px, 100%)', background: 'var(--surface)',
              border: '1px solid var(--border)', borderRadius: 'var(--radius)',
              boxShadow: '0 16px 48px rgba(0,0,0,.35)', padding: 18,
              color: 'var(--text)', font: 'inherit',
            }}
          >
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: opts.body ? 6 : 12 }}>
              {opts.title}
            </div>
            {opts.body && (
              <div id="prompt-dialog-body" style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 12, lineHeight: 1.5 }}>
                {opts.body}
              </div>
            )}
            <input
              ref={inputRef}
              value={value}
              onChange={e => setValue(e.target.value)}
              aria-label={opts.label ?? opts.title}
              placeholder={opts.placeholder}
              style={{
                width: '100%', boxSizing: 'border-box', padding: '8px 10px',
                fontSize: 13, fontFamily: 'inherit', color: 'var(--text)',
                background: 'var(--surface2)', border: '1px solid var(--border)',
                borderRadius: 6, marginBottom: 14,
              }}
            />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <button
                type="button"
                onClick={() => settle(null)}
                style={{
                  padding: '6px 12px', fontSize: 12, cursor: 'pointer',
                  background: 'var(--surface2)', color: 'var(--text)',
                  border: '1px solid var(--border)', borderRadius: 6,
                }}
              >
                {opts.cancelLabel ?? 'Cancel'}
              </button>
              <button
                type="submit"
                disabled={blocked}
                style={{
                  padding: '6px 12px', fontSize: 12, fontWeight: 600,
                  cursor: blocked ? 'not-allowed' : 'pointer', opacity: blocked ? .55 : 1,
                  background: 'var(--accent)', color: 'var(--mc-accent-fg)',
                  border: '1px solid transparent', borderRadius: 6,
                }}
              >
                {opts.confirmLabel ?? 'OK'}
              </button>
            </div>
          </form>
        </div>
      )}
    </PromptContext.Provider>
  )
}
