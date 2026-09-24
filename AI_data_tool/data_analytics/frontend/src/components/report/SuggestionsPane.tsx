import { useEffect, useMemo, useState } from 'react'
import { suggestApi } from '../../services/api'
import type { DatasetColumn, WidgetSuggestion } from '../../services/api'
import type { Widget } from '../../types/report'
import WidgetRenderer from './WidgetRenderer'
import { CrossFilterProvider } from './CrossFilterContext'

export interface Suggestion {
  widget_type: string
  title: string
  reason: string
  config: Record<string, unknown>
}

/**
 * Candidate visuals from what the data actually looks like — SAS's Suggestions,
 * driven by dtype, cardinality and the correlation matrix the analysis already
 * computed. Pure heuristics, deterministic given the inputs, each suggestion a
 * one-click add of an ordinary widget.
 */
export function suggestWidgets(
  columns: DatasetColumn[],
  analysis: {
    numeric?: { correlation?: Record<string, Record<string, number>> }
    categorical?: { columns?: Record<string, { n_unique?: number }> }
  } | null,
  seed = 0,
): Suggestion[] {
  const numeric = columns.filter(c => c.dtype === 'numeric')
  const cats = columns.filter(c => c.dtype === 'categorical')
  const dates = columns.filter(c => c.dtype === 'datetime')
  const out: Suggestion[] = []

  /**
   * How many distinct values a categorical column has, from the PROFILE.
   *
   * This used to read `DatasetColumn.stats.unique`. `stats` is a declared field
   * that nothing in the application ever writes — `stats={}` is passed
   * literally at all three creation sites — so it was always NaN, `low` was
   * always false, and this function had never once suggested a pie. The test
   * that claimed otherwise supplied its own `stats` object.
   *
   * `categorical.columns[name].n_unique` is real and already in the payload
   * this function is handed. Unknown stays unknown: a bar is readable at any
   * width and a pie is not, so an absent count must not read as "few".
   */
  const card = (c: DatasetColumn) =>
    Number(analysis?.categorical?.columns?.[c.name]?.n_unique ?? NaN)

  for (const cat of cats) {
    for (const m of numeric.slice(0, 2)) {
      const n = card(cat)
      const low = Number.isFinite(n) && n <= 6
      out.push(low
        ? { widget_type: 'pie', title: `${m.name} by ${cat.name}`,
            reason: `${cat.name} has few values — parts of a whole read well`,
            config: { dimension: cat.name, measure: m.name, aggregation: 'sum' } }
        : { widget_type: 'bar', title: `${m.name} by ${cat.name}`,
            reason: `compare ${m.name} across ${cat.name}`,
            config: { dimension: cat.name, measure: m.name, aggregation: 'sum' } })
    }
  }
  for (const d of dates.slice(0, 1)) {
    for (const m of numeric.slice(0, 2)) {
      out.push({ widget_type: 'line', title: `${m.name} over ${d.name}`,
        reason: `${d.name} is a date — show the trend`,
        config: { dimension: d.name, measure: m.name, aggregation: 'sum' } })
    }
  }
  // Correlated pairs -> scatter, strongest first.
  const corr = analysis?.numeric?.correlation
  if (corr) {
    const pairs: { a: string; b: string; r: number }[] = []
    for (const [a, row] of Object.entries(corr)) {
      for (const [b, r] of Object.entries(row ?? {})) {
        if (a < b && typeof r === 'number' && Math.abs(r) >= 0.6) pairs.push({ a, b, r })
      }
    }
    pairs.sort((x, y) => Math.abs(y.r) - Math.abs(x.r))
    for (const p of pairs.slice(0, 3)) {
      out.push({ widget_type: 'scatter', title: `${p.a} vs ${p.b}`,
        reason: `correlated (r = ${p.r.toFixed(2)})`,
        config: { x_column: p.a, y_column: p.b } })
    }
  }
  for (const m of numeric.slice(0, 2)) {
    out.push({ widget_type: 'histogram', title: `Distribution of ${m.name}`,
      reason: `see the shape of ${m.name}`, config: { measure: m.name, bins: 20 } })
  }

  // "Refresh" rotates the window so the pane shows different candidates rather
  // than the same six forever — deterministic for a given seed, so testable.
  const start = out.length ? (seed * 6) % out.length : 0
  return out.slice(start).concat(out.slice(0, start)).slice(0, 6)
}

/** A live mini render of the suggested widget on its real data — the same
 *  WidgetRenderer the canvas uses, in an isolated cross-filter scope with
 *  pointer events off. The config travels UNCHANGED, so the preview's fetch
 *  lands in the client result cache and clicking “Add” reuses it. */
