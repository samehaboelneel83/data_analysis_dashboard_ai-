/**
 * Custom categories — SAS's "custom category", Power BI's New group / New bin.
 *
 * These compile to expressions for the *existing* calculated-column engine rather
 * than introducing a parallel mechanism. The payoff is that the result is an ordinary
 * calculated column everywhere: the query path evaluates it, display formats apply to
 * it, the Fields pane lists it, and no backend code changed. The cost is that the
 * generated syntax has to be exactly right, which is what the tests pin down.
 *
 * Two shapes are supported:
 *   - grouping: named buckets of specific values   -> SWITCH(col, v, name, ..., default)
 *   - binning:  numeric intervals                  -> nested IF(col < edge, label, ...)
 */

export interface ValueGroup {
  name: string
  values: string[]
}

/** Column references need backticks when they contain anything but word characters —
 *  the expression validator normalises backtick-quoted names before parsing. */
function ref(column: string): string {
  return /^[A-Za-z_]\w*$/.test(column) ? column : `\`${column}\``
}

/** Values are emitted as double-quoted literals, so an embedded quote must be escaped
 *  or the expression stops parsing at that point. */
function lit(value: string): string {
  return `"${String(value).replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`
}

/**
 * Map named groups of values onto a single category column.
 * Values not in any group fall through to `otherLabel`.
 */
export function groupingExpression(column: string, groups: ValueGroup[], otherLabel = 'Other'): string {
  const pairs: string[] = []
  for (const g of groups) {
    for (const v of g.values) {
      pairs.push(lit(v), lit(g.name))
    }
  }
  // No mappings means the column would just be rebranded with a constant default,
  // which is never what the author wanted — signal "nothing to build" instead.
  if (pairs.length === 0) return ''
  return `SWITCH(${ref(column)}, ${pairs.join(', ')}, ${lit(otherLabel)})`
}

/**
 * Bucket a numeric column into intervals. `edges` are ascending boundaries and the
 * expression nests ascending `<` comparisons so the first match wins.
 *
 * `closedTop` decides what happens at and above the last edge. With hand-specified
 * edges the caller may not know the column's maximum, so the default is an
 * open-ended `"<last>+"` bucket that cannot silently drop rows. When the last edge
 * *is* the maximum — as it is for `defaultBinEdges` — pass `closedTop` so the top
 * interval simply includes it; otherwise asking for 2 bins over [0, 100] yields a
 * surprising third bucket holding nothing but the single maximum value.
 */
export function binningExpression(column: string, edges: number[], closedTop = false): string {
  const sorted = [...new Set(edges.filter(e => Number.isFinite(e)))].sort((a, b) => a - b)
  if (sorted.length < 2) return ''

  const col = ref(column)
  /**
   * "0-10" reads perfectly; "-12012--4991" does not. The hyphen stays for the
   * ordinary case — every existing label is written that way and it is exactly
   * right there — and gives way to " to " only when a bound is negative, which
   * is the only time the two numbers cannot be told apart. Seen on real data:
   * revenue with refunds in it bins into two negative edges.
   */
  const label = (lo: number, hi: number) =>
    lit(lo < 0 || hi < 0 ? `${lo} to ${hi}` : `${lo}-${hi}`)
  const last = sorted.length - 1

  // Build from the innermost bucket outwards.
  let expr = closedTop
    ? label(sorted[last - 1], sorted[last])
    : lit(`${sorted[last]}+`)
  const from = closedTop ? last - 1 : last
  for (let i = from; i >= 1; i--) {
    expr = `IF(${col} < ${sorted[i]}, ${label(sorted[i - 1], sorted[i])}, ${expr})`
  }
  return expr
}

/** Evenly spaced edges across [min, max], rounded so bucket labels stay readable. */
export function defaultBinEdges(min: number, max: number, bins: number): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max) || max <= min || bins < 1) return []
  const step = (max - min) / bins
  // Round to a sensible precision for the magnitude of the step, then clamp the ends
  // back to the true min/max so no data falls outside the buckets.
  const decimals = step >= 10 ? 0 : step >= 1 ? 1 : 2
  const round = (n: number) => Number(n.toFixed(decimals))
  const edges = Array.from({ length: bins + 1 }, (_, i) => round(min + i * step))
  edges[0] = round(min)
  edges[edges.length - 1] = round(max)
  return [...new Set(edges)]
}
