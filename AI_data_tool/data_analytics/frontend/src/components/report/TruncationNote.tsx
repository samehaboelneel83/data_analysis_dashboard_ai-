import { useEffect, useState } from 'react'
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

/** Page sizes the "Show more" button steps through. */
export const SHOW_MORE_STEPS = [SHOW_ALL_CEILING, 1000, 2500, 5000, 10000]

/** The next limit to offer: the first step ABOVE what is already shown,
 *  capped at the total. A fixed "Show 500" kept offering 500 after 500 were
 *  already shown, so the button did nothing (QA 2026-09-26). `null` once the
 *  largest step is reached -- no button that cannot change anything. */
export function nextShowLimit(t: Pick<Truncation, 'shown' | 'of'>): number | null {
  const step = SHOW_MORE_STEPS.find(n => n > t.shown)
  if (step == null) return null
  return Math.min(t.of, step)
}

export interface Truncation { applied: boolean; shown: number; of: number; limit?: number; reason?: string; unit?: 'rows' | 'groups' | 'categories' | 'points' | 'locations' }

export function truncationSentence(t: Truncation, dimension?: string): string {
  const what = t.unit === 'rows' ? 'rows' : t.unit === 'points' ? 'points' : t.unit === 'locations' ? 'locations'
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

/** E08: cells a grid left blank because too few rows stand behind them. */
export function suppressedCellsSentence(cells: number, below: number): string {
  const one = cells === 1
  const why = below > 0 ? `: fewer than ${below.toLocaleString()} rows each` : ''
  return `${cells.toLocaleString()} cell${one ? '' : 's'} hidden${one ? why.replace(' each', '') : why}`
}

/** The slider's top end: past this one chart ships an unbounded payload
 *  (same ceiling as the backend's FULL_DATA_LIMIT). */
export const SLIDER_MAX = 10_000

/** Map slider position 0..1000 to a count on a log scale, so the low end
 *  (10, 25, 50...) is as easy to hit as the high end on a 5,000-row series. */
export function sliderToCount(pos: number, max: number, min = 1): number {
  if (max <= min) return max
  const v = Math.exp(Math.log(min) + (pos / 1000) * (Math.log(max) - Math.log(min)))
  return Math.min(max, Math.max(min, Math.round(v)))
}
export function countToSlider(count: number, max: number, min = 1): number {
  if (max <= min) return 1000
  return Math.round(1000 * (Math.log(Math.max(min, count)) - Math.log(min)) / (Math.log(max) - Math.log(min)))
}

export function TruncationNote({ t, dimension, onShowMore }:
  { t: Truncation; dimension?: string; onShowMore?: (limit: number) => void }) {
  const max = Math.min(t?.of ?? 0, SLIDER_MAX)
  const [pos, setPos] = useState(() => countToSlider(t?.shown ?? 1, max))
  // A new result (the limit was applied, or the data changed) re-seats the thumb.
  useEffect(() => { setPos(countToSlider(t?.shown ?? 1, max)) }, [t?.shown, max])
  if (!t?.applied) return null
  const count = sliderToCount(pos, max)
  const commit = () => {
    if (!onShowMore || count === t.shown) return
    onShowMore(count)
  }
  const stop = (e: { stopPropagation: () => void }) => e.stopPropagation()
  return (
    <div data-testid="truncation-note" role="note"
      style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', padding: '2px 8px 4px',
        fontSize: 10.5, color: 'var(--muted)', borderTop: '1px solid var(--border)' }}>
      <span>{truncationSentence(t, dimension)}{t.reason === 'limit' ? ' (row limit)' : ''}</span>
      {onShowMore && max > 1 && (
        // One control for "fewer or more": a log-scale slider, applied on
        // release. Replaces a "Show 500" button that could only go one way and
        // kept offering 500 after 500 were shown (QA 2026-09-26).
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, flex: '1 1 160px', minWidth: 140 }}
          onMouseDown={stop} onPointerDown={stop} onClick={stop}>
          <input type="range" min={0} max={1000} step={1} value={pos}
            aria-label={`How many ${dimension ? `${dimension} values` : 'groups'} to show`}
            aria-valuetext={count >= max ? `All ${t.of.toLocaleString()}` : count.toLocaleString()}
            onChange={e => setPos(Number(e.target.value))}
            onPointerUp={commit} onKeyUp={commit} onBlur={commit}
            style={{ flex: 1, minWidth: 80, accentColor: 'var(--accent)' }} />
          <span style={{ minWidth: 52, textAlign: 'end', color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}>
            {count >= max && max === t.of ? 'All' : count.toLocaleString()}
          </span>
        </label>
      )}
    </div>
  )
}
