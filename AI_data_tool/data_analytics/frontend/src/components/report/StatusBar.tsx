import { Keyboard } from 'lucide-react'
import { useT } from '../../i18n'
const ZOOM_MIN = 50
const ZOOM_MAX = 150
const ZOOM_STEP = 10

/**
 * The strip under the dashboard. Reading: page position, zoom and save state,
 * as v1. Building (redesign 7e1): "Page 1 of 3 · 12 widgets · 1 selected" and
 * the shortcuts sheet -- zoom moved to the toolbar and the save state to the
 * header, so the builder passes neither.
 */
export default function StatusBar({ pageIndex, pageCount, saveState, zoom, onZoomChange, widgets, selected, onShortcuts }: {
  pageIndex: number
  pageCount: number
  saveState?: 'saved' | 'saving'
  zoom?: number
  onZoomChange?: (zoom: number) => void
  /** Building: widgets on the open page, and how many are selected. */
  widgets?: number
  selected?: number
  onShortcuts?: () => void
}) {
  const tr = useT()
  const clamp = (z: number) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, z))
  const parts = [tr('status.page', { n: pageIndex + 1, total: pageCount })]
  if (widgets != null) parts.push(tr(widgets === 1 ? 'bd.st.widget' : 'bd.st.widgets', { n: widgets }))
  if (selected) parts.push(tr('bd.st.selected', { n: selected }))

  return (
    <div className="dl-statusbar" style={{
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      padding: '4px 12px', borderTop: '1px solid var(--border)', background: 'var(--surface)',
      fontSize: 11, color: 'var(--muted)', flexShrink: 0,
    }}>
      <span>{parts.join(' · ')}</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        {zoom !== undefined && onZoomChange && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <button onClick={() => onZoomChange(clamp(zoom - ZOOM_STEP))}
              style={{ background: 'none', border: '1px solid var(--border)', borderRadius: 4, cursor: 'pointer', color: 'var(--muted)', fontSize: 11, lineHeight: 1, padding: '2px 6px' }}>
              −
            </button>
            <span style={{ fontFamily: 'var(--mono)', minWidth: 34, textAlign: 'center' }}>{zoom}%</span>
            <button onClick={() => onZoomChange(clamp(zoom + ZOOM_STEP))}
              style={{ background: 'none', border: '1px solid var(--border)', borderRadius: 4, cursor: 'pointer', color: 'var(--muted)', fontSize: 11, lineHeight: 1, padding: '2px 6px' }}>
              +
            </button>
          </div>
        )}
        {saveState && <span>{saveState === 'saving' ? tr('status.saving') : tr('status.saved')}</span>}
        {onShortcuts && (
          <button type="button" className="dl-statusbar__keys" onClick={onShortcuts} aria-keyshortcuts="?">
            <Keyboard size={13} aria-hidden />{tr('bd.st.shortcuts')}<kbd aria-hidden>?</kbd>
          </button>
        )}
      </div>
    </div>
  )
}
