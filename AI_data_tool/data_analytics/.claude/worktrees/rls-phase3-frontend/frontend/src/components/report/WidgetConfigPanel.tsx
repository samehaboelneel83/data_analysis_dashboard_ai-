import { useState, useEffect, useRef, useMemo } from 'react'
import type { Widget, WidgetType } from '../../types/report'
import { AGGREGATIONS, ROLE_SPECS } from '../../types/report'
import type { DatasetColumn, Dataset } from '../../services/api'
import InteractionSettings from './InteractionSettings'

interface Props {
  widget: Widget
  columns: DatasetColumn[]
  datasets?: Record<number, Dataset>
  primaryDatasetId?: number | null
  onUpdate: (config: Record<string, unknown>, title: string) => void
}

const RUNNING_OPTIONS = [
  { value: '',    label: 'None' },
  { value: 'sum', label: 'Running Sum' },
  { value: 'avg', label: 'Running Average' },
]

const ROLE_TO_CONFIG_KEY: Record<string, string> = { category: 'dimension', category2: 'dimension2', measure: 'measure' }
const configKeyFor = (role: string) => ROLE_TO_CONFIG_KEY[role] ?? role

function seedRoleValues(cfg: Record<string, unknown>, wt: WidgetType): Record<string, string> {
  const values: Record<string, string> = {}
  for (const rf of (ROLE_SPECS[wt] ?? []).filter(rf => !rf.multi)) {
    values[rf.role] = (cfg[configKeyFor(rf.role)] as string) ?? ''
  }
  return values
}

function seedMultiRoleValues(cfg: Record<string, unknown>, wt: WidgetType): Record<string, string[]> {
  const values: Record<string, string[]> = {}
  for (const rf of (ROLE_SPECS[wt] ?? []).filter(rf => rf.multi)) {
    values[rf.role] = Array.isArray(cfg[rf.role]) ? (cfg[rf.role] as string[]) : []
  }
  return values
}

