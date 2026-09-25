/**
 * The visible half of the truncation contract (MASTER_PLAN Phase 0, rule 4).
 *
 * A series cut by `limit` used to say nothing: the settings panel stamps
 * `limit: 20` on every chart, so a bar over 213 cities drew 20 bars that read
 * as the whole picture. SAS at least has a tiny ⓘ; this is a line of text in
 * the frame, in the one vocabulary every widget uses, with the one-click
 * alternative beside it.
 */
export const PATCH_WIDGET_EVENT = 'datalytics:patch-widget-config'

/** Past this, "show all" would draw an unreadable chart; offer a bigger page instead. */
export const SHOW_ALL_CEILING = 500

export interface Truncation { applied: boolean; shown: number; of: number; limit?: number; reason?: string; unit?: 'rows' | 'groups' | 'categories' | 'points' }

export function truncationSentence(t: Truncation, dimension?: string): string {
  const what = t.unit === 'rows' ? 'rows' : t.unit === 'points' ? 'points'
    : dimension ? `${dimension} values` : t.unit === 'categories' ? 'categories' : 'groups'
  return `Showing ${t.shown.toLocaleString()} of ${t.of.toLocaleString()} ${what}`
}

/** E04: rows whose category is blank are dropped by all three engines (a
 *  deliberate standard), and every grouped series now says how many. This is
 *  the reader's half: without it the bars silently sum to less than the
 *  total everywhere else. */
export function missingCategorySentence(rows: number, dimension?: string): string {
  const one = rows === 1
  return `${rows.toLocaleString()} row${one ? '' : 's'} with no ${dimension || 'category'} ${one ? 'is' : 'are'} not shown`
}

export function TruncationNote({ t, dimension, onShowMore }:
  { t: Truncation; dimension?: string; onShowMore?: (limit: number) => void }) {
  if (!t?.applied) return null
  const next = Math.min(t.of, SHOW_ALL_CEILING)
  return (
    <div data-testid="truncation-note" role="note"
      style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', padding: '2px 8px 4px',
        fontSize: 10.5, color: 'var(--muted)', borderTop: '1px solid var(--border)' }}>
      <span>{truncationSentence(t, dimension)}{t.reason === 'limit' ? ' (row limit)' : ''}</span>
      {onShowMore && (
        <button type="button" className="btn btn-ghost btn-sm"
          style={{ fontSize: 10.5, padding: '0 6px', lineHeight: '18px' }}
          onMouseDown={e => e.stopPropagation()} onPointerDown={e => e.stopPropagation()}
          onClick={e => { e.stopPropagation(); onShowMore(next) }}>
          {next === t.of ? 'Show all' : `Show ${next.toLocaleString()}`}
        </button>
      )}
    </div>
  )
}
