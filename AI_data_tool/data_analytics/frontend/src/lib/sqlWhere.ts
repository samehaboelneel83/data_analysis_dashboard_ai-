/**
 * D3: a small SQL-specific compiler for the query-builder's WHERE rows.
 *
 * lib/simpleExpr.ts (C2/Batch 4) is the codeless-expression compiler for
 * pandas-style filter/computed-column text (`==`, `isnull()`, Python
 * literals). The query builder's WHERE clause is SQL, not pandas expr, and
 * the actual SQL that runs is compiled server-side by
 * services/query_builder.py against the introspected schema (identifiers
 * membership-checked, values single-quote-doubled). Forcing that pandas
 * compiler to also emit SQL would mean two dialects sharing one module for
 * no real gain -- so this module adapts only the SHAPE that genuinely
 * fits: structured condition rows joined by a single AND/OR (the same
 * "one joiner ties every row together" model as simpleExpr's
 * SimpleExprState), compiled to a WHERE-clause preview with the same
 * quoting convention the backend uses (numbers bare, everything else a
 * single-quoted, single-quote-doubled string literal). It never decides
 * what actually runs -- that authority stays server-side.
 */

export type SqlOperator =
  | 'eq' | 'ne' | 'gt' | 'gte' | 'lt' | 'lte'
  | 'contains' | 'in' | 'is_null' | 'not_null'

export type SqlJoiner = 'and' | 'or'

export interface SqlConditionRow {
  table?: string
  column: string
  op: SqlOperator
  value: string
}

const OP_SQL: Record<'eq' | 'ne' | 'gt' | 'gte' | 'lt' | 'lte', string> = {
  eq: '=', ne: '<>', gt: '>', gte: '>=', lt: '<', lte: '<=',
}

// Same convention as query_builder.py's _encode_value: numbers pass through
// bare, everything else becomes a single-quoted literal with quote doubling
// (the one escape SQL string literals define -- never string concatenation).
export function sqlLiteral(raw: string): string {
  const trimmed = raw.trim()
  if (trimmed !== '' && !isNaN(Number(trimmed))) return String(Number(trimmed))
  return `'${raw.replace(/'/g, "''")}'`
}

/** Compiles one row to a WHERE fragment, or '' when it isn't complete enough
 *  to mean anything yet (a row an author hasn't finished filling in). */
export function compileConditionRow(row: SqlConditionRow): string {
  if (!row.column) return ''
  const col = row.column

  if (row.op === 'is_null') return `${col} IS NULL`
  if (row.op === 'not_null') return `${col} IS NOT NULL`

  if (row.op === 'contains') {
    if (row.value.trim() === '') return ''
    return `${col} LIKE '%${row.value.replace(/'/g, "''")}%'`
  }
  if (row.op === 'in') {
    const vals = row.value.split(',').map(v => v.trim()).filter(Boolean)
    if (vals.length === 0) return ''
    return `${col} IN (${vals.map(sqlLiteral).join(', ')})`
  }

  if (row.value.trim() === '') return ''
  return `${col} ${OP_SQL[row.op]} ${sqlLiteral(row.value)}`
}

/** Joins every complete row with a single AND/OR -- the whole set shares one
 *  joiner, same shape as simpleExpr's SimpleExprState, not per-pair logic. */
export function compileWhere(rows: SqlConditionRow[], joiner: SqlJoiner): string {
  const parts = rows.map(compileConditionRow).filter(Boolean)
  if (parts.length === 0) return ''
  if (parts.length === 1) return parts[0]
  return parts.join(` ${joiner.toUpperCase()} `)
}
