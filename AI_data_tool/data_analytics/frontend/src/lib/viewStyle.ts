import { useCallback, useState } from 'react'

/**
 * How a dashboard looks in View mode: the original layout ('default'), or the
 * one from Claude Design's "Dashboards part 3" ('modern') -- one header row,
 * page tabs as pills with the filters beside them, cards on a quiet canvas.
 *
 * A per-viewer preference, so it lives in this browser: storage can be absent
 * or throw (private windows, blocked site data), and then the page simply
 * uses the default.
 */
export type ViewStyle = 'default' | 'modern'

const KEY = 'datalytics.viewStyle'

export function readViewStyle(): ViewStyle {
  try {
    return localStorage.getItem(KEY) === 'modern' ? 'modern' : 'default'
  } catch {
    return 'default'
  }
}

export function useViewStyle(): [ViewStyle, (v: ViewStyle) => void] {
  const [style, setStyle] = useState<ViewStyle>(readViewStyle)
  const set = useCallback((v: ViewStyle) => {
    setStyle(v)
    try { localStorage.setItem(KEY, v) } catch { /* the choice lasts this visit */ }
  }, [])
  return [style, set]
}

/** "12 minutes ago", in the reader's language, Latin digits. */
export function updatedAgo(iso: string | null | undefined, locale: string, now = Date.now()): string | null {
  if (!iso) return null
  const then = Date.parse(iso)
  if (Number.isNaN(then)) return null
  const secs = Math.max(0, Math.round((now - then) / 1000))
  const rtf = new Intl.RelativeTimeFormat(`${locale}-u-nu-latn`, { numeric: 'auto' })
  if (secs < 60) return rtf.format(0, 'second')
  if (secs < 3600) return rtf.format(-Math.floor(secs / 60), 'minute')
  if (secs < 86400) return rtf.format(-Math.floor(secs / 3600), 'hour')
  return rtf.format(-Math.floor(secs / 86400), 'day')
}
