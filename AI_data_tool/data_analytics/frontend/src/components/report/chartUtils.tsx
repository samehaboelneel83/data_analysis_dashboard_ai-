import type { CalcColumnFormat } from '../../services/api'
import { localDigits, symbolAfter } from '../../lib/arabicFormats'
import type { RuleStyle } from '../../lib/displayRules'
import { THEMES, SERIES_DASHES, SERIES_PATTERNS } from './themes'

export const COLORS = [...THEMES.default]

export function applyTheme(name: string, customPalettes?: Record<string, string[]>) {
  // "custom:<id>" resolves through the org's saved palettes; an unknown id falls back
  // to the default rather than leaving the previous report's colours in place, which
  // would silently mis-theme every chart on screen.
  const next = (name.startsWith('custom:') ? customPalettes?.[name] : THEMES[name]) ?? THEMES[name] ?? THEMES.default
  COLORS.length = 0
  COLORS.push(...next)
}
export const SELECTED_STROKE = '#fff'

/**
 * A pie/donut slice label in the TEXT colour, not the slice's. Recharts' default
 * paints each label in its slice colour, which is fine on white for a mid-tone
 * palette and unreadable for a dark one on a dark canvas (Ember's crimson on the
 * dark theme measured well under 3:1). The slice it belongs to is the one it
 * sits beside, so the colour carried no information the position did not.
 */
export function sliceLabel(p: { x: number; y: number; textAnchor?: string; name?: unknown; percent?: number }) {
  return (
    <text x={p.x} y={p.y} textAnchor={p.textAnchor as 'start' | 'middle' | 'end' | undefined} dominantBaseline="central"
      fill="var(--text)" style={{ fontSize: 12 }}>
      {`${String(p.name ?? '')} ${((p.percent ?? 0) * 100).toFixed(0)}%`}
    </text>
  )
}
export const DIM_OPACITY = 0.35

// The chart tooltip: a small floating card on the surface colour with the
// overlay shadow, so it reads as lifted above the plot rather than as a grey
// patch painted onto it.
export const TT: React.CSSProperties = {
  background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12,
  boxShadow: 'var(--dl-shadow-overlay)', padding: '8px 10px',
}

/**
 * Keep a number and its unit in reading order inside an RTL page.
 *
 * "$ 2,000,000" is a Latin symbol followed by Latin digits. Dropped into an
 * RTL context the bidi algorithm reorders that run and it renders as
 * "2,000,000 $" -- which is what the Arabic charts were showing on their value
 * axes. U+2066 LEFT-TO-RIGHT ISOLATE (…U+2069 POP) wraps the pair as one
 * neutral-directional chunk, so the label keeps its order while the AXIS still
 * sits on the correct side of an RTL chart.
 *
 * Applied to currency and percent, the two formats that pin a symbol to one
 * side of the digits. A bare number needs no isolate: digits are already
 * left-to-right by the bidi algorithm's own rules.
 */
const LRI = '⁦'
const PDI = '⁩'
export const isolateLtr = (s: string) => `${LRI}${s}${PDI}`

// String-only version for Recharts axis/tooltip (cannot return JSX)
/** Display units: the divisor and the unit's short name.
 *
 *  A percent is never scaled -- it is already a small number in its own unit,
 *  and dividing it by a thousand would produce a silently wrong figure, which
 *  is exactly the failure this whole formatter exists to avoid.
 */
export function scaleParts(num: number, fmt?: CalcColumnFormat | null):
    { divisor: number; unit: string } {
  const mode = fmt?.scale
  if (!mode || mode === 'none' || fmt?.type === 'percent') return { divisor: 1, unit: '' }
  if (mode === 'thousands') return { divisor: 1e3, unit: 'K' }
  if (mode === 'millions') return { divisor: 1e6, unit: 'M' }
  if (mode === 'billions') return { divisor: 1e9, unit: 'B' }
  const size = Math.abs(num)
  if (size >= 1e9) return { divisor: 1e9, unit: 'B' }
  if (size >= 1e6) return { divisor: 1e6, unit: 'M' }
  if (size >= 1e3) return { divisor: 1e3, unit: 'K' }
  return { divisor: 1, unit: '' }
}

/** A legend with a title above or below its entries.
 *
 *  The swatches say WHICH value each colour is; the title says what the values
 *  ARE. A key reading "29 and below / 30-44 years" leaves the reader to infer
 *  the field from the labels, which is exactly what a dashboard should not ask.
 *
 *  Recharts has no title of its own, so this is passed as the legend's
 *  `content` and draws the payload itself. Everything a default Recharts legend
 *  does that matters here -- swatch, colour, label -- is drawn below; anything
 *  it does that is not drawn here (its hover callbacks) was never used by these
 *  renderers.
 */
