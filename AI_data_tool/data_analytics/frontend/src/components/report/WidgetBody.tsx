import { semanticAggregationWarning, nonAdditiveKind, SAFE_AGGREGATION } from '../../lib/semanticGuard'
import { Suspense, useMemo, useState, type ReactNode } from 'react'
import { useDirection, widgetIsRtl } from '../../contexts/DirectionContext'
import type { CalcColumnFormat } from '../../services/api'
import type { Widget, WidgetType } from '../../types/report'
import type { RuleStyles } from '../../lib/displayRules'
import { fmtStr, formatValue, EmptyState } from './chartUtils'
import { CHART_RENDERERS } from './chartRenderers'
import LatticeRenderer from './chartRenderers/LatticeRenderer'
import AnimatedRenderer from './chartRenderers/AnimatedRenderer'
import type { BrushRange } from './chartRenderers/axisOptions'
import { useWindowedRows, WINDOW_THRESHOLD } from './useWindowedRows'
import { CustomVisual } from './CustomVisual'
import { seriesName } from './chartRenderers/axisOptions'
import { WidgetPlaceholder, missingRequiredRoles, missingWidgetOptions, familyOf } from './WidgetPlaceholder'
import { MeasuredChart } from './MeasuredChart'

// ─────────────────────────────────────────────────────────────────────────────
// WidgetBody — pure rendering, receives onClick callback
// ─────────────────────────────────────────────────────────────────────────────

/** Render markdown-style [label](https://url) links inside a text block.

    Built by splitting rather than by innerHTML: the content is author input, and this
    way it stays text except for the explicit link syntax -- there is no HTML parsing
    to escape from. Only http(s) targets become anchors; any other scheme renders as
    the literal text it was, so a `javascript:` "link" is inert. */
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
  const [query, setQuery] = useState('')
  const visible = searchable && query
    ? rows.filter(r => String(r.name).toLowerCase().includes(query.toLowerCase()))
    : rows
  return (
    <div dir={rtl ? 'rtl' : undefined} style={{ overflow: 'auto', height: '100%', padding: 6 }}>
      {searchable && (
        <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search values…"
          aria-label="Search slicer values"
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

function renderTextWithLinks(content: string): ReactNode {
  const parts = content.split(/(\[[^\]]+\]\((?:https?:)\/\/[^\s)]+\))/g)
  if (parts.length === 1) return content
  return parts.map((part, i) => {
    const m = /^\[([^\]]+)\]\(((?:https?:)\/\/[^\s)]+)\)$/.exec(part)
    if (!m) return part
    return (
      <a key={i} href={m[2]} target="_blank" rel="noopener noreferrer"
        style={{ color: 'var(--accent)' }}>
        {m[1]}
      </a>
    )
  })
}

