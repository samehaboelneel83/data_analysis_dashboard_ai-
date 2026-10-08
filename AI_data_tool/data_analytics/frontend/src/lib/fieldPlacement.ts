import type { RoleField } from '../types/report'
import { configKeyFor } from '../types/report'

/**
 * QA4 E2: which empty role a field dropped (or clicked) onto a widget fills.
 *
 * Before, a text field dropped on a bar that already had its dimension went
 * into the next free role -- Series, then Measure, then Target -- and the same
 * column could fill two roles ("Rows and Columns are both 'region'").
 * Now:
 *  - a column the widget already uses, in any role, is never placed again;
 *  - a text field only goes into a role that takes categories (never a
 *    Measure, Target or Size);
 *  - a number prefers a numeric role, then a required one, then any.
 * null means no role fits: the caller makes a new chart instead, and says so.
 */
export function isNumericRole(rf: RoleField): boolean {
  return /numeric/i.test(rf.label ?? '') || rf.role.startsWith('measure') || rf.role === 'size' || rf.role === 'target'
}

export function roleForField(specs: RoleField[], config: Record<string, unknown>, column: string, numeric: boolean): RoleField | null {
  const has = (v: unknown) => v === column || (Array.isArray(v) && v.includes(column))
  if (specs.some(rf => has(config[configKeyFor(rf.role)]))) return null
  const empty = specs.filter(rf => !rf.multi && !config[configKeyFor(rf.role)])
  if (!numeric) {
    const fits = empty.filter(rf => !isNumericRole(rf))
    return fits.find(rf => rf.required) ?? fits[0] ?? null
  }
  return empty.find(isNumericRole) ?? empty.find(rf => rf.required) ?? empty[0] ?? null
}