export function LegendWithTitle(
  { payload, title, below }:
  { payload?: readonly { value?: unknown; color?: string }[]; title: string; below?: boolean },
) {
  const entries = (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, justifyContent: 'center' }}>
      {(payload ?? []).map((e, i) => (
        <span key={i} style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
          <span aria-hidden style={{ width: 9, height: 9, borderRadius: 2,
            background: e.color ?? 'var(--accent)', display: 'inline-block' }} />
          {String(e.value ?? '')}
        </span>
      ))}
    </div>
  )
  const heading = (
    <div data-legend-title style={{ textAlign: 'center', fontSize: 11,
      fontWeight: 600, color: 'var(--muted)', margin: below ? '2px 0 0' : '0 0 2px' }}>
      {title}
    </div>
  )
  return (
    <div style={{ fontSize: 11 }}>
      {below ? <>{entries}{heading}</> : <>{heading}{entries}</>}
    </div>
  )
}

export function fmtStr(value: unknown, fmt?: CalcColumnFormat | null): string {
  // Phase 7.5: the reader's digits (١٢٣ or 123) on every formatted number.
  return localDigits(fmtStrLatin(value, fmt))
}

function fmtStrLatin(value: unknown, fmt?: CalcColumnFormat | null): string {
  if (!fmt || fmt.type === 'none') {
    if (value == null) return '—'
    return typeof value === 'number'
      ? value.toLocaleString(undefined, { maximumFractionDigits: 2 })
      : String(value)
  }
  const raw = typeof value === 'number' ? value : parseFloat(String(value))
  // Display units first, so every branch below formats the SCALED number and
  // the unit rides along in the suffix.
  const { divisor, unit } = scaleParts(raw, fmt)
  const num = divisor === 1 ? raw : raw / divisor
  const dec = fmt.decimals ?? 2
  const pre = fmt.prefix ?? ''
  const shown = (fmt.scale_suffix ?? true) ? unit : ''
  const suf = `${shown}${fmt.suffix ?? ''}`
  const loc = (n: number, d = dec) =>
    n.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d })

  switch (fmt.type) {
    case 'number':   return isNaN(num) ? '—' : `${pre}${loc(num)}${suf}`
    case 'integer':  return isNaN(num) ? '—' : `${pre}${Math.round(num).toLocaleString()}${suf}`
    case 'currency': {
      if (isNaN(num)) return '—'
      const sym = fmt.symbol ?? '$'
      // An Arabic-script symbol follows the amount ("١٬٢٠٠ ر.س"); a Latin one leads.
      return symbolAfter(sym, fmt.symbol_position)
        ? isolateLtr(`${pre}${loc(num)} ${sym}${suf}`)
        : isolateLtr(`${pre}${sym} ${loc(num)}${suf}`)
    }
    case 'percent':  return isNaN(num) ? '—' : isolateLtr(`${pre}${num.toFixed(dec)}%${suf}`)
    case 'bar':      return isNaN(num) ? '—' : loc(num, 1)
    case 'badge':    return isNaN(num) ? '—' : `${pre}${loc(num)}${suf}`
    case 'colorscale': return isNaN(num) ? '—' : `${pre}${loc(num)}${suf}`
    case 'icon':     return isNaN(num) ? '—' : `${pre}${loc(num)}${suf}`
    case 'trend':    return isNaN(num) ? '—'
      : `${num > 0 ? '↑' : num < 0 ? '↓' : '→'} ${pre}${Math.abs(num).toLocaleString(undefined, { maximumFractionDigits: dec })}${suf}`
    default:         return value == null ? '—' : String(value)
  }
}

function interpolateColor(hexA: string, hexB: string, t: number): string {
  const parse = (hex: string) => {
    const h = hex.replace('#', '')
    return [0, 2, 4].map(i => parseInt(h.substring(i, i + 2), 16))
  }
  const [r1, g1, b1] = parse(hexA)
  const [r2, g2, b2] = parse(hexB)
  const r = Math.round(r1 + (r2 - r1) * t)
  const g = Math.round(g1 + (g2 - g1) * t)
  const b = Math.round(b1 + (b2 - b1) * t)
  return `rgb(${r}, ${g}, ${b})`
}

