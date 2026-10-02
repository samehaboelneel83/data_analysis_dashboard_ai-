/**
 * View mode has one look: Claude Design's "Dashboards part 3" (Modern) -- one
 * header row, page tabs as pills with the filters beside them, cards on a
 * quiet canvas. The old per-viewer Default/Modern switch was removed.
 */

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
