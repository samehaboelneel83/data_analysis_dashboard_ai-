import type { RoleField } from '../types/report'
import { configKeyFor, HIER_MAX_DEPTH, roleAccepts } from '../types/report'

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
  // C-09: the same rule the role pickers use (roleAccepts), so lat/lon count
  // as numeric roles and a text field can never be clicked into them.
  return roleAccepts(rf.role) === 'numeric'
    || /numeric/i.test(rf.label ?? '') || rf.role.startsWith('measure') || rf.role === 'size' || rf.role === 'target'
}

/** Which coordinate a column's NAME says it holds (origin_lat, dest_lon,
 *  latitude, lng...), or null. */
export function coordinateAxis(column: string): 'lat' | 'lon' | null {
  const parts = column.toLowerCase().split(/[^a-z0-9]+|(?<=[a-z])(?=\d)/).filter(Boolean)
  if (parts.some(p => p === 'lat' || p === 'latitude')) return 'lat'
  if (parts.some(p => p === 'lon' || p === 'lng' || p === 'long' || p === 'longitude')) return 'lon'
  return null
}

const COORD_ROLES = new Set(['lat', 'lon', 'lat2', 'lon2'])

export function roleForField(specs: RoleField[], config: Record<string, unknown>, column: string, numeric: boolean): RoleField | null {
  const has = (v: unknown) => v === column || (Array.isArray(v) && v.includes(column))
  if (specs.some(rf => has(config[configKeyFor(rf.role)]))) return null
  const empty = specs.filter(rf => !rf.multi && !config[configKeyFor(rf.role)])
  // C-09: a coordinate goes to its own axis (then the second point's), on a
  // widget that has one -- never into Country, and a city never into Longitude.
  const axis = coordinateAxis(column)
  if (axis && specs.some(rf => rf.role === axis)) {
    return empty.find(rf => rf.role === axis) ?? empty.find(rf => rf.role === `${axis}2`) ?? null
  }
  const levels = config.id_col && config.parent_col ? undefined : specs.find(rf => rf.multi && rf.role === 'levels'
    && (Array.isArray(config.levels) ? config.levels.length : 0) < HIER_MAX_DEPTH)
  if (!numeric) {
    const fits = empty.filter(rf => !isNumericRole(rf))
    return fits.find(rf => rf.required) ?? fits[0] ?? levels ?? null
  }
  // A quantity is never a nesting level: with Value taken it makes a new chart.
  // Nor a coordinate: a measure like `shipments` (2-40) is not a longitude.
  // On a map, Country is a NAME role: a number never falls back into it.
  const isMap = specs.some(rf => COORD_ROLES.has(rf.role))
  const notCoord = empty.filter(rf => !COORD_ROLES.has(rf.role) && !(isMap && rf.role === 'category'))
  return notCoord.find(isNumericRole) ?? notCoord.find(rf => rf.required) ?? notCoord[0] ?? null
}
