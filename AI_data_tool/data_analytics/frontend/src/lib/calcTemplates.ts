/**
 * "What do you want to make?" -- calculated columns from a small form instead
 * of a code box (calculated-column plan, 2026-10-10). Each template turns its
 * form into a formula in the expression language the server evaluates
 * (widget_data._eval_expr), so the result is an ordinary calculated column the
 * person can still open and edit as a formula.
 *
 * Everything here is pure: a form in, `{ expression, name }` out, or null while
 * the form is not finished. Values typed by the person are always written as
 * quoted literals (`pyStr`) and column names through `colRef`; the server
 * checks the formula again before running it.
 */
import type { CondNode } from './conditionTree'
import type { SqlJoiner } from './sqlWhere'

export type TemplateKey = 'math' | 'bands' | 'label' | 'text' | 'date' | 'clean'

export interface Built { expression: string; name: string }

/** A text literal: backslash and quote escaped, so a label can never end early. */
export const pyStr = (s: string): string => `'${s.replace(/\\/g, '\\\\').replace(/'/g, "\\'")}'`

/** A column reference; anything that is not a plain name goes in backticks. */
export const colRef = (name: string): string =>
  /^[\p{L}][\p{L}\p{N}_]*$/u.test(name) ? name : `\`${name.replace(/`/g, '')}\``

const num = (s: string): number | null => {
  const t = s.trim()
  return t !== '' && !isNaN(Number(t)) ? Number(t) : null
}
const slug = (s: string) => s.trim().replace(/\s+/g, '_')

// ── 1. Calculate from two columns ──────────────────────────────────────────
export type MathOp = 'add' | 'sub' | 'mul' | 'div' | 'pct_change' | 'pct_of'
export interface MathForm { a: string; op: MathOp; bKind: 'column' | 'number'; b: string }

export function buildMath(f: MathForm): Built | null {
  if (!f.a || !f.b.trim()) return null
  const a = colRef(f.a)
  const n = f.bKind === 'number' ? num(f.b) : null
  if (f.bKind === 'number' && n === null) return null
  const b = f.bKind === 'column' ? colRef(f.b) : String(n)
  // Dividing by zero gives "infinity", which then sits in every average: an
  // empty value is the honest answer. A fixed number other than 0 needs no guard.
  const safeDiv = (body: string) => f.bKind === 'number'
    ? (n === 0 ? null : body)
    : `IF(${b} == 0, None, ${body})`
  const bName = f.bKind === 'column' ? f.b : String(n)
  const map: Record<MathOp, [string | null, string]> = {
    add: [`${a} + ${b}`, `${f.a}_plus_${bName}`],
    sub: [`${a} - ${b}`, `${f.a}_minus_${bName}`],
    mul: [`${a} * ${b}`, `${f.a}_times_${bName}`],
    div: [safeDiv(`${a} / ${b}`), `${f.a}_per_${bName}`],
    pct_change: [safeDiv(`(${a} - ${b}) / ${b} * 100`), `${f.a}_change_vs_${bName}_pct`],
    pct_of: [safeDiv(`${a} / ${b} * 100`), `${f.a}_pct_of_${bName}`],
  }
  const [expression, name] = map[f.op]
  return expression ? { expression, name: slug(name) } : null
}

// ── 2. Group numbers into bands ────────────────────────────────────────────
export interface Band { below: string; label: string }
export interface BandsForm { column: string; bands: Band[]; elseLabel: string; emptyLabel: string }

/** Why the bands cannot be built yet, or null. */
export function bandsProblem(f: BandsForm): 'needColumn' | 'needLimits' | 'notAscending' | 'needLabels' | null {
  if (!f.column) return 'needColumn'
  const limits = f.bands.map(b => num(b.below))
  if (!f.bands.length || limits.some(v => v === null)) return 'needLimits'
  if (limits.some((v, i) => i > 0 && (v as number) <= (limits[i - 1] as number))) return 'notAscending'
  if (f.bands.some(b => !b.label.trim()) || !f.elseLabel.trim()) return 'needLabels'
  return null
}

export function buildBands(f: BandsForm): Built | null {
  if (bandsProblem(f)) return null
  const c = colRef(f.column)
  let expr = pyStr(f.elseLabel.trim())
  for (let i = f.bands.length - 1; i >= 0; i--) {
    expr = `IF(${c} < ${num(f.bands[i].below)}, ${pyStr(f.bands[i].label.trim())}, ${expr})`
  }
  // Without this an empty value falls through every "below" test into the
  // last band, and missing data is counted as the biggest.
  if (f.emptyLabel.trim()) expr = `IF(isnull(${c}), ${pyStr(f.emptyLabel.trim())}, ${expr})`
  return { expression: expr, name: slug(`${f.column}_band`) }
}

