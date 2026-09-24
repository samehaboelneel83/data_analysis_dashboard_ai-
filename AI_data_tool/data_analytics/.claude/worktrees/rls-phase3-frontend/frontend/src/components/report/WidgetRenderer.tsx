import { useEffect, useState, useCallback, useMemo } from 'react'
import { widgetDataApi } from '../../services/api'
import type { CalcColumn, CalcColumnFormat, Dataset } from '../../services/api'
import { useCrossFilter } from './CrossFilterContext'
import { fmtStr, formatValue, EmptyState } from './chartUtils'
import { CHART_RENDERERS } from './chartRenderers'
import type { Widget } from '../../types/report'

// ── Value formatters ──────────────────────────────────────────────────────────

interface Props {
  widget:            Widget
  datasetId:         number | null
  calculatedColumns?: CalcColumn[]
  columnFormats?:    Record<string, CalcColumnFormat>
  datasets?:         Record<number, Dataset>
  selected?:         boolean
  onSelect?:     () => void
  onDelete?:     () => void
  editMode?:     boolean
  promptFilter?: { column: string; value: string } | null
  onDragStart?:  (e: React.MouseEvent) => void
  onResizeStart?:(e: React.MouseEvent) => void
  isDragging?:   boolean
}

// ─────────────────────────────────────────────────────────────────────────────

