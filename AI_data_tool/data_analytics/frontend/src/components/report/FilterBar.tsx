import { useT } from '../../i18n'
import { useEffect } from 'react'
import { ListFilter } from 'lucide-react'
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
/** A report-wide filter shown on the canvas (Fields plan F7). */
export interface ReportFilterChip { id: number; label: string }

export default function FilterBar({ keyboard = false, variant = 'strip', reportFilters = [], onRemoveReportFilter }: {
  /** Bind Ctrl+Z / Ctrl+Shift+Z to the reader's selection history. Only where
   *  nothing else owns those keys (the share and embed viewers; the builder's
   *  Ctrl+Z is the author's undo). */
  keyboard?: boolean
  /** 'chips': the Modern view style's filter row, beside the page tabs. */
  variant?: 'strip' | 'chips'
  /** Report filters (set in the builder's Fields panel). They filter every
   *  widget, so they are shown here with the selections: a report filtered
   *  out of sight read "No selections" while half the rows were hidden. */
  reportFilters?: ReportFilterChip[]
  /** Given in the builder only: the filter can be removed from the canvas. */
  onRemoveReportFilter?: (id: number) => void
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

  if (variant === 'chips') {
    // Same state, same actions; drawn as the Modern view's chip row. Still
    // says so when nothing is filtering, for the reason given above.
    return (
      <div className="dl-vw-flt" role="group" aria-label={tr('filters.label')}>
        <ListFilter size={14} aria-hidden className="dl-vw-flt__ic" />
        {reportFilters.map(f => (
          <span key={`rf-${f.id}`} className="dl-vw-fc dl-vw-fc--on" title={tr('bc.shell.rf.everywhere')} data-report-filter="">
            <span>{f.label}</span>
            {onRemoveReportFilter && (
              <button type="button" onClick={() => onRemoveReportFilter(f.id)}
                aria-label={tr('bc.shell.flt.remove', { label: f.label })} title={tr('bc.shell.flt.remove', { label: f.label })}>×</button>
            )}
          </span>
        ))}
        {activeFilters.length === 0 && reportFilters.length === 0 && <span className="dl-vw-flt__none">{tr('view.noFilters')}</span>}
        {activeFilters.map(f => (
          <span key={`${f.sourceWidgetId}-${f.column}`} className="dl-vw-fc dl-vw-fc--on">
            <span>{f.label}</span>
            <button type="button" onClick={() => clearFilter(f.column, f.sourceWidgetId)}
              aria-label={tr('bc.shell.flt.remove', { label: f.label })} title={tr('bc.shell.flt.remove', { label: f.label })}>×</button>
          </span>
        ))}
        {activeFilters.length > 0 && (
          <button type="button" className="dl-vw-rst" onClick={clearAllFilters}>{tr('view.resetFilters')}</button>
        )}
        {(undoLabel || redoLabel) && (
          <span style={{ display: 'inline-flex', gap: 2 }}>
            <button className="btn btn-ghost btn-sm" aria-label={tr('bc.shell.flt.undo')} aria-disabled={!undoLabel}
              title={undoLabel ? tr('bc.shell.flt.backTo', { label: undoLabel }) : tr('bc.shell.flt.noEarlier')}
              onClick={() => { if (undoLabel) undoSelection() }}
              style={{ padding: '2px 6px', opacity: undoLabel ? 1 : 0.4 }}>↶</button>
            <button className="btn btn-ghost btn-sm" aria-label={tr('bc.shell.flt.redo')} aria-disabled={!redoLabel}
              title={redoLabel ? tr('bc.shell.flt.forwardTo', { label: redoLabel }) : tr('bc.shell.flt.nothingRedo')}
              onClick={() => { if (redoLabel) redoSelection() }}
              style={{ padding: '2px 6px', opacity: redoLabel ? 1 : 0.4 }}>↷</button>
          </span>
        )}
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 0', marginBottom: 8, flexWrap: 'wrap' }}>
      <span style={{ fontSize: 11, color: 'var(--muted)', fontWeight: 600 }}>{tr('filters.label')}</span>
      {reportFilters.map(f => (
        <span key={`rf-${f.id}`} title={tr('bc.shell.rf.everywhere')} data-report-filter="" style={{
          display: 'flex', alignItems: 'center', gap: 4, background: 'var(--surface2)', border: '1px solid var(--border)',
          borderRadius: 99, padding: '2px 8px 2px 10px', fontSize: 11,
        }}>
          <span>{f.label}</span>
          {onRemoveReportFilter && (
            <button onClick={() => onRemoveReportFilter(f.id)}
              aria-label={tr('bc.shell.flt.remove', { label: f.label })} title={tr('bc.shell.flt.remove', { label: f.label })}
              style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', padding: 0, fontSize: 13, lineHeight: 1 }}>
              ×
            </button>
          )}
        </span>
      ))}
      {activeFilters.length === 0 && reportFilters.length === 0 && (
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
            aria-label={tr('bc.shell.flt.remove', { label: f.label })} title={tr('bc.shell.flt.remove', { label: f.label })}
            style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', padding: 0, fontSize: 13, lineHeight: 1 }}>
            ×
          </button>
        </span>
      ))}
      {activeFilters.length > 0 && (
        <button onClick={clearAllFilters} className="btn btn-ghost btn-sm" style={{ fontSize: 11, padding: '2px 8px' }}>
          {tr('bc.shell.flt.clearAll')}
        </button>
      )}
      {/* The reader's own undo: back through their clicks, never the author's
          design. aria-disabled keeps the tooltip saying why nothing happens. */}
      {(undoLabel || redoLabel) && (
        <span style={{ display: 'inline-flex', gap: 2, marginInlineStart: 'auto' }}>
          <button className="btn btn-ghost btn-sm" aria-label={tr('bc.shell.flt.undo')} aria-disabled={!undoLabel}
            title={undoLabel ? tr('bc.shell.flt.backTo', { label: undoLabel }) : tr('bc.shell.flt.noEarlier')}
            onClick={() => { if (undoLabel) undoSelection() }}
            style={{ fontSize: 11, padding: '2px 6px', opacity: undoLabel ? 1 : 0.4 }}>↶</button>
          <button className="btn btn-ghost btn-sm" aria-label={tr('bc.shell.flt.redo')} aria-disabled={!redoLabel}
            title={redoLabel ? tr('bc.shell.flt.forwardTo', { label: redoLabel }) : tr('bc.shell.flt.nothingRedo')}
            onClick={() => { if (redoLabel) redoSelection() }}
            style={{ fontSize: 11, padding: '2px 6px', opacity: redoLabel ? 1 : 0.4 }}>↷</button>
        </span>
      )}
    </div>
  )
}