function SuggestionPreview({ datasetId, widgetType, config, idx }: {
  datasetId: number; widgetType: string; config: Record<string, unknown>; idx: number
}) {
  const widget = useMemo<Widget>(() => ({
    id: -(idx + 1), page_id: -1, widget_type: widgetType as Widget['widget_type'],
    title: '', config, layout: { x: 0, y: 0, w: 4, h: 3 }, created_at: '',
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [widgetType, JSON.stringify(config), idx])
  return (
    <div aria-hidden="true" data-testid="suggestion-preview"
      style={{ height: 118, pointerEvents: 'none', marginBottom: 6 }}>
      <CrossFilterProvider>
        <WidgetRenderer widget={widget} datasetId={datasetId} editMode={false} />
      </CrossFilterProvider>
    </div>
  )
}

export default function SuggestionsPane({ columns, analysis, onAdd, reportId, datasetId }: {
  columns: DatasetColumn[]
  analysis: { numeric?: { correlation?: Record<string, Record<string, number>> } } | null
  onAdd: (s: Suggestion) => void
  /** When set, the pane leads with insight-driven suggestions for this
      report: the insights engine's ranked findings mapped to widgets, with
      findings about columns the report's name/description mentions first. */
  reportId?: number
  /** When set, every suggestion card renders a LIVE mini chart of itself. */
  datasetId?: number | null
}) {
  const [seed, setSeed] = useState(0)
  const suggestions = useMemo(() => suggestWidgets(columns, analysis, seed), [columns, analysis, seed])
  const [insightSugs, setInsightSugs] = useState<WidgetSuggestion[] | null>(null)
  useEffect(() => {
    if (!reportId) return
    suggestApi.forReport(reportId).then(setInsightSugs).catch(() => setInsightSugs(null))
  }, [reportId])

  return (
    <div style={{ padding: 12, overflowY: 'auto', height: '100%' }}>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 8 }}>
        <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em' }}>
          Suggestions
        </span>
        <button className="btn" style={{ fontSize: 10, marginInlineStart: 'auto' }} onClick={() => setSeed(x => x + 1)}>
          ↻ More
        </button>
      </div>

      {insightSugs && insightSugs.length > 0 && (
        <>
          <div style={{ fontSize: 9, fontWeight: 700, color: 'var(--accent)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 6 }}>
            From this data's insights
          </div>
          <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 10 }}>
            {insightSugs.map((s, i) => (
              <li key={`ins-${i}`} data-testid={`insight-suggestion-${s.kind}`}
                style={{ border: s.aligned ? '1px solid var(--accent)' : '1px solid var(--border)', borderRadius: 6, padding: '8px 10px' }}>
                <div style={{ fontSize: 11, fontWeight: 600 }}>
                  {s.aligned && <span title="Matches the report description" style={{ color: 'var(--accent)' }}>✦ </span>}
                  {s.title}
                </div>
                <div style={{ fontSize: 10, color: 'var(--muted)', margin: '2px 0 6px' }}>{s.widget_type} · {s.reason}</div>
                {datasetId != null && (
                  <SuggestionPreview datasetId={datasetId} widgetType={s.widget_type} config={s.config} idx={i} />
                )}
                <button className="btn btn-primary" style={{ fontSize: 10 }}
                  onClick={() => onAdd({ widget_type: s.widget_type, title: s.title, reason: s.reason, config: s.config })}>
                  + Add to page
                </button>
              </li>
            ))}
          </ul>
          <div style={{ fontSize: 9, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 6 }}>
            From column shapes
          </div>
        </>
      )}
      {suggestions.length === 0 && (
        <p style={{ fontSize: 11, color: 'var(--muted)' }}>Nothing to suggest — the dataset needs at least one numeric column.</p>
      )}
      <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 6 }}>
        {suggestions.map((s, i) => (
          <li key={`${s.widget_type}-${s.title}-${i}`}
            style={{ border: '1px solid var(--border)', borderRadius: 6, padding: '8px 10px' }}>
            <div style={{ fontSize: 11, fontWeight: 600 }}>{s.title}</div>
            <div style={{ fontSize: 10, color: 'var(--muted)', margin: '2px 0 6px' }}>{s.widget_type} · {s.reason}</div>
            {datasetId != null && (
              <SuggestionPreview datasetId={datasetId} widgetType={s.widget_type} config={s.config} idx={100 + i} />
            )}
            <button className="btn btn-primary" style={{ fontSize: 10 }} onClick={() => onAdd(s)}>+ Add to page</button>
          </li>
        ))}
      </ul>
    </div>
  )
}
