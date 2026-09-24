/**
 * Compiles the "Simple" structured mode of ExpressionBuilder (C2) into the same
 * text expression the Advanced textarea edits directly. Generalizes
 * displayRules.compileCondition's pattern (structured form -> compiled string,
 * both kept so the rule stays editable) to a multi-row, AND/OR-joined builder that
 * also understands function calls and the System-parameter tokens.
 *
 * Text is the source of truth (see ExpressionBuilder.tsx docstring): this module
 * only ever compiles forward, never parses text back into rows.
 */

export type SimpleOperator = 'eq' | 'ne' | 'gt' | 'gte' | 'lt' | 'lte' | 'isnull' | 'notnull'
export type SimpleValueKind = 'literal' | 'column' | 'system'

export interface SimpleConditionRow {
  type: 'condition'
  column: string
  op: SimpleOperator
  valueKind: SimpleValueKind
  value: string
}

export interface SimpleFunctionRow {
  type: 'function'
  fn: string
  args: string[]
}

export type SimpleRow = SimpleConditionRow | SimpleFunctionRow
export type SimpleJoiner = 'and' | 'or'

export interface SimpleExprState {
  rows: SimpleRow[]
  joiner: SimpleJoiner
}

// A small static arity map for the common functions — named argument slots.
// Anything not listed here falls back to a single free-text argument list (the
// author types "col, 3" etc. and it's inserted verbatim, comma-split).
export const FUNCTION_ARITY: Record<string, string[]> = {
  'abs':         ['value'],
  'round':       ['value', 'decimals'],
  'SENTIMENT':   ['text'],
  'SENTIMENT_LABEL': ['text'],
  'UPPER':       ['text'],
  'LOWER':       ['text'],
  'TRIM':        ['text'],
  'LEN':         ['text'],
  'CONTAINS':    ['text', 'search'],
  'STARTSWITH':  ['text', 'search'],
  'ENDSWITH':    ['text', 'search'],
  'isnull':      ['value'],
  'YEAR':        ['date'],
  'MONTH':       ['date'],
  'DAY':         ['date'],
  'IF':          ['condition', 'if_true', 'if_false'],
}

const BARE_IDENTIFIER = /^[A-Za-z_][A-Za-z0-9_]*$/

export function colRef(name: string): string {
  return name && BARE_IDENTIFIER.test(name) ? name : `\`${name}\``
}

// Same literal-quoting convention as lib/displayRules.ts: numbers and True/False
// pass through unquoted, everything else becomes an escaped string literal.
export function literal(raw: string): string {
  if (raw.trim() !== '' && !isNaN(Number(raw))) return String(Number(raw))
  if (raw === 'true' || raw === 'false') return raw === 'true' ? 'True' : 'False'
  return `"${raw.replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`
}

const COMPARISONS: Record<Exclude<SimpleOperator, 'isnull' | 'notnull'>, string> = {
  eq: '==', ne: '!=', gt: '>', gte: '>=', lt: '<', lte: '<=',
}

/** Compiles one row to text, or '' when it isn't complete enough to mean anything
 *  yet (an in-progress row an author hasn't finished — never emitted mid-edit). */
export function compileRow(row: SimpleRow): string {
  if (row.type === 'function') {
    const args = row.args.map(a => a.trim()).filter(a => a !== '')
    if (!row.fn || args.length === 0) return ''
    return `${row.fn}(${args.join(', ')})`
  }

  const { column, op, valueKind, value } = row
  if (!column) return ''
  const c = colRef(column)

  if (op === 'isnull') return `isnull(${c}) == True`
  if (op === 'notnull') return `isnull(${c}) == False`

  if (value.trim() === '') return ''
  const rhs = valueKind === 'literal' ? literal(value) : valueKind === 'column' ? colRef(value) : value
  return `${c} ${COMPARISONS[op]} ${rhs}`
}

export function compileSimple(state: SimpleExprState): string {
  const parts = state.rows.map(compileRow).filter(Boolean)
  if (parts.length === 0) return ''
  if (parts.length === 1) return parts[0]
  return parts.join(` ${state.joiner} `)
}

export function emptyConditionRow(defaultColumn: string): SimpleConditionRow {
  return { type: 'condition', column: defaultColumn, op: 'eq', valueKind: 'literal', value: '' }
}
