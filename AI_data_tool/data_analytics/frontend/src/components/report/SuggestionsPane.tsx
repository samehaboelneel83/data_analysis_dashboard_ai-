import { useEffect, useMemo, useState } from 'react'
import { suggestApi, widgetDataApi } from '../../services/api'
import type { ColumnMeta, DatasetColumn, WidgetSuggestion } from '../../services/api'
import { defaultSummary, isIdentifier, nonAdditiveKind } from '../../lib/semanticGuard'
import type { Widget } from '../../types/report'
import { translate, useT, type MessageKey, type TranslateFn } from '../../i18n'
import { formattingCapabilities } from './widgetCapabilities'
import WidgetRenderer from './WidgetRenderer'
import { CrossFilterProvider } from './CrossFilterContext'
import { ArrowUpRight, Check, ChevronRight, EyeOff, Lightbulb, Plus, RefreshCw, Sparkles } from 'lucide-react'
import { takeawayText } from '../../lib/readbackText'
import {
  axisNames, cap, familyOf, signature, takeaway, thumbnail, words,
  type SugFamily, type Takeaway,
} from './suggestionTakeaway'

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
  meta: Record<string, ColumnMeta | undefined> = {},
  /** Titles and reasons in the reader's language; English when not given. */
  tr: TranslateFn = (key, vars) => translate('en', key, vars),
): Suggestion[] {
  if (!columns.some(c => c.dtype === 'numeric')) return []
  const roleOf = (c: DatasetColumn) => meta[c.name]?.role
  const visible = columns.filter(c => !meta[c.name]?.hidden && roleOf(c) !== 'freetext'
    && meta[c.name]?.eligible_for_suggestion !== false)
  // An identifier is never a measure: "Emp no by gender" summed employee
  // numbers (HR evaluation). It is what a head-count counts instead.
  const idCol = visible.find(c => isIdentifier(c.name, meta))
  const numeric = visible.filter(c => (c.dtype === 'numeric' || roleOf(c) === 'measure')
    && !isIdentifier(c.name, meta) && !['category', 'temporal', 'geography'].includes(roleOf(c) ?? '')
    && (nonAdditiveKind(c.name) === null || roleOf(c) === 'measure'))
  const cats = visible.filter(c => (c.dtype === 'categorical' && roleOf(c) !== 'measure' && !isIdentifier(c.name, meta))
    || roleOf(c) === 'category' || roleOf(c) === 'geography')
  const dates = visible.filter(c => c.dtype === 'datetime' || roleOf(c) === 'temporal')
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

  // What counting means: distinct identifiers when there is one ("how many
  // employees"), otherwise rows.
  const countCfg = (dimension: string): Record<string, unknown> => idCol
    ? { dimension, measure: idCol.name, aggregation: 'countd' }
    : { dimension, measure: dimension, aggregation: 'count' }
  const countBy = (cat: string) => idCol
    ? tr('pg.panelsA.sw.countBy', { id: idCol.name, cat }) : tr('pg.panelsA.sw.rowsBy', { cat })
  const countOver = (d: string) => idCol
    ? tr('pg.panelsA.sw.countOver', { id: idCol.name, d }) : tr('pg.panelsA.sw.rowsOver', { d })

  // Head-counts first: the first question about any table of things.
  for (const cat of cats.slice(0, 3)) {
    const n = card(cat)
    const low = Number.isFinite(n) && n <= 6
    out.push({ widget_type: low ? 'pie' : 'bar', title: countBy(cat.name),
      reason: tr('pg.panelsA.sw.howManyEach', { cat: cat.name }), config: countCfg(cat.name) })
  }
  for (const d of dates.slice(0, 1)) {
    out.push({ widget_type: 'line', title: countOver(d.name),
      reason: tr('pg.panelsA.sw.perPeriod', { d: d.name }),
      config: { ...countCfg(d.name), dimension_granularity: 'month' } })
  }
  for (const cat of cats) {
    for (const m of numeric.slice(0, 2)) {
      const n = card(cat)
      const agg = defaultSummary(m.name, meta)
      const avg = agg === 'avg' || agg === 'median'
      // A pie is parts of a whole: an AVERAGE has no whole to be part of.
      const low = Number.isFinite(n) && n <= 6 && !avg
      out.push(low
        ? { widget_type: 'pie', title: tr('pg.panelsA.sw.mBy', { m: m.name, cat: cat.name }),
            reason: tr('pg.panelsA.sw.fewValues', { cat: cat.name }),
            config: { dimension: cat.name, measure: m.name, aggregation: agg } }
        : { widget_type: 'bar', title: tr(avg ? 'pg.panelsA.sw.avgBy' : 'pg.panelsA.sw.mBy', { m: m.name, cat: cat.name }),
            reason: tr(avg ? 'pg.panelsA.sw.compareAvg' : 'pg.panelsA.sw.compare', { m: m.name, cat: cat.name }),
            config: { dimension: cat.name, measure: m.name, aggregation: agg } })
    }
  }
  for (const d of dates.slice(0, 1)) {
    for (const m of numeric.slice(0, 2)) {
      const agg = defaultSummary(m.name, meta)
      out.push({ widget_type: 'line', title: tr(agg === 'avg' ? 'pg.panelsA.sw.avgOver' : 'pg.panelsA.sw.mOver', { m: m.name, d: d.name }),
        reason: tr('pg.panelsA.sw.trend', { d: d.name }),
        // By month: a trend read at a glance, the same grain whether it is
        // previewed or added (an automatic grain drew ~100 weekly points and an
        // overview slider into a 300px preview).
        config: { dimension: d.name, measure: m.name, aggregation: agg, dimension_granularity: 'month' } })
    }
  }
  // Correlated pairs -> scatter, strongest first.
  const corr = analysis?.numeric?.correlation
  const usable = new Set(numeric.map(c => c.name))
  if (corr) {
    const pairs: { a: string; b: string; r: number }[] = []
    for (const [a, row] of Object.entries(corr)) {
      for (const [b, r] of Object.entries(row ?? {})) {
        if (a < b && usable.has(a) && usable.has(b) && typeof r === 'number' && Math.abs(r) >= 0.6) pairs.push({ a, b, r })
      }
    }
    pairs.sort((x, y) => Math.abs(y.r) - Math.abs(x.r))
    for (const p of pairs.slice(0, 3)) {
      out.push({ widget_type: 'scatter', title: tr('pg.panelsA.sw.vs', { a: p.a, b: p.b }),
        reason: tr('pg.panelsA.sw.correlated', { r: p.r.toFixed(2) }),
        config: { x_column: p.a, y_column: p.b } })
    }
  }
  for (const m of numeric.slice(0, 2)) {
    out.push({ widget_type: 'histogram', title: tr('pg.panelsA.sw.dist', { m: m.name }),
      reason: tr('pg.panelsA.sw.shape', { m: m.name }), config: { measure: m.name, bins: 20 } })
  }

  // "Refresh" rotates the window so the pane shows different candidates rather
  // than the same six forever — deterministic for a given seed, so testable.
  const start = out.length ? (seed * 6) % out.length : 0
  return out.slice(start).concat(out.slice(0, start)).slice(0, 6)
}

