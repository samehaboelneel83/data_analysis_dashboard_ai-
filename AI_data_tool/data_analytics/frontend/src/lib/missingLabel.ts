/**
 * The labels a missing value arrives as from the column profile (pandas
 * `value_counts(dropna=False)` stringified: "nan", "None", "NaT", "<NA>").
 * Shown to people as "Empty" (guided setup, phase 5: `nan 73%` was the
 * owner's own example of a result that is correct and unreadable).
 */
const MISSING = new Set(['nan', 'NaN', 'None', 'NaT', '<NA>', 'null', ''])

export function isMissingLabel(value: unknown): boolean {
  return value === null || value === undefined || (typeof value === 'string' && MISSING.has(value.trim()))
}
