import { useState, useEffect } from 'react'
import type { Widget } from '../../types/report'
import { AGGREGATIONS } from '../../types/report'
import type { DatasetColumn } from '../../services/api'
import InteractionSettings from './InteractionSettings'

interface Props {
  widget: Widget
  columns: DatasetColumn[]
  onUpdate: (config: Record<string, unknown>, title: string) => void
}

const RUNNING_OPTIONS = [
  { value: '',    label: 'None' },
  { value: 'sum', label: 'Running Sum' },
  { value: 'avg', label: 'Running Average' },
]

const SORT_BY_OPTIONS = [
  { value: 'value', label: 'By Value' },
  { value: 'name',  label: 'By Name' },
]

export default function WidgetConfigPanel({ widget, columns, onUpdate }: Props) {
  const cfg = widget.config as any
  const wt  = widget.widget_type

  const [title,     setTitle]     = useState(widget.title ?? '')
  const [dimension, setDimension] = useState(cfg.dimension  ?? '')
  const [dimension2,setDimension2]= useState(cfg.dimension2 ?? '')
  const [measure,   setMeasure]   = useState(cfg.measure    ?? '')
  const [agg,       setAgg]       = useState(cfg.aggregation ?? 'sum')
  const [limit,     setLimit]     = useState(cfg.limit      ?? 20)
  const [sort,      setSort]      = useState(cfg.sort       ?? 'desc')
  const [sortBy,    setSortBy]    = useState(cfg.sort_by    ?? 'value')
  const [running,   setRunning]   = useState(cfg.running    ?? '')
  const [content,   setContent]   = useState(cfg.content    ?? '')
  const [label,     setLabel]     = useState(cfg.label      ?? 'Click me')
  const [tableCols, setTableCols] = useState<string[]>(cfg.columns ?? [])

  // Sync state when widget changes (user selects different widget)
  useEffect(() => {
    setTitle(widget.title ?? '')
    setDimension(cfg.dimension ?? '')
    setDimension2(cfg.dimension2 ?? '')
    setMeasure(cfg.measure ?? '')
    setAgg(cfg.aggregation ?? 'sum')
    setLimit(cfg.limit ?? 20)
    setSort(cfg.sort ?? 'desc')
    setSortBy(cfg.sort_by ?? 'value')
    setRunning(cfg.running ?? '')
    setContent(cfg.content ?? '')
    setLabel(cfg.label ?? 'Click me')
    setTableCols(cfg.columns ?? [])
  }, [widget.id])

  // Emit config changes
  useEffect(() => {
    if (wt === 'text')   { onUpdate({ content }, title); return }
    if (wt === 'button') { onUpdate({ label }, title); return }

    const base: Record<string, unknown> = {
      aggregation: agg, limit, sort, sort_by: sortBy,
      ...(running ? { running } : {}),
    }
    if (dimension)  base.dimension  = dimension
    if (dimension2) base.dimension2 = dimension2
    if (measure)    base.measure    = measure
    if (tableCols.length > 0) base.columns = tableCols
    onUpdate(base, title)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [title, dimension, dimension2, measure, agg, limit, sort, sortBy, running, content, label, tableCols.join(',')])

  const numCols = columns.filter(c => c.dtype === 'numeric')

  // Group aggregations for display
  const aggGroups = AGGREGATIONS.reduce<Record<string, typeof AGGREGATIONS[number][]>>((acc, a) => {
    ;(acc[a.group] ??= []).push(a)
    return acc
  }, {})

  const fld = (lbl: string, el: React.ReactNode) => (
    <div style={{ marginBottom: 12 }}>
      <label style={{ display:'block', fontSize:10, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>{lbl}</label>
      {el}
    </div>
  )

  const sel = (value: string, onChange: (v: string) => void, options: {value:string;label:string}[], ph = '— none —') => (
    <select value={value} onChange={e => onChange(e.target.value)} style={{ width:'100%' }}>
      <option value="">{ph}</option>
      {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  )

  return (
    <div style={{ fontSize:13 }}>
      <div style={{ padding:'14px 14px 0' }}>
        <div style={{ fontWeight:700, marginBottom:14, fontSize:13, display:'flex', alignItems:'center', gap:6, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.05em' }}>
          {widgetIcon(wt)} {wt} settings
        </div>

        {fld('Title', <input value={title} onChange={e => setTitle(e.target.value)} style={{ width:'100%' }} placeholder="Widget title" />)}

        {/* Text / Button */}
        {wt === 'text'   && fld('Content', <textarea value={content} onChange={e => setContent(e.target.value)} rows={4} style={{ width:'100%', resize:'vertical' }} placeholder="Enter text…" />)}
        {wt === 'button' && fld('Button label', <input value={label} onChange={e => setLabel(e.target.value)} style={{ width:'100%' }} />)}

        {wt !== 'text' && wt !== 'button' && (<>
          {/* Dimension */}
          {fld('Dimension (Group / X-axis)',
            sel(dimension, setDimension, columns.map(c => ({ value:c.name, label:`${c.name} (${c.dtype})` })), '— select column —')
          )}

          {/* Second dimension for crosstab */}
          {wt === 'crosstab' && fld('Column Pivot',
            sel(dimension2, setDimension2, columns.map(c => ({ value:c.name, label:c.name })))
          )}

          {/* Measure */}
          {fld('Measure (numeric column)',
            sel(measure, setMeasure, numCols.map(c => ({ value:c.name, label:c.name })), '— count rows —')
          )}

          {/* Aggregation — grouped select */}
          <div style={{ marginBottom:12 }}>
            <label style={{ display:'block', fontSize:10, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
              Aggregation
            </label>
            <select value={agg} onChange={e => setAgg(e.target.value)} style={{ width:'100%' }}>
              {Object.entries(aggGroups).map(([group, items]) => (
                <optgroup key={group} label={`── ${group} ──`}>
                  {items.map(a => <option key={a.value} value={a.value}>{a.label}</option>)}
                </optgroup>
              ))}
            </select>
            <div style={{ fontSize:10, color:'var(--muted)', marginTop:3 }}>
              {AGGREGATIONS.find(a => a.value === agg)?.label ?? agg}
              {measure ? ` of ${measure}` : ' (row count)'}
            </div>
          </div>

          {/* Running metric */}
          {(wt === 'bar' || wt === 'line' || wt === 'list') && fld('Running metric',
            sel(running, setRunning, RUNNING_OPTIONS)
          )}

          {/* Column selector for table/list */}
          {(wt === 'table' || wt === 'crosstab' || wt === 'list') && (
            <div style={{ marginBottom:12 }}>
              <label style={{ display:'block', fontSize:10, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>
                Visible columns
              </label>
              <div style={{ maxHeight:130, overflowY:'auto', display:'flex', flexDirection:'column', gap:3, background:'var(--surface2)', border:'1px solid var(--border)', borderRadius:6, padding:'6px 8px' }}>
                {columns.map(c => (
                  <label key={c.name} style={{ display:'flex', alignItems:'center', gap:6, fontSize:12, cursor:'pointer' }}>
                    <input type="checkbox" checked={tableCols.includes(c.name)}
                      onChange={e => setTableCols(p => e.target.checked ? [...p, c.name] : p.filter(x => x !== c.name))} />
                    <span style={{ color: tableCols.includes(c.name) ? 'var(--text)' : 'var(--muted)' }}>{c.name}</span>
                    <span className={`badge badge-${c.dtype}`} style={{ marginLeft:'auto', padding:'1px 5px', fontSize:9 }}>{c.dtype}</span>
                  </label>
                ))}
              </div>
            </div>
          )}

          {/* Sort */}
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8, marginBottom:12 }}>
            <div>
              <label style={{ display:'block', fontSize:10, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>Sort order</label>
              <select value={sort} onChange={e => setSort(e.target.value)} style={{ width:'100%' }}>
                <option value="desc">Descending</option>
                <option value="asc">Ascending</option>
              </select>
            </div>
            <div>
              <label style={{ display:'block', fontSize:10, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:4 }}>Sort by</label>
              <select value={sortBy} onChange={e => setSortBy(e.target.value)} style={{ width:'100%' }}>
                {SORT_BY_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>
          </div>

          {fld('Row limit',
            <input type="number" value={limit} min={1} max={1000} onChange={e => setLimit(Number(e.target.value))} style={{ width:'100%' }} />
          )}
        </>)}
      </div>

      {/* Visual interaction settings */}
      <InteractionSettings widget={widget} />
    </div>
  )
}

function widgetIcon(wt: string) {
  return ({ bar:'▬',line:'↗',pie:'◔',donut:'◯',scatter:'⁘',treemap:'⊞',kpi:'◈',table:'☰',crosstab:'⊟',list:'≡',text:'T',button:'▶' } as any)[wt] ?? '◻'
}
