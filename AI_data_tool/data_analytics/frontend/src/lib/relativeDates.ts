/** Relative date filters (Phase 6.4) — client side of services/relative_dates.py.
 *
 *  A filter `{ column, op: 'relative', value: RelativeSpec }` is resolved by the
 *  server against an EXPLICIT anchor — today, or the latest date in the data —
 *  and the resolved window comes back on the widget result as a note. The
 *  client only builds, validates and describes specs. */

export type RelativeMode = 'last' | 'rolling' | 'to_date' | 'this' | 'previous'
export type RelativeUnit = 'day' | 'week' | 'month' | 'quarter' | 'year'
export type RelativeAnchor = 'today' | 'data_max'

export interface RelativeSpec {
  mode: RelativeMode
  unit: RelativeUnit
  n?: number
  anchor: RelativeAnchor
  include_current?: boolean
}

/** A resolved window as the server returns it in `relative_dates`. */
export interface RelativeNote {
  column: string
  label: string
  start?: string
  end?: string
  anchor?: RelativeAnchor
  anchor_date?: string
  anchor_label?: string
  incomplete?: boolean
  text?: string
  error?: string
}

export interface PartialPeriod { label: string; through: string; granularity: string; text: string }

export const MODES: { value: RelativeMode; label: string }[] = [
  { value: 'last', label: 'Last N' },
  { value: 'rolling', label: 'Rolling N' },
  { value: 'to_date', label: 'To date' },
  { value: 'this', label: 'This' },
  { value: 'previous', label: 'Previous' },
]
export const UNITS: RelativeUnit[] = ['day', 'week', 'month', 'quarter', 'year']

/** One-click presets — "last 30 days is one click" (plan success criterion 9). */
export const PRESETS: { id: string; label: string; spec: Omit<RelativeSpec, 'anchor'> }[] = [
  { id: 'l7d',  label: 'Last 7 days',        spec: { mode: 'last', unit: 'day', n: 7 } },
  { id: 'l30d', label: 'Last 30 days',       spec: { mode: 'last', unit: 'day', n: 30 } },
  { id: 'l90d', label: 'Last 90 days',       spec: { mode: 'last', unit: 'day', n: 90 } },
  { id: 'mtd',  label: 'Month to date',      spec: { mode: 'to_date', unit: 'month' } },
  { id: 'qtd',  label: 'Quarter to date',    spec: { mode: 'to_date', unit: 'quarter' } },
  { id: 'ytd',  label: 'Year to date',       spec: { mode: 'to_date', unit: 'year' } },
  { id: 'pm',   label: 'Previous month',     spec: { mode: 'previous', unit: 'month' } },
  { id: 'l3m',  label: 'Last 3 complete months', spec: { mode: 'last', unit: 'month', n: 3 } },
  { id: 'r12m', label: 'Rolling 12 months',  spec: { mode: 'rolling', unit: 'month', n: 12 } },
]

/** Default: last 30 days, counted from the latest date in the data — most
 *  uploaded datasets stop before today, and an anchor to today would show an
 *  empty window over them. Either way the anchor is named on the widget. */
export const DEFAULT_SPEC: RelativeSpec = { mode: 'last', unit: 'day', n: 30, anchor: 'data_max' }

export function usesN(mode: RelativeMode): boolean {
  return mode === 'last' || mode === 'rolling'
}

export function isRelativeSpec(v: unknown): v is RelativeSpec {
  if (!v || typeof v !== 'object') return false
  const s = v as Record<string, unknown>
  return MODES.some(m => m.value === s.mode) && UNITS.includes(s.unit as RelativeUnit)
    && (s.anchor === 'today' || s.anchor === 'data_max')
}

/** Parse the JSON a filter row keeps in its string value; falls back to the default. */
export function parseSpec(raw: unknown): RelativeSpec {
  let v = raw
  if (typeof raw === 'string') {
    try { v = JSON.parse(raw) } catch { return { ...DEFAULT_SPEC } }
  }
  return isRelativeSpec(v) ? { ...v } : { ...DEFAULT_SPEC }
}

/** Why a spec cannot be sent, or null. */
export function specProblem(s: RelativeSpec): string | null {
  if (usesN(s.mode)) {
    const n = Number(s.n)
    if (!Number.isInteger(n) || n < 1 || n > 1000) return 'The number of periods must be a whole number from 1 to 1000'
  }
  return null
}

function plural(n: number, unit: string): string {
  return `${n} ${unit}${n === 1 ? '' : 's'}`
}

/** Same wording as the server's labels, so the editor and the widget agree. */
export function describeSpec(s: RelativeSpec): string {
  const n = Number(s.n ?? 1)
  let label: string
  switch (s.mode) {
    case 'to_date':
      label = s.unit === 'day' ? 'Today' : `${s.unit[0].toUpperCase()}${s.unit.slice(1)} to date`; break
    case 'this': label = s.unit === 'day' ? 'Today' : `This ${s.unit}`; break
    case 'previous': label = s.unit === 'day' ? 'Yesterday' : `Previous ${s.unit}`; break
    case 'rolling': label = `Rolling ${plural(n, s.unit)}`; break
    default:
      label = s.unit === 'day' ? `Last ${plural(n, s.unit)}`
        : s.include_current ? `Last ${plural(n, s.unit)} (incl. current)` : `Last ${plural(n, s.unit)} (complete)`
  }
  return `${label} · from ${s.anchor === 'today' ? 'today' : 'latest data'}`
}

export function presetOf(s: RelativeSpec): string {
  const p = PRESETS.find(p => p.spec.mode === s.mode && p.spec.unit === s.unit
    && (!usesN(s.mode) || p.spec.n === Number(s.n)) && !s.include_current)
  return p?.id ?? 'custom'
}
