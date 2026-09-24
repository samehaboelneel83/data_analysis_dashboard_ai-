import { useEffect, useRef, useState, type ReactNode } from 'react'

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
  align = 'start', className,
}: Props) {
  const [open, setOpen] = useState(false)
  const [placement, setPlacement] = useState<{ top?: boolean; left?: boolean }>({})
  const [activeIndex, setActiveIndex] = useState(0)
  const rootRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([])

  const enabledIndices = items.reduce<number[]>((acc, it, i) => { if (!it.disabled) acc.push(i); return acc }, [])

  const close = (returnFocus: boolean) => {
    setOpen(false)
    if (returnFocus) triggerRef.current?.focus()
  }

  const doOpen = () => {
    setOpen(true)
    setActiveIndex(enabledIndices[0] ?? 0)
  }

  // Outside click closes without stealing focus back to the trigger.
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
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
    const overflowsBottom = tRect.bottom + mRect.height > window.innerHeight
    const overflowsRight = tRect.left + mRect.width > window.innerWidth
    setPlacement({ top: overflowsBottom, left: overflowsRight })
  }, [open])

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

  const activate = (item: ActionMenuItem) => {
    if (item.disabled) return
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

      {open && (
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
          style={{
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
              onClick={() => activate(item)}
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
      )}
    </div>
  )
}
