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
import { translate, type TranslateFn } from '../i18n'

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

const EN: TranslateFn = (key, vars) => translate('en', key, vars)

/** "86% of rows mapped · 3 of 27 values unmatched: England (120 rows), …",
 *  in the reader's language (`t`; English by default). */
export function geoMatchSentence(r: GeoMatchReport, maxNames = 3, t: TranslateFn = EN): string {
  if (r.totalValues === 0) return t('pg.panelsA.lib.geo.none')
  const head = t('pg.panelsA.lib.geo.head', { pct: r.pctRows })
  if (r.unmatched.length === 0) return t('pg.panelsA.lib.geo.allFound', { head, total: r.totalValues })
  const names = r.unmatched.slice(0, maxNames)
    .map(u => t('pg.panelsA.lib.geo.value', { name: String(u.name), n: u.count.toLocaleString() }))
    .join(t('pg.panelsA.lib.geo.sep'))
  const more = r.unmatched.length > maxNames ? t('pg.panelsA.lib.geo.more', { n: r.unmatched.length - maxNames }) : ''
  return t('pg.panelsA.lib.geo.unmatched', { head, k: r.unmatched.length, total: r.totalValues, names, more })
}
