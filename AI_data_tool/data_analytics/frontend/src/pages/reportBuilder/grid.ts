import type { CSSProperties } from 'react'
import type { Widget } from '../../types/report'

export const COLS = 12
export const ROW_H = 58    // px per grid row unit
export const GAP = 8
export const LEFT_SIDEBAR_W = 220
export const RIGHT_PANEL_W = 245
export const MIN_CANVAS_W = 600   // floor so grid cells stay usable instead of squeezing to nothing

export const CLASSIFICATION_LABELS = ['Public', 'Internal', 'Confidential', 'Restricted']
export const CLASSIFICATION_COLORS: Record<string, string> = {
  Public: '#2e7d32', Internal: '#1565c0', Confidential: '#e65100', Restricted: '#c62828',
}

export function gridStyle(layout: Widget['layout'], containerW: number): CSSProperties {
  const cellW = (containerW - GAP * (COLS - 1)) / COLS
  return {
    position: 'absolute',
    left:   layout.x * (cellW + GAP),
    top:    layout.y * (ROW_H + GAP),
    width:  layout.w * cellW + (layout.w - 1) * GAP,
    height: layout.h * ROW_H + (layout.h - 1) * GAP,
  }
}

export function canvasH(widgets: Widget[]) {
  if (!widgets.length) return 560
  return Math.max(560, Math.max(...widgets.map(w => w.layout.y + w.layout.h)) * (ROW_H + GAP) + 80)
}
