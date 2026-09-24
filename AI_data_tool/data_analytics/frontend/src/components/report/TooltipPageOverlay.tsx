import type { ReactNode } from 'react'
import type { ReportPage, Widget } from '../../types/report'
import { CrossFilterProvider } from './CrossFilterContext'
import { Z_MODAL_TOP } from '../../lib/zIndex'

interface Props {
  page: ReportPage
  /** Viewport coordinates (from the triggering mouse event) to float the panel near. */
  x: number
  y: number
  onDismiss: () => void
  /** Same delegation pattern as PopupOverlay -- ReportBuilder already owns all the
      per-widget wiring, so it hands us a closure that renders one widget the same
      way the main canvas does. */
  renderWidget: (widget: Widget) => ReactNode
}

/**
 * View-mode tooltip-page renderer (Power BI / SAS "report page tooltip" semantics):
 * hovering a widget bound to a tooltip page (via widget config's tooltipPageId)
 * floats that page's widgets in a small panel anchored near the cursor -- unlike
 * PopupOverlay, this is NOT modal: no backdrop, no focus trap, and it is dismissed
 * by the caller on mouseleave rather than owning its own close affordance.
 *
 * v1 is static: the tooltip page renders with no datapoint-filter carried over from
 * the hovered mark (e.g. hovering one bar does not filter the tooltip page to that
 * bar's category). Follow-up: thread the hovered datapoint through as a filter,
 * mirroring how drillthrough carries its source selection.
 */
export default function TooltipPageOverlay({ page, x, y, onDismiss, renderWidget }: Props) {
  return (
    <div
      role="tooltip"
      aria-label={page.name}
      data-testid="tooltip-page-overlay"
      onMouseLeave={onDismiss}
      style={{
        position: 'fixed',
        left: Math.min(x + 16, window.innerWidth - 320),
        top: Math.min(y + 16, window.innerHeight - 240),
        zIndex: Z_MODAL_TOP,
        width: 300, maxHeight: 260, overflowY: 'auto',
        background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)',
        boxShadow: '0 12px 32px rgba(0,0,0,.35)',
        pointerEvents: 'auto',
      }}
    >
      <div style={{
        padding: '6px 10px', borderBottom: '1px solid var(--border)',
        fontWeight: 600, fontSize: 12, color: 'var(--muted)',
      }}>
        {page.title || page.name}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: 10 }}>
        <CrossFilterProvider pageMode={page.mobile_layout?.interaction_mode ?? 'manual'}>
          {page.widgets.length === 0 ? (
            <span style={{ fontSize: 11, color: 'var(--muted)' }}>This page has no widgets yet</span>
          ) : (
            page.widgets.map(w => (
              <div key={w.id} style={{ minHeight: 100 }}>
                {renderWidget(w)}
              </div>
            ))
          )}
        </CrossFilterProvider>
      </div>
    </div>
  )
}
