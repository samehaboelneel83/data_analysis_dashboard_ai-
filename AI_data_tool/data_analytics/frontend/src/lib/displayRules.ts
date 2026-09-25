/**
 * Compiles a structured display-rule condition into an expression string for the
 * backend engine (backend/app/services/display_rules.py).
 *
 * This mirrors lib/customCategories.ts: the author edits the structured form, the
 * compiled string is what runs, and both are persisted so a rule stays editable.
 * Nothing here stops us emitting syntax the engine rejects — that is exactly how the
 * expression palette once shipped `.str.upper()` snippets that could never run — so
 * backend/tests/test_display_rules_contract.py asserts these strings verbatim.
 */
export type RuleOperator =
  | 'eq' | 'ne' | 'gt' | 'gte' | 'lt' | 'lte' | 'between' | 'in' | 'isnull' | 'notnull'

export interface RuleCondition {
  op: RuleOperator
  value?: unknown
  value2?: unknown
}

export interface RuleStyle {
  fill?: string
  text?: string
  icon?: string
  background?: string
  /** 0..1 proportional fill for a `data_bar` rule's in-cell bar. */
  bar?: number
}

export interface DisplayRule {
  id: string
  kind: 'expression' | 'value_map' | 'interval' | 'data_bar'
  target: 'mark' | 'background' | 'visibility'
  label?: string
  column?: string
  expression?: string
  condition?: RuleCondition
  style?: RuleStyle
  mappings?: { value: unknown; color: string }[]
  any_category?: boolean
  bands?: { min: number; max: number; color: string; icon?: string }[]
  // `data_bar` only. Min/max are optional -- omitted, the engine
  // (services/display_rules.py::_data_bar_styles) scales to the column's own
  // observed range instead of a fixed one.
  min?: number
  max?: number
  color?: string
}

export interface RuleStyles {
  rows: (RuleStyle | null)[]
  cells: Record<string, Record<string, RuleStyle>>
  widget: { background?: string; hidden?: boolean }
}

const BARE_IDENTIFIER = /^[A-Za-z_][A-Za-z0-9_]*$/

function col(name: string): string {
  return BARE_IDENTIFIER.test(name) ? name : `\`${name}\``
}

function literal(value: unknown): string {
  if (typeof value === 'number') return String(value)
  // Python has no lowercase `true`/`false` — those are just names. A bare name passes
  // _validate_expr_safety's AST allowlist (it's a plain ast.Name), so a JS-style
  // `String(value)` here would not be rejected at validation time; it would fail later
  // in _eval_expr with `NameError: name 'true' is not defined`, which display rules
  // swallow into rule_errors. The rule then silently never applies. Emit `True`/`False`.
  if (typeof value === 'boolean') return value ? 'True' : 'False'
  return `"${String(value).replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`
}

const COMPARISONS: Partial<Record<RuleOperator, string>> = {
  eq: '==', ne: '!=', gt: '>', gte: '>=', lt: '<', lte: '<=',
}

export function compileCondition(column: string, cond: RuleCondition): string {
  const c = col(column)

  if (cond.op === 'between') return `(${c} >= ${literal(cond.value)}) and (${c} <= ${literal(cond.value2)})`
  if (cond.op === 'in') {
    const items = (Array.isArray(cond.value) ? cond.value : [cond.value]).map(literal)
    return `${c} in [${items.join(', ')}]`
  }
  // `not isnull(x)` would evaluate `not` on a Series, which raises "truth value is
  // ambiguous". Comparing to a boolean keeps it elementwise.
  if (cond.op === 'isnull') return `isnull(${c}) == True`
  if (cond.op === 'notnull') return `isnull(${c}) == False`

  const operator = COMPARISONS[cond.op]
  if (!operator) throw new Error(`Unsupported display-rule operator: ${cond.op}`)
  return `${c} ${operator} ${literal(cond.value)}`
}