export default function WidgetRenderer({ widget, datasetId, calculatedColumns, columnFormats, datasets, selected, onSelect, onDelete, editMode, promptFilter, onDragStart, onResizeStart, isDragging }: Props) {
  const { emitFilter, getFiltersFor, canBroadcast, activeFilters } = useCrossFilter()
  const [data,    setData]    = useState<any>(null)
  const [loading, setLoading] = useState(false)

  // Per-widget dataset override: if the widget has dataset_id in its config, use that dataset's
  // calc columns and formats; otherwise fall back to the report-level ones.
  const cfgDatasetId = (widget.config as { dataset_id?: number }).dataset_id
  const widgetDatasetId: number | null = cfgDatasetId ?? datasetId
  const overrideDataset: Dataset | undefined = (widgetDatasetId != null && datasets) ? datasets[widgetDatasetId] : undefined
  const effectiveCalcCols: CalcColumn[] = overrideDataset?.calculated_columns ?? calculatedColumns ?? []
  const effectiveFormats: Record<string, CalcColumnFormat> = overrideDataset?.column_formats ?? columnFormats ?? {}

  // Active value selected FROM this widget (for highlight)
  const [localSelected, setLocalSelected] = useState<unknown>(null)

  // Cross-filters coming from OTHER widgets
  const incomingFilters = getFiltersFor(widget.id)

  // Rebuild merged config — useMemo with serialised deps so it only changes when
  // content changes, not on every render (avoids an infinite-fetch loop).
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const mergedConfig = useMemo(() => {
    const cfg = { ...(widget.config as any) }
    const existing: any[] = cfg.filters ?? []
    const crossFilters = incomingFilters.map(f => ({ column: f.column, op: 'eq', value: f.value }))
    const pagePrompt   = (promptFilter?.column && promptFilter?.value)
      ? [{ column: promptFilter.column, op: 'eq', value: promptFilter.value }]
      : []
    cfg.filters = [...existing, ...crossFilters, ...pagePrompt]
    return cfg
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(widget.config), JSON.stringify(incomingFilters), promptFilter?.column, promptFilter?.value])

  const fetchData = useCallback(async () => {
    if (!widgetDatasetId) return
    const wt = widget.widget_type
    if (wt === 'text' || wt === 'button') return
    setLoading(true)
    try {
      const result = await widgetDataApi.query(widgetDatasetId, mergedConfig, effectiveCalcCols, wt)
      setData(result)
    } catch { setData(null) }
    finally { setLoading(false) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [widgetDatasetId, widget.widget_type, JSON.stringify(mergedConfig)])

  // Refetch only when config content actually changes
  useEffect(() => { fetchData() }, [fetchData])

  // When a user clicks a data point on THIS widget
  const handleClick = useCallback((name: unknown) => {
    if (!canBroadcast(widget.id)) return
    const cfg = widget.config as any
    const col = cfg.dimension ?? cfg.column ?? null
    if (!col) return
    // Toggle: clicking the same value clears the filter
    if (localSelected === name) {
      setLocalSelected(null)
      emitFilter(widget.id, col, name, `${col} = ${name}`)  // emitFilter toggles on repeat
    } else {
      setLocalSelected(name)
      emitFilter(widget.id, col, name, `${col} = ${name}`)
    }
  }, [canBroadcast, widget.id, widget.config, localSelected, emitFilter])

  // Clear local selection when our own emitted filter is cleared externally
  useEffect(() => {
    const ours = activeFilters.filter(f => f.sourceWidgetId === widget.id)
    if (ours.length === 0) setLocalSelected(null)
  }, [activeFilters, widget.id])

  const wt = widget.widget_type
  const title = widget.title || wt
  const broadcasts = canBroadcast(widget.id)
  const receives   = getFiltersFor(widget.id).length > 0 || (widget.id in useCrossFilter)

  const allFormats = useMemo<Record<string, CalcColumnFormat | undefined>>(() => {
    const calcFmts = Object.fromEntries(
      effectiveCalcCols.filter(c => c.format).map(c => [c.name, c.format])
    )
    return { ...effectiveFormats, ...calcFmts }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(effectiveCalcCols), JSON.stringify(effectiveFormats)])

  return (
    <div
      onClick={onSelect}
      style={{
        height: '100%', display: 'flex', flexDirection: 'column',
        border: selected ? '2px solid var(--accent)' : '1px solid var(--border)',
        borderRadius: 'var(--radius)', background: 'var(--surface)',
        overflow: 'hidden', cursor: 'default',
        boxShadow: isDragging ? '0 8px 24px rgba(0,0,0,.25)' : selected ? '0 0 0 3px rgba(108,143,255,.2)' : 'none',
        opacity: isDragging ? 0.7 : 1,
        transition: isDragging ? 'none' : 'border-color .15s, box-shadow .15s',
        position: 'relative',
        userSelect: 'none',
      }}
    >
      {/* Header — drag handle in edit mode */}
      <div
        onMouseDown={editMode && onDragStart ? e => { e.stopPropagation(); onDragStart(e) } : undefined}
        style={{
          padding: '7px 10px', borderBottom: '1px solid var(--border)',
          display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0,
          cursor: editMode && onDragStart ? 'grab' : 'default',
          background: isDragging ? 'rgba(108,143,255,.06)' : undefined,
        }}
      >
        {editMode && onDragStart && (
          <span style={{ color: 'var(--border)', fontSize: 12, lineHeight: 1, letterSpacing: 1, flexShrink: 0 }}>⠿</span>
        )}
        <span style={{ fontWeight: 600, fontSize: 11, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.05em', flex: 1 }}>{title}</span>
        {broadcasts && <span title="Emits cross-filters" style={{ fontSize: 9, color: 'var(--accent)', opacity: .7 }}>→</span>}
        {incomingFilters.length > 0 && (
          <span title={`Filtered by: ${incomingFilters.map(f => f.label).join(', ')}`}
            style={{ fontSize: 9, background: 'rgba(108,143,255,.2)', color: 'var(--accent)', padding: '1px 5px', borderRadius: 99 }}>
            {incomingFilters.length} filter{incomingFilters.length > 1 ? 's' : ''}
          </span>
        )}
        {editMode && onDelete && (
          <button style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: 14, lineHeight: 1, padding: '0 2px' }}
            onClick={e => { e.stopPropagation(); onDelete() }}>×</button>
        )}
      </div>

      {/* Body */}
      <div style={{ flex: 1, overflow: 'hidden', padding: ['table','crosstab','list'].includes(wt) ? 0 : '6px' }}>
        {loading && <EmptyState msg="Loading…" />}
        {!loading && <WidgetBody widget={widget} data={data} localSelected={localSelected} onClickPoint={handleClick} broadcasts={broadcasts} allFormats={allFormats} />}
      </div>

      {/* Resize handle — bottom-right corner */}
      {editMode && onResizeStart && (
        <div
          onMouseDown={e => { e.stopPropagation(); e.preventDefault(); onResizeStart(e) }}
          style={{
            position: 'absolute', bottom: 0, right: 0,
            width: 18, height: 18, cursor: 'nwse-resize',
            display: 'flex', alignItems: 'flex-end', justifyContent: 'flex-end',
            padding: '3px',
          }}
        >
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
            <path d="M9 1L1 9M9 5L5 9M9 9" stroke="var(--muted)" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// WidgetBody — pure rendering, receives onClick callback
// ─────────────────────────────────────────────────────────────────────────────

function WidgetBody({ widget, data, localSelected, onClickPoint, broadcasts, allFormats }:
  { widget: Widget; data: any; localSelected: unknown; onClickPoint: (v: unknown) => void; broadcasts: boolean; allFormats?: Record<string, CalcColumnFormat | undefined> }) {

  const wt = widget.widget_type
  const cfg = widget.config as any
  const rtl = !!(cfg.rtl)

  // Format for the value column: use measure if set, otherwise fall back to dimension
  // (many widgets aggregate the dimension column directly with no separate measure)
  const measureFmt = allFormats?.[cfg.measure] ?? allFormats?.[cfg.dimension]
  const measure2Fmt = allFormats?.[cfg.measure2]

  if (wt === 'text') return (
    <div dir={rtl ? 'rtl' : undefined} style={{ padding: 12, fontSize: 13, whiteSpace: 'pre-wrap' }}>{cfg.content || 'Text block'}</div>
  )
  if (wt === 'button') return (
    <div dir={rtl ? 'rtl' : undefined} style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <button className="btn btn-primary" style={{ pointerEvents: 'none' }}>{cfg.label || 'Button'}</button>
    </div>
  )

  if (!data) return <EmptyState msg="Configure widget to see data" />

  // KPI
  if (wt === 'kpi') {
    const val = data.rows?.[0]?.value ?? '—'
    return (
      <div dir={rtl ? 'rtl' : undefined} style={{ height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 4 }}>
        <div style={{ fontSize: 36, fontWeight: 700, fontFamily: 'var(--mono)', color: 'var(--accent)' }}>
          {fmtStr(val, measureFmt)}
        </div>
        <div style={{ fontSize: 11, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em' }}>
          {cfg.measure || cfg.dimension || 'Value'}
        </div>
      </div>
    )
  }

  // Table / Crosstab
  if (wt === 'table' || wt === 'crosstab') {
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
      <div dir={rtl ? 'rtl' : undefined} style={{ overflow: 'auto', height: '100%' }}>
        <table style={{ fontSize: 12 }}>
          <thead><tr>{cols.map((c: string) => <th key={c}>{c}</th>)}</tr></thead>
          <tbody>
            {rows.map((row: any[], i: number) => (
              <tr key={i}
                style={{ cursor: broadcasts ? 'pointer' : 'default' }}
                onClick={() => broadcasts && onClickPoint(row[0])}
              >
                {row.map((v, j) => (
                  <td key={j}>{formatValue(v, allFormats?.[cols[j]])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {data.total > rows.length && (
          <div style={{ padding: '6px 12px', color: 'var(--muted)', fontSize: 11, borderTop: '1px solid var(--border)' }}>
            Showing {rows.length} of {data.total}
          </div>
        )}
      </div>
    )
  }

  // List
  if (wt === 'list') {
    return (
      <div dir={rtl ? 'rtl' : undefined} style={{ overflow: 'auto', height: '100%' }}>
        {(data.rows ?? []).map((row: any, i: number) => {
          const isActive = localSelected === row.name
          return (
            <div key={i}
              onClick={() => broadcasts && onClickPoint(row.name)}
              style={{
                padding: '7px 12px', borderBottom: '1px solid var(--border)',
                display: 'flex', justifyContent: 'space-between', fontSize: 12,
                cursor: broadcasts ? 'pointer' : 'default',
                background: isActive ? 'rgba(108,143,255,.12)' : 'transparent',
                transition: 'background .1s',
              }}
              onMouseEnter={e => { if (broadcasts && !isActive) (e.currentTarget as HTMLElement).style.background = 'var(--surface2)' }}
              onMouseLeave={e => { if (!isActive) (e.currentTarget as HTMLElement).style.background = 'transparent' }}
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
      </div>
    )
  }

  const rows = data.rows ?? []

  const ChartRenderer = CHART_RENDERERS[wt]
  if (ChartRenderer) {
    return (
      <ChartRenderer rows={rows} data={data} cfg={cfg} rtl={rtl} broadcasts={broadcasts}
        localSelected={localSelected} onClickPoint={onClickPoint}
        measureFmt={measureFmt} measure2Fmt={measure2Fmt} allFormats={allFormats} />
    )
  }

  return <EmptyState msg={`Unknown widget: ${wt}`} />
}
