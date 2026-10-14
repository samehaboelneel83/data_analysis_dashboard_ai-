import { chartLabel } from '../components/report/ChartGallery'
import type { MessageKey, TranslateFn } from '../i18n'

/**
 * QA4 T2: a chart type by its name, never its code ("kpi", "line"): the
 * gallery's own translated name in Arabic, the gallery label in English.
 */
export function chartName(type: string, t: TranslateFn, language: string): string {
  if (language === 'ar') {
    const k = `gallery.tile.${type}` as MessageKey
    const v = t(k)
    if (v !== k) return v
  }
  return chartLabel(type)
}
