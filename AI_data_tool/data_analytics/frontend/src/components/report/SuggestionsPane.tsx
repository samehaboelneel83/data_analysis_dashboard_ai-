import { useEffect, useMemo, useState } from 'react'
import { suggestApi } from '../../services/api'
import type { DatasetColumn, WidgetSuggestion } from '../../services/api'
import type { Widget } from '../../types/report'
import WidgetRenderer from './WidgetRenderer'
import { CrossFilterProvider } from './CrossFilterContext'
import { Plus, RefreshCw, Sparkles } from 'lucide-react'
import { chartIcon, chartLabel } from './ChartGallery'

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
      className="dl-sug__preview" style={{ pointerEvents: 'none' }}>
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
    <div className="dl-sug">
      <div className="dl-sug__head">
        <span className="dl-sug__title">Suggestions</span>
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => setSeed(x => x + 1)}
          title="Show different suggestions">
          <RefreshCw size={12} aria-hidden /> More
        </button>
      </div>

      {insightSugs && insightSugs.length > 0 && (
        <>
          <div className="dl-sug__group dl-sug__group--accent">From this data's insights</div>
          <ul className="dl-sug__list">
            {insightSugs.map((s, i) => (
              <SuggestionCard key={`ins-${i}`} testId={`insight-suggestion-${s.kind}`} aligned={s.aligned}
                widgetType={s.widget_type} title={s.title} reason={s.reason}
                preview={datasetId != null
                  ? <SuggestionPreview datasetId={datasetId} widgetType={s.widget_type} config={s.config} idx={i} />
                  : null}
                onAdd={() => onAdd({ widget_type: s.widget_type, title: s.title, reason: s.reason, config: s.config })} />
            ))}
          </ul>
          <div className="dl-sug__group">From column shapes</div>
        </>
      )}
      {suggestions.length === 0 && (
        <p className="dl-sug__none">Nothing to suggest — the dataset needs at least one numeric column.</p>
      )}
      <ul className="dl-sug__list">
        {suggestions.map((s, i) => (
          <SuggestionCard key={`${s.widget_type}-${s.title}-${i}`}
            widgetType={s.widget_type} title={s.title} reason={s.reason}
            preview={datasetId != null
              ? <SuggestionPreview datasetId={datasetId} widgetType={s.widget_type} config={s.config} idx={100 + i} />
              : null}
            onAdd={() => onAdd(s)} />
        ))}
      </ul>
    </div>
  )
}

/** One candidate: what it is (glyph + type), why, a live thumbnail when there
 *  is data to draw it from, and a small add action -- the chart is the
 *  content, so the button no longer outweighs it. */
function SuggestionCard({ widgetType, title, reason, preview, onAdd, aligned, testId }: {
  widgetType: string; title: string; reason: string; preview: React.ReactNode
  onAdd: () => void; aligned?: boolean; testId?: string
}) {
  const Icon = chartIcon(widgetType)
  return (
    <li data-testid={testId} className={`dl-sug__card${aligned ? ' dl-sug__card--aligned' : ''}`}>
      <div className="dl-sug__row">
        <span className="dl-sug__icon" aria-hidden><Icon size={15} strokeWidth={1.9} /></span>
        <div className="dl-sug__text">
          <div className="dl-sug__name">
            {aligned && <span title="Matches the report description" className="dl-sug__star"><Sparkles size={11} aria-hidden /></span>}
            {title}
          </div>
          <div className="dl-sug__why">{chartLabel(widgetType)} · {reason}</div>
        </div>
        <button type="button" className="btn btn-sm dl-sug__add" onClick={onAdd} aria-label="Add to page"
          title="Add to page">
          <Plus size={12} aria-hidden /> Add
        </button>
      </div>
      {preview}
    </li>
  )
}
