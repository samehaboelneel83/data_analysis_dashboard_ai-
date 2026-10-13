import type { RoleField } from '../types/report'
import { configKeyFor, HIER_MAX_DEPTH } from '../types/report'

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
 *
 * QA6 B2: a hierarchy widget's `levels` is an ordered list. A category
 * field that fits no empty single role goes on the END of it (the next level
 * in), up to the deepest a hierarchy draws; a quantity never does. Not while
 * the widget is in parent-child mode, which ignores `levels`. A multi role is
 * returned as is: the caller appends to it rather than replacing it.
 */
export function isNumericRole(rf: RoleField): boolean {
  return /numeric/i.test(rf.label ?? '') || rf.role.startsWith('measure') || rf.role === 'size' || rf.role === 'target'
}

export function roleForField(specs: RoleField[], config: Record<string, unknown>, column: string, numeric: boolean): RoleField | null {
  const has = (v: unknown) => v === column || (Array.isArray(v) && v.includes(column))
  if (specs.some(rf => has(config[configKeyFor(rf.role)]))) return null
  const empty = specs.filter(rf => !rf.multi && !config[configKeyFor(rf.role)])
  const levels = config.id_col && config.parent_col ? undefined : specs.find(rf => rf.multi && rf.role === 'levels'
    && (Array.isArray(config.levels) ? config.levels.length : 0) < HIER_MAX_DEPTH)
  if (!numeric) {
    const fits = empty.filter(rf => !isNumericRole(rf))
    return fits.find(rf => rf.required) ?? fits[0] ?? levels ?? null
  }
  // A quantity is never a nesting level: with Value taken it makes a new chart.
  return empty.find(isNumericRole) ?? empty.find(rf => rf.required) ?? empty[0] ?? null
}
