/**
 * A table cell that holds a web address is a link (2026-10-08: a dealer added
 * each car's listing link to a dashboard table and could only copy it).
 * Only http(s) addresses -- never javascript: or data: -- and opened in a new
 * tab without handing the page a reference back to this one.
 */
const URL_RE = /^https?:\/\/[^\s<>"']+$/i

export function isWebAddress(v: unknown): v is string {
  return typeof v === 'string' && URL_RE.test(v.trim())
}

/** "eg.hatla2ee.com/…/7234745": the site and the last part, readable in a cell. */
export function shortAddress(url: string): string {
  try {
    const u = new URL(url)
    const parts = u.pathname.split('/').filter(Boolean)
    const last = parts[parts.length - 1]
    return last ? `${u.host}/…/${last}` : u.host
  } catch { return url }
}

export function CellLink({ url }: { url: string }) {
  return (
    <a href={url.trim()} target="_blank" rel="noopener noreferrer" title={url}
      onClick={e => e.stopPropagation()} dir="ltr">
      {shortAddress(url.trim())}
    </a>
  )
}
