/**
 * How well a column's values land on a set of map regions -- measured BEFORE
 * the author commits, so "3 governorates did not match" is found in a dialog
 * rather than as a gap in a finished dashboard. (SAS's New Geography Item:
 * "86% mapped · 1 of 1 unmapped values: England"; the SAS bundle calls it the
 * single best interaction in the product.)
 *
 * Matching goes through `matchRegion`, the exact function the map renderers
 * use, so the number the dialog shows is the number the map will draw.
 */
import { matchRegion, type RegionFeature, type RegionSet } from '../components/report/geo/worldGeometry'

export interface ValueCount { name: unknown; count: number }

export interface GeoMatchReport {
  /** Rows (summed counts) whose value names a region. */
  matchedRows: number
  totalRows: number
  /** 0-100, rounded down: "100%" must mean every row, not 99.6. */
  pctRows: number
  matchedValues: number
  totalValues: number
  /** Unmatched values, most rows first -- the ones worth fixing first. */
  unmatched: { name: string; count: number }[]
  /** Regions that at least one value landed on (for the preview map). */
  matchedFeatures: Set<RegionFeature>
}

export function geoMatchReport(values: readonly ValueCount[], set: RegionSet): GeoMatchReport {
  let matchedRows = 0, totalRows = 0, matchedValues = 0, totalValues = 0
  const unmatched: { name: string; count: number }[] = []
  const matchedFeatures = new Set<RegionFeature>()
  for (const v of values) {
    const count = Number(v.count) || 0
    if (v.name == null || String(v.name).trim() === '') continue
    totalRows += count
    totalValues++
    const f = matchRegion(v.name, set)
    if (f) {
      matchedRows += count
      matchedValues++
      matchedFeatures.add(f)
    } else {
      unmatched.push({ name: String(v.name), count })
    }
  }
  unmatched.sort((a, b) => b.count - a.count || a.name.localeCompare(b.name))
  const pctRows = totalRows ? Math.floor((matchedRows / totalRows) * 100) : 0
  return { matchedRows, totalRows, pctRows, matchedValues, totalValues, unmatched, matchedFeatures }
}

/** "86% of rows mapped · 3 of 27 values unmatched: England (120 rows), …" */
export function geoMatchSentence(r: GeoMatchReport, maxNames = 3): string {
  if (r.totalValues === 0) return 'No values to map.'
  const head = `${r.pctRows}% of rows mapped`
  if (r.unmatched.length === 0) return `${head} · all ${r.totalValues} values found`
  const names = r.unmatched.slice(0, maxNames)
    .map(u => `${u.name} (${u.count.toLocaleString()} row${u.count === 1 ? '' : 's'})`).join(', ')
  const more = r.unmatched.length > maxNames ? `, +${r.unmatched.length - maxNames} more` : ''
  return `${head} · ${r.unmatched.length} of ${r.totalValues} values unmatched: ${names}${more}`
}
