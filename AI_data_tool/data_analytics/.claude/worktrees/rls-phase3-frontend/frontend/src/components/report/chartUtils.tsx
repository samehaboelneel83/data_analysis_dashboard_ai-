import type { CalcColumnFormat } from '../../services/api'

export const COLORS = ['#6c8fff','#a78bfa','#34d399','#fbbf24','#f87171','#38bdf8','#fb7185','#4ade80','#c084fc','#e879f9']
export const SELECTED_STROKE = '#fff'
export const DIM_OPACITY = 0.35

export const TT: React.CSSProperties = { background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }

// String-only version for Recharts axis/tooltip (cannot return JSX)
export function fmtStr(value: unknown, fmt?: CalcColumnFormat | null): string {
  if (!fmt || fmt.type === 'none') {
    if (value == null) return '—'
    return typeof value === 'number'
      ? value.toLocaleString(undefined, { maximumFractionDigits: 2 })
      : String(value)
  }
  const num = typeof value === 'number' ? value : parseFloat(String(value))
  const dec = fmt.decimals ?? 2
  const pre = fmt.prefix ?? ''
  const suf = fmt.suffix ?? ''
  const loc = (n: number, d = dec) =>
    n.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d })

  switch (fmt.type) {
    case 'number':   return isNaN(num) ? '—' : `${pre}${loc(num)}${suf}`
    case 'integer':  return isNaN(num) ? '—' : `${pre}${Math.round(num).toLocaleString()}${suf}`
    case 'currency': return isNaN(num) ? '—' : `${pre}${fmt.symbol ?? '$'} ${loc(num)}${suf}`
    case 'percent':  return isNaN(num) ? '—' : `${pre}${num.toFixed(dec)}%${suf}`
    case 'bar':      return isNaN(num) ? '—' : loc(num, 1)
    case 'badge':    return isNaN(num) ? '—' : `${pre}${loc(num)}${suf}`
    case 'trend':    return isNaN(num) ? '—'
      : `${num > 0 ? '↑' : num < 0 ? '↓' : '→'} ${pre}${Math.abs(num).toLocaleString(undefined, { maximumFractionDigits: dec })}${suf}`
    default:         return value == null ? '—' : String(value)
  }
}

// ReactNode version for table cells (can return JSX for bar/badge/trend)
export function formatValue(value: unknown, fmt?: CalcColumnFormat | null): React.ReactNode {
  if (!fmt || fmt.type === 'none') return value == null ? '—' : String(value)
  const num = typeof value === 'number' ? value : parseFloat(String(value))
  const dec = fmt.decimals ?? 2
  const pre = fmt.prefix ?? ''
  const suf = fmt.suffix ?? ''
  const fmtNum = (n: number, d = dec) =>
    n.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d })

  switch (fmt.type) {
    case 'number':
      return isNaN(num) ? (value ?? '—') : `${pre}${fmtNum(num)}${suf}`
    case 'integer':
      return isNaN(num) ? (value ?? '—') : `${pre}${Math.round(num).toLocaleString()}${suf}`
    case 'currency': {
      const sym = fmt.symbol ?? '$'
      return isNaN(num) ? (value ?? '—') : `${pre}${sym} ${fmtNum(num)}${suf}`
    }
    case 'percent':
      return isNaN(num) ? (value ?? '—') : `${pre}${num.toFixed(dec)}%${suf}`
    case 'bar': {
      const mn = fmt.min ?? 0; const mx = fmt.max ?? 100
      const pct = isNaN(num) ? 0 : Math.max(0, Math.min(100, ((num - mn) / (mx - mn)) * 100))
      return (
        <div style={{ display:'flex', alignItems:'center', gap:5 }}>
          <div style={{ flex:1, minWidth:50, height:7, background:'var(--border)', borderRadius:4, overflow:'hidden' }}>
            <div style={{ width:`${pct}%`, height:'100%', background: fmt.color ?? '#6c8fff', borderRadius:4 }} />
          </div>
          <span style={{ fontSize:10, color:'var(--muted)', minWidth:30, textAlign:'right' }}>
            {isNaN(num) ? '—' : num.toLocaleString(undefined, { maximumFractionDigits: 1 })}
          </span>
        </div>
      )
    }
    case 'badge': {
      const [lo, hi] = fmt.thresholds ?? [33, 66]
      const color = isNaN(num) ? 'var(--muted)' : num < lo ? '#f87171' : num > hi ? '#34d399' : '#fbbf24'
      const text = isNaN(num) ? (value ?? '—') : `${pre}${num.toLocaleString(undefined, { maximumFractionDigits: dec })}${suf}`
      return (
        <span style={{ display:'inline-block', padding:'1px 7px', borderRadius:10,
          background:color + '22', color, fontWeight:600, fontSize:11 }}>
          {text}
        </span>
      )
    }
    case 'trend': {
      const arrow = isNaN(num) ? '→' : num > 0 ? '↑' : num < 0 ? '↓' : '→'
      const color = isNaN(num) ? 'var(--muted)' : num > 0 ? '#34d399' : num < 0 ? '#f87171' : 'var(--muted)'
      const text  = isNaN(num) ? (value ?? '—')
        : `${pre}${Math.abs(num).toLocaleString(undefined, { maximumFractionDigits: dec })}${suf}`
      return <span style={{ color, fontWeight:700 }}>{arrow} {text}</span>
    }
    default:
      return value == null ? '—' : String(value)
  }
}

export function EmptyState({ msg }: { msg: string }) {
  return (
    <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 12, flexDirection: 'column', gap: 6 }}>
      <span style={{ fontSize: 24, opacity: .4 }}>◻</span>
      <span>{msg}</span>
    </div>
  )
}

// Returns a per-point fill/opacity/stroke resolver for cross-filter highlight/dim.
export function getFillFactory(broadcasts: boolean, localSelected: unknown) {
  return (name: unknown, i: number) => {
    const color = COLORS[i % COLORS.length]
    if (!broadcasts || localSelected === null) return { fill: color, opacity: 1 }
    return localSelected === name
      ? { fill: color, opacity: 1, strokeWidth: 2, stroke: SELECTED_STROKE }
      : { fill: color, opacity: DIM_OPACITY }
  }
}
