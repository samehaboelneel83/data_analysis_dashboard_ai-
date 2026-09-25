import { useT } from '../../i18n'
import { useEffect } from 'react'
import { useCrossFilter } from './CrossFilterContext'

/**
 * What is filtering this page, and a way to undo it.
 *
 * Rendered even when nothing is filtering, saying so — the way SAS's strip
 * does. Returning null on an empty list looked identical to a page with no
 * filter strip at all, so a reader could not tell "nothing is filtering" from
 * "this page cannot be filtered", and after clicking a chart there was no fixed
 * place to look to confirm what they had just done. That matters more now that
 * every map widget cross-filters and a map selection is easy to make by
 * accident.
 */
export default function FilterBar({ keyboard = false }: {
  /** Bind Ctrl+Z / Ctrl+Shift+Z to the reader's selection history. Only where
   *  nothing else owns those keys (the share and embed viewers; the builder's
   *  Ctrl+Z is the author's undo). */
  keyboard?: boolean
} = {}) {
  const tr = useT()
  const { activeFilters, clearFilter, clearAllFilters, undoSelection, redoSelection, undoLabel, redoLabel } = useCrossFilter()
  useEffect(() => {
    if (!keyboard) return
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== 'z') return
      const t = e.target as HTMLElement | null
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return
      e.preventDefault()
      if (e.shiftKey) redoSelection(); else undoSelection()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [keyboard, undoSelection, redoSelection])

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 0', marginBottom: 8, flexWrap: 'wrap' }}>
      <span style={{ fontSize: 11, color: 'var(--muted)', fontWeight: 600 }}>{tr('filters.label')}</span>
      {activeFilters.length === 0 && (
        <span style={{ fontSize: 11, color: 'var(--muted)' }}>{tr('filters.none')}</span>
      )}
      {activeFilters.map(f => (
        <span key={`${f.sourceWidgetId}-${f.column}`} style={{
          display: 'flex', alignItems: 'center', gap: 4,
          background: 'color-mix(in srgb, var(--accent) 15%, transparent)', border: '1px solid var(--accent)',
          borderRadius: 99, padding: '2px 8px 2px 10px', fontSize: 11,
        }}>
          <span style={{ color: 'var(--accent)' }}>{f.label}</span>
          {/* Named, not a bare ×: this strip is the one place a filter can be
              removed without hunting for the widget that set it, and a row of
              unlabelled buttons is unusable by keyboard or screen reader. */}
          <button onClick={() => clearFilter(f.column, f.sourceWidgetId)}
            aria-label={`Remove filter ${f.label}`} title={`Remove filter ${f.label}`}
            style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', padding: 0, fontSize: 13, lineHeight: 1 }}>
            ×
          </button>
        </span>
      ))}
      {activeFilters.length > 0 && (
        <button onClick={clearAllFilters} className="btn btn-ghost btn-sm" style={{ fontSize: 11, padding: '2px 8px' }}>
          Clear all
        </button>
      )}
      {/* The reader's own undo: back through their clicks, never the author's
          design. aria-disabled keeps the tooltip saying why nothing happens. */}
      {(undoLabel || redoLabel) && (
        <span style={{ display: 'inline-flex', gap: 2, marginInlineStart: 'auto' }}>
          <button className="btn btn-ghost btn-sm" aria-label="Undo selection" aria-disabled={!undoLabel}
            title={undoLabel ? `Back to: ${undoLabel}` : 'No earlier selection'}
            onClick={() => { if (undoLabel) undoSelection() }}
            style={{ fontSize: 11, padding: '2px 6px', opacity: undoLabel ? 1 : 0.4 }}>↶</button>
          <button className="btn btn-ghost btn-sm" aria-label="Redo selection" aria-disabled={!redoLabel}
            title={redoLabel ? `Forward to: ${redoLabel}` : 'Nothing to redo'}
            onClick={() => { if (redoLabel) redoSelection() }}
            style={{ fontSize: 11, padding: '2px 6px', opacity: redoLabel ? 1 : 0.4 }}>↷</button>
        </span>
      )}
    </div>
  )
}
