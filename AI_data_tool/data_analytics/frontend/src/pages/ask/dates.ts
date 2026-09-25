/**
 * Dates in the app's language, not the browser's: a PC set to Arabic must
 * still show "Sep 25, 2026" in the English interface, and the reverse.
 * Western digits here; localDigits() applies the reader's digit choice.
 */
function locale(): string {
  try { return localStorage.getItem('datalytics.language') === 'ar' ? 'ar-EG-u-nu-latn' : 'en-US' } catch { return 'en-US' }
}

export function fmtDate(d: Date, opts: Intl.DateTimeFormatOptions): string {
  return d.toLocaleDateString(locale(), opts)
}

export function fmtTime(d: Date): string {
  return d.toLocaleTimeString(locale(), { hour: '2-digit', minute: '2-digit' })
}
