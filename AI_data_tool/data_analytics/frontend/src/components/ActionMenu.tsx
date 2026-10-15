import { useEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

export interface ActionMenuItem {
  key: string
  label: string
  icon?: ReactNode
  onSelect: () => void
  danger?: boolean
  disabled?: boolean
  /** Why it is disabled -- shown as its tooltip. A disabled item with no reason
   *  is a dead end (constitution rule 1). */
  disabledReason?: string
}

interface Props {
  items: ActionMenuItem[]
  /** Accessible name for the trigger button — should identify the row/object it acts on. */
  label: string
  /** Optional custom trigger content; defaults to the "⋯" glyph. */
  trigger?: ReactNode
  /** Trigger classes. Defaults to the ghost button every card and table row
   *  uses; pass '' to style the trigger entirely through `triggerStyle`, as
   *  the dense nav rail does. */
  triggerClassName?: string
  triggerStyle?: React.CSSProperties
  /** Which edge of the trigger the popup hangs from.
   *
   *  'start' (default) keeps the historical behaviour: hang from the leading
   *  edge, flipping only when the VIEWPORT would clip it. That flip cannot
   *  save a menu inside a narrow `overflow-x: hidden` container — the nav
   *  rail — where there is viewport to spare but no room in the box. 'end'
   *  hangs from the trailing edge so the popup opens inward, and does it with
   *  a LOGICAL inset so it mirrors under RTL instead of escaping the rail. */
  align?: 'start' | 'end'
  className?: string
  /** Render the popup on document.body at fixed coordinates (5.10): a menu
   *  inside a narrow chart tile with `overflow: hidden` was clipped to the
   *  tile, its lower items unreachable. */
  portal?: boolean
}

/**
 * A "⋯" trigger that opens a popup of labelled actions — the alternative to a
 * cluster of bare icon buttons. Existing icon buttons stay; this menu calls
 * the exact same handlers, so there is nothing new to keep in sync.
 *
 * Positioning is a simple viewport bounding check (flip above/left near an
 * edge) rather than a floating-UI dependency, per the "no new library" rule
 * the rest of this codebase follows for interactive chrome.
 */
export default function ActionMenu({
  items, label, trigger, triggerClassName = 'btn btn-ghost btn-sm', triggerStyle,
  align = 'start', className, portal = false,
}: Props) {
  const [open, setOpen] = useState(false)
  const [placement, setPlacement] = useState<{ top?: boolean; left?: boolean; maxH?: number }>({})
  // F-16: when it opened and where its trigger was -- see `activate`.
  const openedRef = useRef<{ at: number; rect: DOMRect | null }>({ at: 0, rect: null })
  const [fixedAt, setFixedAt] = useState<{ top: number; left: number } | null>(null)
  const [activeIndex, setActiveIndex] = useState(0)
  const rootRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([])

  const enabledIndices = items.reduce<number[]>((acc, it, i) => { if (!it.disabled) acc.push(i); return acc }, [])

  const close = (returnFocus: boolean) => {
    setOpen(false)
    setFixedAt(null)
    if (returnFocus) triggerRef.current?.focus()
  }

  const doOpen = () => {
    openedRef.current = { at: Date.now(), rect: triggerRef.current?.getBoundingClientRect() ?? null }
    setOpen(true)
    setActiveIndex(enabledIndices[0] ?? 0)
  }

  // Outside click closes without stealing focus back to the trigger.
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node
      if (!rootRef.current?.contains(t) && !menuRef.current?.contains(t)) setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  // Position: flip above/left when the natural placement would overflow the viewport.
  useEffect(() => {
    if (!open) return
    const trigger = triggerRef.current
    const menu = menuRef.current
    if (!trigger || !menu) return
    const tRect = trigger.getBoundingClientRect()
    const mRect = menu.getBoundingClientRect()
    // The menu sits 4px below the trigger: count that gap and a little air,
    // or a menu on the last row "fits" and is then cut by the window edge.
    const overflowsBottom = tRect.bottom + 4 + mRect.height + 4 > window.innerHeight
    const overflowsRight = tRect.left + mRect.width > window.innerWidth
    // F-16: flip above only when it FITS above. Clamped to the top of a short
    // window it used to cover its own trigger, and the second press of a
    // double-click landed on whatever item was there (a widget duplicated by
    // accident). With room on neither side it opens below and scrolls.
    const above = overflowsBottom && tRect.top - 4 - mRect.height - 4 >= 0
    const maxH = overflowsBottom && !above ? Math.max(80, window.innerHeight - (tRect.bottom + 4) - 4) : undefined
    setPlacement({ top: above, left: overflowsRight, maxH })
    if (portal) {
      const top = above ? tRect.top - mRect.height - 4 : tRect.bottom + 4
      const left = overflowsRight || align === 'end'
        ? Math.max(4, tRect.right - mRect.width) : tRect.left
      setFixedAt({ top, left })
    }
  }, [open, portal])
  // A portalled menu is fixed to the window, so a scroll under it would leave
  // it floating away from its button. It follows the button instead, and
  // closes only once the button has left the window. (Closing on any scroll
  // shut the menu as soon as it opened while a smooth scroll was still
  // settling: the Ask AI card's Export menu, autopilot step 3.)
  useEffect(() => {
    if (!open || !portal) return
    let last = triggerRef.current?.getBoundingClientRect()
    const onScroll = () => {
      const tr = triggerRef.current
      if (!tr || !last) return
      const r = tr.getBoundingClientRect()
      if (r.bottom < 0 || r.top > window.innerHeight || r.right < 0 || r.left > window.innerWidth) { setOpen(false); return }
      const dx = r.left - last.left, dy = r.top - last.top
      last = r
      if (dx || dy) setFixedAt(prev => (prev ? { top: prev.top + dy, left: prev.left + dx } : prev))
    }
    window.addEventListener('scroll', onScroll, true)
    return () => window.removeEventListener('scroll', onScroll, true)
  }, [open, portal, align])

  // Focus the active item as arrow navigation moves it.
  useEffect(() => {
    if (!open) return
    itemRefs.current[activeIndex]?.focus()
  }, [open, activeIndex])

  const moveTo = (dir: 1 | -1) => {
    if (enabledIndices.length === 0) return
    const pos = enabledIndices.indexOf(activeIndex)
    const nextPos = pos === -1
      ? 0
      : (pos + dir + enabledIndices.length) % enabledIndices.length
    setActiveIndex(enabledIndices[nextPos])
  }

  const activate = (item: ActionMenuItem, at?: { x: number; y: number }) => {
    if (item.disabled) return
    // F-16: a click landing where the trigger was, moments after it opened
    // the menu, is the trigger's double-click -- not a choice of this item.
    const o = openedRef.current
    if (at && o.rect && o.rect.width > 0 && o.rect.height > 0 && Date.now() - o.at < 400
        && at.x >= o.rect.left && at.x <= o.rect.right && at.y >= o.rect.top && at.y <= o.rect.bottom) return
    close(true)
    item.onSelect()
  }

  return (
    <div ref={rootRef} className={className} style={{ position: 'relative', display: 'inline-block' }}>
      <button
        ref={triggerRef}
        type="button"
        className={triggerClassName}
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        title={label}
        onClick={() => (open ? close(false) : doOpen())}
        style={{ lineHeight: 1, ...triggerStyle }}
      >
        {trigger ?? '⋯'}
      </button>

      {open && (() => {
        const menu = (
        <div
          ref={menuRef}
          role="menu"
          aria-label={label}
          onKeyDown={e => {
            if (e.key === 'Escape') { e.preventDefault(); close(true) }
            else if (e.key === 'ArrowDown') { e.preventDefault(); moveTo(1) }
            else if (e.key === 'ArrowUp') { e.preventDefault(); moveTo(-1) }
            else if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault()
              const item = items[activeIndex]
              if (item) activate(item)
            }
          }}
          style={portal ? {
            position: 'fixed', top: fixedAt?.top ?? -9999, left: fixedAt?.left ?? -9999,
            visibility: fixedAt ? 'visible' : 'hidden',
            minWidth: 160, background: 'var(--surface)', border: '1px solid var(--border)',
            borderRadius: 8, boxShadow: '0 8px 28px rgba(0,0,0,.25)', zIndex: 1200, padding: 4,
            ...(placement.maxH ? { maxHeight: placement.maxH, overflowY: 'auto' as const } : {}),
          } : {
            position: 'absolute',
            top: placement.top ? 'auto' : '100%',
            bottom: placement.top ? '100%' : 'auto',
            ...(align === 'end'
              ? { insetInlineEnd: 0, insetInlineStart: 'auto' }
              : { right: placement.left ? 0 : 'auto', left: placement.left ? 'auto' : 0 }),
            marginTop: placement.top ? 0 : 4,
            marginBottom: placement.top ? 4 : 0,
            minWidth: 160,
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: 8,
            boxShadow: '0 8px 28px rgba(0,0,0,.25)',
            zIndex: 950,
            padding: 4,
            ...(placement.maxH ? { maxHeight: placement.maxH, overflowY: 'auto' as const } : {}),
          }}
        >
          {items.map((item, i) => (
            <button
              key={item.key}
              ref={el => { itemRefs.current[i] = el }}
              role="menuitem"
              type="button"
              tabIndex={-1}
              disabled={item.disabled}
              aria-disabled={item.disabled || undefined}
              title={item.disabled ? item.disabledReason : undefined}
              onClick={e => activate(item, e.detail > 0 ? { x: e.clientX, y: e.clientY } : undefined)}
              onMouseEnter={() => { if (!item.disabled) setActiveIndex(i) }}
              style={{
                display: 'flex', alignItems: 'center', gap: 8, width: '100%', textAlign: 'start',
                background: activeIndex === i && !item.disabled ? 'color-mix(in srgb, var(--accent) 12%, transparent)' : 'transparent',
                border: 'none', borderRadius: 6, padding: '7px 10px', fontSize: 12.5,
                color: item.disabled ? 'var(--muted)' : item.danger ? 'var(--danger)' : 'var(--text)',
                cursor: item.disabled ? 'not-allowed' : 'pointer',
                opacity: item.disabled ? 0.55 : 1,
              }}
            >
              {item.icon && <span aria-hidden style={{ display: 'flex', flexShrink: 0 }}>{item.icon}</span>}
              <span>{item.label}</span>
            </button>
          ))}
        </div>
        )
        return portal && typeof document !== 'undefined' ? createPortal(menu, document.body) : menu
      })()}
    </div>
  )
}
