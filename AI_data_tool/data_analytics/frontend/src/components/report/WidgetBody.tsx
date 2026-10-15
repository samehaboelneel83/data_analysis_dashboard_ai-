import { Lock } from 'lucide-react'
import { semanticAggregationWarning, nonAdditiveKind, SAFE_AGGREGATION } from '../../lib/semanticGuard'
import { CellLink, isWebAddress } from '../../lib/cellLink'
import PivotTable, { type PivotData } from './PivotTable'
import { Suspense, useEffect, useMemo, useState, useId } from 'react'
import { renderTextWithLinks } from '../../lib/inlineMarkup'
import { useDirection, widgetIsRtl } from '../../contexts/DirectionContext'
import { useT, type MessageKey, type TranslateFn } from '../../i18n'
import { MapLoading } from './geo/MapDataTable'
import type { CalcColumnFormat } from '../../services/api'
import type { Widget, WidgetType } from '../../types/report'
import type { RuleStyles } from '../../lib/displayRules'
import { fmtStr, formatValue, formatMeasure, formatMeasureCell, measureFormat, EmptyState, seriesColor } from './chartUtils'
import { CHART_RENDERERS } from './chartRenderers'
import LatticeRenderer from './chartRenderers/LatticeRenderer'
import AnimatedRenderer from './chartRenderers/AnimatedRenderer'
import type { BrushRange } from './chartRenderers/axisOptions'
import { useWindowedRows, WINDOW_THRESHOLD } from './useWindowedRows'
import { CustomVisual } from './CustomVisual'
import { seriesName } from './chartRenderers/axisOptions'
import { WidgetPlaceholder, missingRequiredRoles, missingWidgetOptions, familyOf } from './WidgetPlaceholder'
import { MeasuredChart } from './MeasuredChart'
import SlicerRange, { type RangeValue } from './SlicerRange'
import SlicerTree from './SlicerTree'
import HierPivot from './HierPivot'

// ─────────────────────────────────────────────────────────────────────────────
// WidgetBody — pure rendering, receives onClick callback
// ─────────────────────────────────────────────────────────────────────────────

/**
 * The type size a big single number can take without spilling out of its card.
 *
 * A KPI value is centred, so an oversized number overflows on BOTH sides and
 * the widget's own clipping eats the LEADING characters -- "$8,632,597" renders
 * as ",632,597", a wrong number shown with full confidence rather than an
 * obviously broken one. Stepping the size down by length keeps the default card
 * width honest, and the ellipsis at the call sites catches whatever is still
 * too long by trimming the END, where a cut is visible.
 */
export const fitFontSize = (text: string, max: number): number => {
  const n = text.length
  if (n <= 8) return max
  if (n <= 11) return Math.round(max * 0.78)
  if (n <= 15) return Math.round(max * 0.62)
  if (n <= 20) return Math.round(max * 0.5)
  return Math.round(max * 0.4)
}

/**
 * The KPI/card figure size, fitted to the WIDGET as well as to the text.
 * fitFontSize only knows how long the string is, so a nine-character
 * "$ 8,632,597" was set at 28px whether the tile was 400px wide or 150px --
 * and in the narrow tile it printed "$ 8,632,…". Container query units let
 * the browser cap it by the tile's own width (≈0.62em per tabular digit in
 * Inter), never below a legible 14px. The ellipsis stays as the last resort.
 */
export const fitFigureSize = (text: string, max: number): string => {
  const chars = Math.max(text.length, 1)
  return `max(14px, min(${fitFontSize(text, max)}px, calc(100cqi / ${(chars * 0.62).toFixed(2)})))`
}

function SlicerList({ rows, rtl, checked, onToggle, searchable }: {
  rows: { name: unknown; value?: unknown }[]
  rtl: boolean
  checked?: Set<unknown>
  onToggle?: (v: unknown) => void
  searchable: boolean
}) {
  const tw = useT()
  const [query, setQuery] = useState('')
  const visible = searchable && query
    ? rows.filter(r => String(r.name).toLowerCase().includes(query.toLowerCase()))
    : rows
  return (
    <div dir={rtl ? 'rtl' : undefined} style={{ overflow: 'auto', height: '100%', padding: 6 }}>
      {searchable && (
        <input value={query} onChange={e => setQuery(e.target.value)} placeholder={tw('wb.searchValues')}
          aria-label={tw('wb.searchSlicer')}
          style={{ width: '100%', fontSize: 12, marginBottom: 6 }} />
      )}
      {visible.map((row, i) => (
        <label key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '4px 2px', fontSize: 12, cursor: 'pointer' }}>
          <input type="checkbox" checked={!!checked?.has(row.name)} onChange={() => onToggle?.(row.name)} />
          <span style={{ flex: 1 }}>{String(row.name)}</span>
          {row.value !== undefined && <span style={{ fontFamily: 'var(--mono)', color: 'var(--muted)' }}>{String(row.value)}</span>}
        </label>
      ))}
    </div>
  )
}

/** An image widget that says so when its picture does not load: a broken
 *  URL used to leave a blank 0x0 box with nothing to tell the author why. */
function ImageWidget({ url, alt, fit }: { url: string; alt: string; fit?: string }) {
  const t = useT()
  const [failed, setFailed] = useState(false)
  useEffect(() => setFailed(false), [url])
  if (failed) return <EmptyState msg={t('widget.image.failed')} />
  return <img src={url} alt={alt} onError={() => setFailed(true)}
    style={{ width: '100%', height: '100%', objectFit: (fit || 'contain') as any }} />
}

/** A widget's fetch error, in the reader's language where the code says what
 *  it is. The server's sentence is English; for the two source states it is
 *  replaced (the source's name carried over), for anything else it is shown
 *  as written -- laid out by its OWN direction, so an English sentence in the
 *  Arabic layout no longer reads ".Refresh in a moment" (HR re-test). */
function FetchErrorState({ err, onRetry }: { err: { detail: string; code?: string }; onRetry?: () => void }) {
  const t = useT()
  // Column security (QA E-12 / SEC-02): say it is restricted, never which
  // column, and offer no retry -- trying again cannot change a role.
  if (err.code === 'forbidden_column') {
    return <EmptyState msg={t('widget.err.restricted')} icon={<Lock size={20} aria-hidden />} />
  }
  const name = /'([^']+)'/.exec(err.detail ?? '')?.[1] ?? ''
  const msg = err.code === 'source_busy' ? t('widget.err.busy', { name })
    : err.code === 'source_unavailable' ? t('widget.err.unreachable', { name })
    : err.detail
  const retry = (err.code === 'source_unavailable' || err.code === 'source_busy' || err.code === 'quota') && onRetry
  return <EmptyState msg={msg} action={retry ? { label: t('widget.err.retry'), onClick: onRetry! } : undefined} />
}

/** B-36: a KPI's caption in words ("Distinct shipment id", "Average fee"),
 *  never the raw "countd(shipment_id)" an axis title uses. */
const KPI_CAPTION: Record<string, MessageKey> = {
  count: 'widget.kpiCap.count', countd: 'widget.kpiCap.countd', avg: 'widget.kpiCap.avg', mean: 'widget.kpiCap.avg',
  median: 'widget.kpiCap.median', min: 'widget.kpiCap.min', max: 'widget.kpiCap.max',
}
function kpiCaption(cfg: { measure?: unknown; aggregation?: unknown }, t: TranslateFn): string {
  const key = KPI_CAPTION[String(cfg.aggregation ?? '').toLowerCase()]
  if (!key) return seriesName(cfg as never)
  const m = String(cfg.measure ?? '').replace(/_/g, ' ').trim()
  const text = t(key, { m })
  return text.charAt(0).toUpperCase() + text.slice(1)
}