// ── 3. Label rows by conditions (the condition boxes) ──────────────────────
export interface LabelRule { id: string; joiner: SqlJoiner; conds: CondNode[]; label: string }
export interface LabelForm { rules: LabelRule[]; elseLabel: string; name: string }

/** One condition tree as a formula; '' while nothing in it is complete. */
export function conditionsToFormula(nodes: CondNode[], joiner: SqlJoiner, numeric: Set<string>): string {
  const parts = nodes.map((n): string => {
    if (n.kind === 'kept') return ''
    if (n.kind === 'group') {
      const inner = conditionsToFormula(n.items, n.joiner, numeric)
      return inner ? `(${inner})` : ''
    }
    if (!n.column) return ''
    const c = colRef(n.column)
    const lit = (v: string) => numeric.has(n.column) && num(v) !== null ? String(num(v)) : pyStr(v.trim())
    switch (n.op) {
      case 'is_null': return `isnull(${c})`
      case 'not_null': return `not isnull(${c})`
      case 'contains': return n.value.trim() ? `CONTAINS(${c}, ${pyStr(n.value.trim())})` : ''
      case 'in': {
        const vals = n.value.split(',').map(v => v.trim()).filter(Boolean)
        return vals.length ? `(${vals.map(v => `${c} == ${lit(v)}`).join(' or ')})` : ''
      }
      default: {
        if (!n.value.trim()) return ''
        const op = { eq: '==', ne: '!=', gt: '>', gte: '>=', lt: '<', lte: '<=' }[n.op]
        return `${c} ${op} ${lit(n.value)}`
      }
    }
  }).filter(Boolean)
  return parts.join(` ${joiner} `)
}

export function buildLabel(f: LabelForm, numeric: Set<string>): Built | null {
  const rules = f.rules
    .map(r => ({ cond: conditionsToFormula(r.conds, r.joiner, numeric), label: r.label.trim() }))
    .filter(r => r.cond && r.label)
  if (!rules.length || !f.elseLabel.trim()) return null
  let expr = pyStr(f.elseLabel.trim())
  for (let i = rules.length - 1; i >= 0; i--) expr = `IF(${rules[i].cond}, ${pyStr(rules[i].label)}, ${expr})`
  return { expression: expr, name: slug(f.name || 'label') }
}

// ── 4. Combine text ────────────────────────────────────────────────────────
export interface TextForm { parts: string[]; separator: string }

export function buildText(f: TextForm): Built | null {
  const cols = f.parts.filter(Boolean)
  if (cols.length < 2) return null
  const pieces: string[] = []
  cols.forEach((c, i) => {
    if (i > 0 && f.separator) pieces.push(pyStr(f.separator))
    pieces.push(colRef(c))
  })
  return { expression: `CONCAT(${pieces.join(', ')})`, name: slug(cols.join('_')) }
}

// ── 5. Part of a date ──────────────────────────────────────────────────────
export const DATE_PARTS = ['YEAR', 'QUARTER', 'MONTH', 'MONTHNAME', 'DAY', 'DAYNAME', 'WEEKDAY'] as const
export type DatePart = typeof DATE_PARTS[number]
export interface DateForm { column: string; part: DatePart }

export function buildDate(f: DateForm): Built | null {
  if (!f.column) return null
  return { expression: `${f.part}(${colRef(f.column)})`, name: slug(`${f.column}_${f.part.toLowerCase()}`) }
}

// ── 6. Clean text ──────────────────────────────────────────────────────────
export type CleanAction = 'TRIM' | 'UPPER' | 'LOWER' | 'REPLACE'
export interface CleanForm { column: string; action: CleanAction; find: string; replaceWith: string }

export function buildClean(f: CleanForm): Built | null {
  if (!f.column) return null
  const c = colRef(f.column)
  if (f.action === 'REPLACE') {
    if (!f.find) return null
    return { expression: `REPLACE(${c}, ${pyStr(f.find)}, ${pyStr(f.replaceWith)})`, name: slug(`${f.column}_clean`) }
  }
  return { expression: `${f.action}(${c})`, name: slug(`${f.column}_${f.action.toLowerCase()}`) }
}
