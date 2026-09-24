/**
 * A toolbar button that opens a short menu -- how the builder header groups
 * related actions (Share ▾, Export ▾) instead of laying seven buttons in a row
 * that wrapped onto a second line on an ordinary laptop screen.
 *
 * Closes on outside click, on Escape, and after an item runs. Items are real
 * menuitems, so the keyboard and a screen reader get the same menu the mouse does.
 */
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { ChevronDown } from 'lucide-react'

export interface ToolbarMenuItem {
  key: string
  label: ReactNode
  title?: string
  onSelect: () => void
  /** Shown but not actionable; `title` then says why (aria-disabled keeps the
   *  tooltip -- "why can't I" must always have an answer). */
  disabled?: boolean
}

export default function ToolbarMenu({ label, title, items }: { label: ReactNode; title?: string; items: ToolbarMenuItem[] }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false) }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey) }
  }, [open])
  if (items.length === 0) return null
  return (
    <div ref={ref} style={{ position: 'relative', display: 'inline-flex' }}>
      <button type="button" className="btn btn-ghost btn-sm" title={title} aria-haspopup="menu" aria-expanded={open}
        onClick={() => setOpen(o => !o)}>
        {label} <ChevronDown size={12} style={{ marginInlineStart: 2 }} />
      </button>
      {open && (
        <div role="menu" style={{ position: 'absolute', top: '100%', insetInlineStart: 0, marginTop: 4, zIndex: 50, minWidth: 190,
          background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 6, boxShadow: '0 8px 24px rgba(0,0,0,.2)', padding: 4 }}>
          {items.map(it => (
            <button key={it.key} type="button" role="menuitem" title={it.title}
              aria-disabled={it.disabled || undefined}
              onClick={() => { if (it.disabled) return; setOpen(false); it.onSelect() }}
              style={{ display: 'flex', alignItems: 'center', gap: 8, width: '100%', textAlign: 'start', padding: '6px 10px',
                background: 'none', border: 'none', borderRadius: 4, cursor: it.disabled ? 'not-allowed' : 'pointer',
                color: it.disabled ? 'var(--muted)' : 'var(--text)', opacity: it.disabled ? 0.6 : 1, font: 'inherit', fontSize: 13 }}
              onMouseEnter={e => { e.currentTarget.style.background = 'var(--surface2)' }}
              onMouseLeave={e => { e.currentTarget.style.background = 'none' }}>
              {it.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
