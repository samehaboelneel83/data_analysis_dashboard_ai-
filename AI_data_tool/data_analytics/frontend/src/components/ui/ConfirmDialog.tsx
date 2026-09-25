import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'

export interface ConfirmOptions {
  /** Short question. Rendered as the dialog's accessible name. */
  title: string
  /** Optional detail line: what exactly happens, and whether it can be undone. */
  body?: string
  /** Label for the affirmative button. Say the verb ("Delete"), not "OK". */
  confirmLabel?: string
  cancelLabel?: string
  /** Styles the affirmative button as destructive and is the default, since every
   *  current caller is a delete. Pass false for a benign confirmation. */
  destructive?: boolean
}

type Resolver = (ok: boolean) => void

const ConfirmContext = createContext<((opts: ConfirmOptions) => Promise<boolean>) | null>(null)

/**
 * Promise-based replacement for `window.confirm`.
 *
 * The native dialog blocks the JS thread, cannot be themed, and -- the reason this
 * exists -- browsers let a user tick "prevent this page from creating additional
 * dialogs", after which `confirm()` returns false forever. Every guarded action then
 * silently does nothing, with no way for the app to tell that it was suppressed.
 *
 * Usage mirrors the call it replaces, so migrating a site is a one-line change:
 *
 *   if (!(await confirm({ title: `Delete "${name}"?` }))) return
 */
export function useConfirm() {
  const ctx = useContext(ConfirmContext)
  if (!ctx) throw new Error('useConfirm must be used inside a <ConfirmProvider>')
  return ctx
}

export function ConfirmProvider({ children }: { children: React.ReactNode }) {
  const [opts, setOpts] = useState<ConfirmOptions | null>(null)
  const resolverRef = useRef<Resolver | null>(null)
  const confirmBtnRef = useRef<HTMLButtonElement>(null)
  const restoreFocusRef = useRef<Element | null>(null)

  const confirm = useCallback((next: ConfirmOptions) => {
    // Remember what had focus so it can be restored on close; otherwise focus falls
    // back to <body> and a keyboard user loses their place in the page.
    restoreFocusRef.current = document.activeElement
    setOpts(next)
    return new Promise<boolean>(resolve => { resolverRef.current = resolve })
  }, [])

  const settle = useCallback((ok: boolean) => {
    setOpts(null)
    resolverRef.current?.(ok)
    resolverRef.current = null
    const restore = restoreFocusRef.current
    if (restore instanceof HTMLElement) restore.focus()
  }, [])

  // Focus the affirmative action on open so the dialog is immediately operable by
  // keyboard, and so the focus ring announces which button Enter will press.
  useEffect(() => {
    if (opts) confirmBtnRef.current?.focus()
  }, [opts])

  useEffect(() => {
    if (!opts) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.preventDefault(); settle(false) }
      if (e.key === 'Tab') {
        // Two focusable controls, so a manual trap is cheaper and more predictable
        // than a generic one: Tab cycles between them and never escapes the dialog.
        const nodes = dialogRef.current?.querySelectorAll<HTMLElement>('button')
        if (!nodes || nodes.length === 0) return
        const list = Array.from(nodes)
        const idx = list.indexOf(document.activeElement as HTMLElement)
        e.preventDefault()
        const nextIdx = e.shiftKey
          ? (idx <= 0 ? list.length - 1 : idx - 1)
          : (idx === list.length - 1 ? 0 : idx + 1)
        list[nextIdx].focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [opts, settle])

  const dialogRef = useRef<HTMLDivElement>(null)

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {opts && (
        <div
          // Cancelling from the backdrop matches the Escape key: the safe answer is
          // always "no" for an action the author has not yet agreed to.
          onMouseDown={e => { if (e.target === e.currentTarget) settle(false) }}
          style={{
            position: 'fixed', inset: 0, zIndex: 1000,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: 'rgba(0,0,0,.45)', padding: 16,
          }}
        >
          <div
            ref={dialogRef}
            role="alertdialog"
            aria-modal="true"
            aria-label={opts.title}
            aria-describedby={opts.body ? 'confirm-dialog-body' : undefined}
            style={{
              width: 'min(420px, 100%)', background: 'var(--surface)',
              border: '1px solid var(--border)', borderRadius: 'var(--radius)',
              boxShadow: '0 16px 48px rgba(0,0,0,.35)', padding: 18,
              color: 'var(--text)', font: 'inherit',
            }}
          >
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: opts.body ? 6 : 14 }}>
              {opts.title}
            </div>
            {opts.body && (
              <div id="confirm-dialog-body" style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 14, lineHeight: 1.5, whiteSpace: 'pre-line', maxHeight: 240, overflowY: 'auto' }}>
                {opts.body}
              </div>
            )}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <button
                type="button"
                onClick={() => settle(false)}
                style={{
                  padding: '6px 12px', fontSize: 12, cursor: 'pointer',
                  background: 'var(--surface2)', color: 'var(--text)',
                  border: '1px solid var(--border)', borderRadius: 6,
                }}
              >
                {opts.cancelLabel ?? 'Cancel'}
              </button>
              <button
                ref={confirmBtnRef}
                type="button"
                onClick={() => settle(true)}
                style={{
                  padding: '6px 12px', fontSize: 12, cursor: 'pointer', fontWeight: 600,
                  background: opts.destructive === false ? 'var(--accent)' : 'var(--danger, #dc2626)',
                  color: opts.destructive === false ? 'var(--mc-accent-fg, #fff)' : 'var(--mc-danger-fg, #fff)', border: '1px solid transparent', borderRadius: 6,
                }}
              >
                {opts.confirmLabel ?? 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  )
}
