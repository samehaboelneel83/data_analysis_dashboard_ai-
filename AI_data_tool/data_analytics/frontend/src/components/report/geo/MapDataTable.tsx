/**
 * What a map shows, for someone who cannot see it (E15).
 *
 * A map was an image with a two-word name ("Choropleth map"): a screen reader
 * heard that and nothing else, and a keyboard could not reach a region. Every
 * map now names what it plots, how many places carry a value and the highest
 * and lowest; and carries its values as a table that is read, not drawn.
 */
import { fmtStr } from '../chartUtils'
import { translate, useT, type TranslateFn } from '../../../i18n'

const EN: TranslateFn = (k, v) => translate('en', k, v)

export interface MapEntry { label: string; value: number }

const MAX_ROWS = 200

/** One sentence: what, how many, the extremes. */
export function mapSummary(kind: string, entries: MapEntry[], measureFmt?: unknown, t: TranslateFn = EN): string {
  if (!entries.length) return t('pg.modelsMaps.map.none', { kind })
  const sorted = [...entries].sort((a, b) => b.value - a.value)
  const hi = sorted[0], lo = sorted[sorted.length - 1]
  const f = (v: number) => fmtStr(v, measureFmt as never)
  const places = t('pg.modelsMaps.map.places', { n: entries.length })
  return entries.length === 1
    ? t('pg.modelsMaps.map.one', { kind, places, label: hi.label, value: f(hi.value) })
    : t('pg.modelsMaps.map.many', { kind, places, hi: hi.label, hiValue: f(hi.value), lo: lo.label, loValue: f(lo.value) })
}

/** The values behind the map, largest first, visually hidden. */
export function MapDataTable({ caption, entries, measureFmt, unmatched = 0 }: {
  caption: string; entries: MapEntry[]; measureFmt?: unknown; unmatched?: number
}) {
  const t = useT()
  const sorted = [...entries].sort((a, b) => b.value - a.value)
  return (
    <table className="dl-sr-only" data-testid="map-data-table">
      <caption>{caption}{unmatched > 0 ? ` (${t('pg.modelsMaps.map.notPlaced', { n: unmatched })})` : ''}</caption>
      <thead><tr><th scope="col">{t('pg.modelsMaps.map.place')}</th><th scope="col">{t('pg.modelsMaps.map.value')}</th></tr></thead>
      <tbody>
        {sorted.slice(0, MAX_ROWS).map((e, i) => (
          <tr key={`${e.label}-${i}`}><th scope="row">{e.label}</th><td>{fmtStr(e.value, measureFmt as never)}</td></tr>
        ))}
        {sorted.length > MAX_ROWS && (
          <tr><td colSpan={2}>{t('pg.modelsMaps.map.more', { n: sorted.length - MAX_ROWS })}</td></tr>
        )}
      </tbody>
    </table>
  )
}

/** QA6 A4: what a map says while its code loads, in the UI language. */
export function MapLoading() {
  const t = useT()
  return <div style={{ fontSize: 11, color: 'var(--muted)', padding: 8 }}>{t('pg.modelsMaps.map.loading')}</div>
}
