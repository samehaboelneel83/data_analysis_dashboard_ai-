import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Check, ChevronDown } from 'lucide-react'

/**
 * A toolbar filter (Lineage, step 11): a chip that opens a short menu of
 * options, each one checkable. `multi` keeps the menu open and toggles; a
 * single choice picks one (picking it again clears it) and closes. Arrow
 * keys move, Enter / Space choose, Escape closes and returns to the chip.
 */
export interface ChipOption { value: string; label: string; checked: boolean }

export default function FilterChip({ icon, label, active, options, onPick, multi = false }: {
  icon: ReactNode
  label: string
  active: boolean
  options: ChipOption[]
  onPick: (value: string) => void
  multi?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [at, setAt] = useState(0)
  const root = useRef<HTMLDivElement>(null)
  const chip = useRef<HTMLButtonElement>(null)
  const items = useRef<(HTMLButtonElement | null)[]>([])

  useEffect(() => {
    if (!open) return
    items.current[at]?.focus()
  }, [open, at])
  useEffect(() => {
    if (!open) return
    const away = (e: MouseEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', away)
    return () => document.removeEventListener('mousedown', away)
  }, [open])

  const close = () => { setOpen(false); chip.current?.focus() }
  const pick = (v: string) => { onPick(v); if (!multi) close() }

  return (
    <div className="dl-ln-cw" ref={root}>
      <button ref={chip} type="button" className={`dl-ln-chip${active ? ' is-on' : ''}`} aria-haspopup="menu" aria-expanded={open}
        onClick={() => { setAt(0); setOpen(o => !o) }}
        onKeyDown={e => { if (e.key === 'ArrowDown') { e.preventDefault(); setAt(0); setOpen(true) } }}>
        {icon}<span>{label}</span><ChevronDown size={14} aria-hidden />
      </button>
      {open && (
        <div className="dl-ln-pop" role="menu" aria-label={label}
          onKeyDown={e => {
            if (e.key === 'Escape') { e.preventDefault(); close() }
            else if (e.key === 'ArrowDown') { e.preventDefault(); setAt(a => (a + 1) % options.length) }
            else if (e.key === 'ArrowUp') { e.preventDefault(); setAt(a => (a - 1 + options.length) % options.length) }
            else if (e.key === 'Tab') setOpen(false)
          }}>
          {options.map((o, i) => (
            <button key={o.value} ref={el => { items.current[i] = el }} type="button" tabIndex={-1}
              role={multi ? 'menuitemcheckbox' : 'menuitemradio'} aria-checked={o.checked}
              className="dl-ln-opt" onClick={() => pick(o.value)}>
              <span>{o.label}</span>{o.checked && <Check size={14} aria-hidden />}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
