import { useState, useCallback } from 'react'
import { MENA_CURRENCIES } from '../../lib/arabicFormats'
import { columnFormatsApi } from '../../services/api'
import type { CalcColumnFormat, DatasetColumn } from '../../services/api'

interface Props {
  datasetId: number
  columns: DatasetColumn[]
  columnFormats: Record<string, CalcColumnFormat>
  onChanged: (formats: Record<string, CalcColumnFormat>) => void
}

const FMT_TYPES: { value: CalcColumnFormat['type']; label: string }[] = [
  { value: 'none',     label: 'None'           },
  { value: 'number',   label: '# Number'       },
  { value: 'integer',  label: '0 Integer'      },
  { value: 'currency', label: '$ Currency'     },
  { value: 'percent',  label: '% Percent'      },
  { value: 'bar',      label: '▓ Progress Bar' },
  { value: 'badge',    label: '● Color Badge'  },
  { value: 'trend',    label: '↑ Trend Arrow'  },
  { value: 'colorscale', label: '🎨 Color Scale' },
  { value: 'icon',       label: '🔴 Icon Set'    },
]

export default function ColumnFormatsPanel({ datasetId, columns, columnFormats: initial, onChanged }: Props) {
  const [formats, setFormats] = useState<Record<string, CalcColumnFormat>>(initial ?? {})

  const save = useCallback(async (colName: string, fmt: CalcColumnFormat | null) => {
    const updated = await columnFormatsApi.set(datasetId, colName, fmt)
    setFormats(updated)
    onChanged(updated)
  }, [datasetId, onChanged])

  const setField = (colName: string, key: keyof CalcColumnFormat, value: unknown) => {
    const prev = formats[colName] ?? { type: 'none' }
    const next = { ...prev, [key]: value }
    setFormats(p => ({ ...p, [colName]: next }))
    save(colName, next)
  }

  const setType = (colName: string, type: CalcColumnFormat['type']) => {
    if (type === 'none') {
      setFormats(p => { const n = { ...p }; delete n[colName]; return n })
      save(colName, null)
    } else {
      const next: CalcColumnFormat = { ...formats[colName], type }
      setFormats(p => ({ ...p, [colName]: next }))
      save(colName, next)
    }
  }

  const regularCols = columns.filter(c => c.dtype !== 'calculated')

  const inp: React.CSSProperties = { fontSize: 11, padding: '3px 6px', width: '100%',
    background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text)' }

  return (
    <div>
      <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase',
        letterSpacing: '.06em', marginBottom: 8 }}>
        Display Formats
      </div>

      {regularCols.map(col => {
        const fmt = formats[col.name] ?? { type: 'none' }
        const active = fmt.type !== 'none'

        return (
          <div key={col.name} style={{ marginBottom: 4, border: '1px solid var(--border)',
            borderRadius: 5, background: 'var(--surface2)', overflow: 'hidden' }}>

            {/* Header row */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '5px 8px' }}>
              <span style={{ flex: 1, fontSize: 11, fontWeight: active ? 600 : 400,
                color: active ? 'var(--text)' : 'var(--muted)', overflow: 'hidden',
                textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {col.name}
              </span>
              <span style={{ fontSize: 9, color: 'var(--muted)', flexShrink: 0 }}>{col.dtype}</span>
              <select value={fmt.type}
                onChange={e => setType(col.name, e.target.value as CalcColumnFormat['type'])}
                style={{ ...inp, width: 'auto', fontSize: 11, flexShrink: 0 }}>
                {FMT_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
            </div>

            {/* Options row — shown when format is active */}
            {active && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, padding: '4px 8px 7px',
                borderTop: '1px solid var(--border)', background: 'color-mix(in srgb, var(--accent) 4%, transparent)' }}>

                {/* Decimals */}
                {['number','integer','currency','percent','badge','trend','colorscale','icon'].includes(fmt.type) && (
                  <label style={{ display:'flex', flexDirection:'column', gap:2, width:50 }}>
                    <span style={{ fontSize:9, color:'var(--muted)' }}>Decimals</span>
                    <input type="number" min={0} max={8} value={fmt.decimals ?? ''} placeholder="2"
                      style={inp}
                      onChange={e => setField(col.name, 'decimals', e.target.value === '' ? undefined : +e.target.value)}
                      onBlur={e => setField(col.name, 'decimals', e.target.value === '' ? undefined : +e.target.value)} />
                  </label>
                )}

                {/* Display units — an axis reading "1.2M" instead of "1,200,000" */}
                {['number','integer','currency','percent','badge','trend','colorscale','icon'].includes(fmt.type) && (
                  <label style={{ display:'flex', flexDirection:'column', gap:2, width:78 }}>
                    <span style={{ fontSize:9, color:'var(--muted)' }}>Units</span>
                    <select value={fmt.scale ?? 'none'} style={inp}
                      aria-label={`Display units for ${col.name}`}
                      onChange={e => setField(col.name, 'scale',
                        e.target.value === 'none' ? undefined : e.target.value)}>
                      <option value="none">Full number</option>
                      <option value="auto">Auto (K/M/B)</option>
                      <option value="thousands">Thousands</option>
                      <option value="millions">Millions</option>
                      <option value="billions">Billions</option>
                    </select>
                  </label>
                )}

                {/* Currency symbol */}
                {fmt.type === 'currency' && (<>
                  <label style={{ display:'flex', flexDirection:'column', gap:2, width:64 }}>
                    <span style={{ fontSize:9, color:'var(--muted)' }}>Symbol</span>
                    {/* Suggests the region's currencies in both scripts (Phase 7.5). */}
                    <input value={fmt.symbol ?? '$'} style={inp} list="mena-currencies" dir="auto"
                      aria-label={`${col.name} currency symbol`}
                      onChange={e => setField(col.name, 'symbol', e.target.value)}
                      onBlur={e => setField(col.name, 'symbol', e.target.value)} />
                    <datalist id="mena-currencies">
                      {MENA_CURRENCIES.flatMap(c => [
                        <option key={`${c.code}-ar`} value={c.ar}>{c.name}</option>,
                        <option key={c.code} value={c.code}>{c.name}</option>,
                      ])}
                    </datalist>
                  </label>
                  <label style={{ display:'flex', flexDirection:'column', gap:2, width:70 }}>
                    <span style={{ fontSize:9, color:'var(--muted)' }}>Symbol goes</span>
                    <select value={fmt.symbol_position ?? ''} style={inp} aria-label={`${col.name} symbol position`}
                      onChange={e => setField(col.name, 'symbol_position', e.target.value || undefined)}>
                      <option value="">auto</option>
                      <option value="before">before</option>
                      <option value="after">after</option>
                    </select>
                  </label>
                </>)}

                {/* Prefix / Suffix */}
                {['number','integer','currency','percent'].includes(fmt.type) && (<>
                  <label style={{ display:'flex', flexDirection:'column', gap:2, width:52 }}>
                    <span style={{ fontSize:9, color:'var(--muted)' }}>Prefix</span>
                    <input value={fmt.prefix ?? ''} placeholder="—" style={inp}
                      onChange={e => setField(col.name, 'prefix', e.target.value || undefined)}
                      onBlur={e => setField(col.name, 'prefix', e.target.value || undefined)} />
                  </label>
                  <label style={{ display:'flex', flexDirection:'column', gap:2, width:52 }}>
                    <span style={{ fontSize:9, color:'var(--muted)' }}>Suffix</span>
                    <input value={fmt.suffix ?? ''} placeholder="—" style={inp}
                      onChange={e => setField(col.name, 'suffix', e.target.value || undefined)}
                      onBlur={e => setField(col.name, 'suffix', e.target.value || undefined)} />
                  </label>
                </>)}

                {/* Bar options */}
                {fmt.type === 'bar' && (<>
                  <label style={{ display:'flex', flexDirection:'column', gap:2, width:52 }}>
                    <span style={{ fontSize:9, color:'var(--muted)' }}>Min</span>
                    <input type="number" value={fmt.min ?? ''} placeholder="0" style={inp}
                      onChange={e => setField(col.name, 'min', e.target.value === '' ? undefined : +e.target.value)} />
                  </label>
                  <label style={{ display:'flex', flexDirection:'column', gap:2, width:52 }}>
                    <span style={{ fontSize:9, color:'var(--muted)' }}>Max</span>
                    <input type="number" value={fmt.max ?? ''} placeholder="100" style={inp}
                      onChange={e => setField(col.name, 'max', e.target.value === '' ? undefined : +e.target.value)} />
                  </label>
                  <label style={{ display:'flex', flexDirection:'column', gap:2 }}>
                    <span style={{ fontSize:9, color:'var(--muted)' }}>Color</span>
                    <input type="color" value={fmt.color ?? '#6c8fff'}
                      style={{ width:36, height:26, padding:2, border:'1px solid var(--border)', borderRadius:4, cursor:'pointer', background:'var(--surface)' }}
                      onChange={e => setField(col.name, 'color', e.target.value)} />
                  </label>
                </>)}

                {/* Badge / Icon thresholds */}
                {(fmt.type === 'badge' || fmt.type === 'icon') && (<>
                  <label style={{ display:'flex', flexDirection:'column', gap:2, width:60 }}>
                    <span style={{ fontSize:9, color:'#f87171' }}>Low (red)</span>
                    <input type="number" value={fmt.thresholds?.[0] ?? ''} placeholder="33" style={inp}
                      onChange={e => {
                        const lo = e.target.value === '' ? 33 : +e.target.value
                        setField(col.name, 'thresholds', [lo, fmt.thresholds?.[1] ?? 66])
                      }} />
                  </label>
                  <label style={{ display:'flex', flexDirection:'column', gap:2, width:60 }}>
                    <span style={{ fontSize:9, color:'#34d399' }}>High (green)</span>
                    <input type="number" value={fmt.thresholds?.[1] ?? ''} placeholder="66" style={inp}
                      onChange={e => {
                        const hi = e.target.value === '' ? 66 : +e.target.value
                        setField(col.name, 'thresholds', [fmt.thresholds?.[0] ?? 33, hi])
                      }} />
                  </label>
                </>)}

                {/* Color scale range + colors */}
                {fmt.type === 'colorscale' && (<>
                  <label style={{ display:'flex', flexDirection:'column', gap:2, width:52 }}>
                    <span style={{ fontSize:9, color:'var(--muted)' }}>Min</span>
                    <input type="number" value={fmt.min ?? ''} placeholder="0" style={inp}
                      onChange={e => setField(col.name, 'min', e.target.value === '' ? undefined : +e.target.value)} />
                  </label>
                  <label style={{ display:'flex', flexDirection:'column', gap:2, width:52 }}>
                    <span style={{ fontSize:9, color:'var(--muted)' }}>Max</span>
                    <input type="number" value={fmt.max ?? ''} placeholder="100" style={inp}
                      onChange={e => setField(col.name, 'max', e.target.value === '' ? undefined : +e.target.value)} />
                  </label>
                  <label style={{ display:'flex', flexDirection:'column', gap:2 }}>
                    <span style={{ fontSize:9, color:'#f87171' }}>Low</span>
                    <input type="color" value={fmt.scaleMinColor ?? '#f87171'}
                      style={{ width:36, height:26, padding:2, border:'1px solid var(--border)', borderRadius:4, cursor:'pointer', background:'var(--surface)' }}
                      onChange={e => setField(col.name, 'scaleMinColor', e.target.value)} />
                  </label>
                  <label style={{ display:'flex', flexDirection:'column', gap:2 }}>
                    <span style={{ fontSize:9, color:'#fbbf24' }}>Mid</span>
                    <input type="color" value={fmt.scaleMidColor ?? '#fbbf24'}
                      style={{ width:36, height:26, padding:2, border:'1px solid var(--border)', borderRadius:4, cursor:'pointer', background:'var(--surface)' }}
                      onChange={e => setField(col.name, 'scaleMidColor', e.target.value)} />
                  </label>
                  <label style={{ display:'flex', flexDirection:'column', gap:2 }}>
                    <span style={{ fontSize:9, color:'#34d399' }}>High</span>
                    <input type="color" value={fmt.scaleMaxColor ?? '#34d399'}
                      style={{ width:36, height:26, padding:2, border:'1px solid var(--border)', borderRadius:4, cursor:'pointer', background:'var(--surface)' }}
                      onChange={e => setField(col.name, 'scaleMaxColor', e.target.value)} />
                  </label>
                </>)}

              </div>
            )}
          </div>
        )
      })}

      {regularCols.length === 0 && (
        <p style={{ fontSize:11, color:'var(--muted)', textAlign:'center', padding:'8px 0' }}>
          No columns in this dataset
        </p>
      )}
    </div>
  )
}