export function WidgetBody({ widget, data, fetchError, onRetry, localSelected, onClickPoint, broadcasts, allFormats, checked, onToggleSlicerValue, onButtonClick, ruleStyles, parameters, geography, textFilter, onSubmitTextFilter, rangeFilter, onSubmitRangeFilter, treePaths, onTreeChange, gridOpen, onToggleGridBranch, onGridClick, onAssignData, onBrushChange, brushNonce, onAnimationFrame, onApplyFix, onLoadMore, loadingMore }:
  { widget: Widget; data: any; fetchError?: { detail: string; code?: string } | null; onRetry?: () => void; localSelected: unknown; onClickPoint: (v: unknown) => void; broadcasts: boolean; allFormats?: Record<string, CalcColumnFormat | undefined>; checked?: Set<unknown>; onToggleSlicerValue?: (v: unknown) => void; onButtonClick?: () => void; ruleStyles?: RuleStyles; parameters?: Record<string, unknown>; geography?: Record<string, number>;
    textFilter?: string; onSubmitTextFilter?: (value: string, column: string) => void
    /** A range slicer's current bounds, and how it applies new ones. */
    rangeFilter?: RangeValue | null; onSubmitRangeFilter?: (range: RangeValue | null, column: string) => void
    /** A hierarchy slicer (hierarchy plan, step 2): the ticked paths, and where changes go. */
    treePaths?: string[][] | null; onTreeChange?: (paths: string[][] | null) => void
    /** A hierarchical crosstab (step 3): open branches, toggling them, a value clicked. */
    gridOpen?: { rows: string[]; cols: string[] }
    onToggleGridBranch?: (axis: 'rows' | 'cols', key: string) => void
    onGridClick?: (rowPath: string[], colPath: string[]) => void
    /** Edit mode only: select this widget and open its Data roles. */
    onAssignData?: () => void
    /** Overview-axis zoom reports; bumping brushNonce remounts the chart to reset it. */
    onBrushChange?: (range: BrushRange | null) => void
    brushNonce?: number
    onAnimationFrame?: (label: string | null) => void ; onApplyFix?: (patch: Record<string, unknown>, label: string) => void
    /** A paged raw table: fetch the next page (the reader scrolled near the end). */
    onLoadMore?: () => void; loadingMore?: boolean }) {
  const tw = useT()

  const wt = widget.widget_type
  const cfg = widget.config as any
  const { rtl: appRtl } = useDirection()
  // A stored `rtl: false` means "never turned on", not "force LTR" --
  // WidgetConfigPanel writes the key into every saved config. See
  // widgetIsRtl for why reading it as a plain boolean would make the
  // app-wide switch do nothing.
  const rtl = widgetIsRtl(cfg.rtl, appRtl)

  // Format for the value column: use measure if set, otherwise fall back to dimension
  // (many widgets aggregate the dimension column directly with no separate measure)
  // C-02 / F-12: the format of the AGGREGATED value -- a count of a currency
  // column is a plain count (never in the measure's currency), a share is a percent.
  const measureFmt = measureFormat(allFormats?.[cfg.measure] ?? allFormats?.[cfg.dimension], cfg.aggregation)
  const measure2Fmt = measureFormat(allFormats?.[cfg.measure2], cfg.aggregation2)

  if (wt === 'text') {
    // Substitute resolved {{agg(column)}} values before link rendering. An unresolved
    // placeholder (still loading, or a bad column) shows an em dash rather than the
    // raw syntax -- prose with visible template braces reads as broken.
    let content = String(cfg.content || 'Text block')
    const values = (data?.type === 'text_values' ? data.values : {}) as Record<string, unknown>
    // {{@name}} embeds the current value of a report parameter -- the same value
    // the viewer set in the parameter bar, so prose like "showing orders above
    // {{@threshold}}" always matches what the widgets are actually filtered by.
    content = content.replace(/\{\{\s*@([A-Za-z_][A-Za-z0-9_]*)\s*\}\}/g,
      (_, name: string) => {
        const v = parameters?.[name]
        return v != null && v !== '' ? String(v) : '—'
      })
    // Aggregate placeholders render as their own spans (not a string splice)
    // so a display rule matched server-side can colour the number in prose the
    // same way it colours the mark in the chart beside it. Plain segments
    // still go through the link renderer.
    const valueStyles = (data?.type === 'text_values'
      ? (data.value_styles ?? {}) : {}) as Record<string, { fill?: string; text?: string }>
    const parts = content.split(/(\{\{\s*(?:sum|avg|min|max|count|median)\(\s*[^)\s]+\s*\)\s*\}\})/gi)
    const rendered = parts.map((part, i) => {
      const m = /^\{\{\s*(sum|avg|min|max|count|median)\(\s*([^)\s]+)\s*\)\s*\}\}$/i.exec(part)
      if (!m) return <span key={i}>{renderTextWithLinks(part)}</span>
      const key = `${m[1].toLowerCase()}(${m[2]})`
      const v = values[key]
      const text = typeof v === 'number' && Number.isFinite(v) ? fmtStr(v, allFormats?.[m[2]]) : '—'
      const st = valueStyles[key]
      return st
        ? <span key={i} data-testid="text-rule-styled" style={{ color: st.fill ?? st.text, fontWeight: 600 }}>{text}</span>
        : <span key={i}>{text}</span>
    })
    return (
      // dir="auto": Arabic text reads right-to-left even when the app is in English.
      <div dir={rtl ? 'rtl' : 'auto'} style={{ padding: 12, fontSize: 13, whiteSpace: 'pre-wrap' }}>{rendered}</div>
    )
  }
  if (wt === 'button') return (
    <div dir={rtl ? 'rtl' : undefined} style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <button className="btn btn-primary" onClick={e => { e.stopPropagation(); onButtonClick?.() }}>{cfg.label || 'Button'}</button>
    </div>
  )
  if (wt === 'image') return cfg.url ? (
    <ImageWidget url={cfg.url} alt={cfg.alt || ''} fit={cfg.fit} />
  ) : (
    <EmptyState msg="No image URL set" />
  )
  if (wt === 'web_content') {
    // Only http(s) is embeddable; anything else (javascript:, data:, blank) is a
    // placeholder, never a src -- that keeps an author-typed URL from becoming an
    // injection vector. The frame is sandboxed to the minimum a normal embed needs;
    // sites that forbid framing (X-Frame-Options / CSP frame-ancestors) simply won't
    // load, which is the remote site's choice, not a bug here.
    const url = typeof cfg.url === 'string' ? cfg.url.trim() : ''
    const embeddable = /^https?:\/\//i.test(url)
    return embeddable ? (
      <iframe
        title={widget.title || 'Web content'}
        src={url}
        style={{ width: '100%', height: '100%', border: 'none', display: 'block' }}
        sandbox="allow-scripts allow-same-origin allow-popups allow-forms allow-presentation"
        referrerPolicy="no-referrer"
        loading="lazy"
      />
    ) : (
      <EmptyState msg={url ? 'Web content needs an http(s) URL' : 'No URL set'} />
    )
  }
  if (wt === 'script') {
    // SAS's Job content object. What the code may do is decided server-side
    // (services/script_tile.py: a subprocess, a scrubbed environment, a
    // timeout, admin-only authoring); this end shows what came back. The ERROR
    // is the most important thing on screen, because the person looking at a
    // broken script tile is usually the person who wrote it.
    const payload = (data ?? {}) as {
      columns?: string[]; rows?: unknown[][]; stdout?: string
      truncated?: boolean; row_count?: number; error?: string | null
      input_truncated?: boolean; rows_in?: number
    }
    const columns = payload.columns ?? []
    const rows = payload.rows ?? []
    return (
      <div data-testid="script-tile" style={{ height: '100%', display: 'flex',
        flexDirection: 'column', minHeight: 0, overflow: 'hidden' }}>
        {payload.error ? (
          <div role="alert" style={{ padding: 10, margin: 8, fontSize: 11.5,
            fontFamily: 'var(--mono)', whiteSpace: 'pre-wrap',
            color: 'var(--danger)', background: 'var(--surface2)',
            border: '1px solid var(--border)', borderRadius: 6 }}>
            {payload.error}
          </div>
        ) : (
          <div style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
            <table style={{ fontSize: 12, width: '100%' }}>
              <thead><tr>{columns.map(c => (
                <th key={c} style={{ whiteSpace: 'nowrap' }}>{c}</th>))}</tr></thead>
              <tbody>
                {rows.map((row, i) => (
                  <tr key={i}>{(row as unknown[]).map((v, j) => (
                    <td key={j} style={{ fontFamily: typeof v === 'number' ? 'var(--mono)' : undefined }}>
                      {v == null ? <span style={{ color: 'var(--muted)' }}>—</span>
                        : typeof v === 'number' ? v.toLocaleString() : isWebAddress(v) ? <CellLink url={v} /> : String(v)}
                    </td>))}</tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {payload.truncated && (
          <div style={{ padding: '4px 10px', fontSize: 10.5, color: 'var(--muted)',
            borderTop: '1px solid var(--border)' }}>
            {payload.row_count
              ? tw('wb.firstOf', { n: rows.length.toLocaleString(), total: payload.row_count.toLocaleString() })
              : tw('wb.first', { n: rows.length.toLocaleString() })}
          </div>
        )}
        {payload.input_truncated && (
          <div style={{ padding: '4px 10px', fontSize: 10.5, color: 'var(--warning, var(--muted))',
            borderTop: '1px solid var(--border)' }}>
            {tw('wb.scriptSaw', { n: (payload.rows_in ?? 0).toLocaleString() })}
          </div>
        )}
        {payload.stdout ? (
          <pre data-testid="script-stdout" style={{ margin: 0, padding: '6px 10px',
            maxHeight: 90, overflow: 'auto', fontSize: 10.5, color: 'var(--muted)',
            borderTop: '1px solid var(--border)', whiteSpace: 'pre-wrap' }}>
            {payload.stdout}
          </pre>
        ) : null}
      </div>
    )
  }
  if (wt === 'custom_visual') {
    const url = typeof cfg.url === 'string' ? cfg.url.trim() : ''
    // `handleClick` is the same gate a bar click goes through: it checks
    // `canBroadcast` and supplies the widget's own dimension, so a custom
    // visual can select but cannot exceed a click.
    // `onClickPoint` is `handleClick`, the same gate a bar click goes through:
    // it supplies the widget's own dimension and re-checks `canBroadcast`.
    // `broadcasts` gates it here too, so a page set to manual interactions
    // hands the frame no handler at all and it never starts listening.
    return <CustomVisual url={url} title={widget.title || 'Custom visual'} data={data}
      widgetType={wt} onSelect={broadcasts ? onClickPoint : undefined} />
  }
  if (wt === 'shape') {
    const shape = cfg.shape || 'rectangle'
    return (
      <div style={{ height: '100%', padding: 8, display: 'flex' }}>
        <div data-testid="shape-render" style={{
          flex: 1,
          background: cfg.fill || 'transparent',
          border: `${cfg.strokeWidth ?? 2}px solid ${cfg.stroke || '#6c8fff'}`,
          borderRadius: shape === 'circle' ? '50%' : shape === 'rounded' ? 12 : 0,
          ...(shape === 'line' ? { border: 'none', borderTop: `${cfg.strokeWidth ?? 2}px solid ${cfg.stroke || '#6c8fff'}`, alignSelf: 'center' } : {}),
        }} />
      </div>
    )
  }

  // A refused request is not an unconfigured widget. Showing the reason -- a
  // row cap, a governed column, a dead connection -- is the difference between
  // an author who can act and one who edits a correct config looking for a
  // fault that is not there.
  // A widget still missing a required role is not broken and not empty: it is
  // unfinished. Draw a sample of its own chart family and say what it needs,
  // instead of a blank frame (or the server's refusal of an incomplete query).
  // (Some shapers answer an incomplete config with an empty result rather than
  // a refusal, so "nothing to draw" -- not only "no response" -- counts.)
  {
    const missing = [...missingRequiredRoles(widget), ...missingWidgetOptions(widget)]
    // Same shapes WidgetRenderer counts for its row metric: many results carry
    // no `rows` key at all (matrix, cells, bars, links, forecast, value).
    const drawable = data?.rows?.length || data?.matrix?.length || data?.cells?.length
      || data?.bars?.length || data?.links?.length || data?.forecast?.length
      || data?.points?.length || data?.series?.length || (data?.value != null ? 1 : 0)
      // A contour answers with a density `grid`, a tree/network with `nodes` (C-03).
      || data?.grid?.length || data?.nodes?.length
    const nothingToDraw = !data || !drawable
    // A chart with no dimension is answered by the shaper's raw-table branch
    // (every column, row by row) -- and a line renderer then draws that as a
    // meaningless squiggle. A CHART receiving a raw table is unfinished; a
    // table receiving one is working exactly as designed.
    const rawTableForChart = data?.type === 'table' && familyOf(widget.widget_type) !== 'table'
    // C-14: likewise a measure with no dimension is answered as one scalar
    // row, which a pie drew as a single solid disc. Only a KPI-like widget
    // (or a table) is finished with a single number.
    const scalarForChart = data?.type === 'scalar' && !['table', 'kpi'].includes(familyOf(widget.widget_type))
    if (missing.length && (nothingToDraw || rawTableForChart || scalarForChart)) {
      return <WidgetPlaceholder widget={widget} missing={missing} onAssignData={onAssignData} />
    }
  }
  if (!data && fetchError) {
    // A refused aggregation (a summed year, an averaged id) comes with its
    // fix: one click switches to the aggregation that means something.
    const fix = fetchError.code === 'semantic_veto' && onApplyFix ? semanticFix(widget.config as Record<string, unknown>, tw) : null
    if (fix) {
      return <EmptyState msg={fetchError.detail}
        action={{ label: fix.label, onClick: () => onApplyFix!(fix.patch, fix.label) }} />
    }
    return <FetchErrorState err={fetchError} onRetry={onRetry} />
  }
  if (!data) return <EmptyState msg="Configure widget to see data" />
  // The second channel: a 200 whose body says it failed. A measure that
  // could not be evaluated arrives this way, and until the widget read it
  // the chart renderer got empty rows and drew nothing -- the message lost.
  // A measure that failed to evaluate: the evaluator's reason is for whoever
  // can fix the formula (edit mode); a reader gets a plain sentence (QA E-12).
  if (data?.type === 'error') {
    return <EmptyState msg={data.code === 'measure_error' && !onAssignData
      ? tw('widget.err.measure') : String(data.message || 'This widget could not be computed')} />
  }

  if (data?.type === 'hier_pivot') {
    return <HierPivot data={data} open={gridOpen ?? { rows: [], cols: [] }} rtl={rtl}
      onToggle={onToggleGridBranch} onCellClick={onGridClick} />
  }

  // Slicer
  if (wt === 'slicer') {
    const rows: any[] = data.rows ?? []
    // Control variety, SAS's cardinality rule when on auto: buttons under 5,
    // a checkbox list to 10, a search-filtered list beyond.
    //
    // The search threshold was 40, which was too generous by far: scanning a
    // 30-item checkbox list for one value means reading all thirty, and the
    // list is only as tall as the widget so most of it is scrolled out of
    // sight. Ten is about where a reader stops seeing a set and starts
    // hunting -- and search only ADDS a filter box, so enabling it early costs
    // a reader nothing while a wall of checkboxes costs them the value.
    const mode = (cfg.slicer_mode as string) || 'auto'
    // `auto` never resolves to text: a reader who CAN see their options should
    // be shown them, and a control that silently stopped listing reads as
    // broken rather than deliberate. Text is always a deliberate choice.
    // A range comes from the server: chosen, or picked by `auto` for a number
    // column with many values. It carries bounds, not a value list.
    if (data?.type === 'slicer_tree') {
      return <SlicerTree data={data} paths={treePaths ?? null} rtl={rtl} onChange={onTreeChange} />
    }
    if (data?.type === 'slicer_range') {
      return <SlicerRange data={data} value={rangeFilter ?? null} rtl={rtl} onApply={onSubmitRangeFilter} />
    }
    const effective = mode !== 'auto' ? mode
      : rows.length < 5 ? 'buttons' : rows.length <= 10 ? 'list' : 'search'
    if (effective === 'text') {
      // The control for a column whose value list is useless -- Customer ID
      // with 748k distinct values. The server returns no rows for this mode at
      // all, so there is nothing here to list: the reader types the value they
      // already know.
      const col = String(cfg.dimension ?? cfg.column ?? data?.column ?? '')
      return (
        <div dir={rtl ? 'rtl' : undefined} style={{ padding: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
          <input type="text" aria-label={tw('wb.filterBy', { c: col })} defaultValue={textFilter}
            placeholder={col ? tw('wb.typeA', { c: col }) : tw('wb.typeValue')}
            onKeyDown={e => {
              if (e.key !== 'Enter') return
              onSubmitTextFilter?.((e.target as HTMLInputElement).value.trim(), col)
            }}
            style={{ width: '100%', fontSize: 12, padding: '5px 8px',
              border: '1px solid var(--border)', borderRadius: 6,
              background: 'var(--surface)', color: 'var(--text)' }} />
          <span style={{ fontSize: 10, color: 'var(--muted)' }}>
            {tw('wb.enterToFilter')}
          </span>
        </div>
      )
    }
    if (effective === 'buttons') {
      return (
        <div dir={rtl ? 'rtl' : undefined} style={{ display: 'flex', flexWrap: 'wrap', gap: 6, padding: 8, alignContent: 'flex-start', overflow: 'auto', height: '100%' }}>
          {rows.map((row, i) => {
            const on = !!checked?.has(row.name)
            return (
              <button key={i} onClick={e => { e.stopPropagation(); onToggleSlicerValue?.(row.name) }}
                aria-pressed={on} data-slicer-button
                style={{ padding: '5px 12px', fontSize: 12, borderRadius: 6, cursor: 'pointer',
                  border: '1px solid ' + (on ? 'var(--accent)' : 'var(--border)'),
                  background: on ? 'var(--accent)' : 'var(--surface2)', color: on ? 'var(--mc-accent-fg)' : 'var(--text)' }}>
                {row.name}
              </button>
            )
          })}
        </div>
      )
    }
    if (effective === 'dropdown') {
      const selected = rows.filter(r => checked?.has(r.name)).map(r => r.name)
      return (
        <div dir={rtl ? 'rtl' : undefined} style={{ padding: 8 }}>
          <select multiple aria-label={tw('wb.slicerValues')} value={selected.map(String)}
            onChange={e => {
              const next = new Set([...e.target.selectedOptions].map(o => o.value))
              for (const r of rows) {
                const has = !!checked?.has(r.name)
                if (has !== next.has(String(r.name))) onToggleSlicerValue?.(r.name)
              }
            }}
            style={{ width: '100%', height: '100%', minHeight: 60, fontSize: 12 }}>
            {rows.map((row, i) => <option key={i} value={String(row.name)}>{row.name}</option>)}
          </select>
        </div>
      )
    }
    return <SlicerList rows={rows} rtl={rtl} checked={checked}
      onToggle={onToggleSlicerValue} searchable={effective === 'search'} />
  }

  // KPI
  if (wt === 'kpi') {
    const first = data.rows?.[0]
    const val = (first && typeof first === 'object' && !Array.isArray(first))
      ? (first.value ?? '—')
      : (Array.isArray(first) ? first[first.length - 1] : '—')
    const kpiIcon = ruleStyles?.rows?.[0]?.icon
    // A level's change over the period (`change_over`, server period_change.py):
    // the percent is the number; both ends, in the column's own format, beneath.
    const change = (data as { change?: { pct: number; from: unknown; to: unknown; first: unknown; last: unknown } }).change
    const kpiText = change ? `${change.pct > 0 ? '+' : ''}${change.pct.toFixed(1)}%` : fmtStr(val, measureFmt)
    // Its recent history, when the widget asks for one (`sparkline_date`): the
    // change of the last complete period against the one before, and the
    // shape of the periods before that (server: widget_data.kpi_trend).
    const trend = (data as { trend?: KpiTrend }).trend
    const pct = trend && typeof trend.change_pct === 'number' ? trend.change_pct : null
    const up = pct != null && pct > 0, flat = pct != null && Math.abs(pct) < 0.05
    // Which way is good is the column's stored direction; with none, no colour.
    const good = cfg.trend_good === 'up' ? up : cfg.trend_good === 'down' ? !up : null
    const trendColor = flat || good == null ? 'var(--muted)' : good ? 'var(--ok, #16a34a)' : 'var(--danger, #dc2626)'
    // With a history the card is laid out to be read at a glance: the number
    // at the start, its change as a pill at the end, and the history as a
    // filled line across the whole width underneath. Without one it stays
    // centred, as it always was.
    const withTrend = !!trend && trend.series.length >= 2
    const pill = pct != null && (
      <span data-testid="kpi-change" dir="ltr"
        // A pill tinted with its own colour: the change is read before the line beside it.
        style={{ fontSize: 12, fontWeight: 600, color: trendColor, fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap', flex: '0 0 auto',
          padding: '2px 8px', borderRadius: 999, background: `color-mix(in srgb, ${trendColor} 14%, transparent)` }}>
        {flat ? '→' : up ? '▲' : '▼'} {Math.abs(pct).toFixed(1)}%
      </span>
    )
    return (
      // `safe center`: when the card is shorter than its content, the overflow
      // goes below, never above -- a plain `center` cut the top of the number off
      // on every KPI with a trend line (persona test 2026-10-12).
      <div dir={rtl ? 'rtl' : undefined} style={{ height: '100%', display: 'flex', flexDirection: 'column', alignItems: withTrend ? 'stretch' : 'center', justifyContent: 'safe center', gap: 4, padding: withTrend ? '2px 12px 0' : '0 10px', minWidth: 0, containerType: 'inline-size' }}>
        {/* In a narrow card the change drops under the number instead of cutting it short. */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: withTrend ? 'space-between' : 'center', gap: withTrend ? '2px 8px' : 8, maxWidth: '100%', minWidth: 0, flexWrap: withTrend ? 'wrap' : undefined }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
          {kpiIcon && <span aria-hidden="true" style={{ fontSize: 28, flex: '0 0 auto' }}>{kpiIcon}</span>}
          <div title={kpiText}
            // The dashboard's style may set the headline number's size (lib/dashboardStyle); else it is fitted to the text.
            style={{ fontSize: `var(--dl-s-number-size, ${fitFigureSize(kpiText, 36)})`, fontWeight: 650, fontVariantNumeric: 'tabular-nums', letterSpacing: '-.02em', color: ruleStyles?.rows?.[0]?.fill ?? 'var(--accent)',
              minWidth: 0, maxWidth: '100%', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', lineHeight: 1.15 }}>
            {kpiText}
          </div>
          </div>
          {withTrend && pill}
        </div>
        <div style={{ fontSize: 12, color: 'var(--muted)', maxWidth: '100%', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', textAlign: withTrend ? 'start' : 'center' }}>
          {/* A count or an average is not the column itself: "Records" read
              3,576 over the subtitle RATED_AMOUNT (live QA 2026-09-28). A sum
              keeps the column's name, as it always has. */}
          {/* A caption written for the reader (the guided setup's "why")
              instead of "avg(is_late_pct)". */}
          {typeof cfg.caption === 'string' && cfg.caption.trim() ? cfg.caption
            : cfg.measure && cfg.aggregation && String(cfg.aggregation).toLowerCase() !== 'sum'
              ? kpiCaption(cfg, tw) : (cfg.measure || cfg.dimension || 'Value')}
        </div>
        {change && (
          <div data-testid="kpi-period-change" dir="ltr" style={{ fontSize: 11, color: 'var(--muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {fmtStr(change.from, measureFmt)} → {fmtStr(change.to, measureFmt)} ({String(change.first).slice(0, 10)} – {String(change.last).slice(0, 10)})
          </div>
        )}
        {trend && withTrend && (
          <div data-testid="kpi-trend" style={{ flex: '1 1 auto', minHeight: 0, maxHeight: 72, display: 'flex', flexDirection: 'column', minWidth: 0, margin: '0 -12px' }}
            title={`${trend.period}: ${fmtStr(trend.current, measureFmt)} · ${trend.previous_period}: ${fmtStr(trend.previous, measureFmt)}`}>
            <Sparkline values={trend.series.map(p => p.value)} fluid filled color={seriesColor(Number(widget.id) || 0)} />
          </div>
        )}
        {withTrend && (
          <div style={{ fontSize: 11, color: 'var(--muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {trend!.period}
          </div>
        )}
        {/* Against the target its author stored (server: widget_data.kpi_target). */}
        {(() => {
          const tg = (data as { target?: KpiTarget }).target
          if (!tg) return null
          if (!tg.applies) {
            return <div data-testid="kpi-target" style={{ fontSize: 10.5, color: 'var(--muted)', textAlign: 'center' }}>{tg.reason}</div>
          }
          const pctOf = typeof tg.pct === 'number' ? tg.pct : null
          const tone = tg.met ? 'var(--ok, #16a34a)' : 'var(--muted)'
          return (
            <div data-testid="kpi-target" data-met={tg.met ? 'yes' : 'no'} style={{ width: 'min(180px, 90%)' }}
              title={tg.label ? `${tg.label}: ${fmtStr(tg.against, measureFmt)}` : undefined}>
              <div dir="ltr" style={{ fontSize: 11, color: 'var(--muted)', textAlign: 'center', whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }}>
                {pctOf != null && <b style={{ color: tone }}>{pctOf.toFixed(0)}%</b>} {tw('wb.of')} {fmtStr(tg.value, measureFmt)}
                {tg.period ? ` · ${tg.label ?? tg.period}` : ''}
              </div>
              <div aria-hidden="true" style={{ height: 4, borderRadius: 2, background: 'var(--surface2)', marginTop: 2, overflow: 'hidden' }}>
                <div style={{ width: `${Math.max(0, Math.min(pctOf ?? 0, 100))}%`, height: '100%', background: tone }} />
              </div>
            </div>
          )
        })()}
        {/* Against the same period a year before -- beside, not instead of,
            the change on the previous period. Same rule for its colour. */}
        {trend?.year_ago && typeof trend.year_ago.change_pct === 'number' && (() => {
          const y = trend.year_ago!.change_pct as number
          const yUp = y > 0, yFlat = Math.abs(y) < 0.05
          const yGood = cfg.trend_good === 'up' ? yUp : cfg.trend_good === 'down' ? !yUp : null
          return (
            <div data-testid="kpi-year-ago" dir="ltr"
              title={`${trend.year_ago!.period}: ${fmtStr(trend.year_ago!.value, measureFmt)}`}
              style={{ fontSize: 11, color: 'var(--muted)', whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }}>
              <span style={{ fontWeight: 600, color: yFlat || yGood == null ? 'var(--muted)' : yGood ? 'var(--ok, #16a34a)' : 'var(--danger, #dc2626)' }}>
                {yFlat ? '→' : yUp ? '▲' : '▼'} {Math.abs(y).toFixed(1)}%
              </span>{' '}{tw('wb.vs')} {trend.year_ago!.period}
            </div>
          )
        })()}
      </div>
    )
  }

  // Card / multi-row card
  if (wt === 'card') {
    const rows: any[] = data.rows ?? []
    return (
      // Focusable: a card with more figures than its tile scrolls (E10).
      // C-13: a SIZE container, so each figure is capped by the tile's height
      // too (cqb): three rows at 24px plus labels overflowed a short tile.
      <div dir={rtl ? 'rtl' : undefined} tabIndex={0} role="region" aria-label={tw('wb.values')}
        style={{ height: '100%', overflow: 'auto', display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 10, padding: 8, containerType: 'size' }}>
        {rows.map((row, i) => (
          <div key={i} style={{ textAlign: 'center', minWidth: 0 }}>
            <div title={formatMeasure(row.value, allFormats?.[row.name], cfg.aggregation)}
              style={{ fontSize: `min(${fitFigureSize(formatMeasure(row.value, allFormats?.[row.name], cfg.aggregation), 24)}, calc(100cqb / ${(Math.max(rows.length, 1) * 2.2).toFixed(1)}))`, fontWeight: 650, fontVariantNumeric: 'tabular-nums', letterSpacing: '-.02em', color: ruleStyles?.rows?.[i]?.fill ?? 'var(--accent)',
                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', lineHeight: 1.15 }}>
              {formatMeasure(row.value, allFormats?.[row.name], cfg.aggregation)}
            </div>
            <div style={{ fontSize: 11.5, color: 'var(--muted)' }}>{row.name}</div>
          </div>
        ))}
      </div>
    )
  }

  // A crosstab with more than one field on Rows, Columns or Measures: the
  // nested pivot (backend services/pivot.py).
  if ((wt === 'crosstab' || wt === 'matrix') && data?.type === 'pivot') {
    return <PivotTable data={data as PivotData} rtl={rtl} formats={allFormats} />
  }

  // Table / Crosstab / Matrix (a labeled alias of crosstab — same pivoted-row shaper and layout)
  if (wt === 'table' || wt === 'crosstab' || wt === 'matrix') {
    const rawRows: any[] = data.rows ?? []
    // Rows are arrays (raw table/crosstab) or objects (grouped series) — normalise to arrays.
    const isObjRows = rawRows.length > 0 && !Array.isArray(rawRows[0])
    const cols: string[] = isObjRows
      ? Object.keys(rawRows[0])
      : (data.columns ?? [])
    const rows: any[][] = isObjRows
      ? rawRows.map((r: any) => cols.map(c => r[c]))
      : rawRows
    return (
      <WindowedTable rtl={rtl} cfg={cfg} data={data} cols={cols} rows={rows}
        onLoadMore={onLoadMore} loadingMore={loadingMore}
        ruleStyles={ruleStyles} allFormats={allFormats} broadcasts={broadcasts}
        onClickPoint={onClickPoint} grouped={isObjRows && cols.includes('name') && cols.includes('value')} />
    )
  }

  // List
  if (wt === 'list') {
    return (
      <WindowedList rtl={rtl} rows={data.rows ?? []} ruleStyles={ruleStyles}
        localSelected={localSelected} broadcasts={broadcasts}
        onClickPoint={onClickPoint} measureFmt={measureFmt} />
    )
  }

  const rows = data.rows ?? []

  // Accessible table alternative: any series-shaped chart can render as its data
  // table instead. The rows are the SAME shaped result the chart draws, so the two
  // presentations can never disagree -- and a screen-reader user gets real cells
  // rather than an SVG description.
  if ((widget.config as { show_as_table?: boolean }).show_as_table
      && Array.isArray(data?.rows) && data.rows.length && typeof data.rows[0] === 'object'
      && 'name' in data.rows[0]) {
    return (
      <div style={{ overflow: 'auto', height: '100%', padding: 4 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border)' }}>
              <th style={{ textAlign: 'start', padding: '4px 8px' }}>{cfg.dimension ?? 'name'}</th>
              <th style={{ textAlign: 'end', padding: '4px 8px' }}>{seriesName(cfg)}</th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((r: { name: unknown; value: unknown }, i: number) => (
              <tr key={i} style={{ borderBottom: '1px solid var(--border)' }}>
                <td style={{ padding: '3px 8px' }}>{String(r.name)}</td>
                <td style={{ padding: '3px 8px', textAlign: 'end' }}>{formatMeasureCell(r.value, measureFmt)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  // Lattice: the same renderer once per panel, on one shared axis.
  const AnimInner = data?.type === 'animated' ? CHART_RENDERERS[data.inner as WidgetType] : undefined
  if (AnimInner) {
    return (
      <AnimatedRenderer Inner={AnimInner} onFrame={onAnimationFrame} props={{ rows: [], data, cfg, rtl, broadcasts,
        localSelected, onClickPoint, measureFmt, measure2Fmt, allFormats, ruleStyles, geography }} />
    )
  }
  const LatticeInner = data?.type === 'lattice' ? CHART_RENDERERS[data.inner as WidgetType] : undefined
  if (LatticeInner) {
    return (
      <LatticeRenderer Inner={LatticeInner} props={{ rows: [], data, cfg, rtl, broadcasts,
        localSelected, onClickPoint, measureFmt, measure2Fmt, allFormats, ruleStyles, geography }} />
    )
  }

  const ChartRenderer = CHART_RENDERERS[wt]
  if (ChartRenderer) {
    return (
      /* Boundary for the lazily-loaded renderers (the map family): while their chunk
         downloads, only this tile shows the placeholder -- without a boundary here the
         suspend would bubble to the route-level fallback and blank the whole page. */
      <Suspense fallback={<MapLoading />}>
        <MeasuredChart>
          {(plotW, plotH) => (
            <ChartRenderer key={brushNonce ?? 0} onBrushChange={onBrushChange}
              rows={rows} data={data} cfg={cfg} rtl={rtl} broadcasts={broadcasts}
              localSelected={localSelected} onClickPoint={onClickPoint}
              measureFmt={measureFmt} measure2Fmt={measure2Fmt} allFormats={allFormats}
              ruleStyles={ruleStyles} geography={geography} plotW={plotW} plotH={plotH}
              treePaths={treePaths} onTreeChange={onTreeChange} />
          )}
        </MeasuredChart>
      </Suspense>
    )
  }

  return <EmptyState msg={`Unknown widget: ${wt}`} />
}

/** A KPI against its stored target (server: services/widget_data.kpi_target). */
interface KpiTarget {
  value: number; period: string | null; applies: boolean; reason?: string
  against?: number; label?: string | null; pct?: number | null; remaining?: number; met?: boolean; lower_is_better?: boolean
}

/** A KPI's recent history (server: services/widget_data.kpi_trend). */
interface KpiTrend {
  granularity: string; date: string; series: { period: string; value: number }[]
  current: number; previous: number; change: number; change_pct: number | null
  period: string; previous_period: string; partial_dropped: boolean
  /** The same period one year before, when the history reaches that far. */
  year_ago?: { period: string; value: number; change: number; change_pct: number | null } | null
}

/** An inline row sparkline: the row's numeric cells across the (time-ordered)
 *  crosstab columns, drawn as a mini trend line. Scaled to the row's OWN min/max
 *  so the shape reads at a glance -- a sparkline shows movement, not magnitude.
 *  Fewer than two points is not a trend, so it renders nothing. */
function Sparkline({ values, width = 76, height = 20, filled = false, fluid = false, color = 'var(--accent)' }: {
  values: number[]; width?: number; height?: number; filled?: boolean
  /** Fill whatever box it is given (a headline number's history across its card). */
  fluid?: boolean; color?: string }) {
  const gradient = `spark${useId().replace(/:/g, '')}`
  if (fluid) { width = 100; height = 32 }
  const tw = useT()
  const nums = values.filter(v => typeof v === 'number' && isFinite(v))
  if (nums.length < 2) return null
  const min = Math.min(...nums), max = Math.max(...nums)
  const span = max - min || 1
  const stepX = width / (nums.length - 1)
  const y = (v: number) => (height - 2 - ((v - min) / span) * (height - 4))
  const pts = nums.map((v, i) => `${(i * stepX).toFixed(1)},${y(v).toFixed(1)}`).join(' ')
  return (
    <svg {...(fluid ? { width: '100%', height: '100%', viewBox: `0 0 ${width} ${height}`, preserveAspectRatio: 'none' } : { width, height })}
      style={{ display: 'block', flex: fluid ? '1 1 auto' : undefined, minHeight: 0 }} role="img" aria-label={tw('wb.sparkline')}>
      {filled && (
        <>
          <defs>
            <linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.34} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <polygon data-testid="sparkline-fill" points={`0,${height} ${pts} ${((nums.length - 1) * stepX).toFixed(1)},${height}`}
            fill={`url(#${gradient})`} stroke="none" />
        </>
      )}
      <polyline points={pts} fill="none" stroke={color} strokeWidth={fluid ? 2 : 1.5}
        strokeLinejoin="round" strokeLinecap="round" vectorEffect={fluid ? 'non-scaling-stroke' : undefined} />
      {/* The end dot would be stretched into an oval in a box of any shape. */}
      {!fluid && <circle cx={(nums.length - 1) * stepX} cy={y(nums[nums.length - 1])} r={1.8} fill={color} />}
    </svg>
  )
}

/** Why the server withheld a table's totals -- `totals_unavailable` carries the key. */
const TOTALS_UNAVAILABLE_REASON: Record<string, string> = {
  sampled: 'Totals hidden: this result is a sample, so a total would not describe the whole table.',
  quick_calc: "Totals hidden: this quick calculation's values are not in the measure's units, so they have no meaningful total.",
  suppressed: 'Totals hidden: some groups are suppressed, and a total would let them be worked out.',
}

/** The table widget's body, extracted so it can own the windowing hook
 *  (hooks cannot live inside WidgetRenderer's per-type branches). Above
 *  WINDOW_THRESHOLD rows, only the slice near the viewport renders, with
 *  spacer rows standing in for the rest; banding, rule styles, row numbers
 *  and cross-filter clicks all index off the ABSOLUTE row index. */
function WindowedTable({ rtl, cfg, data, cols: inCols, rows: inRows, ruleStyles, allFormats, broadcasts, onClickPoint, grouped = false, onLoadMore, loadingMore }: {
  onLoadMore?: () => void
  loadingMore?: boolean
  /** Rows are groups of a dimension (a series), not the data's own rows. */
  grouped?: boolean
  rtl: boolean
  cfg: any
  data: any
  cols: string[]
  rows: any[][]
  ruleStyles: RuleStyles | null | undefined
  allFormats: Record<string, CalcColumnFormat | undefined> | undefined
  broadcasts: boolean
  onClickPoint: (name: unknown) => void
}) {
  const tw = useT()
  // Totals placement. 'before' draws the totals row above the data and the row
  // subtotal column (`__total__`) ahead of the value columns, right after the row
  // label. Absent means 'after': how every table saved before placement existed
  // renders. Reordered here, not in the payload, because charts read the same
  // crosstab shape and must not see their series move.
  const totalsBefore = cfg.totals_position === 'before'
  // A grouped table's keys are the series' own: `name` is the dimension and
  // `value` the measure. Headed "name" and "value" (live QA 2026-09-28), they
  // are headed by what they are.
  const headerOf = (c: string) => !grouped ? c
    : c === 'name' ? String(cfg.dimension ?? cfg.roles?.category ?? 'name')
    : c === 'value' ? seriesName(cfg)
    : c
  const order = useMemo(() => {
    const idx = inCols.map((_, j) => j)
    const t = inCols.indexOf('__total__')
    return totalsBefore && t > 1 ? [0, t, ...idx.filter(j => j !== 0 && j !== t)] : idx
  }, [inCols, totalsBefore])
  const cols = useMemo(() => order.map(j => inCols[j]), [order, inCols])
  const rows = useMemo(() => order.every((j, k) => j === k) ? inRows : inRows.map(r => order.map(j => r[j])),
    [order, inRows])
  // Which total to show, and what it covers. `totals` is always every row; when
  // some groups are off the page the server also sends `totals_shown`, and the
  // label says which of the two the reader is looking at.
  const basis = data.totals_basis
  const useShown = cfg.totals_scope === 'shown' && Array.isArray(data.totals_shown)
  const rawTotals: any[] | null = useShown ? data.totals_shown : (Array.isArray(data.totals) ? data.totals : null)
  const totals = rawTotals ? order.map(j => rawTotals[j]) : null
  const totalLabel = basis?.truncated
    ? (useShown ? `Total (${basis.shown} shown)` : 'Total (all rows)')
    : 'Total'
  const rowNumbers = !!cfg.table_row_numbers
  const rowLines = !!cfg.table_row_lines
  // C-02: which columns hold the measure. Their keys ("value", or a crosstab's
  // column-dimension values and `__total__`) are not dataset columns, so a
  // lookup by column name found no format and printed raw floats.
  const crosstab = data.type === 'crosstab'
  const mFmt = measureFormat(allFormats?.[data.measure ?? cfg.measure], cfg.aggregation)
  const isMeasureCol = (c: string, j: number) => grouped ? c === 'value' : crosstab && j > 0
  const cellText = (v: unknown, c: string, j: number) =>
    isMeasureCol(c, j) ? formatMeasureCell(v, mFmt) : formatValue(v, allFormats?.[c])
  const banding = !!cfg.table_banding
  const cellPad = cfg.table_condensed ? '2px 6px' : undefined
  const estRowH = cfg.table_condensed ? 24 : 31
  const win = useWindowedRows(rows.length, estRowH, rows.length > WINDOW_THRESHOLD)
  // Paged: more rows on the server than here. Asked for when the reader is
  // within a few screens of the bottom, and again whenever the table is too
  // short to scroll at all (a tall tile over a small first page).
  const morePending = !!data.page && !grouped && Number(data.total) > rows.length
  const nearEnd = (el: HTMLElement) => el.scrollTop + el.clientHeight > el.scrollHeight - 400
  const onScroll = (e: React.UIEvent<HTMLDivElement>) => {
    win.onScroll()
    if (morePending && nearEnd(e.currentTarget)) onLoadMore?.()
  }
  useEffect(() => {
    const el = win.containerRef.current as HTMLElement | null
    if (morePending && el && el.scrollHeight <= el.clientHeight + 400) onLoadMore?.()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [morePending, rows.length])
  // Per-row trend column: the numeric cells across the crosstab's value columns form
  // the series (the first column is the row's category label, __total__ is a summary,
  // so both are excluded). Needs at least two points to be a trend.
  const seriesIdx = cols.map((_, j) => j).filter(j => j !== 0 && cols[j] !== '__total__')
  const showSpark = !!cfg.sparkline && seriesIdx.length >= 2
  // Built once, placed above the data (inside <thead>, so data-row indices -- and
  // with them banding, display rules and clicks -- are unchanged) or below it.
  const totalsRowEl = totals && (
    // Named only when the visible label has been displaced by a numeric first
    // column. When the label IS rendered, an aria-label here would have the row
    // announce the label and then read a cell that also says it.
    <tr data-testid="table-totals-row"
      aria-label={totals[0] == null ? undefined : totalLabel}
      style={{ ...(totalsBefore ? { borderBottom: '2px solid var(--border)' } : { borderTop: '2px solid var(--border)' }),
        fontWeight: 600 }}>
      {rowNumbers && <td style={{ padding: cellPad }}>{totals[0] == null ? '' : totalLabel}</td>}
      {cols.map((c: string, j: number) => (
        <td key={j} style={{ padding: cellPad }}>
          {/* When the label was displaced by a real number and there is no
              row-number cell to hold it, the word still has to reach a
              screen reader — a title attribute is not a reliable accessible
              name, so it is rendered off-screen rather than merely hinted. */}
          {j === 0 && !rowNumbers && totals[0] != null && (
            <span style={{ position: 'absolute', width: 1, height: 1, padding: 0,
              margin: -1, overflow: 'hidden', clip: 'rect(0 0 0 0)', whiteSpace: 'nowrap',
              border: 0 }}>{totalLabel} </span>
          )}
          {/* The first column carries the label when it has no total of its
              own — totalling a dimension is meaningless and the row needs a
              name. But a raw table can perfectly well START with a numeric column
              (columns: ['sales','units']), and the backend computes totals[0] for
              it; printing the label over that number would throw away a real
              total. So the label yields to a real number, and moves into the row
              -number cell when there is one. */}
          {totals[j] == null
            ? (j === 0 ? totalLabel : '')
            : cellText(totals[j], c, j)}
        </td>
      ))}
      {showSpark && <td style={{ padding: cellPad }} />}
    </tr>
  )
  return (
    // Focusable, so a keyboard user can scroll a table wider or longer than
    // its tile (axe scrollable-region-focusable, E10).
    <div dir={rtl ? 'rtl' : undefined} ref={win.containerRef} onScroll={onScroll}
      tabIndex={0} role="region" aria-label={tw('wb.table')}
      style={{ overflow: 'auto', height: '100%' }}>
      <table style={{ fontSize: 12 }}>
        <thead>
          <tr>
            {rowNumbers && <th>#</th>}
            {/* `__total__` is the grid's row subtotal: its name on screen is "Total". */}
            {cols.map((c: string) => <th key={c} style={{ padding: cellPad }}>{c === '__total__' ? tw('wb.total') : headerOf(c)}</th>)}
            {showSpark && <th style={{ padding: cellPad }}>{tw('wb.trend')}</th>}
          </tr>
          {totalsBefore && totalsRowEl}
        </thead>
        <tbody>
          {win.padTop > 0 && <tr aria-hidden="true" style={{ height: win.padTop }} />}
          {rows.slice(win.start, win.end).map((row: any[], idx: number) => {
            const i = win.start + idx  // absolute index: banding/rules/clicks stay correct
            return (
              <tr key={i}
                style={{
                  cursor: broadcasts ? 'pointer' : 'default',
                  background: banding && i % 2 === 1 ? 'var(--surface2)' : undefined,
                  borderBottom: rowLines ? '1px solid var(--border)' : undefined,
                }}
                onClick={() => broadcasts && onClickPoint(row[0])}
              >
                {rowNumbers && <td style={{ padding: cellPad }}>{i + 1}</td>}
                {row.map((v, j) => {
                  const cellStyle = ruleStyles?.cells?.[String(i)]?.[cols[j]]
                  const rowStyle = ruleStyles?.rows?.[i]
                  const painted = cellStyle ?? rowStyle ?? undefined
                  // A data_bar's `fill` colours the BAR, not the cell -- painting both
                  // would tint the whole cell the same colour the bar already draws,
                  // doubling up on one signal. Every other rule's `fill` still colours
                  // the cell exactly as before.
                  const cellBackground = painted?.bar == null ? painted?.fill : undefined
                  return (
                    <td key={j} style={{ padding: cellPad, position: 'relative', ...(painted ? { background: cellBackground, color: painted.text } : undefined) }}>
                      {painted?.bar != null && (
                        <div data-testid="cell-data-bar" aria-hidden="true" style={{
                          position: 'absolute', insetInlineStart: 0, top: 0, bottom: 0,
                          width: `${Math.max(0, Math.min(1, painted.bar)) * 100}%`,
                          background: painted.fill ?? 'color-mix(in srgb, var(--accent) 35%, transparent)',
                          zIndex: 0,
                        }} />
                      )}
                      <span style={{ position: 'relative', zIndex: 1, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                        {painted?.icon && <span aria-hidden="true">{painted.icon}</span>}
                        {isWebAddress(v) ? <CellLink url={v} /> : cellText(v, cols[j], j)}
                      </span>
                    </td>
                  )
                })}
                {showSpark && (
                  <td style={{ padding: cellPad }}>
                    <Sparkline values={seriesIdx.map(j => Number(row[j]))} />
                  </td>
                )}
              </tr>
            )
          })}
          {win.padBottom > 0 && <tr aria-hidden="true" style={{ height: win.padBottom }} />}
        </tbody>
        {!totalsBefore && totalsRowEl && <tfoot>{totalsRowEl}</tfoot>}
      </table>
      {grouped && data.total > 0 && (
        // A grouped table's `total` is the ROWS its groups were made from, not
        // groups it left out: "Showing 6 of 3576" read as a cut table (live QA
        // 2026-09-28). A left-out group is the truncation note's to say.
        <div data-testid="table-footer" style={{ padding: '6px 12px', color: 'var(--muted)', fontSize: 11, borderTop: '1px solid var(--border)' }}>
          {tw(rows.length === 1 ? 'wb.groupFrom' : 'wb.groupsFrom', { n: rows.length.toLocaleString(), total: Number(data.total).toLocaleString() })}
        </div>
      )}
      {!grouped && data.total > rows.length && (
        <div data-testid="table-footer" style={{ padding: '6px 12px', color: 'var(--muted)', fontSize: 11, borderTop: '1px solid var(--border)' }}>
          {tw('wb.showing', { n: rows.length.toLocaleString(), total: Number(data.total).toLocaleString() })}
          {morePending && (loadingMore ? ` — ${tw('wb.loadingMore')}` : ` — ${tw('wb.scrollMore')}`)}
        </div>
      )}
      {/* The server sets this when "Show totals" was on but the only number it could
          have produced would have described a sample rather than the table (a grouped
          DirectQuery result above the row cap). Saying so beats both a wrong total and
          a checkbox that appears to do nothing. */}
      {data.totals_unavailable && (
        <div data-testid="table-totals-unavailable"
          style={{ padding: '6px 12px', color: 'var(--muted)', fontSize: 11, borderTop: '1px solid var(--border)' }}>
          {TOTALS_UNAVAILABLE_REASON[data.totals_unavailable] ?? TOTALS_UNAVAILABLE_REASON.sampled}
        </div>
      )}
    </div>
  )
}

/** The list widget's body — same windowing treatment as WindowedTable. */
function WindowedList({ rtl, rows, ruleStyles, localSelected, broadcasts, onClickPoint, measureFmt }: {
  rtl: boolean
  rows: any[]
  ruleStyles: RuleStyles | null | undefined
  localSelected: unknown
  broadcasts: boolean
  onClickPoint: (name: unknown) => void
  measureFmt: CalcColumnFormat | undefined
}) {
  const tw = useT()
  const win = useWindowedRows(rows.length, 33, rows.length > WINDOW_THRESHOLD)
  return (
    // Focusable, so a keyboard user can scroll a table wider or longer than
    // its tile (axe scrollable-region-focusable, E10).
    <div dir={rtl ? 'rtl' : undefined} ref={win.containerRef} onScroll={win.onScroll}
      tabIndex={0} role="region" aria-label={tw('wb.table')}
      style={{ overflow: 'auto', height: '100%' }}>
      {win.padTop > 0 && <div aria-hidden="true" style={{ height: win.padTop }} />}
      {rows.slice(win.start, win.end).map((row: any, idx: number) => {
        const i = win.start + idx
        const isActive = localSelected === row.name
        const ruleFill = ruleStyles?.rows?.[i]?.fill
        // Selection/hover are treatments layered ON TOP of a rule fill, never a
        // replacement for it — the same "fill persists, treatment overlays" rule
        // getFillFactory applies to chart marks. An inset box-shadow paints above
        // the background-color but below the row's text content, so a translucent
        // tint shows the rule fill through it instead of erasing what it means.
        const selectedTint = 'inset 0 0 0 999px color-mix(in srgb, var(--accent) 12%, transparent)'
        const hoverTint = 'inset 0 0 0 999px rgba(255,255,255,.08)'
        return (
          <div key={i}
            onClick={() => broadcasts && onClickPoint(row.name)}
            style={{
              padding: '7px 12px', borderBottom: '1px solid var(--border)',
              display: 'flex', justifyContent: 'space-between', fontSize: 12,
              cursor: broadcasts ? 'pointer' : 'default',
              backgroundColor: ruleFill ?? 'transparent',
              boxShadow: isActive ? selectedTint : undefined,
              transition: 'background-color .1s, box-shadow .1s',
            }}
            onMouseEnter={e => {
              if (!broadcasts || isActive) return
              const el = e.currentTarget as HTMLElement
              if (ruleFill) el.style.boxShadow = hoverTint
              else el.style.backgroundColor = 'var(--surface2)'
            }}
            onMouseLeave={e => {
              if (isActive) return
              const el = e.currentTarget as HTMLElement
              el.style.boxShadow = 'none'
              el.style.backgroundColor = ruleFill ?? 'transparent'
            }}
          >
            <span style={{ color: isActive ? 'var(--accent)' : 'var(--text)' }}>{row.name ?? row[0]}</span>
            {row.value !== undefined && (
              <span style={{ fontFamily: 'var(--mono)', color: 'var(--accent)' }}>
                {fmtStr(row.value, measureFmt)}
              </span>
            )}
          </div>
        )
      })}
      {win.padBottom > 0 && <div aria-hidden="true" style={{ height: win.padBottom }} />}
    </div>
  )
}

/** The one-click fix for a refused aggregation: the first measure whose
 *  aggregation is meaningless for what it is, switched to the one that is. */
export function semanticFix(cfg: Record<string, unknown>, t?: TranslateFn): { patch: Record<string, unknown>; label: string } | null {
  const agg = (cfg.aggregation as string) || (cfg.agg as string) || 'sum'
  const pairs: [string, string, string][] = [
    [String(cfg.measure ?? ''), agg, 'aggregation'],
    [String(cfg.measure2 ?? ''), (cfg.aggregation2 as string) || agg, 'aggregation2'],
  ]
  for (const [col, a, key] of pairs) {
    if (!col || !semanticAggregationWarning(col, a)) continue
    const kind = nonAdditiveKind(col)!
    const safe = SAFE_AGGREGATION[kind]
    const label = t ? t('wb.useAggOf', { agg: t(`wb.safeAgg.${kind}` as MessageKey), col })
      : `Use ${safe.label} of ${col}`  // i18n-ok: only without a translator (tests)
    return { patch: { [key]: safe.value }, label }
  }
  return null
}