export function WidgetBody({ widget, data, fetchError, onRetry, localSelected, onClickPoint, broadcasts, allFormats, checked, onToggleSlicerValue, onButtonClick, ruleStyles, parameters, geography, textFilter, onSubmitTextFilter, onAssignData, onBrushChange, brushNonce, onAnimationFrame, onApplyFix }:
  { widget: Widget; data: any; fetchError?: { detail: string; code?: string } | null; onRetry?: () => void; localSelected: unknown; onClickPoint: (v: unknown) => void; broadcasts: boolean; allFormats?: Record<string, CalcColumnFormat | undefined>; checked?: Set<unknown>; onToggleSlicerValue?: (v: unknown) => void; onButtonClick?: () => void; ruleStyles?: RuleStyles; parameters?: Record<string, unknown>; geography?: Record<string, number>;
    textFilter?: string; onSubmitTextFilter?: (value: string, column: string) => void
    /** Edit mode only: select this widget and open its Data roles. */
    onAssignData?: () => void
    /** Overview-axis zoom reports; bumping brushNonce remounts the chart to reset it. */
    onBrushChange?: (range: BrushRange | null) => void
    brushNonce?: number
    onAnimationFrame?: (label: string | null) => void ; onApplyFix?: (patch: Record<string, unknown>, label: string) => void }) {

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
  const measureFmt = allFormats?.[cfg.measure] ?? allFormats?.[cfg.dimension]
  const measure2Fmt = allFormats?.[cfg.measure2]

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
      <div dir={rtl ? 'rtl' : undefined} style={{ padding: 12, fontSize: 13, whiteSpace: 'pre-wrap' }}>{rendered}</div>
    )
  }
  if (wt === 'button') return (
    <div dir={rtl ? 'rtl' : undefined} style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <button className="btn btn-primary" onClick={e => { e.stopPropagation(); onButtonClick?.() }}>{cfg.label || 'Button'}</button>
    </div>
  )
  if (wt === 'image') return cfg.url ? (
    <img src={cfg.url} alt={cfg.alt || ''} style={{ width: '100%', height: '100%', objectFit: cfg.fit || 'contain' }} />
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
                        : typeof v === 'number' ? v.toLocaleString() : String(v)}
                    </td>))}</tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {payload.truncated && (
          <div style={{ padding: '4px 10px', fontSize: 10.5, color: 'var(--muted)',
            borderTop: '1px solid var(--border)' }}>
            Showing the first {rows.length.toLocaleString()} rows
            {payload.row_count ? ` of ${payload.row_count.toLocaleString()}` : ''} —
            the rest were truncated.
          </div>
        )}
        {payload.input_truncated && (
          <div style={{ padding: '4px 10px', fontSize: 10.5, color: 'var(--warning, var(--muted))',
            borderTop: '1px solid var(--border)' }}>
            The script only saw the first {(payload.rows_in ?? 0).toLocaleString()} rows
            of this data — any total below is of those rows, not of everything.
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
      onSelect={broadcasts ? onClickPoint : undefined} />
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
    const nothingToDraw = !data || !drawable
    // A chart with no dimension is answered by the shaper's raw-table branch
    // (every column, row by row) -- and a line renderer then draws that as a
    // meaningless squiggle. A CHART receiving a raw table is unfinished; a
    // table receiving one is working exactly as designed.
    const rawTableForChart = data?.type === 'table' && familyOf(widget.widget_type) !== 'table'
    if (missing.length && (nothingToDraw || rawTableForChart)) {
      return <WidgetPlaceholder widget={widget} missing={missing} onAssignData={onAssignData} />
    }
  }
  if (!data && fetchError) {
    // A refused aggregation (a summed year, an averaged id) comes with its
    // fix: one click switches to the aggregation that means something.
    const fix = fetchError.code === 'semantic_veto' && onApplyFix ? semanticFix(widget.config as Record<string, unknown>) : null
    if (fix) {
      return <EmptyState msg={fetchError.detail}
        action={{ label: fix.label, onClick: () => onApplyFix!(fix.patch, fix.label) }} />
    }
    return (
      <EmptyState msg={fetchError.detail}
        action={(fetchError.code === 'source_unavailable' || fetchError.code === 'quota') && onRetry
          ? { label: 'Try again', onClick: onRetry } : undefined} />
    )
  }
  if (!data) return <EmptyState msg="Configure widget to see data" />
  // The second channel: a 200 whose body says it failed. A measure that
  // could not be evaluated arrives this way, and until the widget read it
  // the chart renderer got empty rows and drew nothing -- the message lost.
  if (data?.type === 'error') return <EmptyState msg={String(data.message || 'This widget could not be computed')} />

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
          <input type="text" aria-label={`Filter by ${col}`} defaultValue={textFilter}
            placeholder={col ? `Type a ${col}…` : 'Type a value…'}
            onKeyDown={e => {
              if (e.key !== 'Enter') return
              onSubmitTextFilter?.((e.target as HTMLInputElement).value.trim(), col)
            }}
            style={{ width: '100%', fontSize: 12, padding: '5px 8px',
              border: '1px solid var(--border)', borderRadius: 6,
              background: 'var(--surface)', color: 'var(--text)' }} />
          <span style={{ fontSize: 10, color: 'var(--muted)' }}>
            Press Enter to filter. Leave empty to clear.
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
          <select multiple aria-label="Slicer values" value={selected.map(String)}
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
    const kpiText = fmtStr(val, measureFmt)
    return (
      <div dir={rtl ? 'rtl' : undefined} style={{ height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 4, padding: '0 10px', minWidth: 0, containerType: 'inline-size' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, maxWidth: '100%', minWidth: 0 }}>
          {kpiIcon && <span aria-hidden="true" style={{ fontSize: 28, flex: '0 0 auto' }}>{kpiIcon}</span>}
          <div title={kpiText}
            style={{ fontSize: fitFigureSize(kpiText, 36), fontWeight: 650, fontVariantNumeric: 'tabular-nums', letterSpacing: '-.02em', color: ruleStyles?.rows?.[0]?.fill ?? 'var(--accent)',
              minWidth: 0, maxWidth: '100%', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', lineHeight: 1.15 }}>
            {kpiText}
          </div>
        </div>
        <div style={{ fontSize: 12, color: 'var(--muted)', maxWidth: '100%', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {cfg.measure || cfg.dimension || 'Value'}
        </div>
      </div>
    )
  }

  // Card / multi-row card
  if (wt === 'card') {
    const rows: any[] = data.rows ?? []
    return (
      <div dir={rtl ? 'rtl' : undefined} style={{ height: '100%', overflow: 'auto', display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 10, padding: 8, containerType: 'inline-size' }}>
        {rows.map((row, i) => (
          <div key={i} style={{ textAlign: 'center', minWidth: 0 }}>
            <div title={fmtStr(row.value, allFormats?.[row.name])}
              style={{ fontSize: fitFigureSize(fmtStr(row.value, allFormats?.[row.name]), 24), fontWeight: 650, fontVariantNumeric: 'tabular-nums', letterSpacing: '-.02em', color: ruleStyles?.rows?.[i]?.fill ?? 'var(--accent)',
                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', lineHeight: 1.15 }}>
              {fmtStr(row.value, allFormats?.[row.name])}
            </div>
            <div style={{ fontSize: 11.5, color: 'var(--muted)' }}>{row.name}</div>
          </div>
        ))}
      </div>
    )
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
        ruleStyles={ruleStyles} allFormats={allFormats} broadcasts={broadcasts}
        onClickPoint={onClickPoint} />
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
                <td style={{ padding: '3px 8px', textAlign: 'end' }}>{formatValue(r.value, measureFmt)}</td>
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
      <Suspense fallback={<EmptyState msg="Loading map…" />}>
        <MeasuredChart>
          {(plotW, plotH) => (
            <ChartRenderer key={brushNonce ?? 0} onBrushChange={onBrushChange}
              rows={rows} data={data} cfg={cfg} rtl={rtl} broadcasts={broadcasts}
              localSelected={localSelected} onClickPoint={onClickPoint}
              measureFmt={measureFmt} measure2Fmt={measure2Fmt} allFormats={allFormats}
              ruleStyles={ruleStyles} geography={geography} plotW={plotW} plotH={plotH} />
          )}
        </MeasuredChart>
      </Suspense>
    )
  }

  return <EmptyState msg={`Unknown widget: ${wt}`} />
}

/** An inline row sparkline: the row's numeric cells across the (time-ordered)
 *  crosstab columns, drawn as a mini trend line. Scaled to the row's OWN min/max
 *  so the shape reads at a glance -- a sparkline shows movement, not magnitude.
 *  Fewer than two points is not a trend, so it renders nothing. */
function Sparkline({ values, width = 76, height = 20 }: { values: number[]; width?: number; height?: number }) {
  const nums = values.filter(v => typeof v === 'number' && isFinite(v))
  if (nums.length < 2) return null
  const min = Math.min(...nums), max = Math.max(...nums)
  const span = max - min || 1
  const stepX = width / (nums.length - 1)
  const y = (v: number) => (height - 2 - ((v - min) / span) * (height - 4))
  const pts = nums.map((v, i) => `${(i * stepX).toFixed(1)},${y(v).toFixed(1)}`).join(' ')
  return (
    <svg width={width} height={height} style={{ display: 'block' }} role="img" aria-label="trend sparkline">
      <polyline points={pts} fill="none" stroke="var(--accent)" strokeWidth={1.5}
        strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={(nums.length - 1) * stepX} cy={y(nums[nums.length - 1])} r={1.8} fill="var(--accent)" />
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
function WindowedTable({ rtl, cfg, data, cols: inCols, rows: inRows, ruleStyles, allFormats, broadcasts, onClickPoint }: {
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
  // Totals placement. 'before' draws the totals row above the data and the row
  // subtotal column (`__total__`) ahead of the value columns, right after the row
  // label. Absent means 'after': how every table saved before placement existed
  // renders. Reordered here, not in the payload, because charts read the same
  // crosstab shape and must not see their series move.
  const totalsBefore = cfg.totals_position === 'before'
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
  const banding = !!cfg.table_banding
  const cellPad = cfg.table_condensed ? '2px 6px' : undefined
  const estRowH = cfg.table_condensed ? 24 : 31
  const win = useWindowedRows(rows.length, estRowH, rows.length > WINDOW_THRESHOLD)
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
            : formatValue(totals[j], allFormats?.[c])}
        </td>
      ))}
      {showSpark && <td style={{ padding: cellPad }} />}
    </tr>
  )
  return (
    <div dir={rtl ? 'rtl' : undefined} ref={win.containerRef} onScroll={win.onScroll}
      style={{ overflow: 'auto', height: '100%' }}>
      <table style={{ fontSize: 12 }}>
        <thead>
          <tr>
            {rowNumbers && <th>#</th>}
            {cols.map((c: string) => <th key={c} style={{ padding: cellPad }}>{c}</th>)}
            {showSpark && <th style={{ padding: cellPad }}>Trend</th>}
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
                        {formatValue(v, allFormats?.[cols[j]])}
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
      {data.total > rows.length && (
        <div style={{ padding: '6px 12px', color: 'var(--muted)', fontSize: 11, borderTop: '1px solid var(--border)' }}>
          Showing {rows.length} of {data.total}
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
  const win = useWindowedRows(rows.length, 33, rows.length > WINDOW_THRESHOLD)
  return (
    <div dir={rtl ? 'rtl' : undefined} ref={win.containerRef} onScroll={win.onScroll}
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
export function semanticFix(cfg: Record<string, unknown>): { patch: Record<string, unknown>; label: string } | null {
  const agg = (cfg.aggregation as string) || (cfg.agg as string) || 'sum'
  const pairs: [string, string, string][] = [
    [String(cfg.measure ?? ''), agg, 'aggregation'],
    [String(cfg.measure2 ?? ''), (cfg.aggregation2 as string) || agg, 'aggregation2'],
  ]
  for (const [col, a, key] of pairs) {
    if (!col || !semanticAggregationWarning(col, a)) continue
    const safe = SAFE_AGGREGATION[nonAdditiveKind(col)!]
    return { patch: { [key]: safe.value }, label: `Use ${safe.label} of ${col}` }
  }
  return null
}
