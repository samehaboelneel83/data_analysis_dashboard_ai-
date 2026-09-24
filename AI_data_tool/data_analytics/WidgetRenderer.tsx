import { useEffect, useState, useCallback } from 'react'
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  ScatterChart, Scatter, Treemap, XAxis, YAxis,
  CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { widgetDataApi } from '../../services/api'
import { useCrossFilter } from './CrossFilterContext'
import type { Widget } from '../../types/report'

const COLORS = ['#6c8fff','#a78bfa','#34d399','#fbbf24','#f87171','#38bdf8','#fb7185','#4ade80','#c084fc','#e879f9']
const SELECTED_STROKE = '#fff'
const DIM_OPACITY = 0.35

interface Props {
  widget:    Widget
  datasetId: number | null
  selected?: boolean
  onSelect?: () => void
  onDelete?: () => void
  editMode?: boolean
}

function EmptyState({ msg }: { msg: string }) {
  return (
    <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 12, flexDirection: 'column', gap: 6 }}>
      <span style={{ fontSize: 24, opacity: .4 }}>◻</span>
      <span>{msg}</span>
    </div>
  )
}

const TT: React.CSSProperties = { background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }

// ─────────────────────────────────────────────────────────────────────────────

export default function WidgetRenderer({ widget, datasetId, selected, onSelect, onDelete, editMode }: Props) {
  const { emitFilter, getFiltersFor, canBroadcast, activeFilters } = useCrossFilter()
  const [data,    setData]    = useState<any>(null)
  const [loading, setLoading] = useState(false)

  // Active value selected FROM this widget (for highlight)
  const [localSelected, setLocalSelected] = useState<unknown>(null)

  // Cross-filters coming from OTHER widgets
  const incomingFilters = getFiltersFor(widget.id)

  // Rebuild merged config: widget config + incoming cross-filters
  const mergedConfig = useCallback(() => {
    const cfg = { ...(widget.config as any) }
    const existing: any[] = cfg.filters ?? []
    const crossFilters = incomingFilters.map(f => ({ column: f.column, op: 'eq', value: f.value }))
    cfg.filters = [...existing, ...crossFilters]
    return cfg
  }, [widget.config, incomingFilters])

  const fetchData = useCallback(async () => {
    if (!datasetId) return
    const wt = widget.widget_type
    if (wt === 'text' || wt === 'button') return
    setLoading(true)
    try {
      const result = await widgetDataApi.query(datasetId, mergedConfig())
      setData(result)
    } catch { setData(null) }
    finally { setLoading(false) }
  }, [datasetId, mergedConfig, widget.widget_type])

  // Refetch whenever incoming filters change
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

  return (
    <div
      onClick={onSelect}
      style={{
        height: '100%', display: 'flex', flexDirection: 'column',
        border: selected ? '2px solid var(--accent)' : '1px solid var(--border)',
        borderRadius: 'var(--radius)', background: 'var(--surface)',
        overflow: 'hidden', cursor: editMode ? 'pointer' : 'default',
        boxShadow: selected ? '0 0 0 3px rgba(108,143,255,.2)' : 'none',
        transition: 'border-color .15s, box-shadow .15s',
        position: 'relative',
      }}
    >
      {/* Header */}
      <div style={{ padding: '7px 10px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
        <span style={{ fontWeight: 600, fontSize: 11, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.05em', flex: 1 }}>{title}</span>
        {/* Interaction badges */}
        {broadcasts && <span title="Emits cross-filters" style={{ fontSize: 9, color: 'var(--accent)', opacity: .7 }}>→</span>}
        {incomingFilters.length > 0 && (
          <span title={`Filtered by: ${incomingFilters.map(f=>f.label).join(', ')}`}
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
        {!loading && <WidgetBody widget={widget} data={data} localSelected={localSelected} onClickPoint={handleClick} broadcasts={broadcasts} />}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// WidgetBody — pure rendering, receives onClick callback
// ─────────────────────────────────────────────────────────────────────────────

function WidgetBody({ widget, data, localSelected, onClickPoint, broadcasts }:
  { widget: Widget; data: any; localSelected: unknown; onClickPoint: (v: unknown) => void; broadcasts: boolean }) {

  const wt = widget.widget_type
  const cfg = widget.config as any

  if (wt === 'text') return (
    <div style={{ padding: 12, fontSize: 13, whiteSpace: 'pre-wrap' }}>{cfg.content || 'Text block'}</div>
  )
  if (wt === 'button') return (
    <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <button className="btn btn-primary" style={{ pointerEvents: 'none' }}>{cfg.label || 'Button'}</button>
    </div>
  )

  if (!data) return <EmptyState msg="Configure widget to see data" />

  // KPI
  if (wt === 'kpi') {
    const val = data.rows?.[0]?.value ?? '—'
    return (
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 4 }}>
        <div style={{ fontSize: 36, fontWeight: 700, fontFamily: 'var(--mono)', color: 'var(--accent)' }}>
          {typeof val === 'number' ? val.toLocaleString(undefined, { maximumFractionDigits: 2 }) : val}
        </div>
        <div style={{ fontSize: 11, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em' }}>
          {cfg.measure || cfg.dimension || 'Value'}
        </div>
      </div>
    )
  }

  // Table / Crosstab
  if (wt === 'table' || wt === 'crosstab') {
    const cols = data.columns ?? []
    const rows = data.rows ?? []
    return (
      <div style={{ overflow: 'auto', height: '100%' }}>
        <table style={{ fontSize: 12 }}>
          <thead><tr>{cols.map((c: string) => <th key={c}>{c}</th>)}</tr></thead>
          <tbody>
            {rows.map((row: any[], i: number) => (
              <tr key={i}
                style={{ cursor: broadcasts ? 'pointer' : 'default' }}
                onClick={() => broadcasts && onClickPoint(row[0])}
              >
                {row.map((v, j) => <td key={j}>{v ?? '—'}</td>)}
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
      <div style={{ overflow: 'auto', height: '100%' }}>
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
                  {typeof row.value === 'number' ? row.value.toLocaleString(undefined, { maximumFractionDigits: 2 }) : row.value}
                </span>
              )}
            </div>
          )
        })}
      </div>
    )
  }

  const rows = data.rows ?? []

  // Helper: get fill + opacity for a bar/slice by index/name
  const getFill = (name: unknown, i: number) => {
    const color = COLORS[i % COLORS.length]
    if (!broadcasts || localSelected === null) return { fill: color, opacity: 1 }
    return localSelected === name
      ? { fill: color, opacity: 1, strokeWidth: 2, stroke: SELECTED_STROKE }
      : { fill: color, opacity: DIM_OPACITY }
  }

  // Bar chart
  if (wt === 'bar') return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={rows} margin={{ top: 4, right: 8, bottom: 20, left: 0 }}
        onClick={broadcasts ? (d) => d?.activePayload?.[0] && onClickPoint(d.activePayload[0].payload.name) : undefined}
        style={{ cursor: broadcasts ? 'pointer' : 'default' }}
      >
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis dataKey="name" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} angle={-30} textAnchor="end" interval={0} />
        <YAxis tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} />
        <Tooltip contentStyle={TT} />
        <Bar dataKey="value" radius={[4,4,0,0]}>
          {rows.map((r: any, i: number) => {
            const s = getFill(r.name, i)
            return <Cell key={i} fill={s.fill} opacity={s.opacity} stroke={s.stroke} strokeWidth={s.strokeWidth} />
          })}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )

  // Line chart
  if (wt === 'line') return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={rows} margin={{ top: 4, right: 8, bottom: 20, left: 0 }}
        onClick={broadcasts ? (d) => d?.activePayload?.[0] && onClickPoint(d.activePayload[0].payload.name) : undefined}
        style={{ cursor: broadcasts ? 'pointer' : 'default' }}
      >
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis dataKey="name" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} angle={-30} textAnchor="end" />
        <YAxis tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} />
        <Tooltip contentStyle={TT} />
        <Line type="monotone" dataKey="value" stroke="var(--accent)" strokeWidth={2}
          dot={{ fill: 'var(--accent)', r: 3 }}
          activeDot={{ r: 5, fill: 'var(--accent)', stroke: '#fff', strokeWidth: 2 }}
        />
      </LineChart>
    </ResponsiveContainer>
  )

  // Pie chart
  if (wt === 'pie') return (
    <ResponsiveContainer width="100%" height="100%">
      <PieChart>
        <Pie data={rows} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius="70%"
          onClick={broadcasts ? (d) => onClickPoint(d.name) : undefined}
          style={{ cursor: broadcasts ? 'pointer' : 'default' }}
          label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
          labelLine={false}
        >
          {rows.map((r: any, i: number) => {
            const s = getFill(r.name, i)
            return <Cell key={i} fill={s.fill} opacity={s.opacity} stroke={localSelected === r.name ? SELECTED_STROKE : 'none'} strokeWidth={s.strokeWidth ?? 0} />
          })}
        </Pie>
        <Tooltip contentStyle={TT} />
      </PieChart>
    </ResponsiveContainer>
  )

  // Donut chart
  if (wt === 'donut') return (
    <ResponsiveContainer width="100%" height="100%">
      <PieChart>
        <Pie data={rows} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius="40%" outerRadius="70%"
          onClick={broadcasts ? (d) => onClickPoint(d.name) : undefined}
          style={{ cursor: broadcasts ? 'pointer' : 'default' }}
        >
          {rows.map((r: any, i: number) => {
            const s = getFill(r.name, i)
            return <Cell key={i} fill={s.fill} opacity={s.opacity} />
          })}
        </Pie>
        <Tooltip contentStyle={TT} />
        <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 11 }} />
      </PieChart>
    </ResponsiveContainer>
  )

  // Scatter chart
  if (wt === 'scatter') {
    const scatterData = rows.map((r: any) => ({ x: r.x ?? r.name, y: r.y ?? r.value }))
    return (
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey="x" type="number" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} />
          <YAxis dataKey="y" type="number" tick={{ fill: 'var(--muted)', fontSize: 10 }} axisLine={false} tickLine={false} />
          <Tooltip contentStyle={TT} />
          <Scatter data={scatterData} fill="var(--accent)"
            onClick={broadcasts ? (d) => onClickPoint(d.x) : undefined}
            style={{ cursor: broadcasts ? 'pointer' : 'default' }}
          />
        </ScatterChart>
      </ResponsiveContainer>
    )
  }

  // Treemap
  if (wt === 'treemap') {
    const tmData = rows.map((r: any, i: number) => ({ name: r.name, size: r.value, _i: i }))
    return (
      <ResponsiveContainer width="100%" height="100%">
        <Treemap data={tmData} dataKey="size" nameKey="name" aspectRatio={4/3}
          onClick={broadcasts ? (d) => onClickPoint(d.name) : undefined}
          style={{ cursor: broadcasts ? 'pointer' : 'default' }}
          content={({ x, y, width, height, name, _i }: any) => {
            const color = COLORS[(_i ?? 0) % COLORS.length]
            const isActive = localSelected === name
            const dimmed  = broadcasts && localSelected !== null && !isActive
            return width > 8 && height > 8 ? (
              <g>
                <rect x={x} y={y} width={width} height={height}
                  fill={color} opacity={dimmed ? DIM_OPACITY : 1}
                  stroke={isActive ? SELECTED_STROKE : 'var(--surface)'} strokeWidth={isActive ? 2 : 1.5} rx={4} />
                {width > 60 && height > 28 && (
                  <text x={x + width / 2} y={y + height / 2} textAnchor="middle" dominantBaseline="middle"
                    fill="#fff" fontSize={Math.min(12, width / 7)} fontWeight={600}>{name}</text>
                )}
              </g>
            ) : <g />
          }}
        />
      </ResponsiveContainer>
    )
  }

  return <EmptyState msg={`Unknown widget: ${wt}`} />
}