// ReactNode version for table cells (can return JSX for bar/badge/trend)
export function formatValue(value: unknown, fmt?: CalcColumnFormat | null): React.ReactNode {
  if (!fmt || fmt.type === 'none') {
    if (value == null) return '—'
    // An unformatted number is stringified as-is, which exposes binary floating-point
    // error the moment anything is summed: a totals row over exact inputs rendered
    // "6067.900000000001". Round-tripping through 15 significant digits removes that
    // artifact (it lives at the 16th-17th digit) while preserving genuine precision,
    // and applies no grouping or forced decimals, so nothing else about the display
    // changes. Integers are left alone -- they carry no such artifact, and reducing
    // their precision would corrupt large ids.
    if (typeof value === 'number' && Number.isFinite(value) && !Number.isInteger(value)) {
      return String(Number(value.toPrecision(15)))
    }
    return String(value)
  }
  const num = typeof value === 'number' ? value : parseFloat(String(value))
  const dec = fmt.decimals ?? 2
  const pre = fmt.prefix ?? ''
  const suf = fmt.suffix ?? ''
  const fmtNum = (n: number, d = dec) =>
    n.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d })

  switch (fmt.type) {
    case 'number':
      return isNaN(num) ? (value == null ? '—' : String(value)) : localDigits(`${pre}${fmtNum(num)}${suf}`)
    case 'integer':
      return isNaN(num) ? (value == null ? '—' : String(value)) : localDigits(`${pre}${Math.round(num).toLocaleString()}${suf}`)
    case 'currency': {
      const sym = fmt.symbol ?? '$'
      if (isNaN(num)) return value == null ? '—' : String(value)
      return localDigits(symbolAfter(sym, fmt.symbol_position)
        ? `${pre}${fmtNum(num)} ${sym}${suf}` : `${pre}${sym} ${fmtNum(num)}${suf}`)
    }
    case 'percent':
      return isNaN(num) ? (value == null ? '—' : String(value)) : `${pre}${num.toFixed(dec)}%${suf}`
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
      const text = isNaN(num) ? (value == null ? '—' : String(value)) : `${pre}${num.toLocaleString(undefined, { maximumFractionDigits: dec })}${suf}`
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
      const text  = isNaN(num) ? (value == null ? '—' : String(value))
        : `${pre}${Math.abs(num).toLocaleString(undefined, { maximumFractionDigits: dec })}${suf}`
      return <span style={{ color, fontWeight:700 }}>{arrow} {text}</span>
    }
    case 'colorscale': {
      if (isNaN(num)) return '—'
      const mn = fmt.min ?? 0; const mx = fmt.max ?? 100
      const t = mx > mn ? Math.max(0, Math.min(1, (num - mn) / (mx - mn))) : 0
      const lo = fmt.scaleMinColor ?? '#f87171'
      const mid = fmt.scaleMidColor
      const hi = fmt.scaleMaxColor ?? '#34d399'
      const color = mid
        ? (t < 0.5 ? interpolateColor(lo, mid, t / 0.5) : interpolateColor(mid, hi, (t - 0.5) / 0.5))
        : interpolateColor(lo, hi, t)
      const text = `${pre}${fmtNum(num)}${suf}`
      return (
        <div style={{ background: color, padding: '2px 6px', borderRadius: 4, textAlign: 'center', fontSize: 11 }}>
          {text}
        </div>
      )
    }
    case 'icon': {
      if (isNaN(num)) return '—'
      const [lo, hi] = fmt.thresholds ?? [33, 66]
      const icon = num < lo ? '🔴' : num > hi ? '🟢' : '🟡'
      const text = `${pre}${fmtNum(num)}${suf}`
      return <span>{icon} {text}</span>
    }
    default:
      return value == null ? '—' : String(value)
  }
}

export function EmptyState({ msg, action }: {
  msg: string
  /** One thing the reader can do about it. Offered only when doing it could
   *  change the answer -- a source that was unreachable may not be now. */
  action?: { label: string; onClick: () => void }
}) {
  return (
    // Styling untouched from before the action existed: this renders in every
    // widget on every surface, and a restyle here is an app-wide change.
    <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 12, flexDirection: 'column', gap: 6 }}>
      <span style={{ fontSize: 24, opacity: .4 }}>◻</span>
      <span>{msg}</span>
      {action && (
        <button type="button" onClick={action.onClick} className="btn btn-ghost btn-sm"
          style={{ fontSize: 11, padding: '3px 10px' }}>
          {action.label}
        </button>
      )}
    </div>
  )
}

// Returns a per-point fill/opacity/stroke resolver for cross-filter highlight/dim.
// A display-rule fill overrides the palette colour but not the selection treatment:
// a rule says what a mark means, selection says what the user is looking at.
export function getFillFactory(
  broadcasts: boolean,
  localSelected: unknown,
  ruleRowStyles?: (RuleStyle | null)[],
) {
  return (name: unknown, i: number) => {
    const color = ruleRowStyles?.[i]?.fill ?? COLORS[i % COLORS.length]
    if (!broadcasts || localSelected === null) return { fill: color, opacity: 1 }
    return localSelected === name
      ? { fill: color, opacity: 1, strokeWidth: 2, stroke: SELECTED_STROKE }
      : { fill: color, opacity: DIM_OPACITY }
  }
}


