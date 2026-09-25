import { useState, type CSSProperties } from 'react'
import { calcColumnsApi } from '../../../services/api'
import type { CalcColumn, CalcColumnFormat, DatasetColumn } from '../../../services/api'
import { Z_MODAL_TOP } from '../../../lib/zIndex'
import ExpressionBuilder from '../../expr/ExpressionBuilder'
import { useModalDialog } from '../../ui/useModalDialog'
import { OP_GROUPS, type FuncCat } from './catalog'

interface BuilderProps {
  initial:   { name: string; expression: string; format?: CalcColumnFormat }
  datasetId: number
  columns:   DatasetColumn[]
  calcCols:  CalcColumn[]
  functionsCatalog: FuncCat[]
  onSave:    (cols: CalcColumn[]) => void
  onClose:   () => void
}

export function BuilderModal({ initial, datasetId, columns, calcCols, functionsCatalog, onSave, onClose }: BuilderProps) {
  const dialogRef = useModalDialog<HTMLDivElement>(onClose)
  const [name,       setName]       = useState(initial.name)
  const [expression, setExpression] = useState(initial.expression)
  const [preview,    setPreview]    = useState<{ ok:boolean; dtype?:string; sample?:unknown[]; error?:string } | null>(null)
  const [testing,    setTesting]    = useState(false)
  const [format, setFormat] = useState<CalcColumnFormat>(initial.format ?? { type: 'none' })
  const setFmt = <K extends keyof CalcColumnFormat>(k: K, v: CalcColumnFormat[K]) =>
    setFormat(p => ({ ...p, [k]: v }))

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

  // Styles
  const panelHd: CSSProperties = {
    fontSize: 11, fontWeight: 700, color: 'var(--muted)',
    textTransform: 'uppercase', letterSpacing: '.06em',
    padding: '0 0 5px', marginBottom: 4,
    borderBottom: '1px solid var(--border)',
  }

  return (
    <div style={{ position:'fixed', inset:0, zIndex:Z_MODAL_TOP, display:'flex', alignItems:'center', justifyContent:'center',
      background:'rgba(0,0,0,.6)', backdropFilter:'blur(3px)' }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}>

      <div ref={dialogRef} role="dialog" aria-modal="true"
        aria-label="Calculated column builder"
        style={{ background:'var(--surface)', border:'1px solid var(--border)', borderRadius:12,
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
            <ExpressionBuilder
              layout="panels"
              columns={columns.filter(c => c.dtype !== 'calculated')}
              attributeExtras={calcCols.map(c => ({ name: c.name }))}
              functionsCatalog={functionsCatalog}
              opGroups={OP_GROUPS}
              value={expression}
              onChange={next => { setExpression(next); setPreview(null) }}
              placeholder="e.g. salary * 12  or  IF(score > 80, 'Pass', 'Fail')"
            />
          </div>

          {/* ── Display Format ── */}
          <div style={{ background:'var(--surface2)', border:'1px solid var(--border)', borderRadius:7, padding:10 }}>
            <div style={{ ...panelHd, marginBottom:8 }}>Display Format</div>
            <div style={{ display:'flex', flexWrap:'wrap', gap:8, alignItems:'flex-end' }}>
              {/* Type selector */}
              <div>
                <div style={{ fontSize: 11, color:'var(--muted)', marginBottom:3 }}>Type</div>
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
                  <div style={{ fontSize: 11, color:'var(--muted)', marginBottom:3 }}>Decimals</div>
                  <input type="number" min={0} max={8} value={format.decimals ?? ''} placeholder="2"
                    onChange={e => setFmt('decimals', e.target.value === '' ? undefined : +e.target.value)}
                    style={{ width:60, fontSize:12, padding:'4px 7px' }} />
                </div>
              )}

              {/* Currency symbol */}
              {format.type === 'currency' && (
                <div>
                  <div style={{ fontSize: 11, color:'var(--muted)', marginBottom:3 }}>Symbol</div>
                  <input value={format.symbol ?? '$'} onChange={e => setFmt('symbol', e.target.value)}
                    style={{ width:56, fontSize:12, padding:'4px 7px' }} />
                </div>
              )}

              {/* Prefix / Suffix — number, integer, currency, percent */}
              {['number','integer','currency','percent'].includes(format.type) && (<>
                <div>
                  <div style={{ fontSize: 11, color:'var(--muted)', marginBottom:3 }}>Prefix</div>
                  <input value={format.prefix ?? ''} onChange={e => setFmt('prefix', e.target.value || undefined)}
                    placeholder="e.g. $"
                    style={{ width:60, fontSize:12, padding:'4px 7px' }} />
                </div>
                <div>
                  <div style={{ fontSize: 11, color:'var(--muted)', marginBottom:3 }}>Suffix</div>
                  <input value={format.suffix ?? ''} onChange={e => setFmt('suffix', e.target.value || undefined)}
                    placeholder="e.g. SAR"
                    style={{ width:60, fontSize:12, padding:'4px 7px' }} />
                </div>
              </>)}

              {/* Bar — min, max, color */}
              {format.type === 'bar' && (<>
                <div>
                  <div style={{ fontSize: 11, color:'var(--muted)', marginBottom:3 }}>Min</div>
                  <input type="number" value={format.min ?? ''} placeholder="0"
                    onChange={e => setFmt('min', e.target.value === '' ? undefined : +e.target.value)}
                    style={{ width:70, fontSize:12, padding:'4px 7px' }} />
                </div>
                <div>
                  <div style={{ fontSize: 11, color:'var(--muted)', marginBottom:3 }}>Max</div>
                  <input type="number" value={format.max ?? ''} placeholder="100"
                    onChange={e => setFmt('max', e.target.value === '' ? undefined : +e.target.value)}
                    style={{ width:70, fontSize:12, padding:'4px 7px' }} />
                </div>
                <div>
                  <div style={{ fontSize: 11, color:'var(--muted)', marginBottom:3 }}>Color</div>
                  <input type="color" value={format.color ?? '#6c8fff'}
                    onChange={e => setFmt('color', e.target.value)}
                    style={{ width:44, height:28, padding:'2px', border:'1px solid var(--border)', borderRadius:4, cursor:'pointer', background:'var(--surface)' }} />
                </div>
              </>)}

              {/* Badge — low/high thresholds */}
              {format.type === 'badge' && (<>
                <div>
                  <div style={{ fontSize: 11, color:'var(--muted)', marginBottom:3 }}>Low ↓ (red)</div>
                  <input type="number" value={format.thresholds?.[0] ?? ''} placeholder="33"
                    onChange={e => {
                      const lo = e.target.value === '' ? 33 : +e.target.value
                      setFmt('thresholds', [lo, format.thresholds?.[1] ?? 66])
                    }}
                    style={{ width:70, fontSize:12, padding:'4px 7px' }} />
                </div>
                <div>
                  <div style={{ fontSize: 11, color:'var(--muted)', marginBottom:3 }}>High ↑ (green)</div>
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
            disabled={testing || !expression.trim()} title={!expression.trim() ? 'Write an expression first' : undefined} style={{ fontSize:12 }}>
            {testing ? 'Testing…' : '▶ Test'}
          </button>
          <button className="btn btn-primary btn-sm" onClick={save}
            disabled={!name.trim() || !expression.trim()} title={!name.trim() ? 'Name the column first' : !expression.trim() ? 'Write an expression first' : undefined}
            style={{ fontSize:12, marginInlineStart:'auto', minWidth:100 }}>
            Save Column
          </button>
        </div>
      </div>
    </div>
  )
}
