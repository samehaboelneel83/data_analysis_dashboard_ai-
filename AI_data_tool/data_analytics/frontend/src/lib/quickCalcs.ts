/**
 * One-click calculations offered from the field list.
 *
 * A widget already had quick calcs — percent of total, difference, percent
 * change, rank — applied to the values that visual aggregated. SAS also offers
 * them from the DATA ITEM, where the result is a new reusable field rather than
 * a setting on one chart, and that is what this produces.
 *
 * The honest mapping is a **measure**, not a calculated column. `measure_eval`
 * evaluates at the requesting widget's grain, so `SUM(x) / TOTAL(SUM(x)) * 100`
 * is a real percent-of-total that re-bases when the visual's crossing changes;
 * a row-level calculated column would freeze it at definition time.
 *
 * Two constraints shape what can be offered:
 *
 *   * **Only functions the measure language has** — SUM, AVG, MEDIAN, COUNT,
 *     COUNTD, STDEV, VARIANCE plus the context functions. A one-click
 *     calculation that saves and then fails to evaluate is worse than no offer.
 *
 *   * **Only columns it can NAME.** `measure_eval` binds each column to a
 *     Python identifier and `eval`s the expression, so a column called
 *     "net revenue" cannot be referenced at all — there is no quoting form.
 *     Those fields are offered nothing rather than something broken.
 */

export interface QuickCalcField {
  name: string
  dtype: string
  numeric: boolean
}

export interface QuickCalc {
  key: string
  /** Menu label. */
  label: string
  /** The measure's name, which is what appears in the field list afterwards. */
  name: string
  expression: string
}

/** Python identifiers only, and never a bare keyword-ish digit start. */
const IDENTIFIER = /^[A-Za-z_][A-Za-z0-9_]*$/

export function quickCalcsFor(field: QuickCalcField): QuickCalc[] {
  const c = field.name
  if (!IDENTIFIER.test(c)) return []

  if (field.numeric) {
    return [
      { key: 'percent_of_total', label: '% of total',
        name: `% of total ${c}`,
        expression: `SUM(${c}) / TOTAL(SUM(${c})) * 100` },
      { key: 'average', label: 'Average', name: `Average ${c}`,
        expression: `AVG(${c})` },
      { key: 'median', label: 'Median', name: `Median ${c}`,
        expression: `MEDIAN(${c})` },
      { key: 'stdev', label: 'Standard deviation', name: `Std dev of ${c}`,
        expression: `STDEV(${c})` },
      { key: 'distinct', label: 'Distinct values', name: `Distinct ${c}`,
        expression: `COUNTD(${c})` },
    ]
  }
  // A category has no average and no spread. What it has is how many distinct
  // values a group holds, and what share of the rows it accounts for.
  return [
    { key: 'distinct', label: 'Distinct values', name: `Distinct ${c}`,
      expression: `COUNTD(${c})` },
    { key: 'percent_of_rows', label: '% of rows', name: `% of rows by ${c}`,
      expression: `COUNT(${c}) / TOTAL(COUNT(${c})) * 100` },
  ]
}

/** A name no existing measure holds.
 *
 *  `measuresApi.save` is an upsert by name: colliding would silently replace
 *  someone else's definition with this one, which is the kind of data loss
 *  nobody would think to look for. */
export function uniqueMeasureName(base: string, existing: string[]): string {
  const taken = new Set(existing)
  if (!taken.has(base)) return base
  for (let n = 2; n < 1000; n++) {
    const candidate = `${base} (${n})`
    if (!taken.has(candidate)) return candidate
  }
  return `${base} (${Date.now()})`
}