/**
 * Dash pattern for one series index, or undefined for a solid line.
 *
 * Returns undefined unless the report has opted in, so nothing changes for existing
 * reports. When enabled, this is redundant encoding: colour and dash carry the same
 * distinction, so a viewer who cannot separate two hues -- or is looking at a
 * greyscale printout -- still reads the chart. It is the accessibility counterpart to
 * the high-contrast palette, and the two are independent: either helps on its own.
 */
export function seriesDash(index: number, enabled?: boolean): string | undefined {
  if (!enabled) return undefined
  return SERIES_DASHES[index % SERIES_DASHES.length]
}

/** Relative luminance of a #rrggbb colour (0..1), for picking a readable motif ink. */
function luma(hex: string): number {
  const m = /^#?([0-9a-fA-F]{6})$/.exec(hex.trim())
  if (!m) return 0.5
  const [r, g, b] = [0, 2, 4].map(i => parseInt(m[1].slice(i, i + 2), 16) / 255)
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

/**
 * Fill for one series/group index: an SVG hatch pattern when the report has opted
 * into `series_patterns`, otherwise the plain series colour. This is the
 * filled-mark counterpart to `seriesDash` (which textures lines): redundant
 * encoding, so bar/area/pie groups stay distinguishable in greyscale or under
 * colour blindness. Index 0 stays a solid fill -- a lone group needs no texture
 * and the chart keeps its clean default. The referenced <pattern> is emitted by
 * <PatternDefs> with the SAME colour list and index scheme, so the tile's ground
 * colour always matches the series colour it replaces.
 */
export function fillPattern(index: number, color: string, enabled?: boolean): string {
  if (!enabled) return color
  return SERIES_PATTERNS[index % SERIES_PATTERNS.length] ? `url(#fillpat-${index})` : color
}

/** The motif drawn over one pattern tile in `ink`; one arm per SERIES_PATTERNS id. */
function motif(id: string, ink: string): React.ReactNode {
  const line = { stroke: ink, strokeWidth: 1.4, fill: 'none' as const }
  switch (id) {
    case 'diagonal':      return <path d="M-2,2 L2,-2 M0,8 L8,0 M6,10 L10,6" {...line} />
    case 'diagonal-back': return <path d="M-2,6 L2,10 M0,0 L8,8 M6,-2 L10,2" {...line} />
    case 'horizontal':    return <path d="M0,2 H8 M0,6 H8" {...line} />
    case 'vertical':      return <path d="M2,0 V8 M6,0 V8" {...line} />
    case 'grid':          return <path d="M0,4 H8 M4,0 V8" {...line} />
    case 'cross':         return <path d="M0,0 L8,8 M8,0 L0,8" {...line} />
    case 'zigzag':        return <path d="M0,6 L2,2 L4,6 L6,2 L8,6" {...line} />
    case 'checker':       return <path d="M0,0 h4 v4 h-4 z M4,4 h4 v4 h-4 z" fill={ink} stroke="none" />
    case 'dots':          return <g fill={ink} stroke="none"><circle cx={2} cy={2} r={1.1} /><circle cx={6} cy={6} r={1.1} /></g>
    default:              return null
  }
}

/**
 * SVG <defs> of one hatch pattern per group colour, referenced by `fillPattern`.
 * Rendered as a direct child of a recharts chart so it lands inside the chart SVG
 * (the mechanism recharts gradients use). Each tile paints the group colour as its
 * ground and a contrasting motif on top, so colour is preserved AND the texture
 * separates groups. `colors` must be the per-group colour list in index order --
 * the same one the marks use -- so id `fillpat-i` carries `colors[i]`. Emits
 * nothing unless enabled, so existing reports are byte-identical.
 */
export function PatternDefs({ colors, enabled }: { colors: string[]; enabled?: boolean }): React.ReactElement | null {
  if (!enabled) return null
  return (
    <defs>
      {colors.map((color, i) => {
        const id = SERIES_PATTERNS[i % SERIES_PATTERNS.length]
        if (!id) return null
        const ink = luma(color) > 0.55 ? 'rgba(0,0,0,.6)' : 'rgba(255,255,255,.85)'
        return (
          <pattern key={i} id={`fillpat-${i}`} patternUnits="userSpaceOnUse" width={8} height={8}>
            <rect width={8} height={8} fill={color} />
            {motif(id, ink)}
          </pattern>
        )
      })}
    </defs>
  )
}