/**
 * The panel, built to be read while scrolling:
 *
 *  - Each card leads with what the chart SAYS ("Delivered has 98% of freight
 *    value"), read from its own data; the column names move to a quiet line
 *    under it.
 *  - Cards are compact: a shape-only thumbnail beside the text, so most of the
 *    ideas fit without scrolling. Clicking a card opens the full live chart --
 *    with its axes named in words -- and the numbers behind the headline.
 *  - Ideas are grouped (Compare, Trend over time, Distribution, Relationship)
 *    under headings that stay put while the list scrolls, with filter chips.
 *  - The strongest finding comes first.
 *  - A chart that is already on the page is folded away under "already on
 *    this page", with a way to jump to it; one just added says "✓ Added".
 */

const FAMILIES: { key: SugFamily; label: MessageKey }[] = [
  { key: 'summary', label: 'sug.fam.summary' },
  { key: 'compare', label: 'sug.fam.compare' },
  { key: 'trend', label: 'sug.fam.trend' },
  { key: 'dist', label: 'sug.fam.dist' },
  { key: 'rel', label: 'sug.fam.rel' },
]

interface Item {
  key: string
  widget_type: string
  title: string
  reason: string
  config: Record<string, unknown>
  aligned?: boolean
  insightKind?: string
  fromInsights: boolean
  /** What it draws, read back from its result on every row (server). */
  takeaway?: string
}