export default function WidgetConfigPanel({ widget, columns, datasets, primaryDatasetId, onUpdate }: Props) {
  const cfg = widget.config as any
  const wt  = widget.widget_type

  const [title,      setTitle]      = useState(widget.title ?? '')
  const [datasetId,  setDatasetId]  = useState<number | ''>(cfg.dataset_id || '')
  const [roleValues, setRoleValues] = useState<Record<string, string>>(() => seedRoleValues(cfg, wt))
  const setRole = (role: string, value: string) => setRoleValues(prev => ({ ...prev, [role]: value }))
  const [multiRoleValues, setMultiRoleValues] = useState<Record<string, string[]>>(() => seedMultiRoleValues(cfg, wt))
  const toggleMultiRole = (role: string, value: string) => setMultiRoleValues(prev => {
    const current = prev[role] ?? []
    const next = current.includes(value) ? current.filter(v => v !== value) : [...current, value]
    return { ...prev, [role]: next }
  })
  const [agg,        setAgg]        = useState(cfg.aggregation ?? 'sum')
  const [limit,      setLimit]      = useState(cfg.limit      ?? 20)
  const [sort,       setSort]       = useState(cfg.sort       ?? 'desc')
  const [sortBy,     setSortBy]     = useState(cfg.sort_by    ?? 'value')
  const [sortCol,    setSortCol]    = useState(cfg.sort_col   ?? '')
  const [running,    setRunning]    = useState(cfg.running    ?? '')
  const [content,    setContent]    = useState(cfg.content    ?? '')
  const [label,      setLabel]      = useState(cfg.label      ?? 'Click me')
  const [tableCols,  setTableCols]  = useState<string[]>(cfg.columns ?? [])
  const [rtl,        setRtl]        = useState<boolean>(cfg.rtl ?? false)
  const [bins,       setBins]       = useState<number>((cfg.bins as number) ?? 10)
  const [baseline,   setBaseline]   = useState<number>((cfg.baseline as number) ?? 0)
  const [fitLine,    setFitLine]    = useState<string>((cfg.fit_line as string) ?? '')
  const [targetValue, setTargetValue] = useState<string>((cfg.target_value != null ? String(cfg.target_value) : ''))

  // Effective columns: use the selected widget dataset if specified, otherwise fall back to report-level columns
  const effectiveCols = useMemo<DatasetColumn[]>(() => {
    if (datasetId && datasets?.[datasetId]) {
      const ds = datasets[datasetId]
      const calcAsCol = (ds.calculated_columns ?? []).map(c => ({
        id: -1, name: c.name, dtype: 'calculated' as const, missing_pct: 0, stats: {},
      }))
      return [...ds.columns, ...calcAsCol]
    }
    return columns
  }, [datasetId, datasets, columns])

  // mounted tracks whether the first render after a widget-change has passed;
  // prevents auto-save firing on mount or when syncing state to a newly selected widget.
  const mounted = useRef(false)

  // Sync state when widget changes — reset mounted so the resulting re-render is skipped.
  useEffect(() => {
    mounted.current = false
    setTitle(widget.title ?? '')
    setDatasetId(cfg.dataset_id || '')
    setRoleValues(seedRoleValues(cfg, wt))
    setMultiRoleValues(seedMultiRoleValues(cfg, wt))
    setAgg(cfg.aggregation ?? 'sum')
    setLimit(cfg.limit ?? 20)
    setSort(cfg.sort ?? 'desc')
    setSortBy(cfg.sort_by ?? 'value')
    setSortCol(cfg.sort_col ?? '')
    setRunning(cfg.running ?? '')
    setContent(cfg.content ?? '')
    setLabel(cfg.label ?? 'Click me')
    setTableCols(cfg.columns ?? [])
    setRtl(cfg.rtl ?? false)
    setBins((cfg.bins as number) ?? 10)
    setBaseline((cfg.baseline as number) ?? 0)
    setFitLine((cfg.fit_line as string) ?? '')
    setTargetValue(cfg.target_value != null ? String(cfg.target_value) : '')
  }, [widget.id])

  // Emit config changes — debounced 600 ms, skips the first render after a widget switch.
  useEffect(() => {
    if (!mounted.current) { mounted.current = true; return }

    let config: Record<string, unknown>
    if (wt === 'text')   { config = { content, rtl } }
    else if (wt === 'button') { config = { label, rtl } }
    else {
      config = { aggregation: agg, limit, sort, sort_by: sortBy, ...(sortCol ? { sort_col: sortCol } : {}), rtl, ...(running ? { running } : {}) }
      for (const rf of (ROLE_SPECS[wt] ?? []).filter(rf => !rf.multi)) {
        const v = roleValues[rf.role]
        if (v) config[configKeyFor(rf.role)] = v
      }
      for (const rf of (ROLE_SPECS[wt] ?? []).filter(rf => rf.multi)) {
        const vals = multiRoleValues[rf.role] ?? []
        if (vals.length > 0) config[rf.role] = vals
      }
      if (tableCols.length > 0) config.columns = tableCols
      if (wt === 'histogram') config.bins = bins
      if (wt === 'needle') config.baseline = baseline
      if (wt === 'bubble' && fitLine) config.fit_line = fitLine
      if (wt === 'gauge' && targetValue !== '' && !isNaN(Number(targetValue))) config.target_value = Number(targetValue)
    }
    if (datasetId) config.dataset_id = datasetId

    const timer = setTimeout(() => onUpdate(config, title), 600)
    return () => clearTimeout(timer)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [title, datasetId, JSON.stringify(roleValues), JSON.stringify(multiRoleValues), agg, limit, sort, sortBy, sortCol, running, content, label, rtl, tableCols.join(','), bins, baseline, fitLine, targetValue])

  const numCols = effectiveCols.filter(c => c.dtype === 'numeric')

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

  const colOptions = effectiveCols.map(c => ({
    value: c.name,
    label: c.dtype === 'calculated' ? `ƒx ${c.name}` : `${c.name} (${c.dtype})`,
  }))

  return (
    <div style={{ fontSize:13 }}>
      <div style={{ padding:'14px 14px 0' }}>
        <div style={{ fontWeight:700, marginBottom:14, fontSize:13, display:'flex', alignItems:'center', gap:6, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.05em' }}>
          {widgetIcon(wt)} {wt} settings
        </div>

        {/* Dataset override — only shown when multiple datasets are attached to the report */}
        {datasets && Object.keys(datasets).length > 1 && fld('Dataset',
          <select value={datasetId} onChange={e => {
            const newId = e.target.value ? Number(e.target.value) : ''
            setDatasetId(newId)
            setRoleValues(Object.fromEntries((ROLE_SPECS[wt] ?? []).map(rf => [rf.role, ''])))
            setMultiRoleValues(Object.fromEntries((ROLE_SPECS[wt] ?? []).filter(rf => rf.multi).map(rf => [rf.role, []])))
            setSortCol('')
            setTableCols([])
          }} style={{ width:'100%' }}>
            <option value="">{primaryDatasetId && datasets[primaryDatasetId] ? `${datasets[primaryDatasetId].name} (default)` : '— report default —'}</option>
            {Object.values(datasets).map(ds => (
              <option key={ds.id} value={ds.id}>{ds.name}</option>
            ))}
          </select>
        )}

        {fld('Title', <input value={title} onChange={e => setTitle(e.target.value)} style={{ width:'100%' }} placeholder="Widget title" />)}

        <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
          <input
            id="rtl-toggle"
            type="checkbox"
            checked={rtl}
            onChange={e => setRtl(e.target.checked)}
          />
          <label htmlFor="rtl-toggle" style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', cursor: 'pointer' }}>
            RTL (Right to Left)
          </label>
        </div>

        {/* Text / Button */}
        {wt === 'text'   && fld('Content', <textarea value={content} onChange={e => setContent(e.target.value)} rows={4} style={{ width:'100%', resize:'vertical' }} placeholder="Enter text…" />)}
        {wt === 'button' && fld('Button label', <input value={label} onChange={e => setLabel(e.target.value)} style={{ width:'100%' }} />)}

        {wt !== 'text' && wt !== 'button' && (<>
          {/* Role fields — driven by ROLE_SPECS so each widget type declares its own fields
              instead of this component hardcoding a conditional per type. */}
          {(ROLE_SPECS[wt] ?? []).map(rf => {
            if (rf.multi) {
              const selected = multiRoleValues[rf.role] ?? []
              const options = colOptions.filter(o => numCols.some(c => c.name === o.value))
              return (
                <div key={rf.role}>
                  {fld(rf.label ?? rf.role, (
                    <div style={{ maxHeight:130, overflowY:'auto', display:'flex', flexDirection:'column', gap:3, background:'var(--surface2)', border:'1px solid var(--border)', borderRadius:6, padding:'6px 8px' }}>
                      {options.map(o => {
                        const idx = selected.indexOf(o.value)
                        return (
                          <label key={o.value} style={{ display:'flex', alignItems:'center', gap:6, fontSize:12, cursor:'pointer' }}>
                            <input type="checkbox" checked={idx !== -1} onChange={() => toggleMultiRole(rf.role, o.value)} />
                            <span style={{ color: idx !== -1 ? 'var(--text)' : 'var(--muted)' }}>{o.label}</span>
                            {idx !== -1 && <span style={{ marginLeft:'auto', fontSize:9, color:'var(--accent)' }}>#{idx + 1}</span>}
                          </label>
                        )
                      })}
                    </div>
                  ))}
                </div>
              )
            }
            const options = (rf.role === 'measure' || rf.role === 'measure2')
              ? numCols.map(c => ({ value: c.name, label: c.name }))
              : colOptions
            const placeholder = rf.role === 'measure' ? '— count rows —' : rf.role === 'category2' ? '— none —' : '— select column —'
            return (
              <div key={rf.role}>
                {fld(rf.label ?? rf.role, sel(roleValues[rf.role] ?? '', v => setRole(rf.role, v), options, placeholder))}
              </div>
            )
          })}

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
              {roleValues.measure ? ` of ${roleValues.measure}` : ' (row count)'}
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
                {effectiveCols.map(c => (
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
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8, marginBottom:8 }}>
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
                <option value="value">By Value</option>
                <option value="name">By Name</option>
              </select>
            </div>
          </div>
          {fld('Sort column (overrides sort by)',
            <select value={sortCol} onChange={e => setSortCol(e.target.value)} style={{ width:'100%' }}>
              <option value="">— use sort by above —</option>
              {colOptions.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          )}

          {fld('Row limit',
            <input type="number" value={limit} min={1} max={1000} onChange={e => setLimit(Number(e.target.value))} style={{ width:'100%' }} />
          )}

          {wt === 'histogram' && fld('Bins',
            <input type="number" value={bins} min={2} max={100} onChange={e => setBins(Number(e.target.value))} style={{ width:'100%' }} />
          )}

          {wt === 'needle' && fld('Baseline',
            <input type="number" value={baseline} onChange={e => setBaseline(Number(e.target.value))} style={{ width:'100%' }} />
          )}

          {wt === 'bubble' && fld('Fit Line',
            sel(fitLine, setFitLine, [
              { value: 'linear',    label: 'Linear' },
              { value: 'quadratic', label: 'Quadratic' },
              { value: 'cubic',     label: 'Cubic' },
              { value: 'best_fit',  label: 'Best Fit' },
            ], '— none —')
          )}

          {wt === 'gauge' && fld('Target value (fixed, optional)',
            <input type="number" value={targetValue} onChange={e => setTargetValue(e.target.value)} style={{ width:'100%' }} placeholder="leave blank to use Target column" />
          )}
        </>)}
      </div>

      {/* Visual interaction settings */}
      <InteractionSettings widget={widget} />
    </div>
  )
}

function widgetIcon(wt: string) {
  return ({ bar:'▬',line:'↗',pie:'◔',donut:'◯',scatter:'⁘',treemap:'⊞',step:'⊓',dot_plot:'⁚',needle:'↕',histogram:'▤',butterfly:'⋈',dual_axis_bar:'▥',dual_axis_line:'⤢',dual_axis_bar_line:'▧',dual_axis_time_series:'⟿',comparative_time_series:'⇄',numeric_series:'∿',bubble:'◉',bubble_change:'◎',correlation_matrix:'▦',heatmap:'▩',parallel_coordinates:'⫴',box_plot:'⊡',waterfall:'▨',gauge:'◐',schedule:'▭',vector_plot:'⇗',word_cloud:'☁',kpi:'◈',table:'☰',crosstab:'⊟',list:'≡',text:'T',button:'▶' } as any)[wt] ?? '◻'
}
