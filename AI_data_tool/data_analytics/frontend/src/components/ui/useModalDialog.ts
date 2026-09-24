import { useEffect, useRef } from 'react'

/**
 * The keyboard mechanics every modal needs: Escape closes, Tab cycles inside,
 * and focus returns to whatever opened it.
 *
 * Extracted from `ConfirmDialog`, where these were proven, because nine other
 * dialogs shipped without them -- a keyboard user could enter any of those and
 * not get out, since Tab walks straight past the dialog into the page behind
 * it while the dialog still covers the screen.
 *
 * ONE DELIBERATE DIVERGENCE from the ConfirmDialog original. Its trap queries
 * `'button'`, which is correct there and only there: it has exactly two, both
 * buttons. A dialog containing inputs, selects or links needs the full
 * focusable set, so this uses the standard selector and filters out anything
 * disabled, hidden, or explicitly removed from the tab order.
 *
 * Usage:
 *
 *   const ref = useModalDialog<HTMLDivElement>(onClose)
 *   <div ref={ref} role="dialog" aria-modal="true" aria-label="…">
 *
 * The caller still supplies `role` and an accessible name: only the caller
 * knows whether it is a `dialog` or an `alertdialog`, and what to call it.
 */

/** Everything focusable by default, minus what cannot currently take focus. */
const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

export function useModalDialog<T extends HTMLElement>(
  onClose: () => void,
  options: { autoFocus?: boolean } = {},
) {
  const { autoFocus = true } = options
  const ref = useRef<T>(null)
  // Kept in a ref so a caller passing an inline arrow does not tear down and
  // re-add the key listener on every render.
  const closeRef = useRef(onClose)
  closeRef.current = onClose

  useEffect(() => {
    // Remember what had focus, so it can be restored on close; otherwise focus
    // falls back to <body> and a keyboard user loses their place in the page.
    const restore = document.activeElement

    if (autoFocus) {
      const first = ref.current?.querySelector<HTMLElement>(FOCUSABLE)
      // Falling back to the dialog itself keeps focus inside even when there is
      // nothing focusable in it yet -- a dialog still loading its content.
      ;(first ?? ref.current)?.focus()
    }

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        closeRef.current()
        return
      }
      if (e.key !== 'Tab') return

      // Hidden controls are excluded via `hidden`/`aria-hidden` rather than
      // `offsetParent`: that property is null for anything inside a
      // position:fixed ancestor -- which every one of these dialogs is -- and
      // jsdom returns null unconditionally, so it would empty the list.
      const list = Array.from(
        ref.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [],
      ).filter(el => !el.hasAttribute('hidden') &&
                     el.getAttribute('aria-hidden') !== 'true')
      if (list.length === 0) return

      const idx = list.indexOf(document.activeElement as HTMLElement)
      e.preventDefault()
      const next = e.shiftKey
        ? (idx <= 0 ? list.length - 1 : idx - 1)
        : (idx === list.length - 1 || idx === -1 ? 0 : idx + 1)
      list[next].focus()
    }

    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      if (restore instanceof HTMLElement) restore.focus()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return ref
}
