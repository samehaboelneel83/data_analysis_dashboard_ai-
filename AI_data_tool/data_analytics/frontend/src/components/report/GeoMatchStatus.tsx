import type { ReactNode } from 'react'

/** The status line under a region map's boundary picker. Kept apart from
 *  GeoMatchLine so the panel can show it as the lazy fallback without pulling
 *  in the world geometry that the match itself needs. */
export default function GeoMatchStatus({ danger = false, children }: { danger?: boolean; children: ReactNode }) {
  return (
    <div data-testid="geo-match-line" role="status"
      style={{ fontSize: 10.5, marginTop: 4, color: danger ? 'var(--danger)' : 'var(--muted)' }}>
      {children}
    </div>
  )
}