const HIDDEN_KEY = (reportId?: number) => `datalytics:sug-hidden:${reportId ?? 'none'}`
function readHidden(reportId?: number): string[] {
  try {
    const v = JSON.parse(localStorage.getItem(HIDDEN_KEY(reportId)) || '[]')
    return Array.isArray(v) ? v.filter(x => typeof x === 'string') : []
  } catch { return [] }
}

/** The config the expanded preview draws AND the one "Add" saves: the same
 *  chart, with its axes named in words so a reader knows what each one is. */
function labelled(item: Item): Record<string, unknown> {
  const out = { ...item.config }
  // Only where the chart draws axis titles: the server refuses a setting the
  // renderer would ignore, and a box plot with titles silently failed to add
  // (HR re-test 2026-10-02).
  if (!formattingCapabilities(item.widget_type as Widget['widget_type']).includes('axes')) return out
  const names = axisNames(item.widget_type, item.config)
  if (names.x && out.x_axis_label === undefined) out.x_axis_label = names.x
  if (names.y && out.y_axis_label === undefined) out.y_axis_label = names.y
  return out
}

function subline(item: Item, tr: ReturnType<typeof useT>): string {
  const c = item.config
  const m = typeof c.measure === 'string' ? cap(words(c.measure)) : tr('sug.rows')
  const d = typeof c.dimension === 'string' ? words(c.dimension) : ''
  switch (familyOf(item.widget_type)) {
    case 'trend': return d ? `${m} · ${tr('sug.over')} ${d}` : m
    case 'dist': return d && item.widget_type === 'box_plot' ? `${m} · ${tr('sug.by')} ${d}` : `${m} · ${tr('sug.spread')}`
    case 'rel': return item.reason
    case 'summary': return item.reason
    default: {
      const d2 = typeof c.dimension2 === 'string' ? ` × ${words(c.dimension2)}` : ''
      return d ? `${m} · ${tr('sug.by')} ${d}${d2}` : m
    }
  }
}

/** The live chart, full size, in an expanded card. Pointer events off: it is
 *  a preview, and the card's own buttons are the actions. */
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

function Thumb({ shape }: { shape: ReturnType<typeof thumbnail> }) {
  return (
    <span className="dl-sug__thumb" data-testid="suggestion-thumb" aria-hidden>
      {shape && (
        <svg width="64" height="36" viewBox="0 0 64 36">
          {shape.kind === 'line' ? (<>
            <path d={shape.area} className="dl-sug__thumb-area" />
            <path d={shape.d} className="dl-sug__thumb-line" />
          </>) : <path d={shape.d} className="dl-sug__thumb-bars" />}
        </svg>
      )}
    </span>
  )
}

