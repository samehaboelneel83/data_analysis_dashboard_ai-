import { useCallback, useRef, useState } from 'react'
import { useCrossFilter } from './CrossFilterContext'

/**
 * What is filtering this page, reachable from anywhere on it.
 *
 * `FilterBar` sits at the top of the canvas, which works until the page is
 * taller than the screen: scroll down and the one place that says what is
 * filtering — and the only way to clear a filter without hunting for the widget
 * that set it — has scrolled away. On a dashboard of twenty tiles that is most
 * of the time, and the reader is left looking at numbers narrowed by something
 * they can no longer see.
 *
 * Three decisions worth stating:
 *
 *   **Pinned to the VIEWPORT, not the document.** `position: fixed` is the
 *   entire feature; `absolute` would scroll away exactly as the strip does.
 *
 *   **Present only while something is filtering.** A permanent floating box on
 *   an unfiltered page is clutter, and clutter teaches a reader to stop seeing
 *   it — including on the day it matters.
 *
 *   **Draggable, because it is covering something.** It sits over the canvas by
 *   definition, so it has to be movable off whatever it lands on. Collapsing it
 *   does NOT clear the filters: they are still narrowing every number on the
 *   page, and a dismissed window that silently meant "unfiltered" would be a
 *   worse lie than no window.
 */
export default function FloatingFilterWindow() {
  const { activeFilters, clearFilter, clearAllFilters } = useCrossFilter()
  const [open, setOpen] = useState(false)
  //: Offset from the default corner, in pixels. Session-only on purpose: a
  //: remembered position is a setting nobody asked to set.
  const [offset, setOffset] = useState({ x: 0, y: 0 })
  const drag = useRef<{ x: number; y: number; ox: number; oy: number } | null>(null)

  // Mouse events rather than pointer events: jsdom implements MouseEvent fully
  // and PointerEvent barely, so a pointer-based drag is untestable here — and an
  // untested drag is one that silently stops working.
  const onPointerDown = useCallback((e: React.MouseEvent) => {
    drag.current = { x: e.clientX, y: e.clientY, ox: offset.x, oy: offset.y }
    const move = (ev: MouseEvent) => {
      const d = drag.current
      if (!d) return
      // Right/bottom anchored, so dragging left and up INCREASES the offsets.
      setOffset({ x: d.ox + (d.x - ev.clientX), y: d.oy + (d.y - ev.clientY) })
    }
    const up = () => {
      drag.current = null
      window.removeEventListener('mousemove', move)
      window.removeEventListener('mouseup', up)
    }
    window.addEventListener('mousemove', move)
    window.addEventListener('mouseup', up)
  }, [offset])

  if (activeFilters.length === 0) return null

  const count = activeFilters.length
  const label = `${count} filter${count === 1 ? '' : 's'}`

  return (
    <div data-testid="floating-filters" style={{
      position: 'fixed',
      right: 18 + offset.x, bottom: 18 + offset.y,
      zIndex: 60, maxWidth: 320,
      background: 'var(--surface)', border: '1px solid var(--accent)',
      borderRadius: 10, boxShadow: '0 8px 28px rgba(0,0,0,.28)',
    }}>
      {!open ? (
        <button onClick={() => setOpen(true)}
          style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '7px 12px',
            background: 'none', border: 'none', cursor: 'pointer', fontSize: 12,
            color: 'var(--accent)', fontWeight: 600 }}>
          <span aria-hidden>⌗</span> {label}
        </button>
      ) : (
        <div style={{ minWidth: 230 }}>
          <div data-testid="floating-filters-grip" onMouseDown={onPointerDown}
            style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'move',
              padding: '6px 8px 6px 10px', borderBottom: '1px solid var(--border)' }}>
            <strong style={{ fontSize: 11, flex: 1 }}>{label}</strong>
            <button onClick={clearAllFilters} className="btn btn-ghost btn-sm"
              style={{ fontSize: 11, padding: '2px 6px' }}>Clear all</button>
            <button onClick={() => setOpen(false)} aria-label="Collapse filters" title="Collapse"
              style={{ background: 'none', border: 'none', cursor: 'pointer',
                color: 'var(--muted)', fontSize: 13, lineHeight: 1 }}>–</button>
          </div>
          <ul style={{ listStyle: 'none', margin: 0, padding: 6,
            display: 'flex', flexDirection: 'column', gap: 4, maxHeight: 220, overflowY: 'auto' }}>
            {activeFilters.map(f => (
              <li key={`${f.sourceWidgetId}-${f.column}`}
                style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11 }}>
                <span style={{ flex: 1, color: 'var(--accent)' }}>{f.label}</span>
                {/* Named, not a bare ×: this is one of the two places a filter
                    can be removed without finding the widget that set it, and a
                    column of unlabelled buttons is unusable by keyboard. */}
                <button onClick={() => clearFilter(f.column, f.sourceWidgetId)}
                  aria-label={`Remove filter ${f.label}`} title={`Remove filter ${f.label}`}
                  style={{ background: 'none', border: 'none', color: 'var(--muted)',
                    cursor: 'pointer', fontSize: 13, lineHeight: 1, padding: 0 }}>×</button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
