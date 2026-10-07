import { Maximize, Minus, Plus } from 'lucide-react'
import { useT } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'

export const ZOOM_MIN = 50
export const ZOOM_MAX = 150
const STEP = 10

/**
 * Zoom − 100% + and Fit in the builder's second row (redesign 7e1; v1 kept it
 * in the status bar). The page is a fluid grid that fills the canvas width at
 * 100%, so Fit is 100%.
 */
export default function ZoomControl({ zoom, onZoom }: { zoom: number; onZoom: (z: number) => void }) {
  const t = useT()
  const set = (z: number) => onZoom(Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, z)))
  return (
    <>
      <span className="dl-bd-zoom">
        <button type="button" className="dl-bd-ib" aria-label={t('bd.zoomOut')} title={t('bd.zoomOut')}
          disabled={zoom <= ZOOM_MIN} onClick={() => set(zoom - STEP)}><Minus size={14} aria-hidden /></button>
        <span dir="ltr">{localDigits(`${zoom}%`)}</span>
        <button type="button" className="dl-bd-ib" aria-label={t('bd.zoomIn')} title={t('bd.zoomIn')}
          disabled={zoom >= ZOOM_MAX} onClick={() => set(zoom + STEP)}><Plus size={14} aria-hidden /></button>
      </span>
      <button type="button" className="btn btn-ghost btn-sm dl-bd-fit" title={t('bd.fitTitle')} onClick={() => onZoom(100)}>
        <Maximize size={14} aria-hidden />{t('bd.fit')}
      </button>
    </>
  )
}
