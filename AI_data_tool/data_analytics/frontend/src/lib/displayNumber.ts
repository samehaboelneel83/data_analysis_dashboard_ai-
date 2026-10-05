import { localDigits } from './arabicFormats'

/**
 * Numbers rounded for reading (redesign step 1b).
 *
 * The backend keeps raw floats, so the model wrote "61.53500000000001" into its
 * sentence and the grid showed "83.8883333333". Both are display problems: the
 * screen rounds, while exports and evidence offsets keep the raw value.
 */

const trimZeros = (s: string) => (s.includes('.') ? s.replace(/\.?0+$/, '') : s)

/** Three significant digits, for values below 1 (0.123456 -> "0.123"). */
function sig3(v: number): string {
  if (v === 0) return '0'
  const s = v.toPrecision(3)
  return /e/i.test(s) ? String(Number(s)) : trimZeros(s)
}

/** The prose rounding of a non-negative value: 1 dp from 10 up, 2 dp from 1
 *  to 10, 3 significant digits below 1. */
function readable(v: number): string {
  return v >= 10 ? trimZeros(v.toFixed(1)) : v >= 1 ? trimZeros(v.toFixed(2)) : sig3(v)
}

/**
 * A chart value with the prose rule applied, for the value labels the chat's
 * charts print: only values with more than 2 decimals change, so the label
 * over a bar reads like the sentence above it (83.9, not 83.89).
 */
export function readingValue(v: number): number {
  if (!Number.isFinite(v) || Number.isInteger(v)) return v
  const decimals = (String(Math.abs(v)).split('.')[1] ?? '').length
  if (decimals <= 2 || /e/i.test(String(v))) return v
  return Math.sign(v) * Number(readable(Math.abs(v)))
}

/**
 * A number token from a sentence or a chart value label ("61.53500000000001",
 * "-3.14159%"). Only tokens with MORE than 2 decimal places change: 1 dp from
 * 10 up, 2 dp from 1 to 10, 3 significant digits below 1. Sign, `%` and
 * thousands separators are kept; integers and anything already at 2 dp or
 * fewer -- years, ids, "1,234.5" -- are left as written.
 */
export function formatProseNumber(token: string): string {
  const m = /^([-+]?)([\d,]+)(?:\.(\d+))?(%?)$/.exec(token)
  if (!m || !m[3] || m[3].length <= 2) return localDigits(token)
  const v = Number(`${m[2].replace(/,/g, '')}.${m[3]}`)
  if (!Number.isFinite(v)) return localDigits(token)
  let r = readable(v)
  if (m[2].includes(',')) r = r.replace(/^\d+/, d => d.replace(/\B(?=(\d{3})+(?!\d))/g, ','))
  return localDigits(`${m[1]}${r}${m[4]}`)
}

/**
 * A result-grid cell. Non-integer floats get at most 2 dp (3 significant
 * digits below 1). Integers stay exactly as they are, with no thousands
 * separators: the grid shows whatever columns the question returned, ids and
 * years included, and "2,024" for a year is its own wrong. A decimal that
 * arrives as a string (a NUMERIC column) is rounded the same way.
 */
export function formatCell(v: string | number | boolean | null | undefined): string {
  if (v == null) return ''
  const n = typeof v === 'number' ? v
    : typeof v === 'string' && /^[-+]?\d+\.\d+$/.test(v.trim()) ? Number(v) : null
  if (n == null || !Number.isFinite(n)) return String(v)
  if (Number.isInteger(n)) return localDigits(String(v))
  return localDigits(Math.abs(n) >= 1 ? trimZeros(n.toFixed(2)) : sig3(n))
}
