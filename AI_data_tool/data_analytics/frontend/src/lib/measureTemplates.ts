/**
 * "What do you want to measure?" -- measures from a small form instead of a
 * formula (2026-10-10, the measures half of the calculated-column work). A
 * measure is computed at each chart's grouping (services/measure_eval.py), so
 * these write aggregate formulas: SUM(...), ratios of two totals, a share of
 * the total, a total of only some rows.
 *
 * Same rules as calcTemplates: pure, null while unfinished, typed values
 * quoted (`pyStr`), names through `colRef`, every division guarded so a zero
 * gives an empty value rather than "infinity". The exact strings are run
 * against the real engine in backend/tests/test_calc_formula_help.py.
 */
import { colRef, conditionsToFormula } from './calcTemplates'
import type { CondNode } from './conditionTree'
import type { SqlJoiner } from './sqlWhere'

export type MeasureTemplateKey = 'summary' | 'ratio' | 'share' | 'only'
export const SUMMARIES = ['SUM', 'AVG', 'MEDIAN', 'COUNTD', 'MIN', 'MAX', 'COUNT'] as const
export type Summary = typeof SUMMARIES[number]

export interface BuiltMeasure { expression: string; name: string }

const WORD: Record<Summary, string> = {
  SUM: 'Total', AVG: 'Average', MEDIAN: 'Median', COUNTD: 'Distinct', MIN: 'Lowest', MAX: 'Highest', COUNT: 'Count of',
}
const agg = (how: Summary, column: string) => `${how}(${colRef(column)})`
const guard = (den: string, body: string) => `IF(${den} == 0, None, ${body})`

// ── 1. Summarise a column ─────────────────────────────────────────────────
export interface SummaryForm { how: Summary; column: string }
export function buildSummary(f: SummaryForm): BuiltMeasure | null {
  if (!f.column) return null
  return { expression: agg(f.how, f.column), name: `${WORD[f.how]} ${f.column}` }
}

// ── 2. Compare two totals ─────────────────────────────────────────────────
export type RatioOp = 'div' | 'pct_of' | 'pct_change' | 'diff'
export interface RatioForm { howA: Summary; a: string; op: RatioOp; howB: Summary; b: string }
export function buildRatio(f: RatioForm): BuiltMeasure | null {
  if (!f.a || !f.b) return null
  const A = agg(f.howA, f.a)
  const B = agg(f.howB, f.b)
  const map: Record<RatioOp, [string, string]> = {
    div: [guard(B, `${A} / ${B}`), `${f.a} per ${f.b}`],
    pct_of: [guard(B, `${A} / ${B} * 100`), `${f.a} as % of ${f.b}`],
    pct_change: [guard(B, `(${A} - ${B}) / ${B} * 100`), `${f.a} vs ${f.b} %`],
    diff: [`${A} - ${B}`, `${f.a} minus ${f.b}`],
  }
  const [expression, name] = map[f.op]
  return { expression, name }
}

// ── 3. Share of the total ─────────────────────────────────────────────────
export interface ShareForm { how: Summary; column: string }
/** Each group's part of the whole (by region: Europe 41%, Asia 22%…). */
export function buildShare(f: ShareForm): BuiltMeasure | null {
  if (!f.column) return null
  const A = agg(f.how, f.column)
  return { expression: guard(`TOTAL(${A})`, `${A} / TOTAL(${A}) * 100`), name: `% of total ${f.column}` }
}

// ── 4. Only some rows ─────────────────────────────────────────────────────
export type OnlyHow = 'SUM' | 'AVG' | 'ROWS'
export interface OnlyForm { how: OnlyHow; column: string; joiner: SqlJoiner; conds: CondNode[]; name: string }
/** A total / average / row count over the rows that match the boxes. */
export function buildOnly(f: OnlyForm, numeric: Set<string>): BuiltMeasure | null {
  const cond = conditionsToFormula(f.conds, f.joiner, numeric)
  if (!cond) return null
  if (f.how === 'ROWS') return { expression: `SUM(IF(${cond}, 1, 0))`, name: f.name || 'Matching rows' }
  if (!f.column) return null
  const c = colRef(f.column)
  // A row that does not match adds 0 to a total but must not pull an average
  // down: it is left out (None), not counted as 0.
  return f.how === 'SUM'
    ? { expression: `SUM(IF(${cond}, ${c}, 0))`, name: f.name || `Total ${f.column} (filtered)` }
    : { expression: `AVG(IF(${cond}, ${c}, None))`, name: f.name || `Average ${f.column} (filtered)` }
}
