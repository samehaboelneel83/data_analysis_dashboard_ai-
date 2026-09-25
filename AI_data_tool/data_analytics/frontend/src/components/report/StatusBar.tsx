import { useT } from '../../i18n'
const ZOOM_MIN = 50
const ZOOM_MAX = 150
const ZOOM_STEP = 10

export default function StatusBar({ pageIndex, pageCount, saveState, zoom, onZoomChange }: {
  pageIndex: number
  pageCount: number
  saveState: 'saved' | 'saving'
  zoom?: number
  onZoomChange?: (zoom: number) => void
}) {
  const tr = useT()
  const clamp = (z: number) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, z))

  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      padding: '4px 12px', borderTop: '1px solid var(--border)', background: 'var(--surface)',
      fontSize: 11, color: 'var(--muted)', flexShrink: 0,
    }}>
      <span>{tr('status.page', { n: pageIndex + 1, total: pageCount })}</span>
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
        <span>{saveState === 'saving' ? tr('status.saving') : tr('status.saved')}</span>
      </div>
    </div>
  )
}
