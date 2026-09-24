import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

/**
 * "There is nothing here yet" — distinct from LoadError's "we could not ask".
 *
 * Every page that got this right (Dashboard, Reports, Connections) converged on
 * the same shape by hand: a card, a muted icon, a bold one-line title, an
 * optional explanation, and — when there is a next action worth naming — a
 * primary button for it. This codifies that shape once instead of leaving the
 * next page to reinvent it slightly differently, which is how Connections ended
 * up with `<div>` text where Dashboard used `<p>`, and no two pages agreed on a
 * font size.
 */
export default function EmptyState({ icon: Icon, title, description, action }: {
  icon: LucideIcon
  title: string
  description?: string
  action?: ReactNode
}) {
  return (
    <div className="card" style={{ textAlign: 'center', padding: '56px 24px' }}>
      <Icon size={40} color="var(--muted)" style={{ margin: '0 auto 16px' }} />
      <p style={{ fontWeight: 600, marginBottom: description || action ? 8 : 0 }}>{title}</p>
      {description && (
        <p style={{ color: 'var(--muted)', fontSize: 13, marginBottom: action ? 20 : 0 }}>
          {description}
        </p>
      )}
      {action && (
        <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
          {action}
        </div>
      )}
    </div>
  )
}