export default function SuggestionsPane({ columns, analysis, onAdd, reportId, datasetId, pageWidgets, columnMeta }: {
  columns: DatasetColumn[]
  /** The author's column meaning (role, default summary): identifiers are
      never charted as measures, a salary is averaged. */
  columnMeta?: Record<string, ColumnMeta | undefined>
  analysis: { numeric?: { correlation?: Record<string, Record<string, number>> } } | null
  onAdd: (s: Suggestion) => void
  /** When set, the pane leads with insight-driven suggestions for this
      report: the insights engine's ranked findings mapped to widgets, with
      findings about columns the report's name/description mentions first. */
  reportId?: number
  /** When set, each card reads its own data: the takeaway headline, the
      thumbnail, the strength order, and the full live chart on expand. */
  datasetId?: number | null
  /** The charts already on the page: a suggestion that repeats one is folded
      away under "already on this page" rather than offered again. */
  pageWidgets?: Widget[]
}) {
  const [seed, setSeed] = useState(0)
  const tr = useT()
  const heuristics = useMemo(() => suggestWidgets(columns, analysis, seed, columnMeta ?? {}, tr), [columns, analysis, seed, columnMeta, tr])
  const [insightSugs, setInsightSugs] = useState<WidgetSuggestion[] | null>(null)
  useEffect(() => {
    if (!reportId) return
    suggestApi.forReport(reportId).then(setInsightSugs).catch(() => setInsightSugs(null))
  }, [reportId])

  const [filter, setFilter] = useState<'all' | SugFamily>('all')
  const [expanded, setExpanded] = useState<string | null>(null)
  const [added, setAdded] = useState<string[]>([])
  const [hidden, setHiddenState] = useState<string[]>(() => readHidden(reportId))
  const [showOnPage, setShowOnPage] = useState(false)
  const hide = (key: string) => {
    const next = [...hidden, key]
    setHiddenState(next)
    if (expanded === key) setExpanded(null)
    try { localStorage.setItem(HIDDEN_KEY(reportId), JSON.stringify(next)) } catch { /* a convenience */ }
  }

  const items: Item[] = useMemo(() => {
    const out: Item[] = []
    const seen = new Set<string>()
    // The same chart by identity, not by exact config: the panel's own
    // "Development leads with 61.4K" is the server's "Headcount by dept name"
    // (HR re-test 2026-10-02). The server's comes first and wins.
    const sigs = new Set<string>()
    const push = (it: Omit<Item, 'key'>) => {
      const key = `${it.widget_type}|${JSON.stringify(it.config)}`
      const sig = signature(it.widget_type, it.config)
      if (seen.has(key) || sigs.has(sig)) return
      seen.add(key)
      sigs.add(sig)
      out.push({ ...it, key })
    }
    for (const s of insightSugs ?? []) {
      push({ widget_type: s.widget_type, title: s.title, reason: s.reason, config: s.config,
        aligned: s.aligned, insightKind: s.kind, fromInsights: true,
        // in the reader's language when the server sent the sentence's key
        takeaway: takeawayText(tr, s) })
    }
    for (const s of heuristics) push({ ...s, fromInsights: false })
    return out
  }, [insightSugs, heuristics])

  // Each card's own rows: the headline, the thumbnail and the order come from them.
  const [rowsByKey, setRowsByKey] = useState<Record<string, unknown>>({})
  useEffect(() => {
    if (datasetId == null) return
    let alive = true
    for (const it of items) {
      if (rowsByKey[it.key] !== undefined) continue
      widgetDataApi.query(datasetId, it.config, [], it.widget_type, { reportId })
        .then((d: any) => { if (alive) setRowsByKey(m => ({ ...m, [it.key]: d?.rows ?? [] })) })
        .catch(() => { if (alive) setRowsByKey(m => ({ ...m, [it.key]: [] })) })
    }
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, datasetId, reportId])

  const onPageBySig = useMemo(() => {
    const m = new Map<string, Widget>()
    for (const w of pageWidgets ?? []) m.set(signature(w.widget_type, (w.config ?? {}) as Record<string, unknown>), w)
    return m
  }, [pageWidgets])

  type View = Item & { take: Takeaway | null; headline: string; family: SugFamily; strength: number;
    shape: ReturnType<typeof thumbnail>; onPage?: Widget }
  const views: View[] = items.map(it => {
    const rows = rowsByKey[it.key]
    const take = it.fromInsights ? null : takeaway(it.widget_type, it.config, rows)
    const family = familyOf(it.widget_type)
    // A headline number says its number on the card.
    const first = Array.isArray(rows) ? (rows as { value?: unknown }[])[0] : undefined
    const kpiValue = family === 'summary' && first && Number.isFinite(Number(first.value)) ? Number(first.value) : null
    const headline = kpiValue != null ? `${it.title}: ${Math.abs(kpiValue) >= 1000 ? Math.round(kpiValue).toLocaleString() : Number(kpiValue.toFixed(2)).toLocaleString()}`
      : it.fromInsights ? it.title : (take?.headline ?? cap(words(it.title)))
    return { ...it, take, headline, family,
      // Findings the insights engine ranked lead; then the strongest of the rest.
      strength: (it.fromInsights ? 2 : 0) + (it.aligned ? 1 : 0) + (take?.strength ?? 0),
      shape: thumbnail(it.widget_type, rows),
      onPage: added.includes(it.key) ? undefined : onPageBySig.get(signature(it.widget_type, it.config)) }
  })
  const live = views.filter(v => !v.onPage && !hidden.includes(v.key))
  const onPage = views.filter(v => v.onPage)
  const shown = live.filter(v => filter === 'all' || v.family === filter)
  const sections = FAMILIES.map(f => ({
    ...f, items: shown.filter(v => v.family === f.key).sort((a, b) => b.strength - a.strength),
  })).filter(s => s.items.length > 0)
    .sort((a, b) => b.items[0].strength - a.items[0].strength)

  const add = (v: View) => {
    setAdded(a => [...a, v.key])
    onAdd({ widget_type: v.widget_type, title: v.headline, reason: v.reason, config: labelled(v) })
  }
  const goTo = (w: Widget) => {
    const el = document.querySelector(`[data-widget-id="${w.id}"]`) as HTMLElement | null
    if (!el) return
    el.scrollIntoView?.({ block: 'center', behavior: 'smooth' })
    el.animate?.([
      { outline: '3px solid var(--accent)', outlineOffset: '2px' },
      { outline: '3px solid transparent', outlineOffset: '2px' },
    ], { duration: 2200, easing: 'ease-out' })
  }

  const n = live.length
  return (
    <div className="dl-sug">
      <div className="dl-sug__top">
        <div className="dl-sug__head">
          <div className="dl-sug__heading">
            <span className="dl-sug__title"><Lightbulb size={15} aria-hidden /> {tr('sug.title')}</span>
            <span className="dl-sug__summary">{tr('sug.summary', { n })}</span>
          </div>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setSeed(x => x + 1)}
            title={tr('sug.moreTitle')}>
            <RefreshCw size={12} aria-hidden /> {tr('sug.more')}
          </button>
        </div>
        <div className="dl-sug__chips" role="group" aria-label={tr('sug.chipsLabel')}>
          {[{ key: 'all' as const, label: 'sug.all' as MessageKey }, ...FAMILIES].map(f => {
            const count = f.key === 'all' ? live.length : live.filter(v => v.family === f.key).length
            const on = filter === f.key
            // A kind with nothing to offer takes no room (unless it is the one picked).
            if (count === 0 && f.key !== 'all' && !on) return null
            return (
              <button key={f.key} type="button" aria-pressed={on} disabled={count === 0 && f.key !== 'all'}
                className={`dl-sug__chip${on ? ' dl-sug__chip--on' : ''}`} onClick={() => setFilter(f.key)}>
                {f.key !== 'all' && <span className={`dl-sug__dot dl-sug__dot--${f.key}`} aria-hidden />}
                {tr(f.label)} <span className="dl-sug__chip-n">{count}</span>
              </button>
            )
          })}
        </div>
      </div>

      {items.length === 0 && (
        <p className="dl-sug__none">{tr('sug.noneAtAll')}</p>
      )}
      {items.length > 0 && sections.length === 0 && (
        <p className="dl-sug__none">{tr('sug.noneOfKind')}</p>
      )}

      {sections.map(sec => (
        <section key={sec.key} className="dl-sug__section" aria-label={tr(sec.label)}>
          <h3 className="dl-sug__sec-head">
            <span className={`dl-sug__dot dl-sug__dot--${sec.key}`} aria-hidden />
            {tr(sec.label)} <span className="dl-sug__chip-n">{sec.items.length}</span>
          </h3>
          <ul className="dl-sug__list">
            {sec.items.map((v, i) => {
              const open = expanded === v.key
              const isAdded = added.includes(v.key)
              return (
                <li key={v.key} data-testid={v.fromInsights ? `insight-suggestion-${v.insightKind}` : undefined}
                  className={`dl-sug__card dl-sug__card--${v.family}${open ? ' dl-sug__card--open' : ''}${v.aligned ? ' dl-sug__card--aligned' : ''}`}>
                  <div className="dl-sug__row">
                    <button type="button" className="dl-sug__main" aria-expanded={open}
                      onClick={() => setExpanded(open ? null : v.key)}>
                      <Thumb shape={v.shape} />
                      <span className="dl-sug__text">
                        <span className="dl-sug__name">
                          {v.aligned && <span title={tr('sug.matches')} className="dl-sug__star"><Sparkles size={11} aria-hidden /></span>}
                          <bdi>{v.headline}</bdi>
                        </span>
                        <span className="dl-sug__why" dir="auto">{(v.family !== 'summary' && v.takeaway) || subline(v, tr)}</span>
                      </span>
                    </button>
                    {isAdded ? (
                      <span className="dl-sug__added"><Check size={13} aria-hidden /> {tr('sug.added')}</span>
                    ) : (
                      <button type="button" className="btn btn-sm dl-sug__add" onClick={() => add(v)}
                        aria-label={tr('sug.addAria', { t: v.headline })} title={tr('sug.addToPage')}>
                        <Plus size={12} aria-hidden /> {tr('sug.add')}
                      </button>
                    )}
                  </div>
                  {open && (
                    <div className="dl-sug__more">
                      {datasetId != null && (
                        // Axes named; category names shortened and values
                        // written compactly, so long ones cannot squeeze the bars.
                        <SuggestionPreview datasetId={datasetId} widgetType={v.widget_type}
                          config={{ ...labelled(v), axis_tick_max_chars: 12, labels_compact: true }} idx={i} />
                      )}
                      <p className="dl-sug__detail" dir="auto">{v.take?.detail ?? v.reason}</p>
                      {v.takeaway && v.takeaway !== v.reason && (
                        <p className="dl-sug__detail" dir="auto" data-testid="suggestion-takeaway">
                          <strong>{tr('sug.dataShows')}</strong> {v.takeaway}
                        </p>
                      )}
                      <div className="dl-sug__actions">
                        {!isAdded && (
                          <button type="button" className="btn btn-primary btn-sm" onClick={() => add(v)}>
                            <Plus size={13} aria-hidden /> {tr('sug.addToPage')}
                          </button>
                        )}
                        <button type="button" className="btn btn-ghost btn-sm" onClick={() => hide(v.key)}>
                          <EyeOff size={13} aria-hidden /> {tr('sug.notUseful')}
                        </button>
                      </div>
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
        </section>
      ))}

      {onPage.length > 0 && (
        <div className="dl-sug__onpage">
          <button type="button" className="dl-sug__onpage-toggle" aria-expanded={showOnPage}
            onClick={() => setShowOnPage(o => !o)}>
            <ChevronRight size={14} aria-hidden className="dl-sug__chev flip-rtl" />
            {tr('sug.onPage', { n: onPage.length })}
          </button>
          {showOnPage && (
            <ul className="dl-sug__list">
              {onPage.map(v => (
                <li key={v.key} className="dl-sug__card dl-sug__card--onpage">
                  <div className="dl-sug__row">
                    <Thumb shape={v.shape} />
                    <span className="dl-sug__text">
                      <span className="dl-sug__name">{v.headline}</span>
                      <span className="dl-sug__why">{tr('sug.onPageAs', { t: v.onPage!.title || v.onPage!.widget_type })}</span>
                    </span>
                    <button type="button" className="dl-sug__goto" onClick={() => goTo(v.onPage!)}>
                      {tr('sug.goTo')} <ArrowUpRight size={12} aria-hidden className="flip-rtl" />
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
