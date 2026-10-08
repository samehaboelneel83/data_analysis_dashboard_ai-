import { useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode, type RefObject } from 'react'
import { createPortal } from 'react-dom'

/**
 * QA5 F2: a small menu that opens from a button and is never cut off.
 *
 * Rendered in a portal on <body> (a panel that scrolls or clips can no longer
 * hide it) with fixed coordinates taken from its button: under it, or above
 * when there is no room below; aligned to the button's start edge (the right
 * edge in Arabic), then shifted to stay 8px inside the window.
 */
const GAP = 4
const MARGIN = 8

export default function AnchoredMenu({ anchorRef, children, style, rtl, ...rest }: {
  anchorRef: RefObject<HTMLElement | null>
  children: ReactNode
  style?: CSSProperties
  rtl?: boolean
} & Record<`data-${string}`, string | undefined>) {
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null)

  useLayoutEffect(() => {
    const place = () => {
      const a = anchorRef.current?.getBoundingClientRect(), m = ref.current
      if (!a || !m) return
      const w = m.offsetWidth, h = m.offsetHeight
      const vw = window.innerWidth, vh = window.innerHeight
      let top = a.bottom + GAP
      if (top + h > vh - MARGIN && a.top - GAP - h >= MARGIN) top = a.top - GAP - h
      top = Math.max(MARGIN, Math.min(top, vh - MARGIN - h))
      let left = rtl ? a.right - w : a.left
      left = Math.max(MARGIN, Math.min(left, vw - MARGIN - w))
      setPos({ left, top })
    }
    place()
    window.addEventListener('resize', place)
    window.addEventListener('scroll', place, true)
    return () => { window.removeEventListener('resize', place); window.removeEventListener('scroll', place, true) }
  }, [anchorRef, rtl])

  return createPortal(
    <div ref={ref} role="menu" {...rest}
      style={{ position: 'fixed', zIndex: 1100, left: pos?.left ?? -9999, top: pos?.top ?? -9999,
        maxHeight: `calc(100vh - ${2 * MARGIN}px)`, overflowY: 'auto', ...style }}>
      {children}
    </div>,
    document.body)
}
