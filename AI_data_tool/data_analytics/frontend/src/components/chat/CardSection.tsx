import { useId, type ReactNode } from 'react'
import { ChevronDown, type LucideIcon } from 'lucide-react'
import { localDigits } from '../../lib/arabicFormats'

/** A collapsible band of an answer card (step 10: "Rows behind this answer",
 *  "Show SQL"): a full-width button with an icon, a label, an optional count
 *  and a chevron, and what it opens underneath. */
export default function CardSection({ icon: Icon, label, count, open, onToggle, children }: {
  icon: LucideIcon
  label: string
  count?: number
  open: boolean
  onToggle: () => void
  children: ReactNode
}) {
  const id = useId()
  return (
    <div className={`dl-sect${open ? ' dl-sect--open' : ''}`}>
      <button type="button" className="dl-sect__btn" aria-expanded={open} aria-controls={id} onClick={onToggle}>
        <Icon size={16} aria-hidden />
        {label}
        {count != null && <span className="dl-sect__n" dir="ltr">{localDigits(String(count))}</span>}
        <ChevronDown size={16} aria-hidden className="dl-sect__chev" />
      </button>
      {open && <div id={id} className="dl-sect__body">{children}</div>}
    </div>
  )
}
