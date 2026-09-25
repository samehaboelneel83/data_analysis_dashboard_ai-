import { useState, type ReactNode } from 'react'
import type { ReportPage, Widget } from '../../types/report'
import { CrossFilterProvider } from './CrossFilterContext'
import { Z_MODAL_TOP } from '../../lib/zIndex'
import { useModalDialog } from '../ui/useModalDialog'
import IconLabel from '../ui/IconLabel'
import { FileDown } from 'lucide-react'

interface Props {
  page: ReportPage
  onClose: () => void
  /** ReportBuilder already owns all the per-widget wiring (dataset, parameters,
      display rules, drillthrough/navigate handlers, ...) -- rather than threading
      a dozen props through here a second time, it hands us a closure that renders
      one widget the same way the main canvas does. */
  renderWidget: (widget: Widget) => ReactNode
  /** Download just this pop-up page as a PDF (its own export). */
  onExport?: () => void
}

/** Sizes a reader can switch between; the choice sticks for this browser. */
const SIZES = { small: 'min(560px, 92vw)', medium: 'min(760px, 92vw)', large: 'min(1100px, 96vw)', full: '98vw' } as const
type Size = keyof typeof SIZES
const SIZE_KEY = 'datalytics:popup-size'
function initialSize(): Size {
  try { const v = localStorage.getItem(SIZE_KEY); return v && v in SIZES ? v as Size : 'medium' } catch { return 'medium' }
}

/**
 * View-mode popup page renderer (Power BI / SAS popup page): a centred modal
 * overlay showing one page's widgets ON TOP of whatever page is currently active,
 * rather than switching the active tab to it. Closing (Esc, backdrop click, or the
 * × button) returns to the underlying page exactly as it was -- it never touched.
 */
export default function PopupOverlay({ page, onClose, renderWidget, onExport }: Props) {
  const [size, setSizeState] = useState<Size>(initialSize)
  const setSize = (v: Size) => { setSizeState(v); try { localStorage.setItem(SIZE_KEY, v) } catch { /* private mode */ } }
  // Escape and focus-restore were hand-rolled here and correct; the TAB TRAP
  // was missing, so Tab walked out of the overlay into the page behind it
  // while the scrim still covered the screen. The shared hook supplies all
  // three, so the two local effects it replaces are gone rather than duplicated.
  const dialogRef = useModalDialog<HTMLDivElement>(onClose)

  return (
    <div
      role="presentation"
      data-testid="popup-overlay-backdrop"
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: Z_MODAL_TOP,
        background: 'rgba(0,0,0,.5)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 24,
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={page.name}
        data-testid="popup-overlay"
        onClick={e => e.stopPropagation()}
        style={{
          width: SIZES[size], maxHeight: size === 'full' ? '96vh' : '86vh', overflowY: 'auto',
          background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)',
          boxShadow: '0 24px 64px rgba(0,0,0,.4)', display: 'flex', flexDirection: 'column',
        }}
      >
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '10px 14px', borderBottom: '1px solid var(--border)', flexShrink: 0,
        }}>
          <span style={{ fontWeight: 600, fontSize: 13, flex: 1 }}>{page.title || page.name}</span>
          {/* Resize and export belong to the pop-up itself (SAS gives a pop-up
              page its own), so a reader can widen a dense table or keep it. */}
          <select aria-label="Pop-up size" value={size} onChange={e => setSize(e.target.value as Size)}
            style={{ fontSize: 11, marginInlineEnd: 6 }}>
            {(Object.keys(SIZES) as Size[]).map(k => <option key={k} value={k}>{k}</option>)}
          </select>
          {onExport && (
            <button type="button" className="btn btn-ghost btn-sm" onClick={onExport}
              title="Download this pop-up page as a PDF" style={{ fontSize: 11, marginInlineEnd: 6 }}>
              <IconLabel icon={FileDown}>PDF</IconLabel>
            </button>
          )}
          {/* No ref needed: the hook focuses the first focusable control,
              which is this button. */}
          <button aria-label="Close" onClick={onClose}
            style={{ border: 'none', background: 'none', cursor: 'pointer', fontSize: 18, lineHeight: 1, color: 'var(--muted)' }}>
            ×
          </button>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: 14 }}>
          <CrossFilterProvider pageMode={page.mobile_layout?.interaction_mode ?? 'manual'}>
            {page.widgets.length === 0 ? (
              <span style={{ fontSize: 12, color: 'var(--muted)' }}>This page has no widgets yet</span>
            ) : (
              page.widgets.map(w => (
                <div key={w.id} style={{ minHeight: 220 }}>
                  {renderWidget(w)}
                </div>
              ))
            )}
          </CrossFilterProvider>
        </div>
      </div>
    </div>
  )
}
