import { useMemo, useState } from 'react'

/**
 * A search box for a list that renders every row it is given.
 *
 * Dashboard, Reports and Connections each render their whole
 * collection with no way to narrow it. That is fine at a demo's fifteen rows
 * and useless at an organisation's four hundred, where finding one report
 * means scrolling past every other.
 *
 * Client-side on purpose. The list endpoints take no `limit`/`offset` (checked:
 * `list_reports` and its siblings accept neither), and filtering rows the
 * browser already holds costs nothing, needs no API change, and keeps the
 * air-gapped guarantee intact -- it is a native `<input>` and an `Array.filter`,
 * with no new dependency.
 *
 * It deliberately does NOT paginate. Pagination without a server-side `offset`
 * would hide rows behind pages the user must click through, which is worse than
 * a long scroll; searching is what actually answers "where is that report?".
 */

/** Case-insensitive substring match across whatever fields the caller names. */
export function matches(haystacks: (string | null | undefined)[], needle: string) {
  const q = needle.trim().toLowerCase()
  if (!q) return true
  return haystacks.some(h => (h ?? '').toLowerCase().includes(q))
}

/**
 * Filters `items` by `fields`, and renders the search box.
 *
 * Returns both so the caller controls where the input sits and what the empty
 * result looks like -- the four pages have different layouts, and a component
 * that owned the whole list would have to know all of them.
 */
export function useListFilter<T>(
  items: T[],
  fields: (item: T) => (string | null | undefined)[],
  label: string,
) {
  const [query, setQuery] = useState('')

  const filtered = useMemo(
    () => (query.trim() ? items.filter(i => matches(fields(i), query)) : items),
    // `fields` is typically an inline arrow, so it is intentionally not a
    // dependency: including it would recompute on every render and defeat the
    // memo, and it is pure with respect to `query` and `items`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [items, query],
  )

  // Only worth showing once the list is long enough to be hard to scan. Below
  // that the box is chrome competing with the content it filters.
  const worthShowing = items.length >= 8

  const input = worthShowing ? (
    <input
      type="search"
      value={query}
      onChange={e => setQuery(e.target.value)}
      aria-label={label}
      placeholder={label}
      style={{
        padding: '6px 10px', fontSize: 12, borderRadius: 6,
        border: '1px solid var(--border)', background: 'var(--surface)',
        color: 'var(--text)', minWidth: 200,
      }}
    />
  ) : null

  return {
    /** The rows to render. */
    filtered,
    /** The search box, or null when the list is short enough not to need one. */
    input,
    query,
    /** True when a search is active but matched nothing -- distinct from an
     *  empty collection, which needs the page's own "nothing yet" copy. */
    noMatches: query.trim().length > 0 && filtered.length === 0,
  }
}
