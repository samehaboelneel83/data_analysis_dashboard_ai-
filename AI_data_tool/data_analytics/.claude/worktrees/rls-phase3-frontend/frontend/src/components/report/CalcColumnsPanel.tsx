import { useState, useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { calcColumnsApi } from '../../services/api'
import type { CalcColumn, CalcColumnFormat, DatasetColumn } from '../../services/api'

// ── Expression builder data ───────────────────────────────────────────────────

interface FuncItem { label: string; snippet: string; back: number; hint: string }
interface FuncCat  { label: string; color: string; items: FuncItem[] }

const FUNC_CATS: FuncCat[] = [
  {
    label: 'Numeric', color: '#60a5fa',
    items: [
      { label: 'abs(x)',       snippet: 'abs()',        back: 1, hint: 'Absolute value' },
      { label: 'round(x,n)',   snippet: 'round(, 2)',   back: 4, hint: 'Round to n decimals' },
      { label: 'sqrt(x)',      snippet: 'sqrt()',       back: 1, hint: 'Square root' },
      { label: 'floor(x)',     snippet: 'floor()',      back: 1, hint: 'Round down to integer' },
      { label: 'ceil(x)',      snippet: 'ceil()',       back: 1, hint: 'Round up to integer' },
      { label: 'log(x)',       snippet: 'log()',        back: 1, hint: 'Natural logarithm' },
      { label: 'exp(x)',       snippet: 'exp()',        back: 1, hint: 'e to the power x' },
      { label: 'pow(x,n)',     snippet: 'pow(, 2)',     back: 4, hint: 'x raised to power n' },
      { label: 'min(x,y)',     snippet: 'min(, )',      back: 3, hint: 'Minimum of two values' },
      { label: 'max(x,y)',     snippet: 'max(, )',      back: 3, hint: 'Maximum of two values' },
    ],
  },
  {
    label: 'Text', color: '#34d399',
    items: [
      { label: 'upper(col)',         snippet: '.str.upper()',         back: 0, hint: 'Convert to uppercase' },
      { label: 'lower(col)',         snippet: '.str.lower()',         back: 0, hint: 'Convert to lowercase' },
      { label: 'length(col)',        snippet: '.str.len()',           back: 0, hint: 'Count characters' },
      { label: 'trim(col)',          snippet: '.str.strip()',         back: 0, hint: 'Remove surrounding spaces' },
      { label: 'contains(col,"t")',  snippet: '.str.contains("")',   back: 2, hint: 'True if text found inside' },
      { label: 'replace(col,"a","b")',snippet: '.str.replace("", "")',back: 6, hint: 'Replace one text with another' },
      { label: 'to_text(x)',         snippet: 'str()',               back: 1, hint: 'Convert value to text' },
    ],
  },
  {
    label: 'Date', color: '#f59e0b',
    items: [
      { label: 'year(col)',    snippet: '.dt.year',      back: 0, hint: 'Extract year from date' },
      { label: 'month(col)',   snippet: '.dt.month',     back: 0, hint: 'Month number (1–12)' },
      { label: 'day(col)',     snippet: '.dt.day',       back: 0, hint: 'Day of month (1–31)' },
      { label: 'hour(col)',    snippet: '.dt.hour',      back: 0, hint: 'Hour of day (0–23)' },
      { label: 'weekday(col)', snippet: '.dt.dayofweek', back: 0, hint: 'Day of week (0=Mon, 6=Sun)' },
    ],
  },
  {
    label: 'Conditional', color: '#c084fc',
    items: [
      { label: 'IF(cond,yes,no)',           snippet: 'IF(, , )',           back: 5, hint: 'Return yes if condition true, else no' },
      { label: 'SWITCH(col,v1,r1,default)', snippet: 'SWITCH(, , , )',     back: 7, hint: 'Map values: col==v1→r1, else default' },
      { label: 'isnull(col)',               snippet: 'isnull()',           back: 1, hint: 'True if value is missing / null' },
      { label: 'fillna(col,val)',           snippet: '.fillna()',          back: 1, hint: 'Replace null with a value' },
    ],
  },
  {
    label: 'Aggregation', color: '#f472b6',
    items: [
      { label: 'SUM(col)',       snippet: 'SUM()',       back: 1, hint: 'Total sum of all values in column' },
      { label: 'AVG(col)',       snippet: 'AVG()',       back: 1, hint: 'Average (mean) of all values' },
      { label: 'MEDIAN(col)',    snippet: 'MEDIAN()',    back: 1, hint: 'Middle value (50th percentile)' },
      { label: 'COUNT(col)',     snippet: 'COUNT()',     back: 1, hint: 'Count of non-null values' },
      { label: 'COUNTD(col)',    snippet: 'COUNTD()',    back: 1, hint: 'Count of distinct (unique) values' },
      { label: 'STDEV(col)',     snippet: 'STDEV()',     back: 1, hint: 'Standard deviation' },
      { label: 'VARIANCE(col)',  snippet: 'VARIANCE()',  back: 1, hint: 'Statistical variance' },
      { label: 'PCT_TOTAL(col)', snippet: 'PCT_TOTAL()', back: 1, hint: '% share of column total (0–100)' },
      { label: 'NORMALIZE(col)', snippet: 'NORMALIZE()', back: 1, hint: 'Scale to 0–1 range (min-max)' },
      { label: 'ZSCORE(col)',    snippet: 'ZSCORE()',    back: 1, hint: 'Standard deviations from mean' },
    ],
  },
  {
    label: 'Running & Rank', color: '#fb923c',
    items: [
      { label: 'CUMSUM(col)',    snippet: 'CUMSUM()',    back: 1, hint: 'Running cumulative sum' },
      { label: 'CUMPCT(col)',    snippet: 'CUMPCT()',    back: 1, hint: 'Cumulative % of total' },
      { label: 'RANK(col)',      snippet: 'RANK()',      back: 1, hint: 'Rank each row (1 = smallest)' },
      { label: 'DIFF(col)',      snippet: 'DIFF()',      back: 1, hint: 'Difference from previous row' },
      { label: 'LAG(col, n)',    snippet: 'LAG(, 1)',    back: 4, hint: 'Value n rows back (default 1)' },
      { label: 'LEAD(col, n)',   snippet: 'LEAD(, 1)',   back: 4, hint: 'Value n rows ahead (default 1)' },
    ],
  },
  {
    label: 'Group By', color: '#2dd4bf',
    items: [
      { label: 'GROUPSUM(col,grp)',   snippet: 'GROUPSUM(, )',   back: 3, hint: 'Sum of col within each group value' },
      { label: 'GROUPAVG(col,grp)',   snippet: 'GROUPAVG(, )',   back: 3, hint: 'Average of col within each group' },
      { label: 'GROUPCOUNT(col,grp)', snippet: 'GROUPCOUNT(, )', back: 3, hint: 'Count within each group' },
      { label: 'GROUPRANK(col,grp)',  snippet: 'GROUPRANK(, )',  back: 3, hint: 'Rank within each group' },
      { label: 'GROUPMIN(col,grp)',   snippet: 'GROUPMIN(, )',   back: 3, hint: 'Minimum within each group' },
      { label: 'GROUPMAX(col,grp)',   snippet: 'GROUPMAX(, )',   back: 3, hint: 'Maximum within each group' },
      { label: 'GROUPPCT(col,grp)',   snippet: 'GROUPPCT(, )',   back: 3, hint: '% of group total' },
    ],
  },
]

interface OpItem { label: string; snippet: string; back?: number }
const OP_GROUPS: { label: string; items: OpItem[] }[] = [
  { label: 'Arithmetic', items: [
    { label: '+',  snippet: ' + '  },
    { label: '-',  snippet: ' - '  },
    { label: '*',  snippet: ' * '  },
    { label: '/',  snippet: ' / '  },
    { label: '**', snippet: ' ** ' },
    { label: '%',  snippet: ' % '  },
  ]},
  { label: 'Comparison', items: [
    { label: '==', snippet: ' == ' },
    { label: '!=', snippet: ' != ' },
    { label: '>',  snippet: ' > '  },
    { label: '<',  snippet: ' < '  },
    { label: '>=', snippet: ' >= ' },
    { label: '<=', snippet: ' <= ' },
    { label: 'IN', snippet: '.isin([])', back: 1, hint: 'True if value is in a list' } as OpItem & { hint: string },
  ]},
  { label: 'Logical', items: [
    { label: 'and', snippet: ' and ' },
    { label: 'or',  snippet: ' or '  },
    { label: 'not', snippet: ' not ' },
    { label: '(',   snippet: '('     },
    { label: ')',   snippet: ')'     },
  ]},
]

// Wrap column name in backticks if it contains spaces or starts with a digit
const colRef = (name: string) =>
  /\s/.test(name) || /^\d/.test(name) ? `\`${name}\`` : name

// ── Props ─────────────────────────────────────────────────────────────────────

interface Props {
  datasetId: number
  columns: DatasetColumn[]
  onChanged: (cols: CalcColumn[]) => void
}

const BLANK = { name: '', expression: '', format: undefined as CalcColumnFormat | undefined }

// ── Main component ────────────────────────────────────────────────────────────

export default function CalcColumnsPanel({ datasetId, columns, onChanged }: Props) {
  const [calcCols, setCalcCols] = useState<CalcColumn[]>([])
  const [editing,  setEditing]  = useState<typeof BLANK | null>(null)  // null = modal closed

  useEffect(() => {
    calcColumnsApi.list(datasetId).then(cols => { setCalcCols(cols); onChanged(cols) })
  }, [datasetId])

  const openAdd  = ()                => setEditing({ ...BLANK })
  const openEdit = (col: CalcColumn) => setEditing({ name: col.name, expression: col.expression, format: col.format })

  const handleSaved = (updated: CalcColumn[]) => {
    setCalcCols(updated); onChanged(updated); setEditing(null)
  }

  const del = async (name: string) => {
    const updated = await calcColumnsApi.delete(datasetId, name)
    setCalcCols(updated); onChanged(updated)
  }

  return (
    <div>
      {/* Header */}
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:8 }}>
        <span style={{ fontSize:10, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em' }}>
          ƒx Calculated columns
        </span>
        <button className="btn btn-ghost btn-sm" onClick={openAdd} style={{ fontSize:10, padding:'2px 7px' }}>
          + Add
        </button>
      </div>

      {/* Existing columns list */}
      {calcCols.map(col => (
        <div key={col.name} style={{ display:'flex', alignItems:'center', gap:5, padding:'5px 7px',
          background:'var(--surface2)', border:'1px solid var(--border)', borderRadius:5, marginBottom:4 }}>
          <span style={{ color:'var(--accent)', fontSize:11, flexShrink:0 }}>ƒx</span>
          <div style={{ flex:1, minWidth:0 }}>
            <div style={{ fontSize:12, fontWeight:600, color:'var(--text)' }}>{col.name}</div>
            <div style={{ fontSize:10, color:'var(--muted)', overflow:'hidden', textOverflow:'ellipsis',
              whiteSpace:'nowrap', fontFamily:'var(--mono)' }}>{col.expression}</div>
          </div>
          <button style={{ background:'none', border:'none', cursor:'pointer', color:'var(--muted)', fontSize:12, padding:'0 3px' }}
            title="Edit" onClick={() => openEdit(col)}>✏</button>
          <button style={{ background:'none', border:'none', cursor:'pointer', color:'var(--muted)', fontSize:14, padding:'0 3px' }}
            title="Delete" onClick={() => del(col.name)}>×</button>
        </div>
      ))}

      {calcCols.length === 0 && (
        <p style={{ fontSize:11, color:'var(--muted)', textAlign:'center', padding:'8px 0' }}>
          No calculated columns yet
        </p>
      )}

      {/* Builder modal */}
      {editing !== null && createPortal(
        <BuilderModal
          initial={editing}
          datasetId={datasetId}
          columns={columns}
          calcCols={calcCols}
          onSave={handleSaved}
          onClose={() => setEditing(null)}
        />,
        document.body,
      )}
    </div>
  )
}

// ── Builder modal ─────────────────────────────────────────────────────────────

interface BuilderProps {
  initial:   { name: string; expression: string; format?: CalcColumnFormat }
  datasetId: number
  columns:   DatasetColumn[]
  calcCols:  CalcColumn[]
  onSave:    (cols: CalcColumn[]) => void
  onClose:   () => void
}

function BuilderModal({ initial, datasetId, columns, calcCols, onSave, onClose }: BuilderProps) {
  const [name,       setName]       = useState(initial.name)
  const [expression, setExpression] = useState(initial.expression)
  const [preview,    setPreview]    = useState<{ ok:boolean; dtype?:string; sample?:unknown[]; error?:string } | null>(null)
  const [testing,    setTesting]    = useState(false)
  const [openCats,   setOpenCats]   = useState<Record<string, boolean>>(
    Object.fromEntries(FUNC_CATS.map(c => [c.label, true]))
  )
  const [format, setFormat] = useState<CalcColumnFormat>(initial.format ?? { type: 'none' })
  const setFmt = <K extends keyof CalcColumnFormat>(k: K, v: CalcColumnFormat[K]) =>
    setFormat(p => ({ ...p, [k]: v }))

  const taRef = useRef<HTMLTextAreaElement>(null)

  // Insert text at cursor position, then restore cursor
  const insert = (snippet: string, back = 0) => {
    const ta = taRef.current
    const start = ta?.selectionStart ?? expression.length
    const end   = ta?.selectionEnd   ?? expression.length
    const next  = expression.slice(0, start) + snippet + expression.slice(end)
    const cursor = start + snippet.length - back
    setExpression(next)
    setPreview(null)
    requestAnimationFrame(() => {
      ta?.focus()
      ta?.setSelectionRange(cursor, cursor)
    })
  }

  const insertCol = (col: DatasetColumn | CalcColumn) => insert(colRef(col.name))

  const insertOp = (op: OpItem) => insert(op.snippet, op.back ?? 0)

  const test = async () => {
    if (!expression.trim()) return
    setTesting(true)
    try {
      setPreview(await calcColumnsApi.preview(datasetId, expression.trim()))
    } catch (err: any) {
      const msg = err?.response?.data?.detail ?? err?.message ?? 'Preview failed'
      setPreview({ ok: false, error: msg })
    } finally {
      setTesting(false)
    }
  }

  const save = async () => {
    if (!name.trim() || !expression.trim()) return
    const fmt = format.type === 'none' ? undefined : format
    const updated = await calcColumnsApi.save(datasetId, { name: name.trim(), expression: expression.trim(), format: fmt })
    onSave(updated)
  }

  const toggleCat = (label: string) =>
    setOpenCats(p => ({ ...p, [label]: !p[label] }))

  // Styles
  const panelHd: React.CSSProperties = {
    fontSize: 10, fontWeight: 700, color: 'var(--muted)',
    textTransform: 'uppercase', letterSpacing: '.06em',
    padding: '0 0 5px', marginBottom: 4,
    borderBottom: '1px solid var(--border)',
  }
  const chip = (active = false): React.CSSProperties => ({
    display: 'block', width: '100%', textAlign: 'left',
    padding: '3px 7px', margin: '1px 0', border: 'none',
    borderRadius: 4, cursor: 'pointer', fontSize: 11,
    fontFamily: 'var(--mono)',
    background: active ? 'rgba(108,143,255,.15)' : 'transparent',
    color: 'var(--text)',
    transition: 'background .1s',
  })

  return (
    <div style={{ position:'fixed', inset:0, zIndex:9999, display:'flex', alignItems:'center', justifyContent:'center',
      background:'rgba(0,0,0,.6)', backdropFilter:'blur(3px)' }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}>

      <div style={{ background:'var(--surface)', border:'1px solid var(--border)', borderRadius:12,
        width:720, maxWidth:'95vw', maxHeight:'90vh', display:'flex', flexDirection:'column',
        boxShadow:'0 24px 64px rgba(0,0,0,.4)', overflow:'hidden' }}>

        {/* ── Modal header ── */}
        <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between',
          padding:'14px 18px', borderBottom:'1px solid var(--border)', flexShrink:0 }}>
          <div style={{ fontWeight:700, fontSize:14, color:'var(--accent)' }}>ƒx Expression Builder</div>
          <button onClick={onClose} style={{ background:'none', border:'none', cursor:'pointer',
            color:'var(--muted)', fontSize:20, lineHeight:1, padding:'0 4px' }}>×</button>
        </div>

        <div style={{ flex:1, overflowY:'auto', padding:16, display:'flex', flexDirection:'column', gap:12 }}>

          {/* ── Column name ── */}
          <div>
            <label style={{ ...panelHd, borderBottom:'none', marginBottom:4 }}>Column name</label>
            <input value={name} onChange={e => setName(e.target.value)}
              placeholder="e.g. Annual Salary"
              style={{ width:'100%', fontSize:13, padding:'7px 10px' }} />
          </div>

          {/* ── Expression ── */}
          <div>
            <label style={{ ...panelHd, borderBottom:'none', marginBottom:4 }}>
              Expression — click items below to build, or type directly
            </label>
            <textarea ref={taRef} value={expression}
              onChange={e => { setExpression(e.target.value); setPreview(null) }}
              rows={3}
              placeholder="e.g. salary * 12  or  IF(score > 80, 'Pass', 'Fail')"
              style={{ width:'100%', fontFamily:'var(--mono)', fontSize:12,
                padding:'8px 10px', resize:'vertical', lineHeight:1.6 }} />
          </div>

          {/* ── 3 panels ── */}
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:8, minHeight:220 }}>

            {/* Panel 1: Attributes */}
            <div style={{ background:'var(--surface2)', border:'1px solid var(--border)',
              borderRadius:7, padding:10, overflow:'hidden', display:'flex', flexDirection:'column' }}>
              <div style={panelHd}>Attributes</div>
              <div style={{ flex:1, overflowY:'auto' }}>
                {/* Regular columns */}
                {columns.filter(c => c.dtype !== 'calculated').map(col => (
                  <button key={col.name} style={chip()} title={`${col.name} (${col.dtype})`}
                    onClick={() => insertCol(col)}
                    onMouseEnter={e => (e.currentTarget.style.background = 'rgba(108,143,255,.12)')}
                    onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
                    <span style={{ color:'var(--text)' }}>{col.name}</span>
                    <span style={{ color:'var(--muted)', fontSize:9, marginLeft:5 }}>{col.dtype}</span>
                  </button>
                ))}
                {/* Calculated columns */}
                {calcCols.map(col => (
                  <button key={col.name} style={chip()} title={`ƒx ${col.name}`}
                    onClick={() => insertCol(col)}
                    onMouseEnter={e => (e.currentTarget.style.background = 'rgba(108,143,255,.12)')}
                    onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
                    <span style={{ color:'var(--accent)', marginRight:4 }}>ƒx</span>
                    <span style={{ color:'var(--text)' }}>{col.name}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Panel 2: Functions */}
            <div style={{ background:'var(--surface2)', border:'1px solid var(--border)',
              borderRadius:7, padding:10, overflow:'hidden', display:'flex', flexDirection:'column' }}>
              <div style={panelHd}>Functions</div>
              <div style={{ flex:1, overflowY:'auto' }}>
                {FUNC_CATS.map(cat => (
                  <div key={cat.label} style={{ marginBottom:4 }}>
                    <button
                      onClick={() => toggleCat(cat.label)}
                      style={{ display:'flex', alignItems:'center', gap:5, width:'100%',
                        background:'none', border:'none', cursor:'pointer', padding:'3px 0',
                        fontSize:10, fontWeight:700, color:cat.color,
                        textTransform:'uppercase', letterSpacing:'.06em' }}>
                      <span style={{ fontSize:9 }}>{openCats[cat.label] ? '▼' : '▶'}</span>
                      {cat.label}
                    </button>
                    {openCats[cat.label] && cat.items.map(fn => (
                      <button key={fn.label} style={chip()} title={fn.hint}
                        onClick={() => insert(fn.snippet, fn.back)}
                        onMouseEnter={e => (e.currentTarget.style.background = 'rgba(108,143,255,.12)')}
                        onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
                        {fn.label}
                      </button>
                    ))}
                  </div>
                ))}
              </div>
            </div>

            {/* Panel 3: Operators */}
            <div style={{ background:'var(--surface2)', border:'1px solid var(--border)',
              borderRadius:7, padding:10, overflow:'hidden', display:'flex', flexDirection:'column' }}>
              <div style={panelHd}>Operators</div>
              <div style={{ flex:1, overflowY:'auto' }}>
                {OP_GROUPS.map(grp => (
                  <div key={grp.label} style={{ marginBottom:10 }}>
                    <div style={{ fontSize:9, fontWeight:700, color:'var(--muted)',
                      textTransform:'uppercase', letterSpacing:'.06em', marginBottom:5 }}>
                      {grp.label}
                    </div>
                    <div style={{ display:'flex', flexWrap:'wrap', gap:4 }}>
                      {grp.items.map(op => (
                        <button key={op.label} onClick={() => insertOp(op)}
                          title={(op as any).hint}
                          style={{ padding:'4px 9px', border:'1px solid var(--border)',
                            borderRadius:5, cursor:'pointer', fontSize:12,
                            fontFamily:'var(--mono)', fontWeight:600,
                            background:'var(--surface)', color:'var(--text)',
                            transition:'border-color .1s, background .1s' }}
                          onMouseEnter={e => {
                            e.currentTarget.style.borderColor = 'var(--accent)'
                            e.currentTarget.style.background  = 'rgba(108,143,255,.12)'
                          }}
                          onMouseLeave={e => {
                            e.currentTarget.style.borderColor = 'var(--border)'
                            e.currentTarget.style.background  = 'var(--surface)'
                          }}>
                          {op.label}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* ── Display Format ── */}
          <div style={{ background:'var(--surface2)', border:'1px solid var(--border)', borderRadius:7, padding:10 }}>
            <div style={{ ...panelHd, marginBottom:8 }}>Display Format</div>
            <div style={{ display:'flex', flexWrap:'wrap', gap:8, alignItems:'flex-end' }}>
              {/* Type selector */}
              <div>
                <div style={{ fontSize:10, color:'var(--muted)', marginBottom:3 }}>Type</div>
                <select value={format.type} onChange={e => setFmt('type', e.target.value as CalcColumnFormat['type'])}
                  style={{ fontSize:12, padding:'4px 7px', background:'var(--surface)', border:'1px solid var(--border)', borderRadius:4, color:'var(--text)' }}>
                  <option value="none">None (raw)</option>
                  <option value="number">Number  1,234.56</option>
                  <option value="integer">Integer  1,235</option>
                  <option value="currency">Currency  $ 1,234</option>
                  <option value="percent">Percent  12.3%</option>
                  <option value="bar">Progress Bar  ▓░░</option>
                  <option value="badge">Color Badge  ●</option>
                  <option value="trend">Trend Arrow  ↑↓</option>
                </select>
              </div>

              {/* Decimals — shown for number / integer / currency / percent / badge / trend */}
              {['number','integer','currency','percent','badge','trend'].includes(format.type) && (
                <div>
                  <div style={{ fontSize:10, color:'var(--muted)', marginBottom:3 }}>Decimals</div>
                  <input type="number" min={0} max={8} value={format.decimals ?? ''} placeholder="2"
                    onChange={e => setFmt('decimals', e.target.value === '' ? undefined : +e.target.value)}
                    style={{ width:60, fontSize:12, padding:'4px 7px' }} />
                </div>
              )}

              {/* Currency symbol */}
              {format.type === 'currency' && (
                <div>
                  <div style={{ fontSize:10, color:'var(--muted)', marginBottom:3 }}>Symbol</div>
                  <input value={format.symbol ?? '$'} onChange={e => setFmt('symbol', e.target.value)}
                    style={{ width:56, fontSize:12, padding:'4px 7px' }} />
                </div>
              )}

              {/* Prefix / Suffix — number, integer, currency, percent */}
              {['number','integer','currency','percent'].includes(format.type) && (<>
                <div>
                  <div style={{ fontSize:10, color:'var(--muted)', marginBottom:3 }}>Prefix</div>
                  <input value={format.prefix ?? ''} onChange={e => setFmt('prefix', e.target.value || undefined)}
                    placeholder="e.g. $"
                    style={{ width:60, fontSize:12, padding:'4px 7px' }} />
                </div>
                <div>
                  <div style={{ fontSize:10, color:'var(--muted)', marginBottom:3 }}>Suffix</div>
                  <input value={format.suffix ?? ''} onChange={e => setFmt('suffix', e.target.value || undefined)}
                    placeholder="e.g. SAR"
                    style={{ width:60, fontSize:12, padding:'4px 7px' }} />
                </div>
              </>)}

              {/* Bar — min, max, color */}
              {format.type === 'bar' && (<>
                <div>
                  <div style={{ fontSize:10, color:'var(--muted)', marginBottom:3 }}>Min</div>
                  <input type="number" value={format.min ?? ''} placeholder="0"
                    onChange={e => setFmt('min', e.target.value === '' ? undefined : +e.target.value)}
                    style={{ width:70, fontSize:12, padding:'4px 7px' }} />
                </div>
                <div>
                  <div style={{ fontSize:10, color:'var(--muted)', marginBottom:3 }}>Max</div>
                  <input type="number" value={format.max ?? ''} placeholder="100"
                    onChange={e => setFmt('max', e.target.value === '' ? undefined : +e.target.value)}
                    style={{ width:70, fontSize:12, padding:'4px 7px' }} />
                </div>
                <div>
                  <div style={{ fontSize:10, color:'var(--muted)', marginBottom:3 }}>Color</div>
                  <input type="color" value={format.color ?? '#6c8fff'}
                    onChange={e => setFmt('color', e.target.value)}
                    style={{ width:44, height:28, padding:'2px', border:'1px solid var(--border)', borderRadius:4, cursor:'pointer', background:'var(--surface)' }} />
                </div>
              </>)}

              {/* Badge — low/high thresholds */}
              {format.type === 'badge' && (<>
                <div>
                  <div style={{ fontSize:10, color:'var(--muted)', marginBottom:3 }}>Low ↓ (red)</div>
                  <input type="number" value={format.thresholds?.[0] ?? ''} placeholder="33"
                    onChange={e => {
                      const lo = e.target.value === '' ? 33 : +e.target.value
                      setFmt('thresholds', [lo, format.thresholds?.[1] ?? 66])
                    }}
                    style={{ width:70, fontSize:12, padding:'4px 7px' }} />
                </div>
                <div>
                  <div style={{ fontSize:10, color:'var(--muted)', marginBottom:3 }}>High ↑ (green)</div>
                  <input type="number" value={format.thresholds?.[1] ?? ''} placeholder="66"
                    onChange={e => {
                      const hi = e.target.value === '' ? 66 : +e.target.value
                      setFmt('thresholds', [format.thresholds?.[0] ?? 33, hi])
                    }}
                    style={{ width:70, fontSize:12, padding:'4px 7px' }} />
                </div>
              </>)}
            </div>
          </div>

          {/* ── Preview result ── */}
          {preview && (
            <div style={{ padding:'8px 12px', borderRadius:6, fontSize:12,
              background: preview.ok ? 'rgba(52,211,153,.08)' : 'rgba(248,113,113,.08)',
              border: `1px solid ${preview.ok ? '#34d399' : '#f87171'}` }}>
              {preview.ok
                ? <><span style={{ color:'#34d399', fontWeight:700 }}>✓ {preview.dtype}</span>
                    {' — '}{preview.sample?.slice(0, 6).map(String).join(', ')}</>
                : <span style={{ color:'#f87171' }}>✗ {preview.error}</span>}
            </div>
          )}
        </div>

        {/* ── Footer ── */}
        <div style={{ display:'flex', gap:8, padding:'12px 16px',
          borderTop:'1px solid var(--border)', flexShrink:0 }}>
          <button className="btn btn-ghost btn-sm" onClick={onClose} style={{ fontSize:12 }}>
            Cancel
          </button>
          <button className="btn btn-ghost btn-sm" onClick={test}
            disabled={testing || !expression.trim()} style={{ fontSize:12 }}>
            {testing ? 'Testing…' : '▶ Test'}
          </button>
          <button className="btn btn-primary btn-sm" onClick={save}
            disabled={!name.trim() || !expression.trim()}
            style={{ fontSize:12, marginLeft:'auto', minWidth:100 }}>
            Save Column
          </button>
        </div>
      </div>
    </div>
  )
}
