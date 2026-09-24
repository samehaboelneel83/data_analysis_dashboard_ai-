import type { LucideIcon } from 'lucide-react'

/**
 * An icon beside a label, for buttons and menu items.
 *
 * Exists because the app's chrome used emoji for this everywhere ("📊 Report",
 * "🤖 Ask"), which renders as a different colourful picture on every OS and
 * reads as a toy beside enterprise chrome. One Lucide glyph, one stroke
 * weight, `currentColor` -- so a button's active state tints mark and word
 * together instead of leaving a coloured emoji stranded on a blue background.
 *
 * The TEXT is a plain child, never baked into the icon: screen readers and
 * `getByRole('button', { name })` both read the word, and the mark is
 * `aria-hidden` decoration. That is what let the emoji-to-Lucide conversion
 * land without rewriting the assertions in a 54k-line test file.
 */
export default function IconLabel({ icon: Icon, children, size = 13 }: {
  icon: LucideIcon
  children?: React.ReactNode
  size?: number
}) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
      <span aria-hidden style={{ display: 'inline-flex', flexShrink: 0 }}>
        <Icon size={size} strokeWidth={1.9} />
      </span>
      {children}
    </span>
  )
}
